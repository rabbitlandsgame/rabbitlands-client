#!/usr/bin/env python3
"""Run the Phase 4 crowd presentation benchmark and summarise it.

Runs tests/integration/crowd_presentation_benchmark.gd in fresh Godot
processes, one per (variant, repeat), each with its own user-data directory so
saved preferences never leak into a measurement. Variants compare the crowd
presentation with parts of it switched off through
RABBITLANDS_CROWD_PRESENTATION ("all" is the shipped behaviour, "legacy" turns
every part off). Prints one line per cell and writes the reports beside a
summary JSON. `--replay` plays one connection of a server session recording
(.rlrec) instead of a synthetic crowd; recordings hold player data, so keep
them and the reports made from them out of this repository.

Examples:
  python tests/integration/run_crowd_presentation_benchmark.py --godot <Godot.exe> \
      --mode headless --variants all,legacy --cells phase4
  python tests/integration/run_crowd_presentation_benchmark.py --godot <Godot.exe> \
      --mode windowed --renderer forward_plus --variants all --cells s3-market-160
  python tests/integration/run_crowd_presentation_benchmark.py --godot <Godot.exe>       --replay <recording>.rlrec --replay-start-ms 30000 --sample-ms 40000 --out-dir <ignored dir>

Windowed runs use the GPU: run one at a time on a shared machine.
"""
from __future__ import annotations

import argparse
import json
import os
import platform
import subprocess
import sys
import time
from pathlib import Path

CLIENT = Path(__file__).resolve().parents[2]
SCRIPT = "res://tests/integration/crowd_presentation_benchmark.gd"


def set_affinity(pid: int, mask: int) -> bool:
    """Pins a process to the logical CPUs in `mask` (Windows only)."""
    if os.name != "nt" or mask <= 0:
        return False
    import ctypes
    kernel = ctypes.windll.kernel32
    handle = kernel.OpenProcess(0x0200 | 0x0400, False, pid)
    if not handle:
        return False
    try:
        return bool(kernel.SetProcessAffinityMask(handle, ctypes.c_size_t(mask)))
    finally:
        kernel.CloseHandle(handle)


def machine() -> dict:
    info = {"platform": platform.platform(), "machine": platform.machine(),
            "python": platform.python_version()}
    if os.name == "nt":
        try:
            import winreg
            key = winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE,
                                 r"HARDWARE\DESCRIPTION\System\CentralProcessor\0")
            info["cpu"] = winreg.QueryValueEx(key, "ProcessorNameString")[0].strip()
        except OSError:
            pass
    return info


def run_one(args, variant: str, repeat: int, out_dir: Path) -> dict:
    stamp = time.strftime("%Y%m%dT%H%M%S")
    name = f"{args.label}-{variant}-{args.mode}-{args.driver}-{map_name(args)}-r{repeat}-{stamp}"
    user_root = out_dir / "userdata" / name
    user_root.mkdir(parents=True, exist_ok=True)
    report = out_dir / f"{name}.json"
    log = out_dir / f"{name}.log"
    env = dict(os.environ)
    env.update({
        "APPDATA": str(user_root),
        "XDG_DATA_HOME": str(user_root),
        "RABBITLANDS_CROWD_PRESENTATION": "" if variant == "all" else variant,
        "RABBITLANDS_CROWD_BODY_CAP": str(args.body_cap or ""),
        "RABBITLANDS_CROWD_BENCH_CELLS": args.cells,
        "RABBITLANDS_CROWD_BENCH_MAP": args.map,
        "RABBITLANDS_CROWD_BENCH_REPLAY": str(Path(args.replay).resolve()) if args.replay else "",
        "RABBITLANDS_CROWD_BENCH_REPLAY_START_MSEC": str(args.replay_start_ms),
        "RABBITLANDS_CROWD_BENCH_SAMPLE_MSEC": str(args.sample_ms),
        "RABBITLANDS_CROWD_BENCH_WARMUP_MSEC": str(args.warmup_ms),
        "RABBITLANDS_CROWD_BENCH_LABEL": f"{args.label}-{variant}",
        "RABBITLANDS_CROWD_BENCH_OUT": str(report),
    })
    if args.centre:
        env["RABBITLANDS_CROWD_BENCH_CENTRE"] = args.centre
    if args.quality:
        env["ELORIA_LOOK_QUALITY"] = args.quality
    env["RABBITLANDS_CROWD_BENCH_DIAG"] = args.diagnostics
    env["RABBITLANDS_CROWD_BENCH_DRIVER"] = args.driver
    env["RABBITLANDS_CROWD_TUNING"] = args.tuning
    env["RABBITLANDS_CROWD_BENCH_MINIMAP"] = {"show": "1", "hide": "0"}.get(args.minimap, "")
    command = [args.godot, "--path", str(CLIENT), "--audio-driver", "Dummy",
               "--log-file", str(log)]
    if args.mode == "headless":
        command.append("--headless")
    else:
        command += ["--rendering-method", args.renderer, "--resolution", "1280x720"]
    command += ["--script", SCRIPT]
    started = time.time()
    process = subprocess.Popen(command, env=env, stdout=subprocess.DEVNULL,
                               stderr=subprocess.DEVNULL)
    pinned = set_affinity(process.pid, int(args.affinity, 16)) if args.affinity else False
    try:
        code = process.wait(timeout=args.timeout)
    except subprocess.TimeoutExpired:
        process.kill()
        code = "timeout"
    data = json.loads(report.read_text(encoding="utf-8")) if report.exists() else {}
    return {"variant": variant, "repeat": repeat, "exit": code, "pid": process.pid,
            "affinity": args.affinity if pinned else None, "seconds": round(time.time() - started, 1),
            "report": str(report), "log": str(log), "data": data}


def map_name(args) -> str:
    """The map in report names: the one asked for, else the driver's default."""
    return args.map or ("recording" if args.driver == "replay" else "four_gates")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--godot", required=True, help="Godot 4.7 executable (not the console wrapper)")
    parser.add_argument("--mode", choices=["headless", "windowed"], default="headless")
    parser.add_argument("--renderer", default="forward_plus",
                        choices=["forward_plus", "mobile", "gl_compatibility"])
    parser.add_argument("--map", default="",
                        help="map id (default: four_gates, or the recording's map for --replay)")
    parser.add_argument("--centre", default="", help="x,y server tile for the player")
    parser.add_argument("--quality", default="", choices=["", "low", "medium", "high"],
                        help="graphics quality (ELORIA_LOOK_QUALITY); default: the client's own")
    parser.add_argument("--cells", default="phase4")
    parser.add_argument("--variants", default="all,legacy",
                        help="comma list of RABBITLANDS_CROWD_PRESENTATION values; 'all' is the default client")
    parser.add_argument("--body-cap", type=int, default=0)
    parser.add_argument("--driver", default="live", choices=["live", "stress", "replay"],
                        help="live: game cadence (600 ms steps, 2 s rounds, staggered); "
                             "stress: the earlier study's 100 ms steps and 400 ms rounds in lockstep; "
                             "replay: a session recording (--replay)")
    parser.add_argument("--replay", default="",
                        help="session recording (.rlrec) to replay; implies --driver replay")
    parser.add_argument("--replay-start-ms", type=int, default=30000,
                        help="where the replay's warmup starts, in ms after the recording's YOU_ARE")
    parser.add_argument("--minimap", default="saved", choices=["saved", "show", "hide"],
                        help="minimap during the run (its marks are timed as mapViewports)")
    parser.add_argument("--tuning", default="", help="full=N,cloth=N budgets (RABBITLANDS_CROWD_TUNING)")
    parser.add_argument("--diagnostics", default="",
                        help="attribution only: no_animation,no_overhead,no_ground")
    parser.add_argument("--repeats", type=int, default=1)
    parser.add_argument("--sample-ms", type=int, default=6000)
    parser.add_argument("--warmup-ms", type=int, default=2000)
    parser.add_argument("--affinity", default="", help="hex CPU mask, e.g. F for four logical CPUs")
    parser.add_argument("--timeout", type=int, default=3600)
    parser.add_argument("--label", default="crowd")
    parser.add_argument("--out-dir", default=str(CLIENT / "test-artifacts" / "crowd-presentation"))
    args = parser.parse_args()
    if args.replay:
        args.driver = "replay"
    elif args.driver == "replay":
        parser.error("--driver replay needs --replay <recording>.rlrec")
    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    runs = []
    # Variants alternate within each repeat, so slow drift on a shared machine
    # lands on both sides of a comparison.
    for repeat in range(1, args.repeats + 1):
        variants = args.variants.split(",")
        if repeat % 2 == 0:
            variants.reverse()
        for variant in variants:
            run = run_one(args, variant, repeat, out_dir)
            runs.append(run)
            print(f"[{variant} r{repeat}] exit={run['exit']} {run['seconds']} s -> {run['report']}")
            for cell in run["data"].get("cells", []):
                frame = cell.get("frameTime") or {}
                census = (cell.get("census") or {}).get("afterSpawn", {})
                memory = (cell.get("memory") or {}).get("crowdDelta", {})
                print(f"  {cell['id']:<18} mean {frame.get('mean', 0):7.2f}  p95 {frame.get('p95', 0):7.2f}"
                      f"  p99 {frame.get('p99', 0):7.2f} ms  p5 {cell.get('fpsP5') or 0:6.1f} FPS"
                      f"  bodies {census.get('builtBodies', '?'):>3}/{census.get('nodes', '?'):>3}"
                      f"  static +{(memory.get('staticBytes') or 0) / 2**20:7.1f} MiB")
            for failure in run["data"].get("failures", []):
                print(f"  FAIL {failure}")
    summary = out_dir / f"{args.label}-{args.mode}-{map_name(args)}-summary.json"
    summary.write_text(json.dumps({"machine": machine(), "arguments": vars(args),
                                   "runs": [{k: v for k, v in run.items() if k != "data"} | {
                                       "cells": [{"id": c["id"], "frameTime": c.get("frameTime"),
                                                  "fpsP5": c.get("fpsP5"),
                                                  "census": c.get("census"),
                                                  "memory": c.get("memory", {}).get("crowdDelta")}
                                                 for c in run["data"].get("cells", [])],
                                       "failures": run["data"].get("failures", [])} for run in runs]},
                                  indent=2), encoding="utf-8")
    print(f"summary: {summary}")
    return 0 if all(run["exit"] == 0 for run in runs) else 1


if __name__ == "__main__":
    sys.exit(main())
