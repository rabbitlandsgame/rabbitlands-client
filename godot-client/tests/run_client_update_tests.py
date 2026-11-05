"""Isolated signed update/recovery and real local HTTPS download tests."""
from __future__ import annotations

import argparse
import functools
import http.server
import json
import os
import re
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
import desktop_r2

# The shipped R2 base line in src/updates/release.gd. Fixture projects replace
# it in their own copy only; the shipped rules never name a local server.
R2_DECLARATION = f'const DESKTOP_ASSETS := "{desktop_r2.DESKTOP_ASSETS}"'
LOCAL_R2_BASE = re.compile(r"https://127\.0\.0\.1:[0-9]{1,5}/desktop/v1/")
R2_FIXTURE_SCRIPTS = ("release.gd", "package_updates.gd", "package_download.gd", "update_transport.gd")


def r2_fixture_release(text: str, base: str) -> str:
    """The fixture's release.gd: the shipped text with only DESKTOP_ASSETS moved
    to the local HTTPS server `base`."""
    if not LOCAL_R2_BASE.fullmatch(base):
        raise ValueError(f"not a local fixture base: {base!r}")
    lines = text.split("\n")
    found = [index for index, line in enumerate(lines) if line == R2_DECLARATION]
    if len(found) != 1:
        raise ValueError("release.gd must declare the production DESKTOP_ASSETS exactly once")
    lines[found[0]] = f'const DESKTOP_ASSETS := "{base}"'
    return "\n".join(lines)


def fault_handler(directory: Path):
    """Serves `directory`. Before each GET it takes the next scripted action for
    the path from faults.json: "ok", an HTTP status, "garbage" (the same length
    of other bytes) or "drop" (no reply), and counts requests in requests.json."""
    lock = threading.Lock()
    counts: dict[str, int] = {}

    class Handler(http.server.SimpleHTTPRequestHandler):
        def do_GET(self):
            with lock:
                counts[self.path] = counts.get(self.path, 0) + 1
                script = directory / "faults.json"
                faults = json.loads(script.read_text(encoding="utf-8") or "{}") if script.is_file() else {}
                queue = faults.get(self.path) or []
                action = str(queue.pop(0)) if queue else "ok"
                script.write_text(json.dumps(faults), encoding="utf-8")
                (directory / "requests.json").write_text(json.dumps(counts), encoding="utf-8")
            if action == "ok":
                super().do_GET()
            elif action == "drop":
                self.close_connection = True
            elif action == "garbage":
                data = bytes(byte ^ 0x5A for byte in Path(self.translate_path(self.path)).read_bytes())
                self.send_response(200)
                self.send_header("Content-Type", "application/octet-stream")
                self.send_header("Content-Length", str(len(data)))
                self.end_headers()
                self.wfile.write(data)
            else:
                self.send_error(int(action), "scripted fixture fault")

        def log_message(self, *_args):
            pass

    return functools.partial(Handler, directory=str(directory))


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
    for name in ("release.gd", "client_updates.gd", "package_updates.gd", "package_download.gd",
                 "startup_update.gd", "launch_options.gd", "update_transport.gd", "bootstrap.gd"):
        shutil.copyfile(SOURCE / "src/updates" / name, scripts / name)
    # The real update notice uses the shared text-color binding.
    (root / "src/ui").mkdir(parents=True, exist_ok=True)
    shutil.copyfile(SOURCE / "src/ui/text_colors.gd", root / "src/ui/text_colors.gd")
    (root / "data").mkdir(exist_ok=True)
    (root / "data/client_release.json").write_text('{"platform":"source"}')
    (root / "network_stub.gd").write_text("extends Node\nvar offline_hud_preview := false\nsignal packet_received(command, payload)\nsignal connection_state_changed(state)\n")
    (root / "app_state_stub.gd").write_text("extends Node\nfunc append_local_message(message, _channel):\n\tprint(message)\n")
    (root / "project.godot").write_text('config_version=5\n[autoload]\nNetwork="*res://network_stub.gd"\nAppState="*res://app_state_stub.gd"\n')
    env = dict(os.environ, APPDATA=str(root / "appdata"), LOCALAPPDATA=str(root / "appdata"),
               XDG_DATA_HOME=str(root / "appdata"), XDG_CONFIG_HOME=str(root / "appdata"))

    def run(script: str, *arguments, project: Path = root) -> None:
        kwargs = {"creationflags": subprocess.CREATE_NO_WINDOW} if os.name == "nt" else {}
        result = subprocess.run([options.godot, "--headless", "--path", str(project), "--script",
                                 str(SOURCE / script), "--", *map(str, arguments)],
                                capture_output=True, text=True, timeout=45, env=env, **kwargs)
        print(result.stdout)
        if result.returncode or "SCRIPT ERROR" in result.stderr:
            raise RuntimeError(result.stderr or f"{script} exited {result.returncode}")

    # Launch options on their own, as the updater project compiles them.
    run("tests/test_launch_renderer.gd")
    run("tests/test_client_updates.gd", root / "install-fixture")
    run("tests/test_client_update_cleanup.gd", root / "cleanup-fixture")
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
    # R2 content parts (W1a): schema 2/3 rules, retries, fail-fast 404s and
    # resume, through the updater transport over real local HTTPS. The fixture
    # project's release.gd names this server as DESKTOP_ASSETS.
    served = root / "r2-served"
    shutil.rmtree(served, ignore_errors=True)
    served.mkdir()
    r2_server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), fault_handler(served))
    r2_server.socket = context.wrap_socket(r2_server.socket, server_side=True)
    r2_thread = threading.Thread(target=r2_server.serve_forever, daemon=True)
    r2_thread.start()
    try:
        base = f"https://127.0.0.1:{r2_server.server_port}/desktop/v1/"
        project = root / "r2-project"
        (project / "src/updates").mkdir(parents=True, exist_ok=True)
        for name in R2_FIXTURE_SCRIPTS:
            text = (SOURCE / "src/updates" / name).read_text(encoding="utf-8")
            if name == "release.gd":
                text = r2_fixture_release(text, base)
            (project / "src/updates" / name).write_text(text, encoding="utf-8", newline="\n")
        (project / "project.godot").write_text('config_version=5\n[application]\nconfig/name="R2 download fixture"\n')
        request = root / "r2-request.json"
        request.write_text(json.dumps({"served": served.as_posix(), "root": (root / "r2-install").as_posix(),
                                       "certificate": str(certificate),
                                       "production_key": (SOURCE / "data/update_public.pem").as_posix()}))
        run("tests/test_client_update_r2.gd", request, project=project)
    finally:
        r2_server.shutdown()
        r2_server.server_close()
        r2_thread.join(timeout=3)
    print("Signed client update runtime and HTTPS checks: PASS")


if __name__ == "__main__":
    main()
