"""Run fresh, isolated offline road comparisons under the shared GPU lock.

Run --qualification separately from timing; pixel reads are never timed.
Settings and renderer are explicit and no player profile is read or copied.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
from pathlib import Path
import re
import struct
import sys
import uuid

PROJECT = Path(__file__).resolve().parents[1]
ROOT = PROJECT.parent
sys.path.insert(0, str(PROJECT / "tools"))
sys.path.insert(0, str(PROJECT / "tests/integration"))
from crowd_benchmark_support import BenchmarkLock, default_lock_path
from interior_load_benchmark import run_owned_engine
from continent_stream_benchmark import engine_error, process_memory_summary


def write(path: Path, value: dict) -> None:
    path.write_text(json.dumps(value, indent=2, allow_nan=False) + "\n", encoding="utf-8")


def percentile(values: list[float], fraction: float) -> float:
    values = sorted(values)
    return values[max(0, math.ceil(len(values) * fraction) - 1)] if values else 0


def summarize(report: dict) -> dict:
    frames = report.get("frames", [])
    durations = [r["frame_ms"] for r in frames if r["frame_ms"] > 0]
    by_view = {}
    for index in sorted({r.get("view",0) for r in frames}):
        rows = [r for r in frames if r.get("view",0) == index]
        by_view[str(index)] = {"frames":len(rows),
            "gpu_ms_p50":percentile([r.get("gpu_ms",0) for r in rows],.5),
            "frame_ms_p50":percentile([r["frame_ms"] for r in rows],.5),
            "draw_calls_p50":percentile([r["draw_calls"] for r in rows],.5),
            "primitives_p50":percentile([r["primitives"] for r in rows],.5)}
    return {"frames": len(durations), "p50_ms": percentile(durations, .5),
            "p95_ms": percentile(durations, .95), "p99_ms": percentile(durations, .99),
            "max_ms": max(durations, default=0),
            "unfocused_frames": sum(not r["focused"] for r in frames),
            "draw_calls_p50": percentile([r["draw_calls"] for r in frames], .5),
            "primitives_p50": percentile([r["primitives"] for r in frames], .5),
            "gpu_ms_p50": percentile([r.get("gpu_ms",0) for r in frames], .5),
            "gpu_ms_p95": percentile([r.get("gpu_ms",0) for r in frames], .95),
            "render_cpu_ms_p50": percentile([r.get("render_cpu_ms",0) for r in frames], .5),
            "by_view":by_view}


def input_identity(project: Path, config: dict) -> dict:
    selected = {project / "project.godot", Path(__file__),
                project / "tests/integration/road_texture_benchmark.gd"}
    for folder in ["src/world", "src/runtime", "src/dev/road_texture_trial"]:
        for extension in ["*.gd", "*.gdshader", "*.gdshaderinc"]:
            selected.update((project / folder).rglob(extension))
    def path_for(raw):
        return Path(os.path.abspath(project / raw[6:] if raw.startswith("res://") else Path(raw)))
    def visit_glb(path):
        if path in selected: return
        selected.add(path)
        with path.open("rb") as stream:
            stream.seek(12)
            length, kind = struct.unpack("<II",stream.read(8))
            if kind != 0x4e4f534a: raise ValueError("invalid input GLB JSON header")
            document = json.loads(stream.read(length))
        for image in document.get("images",[]):
            uri = image.get("uri","")
            if uri and not uri.startswith("data:"):
                selected.add(Path(os.path.abspath(path.parent / uri)))
    selected.add(path_for(config["lighting_manifest"]))
    for raw in config.get("manifests", []):
        path = path_for(raw)
        selected.add(path)
        document = json.loads(path.read_text())
        glb = document.get("asset", {}).get("glb")
        if glb:
            glb_path = Path(os.path.abspath(path.parent / glb))
            visit_glb(glb_path)
            for uri in document.get("externalResources",{}):
                selected.add(Path(os.path.abspath(glb_path.parent / uri)))
        for uri in document.get("externalMeshes",{}):
            visit_glb(Path(os.path.abspath(path.parent / uri)))
    for raw in config.get("trials",[]):
        path = path_for(raw)
        # Include the complete private generation, including all coverage/flow
        # mips and exact collision payloads. This is deliberately outside timing.
        selected.update(p for p in path.parents[3].rglob("*") if p.is_file())
    pool_index = project.parent / "eloria-assets/maps/_shared/meshes/index.json"
    selected.add(pool_index)
    for path in (project / "src/world/look/textures").glob("*"):
        if path.is_file(): selected.add(path)
        if path.suffix == ".import":
            for resource in re.findall(r'res://(\.godot/imported/[^"\n]+)',path.read_text()):
                selected.add(project / resource)
    return {str(path): hashlib.sha256(path.read_bytes()).hexdigest()
            for path in sorted(selected) if path.is_file()}


def run(args) -> dict:
    project = args.project.resolve()
    output = args.output.resolve()
    if output.exists():
        raise ValueError("Each run needs a new output directory")
    if not output.is_relative_to((PROJECT / "test-artifacts").resolve()):
        raise ValueError("Keep generated reports/profiles in this task's ignored test-artifacts")
    template = json.loads(args.config.read_text(encoding="utf-8"))
    if not args.qualification and ("debug_lift" in template or any(template.get(k) for k in ["debug_trial", "debug_coverage"])):
        raise ValueError("Debug probes and altered road height are qualification-only")
    if not args.qualification and (not template.get("views") or not template.get("probes")):
        raise ValueError("Timed runs require fixed probes/views; no mesh readback fallback")
    output.mkdir(parents=True)
    config = dict(template, output=str(output / "report.json"), run_id=uuid.uuid4().hex,
                  qualification=args.qualification, renderer=args.renderer)
    config_path = output / "configuration.json"
    write(config_path, config)
    environment = {k: v for k, v in os.environ.items()
                   if not k.startswith(("ELORIA_", "RABBITLANDS_", "RL_STREAM_", "RL_INTERIOR_"))}
    profile = output / "profile"
    environment.update(APPDATA=str(profile / "APPDATA"), LOCALAPPDATA=str(profile / "LOCALAPPDATA"),
                       ELORIA_LOOK=template.get("look", "painted_ground"), ELORIA_LOOK_QUALITY="high",
                       ELORIA_NO_MAP_CACHE="1", ELORIA_NO_GEOMETRY_CACHE="1",
                       ELORIA_VRAM_TEXTURES="0", RABBITLANDS_PREPARED_CONTENT="raw")
    settings = profile / "APPDATA/Godot/app_userdata/Eloria/eloria_hud.cfg"
    settings.parent.mkdir(parents=True)
    settings.write_text('[graphics]\nmap_texture_quality="full"\nappearance="painted_ground"\n'
                        'decorative_grass=false\nfps_limit=0\n', encoding="utf-8")
    command = [str(args.godot.resolve()), "--path", str(project), "--audio-driver", "Dummy",
               "--rendering-method", args.renderer, "--resolution", "1280x720",
               "--position", "100,100", "--script", "res://tests/integration/road_texture_benchmark.gd",
               "--", "--config=" + str(config_path)]
    log = output / "engine.log"
    before = input_identity(project, config)
    exit_code, samples, timed_out = run_owned_engine(command, environment, log, args.timeout)
    after = input_identity(project, config)
    report_path = output / "report.json"
    report = json.loads(report_path.read_text()) if report_path.exists() else {}
    errors = []
    if exit_code or timed_out: errors.append("engine_failed_or_timed_out")
    engine_output = log.read_text(errors="replace")
    if engine_error(engine_output): errors.append("engine_error")
    if re.search(r"ObjectDB.*leaked|RID allocations.*leaked|Resources still in use at exit", engine_output):
        errors.append("engine_resource_leak")
    if not report or not report.get("ok"): errors.append("report_missing_or_failed")
    effective = report.get("effective_settings",{})
    if not effective or (effective.get("texture_skip") != 0 or effective.get("texture_mode") != "off"
                      or effective.get("decorative_grass") is not False or effective.get("look") != 1):
        errors.append("effective_settings_mismatch")
    window = report.get("window", {})
    if window.get("renderer") != args.renderer or window.get("size") != [1280, 720]:
        errors.append("render_configuration_mismatch")
    witnesses = template.get("expected_ground", [])
    ground = report.get("ground", [])
    if witnesses:
        if len(witnesses) != len(ground):
            errors.append("ground_witness_count_mismatch")
        # Intersecting ribbons can exchange the winning road at an equal-height
        # overlap after the BVH is rebuilt. Require the same road collision class,
        # surface and sub-millimetre height, rather than a particular tie winner.
        elif any(not actual.get("hit") or not str(actual.get("collider", "")).startswith("Walk_")
                 or actual.get("footstep") != expected.get("footstep")
                 or max(abs(a-b) for a,b in zip(actual["position"], expected["position"])) > .0001
                 for actual, expected in zip(ground,witnesses)):
            errors.append("ground_witness_mismatch")
    if report.get("configuration", {}).get("run_id") != config["run_id"]: errors.append("fresh_identity_mismatch")
    if before != after: errors.append("inputs_changed_during_run")
    frame_summary = summarize(report)
    frame_summary["gpu_timing_available"] = any(r.get("gpu_ms",0) > 0 for r in report.get("frames",[]))
    if not args.qualification and not frame_summary["frames"]: errors.append("timed_frames_missing")
    if not args.qualification and frame_summary["unfocused_frames"]: errors.append("timed_window_unfocused")
    result = {"ok": not errors, "errors": errors, "report": str(report_path), "log": str(log),
              "configuration_sha256": hashlib.sha256(config_path.read_bytes()).hexdigest(),
              "timing": report.get("timing"), "memory": report.get("after_memory"),
              "frames": frame_summary, "process_memory": process_memory_summary(samples),
              "scope": report.get("scope"), "window": report.get("window"),
              "inputs_unchanged": before == after, "input_sha256": before}
    write(output / "summary.json", result)
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--godot", type=Path, required=True)
    parser.add_argument("--project", type=Path, default=PROJECT,
                        help="Optional task-owned immutable source snapshot fixture")
    parser.add_argument("--renderer", choices=["forward_plus", "gl_compatibility"], default="forward_plus")
    parser.add_argument("--qualification", action="store_true")
    parser.add_argument("--timeout", type=int, default=180)
    args = parser.parse_args()
    with BenchmarkLock(default_lock_path(PROJECT), label="map-consolidation-suncoil-road-trial"):
        result = run(args)
    print(json.dumps({k: v for k, v in result.items() if k != "input_sha256"}, indent=2))
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
