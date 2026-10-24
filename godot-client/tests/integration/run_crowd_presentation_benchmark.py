#!/usr/bin/env python3
"""Run isolated, serialized crowd workloads and retain validated evidence.

Use --variants all for the current client. Historical phase4/quick selectors and
the live/stress/replay drivers retain their workloads. --cells phase1 selects
the additional mounted, combat and traversal reference cells. A source project
is not an exported package: --executable-mode exported requires an explicit
benchmark PCK or package artifact manifest and standalone runtime attestation.

Replay recordings and their raw reports contain player data. Replay output must
remain outside the repository; summaries omit the recording path and contents.
The advisory lock coordinates participating launchers, not unrelated programs.
"""
from __future__ import annotations

import argparse
import json
import math
import os
from pathlib import Path
import platform
import re
import subprocess
import sys
import tempfile
import time
import uuid

from process_memory_sampler import ProcessMemorySampler

from crowd_benchmark_support import (
    BenchmarkLock, EvidenceError, asset_files, clean_environment, configure_prepared_profile, configure_settings_profile, default_lock_path,
    hash_files, manifest_identity, read_json, require_private_replay_output,
    seed_settings_profile, selected_cells, sha256_file, source_files, validate_report, validate_startup_ack,
)

CLIENT = Path(__file__).resolve().parents[2]
SCRIPT = "res://tests/integration/crowd_presentation_benchmark.gd"


def set_affinity(pid: int, mask: int) -> int | None:
    """Apply and observe affinity on the process we created, never by process name."""
    if mask <= 0:
        return None
    if os.name != "nt":
        if not hasattr(os, "sched_setaffinity"):
            return None
        try:
            os.sched_setaffinity(pid, {n for n in range(mask.bit_length()) if mask & (1 << n)})
            return sum(1 << n for n in os.sched_getaffinity(pid))
        except OSError:
            return None
    import ctypes
    from ctypes import wintypes
    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
    kernel.OpenProcess.restype = wintypes.HANDLE
    kernel.SetProcessAffinityMask.argtypes = [wintypes.HANDLE, ctypes.c_size_t]
    kernel.GetProcessAffinityMask.argtypes = [wintypes.HANDLE, ctypes.POINTER(ctypes.c_size_t),
                                            ctypes.POINTER(ctypes.c_size_t)]
    kernel.CloseHandle.argtypes = [wintypes.HANDLE]
    handle = kernel.OpenProcess(0x0200 | 0x0400, False, pid)
    if not handle:
        return None
    try:
        if not kernel.SetProcessAffinityMask(handle, mask):
            return None
        observed, system = ctypes.c_size_t(), ctypes.c_size_t()
        if not kernel.GetProcessAffinityMask(handle, ctypes.byref(observed), ctypes.byref(system)):
            return None
        return observed.value
    finally:
        kernel.CloseHandle(handle)


def machine() -> dict:
    return {"platform": platform.platform(), "machine": platform.machine(),
            "python": platform.python_version(), "logicalProcessors": os.cpu_count()}


def resolution(value: str) -> tuple[int, int]:
    match = re.fullmatch(r"([1-9][0-9]*)[xX]([1-9][0-9]*)", value)
    if not match or not 320 <= int(match[1]) <= 7680 or not 240 <= int(match[2]) <= 4320:
        raise argparse.ArgumentTypeError("resolution must be WIDTHxHEIGHT, 320x240 through 7680x4320")
    return tuple(map(int, match.groups()))


def admission_budget(value: str) -> int:
    try:
        result = int(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError("admission budget must be an integer MiB value") from exc
    if not 64 <= result <= 8192:
        raise argparse.ArgumentTypeError("admission budget must be 64 through 8192 MiB")
    return result


def executable_path(value: str) -> Path:
    path = Path(value).resolve()
    if path.stem.endswith("_console"):
        sibling = path.with_name(path.stem.removesuffix("_console") + path.suffix)
        if not sibling.is_file():
            raise EvidenceError("console wrapper has no sibling executable for process affinity")
        path = sibling
    if not path.is_file():
        raise EvidenceError("Godot executable does not exist")
    return path


def request_for(args) -> dict:
    return {"mode": args.mode, "renderer": args.renderer, "quality": args.quality,
            "resolution": args.resolution, "map": args.map, "minimap": args.minimap,
            "fps_cap": args.fps_cap, "sample_ms": args.sample_ms, "warmup_ms": args.warmup_ms,
            "driver": args.driver, "body_cap": args.body_cap, "cells": args.cells,
            "replay": bool(args.replay), "executable_mode": args.executable_mode,
            "native_reducer": args.native_reducer, "native_presentation": args.native_presentation,
            "remote_presentation": getattr(args, "remote_presentation", "legacy"),
            "client_runtime": args.client_runtime, "rust_effects": args.rust_effects,
            "resource_admission": args.resource_admission,
            "resource_admission_budget_mib": args.resource_admission_budget_mib,
            "prepared_content": getattr(args, "prepared_content", "raw"),
            "prepared_node_policy": getattr(args, "prepared_node_policy", "retain"),
            "capture_boundaries": args.capture_boundaries,
            "tuning": args.tuning, "diagnostics": args.diagnostics, "executable": str(args.godot),
            "presence": args.presence, "server_time": args.server_time,
            "settings_profile": args.settings_profile}


def command_for(args, log: Path) -> list[str]:
    command = [str(args.godot)]
    if args.executable_mode == "project":
        command += ["--path", str(args.project_path)]
    elif args.main_pack:
        command += ["--main-pack", str(args.main_pack)]
    command += ["--audio-driver", "Dummy", "--log-file", str(log)]
    if args.mode == "headless":
        command.append("--headless")
    else:
        command += ["--rendering-method", args.renderer,
                    "--resolution", f"{args.resolution[0]}x{args.resolution[1]}"]
    if args.executable_mode == "project":
        command += ["--script", args.benchmark_script]
    elif args.benchmark_script != SCRIPT:
        raise EvidenceError("exported workloads use the package's benchmark main loop; custom --benchmark-script is unsupported")
    return command


def wait_for_startup(process, path: Path, request: dict, timeout: float) -> dict:
    """A release template may ignore --script; prove routing before the long wait."""
    deadline = time.monotonic() + timeout
    while True:
        if path.is_file():
            if path.stat().st_size > 16384:
                raise EvidenceError("startup acknowledgement is unexpectedly large")
            return validate_startup_ack(read_json(path), request)
        code = process.poll()
        if code is not None:
            raise EvidenceError(f"engine exited before benchmark startup acknowledgement ({code})")
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise EvidenceError(f"benchmark startup acknowledgement was not received within {timeout:g} seconds")
        time.sleep(min(.05, remaining))


def wait_for_workload(process, failure_path: Path, request: dict,
                      timeout: float, memory_sampler=None) -> tuple[int | str, dict | None]:
    """Poll the small failure marker and bounded optional owned-process counters."""
    deadline = time.monotonic() + timeout
    while True:
        if failure_path.is_file():
            if failure_path.stat().st_size > 16384:
                raise EvidenceError("teardown failure marker is unexpectedly large")
            data = validate_startup_ack(read_json(failure_path), request)
            if data.get("requiresRunnerTermination") is not True or data.get("failure") != "teardown_timeout" \
                    or not isinstance(data.get("teardown"), dict) or data["teardown"].get("ready") is not False:
                raise EvidenceError("invalid benchmark teardown failure marker")
            if process.poll() is None:
                process.kill()
            process.wait()
            return "teardown-failed", data
        now = time.monotonic()
        if memory_sampler is not None:
            memory_sampler.sample_if_due(now)
        remaining = deadline - now
        if remaining <= 0:
            raise subprocess.TimeoutExpired(process.args, timeout)
        try:
            return process.wait(timeout=min(.1, remaining)), None
        except subprocess.TimeoutExpired:
            continue


def identity(args) -> dict:
    maps = list(dict.fromkeys([args.map or "four_gates", *args.asset_map]))
    if any(name.startswith("traversal-") for name in selected_cells(args.cells, bool(args.replay))):
        maps = list(dict.fromkeys(maps + ["whitehorn_range", "mirrorhold", "amethyst_barrens",
                                         "amethyst_barrens_secrets", "sunmane_steppe"]))
    result = {"source": hash_files(source_files(args.project_path), args.project_path.parent),
              "executable": {"path": str(args.godot), "sha256": sha256_file(args.godot)},
              "executionKind": "source-project" if args.executable_mode == "project"
              else "exported-local-benchmark"}
    commit = subprocess.run(["git", "-C", str(args.project_path), "rev-parse", "HEAD"],
                            text=True, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
    status = subprocess.run(["git", "-C", str(args.project_path), "status", "--porcelain", "--untracked-files=normal"],
                            text=True, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
    result["sourceRevision"] = {"commit": commit.stdout.strip() if commit.returncode == 0 else None,
                                "dirty": bool(status.stdout.strip()) if status.returncode == 0 else None}
    if args.package_manifest:
        result["package"] = manifest_identity(args.package_manifest)
    if args.asset_manifest:
        result["assets"] = manifest_identity(args.asset_manifest)
    elif args.executable_mode == "exported" and args.package_manifest:
        result["assets"] = result["package"].get("assetClosure", {
            "schemaVersion": 1, "status": "unsupported",
            "scope": "package artifacts; asset closure not claimed", "assetClosureHash": None,
            "unknowns": ["legacy package has no verified asset closure"]})
        if result["assets"].get("status") == "complete":
            app = (args.package_manifest.parent / "app").resolve()
            if args.godot.resolve().parent != app or (args.main_pack is not None
                    and args.main_pack.resolve() != app / "RabbitLands.pck"):
                raise EvidenceError("verified asset closure does not cover this executable/main-pack location")
    else:
        result["assets"] = {"scope": "all Godot assets/data and selected map/chunk external dependencies",
                            "mapIds": maps, "importCacheIncluded": False,
                            **hash_files(asset_files(args.project_path, maps), args.project_path.parent)}
    if args.main_pack:
        result["mainPack"] = {"path": str(args.main_pack), "sha256": sha256_file(args.main_pack)}
    if args.replay:
        result["replayInput"] = {"sha256": sha256_file(args.replay), "bytes": args.replay.stat().st_size}
    return result


def run_one(args, variant: str, repeat: int, out_dir: Path) -> dict:
    configure_settings_profile(args)
    name = f"{args.label}-{variant}-{args.mode}-{args.driver}-{time.strftime('%Y%m%dT%H%M%S')}-{uuid.uuid4().hex[:8]}"
    user_root = out_dir / "userdata" / name
    user_root.mkdir(parents=True)
    report, log = out_dir / f"{name}.json", out_dir / f"{name}.log"
    started_report = Path(str(report) + ".started.json")
    teardown_failure_path = Path(str(report) + ".teardown-failed.json")
    start_token = uuid.uuid4().hex
    launch_log = out_dir / f"{name}.launch.log"
    env, cleared = clean_environment(dict(os.environ))
    overrides = {
        "APPDATA": str(user_root), "XDG_DATA_HOME": str(user_root),
        "RABBITLANDS_CROWD_PRESENTATION": "" if variant == "all" else variant,
        "RABBITLANDS_CROWD_BODY_CAP": "" if args.body_cap is None else str(args.body_cap),
        "RABBITLANDS_CROWD_BENCH_CELLS": args.cells,
        "RABBITLANDS_CROWD_BENCH_MAP": args.map,
        "RABBITLANDS_CROWD_BENCH_REPLAY": str(args.replay) if args.replay else "",
        "RABBITLANDS_CROWD_BENCH_REPLAY_START_MSEC": str(args.replay_start_ms),
        "RABBITLANDS_CROWD_BENCH_SAMPLE_MSEC": str(args.sample_ms),
        "RABBITLANDS_CROWD_BENCH_WARMUP_MSEC": str(args.warmup_ms),
        "RABBITLANDS_CROWD_BENCH_LABEL": f"{args.label}-{variant}",
        "RABBITLANDS_CROWD_BENCH_OUT": str(report),
        "RABBITLANDS_CROWD_BENCH_DIAG": args.diagnostics,
        "RABBITLANDS_CROWD_BENCH_CAPTURE_BOUNDARIES": "1" if args.capture_boundaries else "",
        "RABBITLANDS_CROWD_BENCH_DRIVER": args.driver,
        "RABBITLANDS_CROWD_BENCH_FPS_CAP": str(args.fps_cap),
        "RABBITLANDS_CROWD_BENCH_RESOLUTION": f"{args.resolution[0]}x{args.resolution[1]}",
        "RABBITLANDS_CROWD_BENCH_EXECUTION_MODE": args.executable_mode,
        "RABBITLANDS_CROWD_BENCH_START_TOKEN": start_token,
        "RABBITLANDS_CROWD_TUNING": args.tuning,
        "RABBITLANDS_CROWD_BENCH_MINIMAP": {"show": "1", "hide": "0"}.get(args.minimap, ""),
        "RABBITLANDS_CROWD_BENCH_PRESENCE": str(args.presence),
        "RABBITLANDS_CROWD_BENCH_SERVER_TIME": "1" if args.server_time else "",
        "ELORIA_LOOK_QUALITY": args.quality,
        "ELORIA_NATIVE_CROWD": "1" if args.native_reducer == "on" else "0",
        "ELORIA_NATIVE_PRESENTATION": "0" if args.native_presentation == "off" else args.native_presentation,
        "RABBITLANDS_CLIENT_RUNTIME": args.client_runtime,
        "RABBITLANDS_REMOTE_PRESENTATION": getattr(args, "remote_presentation", "legacy"),
        "RABBITLANDS_RESOURCE_ADMISSION": args.resource_admission,
        "RABBITLANDS_RESOURCE_BUDGET_MIB": str(args.resource_admission_budget_mib),
        "RABBITLANDS_RUST_EFFECTS": "heat_bolt" if args.rust_effects == "heat_bolt" else "",
        "RABBITLANDS_PREPARED_CONTENT": getattr(args, "prepared_content", "raw"),
        "RABBITLANDS_PREPARED_NODE_POLICY": getattr(args, "prepared_node_policy", "retain"),
    }
    if args.centre:
        overrides["RABBITLANDS_CROWD_BENCH_CENTRE"] = args.centre
    if args.disable_obs_vulkan_capture:
        overrides["DISABLE_VULKAN_OBS_CAPTURE"] = "1"
    env.update(overrides)
    settings_seed = seed_settings_profile(args.settings_profile, args.project_path, user_root, env)
    before = identity(args)
    command = command_for(args, log)
    started = time.monotonic()
    utc = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    startup = {"path": str(started_report), "timeoutSeconds": args.startup_timeout,
               "valid": False, "acknowledgement": None, "seconds": None, "error": None}
    teardown_failure = None
    workload_error = None
    memory_sampler = None
    startup_request = {"executable_mode": args.executable_mode, "executable": str(args.godot),
                       "start_token": start_token, "user_root": str(user_root)}
    if settings_seed:
        startup_request["settings_seed_user_dir"] = settings_seed["userDataDir"]
    with launch_log.open("w", encoding="utf-8") as stream:
        process = subprocess.Popen(command, env=env, stdout=stream, stderr=subprocess.STDOUT,
                                   cwd=args.project_path if args.executable_mode == "project" else args.godot.parent)
        observed = set_affinity(process.pid, int(args.affinity, 16)) if args.affinity else None
        startup_request["pid"] = process.pid
        try:
            if args.affinity and observed != int(args.affinity, 16):
                raise EvidenceError("requested affinity could not be applied/observed on the launched process")
            startup["acknowledgement"] = wait_for_startup(process, started_report, startup_request, args.startup_timeout)
            startup["valid"] = True
            startup["seconds"] = round(time.monotonic() - started, 3)
            memory_sampler = ProcessMemorySampler(process, started)
            code, teardown_failure = wait_for_workload(
                process, teardown_failure_path, startup_request, args.timeout, memory_sampler=memory_sampler)
        except EvidenceError as exc:
            if not startup["valid"]:
                startup["seconds"] = round(time.monotonic() - started, 3)
                startup["error"] = str(exc)
            workload_error = str(exc)
            if process.poll() is None:
                process.kill()
            code = process.wait()
        except subprocess.TimeoutExpired:
            if process.poll() is None:
                process.kill()
            process.wait()
            code = "timeout"
    process_seconds = time.monotonic() - started
    try:
        after = identity(args)
    except (EvidenceError, OSError) as exc:
        after = {"error": str(exc)}  # Retain invalid process evidence even if a file disappeared.
    run = {"variant": variant, "repeat": repeat, "exit": code, "pid": process.pid,
           "executable": str(args.godot), "startedUtc": utc,
           "affinityRequested": args.affinity or None, "affinityObserved": observed,
           "affinity": args.affinity if observed is not None else None,
           "seconds": round(process_seconds, 3), "report": str(report),
           "log": str(log), "launchLog": str(launch_log), "command": command,
           "clearedOverrideNames": cleared,
           "effectiveOverrides": {k: v for k, v in overrides.items() if k != "RABBITLANDS_CROWD_BENCH_REPLAY"},
           "identityBefore": before, "identityAfter": after,
           "identityStable": before == after, "interferenceLabel": args.interference_label,
           "requestedMeasurementStatus": args.measurement_status, "data": {}}
    run["processMemory"] = memory_sampler.snapshot() if memory_sampler is not None else {
        "schemaVersion": 1, "pid": process.pid, "status": "unavailable", "sampleCount": 0,
        "unavailableReason": {"reason": "workload_wait_not_started; no acknowledged startup"}}
    run["startup"] = startup
    run["externalInterference"] = {"obsVulkan": {
        "requestedDisabled": args.disable_obs_vulkan_capture,
        "effectiveEnvValue": env.get("DISABLE_VULKAN_OBS_CAPTURE"),
        "observedHookLoaded": None}}
    run["teardownFailurePath"] = str(teardown_failure_path)
    run["teardownFailure"] = teardown_failure
    run["workloadError"] = workload_error
    run["settingsProfile"] = args.settings_profile
    run["settingsSeed"] = settings_seed
    if settings_seed:
        run["settingsSeedFinalSha256"] = sha256_file(Path(settings_seed["path"])) \
            if Path(settings_seed["path"]).is_file() else None
    if args.replay:
        run["replayInput"] = before["replayInput"]
    try:
        if not startup["valid"]:
            raise EvidenceError(startup["error"] or "benchmark startup was not acknowledged")
        if workload_error:
            raise EvidenceError(workload_error)
        if teardown_failure is not None:
            raise EvidenceError("benchmark teardown failed; the owning runner terminated its process")
        if code != 0:
            raise EvidenceError(f"engine did not exit successfully ({code})")
        if before != after:
            raise EvidenceError("source/content/executable/package identity changed during the run")
        data = read_json(report)
        if not log.is_file():
            raise EvidenceError("engine log is missing")
        text = log.read_text(encoding="utf-8-sig", errors="replace") + "\n" + launch_log.read_text(encoding="utf-8", errors="replace")
        request = request_for(args) | {"user_root": str(user_root)}
        if settings_seed:
            request["settings_seed_user_dir"] = settings_seed["userDataDir"]
        run["validation"] = validate_report(data, request, text)
        actual_user_dir = data["runtimeBuild"]["userDataDir"]
        acknowledged_user_dir = startup["acknowledgement"]["userDataDir"]
        if os.path.normcase(str(Path(actual_user_dir).resolve())) != os.path.normcase(str(Path(acknowledged_user_dir).resolve())):
            raise EvidenceError("final report user directory differs from startup acknowledgement")
        run["data"] = data
    except EvidenceError as exc:
        run["validation"] = {"valid": False, "qualification": "invalid", "errors": [str(exc)]}
    metadata = {k: v for k, v in run.items() if k != "data"}
    (out_dir / f"{name}.process.json").write_text(json.dumps(metadata, indent=2, allow_nan=False), encoding="utf-8")
    return run


def parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--godot", required=True)
    p.add_argument("--project-path", type=Path, default=CLIENT)
    p.add_argument("--benchmark-script", default=SCRIPT)
    p.add_argument("--executable-mode", choices=["project", "exported"], default="project")
    p.add_argument("--main-pack", type=Path)
    p.add_argument("--package-manifest", type=Path)
    p.add_argument("--asset-manifest", type=Path)
    p.add_argument("--asset-map", action="append", default=[])
    p.add_argument("--mode", choices=["headless", "windowed"], default="headless")
    p.add_argument("--renderer", default="forward_plus", choices=["forward_plus", "mobile", "gl_compatibility"])
    p.add_argument("--resolution", type=resolution, default=(1280, 720))
    p.add_argument("--settings-profile", choices=["default", "performance"], default="default",
                   help="Performance seeds the actual preset into fresh Windows user settings before startup")
    p.add_argument("--fps-cap", type=int, default=None,
                   help="default 60; Performance profile requires 30")
    p.add_argument("--map", default="")
    p.add_argument("--centre", default="")
    p.add_argument("--quality", default="", choices=["", "low", "medium", "high"])
    p.add_argument("--cells", default="phase4")
    p.add_argument("--variants", default="all,legacy")
    p.add_argument("--body-cap", type=int)
    p.add_argument("--driver", default="live", choices=["live", "stress"])
    p.add_argument("--replay", type=Path)
    p.add_argument("--replay-start-ms", type=int, default=30000)
    p.add_argument("--minimap", default="saved", choices=["saved", "show", "hide"])
    p.add_argument("--tuning", default="")
    p.add_argument("--presence", type=int, default=0)
    p.add_argument("--server-time", action="store_true")
    p.add_argument("--diagnostics", default="")
    p.add_argument("--capture-boundaries", action="store_true",
                   help="save the last completed world viewport after sampling; readback is outside timing")
    p.add_argument("--native-reducer", default="off", choices=["off", "on"])
    p.add_argument("--native-presentation", default="off", choices=["off", "cape", "flight", "both", "world", "all"])
    p.add_argument("--client-runtime", default="legacy", choices=["legacy", "compare", "rust", "services"])
    p.add_argument("--remote-presentation", default="legacy", choices=["legacy", "rust"])
    p.add_argument("--resource-admission", default="legacy", choices=["legacy", "rust"])
    p.add_argument("--resource-admission-budget-mib", type=admission_budget, default=768,
                   help="logical estimated residency allowance, 64 through 8192 MiB; not an allocation measurement")
    p.add_argument("--rust-effects", default="legacy", choices=["legacy", "heat_bolt"])
    p.add_argument("--prepared-content", default="raw", choices=["raw", "auto", "require-pilot"])
    p.add_argument("--prepared-node-policy", default="retain", choices=["retain", "lazy-source-v1"])
    p.add_argument("--repeats", type=int, default=1)
    p.add_argument("--sample-ms", type=int, default=6000)
    p.add_argument("--warmup-ms", type=int, default=2000)
    p.add_argument("--affinity", default="")
    p.add_argument("--timeout", type=float, default=3600)
    p.add_argument("--startup-timeout", type=float, default=60,
                   help="seconds allowed for the benchmark startup acknowledgement before the full workload timeout")
    p.add_argument("--label", default="crowd")
    p.add_argument("--out-dir", type=Path)
    p.add_argument("--lock-path", type=Path)
    p.add_argument("--lock-timeout", type=float, default=0)
    p.add_argument("--interference-label", default="shared host; activity not continuously monitored")
    p.add_argument("--disable-obs-vulkan-capture", action="store_true",
                   help="set DISABLE_VULKAN_OBS_CAPTURE=1 only for the owned child; records no hook observation")
    p.add_argument("--measurement-status", choices=["screening", "quiet-comparison"], default="screening",
                   help="records the coordinator's conditions; does not qualify another device or reserve unrelated work")
    return p


def main(argv: list[str] | None = None) -> int:
    p = parser()
    args = p.parse_args(argv)
    try:
        configure_settings_profile(args)
        if args.remote_presentation == "rust" and args.client_runtime != "rust":
            raise EvidenceError("--remote-presentation rust requires --client-runtime rust")
        configure_prepared_profile(args)
        if args.resource_admission == "rust" and args.client_runtime not in ("services", "rust"):
            raise EvidenceError("--resource-admission rust requires --client-runtime services or rust")
        if args.capture_boundaries and args.mode != "windowed":
            raise EvidenceError("--capture-boundaries requires --mode windowed")
        if args.capture_boundaries and (args.replay or any(name.startswith("traversal-") for name in selected_cells(args.cells, False))):
            raise EvidenceError("--capture-boundaries currently supports synthetic crowd cells only")
        if args.rust_effects == "heat_bolt" and args.client_runtime != "rust":
            raise EvidenceError("--rust-effects heat_bolt requires --client-runtime rust")
        if args.rust_effects == "heat_bolt" and args.native_presentation != "off":
            raise EvidenceError("Rust heat-bolt qualification requires --native-presentation off")
        args.project_path = args.project_path.resolve()
        args.godot = executable_path(args.godot)
        for field in ("main_pack", "package_manifest", "asset_manifest", "replay"):
            value = getattr(args, field)
            if value:
                value = value.resolve()
                if not value.is_file():
                    raise EvidenceError(f"{field} input does not exist")
                setattr(args, field, value)
        if args.executable_mode == "project" and args.main_pack:
            raise EvidenceError("--main-pack requires --executable-mode exported")
        if args.executable_mode == "exported" and not (args.main_pack or args.package_manifest):
            raise EvidenceError("exported mode requires a workload PCK or explicit package artifact manifest")
        if not re.fullmatch(r"[A-Za-z0-9_.-]+", args.label):
            raise EvidenceError("label must contain only letters, numbers, underscore, dot or hyphen")
        if any(re.fullmatch(r"[A-Za-z0-9_-]+", name) is None for name in [args.map, *args.asset_map] if name):
            raise EvidenceError("invalid map identifier")
        if args.repeats < 1 or args.sample_ms < 500 or args.warmup_ms < 100 or args.fps_cap < 0 \
                or args.presence < 0 or args.replay_start_ms < 0 or args.timeout <= 0 or args.lock_timeout < 0 \
                or not math.isfinite(args.startup_timeout) or args.startup_timeout <= 0 \
                or (args.body_cap is not None and args.body_cap < 0):
            raise EvidenceError("invalid negative/zero workload or timing option")
        if args.affinity and int(args.affinity, 16) <= 0:
            raise EvidenceError("affinity mask must be positive")
        if args.replay:
            args.driver = "replay"
        selected_cells(args.cells, bool(args.replay))
        output = args.out_dir or (Path(tempfile.gettempdir()) / "rabbitlands-private-benchmarks" / uuid.uuid4().hex
                                  if args.replay else args.project_path / "test-artifacts/crowd-presentation")
        output = output.resolve()
        if args.replay:
            require_private_replay_output(output, args.project_path)
        output.mkdir(parents=True, exist_ok=True)
        variants = [v for v in args.variants.split(";" if ";" in args.variants else ",") if v]
        if not variants or any(re.fullmatch(r"[A-Za-z0-9_,-]+", v) is None for v in variants):
            raise EvidenceError("invalid variant selector")
        runs = []
        lock_path = args.lock_path or default_lock_path(args.project_path)
        with BenchmarkLock(lock_path, args.lock_timeout, args.label):
            for repeat in range(1, args.repeats + 1):
                for variant in variants if repeat % 2 else reversed(variants):
                    run = run_one(args, variant, repeat, output)
                    runs.append(run)
                    validation = run["validation"]
                    print(f"[{variant} r{repeat}] {validation['qualification']} exit={run['exit']} -> {run['report']}")
                    if validation["valid"]:
                        for cell in run["data"]["cells"]:
                            if cell.get("status") == "unavailable_content":
                                print(f"  {cell['id']}: pending authored content; no accepted timing")
                                continue
                            frame = cell["frameTime"]
                            print(f"  {cell['id']:<28} mean {frame['mean']:7.2f} p95 {frame['p95']:7.2f} p99 {frame['p99']:7.2f} ms")
                    else:
                        print("  INVALID: " + "; ".join(validation["errors"]))
                        break
                if not runs[-1]["validation"]["valid"]:
                    break
        arguments = {k: (str(v) if isinstance(v, Path) else v) for k, v in vars(args).items() if k != "replay"}
        arguments["replay"] = bool(args.replay)
        summary = {"schemaVersion": 2, "machine": machine(), "arguments": arguments,
                   "lockPath": str(lock_path), "qualification": "invalid" if any(not r["validation"]["valid"] for r in runs)
                   else "pending_content" if any(r["validation"]["pendingCells"] for r in runs)
                   else "diagnostic" if args.diagnostics else "screening",
                   "runs": [{k: v for k, v in r.items() if k != "data"} | {
                       "cells": [{"id": c["id"], "frameTime": c.get("frameTime"), "readiness": c.get("readiness"),
                                  "census": c.get("census"), "effectiveRuntime": c.get("effectiveRuntime")}
                                 for c in r["data"].get("cells", [])]} for r in runs]}
        path = output / f"{args.label}-{args.mode}-{args.map or ('recording' if args.replay else 'four_gates')}-summary.json"
        path.write_text(json.dumps(summary, indent=2, allow_nan=False), encoding="utf-8")
        print(f"summary: {path}")
        return {"invalid": 1, "pending_content": 2, "screening": 0, "diagnostic": 0}[summary["qualification"]]
    except (EvidenceError, OSError, ValueError) as exc:
        print(f"benchmark rejected: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
