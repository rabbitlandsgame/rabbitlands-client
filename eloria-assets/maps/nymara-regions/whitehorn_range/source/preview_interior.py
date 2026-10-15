"""Render the Whitehorn interior with the offline rasteriser.

Same harness as Amberwood's, with two differences that matter.

The lighting rig is cold. Amberwood's interiors are lit by hung amber in timber
rooms; this one is lit by lamps standing in ice, and the ice does most of the
work - it bounces a blue ambient that a warm rig destroys. Rendered under
Amberwood's `INTERIOR_LIGHT` the whole temple came out the colour of a tavern.

The camera set is per-space rather than one-per-subject, because two of the ten
subjects (the materials study and the prayer columns) share a room with another
subject and would otherwise render the same frame twice.
"""
from __future__ import annotations

import argparse
import os
import sys

from PIL import Image, ImageDraw

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                "..", "..", "_toolkit"))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import preview
from amberwood import interiors as I, render as R

import interiors as IT

# Lamplight on ice: a dim warm key for the hung lanterns, a strong cold ambient
# for everything the ice bounces, and no shadow pass - shadow-mapping a sealed
# volume from a single direction only darkens it uniformly.
GLACIER_LIGHT = R.Lighting(
    sun_direction=(-0.28, 0.78, 0.56),
    sun_color=(0.42, 0.36, 0.26),
    sky_color=(0.16, 0.20, 0.28),
    ground_color=(0.10, 0.13, 0.18),
    fog_color=(0.13, 0.16, 0.21),
    fog_density=0.011,
    fog_height_falloff=0.0,
    exposure=1.12,
    ambient_strength=0.42,
    saturation=1.02,
    sky_zenith=(0.09, 0.12, 0.18),
    sky_horizon=(0.16, 0.20, 0.26),
)


# The generic "stand back along the room's mid-line" rule puts the eye inside a
# column in the altar chamber and against a wall in the ice arch, and lands it
# on top of a brazier at the entry. These rooms name their own camera.
# Keyed "section.space" and written in each section's OWN local coordinates;
# combine() then shifts them by that section's layout offset, exactly as it
# shifts the geometry. Writing them in combined coordinates would mean
# rewriting every camera the next time a section moves on the map.
CAMERAS = {
    "glacier_temple.snow_entry":      ((0.0, 1.7, -10.5), (0.0, 1.5, 3.0)),
    "glacier_temple.votive":          ((-29.5, 0.9, 13.5), (-21.0, 0.6, 26.0)),
    "glacier_temple.ice_arch":        ((0.0, 0.2, 50.5), (0.0, 0.1, 61.0)),
    "glacier_temple.glacier_altar":   ((-4.0, -1.3, 69.0), (-4.0, -1.6, 86.0)),
    "glacier_temple.upper_sanctuary": ((27.0, 8.7, 58.5), (27.0, 8.5, 75.0)),
    "whitehorn_mine.crevasse_hall":   ((13.0, 0.6, 21.5), (13.0, 0.3, 35.0)),
    "whitehorn_mine.main_gallery":    ((2.0, 0.5, -6.0), (24.0, 0.2, 14.0)),
    "ice_cave.blue_chamber":          ((-14.0, 0.1, 9.5), (8.0, -0.2, 28.0)),
    "ice_cave.crystal_vault":         ((0.0, -1.5, 35.0), (0.0, -1.8, 44.0)),
    "ice_cave.meltwater_pool":        ((17.5, -0.7, 15.0), (31.0, -1.0, 15.0)),
    "frost_barrow.cist_gallery":      ((-4.0, 0.5, 6.5), (-4.0, 0.3, 21.0)),
    "frost_barrow.barrow_chamber":    ((13.0, -0.3, 9.5), (20.0, -0.6, 24.0)),
}


def _offset_for(space_key):
    """The layout shift combine() applied to the section this space belongs to."""
    section = space_key.split(".", 1)[0]
    dx, dz = IT.LAYOUT.get(section, (0.0, 0.0))
    return dx + IT.LAYOUT_ORIGIN[0], dz + IT.LAYOUT_ORIGIN[1]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("interior", nargs="?", default="insides",
                    choices=sorted(IT.ALL) + ["insides"])
    ap.add_argument("out")
    ap.add_argument("--width", type=int, default=460)
    ap.add_argument("--height", type=int, default=290)
    ap.add_argument("--cols", type=int, default=4)
    args = ap.parse_args()

    sets = preview.texture_sets()
    interior = IT.combine() if args.interior == "insides"         else IT.ALL[args.interior]()
    scene = preview.new_scene(sets)
    for part in interior.group.all_parts:
        scene.add_mesh(part)
    print("[scene] %d triangles" % scene.triangle_count())

    views, seen = [], set()
    for ident, subject, space in interior.subjects:
        if space in seen or space not in interior.spaces:
            continue
        seen.add(space)
        views.append((ident, subject, space))

    cols = args.cols
    rows = (len(views) + cols - 1) // cols
    sheet = Image.new("RGB", (cols * args.width, rows * (args.height + 16)),
                      (12, 13, 16))
    draw = ImageDraw.Draw(sheet)
    for i, (ident, subject, space) in enumerate(views):
        if space in CAMERAS:
            eye, target = CAMERAS[space]
            dx, dz = _offset_for(space)
            eye = (eye[0] + dx, eye[1], eye[2] + dz)
            target = (target[0] + dx, target[1], target[2] + dz)
        elif space in interior.passages:
            eye, target = _passage_camera(interior.passages[space])
        else:
            eye, target = _room_camera(interior.spaces[space])
        image = scene.render(eye, target, width=args.width, height=args.height,
                             fov=64.0, lighting=GLACIER_LIGHT, shadows=False,
                             far=420.0)
        x, y = (i % cols) * args.width, (i // cols) * (args.height + 16)
        sheet.paste(image, (x, y + 16))
        draw.text((x + 5, y + 3), "%s  %s" % (ident, subject),
                  fill=(186, 200, 216))
        print("  %s  %s" % (ident, subject))
    sheet.save(args.out)
    print("[sheet] %s" % args.out)
    return 0


def _room_camera(space):
    cx = (space["x0"] + space["x1"]) * 0.5
    cz = (space["z0"] + space["z1"]) * 0.5
    ix = (space["x1"] - space["x0"]) * 0.34
    iz = (space["z1"] - space["z0"]) * 0.34
    if abs(space["x1"] - space["x0"]) >= abs(space["z1"] - space["z0"]):
        eye = (cx - ix, space["floor"] + I.EYE, cz - iz * 0.3)
    else:
        eye = (cx - ix * 0.3, space["floor"] + I.EYE, cz - iz)
    target = (cx + (cx - eye[0]) * 0.4, space["floor"] + I.EYE * 0.85,
              cz + (cz - eye[2]) * 0.4)
    return eye, target


def _passage_camera(run):
    (ax, az), (bx, bz) = run["a"], run["b"]
    dx, dz = bx - ax, bz - az
    eye = (ax + dx * 0.05, run["y0"] + I.EYE, az + dz * 0.05)
    target = (bx - dx * 0.04, run["y1"] + I.EYE * 0.8, bz - dz * 0.04)
    return eye, target


if __name__ == "__main__":
    raise SystemExit(main())
