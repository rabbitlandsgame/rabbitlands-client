"""Check actual skinned cape/pony samples exported by test_mounted_cape.gd.

Vertical triangle intersections test the worn fabric against the rendered
back/saddle mesh, independently of the deliberately inflated cloth collider.
All skin influence sets are applied by the engine-side sample exporter.
"""
from __future__ import annotations
import argparse
import json
from pathlib import Path
import numpy as np


def check(samples):
    rows = []
    for sample in samples:
        pony = np.asarray(sample["pony"], dtype=float)
        faces = pony[np.asarray(sample["body_indices"], dtype=int).reshape(-1, 3)]
        a, b, c = faces[:, 0], faces[:, 1], faces[:, 2]
        den = (b[:, 2] - c[:, 2]) * (a[:, 0] - c[:, 0]) + (c[:, 0] - b[:, 0]) * (a[:, 2] - c[:, 2])
        valid_face = np.abs(den) > 1e-9
        den = np.where(valid_face, den, 1.0)
        cape = np.asarray(sample["cape"], dtype=float)
        cape_faces = cape[np.asarray(sample["cape_indices"], dtype=int).reshape(-1, 3)]
        # Check faces and edges as well as joints/vertices: clear vertices
        # alone can conceal a straight cloth triangle cutting into the rump.
        points = np.concatenate([cape, cape_faces.mean(axis=1),
            (cape_faces[:, 0] + cape_faces[:, 1]) * .5,
            (cape_faces[:, 1] + cape_faces[:, 2]) * .5,
            (cape_faces[:, 2] + cape_faces[:, 0]) * .5])
        points = np.unique(np.round(points, 8), axis=0)
        gap = float("inf")
        tested = 0
        for x, y, z in points:
            u = ((b[:, 2] - c[:, 2]) * (x - c[:, 0]) + (c[:, 0] - b[:, 0]) * (z - c[:, 2])) / den
            v = ((c[:, 2] - a[:, 2]) * (x - c[:, 0]) + (a[:, 0] - c[:, 0]) * (z - c[:, 2])) / den
            w = 1 - u - v
            hit = valid_face & (u >= -1e-5) & (v >= -1e-5) & (w >= -1e-5)
            if hit.any():
                top = (a[:, 1] * u + b[:, 1] * v + c[:, 1] * w)[hit].max()
                gap = min(gap, float(y - top))
                tested += 1
        rows.append({"gait": sample["gait"], "stage": sample.get("stage"), "frame": sample.get("frame"),
                     "minimum_gap_metres": gap if tested else None,
                     "overlapping_surface_points_checked": tested})
    qualified = [row for row in rows if row["minimum_gap_metres"] is not None]
    return {"samples": rows, "minimum_gap_metres": min(row["minimum_gap_metres"] for row in qualified),
            "passed": bool(qualified) and all(row["minimum_gap_metres"] >= -.002 for row in qualified)}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--samples", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    report = check(json.loads(args.samples.read_text()))
    args.output.write_text(json.dumps(report, indent=2) + "\n")
    print(f"Mounted cape mesh clearance: {'PASS' if report['passed'] else 'FAIL'}; "
          f"{len(report['samples'])} samples; minimum {report['minimum_gap_metres'] * 1000:.2f} mm")
    raise SystemExit(0 if report["passed"] else 1)


if __name__ == "__main__":
    main()
