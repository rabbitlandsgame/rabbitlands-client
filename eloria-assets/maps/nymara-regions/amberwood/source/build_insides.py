#!/usr/bin/env python3
"""Compose Amberwood's four interiors into the map the server serves.

Every other Nymara region has one `<region>_insides` package: its interiors
side by side on a single map with unreachable blackspace between them, which is
the one interior map the server serves for that region. Amberwood is the
exception. Its four interiors were each built as a standalone package -
`amberwood_amber_hall`, `amberwood_cinder_chapel`, `amberwood_gate_undercroft`
and `amberwood_motherroot` - and the served `amberwood_estate` was left as a
concept stub with a flat placeholder ELM behind it. It is the last served map
with no authored collision: a 192-tile void a player walks across in any
direction.

    python eloria-assets/maps/nymara-regions/amberwood/source/build_insides.py

This composes the four, geometry and walk grid together, into
`interiors/amberwood_insides`. Nothing here is authored: each interior keeps
its own geometry, materials and collision exactly as built, and only the offset
that puts it in its quarter of the map is chosen - which is the same choice the
other nine composites already made.

The map is 64 ELM tiles, 384 cells, like every other composited insides map,
because Motherroot alone is 105 m deep and would not fit a quarter of the
192-tile map the estate placeholder used.
"""
from __future__ import annotations

import argparse
import json
import struct
import sys
from pathlib import Path

import numpy as np
from PIL import Image

HERE = Path(__file__).resolve().parent
REGIONS = HERE.parents[1]
INTERIORS = REGIONS / "interiors"

# The composite's own grid. 384 server tiles at a metre, two collision cells to
# the tile, with the origin at the centre the way the region maps have it.
SERVER_CELLS = 384
CELL_METRES = 0.5
SERVER_ORIGIN = (192.0, 192.0)
METRES_PER_TILE = 1.0
# The ELM's own convention, which the server's height field is read in.
HEIGHT_STEP = 0.2
HEIGHT_ORIGIN = -2.2

# Where each interior sits, in server tiles from the map's north-west corner.
# Quarters, with the blackspace between them that makes each a separate island:
# they are four buildings, not four wings of one.
SECTIONS = (
    ("AmberHall", "amberwood_amber_hall", (16, 16)),
    ("CinderChapel", "amberwood_cinder_chapel", (208, 16)),
    ("GateUndercroft", "amberwood_gate_undercroft", (16, 208)),
    ("Motherroot", "amberwood_motherroot", (208, 208)),
)


# ------------------------------------------------------------------ glTF I/O
JSON_CHUNK = 0x4E4F534A
BIN_CHUNK = 0x004E4942


def read_glb(path: Path) -> tuple[dict, bytes]:
    data = path.read_bytes()
    if data[:4] != b"glTF":
        raise SystemExit(f"not a GLB: {path}")
    _, _, length = struct.unpack_from("<III", data, 0)
    offset, gltf, buffer = 12, None, b""
    while offset < length:
        chunk_length, chunk_type = struct.unpack_from("<II", data, offset)
        body = data[offset + 8:offset + 8 + chunk_length]
        if chunk_type == JSON_CHUNK and gltf is None:
            gltf = json.loads(body)
        elif chunk_type == BIN_CHUNK and not buffer:
            buffer = bytes(body)
        offset += 8 + chunk_length + (-chunk_length % 4)
    if gltf is None:
        raise SystemExit(f"no JSON chunk in {path}")
    return gltf, buffer


def write_glb(path: Path, gltf: dict, buffer: bytes) -> int:
    gltf["buffers"] = [{"byteLength": len(buffer)}]
    text = json.dumps(gltf, separators=(",", ":")).encode("utf-8")
    text += b" " * (-len(text) % 4)
    body = buffer + b"\0" * (-len(buffer) % 4)
    total = 12 + 8 + len(text) + (8 + len(body) if body else 0)
    out = bytearray()
    out += struct.pack("<III", 0x46546C67, 2, total)
    out += struct.pack("<II", len(text), JSON_CHUNK) + text
    if body:
        out += struct.pack("<II", len(body), BIN_CHUNK) + body
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(bytes(out))
    return len(out)


def remap_texture_refs(node, mapping: dict) -> None:
    """Point every textureInfo in a material subtree at the merged texture."""
    if isinstance(node, dict):
        if "index" in node and isinstance(node["index"], int):
            node["index"] = mapping[node["index"]]
        for key, value in node.items():
            if key != "index":
                remap_texture_refs(value, mapping)
    elif isinstance(node, list):
        for value in node:
            remap_texture_refs(value, mapping)


class Merge:
    """One glTF being built out of several, with every index rewritten."""

    def __init__(self):
        self.out = {
            "asset": {"version": "2.0",
                      "generator": "Eloria Amberwood insides compositor"},
            "scene": 0, "scenes": [{"nodes": []}],
            "nodes": [], "meshes": [], "accessors": [], "bufferViews": [],
            "materials": [], "textures": [], "images": [], "samplers": [],
        }
        self.buffer = bytearray()
        self.used: set[str] = set()
        self.required: set[str] = set()

    def add(self, gltf: dict, buffer: bytes, prefix: str,
            translation: tuple[float, float, float]) -> None:
        self.used.update(gltf.get("extensionsUsed", ()))
        self.required.update(gltf.get("extensionsRequired", ()))

        # The BIN chunk goes on the end; every view shifts by where it landed.
        base = len(self.buffer)
        if base % 4:
            base += -base % 4
            self.buffer += b"\0" * (-len(self.buffer) % 4)
        self.buffer += buffer

        views = len(self.out["bufferViews"])
        for view in gltf.get("bufferViews", ()):
            moved = dict(view)
            moved["buffer"] = 0
            moved["byteOffset"] = view.get("byteOffset", 0) + base
            self.out["bufferViews"].append(moved)

        accessors = len(self.out["accessors"])
        for accessor in gltf.get("accessors", ()):
            moved = dict(accessor)
            if "bufferView" in moved:
                moved["bufferView"] += views
            if "sparse" in moved:
                raise SystemExit(f"{prefix}: sparse accessors are not merged")
            self.out["accessors"].append(moved)

        samplers = len(self.out["samplers"])
        self.out["samplers"].extend(dict(s) for s in gltf.get("samplers", ()))

        images = len(self.out["images"])
        for image in gltf.get("images", ()):
            moved = dict(image)
            if "bufferView" in moved:
                moved["bufferView"] += views
            self.out["images"].append(moved)

        texture_map = {}
        for index, texture in enumerate(gltf.get("textures", ())):
            moved = dict(texture)
            if "source" in moved:
                moved["source"] += images
            if "sampler" in moved:
                moved["sampler"] += samplers
            texture_map[index] = len(self.out["textures"])
            self.out["textures"].append(moved)

        materials = len(self.out["materials"])
        for material in gltf.get("materials", ()):
            moved = json.loads(json.dumps(material))
            remap_texture_refs(moved, texture_map)
            if "name" in moved:
                moved["name"] = f"{prefix}_{moved['name']}"
            self.out["materials"].append(moved)

        meshes = len(self.out["meshes"])
        for mesh in gltf.get("meshes", ()):
            moved = json.loads(json.dumps(mesh))
            for primitive in moved.get("primitives", ()):
                primitive["attributes"] = {
                    name: value + accessors
                    for name, value in primitive["attributes"].items()}
                if "indices" in primitive:
                    primitive["indices"] += accessors
                if "material" in primitive:
                    primitive["material"] += materials
                for target in primitive.get("targets", ()):
                    for name in list(target):
                        target[name] += accessors
            if "name" in moved:
                moved["name"] = f"{prefix}_{moved['name']}"
            self.out["meshes"].append(moved)

        nodes = len(self.out["nodes"])
        for node in gltf.get("nodes", ()):
            moved = json.loads(json.dumps(node))
            if "mesh" in moved:
                moved["mesh"] += meshes
            if "children" in moved:
                moved["children"] = [child + nodes for child in moved["children"]]
            moved.pop("camera", None)
            moved.pop("skin", None)
            # The client resolves collision and navigation nodes by name, and
            # four packages built from the same kit share plenty of them.
            if "name" in moved:
                moved["name"] = f"{prefix}_{moved['name']}"
            self.out["nodes"].append(moved)

        scene = gltf["scenes"][gltf.get("scene", 0)]
        roots = [index + nodes for index in scene.get("nodes", ())]
        holder = {"name": prefix, "translation": list(translation),
                  "children": roots}
        self.out["nodes"].append(holder)
        self.out["scenes"][0]["nodes"].append(len(self.out["nodes"]) - 1)

    def finish(self) -> dict:
        if self.used:
            self.out["extensionsUsed"] = sorted(self.used)
        if self.required:
            self.out["extensionsRequired"] = sorted(self.required)
        for key in ("materials", "textures", "images", "samplers"):
            if not self.out[key]:
                self.out.pop(key)
        return self.out


# ---------------------------------------------------------------- collision
def section_grid(package: Path) -> tuple[np.ndarray, np.ndarray]:
    """One interior's walk grid as (walkable, metres)."""
    manifest = json.loads((package / "world.json").read_text(encoding="utf-8"))
    collision = manifest["collision"]
    payload = (package / collision["binary"]).read_bytes()
    _, _, _, width, height = struct.unpack_from("<4sHHII", payload, 0)
    grid = np.frombuffer(payload[16:16 + width * height],
                         dtype=np.uint8).reshape(height, width)
    encoding = collision["heightEncoding"]
    # Each interior was quantised against its own floor, so decode with the
    # package's own origin and step rather than assume a shared one.
    metres = grid.astype(np.float64) * encoding["step"] + encoding["origin"]
    return grid != 0, metres


def build_collision() -> tuple[bytes, dict]:
    size = int(round(SERVER_CELLS * METRES_PER_TILE / CELL_METRES))
    walkable = np.zeros((size, size), dtype=bool)
    metres = np.zeros((size, size), dtype=np.float64)
    placed = {}
    for prefix, name, (offset_x, offset_y) in SECTIONS:
        mask, height = section_grid(INTERIORS / name)
        rows, columns = mask.shape
        # Server tiles are two cells; an offset in tiles is twice that in cells.
        top, left = offset_y * 2, offset_x * 2
        if top + rows > size or left + columns > size:
            raise SystemExit(f"{name} does not fit at {(offset_x, offset_y)}")
        window = (slice(top, top + rows), slice(left, left + columns))
        walkable[window] |= mask
        metres[window] = np.where(mask, height, metres[window])
        placed[prefix] = {"tiles": [offset_x, offset_y],
                          "cells": [columns, rows],
                          "walkable": int(mask.sum())}
    floor = metres[walkable].min() if walkable.any() else 0.0
    encoded = np.clip(np.round((metres - floor - HEIGHT_ORIGIN) / HEIGHT_STEP), 1, 255)
    payload = np.where(walkable, encoded, 0).astype(np.uint8)
    header = struct.pack("<4sHHII", b"EWCG", 2, 0, size, size)
    stats = {"cells": size, "cellMetres": CELL_METRES,
             "walkableFraction": round(float(walkable.mean()), 4),
             "sections": placed}
    return header + payload.tobytes(), stats


# ----------------------------------------------------------------- manifest
def collision_nodes(prefix: str, package: Path) -> list[str]:
    manifest = json.loads((package / "world.json").read_text(encoding="utf-8"))
    return [f"{prefix}_{name}"
            for name in manifest.get("collision", {}).get("nodeNames", ())]


def composed_bounds() -> dict:
    """Frame the placed interiors, using the same offsets as the merged GLB."""
    result = {}
    for key in ("bounds", "playableBounds"):
        lows, highs = [], []
        for _, name, (offset_x, offset_y) in SECTIONS:
            manifest = json.loads((INTERIORS / name / "world.json").read_text(encoding="utf-8"))
            origin_x, origin_y = manifest["coordinateTransform"]["serverOrigin"]
            translation = (offset_x - SERVER_ORIGIN[0] + origin_x, 0.0,
                           SERVER_ORIGIN[1] - offset_y - origin_y)
            bounds = manifest["asset"].get(key, manifest["asset"]["bounds"])
            lows.append([bounds["min"][axis] + translation[axis] for axis in range(3)])
            highs.append([bounds["max"][axis] + translation[axis] for axis in range(3)])
        result[key] = {
            "min": [round(min(row[axis] for row in lows), 3) for axis in range(3)],
            "max": [round(max(row[axis] for row in highs), 3) for axis in range(3)],
        }
    return result


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", default=str(INTERIORS / "amberwood_insides"))
    args = parser.parse_args()
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)

    merge = Merge()
    nodes: list[str] = []
    walk_prefixes: list[str] = []
    bounds = []
    cutaway_nodes, lights, spawns = [], [], []
    for prefix, name, (offset_x, offset_y) in SECTIONS:
        package = INTERIORS / name
        manifest = json.loads((package / "world.json").read_text(encoding="utf-8"))
        origin_x, origin_y = manifest["coordinateTransform"]["serverOrigin"]
        # Put the interior's own server tile (lx, ly) at (lx + offset) here.
        translation = (offset_x - SERVER_ORIGIN[0] + origin_x, 0.0,
                       SERVER_ORIGIN[1] - offset_y - origin_y)
        gltf, buffer = read_glb(package / "world.glb")
        merge.add(gltf, buffer, prefix, translation)
        nodes.extend(collision_nodes(prefix, package))
        walk_prefixes.extend(f"{prefix}_{p}" for p in
                             manifest.get("navigation", {}).get("surfaceNodePrefixes", []))
        source_bounds = manifest["asset"]["bounds"]
        bounds.extend(np.asarray(source_bounds[k]) + translation for k in ("min", "max"))
        cutaway_nodes.extend(f"{prefix}_{n}" for n in manifest.get("cutaway", {}).get("hideNodes", []))
        for key, target in (("lights", lights), ("spawnPoints", spawns)):
            for original in manifest.get(key, []):
                entry = dict(original)
                entry["id"] = prefix + "-" + entry["id"]
                entry["position"] = (np.asarray(entry["position"]) + translation).tolist()
                target.append(entry)

    payload, stats = build_collision()
    size = write_glb(out / "world.glb", merge.finish(), bytes(merge.buffer))
    (out / "collision.bin").write_bytes(payload)
    # A real overview of the four served floor plans; dark space is unserved.
    grid = np.frombuffer(payload, dtype=np.uint8, offset=16).reshape(stats["cells"], stats["cells"])
    pixels = np.full((*grid.shape, 3), [25, 29, 26], dtype=np.uint8)
    pixels[grid > 0] = [170, 151, 111]
    Image.fromarray(np.flipud(pixels)).resize((384, 384), Image.Resampling.LANCZOS).save(out / "minimap.webp", lossless=True)

    manifest = {
        "schemaVersion": "1.0.0", "assetVersion": "1.0.0",
        "asset": {"id": "amberwood_insides", "name": "Amberwood Insides",
                  "glb": "world.glb", "units": "meters", "serverCells": SERVER_CELLS,
                  "origin": [0, 0, 0],
                  **composed_bounds(),
                  "coordinateSystem": {"handedness": "right", "upAxis": "Y",
                                       "northAxis": "-Z"}},
        "coordinateTransform": {
            "metresPerTile": METRES_PER_TILE,
            "serverOrigin": list(SERVER_ORIGIN),
            "origin": [0.0, 0.0, 0.0], "walkingHeight": 0.0,
            "invertServerY": True},
        "collision": {"binary": "collision.bin", "format": "EWCG-v2",
                      "cellMetres": CELL_METRES,
                      "heightEncoding": {"origin": HEIGHT_ORIGIN,
                                         "step": HEIGHT_STEP,
                                         "range": [1, 255], "zeroMeansBlocked": True},
                      "nodeNames": nodes},
        "navigation": {"surfaceNodePrefixes": walk_prefixes,
                       "agentRadius": 0.4, "agentHeight": 1.9, "maxSlopeDegrees": 45,
                       "navmesh": {"format": "surface-prefix-v1", "polygons": []}},
        "cutaway": {"hideNodes": cutaway_nodes, "reason": "Preserve each source interior's camera cutaway."},
        "lights": lights,
        "spawnPoints": spawns,
        "minimap": {"file": "minimap.webp", "worldMin": [-192, -192],
                    "worldMax": [192, 192], "imageSize": [384, 384],
                    "pixelsPerMetre": 1},
        "sections": [
            {"id": prefix, "package": name, "serverTile": [x, y]}
            for prefix, name, (x, y) in SECTIONS],
        "provenance": {
            "composedFrom": [name for _, name, _ in SECTIONS],
            "note": "Geometry and walk grids are each package's own; only the "
                    "offset that puts one in its quarter of the map is chosen "
                    "here."},
        "statistics": stats,
    }
    (out / "world.json").write_text(json.dumps(manifest, indent=2) + "\n",
                                    encoding="utf-8")
    print(f"[insides] {out} glb {size / 1048576:.1f} MiB, "
          f"{stats['cells']}x{stats['cells']} cells, "
          f"{stats['walkableFraction'] * 100:.1f}% walkable, "
          f"{len(nodes)} collision nodes")
    for prefix, section in stats["sections"].items():
        print(f"[section] {prefix:16s} at tile {tuple(section['tiles'])} "
              f"{section['cells'][0]}x{section['cells'][1]} cells, "
              f"{section['walkable']} walkable")
    return 0


if __name__ == "__main__":
    sys.exit(main())
