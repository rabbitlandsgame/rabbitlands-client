"""Signed startup discovery, consent, and native updater restart checks."""
import json
import os
from pathlib import Path
import shutil
import subprocess
import time

import pytest

from test_asset_packages import CLIENT, fixture, signed, manifest, export_test_updater
import package_client


def run_probe(f, installed, published, action="decline", automatic=False, spawn_result=123, legacy=False, tamper=False):
    project = f["project"]
    script = project / "startup-probe.gd"
    script.write_text('''extends SceneTree
const Startup = preload("res://src/updates/startup_update.gd")
const Release = preload("res://src/updates/release.gd")
const Launch = preload("res://src/updates/launch_options.gd")
class LocalTransport extends "res://src/updates/update_transport.gd":
    var endpoint: String
    func fetch(url: String, path := "", limit := Release.MAX_MANIFEST_BYTES) -> Dictionary:
        return await super.fetch(endpoint + "/" + url.get_file(), path, limit)
class Probe extends "res://src/updates/startup_update.gd":
    var automatic := false
    var endpoint: String
    var started := PackedStringArray()
    var closed := false
    var spawn_result := 123
    var notice := ""
    func _ready() -> void:
        notice_changed.connect(func(message: String) -> void: notice = message)
    func _source_identity() -> Dictionary:
        return identity
    func can_auto_update() -> bool:
        return automatic
    func _new_transport() -> Node:
        var result := LocalTransport.new()
        result.endpoint = endpoint
        return result
    func _start_updater(args: PackedStringArray) -> int:
        started = args
        return spawn_result
    func _close_client() -> void:
        closed = true
func _initialize() -> void:
    run.call_deferred()
func run() -> void:
    var request := Release.read_json(OS.get_cmdline_user_args()[0])
    var probe := Probe.new()
    probe.identity = request.identity
    probe.automatic = request.automatic
    probe.endpoint = request.endpoint
    probe.spawn_result = request.spawn_result
    root.add_child(probe)
    await probe._check()
    var prompted := is_instance_valid(probe.dialog)
    var title := probe.dialog.title if prompted else ""
    var commands := ""
    if prompted:
        for child: Node in probe.dialog.get_children():
            if child is TextEdit:
                commands = child.text
        if request.action == "accept":
            probe._accept_update()
        else:
            probe.dialog.canceled.emit()
    var cases := []
    for flag: String in ["", "--client-debug", "--client-compatibility", "--client-safe-mode"]:
        var user := PackedStringArray(["--server=game.example", "--port=2001"])
        if flag != "": user.append(flag)
        var args := Launch.game_arguments(user, [], "C:/Game Folder", true)
        var split := args.find("--")
        var context := Launch.resume_context(args, args.slice(split + 1))
        cases.append({"flag": flag, "before": Array(args), "after": Array(Launch.resume_arguments(context))})
    var unsafe := Launch.resume_arguments({"schema": 1, "engine": ["--script", "bad.gd"], "user": []})
    Release.save_json(request.result, {"prompted": prompted, "title": title, "commands": commands,
        "notice": probe.notice, "declined": probe.declined, "started": Array(probe.started),
        "closed": probe.closed, "modes": cases, "unsafe_rejected": unsafe.is_empty()})
    probe.free()
    quit()
''')
    envelope = signed(published, f["key"])
    if tamper:
        envelope["payload"] = signed({**published, "commit": "2" * 40}, f["key"])["payload"]
    alias = f["tmp_path"] / "RabbitLands-windows.json"
    if legacy:
        alias.unlink(missing_ok=True)
        (f["tmp_path"] / "legacy-windows.json").write_text(json.dumps(envelope))
        (f["tmp_path"] / "latest").write_text(json.dumps({"assets": [{"name": "legacy-windows.json",
            "browser_download_url": "https://github.com/rabbitlandsgame/rabbitlands-client/releases/download/legacy/legacy-windows.json"}]}))
        (f["tmp_path"] / (installed["commit"] + "..." + published["commit"])).write_text(json.dumps({
            "base_commit": {"sha": installed["commit"]}, "status": "ahead"}))
    else:
        alias.write_text(json.dumps(envelope))
    request = f["tmp_path"] / "startup-request.json"
    result = f["tmp_path"] / "startup-result.json"
    request.write_text(json.dumps({"identity": installed, "automatic": automatic, "action": action,
        "endpoint": f'http://127.0.0.1:{f["server"].server_port}', "spawn_result": spawn_result, "result": str(result)}))
    completed = subprocess.run([str(f["godot"]), "--headless", "--path", str(project), "--script", str(script), "--", str(request)],
        env=f["env"], text=True, capture_output=True, timeout=35)
    output = completed.stdout + completed.stderr
    assert completed.returncode == 0 and "SCRIPT ERROR" not in output, output
    return json.loads(result.read_text())


def history(f):
    # Deliberately reverse lexical order: Git hashes are never version numbers.
    installed = {**f["identity"], "commit": "f" * 40, "ancestors": ["f" * 40]}
    published = {**f["payload"], "commit": "1" * 40, "ancestors": ["1" * 40, "f" * 40]}
    return installed, published


def test_startup_consent_and_launch_mode_roundtrip(fixture):
    f = fixture
    installed, published = history(f)
    declined = run_probe(f, installed, published, automatic=True)
    assert declined["prompted"] and declined["declined"]
    assert "compatibility issues" in declined["notice"] and "as soon as possible" in declined["notice"]
    assert not declined["started"] and not declined["closed"]
    assert f["downloads"] == ["/RabbitLands-windows.json"]
    accepted = run_probe(f, installed, published, action="accept", automatic=True)
    assert accepted["closed"] and "--wait-for-pid" in accepted["started"]
    assert "--resume-client" in accepted["started"]
    failed = run_probe(f, installed, published, action="accept", automatic=True, spawn_result=-1)
    assert not failed["closed"] and "could not start" in failed["notice"]
    for case in accepted["modes"]:
        assert case["before"] == case["after"], case
    assert accepted["unsafe_rejected"]


@pytest.mark.parametrize("relation", ["same", "ahead", "diverged", "steam", "standalone"])
def test_no_update_prompt_for_current_newer_divergent_or_store_builds(fixture, relation):
    f = fixture
    installed, published = history(f)
    if relation == "same":
        installed["commit"] = published["commit"]
    elif relation == "ahead":
        installed["ancestors"].append(published["commit"])
    elif relation == "diverged":
        published["ancestors"] = [published["commit"]]
    else:
        installed["distribution"] = relation
    result = run_probe(f, installed, published)
    assert not result["prompted"] and not result["started"]
    if relation in {"steam", "standalone"}:
        assert not f["downloads"]


def test_custom_build_gets_pinned_manual_commands_without_automatic_replacement(fixture):
    f = fixture
    installed, published = history(f)
    result = run_probe(f, installed, published)
    assert result["prompted"] and result["title"] == "Update your custom build"
    assert "git merge --ff-only client-" + published["commit"] in result["commands"]
    assert "--no-client-updates" in result["commands"]
    assert not result["started"] and not result["closed"]
    installed["platform"] = "source"
    result = run_probe(f, installed, published)
    assert "godot --path godot-client" in result["commands"]
    assert not result["started"]


def test_invalid_signed_release_history_does_not_prompt_or_download(fixture):
    f = fixture
    installed, published = history(f)
    published["ancestors"] = ["not-a-commit"]
    result = run_probe(f, installed, published, automatic=True)
    assert not result["prompted"] and not result["started"]
    assert f["downloads"] == ["/RabbitLands-windows.json"]


def test_tampered_signature_does_not_prompt_or_download(fixture):
    f = fixture
    installed, published = history(f)
    result = run_probe(f, installed, published, automatic=True, tamper=True)
    assert not result["prompted"] and not result["started"]
    assert f["downloads"] == ["/RabbitLands-windows.json"]


def test_legacy_published_release_uses_signed_manifest_and_commit_comparison(fixture):
    f = fixture
    installed, published = history(f)
    published.pop("ancestors")
    result = run_probe(f, installed, published, automatic=True, legacy=True)
    assert result["prompted"] and result["declined"]
    assert len(f["downloads"]) == 4
    assert f["downloads"][:3] == ["/RabbitLands-windows.json", "/latest", "/legacy-windows.json"]


@pytest.mark.skipif(os.name != "nt", reason="Native Windows export and process handoff")
def test_native_game_closes_updates_and_reopens_in_each_launch_mode(fixture):
    f = fixture
    stage = f["tmp_path"] / "RabbitLands-Windows-startup-bbbbbbbbb"
    shutil.copytree(f["stage"], stage)
    f["stage"] = stage # Keep generated parts distinct from the fixture's first inventory.
    updater = export_test_updater(f, "startup-restart")
    project = f["tmp_path"] / "restart-game"
    shutil.copytree(CLIENT / "src/updates", project / "src/updates")
    shutil.copytree(CLIENT / "assets/branding", project / "assets/branding")
    (project / "data").mkdir()
    (project / "project.godot").write_text('config_version=5\n[application]\nconfig/name="Restart probe"\nrun/main_scene="res://main.tscn"\n[rendering]\nrenderer/rendering_method="gl_compatibility"\n')
    (project / "main.gd").write_text('''extends Node
const Release = preload("res://src/updates/release.gd")
class Startup extends "res://src/updates/startup_update.gd":
    func _start_updater(args: PackedStringArray) -> int:
        # Exercise the installed executable and production handoff without
        # opening an interactive updater window on the test desktop.
        return OS.create_process(updater_path(), PackedStringArray(["--headless"]) + args)
func _ready() -> void:
    var root := OS.get_environment("ELORIA_INSTALL_ROOT")
    var startup := Startup.new()
    startup.identity = Release.read_json("res://data/client_release.json")
    add_child(startup)
    var record := {"engine": Array(OS.get_cmdline_args()), "user": Array(OS.get_cmdline_user_args()),
        "managed": startup.can_auto_update(), "commit": startup.identity.commit,
        "safe": OS.get_environment("ELORIA_NO_MAP_CACHE"), "verbose": OS.is_stdout_verbose(),
        "context": OS.get_environment("RABBITLANDS_LAUNCH_CONTEXT")}
    if FileAccess.file_exists(root.path_join("request-update")):
        DirAccess.remove_absolute(root.path_join("request-update"))
        Release.save_json(root.path_join("before.json"), record)
        startup._accept_update()
    else:
        Release.save_json(root.path_join("after.json"), record)
        get_tree().quit()
''')
    (project / "main.tscn").write_text('[gd_scene load_steps=2 format=3]\n[ext_resource type="Script" path="res://main.gd" id="1"]\n[node name="Probe" type="Node"]\nscript=ExtResource("1")\n')
    (project / "export_presets.cfg").write_text(package_client.EXPORT_PRESETS)
    snapshots = {}
    for commit, stage in (("a" * 40, f["installed"]), ("b" * 40, f["stage"])):
        identity = {**f["identity"], "release_build": True, "commit": commit,
                    "ancestors": [commit, "a" * 40]}
        (project / "data/client_release.json").write_text(json.dumps(identity))
        (stage / "app/client-release.json").write_text(json.dumps(identity))
        for args in (["--headless", "--path", str(project), "--import"],
                     ["--headless", "--path", str(project), "--export-release", "Windows Desktop", str(stage / "app/RabbitLands.exe")]):
            result = subprocess.run([str(f["godot"]), *args], capture_output=True, text=True, timeout=90)
            assert result.returncode == 0 and "SCRIPT ERROR" not in result.stdout + result.stderr, result.stdout + result.stderr
        if commit.startswith("a"):
            snapshots = {path.name: path.read_bytes() for path in (stage / "app").iterdir() if path.is_file()}
    metadata = json.loads((f["stage"] / "app/client-release.json").read_text())
    payload = manifest(f["stage"], metadata, {kind: updater.read_bytes() for kind in ("updater", "uninstall")})
    payload["ancestors"] = metadata["ancestors"]
    (f["tmp_path"] / "RabbitLands-windows.json").write_text(json.dumps(signed(payload, f["key"])))
    for kind in ("updater", "uninstall"):
        shutil.copyfile(updater, f["installed"] / f"RabbitLands-{kind}.exe")
    for mode in ("", "--client-debug", "--client-compatibility", "--client-safe-mode"):
        for name, content in snapshots.items():
            (f["installed"] / "app" / name).write_bytes(content)
        (f["installed"] / "after.json").unlink(missing_ok=True)
        (f["installed"] / "request-update").touch()
        command = [str(f["installed"] / "RabbitLands-updater.exe"), "--headless", "--", "--root", str(f["installed"])]
        if mode:
            command.extend(["--launch-only", mode])
        original = subprocess.Popen(command, cwd=f["installed"] / "app", env=f["env"],
                                    stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        try:
            deadline = time.monotonic() + 50
            while time.monotonic() < deadline:
                if (f["installed"] / "after.json").exists() and not (f["installed"] / ".eloria-launcher-lock").exists():
                    break
                time.sleep(0.1)
            assert (f["installed"] / "after.json").exists(), mode
            before = json.loads((f["installed"] / "before.json").read_text())
            after = json.loads((f["installed"] / "after.json").read_text())
            assert before["managed"] and after["managed"], (before, after)
            assert before["commit"] == "a" * 40 and after["commit"] == "b" * 40
            assert before["engine"] == after["engine"] and before["user"] == after["user"], (mode, before, after)
            assert before["safe"] == after["safe"]
            assert before["context"] == after["context"] and before["verbose"] == after["verbose"]
            assert after["verbose"] == bool(mode)
            assert original.wait(timeout=5) == 0
        finally:
            if original.poll() is None:
                subprocess.run(["taskkill", "/PID", str(original.pid), "/T", "/F"], capture_output=True)
                original.wait(timeout=5)


# A stand-in game for the renderer relaunch handshake. Each start records what
# it was given, then follows the next step of relaunch-plan.json in the install
# root: optionally record settings (as RendererPolicy does before it asks for a
# restart), write the running lease (as ClientUpdates does) and stay a while,
# then exit with a code or crash the engine.
RELAUNCH_GAME = '''extends Node
const Release = preload("res://src/updates/release.gd")
func _ready() -> void:
    var root := OS.get_environment("ELORIA_INSTALL_ROOT")
    var steps: Array = Release.read_json(root.path_join("relaunch-plan.json")).get("runs", [])
    var done: Array = Release.read_json(root.path_join("relaunch-runs.json")).get("runs", [])
    var step: Dictionary = steps[done.size()] if done.size() < steps.size() else {"exit": 0}
    var encoded := OS.get_environment("RABBITLANDS_LAUNCH_CONTEXT")
    var context: Variant = JSON.parse_string(Marshalls.base64_to_utf8(encoded)) if encoded != "" else null
    done.append({"user": Array(OS.get_cmdline_user_args()), "context": context, "pid": OS.get_process_id(),
        "features": OS.get_environment("RABBITLANDS_LAUNCHER_FEATURES"),
        "lock_owner": Release.read_json(root.path_join(".eloria-launcher-lock/owner.json")).get("pid", 0)})
    Release.save_json(root.path_join("relaunch-runs.json"), {"runs": done})
    if step.has("settings"):
        var config := ConfigFile.new()
        config.load("user://eloria_hud.cfg")
        for key: String in step.settings:
            var value: Variant = step.settings[key]
            config.set_value("graphics", key, int(value) if value is float else value)
        config.save("user://eloria_hud.cfg")
    if step.get("lease", false):
        var cache := Release.cache_for(root)
        DirAccess.make_dir_recursive_absolute(cache)
        Release.save_json(cache.path_join("running-%d.json" % OS.get_process_id()), {"pid": OS.get_process_id()})
    if step.has("sleep"):
        OS.delay_msec(int(step.sleep))
    if step.get("crash", false):
        OS.crash("relaunch fixture crash")
    get_tree().quit(int(step.get("exit", 0)))
'''

# The updater runs headless here. These test seams make it compute the renderer
# arguments of a game with a display, while the game itself still starts headless.
# With relaunch-start-fails in the install root, every start after the first
# fails, and _fail records whether a backup removal was still running then.
RELAUNCH_LAUNCHER = ('func _game_headless() -> bool:\n\treturn false\n'
    'var _test_starts := 0\n'
    'func _start_process(path: String, game_args: PackedStringArray) -> int:\n'
    '\t_test_starts += 1\n'
    '\tif _test_starts > 1 and FileAccess.file_exists(_root.path_join("relaunch-start-fails")):\n'
    '\t\treturn -1\n'
    '\treturn super._start_process(path, PackedStringArray(["--headless"]) + game_args)\n'
    'func _fail(message: String) -> void:\n'
    '\tRelease.save_json(_root.path_join("relaunch-fail.json"), {"message": message,\n'
    '\t\t"cleanup_running": _backup_cleanup != null, "lock_held": DirAccess.dir_exists_absolute(_root.path_join(".eloria-launcher-lock"))})\n'
    '\tsuper._fail(message)\n')

TRIAL = {"auto_renderer": "mobile", "auto_renderer_basis": "integrated_gpu",
         "auto_renderer_adapter": "Intel(R) UHD Graphics 620", "auto_renderer_state": "trial",
         "auto_renderer_attempts": 1}


def settings_text(values):
    lines = ["[notes]", "", 'text="keep [graphics] notes"', "", "[graphics]", ""]
    for key, value in values.items():
        lines.append(f'{key}="{value}"' if isinstance(value, str) else f"{key}={value}")
    return "\n".join(lines) + "\n"


def settings_values(text):
    values, section = {}, ""
    for line in text.splitlines():
        if line.startswith("["):
            section = line.strip("[]")
        elif "=" in line and section == "graphics":
            key, value = line.split("=", 1)
            values[key] = value.strip('"') if value.startswith('"') else int(value) if value.lstrip("-").isdigit() else value
    return values


def engine_renderer(record):
    engine = record["context"]["engine"]
    return engine[engine.index("--rendering-method") + 1] if "--rendering-method" in engine else ""


@pytest.mark.skipif(os.name != "nt", reason="Native Windows export and process exit codes")
def test_exported_updater_relaunches_a_renderer_restart_once_and_gives_up_failed_trials(fixture):
    f = fixture
    updater = export_test_updater(f, "relaunch", launcher_methods=RELAUNCH_LAUNCHER)
    project = f["tmp_path"] / "relaunch-game"
    shutil.copytree(CLIENT / "src/updates", project / "src/updates")
    shutil.copytree(CLIENT / "assets/branding", project / "assets/branding")
    # The game and its updater share one user directory, as the real ones do.
    (project / "project.godot").write_text('config_version=5\n[application]\nconfig/name="Relaunch probe"\n'
        'config/use_custom_user_dir=true\nconfig/custom_user_dir_name="Godot/app_userdata/Eloria"\n'
        'run/main_scene="res://main.tscn"\n[rendering]\nrenderer/rendering_method="gl_compatibility"\n')
    (project / "main.gd").write_text(RELAUNCH_GAME)
    (project / "main.tscn").write_text('[gd_scene load_steps=2 format=3]\n[ext_resource type="Script" path="res://main.gd" id="1"]\n[node name="Probe" type="Node"]\nscript=ExtResource("1")\n')
    (project / "export_presets.cfg").write_text(package_client.EXPORT_PRESETS)
    installed = f["installed"]
    for args in (["--headless", "--path", str(project), "--import"],
                 ["--headless", "--path", str(project), "--export-release", "Windows Desktop", str(installed / "app/RabbitLands.exe")]):
        result = subprocess.run([str(f["godot"]), *args], capture_output=True, text=True, timeout=120)
        assert result.returncode == 0 and "SCRIPT ERROR" not in result.stdout + result.stderr, result.stdout + result.stderr
    for kind in ("updater", "uninstall"):
        shutil.copyfile(updater, installed / f"RabbitLands-{kind}.exe")
    settings = Path(f["env"]["APPDATA"]) / "Godot/app_userdata/Eloria/eloria_hud.cfg"
    settings.parent.mkdir(parents=True, exist_ok=True)

    def launch(initial, runs, *user, returncode=0):
        (installed / "relaunch-runs.json").unlink(missing_ok=True)
        (installed / "relaunch-plan.json").write_text(json.dumps({"runs": runs}))
        if initial is None:
            settings.unlink(missing_ok=True)
        else:
            settings.write_text(settings_text(initial))
        completed = subprocess.run([str(installed / "RabbitLands-updater.exe"), "--headless", "--", "--root",
            str(installed), "--launch-only", *user], cwd=installed / "app", env=f["env"], timeout=90,
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        assert completed.returncode == returncode
        assert not (installed / ".eloria-launcher-lock").exists(), "the launcher releases the lock when it ends"
        records = json.loads((installed / "relaunch-runs.json").read_text())["runs"]
        return records, settings.read_text() if settings.exists() else None

    # A fresh profile: the game records a trial, counts the restart and exits 75.
    records, text = launch(None, [{"exit": 75, "settings": {"renderer": "auto", **TRIAL}}, {"exit": 0}])
    assert len(records) == 2, records
    first, second = records
    # One launcher holds the installation lock for both starts.
    assert first["lock_owner"] and first["lock_owner"] == second["lock_owner"], records
    assert first["lock_owner"] not in (first["pid"], second["pid"])
    assert all("renderer-relaunch" in record["features"].split(",") for record in records), records
    assert first["pid"] != second["pid"]
    assert engine_renderer(first) == "" and engine_renderer(second) == "mobile", records
    assert "--graphics-renderer-restarted" not in first["user"]
    assert second["user"] == first["user"] + ["--graphics-renderer-restarted"], records
    assert second["context"]["user"] == second["user"], "the relaunched game gets its own launch context"
    assert settings_values(text)["auto_renderer_state"] == "trial"

    # The relaunched trial start fails at once: Automatic gives Mobile up ...
    records, text = launch({"renderer": "auto"}, [{"exit": 75, "settings": TRIAL}, {"exit": 3}])
    values = settings_values(text)
    assert len(records) == 2 and engine_renderer(records[1]) == "mobile", records
    assert values["auto_renderer_state"] == "failed_start", text
    assert values["auto_renderer"] == "mobile" and values["auto_renderer_attempts"] == 1, text
    assert 'text="keep [graphics] notes"' in text
    # ... and the next launch starts the project default.
    records, after = launch(values, [{"exit": 0}])
    assert len(records) == 1 and engine_renderer(records[0]) == "", records
    assert after == settings_text(values)

    # An engine crash on an ordinary trial start (no relaunch) counts as well.
    records, text = launch({"renderer": "auto", **TRIAL}, [{"crash": True}])
    assert len(records) == 1 and engine_renderer(records[0]) == "mobile", records
    assert settings_values(text)["auto_renderer_state"] == "failed_start", text

    # A second request is not relaunched, and 75 is no failure.
    records, text = launch(None, [{"exit": 75, "settings": {"renderer": "auto", **TRIAL}}, {"exit": 75}, {"exit": 0}])
    assert len(records) == 2, records
    assert settings_values(text)["auto_renderer_state"] == "trial"

    # Errors that are not a failed trial leave the settings alone.
    confirmed = {"renderer": "auto", **TRIAL, "auto_renderer_state": "ok", "auto_renderer_attempts": 0}
    for initial, user, renderer in ((confirmed, (), "mobile"),
                                    ({**TRIAL, "renderer": "forward_plus"}, (), "forward_plus"),
                                    ({"renderer": "auto", **TRIAL}, ("--client-compatibility",), "gl_compatibility")):
        records, text = launch(initial, [{"exit": 3}], *user)
        assert len(records) == 1 and engine_renderer(records[0]) == renderer, (initial, records)
        assert text == settings_text(initial), (initial, text)

    # The first start ran long enough to begin removing the previous
    # installation's backup, then asked for a relaunch that cannot start. The
    # removal is stopped before the lock is given up (no other updater may
    # install meanwhile).
    backup = installed / ".eloria-previous"
    (backup / "app").mkdir(parents=True, exist_ok=True)
    for index in range(8):
        (backup / "app" / f"old-{index}.bin").write_bytes(b"previous" * 64)
    (installed / "relaunch-fail.json").unlink(missing_ok=True)
    (installed / "relaunch-start-fails").write_text("")
    try:
        records, text = launch({"renderer": "auto"}, [{"lease": True, "sleep": 3000, "exit": 75}], returncode=1)
    finally:
        (installed / "relaunch-start-fails").unlink(missing_ok=True)
    assert len(records) == 1, records
    assert not backup.exists(), "the backup removal began during the first start"
    failed = json.loads((installed / "relaunch-fail.json").read_text())
    assert "could not start" in failed["message"] and failed["lock_held"], failed
    assert failed["cleanup_running"] is False, "the backup removal still ran when the lock was given up"
