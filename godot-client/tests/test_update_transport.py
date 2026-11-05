"""The updater transport reads package downloads in large chunks (FIX-UD).

HTTPRequest's download thread reads one `download_chunk_size` chunk and then
sleeps until the next timer tick (15.6 ms at Windows' default timer resolution,
about 2 ms when a finer one is in effect), so the 64 KiB default capped package
downloads at about 4.2 (or 30) MB/s. A real Godot process downloads from a local
server through `update_transport.gd` exactly as the updater does.
"""
import functools
import hashlib
import http.server
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import threading

import pytest

CLIENT = Path(__file__).resolve().parents[1]
GODOT = CLIENT / "Godot_v4.7.2-stable_win64.exe"
BLOB_BYTES = 24 * 1024 * 1024
RUNNER = '''extends SceneTree
const Transport = preload("res://src/updates/update_transport.gd")
func _initialize() -> void:
\t_run.call_deferred()
func _run() -> void:
\tvar request: Dictionary = JSON.parse_string(FileAccess.get_file_as_string(OS.get_cmdline_user_args()[0]))
\tvar transport := Transport.new()
\troot.add_child(transport)
\tvar report := {}
\tfor kind: String in ["file", "memory"]:
\t\tvar result := {}
\t\tvar began := Time.get_ticks_usec()
\t\tvar fetch := func() -> void:
\t\t\tif kind == "file":
\t\t\t\tresult.merge(await transport.fetch(request.server + "/blob.bin", request.target, int(request.size)))
\t\t\telse:
\t\t\t\tresult.merge(await transport.fetch(request.server + "/manifest.json"))
\t\t\tresult["done"] = true
\t\tfetch.call()
\t\t# The request exists from the call until the reply arrives.
\t\treport[kind + "_chunk"] = transport._request.download_chunk_size if transport._request != null else -1
\t\twhile not result.has("done"):
\t\t\tawait process_frame
\t\treport[kind + "_seconds"] = (Time.get_ticks_usec() - began) / 1e6
\t\treport[kind + "_error"] = str(result.get("error", ""))
\t\tif kind == "memory":
\t\t\tvar body: PackedByteArray = result.get("body", PackedByteArray())
\t\t\treport["memory_body"] = body.get_string_from_utf8()
\tvar file := FileAccess.open(request.report, FileAccess.WRITE)
\tfile.store_string(JSON.stringify(report))
\tfile.close()
\tquit(0)
'''


@pytest.fixture
def served(tmp_path):
    if not GODOT.is_file():
        pytest.skip("Native Godot is required for the transport test.")
    root = tmp_path / "served"
    root.mkdir()
    blob = os.urandom(BLOB_BYTES)
    (root / "blob.bin").write_bytes(blob)
    (root / "manifest.json").write_text('{"schema": 2}')

    class Handler(http.server.SimpleHTTPRequestHandler):
        def log_message(self, *_):
            pass

    server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), functools.partial(Handler, directory=root))
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    yield {"tmp": tmp_path, "server": f"http://127.0.0.1:{server.server_port}", "sha256": hashlib.sha256(blob).hexdigest()}
    server.shutdown()
    server.server_close()
    thread.join(timeout=3)


def run_transport(served):
    tmp = served["tmp"]
    project = tmp / "project"
    shutil.copytree(CLIENT / "src/updates", project / "src/updates")
    (project / "project.godot").write_text('config_version=5\n[application]\nconfig/name="Transport test"\n'
                                           'config/use_custom_user_dir=true\nconfig/custom_user_dir_name="RabbitLandsTransportTest"\n')
    (project / "run.gd").write_text(RUNNER)
    target = tmp / "download.bin"
    report = tmp / "report.json"
    request = tmp / "request.json"
    request.write_text(json.dumps({"server": served["server"], "target": target.as_posix(), "size": BLOB_BYTES,
                                   "report": report.as_posix()}))
    env = {**os.environ, "APPDATA": str(tmp / "userdata"), "LOCALAPPDATA": str(tmp / "userdata")}
    completed = subprocess.run([str(GODOT), "--headless", "--path", str(project), "--script", "res://run.gd", "--", str(request)],
                               env=env, text=True, capture_output=True, timeout=120)
    output = completed.stdout + completed.stderr
    assert completed.returncode == 0 and "SCRIPT ERROR" not in output, output
    return json.loads(report.read_text()), target


def test_package_downloads_use_large_chunks_and_manifests_keep_the_default(served):
    source = (CLIENT / "src/updates/update_transport.gd").read_text(encoding="utf-8")
    declared = re.search(r"const DOWNLOAD_CHUNK_BYTES := (\d+) \* (\d+)", source)
    assert declared, "update_transport.gd no longer declares DOWNLOAD_CHUNK_BYTES"
    chunk = int(declared.group(1)) * int(declared.group(2))
    assert chunk >= 1024 * 1024, "package downloads would be capped near chunk / 15.6 ms on Windows"
    report, target = run_transport(served)
    assert report["file_error"] == "" and report["memory_error"] == "", report
    assert report["file_chunk"] == chunk, report
    # Manifests and API replies are small and read into memory: default chunk.
    assert report["memory_chunk"] == 65536, report
    assert report["memory_body"] == '{"schema": 2}', report
    assert target.stat().st_size == BLOB_BYTES
    assert hashlib.sha256(target.read_bytes()).hexdigest() == served["sha256"]


def test_package_download_is_not_capped_by_the_chunk_size(served):
    # With 1 MiB chunks this download takes 24 timer ticks: about 0.4 s even at
    # the default 15.6 ms tick. (With 64 KiB chunks it takes 384 ticks, 6.0 s at
    # that tick; a finer tick hides that, so the chunk value is checked above.)
    report, target = run_transport(served)
    assert report["file_error"] == "", report
    assert hashlib.sha256(target.read_bytes()).hexdigest() == served["sha256"]
    assert report["file_seconds"] < 3.0, report
