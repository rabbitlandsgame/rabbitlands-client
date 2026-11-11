"""Checks for draft selection, hosted signing-key lifetime and the R2 workflow glue, without GitHub writes."""
import hashlib
import io
import json
import shlex
import subprocess
import os
from pathlib import Path
import sys
import zipfile

import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
import actions_release as actions
import setup_runner_tools as tools

SHA = "a" * 40


def context(tmp_path, monkeypatch):
    (tmp_path / "rabbitlands-native-toolchain").mkdir(exist_ok=True)
    for name, value in {"GITHUB_ACTIONS": "true", "GITHUB_REPOSITORY": actions.release.REPOSITORY,
                        "GITHUB_REF": "refs/heads/master", "GITHUB_EVENT_NAME": "push",
                        "GITHUB_SHA": SHA, "SIGNING_KEY_AVAILABLE": "true",
                        "GITHUB_RUN_ID": "42", "GITHUB_RUN_ATTEMPT": "1",
                        "RUSTUP_HOME": str(tmp_path / "rabbitlands-native-toolchain/rustup"),
                        "CARGO_HOME": str(tmp_path / "rabbitlands-native-toolchain/cargo"),
                        "GITHUB_OUTPUT": str(tmp_path / "outputs"), "RUNNER_TEMP": str(tmp_path)}.items():
        monkeypatch.setenv(name, value)
    monkeypatch.setattr(actions.package, "git", lambda *args: SHA)
    monkeypatch.setattr(actions.runner_release, "exact_checkout", lambda repo: 1)  # its own tests below
    monkeypatch.setattr(actions.runner_release, "authorize", lambda: None)
    monkeypatch.setattr(actions.shared_release_assets, "ensure", lambda sha: {"id": 789})


def test_existing_draft_is_selected_without_changing_previous_downloads(tmp_path, monkeypatch):
    context(tmp_path, monkeypatch)
    draft = {"id": 123, "tag_name": "client-" + "b" * 40, "draft": True,
             "author": {"login": "rabbitlandsgame"}}
    monkeypatch.setattr(actions.release, "github_releases", lambda: [draft])
    monkeypatch.setattr(actions.release, "gh", lambda *args: pytest.fail("Preparation must not retag or prune the existing draft"))
    assert actions.prepare() == (SHA, 123)
    assert (tmp_path / "outputs").read_text() == f"commit={SHA}\nrelease_id=123\n"


def test_no_client_draft_creates_one_and_preserves_published_release(tmp_path, monkeypatch):
    context(tmp_path, monkeypatch)
    published = {"tag_name": "client-" + "b" * 40, "draft": False}
    calls = []
    monkeypatch.setattr(actions.release, "github_releases", lambda: [published])
    monkeypatch.setattr(actions.release, "gh", lambda *args: calls.append(args))
    monkeypatch.setattr(actions.release, "github_release", lambda tag: {
        "id": 456, "draft": True, "author": {"login": "github-actions[bot]"}})
    assert actions.prepare() == (SHA, 456)
    assert len(calls) == 1 and calls[0][:2] == ("release", "create") and "--draft" in calls[0]


def test_new_draft_visibility_is_retried_without_duplicate_creation(tmp_path, monkeypatch):
    context(tmp_path, monkeypatch)
    monkeypatch.setattr(actions.release, "github_releases", lambda: [])
    created, waits = [], []
    monkeypatch.setattr(actions.release, "gh", lambda *args: created.append(args))
    sequence = iter([None, None, {"id": 789, "draft": True, "author": {"login": "github-actions[bot]"}}])
    monkeypatch.setattr(actions.release, "github_release", lambda tag: next(sequence))
    monkeypatch.setattr(actions.time, "sleep", waits.append)
    assert actions.prepare() == (SHA, 789)
    assert len(created) == 1 and waits == [1, 2]


def test_mac_toolchain_retains_signed_bundle_and_portable_templates(tmp_path, monkeypatch):
    monkeypatch.setattr(tools.sys, "platform", "darwin")
    def download(spec, target):
        with zipfile.ZipFile(target, "w") as archive:
            if spec == tools.DOWNLOADS["macos"]:
                archive.writestr("Godot.app/Contents/MacOS/Godot", b"signed-editor")
                archive.writestr("Godot.app/Contents/Info.plist", b"signed-plist")
            else:
                archive.writestr("templates/macos.zip", b"universal-template")
    def run(command, **kwargs):
        assert command[:3] == ["ditto", "-x", "-k"]
        with zipfile.ZipFile(command[3]) as archive:
            archive.extractall(command[4])
    monkeypatch.setattr(tools, "download", download)
    monkeypatch.setattr(tools.subprocess, "run", run)
    root = tmp_path / "tools"
    config = tools.install("macos", root, installers=False)
    assert config["godot"] == root / "Godot.app/Contents/MacOS/Godot"
    assert (root / "Godot.app/Contents/Info.plist").read_bytes() == b"signed-plist"
    assert (root / "_sc_").is_file()
    assert (root / "editor_data/export_templates/4.7.2.stable/macos.zip").read_bytes() == b"universal-template"
    assert not (root / "editor.zip").exists()


@pytest.mark.parametrize("condition", ["unrelated-owner", "ambiguous-drafts"])
def test_draft_selection_does_not_mutate_an_unexpected_destination(tmp_path, monkeypatch, condition):
    context(tmp_path, monkeypatch)
    draft = {"id": 123, "tag_name": "client-" + "b" * 40, "draft": True,
             "author": {"login": "other-account" if condition == "unrelated-owner" else "rabbitlandsgame"}}
    entries = [draft, dict(draft, id=456)] if condition == "ambiguous-drafts" else [draft]
    monkeypatch.setattr(actions.release, "github_releases", lambda: entries)
    monkeypatch.setattr(actions.release, "gh", lambda *args: pytest.fail("Do not change an unexpected destination"))
    with pytest.raises(ValueError):
        actions.prepare()


def test_manual_develop_run_uses_its_exact_checkout(tmp_path, monkeypatch):
    context(tmp_path, monkeypatch)
    monkeypatch.setenv("GITHUB_EVENT_NAME", "workflow_dispatch")
    monkeypatch.setenv("GITHUB_REF", "refs/heads/develop")
    assert actions.workflow_commit() == SHA
    monkeypatch.setenv("GITHUB_EVENT_NAME", "push")
    with pytest.raises(ValueError, match="only on master"):
        actions.workflow_commit()


def test_workflow_token_does_not_require_human_permissions_metadata(monkeypatch):
    monkeypatch.setenv("GITHUB_ACTIONS", "true")
    monkeypatch.setenv("GITHUB_REPOSITORY", actions.release.REPOSITORY)
    calls = []
    def gh(*args):
        calls.append(args)
        assert args[-1] == ".full_name"
        return actions.release.REPOSITORY
    monkeypatch.setattr(actions.release, "gh", gh)
    actions.runner_release.authorize()
    assert len(calls) == 1
    monkeypatch.setenv("GITHUB_REPOSITORY", "other/repository")
    with pytest.raises(ValueError, match="not executing"):
        actions.runner_release.authorize()
    assert len(calls) == 1


@pytest.mark.parametrize("condition", ["missing-secret", "published-same-commit", "wrong-branch", "wrong-checkout"])
def test_prepare_rejects_unusable_run_before_any_release_write(tmp_path, monkeypatch, condition):
    context(tmp_path, monkeypatch)
    entries = []
    if condition == "missing-secret":
        monkeypatch.setenv("SIGNING_KEY_AVAILABLE", "false")
    elif condition == "published-same-commit":
        entries = [{"tag_name": f"client-{SHA}", "draft": False}]
    elif condition == "wrong-branch":
        monkeypatch.setenv("GITHUB_REF", "refs/heads/other")
    else:
        monkeypatch.setattr(actions.package, "git", lambda *args: "c" * 40)
    monkeypatch.setattr(actions.release, "github_releases", lambda: entries)
    monkeypatch.setattr(actions.release, "gh", lambda *args: pytest.fail("No write is allowed"))
    with pytest.raises(ValueError):
        actions.prepare()
    assert not (tmp_path / "outputs").exists()


@pytest.mark.parametrize("fail", [False, True])
def test_key_is_removed_from_environment_and_deleted_after_build(tmp_path, monkeypatch, fail):
    context(tmp_path, monkeypatch)
    private = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    key = private.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.TraditionalOpenSSL,
                                serialization.NoEncryption())
    public = private.public_key().public_bytes(serialization.Encoding.PEM, serialization.PublicFormat.SubjectPublicKeyInfo)
    monkeypatch.setenv(actions.SECRET, key.decode())
    monkeypatch.setattr(actions.package, "git", lambda *args: public.decode() if args[0] == "show" else SHA)
    def install(platform, root):
        assert actions.SECRET not in os.environ
        return {"godot": root / "godot", "env": {"XDG_DATA_HOME": str(root / "data")}}
    monkeypatch.setattr(tools, "install", install)
    paths = []
    def build(options):
        paths.append(options.update_signing_key)
        assert actions.SECRET not in os.environ
        assert paths[0].read_bytes() == key
        assert not paths[0].is_relative_to(actions.package.REPO)
        assert options.native_tool_root == tmp_path / "rabbitlands-native-toolchain"
        assert (options.native_tool_root / actions.runner_retirement.SDK_MARKER).is_file()
        if fail:
            raise ValueError("fixture build failure")
        return tmp_path / "receipt.json"
    monkeypatch.setattr(actions.runner_release, "build", build)
    previous = os.environ.get("XDG_DATA_HOME")
    if fail:
        with pytest.raises(ValueError, match="fixture"):
            actions.build("linux", 123)
    else:
        assert actions.build("linux", 123) == tmp_path / "receipt.json"
    assert paths and not paths[0].exists() and not paths[0].parent.exists()
    assert os.environ.get("XDG_DATA_HOME") == previous


def test_mismatched_key_fails_before_downloading_tools(tmp_path, monkeypatch):
    context(tmp_path, monkeypatch)
    monkeypatch.setenv(actions.SECRET, "invalid fixture key")
    monkeypatch.setattr(tools, "install", lambda *args: pytest.fail("Do not download tools with an invalid key"))
    with pytest.raises(ValueError, match="RSA PEM"):
        actions.build("linux", 123)


@pytest.mark.parametrize("bad", [False, True])
def test_tool_download_checks_bytes_and_removes_only_its_failed_download(tmp_path, monkeypatch, bad):
    data = b"tool fixture"
    spec = ("https://example.invalid/tool.zip", len(data), hashlib.sha256(data).hexdigest())
    monkeypatch.setattr(tools.urllib.request, "urlopen", lambda *args, **kwargs: io.BytesIO(data + (b"!" if bad else b"")))
    target = tmp_path / "tool.zip"
    if bad:
        with pytest.raises(ValueError, match="pinned"):
            tools.download(spec, target)
        assert not target.exists()
    else:
        tools.download(spec, target)
        assert target.read_bytes() == data
    target.write_bytes(b"preexisting")
    with pytest.raises(FileExistsError):
        tools.download(spec, target)
    assert target.read_bytes() == b"preexisting"


def test_extracts_only_the_named_release_template(tmp_path):
    archive = tmp_path / "templates.zip"
    with zipfile.ZipFile(archive, "w") as output:
        output.writestr("templates/linux_release.x86_64", b"release")
        output.writestr("templates/linux_debug.x86_64", b"debug")
        output.writestr("../escape", b"unwanted")
    target = tmp_path / "tools/template"
    tools.extract_member(archive, "templates/linux_release.x86_64", target)
    assert target.read_bytes() == b"release"
    assert sorted(path.relative_to(tmp_path).as_posix() for path in tmp_path.rglob("*") if path.is_file()) == [
        "templates.zip", "tools/template"]


@pytest.mark.skipif(os.name != "nt", reason="Windows toolchain installation fixture")
def test_windows_toolchain_keeps_one_template_and_removes_downloads(tmp_path, monkeypatch):
    def download(spec, target):
        if spec == tools.DOWNLOADS["inno"]:
            target.write_bytes(b"installer fixture")
            return
        with zipfile.ZipFile(target, "w") as archive:
            if spec == tools.DOWNLOADS["windows"]:
                archive.writestr("Godot_v4.7.2-stable_win64.exe", b"editor")
                archive.writestr("Godot_v4.7.2-stable_win64_console.exe", b"console")
            else:
                archive.writestr("templates/windows_release_x86_64.exe", b"release")
                archive.writestr("templates/linux_release.x86_64", b"other platform")
    def run(command, **kwargs):
        assert "/VERYSILENT" in command and "/CURRENTUSER" in command
        directory = Path(next(arg.removeprefix("/DIR=") for arg in command if arg.startswith("/DIR=")))
        directory.mkdir()
        (directory / "ISCC.exe").write_bytes(b"compiler")
    monkeypatch.setattr(tools, "download", download)
    monkeypatch.setattr(tools.subprocess, "run", run)
    root = tmp_path / "toolchain"
    config = tools.install("windows", root)
    assert config["iscc"].read_bytes() == b"compiler"
    assert config["env"] == {"APPDATA": str(root / "data")}
    assert sorted(path.relative_to(root).as_posix() for path in root.rglob("*") if path.is_file()) == [
        "Godot_v4.7.2-stable_win64.exe", "data/Godot/export_templates/4.7.2.stable/windows_release_x86_64.exe", "inno/ISCC.exe"]


# --- desktop-release-r2.yml, desktop-repoint.yml and the old workflow's guard ------------------

import desktop_r2 as r2  # noqa: E402
import prune_published_release  # noqa: E402
import release_manifest as rm  # noqa: E402
import upload_desktop_assets as up  # noqa: E402
import test_release_manifest as fx  # noqa: E402
from test_desktop_release_ci import FakeHttp  # noqa: E402

key = fx.key
other_key = fx.other_key
COMMIT = fx.COMMIT
TARGET = fx.PARENT
INPUTS = {"WINDOWS_SOURCE": "r2", "WINDOWS_SET_SHA256": "1" * 64, "LINUX_SOURCE": "r2",
          "LINUX_SET_SHA256": "2" * 64, "DRY_RUN": "false"}
CAPS_R2 = rm.ReaderCapabilities(schema3=True, r2_rows=True, package_limit=2000)
CAPS_B8 = rm.ReaderCapabilities(schema3=True, r2_rows=False, package_limit=850)
REAL_COMMIT_CAPABILITIES = rm.commit_capabilities
REAL_RETENTION_SCHEMA = getattr(prune_published_release, "RETENTION_SCHEMA", None)


def dispatch(tmp_path, monkeypatch, *, workflow=actions.R2_WORKFLOW, sha=SHA, ref="refs/heads/develop", inputs=None):
    for name, value in {"GITHUB_ACTIONS": "true", "GITHUB_REPOSITORY": actions.release.REPOSITORY,
                        "GITHUB_REF": ref, "GITHUB_EVENT_NAME": "workflow_dispatch",
                        "GITHUB_WORKFLOW_REF": f"{actions.release.REPOSITORY}/{workflow}@{ref}",
                        "GITHUB_SHA": sha, "GITHUB_OUTPUT": str(tmp_path / "outputs"),
                        "GITHUB_STEP_SUMMARY": str(tmp_path / "summary.md"),
                        "RUNNER_TEMP": str(tmp_path / "runner"), **(inputs or {})}.items():
        monkeypatch.setenv(name, value)
    (tmp_path / "runner").mkdir(exist_ok=True)
    monkeypatch.delenv(actions.SECRET, raising=False)
    monkeypatch.setattr(actions.package, "git", lambda *args: sha)
    monkeypatch.setattr(actions.runner_release, "exact_checkout", lambda repo: 1)  # its own tests below
    monkeypatch.setattr(actions.runner_release, "authorize", lambda: None)
    monkeypatch.setattr(actions.shared_release_assets, "ensure", lambda value: {"id": 789})
    monkeypatch.setattr(prune_published_release, "RETENTION_SCHEMA", 2, raising=False)
    # R1's commit pins the last GitHub-hosted release (T); r2 content needs the pin.
    monkeypatch.setattr(prune_published_release, "PINNED_GITHUB_HOSTED", PIN, raising=False)
    monkeypatch.setattr(rm, "commit_capabilities", lambda repo, commit: CAPS_R2)


PIN = "client-" + "c" * 40


def outputs(tmp_path) -> dict:
    return dict(line.split("=", 1) for line in (tmp_path / "outputs").read_text().splitlines())


def no_github(monkeypatch):
    monkeypatch.setattr(actions.release, "gh", lambda *args: pytest.fail("no GitHub call is allowed here"))
    monkeypatch.setattr(actions.release, "github_releases", lambda: pytest.fail("no GitHub call is allowed here"))
    monkeypatch.setattr(actions.runner_release, "authorize", lambda: pytest.fail("no GitHub call is allowed here"))
    monkeypatch.setattr(actions.shared_release_assets, "ensure", lambda sha: pytest.fail("no pool write"))


@pytest.mark.parametrize("change, message", [
    ({"GITHUB_EVENT_NAME": "push"}, "dispatched"),
    ({"GITHUB_REF": "refs/heads/feature"}, "dispatched"),
    ({"GITHUB_REPOSITORY": "other/fork"}, "dispatched"),
    ({"GITHUB_ACTIONS": "false"}, "dispatched"),
    ({"GITHUB_WORKFLOW_REF": "rabbitlandsgame/rabbitlands-client/.github/workflows/desktop-release.yml"
                             "@refs/heads/develop"}, "running workflow file"),
    ({"GITHUB_SHA": "A" * 40}, "exact source commit"),
])
def test_dispatch_commit_needs_the_dispatched_workflow_on_a_release_branch(tmp_path, monkeypatch, change, message):
    dispatch(tmp_path, monkeypatch)
    assert actions.dispatch_commit(actions.R2_WORKFLOW) == SHA
    for name, value in change.items():
        monkeypatch.setenv(name, value)
    with pytest.raises(ValueError, match=message):
        actions.dispatch_commit(actions.R2_WORKFLOW)


def test_dispatch_commit_refuses_a_checkout_of_another_commit(tmp_path, monkeypatch):
    dispatch(tmp_path, monkeypatch, ref="refs/heads/master")
    assert actions.dispatch_commit(actions.R2_WORKFLOW) == SHA
    monkeypatch.setattr(actions.package, "git", lambda *args: "c" * 40)
    with pytest.raises(ValueError, match="exact source commit"):
        actions.dispatch_commit(actions.R2_WORKFLOW)


# --- the exact-bytes checkout guard (second R2 dry run: CRLF native inputs on Windows) ---------

def isolated_git(tmp_path, monkeypatch, system: str = "") -> None:
    """Only this test's Git config: the machine's own (a Windows system autocrlf=true) must not leak in."""
    for name, text in (("GIT_CONFIG_SYSTEM", system), ("GIT_CONFIG_GLOBAL", "")):
        path = tmp_path / f"{name.lower()}.gitconfig"
        path.write_text(text, encoding="ascii")
        monkeypatch.setenv(name, str(path))
    monkeypatch.delenv("GIT_CONFIG_NOSYSTEM", raising=False)


def committed_source(tmp_path) -> Path:
    """A commit shaped like the release checkout: LF native inputs and updater scripts, a CRLF blob kept
    exact by -text (like the map authoring scripts), an executable and a path outside the sparse set."""
    source = tmp_path / "source"
    files = {".gitattributes": b"tools/kept_crlf.gd -text\n",
             "native/client_runtime/CMakeLists.txt": b"cmake_minimum_required(VERSION 3.20)\nproject(x)\n",
             "native/client_runtime/client_runtime.gdextension.in": b"[configuration]\nentry_symbol=\"x\"\n",
             "src/updates/release.gd": b"extends RefCounted\nconst CODEC_SCHEMA := 3\n",
             "tools/kept_crlf.gd": b"extends Node\r\nfunc _ready():\r\n\tpass\r\n",
             "tools/run.sh": b"#!/bin/sh\necho ok\n",
             "world/big_source.txt": b"outside the sparse checkout\n"}
    for name, data in files.items():
        (source / name).parent.mkdir(parents=True, exist_ok=True)
        (source / name).write_bytes(data)
    git = ["git", "-c", "user.name=t", "-c", "user.email=t@example.invalid", "-C", str(source)]
    subprocess.run(["git", "init", "-q", str(source)], check=True)
    subprocess.run([*git, "add", "-A"], check=True)
    subprocess.run([*git, "update-index", "--chmod=+x", "tools/run.sh"], check=True)
    subprocess.run([*git, "commit", "-q", "-m", "source"], check=True)
    return source


def ci_checkout(tmp_path, source: Path, name: str, *, config: dict | None = None) -> Path:
    """actions/checkout's steps: init, fetch, a non-cone sparse file, a forced checkout."""
    target = tmp_path / name
    subprocess.run(["git", "init", "-q", str(target)], check=True)
    for key, value in (config or {}).items():
        subprocess.run(["git", "-C", str(target), "config", key, value], check=True)
    subprocess.run(["git", "-C", str(target), "fetch", "-q", str(source), "HEAD"], check=True)
    subprocess.run(["git", "-C", str(target), "config", "core.sparseCheckout", "true"], check=True)
    (target / ".git/info").mkdir(parents=True, exist_ok=True)
    (target / ".git/info/sparse-checkout").write_text("/native/\n/src/updates/\n/tools/\n", encoding="ascii")
    subprocess.run(["git", "-C", str(target), "checkout", "-q", "--force", "FETCH_HEAD"], check=True)
    return target


def test_exact_checkout_accepts_committed_bytes_crlf_blobs_and_sparse_paths(tmp_path, monkeypatch):
    isolated_git(tmp_path, monkeypatch)
    checkout = ci_checkout(tmp_path, committed_source(tmp_path), "checkout")
    assert not (checkout / "world").exists()
    assert (checkout / "tools/kept_crlf.gd").read_bytes().count(b"\r\n") == 3
    assert actions.runner_release.exact_checkout(checkout) == 5  # 2 native, release.gd, 2 tools (not world/)


def test_exact_checkout_refuses_the_windows_images_line_ending_conversion(tmp_path, monkeypatch):
    # The windows-2025 image: core.autocrlf=true in Git's system config, nothing in the global config.
    isolated_git(tmp_path, monkeypatch, system="[core]\n\tautocrlf = true\n")
    source = committed_source(tmp_path)
    converted = ci_checkout(tmp_path, source, "converted")
    assert (converted / "native/client_runtime/CMakeLists.txt").read_bytes().count(b"\r\n") == 2
    with pytest.raises(ValueError, match=r"core\.autocrlf=true.*git config --global core\.autocrlf false"):
        actions.runner_release.exact_checkout(converted)
    # The bytes alone refuse too, once the setting is gone (or set by something the check does not read).
    subprocess.run(["git", "-C", str(converted), "config", "core.autocrlf", "false"], check=True)
    with pytest.raises(ValueError, match=r"^4 checked-out files differ from their committed blobs \(first: "
                                         r"native/client_runtime/CMakeLists.txt, native/client_runtime/"
                                         r"client_runtime.gdextension.in, src/updates/release.gd\)"):
        actions.runner_release.exact_checkout(converted)
    # The workflows' first step, in the runner's global config, before the checkout: exact bytes.
    for command in actions.runner_release.EXACT_CHECKOUT_STEPS:
        subprocess.run(shlex.split(command), check=True)
    fixed = ci_checkout(tmp_path, source, "fixed")
    assert actions.runner_release.exact_checkout(fixed) == 5


def test_exact_checkout_refuses_changed_and_missing_checked_out_files(tmp_path, monkeypatch):
    isolated_git(tmp_path, monkeypatch)
    checkout = ci_checkout(tmp_path, committed_source(tmp_path), "checkout")
    (checkout / "src/updates/release.gd").write_bytes(b"extends RefCounted\n")
    (checkout / "tools/run.sh").unlink()
    with pytest.raises(ValueError, match=r"^2 checked-out files differ .*first: src/updates/release.gd, "
                                         r"tools/run.sh\)"):
        actions.runner_release.exact_checkout(checkout)


@pytest.mark.parametrize("check", ["dispatch", "workflow"])
def test_every_release_job_entry_proves_its_checkout_holds_exact_bytes(tmp_path, monkeypatch, check):
    """dispatch_commit (R2, repoint) and workflow_commit (the old workflow) run the guard on the tools'
    repository right after the commit check, before any tool download, build or GitHub call."""
    if check == "dispatch":
        dispatch(tmp_path, monkeypatch)
        entry = lambda: actions.dispatch_commit(actions.R2_WORKFLOW)  # noqa: E731
    else:
        context(tmp_path, monkeypatch)
        entry = actions.workflow_commit
    seen = []
    monkeypatch.setattr(actions.runner_release, "exact_checkout", lambda repo: seen.append(repo) or 670)
    assert entry() == SHA and seen == [actions.package.REPO]

    def converted(repo):
        raise ValueError("210 checked-out files differ from their committed blobs")
    monkeypatch.setattr(actions.runner_release, "exact_checkout", converted)
    with pytest.raises(ValueError, match="210 checked-out files differ"):
        entry()


@pytest.mark.parametrize("change", [
    {"WINDOWS_SOURCE": "R2"}, {"WINDOWS_SOURCE": "r2\n"}, {"WINDOWS_SOURCE": ""}, {"LINUX_SOURCE": "local"},
    {"WINDOWS_SET_SHA256": "1" * 63}, {"WINDOWS_SET_SHA256": "A" * 64}, {"WINDOWS_SET_SHA256": "1" * 64 + "\n"},
    {"LINUX_SET_SHA256": ""}, {"LINUX_SET_SHA256": "2" * 64 + " "}, {"LINUX_SET_SHA256": "$(id)" + "2" * 59},
    {"LINUX_SOURCE": "ci"}, {"DRY_RUN": "yes"}, {"DRY_RUN": ""}, {"DRY_RUN": "True"},
    {"LINUX_SET_SHA256": "1" * 64},
    # none is a dry run's only: a real release always has both platforms.
    {"WINDOWS_SOURCE": "none", "WINDOWS_SET_SHA256": ""}, {"WINDOWS_SOURCE": "none"},
    {"WINDOWS_SOURCE": "None", "WINDOWS_SET_SHA256": ""},
])
def test_r2_inputs_are_regex_validated(change):
    assert actions.r2_inputs(INPUTS)["platforms"]["windows"] == {"source": "r2", "set_sha256": "1" * 64}
    with pytest.raises(ValueError):
        actions.r2_inputs({**INPUTS, **change})


def test_r2_inputs_take_a_linux_only_dry_run():
    value = actions.r2_inputs({**INPUTS, "WINDOWS_SOURCE": "none", "WINDOWS_SET_SHA256": "",
                               "LINUX_SOURCE": "ci", "LINUX_SET_SHA256": "", "DRY_RUN": "true"})
    assert value == {"platforms": {"windows": {"source": "none", "set_sha256": ""},
                                   "linux": {"source": "ci", "set_sha256": ""}}, "dry_run": True}


@pytest.mark.parametrize("change", [
    {"WINDOWS_SOURCE": "none", "WINDOWS_SET_SHA256": "1" * 64},  # none takes no set
    {"WINDOWS_SOURCE": "none", "WINDOWS_SET_SHA256": "", "LINUX_SOURCE": "none", "LINUX_SET_SHA256": ""},
])
def test_r2_inputs_refuse_a_dry_run_none_with_a_set_or_without_any_platform(change):
    with pytest.raises(ValueError):
        actions.r2_inputs({**INPUTS, "DRY_RUN": "true", **change})


def test_r2_inputs_take_ci_sources_without_a_set_hash():
    value = actions.r2_inputs({**INPUTS, "LINUX_SOURCE": "ci", "LINUX_SET_SHA256": "", "DRY_RUN": "true"})
    assert value == {"platforms": {"windows": {"source": "r2", "set_sha256": "1" * 64},
                                   "linux": {"source": "ci", "set_sha256": ""}}, "dry_run": True}


@pytest.mark.parametrize("schema", [None, 1, True, "2", 2.0])
def test_retention_guard_refuses_a_prune_that_deletes_rollback_releases(monkeypatch, schema):
    if schema is None:
        monkeypatch.delattr(prune_published_release, "RETENTION_SCHEMA", raising=False)
    else:
        monkeypatch.setattr(prune_published_release, "RETENTION_SCHEMA", schema, raising=False)
    with pytest.raises(ValueError, match="RETENTION_SCHEMA"):
        actions.retention_guard()
    monkeypatch.setattr(prune_published_release, "RETENTION_SCHEMA", 2, raising=False)
    assert actions.retention_guard() == 2


def test_this_tree_keeps_whole_releases_so_the_r2_workflow_may_run():
    # R2-A7 landed: this tree's prune keeps whole releases, so the retention guard passes.
    assert REAL_RETENTION_SCHEMA == prune_published_release.RETENTION_SCHEMA >= actions.MIN_RETENTION_SCHEMA
    assert actions.retention_guard() == REAL_RETENTION_SCHEMA


@pytest.mark.parametrize("condition, message", [
    ("retention", "RETENTION_SCHEMA"), ("signing-key", actions.SECRET), ("ci-leg-missing", "build-content"),
    ("reader-lacks-r2", "DESKTOP_ASSETS"), ("reader-keeps-850", "2000"), ("inputs", "windows_set_sha256"),
    ("no-pin", "PINNED_GITHUB_HOSTED"), ("pin-not-a-tag", "PINNED_GITHUB_HOSTED"),
    ("pin-uppercase", "PINNED_GITHUB_HOSTED"), ("pin-missing", "PINNED_GITHUB_HOSTED"),
    ("other-draft", "Another client draft"), ("published", "already has a published release")])
def test_r2_prepare_refuses_before_any_release_write(tmp_path, monkeypatch, condition, message):
    dispatch(tmp_path, monkeypatch, inputs=INPUTS)
    entries = []
    if condition == "retention":
        monkeypatch.setattr(prune_published_release, "RETENTION_SCHEMA", 1)
    elif condition == "no-pin":
        monkeypatch.setattr(prune_published_release, "PINNED_GITHUB_HOSTED", None)
    elif condition == "pin-not-a-tag":
        monkeypatch.setattr(prune_published_release, "PINNED_GITHUB_HOSTED", "c" * 40)
    elif condition == "pin-uppercase":
        monkeypatch.setattr(prune_published_release, "PINNED_GITHUB_HOSTED", "client-" + "C" * 40)
    elif condition == "pin-missing":
        monkeypatch.delattr(prune_published_release, "PINNED_GITHUB_HOSTED")
    elif condition == "signing-key":
        monkeypatch.setenv(actions.SECRET, "not for this job")
    elif condition == "ci-leg-missing":
        # a commit from before R2-A6b: its desktop_release_ci.py has no build-content
        monkeypatch.setenv("LINUX_SOURCE", "ci")
        monkeypatch.setenv("LINUX_SET_SHA256", "")
        monkeypatch.setattr(actions, "ci_tool_commands", lambda: {"verify-content", "executables", "sign"})
    elif condition == "reader-lacks-r2":
        monkeypatch.setattr(rm, "commit_capabilities", lambda repo, commit: CAPS_B8)
    elif condition == "reader-keeps-850":
        # the R2 base without W1a's raised package limit is not the W1a reader
        monkeypatch.setattr(rm, "commit_capabilities", lambda repo, commit: rm.ReaderCapabilities(
            schema3=True, r2_rows=True, package_limit=850))
    elif condition == "inputs":
        monkeypatch.setenv("WINDOWS_SET_SHA256", "")
    elif condition == "other-draft":
        entries = [{"id": 5, "tag_name": "client-" + "b" * 40, "draft": True, "author": {"login": "rabbitlandsgame"}}]
    else:
        entries = [{"id": 5, "tag_name": f"client-{SHA}", "draft": False, "author": {"login": "rabbitlandsgame"}}]
    monkeypatch.setattr(actions.release, "github_releases", lambda: entries)
    monkeypatch.setattr(actions.release, "gh", lambda *args: pytest.fail("No write is allowed"))
    monkeypatch.setattr(actions.shared_release_assets, "ensure", lambda sha: pytest.fail("No pool write is allowed"))
    with pytest.raises(ValueError, match=message):
        actions.r2_prepare()
    assert not (tmp_path / "outputs").exists()


def _tree_git(*args) -> str:
    result = subprocess.run(["git", "-C", str(actions.package.REPO), *args], capture_output=True, text=True)
    if result.returncode:
        pytest.skip("this checkout's Git history is not available")
    return result.stdout.strip()


def test_this_tree_opens_the_r2_gate_from_the_w1a_commit_on(tmp_path, monkeypatch):
    """The r2 gate is on: r2-prepare reads this commit's own updater from Git and finds
    W1a's exact declarations; the commit before W1a keeps it shut."""
    head = _tree_git("rev-parse", "HEAD^{commit}")
    if _tree_git("rev-parse", "--is-shallow-repository") != "false":
        pytest.skip("a shallow checkout lacks the W1a history")
    line = f'const DESKTOP_ASSETS := "{r2.DESKTOP_ASSETS}"'
    added = _tree_git("log", "--format=%H", "--reverse", "-S", line, head, "--", rm.RELEASE_GD).splitlines()
    assert added, "W1a's DESKTOP_ASSETS line is in no commit of this history"
    first = added[0]
    before = _tree_git("rev-parse", f"{first}^")
    assert rm.r2_source_problem(REAL_COMMIT_CAPABILITIES(actions.package.REPO, head)) is None
    assert rm.r2_source_problem(REAL_COMMIT_CAPABILITIES(actions.package.REPO, first)) is None
    assert "DESKTOP_ASSETS" in rm.r2_source_problem(REAL_COMMIT_CAPABILITIES(actions.package.REPO, before))
    # r2-prepare itself, with this tree's retention module and the commit's real reader (dry run)
    dispatch(tmp_path, monkeypatch, sha=head, inputs={**INPUTS, "DRY_RUN": "true"})
    monkeypatch.setattr(rm, "commit_capabilities", REAL_COMMIT_CAPABILITIES)
    monkeypatch.setattr(prune_published_release, "RETENTION_SCHEMA", REAL_RETENTION_SCHEMA)
    no_github(monkeypatch)
    values = actions.r2_prepare()
    assert values["r2_any"] == "true" and values["windows_source"] == values["linux_source"] == "r2"
    (tmp_path / "before").mkdir()
    dispatch(tmp_path / "before", monkeypatch, sha=before, inputs={**INPUTS, "DRY_RUN": "true"})
    monkeypatch.setattr(rm, "commit_capabilities", REAL_COMMIT_CAPABILITIES)
    no_github(monkeypatch)
    with pytest.raises(ValueError, match="DESKTOP_ASSETS"):
        actions.r2_prepare()


def test_r2_prepare_dry_run_makes_no_github_call_and_emits_validated_matrices(tmp_path, monkeypatch):
    dispatch(tmp_path, monkeypatch, inputs={**INPUTS, "DRY_RUN": "true"})
    no_github(monkeypatch)
    actions.r2_prepare()
    values = outputs(tmp_path)
    assert values["release_id"] == "0" and values["dry_run"] == "true" and values["commit"] == SHA
    assert json.loads(values["r2_matrix"]) == {"include": [{"platform": "windows", "set_sha256": "1" * 64},
                                                           {"platform": "linux", "set_sha256": "2" * 64}]}
    assert json.loads(values["ci_matrix"]) == {"include": []}
    assert json.loads(values["build_matrix"]) == {"include": [{"platform": "windows", "runner": "windows-2025"},
                                                              {"platform": "linux", "runner": "ubuntu-24.04"}]}
    assert (values["r2_any"], values["ci_any"]) == ("true", "false")
    assert "Dry run" in (tmp_path / "summary.md").read_text()


def test_r2_prepare_linux_only_dry_run_builds_and_checks_linux_alone(tmp_path, monkeypatch):
    dispatch(tmp_path, monkeypatch, inputs={**INPUTS, "WINDOWS_SOURCE": "none", "WINDOWS_SET_SHA256": "",
                                            "LINUX_SOURCE": "ci", "LINUX_SET_SHA256": "", "DRY_RUN": "true"})
    monkeypatch.setattr(actions, "ci_tool_commands", lambda: {"verify-content", actions.CI_CONTENT_COMMAND})
    no_github(monkeypatch)
    actions.r2_prepare()
    values = outputs(tmp_path)
    assert values["release_id"] == "0" and values["dry_run"] == "true"
    assert (values["windows_source"], values["windows_set_sha256"]) == ("none", "")
    assert (values["r2_any"], values["ci_any"]) == ("false", "true")
    assert json.loads(values["r2_matrix"]) == {"include": []}
    assert json.loads(values["ci_matrix"]) == {"include": [{"platform": "linux", "runner": "ubuntu-24.04"}]}
    assert json.loads(values["build_matrix"]) == {"include": [{"platform": "linux", "runner": "ubuntu-24.04"}]}


def test_r2_prepare_creates_this_commits_draft_and_a_ci_leg_when_available(tmp_path, monkeypatch):
    dispatch(tmp_path, monkeypatch, inputs={**INPUTS, "LINUX_SOURCE": "ci", "LINUX_SET_SHA256": ""})
    monkeypatch.setattr(actions, "ci_tool_commands", lambda: {"verify-content", actions.CI_CONTENT_COMMAND})
    created, ensured = [], []
    monkeypatch.setattr(actions.release, "github_releases", lambda: [])
    monkeypatch.setattr(actions.release, "gh", lambda *args: created.append(args))
    monkeypatch.setattr(actions.release, "github_release", lambda tag: {
        "id": 456, "tag_name": tag, "draft": True, "author": {"login": "github-actions[bot]"}})
    monkeypatch.setattr(actions.shared_release_assets, "ensure", ensured.append)
    actions.r2_prepare()
    values = outputs(tmp_path)
    assert values["release_id"] == "456" and values["dry_run"] == "false" and ensured == [SHA]
    assert len(created) == 1 and created[0][:3] == ("release", "create", f"client-{SHA}") and "--draft" in created[0]
    assert json.loads(values["ci_matrix"]) == {"include": [{"platform": "linux", "runner": "ubuntu-24.04"}]}
    assert json.loads(values["r2_matrix"]) == {"include": [{"platform": "windows", "set_sha256": "1" * 64}]}
    assert (values["linux_source"], values["linux_set_sha256"]) == ("ci", "")


@pytest.mark.parametrize("inputs", [
    {**INPUTS, "DRY_RUN": "true"},  # a dry run publishes and prunes nothing
    {**INPUTS, "WINDOWS_SOURCE": "ci", "WINDOWS_SET_SHA256": "", "LINUX_SOURCE": "ci", "LINUX_SET_SHA256": ""}])
def test_r2_prepare_needs_the_pin_only_for_a_real_release_with_r2_content(tmp_path, monkeypatch, inputs):
    # Release T (ci sources) comes before its own tag can be pinned; R1's commit sets the pin.
    dispatch(tmp_path, monkeypatch, inputs=inputs)
    monkeypatch.setattr(prune_published_release, "PINNED_GITHUB_HOSTED", None)
    monkeypatch.setattr(actions, "ci_tool_commands", lambda: {"verify-content", actions.CI_CONTENT_COMMAND})
    monkeypatch.setattr(actions.release, "github_releases", lambda: [])
    monkeypatch.setattr(actions.release, "gh", lambda *args: None)
    monkeypatch.setattr(actions.release, "github_release", lambda tag: {
        "id": 456, "tag_name": tag, "draft": True, "author": {"login": "github-actions[bot]"}})
    assert actions.r2_prepare()["commit"] == SHA
    with pytest.raises(ValueError, match="PINNED_GITHUB_HOSTED"):
        actions.pinned_release_guard()
    monkeypatch.setattr(prune_published_release, "PINNED_GITHUB_HOSTED", PIN)
    assert actions.pinned_release_guard() == PIN


def test_r2_prepare_reuses_only_this_commits_draft(tmp_path, monkeypatch):
    dispatch(tmp_path, monkeypatch, inputs=INPUTS)
    draft = {"id": 321, "tag_name": f"client-{SHA}", "draft": True, "author": {"login": "rabbitlandsgame"}}
    monkeypatch.setattr(actions.release, "github_releases", lambda: [draft])
    monkeypatch.setattr(actions.release, "gh", lambda *args: pytest.fail("reuse, do not create"))
    actions.r2_prepare()
    assert outputs(tmp_path)["release_id"] == "321"


def test_ci_leg_needs_the_build_content_subcommand():
    assert actions.CI_CONTENT_COMMAND in actions.ci_tool_commands()  # R2-A6b
    assert {"verify-content", "build-content", "content-cache-key", "executables", "sign", "pointer",
            "installers", "stage", "e2e", "artifact-digest"} <= actions.ci_tool_commands()


@pytest.mark.parametrize("statuses, ok", [((404, 404), True), ((200, 404), False), ((404, 200), False),
                                          ((403, 404), False), ((503, 404), False), (("error", 404), False)])
def test_live_pointer_guard_passes_only_while_both_pointers_are_absent(statuses, ok):
    calls = []

    class Http:
        def request(self, method, url, *, limit, headers=None, keep_body=True):
            calls.append((method, url, limit))
            status = statuses[len(calls) - 1]
            if status == "error":
                raise up.UploadError("http-error", "URLError")
            return up.HttpResponse(status, {})
    if ok:
        actions.live_pointer_guard(Http())
    else:
        with pytest.raises(ValueError):
            actions.live_pointer_guard(Http())
    expected = [("GET", r2.pointer_url(platform), r2.MAX_POINTER_BYTES) for platform in r2.PLATFORMS]
    assert calls == expected[:len(calls)] and (len(calls) == 2 or not ok)


def test_main_reports_refusals_without_a_traceback(tmp_path, monkeypatch, capsys):
    dispatch(tmp_path, monkeypatch, inputs={**INPUTS, "DRY_RUN": "maybe"})
    no_github(monkeypatch)
    assert actions.main(["r2-prepare"]) == 1
    assert "dry_run must be true or false" in capsys.readouterr().err
    assert actions.main(["disk-probe", "--label", "Not A Label"]) == 1


@pytest.mark.parametrize("values", [{"tag": "a\nrelease_id=1"}, {"tag": "a\r"}, {"Bad-Name": "x"}, {"": "x"}])
def test_step_outputs_refuse_names_and_values_that_could_inject_another_output(tmp_path, monkeypatch, values):
    dispatch(tmp_path, monkeypatch)
    actions._write_outputs({"tag": "client-" + "a" * 40, "release_id": 7})
    with pytest.raises(ValueError, match="unsafe step output"):
        actions._write_outputs(values)
    assert outputs(tmp_path) == {"tag": "client-" + "a" * 40, "release_id": "7"}


def test_disk_probe_writes_a_summary(tmp_path, monkeypatch, capsys):
    dispatch(tmp_path, monkeypatch)
    rows = actions.disk_probe("build-linux")
    assert rows and all(row["free"] <= row["total"] for row in rows)
    assert "Disk: build-linux" in (tmp_path / "summary.md").read_text()
    assert json.loads(capsys.readouterr().out)["label"] == "build-linux"


# --- signed fixtures ------------------------------------------------------------------------

def signed_release(tmp_path, key, platform, *, commit=COMMIT, schema3=True):
    """A signed release manifest of `commit` (test key), built like the sign job builds it."""
    stage = fx.make_stage(tmp_path / f"stage-{platform}-{commit[:4]}", platform, key, commit=commit)
    caps = fx.CAPS_R2 if schema3 else fx.CAPS2
    identity = fx.identity(platform, key, commit, ancestors=[commit, "9" * 40])
    payload = fx.build_payload(stage, platform, key, tmp_path / f"work-{platform}-{commit[:4]}",
                               source="r2" if schema3 else "ci", caps=caps, identity=identity)
    private = rm.load_signing_key(key.private, key.public)
    manifest, _ = rm.sign_manifest(payload, identity, caps, private, key.public)
    return manifest, payload


def pointer_for(manifest, key, platform, *, release_id=7, rollback=False, sequence=fx.SEQUENCE + 600):
    private = rm.load_signing_key(key.private, key.public)
    return rm.pointer_envelope(platform=platform, sequence=sequence, rollback=rollback, release_id=release_id,
                               run_id=9, manifest=manifest, private_key=private, public_pem=key.public)


def envelopes_dir(tmp_path, key, commit=COMMIT) -> tuple[Path, dict]:
    folder = tmp_path / "envelopes"
    folder.mkdir()
    platforms, manifests = {}, {}
    for platform in r2.PLATFORMS:
        manifest, payload = signed_release(tmp_path, key, platform, commit=commit)
        name = f"{payload['version']}-{platform}.json"
        (folder / name).write_bytes(manifest)
        (folder / f"RabbitLands-{platform}.json").write_bytes(manifest)
        platforms[platform] = {"manifest": name, "sha256": hashlib.sha256(manifest).hexdigest(),
                               "bytes": len(manifest), "schema": 3, "sequence": fx.SEQUENCE}
        manifests[platform] = manifest
    (folder / "sign.json").write_text(json.dumps({"commit": commit, "platforms": platforms}), encoding="ascii")
    return folder, manifests


@pytest.fixture
def released(tmp_path_factory, key):
    """Both platforms' signed manifests of COMMIT, shared by the publish tests."""
    root = tmp_path_factory.mktemp("released")
    folder, manifests = envelopes_dir(root, key)
    return folder, manifests


def test_sign_record_accepts_only_this_runs_two_manifests(tmp_path, released):
    folder, _ = released
    record = actions.sign_record(folder, COMMIT)
    assert set(record) == {"windows", "linux"}
    with pytest.raises(ValueError):
        actions.sign_record(folder, TARGET)
    data = json.loads((folder / "sign.json").read_text())
    other_version = data["platforms"]["linux"]["manifest"].replace(COMMIT[:9], TARGET[:9])
    (folder / other_version).write_bytes((folder / data["platforms"]["linux"]["manifest"]).read_bytes())
    for mutate in (lambda d: d["platforms"]["linux"].update(manifest=other_version),  # another commit's name
                   lambda d: d["platforms"].pop("linux"),
                   lambda d: d["platforms"]["linux"].update(manifest="../RabbitLands-linux.json"),
                   lambda d: d["platforms"]["linux"].update(manifest=d["platforms"]["windows"]["manifest"]),
                   lambda d: d["platforms"]["windows"].update(sha256="nope"),
                   lambda d: d.update(platforms=[])):
        copy = tmp_path / f"copy-{len(list(tmp_path.iterdir()))}"
        copy.mkdir()
        for path in folder.iterdir():
            (copy / path.name).write_bytes(path.read_bytes())
        changed = json.loads(json.dumps(data))
        mutate(changed)
        (copy / "sign.json").write_text(json.dumps(changed))
        with pytest.raises(ValueError):
            actions.sign_record(copy, COMMIT)


def pointer_folder(tmp_path, manifests, key, **options) -> Path:
    folder = tmp_path / "pointers"
    folder.mkdir()
    for platform, manifest in manifests.items():
        (folder / r2.pointer_asset_name(platform)).write_bytes(pointer_for(manifest, key, platform, **options))
    return folder


def test_publish_checks_this_runs_forward_pointers_before_r2_a7_writes(tmp_path, monkeypatch, released, key):
    folder, manifests = released
    dispatch(tmp_path, monkeypatch, sha=COMMIT)
    monkeypatch.setattr(rm, "commit_public_key", lambda repo, commit: key.public)
    calls = []
    monkeypatch.setattr(actions, "r2_a7", lambda step: lambda **kwargs: calls.append((step, kwargs)) or "url")
    pointers = pointer_folder(tmp_path, manifests, key)
    assert actions.r2_publish("7", folder, pointers, tmp_path / "runner-release.json") == "url"
    assert calls == [("publish", {"commit": COMMIT, "release_id": 7, "receipt": tmp_path / "runner-release.json",
                                  "pointers": pointers})]
    summary = (tmp_path / "summary.md").read_text()
    assert f"upload_desktop_assets.py publish --release client-{COMMIT} --platform windows --platform linux" in summary
    assert "C:/" not in summary and "<private R2 credential file>" in summary


@pytest.mark.parametrize("problem", ["rollback", "release-id", "extra-file", "missing", "other-key", "release-id-text"])
def test_publish_refuses_pointers_that_are_not_this_runs(tmp_path, monkeypatch, released, key, other_key, problem):
    folder, manifests = released
    dispatch(tmp_path, monkeypatch, sha=COMMIT)
    monkeypatch.setattr(rm, "commit_public_key", lambda repo, commit: key.public)
    monkeypatch.setattr(actions, "r2_a7", lambda step: pytest.fail("R2-A7 must not run"))
    options, release_id = {}, "7"
    if problem == "rollback":
        options = {"rollback": True}
    elif problem == "release-id":
        options = {"release_id": 8}
    elif problem == "release-id-text":
        release_id = "7 "
    pointers = pointer_folder(tmp_path, manifests, key, **options)
    if problem == "extra-file":
        (pointers / "RabbitLands-windows.json").write_bytes(b"{}")
    elif problem == "missing":
        (pointers / r2.pointer_asset_name("linux")).unlink()
    elif problem == "other-key":
        good = rm.verify((pointers / r2.pointer_asset_name("linux")).read_bytes(), key.public,
                         limit=r2.MAX_POINTER_BYTES)[1]
        forged = rm.sign(r2.pointer_bytes(good, platform="linux"),
                         rm.load_signing_key(other_key.private, other_key.public))
        (pointers / r2.pointer_asset_name("linux")).write_bytes(forged)
    with pytest.raises(ValueError):
        actions.r2_publish(release_id, folder, pointers, tmp_path / "runner-release.json")


@pytest.mark.parametrize("step", ["finalize", "publish", "promote"])
def test_r2_a7_entry_points_are_refused_by_name_until_they_exist(monkeypatch, step):
    module = __import__(actions.R2_A7[step][0])
    monkeypatch.delattr(module, actions.R2_A7[step][1], raising=False)
    with pytest.raises(ValueError, match=actions.R2_A7[step][1]):
        actions.r2_a7(step)
    monkeypatch.setattr(module, actions.R2_A7[step][1], lambda **kwargs: kwargs, raising=False)
    assert actions.r2_a7(step)(x=1) == {"x": 1}


def test_finalize_and_promote_pass_validated_arguments_to_r2_a7(tmp_path, monkeypatch, released):
    folder, _ = released
    dispatch(tmp_path, monkeypatch, sha=COMMIT)
    calls = []
    monkeypatch.setattr(actions, "r2_a7", lambda step: lambda **kwargs: calls.append((step, kwargs)) or step)
    content = {p: tmp_path / f"content-{p}" for p in r2.PLATFORMS}
    e2e = {p: tmp_path / f"e2e-{p}" for p in r2.PLATFORMS}
    installers = tmp_path / "installers-windows"
    assert actions.r2_finalize("12", folder, content, e2e, installers, tmp_path / "out") == "finalize"
    assert actions.r2_promote("12", tmp_path / "receipt.json") == "promote"
    assert calls == [("finalize", {"commit": COMMIT, "release_id": 12, "envelopes": folder, "content": content,
                                   "e2e": e2e, "installers": {"windows": installers}, "out": tmp_path / "out"}),
                     ("promote", {"commit": COMMIT, "release_id": 12, "receipt": tmp_path / "receipt.json"})]
    assert "check-policy" in (tmp_path / "summary.md").read_text()
    for bad in ("0", "-1", "1e3", "", "12\n"):
        with pytest.raises(ValueError):
            actions.r2_promote(bad, tmp_path / "receipt.json")
    monkeypatch.setattr(prune_published_release, "RETENTION_SCHEMA", 1)
    with pytest.raises(ValueError, match="RETENTION_SCHEMA"):
        actions.r2_promote("12", tmp_path / "receipt.json")
    monkeypatch.setattr(prune_published_release, "RETENTION_SCHEMA", 2)
    monkeypatch.setenv(actions.SECRET, "never here")
    with pytest.raises(ValueError, match=actions.SECRET):
        actions.r2_finalize("12", folder, content, e2e, installers, tmp_path / "out")
    assert len(calls) == 2


# --- tool wrappers (no real tools, Godot or network) ---------------------------------------

def fake_tools(tmp_path, monkeypatch, seen):
    def install(platform, root, *, installers=True):
        seen.append(("install", platform, installers, Path(root)))
        (root / "data").mkdir(parents=True)
        (root / "godot").write_bytes(b"editor")
        config = {"godot": root / "godot", "env": {"XDG_DATA_HOME": str(root / "data")}}
        if installers:
            (root / "ISCC.exe").write_bytes(b"iscc")
            config["iscc"] = root / "ISCC.exe"
        return config
    monkeypatch.setattr(actions.setup_runner_tools, "install", install)

    def ci_main(argv):
        seen.append(("ci", list(argv), os.environ.get("XDG_DATA_HOME")))
        return 0
    import desktop_release_ci
    monkeypatch.setattr(desktop_release_ci, "main", ci_main)


def test_r2_build_installs_pinned_tools_and_runs_executables_with_their_environment(tmp_path, monkeypatch):
    dispatch(tmp_path, monkeypatch)
    monkeypatch.delenv("XDG_DATA_HOME", raising=False)
    seen = []
    fake_tools(tmp_path, monkeypatch, seen)
    assert actions.r2_build("linux", tmp_path / "content-linux", tmp_path / "exec-linux") == 0
    root = tmp_path / "runner" / "rabbitlands-toolchain"
    assert seen[0] == ("install", "linux", False, root)
    assert seen[1] == ("ci", ["executables", "--platform", "linux", "--commit", SHA, "--godot", str(root / "godot"),
                              "--content", str(tmp_path / "content-linux"), "--work",
                              str(tmp_path / "runner" / "exec-work"), "--out", str(tmp_path / "exec-linux")],
                       str(root / "data"))
    assert "XDG_DATA_HOME" not in os.environ  # restored after the step
    monkeypatch.setenv(actions.SECRET, "never in the build job")
    with pytest.raises(ValueError, match=actions.SECRET):
        actions.r2_build("linux", tmp_path / "content-linux", tmp_path / "exec-linux")


def test_r2_installers_use_the_signed_manifest_and_inno_on_windows(tmp_path, monkeypatch, released):
    folder, _ = released
    dispatch(tmp_path, monkeypatch, sha=COMMIT)
    seen = []
    fake_tools(tmp_path, monkeypatch, seen)
    assert actions.r2_installers("windows", folder, tmp_path / "exec-windows", tmp_path / "out", False) == 0
    argv = seen[1][1]
    name = actions.sign_record(folder, COMMIT)["windows"]["manifest"]
    assert argv[:6] == ["installers", "--platform", "windows", "--commit", COMMIT, "--envelope"]
    assert argv[6] == str(folder / name)
    assert argv[-2:] == ["--iscc", str(tmp_path / "runner/rabbitlands-toolchain/ISCC.exe")]


def test_r2_installers_dry_run_only_installs_tools_and_measures(tmp_path, monkeypatch):
    dispatch(tmp_path, monkeypatch)
    seen = []
    fake_tools(tmp_path, monkeypatch, seen)
    assert actions.r2_installers("windows", None, tmp_path / "exec-windows", tmp_path / "out", True) == 0
    assert [item[0] for item in seen] == ["install"] and seen[0][2] is True
    record = json.loads((tmp_path / "out" / "dry-run.json").read_text())
    assert record["godot"] and record["iscc"] and record["setup"].startswith("skipped") and record["disk"]


def test_r2_e2e_runs_the_signed_manifest_and_installer_and_keeps_logs(tmp_path, monkeypatch, released):
    folder, _ = released
    dispatch(tmp_path, monkeypatch, sha=COMMIT)
    version = actions.sign_record(folder, COMMIT)["windows"]["manifest"][:-len("-windows.json")]
    installers = tmp_path / "installers-windows"
    installers.mkdir()
    import desktop_release_ci
    seen = []

    def ci_main(argv):
        seen.append(argv)
        work = Path(argv[argv.index("--work") + 1])
        (work / "logs").mkdir(parents=True)
        (work / "logs" / "install.log").write_text("installed")
        return 3
    monkeypatch.setattr(desktop_release_ci, "main", ci_main)
    with pytest.raises(ValueError, match="setup.exe"):
        actions.r2_e2e("windows", folder, tmp_path / "exec", installers, tmp_path / "e2e/e2e.json", tmp_path / "logs")
    (installers / f"{version}-setup.exe").write_bytes(b"setup")
    assert actions.r2_e2e("windows", folder, tmp_path / "exec", installers, tmp_path / "e2e/e2e.json",
                          tmp_path / "logs") == 3
    (argv,) = seen
    assert argv[argv.index("--envelope") + 1] == str(folder / f"{version}-windows.json")
    assert argv[argv.index("--installer") + 1] == str(installers / f"{version}-setup.exe")
    assert (tmp_path / "logs" / "install.log").read_text() == "installed"
    assert actions.LINUX_E2E_WORK == Path("/mnt/rl-e2e/work")


# --- repoint ----------------------------------------------------------------------------------

def target_release(tmp_path, key, *, schema3=True, author="github-actions[bot]"):
    """A published release of TARGET on a fake public GitHub and custom domain, every download present."""
    http = FakeHttp()
    tag = f"client-{TARGET}"
    assets, manifests = [], {}
    for platform in r2.PLATFORMS:
        manifest, payload = signed_release(tmp_path, key, platform, commit=TARGET, schema3=schema3)
        manifests[platform] = (manifest, payload)
        name = f"RabbitLands-{platform}.json"
        assets.append({"name": name, "state": "uploaded", "size": len(manifest)})
        http.objects[f"{r2.GITHUB_DOWNLOADS}{tag}/{name}"] = manifest
        for row in actions.manifest_rows(payload):
            http.objects[row["url"]] = b"x" * row["size"]
    record = {"id": 99, "tag_name": tag, "draft": False, "prerelease": False, "author": {"login": author},
              "assets": assets}
    http.objects[f"{up.GITHUB_API}repos/{r2.REPOSITORY}/releases/tags/{tag}"] = json.dumps(record).encode()
    return http, manifests


def repoint_env(tmp_path, monkeypatch, key, platforms="both"):
    dispatch(tmp_path, monkeypatch, workflow=actions.REPOINT_WORKFLOW, sha=COMMIT,
             inputs={"TARGET_COMMIT": TARGET, "REPOINT_PLATFORMS": platforms})
    monkeypatch.setattr(rm, "commit_public_key", lambda repo, commit: key.public)
    monkeypatch.setattr(actions, "tag_commit", lambda tag: TARGET)


def test_repoint_check_verifies_the_target_and_every_download(tmp_path, monkeypatch, key):
    repoint_env(tmp_path, monkeypatch, key)
    http, manifests = target_release(tmp_path, key)
    record = actions.repoint_check(tmp_path / "repoint", http=http)
    assert record["release_id"] == 99 and record["platforms"] == ["windows", "linux"] and record["target"] == TARGET
    for platform in r2.PLATFORMS:
        assert (tmp_path / "repoint" / f"{platform}-manifest.json").read_bytes() == manifests[platform][0]
    heads = {url for method, url in http.calls if method == "HEAD"}
    assert heads == {row["url"] for _, payload in manifests.values() for row in actions.manifest_rows(payload)}
    gets = [url for method, url in http.calls if method == "GET"]
    assert not any(url.startswith(r2.DESKTOP_ASSETS) for url in gets)  # parts are only HEADed
    assert outputs(tmp_path) == {"tag": f"client-{TARGET}", "release_id": "99", "windows": "true", "linux": "true"}


@pytest.mark.parametrize("problem", ["schema-2", "missing-part", "missing-helper", "author", "tag", "other-key",
                                     "wrong-commit", "not-empty", "inputs", "draft"])
def test_repoint_check_refuses_a_target_that_is_not_a_retained_schema_3_release(
        tmp_path, monkeypatch, key, other_key, problem):
    repoint_env(tmp_path, monkeypatch, key)
    http, manifests = target_release(tmp_path, key, schema3=problem != "schema-2",
                                     author="someone" if problem == "author" else "github-actions[bot]")
    payload = manifests["linux"][1]
    if problem == "missing-part":
        del http.objects[payload["packages"][0]["parts"][0]["url"]]
    elif problem == "missing-helper":
        del http.objects[payload["updater"]["url"]]
    elif problem == "tag":
        monkeypatch.setattr(actions, "tag_commit", lambda tag: "d" * 40)
    elif problem == "other-key":
        monkeypatch.setattr(rm, "commit_public_key", lambda repo, commit: other_key.public)
    elif problem == "wrong-commit":
        monkeypatch.setattr(actions, "tag_commit", lambda tag: COMMIT)
        monkeypatch.setenv("TARGET_COMMIT", COMMIT)
        # client-COMMIT carries TARGET's (validly signed, fully present) manifests
        record = json.dumps({"id": 99, "tag_name": f"client-{COMMIT}", "draft": False, "prerelease": False,
                             "author": {"login": "rabbitlandsgame"},
                             "assets": [{"name": f"RabbitLands-{p}.json", "state": "uploaded",
                                         "size": len(manifests[p][0])} for p in r2.PLATFORMS]}).encode()
        http.objects[f"{up.GITHUB_API}repos/{r2.REPOSITORY}/releases/tags/client-{COMMIT}"] = record
        for p in r2.PLATFORMS:
            http.objects[f"{r2.GITHUB_DOWNLOADS}client-{COMMIT}/RabbitLands-{p}.json"] = manifests[p][0]
    elif problem == "not-empty":
        (tmp_path / "repoint").mkdir()
        (tmp_path / "repoint" / "stale.json").write_text("{}")
    elif problem == "inputs":
        monkeypatch.setenv("REPOINT_PLATFORMS", "all")
    elif problem == "draft":
        url = f"{up.GITHUB_API}repos/{r2.REPOSITORY}/releases/tags/client-{TARGET}"
        http.objects[url] = json.dumps({**json.loads(http.objects[url]), "draft": True}).encode()
    with pytest.raises(ValueError):
        actions.repoint_check(tmp_path / "repoint", http=http)
    assert not (tmp_path / "outputs").exists()


class FakeGitHub:
    """`gh` for the repoint jobs: release records, latest, edits, uploads and asset listings."""

    def __init__(self, release_id=99, latest=55):
        self.release_id, self.latest, self.calls, self.assets = release_id, latest, [], {}

    def gh(self, *args):
        self.calls.append(args)
        if args[:2] == ("release", "edit"):
            assert "--latest" in args
            self.latest = self.release_id
            return ""
        if args[:2] == ("release", "upload"):
            assert "--clobber" in args
            data = Path(args[3]).read_bytes()
            self.assets[Path(args[3]).name] = {"name": Path(args[3]).name, "state": "uploaded", "size": len(data),
                                               "digest": "sha256:" + hashlib.sha256(data).hexdigest()}
            return ""
        if args[1].endswith("/releases/latest"):
            return json.dumps({"id": self.latest})
        if args[1].endswith(f"/releases/{self.release_id}"):
            return json.dumps({"id": self.release_id, "tag_name": f"client-{TARGET}", "draft": False,
                               "prerelease": False})
        raise AssertionError(args)


def checked_target(tmp_path, monkeypatch, key, platforms="both"):
    repoint_env(tmp_path, monkeypatch, key, platforms)
    http, manifests = target_release(tmp_path, key)
    actions.repoint_check(tmp_path / "repoint", http=http)
    github = FakeGitHub()
    monkeypatch.setattr(actions.release, "gh", github.gh)
    monkeypatch.setattr(actions.release, "github_assets", lambda release_id: list(github.assets.values()))
    return github, manifests


def test_repoint_moves_github_latest_first_then_uploads_signed_rollback_pointers(tmp_path, monkeypatch, key):
    github, manifests = checked_target(tmp_path, monkeypatch, key)
    pointers = tmp_path / "pointers"
    pointers.mkdir()
    for platform in r2.PLATFORMS:
        (pointers / r2.pointer_asset_name(platform)).write_bytes(
            pointer_for(manifests[platform][0], key, platform, release_id=99, rollback=True))
    with pytest.raises(ValueError, match="GitHub latest"):
        actions.repoint_upload(tmp_path / "repoint", pointers)  # GitHub first
    assert actions.repoint_latest(tmp_path / "repoint") == 99
    assert [call[:2] for call in github.calls].count(("release", "edit")) == 1
    assert sorted(actions.repoint_upload(tmp_path / "repoint", pointers)) == sorted(
        r2.pointer_asset_name(p) for p in r2.PLATFORMS)
    uploads = [call for call in github.calls if call[:2] == ("release", "upload")]
    assert [call[2] for call in uploads] == [f"client-{TARGET}", f"client-{TARGET}"]
    summary = (tmp_path / "summary.md").read_text()
    assert f"publish --release client-{TARGET} --platform windows --platform linux --rollback" in summary
    # a second latest call is a confirmation only
    actions.repoint_latest(tmp_path / "repoint")
    assert [call[:2] for call in github.calls].count(("release", "edit")) == 1


@pytest.mark.parametrize("problem", ["forward", "other-release", "extra", "other-platform-only", "changed-record"])
def test_repoint_upload_refuses_pointers_that_are_not_signed_rollbacks_of_the_target(
        tmp_path, monkeypatch, key, problem):
    github, manifests = checked_target(tmp_path, monkeypatch, key, "windows")
    github.latest = 99
    pointers = tmp_path / "pointers"
    pointers.mkdir()
    options = {"release_id": 99, "rollback": True}
    if problem == "forward":
        options["rollback"] = False
    elif problem == "other-release":
        options["release_id"] = 98
    platform = "linux" if problem == "other-platform-only" else "windows"
    (pointers / r2.pointer_asset_name(platform)).write_bytes(
        pointer_for(manifests[platform][0], key, platform, **options))
    if problem == "extra":
        (pointers / r2.pointer_asset_name("linux")).write_bytes(
            pointer_for(manifests["linux"][0], key, "linux", release_id=99, rollback=True))
    elif problem == "changed-record":
        monkeypatch.setenv("REPOINT_PLATFORMS", "both")
    with pytest.raises(ValueError):
        actions.repoint_upload(tmp_path / "repoint", pointers)
    assert not any(call[:2] == ("release", "upload") for call in github.calls)


def test_tag_commit_follows_annotated_tags():
    responses = {
        f"repos/{actions.release.REPOSITORY}/git/matching-refs/tags/client-{TARGET}": [
            {"ref": f"refs/tags/client-{TARGET}0", "object": {"type": "commit", "sha": "0" * 40}},
            {"ref": f"refs/tags/client-{TARGET}", "object": {"type": "tag", "sha": "e" * 40}}],
        f"repos/{actions.release.REPOSITORY}/git/tags/{'e' * 40}": {"object": {"type": "commit", "sha": TARGET}}}
    original = actions.release.gh
    try:
        actions.release.gh = lambda *args: json.dumps(responses[args[1]])
        assert actions.tag_commit(f"client-{TARGET}") == TARGET
        actions.release.gh = lambda *args: "[]"
        assert actions.tag_commit(f"client-{TARGET}") is None
    finally:
        actions.release.gh = original
