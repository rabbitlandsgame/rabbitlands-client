"""Retarget original torso artwork before fitting it to the wearer.

The design has an upright trunk and hanging arms. Infer a source arm frame
from each cuff, map those frames to the rig, and move welded plate islands
whole. The frontal trunk scale seats the design's waist at the pelvis rather
than squeezing its skirt, waist, chest and collar into one short torso span.
Short shoulder connections remain; fused sleeve-to-flank bridges are opened. A skinned backing replaces
the default race clothing through TorsoBodyCover in the client.

conform_equipment supplies file/topology/ray helpers only; none of its legacy
seat, repose, sleeve-unsquash or trunk-correction passes run on this path.
"""
from __future__ import annotations

import argparse
import json
from io import BytesIO
from pathlib import Path

import numpy as np
from PIL import Image

import equipment_authoring as ea
import conform_equipment as io

# Art-directed collar height, requested for the three reviewed designs.
# Keys name the original input, so isolated QA builds and shipped builds agree.
COLLAR_LIFT = {
    'Eight_legendary_hero_armor_designs__r01_c01.glb': .045,
    'Eight_leather_ranger_torso_designs__r02_c01.glb': .045,
    'Amberwood_Woodland_Armor_Concept_Sheet__r01_c04.glb': .045,
}


def rotation_between(a, b):
    a, b = a / np.linalg.norm(a), b / np.linalg.norm(b)
    cross = np.cross(a, b)
    cosine = float(a @ b)
    if np.linalg.norm(cross) < 1e-8:
        return np.eye(3)
    skew = np.array([[0, -cross[2], cross[1]],
                     [cross[2], 0, -cross[0]],
                     [-cross[1], cross[0], 0]])
    return np.eye(3) + skew + skew @ skew / (1 + cosine)


def source_skeleton(points):
    height = np.ptp(points[:, 1])
    top = float(points[:, 1].max())
    middle_x = float((points[:, 0].min() + points[:, 0].max()) / 2)
    result = {}
    for side, sign in [('l', 1.), ('r', -1.)]:
        shoulder = np.array([middle_x + sign * .23 * height,
                             top - .17 * height, -.04 * height])
        distal = points[((points[:, 0] - middle_x) * sign > .28 * height)
                        & (points[:, 1] < top - .35 * height)]
        if len(distal) > 12:
            low = np.percentile(distal[:, 1], 15)
            wrist = np.median(distal[distal[:, 1] <= low], axis=0)
            # The front lip of an oblique cuff reaches lower than its rear.
            # Measure depth over the whole sleeve, not that biased lip.
            wrist[2] = np.percentile(distal[:, 2], [2, 98]).mean()
        else:
            wrist = shoulder + np.array([sign * .14, -.70, .06]) * height
        result[side] = (shoulder, wrist)
    return result


def source_seam_boundaries(points, triangles):
    """Locate a stable trunk wall below each source armpit.

    A hanging sleeve can fuse to the coat at upper chest height. Descend until
    at least three depth probes agree on a narrow trunk enclosure; ignore rays
    that reach the outside of a sleeve or strike a central wrap/ornament.
    Only the part boundary changes. No source vertex is scaled by this profile.
    """
    height = np.ptp(points[:, 1])
    top = points[:, 1].max()
    mesh = points[triangles]
    result = {}
    for side, sign in [('l', 1.), ('r', -1.)]:
        value = .245  # Preserve the wider source trunk if enclosure is ambiguous.
        measured_y = None
        for level in np.arange(.30, .501, .01):
            y = top - level * height
            hits = np.array([io.cast(np.array([0., y, z * height]),
                                     np.array([sign, 0., 0.]), mesh)[0] / height
                             for z in [-.06, -.03, 0., .03, .06]])
            wall = hits[(hits > .14) & (hits < .265)]
            if len(wall) >= 3 and np.ptp(wall) < .035:
                value = float(np.clip(np.percentile(wall, 90), .215, .245))
                measured_y = float(y)
                break
        result[side] = {'fraction': value, 'sourceY': measured_y}
    return result


def drop_cut_fragments(points, triangles, keep, source_labels, fit_scale):
    """Discard small debris severed from a source shell by opening a fused seam.

    Original independent ornaments are retained, including intentional floating
    pieces. Only a new fragment of a still-large source shell is eligible, and
    it must stand at least 40 mm clear of the rest of the fitted garment.
    """
    from scipy.spatial import cKDTree
    faces = triangles[keep]
    if not len(faces):
        return keep, 0
    canon, edges, count = io._weld(points, faces)
    labels = io._components(edges, count)[canon]
    used = np.unique(faces)
    components = {label: used[labels[used] == label] for label in np.unique(labels[used])}
    large_parents = set()
    for own in components.values():
        if len(own) > 60:
            large_parents.update(source_labels[own])
    dropped = []
    for label, own in components.items():
        if len(own) > 60 or not set(source_labels[own]).issubset(large_parents):
            continue
        others = used[labels[used] != label]
        if len(others) and cKDTree(points[others]).query(points[own])[0].min() > .04 * fit_scale:
            dropped.append(label)
    if dropped:
        keep = keep & ~np.isin(labels[triangles], dropped).any(axis=1)
    return keep, len(dropped)


def long_sleeve_island(block, centroid, root, wrist, height):
    """Recognize a detached upper sleeve whose inner wall lowers its mean X.

    The arm-axis distance and vertical span distinguish it from skirt plates.
    Near-mirrored sleeves must not attach to different bones because their
    source centroids straddle a fixed lateral threshold by a fraction of a mm.
    """
    axis = wrist - root
    travel = np.clip((centroid-root) @ axis / (axis @ axis), 0., 1.)
    distance = np.linalg.norm(centroid-root-travel*axis)
    return (abs(centroid[0]) > .23*height and np.ptp(block[:, 1]) > .30*height
            and block[:, 1].max() > root[1]-.10*height and distance < .08*height)


def remap(points, triangles, rig, collar_lift=0., parts_out=None):
    canon, edges, count = io._weld(points, triangles)
    labels = io._components(edges, count)[canon]
    source = source_skeleton(points)
    seams = source_seam_boundaries(points, triangles)
    source_height = np.ptp(points[:, 1])
    source_top = float(points[:, 1].max())
    shoulder_y = source_top - .17 * source_height
    # In these concept sheets the shoulder and waist landmarks are 53% of
    # the drawing height apart. Seat those at the arm root and pelvis;
    # decorations below the belt remain below it instead of shortening the chest.
    waist = rig.origin('spine_01')[1] + .010 * rig.fit_scale
    scale = (rig.origin('upperarm_l')[1] - waist) / (.53 * source_height)
    centre = np.array([0., shoulder_y, -.02 * source_height])
    target = np.array([0., rig.origin('upperarm_l')[1], -.035 * rig.fit_scale])
    trunk = (points - centre) * np.array([scale, scale, .8 * scale]) + target
    out = trunk.copy()
    arm_share = np.zeros((len(points), 2))
    cap_side = np.full(len(points), -1, dtype=int)
    reports = {}
    for col, (side, sign) in enumerate([('l', 1.), ('r', -1.)]):
        root, wrist = source[side]
        target_root = rig.origin('upperarm_' + side)
        target_wrist = rig.origin('hand_' + side)
        source_axis = wrist - root
        target_axis = target_wrist - target_root
        limb_scale = np.linalg.norm(target_axis) / np.linalg.norm(source_axis)
        turn = rotation_between(source_axis, target_axis)
        arm = (points - root) @ turn.T * limb_scale + target_root
        cap = (points - root) * limb_scale + target_root
        caps = tubes = 0
        for label in np.unique(labels):
            own = labels == label
            block = points[own]
            centroid = np.unique(np.round(block, 5), axis=0).mean(axis=0)
            spanning = block[:, 0].min() < -.075 * source_height and block[:, 0].max() > .075 * source_height
            if spanning:
                if np.max(np.abs(block[:, 0])) < .30 * source_height:
                    continue
                # A sewn sleeve can share the coat's mesh.  Blend only that
                # seam, on welded positions, never across independent plates.
                travel = np.clip((block - root) @ source_axis / (source_axis @ source_axis), 0., 1.)
                axis_point = root + travel[:, None] * source_axis
                distance = np.linalg.norm(block - axis_point, axis=1) / source_height
                blend = np.clip((.18 - distance) / .035, 0., 1.)
                # A hanging sleeve can touch the coat down its entire flank.
                # The medial strip belongs to the trunk, even when it lies
                # within the broad sleeve enclosure. Use the source's lateral
                # arm/coat seam, tapering into the shoulder. Measure each
                # original trunk: a universal .245 leaves Militia sleeve strips
                # on the flank, while .215 cuts into the wider Sashwrap chest.
                # Keep the central skirt inside the trunk assignment.
                seam_x = np.interp(block[:, 1],
                    [shoulder_y - .20 * source_height, shoulder_y], [seams[side]['fraction'], .205])
                blend *= np.clip((block[:, 0] * sign / source_height - seam_x) / .025, 0., 1.)
                upper = np.clip((block[:, 1] - shoulder_y + .22 * source_height)
                                / (.10 * source_height), 0., 1.)
                chest_edge = np.clip((block[:, 0] * sign / source_height - .19) / .06, 0., 1.)
                blend *= 1 - upper * (1 - chest_edge)
                blend *= np.clip((source_top - block[:, 1]) / (.20 * source_height), 0., 1.)
                blend = blend * blend * (3 - 2 * blend)
                blend = (blend >= .5).astype(float)
                out[own] += (arm[own] - trunk[own]) * blend[:, None]
                arm_share[own, col] = blend
                continue
            if centroid[0] * sign < 0:
                continue
            if centroid[0] * sign < .17 * source_height:
                continue
            crest = (centroid[1] > shoulder_y - .11 * source_height
                     and block[:, 1].max() > shoulder_y + .02 * source_height)
            if crest:
                out[own] = cap[own]
                cap_side[own] = col
                caps += 1
            elif (centroid[0] * sign > .25 * source_height
                  or long_sleeve_island(block, centroid, root, wrist, source_height)):
                out[own] = arm[own]
                arm_share[own, col] = 1.
                tubes += 1
        reports[side] = {'sourceShoulder': root.tolist(), 'sourceWrist': wrist.tolist(),
                         'scale': float(limb_scale), 'caps': caps, 'tubes': tubes}
        own = cap_side == col
        if own.any():
            out[own, 0] += sign * .025 * rig.fit_scale
            block = out[own]
            skin = rig._region(list(ea.TORSO_BONES) + ['upperarm_' + side])
            near = skin[(skin[:, 0] * sign > .10 * rig.fit_scale)
                        & (skin[:, 0] * sign < .26 * rig.fit_scale)
                        & (skin[:, 1] > 1.38 * rig.fit_scale)]
            if len(near) > 8:
                have_lo, have_hi = np.percentile(block[:, 2], [2, 98])
                want_lo, want_hi = np.percentile(near[:, 2], [2, 98]) + np.array([-.015, .015])
                depth_scale = max(1., (want_hi - want_lo) / max(have_hi - have_lo, .04))
                out[own, 2] = ((block[:, 2] - (have_hi + have_lo)/2) * depth_scale
                               + (want_hi + want_lo)/2)
                out[own, 1] += max(0., target_root[1] + .025 * rig.fit_scale - float(np.median(block[:, 1])))
    trunk_share = (1 - arm_share.sum(axis=1)) * (cap_side < 0)
    before_cage = out.copy()
    _clear_trunk(out, triangles, rig, trunk_share, labels)
    cage_motion = np.linalg.norm(out - before_cage, axis=1)
    collar_vertices = 0
    if collar_lift:
        shoulder = rig.origin('upperarm_l')[1]
        top = target[1] + (source_top - shoulder_y) * scale
        for label in np.unique(labels):
            own = labels == label
            if not (trunk_share[own] > .99).all():
                continue
            block = out[own].copy()
            if np.ptp(block[:, 1]) < .16 * rig.fit_scale:
                center = block.mean(axis=0)
                rise = np.clip((center[1] - shoulder) / (top - shoulder), 0., 1.)
                rise *= np.clip((.19 * rig.fit_scale - abs(center[0])) / (.06 * rig.fit_scale), 0., 1.)
            else:
                rise = np.clip((block[:, 1] - shoulder) / (top - shoulder), 0., 1.)
                rise *= np.clip((.19 * rig.fit_scale - np.abs(block[:, 0])) / (.06 * rig.fit_scale), 0., 1.)
            out[own, 1] += rise * collar_lift * rig.fit_scale
            collar_vertices += int(np.count_nonzero(out[own, 1] - block[:, 1] > 1e-6))
    # Bind using the same anatomical assignment used for the rest-pose map.
    torso_bones = list(ea.TORSO_BONES) + ['pelvis']
    joints, weights = rig.weights_for(out, torso_bones)
    pool = np.zeros((len(points), len(rig.joint_names)))
    for slot in range(4):
        pool[np.arange(len(points)), joints[:, slot]] += weights[:, slot] * (1 - arm_share.sum(axis=1))
    for col, side in enumerate(['l', 'r']):
        root, wrist = rig.origin('upperarm_' + side), rig.origin('hand_' + side)
        axis = wrist - root
        t = (out - root) @ axis / (axis @ axis)
        lower = np.clip((t - .43) / .16, 0., 1.)
        lower = lower * lower * (3 - 2 * lower)
        pool[:, rig.joint_names.index('upperarm_' + side)] += arm_share[:, col] * (1 - lower)
        pool[:, rig.joint_names.index('lowerarm_' + side)] += arm_share[:, col] * lower
        own = cap_side == col
        pool[own] = 0
        pool[own, rig.joint_names.index('clavicle_' + side)] = 1
    joints = np.argsort(-pool, axis=1)[:, :4].astype(np.uint16)
    weights = np.take_along_axis(pool, joints, axis=1)
    weights /= weights.sum(axis=1, keepdims=True)
    # Meshy sometimes welds the hanging sleeve to the coat down the flank.
    # Those bridges cannot unfold into an armpit: they become enormous UV
    # streaks in the T-pose. Open that fused seam; the fitted backing closes it.
    mixed = np.ptp(arm_share[triangles], axis=1).max(axis=1) > .20
    edge_scale = np.ones(len(triangles))
    for a, b in ((0, 1), (1, 2), (2, 0)):
        before = np.linalg.norm(points[triangles[:, a]] - points[triangles[:, b]], axis=1)
        after = np.linalg.norm(out[triangles[:, a]] - out[triangles[:, b]], axis=1)
        edge_scale = np.maximum(edge_scale, after / np.maximum(before * scale, 1e-9))
    part = np.where(arm_share[:, 0] > .5, 1, np.where(arm_share[:, 1] > .5, 2, 0))
    if parts_out is not None:
        parts_out[:] = part
    same_part = np.ptp(part[triangles], axis=1) == 0
    shoulder_seam = (points[triangles, 1].min(axis=1) > shoulder_y - .12 * source_height) & (edge_scale < 1.75)
    keep = same_part | shoulder_seam
    keep, cut_fragments = drop_cut_fragments(out, triangles, keep, labels, rig.fit_scale)
    import equipment_seams
    joints, weights = equipment_seams.smooth_skin(out, triangles[keep], joints, weights, len(rig.joint_names), strength=2.)
    return out, joints, weights, keep, {'trunkScale': scale, 'limbs': reports, 'sourceSeams': seams,
        'openedSeamTriangles': int((~keep).sum()), 'cutFragmentsRemoved': cut_fragments, 'passes': [
            {'name': 'source_pose_retarget', 'vertices': len(points),
             'frontalAspectScale': 1.0, 'shoulderY': float(target[1]), 'waistY': float(waist)},
            {'name': 'body_contact_cage', 'movedVertices': int((cage_motion > 1e-6).sum()),
             'maximumMove': float(cage_motion.max()), 'meanMove': float(cage_motion.mean())},
            {'name': 'raised_collar', 'lift': collar_lift * rig.fit_scale,
             'movedVertices': collar_vertices},
            {'name': 'open_fused_sleeve_seams', 'triangles': int((~keep).sum())}]}


def _clear_trunk(points, faces, rig, influence, labels):
    """Retain a fitted design, or solve the chest contacts it still misses.

    The bounded and paired fields both start from the same source retarget.
    There is no repeated fitting of an exported garment. Well-covered chests
    retain the established collar and back profile exactly.
    """
    source = points.copy()
    _bounded_trunk(points, faces, rig, influence, labels)
    chest = rig.origin('spine_03')[1]
    # Mixed sleeve/flank triangles are subsequently opened. Counting them
    # here can falsely mark a missing chest as covered and skip the paired solve.
    garment = points[faces[(influence[faces] > .99).all(axis=1)]]
    body = rig.positions[rig.faces]
    covered = count = 0
    for y in np.linspace(chest - 0.01, chest + 0.01, 5):
        for x in np.linspace(-0.235, 0.235, 61):
            origin = np.array([x, y, 0.8])
            ray = np.array([0.0, 0.0, -1.0])
            skin, _ = io.cast(origin, ray, body)
            if not np.isfinite(skin):
                continue
            armour, _ = io.cast(origin, ray, garment)
            count += 1
            covered += armour < skin - 0.001
    if not count or covered / count >= 0.98:
        return
    bounded = points.copy()
    points[:] = source
    _paired_trunk(points, faces, rig, influence, labels)
    # The tighter solve concerns the chest. Preserve the open collar above
    # it, blending fields without changing the shape of short plate islands.
    y = source[:, 1].copy()
    for label in np.unique(labels):
        own = labels == label
        if np.ptp(source[own, 1]) < 0.16 * rig.fit_scale:
            y[own] = source[own, 1].mean()
    blend = np.clip((chest + 0.13 * rig.fit_scale - y) / (0.06 * rig.fit_scale), 0.0, 1.0)
    blend = blend * blend * (3 - 2 * blend)
    points[:] = bounded + (points - bounded) * blend[:, None]


def _paired_trunk(points, faces, rig, influence, labels):
    """Solve paired front/back inequalities after measuring lateral fit.

    Only rays crossing a substantial trunk section enter the solve. Thin
    side walls and open collars cannot demand a large whole-band depth scale.
    Short ornaments translate whole; both walls share every band transform.
    """
    heights = np.linspace(0.90, 1.58, 35) * rig.fit_scale
    widths = np.ones(len(heights))
    scales = np.ones(len(heights))
    shifts = np.zeros(len(heights))
    conservative_scale = np.ones(len(heights))
    conservative_shift = np.zeros(len(heights))
    chest = rig.origin('spine_03')[1]
    neck = rig.origin('neck_01')[1]
    chest_blend = np.clip(
        (neck - 0.04 * rig.fit_scale - heights) / (neck - chest - 0.08 * rig.fit_scale), 0.0, 1.0
    )
    chest_blend = chest_blend * chest_blend * (3 - 2 * chest_blend)
    movable = influence > 0.99

    def transform(axis, scale, shift):
        for label in np.unique(labels[movable]):
            own = labels == label
            block = points[own].copy()
            if np.ptp(block[:, 1]) < 0.16 * rig.fit_scale:
                if not movable[own].all():
                    continue
                c = block.mean(axis=0)
                points[own, axis] += c[axis] * (np.interp(c[1], heights, scale) - 1) + np.interp(
                    c[1], heights, shift
                )
            else:
                points[own, axis] += influence[own] ** 2 * (
                    block[:, axis] * (np.interp(block[:, 1], heights, scale) - 1)
                    + np.interp(block[:, 1], heights, shift)
                )

    triangles = faces[movable[faces].all(axis=1)]
    verts = points[triangles]
    body_verts = rig.positions[rig.faces]
    skin_points = rig._region(ea.TORSO_BONES)
    for i, y in enumerate(heights):
        skin = skin_points[abs(skin_points[:, 1] - y) < 0.03]
        if len(skin) < 6 or y >= 1.49 * rig.fit_scale:
            continue
        z = (skin[:, 2].min() + skin[:, 2].max()) / 2
        sides = [
            io.cast(np.array([0.0, y, z]), np.array([s, 0.0, 0.0]), verts)[0] for s in [-1.0, 1.0]
        ]
        if np.isfinite(sides).all() and min(sides) > 0.07 * rig.fit_scale:
            widths[i] = np.clip(
                (np.percentile(abs(skin[:, 0]), 98) + 0.014) / min(sides),
                1.0,
                1.45 + 0.35 * chest_blend[i],
            )
    for _ in range(2):
        widths[:] = np.convolve(np.pad(widths, 1, mode='edge'), [0.25, 0.5, 0.25], mode='valid')
    transform(0, widths, np.zeros(len(heights)))
    verts = points[triangles]
    contacts = []
    for i, y in enumerate(heights):
        az = [[], []]
        target = [[], []]
        for x in np.linspace(-0.20, 0.20, 17) * rig.fit_scale:
            sample = []
            for sign in [1.0, -1.0]:
                origin = np.array([x, y, sign * 0.8])
                direction = np.array([0.0, 0.0, -sign])
                a, _ = io.cast(origin, direction, verts)
                b, _ = io.cast(origin, direction, body_verts)
                if not np.isfinite(a + b):
                    break
                z = sign * (0.8 - a)
                body = sign * (0.8 - b)
                if z * sign < -0.045:
                    break
                sample.append((z, z + sign * max(0.0, (body - z) * sign + 0.018)))
            # Thin silhouettes at an armpit or an open collar are not a
            # front/back trunk section. Do not inflate the entire back to
            # satisfy two nearly coincident surfaces from such a ray.
            if len(sample) != 2 or sample[0][0] - sample[1][0] < 0.12 * rig.fit_scale:
                continue
            for col, (z, goal) in enumerate(sample):
                az[col].append(z)
                target[col].append(goal)
        if (
            min(map(len, az)) < 3
            or np.percentile(az[0], 90) - np.percentile(az[1], 10) < 0.12 * rig.fit_scale
        ):
            contacts.append(None)
            continue
        az = [np.array(v) for v in az]
        target = [np.array(v) for v in target]
        contacts.append((az, target))
        front = np.percentile(az[0], 90)
        back = np.percentile(az[1], 10)
        f = np.percentile(target[0] - az[0], 90)
        b = np.percentile(az[1] - target[1], 90)
        conservative_scale[i] = np.clip(1 + (f + b) / (front - back), 1.0, 1.55)
        conservative_shift[i] = np.clip(
            front + f - front * conservative_scale[i], -0.025 * rig.fit_scale, 0.025 * rig.fit_scale
        )
        candidates = np.linspace(1.0, 2.75, 71)
        low = np.percentile(target[0] - candidates[:, None] * az[0], 95, axis=1)
        high = np.percentile(target[1] - candidates[:, None] * az[1], 5, axis=1)
        good = (low <= high) & (low <= 0.08 * rig.fit_scale) & (high >= -0.08 * rig.fit_scale)
        if good.any():
            idx = np.flatnonzero(good)[0]
        else:
            idx = np.argmin(
                np.maximum(low - high, 0)
                + np.maximum(low - 0.08 * rig.fit_scale, 0)
                + np.maximum(-0.08 * rig.fit_scale - high, 0)
            )
        scales[i] = candidates[idx]
        shifts[i] = np.clip((low[idx] + high[idx]) / 2, -0.08 * rig.fit_scale, 0.08 * rig.fit_scale)
    for _ in range(2):
        scales[:] = np.maximum(
            scales, np.convolve(np.pad(scales, 1, mode='edge'), [0.25, 0.5, 0.25], mode='valid')
        )
        shifts[:] = np.convolve(np.pad(shifts, 1, mode='edge'), [0.25, 0.5, 0.25], mode='valid')
    for i, contact in enumerate(contacts):
        if contact is None:
            continue
        az, target = contact
        low = np.percentile(target[0] - scales[i] * az[0], 95)
        high = np.percentile(target[1] - scales[i] * az[1], 5)
        if low <= high:
            shifts[i] = np.clip(shifts[i], low, high)
    for _ in range(2):
        conservative_scale[:] = np.convolve(
            np.pad(conservative_scale, 1, mode='edge'), [0.25, 0.5, 0.25], mode='valid'
        )
        conservative_shift[:] = np.convolve(
            np.pad(conservative_shift, 1, mode='edge'), [0.25, 0.5, 0.25], mode='valid'
        )
    scales = conservative_scale * (1 - chest_blend) + scales * chest_blend
    shifts = conservative_shift * (1 - chest_blend) + shifts * chest_blend
    transform(2, scales, shifts)


def _bounded_trunk(points, faces, rig, influence, labels):
    """Fit front/back contacts with band affines and bounded lateral ease.

    Frontmost surfaces, not ray parity, define contact on overlapping solids.
    A short ornament receives only its centroid's translation, preserving its
    volume and UVs. Both walls of a long shell receive the same band affine.
    """
    heights = np.linspace(.90, 1.58, 35) * rig.fit_scale
    scales, shifts = np.ones(len(heights)), np.zeros(len(heights))
    widths = np.ones(len(heights))
    movable = influence > .99
    verts = points[faces[movable[faces].all(axis=1)]]
    body_verts = rig.positions[rig.faces]
    torso_body = rig._region(ea.TORSO_BONES)
    for i, y in enumerate(heights):
        skin = torso_body[np.abs(torso_body[:, 1] - y) < .03]
        if len(skin) >= 6 and y < 1.49 * rig.fit_scale:
            z = float((skin[:, 2].min() + skin[:, 2].max()) / 2)
            sides = [io.cast(np.array([0., y, z]), np.array([s, 0., 0.]), verts)[0] for s in [-1., 1.]]
            if np.isfinite(sides).all() and min(sides) > .07 * rig.fit_scale:
                want = float(np.percentile(np.abs(skin[:, 0]), 98)) + .014
                widths[i] = np.clip(want / min(sides), 1., 1.45)
        contacts = [[], []]
        armour_depths = [[], []]
        for x in np.linspace(-.17, .17, 13) * rig.fit_scale:
            for col, sign in enumerate([1., -1.]):
                origin = np.array([x, y, sign * .8])
                direction = np.array([0., 0., -sign])
                a, _ = io.cast(origin, direction, verts)
                b, _ = io.cast(origin, direction, body_verts)
                if not np.isfinite(a + b): continue
                az, bz = sign * (.8 - a), sign * (.8 - b)
                if az * sign < -.045: continue  # open neckline / opposite wall
                contacts[col].append(max(0., (bz - az) * sign + .018))
                armour_depths[col].append(az)
        if not all(len(c) >= 3 for c in contacts): continue
        f, b = (float(np.percentile(c, 90)) for c in contacts)
        # A collar opening can leave only a few almost coplanar contacts.
        # Their median depth is not the depth of the trunk: scaling about it
        # used to throw a backplate 200 mm behind the wearer. Use the outer
        # contact envelope and bound the ease of the whole band.
        front = float(np.percentile(armour_depths[0], 90))
        back = float(np.percentile(armour_depths[1], 10))
        if front - back < .12 * rig.fit_scale:
            continue
        scales[i] = np.clip(1 + (f + b) / (front - back), 1., 1.55)
        shifts[i] = np.clip(front + f - front * scales[i], -.025 * rig.fit_scale, .025 * rig.fit_scale)
    for values in (scales, shifts, widths):
        for _ in range(2):
            values[:] = np.convolve(np.pad(values, 1, mode='edge'), [.25, .5, .25], mode='valid')
    for label in np.unique(labels[movable]):
        own = labels == label
        block = points[own].copy()
        if np.ptp(block[:, 1]) < .16:
            if not movable[own].all():
                continue
            c = block.mean(axis=0)
            points[own, 2] += c[2] * (np.interp(c[1], heights, scales)-1) + np.interp(c[1], heights, shifts)
            points[own, 0] += c[0] * (np.interp(c[1], heights, widths)-1)
        else:
            points[own, 2] += influence[own]**2 * (block[:, 2] * (np.interp(block[:, 1], heights, scales)-1)
                                                 + np.interp(block[:, 1], heights, shifts))
            points[own, 0] += influence[own]**2 * block[:, 0] * (np.interp(block[:, 1], heights, widths)-1)


def lining(rig, armour, triangles):
    """A closed fitted backing carrying the body's original blend weights."""
    points, faces = rig.positions, ea.garment_faces(rig, 'torso')
    centre = points[faces].mean(axis=1)
    keep = (centre[:, 1] > .95 * rig.fit_scale) & (centre[:, 1] < 1.535 * rig.fit_scale)
    wrist = min(abs(rig.origin('hand_' + side)[0]) for side in ['l', 'r']) - .008 * rig.fit_scale
    keep &= np.abs(centre[:, 0]) < wrist
    faces = faces[keep]
    used, inverse = np.unique(faces, return_inverse=True)
    points = points[used].copy()
    faces = inverse.reshape(-1, 3)
    # Merge body UV seams before calculating the backing's outward normals.
    _, first, weld = np.unique(np.round(points, 6), axis=0, return_index=True, return_inverse=True)
    points = points[first]
    used = used[first]
    faces = weld[faces]
    _, unique_faces = np.unique(np.sort(faces, axis=1), axis=0, return_index=True)
    faces = faces[unique_faces]
    # The race's default clothing is a loose shirt, not the anatomy under a
    # cuirass.  Build the backing on a fitted cage instead of copying its
    # flared sleeve hems into every armour design.
    dominant = rig.joints[used, np.argmax(rig.weights[used], axis=1)]
    trunk = np.ones(len(points), dtype=bool)
    for side in ['l', 'r']:
        limb_bones = [rig.joint_names.index(b) for b in ['upperarm_'+side, 'lowerarm_'+side, 'hand_'+side]]
        own = np.isin(dominant, limb_bones)
        root, wrist = rig.origin('upperarm_'+side), rig.origin('hand_'+side)
        axis = wrist-root
        t = np.clip((points[own]-root) @ axis / (axis@axis), 0., 1.)
        centre_line = root + t[:, None]*axis
        radial = points[own]-centre_line
        radius = np.linalg.norm(radial, axis=1)
        want = np.interp(t, [0., .15, .5, 1.], [.055, .048, .040, .034]) * rig.fit_scale
        sleeve_faces = armour[triangles]
        sleeve_faces = sleeve_faces[(sleeve_faces[:, :, 0].mean(axis=1) * (1 if side == 'l' else -1)) > .18 * rig.fit_scale]
        for row, (origin, ray, length) in enumerate(zip(centre_line, radial, radius)):
            if length < 1e-8:
                continue
            hit, _ = io.cast(origin, ray / length, sleeve_faces)
            if np.isfinite(hit) and .012 * rig.fit_scale < hit < .16 * rig.fit_scale:
                # Fill the shoulder seam just inside the artwork. Recessing this
                # to 75% of the inner radius exposed a deep underarm cavity.
                # This is a new open sheet; give it thickness only after fitting.
                inside = max(.015 * rig.fit_scale, hit - .004 * rig.fit_scale)
                shoulder = np.clip((.35 - t[row]) / .25, 0., 1.)
                shoulder = shoulder * shoulder * (3 - 2 * shoulder)
                want[row] = min(want[row], inside) * (1 - shoulder) + inside * shoulder
        points[own] = centre_line + radial * (want/np.maximum(radius, 1e-8))[:, None]
        trunk &= ~own
    y = points[trunk, 1]/rig.fit_scale
    width = np.interp(y, [.95, 1.05, 1.30, 1.45, 1.52], [.16, .15, .18, .18, .075])*rig.fit_scale
    depth = np.interp(y, [.95, 1.05, 1.30, 1.45, 1.52], [.12, .125, .145, .145, .075])*rig.fit_scale
    radial = points[trunk][:, [0, 2]] - np.array([0., -.045*rig.fit_scale])
    ratio = np.linalg.norm(radial/np.column_stack((width, depth)), axis=1)
    points[np.ix_(trunk, [0, 2])] = radial/np.maximum(1., ratio)[:, None] + np.array([0., -.045*rig.fit_scale])
    # The current bodies are slimmer than the former fixed ellipse. Keep the
    # new backing inside the reconstructed artwork at every trunk height;
    # otherwise its flat cloth material can cover a correctly textured flank.
    art = armour[triangles]
    for vertex in np.flatnonzero(trunk):
        origin = np.array([0., points[vertex, 1], -.045 * rig.fit_scale])
        radial = points[vertex] - origin
        distance = np.linalg.norm(radial)
        if distance < 1e-8:
            continue
        hit, _ = io.cast(origin, radial / distance, art)
        if np.isfinite(hit) and .025 * rig.fit_scale < hit < .3 * rig.fit_scale:
            points[vertex] = origin + radial * min(1., max(.015, hit - .006) / distance)
    # Above the chest the source's collar is considerably narrower than the
    # default shirt. Keep the backing inside that artwork, just as on sleeves;
    # otherwise it hides the collar as soon as excessive depth ease is removed.
    collar = np.flatnonzero(trunk & (points[:, 1] > 1.40 * rig.fit_scale))
    art_faces = armour[triangles]
    for vertex in collar:
        origin = np.array([0., points[vertex, 1], -.045 * rig.fit_scale])
        ray = points[vertex] - origin
        radius = np.linalg.norm(ray)
        if radius < 1e-8:
            continue
        hit, _ = io.cast(origin, ray / radius, art_faces)
        want = .065 * rig.fit_scale
        if np.isfinite(hit):
            want = min(radius, max(.015 * rig.fit_scale, hit * .70))
        blend = np.clip((points[vertex, 1] / rig.fit_scale - 1.40) / .07, 0., 1.)
        points[vertex] = origin + ray * (1 - blend + blend * min(1., want / radius))
    # The copied face selection has a saw-toothed neckline. Construct a level
    # neck rim before giving this new backing any thickness.
    rim_edges = np.vstack((faces[:, [0, 1]], faces[:, [1, 2]], faces[:, [2, 0]]))
    _, rim_inverse, rim_counts = np.unique(np.sort(rim_edges, axis=1), axis=0,
                                           return_inverse=True, return_counts=True)
    rim = np.unique(rim_edges[rim_counts[rim_inverse] == 1])
    neck = rim[(np.abs(points[rim, 0]) < .13 * rig.fit_scale)
               & (points[rim, 1] > 1.49 * rig.fit_scale)]
    head = rig._region(['Head'])
    points[neck, 1] = min(1.535 * rig.fit_scale, head[:, 1].min() - .008 * rig.fit_scale)
    # Clip the newly reconstructed open lining before thickening. Levelling
    # only boundary vertices can leave folded interior cloth above the rim.
    import limb_head_remap
    points, _, _, faces = limb_head_remap.clip(points, np.zeros_like(points),
        points[:, [0, 1]], faces, 1.485 * rig.fit_scale, above=False)
    normals = np.zeros_like(points)
    face_normals = np.cross(points[faces[:, 1]] - points[faces[:, 0]], points[faces[:, 2]] - points[faces[:, 0]])
    for col in range(3): np.add.at(normals, faces[:, col], face_normals)
    normals /= np.maximum(np.linalg.norm(normals, axis=1, keepdims=True), 1e-10)
    outer, inner = points + normals * .004, points + normals * .001
    import equipment_seams
    # Bind the fitted lining, not the loose shirt positions it came from.
    j, w = rig.weights_for(points, list(ea.TORSO_BONES) + ['neck_01',
        'upperarm_l', 'upperarm_r', 'lowerarm_l', 'lowerarm_r'])
    j, w = equipment_seams.smooth_skin(points, faces, j, w, len(rig.joint_names), strength=2.)
    return equipment_seams.thickened_sheets(outer, inner, normals, faces, j, w)


def backing_colour(surface, texture):
    """Pick an unobtrusive cloth colour from the design's own sleeve atlas."""
    if texture is None:
        return [.045, .025, .018, 1.]
    im = np.asarray(Image.open(BytesIO(texture)).convert('RGB'))
    points = surface.positions
    height = np.ptp(points[:, 1])
    own = (np.abs(points[:, 0]) > .28 * height) & (points[:, 1] < points[:, 1].max() - .35 * height)
    uv = surface.uvs[own]
    if not len(uv):
        uv = surface.uvs
    xy = np.clip(uv, 0., 1.) * np.array([im.shape[1]-1, im.shape[0]-1])
    colours = im[xy[:, 1].astype(int), xy[:, 0].astype(int)].astype(float)
    brightness = colours.mean(axis=1)
    lo, hi = np.percentile(brightness, [20, 55])
    cloth = colours[(brightness >= lo) & (brightness <= hi)]
    if not len(cloth):
        # With only two atlas samples both percentiles can lie between them.
        cloth = colours[np.argsort(brightness)[:max(1, len(colours) // 2)]]
    return ea.srgb_to_linear(np.median(cloth, axis=0)) + [1.]


def source_coordinates(points, joints, weights, source_points, report, rig):
    """Inverse anatomical frames for painting reconstructed cloth from the art.

    Projecting directly onto the fitted, opened seam samples one edge of a UV
    chart repeatedly. Return to the complete original shell before sampling,
    including the flank triangles separated from its hanging sleeves.
    """
    height=np.ptp(source_points[:,1]);shoulder=source_points[:,1].max()-.17*height
    center=np.array([0.,shoulder,-.02*height])
    target=np.array([0.,rig.origin('upperarm_l')[1],-.035*rig.fit_scale])
    scale=report['trunkScale']
    out=(points-target)/np.array([scale,scale,.8*scale])+center
    for side in ('l','r'):
        bones=[rig.joint_names.index(name+'_'+side) for name in ('upperarm','lowerarm','hand')]
        own=(weights*np.isin(joints,bones)).sum(axis=1)>.5
        frame=report['limbs'][side]
        root=np.array(frame['sourceShoulder']);wrist=np.array(frame['sourceWrist'])
        target_root=rig.origin('upperarm_'+side)
        turn=rotation_between(wrist-root,rig.origin('hand_'+side)-target_root)
        out[own]=(points[own]-target_root)@turn/frame['scale']+root
    return out


def build(source, out, rig, kind='cuirass', label='Remapped armour'):
    original = source.with_name(source.name + '.orig')
    if original.exists():
        source = original
    surface, texture = io.read_source(source)
    cloth_colour = backing_colour(surface, texture)
    raw = surface.positions.copy()
    original_faces = surface.indices.reshape(-1, 3).copy()
    lift = COLLAR_LIFT.get(source.name.removesuffix('.orig'), 0.)
    points, joints, weights, keep, report = remap(raw, surface.indices.reshape(-1, 3), rig, lift)
    surface.indices = surface.indices.reshape(-1, 3)[keep].reshape(-1)
    surface.positions = points
    canon, _, _ = io._weld(points, surface.indices.reshape(-1, 3))
    faces = surface.indices.reshape(-1, 3)
    _, unique = np.unique(np.sort(canon[faces], axis=1), axis=0, return_index=True)
    report['duplicateFacesRemoved'] = int(len(faces) - len(unique))
    surface.indices = faces[np.sort(unique)].reshape(-1)
    io._make_winding_coherent(surface)
    io._unwind_inverted_shells(surface)
    # Face-based normals follow the new geometry.  UV seams remain split.
    triangles = surface.indices.reshape(-1, 3)
    normals = np.zeros_like(points)
    face_normals = np.cross(points[triangles[:, 1]] - points[triangles[:, 0]],
                            points[triangles[:, 2]] - points[triangles[:, 0]])
    for col in range(3):
        np.add.at(normals, triangles[:, col], face_normals)
    normals /= np.maximum(np.linalg.norm(normals, axis=1, keepdims=True), 1e-10)
    glb = ea.EquipmentGLB(generator='Eloria source-pose torso retarget')
    source_doc, _ = ea.read_glb(source)
    source_material = source_doc.get('materials', [{}])[0]
    material = io.textured_material(glb, label + ' Base', texture,
                                    double_sided=source_material.get('doubleSided', False))
    # read_source returns the original encoded image. Originals are JPEGs;
    # labelling those bytes PNG makes Godot export corrupt .png sidecars.
    if texture is not None and texture.startswith(b'\xff\xd8'):
        glb.doc['images'][0]['mimeType'] = 'image/jpeg'
    glb.doc['materials'][material]['pbrMetallicRoughness']['roughnessFactor'] = source_material.get(
        'pbrMetallicRoughness', {}).get('roughnessFactor', .8)
    glb.skeleton(rig)
    primitive = glb.primitive(points, normals, surface.uvs, surface.indices, material,
                              joints=joints, weights=weights)
    # The source can fuse a hanging sleeve along its entire flank. Capping
    # that long boundary creates a cone outside the sleeve when the arm bends.
    # The continuous fitted lining closes the opened underarm instead.
    p, n, uv, idx, j, w = lining(rig, points, triangles)
    liner_mat = len(glb.doc['materials'])
    glb.doc['materials'].append({'name': label + ' Backing', 'pbrMetallicRoughness': {
        'baseColorFactor': cloth_colour, 'metallicFactor': 0., 'roughnessFactor': 1.}})
    if texture is not None:
        import equipment_seam_texture
        source_p = source_coordinates(p, j, w, raw, report, rig)
        liner = equipment_seam_texture.primitive(glb, p, idx.reshape(-1,3), n, j, w, source_p,
            raw, original_faces, surface.uvs, texture, label+' Fitted cloth')
    else:
        liner = glb.primitive(p, n, uv, idx, liner_mat, joints=j, weights=w, weight_floats=True)
    glb.mesh(label, [primitive], skin=0)
    glb.mesh('GeneratedArmorBacking', [liner], skin=0)
    cover = [.95, 1.535, min(abs(rig.origin('hand_' + side)[0]) for side in ['l', 'r']) / rig.fit_scale - .008]
    glb.doc['meshes'][-1]['extras'] = {'bodyCover': cover}
    report['passes'].append({'name': 'fitted_backing', 'vertices': len(p),
                             'triangles': len(idx)//3, 'bodyCover': cover})
    glb.write(out)
    return dict(report, source=source.name, out=out.name, kind=kind,
                vertices=len(points), triangles=len(triangles), bytes=out.stat().st_size)


if __name__ == '__main__':
    ap = argparse.ArgumentParser()
    ap.add_argument('source', type=Path)
    ap.add_argument('-o', required=True, type=Path)
    args = ap.parse_args()
    rig = ea.load_rig(io.RACES / 'luminous_male.glb', body_mesh_names=io.BODY_MESH)
    result = build(args.source, args.o, rig)
    args.o.with_suffix('.report.json').write_text(json.dumps(result, indent=2))
    print(json.dumps(result, indent=2))
