"""Independent fixed-grid coverage measurements for generated armour.

The original body remains the absolute proud-cell reference. Replacement-body
visibility is measured separately, only within the declared coverage region.
Open visors and circlets intentionally reveal the face and are not body masks.
"""

import argparse
import json
from pathlib import Path
import numpy as np
import conform_equipment as ce
import equipment_authoring as ea
import import_generated_equipment as batch
from audit_torso_remap import depth

GRIDS = {3: (0.16, 1.56, 1.89), 4: (0.29, 0.20, 1.09), 6: (0.29, -0.01, 0.47)}


def audit(directory, output, before=None, slugs=None):
    rig = ea.load_rig(ce.RACES / "luminous_male.glb", ce.BODY_MESH)
    grids = {}
    for part, (width, low, high) in GRIDS.items():
        x, y = np.meshgrid(np.linspace(-width, width, 101), np.linspace(low, high, 81))
        xy = np.column_stack((x.ravel(), y.ravel()))
        grids[part] = xy, depth(rig.positions, rig.faces, xy)
    body_centers = rig.positions[rig.faces].mean(axis=1)
    records = {}
    baseline = json.loads(Path(before).read_text()) if before else {}
    for piece in batch.roster():
        if piece.part not in GRIDS:
            continue
        if slugs and piece.slug not in slugs:
            continue
        path = directory / (piece.slug + ".glb")
        doc, binary = ea.read_glb(path)
        vertices, triangles = [], []
        count = 0
        for mesh in doc["meshes"]:
            if mesh.get("name") in (
                "GeneratedBootBackingWithLegs",
                "GeneratedLegBackingWithBoots",
            ):
                continue  # this audit wears each piece alone, with default pants
            for primitive in mesh["primitives"]:
                points = ea.accessor_array(
                    doc, binary, primitive["attributes"]["POSITION"]
                )
                vertices.append(points)
                triangles.append(
                    ea.accessor_array(doc, binary, primitive["indices"]).reshape(-1, 3)
                    + count
                )
                count += len(points)
        points = np.vstack(vertices)
        if piece.part == 3:
            points += ce.socket_origin(rig, 3)
        xy, body = grids[piece.part]
        armour = depth(points, np.vstack(triangles), xy)
        hits = np.isfinite(body)
        regions = [m.get("extras", {}).get("bodyCover") for m in doc["meshes"]]
        regions = [r for r in regions if r]
        covered = np.zeros(len(body_centers), dtype=bool)
        owned = np.zeros(len(xy), dtype=bool)
        for low, high, width in regions:
            covered |= (
                (body_centers[:, 1] > low)
                & (body_centers[:, 1] < high)
                & (np.abs(body_centers[:, 0]) < width)
            )
            owned |= (xy[:, 1] > low) & (xy[:, 1] < high) & (np.abs(xy[:, 0]) < width)
        remainder = depth(rig.positions, rig.faces[~covered], xy) if regions else None
        record = dict(
            part=piece.part,
            proud_cells=int((hits & (armour >= body)).sum()),
            body_cells=int(hits.sum()),
            silhouette=float(np.isfinite(armour[hits]).mean()),
            bounds=[points.min(axis=0).tolist(), points.max(axis=0).tolist()],
            body_cover=regions,
        )
        if regions:
            record["remaining_body_cells"] = int(
                (
                    hits & owned & np.isfinite(remainder) & (remainder > armour + 1e-5)
                ).sum()
            )
        if piece.slug in baseline:
            record["before_proud_cells"] = baseline[piece.slug]["proud_cells"]
        records[piece.slug] = record
        print(
            piece.slug,
            record["proud_cells"],
            record.get("remaining_body_cells"),
            flush=True,
        )
        summaries = {}
        for part in GRIDS:
            group = [v for v in records.values() if v["part"] == part]
            if group:
                summaries[str(part)] = dict(
                    pieces=len(group),
                    proud_cells=sum(v["proud_cells"] for v in group),
                    before_proud_cells=sum(
                        v.get("before_proud_cells", 0) for v in group
                    ),
                    remaining_body_cells=(
                        sum(v.get("remaining_body_cells", 0) for v in group)
                        if any(v["body_cover"] for v in group)
                        else None
                    ),
                )
        output.write_text(
            json.dumps(
                dict(
                    measurement={
                        "view": "orthographic front, unmasked rest body reference",
                        "grids": GRIDS,
                        "resolution": [101, 81],
                        "limitations": "Front rest view; open faces are intentional. Use complete-set, side and posed renders as well.",
                    },
                    summary=summaries,
                    pieces=records,
                ),
                indent=2,
            )
            + "\n"
        )
    print(summaries, flush=True)


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__)
    # The Human male fits; the old-male base scenes were deleted in P7 (2026-10).
    ap.add_argument("--directory", type=Path, default=batch.EQUIPMENT / "variants" / "human_male")
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--before", type=Path)
    ap.add_argument("--piece", action="append", default=[])
    args = ap.parse_args()
    audit(args.directory, args.out, args.before, args.piece)
