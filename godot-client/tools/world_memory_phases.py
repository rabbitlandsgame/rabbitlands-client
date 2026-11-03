"""Host private bytes per world phase (wave-2 memory measurement, MEM-M2/M5).

Two ways to see what entering and leaving a large interior (the Landfall underground)
costs the process, as the host sees it (Windows private bytes and working set, which
Godot's own counters cannot show):

  park   Runs tests/integration/landfall_town_park.gd (WorldLoader + WorldPark, no Main)
         under the crowd harness's process sampler. Every `_memory` phase of the script
         prints its unix time; each phase gets the private bytes and working set sampled
         nearest after it, plus the extremes until the next phase. --dwell-ms holds Landfall
         after the first exit (exit_dwell phases once a second) while the interior is freed
         (refused parking: small) or kept (parked: medium, large).

             python tools/world_memory_phases.py park --godot <exe> --out-dir <ignored dir>
                 [--memory-class small|medium|large|auto] [--interior landfall_insides]
                 [--park-held] [--dwell-ms 20000] [--mode headless|windowed] [--renderer R]
                 [--resolution WxH] [--engine-arg=--gpu-index=1] [--affinity HEX]

  crowd  Reads a finished crowd-runner run (run_crowd_presentation_benchmark.py; the live
         client with Main, e.g. --cells traversal-underground-roundtrip): its report's
         route legs carry memory points with unix times (legs[].memory, legs[].dwell), and
         its `.process.json` the sampler's private bytes. Prints the same table per leg.

             python tools/world_memory_phases.py crowd <run>.process.json [...]

Both write JSON (--json) and print a Markdown table. A park run's environment is
cleared like the crowd runner's (every inherited ELORIA_*/RABBITLANDS_* switch);
APPDATA and LOCALAPPDATA are fresh directories under --out-dir; the run holds the
client benchmark lock. A failed park-script check is recorded, not fatal: the script's
checks describe the class behaviour, the measurement is the memory. The same file runs
against clients with and without memory classes (the wave-2 baseline reports
memory_class.available false).
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import time
import uuid

PROJECT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT / "tests" / "integration"))
from crowd_benchmark_support import (  # noqa: E402
    ERROR_PATTERN, BenchmarkLock, EvidenceError, clean_environment, default_lock_path, hash_files,
    parse_engine_args, parse_switches, source_files, switch_record,
)
from process_memory_sampler import ProcessMemorySampler  # noqa: E402

SCRIPT = "res://tests/integration/landfall_town_park.gd"
PHASE_PREFIX = "LANDFALL_TOWN_PARK phase "
SCHEMA = 1


def _git(project: Path, *arguments: str) -> str | None:
    done = subprocess.run(["git", "-C", str(project), *arguments], text=True,
                          stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
    return done.stdout.strip() if done.returncode == 0 else None


def git_state(project: Path) -> dict:
    status = _git(project, "status", "--porcelain", "--untracked-files=normal")
    return {"head": _git(project, "rev-parse", "HEAD"), "branch": _git(project, "rev-parse", "--abbrev-ref", "HEAD"),
            "dirty": None if status is None else bool(status)}


def set_affinity(pid: int, mask: int) -> int | None:
    """The crowd runner's own affinity setter (owned process only)."""
    import run_crowd_presentation_benchmark as runner
    return runner.set_affinity(pid, mask)


def match_samples(points: list[dict], samples: list[dict], time_key: str = "unixTime") -> list[dict]:
    """Each point (with a unix time) and the sampler's view of it.

    `at`: the first sample at or after the point (None past the series); `window`: the
    minimum and maximum private bytes and working set from the point to the next point
    (or the series end). Samples are about one second apart, so `at` lags the point by
    up to a second.
    """
    ordered = sorted((s for s in samples if isinstance(s.get("unixTime"), (int, float))), key=lambda s: s["unixTime"])
    rows = []
    for index, point in enumerate(points):
        at_time = point.get(time_key)
        if not isinstance(at_time, (int, float)):
            rows.append(point | {"at": None, "window": None})
            continue
        end_time = next((p.get(time_key) for p in points[index + 1:] if isinstance(p.get(time_key), (int, float))),
                        float("inf"))
        after = [s for s in ordered if s["unixTime"] >= at_time]
        inside = [s for s in after if s["unixTime"] < end_time]
        at = after[0] if after else None
        window = None
        if inside:
            window = {"samples": len(inside)}
            for key in ("privateBytes", "workingSetBytes"):
                values = [s[key] for s in inside if isinstance(s.get(key), int)]
                if values:
                    window[key] = {"min": min(values), "max": max(values)}
        rows.append(point | {"at": None if at is None else {
            "lagSeconds": round(at["unixTime"] - at_time, 3), "privateBytes": at.get("privateBytes"),
            "workingSetBytes": at.get("workingSetBytes")}, "window": window})
    return rows


def _mib(value) -> str:
    return "-" if not isinstance(value, (int, float)) else f"{value / 1048576:,.0f}"


def markdown(title: str, rows: list[dict], label_key: str) -> str:
    lines = [title, "", "| Phase | Map | Private MiB (at) | Working set MiB (at) | Private MiB min-max until next "
             "| Static MiB | Video MiB | Actor scenes MiB | WorldPark kept MiB | Parked |",
             "| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | --- |"]
    for row in rows:
        at = row.get("at") or {}
        window = (row.get("window") or {}).get("privateBytes") or {}
        lines.append(f"| {row.get(label_key)} | {row.get('map', '')} | {_mib(at.get('privateBytes'))} | "
                     f"{_mib(at.get('workingSetBytes'))} | {_mib(window.get('min'))}-{_mib(window.get('max'))} | "
                     f"{_mib(row.get('staticBytes'))} | {_mib(row.get('videoBytes'))} | "
                     f"{_mib(row.get('actorSceneBytes'))} | {_mib(row.get('worldParkKeptBytes'))} | "
                     f"{row.get('parked', '')} |")
    return "\n".join(lines) + "\n"


# ---------------------------------------------------------------------------- park


def park_command(args, report: Path, log: Path) -> list[str]:
    command = [str(args.godot), *args.engine_args, "--path", str(args.project), "--audio-driver", "Dummy",
               "--log-file", str(log)]
    if args.mode == "headless":
        command.append("--headless")
    else:
        command += ["--rendering-method", args.renderer, "--resolution", args.resolution]
    command += ["--script", SCRIPT, "--", "--report", str(report), "--interior", args.interior]
    if args.park_held:
        command.append("--park-held")
    if args.keep_vsync:
        command.append("--keep-vsync")
    if args.dwell_ms:
        command += ["--dwell-ms", str(args.dwell_ms)]
    return command


def park_phases(stdout_text: str) -> list[dict]:
    rows = []
    for line in stdout_text.splitlines():
        if line.startswith(PHASE_PREFIX):
            try:
                value = json.loads(line[len(PHASE_PREFIX):])
            except ValueError:
                continue
            if isinstance(value, dict):
                rows.append({"phase": value.get("phase"), "unixTime": value.get("unix_time"),
                             "staticBytes": value.get("static_bytes"), "videoBytes": value.get("video_gpu_bytes"),
                             "worldParkKeptBytes": value.get("world_park_kept_bytes"),
                             "parked": value.get("world_park_parked")})
    return rows


def run_park(args) -> dict:
    stamp = time.strftime("%Y%m%dT%H%M%S") + "-" + uuid.uuid4().hex[:6]
    out = args.out_dir / f"{args.label}-{stamp}"
    (out / "appdata").mkdir(parents=True)
    (out / "localappdata").mkdir()
    report, log, stdout_path = out / "landfall_town_park.json", out / "godot.log", out / "stdout.txt"
    env, cleared = clean_environment(dict(os.environ))
    env.update({"APPDATA": str(out / "appdata"), "LOCALAPPDATA": str(out / "localappdata"),
                "XDG_DATA_HOME": str(out / "appdata")})
    env.update(args.switches)
    command = park_command(args, report, log)
    git_before = git_state(args.project)
    identity_before = hash_files(source_files(args.project), args.project.parent)
    started = time.monotonic()
    utc = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    observed_affinity = None
    with stdout_path.open("w", encoding="utf-8") as stream:
        process = subprocess.Popen(command, env=env, stdout=stream, stderr=subprocess.STDOUT, cwd=str(args.project))
        if args.affinity:
            observed_affinity = set_affinity(process.pid, int(args.affinity, 16))
        sampler = ProcessMemorySampler(process, started)
        deadline = started + args.timeout
        exit_code: int | str
        while True:
            sampler.sample_if_due()
            try:
                exit_code = process.wait(timeout=0.1)
                break
            except subprocess.TimeoutExpired:
                if time.monotonic() > deadline:
                    process.kill()
                    process.wait()
                    exit_code = "timeout"
                    break
    seconds = round(time.monotonic() - started, 3)
    identity_after = hash_files(source_files(args.project), args.project.parent)
    git_after = git_state(args.project)
    stdout_text = stdout_path.read_text(encoding="utf-8", errors="replace")
    log_text = log.read_text(encoding="utf-8-sig", errors="replace") if log.is_file() else ""
    error_lines = sorted({line.strip() for line in (log_text + "\n" + stdout_text).splitlines()
                          if ERROR_PATTERN.search(line)})
    allowed = [line for line in error_lines if any(re.search(pattern, line) for pattern in args.allow_error)]
    errors = [line for line in error_lines if line not in allowed]
    data = json.loads(report.read_text(encoding="utf-8")) if report.is_file() else None
    memory = sampler.snapshot()
    phases = match_samples(park_phases(stdout_text), memory.get("samples", []))
    problems = []
    if data is None:
        problems.append("no park report")
    if exit_code == "timeout":
        problems.append("timeout")
    if identity_before != identity_after:
        problems.append("source identity changed during the run")
    if args.affinity and observed_affinity != int(args.affinity, 16):
        problems.append("affinity was not applied")
    if memory.get("status") != "available":
        problems.append("process memory sampling " + str(memory.get("status")))
    if not phases:
        problems.append("no phase lines (an older park script?)")
    checks = (data or {}).get("checks", [])
    result = {"schema": SCHEMA, "tool": "world_memory_phases", "mode": "park", "label": args.label,
              "startedUtc": utc, "seconds": seconds, "exit": exit_code, "command": command,
              "project": str(args.project), "gitBefore": git_before, "gitAfter": git_after,
              "identityStable": identity_before == identity_after,
              "affinityRequested": args.affinity or None, "affinityObserved": observed_affinity,
              "clearedEnvironment": cleared, "switches": switch_record(env), "explicitSwitches": args.switches,
              "logErrorLines": errors, "allowedErrorLines": allowed, "allowErrorPatterns": args.allow_error,
              "memoryClass": (data or {}).get("memory_class"),
              "worldParkBudgetMiB": (data or {}).get("world_park_budget_mib"),
              "preloadEnabled": (data or {}).get("preload_enabled"),
              "checksFailed": [c.get("check") for c in checks if isinstance(c, dict) and not c.get("ok")],
              "transitions": (data or {}).get("transitions"), "phases": phases,
              "processMemory": {k: v for k, v in memory.items() if k != "samples"} | {"samples": memory.get("samples")},
              "report": str(report), "log": str(log), "stdout": str(stdout_path),
              "valid": not problems and not errors, "problems": problems + (
                  [f"{len(errors)} distinct unexpected error lines in the log"] if errors else [])}
    (out / "world-memory-phases.json").write_text(json.dumps(result, indent=1) + "\n", encoding="utf-8")
    result["out"] = str(out)
    return result


# ---------------------------------------------------------------------------- crowd


def crowd_points(report: dict) -> list[dict]:
    """Every route memory point of a crowd report, in order, labelled by cell and leg."""
    points = []
    for cell in report.get("cells", []):
        route = cell.get("route") if isinstance(cell, dict) else None
        if not isinstance(route, dict):
            continue
        for leg in route.get("legs", []):
            if not isinstance(leg, dict):
                continue
            rows = list((leg.get("memory") or {}).values())
            rows += list((leg.get("dwell") or {}).get("points", []) if isinstance(leg.get("dwell"), dict) else [])
            for row in rows:
                if not isinstance(row, dict):
                    continue
                park = row.get("worldPark") or {}
                points.append({"cell": cell.get("id"), "leg": leg.get("id"),
                               "phase": f"{leg.get('id')}:{row.get('label')}", "map": row.get("map"),
                               "unixTime": row.get("unixTime"), "staticBytes": row.get("staticBytes"),
                               "videoBytes": row.get("videoBytes"),
                               "actorSceneBytes": (row.get("actorScenes") or {}).get("bytes"),
                               "worldParkKeptBytes": park.get("keptBytes"), "parked": park.get("parked")})
    # The report's JSON sorts keys (Godot's JSON.stringify), so order by the clock.
    return sorted(points, key=lambda point: point["unixTime"] if isinstance(point["unixTime"], (int, float))
                  else float("inf"))


def crowd_from_process(path: Path) -> dict:
    metadata = json.loads(path.read_text(encoding="utf-8"))
    report_path = Path(metadata["report"])
    report = json.loads(report_path.read_text(encoding="utf-8"))
    samples = (metadata.get("processMemory") or {}).get("samples", [])
    rows = match_samples(crowd_points(report), samples)
    return {"schema": SCHEMA, "tool": "world_memory_phases", "mode": "crowd", "process": str(path),
            "report": str(report_path), "valid": bool((metadata.get("validation") or {}).get("valid")),
            "memoryClass": report.get("memoryClass"), "switches": metadata.get("switches"),
            "processMemoryStatus": (metadata.get("processMemory") or {}).get("status"),
            "peaks": (metadata.get("processMemory") or {}).get("peaks"),
            "routeMemoryPeak": [((c.get("route") or {}).get("memoryPeak")) for c in report.get("cells", [])
                                if isinstance(c, dict) and isinstance(c.get("route"), dict)],
            "phases": rows}


# ---------------------------------------------------------------------------- main


def parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = p.add_subparsers(dest="command", required=True)
    park = sub.add_parser("park", help="run landfall_town_park.gd under the process sampler")
    park.add_argument("--godot", required=True)
    park.add_argument("--project", type=Path, default=PROJECT)
    park.add_argument("--out-dir", type=Path, required=True, help="evidence directory (keep it out of Git)")
    park.add_argument("--label", default="world-memory")
    park.add_argument("--mode", choices=["headless", "windowed"], default="windowed")
    park.add_argument("--renderer", default="forward_plus", choices=["forward_plus", "mobile", "gl_compatibility"])
    park.add_argument("--resolution", default="1280x720")
    park.add_argument("--engine-arg", action="append", default=[], metavar="OPTION")
    park.add_argument("--memory-class", default="auto", choices=["auto", "small", "medium", "large"])
    park.add_argument("--switch", action="append", default=[], metavar="NAME=VALUE")
    park.add_argument("--interior", default="landfall_insides")
    park.add_argument("--park-held", action="store_true",
                      help="lift WorldParkPolicy.HELD_INTERIORS (the underground is held otherwise)")
    park.add_argument("--keep-vsync", action="store_true")
    park.add_argument("--dwell-ms", type=int, default=20000)
    park.add_argument("--affinity", default="")
    park.add_argument("--timeout", type=float, default=1800)
    park.add_argument("--lock-path", type=Path)
    park.add_argument("--lock-timeout", type=float, default=0)
    park.add_argument("--allow-error", action="append", default=[], metavar="REGEX",
                      help="repeatable: a log error line matching it is recorded as allowed (a known, attributed "
                           "pre-existing engine error), not as one that invalidates the run")
    park.add_argument("--json", type=Path)
    crowd = sub.add_parser("crowd", help="per-leg private bytes of finished crowd-runner runs")
    crowd.add_argument("process", nargs="+", type=Path, help="<run>.process.json files of the crowd runner")
    crowd.add_argument("--json", type=Path)
    return p


def main(argv: list[str] | None = None) -> int:
    args = parser().parse_args(argv)
    try:
        if args.command == "crowd":
            results = [crowd_from_process(path) for path in args.process]
            for result in results:
                print(markdown(f"Crowd run {Path(result['process']).name} (valid={result['valid']}, memory class "
                               f"{(result.get('memoryClass') or {}).get('class')})", result["phases"], "phase"))
            if args.json:
                args.json.write_text(json.dumps(results, indent=1) + "\n", encoding="utf-8")
            return 0 if all(result["valid"] for result in results) else 1
        args.project = args.project.resolve()
        args.out_dir = args.out_dir.resolve()
        args.godot = Path(args.godot).resolve()
        if not args.godot.is_file():
            raise EvidenceError("Godot executable does not exist")
        if args.dwell_ms < 0 or args.timeout <= 0:
            raise EvidenceError("--dwell-ms and --timeout must not be negative")
        if args.affinity and int(args.affinity, 16) <= 0:
            raise EvidenceError("affinity mask must be positive")
        args.engine_args = parse_engine_args(args.engine_arg, args.renderer, args.mode)
        args.switches = parse_switches(args.switch, args.memory_class)
        args.out_dir.mkdir(parents=True, exist_ok=True)
        with BenchmarkLock(args.lock_path or default_lock_path(args.project), args.lock_timeout, args.label):
            result = run_park(args)
    except (EvidenceError, OSError, ValueError, KeyError) as exc:
        print(f"world_memory_phases: {exc}", file=sys.stderr)
        return 2
    print(markdown(f"Park run {result['label']} (valid={result['valid']}, memory class "
                   f"{(result.get('memoryClass') or {}).get('class')}, exit {result['exit']})", result["phases"], "phase"))
    if result["checksFailed"]:
        print("park-script checks failed (recorded): " + "; ".join(map(str, result["checksFailed"])))
    if result["problems"]:
        print("problems: " + "; ".join(result["problems"]))
    print(f"world_memory_phases: {'valid' if result['valid'] else 'INVALID'} -> {result['out']}")
    if args.json:
        args.json.write_text(json.dumps(result, indent=1) + "\n", encoding="utf-8")
    return 0 if result["valid"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
