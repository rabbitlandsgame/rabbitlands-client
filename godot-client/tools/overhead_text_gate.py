"""Overhead-text gate (wave 2 OV-0, owner decision 8): what a 2D overhead layer could recover.

Reads crowd-presentation reports (tests/integration/run_crowd_presentation_benchmark.py)
of one configuration, run with --diagnostics "" (full), no_overhead, no_text_pass and,
optionally, text_pass_always, and compares the cells they share:

- recoverable = full - no_overhead: the most a 2D layer can recover (banners and the
  separate text pass both gone; the layer's own placement cost is not included);
- text pass = full - no_text_pass: the separate world-text pass alone (second camera,
  native-size target, composite), its labels still culled by every other camera;
- idle saving = text_pass_always - full: wave 1's idle pass, seen in the empty cell.
Video memory is compared both as totals after the sample and in-process (after the sample minus
after the spawn, the diagnostics applying in between), which removes run-to-run VRAM spread.

Differences of means and of p95s, averaged over repeats; runs are not frame-paired.
Metrics: frame work (`frameMilliseconds`, CPU side including GPU waits) and, on rendered
runs, `renderGpuSumMilliseconds` (world + text pass + root viewport GPU) and video memory
after the sample. The verdict is advisory: GO when a crowd cell's recoverable frame work
or GPU sum reaches --mean-ms (default 1.0) or --p95-ms (default 2.0), as the schedule's
G2 gate reads. Every report must carry the OV-0 records with its diagnostic in effect, and
renderer, quality, viewport, adapter, display, body cap, fps cap, map, effective settings and
build kind must match; give it only reports the runner marked valid. Usage:

    python tools/overhead_text_gate.py REPORT.json [...] [--json out.json] [--markdown out.md]
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import statistics
import sys

PROJECT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT / "tests" / "integration"))
from crowd_benchmark_support import (  # noqa: E402
    EvidenceError, parse_diagnostics, text_pass_mode, validate_overhead_diagnostics,
)

VARIANTS = ("full", "no_overhead", "no_text_pass", "text_pass_always")
CROWD_CELLS = ("s3-market-160", "combat-160")
# What must match across the compared reports. effectiveSettings separates the Performance preset from
# plain Low at the same quality (render scale, frame cap, appearance, ...); runtimeBuild separates the
# debug editor binary from a release template.
CONFIGURATION = ("renderingMethod", "graphicsQuality", "viewport", "videoAdapter", "headless", "bodyCap", "fpsCap",
                 "map", "effectiveSettings", "runtimeBuild")
RUNTIME_BUILD_KEYS = ("debug", "editor", "release", "template", "standalone")
METRICS = ("frameMilliseconds", "renderGpuSumMilliseconds", "worldRenderGpuMilliseconds",
           "textPassRenderGpuMilliseconds", "rootRenderGpuMilliseconds", "totalDrawCalls", "totalObjects",
           "textPassDrawn")
GATED = ("frameMilliseconds", "renderGpuSumMilliseconds")


def variant_of(report: dict) -> str:
    names = parse_diagnostics(str(report.get("diagnostics", "")))
    other = sorted(set(names) - {"no_overhead", "no_text_pass", "text_pass_always"})
    if other or len(names) > 1:
        raise EvidenceError(f"gate reports take one overhead/text-pass diagnostic, not {names}")
    if "no_overhead" in names:
        return "no_overhead"
    return {"off": "no_text_pass", "always": "text_pass_always", "auto": "full"}[text_pass_mode(names)]


def configuration_of(report: dict) -> dict:
    measurement = report.get("measurement") or {}
    build = report.get("runtimeBuild") or {}
    out = {key: report.get(key) for key in CONFIGURATION}
    out["fpsCap"] = measurement.get("fpsCap")
    out["runtimeBuild"] = {key: build.get(key) for key in RUNTIME_BUILD_KEYS}
    return out


def _cell_values(cell: dict) -> dict:
    summary = cell.get("summary") or {}
    values: dict = {}
    for metric in METRICS:
        dist = summary.get(metric)
        if isinstance(dist, dict) and dist.get("count"):
            values[metric] = {"mean": float(dist["mean"]), "p95": float(dist["p95"])}
    memory = cell.get("memory") or {}
    video = (memory.get("afterSample") or {}).get("videoBytes")
    spawned = (memory.get("withCrowd") or {}).get("videoBytes")
    if isinstance(video, (int, float)) and not isinstance(video, bool):
        values["videoBytesAfterSample"] = float(video)
        # The diagnostics apply between these two samples of one process, so this
        # isolates what they free from the run-to-run spread of total VRAM.
        if isinstance(spawned, (int, float)) and not isinstance(spawned, bool):
            values["videoBytesSampleMinusSpawn"] = float(video) - float(spawned)
    return values


def collect(reports: list[dict]) -> tuple[dict, dict]:
    """{variant: {cell: [values per repeat]}} and the shared configuration."""
    if not reports:
        raise EvidenceError("no reports")
    shared = configuration_of(reports[0])
    table: dict = {variant: {} for variant in VARIANTS}
    for report in reports:
        if report.get("benchmark") != "crowd_presentation":
            raise EvidenceError("not a crowd-presentation report")
        if configuration_of(report) != shared:
            raise EvidenceError(f"reports mix configurations: {configuration_of(report)} vs {shared}")
        if report.get("failures"):
            raise EvidenceError("a report lists failures")
        variant = variant_of(report)
        # OV-0 records in every sampled cell, and each diagnostic in effect: an older harness's
        # no_overhead reached only re-presented actors (120 of 160 market banners stayed up).
        validate_overhead_diagnostics(report, {"diagnostics": str(report.get("diagnostics", "")),
                                               "mode": "headless" if report.get("headless") is True else "windowed"},
                                      require_records=True)
        for cell in report.get("cells", []):
            if "summary" in cell:
                table[variant].setdefault(str(cell["id"]), []).append(_cell_values(cell))
    if not table["full"] or not table["no_overhead"] or not table["no_text_pass"]:
        raise EvidenceError("the gate needs full, no_overhead and no_text_pass reports")
    return table, shared


def _average(rows: list[dict], metric: str, stat: str) -> float | None:
    numbers = [row[metric][stat] if stat else row[metric] for row in rows if metric in row]
    return statistics.fmean(numbers) if numbers else None


def _delta(table: dict, minuend: str, subtrahend: str, cell: str) -> dict:
    out: dict = {}
    first, second = table[minuend].get(cell), table[subtrahend].get(cell)
    if not first or not second:
        return out
    for metric in METRICS:
        for stat in ("mean", "p95"):
            a, b = _average(first, metric, stat), _average(second, metric, stat)
            if a is not None and b is not None:
                out.setdefault(metric, {})[stat] = round(a - b, 3)
    for key, label in (("videoBytesAfterSample", "videoMiBAfterSample"),
                       ("videoBytesSampleMinusSpawn", "videoMiBInProcess")):
        a, b = _average(first, key, ""), _average(second, key, "")
        if a is not None and b is not None:
            out[label] = round((a - b) / 1048576.0, 2)
    return out


def gate(table: dict, mean_ms: float = 1.0, p95_ms: float = 2.0, headless: bool = False) -> dict:
    cells = sorted(set(table["full"]))
    result: dict = {"thresholds": {"meanMs": mean_ms, "p95Ms": p95_ms, "gatedMetrics": list(GATED),
                                   "crowdCells": list(CROWD_CELLS)},
                    "repeats": {variant: {cell: len(rows) for cell, rows in table[variant].items()}
                                for variant in VARIANTS},
                    "cells": {}, "reasons": []}
    for cell in cells:
        row = {"recoverable": _delta(table, "full", "no_overhead", cell),
               "textPass": _delta(table, "full", "no_text_pass", cell)}
        if table["text_pass_always"].get(cell):
            row["idleSaving"] = _delta(table, "text_pass_always", "full", cell)
        result["cells"][cell] = row
        if cell not in CROWD_CELLS:
            continue
        for metric in GATED:
            values = row["recoverable"].get(metric, {})
            if values.get("mean", 0.0) >= mean_ms or values.get("p95", 0.0) >= p95_ms:
                result["reasons"].append(f"{cell} {metric}: mean {values.get('mean')} ms, p95 {values.get('p95')} ms")
    missing = [cell for cell in CROWD_CELLS if cell not in result["cells"]]
    result["verdict"] = "GO" if result["reasons"] else ("INCOMPLETE" if missing else "NO-GO")
    if headless:
        # Headless Godot never draws, so the text pass never runs: no evidence either way.
        result["verdict"], result["reasons"] = "HEADLESS", ["headless runs never draw the world-text pass"]
    result["missingCrowdCells"] = missing
    return result


def markdown(result: dict, shared: dict) -> str:
    lines = [f"Overhead-text gate (OV-0): {result['verdict']}", "",
             "Configuration: " + ", ".join(f"{key} {json.dumps(shared.get(key), sort_keys=True)}"
                                           for key in CONFIGURATION), "",
             "| Cell | Comparison | Frame mean / p95 ms | GPU sum mean / p95 ms | Text GPU mean ms | Draws (all) "
             "| VRAM MiB | VRAM MiB in-process |",
             "| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: |"]
    for cell, row in result["cells"].items():
        for label, key in (("full - no_overhead", "recoverable"), ("full - no_text_pass", "textPass"),
                           ("always - full", "idleSaving")):
            delta = row.get(key)
            if delta is None:
                continue
            def pair(metric: str) -> str:
                values = delta.get(metric, {})
                return f"{values.get('mean', '-')} / {values.get('p95', '-')}"
            lines.append(f"| {cell} | {label} | {pair('frameMilliseconds')} | {pair('renderGpuSumMilliseconds')} | "
                         f"{delta.get('textPassRenderGpuMilliseconds', {}).get('mean', '-')} | "
                         f"{delta.get('totalDrawCalls', {}).get('mean', '-')} | {delta.get('videoMiBAfterSample', '-')} | "
                         f"{delta.get('videoMiBInProcess', '-')} |")
    lines += ["", "Reasons: " + ("; ".join(result["reasons"]) or "none"),
              "Positive numbers are what the first variant costs more. Differences of averaged means and p95s; "
              "runs are not frame-paired."]
    return "\n".join(lines) + "\n"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("reports", nargs="+", type=Path)
    parser.add_argument("--mean-ms", type=float, default=1.0)
    parser.add_argument("--p95-ms", type=float, default=2.0)
    parser.add_argument("--json", type=Path)
    parser.add_argument("--markdown", type=Path)
    args = parser.parse_args(argv)
    try:
        reports = [json.loads(path.read_text(encoding="utf-8")) for path in args.reports]
        table, shared = collect(reports)
        result = gate(table, args.mean_ms, args.p95_ms, shared.get("headless") is True)
    except (EvidenceError, OSError, ValueError, KeyError) as exc:
        print(f"overhead_text_gate: {exc}", file=sys.stderr)
        return 2
    result["configuration"] = shared
    result["reports"] = [str(path) for path in args.reports]
    text = markdown(result, shared)
    if args.json:
        args.json.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    if args.markdown:
        args.markdown.write_text(text, encoding="utf-8")
    print(text, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
