#!/usr/bin/env python3
"""Build the Westhaven interior map packages.

Emits, per interior, the same package shape the region above uses:

    maps/nymara-regions/interiors/<id>/world.glb
                                     /world.json
                                     /collision.bin
                                     /world.glb.validator.json

Geometry, materials and the walk-surface contract all come from the shared
toolkit, so an interior is the same construction as the map it opens off. The
four compositions themselves are this region's, in `interiors.py` beside this
file, rather than in the toolkit: they are region content, not shared capability.
"""
from __future__ import annotations

import argparse
import json
import math
import struct
import sys
import time
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "_toolkit"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import preview
import validate_gltf
import secretdoors as SD
import secrets_design as SEC
from amberwood import gltf as GLTF, materials as MAT, mesh as M

import havenkit as HK
import interiors as I

ROOT = Path(__file__).resolve().parents[1]           # .../westhaven
INTERIOR_ROOT = ROOT.parent / "interiors"
SEED = 20260902

# The region these interiors open off. Every reference below is derived from it
# rather than written out, because a copied build script whose return portal
# still says "amberwood" sends every player out of the wrong map.
PARENT_REGION_ID = "westhaven"
PARENT_REGION_NAME = "Westhaven"
PARENT_REGION_MAP = "westhaven"
INSIDES_MAP = "westhaven_insides"
CELL = 1.0                                            # collision cell, metres


def surface_doors() -> dict[str, dict]:
    """The region's doors into this map, read from the region's own manifest.

    The interiors record where their surface entrance is, and the region records
    where the door is. Those are the same fact, so only one of them should be
    authored: this reads the region's finished `world.json` and lets the
    interiors take their anchors from it. Otherwise the two drift the first time
    a door is nudged onto a walkable cell, and the interiors go on claiming an
    entrance that has moved.
    """
    manifest = json.loads((ROOT / "world.json").read_text())
    doors = {p["destinationSpawn"]: p for p in manifest.get("portals", [])
             if p.get("destinationMap") == INSIDES_MAP}
    if not doors:
        raise SystemExit(
            f"{ROOT / 'world.json'} declares no portals into {INSIDES_MAP}: "
            "build the region first, with the insides doors in it")
    return doors


def export_glb(interior: I.Interior, sets, path: Path):
    builder = GLTF.GltfBuilder(generator="Eloria Westhaven interior builder (original procedural assets)")
    used = {piece.material for piece in interior.group.all_parts}
    unpinned = sorted(used - I.MATERIALS)
    if unpinned:
        raise SystemExit("materials used but not in interiors.MATERIALS: "
                         + ", ".join(unpinned))
    unused = sorted(I.MATERIALS - used)
    if unused:
        print("[materials] WARNING pinned but unreferenced, costing bytes: "
              + ", ".join(unused))
    MAT.register_gltf_materials(builder, sets, only=used)
    root = GLTF.Node(name=f"Interior_{interior.ident}")

    def emit(bucket: dict[str, M.Mesh], prefix: str, parent: GLTF.Node):
        for material, piece in sorted(bucket.items()):
            piece = piece.drop_degenerate().sanitise_normals()
            if piece.triangle_count == 0:
                continue
            name = f"{prefix}_{material}"
            builder.add_mesh(name, piece, with_tangents=True)
            parent.add(GLTF.Node(name=name, mesh=name))

    # Walk surfaces carry the navigation prefix the client's grounding ray tests,
    # and lids go out under Roof_ so the manifest's cutaway block can name them.
    emit(interior.group.by_material(overhead=True), f"Roof_{interior.ident}", root)
    emit(interior.group.by_material(walk=False), f"Build_{interior.ident}", root)
    emit(interior.group.by_material(walk=True), "Walk", root)

    builder.add_node(root)
    size = builder.write_glb(str(path))
    stats = builder.statistics()
    stats["glbBytes"] = size
    return builder, stats


COLLISION_CELL = 0.5


def build_collision(interior: I.Interior):
    """Half-metre walkability grid in the region's EWCG v1 format.

    The region and the client already agree on a binary contract - magic, version,
    width, height, then one unsigned byte per cell, rows running north to south.
    Inventing a second format for interiors would produce a file the loader
    cannot read, so this emits exactly the same layout.
    """
    lo, hi = interior.group.walk_bounds()
    x0 = math.floor(float(lo[0])) - 2
    z1 = math.ceil(float(hi[2])) + 2
    width = int(math.ceil((math.ceil(float(hi[0])) + 2 - x0) / COLLISION_CELL))
    height = int(math.ceil((z1 - (math.floor(float(lo[2])) - 2)) / COLLISION_CELL))
    width -= width % 6
    height -= height % 6

    walkable = np.zeros((height, width), dtype=bool)
    tops = np.full((height, width), np.nan)
    for piece in interior.group.walk_parts:
        tri = piece.positions[piece.indices].reshape(-1, 3, 3)
        normals = np.cross(tri[:, 1] - tri[:, 0], tri[:, 2] - tri[:, 0])
        lengths = np.linalg.norm(normals, axis=1)
        keep = lengths > 1e-9
        tri, normals, lengths = tri[keep], normals[keep], lengths[keep]
        tri = tri[(normals[:, 1] / lengths) > 0.55]     # a riser is not a floor
        if len(tri) == 0:
            continue
        # Column 0 is the -X western edge; row 0 is the +Z southern edge.
        cx0 = np.clip(np.floor((tri[:, :, 0].min(axis=1) - x0) / COLLISION_CELL), 0,
                      width - 1).astype(int)
        cx1 = np.clip(np.floor((tri[:, :, 0].max(axis=1) - x0) / COLLISION_CELL), 0,
                      width - 1).astype(int)
        cz0 = np.clip(np.floor((z1 - tri[:, :, 2].max(axis=1)) / COLLISION_CELL), 0,
                      height - 1).astype(int)
        cz1 = np.clip(np.floor((z1 - tri[:, :, 2].min(axis=1)) / COLLISION_CELL), 0,
                      height - 1).astype(int)
        peak = tri[:, :, 1].max(axis=1)
        for i in range(len(tri)):
            # Test the cell centre against the triangle rather than filling its
            # bounding box: a box fill marks cells the surface does not actually
            # cover, and the region's verifier reports those as walkable cells
            # with no surface under them.
            zs = np.arange(cz0[i], cz1[i] + 1)
            xs = np.arange(cx0[i], cx1[i] + 1)
            if zs.size == 0 or xs.size == 0:
                continue
            px = x0 + (xs + 0.5) * COLLISION_CELL
            pz = z1 - (zs + 0.5) * COLLISION_CELL
            gx, gz = np.meshgrid(px, pz)
            a, b, c = tri[i, 0], tri[i, 1], tri[i, 2]
            d = ((b[2] - c[2]) * (a[0] - c[0]) + (c[0] - b[0]) * (a[2] - c[2]))
            if abs(d) < 1e-12:
                continue
            w0 = ((b[2] - c[2]) * (gx - c[0]) + (c[0] - b[0]) * (gz - c[2])) / d
            w1 = ((c[2] - a[2]) * (gx - c[0]) + (a[0] - c[0]) * (gz - c[2])) / d
            # Barycentric tolerance is relative to triangle size: 0.02 on a 22 m
            # floor is nearly half a metre of slop, which marks cells outside the
            # room as walkable. Test strictly.
            inside = (w0 >= 0.0) & (w1 >= 0.0) & (w0 + w1 <= 1.0)
            if not inside.any():
                continue
            block = walkable[cz0[i]:cz1[i] + 1, cx0[i]:cx1[i] + 1]
            block |= inside
            heights = tops[cz0[i]:cz1[i] + 1, cx0[i]:cx1[i] + 1]
            np.copyto(heights, peak[i],
                      where=inside & (np.isnan(heights) | (heights < peak[i])))

    # EWCG cells are a six-bit height code, not a flag: 0 means blocked, and
    # 1..63 decode as origin + value * step. Writing a flat 1 would claim every
    # floor in the map sits at one height, which the region's own verifier
    # catches by comparing the decoded height against the rendered surface.
    surfaces = tops[~np.isnan(tops)]
    if surfaces.size:
        low, high = float(surfaces.min()), float(surfaces.max())
    else:
        low = high = 0.0
    step = max(0.1, (high - low) / 61.0)
    origin = low - step
    codes = np.clip(np.round((tops - origin) / step), 1, 63)
    grid = np.where(walkable & ~np.isnan(tops), codes, 0).astype(np.uint8)
    walkable &= grid > 0
    payload = struct.pack("<4sHHII", b"EWCG", 1, 0, width, height) + grid.tobytes()
    stats = {
        "binary": "collision.bin",
        "format": "EWCG-v1",
        "width": width, "height": height, "cellMetres": COLLISION_CELL,
        "originMetres": [float(x0), float(z1)],
        "heightEncoding": {
            "origin": round(origin, 3), "step": round(step, 4), "range": [1, 63],
            "zeroMeansBlocked": True,
            "note": ("Step is fitted to this interior's own vertical range, so the "
                     "six-bit field spans it without clamping. The Godot loader "
                     "still takes elevation from the rendered Walk_ surfaces; this "
                     "grid is authoritative only for walkability."),
        },
        "walkableCells": int(walkable.sum()),
        "blockedCells": int((~walkable).sum()),
        "walkableFraction": round(float(walkable.mean()), 4),
        "rowOrder": "server-tile-y (row 0 is the +Z southern edge)",
        "columnOrder": "server-tile-x (column 0 is the -X western edge)",
    }
    return payload, stats


def write_manifest(interior: I.Interior, stats, collision_stats, path: Path):
    lo, hi = interior.group.bounds()
    walk_lo, walk_hi = interior.group.walk_bounds()
    spawn_space = interior.spawn_space or interior.subjects[0][2]
    space = interior.spaces[spawn_space]
    spawn = [round((space["x0"] + space["x1"]) * 0.5, 2), round(space["floor"] + 0.05, 2),
             round((space["z0"] + space["z1"]) * 0.5, 2)]
    arrivals = getattr(interior, "arrivals", None) or [
        {"id": interior.destination_spawn, "name": interior.name,
         "section": interior.ident, "position": spawn}]
    doc = {
        "schemaVersion": "1.0.0",
        "assetVersion": "1.0.0",
        "asset": {
            "id": interior.ident,
            "name": interior.name,
            "glb": "world.glb",
            "units": "meters",
            "coordinateSystem": {"handedness": "right", "upAxis": "Y", "northAxis": "-Z"},
            "origin": [0, 0, 0],
            "bounds": {"min": [round(float(v), 2) for v in lo],
                       "max": [round(float(v), 2) for v in hi]},
            "playableBounds": {"min": [round(float(v), 2) for v in walk_lo],
                               "max": [round(float(v), 2) for v in walk_hi]},
            "interiorClass": interior.klass,
            "parentRegion": PARENT_REGION_ID,
            "serverCells": int(max(collision_stats["width"], collision_stats["height"])
                               * COLLISION_CELL),
        },
        "coordinateTransform": {
            "metresPerTile": 1.0,
            "serverOrigin": [float(-collision_stats["originMetres"][0]),
                             float(collision_stats["originMetres"][1])],
            "origin": [0.0, 0.0, 0.0],
            "walkingHeight": round(float(space["floor"]), 2),
            "invertServerY": True,
        },
        # One arrival per surface door. A combined insides map is entered at a
        # different point depending on which door was used, so the spawn list is
        # the whole point of it rather than a formality.
        "spawnPoints": ([{"id": "default", "position": spawn, "rotationDegrees": 0,
                          "surface": "Walk"}]
                        + [{"id": a["id"], "name": a["name"], "position": a["position"],
                            "rotationDegrees": 0, "surface": "Walk",
                            "section": a["section"]}
                           for a in arrivals]),
        "collision": dict(collision_stats,
                          nodeNames=[n for n in stats["nodeNames"]
                                     if not n.startswith("Walk_")]),
        # Every lid in the map. An interior is a closed box under a camera that
        # looks down into it, so the client hides these outright and the player
        # sees the room they are standing in. Collision built from the same
        # nodes stays, so a hidden vault is still solid overhead.
        "cutaway": {
            "hideNodes": [n for n in stats["nodeNames"] if n.startswith("Roof_")],
            "reason": "interior lids; the isometric rig frames the floor, not the roof",
        },
        "navigation": {
            "surfaceNodePrefixes": ["Walk_"],
            "agentRadius": 0.4,
            "agentHeight": 1.9,
            "maxSlopeDegrees": 45,
            "navmesh": {"format": "surface-prefix-v1", "polygons": []},
            "notes": ["Every standable surface is a Walk_<material> node, matching the "
                      "region's contract: the client turns navigation.surfaceNodePrefixes "
                      "into the layer its downward grounding ray tests."],
        },
        # A return portal standing on each arrival, sending the player back to
        # the surface door they came in by rather than to one shared exit.
        "portals": [{
            "id": f"exit-{a['id']}",
            "name": f"Return to {PARENT_REGION_NAME}",
            "type": "map-transition",
            "position": a["position"],
            "radius": 3.0,
            "destinationMap": PARENT_REGION_MAP,
            "destinationSpawn": a["id"],
            "section": a["section"],
            "authority": "server",
        } for a in arrivals],
        "sections": getattr(interior, "sections", []),
        "landmarks": interior.landmarks,
        "interactives": interior.interactives,
        "npcMarkers": interior.npc_markers,
        "harvestables": interior.harvestables,
        # A lamp is [x, y, z] or [x, y, z, range, energy]. The defaults suit a
        # room; a 52 m cavern needs its own reach, and without the override
        # every lamp in it throws 9 m and the section is unlit whatever you do.
        "lights": [{"id": f"lantern-{i:02d}", "kind": "point",
                    "position": [round(float(v), 2) for v in p[:3]],
                    "colour": [1.0, 0.66, 0.32],
                    "range": round(float(p[3]), 2) if len(p) > 3 else 9.0,
                    "energy": round(float(p[4]), 2) if len(p) > 4 else 1.5}
                   for i, p in enumerate(interior.lamps)],
        "environment": dict(interior.environment, openToSky=interior.open_to_sky),
        "spaces": {key: {k: round(float(v), 2) for k, v in value.items()}
                   for key, value in interior.spaces.items()},
        "conceptArt": {
            "detailBoard": f"../../{PARENT_REGION_ID}/references/00-concept-detail-board.png",
            "role": "parent-region board; these interiors have no board of their own",
            "panelGrid": [5, 2],
            "viewCount": 10,
            # a subject may carry an explicit camera, so index rather than unpack
            "subjects": [entry[1] for entry in interior.subjects],
        },
        "performance": stats,
        "sources": [
            {"id": "generator", "file": "source/build_interiors.py",
             "role": "reproducible-build", "seed": SEED},
            {"id": "anchor", "landmark": interior.anchor_landmark,
             "position": interior.anchor_position,
             "role": f"surface entrance on the {PARENT_REGION_NAME} region map"},
        ],
        "provenance": {
            "geometry": "authored with the shared Nymara toolkit; no scattered placement",
            "textures": "procedural, from _toolkit/amberwood/textures.py",
            "thirdParty": "none",
        },
        "notes": interior.notes,
        "productionStatus": "authored-geometry-materials-population",
        "knownLimitations": [
            "Not opened in Godot: no client is installable in the build environment, "
            "so collision response, navmesh generation, portal transition, LOD and "
            "transparency sorting are unverified.",
            "eloria-server has not registered these map keys.",
        ],
    }
    path.write_text(json.dumps(doc, indent=2) + "\n")
    return doc


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--only", nargs="*", default=None)
    args = ap.parse_args()
    # Westhaven's own recipes are registered at build time rather than being in
    # the shared table, so the interiors need the same call the region build
    # makes. Without it every Walk_ floor here is a material the exporter has
    # never heard of.
    sets = HK.register(preview.texture_sets())
    summary = []
    # One combined map, not four packages: see interiors.combine().
    for key, builder_fn in (("westhaven_insides", I.combine),):
        if args.only and key not in args.only:
            continue
        t0 = time.time()
        interior = builder_fn(SEED)
        # a secret whose door is down here rather than on the region above
        SD.dress_interior(interior, SEC, "westhaven_insides", SEED)
        # Take every surface anchor from the region manifest, so the entrance a
        # section claims is the door the region actually built.
        doors = surface_doors()
        missing = [a["id"] for a in interior.arrivals if a["id"] not in doors]
        if missing:
            raise SystemExit("the region has no door for: " + ", ".join(missing))
        for arrival in interior.arrivals:
            door = doors[arrival["id"]]
            arrival["surfaceLandmark"] = door["id"]
            arrival["surfacePosition"] = door["position"]
        for section in interior.sections:
            door = doors[[a["id"] for a in interior.arrivals
                          if a["section"] == section["id"]][0]]
            section["surfaceLandmark"] = door["id"]
            section["surfacePosition"] = door["position"]
        interior.anchor_position = doors[interior.destination_spawn]["position"]
        interior.anchor_landmark = doors[interior.destination_spawn]["id"]
        out = INTERIOR_ROOT / interior.ident
        out.mkdir(parents=True, exist_ok=True)
        builder, stats = export_glb(interior, sets, out / "world.glb")
        stats["nodeNames"] = [n["name"] for n in builder.to_json()["nodes"]]
        payload, collision_stats = build_collision(interior)
        (out / "collision.bin").write_bytes(payload)
        doc = write_manifest(interior, stats, collision_stats, out / "world.json")
        report = validate_gltf.validate(str(out / "world.glb"))
        (out / "world.glb.validator.json").write_text(
            json.dumps(report.to_dict(), indent=2) + "\n")
        ok = not report.to_dict().get("errors")
        summary.append((interior.ident, stats["uniqueTriangles"], stats["glbBytes"],
                        collision_stats["walkableCells"], ok))
        print(f"[{interior.ident}] {stats['uniqueTriangles']} tris, "
              f"{stats['glbBytes'] / 1e6:.2f} MB, "
              f"{collision_stats['walkableCells']} walkable cells, "
              f"glTF {'ok' if ok else 'ERRORS'} ({time.time() - t0:.1f}s)")
    print()
    for ident, tris, size, cells, ok in summary:
        print(f"  {ident:<28} {tris:>7} tris {size / 1e6:>7.2f} MB {cells:>6} cells "
              f"{'PASS' if ok else 'FAIL'}")
    return 0 if all(s[-1] for s in summary) else 1


if __name__ == "__main__":
    raise SystemExit(main())
