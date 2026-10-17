"""Manual Linux/WSL check for the release download helper; uses only a local HTTP fixture."""
import hashlib
import http.server
import io
import os
from pathlib import Path
import subprocess
import sys
import tarfile
import tempfile
import threading

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
from linux_download_helper import download_script as generate


def main():
    folder = "RabbitLands-Linux-Smoke"
    data = io.BytesIO()
    with tarfile.open(fileobj=data, mode="w:gz") as archive:
        for name in ("RabbitLands.sh", "app/RabbitLands.x86_64"):
            payload = b"#!/bin/sh\nexit 0\n"
            info = tarfile.TarInfo(folder + "/" + name)
            info.size, info.mode = len(payload), 0o755
            archive.addfile(info, io.BytesIO(payload))
    payload = data.getvalue()
    step = (len(payload) + 2) // 3
    names = ["game.tar.gz.001", "game.tar.gz.002.001", "game.tar.gz.002.002"]
    pieces = {name: payload[index * step:(index + 1) * step] for index, name in enumerate(names)}
    rows = [{"path": name, "sha256": hashlib.sha256(body).hexdigest()} for name, body in pieces.items()]
    counts = {name: 0 for name in pieces}
    corrupt = {"enabled": True}

    class Handler(http.server.BaseHTTPRequestHandler):
        def do_GET(self):
            name = self.path.removeprefix("/")
            body = pieces[name]
            counts[name] += 1
            if corrupt["enabled"] and name == names[-1]:
                body = b"corrupted"
            self.send_response(200)
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
        def log_message(self, *_args):
            pass

    server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    fixture = Path(tempfile.mkdtemp(prefix="linux-helper-smoke-"))
    script = fixture / "download.sh"
    script.write_text(generate(folder, "fixture", f"http://127.0.0.1:{server.server_port}",
                               hashlib.sha256(payload).hexdigest(), rows))
    env = dict(os.environ, HOME=str(fixture / "home"), XDG_CACHE_HOME=str(fixture / "cache with spaces"))
    target = fixture / "Games With Spaces"
    subprocess.run(["sh", "-n", str(script)], check=True)
    result = subprocess.run(["sh", str(script), str(target)], env=env, capture_output=True, text=True)
    assert result.returncode != 0 and not (target / folder).exists(), result.stdout + result.stderr
    assert counts[names[-1]] == 3
    cached_counts = dict(counts)
    corrupt["enabled"] = False
    result = subprocess.run(["sh", str(script), str(target)], env=env, capture_output=True, text=True)
    assert result.returncode == 0, result.stdout + result.stderr
    assert counts[names[0]] == cached_counts[names[0]] and counts[names[1]] == cached_counts[names[1]]
    assert os.access(target / folder / "app/RabbitLands.x86_64", os.X_OK)
    marker = target / folder / "preserve.txt"
    marker.write_text("existing installation")
    cached_counts = dict(counts)
    result = subprocess.run(["sh", str(script), str(target)], env=env, capture_output=True, text=True)
    assert result.returncode != 0 and marker.read_text() == "existing installation"
    assert counts == cached_counts
    server.shutdown()
    print("Linux helper passed: corrupt-part rejection, verified-cache resume, subpart order, paths with spaces, executable extraction, existing-folder protection.")


if __name__ == "__main__":
    if os.name == "nt":
        raise SystemExit("Run this check in Linux or WSL with curl, sha256sum and tar installed.")
    main()
