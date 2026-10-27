"""Run isolated rendered continent camera routes; never alter player profiles.

Uses production streaming limits unless --budget-mib explicitly requests a
comparison. Process-cold is reported honestly; this does not clear OS caches.
"""
from __future__ import annotations

import argparse
import ctypes
import hashlib
import json
import math
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import time
import uuid

PROJECT = Path(__file__).resolve().parents[1]
ROOT = PROJECT.parent
sys.path.insert(0, str(PROJECT / "tests/integration"))
from crowd_benchmark_support import BenchmarkLock

POINTS = [[-205, 115, 14], [-149, 121, -17], [-115, 122, 6], [50.5, 106.15, 161.5]]


def percentile(values: list[float], quantile: float) -> float:
    """Nearest-rank percentile, including the worst observed frame at q=1."""
    if not values:
        return 0.0
    ordered = sorted(values)
    return ordered[max(0, min(len(ordered) - 1, math.ceil(len(ordered) * quantile) - 1))]


def frame_summary(frames: list[dict]) -> dict:
    durations = [float(row["frame_ms"]) for row in frames if float(row["frame_ms"]) > 0]
    return {"frames": len(durations), "p50_ms": percentile(durations, .5),
            "p95_ms": percentile(durations, .95), "p99_ms": percentile(durations, .99),
            "max_ms": max(durations, default=0),
            "over_33ms": sum(x > 33 for x in durations),
            "over_50ms": sum(x > 50 for x in durations),
            "over_100ms": sum(x > 100 for x in durations),
            "ground_missing_frames": sum(row["ground_hit"] is False for row in frames),
            "ground_probed_frames": sum(row["ground_hit"] is not None for row in frames),
            "focused_frames":sum(row.get("window_focused") is True for row in frames),
            "unfocused_frames":sum(row.get("window_focused") is False for row in frames),
            "bounds_not_resident_frames": sum(not row["resident"] for row in frames)}


def summarize(report: dict) -> dict:
    frames = report["frames"]
    phase_names = [row["id"] for row in report["phases"]]
    movement = [row for row in frames if row["phase"] not in ["arrival", "post_route_settle"]]
    memory = report["memory"]
    fields = ["resident_estimated_bytes", "texture_gpu_bytes", "buffer_gpu_bytes", "video_gpu_bytes", "static_bytes"]
    settle = next((row for row in report["phases"] if row["id"] == "post_route_settle"), {})
    arrival = next((row for row in report["phases"] if row["id"] == "arrival"), {})
    return {"ok": report["ok"], "scope": report["scope"], "movement": frame_summary(movement),
            "window_context":report.get("window_context",{}),"renderer":report.get("renderer"),"gpu":report.get("gpu"),
            "movement_and_settle":frame_summary([row for row in frames if row["phase"] != "arrival"]),
            "post_route_settle_ms":(settle.get("end_us",0)-settle.get("start_us",0))/1000,
            "arrival_wall_ms":(arrival.get("end_us",0)-arrival.get("start_us",0))/1000,
            "phase_wall_ms":{row["id"]:(row.get("end_us",0)-row.get("start_us",0))/1000 for row in report["phases"]},
            "arrival_readiness":{key:arrival.get(key) for key in ["radius_metres","radius_ready_cells","radius_total_cells","coverage_at_end"]},
            "phases": {name: frame_summary([x for x in frames if x["phase"] == name]) for name in phase_names},
            "peak_memory": {key: max((row.get(key, 0) for row in memory), default=0) for key in fields},
            "pipeline_counter_names": report.get("pipeline_counter_names", []),
            "configuration": report["configuration"]}


def engine_error(text: str) -> bool:
    return re.search(r"(?m)^[ \t]*(?:SCRIPT )?ERROR:",text) is not None


def process_memory_summary(samples: list[dict]) -> dict:
    return {"peak_process_rss_bytes":max((max(x.get("peak_rss_bytes",0),x.get("rss_bytes",0)) for x in samples),default=0),
            "peak_process_sampled_rss_bytes":max((x.get("rss_bytes",0) for x in samples),default=0),
            "process_memory_scope":"Windows PeakWorkingSetSize high-water mark observed during the run; separate sampled WorkingSetSize peak is also retained."}


def qualification_errors(report: dict | None, configuration: dict, configuration_sha: str,
                         initial_inputs: dict, final_inputs: dict, engine_output: str = "") -> list[str]:
    if report is None:
        return ["fresh_report_missing"]
    errors = []
    if engine_error(engine_output):
        errors.append("engine_error_in_complete_log")
    if report.get("configuration", {}).get("run_id") != configuration["run_id"]:
        errors.append("report_run_id_mismatch")
    if report.get("configuration_sha256") != configuration_sha:
        errors.append("report_configuration_digest_mismatch")
    if initial_inputs != final_inputs:
        errors.append("runtime_or_import_inputs_changed")
    if not report.get("ok"):
        errors.append("engine_checks_failed")
    movement = [x for x in report.get("frames", []) if x.get("phase") not in ["arrival", "post_route_settle"]]
    if not movement:
        errors.append("measured_movement_missing")
    if configuration.get("ground_probe") is False:
        errors.append("terrain_deadline_probe_disabled")
    elif any(row.get("ground_hit") is False for row in movement):
        errors.append("movement_ground_missing")
    if any(row.get("resident") is False for row in movement):
        errors.append("movement_bounds_not_resident")
    return errors


def trim_route(points: list[list[float]], metres: float) -> list[list[float]]:
    if metres <= 0:
        return points
    result = [points[0]]
    for start, end in zip(points, points[1:]):
        length = math.dist(start, end)
        if metres <= length:
            result.append([a + (b - a) * metres / length for a, b in zip(start, end)])
            break
        result.append(end)
        metres -= length
    return result


def input_identity() -> dict:
    paths = [PROJECT / "src/world/continent_chunk_stream.gd", PROJECT / "src/world/world_loader.gd",
             PROJECT / "src/world/look/look_ground.gd", PROJECT / "src/world/map_image_extension.gd",
             PROJECT / "src/world/external_mesh_pool.gd",PROJECT / "src/world/external_texture_pool.gd",
             PROJECT / "src/world/map_mesh_extension.gd",PROJECT / "src/world/map_material_preparation.gd",
             PROJECT / "src/world/map_collision_cache.gd", PROJECT / "src/world/map_paving_cache.gd", PROJECT / "src/app/main.gd",
             PROJECT / "src/world/map_geometry_cache.gd",PROJECT / "src/world/map_geometry_policy.gd",
             PROJECT / "src/world/map_scene_cache.gd",PROJECT / "src/world/vram_textures.gd",
             PROJECT / "src/world/graphics_options.gd",PROJECT / "src/world/chunk_surface_refresh.gd",
             PROJECT / "src/world/season_surfaces.gd",PROJECT / "project.godot",
             PROJECT / "override.cfg",
             PROJECT / "tests/integration/crowd_benchmark_main.gd",
             PROJECT / "tests/integration/continent_stream_benchmark.gd",
             PROJECT / "tests/integration/continent_stream_benchmark_main.gd",
             PROJECT / "tests/integration/continent_stream_benchmark_main_fixture.gd", Path(__file__)]
    for path in (PROJECT / "src/world/look/textures").glob("*.png.import"):
        paths.append(path)
        imported = re.search(r'^path="res://([^"]+)"', path.read_text(encoding="utf-8"), re.MULTILINE)
        if imported:
            paths.append(PROJECT / imported.group(1))
    for relative in ["continent-v2/_continent_v2/shared-assets/vram/index.json",
                     "nymara-regions/_continent/shared-assets/vram/index.json"]:
        paths.append(ROOT / "eloria-assets/maps" / relative)
    result = {}
    for path in paths:
        if path.is_file():
            result[path.relative_to(ROOT).as_posix()] = {"sha256": hashlib.sha256(path.read_bytes()).hexdigest(), "bytes": path.stat().st_size}
    return result


def disk_inventory(profile: Path) -> dict:
    """Logical product bytes and file-identity dedup; not guessed GPU memory."""
    indexes = [ROOT / "eloria-assets/maps" / relative for relative in
               ["continent-v2/_continent_v2/shared-assets/vram/index.json",
                "nymara-regions/_continent/shared-assets/vram/index.json"]]
    files = set()
    indexed_contents = set()
    content_bytes = {}
    for path in indexes:
        if not path.is_file():
            continue
        files.add(path)
        index = json.loads(path.read_text(encoding="utf-8"))
        for sha, entry in index.get("images", {}).items():
            file = (path.parent.parent / entry.get("pool", "") / "vram" / entry["file"]).resolve()
            if not file.is_relative_to(ROOT.resolve()):
                raise ValueError("Sidecar path escapes task workspace")
            if file.is_file():
                files.add(file)
                indexed_contents.add(sha)
                content_bytes[entry["sha256"]] = file.stat().st_size
    identities = {}
    for path in files:
        stat = path.stat()
        identities[(stat.st_dev, stat.st_ino)] = stat.st_size
    class_products = {key: value for key, value in input_identity().items() if key.endswith(".ctex")}
    return {"sidecar_indexed_texture_contents": len(indexed_contents), "sidecar_product_files":len(files),
            "sidecar_logical_bytes_including_indexes":sum(path.stat().st_size for path in files),
            "sidecar_file_identity_deduplicated_bytes":sum(identities.values()),
            "sidecar_unique_content_payload_bytes":sum(content_bytes.values()),
            "class_ctex_bytes":sum(value["bytes"] for value in class_products.values()),
            "profile_logical_bytes":sum(p.stat().st_size for p in profile.rglob("*") if p.is_file()) if profile.exists() else 0,
            "scope":"Logical file sizes; file-identity dedup recognizes hard links. Filesystem allocation/compression and OS cache residency are not inferred."}


def seed_cache(user_root: Path | None, profile: Path, cache: str, extensions: list[str]) -> dict:
    if user_root is None:
        return {"files": 0, "bytes": 0, "sha256": {}}
    user_root = user_root.resolve()
    if not user_root.is_relative_to((ROOT / ".local").resolve()):
        raise ValueError("Cache seed must be task-owned ignored data")
    source = user_root / "Godot/app_userdata/Eloria" / cache
    if not source.is_dir():
        raise ValueError("Cache seed directory does not exist: " + str(source))
    if not source.resolve().is_relative_to(user_root):
        raise ValueError("Cache seed directory escapes its task-owned root")
    target = profile / "Godot/app_userdata/Eloria" / cache
    if not profile.resolve().is_relative_to((ROOT/".local").resolve()) or not target.resolve().is_relative_to(profile.resolve()):
        raise ValueError("Cache seed destination escapes its isolated task profile")
    identities = {}
    size = 0
    for path in sorted(source.rglob("*")):
        if not path.is_file() or path.suffix not in extensions:
            continue
        if path.is_symlink() or not path.resolve().is_relative_to(source.resolve()):
            raise ValueError("Unexpected cache link")
        relative = path.relative_to(source)
        destination = target / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(path, destination)
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        if hashlib.sha256(destination.read_bytes()).hexdigest() != digest:
            raise ValueError("Cache seed copy differs")
        identities[relative.as_posix()] = digest
        size += path.stat().st_size
    if not identities:
        raise ValueError("Cache seed has no products")
    return {"files": len(identities), "bytes": size, "sha256": identities}


def seed_collision_cache(user_root: Path | None, profile: Path) -> dict:
    return seed_cache(user_root,profile,"map-collision-cache",[".json",".rlc"])


def seed_paving_cache(user_root: Path | None, profile: Path) -> dict:
    return seed_cache(user_root,profile,"map-paving-cache",[".json",".res"])


class ProcessSampler:
    """Own-child RSS and logical I/O counters; no system-wide disk attribution."""
    def __init__(self, pid: int):
        self.handle = None
        if os.name != "nt":
            return
        from ctypes import wintypes
        self.kernel = ctypes.WinDLL("kernel32", use_last_error=True)
        self.psapi = ctypes.WinDLL("psapi", use_last_error=True)
        self.kernel.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
        self.kernel.OpenProcess.restype = wintypes.HANDLE
        self.kernel.CloseHandle.argtypes = [wintypes.HANDLE]
        self.handle = self.kernel.OpenProcess(0x0400 | 0x0010, False, pid)
        class Memory(ctypes.Structure):
            _fields_ = [("cb", wintypes.DWORD), ("PageFaultCount", wintypes.DWORD)] + [(name, ctypes.c_size_t) for name in
                ["PeakWorkingSetSize", "WorkingSetSize", "QuotaPeakPagedPoolUsage", "QuotaPagedPoolUsage",
                 "QuotaPeakNonPagedPoolUsage", "QuotaNonPagedPoolUsage", "PagefileUsage", "PeakPagefileUsage", "PrivateUsage"]]
        class Io(ctypes.Structure):
            _fields_ = [(name, ctypes.c_ulonglong) for name in ["ReadOperationCount", "WriteOperationCount", "OtherOperationCount",
                                                               "ReadTransferCount", "WriteTransferCount", "OtherTransferCount"]]
        self.Memory, self.Io = Memory, Io
        self.psapi.GetProcessMemoryInfo.argtypes = [wintypes.HANDLE, ctypes.POINTER(Memory), wintypes.DWORD]
        self.kernel.GetProcessIoCounters.argtypes = [wintypes.HANDLE, ctypes.POINTER(Io)]

    def sample(self) -> dict:
        row = {"monotonic_ns": time.perf_counter_ns(), "unix_ms": time.time() * 1000}
        if not self.handle:
            return row
        memory = self.Memory()
        memory.cb = ctypes.sizeof(memory)
        if self.psapi.GetProcessMemoryInfo(self.handle, ctypes.byref(memory), ctypes.sizeof(memory)):
            row.update(rss_bytes=memory.WorkingSetSize, peak_rss_bytes=memory.PeakWorkingSetSize,
                       private_bytes=memory.PrivateUsage, page_fault_count=memory.PageFaultCount)
        io = self.Io()
        if self.kernel.GetProcessIoCounters(self.handle, ctypes.byref(io)):
            row.update(logical_read_bytes=io.ReadTransferCount, logical_write_bytes=io.WriteTransferCount,
                       logical_read_operations=io.ReadOperationCount)
        return row

    def close(self):
        if self.handle:
            self.kernel.CloseHandle(self.handle)
            self.handle = None


def main() -> int:
    global PROJECT
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--godot", type=Path, default=Path("C:/rabbitlands/rabbitlands-client/godot-client/Godot_v4.7.2-stable_win64.exe"))
    parser.add_argument("--output", type=Path)
    parser.add_argument("--project",type=Path,default=PROJECT,help="Task project or ignored configuration overlay; never the primary checkout")
    parser.add_argument("--variant", default="baseline")
    parser.add_argument("--route-metres", type=float, default=160)
    parser.add_argument("--walk-speed", type=float, default=5)
    parser.add_argument("--fast-speed", type=float, default=10)
    parser.add_argument("--speed-order", choices=["walk-first", "fast-first"], default="walk-first")
    parser.add_argument("--no-ground-probe", action="store_true", help="Diagnostic only: cannot qualify terrain readiness")
    parser.add_argument("--main-listeners", action="store_true", help="Offline actual Main listener fixture; no server/player replay")
    parser.add_argument("--arrival-radius",type=int,choices=[36,64],default=36,help="Explicit curtain-readiness tradeoff; does not change selection/import policy")
    parser.add_argument("--repeats", type=int, default=1)
    parser.add_argument("--fps-limit", type=int, default=60)
    parser.add_argument("--budget-mib", type=int, choices=[0, 256, 512, 768], default=0)
    parser.add_argument("--mip-skip", type=int, choices=[0, 1, 2], default=0)
    parser.add_argument("--sidecars", choices=["auto", "off"], default="auto")
    parser.add_argument("--collision-user-root", type=Path, help="Copy faces-only cache products into isolated profile; never copy full geometry/player data")
    parser.add_argument("--paving-user-root",type=Path,help="Copy paving-only cache products into isolated profile")
    parser.add_argument("--env", action="append", default=[])
    parser.add_argument("--timeout", type=float, default=900)
    parser.add_argument("--parse-only", action="store_true")
    args = parser.parse_args()
    selected_project = args.project.resolve()
    if selected_project != PROJECT.resolve() and not selected_project.is_relative_to((ROOT/".local").resolve()):
        parser.error("Project must be this task's project or an ignored task overlay")
    if not (selected_project/"project.godot").is_file():
        parser.error("Selected project has no project.godot")
    PROJECT = selected_project
    output = (args.output or ROOT / ".local/continent-stream-smoothing" /
              (time.strftime("%Y%m%d-%H%M%S") + "-" + args.variant)).resolve()
    if not output.is_relative_to((ROOT / ".local").resolve()):
        parser.error("Output must be inside this task's ignored .local directory")
    output.mkdir(parents=True, exist_ok=True)
    profile = output / "profile"
    if not profile.resolve().is_relative_to(output) or (profile.is_dir() and any(profile.iterdir())):
        parser.error("Output profile must be fresh and contained in this output directory")
    config_path, report_path = output / "configuration.json", output / "report.json"
    if report_path.exists():
        parser.error("Output already contains a report; choose a fresh output directory to preserve evidence")
    config = {"run_id": uuid.uuid4().hex, "variant": args.variant, "manifest": "res://../eloria-assets/maps/continent-v2/landfall/client/world.json",
              "project_path":str(PROJECT),
              "project_override_sha256":hashlib.sha256((PROJECT/"override.cfg").read_bytes()).hexdigest() if (PROJECT/"override.cfg").exists() else None,
              "points": trim_route(POINTS, args.route_metres), "walk_speed": args.walk_speed,
              "fast_speed": args.fast_speed, "repeats": args.repeats, "fps_limit": args.fps_limit,
              "budget_mib": args.budget_mib, "mip_skip": args.mip_skip, "sidecars": args.sidecars,
              "speed_order": args.speed_order, "ground_probe": not args.no_ground_probe,
              "main_listeners":args.main_listeners,
              "arrival_radius":args.arrival_radius,
              "environment_overrides": args.env,
              "process_cache_state": "fresh process; OS/driver cache state uncontrolled"}
    config_path.write_text(json.dumps(config, indent=2), encoding="utf-8")
    configuration_sha = hashlib.sha256(config_path.read_bytes()).hexdigest()
    identity = input_identity()
    collision_seed = seed_collision_cache(args.collision_user_root, profile)
    paving_seed = seed_paving_cache(args.paving_user_root,profile)
    (output / "collision-seed.json").write_text(json.dumps(collision_seed, indent=2), encoding="utf-8")
    (output / "paving-seed.json").write_text(json.dumps(paving_seed,indent=2),encoding="utf-8")
    disk_before = disk_inventory(profile)
    (output / "inputs.json").write_text(json.dumps(identity, indent=2), encoding="utf-8")
    env = {key: value for key, value in os.environ.items() if not key.startswith(("ELORIA_", "RABBITLANDS_", "RL_"))}
    env.update(APPDATA=str(profile), LOCALAPPDATA=str(profile), XDG_DATA_HOME=str(profile), XDG_CONFIG_HOME=str(profile),
               RL_CONTINENT_BENCH_CONFIG=str(config_path), RL_CONTINENT_BENCH_REPORT=str(report_path),
               RABBITLANDS_OPTIMIZATION_PROFILE="legacy", RABBITLANDS_PREPARED_CONTENT="raw",
               RABBITLANDS_CROWD_BENCH_START_TOKEN=config["run_id"],
               ELORIA_VRAM_TEXTURES="auto" if args.sidecars == "auto" else "0")
    for override in args.env:
        key, separator, value = override.partition("=")
        if not separator or not key.startswith(("ELORIA_", "RABBITLANDS_")):
            parser.error("--env requires an explicit ELORIA_ or RABBITLANDS_ key=value")
        env[key] = value
    command = [str(args.godot.resolve()), "--path", str(PROJECT), "--script",
               "res://tests/integration/continent_stream_benchmark.gd", "--audio-driver", "Dummy"]
    if args.parse_only:
        command.extend(["--headless", "--check-only"])
    else:
        command.extend(["--rendering-method", "forward_plus", "--resolution", "1280x720", "--position", "-16000,-16000"])
    command.extend(["--log-file", str(output / "engine.log")])
    samples, failure = [], ""
    started = time.perf_counter()
    with BenchmarkLock(Path("C:/rabbitlands/.benchmark-locks/client-performance.lock"), label="continent-stream-benchmark"):
        with (output / "stdout.log").open("w", encoding="utf-8") as log:
            process_started_monotonic_ns = time.perf_counter_ns()
            process_started_unix_ms = time.time()*1000
            process = subprocess.Popen(command, env=env, stdout=log, stderr=subprocess.STDOUT, creationflags=subprocess.CREATE_NO_WINDOW)
            sampler = ProcessSampler(process.pid)
            try:
                while process.poll() is None:
                    samples.append(sampler.sample())
                    time.sleep(.25)
                    text = (output / "stdout.log").read_text(encoding="utf-8", errors="replace")
                    if engine_error(text):
                        failure = "engine_error"
                        break
                    if time.perf_counter() - started > args.timeout:
                        failure = "timeout"
                        break
                if failure and process.poll() is None:
                    process.terminate()
                process.wait(timeout=15)
            finally:
                if process.poll() is None:
                    process.kill()
                    process.wait(timeout=15)
                sampler.close()
    complete_log = (output/"stdout.log").read_text(encoding="utf-8",errors="replace")
    if (output/"engine.log").exists():
        complete_log += "\n"+(output/"engine.log").read_text(encoding="utf-8",errors="replace")
    # Shutdown can log an error and exit0 between polling iterations. Inspect
    # both complete logs after the child has exited before qualifying evidence.
    if engine_error(complete_log):
        failure = failure or "engine_error"
    (output / "process-samples.json").write_text(json.dumps(samples, indent=2), encoding="utf-8")
    result = {"exit": process.returncode, "failure": failure, "output": str(output),
              "process_started_monotonic_ns":process_started_monotonic_ns,"process_started_unix_ms":process_started_unix_ms,
              "collision_seed_files":collision_seed["files"], "collision_seed_bytes":collision_seed["bytes"],
              "paving_seed_files":paving_seed["files"],"paving_seed_bytes":paving_seed["bytes"],
              "process_io_scope": "Windows per-process logical transfer counters, includes page-cache IO; not physical disk bytes"}
    result.update(process_memory_summary(samples))
    report = None
    if report_path.exists():
        report = json.loads(report_path.read_text(encoding="utf-8"))
        result.update(summarize(report))
        result["inputs_unchanged"] = input_identity() == identity
        result["disk_before"] = disk_before
        result["disk_after"] = disk_inventory(profile)
    if not args.parse_only:
        result["qualification_errors"] = qualification_errors(report, config, configuration_sha, identity, input_identity(),complete_log)
        result["qualified"] = not result["qualification_errors"] and not failure and process.returncode == 0
    (output / "summary.json").write_text(json.dumps(result, indent=2), encoding="utf-8")
    print(json.dumps(result, indent=2))
    if process.returncode or failure:
        print((output / "stdout.log").read_text(encoding="utf-8", errors="replace")[-6000:])
    return 1 if process.returncode or failure or result.get("ok") is False or result.get("qualified") is False else 0


if __name__ == "__main__":
    raise SystemExit(main())
