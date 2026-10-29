"""Plan scoped map geometry preparation, or run the runtime preparer in isolation.

Planning reads exact runtime source closures; it never imports, encodes, or writes
beside source assets. Build uses an existing Godot editor/runtime and imports.
The runtime, not file existence or this plan, validates reusable cache entries.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import signal
import subprocess
import sys
import time
from road_ground_dependencies import dependencies as road_dependencies, RoadGroundDependencyError

SCHEMA = 1
SCOPE = "data/maps/geometry-cache-scope.json"
REGISTRY = "data/maps/registry.json"
PREPARER = "res://src/world/map_geometry_prepare.gd"
MAX_GLB_JSON = 64 * 1024 * 1024
ERROR_PATTERN = re.compile(r"SCRIPT ERROR|Parse Error|ERROR:|Failed to load|Error loading", re.I)
DEFAULT_TIMEOUT_SECONDS = 2 * 60 * 60


class PlanError(ValueError):
    pass


def read_json(path: Path) -> dict:
    try:
        value = json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, ValueError) as exc:
        raise PlanError(f"Cannot read JSON: {path}: {exc}") from exc
    if not isinstance(value, dict):
        raise PlanError(f"Expected a JSON object: {path}")
    return value


def project_path(project: Path) -> Path:
    project = project.resolve()
    if not (project / "project.godot").is_file():
        raise PlanError(f"No project.godot in {project}; pass the Godot project directory")
    return project


def _portable(value: str, label: str, *, parent: bool = True) -> PurePosixPath:
    if not isinstance(value, str) or not value or "\\" in value or ":" in value or "\0" in value:
        raise PlanError(f"Nonportable {label}: {value!r}")
    path = PurePosixPath(value)
    if path.is_absolute() or (not parent and ".." in path.parts):
        raise PlanError(f"Path traversal in {label}: {value}")
    return path


def allowed_path(project: Path, path: Path) -> Path:
    path = path.resolve()
    if not any(path.is_relative_to(base) for base in (project, (project.parent / "eloria-assets").resolve())):
        raise PlanError(f"Runtime source escaped the project asset scope: {path}")
    if not path.is_file():
        raise PlanError(f"Runtime source is missing: {path}")
    return path


def source_path(project: Path, source: str) -> Path:
    if not isinstance(source, str) or not source.startswith("res://"):
        raise PlanError(f"Expected a portable res:// source: {source!r}")
    return allowed_path(project, project / _portable(source[6:], "source"))


def relative_source(project: Path, parent: Path, value: str, *, chunk: bool = False) -> Path:
    return allowed_path(project, parent / _portable(value, "chunk" if chunk else "dependency", parent=not chunk))


def logical(project: Path, path: Path) -> str:
    path = path.resolve()
    if path.is_relative_to(project):
        return "res://" + path.relative_to(project).as_posix()
    assets = (project.parent / "eloria-assets").resolve()
    if path.is_relative_to(assets):
        return "res://../eloria-assets/" + path.relative_to(assets).as_posix()
    raise PlanError(f"Cannot express runtime source: {path}")


def resolve_alias(maps: dict, identity: str) -> str:
    seen = set()
    while True:
        if not isinstance(identity, str) or identity not in maps:
            raise PlanError(f"Dangling map ID or alias: {identity!r}")
        if identity in seen:
            raise PlanError(f"Map alias cycle: {identity}")
        seen.add(identity)
        row = maps[identity]
        if not isinstance(row, dict):
            raise PlanError(f"Invalid registry row: {identity}")
        if "alias" not in row:
            if not isinstance(row.get("manifest"), str):
                raise PlanError(f"Map has no manifest: {identity}")
            return identity
        identity = row["alias"]


def glb_json(path: Path) -> dict:
    import struct
    try:
        with path.open("rb") as stream:
            header = stream.read(20)
            if len(header) != 20:
                raise ValueError("short header")
            magic, version, total, size, kind = struct.unpack("<5I", header)
            if magic != 0x46546C67 or version != 2 or kind != 0x4E4F534A \
                    or total != path.stat().st_size or size > MAX_GLB_JSON or size > total - 20:
                raise ValueError("invalid GLB JSON header")
            document = json.loads(stream.read(size))
            if not isinstance(document, dict):
                raise ValueError("JSON chunk is not an object")
            return document
    except (OSError, ValueError) as exc:
        raise PlanError(f"Cannot inspect GLB {path}: {exc}") from exc


class Closure:
    def __init__(self, project: Path):
        self.project = project
        self.files: dict[str, dict] = {}
        self.prototypes: set[str] = set()
        self.images: set[str] = set()
        self.embedded_images = 0
        self._gltf_seen: set[str] = set()
        self._sources: dict[Path, str] = {}
        self._prototype_indexes: dict[Path, dict] = {}
        self._dependencies: dict[Path, Path] = {}

    def dependency(self, parent: Path, value: str) -> Path:
        # The same pooled image is named by hundreds of chunks. Resolve and
        # validate each physical path once per readonly planning pass.
        path = Path(os.path.normpath(str(parent / _portable(value, "dependency"))))
        if path not in self._dependencies:
            self._dependencies[path] = allowed_path(self.project, path)
        return self._dependencies[path]

    def add(self, path: Path, kind: str, expected: str | None = None) -> str:
        source = self._sources.get(path)
        if source is None:
            path = allowed_path(self.project, path)
            source = logical(self.project, path)
            self._sources[path] = source
        if source not in self.files:
            with path.open("rb") as stream:
                digest = hashlib.file_digest(stream, "sha256").hexdigest()
            self.files[source] = {"source": source, "bytes": path.stat().st_size,
                                  "sha256": digest, "kinds": []}
        record = self.files[source]
        if expected is not None and record["sha256"] != expected:
            raise PlanError(f"Declared content digest differs: {source}")
        if kind not in record["kinds"]:
            record["kinds"].append(kind)
        if kind == "image":
            self.images.add(record["sha256"])
        return source

    def gltf(self, path: Path, kind: str, expected: str | None = None) -> None:
        source = self.add(path, kind, expected)
        if source in self._gltf_seen:
            return
        self._gltf_seen.add(source)
        document = glb_json(path)
        for image in document.get("images", []):
            if not isinstance(image, dict):
                raise PlanError(f"Invalid GLB image descriptor: {source}")
            if "uri" in image and not str(image["uri"]).startswith("data:"):
                self.add(self.dependency(path.parent, image["uri"]), "image")
            elif "bufferView" in image or str(image.get("uri", "")).startswith("data:"):
                self.embedded_images += 1
            else:
                raise PlanError(f"Unsupported GLB image descriptor: {source}")

    def world(self, path: Path, manifest: dict) -> None:
        self.add(path, "world_manifest")
        try:
            for dependency, digest in road_dependencies(self.project.parent, path, manifest.get("roadGround")).items():
                self.add(dependency, "road_ground", digest)
        except RoadGroundDependencyError as exc:
            raise PlanError(str(exc)) from exc
        glb = self.dependency(path.parent, manifest.get("asset", {}).get("glb", ""))
        self.gltf(glb, "geometry")
        for field, kind in (("externalResources", "image"), ("externalMeshes", "prototype")):
            table = manifest.get(field, {})
            if not isinstance(table, dict):
                raise PlanError(f"{field} must be an object: {path}")
            for uri, digest in table.items():
                dep = self.dependency(glb.parent, uri)
                if kind == "image":
                    self.add(dep, kind, digest)
                    continue
                prototype = self.add(dep, kind, digest)
                if prototype in self.prototypes:
                    continue
                self.prototypes.add(prototype)
                self.gltf(dep, kind, digest)
                index_path = dep.parent / "index.json"
                self.add(index_path, "prototype_index")
                if index_path not in self._prototype_indexes:
                    self._prototype_indexes[index_path] = read_json(index_path)
                index = self._prototype_indexes[index_path].get("prototypes", {}).get(dep.stem)
                if not isinstance(index, dict):
                    raise PlanError(f"Prototype index entry is missing: {dep}")
                for image_uri, image_digest in index.get("images", {}).items():
                    self.add(self.dependency(dep.parent, image_uri), "image", image_digest)
        # Only portable runtime biome inputs, never source/provenance records.
        config = manifest.get("biomeBlend")
        if isinstance(config, dict):
            for mask in (config.get("baseMask"), config.get("secondaryMask")):
                if isinstance(mask, dict) and mask.get("path"):
                    self.add(source_path(self.project, mask["path"]), "blend_texture", mask.get("sha256"))
            for palette in config.get("palettes", []):
                for role in ("base", "secondary"):
                    record = palette.get(role)
                    if not isinstance(record, dict):
                        continue
                    for slot in ("albedoTexture", "normalTexture", "ormTexture"):
                        if record.get(slot):
                            expected = record.get("textureSha256", {}).get(slot)
                            self.add(source_path(self.project, record[slot]), "blend_texture", expected)


def plan(project: Path, *, scope_path: Path | None = None, include_assets: bool = True) -> dict:
    project = project_path(project)
    scope_file = scope_path.resolve() if scope_path is not None else project / SCOPE
    scope = read_json(scope_file)
    if scope.get("schema") != SCHEMA or not isinstance(scope.get("maps"), list):
        raise PlanError(f"Unsupported geometry scope: {scope_file}")
    registry = read_json(project / REGISTRY).get("maps")
    if not isinstance(registry, dict):
        raise PlanError("Map registry has no maps object")
    # Validate every alias, including dangling tier aliases not explicitly selected.
    for identity in registry:
        resolve_alias(registry, identity)
    roots = list(dict.fromkeys(resolve_alias(registry, identity) for identity in scope["maps"]))
    closure = Closure(project)
    targets = []
    used_sources, used_ids = set(), set()
    root_rows = []

    def target(kind: str, identity: str, path: Path, owner: str) -> None:
        source = logical(project, path)
        if source in used_sources:
            raise PlanError(f"Duplicate scene leaf/source: {source}")
        if not isinstance(identity, str) or not identity or identity in used_ids:
            raise PlanError(f"Duplicate or missing target ID: {identity!r}")
        used_sources.add(source)
        used_ids.add(identity)
        targets.append({"kind": kind, "source": source, "id": identity, "owner": owner})

    for identity in roots:
        root_path = source_path(project, registry[identity]["manifest"])
        manifest = read_json(root_path)
        chunks = manifest.get("streamingChunks")
        if chunks is None:
            leaves = [(root_path, manifest)]
        else:
            if not isinstance(chunks, dict) or not isinstance(chunks.get("chunks"), list) or not chunks["chunks"]:
                raise PlanError(f"Invalid streaming chunk list: {identity}")
            closure.add(root_path, "streaming_manifest")
            leaves = []
            for chunk in chunks["chunks"]:
                if not isinstance(chunk, dict):
                    raise PlanError(f"Invalid streaming chunk: {identity}")
                leaf = relative_source(project, root_path.parent, chunk.get("manifest", ""), chunk=True)
                child = read_json(leaf)
                if "streamingChunks" in child:
                    raise PlanError(f"Nested streaming manifest is not a scene leaf: {leaf}")
                leaves.append((leaf, child))
        for leaf, child in leaves:
            target("world", child.get("asset", {}).get("id"), leaf, identity)
            closure.world(leaf, child)
        root_rows.append({"id": identity, "source": logical(project, root_path),
                          "scene_leaves": len(leaves),
                          "aliases": [key for key in registry if key != identity and resolve_alias(registry, key) == identity]})

    if include_assets:
        for overlay in scope.get("asset_overlays", []):
            if not isinstance(overlay, dict) or overlay.get("owner") not in roots:
                raise PlanError("Asset overlay has no selected canonical map owner")
            owner = overlay["owner"]
            config_path = source_path(project, overlay.get("config"))
            closure.add(config_path, "overlay_config")
            config = read_json(config_path)
            if config.get("map") != owner or not isinstance(config.get("assets"), dict) \
                    or not isinstance(config.get("placements"), list):
                raise PlanError(f"Invalid asset overlay: {config_path}")
            used_assets = set()
            for placement in config["placements"]:
                if not isinstance(placement, dict) or not isinstance(placement.get("asset"), str):
                    raise PlanError(f"Invalid asset placement: {config_path}")
                used_assets.add(placement["asset"])
            paths = set()
            for asset in sorted(used_assets):
                if asset not in config["assets"]:
                    raise PlanError(f"Missing overlay asset: {asset}")
                path = source_path(project, config["assets"][asset])
                if path in paths:
                    continue
                paths.add(path)
                target("asset", f"{owner}:{asset}", path, owner)
                closure.gltf(path, "overlay_asset")

    files = [dict(row, kinds=sorted(row["kinds"])) for _, row in sorted(closure.files.items())]
    fingerprint = hashlib.sha256(json.dumps(files, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
    return {"schema": SCHEMA, "scope_version": scope.get("version"), "project": str(project),
            "scope": str(scope_file), "roots": root_rows, "targets": targets,
            "source_closure": files, "source_closure_sha256": fingerprint,
            "summary": {"canonical_maps": len(roots),
                        "world_targets": sum(row["kind"] == "world" for row in targets),
                        "asset_targets": sum(row["kind"] == "asset" for row in targets),
                        "shared_prototypes": len(closure.prototypes),
                        "unique_external_image_contents": len(closure.images),
                        "embedded_image_references": closure.embedded_images,
                        "source_files": len(files), "source_bytes": sum(row["bytes"] for row in files)}}


def _write_json(path: Path, value: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def _ignored_output(path: Path) -> None:
    """Generated profiles/logs must not become source files in a Git checkout."""
    path.mkdir(parents=True, exist_ok=True)
    git = subprocess.run(["git", "-C", str(path), "rev-parse", "--show-toplevel"], capture_output=True, text=True)
    if git.returncode == 0:
        ignored = subprocess.run(["git", "-C", str(path), "check-ignore", "-q", "--", str(path / "geometry-job.json")])
        if ignored.returncode != 0:
            raise PlanError(f"Generated output directory is not Git-ignored: {path}")


def _job_targets(project: Path, document: dict, include_assets: bool) -> list[dict]:
    if document.get("schema") != SCHEMA or not isinstance(document.get("targets"), list):
        raise PlanError("Preparation plan must contain schema 1 and a targets array")
    targets, ids, sources = [], set(), set()
    for row in document["targets"]:
        if not isinstance(row, dict) or row.get("kind") not in ("world", "asset"):
            raise PlanError("Preparation plan has an invalid target kind")
        if not include_assets and row["kind"] == "asset":
            continue
        identity, source = row.get("id"), row.get("source")
        path = source_path(project, source)
        if path.suffix.lower() != (".json" if row["kind"] == "world" else ".glb"):
            raise PlanError(f"Preparation target has the wrong file type: {source}")
        source = logical(project, path)
        if not isinstance(identity, str) or not identity or identity in ids or source in sources:
            raise PlanError(f"Duplicate or invalid preparation target: {identity!r}")
        ids.add(identity)
        sources.add(source)
        targets.append({"kind": row["kind"], "source": source, "id": identity})
    if not targets:
        raise PlanError("Preparation plan contains no selected targets")
    return targets


def _stop_child(process: subprocess.Popen) -> None:
    """Stop only the engine process this invocation created."""
    if process.poll() is not None:
        return
    try:
        if os.name == "nt":
            process.terminate()
        else:
            os.killpg(process.pid, signal.SIGTERM)
        process.wait(timeout=5)
    except subprocess.TimeoutExpired:
        if os.name == "nt":
            process.kill()
        else:
            os.killpg(process.pid, signal.SIGKILL)
        process.wait(timeout=5)
    except ProcessLookupError:
        pass  # It finished between poll and terminate.


def _run_engine(command: list[str], env: dict, stdout_path: Path, stderr_path: Path,
                timeout_seconds: float, *, check_progress=None) -> int:
    offsets = {stdout_path: 0, stderr_path: 0}
    tails = {stdout_path: "", stderr_path: ""}

    def first_error() -> str | None:
        for path in offsets:
            with path.open("rb") as stream:
                stream.seek(offsets[path])
                text = tails[path] + stream.read().decode("utf-8", errors="replace")
                offsets[path] = stream.tell()
            # Keep a short boundary tail for errors split across two writes.
            tails[path] = text[-256:]
            match = ERROR_PATTERN.search(text)
            if match:
                return text[match.start():].splitlines()[0][:400]
        return None

    options = {"creationflags": subprocess.CREATE_NO_WINDOW} if os.name == "nt" else {}
    with stdout_path.open("w", encoding="utf-8") as stdout, stderr_path.open("w", encoding="utf-8") as stderr:
        process = subprocess.Popen(command, env=env, stdout=stdout, stderr=stderr,
                                   start_new_session=os.name != "nt", **options)
        deadline = time.monotonic() + timeout_seconds
        next_check = time.monotonic()
        try:
            while True:
                if check_progress is not None and time.monotonic() >= next_check:
                    check_progress()
                    next_check = time.monotonic() + 5
                error = first_error()
                if error:
                    _stop_child(process)
                    raise PlanError(f"Geometry preparation stopped on engine error: {error}. "
                                    f"Logs: {stdout_path}, {stderr_path}")
                code = process.poll()
                if code is not None:
                    # A process can finish after the read above and before poll.
                    error = first_error()
                    if error:
                        raise PlanError(f"Geometry preparation reported an engine error: {error}. "
                                        f"Logs: {stdout_path}, {stderr_path}")
                    return code
                if time.monotonic() >= deadline:
                    _stop_child(process)
                    raise PlanError(f"Geometry preparation exceeded {timeout_seconds:g} seconds. "
                                    f"Logs: {stdout_path}, {stderr_path}")
                time.sleep(0.5)
        except BaseException:
            _stop_child(process)
            raise


def build(project: Path, godot: Path, *, user_root: Path | None = None, plan_path: Path | None = None,
          resume: bool = False, include_assets: bool = True, rendering_method: str = "forward_plus",
          timeout_seconds: float = DEFAULT_TIMEOUT_SECONDS, release_preparation: bool = False,
          run_engine=None) -> dict:
    project = project_path(project)
    godot = godot.resolve()
    if not godot.is_file():
        raise PlanError(f"Godot executable is missing: {godot}")
    if rendering_method not in ("forward_plus", "gl_compatibility"):
        raise PlanError("Use forward_plus or gl_compatibility for rendered geometry preparation")
    if not 0 < timeout_seconds < float("inf"):
        raise PlanError("Preparation timeout must be a finite positive number of seconds")
    if not source_path(project, PREPARER).is_file():
        raise PlanError("The runtime map geometry preparer is not installed")
    document = read_json(plan_path) if plan_path is not None else plan(project, include_assets=include_assets)
    targets = _job_targets(project, document, include_assets)
    user_root = (user_root or project / "test-artifacts/map-geometry-prepare").resolve()
    _ignored_output(user_root)
    run = user_root / "jobs" / f"{time.strftime('%Y%m%d-%H%M%S')}-{os.getpid()}-{time.time_ns()}"
    run.mkdir(parents=True)
    report_path = run / "report.json"
    job_path = run / "job.json"
    _write_json(job_path, {"schema": SCHEMA, "targets": targets, "resume": resume,
                           "release_preparation": release_preparation,
                           "output_report": str(report_path)})
    env = dict(os.environ, APPDATA=str(user_root), LOCALAPPDATA=str(user_root),
               XDG_DATA_HOME=str(user_root), XDG_CONFIG_HOME=str(user_root),
               ELORIA_GEOMETRY_JOB=str(job_path), RABBITLANDS_PREPARED_CONTENT="raw",
               ELORIA_NO_MAP_CACHE="1", ELORIA_VRAM_TEXTURES="0")
    # Render normally so texture/resource creation has a real renderer, with
    # an offscreen window and no audio. Never start the editor or an import.
    command = [str(godot), "--path", str(project), "--rendering-method", rendering_method,
               "--audio-driver", "Dummy", "--position", "-32000,-32000", "--resolution", "320x180",
               "--script", PREPARER]
    stdout_path, stderr_path = run / "stdout.log", run / "stderr.log"
    returncode = (run_engine or _run_engine)(command, env, stdout_path, stderr_path, timeout_seconds)
    stdout_text = stdout_path.read_text(encoding="utf-8", errors="replace")
    stderr_text = stderr_path.read_text(encoding="utf-8", errors="replace")
    if not report_path.is_file():
        raise PlanError(f"Godot did not produce a preparation report (exit {returncode}). "
                        f"Inspect {stdout_path} and {stderr_path}")
    report = read_json(report_path)
    if returncode != 0 or report.get("ok") is not True or ERROR_PATTERN.search(stdout_text + stderr_text):
        raise PlanError(f"Geometry preparation failed (exit {returncode}, "
                        f"failed entries: {report.get('failed', [])}). Inspect {report_path}, "
                        f"{stdout_path} and {stderr_path}")
    return {"ok": True, "report": str(report_path), "prepared": report.get("prepared", 0),
            "reused": report.get("reused", 0), "targets": len(targets), "user_root": str(user_root),
            "stdout": str(stdout_path), "stderr": str(stderr_path)}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    planner = commands.add_parser("plan", help="Validate the runtime scope and describe its exact source closure")
    planner.add_argument("--project", type=Path, required=True)
    planner.add_argument("--out", "--out-json", "--outJSON", dest="out_json", type=Path)
    planner.add_argument("--no-assets", action="store_true")
    runner = commands.add_parser("build", help="Prepare scoped geometry with existing imported dependencies")
    runner.add_argument("--project", type=Path, required=True)
    runner.add_argument("--godot", type=Path, required=True)
    runner.add_argument("--user-root", type=Path)
    runner.add_argument("--plan", type=Path)
    runner.add_argument("--resume", action="store_true")
    runner.add_argument("--no-assets", action="store_true")
    runner.add_argument("--rendering-method", choices=("forward_plus", "gl_compatibility"), default="forward_plus")
    runner.add_argument("--timeout-seconds", type=float, default=DEFAULT_TIMEOUT_SECONDS)
    args = parser.parse_args(argv)
    try:
        if args.command == "plan":
            result = plan(args.project, include_assets=not args.no_assets)
            if args.out_json:
                _write_json(args.out_json, result)
                print(json.dumps({"plan": str(args.out_json.resolve()), **result["summary"]}, indent=2))
            else:
                print(json.dumps(result, indent=2, ensure_ascii=False))
        else:
            result = build(args.project, args.godot, user_root=args.user_root, plan_path=args.plan,
                           resume=args.resume, include_assets=not args.no_assets,
                           rendering_method=args.rendering_method, timeout_seconds=args.timeout_seconds)
            print(json.dumps(result, indent=2))
        return 0
    except (PlanError, OSError) as exc:
        print(f"map geometry cache: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
