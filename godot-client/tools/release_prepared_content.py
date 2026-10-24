"""Fresh, serial prepared pilot cooking inside an owned release build tree.

The caller owns Godot execution and final import/export. This module never
starts a process, downloads assets, uploads a release, or trusts an old catalog.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
import re
import shutil
from typing import Callable

import prepared_content_package as prepared

FOUR_GATES = "eloria-assets/maps/four-gates/chunks/02_07/world.json"
TEXTURES = ("full", "half", "quarter")
POLICY = "fresh-release-prepared-pilot-v1"


class ReleasePreparedError(prepared.PreparedError):
    pass


def _json(path: Path) -> dict:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ReleasePreparedError(f"object required: {path}")
    return value


def _check(check_budget, phase: str, additional: int = 0) -> None:
    if check_budget is not None:
        check_budget("prepared: " + phase, additional)


class _Overlay:
    """Restore only our exact changed files; never recursively delete inputs."""
    def __init__(self, root: Path, backups: Path, check_budget):
        self.root, self.backups, self.check_budget = root.resolve(), backups, check_budget
        self.saved: dict[Path, Path | None] = {}
        self.backups.mkdir()

    def remember(self, path: Path) -> None:
        path = path.resolve()
        if not path.is_relative_to(self.root) or path.is_symlink():
            raise ReleasePreparedError(f"temporary overlay escaped the owned source: {path}")
        if path in self.saved:
            return
        if path.exists() and not path.is_file():
            raise ReleasePreparedError(f"temporary overlay is not a regular file: {path}")
        backup = None
        if path.is_file():
            _check(self.check_budget, "backup selected input", path.stat().st_size)
            backup = self.backups / str(len(self.saved))
            shutil.copy2(path, backup)  # Snapshot copy must survive an in-place PCK copy.
        self.saved[path] = backup

    def link(self, source: Path, target: Path) -> None:
        if source.is_symlink() or not source.is_file():
            raise ReleasePreparedError(f"staged overlay is not a regular file: {source}")
        if target.is_file() and prepared.digest(source) == prepared.digest(target):
            return
        self.remember(target)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.unlink(missing_ok=True)
        os.link(source, target)  # Same-volume requirement is deliberate; no hidden full copy.
        if prepared.digest(target) != prepared.digest(source):
            raise ReleasePreparedError(f"staged input changed while linking: {source}")

    def isolate(self, path: Path) -> None:
        """Break any retained-cache/stage hard link before an in-place writer."""
        self.remember(path)
        backup = self.saved[path.resolve()]
        if backup is None:
            raise ReleasePreparedError("runtime snapshot input must already exist: " + str(path))
        _check(self.check_budget, "isolate selected import", backup.stat().st_size)
        path.unlink()
        shutil.copy2(backup, path)

    def restore(self) -> None:
        for path, backup in reversed(list(self.saved.items())):
            path.unlink(missing_ok=True)
            if backup is not None:
                backup.replace(path)


def _discover(project: Path, targets: list[tuple[str, str]]) -> dict[str, str]:
    files: dict[str, str] = {}
    for _kind, source in targets:
        closure = prepared.Closure(project, include_sidecars=False)
        closure.visit(prepared.scoped(project.parent, source))
        files.update(closure.files)
    return files


def _overlay_sidecars(project: Path, stage: Path, files: dict[str, str], overlay: _Overlay) -> list[dict]:
    """Use actual selected staged indices/DDS, without copying the whole stage."""
    selected = set(files)
    selected.update(name.removesuffix(".import") for name in files if name.endswith(".import"))
    linked: dict[str, dict] = {}
    for name in sorted(selected):
        image = prepared.scoped(project.parent, name)
        if not image.is_file() or image.suffix.lower() not in {".jpg", ".jpeg", ".png", ".webp"}:
            continue
        index_name = (Path(name).parent / "vram/index.json").as_posix()
        staged_index = prepared.scoped(stage if name.startswith("eloria-assets/") else stage / "app",
            index_name if name.startswith("eloria-assets/") else index_name.removeprefix("godot-client/"))
        if not staged_index.is_file():
            continue
        document = _json(staged_index)
        if document.get("schema") != 1 or document.get("recipeVersion") != 1:
            raise ReleasePreparedError("unsupported actual staged sidecar index: " + index_name)
        target_index = prepared.scoped(project.parent, index_name)
        overlay.link(staged_index, target_index)
        linked[index_name] = {"path": index_name, "sha256": prepared.digest(staged_index)}
        entry = document.get("images", {}).get(prepared.digest(image))
        if entry is None:
            continue  # The runtime also decodes this exact unlisted source.
        filename = str(entry.get("file", ""))
        if not filename or Path(filename).name != filename or "\\" in filename:
            raise ReleasePreparedError("invalid staged sidecar filename")
        relative = (Path(name).parent / str(entry.get("pool", ".")) / "vram" / filename).as_posix()
        target = prepared.scoped(project.parent, relative)
        actual = prepared.scoped(stage if name.startswith("eloria-assets/") else stage / "app",
            relative if name.startswith("eloria-assets/") else relative.removeprefix("godot-client/"))
        if not prepared.HEX.fullmatch(str(entry.get("sha256", ""))) or prepared.digest(actual) != entry["sha256"]:
            raise ReleasePreparedError("staged sidecar bytes differ: " + relative)
        overlay.link(actual, target)
        linked[relative] = {"path": relative, "sha256": entry["sha256"]}
    return [linked[name] for name in sorted(linked)]


def _validate_variant(path: Path, expected: list[tuple[str, str, str]], quality: str) -> tuple[int, dict]:
    catalog = _json(path)
    if catalog.get("schema_version") != prepared.SCHEMA or catalog.get("policy") != prepared.POLICY:
        raise ReleasePreparedError("cooker returned an unsupported catalog")
    entries = catalog.get("entries")
    if not isinstance(entries, list) or len(entries) != len(expected):
        raise ReleasePreparedError("cooker did not produce the complete source-planned target set")
    expected_set = set(expected)
    actual = [(row.get("kind"), row.get("source"), row.get("node_policy", "retain")) for row in entries]
    if len(set(actual)) != len(actual) or set(actual) != expected_set:
        raise ReleasePreparedError("cooked target/policy membership differs from the source plan")
    masks = {row.get("format_mask") for row in entries}
    if len(masks) != 1:
        raise ReleasePreparedError("one process produced mixed texture-format capability tokens")
    mask = next(iter(masks))
    if type(mask) is not int or mask != 7:
        raise ReleasePreparedError("release cook requires actual observed BC1/BC5/BC7 support")
    if any(row.get("texture_skip") != TEXTURES.index(quality) for row in entries):
        raise ReleasePreparedError("cooker texture quality differs from its exact job")
    attestation = catalog.get("release_cook")
    if not isinstance(attestation, dict) or attestation.get("policy") != "actual-renderer-supported-format-subset-v1" \
            or attestation.get("detected_format_mask") != mask or attestation.get("resource_buffer_probe") is not True \
            or attestation.get("software_adapter") is not True or not attestation.get("adapter_name") \
            or type(attestation.get("adapter_type")) is not int:
        raise ReleasePreparedError("actual renderer/capability/resource-buffer proof is missing")
    return mask, attestation


def _validate_log(path: Path, count: int) -> None:
    text = path.read_text(encoding="utf-8", errors="replace")
    if re.search(r"(?m)^(?:ERROR|SCRIPT ERROR|SHADER ERROR|USER ERROR):", text) \
            or text.count("prepared asset cook: PASS entries=" + str(count)) != 1:
        raise ReleasePreparedError("cooker reported errors or omitted its exact completion marker: " + str(path))


def prepare_generation(project: Path, stage: Path, *, platform: str, godot: Path,
                       run_cook: Callable[[dict], object], check_budget: Callable | None,
                       work_root: Path, rendering_method: str | None = None,
                       timeout_seconds: int = 900) -> dict:
    """Return an external fresh index; caller installs, imports and checks final PCK.

    run_cook receives {argv, environment, log, timeout_seconds, variant}; argv
    includes the engine path. It must wait for/terminate its owned process and
    raise on timeout, nonzero exit or unexpected engine diagnostics. No --headless
    is supplied: the producer requires a real resource-buffer round trip.
    """
    project, stage, work_root = project.resolve(), stage.resolve(), work_root.resolve()
    rendering_method = rendering_method or ("forward_plus" if platform == "windows" else "gl_compatibility")
    if platform not in {"windows", "linux"} or rendering_method not in {"gl_compatibility", "forward_plus"}:
        raise ReleasePreparedError("native Windows/Linux with an explicit supported renderer is required")
    if type(timeout_seconds) is not int or not 30 <= timeout_seconds <= 3600:
        raise ReleasePreparedError("bounded cook timeout must be 30..3600 seconds")
    if project.name != "godot-client" or not (project / "project.godot").is_file() \
            or not (project.parent / ".git").is_file() or not (stage / ".eloria-package").is_file() \
            or not (project / ".godot/imported").is_dir() or not (stage / "app/RabbitLands.pck").is_file():
        raise ReleasePreparedError("complete disposable source, retained imports and first export required")
    if work_root.exists() or work_root.is_relative_to(project) or work_root.is_relative_to(stage) \
            or project.is_relative_to(work_root) or stage.is_relative_to(work_root):
        raise ReleasePreparedError("fresh owned work directory outside project/stage required")
    generated = project / "prepared-content"
    marker = project / ".prepared-cook-project.json"
    snapshot_marker = project / prepared.RUNTIME_IMPORT_MARKER
    if generated.exists() or marker.exists() or snapshot_marker.exists():
        raise ReleasePreparedError("fresh build has leftover prepared generation or cook marker")
    retained = list(dict.fromkeys([*prepared.pilot(project), ("world", FOUR_GATES)]))
    all_targets = retained
    required = {quality: [(kind, source, "retain") for kind, source in retained]
        + [("world", FOUR_GATES, "lazy-source-v1")] for quality in TEXTURES}
    _check(check_budget, "preflight", 256 * 1024**2)
    work_root.mkdir(parents=True)
    overlay = _Overlay(project.parent, work_root / "input-backups", check_budget)
    receipt = {"schema_version": 1, "policy": POLICY, "platform": platform,
        "status": "incomplete", "fresh_generation": True, "catalog_reused": False,
        "qualification": "pending_final_export_and_rendered_runtime_parity",
        "required_entries": required, "variants": [], "limitations": [
            "selected pilot only; unlisted format tokens, content or policies retain validated raw fallback",
            "cooking/resource identity is not a performance or low-end hardware qualification"]}
    receipt_file = work_root / "prepared-release.json"
    try:
        marker.write_text(json.dumps({"purpose": "disposable-native-cook", "release_policy": POLICY}) + "\n", encoding="utf-8")
        discovered = _discover(project, all_targets)
        receipt["staged_sidecars"] = _overlay_sidecars(project, stage, discovered, overlay)
        # Snapshot only exact selected imports/products; restore their editor
        # source generation before the caller's second import/export.
        for name in discovered:
            if name.endswith(".import") or name.startswith("godot-client/.godot/imported/"):
                overlay.isolate(prepared.scoped(project.parent, name))
        receipt["runtime_import_snapshot"] = prepared.snapshot_runtime_imports(project, stage, all_targets)
        catalogs = []
        observed = None
        for quality in TEXTURES:
            for policy in ("retain", "lazy-source-v1"):
                variant = quality + "-" + policy
                targets = retained if policy == "retain" else [("world", FOUR_GATES)]
                job = work_root / "jobs" / (variant + ".json")
                user_root = work_root / "users" / variant
                prepared.write_job(project, quality, "res://prepared-content/" + variant,
                    targets, job, user_root, node_policy=policy, platform=platform)
                document = _json(job)
                document["require_rendered_resource_buffers"] = True
                document["require_software_renderer"] = True
                job.write_text(json.dumps(document, indent=2) + "\n", encoding="utf-8")
                log = work_root / "logs" / (variant + ".log")
                log.parent.mkdir(exist_ok=True)
                _check(check_budget, "before " + variant, 256 * 1024**2)
                run_cook({"argv": [str(godot), "--path", str(project), "--rendering-method", rendering_method,
                    "--script", "res://tools/cook_prepared_assets.gd", "--", str(job)],
                    "environment": {**document["required_environment"],
                        "RABBITLANDS_OPTIMIZATION_PROFILE": "legacy", "RABBITLANDS_CLIENT_RUNTIME": "legacy",
                        "RABBITLANDS_REMOTE_PRESENTATION": "legacy", "RABBITLANDS_RUST_EFFECTS": "legacy",
                        "RABBITLANDS_RESOURCE_ADMISSION": "legacy", "RABBITLANDS_PREPARED_CONTENT": "raw",
                        "RABBITLANDS_PREPARED_NODE_POLICY": "retain", "ELORIA_NATIVE_PRESENTATION": "0",
                        "ELORIA_NATIVE_CROWD": "0", "ELORIA_VRAM_TEXTURES": "", "ELORIA_LOOK": "0"},
                    "log": log, "timeout_seconds": timeout_seconds, "variant": variant})
                catalog = generated / variant / "variant-catalog.json"
                subset = [(kind, source, policy if kind == "world" else "retain") for kind, source in targets]
                _validate_log(log, len(subset))
                mask, attestation = _validate_variant(catalog, subset, quality)
                if attestation.get("platform") != platform or attestation.get("rendering_method") != rendering_method:
                    raise ReleasePreparedError("cooker actual native platform/renderer differs from requested release")
                if observed is not None and mask != observed:
                    raise ReleasePreparedError("renderer capability token changed between serial variant processes")
                observed = mask
                catalogs.append(catalog)
                receipt["variants"].append({"variant": variant, "entries": len(subset),
                    "format_mask": mask, "catalog_sha256": prepared.digest(catalog), "renderer": attestation,
                    "log": str(log), "job_sha256": prepared.digest(job)})
                _check(check_budget, "after " + variant)
        result = prepared.merge_catalogs(project, catalogs, generated / "index.json")
        expected_count = sum(len(rows) for rows in required.values())
        if result["entries"] != expected_count:
            raise ReleasePreparedError("merged generation lost or duplicated a planned exact entry")
        destination = work_root / "generation" / "prepared-content"
        destination.parent.mkdir()
        generated.rename(destination)  # No copy of the large generated payload tree.
        receipt.update(result, status="cooked_pending_final_export", catalog=str(destination / "index.json"),
            observed_format_mask=observed, source_planned_entries=expected_count)
        return receipt
    except BaseException as error:
        receipt["error"] = type(error).__name__ + ": " + str(error)
        raise
    finally:
        try:
            overlay.restore()
            snapshot_marker.unlink(missing_ok=True)
            marker.unlink(missing_ok=True)
            receipt["selected_source_inputs_restored"] = True
        finally:
            receipt_file.write_text(json.dumps(receipt, indent=2, sort_keys=True) + "\n", encoding="utf-8")
