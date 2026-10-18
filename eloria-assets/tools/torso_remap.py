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
import struct
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

# The source sheets deliberately exaggerate cloth volume.  Keeping that
# volume after the hanging sleeves have been rotated into the T pose makes a
# canonical actor read as if its upper arms are nearly as wide as its chest.
# This is an authoring profile, not a runtime transform: the fitted vertices,
# normals and skin are written once into the GLB.
SLEEVE_PROFILE_T = np.array([0.0, 0.12, 0.40, 0.52, 0.62, 0.75, 1.05])
# The two added knots make the reviewed upper-arm edit return exactly to the
# previously shipped curve at t=.62.  That is before the elbow/cuff domain, so
# a shoulder revision cannot shorten an arm or resize its hand opening.
SLEEVE_PROFILE_SCALE = np.array([
    0.90, 0.82, 0.803030303030303, 0.804666666666667,
    0.811333333333333, 0.82, 0.86,
])
SHOULDER_CAP_INSET = 0.012
SLEEVE_PROFILE_LOCK_T = 0.62
SLEEVE_BACKING_CLEARANCE = 0.006
#: Centre height (fit units) of the lining's open neckline. Since 2026-10-17
#: it is also bodyCover's fourth value: the runtime (TorsoBodyCover's open
#: throat) keeps the throat skin above it, which it otherwise hid up to the
#: neck's own ring, leaving a hole under every open collar.
LINING_NECKLINE = 1.40
# Profiles used by the installed class silhouettes before the final shoulder
# review.  They are retained as data so tests can prove every new curve is
# byte-stable from the lock knot through the cuff.
REVIEWED_ARM_FIT_BASELINES = {
    'Militia_torso_armor_concept_sheet__r01_c02.glb': {
        'radial_scale': SLEEVE_PROFILE_SCALE.copy(), 'cap_inset': .012,
    },
    'Eight_leather_ranger_torso_designs__r01_c02.glb': {
        'radial_scale': SLEEVE_PROFILE_SCALE.copy(), 'cap_inset': .012,
    },
    'Eloria_Arcane_Armor_Design_Sheet__r01_c01.glb': {
        'radial_scale': np.array([
            .88, .77, .761515151515152, .767, .777333333333333, .79, .84]),
        'cap_inset': .020,
    },
    'Amberwood_Woodland_Armor_Concept_Sheet__r02_c02.glb': {
        'radial_scale': np.array([
            .86, .72, .711515151515152, .721666666666667,
            .738333333333333, .76, .82]),
        'cap_inset': .024,
    },
}
ARM_FIT_OVERRIDES = {
    # Fur and plated cap islands sit outside the welded sleeve assignment.
    # Their concept-sheet silhouettes need the stronger, still restrained,
    # authored fit requested by the in-client side-view review.
    'Amberwood_Woodland_Armor_Concept_Sheet__r02_c02.glb': {
        'radial_scale': np.array([
            .7912, .6408, .633248484848485, .678366666666667,
            .738333333333333, .76, .82]),
        'cap_inset': .034,
    },
    'Eloria_Arcane_Armor_Design_Sheet__r01_c01.glb': {
        'radial_scale': np.array([
            .7744, .6545, .639672727272727, .71331,
            .777333333333333, .79, .84]),
        'cap_inset': .048,
    },
    'Eight_leather_ranger_torso_designs__r01_c02.glb': {
        'radial_scale': np.array([
            .873, .7708, .754848484848485, .788573333333333,
            .811333333333333, .82, .86]),
        'cap_inset': .022,
    },
    'Militia_torso_armor_concept_sheet__r01_c02.glb': {
        'radial_scale': np.array([
            .819, .7216, .706666666666667, .756386666666667,
            .811333333333333, .82, .86]),
        'cap_inset': .018,
    },
}

# These factors are applied to the already packed generated backing.  Unlike
# the absolute authoring profiles above they are deltas from the reviewed
# production asset, and therefore become exactly one at the lock knot.
PACKED_BACKING_RELATIVE_PROFILES = {
    'militia_torso_armor_02': np.array([.91, .88, .88, .94, 1., 1., 1.]),
    'leather_ranger_torso_02': np.array([.97, .94, .94, .98, 1., 1., 1.]),
    'eloria_arcane_armor_01': np.array([.88, .85, .84, .93, 1., 1., 1.]),
    'amberwood_woodland_cuirass_06': np.array([.92, .89, .89, .94, 1., 1., 1.]),
}


def position_only_revision(source, out, updates):
    """Copy a packed GLB while changing selected float VEC3 byte ranges.

    Canonical equipment deliberately shares external image resources.  A full
    rebuild can accidentally externalize a second copy of those images even
    when the requested revision is geometric.  This narrow writer retains the
    original JSON chunk byte-for-byte and overwrites fixed-size POSITION and
    NORMAL accessors inside the existing BIN chunk.  The old bounds must still
    contain the revised values, which lets the JSON remain exact as well.
    """
    source, out = Path(source), Path(out)
    document, binary = ea.read_glb(source)
    raw = bytearray(source.read_bytes())
    total = struct.unpack_from('<I', raw, 8)[0]
    offset, binary_start, binary_length = 12, None, None
    while offset < total:
        length, kind = struct.unpack_from('<II', raw, offset)
        if kind == 0x004E4942:
            if binary_start is not None:
                raise ValueError('VEC3 accessor revision requires one BIN chunk')
            binary_start, binary_length = offset + 8, length
        offset += 8 + length
    if binary_start is None or binary_length != len(binary):
        raise ValueError('Could not identify the packed GLB BIN chunk')

    changed = 0
    updated = set()
    for index, values in updates.items():
        index = int(index)
        if index in updated:
            raise ValueError(f'Duplicate accessor update: {index}')
        updated.add(index)
        spec = document['accessors'][index]
        if spec['componentType'] != 5126 or spec['type'] != 'VEC3':
            raise ValueError(f'Accessor {index} is not a float VEC3')
        values = np.ascontiguousarray(values, dtype='<f4')
        if values.shape != (spec['count'], 3) or not np.isfinite(values).all():
            raise ValueError(f'Invalid replacement shape or value for accessor {index}')
        if 'min' in spec and np.any(values.min(axis=0) < np.asarray(spec['min']) - 1e-6):
            raise ValueError(f'Accessor {index} escapes its retained minimum bound')
        if 'max' in spec and np.any(values.max(axis=0) > np.asarray(spec['max']) + 1e-6):
            raise ValueError(f'Accessor {index} escapes its retained maximum bound')
        view = document['bufferViews'][spec['bufferView']]
        stride = view.get('byteStride', 12)
        start = binary_start + view.get('byteOffset', 0) + spec.get('byteOffset', 0)
        packed = values.view(np.uint8).reshape(len(values), 12)
        for row in range(len(values)):
            target = start + row * stride
            before = raw[target:target + 12]
            replacement = packed[row].tobytes()
            changed += sum(a != b for a, b in zip(before, replacement))
            raw[target:target + 12] = replacement

    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_bytes(raw)
    revised_document, revised_binary = ea.read_glb(out)
    if revised_document != document or len(raw) != source.stat().st_size:
        raise ValueError('VEC3 accessor revision changed the GLB document or size')
    for index in range(len(document.get('accessors', []))):
        before = ea.accessor_array(document, binary, index)
        after = ea.accessor_array(revised_document, revised_binary, index)
        if index in updated:
            if not np.array_equal(after, np.asarray(updates[index], dtype=np.float32)):
                raise ValueError(f'Accessor {index} replacement did not round-trip')
        elif not np.array_equal(before, after):
            raise ValueError(f'Unrelated accessor {index} changed')
    return {'accessors': sorted(updated), 'changedBytes': changed,
            'bytes': len(raw), 'documentPreserved': True}


def _area_weighted_normals(points, triangles):
    points = np.asarray(points, dtype=float)
    triangles = np.asarray(triangles, dtype=np.int64).reshape(-1, 3)
    normals = np.zeros_like(points)
    if len(triangles):
        face_normals = np.cross(
            points[triangles[:, 1]] - points[triangles[:, 0]],
            points[triangles[:, 2]] - points[triangles[:, 0]])
        for corner in range(3):
            np.add.at(normals, triangles[:, corner], face_normals)
    lengths = np.linalg.norm(normals, axis=1)
    valid = lengths > 1e-12
    normals[valid] /= lengths[valid, None]
    return normals, valid


def deformation_orientation_report(
        original_points, revised_points, triangles, minimum_cosine=.1):
    """Audit moved triangle orientation before writing a packed revision.

    POSITION-only silhouette edits are allowed to rotate a surface, but they
    must not fold an incident triangle through itself or collapse it.  The
    check is deliberately geometric and independent of authored NORMAL data;
    normals are transported only after the revised positions pass this gate.
    Existing source degeneracies are reported but excluded from the gate.
    """
    original_points = np.asarray(original_points, dtype=float)
    revised_points = np.asarray(revised_points, dtype=float)
    triangles = np.asarray(triangles, dtype=np.int64).reshape(-1, 3)
    if (original_points.shape != revised_points.shape
            or original_points.ndim != 2
            or original_points.shape[1:] != (3,)):
        raise ValueError('Expected matching original and revised POSITION VEC3 arrays')
    if len(triangles) and (triangles.min() < 0
                           or triangles.max() >= len(original_points)):
        raise ValueError('Triangle index escapes POSITION accessor')

    moved = np.any(original_points != revised_points, axis=1)
    incident = (moved[triangles].any(axis=1)
                if len(triangles) else np.zeros(0, dtype=bool))
    old_face = np.cross(
        original_points[triangles[:, 1]] - original_points[triangles[:, 0]],
        original_points[triangles[:, 2]] - original_points[triangles[:, 0]])
    new_face = np.cross(
        revised_points[triangles[:, 1]] - revised_points[triangles[:, 0]],
        revised_points[triangles[:, 2]] - revised_points[triangles[:, 0]])
    old_area = np.linalg.norm(old_face, axis=1)
    new_area = np.linalg.norm(new_face, axis=1)
    # GLB metres make 1e-12 a conservative absolute floor.  The relative
    # floor also catches a newly collapsed large source face.
    source_valid = old_area > 1e-12
    audited = incident & source_valid
    newly_degenerate = audited & (
        (new_area <= 1e-12) | (new_area <= old_area * 1e-6))
    cosine = np.ones(len(triangles), dtype=float)
    comparable = audited & ~newly_degenerate
    cosine[comparable] = np.einsum(
        'ij,ij->i', old_face[comparable], new_face[comparable]) / (
            old_area[comparable] * new_area[comparable])
    cosine[comparable] = np.clip(cosine[comparable], -1., 1.)
    unsafe = comparable & (cosine <= float(minimum_cosine))
    area_ratio = np.ones(len(triangles), dtype=float)
    area_ratio[audited] = new_area[audited] / old_area[audited]
    considered_cosines = cosine[comparable]
    return {
        'incidentFaces': int(incident.sum()),
        'auditedFaces': int(audited.sum()),
        'sourceDegenerateIncidentFaces': np.flatnonzero(
            incident & ~source_valid).astype(int).tolist(),
        'newlyDegenerateFaces': np.flatnonzero(
            newly_degenerate).astype(int).tolist(),
        'unsafeOrientationFaces': np.flatnonzero(unsafe).astype(int).tolist(),
        'minimumCosine': float(considered_cosines.min(initial=1.)),
        'minimumAreaRatio': float(area_ratio[audited].min(initial=1.)),
        'minimumAllowedCosine': float(minimum_cosine),
    }


def require_safe_deformation(
        original_points, revised_points, triangles, minimum_cosine=.1):
    """Return an orientation report or reject a folded packed deformation."""
    report = deformation_orientation_report(
        original_points, revised_points, triangles, minimum_cosine)
    if report['newlyDegenerateFaces'] or report['unsafeOrientationFaces']:
        raise ValueError(
            'Unsafe packed deformation: '
            f"newly degenerate faces {report['newlyDegenerateFaces'][:8]}, "
            f"orientation faces {report['unsafeOrientationFaces'][:8]}, "
            f"minimum cosine {report['minimumCosine']:.6f}")
    return report


def constrain_deformation_orientation(
        original_points, desired_points, triangles, minimum_cosine=.1,
        maximum_iterations=16):
    """Locally ease a baked edit until every incident face stays oriented.

    A handful of very coarse inner-sheet triangles can straddle a cuff or an
    arm-profile transition.  Discarding the whole silhouette edit for those
    faces would undo visible fit work.  Instead, halve motion on the unsafe
    face, its one-ring neighbours, and every coincident UV-split copy.  The
    operation is deterministic, topology preserving, and converges to the
    original (therefore safe) geometry if necessary.
    """
    original = np.asarray(original_points, dtype=float)
    desired = np.asarray(desired_points, dtype=float)
    triangles = np.asarray(triangles, dtype=np.int64).reshape(-1, 3)
    if original.shape != desired.shape:
        raise ValueError('Expected matching original and desired POSITION arrays')
    blend = np.ones(len(original), dtype=float)
    # Packed equipment uses split vertices along texture seams.  Quantization
    # is much tighter than the smallest authored feature and keeps those
    # copies moving identically without relying on UV topology.
    _, coincident = np.unique(
        np.round(original / 1e-6).astype(np.int64), axis=0,
        return_inverse=True)
    iterations = 0
    limited = np.zeros(len(original), dtype=bool)
    while True:
        revised = original + (desired - original) * blend[:, None]
        report = deformation_orientation_report(
            original, revised, triangles, minimum_cosine)
        bad_faces = np.asarray(
            report['newlyDegenerateFaces'] + report['unsafeOrientationFaces'],
            dtype=np.int64)
        if not len(bad_faces):
            break
        if iterations >= maximum_iterations:
            raise ValueError(
                'Could not constrain packed deformation orientation after '
                f'{maximum_iterations} iterations')
        affected = np.zeros(len(original), dtype=bool)
        affected[triangles[bad_faces].ravel()] = True
        # Ease a one-ring patch, not three isolated corners.  This avoids a
        # visible crease and prevents the next face across the edge becoming
        # the new limiting face on the following iteration.
        neighbour_faces = affected[triangles].any(axis=1)
        affected[triangles[neighbour_faces].ravel()] = True
        affected = np.isin(coincident, np.unique(coincident[affected]))
        blend[affected] *= .5
        limited |= affected
        iterations += 1
    motion = np.linalg.norm(desired - original, axis=1)
    residual = np.linalg.norm(revised - original, axis=1)
    return revised, {
        'iterations': iterations,
        'limitedVertices': int(limited.sum()),
        'minimumBlend': float(blend[limited].min(initial=1.)),
        'maximumSuppressedMove': float((motion - residual).max(initial=0.)),
        'orientation': report,
    }


def transport_normals_across_deformation(
        original_points, revised_points, normals, triangles):
    """Rotate authored normals with the local geometric surface deformation.

    Only vertices incident to a moved face are touched.  Applying the minimal
    rotation between old and new area-weighted geometric normals preserves
    deliberate authored smoothing (including inner-sheet orientation) while
    preventing stale lighting on baked silhouette and cuff edits.
    """
    original_points = np.asarray(original_points, dtype=float)
    revised_points = np.asarray(revised_points, dtype=float)
    original_normals = np.asarray(normals, dtype=float)
    triangles = np.asarray(triangles, dtype=np.int64).reshape(-1, 3)
    if (original_points.shape != revised_points.shape
            or original_points.shape != original_normals.shape
            or original_points.ndim != 2
            or original_points.shape[1:] != (3,)):
        raise ValueError('Expected matching POSITION/NORMAL VEC3 arrays')
    moved = np.any(original_points != revised_points, axis=1)
    incident_mask = (moved[triangles].any(axis=1)
                     if len(triangles) else np.zeros(0, dtype=bool))
    vertices = (np.unique(triangles[incident_mask])
                if incident_mask.any() else np.empty(0, dtype=int))
    revised_normals = original_normals.copy()
    if not len(vertices):
        return revised_normals, {
            'incidentFaces': 0, 'movedNormals': 0, 'maximumRotationDegrees': 0.,
            'maximumAlignmentDelta': 0., 'vertexIndices': []}

    old_geometric, old_valid = _area_weighted_normals(
        original_points, triangles)
    new_geometric, new_valid = _area_weighted_normals(
        revised_points, triangles)
    valid = old_valid[vertices] & new_valid[vertices]
    if not valid.all():
        raise ValueError('Deformation creates a degenerate incident normal')
    source, target = old_geometric[vertices], new_geometric[vertices]
    axes_sine = np.cross(source, target)
    cosine = np.clip(np.einsum('ij,ij->i', source, target), -1., 1.)
    sine_squared = np.einsum('ij,ij->i', axes_sine, axes_sine)
    rotated = original_normals[vertices].copy()
    regular = sine_squared > 1e-20
    if regular.any():
        first = np.cross(axes_sine[regular], rotated[regular])
        second = np.cross(axes_sine[regular], first)
        rotated[regular] += first + second * (
            (1. - cosine[regular]) / sine_squared[regular])[:, None]
    opposite = (~regular) & (cosine < 0.)
    for row in np.flatnonzero(opposite):
        basis = np.zeros(3)
        basis[int(np.argmin(np.abs(source[row])))] = 1.
        axis = np.cross(source[row], basis)
        axis /= np.linalg.norm(axis)
        rotated[row] = 2. * axis * np.dot(axis, rotated[row]) - rotated[row]
    lengths = np.linalg.norm(rotated, axis=1)
    if np.any(lengths <= 1e-12):
        raise ValueError('Normal transport produced a zero-length normal')
    rotated /= lengths[:, None]
    revised_normals[vertices] = rotated
    old_alignment = np.einsum(
        'ij,ij->i', original_normals[vertices], source)
    new_alignment = np.einsum('ij,ij->i', rotated, target)
    normal_cosine = np.clip(np.einsum(
        'ij,ij->i', original_normals[vertices], rotated), -1., 1.)
    return revised_normals, {
        'incidentFaces': int(incident_mask.sum()),
        'movedNormals': int(len(vertices)),
        'maximumRotationDegrees': float(np.degrees(
            np.arccos(normal_cosine)).max(initial=0.)),
        'maximumAlignmentDelta': float(np.max(
            np.abs(new_alignment - old_alignment), initial=0.)),
        'vertexIndices': vertices.astype(int).tolist(),
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


def source_skeleton(points, triangles=None):
    height = np.ptp(points[:, 1])
    top = float(points[:, 1].max())
    middle_x = float((points[:, 0].min() + points[:, 0].max()) / 2)
    if triangles is not None:
        canonical, edges, count = io._weld(points, triangles)
        labels = io._components(edges, count)
        sizes = np.bincount(labels)
        # Thin ties and loose trim below a cuff are not wrist landmarks.
        # Count welded positions, so UV splits cannot change the measurement.
        stable = sizes[labels[canonical]] >= 12
        if stable.any():
            points = points[stable]
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


def connected_sleeve(points, triangles, side, height, shoulder_y, wrist_y):
    """Separate sewn sleeves along their surface instead of slicing the tube.

    An inner sleeve wall can have the same X as the chest. Distance through
    the welded cloth keeps that wall with its cuff, including broad folds.
    """
    from scipy.sparse import coo_matrix
    from scipy.sparse.csgraph import dijkstra
    canonical, edges, count = io._weld(points, triangles)
    _, first = np.unique(canonical, return_index=True)
    p = points[first]
    sign = 1. if side == 'l' else -1.
    x = p[:, 0] * sign / height
    seeds = (x > .285) & (p[:, 1] < shoulder_y - .10 * height)
    seeds &= p[:, 1] > wrist_y - .04 * height
    trunk = (np.abs(p[:, 0]) < .15 * height) | (p[:, 1] > shoulder_y + .04 * height)
    trunk |= (p[:, 1] < wrist_y - .06 * height) & (x < .27)
    if not seeds.any() or not trunk.any():
        return None
    lengths = np.maximum(np.linalg.norm(p[edges[:, 0]] - p[edges[:, 1]], axis=1), 1e-8)
    graph = coo_matrix((np.r_[lengths, lengths],
        (np.r_[edges[:, 0], edges[:, 1]], np.r_[edges[:, 1], edges[:, 0]])), shape=(count, count)).tocsr()
    arm_distance = dijkstra(graph, indices=np.flatnonzero(seeds), min_only=True)
    trunk_distance = dijkstra(graph, indices=np.flatnonzero(trunk), min_only=True)
    own = (arm_distance < trunk_distance) & (x > .17)
    own &= p[:, 1] >= wrist_y - .04 * height
    return own[canonical].astype(float)


def settle_cloth_sleeve(points, selected, rig, side, shoulder_blend=(.05, .20)):
    """Center connected cloth bands on the arm without changing hard cuffs.

    Fused flank folds are no longer the side of a sleeve after retargeting.
    Apply a smooth band transform, keeping the ring's folds and UV topology.
    """
    root, wrist = rig.origin('upperarm_' + side), rig.origin('hand_' + side)
    axis = wrist - root
    direction = axis / np.linalg.norm(axis)
    travel = (points - root) @ axis / (axis @ axis)
    radial = points - root - travel[:, None] * axis
    stations = np.linspace(.08, 1., 16)
    centers = np.zeros((len(stations), 3))
    scales = np.ones(len(stations))
    valid = np.zeros(len(stations), dtype=bool)
    for row, t in enumerate(stations):
        own = selected & (np.abs(travel - t) < .10)
        if own.sum() < 6:
            continue
        block = radial[own]
        center = (np.percentile(block, 5, axis=0) + np.percentile(block, 95, axis=0)) / 2
        center -= direction * (center @ direction)
        radius = np.percentile(np.linalg.norm(block - center, axis=1), 80)
        want = np.interp(t, [0., .35, .60, 1.], [.065, .060, .052, .045]) * rig.fit_scale
        centers[row] = center
        scales[row] = np.clip(want / max(radius, .01 * rig.fit_scale), .65, 1.35)
        valid[row] = True
    if not valid.any():
        return
    for col in range(3):
        centers[:, col] = np.interp(stations, stations[valid], centers[valid, col])
    scales[:] = np.interp(stations, stations[valid], scales[valid])
    for _ in range(2):
        for col in range(3):
            centers[:, col] = np.convolve(np.pad(centers[:, col], 1, mode='edge'), [.25, .5, .25], mode='valid')
        scales[:] = np.convolve(np.pad(scales, 1, mode='edge'), [.25, .5, .25], mode='valid')
    own = np.flatnonzero(selected)
    center = np.column_stack([np.interp(travel[own], stations, centers[:, col]) for col in range(3)])
    factor = np.interp(travel[own], stations, scales)
    blend = np.clip((travel[own] - shoulder_blend[0]) / (shoulder_blend[1] - shoulder_blend[0]), 0., 1.)
    corrected = (radial[own] - center) * factor[:, None]
    points[own] += (corrected - radial[own]) * blend[:, None]


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


def tighten_arm_silhouette(points, rig, arm_share, cap_side,
                           radial_scale=None, cap_inset=None,
                           locked_from=None, cap_locked_from=None):
    """Bake a restrained heroic arm profile into the fitted torso artwork.

    ``remap`` has already put each sleeve on the canonical shoulder-to-hand
    axis.  Scaling only the component perpendicular to that axis keeps cuff
    length, UVs and the hand opening unchanged while removing the inflated
    upper-arm silhouette inherited from the concept-sheet pose.  When
    ``locked_from`` is supplied, skinned sleeve vertices at or beyond that
    normalized arm travel are not reassigned at all; this keeps their packed
    float bytes exact rather than merely recomputing the same values.
    ``cap_locked_from`` independently protects detached cap rows.  The split
    matters for fresh authoring builds: their sleeve tail still needs the
    previously reviewed absolute profile, while cap islands past the lock
    must not inherit a stronger shoulder inset.  Detached shoulder plates
    otherwise remain rigid and are only seated slightly inboard; their
    authored relief is not flattened.
    """
    radial_scale = (SLEEVE_PROFILE_SCALE if radial_scale is None
                    else np.asarray(radial_scale, dtype=float))
    if radial_scale.shape != SLEEVE_PROFILE_SCALE.shape:
        raise ValueError('Arm radial profile must match SLEEVE_PROFILE_T')
    cap_inset = SHOULDER_CAP_INSET if cap_inset is None else float(cap_inset)
    if locked_from is not None:
        locked_from = float(locked_from)
    if cap_locked_from is None:
        cap_locked_from = locked_from
    elif cap_locked_from is not None:
        cap_locked_from = float(cap_locked_from)
    moved = 0
    caps = 0
    locked = 0
    locked_caps = 0
    maximum = 0.0
    for col, (side, sign) in enumerate((('l', 1.0), ('r', -1.0))):
        root = rig.origin('upperarm_' + side)
        wrist = rig.origin('hand_' + side)
        axis = wrist - root
        length2 = float(axis @ axis)
        own = arm_share[:, col] > .5
        if own.any() and length2 > 1e-10:
            indices = np.flatnonzero(own)
            before = points[indices].copy()
            travel = (before - root) @ axis / length2
            centre_line = root + travel[:, None] * axis
            radial = before - centre_line
            scale = np.interp(np.clip(travel, SLEEVE_PROFILE_T[0],
                                      SLEEVE_PROFILE_T[-1]),
                              SLEEVE_PROFILE_T, radial_scale)
            active = (np.ones(len(indices), dtype=bool)
                      if locked_from is None else travel < locked_from)
            revised = centre_line + radial * scale[:, None]
            points[indices[active]] = revised[active]
            locked += int((~active).sum())
            motion = np.linalg.norm(points[indices] - before, axis=1)
            moved += int(np.count_nonzero(motion > 1e-8))
            maximum = max(maximum, float(motion.max(initial=0.0)))
        cap = cap_side == col
        if cap.any():
            if cap_locked_from is not None and length2 > 1e-10:
                cap_indices = np.flatnonzero(cap)
                cap_travel = ((points[cap_indices] - root) @ axis / length2)
                cap_active = cap_travel < cap_locked_from
                locked_caps += int((~cap_active).sum())
                cap = np.zeros(len(points), dtype=bool)
                cap[cap_indices[cap_active]] = True
            # Earlier revisions pushed every cap 25 mm outboard.  Once the
            # source sleeve is mapped to the real shoulder that allowance is
            # no longer needed, and is the principal cause of shelf-like
            # shoulders.  Translate whole islands so plate proportions and
            # texture seams remain exact.  The elbow/cuff lock applies to cap
            # rows too: decorative islands can extend beyond the shoulder and
            # must not bypass the byte-stable tail invariant.
        if cap.any():
            points[cap, 0] -= sign * cap_inset * rig.fit_scale
            caps += int(np.count_nonzero(cap))
            moved += int(np.count_nonzero(cap))
            maximum = max(maximum, cap_inset * rig.fit_scale)
    return {'name': 'restrained_arm_silhouette', 'movedVertices': moved,
            'capVertices': caps, 'maximumMove': maximum,
            'radialScale': radial_scale.tolist(),
            'capInset': cap_inset * rig.fit_scale,
            'lockedFrom': locked_from,
            'capLockedFrom': cap_locked_from,
            'lockedVertices': locked,
            'lockedCapVertices': locked_caps}


def seat_arm_backing_inside_visible(
        points, rig, arm_share, visible_faces_by_side,
        clearance=SLEEVE_BACKING_CLEARANCE,
        locked_from=SLEEVE_PROFILE_LOCK_T, enforce=True, triangles=None):
    """Recess packed sleeve backing beneath the visible authored shell.

    A radial ray is measured from each canonical arm axis through each backing
    vertex.  Only rays that actually meet the corresponding skinned visible
    sleeve are constrained, so deliberately exposed lining remains authored
    rather than being mistaken for a clearance failure.  The elbow/cuff tail
    is an exact no-write region.
    """
    points = np.asarray(points)
    arm_share = np.asarray(arm_share, dtype=float)
    if arm_share.shape != (len(points), 2):
        raise ValueError('Expected one left/right arm-share pair per vertex')
    if len(visible_faces_by_side) != 2:
        raise ValueError('Expected visible sleeve faces for left and right')
    clearance_distance = float(clearance) * rig.fit_scale
    moved = 0
    covered = 0
    locked = 0
    minimum_before = np.inf
    minimum_after = np.inf
    maximum_move = 0.0
    ignored_near_axis = 0
    ignored_exposed = 0
    required = np.zeros(len(points), dtype=float)
    active = np.zeros(len(points), dtype=bool)
    centres = np.zeros_like(points, dtype=float)
    radial_vectors = np.zeros_like(points, dtype=float)
    radii = np.zeros(len(points), dtype=float)
    hits = np.full(len(points), np.inf)
    covered_rows = np.zeros(len(points), dtype=bool)
    travels = np.full(len(points), np.inf)
    arm_columns = np.full(len(points), -1, dtype=int)
    for column, side in enumerate(('l', 'r')):
        faces = np.asarray(visible_faces_by_side[column], dtype=float)
        if not len(faces):
            continue
        root = rig.origin('upperarm_' + side)
        wrist = rig.origin('hand_' + side)
        axis = wrist - root
        length2 = float(axis @ axis)
        indices = np.flatnonzero(arm_share[:, column] > .5)
        for index in indices:
            offset = points[index] - root
            travel = float(offset @ axis / length2)
            if travel >= locked_from:
                locked += 1
                continue
            centre = root + travel * axis
            radial = points[index] - centre
            radius = float(np.linalg.norm(radial))
            if radius <= 1e-10:
                continue
            active[index] = True
            travels[index] = travel
            arm_columns[index] = column
            centres[index] = centre
            radial_vectors[index] = radial
            radii[index] = radius
            hit, _ = io.cast(centre, radial / radius, faces)
            if not np.isfinite(hit):
                continue
            # A triangle crossing the arm axis is not an enclosing sleeve
            # wall.  Treat that incidental bridge/inner flap as uncovered;
            # there is physically no room for an arm backing inside it.
            if hit <= max(clearance_distance + 1e-6,
                          .012 * rig.fit_scale):
                ignored_near_axis += 1
                continue
            # If the lining is already outside the first visible hit, that
            # authored sector is exposed backing rather than a covered sleeve.
            # Pulling it through the shell would create a local fold and would
            # falsely turn an intentional quilted panel into hidden lining.
            if hit + 1e-6 < radius:
                ignored_exposed += 1
                continue
            covered += 1
            covered_rows[index] = True
            hits[index] = hit
            minimum_before = min(minimum_before, hit - radius)
            target = hit - clearance_distance
            if target <= 1e-6:
                raise ValueError(
                    'Visible sleeve cannot contain the required backing '
                    f'clearance at vertex {index}')
            required[index] = max(0., radius - target)
    applied_profiles = []
    if enforce:
        knots = SLEEVE_PROFILE_T[SLEEVE_PROFILE_T <= locked_from]
        for column in range(2):
            values = np.ones(len(knots), dtype=float)
            rows = np.flatnonzero(covered_rows & (arm_columns == column)
                                  & (required > 0.))
            # Solve a monotone set of interpolation upper bounds.  A single
            # travel profile moves all angular sectors coherently, avoiding
            # the folds created by independent per-ray offsets.
            for _ in range(12):
                changed = False
                for index in rows:
                    travel = travels[index]
                    interval = int(np.searchsorted(knots, travel, side='right') - 1)
                    interval = int(np.clip(interval, 0, len(knots) - 2))
                    span = knots[interval + 1] - knots[interval]
                    right = np.clip((travel - knots[interval]) / span, 0., 1.)
                    left = 1. - right
                    limit = ((hits[index] - clearance_distance)
                             / radii[index])
                    current = left*values[interval] + right*values[interval + 1]
                    if current <= limit + 1e-12:
                        continue
                    excess = current - limit
                    if interval + 1 == len(knots) - 1:
                        if left <= 1e-8:
                            raise ValueError(
                                'Required backing clearance reaches the '
                                'immutable cuff boundary')
                        values[interval] -= excess / left
                    else:
                        values[interval] -= excess
                        values[interval + 1] -= excess
                    changed = True
                if not changed:
                    break
            if np.any(values[:-1] <= .25):
                raise ValueError('Backing clearance requires an unsafe arm scale')
            values[-1] = 1.
            applied_profiles.append(values.tolist())
            indices = np.flatnonzero(active & (arm_columns == column))
            scales = np.interp(travels[indices], knots, values)
            revised_radius = radii[indices] * scales
            points[indices] = (centres[indices] + radial_vectors[indices]
                               * scales[:, None])
            motion = radii[indices] - revised_radius
            moved += int(np.count_nonzero(motion > 1e-10))
            maximum_move = max(maximum_move, float(motion.max(initial=0.)))
            radii[indices] = revised_radius
    for index in np.flatnonzero(covered_rows):
        minimum_after = min(minimum_after, hits[index] - radii[index])
    if covered and minimum_after + 1e-9 < clearance_distance:
        raise ValueError(
            f'Backing clearance {minimum_after:.9f} is below '
            f'{clearance_distance:.9f}')
    return {
        'name': 'visible_sleeve_backing_clearance',
        'coveredRays': covered,
        'movedVertices': moved,
        'lockedVertices': locked,
        'ignoredNearAxisRays': ignored_near_axis,
        'ignoredExposedRays': ignored_exposed,
        'lockedFrom': float(locked_from),
        'requiredClearance': clearance_distance,
        'minimumClearanceBefore': (None if not covered
                                   else float(minimum_before)),
        'minimumClearanceAfter': (None if not covered
                                  else float(minimum_after)),
        'maximumMove': maximum_move,
        'enforced': bool(enforce),
        'radialProfiles': applied_profiles,
    }


def loose_ties(points, triangles, labels, source, source_height):
    """Triangles of tiny isolated ties hanging far below the measured cuff.

    After the arm scale is corrected they become long floating spikes, or float
    beside the hand. Only those narrow, disconnected fragments are marked;
    ordinary trim and hem tabs stay intact.
    """
    drop = np.zeros(len(triangles), dtype=bool)
    for label in np.unique(labels):
        own = labels == label
        block = np.unique(np.round(points[own], 5), axis=0)
        if len(block) > 8 or np.ptp(block[:, 0]) > .025 * source_height:
            continue
        side = 'l' if block[:, 0].mean() > 0 else 'r'
        if (abs(block[:, 0].mean()) > .23 * source_height
                and block[:, 1].min() < source[side][1][1] - .12 * source_height
                and block[:, 1].max() < source[side][1][1]):
            drop |= own[triangles].any(axis=1)
    return drop


def buried_fragments(points, triangles, labels, rig, depth=.03, largest=64):
    """Triangles of small loose fragments the fit carries through the throat.

    Added 2026-10-17.  Some sources carry small loose pieces, a strap end or an
    inner fold, that a set fit lands inside the body: the Warden coat's
    28-vertex throat fragment ran 9 cm deep into the neck.  The cover hid the
    skin around it until the throat stayed visible under open collars
    (TorsoBodyCover's open throat, LINING_NECKLINE); then it cut across the
    neck as a black band.  A component of at most ``largest`` welded vertices
    centred in that open throat (in front of the neck axis, within 13 cm of the
    midline, from 2 cm below the neckline to 1.52 m) with a vertex there more
    than ``depth`` inside the skin, along the ray from the neck axis, is dropped.
    Trim elsewhere that merely dips into the skin (studs, buckles, fur tufts
    over the shoulders) stays: the cover still hides the skin there.
    """
    s = rig.fit_scale
    skin = rig.positions[rig.faces]
    drop = np.zeros(len(triangles), dtype=bool)
    axis_z = lambda y: (-.051 + (y / s - 1.452) / (1.568 - 1.452) * .062) * s
    throat = lambda p: ((LINING_NECKLINE - .02) * s < p[1] < 1.52 * s and abs(p[0]) < .13 * s
                        and p[2] >= axis_z(p[1]))
    for label in np.unique(labels):
        own = np.flatnonzero(labels == label)
        if len(np.unique(np.round(points[own], 5), axis=0)) > largest or not throat(points[own].mean(0)):
            continue
        for v in own:
            p = points[v]
            if not throat(p):
                continue
            origin = np.array([0., p[1], axis_z(p[1])])
            ray = p - origin
            radius = float(np.linalg.norm(ray))
            hit = io.cast(origin, ray / radius, skin)[0] if radius > 1e-6 else np.inf
            if radius < 1e-6 or (np.isfinite(hit) and radius < hit - depth * s):
                drop |= np.isin(triangles, own).any(axis=1)
                break
    return drop


def remap(points, triangles, rig, collar_lift=0., parts_out=None,
          arm_fit=None, split_sewn_surface=True):
    canon, edges, count = io._weld(points, triangles)
    labels = io._components(edges, count)[canon]
    source = source_skeleton(points, triangles)
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
                # Outboard cloth belongs to the sleeve even when a broad source
                # radius falls outside the initial arm cylinder. Keep the
                # existing medial seam and the source cuff/hem separation.
                outer = np.clip((block[:, 0] * sign / source_height - .30) / .035, 0., 1.)
                outer *= (block[:, 1] >= wrist[1] - .02 * source_height)
                blend = np.maximum(blend, outer)
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
                # Use global indices for the welded source component.
                faces = triangles[own[triangles].all(axis=1)]
                sewn = (connected_sleeve(points, faces, side, source_height, shoulder_y, wrist[1])
                        if split_sewn_surface else None)
                if sewn is not None:
                    # Preserve the authored vest/shoulder yoke. The surface
                    # split corrects sleeve walls below that attachment.
                    blend = np.where(block[:, 1] < shoulder_y - .06 * source_height,
                                     sewn[own], blend)
                out[own] += (arm[own] - trunk[own]) * blend[:, None]
                arm_share[own, col] = blend
                continue
            if centroid[0] * sign < 0:
                continue
            if centroid[0] * sign < .17 * source_height:
                continue
            # Independent hem tabs stay with the trunk. Their outboard X
            # alone does not make them cuffs when they sit well below the arm.
            if block[:, 1].max() < wrist[1] - .16 * source_height:
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
        sewn = np.zeros(len(points), dtype=bool)
        for label in np.unique(labels):
            own = labels == label
            if points[own, 0].min() < -.075 * source_height and points[own, 0].max() > .075 * source_height:
                sewn |= own & (arm_share[:, col] > .5)
        settle_cloth_sleeve(out, sewn, rig, side)
    arm_fit = arm_fit or {}
    arm_profile = tighten_arm_silhouette(out, rig, arm_share, cap_side,
                                         arm_fit.get('radial_scale'),
                                         arm_fit.get('cap_inset'),
                                         cap_locked_from=SLEEVE_PROFILE_LOCK_T)
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
    keep &= ~loose_ties(points, triangles, labels, source, source_height)
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
            arm_profile,
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


def clip_lining_neckline(points, faces, scale):
    """An open central neckline that keeps the lining's shoulder coverage.

    Intersections lie on original triangle edges. Nothing is flattened or
    pushed through a closed shell: thickness and binding are added afterwards.
    """
    # Only the central throat is open. A horizontal ceiling across the arms
    # amputates the shoulder roof and leaves a hole behind raised sleeves.
    height = (LINING_NECKLINE + 1.5 * np.maximum(0., np.abs(points[:, 0]) / scale - .08)) * scale
    points, faces, _ = clip_open_sheet(points, faces, points[:, 1] - height)
    return points, faces


def clip_open_sheet(points, faces, signed):
    """Keep the part of a sheet where ``signed <= 0``, cut exactly on its edges.

    Returns the kept points, their faces and, per kept point, the input point
    it came from (for a new point on a cut edge, the edge's kept end).
    """
    inside = signed <= 0.
    output = list(points)
    origin = list(range(len(points)))
    cache, kept = {}, []
    def intersection(i, j):
        key = tuple(sorted((int(i), int(j))))
        if key not in cache:
            t = signed[i] / (signed[i] - signed[j])
            cache[key] = len(output)
            output.append(points[i] * (1-t) + points[j] * t)
            origin.append(int(i) if inside[i] else int(j))
        return cache[key]
    for face in faces:
        polygon = []
        for i, j in zip(face, np.roll(face, -1)):
            if inside[i]: polygon.append(int(i))
            if inside[i] != inside[j]: polygon.append(intersection(i, j))
        kept.extend([[polygon[0], polygon[k], polygon[k+1]] for k in range(1, len(polygon)-1)])
    kept = np.asarray(kept, dtype=np.int64).reshape(-1, 3)
    used, inverse = np.unique(kept, return_inverse=True)
    return np.asarray(output)[used], inverse.reshape(-1, 3), np.asarray(origin)[used]


def lining_wrist(rig):
    """Rest-pose |x| of the wrist plane each fitted sleeve lining ends on."""
    return min(abs(rig.origin('hand_' + side)[0]) for side in ['l', 'r']) - .008 * rig.fit_scale


def wrist_cover(rig):
    """The bodyCover wrist edge that leaves no hole past the lining's end.

    The runtime (TorsoBodyCover) hides each body triangle whose rest centre
    lies inside the cover. A wrist triangle can reach past its centre by
    2.5 cm on the male body, so a cover edge on the lining's own plane hid skin
    beyond the lining and the cuff showed a fringe of holes at the hand. The
    edge is therefore just short of the nearest centre of any band triangle
    that crosses the lining's plane. Skin between it and the plane stays, and
    `lining` keeps it inside the sleeve lining. Half a millimetre short: on
    the centre itself, that triangle sat on the cover's strict edge, kept on
    the Human body and cut on a race body whose rest skeleton differs by a few
    micrometres (torso_body_cover.gd's face-for-face match, 2026-10-17).
    """
    cut = lining_wrist(rig)
    faces = rig.faces
    corner = rig.positions[faces]
    centre = corner.mean(axis=1)
    band = (centre[:, 1] > .95 * rig.fit_scale) & (centre[:, 1] < 1.535 * rig.fit_scale)
    crossing = band & (np.abs(corner[:, :, 0]).max(axis=1) > cut) & (np.abs(centre[:, 0]) < cut)
    return float(min(cut, np.abs(centre[crossing, 0]).min() - .0005 * rig.fit_scale)) if crossing.any() else cut


def lining(rig, armour, triangles, binding_rig=None):
    """A closed fitted backing with continuous anatomical sleeve weights."""
    points, faces = rig.positions, ea.garment_faces(rig, 'torso')
    skin_faces = points[faces]
    centre = skin_faces.mean(axis=1)
    keep = (centre[:, 1] > .95 * rig.fit_scale) & (centre[:, 1] < 1.535 * rig.fit_scale)
    cut, cover = lining_wrist(rig), wrist_cover(rig)
    # End each sleeve on the wrist plane, cut exactly. Keeping whole
    # triangles by centre left shirt-cuff and wrist-skin spikes up to 2 cm
    # past the cut, which showed inside wide cuffs.
    keep &= np.abs(points[faces, 0]).min(axis=1) < cut
    points, faces, used = clip_open_sheet(points, faces[keep], np.abs(points[:, 0]) - cut)
    points = points.copy()
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
        # Between the cover edge and the lining's end the body stays visible
        # (see wrist_cover): the lining's last stretch holds that skin inside.
        sign = 1 if side == 'l' else -1
        wrist_skin = skin_faces[(skin_faces[:, :, 0].mean(axis=1) * sign > cover - .03 * rig.fit_scale)
                                & (skin_faces[:, :, 0].mean(axis=1) * sign < cut + .03 * rig.fit_scale)]
        near_hand = points[own, 0] * sign > cover - .015 * rig.fit_scale
        for row, (origin, ray, length) in enumerate(zip(centre_line, radial, radius)):
            if length < 1e-8:
                continue
            if near_hand[row] and len(wrist_skin):
                skin, _ = io.cast(origin, ray / length, wrist_skin)
                if np.isfinite(skin) and skin < .09 * rig.fit_scale:
                    want[row] = max(want[row], skin + .003 * rig.fit_scale)
            hit, _ = io.cast(origin, ray / length, sleeve_faces)
            if np.isfinite(hit) and .012 * rig.fit_scale < hit < .16 * rig.fit_scale:
                # Fill the shoulder seam just inside the artwork. Recessing this
                # to 75% of the inner radius exposed a deep underarm cavity.
                # This is a new open sheet; give it thickness only after fitting.
                inside = max(
                    .015 * rig.fit_scale,
                    hit - SLEEVE_BACKING_CLEARANCE * rig.fit_scale)
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
    # Cut the open sheet before thickening. The default shirt has folded
    # collar facets inside its face selection; levelling only its boundary or
    # clipping at the old high neck plane leaves those facets in the throat.
    points, faces = clip_lining_neckline(points, faces, rig.fit_scale)
    normals = np.zeros_like(points)
    face_normals = np.cross(points[faces[:, 1]] - points[faces[:, 0]], points[faces[:, 2]] - points[faces[:, 0]])
    for col in range(3): np.add.at(normals, faces[:, col], face_normals)
    normals /= np.maximum(np.linalg.norm(normals, axis=1, keepdims=True), 1e-10)
    outer, inner = points + normals * .004, points + normals * .001
    import equipment_seams
    # Bind the fitted lining, not the loose shirt positions it came from.
    j, w = lining_weights(points, binding_rig or rig)
    return equipment_seams.thickened_sheets(outer, inner, normals, faces, j, w)


def art_lining_weights(points, joints, weights, art, art_joints, art_weights, rig, neighbours=6,
                       sleeveless=False):
    """Lining weights from the art it lies under, for a design-fit torso.

    Added 2026-10-17 (owner's third review, notes 7-9, 12-14). lining_weights
    binds the lining with its own continuous arm field and the body's trunk
    weights, but a design-fit coat binds its art differently (bind_sleeves'
    seam blend, the twist on the waist), so in a drawn bow or a walk the lining
    rose with the arm, or stayed with the hips, while the art over it did not,
    and showed through the coat's sides and back. Each lining vertex now takes
    the blend of its nearest art vertices (rest pose, inverse distance
    squared). Over the forearm's last stretch, where the lining holds the
    wrist skin (wrist_cover), it keeps lining_weights' own binding.

    ``sleeveless`` (2026-10-18, a vest whose design fit gives no vertex to an
    arm): no art lies over the arms, so the nearest art is the vest and the
    arm lining stayed in the rest pose with the trunk. There the lining keeps
    its own arm field (lining_weights' arm region) as well.
    """
    from scipy.spatial import cKDTree
    from equipment_skinning import smoothstep
    count = len(rig.joint_names)
    distance, index = cKDTree(art).query(points, k=neighbours)
    near = 1. / np.maximum(distance, 1e-4) ** 2
    near /= near.sum(axis=1, keepdims=True)
    dense = np.zeros((len(points), count))
    for k in range(neighbours):
        for slot in range(art_joints.shape[1]):
            np.add.at(dense, (np.arange(len(points)), art_joints[index[:, k], slot].astype(int)),
                      near[:, k] * art_weights[index[:, k], slot])
    own = np.zeros((len(points), count))
    for slot in range(joints.shape[1]):
        np.add.at(own, (np.arange(len(points)), joints[:, slot].astype(int)), weights[:, slot])
    keep = np.zeros(len(points))
    for side in "lr":
        root, wrist = rig.origin('upperarm_' + side), rig.origin('hand_' + side)
        axis = wrist - root
        travel = (points - root) @ axis / (axis @ axis)
        keep = np.maximum(keep, smoothstep(travel, .7, .85) * ((points[:, 0] > 0) == (side == 'l')))
    if sleeveless:
        keep = np.maximum(keep, smoothstep(np.abs(points[:, 0]) / rig.fit_scale, .13, .245)
                          * smoothstep(points[:, 1] / rig.fit_scale, 1.28, 1.40))
    dense = (1 - keep)[:, None] * dense + keep[:, None] * own
    j = np.argsort(-dense, axis=1)[:, :4]
    w = np.take_along_axis(dense, j, axis=1)
    w /= np.maximum(w.sum(axis=1, keepdims=True), 1e-12)
    return j.astype(np.uint16), w


def lining_weights(points, rig):
    """Use one continuous arm field around each reconstructed sleeve ring.

    The fitted lining has moved away from the loose source shirt. Nearest
    shirt vertices can put one side of a ring on the chest and the other on
    the elbow, pinching the cloth when the arm drops.
    """
    from equipment_skinning import smoothstep
    j, w = rig.weights_for(points, list(ea.TORSO_BONES))
    dense = np.zeros((len(points), len(rig.joint_names)))
    arm = smoothstep(np.abs(points[:, 0]) / rig.fit_scale, .13, .245)
    arm *= smoothstep(points[:, 1] / rig.fit_scale, 1.28, 1.40)
    for slot in range(4):
        dense[np.arange(len(points)), j[:, slot]] += w[:, slot] * (1 - arm)
    for side, sign in [('l', 1.), ('r', -1.)]:
        root, wrist = rig.origin('upperarm_' + side), rig.origin('hand_' + side)
        axis = wrist - root
        travel = (points - root) @ axis / (axis @ axis)
        lower = smoothstep(travel, .43, .59)
        share = arm * (points[:, 0] * sign > 0)
        dense[:, rig.joint_names.index('upperarm_' + side)] += share * (1 - lower)
        dense[:, rig.joint_names.index('lowerarm_' + side)] += share * lower
        # Over its last stretch the lining holds wrist skin (see wrist_cover)
        # that bends with the hand; it takes that skin's lowerarm/hand weights
        # there, or the skin swings out through the ring in idle.
        end = share * smoothstep(np.abs(points[:, 0]), wrist_cover(rig) - .02 * rig.fit_scale,
                                 lining_wrist(rig))
        near = np.flatnonzero(end > 0)
        if len(near):
            jj, ww = rig.weights_for(points[near], ['lowerarm_' + side, 'hand_' + side])
            dense[near] *= (1 - end[near])[:, None]
            for slot in range(jj.shape[1]):
                dense[near, jj[:, slot]] += end[near] * ww[:, slot]
    j = np.argsort(-dense, axis=1)[:, :4]
    w = np.take_along_axis(dense, j, axis=1)
    w /= w.sum(axis=1, keepdims=True)
    return j.astype(np.uint16), w


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


def build(source, out, rig, kind='cuirass', label='Remapped armour',
          anatomy_reference=None):
    # The shared neck adds new samples to a localized anatomical transition.
    # Those samples must not change already approved shoulder/plate bindings.
    # Use the verified canonical template for original-art fitting and skin
    # inheritance, and the current visible body for the lining's geometry.
    design_rig = anatomy_reference or rig
    if design_rig.joint_names != rig.joint_names or any(
            not np.array_equal(design_rig.rest[n], rig.rest[n]) for n in rig.joint_names):
        raise ValueError('Anatomy reference must share the exact current skeleton')
    original = source.with_name(source.name + '.orig')
    if original.exists():
        source = original
    surface, texture = io.read_source(source)
    cloth_colour = backing_colour(surface, texture)
    raw = surface.positions.copy()
    original_faces = surface.indices.reshape(-1, 3).copy()
    lift = COLLAR_LIFT.get(source.name.removesuffix('.orig'), 0.)
    arm_fit = ARM_FIT_OVERRIDES.get(source.name.removesuffix('.orig'))
    import design_fit
    body_file = io.RACES / f'{design_rig.source_slug}.glb'
    fit = design_fit.override(source, design_rig, body_file if body_file.exists() else None)
    if fit is not None:
        # The set's design fit supplies the shell; its sleeves are bound with
        # the arm field (design_fit.bind_sleeves). Backing and packing follow below.
        points, joints, weights, sewn = design_fit.bind_sleeves(fit, design_rig, original_faces, source=raw)
        fit = dict(fit, positions=points)
        canon_raw, edges_raw, count_raw = io._weld(raw, original_faces)
        labels = io._components(edges_raw, count_raw)[canon_raw]
        ties = loose_ties(raw, original_faces, labels,
                          source_skeleton(raw, original_faces), np.ptp(raw[:, 1]))
        buried = buried_fragments(points, original_faces, labels, design_rig)
        keep = design_fit.keep_triangles(fit, original_faces) & sewn & ~ties & ~buried
        report = {'designFit': {'file': fit['file'], 'sha256': fit['sha256']},
                  'openedSeamTriangles': int((~keep).sum()),
                  'passes': [{'name': 'design_fit', 'file': fit['file'],
                              'openedTriangles': int((~keep).sum()),
                              'sleeveBridgesOpened': int((~sewn).sum()),
                              'looseTiesRemoved': int(ties.sum()),
                              'buriedFragmentsRemoved': int(buried.sum())}]}
    else:
        points, joints, weights, keep, report = remap(
            raw, surface.indices.reshape(-1, 3), design_rig, lift,
            arm_fit=arm_fit, split_sewn_surface=(kind != 'shirt'))
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
    p, n, uv, idx, j, w = lining(
        rig, points, triangles, design_rig)
    if fit is not None:
        j, w = art_lining_weights(p, j, w, points, joints, weights, design_rig,
                                  sleeveless=not (fit['arm_share'] > .5).any())
    liner_mat = len(glb.doc['materials'])
    glb.doc['materials'].append({'name': label + ' Backing', 'pbrMetallicRoughness': {
        'baseColorFactor': cloth_colour, 'metallicFactor': 0., 'roughnessFactor': 1.}})
    if texture is not None:
        import equipment_seam_texture
        source_p = (design_fit.source_coordinates(p, fit, raw) if fit is not None
                    else source_coordinates(p, j, w, raw, report, rig))
        liner = equipment_seam_texture.primitive(glb, p, idx.reshape(-1,3), n, j, w, source_p,
            raw, original_faces, surface.uvs, texture, label+' Fitted cloth')
    else:
        liner = glb.primitive(p, n, uv, idx, liner_mat, joints=j, weights=w, weight_floats=True)
    glb.mesh(label, [primitive], skin=0)
    glb.mesh('GeneratedArmorBacking', [liner], skin=0)
    # The runtime hides the body up to wrist_cover, short of the lining's end,
    # and keeps the throat skin above the lining's open neckline.
    cover = [.95, 1.535, wrist_cover(rig) / rig.fit_scale, LINING_NECKLINE]
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
