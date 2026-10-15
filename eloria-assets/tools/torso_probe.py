#!/usr/bin/env python3
"""Where exactly is the skin coming through?

The coverage number says how many vertices show; this says where they are, which
is the difference between tuning a cap and guessing at one.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np

import garment_coverage as gf


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--client", type=Path, required=True)
    parser.add_argument("--garment", type=Path, required=True)
    parser.add_argument("--race", default="luminous_male")
    parser.add_argument("--author-rig", default="luminous_male")
    parser.add_argument("--clip", default="bind")
    parser.add_argument("--time", type=float, default=0.0)
    arguments = parser.parse_args()

    client = arguments.client
    registry = json.loads((client / "data/actors/equipment.json").read_text())
    race_path = client / f"assets/actors/native/races/{arguments.race}.glb"
    library = client / "assets/actors/native/shared/Universal_Animation_Library.glb"

    garment_prims, garment_rig, _ = gf.load(str(arguments.garment))
    body_prims, wearer, mesh_names = gf.load(str(race_path))
    binds = gf.bone_binds(garment_rig, wearer,
                          gf.girth_ratios(registry, arguments.author_rig, arguments.race))
    if arguments.clip == "bind":
        posed = {bone: wearer.rest[bone] for bone in wearer.names}
    else:
        posed = gf.pose_globals(wearer, gf._thaw(
            gf.clip_pose(str(library), arguments.clip, arguments.time)))
    garment_matrices = {b: posed[b] @ binds[b] for b in binds if b in posed}
    body_matrices = {b: posed[b] @ wearer.inverse_bind[b] for b in wearer.names
                     if b in posed and b in wearer.inverse_bind}

    shells = []
    for primitive in garment_prims:
        moved = gf.skin(primitive.points, primitive.joints, primitive.weights,
                        garment_rig.names, garment_matrices)
        shells.extend(gf.components(moved, primitive.triangles))
    # The same rest-space claim the checker uses, so the probe and the report
    # are talking about the same set of vertices.
    arm_reach = gf._rest_reach(garment_prims, garment_rig, wearer, binds)
    print(f"shells {len(shells)}  closed {sum(s.closed for s in shells)}")
    for index, shell in enumerate(shells):
        low, high = shell.points.min(axis=0), shell.points.max(axis=0)
        print(f"  [{index}] closed={shell.closed!s:<5} volume={shell.volume:+.5f} "
              f"tris={len(shell.triangles):<5} "
              f"x {low[0]:+.3f}..{high[0]:+.3f} y {low[1]:.3f}..{high[1]:.3f}")
    enclosure = gf.Enclosure(shells)

    for primitive, name in zip(body_prims, mesh_names):
        if name != "Body" or primitive.joints is None:
            continue
        mask = gf.region_mask(primitive.points, primitive.joints, primitive.weights,
                              wearer.names, gf.TORSO_REGION, 1.030, 1.492, arm_reach)
        moved = gf.skin(primitive.points[mask], primitive.joints[mask],
                        primitive.weights[mask], wearer.names, body_matrices)
        exposed = moved[~enclosure.inside(moved)]
        if not len(exposed):
            print("nothing exposed")
            return
        print(f"\n{len(exposed)} exposed of {int(mask.sum())}")
        print(f"  x {np.abs(exposed[:, 0]).min():.3f}..{np.abs(exposed[:, 0]).max():.3f}"
              f"  y {exposed[:, 1].min():.3f}..{exposed[:, 1].max():.3f}"
              f"  z {exposed[:, 2].min():+.3f}..{exposed[:, 2].max():+.3f}")
        # A coarse map: how the exposure is spread up the body and out the arm.
        for low in np.arange(1.02, 1.56, .06):
            band = exposed[(exposed[:, 1] >= low) & (exposed[:, 1] < low + .06)]
            if len(band):
                print(f"   y {low:.2f}-{low + .06:.2f}: {len(band):>4}  "
                      f"|x| {np.abs(band[:, 0]).min():.3f}-{np.abs(band[:, 0]).max():.3f}"
                      f"  z {band[:, 2].min():+.3f}..{band[:, 2].max():+.3f}")


if __name__ == "__main__":
    main()
