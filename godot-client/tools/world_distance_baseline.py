"""World-distance baseline runner (wave 2 WD-C0): the camera-probe matrix, rendered.

Runs tests/integration/camera_rotation_probe.gd once per territory x configuration x repeat,
interleaved (repeat-major, so a drifting machine affects every configuration alike), in one
isolated user root per renderer (APPDATA, LOCALAPPDATA, XDG_DATA_HOME under the out dir; the
geometry cache is keyed by renderer family) that every run shares, so caches stay warm.
World geometry: `--geometry-cache prepare` (default) first runs the client's own explicit
preparation (`-- --prepare-map-geometry`, the cook a fresh source checkout otherwise starts
before login; all served maps, roughly 20-30 minutes once per renderer and out dir, so reuse
the out dir), and arrivals then read prepared geometry as installed players do.
`--geometry-cache off` sets ELORIA_NO_GEOMETRY_CACHE=1 instead (load-time batches; screening).
Every run turns the camera at all distance x pitch poses (default 26/90 m x -60/-35/-15 degrees) at the territory's
default spawn tile, the focus tools/world_draw_budget.py simulates. The summary keeps each
pose's last turn (the earlier turns carry first-use compilation): world GPU mean/p95, frame
mean/p95, visible and shadow draws/primitives, camera far plane and shadow distance.

Configurations (Graphics overrides on top of the probe's Performance preset):
    low-painted   {"quality": "low", "appearance": "painted_ground"}
    low-original  {"quality": "low", "appearance": "original"}   (GPU-03 / gate G3 A/B)
    high          {"quality": "high", "appearance": "painted_ground", "shadows": true, "render_scale": 1.0}
One GPU process at a time: the run holds the client benchmark lock and, with --gpu-lock-dir,
the machine's GPU lock directory. Nothing here edits player settings.

    python tools/world_distance_baseline.py --godot <exe> --out-dir <ignored dir> [--dry-run]
"""
from __future__ import annotations

import argparse
import datetime
import json
import os
from pathlib import Path
import subprocess
import sys
import time

PROJECT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT / "tests" / "integration"))
from crowd_benchmark_support import BenchmarkLock, EvidenceError, clean_environment, default_lock_path  # noqa: E402

PROBE = "res://tests/integration/camera_rotation_probe.gd"
MAPS = PROJECT.parent / "eloria-assets" / "maps" / "continent-v2"
CONFIGURATIONS = {
    "low-painted": {"quality": "low", "appearance": "painted_ground"},
    "low-original": {"quality": "low", "appearance": "original"},
    "high": {"quality": "high", "appearance": "painted_ground", "shadows": True, "render_scale": 1.0},
}
ERROR_MARKERS = ("SCRIPT ERROR", "ERROR:")
# Inherited switches every run clears before applying its own (besides the crowd runner's
# clean_environment): the probe's own settings (fps cap, vsync, load-only, pose settle, shader
# warmup) and the world/memory switches that change what a pose draws or keeps resident.
PROBE_PREFIXES = ("ELORIA_CAMERA_PROBE_", "ELORIA_CAMERA_SHADER_WARMUP")
WORLD_OVERRIDES = frozenset({"ELORIA_WORLD_DISTANCE", "ELORIA_NO_GEOMETRY_CACHE", "ELORIA_GEOMETRY_CONTAINER_REUSE",
                             "ELORIA_GEOMETRY_DIAGNOSTICS", "RABBITLANDS_MEMORY_CLASS", "ELORIA_ACTOR_IMAGES",
                             "ELORIA_ACTOR_VRAM_SELF_TEST", "RABBITLANDS_ACTOR_GEOMETRY", "RABBITLANDS_CAPE_MATH"})
SCHEMA = 1


def spawn_tile(territory: str, maps: Path = MAPS) -> list[int]:
    manifest = json.loads((maps / territory / "client" / "world.json").read_text(encoding="utf-8"))
    spawns = manifest.get("spawnPoints") or []
    spawn = next((point for point in spawns if point.get("default")), spawns[0] if spawns else {})
    tile = spawn.get("serverTile")
    if not (isinstance(tile, list) and len(tile) == 2):
        raise EvidenceError(f"{territory}: the default spawn has no serverTile")
    return [int(tile[0]), int(tile[1])]


def user_root(args) -> Path:
    return Path(args.out_dir) / "userdata" / args.renderer


def isolation_env(root: Path) -> dict:
    return {"APPDATA": str(root), "LOCALAPPDATA": str(root / "local"), "XDG_DATA_HOME": str(root)}


def engine_command(args, log: Path) -> list[str]:
    command = [str(args.godot), "--log-file", log.as_posix(), "--path", str(args.project), "--audio-driver", "Dummy",
               "--rendering-method", args.renderer, "--resolution", args.resolution]
    if args.gpu_index is not None:
        command += ["--gpu-index", str(args.gpu_index)]
    return command


def preparation(args) -> dict | None:
    """The one explicit geometry preparation for this renderer's shared user root."""
    if args.geometry_cache != "prepare":
        return None
    log = Path(args.out_dir) / f"prepare-{args.renderer}.log"
    root = user_root(args)
    return {"label": f"prepare-{args.renderer}", "userRoot": str(root), "log": str(log),
            "env": isolation_env(root), "command": engine_command(args, log) + ["--", "--prepare-map-geometry"]}


def plan(args) -> list[dict]:
    """Every run, repeat-major and interleaved, with its environment and Godot arguments."""
    out_dir = Path(args.out_dir)
    root = user_root(args)
    runs = []
    for repeat in range(1, args.repeats + 1):
        for territory in args.maps.split(","):
            tile = spawn_tile(territory, args.maps_dir)
            for name in args.configs.split(","):
                if name not in CONFIGURATIONS:
                    raise EvidenceError(f"unknown configuration {name}; known: {', '.join(CONFIGURATIONS)}")
                label = f"{territory}-{name}-{args.renderer}-r{repeat}"
                env = isolation_env(root) | {"ELORIA_CAMERA_PROBE_USER_ROOT": root.as_posix(),
                       "ELORIA_CAMERA_PROBE_REPORT": (out_dir / f"{label}.json").as_posix(),
                       "ELORIA_CAMERA_PROBE_MAP": territory, "ELORIA_CAMERA_PROBE_TILE": f"{tile[0]},{tile[1]}",
                       "ELORIA_CAMERA_PROBE_DISTANCE": args.distances, "ELORIA_CAMERA_PROBE_PITCH": args.pitches,
                       "ELORIA_CAMERA_PROBE_TURNS": str(args.turns),
                       "ELORIA_CAMERA_PROBE_MINUTE": str(args.minute),
                       "ELORIA_CAMERA_PROBE_GRAPHICS": json.dumps(CONFIGURATIONS[name], sort_keys=True),
                       "ELORIA_CAMERA_PROBE_ROTATION_FPS": str(args.rotation_fps),
                       "ELORIA_CAMERA_PROBE_MINIMAP": "hide"}
                if args.world_distance == "off":
                    env["ELORIA_WORLD_DISTANCE"] = "off"
                if args.geometry_cache == "off":
                    env["ELORIA_NO_GEOMETRY_CACHE"] = "1"
                command = engine_command(args, out_dir / f"{label}.log") + ["--script", PROBE]
                runs.append({"label": label, "territory": territory, "tile": tile, "configuration": name,
                             "graphics": CONFIGURATIONS[name], "repeat": repeat, "userRoot": str(root),
                             "report": str(out_dir / f"{label}.json"), "log": str(out_dir / f"{label}.log"),
                             "env": env, "command": command})
    return runs


def summarize(report: dict) -> list[dict]:
    """One row per pose: its last (warm) turn, the camera planes and the shadow fit."""
    rows = []
    for pose in report.get("poses", []):
        turns = pose.get("turns") or []
        if not turns:
            continue
        last = turns[-1]
        rows.append({"distance": pose.get("distance"), "pitch": pose.get("pitch"), "turn": last.get("turn"),
                     "worldGpuMeanMs": last.get("gpu_mean_ms"), "worldGpuP95Ms": last.get("gpu_p95_ms"),
                     "frameMeanMs": last.get("mean_ms"), "frameP95Ms": last.get("p95_ms"),
                     "renderCpuMeanMs": last.get("render_cpu_mean_ms"),
                     "drawCalls": last.get("draw_calls_mean"), "primitives": last.get("primitives_mean"),
                     "objects": last.get("objects_mean"), "shadowDrawCalls": last.get("shadow_draw_calls_mean"),
                     "shadowPrimitives": last.get("shadow_primitives_mean"),
                     "spikes": len(last.get("spikes") or []), "cameraFar": pose.get("camera_far"),
                     "cameraNear": pose.get("camera_near"), "sunShadows": pose.get("sun_shadows_enabled"),
                     "sunShadowMaxDistance": pose.get("sun_shadow_max_distance"),
                     "worldDistance": pose.get("world_distance")})
    return rows


def log_errors(path: Path) -> list[str]:
    if not path.is_file():
        return ["log missing"]
    lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
    return [line for line in lines if any(marker in line for marker in ERROR_MARKERS)][:40]


def _git_head(project: Path) -> str | None:
    try:
        return subprocess.run(["git", "-C", str(project), "rev-parse", "HEAD"], capture_output=True, text=True,
                              timeout=20, check=True).stdout.strip()
    except (OSError, subprocess.SubprocessError):
        return None


def abandoned_text(text: str) -> bool:
    """A complete probe report that leaves the process waiting to be terminated: an arrival
    failure, or a teardown that did not drain (its documented hand-over to the owning runner)."""
    try:
        report = json.loads(text)
    except ValueError:
        return False  # Not completely written yet.
    if not isinstance(report, dict):
        return False
    teardown = report.get("teardown")
    return bool(report.get("error")) or not (isinstance(teardown, dict) and teardown.get("ready") is True)


def abandoned(report_path: Path) -> bool:
    try:
        return abandoned_text(report_path.read_text(encoding="utf-8"))
    except OSError:
        return False


def wait_for(process: subprocess.Popen, report_path: Path, timeout: float, grace: float) -> tuple[int | None, str]:
    """Wait for the probe; terminate it at the timeout, or `grace` seconds after it hands over."""
    deadline = time.monotonic() + timeout
    handed_over = None
    while process.poll() is None:
        now = time.monotonic()
        if handed_over is None and report_path.is_file() and abandoned(report_path):
            handed_over = now
        if now >= deadline or (handed_over is not None and now - handed_over >= grace):
            process.kill()
            process.wait()
            return None, "timeout" if now >= deadline else "terminated_after_report"
        time.sleep(1)
    return process.returncode, "exited"


def _environment(run: dict) -> tuple[dict, list[str]]:
    Path(run["userRoot"]).mkdir(parents=True, exist_ok=True)
    Path(run["env"]["LOCALAPPDATA"]).mkdir(parents=True, exist_ok=True)
    env, cleared = clean_environment(dict(os.environ))
    probe = [name for name in env if name.startswith(PROBE_PREFIXES) or name in WORLD_OVERRIDES]
    for name in probe:
        env.pop(name)
    env.update(run["env"])
    return env, sorted(cleared + probe)


def _take_gpu_lock(gpu_lock_dir: Path | None) -> None:
    while gpu_lock_dir is not None:
        try:
            gpu_lock_dir.mkdir()
            return
        except FileExistsError:
            time.sleep(5)


def prepare(run: dict, timeout: float, gpu_lock_dir: Path | None) -> dict:
    """The client's explicit geometry preparation; it quits 0 and prints its report when done."""
    env, _ = _environment(run)
    Path(run["log"]).unlink(missing_ok=True)  # Never read an earlier preparation's report.
    _take_gpu_lock(gpu_lock_dir)
    started = time.monotonic()
    try:
        process = subprocess.Popen(run["command"], env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        try:
            exit_code = process.wait(timeout=timeout)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait()
            exit_code = None
    finally:
        if gpu_lock_dir is not None:
            gpu_lock_dir.rmdir()
    report = None
    log = Path(run["log"])
    if log.is_file():
        for line in log.read_text(encoding="utf-8", errors="replace").splitlines():
            if line.startswith("MAP_GEOMETRY_PREPARE "):
                try:
                    report = json.loads(line.removeprefix("MAP_GEOMETRY_PREPARE "))
                except ValueError:
                    report = None
    ok = exit_code == 0 and isinstance(report, dict) and report.get("ok") is True
    return {"label": run["label"], "seconds": round(time.monotonic() - started, 1), "exitCode": exit_code,
            "ok": ok, "report": report, "logErrors": log_errors(log)}


def execute(run: dict, timeout: float, gpu_lock_dir: Path | None, grace: float = 60.0) -> dict:
    env, cleared = _environment(run)
    _take_gpu_lock(gpu_lock_dir)
    started = time.monotonic()
    report_path = Path(run["report"])
    report_path.unlink(missing_ok=True)
    Path(run["log"]).unlink(missing_ok=True)
    try:
        process = subprocess.Popen(run["command"], env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        exit_code, ending = wait_for(process, report_path, timeout, grace)
    finally:
        if gpu_lock_dir is not None:
            gpu_lock_dir.rmdir()
    result = {key: run[key] for key in ("label", "territory", "tile", "configuration", "graphics", "repeat")}
    result.update(seconds=round(time.monotonic() - started, 1), exitCode=exit_code, ending=ending,
                  clearedEnvironment=cleared, logErrors=log_errors(Path(run["log"])))
    if report_path.is_file():
        try:
            report = json.loads(report_path.read_text(encoding="utf-8"))
        except (OSError, ValueError) as exc:  # Ended mid-write: keep the matrix going.
            report = {"error": f"unreadable probe report: {exc}"}
        if not isinstance(report, dict):
            report = {"error": "the probe report is not a JSON object"}
        result.update(renderer=report.get("renderer"), adapter=report.get("adapter"),
                      viewport=report.get("viewport"), appearance=report.get("appearance"),
                      settings=report.get("settings"), arrivalMs=report.get("arrival_ms"),
                      videoMemoryBytes=report.get("video_memory_bytes"), poses=summarize(report),
                      geometryPreparation=report.get("geometry_preparation"),
                      error=report.get("error"))
    result["valid"] = exit_code == 0 and not result["logErrors"] and bool(result.get("poses")) \
        and not result.get("error")
    return result


def parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("--godot", required=True, help="rendered Godot 4.7.2 editor executable")
    p.add_argument("--project", type=Path, default=PROJECT)
    p.add_argument("--out-dir", type=Path, required=True, help="evidence directory (keep it out of Git)")
    p.add_argument("--maps", default="landfall,suncoil")
    p.add_argument("--maps-dir", type=Path, default=MAPS)
    p.add_argument("--configs", default="low-painted,low-original,high")
    p.add_argument("--distances", default="26,90")
    p.add_argument("--pitches", default="-60,-35,-15", help="write --pitches=-60,-15 (a leading minus)")
    p.add_argument("--turns", type=int, default=2, help="per pose; the summary keeps the last")
    p.add_argument("--repeats", type=int, default=2)
    p.add_argument("--minute", type=int, default=600)
    p.add_argument("--rotation-fps", type=int, default=0, help="0 = uncapped frame costs (the probe default)")
    p.add_argument("--renderer", default="forward_plus", choices=["forward_plus", "mobile", "gl_compatibility"])
    p.add_argument("--resolution", default="1280x720")
    p.add_argument("--gpu-index", type=int)
    p.add_argument("--geometry-cache", default="prepare", choices=["prepare", "off"],
                   help="prepare: cook prepared world geometry once per renderer root first; "
                        "off: ELORIA_NO_GEOMETRY_CACHE=1 (load-time batches, screening)")
    p.add_argument("--prepare-timeout", type=float, default=5400)
    p.add_argument("--world-distance", default="on", choices=["on", "off"],
                   help="off sets ELORIA_WORLD_DISTANCE=off (meaningful once WD-C3 lands)")
    p.add_argument("--timeout", type=float, default=1800, help="seconds per probe run")
    p.add_argument("--abandon-after", type=float, default=60,
                   help="seconds to wait after the probe reports a failure or an undrained teardown before ending it")
    p.add_argument("--lock-path", type=Path)
    p.add_argument("--lock-timeout", type=float, default=0)
    p.add_argument("--gpu-lock-dir", type=Path, help="machine GPU lock directory to hold per run (mkdir lock)")
    p.add_argument("--dry-run", action="store_true")
    return p


def main(argv: list[str] | None = None) -> int:
    args = parser().parse_args(argv)
    try:
        if args.repeats < 1 or args.turns < 1 or args.timeout <= 0:
            raise EvidenceError("--repeats, --turns and --timeout must be positive")
        args.project = args.project.resolve()
        args.out_dir = args.out_dir.resolve()  # The probe's isolation guard compares absolute user roots.
        runs = plan(args)
    except (EvidenceError, OSError, ValueError) as exc:
        print(f"world_distance_baseline: {exc}", file=sys.stderr)
        return 2
    prepare_run = preparation(args)
    if args.dry_run:
        rows = ([prepare_run] if prepare_run else []) + runs
        print(json.dumps([{key: run[key] for key in ("label", "env", "command")} for run in rows], indent=1))
        return 0
    args.out_dir.mkdir(parents=True, exist_ok=True)
    results = []
    prepared = None
    with BenchmarkLock(args.lock_path or default_lock_path(args.project), args.lock_timeout, "world-distance"):
        if prepare_run is not None:
            print(f"world_distance_baseline: {prepare_run['label']} (once per renderer root)", flush=True)
            prepared = prepare(prepare_run, args.prepare_timeout, args.gpu_lock_dir)
            print(f"  ok={prepared['ok']} seconds={prepared['seconds']}", flush=True)
            if not prepared["ok"]:
                runs = []
        for run in runs:
            print(f"world_distance_baseline: {run['label']}", flush=True)
            results.append(execute(run, args.timeout, args.gpu_lock_dir, args.abandon_after))
            print(f"  valid={results[-1]['valid']} seconds={results[-1]['seconds']}", flush=True)
    summary = {"schema": SCHEMA, "tool": "world_distance_baseline", "probe": PROBE,
               "date": datetime.date.today().isoformat(), "gitHead": _git_head(args.project),
               "arguments": {key: str(value) for key, value in vars(args).items() if key != "dry_run"},
               "configurations": CONFIGURATIONS, "geometryPreparation": prepared,
               "valid": bool(results) and all(result["valid"] for result in results)
               and (prepared is None or prepared["ok"]), "runs": results}
    (args.out_dir / "world-distance-baseline.json").write_text(json.dumps(summary, indent=1) + "\n", encoding="utf-8")
    print(f"world_distance_baseline: {'valid' if summary['valid'] else 'INVALID'} -> "
          f"{args.out_dir / 'world-distance-baseline.json'}")
    return 0 if summary["valid"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
