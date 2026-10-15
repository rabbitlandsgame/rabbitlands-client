#!/usr/bin/env python3
"""Summarize Tracy CPU zones inside ELORIA_CROWD_ENGINE_PROFILE windows."""

from __future__ import annotations

import argparse
import csv
import json
from collections import defaultdict, deque
from itertools import zip_longest
from pathlib import Path


MARKER_PREFIX = "ELORIA_CROWD_ENGINE_PROFILE "
FOCUS_ZONES = {
    "frame": ("Main::iteration",),
    "scene_traversal": ("SceneTree::_process", "SceneTree::_process_group"),
    "animation": (
        "AnimationMixer::_process_animation",
        "AnimationMixer::_blend_process",
        "AnimationMixer::_blend_apply",
    ),
    "skeleton": (
        "Skeleton3D::NOTIFICATION_UPDATE_SKELETON",
        "Skeleton3D::_force_update_all_bone_transforms",
        "Skeleton3D::_process_modifiers",
        "Skeleton3D::emit_skeleton_updated",
        "Skeleton3D::update_skins",
    ),
    "script_modifiers": ("_process_modification_with_delta", "update_pose"),
    "render_and_wait": (
        "RenderingServer::sync",
        "RenderingServer::draw",
        "OS::add_frame_delay",
        "_stall_for_frame",
        "fence_wait",
    ),
}


def read_markers(path: Path) -> list[dict]:
    markers: list[dict] = []
    with path.open("r", encoding="utf-8-sig", errors="replace") as stream:
        next(stream, None)
        for raw_line in stream:
            message, separator, timestamp = raw_line.rstrip("\r\n").rpartition(",")
            if not separator or not message.startswith(MARKER_PREFIX):
                continue
            marker = json.loads(message[len(MARKER_PREFIX) :])
            marker["traceNanoseconds"] = int(timestamp)
            markers.append(marker)
    return markers


def pair_windows(markers: list[dict]) -> list[dict]:
    starts: dict[tuple[int, str], dict] = {}
    windows: list[dict] = []
    for marker in sorted(markers, key=lambda item: item["traceNanoseconds"]):
        if marker.get("event") not in {"sample_start", "sample_end"}:
            raise ValueError(f"Unknown engine profile event: {marker.get('event')!r}")
        if not str(marker.get("cell", "")):
            raise ValueError("Engine profile marker has an empty cell")
        key = (int(marker["processId"]), str(marker["cell"]))
        if marker["event"] == "sample_start":
            if key in starts:
                raise ValueError(f"Overlapping sample_start markers for {key}")
            starts[key] = marker
        else:
            if key not in starts:
                raise ValueError(f"Orphan sample_end marker for {key}")
            start = starts.pop(key)
            trace_duration = marker["traceNanoseconds"] - start["traceNanoseconds"]
            process_frames = int(marker["processFrame"]) - int(start["processFrame"])
            if trace_duration <= 0 or process_frames <= 0:
                raise ValueError(f"Nonpositive sample window for {key}")
            if int(marker["engineMicroseconds"]) <= int(start["engineMicroseconds"]):
                raise ValueError(f"Non-monotonic engine clock for {key}")
            if int(marker["unixMicroseconds"]) <= int(start["unixMicroseconds"]):
                raise ValueError(f"Non-monotonic UTC clock for {key}")
            windows.append(
                {
                    "processId": key[0],
                    "cell": key[1],
                    "start": start,
                    "end": marker,
                    "startNs": start["traceNanoseconds"],
                    "endNs": marker["traceNanoseconds"],
                    "processFrames": process_frames,
                }
            )
    if starts:
        raise ValueError("Unpaired sample_start marker(s) in Tracy messages")
    if not windows:
        raise ValueError("No complete engine profile marker window found")
    return windows


def zone_key(row: dict[str, str]) -> tuple[str, str, str, str, str]:
    return (
        row["name"],
        row["src_file"],
        row["src_line"],
        row["ns_since_start"],
        row["thread"],
    )


def read_zone_events(session: Path) -> list[dict]:
    events: list[dict] = []
    unmatched: dict[tuple[str, str, str, str, str], deque[dict]] = defaultdict(deque)
    with (session / "zones-unwrapped.csv").open(
        "r", encoding="utf-8-sig", newline=""
    ) as stream:
        for row in csv.DictReader(stream):
            event = {
                "name": row["name"],
                "startNs": int(row["ns_since_start"]),
                "inclusiveNs": max(int(row["exec_time_ns"]), 0),
                "selfNs": None,
            }
            events.append(event)
            unmatched[zone_key(row)].append(event)

    with (session / "zones-unwrapped-self.csv").open(
        "r", encoding="utf-8-sig", newline=""
    ) as stream:
        for row in csv.DictReader(stream):
            key = zone_key(row)
            if not unmatched[key]:
                raise ValueError(f"Self-time zone has no matching inclusive event: {key}")
            unmatched[key].popleft()["selfNs"] = max(int(row["exec_time_ns"]), 0)
    leftovers = sum(len(queue) for queue in unmatched.values())
    if leftovers:
        raise ValueError(f"Inclusive zone export has {leftovers} unmatched self-time events")
    return events


def zone_totals(events: list[dict], windows: list[dict]) -> list[dict[str, dict]]:
    totals: list[dict[str, dict]] = [
        defaultdict(
            lambda: {
                "inclusiveNs": 0,
                "selfNs": 0,
                "count": 0,
                "selfCount": 0,
                "boundaryOmittedSelfCount": 0,
            }
        )
        for _ in windows
    ]
    for event in events:
        zone_start = event["startNs"]
        zone_end = zone_start + event["inclusiveNs"]
        for index, window in enumerate(windows):
            overlap = max(
                0,
                min(zone_end, window["endNs"]) - max(zone_start, window["startNs"]),
            )
            if not overlap:
                continue
            item = totals[index][event["name"]]
            item["inclusiveNs"] += overlap
            item["count"] += 1
            if zone_start >= window["startNs"] and zone_end <= window["endNs"]:
                item["selfNs"] += event["selfNs"]
                item["selfCount"] += 1
            else:
                # csvexport gives exclusive duration but not its disjoint intervals,
                # so clipping self time at a marker boundary would be false precision.
                item["boundaryOmittedSelfCount"] += 1
    return totals


def read_focus_zone_totals(session: Path, windows: list[dict]) -> list[dict[str, dict]]:
    totals: list[dict[str, dict]] = [
        defaultdict(
            lambda: {
                "inclusiveNs": 0,
                "selfNs": 0,
                "count": 0,
                "selfCount": 0,
                "boundaryOmittedSelfCount": 0,
            }
        )
        for _ in windows
    ]
    inclusive_paths = sorted(session.glob("focus-*-inclusive.csv"))
    if not inclusive_paths:
        raise ValueError("No focused unwrapped zone exports found")
    for inclusive_path in inclusive_paths:
        self_path = inclusive_path.with_name(
            inclusive_path.name.replace("-inclusive.csv", "-self.csv")
        )
        if not self_path.is_file():
            raise ValueError(f"Missing matching self-time export for {inclusive_path.name}")
        with inclusive_path.open("r", encoding="utf-8-sig", newline="") as inc_stream, self_path.open(
            "r", encoding="utf-8-sig", newline=""
        ) as self_stream:
            inclusive_rows = csv.DictReader(inc_stream)
            self_rows = csv.DictReader(self_stream)
            for inclusive_row, self_row in zip_longest(inclusive_rows, self_rows):
                if inclusive_row is None or self_row is None:
                    raise ValueError(f"Focused exports have different row counts: {inclusive_path.name}")
                if zone_key(inclusive_row) != zone_key(self_row):
                    raise ValueError(f"Focused inclusive/self event mismatch: {inclusive_path.name}")
                event = {
                    "name": inclusive_row["name"],
                    "startNs": int(inclusive_row["ns_since_start"]),
                    "inclusiveNs": max(int(inclusive_row["exec_time_ns"]), 0),
                    "selfNs": max(int(self_row["exec_time_ns"]), 0),
                }
                zone_start = event["startNs"]
                zone_end = zone_start + event["inclusiveNs"]
                for index, window in enumerate(windows):
                    overlap = max(
                        0,
                        min(zone_end, window["endNs"])
                        - max(zone_start, window["startNs"]),
                    )
                    if not overlap:
                        continue
                    item = totals[index][(event["name"], inclusive_row["src_file"])]
                    item["inclusiveNs"] += overlap
                    item["count"] += 1
                    if zone_start >= window["startNs"] and zone_end <= window["endNs"]:
                        item["selfNs"] += event["selfNs"]
                        item["selfCount"] += 1
                    else:
                        item["boundaryOmittedSelfCount"] += 1
    return totals


def corroborate_benchmark(session: Path, windows: list[dict]) -> Path:
    manifest_path = session / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    candidates = []
    for raw_path in manifest["captured"]["reports"]:
        path = Path(raw_path)
        if path.suffix.lower() != ".json" or path.name.endswith(".process.json"):
            continue
        try:
            report = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        if isinstance(report.get("cells"), list) and isinstance(report.get("process"), dict):
            candidates.append((path, report))
    if len(candidates) != 1:
        raise ValueError(f"Expected one captured benchmark report, found {len(candidates)}")
    path, report = candidates[0]
    report_pid = int(report["process"]["pid"])
    cells = {str(cell["id"]): cell for cell in report["cells"]}
    stored_windows = [
        (str(cell["id"]), cell["sample"]["engineProfileWindow"])
        for cell in report["cells"]
        if cell.get("sample", {}).get("engineProfileWindow", {}).get("enabled")
    ]
    if len(stored_windows) != len(windows):
        raise ValueError(
            "Captured benchmark window count does not match complete trace marker pairs"
        )
    marker_fields = {
        "schemaVersion",
        "event",
        "cell",
        "processId",
        "unixMicroseconds",
        "engineMicroseconds",
        "processFrame",
    }
    for window in windows:
        if report_pid != window["processId"]:
            raise ValueError("Marker PID does not match captured benchmark PID")
        if window["cell"] not in cells:
            raise ValueError(f"Marker cell {window['cell']!r} is absent from benchmark")
        cell = cells[window["cell"]]
        stored = cell["sample"]["engineProfileWindow"]
        if not stored.get("enabled"):
            raise ValueError("Captured benchmark window is not enabled")
        for endpoint in ("start", "end"):
            expected = {key: window[endpoint][key] for key in marker_fields}
            actual = {key: stored[endpoint][key] for key in marker_fields}
            if actual != expected:
                raise ValueError(f"Trace marker and benchmark {endpoint} differ")
        if int(cell["sample"]["frames"]) != window["processFrames"]:
            raise ValueError("Marker frame interval does not match sampled frame count")
    return path


def relevant(name: str) -> bool:
    return any(token in name for tokens in FOCUS_ZONES.values() for token in tokens)


def summarize(session: Path) -> dict:
    windows = pair_windows(read_markers(session / "messages.csv"))
    benchmark_path = corroborate_benchmark(session, windows)
    totals = read_focus_zone_totals(session, windows)
    output_windows: list[dict] = []
    for index, window in enumerate(windows):
        frame_count = window["processFrames"]
        zone_keys = sorted(totals[index])
        focus = []
        for name, source_file in zone_keys:
            if not relevant(name):
                continue
            item = totals[index][(name, source_file)]
            focus.append(
                {
                    "name": name,
                    "sourceFile": source_file,
                    "count": item["count"],
                    "selfTimeEventCount": item["selfCount"],
                    "boundaryOmittedSelfTimeEventCount": item[
                        "boundaryOmittedSelfCount"
                    ],
                    "inclusiveMilliseconds": item["inclusiveNs"] / 1_000_000,
                    "selfMilliseconds": item["selfNs"] / 1_000_000,
                    "inclusiveMillisecondsPerProcessFrame": (
                        item["inclusiveNs"] / 1_000_000 / frame_count
                    ),
                    "selfMillisecondsPerProcessFrame": (
                        item["selfNs"] / 1_000_000 / frame_count
                    ),
                }
            )
        output_windows.append(
            {
                "processId": window["processId"],
                "cell": window["cell"],
                "startTraceNanoseconds": window["startNs"],
                "endTraceNanoseconds": window["endNs"],
                "traceMilliseconds": (window["endNs"] - window["startNs"]) / 1_000_000,
                "processFrames": frame_count,
                "startProcessFrame": window["start"]["processFrame"],
                "endProcessFrame": window["end"]["processFrame"],
                "zones": focus,
            }
        )
    return {
        "schemaVersion": 1,
        "sourceSession": str(session.resolve()),
        "benchmarkReport": str(benchmark_path.resolve()),
        "timingSemantics": (
            "Each zone is reported independently inside trace-native marker bounds. "
            "Inclusive values overlap for nested zones and must not be added together. "
            "Self time is included only for events wholly inside the window; boundary "
            "events are counted and omitted because their exclusive intervals are not exported."
        ),
        "windows": output_windows,
    }


def write_csv(path: Path, summary: dict) -> None:
    fields = [
        "cell",
        "processFrames",
        "name",
        "sourceFile",
        "count",
        "selfTimeEventCount",
        "boundaryOmittedSelfTimeEventCount",
        "inclusiveMilliseconds",
        "selfMilliseconds",
        "inclusiveMillisecondsPerProcessFrame",
        "selfMillisecondsPerProcessFrame",
    ]
    with path.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=fields)
        writer.writeheader()
        for window in summary["windows"]:
            for zone in window["zones"]:
                writer.writerow(
                    {
                        "cell": window["cell"],
                        "processFrames": window["processFrames"],
                        **zone,
                    }
                )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("session", type=Path, help="Tracy capture session directory")
    args = parser.parse_args()
    session = args.session.resolve()
    summary = summarize(session)
    json_path = session / "steady-zone-summary.json"
    csv_path = session / "steady-zone-summary.csv"
    json_path.write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    write_csv(csv_path, summary)
    print(json_path)
    print(csv_path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
