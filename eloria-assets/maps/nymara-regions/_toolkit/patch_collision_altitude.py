#!/usr/bin/env python3
"""Apply the altitude fix to every region's `build_collision`.

Each region package carries its own copy of `build_collision`, and all ten are
identical in the two places that matter, so the change is made once here and
stamped onto each rather than hand-edited ten times and left to drift.

Two things change.

**Elevation stops being clipped to 63.** A walk grid encoded at 0.2 m over the
range 1..63 can only express 12.4 m of relief. These regions have between 18 m
and 253 m of it, so all their high ground collapsed onto the same value:
Whitehorn Range came out 99.9% one elevation. The server measures its climb
limit in differences between those bytes, so on a map with no differences
nothing stops a player walking straight up a mountain. The grid now carries the
map's real relief, with the step it was encoded at declared beside it.

**Steep ground is blocked.** The height byte cannot express a 253 m map at a
step fine enough for a two-stage climb limit to mean anything, so steepness has
to be part of walkability instead. The gradient is measured on the *composed*
surface - terrain with its bridges, decks and stairs on it - at the walk grid's
own half-metre resolution, and anything above `MAX_WALK_GRADIENT` is blocked.
The existing `slope < 1.05` test stays: it is measured on the bare terrain
grid, which is coarser and misses what the decks change.

Authored walk surfaces are exempt. A deck is flat but its rim is a cliff, and
blocking the rim would strand the deck; the package placed it deliberately, so
it stays walkable and its own edges do the stopping.

    python eloria-assets/maps/nymara-regions/_toolkit/patch_collision_altitude.py [--check]
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

REGIONS = Path(__file__).resolve().parent.parent
BUILDS = {
    "amberwood": "build_amberwood.py",
    "amethyst_barrens": "build_amethyst.py",
    "crownwater": "build_crownwater.py",
    "grey_moors": "build_grey_moors.py",
    "manymouth_delta": "build_manymouth_delta.py",
    "mirrorhold": "build_mirrorhold.py",
    "ssarathi_ruins": "build_ssarathi.py",
    "verdant_stair": "build_verdant_stair.py",
    "westhaven": "build_westhaven.py",
    "whitehorn_range": "build_whitehorn.py",
}

OLD_DECK_MARK = """        elevated += 1
        surface = np.where(footprint, deck_y, surface)"""
NEW_DECK_MARK = """        elevated += 1
        decks |= footprint
        surface = np.where(footprint, deck_y, surface)"""

OLD_QUANTISE = """    quantised = np.clip(np.round((surface - COLLISION_HEIGHT_ORIGIN)
                                 / COLLISION_HEIGHT_STEP), 1, 63).astype(np.uint8)
    grid = np.where(walkable, quantised, 0).astype(np.uint8)"""
NEW_QUANTISE = """    # Steepness has to be part of walkability, not of the height byte. That
    # byte holds 63 steps, and a region with 253 m of relief cannot be encoded
    # finely enough for a two-stage climb limit to mean anything - which is how
    # a mountainside ended up walkable. Measured here on the *composed* surface
    # at the walk grid's own resolution, so a bridge reads as the bridge rather
    # than the gorge under it, unlike the bare-terrain `slope` above.
    rise_z, rise_x = np.gradient(surface, COLLISION_CELL)
    too_steep = np.hypot(rise_x, rise_z) > MAX_WALK_GRADIENT
    # A deck is flat but its rim is a cliff. The package put it there to be
    # walked on, so it keeps its footprint and its own edges do the stopping.
    steep_ground = too_steep & ~decks
    walkable &= ~steep_ground

    # The map's own relief, at the finest step that fits the byte. Clipping to
    # 63 at 0.2 m held 12.4 m and flattened everything above it into one value.
    floor = float(surface[walkable].min()) if walkable.any() else 0.0
    relief = (float(surface[walkable].max()) - floor) if walkable.any() else 0.0
    height_step = max(COLLISION_HEIGHT_STEP,
                      relief / (COLLISION_HEIGHT_LEVELS - 1))
    quantised = np.clip(np.round((surface - floor) / height_step) + 1,
                        1, COLLISION_HEIGHT_LEVELS).astype(np.uint8)
    grid = np.where(walkable, quantised, 0).astype(np.uint8)"""

OLD_HEADER = 'struct.pack("<4sHHII", b"EWCG", 1, 0, width, height)'
NEW_HEADER = 'struct.pack("<4sHHII", b"EWCG", 2, 0, width, height)'

OLD_STATS = '        "elevatedDecks": elevated,'
NEW_STATS = """        "elevatedDecks": elevated,
        "steepCells": int(steep_ground.sum()),
        "reliefMetres": round(relief, 2),
        "heightEncoding": {"origin": round(floor - height_step, 4),
                           "step": round(height_step, 6),
                           "range": [1, COLLISION_HEIGHT_LEVELS],
                           "zeroMeansBlocked": True},"""

OLD_DECKS = """    surface = ground.copy()"""
NEW_DECKS = """    surface = ground.copy()
    decks = np.zeros_like(walkable)"""

OLD_CONSTANTS = """COLLISION_HEIGHT_ORIGIN = -2.2"""
NEW_CONSTANTS = """COLLISION_HEIGHT_ORIGIN = -2.2
# Levels an ELM height byte holds: the server masks it with 0x3F, so 1..63.
COLLISION_HEIGHT_LEVELS = 63
# Metres of rise per metre travelled that a walker will not climb. Eternal
# Lands allows two 0.2 m stages across a half-metre tile, which is this.
MAX_WALK_GRADIENT = 0.8"""


# Two packages build their decks differently and need their own anchor for the
# one line that records which cells a deck covers. Westhaven already tracks it
# under another name; Verdant Stair rasterises deck triangles rather than
# stamping circular footprints, because its whole region is a staircase.
REGION_PATCHES = {
    "westhaven": (('''        elevated += 1
        deck_mask |= footprint''',
                   '''        elevated += 1
        deck_mask |= footprint
        decks |= footprint'''),),
    "verdant_stair": (('''                walkable[block_rows, block_columns] = True
                touched = True''',
                       '''                walkable[block_rows, block_columns] = True
                decks[block_rows, block_columns] = True
                touched = True'''),),
}

PATCHES = ((OLD_CONSTANTS, NEW_CONSTANTS), (OLD_DECKS, NEW_DECKS),
           (OLD_QUANTISE, NEW_QUANTISE),
           (OLD_HEADER, NEW_HEADER), (OLD_STATS, NEW_STATS))


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--check", action="store_true",
                        help="report which packages still need the change")
    args = parser.parse_args()
    pending, done = [], []
    for region, filename in BUILDS.items():
        path = REGIONS / region / "source" / filename
        text = path.read_text(encoding="utf-8")
        patches = PATCHES + REGION_PATCHES.get(
            region, ((OLD_DECK_MARK, NEW_DECK_MARK),))
        if all(new in text for _, new in patches):
            done.append(region)
            continue
        missing = [old for old, new in patches if old not in text and new not in text]
        if missing:
            print(f"[skip] {region}: source does not match the expected shape")
            continue
        if args.check:
            pending.append(region)
            continue
        for old, new in patches:
            if new not in text:
                text = text.replace(old, new, 1)
        path.write_text(text, encoding="utf-8")
        print(f"[patch] {region}")
        done.append(region)
    if args.check:
        print(f"[check] {len(done)} patched, {len(pending)} pending: "
              f"{', '.join(pending) if pending else 'none'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
