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
    parents = _parents(document)
    scene_roots = set(document['scenes'][document.get('scene', 0)].get('nodes', []))
    def complete_placement(index):
        parent = parents.get(index)
        return index in scene_roots or (parent is not None and
            str(document['nodes'][parent].get('name', '')).endswith('_WorldPlacement'))
    indices = []
    for name in names:
        matches = occurrences.get(name, [])
        # Generated transform wrappers may share their object's name. Only
        # the complete placement is an extraction root; inner wrappers are fragments.
        if len(matches) > 1:
            matches = [index for index in matches if complete_placement(index)]
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


def _repair_recipe(recipe):
    if recipe == 'mirrorhold-rowing-boat-v1':
        from amberwood import props
        meshes = {'Mirrorhold_Boat': props.rowing_boat(4.6, 1.5)}
    elif recipe == 'mirrorhold-drain-grate-v1':
        import secretrooms
        group = secretrooms.entrance_prop('drain_grate',
            {'rock': 'cliff_rock', 'bark': 'bark_dark', 'stone': 'pale_ashlar', 'timber': 'timber_dark'},
            seed=20260829)
        meshes = {'Secret_mirror_lens_garden__' + name: mesh
                  for name, mesh in group.by_material(False).items()}
    else:
        raise ValueError('Unsupported map geometry repair recipe')
    result = {}
    for name, mesh in sorted(meshes.items()):
        mesh.sanitise_normals()
        mesh.drop_degenerate()
        mesh.weld(1e-4)
        result[name] = [mesh.positions.astype('<f4'), mesh.normals.astype('<f4'),
                        mesh.uvs.astype('<f4'), mesh.indices.astype('<u4').ravel()]
    return result


def _geometry_digest(values):
    return hashlib.sha256(b''.join(array.tobytes() for arrays in values for array in arrays)).hexdigest()


def _repair_geometry(spec, document, body, source):
    """Apply only explicit, hash-pinned procedural reconstruction recipes."""
    repair = spec.get('geometryRepair')
    if repair is None:
        return document, body, None
    recipe = _repair_recipe(repair['recipe'])
    if _geometry_digest(recipe.values()) != repair['geometrySha256']:
        raise ValueError('Procedural repair recipe changed; review its pinned geometry')
    selected = _select_roots(str(spec['id']), document, list(spec['roots']))
    meshes = {document['nodes'][i]['mesh'] for i in S.descendants(document, selected)
              if 'mesh' in document['nodes'][i]}
    names = {document['meshes'][index].get('name'): index for index in meshes}
    if set(names) != set(recipe) or len(names) != len(meshes):
        raise ValueError('Selected reconstruction mesh layout changed')
    semantics = ('POSITION', 'NORMAL', 'TEXCOORD_0')
    original = []
    for name in recipe:
        primitives = document['meshes'][names[name]]['primitives']
        if len(primitives) != 1 or set(primitives[0]['attributes']) != set(semantics) or primitives[0].get('targets'):
            raise ValueError('Reconstruction primitive layout changed')
        primitive = primitives[0]
        arrays = [S.GR.accessor(document, body, primitive['attributes'][k]).astype('<f4') for k in semantics]
        arrays.append(S.GR.accessor(document, body, primitive['indices']).astype('<u4').ravel())
        original.append(arrays)
    report = dict(repair, applied=False)
    if _geometry_digest(original) == repair['geometrySha256']:
        return document, body, report
    if hashlib.sha256(source.read_bytes()).hexdigest() != repair['sourceSha256']:
        raise ValueError('Damaged source differs from the pinned repair input')
    document = copy.deepcopy(document)
    packed = bytearray(body)
    for name, arrays in recipe.items():
        primitive = document['meshes'][names[name]]['primitives'][0]
        for semantic, array in zip((*semantics, 'indices'), arrays, strict=True):
            packed.extend(b'\0' * ((-len(packed)) % 4))
            view = len(document['bufferViews'])
            document['bufferViews'].append({'buffer': 0, 'byteOffset': len(packed),
                'byteLength': array.nbytes, 'target': 34963 if semantic == 'indices' else 34962})
            packed.extend(array.tobytes())
            accessor = {'bufferView': view, 'componentType': 5125 if semantic == 'indices' else 5126,
                        'count': len(array), 'type': 'SCALAR' if array.ndim == 1 else 'VEC' + str(array.shape[1]),
                        'min': np.atleast_1d(array.min(axis=0)).astype(float).tolist(),
                        'max': np.atleast_1d(array.max(axis=0)).astype(float).tolist()}
            index = len(document['accessors'])
            document['accessors'].append(accessor)
            if semantic == 'indices':
                primitive['indices'] = index
            else:
                primitive['attributes'][semantic] = index
    document['buffers'] = [{'byteLength': len(packed)}]
    report['applied'] = True
    return document, bytes(packed), report


def _materialize_selected(document, body, roots, source):
    """Expand hash-verified shared props for standalone library exports."""
    matrices, _ = S.GR.hierarchy(document)
    private, body = _embed_external_images(
        document, body, source.parent, _reachable_images(document, roots))
    for root in roots:
        OE.set_matrix(private['nodes'][root], matrices[root])
    merged = S.Exporter(source.with_name('in-memory-extraction.glb'))
    chosen = merged.add(private, body, roots)
    prototypes = {}
    manifest = None
    for node in list(merged.doc['nodes']):
        extras = node.get('extras', {}).get('eloria', {})
        key = extras.get('prototype')
        if key is None:
            continue
        if not re.fullmatch(r'[0-9a-f]{64}', key):
            raise ValueError('Invalid shared map prototype key')
        path = (MAPS / '_shared/meshes' / (key + '.glb')).resolve()
        if manifest is None:
            manifest = _read_json(source.with_suffix('.json')).get('externalMeshes', {})
        expected = next((sha for uri, sha in manifest.items()
                         if (source.parent / uri).resolve() == path), None)
        if expected is None or hashlib.sha256(path.read_bytes()).hexdigest() != expected:
            raise ValueError('Missing or changed shared map prototype: ' + key)
        if key not in prototypes:
            proto, data = S.GR.load(path)
            proto_roots = proto['scenes'][proto.get('scene', 0)]['nodes']
            proto, data = _embed_external_images(
                proto, data, path.parent, _reachable_images(proto, proto_roots))
            prototypes[key] = (proto, data, proto_roots)
        proto, data, proto_roots = prototypes[key]
        wrappers = merged.add(proto, data, proto_roots)
        node.setdefault('children', []).extend(wrappers)
        for wrapper in wrappers:
            merged.doc['scenes'][0]['nodes'].remove(wrapper)
        extras.pop('prototype')
    return merged.doc, bytes(merged.body), chosen


def _extract_one(spec: dict, source: Path, slug: str, output: Path, shared_images: Path) -> dict:
    document, body = S.GR.load(source)
    document, body, repair = _repair_geometry(spec, document, body, source)
    roots = _select_roots(str(spec["id"]), document, [str(name) for name in spec["roots"]])
    document, body, roots = _materialize_selected(document, body, roots, source)
    matrices, _ = S.GR.hierarchy(document)
    for node_index in S.descendants(document, roots):
        node = document['nodes'][node_index]
        if 'mesh' not in node:
            continue
        for primitive in document['meshes'][node['mesh']]['primitives']:
            vertices = S.GR.accessor(document, body, primitive['attributes']['POSITION'])
            if not np.isfinite(vertices).all():
                raise ValueError(str(spec['id']) + ' contains nonfinite geometry')
            if 'indices' in primitive:
                indices = S.GR.accessor(document, body, primitive['indices'])
                if indices.size and int(indices.max()) >= len(vertices):
                    raise ValueError(str(spec['id']) + ' contains out-of-range triangle indices')
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
    if repair is not None:
        summary["geometryRepair"] = repair
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
