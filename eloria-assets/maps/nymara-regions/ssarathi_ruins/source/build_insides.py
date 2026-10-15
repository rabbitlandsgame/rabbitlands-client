#!/usr/bin/env python3
"""Build Ssarathi Ruins' four insides as ONE map with blackspace between them.

Eternal Lands puts a region's interiors on a single map, laid out as islands of
floor with unwalkable void between, rather than one map file per room.
`amethyst_barrens_insides` and `crownwater_insides` already do this in the
repository; this follows them. One package, one GLB, one collision grid, four
sections, one spawn and one exit portal per section.

WHY THE BLACKSPACE IS FREE
--------------------------
Nothing has to draw the void. `build_collision` marks a cell walkable only where
a `Walk_` surface actually covers it, so every cell between the sections is
already zero - which is exactly what "blocked" means in EWCG v1 and what the
server reads as blackspace. The gaps are wide enough that no section's geometry,
lamps or grounding ray can reach another's.

LAYOUT, in metres on the 384 x 384 map

    z=344  +----------------+          +------------------+
           | drowned        |          | root undercroft  |
           | cistern        |          |                  |
    z=252  +----------------+          +------------------+

    z=178  +------------------+        +----------------+
           | royal archive    |        | serpent        |
           | (135 m deep, it  |        | hatchery       |
           |  sets the size)  |        |                |
    z= 30  +------------------+        +----------------+
             x=30        x=98           x=190      x=260

The Royal Archive is 68 x 135 m on its own and sets the map size; the other
three fit around it. Closest approach between any two sections is 60 m.
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
import ssarathikit as SK
import interiors_ssarathi as I

ROOT = Path(__file__).resolve().parents[1]
INTERIOR_ROOT = ROOT.parent / "interiors"
PACKAGE_ID = "ssarathi_insides"
SEED = 20260901

# section id -> (builder key, x offset, z offset, entrance space)
# Offsets chosen so the closest approach between any two sections is 60 m, which
# is far beyond both the collision grid's reach and any lamp's range.
SECTIONS = [
    ("royal_archive", "royal_archive", 55.0, 38.0, "water_entrance"),
    ("serpent_hatchery", "serpent_hatchery", 217.0, 46.0, "descent"),
    ("drowned_cistern", "drowned_cistern", 69.0, 258.0, "shaft_room"),
    ("root_undercroft", "root_undercroft", 213.0, 264.0, "mouth"),
    # the small rooms, a column east of the set pieces
    ("tenth_mouth", "tenth_mouth", 295.0, 38.0, "porch"),
    ("water_gate_undercut", "water_gate_undercut", 295.0, 110.0, "mouth"),
    ("lineage_house", "lineage_house", 295.0, 200.0, "hall"),
]

SPAWN_FOR = {
    "royal_archive": "archive-vault-door",
    "serpent_hatchery": "hatchery-descent",
    "drowned_cistern": "cistern-shaft",
    "root_undercroft": "undercroft-mouth",
    "tenth_mouth": "tenth-mouth-door",
    "water_gate_undercut": "water-gate-undercut-mouth",
    "lineage_house": "lineage-house-door",
}


def _offset_point(point, dx, dz):
    return [round(float(point[0]) + dx, 2), round(float(point[1]), 2),
            round(float(point[2]) + dz, 2)]


def combine(seed: int = SEED) -> tuple[Interior, list[dict]]:
    """Build every section and place it on one map."""
    combined = Interior(PACKAGE_ID, "Ssarathi Ruins Insides", "insides",
                        "sun-vault", [60.0, 13.0, -208.5], "royal_archive")
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
        # One environment for four sections of different character - a dry
        # archive, a warm hatchery, a flooded cistern and a root-broken ruin.
        # Pitched between them and left to the per-section lamps to carry the
        # difference, which is a genuine compromise of the single-map layout
        # rather than a choice. Tuned against real client frames, not guessed:
        # the region's first manifest declared no `tonemap` and rendered flat,
        # and an interior with a ceiling over it has even less to fall back on.
        "sky": {"type": "gradient", "zenith": [0.06, 0.10, 0.09],
                "horizon": [0.16, 0.22, 0.18], "energy": 0.5},
        # Values raised twice against real client frames. The first pass -
        # ambient 0.62, sun 0.55, fog 0.010, exposure 1.10 - produced rooms
        # that were atmospheric in the sense of being unreadable: the lamps
        # showed as orange points and lit nothing around them. An interior has
        # no sky to fall back on, so the ambient has to do more work here than
        # it does outdoors, not less.
        "sun": {"enabled": True, "direction": [-0.20, -0.94, 0.28],
                "color": [0.86, 0.92, 0.84], "energy": 0.30,
                "shadows": True},
        "ambient": {"color": [0.40, 0.48, 0.42], "energy": 1.30,
                    "skyContribution": 0.20},
        "fog": {"enabled": True, "color": [0.16, 0.22, 0.19],
                "density": 0.0035, "skyAffect": 0.08},
        "tonemap": {"mode": "filmic", "exposure": 1.30, "white": 6.0},
    }
    return combined, sections


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=str(INTERIOR_ROOT / PACKAGE_ID))
    args = ap.parse_args()
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)

    t0 = time.time()
    sets = SK.register(preview.texture_sets())
    interior, sections = combine()
    SD.dress_interior(interior, SEC, "ssarathi_royal_archive", SEED)

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
        {"id": f"exit-{s['spawn']}", "name": f"Return to Ssarathi Ruins ({s['name']})",
         "type": "map-transition", "position": s["arrival"],
         "destinationMap": "ssarathi_ruins",
         "destinationSpawn": s["spawn"], "radius": 2.5,
         "section": s["id"], "authority": "server"}
        for s in sections]
    manifest["notes"].append(
        "Four insides on one map with blackspace between them, following "
        "amethyst_barrens_insides and crownwater_insides. Cells between "
        "sections are zero in collision.bin because no Walk_ surface covers "
        "them - the void is not drawn, it is simply the absence of floor.")
    manifest["knownLimitations"] = list(manifest.get("knownLimitations", [])) + [
        "One environment block serves four sections of different character; the "
        "per-section lamps carry most of the lighting difference.",
        "The Royal Archive's own concept board does not decode - zero rows, not "
        "just the truncated tail every region board has - so its ten subjects "
        "were worked from concept.json's written list and the authored asset "
        "pack's piece names. There is no panel comparison for it.",
        "The other three sections have no concept art at all and are authored "
        "from the region's surface landmarks and its (intact) region board.",
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
