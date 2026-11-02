"""Shared local body support for imported hanging hair.

These functions author geometry; they do not qualify or register an asset.
Callers supply contacts on the complete evaluated body, and an explicitly
reviewed shoulder region.  A shoulder roof can use an upward support step;
lower back curls must follow the actual outward surface direction instead.

Neutral support and control attenuation must agree across UV split copies.
Use the same position-weld groups for all four Length/Volume fields, retain
fixed scalp anchors, then re-root separate detail on the final exterior.
Independently check head/body triangle interiors, coverage, actual saved looks
and Native placement.  A successful local step is not an acceptance result.
"""
import numpy as np


def high_body_triangle_mask(triangle_count, body_cut, *, source_sha256, head_materials):
    """Apply the declared High body cut only with its replacement skin present.

    An uncut Native fixture is not the visible High torso. The supplied source
    hash must be checked against the real body file by the caller; triangle
    order must still match that source. Include the current head's rl_skin and
    rl_bodypatch in the combined High surface before using the returned mask.
    Full uncut Native qualification remains a different check.
    """
    if not isinstance(triangle_count, (int, np.integer)) or triangle_count < 0:
        raise ValueError('triangle_count must be a nonnegative integer')
    if not source_sha256 or body_cut.get('bodySHA256') != source_sha256:
        raise ValueError('the actual body source must match the declared High cut')
    if not {'rl_skin', 'rl_bodypatch'}.issubset(set(head_materials)):
        raise ValueError('the complete High skin and replacement body patch are required')
    runs = body_cut.get('hiddenBodyTriangles')
    if not isinstance(runs, list):
        raise ValueError('the declared High cut must contain explicit triangle runs')
    keep = np.ones(triangle_count, dtype=bool)
    for run in runs:
        if (not isinstance(run, (list, tuple)) or len(run) != 2
                or any(not isinstance(v, (int, np.integer)) for v in run)):
            raise ValueError('each hidden triangle run must contain two integers')
        start, count = run
        if start < 0 or count < 0 or start + count > triangle_count:
            raise ValueError('a hidden triangle run lies outside the actual body')
        keep[start:start + count] = False
    return keep


def _points(value, name):
    result = np.asarray(value, dtype=float)
    if result.ndim != 2 or result.shape[1] != 3 or not np.isfinite(result).all():
        raise ValueError(name + ' must be a finite N by 3 array')
    return result


def _groups(weld, count):
    weld = np.asarray(weld)
    if weld.shape != (count,) or weld.dtype.kind not in 'iu' or (weld < 0).any():
        raise ValueError('weld must contain one nonnegative integer per vertex')
    # Compact arbitrary caller labels without changing membership.
    return np.unique(weld, return_inverse=True)[1]


def contact_step(points, closest, normals, signed, *, margin_m,
                 shoulder_floor_y, shoulder_ceiling_y, maximum_probe_y):
    """Return outward contact proposals and the explicit shoulder-roof mask.

    The geometric direction uses signed distance to distinguish an interior
    point from an exterior point.  Coincident contacts use the supplied surface
    normal.  This never pushes a lower back contact upward toward the shoulder.
    No displacement bound is inferred: callers enforce their separate, measured
    body support allowance and preserve the ordinary head/Native bounds.
    """
    points = _points(points, 'points')
    closest = _points(closest, 'closest')
    normals = _points(normals, 'normals')
    signed = np.asarray(signed, dtype=float)
    if closest.shape != points.shape or normals.shape != points.shape:
        raise ValueError('contact arrays must have the same shape')
    if signed.shape != (len(points),) or not np.isfinite(signed).all():
        raise ValueError('signed must contain one finite distance per point')
    limits = [margin_m, shoulder_floor_y, shoulder_ceiling_y, maximum_probe_y]
    if not np.isfinite(limits).all() or margin_m <= 0:
        raise ValueError('finite region limits and a positive margin are required')
    if shoulder_floor_y >= shoulder_ceiling_y:
        raise ValueError('the measured shoulder region must have positive height')
    separation = points - closest
    length = np.linalg.norm(separation, axis=1)
    direction = separation / np.maximum(length[:, None], 1e-30)
    direction *= np.where(signed < 0, -1., 1.)[:, None]
    coincident = length < 1e-10
    normal_length = np.linalg.norm(normals, axis=1)
    if (coincident & (normal_length < 1e-10)).any():
        raise ValueError('coincident contacts require a valid surface normal')
    direction[coincident] = normals[coincident] / normal_length[coincident, None]
    shoulder = ((closest[:, 1] >= shoulder_floor_y)
                & (closest[:, 1] < shoulder_ceiling_y)
                & (points[:, 1] < maximum_probe_y))
    direction[shoulder] = [0., 1., 0.]
    return direction * np.maximum(margin_m - signed, 0.)[:, None], shoulder


def shared_displacement(points, displacement, weld, *, fixed=None):
    """Share the largest contact displacement across every position copy.

    A group containing a fixed scalp anchor remains fixed.  This can expose an
    unresolved contact to the independent gate; it never moves the anchor or
    hides the contact by opening a seam.  Unaffected groups stay byte-exact.
    """
    points = _points(points, 'points')
    displacement = _points(displacement, 'displacement')
    if displacement.shape != points.shape:
        raise ValueError('displacement must match points')
    groups = _groups(weld, len(points))
    if not len(points):
        return displacement.copy()
    magnitude = np.linalg.norm(displacement, axis=1)
    order = np.argsort(magnitude, kind='stable')
    _, reverse = np.unique(groups[order][::-1], return_index=True)
    chosen = order[len(order) - 1 - reverse]
    vector = np.zeros((int(groups.max()) + 1, 3))
    vector[groups[chosen]] = displacement[chosen]
    if fixed is not None:
        fixed = np.asarray(fixed, dtype=bool)
        if fixed.shape != (len(points),):
            raise ValueError('fixed must contain one flag per vertex')
        vector[np.unique(groups[fixed])] = 0.
    return vector[groups]


def shared_control_influence(influence, weld, *, blocked=None, decay=.5):
    """Share the minimum safe influence and any further reduction per weld.

    The returned single scale must be applied to every Length/Volume field.
    Reducing only the vertices of an individual UV island can open centimeter
    gaps, even when each checked skin contact passes independently.
    """
    influence = np.asarray(influence, dtype=float)
    if influence.ndim != 1 or not np.isfinite(influence).all():
        raise ValueError('influence must be a finite vector')
    if ((influence < 0) | (influence > 1)).any() or not 0 <= decay <= 1:
        raise ValueError('influence and decay must be in the range 0 to 1')
    groups = _groups(weld, len(influence))
    if not len(influence):
        return influence.copy()
    result = np.ones(int(groups.max()) + 1)
    np.minimum.at(result, groups, influence)
    if blocked is not None:
        blocked = np.asarray(blocked, dtype=bool)
        if blocked.shape != influence.shape:
            raise ValueError('blocked must contain one flag per vertex')
        group_blocked = np.zeros(len(result), dtype=bool)
        np.logical_or.at(group_blocked, groups, blocked)
        result[group_blocked] *= decay
    return result[groups]


def shared_control_vectors(delta, weld, *, maximum_reconciliation_mm, fixed=None):
    """Reconcile a small pre-existing vector mismatch before body attenuation.

    This is for minor independently seated UV copies, not independently
    attenuated body controls. Recover those original fields and share their
    minimum influence instead. The explicit reconciliation bound prevents a
    large control seam from being concealed by averaging. Re-run the physical
    gates after reconciling any field; averaging is not a clearance proof.
    """
    delta = _points(delta, 'delta')
    groups = _groups(weld, len(delta))
    if not np.isfinite(maximum_reconciliation_mm) or maximum_reconciliation_mm < 0:
        raise ValueError('a finite nonnegative reconciliation bound is required')
    if not len(delta):
        return delta.copy()
    count = np.bincount(groups)
    total = np.zeros((len(count), 3))
    np.add.at(total, groups, delta)
    mean = total / count[:, None]
    if fixed is not None:
        fixed = np.asarray(fixed, dtype=bool)
        if fixed.shape != (len(delta),):
            raise ValueError('fixed must contain one flag per vertex')
        mean[np.unique(groups[fixed])] = 0.
    result = mean[groups]
    assert_local_bound(delta, result, maximum_mm=maximum_reconciliation_mm)
    return result


def assert_local_bound(original, changed, *, maximum_mm):
    """Enforce an explicit body-authoring allowance without changing a gate."""
    original = _points(original, 'original')
    changed = _points(changed, 'changed')
    if changed.shape != original.shape or not np.isfinite(maximum_mm) or maximum_mm < 0:
        raise ValueError('matching points and a finite nonnegative bound are required')
    measured = float(np.linalg.norm(changed - original, axis=1).max(initial=0) * 1000)
    if measured > maximum_mm + 1e-8:
        raise ValueError('Body support exceeded the explicit local allowance: '
                         + str({'measured_mm': measured, 'maximum_mm': maximum_mm}))
    return measured
