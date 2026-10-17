"""Cross-platform depot handoff, update ownership, and archive safety checks."""
import io
import json
import os
from pathlib import Path
import plistlib
import sys
import tarfile

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
import client_release
import macos_package
import package_client
import steam_release
import store_build

SHA = "a" * 40


def stage(root, platform="windows", distribution="steam", commit=SHA):
    descriptor, binary, _ = steam_release.LAYOUT[platform]
    metadata = root / descriptor
    metadata.parent.mkdir(parents=True)
    metadata.write_text(json.dumps({"commit": commit, "platform": platform,
        "ancestors": [commit], "distribution": distribution}))
    exe = root / binary
    if platform == "macos":
        exe /= "Contents/MacOS/RabbitLands"
    exe.parent.mkdir(parents=True, exist_ok=True)
    exe.write_bytes(b"executable")
    return root


def test_steampipe_requires_same_commit_and_steam_channel(tmp_path):
    windows, linux = stage(tmp_path / "windows"), stage(tmp_path / "linux", "linux")
    depots = {"windows": (101, windows), "linux": (102, linux)}
    output = steam_release.prepare(100, depots, SHA, tmp_path / "preview")
    text = output.read_text()
    assert '"Preview" "1"' in text and '"SetLive" ""' in text
    assert all(f'"{id}" "depot-{os}.vdf"' in text for os, id in [("windows", 101), ("linux", 102)])
    assert str(windows).replace("\\", "/") in (output.parent / "depot-windows.vdf").read_text()
    settings = json.loads((output.parent / "steamworks-launch-settings.json").read_text())
    assert settings["windows"]["working_directory"] == "app"
    data = linux / "app/client-release.json"
    identity = json.loads(data.read_text())
    identity["distribution"] = "github"
    data.write_text(json.dumps(identity))
    with pytest.raises(ValueError, match="Steam builds"):
        steam_release.prepare(100, depots, SHA, tmp_path / "bad")


@pytest.mark.parametrize("problem", ["commit", "ids", "secret", "updater", "appid", "injection", "cache"])
def test_invalid_depots_are_rejected_before_vdf_creation(tmp_path, problem):
    windows = stage(tmp_path / "windows", commit="b" * 40 if problem == "commit" else SHA)
    linux = stage(tmp_path / "linux", "linux")
    depots = {"windows": (101, windows), "linux": (101 if problem == "ids" else 102, linux)}
    if problem in {"secret", "updater", "appid"}:
        name = {"secret": "private.pem", "updater": "RabbitLands-updater.exe", "appid": "steam_appid.txt"}[problem]
        (windows / name).write_text("unwanted")
    if problem == "injection":
        with pytest.raises(ValueError):
            steam_release.quoted('abc"\n"Preview" "0')
        return
    out = windows / "cache" if problem == "cache" else tmp_path / "bad"
    with pytest.raises(ValueError):
        steam_release.prepare(100, depots, SHA, out)
    assert not out.exists()


def test_artifact_stream_roundtrip_and_corruption(tmp_path, monkeypatch):
    source = stage(tmp_path / "source", "linux")
    (source / ".eloria-package").write_text(SHA)
    monkeypatch.setattr(client_release, "PART_BYTES", 100)
    packed = store_build.pack(source, tmp_path / "artifact")
    assert len(packed["parts"]) > 1 and not (tmp_path / "artifact/depot.tar.gz").exists()
    receipt = {"schema": 1, "commit": SHA, "platform": "linux", "distribution": "steam", "archive": packed}
    (tmp_path / "artifact/depot.json").write_text(json.dumps(receipt))
    restored = tmp_path / "restored"
    assert store_build.extract(tmp_path / "artifact", restored) == receipt
    assert (restored / "app/RabbitLands.x86_64").read_bytes() == b"executable"
    assert not (restored / ".eloria-package").exists()
    first = tmp_path / "artifact" / packed["parts"][0]["name"]
    first.write_bytes(first.read_bytes() + b"corruption")
    with pytest.raises(ValueError, match="SHA-256"):
        store_build.extract(tmp_path / "artifact", tmp_path / "bad")
    assert not (tmp_path / "bad").exists()


def test_depot_accepts_its_pinned_public_key_and_rejects_private_material(tmp_path):
    source = stage(tmp_path / "source")
    metadata = source / "app/client-release.json"
    identity = json.loads(metadata.read_text())
    identity["public_key"] = "-----BEGIN PUBLIC KEY-----\nfixture\n-----END PUBLIC KEY-----\n"
    metadata.write_text(json.dumps(identity))
    key = source / "app/data/update_public.pem"
    key.parent.mkdir()
    key.write_text(identity["public_key"])
    assert steam_release.validate(source, "windows", SHA) == source
    key.write_text("-----BEGIN PRIVATE KEY-----\nnever ship\n")
    with pytest.raises(ValueError, match="public key differs"):
        steam_release.validate(source, "windows", SHA)


def test_archive_rejects_traversal_even_with_matching_receipt(tmp_path):
    import hashlib
    artifact = tmp_path / "artifact"
    artifact.mkdir()
    part = artifact / "depot.tar.gz.001"
    with tarfile.open(part, "w:gz") as archive:
        info = tarfile.TarInfo("../../escape")
        info.size = 4
        archive.addfile(info, io.BytesIO(b"evil"))
    digest = hashlib.sha256(part.read_bytes()).hexdigest()
    size = part.stat().st_size
    (artifact / "depot.json").write_text(json.dumps({"schema": 1, "distribution": "steam",
        "archive": {"parts": [{"name": part.name, "size": size, "sha256": digest}], "size": size, "sha256": digest}}))
    with pytest.raises(tarfile.TarError):
        store_build.extract(artifact, tmp_path / "out")
    assert not (tmp_path / "escape").exists()


def test_mac_import_formats_do_not_change_github_presets(tmp_path):
    (tmp_path / "project.godot").write_text("[rendering]\ntextures/vram_compression/import_etc2_astc=false\n")
    macos_package.prepare_import(tmp_path)
    assert "import_etc2_astc=true" in (tmp_path / "project.godot").read_text()
    assert 'binary_format/architecture="universal"' in macos_package.EXPORT_PRESET
    assert package_client.EXPORT_PRESETS.count("texture_format/etc2_astc=false") == 2


def test_macos_finish_moves_assets_without_extra_copy_and_seals_bundle(tmp_path, monkeypatch):
    monkeypatch.setattr(macos_package, "native", lambda: None)
    root = tmp_path / "stage"
    root.mkdir()
    app = macos_package.bundle(root)
    (app / "Contents/MacOS").mkdir(parents=True)
    (app / "Contents/MacOS/Rabbit Lands").write_bytes(b"universal-game-binary")
    (app / "Contents/Resources").mkdir()
    (app / "Contents/Info.plist").write_bytes(plistlib.dumps({"CFBundleExecutable": "Rabbit Lands"}))
    (root / "app").mkdir()
    (root / "app/RabbitLands.pck").write_bytes(b"game pack")
    (root / "eloria-assets").mkdir()
    asset = root / "eloria-assets/world.json"
    asset.write_text("world")
    before = asset.stat().st_ino
    commands = []
    monkeypatch.setattr(macos_package.subprocess, "run", lambda command, **kwargs: commands.append(command))
    monkeypatch.setattr(macos_package, "sign", lambda path: commands.append(["seal", path]))
    macos_package.finish(root, tmp_path, {"commit": SHA, "distribution": "steam"})
    assert (app / "Contents/eloria-assets/world.json").stat().st_ino == before
    assert (app / "Contents/Resources/RabbitLands.pck").read_bytes() == b"game pack"
    assert (app / "Contents/MacOS/RabbitLands").read_bytes() == b"universal-game-binary"
    assert not (root / "app").exists()
    assert commands[-1] == ["seal", app]
    assert commands[0][0] == "lipo" and commands[0][2:] == ["-verify_arch", "x86_64", "arm64"]


def test_mac_cross_export_fails_instead_of_claiming_a_native_test(tmp_path, monkeypatch):
    monkeypatch.setattr(macos_package.sys, "platform", "win32")
    with pytest.raises(ValueError, match="native macOS"):
        macos_package.native()
