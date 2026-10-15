"""Render an authored interior with the region's own rasteriser.

Interiors are lit by hung amber, not by the sun, so the lighting rig here is a
dim warm key with a strong ambient floor and no shadow pass - shadow mapping a
sealed volume from a sun direction only darkens everything uniformly.
"""
import argparse
import math
import os
import sys

from PIL import Image, ImageDraw

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "_toolkit"))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import preview
from amberwood import interiors as I, render as R

INTERIOR_LIGHT = R.Lighting(
    sun_direction=(-0.30, 0.80, 0.52),
    sun_color=(0.30, 0.22, 0.14),
    sky_color=(0.07, 0.07, 0.08),
    ground_color=(0.05, 0.04, 0.03),
    fog_color=(0.055, 0.042, 0.034),
    fog_density=0.016,
    fog_height_falloff=0.0,
    exposure=1.08,
    ambient_strength=0.24,
    saturation=1.04,
    sky_zenith=(0.05, 0.05, 0.06),
    sky_horizon=(0.10, 0.08, 0.07),
)

BUILDERS = dict(I.ALL)


DAYLIT = R.Lighting(
    sun_direction=(-0.38, 0.72, 0.58),
    sun_color=(1.05, 0.86, 0.60),
    sky_color=(0.34, 0.30, 0.26),
    ground_color=(0.16, 0.12, 0.09),
    fog_color=(0.26, 0.22, 0.18),
    fog_density=0.0055,
    fog_height_falloff=0.0,
    exposure=1.12,
    ambient_strength=0.46,
    saturation=1.05,
    sky_zenith=(0.20, 0.26, 0.34),
    sky_horizon=(0.46, 0.44, 0.40),
)


def scene_for(interior, sets):
    scene = preview.new_scene(sets)
    for part in interior.group.all_parts:
        scene.add_mesh(part)
    return scene


def camera_for_passage(run):
    (ax, az), (bx, bz) = run["a"], run["b"]
    dx, dz = bx - ax, bz - az
    eye = (ax + dx * 0.05, run["y0"] + I.EYE, az + dz * 0.05)
    target = (bx - dx * 0.04, run["y1"] + I.EYE * 0.8, bz - dz * 0.04)
    return eye, target


def camera_for(space, cloud=None):
    """Stand back along the room's mid-line at eye height, look at its middle."""
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


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("interior", choices=sorted(BUILDERS))
    ap.add_argument("out")
    ap.add_argument("--width", type=int, default=440)
    ap.add_argument("--height", type=int, default=270)
    ap.add_argument("--cols", type=int, default=4)
    args = ap.parse_args()

    sets = preview.texture_sets()
    interior = BUILDERS[args.interior]()
    scene = scene_for(interior, sets)
    print(f"[scene] {scene.triangle_count} triangles")

    views = []
    seen = set()
    for ident, subject, space in interior.subjects:
        if space in seen or space not in interior.spaces:
            continue
        seen.add(space)
        views.append((ident, subject, space))

    cols = args.cols
    rows = (len(views) + cols - 1) // cols
    sheet = Image.new("RGB", (cols * args.width, rows * (args.height + 16)), (14, 13, 15))
    draw = ImageDraw.Draw(sheet)
    for i, (ident, subject, space) in enumerate(views):
        if space in interior.passages:
            eye, target = camera_for_passage(interior.passages[space])
        else:
            eye, target = camera_for(interior.spaces[space])
        rig = DAYLIT if interior.klass in ("settlement", "transition") else INTERIOR_LIGHT
        image = scene.render(eye, target, width=args.width, height=args.height,
                             fov=62.0, lighting=rig, shadows=False, far=400.0)
        x, y = (i % cols) * args.width, (i // cols) * (args.height + 16)
        sheet.paste(image, (x, y + 16))
        draw.text((x + 5, y + 3), f"{ident}  {subject}", fill=(198, 176, 146))
        print(f"  {ident}  {subject}")
    sheet.save(args.out)
    print(f"[sheet] {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
