"""Isolated signed update/recovery and real local HTTPS download tests."""
from __future__ import annotations

import argparse
import functools
import http.server
import json
import os
import shutil
import ssl
import subprocess
import sys
import tempfile
import threading
from pathlib import Path

SOURCE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SOURCE / "tools"))
import client_release


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--godot", default=shutil.which("godot"))
    parser.add_argument("--out", type=Path)
    options = parser.parse_args()
    if not options.godot:
        parser.error("pass --godot PATH or put godot on PATH")
    root = options.out.resolve() if options.out else Path(tempfile.mkdtemp(prefix="eloria-updates-test-"))
    root.mkdir(parents=True, exist_ok=True)
    scripts = root / "src/updates"
    scripts.mkdir(parents=True, exist_ok=True)
    for name in ("release.gd", "client_updates.gd", "package_updates.gd", "package_download.gd"):
        shutil.copyfile(SOURCE / "src/updates" / name, scripts / name)
    (root / "data").mkdir(exist_ok=True)
    (root / "data/client_release.json").write_text('{"platform":"source"}')
    (root / "network_stub.gd").write_text("extends Node\nvar offline_hud_preview := false\nsignal packet_received(command, payload)\nsignal connection_state_changed(state)\n")
    (root / "app_state_stub.gd").write_text("extends Node\nfunc append_local_message(message, _channel):\n\tprint(message)\n")
    (root / "project.godot").write_text('config_version=5\n[autoload]\nNetwork="*res://network_stub.gd"\nAppState="*res://app_state_stub.gd"\n')
    env = dict(os.environ, APPDATA=str(root / "appdata"), LOCALAPPDATA=str(root / "appdata"),
               XDG_DATA_HOME=str(root / "appdata"), XDG_CONFIG_HOME=str(root / "appdata"))

    def run(script: str, *arguments) -> None:
        kwargs = {"creationflags": subprocess.CREATE_NO_WINDOW} if os.name == "nt" else {}
        result = subprocess.run([options.godot, "--headless", "--path", str(root), "--script",
                                 str(SOURCE / script), "--", *map(str, arguments)],
                                capture_output=True, text=True, timeout=45, env=env, **kwargs)
        print(result.stdout)
        if result.returncode or "SCRIPT ERROR" in result.stderr:
            raise RuntimeError(result.stderr or f"{script} exited {result.returncode}")

    run("tests/test_client_updates.gd", root / "install-fixture")
    run("tests/test_store_updates.gd", root / "store-install-fixture")
    private, public, certificate = (root / name for name in ("private.pem", "public.pem", "localhost.crt"))
    # An output folder can be reused without overwriting its test key.
    if not private.exists():
        run("tools/sign_client_release.gd", "generate", private, public)
    run("tests/client_update_test_certificate.gd", private, certificate)
    stage = root / "payload-fixture"
    (stage / "app").mkdir(parents=True, exist_ok=True)
    (stage / "eloria-assets").mkdir(exist_ok=True)
    (stage / "app/RabbitLands.pck").write_bytes(b"background download fixture" * 1024)
    (stage / "eloria-assets/map.json").write_text("{}")
    archive = root / "payload.zip"
    _, unpacked = client_release.build_payload(stage, archive)
    identity = {"commit": "a" * 40, "ancestors": ["a" * 40], "platform": "windows",
                "public_key": public.read_text(), "repository": "o/r"}

    class Handler(http.server.SimpleHTTPRequestHandler):
        failures_left = 1

        def do_GET(self):
            if self.path == "/manifest.json" and Handler.failures_left:
                Handler.failures_left -= 1
                self.send_error(503, "transient test failure")
                return
            super().do_GET()

        def log_message(self, *_args):
            pass

    server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), functools.partial(Handler, directory=root))
    context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    context.load_cert_chain(certificate, private)
    server.socket = context.wrap_socket(server.socket, server_side=True)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    # The fixture listens on IPv4. Avoid Windows localhost resolving to ::1
    # while retaining explicit certificate hostname verification in the test.
    url = f"https://127.0.0.1:{server.server_port}"
    release = {"schema": 1, "commit": "b" * 40, "platform": "windows",
               "size": archive.stat().st_size, "unpacked_size": unpacked,
               "sha256": client_release.digest(archive),
               "parts": [{"url": url + "/payload.zip", "size": archive.stat().st_size,
                          "sha256": client_release.digest(archive)}]}
    payload = root / "manifest-payload.json"
    payload.write_text(json.dumps(release))
    try:
        run("tools/sign_client_release.gd", "sign", private, payload, root / "manifest.json")
        request = root / "download-request.json"
        request.write_text(json.dumps({"identity": identity, "certificate": str(certificate),
                                      "url": url + "/manifest.json", "commit": "b" * 40}))
        run("tests/test_client_update_download.gd", request)
        assert Handler.failures_left == 0, "the HTTPS transport was not exercised"
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=3)
    print("Signed client update runtime and HTTPS checks: PASS")


if __name__ == "__main__":
    main()
