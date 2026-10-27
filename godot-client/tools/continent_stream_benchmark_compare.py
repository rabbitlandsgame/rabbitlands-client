"""Compare matched rendered route runs; preserve per-run tails, not pooled FPS.

Three or more pairs are required for the performance target verdict. This does
not prove geometry parity or end-to-end player behavior; those need independent
qualification. No engine workload or source/profile mutation is performed.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from statistics import median

ROOT = Path(__file__).resolve().parents[2]
SETTINGS = ["manifest", "points", "walk_speed", "fast_speed", "repeats", "fps_limit",
            "budget_mib", "mip_skip", "sidecars", "speed_order", "ground_probe", "main_listeners", "arrival_radius"]


def compare(controls: list[dict], candidates: list[dict]) -> dict:
    errors = []
    if len(controls) != len(candidates):
        errors.append("unequal_pair_count")
    if len(controls) < 3:
        errors.append("fewer_than_three_pairs")
    all_runs = controls+candidates
    ids = [run.get("configuration",{}).get("run_id") for run in all_runs]
    paths = [run.get("output") for run in all_runs]
    if any(not key for key in ids) or len(set(ids)) != len(ids):
        errors.append("missing_or_reused_run_ids")
    if any(not key for key in paths) or len(set(paths)) != len(paths):
        errors.append("missing_or_reused_run_outputs")
    rows = []
    orders = set()
    for index, (control, candidate) in enumerate(zip(controls, candidates)):
        changed = [key for key in SETTINGS if control.get("configuration", {}).get(key) != candidate.get("configuration", {}).get(key)]
        if changed:
            errors.append(f"pair_{index}_settings_differ:" + ",".join(changed))
        if not control.get("qualified") or not candidate.get("qualified"):
            errors.append(f"pair_{index}_unqualified")
        control_start,candidate_start = control.get("process_started_monotonic_ns",0),candidate.get("process_started_monotonic_ns",0)
        order = "AB" if control_start < candidate_start else "BA"
        if not control_start or not candidate_start or control_start == candidate_start:
            order = "unknown"
            errors.append(f"pair_{index}_process_order_unknown")
        orders.add(order)
        rows.append({"pair":index,"control":control.get("output"),"candidate":candidate.get("output"),
                     "process_order":order,"control_start_monotonic_ns":control_start,"candidate_start_monotonic_ns":candidate_start,
                     "control_movement":control.get("movement",{}),"candidate_movement":candidate.get("movement",{}),
                     "control_movement_and_settle":control.get("movement_and_settle",{}),
                     "candidate_movement_and_settle":candidate.get("movement_and_settle",{}),
                     "control_settle_ms":control.get("post_route_settle_ms"),"candidate_settle_ms":candidate.get("post_route_settle_ms"),
                     "control_arrival_ms":control.get("arrival_wall_ms"),"candidate_arrival_ms":candidate.get("arrival_wall_ms"),
                     "control_env":control.get("configuration",{}).get("environment_overrides",[]),
                     "candidate_env":candidate.get("configuration",{}).get("environment_overrides",[])})
    if not {"AB","BA"}.issubset(orders):
        errors.append("process_order_not_counterbalanced")
    def metric(group: list[dict], key: str, scope: str = "movement") -> float:
        return median([float(run.get(scope,{}).get(key,0)) for run in group]) if group else 0
    def wall(group: list[dict], key: str) -> float:
        return median([float(run.get(key,0)) for run in group]) if group else 0
    def peak(group: list[dict], key: str) -> float:
        return max([float(run.get("peak_memory",{}).get(key,0)) for run in group],default=0)
    base_max, test_max = metric(controls,"max_ms"),metric(candidates,"max_ms")
    base_p99,test_p99 = metric(controls,"p99_ms"),metric(candidates,"p99_ms")
    base_combined_max,test_combined_max = metric(controls,"max_ms","movement_and_settle"),metric(candidates,"max_ms","movement_and_settle")
    base_combined_p99,test_combined_p99 = metric(controls,"p99_ms","movement_and_settle"),metric(candidates,"p99_ms","movement_and_settle")
    base_settle,test_settle = wall(controls,"post_route_settle_ms"),wall(candidates,"post_route_settle_ms")
    base_memory = max([float(run.get("peak_process_rss_bytes",0)) for run in controls],default=0)
    test_memory = max([float(run.get("peak_process_rss_bytes",0)) for run in candidates],default=0)
    ground_ok = all(run.get("movement",{}).get("ground_missing_frames",1) == 0
                    and run.get("movement",{}).get("bounds_not_resident_frames",1) == 0
                    and run.get("movement",{}).get("ground_probed_frames",0) > 0 for run in candidates)
    targets = {"median_worst_frame_25_percent_lower":base_max > 0 and test_max <= base_max*.75,
               "median_p99_target":base_p99 > 0 and test_p99 <= (base_p99*.8 if base_p99 > 16.7 else base_p99+2),
               "zero_terrain_deadline_misses":bool(candidates) and ground_ok,
               "peak_process_resident_within_10_percent":base_memory > 0 and test_memory <= base_memory*1.1,
               "combined_worst_frame_not_regressed":base_combined_max > 0 and test_combined_max <= base_combined_max,
               "combined_p99_within_two_ms":base_combined_p99 > 0 and test_combined_p99 <= base_combined_p99+2,
               "settle_wall_within_250ms":bool(controls and candidates) and test_settle <= base_settle+250}
    return {"pairs":rows,"validation_errors":errors,
            "median_worst_ms":{"control":base_max,"candidate":test_max},
            "median_p99_ms":{"control":base_p99,"candidate":test_p99},
            "median_combined_worst_ms":{"control":base_combined_max,"candidate":test_combined_max},
            "median_combined_p99_ms":{"control":base_combined_p99,"candidate":test_combined_p99},
            "median_post_route_settle_ms":{"control":base_settle,"candidate":test_settle},
            "median_arrival_wall_ms":{"control":wall(controls,"arrival_wall_ms"),"candidate":wall(candidates,"arrival_wall_ms")},
            "maximum_process_rss_bytes":{"control":base_memory,"candidate":test_memory},
            "maximum_manifest_resident_estimate_bytes":{"control":peak(controls,"resident_estimated_bytes"),"candidate":peak(candidates,"resident_estimated_bytes")},
            "maximum_gpu_video_bytes":{"control":peak(controls,"video_gpu_bytes"),"candidate":peak(candidates,"video_gpu_bytes")},
            "targets":targets,"performance_targets_met":not errors and all(targets.values()),
            "timing_protocol":"Declared before the final cohort: original movement targets, plus median movement+settle worst not above baseline, combined p99 not above baseline+2ms, and median settle wall not above baseline+250ms. Arrival wall is reported separately; differing arrival radius remains a settings mismatch.",
            "limitations":"Per-run median tails from matched route settings; no confidence interval inferred from a small cohort. OS/driver caches remain uncontrolled. Geometry parity, Main-listener coverage and disk tradeoffs require their separate evidence."}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--control",type=Path,action="append",required=True)
    parser.add_argument("--candidate",type=Path,action="append",required=True)
    parser.add_argument("--output",type=Path,required=True)
    args = parser.parse_args()
    output = args.output.resolve()
    if not output.is_relative_to((ROOT/".local").resolve()):
        parser.error("Output must be in the task's ignored .local directory")
    def read(path: Path) -> dict:
        folder = path if path.is_dir() else path.parent
        result = json.loads((folder/"summary.json").read_text(encoding="utf-8"))
        result["inputs"] = json.loads((folder/"inputs.json").read_text(encoding="utf-8"))
        return result
    controls,candidates = [read(path) for path in args.control],[read(path) for path in args.candidate]
    result = compare(controls,candidates)
    inputs = [run["inputs"] for run in controls+candidates]
    if inputs and any(value != inputs[0] for value in inputs):
        result["validation_errors"].append("cohort_runtime_or_import_inputs_differ")
        result["performance_targets_met"] = False
    output.parent.mkdir(parents=True,exist_ok=True)
    output.write_text(json.dumps(result,indent=2),encoding="utf-8")
    print(json.dumps(result,indent=2))
    return int(bool(result["validation_errors"]))


if __name__ == "__main__":
    raise SystemExit(main())
