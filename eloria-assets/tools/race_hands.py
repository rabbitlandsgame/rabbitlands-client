"""Race hand projection (race programme P4, decision 7).

Stoneborn (stone) and Ssarathi (scale colour) hands are projected from each
race's 2048 Meshy source (generate_models/eloria-races-meshy/<slug>_tpose.glb,
placed in its rigged donor's space, <slug>_tpose_rigged.glb) onto the Human
hands of the rebased body (body primitive shared_body, skin atlas only).
Mycelari is skipped. Per side (left and right hands own separate texels):

1. Human hand: shared_body faces past the forearm midpoint (the wrist skin
   starts at |x| .709 male / .741 female, the hand joint at .75).
2. Source hand: source faces in HAND_BOX around the donor <Side>Hand joint,
   their largest welded component, minus the dark sleeve before the cuff
   (found from the luminance step along the arm).
3. Alignment: per-axis box scaling from the hand joint, a trimmed affine ICP
   (Human points past the hand joint -> source surface samples), then one
   trimmed two-way affine ICP per finger. Fingers are segmented on both meshes
   by geometry (geodesic_fingers: tips from wrist-distance maxima; the Human
   hand is weighted to hand_<side> only and its fingers do not follow the
   skeleton's finger joints). A finger map covers the source finger's free
   length (its web distance) and fades into the palm map over FINGER_BLEND_M;
   the map weights are smoothed over the Human mesh so neighbouring regions
   blend. A coarse-to-fine non-rigid refinement (REFINE_SCHEDULE) then pulls
   the mapped hand onto the source surface with a smooth displacement field.
4. Residual (gate): distance from each mapped Human hand vertex past the hand
   joint to the source skin surface, 90th percentile per finger and palm,
   <= GATE_P90_MM[race] (4 mm Stoneborn, 5 mm Ssarathi; affine-only numbers
   are reported too). A side missing it falls back to tone-only.
5. Lookup: each hand texel's 3D point (texel centre on its UV triangle) is
   mapped and takes the colour of the nearest source surface sample whose
   normal agrees with the mapped Human normal (dot > NORMAL_GATE; the
   Stoneborn male source is double-shelled), bilinear at the sample's UV.
   Texels over BRIGHT_LIMIT x the median luminance (Meshy's grey fill between
   source fingers) are refilled from neighbouring hand texels.
6. Luminance match: one linear gain takes the hand's texel-median luminance
   to the face reference's (the calibrated skin dye then treats hand and face
   alike, as decision 7 asks); chroma stays the source's. Claws transfer as
   colour only.
7. Wrist blend: weight 0 at the first hand-face vertex along lowerarm->hand,
   1 at the hand joint (smoothstep), under the sleeve.
8. Gutter: projected colours are pushed GUTTER_PX texels into texels no face
   of the atlas covers, so mip filtering does not bleed the old hand colour.

Tone-only fallback: the dyed Human hand keeps its own detail and takes the
source hand's luminance-matched median colour by one linear per-channel gain.

`project_hands(...)` is pure (arrays in, texels + report out);
`apply_hand_texels(image, result)` blends them into a copy of the skin image.

    python eloria-assets/tools/race_hands.py check --root <wt> --slug stoneborn_male [--out <dir outside godot-client>]
"""
from __future__ import annotations

import argparse
import io
import json
from pathlib import Path
import sys

import numpy as np
from PIL import Image
from scipy.ndimage import convolve
from scipy.sparse import coo_matrix
from scipy.sparse.csgraph import connected_components, dijkstra
from scipy.spatial import cKDTree

sys.path.insert(0, str(Path(__file__).resolve().parent))
import equipment_authoring as ea  # noqa: E402

RACES = ('stoneborn_male', 'stoneborn_female', 'ssarathi_male', 'ssarathi_female')
GATE_P90_MM = {'stoneborn': 4.0, 'ssarathi': 5.0}
PER_FINGER = {'stoneborn': True, 'ssarathi': True}
NORMAL_GATE = .3
LOOKUP_K = 48
SAMPLE_DENSITY = 4e6          # source surface samples per m^2 (about one per 0.5 mm)
HAND_BOX = (-.04, .25, .075)  # source: along forearm->hand from the hand joint (min, max), radial max (m)
CUFF_MARGIN_M = .002
ICP_FROM_M = -.005            # Human hand points used for alignment: past hand joint + this
WEIGHT_SMOOTHING = 3          # 1-ring averaging passes over the Human hand's map weights
# Non-rigid refinement after the affine maps, coarse to fine: each pass moves
# the mapped Human hand REFINE_STEP of the way to its normal-gated nearest
# source points, the displacements smoothed over the scheduled number of
# 1-ring passes on the Human hand (12 passes: about 3 cm; 2 passes: about
# 1 cm), pairs farther than REFINE_REJECT_M left out.
REFINE_SCHEDULE = (12,)*5+(6,)*5+(3,)*5+(2,)*5
REFINE_STEP, REFINE_REJECT_M = .5, .02
ICP_ITERATIONS = 30
ICP_TRIM = 90                 # percentile of correspondences kept
FINGER_ITERATIONS = 25
FINGER_BLEND_M = .015         # finger map fades out over this many m past the finger web
TIP_MERGE_M = .015
TIP_LANE_M = .010             # a tip is the furthest-reaching candidate of its lateral lane
FINGER_REACH_WINDOW_M = .10   # finger tips reach within this of the furthest one
FINGERS = ('thumb', 'index', 'middle', 'ring', 'pinky')
GUTTER_PX = 4
OPPOSED_MAX = .05             # V22: opposed-normal lookups allowed per side
TEXEL_TOLERANCE = 4.          # V22: mean |candidate - redone projection| on hand texels, sRGB levels
# Texels brighter than BRIGHT_LIMIT x the hand's median linear luminance are
# the Meshy grey fill seen between source fingers (0.5-0.9% on the Stoneborn
# hands, none on Ssarathi); they are refilled from neighbouring hand texels.
BRIGHT_LIMIT = 2.2
LUMA = np.array([.2126, .7152, .0722])
SOURCE_FOLDER = 'generate_models/eloria-races-meshy'


# ---------------------------------------------------------------------------
# Colour and raster helpers (same conventions as rebase_race_body)
# ---------------------------------------------------------------------------

def srgb_to_linear(c):
    c = np.asarray(c, float)
    return np.where(c <= .04045, c/12.92, ((c+.055)/1.055)**2.4)


def linear_to_srgb(c):
    c = np.clip(np.asarray(c, float), 0, 1)
    return np.where(c <= .0031308, c*12.92, 1.055*c**(1/2.4)-.055)


def bilinear(pixels, uv):
    """sRGB 0-1 at UV (glTF texel-centre convention, repeat wrap); pixels 0-1."""
    size = np.array(pixels.shape[:2][::-1])
    xy = (np.asarray(uv, float) % 1)*size-.5
    lo = np.floor(xy).astype(int)
    t = xy-lo
    hi = (lo+1) % size
    lo %= size
    return ((pixels[lo[:, 1], lo[:, 0]]*(1-t[:, 0, None])+pixels[lo[:, 1], hi[:, 0]]*t[:, 0, None])*(1-t[:, 1, None])
            + (pixels[hi[:, 1], lo[:, 0]]*(1-t[:, 0, None])+pixels[hi[:, 1], hi[:, 0]]*t[:, 0, None])*t[:, 1, None])


def raster(uv, faces, size, tol=-1e-5):
    """Texel centres inside each UV triangle: face, row, column, barycentric."""
    w, h = size
    px = np.asarray(uv, float)*[w, h]
    out = [[], [], [], []]
    for fi, f in enumerate(faces):
        t = px[f]
        lo = np.maximum(np.floor(t.min(0)-.5).astype(int), 0)
        hi = np.minimum(np.ceil(t.max(0)-.5).astype(int), [w-1, h-1])
        if (lo > hi).any():
            continue
        e1, e2 = t[1]-t[0], t[2]-t[0]
        det = e1[0]*e2[1]-e1[1]*e2[0]
        if abs(det) < 1e-12:
            continue
        yy, xx = np.mgrid[lo[1]:hi[1]+1, lo[0]:hi[0]+1]
        dx, dy = xx+.5-t[0, 0], yy+.5-t[0, 1]
        u = (dx*e2[1]-dy*e2[0])/det
        v = (e1[0]*dy-e1[1]*dx)/det
        inside = (u >= tol) & (v >= tol) & (1-u-v >= tol)
        if inside.any():
            out[0].append(np.full(int(inside.sum()), fi)); out[1].append(yy[inside])
            out[2].append(xx[inside]); out[3].append(np.stack([1-u-v, u, v], -1)[inside])
    if not out[0]:
        return np.zeros(0, int), np.zeros(0, int), np.zeros(0, int), np.zeros((0, 3))
    return tuple(np.concatenate(v) for v in out)


def occupancy(uv_faces, size):
    """Texels covered by any of the given (uv, faces) sets."""
    mask = np.zeros(size[::-1], bool)
    for uv, faces in uv_faces:
        _, y, x, _ = raster(uv, faces, size)
        mask[y, x] = True
    return mask


# ---------------------------------------------------------------------------
# Geometry helpers
# ---------------------------------------------------------------------------

def weld(p, tol=1e-6):
    p = np.asarray(p, float)
    pairs = cKDTree(p).query_pairs(tol, output_type='ndarray')
    return connected_components(coo_matrix((np.ones(len(pairs)), (pairs[:, 0], pairs[:, 1])),
                                           shape=(len(p), len(p))).tocsr(), directed=False)[1]


def surface_samples(p, faces, density=SAMPLE_DENSITY, normals=None, uv=None, rng=None):
    """Area-proportional surface samples: points, face index, barycentrics,
    interpolated (unit) normals and UVs when given."""
    rng = np.random.default_rng(0) if rng is None else rng
    tri = np.asarray(p, float)[faces]
    area = .5*np.linalg.norm(np.cross(tri[:, 1]-tri[:, 0], tri[:, 2]-tri[:, 0]), axis=1)
    count = np.maximum(1, np.round(area*density).astype(int))
    fi = np.repeat(np.arange(len(faces)), count)
    r1, r2 = rng.random(len(fi)), rng.random(len(fi))
    s = np.sqrt(r1)
    bary = np.stack([1-s, s*(1-r2), s*r2], 1)
    out = {'P': np.einsum('ni,nij->nj', bary, tri[fi]), 'face': fi, 'bary': bary}
    if normals is not None:
        n = np.einsum('ni,nij->nj', bary, np.asarray(normals, float)[faces[fi]])
        out['N'] = n/np.maximum(np.linalg.norm(n, axis=1, keepdims=True), 1e-12)
    if uv is not None:
        out['UV'] = np.einsum('ni,nij->nj', bary, np.asarray(uv, float)[faces[fi]])
    return out


def closest_distance(points, p, faces):
    """Exact point-to-triangle-mesh distance (trimesh)."""
    import trimesh
    mesh = trimesh.Trimesh(np.asarray(p, float), np.asarray(faces, int), process=False)
    _, distance, _ = trimesh.proximity.closest_point(mesh, np.asarray(points, float))
    return distance


def affine_fit(x, y, weights=None):
    """Least-squares affine (A, t) with y ~ x A^T + t."""
    X = np.hstack([x, np.ones((len(x), 1))])
    if weights is not None:
        w = np.sqrt(weights)[:, None]
        sol = np.linalg.lstsq(X*w, y*w, rcond=None)[0]
    else:
        sol = np.linalg.lstsq(X, y, rcond=None)[0]
    return sol[:3].T, sol[3]


# ---------------------------------------------------------------------------
# Sources
# ---------------------------------------------------------------------------

def source_paths(root, slug):
    """(tpose, rigged donor) Meshy files for `slug`, searched upwards from
    the checkout like rebase_race_body.locate_head_texture."""
    stem = slug.replace('votary_', 'whitehorn_votary_')
    for base in (Path(root).resolve(), *Path(root).resolve().parents):
        folder = base/SOURCE_FOLDER
        if (folder/f'{stem}_tpose.glb').exists():
            return folder/f'{stem}_tpose.glb', folder/f'{stem}_tpose_rigged.glb'
    raise FileNotFoundError(f'{SOURCE_FOLDER}/{stem}_tpose.glb not found above {root}')


def load_source(tpose, rigged):
    """Meshy source mesh in its rigged donor's space (raw mesh bbox fitted to
    the donor mesh bbox by height, centres matched), its image (sRGB 0-1) and
    the donor joints (rest world positions)."""
    d, b = ea.read_glb(Path(rigged))
    names = [d['nodes'][j].get('name') for j in d['skins'][0]['joints']]
    ibm = ea.accessor_array(d, b, d['skins'][0]['inverseBindMatrices']).astype(float).reshape(-1, 4, 4).transpose(0, 2, 1)
    joints = {n: np.linalg.inv(m)[:3, 3] for n, m in zip(names, ibm)}
    donor = ea.accessor_array(d, b, d['meshes'][0]['primitives'][0]['attributes']['POSITION']).astype(float)
    dlo, dhi = donor.min(0), donor.max(0)
    d, b = ea.read_glb(Path(tpose))
    prim = d['meshes'][0]['primitives'][0]
    P = ea.accessor_array(d, b, prim['attributes']['POSITION']).astype(float)
    N = ea.accessor_array(d, b, prim['attributes']['NORMAL']).astype(float)
    UV = ea.accessor_array(d, b, prim['attributes']['TEXCOORD_0']).astype(float)
    F = ea.accessor_array(d, b, prim['indices']).astype(int).reshape(-1, 3)
    tex = d['materials'][prim['material']]['pbrMetallicRoughness']['baseColorTexture']['index']
    image = d['images'][d['textures'][tex]['source']]
    view = d['bufferViews'][image['bufferView']]
    payload = bytes(b[view.get('byteOffset', 0):view.get('byteOffset', 0)+view['byteLength']])
    pixels = np.asarray(Image.open(io.BytesIO(payload)).convert('RGB')).astype(float)/255
    lo, hi = P.min(0), P.max(0)
    scale = (dhi[1]-dlo[1])/(hi[1]-lo[1])
    offset = (dlo+dhi)/2-scale*(lo+hi)/2
    return {'P': P*scale+offset, 'N': N, 'UV': UV, 'F': F, 'pixels': pixels, 'joints': joints,
            'scale': float(scale), 'offset': offset}


def source_hand(src, side):
    """Faces of the source hand skin around the donor <Side>Hand joint: the
    HAND_BOX crop, its largest welded component, and only past the sleeve
    cuff. The cuff end is where the median luminance along the arm (4 mm
    bins) first rises half way from the sleeve level (the first 3 bins) to
    the hand level (bins 0-3 cm past the joint); faces before it plus
    CUFF_MARGIN_M are the dark sleeve the Human wrist must not sample."""
    key = 'Left' if side == 'l' else 'Right'
    hj, fa = src['joints'][f'{key}Hand'], src['joints'][f'{key}ForeArm']
    axis = (hj-fa)/np.linalg.norm(hj-fa)
    c = src['P'][src['F']].mean(1)
    t = (c-hj)@axis
    radial = np.linalg.norm((c-hj)-np.outer(t, axis), axis=1)
    faces = src['F'][(t > HAND_BOX[0]) & (t < HAND_BOX[1]) & (radial < HAND_BOX[2])]
    used, inverse = np.unique(faces, return_inverse=True)
    ids = weld(src['P'][used])
    ff = ids[inverse.reshape(-1, 3)]
    e = np.concatenate([ff[:, [0, 1]], ff[:, [1, 2]]])
    n = ids.max()+1
    lab = connected_components(coo_matrix((np.ones(len(e)), (e[:, 0], e[:, 1])), shape=(n, n)).tocsr(), directed=False)[1]
    flab = lab[ff[:, 0]]
    faces = faces[flab == np.argmax(np.bincount(flab))]
    c = src['P'][faces].mean(1)
    t = (c-hj)@axis
    lum = bilinear(src['pixels'], src['UV'][faces].mean(1))@LUMA
    bins = np.arange(HAND_BOX[0], .04, .004)
    level = np.array([np.median(lum[(t >= b0) & (t < b0+.004)]) if ((t >= b0) & (t < b0+.004)).any() else np.nan
                      for b0 in bins])
    sleeve = np.nanmedian(level[:3])
    skin = np.nanmedian(level[(bins >= 0) & (bins < .03)])
    rise = np.flatnonzero(level > .5*(sleeve+skin))
    cuff = float(bins[rise[0]]) if len(rise) and skin > sleeve*1.3 else HAND_BOX[0]
    keep = t > cuff+CUFF_MARGIN_M
    return faces[keep], hj, axis, {'cuffAlongM': cuff, 'sleeveLuminance': float(sleeve), 'handLuminance': float(skin),
                                   'faces': int(keep.sum()), 'droppedSleeveFaces': int((~keep).sum())}


# ---------------------------------------------------------------------------
# Human hand and finger segmentation
# ---------------------------------------------------------------------------

def human_hand(body, joints, side):
    """Faces of the Human hand (beyond the forearm midpoint) on shared_body."""
    p = np.asarray(body['POSITION'], float)
    f = np.asarray(body['faces'], int)
    hand, fore = joints[f'hand_{side}'], joints[f'lowerarm_{side}']
    axis = (hand-fore)/np.linalg.norm(hand-fore)
    t = (p[f].mean(1)-fore)@axis
    return f[t > .5*np.linalg.norm(hand-fore)], hand, axis


def geodesic_fingers(P, faces, wrist_point, axis, side_axis, tips_wanted=5, far_m=.06):
    """Fingers of a hand mesh by geodesic tips. The Human hand is weighted to
    hand_<side> only and its fingers do not follow the skeleton's finger
    joints, so both meshes are segmented by geometry.

    wd: geodesic distance from the wrist cut (the 1% of vertices lowest along
    `axis`). Tip candidates: 1-ring local maxima of wd over far_m, merged
    within TIP_MERGE_M along the surface (highest kept); a candidate with
    another one reaching further along `axis` within TIP_LANE_M along
    `side_axis` is dropped (knuckle bumps, second peaks along a finger); the
    four fingers are the remaining candidates reaching furthest (within
    FINGER_REACH_WINDOW_M of the furthest), the thumb the remaining one
    furthest along `side_axis`
    (T-pose hand, thumb forward). Each vertex joins the tip it is
    geodesically nearest: label 1..5 = thumb, index, middle, ring, pinky
    (fingers ordered thumb side first). A finger's web is the smallest
    own-tip distance on its region's border with another finger (meaningful
    on separated fingers; fused Human fingers border along their length).
    Returns per-row label (0 = unreached) and own-tip distance, and a report."""
    ids = weld(P)
    n = ids.max()+1
    pw = np.zeros((n, 3)); pw[ids] = P
    ff = ids[faces]
    rows = np.concatenate([ff[:, 0], ff[:, 1], ff[:, 2]])
    cols = np.concatenate([ff[:, 1], ff[:, 2], ff[:, 0]])
    graph = coo_matrix((np.linalg.norm(pw[rows]-pw[cols], axis=1), (rows, cols)), shape=(n, n)).tocsr()
    used = np.unique(ff)
    t = (pw[used]-wrist_point)@axis
    start = used[t < np.percentile(t, 1)]
    wd = dijkstra(graph, directed=False, indices=start, min_only=True)
    finite = np.isfinite(wd)
    best = np.full(n, -np.inf)
    np.maximum.at(best, cols, np.where(np.isfinite(wd[rows]), wd[rows], -np.inf))
    peak = used[finite[used] & (wd[used] > far_m) & (wd[used] >= best[used])]
    peak = peak[np.argsort(-wd[peak])]
    # merge peaks within TIP_MERGE_M along the surface (adjacent finger tips can
    # be closer than that in space, never along the surface)
    kept, covered = [], np.zeros(n, bool)
    for v in peak:
        if covered[v]:
            continue
        kept.append(v)
        covered |= np.isfinite(dijkstra(graph, directed=False, indices=int(v), limit=TIP_MERGE_M))
    kept = np.array(kept)
    reach = (pw[kept]-wrist_point)@axis
    lateral = (pw[kept]-wrist_point)@side_axis
    # a candidate behind another one in its lateral lane (a knuckle bump, a
    # second peak along a finger) is not a tip
    dominated = np.array([((reach > reach[i]) & (np.abs(lateral-lateral[i]) < TIP_LANE_M)).any()
                          for i in range(len(kept))])
    pool = np.flatnonzero(~dominated & (reach >= reach.max()-FINGER_REACH_WINDOW_M))
    if len(pool) < tips_wanted-1:
        raise ValueError(f'only {len(pool)} finger tips found')
    fingers = kept[pool[np.argsort(-reach[pool])[:tips_wanted-1]]]
    rest = np.setdiff1d(kept, fingers)
    if not len(rest):
        raise ValueError('no thumb tip found')
    thumb = rest[np.argmax((pw[rest]-wrist_point)@side_axis)]
    tips = np.concatenate([[thumb], fingers[np.argsort(-((pw[fingers]-wrist_point)@side_axis))]])
    td = np.vstack([dijkstra(graph, directed=False, indices=int(tip)) for tip in tips]).T
    near = np.argmin(td, 1)
    own = td[np.arange(n), near]
    border = (near[rows] != near[cols]) & finite[rows] & finite[cols]
    web = np.full(len(tips), np.inf)
    for k in range(len(tips)):
        mine = border & (near[rows] == k)
        if mine.any():
            web[k] = float(own[rows[mine]].min())
    label = np.where(finite, near+1, 0)
    return label[ids], own[ids], {'tips': [pw[v].tolist() for v in tips], 'tipWristGeodesicM': [float(wd[v]) for v in tips],
                                  'webFromTipM': [float(x) for x in web]}


def smooth_weights(P, faces, weights, passes=WEIGHT_SMOOTHING):
    """Per-row weight vectors averaged over welded 1-rings `passes` times
    (rows outside `faces` keep theirs)."""
    ids = weld(P)
    n = ids.max()+1
    ff = ids[faces]
    rows = np.concatenate([ff[:, 0], ff[:, 1], ff[:, 2], ff[:, 1], ff[:, 2], ff[:, 0]])
    cols = np.concatenate([ff[:, 1], ff[:, 2], ff[:, 0], ff[:, 0], ff[:, 1], ff[:, 2]])
    adj = coo_matrix((np.ones(len(rows)), (rows, cols)), shape=(n, n)).tocsr()
    adj.data[:] = 1
    deg = np.asarray(adj.sum(1)).ravel()
    used = np.unique(faces)
    w = np.zeros((n, weights.shape[1])); w[ids[used]] = weights[used]
    for _ in range(passes):
        w = np.where((deg > 0)[:, None], (adj@w+w)/(deg+1)[:, None], w)
    out = weights.copy()
    out[used] = w[ids[used]]
    return out


def finger_weight(own, label, cut, blend=FINGER_BLEND_M):
    """Finger-map weight: 1 within cut[label] of the own tip, smoothstep to 0
    at cut + blend; 0 for unlabelled rows."""
    c = np.asarray(cut, float)[np.maximum(label, 1)-1]
    u = np.clip((c+blend-np.asarray(own, float))/blend, 0, 1)
    return np.where(label > 0, u*u*(3-2*u), 0.)


# ---------------------------------------------------------------------------
# Alignment
# ---------------------------------------------------------------------------

def box_init(hp, hand_joint, src_points, src_hand_joint, axis_h, axis_s):
    """Per-axis scale from the hand joint (x along the arm), centre match."""
    def box(points, joint, axis):
        q = points[(points-joint)@axis > 0]
        return np.percentile(q, 1, 0), np.percentile(q, 99, 0)
    hlo, hhi = box(hp, hand_joint, axis_h)
    slo, shi = box(src_points, src_hand_joint, axis_s)
    if axis_h[0] > 0:
        sx = (shi[0]-src_hand_joint[0])/(hhi[0]-hand_joint[0])
    else:
        sx = (slo[0]-src_hand_joint[0])/(hlo[0]-hand_joint[0])
    syz = (shi[1:]-slo[1:])/(hhi[1:]-hlo[1:])
    A = np.diag([sx, syz[0], syz[1]])
    t = np.zeros(3)
    t[0] = src_hand_joint[0]-sx*hand_joint[0]
    t[1:] = (slo[1:]+shi[1:])/2-A[1:, 1:]@((hlo[1:]+hhi[1:])/2)
    return A, t


def icp_affine(x, tree, targets, A, t, iterations=ICP_ITERATIONS, trim=ICP_TRIM, back=None):
    """Trimmed affine ICP of points x onto target samples (KD-tree). With
    `back` (target points) correspondences also run target -> mapped x, which
    keeps a finger's length (tip to tip)."""
    for _ in range(iterations):
        m = x@A.T+t
        d, idx = tree.query(m)
        keep = d <= np.percentile(d, trim)
        X, Y = x[keep], targets[idx[keep]]
        if back is not None:
            d2, j2 = cKDTree(m).query(back)
            k2 = d2 <= np.percentile(d2, trim)
            X = np.vstack([X, x[j2[k2]]]); Y = np.vstack([Y, back[k2]])
        A, t = affine_fit(X, Y)
    return A, t


def face_values(faces, per_row_label, per_row_value, face_index, bary):
    """Label (largest barycentric corner) and the barycentric mix of the
    values of the corners sharing it, at points on faces."""
    f = faces[face_index]
    lab = per_row_label[f]
    pick = lab[np.arange(len(f)), bary.argmax(1)]
    same = lab == pick[:, None]
    w = bary*same
    val = (w*per_row_value[f]).sum(1)/np.maximum(w.sum(1), 1e-12)
    return pick, val


def blended_map(points, weights, maps):
    """Mapped points and blended linear parts (n,3,3): the sum over k of
    weights[:, k] times map k (0 palm, 1..5 fingers; rows sum to 1, weight
    of a finger without its own map goes to the palm map)."""
    lin = np.zeros((len(points), 3, 3))
    off = np.zeros((len(points), 3))
    for k in range(weights.shape[1]):
        Ak, tk = maps.get(k, maps[0])
        w = weights[:, k]
        lin += w[:, None, None]*Ak
        off += w[:, None]*tk
    return np.einsum('nij,nj->ni', lin, points)+off, lin


def align_side(body, faces, joints, side, src, src_faces, src_hand_joint, src_axis, per_finger=True):
    """Global affine + per-finger affines mapping the Human hand -> source.
    Returns maps {0: palm, 1..5: fingers}, per-row Human labels/weights,
    source samples (+ tree) and a report."""
    p = np.asarray(body['POSITION'], float)
    rows = np.unique(faces)
    hp = p[rows]
    hand = joints[f'hand_{side}']
    axis_h = hand-joints[f'lowerarm_{side}']
    axis_h /= np.linalg.norm(axis_h)
    samples = surface_samples(src['P'], src_faces, normals=src['N'], uv=src['UV'])
    tree = cKDTree(samples['P'])
    fit = (hp-hand)@axis_h > ICP_FROM_M
    A0, t0 = box_init(hp, hand, samples['P'], src_hand_joint, axis_h, src_axis)
    A, t = icp_affine(hp[fit], tree, samples['P'], A0, t0)
    maps = {0: (A, t)}
    info = {'box': {'A': A0.tolist(), 't': t0.tolist()},
            'globalAffine': {'A': A.tolist(), 't': t.tolist(), 'singular': np.linalg.svd(A, compute_uv=False).tolist()}}
    label = np.zeros(len(p), int)
    weight = np.zeros(len(p))
    weights = np.zeros((len(p), 6)); weights[:, 0] = 1
    if per_finger:
        forward = np.array([0., 0., 1.])     # thumbs point +z (forward) in the T-pose
        h_label, h_own, h_info = geodesic_fingers(p, faces, hand-axis_h*.05, axis_h, forward)
        s_label, s_own, s_info = geodesic_fingers(src['P'], src_faces, src_hand_joint-src_axis*.04, src_axis, forward)
        # The free finger is what the (separated) source fingers show: its web
        # distance, carried to the Human by the palm map's scale along the arm.
        along = float(np.linalg.norm(A@axis_h))
        cut_s = np.array(s_info['webFromTipM'])
        cut_h = cut_s/along
        label[rows] = h_label[rows]
        weight[rows] = finger_weight(h_own[rows], h_label[rows], cut_h)
        weights[rows, 0] = 1-weight[rows]
        weights[rows, label[rows]] += weight[rows]
        weights = smooth_weights(p, faces, weights)
        third = np.full((len(src_faces), 3), 1/3)
        sf_lab, sf_own = face_values(src_faces, s_label, s_own, np.arange(len(src_faces)), third)
        smp_lab = sf_lab[samples['face']]
        smp_own = sf_own[samples['face']]
        info.update(humanFingers=h_info, sourceFingers=s_info, cutHumanM=cut_h.tolist(), alongScale=along, fingerSamples={})
        for k, finger in enumerate(FINGERS, 1):
            sel = (label[rows] == k) & (weight[rows] > .5) & fit
            pts = samples['P'][(smp_lab == k) & (smp_own < cut_s[k-1]+.5*FINGER_BLEND_M*along)]
            info['fingerSamples'][finger] = {'human': int(sel.sum()), 'source': int(len(pts))}
            if sel.sum() < 12 or len(pts) < 50:
                continue
            Ak, tk = icp_affine(hp[sel], cKDTree(pts), pts, A.copy(), t.copy(), FINGER_ITERATIONS, back=pts)
            maps[k] = (Ak, tk)
        info['fingerAffines'] = {f: {'A': maps[k][0].tolist(), 't': maps[k][1].tolist(),
                                     'singular': np.linalg.svd(maps[k][0], compute_uv=False).tolist()}
                                 for k, f in enumerate(FINGERS, 1) if k in maps}
    return maps, label, weights, samples, tree, info


def refine(P, faces, rows, mapped, mapped_normals, samples, tree, schedule=REFINE_SCHEDULE, step=REFINE_STEP,
           reject=REFINE_REJECT_M):
    """Smooth non-rigid refinement of the mapped Human hand rows: a
    displacement per row (added to the affine map), pulled towards the
    normal-gated nearest source samples and smoothed over the Human mesh,
    coarse to fine (`schedule`: smoothing passes per iteration)."""
    disp = np.zeros((len(P), 3))
    for passes in schedule:
        m = mapped+disp[rows]
        pick, dist, ok = gated_lookup(m, mapped_normals, samples, tree)
        pull = samples['P'][pick]-m
        valid = ok & (dist < reject)
        field = np.zeros((len(P), 4))
        field[rows, :3] = np.where(valid[:, None], pull, 0.)
        field[rows, 3] = valid
        field = smooth_weights(P, faces, field, passes)
        disp[rows] += step*field[rows, :3]/np.maximum(field[rows, 3:], 1e-3)
    return disp


def gated_lookup(mapped, mapped_normals, samples, tree, k=LOOKUP_K, gate=NORMAL_GATE):
    """Index of the nearest source sample whose normal agrees (dot > gate);
    falls back to the nearest sample. Returns index, distance, gated flag."""
    d, idx = tree.query(mapped, k=k)
    dots = np.einsum('nkj,nj->nk', samples['N'][idx], mapped_normals)
    ok = dots > gate
    first = np.where(ok.any(1), ok.argmax(1), 0)
    pick = idx[np.arange(len(idx)), first]
    return pick, d[np.arange(len(idx)), first], ok.any(1)


def _mapped_normals(lin, normals):
    n = np.einsum('nij,nj->ni', np.linalg.inv(lin).transpose(0, 2, 1), normals)
    return n/np.maximum(np.linalg.norm(n, axis=1, keepdims=True), 1e-12)


# ---------------------------------------------------------------------------
# Projection
# ---------------------------------------------------------------------------

def race_of(slug):
    return slug.rsplit('_', 1)[0]


def project_hands(slug, body, joints, skin_pixels, target, src, occupied=None, sides=('l', 'r'),
                  per_finger=None, gate_mm=None, force_tone=False, fallback=True, refine_steps=True):
    """Projected hand texels for the body skin atlas.

    body:        {'POSITION','NORMAL','TEXCOORD_0': rows, 'faces': shared_body skin faces}
    joints:      {name: rest world position} (77-joint rig)
    skin_pixels: (H,W,3) sRGB 0-1, the recoloured skin atlas (recolour_skin output)
    target:      face reference sRGB 0-1 (face_reference)
    src:         load_source(...) of the race's Meshy tpose + rigged donor
    occupied:    (H,W) bool, texels any face of this atlas covers (gutter guard);
                 default: the body faces' own coverage
    fallback:    a side missing the residual gate goes tone-only (False keeps
                 the projection, for review)
    Returns {'y','x','rgb','weight','mode','report'}; rgb is the projected
    (or tone-only) colour, weight the wrist blend (1 on the hand)."""
    race = race_of(slug)
    per_finger = PER_FINGER.get(race, True) if per_finger is None else per_finger
    gate = GATE_P90_MM.get(race, 5.) if gate_mm is None else gate_mm
    p = np.asarray(body['POSITION'], float)
    nrm = np.asarray(body['NORMAL'], float)
    uv = np.asarray(body['TEXCOORD_0'], float)
    size = skin_pixels.shape[1::-1]
    if occupied is None:
        occupied = occupancy([(uv, np.asarray(body['faces'], int))], size)
    target_l = srgb_to_linear(np.asarray(target, float))
    debug = {}
    sides_out, report = [], {'slug': slug, 'gateP90Mm': gate, 'normalGate': NORMAL_GATE, 'perFinger': per_finger,
                             'sides': {}}
    for side in sides:
        faces, hand, axis = human_hand(body, joints, side)
        rows = np.unique(faces)
        sf, s_hand, s_axis, cuff = source_hand(src, side)
        maps, label, wmat, samples, tree, info = align_side(body, faces, joints, side, src, sf, s_hand, s_axis,
                                                            per_finger)
        info['sourceCuff'] = cuff
        mapped, lin = blended_map(p[rows], wmat[rows], maps)
        affine_resid = closest_distance(mapped, src['P'], sf)
        mnormals = _mapped_normals(lin, nrm[rows])
        disp = refine(p, faces, rows, mapped, mnormals, samples, tree) if refine_steps else np.zeros((len(p), 3))
        mapped = mapped+disp[rows]
        resid = closest_distance(mapped, src['P'], sf)
        on_hand = (p[rows]-hand)@axis >= 0
        group = np.where(wmat[rows, label[rows]] >= .5, label[rows], 0) if per_finger else np.zeros(len(rows), int)
        fingers = {}
        for k, name in enumerate(('palm',)+FINGERS):
            sel = (group == k) & on_hand
            if sel.any():
                fingers[name] = {'vertices': int(sel.sum()), 'p50Mm': float(np.median(resid[sel])*1000),
                                 'p90Mm': float(np.percentile(resid[sel], 90)*1000),
                                 'p99Mm': float(np.percentile(resid[sel], 99)*1000),
                                 'affineP90Mm': float(np.percentile(affine_resid[sel], 90)*1000)}
        finger_ok = all(v['p90Mm'] <= gate for v in fingers.values())
        _, _, gated_v = gated_lookup(mapped, mnormals, samples, tree)
        # texels: centre points on the hand faces
        face_i, ty, tx, bary = raster(uv, faces, size)
        tp = np.einsum('ni,nij->nj', bary, p[faces[face_i]])
        tn = np.einsum('ni,nij->nj', bary, nrm[faces[face_i]])
        tn /= np.maximum(np.linalg.norm(tn, axis=1, keepdims=True), 1e-12)
        twm = np.einsum('ni,nik->nk', bary, wmat[faces[face_i]])
        tm, tlin = blended_map(tp, twm, maps)
        tm = tm+np.einsum('ni,nij->nj', bary, disp[faces[face_i]])
        pick, dist, gated = gated_lookup(tm, _mapped_normals(tlin, tn), samples, tree)
        colour = bilinear(src['pixels'], samples['UV'][pick])
        travel = (tp-joints[f'lowerarm_{side}'])@axis
        start = float(((p[rows]-joints[f'lowerarm_{side}'])@axis).min())
        end = float((hand-joints[f'lowerarm_{side}'])@axis)
        u = np.clip((travel-start)/max(end-start, 1e-6), 0, 1)
        weight = u*u*(3-2*u)
        lin_c = srgb_to_linear(colour)
        full = weight > .999
        bright = (lin_c@LUMA) > BRIGHT_LIMIT*np.median(lin_c[full]@LUMA)
        lin_c, unfilled = refill(ty, tx, lin_c, bright, size)
        median_l = float(np.median(lin_c[full]@LUMA))
        gain = float(target_l@LUMA/median_l)
        projected = lin_c*gain
        base = skin_pixels[ty, tx]
        mode = 'projected'
        if force_tone or (fallback and not finger_ok):
            mode = 'tone-only'
            src_med = np.median(projected[full], axis=0)
            base_med = np.median(srgb_to_linear(base[full]), axis=0)
            projected = srgb_to_linear(base)*(src_med/np.maximum(base_med, 1e-6))
        rgb = linear_to_srgb(projected)
        sides_out.append((ty, tx, rgb, weight))
        debug[side] = {'rows': rows, 'residual': resid, 'affineResidual': affine_resid, 'group': group, 'mapped': mapped}
        med = np.median(projected[full], axis=0)
        report['sides'][side] = {
            'mode': mode, 'humanHandVertices': int(len(rows)), 'sourceHandFaces': int(len(sf)),
            'texels': int(len(ty)), 'fullWeightTexels': int(full.sum()),
            'wristBand': {'startM': start, 'endM': end, 'along': f'lowerarm_{side} -> hand_{side}'},
            'residualMm': {'all': {'p50': float(np.median(resid[on_hand])*1000), 'p90': float(np.percentile(resid[on_hand], 90)*1000),
                                   'p99': float(np.percentile(resid[on_hand], 99)*1000)}, **fingers},
            'gatePassed': bool(finger_ok),
            'brightRefill': {'limit': BRIGHT_LIMIT, 'texels': int(bright.sum()), 'unfilled': unfilled},
            'refinement': {'schedule': list(REFINE_SCHEDULE) if refine_steps else [], 'step': REFINE_STEP,
                           'rejectM': REFINE_REJECT_M,
                           'displacementMm': {'p50': float(np.median(np.linalg.norm(disp[rows], axis=1))*1000),
                                              'p90OnHand': float(np.percentile(np.linalg.norm(disp[rows][on_hand], axis=1), 90)*1000),
                                              'max': float(np.linalg.norm(disp[rows], axis=1).max()*1000),
                                              'maxOnHand': float(np.linalg.norm(disp[rows][on_hand], axis=1).max()*1000)}},
            'opposedVertexFraction': float(1-gated_v.mean()), 'opposedTexelFraction': float(1-gated.mean()),
            'lookupDistanceMm': {'p50': float(np.median(dist)*1000), 'p90': float(np.percentile(dist, 90)*1000)},
            'luminanceGain': gain, 'sourceMedianLuminance': median_l, 'targetLuminance': float(target_l@LUMA),
            'medianLinearRGB': med.tolist(), 'targetLinearRGB': target_l.tolist(),
            'chromaDelta': (med/max(med@LUMA, 1e-9)-target_l/max(target_l@LUMA, 1e-9)).tolist(),
            'alignment': info}
    y = np.concatenate([s[0] for s in sides_out]); x = np.concatenate([s[1] for s in sides_out])
    rgb = np.concatenate([s[2] for s in sides_out]); w = np.concatenate([s[3] for s in sides_out])
    # one value per texel (the two hands never share texels; keep the larger weight if they do)
    order = np.lexsort((-w, y*size[0]+x))
    key = (y*size[0]+x)[order]
    first = np.r_[True, key[1:] != key[:-1]]
    y, x, rgb, w = y[order][first], x[order][first], rgb[order][first], w[order][first]
    gy, gx, grgb, gw = gutter(y, x, rgb, w, occupied, size)
    report['gutterTexels'] = int(len(gy))
    modes = {s['mode'] for s in report['sides'].values()}
    report['mode'] = modes.pop() if len(modes) == 1 else 'mixed'
    report['rule'] = {'residual': 'mapped Human hand vertex (past the hand joint) -> source hand skin surface (exact), '
                                  'p90 per finger (its finger weight >= .5) and palm, after the smooth non-rigid '
                                  'refinement (affineP90Mm: before it)',
                      'lookup': f'nearest source sample (about 0.5 mm spacing) with normal dot > {NORMAL_GATE}',
                      'luminance': 'one linear gain: hand texel-median luminance -> face reference luminance',
                      'wrist': 'smoothstep from the first hand-face vertex to the hand joint along lowerarm->hand'}
    return {'y': np.concatenate([y, gy]), 'x': np.concatenate([x, gx]), 'rgb': np.concatenate([rgb, grgb]),
            'weight': np.concatenate([w, gw]), 'mode': report['mode'], 'report': report, 'debug': debug,
            'handTexels': int(len(y))}


def refill(y, x, rgb, bad, size, steps=32):
    """Replace `bad` texels of a texel set (y, x) by the 3x3 mean of good
    neighbours, growing inwards; texels never reached keep their colour."""
    if not bad.any():
        return rgb, 0
    h, wd = size[1], size[0]
    lo = np.maximum([y.min()-1, x.min()-1], 0)
    hi = np.minimum([y.max()+2, x.max()+2], [h, wd])
    shape = (hi[0]-lo[0], hi[1]-lo[1])
    canvas = np.zeros(shape+(3,)); valid = np.zeros(shape, bool); todo = np.zeros(shape, bool)
    yy, xx = y-lo[0], x-lo[1]
    canvas[yy, xx] = rgb
    valid[yy[~bad], xx[~bad]] = True
    todo[yy[bad], xx[bad]] = True
    kernel = np.ones((3, 3))
    for _ in range(steps):
        count = convolve(valid.astype(float), kernel, mode='constant')
        new = (count > 0) & todo & ~valid
        if not new.any():
            break
        for ch in range(3):
            total = convolve(np.where(valid, canvas[..., ch], 0.), kernel, mode='constant')
            canvas[..., ch][new] = total[new]/count[new]
        valid |= new
    out = rgb.copy()
    out[bad] = canvas[yy[bad], xx[bad]]
    return out, int((~valid[yy[bad], xx[bad]]).sum())


def gutter(y, x, rgb, w, occupied, size, steps=GUTTER_PX):
    """Push hand texel colours into uncovered neighbour texels (3x3 mean)."""
    h, wd = size[1], size[0]
    canvas = np.zeros((h, wd, 3)); weight = np.zeros((h, wd)); valid = np.zeros((h, wd), bool)
    canvas[y, x] = rgb; weight[y, x] = w; valid[y, x] = True
    free = ~occupied
    kernel = np.ones((3, 3))
    added = np.zeros((h, wd), bool)
    lo = np.maximum([y.min()-steps-1, x.min()-steps-1], 0)
    hi = np.minimum([y.max()+steps+2, x.max()+steps+2], [h, wd])
    sl = (slice(lo[0], hi[0]), slice(lo[1], hi[1]))
    c, wt, v, fr, ad = canvas[sl], weight[sl], valid[sl], free[sl], added[sl]
    for _ in range(steps):
        count = convolve(v.astype(float), kernel, mode='constant')
        new = (count > 0) & ~v & fr
        if not new.any():
            break
        for ch in range(3):
            total = convolve(np.where(v, c[..., ch], 0.), kernel, mode='constant')
            c[..., ch][new] = total[new]/count[new]
        tw = convolve(np.where(v, wt, 0.), kernel, mode='constant')
        wt[new] = tw[new]/count[new]
        v |= new
        ad |= new
    gy, gx = np.nonzero(ad)
    return gy+lo[0], gx+lo[1], c[gy, gx], wt[gy, gx]


def apply_hand_texels(image, result):
    """A copy of `image` (sRGB 0-1) with the hand texels blended in."""
    out = np.array(image, float, copy=True)
    w = result['weight'][:, None]
    out[result['y'], result['x']] = (1-w)*out[result['y'], result['x']]+w*result['rgb']
    return out


# ---------------------------------------------------------------------------
# Installed-body glue (check)
# ---------------------------------------------------------------------------

def body_skin(d, b):
    """shared_body skin primitive arrays, its image (sRGB 0-1) and index,
    joints, and the occupancy of every primitive textured by that image."""
    skin_ = d['skins'][0]
    names = [d['nodes'][j]['name'] for j in skin_['joints']]
    ibm = ea.accessor_array(d, b, skin_['inverseBindMatrices']).astype(float).reshape(-1, 4, 4).transpose(0, 2, 1)
    joints = {n: np.linalg.inv(m)[:3, 3] for n, m in zip(names, ibm)}
    mesh = next(m for m in d['meshes'] if m['name'] == 'body')
    prim = next(p for p in mesh['primitives'] if p.get('extras', {}).get('sourceRole') == 'shared_body')
    a = prim['attributes']
    body = {k: ea.accessor_array(d, b, a[k]).astype(float) for k in ('POSITION', 'NORMAL', 'TEXCOORD_0')}
    body['faces'] = ea.accessor_array(d, b, prim['indices']).astype(int).reshape(-1, 3)
    mat = d['materials'][prim['material']]
    index = d['textures'][mat['pbrMetallicRoughness']['baseColorTexture']['index']]['source']
    view = d['bufferViews'][d['images'][index]['bufferView']]
    payload = bytes(b[view.get('byteOffset', 0):view.get('byteOffset', 0)+view['byteLength']])
    pixels = np.asarray(Image.open(io.BytesIO(payload)).convert('RGB')).astype(float)/255
    users = []
    for m in d['meshes']:
        for q in m['primitives']:
            qm = d['materials'][q['material']]
            tex = qm.get('pbrMetallicRoughness', {}).get('baseColorTexture', {}).get('index')
            if tex is not None and d['textures'][tex]['source'] == index:
                users.append((ea.accessor_array(d, b, q['attributes']['TEXCOORD_0']).astype(float),
                              ea.accessor_array(d, b, q['indices']).astype(int).reshape(-1, 3)))
    return body, pixels, index, joints, users


def v22_gate(root, slug, candidate, head=None):
    """V22 on a built candidate GLB: (ok, values). The projection is redone
    on the candidate (deterministic: seeded samples, the candidate's own skin
    primitive, joints and face reference sharedBodyShape.skinRecolour.targetRGB).

    projected mode: both sides pass the residual gate (GATE_P90_MM per finger
    and palm), opposed-normal texel hits <= OPPOSED_MAX, and the candidate's
    full-weight hand texels equal the redone projection within
    TEXEL_TOLERANCE (mean absolute sRGB levels; JPEG noise); the mode equals
    the one the build recorded (sharedBodyShape.hands.mode) when recorded.
    tone-only mode (a side missed the gate at build time): reported, passes
    when the redone projection also misses it (the build's choice holds)."""
    d, b = ea.read_glb(Path(candidate))
    if slug not in RACES:
        return True, {'skipped': f'{slug} has no hand projection (decision 7)'}
    body, pixels, index, joints, users = body_skin(d, b)
    shape = d['asset'].get('extras', {}).get('sharedBodyShape', {})
    target = np.asarray(shape['skinRecolour']['targetRGB'], float)
    tpose, rigged = source_paths(root, slug)
    src = load_source(tpose, rigged)
    result = project_hands(slug, body, joints, pixels, target, src, occupancy(users, pixels.shape[1::-1]))
    rep_ = result['report']
    recorded = (shape.get('hands') or {}).get('mode')
    values = {'mode': rep_['mode'], 'recordedMode': recorded, 'source': [Path(tpose).name, Path(rigged).name],
              'gateP90Mm': rep_['gateP90Mm'], 'opposedMax': OPPOSED_MAX, 'texelToleranceLevels': TEXEL_TOLERANCE,
              'sides': {}}
    ok = recorded is None or recorded == rep_['mode']
    hand = slice(0, result['handTexels'])     # hand texels come before the gutter texels
    full = result['weight'][hand] > .999
    diff = np.abs(pixels[result['y'][hand], result['x'][hand]]-result['rgb'][hand])[full].mean()*255
    values['texelMeanAbsLevels'] = float(diff)
    for side, v in rep_['sides'].items():
        values['sides'][side] = {'mode': v['mode'], 'gatePassed': v['gatePassed'],
                                 'residualP90Mm': {k: x.get('p90Mm', x.get('p90')) for k, x in v['residualMm'].items()},
                                 'affineP90Mm': {k: x['affineP90Mm'] for k, x in v['residualMm'].items() if 'affineP90Mm' in x},
                                 'opposedTexelFraction': v['opposedTexelFraction'], 'luminanceGain': v['luminanceGain']}
        if v['mode'] == 'projected':
            ok &= v['gatePassed'] and v['opposedTexelFraction'] <= OPPOSED_MAX
    if rep_['mode'] == 'projected':
        ok &= diff <= TEXEL_TOLERANCE
    return bool(ok), values


def check(root, slug, out=None, force_tone=False):
    root = Path(root)
    path = root/'godot-client/assets/actors/native/races'/f'{slug}.glb'
    d, b = ea.read_glb(path)
    body, pixels, index, joints, users = body_skin(d, b)
    target = np.asarray(d['asset']['extras']['sharedBodyShape']['skinRecolour']['targetRGB'], float)
    tpose, rigged = source_paths(root, slug)
    src = load_source(tpose, rigged)
    occupied = occupancy(users, pixels.shape[1::-1])
    result = project_hands(slug, body, joints, pixels, target, src, occupied, force_tone=force_tone)
    image = apply_hand_texels(pixels, result)
    if out:
        out = Path(out).resolve()
        if 'godot-client' in out.parts:
            raise ValueError('write outside godot-client')
        out.mkdir(parents=True, exist_ok=True)
        Image.fromarray(np.clip(np.rint(image*255), 0, 255).astype('u1')).save(out/f'{slug}_skin.png')
        (out/f'{slug}_hands.json').write_text(json.dumps(result['report'], indent=2, default=float)+'\n', encoding='utf-8')
    return result, image, {'imageIndex': index, 'source': [str(tpose), str(rigged)]}


def main():
    ap = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    sub = ap.add_subparsers(dest='cmd', required=True)
    c = sub.add_parser('check')
    c.add_argument('--root', required=True)
    c.add_argument('--slug', required=True, choices=RACES)
    c.add_argument('--out')
    c.add_argument('--tone-only', action='store_true')
    args = ap.parse_args()
    result, _, _ = check(args.root, args.slug, args.out, args.tone_only)
    rep = result['report']
    print(json.dumps({'mode': rep['mode'], 'sides': {s: {k: v[k] for k in ('mode', 'residualMm', 'gatePassed', 'opposedTexelFraction',
                                                                         'luminanceGain', 'chromaDelta')}
                                                    for s, v in rep['sides'].items()}}, indent=1, default=float))


if __name__ == '__main__':
    main()
