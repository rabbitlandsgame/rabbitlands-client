"""Isolated rendered interior foreground load benchmark and untimed qualification.

One fresh process per arm. This keeps OS/driver caches and measures a production
WorldLoader/controller fixture, not network, avatars or the application curtain.
No player profile or primary checkout is modified.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import statistics
import subprocess
import sys
import time
import uuid

from continent_stream_benchmark import ProcessSampler, engine_error, process_memory_summary

PROJECT = Path(__file__).resolve().parents[1]
ROOT = PROJECT.parent
sys.path.insert(0, str(PROJECT / "tests/integration"))
from crowd_benchmark_support import BenchmarkLock

TARGETS = {
    "four_gates_stormglass_house": "four-gates-stormglass-house",
    "resonant_vault": "resonant_vault",
    "sunmane_wind_caves": "sunmane_wind_caves",
    "landfall_insides": "landfall-insides",
    "landfall_town": "landfall_town",
}
# The interiors whose WorldLoader places imported scenery from a config (src/world/underground_scenery.gd CONFIGS):
# map id -> (config, the number of distinct prepared assets its placements need, or None for exactly as many as
# the config places, and the name the refusal gives them). The config is in every run's input set (input_identity).
SCENERY = {
    "landfall_insides": ("data/world/underground-scenery.json", 155, "underground"),
    "landfall_town": ("data/world/town-scenery.json", None, "town scenery"),
}
LOCK = Path("C:/rabbitlands/.benchmark-locks/client-performance.lock")
DEFAULT_CACHE = ROOT / ".local/geometry-cache-runtime/Godot/app_userdata/Eloria"
DEFAULT_ENGINE = Path("C:/rabbitlands/rabbitlands-client/godot-client/Godot_v4.7.2-stable_win64.exe")


def read(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8-sig"))


def digest(path: Path) -> str:
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def canonical_sha(value: dict) -> str:
    return hashlib.sha256(json.dumps(value,sort_keys=True,separators=(",", ":")).encode()).hexdigest()


def write(path: Path, value: dict) -> None:
    path.write_text(json.dumps(value, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def target_info(target: str) -> dict:
    maps = read(PROJECT / "data/maps/registry.json")["maps"]
    if target in maps:
        item = maps[target]
    else:
        found = [v for v in maps.values() if TARGETS[target] in v.get("manifest", "")]
        if len(found) != 1:
            raise ValueError(f"target is not uniquely registered: {target}")
        item = found[0]
    manifest = item["manifest"]
    path = PROJECT / manifest.removeprefix("res://")
    data = read(path)
    points = [x["position"] for x in data.get("spawnPoints", [])]
    if not points:
        raise ValueError("authored spawn point required")
    # Spawn points are authored traversable anchors. Cover every authored entry
    # section without inventing off-navigation samples; duplicate defaults merge.
    unique = list(dict.fromkeys(tuple(p) for p in points))
    return {"target": target, "manifest": manifest, "focus": points[0],
            "qualification_points": [list(p) for p in unique],
            "source": "eloria-assets/" + path.resolve().relative_to((ROOT / "eloria-assets").resolve()).as_posix(),
            "input_glb_bytes": (path.parent / data["asset"]["glb"]).stat().st_size}


def require_active_scope(info: dict) -> None:
    scope = read(PROJECT / "data/maps/geometry-cache-scope.json")
    registry = read(PROJECT / "data/maps/registry.json")["maps"]
    active = {registry[key].get("manifest") for key in scope.get("maps",[]) if key in registry}
    if info["manifest"] not in active:
        raise ValueError(
            f"{info['target']} is outside the active native geometry scope. The 33 interior candidates "
            "were not promoted after their timing targets failed. For an explicit experiment, "
            "activate data/maps/geometry-cache-interior-candidates.json as geometry-cache-scope.json "
            "only in an owned task worktree, prepare its cache, and restore the production scope afterward. "
            "See docs/client-interior-preparation-performance.md.")


def safe_user_path(value: str, root: Path) -> Path:
    if not value.startswith("user://map-geometry-cache/") or "\\" in value or ":" in value[7:]:
        raise ValueError(f"unsupported cache path: {value}")
    path = root / value[7:]
    resolved = path.resolve()
    if not resolved.is_relative_to(root.resolve()) or ".." in Path(value[7:]).parts:
        raise ValueError("cache path escapes isolated profile")
    return path


def cache_entries(source_root: Path, source: str) -> tuple[Path, list[tuple[Path, dict]]]:
    matches: list[tuple[Path, list[tuple[Path, dict]]]] = []
    for policy in (source_root / "map-geometry-cache").iterdir():
        if not policy.is_dir():
            continue
        selected = []
        for path in policy.glob("entries/*.json"):
            entry = read(path)
            if entry.get("source") == source:
                selected.append((path, entry))
        if selected:
            matches.append((policy, selected))
    if len(matches) != 1 or len(matches[0][1]) != 1:
        raise ValueError(f"need one prepared world entry/policy for {source}; got {len(matches)}")
    policy, selected = matches[0]
    scenery = next((row for map_id, row in SCENERY.items() if map_id in Path(source).parts), None)
    if scenery is not None:
        config_path, count, name = scenery
        assets = []
        config = read(PROJECT / config_path)
        expected = {config["assets"][row["asset"]] for row in config["placements"]}
        # Entries use portable logical paths, while config uses res:// paths.
        expected = {"godot-client/" + p[6:] if p.startswith("res://") else p for p in expected}
        count = len(expected) if count is None else count
        for path in policy.glob("entries/*.json"):
            entry = read(path)
            if entry.get("kind") == "asset" and entry.get("source") in expected:
                assets.append((path, entry))
        if len(assets) != count or {e["source"] for _, e in assets} != expected:
            raise ValueError(f"all {count} {name} assets must be prepared; found {len(assets)}")
        selected += assets
    return policy, selected


def seed_cache(source_root: Path, destination_root: Path, source: str) -> dict:
    """Copy exactly the selected entry closure; never copy unrelated user data."""
    policy, entries = cache_entries(source_root, source)
    files: dict[Path, tuple[Path, str]] = {}
    for entry_path, entry in entries:
        destination = destination_root / entry_path.relative_to(source_root)
        files[destination] = (entry_path, digest(entry_path))
        for logical, sha in entry.get("payloads", {}).items():
            origin = safe_user_path(logical, source_root)
            dest = safe_user_path(logical, destination_root)
            if dest in files and files[dest][1] != sha:
                raise ValueError("payload closure digest conflict")
            files[dest] = origin, sha
    total = 0
    for dest, (origin, sha) in files.items():
        if digest(origin) != sha:
            raise ValueError(f"prepared payload digest mismatch: {origin}")
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(origin, dest)
        if digest(dest) != sha:
            raise ValueError("copied cache digest mismatch")
        total += dest.stat().st_size
    return {"policy": policy.name, "entries": len(entries), "files": len(files), "bytes": total,
            "files_sha256": {p.relative_to(destination_root).as_posix(): sha for p, (_, sha) in files.items()}}


def source_identity(source_root: Path, source: str) -> dict:
    _, entries = cache_entries(source_root,source)
    inputs = {}
    for _, entry in entries:
        for row in entry.get("inputs",[]):
            logical = row["path"]
            if logical in inputs:
                if inputs[logical] != row["sha256"]:
                    raise ValueError("prepared input closure digest conflict")
                continue
            path = (ROOT / logical).resolve()
            if (not path.is_relative_to(ROOT.resolve()) or not logical.startswith(("godot-client/","eloria-assets/"))
                    or ".." in Path(logical).parts or "\\" in logical or ":" in logical):
                raise ValueError("prepared input is outside task source roots")
            actual = digest(path)
            if actual != row["sha256"]:
                raise ValueError(f"prepared source digest mismatch: {logical}")
            inputs[logical] = actual
    return inputs


def input_identity() -> dict:
    paths = [PROJECT / "project.godot", PROJECT / "override.cfg"]
    # A small authored/runtime closure plus native class import products. Assets
    # are validated by production loading and the prepared input rows below.
    for pattern in ["*.gd","*.gdshader","*.gdshaderinc"]:
        paths += list((PROJECT / "src").rglob(pattern))
    paths += [PROJECT / "data/maps/geometry-cache-scope.json", PROJECT / "data/maps/registry.json",
              *(PROJECT / config for config, _count, _name in SCENERY.values()), Path(__file__),
              PROJECT / "tools/interior_load_benchmark_compare.py",PROJECT / "tools/continent_stream_benchmark.py",
              PROJECT / "tests/integration/crowd_benchmark_support.py"]
    paths += list((PROJECT / "tests/integration").glob("interior_load_benchmark*"))
    for path in (PROJECT / "src/world/look/textures").glob("*.png.import"):
        paths.append(path)
        import re
        match = re.search(r'^path="res://([^"]+)"', path.read_text(), re.MULTILINE)
        if match:
            paths.append(PROJECT / match.group(1))
    return {p.relative_to(ROOT).as_posix(): digest(p) if p.is_file() else None for p in paths}


def qualification_errors(report: dict | None, config: dict, config_sha: str,
                         before: dict, after: dict, output: str) -> list[str]:
    errors = []
    if engine_error(output):
        errors.append("engine_error_in_complete_log")
    if before != after:
        errors.append("runtime_or_import_inputs_changed")
    if report is None:
        return errors + ["fresh_report_missing"]
    if report.get("configuration", {}).get("run_id") != config["run_id"]:
        errors.append("report_run_id_mismatch")
    if report.get("configuration_sha256") != config_sha:
        errors.append("report_configuration_digest_mismatch")
    if not report.get("ok"):
        errors.append("engine_checks_failed")
    if not config.get("qualification"):
        timing = report.get("timing", {})
        if not all(float(timing.get(k, 0)) > 0 for k in ["load_call_ms", "first_ready_ms"]):
            errors.append("measured_load_missing")
        if not report.get("frames"):
            errors.append("measured_frames_missing")
        if config.get("diagnostics"):
            errors.append("diagnostic_timing_not_acceptance")
        if (not report.get("window_start",{}).get("focused") or not report.get("window_end",{}).get("focused")
                or any(not row.get("focused") for row in report.get("frames",[]))):
            errors.append("measured_window_not_focused")
    elif not report.get("qualification", {}).get("scene", {}).get("digest"):
        errors.append("qualification_witness_missing")
    return errors


def matched_settings(config: dict, *, include_qualification: bool = True) -> dict:
    excluded = {"mode", "run_id", "report", "output", "profile"}
    if not include_qualification:
        excluded.add("qualification")
    return {k:v for k,v in config.items() if k not in excluded}


def compare(raw_runs: list[dict], native_runs: list[dict]) -> dict:
    if len(raw_runs) != 3 or len(native_runs) != 3:
        raise ValueError("exactly three fresh runs per arm required")
    runs = raw_runs + native_runs
    ids = [r["configuration"]["run_id"] for r in runs]
    if len(set(ids)) != 6:
        raise ValueError("runs must have distinct identities")
    if not all(r["configuration"].get("mode") == "raw" for r in raw_runs) or not all(r["configuration"].get("mode") == "native" for r in native_runs):
        raise ValueError("three raw controls and three native candidates required")
    if not all(r.get("qualified") and not r.get("parse_only") and not r["configuration"].get("qualification") for r in runs):
        raise ValueError("all six runs must qualify as timed loads")
    if any(matched_settings(r["configuration"]) != matched_settings(runs[0]["configuration"]) for r in runs):
        raise ValueError("cohort settings differ")
    for field in ["runtime_inputs_sha256","source_inputs_sha256","cache_inputs_sha256"]:
        if not runs[0].get(field) or any(r.get(field) != runs[0][field] for r in runs):
            raise ValueError(f"cohort input generation differs: {field}")
    orders = ["AB" if a["process_started_monotonic_ns"] < b["process_started_monotonic_ns"] else "BA"
              for a,b in zip(raw_runs,native_runs)]
    if "AB" not in orders or "BA" not in orders:
        raise ValueError("both AB and BA fresh-process orders required")
    result = {"target":runs[0]["configuration"]["target"],"orders":orders,"metrics":{},"pass":True}
    for field, reduction in [("load_call_ms",.20),("first_ready_ms",.10)]:
        raw = statistics.median(r["report"]["timing"][field] for r in raw_runs)
        native = statistics.median(r["report"]["timing"][field] for r in native_runs)
        limit = raw*(1-reduction) if raw >= 100 else raw+10
        passed = native <= limit
        result["metrics"][field] = {"raw_median":raw,"native_median":native,"limit":limit,"pass":passed,
                                    "reduction_fraction":1-native/raw}
        result["pass"] &= passed
    raw_rss = max(r["process_memory"]["peak_process_rss_bytes"] for r in raw_runs)
    native_rss = max(r["process_memory"]["peak_process_rss_bytes"] for r in native_runs)
    memory_pass = raw_rss > 0 and native_rss <= raw_rss*1.10
    result["peak_rss"] = {"raw":raw_rss,"native":native_rss,"limit":raw_rss*1.10,"pass":memory_pass}
    result["pass"] &= memory_pass
    raw_settled = statistics.median(r["report"]["timing"]["through_settled_ms"] for r in raw_runs)
    native_settled = statistics.median(r["report"]["timing"]["through_settled_ms"] for r in native_runs)
    result["through_settled"] = {"raw_median":raw_settled,"native_median":native_settled,
                                 "nonregression_limit":raw_settled+250,"pass":native_settled<=raw_settled+250}
    result["pass"] &= result["through_settled"]["pass"]
    return result


def compare_witness(raw: dict, native: dict) -> dict:
    """Readbacks qualify content, independently of performance acceptance."""
    if not all(r.get("qualified") and r["configuration"].get("qualification") for r in [raw,native]):
        raise ValueError("two successful qualification processes required")
    if raw["configuration"].get("mode") != "raw" or native["configuration"].get("mode") != "native":
        raise ValueError("raw/native witnesses required")
    ids = [r["configuration"].get("run_id") for r in [raw,native]]
    if not all(ids) or len(set(ids)) != 2:
        raise ValueError("distinct nonempty witness run IDs required")
    if matched_settings(raw["configuration"]) != matched_settings(native["configuration"]):
        raise ValueError("qualification settings differ")
    if raw["configuration"]["target"] != native["configuration"]["target"]:
        raise ValueError("qualification targets differ")
    for field in ["runtime_inputs_sha256","source_inputs_sha256","cache_inputs_sha256"]:
        if not raw.get(field) or raw.get(field) != native.get(field):
            raise ValueError("qualification input generation differs")
    a,b = [r["report"]["qualification"] for r in [raw,native]]
    scene = a["scene"]["digest"] == b["scene"]["digest"]
    pixels = a["views"] == b["views"]
    ground = a["ground"] == b["ground"]
    return {"pass":scene and pixels and ground,"scene_material_full_mip_collision_parity":scene,
            "deterministic_time_pixel_and_visibility_parity":pixels,"authored_ground_and_section_parity":ground,
            "raw_textures":a["scene"].get("textures"),"native_textures":b["scene"].get("textures"),
            "pixel_scope":a.get("deterministic_shader_time")}


def compare_cohort(raw_runs: list[dict], native_runs: list[dict], raw_witness: dict, native_witness: dict) -> dict:
    result = compare(raw_runs,native_runs)
    witnesses = [raw_witness,native_witness]
    identities = [r["configuration"].get("run_id") for r in raw_runs+native_runs+witnesses]
    if not all(identities) or len(set(identities)) != 8:
        raise ValueError("all timed/qualification processes must be distinct")
    for witness in witnesses:
        if matched_settings(witness["configuration"],include_qualification=False) != matched_settings(raw_runs[0]["configuration"],include_qualification=False):
            raise ValueError("witness does not match timed cohort settings/target")
        for field in ["runtime_inputs_sha256","source_inputs_sha256","cache_inputs_sha256"]:
            if witness.get(field) != raw_runs[0].get(field):
                raise ValueError("witness does not match timed cohort input generation")
    result["qualification"] = compare_witness(raw_witness,native_witness)
    result["pass"] &= result["qualification"]["pass"]
    return result


def stop_owned_process(process) -> None:
    """Release this Popen child's renderer before releasing the benchmark lock."""
    if process.poll() is not None:
        return
    process.terminate()
    try:
        process.wait(timeout=10)
    except subprocess.TimeoutExpired:
        process.kill()
        process.wait(timeout=10)


def run_owned_engine(command: list[str], env: dict, stdout_path: Path, timeout: float) -> tuple[int,list[dict],bool]:
    """Supervise only this Popen child; cleanup completes while caller holds its lock."""
    samples = []
    timed_out = False
    with stdout_path.open("w",encoding="utf-8") as log:
        process = subprocess.Popen(command,env=env,stdout=log,stderr=subprocess.STDOUT)
        sampler = None
        try:
            sampler = ProcessSampler(process.pid)
            deadline = time.monotonic()+timeout
            while process.poll() is None:
                samples.append(sampler.sample())
                text = stdout_path.read_text(encoding="utf-8",errors="replace")
                if engine_error(text) or time.monotonic() > deadline:
                    timed_out = time.monotonic() > deadline
                    stop_owned_process(process)
                    break
                time.sleep(.25)
            process.wait(timeout=15)
            samples.append(sampler.sample())
        finally:
            try:
                stop_owned_process(process)
            finally:
                if sampler is not None:
                    sampler.close()
    return int(process.returncode),samples,timed_out


def _run_locked(args) -> int:
    target = target_info(args.target)
    if not args.parse_only:
        require_active_scope(target)
    run_id = uuid.uuid4().hex
    output = args.output or ROOT / ".local/interior-load-benchmark" / f"{args.target}-{args.mode}-{run_id[:8]}"
    output = output.resolve()
    if output.exists():
        raise ValueError("output directory must be new (fresh report/profile guard)")
    if not output.is_relative_to((ROOT / ".local").resolve()):
        raise ValueError("benchmark output must be in this task's ignored .local tree")
    output.mkdir(parents=True)
    profile = output / "profile"
    user_root = profile / "APPDATA/Godot/app_userdata/Eloria"
    bundle = seed_cache(args.cache_user_root.resolve(),user_root,target["source"])
    config = {**target,"mode":args.mode,"run_id":run_id,"qualification":args.qualify,
              "report":str(output / "report.json"),"output":str(output),"profile":str(profile),
              "texture_mode":"off","texture_skip":0,"diagnostics":args.diagnostics,
              "container_reuse":args.container_reuse,"bound_prepare":args.bound_prepare,
              "early_world_filter":args.early_world_filter,
              "fixture":"foreground-production-controllers","fps_limit":60,
              "cache_policy":bundle["policy"],"renderer":"gl_compatibility" if args.compatibility else "forward_plus"}
    config_path = output / "configuration.json"
    write(config_path, config)
    config_sha = digest(config_path)
    env = os.environ.copy()
    # Explicit matching defaults; no user settings, old disk-cache overrides,
    # experimental optimization flags or inherited developer texture policies.
    for key in list(env):
        if key.startswith(("ELORIA_", "RL_VERIFY_", "RL_STREAM_", "RABBITLANDS_")):
            env.pop(key)
    env.update(APPDATA=str(profile / "APPDATA"),LOCALAPPDATA=str(profile / "LOCALAPPDATA"),
               RL_INTERIOR_CONFIG=str(config_path),RL_INTERIOR_CONFIG_SHA=config_sha,
               ELORIA_NO_GEOMETRY_CACHE="1" if args.mode == "raw" else "0",
               ELORIA_UNDERGROUND_DIAGNOSTICS="1" if args.diagnostics else "0",
               ELORIA_GEOMETRY_DIAGNOSTICS="1" if args.diagnostics else "0",
               ELORIA_GEOMETRY_CONTAINER_REUSE="1" if args.container_reuse == "on" else "0",
               ELORIA_UNDERGROUND_BOUND_PREPARE="1" if args.bound_prepare == "on" else "0",
               ELORIA_EARLY_WORLD_OBJECT_FILTER="1" if args.early_world_filter == "on" else "0",
               RABBITLANDS_OPTIMIZATION_PROFILE="legacy",RABBITLANDS_PREPARED_CONTENT="raw",
               ELORIA_VRAM_TEXTURES="0")
    command = [str(args.godot),"--path",str(PROJECT),"--rendering-method","gl_compatibility" if args.compatibility else "forward_plus",
               "--resolution","1280x720","--position","0,0","--log-file",str(output / "engine.log"),
               "--script","res://tests/integration/interior_load_benchmark.gd"]
    if args.parse_only:
        command += ["--headless","--check-only"]
    before = input_identity()
    source_before = source_identity(args.cache_user_root.resolve(),target["source"])
    write(output / "inputs-before.json",before)
    write(output / "source-inputs-before.json",source_before)
    write(output / "cache-bundle.json",bundle)
    started = time.perf_counter_ns()
    exit_code,samples,timed_out = run_owned_engine(command,env,output/"stdout.log",args.timeout)
    after = input_identity()
    source_after = source_identity(args.cache_user_root.resolve(),target["source"])
    cache_unchanged = all(digest(user_root / path) == sha for path,sha in bundle["files_sha256"].items())
    complete = (output / "stdout.log").read_text(encoding="utf-8",errors="replace")
    if (output / "engine.log").exists():
        complete += (output / "engine.log").read_text(encoding="utf-8",errors="replace")
    report_path = output / "report.json"
    report = read(report_path) if report_path.is_file() else None
    errors = qualification_errors(report,config,config_sha,before,after,complete) if not args.parse_only else []
    if source_before != source_after: errors.append("source_assets_changed")
    if not cache_unchanged: errors.append("isolated_prepared_cache_changed")
    if exit_code != 0: errors.append(f"process_exit_{exit_code}")
    if timed_out: errors.append("watchdog_timeout")
    if args.parse_only and engine_error(complete): errors.append("parse_error")
    result = {"qualified":not errors,"errors":errors,"configuration":config,"report":report,
              "process_started_monotonic_ns":started,"process_finished_monotonic_ns":time.perf_counter_ns(),
              "command":command,"explicit_environment":{k:v for k,v in env.items() if k.startswith(("ELORIA_","RABBITLANDS_"))},
              "inputs_unchanged":before==after,"process_memory":process_memory_summary(samples),
              "runtime_inputs_sha256":canonical_sha(before),"source_inputs_sha256":canonical_sha(source_before),
              "cache_inputs_sha256":canonical_sha(bundle["files_sha256"]),"cache_inputs_unchanged":cache_unchanged,
              "process_samples":samples,"cache_bundle":bundle,"parse_only":args.parse_only}
    write(output / "summary.json",result)
    print(json.dumps({"qualified":not errors,"errors":errors,"output":str(output),
                      "timing":report.get("timing") if report else None},indent=2))
    return 0 if not errors else 1


def run(args) -> int:
    # Preparation and final source verification also perform disk/CPU work;
    # keep them outside every other agent's timed engine trial, not just ours.
    with BenchmarkLock(LOCK,timeout=0,label="interior-load-benchmark"):
        return _run_locked(args)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--target",choices=TARGETS,required=True)
    parser.add_argument("--mode",choices=["raw","native"],required=True)
    parser.add_argument("--output",type=Path)
    parser.add_argument("--cache-user-root",type=Path,default=DEFAULT_CACHE)
    parser.add_argument("--godot",type=Path,default=DEFAULT_ENGINE)
    parser.add_argument("--qualify",action="store_true",help="Untimed separate-process readback/grounding witness")
    parser.add_argument("--diagnostics",action="store_true",help="Attribution only; do not use as acceptance timing")
    parser.add_argument("--container-reuse",choices=["on","off"],default="on",help="Recorded embedded-image container-read experiment switch")
    parser.add_argument("--bound-prepare",choices=["on","off"],default="on",help="Recorded bounded native underground preparation switch")
    parser.add_argument("--early-world-filter",choices=["on","off"],default="on",help="Recorded world-object final-filter preparation order switch")
    parser.add_argument("--parse-only",action="store_true")
    parser.add_argument("--compatibility",action="store_true",help="Separate renderer qualification; not matched with Forward+")
    parser.add_argument("--timeout",type=int,default=180)
    return run(parser.parse_args())


if __name__ == "__main__":
    raise SystemExit(main())
