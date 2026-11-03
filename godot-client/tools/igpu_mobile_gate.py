"""Mobile-on-iGPU gate (wave 2 gate G1, MOB-C6 criteria): Forward+ against Mobile.

Reads finished crowd-runner runs (tests/integration/run_crowd_presentation_benchmark.py:
the `<run>.process.json` files, or directories holding them) of one configuration run
under both renderers, normally the iGPU proxy (--engine-arg=--gpu-index=1, --affinity
3C0), --settings-profile performance --fps-cap 0 (0.75 render scale, FSR1), at
1280x720 and 1920x1080, interleaved F+/Mobile/F+/Mobile with --seed-profile (warm),
plus one cold run (no --seed-profile) per renderer for the first arrival.

Warm runs are paired per resolution in start order (the i-th Forward+ run with the i-th
Mobile run). GO when every criterion holds in every pair (at least --repeats pairs at
each resolution):
  1. world GPU: Mobile `summary.worldRenderGpuMilliseconds.mean` <= --gpu-ratio (0.85) x
     Forward+ in both crowd cells (s3-market-160, combat-160) at both resolutions;
  2. frame-work p99 (`frameTime.p99`) no more than --p99-worse (5 %) worse, every shared cell;
  3. peak working set (the runner's process sampler) no more than --memory-worse (5 %) higher;
  4. cold first arrival not worse: cold runs, `firstArrival.arrivalReportMs` (else
     `firstArrival.readyMs`, else `worldReadiness.waitMilliseconds`), Mobile <= Forward+;
  5. zero new error lines: every given run is one the runner marked valid (it rejects any
     SCRIPT ERROR/ERROR: line); an invalid run is listed and the verdict is INVALID-INPUT.
Missing resolutions, cells, pairs or cold runs give INCOMPLETE. The configuration (adapter,
GPU index, affinity, settings profile, quality, frame cap, render scale, memory class, body
cap, map, build kind, harness revision) must match across all runs. Usage:

    python tools/igpu_mobile_gate.py RUNS... [--json out.json] [--markdown out.md]
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import statistics
import sys

RENDERERS = ("forward_plus", "mobile")
CROWD_CELLS = ("s3-market-160", "combat-160")
RESOLUTIONS = ((1280, 720), (1920, 1080))
GPU_METRIC = "worldRenderGpuMilliseconds"


class GateError(ValueError):
    pass


def _engine_value(engine_args: list, name: str):
    for index, token in enumerate(engine_args or []):
        if token == name:
            return engine_args[index + 1] if index + 1 < len(engine_args) else True
        if isinstance(token, str) and token.startswith(name + "="):
            return token.split("=", 1)[1]
    return None


def load_runs(paths: list[Path]) -> list[dict]:
    files: list[Path] = []
    for path in paths:
        files += sorted(path.glob("*.process.json")) if path.is_dir() else [path]
    if not files:
        raise GateError("no <run>.process.json files")
    runs = []
    for path in files:
        metadata = json.loads(path.read_text(encoding="utf-8"))
        report_path = Path(metadata.get("report", ""))
        report = json.loads(report_path.read_text(encoding="utf-8")) if report_path.is_file() else None
        runs.append({"path": str(path), "metadata": metadata, "report": report})
    return runs


def describe(run: dict) -> dict:
    metadata, report = run["metadata"], run["report"] or {}
    measurement = report.get("measurement") or {}
    settings = report.get("effectiveSettings") or {}
    build = report.get("runtimeBuild") or {}
    memory = report.get("memoryClass") or {}
    peaks = (metadata.get("processMemory") or {}).get("peaks") or {}
    working = peaks.get("workingSetBytes") or {}
    arrival = report.get("firstArrival") or {}
    first = arrival.get("arrivalReportMs")
    basis = "arrivalReportMs"
    if first is None:
        first, basis = arrival.get("readyMs"), "readyMs"
    if first is None:
        first, basis = (report.get("worldReadiness") or {}).get("waitMilliseconds"), "worldReadiness.waitMilliseconds"
    cells = {}
    for cell in report.get("cells", []):
        summary = cell.get("summary") or {}
        gpu = summary.get(GPU_METRIC) or {}
        frame = cell.get("frameTime") or {}
        cells[str(cell.get("id"))] = {"worldGpuMean": gpu.get("mean"), "frameP99": frame.get("p99"),
                                      "frameMean": frame.get("mean")}
    revision = ((metadata.get("identityBefore") or {}).get("sourceRevision") or {})
    return {"path": run["path"], "valid": bool((metadata.get("validation") or {}).get("valid")),
            "errors": (metadata.get("validation") or {}).get("errors"),
            "startedUtc": metadata.get("startedUtc"), "renderer": report.get("renderingMethod"),
            "resolution": tuple(report.get("viewport") or ()), "warm": metadata.get("profileSeed") is not None,
            "cells": cells, "peakWorkingSetBytes": working.get("bytes"),
            "firstArrivalMs": first, "firstArrivalBasis": basis,
            "configuration": {"adapter": report.get("videoAdapter"),
                              "gpuIndex": _engine_value(metadata.get("engineArgs"), "--gpu-index"),
                              "affinity": metadata.get("affinityObserved"),
                              "settingsProfile": metadata.get("settingsProfile"),
                              "quality": report.get("graphicsQuality"), "fpsCap": measurement.get("fpsCap"),
                              "renderScale": settings.get("renderScale"), "memoryClass": memory.get("class"),
                              "memoryClassAvailable": memory.get("available"),
                              "bodyCap": report.get("bodyCap") or (report.get("crowdPolicy") or {}).get("bodyCap"),
                              "map": report.get("map"), "headless": report.get("headless"),
                              "build": {k: build.get(k) for k in ("debug", "editor", "template", "standalone")},
                              "commit": revision.get("commit"), "dirty": revision.get("dirty")}}


def _ratio(numerator, denominator):
    if not isinstance(numerator, (int, float)) or not isinstance(denominator, (int, float)) or denominator <= 0:
        return None
    return round(float(numerator) / float(denominator), 4)


def evaluate(runs: list[dict], repeats: int = 2, gpu_ratio: float = .85, p99_worse: float = .05,
             memory_worse: float = .05, expect_profile: str = "performance", expect_fps_cap: int = 0,
             expect_scale: float = .75) -> dict:
    rows = [describe(run) for run in runs]
    result: dict = {"criteria": {"gpuRatio": gpu_ratio, "p99Worse": p99_worse, "memoryWorse": memory_worse,
                                 "repeats": repeats, "crowdCells": list(CROWD_CELLS),
                                 "resolutions": ["%dx%d" % r for r in RESOLUTIONS]},
                    "runs": rows, "pairs": [], "cold": {}, "failures": [], "missing": [], "invalid": []}
    invalid = [row for row in rows if not row["valid"] or row["renderer"] not in RENDERERS]
    result["invalid"] = [{"path": row["path"], "renderer": row["renderer"], "errors": row["errors"]} for row in invalid]
    rows = [row for row in rows if row not in invalid]
    if not rows:
        raise GateError("no valid Forward+ or Mobile runs")
    shared = rows[0]["configuration"]
    for row in rows:
        if row["configuration"] != shared:
            raise GateError(f"runs mix configurations: {row['path']}: {row['configuration']} vs {shared}")
    if shared["settingsProfile"] != expect_profile or shared["fpsCap"] != expect_fps_cap \
            or shared["renderScale"] is None or abs(float(shared["renderScale"]) - expect_scale) > 1e-6:
        raise GateError(f"G1 runs use --settings-profile {expect_profile} --fps-cap {expect_fps_cap} "
                        f"(render scale {expect_scale}); got {shared}")
    if shared["headless"] is not False:
        raise GateError("G1 needs rendered (windowed) runs")
    result["configuration"] = shared
    for resolution in RESOLUTIONS:
        label = "%dx%d" % resolution
        warm = sorted((row for row in rows if row["warm"] and row["resolution"] == resolution),
                      key=lambda row: row["startedUtc"] or "")
        by_renderer = {renderer: [row for row in warm if row["renderer"] == renderer] for renderer in RENDERERS}
        count = min(len(by_renderer["forward_plus"]), len(by_renderer["mobile"]))
        if count < repeats:
            result["missing"].append(f"{label}: {count} warm F+/Mobile pairs, need {repeats}")
        for index in range(count):
            fplus, mobile = by_renderer["forward_plus"][index], by_renderer["mobile"][index]
            pair = {"resolution": label, "repeat": index + 1, "forwardPlus": fplus["path"], "mobile": mobile["path"],
                    "cells": {}, "peakWorkingSetRatio": _ratio(mobile["peakWorkingSetBytes"],
                                                               fplus["peakWorkingSetBytes"])}
            for cell in CROWD_CELLS:
                if cell not in fplus["cells"] or cell not in mobile["cells"]:
                    result["missing"].append(f"{label} repeat {index + 1}: cell {cell} absent")
            for cell in sorted(set(fplus["cells"]) & set(mobile["cells"])):
                a, b = fplus["cells"][cell], mobile["cells"][cell]
                entry = {"worldGpuForwardPlus": a["worldGpuMean"], "worldGpuMobile": b["worldGpuMean"],
                         "worldGpuRatio": _ratio(b["worldGpuMean"], a["worldGpuMean"]),
                         "frameP99ForwardPlus": a["frameP99"], "frameP99Mobile": b["frameP99"],
                         "frameP99Ratio": _ratio(b["frameP99"], a["frameP99"])}
                pair["cells"][cell] = entry
                where = f"{label} repeat {index + 1} {cell}"
                if cell in CROWD_CELLS:
                    if entry["worldGpuRatio"] is None:
                        result["missing"].append(f"{where}: no world GPU time")
                    elif entry["worldGpuRatio"] > gpu_ratio:
                        result["failures"].append(f"{where}: Mobile world GPU {entry['worldGpuRatio']}x Forward+ "
                                                  f"(> {gpu_ratio})")
                if entry["frameP99Ratio"] is None:
                    result["missing"].append(f"{where}: no frame p99")
                elif entry["frameP99Ratio"] > 1 + p99_worse:
                    result["failures"].append(f"{where}: Mobile frame p99 {entry['frameP99Ratio']}x Forward+ "
                                              f"(> {1 + p99_worse})")
            if pair["peakWorkingSetRatio"] is None:
                result["missing"].append(f"{label} repeat {index + 1}: no peak working set")
            elif pair["peakWorkingSetRatio"] > 1 + memory_worse:
                result["failures"].append(f"{label} repeat {index + 1}: Mobile peak working set "
                                          f"{pair['peakWorkingSetRatio']}x Forward+ (> {1 + memory_worse})")
            result["pairs"].append(pair)
    cold = {renderer: [row for row in rows if not row["warm"] and row["renderer"] == renderer] for renderer in RENDERERS}
    for renderer in RENDERERS:
        values = [row["firstArrivalMs"] for row in cold[renderer] if isinstance(row["firstArrivalMs"], (int, float))]
        result["cold"][renderer] = {"runs": len(cold[renderer]), "firstArrivalMs": values,
                                    "median": statistics.median(values) if values else None,
                                    "basis": sorted({row["firstArrivalBasis"] for row in cold[renderer]})}
    if not result["cold"]["forward_plus"]["firstArrivalMs"] or not result["cold"]["mobile"]["firstArrivalMs"]:
        result["missing"].append("cold first arrival: one cold run per renderer is needed")
    elif result["cold"]["mobile"]["median"] > result["cold"]["forward_plus"]["median"]:
        result["failures"].append(f"cold first arrival: Mobile {result['cold']['mobile']['median']} ms > Forward+ "
                                  f"{result['cold']['forward_plus']['median']} ms")
    if result["invalid"]:
        result["verdict"] = "INVALID-INPUT"
    elif result["failures"]:
        result["verdict"] = "NO-GO"
    elif result["missing"]:
        result["verdict"] = "INCOMPLETE"
    else:
        result["verdict"] = "GO"
    return result


def markdown(result: dict) -> str:
    lines = [f"Mobile-on-iGPU gate (G1, MOB-C6): {result['verdict']}", "",
             "Configuration: " + json.dumps(result.get("configuration"), sort_keys=True), "",
             "| Resolution | Repeat | Cell | World GPU F+ ms | World GPU Mobile ms | Ratio | p99 F+ ms | p99 Mobile ms "
             "| p99 ratio | Peak WS ratio |",
             "| --- | ---: | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |"]
    for pair in result["pairs"]:
        for cell, entry in pair["cells"].items():
            lines.append(f"| {pair['resolution']} | {pair['repeat']} | {cell} | {entry['worldGpuForwardPlus']} | "
                         f"{entry['worldGpuMobile']} | {entry['worldGpuRatio']} | {entry['frameP99ForwardPlus']} | "
                         f"{entry['frameP99Mobile']} | {entry['frameP99Ratio']} | {pair['peakWorkingSetRatio']} |")
    cold = result.get("cold", {})
    lines += ["", "Cold first arrival (median ms): Forward+ %s, Mobile %s (%s)" % (
        cold.get("forward_plus", {}).get("median"), cold.get("mobile", {}).get("median"),
        ", ".join(sorted(set(cold.get("forward_plus", {}).get("basis", []) + cold.get("mobile", {}).get("basis", [])))))]
    for title, key in (("Failures", "failures"), ("Missing", "missing")):
        lines.append(f"{title}: " + ("; ".join(result[key]) or "none"))
    if result["invalid"]:
        lines.append("Invalid runs: " + "; ".join(f"{row['path']} ({row['errors']})" for row in result["invalid"]))
    return "\n".join(lines) + "\n"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("runs", nargs="+", type=Path, help="<run>.process.json files or directories holding them")
    parser.add_argument("--repeats", type=int, default=2)
    parser.add_argument("--gpu-ratio", type=float, default=.85)
    parser.add_argument("--p99-worse", type=float, default=.05)
    parser.add_argument("--memory-worse", type=float, default=.05)
    parser.add_argument("--settings-profile", default="performance")
    parser.add_argument("--fps-cap", type=int, default=0)
    parser.add_argument("--render-scale", type=float, default=.75)
    parser.add_argument("--json", type=Path)
    parser.add_argument("--markdown", type=Path)
    args = parser.parse_args(argv)
    try:
        result = evaluate(load_runs(args.runs), args.repeats, args.gpu_ratio, args.p99_worse, args.memory_worse,
                          args.settings_profile, args.fps_cap, args.render_scale)
    except (GateError, OSError, ValueError, KeyError) as exc:
        print(f"igpu_mobile_gate: {exc}", file=sys.stderr)
        return 2
    text = markdown(result)
    if args.json:
        args.json.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    if args.markdown:
        args.markdown.write_text(text, encoding="utf-8")
    print(text, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
