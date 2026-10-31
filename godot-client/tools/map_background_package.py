"""Read-only, standard-library contracts for mandatory prerendered map images.

The renderer and release packager use the same registry, framing and source
closure rules. Runtime images stay independent of map geometry/cache formats.
"""
from __future__ import annotations

import hashlib
import json
import math
from pathlib import Path
import re
import struct

import map_geometry_cache as geometry

CATALOG = "godot-client/data/maps/map-backgrounds.json"
REGISTRY = "godot-client/data/maps/registry.json"
POLICY = "prerendered-map-background-v1"
GENERATOR = "eloria-assets/tools/render_map_backgrounds.py"
RENDERER_REQUIRED_INPUTS = {GENERATOR, "godot-client/tools/map_background_package.py",
                            "godot-client/data/assets/retired_procedural_models.json"}
HASH = re.compile(r"[0-9a-f]{64}\Z")


class BackgroundError(ValueError):
    pass


def read_json(path: Path) -> dict:
    try:
        value = json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, ValueError) as error:
        raise BackgroundError(f"Cannot read {path}: {error}") from error
    if not isinstance(value, dict):
        raise BackgroundError(f"Expected JSON object: {path}")
    return value


def sha256(path: Path) -> str:
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def resource_path(root: Path, resource: str) -> Path:
    if not isinstance(resource, str) or not resource.startswith("res://"):
        raise BackgroundError(f"Expected res:// map background/source path: {resource!r}")
    try:
        return geometry.source_path(root.resolve() / "godot-client", resource)
    except geometry.PlanError as error:
        raise BackgroundError(str(error)) from error


def inventory(root: Path) -> dict:
    root = root.resolve()
    registry = read_json(root / REGISTRY).get("maps")
    if not isinstance(registry, dict) or not registry:
        raise BackgroundError("Map registry must contain maps")
    maps, aliases = {}, {}
    try:
        for identity in registry:
            canonical = geometry.resolve_alias(registry, identity)
            if identity != canonical:
                aliases[identity] = canonical
                continue
            entry = registry[identity]
            manifest = entry["manifest"]
            maps[identity] = {"manifest": manifest, "entry": entry,
                              "document": read_json(resource_path(root, manifest))}
    except geometry.PlanError as error:
        raise BackgroundError(str(error)) from error
    return {"maps": maps, "aliases": aliases}


def _pair(value) -> list[float] | None:
    if not isinstance(value, list) or len(value) != 2 or any(
            isinstance(n, bool) or not isinstance(n, (int, float)) or not math.isfinite(n) for n in value):
        return None
    return [float(n) for n in value]


def _bounds(value) -> tuple[list[float], list[float]] | None:
    if not isinstance(value, dict):
        return None
    low, high = value.get("min"), value.get("max")
    if not isinstance(low, list) or not isinstance(high, list) or len(low) != len(high) or len(low) not in (2, 3):
        return None
    minimum = _pair(low if len(low) == 2 else [low[0], low[2]])
    maximum = _pair(high if len(high) == 2 else [high[0], high[2]])
    if minimum is None or maximum is None or any(a >= b for a, b in zip(minimum, maximum)):
        return None
    return minimum, maximum


def _frame_matches(row: dict, expected: tuple[list[float], list[float]]) -> bool:
    return (_pair(row.get("worldMin")), _pair(row.get("worldMax"))) == expected


def frame_for(manifest: dict, section_id: str = "") -> tuple[list[float], list[float]]:
    """Exact north-up X/Z frame used by MapView, before its display margin."""
    if section_id:
        for section in manifest.get("sections", []):
            if isinstance(section, dict) and section.get("id") == section_id:
                result = _bounds(section.get("bounds"))
                if result:
                    return result
                raise BackgroundError(f"Invalid section bounds: {section_id}")
        raise BackgroundError(f"Unknown section: {section_id}")
    asset = manifest.get("asset", {})
    for name in ("mapBounds", "playableBounds"):
        result = _bounds(asset.get(name))
        if result:
            return result
    result = _bounds(manifest.get("coordinateTransform", {}).get("addressableWorldBounds"))
    if result:
        return result
    result = _bounds(asset.get("bounds"))
    if result:
        return result
    raise BackgroundError("Map has no positive framing bounds")


def source_inputs(root: Path, manifest_path: Path | str) -> dict[str, str]:
    """Hash complete published world/chunk/mesh/texture/road inputs once per map."""
    root = root.resolve()
    project = root / "godot-client"
    path = resource_path(root, manifest_path) if isinstance(manifest_path, str) and manifest_path.startswith("res://") \
        else Path(manifest_path).resolve()
    closure = geometry.Closure(project)
    pending = [path]
    seen = set()
    try:
        while pending:
            path = pending.pop()
            if path in seen:
                continue
            seen.add(path)
            document = read_json(path)
            stream = document.get("streamingChunks")
            if stream is None:
                closure.world(path, document)
            else:
                if not isinstance(stream, dict) or not isinstance(stream.get("chunks"), list) or not stream["chunks"]:
                    raise BackgroundError(f"Invalid streaming chunks: {path}")
                closure.add(path, "streaming_manifest")
                for chunk in stream["chunks"]:
                    pending.append(geometry.relative_source(project, path.parent, chunk.get("manifest", ""), chunk=True))
    except geometry.PlanError as error:
        raise BackgroundError(str(error)) from error
    result = {}
    for source, record in closure.files.items():
        physical = resource_path(root, source)
        result[physical.relative_to(root).as_posix()] = record["sha256"]
    return dict(sorted(result.items()))


def image_size(path: Path) -> tuple[int, int]:
    """Read PNG/WebP dimensions without an image-codec dependency in packaging."""
    with path.open("rb") as stream:
        header = stream.read(32)
        if header.startswith(b"\x89PNG\r\n\x1a\n") and header[12:16] == b"IHDR" and len(header) >= 24:
            return struct.unpack(">II", header[16:24])
        if header[:4] != b"RIFF" or header[8:12] != b"WEBP":
            raise BackgroundError(f"Unsupported map background image: {path}")
        if len(header) < 20 or int.from_bytes(header[4:8], "little") + 8 != path.stat().st_size:
            raise BackgroundError(f"Truncated WebP map background: {path}")
        stream.seek(12)
        while chunk := stream.read(8):
            if len(chunk) != 8:
                break
            size = int.from_bytes(chunk[4:8], "little")
            body = stream.read(min(size, 16))
            if chunk[:4] == b"VP8X" and len(body) >= 10:
                return int.from_bytes(body[4:7], "little") + 1, int.from_bytes(body[7:10], "little") + 1
            if chunk[:4] == b"VP8L" and len(body) >= 5 and body[0] == 0x2F:
                bits = int.from_bytes(body[1:5], "little")
                return (bits & 0x3FFF) + 1, ((bits >> 14) & 0x3FFF) + 1
            if chunk[:4] == b"VP8 " and len(body) >= 10 and body[3:6] == b"\x9d\x01\x2a":
                return int.from_bytes(body[6:8], "little") & 0x3FFF, int.from_bytes(body[8:10], "little") & 0x3FFF
            stream.seek(size - len(body) + size % 2, 1)
    raise BackgroundError(f"Missing WebP dimensions: {path}")


def picture_rows(catalog: dict, identities=None):
    for identity, row in catalog.get("maps", {}).items():
        if identities is not None and identity not in identities:
            continue
        if row.get("path"):
            yield identity, row
        for section, picture in row.get("sections", {}).items():
            yield identity + "/" + section, picture


def _image_errors(root: Path, label: str, row: dict, verify_images: bool) -> list[str]:
    errors = []
    try:
        path = resource_path(root, row.get("path"))
        if not path.is_relative_to(root.resolve() / "eloria-assets/maps"):
            raise BackgroundError("Map background must be a loose eloria-assets/maps image")
        if not HASH.fullmatch(str(row.get("sha256", ""))):
            raise BackgroundError("Image has no valid SHA-256")
        dimensions = row.get("imageSize")
        if not isinstance(dimensions, list) or len(dimensions) != 2 or any(
                isinstance(n, bool) or not isinstance(n, int) or not 1 <= n <= 16384 for n in dimensions):
            raise BackgroundError("Image has invalid dimensions")
        if verify_images:
            if sha256(path) != row["sha256"]:
                raise BackgroundError("Image bytes differ from the catalog")
            if image_size(path) != tuple(dimensions):
                raise BackgroundError("Image dimensions differ from the catalog")
    except (BackgroundError, OSError) as error:
        errors.append(f"{label}: {error}")
    return errors


def validate_catalog(root: Path, catalog=None, verify_sources=True, verify_images=True) -> list[str]:
    root = root.resolve()
    try:
        catalog = read_json(root / CATALOG) if catalog is None else catalog
        expected = inventory(root)
        if not isinstance(catalog, dict) or catalog.get("schemaVersion") != 1 or not isinstance(catalog.get("maps"), dict):
            raise BackgroundError("Unsupported map-background catalog")
    except (BackgroundError, OSError) as error:
        return [str(error)]
    errors = []
    if set(catalog["maps"]) != set(expected["maps"]):
        errors.append("Map background coverage differs from canonical registry maps")
    if catalog.get("aliases") != expected["aliases"]:
        errors.append("Map background aliases differ from the registry")
    renderer_inputs = catalog.get("rendererInputs")
    if catalog.get("generator") != GENERATOR:
        errors.append("Map background generator differs")
    if not isinstance(renderer_inputs, dict) or not RENDERER_REQUIRED_INPUTS.issubset(renderer_inputs):
        errors.append("Map background rendererInputs must include the generator, contract and retirement policy")
    elif verify_sources:
        errors.extend(_input_errors(root, renderer_inputs, "renderer"))
    for identity, definition in expected["maps"].items():
        row = catalog["maps"].get(identity)
        if not isinstance(row, dict):
            errors.append(f"{identity}: Missing background")
            continue
        manifest = definition["document"]
        sectioned = bool(manifest.get("secret") or manifest.get("sectioned"))
        sections = {s["id"] for s in manifest.get("sections", []) if isinstance(s, dict) and s.get("id")} if sectioned else set()
        try:
            if row.get("rendererPolicy") != POLICY:
                raise BackgroundError("Background renderer policy differs")
            if not _frame_matches(row, frame_for(manifest)):
                raise BackgroundError("Background frame differs from MapView")
            if sectioned and (row.get("sectioned") is not True or row.get("path") or not sections):
                raise BackgroundError("Sectioned maps require section images without an aggregate image")
            declared = row.get("sections", {})
            if not isinstance(declared, dict) or set(declared) != sections:
                raise BackgroundError("Background section coverage differs from the manifest")
            if not sectioned:
                errors.extend(_image_errors(root, identity, row, verify_images))
            for section_id in sections:
                picture = declared[section_id]
                if not isinstance(picture, dict) or not _frame_matches(picture, frame_for(manifest, section_id)):
                    raise BackgroundError(f"Section frame differs: {section_id}")
                errors.extend(_image_errors(root, identity + "/" + section_id, picture, verify_images))
            inputs = row.get("sourceInputs")
            if not isinstance(inputs, dict) or not inputs:
                raise BackgroundError("Missing sourceInputs")
            if verify_sources and inputs != source_inputs(root, definition["manifest"]):
                raise BackgroundError("Background source closure is stale")
        except (BackgroundError, OSError, KeyError, TypeError) as error:
            errors.append(f"{identity}: {error}")
    return errors


def _input_errors(root: Path, inputs: dict, label: str) -> list[str]:
    errors = []
    for name, digest in inputs.items():
        path = (root / name).resolve()
        if not path.is_relative_to(root) or not path.is_file() or not isinstance(digest, str) or not HASH.fullmatch(digest):
            errors.append(f"{label}: invalid input {name}")
        elif sha256(path) != digest:
            errors.append(f"{label}: stale input {name}")
    return errors


def staged_image_errors(root: Path, stage: Path) -> list[str]:
    """Verify the actual loose image bytes selected for this shipped registry."""
    catalog = read_json(root / CATALOG)
    selected = set(inventory(root)["maps"])
    errors = []
    for label, row in picture_rows(catalog, selected):
        try:
            source = resource_path(root, row["path"])
            relative = source.relative_to(root.resolve())
            destination = (stage / relative).resolve()
            if not destination.is_relative_to(stage.resolve()) or not destination.is_file():
                raise BackgroundError(f"Background is missing from staged files: {relative}")
            if sha256(destination) != row["sha256"]:
                raise BackgroundError(f"Staged background differs: {relative}")
        except (BackgroundError, OSError, KeyError) as error:
            errors.append(f"{label}: {error}")
    return errors
