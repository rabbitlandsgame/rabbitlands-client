"""Exercise the online setup helper against signed, local miniature downloads."""
import base64
import functools
import http.server
import json
import os
from pathlib import Path
import subprocess
import shutil
import sys
import time
import threading
from types import SimpleNamespace

import pytest
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding, rsa

CLIENT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(CLIENT / "tools"))
import client_release
from release_storage import PartWriter
import package_client


def online_fixture(tmp_path, streamed=False):
    godot = CLIENT / "Godot_v4.7.2-stable_win64.exe"
    if not godot.is_file() or os.name != "nt":
        pytest.skip("Run this focused integration check on the Windows packaging host.")
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    identity = {"schema": 1, "commit": "a" * 40, "platform": "windows", "ancestors": [],
        "repository": "rabbitlandsgame/rabbitlands-client",
        "public_key": key.public_key().public_bytes(serialization.Encoding.PEM,
            serialization.PublicFormat.SubjectPublicKeyInfo).decode()}
    stage = tmp_path / "fixture"
    (stage / "app").mkdir(parents=True)
    (stage / "eloria-assets").mkdir()
    (stage / "app/client-release.json").write_text(json.dumps(identity))
    (stage / "app/RabbitLands.exe").write_bytes(b"fixture game, never executed")
    (stage / "app/RabbitLands.pck").write_bytes(b"fixture pack")
    (stage / "eloria-assets/world.json").write_bytes(b"{}")
    parts = tmp_path / "parts"
    parts.mkdir()
    archive = parts / "fixture.zip"
    if streamed:
        # The hosted runner writes a non-seekable ZIP directly into parts.
        # Exercise Godot's actual reader with that data-descriptor/ZIP64 format.
        with PartWriter(archive, "https://github.com/rabbitlandsgame/rabbitlands-client/releases/download/test", 1024) as writer:
            count, unpacked = client_release.build_payload(stage, writer)
        payload_parts, payload_size, payload_hash = writer.parts, writer.size, writer.sha256
    else:
        count, unpacked = client_release.build_payload(stage, archive)
        payload_size, payload_hash = archive.stat().st_size, client_release.digest(archive)
        payload_parts = client_release.split_payload(archive, "https://github.com/rabbitlandsgame/rabbitlands-client/releases/download/test", 1024)
    payload = {"schema": 1, "commit": identity["commit"], "platform": "windows",
        "size": payload_size, "unpacked_size": unpacked, "file_count": count,
        "sha256": payload_hash, "parts": payload_parts}
    raw = json.dumps(payload, separators=(",", ":")).encode()
    envelope = {"payload": base64.b64encode(raw).decode(), "signature": base64.b64encode(
        key.sign(raw, padding.PKCS1v15(), hashes.SHA256())).decode()}
    project = tmp_path / "project"
    (project / "src/updates").mkdir(parents=True)
    (project / "data").mkdir()
    (project / "src/updates/release.gd").write_bytes((CLIENT / "src/updates/release.gd").read_bytes())
    (project / "install.gd").write_bytes((CLIENT / "tools/install_client_payload.gd").read_bytes())
    (project / "data/client_release.json").write_text(json.dumps(identity))
    (project / "data/install_manifest.json").write_text(json.dumps(envelope))
    (project / "project.godot").write_text('config_version=5\n[application]\nconfig/name="RL Setup Test"\n'
        f'config/use_custom_user_dir=true\nconfig/custom_user_dir_name="RabbitLandsInstallerTest/{tmp_path.name}"\n'
        'run/flush_stdout_on_print=true\n'
        'run/main_scene="res://main.tscn"\n[rendering]\nrenderer/rendering_method="gl_compatibility"\n')
    (project / "main.tscn").write_text('[gd_scene load_steps=2 format=3]\n'
        '[ext_resource type="Script" path="res://install.gd" id="1"]\n'
        '[node name="Installer" type="Node"]\nscript=ExtResource("1")\n')
    root = tmp_path / "installed"
    env = {**os.environ, "APPDATA": str(tmp_path / "userdata"), "LOCALAPPDATA": str(tmp_path / "userdata")}

    command = [str(godot), "--headless", "--path", str(project), "--",
               "--root", str(root), "--parts", str(parts)]

    def run():
        result = subprocess.run(command, env=env, capture_output=True, text=True, timeout=60)
        return result.returncode, result.stdout + result.stderr

    return SimpleNamespace(**locals())


@pytest.mark.parametrize("streamed", [False, True])
def test_online_install_fresh_repair_and_corrupt_download_preserves_game(tmp_path, streamed):
    fixture = online_fixture(tmp_path, streamed)
    root, stage, parts = fixture.root, fixture.stage, fixture.parts
    project, payload, envelope, run = fixture.project, fixture.payload, fixture.envelope, fixture.run
    code, output = run()
    assert code == 0, output
    assert "RL_PROGRESS|0|Unpacking game files: 0 of 4 files" in output
    assert "RL_PROGRESS|100|Unpacking game files: 4 of 4 files" in output
    assert "RL_PROGRESS|100|Game files installed" in output
    game = root / "app/RabbitLands.exe"
    expected = (stage / "app/RabbitLands.exe").read_bytes()
    assert game.read_bytes() == expected
    game.write_bytes(b"damaged installation")
    code, output = run()
    assert code == 0, output
    assert game.read_bytes() == expected
    first = parts / payload["parts"][0]["url"].rsplit("/", 1)[1]
    first.write_bytes(b"corrupt download")
    code, output = run()
    assert code == 1 and "verification" in output, output
    assert game.read_bytes() == expected
    assert not (root / ".eloria-launcher-lock").exists()
    lock = root / ".eloria-launcher-lock"
    lock.mkdir()
    (lock / "owner.json").write_text(json.dumps({"pid": os.getpid()}))
    code, output = run()
    assert code == 1 and "Close Rabbit Lands" in output, output
    assert lock.exists() and game.read_bytes() == expected
    bad_envelope = {**envelope, "signature": base64.b64encode(bytes(256)).decode()}
    (project / "data/install_manifest.json").write_text(json.dumps(bad_envelope))
    code, output = run()
    assert code == 1 and "signature" in output, output
    assert lock.exists() and game.read_bytes() == expected


@pytest.mark.parametrize("finish", ["complete", "crash"])
def test_overlapping_helper_preserves_busy_cache_and_retry_recovers(tmp_path, finish):
    fixture = online_fixture(tmp_path)
    project, root = fixture.project, fixture.root
    # Pause inside real extraction, after the signed archive and pending record
    # exist. This keeps the test deterministic without a multi-GB download.
    (project / "gate.gd").write_text('extends "res://install.gd"\n'
        'func _progress(phase: String, completed: int, total: int, detail := "") -> void:\n'
        '\tsuper._progress(phase, completed, total, detail)\n'
        '\tif phase == "Unpacking game files" and completed == 0:\n'
        '\t\tvar cache := Release.cache_for(OS.get_cmdline_user_args()[1].simplify_path())\n'
        '\t\tRelease.save_json(ProjectSettings.globalize_path("res://gate.json"), {"cache": cache})\n'
        '\t\twhile not FileAccess.file_exists(ProjectSettings.globalize_path("res://continue")):\n'
        '\t\t\tOS.delay_msec(10)\n')
    scene = project / "main.tscn"
    scene.write_text(scene.read_text().replace('path="res://install.gd"', 'path="res://gate.gd"'))
    first_log = tmp_path / "first-helper.log"
    with first_log.open("w") as output_file:
        first = subprocess.Popen(fixture.command, env=fixture.env, stdout=output_file,
                                 stderr=subprocess.STDOUT, text=True)
    try:
        deadline = time.monotonic() + 15
        while not (project / "gate.json").exists():
            assert first.poll() is None, first_log.read_text()
            if time.monotonic() >= deadline:
                first.kill()
                first.wait(timeout=10)
                pytest.fail("First installer did not reach extraction:\n" + first_log.read_text())
            time.sleep(0.02)
        cache = Path(json.loads((project / "gate.json").read_text())["cache"])
        before = {p.name: p.read_bytes() for p in cache.iterdir() if p.is_file()}
        owner = root / ".eloria-launcher-lock/owner.json"
        if finish == "complete":
            # Simulate a PID lookup that cannot establish liveness, as can
            # happen across privilege levels. The open Windows handle must
            # still prevent deleting/reclaiming this live installation lock.
            owner.write_text('{"pid":0,"guarded":true}')
            os.utime(owner, (time.time() - 120, time.time() - 120))
        code, output = fixture.run()
        assert code == 1 and ("still working" in output or "Close Rabbit Lands" in output), output
        assert "Copying downloads" not in output
        assert {p.name: p.read_bytes() for p in cache.iterdir() if p.is_file()} == before
        assert not (root / "app/RabbitLands.exe").exists()
        if finish == "complete":
            (project / "continue").touch()
            assert first.wait(timeout=30) == 0, first_log.read_text()
        else:
            first.terminate()
            first.wait(timeout=10)
            (project / "continue").touch()
        # A normal exit releases the guard; a crash leaves a recoverable lock.
        code, output = fixture.run()
        assert code == 0, output
        assert (root / "app/RabbitLands.exe").read_bytes() == (fixture.stage / "app/RabbitLands.exe").read_bytes()
        assert not owner.parent.exists()
    finally:
        if first.poll() is None:
            first.kill()
            first.wait(timeout=10)


def test_compiled_setup_streams_progress_and_rejects_second_setup(tmp_path):
    """Exercise Inno's actual callback, singleton and release-exported helper."""
    fixture = online_fixture(tmp_path, streamed=True)
    iscc = Path(os.environ["LOCALAPPDATA"]) / "Programs/Inno Setup 6/ISCC.exe"
    if not iscc.is_file():
        pytest.skip("Inno Setup is needed for the compiled setup integration check.")
    stage, logs = fixture.stage, tmp_path / "logs"
    logs.mkdir()
    branding = stage / "app/assets/branding"
    branding.mkdir(parents=True)
    for name in ("rabbitlands-icon.ico", "rabbitlands-mark-64.png"):
        shutil.copyfile(CLIENT / "assets/branding" / name, branding / name)
    (stage.parent / f"{stage.name}-windows.json").write_text(json.dumps(fixture.envelope))

    def run_godot(godot, args, log, timeout):
        if "--export-release" in args:
            project = logs / "installer-project"
            # Gate only the test scene, keeping the production helper and
            # generated release project settings unchanged.
            (project / "gate.gd").write_text('extends "res://install.gd"\n'
                'func _progress(phase: String, completed: int, total: int, detail := "") -> void:\n'
                '\tsuper._progress(phase, completed, total, detail)\n'
                '\tif phase == "Unpacking game files" and completed == 0:\n'
                '\t\tvar root := OS.get_cmdline_user_args()[1].simplify_path()\n'
                '\t\tRelease.save_json(root.path_join("entered.json"), {"ready": true})\n'
                '\t\twhile not FileAccess.file_exists(root.path_join("continue")):\n'
                '\t\t\tOS.delay_msec(10)\n')
            scene = project / "main.tscn"
            scene.write_text(scene.read_text().replace('path="res://install.gd"', 'path="res://gate.gd"'))
        result = subprocess.run([str(godot), *args], env=fixture.env, capture_output=True,
                                text=True, timeout=timeout)
        log.write_text(result.stdout + result.stderr)
        assert result.returncode == 0 and "SCRIPT ERROR" not in result.stdout + result.stderr, log.read_text()

    templates = Path(os.environ["APPDATA"]) / "Godot/export_templates/4.7.2.stable"
    for name in ("windows_debug_x86_64.exe", "windows_release_x86_64.exe"):
        if not (templates / name).is_file():
            pytest.skip("Windows export templates are needed for the compiled setup check.")
    presets = package_client.EXPORT_PRESETS.replace('custom_template/debug=""',
        f'custom_template/debug="{(templates / "windows_debug_x86_64.exe").as_posix()}"', 1)
    presets = presets.replace('custom_template/release=""',
        f'custom_template/release="{(templates / "windows_release_x86_64.exe").as_posix()}"', 1)
    helper = client_release.export_installer_helper(stage, fixture.godot, CLIENT,
        presets, run_godot, logs)
    project_text = (logs / "installer-project/project.godot").read_text()
    assert 'run/flush_stdout_on_print=true' in project_text

    class Handler(http.server.SimpleHTTPRequestHandler):
        def log_message(self, *_args):
            pass

    server = http.server.ThreadingHTTPServer(("127.0.0.1", 0),
        functools.partial(Handler, directory=fixture.parts))
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    payload = {**fixture.payload, "parts": [{**part,
        "url": f"http://127.0.0.1:{server.server_port}/" + part["url"].rsplit("/", 1)[1]}
        for part in fixture.payload["parts"]]}
    script = package_client.online_installer_script(stage, helper, "test", [], payload)
    # No production registration, shortcuts, game launch or uninstall entry.
    script = script.replace('AppId=' + package_client.INSTALLER_APP_ID.replace('{', '{{'),
                            'AppId=RabbitLandsInstallerRegression\nUninstallable=no')
    script = script.split('[Icons]')[0] + '[Code]' + script.split('[Code]', 1)[1]
    info = stage.parent / f"{stage.name}-online-install.txt"
    info.write_text("Isolated miniature installer regression fixture.")
    iss = logs / "setup.iss"
    iss.write_text(script, encoding="utf-8-sig")
    result = subprocess.run([str(iscc), str(iss)], capture_output=True, text=True, timeout=120)
    assert result.returncode == 0, result.stdout + result.stderr
    setup = stage.parent / f"{stage.name}-setup.exe"
    root = tmp_path / "setup-installed"
    log = tmp_path / "setup.log"
    command = [str(setup), "/VERYSILENT", "/SUPPRESSMSGBOXES", "/NORESTART", "/SP-",
               f"/DIR={root}", f"/LOG={log}"]
    first = subprocess.Popen(command, env=fixture.env)
    try:
        deadline = time.monotonic() + 45
        while not (root / "entered.json").exists():
            assert first.poll() is None, log.read_text(errors="replace") if log.exists() else "Setup exited"
            assert time.monotonic() < deadline, log.read_text(errors="replace") if log.exists() else "Setup did not start"
            time.sleep(0.05)
        # The release helper is still paused. Progress must already have
        # reached Inno's callback and the helper's flushed log, before exit.
        assert "RL_PROGRESS|0|Unpacking game files: 0 of 4 files" in log.read_text(errors="replace")
        other_root = tmp_path / "must-not-install"
        second = subprocess.run([*command[:-2], f"/DIR={other_root}",
                                 f"/LOG={tmp_path / 'second-setup.log'}"],
                                env=fixture.env, capture_output=True, timeout=15)
        assert second.returncode != 0
        assert not other_root.exists()
        (root / "continue").touch()
        assert first.wait(timeout=30) == 0, log.read_text(errors="replace")
        assert (root / "app/RabbitLands.exe").read_bytes() == (fixture.stage / "app/RabbitLands.exe").read_bytes()
        assert "RL_PROGRESS|100|Game files installed" in log.read_text(errors="replace")
        assert not (root / ".eloria-launcher-lock").exists()
    finally:
        # Release the gated child even if an assertion fails, before closing
        # its parent setup. All paths belong to this test's temporary root.
        if root.is_dir():
            (root / "continue").touch()
        if first.poll() is None:
            try:
                first.wait(timeout=30)
            except subprocess.TimeoutExpired:
                first.kill()
                first.wait(timeout=10)
        server.shutdown()
        server.server_close()
