"""Exercise the online setup helper against signed, local miniature downloads."""
import base64
import json
import os
from pathlib import Path
import subprocess
import sys

import pytest
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding, rsa

CLIENT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(CLIENT / "tools"))
import client_release
from release_storage import PartWriter


@pytest.mark.parametrize("streamed", [False, True])
def test_online_install_fresh_repair_and_corrupt_download_preserves_game(tmp_path, streamed):
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
        'config/use_custom_user_dir=true\nconfig/custom_user_dir_name="RabbitLandsInstallerTest"\n'
        'run/main_scene="res://main.tscn"\n[rendering]\nrenderer/rendering_method="gl_compatibility"\n')
    (project / "main.tscn").write_text('[gd_scene load_steps=2 format=3]\n'
        '[ext_resource type="Script" path="res://install.gd" id="1"]\n'
        '[node name="Installer" type="Node"]\nscript=ExtResource("1")\n')
    root = tmp_path / "installed"
    env = {**os.environ, "APPDATA": str(tmp_path / "userdata"), "LOCALAPPDATA": str(tmp_path / "userdata")}

    def run():
        result = subprocess.run([str(godot), "--headless", "--path", str(project), "--",
            "--root", str(root), "--parts", str(parts)], env=env, capture_output=True, text=True, timeout=60)
        return result.returncode, result.stdout + result.stderr

    code, output = run()
    assert code == 0, output
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
