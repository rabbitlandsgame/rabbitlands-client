"""Race head features as their own mesh node (P4, lead decision 1).

Votary horns, the Stoneborn crown and Glasswarden crystals were part of the
v2 race head: mostly the scalp, partly the body race_head primitive (5-756
faces per body). rebase_race_body.build moves them into one mesh node,
`race_feature_head`:
  - one primitive, sourceRole `race_feature`, the race skin, 100% Head
    weights (the feature rows get their own copies);
  - a material per kind (MATERIALS) sampling the head atlas image, so no new
    texture; the head atlas packs and bakes the feature charts with the head;
  - the node is appended after every existing node, so the skin joints and
    the inverse-bind bytes stay identical.
Being a separate node it escapes the skin dye (replicated_actor_3d.gd has no
dye branch for it) and the runtime hides it under helms on its own.

The split runs after clean_head and before every texture step:
  segment  distance outside a skull ellipsoid fitted per head (eyes and the
           cranium behind the brow), seeded and grown over welded edges; the
           Glasswarden male also needs crystal colour (port of
           race_p47/features/seg2.py and v2/featinfo.py). Eyes, eyebrows and
           the rim band never join a feature.
  settle   feature components under FOLD_FACES faces go back to the head and
           head islands under FOLD_FACES faces the split leaves go into the
           feature (V6 and the CI fragment test want >= 20-face components).
  caps     every hole the split opens is closed by a cap WELDED to the hole
           boundary: the cap's boundary rows copy the position, normal and
           weights of the boundary rows (only the UV differs), the interior
           is a constrained Delaunay triangulation of the loop in a gnomonic
           projection about the skull (else the loop's best-fit plane, else a
           minimum-area triangulation), interior edges bisected to CAP_EDGE_M
           and lifted onto the skull ellipsoid plus a harmonic offset that
           meets the boundary. A cap joins the primitive that owns most of its
           hole's edges, a tie going to the body (cap_owner; R1 gave a mixed
           hole to the body, which left the Votary horn-root caps standing as
           domes through hide headwear); its triangles are appended LAST to
           that primitive (sharedBodyShape.raceFeatures.caps counts them), and
           it gets its own head-atlas chart: the hole edge's texels at its
           boundary, the local skin median inside.
  islands  (R2) head components the split or clean_head left floating (no rim
           face, no eye/eyebrow face) that lie on the caps of the head proper
           (median centroid distance under ISLAND_ON_CAP_M) are dropped with no
           caps of their own: kept, they doubled those caps (z-fighting); any
           other floating component keeps its faces and caps
           (raceFeatures.floatingIslands).
  layered  (batch B) the crowned Glasswarden female's shard fringe under the
           crest, inside the skull fit, joins the feature by ray crossings
           from the neck axis (layered_faces).
  repaint  (batch B, after split) glass-coloured paint the split leaves in
           the dyed head takes the local skin colour in the head source the
           bake samples (the Glasswarden male's flecks and crystal bases);
           V20 glassLeft measures the baked atlas (glass_left).
rebase_race_body.verify: V3 becomes head = v2 - cleanup - features - dropped
islands (caps set aside) and V20 (verify_features) checks the node, its
weights, material and v2 provenance, the caps (watertight, never above their
hole, each in the primitive owning most of its hole's edges) and that the
crown left in race_head/scalp is feature-free; rebase_race_body adds the
hide-state headwear check of the body caps (capHeadwear).
"""
from __future__ import annotations

from collections import Counter, defaultdict
import hashlib

import numpy as np
from scipy.optimize import least_squares
from scipy.sparse import coo_matrix, csr_matrix
from scipy.sparse.csgraph import connected_components
from scipy.sparse.linalg import spsolve
from scipy.spatial import cKDTree

NODE = 'race_feature_head'
ROLE = 'race_feature'
KEY = (NODE, 'head')
HEADISH = ('body', 'scalp')
PROTECTED = ('eyes', 'eyebrows')
LUMA = np.array([.2126, .7152, .0722])
# Components under this many faces are fragments (V6, test_race_rebase).
FOLD_FACES = 20
# A floating head component whose face centroids lie this close to the caps
# of the head proper (median) is a duplicate of them and is dropped (R2).
ISLAND_ON_CAP_M = .010
# Cap interior edges are bisected until shorter than this.
CAP_EDGE_M = .015
CAP_MAX_PASSES = 40
# Cap colour: boundary corners take the source texel of the hole edge; inside,
# the colour blends to the median of the intact skin within CAP_COLOUR_RADIUS_M
# of the hole over CAP_COLOUR_BLEND_M from the boundary.
CAP_COLOUR_RADIUS_M, CAP_COLOUR_BLEND_M = .02, .008
# A gnomonic cap needs every boundary direction within ~78 degrees of the
# loop's mean direction; otherwise (never seen) it falls back to a fan.
GNOMONIC_MIN_COS = .2
# A loop no projection makes simple is triangulated by minimum area; its
# interior follows the skull when the loop lies within this of it on average.
MEMBRANE_EXCESS_M = .02

MATERIALS = {
    'horn': {'name': 'Race feature horn', 'roughness': .7},
    'stone': {'name': 'Race feature stone', 'roughness': .9},
    # Lead decision 4: glass is authored opaque, roughness ~.2, metallic 0, no
    # emission; OldcraftActorStyle skips its roughness floor for this name.
    'glass': {'name': 'Race feature glass', 'roughness': .2},
}

# Segmentation per slug (head-local metres; excess = distance outside the
# fitted skull ellipsoid, per face its largest corner excess).
#   seed/grow: excess thresholds; aboveEyeM: centroids above the eye line
#   only (the crown never reaches the face below the brow ridge or the ear),
#   except behindSkullM behind the skull centre, where the Stoneborn rear
#   spikes hang down the nape (stoneborn_female: 52 mm stumps otherwise, the
#   P3 'nape wedges'); colour: seed/grow luminance (sRGB 0-255, per-face median of 7
#   samples of the head source); ear: the crowned Glasswarden female's ear
#   exclusion (relative to the eyes).
FEATURES = {
    'votary_male': {'kind': 'horn', 'seed': .015, 'grow': .003, 'seedOn': ('scalp',)},
    'votary_female': {'kind': 'horn', 'seed': .015, 'grow': .003, 'seedOn': ('scalp',)},
    # Batch B review: grown over 4 mm the male crown took the forehead, the
    # temples and the brow ridge (4-10 mm proud of the skull fit: carved skin,
    # not crown) as a stone band that stays grey at dyed skins around a dyed
    # patch. frontGrow: in front of the skull centre (+ zOverSkullCentreM) a
    # face joins only over frontGrow.grow, so only the spikes and their bases
    # split there; behind it the rear spikes keep the 4 mm rule (grown over
    # 10 mm everywhere, their base caps rose 2-7 mm through the Knotwork Helm
    # 3:131, 28 V20 capHeadwear pokes).
    'stoneborn_male': {'kind': 'stone', 'seed': .010, 'grow': .004, 'seedOn': ('scalp',), 'aboveEyeM': .005,
                       'behindSkullM': .04, 'frontGrow': {'grow': .010, 'zOverSkullCentreM': 0.}},
    'stoneborn_female': {'kind': 'stone', 'seed': .010, 'grow': .004, 'seedOn': ('scalp',), 'aboveEyeM': .005,
                         'behindSkullM': .04},
    # Batch B review: flat flecks and crystal bases left in the head keep the
    # glass paint and take the skin dye; repaint (below) gives them skin.
    'glasswarden_male': {'kind': 'glass', 'seed': .006, 'grow': .001, 'seedOn': HEADISH,
                         'colour': {'seed': 205., 'grow': 185.},
                         'repaint': {'colourDistance': 45., 'eyeBehindM': .035, 'eyeAboveM': .03, 'leftLimitCm2': 2.}},
    # P6 crowned head only (race_heads_2026-10 Meshy run); the current v2 head
    # has no crystals, only glassy ear rims. Ported from race_p47/features/
    # gwf2.py: seed over 12 mm above the eye line, grow over 3 mm from 1 cm
    # below it, never on the ears: |x| over 9.5 cm below eye + 7 cm, at any
    # depth (gwf2's z limit let the swept-back ear tips of the aligned
    # crowned head, z down to eye - 14.5 cm, into the crest). Checked on
    # p47/heads/glasswarden_female.crowned-v2.glb before cleanup only.
    # R1 pilot: clean_head deletes the crowned head's skull under the crest
    # (its inner shell), so a skull fitted after cleanup sits on the crest and
    # keeps most of it in race_head (dyed with the skin, V7/V20 failed):
    # skullFrom 'uncleaned' fits the ellipsoid before clean_head (the dry
    # run's fit, the whole crest splits). The skull faces clean_head kept
    # because they showed through crest gaps end up under the caps;
    # foldHidden moves the head faces a first split leaves robustly hidden
    # (V7's rule) into the feature, then splits again.
    # R2: requiresSourceSHA256 is the crowned Meshy original
    # (race_head_prepare.MESHY_HEADS); the head's highResolutionHead names it.
    # Batch B review: under the crest a fringe of overlapping shards runs round
    # the back of the skull to the nape (3.6 surface layers against about one
    # on the v2 head), all inside the tall skull fit (excess -17 to 0 mm), so
    # neither the excess rule nor aboveEyeM reaches it and it took the dye.
    # layered: below the eye line + belowEyeM and behind the skull centre +
    # behindSkullM, a head face (off the rim by rimMarginM) whose ray from the
    # neck axis through its centroid crosses the head minCrossings times or
    # more (skin plus at least one shard, both its sides) joins the feature
    # (layered_faces), forced like foldHidden's faces.
    'glasswarden_female': {'kind': 'glass', 'seed': .012, 'grow': .003, 'seedOn': HEADISH,
                           'seedAboveEyeM': 0., 'aboveEyeM': -.010,
                           'ear': {'absXOver': .095, 'yUnderEye': .07, 'zOverEye': -1.},
                           'requiresSourceSHA256': 'b9ed0125b47bb8a5737250d79bb59aa09260d0d45aa386fd07419ec4a9880643',
                           'skullFrom': 'uncleaned', 'foldHidden': True,
                           'layered': {'belowEyeM': -.010, 'behindSkullM': 0., 'rimMarginM': .006, 'minCrossings': 3}},
}


def spec_for(slug, provenance=None):
    """FEATURES entry for this slug, or None. An entry with
    requiresSourceSHA256 applies only to a head whose highResolutionHead
    (provenance) names that Meshy original; any other head gets no split, and
    V20 (expected) then fails the body, so it cannot install."""
    spec = FEATURES.get(slug)
    if spec is None:
        return None
    needed = spec.get('requiresSourceSHA256')
    if needed and (provenance or {}).get('originalSHA256') != needed:
        return None
    return spec


# ---------------------------------------------------------------------------
# geometry helpers
# ---------------------------------------------------------------------------

def weld_ids(p, tol=1e-6):
    """Position-welded ids (cKDTree pairs, as rebase_race_body.weld)."""
    p = np.asarray(p, float)
    pairs = cKDTree(p).query_pairs(tol, output_type='ndarray')
    return connected_components(coo_matrix((np.ones(len(pairs)), (pairs[:, 0], pairs[:, 1])),
                                           shape=(len(p), len(p))).tocsr(), directed=False)[1]


def to_local(p, head):
    return (np.asarray(p, float)-head[:3, 3])@head[:3, :3]


def to_world(q, head):
    return np.asarray(q, float)@head[:3, :3].T+head[:3, 3]


def edge_keys(ids, faces):
    e = np.sort(ids[np.concatenate([faces[:, [0, 1]], faces[:, [1, 2]], faces[:, [2, 0]]])], 1)
    return e[:, 0].astype(np.int64)*(int(ids.max())+1)+e[:, 1], e


def face_adjacency(ids, faces):
    """Faces sharing a welded edge."""
    key, _ = edge_keys(ids, faces)
    fid = np.tile(np.arange(len(faces)), 3)
    order = np.argsort(key, kind='stable'); key, fid = key[order], fid[order]
    same = key[1:] == key[:-1]
    a, b = fid[:-1][same], fid[1:][same]
    n = len(faces)
    return csr_matrix((np.ones(2*len(a)), (np.concatenate([a, b]), np.concatenate([b, a]))), shape=(n, n))


def vertex_components(ids, faces, mask):
    """Components of the masked faces sharing a welded vertex (V6's rule);
    labels per face, -1 outside the mask."""
    sel = np.flatnonzero(mask)
    out = np.full(len(faces), -1)
    if not len(sel):
        return out
    ff = ids[faces[sel]]
    n = int(ids.max())+1
    e = np.concatenate([ff[:, [0, 1]], ff[:, [1, 2]]])
    label = connected_components(coo_matrix((np.ones(len(e)), (e[:, 0], e[:, 1])), shape=(n, n)).tocsr(),
                                 directed=False)[1]
    out[sel] = np.unique(label[ff[:, 0]], return_inverse=True)[1]
    return out


def grow(adjacency, seed, allowed):
    current = seed.copy()
    while True:
        nxt = current | (((adjacency@current.astype(float)) > 0) & allowed)
        if (nxt == current).all():
            return current
        current = nxt


def area3(p, faces):
    p = np.asarray(p, float)
    return .5*np.linalg.norm(np.cross(p[faces[:, 1]]-p[faces[:, 0]], p[faces[:, 2]]-p[faces[:, 0]]), axis=1)


def sample_image(pixels, uv):
    """Bilinear, repeat-wrapped, texel-centre sampling (spb.sample_image) of a
    0-1 float image; returns 0-1."""
    size = np.array(pixels.shape[:2][::-1]); xy = (np.asarray(uv, float) % 1)*size-.5
    lo = np.floor(xy).astype(int); t = xy-lo; hi = (lo+1) % size; lo %= size
    return ((pixels[lo[:, 1], lo[:, 0]]*(1-t[:, 0, None])+pixels[lo[:, 1], hi[:, 0]]*t[:, 0, None])*(1-t[:, 1, None])
            + (pixels[hi[:, 1], lo[:, 0]]*(1-t[:, 0, None])+pixels[hi[:, 1], hi[:, 0]]*t[:, 0, None])*t[:, 1, None])


# ---------------------------------------------------------------------------
# skull fit and segmentation
# ---------------------------------------------------------------------------

def fit_skull(local_by_part):
    """Ellipsoid (centre on x = 0) through the cranium behind the brow,
    eye-line to +9 cm (race_p47/features/seg1.fit_skull). Returns
    (centre yz, radii xyz) as q = [cy, cz, rx, ry, rz], eye y and z."""
    eyes = local_by_part['eyes']
    ey, ez = float(np.median(eyes[:, 1])), float(np.median(eyes[:, 2]))
    allv = np.concatenate(list(local_by_part.values()))
    s = allv[(allv[:, 1] > ey+.005) & (allv[:, 1] < ey+.09) & (np.abs(allv[:, 0]) < .075) & (allv[:, 2] < ez)]

    def residual(q):
        c = np.array([0., q[0], q[1]])
        return (np.linalg.norm((s-c)/q[2:], axis=1)-1)*.09
    fit = least_squares(residual, [ey+.01, ez-.07, .08, .10, .10],
                        bounds=([ey-.03, ez-.12, .06, .07, .075], [ey+.04, ez-.02, .10, .13, .125]),
                        loss='soft_l1', f_scale=.002)
    return fit.x, ey, ez


def skull_centre(q):
    return np.array([0., q[0], q[1]])


def excess(local, q):
    """Approximate metric distance outside the skull ellipsoid."""
    c = skull_centre(q)
    rel = np.asarray(local, float)-c
    r = np.linalg.norm(rel/q[2:], axis=1)
    direction = rel/np.maximum(np.linalg.norm(rel, axis=1, keepdims=True), 1e-9)
    radius = 1/np.linalg.norm(direction/q[2:], axis=1)
    return (r-1)*radius


def head_parts(upper):
    """Faces of the head group with their primitive name."""
    keys = [k for k in upper['f'] if k != KEY]
    faces = np.concatenate([upper['f'][k] for k in keys])
    part = np.concatenate([[k[0]]*len(upper['f'][k]) for k in keys])
    return keys, faces, part


def face_colours(pixels, uv, faces):
    """Per-face median sRGB (0-255) of 7 barycentric samples."""
    bary = np.array([[1/3, 1/3, 1/3], [.5, .5, 0], [0, .5, .5], [.5, 0, .5], [.6, .2, .2], [.2, .6, .2], [.2, .2, .6]])
    samples = np.stack([sample_image(pixels, np.einsum('i,nij->nj', w, uv[faces])) for w in bary], 0)*255
    return np.median(samples, 0)


def skull_fit(upper, head):
    """fit_skull over the head group's primitives: (q, eye y, eye z)."""
    keys, _, _ = head_parts(upper)
    local = to_local(upper['a']['POSITION'].astype(float), head)
    return fit_skull({k[0]: local[np.unique(upper['f'][k])] for k in keys})


def layered_faces(p, faces, local, centre, headish, travel, upper_cut, origin, axis, q, ey, rule):
    """spec 'layered' (the crowned Glasswarden female's shard fringe): head
    faces below ey + belowEyeM, behind the skull centre + behindSkullM and
    with every corner rimMarginM over the cut, whose ray from the neck axis
    (at the centroid's travel) through the centroid crosses the head
    (headish faces) at least minCrossings times. One smooth skin layer is
    one crossing; a shard over it adds two. Rays go through trimesh's
    numpy intersector (no embree), so the result is deterministic."""
    import trimesh
    from trimesh.ray.ray_triangle import RayMeshIntersector
    cand = (headish & (centre[:, 1] < ey+rule['belowEyeM']) & (centre[:, 2] < q[1]-rule['behindSkullM'])
            & (travel[faces].min(1)-upper_cut > rule['rimMarginM']))
    out = np.zeros(len(faces), bool)
    idx = np.flatnonzero(cand)
    if not len(idx):
        return out
    world = p[faces[idx]].mean(1)
    foot = origin+np.outer((world-origin)@axis, axis)
    direction = world-foot
    direction /= np.maximum(np.linalg.norm(direction, axis=1, keepdims=True), 1e-12)
    mesh = trimesh.Trimesh(p, faces[headish], process=False)
    _, ray, _ = RayMeshIntersector(mesh).intersects_location(foot, direction, multiple_hits=True)
    out[idx] = np.bincount(ray, minlength=len(idx)) >= rule['minCrossings']
    return out


def segment(upper, spec, pixels, head, origin, axis, upper_cut, rim_band=.002, skull=None, include=None):
    """Feature mask over head_parts(upper) faces (plus the measures). skull:
    a (q, eye y, eye z) fit to use instead of fitting this head (skullFrom);
    include: faces forced into the feature (foldHidden)."""
    keys, faces, part = head_parts(upper)
    p = upper['a']['POSITION'].astype(float)
    local = to_local(p, head)
    q, ey, ez = skull if skull is not None else skull_fit(upper, head)
    ex = excess(local, q)
    fex = ex[faces].max(1)
    centre = local[faces].mean(1)
    ids = weld_ids(p)
    adjacency = face_adjacency(ids, faces)
    travel = (p-origin)@axis
    rim = (np.abs(travel-upper_cut) < rim_band)[faces].any(1)
    headish = np.isin(part, HEADISH) & ~rim
    seed = np.isin(part, spec['seedOn']) & headish & (fex > spec['seed'])
    allowed = headish & (fex > spec['grow'])
    if 'frontGrow' in spec:
        front = centre[:, 2] > q[1]+spec['frontGrow']['zOverSkullCentreM']
        allowed &= ~front | (fex > spec['frontGrow']['grow'])
    if 'aboveEyeM' in spec:
        above = centre[:, 1] > ey+spec['aboveEyeM']
        if 'behindSkullM' in spec:
            above |= centre[:, 2] < q[1]-spec['behindSkullM']
        allowed &= above
        seed &= centre[:, 1] > ey+spec.get('seedAboveEyeM', spec['aboveEyeM'])
    lum = None
    if 'colour' in spec:
        lum = face_colours(pixels, upper['a']['TEXCOORD_0'].astype(float), faces)@LUMA
        seed &= lum > spec['colour']['seed']
        allowed &= lum > spec['colour']['grow']
    if 'ear' in spec:
        e = spec['ear']
        ear = ((np.abs(centre[:, 0]) > e['absXOver']) & (centre[:, 1] < ey+e['yUnderEye'])
               & (centre[:, 2] > ez+e['zOverEye']))
        seed &= ~ear; allowed &= ~ear
    feature = grow(adjacency, seed, allowed)
    forced = np.zeros(len(faces), bool) if include is None else np.asarray(include, bool) & headish
    included = forced.copy()
    layered = None
    if 'layered' in spec:
        layered = layered_faces(p, faces, local, centre, headish, travel, upper_cut, origin, axis, q, ey, spec['layered'])
        forced |= layered
    feature |= forced
    return feature, {'keys': keys, 'faces': faces, 'part': part, 'ids': ids, 'adjacency': adjacency, 'local': local,
                     'skull': q, 'eye': (ey, ez), 'fex': fex, 'rim': rim, 'lum': lum, 'seed': seed, 'forced': forced,
                     'layered': layered, 'included': included}


def settle(feature, info):
    """Feature components under FOLD_FACES go back to the head; head islands
    under FOLD_FACES the split leaves (not eyes/eyebrows, not on the rim)
    join the feature. Repeats until stable."""
    faces, part, ids, rim = info['faces'], info['part'], info['ids'], info['rim']
    feature = feature.copy()
    returned, folded = [], []
    for _ in range(8):
        changed = False
        label = vertex_components(ids, faces, feature)
        sizes = np.bincount(label[feature]) if feature.any() else np.zeros(0, int)
        small = feature & (sizes[np.maximum(label, 0)] < FOLD_FACES)
        if small.any():
            returned += sorted(np.bincount(label[small])[np.unique(label[small])].tolist())
            feature &= ~small; changed = True
        rest = ~feature
        label = vertex_components(ids, faces, rest)
        sizes = np.bincount(label[rest])
        protected = np.zeros(len(sizes), bool)
        protected[np.unique(label[rest & (np.isin(part, PROTECTED) | rim)])] = True
        island = rest & (sizes[np.maximum(label, 0)] < FOLD_FACES) & ~protected[np.maximum(label, 0)]
        if island.any():
            folded += sorted(np.bincount(label[island])[np.unique(label[island])].tolist())
            feature |= island; changed = True
        if not changed:
            return feature, {'featureComponentsReturned': returned, 'headIslandsFolded': folded}
    raise ValueError('feature split does not settle')


def floating_islands(feature, info):
    """Floating head faces (R2): components of the head without the feature
    that hold no rim face and no eye/eyebrow face, as a face mask and a
    per-face component label (-1 elsewhere). settle() already folded the ones
    under FOLD_FACES into the feature; these are larger patches of skull skin
    between crystals, cut off by the split or by clean_head before it (the
    crowned Glasswarden female: 404, 152, 148, 78 and 70 faces). Lying inside
    the hole a cap of the head proper closes, on the same skull, they double
    that cap within 0.1 mm (z-fighting) and, capped themselves, stack three
    surfaces; split() drops the ones on the caps (ISLAND_ON_CAP_M)."""
    faces, part, ids, rim = info['faces'], info['part'], info['ids'], info['rim']
    rest = ~feature
    label = vertex_components(ids, faces, rest)
    anchored = np.zeros(int(label.max())+1 if rest.any() else 0, bool)
    anchored[np.unique(label[rest & (rim | np.isin(part, PROTECTED))])] = True
    floating = rest & ~anchored[np.maximum(label, 0)]
    return floating, np.where(floating, label, -1)


# ---------------------------------------------------------------------------
# holes and caps
# ---------------------------------------------------------------------------

def boundary_edges(ids, faces):
    """Directed boundary half-edges (welded ids) with their face and corner."""
    key, undirected = edge_keys(ids, faces)
    _, inverse, count = np.unique(key, return_inverse=True, return_counts=True)
    open_ = count[inverse.ravel()] == 1
    n = len(faces)
    face = np.tile(np.arange(n), 3)[open_]
    corner = np.repeat([0, 1, 2], n)[open_]
    a = faces[face, corner]; b = faces[face, (corner+1) % 3]
    return ids[a], ids[b], face, a, b


def hole_loops(info, feature, upper_cut_rows):
    """Ordered boundary loops of the head without the feature that the split
    opened (each with its welded ids, an owning face and row per vertex)."""
    faces, ids = info['faces'], info['ids']
    rest = np.flatnonzero(~feature)
    before = set(map(tuple, np.sort(np.stack(boundary_edges(ids, faces)[:2], 1), 1).tolist()))
    wa, wb, face, ra, rb = boundary_edges(ids, faces[rest])
    face = rest[face]
    undirected = np.sort(np.stack([wa, wb], 1), 1)
    new = np.array([tuple(e) not in before for e in undirected.tolist()])
    n = int(ids.max())+1
    label = connected_components(coo_matrix((np.ones(len(wa)), (wa, wb)), shape=(n, n)).tocsr(), directed=False)[1]
    loops, skipped = [], []
    for c in np.unique(label[wa[new]]):
        sel = np.flatnonzero(label[wa] == c)
        if np.isin(np.concatenate([wa[sel], wb[sel]]), upper_cut_rows).any():
            skipped.append({'edges': int(len(sel)), 'reason': 'touches the rim'})
            continue
        for cycle in walk(wa[sel], wb[sel]):
            rows = sel[cycle]
            loops.append({'ids': wa[rows], 'rows': ra[rows], 'face': face[rows], 'nextRows': rb[rows],
                          'oldEdges': int((~new[rows]).sum())})
    return loops, skipped


def walk(a, b):
    """Split directed edges a->b into simple cycles (pinched loops split at
    the repeated vertex). Returns index arrays into a/b."""
    out = defaultdict(list)
    for i, v in enumerate(a.tolist()):
        out[v].append(i)
    used = np.zeros(len(a), bool)
    cycles = []
    for start in range(len(a)):
        if used[start]:
            continue
        path, seen = [], {}
        i = start
        while True:
            if used[i]:
                break
            used[i] = True
            if int(a[i]) in seen:
                # A pinch: close the sub-cycle that started at this vertex.
                k = seen[int(a[i])]
                cycles.append(np.array(path[k:])); path = path[:k]
                seen = {int(a[j]): n for n, j in enumerate(path)}
            seen[int(a[i])] = len(path); path.append(i)
            nxt = [j for j in out[int(b[i])] if not used[j]]
            if not nxt:
                break
            i = nxt[0]
        if path:
            if int(b[path[-1]]) == int(a[path[0]]):
                cycles.append(np.array(path))
            else:
                raise ValueError(f'open hole boundary ({len(path)} edges); winding is inconsistent')
    return cycles


def bisect(points, tris, boundary, limit, max_passes=CAP_MAX_PASSES):
    """Split interior edges (not in `boundary`) longer than `limit` at their
    midpoints until none is left; boundary edges are never split, so the cap
    stays welded edge to edge with the hole."""
    points, tris = [tuple(x) for x in points], np.asarray(tris, int)
    for _ in range(max_passes):
        P = np.array(points)
        e = np.concatenate([tris[:, [0, 1]], tris[:, [1, 2]], tris[:, [2, 0]]])
        key = np.sort(e, 1)
        length = np.linalg.norm(P[key[:, 0]]-P[key[:, 1]], axis=1)
        owner = np.tile(np.arange(len(tris)), 3)
        candidates = sorted({(float(length[i]), tuple(key[i])) for i in range(len(key))
                             if length[i] > limit and tuple(key[i]) not in boundary}, reverse=True)
        if not candidates:
            break
        by_edge = defaultdict(list)
        for i, k in enumerate(map(tuple, key.tolist())):
            by_edge[k].append(owner[i])
        taken = np.zeros(len(tris), bool)
        splits = {}
        for _, k in candidates:
            ts = by_edge[k]
            if taken[ts].any():
                continue
            taken[ts] = True
            splits[k] = len(points); points.append(tuple((P[k[0]]+P[k[1]])/2))
        new = []
        for t in tris.tolist():
            for c in range(3):
                k = tuple(sorted((t[c], t[(c+1) % 3])))
                if k in splits:
                    m, a, b, o = splits[k], t[c], t[(c+1) % 3], t[(c+2) % 3]
                    new += [[a, m, o], [m, b, o]]
                    break
            else:
                new.append(t)
        tris = np.array(new)
    return np.array(points), tris


def harmonic(n, tris, fixed, values):
    """Uniform-Laplacian interpolation of `values` (on the `fixed` vertices)."""
    e = np.unique(np.sort(np.concatenate([tris[:, [0, 1]], tris[:, [1, 2]], tris[:, [2, 0]]]), 1), axis=0)
    W = coo_matrix((np.ones(2*len(e)), (np.concatenate([e[:, 0], e[:, 1]]), np.concatenate([e[:, 1], e[:, 0]]))),
                   shape=(n, n)).tocsr()
    free = np.setdiff1d(np.arange(n), fixed)
    out = np.zeros((n, values.shape[1])); out[fixed] = values
    if len(free):
        L = (csr_matrix((np.asarray(W.sum(1)).ravel(), (np.arange(n), np.arange(n))), shape=(n, n))-W).tocsr()
        A = L[free][:, free].tocsc()
        rhs = -(L[free][:, fixed]@values)
        out[free] = np.asarray(spsolve(A, rhs)).reshape(len(free), -1)
    return out


def project_loop(boundary, q):
    """2D coordinates of a hole loop: gnomonic about the skull centre when
    that is a simple polygon (the cap is then lifted onto the skull), else
    orthographic onto the loop's best-fit plane (a membrane cap, for holes
    on the face or jaw that the skull does not underlie)."""
    import shapely
    n = len(boundary)
    c = skull_centre(q)
    u = (boundary-c)/q[2:]
    u /= np.linalg.norm(u, axis=1, keepdims=True)
    m = u.sum(0); m /= np.linalg.norm(m)
    e1 = np.cross(m, [0., 0., 1.]) if abs(m[2]) < .9 else np.cross(m, [1., 0., 0.])
    e1 /= np.linalg.norm(e1); e2 = np.cross(m, e1)
    cos = u@m
    tried = []
    if cos.min() > GNOMONIC_MIN_COS:
        g = np.stack([(u@e1)/cos, (u@e2)/cos], 1)
        if shapely.Polygon(g).is_valid and len({tuple(x) for x in g.tolist()}) == n:
            return 'gnomonic', g, (m, e1, e2), tried
        tried.append('gnomonic: not a simple polygon')
    else:
        tried.append(f'gnomonic: boundary {np.degrees(np.arccos(cos.min())):.0f} deg off the mean direction')
    centre = boundary.mean(0)
    _, _, vt = np.linalg.svd(boundary-centre)
    normal = vt[2]*(1 if vt[2]@(centre-c) > 0 else -1)
    a1, a2 = vt[0], np.cross(normal, vt[0])
    g = np.stack([(boundary-centre)@a1, (boundary-centre)@a2], 1)
    if shapely.Polygon(g).is_valid and len({tuple(x) for x in g.tolist()}) == n:
        return 'plane', g, (centre, a1, a2, normal), tried
    tried.append('plane: not a simple polygon')
    return 'minimum-area', None, None, tried


def minimum_area(points):
    """Minimum-area triangulation of a closed 3D polygon (dynamic programme
    over the corner order, no Steiner points): always a disc welded to every
    boundary edge, even where no projection is a simple polygon."""
    n = len(points)
    cost = np.zeros((n, n)); split = np.zeros((n, n), int)
    for span in range(2, n):
        for i in range(n-span):
            j = i+span
            k = np.arange(i+1, j)
            area = .5*np.linalg.norm(np.cross(points[k]-points[i], points[j]-points[i]), axis=1)
            total = cost[i, k]+cost[k, j]+area
            best = int(np.argmin(total))
            cost[i, j], split[i, j] = total[best], k[best]
    tris, stack = [], [(0, n-1)]
    while stack:
        i, j = stack.pop()
        if j-i < 2:
            continue
        k = split[i, j]
        tris.append([i, k, j]); stack += [(i, k), (k, j)]
    return np.array(tris)


def cap_geometry(boundary_local, q):
    """Cap of one hole loop (head-local boundary points in loop order).
    Returns (points, triangles, report); the first len(boundary) points are
    the boundary itself, every boundary edge is a cap edge (welded edge to
    edge), and only interior edges are bisected to CAP_EDGE_M."""
    import shapely
    n = len(boundary_local)
    if n == 3:
        return boundary_local.copy(), np.array([[0, 1, 2]]), {'method': 'triangle'}
    method, g, frame, tried = project_loop(boundary_local, q)
    tris = None
    if method != 'minimum-area':
        lookup = {tuple(x): i for i, x in enumerate(g.tolist())}
        tris = np.array([[lookup[tuple(x)] for x in list(t.exterior.coords)[:3]]
                         for t in shapely.constrained_delaunay_triangles(shapely.Polygon(g)).geoms])
        if len(tris) != n-2:
            tried.append(f'{method}: {len(tris)} triangles for {n} corners')
            method, tris = 'minimum-area', None
    if tris is None:
        g, tris = boundary_local.copy(), minimum_area(boundary_local)
    radius = float(np.mean(q[2:]))
    edges = {tuple(sorted((i, (i+1) % n))) for i in range(n)}
    pts2, tris = bisect(g, tris, edges, CAP_EDGE_M/radius if method == 'gnomonic' else CAP_EDGE_M)
    c = skull_centre(q)
    if method == 'minimum-area':
        # Minimum-area connectivity; a loop near the skull (mean boundary
        # excess under MEMBRANE_EXCESS_M) is lifted radially onto it, else
        # a harmonic membrane spans it.
        if np.abs(excess(boundary_local, q)).mean() < MEMBRANE_EXCESS_M:
            d = (pts2-c)/q[2:]
            base = c+d/np.linalg.norm(d, axis=1, keepdims=True)*q[2:]
            method = 'minimum-area-skull'
        else:
            base = np.zeros_like(pts2)
    elif method == 'gnomonic':
        # Gnomonic point -> direction -> skull ellipsoid, plus the harmonic
        # interpolation of the boundary's offset from its own skull point.
        m, e1, e2 = frame
        d = m[None]+pts2[:, :1]*e1+pts2[:, 1:]*e2
        d /= np.linalg.norm(d, axis=1, keepdims=True)
        base = c+d*q[2:]
    else:
        centre, a1, a2, _ = frame
        base = centre+pts2[:, :1]*a1+pts2[:, 1:]*a2
    points = base+harmonic(len(pts2), tris, np.arange(n), boundary_local-base[:n])
    points[:n] = boundary_local
    # Outward winding about the skull centre.
    normal = np.cross(points[tris[:, 1]]-points[tris[:, 0]], points[tris[:, 2]]-points[tris[:, 0]])
    flip = (normal*(points[tris].mean(1)-c)).sum(1) < 0
    tris[flip] = tris[flip][:, [0, 2, 1]]
    report = {'method': method}
    if tried:
        report['fallbacks'] = tried
    return points, tris, report


# ---------------------------------------------------------------------------
# the split (rebase_race_body.build)
# ---------------------------------------------------------------------------

def cap_owner(edge_parts):
    """CAP_OWNER (decision 1: the cap goes inside the primitive the faces came
    from): the primitive that owns most of the hole's boundary edges; a tie
    goes to `body`. R1 gave a cap to `body` whenever any edge was body, so
    the Votary horn-root caps (55 of 68 and 59 of 70 edges scalp) stayed
    drawn under helms that hide the scalp, lifted onto the skull ellipsoid at
    scalp height: domes through 49 of the 64 hide pieces. A scalp cap goes
    with the scalp; the few body edges of its hole open onto the hairline
    opening the hidden scalp leaves anyway, which the piece covers (V20
    capHeadwear checks the body caps against every hide piece)."""
    count = Counter(edge_parts)
    return 'body' if count['body'] >= count['scalp'] else 'scalp'


def texel_density(p, uv, faces, size):
    """px/cm per face (rebase_race_body.texel_density) for a square size."""
    a = area3(p, faces)*1e4
    e1, e2 = uv[faces[:, 1]]-uv[faces[:, 0]], uv[faces[:, 2]]-uv[faces[:, 0]]
    uva = np.abs(e1[:, 0]*e2[:, 1]-e1[:, 1]*e2[:, 0])/2
    ok = a > 1e-6
    return np.sqrt(uva[ok]*size*size/a[ok])


def append_rows(a, attrs):
    start = len(a['POSITION'])
    for k, v in attrs.items():
        a[k] = np.concatenate([a[k], np.asarray(v).astype(a[k].dtype)])
    return np.arange(start, start+len(attrs['POSITION']))


def dense(joints, weights, count=77):
    out = np.zeros((len(joints), count))
    for c in range(joints.shape[1]):
        np.add.at(out, (np.arange(len(joints)), joints[:, c].astype(int)), weights[:, c])
    return out


def sparse(w):
    j = np.argsort(-w, axis=1, kind='stable')[:, :4]
    v = np.take_along_axis(w, j, axis=1)
    return j, v/np.maximum(v.sum(1, keepdims=True), 1e-12)


def split(upper, slug, spec, pixels, head, origin, axis, upper_cut, head_index, source_size, skull=None, include=None):
    """Carve the features out of `upper` (rebase_race_body's cleaned v2 head
    group) in place: their faces move to upper['f'][KEY]; caps are appended
    LAST to the owning primitives with their own rows (charts in source-UV
    units at the head's median density). Returns (report, caps), caps =
    {key: {'count': n, 'colours': (n, 3, 3) corner colours 0-1}}. skull and
    include: see segment (skullFrom, foldHidden).

    Floating head components (floating_islands) that lie on the caps of the
    head proper are dropped (R2): the caps of the head proper are built
    first, then each floating component whose faces lie within
    ISLAND_ON_CAP_M of them (median) goes, with no caps of its own; any other
    floating component keeps its faces and gets its caps."""
    import trimesh
    feature, info = segment(upper, spec, pixels, head, origin, axis, upper_cut, skull=skull, include=include)
    feature, settled = settle(feature, info)
    keys, faces, part, ids = info['keys'], info['faces'], info['part'], info['ids']
    floating, floating_label = floating_islands(feature, info)
    a = upper['a']
    p = a['POSITION'].astype(float)
    uv = a['TEXCOORD_0'].astype(float)
    travel = (p-origin)@axis
    used = np.unique(faces)
    rim_ids = ids[used[np.abs(travel[used]-upper_cut) < 2e-6]]
    loops, skipped = hole_loops(info, feature, rim_ids)
    if skipped:
        raise ValueError(f'{slug}: feature holes reach the rim {skipped}')
    density = float(np.median(texel_density(p, uv, faces, source_size)))
    # Local skin colour samples: intact body/scalp faces off the rim band.
    rest = ~feature & ~floating & np.isin(part, HEADISH) & (travel[faces].min(1) > upper_cut+.01)
    centre = p[faces[rest]].mean(1)
    colour = sample_image(pixels, uv[faces[rest]].mean(1))
    weight = area3(p, faces[rest])
    tree = cKDTree(centre)
    q = info['skull']
    caps = {k: {'faces': [], 'colours': []} for k in keys}
    cap_reports = []

    def make_cap(loop):
        owner = cap_owner(part[loop['face']].tolist())
        key = next(k for k in keys if k[0] == owner)
        rows = loop['rows']
        n = len(rows)
        local, tris, geometry = cap_geometry(to_local(p[rows], head), q)
        world = to_world(local, head)
        # Normals: boundary rows copy the hole rows; inside, area-weighted
        # cap face normals.
        fn = np.cross(world[tris[:, 1]]-world[tris[:, 0]], world[tris[:, 2]]-world[tris[:, 0]])
        vn = np.zeros_like(world)
        for c in range(3):
            np.add.at(vn, tris[:, c], fn)
        vn /= np.maximum(np.linalg.norm(vn, axis=1, keepdims=True), 1e-12)
        bw = dense(a['JOINTS_0'][rows], a['WEIGHTS_0'][rows].astype(float))
        jj, ww = sparse(np.repeat(bw.mean(0)[None], len(world)-n, 0))
        # Chart: orthographic onto the plane across the cap's mean normal, in
        # source-UV units at the head's median density.
        mean_normal = fn.sum(0); mean_normal /= max(np.linalg.norm(mean_normal), 1e-12)
        e1 = np.cross(mean_normal, [0., 1., 0.]) if abs(mean_normal[1]) < .9 else np.cross(mean_normal, [1., 0., 0.])
        e1 /= np.linalg.norm(e1); e2 = np.cross(mean_normal, e1)
        rel = world-world.mean(0)
        chart = np.stack([rel@e1, rel@e2], 1)*100*density/source_size
        chart -= chart.min(0)
        # Colour: the hole edge's own texel at the boundary, the local skin
        # median inside (CAP_COLOUR_*).
        near = sorted({i for hits in tree.query_ball_point(p[rows], CAP_COLOUR_RADIUS_M) for i in hits})
        if not near:
            near = np.unique(tree.query(p[rows], k=8)[1].ravel()).tolist()
        order = np.argsort(colour[near]@LUMA)
        cw = np.cumsum(weight[near][order])
        local_median = colour[near][order[np.searchsorted(cw, cw[-1]/2)]]
        edge_colour = sample_image(pixels, uv[rows])
        inside = harmonic(len(world), tris, np.arange(n), edge_colour)
        dist = cKDTree(world[:n]).query(world)[0]
        s = np.clip(dist/CAP_COLOUR_BLEND_M, 0, 1)[:, None]
        vertex_colour = (1-s)*inside+s*local_median
        vertex_colour[:n] = edge_colour
        new_rows = append_rows(a, {
            'POSITION': np.concatenate([a['POSITION'][rows], world[n:].astype(a['POSITION'].dtype)]),
            'NORMAL': np.concatenate([a['NORMAL'][rows], vn[n:].astype(a['NORMAL'].dtype)]),
            'TEXCOORD_0': chart,
            'JOINTS_0': np.concatenate([a['JOINTS_0'][rows], jj.astype(a['JOINTS_0'].dtype)]),
            'WEIGHTS_0': np.concatenate([a['WEIGHTS_0'][rows], ww.astype(a['WEIGHTS_0'].dtype)])})
        caps[key]['faces'].append(new_rows[tris])
        caps[key]['colours'].append(vertex_colour[tris])
        cap_reports.append({'primitive': owner, 'holeEdges': n, 'oldBoundaryEdges': loop['oldEdges'],
                            'edgeOwners': dict(Counter(part[loop['face']].tolist())), 'triangles': int(len(tris)),
                            'vertices': int(len(world)), **geometry,
                            'maxBoundaryExcessM': float(np.abs(excess(local[:n], q)).max()),
                            'interiorExcessM': [float(excess(local[n:], q).min()), float(excess(local[n:], q).max())]
                            if len(local) > n else None,
                            'localSkinRGB': np.round(local_median, 4).tolist()})

    # Caps of the head proper first, then the floating components.
    loop_island = [int(floating_label[loop['face'][0]]) for loop in loops]
    for loop, island in zip(loops, loop_island):
        if island < 0:
            make_cap(loop)
    dropped = np.zeros(len(faces), bool)
    island_reports = []
    cap_now = [np.concatenate(caps[k]['faces']) for k in keys if caps[k]['faces']]
    cap_mesh = trimesh.Trimesh(a['POSITION'].astype(float), np.concatenate(cap_now), process=False) if cap_now else None
    for island in np.unique(floating_label[floating]):
        sel = floating_label == island
        centre_i = p[faces[sel]].mean(1)
        gap = (trimesh.proximity.closest_point(cap_mesh, centre_i)[1] if cap_mesh is not None
               else np.full(len(centre_i), np.inf))
        on_cap = float(np.median(gap)) < ISLAND_ON_CAP_M
        island_reports.append({'triangles': int(sel.sum()), 'byPrimitive': dict(Counter(part[sel].tolist())),
                               'capDistanceM': {'median': float(np.median(gap)), 'max': float(gap.max())},
                               'dropped': on_cap})
        if on_cap:
            dropped |= sel
    for loop, island in zip(loops, loop_island):
        if island >= 0 and not dropped[floating_label == island].any():
            make_cap(loop)
    gone = feature | dropped
    # Remaining faces per key (feature and dropped islands out), caps last.
    new_f, start = {}, 0
    for k in keys:
        count = len(upper['f'][k])
        new_f[k] = upper['f'][k][~gone[start:start+count]]
        start += count
    out = {}
    for k in keys:
        if caps[k]['faces']:
            fc = np.concatenate(caps[k]['faces'])
            new_f[k] = np.concatenate([new_f[k], fc])
            out[k] = {'count': int(len(fc)), 'colours': np.concatenate(caps[k]['colours'])}
    for k in keys:
        upper['f'][k] = new_f[k]
    # The feature gets its own rows (copies): every head primitive keeps rows
    # no other primitive indexes, so pack_head's islands (index-connected per
    # primitive) never share a row and no row is moved twice.
    rows, inverse = np.unique(faces[feature], return_inverse=True)
    upper['f'][KEY] = append_rows(a, {k: a[k][rows] for k in list(a)})[inverse.reshape(-1, 3)]
    fv = rows
    head_share = np.where(a['JOINTS_0'][fv].astype(int) == head_index, a['WEIGHTS_0'][fv], 0.).sum(1)
    flab = vertex_components(ids, faces, feature)
    report = {'kind': spec['kind'], 'material': MATERIALS[spec['kind']]['name'], 'node': NODE, 'role': ROLE,
              'triangles': int(feature.sum()),
              'byPrimitive': {k[0]: int((feature & (part == k[0])).sum()) for k in keys if (feature & (part == k[0])).any()},
              'seedTriangles': int(info['seed'].sum()), 'components': sorted(np.bincount(flab[feature]).tolist(), reverse=True),
              'settle': settled, 'skull': {'centreYZ': np.round(q[:2], 5).tolist(), 'radii': np.round(q[2:], 5).tolist(),
                                           'eyeYZ': [round(info['eye'][0], 5), round(info['eye'][1], 5)],
                                           'fittedOn': 'uncleaned head' if skull is not None else 'cleaned head'},
              'rule': {k: v for k, v in spec.items() if k != 'kind'},
              'headWeightBefore': {'min': float(head_share.min()), 'verticesBelow1': int((head_share < 1-1e-6).sum())},
              'caps': {k[0]: v['count'] for k, v in out.items()},
              'capRule': 'the last caps[<mesh>] triangles of that race_head primitive, welded to the hole boundary; '
                         'the primitive owning most of the hole edges',
              'holes': cap_reports, 'capEdgeM': CAP_EDGE_M, 'sourceDensityPxPerCm': density}
    if info['layered'] is not None:
        report['layered'] = {'triangles': int(info['layered'].sum()), 'inFeature': int((info['layered'] & feature).sum()),
                             'rule': spec['layered']}
    if info['included'].any():
        report['foldedHidden'] = {'triangles': int(info['included'].sum()), 'inFeature': int((info['included'] & feature).sum()),
                                  'rule': 'head faces a first split left robustly hidden (V7 rule) under its caps'}
    if island_reports:
        report['floatingIslands'] = {
            'triangles': int(dropped.sum()), 'components': island_reports, 'onCapM': ISLAND_ON_CAP_M,
            'rule': 'head components with no rim and no eye/eyebrow face whose faces lie on the caps of the head '
                    'proper (median centroid distance under onCapM) are dropped; triangles counts the dropped ones'}
    return report, out


def feature_group(upper, head_index, material_index):
    """The node's group for write_group_v3: its own attribute copy with every
    feature row on the Head joint alone."""
    faces = upper['f'][KEY]
    a = {k: v.copy() for k, v in upper['a'].items()}
    rows = np.unique(faces)
    a['JOINTS_0'][rows] = 0; a['JOINTS_0'][rows, 0] = head_index
    a['WEIGHTS_0'][rows] = 0; a['WEIGHTS_0'][rows, 0] = 1
    return {'a': a, 'role': ROLE, 'f': {(NODE, material_index): faces}}


def material(kind, texture):
    m = MATERIALS[kind]
    return {'name': m['name'], 'doubleSided': True, 'emissiveFactor': [0, 0, 0],
            'pbrMetallicRoughness': {'baseColorTexture': {'index': texture}, 'metallicFactor': 0,
                                     'roughnessFactor': m['roughness']}}


def add_node(d, mesh_index):
    """Append the feature node after every node (skin joints and IBMs keep
    their indices), beside the body mesh node."""
    body = next(i for i, n in enumerate(d['nodes']) if n.get('name') == 'body' and 'mesh' in n)
    parent = next((i for i, n in enumerate(d['nodes']) if body in n.get('children', [])), None)
    d['nodes'].append({'name': NODE, 'mesh': mesh_index, 'skin': d['nodes'][body]['skin']})
    index = len(d['nodes'])-1
    if parent is None:
        d['scenes'][d.get('scene', 0)]['nodes'].append(index)
    else:
        d['nodes'][parent]['children'].append(index)
    return index


# ---------------------------------------------------------------------------
# Glass flecks (batch B review): feature-coloured paint left in the dyed head
# ---------------------------------------------------------------------------

# A head face (body/scalp; caps, the rim band and the eye-front box out)
# whose 7-sample median colour lies within repaint['colourDistance'] (sRGB
# 0-255) of the feature's median colour is glass paint the split left in the
# dyed head: flecks too flat to seed (under 6 mm proud on the Glasswarden
# male), crystal pieces under FOLD_FACES (V20 wants >= 20-face feature
# components) and the painted bases of the crystals. Their texels, in a copy
# of the source image, take the local skin colour (the area-weighted
# luminance median of the head faces within REPAINT_RADIUS_M whose colour is
# over REPAINT_SKIN_DISTANCE from the glass) scaled by the texel's own
# luminance against the glass median, clamped to REPAINT_SHADE, so the skin
# dye tints skin there and not glass. Faces in front of the eyes (eye glow
# paint: eyeBehindM behind the eye line, up to eyeAboveM above it) keep their
# colour. Texels of feature, eye and eyebrow faces are never written. V20
# then measures what is left on the baked atlas (glass_left).
REPAINT_RADIUS_M = .025
REPAINT_SKIN_DISTANCE = 70.
REPAINT_SHADE = (.9, 1.08)
REPAINT_DILATE_PX = 2


def _uv_mask(uv, faces, size, colours=None):
    """Texels whose centre lies in the faces' UV triangles (PIL fill) as a
    bool mask, plus per-texel colours (one sRGB 0-255 colour per face) when
    given. Faces spanning over half the image (wrapped charts) are skipped."""
    from PIL import Image, ImageDraw
    h, w = size
    mask = Image.new('L', (w, h), 0)
    draw = ImageDraw.Draw(mask)
    paint = None if colours is None else Image.new('RGB', (w, h), (0, 0, 0))
    pdraw = None if paint is None else ImageDraw.Draw(paint)
    for i, f in enumerate(faces):
        pts = [(float(u*w-.5), float(v*h-.5)) for u, v in (np.asarray(uv[f], float) % 1)]
        xs, ys = [x for x, _ in pts], [y for _, y in pts]
        if max(xs)-min(xs) > w/2 or max(ys)-min(ys) > h/2:
            continue
        draw.polygon(pts, fill=255)
        if pdraw is not None:
            pdraw.polygon(pts, fill=tuple(int(round(c)) for c in colours[i]))
    out = np.asarray(mask) > 0
    return (out, np.asarray(paint).astype(float)) if paint is not None else out


def _eye_line(local_eyes):
    return float(np.median(local_eyes[:, 1])), float(np.median(local_eyes[:, 2]))


def repaint(upper, spec, pixels, head, caps, origin, axis, upper_cut, rim_band=.002):
    """Repaint the glass flecks the split left in the dyed head (spec
    'repaint'; run after split). Returns (pixels copy, report); `pixels`
    (the 0-1 head source) is not modified."""
    from scipy import ndimage
    rule = spec['repaint']
    a = upper['a']
    p = a['POSITION'].astype(float)
    uv = a['TEXCOORD_0'].astype(float)
    local = to_local(p, head)
    feature = upper['f'][KEY]
    glass = np.median(face_colours(pixels, uv, feature), 0)
    ey, ez = _eye_line(local[np.unique(np.concatenate([f for k, f in upper['f'].items() if k[0] == 'eyes']))])
    travel = (p-origin)@axis
    faces, parts = [], []
    for k, f in upper['f'].items():
        if k[0] not in HEADISH:
            continue
        own = f[:len(f)-caps.get(k, {'count': 0})['count']]
        faces.append(own)
        parts += [k[0]]*len(own)
    faces, parts = np.concatenate(faces), np.array(parts)
    colour = face_colours(pixels, uv, faces)
    distance = np.linalg.norm(colour-glass, axis=1)
    centre = local[faces].mean(1)
    rim = (np.abs(travel-upper_cut) < rim_band)[faces].any(1)
    eye_front = (centre[:, 2] > ez-rule['eyeBehindM']) & (centre[:, 1] < ey+rule['eyeAboveM'])
    pick = (distance < rule['colourDistance']) & ~rim & ~eye_front
    skin = (distance > REPAINT_SKIN_DISTANCE) & ~rim
    report = {'glassRGB': np.round(glass, 1).tolist(),
              'rule': {**rule, 'radiusM': REPAINT_RADIUS_M, 'skinDistance': REPAINT_SKIN_DISTANCE,
                       'shade': list(REPAINT_SHADE), 'dilatePx': REPAINT_DILATE_PX},
              'faces': {n: int((pick & (parts == n)).sum()) for n in HEADISH},
              'areaCm2': round(float(area3(p, faces[pick]).sum()*1e4), 2),
              'eyeFrontKept': int(((distance < rule['colourDistance']) & eye_front & ~rim).sum())}
    if not pick.any():
        report['texels'] = 0
        return pixels, report
    picked = faces[pick]
    sc, sw, scol = p[faces[skin]].mean(1), area3(p, faces[skin]), colour[skin]
    tree = cKDTree(sc)
    fills = []
    for c in p[picked].mean(1):
        near = tree.query_ball_point(c, REPAINT_RADIUS_M)
        near = np.array(near if near else tree.query(c, k=8)[1].tolist())
        order = np.argsort(scol[near]@LUMA)
        cw = np.cumsum(sw[near][order])
        fills.append(scol[near][order[np.searchsorted(cw, cw[-1]/2)]])
    fills = np.array(fills)
    size = pixels.shape[:2]
    inside, paint = _uv_mask(uv, picked, size, fills)
    grown = ndimage.binary_dilation(inside, iterations=REPAINT_DILATE_PX)
    protect = _uv_mask(uv, np.concatenate([feature]+[f for k, f in upper['f'].items() if k[0] in PROTECTED]), size)
    target = grown & ~protect
    # Dilated texels take the nearest picked texel's fill.
    _, (iy, ix) = ndimage.distance_transform_edt(~inside, return_indices=True)
    fill = paint[iy, ix]/255
    shade = np.clip((pixels@LUMA)/max(float(glass@LUMA)/255, 1e-6), *REPAINT_SHADE)
    out = pixels.copy()
    out[target] = np.clip(fill[target]*shade[target, None], 0, 1)
    report.update(texels=int(target.sum()), protectedTexels=int((grown & protect).sum()),
                  fillRGB={'min': np.round(fills.min(0), 1).tolist(), 'median': np.round(np.median(fills, 0), 1).tolist(),
                           'max': np.round(fills.max(0), 1).tolist()})
    return out, report


def glass_left(d, b, parts, caps, head, accessor, rule):
    """V20 measure for a 'repaint' spec: area of dyed-head faces (race_head
    body/scalp, caps out, the eye-front box out) whose colour on the baked
    head atlas lies within rule['colourDistance'] of the feature node's median
    colour on the same atlas."""
    import io
    from PIL import Image
    body = next(m for m in d['meshes'] if m['name'] == 'body')
    head_prim = next(q for q in body['primitives'] if q.get('extras', {}).get('sourceRole') == 'race_head')
    tex = d['materials'][head_prim['material']]['pbrMetallicRoughness']['baseColorTexture']['index']
    view = d['bufferViews'][d['images'][d['textures'][tex]['source']]['bufferView']]
    start = view.get('byteOffset', 0)
    atlas = np.asarray(Image.open(io.BytesIO(bytes(b[start:start+view['byteLength']]))).convert('RGB')).astype(float)/255
    fprim = next(m for m in d['meshes'] if m['name'] == NODE)['primitives'][0]
    ff = accessor(d, b, fprim['indices']).astype(int).reshape(-1, 3)
    glass = np.median(face_colours(atlas, accessor(d, b, fprim['attributes']['TEXCOORD_0']).astype(float), ff), 0)
    ey, ez = _eye_line(np.concatenate([to_local(q['POSITION'][np.unique(f)].astype(float), head)
                                       for name, role, q, f in parts if role == 'race_head' and name == 'eyes']))
    area, count = 0., 0
    for name, role, q, f in parts:
        if role != 'race_head' or name not in HEADISH:
            continue
        own = f[:len(f)-caps.get(name, 0)]
        qp = q['POSITION'].astype(float)
        centre = to_local(qp[own].mean(1), head)
        eye_front = (centre[:, 2] > ez-rule['eyeBehindM']) & (centre[:, 1] < ey+rule['eyeAboveM'])
        hit = (np.linalg.norm(face_colours(atlas, q['TEXCOORD_0'].astype(float), own)-glass, axis=1)
               < rule['colourDistance']) & ~eye_front
        area += float(area3(qp, own[hit]).sum())
        count += int(hit.sum())
    return {'glassRGB': np.round(glass, 1).tolist(), 'areaCm2': round(area*1e4, 2), 'faces': count,
            'limitCm2': rule['leftLimitCm2'], 'colourDistance': rule['colourDistance'],
            'rule': 'dyed-head faces (caps and the eye-front box out) within colourDistance of the feature median '
                    'colour on the baked atlas'}


# ---------------------------------------------------------------------------
# V20 (rebase_race_body.verify)
# ---------------------------------------------------------------------------

# V20: crown-region race_head/scalp vertices (above the eye line plus
# CROWN_ABOVE_EYE_M, ears excluded) stay within FEATURE_FREE_M of the skull
# fit; cap interiors never rise CAP_RISE_M above their own hole's boundary.
FEATURE_FREE_M, CROWN_ABOVE_EYE_M, CAP_RISE_M = .015, .005, .001
EAR = {'absXOver': .06, 'yUnderEye': .06}


def expected(slug, spec=None):
    """Whether a body must carry the node: every FEATURES slug (R2). A body
    built without the split (a head without the required source, or the
    feature hook off) fails V20 instead of verifying feature-free; the
    crowned Glasswarden female head is required by V23 as well."""
    return slug in FEATURES


def cap_owner_check(parts, caps):
    """V20 (R2): every cap component sits in the primitive that owns most of
    its hole's edges (cap_owner). The hole edges are the cap component's
    boundary edges (welded over every race_head primitive), owned by the
    primitive whose non-cap faces use them."""
    heads = [(name, q, ff) for name, role, q, ff in parts if role == 'race_head' and name in HEADISH]
    points = np.concatenate([q['POSITION'].astype(float) for _, q, _ in heads])
    wid = weld_ids(points)
    off, owned, cap_faces = 0, {}, []
    for name, q, ff in heads:
        n = caps.get(name, 0)
        key, _ = edge_keys(wid, ff[:len(ff)-n]+off)
        owned[name] = set(key.tolist())
        if n:
            cap_faces.append((name, ff[len(ff)-n:]+off))
        off += len(q['POSITION'])
    rows, wrong = [], 0
    for name, cf in cap_faces:
        label = vertex_components(wid, cf, np.ones(len(cf), bool))
        for c in np.unique(label):
            key, _ = edge_keys(wid, cf[label == c])
            k, count = np.unique(key, return_counts=True)
            boundary = k[count == 1]
            votes = Counter({other: int(np.isin(boundary, list(keys)).sum()) for other, keys in owned.items()})
            want = cap_owner(list(votes.elements()))
            rows.append({'primitive': name, 'holeEdges': dict(votes), 'owner': want})
            wrong += want != name
    return wrong == 0, {'caps': len(rows), 'wrongPrimitive': wrong,
                        'rule': 'a cap goes in the primitive owning most of its hole edges (a tie goes to body)',
                        'mixedHoles': [r for r in rows if sum(1 for v in r['holeEdges'].values() if v) > 1]}


def open_edge_count(p, faces):
    ids = weld_ids(p)
    key, _ = edge_keys(ids, faces)
    _, count = np.unique(key, return_counts=True)
    return int((count == 1).sum())


def face_signatures(a, faces, fields):
    """Per-face sha256 of the corner bytes (verify_shared_player_bodies.signatures order)."""
    return [hashlib.sha256(b''.join(a[k][f].tobytes() for k in fields)).hexdigest() for f in faces]


def verify_features(d, b, parts, slug, spec, missing_positions, head, head_index, accessor):
    """V20 values for a candidate. parts: vspb.primitives list; missing_positions:
    Counter of POSITION signatures of the v2 head faces absent from the
    candidate's race_head (caps excluded); head: Head world matrix."""
    features = spec.get('raceFeatures')
    want = expected(slug, spec)
    nodes = [i for i, n in enumerate(d['nodes']) if n.get('name') == NODE]
    values = {'expected': want, 'nodes': len(nodes)}
    if not want:
        values['absent'] = not nodes and not features
        return values['absent'], values
    if len(nodes) != 1 or not features:
        return False, values
    node = d['nodes'][nodes[0]]
    mesh = d['meshes'][node['mesh']]
    joints = d['skins'][0]['joints']
    prim = mesh['primitives'][0]
    mat = d['materials'][prim['material']]
    body = next(m for m in d['meshes'] if m['name'] == 'body')
    head_prim = next(p for p in body['primitives'] if p.get('extras', {}).get('sourceRole') == 'race_head')
    head_image = d['textures'][d['materials'][head_prim['material']]['pbrMetallicRoughness']['baseColorTexture']['index']]['source']
    texture = mat['pbrMetallicRoughness'].get('baseColorTexture', {}).get('index')
    kind = features['kind']
    structure = {'onePrimitive': len(mesh['primitives']) == 1, 'role': prim.get('extras', {}).get('sourceRole') == ROLE,
                 'skin': node.get('skin') == 0, 'afterJoints': nodes[0] > max(joints),
                 'material': mat.get('name') == MATERIALS[kind]['name'],
                 'roughness': abs(mat['pbrMetallicRoughness'].get('roughnessFactor', 1)-MATERIALS[kind]['roughness']) < 1e-6
                 and mat['pbrMetallicRoughness'].get('metallicFactor', 1) == 0 and mat.get('emissiveFactor', [0, 0, 0]) == [0, 0, 0]
                 and mat.get('alphaMode', 'OPAQUE') == 'OPAQUE',
                 'headAtlasImage': texture is not None and d['textures'][texture]['source'] == head_image}
    a = {k: accessor(d, b, v) for k, v in prim['attributes'].items()}
    f = accessor(d, b, prim['indices']).astype(int).reshape(-1, 3)
    rows = np.unique(f)
    jj, ww = a['JOINTS_0'][rows].astype(int), a['WEIGHTS_0'][rows].astype(float)
    head_only = bool(((jj[:, 0] == head_index) & (np.abs(ww[:, 0]-1) < 1e-7)).all() and (ww[:, 1:] == 0).all())
    mine = Counter(face_signatures(a, f, ('POSITION',)))
    from_v2 = not (mine-missing_positions) and len(f) == features['triangles']
    sizes = np.bincount(vertex_components(weld_ids(a['POSITION']), f, np.ones(len(f), bool)))
    values.update(structure=structure, triangles=int(len(f)), headWeightsOnly=head_only, facesFromV2=from_v2,
                  removedV2NotInFeature=int(sum((missing_positions-mine).values())),
                  componentSizes=sorted(sizes.tolist(), reverse=True))
    owners_ok, values['capOwners'] = cap_owner_check(parts, features.get('caps', {}))
    if 'floatingIslands' in features:
        values['floatingIslands'] = features['floatingIslands']
    # Skull fit and crown excess on the candidate head (features out).
    heads = [(name, q, ff) for name, role, q, ff in parts if role == 'race_head']
    if 'skull' in features:
        # The build's fit: refitting without the features and with the caps
        # moves the ellipsoid (stoneborn_female: z radius 113 -> 101 mm).
        sk = np.array(features['skull']['centreYZ']+features['skull']['radii'], float)
        ey, ez = features['skull']['eyeYZ']
    else:
        local = {name: to_local(q['POSITION'][np.unique(ff)], head) for name, q, ff in heads}
        sk, ey, ez = fit_skull(local)
    caps = features.get('caps', {})
    crown, cap_rise, points, faces_all, faces_open, off = [], [], [], [], [], 0
    for name, q, ff in heads:
        n = caps.get(name, 0)
        p = q['POSITION'].astype(float)
        points.append(p)
        faces_all.append(ff+off); faces_open.append(ff[:len(ff)-n]+off)
        if name in HEADISH:
            original = np.unique(ff[:len(ff)-n])
            cap_rows = np.setdiff1d(np.unique(ff[len(ff)-n:]), original) if n else np.zeros(0, int)
            loc = to_local(p[original], head)
            region = (loc[:, 1] > ey+CROWN_ABOVE_EYE_M) & ~((np.abs(loc[:, 0]) > EAR['absXOver'])
                                                            & (loc[:, 1] < ey+EAR['yUnderEye']))
            if region.any():
                crown.append(float(excess(loc[region], sk).max()))
            if len(cap_rows):
                cf = ff[len(ff)-n:]
                ids = weld_ids(p)
                label = vertex_components(ids, cf, np.ones(len(cf), bool))
                interior_ids = set(ids[np.setdiff1d(np.unique(cf), original)].tolist()) - set(ids[original].tolist())
                for c in np.unique(label):
                    cr = np.unique(cf[label == c])
                    inner = cr[np.isin(ids[cr], list(interior_ids))]
                    edge = cr[~np.isin(ids[cr], list(interior_ids))]
                    if len(inner) and len(edge):
                        e_in = excess(to_local(p[inner], head), sk).max()
                        e_edge = excess(to_local(p[edge], head), sk).max()
                        cap_rise.append(float(e_in-max(e_edge, FEATURE_FREE_M)))
        off += len(p)
    feature_p = a['POSITION'].astype(float)
    points_all = np.concatenate(points)
    # Open edges in one welded id space: the head with its caps may keep only
    # edges the cleaned head (head without caps plus feature) had open. Caps
    # close every edge the split opened; a hole the split merged with an
    # older cleanup hole (the crowned Glasswarden female's removed inner
    # shell) is closed whole, so the head may end with fewer open edges.
    wid = weld_ids(np.concatenate([points_all, feature_p]))

    def open_set(faces):
        key, _ = edge_keys(wid, faces)
        k, count = np.unique(key, return_counts=True)
        return set(k[count == 1].tolist())
    closed_set = open_set(np.concatenate(faces_all))
    opened_set = open_set(np.concatenate(faces_open+[f+len(points_all)]))
    closed, opened = len(closed_set), len(opened_set)
    new_open = len(closed_set-opened_set)
    values.update(skull={'centreYZ': np.round(sk[:2], 4).tolist(), 'radii': np.round(sk[2:], 4).tolist(), 'eyeY': round(float(ey), 4),
                         'source': 'build' if 'skull' in features else 'refit'},
                  crownExcessMaxM=max(crown) if crown else None, crownExcessLimitM=FEATURE_FREE_M,
                  capRiseMaxM=max(cap_rise) if cap_rise else None, capRiseLimitM=CAP_RISE_M,
                  openEdges={'headWithCaps': closed, 'headWithoutCapsPlusFeature': opened, 'newOpenEdges': new_open,
                             'cleanedHeadEdgesNoLongerOpen': len(opened_set-closed_set)},
                  caps=caps, rule='crown-region race_head/scalp vertices (y > eye + 5 mm, ears |x| > .06 below eye + 6 cm '
                                  'excluded) within 15 mm of the candidate skull fit; cap interiors at most 1 mm above '
                                  'their hole (or 15 mm); the head with its caps keeps no edge open that the cleaned '
                                  'head (head without caps plus feature) had closed: caps close every edge the split '
                                  'opened')
    # Report only (R2 review): the crown measured against a skull refitted on
    # the candidate head without its caps, beside the build's fit the gate
    # uses (the fit's vertical radius sits at its .13 bound on the featured
    # pilots, so the gated measure partly tests the fit against itself).
    if 'skull' in features:
        local = {name: to_local(q['POSITION'][np.unique(ff[:len(ff)-caps.get(name, 0)])], head) for name, q, ff in heads}
        rk, rey, _ = fit_skull(local)
        refit = []
        for name, q, ff in heads:
            if name in HEADISH:
                loc = to_local(q['POSITION'].astype(float)[np.unique(ff[:len(ff)-caps.get(name, 0)])], head)
                region = (loc[:, 1] > rey+CROWN_ABOVE_EYE_M) & ~((np.abs(loc[:, 0]) > EAR['absXOver'])
                                                               & (loc[:, 1] < rey+EAR['yUnderEye']))
                if region.any():
                    refit.append(float(excess(loc[region], rk).max()))
        values['crownRefit'] = {'centreYZ': np.round(rk[:2], 4).tolist(), 'radii': np.round(rk[2:], 4).tolist(),
                                'crownExcessMaxM': max(refit) if refit else None, 'gated': False}
    ok = (all(structure.values()) and head_only and from_v2 and values['removedV2NotInFeature'] >= 0
          and min(sizes) >= FOLD_FACES and (not crown or max(crown) <= FEATURE_FREE_M)
          and (not cap_rise or max(cap_rise) <= CAP_RISE_M) and new_open == 0 and owners_ok)
    return bool(ok), values
