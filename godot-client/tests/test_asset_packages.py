"""Real Godot checks for selective downloads, repair, rollback and uninstall."""
import base64
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
import functools
import hashlib
import http.server
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import threading
import time

import pytest
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding, rsa

CLIENT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(CLIENT / "tools"))
import asset_packages
import client_release
import package_client


@contextmanager
def locked_directory(path):
    """Hold a real Windows directory handle without delete/rename sharing."""
    import ctypes
    from ctypes import wintypes

    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel.CreateFileW.argtypes = [wintypes.LPCWSTR, wintypes.DWORD, wintypes.DWORD,
                                  wintypes.LPVOID, wintypes.DWORD, wintypes.DWORD, wintypes.HANDLE]
    kernel.CreateFileW.restype = wintypes.HANDLE
    kernel.CloseHandle.argtypes = [wintypes.HANDLE]
    handle = kernel.CreateFileW(str(path), 1, 3, None, 3, 0x02000000, None)
    assert handle != wintypes.HANDLE(-1).value, ctypes.get_last_error()
    try:
        yield
    finally:
        kernel.CloseHandle(handle)


@contextmanager
def locked_file(path):
    """Hold a real Windows file handle that refuses rename and delete sharing."""
    import ctypes
    from ctypes import wintypes

    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel.CreateFileW.argtypes = [wintypes.LPCWSTR, wintypes.DWORD, wintypes.DWORD,
                                  wintypes.LPVOID, wintypes.DWORD, wintypes.DWORD, wintypes.HANDLE]
    kernel.CreateFileW.restype = wintypes.HANDLE
    kernel.CloseHandle.argtypes = [wintypes.HANDLE]
    # GENERIC_READ with FILE_SHARE_READ only: renaming the file now fails.
    handle = kernel.CreateFileW(str(path), 0x80000000, 1, None, 3, 0, None)
    assert handle != wintypes.HANDLE(-1).value, ctypes.get_last_error()
    try:
        yield
    finally:
        kernel.CloseHandle(handle)


DESCRIPTOR = "app/client-release.json"
UPDATE_DIRS = (".eloria-update-stage", ".eloria-update-backup", ".eloria-previous")
JOURNALS = (".eloria-update-journal.json", ".eloria-update-journal-v2.json")


def descriptor_package():
    """The package holding the release descriptor (its own one after W2-UD-01)."""
    return asset_packages.package_id(DESCRIPTOR)


def part_name(payload, package_id):
    package = next(p for p in payload["packages"] if p["id"] == package_id)
    return "/" + package["parts"][0]["url"].rsplit("/", 1)[1]


def tree(root):
    """Files and folders under the game roots, spelled as on disk, with bytes."""
    files, folders = {}, set()
    for name in ("app", "eloria-assets"):
        for folder, children, names in os.walk(root / name):
            base = Path(folder)
            folders.update((base / child).relative_to(root).as_posix() for child in children)
            for entry in names:
                files[(base / entry).relative_to(root).as_posix()] = (base / entry).read_bytes()
    return files, folders


def identities(root, paths):
    """NTFS file IDs and times: a file that was never copied or rewritten keeps both."""
    return {path: ((root / path).stat().st_ino, (root / path).stat().st_mtime_ns) for path in paths}


def assert_no_transaction(root):
    for name in UPDATE_DIRS:
        assert not (root / name).exists(), name
    for name in JOURNALS:
        assert not (root / name).exists(), name


def source(root, identity):
    (root / "app/assets/actors/native/creatures").mkdir(parents=True)
    (root / "eloria-assets/maps/landfall").mkdir(parents=True)
    (root / "app/RabbitLands.exe").write_bytes(b"unchanged engine")
    (root / "app/RabbitLands.pck").write_bytes(b"fixture pack")
    (root / "app/client-release.json").write_text(json.dumps(identity))
    (root / "app/assets/actors/native/creatures/rabbit.glb").write_bytes(b"old rabbit")
    (root / "eloria-assets/maps/landfall/world.json").write_bytes(b"unchanged world")


def manifest(stage, identity, helpers=None):
    base = f'https://github.com/{identity["repository"]}/releases/download/client-{identity["commit"]}'
    packages = asset_packages.build(stage, base)
    helpers = helpers or {kind: b"fixture bootstrap" for kind in ("updater", "uninstall")}
    rows = {}
    for kind, content in helpers.items():
        path = stage.parent / f"{stage.name}-{kind}.exe"
        path.write_bytes(content)
        rows[kind] = {"url": base + "/" + path.name, "size": path.stat().st_size,
                      "sha256": client_release.digest(path)}
    return {"schema": 2, "bootstrap_schema": 1, "commit": identity["commit"], "platform": identity["platform"],
            "repository": identity["repository"], "version": stage.name,
            "sha256": "a" * 64, "packages": packages,
            "size": sum(p["size"] for p in packages),
            "unpacked_size": sum(p["unpacked_size"] for p in packages),
            "file_count": sum(p["file_count"] for p in packages),
            "parts": [part for p in packages for part in p["parts"]], **rows}


def signed(payload, key):
    raw = json.dumps(payload, separators=(",", ":")).encode()
    return {"payload": base64.b64encode(raw).decode(), "signature": base64.b64encode(
        key.sign(raw, padding.PKCS1v15(), hashes.SHA256())).decode()}


@pytest.fixture
def fixture(tmp_path):
    godot = CLIENT / "Godot_v4.7.2-stable_win64.exe"
    if not godot.is_file():
        pytest.skip("Native Godot is required for the updater integration tests.")
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    identity = {"schema": 1, "commit": "a" * 40, "platform": "windows", "distribution": "github",
                "repository": "rabbitlandsgame/rabbitlands-client", "ancestors": ["a" * 40],
                "public_key": key.public_key().public_bytes(serialization.Encoding.PEM,
                    serialization.PublicFormat.SubjectPublicKeyInfo).decode()}
    project = tmp_path / "project"
    shutil.copytree(CLIENT / "src/updates", project / "src/updates")
    (project / "data").mkdir()
    (project / "data/client_release.json").write_text(json.dumps(identity))
    (project / "project.godot").write_text('config_version=5\n[application]\nconfig/name="Package tests"\n'
        'config/use_custom_user_dir=true\nconfig/custom_user_dir_name="RabbitLandsPackageTests"\n')
    script = project / "run.gd"
    script.write_text('''extends SceneTree
const Release = preload("res://src/updates/release.gd")
const Packages = preload("res://src/updates/package_updates.gd")
const Download = preload("res://src/updates/package_download.gd")
const Transport = preload("res://src/updates/update_transport.gd")
const Bootstrap = preload("res://src/updates/bootstrap.gd")
const Uninstall = preload("res://src/updates/uninstall.gd")
func _initialize() -> void:
    _run.call_deferred()
func _run() -> void:
    var request := Release.read_json(OS.get_cmdline_user_args()[0])
    var release := Bootstrap.verify(request.envelope, request.identity) if request.action == "bootstrap-verify" else Release.verify_manifest(request.envelope, request.identity)
    var error := str(release.get("error", ""))
    var transport := Transport.new()
    root.add_child(transport)
    var fetch := func(url: String, path: String, limit: int) -> Dictionary:
        return await transport.fetch(request.server + "/" + url.get_file(), path, limit)
    if error == "" and request.action == "recover":
        error = await transport.worker(func() -> String: return Release.recover(request.root))
    if error == "" and request.action == "update":
        var prepared_plan: Dictionary = {}
        var stop_after := OS.get_environment("RL_UPDATE_TEST_STOP_AFTER")
        var progress := func(phase: String, completed: int, _total: int, _detail := "") -> void:
            if phase == "Checking installed packages" and completed == 0:
                print("TEST_VERIFICATION_PASS")
            # Crash injection exists only in this fixture project: it ends its
            # own process right after install step k, like a power cut.
            if stop_after != "" and phase == "Installing verified game files" and completed == int(stop_after):
                OS.kill(OS.get_process_id())
        if request.get("corrupt_package", "") != "":
            for package: Dictionary in release.packages:
                if package.id == request.corrupt_package:
                    var path := Packages.package_path(Release.cache_for(request.root), package)
                    DirAccess.make_dir_recursive_absolute(path.get_base_dir())
                    var file := FileAccess.open(path, FileAccess.WRITE)
                    file.store_string("damaged cached archive")
                    file.close()
        error = await Download.prepare(request.root, release, fetch, transport.worker, progress, Callable(), prepared_plan)
        if error == "" and request.has("tamper_after_prepare"):
            var entry: Dictionary = request.tamper_after_prepare
            var file := FileAccess.open(request.root.path_join(entry.path), FileAccess.WRITE)
            file.store_string(entry.content)
            file.close()
        if error == "" and request.has("plan_root"):
            prepared_plan["checked"] = Packages.inspect(request.plan_root, release)
        if error == "":
            error = await transport.worker(func() -> String: return Packages.install(request.root, release, request.identity, progress, prepared_plan.get("checked")))
        if error == "" and request.get("reuse_consumed_plan", false):
            error = await transport.worker(func() -> String: return Packages.install(request.root, release, request.identity, progress, prepared_plan.get("checked")))
    if error == "" and request.action == "bootstrap":
        error = await Bootstrap.prepare_helpers(request.root, release, fetch, transport.worker)
        if error == "":
            error = Bootstrap.promote_helpers(request.root, release, request.identity)
    if error == "" and request.action == "uninstall":
        await Uninstall.run(root, request.root, request.get("confirm", false))
        return
    if error == "" and request.action == "script":
        var file := FileAccess.open(request.script, FileAccess.WRITE)
        file.store_string(Uninstall.windows_script(request.root, request.cache, 0, request.identity.repository))
        file.close()
    if error == "" and request.action == "promote":
        error = await transport.worker(func() -> String: return Release.promote_staged(request.root))
    Release.save_json(request.result, {"error": error})
    quit(0 if error == "" else 1)
''')
    downloads = []

    class Handler(http.server.SimpleHTTPRequestHandler):
        def do_GET(self):
            downloads.append(self.path)
            super().do_GET()

        def log_message(self, *_):
            pass

    server = http.server.ThreadingHTTPServer(("127.0.0.1", 0),
        functools.partial(Handler, directory=tmp_path))
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    stage = tmp_path / "RabbitLands-Windows-20261023-bbbbbbbbb"
    newer = {**identity, "commit": "b" * 40, "ancestors": ["b" * 40, "a" * 40]}
    source(stage, newer)
    payload = manifest(stage, newer)
    installed = tmp_path / "installed"
    source(installed, identity)
    env = {**os.environ, "APPDATA": str(tmp_path / "userdata"), "LOCALAPPDATA": str(tmp_path / "userdata")}

    def run(action="update", payload=payload, stop_after=None, **extra):
        request = tmp_path / "request.json"
        result = tmp_path / "result.json"
        result.unlink(missing_ok=True)
        request.write_text(json.dumps({"root": installed.as_posix(), "identity": identity,
            "envelope": signed(payload, key), "action": action, "result": str(result),
            "server": f"http://127.0.0.1:{server.server_port}", **extra}))
        run_env = env if stop_after is None else {**env, "RL_UPDATE_TEST_STOP_AFTER": str(stop_after)}
        completed = subprocess.run([str(godot), "--headless", "--path", str(project),
            "--script", str(script), "--", str(request)], env=run_env, text=True, capture_output=True, timeout=40)
        output = completed.stdout + completed.stderr
        assert "SCRIPT ERROR" not in output, output
        if stop_after is not None and not result.is_file():
            # The fixture ended its own process at the requested install step.
            return completed.returncode, "killed", output
        if action != "uninstall":
            assert result.is_file(), output
            return completed.returncode, json.loads(result.read_text())["error"], output
        return completed.returncode, "", output

    yield locals()
    server.shutdown()
    server.server_close()
    thread.join(timeout=3)


def test_packages_are_deterministic_and_only_changed_members_change(tmp_path):
    stage = tmp_path / "stage"
    source(stage, {"commit": "a" * 40})
    first = asset_packages.build(stage, "https://example.invalid/one")
    path = stage / "app/assets/actors/native/creatures/rabbit.glb"
    os.utime(path, (time.time() + 300, time.time() + 300))
    second_stage = tmp_path / "second"
    shutil.copytree(stage, second_stage)
    second = asset_packages.build(second_stage, "https://example.invalid/two")
    before = {p["id"]: p["sha256"] for p in first}
    assert before == {p["id"]: p["sha256"] for p in second}
    path.write_bytes(b"new rabbit")
    third_stage = tmp_path / "third"
    shutil.copytree(stage, third_stage)
    third = asset_packages.build(third_stage, "https://example.invalid/three")
    assert [p["id"] for p in third if p["sha256"] != before[p["id"]]] == [asset_packages.package_id(path.relative_to(stage).as_posix())]


def test_real_download_skips_unchanged_packages_repairs_and_removes_obsolete_files(fixture):
    f = fixture
    (f["installed"] / "app/obsolete.txt").write_text("retired")
    kept = ["app/RabbitLands.exe", "app/RabbitLands.pck", "app/assets/actors/native/creatures/rabbit.glb",
            "eloria-assets/maps/landfall/world.json"]
    before = identities(f["installed"], kept)
    code, error, output = f["run"]()
    assert code == 0 and not error, output
    assert output.count("TEST_VERIFICATION_PASS") == 1, "The locked transaction scanned installed files twice."
    # Only the client descriptor changed. The engine, actor and map stay local.
    assert f["downloads"] == [part_name(f["payload"], descriptor_package())]
    assert not (f["installed"] / "app/obsolete.txt").exists()
    # Unchanged files were neither copied nor rewritten, and nothing is kept.
    assert identities(f["installed"], kept) == before
    assert tree(f["installed"]) == tree(f["stage"])
    assert_no_transaction(f["installed"])
    f["downloads"].clear()
    assert f["run"]()[0] == 0
    assert not f["downloads"], "An up-to-date install must not redownload any ZIP."
    actor = f["installed"] / "app/assets/actors/native/creatures/rabbit.glb"
    actor.write_bytes(b"damaged actor")
    assert f["run"]()[0] == 0
    actor_package = next(p for p in f["payload"]["packages"] if p["id"].startswith("actors-"))
    assert f["downloads"] == ["/" + actor_package["parts"][0]["url"].rsplit("/", 1)[1]]
    assert actor.read_bytes() == b"old rabbit"


def test_corrupt_package_preserves_existing_install(fixture):
    f = fixture
    (f["tmp_path"] / part_name(f["payload"], descriptor_package()).lstrip("/")).write_bytes(b"broken zip")
    before = (f["installed"] / "app/client-release.json").read_bytes()
    code, error, output = f["run"]()
    assert code == 1 and ("verification" in error or "download failed" in error), output
    assert (f["installed"] / "app/client-release.json").read_bytes() == before


LOCKABLE = [DESCRIPTOR, "app/assets/actors/native/creatures/rabbit.glb", "eloria-assets/maps/landfall/world.json"]


def damage_for_replacement(f):
    """Damaged actor and map files make three replacements: first, middle and last."""
    for path in LOCKABLE[1:]:
        (f["installed"] / path).write_bytes(b"damaged " + path.encode())


@pytest.mark.skipif(os.name != "nt", reason="Native Windows file locking")
@pytest.mark.parametrize("locked", LOCKABLE)
def test_locked_live_file_reports_failure_and_rolls_back(fixture, locked):
    f = fixture
    damage_for_replacement(f)
    before = tree(f["installed"])
    with locked_file(f["installed"] / locked):
        code, error, output = f["run"]()
    assert code == 1 and "previous game was restored" in error, output
    assert "Could not move" in error and Path(locked).name in error and "error " in error
    report_path = Path(error.split("Error report: ", 1)[1])
    report = json.loads(report_path.read_text())
    assert Path(report["source"]) == f["installed"] / locked
    assert Path(report["destination"]) == f["installed"] / ".eloria-update-backup" / locked
    assert report["error_code"] != 0 and report["error"]
    assert report["commit"] == f["payload"]["commit"] and report["timestamp_utc"]
    assert report["recovery_error"] == ""
    # Replacements made before the locked file were moved back as well.
    assert tree(f["installed"]) == before
    assert_no_transaction(f["installed"])
    f["downloads"].clear()
    assert f["run"]()[0] == 0
    assert not f["downloads"], "A failed file move must retain verified downloads for retry."
    assert tree(f["installed"]) == tree(f["stage"])


@pytest.mark.skipif(os.name != "nt", reason="Native Windows folder locking")
@pytest.mark.parametrize("locked_root", ["app", "eloria-assets"])
def test_open_installed_folder_no_longer_blocks_a_file_update(fixture, locked_root):
    # A scanner holding a game folder open blocked the old two-root swap. The
    # per-file update renames files inside it and never moves the folder.
    f = fixture
    damage_for_replacement(f)
    with locked_directory(f["installed"] / locked_root):
        code, error, output = f["run"]()
    assert code == 0 and not error, output
    assert tree(f["installed"]) == tree(f["stage"])
    assert_no_transaction(f["installed"])


@pytest.mark.skipif(os.name != "nt", reason="Native Windows file locking")
def test_temporary_file_lock_is_retried(fixture):
    f = fixture
    with ThreadPoolExecutor(max_workers=1) as executor:
        with locked_file(f["installed"] / DESCRIPTOR):
            future = executor.submit(f["run"])
            deadline = time.monotonic() + 15
            while not (f["installed"] / ".eloria-update-journal-v2.json").exists():
                assert not future.done(), future.result()
                assert time.monotonic() < deadline, "The updater never reached the file moves."
                time.sleep(0.01)
            # Hold the lock through the first rename, then let the retry succeed.
            time.sleep(0.5)
            assert not future.done(), "The updater abandoned a temporary file lock."
        code, error, output = future.result(timeout=15)
    assert code == 0 and not error, output
    assert json.loads((f["installed"] / DESCRIPTOR).read_text())["commit"] == "b" * 40
    assert_no_transaction(f["installed"])


@pytest.mark.skipif(os.name != "nt", reason="Native Windows folder locking")
@pytest.mark.parametrize("locked_root", ["app", "eloria-assets"])
def test_locked_staged_folder_reports_promotion_and_restores_both_roots(fixture, locked_root):
    f = fixture
    stage = f["installed"] / ".eloria-update-stage"
    shutil.copytree(f["stage"], stage)
    (f["installed"] / ".eloria-previous").mkdir()
    journal = f["installed"] / ".eloria-update-journal.json"
    journal.write_text(json.dumps({"commit": f["payload"]["commit"], "original_roots": ["app", "eloria-assets"]}))
    before = (f["installed"] / "app/client-release.json").read_bytes()
    with locked_directory(stage / locked_root):
        code, error, output = f["run"]("promote")
    assert code == 1 and "previous game was restored" in error, output
    report = json.loads(Path(error.split("Error report: ", 1)[1]).read_text())
    assert Path(report["source"]) == stage / locked_root
    assert Path(report["destination"]) == f["installed"] / locked_root
    assert report["recovery_error"] == ""
    assert (f["installed"] / "app/client-release.json").read_bytes() == before
    assert (f["installed"] / "eloria-assets/maps/landfall/world.json").read_bytes() == b"unchanged world"
    assert not journal.exists()


def test_fresh_install_fetches_every_package_once(fixture):
    f = fixture
    f["installed"].rename(f["tmp_path"] / "previous-fixture")
    code, error, output = f["run"]()
    assert code == 0 and not error, output
    assert len(f["downloads"]) == len(f["payload"]["parts"])
    assert json.loads((f["installed"] / "app/client-release.json").read_text())["commit"] == "b" * 40
    # A fresh install keeps the two-root promotion; it leaves no empty backup.
    assert tree(f["installed"]) == tree(f["stage"])
    assert_no_transaction(f["installed"])


def test_changed_local_file_after_planning_cannot_be_promoted(fixture):
    f = fixture
    descriptor = (f["installed"] / "app/client-release.json").read_bytes()
    # Same size as the planned "old rabbit": only the commit point's check
    # (time, then hash) can notice it.
    code, error, output = f["run"](tamper_after_prepare={
        "path": "app/assets/actors/native/creatures/rabbit.glb", "content": "bad rabbit"})
    assert code == 1 and "changed while the update was being prepared" in error and "rabbit.glb" in error, output
    assert output.count("TEST_VERIFICATION_PASS") == 1
    assert (f["installed"] / "app/client-release.json").read_bytes() == descriptor
    assert_no_transaction(f["installed"])


def test_plan_for_another_installation_is_not_reused(fixture):
    f = fixture
    # The target stage already matches everything. Taking its plan for the old
    # installed root would otherwise falsely turn this update into a no-op.
    code, error, output = f["run"](plan_root=str(f["stage"]))
    assert code == 0 and not error, output
    assert output.count("TEST_VERIFICATION_PASS") == 2
    assert json.loads((f["installed"] / "app/client-release.json").read_text())["commit"] == "b" * 40


def test_a_consumed_plan_rechecks_the_installation_on_reuse(fixture):
    f = fixture
    code, error, output = f["run"](reuse_consumed_plan=True)
    assert code == 0 and not error, output
    assert output.count("TEST_VERIFICATION_PASS") == 2
    assert len(f["downloads"]) == 1


def test_single_part_download_replaces_a_damaged_cached_archive(fixture):
    f = fixture
    code, error, output = f["run"](corrupt_package=descriptor_package())
    assert code == 0 and not error, output
    assert len(f["downloads"]) == 1
    assert json.loads((f["installed"] / "app/client-release.json").read_text())["commit"] == "b" * 40


def test_map_texture_and_metadata_updates_keep_mesh_packages_reusable(tmp_path):
    stage = tmp_path / "map-stage"
    source(stage, {"commit": "a" * 40})
    pool = stage / "eloria-assets/maps/continent-v2/shared-assets/vram"
    pool.mkdir(parents=True)
    texture = pool / "first.base.evt"
    texture.write_bytes(b"texture one")
    other = next(pool / f"other-{i}.base.evt" for i in range(256)
                 if asset_packages.package_id((pool / f"other-{i}.base.evt").relative_to(stage).as_posix())
                 != asset_packages.package_id(texture.relative_to(stage).as_posix()))
    other.write_bytes(b"texture two")
    metadata = pool / "index.json"
    metadata.write_text('{"revision":1}')
    mesh = stage / "eloria-assets/maps/continent-v2/world.glb"
    mesh.write_bytes(b"stable large map geometry")
    before = {p["id"]: p["sha256"] for p in asset_packages.build(stage, "https://example.invalid/one")}
    texture.write_bytes(b"changed texture")
    metadata.write_text('{"revision":2}')
    next_stage = tmp_path / "next" / "map-stage"
    shutil.copytree(stage, next_stage)
    after = {p["id"]: p["sha256"] for p in asset_packages.build(next_stage, "https://example.invalid/two")}
    assert {name for name in before if before[name] != after[name]} == {
        asset_packages.package_id(texture.relative_to(stage).as_posix()),
        asset_packages.package_id(metadata.relative_to(stage).as_posix())}
    assert before[asset_packages.package_id(mesh.relative_to(stage).as_posix())] == after[
        asset_packages.package_id(mesh.relative_to(stage).as_posix())]


def same_package_neighbour(relative):
    """Another path that lands in the same package as relative."""
    folder, want = relative.rsplit("/", 1)[0], asset_packages.package_id(relative)
    return next(f"{folder}/neighbour-{index}.json" for index in range(4096)
                if asset_packages.package_id(f"{folder}/neighbour-{index}.json") == want)


def release_stage(f, name, change):
    """Sign another release of commit b, built from the fixture's new stage."""
    stage = f["tmp_path"] / name
    shutil.copytree(f["stage"], stage)
    change(stage)
    return stage, manifest(stage, f["newer"])


def every_operation(f):
    """A release whose install needs every operation kind and both folder swaps."""
    installed = f["installed"]
    (installed / "app/retired.txt").write_bytes(b"retired file")
    (installed / "app/data/folder").mkdir(parents=True)
    (installed / "app/data/folder/member.txt").write_bytes(b"old folder member")
    (installed / "app/data/thing").write_bytes(b"old thing file")
    if os.name == "nt":
        (installed / "app/notes").mkdir()
        (installed / "app/notes/readme.txt").write_bytes(b"same words")

    def change(stage):
        (stage / "eloria-assets/maps/landfall/world.json").write_bytes(b"new world")
        (stage / "app/notes").mkdir()
        (stage / "app/notes/added.txt").write_bytes(b"added file")
        (stage / "app/data/thing").mkdir(parents=True)
        (stage / "app/data/thing/member.txt").write_bytes(b"new folder member")
        (stage / "app/data/folder").write_bytes(b"new folder file")
        if os.name == "nt":
            (stage / "app/notes/ReadMe.txt").write_bytes(b"same words")

    stage, payload = release_stage(f, "RabbitLands-Windows-20261102-ccccccccc", change)
    # retire 3 (one step each), replace descriptor + map (+ case rename), add 3.
    steps = 3 + 2 * (2 + (os.name == "nt")) + 3
    return stage, payload, steps


def test_a_crash_after_any_install_step_restores_the_previous_install(fixture):
    f = fixture
    installed = f["installed"]
    stage, payload, steps = every_operation(f)
    pristine = f["tmp_path"] / "pristine"
    shutil.copytree(installed, pristine)
    expected = tree(stage)
    step = 0
    while True:
        shutil.rmtree(installed)
        shutil.copytree(pristine, installed)
        before = tree(installed)
        moved = identities(installed, before[0])
        code, error, output = f["run"](payload=payload, stop_after=step)
        if error != "killed":
            assert code == 0 and not error, output
            break
        assert (installed / ".eloria-update-journal-v2.json").is_file(), step
        code, error, output = f["run"]("recover", payload)
        assert code == 0 and not error, output
        # The same files, names, bytes and folders; originals were moved back,
        # never rewritten.
        assert tree(installed) == before, step
        assert identities(installed, before[0]) == moved, step
        assert_no_transaction(installed)
        f["downloads"].clear()
        code, error, output = f["run"](payload=payload)
        assert code == 0 and not error, output
        assert not f["downloads"], "Verified downloads must survive an interrupted install."
        assert tree(installed) == expected, step
        assert_no_transaction(installed)
        step += 1
    assert step == steps + 1, "The install did not take the expected steps."
    assert tree(installed) == expected
    assert_no_transaction(installed)


@pytest.mark.parametrize("point", ["middle", "last"])
def test_a_journal_that_lost_its_bytes_still_restores_every_original(fixture, point):
    # A power cut can lose the journal's bytes yet keep the renames made after
    # it. Recovery must not stop for good (setup recovers through the same
    # call): every original comes back from the backup, files the update added
    # may stay, and the retry lands the release exactly.
    f = fixture
    installed = f["installed"]
    stage, payload, steps = every_operation(f)
    expected = tree(stage)
    before = tree(installed)
    moved = identities(installed, before[0])
    code, error, output = f["run"](payload=payload, stop_after=steps // 2 if point == "middle" else steps)
    assert error == "killed", output
    journal = installed / ".eloria-update-journal-v2.json"
    journal.write_bytes(b"\0" * journal.stat().st_size)
    code, error, output = f["run"]("recover", payload)
    assert code == 0 and not error, output
    files, _ = tree(installed)
    added = set(expected[0]) - set(before[0])
    assert {path: data for path, data in files.items() if path not in added} == before[0]
    assert set(files) - set(before[0]) <= added
    assert identities(installed, before[0]) == moved, "Originals must be moved back, not rewritten."
    assert_no_transaction(installed)
    f["downloads"].clear()
    code, error, output = f["run"](payload=payload)
    assert code == 0 and not error, output
    assert not f["downloads"], "Verified downloads must survive an interrupted install."
    assert tree(installed) == expected
    assert_no_transaction(installed)


def test_only_changed_members_are_staged_and_unchanged_files_keep_their_identity(fixture):
    f = fixture
    world = "eloria-assets/maps/landfall/world.json"
    neighbour = same_package_neighbour(world)
    (f["installed"] / neighbour).write_bytes(b"stable neighbour")

    def change(stage):
        (stage / neighbour).write_bytes(b"stable neighbour")
        (stage / world).write_bytes(b"new world")

    stage, payload = release_stage(f, "RabbitLands-Windows-20261102-ddddddddd", change)
    package = next(p for p in payload["packages"] if p["id"] == asset_packages.package_id(world))
    assert {neighbour, world} <= {entry["path"] for entry in package["files"]}
    kept = [neighbour, "app/RabbitLands.exe", "app/RabbitLands.pck", "app/assets/actors/native/creatures/rabbit.glb"]
    before = identities(f["installed"], kept)
    # Stopped once the journal is written: the stage holds only changed members.
    code, error, output = f["run"](payload=payload, stop_after=0)
    assert error == "killed", output
    staged = f["installed"] / ".eloria-update-stage"
    assert {p.relative_to(staged).as_posix() for p in staged.rglob("*") if p.is_file()} == {DESCRIPTOR, world}
    assert sorted(f["downloads"]) == sorted([part_name(payload, descriptor_package()), part_name(payload, package["id"])])
    code, error, output = f["run"](payload=payload)
    assert code == 0 and not error, output
    # The neighbour shares the downloaded package but was neither unpacked
    # nor moved: same file ID and time.
    assert identities(f["installed"], kept) == before
    assert tree(f["installed"]) == tree(stage)
    assert_no_transaction(f["installed"])


@pytest.mark.skipif(os.name != "nt", reason="Case-insensitive file names")
def test_a_case_only_rename_lands(fixture):
    f = fixture
    (f["installed"] / "app/notes").mkdir()
    (f["installed"] / "app/notes/readme.txt").write_bytes(b"same words")

    def change(stage):
        (stage / "app/notes").mkdir()
        (stage / "app/notes/ReadMe.txt").write_bytes(b"same words")

    stage, payload = release_stage(f, "RabbitLands-Windows-20261102-eeeeeeeee", change)
    code, error, output = f["run"](payload=payload)
    assert code == 0 and not error, output
    assert os.listdir(f["installed"] / "app/notes") == ["ReadMe.txt"]
    assert tree(f["installed"]) == tree(stage)
    f["downloads"].clear()
    assert f["run"](payload=payload)[0] == 0 and not f["downloads"], "The new spelling was not recognized."


def test_an_older_updaters_interrupted_promotion_is_recovered_then_updated(fixture):
    f = fixture
    installed = f["installed"]
    before = tree(installed)
    # The two-root journal of an older updater, stopped between its renames.
    (installed / ".eloria-previous").mkdir()
    (installed / "app").rename(installed / ".eloria-previous/app")
    shutil.copytree(f["stage"] / "app", installed / "app")
    (installed / ".eloria-update-journal.json").write_text(json.dumps(
        {"commit": "b" * 40, "original_roots": ["app", "eloria-assets"]}))
    code, error, output = f["run"]("recover")
    assert code == 0 and not error, output
    assert tree(installed) == before
    assert not (installed / ".eloria-update-journal.json").exists()
    code, error, output = f["run"]()
    assert code == 0 and not error, output
    assert tree(installed) == tree(f["stage"])
    assert_no_transaction(installed)


def test_an_update_over_an_older_updaters_backup_removes_it(fixture):
    f = fixture
    installed = f["installed"]
    for name in ("app", "eloria-assets"):
        shutil.copytree(installed / name, installed / ".eloria-previous" / name)
    code, error, output = f["run"]()
    assert code == 0 and not error, output
    assert tree(installed) == tree(f["stage"])
    assert_no_transaction(installed)


def test_uninstall_requires_confirmation_and_refuses_steam(fixture):
    f = fixture
    assert f["run"]("uninstall")[0] == 1
    path = f["installed"] / "app/client-release.json"
    steam = {**f["identity"], "distribution": "steam"}
    path.write_text(json.dumps(steam))
    assert f["run"]("uninstall", confirm=True)[0] == 1
    assert path.is_file()


@pytest.mark.parametrize("mutation", ["path", "duplicate", "url", "size"])
def test_signed_but_unsafe_inventories_are_rejected(fixture, mutation):
    f = fixture
    payload = json.loads(json.dumps(f["payload"]))
    package = payload["packages"][0]
    if mutation == "path":
        package["files"][0]["path"] = "app/../outside"
    elif mutation == "duplicate":
        package["files"].append(package["files"][0])
    elif mutation == "url":
        package["parts"][0]["url"] = "https://example.invalid/evil.zip"
    else:
        package["size"] += 1
    assert f["run"]("verify", payload)[0] == 1
    assert not f["downloads"]


def test_bootstrap_hashes_are_verified_before_replacement(fixture):
    f = fixture
    for kind in ("updater", "uninstall"):
        (f["installed"] / f"RabbitLands-{kind}.exe").write_bytes(b"old helper")
    assert f["run"]("bootstrap")[0] == 0
    assert (f["installed"] / "RabbitLands-updater.exe").read_bytes() == b"fixture bootstrap"
    # Both executables have the same hash: only one network transfer is needed.
    assert len(f["downloads"]) == 1


def test_bootstrap_can_upgrade_before_reading_a_future_game_format(fixture):
    f = fixture
    payload = {**f["payload"], "schema": 999, "packages": []}
    assert f["run"]("bootstrap-verify", payload)[0] == 0
    assert f["run"]("verify", payload)[0] == 1
    payload["updater"] = {**payload["updater"], "url": "https://example.invalid/helper.exe"}
    assert f["run"]("bootstrap-verify", payload)[0] == 1


@pytest.mark.parametrize("shared", [False, True])
@pytest.mark.parametrize("platform", ["windows", "linux"])
def test_publication_signs_package_inventory_and_collects_all_installer_assets(fixture, shared, platform):
    import build_release
    f = fixture
    stage = f["tmp_path"] / f"RabbitLands-{platform.title()}-20261024-bbbbbbbbb"
    shutil.copytree(f["stage"], stage)
    metadata = json.loads((stage / "app/client-release.json").read_text())
    metadata["platform"] = platform
    (stage / "app/client-release.json").write_text(json.dumps(metadata))
    if platform == "linux":
        (stage / "app/RabbitLands.exe").rename(stage / "app/RabbitLands.x86_64")
    (stage / package_client.MARKER).write_text("b" * 40)
    for kind in ("updater", "uninstall"):
        extension = "exe" if platform == "windows" else "x86_64"
        (stage / f"RabbitLands-{kind}.{extension}").write_bytes(b"test native bootstrap")
    logs = f["tmp_path"] / "publication-logs"
    shutil.copytree(f["project"], logs / "updater-project")
    private = f["tmp_path"] / "test-only-private.pem"
    private.write_bytes(f["key"].private_bytes(serialization.Encoding.PEM,
        serialization.PrivateFormat.PKCS8, serialization.NoEncryption()))

    def run_godot(godot, args, log, timeout):
        result = subprocess.run([str(godot), *args], env=f["env"], capture_output=True, text=True, timeout=timeout)
        log.write_text(result.stdout + result.stderr)
        assert result.returncode == 0 and "SCRIPT ERROR" not in log.read_text(), log.read_text()

    outputs = client_release.publish_artifacts(stage, metadata, private, f["godot"], CLIENT, run_godot, logs, shared=shared)
    manifest_path = stage.parent / f"{stage.name}-{platform}.json"
    envelope = json.loads(manifest_path.read_text())
    payload = json.loads(base64.b64decode(envelope["payload"]))
    assert payload["schema"] == 2 and payload["bootstrap_schema"] == 1
    assert (stage.parent / f"RabbitLands-{platform}.json").read_bytes() == manifest_path.read_bytes()
    setup = stage.parent / f"{stage.name}-setup.exe"
    setup.write_bytes(b"test setup")
    receipt = {"schema": 1, "mode": "online", "commit": metadata["commit"], "manifest": manifest_path.name,
        "parts": [{"name": p["url"].rsplit("/", 1)[1], "size": p["size"], "sha256": p["sha256"]} for p in payload["parts"]]}
    (stage.parent / f"{stage.name}-setup-downloads.json").write_text(json.dumps(receipt))
    if platform == "linux" and not shared:
        (stage.parent / f"{stage.name}.tar.gz").write_bytes(b"portable archive fixture")
    assets, policy, actual_stage = build_release.platform_assets(stage.parent, metadata["commit"], platform)
    assert actual_stage == stage
    assert {p.name for p in outputs if p.suffix != ".txt" and "server-policy" not in p.name} <= {p.name for p in assets}
    assert all(p.is_file() for p in assets)
    if platform == "windows":
        assert setup in assets
    elif shared:
        assert any(p.name.endswith("-download.sh") for p in assets)
        assert not any(".tar.gz" in p.name for p in assets)


def export_test_updater(f, version, platform="windows", launcher_methods=""):
    """Exports the production launcher with a fixture transport. `launcher_methods`
    is GDScript appended to the fixture launcher (test seams only)."""
    stage = f["tmp_path"] / ("helper-" + platform + "-" + version)
    logs = stage / "logs"
    logs.mkdir(parents=True)
    identity = {**f["identity"], "platform": platform}

    def run_godot(godot, args, log, timeout):
        project = logs / "updater-project"
        # The production launcher and verifier stay intact. Only the transport
        # endpoint is redirected to this test's local HTTP server after signature
        # verification; there is no runtime endpoint override in shipped builds.
        (project / "fixture_transport.gd").write_text('extends "res://src/updates/update_transport.gd"\n'
            'func fetch(url: String, path := "", limit := Release.MAX_MANIFEST_BYTES) -> Dictionary:\n'
            '\tvar base: String = Release.read_json("res://data/test-server.json").url\n'
            '\treturn await super.fetch(base + "/" + url.get_file(), path, limit)\n')
        (project / "fixture_launcher.gd").write_text('extends "res://src/updates/launcher.gd"\n'
            'func _new_transport() -> Node:\n\treturn load("res://fixture_transport.gd").new()\n'
            'func _backup_cleanup_delay_msec() -> int:\n\treturn 0\n'
            'func _ready() -> void:\n'
            '\tvar args := OS.get_cmdline_user_args()\n'
            '\tvar index := args.find("--root")\n'
            '\tif index >= 0:\n'
            '\t\tvar file := FileAccess.open(args[index + 1].path_join("updater-test-version.txt"), FileAccess.WRITE)\n'
            '\t\tif file != null:\n'
            '\t\t\tfile.store_string(Release.read_json("res://data/test-version.json").version)\n'
            '\t\t\tfile.close()\n'
            '\tsuper._ready()\n' + launcher_methods)
        (project / "data/test-version.json").write_text(json.dumps({"version": version}))
        (project / "data/test-server.json").write_text(json.dumps({"url": f'http://127.0.0.1:{f["server"].server_port}'}))
        scene = project / "main.tscn"
        scene.write_text(scene.read_text().replace('path="res://src/updates/launcher.gd"', 'path="res://fixture_launcher.gd"'))
        completed = subprocess.run([str(godot), *args], capture_output=True, text=True, timeout=timeout)
        log.write_text(completed.stdout + completed.stderr)
        assert completed.returncode == 0 and "SCRIPT ERROR" not in log.read_text(), log.read_text()

    client_release.export_launcher(stage, identity, f["godot"], CLIENT, package_client.EXPORT_PRESETS,
        package_client.PLATFORMS[platform]["preset"], run_godot, logs)
    return stage / ("RabbitLands-updater.exe" if platform == "windows" else "RabbitLands-updater.x86_64")


@pytest.mark.parametrize("shared", [False, True])
def test_exported_updater_replaces_itself_then_installs_and_uninstalls(fixture, shared):
    if os.name != "nt":
        pytest.skip("This check exercises Windows executable locking and its native uninstaller.")
    f = fixture
    old = export_test_updater(f, "old")
    new = export_test_updater(f, "new")
    payload = json.loads(json.dumps(f["payload"]))
    for kind in ("updater", "uninstall"):
        row = payload[kind]
        path = f["tmp_path"] / row["url"].rsplit("/", 1)[1]
        shutil.copyfile(new, path)
        row.update(size=path.stat().st_size, sha256=client_release.digest(path))
        shutil.copyfile(old, f["installed"] / f"RabbitLands-{kind}.exe")
    if shared:
        from test_shared_release_assets import shared_payload
        payload = shared_payload({**f, "payload": payload})
        payload["launch_args"] = ["--server=draft.example", "--port=2002"]
    envelope = signed(payload, f["key"])
    (f["tmp_path"] / "RabbitLands-windows.json").write_text(json.dumps({} if shared else envelope))
    pinned = f["tmp_path"] / "pinned-installer.json"
    pinned.write_text(json.dumps(envelope))
    # Leftovers of an earlier handover: the replacement updater prunes the
    # staged helper this handover does not name, and keeps a recent copy.
    cache = (f["tmp_path"] / "userdata/Godot/app_userdata/Eloria/client-updates"
             / hashlib.sha256(f["installed"].as_posix().encode()).hexdigest()[:24])
    stale_helper = cache / "bootstrap" / ("0" * 64)
    stale_helper.parent.mkdir(parents=True)
    stale_helper.write_bytes(b"stale staged helper")
    recent_copy = cache / "handoff-999999999.exe"
    recent_copy.write_bytes(b"recent handover copy")
    log = f["tmp_path"] / "native-updater.log"
    with log.open("w") as output:
        process = subprocess.Popen([str(f["installed"] / "RabbitLands-updater.exe"), "--headless",
            "--", "--root", str(f["installed"]), "--update-only",
            *(["--install-manifest", str(pinned)] if shared else [])], env=f["env"], stdout=output, stderr=subprocess.STDOUT)
    assert process.wait(timeout=30) == 0, log.read_text()
    pinned.unlink() # A shell installer's temporary files disappear at this handoff.
    deadline = time.monotonic() + 40
    while True:
        descriptor = json.loads((f["installed"] / "app/client-release.json").read_text())
        proof = f["installed"] / "updater-test-version.txt"
        if (descriptor["commit"] == "b" * 40 and proof.is_file() and proof.read_text() == "new"
                and not (f["installed"] / ".eloria-launcher-lock").exists()):
            break
        assert time.monotonic() < deadline, log.read_text() + "\n" + str(f["downloads"])
        time.sleep(0.1)
    for kind in ("updater", "uninstall"):
        assert client_release.digest(f["installed"] / f"RabbitLands-{kind}.exe") == client_release.digest(new)
    assert sorted(p.name for p in (cache / "bootstrap").iterdir()) == [client_release.digest(new)]
    assert recent_copy.is_file(), "A handover copy inside its grace period was removed."
    assert not (f["installed"] / ".rabbitlands-bootstrap-previous").exists(), "The running installed updater kept the helpers it replaced."
    assert_no_transaction(f["installed"])
    updater_download = "/" + payload["updater"]["url"].rsplit("/", 1)[1]
    client_part = next(p for p in payload["packages"] if p["id"] == descriptor_package())["parts"][0]
    client_download = "/" + client_part["url"].rsplit("/", 1)[1]
    assert f["downloads"].count(updater_download) == 1
    assert f["downloads"].count(client_download) == 1
    assert set(f["downloads"]) <= {"/RabbitLands-windows.json", updater_download, client_download}
    if shared:
        assert "/RabbitLands-windows.json" not in f["downloads"], "Pinned draft install looked up the public release"
        assert json.loads((f["installed"] / "launcher-defaults.json").read_text())["args"] == payload["launch_args"]
    settings = f["tmp_path"] / "userdata/player-settings.cfg"
    settings.parent.mkdir(exist_ok=True)
    settings.write_text("keep my settings")
    junction = f["installed"] / "external-settings"
    assert settings.parent.resolve().is_relative_to(f["tmp_path"].resolve())
    literal = lambda p: "'" + str(p).replace("'", "''") + "'"
    linked = subprocess.run(["powershell.exe", "-NoProfile", "-NonInteractive", "-Command",
        "New-Item -ItemType Junction -Path " + literal(junction) + " -Target " + literal(settings.parent) + " | Out-Null"],
        capture_output=True, text=True, timeout=15)
    assert linked.returncode == 0, linked.stdout + linked.stderr
    # The actual installed uninstaller removes its running executable via a
    # hidden waiting native helper, without touching settings outside the root.
    result = subprocess.run([str(f["installed"] / "RabbitLands-uninstall.exe"), "--headless", "--",
        "--root", str(f["installed"]), "--confirm"], env=f["env"], capture_output=True, text=True, timeout=15)
    assert result.returncode == 0, result.stdout + result.stderr
    deadline = time.monotonic() + 20
    while f["installed"].exists():
        assert time.monotonic() < deadline, "Native uninstall did not remove its installation."
        time.sleep(0.1)
    assert settings.read_text() == "keep my settings"


def test_linux_export_runs_native_uninstaller_and_keeps_settings(fixture):
    if os.name != "nt" or not shutil.which("wsl.exe"):
        pytest.skip("This host check needs WSL Ubuntu-24.04.")
    f = fixture
    helper = export_test_updater(f, "linux", "linux")
    installed = f["installed"]
    descriptor = {**f["identity"], "platform": "linux"}
    (installed / "app/client-release.json").write_text(json.dumps(descriptor))
    binary = installed / "RabbitLands-uninstall.x86_64"
    shutil.copyfile(helper, binary)
    settings = f["tmp_path"] / "player-settings.cfg"
    settings.write_text("keep Linux settings")
    command = ["wsl.exe", "-d", "Ubuntu-24.04", "--exec", "env",
        "XDG_DATA_HOME=" + package_client.wsl_path(f["tmp_path"] / "linux-userdata"),
        package_client.wsl_path(binary), "--headless", "--", "--root", package_client.wsl_path(installed), "--confirm"]
    result = subprocess.run(command, capture_output=True, text=True, timeout=25)
    assert result.returncode == 0 and "SCRIPT ERROR" not in result.stdout + result.stderr, result.stdout + result.stderr
    assert not installed.exists()
    assert settings.read_text() == "keep Linux settings"


def test_inno_single_file_setup_uses_packages_for_fresh_install_and_repair(fixture):
    f = fixture
    iscc = package_client.find_iscc(None)
    if os.name != "nt" or not iscc:
        pytest.skip("Inno Setup 6 is needed for this native integration check.")
    stage = f["stage"]
    logs = f["tmp_path"] / "inno-logs"
    logs.mkdir()
    branding = stage / "app/assets/branding"
    branding.mkdir(parents=True)
    for name in ("rabbitlands-icon.ico", "rabbitlands-mark-64.png"):
        shutil.copyfile(CLIENT / "assets/branding" / name, branding / name)
    manifest_path = stage.parent / f"{stage.name}-windows.json"
    manifest_path.write_text(json.dumps(signed(f["payload"], f["key"])))

    def run_godot(godot, args, log, timeout):
        result = subprocess.run([str(godot), *args], capture_output=True, text=True, timeout=timeout)
        log.write_text(result.stdout + result.stderr)
        assert result.returncode == 0 and "SCRIPT ERROR" not in log.read_text(), log.read_text()

    helper = client_release.export_installer_helper(stage, f["godot"], CLIENT,
        package_client.EXPORT_PRESETS, run_godot, logs)
    # Only Inno's download URLs are redirected. The embedded helper still
    # verifies the original GitHub-pinned, signed package inventory.
    payload = json.loads(json.dumps(f["payload"]))
    for package in payload["packages"]:
        for part in package["parts"]:
            part["url"] = f'http://127.0.0.1:{f["server"].server_port}/' + part["url"].rsplit("/", 1)[1]
    script = package_client.online_installer_script(stage, helper, "test", [], payload)
    script = script.replace('AppId=' + package_client.INSTALLER_APP_ID.replace('{', '{{'),
        'AppId=RabbitLandsPackageInstallerTest\nUninstallable=no')
    script = script.split('[Icons]')[0] + '[Code]' + script.split('[Code]', 1)[1]
    (stage.parent / f"{stage.name}-online-install.txt").write_text("Isolated package installer test.")
    iss = logs / "setup.iss"
    iss.write_text(script, encoding="utf-8-sig")
    result = subprocess.run([str(iscc), str(iss)], capture_output=True, text=True, timeout=120)
    assert result.returncode == 0, result.stdout + result.stderr
    setup = stage.parent / f"{stage.name}-setup.exe"
    assert setup.is_file() and not list(stage.parent.glob(f"{stage.name}-setup-*.bin"))
    installed = f["tmp_path"] / "setup-installed"
    command = [str(setup), "/VERYSILENT", "/SUPPRESSMSGBOXES", "/NORESTART", "/SP-",
        f"/DIR={installed}", f'/LOG={logs / "setup.log"}']

    def install():
        result = subprocess.run(command, env=f["env"], capture_output=True, text=True, timeout=45)
        assert result.returncode == 0, (logs / "setup.log").read_text(errors="replace")

    install()
    assert len(f["downloads"]) == len(f["payload"]["parts"])
    assert json.loads((installed / "app/client-release.json").read_text())["commit"] == "b" * 40
    f["downloads"].clear()
    install()
    assert not f["downloads"], "Setup repair downloaded unchanged packages."
    (installed / "app/assets/actors/native/creatures/rabbit.glb").write_bytes(b"damage")
    install()
    actor = next(p for p in f["payload"]["packages"] if p["id"].startswith("actors-"))
    assert f["downloads"] == ["/" + actor["parts"][0]["url"].rsplit("/", 1)[1]]


def test_downloaded_updater_launches_game_with_loose_assets(fixture):
    f = fixture
    updater = export_test_updater(f, "launch-probe")
    project = f["tmp_path"] / "probe-project"
    project.mkdir()
    shutil.copytree(CLIENT / "assets/branding", project / "assets/branding")
    (project / "project.godot").write_text('config_version=5\n[application]\nconfig/name="Game probe"\nrun/main_scene="res://main.tscn"\n[rendering]\nrenderer/rendering_method="gl_compatibility"\n')
    (project / "main.gd").write_text('extends Node\nfunc _ready() -> void:\n'
        '\tvar path := ProjectSettings.globalize_path("res://assets/actors/native/creatures/rabbit.glb")\n'
        '\tvar file := FileAccess.open(OS.get_environment("ELORIA_INSTALL_ROOT").path_join("game-probe.json"), FileAccess.WRITE)\n'
        '\tfile.store_string(JSON.stringify({"path": path, "content": FileAccess.get_file_as_string(path)}))\n'
        '\tfile.close()\n\tget_tree().quit()\n')
    (project / "main.tscn").write_text('[gd_scene load_steps=2 format=3]\n[ext_resource type="Script" path="res://main.gd" id="1"]\n[node name="Probe" type="Node"]\nscript=ExtResource("1")\n')
    (project / "export_presets.cfg").write_text(package_client.EXPORT_PRESETS)
    stage = f["tmp_path"] / "RabbitLands-Windows-20261025-bbbbbbbbb"
    shutil.copytree(f["stage"], stage)
    for args in (["--headless", "--path", str(project), "--import"],
                 ["--headless", "--path", str(project), "--export-release", "Windows Desktop", str(stage / "app/RabbitLands.exe")]):
        result = subprocess.run([str(f["godot"]), *args], capture_output=True, text=True, timeout=90)
        assert result.returncode == 0 and "SCRIPT ERROR" not in result.stdout + result.stderr, result.stdout + result.stderr
    metadata = json.loads((stage / "app/client-release.json").read_text())
    payload = manifest(stage, metadata, {kind: updater.read_bytes() for kind in ("updater", "uninstall")})
    (f["tmp_path"] / "RabbitLands-windows.json").write_text(json.dumps(signed(payload, f["key"])))
    for kind in ("updater", "uninstall"):
        shutil.copyfile(updater, f["installed"] / f"RabbitLands-{kind}.exe")
    result = subprocess.run([str(f["installed"] / "RabbitLands-updater.exe"), "--headless", "--", "--root", str(f["installed"])],
        env=f["env"], capture_output=True, text=True, timeout=40)
    assert result.returncode == 0, result.stdout + result.stderr
    probe = json.loads((f["installed"] / "game-probe.json").read_text())
    assert probe["content"] == "old rabbit", probe


def test_updated_game_start_removes_previous_installation_backup(fixture):
    f = fixture
    updater = export_test_updater(f, "backup-probe")
    project = f["tmp_path"] / "backup-probe-project"
    project.mkdir()
    shutil.copytree(CLIENT / "assets/branding", project / "assets/branding")
    # Same user folder as the real game: it records its running lease where
    # the launcher looks, then waits to see whether the backup is removed.
    (project / "project.godot").write_text('config_version=5\n[application]\nconfig/name="Backup probe"\nrun/main_scene="res://main.tscn"\n'
        'config/use_custom_user_dir=true\nconfig/custom_user_dir_name="Godot/app_userdata/Eloria"\n'
        '[rendering]\nrenderer/rendering_method="gl_compatibility"\n')
    (project / "main.gd").write_text('extends Node\nfunc _ready() -> void:\n'
        '\tvar root := OS.get_executable_path().get_base_dir().get_base_dir().simplify_path()\n'
        '\tvar backup := root.path_join(".eloria-previous")\n'
        '\tvar had_backup := DirAccess.dir_exists_absolute(backup)\n'
        '\tvar cache := ProjectSettings.globalize_path("user://client-updates/" + root.sha256_text().left(24))\n'
        '\tDirAccess.make_dir_recursive_absolute(cache)\n'
        '\tvar lease := cache.path_join("running-%d.json" % OS.get_process_id())\n'
        '\tvar file := FileAccess.open(lease, FileAccess.WRITE)\n'
        '\tfile.store_string(JSON.stringify({"pid": OS.get_process_id()}))\n'
        '\tfile.close()\n'
        '\tvar deadline := Time.get_ticks_msec() + 20000\n'
        '\twhile DirAccess.dir_exists_absolute(backup) and Time.get_ticks_msec() < deadline:\n'
        '\t\tawait get_tree().create_timer(0.25).timeout\n'
        '\tvar live := FileAccess.get_file_as_string(root.path_join("app/assets/actors/native/creatures/rabbit.glb"))\n'
        '\tfile = FileAccess.open(root.path_join("game-probe.json"), FileAccess.WRITE)\n'
        '\tfile.store_string(JSON.stringify({"had_backup": had_backup, "removed_while_running": not DirAccess.dir_exists_absolute(backup), "live": live}))\n'
        '\tfile.close()\n'
        '\tDirAccess.remove_absolute(lease)\n\tget_tree().quit()\n')
    (project / "main.tscn").write_text('[gd_scene load_steps=2 format=3]\n[ext_resource type="Script" path="res://main.gd" id="1"]\n[node name="Probe" type="Node"]\nscript=ExtResource("1")\n')
    (project / "export_presets.cfg").write_text(package_client.EXPORT_PRESETS)
    stage = f["tmp_path"] / "RabbitLands-Windows-20261026-bbbbbbbbb"
    shutil.copytree(f["stage"], stage)
    for args in (["--headless", "--path", str(project), "--import"],
                 ["--headless", "--path", str(project), "--export-release", "Windows Desktop", str(stage / "app/RabbitLands.exe")]):
        result = subprocess.run([str(f["godot"]), *args], capture_output=True, text=True, timeout=90)
        assert result.returncode == 0 and "SCRIPT ERROR" not in result.stdout + result.stderr, result.stdout + result.stderr
    metadata = json.loads((stage / "app/client-release.json").read_text())
    payload = manifest(stage, metadata, {kind: updater.read_bytes() for kind in ("updater", "uninstall")})
    (f["tmp_path"] / "RabbitLands-windows.json").write_text(json.dumps(signed(payload, f["key"])))
    for kind in ("updater", "uninstall"):
        shutil.copyfile(updater, f["installed"] / f"RabbitLands-{kind}.exe")
    previous = f["installed"] / ".eloria-previous"

    def leave_old_updater_backup():
        # What an older updater leaves after its two-root update.
        for name in ("app", "eloria-assets"):
            shutil.copytree(f["tmp_path"] / "previous-roots" / name, previous / name)

    shutil.copytree(f["installed"] / "app", f["tmp_path"] / "previous-roots/app")
    shutil.copytree(f["installed"] / "eloria-assets", f["tmp_path"] / "previous-roots/eloria-assets")
    leave_old_updater_backup()
    result = subprocess.run([str(f["installed"] / "RabbitLands-updater.exe"), "--headless", "--", "--root", str(f["installed"])],
        env=f["env"], capture_output=True, text=True, timeout=60)
    assert result.returncode == 0, result.stdout + result.stderr
    probe = json.loads((f["installed"] / "game-probe.json").read_text())
    # A per-file update needs no whole-game backup: the old updater's one was
    # removed before staging, and the update kept none of its own.
    assert probe == {"had_backup": False, "removed_while_running": True, "live": "old rabbit"}, probe
    assert json.loads((f["installed"] / "app/client-release.json").read_text())["commit"] == "b" * 40
    assert_no_transaction(f["installed"])
    # Launch-only starts still remove a backup an older updater left: the
    # started game sees it removed while the launcher holds the lock.
    leave_old_updater_backup()
    result = subprocess.run([str(f["installed"] / "RabbitLands-updater.exe"), "--headless", "--", "--root", str(f["installed"]), "--launch-only"],
        env=f["env"], capture_output=True, text=True, timeout=60)
    assert result.returncode == 0, result.stdout + result.stderr
    probe = json.loads((f["installed"] / "game-probe.json").read_text())
    assert probe == {"had_backup": True, "removed_while_running": True, "live": "old rabbit"}, probe
    assert_no_transaction(f["installed"])
    assert "Removed the previous installation backup" in result.stdout, result.stdout
