#!/usr/bin/env python3
"""The ground a player walks on has to be opaque in every shipped region.

Blended geometry in Godot writes no depth, is sorted one whole instance at a
time rather than per triangle, and is left out of the directional shadow map.
None of that matters for a pond. It matters a great deal for a terrain layer:
Whitehorn's glacier is a 140 x 436 m sheet folded 128 m down a gorge, and while
it was blended its own far triangles painted over its near ones, the seracs
standing on it dropped out as the camera turned, and it cast no shadow at all.
"""
from __future__ import annotations

import json
from pathlib import Path
import struct
import unittest

ROOT = Path(__file__).resolve().parents[2]
REGIONS = ROOT / "eloria-assets" / "maps" / "nymara-regions"

GLB_MAGIC = b"glTF"
CHUNK_JSON = 0x4E4F534A

# Solid ice: the ICE terrain class, the seracs and frozen cascades standing on
# it, the glacier temple's walls, and the walkable ice decks inside Whitehorn.
# It reads as ice through its own texture and roughness, not through alpha.
OPAQUE_MATERIALS = {"glacier_ice"}


def read_document(path: Path) -> dict:
    data = path.read_bytes()
    if data[:4] != GLB_MAGIC:
        raise ValueError(f"{path} is not a binary glTF")
    offset = 12
    while offset < len(data):
        length, kind = struct.unpack("<II", data[offset:offset + 8])
        if kind == CHUNK_JSON:
            return json.loads(data[offset + 8:offset + 8 + length])
        offset += 8 + length
    raise ValueError(f"{path} has no JSON chunk")


def packages() -> list[Path]:
    return sorted(REGIONS.rglob("world.glb"))


def blended_material_names(document: dict) -> set[str]:
    return {
        material.get("name", "")
        for material in document.get("materials", [])
        if material.get("alphaMode") == "BLEND"
    }


def nodes_by_material(document: dict) -> dict[str, list[str]]:
    """Node name -> the material names its mesh draws with."""
    materials = document.get("materials", [])
    meshes = document.get("meshes", [])
    per_mesh: list[set[str]] = []
    for mesh in meshes:
        names: set[str] = set()
        for primitive in mesh.get("primitives", []):
            index = primitive.get("material")
            if index is not None:
                names.add(materials[index].get("name", ""))
        per_mesh.append(names)
    found: dict[str, list[str]] = {}
    for node in document.get("nodes", []):
        index = node.get("mesh")
        if index is None:
            continue
        found.setdefault(node.get("name", ""), []).extend(sorted(per_mesh[index]))
    return found


class MapSurfaceMaterials(unittest.TestCase):
    def test_packages_are_present(self) -> None:
        self.assertGreaterEqual(len(packages()), 10,
                                "the region packages should be checked out")

    def test_walk_surfaces_are_opaque(self) -> None:
        offenders: list[str] = []
        for glb in packages():
            manifest_path = glb.with_name("world.json")
            if not manifest_path.exists():
                continue
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            prefixes = [
                str(prefix) for prefix in
                manifest.get("navigation", {}).get("surfaceNodePrefixes", [])
            ]
            if not prefixes:
                continue
            document = read_document(glb)
            blended = blended_material_names(document)
            if not blended:
                continue
            for node, used in nodes_by_material(document).items():
                if not any(node.startswith(prefix) for prefix in prefixes):
                    continue
                for material in used:
                    if material in blended:
                        offenders.append("%s: %s draws blended %s" % (
                            glb.parent.relative_to(REGIONS), node, material))
        self.assertEqual(offenders, [], "walk surfaces must be opaque")

    def test_solid_materials_are_opaque(self) -> None:
        offenders: list[str] = []
        for glb in packages():
            blended = blended_material_names(read_document(glb))
            for material in sorted(blended & OPAQUE_MATERIALS):
                offenders.append("%s: %s is blended" % (
                    glb.parent.relative_to(REGIONS), material))
        self.assertEqual(offenders, [],
                         "materials standing for solid volumes must be opaque")


if __name__ == "__main__":
    unittest.main(verbosity=2)
