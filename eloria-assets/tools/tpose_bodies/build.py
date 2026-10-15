"""Fit an existing T-pose derivative to the shared Rest_Pose; never export into a client.

Uses fix_limbs' minimal per-segment rotation about each joint, with axial length
fitting and source skin weights blending the transforms. Mesh topology/UVs stay
unchanged. The whole head and each hand follow their proximal joint rigidly.
"""

from __future__ import annotations
import argparse
import copy
import json
from pathlib import Path
import sys
import numpy as np
from audit import HERE, WORKTREE, digest, reference_pose, g
import fix_limbs as limb
import split_reference
import tail

sys.path.insert(0, str(HERE.parent))
import split_race_surfaces as split

MAPPING = {
    "Hips": "pelvis",
    "Spine02": "spine_01",
    "Spine01": "spine_02",
    "Spine": "spine_03",
    "neck": "neck_01",
    "Head": "Head",
    "head_end": "Head",
    "headfront": "Head",
}
for side, word in (("l", "Left"), ("r", "Right")):
    MAPPING.update(
        {
            word + a: b + "_" + side
            for a, b in (
                ("Shoulder", "clavicle"),
                ("Arm", "upperarm"),
                ("ForeArm", "lowerarm"),
                ("Hand", "hand"),
                ("UpLeg", "thigh"),
                ("Leg", "calf"),
                ("Foot", "foot"),
                ("ToeBase", "ball"),
            )
        }
    )
CHILD = {
    "pelvis": "spine_01",
    "spine_01": "spine_02",
    "spine_02": "spine_03",
    "spine_03": "neck_01",
    "neck_01": "Head",
}
for side in ("l", "r"):
    CHILD.update(
        {
            a + "_" + side: b + "_" + side
            for a, b in (
                ("clavicle", "upperarm"),
                ("upperarm", "lowerarm"),
                ("lowerarm", "hand"),
                ("thigh", "calf"),
                ("calf", "foot"),
                ("foot", "ball"),
            )
        }
    )


def append(d, blob, values, ctype, atype, target=None):
    # Existing splitter includes the BIN header in its buffer argument.
    return split.append_accessor(d, blob, values, ctype, atype, target)


def canonical(library, template):
    ref, _, _ = reference_pose(library)
    old, _ = g.read(template)
    names = [old["nodes"][j]["name"] for j in old["skins"][0]["joints"]]
    if len(names) != 77 or len(set(names)) != 77:
        raise ValueError("The shipped 77-joint contract changed")
    rp = g.parents_of(ref)
    op = g.parents_of(old)
    byname = {
        n["name"] if n["name"] != "head" else "Head": i
        for i, n in enumerate(ref["nodes"])
    }
    oldnames = {n.get("name"): i for i, n in enumerate(old["nodes"])}
    nodes = []
    for name in names:
        src = ref if name in byname else old
        idx = byname[name] if name in byname else oldnames[name]
        n = {
            k: copy.deepcopy(v)
            for k, v in src["nodes"][idx].items()
            if k in ("translation", "rotation", "scale")
        }
        if "scale" in n and np.max(np.abs(np.array(n["scale"]) - 1)) < 1e-5:
            n.pop("scale")  # clear floating-point export noise, never artistic scaling
        n["name"] = name
        if name not in byname and not name.startswith("cape_"):
            raise ValueError("Missing library joint: " + name)
        par = (rp if name in byname else op).get(idx)
        pn = src["nodes"][par]["name"] if par is not None else None
        if pn == "head":
            pn = "Head"
        if pn in names:
            n["_parent"] = names.index(pn)
        elif name != "root":
            raise ValueError("Unknown parent for " + name)
        nodes.append(n)
    for i, n in enumerate(nodes):
        if "_parent" in n:
            nodes[n.pop("_parent")].setdefault("children", []).append(i)
    return names, nodes


def fit(source, library, template, out, preserve_source_shape=False):
    out = out.resolve()
    if "godot-client" in out.parts or "races" in out.parts or out == source.resolve():
        raise ValueError(
            "Build output must be in scratch out/, never a client asset directory"
        )
    d, blob = split.read_glb(source)
    original = copy.deepcopy(d)
    names, nodes = canonical(library, template)
    tw = g.globals_of({"nodes": nodes})
    target = {name: tw[i][:3, 3] for i, name in enumerate(names)}
    skin = d["skins"][0]
    sn = [d["nodes"][j]["name"] for j in skin["joints"]]
    if set(sn) - set(MAPPING):
        raise ValueError("Unmapped source bones: " + str(set(sn) - set(MAPPING)))
    # Inverse binds describe the geometry's actual coordinate space. Meshy's
    # mesh-node scale is 0.01 despite positions/binds being in metres.
    ib = (
        split.accessor_array(d, blob, skin["inverseBindMatrices"])
        .reshape(-1, 4, 4)
        .transpose(0, 2, 1)
    )
    src = {
        MAPPING[n]: np.linalg.inv(ib[i])[:3, 3]
        for i, n in enumerate(sn)
        if n not in ("head_end", "headfront")
    }
    repaired_feet = False
    if (
        source.name.startswith("ssarathi_")
        and max(src["foot_l"][1], src["foot_r"][1]) > 0.16
    ):
        # The tail reaches 107 mm below the source soles. Its ankles really
        # are around Y=.21; lowering them to .105 mistakes the tail's minimum
        # for the floor under the feet. Keep those physical ankle anchors and
        # repair only the auto-rig's toe locations (one was on the tail).
        repaired_feet = True
        for side in ("l", "r"):
            src["ball_" + side] = src["foot_" + side] + np.array([0.0, -0.075, 0.11])
    mats = {}
    rots = {}
    scales = {}
    for name in src:
        child = CHILD.get(name)
        a = src[name]
        ta = target[name]
        if child:
            axis = src[child] - a
            tax = target[child] - ta
            rot = limb.minimal_rotation(axis, tax)
            s = np.linalg.norm(tax) / np.linalg.norm(axis)
            unit = axis / np.linalg.norm(axis)
            linear = rot @ (np.eye(3) + (s - 1) * np.outer(unit, unit))
        else:
            # Whole parts: do not hunt for, cut, or blend a skin-shell boundary.
            prior = (
                "lowerarm_" + name[-1]
                if name.startswith("hand_")
                else "foot_" + name[-1] if name.startswith("ball_") else None
            )
            rot = rots.get(prior, np.eye(3))
            s = 1.0
            linear = rot
        rots[name] = rot
        scales[name] = float(s)
        m = np.eye(4)
        m[:3, :3] = linear
        m[:3, 3] = ta - linear @ a
        mats[name] = m
    # Spine labels do not mark equivalent anatomy in Meshy's evenly spaced
    # spine and the library's short lumbar / long upper-chest chain. Fitting
    # each label independently drops the breast/ribcage and adds projection.
    # Preserve the complete torso between physical pelvis/shoulder anchors.
    torso_names = ("pelvis", "spine_01", "spine_02", "spine_03")
    a = src["pelvis"]
    z = (src["upperarm_l"] + src["upperarm_r"]) * 0.5
    ta = target["pelvis"]
    tz = (target["upperarm_l"] + target["upperarm_r"]) * 0.5
    if preserve_source_shape:
        # Meshy's Hips lies ABOVE its thigh joints; the canonical pelvis lies
        # BELOW them. Matching those labels compresses and inverts the crotch.
        # Physical hip centres give torso and legs the same lower anchor.
        a = (src["thigh_l"] + src["thigh_r"]) * 0.5
        ta = (target["thigh_l"] + target["thigh_r"]) * 0.5
    axis = z - a
    tax = tz - ta
    unit = axis / np.linalg.norm(axis)
    scale = np.linalg.norm(tax) / np.linalg.norm(axis)
    linear = limb.minimal_rotation(axis, tax) @ (
        np.eye(3) + (scale - 1) * np.outer(unit, unit)
    )
    torso = np.eye(4)
    torso[:3, :3] = linear
    torso[:3, 3] = ta - linear @ a
    for name in torso_names:
        mats[name] = torso.copy()
    # Reassign each source spine contribution by where its anchor now lies,
    # retaining a smooth blend rather than binding the relocated chest low.
    transfer = np.zeros((len(sn), len(names)))
    heights = np.array([target[n][1] for n in torso_names])
    for si, name in enumerate(sn):
        mapped = MAPPING[name]
        if preserve_source_shape and mapped == 'pelvis':
            # The fit uses physical hip centres, but Hips still drives the
            # pelvis in motion. Its differently placed donor origin must not
            # rebind all waistband cloth to a lumbar joint.
            transfer[si, names.index('pelvis')] = 1
        elif mapped in torso_names:
            y = (torso @ np.r_[src[mapped], 1])[1]
            upper = int(np.clip(np.searchsorted(heights, y), 1, len(heights) - 1))
            lower = upper - 1
            f = float(
                np.clip((y - heights[lower]) / (heights[upper] - heights[lower]), 0, 1)
            )
            transfer[si, names.index(torso_names[lower])] = 1 - f
            transfer[si, names.index(torso_names[upper])] = f
        else:
            transfer[si, names.index(mapped)] = 1
    d["nodes"] = nodes + [
        {"name": "BodyRoot", "children": [0, len(nodes) + 1]},
        {"name": "unsplit", "mesh": 0, "skin": 0},
    ]
    d["scenes"] = [{"nodes": [len(nodes)]}]
    d["scene"] = 0
    d.pop("animations", None)
    # Every unique attribute set is fitted once, never once per split surface.
    seen = set()
    report = {
        "source_sha256": digest(source),
        "preserve_source_shape": preserve_source_shape,
        "library_sha256": digest(library),
        "template_sha256": digest(template),
        "segment_axial_scale": scales,
        "groups": [],
    }
    for mesh in d["meshes"]:
        for p in mesh["primitives"]:
            attrs = p["attributes"]
            key = tuple(sorted(attrs.items()))
            if key in seen:
                continue
            seen.add(key)
            v = split.accessor_array(d, blob, attrs["POSITION"])
            normal = split.accessor_array(d, blob, attrs["NORMAL"])
            alpha = np.zeros(len(v))
            if source.name.startswith("ssarathi_"):
                uv = split.accessor_array(d, blob, attrs["TEXCOORD_0"])
                faces = (
                    split.accessor_array(d, blob, p["indices"])
                    .astype(int)
                    .reshape(-1, 3)
                )
                alpha, report["tail"] = tail.feather(d, blob, p, v, uv, faces, src)
            jj = split.accessor_array(d, blob, attrs["JOINTS_0"]).astype(int)
            ww = split.accessor_array(d, blob, attrs["WEIGHTS_0"])
            ww /= ww.sum(1, keepdims=True)
            if repaired_feet:
                # Replace the cuff-to-ankle weight jump with a continuous anatomical
                # blend. Process unique attributes once; tail weights are handled
                # by the separate feather below.
                source_dense = np.zeros((len(v), len(sn)))
                for k in range(4):
                    np.add.at(source_dense, (np.arange(len(v)), jj[:, k]), ww[:, k])
                for side in ("l", "r"):
                    ci = next(
                        i for i, n in enumerate(sn) if MAPPING[n] == "calf_" + side
                    )
                    fi = next(
                        i for i, n in enumerate(sn) if MAPPING[n] == "foot_" + side
                    )
                    bi = next(
                        i for i, n in enumerate(sn) if MAPPING[n] == "ball_" + side
                    )
                    mask = (v[:, 1] < src["calf_" + side][1] - 0.05) & (alpha == 0)
                    total = source_dense[:, [ci, fi, bi]].sum(1)
                    mix = limb.smoothstep(
                        v[:, 1],
                        src["foot_" + side][1] + 0.01,
                        src["foot_" + side][1] + 0.14,
                    )
                    source_dense[mask, ci] = total[mask] * mix[mask]
                    source_dense[mask, fi] = total[mask] * (1 - mix[mask])
                    source_dense[mask, bi] = 0
                jj, ww = limb.sparse_weights(source_dense)
                jj = jj.astype(int)
                report["foot_anchor_repair"] = (
                    "Physical source ankle anchors retained above elevated soles; toes aligned with plantar geometry; calf/foot weights feathered over 130mm"
                )
            transforms = np.array([mats[MAPPING[n]] for n in sn])
            normal_mats = np.linalg.inv(transforms[:, :3, :3]).transpose(0, 2, 1)
            vout = np.zeros_like(v)
            nout = np.zeros_like(normal)
            for k in range(jj.shape[1]):
                mm = transforms[jj[:, k]]
                vout += (np.einsum("nij,nj->ni", mm[:, :3, :3], v) + mm[:, :3, 3]) * ww[
                    :, k, None
                ]
                nout += (
                    np.einsum("nij,nj->ni", normal_mats[jj[:, k]], normal)
                    * ww[:, k, None]
                )
            # Narrow the upper sleeves around their actual joint-to-joint axes.
            # The user's EL reference has relaxed shoulders, not inflated deltoids.
            # Bake this into vertices; no skeleton/rest-scale compensation.
            for side in (() if preserve_source_shape else ("l", "r")):
                chain = [
                    i
                    for i, n in enumerate(sn)
                    if MAPPING[n]
                    in ("clavicle_" + side, "upperarm_" + side, "lowerarm_" + side)
                ]
                strength = (ww * np.isin(jj, chain)).sum(1)
                a = target["upperarm_" + side]
                z = target["lowerarm_" + side]
                axis = z - a
                length = np.linalg.norm(axis)
                axis /= length
                along = (vout - a) @ axis
                radial = vout - a - np.outer(along, axis)
                radius = np.linalg.norm(radial, axis=1)
                fade = (
                    1 - limb.smoothstep(along, length * 0.70, length * 1.15)
                ) * limb.smoothstep(along, -0.10, -0.025)
                scale = 1 - 0.28 * strength * fade
                vout -= radial * (1 - scale[:, None])
                # Slim the sleeve's underside at the axilla. Limit this to the
                # arm root and upper side of the ribcage so the breast/waist fit
                # stays unchanged. The source faces and UV seams remain intact.
                radial = vout - a - np.outer((vout - a) @ axis, axis)
                depth = -radial[:, 1]
                root_fade = limb.smoothstep(along, -0.07, -0.015) * (
                    1 - limb.smoothstep(along, 0.08, 0.17)
                )
                underside = limb.smoothstep(depth, 0.005, 0.025) * (
                    1 - limb.smoothstep(depth, 0.10, 0.16)
                )
                slim = 0.50 * root_fade * underside * np.clip(strength / 0.30, 0, 1)
                vout -= radial * slim[:, None]
            if alpha.any():
                rigid, lift_report = tail.lifted_shape(
                    v, alpha, src["pelvis"], target["pelvis"], library, nodes
                )
                report["tail"].update(lift_report)
                vout = vout * (1 - alpha[:, None]) + rigid * alpha[:, None]
            # Seat the authored soles at ground level in the canonical bind. This
            # is a vertex correction, faded out below the calf, not a root offset.
            floor = float(vout[alpha == 0, 1].min())
            if floor < 0:
                vout[:, 1] += -floor * (1 - limb.smoothstep(vout[:, 1], 0, 0.24))
            nout /= np.maximum(np.linalg.norm(nout, axis=1, keepdims=True), 1e-12)
            # Reuse the prior pipeline's position-aware shading repair before the
            # split. In-engine normal-grow opens the exporter's split facet edges
            # unless their shading normals agree. Indices/positions stay intact.
            fi = split.accessor_array(d, blob, p["indices"]).astype(int).reshape(-1)
            if not preserve_source_shape:
                nout = split_reference.smooth_normals(vout, fi)
            dense = np.zeros((len(v), len(names)))
            for k in range(jj.shape[1]):
                dense += transfer[jj[:, k]] * ww[:, k, None]
            if repaired_feet:
                # The source's misplaced toe bones could not supply usable
                # weights. Rebuild the forefoot hinge on the canonical ball,
                # so toe-off rolls the toes instead of driving a rigid boot
                # through the floor during a full walking cycle.
                for side in ("l", "r"):
                    foot_index = names.index("foot_" + side)
                    ball_index = names.index("ball_" + side)
                    hinge = target["ball_" + side][2]
                    blend = limb.smoothstep(vout[:, 2], hinge - 0.035, hinge + 0.035)
                    blend *= 1 - limb.smoothstep(vout[:, 1], 0.08, 0.16)
                    amount = dense[:, foot_index] * blend
                    dense[:, foot_index] -= amount
                    dense[:, ball_index] += amount
                    # Fit the source's long clawed forefoot to the canonical
                    # ball-to-leaf segment, just as the other limb segments.
                    # The original bad ToeBase cannot supply this endpoint.
                    region = (dense[:, foot_index] + dense[:, ball_index] > 0.5) & (
                        vout[:, 1] < 0.20
                    )
                    span = float(vout[region, 2].max() - hinge)
                    target_span = target["ball_leaf_" + side][2] + 0.006 - hinge
                    toes = region & (vout[:, 2] > hinge)
                    vout[toes, 2] = hinge + (vout[toes, 2] - hinge) * min(
                        1.0, target_span / span
                    )
                    vout[toes, 1] += 0.012 * limb.smoothstep(
                        (vout[toes, 2] - hinge) / target_span, 0.2, 1.0
                    )
                nout = split_reference.smooth_normals(vout, fi)
                report["forefoot_fit"] = (
                    "Canonical ball-to-leaf length, feathered ball weights, 12mm toe-tip clearance"
                )
            if alpha.any():
                dense *= 1 - alpha[:, None]
                dense[:, names.index("pelvis")] += alpha
            newj, neww = limb.sparse_weights(dense)
            attrs["POSITION"] = append(d, blob, vout.astype("<f4"), 5126, "VEC3", 34962)
            attrs["NORMAL"] = append(d, blob, nout.astype("<f4"), 5126, "VEC3", 34962)
            attrs["JOINTS_0"] = append(d, blob, newj.astype("<u2"), 5123, "VEC4", 34962)
            attrs["WEIGHTS_0"] = append(
                d, blob, neww.astype("<f4"), 5126, "VEC4", 34962
            )
            report["groups"].append(
                {
                    "vertices": len(v),
                    "bounds": [vout.min(0).tolist(), vout.max(0).tolist()],
                }
            )
    inverses = (
        np.linalg.inv(np.array([tw[i] for i in range(len(names))]))
        .transpose(0, 2, 1)
        .reshape(-1, 16)
    )
    d["skins"] = [
        {
            "name": "CanonicalPlayerRig",
            "joints": list(range(len(names))),
            "skeleton": 0,
            "inverseBindMatrices": append(
                d, blob, inverses.astype("<f4"), 5126, "MAT4"
            ),
        }
    ]
    d.setdefault("asset", {})[
        "generator"
    ] = "Eloria T-pose bodies: canonical Rest_Pose fit"
    d["asset"]["extras"] = {
        "source": source.name,
        "sourceSHA256": digest(source),
        "canonicalLibrarySHA256": digest(library),
    }
    out.parent.mkdir(parents=True, exist_ok=True)
    # Compact through existing payload-only helper; no re-meshing or vertex welding.
    d, payload = g.compact(d, bytes(blob[8:]))
    g.write(out, d, payload)
    out.with_suffix(".fit.json").write_text(json.dumps(report, indent=2) + "\n")
    return report


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("source", type=Path)
    ap.add_argument("out", type=Path)
    ap.add_argument("--library", type=Path, required=True)
    ap.add_argument("--template", type=Path, required=True)
    ap.add_argument("--preserve-source-shape", action="store_true",
                    help="Keep source sleeve shape and authored normals during rig fitting")
    a = ap.parse_args()
    print(json.dumps(fit(a.source, a.library, a.template, a.out, a.preserve_source_shape), indent=2))
