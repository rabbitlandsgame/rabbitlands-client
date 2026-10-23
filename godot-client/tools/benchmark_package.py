"""Explicit local-only workload export layered on normal client packaging."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import re

PROFILE = "client-performance-v1"
WORKLOAD_FILES = frozenset({
    "tests/integration/crowd_presentation_benchmark.gd",
    "tests/integration/crowd_benchmark_main.gd",
    "tests/integration/crowd_benchmark_main.tscn",
    "tests/integration/performance_workloads.gd",
})


def prepare_export(project: Path) -> None:
    """Keep only allowlisted workloads in the disposable package worktree.

    Normal exports retain their tests exclusion. This function is called only
    after the standalone benchmark option has been validated by the packager.
    Actor imports, loose assets, texture policies and the game entry stay as
    configured by the ordinary packaging pipeline.
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
    for path in files:
        if path.relative_to(root).as_posix() not in WORKLOAD_FILES:
            path.unlink()
    presets.write_text(text.replace("tests/*,", ""), encoding="utf-8", newline="\n")
    # Editor authoring tools do not run in a standalone client. Avoid importing
    # their private working resources while preparing this disposable export.
    authoring = root / "world_authoring"
    if authoring.is_dir():
        (authoring / ".gdignore").write_text("", encoding="utf-8")
    config = root / "project.godot"
    if config.is_file():
        settings = config.read_text(encoding="utf-8")
        settings = re.sub(r'(\[editor_plugins\]\s*)enabled\s*=\s*[^\n]*',
                          r'\1enabled=PackedStringArray()', settings)
        config.write_text(settings, encoding="utf-8")
    marker = {"schemaVersion": 1, "profile": PROFILE,
              "executionKind": "exported-local-benchmark",
              "script": "res://tests/integration/crowd_presentation_benchmark.gd",
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
                "scope": "all staged files except this identity manifest", "artifacts": artifacts}
    destination.write_text(json.dumps(document, indent=2) + "\n", encoding="utf-8")
    return destination
