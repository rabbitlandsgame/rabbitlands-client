"""Centre fitted lower garments on the actual body surface, not the rest bone axis.

The regenerated bodies keep the canonical skeleton, but their calves curve
behind it. A bone-axis trouser fit can consequently miss an otherwise seated
boot by several centimetres. Measure both garments against the same transverse
body sections, preserve the soles and upper legs, and carry ornaments whole.
"""

from __future__ import annotations
from concurrent.futures import ProcessPoolExecutor, as_completed
import argparse
import copy
import hashlib
import json
from functools import lru_cache
from pathlib import Path
import numpy as np
import equipment_authoring as ea
import conform_equipment as ce
import torso_remap as torso
import limb_head_remap as limbs

ROOT = Path(__file__).resolve().parents[2]
LEVELS = np.linspace(0.105, 0.595, 50)
FIT_VERSION = 1


def smooth(value, low, high):
    t = np.clip((value - low) / (high - low), 0.0, 1.0)
    return t * t * (3.0 - 2.0 * t)


def sections(points, faces, levels):
    triangles = np.asarray(points)[np.asarray(faces).reshape(-1, 3)]
    values = np.full((len(levels), 2), np.nan)
    for row, y in enumerate(levels):
        cut = []
        crossing = triangles[
            (triangles[:, :, 1].min(1) < y) & (triangles[:, :, 1].max(1) > y)
        ]
        for a, b in [(0, 1), (1, 2), (2, 0)]:
            start, end = crossing[:, a], crossing[:, b]
            own = (start[:, 1] - y) * (end[:, 1] - y) < 0
            t = (y - start[own, 1]) / (end[own, 1] - start[own, 1])
            cut.extend((start[own] + t[:, None] * (end[own] - start[own]))[:, [0, 2]])
        if len(cut) >= 6:
            low, high = np.percentile(cut, [3, 97], axis=0)
            values[row] = (low + high) / 2
    return values


def body_sections(rig, side, levels):
    bones = [
        rig.joint_names.index(b + "_" + side) for b in ["thigh", "calf", "foot", "ball"]
    ]
    belongs = (rig.weights * np.isin(rig.joints, bones)).sum(1) > 0.35
    faces = rig.faces[belongs[rig.faces].all(1)]
    if rig.tail is not None:
        faces = faces[~rig.tail[faces].any(1)]
    return sections(rig.positions, faces, levels)


def field(points, faces, rig, region="legs"):
    labels = limbs.components(points, faces)
    maps = {}
    for side, sign in [("l", 1.0), ("r", -1.0)]:
        wanted = body_sections(rig, side, LEVELS * rig.fit_scale)
        if region == "boots":
            candidates = np.unique(labels[points[:, 0] * sign > 0])
            shell = max(
                candidates,
                key=lambda label: np.count_nonzero(
                    (labels == label) & (points[:, 0] * sign > 0)
                )
                * np.ptp(points[(labels == label) & (points[:, 0] * sign > 0), 1]),
            )
            own = (labels[faces] == shell).all(1) & (
                points[faces, 0].mean(1) * sign > 0
            )
            current = sections(points, faces[own], LEVELS * rig.fit_scale)
        else:
            # A hanging skirt panel can have more triangles than a trouser
            # tube. Follow substantial shells nearest the original shin axis
            # at each height; never pull a distant panel onto the skin.
            current = np.full_like(wanted, np.nan)
            distance = np.full(len(LEVELS), np.inf)
            axis = rig.origin("calf_" + side)[[0, 2]]
            for label in np.unique(labels[points[:, 0] * sign > 0]):
                own = (labels[faces] == label).all(1) & (
                    points[faces, 0].mean(1) * sign > 0
                )
                if own.sum() < 12:
                    continue
                center = sections(points, faces[own], LEVELS * rig.fit_scale)
                score = np.linalg.norm(center - axis, axis=1)
                use = (score < distance) & (score < 0.060 * rig.fit_scale)
                current[use] = center[use]
                distance[use] = score[use]
        valid = np.isfinite(current).all(1) & np.isfinite(wanted).all(1)
        if valid.sum() < 4:
            # Open skirt/greave panels have no complete shaft to measure.
            # Carry their authored offsets from the canonical fitting axis.
            current = np.tile(rig.origin("calf_" + side)[[0, 2]], (len(LEVELS), 1))
            valid = np.isfinite(wanted).all(1)
        difference = wanted - current
        shift = np.column_stack(
            [
                np.interp(LEVELS, LEVELS[valid], difference[valid, col])
                for col in range(2)
            ]
        )
        # A continuous translation preserves circumference, folds and seam
        # duplicates. Smooth the measured field rather than individual vertices.
        for _ in range(2):
            for col in range(2):
                shift[:, col] = np.convolve(
                    np.pad(shift[:, col], 1, mode="edge"),
                    [0.25, 0.5, 0.25],
                    mode="valid",
                )
        if np.max(np.linalg.norm(shift, axis=1)) > 0.15 * rig.fit_scale:
            raise ValueError("Ambiguous shaft measurement exceeds 150 mm")
        maps[side] = shift
    return maps


def apply(points, faces, maps, scale=1.0):
    points = np.asarray(points, dtype=float)
    out = points.copy()
    labels = limbs.components(points, faces)
    for side, sign in [("l", 1.0), ("r", -1.0)]:
        for label in np.unique(labels):
            member = labels == label
            rigid = np.ptp(points[member, 1]) < 0.10 * scale or member.sum() <= 64
            if rigid:
                # A buckle crossing x=0 still belongs to one leg. Translating
                # its two halves along different shafts can turn it inside out.
                left = points[member, 0].mean() >= 0.0
                if left != (side == "l"):
                    continue
                own = member
            else:
                own = member & (points[:, 0] * sign > 0)
            if not own.any():
                continue
            block = points[own]
            # Independent short buckles and plates translate whole. Long
            # connected cloth follows the smooth section field.
            y = np.full(len(block), block[:, 1].mean()) if rigid else block[:, 1]
            fade = smooth(y, 0.065 * scale, 0.120 * scale) * (
                1.0 - smooth(y, 0.50 * scale, 0.65 * scale)
            )
            move = (
                np.column_stack(
                    [
                        np.interp(y, LEVELS * scale, maps[side][:, col])
                        for col in range(2)
                    ]
                )
                * fade[:, None]
            )
            out[own, 0] += move[:, 0]
            out[own, 2] += move[:, 1]
    return out


def align(points, faces, rig, region="legs"):
    maps = field(points, faces, rig, region)
    result, safe = torso.constrain_deformation_orientation(
        points, apply(points, faces, maps, rig.fit_scale), faces, maximum_iterations=48
    )
    return result, {
        "name": "body_surface_shaft_centres",
        "maximumShift": {
            s: float(np.linalg.norm(v, axis=1).max()) for s, v in maps.items()
        },
    }


@lru_cache(maxsize=2)
def rig_for(sex):
    return ea.load_rig(
        ROOT / f"godot-client/assets/actors/native/races/luminous_{sex}.glb",
        ce.BODY_MESH,
    )


def revise(source, target, sex, region):
    d, b = ea.read_glb(source)
    if d["asset"].get("extras", {}).get("shaftFitVersion") == FIT_VERSION:
        return {"changedVertices": 0, "maximumMove": 0.0, "limitedVertices": 0}
    rig = rig_for(sex)
    art = []
    faces = []
    offset = 0
    for m in d["meshes"]:
        if m["name"].startswith("Generated"):
            continue
        for pr in m["primitives"]:
            p = ea.accessor_array(d, b, pr["attributes"]["POSITION"]).astype(float)
            f = ea.accessor_array(d, b, pr["indices"]).reshape(-1, 3)
            art.append(p)
            faces.append(f + offset)
            offset += len(p)
    maps = field(np.concatenate(art), np.concatenate(faces), rig, region)
    doc = copy.deepcopy(d)
    data = bytearray(b)
    maximum = 0.0
    changed = 0
    limited = 0
    seen = set()
    for mesh in doc["meshes"]:
        for pr in mesh["primitives"]:
            attrs = pr["attributes"]
            idx = attrs["POSITION"]
            if idx in seen:
                continue
            seen.add(idx)
            p = ea.accessor_array(doc, data, idx)
            f = ea.accessor_array(doc, data, pr["indices"]).reshape(-1, 3)
            before = p.astype(float).copy()
            after = apply(before, f, maps, rig.fit_scale)
            after, safe = torso.constrain_deformation_orientation(
                before, after, f, maximum_iterations=48
            )
            limited += safe["limitedVertices"]
            normal = ea.accessor_array(doc, data, attrs["NORMAL"])
            normal[:] = torso.transport_normals_across_deformation(
                before, after, normal, f
            )[0]
            p[:] = after
            spec = doc["accessors"][idx]
            spec["min"] = p.min(0).tolist()
            spec["max"] = p.max(0).tolist()
            delta = np.linalg.norm(after - before, axis=1)
            maximum = max(maximum, float(delta.max()))
            changed += int((delta > 1e-6).sum())
    writer = ea.EquipmentGLB(generator="Eloria equipment joint fit")
    writer.doc, writer.binary = doc, data
    doc["asset"].setdefault("extras", {})["shaftFitVersion"] = FIT_VERSION
    for image in doc.get("images", []):
        if "uri" in image:
            image["uri"] = (source.parent / image["uri"]).resolve().as_posix()
    target.parent.mkdir(parents=True, exist_ok=True)
    writer.write(target)
    return {
        "changedVertices": changed,
        "maximumMove": maximum,
        "limitedVertices": limited,
    }


def build_one(work):
    key, sex, relative, output = work
    import pack_canonical_equipment as pack

    relative, output = Path(relative), Path(output)
    source = ROOT / relative
    target = output / "raw" / sex / source.name
    expected = hashlib.sha256(source.read_bytes()).hexdigest()
    report = revise(source, target, sex, "legs" if key.startswith("4:") else "boots")
    if report["changedVertices"] == 0:
        return None
    pack.validate(target)
    pack.pack_glb(target, relative, output / "packed")
    return {
        "key": key,
        "sex": sex,
        "path": relative.as_posix(),
        "report": report,
        "expectedSHA256": expected,
        "candidateSHA256": hashlib.sha256(
            (output / "packed" / relative).read_bytes()
        ).hexdigest(),
    }


def install(output):
    records = json.loads((output / "manifest.json").read_text())
    for record in records:
        target = (ROOT / record["path"]).resolve()
        if not target.is_relative_to(ROOT):
            raise ValueError("Target escapes repository")
        if hashlib.sha256(target.read_bytes()).hexdigest() != record["expectedSHA256"]:
            raise ValueError("Installed equipment changed since candidate build")
        candidate = output / "packed" / record["path"]
        if (
            hashlib.sha256(candidate.read_bytes()).hexdigest()
            != record["candidateSHA256"]
        ):
            raise ValueError("Candidate changed since validation")
    for record in records:
        (ROOT / record["path"]).write_bytes(
            (output / "packed" / record["path"]).read_bytes()
        )
    print(f"Installed {len(records)} measured shaft fits")


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--output", type=Path, required=True)
    ap.add_argument("--pieces", default="all")
    ap.add_argument("--jobs", type=int, default=4)
    ap.add_argument("--install", action="store_true")
    args = ap.parse_args()
    args.output = args.output.resolve()
    if args.install:
        install(args.output)
        return
    registry = json.loads(
        (ROOT / "godot-client/data/actors/equipment.json").read_text()
    )
    chosen = None if args.pieces == "all" else set(args.pieces.split(","))
    args.output.mkdir(parents=True, exist_ok=True)
    work = []
    for key, model in registry["models"].items():
        if model.get("fitProfile") != "canonical" or not key.startswith(("4:", "6:")):
            continue
        if chosen is not None and key not in chosen:
            continue
        for sex in ["male", "female"]:
            variant = model["variants"]["canonical_human_" + sex]
            relative = Path("godot-client") / variant["scene"].removeprefix("res://")
            work.append((key, sex, relative.as_posix(), str(args.output)))
    records = []
    with ProcessPoolExecutor(max_workers=args.jobs) as pool:
        futures = {pool.submit(build_one, w): w for w in work}
        for count, future in enumerate(as_completed(futures), 1):
            try:
                record = future.result()
            except Exception as error:
                raise RuntimeError(
                    f"Failed shaft fit: {futures[future][:3]}"
                ) from error
            if record is not None:
                records.append(record)
                variant = registry["models"][record["key"]]["variants"][
                    "canonical_human_" + record["sex"]
                ]
                variant["scene"] = (
                    (args.output / "packed" / record["path"]).resolve().as_posix()
                )
            if count % 16 == 0:
                print(f"Shaft fits: {count}/{len(work)}", flush=True)
    records.sort(key=lambda r: r["path"])
    (args.output / "equipment.json").write_text(json.dumps(registry, indent=2) + "\n")
    (args.output / "manifest.json").write_text(json.dumps(records, indent=2) + "\n")
    print(f"Validated {len(records)} fitted variants", flush=True)


if __name__ == "__main__":
    main()
