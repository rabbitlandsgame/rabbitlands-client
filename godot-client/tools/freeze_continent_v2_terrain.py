#!/usr/bin/env python3
"""Freeze a catalog's sculpted island group into one replayable terrain input.

Read original scenes, manifests, specs, bases and colors from a pinned Git commit,
not the working tree. This still replays after those scenes are retired. The
largest source grid is the parent; smaller grids must be byte-identical crops.
Sparse sculpt entries must be disjoint, finite, correctly bound and inside their
source's ownership/authority. Apply float32 additions exactly as the editor does.
Patches remain authored scene modifiers; paths must not shape terrain.

  python godot-client/tools/freeze_continent_v2_terrain.py [--source-ref COMMIT]
  python godot-client/tools/freeze_continent_v2_terrain.py --check

--check writes nothing and compares every output byte, including provenance.
"""
from __future__ import annotations

import argparse
from dataclasses import dataclass
import hashlib
import json
from pathlib import Path, PurePosixPath
import re
import subprocess
import tempfile

import numpy as np

import continent_v2_territories as T

CHECKOUT = Path(__file__).resolve().parents[2]
SOURCE_REF = "72fbd49e11f39fc9c1a00f5cadd9e447ae34e46e"
CATALOG_PATH = "godot-client/world_authoring/continent-v2/territories.json"
OUTPUT_PATH = "eloria-assets/maps/continent-v2/_continent_v2/group-terrain"
MAX_ABS_DELTA_METRES = 4096.0
SCHEMA = "eloria-continent-v2-frozen-group-terrain-v1"


class FreezeError(ValueError):
    """An input cannot safely produce one shared terrain base."""


def sha256(blob: bytes) -> str:
    return hashlib.sha256(blob).hexdigest()


def json_bytes(value) -> bytes:
    return (json.dumps(value, indent=1, ensure_ascii=False, allow_nan=False) + "\n").encode("utf-8")


def git_path(resource: str) -> str:
    if resource.startswith("res://../"):
        path = resource[len("res://../"):]
    elif resource.startswith("res://"):
        path = "godot-client/" + resource[len("res://"):]
    else:
        path = resource
    if PurePosixPath(path).is_absolute() or ".." in PurePosixPath(path).parts:
        raise FreezeError(f"resource is outside the checkout: {resource}")
    return path


class GitInputs:
    """A pinned source reader; subprocess arguments never pass through a shell."""
    def __init__(self, checkout: Path, source_ref: str = SOURCE_REF):
        self.checkout = Path(checkout)
        try:
            self.commit = subprocess.check_output(
                ["git", "rev-parse", "--verify", source_ref + "^{commit}"],
                cwd=self.checkout, stderr=subprocess.PIPE, text=True).strip()
        except subprocess.CalledProcessError as error:
            raise FreezeError(f"source ref does not resolve to a commit: {source_ref}") from error
        self.files: dict[str, bytes] = {}

    def read(self, path: str) -> bytes:
        if path not in self.files:
            try:
                self.files[path] = subprocess.check_output(
                    ["git", "show", f"{self.commit}:{path}"],
                    cwd=self.checkout, stderr=subprocess.PIPE)
            except subprocess.CalledProcessError as error:
                raise FreezeError(f"pinned source file is missing: {path}") from error
        return self.files[path]


def parse_scene(blob: bytes) -> T.Scene:
    # Reuse the project's TSCN parser without assuming retired sources exist.
    with tempfile.TemporaryDirectory(prefix="eloria-frozen-scene-") as scratch:
        path = Path(scratch) / "source.tscn"
        path.write_bytes(blob)
        sections = T.read_tscn(path)
    ext = {s.attributes["id"]: s.attributes.get("path", "") for s in sections if s.kind == "ext_resource"}
    sub = {s.attributes["id"]: s for s in sections if s.kind == "sub_resource"}
    nodes = {}
    for section in sections:
        if section.kind != "node":
            continue
        parent = section.attributes.get("parent")
        name = section.attributes["name"]
        nodes["." if parent is None else name if parent == "." else f"{parent}/{name}"] = section
    return T.Scene(Path("pinned-source.tscn"), ext, sub, nodes)


def numbers(text: str, kind: str) -> np.ndarray:
    values = np.asarray(T._numbers(text, kind), dtype=np.float64)
    if not np.isfinite(values).all():
        raise FreezeError(f"{kind} contains a non-finite number")
    return values


@dataclass
class Source:
    territory: T.Territory
    colors: np.ndarray
    sculpt: np.ndarray
    paths: dict[str, str]


def load_source(reader: GitInputs, entry: dict) -> Source:
    paths = {"scene": git_path(entry["scenePath"]),
             "manifest": git_path(entry["manifestPath"]),
             "authoringSpec": git_path(entry["authoringSpecPath"])}
    manifest = json.loads(reader.read(paths["manifest"]))
    spec = json.loads(reader.read(paths["authoringSpec"]))
    scene = parse_scene(reader.read(paths["scene"]))
    terrain = scene.node("Terrain")
    if terrain is None or scene.script_of(terrain) != T.TERRAIN_SCRIPT:
        raise FreezeError(f"{entry['id']}: no authored Terrain node")
    props = terrain.properties
    origin = numbers(props["origin"], "Vector2")
    raw_grid = numbers(props["grid_size"], "Vector2i")
    if raw_grid.size != 2 or np.any(raw_grid != raw_grid.astype(np.int64)) or np.any(raw_grid < 2):
        raise FreezeError(f"{entry['id']}: invalid terrain grid")
    width, height = map(int, raw_grid)
    cell = float(props.get("cell_metres", "2.0"))
    if not np.isfinite(cell) or cell != T.CELL:
        raise FreezeError(f"{entry['id']}: terrain cell spacing differs from the 2 m lattice")
    paths["baseHeights"] = git_path(json.loads(props["base_heights_path"]))
    paths["baseColors"] = git_path(json.loads(props["base_colors_path"]))
    paths["terrainProvenance"] = str(PurePosixPath(paths["baseHeights"]).parent / "terrain-provenance.json")
    heights_blob = reader.read(paths["baseHeights"])
    colors_blob = reader.read(paths["baseColors"])
    if len(heights_blob) != width * height * 4 or len(colors_blob) != width * height * 4:
        raise FreezeError(f"{entry['id']}: base height/color lengths disagree with terrain grid")
    heights = np.frombuffer(heights_blob, dtype="<f4").reshape(height, width).copy()
    colors = np.frombuffer(colors_blob, dtype=np.uint8).reshape(height, width, 4).copy()
    if not np.isfinite(heights).all():
        raise FreezeError(f"{entry['id']}: base heights contain non-finite samples")
    geography = manifest["continentGeography"]
    translation = np.asarray(geography["translation"], dtype=np.float64)
    if origin.size != 2 or translation.shape != (3,) or not np.isfinite(translation).all():
        raise FreezeError(f"{entry['id']}: invalid terrain frame")
    territory = T.Territory(
        entry["id"], entry["label"], translation, geography["ownershipPolygon"], manifest, spec, scene,
        origin + translation[[0, 2]], width, height, heights, Path(paths["baseColors"]),
        json.loads(reader.read(paths["terrainProvenance"])))
    sculpt = np.zeros((height, width), dtype=np.float32)
    reference = props.get("sculpt_layer")
    if reference is not None:
        match = re.fullmatch(r'SubResource\("([^"]+)"\)', reference.strip())
        if match is None or match.group(1) not in scene.sub:
            raise FreezeError(f"{territory.id}: sculpt layer is not an embedded resource")
        layer = scene.sub[match.group(1)].properties
        if (json.loads(layer.get("base_sha256", '""')) != sha256(heights_blob)
                or not np.array_equal(numbers(layer["origin"], "Vector2"), origin)
                or not np.array_equal(numbers(layer["grid_size"], "Vector2i"), raw_grid)
                or float(layer.get("cell_metres", "0")) != cell):
            raise FreezeError(f"{territory.id}: stale sculpt base/grid binding")
        raw_indices = numbers(layer.get("indices", "PackedInt32Array()"), "PackedInt32Array")
        deltas = numbers(layer.get("deltas", "PackedFloat32Array()"), "PackedFloat32Array")
        if raw_indices.size != deltas.size:
            raise FreezeError(f"{territory.id}: sculpt index/delta lengths differ")
        if (np.any(raw_indices != raw_indices.astype(np.int64)) or np.any(raw_indices < 0)
                or np.any(raw_indices >= width * height) or np.any(np.diff(raw_indices) <= 0)):
            raise FreezeError(f"{territory.id}: sculpt indices must be unique, sorted and in-grid")
        if np.any(np.abs(deltas) > MAX_ABS_DELTA_METRES):
            raise FreezeError(f"{territory.id}: sculpt delta exceeds editor's 4096 m limit")
        sculpt.ravel()[raw_indices.astype(np.int64)] = deltas.astype(np.float32)
    shaping = T.shaping_paths(territory)
    if shaping:
        raise FreezeError(f"{territory.id}: terrain-shaping paths must remain disabled: {shaping}")
    return Source(territory, colors, sculpt, paths)


def build_snapshot(reader: GitInputs) -> dict[str, bytes]:
    catalog = json.loads(reader.read(CATALOG_PATH))
    entries = catalog["entries"]
    ids = [entry["id"] for entry in entries]
    if not ids or len(set(ids)) != len(ids):
        raise FreezeError("source catalog must contain distinct territories")
    sources = [load_source(reader, entry) for entry in entries]
    territories = [source.territory for source in sources]
    frame_problems, _ = T.check_frames(territories)
    if frame_problems:
        raise FreezeError("source frames disagree: " + "; ".join(frame_problems))
    lattice = T.Lattice.of(territories)
    parents = [s for s in sources if s.territory.width == lattice.width
               and s.territory.height == lattice.height
               and np.array_equal(s.territory.first_vertex, lattice.first)]
    if len(parents) != 1:
        raise FreezeError("the source catalog must have one parent grid containing every crop")
    parent = parents[0]
    combined = np.zeros_like(parent.territory.heights)
    changed = np.zeros(combined.shape, dtype=bool)
    # Conflicts are refused before ownership checks: no order-dependent merge.
    for source in sources:
        t = source.territory
        window = lattice.window(t)
        if not np.array_equal(t.heights.view(np.uint32), parent.territory.heights[window].view(np.uint32)):
            raise FreezeError(f"{t.id}: base is not a byte-identical crop of the group parent")
        if not np.array_equal(source.colors, parent.colors[window]):
            raise FreezeError(f"{t.id}: colors are not a byte-identical crop of the group parent")
        active = source.sculpt != 0
        if (changed[window] & active).any():
            raise FreezeError(f"{t.id}: overlapping sparse sculpt entries conflict with another source")
        combined[window] += source.sculpt
        changed[window] |= active
    frozen = parent.territory.heights + combined
    if not np.isfinite(frozen).all():
        raise FreezeError("frozen group heights contain non-finite values")
    x, z = lattice.xz()
    records = []
    for source in sources:
        t = source.territory
        window = lattice.window(t)
        own = T.classify(x[None, :], z[:, None], t.polygon) > 0
        active = T._on_lattice(t, lattice, source.sculpt, np.float32(0)) != 0
        if (active & ~own).any() or (active & ~T.authority(t, lattice)).any():
            raise FreezeError(f"{t.id}: sculpt extends outside source ownership/authority")
        old = t.heights + source.sculpt
        owned = own[window]
        if ((old.view(np.uint32) != frozen[window].view(np.uint32)) & owned).any():
            raise FreezeError(f"{t.id}: aggregated terrain changes an owned source height")
        records.append({"id": t.id, "label": t.label, "paths": source.paths,
                        "frame": {"translation": t.translation.tolist(), "continentFirstVertex": t.first_vertex.tolist(),
                                  "gridSize": [t.width, t.height], "cellMetres": T.CELL,
                                  "server": t.manifest["server"]},
                        "nonzeroSculptVertices": int((source.sculpt != 0).sum()),
                        "ownedVerticesVerifiedByteExact": int(owned.sum()),
                        "sceneSidePatches": T.patches(t), "terrainShapingPaths": []})
    # Pin the editor's arithmetic/patch order, without baking its patches twice.
    for path in ("godot-client/src/dev/map_authoring_region/terrain_sculpt_layer.gd",
                 "godot-client/src/dev/map_authoring_region/terrain_control.gd"):
        reader.read(path)
    outputs = {"base-heights.f32le": frozen.astype("<f4").tobytes(),
               "base-colors.rgba8": parent.colors.tobytes()}
    provenance = {"schema": SCHEMA, "sourceCommit": reader.commit, "sourceCatalog": CATALOG_PATH,
                  "method": "Parent float32 base plus disjoint sparse sculpt layers; patches remain authored in scenes",
                  "parentSourceId": parent.territory.id,
                  "grid": {"continentFirstVertex": lattice.first.tolist(), "gridSize": [lattice.width, lattice.height],
                           "cellMetres": T.CELL},
                  "sourceFiles": {path: {"sha256": sha256(blob), "bytes": len(blob)}
                                  for path, blob in sorted(reader.files.items())},
                  "sources": records, "nonzeroSculptVertices": int(changed.sum()),
                  "outputs": {name: {"sha256": sha256(blob), "bytes": len(blob)} for name, blob in outputs.items()}}
    outputs["terrain-provenance.json"] = json_bytes(provenance)
    return outputs


def write_or_check(output: Path, expected: dict[str, bytes], *, check: bool) -> None:
    if check:
        for name, blob in expected.items():
            path = output / name
            if not path.is_file() or path.read_bytes() != blob:
                raise FreezeError(f"frozen terrain output is missing, stale or corrupt: {name}")
        return
    output.mkdir(parents=True, exist_ok=True)
    for name, blob in expected.items():
        path = output / name
        if not path.is_file() or path.read_bytes() != blob:
            path.write_bytes(blob)


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--checkout", type=Path, default=CHECKOUT)
    parser.add_argument("--source-ref", default=SOURCE_REF)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args(argv)
    try:
        reader = GitInputs(args.checkout, args.source_ref)
        expected = build_snapshot(reader)
        output = args.output or args.checkout / OUTPUT_PATH
        write_or_check(output, expected, check=args.check)
    except (FreezeError, KeyError, ValueError, OSError) as error:
        print(f"freeze_continent_v2_terrain: {error}")
        return 1
    print(json.dumps({"mode": "check" if args.check else "write", "sourceCommit": reader.commit,
                      "output": str(output), "baseSha256": sha256(expected["base-heights.f32le"])}, indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

