"""Exercise release assembly and publication without building Godot or using GitHub."""
import argparse
import base64
import json
from pathlib import Path
import subprocess
import sys

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
import build_release
import client_release
import package_client

SHA = "a" * 40


def fake_package(folder, platform):
    stage = folder / f"RabbitLands-{platform.title()}-test"
    (stage / "app").mkdir(parents=True)
    (stage / package_client.MARKER).write_text(SHA)
    identity = {"commit": SHA, "platform": platform, "repository": build_release.REPOSITORY}
    (stage / "app/client-release.json").write_text(json.dumps(identity))
    base = f"https://github.com/{build_release.REPOSITORY}/releases/download/client-{SHA}/"
    part = folder / f"{stage.name}.update.zip.001"
    part.write_bytes(b"signed update content")
    payload = {**identity, "parts": [{"url": base + part.name, "size": part.stat().st_size,
                                     "sha256": client_release.digest(part)}]}
    signed = {"payload": base64.b64encode(json.dumps(payload).encode()).decode(), "signature": "test"}
    manifest = folder / f"{stage.name}-{platform}.json"
    manifest.write_text(json.dumps(signed))
    policy = {"schema": 1, "required_commit": SHA, "enforce": True,
              "manifests": {platform: base + manifest.name}}
    (folder / f"{stage.name}-server-policy.json").write_text(json.dumps(policy))
    if platform == "windows":
        (folder / f"{stage.name}-setup.exe").write_bytes(b"installer")
        (folder / f"{stage.name}-setup-1.bin").write_bytes(b"installer data")
    else:
        (folder / f"{stage.name}.tar.gz").write_bytes(b"linux portable archive")
    # These must never become upload assets through a directory glob.
    (folder / "private.pem").write_text("private key fixture")
    (folder / "build.log").write_text("local build details")
    return stage


def test_build_freezes_one_commit_and_collects_only_supported_downloads(tmp_path, monkeypatch):
    commands = []
    monkeypatch.setattr(build_release, "preflight", lambda options: (SHA, tmp_path / "godot.exe", tmp_path / "ISCC.exe"))

    def package(command, **kwargs):
        commands.append(command)
        folder = Path(command[command.index("--out") + 1])
        fake_package(folder, command[command.index("--platform") + 1])

    monkeypatch.setattr(build_release, "run", package)
    options = argparse.Namespace(out=tmp_path, update_signing_key=tmp_path / "signing.pem", server="game.example:2000")
    bundle = build_release.build(options)
    data = json.loads(bundle.read_text())
    assert data["tag"] == f"client-{SHA}"
    assert len(commands) == 2
    assert all(command[command.index("--ref") + 1] == SHA for command in commands)
    assert "--installer" in commands[0] and "--no-zip" in commands[0]
    assert "--installer" not in commands[1] and "--no-zip" not in commands[1]
    assert all("--no-smoke" not in command and "--no-client-updates" not in command for command in commands)
    paths = [Path(row["path"]) for row in data["assets"]]
    assert any(path.name.endswith("-setup-1.bin") for path in paths)
    assert any(path.name.endswith(".tar.gz") for path in paths)
    assert not any(path.suffix in {".pem", ".log"} or "server-policy" in path.name for path in paths)
    assert paths[-1].name == "SHA256SUMS"
    policy = json.loads((bundle.parent / "client_updates.json").read_text())
    assert set(policy["manifests"]) == {"windows", "linux"}
    assert policy["required_commit"] == SHA


def test_large_linux_archive_parts_reassemble_at_the_github_boundary(tmp_path, monkeypatch):
    monkeypatch.setattr(build_release, "ASSET_LIMIT", 32)
    monkeypatch.setattr(build_release, "PART_BYTES", 13)
    archive = tmp_path / "RabbitLands-Linux-test.tar.gz"
    contents = bytes(range(32))
    archive.write_bytes(contents)
    parts = build_release.initial_linux_assets(archive)
    assert len(parts) == 3
    assert all(path.stat().st_size <= 13 for path in parts)
    assert b"".join(path.read_bytes() for path in parts) == contents
    stages = {"windows": tmp_path / "Windows", "linux": tmp_path / "RabbitLands-Linux-test"}
    notes = build_release.release_notes(SHA, stages, parts)
    assert "cat RabbitLands-Linux-test.tar.gz." in notes
    archive.write_bytes(contents[:31])
    assert build_release.initial_linux_assets(archive) == [archive]


def test_inventory_rejects_files_at_limit_and_files_outside_bundle(tmp_path, monkeypatch):
    root = tmp_path / "bundle"
    root.mkdir()
    outside = tmp_path / "private.pem"
    outside.write_bytes(b"not an upload")
    with pytest.raises(ValueError, match="inside"):
        build_release.inventory(root, [outside])
    inside = root / "download"
    inside.write_bytes(b"1234")
    monkeypatch.setattr(build_release, "ASSET_LIMIT", 4)
    with pytest.raises(ValueError, match="oversized"):
        build_release.inventory(root, [inside])


def test_changed_update_part_cannot_enter_release(tmp_path):
    stage = fake_package(tmp_path, "linux")
    (tmp_path / f"{stage.name}.update.zip.001").write_bytes(b"corrupt")
    with pytest.raises(ValueError, match="verification failed"):
        build_release.platform_assets(tmp_path, SHA, "linux")


def upload_fixture(tmp_path):
    asset = tmp_path / "download.exe"
    asset.write_bytes(b"download")
    bundle = tmp_path / "release.json"
    build_release.write_json(bundle, {"schema": 1, "repository": build_release.REPOSITORY,
        "commit": SHA, "tag": f"client-{SHA}", "assets": build_release.inventory(tmp_path, [asset])})
    (tmp_path / "RELEASE-NOTES.md").write_text("Player installation instructions")
    return bundle, asset


def mock_github(monkeypatch, *, account="rabbitlandsgame", public=False, wrong_tag=False, fail_upload=False, remote_digest=None, exists=True, stored_assets=None):
    calls, remote_assets = [], []
    if stored_assets:
        remote_assets.extend(stored_assets)

    def gh(*args):
        nonlocal exists
        calls.append(args)
        if args[:2] == ("api", "user"):
            return account
        if args[0] == "api" and args[-1] == ".permissions.push":
            return "true"
        if args[0] == "api" and args[-1] == ".sha":
            return SHA
        if args[0] == "api" and "matching-refs" in args[1]:
            return json.dumps([{"ref": f"refs/tags/client-{SHA}",
                                "object": {"type": "commit", "sha": "b" * 40 if wrong_tag else SHA}}])
        if args[:3] == ("api", "--paginate", "--slurp"):
            if "/assets?" in args[3]:
                # Use two pages to cover the asset-list pagination.
                return json.dumps([remote_assets[:1], remote_assets[1:]])
            return json.dumps([[{"id": 123, "tag_name": f"client-{SHA}", "draft": not public}]] if exists else [[]])
        if args[:2] == ("release", "create"):
            exists = True
        if args[:2] == ("release", "upload"):
            if fail_upload:
                raise subprocess.CalledProcessError(1, ["gh", *args])
            path = Path(args[3])
            remote_assets.append({"name": path.name, "size": path.stat().st_size,
                                  "digest": remote_digest or "sha256:" + client_release.digest(path)})
        return ""

    monkeypatch.setattr(build_release, "gh", gh)
    return calls


def test_wrong_github_account_cannot_mutate_a_release(tmp_path, monkeypatch):
    bundle, _ = upload_fixture(tmp_path)
    calls = mock_github(monkeypatch, account="some-other-account")
    with pytest.raises(ValueError, match="unrelated account"):
        build_release.upload(bundle, publish=True)
    assert not any(call[0] == "release" for call in calls)


@pytest.mark.parametrize("problem", ["public", "wrong_tag"])
def test_published_release_or_conflicting_tag_cannot_be_replaced(tmp_path, monkeypatch, problem):
    bundle, _ = upload_fixture(tmp_path)
    calls = mock_github(monkeypatch, **{problem: True})
    with pytest.raises(ValueError):
        build_release.upload(bundle, publish=True)
    assert not any(call[0] == "release" for call in calls)


@pytest.mark.parametrize("publish,exists", [(False, False), (False, True), (True, False), (True, True)])
def test_upload_publishes_only_after_all_assets_are_verified(tmp_path, monkeypatch, publish, exists):
    bundle, _ = upload_fixture(tmp_path)
    calls = mock_github(monkeypatch, exists=exists)
    build_release.upload(bundle, publish=publish)
    edits = [call for call in calls if "--draft=false" in call]
    assert bool(edits) == publish
    if publish:
        assert calls[-1] == edits[0]
        assert calls[-2][:3] == ("api", "--paginate", "--slurp") and "/123/assets?" in calls[-2][3]
    if not exists:
        create = next(call for call in calls if call[:2] == ("release", "create"))
        assert "--draft" in create and create[create.index("--target") + 1] == SHA
    else:
        edit = next(call for call in calls if call[:2] == ("release", "edit"))
        assert edit[edit.index("--target") + 1] == SHA


def test_resume_reuses_only_identical_remote_assets(tmp_path, monkeypatch):
    bundle, asset = upload_fixture(tmp_path)
    stored = [{"name": asset.name, "size": asset.stat().st_size,
               "digest": "sha256:" + client_release.digest(asset)}]
    calls = mock_github(monkeypatch, stored_assets=stored)
    build_release.upload(bundle, publish=True)
    assert not any(call[:2] == ("release", "upload") for call in calls)
    assert any("--draft=false" in call for call in calls)


@pytest.mark.parametrize("problem", ["fail_upload", "remote_digest"])
def test_upload_failure_or_bad_remote_checksum_leaves_draft(tmp_path, monkeypatch, problem):
    bundle, _ = upload_fixture(tmp_path)
    value = True if problem == "fail_upload" else "sha256:" + "0" * 64
    calls = mock_github(monkeypatch, **{problem: value})
    with pytest.raises((ValueError, subprocess.CalledProcessError)):
        build_release.upload(bundle, publish=True)
    assert not any("--draft=false" in call for call in calls)


def test_modified_local_download_cannot_be_uploaded(tmp_path, monkeypatch):
    bundle, asset = upload_fixture(tmp_path)
    asset.write_bytes(b"tampered")
    calls = mock_github(monkeypatch)
    with pytest.raises(ValueError, match="changed after"):
        build_release.upload(bundle)
    assert calls == []
