"""Per-piece reshaping of fitted headwear (the owner's review of the class kits, 2026-10-17).

``limb_head_remap.head_frame`` seats every helm and hood the same way: one
uniform scale and a translation, large enough that the whole head clears the
shell by 9 mm.  A few pieces need more than that.  This module does it, opt in
per piece from ``eloria-assets/source/equipment-design-fit/headwear.json``
(keyed by the Meshy source, like the set specs).  ``limb_head_remap.build``
calls it after head_frame.

``frame`` (every body)
    Scale by ``scale`` about ``about`` and lower by ``drop`` metres (either a
    number or one per sex, ``{"male": .., "female": ..}``).  ``centre`` is the
    cranium centre race_headwear_clearance fits behind the face (the default:
    the shell shrinks evenly round the skull); ``brow`` is head_frame's brow
    seat on the front of the face; ``socket`` the socket.  The result is still
    a similarity of the source and the frame record is rewritten to match.

``clear`` (Human bodies)
    Whatever of the head then comes through is pushed out radially from the
    cranium centre to ``clear`` metres (race_headwear_clearance.radial_push,
    the broad push the race passes give a helm).  The push only moves
    vertices; it never splits faces, so the vertex order still matches the
    race raw fits.

``cowl`` (Human bodies)
    A hood's lower part is drawn out over the collar of the torso it is
    designed with (``over``, a registry key).  It is solved in the idle pose,
    where the torso's design fit is solved: that torso's rest shell is an
    inverse-skinning image, standing up to 5 cm higher behind the neck than
    anything a player sees.  The hood rides Head; body and torso are skinned
    with the idle matrices in the torso's design-fit npz.  Round the idle neck
    axis:

    * the hem follows the upper envelope of the torso art's visible top (an
      open V-neck does not pull it down): below ``pivot`` (metres along the
      axis from the Head joint) the shell is stretched down, linearly with
      depth, to end ``overlap`` under it, by at most ``max_lower``;
    * the shell is pushed out to ``clear`` over skin and the art seen from
      outside, every layer at a bearing and height by the same amount, up to
      ``max_push``; art more than ``reach`` outside the shell is a hem tucked
      under by design and is left.  The push flares up into the hood over
      ``flare``, and the move is smoothed over space (``smooth_radius``), so
      a wrap folds as one cloth and its trims and beads stay on it.

    Head's idle matrix carries the shape back to rest: the cowl stays rigid
    on Head, socketed like any headwear.

    ``skinned: true`` skins it instead (written with the rig's skeleton and
    character-space rest positions; refit_race_headwear carries the weights to
    the races).  Weights: Head above the pivot; below it the skin's blend at
    the shell's radial projection (Head, neck_01, spine_03, spine_02,
    clavicles), faded in over ``blend``; where the shell lies on the collar
    (within ``follow``) the collar art's own weights; where it lies on Head
    skin (within ``face``: a wrap across the chin) Head; smoothed over
    ``weight_radius``; inverse skinning gives the rest shell.

Why rigid by default: in the game's clips the head moves a long way against
the upper torso (Head against spine_03, from idle: Walk 16 degrees, Jog 36,
Bow_Pull_Back 72), so a hood lying on the collar lets the collar through when
the head turns.  Measured through eight clips (Blender, the torso skinned,
rays square to the neck), a skinned cowl lets it through 4-16 % less than the
same shape rigid on Head, but stretches 6-13 % of its triangles past 1.8x in
the bow pull and sword swings (tearing; the sleeves read as torn at 0.6-5 %).
The rigid cowl lets it through no more than the hoods it replaces
(eloria-assets/qa/canonical-equipment-refit.md, "Headwear review fixes").
"""
from __future__ import annotations

import hashlib
import json
from functools import lru_cache
from pathlib import Path

import numpy as np

import equipment_authoring as ea

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
DESIGN = ROOT / 'eloria-assets/source/equipment-design-fit'
SPEC = DESIGN / 'headwear.json'
REGISTRY = ROOT / 'godot-client/data/actors/equipment.json'
CLIENT = ROOT / 'godot-client'
HUMAN = frozenset({'luminous_male', 'luminous_female'})
#: The bones a cowl may follow: the head, the neck and the yoke under the collar.
COWL_BONES = ('Head', 'neck_01', 'spine_03', 'spine_02', 'clavicle_l', 'clavicle_r')
#: Occupancy grid round the neck axis: azimuth bins and height step.
AZ_BINS = 72
T_STEP = .0025
#: Inward rays start this far from the neck axis.
RAY_FROM = .35
#: A helm's clearance push reads the head down to this far under the eye line (the jaw).
JAW_BELOW_EYE = .08


def _name(source) -> str:
    return Path(source).name.removesuffix('.orig')


@lru_cache(maxsize=4)
def _spec(text: str) -> dict:
    return json.loads(text)['pieces']


def entry(source) -> dict | None:
    """This piece's row of headwear.json, or None (the fitter's default)."""
    if not SPEC.exists():
        return None
    return _spec(SPEC.read_text(encoding='utf-8')).get(_name(source))


def _digest(path: Path) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def inputs_digest(source, rig) -> str | None:
    """What decides this piece's reshaping on ``rig``: its spec row and, for a
    cowl on a Human body, the torso it is drawn over (scene and npz)."""
    e = entry(source)
    if e is None:
        return None
    parts = [json.dumps(e, sort_keys=True)]
    if e.get('cowl') and rig.source_slug in HUMAN:
        scene, npz = _torso_files(e['cowl'], rig.source_slug)
        parts += [_digest(scene), _digest(npz)]
    return hashlib.sha256('|'.join(parts).encode()).hexdigest()


# ---------------------------------------------------------------------------
# frame
# ---------------------------------------------------------------------------

def _per_body(value, rig, default):
    """A number, or {"male": .., "female": ..} by the body's sex (a race takes its Human's)."""
    if isinstance(value, dict):
        return float(value.get(rig.source_slug.rsplit('_', 1)[1], default))
    return float(default if value is None else value)


def frame(points, report, e, rig, body_path):
    """``scale`` about the cranium centre (or the brow seat, or the socket) and
    ``drop``; returns the moved points and rewrites ``report`` (head_frame's
    record) to match."""
    m = _per_body(e.get('scale'), rig, 1.0)
    drop = _per_body(e.get('drop'), rig, 0.0) * rig.fit_scale
    if m == 1.0 and drop == 0.0:
        return points
    target = np.asarray(report['targetCenter'], dtype=float)
    about = e.get('about', 'centre')
    anchor = target.copy()
    if about == 'centre':
        import race_headwear_clearance as rc
        g = rc.head_geometry(str(body_path))
        anchor = g.head[:3, :3] @ g.centre_local + g.head[:3, 3]
    elif about == 'brow' and report.get('sourceBrow') is not None:
        eyes = ea.load_rig(Path(body_path), ('eyes',)).positions
        anchor = np.array([target[0], float(np.quantile(eyes[:, 1], .95)) + .032 * rig.fit_scale,
                           float(eyes[:, 2].max())])
    lower = np.array([0., drop, 0.])
    out = anchor + m * (np.asarray(points, dtype=float) - anchor) - lower
    report['scale'] = float(report['scale']) * m
    report['targetCenter'] = (anchor + m * (target - anchor) - lower).tolist()
    report['headwearFrame'] = {'scale': m, 'drop': drop, 'about': about, 'anchor': anchor.tolist()}
    return out


# ---------------------------------------------------------------------------
# clear (Human): the head that comes through a smaller helm
# ---------------------------------------------------------------------------

def clear(points, faces, e, body_path):
    import race_headwear_clearance as rc
    g = rc.head_geometry(str(body_path))
    head = np.concatenate([g.skin, g.scalp, g.ears])
    # The cranium and the face above the jaw: on a Human body the "face" set
    # is the whole one-role body, and a helm's rim stands off the neck and the
    # shoulders by design (head_frame never measured them).
    head = head[head.mean(1)[:, 1] > g.eye_y - JAW_BELOW_EYE]
    obstacle = rc.poking(g, head, points[faces], tol=0.0)
    # Head within ``clear`` of the inner wall counts too (``swallow``): the
    # push keeps that padding, not just the surface; whatever stands further
    # out than that is an opening (the face under a visor) and is left.
    moved, dv = rc.radial_push(g, head, points, float(e['clear']), shell_tris=points[faces], limit=.03,
                               swallow=float(e['clear']))
    moved = points + rc.rigid_small_parts(points, faces, moved - points)
    return moved, {'name': 'headwear_clear', 'poking': int(len(obstacle)),
                   'moved': int((dv > 1e-5).sum()), 'maxMm': round(float(dv.max(initial=0)) * 1000, 1)}


# ---------------------------------------------------------------------------
# cowl (Human): over the collar, skinned to the neck
# ---------------------------------------------------------------------------

def _torso_files(cowl, slug):
    registry = json.loads(REGISTRY.read_text(encoding='utf-8'))
    model = registry['models'][cowl['over']]
    sex = slug.rsplit('_', 1)[1]
    scene = model['variants'][f'canonical_human_{sex}']['scene']
    npz = DESIGN / slug / (cowl['overSource'] + '.npz')
    return CLIENT / scene.removeprefix('res://'), npz


def _lbs(points, joints, weights, skin):
    h = np.c_[points, np.ones(len(points))]
    m = np.einsum('nk,nkij->nij', weights, skin[joints])
    return np.einsum('nij,nj->ni', m, h)[:, :3]


def _art(scene: Path, names, skin, rows_for=None):
    """The torso's art (not its generated lining), skinned to idle: triangles,
    or with ``rows_for`` (bone names) also its idle vertices and their weights
    as dense rows over those bones."""
    d, b = ea.read_glb(scene)
    order = [d['nodes'][j]['name'] for j in d['skins'][0]['joints']]
    remap = np.array([names.index(n) for n in order])
    tris, verts, rows = [], [], []
    for m in d['meshes']:
        if m.get('name', '').startswith('Generated'):
            continue
        for p in m['primitives']:
            a = p['attributes']
            P = ea.accessor_array(d, b, a['POSITION']).astype(float)
            J = remap[ea.accessor_array(d, b, a['JOINTS_0']).astype(int)]
            W = ea.accessor_array(d, b, a['WEIGHTS_0']).astype(float)
            if np.issubdtype(ea.accessor_array(d, b, a['WEIGHTS_0']).dtype, np.integer):
                W = W / 255.
            W = W / np.maximum(W.sum(1, keepdims=True), 1e-9)
            F = ea.accessor_array(d, b, p['indices']).astype(int).reshape(-1, 3)
            Q = _lbs(P, J, W, skin)
            tris.append(Q[F])
            if rows_for is not None:
                dense = np.zeros((len(P), len(rows_for)))
                for k, bone in enumerate(rows_for):
                    dense[:, k] = np.where(J == names.index(bone), W, 0.).sum(1)
                verts.append(Q)
                rows.append(dense)
    if rows_for is not None:
        return np.concatenate(tris), np.concatenate(verts), np.concatenate(rows)
    return np.concatenate(tris)


class _Neck:
    """Cylindrical coordinates round the idle neck axis (neck_01 -> Head)."""

    def __init__(self, base, top):
        self.o = np.asarray(base, dtype=float)
        a = np.asarray(top, dtype=float) - self.o
        self.a = a / np.linalg.norm(a)
        f = np.array([0., 0., 1.]) - self.a[2] * self.a
        self.f = f / np.linalg.norm(f)
        self.s = np.cross(self.a, self.f)
        self.head_t = float(np.dot(np.asarray(top) - self.o, self.a))

    def cyl(self, p):
        d = np.asarray(p, dtype=float) - self.o
        t = d @ self.a
        x, z = d @ self.s, d @ self.f
        return np.arctan2(x, z), t, np.hypot(x, z)

    def point(self, th, t, r):
        return (self.o + np.multiply.outer(t, self.a) + np.multiply.outer(r * np.sin(th), self.s)
                + np.multiply.outer(r * np.cos(th), self.f))

    def direction(self, th):
        return np.multiply.outer(np.sin(th), self.s) + np.multiply.outer(np.cos(th), self.f)


def _inward(engine, neck, th, t):
    """Radius of the first surface facing an inward ray (from RAY_FROM), per (th, t);
    nan where the ray meets none.  Back faces are skipped: materials are culled."""
    th, t = np.broadcast_arrays(th, t)
    th, t = th.ravel(), t.ravel()
    d = -neck.direction(th)
    o = neck.point(th, t, np.full(len(th), RAY_FROM))
    r = np.full(len(th), np.nan)
    import race_headwear_clearance as rc
    for s in rc._chunks(len(o), 4000):
        loc, ri, ti = engine.ray.intersects_location(o[s], d[s], multiple_hits=True)
        facing = np.einsum('ij,ij->i', engine.face_normals[ti], d[s][ri]) < 0
        loc, ri = loc[facing], ri[facing]
        dist = np.full(len(o[s]), np.inf)
        np.minimum.at(dist, ri, np.linalg.norm(loc - o[s][ri], axis=1))
        r[s] = np.where(np.isfinite(dist), RAY_FROM - dist, np.nan)
    return r


def _mesh(tris):
    import trimesh
    return trimesh.Trimesh(tris.reshape(-1, 3), np.arange(tris.size // 3).reshape(-1, 3), process=False)


def _circular_smooth(values, sigma_bins):
    from scipy.ndimage import gaussian_filter1d
    return gaussian_filter1d(values, sigma_bins, mode='wrap')


def _bins(th):
    return np.clip(((th + np.pi) / (2 * np.pi) * AZ_BINS).astype(int), 0, AZ_BINS - 1)


def _space_smooth(values, points, fixed, radius, rounds):
    """Average each row over the points within ``radius`` (Gaussian, sigma a
    third of it) ``rounds`` times; ``fixed`` rows stay.  By distance, not by
    mesh edges: a trim strip, a bead or a lining is its own piece of mesh but
    lies on the cloth, and must move (and bend) with it."""
    from scipy.sparse import csr_matrix
    from scipy.spatial import cKDTree
    tree = cKDTree(points)
    pairs = tree.sparse_distance_matrix(tree, radius, output_type='coo_matrix')
    sigma = radius / 3.
    w = np.exp(-(pairs.data ** 2) / (2 * sigma * sigma))
    n = len(points)
    m = csr_matrix((np.r_[w, np.ones(n)], (np.r_[pairs.row, np.arange(n)], np.r_[pairs.col, np.arange(n)])),
                   shape=(n, n))
    total = np.asarray(m.sum(1)).ravel()
    v = np.asarray(values, dtype=float).copy()
    for _ in range(rounds):
        v = np.where(fixed[:, None], v, (m @ v) / total[:, None])
    return v


def cowl(points, faces, e, rig, body_path):
    """Draw the hood's lower part over the torso collar and skin it (Human body).

    ``points`` are head_frame's rest world positions.  Returns (rest points,
    joints into rig.joint_names (n, 4), weights (n, 4), report)."""
    import race_headwear_clearance as rc
    from scipy.ndimage import gaussian_filter, grey_dilation
    c = e['cowl']
    scene, npz = _torso_files(c, rig.source_slug)
    data = np.load(npz)
    names = [str(n) for n in data['joint_names']]
    skin = np.asarray(data['skin'], dtype=float)
    # body skin (with the scalp: the back of the skull is its own surface), idle
    body = ea.load_rig(Path(body_path), ('body', 'scalp'))
    remap = np.array([names.index(n) for n in body.joint_names])
    bj = remap[body.joints]
    body_idle = _lbs(body.positions, bj, body.weights, skin)
    body_tris = body_idle[body.faces]
    art_tris, art_v, art_rows = _art(scene, names, skin, rows_for=COWL_BONES)
    head_m = skin[names.index('Head')]
    joint = lambda n: (skin[names.index(n)] @ np.r_[rig.origin(n), 1.])[:3]
    neck = _Neck(joint('neck_01'), joint('Head'))
    q = (head_m @ np.c_[points, np.ones(len(points))].T).T[:, :3]

    pivot = neck.head_t + float(c.get('pivot', -.01)) * rig.fit_scale
    th_grid = (np.arange(AZ_BINS) + .5) / AZ_BINS * 2 * np.pi - np.pi
    t_grid = np.arange(-.10, pivot + .02, T_STEP)
    TH, T = np.meshgrid(th_grid, t_grid, indexing='ij')
    skin_r = _inward(_mesh(body_tris), neck, TH, T).reshape(TH.shape)
    art_r = _inward(_mesh(art_tris), neck, TH, T).reshape(TH.shape)
    seen = np.isfinite(art_r) & (art_r > np.nan_to_num(skin_r, nan=0.) - .001)
    # The collar's visible top: the highest art seen from outside, joined to
    # art below it (gaps under 1 cm bridge a strap's shadow).
    gap = int(round(.01 / T_STEP))
    run = np.zeros_like(seen)
    run[:, 0] = seen[:, 0]
    for k in range(1, seen.shape[1]):
        run[:, k] = seen[:, k] & (run[:, k - 1] | seen[:, max(0, k - gap):k].any(1))
    has = run.any(1)
    top = np.where(has, t_grid[np.where(run, np.arange(len(t_grid))[None, :], 0).max(1)], np.nan)
    occupied = np.fmax(np.where(seen, art_r, np.nan), skin_r)

    th, t, r = neck.cyl(q)
    b = _bins(th)
    below = t < pivot
    hem = np.full(AZ_BINS, np.nan)
    np.fmin.at(hem, b[below], t[below])
    # A bin the hood does not reach takes its neighbours' hem.
    hem = np.where(np.isfinite(hem), hem, np.nanmin(hem))
    # The collar line the hem follows is the upper envelope of the art's top
    # (a max over ``window_deg`` either side, then smoothed): an open V-neck
    # or a lapel's notch does not pull the hood down into the chest.
    from scipy.ndimage import maximum_filter1d
    win = int(round(float(c.get('window_deg', 40)) / (360 / AZ_BINS)))
    line = maximum_filter1d(np.where(has, top, -np.inf), 2 * win + 1, mode='wrap')
    line = np.where(np.isfinite(line), line, hem)
    line = _circular_smooth(line, float(c.get('smooth_deg', 15)) / (360 / AZ_BINS))
    want = np.minimum(hem, line - float(c.get('overlap', .015)) * rig.fit_scale)
    want = np.maximum(want, hem - float(c.get('max_lower', .05)) * rig.fit_scale)
    k = (pivot - want) / np.maximum(pivot - hem, 1e-6)
    k = np.clip(_circular_smooth(np.clip(k, 1., None), float(c.get('smooth_deg', 15)) / (360 / AZ_BINS)),
                1., float(c.get('max_stretch', 2.5)))
    t_new = np.where(below, pivot - (pivot - t) * k[b], t)

    # Out over skin and art: the inner wall per (azimuth, height) cell may not
    # come within ``clear`` of what is there; every layer at a cell moves by
    # the same amount, so a lining stays inside its shell.
    clearance = float(c.get('clear', .006)) * rig.fit_scale
    reach = float(c.get('reach', .07)) * rig.fit_scale
    cap = float(c.get('max_push', .06)) * rig.fit_scale
    # The push flares up into the hood above it (a cowl drawn out over a
    # stand-up collar, not a step at the collar's top), fading over ``flare``.
    keep = 1. - T_STEP / (float(c.get('flare', .04)) * rig.fit_scale)
    r_new = r.copy()
    pushed = np.zeros(len(q))
    for _ in range(3):
        cell_t = np.clip(np.round((t_new - t_grid[0]) / T_STEP).astype(int), 0, len(t_grid) - 1)
        inner = np.full(TH.shape, np.inf)
        live = t_new < pivot
        np.minimum.at(inner, (b[live], cell_t[live]), r_new[live])
        # Art or skin further out than ``reach`` past the inner wall is a hem
        # tucked under a collar by design (or a shoulder the hem stops at),
        # not something to climb over.
        over = occupied + clearance - inner
        need = np.where(np.isfinite(inner) & np.isfinite(occupied) & (over < reach), np.maximum(0., over), 0.)
        need = grey_dilation(need, size=(3, 3), mode=('wrap', 'nearest'))
        for j in range(1, need.shape[1]):
            need[:, j] = np.maximum(need[:, j], need[:, j - 1] * keep)
        need = np.maximum(need, gaussian_filter(need, (2.0, 2.0), mode=('wrap', 'nearest')))
        step = np.where(live, np.clip(need[b, cell_t], 0., cap - pushed), 0.)
        if step.max(initial=0) < 2e-4:
            break
        r_new += step
        pushed += step
    q_new = neck.point(th, t_new, r_new)
    # The move is smoothed over the shell (welded neighbours, the crown held),
    # so the layers of a wrap fold as one cloth instead of crumpling where the
    # push field steps; then pushed once more to restore the clearance.
    smooth = float(c.get('smooth_radius', .02)) * rig.fit_scale
    move = _space_smooth(q_new - q, q, fixed=t >= pivot, radius=smooth, rounds=int(c.get('move_rounds', 4)))
    q_new = q + move
    th1, t1, r1 = neck.cyl(q_new)
    b1 = _bins(th1)
    cell1 = np.clip(np.round((t1 - t_grid[0]) / T_STEP).astype(int), 0, len(t_grid) - 1)
    inner = np.full(TH.shape, np.inf)
    live = t1 < pivot
    np.minimum.at(inner, (b1[live], cell1[live]), r1[live])
    over = occupied + clearance - inner
    need = np.where(np.isfinite(inner) & np.isfinite(occupied) & (over < reach), np.maximum(0., over), 0.)
    need = gaussian_filter(grey_dilation(need, size=(5, 5), mode=('wrap', 'nearest')), (2.0, 2.0),
                           mode=('wrap', 'nearest'))
    extra = np.where(live, np.clip(need[b1, cell1], 0., cap), 0.)
    extra = _space_smooth(extra[:, None], q, fixed=t1 >= pivot, radius=smooth, rounds=2)[:, 0]
    q_new = neck.point(th1, t1, r1 + extra)
    pushed = np.linalg.norm(q_new - q, axis=1)
    q_new = q + rc.rigid_small_parts(q, faces, q_new - q)

    cols = [rig.joint_names.index(n) for n in COWL_BONES]
    if not c.get('skinned', False):
        # Kept rigid on Head: the idle shape carried back by Head's idle matrix.
        rest = (np.linalg.inv(head_m) @ np.c_[q_new, np.ones(len(q_new))].T).T[:, :3]
        joints = np.zeros((len(q_new), 4), dtype=int)
        joints[:, 0] = cols[0]
        weights = np.zeros((len(q_new), 4))
        weights[:, 0] = 1.
        report = {'name': 'headwear_cowl', 'over': c['over'], 'skinned': False,
                  'pushMm': {'max': round(float(pushed.max(initial=0)) * 1000, 1),
                             'moved': int((pushed > 1e-4).sum())},
                  'stretchMax': round(float(k.max()), 3)}
        return rest, None, None, report
    # Weights: Head above the pivot; below it the skin's blend where the
    # shell projects onto the neck and yoke, faded in over ``blend``.
    th2, t2, r2 = neck.cyl(q_new)
    hit_w = _projected_weights(body, body_tris, neck, q_new, cols, rig)
    head_row = np.zeros(len(cols))
    head_row[0] = 1.
    blend = float(c.get('blend', .02)) * rig.fit_scale
    s = np.clip((pivot - t2) / blend, 0., 1.)
    s = s * s * (3 - 2 * s)
    w = (1 - s)[:, None] * head_row + s[:, None] * hit_w
    # Where the shell lies on the collar it takes the collar's own weights
    # (faded out over ``follow``), so the two move as one: the design-fit
    # collar carries neck_01 up the nape and spine_03/clavicles in front.
    from scipy.spatial import cKDTree
    d_art, i_art = cKDTree(art_v).query(q_new)
    on = art_rows[i_art]
    total = on.sum(1)
    near = np.clip(1. - d_art / (float(c.get('follow', .03)) * rig.fit_scale), 0., 1.)
    near = near * near * (3 - 2 * near) * (total > .5)
    on = on / np.maximum(total, 1e-9)[:, None]
    w = (1 - near)[:, None] * w + near[:, None] * on
    # ...except over the face: shell lying on Head skin (a wrap across the
    # chin and jaw) stays on Head, or the jaw comes through it whenever the
    # head turns against the chest.
    from scipy.spatial import cKDTree as _Tree
    head_skin = body_idle[_dense_rows(body)[:, body.joint_names.index('Head')] > .8]
    d_face, _ = _Tree(head_skin).query(q_new)
    face = np.clip(1. - d_face / (float(c.get('face', .025)) * rig.fit_scale), 0., 1.)
    face = face * face * (3 - 2 * face) * (t2 < pivot)
    w = (1 - face)[:, None] * w + face[:, None] * head_row
    # Weights are smoothed over a short radius only: enough for a trim or a
    # bead to bend with the cloth it lies on, not so far that the crown's
    # Head and the hem's collar blend over the whole hood (which stretched a
    # tenth of its triangles past 1.8x in Bow_Pull_Back).
    w = _space_smooth(w, q_new, fixed=(t2 >= pivot) & (near == 0) & (face == 0),
                      radius=float(c.get('weight_radius', .01)) * rig.fit_scale,
                      rounds=int(c.get('smooth_rounds', 2)))
    w = _small_parts_mean(points, faces, w)
    w = np.clip(w, 0., None)
    w /= np.maximum(w.sum(1, keepdims=True), 1e-9)
    order = np.argsort(-w, axis=1)[:, :4]
    top4 = np.take_along_axis(w, order, 1)
    top4 /= np.maximum(top4.sum(1, keepdims=True), 1e-9)
    joints = np.asarray(cols)[order]
    rig_skin = skin[[names.index(n) for n in rig.joint_names]]
    m = np.einsum('nk,nkij->nij', top4, rig_skin[joints])
    rest = np.einsum('nij,nj->ni', np.linalg.inv(m), np.c_[q_new, np.ones(len(q_new))])[:, :3]
    reach = np.where(has, top, np.nan)
    report = {'name': 'headwear_cowl', 'over': c['over'], 'pivotAboveNeckMm': round(pivot * 1000, 1),
              'stretchMax': round(float(k.max()), 3), 'stretchMean': round(float(k.mean()), 3),
              'hemLowerMm': {'max': round(float(np.nanmax(hem - (want))) * 1000, 1),
                             'mean': round(float(np.nanmean(hem - want)) * 1000, 1)},
              'pushMm': {'max': round(float(pushed.max(initial=0)) * 1000, 1), 'moved': int((pushed > 1e-4).sum())},
              'collarBins': int(has.sum()), 'collarTopMm': round(float(np.nanmedian(reach)) * 1000, 1),
              'skinnedVertices': int(((s > 0) | (near > 0)).sum()), 'onCollar': int((near > .5).sum())}
    return rest, joints, top4, report


def _dense_rows(rig):
    """A rig's skin weights as dense rows over its joints."""
    dense = np.zeros((len(rig.positions), len(rig.joint_names)))
    for c in range(rig.joints.shape[1]):
        np.add.at(dense, (np.arange(len(dense)), rig.joints[:, c]), rig.weights[:, c])
    return dense


def _small_parts_mean(points, faces, values):
    """Every welded part smaller than race_headwear_clearance.SMALL_PART (a
    buckle, a rivet, a bead) takes its mean row, so it moves as one."""
    import race_headwear_clearance as rc
    from scipy.sparse import coo_matrix
    from scipy.sparse.csgraph import connected_components
    _, welded = np.unique(np.round(points, 5), axis=0, return_inverse=True)
    welded = welded.ravel()
    f = welded[faces]
    n = int(welded.max()) + 1
    graph = coo_matrix((np.ones(len(f) * 3), (f.ravel(), f[:, [1, 2, 0]].ravel())), shape=(n, n))
    _, label = connected_components(graph, directed=False)
    part = label[welded]
    count = int(part.max()) + 1
    lo = np.full((count, 3), np.inf)
    hi = np.full((count, 3), -np.inf)
    np.minimum.at(lo, part, points)
    np.maximum.at(hi, part, points)
    small = np.linalg.norm(hi - lo, axis=1) < rc.SMALL_PART
    total = np.zeros((count, values.shape[1]))
    np.add.at(total, part, values)
    mean = total / np.bincount(part, minlength=count)[:, None]
    return np.where(small[part][:, None], mean[part], values)


def _projected_weights(body, body_tris, neck, points, cols, rig):
    """The skin's own weights (restricted to ``cols``, renormalised) where an
    inward ray through each point, square to the neck axis, first meets the
    idle skin; the nearest skin vertex's where it meets none."""
    import race_headwear_clearance as rc
    import trimesh
    from scipy.spatial import cKDTree
    mesh = _mesh(body_tris)
    th, t, _ = neck.cyl(points)
    d = -neck.direction(th)
    o = neck.point(th, t, np.full(len(th), RAY_FROM))
    hit_tri = np.full(len(th), -1)
    hit_loc = np.zeros((len(th), 3))
    for s in rc._chunks(len(o), 4000):
        idx = np.arange(len(o))[s]
        loc, ri, ti = mesh.ray.intersects_location(o[s], d[s], multiple_hits=True)
        facing = np.einsum('ij,ij->i', mesh.face_normals[ti], d[s][ri]) < 0
        loc, ri, ti = loc[facing], ri[facing], ti[facing]
        dist = np.linalg.norm(loc - o[s][ri], axis=1)
        best = np.full(len(idx), np.inf)
        np.minimum.at(best, ri, dist)
        win = dist <= best[ri] + 1e-9
        hit_tri[idx[ri[win]]] = ti[win]
        hit_loc[idx[ri[win]]] = loc[win]
    dense = _dense_rows(body)
    rows = np.zeros((len(th), len(cols)))
    ok = hit_tri >= 0
    if ok.any():
        tri = body.faces[hit_tri[ok]]
        bary = np.clip(trimesh.triangles.points_to_barycentric(body_tris[hit_tri[ok]], hit_loc[ok]), 0, 1)
        bary /= np.maximum(bary.sum(1, keepdims=True), 1e-9)
        rows[ok] = np.einsum('nk,nkj->nj', bary, dense[tri][:, :, cols])
    if (~ok).any():
        _, near = cKDTree(body_tris.reshape(-1, 3)).query(points[~ok])
        rows[~ok] = dense[body.faces.reshape(-1)[near]][:, cols]
    total = rows.sum(1, keepdims=True)
    return np.where(total > 1e-6, rows / np.maximum(total, 1e-9), np.eye(len(cols))[0])
