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
        original = subprocess.Popen(command, env=f["env"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
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
