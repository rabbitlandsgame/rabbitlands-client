"""Fit original leg, foot and head artwork to anatomical frames.

Legs share the pelvis but have independent shin axes. Boots are sized by their
feet, so the drawing determines shaft height. Headwear is sized to its inner
cranium, keeping crests and brims out of the measurement. Connected ornaments
move whole, and source UV seams always receive identical geometry and weights.
"""

from __future__ import annotations

import numpy as np

import conform_equipment as io
import equipment_authoring as ea
import torso_remap
from trim_generated_boots import clip


# Alternate leg linings are used only when fitted boots are also present.  A
# common cuff hand-off keeps the leg and boot underlayers from occupying the
# whole shin together (which used to reveal trouser cloth from the front and
# boot cloth from the rear through openings in the authored shells).  The
# visible source art is untouched; only the hidden, generated backing starts
# here, and its radial section is still derived from that garment's artwork.
FITTED_BOOT_CUFF_SEAM = 0.190


def compress_cuff_band(points, seam, keep_above):
    """Move an existing backing inside a cuff without changing topology.

    Fresh authoring clips the hidden sheet at the measured cuff.  For already
    reviewed packed assets, however, a clip adds vertices and indices.  This
    affine height compression is the POSITION-only equivalent: it preserves
    every triangle and draw call, keeps the far garment edge exact, and moves
    the old overshoot wholly inside the adjacent fitted garment.  One affine
    scale across the complete hidden sheet avoids a fold at a blend boundary.
    """
    out = np.asarray(points, dtype=float).copy()
    if not len(out):
        return out
    y = out[:, 1].copy()
    low, high = float(y.min()), float(y.max())
    if high - low <= 1e-12:
        return out
    if keep_above:
        if low < seam < high:
            out[:, 1] = seam + (y - low) * (high - seam) / (high - low)
    else:
        if low < seam < high:
            out[:, 1] = low + (y - low) * (seam - low) / (high - low)
    return out


def components(points, triangles):
    canonical, edges, count = io._weld(points, triangles)
    return io._components(edges, count)[canonical]


def normals(points, faces):
    result = np.zeros_like(points)
    face = np.cross(
        points[faces[:, 1]] - points[faces[:, 0]],
        points[faces[:, 2]] - points[faces[:, 0]],
    )
    for col in range(3):
        np.add.at(result, faces[:, col], face)
    return result / np.maximum(np.linalg.norm(result, axis=1, keepdims=True), 1e-10)


def leg_frame(points, faces, rig, full_harness=False):
    """Put the waist over the pelvis and each trouser tube on its own shin."""
    labels = components(points, faces)
    low, high = points[:, 1].min(), points[:, 1].max()
    height = high - low
    floor = (min(ea.weighted_sole(rig, side) for side in ("l", "r")) - .004 * rig.fit_scale
             if full_harness else .10 * rig.fit_scale)
    waist = rig.origin("spine_01")[1] + .020 * rig.fit_scale
    scale = (waist - floor) / height
    out = points * scale
    out[:, 1] += floor - low * scale
    out[:, 2] += -0.035 * rig.fit_scale
    # The longest connected shell carries the trouser axes. Rivets and flared
    # knee ornaments cannot move the measured centre of a tube.
    shell = max(
        np.unique(labels),
        key=lambda label: np.ptp(points[labels == label, 1])
        * np.count_nonzero(labels == label),
    )
    heights = np.linspace(low + 0.08 * height, low + 0.72 * height, 13)
    shifts = {}
    for side, sign in [("l", 1.0), ("r", -1.0)]:
        xs, zs = [], []
        for y in heights:
            band = points[
                (labels == shell)
                & (points[:, 0] * sign > 0.025 * height)
                & (np.abs(points[:, 1] - y) < 0.075 * height)
            ]
            if len(band) < 5:
                band = points[
                    (points[:, 0] * sign > 0.025 * height)
                    & (np.abs(points[:, 1] - y) < 0.10 * height)
                ]
            center = (
                np.percentile(band, [10, 90], axis=0).mean(axis=0)
                if len(band)
                else np.array([sign * 0.15 * height, y, 0.0])
            )
            xs.append(rig.origin("calf_" + side)[0] - center[0] * scale)
            zs.append(
                rig.origin("calf_" + side)[2]
                - (center[2] * scale - 0.035 * rig.fit_scale)
            )
        shifts[side] = [float(np.median(xs)), float(np.median(zs))]
        for label in np.unique(labels):
            own = (labels == label) & (points[:, 0] * sign >= 0)
            if not own.any():
                continue
            block = points[own]
            whole = np.ptp(points[labels == label, 1]) * scale < 0.16 * rig.fit_scale
            y = np.full(len(block), block[:, 1].mean()) if whole else block[:, 1]
            x = (
                np.full(len(block), abs(block[:, 0].mean()))
                if whole
                else np.abs(block[:, 0])
            )
            hip_fade = np.clip((low + 0.86 * height - y) / (0.25 * height), 0.0, 1.0)
            middle_fade = np.clip(x / (0.09 * height), 0.0, 1.0)
            out[own, 0] += np.interp(y, heights, xs) * hip_fade * middle_fade
            out[own, 2] += np.interp(y, heights, zs) * hip_fade
    # The drawn crotch is lower than the canonical body's. Map that landmark
    # explicitly before binding; a waist/hem-only scale leaves the seat hanging
    # between the moving thighs. Whole ornaments receive only a translation.
    source_hits, target_hits = [], []
    for z in np.linspace(-.10, .06, 9):
        origin = np.array([0., low-.1*height, z*height])
        hit, _ = io.cast(origin, np.array([0.,1.,0.]), points[faces])
        if np.isfinite(hit): source_hits.append(origin[1]+hit)
        origin = np.array([0., .10, z])
        hit, _ = io.cast(origin, np.array([0.,1.,0.]), rig.positions[ea.garment_faces(rig)])
        if np.isfinite(hit) and origin[1]+hit < rig.origin('pelvis')[1]: target_hits.append(origin[1]+hit)
    source_crotch = float(np.median(source_hits)) if source_hits else low+.70*height
    target_crotch = float(np.median(target_hits))-.012 if target_hits else rig.origin('pelvis')[1]-.10
    if low+.3*height < source_crotch < high-.10*height:
        for label in np.unique(labels):
            own=labels==label
            y=points[own,1]
            if np.ptp(y)*scale < .16*rig.fit_scale: y=np.full(len(y),y.mean())
            old=floor+(y-low)*scale
            want=np.interp(y,[low,source_crotch,high],[floor,target_crotch,waist])
            out[own,1]+=want-old
    if full_harness:
        seat_harness_soles(out, points, labels, rig)
    return out, {
        "name": "waist_crotch_and_shin_frames",
        "sourceCrotchY": source_crotch,
        "crotchY": target_crotch,
        "scale": float(scale),
        "waistY": float(waist),
        "hemY": float(floor),
        "shifts": shifts,
    }


def seat_harness_soles(out, points, labels, rig):
    """Seat each sabaton of a legs-with-boots harness on its weighted sole.

    Shared rest transforms do not make the two foot surfaces identical, so
    each side is lifted or lowered to 4 mm under its own weighted sole, the
    shift fading out by the shin split. Short ornaments travel whole; both
    walls share the positive band map. ``points`` (the source) picks the side.
    """
    seam_y = .320 * rig.fit_scale
    for side, sign in (("l", 1.), ("r", -1.)):
        side_vertices = points[:, 0] * sign >= 0
        have = float(out[side_vertices, 1].min())
        want = ea.weighted_sole(rig, side) - .004 * rig.fit_scale
        for label in np.unique(labels[side_vertices]):
            own = (labels == label) & side_vertices
            block = out[own, 1].copy()
            y = np.full(len(block), block.mean()) if np.ptp(block) < .16 * rig.fit_scale else block
            out[own, 1] += np.clip((seam_y-y) / max(seam_y-have, .01), 0., 1.) * (want-have)
    return out


def boot_frame(points, faces, rig):
    """Map each heel/toe span independently; retain the design's shaft height."""
    out = points.copy()
    report = []
    cuffs = []
    labels = components(points, faces)
    height = np.ptp(points[:, 1])
    for side, sign in [("l", 1.0), ("r", -1.0)]:
        own = points[:, 0] * sign >= 0
        block = points[own]
        sole = float(block[:, 1].min())
        foot = block[block[:, 1] < sole + 0.22 * height]
        if len(foot) < 8:
            foot = block
        low, high = np.percentile(foot, [1, 99], axis=0)
        body = rig._region(["foot_" + side, "ball_" + side])
        body_low, body_high = body.min(axis=0), body.max(axis=0)
        scale = (body_high[2] - body_low[2] + 0.012 * rig.fit_scale) / max(
            high[2] - low[2], 0.1 * height
        )
        center = (low + high) / 2
        center[1] = sole
        target = (body_low + body_high) / 2
        target[1] = ea.weighted_sole(rig, side) - 0.004 * rig.fit_scale
        out[own] = (block - center) * scale + target
        # The main shaft ends at the cuff; an ornamental spike above it must
        # not make the replacement stocking climb to the spike's tip.
        candidates = [
            label
            for label in np.unique(labels[own])
            if np.count_nonzero((labels == label) & own) > 50
        ]
        if not candidates:
            candidates = np.unique(labels[own])
        shell = max(
            candidates,
            key=lambda label: np.count_nonzero((labels == label) & own)
            * np.ptp(points[(labels == label) & own, 1]),
        )
        cuff = float(np.percentile(out[(labels == shell) & own, 1], 98))
        cuffs.append(cuff)
        report.append(
            {
                "side": side,
                "scale": float(scale),
                "sourceFootLength": float(high[2] - low[2]),
                "targetFootLength": float(body_high[2] - body_low[2]),
                "cuffY": cuff,
            }
        )
    return out, min(cuffs), {"name": "heel_to_toe_frames", "feet": report}


def head_frame(points, faces, rig, label):
    """Find an enclosed cranium, ignoring the outer crest and brim bounds."""
    height = np.ptp(points[:, 1])
    low = points.min(axis=0)
    middle = np.percentile(points, [5, 95], axis=0).mean(axis=0)
    target = io.socket_origin(rig, 3)
    ring = bool(set(label.lower().split()) & {"circlet", "headband", "crown", "tiara"})
    directions = []
    for y in ([0.0] if ring else [0.0, 0.45, 0.8]):
        for angle in np.linspace(0.0, 2 * np.pi, 12, endpoint=False):
            ray = np.array(
                [
                    np.sin(angle) * np.sqrt(1 - y * y),
                    y,
                    np.cos(angle) * np.sqrt(1 - y * y),
                ]
            )
            if not ring and y == 0 and ray[2] > 0.25:
                continue  # the face opening is intentional
            directions.append(ray)
    if not ring:
        directions.append(np.array([0.0, 1.0, 0.0]))
    rays = np.asarray(directions)
    if ring:
        target = target.copy()
        from headwear_envelope import band_envelope
        target, ring_need = band_envelope(rig, rays)
    body_faces = rig.positions[rig.faces]
    need = (
        np.array([io.cast(target, ray, body_faces)[0] for ray in rays])
        + 0.009 * rig.fit_scale
    )
    need[~np.isfinite(need)] = 0.105 * rig.fit_scale
    if ring:
        need = ring_need
    triangles = points[faces]
    best = None
    for y in np.linspace(low[1] + 0.30 * height, low[1] + 0.73 * height, 12):
        for z in np.linspace(middle[2] - 0.16 * height, middle[2] + 0.10 * height, 9):
            center = np.array([middle[0], y, z])
            distances = np.array([io.cast(center, ray, triangles)[0] for ray in rays])
            valid = np.isfinite(distances) & (distances > 0.025 * height)
            if valid.mean() < (0.65 if ring else 0.88):
                continue
            scale = float(np.percentile(need[valid] / distances[valid], 95))
            score = scale * (1 + 0.25 * (1 - valid.mean()))
            if best is None or score < best[0]:
                best = (score, scale, center, float(valid.mean()))
    if best is None:
        # Open bands can have no enclosed hemisphere. Their inner left/right
        # span at the band still measures a skull, rather than a crest.
        span = np.percentile(points[:, 0], 90) - np.percentile(points[:, 0], 10)
        best = (0.0, 0.235 * rig.fit_scale / max(span, 1e-8), middle, 0.0)
    _, scale, center, enclosure = best
    out = (points - center) * scale + target
    if ring and "headband" in label.lower().split():
        # Size a wrapped band around the full forehead, then lift its deeper
        # cloth border above the eyes. Measuring at the narrower crown would
        # shrink the whole design, including its hanging scarf.
        target = target.copy()
        target[1] += 0.045 * rig.fit_scale
        out[:, 1] += 0.045 * rig.fit_scale
    # A cranium can fit while the visor sits across the eyes. Locate the top
    # of the frontal opening separately: rays through a face opening reach
    # the back wall, whereas rays above its brow meet the front of the cap.
    brow = None
    if not ring:
        rows = np.linspace(low[1] + 0.20 * height, low[1] + 0.80 * height, 60)
        openings = []
        for y in rows:
            z = []
            for x in (
                np.r_[np.linspace(-0.23, -0.11, 5), np.linspace(0.11, 0.23, 5)] * height
                + middle[0]
            ):
                origin = np.array([x, y, points[:, 2].max() + height])
                distance, _ = io.cast(origin, np.array([0.0, 0.0, -1.0]), triangles)
                z.append(origin[2] - distance)
            openings.append(np.mean(np.asarray(z) < center[2] + 0.04 * height))
        for i in range(len(rows) - 5):
            if openings[i] >= 0.5 and np.mean(openings[i + 1 : i + 6]) < 0.25:
                brow = float(rows[i])
        if brow is not None:
            # Horns, crystals and mushrooms can extend well above the skull.
            # The visor belongs above the actual eyes, not at a fraction of
            # the full weighted head-feature height.
            eyes = ea.load_rig(io.RACES / (rig.source_slug + ".glb"), ("eyes",))
            brow_target = float(np.quantile(eyes.positions[:, 1], .95)) + .032 * rig.fit_scale
            # Keep the brow over the eyes while fitting the skull. Translating
            # an already fitted cap upward puts its narrower lower section
            # across the head and can expose the skull at the back.
            seated = None
            for trial in np.linspace(scale * 0.9, scale * 1.7, 25):
                for z in np.linspace(
                    center[2] - 0.12 * height, center[2] + 0.16 * height, 19
                ):
                    candidate = np.array(
                        [middle[0], brow + (target[1] - brow_target) / trial, z]
                    )
                    distances = np.array(
                        [io.cast(candidate, ray, triangles)[0] for ray in rays]
                    )
                    valid = np.isfinite(distances) & (distances > 0.025 * height)
                    if (
                        valid.mean() < 0.95
                        or np.max(need[valid] / distances[valid]) > trial
                    ):
                        continue
                    score = trial + 0.02 * abs(z - center[2]) / height
                    if seated is None or score < seated[0]:
                        seated = score, trial, candidate, float(valid.mean())
                if seated is not None:
                    break
            if seated is not None:
                _, scale, center, enclosure = seated
                out = (points - center) * scale + target
            else:
                lift = float(
                    np.clip(
                        brow_target - (target[1] + (brow - center[1]) * scale),
                        -0.06 * rig.fit_scale,
                        0.12 * rig.fit_scale,
                    )
                )
                out[:, 1] += lift
                target = target.copy()
                target[1] += lift
    return out, {
        "name": "inner_cranium_frame",
        "sourceCenter": center.tolist(),
        "targetCenter": target.tolist(),
        "scale": scale,
        "enclosure": enclosure,
        "sourceBrow": brow,
        "openBand": ring,
    }


def shaft_sections(points, faces, low, high, sign):
    labels = components(points, faces)
    candidates = np.unique(labels[points[:, 0] * sign > 0])
    shell = max(
        candidates,
        key=lambda label: np.count_nonzero(
            (labels == label) & (points[:, 0] * sign > 0)
        )
        * np.ptp(points[(labels == label) & (points[:, 0] * sign > 0), 1]),
    )
    triangles = points[faces[(labels[faces] == shell).all(axis=1)]]
    triangles = triangles[triangles[:, :, 0].mean(axis=1) * sign > 0]
    rows, sections = [], []
    for y in np.linspace(low + 0.003, high - 0.003, 70):
        cut = []
        for a, b in ((0, 1), (1, 2), (2, 0)):
            start, end = triangles[:, a], triangles[:, b]
            own = (start[:, 1] - y) * (end[:, 1] - y) < 0
            t = (y - start[own, 1]) / (end[own, 1] - start[own, 1])
            cut.extend((start[own] + t[:, None] * (end[own] - start[own]))[:, [0, 2]])
        if len(cut) < 4:
            continue
        lo, hi = np.percentile(cut, [3, 97], axis=0)
        rows.append(y)
        sections.append([*(lo + hi) / 2, *np.maximum((hi - lo) * 0.40, 0.012)])
    return np.asarray(rows), np.asarray(sections)


def clip_sheet_band(points, faces, low=None, high=None, vertex_values=None):
    """Clip an open triangle sheet to exact Y planes before thickening it.

    The body triangles used to seed a backing straddle its requested band.
    Keeping those uncut triangles made the alternate leg lining reach down
    into the foot and the alternate boot lining climb above its measured cuff.
    Edge interpolation preserves the surface and creates a clean boundary;
    ``thickened_sheets`` subsequently closes that boundary.

    Optional per-vertex values follow the same edge interpolation and vertex
    compaction as positions.  The backing passes its signed, weight-derived
    leg ownership here: a broad left foot may cross ``x == 0`` without becoming
    attached to the right-leg bone chain at the new cuff vertices.
    """
    result_points = np.asarray(points, dtype=float).copy()
    result_faces = np.asarray(faces, dtype=np.int64)
    result_values = (None if vertex_values is None
                     else np.asarray(vertex_values, dtype=float))
    if result_values is not None and len(result_values) != len(result_points):
        raise ValueError('Per-vertex clip values must match the point count')
    for plane, keep_above in ((low, True), (high, False)):
        if plane is None or not len(result_faces):
            continue
        signed = result_points[:, 1] - float(plane)
        on_plane = np.abs(signed) <= 1e-12
        result_points[on_plane, 1] = float(plane)
        signed[on_plane] = 0.0
        inside = signed >= -1e-12 if keep_above else signed <= 1e-12
        output = list(result_points)
        output_values = list(result_values) if result_values is not None else None
        cache = {}
        kept = []

        def intersection(i, j):
            # Reuse a vertex already on the clipping plane. Creating a second
            # index at the same position makes the fan below emit a zero-area
            # triangle when the other endpoint is outside the kept half-space.
            if signed[i] == 0.0:
                return int(i)
            if signed[j] == 0.0:
                return int(j)
            key = tuple(sorted((int(i), int(j))))
            if key not in cache:
                denominator = signed[i] - signed[j]
                t = signed[i] / denominator if abs(denominator) > 1e-12 else 0.5
                point = result_points[i] * (1.0 - t) + result_points[j] * t
                point[1] = float(plane)
                cache[key] = len(output)
                output.append(point)
                if output_values is not None:
                    output_values.append(
                        result_values[i] * (1.0 - t) + result_values[j] * t)
            return cache[key]

        for face in result_faces:
            polygon = []

            def append_vertex(index):
                index = int(index)
                if not polygon or polygon[-1] != index:
                    polygon.append(index)

            for i, j in zip(face, np.roll(face, -1)):
                if inside[i]:
                    append_vertex(i)
                if inside[i] != inside[j]:
                    append_vertex(intersection(i, j))
            if len(polygon) > 1 and polygon[0] == polygon[-1]:
                polygon.pop()
            if len(set(polygon)) >= 3:
                kept.extend([[polygon[0], polygon[k], polygon[k + 1]]
                             for k in range(1, len(polygon) - 1)])
        if not kept:
            empty = (np.empty((0, 3)),
                     np.empty((0, 3), dtype=np.int64))
            if result_values is None:
                return empty
            return (*empty, np.empty((0, *result_values.shape[1:])))
        kept = np.asarray(kept, dtype=np.int64)
        used, inverse = np.unique(kept, return_inverse=True)
        result_points = np.asarray(output)[used]
        if output_values is not None:
            result_values = np.asarray(output_values)[used]
        result_faces = inverse.reshape(-1, 3)
    if result_values is None:
        return result_points, result_faces
    return result_points, result_faces, result_values


def backing(rig, armour, faces, region, low, high, join_default_clothing=True,
            join_lower=True, exact_low=False, exact_high=False):
    """A closed stocking/trouser lining inside the artwork, with body weights."""
    p, f = rig.positions, ea.garment_faces(rig)
    c = p[f].mean(axis=1)
    removed = (c[:, 1] > low) & (c[:, 1] < high)
    in_band = (p[f, 1] > low) & (p[f, 1] < high)
    own = in_band.any(axis=1) & (np.abs(c[:, 0]) < 0.30 * rig.fit_scale)
    boundary_faces = own & ~removed
    if not join_lower:
        boundary_faces &= c[:, 1] >= high
    boundary_vertices = np.unique(f[boundary_faces])
    f = f[own]
    used, inverse = np.unique(f, return_inverse=True)
    p, f = p[used].copy(), inverse.reshape(-1, 3)
    _, first, weld = np.unique(np.round(p, 6), axis=0, return_index=True, return_inverse=True)
    # A UV seam may have several source indices at the same position. Carry
    # boundary membership across the weld before selecting a representative.
    boundary = np.zeros(len(first), dtype=bool)
    np.logical_or.at(boundary, weld, np.isin(used, boundary_vertices))
    p, used, f = p[first], used[first], weld[f]
    original_positions = p.copy()
    left_bones = [rig.joint_names.index(b + '_l') for b in ('thigh', 'calf', 'foot', 'ball')]
    right_bones = [rig.joint_names.index(b + '_r') for b in ('thigh', 'calf', 'foot', 'ball')]
    left_share = (rig.weights[used] * np.isin(rig.joints[used], left_bones)).sum(axis=1)
    right_share = (rig.weights[used] * np.isin(rig.joints[used], right_bones)).sum(axis=1)
    # Broad feet can cross x=0. The original weighted chain owns their lining;
    # projecting a vertex onto a new shaft must never switch it to the other leg.
    side_ownership = np.where(
        left_share + right_share > 0.25,
        left_share - right_share,
        np.where(p[:, 0] >= 0, 1.0, -1.0),
    )
    own_left = side_ownership >= 0.0
    _, unique = np.unique(np.sort(f, axis=1), axis=0, return_index=True)
    f = f[unique]
    art = armour[faces]
    profiles = {
        side: shaft_sections(armour, faces, low, min(high, 0.79 * rig.fit_scale), sign)
        for side, sign in [("l", 1), ("r", -1)]
    }
    for i in range(len(p)):
        side = "l" if own_left[i] else "r"
        if region == "boots" or p[i, 1] < 0.79 * rig.fit_scale:
            rows, sections = profiles[side]
            if len(rows):
                cx, cz, rx, rz = [np.interp(p[i, 1], rows, sections[:, j]) for j in range(4)]
                radial = p[i, [0, 2]] - np.array([cx, cz])
                ratio = np.linalg.norm(radial / np.array([rx, rz]))
                p[i, [0, 2]] = np.array([cx, cz]) + radial / max(1.0, ratio)
                continue
        # Above the crotch use one pelvis section. Below it each tube has its
        # own axis, including the ankle/instep transition in the stocking.
        if p[i, 1] > 0.79 * rig.fit_scale and region == "legs":
            origin = np.array([0.0, p[i, 1], -0.04 * rig.fit_scale])
        else:
            y = p[i, 1]
            origin = rig.origin("calf_" + side).copy()
            origin[1] = y
            if y < 0.18 * rig.fit_scale:
                foot = rig._region(["foot_" + side, "ball_" + side])
                origin[[0, 2]] = (foot.min(axis=0) + foot.max(axis=0))[[0, 2]] / 2
        ray = p[i] - origin
        length = np.linalg.norm(ray)
        if length < 1e-8:
            continue
        hit, _ = io.cast(origin, ray / length, art)
        factor = 0.91
        if np.isfinite(hit) and hit > 0.015 * rig.fit_scale:
            factor = min(factor, max(0.025 * rig.fit_scale, hit - 0.008 * rig.fit_scale) / length)
        p[i] = origin + ray * factor
    # Cover the shared boundary triangle too, following its original shape.
    # Otherwise a large retained pants triangle can cross below the cuff and
    # pierce a narrowed lining. Only this new underlayer changes; the body
    # resource and original armour remain intact.
    if join_default_clothing:
        p[boundary] = original_positions[boundary]
    if exact_low or exact_high:
        p, f, side_ownership = clip_sheet_band(
            p, f, low if exact_low else None, high if exact_high else None,
            side_ownership)
        # Exact cuff cuts are alternate fitted-garment joins, so no retained
        # default-clothing boundary normal is applicable after interpolation.
        boundary = np.zeros(len(p), dtype=bool)
        own_left = side_ownership >= 0.0
    n = normals(p, f)
    if join_default_clothing and not (exact_low or exact_high):
        n[boundary] = normals(original_positions, f)[boundary]
    outer, inner = p + n * 0.003 * rig.fit_scale, p + n * 0.001 * rig.fit_scale
    import equipment_seams

    if region == "legs":
        from equipment_skinning import leg_lining_weights

        j, w = leg_lining_weights(p, rig)
        swap = (p[:, 1] < 0.79 * rig.fit_scale) & ((p[:, 0] >= 0) != own_left)
        if swap.any():
            mapping = np.arange(len(rig.joint_names), dtype=np.uint16)
            for a, b in zip(left_bones, right_bones):
                mapping[a], mapping[b] = b, a
            j[swap] = mapping[j[swap]]
        # Relax the continuous seat on welded topology. Adjacent crotch points
        # must not jump from one thigh to the other at the centre line.
        j, w = equipment_seams.smooth_skin(p, f, j, w, len(rig.joint_names), strength=8.0)
    else:
        j = np.zeros((len(p), 4), dtype=np.uint16)
        w = np.zeros((len(p), 4))
        for side, sign in [("l", 1), ("r", -1)]:
            own = own_left if side == "l" else ~own_left
            if own.any():
                j[own], w[own] = rig.weights_for(
                    p[own], [bone + "_" + side for bone in ["thigh", "calf", "foot", "ball"]]
                )
        j, w = equipment_seams.smooth_skin(p, f, j, w, len(rig.joint_names), strength=2.0)
    return equipment_seams.thickened_sheets(outer, inner, n, f, j, w)


def build(source, out, rig, kind, label, span=None):
    original = source.with_name(source.name + ".orig")
    if original.exists():
        source = original
    # Reconstruct both halves of the authored legendary harness from the same
    # original; its derived sabaton source has already lost the waist datum.
    derived_boot = source.name.startswith("Eight_legendary_fantasy_sabatons__")
    if derived_boot:
        source = source.with_name(
            source.name.replace(
                "Eight_legendary_fantasy_sabatons__",
                "Eight_legendary_fantasy_leg_armor_designs__",
            )
        )
    surface, texture = io.read_source(source)
    source_doc, _ = ea.read_glb(source)
    original_material = source_doc.get("materials", [{}])[0]
    p = surface.positions.copy()
    source_left = p[:, 0] >= 0
    f = surface.indices.reshape(-1, 3)
    is_head = kind in io.SOCKET_KIND
    region = "head" if is_head else ea.garment_region(kind)
    full = source.name.startswith("Eight_legendary_fantasy_leg_armor_designs__")
    import design_fit
    body_file = io.RACES / f"{rig.source_slug}.glb"
    fit = None if is_head else design_fit.override(source, rig, body_file if body_file.exists() else None)
    used = np.arange(len(p))
    if region == "boots" and not full:
        # Meshy sometimes joins the two shoes with triangles. Separate their
        # original owners before either heel/toe frame moves; a welded bridge
        # would otherwise inherit both legs and tear during a stride.
        f = f[np.ptp(source_left[f].astype(int), axis=1) == 0]
        used, inverse = np.unique(f, return_inverse=True)
        p, surface.uvs, source_left = p[used], surface.uvs[used], source_left[used]
        f = inverse.reshape(-1, 3)
    if is_head:
        p, report = head_frame(p, f, rig, label)
    elif region == "legs" or full:
        p, report = leg_frame(p, f, rig, full)
    else:
        p, cuff, report = boot_frame(p, f, rig)
    if fit is not None:
        # The set's design fit supplies the shell. The frame above still
        # measures the body's crotch and cuff, which the cut and backing use.
        source_points = surface.positions[used]
        p = fit['positions'][used].copy()
        if full:
            # The fit is solved in idle; its rest soles still go on the weighted soles.
            seat_harness_soles(p, source_points, components(source_points, f), rig)
        report['designFit'] = {'file': fit['file'], 'sha256': fit['sha256']}
    if full:
        clipped = clip(
            p,
            np.column_stack((np.where(source_left, 1., -1.), np.zeros((len(p), 2)))),
            surface.uvs,
            f,
            0.320 * rig.fit_scale,
            above=not derived_boot,
        )
        p, side_marker, surface.uvs, f = clipped
        source_left = side_marker[:, 0] >= 0
        cuff = 0.320 * rig.fit_scale
    original_faces = f.copy()
    if region == "legs":
        groin = report["crotchY"] - .025 * rig.fit_scale
        crossing = np.ptp(source_left[f].astype(int), axis=1) > 0
        f = f[~(crossing & (p[f, 1].min(axis=1) < groin))]
    if not is_head and fit is None:
        # A design fit is already centred on the body surface, segment by segment.
        from equipment_joint_fit import align
        p, joint_fit = align(p, f, rig, region)
        report['jointFit'] = joint_fit
    surface.positions, surface.indices = p, f.ravel()
    # Clipping creates vertices; winding helpers need a matching normal array.
    surface.normals = normals(p, f)
    canonical, _, _ = io._weld(p, f)
    _, unique = np.unique(np.sort(canonical[f], axis=1), axis=0, return_index=True)
    surface.indices = f[np.sort(unique)].ravel()
    io._make_winding_coherent(surface)
    io._unwind_inverted_shells(surface)
    f = surface.indices.reshape(-1, 3)
    n = normals(p, f)
    glb = ea.EquipmentGLB(generator="Eloria anatomical equipment retarget")
    if not is_head:
        from equipment_joint_fit import FIT_VERSION
        glb.doc['asset'].setdefault('extras', {})['shaftFitVersion'] = FIT_VERSION
    material = io.textured_material(
        glb,
        label + " Base",
        texture,
        double_sided=original_material.get("doubleSided", False),
    )
    if texture and texture.startswith(b"\xff\xd8"):
        glb.doc["images"][0]["mimeType"] = "image/jpeg"
    glb.doc["materials"][material]["pbrMetallicRoughness"]["roughnessFactor"] = (
        original_material.get("pbrMetallicRoughness", {}).get("roughnessFactor", 0.8)
    )
    if is_head:
        primitive = glb.primitive(
            p - io.socket_origin(rig, 3), n, surface.uvs, f.ravel(), material
        )
        glb.mesh(label, [primitive])
        glb.doc["meshes"][-1]["extras"] = {"coversHair": not report["openBand"]}
    else:
        glb.skeleton(rig)
        joints = np.zeros((len(p), 4), dtype=np.uint16)
        weights = np.zeros((len(p), 4))
        for side, sign in [("l", 1), ("r", -1)]:
            own = source_left if side == "l" else ~source_left
            candidates = [
                "pelvis",
                "thigh_" + side,
                "calf_" + side,
                "foot_" + side,
                "ball_" + side,
            ]
            if region == "legs":
                # A trouser cuff above the ankle follows the shin. The nearby
                # toe can be the closest body surface at the front of a loose
                # cuff, but inheriting toe-off there tears the calf panel.
                candidates = ["pelvis", "thigh_" + side, "calf_" + side]
            joints[own], weights[own] = rig.weights_for(p[own], candidates)
        if region == "legs":
            hip = p[:, 1] > report["crotchY"] - .05 * rig.fit_scale
            candidates = ["pelvis", "thigh_l", "thigh_r", "calf_l", "calf_r"]
            joints[hip], weights[hip] = rig.weights_for(p[hip], candidates)
        if region in ("legs", "boots"):
            import equipment_seams
            joints, weights = equipment_seams.smooth_skin(p, f, joints, weights, len(rig.joint_names), strength=2.)
        if region == "legs":
            from equipment_skinning import constrain_legs
            joints, weights = constrain_legs(p, joints, weights, rig)
        primitive = glb.primitive(
            p, n, surface.uvs, f.ravel(), material, joints=joints, weights=weights
        )
        glb.mesh(label, [primitive], skin=0)
        lower = (
            (0.320 if full else 0.10) * rig.fit_scale
            if region == "legs"
            else min(ea.weighted_sole(rig, side) for side in ("l", "r")) - 0.005 * rig.fit_scale
        )
        upper = (
            rig.origin("spine_01")[1] + .010 * rig.fit_scale
            if region == "legs"
            else cuff - (0.0 if full else 0.008) * rig.fit_scale
        )
        b, n, uv, idx, j, w = backing(rig, p, f, region, lower, upper)
        mat = len(glb.doc["materials"])
        color = torso_remap.backing_colour(surface, texture)
        glb.doc["materials"].append(
            {
                "name": label + " Backing",
                "pbrMetallicRoughness": {
                    "baseColorFactor": color,
                    "metallicFactor": 0.0,
                    "roughnessFactor": 1.0,
                },
            }
        )
        if region == "legs":
            import equipment_seams
            panels = equipment_seams.close_cuts(p, f, original_faces, joints, weights, rig, source_left, region="legs")
            if panels is not None:
                pp, ff, jj, ww = panels
                seam = glb.primitive(pp, normals(pp, ff), pp[:, [0,1]], ff.ravel(), mat, joints=jj, weights=ww, weight_floats=True)
                glb.mesh("ReconstructedInseams", [seam], skin=0)
        lining = glb.primitive(
            b, n, uv, idx, mat, joints=j, weights=w, weight_floats=True
        )
        glb.mesh(
            "GeneratedLegBacking" if region == "legs" else "GeneratedBootBacking",
            [lining],
            skin=0,
        )
        glb.doc["meshes"][-1]["extras"] = {
            "bodyCover": [lower / rig.fit_scale, upper / rig.fit_scale, 1.0]
        }
        if region == "boots":
            # Default pants need a cuff transition. Fitted legwear already
            # supplies that join: use the stocking inside the original boot
            # instead, so the default pants' bulky calf cannot flare outside
            # it. Both fitted-garment alternates terminate at the same
            # canonical cuff; using the authored boot shaft height here left a
            # boot backing visible behind fitted trousers.
            cuff_seam = max(lower, FITTED_BOOT_CUFF_SEAM * rig.fit_scale)
            b, n, uv, idx, j, w = backing(
                rig, p, f, region, lower, cuff_seam,
                join_default_clothing=False, exact_high=True
            )
            lining = glb.primitive(
                b, n, uv, idx, mat, joints=j, weights=w, weight_floats=True
            )
            glb.mesh("GeneratedBootBackingWithLegs", [lining], skin=0)
        else:
            # Fitted footwear supplies the lower transition. Start this
            # alternate trouser backing at the shared cuff hand-off and clip
            # the seed body triangles there exactly; the visible trouser art
            # remains at its authored hem and overlaps the boot normally.
            cuff_seam = max(lower, FITTED_BOOT_CUFF_SEAM * rig.fit_scale)
            b, n, uv, idx, j, w = backing(
                rig, p, f, region, cuff_seam, upper,
                join_lower=False, exact_low=True
            )
            lining = glb.primitive(
                b, n, uv, idx, mat, joints=j, weights=w, weight_floats=True
            )
            glb.mesh("GeneratedLegBackingWithBoots", [lining], skin=0)
    glb.write(out)
    return {
        "source": source.name,
        "out": out.name,
        "kind": kind,
        "region": region,
        "attach": "socket" if is_head else "skinned",
        "vertices": len(p),
        "triangles": len(f),
        "bytes": out.stat().st_size,
        "passes": [report],
    }
