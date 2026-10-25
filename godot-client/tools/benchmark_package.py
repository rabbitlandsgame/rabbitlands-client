"""Explicit local-only workload export layered on normal client packaging."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import re

from benchmark_asset_closure import build_asset_closure

PROFILE = "client-performance-v1"
MAIN_LOOP_CLASS = "RabbitLandsCrowdBenchmarkLoop"
MAIN_ENTRY_SCENE = "res://tests/integration/crowd_benchmark_entry.tscn"
EXECUTION_MODE_ENVIRONMENT = "RABBITLANDS_CROWD_BENCH_EXECUTION_MODE"
WORKLOAD_FILES = frozenset({
    "tests/integration/crowd_benchmark_loop.gd",
    "tests/integration/crowd_benchmark_entry.tscn",
    "tests/integration/crowd_presentation_benchmark.gd",
    "tests/integration/crowd_benchmark_main.gd",
    "tests/integration/crowd_benchmark_main.tscn",
    "tests/integration/client_world_readiness.gd",
    "tests/integration/performance_workloads.gd",
    "tests/integration/benchmark_route_content.gd",
    "tests/integration/benchmark_placement_diagnostics.gd",
    "tests/integration/benchmark_mounted_census.gd",
    "tests/integration/benchmark_heat_bolt.gd",
    "tests/integration/prepared_content_parity.gd",
    "tests/integration/benchmark_resource_admission.gd",
    "tests/test_native_streaming_lifetime.gd",
    "tests/test_prepared_content_pilot.gd",
})


def _benchmark_loop_settings(settings: str) -> str:
    """Select the local router only in the disposable build's application section."""
    application = re.search(r"(?m)^\[application\][ \t]*(?:\n|$)", settings)
    if application is None:
        raise ValueError("Benchmark project has no application settings")
    following_section = re.search(r"(?m)^\[", settings[application.end():])
    end = application.end() + following_section.start() if following_section else len(settings)
    body = settings[application.end():end]
    body = re.sub(r"(?m)^run/(?:main_scene|main_loop_type)[ \t]*=[^\n]*(?:\n|$)", "", body)
    # Release templates require a nonempty main scene even for a SceneTree
    # subclass. This inert Node lets the loop decide which real Main to open.
    body = (body.rstrip("\n") + "\nrun/main_loop_type=" + json.dumps(MAIN_LOOP_CLASS)
            + "\nrun/main_scene=" + json.dumps(MAIN_ENTRY_SCENE) + "\n\n")
    return settings[:application.end()] + body + settings[end:]


def prepare_export(project: Path) -> None:
    """Keep only allowlisted workloads in the disposable package worktree.

    Normal exports retain their tests exclusion. This function is called only
    after the standalone benchmark option has been validated by the packager.
    Actor imports, loose assets and texture policies follow ordinary packaging.
    Release templates do not execute --script, so a custom loop dispatches the
    workload only when explicitly requested; otherwise it opens the normal game.
    """
    root = project.resolve()
    tests = (root / "tests").resolve()
    if not tests.is_relative_to(root):
        raise ValueError("Benchmark test directory escapes the build project")
    missing = [name for name in WORKLOAD_FILES if not (root / name).is_file()]
    if missing:
        raise ValueError("Missing benchmark export inputs: " + ", ".join(sorted(missing)))
    files = [p for p in tests.rglob("*") if p.is_file()]
    # Validate the entire set before removing any files, including symlinks.
    if any(not p.resolve().is_relative_to(tests) for p in files):
        raise ValueError("Benchmark test input escapes the build test directory")
    presets = root / "export_presets.cfg"
    text = presets.read_text(encoding="utf-8")
    if "tests/*," not in text:
        raise ValueError("Expected normal test exclusion in export presets")
    config = root / "project.godot"
    if not config.is_file():
        raise ValueError("Benchmark project settings are missing")
    settings = _benchmark_loop_settings(config.read_text(encoding="utf-8"))
    settings = re.sub(r'(\[editor_plugins\]\s*)enabled\s*=\s*[^\n]*',
                      r'\1enabled=PackedStringArray()', settings)
    for path in files:
        if path.relative_to(root).as_posix() not in WORKLOAD_FILES:
            path.unlink()
    presets.write_text(text.replace("tests/*,", ""), encoding="utf-8", newline="\n")
    # Editor authoring tools do not run in a standalone client. Avoid importing
    # their private working resources while preparing this disposable export.
    authoring = root / "world_authoring"
    if authoring.is_dir():
        (authoring / ".gdignore").write_text("", encoding="utf-8")
    config.write_text(settings, encoding="utf-8", newline="\n")
    marker = {"schemaVersion": 1, "profile": PROFILE,
              "executionKind": "exported-local-benchmark",
              "script": "res://tests/integration/crowd_presentation_benchmark.gd",
              "mainLoopClass": MAIN_LOOP_CLASS,
              "mainEntryScene": MAIN_ENTRY_SCENE,
              "executionModeEnvironment": EXECUTION_MODE_ENVIRONMENT,
              "benchmarkExecutionMode": "exported",
              "defaultMainScene": "res://src/app/main.tscn",
              "workloadFiles": sorted(WORKLOAD_FILES)}
    (root / "data/benchmark_profile.json").write_text(
        json.dumps(marker, indent=2) + "\n", encoding="utf-8")


def write_manifest(stage: Path, commit: str) -> Path:
    """Attest executable/PCK and every staged loose input outside timing."""
    destination = stage / "benchmark-package.json"
    artifacts = []
    aggregate = hashlib.sha256()
    for path in sorted(stage.rglob("*")):
        if not path.is_file() or path == destination:
            continue
        relative = path.relative_to(stage).as_posix()
        with path.open("rb") as stream:
            digest = hashlib.file_digest(stream, "sha256").hexdigest()
        artifacts.append({"path": relative, "sha256": digest, "bytes": path.stat().st_size})
        aggregate.update(relative.encode("utf-8") + b"\0" + bytes.fromhex(digest))
    document = {"schemaVersion": 1, "executionKind": "exported-local-benchmark",
                "benchmarkProfile": PROFILE, "sourceCommit": commit,
                "contentHash": aggregate.hexdigest(), "contentComplete": True,
                "scope": "all staged files except this identity manifest", "artifacts": artifacts,
                "assetClosure": build_asset_closure(stage)}
    destination.write_text(json.dumps(document, indent=2) + "\n", encoding="utf-8")
    return destination
