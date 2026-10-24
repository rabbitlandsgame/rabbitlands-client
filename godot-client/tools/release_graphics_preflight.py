"""Qualify the actual release renderer before materializing any game assets."""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import signal
import subprocess
import time

import release_software_graphics as graphics

POLICY = "rl-early-release-graphics-preflight-v1"
TOOLS = Path(__file__).resolve().parent
SCRIPTS = ("release_graphics_probe.gd", "probe_release_software_graphics.gd")
MAX_LOG_BYTES = 4 * 1024**2
ANSI = re.compile(r"\x1b\[[0-?]*[ -/]*[@-~]")
ERROR = re.compile(r"(?m)^(?:USER )?(?:SCRIPT ERROR:|SHADER ERROR:|WARNING:|ERROR:|FATAL(?: ERROR)?:)|"
                   r"ObjectDB instances (?:were )?leaked|RID allocations.*leaked|"
                   r"Resources still in use at exit|Pages in use exist at exit|Leaked instance")
LINUX_VSYNC_WARNING = ("WARNING: Could not set V-Sync mode, as changing V-Sync mode "
                       "is not supported by the graphics driver.")
PRIVATE_ENV = frozenset(("GH_TOKEN", "GITHUB_TOKEN", "CLIENT_UPDATE_SIGNING_KEY", "ACTIONS_ID_TOKEN_REQUEST_TOKEN"))


def _checked(path):
    path = Path(path).absolute()
    for ancestor in (path, *path.parents):
        if ancestor.is_symlink() or ancestor.is_junction():
            raise ValueError("Graphics preflight path contains a link: " + str(ancestor))
    return path.resolve()


def _regular_tree(path):
    root = _checked(path)
    for directory, folders, files in os.walk(root, followlinks=False):
        for name in [*folders, *files]:
            child = Path(directory) / name
            if (child.is_symlink() or child.is_junction() or not child.resolve().is_relative_to(root)
                    or (name in files and not child.is_file())):
                raise ValueError("Graphics preflight scratch contains a nonregular input")
    return root


def _digest(path):
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def _write(path, value):
    path.write_text(json.dumps(value, sort_keys=True, indent=2) + "\n", encoding="utf-8")


def _stop(child):
    if child.poll() is not None:
        return
    if os.name == "nt":
        subprocess.run(["taskkill", "/PID", str(child.pid), "/T", "/F"],
                       capture_output=True, timeout=15, check=False)
    else:
        os.killpg(child.pid, signal.SIGTERM)
        try:
            child.wait(timeout=5)
        except subprocess.TimeoutExpired:
            os.killpg(child.pid, signal.SIGKILL)
    child.wait(timeout=15)


def run_preflight(config, godot, root, check_budget):
    """Keep failure evidence; retire owned project/user caches after success.

    Uses only two committed tool scripts and a standalone project without game
    autoloads. The full cooker independently repeats all real graphics gates.
    """
    root, godot = _checked(root), _checked(godot)
    if root.exists() or not godot.is_file() or godot.is_relative_to(root):
        raise ValueError("Graphics preflight requires fresh scratch and an external engine")
    scripts = {}
    for name in SCRIPTS:
        source = _checked(TOOLS / name)
        if not source.is_file() or source.stat().st_size > 128 * 1024:
            raise ValueError("Graphics preflight tool script is missing or oversized")
        scripts[name] = {"bytes": source.stat().st_size, "sha256": _digest(source)}
    check_budget("before standalone graphics preflight", 256 * 1024**2)
    root.mkdir(parents=True, exist_ok=False)
    project, users = root / "project", root / "users"
    (project / "tools").mkdir(parents=True)
    users.mkdir()
    for name, row in scripts.items():
        target = project / "tools" / name
        shutil.copyfile(TOOLS / name, target)
        if _digest(target) != row["sha256"]:
            raise ValueError("Graphics preflight script changed during copy")
    (project / "project.godot").write_text(
        'config_version=5\n[application]\nconfig/name="Rabbit Lands Release Graphics Probe"\n'
        'config/use_custom_user_dir=true\nconfig/custom_user_dir_name="RabbitLandsReleaseGraphicsProbe"\n'
        '[display]\nwindow/size/viewport_width=64\nwindow/size/viewport_height=64\n', encoding="utf-8")
    report_path, job_path = root / "report.json", root / "job.json"
    user_directory = users / "RabbitLandsReleaseGraphicsProbe"
    job = {"schema_version": 1, "platform": config["platform"], "expected_project_root": str(project),
           "expected_user_directory": str(user_directory), "expected_rendering_method": config["rendering_method"],
           "expected_rendering_driver": config["rendering_driver"], "report": str(report_path)}
    _write(job_path, job)
    owner = {"schema": 1, "policy": POLICY, "root": str(root), "project": str(project),
             "users": str(users), "engine_sha256": _digest(godot), "scripts": scripts}
    _write(root / "owner.json", owner)
    receipt = {**owner, "status": "running", "configuration": config}
    _write(root / "receipt.json", receipt)
    command = graphics.cook_command(config, [godot, "--path", project,
        "--position", "-32000,-32000", "--resolution", "64x64", "--log-file", root / "engine.log",
        "--script", "res://tools/probe_release_software_graphics.gd", "--", job_path])
    environment = {key: value for key, value in os.environ.items()
                   if key not in PRIVATE_ENV and not key.startswith(("ELORIA_", "RABBITLANDS_"))}
    environment = graphics.child_environment(config, environment)
    environment.update({key: str(users) for key in ("APPDATA", "LOCALAPPDATA", "XDG_DATA_HOME", "XDG_CONFIG_HOME")})
    child = None
    started = time.monotonic()
    try:
        with (root / "launch.log").open("x", encoding="utf-8") as stream:
            child = subprocess.Popen(command, cwd=root, env=environment, stdout=stream,
                stderr=subprocess.STDOUT, start_new_session=os.name != "nt")
            while child.poll() is None:
                if time.monotonic() - started > 120:
                    raise ValueError("Standalone graphics preflight exceeded 120 seconds")
                if sum(path.stat().st_size for path in (root / "launch.log", root / "engine.log") if path.exists()) > MAX_LOG_BYTES:
                    raise ValueError("Standalone graphics preflight exceeded its diagnostic bound")
                check_budget("running standalone graphics preflight")
                try:
                    child.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    pass
        # The entrypoint writes its actual observation before rejecting. Keep
        # and bind it even when the renderer classification fails.
        if sum(path.stat().st_size for path in (root / "launch.log", root / "engine.log") if path.exists()) > MAX_LOG_BYTES:
            raise ValueError("Standalone graphics preflight exceeded its diagnostic bound")
        if report_path.is_file() and report_path.stat().st_size > 1024**2:
            raise ValueError("Standalone graphics preflight observation is oversized")
        report = json.loads(report_path.read_text(encoding="utf-8-sig")) if report_path.is_file() else None
        receipt["report"] = report
        receipt["exit"] = child.returncode
        _write(root / "receipt.json", receipt)
        if child.returncode != 0:
            raise ValueError("Standalone graphics preflight failed; see " + str(root / "launch.log"))
        receipt["verification"] = graphics.validate_preflight_report(config, report,
            project=project, user_directory=user_directory, godot=godot)
        # Only a fully qualified Linux GL probe may ignore this exact driver
        # limitation. Preserve the original logs and explicitly receipt it;
        # all other warnings, errors and resource leaks still reject the run.
        allowed_warnings = set()
        for path in (root / "launch.log", root / "engine.log"):
            if not path.is_file():
                continue
            lines = ANSI.sub("", path.read_text(encoding="utf-8-sig", errors="replace")).splitlines()
            if (config["platform"] == "linux" and config["rendering_method"] == "gl_compatibility"
                    and config["rendering_driver"] == "opengl3"):
                if LINUX_VSYNC_WARNING in lines:
                    allowed_warnings.add(LINUX_VSYNC_WARNING)
                    lines = [line for line in lines if line != LINUX_VSYNC_WARNING]
            if ERROR.search("\n".join(lines)):
                raise ValueError("Engine diagnostic in standalone graphics preflight: " + str(path))
        receipt["allowed_driver_warnings"] = sorted(allowed_warnings)
        # Only scratch made by this call is disposable. Preserve all diagnostic
        # files and the verified report while reclaiming generated shaders.
        if json.loads((root / "owner.json").read_text()) != owner:
            raise ValueError("Graphics preflight ownership changed before cleanup")
        for directory, expected in ((project, root / "project"), (users, root / "users")):
            if _regular_tree(directory) != expected:
                raise ValueError("Graphics preflight cleanup escaped owned scratch")
        for directory in (project, users):
            shutil.rmtree(directory)
        receipt["status"] = "verified_scratch_retired"
        _write(root / "receipt.json", receipt)
        check_budget("standalone graphics preflight verified and scratch retired")
        return receipt
    except BaseException as error:
        receipt.update(status="failed", error=f"{type(error).__name__}: {error}")
        _write(root / "receipt.json", receipt)
        raise
    finally:
        if child is not None:
            _stop(child)
