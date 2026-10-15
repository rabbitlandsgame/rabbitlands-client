"""Render an authored interior with the region's own rasteriser.

Interiors are lit by hung amber, not by the sun, so the lighting rig here is a
dim warm key with a strong ambient floor and no shadow pass - shadow mapping a
sealed volume from a sun direction only darkens everything uniformly.
"""
import argparse
import json
import math
import os
import pathlib
import sys

from PIL import Image, ImageDraw

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "_toolkit"))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import preview
from amberwood import render as R

import interiors as I

# Amberwood's interiors are lit by hung amber, so its rig is warm. These are lit
# by crystal: a cold violet key with a slightly higher ambient floor, because a
# brass-and-slate room with a warm key reads as a cellar rather than a vault.
# Amethyst's interior key is a cold violet wash, which is right for a crystal
# vault and turns a candle-lit granite barrow into flat mauve cardboard. These
# barrows are lit by tallow: a warm low key, a nearly black cold ambient, and
# enough exposure that the stone still has grain in it.
INTERIOR_LIGHT = R.Lighting(
    sun_direction=(-0.26, 0.74, 0.60),
    sun_color=(0.46, 0.34, 0.20),
    sky_color=(0.075, 0.070, 0.066),
    ground_color=(0.040, 0.036, 0.030),
    fog_color=(0.052, 0.044, 0.034),
    fog_density=0.011,
    fog_height_falloff=0.0,
    exposure=1.34,
    ambient_strength=0.34,
    saturation=1.06,
    sky_zenith=(0.045, 0.042, 0.038),
    sky_horizon=(0.085, 0.074, 0.058),
)

def _safe_name(text: str) -> str:
    """A capture id that is legal as a filename on every platform.

    Subjects are prose and contain colons - "The Great Barrow: the royal tomb".
    A colon is legal in a POSIX filename and is not on Windows, where
    `name:rest.png` silently creates an alternate data stream on `name` instead
    of a file called `name:rest.png`. The captures then appear as a directory
    of empty extension-less files, and the Godot harness, which takes its
    output filename from this id, writes nothing at all.
    """
    out = []
    for character in text:
        out.append(character if (character.isalnum() or character in "._-")
                   else "-")
    name = "".join(out)
    while "--" in name:
        name = name.replace("--", "-")
    return name.strip("-")


BUILDERS = dict(I.ALL)
BUILDERS["insides"] = I.combine


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


def camera_for(space, cloud=None, repeat: int = 0):
    """Stand back along the room's mid-line at eye height, look at its middle.

    `repeat` swings the eye a third of a turn per extra view of the same room,
    so a second subject in a room already shot is a different picture rather
    than the same one twice.
    """
    cx = (space["x0"] + space["x1"]) * 0.5
    cz = (space["z0"] + space["z1"]) * 0.5
    ix = (space["x1"] - space["x0"]) * 0.34
    iz = (space["z1"] - space["z0"]) * 0.34
    if repeat:
        angle = 2.0 * math.pi * repeat / 3.0
        eye = (cx + math.cos(angle) * ix * 1.15, space["floor"] + I.EYE,
               cz + math.sin(angle) * iz * 1.15)
        target = (cx, space["floor"] + I.EYE * 0.85, cz)
        return eye, target
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
    ap.add_argument("--captures", default=None,
                    help="also write individual frames and index.json here")
    args = ap.parse_args()

    sets = preview.texture_sets()
    interior = BUILDERS[args.interior]()
    scene = scene_for(interior, sets)
    print(f"[scene] {scene.triangle_count} triangles")

    # A subject is (ident, subject, space) or (ident, subject, space, eye, target).
    # The original tool skipped any subject whose space had already been shot,
    # which silently dropped three of the Vault's ten concept panels: an
    # experiment table and a material study are legitimately in a room the sheet
    # has already established, and they still need their own view.
    views = []
    seen: dict[str, int] = {}
    for entry in interior.subjects:
        ident, subject, space = entry[0], entry[1], entry[2]
        if space not in interior.spaces and space not in interior.passages:
            continue
        camera = entry[3:] if len(entry) >= 5 else None
        views.append((ident, subject, space, camera, seen.get(space, 0)))
        seen[space] = seen.get(space, 0) + 1

    cols = args.cols
    rows = (len(views) + cols - 1) // cols
    sheet = Image.new("RGB", (cols * args.width, rows * (args.height + 16)), (14, 13, 15))
    draw = ImageDraw.Draw(sheet)
    for i, (ident, subject, space, camera, repeat) in enumerate(views):
        if camera is not None:
            eye, target = camera
        elif space in interior.passages:
            eye, target = camera_for_passage(interior.passages[space])
        else:
            eye, target = camera_for(interior.spaces[space], repeat=repeat)
        rig = DAYLIT if interior.klass in ("settlement", "transition") else INTERIOR_LIGHT
        image = scene.render(eye, target, width=args.width, height=args.height,
                             fov=62.0, lighting=rig, shadows=False, far=400.0)
        x, y = (i % cols) * args.width, (i // cols) * (args.height + 16)
        sheet.paste(image, (x, y + 16))
        draw.text((x + 5, y + 3), f"{ident}  {subject}", fill=(198, 176, 146))
        print(f"  {ident}  {subject}")
    sheet.save(args.out)
    print(f"[sheet] {args.out}")

    # Also write the individual frames and an index beside the package, in the
    # same shape a region package uses. The shared Godot capture harness takes
    # its camera set from references/captures/index.json, so writing one here is
    # what lets an interior be captured through the real client loader at all -
    # and it makes the offline frame and the client frame the same camera.
    if args.captures:
        out_dir = pathlib.Path(args.captures)
        out_dir.mkdir(parents=True, exist_ok=True)
        index = []
        for i, (ident, subject, space, camera, repeat) in enumerate(views):
            if camera is not None:
                eye, target = camera
            elif space in interior.passages:
                eye, target = camera_for_passage(interior.passages[space])
            else:
                eye, target = camera_for(interior.spaces[space], repeat=repeat)
            rig = DAYLIT if interior.klass in ("settlement", "transition") else INTERIOR_LIGHT
            image = scene.render(eye, target, width=1180, height=760, fov=62.0,
                                 lighting=rig, shadows=False, far=400.0)
            name = _safe_name(f"{ident}-{subject}")
            image.save(out_dir / f"{name}.png")
            index.append({"id": name, "file": f"{name}.png", "panel": ident,
                          "subject": subject, "space": space,
                          "eye": [round(v, 3) for v in eye],
                          "target": [round(v, 3) for v in target],
                          "fov": 62.0, "pixels": [1180, 760]})
        (out_dir / "index.json").write_text(json.dumps(index, indent=2))
        print(f"[captures] {len(index)} frames -> {out_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
