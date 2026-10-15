#!/usr/bin/env python3
"""Build Crownwater's four insides as ONE map with blackspace between them.

Eternal Lands puts a region's interiors on a single map, laid out as islands of
floor with unwalkable void between, rather than one map file per room. Amethyst
Barrens' `amethyst_barrens_insides` already does this in the repository, and
this follows it: one package, one GLB, one collision grid, four sections, one
spawn and one exit portal per section.

WHY THE BLACKSPACE IS FREE
--------------------------
Nothing has to draw the void. `build_collision` marks a cell walkable only where
a `Walk_` surface actually covers it, so every cell between the sections is
already zero - which is exactly what "blocked" means in EWCG v1 and what the
server reads as blackspace. The gaps are wide enough (60 m and more) that no
section's geometry, lights or grounding ray can reach another's.

LAYOUT, in metres on the 384 x 384 map

    z=334  +----------------+--------+--------------+
           | customs hall   |        |              |
    z=251  +----------------+        |              |
           |                          blackspace    |
    z=179  +-------------------+     +--------------+
           | drowned crown     |     | tide cistern |
    z=  7  +-------------------+     +--------------+
             x=9         x=170        x=234    x=304

    the campanile sits alone at x 55-65, z 295-305

The Drowned Crown is 121 x 172 m on its own and sets the map size; the other
three fit around it.
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
from amberwood import mesh as M
from amberwood.interiors import Interior

import build_interiors as BI
import crownkit as CK
import interiors_crownwater as I

ROOT = Path(__file__).resolve().parents[1]
INTERIOR_ROOT = ROOT.parent / "interiors"
PACKAGE_ID = "crownwater_insides"
SEED = 20260901

# section id -> (builder key, x offset, z offset, entrance space)
# Offsets chosen so the closest approach between any two sections is 60 m, which
# is far beyond both the collision grid's reach and any lamp's range.
SECTIONS = [
    ("drowned_crown", "drowned_crown", 50.0, 60.0, "stairhead"),
    ("tide_cistern", "tide_cistern", 260.0, 60.0, "wellhouse"),
    ("customs_hall", "customs_hall", 250.0, 260.0, "ledger_hall"),
    ("tide_campanile", "tide_campanile", 60.0, 300.0, "shaft"),
    # the small rooms, a column east of the set pieces
    ("eleventh_bell", "eleventh_bell", 338.0, 60.0, "porch"),
    ("case_room", "case_room", 338.0, 120.0, "hall"),
    ("the_grating", "the_grating", 338.0, 180.0, "mouth"),
]

SPAWN_FOR = {
    "drowned_crown": "basilica-undercroft",
    "tide_cistern": "cistern-stair",
    "customs_hall": "customs-door",
    "tide_campanile": "campanile-door",
    "eleventh_bell": "eleventh-bell-door",
    "case_room": "case-room-door",
    "the_grating": "grating-mouth",
}


def _offset_point(point, dx, dz):
    return [round(float(point[0]) + dx, 2), round(float(point[1]), 2),
            round(float(point[2]) + dz, 2)]


def combine(seed: int = SEED) -> tuple[Interior, list[dict]]:
    """Build every section and place it on one map."""
    combined = Interior(PACKAGE_ID, "Crownwater Insides", "insides",
                        "crownwater-cathedral", [114.0, 18.09, -132.0],
                        "drowned_crown")
    sections = []

    for ident, key, dx, dz, entrance in SECTIONS:
        piece = I.ALL[key](seed)
        piece.group.transform(M.translation(dx, 0.0, dz))

        for space_key, space in piece.spaces.items():
            combined.spaces[f"{ident}.{space_key}"] = {
                "x0": round(space["x0"] + dx, 2), "z0": round(space["z0"] + dz, 2),
                "x1": round(space["x1"] + dx, 2), "z1": round(space["z1"] + dz, 2),
                "floor": round(space["floor"], 2), "height": round(space["height"], 2)}
        combined.group.add(piece.group)

        for entry in piece.landmarks:
            entry = dict(entry)
            entry["id"] = f"{ident}-{entry['id']}" if not entry["id"].startswith(ident) \
                else entry["id"]
            entry["space"] = f"{ident}.{entry['space']}"
            entry["position"] = _offset_point(entry["position"], dx, dz)
            combined.landmarks.append(entry)
        for source, target in ((piece.interactives, combined.interactives),
                               (piece.npc_markers, combined.npc_markers),
                               (piece.harvestables, combined.harvestables)):
            for entry in source:
                entry = dict(entry)
                entry["position"] = _offset_point(entry["position"], dx, dz)
                entry["section"] = ident
                target.append(entry)
        for lamp in piece.lamps:
            combined.lamps.append(_offset_point(lamp, dx, dz))
        combined.open_to_sky.extend(f"{ident}.{k}" for k in piece.open_to_sky)
        for subject, space_key, note in piece.subjects:
            combined.subjects.append((subject, f"{ident}.{space_key}", note))
        combined.notes.extend(f"[{ident}] {note}" for note in piece.notes)

        space = combined.spaces[f"{ident}.{entrance}"]
        # The section's own extent, not just its entrance room. Taken from the
        # union of every space it contributed, so a verifier counting cells per
        # section counts the whole inside rather than the doorway.
        own = [v for k, v in combined.spaces.items() if k.startswith(ident + ".")]
        extent = {"min": [round(min(s["x0"] for s in own), 2),
                          round(min(s["z0"] for s in own), 2)],
                  "max": [round(max(s["x1"] for s in own), 2),
                          round(max(s["z1"] for s in own), 2)]}
        sections.append({
            "id": ident,
            "name": piece.name,
            "class": piece.klass,
            "spawn": SPAWN_FOR[ident],
            "entrance": f"{ident}.{entrance}",
            "offset": [dx, dz],
            "arrival": [round((space["x0"] + space["x1"]) * 0.5, 2),
                        round(space["floor"] + 0.05, 2),
                        round((space["z0"] + space["z1"]) * 0.5, 2)],
            "bounds": extent,
            "entranceBounds": {"min": [space["x0"], space["z0"]],
                               "max": [space["x1"], space["z1"]]},
            "surfaceLandmark": piece.anchor_landmark,
        })

    combined.spawn_space = f"{SECTIONS[0][0]}.{SECTIONS[0][4]}"
    # One environment for one map. The sections differ in intent - a drowned
    # ruin and a working warehouse want different light - so this is a genuine
    # compromise of the single-map layout, and the per-section lamps do most of
    # the work. Pitched between the two rather than at either.
    combined.environment = {
        "sky": {"type": "gradient", "zenith": [0.10, 0.20, 0.26],
                "horizon": [0.24, 0.36, 0.40]},
        "sun": {"enabled": True, "direction": [-0.14, -0.94, 0.31],
                "color": [0.92, 0.96, 0.96], "energy": 0.95},
        "ambient": {"color": [0.34, 0.44, 0.48], "energy": 0.88,
                    "skyContribution": 0.35},
        "fog": {"enabled": True, "color": [0.20, 0.30, 0.34], "density": 0.009},
    }
    return combined, sections


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=str(INTERIOR_ROOT / PACKAGE_ID))
    args = ap.parse_args()
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)

    t0 = time.time()
    sets = CK.register(preview.texture_sets())
    interior, sections = combine()
    SD.dress_interior(interior, SEC, "drowned_crown", SEED)

    builder, stats = BI.export_glb(interior, sets, out / "world.glb")
    stats["nodeNames"] = [n["name"] for n in builder.to_json()["nodes"]]
    payload, collision_stats = BI.build_collision(interior)
    (out / "collision.bin").write_bytes(payload)

    manifest = BI.write_manifest(interior, stats, collision_stats,
                                 out / "world.json")

    # Sections, and one spawn plus one exit portal each. Written after the
    # shared writer so the single-map layout is additive rather than a fork of
    # it: everything above is the same code the per-room packages used.
    manifest["sections"] = sections
    manifest["spawnPoints"] = [
        {"id": "default", "position": sections[0]["arrival"],
         "rotationDegrees": 0, "surface": "Walk", "section": sections[0]["id"]}
    ] + [{"id": s["spawn"], "position": s["arrival"], "rotationDegrees": 0,
          "surface": "Walk", "section": s["id"]} for s in sections]
    manifest["portals"] = [
        {"id": f"exit-{s['spawn']}", "name": f"Return to Crownwater ({s['name']})",
         "type": "map-transition", "position": s["arrival"],
         "destinationMap": "crownwater",
         "destinationSpawn": "default", "radius": 2.5,
         "section": s["id"], "authority": "server"}
        for s in sections]
    manifest["notes"].append(
        "Four insides on one map with blackspace between them, following "
        "amethyst_barrens_insides. Cells between sections are zero in "
        "collision.bin because no Walk_ surface covers them - the void is not "
        "drawn, it is simply the absence of floor.")
    manifest["knownLimitations"] = list(manifest.get("knownLimitations", [])) + [
        "One environment block serves four sections of different character; the "
        "per-section lamps carry most of the lighting difference.",
    ]
    (out / "world.json").write_text(json.dumps(manifest, indent=2) + "\n",
                                    encoding="utf-8")

    report = validate_gltf.validate(str(out / "world.glb"))
    (out / "world.glb.validator.json").write_text(
        json.dumps(report.to_dict(), indent=2) + "\n", encoding="utf-8")
    errors = report.to_dict()["issues"]["numErrors"]

    print(f"[{PACKAGE_ID}] {stats['uniqueTriangles']} tris, "
          f"{stats['glbBytes'] / 1e6:.2f} MB, "
          f"{collision_stats['width']}x{collision_stats['height']} cells, "
          f"{collision_stats['walkableCells']} walkable "
          f"({collision_stats['walkableFraction'] * 100:.1f}%), "
          f"glTF {'ok' if errors == 0 else 'ERRORS'} ({time.time() - t0:.1f}s)")
    for section in sections:
        print(f"    {section['id']:<16} arrival {section['arrival']}")
    return 0 if errors == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
