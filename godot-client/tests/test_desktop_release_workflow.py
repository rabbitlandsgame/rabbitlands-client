"""Static checks of the desktop release workflows (.github/workflows). No GitHub call, no run, no network."""
import inspect
import os
import re
import shlex
import subprocess
import sys
from pathlib import Path

import pytest

yaml = pytest.importorskip("yaml")

GODOT = Path(__file__).resolve().parents[1]
REPO = GODOT.parent
TOOLS = GODOT / "tools"
WORKFLOWS = REPO / ".github" / "workflows"
sys.path.insert(0, str(TOOLS))
import actions_release  # noqa: E402
import desktop_release_ci  # noqa: E402
import runner_release  # noqa: E402

R2_FILE, REPOINT_FILE, OLD_FILE = "desktop-release-r2.yml", "desktop-repoint.yml", "desktop-release.yml"
NEW_FILES = (R2_FILE, REPOINT_FILE)
DESKTOP_FILES = (OLD_FILE, R2_FILE, REPOINT_FILE, "published-client-cleanup.yml")
ALL_FILES = tuple(sorted(path.name for path in WORKFLOWS.glob("*.yml")))  # every workflow, store-build.yml too
KEY = "CLIENT_UPDATE_SIGNING_KEY"
KEY_VALUE = "${{ secrets.CLIENT_UPDATE_SIGNING_KEY }}"
PLATFORMS = ("windows", "linux")
ALLOWED_ACTIONS = {"actions/checkout", "actions/setup-python", "actions/upload-artifact",
                   "actions/download-artifact", "actions/cache"}
RUNNERS = {"ubuntu-24.04", "windows-2025"}
SPARSE_R2 = ["/godot-client/tools/", "/godot-client/src/updates/", "/godot-client/src/app/main.tscn",
             "/godot-client/assets/branding/", "/godot-client/assets/audio/CREDITS.txt", "/godot-client/native/",
             "/godot-client/data/update_public.pem", "/godot-client/project.godot"]
SIGN_REQUIREMENTS = "godot-client/tools/desktop-sign-requirements.txt"
RELEASE_REQUIREMENTS = "godot-client/tools/desktop-release-requirements.txt"
CONTENT_REQUIREMENTS = "godot-client/tools/desktop-content-requirements.txt"
# desktop_release_ci.py subcommands that later chunks add (contract named here, checked by r2-prepare).
PENDING_CI_COMMANDS = {}


# --- loading ----------------------------------------------------------------------------------

class UniqueKeyLoader(yaml.SafeLoader):
    """A SafeLoader that refuses duplicate mapping keys (PyYAML keeps the last one silently)."""


def _mapping(loader, node, deep=False):
    seen = set()
    for key_node, _ in node.value:
        key = loader.construct_object(key_node, deep=deep)
        if key in seen:
            raise yaml.constructor.ConstructorError(None, None, f"duplicate key {key!r}", key_node.start_mark)
        seen.add(key)
    return loader.construct_mapping(node, deep=deep)


UniqueKeyLoader.add_constructor(yaml.resolver.BaseResolver.DEFAULT_MAPPING_TAG, _mapping)


def text(name: str) -> str:
    return (WORKFLOWS / name).read_text(encoding="utf-8")


def load(name: str) -> dict:
    return yaml.load(text(name), Loader=UniqueKeyLoader)  # noqa: S506 - SafeLoader subclass


def triggers(workflow: dict) -> dict:
    return workflow.get("on", workflow.get(True))  # YAML 1.1 reads a bare `on` key as True


def jobs(name: str) -> dict:
    return load(name)["jobs"]


def steps(job: dict) -> list:
    return job.get("steps", [])


def runs(job: dict) -> list:
    return [step for step in steps(job) if "run" in step]


def commands(step: dict) -> list:
    """Every `python godot-client/tools/<tool>.py ...` line of a run step, split like a shell would."""
    return [shlex.split(line.strip()) for line in step.get("run", "").splitlines()
            if line.strip().startswith("python godot-client/tools/")]


def uses(step: dict) -> str:
    return step.get("uses", "").split("@", 1)[0]


def expand(value: str) -> set:
    """Artifact names and folders with `${{ matrix.platform }}` expanded to both platforms."""
    value = value.replace("${{ runner.temp }}", "$RUNNER_TEMP")
    if "${{ matrix.platform }}" in value:
        return {value.replace("${{ matrix.platform }}", platform) for platform in PLATFORMS}
    return {value}


def run_dir(value: str) -> set:
    return {value.replace("$PLATFORM", platform) for platform in PLATFORMS} if "$PLATFORM" in value else {value}


def needs(job: dict) -> list:
    value = job.get("needs", [])
    return [value] if isinstance(value, str) else list(value)


def references(value: str, kind: str = "needs") -> list[tuple[str, str]]:
    """(job or step, output) pairs of `needs.X.outputs.Y` / `needs.X.outputs[format(...)]` in a string."""
    found = []
    for match in re.finditer(rf"{kind}\.([A-Za-z0-9_-]+)\.(outputs\.([A-Za-z0-9_]+)|outputs\[format\('\{{0\}}_digest', "
                             r"matrix\.platform\)\]|result)", value):
        if match[2] == "result":
            found.append((match[1], "result"))
        elif match[3]:
            found.append((match[1], match[3]))
        else:
            found.extend((match[1], f"{platform}_digest") for platform in PLATFORMS)
    return found


def every_string(value):
    if isinstance(value, str):
        yield value
    elif isinstance(value, dict):
        for key, item in value.items():
            yield from every_string(key if isinstance(key, str) else "")
            yield from every_string(item)
    elif isinstance(value, list):
        for item in value:
            yield from every_string(item)


def subcommands(parser) -> dict:
    for action in parser._actions:
        if action.__class__.__name__ == "_SubParsersAction":
            return action.choices
    return {}


TOOL_PARSERS = {"actions_release.py": actions_release.build_parser(),
                "desktop_release_ci.py": desktop_release_ci.build_parser()}


# --- triggers, inputs, interpolation ---------------------------------------------------------------

@pytest.mark.parametrize("name", [R2_FILE, REPOINT_FILE, OLD_FILE])
def test_desktop_release_workflows_are_dispatch_only(name):
    workflow = load(name)
    assert set(triggers(workflow)) == {"workflow_dispatch"}
    assert "push:" not in text(name) and "pull_request" not in text(name) and "workflow_run" not in text(name)


def test_r2_inputs_reach_only_the_prepare_validation_step_through_env():
    workflow = load(R2_FILE)
    inputs = triggers(workflow)["workflow_dispatch"]["inputs"]
    assert set(inputs) == {"windows_source", "windows_set_sha256", "linux_source", "linux_set_sha256", "dry_run"}
    assert inputs["windows_source"]["options"] == ["r2", "ci", "none"]  # none: a dry run of Linux only
    assert inputs["linux_source"]["options"] == ["r2", "ci"]
    assert inputs["dry_run"]["type"] == "boolean" and inputs["dry_run"]["default"] is False
    step = next(step for step in steps(workflow["jobs"]["prepare"]) if step.get("id") == "prepare")
    assert step["env"] == {"GH_TOKEN": "${{ github.token }}",
                           **{name.upper(): f"${{{{ inputs.{name} }}}}" for name in inputs}}
    assert commands(step) == [["python", "godot-client/tools/actions_release.py", "r2-prepare"]]
    # The environment names are the ones r2_inputs reads.
    valid = {"WINDOWS_SOURCE": "r2", "WINDOWS_SET_SHA256": "a" * 64, "LINUX_SOURCE": "r2",
             "LINUX_SET_SHA256": "b" * 64, "DRY_RUN": "false"}
    assert actions_release.r2_inputs(valid)["platforms"]["linux"]["set_sha256"] == "b" * 64
    raw = text(R2_FILE)
    assert raw.count("inputs.") == len(inputs) and "github.event.inputs" not in raw
    for job_name, job in workflow["jobs"].items():
        for item in steps(job):
            if item is step:
                continue
            assert not any("inputs." in value for value in every_string(item)), (job_name, item.get("name"))
        assert not any("inputs." in value for value in every_string({k: v for k, v in job.items() if k != "steps"}))


def test_repoint_inputs_reach_only_validating_steps_through_env():
    workflow = load(REPOINT_FILE)
    inputs = triggers(workflow)["workflow_dispatch"]["inputs"]
    assert set(inputs) == {"target_commit", "platforms"}
    assert inputs["platforms"]["options"] == ["both", "windows", "linux"]
    seen = 0
    for job in workflow["jobs"].values():
        for step in steps(job):
            mentions = [value for value in every_string(step) if "inputs." in value]
            if not mentions:
                continue
            seen += 1
            assert {key: value for key, value in step["env"].items() if "inputs." in value} == {
                "TARGET_COMMIT": "${{ inputs.target_commit }}", "REPOINT_PLATFORMS": "${{ inputs.platforms }}"}
            assert len(mentions) == 2
            (command,) = commands(step)
            assert command[1:3] in (["godot-client/tools/actions_release.py", name]
                                    for name in ("repoint-check", "repoint-latest", "repoint-upload"))
    assert seen == 4
    assert actions_release.repoint_inputs({"TARGET_COMMIT": "c" * 40, "REPOINT_PLATFORMS": "both"})[1] == PLATFORMS


@pytest.mark.parametrize("name", [R2_FILE, REPOINT_FILE, OLD_FILE])
def test_no_expression_is_interpolated_into_a_shell_script(name):
    for job_name, job in load(name)["jobs"].items():
        for step in runs(job):
            assert "${{" not in step["run"], (job_name, step.get("name"))


# --- permissions, environments, secrets -------------------------------------------------------------

@pytest.mark.parametrize("name, writers", [
    (R2_FILE, {"prepare", "content-ci", "stage", "finalize", "publish", "promote"}),
    (REPOINT_FILE, {"repoint"}),
])
def test_top_level_read_and_write_only_in_the_listed_jobs(name, writers):
    workflow = load(name)
    assert workflow["permissions"] == {"contents": "read"}
    for job_name, job in workflow["jobs"].items():
        assert set(job["permissions"]) == {"contents"}, job_name  # explicit, nothing else (no id-token, actions)
        assert job["permissions"]["contents"] == ("write" if job_name in writers else "read"), job_name


def test_e2e_and_r2_content_jobs_have_no_write_token():
    workflow = jobs(R2_FILE)
    for job_name in ("content", "build", "sign", "installers", "e2e"):
        job = workflow[job_name]
        assert job["permissions"] == {"contents": "read"}, job_name
        assert not any("github.token" in value or "GH_TOKEN" in value for value in every_string(job)), job_name


@pytest.mark.parametrize("name", NEW_FILES)
def test_signing_key_only_in_environment_gated_signing_steps(name):
    raw = text(name)
    workflow = load(name)
    assert "env" not in workflow or KEY not in str(workflow["env"])
    count = 0
    for job_name, job in workflow["jobs"].items():
        assert KEY not in str(job.get("env", {})) and KEY not in str(job.get("with", {}))
        for step in steps(job):
            if not any(KEY in value for value in every_string(step)):
                continue
            count += 1
            assert job.get("environment") in ("desktop-sign", "desktop-publish"), job_name
            assert step["env"][KEY] == KEY_VALUE
            # nothing else secret or credential-like beside the key: no token, no other secret
            others = {name: value for name, value in step["env"].items() if name != KEY}
            assert not any("secrets." in value or "github.token" in value or "TOKEN" in name
                           for name, value in others.items()), (job_name, others)
            assert [value for value in every_string(step) if KEY in value] == [KEY, KEY_VALUE]
            lines = [line for line in step["run"].splitlines() if line.strip()]
            assert lines and len(lines) == len(commands(step))
            for command in commands(step):
                assert command[1:3] in (["godot-client/tools/desktop_release_ci.py", "sign"],
                                        ["godot-client/tools/desktop_release_ci.py", "pointer"])
    assert raw.count(KEY) == 2 * count
    assert count == 2  # r2: the sign step and the publish job's pointer step; repoint: one pointer step each


@pytest.mark.parametrize("name, job_name, writes", [
    (R2_FILE, "publish", {"r2-publish"}),
    (REPOINT_FILE, "repoint", {"repoint-latest", "repoint-upload"}),
])
def test_keyed_steps_sign_before_any_release_write_in_their_job(name, job_name, writes):
    """A missing or wrong key fails before the draft is published or GitHub latest moves."""
    items = steps(jobs(name)[job_name])
    keyed = [index for index, step in enumerate(items) if KEY in step.get("env", {})]
    writing = [index for index, step in enumerate(items) for command in commands(step) if command[2] in writes]
    assert keyed and len(writing) == len(writes), (name, job_name)
    assert max(keyed) < min(writing), (name, job_name)
    # the check that feeds the signing steps still runs first
    if name == REPOINT_FILE:
        (check,) = [index for index, step in enumerate(items) if step.get("id") == "check"]
        assert check < min(keyed)


def test_environments_gate_sign_publish_promote_and_repoint():
    workflow = jobs(R2_FILE)
    environments = {job_name: job.get("environment") for job_name, job in workflow.items() if job.get("environment")}
    assert environments == {"sign": "desktop-sign", "publish": "desktop-publish", "promote": "desktop-promote"}
    assert not any("secrets." in value for value in every_string(workflow["promote"]))
    repoint = jobs(REPOINT_FILE)
    assert {job_name: job.get("environment") for job_name, job in repoint.items()} == {
        "check": None, "repoint": "desktop-publish"}


@pytest.mark.parametrize("name", NEW_FILES)
def test_only_the_signing_key_is_a_secret_and_no_r2_credential_is_named(name):
    raw = text(name)
    assert set(re.findall(r"secrets\.([A-Za-z0-9_]+)", raw)) == {KEY}
    assert "secrets: inherit" not in raw and "toJSON(secrets)" not in raw
    lowered = raw.lower()
    for needle in ("aws_", "r2_access", "r2_secret", "r2_endpoint", "r2_account", "cloudflare_", "access_key",
                   "secret_access", "endpoint_url", "account_id", "cloudflarestorage", "r2-upload", "--credentials ",
                   "boto", "desktop-r2-requirements"):
        assert needle not in lowered, needle


# --- caches, checkouts, actions, runners ------------------------------------------------------

@pytest.mark.parametrize("name", NEW_FILES)
def test_no_cache_in_shipped_binary_legs_and_no_restore_keys(name):
    raw = text(name)
    assert "restore-keys" not in raw
    for job_name, job in load(name)["jobs"].items():
        for step in steps(job):
            if uses(step) == "actions/cache" or uses(step).startswith("actions/cache/"):
                assert job_name == "content-ci", job_name  # R2-A6b: exact keys only, never a shipped binary
            if uses(step) == "actions/setup-python":
                assert set(step["with"]) == {"python-version"}, job_name  # no pip cache through the cache service


@pytest.mark.parametrize("name", NEW_FILES)
def test_checkouts_are_exact_partial_and_hold_no_credentials(name):
    for job_name, job in load(name)["jobs"].items():
        checkouts = [step for step in steps(job) if uses(step) == "actions/checkout"]
        # first, or second after the line-ending step of a job that can run on Windows
        first = 1 if windows_capable(job) else 0
        assert len(checkouts) == 1 and steps(job)[first] is checkouts[0], job_name
        options = checkouts[0]["with"]
        assert options["ref"] == "${{ github.sha }}" and options["fetch-depth"] == 0, job_name
        assert options["filter"] == "blob:none" and options["persist-credentials"] is False, job_name
        assert options["sparse-checkout-cone-mode"] is False, job_name
        paths = options["sparse-checkout"].split()
        expected = SPARSE_R2 if name == R2_FILE else ["/godot-client/tools/", "/godot-client/data/update_public.pem"]
        assert paths == expected, job_name


def windows_capable(job: dict) -> bool:
    """Whether any leg of `job` runs on a Windows runner (a literal image, a matrix row, or the
    matrix r2-prepare emits from actions_release.RUNNERS)."""
    runner = job.get("runs-on", "")
    if runner != "${{ matrix.runner }}":
        return "windows" in str(runner)
    matrix = job["strategy"]["matrix"]
    if isinstance(matrix, str):
        assert "needs.prepare.outputs" in matrix, matrix
        return any(image.startswith("windows") for image in actions_release.RUNNERS.values())
    return any(str(row.get("runner", "")).startswith("windows") for row in matrix["include"])


def shell(workflow: dict, step: dict) -> str:
    return step.get("shell", workflow.get("defaults", {}).get("run", {}).get("shell", ""))


@pytest.mark.parametrize("name", ALL_FILES)
def test_windows_jobs_turn_off_line_ending_conversion_before_checkout(name):
    """Windows images default to core.autocrlf=true, and a converted checkout fails the native
    input proof (the second R2 dry run) or ships other bytes. Every job that can run on Windows
    sets the runner's global Git config first, unconditionally, before any checkout."""
    workflow = load(name)
    for job_name, job in workflow["jobs"].items():
        items = steps(job)
        exact = [index for index, step in enumerate(items)
                 if tuple(line.strip() for line in step.get("run", "").splitlines() if line.strip())
                 == runner_release.EXACT_CHECKOUT_STEPS]
        if not windows_capable(job):
            continue
        checkouts = [index for index, step in enumerate(items) if uses(step) == "actions/checkout"]
        assert checkouts and exact == [0], (name, job_name)
        step = items[0]
        assert set(step) == {"name", "run"} | ({"shell"} if "shell" in step else set()), (name, job_name)
        assert shell(workflow, step) == "bash", (name, job_name)  # Git Bash on Windows, as the tools' steps


def test_the_windows_job_classifier_finds_exactly_the_known_windows_jobs():
    found = {(name, job_name) for name in ALL_FILES for job_name, job in jobs(name).items() if windows_capable(job)}
    assert found == {(R2_FILE, "content-ci"), (R2_FILE, "build"), (R2_FILE, "installers"), (R2_FILE, "e2e"),
                     (OLD_FILE, "build"), ("store-build.yml", "build")}
    assert REPOINT_FILE in ALL_FILES  # its jobs run on Linux only


def test_the_exact_checkout_steps_disable_every_checkout_conversion(tmp_path):
    """Run on a CRLF-converting machine config, the steps' global settings give a byte-exact checkout."""
    source = tmp_path / "source"
    git = ["git", "-c", "user.name=t", "-c", "user.email=t@example.invalid"]
    subprocess.run(["git", "init", "-q", str(source)], check=True)
    (source / "native").mkdir()
    (source / "native/CMakeLists.txt").write_bytes(b"project(x)\nadd_library(x)\n")
    subprocess.run([*git, "-C", str(source), "add", "-A"], check=True)
    subprocess.run([*git, "-C", str(source), "commit", "-q", "-m", "x"], check=True)
    system, home = tmp_path / "system.gitconfig", tmp_path / "home"
    system.write_text("[core]\n\tautocrlf = true\n", encoding="ascii")  # the windows-2025 image's system config
    home.mkdir()
    env = {**os.environ, "GIT_CONFIG_SYSTEM": str(system), "GIT_CONFIG_GLOBAL": str(home / ".gitconfig"),
           "HOME": str(home)}
    env.pop("GIT_CONFIG_NOSYSTEM", None)
    converted = tmp_path / "converted"
    subprocess.run(["git", "clone", "-q", str(source), str(converted)], check=True, env=env)
    assert (converted / "native/CMakeLists.txt").read_bytes() == b"project(x)\r\nadd_library(x)\r\n"
    for command in runner_release.EXACT_CHECKOUT_STEPS:
        subprocess.run(shlex.split(command), check=True, env=env)
    exact = tmp_path / "exact"
    subprocess.run(["git", "clone", "-q", str(source), str(exact)], check=True, env=env)
    assert (exact / "native/CMakeLists.txt").read_bytes() == b"project(x)\nadd_library(x)\n"


@pytest.mark.parametrize("name", [R2_FILE, REPOINT_FILE, OLD_FILE])
def test_actions_are_pinned_to_full_commit_shas(name):
    pins = {}
    for workflow in DESKTOP_FILES:
        for line in text(workflow).splitlines():
            match = re.search(r"uses: ([^@\s]+)@(\S+)", line)
            if match:
                pins.setdefault(match[1], set()).add(match[2])
    for line in text(name).splitlines():
        if "uses:" not in line:
            continue
        match = re.fullmatch(r"\s*(?:- )?uses: ([a-z0-9-]+/[a-z0-9-]+(?:/[a-z0-9-]+)?)@([0-9a-f]{40}) # v[0-9.]+",
                             line)
        assert match, line
        assert match[1].split("/")[0] + "/" + match[1].split("/")[1] in ALLOWED_ACTIONS, line
    assert all(len(shas) == 1 for shas in pins.values()), pins  # one SHA per action across the desktop workflows


@pytest.mark.parametrize("name", NEW_FILES)
def test_jobs_have_timeouts_and_pinned_runner_images(name):
    for job_name, job in load(name)["jobs"].items():
        assert 0 < job["timeout-minutes"] <= 180, job_name
        runner = job["runs-on"]
        if runner == "${{ matrix.runner }}":
            include = job["strategy"]["matrix"]
            if isinstance(include, dict):
                assert {row["runner"] for row in include["include"]} <= RUNNERS, job_name
            else:
                assert include in ("${{ fromJSON(needs.prepare.outputs.ci_matrix) }}",
                                   "${{ fromJSON(needs.prepare.outputs.build_matrix) }}"), job_name
                assert set(actions_release.RUNNERS.values()) <= RUNNERS
        else:
            assert runner in RUNNERS, job_name


# --- Python and requirements ----------------------------------------------------------------

@pytest.mark.parametrize("name", NEW_FILES)
def test_pip_installs_are_hash_locked_and_signing_jobs_install_only_cryptography(name):
    count = 0
    for job_name, job in load(name)["jobs"].items():
        installs = [step for step in runs(job) if "pip" in step["run"]]
        uses_key = any(KEY in value for value in every_string(job))
        for step in installs:
            count += 1
            words = shlex.split(step["run"])
            assert words[:5] == ["python", "-m", "pip", "install", "--require-hashes"], job_name
            assert "--no-deps" in words and "--only-binary=:all:" in words, job_name
            assert words[-2] == "--requirement" and words.count("--requirement") == 1, job_name
            assert words[-1] in (SIGN_REQUIREMENTS, RELEASE_REQUIREMENTS, CONTENT_REQUIREMENTS), job_name
            if uses_key or job_name in ("promote", "check"):
                assert words[-1] == SIGN_REQUIREMENTS, job_name
            # numpy and Pillow (the content build's imports) only where content is built
            assert (words[-1] == CONTENT_REQUIREMENTS) == (job_name == "content-ci"), job_name
        assert len(installs) == 1 or job_name == "prepare", job_name
    assert count == len(load(name)["jobs"]) - (1 if name == R2_FILE else 0)


def requirement_blocks(path: Path) -> dict:
    data = path.read_bytes()
    assert data.isascii() and b"\r" not in data and data.endswith(b"\n")
    blocks, current = {}, None
    backslash = chr(92)
    for line in data.decode("ascii").splitlines():
        if not line or line.startswith("#"):
            current = None
            continue
        if line.startswith("    --hash=sha256:"):
            assert current, line
            assert re.fullmatch(r"    --hash=sha256:[0-9a-f]{64}( \\)?", line), line
            blocks[current].append(line.rstrip(" " + backslash))
            continue
        match = re.fullmatch(r"([a-z0-9-]+)==([0-9][A-Za-z0-9.]*) \\", line)
        assert match, line
        current = f"{match[1]}=={match[2]}"
        assert current not in blocks
        blocks[current] = []
    assert all(len(hashes) == len(set(hashes)) > 0 for hashes in blocks.values())
    return blocks


def test_requirement_files_are_exact_closed_and_match_the_local_lock():
    sign = requirement_blocks(TOOLS / "desktop-sign-requirements.txt")
    full = requirement_blocks(TOOLS / "desktop-release-requirements.txt")
    local = requirement_blocks(TOOLS / "desktop-r2-requirements.txt")
    assert {name.split("==")[0] for name in sign} == {"cryptography", "cffi", "pycparser"}
    assert {name.split("==")[0] for name in full} == {"cryptography", "cffi", "pycparser", "zstandard"}
    for name, hashes in sign.items():
        assert full[name] == hashes and local[name] == hashes, name  # one version and hash set everywhere
    pinned = dict(line.split("==") for line in (TOOLS / "runner-requirements.txt").read_text().split())
    assert f"zstandard=={pinned['zstandard']}" in full and f"cryptography=={pinned['cryptography']}" in full
    assert len(full[f"zstandard=={pinned['zstandard']}"]) > 10  # every published file, not one platform's
    # the ci content leg: the release lock plus the hosted build's numpy and Pillow, nothing else
    content = requirement_blocks(TOOLS / "desktop-content-requirements.txt")
    names = {"cryptography", "cffi", "pycparser", "zstandard", "numpy", "pillow"}
    assert {name.split("==")[0] for name in content} == names
    for name, hashes in full.items():
        assert content[name] == hashes, name
    for project in ("numpy", "Pillow"):
        name = f"{project.lower()}=={pinned[project]}"
        assert name in content and len(content[name]) > 10, name  # runner-requirements' version, every file


def test_content_lock_starts_with_the_release_lock_byte_for_byte():
    content = (TOOLS / "desktop-content-requirements.txt").read_text(encoding="ascii")
    release = (TOOLS / "desktop-release-requirements.txt").read_text(encoding="ascii")

    def body(text):
        return [line for line in text.splitlines() if line and not line.startswith("#")]
    assert body(content)[:len(body(release))] == body(release)


# --- artifacts and digests ------------------------------------------------------------------

def producers(workflow: dict) -> dict:
    """artifact name -> {job names that upload it}."""
    result = {}
    for job_name, job in workflow["jobs"].items():
        for step in steps(job):
            if uses(step) == "actions/upload-artifact":
                for name in expand(step["with"]["name"]):
                    result.setdefault(name, set()).add(job_name)
    return result


def test_artifacts_are_downloaded_by_exact_name_and_checked_against_their_producers_digest():
    workflow = load(R2_FILE)
    made = producers(workflow)
    checked = 0
    for job_name, job in workflow["jobs"].items():
        items = steps(job)
        for index, step in enumerate(items):
            if uses(step) != "actions/download-artifact":
                continue
            options = step["with"]
            assert set(options) == {"name", "path"}, (job_name, options)  # no pattern, no merge-multiple
            names = expand(options["name"])
            folders = expand(options["path"])
            assert folders == {"$RUNNER_TEMP/" + name for name in names}, job_name
            sources = set().union(*(made[name] for name in names))
            assert sources <= set(needs(job)), (job_name, sources)
            # a later step checks exactly this folder against an env value naming every producer's output
            found = False
            for later in items[index + 1:]:
                for command in commands(later):
                    if command[1:3] != ["godot-client/tools/desktop_release_ci.py", "artifact-digest"]:
                        continue
                    if run_dir(command[command.index("--dir") + 1]) != folders:
                        continue
                    variable = command[command.index("--expect") + 1]
                    assert variable.startswith("$"), job_name
                    value = later["env"][variable[1:]]
                    assert {job for job, _ in references(value)} == sources, (job_name, value)
                    for producer, output in references(value):
                        assert output in workflow["jobs"][producer]["outputs"], (producer, output)
                    assert later.get("if", "") == step.get("if", ""), job_name
                    found = True
            assert found, (job_name, options["name"])
            checked += 1
    assert checked == 24  # finalize also checks installers-windows (Q18)


def test_every_consumed_artifact_exports_its_digest_from_the_producing_job():
    workflow = load(R2_FILE)
    consumed = set()
    for job in workflow["jobs"].values():
        for step in steps(job):
            if uses(step) == "actions/download-artifact":
                consumed |= expand(step["with"]["name"])
    for job_name, job in workflow["jobs"].items():
        items = steps(job)
        for index, step in enumerate(items):
            if uses(step) != "actions/upload-artifact" or not expand(step["with"]["name"]) & consumed:
                continue
            assert step["with"]["if-no-files-found"] == "error" and step.get("if") is None, job_name
            digest = next(item for item in items[:index] if item.get("id") == "digest")
            (command,) = commands(digest)
            assert run_dir(command[command.index("--dir") + 1]) == expand(step["with"]["path"]), job_name
            name = command[command.index("--output-name") + 1]
            if "matrix" in job.get("strategy", {}):
                assert name == "${PLATFORM}_digest" and digest["env"]["PLATFORM"] == "${{ matrix.platform }}"
                assert {key: value for key, value in job["outputs"].items() if key.endswith("_digest")} == {
                    f"{p}_digest": f"${{{{ steps.digest.outputs.{p}_digest }}}}" for p in PLATFORMS}, job_name
            else:
                assert name == "digest" and job["outputs"]["digest"] == "${{ steps.digest.outputs.digest }}"


def test_needs_outputs_and_step_outputs_refer_to_declared_values():
    for name in NEW_FILES:
        workflow = load(name)
        for job_name, job in workflow["jobs"].items():
            ids = {step.get("id") for step in steps(job)}
            for value in every_string(job):
                for producer, output in references(value):
                    assert producer in needs(job), (job_name, producer)
                    if output != "result":
                        assert output in workflow["jobs"][producer].get("outputs", {}), (job_name, producer, output)
                for step_id, _ in references(value, "steps"):
                    assert step_id in ids, (job_name, step_id)


# --- the job graph and dry run ----------------------------------------------------------------

def test_release_job_graph_and_dry_run():
    workflow = jobs(R2_FILE)
    assert needs(workflow["content"]) == ["prepare"] and needs(workflow["content-ci"]) == ["prepare"]
    assert workflow["content"]["if"] == "needs.prepare.outputs.r2_any == 'true'"
    assert workflow["content-ci"]["if"] == "needs.prepare.outputs.ci_any == 'true'"
    assert workflow["prepare"]["if"] == "github.repository == 'rabbitlandsgame/rabbitlands-client'"
    order = {"build": {"prepare", "content", "content-ci"}, "sign": {"prepare", "content", "content-ci", "build"},
             "installers": {"prepare", "build", "sign"}, "stage": {"prepare", "build", "sign", "installers"},
             "e2e": {"prepare", "build", "sign", "installers", "stage"},
             "finalize": {"prepare", "content", "content-ci", "sign", "installers", "stage", "e2e"},
             "publish": {"prepare", "sign", "finalize"}, "promote": {"prepare", "finalize", "publish"}}
    for job_name, required in order.items():
        job = workflow[job_name]
        assert set(needs(job)) == required, job_name
        condition = job["if"]
        assert condition.startswith("${{ !cancelled() && needs.prepare.result == 'success'"), job_name
        assert condition.endswith("}}"), job_name
        for dependency in required - {"prepare"}:
            assert f"needs.{dependency}.result" in condition, (job_name, dependency)
        # jobs that hold a key, touch release state or run the shipped binaries skip in a dry run
        if job_name not in ("build", "installers"):
            assert "needs.prepare.outputs.dry_run == 'false'" in condition, job_name
    assert "dry_run == 'true' && needs.sign.result == 'skipped'" in workflow["installers"]["if"]
    # in a dry run the installers job neither fetches nor checks the (absent) envelopes
    envelope_steps = [step for step in steps(workflow["installers"])
                      if any("envelopes" in value and "--envelopes" not in value for value in every_string(step))]
    assert len(envelope_steps) == 2
    assert all(step["if"] == "needs.prepare.outputs.dry_run == 'false'" for step in envelope_steps)
    (build_step,) = [step for step in runs(workflow["installers"]) if "r2-installers" in step["run"]]
    assert build_step["env"]["DRY_RUN"] == "${{ needs.prepare.outputs.dry_run }}"


def test_matrix_legs_come_from_validated_prepare_outputs():
    workflow = jobs(R2_FILE)
    assert workflow["content"]["strategy"]["matrix"] == "${{ fromJSON(needs.prepare.outputs.r2_matrix) }}"
    assert workflow["content-ci"]["strategy"]["matrix"] == "${{ fromJSON(needs.prepare.outputs.ci_matrix) }}"
    # Executables and installers run for every platform with a source: both, except in a dry
    # run of Linux only (windows_source none, actions_release.r2_inputs). e2e runs only in a
    # real release, which always has both.
    for job_name in ("build", "installers"):
        assert workflow[job_name]["strategy"]["matrix"] == "${{ fromJSON(needs.prepare.outputs.build_matrix) }}"
        assert workflow[job_name]["strategy"]["fail-fast"] is False
    assert workflow["e2e"]["strategy"]["matrix"]["include"] == [
        {"platform": "windows", "runner": "windows-2025"}, {"platform": "linux", "runner": "ubuntu-24.04"}]
    assert workflow["e2e"]["strategy"]["fail-fast"] is False
    for job_name in ("sign", "stage", "e2e"):
        assert "needs.prepare.outputs.dry_run == 'false'" in workflow[job_name]["if"], job_name


def test_windows_source_offers_none_for_a_linux_only_dry_run():
    inputs = triggers(load(R2_FILE))["workflow_dispatch"]["inputs"]
    assert inputs["windows_source"]["default"] == "r2"
    none = {"WINDOWS_SOURCE": "none", "WINDOWS_SET_SHA256": "", "LINUX_SOURCE": "ci", "LINUX_SET_SHA256": ""}
    assert actions_release.r2_inputs({**none, "DRY_RUN": "true"})["platforms"]["windows"]["source"] == "none"
    with pytest.raises(ValueError):
        actions_release.r2_inputs({**none, "DRY_RUN": "false"})


def test_shared_concurrency_group():
    for name in DESKTOP_FILES:
        assert load(name)["concurrency"] == {"group": "rabbitlands-desktop-release", "cancel-in-progress": False}, name


# --- tool commands --------------------------------------------------------------------------

@pytest.mark.parametrize("name", [R2_FILE, REPOINT_FILE, OLD_FILE])
def test_every_tool_command_exists_with_its_flags(name):
    for job_name, job in load(name)["jobs"].items():
        for step in runs(job):
            for command in commands(step):
                tool = command[1].rsplit("/", 1)[1]
                if tool not in TOOL_PARSERS:
                    # the old workflow keeps its legacy finalize/publish tools; the new ones call only these two
                    assert name == OLD_FILE and tool in ("finalize_runner_release.py", "publish_runner_release.py")
                    continue
                sub = command[2]
                choices = subcommands(TOOL_PARSERS[tool])
                if sub not in choices:
                    assert PENDING_CI_COMMANDS.get(sub) == job_name and tool == "desktop_release_ci.py", sub
                    continue
                parser = choices[sub]
                flags = [word for word in command[3:] if word.startswith("--")]
                known = parser._option_string_actions
                assert set(flags) <= set(known), (job_name, sub, set(flags) - set(known))
                required = {action.option_strings[0] for action in parser._actions
                            if action.required and action.option_strings}
                assert required <= set(flags), (job_name, sub, required - set(flags))
                # every value is a literal or one quoted shell variable expansion, never an expression
                for word in command[3:]:
                    assert "${{" not in word and ("$" not in word or re.fullmatch(
                        r"(?:[A-Za-z0-9_./=-]*\$\{?[A-Z_]+\}?[A-Za-z0-9_./-]*)+", word)), word


def test_ci_leg_command_exists_so_prepare_accepts_ci_sources():
    assert actions_release.CI_CONTENT_COMMAND == "build-content"
    assert {"build-content", "content-cache-key"} <= set(subcommands(desktop_release_ci.build_parser()))
    assert actions_release.CI_CONTENT_COMMAND in actions_release.ci_tool_commands()
    assert not PENDING_CI_COMMANDS


# --- the ci content leg (R2-A6b) ------------------------------------------------------------

def _build_content_step(job: dict) -> dict:
    (step,) = [step for step in runs(job) for command in commands(step) if command[2] == "build-content"]
    return step


def test_ci_leg_writes_only_through_build_content_and_never_sees_the_key():
    workflow = jobs(R2_FILE)
    job = workflow["content-ci"]
    tokened = [step for step in steps(job)
               if any("github.token" in value or "GH_TOKEN" in value for value in every_string(step))]
    step = _build_content_step(job)
    assert tokened == [step]  # pip, apt, rustup, the cache keys, caches, digests and logs hold no token
    assert step["env"] == {"GH_TOKEN": "${{ github.token }}", "PLATFORM": "${{ matrix.platform }}",
                           "RELEASE_ID": "${{ needs.prepare.outputs.release_id }}",
                           "DRY_RUN": "${{ needs.prepare.outputs.dry_run }}"}
    assert [command[1:3] for command in commands(step)] == [["godot-client/tools/desktop_release_ci.py",
                                                            "build-content"]]
    (command,) = commands(step)
    assert command[command.index("--dry-run") + 1] == "$DRY_RUN"
    assert command[command.index("--commit") + 1] == "$GITHUB_SHA"
    assert not any("secrets." in value or KEY in value for value in every_string(job))
    assert job["permissions"] == {"contents": "write"} and "environment" not in job
    # the r2 content leg verifies anonymously: no token at all
    assert workflow["content"]["permissions"] == {"contents": "read"}
    assert not any("GH_TOKEN" in value for value in every_string(workflow["content"]))


def test_ci_leg_caches_use_exact_keys_and_the_tools_layout():
    job = jobs(R2_FILE)["content-ci"]
    items = steps(job)
    index = {id(step): position for position, step in enumerate(items)}
    caches = [step for step in items if uses(step).startswith("actions/cache")]
    assert {uses(step) for step in caches} == {"actions/cache/restore", "actions/cache/save"}
    (key_step,) = [step for step in items if step.get("id") == "cache-key"]
    (command,) = commands(key_step)
    assert command[1:3] == ["godot-client/tools/desktop_release_ci.py", "content-cache-key"]
    assert "GH_TOKEN" not in key_step.get("env", {})
    restores = {step["id"]: step for step in caches if uses(step) == "actions/cache/restore"}
    saves = [step for step in caches if uses(step) == "actions/cache/save"]
    assert set(restores) == {"asset-cache", "world-cache"} and len(saves) == 2
    names = set()
    for step in caches:
        # exactly a path and a key: no restore-keys, lookup-only, fail-on-cache-miss or cross-OS archive
        assert set(step["with"]) == {"path", "key"}, step.get("name")
        assert step["continue-on-error"] is True  # a cache outage is a cold build, never a failure
        match = re.fullmatch(r"\$\{\{ steps\.cache-key\.outputs\.([a-z_]+) \}\}", step["with"]["key"])
        assert match, step["with"]["key"]
        names.add(match[1])
    # the keys are the tool's outputs, computed for real on this checkout's commit
    head = desktop_release_ci.git_runner(REPO)("rev-parse", "HEAD").strip()
    keys = desktop_release_ci.content_cache_keys(desktop_release_ci.git_runner(REPO), head, "linux")
    assert names == set(keys) == {"asset_key", "world_key"}
    for value in keys.values():
        assert value.startswith(desktop_release_ci.CONTENT_CACHE_PREFIX) and "*" not in value
    # each save writes exactly what its restore read, and only after a miss
    pairs = {(step["with"]["path"], step["with"]["key"]) for step in restores.values()}
    assert {(step["with"]["path"], step["with"]["key"]) for step in saves} == pairs
    for step in saves:
        (restore,) = [item for item in restores.values() if item["with"]["key"] == step["with"]["key"]]
        assert step["if"] == f"steps.{restore['id']}.outputs.cache-hit != 'true'"
    # the folders are the ones build-content uses under its --cache root
    build = _build_content_step(job)
    (command,) = commands(build)
    root = Path(command[command.index("--cache") + 1])
    for name, step_id in (("assets", "asset-cache"), ("world", "world-cache")):
        assert expand(restores[step_id]["with"]["path"]) == {
            desktop_release_ci.content_cache_dirs(root, platform)[name].as_posix() for platform in PLATFORMS}
    # order: keys, restores, the build, then the saves
    assert index[id(key_step)] < min(index[id(step)] for step in restores.values())
    assert max(index[id(step)] for step in restores.values()) < index[id(build)]
    assert index[id(build)] < min(index[id(step)] for step in saves)


@pytest.mark.parametrize("windows, linux, error", [
    (("r2", "a" * 64), ("ci", ""), None),
    (("ci", ""), ("r2", "b" * 64), None),
    (("ci", ""), ("ci", ""), None),
    (("r2", "a" * 64), ("r2", "b" * 64), None),
    (("ci", "a" * 64), ("r2", "b" * 64), "windows_set_sha256 must be empty"),
    (("r2", "a" * 64), ("ci", "b" * 64), "linux_set_sha256 must be empty"),
    (("r2", ""), ("ci", ""), "windows_set_sha256 must be the 64"),
    (("ci", ""), ("r2", "B" * 64), "linux_set_sha256 must be the 64"),
    (("r2", "a" * 64), ("r2", "a" * 64), "cannot be the same object"),
    (("R2", "a" * 64), ("ci", ""), "windows_source must be r2 or ci"),
])
def test_mixed_sources_are_validated_per_platform(windows, linux, error):
    env = {"WINDOWS_SOURCE": windows[0], "WINDOWS_SET_SHA256": windows[1], "LINUX_SOURCE": linux[0],
           "LINUX_SET_SHA256": linux[1], "DRY_RUN": "false"}
    if error:
        with pytest.raises(ValueError, match=error):
            actions_release.r2_inputs(env)
        return
    value = actions_release.r2_inputs(env)["platforms"]
    assert value == {"windows": {"source": windows[0], "set_sha256": windows[1]},
                     "linux": {"source": linux[0], "set_sha256": linux[1]}}


def test_each_platforms_source_and_set_reach_sign_from_prepare_and_content_from_either_leg():
    workflow = jobs(R2_FILE)
    step = next(step for step in runs(workflow["sign"]) if KEY in step.get("env", {}))
    for platform in PLATFORMS:
        for name in ("source", "set_sha256"):
            assert step["env"][f"{platform.upper()}_{name.upper()}"] == (
                f"${{{{ needs.prepare.outputs.{platform}_{name} }}}}")
        (command,) = commands(step)
        assert command[command.index(f"--{platform}-set-sha256") + 1] == f"${platform.upper()}_SET_SHA256"
    # a platform's content artifact comes from whichever leg ran for it (the other leg skipped)
    for job_name in ("build", "sign", "finalize"):
        values = [value for value in every_string(workflow[job_name]) if "content.outputs" in value]
        assert values and all("content-ci.outputs" in value for value in values), job_name


# --- the old workflow ---------------------------------------------------------------------

def test_old_workflow_has_no_push_trigger_and_a_first_live_pointer_guard():
    workflow = load(OLD_FILE)
    assert triggers(workflow) == {"workflow_dispatch": None}
    guard = workflow["jobs"]["r2-guard"]
    assert guard["permissions"] == {"contents": "read"} and "needs" not in guard
    assert [command for step in runs(guard) for command in commands(step)] == [
        ["python", "godot-client/tools/actions_release.py", "live-pointer-guard"]]
    assert not any("secrets." in value or "GH_TOKEN" in value for value in every_string(guard))

    def closure(job_name):
        found, todo = set(), list(needs(workflow["jobs"][job_name]))
        while todo:
            item = todo.pop()
            if item not in found:
                found.add(item)
                todo.extend(needs(workflow["jobs"][item]))
        return found
    for job_name in workflow["jobs"]:
        if job_name != "r2-guard":
            assert "r2-guard" in closure(job_name), job_name
    assert set(workflow["jobs"]) == {"r2-guard", "prepare", "build", "finalize", "publish"}


def test_committed_files_hold_no_machine_or_scratch_paths():
    files = [WORKFLOWS / name for name in (R2_FILE, REPOINT_FILE, OLD_FILE)] + [
        TOOLS / "actions_release.py", TOOLS / "desktop-release-requirements.txt",
        TOOLS / "desktop-sign-requirements.txt", TOOLS / "desktop-content-requirements.txt"]
    for path in files:
        data = path.read_bytes()
        assert data.isascii() and b"\r" not in data, path.name
        for needle in (b"C:/", b"C:" + bytes([92]), b"AppData", b"scratchpad", b"/Users/", b"worktrees/",
                       b"secrets/", b"r2-upload"):
            assert needle not in data, (path.name, needle)


# --- R2-A7 contract ---------------------------------------------------------------------------

def test_r2_a7_entry_points_take_the_keywords_the_workflow_passes():
    import prune_published_release
    if getattr(prune_published_release, "RETENTION_SCHEMA", 1) < actions_release.MIN_RETENTION_SCHEMA:
        pytest.skip("R2-A7 (whole-release retention and the R2 publication entry points) is not in this tree yet")
    keywords = {"finalize": {"commit", "release_id", "envelopes", "content", "e2e", "installers", "out"},
                "publish": {"commit", "release_id", "receipt", "pointers"},
                "promote": {"commit", "release_id", "receipt"}}
    for step, names in keywords.items():
        signature = inspect.signature(actions_release.r2_a7(step))
        assert names <= set(signature.parameters), step


# --- UD-09: the helper template ---------------------------------------------------------------

HELPER_TEMPLATE_FILES = ("godot-client/tools/helper_template.json", "godot-client/tools/helper_template.py",
                         "godot-client/tools/helper_template_classes.json")


def _covered(relative: str, patterns: list[str] | None) -> bool:
    """Whether a sparse checkout with `patterns` (folders or files) contains `relative`;
    a checkout without sparse patterns contains everything."""
    if patterns is None:
        return True
    for pattern in patterns:
        folder = pattern.strip("/")
        if pattern.endswith("/") or (REPO / folder).is_dir():
            if relative.startswith(folder + "/"):
                return True
        elif relative == folder:
            return True
    return False


def test_the_executables_jobs_check_out_the_helper_template_pin_and_no_step_builds_or_caches_it():
    """The build job's tools read tools/helper_template.json and fetch the pinned template
    themselves (desktop_release_ci.executables, export_into): the workflows need no step, input,
    cache or artifact for it, so this chunk changes no workflow line."""
    for relative in HELPER_TEMPLATE_FILES:
        assert (REPO / relative).is_file(), relative

    def sparse(step: dict) -> list[str] | None:
        patterns = step.get("with", {}).get("sparse-checkout")
        return patterns.split() if patterns else None
    # Found by `uses`, not by position: Windows-capable jobs may run a line-ending step before the checkout.
    checkouts = [step for step in steps(jobs(R2_FILE)["build"]) if uses(step) == "actions/checkout"]
    assert len(checkouts) == 1
    for relative in HELPER_TEMPLATE_FILES:
        assert _covered(relative, sparse(checkouts[0])), relative
    for job in load(OLD_FILE)["jobs"].values():
        for step in steps(job):
            if uses(step) == "actions/checkout":
                assert all(_covered(relative, sparse(step)) for relative in HELPER_TEMPLATE_FILES)
    for name in DESKTOP_FILES:
        raw = text(name)
        assert "helper_template" not in raw and "helper-template" not in raw, name
