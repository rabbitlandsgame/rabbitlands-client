#!/usr/bin/env python3
"""Build the Manymouth Delta interior map packages.

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

import deltakit as DK
import interiors as I
import stiltkit  # noqa: F401  (registers the delta tree species)

ROOT = Path(__file__).resolve().parents[1]           # .../manymouth_delta
INTERIOR_ROOT = ROOT.parent / "interiors"
SEED = 20260830

# The region these interiors open off. Every reference below is derived from it
# rather than written out, because a copied build script whose return portal
# still says "amberwood" sends every player out of the wrong map.
PARENT_REGION_ID = "manymouth_delta"
PARENT_REGION_NAME = "Manymouth Delta"
PARENT_REGION_MAP = "manymouth_delta"
CELL = 1.0                                            # collision cell, metres


def export_glb(interior: I.Interior, sets, path: Path):
    builder = GLTF.GltfBuilder(generator="Eloria Manymouth Delta interior builder")
    used = {piece.material for piece in interior.group.all_parts}
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
                            # Facing matters on arrival: a player dropped into a
                            # room looking at the wall they came through has to
                            # turn round before they can see where they are.
                            "rotationDegrees": round(float(a.get("facing", 0.0)), 1),
                            "surface": "Walk", "section": a["section"]}
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
        # Two classes: the hanging oil lanterns that are the region's readable
        # light source, and a handful of large cold sources for the two rooms a
        # lantern cannot light - the forty-metre gate chamber, whose subject is
        # a glowing ring, and the sanctum court, which is open to the sky.
        "lights": ([{"id": f"lantern-{i:02d}", "kind": "point", "position": p,
                     "colour": [1.0, 0.66, 0.32], "range": 9.0, "energy": 1.5}
                    for i, p in enumerate(interior.lamps)]
                   + [{"id": f"shaft-{i:02d}", "kind": "point",
                       "position": entry["position"],
                       "colour": entry.get("colour", [0.7, 0.85, 0.9]),
                       "range": entry.get("range", 30.0),
                       "energy": entry.get("energy", 3.0),
                       "section": entry.get("section")}
                      for i, entry in enumerate(
                          getattr(interior, "skylights", []))]),
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
            "Portal transition, navmesh generation and LOD are unverified: the "
            "frames captured for this package are real Godot renders of the GLB "
            "through GLTFDocument, but no server was run, so no transition was "
            "actually taken.",
            "The interior concept board is truncated to 786,446 bytes and only "
            "the top tenth of each panel decodes. These four compositions are "
            "authored from its ten named subjects, the QA layout brief, the "
            "region board's intact panel 8, and the region itself.",
        ],
    }
    path.write_text(json.dumps(doc, indent=2) + "\n")
    return doc


def check_doors_match(interior: I.Interior, doc: dict) -> list[str]:
    """Every region door must have an arrival, and every arrival a door.

    The two halves of a transition are authored in two different build scripts,
    and nothing has ever checked that they agree. A door whose destinationSpawn
    names an arrival that does not exist is a door that drops the player at the
    map's default spawn - which, on a combined insides map, is in a completely
    different section - and an arrival with no door is dead geometry nobody can
    reach. Both failures are silent and neither shows up in a validator.
    """
    region_manifest = ROOT / "world.json"
    if not region_manifest.is_file():
        return [f"cannot check doors: no {region_manifest}"]
    region = json.loads(region_manifest.read_text(encoding="utf-8"))
    insides_map = "manymouth_flooded_labyrinth"
    doors = {p["destinationSpawn"]: p["id"] for p in region.get("portals", [])
             if p.get("destinationMap") == insides_map
             and p.get("destinationSpawn")}
    arrivals = {a["id"] for a in getattr(interior, "arrivals", [])}
    region_spawns = {s["id"] for s in region.get("spawnPoints", [])}
    exits = {p["destinationSpawn"] for p in doc.get("portals", [])
             if p.get("destinationSpawn")}

    problems = []
    for spawn_id in sorted(set(doors) - arrivals):
        problems.append(f"region door targets missing arrival {spawn_id!r}")
    for spawn_id in sorted(arrivals - set(doors)):
        problems.append(f"arrival {spawn_id!r} has no region door")
    for spawn_id in sorted(exits - region_spawns):
        problems.append(f"return portal targets missing region spawn {spawn_id!r}")
    return problems


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--only", nargs="*", default=None)
    args = ap.parse_args()
    # The region's own recipes are not in the shared table until deltakit
    # registers them; without this every manymouth_* material in these
    # interiors resolves to bark_oak, exactly as it did in the region's
    # captures before the toolkit gained its register_materials hook.
    sets = DK.register(preview.texture_sets())
    summary = []
    # One combined map, not four packages: see interiors.combine().
    for key, builder_fn in (("manymouth_delta_insides", I.combine),):
        if args.only and key not in args.only:
            continue
        t0 = time.time()
        interior = builder_fn(SEED)
        # a secret whose door is down here rather than on the region above
        SD.dress_interior(interior, SEC, "manymouth_flooded_labyrinth", SEED)
        out = INTERIOR_ROOT / interior.ident
        out.mkdir(parents=True, exist_ok=True)
        builder, stats = export_glb(interior, sets, out / "world.glb")
        stats["nodeNames"] = [n["name"] for n in builder.to_json()["nodes"]]
        payload, collision_stats = build_collision(interior)
        (out / "collision.bin").write_bytes(payload)
        doc = write_manifest(interior, stats, collision_stats, out / "world.json")
        problems = check_doors_match(interior, doc)
        if problems:
            print("[doors] TRANSITIONS DO NOT RESOLVE:")
            for line in problems:
                print("   ", line)
        else:
            print(f"[doors] {len(getattr(interior, 'arrivals', []))} arrivals, "
                  f"every one reachable from a region door and returning to a "
                  f"region spawn")
        report = validate_gltf.validate(str(out / "world.glb"))
        (out / "world.glb.validator.json").write_text(
            json.dumps(report.to_dict(), indent=2) + "\n")
        ok = (not report.to_dict().get("errors")) and not problems
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
