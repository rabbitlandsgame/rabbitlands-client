"""Actions glue for the desktop release workflows.

desktop-release.yml (the full-CI workflow, dispatch-only while R2 delivery starts):
  prepare, cache-key, build      draft, cache keys, the full hosted build
  live-pointer-guard             refuse once an R2 live pointer exists

desktop-release-r2.yml (content from the owner's machine on R2, executables here):
  r2-prepare      dispatch context, input validation, the retention guard, the draft
  r2-build        pinned tools, then desktop_release_ci.py executables
  r2-installers   pinned tools, then desktop_release_ci.py installers (tools only in a dry run)
  r2-e2e          desktop_release_ci.py e2e with the signed manifest and installer of sign.json
  r2-finalize     finalize_runner_release.finalize_r2 (R2-A7)
  r2-publish      checks this run's forward pointers, then publish_runner_release.publish_r2 (R2-A7)
  r2-promote      publish_runner_release.promote_r2 (R2-A7)
  disk-probe      free space of the runner's volumes, for the dry run and e2e

desktop-repoint.yml (deliberate rollback to a retained, published, schema-3 release):
  repoint-check   the target release and every download it names, before any write
  repoint-latest  GitHub latest first
  repoint-upload  the signed rollback pointers, as the target release's pointer assets

Every input arrives through the environment or an argument and is validated
here; the signing key is never read by this module outside `build`.
"""
from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
import importlib
import json
import os
from pathlib import Path
import re
import shutil
import sys
import tempfile
import time
from types import SimpleNamespace

import build_release as release
import package_client as package
import runner_release
import setup_runner_tools
import shared_release_assets
import release_asset_cache
import release_native_runtime
import runner_retirement

SECRET = "CLIENT_UPDATE_SIGNING_KEY"


def workflow_commit() -> str:
    if (os.environ.get("GITHUB_ACTIONS") != "true"
            or os.environ.get("GITHUB_REPOSITORY") != release.REPOSITORY
            or os.environ.get("GITHUB_REF") not in ("refs/heads/master", "refs/heads/develop")
            or os.environ.get("GITHUB_EVENT_NAME") not in ("push", "workflow_dispatch")):
        raise ValueError("Release automation must run in this repository on master or develop.")
    if os.environ["GITHUB_EVENT_NAME"] == "push" and os.environ["GITHUB_REF"] != "refs/heads/master":
        raise ValueError("Automatic release builds run only on master.")
    sha = os.environ.get("GITHUB_SHA", "")
    if not re.fullmatch(r"[0-9a-f]{40}", sha) or package.git("rev-parse", "HEAD").strip() != sha:
        raise ValueError("The checkout must match the workflow's exact source commit.")
    runner_release.exact_checkout(package.REPO)
    return sha


def prepare() -> tuple[str, int]:
    sha = workflow_commit()
    if os.environ.get("SIGNING_KEY_AVAILABLE") != "true":
        raise ValueError(f"Configure the repository Actions secret {SECRET} before running a release.")
    runner_release.authorize()
    entries = [item for item in release.github_releases()
               if re.fullmatch(r"client-[0-9a-f]{40}", item["tag_name"])]
    if any(item["tag_name"] == f"client-{sha}" and not item["draft"] for item in entries):
        raise ValueError("This commit already has a published release. Build a newer commit, or return that release to draft before rebuilding it.")
    drafts = [item for item in entries if item["draft"]]
    if len(drafts) > 1:
        raise ValueError("More than one client draft exists; choose one before starting automation.")
    if drafts:
        draft = drafts[0]
    else:
        tag = f"client-{sha}"
        release.gh("release", "create", tag, "--repo", release.REPOSITORY, "--draft", "--target", sha,
                   "--title", f"Rabbit Lands {sha[:9]}", "--notes", "Desktop builds are being prepared. This release remains a draft.")
        # A newly created draft can briefly be absent from the release listing.
        # Re-read the same tag; never create a second destination on a retry.
        draft = None
        for delay in (0, 1, 2, 4, 8):
            if delay:
                time.sleep(delay)
            draft = release.github_release(tag)
            if draft is not None:
                break
    if (not draft or not draft["draft"]
            or draft["author"]["login"] not in (release.ACCOUNT, "github-actions[bot]")):
        raise ValueError("The draft must belong to the Rabbit Lands account or this repository's workflow.")
    release_id = draft["id"]
    shared_release_assets.ensure(sha)
    with Path(os.environ["GITHUB_OUTPUT"]).open("a", encoding="utf-8") as output:
        output.write(f"commit={sha}\nrelease_id={release_id}\n")
    summary = os.environ.get("GITHUB_STEP_SUMMARY")
    if summary:
        with Path(summary).open("a", encoding="utf-8") as output:
            output.write(f"Building Windows and Linux from `{sha}` into draft release `{release_id}`.\n")
    return sha, release_id


def check_signing_key(key: bytes, public: bytes) -> None:
    from cryptography.hazmat.primitives import serialization
    from cryptography.hazmat.primitives.asymmetric import rsa
    try:
        private = serialization.load_pem_private_key(key, password=None)
        expected = serialization.load_pem_public_key(public)
    except (TypeError, ValueError) as error:
        raise ValueError(f"{SECRET} must contain the existing unencrypted RSA PEM key.") from error
    if (not isinstance(private, rsa.RSAPrivateKey)
            or not isinstance(expected, rsa.RSAPublicKey)
            or private.public_key().public_numbers() != expected.public_numbers()):
        raise ValueError("The Actions signing key does not match this commit's public update key.")


def build(platform: str, release_id: int) -> Path:
    sha = workflow_commit()
    # Remove the secret from the environment before starting installers or Godot.
    key = os.environ.pop(SECRET, "").encode("ascii")
    public = package.git("show", f"{sha}:godot-client/data/update_public.pem").encode("ascii")
    check_signing_key(key, public)
    temp = Path(os.environ["RUNNER_TEMP"]).resolve()
    tool_root = temp / "rabbitlands-toolchain"
    native_tool_root = temp / "rabbitlands-native-toolchain"
    if not native_tool_root.is_dir():
        raise ValueError("Install the pinned native toolchain in the job's accounted native-toolchain directory first.")
    runner_retirement.claim_native_sdk(native_tool_root, temp, sha, platform)
    config = setup_runner_tools.install(platform, tool_root)
    previous = {name: os.environ.get(name) for name in config["env"]}
    try:
        os.environ.update(config["env"])
        with tempfile.TemporaryDirectory(prefix="rabbitlands-signing-", dir=temp) as private:
            key_path = Path(private) / "signing.pem"
            with key_path.open("xb") as output:
                os.chmod(key_path, 0o600)
                output.write(key)
            return runner_release.build(SimpleNamespace(platform=platform, ref=sha,
                out=temp / "rabbitlands-releases", godot=config["godot"], iscc=config.get("iscc"),
                update_signing_key=key_path, tool_root=[tool_root, native_tool_root], draft_release_id=release_id,
                native_cache=temp / "rabbitlands-native-cache" / platform, native_tool_root=native_tool_root,
                asset_cache=temp / "rabbitlands-asset-cache" / platform,
                server="game.rabbitlandsgame.com:2001"))
    finally:
        for name, value in previous.items():
            if value is None:
                os.environ.pop(name, None)
            else:
                os.environ[name] = value


# --- desktop-release.yml during the R2 transition ---------------------------------------------

def live_pointer_guard(http=None) -> None:
    """The old full-CI workflow's first job: pass only while neither R2 live pointer exists.

    An R2-aware client reads the pointer first, so a GitHub-only release made
    after the first pointer would move GitHub `latest` out of step with it.
    Anything but a 404 (a 200, a challenge, an outage) refuses: fail closed.
    """
    import desktop_r2 as r2
    import upload_desktop_assets as up
    http = http or up.Http()
    for platform in r2.PLATFORMS:
        try:
            response = http.request("GET", r2.pointer_url(platform), limit=r2.MAX_POINTER_BYTES, keep_body=False)
        except r2.DesktopR2Error as error:
            raise ValueError(f"Could not confirm that no R2 live pointer exists for {platform} ({error.code}); "
                             "this workflow refuses rather than risk a release R2-aware clients never see.") from None
        if response.status == 200:
            raise ValueError(f"The R2 live pointer for {platform} exists, so desktop releases are made with "
                             "desktop-release-r2.yml; this full-CI workflow would publish a GitHub-only release "
                             "that R2-aware clients never see.")
        if response.status != 404:
            raise ValueError(f"Could not confirm that no R2 live pointer exists for {platform} "
                             f"(HTTP {response.status}); this workflow refuses (fail closed).")


# --- desktop-release-r2.yml and desktop-repoint.yml --------------------------------------------

R2_WORKFLOW = ".github/workflows/desktop-release-r2.yml"
REPOINT_WORKFLOW = ".github/workflows/desktop-repoint.yml"
PLATFORMS = ("windows", "linux")
RUNNERS = {"windows": "windows-2025", "linux": "ubuntu-24.04"}
RELEASE_BRANCHES = ("refs/heads/master", "refs/heads/develop")
WORKFLOW_AUTHORS = (release.ACCOUNT, "github-actions[bot]")
MIN_RETENTION_SCHEMA = 2            # prune_published_release.RETENTION_SCHEMA of R2-A7
CI_CONTENT_COMMAND = "build-content"  # desktop_release_ci.py subcommand of the ci content leg (R2-A6b)
LINUX_E2E_WORK = Path("/mnt/rl-e2e/work")  # every parent must be traversable by the throwaway e2e user
REPOINT_PLATFORMS = {"both": PLATFORMS, "windows": ("windows",), "linux": ("linux",)}
# R2-A7 entry points, called with keyword arguments only (see each wrapper).
R2_A7 = {"finalize": ("finalize_runner_release", "finalize_r2"),
         "publish": ("publish_runner_release", "publish_r2"),
         "promote": ("publish_runner_release", "promote_r2")}
HEAD_WORKERS = 4
REPOINT_KIND = "rabbitlands-desktop-repoint"
_SOURCE = re.compile(r"(?:r2|ci)")
_SHA256 = re.compile(r"[0-9a-f]{64}")
_COMMIT = re.compile(r"[0-9a-f]{40}")
_RELEASE_ID = re.compile(r"[1-9][0-9]{0,15}")
_LABEL = re.compile(r"[a-z0-9-]{1,40}")
_OUTPUT_NAME = re.compile(r"[a-z0-9_]{1,64}")
_MANIFEST_NAME = re.compile(r"RabbitLands-(Windows|Linux)-[0-9]{8}-([0-9a-f]{9})-(windows|linux)\.json")
_CONFIRM_DELAYS = (0, 1, 2, 4, 8)


def _platform(value: str) -> str:
    if value not in PLATFORMS:
        raise ValueError("Unknown desktop platform.")
    return value


def _release_id(value) -> int:
    if not _RELEASE_ID.fullmatch(str(value)):
        raise ValueError("The draft release ID must be a positive integer from the prepare job.")
    return int(value)


def _runner_temp() -> Path:
    value = os.environ.get("RUNNER_TEMP")
    if not value:
        raise ValueError("RUNNER_TEMP is not set; this step runs only on a hosted runner.")
    return Path(value).resolve()


def _write_outputs(values: dict) -> None:
    path = os.environ.get("GITHUB_OUTPUT")
    if not path:
        raise ValueError("GITHUB_OUTPUT is not set.")
    lines = []
    for name, value in values.items():
        text = str(value)
        if not _OUTPUT_NAME.fullmatch(name) or any(char in text for char in "\r\n"):
            raise ValueError("Refusing an unsafe step output.")
        lines.append(f"{name}={text}\n")
    with Path(path).open("a", encoding="utf-8") as output:
        output.writelines(lines)


def _summary(text: str) -> None:
    path = os.environ.get("GITHUB_STEP_SUMMARY")
    if path:
        with Path(path).open("a", encoding="utf-8") as output:
            output.write(text)


def no_signing_key() -> None:
    """Only the signing steps of the desktop-sign/desktop-publish jobs may see the key."""
    if SECRET in os.environ:
        raise ValueError(f"{SECRET} must be visible only to the signing steps of the desktop-sign and "
                         "desktop-publish jobs.")


def dispatch_commit(workflow: str) -> str:
    """The dispatched commit of `workflow` (dispatch only, master or develop, exact checkout: the
    commit, with every checked-out file its committed bytes, runner_release.exact_checkout)."""
    ref = os.environ.get("GITHUB_REF")
    if (os.environ.get("GITHUB_ACTIONS") != "true"
            or os.environ.get("GITHUB_REPOSITORY") != release.REPOSITORY
            or ref not in RELEASE_BRANCHES
            or os.environ.get("GITHUB_EVENT_NAME") != "workflow_dispatch"):
        raise ValueError("This workflow runs only when dispatched in this repository on master or develop.")
    if os.environ.get("GITHUB_WORKFLOW_REF") != f"{release.REPOSITORY}/{workflow}@{ref}":
        raise ValueError(f"This step belongs to {workflow}; the running workflow file is another one.")
    sha = os.environ.get("GITHUB_SHA", "")
    if not _COMMIT.fullmatch(sha) or package.git("rev-parse", "HEAD").strip() != sha:
        raise ValueError("The checkout must match the workflow's exact source commit.")
    runner_release.exact_checkout(package.REPO)
    return sha


def r2_inputs(env=None) -> dict:
    """The dispatch inputs, as the prepare step receives them through `env:`.

    `none` leaves Windows out entirely, and only a dry run may do that: a dry run
    of Linux alone can start while the Windows content is still being built, so a
    CI failure shows early. A real release always has both platforms.

    `commit`, when given, is the full commit the dispatcher meant: the branch head
    can move between choosing it and dispatching, and prepare refuses the run
    before it writes anything (r2_prepare).
    """
    env = os.environ if env is None else env
    dry_run = env.get("DRY_RUN", "")
    if dry_run not in ("true", "false"):
        raise ValueError("dry_run must be true or false.")
    platforms = {}
    for platform in PLATFORMS:
        source = env.get(f"{platform.upper()}_SOURCE", "")
        digest = env.get(f"{platform.upper()}_SET_SHA256", "")
        if source == "none":
            if platform != "windows":
                raise ValueError(f"{platform}_source must be r2 or ci; only Windows can be left out of a dry run.")
            if dry_run != "true":
                raise ValueError(f"{platform}_source none is only for a dry run; a release needs both platforms.")
            if digest:
                raise ValueError(f"{platform}_set_sha256 must be empty for a none source.")
            platforms[platform] = {"source": source, "set_sha256": ""}
            continue
        if not _SOURCE.fullmatch(source):
            raise ValueError(f"{platform}_source must be r2 or ci (or none, in a dry run).")
        if source == "r2" and not _SHA256.fullmatch(digest):
            raise ValueError(f"{platform}_set_sha256 must be the 64 lowercase hex SHA-256 of the {platform} "
                             "content set on R2.")
        if source == "ci" and digest:
            raise ValueError(f"{platform}_set_sha256 must be empty for a ci source.")
        platforms[platform] = {"source": source, "set_sha256": digest}
    if all(item["source"] == "none" for item in platforms.values()):  # defensive: only Windows takes none today
        raise ValueError("At least one platform needs a content source.")
    commit = env.get("COMMIT", "")
    if commit and not _COMMIT.fullmatch(commit):
        raise ValueError("commit must be empty or a full 40-character lowercase commit.")
    hashes = [item["set_sha256"] for item in platforms.values() if item["source"] == "r2"]
    if len(set(hashes)) != len(hashes):
        raise ValueError("The Windows and Linux content sets cannot be the same object.")
    return {"platforms": platforms, "dry_run": dry_run == "true", "commit": commit}


def retention_guard() -> int:
    """Refuse unless this commit's prune keeps whole releases (R2-A7, RETENTION_SCHEMA >= 2)."""
    import prune_published_release
    schema = getattr(prune_published_release, "RETENTION_SCHEMA", None)
    if type(schema) is not int or schema < MIN_RETENTION_SCHEMA:
        raise ValueError("This commit's prune_published_release.py predates whole-release retention "
                         f"(RETENTION_SCHEMA >= {MIN_RETENTION_SCHEMA}); an R2-era promote would delete the "
                         "rollback releases and their helpers. Dispatch a commit that contains it.")
    return schema


def pinned_release_guard() -> str:
    """Refuse a release with r2 content unless this commit's prune pins the last GitHub-hosted release.

    Retention (design Q11) keeps latest, KEEP_PREVIOUS earlier releases and
    PINNED_GITHUB_HOSTED, normally T, set in the commit of the first R2 content
    release. With no pin the third r2 promote would retire T and every GitHub-hosted
    file only it references, silently. Prune itself refuses a pin that is not a
    published release, before it deletes anything.
    """
    import prune_published_release
    pinned = getattr(prune_published_release, "PINNED_GITHUB_HOSTED", None)
    if type(pinned) is not str or not shared_release_assets.CLIENT_TAG.fullmatch(pinned):
        raise ValueError("An r2 content source needs prune_published_release.PINNED_GITHUB_HOSTED set to the "
                         "client-<commit> tag of the last GitHub-hosted release (normally T) in this commit, "
                         "so retention keeps it; use ci sources or a commit that sets it.")
    return pinned


def _ci():
    import desktop_release_ci
    return desktop_release_ci


def ci_tool_commands() -> set[str]:
    for action in _ci().build_parser()._actions:
        if isinstance(action, argparse._SubParsersAction):
            return set(action.choices)
    return set()


def r2_draft(sha: str) -> int:
    """Find or create the draft `client-<sha>`; refuse any other client draft."""
    tag = f"client-{sha}"
    entries = [item for item in release.github_releases() if re.fullmatch(r"client-[0-9a-f]{40}", item["tag_name"])]
    if any(item["tag_name"] == tag and not item["draft"] for item in entries):
        raise ValueError("This commit already has a published release. Dispatch a newer commit.")
    drafts = [item for item in entries if item["draft"]]
    others = sorted(item["tag_name"] for item in drafts if item["tag_name"] != tag)
    if others:
        raise ValueError(f"Another client draft exists ({others[0]}); finish or delete it before this release.")
    if len(drafts) > 1:
        raise ValueError("More than one draft exists for this commit; keep one before starting automation.")
    if drafts:
        draft = drafts[0]
    else:
        release.gh("release", "create", tag, "--repo", release.REPOSITORY, "--draft", "--target", sha,
                   "--title", f"Rabbit Lands {sha[:9]}", "--notes",
                   "Desktop builds are being prepared. This release remains a draft.")
        draft = None
        for delay in _CONFIRM_DELAYS:
            if delay:
                time.sleep(delay)
            draft = release.github_release(tag)
            if draft is not None:
                break
    if (not draft or not draft["draft"] or draft.get("tag_name", tag) != tag
            or draft["author"]["login"] not in WORKFLOW_AUTHORS):
        raise ValueError("The draft must be this commit's and belong to the Rabbit Lands account or this workflow.")
    return draft["id"]


def r2_prepare() -> dict:
    """The first job of desktop-release-r2.yml: every refusal happens before any write."""
    sha = dispatch_commit(R2_WORKFLOW)
    no_signing_key()
    inputs = r2_inputs()
    if inputs["commit"] and inputs["commit"] != sha:
        raise ValueError(f"The run is at {sha}, but the dispatch asked for {inputs['commit']}: the branch moved on "
                         "between the two. Nothing was written; dispatch again from a branch at that commit.")
    retention_guard()
    platforms = inputs["platforms"]
    sources = {platform: item["source"] for platform, item in platforms.items()}
    if "ci" in sources.values() and CI_CONTENT_COMMAND not in ci_tool_commands():
        raise ValueError(f"A ci content source needs desktop_release_ci.py {CI_CONTENT_COMMAND} (R2-A6b), "
                         "which this commit lacks.")
    if "r2" in sources.values():
        # The r2 gate, open from W1a on: the commit's own updater must read derived
        # R2 rows (the exact W1a declarations, release_manifest.r2_source_problem).
        import release_manifest
        problem = release_manifest.r2_source_problem(release_manifest.commit_capabilities(package.REPO, sha))
        if problem:
            raise ValueError(f"An r2 content source needs this commit's R2-aware updater (W1a), but {problem}; "
                             "use ci sources or a later commit.")
        # A dry run publishes and prunes nothing, so it may exercise r2 legs before R1's commit.
        if not inputs["dry_run"]:
            pinned_release_guard()
    release_id = 0
    if not inputs["dry_run"]:
        runner_release.authorize()
        release_id = r2_draft(sha)
        shared_release_assets.ensure(sha)
    r2_rows = [{"platform": p, "set_sha256": platforms[p]["set_sha256"]} for p in PLATFORMS if sources[p] == "r2"]
    ci_rows = [{"platform": p, "runner": RUNNERS[p]} for p in PLATFORMS if sources[p] == "ci"]
    build_rows = [{"platform": p, "runner": RUNNERS[p]} for p in PLATFORMS if sources[p] != "none"]
    values = {"commit": sha, "release_id": release_id, "dry_run": str(inputs["dry_run"]).lower(),
              **{f"{p}_source": sources[p] for p in PLATFORMS},
              **{f"{p}_set_sha256": platforms[p]["set_sha256"] for p in PLATFORMS},
              "r2_any": str(bool(r2_rows)).lower(), "ci_any": str(bool(ci_rows)).lower(),
              "r2_matrix": json.dumps({"include": r2_rows}, separators=(",", ":"), sort_keys=True),
              "ci_matrix": json.dumps({"include": ci_rows}, separators=(",", ":"), sort_keys=True),
              "build_matrix": json.dumps({"include": build_rows}, separators=(",", ":"), sort_keys=True)}
    _write_outputs(values)
    rows = "".join(f"| {p} | {sources[p]} | `{platforms[p]['set_sha256'] or '-'}` |\n" for p in PLATFORMS)
    _summary(f"## Desktop release from `{sha}`\n\n"
             + ("Dry run: no draft, no signing, no uploads.\n\n" if inputs["dry_run"]
                else f"Draft release `{release_id}`.\n\n")
             + "| Platform | Content source | Content set SHA-256 |\n| --- | --- | --- |\n" + rows)
    return values


def tool_config(platform: str, *, installers: bool) -> dict:
    """The pinned editor and export template (and Inno on Windows) in this job's runner temp."""
    return setup_runner_tools.install(platform, _runner_temp() / "rabbitlands-toolchain", installers=installers)


@contextmanager
def tool_environment(config: dict):
    previous = {name: os.environ.get(name) for name in config["env"]}
    os.environ.update(config["env"])
    try:
        yield
    finally:
        for name, value in previous.items():
            if value is None:
                os.environ.pop(name, None)
            else:
                os.environ[name] = value


def r2_build(platform: str, content: Path, out: Path) -> int:
    sha = dispatch_commit(R2_WORKFLOW)
    no_signing_key()
    platform = _platform(platform)
    config = tool_config(platform, installers=False)
    with tool_environment(config):
        return _ci().main(["executables", "--platform", platform, "--commit", sha, "--godot", str(config["godot"]),
                           "--content", str(content), "--work", str(_runner_temp() / "exec-work"),
                           "--out", str(out)])


def sign_record(envelopes: Path, sha: str) -> dict:
    """sign.json of the envelopes artifact: both platforms of this commit, with plain manifest names."""
    envelopes = Path(envelopes)
    data = json.loads((envelopes / "sign.json").read_text(encoding="ascii"))
    platforms = data.get("platforms") if isinstance(data, dict) else None
    if (not isinstance(platforms, dict) or data.get("commit") != sha or set(platforms) != set(PLATFORMS)):
        raise ValueError("The envelopes artifact is not this run's signed release.")
    for platform, row in platforms.items():
        name = row.get("manifest") if isinstance(row, dict) else None
        match = _MANIFEST_NAME.fullmatch(name) if type(name) is str else None
        if (not match or match[1].lower() != platform or match[3] != platform or match[2] != sha[:9]
                or not _SHA256.fullmatch(str(row.get("sha256"))) or not (envelopes / name).is_file()):
            raise ValueError(f"The envelopes artifact names no valid {platform} manifest.")
    return platforms


def r2_installers(platform: str, envelopes: Path | None, exec_dir: Path, out: Path, dry_run: bool) -> int:
    sha = dispatch_commit(R2_WORKFLOW)
    no_signing_key()
    platform = _platform(platform)
    config = tool_config(platform, installers=platform == "windows")
    if dry_run:
        # No signed envelope exists in a dry run and desktop_release_ci.installers
        # verifies one first, so this proves the tool installs and measures the disk.
        out = Path(out)
        out.mkdir(parents=True, exist_ok=False)
        record = {"kind": "rabbitlands-desktop-dry-run-installers", "schema": 1, "platform": platform,
                  "commit": sha, "godot": Path(config["godot"]).is_file(),
                  "iscc": bool(config.get("iscc")) and Path(config["iscc"]).is_file(),
                  "setup": "skipped: a dry run has no signed envelope", "disk": disk_usage()}
        (out / "dry-run.json").write_text(json.dumps(record, sort_keys=True, indent=1) + "\n", encoding="ascii")
        _summary(f"\n{platform}: installer tools installed; the setup build needs a signed envelope (skipped).\n")
        return 0
    if envelopes is None:
        raise ValueError("Installers need the signed envelopes artifact.")
    manifest = Path(envelopes) / sign_record(envelopes, sha)[platform]["manifest"]
    argv = ["installers", "--platform", platform, "--commit", sha, "--envelope", str(manifest),
            "--exec", str(exec_dir), "--godot", str(config["godot"]),
            "--work", str(_runner_temp() / "installer-work"), "--out", str(out)]
    if config.get("iscc"):
        argv += ["--iscc", str(config["iscc"])]
    with tool_environment(config):
        return _ci().main(argv)


def r2_e2e(platform: str, envelopes: Path, exec_dir: Path, installers: Path, receipt: Path, logs: Path) -> int:
    sha = dispatch_commit(R2_WORKFLOW)
    no_signing_key()
    platform = _platform(platform)
    name = sign_record(envelopes, sha)[platform]["manifest"]
    version = name[:-len(f"-{platform}.json")]
    installer = Path(installers) / (f"{version}-setup.exe" if platform == "windows" else f"{version}-download.sh")
    if not installer.is_file():
        raise ValueError(f"The {platform} installers artifact lacks {installer.name}.")
    work = LINUX_E2E_WORK if platform == "linux" else _runner_temp() / "rl-e2e" / "work"
    try:
        return _ci().main(["e2e", "--platform", platform, "--envelope", str(Path(envelopes) / name),
                           "--exec", str(exec_dir), "--installer", str(installer), "--work", str(work),
                           "--receipt", str(receipt)])
    finally:
        if (work / "logs").is_dir():
            shutil.copytree(work / "logs", Path(logs), dirs_exist_ok=True)


def disk_usage() -> list[dict]:
    candidates = [os.environ[name] for name in ("RUNNER_TEMP", "GITHUB_WORKSPACE") if os.environ.get(name)]
    candidates += [f"{letter}:\\" for letter in "CDEF"] if os.name == "nt" else ["/mnt", "/"]
    rows = []
    for path in candidates:
        if os.path.isdir(path):
            usage = shutil.disk_usage(path)
            rows.append({"path": path, "free": usage.free, "total": usage.total})
    return rows


def disk_probe(label: str) -> list[dict]:
    if not _LABEL.fullmatch(label):
        raise ValueError("The disk probe label must be short lowercase text.")
    rows = disk_usage()
    _summary(f"\n### Disk: {label}\n\n| Path | Free GiB | Total GiB |\n| --- | --- | --- |\n"
             + "".join(f"| `{row['path']}` | {row['free'] / 1024 ** 3:.1f} | {row['total'] / 1024 ** 3:.1f} |\n"
                       for row in rows))
    print(json.dumps({"label": label, "volumes": rows}, sort_keys=True))
    return rows


def r2_a7(step: str):
    """An R2-A7 entry point of this commit, or a refusal that names it."""
    module_name, function = R2_A7[step]
    target = getattr(importlib.import_module(module_name), function, None)
    if not callable(target):
        raise ValueError(f"{module_name}.{function} (R2-A7) is missing at this commit; it cannot {step} an R2 "
                         "release.")
    return target


def r2_finalize(release_id, envelopes: Path, content: dict, e2e: dict, windows_installers: Path, out: Path):
    """Finalize the draft; setup.exe is bound to the bytes of the installers-windows artifact (Q18)."""
    sha = dispatch_commit(R2_WORKFLOW)
    no_signing_key()
    retention_guard()
    release_id = _release_id(release_id)
    sign_record(envelopes, sha)
    return r2_a7("finalize")(commit=sha, release_id=release_id, envelopes=Path(envelopes),
                             content={p: Path(content[p]) for p in PLATFORMS},
                             e2e={p: Path(e2e[p]) for p in PLATFORMS},
                             installers={"windows": Path(windows_installers)}, out=Path(out))


def check_forward_pointers(sha: str, release_id: int, envelopes: Path, pointers: Path) -> dict:
    """This run's two pointers: forward, for this draft, each naming its signed manifest."""
    import desktop_r2 as r2
    import release_manifest as rm
    import upload_desktop_assets as up
    public_pem = rm.commit_public_key(package.REPO, sha)
    signed = sign_record(envelopes, sha)
    pointers = Path(pointers)
    if sorted(path.name for path in pointers.iterdir()) != sorted(r2.pointer_asset_name(p) for p in PLATFORMS):
        raise ValueError("The pointer folder must hold exactly the two platform pointers.")
    checked = {}
    for platform in PLATFORMS:
        manifest = (Path(envelopes) / signed[platform]["manifest"]).read_bytes()
        if r2.sha256_hex(manifest) != signed[platform]["sha256"]:
            raise ValueError(f"The {platform} manifest differs from the one signed in this run.")
        checked[platform] = up.check_release_pair(
            (pointers / r2.pointer_asset_name(platform)).read_bytes(), lambda _p, _v, data=manifest: data,
            platform=platform, public_pem=public_pem, commit=sha, release_id=release_id, rollback=False)
    return checked


def r2_publish(release_id, envelopes: Path, pointers: Path, receipt: Path):
    """Publish the verified draft as not latest, with its signed pointers (R2-A7 does the writes)."""
    sha = dispatch_commit(R2_WORKFLOW)
    no_signing_key()
    retention_guard()
    release_id = _release_id(release_id)
    check_forward_pointers(sha, release_id, envelopes, pointers)
    result = r2_a7("publish")(commit=sha, release_id=release_id, receipt=Path(receipt), pointers=Path(pointers))
    _summary(f"\nPublished `client-{sha}` as **not latest** with signed pointers. On the build machine, put both "
             "pointers live on R2, then approve `desktop-promote`:\n\n```\n"
             f"python godot-client/tools/upload_desktop_assets.py publish --release client-{sha} "
             "--platform windows --platform linux --credentials <private R2 credential file> "
             "--receipt <private publish receipt>\n```\n")
    return result


def r2_promote(release_id, receipt: Path):
    """GitHub latest after both live R2 pointers name this release (R2-A7 does the checks and writes)."""
    sha = dispatch_commit(R2_WORKFLOW)
    no_signing_key()
    retention_guard()
    release_id = _release_id(release_id)
    result = r2_a7("promote")(commit=sha, release_id=release_id, receipt=Path(receipt))
    _summary("\nGitHub latest now names this release. Before changing the server's required commit, run:\n\n```\n"
             "python godot-client/tools/upload_desktop_assets.py check-policy --policy <client_updates.json>\n```\n")
    return result


def repoint_inputs(env=None) -> tuple[str, tuple]:
    env = os.environ if env is None else env
    target = env.get("TARGET_COMMIT", "")
    if not _COMMIT.fullmatch(target):
        raise ValueError("target_commit must be a full 40-character lowercase commit ID.")
    choice = env.get("REPOINT_PLATFORMS", "")
    if choice not in REPOINT_PLATFORMS:
        raise ValueError("platforms must be both, windows or linux.")
    return target, REPOINT_PLATFORMS[choice]


def tag_commit(tag: str) -> str | None:
    """The commit a release tag names, through annotated tags; None when absent."""
    refs = json.loads(release.gh("api", f"repos/{release.REPOSITORY}/git/matching-refs/tags/{tag}"))
    for ref in refs:
        if ref.get("ref") == "refs/tags/" + tag:
            obj = ref["object"]
            for _ in range(16):
                if obj["type"] != "tag":
                    break
                obj = json.loads(release.gh("api", f"repos/{release.REPOSITORY}/git/tags/{obj['sha']}"))["object"]
            return obj["sha"] if obj["type"] == "commit" else None
    return None


def manifest_rows(manifest: dict) -> list[dict]:
    """Every download a signed manifest names (parts of all packages and both helpers), once each."""
    rows = {}
    for group in ("packages", "optional_packages"):
        for item in manifest.get(group) or []:
            for part in item["parts"]:
                rows[part["url"]] = part
    for kind in ("updater", "uninstall"):
        if kind in manifest:
            rows[manifest[kind]["url"]] = manifest[kind]
    return list(rows.values())


def missing_downloads(http, manifest: dict) -> list[str]:
    """Anonymous HEADs (200 and exact length) of every row; R2 and GitHub alike."""
    ci = _ci()
    rows = manifest_rows(manifest)
    with ThreadPoolExecutor(HEAD_WORKERS) as pool:
        present = list(pool.map(lambda row: ci.head_ok(http, row["url"], row["size"]), rows))
    return [row["url"] for row, ok in zip(rows, present) if not ok]


def repoint_check(out: Path, *, http=None) -> dict:
    """The rollback target: a published release of this account whose tag names it, signed
    schema-3 manifests the dispatched commit's key verifies, and every download present."""
    import desktop_r2 as r2
    import release_manifest as rm
    import upload_desktop_assets as up
    sha = dispatch_commit(REPOINT_WORKFLOW)
    no_signing_key()
    target, platforms = repoint_inputs()
    http = http or _ci().Fetcher()
    out = Path(out)
    if out.exists() and any(out.iterdir()):
        raise ValueError("The repoint folder must start empty.")
    out.mkdir(parents=True, exist_ok=True)
    tag = f"client-{target}"
    public = up.GitHubRelease(http)
    record = public.release(tag)  # anonymous: published, not a draft, not a prerelease
    if (record.get("author") or {}).get("login") not in WORKFLOW_AUTHORS:
        raise ValueError(f"{tag} does not belong to the Rabbit Lands account or its workflow.")
    if tag_commit(tag) != target:
        raise ValueError(f"The tag {tag} does not point at {target}.")
    public_pem = rm.commit_public_key(package.REPO, sha)
    manifests = {}
    for platform in platforms:
        data = public.asset(record, f"RabbitLands-{platform}.json", r2.MAX_ENVELOPE_BYTES)
        _, manifest = rm.verify(data, public_pem, limit=r2.MAX_ENVELOPE_BYTES)
        if (manifest.get("commit") != target or manifest.get("platform") != platform
                or manifest.get("repository") != r2.REPOSITORY):
            raise ValueError(f"The {platform} manifest of {tag} is not that release's.")
        if manifest.get("schema") != 3:
            raise ValueError(f"The {platform} manifest of {tag} is schema {manifest.get('schema')}: a pointer names "
                             "only schema-3 releases (the helper-train release T or later).")
        r2.validate_manifest_additions(manifest, platform=platform)
        missing = missing_downloads(http, manifest)
        if missing:
            raise ValueError(f"{platform}: {len(missing)} download(s) of {tag} are gone, so it is not a retained "
                             "release.")
        (out / f"{platform}-manifest.json").write_bytes(data)
        manifests[platform] = {"sha256": r2.sha256_hex(data), "size": len(data), "sequence": manifest["sequence"],
                               "version": manifest["version"]}
    value = {"kind": REPOINT_KIND, "schema": 1, "commit": sha, "target": target, "tag": tag,
             "release_id": record["id"], "platforms": list(platforms), "manifests": manifests}
    (out / "repoint.json").write_text(json.dumps(value, sort_keys=True, indent=1) + "\n", encoding="ascii")
    _write_outputs({"tag": tag, "release_id": record["id"],
                    **{p: str(p in platforms).lower() for p in PLATFORMS}})
    _summary(f"## Repoint to `{tag}`\n\n" + "".join(
        f"- {p}: `{row['version']}`, manifest `{row['sha256']}`, sequence {row['sequence']}\n"
        for p, row in manifests.items()))
    return value


def _repoint_record(check: Path, sha: str) -> dict:
    target, platforms = repoint_inputs()
    value = json.loads((Path(check) / "repoint.json").read_text(encoding="ascii"))
    if (not isinstance(value, dict) or value.get("kind") != REPOINT_KIND or value.get("commit") != sha
            or value.get("target") != target or value.get("tag") != f"client-{target}"
            or value.get("platforms") != list(platforms) or type(value.get("release_id")) is not int
            or value["release_id"] <= 0):
        raise ValueError("The repoint check record is not this run's.")
    return value


def _latest_id() -> int | None:
    return json.loads(release.gh("api", f"repos/{release.REPOSITORY}/releases/latest")).get("id")


def repoint_latest(check: Path) -> int:
    """GitHub first: the alias old helpers read names the target before any pointer does."""
    sha = dispatch_commit(REPOINT_WORKFLOW)
    no_signing_key()
    record = _repoint_record(check, sha)
    runner_release.authorize()
    current = json.loads(release.gh("api", f"repos/{release.REPOSITORY}/releases/{record['release_id']}"))
    if current.get("tag_name") != record["tag"] or current.get("draft") or current.get("prerelease"):
        raise ValueError("The rollback target changed after it was checked.")
    if _latest_id() != record["release_id"]:
        release.gh("release", "edit", record["tag"], "--repo", release.REPOSITORY, "--latest")
    for delay in _CONFIRM_DELAYS:
        if delay:
            time.sleep(delay)
        if _latest_id() == record["release_id"]:
            return record["release_id"]
    raise ValueError("Could not confirm that GitHub latest names the rollback target; rerun this job.")


def repoint_upload(check: Path, pointers: Path) -> list[str]:
    """Upload the signed rollback pointers as the target release's pointer assets."""
    import desktop_r2 as r2
    import release_manifest as rm
    import upload_desktop_assets as up
    sha = dispatch_commit(REPOINT_WORKFLOW)
    no_signing_key()
    record = _repoint_record(check, sha)
    public_pem = rm.commit_public_key(package.REPO, sha)
    pointers = Path(pointers)
    names = {p: r2.pointer_asset_name(p) for p in record["platforms"]}
    if sorted(path.name for path in pointers.iterdir()) != sorted(names.values()):
        raise ValueError("The pointer folder must hold exactly the selected platforms' pointers.")
    rows = []
    for platform, name in names.items():
        manifest = (Path(check) / f"{platform}-manifest.json").read_bytes()
        if r2.sha256_hex(manifest) != record["manifests"][platform]["sha256"]:
            raise ValueError(f"The checked {platform} manifest changed.")
        data = (pointers / name).read_bytes()
        up.check_release_pair(data, lambda _p, _v, value=manifest: value, platform=platform, public_pem=public_pem,
                              commit=record["target"], release_id=record["release_id"], rollback=True)
        rows.append((pointers / name, {"name": name, "size": len(data), "sha256": r2.sha256_hex(data)}))
    runner_release.authorize()
    if _latest_id() != record["release_id"]:
        raise ValueError("GitHub latest must name the rollback target before its pointers are uploaded.")
    for path, _ in rows:
        release.gh("release", "upload", record["tag"], str(path), "--repo", release.REPOSITORY, "--clobber")
    for delay in _CONFIRM_DELAYS:
        if delay:
            time.sleep(delay)
        assets = {asset["name"]: asset for asset in release.github_assets(record["release_id"])}
        if all(release.asset_matches(assets.get(row["name"], {}), row) for _, row in rows):
            break
    else:
        raise ValueError("The uploaded pointers could not be confirmed on the target release; rerun this job.")
    platforms = " ".join(f"--platform {p}" for p in record["platforms"])
    _summary(f"\nGitHub latest names `{record['tag']}` and its rollback pointers are uploaded. On the build machine, "
             "put them live on R2:\n\n```\n"
             f"python godot-client/tools/upload_desktop_assets.py publish --release {record['tag']} {platforms} "
             "--rollback --credentials <private R2 credential file> --receipt <private publish receipt>\n```\n")
    return [row["name"] for _, row in rows]


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("prepare")
    cache = commands.add_parser("cache-key")
    cache.add_argument("--platform", choices=PLATFORMS, required=True)
    target = commands.add_parser("build")
    target.add_argument("--platform", choices=PLATFORMS, required=True)
    target.add_argument("--release-id", type=int, required=True)
    commands.add_parser("live-pointer-guard")
    commands.add_parser("r2-prepare")
    build_step = commands.add_parser("r2-build")
    build_step.add_argument("--platform", choices=PLATFORMS, required=True)
    build_step.add_argument("--content", type=Path, required=True)
    build_step.add_argument("--out", type=Path, required=True)
    setup = commands.add_parser("r2-installers")
    setup.add_argument("--platform", choices=PLATFORMS, required=True)
    setup.add_argument("--envelopes", type=Path)
    setup.add_argument("--exec", type=Path, required=True)
    setup.add_argument("--out", type=Path, required=True)
    setup.add_argument("--dry-run", choices=("true", "false"), required=True)
    test = commands.add_parser("r2-e2e")
    test.add_argument("--platform", choices=PLATFORMS, required=True)
    test.add_argument("--envelopes", type=Path, required=True)
    test.add_argument("--exec", type=Path, required=True)
    test.add_argument("--installers", type=Path, required=True)
    test.add_argument("--receipt", type=Path, required=True)
    test.add_argument("--logs", type=Path, required=True)
    final = commands.add_parser("r2-finalize")
    final.add_argument("--release-id", required=True)
    final.add_argument("--envelopes", type=Path, required=True)
    for platform in PLATFORMS:
        final.add_argument(f"--{platform}-content", type=Path, required=True)
        final.add_argument(f"--{platform}-e2e", type=Path, required=True)
    final.add_argument("--windows-installers", type=Path, required=True)
    final.add_argument("--out", type=Path, required=True)
    publish = commands.add_parser("r2-publish")
    publish.add_argument("--release-id", required=True)
    publish.add_argument("--envelopes", type=Path, required=True)
    publish.add_argument("--pointers", type=Path, required=True)
    publish.add_argument("--receipt", type=Path, required=True)
    promote = commands.add_parser("r2-promote")
    promote.add_argument("--release-id", required=True)
    promote.add_argument("--receipt", type=Path, required=True)
    probe = commands.add_parser("disk-probe")
    probe.add_argument("--label", required=True)
    check = commands.add_parser("repoint-check")
    check.add_argument("--out", type=Path, required=True)
    latest = commands.add_parser("repoint-latest")
    latest.add_argument("--check", type=Path, required=True)
    upload = commands.add_parser("repoint-upload")
    upload.add_argument("--check", type=Path, required=True)
    upload.add_argument("--pointers", type=Path, required=True)
    return parser


def _run(options) -> int:
    command = options.command
    if command == "prepare":
        prepare()
    elif command == "cache-key":
        selected = workflow_commit()
        key = release_asset_cache.input_key(package.git, selected, options.platform)
        native_key = release_native_runtime.release_cache_key(package.REPO, selected, options.platform)["key"]
        with Path(os.environ["GITHUB_OUTPUT"]).open("a", encoding="utf-8") as output:
            output.write(f"key={key}\nnative_key={native_key}\n")
    elif command == "build":
        build(options.platform, options.release_id)
    elif command == "live-pointer-guard":
        live_pointer_guard()
    elif command == "r2-prepare":
        r2_prepare()
    elif command == "r2-build":
        return r2_build(options.platform, options.content, options.out)
    elif command == "r2-installers":
        return r2_installers(options.platform, options.envelopes, options.exec, options.out,
                             options.dry_run == "true")
    elif command == "r2-e2e":
        return r2_e2e(options.platform, options.envelopes, options.exec, options.installers, options.receipt,
                      options.logs)
    elif command == "r2-finalize":
        r2_finalize(options.release_id, options.envelopes,
                    {p: getattr(options, f"{p}_content") for p in PLATFORMS},
                    {p: getattr(options, f"{p}_e2e") for p in PLATFORMS}, options.windows_installers, options.out)
    elif command == "r2-publish":
        r2_publish(options.release_id, options.envelopes, options.pointers, options.receipt)
    elif command == "r2-promote":
        r2_promote(options.release_id, options.receipt)
    elif command == "disk-probe":
        disk_probe(options.label)
    elif command == "repoint-check":
        repoint_check(options.out)
    elif command == "repoint-latest":
        repoint_latest(options.check)
    else:
        repoint_upload(options.check, options.pointers)
    return 0


def main(argv=None) -> int:
    options = build_parser().parse_args(argv)
    try:
        return _run(options)
    except (OSError, ValueError, package.PackageError) as error:
        print(f"Release automation failed: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
