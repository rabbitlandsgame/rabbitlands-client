"""Cold/warm release builds, with real ZIPs, signatures and file inventories."""
import base64
import json
import os
from pathlib import Path
import subprocess
import sys

import pytest
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding, rsa

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
import asset_packages
import build_release
import client_release
import package_client
from release_asset_cache import AssetCache, input_key
from release_storage import DiskBudget, unique_bytes
from runner_release import GitHubSink, RunnerStorage
import shared_release_assets as shared

REPO = "rabbitlandsgame/rabbitlands-client"


def write(root, path, data):
    target = root / path
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(data)
    return target


def signed(packages, platform="windows"):
    private = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    raw = json.dumps({"schema": 2, "platform": platform, "repository": REPO, "packages": packages}).encode()
    envelope = {"payload": base64.b64encode(raw).decode(), "signature": base64.b64encode(
        private.sign(raw, padding.PKCS1v15(), hashes.SHA256())).decode()}
    public = private.public_key().public_bytes(serialization.Encoding.PEM, serialization.PublicFormat.SubjectPublicKeyInfo)
    return json.dumps(envelope).encode(), public


def test_code_changes_reuse_key_but_asset_and_policy_changes_invalidate(tmp_path):
    def git(*args):
        return subprocess.check_output(["git", *args], cwd=tmp_path).decode()
    git("init", "-b", "master")
    git("config", "user.name", "Cache test")
    git("config", "user.email", "cache@example.invalid")
    for path in ("godot-client/src/client.gd", "godot-client/src/updates/bootstrap.gd",
                 "godot-client/assets/test.png", "godot-client/assets/test.png.import",
                 "eloria-assets/maps/test/world.json", "godot-client/project.godot",
                 "godot-client/tools/setup_runner_tools.py", "godot-client/tools/asset_packages.py"):
        write(tmp_path, path, b"original")
    def snapshot():
        git("add", ".")
        git("commit", "-m", "fixture")
        return input_key(git, "HEAD", "windows")
    original = snapshot()
    write(tmp_path, "godot-client/src/client.gd", b"new game logic")
    assert snapshot() == original
    assert input_key(git, "HEAD", "linux") != original
    for path in ("godot-client/assets/test.png", "godot-client/assets/test.png.import",
                 "eloria-assets/maps/test/world.json", "godot-client/project.godot",
                 "godot-client/tools/setup_runner_tools.py", "godot-client/tools/asset_packages.py",
                 "godot-client/src/updates/bootstrap.gd", "godot-client/assets/new-model.glb"):
        write(tmp_path, path, b"changed")
        changed = snapshot()
        assert changed != original, path
        original = changed
    (tmp_path / "godot-client/assets/test.png").unlink()
    assert snapshot() != original


def test_cache_roundtrip_retains_only_products_and_verifies_signature(tmp_path):
    root, project = tmp_path / "cache", tmp_path / "project"
    cache = AssetCache(root, "asset-key")
    assert not cache.hit
    product = write(project, ".godot/imported/icon.ctex", b"imported texture")
    write(project, ".godot/global_script_class_cache.cfg", b"must not be restored")
    write(cache.vram, "texture.evt", b"encoded texture")
    write(cache.vram, "_work/scratch.dds", b"temporary DDS")
    cache.retain_imports(project)
    assert not product.exists()
    manifest, public = signed([{"id": "map-01", "files": []}])
    cache.finish(manifest)
    assert not (cache.vram / "_work").exists()
    warm = AssetCache(root, "asset-key")
    assert warm.hit and warm.packages(public, "windows", REPO)["map-01"]["files"] == []
    assert warm.packages(public, "linux", REPO) == {}
    assert warm.packages(signed([])[1], "windows", REPO) == {}
    warm.restore_imports(project)
    assert product.read_bytes() == b"imported texture"
    # Products are moved, so retaining them never adds a second full copy.
    assert not (root / "imported").exists()
    assert unique_bytes([root, project]) < 4096


@pytest.mark.parametrize("damage", ["bytes", "manifest", "key", "missing", "invalid-json"])
def test_corrupt_or_mismatched_cache_falls_back_to_cold_build(tmp_path, damage):
    cache = AssetCache(tmp_path / "cache", "original")
    write(cache.vram, "texture.evt", b"good")
    manifest, _ = signed([])
    cache.finish(manifest)
    if damage == "bytes":
        (cache.vram / "texture.evt").write_bytes(b"bad")
    elif damage == "manifest":
        (cache.root / "manifest.json").write_text("{}")
    elif damage == "missing":
        (cache.vram / "texture.evt").unlink()
    elif damage == "invalid-json":
        (cache.root / "state.json").write_text("{bad")
    warm = AssetCache(cache.root, "new" if damage == "key" else "original")
    assert not warm.hit and list(warm.root.iterdir()) == []


def test_code_only_build_skips_asset_zip_creation_and_reuses_remote_parts(tmp_path, monkeypatch):
    root = tmp_path / "runner"
    stage = root / "downloads/game"
    write(stage, "app/RabbitLands.exe", b"engine")
    write(stage, "app/RabbitLands.pck", b"old code")
    write(stage, "app/assets/actors/native/creatures/rabbit.glb", b"rabbit")
    write(stage, "eloria-assets/maps/test/world.json", b"world")
    uploaded = {}
    def accept(path, row):
        uploaded[path.name] = {"name": path.name, "state": "uploaded", "size": row["size"],
                               "digest": "sha256:" + row["sha256"]}
    old = asset_packages.build(stage, shared.base(REPO), shared=True, accept_part=accept)
    manifest, public = signed(old)
    cache = AssetCache(tmp_path / "cache", "key")
    cache.finish(manifest)
    warm = AssetCache(cache.root, "key")
    previous = warm.packages(public, "windows", REPO)
    sink = object.__new__(GitHubSink)
    sink.pool, sink.shared_previous = {"id": 1}, uploaded
    sink.reused_bytes = sink.uploaded_bytes = 0
    sink.accept = accept
    storage = RunnerStorage(root, DiskBudget([root, warm.root]), sink, warm)
    writes = []
    real_write = asset_packages.write_payload
    def archive(stage, files, output):
        writes.append([f["path"] for f in files])
        return real_write(stage, files, output)
    monkeypatch.setattr(asset_packages, "write_payload", archive)
    # No network mutation is permitted for the reused asset packages.
    monkeypatch.setattr(build_release, "upload_asset_api", lambda *a, **k: pytest.fail("Unexpected upload"))
    (stage / "app/RabbitLands.pck").write_bytes(b"new code")
    current = asset_packages.build(stage, shared.base(REPO), shared=True, accept_part=storage.accept_part,
                                  previous_packages=previous, reuse_package=storage.reuse_package)
    assert writes == [["app/RabbitLands.pck"]]
    assert warm.reused_packages == len(old) - 1
    assert sink.reused_bytes == sum(p["size"] for p in old if p["id"] != "client")
    for package in current:
        if package["id"] != "client":
            assert package == previous[package["id"]]
        for part in package["parts"]:
            assert storage.part_matches(part["url"].rsplit("/", 1)[1], part)
    # A changed asset rebuilds its own bucket, and deletion drops its inventory.
    writes.clear()
    (stage / "app/assets/actors/native/creatures/rabbit.glb").write_bytes(b"new rabbit")
    (stage / "eloria-assets/maps/test/world.json").unlink()
    storage = RunnerStorage(root, DiskBudget([root, warm.root]), sink, warm)
    changed = asset_packages.build(stage, shared.base(REPO), shared=True, accept_part=storage.accept_part,
        previous_packages={p["id"]: p for p in current}, reuse_package=storage.reuse_package)
    assert writes == [["app/assets/actors/native/creatures/rabbit.glb"]]
    assert not any(p["id"].startswith("map-") for p in changed)


def test_missing_remote_part_rebuilds_and_conflicting_completed_part_stops(tmp_path):
    sink = object.__new__(GitHubSink)
    sink.pool, sink.shared_previous = {"id": 1}, {}
    sink.reused_bytes = 0
    row = {"name": shared.name("a" * 64), "size": 5, "sha256": "a" * 64}
    assert not sink.reuse([row]) and sink.reused_bytes == 0
    sink.shared_previous[row["name"]] = {**row, "state": "uploaded", "digest": "sha256:" + "b" * 64}
    with pytest.raises(ValueError, match="conflicts"):
        sink.reuse([row])


def test_cache_links_are_not_followed(tmp_path):
    cache = AssetCache(tmp_path / "cache", "key")
    outside = write(tmp_path, "outside/keep", b"player data")
    try:
        (cache.root / "link").symlink_to(outside)
    except OSError:
        pytest.skip("Symlinks are unavailable")
    warm = AssetCache(cache.root, "key")
    assert not warm.hit and outside.read_bytes() == b"player data"


def test_generated_import_settings_restored_only_for_matching_source_and_policy(tmp_path):
    cache = AssetCache(tmp_path / "cache", "key")
    project = tmp_path / "cold"
    write(project, "assets/icon.png", b"original image")
    write(project, "assets/model.glb", b"model")
    write(project, "assets/model.glb.import", b"committed policy")
    cache.restore_imports(project)
    write(project, "assets/icon.png.import", b"generated import UID")
    write(project, "assets/model.glb.import", b"generated from committed policy")
    cache.retain_imports(project)
    cache.finish(signed([])[0])
    for condition in ("same", "source", "policy"):
        warm = AssetCache(cache.root, "key")
        fresh = tmp_path / condition
        write(fresh, "assets/icon.png", b"other image" if condition == "source" else b"original image")
        policy = b"new policy" if condition == "policy" else b"committed policy"
        write(fresh, "assets/model.glb", b"model")
        write(fresh, "assets/model.glb.import", policy)
        warm.restore_imports(fresh)
        assert (fresh / "assets/icon.png.import").is_file() == (condition != "source")
        assert (fresh / "assets/model.glb.import").read_bytes() == (
            policy if condition == "policy" else b"generated from committed policy")


def test_native_import_cache_survives_a_fresh_source_tree(tmp_path):
    from PIL import Image
    client = Path(__file__).resolve().parents[1]
    godot = client / "Godot_v4.7.2-stable_win64.exe"
    if os.name != "nt" or not godot.is_file():
        pytest.skip("Native Godot required")
    cache = AssetCache(tmp_path / "cache", "key")
    def project(name, code):
        path = tmp_path / name
        path.mkdir()
        (path / "project.godot").write_text('config_version=5\n[application]\nconfig/name="Asset Cache Test"\n'
            '[rendering]\nrenderer/rendering_method="gl_compatibility"\n')
        (path / "script.gd").write_text(code)
        Image.new("RGB", (16, 16), "green").save(path / "icon.png")
        return path
    def run(path):
        result = subprocess.run([str(godot), "--headless", "--path", str(path), "--import"],
                                capture_output=True, timeout=90)
        assert result.returncode == 0 and b"SCRIPT ERROR" not in result.stdout + result.stderr
    cold = project("cold", "extends Node\n")
    cache.restore_imports(cold)
    run(cold)
    sidecar = (cold / "icon.png.import").read_bytes()
    products = {p.name: (client_release.digest(p), p.stat().st_mtime_ns)
                for p in (cold / ".godot/imported").glob("*.ctex")}
    assert products
    cache.retain_imports(cold)
    cache.finish(signed([])[0])
    warm = AssetCache(cache.root, "key")
    fresh = project("fresh", "extends Node\nconst NEW_GAME_LOGIC = true\n")
    warm.restore_imports(fresh)
    assert (fresh / "icon.png.import").read_bytes() == sidecar
    run(fresh)
    assert {p.name: (client_release.digest(p), p.stat().st_mtime_ns)
            for p in (fresh / ".godot/imported").glob("*.ctex")} == products


def test_native_cached_updater_still_signs_and_verifies_new_release(tmp_path):
    client = Path(__file__).resolve().parents[1]
    godot = client / "Godot_v4.7.2-stable_win64.exe"
    if os.name != "nt" or not godot.is_file():
        pytest.skip("Native Windows Godot and export template required")
    template = Path(os.environ["APPDATA"]) / "Godot/export_templates/4.7.2.stable/windows_release_x86_64.exe"
    if not template.is_file():
        pytest.skip("Windows export template unavailable")
    private = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    key = tmp_path / "fixture-private.pem"
    key.write_bytes(private.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.TraditionalOpenSSL,
                                         serialization.NoEncryption()))
    identity = {"schema": 1, "commit": "a" * 40, "ancestors": ["a" * 40], "platform": "windows",
        "repository": REPO, "distribution": "github", "release_build": True,
        "public_key": private.public_key().public_bytes(serialization.Encoding.PEM,
            serialization.PublicFormat.SubjectPublicKeyInfo).decode()}
    cache = AssetCache(tmp_path / "cache", "key")
    def run(godot, args, log, timeout=120):
        result = subprocess.run([str(godot), *args], capture_output=True, timeout=timeout)
        log.write_bytes(result.stdout + result.stderr)
        assert result.returncode == 0 and b"SCRIPT ERROR" not in log.read_bytes(), log.read_text()
    first = tmp_path / "first"
    first.mkdir()
    logs = tmp_path / "logs-first"
    logs.mkdir()
    client_release.export_launcher(first, identity, godot, client, package_client.EXPORT_PRESETS,
        "Windows Desktop", run, logs, cache=cache.root / "helpers")
    previous_hash = client_release.digest(first / "RabbitLands-updater.exe")
    cache.finish(signed([])[0])
    warm = AssetCache(cache.root, "key")
    assert warm.hit
    second = tmp_path / "second"
    second.mkdir()
    logs = tmp_path / "logs-second"
    logs.mkdir()
    newer = {**identity, "commit": "b" * 40, "ancestors": ["b" * 40, "a" * 40]}
    def cached_run(godot, args, log, timeout=120):
        assert "--export-release" not in args and "--import" not in args, "Helper unnecessarily rebuilt"
        run(godot, args, log, timeout)
    client_release.export_launcher(second, newer, godot, client, package_client.EXPORT_PRESETS,
        "Windows Desktop", cached_run, logs, cache=warm.root / "helpers")
    assert client_release.digest(second / "RabbitLands-updater.exe") == previous_hash
    assert os.path.samefile(second / "RabbitLands-updater.exe", second / "RabbitLands-uninstall.exe")
    write(second, "app/RabbitLands.pck", b"new game code")
    write(second, "app/client-release.json", json.dumps(newer).encode())
    client_release.publish_artifacts(second, newer, key, godot, client, cached_run, logs, shared=True)
    # The new manifest is independently verified with the same public key.
    warm.finish((tmp_path / "second-windows.json").read_bytes())
    assert warm.packages(identity["public_key"].encode(), "windows", REPO)["client"]["files"]
