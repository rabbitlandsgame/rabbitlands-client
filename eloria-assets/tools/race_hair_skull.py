"""The cranium race hair is fitted over, and the lateral protrusions it tucks under.

Since the race programme's P4 (2026-10) horns, crowns, crests and crystals live
on their own `race_feature_head` node, outside the `race_head` surfaces, and
caps close the cranium beneath them. Hair is fitted over that closed cranium
(`source_head`: race_head skin, scalp, eyes, eyebrows) and the features show
through it on every race, the crowned Glasswarden female included.

The smooth ellipsoid proxy that used to stand in for the cranium beneath horns
and crystals (Votary, Stoneborn, Glasswarden male; `hairAllowsProtrusions`) is
retired: fitted on the plain cranium, every style on those five bodies keeps
at least 5.7 mm of hair over the cranium under the crown rays of
test_character_appearance_fit.py (5.7-9.5 mm at the closest ray; P5 refit,
2026-10-08), so `hairAllowsProtrusions` is gone from models.json.

`lateral_features` gives `fit_character_appearance.tuck_ears` the race_head
triangles beside the head that stand more than FEATURE_M outside a fitted
cranium ellipsoid - pointed ears and the Ssarathi head spikes - so hair can be
pulled under them instead of being pierced by them.
"""
import numpy as np
from scipy.optimize import least_squares
from scipy.sparse import coo_matrix
from scipy.sparse.csgraph import connected_components
import equipment_authoring as ea
from integrate_luminous_sources import source_head
from verify_shared_player_bodies import primitives

# Head-local metres. A race_head triangle is a lateral feature when its
# centroid stands FEATURE_M outside the cranium fit, lies LATERAL_X beside the
# midline and below LATERAL_ABOVE_EYE over the eye line, and is not face or
# temple: not in front of the eyes' front minus TEMPLE_BEHIND_EYE (at any
# height; ears and spikes sit further back, while broad brows, cheekbones and
# temples - the Mycelari male's flat forehead corners stand 10-18 mm outside
# an ellipsoid - would otherwise join an ear's piece and have the hair tucked
# away from the temple) and not more than JAW_BELOW_EYE below the eye line.
FEATURE_M = .010
LATERAL_X, LATERAL_ABOVE_EYE = .06, .06
TEMPLE_BEHIND_EYE, JAW_BELOW_EYE = .055, .045


def allows_protrusions(slug):
    """Retired (see module docstring): no race fits its hair over a proxy."""
    return False


def hair_skull(document, binary, slug=None):
    """Head-local cranium mesh, its skin weights and the Head joint's matrix."""
    return source_head(document, binary)


def head_matrix(document):
    head = next(i for i, n in enumerate(document['nodes']) if n.get('name') == 'Head')
    return ea.global_matrices(document)[head]


def to_local(points, matrix):
    return (points - matrix[:3, 3]) @ matrix[:3, :3]


def protrusion(local, centre, radii):
    """Approximate metric distance outside the ellipsoid along the radial line."""
    q = (local - centre) / radii
    k = np.linalg.norm(q, axis=1)
    r = np.linalg.norm(local - centre, axis=1)
    return r * (1 - 1 / np.maximum(k, 1e-9))


def fit_cranium(local, eye_y, eye_z):
    """Ellipsoid through the cranium behind the face and above the cheek, with
    the ear band left out; refitted without >6 mm outliers so ears and spikes
    do not pull it."""
    v = local
    keep = (v[:, 1] > eye_y - .02) & (v[:, 2] < eye_z - .03)
    keep &= ~((abs(v[:, 0]) > .068) & (v[:, 1] < eye_y + .055))
    s = v[keep]
    s = s[::max(1, len(s) // 5000)]
    p0 = [eye_y + .02, -.02, .08, .095, .095]
    lo = [eye_y - .03, -.07, .062, .07, .075]
    hi = [eye_y + .07, .03, .105, .125, .125]
    for _ in range(3):
        def residual(p, s=s):
            c = np.array([0., p[0], p[1]])
            return (np.linalg.norm((s - c) / p[2:], axis=1) - 1) * .09
        fit = least_squares(residual, p0, bounds=(lo, hi), loss='soft_l1', f_scale=.002)
        centre, radii = np.array([0., fit.x[0], fit.x[1]]), fit.x[2:]
        s = s[protrusion(s, centre, radii) < .006]
        p0 = fit.x
    return centre, radii


def lateral_features(document, binary):
    """Head-local lateral feature triangles (n, 3, 3), the cranium centre and
    a per-triangle feature label (connected pieces: one ear, one spike).

    Built from the race_head surfaces only, so `race_feature_*` nodes (horns,
    crowns, crests, crystals), which show through the hair, never count."""
    matrix = head_matrix(document)
    surfaces = {}
    for name, role, a, f in primitives(document, binary):
        if role != 'race_head':
            continue
        ids, inverse = np.unique(f, return_inverse=True)
        v, faces = a['POSITION'][ids].astype(float), inverse.reshape(-1, 3)
        if name in surfaces:
            pv, pf = surfaces[name]
            surfaces[name] = (np.vstack([pv, v]), np.vstack([pf, faces + len(pv)]))
        else:
            surfaces[name] = (v, faces)
    eyes = to_local(surfaces['eyes'][0], matrix)
    eye_y, eye_z = float(np.median(eyes[:, 1])), float(eyes[:, 2].max())
    every = np.vstack([v for v, _ in surfaces.values()])
    centre, radii = fit_cranium(to_local(every, matrix), eye_y, eye_z)
    found = []
    for v, faces in surfaces.values():
        triangles = to_local(v[faces].reshape(-1, 3), matrix).reshape(-1, 3, 3)
        c = triangles.mean(1)
        feature = protrusion(c, centre, radii) > FEATURE_M
        face = (c[:, 2] > eye_z - TEMPLE_BEHIND_EYE) | (c[:, 1] < eye_y - JAW_BELOW_EYE)
        lateral = (abs(c[:, 0]) > LATERAL_X) & (c[:, 1] < eye_y + LATERAL_ABOVE_EYE)
        found.append(triangles[feature & lateral & ~face])
    found = np.concatenate(found)
    return found, centre, pieces(found)


def pieces(triangles):
    """Label triangles (n, 3, 3) by connected piece; corners join when their
    positions agree to a micrometre (surfaces are split at UV seams)."""
    if not len(triangles):
        return np.zeros(0, dtype=int)
    _, corner = np.unique(np.round(triangles.reshape(-1, 3), 6), axis=0, return_inverse=True)
    corner = corner.reshape(-1, 3)
    edges = np.concatenate([corner[:, [0, 1]], corner[:, [1, 2]]])
    n = int(corner.max())+1
    graph = coo_matrix((np.ones(len(edges)), (edges[:, 0], edges[:, 1])), shape=(n, n))
    return connected_components(graph, directed=False)[1][corner[:, 0]]
