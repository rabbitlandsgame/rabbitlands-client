#!/usr/bin/env python3
"""Render a conformed equipment GLB beside the mesh it was generated from.

`render_native_glb_lit.py` frames each model to its own bounding box, which is
the wrong thing here twice over: a conformed piece binds in a T-pose while the
generated mesh hangs its arms down, so the two are framed at different scales
and compared in different poses.  What is left in such a picture is the pose,
not the fit.

This drives Blender instead.  The conformed piece's arms are swung down to the
angle measured off the generated mesh, both models are normalised to the same
height, and they are drawn into one frame with the same camera -- so what is
left in the picture is the difference the conform made.

    python3 eloria-assets/tools/compare_conformed_piece.py \
        --out qa/phoenix.png \
        godot-client/assets/actors/native/equipment/variants/human_male/legendary_hero_cuirass_01.glb \
        ../generate_models/meshy-armor-individual-glb/Eight...c01.glb.orig

Pass `--yaw 90` for the side view, and `--drop-material Liner` to hide the
underlayer and see the armour on its own.
"""
from __future__ import annotations

import argparse
import os
from pathlib import Path
import subprocess
import shutil
import sys

BLENDER_CANDIDATES = [
    Path(r"C:\Program Files\Blender Foundation\Blender 5.2\blender.exe"),
    Path(r"C:\Program Files\Blender Foundation\Blender 4.2\blender.exe"),
]

SCRIPT = Path(__file__).with_name("_compare_conformed_blender.py")


def find_blender() -> Path:
    for candidate in BLENDER_CANDIDATES:
        if candidate.exists():
            return candidate
    found = shutil.which("blender")
    if found:
        return Path(found)
    base = Path(r"C:\Program Files\Blender Foundation")
    if base.is_dir():
        for exe in sorted(base.glob("*/blender.exe"), reverse=True):
            return exe
    raise SystemExit("could not find blender.exe")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("models", nargs="+", type=Path)
    ap.add_argument("--out", required=True, type=Path)
    ap.add_argument("--yaw", type=float, default=0.0)
    ap.add_argument("--pose-arms", action="store_true", default=True,
                    help="swing skinned arms down to the generated angle")
    ap.add_argument("--no-pose-arms", dest="pose_arms", action="store_false")
    ap.add_argument("--drop-material", action="append", default=[],
                    help="hide materials whose name ends with this")
    ap.add_argument("--worn", type=Path, default=None, metavar="RACE.GLB",
                    help="also write <out>_worn.png: every skinned model drawn "
                         "on this race body at true scale, framed on the "
                         "torso.  A fit that reads well beside the generated "
                         "mesh can still read badly on a character, and that "
                         "is the picture the player sees")
    ap.add_argument("--labels", default="")
    ap.add_argument("--equipment", type=Path, help="Candidate equipment registry for per-body socket transforms")
    ap.add_argument("--worn-pose", choices=["rest", "source", "bent"], default="rest",
                    help="pose both the character and equipment in the worn sheet")
    ap.add_argument("--worn-region", choices=["torso", "legs", "boots", "head"], default="torso",
                    help="frame the worn region; head also attaches the first static model to its socket")
    ap.add_argument("--ensemble", action="store_true",
                    help="assemble fitted pieces into one complete set, including socket headwear")
    ap.add_argument("--save-blend", action="store_true",
                    help="save editable Blender scenes beside the comparison and worn renders")
    ap.add_argument("--width", type=int, default=760,
                    help="pixels per column")
    ap.add_argument("--threads", type=int, default=8, help="Maximum CPU render threads (default: 8)")
    args = ap.parse_args()
    if not 1 <= args.threads <= 8:
        ap.error("--threads must be between 1 and 8")

    for model in args.models:
        if not model.exists():
            raise SystemExit("no such model: %s" % model)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    if args.worn is not None and not args.worn.exists():
        raise SystemExit("no such race body: %s" % args.worn)
    if args.ensemble and args.worn is None:
        raise SystemExit("--ensemble needs --worn to resolve the head socket")
    command = [str(find_blender()), "--background", "--threads", str(args.threads), "--python", str(SCRIPT),
               "--", str(args.out.resolve()), str(args.yaw),
               "1" if args.pose_arms else "0", str(args.width),
               ",".join(args.drop_material), args.labels,
               str(args.worn.resolve()) if args.worn is not None else "", args.worn_pose,
               args.worn_region, '1' if args.ensemble else '0', '1' if args.save_blend else '0',
               str(args.equipment.resolve()) if args.equipment else '']
    command += [str(m.resolve()) for m in args.models]
    result = subprocess.run(command, capture_output=True, text=True,
                            env=dict(os.environ, ELORIA_RENDER_CORES=str(args.threads)))
    if result.returncode != 0 or not args.out.exists():
        sys.stderr.write(result.stdout[-4000:])
        sys.stderr.write(result.stderr[-4000:])
        raise SystemExit("blender failed")
    for line in result.stdout.splitlines():
        if line.startswith(("  ", "loaded")):
            print(line)
    print("wrote %s" % args.out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
