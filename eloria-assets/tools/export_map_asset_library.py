"""Extract complete reusable map objects from the current continent packages.

The source manifest names exact placement roots.  Each output keeps the source
hierarchy, meshes, materials, and textures, but moves the aggregate XZ centre to
the origin and its lowest rendered vertex to Y=0.  No source geometry is edited.
"""
from __future__ import annotations

import argparse
import copy
import hashlib
import json
import math
import mimetypes
import re
import sys
from pathlib import Path

import numpy as np


REPO = Path(__file__).resolve().parents[2]
MAPS = REPO / "eloria-assets/maps"
CONTINENT = MAPS / "nymara-regions/_continent"
TOOLKIT = MAPS / "nymara-regions/_toolkit"
GODOT = REPO / "godot-client"
DEFAULT_MANIFEST = CONTINENT / "map-asset-library.json"
DEFAULT_OUTPUT = GODOT / "assets/world/continent"
DEFAULT_CATALOG = GODOT / "data/world/map_asset_extras.json"
CATEGORIES = {"Continent props", "Continent structures", "Continent landmarks"}
ID_PATTERN = re.compile(r"^continent:[a-z0-9]+(?:-[a-z0-9]+)*$")
SLUG_PATTERN = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
FORBIDDEN_ROOT_PREFIXES = ("Terrain_", "Collision_", "StreamView_", "Backdrop_", "Walk_")

for path in (CONTINENT, TOOLKIT):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

import object_edits as OE
import scene_io as S


def _read_json(path: Path) -> dict:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"{path} must contain a JSON object")
    return value


def _report_path(path: Path) -> str:
    try:
        return path.relative_to(REPO).as_posix()
    except ValueError:
        return path.as_posix()


def _package(region: str) -> Path:
    return MAPS / ("four-gates" if region == "four_gates" else f"nymara-regions/{region}")


def _allowed_sources() -> dict[Path, str]:
    master = _read_json(CONTINENT / "generated/master-scene.json")
    return {(_package(region) / "world.glb").resolve(): region for region in master["regions"]}


def _parents(document: dict) -> dict[int, int]:
    result = {}
    for parent, node in enumerate(document["nodes"]):
        for child in node.get("children", []):
            if child in result:
                raise ValueError(f"node {child} has more than one parent")
            result[child] = parent
    return result


def _validate_asset(spec: dict, seen_ids: set[str], allowed: dict[Path, str]) -> tuple[Path, str]:
    required = {"id", "label", "category", "source", "roots", "height", "tags"}
    missing = required - spec.keys()
    if missing:
        raise ValueError(f"asset is missing {sorted(missing)}: {spec}")
    asset_id = str(spec["id"])
    if not ID_PATTERN.fullmatch(asset_id) or asset_id in seen_ids:
        raise ValueError(f"invalid or duplicate asset id: {asset_id}")
    seen_ids.add(asset_id)
    slug = asset_id.removeprefix("continent:")
    if not SLUG_PATTERN.fullmatch(slug):
        raise ValueError(f"invalid output slug: {slug}")
    if spec["category"] not in CATEGORIES:
        raise ValueError(f"unsupported category for {asset_id}: {spec['category']}")
    if not isinstance(spec["roots"], list) or not spec["roots"] or \
            len(set(spec["roots"])) != len(spec["roots"]):
        raise ValueError(f"{asset_id} needs unique exact roots")
    if not isinstance(spec["tags"], list) or not all(isinstance(tag, str) and tag for tag in spec["tags"]):
        raise ValueError(f"{asset_id} tags must be non-empty strings")
    height = float(spec["height"])
    if not math.isfinite(height) or height < 0:
        raise ValueError(f"{asset_id} height must be finite and non-negative")
    source = (MAPS / str(spec["source"])).resolve()
    if source not in allowed:
        raise ValueError(f"{asset_id} source is not a current master-scene package: {source}")
    return source, slug


def _select_roots(asset_id: str, document: dict, names: list[str]) -> list[int]:
    occurrences: dict[str, list[int]] = {}
    for index, node in enumerate(document["nodes"]):
        occurrences.setdefault(str(node.get("name", "")), []).append(index)
    indices = []
    for name in names:
        matches = occurrences.get(name, [])
        if len(matches) != 1:
            raise ValueError(f"{asset_id} root {name!r} has {len(matches)} matches")
        if name.startswith(FORBIDDEN_ROOT_PREFIXES):
            raise ValueError(f"{asset_id} selects a non-object root: {name}")
        indices.append(matches[0])
    selected = set(indices)
    for root in indices:
        descendants = S.descendants(document, [root]) - {root}
        if selected & descendants:
            raise ValueError(f"{asset_id} selects both a root and its descendant")
    parents = _parents(document)
    scene_roots = set(document["scenes"][document.get("scene", 0)].get("nodes", []))
    for root in indices:
        parent = parents.get(root)
        parent_name = "" if parent is None else str(document["nodes"][parent].get("name", ""))
        if root not in scene_roots and not parent_name.endswith("_WorldPlacement"):
            raise ValueError(f"{asset_id} root is a fragment under {parent_name!r}: {names[indices.index(root)]}")
    return indices


def _reachable_images(document: dict, roots: list[int]) -> set[int]:
    textures = set()

    def collect(value):
        if isinstance(value, dict):
            for key, item in value.items():
                if key.endswith("Texture") and isinstance(item, dict) and "index" in item:
                    textures.add(int(item["index"]))
                else:
                    collect(item)
        elif isinstance(value, list):
            for item in value:
                collect(item)

    for node_index in S.descendants(document, roots):
        mesh_index = document["nodes"][node_index].get("mesh")
        if mesh_index is None:
            continue
        for primitive in document["meshes"][mesh_index]["primitives"]:
            material_index = primitive.get("material")
            if material_index is not None:
                collect(document["materials"][material_index])
    return {int(document["textures"][index]["source"]) for index in textures
            if "source" in document["textures"][index]}


def _embed_external_images(document: dict, body: bytes, source_dir: Path,
                           needed_images: set[int]) -> tuple[dict, bytes]:
    """Make certified package image URIs usable by the existing subtree exporter."""
    document = copy.deepcopy(document)
    packed = bytearray(body)
    for image_index, image in enumerate(document.get("images", [])):
        if image_index not in needed_images:
            continue
        uri = image.get("uri")
        if not uri:
            continue
        if str(uri).startswith(("data:", "http:", "https:")):
            raise ValueError(f"unsupported map asset image URI: {uri}")
        source = (source_dir / str(uri)).resolve()
        try:
            source.relative_to(REPO.resolve())
        except ValueError as error:
            raise ValueError(f"map asset texture is outside the repository: {source}") from error
        if not source.is_file():
            raise ValueError(f"map asset texture is missing: {source}")
        packed.extend(bytes((-len(packed)) % 4))
        data = source.read_bytes()
        view = {"buffer": 0, "byteOffset": len(packed), "byteLength": len(data)}
        document.setdefault("bufferViews", []).append(view)
        packed.extend(data)
        image.pop("uri", None)
        image["bufferView"] = len(document["bufferViews"]) - 1
        mime = mimetypes.guess_type(source.name)[0]
        if mime not in ("image/png", "image/jpeg"):
            raise ValueError(f"unsupported map asset texture type: {source}")
        image["mimeType"] = mime
    if document.get("buffers"):
        document["buffers"] = [dict(document["buffers"][0], byteLength=len(packed))]
    return document, bytes(packed)


def _extract_one(spec: dict, source: Path, slug: str, output: Path, shared_images: Path) -> dict:
    document, body = S.GR.load(source)
    roots = _select_roots(str(spec["id"]), document, [str(name) for name in spec["roots"]])
    matrices, _ = S.GR.hierarchy(document)
    low, high = OE.subtree_bounds_all(S, document, body, roots)
    size = high - low
    if not np.isfinite(low).all() or not np.isfinite(high).all() or np.any(size <= 0.001):
        raise ValueError(f"{spec['id']} has invalid rendered bounds: {low} {high}")
    if max(float(size[0]), float(size[2])) > 80.0 or float(size[1]) > 80.0:
        raise ValueError(f"{spec['id']} is too large for an individual map asset: {size}")

    private, body = _embed_external_images(
        document, body, source.parent, _reachable_images(document, roots))
    for root in roots:
        OE.set_matrix(private["nodes"][root], matrices[root])
    target = output / f"{slug}.glb"
    exporter = S.Exporter(target, shared_images=shared_images)
    exporter.add(private, body, roots)
    centre = (low + high) * 0.5
    shift = [-float(centre[0]), -float(low[1]), -float(centre[2])]
    for wrapper in exporter.doc["scenes"][0]["nodes"]:
        exporter.doc["nodes"][wrapper]["translation"] = shift
    exporter.doc["asset"]["generator"] = "Eloria map asset library extractor"
    exporter.doc["asset"]["extras"] = {
        "source": str(spec["source"]),
        "roots": list(spec["roots"]),
    }
    summary = exporter.write()
    summary.update({
        "id": spec["id"],
        "output": _report_path(target),
        "source": _report_path(source),
        "roots": list(spec["roots"]),
        "bounds": {"size": [round(float(value), 6) for value in size]},
        "sha256": hashlib.sha256(target.read_bytes()).hexdigest(),
    })
    return summary


def export_library(manifest_path: Path = DEFAULT_MANIFEST, output: Path = DEFAULT_OUTPUT,
                   catalog_path: Path = DEFAULT_CATALOG) -> dict:
    manifest = _read_json(manifest_path)
    if manifest.get("version") != 1 or not isinstance(manifest.get("assets"), list):
        raise ValueError("map asset source manifest must have version 1 and an assets array")
    output.mkdir(parents=True, exist_ok=True)
    shared_images = output / "_textures"
    allowed = _allowed_sources()
    seen_ids: set[str] = set()
    report = []
    catalog_entries = []
    expected_outputs = set()
    for spec in manifest["assets"]:
        if not isinstance(spec, dict):
            raise ValueError("every source asset must be an object")
        source, slug = _validate_asset(spec, seen_ids, allowed)
        summary = _extract_one(spec, source, slug, output, shared_images)
        report.append(summary)
        expected_outputs.add((output / f"{slug}.glb").resolve())
        catalog_entries.append({
            "id": spec["id"],
            "label": spec["label"],
            "category": spec["category"],
            "scene_path": f"res://assets/world/continent/{slug}.glb",
            "height": float(spec["height"]),
            "tags": list(spec["tags"]),
        })
    unexpected = sorted(path.name for path in output.glob("*.glb") if path.resolve() not in expected_outputs)
    if unexpected:
        raise ValueError(f"unexpected stale extracted GLBs: {unexpected}")
    catalog_path.parent.mkdir(parents=True, exist_ok=True)
    catalog_path.write_text(json.dumps({"version": 1, "entries": catalog_entries}, indent=2) + "\n",
                            encoding="utf-8")
    # Godot writes ignored ``.import`` sidecars beside these sources.  They are
    # machine-local cache metadata, not part of the extracted library budget.
    total_bytes = sum(path.stat().st_size for path in output.rglob("*")
                      if path.is_file() and path.suffix.lower() in {".glb", ".png", ".jpg"})
    maximum = int(manifest.get("maxOutputBytes", 50 * 1024 * 1024))
    if total_bytes > maximum:
        raise ValueError(f"extracted library is {total_bytes} bytes, over the {maximum} byte limit")
    return {"assetCount": len(report), "outputBytes": total_bytes, "assets": report}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--catalog", type=Path, default=DEFAULT_CATALOG)
    parser.add_argument("--report", type=Path)
    args = parser.parse_args()
    result = export_library(args.manifest.resolve(), args.output.resolve(), args.catalog.resolve())
    if args.report:
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    print(f"exported {result['assetCount']} map assets ({result['outputBytes']} bytes)")


if __name__ == "__main__":
    main()
