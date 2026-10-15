#!/usr/bin/env python3
"""Measure how dark each creature renders against the artwork it came from.

The roster's palettes are sampled from the concept figures and their *hues* are
good -- the median hue error across the library is about two degrees.  Their
*values* are not.  Rendered and compared against the art, every creature comes
out at roughly the same middle-dark luminance regardless of how light the
figure is: a whitehorn yak and a coastal gull, which the art paints nearly
white, land within a few points of a black iron death knight.  The range is
compressed, and range is what tells one silhouette from another in a lineup.

This renders each built GLB, compares its mean luminance to the mean luminance
of its concept figure, and reports the gain that would put it back in
proportion.  Gains only ever lift: creatures the art paints dark are already
correct and must not be crushed further.

    ELORIA_CONCEPT_FIGURES=/path/to/figures \\
        python3 eloria-assets/tools/concept_value_gains.py --table
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import numpy as np
from PIL import Image

import concept_figures as CF
import creature_roster as RO
import render_creature_qa as R

REPO = HERE.parents[1]
GLBS = REPO / "godot-client/assets/actors/native/creatures"

# The albedo is a base colour, not a lit painting, so a model is legitimately
# darker than the artwork it is taken from.  This is the ratio the library
# already sits at in the median, and holding every creature to it keeps that
# relationship while restoring the spread around it.
TARGET_RATIO = .68
# Chasing the art's absolute value is not achievable through albedo and should
# not be attempted: the shading falloff in the renderer means even a pure white
# albedo lands near 90, well under the 128 a pale concept figure measures, so
# the last of the gap can only be closed by washing every pale creature out to
# white.  The cap stops the correction before it costs more in colour than it
# buys in range; what is left is a renderer exposure question, not a palette
# one.
LIFT_LIMIT = 1.55
SIZE = 180
YAW, PITCH = 34.0, 14.0


def _luma(pixels: np.ndarray) -> float:
    return float((pixels @ np.array([.2126, .7152, .0722])).mean())


def art_luma(slug: str):
    path = CF.figure_path(slug)
    if path is None:
        return None
    array = np.asarray(Image.open(path).convert("RGBA"))
    opaque = array[..., 3] > 140
    if opaque.sum() < 200:
        return None
    return _luma(array[..., :3][opaque].astype(float))


def model_luma(slug: str):
    glb = GLBS / f"{slug}.glb"
    if not glb.exists():
        return None
    doc, binv = R.read_glb(glb)
    batches = R.gather(doc, binv)
    shot = np.asarray(R.render(batches, SIZE, YAW, PITCH,
                               R.model_bounds(batches))).astype(float)
    flat = shot.reshape(-1, 3)
    # The backdrop is a smooth gradient; anything far from its top-left value
    # in all three channels at once is the model.
    mask = np.abs(flat - flat[0]).sum(axis=1) > 26
    if mask.sum() < 400:
        return None
    return _luma(flat[mask])


def gain_for(slug: str, refine: bool = False):
    """The gain this creature needs.

    With ``refine`` the gain already in the roster is folded in, so measuring a
    build that was made *with* the table produces a corrected table rather than
    a second helping of the same correction.
    """
    art = art_luma(slug)
    model = model_luma(slug)
    if art is None or model is None or model <= 1e-6:
        return None
    standing = RO.VALUE_GAIN.get(slug, 1.0) if refine else 1.0
    wanted = standing * TARGET_RATIO * art / model
    return min(LIFT_LIMIT, max(1.0, wanted)), art, model


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("slugs", nargs="*")
    parser.add_argument("--table", action="store_true",
                        help="emit a VALUE_GAIN table for creature_roster.py")
    parser.add_argument("--refine", action="store_true",
                        help="fold in the gains already in the roster, so a "
                             "build made with the table yields a corrected one")
    parser.add_argument("--report", action="store_true",
                        help="report the ratio spread instead of a table")
    args = parser.parse_args()
    slugs = args.slugs or [entry[0] for entry in RO.ROSTER]
    measured = []
    for slug in slugs:
        found = gain_for(slug, args.refine)
        if found is None:
            continue
        gain, art, model = found
        measured.append((gain, slug, art, model))
        if args.table and gain > 1.01:
            print(f'    "{slug}": {gain:.2f},'.ljust(40)
                  + f"# art {art:5.1f}, model {model:5.1f}")
        elif not args.table:
            print(f"{slug:26s} gain {gain:.2f}  art {art:6.1f}  model {model:6.1f}"
                  f"  ratio {model / art:.2f}")
    if args.report and measured:
        ratios = sorted(m[3] / m[2] for m in measured)
        mid = ratios[len(ratios) // 2]
        print(f"\n{len(ratios)} creatures: ratio min {ratios[0]:.2f} "
              f"median {mid:.2f} max {ratios[-1]:.2f}")


if __name__ == "__main__":
    main()
