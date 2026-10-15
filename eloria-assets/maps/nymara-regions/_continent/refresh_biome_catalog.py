"""Refresh saved-terrain appearance without recomposing continent geometry.

Run after baking edited region scenes. The catalog is portable Godot input;
existing chunk GLBs, roads, collision, and publication records are untouched.
Normal continent export emits the same masks into new chunk manifests.
"""
from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path
from types import SimpleNamespace

import numpy as np

import authoring as AUTHORING
import landscape as L
from biome_blend import build_masks, palette_sources
from world_layout import CELL, CHUNK, outline, ownership_map, triangle_sample


HERE = Path(__file__).resolve().parent
CATALOG = AUTHORING.CLIENT / "godot-client/assets/world/biome_blend/catalog.json"


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _existing_chunks() -> set[tuple[int, int]]:
    root = AUTHORING.CLIENT / "eloria-assets/maps/nymara-regions"
    chunks = set()
    manifests = list(root.glob("*/chunks/*/world.json"))
    manifests += list((AUTHORING.CLIENT / "eloria-assets/maps/four-gates/chunks").glob("*/world.json"))
    for manifest in manifests:
        if 'biomeBlend' in json.loads(manifest.read_text(encoding='utf-8')):
            raise AUTHORING.AuthoringError(
                f'{manifest}: child biomeBlend is authoritative; use normal continent export for this material edit')
        stem = manifest.parent.name
        if re.fullmatch(r"-?\d+_-?\d+", stem) is None:
            raise AUTHORING.AuthoringError(f"unexpected continent chunk name: {manifest}")
        chunks.add(tuple(map(int, stem.split("_"))))
    if not chunks:
        raise AUTHORING.AuthoringError("no published chunk manifests; generate geometry first")
    return chunks


def refresh() -> dict:
    """Reuse exact saved height authority and only generate colour masks."""
    plan = L.load_plan()
    ids, owner, x0, z0 = ownership_map(plan)
    height = np.zeros((owner.shape[0] + 1, owner.shape[1] + 1), dtype=np.float64)
    world = SimpleNamespace(plan=plan, ids=ids, owner=owner, x0=x0, z0=z0,
                            height=height, polygons={region: outline(owner == index, x0, z0)
                                                     for index, region in enumerate(ids)})
    world.height_at = lambda x, z: triangle_sample(world.height, x, z, x0, z0, CELL)
    snapshots = AUTHORING.load_snapshots()
    if set(ids) != {snapshot.document["regionId"] for snapshot in snapshots}:
        raise AUTHORING.AuthoringError("colour refresh requires all 12 saved regions")
    world.authoring_snapshots = {snapshot.document["regionId"]: snapshot for snapshot in snapshots}
    for snapshot in snapshots:
        AUTHORING.verify_ownership(world, snapshot)
        AUTHORING.apply_terrain(world, snapshot)
    authority = world.authored_terrain_authority
    if not np.all(authority):
        raise AUTHORING.AuthoringError(
            f"saved terrain does not cover {int(np.count_nonzero(~authority))} continent vertices")
    if not np.array_equal(world.height.astype("<f4"), world.authored_terrain_height):
        raise AUTHORING.AuthoringError("saved terrain height differs after authority assembly")

    configs = build_masks(world, _existing_chunks())
    catalog = {
        "schema": "eloria-biome-blend-catalog-v1",
        "chunkMetres": CHUNK,
        "sources": {
            "planSha256": _sha(HERE / "diagonal-plan.json"),
            "savedHeightSha256": hashlib.sha256(world.authored_terrain_height.tobytes()).hexdigest(),
            "savedVertices": int(authority.sum()),
            "snapshots": {snapshot.document["regionId"]: snapshot.digest for snapshot in snapshots},
            "optedRegions": sorted(palette_sources(world)),
        },
        "chunks": [configs[key] for key in sorted(configs, key=lambda cell: (cell[1], cell[0]))],
    }
    CATALOG.parent.mkdir(parents=True, exist_ok=True)
    encoded = json.dumps(catalog, sort_keys=True, indent=2, ensure_ascii=False) + "\n"
    if not CATALOG.is_file() or CATALOG.read_text(encoding="utf-8") != encoded:
        CATALOG.write_text(encoded, encoding="utf-8", newline="\n")
    return {"regions": len(snapshots), "optedRegions": catalog["sources"]["optedRegions"],
            "savedVertices": int(authority.sum()), "chunks": len(configs),
            "catalogSha256": hashlib.sha256(encoded.encode("utf-8")).hexdigest()}


if __name__ == "__main__":
    print(json.dumps(refresh(), sort_keys=True), flush=True)
