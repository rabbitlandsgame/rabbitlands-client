"""Online setup undoes an interrupted per-file update before it plans (W2-UD-04, hook H2).

The setup helper (tools/install_client_payload.gd) plans its downloads against
the installed files. After a crashed update those files are half moved, so a
plan made first would skip packages whose files only look current. Setup must
recover first, as the launcher does, and then install the release exactly.
Setup's own update cache does not hold the interrupted update's downloads here
(a separate user folder), which is when a stale plan would fail.
"""
import json
from pathlib import Path
import shutil
import subprocess

import pytest

from test_asset_packages import CLIENT, assert_no_transaction, every_operation, fixture, signed, tree  # noqa: F401

RUNNER = '''extends SceneTree
func _initialize() -> void:
    root.add_child.call_deferred(load("res://tools/install_client_payload.gd").new())
'''
HELPER = "tools/install_client_payload.gd"


def setup_project(f, payload, helper_source=None):
    """A minimal project that runs the setup helper with the signed release embedded."""
    project = f["tmp_path"] / "setup-project"
    shutil.copytree(CLIENT / "src/updates", project / "src/updates")
    (project / "tools").mkdir()
    source = helper_source if helper_source is not None else (CLIENT / HELPER).read_text(encoding="utf-8")
    (project / HELPER).write_text(source, encoding="utf-8", newline="\n")
    (project / "data").mkdir()
    (project / "data/client_release.json").write_text(json.dumps(f["newer"]))
    (project / "data/install_manifest.json").write_text(json.dumps(signed(payload, f["key"])))
    (project / "project.godot").write_text('config_version=5\n[application]\nconfig/name="Setup recovery tests"\n'
        'config/use_custom_user_dir=true\nconfig/custom_user_dir_name="RabbitLandsSetupRecoveryTests"\n')
    (project / "run.gd").write_text(RUNNER)
    return project


def setup_parts(f, payload):
    """Every part of the release, verified-downloaded as Inno leaves them in {tmp}."""
    parts = f["tmp_path"] / "setup-parts"
    parts.mkdir()
    for part in payload["parts"]:
        name = part["url"].rsplit("/", 1)[1]
        shutil.copyfile(f["tmp_path"] / name, parts / name)
    return parts


def run_setup(f, project, parts):
    completed = subprocess.run([str(f["godot"]), "--headless", "--path", str(project), "--script",
        str(project / "run.gd"), "--", "--root", f["installed"].as_posix(), "--parts", parts.as_posix()],
        env=f["env"], text=True, capture_output=True, timeout=60)
    return completed.returncode, completed.stdout + completed.stderr


def interrupted_update(f, point):
    """The fixture's every-operation release, its update killed after an early or a late step."""
    stage, payload, steps = every_operation(f)
    stop = 1 if point == "early" else steps - 1
    code, error, output = f["run"](payload=payload, stop_after=stop)
    assert error == "killed", output
    assert (f["installed"] / ".eloria-update-journal-v2.json").is_file(), "the update left its journal"
    return stage, payload


@pytest.mark.parametrize("point", ["early", "late"])
def test_setup_recovers_an_interrupted_update_then_installs_the_release(fixture, point):
    f = fixture
    stage, payload = interrupted_update(f, point)
    project = setup_project(f, payload)
    code, log = run_setup(f, project, setup_parts(f, payload))
    assert "SCRIPT ERROR" not in log, log
    assert code == 0 and "Rabbit Lands installation verified." in log and "RL_ERROR" not in log, log
    assert tree(f["installed"]) == tree(stage)
    assert_no_transaction(f["installed"])
    assert not (f["installed"] / ".eloria-launcher-lock").exists()


def test_setup_helper_recovers_before_it_plans():
    # The order the behaviour above depends on: the interrupted update is undone
    # after the running-game check and before Download.prepare plans anything.
    source = (CLIENT / HELPER).read_text(encoding="utf-8")
    body = source[source.index("func _install_packages("):source.index("func _install() ")]
    lease = body.index('return "Close Rabbit Lands before installing."')
    recover = body.index("error = Release.recover(root)")
    prepare = body.index("Download.prepare(")
    assert lease < recover < prepare
