"""Checks for draft selection and hosted signing-key lifetime, without GitHub writes."""
import hashlib
import io
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
    for name, value in {"GITHUB_ACTIONS": "true", "GITHUB_REPOSITORY": actions.release.REPOSITORY,
                        "GITHUB_REF": "refs/heads/master", "GITHUB_EVENT_NAME": "push",
                        "GITHUB_SHA": SHA, "SIGNING_KEY_AVAILABLE": "true",
                        "GITHUB_OUTPUT": str(tmp_path / "outputs"), "RUNNER_TEMP": str(tmp_path)}.items():
        monkeypatch.setenv(name, value)
    monkeypatch.setattr(actions.package, "git", lambda *args: SHA)
    monkeypatch.setattr(actions.runner_release, "authorize", lambda: None)


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
