from __future__ import annotations

import argparse
import hashlib
import json
import re
from collections import defaultdict
from pathlib import Path


FRAME = re.compile(r"^FRAME: total: ([0-9.]+) script: ([0-9.]+)/([0-9]+) %$")
ENTRY = re.compile(r"^\d+:(res://.+)::([0-9]+)::(.+)$")
DETAIL = re.compile(
    r"^\s*total: ([0-9.]+)/[0-9]+ %\s+self: ([0-9.]+)/[0-9]+ % tcalls: ([0-9]+)$"
)
SAMPLE_MARKER = ("res://tests/integration/crowd_benchmarks.gd", "_sample_cell")
SELECTED = {
    ("res://tests/integration/crowd_benchmark_main.gd", "_process"),
    ("res://tests/integration/crowd_benchmark_main.gd", "_sync_world"),
    ("res://tests/integration/crowd_benchmark_main.gd", "_present_actor"),
    ("res://src/app/main.gd", "_process"),
    ("res://src/actors/cape_cloth.gd", "_process_modification_with_delta"),
    ("res://src/actors/cape_cloth.gd", "_try_native_constraint_step"),
    ("res://src/actors/cape_cloth.gd", "_write_native_chain_bones"),
    ("res://src/actors/combat_presentation_3d.gd", "CombatPresentation3D.update_pose"),
    ("res://src/actors/ranger_bow_3d.gd", "RangerBow3D.pose"),
    ("res://src/world/world_effect_3d.gd", "WorldEffect3D._process"),
    ("res://src/world/world_effect_3d.gd", "WorldEffect3D._draw_details"),
    ("res://src/world/world_effect_3d.gd", "WorldEffect3D._commit_native_details"),
    ("res://src/world/world_effect_3d.gd", "WorldEffect3D.configure"),
    ("res://src/world/world_effect_3d.gd", "WorldEffect3D._add_burst"),
    ("res://src/world/spell_flight_3d.gd", "draw_at"),
    ("res://src/world/spell_flight_3d.gd", "_commit_native_surface"),
}


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def artifact(path: Path, client_root: Path) -> dict:
    try:
        shown = path.relative_to(client_root).as_posix()
    except ValueError:
        shown = str(path)
    return {"path": shown, "sha256": sha(path), "bytes": path.stat().st_size}


def parse_frames(lines: list[str]) -> list[dict]:
    frames: list[dict] = []
    current = None
    pending = None
    for number, line in enumerate(lines, 1):
        match = FRAME.match(line)
        if match:
            current = {
                "stdoutLine": number,
                "frameSeconds": float(match.group(1)),
                "reportedScriptSeconds": float(match.group(2)),
                "reportedScriptPercent": int(match.group(3)),
                "entries": [],
            }
            frames.append(current)
            pending = None
            continue
        match = ENTRY.match(line)
        if current is not None and match:
            pending = {
                "identity": f"{match.group(1)}::{match.group(2)}::{match.group(3)}",
                "path": match.group(1),
                "line": int(match.group(2)),
                "function": match.group(3),
            }
            continue
        match = DETAIL.match(line)
        if current is not None and pending is not None and match:
            pending.update({
                "inclusiveSeconds": float(match.group(1)),
                "selfSeconds": float(match.group(2)),
                "calls": int(match.group(3)),
            })
            current["entries"].append(pending)
            pending = None
    for frame in frames:
        frame["sampleMarked"] = any(
            (entry["path"], entry["function"]) == SAMPLE_MARKER
            for entry in frame["entries"]
        )
    return frames


def aggregate(frames: list[dict]) -> dict:
    rows = defaultdict(lambda: {
        "path": "", "line": 0, "function": "", "inclusiveSeconds": 0.0,
        "selfSeconds": 0.0, "calls": 0, "snapshots": 0,
    })
    for frame in frames:
        for entry in frame["entries"]:
            row = rows[entry["identity"]]
            row["path"] = entry["path"]
            row["line"] = entry["line"]
            row["function"] = entry["function"]
            row["inclusiveSeconds"] += entry["inclusiveSeconds"]
            row["selfSeconds"] += entry["selfSeconds"]
            row["calls"] += entry["calls"]
            row["snapshots"] += 1
    values = list(rows.values())
    count = len(frames)
    for row in values:
        row["inclusiveSeconds"] = round(row["inclusiveSeconds"], 6)
        row["selfSeconds"] = round(row["selfSeconds"], 6)
        row["inclusiveMillisecondsPerSnapshot"] = round(
            row["inclusiveSeconds"] * 1000.0 / count, 6) if count else None
        row["selfMillisecondsPerSnapshot"] = round(
            row["selfSeconds"] * 1000.0 / count, 6) if count else None
        row["callsPerSnapshot"] = round(row["calls"] / count, 6) if count else None
        observed = row["snapshots"]
        row["inclusiveMillisecondsPerObservedSnapshot"] = round(
            row["inclusiveSeconds"] * 1000.0 / observed, 6
        ) if observed else None
        row["selfMillisecondsPerObservedSnapshot"] = round(
            row["selfSeconds"] * 1000.0 / observed, 6
        ) if observed else None
        row["callsPerObservedSnapshot"] = round(
            row["calls"] / observed, 6
        ) if observed else None
    return {
        "snapshotCount": count,
        "frameSecondsSum": round(sum(frame["frameSeconds"] for frame in frames), 6),
        "averageFrameMilliseconds": round(
            sum(frame["frameSeconds"] for frame in frames) * 1000.0 / count, 6
        ) if count else None,
        "reportedScriptSecondsSum": round(sum(
            frame["reportedScriptSeconds"] for frame in frames), 6),
        "topSelf": sorted(values, key=lambda row: row["selfSeconds"], reverse=True)[:20],
        "topInclusive": sorted(
            values, key=lambda row: row["inclusiveSeconds"], reverse=True)[:20],
        "selectedFunctions": sorted(
            [row for row in values if (row["path"], row["function"]) in SELECTED],
            key=lambda row: row["selfSeconds"], reverse=True,
        ),
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("session", type=Path)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    session = args.session.resolve()
    client_root = Path(__file__).resolve().parents[1]
    stdout = session / "profiler.stdout.log"
    process_path = session / "process.json"
    report_path = session / "crowd-report.json"
    for path in (stdout, process_path, report_path):
        if not path.is_file():
            raise SystemExit(f"missing profiler input: {path}")

    lines = stdout.read_text(encoding="utf-8-sig", errors="replace").splitlines()
    frames = parse_frames(lines)
    if not frames or "BEGIN PROFILING" not in lines:
        raise SystemExit("no Godot script profile frames found")
    process = json.loads(process_path.read_text(encoding="utf-8-sig"))
    report = json.loads(report_path.read_text(encoding="utf-8-sig"))
    if not process.get("valid") or report.get("failureCount") != 0:
        raise SystemExit("profile process/report validation did not pass")
    sample_frames = [frame for frame in frames if frame["sampleMarked"]]
    if not sample_frames:
        raise SystemExit("no sample-marked profiler frames found")

    output = {
        "schemaVersion": 1,
        "title": "Godot script profile of the full native-presentation crowd fixture",
        "date": "2026-09-19",
        "status": "valid diagnostic profile; excluded from acceptance timing",
        "conclusion": {
            "continuous": (
                f"The {len(sample_frames)} sample-marked snapshots place repeated cape "
                "constraint/write work, "
                "WorldEffect detail build/submission, SpellFlight draw/submission, and broad "
                "CombatPresentation pose updates among the largest script callers."
            ),
            "eventCreation": (
                "WorldEffect configure and burst allocation appear only in the sampled packet "
                "frame and are material there, but are not the dominant continuous cost."
            ),
            "engineBoundary": (
                "The profile cannot split GDScript from synchronous native calls charged to "
                "the caller, deferred skeleton/skinning work, RenderingServer work, or GPU work."
            ),
        },
        "scope": {
            "nativeCallsEnabled": False,
            "timeUnit": "seconds",
            "frameSnapshots": (
                "Each FRAME block emitted by the Godot local debugger is one individual "
                "rendered-frame snapshot sampled periodically; it is not a window total, and "
                "the profiler does not emit every rendered frame."
            ),
            "inclusiveCaveat": "inclusive function totals overlap through call nesting",
            "reportedScriptCaveat": (
                "FRAME header script values can overlap through nested profiler accounting and "
                "can exceed frame time; their sum is not total CPU time or a workload percentage"
            ),
            "sampleMarker": (
                "a snapshot is sample-marked when crowd_benchmarks._sample_cell appears; "
                "coroutine scheduling makes this a useful subset, not an exact profiler gate; "
                f"this capture marked {len(sample_frames)} of "
                f"{len(report['cells'][0]['sample']['raw']['wallMilliseconds'])} sampled frames"
            ),
            "engineCaveat": (
                "native engine and GDExtension calls are not separate entries; time charged to "
                "a GDScript caller can include synchronous native calls"
            ),
            "acceptanceCaveat": (
                "profiling overhead changed the raw frame distribution, so these timings are "
                "diagnostic and must not be merged with acceptance benchmarks"
            ),
        },
        "source": {
            "commit": process["commit"],
            "sourceHash": process["sourceHash"],
            "sourceFiles": process["sourceFiles"],
            "nativePresentation": process["nativePresentation"],
            "nativeReducer": process["nativeReducer"],
            "affinityMask": process["affinityMask"],
            "observedAffinityMasks": process["observedAffinityMasks"],
            "interferenceLabel": report["interferenceLabel"],
            "godot": report["godot"],
            "launchExecutablePath": process["launchExecutablePath"],
            "launchExecutableSha256": process["launchExecutableSha256"],
        },
        "admission": {
            "processValid": process["valid"],
            "reportFailureCount": report["failureCount"],
            "profileStarted": process["profileStarted"],
            "profileAccumulated": process["profileAccumulated"],
            "scriptErrorsDetected": process["scriptErrorsDetected"],
            "fallbacks": {
                "cape": report["nativePresentation"]["actual"]["capeFallbackCalls"],
                "flight": report["nativePresentation"]["actual"]["flightBuildFallbacks"],
                "world": report["nativePresentation"]["actual"]["worldBuildFallbacks"],
            },
        },
        "fixture": {
            "actors": report["cells"][0]["count"],
            "visible": report["cells"][0]["fixture"]["before"]["frustumAndDrawVisible"],
            "active": report["cells"][0]["plannedActive"],
            "features": report["cells"][0]["features"],
            "sampleFrames": len(report["cells"][0]["sample"]["raw"]["wallMilliseconds"]),
            "sampleMilliseconds": report["measurement"]["sampleMilliseconds"],
            "wallMilliseconds": report["cells"][0]["sample"]["summary"]["wallMilliseconds"],
            "rates": report["cells"][0]["sample"]["rates"],
        },
        "raw": {
            "stdout": artifact(stdout, client_root),
            "process": artifact(process_path, client_root),
            "report": artifact(report_path, client_root),
        },
        "allProcessSnapshots": aggregate(frames),
        "sampleMarkedSnapshots": aggregate(sample_frames),
        "snapshotHeaders": [{key: frame[key] for key in (
            "stdoutLine", "frameSeconds", "reportedScriptSeconds",
            "reportedScriptPercent", "sampleMarked")}
            for frame in frames],
    }

    target = args.output.resolve() if args.output else session / "script-profile.json"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(output, indent=2) + "\n", encoding="utf-8")
    print(target)
    print(json.dumps({
        "sampleTopSelf": output["sampleMarkedSnapshots"]["topSelf"][:20],
        "sampleTopInclusive": output["sampleMarkedSnapshots"]["topInclusive"][:20],
    }, indent=2))


if __name__ == "__main__":
    main()
