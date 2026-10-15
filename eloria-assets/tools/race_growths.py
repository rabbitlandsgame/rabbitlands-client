"""Mycelari shoulder growths: the race_feature_shoulders node (P4 decision 8).

    python eloria-assets/tools/race_growths.py prepare --sex male [--out <dir>] [--blender <exe>]
    python eloria-assets/tools/race_growths.py place --body <race glb> --out <glb> [--growth <glb>]
    python eloria-assets/tools/race_growths.py check --candidate <glb> [--out <json>] [--clips A B ...]

prepare: the mushroom caps on the shoulders of the 2048 Meshy source
(generate_models/eloria-races-meshy/mycelari_<sex>_tpose.glb, scaled into the
mesh frame of its _rigged donor as the P4 feature map measured them) are
segmented by colour inside SEGMENT_BOX: faces brighter than SEED_LUMINANCE
seed, faces brighter than GROW_LUMINANCE grow them over welded edges. Each
side keeps its largest bright piece (mycelari_male also has a hidden inner
shell ~3 mm inside the outer one: dropped), opened by OPEN_RADIUS to trim the
ragged colour fringe at the base, with enclosed dark patches filled, so its
one open boundary is the base ring. Blender 5.2.1 (race_growths_blender.py)
thins that ring, collapse-decimates each side to TARGET_TRIANGLES and
smart-UV-projects/packs both sides into one square; the BAKE_SIZE image is
baked here from the source texture (nearest source sample whose normal agrees).
Output <out>/mycelari_<sex>.glb (default work-output/race-rebase/p47/growths):
an unskinned GLB in the donor frame, one node race_feature_shoulders, one
primitive, material 'Race feature growth', asset.extras.raceGrowths
(provenance, donor joints, counts). Deterministic; it embeds this file's
toolSHA256, so re-run prepare after editing this file.

place_growths() (called by rebase_race_body.py build on the assembled body)
and append_growths(): each side moves by joint translation (port of the P4
map's growthplace.py): the ring centre keeps its offset from the donor
LeftArm/RightArm joint, the x offset scaled by |upperarm.x| / |Arm.x|; the
shape is not scaled. A point-to-plane fit in the body's y-z plane only (x
stays where the joint translation put it) seats the ring SNAP_INSET inside
wardrobe_shirt, then the residual is closed exactly with a displacement that
fades out over SNAP_FALLOFF of geodesic distance from the ring. Weights
(cap_mode 'surface', R2): every growth vertex takes the shirt weights at its
closest shirt point, then WEIGHT_SMOOTH_PASSES uniform-Laplacian passes over
the welded growth edges smooth them with the base ring pinned: the stalk
follows the shoulder it stands on and the cap the shirt it overhangs, so it
rides the shoulder instead of swinging on one blend. R1's 'mean' (ring
weights blending by WEIGHT_FEATHER to their mean: about .4 upper arm, .4
spine_03, .2 clavicle) sank the cap 16-27 mm (female) and 40 mm (male) into
the shoulder in Sword_Regular_A/B, the melee attacks; a sweep of rigid cap
blends over the spine_03/clavicle/upper-arm simplex left at least 20 mm in
some clip (less arm: the deltoid rises into the cap; more: the cap sinks into
the chest); 32 passes was the best of 8-48 on both bodies (r2/gr sweeps).
'mean' and 'torso' (the spine/clavicle/neck share of that mean) stay for
comparison. The node is appended after every existing node under the body
node's parent, skinned with skin 0 (joint order and inverse binds
untouched), sourceRole 'race_feature', its own sampler/texture/image. It is
never dyed: replicated_actor_3d.gd has no appearance branch for
race_feature_* names.

growth_checks() / gate() (V21): base gap (ring outside the shirt; the ring is
inset by design, reported as baseInsetMm), rest penetration of the free
growth into the shirt, triangles per side, weight sums, and per library clip
the player action map reaches (combat clips through their recipe source
clips), skinned like the client (library local TRS copied by bone name, with
boneAliases, over the body's rest locals): growth sinking under the posed
shirt (normal-probed, confirmed by the shirt's winding number), shirt poking
into the closed growth (winding number), head inside the growth, max edge
stretch, cap tilt against spine_03 and arm elevation. Crossings within
CHECK_BASE_BAND of the ring are the base seating (base*Mm, not gated);
above it, arm* counts shirt that is mostly upper/lower-arm weighted. Depths
are probed to CHECK_PROBE (6 cm; R1's 2 cm reported its own ceiling, 20 mm).
gate() fails on any contact (growth sinking under the shirt, shirt poking
into the growth, arm or torso, the head inside it) deeper than clipDepthMm in
any clip, or deeper than the waived depth of a clip the owner waived (R1
gated only upper-arm contact, and only in clips raising the upper arm over
ARM_RAISE_DEG; armRaise stays in the report).

Hash inputs (V16): growth_input_digests() - this file and
race_growths_blender.py LF-folded, the growth GLB as bytes.
"""
from __future__ import annotations

import argparse
import hashlib
import io
import json
from pathlib import Path
import shutil
import subprocess
import tempfile

import numpy as np
from PIL import Image
from scipy.sparse import coo_matrix, csr_matrix
from scipy.sparse.csgraph import connected_components
from scipy.spatial import cKDTree

import equipment_authoring as ea
import shared_player_bodies as spb
import verify_shared_player_bodies as vspb
g = spb.g

TOOLS = Path(__file__).resolve().parent
BLENDER_SCRIPT = TOOLS/'race_growths_blender.py'
BLENDER = Path(r'C:\Program Files\Blender Foundation\Blender 5.2\blender.exe')
BLENDER_VERSION = '5.2.1'
NODE = 'race_feature_shoulders'
MATERIAL = 'Race feature growth'
ROLE = 'race_feature'
SLUGS = ('mycelari_male', 'mycelari_female')
LUMA = np.array([.2126, .7152, .0722])
# Segmentation (sRGB 0-255 luminance of the face colour; donor-frame metres).
SEED_LUMINANCE, GROW_LUMINANCE = 120., 85.
SEGMENT_BOX = {'y': (1.15, 1.50), 'absX': (.06, .40)}
SEED_BOX = {'absX': .10, 'yMin': 1.33}
GROW_BOX = {'absX': .085, 'yMax': 1.47}
# Opening radius (metres, in face rings of the median edge) that trims the
# ragged colour fringe and thin flaps at the base.
OPEN_RADIUS = .008
WELD_TOLERANCE = 1e-5
TARGET_TRIANGLES = 1300
TRIANGLE_RANGE = (1000, 1500)
BAKE_SIZE = 512
BAKE_SAMPLES_PER_M2 = 1.2e7
BAKE_NORMAL_DOT = .3
BAKE_GUTTER = 6
UV_BORDER = 3
JPEG_QUALITY = 92
DONOR_JOINTS = ('Hips', 'Spine02', 'Spine01', 'Spine', 'neck', 'Head', 'LeftShoulder', 'LeftArm', 'LeftForeArm',
                'RightShoulder', 'RightArm', 'RightForeArm')
SIDES = (('left', 1., 'LeftArm', 'upperarm_l'), ('right', -1., 'RightArm', 'upperarm_r'))
KEYS = ('POSITION', 'NORMAL', 'TEXCOORD_0', 'JOINTS_0', 'WEIGHTS_0')
# Placement.
SNAP_INSET = .001
SNAP_FALLOFF = .02
SNAP_ITERATIONS = 12
SEAT_DAMPING = 1e-4
WEIGHT_FEATHER = .03
TORSO_JOINTS = ('spine_01', 'spine_02', 'spine_03', 'clavicle_l', 'clavicle_r', 'neck_01')
CAP_MODES = ('surface', 'mean', 'torso')
# cap_mode 'surface': uniform-Laplacian smoothing passes over the projected
# shirt weights (base ring pinned).
WEIGHT_SMOOTH_PASSES = 32
# Checks (V21).
GATES = {'baseGapMedianMm': 1., 'baseGapMaxMm': 3., 'restPenetrationMm': 2., 'trianglesPerSide': 2000,
         'weightSumError': 1e-4, 'clipDepthMm': 2.}
CHECK_FPS = 15.
ARM_RAISE_DEG = 30.
CHECK_RING_BAND = .005
CHECK_PROBE = .06
CHECK_SLACK = .0005
# Crossings within this geodesic height of the base ring are the base seating
# itself (reported apart as baseSinkMm/basePokeMm, not gated).
CHECK_BASE_BAND = .015


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def source_digest(path):
    """SHA-256 with CRLF folded to LF (the git blob of a text source)."""
    return hashlib.sha256(Path(path).read_bytes().replace(b'\r\n', b'\n')).hexdigest()


def project_dir(root=None):
    """eloria-project, from a worktree root (work-output/<wt>) or this file."""
    here = Path(root).resolve() if root else TOOLS.parent.parent
    for p in (here, *here.parents):
        if (p/'generate_models').is_dir():
            return p
    raise FileNotFoundError('no eloria-project folder (with generate_models/) above '+str(here))


def default_growth(slug, root=None):
    return project_dir(root)/'work-output/race-rebase/p47/growths'/f'{slug}.glb'


def growth_inputs(slug, growth=None, root=None):
    """Files a body build with growths depends on (hash them into V16)."""
    return {'growthTool': TOOLS/'race_growths.py', 'growthBlender': BLENDER_SCRIPT,
            'growth': Path(growth) if growth else default_growth(slug, root)}


def growth_input_digests(slug, growth=None, root=None):
    """growth_inputs() hashed: the two scripts LF-folded, the GLB as bytes."""
    return {k: (digest if k == 'growth' else source_digest)(v) for k, v in growth_inputs(slug, growth, root).items()}


# ---------------------------------------------------------------------------
# prepare
# ---------------------------------------------------------------------------

def weld_ids(p, tol=WELD_TOLERANCE):
    _, inverse = np.unique(np.round(p/tol).astype(np.int64), axis=0, return_inverse=True)
    return inverse.ravel()


def edge_table(faces):
    """Sorted edge keys per face corner: (key, face) pairs of a welded mesh."""
    e = np.concatenate([faces[:, [0, 1]], faces[:, [1, 2]], faces[:, [2, 0]]])
    e.sort(1)
    n = int(faces.max())+1
    return e[:, 0].astype(np.int64)*n+e[:, 1], np.tile(np.arange(len(faces)), 3), e


def face_adjacency(faces):
    key, fid, _ = edge_table(faces)
    o = np.argsort(key, kind='stable'); key, fid = key[o], fid[o]
    same = key[1:] == key[:-1]
    a, b = fid[:-1][same], fid[1:][same]
    n = len(faces)
    return csr_matrix((np.ones(2*len(a)), (np.concatenate([a, b]), np.concatenate([b, a]))), shape=(n, n))


def grow(adjacency, seed, allowed):
    current = seed.copy()
    while True:
        nxt = current | ((adjacency@current.astype(float)) > 0) & allowed
        if (nxt == current).all():
            return current
        current = nxt


def components(adjacency, mask):
    idx = np.flatnonzero(mask)
    _, lab = connected_components(adjacency[idx][:, idx], directed=False)
    out = np.full(len(mask), -1); out[idx] = lab
    return out


def boundary_loops(faces):
    """Open-boundary components of a triangle mesh: vertex rows per component
    (edges used by one face, grouped by shared vertices), largest first."""
    key, _, e = edge_table(faces)
    _, inverse, count = np.unique(key, return_inverse=True, return_counts=True)
    edges = e[count[inverse.ravel()] == 1]
    if not len(edges):
        return []
    verts, local = np.unique(edges, return_inverse=True)
    local = local.reshape(-1, 2)
    n = len(verts)
    _, lab = connected_components(coo_matrix((np.ones(len(local)), (local[:, 0], local[:, 1])), shape=(n, n)),
                                  directed=False)
    return sorted((verts[lab == k] for k in range(lab.max()+1)), key=len, reverse=True)


def area3(p, faces):
    a = p[faces]
    return .5*np.linalg.norm(np.cross(a[:, 1]-a[:, 0], a[:, 2]-a[:, 0]), axis=1)


def face_normals(p, faces):
    n = np.cross(p[faces[:, 1]]-p[faces[:, 0]], p[faces[:, 2]]-p[faces[:, 0]])
    return n/np.maximum(np.linalg.norm(n, axis=1, keepdims=True), 1e-20)


def vertex_normals(p, faces, weld=None):
    """Area-weighted normals; rows sharing a welded position share a normal."""
    w = np.arange(len(p)) if weld is None else weld
    n = np.cross(p[faces[:, 1]]-p[faces[:, 0]], p[faces[:, 2]]-p[faces[:, 0]])
    acc = np.zeros((w.max()+1, 3))
    for k in range(3):
        np.add.at(acc, w[faces[:, k]], n)
    acc /= np.maximum(np.linalg.norm(acc, axis=1, keepdims=True), 1e-20)
    return acc[w]


def nearest_texel(pixels, uv):
    h, w = pixels.shape[:2]
    x = np.clip(np.floor((uv[:, 0] % 1)*w).astype(int), 0, w-1)
    y = np.clip(np.floor((uv[:, 1] % 1)*h).astype(int), 0, h-1)
    return pixels[y, x]


def donor_frame(slug, sources):
    """Donor joints (bind positions) and the Meshy source in the donor frame."""
    sex = slug.rsplit('_', 1)[1]
    donor_path = sources/f'mycelari_{sex}_tpose_rigged.glb'
    source_path = sources/f'mycelari_{sex}_tpose.glb'
    d, b = ea.read_glb(donor_path)
    names = [d['nodes'][j].get('name') for j in d['skins'][0]['joints']]
    ibm = ea.accessor_array(d, b, d['skins'][0]['inverseBindMatrices']).reshape(-1, 4, 4).transpose(0, 2, 1)
    joints = {n: np.linalg.inv(m)[:3, 3] for n, m in zip(names, ibm)}
    dv = ea.accessor_array(d, b, d['meshes'][0]['primitives'][0]['attributes']['POSITION']).astype(float)
    sd, sb = ea.read_glb(source_path)
    prim = sd['meshes'][0]['primitives'][0]
    p = ea.accessor_array(sd, sb, prim['attributes']['POSITION']).astype(float)
    uv = ea.accessor_array(sd, sb, prim['attributes']['TEXCOORD_0']).astype(float)
    faces = ea.accessor_array(sd, sb, prim['indices']).astype(int).reshape(-1, 3)
    image = sd['textures'][sd['materials'][prim['material']]['pbrMetallicRoughness']['baseColorTexture']['index']]['source']
    pixels = np.asarray(Image.open(io.BytesIO(spb.image_bytes(sd, sb, image))).convert('RGB')).astype(float)
    lo, hi, dlo, dhi = p.min(0), p.max(0), dv.min(0), dv.max(0)
    scale = (dhi[1]-dlo[1])/(hi[1]-lo[1])
    offset = (dlo+dhi)/2-scale*(lo+hi)/2
    return {'P': p*scale+offset, 'UV': uv, 'F': faces, 'pixels': pixels, 'joints': joints,
            'scale': float(scale), 'offset': offset.tolist(), 'source': source_path, 'donor': donor_path}


def segment(src):
    """Per side: the growth sub-mesh (welded) and its high-resolution faces."""
    p, faces, uv, pixels = src['P'], src['F'], src['UV'], src['pixels']
    c = p[faces].mean(1)
    box = ((c[:, 1] > SEGMENT_BOX['y'][0]) & (c[:, 1] < SEGMENT_BOX['y'][1])
           & (np.abs(c[:, 0]) > SEGMENT_BOX['absX'][0]) & (np.abs(c[:, 0]) < SEGMENT_BOX['absX'][1]))
    faces, c = faces[box], c[box]
    bary = np.array([[1/3, 1/3, 1/3], [.6, .2, .2], [.2, .6, .2], [.2, .2, .6]])
    colours = np.median(np.stack([nearest_texel(pixels, np.einsum('i,nij->nj', bb, uv[faces])) for bb in bary]), 0)
    lum = colours@LUMA
    used, local = np.unique(faces, return_inverse=True)
    local = local.reshape(-1, 3)
    w = weld_ids(p[used])
    wf = w[local]
    first = np.zeros(w.max()+1, int)
    first[w[::-1]] = np.arange(len(w))[::-1]
    pw = p[used][first]
    adjacency = face_adjacency(wf)
    seed = (lum > SEED_LUMINANCE) & (np.abs(c[:, 0]) > SEED_BOX['absX']) & (c[:, 1] > SEED_BOX['yMin'])
    allowed = (lum > GROW_LUMINANCE) & (np.abs(c[:, 0]) > GROW_BOX['absX']) & (c[:, 1] < GROW_BOX['yMax'])
    feature = grow(adjacency, seed, allowed)
    a = adjacency.tocoo()
    # Faces on an open edge of the cropped mesh (the box edge) are never enclosed.
    key, fid, _ = edge_table(wf)
    _, inverse, count = np.unique(key, return_inverse=True, return_counts=True)
    cut = np.zeros(len(wf), bool); cut[fid[count[inverse.ravel()] == 1]] = True
    sides, report = {}, {'segmentedTriangles': int(feature.sum()), 'regionTriangles': int(len(faces))}
    for side, sign, _, _ in SIDES:
        on_side = np.sign(c[:, 0]) == sign
        mask = feature & on_side
        lab = components(adjacency, mask)
        sizes = np.bincount(lab[mask])
        # The largest bright piece is the growth. mycelari_male also carries a
        # hidden inner shell about 3 mm inside it (a separate piece): dropped.
        keep = mask & (lab == np.argmax(sizes))
        largest = int(keep.sum())
        # Morphological opening over face rings trims the ragged colour
        # fringe (thin spikes running down onto the shirt) at the base.
        edges = wf[keep][:, [0, 1, 1, 2, 2, 0]].reshape(-1, 2)
        rings = max(1, int(round(OPEN_RADIUS/np.median(np.linalg.norm(pw[edges[:, 0]]-pw[edges[:, 1]], axis=1)))))
        core = keep.copy()
        for _ in range(rings):
            core &= ~((adjacency@(~core).astype(float)) > 0)
        for _ in range(rings):
            core |= ((adjacency@core.astype(float)) > 0) & keep
        clab = components(adjacency, core)
        keep = core & (clab == np.argmax(np.bincount(clab[core])))
        # Non-growth patches whose every neighbour is kept growth (pin holes,
        # dark spots on the cap) fill in; the patch holding the most faces is
        # the shirt and never does.
        other = on_side & ~keep
        olab = components(adjacency, other)
        osizes = np.bincount(olab[other])
        open_ = np.zeros(len(osizes), bool)
        leak = other[a.row] & ~keep[a.col] & ~other[a.col]
        open_[np.unique(olab[a.row[leak]])] = True
        open_[np.unique(olab[cut & other])] = True
        open_[np.argmax(osizes)] = True
        touches = np.zeros(len(osizes), bool)
        touches[np.unique(olab[a.col[keep[a.row] & other[a.col]]])] = True
        enclosed = np.flatnonzero(touches & ~open_)
        filled = keep | (other & np.isin(olab, enclosed))
        flab = components(adjacency, filled)
        if flab.max() != 0:
            raise ValueError(f'{side}: growth pieces do not join ({np.bincount(flab[filled]).tolist()})')
        sel = np.flatnonzero(filled)
        wverts, inverse = np.unique(wf[sel], return_inverse=True)
        sides[side] = {'P': pw[wverts], 'F': inverse.reshape(-1, 3).astype(np.int32),
                       'hiP': p, 'hiF': faces[sel], 'hiUV': uv}
        loops = boundary_loops(sides[side]['F'])
        report[side] = {'triangles': int(len(sel)), 'brightPieces': [int(v) for v in sorted(sizes, reverse=True)[:3]],
                        'droppedPieceTriangles': int(mask.sum()-largest), 'openRings': rings,
                        'openedTriangles': int(largest-keep.sum()),
                        'filledTriangles': int(filled.sum()-keep.sum()), 'filledPatches': int(len(enclosed)),
                        'boundaryLoops': [int(len(l)) for l in loops],
                        'areaCm2': round(float(area3(p, faces[sel]).sum()*1e4), 1)}
    return sides, report


def run_blender(sides, work, blender=None, target=TARGET_TRIANGLES):
    blender = Path(blender or BLENDER)
    source, result = work/'growth_in.npz', work/'growth_out.npz'
    np.savez(source, target=np.array(target), **{f'{s}_{k}': sides[s][k] for s in sides for k in ('P', 'F')})
    run = subprocess.run([str(blender), '--background', '--factory-startup', '--python', str(BLENDER_SCRIPT),
                          '--', str(source), str(result)], capture_output=True, text=True)
    log = run.stdout+run.stderr
    (work/'blender.log').write_text(log, encoding='utf-8')
    if run.returncode or 'GROWTH_BLENDER_OK' not in log:
        raise RuntimeError('Blender growth reduction failed; see '+str(work/'blender.log'))
    out = dict(np.load(result))
    version = str(out['blender'])
    if not version.startswith(BLENDER_VERSION):
        raise RuntimeError(f'Blender {version}; prepare is pinned to {BLENDER_VERSION}')
    return out, version


def split_corners(p, faces, uv):
    """One row per distinct (vertex, uv) corner pair."""
    corner_v = faces.ravel()
    corner_uv = uv.reshape(-1, 2)
    key = np.concatenate([corner_v[:, None].astype(np.float64), np.round(corner_uv.astype(np.float64)*1e6)], 1)
    _, first, inverse = np.unique(key, axis=0, return_index=True, return_inverse=True)
    return corner_v[first], corner_uv[first], inverse.reshape(-1, 3)


def raster(uv, faces, size):
    """Texel centres covered by each UV triangle: (ys, xs, face, barycentric)."""
    out = []
    t = uv[faces]*size
    for k, tri in enumerate(t):
        lo = np.floor(tri.min(0)-.5).astype(int); hi = np.ceil(tri.max(0)+.5).astype(int)
        xs, ys = np.meshgrid(np.arange(max(lo[0], 0), min(hi[0], size)), np.arange(max(lo[1], 0), min(hi[1], size)))
        if not xs.size:
            continue
        q = np.stack([xs.ravel()+.5, ys.ravel()+.5], 1)
        a, b, c = tri
        m = np.array([b-a, c-a]).T
        if abs(np.linalg.det(m)) < 1e-12:
            continue
        st = np.linalg.solve(m, (q-a).T).T
        bary = np.stack([1-st.sum(1), st[:, 0], st[:, 1]], 1)
        inside = (bary > -1e-6).all(1)
        if inside.any():
            out.append((ys.ravel()[inside], xs.ravel()[inside], np.full(int(inside.sum()), k), bary[inside]))
    ys, xs, fi, bary = (np.concatenate(v) for v in zip(*out))
    return ys, xs, fi, bary


def dilate(rgb, valid, steps):
    rgb, valid = rgb.copy(), valid.copy()
    for _ in range(steps):
        acc = np.zeros_like(rgb); cnt = np.zeros(valid.shape)
        for dy in (-1, 0, 1):
            for dx in (-1, 0, 1):
                if dy == dx == 0:
                    continue
                sv = np.roll(np.roll(valid, dy, 0), dx, 1)
                acc += np.roll(np.roll(rgb, dy, 0), dx, 1)*sv[..., None]; cnt += sv
        grow_ = ~valid & (cnt > 0)
        rgb[grow_] = acc[grow_]/cnt[grow_, None]
        valid |= grow_
    return rgb, valid


def surface_samples(p, faces, uv, density, rng):
    a = area3(p, faces)
    n = np.maximum(1, np.round(a*density).astype(int))
    fi = np.repeat(np.arange(len(faces)), n)
    r1, r2 = rng.random(len(fi)), rng.random(len(fi))
    s = np.sqrt(r1)
    bary = np.stack([1-s, s*(1-r2), s*r2], 1)
    return (np.einsum('ni,nij->nj', bary, p[faces[fi]]), np.einsum('ni,nij->nj', bary, uv[faces[fi]]),
            face_normals(p, faces)[fi])


def bake(low, sides, pixels, size=BAKE_SIZE):
    """Colour each covered texel from the nearest normal-agreeing source point."""
    rng = np.random.default_rng(0)
    sp, suv, sn = [], [], []
    for side in ('left', 'right'):
        s = sides[side]
        a, b, c = surface_samples(s['hiP'], s['hiF'], s['hiUV'], BAKE_SAMPLES_PER_M2, rng)
        sp.append(a); suv.append(b); sn.append(c)
    sp, suv, sn = np.concatenate(sp), np.concatenate(suv), np.concatenate(sn)
    tree = cKDTree(sp)
    ys, xs, fi, bary = raster(low['uv'], low['faces'], size)
    points = np.einsum('ni,nij->nj', bary, low['p'][low['faces'][fi]])
    normals = np.einsum('ni,nij->nj', bary, low['n'][low['faces'][fi]])
    normals /= np.maximum(np.linalg.norm(normals, axis=1, keepdims=True), 1e-20)
    dist, idx = tree.query(points, k=12)
    agree = np.einsum('nkj,nj->nk', sn[idx], normals) > BAKE_NORMAL_DOT
    pick = np.where(agree.any(1), np.argmax(agree, 1), 0)
    chosen = idx[np.arange(len(idx)), pick]
    colours = spb.sample_image(pixels, suv[chosen])*255.
    rgb = np.zeros((size, size, 3)); valid = np.zeros((size, size), bool)
    rgb[ys, xs] = colours; valid[ys, xs] = True
    covered = int(valid.sum())
    rgb, valid = dilate(rgb, valid, BAKE_GUTTER)
    rgb[~valid] = np.median(colours, 0)
    report = {'size': size, 'coveredTexels': covered, 'coverage': round(covered/size/size, 4),
              'normalGatedShare': round(float(agree.any(1).mean()), 4),
              'sampleDistanceMm': {'p50': round(float(np.median(dist[:, 0])*1000), 2),
                                   'p99': round(float(np.percentile(dist[:, 0], 99)*1000), 2)},
              'sourceSamples': int(len(sp))}
    return np.clip(np.rint(rgb), 0, 255).astype(np.uint8), report


def encode_jpeg(pixels):
    out = io.BytesIO()
    Image.fromarray(pixels).save(out, 'JPEG', quality=JPEG_QUALITY, subsampling=0, optimize=False)
    return out.getvalue()


def texel_density(p, uv, faces, size):
    a3 = area3(p, faces)
    t = uv[faces]*size
    u, v = t[:, 1]-t[:, 0], t[:, 2]-t[:, 0]
    a2 = .5*np.abs(u[:, 0]*v[:, 1]-u[:, 1]*v[:, 0])
    return float(np.sqrt(a2.sum()/(a3.sum()*1e4)))


def write_growth_glb(target, low, image_payload, extras):
    d = {'asset': {'version': '2.0', 'generator': 'Eloria race_growths.py', 'extras': {'raceGrowths': extras}},
         'scene': 0, 'scenes': [{'nodes': [0]}], 'nodes': [{'name': NODE, 'mesh': 0}],
         'buffers': [{'byteLength': 0}], 'bufferViews': [], 'accessors': []}
    binary = bytearray()
    attrs = {'POSITION': spb.append_array(d, binary, low['p'], 'VEC3'),
             'NORMAL': spb.append_array(d, binary, low['n'], 'VEC3'),
             'TEXCOORD_0': spb.append_array(d, binary, low['uv'], 'VEC2')}
    indices = spb.append_array(d, binary, low['faces'].ravel(), 'SCALAR', 5125)
    d['meshes'] = [{'name': NODE, 'primitives': [{'attributes': attrs, 'indices': indices, 'material': 0,
                                                  'extras': {'sourceRole': ROLE}}]}]
    d['materials'] = [material_spec(0)]
    d['images'] = [{'mimeType': 'image/jpeg', 'bufferView': spb.append_view(d, binary, image_payload)}]
    d['samplers'] = [{'magFilter': 9729, 'minFilter': 9987, 'wrapS': 33071, 'wrapT': 33071}]
    d['textures'] = [{'source': 0, 'sampler': 0}]
    g.write(target, d, bytes(binary))


def material_spec(texture):
    return {'name': MATERIAL, 'doubleSided': True, 'emissiveFactor': [0, 0, 0],
            'pbrMetallicRoughness': {'baseColorTexture': {'index': texture}, 'metallicFactor': 0, 'roughnessFactor': .85}}


def prepare(sex, out=None, blender=None, sources=None, work=None, target=TARGET_TRIANGLES):
    slug = f'mycelari_{sex}'
    sources = Path(sources or project_dir()/'generate_models/eloria-races-meshy')
    out = Path(out or default_growth(slug).parent)
    if 'godot-client' in out.resolve().parts:
        raise ValueError('prepare writes outside the client (work-output/race-rebase/p47/growths)')
    out.mkdir(parents=True, exist_ok=True)
    src = donor_frame(slug, sources)
    sides, seg_report = segment(src)
    for side in sides:
        if len(seg_report[side]['boundaryLoops']) != 1:
            raise ValueError(f'{slug} {side}: segmented growth has loops {seg_report[side]["boundaryLoops"]}')
    temp = Path(work) if work else Path(tempfile.mkdtemp(prefix='race_growths_'))
    temp.mkdir(parents=True, exist_ok=True)
    blended, version = run_blender(sides, temp, blender, target)
    p = blended['P'].astype(float); faces = blended['F'].astype(int); side_of_face = blended['side'].astype(int)
    counts = np.bincount(side_of_face, minlength=2)
    if not ((counts >= TRIANGLE_RANGE[0]) & (counts <= TRIANGLE_RANGE[1])).all():
        raise ValueError(f'{slug}: decimated triangles per side {counts.tolist()} outside {TRIANGLE_RANGE}')
    # Keep UV_BORDER texels clear of the image edge (repeat-wrapped bilinear
    # filtering would pull in the opposite edge).
    border = UV_BORDER/BAKE_SIZE
    rows, uv, local = split_corners(p, faces, border+blended['UV'].astype(float)*(1-2*border))
    weld = weld_ids(p[rows])
    low = {'p': p[rows], 'uv': uv, 'faces': local}
    low['n'] = vertex_normals(low['p'], local, weld)
    pixels, bake_report = bake(low, sides, src['pixels'])
    payload = encode_jpeg(pixels)
    loops = {}
    for k, (side, *_rest) in enumerate(SIDES):
        loops[side] = [int(len(l)) for l in boundary_loops(weld[local[side_of_face == k]])]
        if len(loops[side]) != 1:
            raise ValueError(f'{slug} {side}: decimated growth has loops {loops[side]}')
    extras = {'slug': slug, 'frame': 'donor (mycelari_<sex>_tpose_rigged.glb mesh space, metres)',
              'source': src['source'].name, 'sourceSHA256': digest(src['source']),
              'donor': src['donor'].name, 'donorSHA256': digest(src['donor']),
              'sourceToDonor': {'scale': src['scale'], 'offset': src['offset'],
                                'rule': 'uniform scale to the donor mesh height, bounding-box centres matched'},
              'donorJoints': {n: [float(v) for v in src['joints'][n]] for n in DONOR_JOINTS},
              'segmentation': {'seedLuminance': SEED_LUMINANCE, 'growLuminance': GROW_LUMINANCE,
                               'box': SEGMENT_BOX, 'seedBox': SEED_BOX, 'growBox': GROW_BOX,
                               'openRadiusM': OPEN_RADIUS, **seg_report},
              'reduction': {'blender': version, 'script': BLENDER_SCRIPT.name,
                            'scriptSHA256': source_digest(BLENDER_SCRIPT), 'targetTrianglesPerSide': target,
                            'trianglesPerSide': {'left': int(counts[0]), 'right': int(counts[1])},
                            'baseRingVertices': {k: v[0] for k, v in loops.items()}},
              'bake': {**bake_report, 'pxPerCm': round(texel_density(low['p'], low['uv'], low['faces'], BAKE_SIZE), 2),
                       'rule': f'nearest source sample with normal dot > {BAKE_NORMAL_DOT} (k=12), '
                               f'{BAKE_GUTTER} px gutter dilation', 'jpegQuality': JPEG_QUALITY},
              'toolSHA256': source_digest(Path(__file__))}
    target_path = out/f'{slug}.glb'
    write_growth_glb(target_path, low, payload, extras)
    report = {'output': str(target_path), 'outputSHA256': digest(target_path), **extras}
    target_path.with_suffix('.json').write_text(json.dumps(report, indent=2)+'\n', encoding='utf-8')
    Image.fromarray(pixels).save(out/f'{slug}_bake.png')
    if not work:
        shutil.rmtree(temp, ignore_errors=True)
    return report


# ---------------------------------------------------------------------------
# place
# ---------------------------------------------------------------------------

def read_growth(path):
    d, b = ea.read_glb(Path(path))
    prim = d['meshes'][0]['primitives'][0]
    out = {k: ea.accessor_array(d, b, prim['attributes'][k]).astype(float) for k in ('POSITION', 'NORMAL', 'TEXCOORD_0')}
    out['faces'] = ea.accessor_array(d, b, prim['indices']).astype(int).reshape(-1, 3)
    texture = d['textures'][d['materials'][prim['material']]['pbrMetallicRoughness']['baseColorTexture']['index']]
    out['image'] = spb.image_bytes(d, b, texture['source'])
    out['mimeType'] = d['images'][texture['source']]['mimeType']
    out['extras'] = d['asset']['extras']['raceGrowths']
    return out


def bind_joints(d, b):
    skin = d['skins'][0]
    names = [d['nodes'][j]['name'] for j in skin['joints']]
    ibm = ea.accessor_array(d, b, skin['inverseBindMatrices']).astype(float).reshape(-1, 4, 4).transpose(0, 2, 1)
    return names, ibm, {n: np.linalg.inv(m)[:3, 3] for n, m in zip(names, ibm)}


def part(d, b, name):
    for mesh, _, a, f in vspb.primitives(d, b):
        if mesh == name:
            return {k: np.asarray(v) for k, v in a.items()}, f
    raise ValueError(f'no {name} primitive')


def dense(a, joints):
    out = np.zeros((len(a['POSITION']), joints))
    for col in range(4):
        out[np.arange(len(out)), a['JOINTS_0'][:, col].astype(int)] += a['WEIGHTS_0'][:, col]
    return out


class Surface:
    """Closest points (with interpolated normals and dense weights) on a mesh."""

    def __init__(self, p, faces, normals=None, weights=None):
        import trimesh
        self.p, self.faces = np.asarray(p, float), np.asarray(faces, int)
        self.mesh = trimesh.Trimesh(self.p, self.faces, process=False)
        self.normals, self.weights = normals, weights

    def query(self, points):
        import trimesh
        points = np.asarray(points, float)
        q, dist, tri = trimesh.proximity.closest_point(self.mesh, points)
        bary = trimesh.triangles.points_to_barycentric(self.p[self.faces[tri]], q)
        bary = np.clip(bary, 0, 1)
        bary /= bary.sum(1, keepdims=True)
        out = {'point': q, 'distance': dist, 'triangle': tri, 'bary': bary}
        if self.normals is not None:
            n = np.einsum('ni,nij->nj', bary, self.normals[self.faces[tri]])
            out['normal'] = n/np.maximum(np.linalg.norm(n, axis=1, keepdims=True), 1e-20)
            out['signed'] = np.einsum('nj,nj->n', points-q, out['normal'])
        if self.weights is not None:
            out['weights'] = np.einsum('ni,nij->nj', bary, self.weights[self.faces[tri]])
        return out


def welded_edges(p, faces, weld):
    e = np.concatenate([faces[:, [0, 1]], faces[:, [1, 2]], faces[:, [2, 0]]])
    e = np.unique(np.sort(weld[e], 1), axis=0)
    first = np.zeros(weld.max()+1, int)
    first[weld[::-1]] = np.arange(len(weld))[::-1]
    return e, np.linalg.norm(p[first[e[:, 0]]]-p[first[e[:, 1]]], axis=1)


def geodesic_from(p, faces, weld, sources):
    """Shortest edge-path distance (over welded vertices) from any source row."""
    from scipy.sparse.csgraph import dijkstra
    e, length = welded_edges(p, faces, weld)
    n = weld.max()+1
    graph = coo_matrix((np.concatenate([length, length]), (np.concatenate([e[:, 0], e[:, 1]]),
                                                         np.concatenate([e[:, 1], e[:, 0]]))), shape=(n, n)).tocsr()
    return dijkstra(graph, directed=False, indices=np.unique(weld[sources]), min_only=True)[weld]


def smoothstep(x, width):
    t = np.clip(x/width, 0, 1)
    return t*t*(3-2*t)


def smooth_weights(points, faces, ring, weights, passes=WEIGHT_SMOOTH_PASSES):
    """`passes` uniform-Laplacian passes of per-vertex weights over the
    welded edges of one growth side, the base ring rows pinned."""
    weld = weld_ids(points)
    e, _ = welded_edges(points, faces, weld)
    n = weld.max()+1
    graph = coo_matrix((np.ones(2*len(e)), (np.concatenate([e[:, 0], e[:, 1]]), np.concatenate([e[:, 1], e[:, 0]]))),
                       shape=(n, n)).tocsr()
    degree = np.maximum(np.asarray(graph.sum(1)).ravel(), 1)
    w = np.zeros((n, weights.shape[1]))
    np.add.at(w, weld, weights)
    w /= np.bincount(weld, minlength=n)[:, None]
    pinned = np.zeros(n, bool); pinned[weld[ring]] = True
    for _ in range(passes):
        w = np.where(pinned[:, None], w, (graph@w)/degree[:, None])
    return w[weld]


def place_growths(d, b, growth, cap_mode='surface', medial=0., arm_gain=1.):
    """The race_feature_shoulders primitive for an assembled body document.

    d, b: the body glTF (b may be a bytearray); growth: the prepared GLB.
    Returns {'attributes': {POSITION, NORMAL, TEXCOORD_0, JOINTS_0 (u8),
    WEIGHTS_0}, 'indices', 'image', 'mimeType', 'report'}. Read-only on d
    and b; append_growths() writes the node.
    """
    if cap_mode not in CAP_MODES:
        raise ValueError(f'cap_mode {cap_mode!r} not in {CAP_MODES}')
    src = read_growth(growth)
    names, _, joints = bind_joints(d, b)
    shirt_a, shirt_f = part(d, b, 'wardrobe_shirt')
    shirt = Surface(shirt_a['POSITION'], shirt_f, shirt_a['NORMAL'].astype(float), dense(shirt_a, len(names)))
    p0, faces = src['POSITION'], src['faces']
    weld = weld_ids(p0)
    donor = {k: np.array(v) for k, v in src['extras']['donorJoints'].items()}
    out_p = p0.copy()
    weights = np.zeros((len(p0), len(names)))
    report = {'growth': Path(growth).name, 'growthSHA256': digest(growth), 'capMode': cap_mode, 'medialM': medial,
              'capArmGain': arm_gain, 'weightSmoothPasses': WEIGHT_SMOOTH_PASSES if cap_mode == 'surface' else None,
              'snap': {'insetM': SNAP_INSET, 'falloffM': SNAP_FALLOFF, 'iterations': SNAP_ITERATIONS},
              'weightFeatherM': WEIGHT_FEATHER}
    torso = np.isin(names, TORSO_JOINTS)
    arm = np.array(['upperarm' in n for n in names])
    for side, sign, donor_joint, joint in SIDES:
        rows = np.flatnonzero(np.sign(p0[:, 0]) == sign)
        side_faces = faces[(np.sign(p0[faces, 0]) == sign).all(1)]
        if len(np.unique(side_faces)) != len(rows):
            raise ValueError(f'{side}: growth faces straddle the midline')
        loops = boundary_loops(weld[side_faces])
        if len(loops) != 1:
            raise ValueError(f'{side}: growth has {len(loops)} open boundaries')
        ring = np.searchsorted(rows, rows[np.isin(weld[rows], loops[0])])
        local_faces = np.searchsorted(rows, side_faces)
        centre = p0[rows][ring].mean(0)
        k = abs(joints[joint][0])/abs(donor[donor_joint][0])
        moved = joints[joint]+(centre-donor[donor_joint])*np.array([k, 1., 1.])-centre-np.array([sign*medial, 0., 0.])
        g = p0[rows]+moved
        # Seat the ring on the shirt (SNAP_INSET inside it): a point-to-plane
        # fit that moves the growth in the body's y-z plane only. The joint
        # translation keeps deciding how far out along the shoulder (x) it
        # stands; a free x slides the male caps 3 cm out onto the deltoid.
        t = np.zeros(3)
        before = shirt.query(g[ring])
        for _ in range(SNAP_ITERATIONS):
            q = shirt.query(g[ring]+t)
            n = q['normal'][:, 1:]
            r = (q['point']-SNAP_INSET*q['normal']-(g[ring]+t))[:, 1:]
            nn = np.einsum('ni,nj->nij', n, n)
            t[1:] += np.linalg.solve(nn.sum(0)+SEAT_DAMPING*len(n)*np.eye(2), np.einsum('nij,nj->i', nn, r))
        g += t
        # The ring then lands exactly SNAP_INSET inside the shirt; the residual
        # displacement fades out over SNAP_FALLOFF of geodesic distance.
        q = shirt.query(g[ring])
        target = q['point']-SNAP_INSET*q['normal']
        residual = target-g[ring]
        geo = geodesic_from(g, local_faces, weld_ids(g), ring)
        kernel = np.exp(-(np.linalg.norm(g[:, None]-g[ring][None], axis=2)/(SNAP_FALLOFF/2))**2)
        kernel /= np.maximum(kernel.sum(1, keepdims=True), 1e-20)
        g += (kernel@residual)*(1-smoothstep(geo, SNAP_FALLOFF))[:, None]
        g[ring] = target
        out_p[rows] = g
        # Weights. 'surface': the shirt weights under every vertex, smoothed
        # over the growth (smooth_weights). 'mean'/'torso': a ring vertex
        # copies the shirt at its closest point; with geodesic distance they
        # blend (WEIGHT_FEATHER) to the cap weights.
        ring_w = q['weights']
        mean = ring_w.mean(0)
        cap = np.where(torso, mean, 0.) if cap_mode == 'torso' else mean.copy()
        cap[arm] *= arm_gain
        cap /= cap.sum()
        if cap_mode == 'surface':
            weights[rows] = smooth_weights(g, local_faces, ring, shirt.query(g)['weights'])
        else:
            s = smoothstep(geo, WEIGHT_FEATHER)[:, None]
            weights[rows] = (1-s)*(kernel@ring_w)+s*cap
        after = shirt.query(g)
        free = geo > CHECK_RING_BAND
        report[side] = {
            'baseRingVertices': int(len(ring)), 'shoulderScaleX': float(k), 'jointTranslationM': moved.tolist(),
            'fitTranslationM': t.tolist(),
            'ringGapBeforeFitMm': {'median': float(np.median(before['distance'])*1000), 'max': float(before['distance'].max()*1000)},
            'ringResidualAfterFitMm': {'median': float(np.median(np.linalg.norm(residual, axis=1))*1000),
                                       'max': float(np.linalg.norm(residual, axis=1).max()*1000)},
            'restPenetrationMm': float(max(0., -after['signed'][free].min())*1000) if free.any() else 0.,
            'ringWeightsMean': {names[j]: round(float(mean[j]), 4) for j in np.argsort(-mean) if mean[j] > .005},
            'capWeights': {names[j]: round(float(cap[j]), 4) for j in np.argsort(-cap) if cap[j] > .005}
            if cap_mode != 'surface' else None,
            'topWeightsMean': {names[j]: round(float(v), 4) for j, v in enumerate(weights[rows][geo > .03].mean(0))
                               if v > .005} if (geo > .03).any() else None}
    order = np.argsort(-weights, axis=1, kind='stable')[:, :4]
    values = np.take_along_axis(weights, order, axis=1)
    values = np.where(values > 1e-6, values, 0.)
    values /= values.sum(1, keepdims=True)
    order = np.where(values > 0, order, 0)
    attributes = {'POSITION': out_p.astype('<f4'), 'NORMAL': vertex_normals(out_p, faces, weld).astype('<f4'),
                  'TEXCOORD_0': src['TEXCOORD_0'].astype('<f4'), 'JOINTS_0': order.astype('u1'),
                  'WEIGHTS_0': values.astype('<f4')}
    report.update(triangles=int(len(faces)), vertices=int(len(out_p)))
    return {'attributes': attributes, 'indices': faces.ravel().astype('<u4'), 'image': src['image'],
            'mimeType': src['mimeType'], 'report': report}


def append_array(d, binary, values, kind, component):
    dtype = {5126: '<f4', 5125: '<u4', 5123: '<u2', 5121: 'u1'}[component]
    values = np.ascontiguousarray(values, dtype=dtype)
    spec = {'bufferView': spb.append_view(d, binary, values.tobytes()), 'componentType': component,
            'count': len(values), 'type': kind}
    if kind == 'VEC3':
        spec.update(min=values.min(0).tolist(), max=values.max(0).tolist())
    d['accessors'].append(spec)
    return len(d['accessors'])-1


def append_growths(d, binary, placed):
    """Append node, mesh, material, texture, sampler and image for `placed`.

    The node goes after every existing node, under the parent of the body
    node, skinned with skin 0: joint order and inverse binds are untouched.
    binary must be a bytearray; g.compact afterwards, as build does.
    """
    if any(n.get('name') == NODE for n in d['nodes']):
        raise ValueError(f'{NODE} already present')
    a = placed['attributes']
    attrs = {'POSITION': append_array(d, binary, a['POSITION'], 'VEC3', 5126),
             'NORMAL': append_array(d, binary, a['NORMAL'], 'VEC3', 5126),
             'TEXCOORD_0': append_array(d, binary, a['TEXCOORD_0'], 'VEC2', 5126),
             'JOINTS_0': append_array(d, binary, a['JOINTS_0'], 'VEC4', 5121),
             'WEIGHTS_0': append_array(d, binary, a['WEIGHTS_0'], 'VEC4', 5126)}
    indices = append_array(d, binary, placed['indices'], 'SCALAR', 5125)
    d.setdefault('images', []).append({'mimeType': placed['mimeType'],
                                       'bufferView': spb.append_view(d, binary, placed['image'])})
    d.setdefault('samplers', []).append({'magFilter': 9729, 'minFilter': 9987, 'wrapS': 33071, 'wrapT': 33071})
    d.setdefault('textures', []).append({'source': len(d['images'])-1, 'sampler': len(d['samplers'])-1})
    d['materials'].append(material_spec(len(d['textures'])-1))
    d['meshes'].append({'name': NODE, 'primitives': [{'attributes': attrs, 'indices': indices,
                                                      'material': len(d['materials'])-1,
                                                      'extras': {'sourceRole': ROLE}}]})
    body = next(i for i, n in enumerate(d['nodes']) if n.get('name') == 'body')
    parent = next((i for i, n in enumerate(d['nodes']) if body in n.get('children', [])), None)
    d['nodes'].append({'name': NODE, 'mesh': len(d['meshes'])-1, 'skin': 0})
    if parent is None:
        d['scenes'][d.get('scene', 0)]['nodes'].append(len(d['nodes'])-1)
    else:
        d['nodes'][parent]['children'].append(len(d['nodes'])-1)
    return len(d['nodes'])-1


def place_file(body, out, growth=None, cap_mode='surface', medial=0., arm_gain=1.):
    """Proof path: body GLB + growths -> a scratch GLB (never into the client)."""
    out = Path(out)
    if 'godot-client' in out.resolve().parts:
        raise ValueError('place writes scratch GLBs outside godot-client')
    d, blob = ea.read_glb(Path(body))
    growth = Path(growth or default_growth(Path(body).stem))
    placed = place_growths(d, blob, growth, cap_mode, medial, arm_gain)
    binary = bytearray(blob)
    append_growths(d, binary, placed)
    d, binary = g.compact(d, bytes(binary))
    out.parent.mkdir(parents=True, exist_ok=True)
    g.write(out, d, binary)
    report = {'body': str(body), 'bodySHA256': digest(body), 'output': str(out), 'outputSHA256': digest(out),
              **placed['report']}
    out.with_suffix('.json').write_text(json.dumps(report, indent=2)+'\n', encoding='utf-8')
    return report


# ---------------------------------------------------------------------------
# check (V21)
# ---------------------------------------------------------------------------

def quat_matrix(q):
    x, y, z, w = q
    return np.array([[1-2*(y*y+z*z), 2*(x*y-z*w), 2*(x*z+y*w)],
                     [2*(x*y+z*w), 1-2*(x*x+z*z), 2*(y*z-x*w)],
                     [2*(x*z-y*w), 2*(y*z+x*w), 1-2*(x*x+y*y)]])


def trs(t, r, s):
    m = np.eye(4)
    m[:3, :3] = quat_matrix(r)*np.asarray(s, float)
    m[:3, 3] = t
    return m


def node_trs(node):
    if 'matrix' in node:
        m = np.asarray(node['matrix'], float).reshape(4, 4).T
        return m
    return trs(node.get('translation', [0, 0, 0]), node.get('rotation', [0, 0, 0, 1]), node.get('scale', [1, 1, 1]))


class Library:
    """The shared animation library, sampled the way the client copies it:
    each channel's local TRS replaces the body joint's rest local by bone
    name (with the model's boneAliases); joints without a channel keep their
    rest local."""

    def __init__(self, path, aliases):
        self.d, self.b = ea.read_glb(Path(path))
        self.clips = {}
        for anim in self.d['animations']:
            channels = {}
            for c in anim['channels']:
                node, kind = c['target'].get('node'), c['target']['path']
                if node is None or kind == 'weights':
                    continue
                s = anim['samplers'][c['sampler']]
                name = self.d['nodes'][node].get('name')
                channels[(aliases.get(name, name), kind)] = (
                    ea.accessor_array(self.d, self.b, s['input']).astype(float).ravel(),
                    ea.accessor_array(self.d, self.b, s['output']).astype(float), s.get('interpolation', 'LINEAR'))
            self.clips[anim['name']] = channels

    def duration(self, clip):
        return max(t[-1] for t, _, _ in self.clips[clip].values())

    def value(self, clip, joint, kind, time, default):
        entry = self.clips[clip].get((joint, kind))
        if entry is None:
            return default
        t, v, interpolation = entry
        k = int(np.searchsorted(t, time, side='right'))
        if k <= 0:
            return v[0]
        if k >= len(t) or interpolation == 'STEP':
            return v[min(k, len(t))-1]
        a = (time-t[k-1])/(t[k]-t[k-1])
        if kind == 'rotation':
            q0, q1 = v[k-1], v[k]*(1 if np.dot(v[k-1], v[k]) >= 0 else -1)
            q = q0*(1-a)+q1*a
            return q/np.linalg.norm(q)
        return v[k-1]*(1-a)+v[k]*a


class Rig:
    """Body node tree; skinning matrices for a library pose."""

    def __init__(self, d, b):
        self.d = d
        self.names, self.ibm, _ = bind_joints(d, b)
        self.joint_nodes = d['skins'][0]['joints']
        self.parent = {c: i for i, n in enumerate(d['nodes']) for c in n.get('children', [])}
        self.rest = [node_trs(n) for n in d['nodes']]
        self.rest_trs = [(n.get('translation', [0, 0, 0]), n.get('rotation', [0, 0, 0, 1]), n.get('scale', [1, 1, 1]))
                         for n in d['nodes']]
        self.order = []
        seen = set()

        def visit(i):
            if i in seen:
                return
            if i in self.parent:
                visit(self.parent[i])
            seen.add(i); self.order.append(i)
        for i in range(len(d['nodes'])):
            visit(i)

    def skinning(self, library=None, clip=None, time=0.):
        local = list(self.rest)
        if library is not None:
            for j in self.joint_nodes:
                name = self.d['nodes'][j]['name']
                t0, r0, s0 = self.rest_trs[j]
                local[j] = trs(library.value(clip, name, 'translation', time, t0),
                               library.value(clip, name, 'rotation', time, r0),
                               library.value(clip, name, 'scale', time, s0))
        world = [None]*len(local)
        for i in self.order:
            world[i] = local[i] if i not in self.parent else world[self.parent[i]]@local[i]
        return np.stack([world[j] for j in self.joint_nodes])@self.ibm, {self.d['nodes'][j]['name']: world[j]
                                                                          for j in self.joint_nodes}


def skin_points(mats, a, rows=None):
    rows = np.arange(len(a['POSITION'])) if rows is None else rows
    p = np.concatenate([a['POSITION'][rows].astype(float), np.ones((len(rows), 1))], 1)
    m = np.einsum('nk,nkij->nij', a['WEIGHTS_0'][rows].astype(float), mats[a['JOINTS_0'][rows].astype(int)])
    return np.einsum('nij,nj->ni', m, p)[:, :3], m[:, :3, :3]


def winding(points, tris):
    """Generalised winding number of each point against triangles (n, 3, 3)."""
    out = np.zeros(len(points))
    for start in range(0, len(points), 64):
        a = tris[None, :, 0]-points[start:start+64, None]
        b = tris[None, :, 1]-points[start:start+64, None]
        c = tris[None, :, 2]-points[start:start+64, None]
        la, lb, lc = (np.linalg.norm(v, axis=2) for v in (a, b, c))
        det = np.einsum('pti,pti->pt', a, np.cross(b, c))
        den = la*lb*lc+np.einsum('pti,pti->pt', a, b)*lc+np.einsum('pti,pti->pt', b, c)*la+np.einsum('pti,pti->pt', c, a)*lb
        out[start:start+64] = 2*np.arctan2(det, den).sum(1)/(4*np.pi)
    return out


def closed(p, faces, weld):
    """Faces plus a fan over the open base ring (to the ring centroid)."""
    key, fid, _ = edge_table(weld[faces])
    _, inverse, count = np.unique(key, return_inverse=True, return_counts=True)
    corner = np.concatenate([faces[:, [0, 1]], faces[:, [1, 2]], faces[:, [2, 0]]])[count[inverse.ravel()] == 1]
    centre = len(p)
    ring = np.unique(corner)
    pts = np.concatenate([p, p[ring].mean(0)[None]])
    fan = np.stack([corner[:, 1], corner[:, 0], np.full(len(corner), centre)], 1)
    return pts, np.concatenate([faces, fan]), ring


def action_clips(root, library):
    """Library clips the player action map reaches (combat clips through
    their recipe source clips)."""
    root = Path(root)
    actions = json.loads((root/'godot-client/data/animations/luminous.json').read_text(encoding='utf-8'))['actions']
    recipes = (root/'godot-client/src/actors/combat_animation_library.gd').read_text(encoding='utf-8')
    import re
    wanted = set(actions.values())|set(re.findall(r'\["([\w-]+)", [\d.]+, [\d.]+, [\d.]+\]', recipes))
    return sorted(c for c in wanted if c in library.clips)


def growth_parts(d, b):
    prim = next(p for m in d['meshes'] if m['name'] == NODE for p in m['primitives'])
    a = {k: ea.accessor_array(d, b, prim['attributes'][k]) for k in KEYS}
    return a, ea.accessor_array(d, b, prim['indices']).astype(int).reshape(-1, 3)



def growth_checks(d, b, root, clips=None, fps=CHECK_FPS, slug=None, library_path=None):
    """V21 numbers for a body carrying race_feature_shoulders."""
    root = Path(root)
    models = json.loads((root/'godot-client/data/actors/models.json').read_text(encoding='utf-8'))['models']
    config = models.get(slug, {}) if slug else {}
    aliases = config.get('boneAliases', {'head': 'Head'})
    library_path = Path(library_path or root/'godot-client'/str(config.get(
        'animationLibrary', 'res://assets/actors/native/shared/Universal_Animation_Library.glb')).replace('res://', ''))
    library = Library(library_path, aliases)
    clips = clips or action_clips(root, library)
    rig = Rig(d, b)
    rest, _ = rig.skinning()
    ga, gf = growth_parts(d, b)
    gp = ga['POSITION'].astype(float)
    weld = weld_ids(gp)
    shirt_a, shirt_f = part(d, b, 'wardrobe_shirt')
    shirt = Surface(shirt_a['POSITION'], shirt_f, shirt_a['NORMAL'].astype(float))
    arm_joints = [k for k, n in enumerate(rig.names) if 'upperarm' in n or 'lowerarm' in n]
    arm_share = dense(shirt_a, len(rig.names))[:, arm_joints].sum(1)
    heads = [(a, f) for name, role, a, f in vspb.primitives(d, b) if role == 'race_head']
    head_p = np.concatenate([a['POSITION'][np.unique(f)].astype(float) for a, f in heads])
    head_a = {k: np.concatenate([np.asarray(a[k])[np.unique(f)] for a, f in heads]) for k in ('POSITION', 'JOINTS_0', 'WEIGHTS_0')}
    wsum = ga['WEIGHTS_0'].astype(float).sum(1)
    report = {'node': NODE, 'triangles': int(len(gf)), 'vertices': int(len(gp)),
              'weightSumMaxError': float(np.abs(wsum-1).max()), 'restSkinMaxError': float(np.abs(rest-np.eye(4)).max()),
              'library': library_path.name, 'librarySHA256': digest(library_path), 'fps': fps, 'sides': {}}
    sides = {}
    for side, sign, _, joint in SIDES:
        tri = gf[(np.sign(gp[gf, 0]) == sign).all(1)]
        rows = np.unique(tri)
        local = np.searchsorted(rows, tri)
        pts, fan, ring = closed(gp[rows], local, weld[rows])
        geo = geodesic_from(gp[rows], local, weld[rows], ring)
        rest_q = shirt.query(gp[rows][ring])
        free = geo > CHECK_RING_BAND
        rest_all = shirt.query(gp[rows])
        centre, radius = gp[rows].mean(0), np.linalg.norm(gp[rows]-gp[rows].mean(0), axis=1).max()
        near_shirt = np.unique(shirt_f[(np.linalg.norm(shirt_a['POSITION'][shirt_f].astype(float).mean(1)-centre, axis=1) < radius+.12)])
        footprint = np.abs(winding(shirt_a['POSITION'][near_shirt].astype(float), pts[fan])) > .5
        # The shirt under the stalk (inside the closed growth at rest, grown by
        # one triangle ring) is hidden and crumples when the arm drops: it is
        # no surface the growth can sink under.
        covered = np.isin(shirt_f, near_shirt[footprint]).any(1)
        covered = np.isin(shirt_f, np.unique(shirt_f[covered])).any(1)
        shirt_tris = shirt_f[np.isin(shirt_f, near_shirt).all(1) & ~covered]
        near_head = np.flatnonzero(np.linalg.norm(head_p-centre, axis=1) < radius+.15)
        edges = np.unique(np.sort(np.concatenate([local[:, [0, 1]], local[:, [1, 2]], local[:, [2, 0]]]), 1), axis=0)
        rest_len = np.linalg.norm(gp[rows][edges[:, 0]]-gp[rows][edges[:, 1]], axis=1)
        top = np.argsort(-(gp[rows]-gp[rows][ring].mean(0))@np.array([0, 1., 0]))[:max(3, len(rows)//20)]
        axis = gp[rows][top].mean(0)-gp[rows][ring].mean(0)
        sides[side] = dict(rows=rows, local=local, fan=fan, ring=ring, free=free, geo=geo, near_shirt=near_shirt, shirt_tris=shirt_tris,
                           footprint=footprint, near_head=near_head, edges=edges, rest_len=rest_len, top=top,
                           axis=axis/np.linalg.norm(axis), joint=joint)
        report['sides'][side] = {
            'baseGapMm': {'median': float(np.median(np.maximum(rest_q['signed'], 0))*1000),
                          'max': float(np.maximum(rest_q['signed'], 0).max()*1000)},
            'baseInsetMm': {'median': float(np.median(-rest_q['signed'])*1000), 'max': float((-rest_q['signed']).max()*1000)},
            'restPenetrationMm': float(max(0., -rest_all['signed'][free].min())*1000) if free.any() else 0.,
            'triangles': int(len(tri)), 'baseRingVertices': int(len(ring)), 'nearShirtVertices': int(len(near_shirt)),
            'footprintShirtVertices': int(footprint.sum()), 'coveredShirtTriangles': int(covered.sum()),
            'nearHeadVertices': int(len(near_head)), 'clips': {}}
    for clip in clips:
        duration = library.duration(clip)
        times = np.arange(0, duration+1e-9, 1/fps) if duration > 0 else np.array([0.])
        for side, s in sides.items():
            report['sides'][side]['clips'][clip] = {'armSinkMm': 0., 'armPokeMm': 0., 'sinkMm': 0., 'pokeMm': 0.,
                                                    'headMm': 0., 'baseSinkMm': 0.,
                                                    'basePokeMm': 0., 'maxEdgeStretch': 1.,
                                                    'capTiltFromTorsoDeg': 0., 'armElevationDeg': -90.,
                                                    'worstMm': 0., 'worstTime': 0.}
        for time in times:
            mats, world = rig.skinning(library, clip, time)
            sp, srot = skin_points(mats, shirt_a)
            sn = np.einsum('nij,nj->ni', srot, shirt_a['NORMAL'].astype(float))
            sn /= np.maximum(np.linalg.norm(sn, axis=1, keepdims=True), 1e-20)
            hp, _ = skin_points(mats, head_a)
            for side, s in sides.items():
                r = report['sides'][side]['clips'][clip]
                rows = s['rows']
                gpts, grot = skin_points(mats, {k: ga[k] for k in ('POSITION', 'JOINTS_0', 'WEIGHTS_0')}, rows)
                # Growth sinking under the shirt: candidates by the skinned
                # smooth shirt normal within CHECK_PROBE, confirmed by the
                # winding number of the whole posed shirt (the shoulder
                # crease folds and flips normals when the arm drops).
                posed_shirt = Surface(sp, s['shirt_tris'], sn)
                q = posed_shirt.query(gpts[s['free']])
                cand = (q['distance'] < CHECK_PROBE) & (q['signed'] < -CHECK_SLACK)
                if cand.any():
                    inside = np.abs(winding(gpts[s['free']][cand], sp[shirt_f])) > .5
                    if inside.any():
                        depth, height = q['distance'][cand][inside], s['geo'][s['free']][cand][inside]
                        tri = s['shirt_tris'][q['triangle'][cand][inside]]
                        arm = (q['bary'][cand][inside]*arm_share[tri]).sum(1) > .5
                        for key, sel in (('armSinkMm', (height > CHECK_BASE_BAND) & arm),
                                         ('sinkMm', (height > CHECK_BASE_BAND) & ~arm),
                                         ('baseSinkMm', height <= CHECK_BASE_BAND)):
                            if sel.any():
                                r[key] = max(r[key], float(depth[sel].max()*1000))
                # Shirt inside the closed growth: where it crosses the growth
                # (geodesic height of the nearest growth point above the ring)
                # tells a seated base from cloth poking through the stalk/cap.
                closed_pts = np.concatenate([gpts, gpts[s['ring']].mean(0)[None]])
                tris = closed_pts[s['fan']]
                centre = gpts.mean(0); radius = np.linalg.norm(gpts-centre, axis=1).max()
                cand = s['near_shirt'][~s['footprint']]
                cand = cand[np.linalg.norm(sp[cand]-centre, axis=1) < radius]
                if len(cand):
                    inside = np.abs(winding(sp[cand], tris)) > .5
                    if inside.any():
                        hit = Surface(gpts, s['local']).query(sp[cand][inside])
                        height = (hit['bary']*s['geo'][s['local'][hit['triangle']]]).sum(1)
                        arm = arm_share[cand[inside]] > .5
                        for key, sel in (('armPokeMm', (height > CHECK_BASE_BAND) & arm),
                                         ('pokeMm', (height > CHECK_BASE_BAND) & ~arm),
                                         ('basePokeMm', height <= CHECK_BASE_BAND)):
                            if sel.any():
                                r[key] = max(r[key], float(hit['distance'][sel].max()*1000))
                hc = s['near_head'][np.linalg.norm(hp[s['near_head']]-centre, axis=1) < radius]
                if len(hc):
                    inside = np.abs(winding(hp[hc], tris)) > .5
                    if inside.any():
                        surf = Surface(gpts, s['local'])
                        r['headMm'] = max(r['headMm'], float(surf.query(hp[hc][inside])['distance'].max()*1000))
                worst = max(r['armSinkMm'], r['armPokeMm'], r['sinkMm'], r['pokeMm'], r['headMm'])
                if worst > r['worstMm']:
                    r['worstMm'], r['worstTime'] = worst, float(time)
                length = np.linalg.norm(gpts[s['edges'][:, 0]]-gpts[s['edges'][:, 1]], axis=1)
                r['maxEdgeStretch'] = max(r['maxEdgeStretch'], float((length/np.maximum(s['rest_len'], 1e-9)).max()))
                axis = gpts[s['top']].mean(0)-gpts[s['ring']].mean(0)
                expected = mats[rig.names.index('spine_03')][:3, :3]@s['axis']
                cosine = float(np.dot(axis/np.linalg.norm(axis), expected/np.linalg.norm(expected)))
                r['capTiltFromTorsoDeg'] = max(r['capTiltFromTorsoDeg'], float(np.degrees(np.arccos(np.clip(cosine, -1, 1)))))
                arm = world[s['joint'].replace('upperarm', 'lowerarm')][:3, 3]-world[s['joint']][:3, 3]
                r['armElevationDeg'] = max(r['armElevationDeg'], float(np.degrees(np.arcsin(arm[1]/np.linalg.norm(arm)))))
    for side in report['sides'].values():
        for r in side['clips'].values():
            for k in r:
                r[k] = round(r[k], 2)
            r['armRaise'] = r['armElevationDeg'] > ARM_RAISE_DEG
    return report


def clip_worst(r):
    """Deepest contact of one clip row (any kind growth_checks measures)."""
    return max(r['armSinkMm'], r['armPokeMm'], r['sinkMm'], r['pokeMm'], r['headMm'])


def gate(report, waivers=None):
    """V21 verdicts from growth_checks(). Every clip fails on any contact
    deeper than clipDepthMm, except a clip in `waivers` ({clip: mm}), which
    fails only deeper than its waived depth (a bound, so a waived clip cannot
    get silently worse)."""
    waivers = dict(waivers or {})
    fails = []
    if report['weightSumMaxError'] > GATES['weightSumError']:
        fails.append(f"weights sum off by {report['weightSumMaxError']:.2g}")
    for side, s in report['sides'].items():
        if s['baseGapMm']['median'] > GATES['baseGapMedianMm'] or s['baseGapMm']['max'] > GATES['baseGapMaxMm']:
            fails.append(f"{side} base gap {s['baseGapMm']}")
        if s['restPenetrationMm'] > GATES['restPenetrationMm']:
            fails.append(f"{side} rest penetration {s['restPenetrationMm']:.1f} mm")
        if s['triangles'] > GATES['trianglesPerSide']:
            fails.append(f"{side} {s['triangles']} triangles")
        for clip, r in s['clips'].items():
            limit = waivers.get(clip, GATES['clipDepthMm'])
            if clip_worst(r) > limit:
                kinds = {k: r[k] for k in ('armSinkMm', 'armPokeMm', 'sinkMm', 'pokeMm', 'headMm') if r[k] > limit}
                fails.append(f'{side} {clip}: {clip_worst(r):.1f} mm over {limit:g} mm {kinds}')
    return fails


def check_file(candidate, root, out=None, clips=None, fps=CHECK_FPS, slug=None):
    candidate = Path(candidate)
    d, b = ea.read_glb(candidate)
    report = growth_checks(d, b, root, clips, fps, slug or candidate.stem)
    report.update(candidate=str(candidate), candidateSHA256=digest(candidate), fails=gate(report), gates=GATES)
    if out:
        Path(out).write_text(json.dumps(report, indent=2)+'\n', encoding='utf-8')
    return report


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest='command', required=True)
    pr = sub.add_parser('prepare')
    pr.add_argument('--sex', choices=('male', 'female'), required=True)
    pr.add_argument('--out')
    pr.add_argument('--blender')
    pr.add_argument('--work', help='keep the Blender exchange files here')
    pl = sub.add_parser('place')
    pl.add_argument('--body', required=True)
    pl.add_argument('--out', required=True)
    pl.add_argument('--growth')
    pl.add_argument('--cap-mode', choices=CAP_MODES, default='surface')
    ch = sub.add_parser('check')
    ch.add_argument('--candidate', required=True)
    ch.add_argument('--root', default=str(TOOLS.parent.parent))
    ch.add_argument('--out')
    ch.add_argument('--slug')
    ch.add_argument('--clips', nargs='*')
    ch.add_argument('--fps', type=float, default=CHECK_FPS)
    args = ap.parse_args()
    if args.command == 'prepare':
        report = prepare(args.sex, args.out, args.blender, work=args.work)
        print(json.dumps({k: report[k] for k in ('output', 'outputSHA256', 'reduction', 'bake')}, indent=2))
    elif args.command == 'place':
        report = place_file(args.body, args.out, args.growth, args.cap_mode)
        print(json.dumps({k: report[k] for k in ('output', 'outputSHA256', 'left', 'right')}, indent=2))
    else:
        report = check_file(args.candidate, args.root, args.out, args.clips, args.fps, args.slug)
        print(json.dumps({'sides': {s: {k: v for k, v in r.items() if k != 'clips'} for s, r in report['sides'].items()},
                          'fails': report['fails']}, indent=2))
        if report['fails']:
            raise SystemExit(1)


if __name__ == '__main__':
    main()
