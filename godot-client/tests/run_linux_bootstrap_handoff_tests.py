"""Manual Linux/WSL regression for installer cleanup during updater handoff."""
import argparse
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import time


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--godot", type=Path, required=True)
    parser.add_argument("--template", type=Path, required=True)
    options = parser.parse_args()
    if os.name != "posix":
        parser.error("Run this check on Linux or in WSL.")
    godot = options.godot.resolve()
    template = options.template.resolve()
    source = Path(__file__).resolve().parents[1] / "src/updates"
    with tempfile.TemporaryDirectory(prefix="rabbitlands-handoff-") as directory:
        fixture = Path(directory)
        project = fixture / "project"
        scripts = project / "src/updates"
        scripts.mkdir(parents=True)
        for name in ("bootstrap.gd", "release.gd"):
            shutil.copyfile(source / name, scripts / name)
        (project / "project.godot").write_text(
            'config_version=5\n[application]\nconfig/name="Handoff regression"\n'
            'run/main_scene="res://main.tscn"\n'
            '[rendering]\nrenderer/rendering_method="gl_compatibility"\n')
        (project / "main.tscn").write_text(
            '[gd_scene load_steps=2 format=3]\n'
            '[ext_resource type="Script" path="res://probe.gd" id="1"]\n'
            '[node name="Probe" type="Node"]\nscript=ExtResource("1")\n')
        (project / "probe.gd").write_text('''extends Node
const Bootstrap = preload("res://src/updates/bootstrap.gd")
const Release = preload("res://src/updates/release.gd")
func _ready() -> void:
    var args := OS.get_cmdline_user_args()
    if args[0] == "--handoff":
        var root := args[1]
        var request := Release.read_json(args[2])
        Release.save_json(root.path_join("worker.json"), {
            "pid": OS.get_process_id(), "args": request.args})
        for attempt in 200:
            if FileAccess.file_exists(root.path_join("parent-cleaned")):
                get_tree().quit()
                return
            await get_tree().create_timer(0.05).timeout
        get_tree().quit(1)
    else:
        DirAccess.make_dir_recursive_absolute(Release.cache_for(args[0]))
        var error := Bootstrap.start_handoff(args[0], {}, args.slice(1))
        if error != "":
            push_error(error)
        get_tree().quit(0 if error == "" else 1)
''')
        (project / "export_presets.cfg").write_text(
            '[preset.0]\nname="Linux"\nplatform="Linux"\n'
            'export_filter="all_resources"\ninclude_filter="*.json"\n'
            '[preset.0.options]\n'
            f'custom_template/release={json.dumps(str(template))}\n'
            'binary_format/embed_pck=true\nbinary_format/architecture="x86_64"\n')
        env = dict(os.environ, HOME=str(fixture / "home"),
                   XDG_DATA_HOME=str(fixture / "data"),
                   XDG_CONFIG_HOME=str(fixture / "config"), GODOT_SILENCE_ROOT_WARNING="1")
        temporary = fixture / "installer temporary"
        temporary.mkdir()
        binary = temporary / "updater"
        for args in (["--import"], ["--export-release", "Linux", str(binary)]):
            result = subprocess.run([str(godot), "--headless", "--path", str(project), *args],
                                    env=env, capture_output=True, text=True, timeout=60)
            assert result.returncode == 0 and "SCRIPT ERROR" not in result.stdout + result.stderr, result.stdout + result.stderr
        binary.chmod(0o700)
        # Spaces and shell metacharacters must remain literal across the handoff.
        root = fixture / "Rabbit Lands ' $() ; installation"
        root.mkdir()
        forwarded = ["--install-manifest", "a path ' $() ; manifest.json", "--update-only"]
        log = fixture / "handoff.log"
        with log.open("w") as output:
            parent = subprocess.Popen([str(binary), "--headless", "--", str(root), *forwarded],
                                      cwd=temporary, env=env, stdout=output, stderr=subprocess.STDOUT)
            assert parent.wait(timeout=20) == 0, log.read_text()
            deadline = time.monotonic() + 15
            proof = root / "worker.json"
            while not proof.exists():
                assert time.monotonic() < deadline, log.read_text()
                time.sleep(0.05)
            worker = json.loads(proof.read_text())
            assert worker["args"] == forwarded, worker
            # Match the shell installer's trap after the first updater exits.
            shutil.rmtree(temporary)
            (root / "parent-cleaned").touch()
            status = Path(f'/proc/{worker["pid"]}/stat')
            while status.exists():
                try:
                    if status.read_text().split(") ", 1)[1].startswith("Z"):
                        break
                except FileNotFoundError:
                    break
                assert time.monotonic() < deadline, log.read_text()
                time.sleep(0.05)
        text = log.read_text()
        assert "ERROR:" not in text, text
        print("Linux installer handoff passed: temporary-folder cleanup, worker exit, literal paths and arguments.")


if __name__ == "__main__":
    main()
