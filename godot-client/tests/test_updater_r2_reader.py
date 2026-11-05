"""The updater's R2 reader (W1a) as the R2 release tools read it.

The R2 release workflow signs derived R2 part rows and more than 850 packages
only for a commit whose src/updates declares them (release_manifest.py reads
whole lines). These checks pin those declarations to desktop_r2, and check
that test fixtures move only the compiled R2 base, in their own copies.
The runtime rules themselves run in Godot: tests/run_client_update_tests.py
(test_client_updates.gd with the shipped base, and the local HTTPS fixture
test_client_update_r2.gd).
"""
import os
from pathlib import Path
import re
import subprocess
import sys

import pytest

CLIENT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(CLIENT / "tools"))
sys.path.insert(0, str(Path(__file__).resolve().parent))
import desktop_r2 as r2
import release_manifest as rm
import run_client_update_tests as runner

UPDATES = CLIENT / "src/updates"


def text(name: str) -> str:
    return (UPDATES / name).read_text(encoding="utf-8")


def test_release_gd_declares_the_production_r2_base_once():
    assert r2.DESKTOP_ASSETS == "https://assets.rabbitlandsgame.com/desktop/v1/"
    lines = text("release.gd").split("\n")
    assert lines.count(f'const DESKTOP_ASSETS := "{r2.DESKTOP_ASSETS}"') == 1
    assert sum("DESKTOP_ASSETS :=" in line for line in lines) == 1
    assert runner.R2_DECLARATION in lines


def test_derived_r2_forms_match_the_release_tools():
    # release.gd builds these from DESKTOP_ASSETS; test_client_updates.gd pins the
    # same strings in Godot. Both must equal what the tools upload and sign.
    source = text("release.gd")
    digest = "e" * 64
    assert 'return DESKTOP_ASSETS + "manifests/%s/%s.json" % [platform, sha256]' in source
    assert r2.manifest_url("windows", digest) == r2.DESKTOP_ASSETS + f"manifests/windows/{digest}.json"
    assert 'return DESKTOP_ASSETS + "channels/live/%s.json" % platform' in source
    assert r2.pointer_url("linux") == r2.DESKTOP_ASSETS + "channels/live/linux.json"
    assert 'row.url == DESKTOP_ASSETS + "parts/" + str(row.sha256) + ".bin"' in source
    assert r2.part_url(digest) == r2.DESKTOP_ASSETS + f"parts/{digest}.bin"


def test_this_reader_reads_schema_3_r2_rows_and_2000_packages():
    capabilities = rm.reader_capabilities(text("release.gd"), text("package_updates.gd"))
    assert (capabilities.schema, capabilities.r2_rows, capabilities.package_limit) == (3, True, r2.READER_CAP_W1A)
    assert capabilities.reader_cap == r2.READER_CAP_W1A == 2000


def test_no_lower_package_limit_remains():
    source = text("package_updates.gd")
    assert re.findall(r"release\.packages\.size\(\) > ([0-9]+)", source) == ["2000"]
    assert re.findall(r"parts\.size\(\) > ([0-9]+)", source) == ["2000"]
    assert "850" not in source


def test_helpers_keep_the_github_rule():
    # Old updaters hand off through helper rows they can read: never R2 ones.
    assert "r2_part" not in text("bootstrap.gd")
    validate = text("package_updates.gd").split("static func validate(", 1)[1].split("\nstatic func ", 1)[0]
    helpers = validate.split('for kind: String in ["updater", "uninstall"]:', 1)[1]
    assert "r2_part" not in helpers and "shared_download" in helpers


def test_r2_rows_need_schema_3():
    validate = text("package_updates.gd").split("static func validate(", 1)[1].split("\nstatic func ", 1)[0]
    assert "var codecs: bool = release.get(\"schema\") == Release.CODEC_SCHEMA" in validate
    assert "var r2_rows := codecs" in validate
    assert "(r2_rows and Release.r2_part(part))" in validate


def test_fixture_copies_move_only_the_r2_base():
    shipped = text("release.gd")
    base = "https://127.0.0.1:8443/desktop/v1/"
    copy = runner.r2_fixture_release(shipped, base)
    changed = [(old, new) for old, new in zip(shipped.split("\n"), copy.split("\n")) if old != new]
    assert changed == [(runner.R2_DECLARATION, f'const DESKTOP_ASSETS := "{base}"')]
    assert len(copy.split("\n")) == len(shipped.split("\n"))
    # The release tools never mistake a fixture copy for the R2-aware reader.
    assert rm.reader_capabilities(shipped).r2_rows and not rm.reader_capabilities(copy).r2_rows
    for bad in (r2.DESKTOP_ASSETS, "https://127.0.0.1:8443/desktop/v2/", "http://127.0.0.1:8443/desktop/v1/",
                "https://localhost:8443/desktop/v1/", "https://127.0.0.1:8443/desktop/v1", "https://127.0.0.2:8443/desktop/v1/"):
        with pytest.raises(ValueError):
            runner.r2_fixture_release(shipped, bad)
    with pytest.raises(ValueError):
        runner.r2_fixture_release(copy, base)


def test_retry_schedule_and_messages():
    source = text("package_download.gd")
    assert "const RETRY_WAITS_SEC: Array[float] = [5.0, 30.0]" in source
    assert 'const MISSING_ERROR := "The update files are not available yet. Try again later."' in source
    assert "const MISSING_STATUSES := [404, 410]" in source
    # Both transports report the status a retry decision reads; a request that
    # could not start made no network attempt and carries none (never retried).
    for name in ("update_transport.gd", "client_updates.gd"):
        assert '"status": int(response[1]), "result": int(response[0])' in text(name), name
        assert 'return {"error": "The update download could not start."}' in text(name), name


def test_updater_runtime_and_https_suite(tmp_path):
    godot = Path(os.environ.get("RL_GODOT", CLIENT / "Godot_v4.7.2-stable_win64.exe"))
    if not godot.is_file():
        pytest.skip("Native Godot is required for the updater runtime and HTTPS checks.")
    result = subprocess.run([sys.executable, str(Path(__file__).resolve().parent / "run_client_update_tests.py"),
                             "--godot", str(godot), "--out", str(tmp_path / "updates")],
                            capture_output=True, text=True, timeout=900)
    output = result.stdout + result.stderr
    assert result.returncode == 0, output
    assert "Client update runtime checks: PASS" in output
    assert "R2 content download checks: PASS" in output
