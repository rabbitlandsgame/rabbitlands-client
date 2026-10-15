"""Ssarathi tail re-root (race programme P4, decision 6) and its clip checks.

The v2 tail (body primitive `race_tail`, its own image `Material_1`) is
re-emitted from the sacrum along a static drape in the midline plane:

* geometry: geodesic distance s from the root ring (the open loop nearest the
  pelvis); knots = the root-ring centroid at s = 0 and the Gaussian-smoothed
  centroids of CENTRELINE_BINS equal s-bands; rotation-minimising frames.
  Near the root the iso-s slices lie parallel to the oblique v2 root ring
  (44-48 degrees off the tube), so the old tangent there is the ring normal,
  blended to the centreline tangent over ROOT_BLEND_M: the ring stays
  parallel to the seat;
* a new centreline starts at SACRUM[slug] and follows the drape shape
  (TAIL_SHAPES[TAIL_SHAPE], R3 'heavy'): its pitch below the horizontal
  (straight back, -z) runs through (arc fraction, degrees) knots, 20 at the
  root, 50 half way, 80 at the tip, sampled at the old centreline's
  cumulative arc length scaled to the shape's length (.78 of v2: identity
  over the first KEEP_ROOT_M, one compression factor past it);
* every vertex keeps its offset in the old frame at its s and is re-emitted
  in the new frame there, its offset along the tangent stretched by the arc
  scale (cross-sections kept, texture compressed along the tail, UVs and
  triangles unchanged); normals turn with the same rotation;
* the flared root ring is taller than the seat is deep, so ring vertices
  less than SINK_DEPTH_M inside the Human surface are pushed to that depth,
  fading over SINK_FALLOFF_M (sink_root, as fit_tail did);
* weights: each vertex copies the trouser weights at its new rest position
  (inverse-square mix of the RESEAT_NEIGHBOURS nearest wardrobe_pants rows:
  pelvis about .72, thighs .07-.19), smoothstep to pure pelvis by FEATHER_M
  of geodesic arc from the root ring;
* faces lose only their loose fragments (< FRAGMENT_MIN_FACES, as fit_tail);
  TEXCOORD_0, the indices' rows and the image are the input's.

The race has no tail bones (joints would break every hair and headwear
bind), so past FEATHER_M the tail is rigid on the pelvis: the shape is the
one static drape that reads as a heavy tail in idle, walk and run, clears
the legs and the floor there, and stands up least when the pelvis bends
(R3 candidates and numbers: TAIL_SHAPES; clip limits and the pending waivers:
LEG_CLEARANCE_MIN_M, TAIL_CLIP_WAIVERS).

`reroot_tail` is pure: arrays in, arrays out. `tail_capsule` gives the
pelvis-local capsule (first CAPSULE_LENGTH_M of tail) a cape solver can
collide with (models.json tailCollision). `ClipLibrary` + `BodyRig` evaluate
the animation library the client plays (tracks applied by bone name onto the
body skeleton, untracked channels at the body's rest: NativeAnimationImporter
semantics) so that `clip_clearance` measures the skinned tail against leg
capsules, the floor and the class-kit pieces (parts 2/4/5) frame by frame,
offline. `v18_gate` is the verify hook (rest + playable clips).

    python eloria-assets/tools/race_tail.py check --root <wt> --slug ssarathi_male --head <v2 backup glb> [--shape heavy] [--clips action|all] [--no-kits] [--out report.json]

`check` re-roots the tail of a v2 body onto the installed body's trousers and
prints the rest and clip numbers; it never writes into the worktree.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

import numpy as np
from scipy.ndimage import gaussian_filter1d
from scipy.sparse import coo_matrix
from scipy.sparse.csgraph import connected_components, dijkstra
from scipy.spatial import cKDTree

sys.path.insert(0, str(Path(__file__).resolve().parent))
import equipment_authoring as ea  # noqa: E402

# Root-ring centre of the re-emitted tail (rest pose, metres): on the midline,
# 5.5 cm inside the Human trouser back (z -.138 male / -.127 female at y .955).
SACRUM = {'ssarathi_male': (0., .955, -.083), 'ssarathi_female': (0., .955, -.072)}
# Static drape shapes (R3). The race has no tail bones (adding joints would
# break every hair and headwear bind), so past FEATHER_M the tail is rigid on
# the pelvis and one shape has to read in every clip. A shape gives the new
# centreline's pitch below the horizontal (straight back, -z) as (arc
# fraction, degrees) knots, smoothstep between consecutive knots (zero slope
# at each knot), optionally a yaw towards +x the same way, and its arc length
# relative to the v2 tail ('length'). Below 1 the arc past KEEP_ROOT_M is
# compressed by one factor (ramping in over KEEP_RAMP_M) and the
# cross-sections are kept: the texture compresses along the tail by that
# factor, UVs and triangles are unchanged and nothing is cropped.
TAIL_SHAPES = {
    'pole': {'pitch': ((0., 10.), (1., 30.)), 'length': 1.},
    'drape': {'pitch': ((0., 25.), (1., 70.)), 'length': 1.},
    'drape_short': {'pitch': ((0., 25.), (1., 70.)), 'length': .82},
    's_curve': {'pitch': ((0., 20.), (.6, 65.), (1., 20.)), 'length': .85},
    'heavy': {'pitch': ((0., 20.), (.5, 50.), (1., 80.)), 'length': .78},
}
# R3 (lead review of the R2 pole, candidates in race-rebase/p47/tail_cands):
# 'pole' is the R1/R2 hang (a rigid 1.3-1.4 m pole straight back, standing up
# 1.35 m in Death_A and 1.09 m in Farm_Harvest, through capes); 'drape' and
# 'drape_short' hang 25 -> 70 degrees (full length the female tip goes 17 cm
# under the floor in Run_Female); 's_curve' lifts its tip off the ground but
# curls it upwards in the bent clips and crosses capes most. 'heavy' curves
# down from 20 degrees at the sacrum (steeper roots meet the thighs in
# Run_Female) to 80 at a tip that ends behind the heels near the ground, at
# 78% of the v2 length (80% leaves the female 7 mm off the floor in
# Run_Female at 30 fps): least rise in the bent clips and fewest cape
# crossings of the candidates that clear legs and floor in idle, walk and run.
TAIL_SHAPE = 'heavy'
KEEP_ROOT_M, KEEP_RAMP_M = .25, .10
CENTRELINE_BINS = 40
CENTRELINE_SIGMA = 1.5
ROOT_BLEND_M = .12
# The flared root ring is taller than the seat is deep: ring vertices less than
# SINK_DEPTH_M inside the Human surface are pushed to that depth; the push
# fades over SINK_FALLOFF_M of geodesic arc (as fit_tail did with TAIL_DEPTH).
SINK_DEPTH_M, SINK_FALLOFF_M = .008, .12
# A ring row the push leaves shallower than SINK_PULL_BELOW * SINK_DEPTH_M
# (it went into a narrow fold, near the opposite wall: the male crotch under
# a root pitched 20 degrees, 1.3 mm) is pulled towards the ring centre, in
# SINK_PULL_STEPS steps, until it is SINK_DEPTH_M deep.
SINK_PULL_BELOW, SINK_PULL_STEPS = .9, 40
FEATHER_M = .25
RESEAT_NEIGHBOURS = 4
FRAGMENT_MIN_FACES = 20
CAPSULE_LENGTH_M = .45
CAPSULE_MARGIN_M = .01
CAPSULE_START_M = .10
# Clip gates (design V18): the root band is fused into the seat and is not
# tested against the legs; leg capsules are the prototype's (thigh->calf,
# calf->foot, foot->ball).
ROOT_BAND_M = .25
LEG_CAPSULES = (('thigh', 'calf', .085), ('calf', 'foot', .060), ('foot', 'ball', .050))
# V18 clip gates, design limits (V18 at db9a92d30): in every playable clip
# (action_clips) the free tail keeps LEG_CLEARANCE_MIN_M off the leg capsules
# and no tail point goes more than -FLOOR_MIN_M under the floor; the highest
# tail point stays within RISE_MAX_M of the pelvis joint (in the idle family
# the flared root ring reaches 115-130 mm above it). Idle, walk and run keep
# LOCOMOTION_LEG_MIN_M (Run_Female 64 / 77 mm female / male) and the whole
# tail LOCOMOTION_FLOOR_MIN_M above the floor (Run_Female 37 / 123 mm).
# Batch B review: R3 had moved the limits to just past what the drape reaches
# and gated the floor only in Sitting_Idle and Death_A and the rise only in
# three clips, with Meditate exempt. Rigid on the pelvis, the drape sinks
# into the floor when the pelvis drops or tilts back (Meditate, the sit
# action, 906 / 808 mm; the attack_primary lunge Sword_Regular_A 395 /
# 296 mm) and stands up when it bends forward (Death_A 690 / 632 mm above the
# pelvis), and no static drape meets the design limits in those clips (R3
# candidates in race_b/tail). The clips that miss them are listed in
# TAIL_CLIP_WAIVERS at the achieved value (SAMPLE_FPS, rounded at least
# 1 mm outward to 5 mm) so that a rebuild cannot get worse unseen. THEY ARE
# WAIVERS PENDING THE LEAD'S TAIL CALL, not accepted values; every other
# playable clip is held to the design limits.
LEG_CLEARANCE_MIN_M = {'ssarathi_male': .090, 'ssarathi_female': .100}
LOCOMOTION_CLIPS = ('Idle_Subtle', 'Walk', 'Run_Female')
LOCOMOTION_LEG_MIN_M = {'ssarathi_male': .065, 'ssarathi_female': .055}
LOCOMOTION_FLOOR_MIN_M = .020
FLOOR_MIN_M = -.030
RISE_MAX_M = .30
# {slug: {clip: {'legM' | 'floorM' | 'riseM': limit}}} (see above).
TAIL_CLIP_WAIVERS = {
    'ssarathi_female': {
        'Meditate': {'floorM': -.910},
        'Sword_Regular_A': {'legM': .065, 'floorM': -.400},
        'Sword_Regular_A_Rec': {'legM': .075, 'floorM': -.385},
        'Sword_Regular_B': {'legM': .090, 'floorM': -.375},
        'Two-hand_Blast': {'floorM': -.370},
        'Death_A': {'legM': .020, 'floorM': -.365, 'riseM': .695},
        'Power_Up': {'floorM': -.360},
        'Backflip': {'floorM': -.280, 'riseM': 1.045},
        'Sitting_Idle': {'floorM': -.250},
        'Sitting_Exit': {'floorM': -.250},
        'Shivering': {'floorM': -.095},
        'Hit_Chest': {'floorM': -.090},
        'Farm_Harvest': {'floorM': -.060, 'riseM': .425},
        'Tired_Hunched': {'riseM': .310}},
    'ssarathi_male': {
        'Meditate': {'floorM': -.810},
        'Sword_Regular_A': {'legM': .065, 'floorM': -.300},
        'Sword_Regular_A_Rec': {'legM': .070, 'floorM': -.285},
        'Death_A': {'legM': .025, 'floorM': -.280, 'riseM': .635},
        'Sword_Regular_B': {'floorM': -.275},
        'Two-hand_Blast': {'floorM': -.270},
        'Power_Up': {'floorM': -.265},
        'Backflip': {'floorM': -.190, 'riseM': .945},
        'Sitting_Idle': {'floorM': -.165},
        'Sitting_Exit': {'floorM': -.165},
        'Farm_Harvest': {'riseM': .390}}}
SAMPLE_FPS = 15.
TIP_BAND_M = .03
ARC_TOLERANCE = .01
ROOT_X_MAX_M = .005
DEFAULT_ALIASES = {'head': 'Head'}
# Class kits (CreationArchetypes.loadout_at, creation_class_equipment_fit.gd):
# the tail-relevant parts only (2 cape, 4 legs, 5 torso).
CLASS_KITS = {'Vanguard': {2: 105, 4: 220, 5: 209}, 'Ranger': {4: 230, 5: 225},
              'Arcanist': {4: 185, 5: 222}, 'Warden': {2: 100, 4: 176, 5: 189}}


# ---------------------------------------------------------------------------
# Surface helpers
# ---------------------------------------------------------------------------

def weld(p, tol=1e-6):
    """Weld ids per row (rows within `tol` share an id), as rebase_race_body."""
    p = np.asarray(p, float)
    pairs = cKDTree(p).query_pairs(tol, output_type='ndarray')
    return connected_components(coo_matrix((np.ones(len(pairs)), (pairs[:, 0], pairs[:, 1])),
                                           shape=(len(p), len(p))).tocsr(), directed=False)[1]


def face_components(p, faces):
    ids = weld(p)
    ff = ids[faces]
    e = np.concatenate([ff[:, [0, 1]], ff[:, [1, 2]]])
    n = ids.max()+1
    return connected_components(coo_matrix((np.ones(len(e)), (e[:, 0], e[:, 1])), shape=(n, n)).tocsr(),
                                directed=False)[1][ff[:, 0]]


def drop_fragments(p, faces, minimum=FRAGMENT_MIN_FACES):
    """Faces without the loose pieces (< minimum faces), and the count dropped.
    fit_tail dropped the same pieces (the male v2 tail has one stray triangle)."""
    label = face_components(p, faces)
    size = np.bincount(label)
    loose = size[label] < minimum
    return faces[~loose], {'fragments': int((size < minimum).sum()), 'fragmentTriangles': int(loose.sum())}


def open_loops(ids, faces):
    """Weld ids of each open boundary loop, largest first."""
    e = np.sort(ids[np.concatenate([faces[:, [0, 1]], faces[:, [1, 2]], faces[:, [2, 0]]])], 1)
    edges, count = np.unique(e, axis=0, return_counts=True)
    edges = edges[count == 1]
    if not len(edges):
        return []
    n = ids.max()+1
    label = connected_components(coo_matrix((np.ones(len(edges)), (edges[:, 0], edges[:, 1])), shape=(n, n)).tocsr(),
                                 directed=False)[1]
    loops = [np.unique(edges[label[edges[:, 0]] == c]) for c in np.unique(label[edges[:, 0]])]
    return sorted(loops, key=len, reverse=True)


def tail_geodesic(p, faces, pelvis):
    """Per-row weld ids, welded positions, geodesic distance (per weld id)
    from the root ring, and the root ring's weld ids. The root ring is the open
    loop (>= 8 vertices) whose centroid is nearest the pelvis joint."""
    p = np.asarray(p, float)
    ids = weld(p)
    n = ids.max()+1
    pw = np.zeros((n, 3)); pw[ids] = p
    ff = ids[faces]
    loops = [loop for loop in open_loops(ids, faces) if len(loop) >= 8]
    if not loops:
        raise ValueError('tail has no open root ring')
    root = min(loops, key=lambda loop: np.linalg.norm(pw[loop].mean(0)-np.asarray(pelvis, float)))
    rows = np.concatenate([ff[:, 0], ff[:, 1], ff[:, 2]])
    cols = np.concatenate([ff[:, 1], ff[:, 2], ff[:, 0]])
    graph = coo_matrix((np.linalg.norm(pw[rows]-pw[cols], axis=1), (rows, cols)), shape=(n, n)).tocsr()
    dist = dijkstra(graph, directed=False, indices=root, min_only=True)
    return ids, pw, dist, root, len(loops)


def centreline(pw, dist, used, bins=CENTRELINE_BINS, sigma=CENTRELINE_SIGMA):
    """Band mids (geodesic distance), smoothed band centroids and the tail's
    geodesic length."""
    d = dist[used]
    length = float(d[np.isfinite(d)].max())
    edges = np.linspace(0, length, bins+1)
    mids = .5*(edges[1:]+edges[:-1])
    q = pw[used]
    centre = []
    for i in range(bins):
        band = (d >= edges[i]) & ((d < edges[i+1]) if i < bins-1 else (d <= edges[i+1]))
        if not band.any():
            raise ValueError(f'centreline band {i} is empty')
        centre.append(q[band].mean(0))
    return mids, gaussian_filter1d(np.array(centre), sigma, axis=0, mode='nearest'), length


def ring_frame(ring):
    """Centroid and unit plane normal (least-variance axis) of the root ring."""
    c = ring.mean(0)
    return c, np.linalg.svd(ring-c)[2][2]


def tangents(curve):
    t = np.gradient(curve, axis=0)
    return t/np.linalg.norm(t, axis=1, keepdims=True)


def rmf(t, first_normal=None):
    """Rotation-minimising normals along unit tangents t (double reflection
    would be overkill at 41 knots; projection is stable here)."""
    ref = np.array([0., 1., 0.]) if first_normal is None else np.asarray(first_normal, float)
    n = np.zeros_like(t)
    n0 = ref-t[0]*(ref@t[0])
    n[0] = n0/np.linalg.norm(n0)
    for i in range(1, len(t)):
        v = n[i-1]-t[i]*(n[i-1]@t[i])
        n[i] = v/np.linalg.norm(v)
    return n


def tail_shape(shape=None):
    """A drape shape: a TAIL_SHAPES name (default TAIL_SHAPE) or a dict;
    returns (name, {'pitch', 'yaw', 'length'})."""
    if shape is None:
        shape = TAIL_SHAPE
    if isinstance(shape, str):
        if shape not in TAIL_SHAPES:
            raise ValueError(f'unknown tail shape {shape!r} (one of {sorted(TAIL_SHAPES)})')
        name, spec = shape, TAIL_SHAPES[shape]
    else:
        name, spec = 'custom', shape
    pitch = tuple((float(u), float(v)) for u, v in spec['pitch'])
    yaw = tuple((float(u), float(v)) for u, v in spec.get('yaw', ((0., 0.), (1., 0.))))
    for knots in (pitch, yaw):
        if knots[0][0] != 0 or knots[-1][0] != 1 or any(b[0] <= a[0] for a, b in zip(knots, knots[1:])):
            raise ValueError(f'shape knots must run 0 -> 1 in increasing arc fraction: {knots}')
    return name, {'pitch': pitch, 'yaw': yaw, 'length': float(spec.get('length', 1.))}


def profile(knots, u):
    """Piecewise smoothstep through (u, value) knots: zero slope at every
    knot, so extremes sit on knots."""
    u = np.clip(np.asarray(u, float), 0, 1)
    out = np.full_like(u, knots[0][1])
    for (u0, v0), (u1, v1) in zip(knots[:-1], knots[1:]):
        t = np.clip((u-u0)/(u1-u0), 0, 1)
        out = np.where(u >= u0, v0+(v1-v0)*t*t*(3-2*t), out)
    return out


def arc_map(a, total, scale, keep=KEEP_ROOT_M, ramp=KEEP_RAMP_M):
    """New arc position and local stretch (d new / d old) of old centreline
    arc `a` for a tail scaled to `scale` of `total`: identity up to `keep`,
    then one factor c past keep + ramp (smoothstep in between), with
    c chosen so that the whole arc maps to scale * total."""
    a = np.asarray(a, float)
    if scale == 1:
        return a.copy(), np.ones_like(a)
    if total <= keep+ramp:
        raise ValueError('tail shorter than its kept root')
    c = 1+(scale-1)*total/(total-keep-ramp/2)
    t = np.clip((a-keep)/ramp, 0, 1)
    integral = np.where(a <= keep+ramp, ramp*(t**3-t**4/2), ramp/2+(a-keep-ramp))
    return a+(c-1)*integral, 1+(c-1)*t*t*(3-2*t)


def shape_curve(length, start, shape, arcs, samples=800):
    """The new centreline at arc positions `arcs` (on a curve of arc length
    `length`): from `start`, pitched below the horizontal (straight back, -z)
    by profile(shape['pitch']) and turned towards +x by profile(shape['yaw'])
    of the arc fraction."""
    s = np.linspace(0, length, samples)
    u = s/length
    th = np.radians(profile(shape['pitch'], u))
    ya = np.radians(profile(shape['yaw'], u))
    direction = np.stack([np.cos(th)*np.sin(ya), -np.sin(th), -np.cos(th)*np.cos(ya)], 1)
    ds = s[1]-s[0]
    pts = np.asarray(start, float)+np.concatenate([[np.zeros(3)], np.cumsum(.5*(direction[1:]+direction[:-1])*ds, 0)])
    return np.array([np.interp(arcs, s, pts[:, k]) for k in range(3)]).T


def _rotation_between(a, b):
    v = np.cross(a, b)
    c = float(a@b)
    if np.linalg.norm(v) < 1e-9:
        return np.eye(3)
    vx = np.array([[0, -v[2], v[1]], [v[2], 0, -v[0]], [-v[1], v[0], 0]])
    return np.eye(3)+vx+vx@vx/(1+c)


def _slerp_dirs(a, b, w):
    """Unit vectors from a (n,3) towards b (n,3) by fraction w (n,)."""
    dot = np.clip((a*b).sum(1), -1, 1)
    th = np.arccos(dot)
    small = th < 1e-6
    sin = np.where(small, 1, np.sin(th))
    out = (np.sin((1-w)*th)/sin)[:, None]*a+(np.sin(w*th)/sin)[:, None]*b
    out[small] = a[small]
    return out/np.linalg.norm(out, axis=1, keepdims=True)


def _frames_at(knots, curve, t, n, s):
    """Centre and orthonormal frame [N B T] (columns) interpolated at s."""
    def interp(a):
        return np.array([np.interp(s, knots, a[:, k]) for k in range(3)]).T
    c, tt, nn = interp(curve), interp(t), interp(n)
    tt /= np.linalg.norm(tt, axis=1, keepdims=True)
    nn -= tt*(nn*tt).sum(1, keepdims=True)
    nn /= np.linalg.norm(nn, axis=1, keepdims=True)
    return c, np.stack([nn, np.cross(tt, nn), tt], 2)


def reemit(p, normals, faces, pelvis, start, shape=None, bins=CENTRELINE_BINS, root_blend=ROOT_BLEND_M):
    """POSITION/NORMAL re-emitted along the shape's curve (per input row; rows
    not used by `faces` are returned unchanged) plus the geometry it was
    built on.

    Knots: the root-ring centroid at s = 0, then the smoothed geodesic-band
    centroids. Near the root the iso-distance slices lie parallel to the
    (oblique) root ring, so the old tangent there is the ring normal, blended
    to the centreline tangent by `root_blend` m; the ring therefore stays
    parallel to the seat (its plane normal goes onto the new root tangent).
    The new curve is sampled at the old centreline's cumulative arc length
    mapped by arc_map (identity for a full-length shape), and each vertex's
    offset along the tangent is stretched by the local arc_map factor
    (cross-sections kept; normals take the inverse stretch)."""
    _, shape = tail_shape(shape)
    p = np.asarray(p, float)
    ids, pw, dist, root, loops = tail_geodesic(p, faces, pelvis)
    used = np.unique(ids[faces])
    if not np.isfinite(dist[used]).all():
        raise ValueError('tail vertices unreachable from the root ring (drop fragments first)')
    mids, bands, length = centreline(pw, dist, used, bins)
    ring_c, ring_n = ring_frame(pw[root])
    if ring_n@(bands[min(2, len(bands)-1)]-ring_c) < 0:
        ring_n = -ring_n
    knots = np.concatenate([[0.], mids])
    old = np.vstack([ring_c, bands])
    arcs = np.concatenate([[0.], np.cumsum(np.linalg.norm(np.diff(old, axis=0), axis=1))])
    total = float(arcs[-1]+(length-mids[-1]))
    new_arcs, _ = arc_map(arcs, total, shape['length'])
    new_total = float(arc_map([total], total, shape['length'])[0][0])
    new = shape_curve(new_total, start, shape, new_arcs)
    u = np.clip(knots/root_blend, 0, 1)
    t_old = _slerp_dirs(np.tile(ring_n, (len(knots), 1)), tangents(old), u*u*(3-2*u))
    n_old = rmf(t_old)
    t_new = tangents(new)
    n_new = rmf(t_new, _rotation_between(t_old[0], t_new[0])@n_old[0])
    rows = np.unique(faces)
    s = dist[ids[rows]]
    c0, f0 = _frames_at(knots, old, t_old, n_old, s)
    c1, f1 = _frames_at(knots, new, t_new, n_new, s)
    _, stretch = arc_map(np.interp(s, knots, arcs), total, shape['length'])
    local = np.einsum('nji,nj->ni', f0, p[rows]-c0)    # F0^T (p - c0): [N, B, T] offsets
    local[:, 2] *= stretch
    out_p, out_n = p.copy(), np.asarray(normals, float).copy()
    out_p[rows] = c1+np.einsum('nij,nj->ni', f1, local)
    ln = np.einsum('nji,nj->ni', f0, out_n[rows])
    ln[:, 2] /= stretch
    rn = np.einsum('nij,nj->ni', f1, ln)
    out_n[rows] = rn/np.maximum(np.linalg.norm(rn, axis=1, keepdims=True), 1e-12)
    geometry = {'ids': ids, 'dist': dist, 'root': root, 'openLoops': loops, 'knots': knots, 'arcs': arcs,
                'newArcs': new_arcs, 'oldCentreline': old, 'newCentreline': new, 'length': length,
                'centrelineArcM': total, 'newCentrelineArcM': new_total, 'shape': shape,
                'ringNormal': ring_n, 'ringObliquityDegrees': float(np.degrees(np.arccos(np.clip(ring_n@tangents(old)[min(3, len(old)-1)], -1, 1))))}
    return out_p, out_n, geometry


def arc_length(pw, dist, used, root, bins=CENTRELINE_BINS):
    """Length of the polyline root-ring centroid -> smoothed band centroids
    (the measure the +-1% gate compares before and after)."""
    _, c, _ = centreline(pw, dist, used, bins)
    knots = np.vstack([pw[root].mean(0), c])
    return float(np.linalg.norm(np.diff(knots, axis=0), axis=1).sum())


def winding(points, tris, chunk=128):
    """Generalised winding number of each point against a triangle soup."""
    points, tris = np.asarray(points, float), np.asarray(tris, float)
    out = np.zeros(len(points))
    for s in range(0, len(points), chunk):
        q = points[s:s+chunk]
        a, b, c = (tris[None, :, i]-q[:, None] for i in range(3))
        la, lb, lc = (np.linalg.norm(v, axis=2) for v in (a, b, c))
        num = np.einsum('ijk,ijk->ij', a, np.cross(b, c))
        den = (la*lb*lc+np.einsum('ijk,ijk->ij', a, b)*lc+np.einsum('ijk,ijk->ij', b, c)*la
               + np.einsum('ijk,ijk->ij', c, a)*lb)
        out[s:s+chunk] = np.arctan2(num, den).sum(1)/(2*np.pi)
    return out


def surface_depth(points, tris):
    """Signed depth inside a closed triangle soup (positive inside: winding
    > .5) and the closest surface points."""
    import trimesh
    mesh = trimesh.Trimesh(np.asarray(tris, float).reshape(-1, 3), np.arange(np.asarray(tris).size//3).reshape(-1, 3),
                           process=False)
    closest, distance, _ = trimesh.proximity.closest_point(mesh, np.asarray(points, float))
    inside = winding(points, tris) > .5
    return np.where(inside, distance, -distance), closest


def _vertex_normals(p, faces, ids):
    q = np.cross(p[faces[:, 1]]-p[faces[:, 0]], p[faces[:, 2]]-p[faces[:, 0]])
    total = np.zeros((ids.max()+1, 3))
    for c in range(3):
        np.add.at(total, ids[faces[:, c]], q)
    return total[ids]/np.maximum(np.linalg.norm(total[ids], axis=1, keepdims=True), 1e-12)


def sink_root(p, normals, faces, geo, surface_tris, depth=SINK_DEPTH_M, falloff=SINK_FALLOFF_M):
    """Push root-ring rows shallower than `depth` (or outside) to `depth`
    inside the Human surface (rows the push leaves in a fold are pulled
    towards the ring centre until they are that deep), fading the push over
    `falloff` m of geodesic arc; normals follow the change of the geometric
    vertex normals."""
    p = np.asarray(p, float).copy()
    normals = np.asarray(normals, float).copy()
    ids, dist = geo['ids'], geo['dist']
    ring = np.flatnonzero(np.isin(ids, geo['root']))
    d0, closest = surface_depth(p[ring], surface_tris)
    outward = np.where((d0 > 0)[:, None], closest-p[ring], p[ring]-closest)
    outward /= np.maximum(np.linalg.norm(outward, axis=1, keepdims=True), 1e-12)
    move = np.where((d0 < depth)[:, None], closest-outward*depth-p[ring], 0.)
    pushed, _ = surface_depth(p[ring]+move, surface_tris)
    shallow = np.flatnonzero(pushed < depth*SINK_PULL_BELOW)
    pulled = len(shallow)
    if pulled:
        _, first = np.unique(ids[ring], return_index=True)
        centre = p[ring][first].mean(0)
        start = p[ring][shallow]+move[shallow]
        for f in np.linspace(0, 1, SINK_PULL_STEPS+1)[1:]:
            q = start+f*(centre-start)
            dq, _ = surface_depth(q, surface_tris)
            ok = dq >= depth
            move[shallow[ok]] = q[ok]-p[ring][shallow[ok]]
            shallow, start = shallow[~ok], start[~ok]
            if not len(shallow):
                break
    rows = np.unique(faces)
    s = dist[ids[rows]]
    near = rows[s < falloff]
    shift = np.zeros_like(p)
    if (np.linalg.norm(move, axis=1) > 0).any():
        moving = np.linalg.norm(move, axis=1) > 0
        k = min(8, int(moving.sum()))
        distance, nearest = cKDTree(p[ring][moving]).query(p[near], k=k)
        distance, nearest = distance.reshape(len(near), k), nearest.reshape(len(near), k)
        w = 1/np.maximum(distance, 1e-9)**4
        field = (w[..., None]*move[moving][nearest]).sum(1)/w.sum(1, keepdims=True)
        u = np.clip(dist[ids[near]]/falloff, 0, 1)
        shift[near] = field*(1-u*u*(3-2*u))[:, None]
        shift[ring] = move
    p1 = p+shift
    moved = np.linalg.norm(shift, axis=1) > 1e-9
    if moved.any():
        before, after = _vertex_normals(p, faces, ids), _vertex_normals(p1, faces, ids)
        normals[moved] += after[moved]-before[moved]
        normals[moved] /= np.maximum(np.linalg.norm(normals[moved], axis=1, keepdims=True), 1e-12)
    d1, _ = surface_depth(p1[ring], surface_tris)
    return p1, normals, {'targetDepthM': depth, 'falloffM': falloff, 'ringRows': int(len(ring)),
                         'pushedRingRows': int((np.linalg.norm(move, axis=1) > 0).sum()),
                         'pulledRingRows': int(pulled-len(shallow)), 'unresolvedRingRows': int(len(shallow)),
                         'maxShiftM': float(np.linalg.norm(shift, axis=1).max()), 'movedRows': int(moved.sum()),
                         'ringDepthBeforeM': [float(d0.min()), float(np.median(d0))],
                         'ringDepthAfterM': [float(d1.min()), float(np.median(d1))]}


# ---------------------------------------------------------------------------
# Weights
# ---------------------------------------------------------------------------

def dense(joints, weights, width):
    out = np.zeros((len(joints), width))
    for col in range(joints.shape[1]):
        np.add.at(out, (np.arange(len(out)), joints[:, col].astype(int)), weights[:, col].astype(float))
    return out


def sparse(w, limit=4):
    j = np.argsort(-w, axis=1, kind='stable')[:, :limit]
    v = np.take_along_axis(w, j, axis=1)
    v /= np.maximum(v.sum(1, keepdims=True), 1e-12)
    return j, v


def seat_weights(points, trouser, width, k=RESEAT_NEIGHBOURS):
    """Dense weights copied from the trousers at each point: inverse-square
    distance mix of the k nearest wardrobe_pants rows."""
    tp = np.asarray(trouser['POSITION'], float)
    td = dense(trouser['JOINTS_0'], trouser['WEIGHTS_0'], width)
    distance, nearest = cKDTree(tp).query(points, k=k)
    w = 1/np.maximum(distance, 1e-6)**2
    w /= w.sum(1, keepdims=True)
    return np.einsum('nk,nkj->nj', w, td[nearest])


def feather_weights(s, seat, pelvis_index, feather=FEATHER_M):
    """Seat weights at the root, pure pelvis from `feather` metres of arc."""
    u = np.clip(np.asarray(s, float)/feather, 0, 1)
    u = (u*u*(3-2*u))[:, None]
    pure = np.zeros_like(seat)
    pure[:, pelvis_index] = 1
    return (1-u)*seat+u*pure


# ---------------------------------------------------------------------------
# The re-root
# ---------------------------------------------------------------------------

def reroot_tail(tail, trouser, joints, names, slug=None, sacrum=None, shape=None,
                feather=FEATHER_M, bins=CENTRELINE_BINS, surface_tris=None):
    """Re-root a race_tail primitive at the sacrum.

    tail:    {'POSITION','NORMAL','TEXCOORD_0','JOINTS_0','WEIGHTS_0': rows, 'faces': (n,3)}
             in rest/world space (the v2 tail; fragments may still be present)
    trouser: {'POSITION','JOINTS_0','WEIGHTS_0': rows} of wardrobe_pants (the
             Human trousers the root sits in), joint indices into `names`
    joints:  {name: rest world position (3,)} (needs 'pelvis')
    names:   skin joint names (77)
    surface_tris: (n,3,3) closed Human below-neck surface (rebase_race_body
             human_surface(lower)); when given, the root ring is sunk to
             SINK_DEPTH_M inside it (sink_root)
    shape:   a TAIL_SHAPES name or dict (default TAIL_SHAPE)
    Returns {'POSITION','NORMAL','JOINTS_0','WEIGHTS_0' (input row count and
    dtypes; TEXCOORD_0 untouched), 'faces' (fragments dropped), 'report',
    'geometry'} (geometry['featherArc']: per-row geodesic distance from the
    root ring on the new positions, the s the feather and the clip gates use)."""
    if sacrum is None:
        if slug not in SACRUM:
            raise ValueError(f'no sacrum for {slug}; pass sacrum=')
        sacrum = SACRUM[slug]
    p0 = np.asarray(tail['POSITION'], float)
    faces, fragments = drop_fragments(p0, np.asarray(tail['faces'], int))
    pelvis = np.asarray(joints['pelvis'], float)
    shape_name, shape = tail_shape(shape)
    p1, n1, geo = reemit(p0, tail['NORMAL'], faces, pelvis, sacrum, shape, bins)
    sink = None
    if surface_tris is not None:
        p1, n1, sink = sink_root(p1, n1, faces, geo, surface_tris)
    rows = np.unique(faces)
    # The feather runs along the re-emitted tail: geodesic distance from the
    # root ring on the new positions (the curled v2 tail's distances are up to
    # 13% shorter).
    ids_new, _, dist_new, _, _ = tail_geodesic(p1, faces, pelvis)
    s = dist_new[ids_new]
    geo['featherArc'] = s
    width = len(names)
    seat = seat_weights(p1[rows], trouser, width)
    blended = feather_weights(s[rows], seat, names.index('pelvis'), feather)
    j, w = sparse(blended)
    out_j = np.asarray(tail['JOINTS_0']).copy()
    out_w = np.asarray(tail['WEIGHTS_0']).copy()
    if j.max() > np.iinfo(out_j.dtype).max:
        raise ValueError('joint index does not fit the tail JOINTS_0 type')
    out_j[rows] = j.astype(out_j.dtype)
    out_w[rows] = w.astype(out_w.dtype)
    ids, dist = geo['ids'], geo['dist']
    used = np.unique(ids[faces])
    pw1 = np.zeros((ids.max()+1, 3)); pw1[ids] = p1
    pw0 = np.zeros((ids.max()+1, 3)); pw0[ids] = p0
    root_rows = np.flatnonzero(np.isin(ids, geo['root']))
    thighs = [names.index('thigh_l'), names.index('thigh_r')]
    final = dense(out_j[rows], out_w[rows], width)
    seat_mean = seat[s[rows] < .02].mean(0) if (s[rows] < .02).any() else seat.mean(0)
    report = {
        'slug': slug, 'sacrumM': [float(x) for x in sacrum],
        'shape': {'name': shape_name, 'pitchDegrees': [list(k) for k in shape['pitch']],
                  'yawDegrees': [list(k) for k in shape['yaw']], 'length': shape['length']},
        'featherM': feather, 'centrelineBins': bins,
        'triangles': int(len(faces)), 'trianglesBefore': int(len(tail['faces'])), **fragments,
        'openLoops': geo['openLoops'], 'rootLoopVertices': int(len(geo['root'])),
        'lengthGeodesicM': geo['length'],
        'ringObliquityDegrees': geo['ringObliquityDegrees'], 'rootBlendM': ROOT_BLEND_M,
        'arcLengthM': {'before': arc_length(pw0, dist, used, geo['root'], bins), 'after': arc_length(pw1, dist, used, geo['root'], bins)},
        'rootCentre': {'before': pw0[geo['root']].mean(0).tolist(), 'after': pw1[geo['root']].mean(0).tolist()},
        'tip': {'before': pw0[used][np.argmax(dist[used])].tolist(), 'after': pw1[used][np.argmax(dist[used])].tolist()},
        'boundsAfter': [p1[rows].min(0).tolist(), p1[rows].max(0).tolist()],
        'weights': {
            'seatAtRoot': {names[k]: float(seat_mean[k]) for k in np.argsort(-seat_mean)[:4] if seat_mean[k] > 1e-4},
            'thighShareMax': float(final[:, thighs].sum(1).max()),
            'thighShareMaxBeyondFeather': float(final[s[rows] >= feather][:, thighs].sum(1).max(initial=0)),
            'pelvisMinBeyondFeather': float(final[s[rows] >= feather, names.index('pelvis')].min(initial=1)),
            'rule': f'seat (inverse-square mix of the {RESEAT_NEIGHBOURS} nearest wardrobe_pants rows) at the root, '
                    f'smoothstep to pure pelvis by {feather} m of geodesic arc from the root ring (re-emitted tail)'},
        'normalsRule': 'input normal turned by the frame rotation (old centreline RMF -> new), per vertex; '
                       'the tangent component divided by the arc stretch of a shortened shape',
        'unchanged': ['TEXCOORD_0', 'faces (after fragment drop)', 'image'],
    }
    report['arcLengthM']['ratio'] = report['arcLengthM']['after']/report['arcLengthM']['before']
    report['rootRows'] = int(len(root_rows))
    if sink:
        report['rootSink'] = sink
    return {'POSITION': p1.astype(np.asarray(tail['POSITION']).dtype),
            'NORMAL': n1.astype(np.asarray(tail['NORMAL']).dtype),
            'JOINTS_0': out_j, 'WEIGHTS_0': out_w, 'faces': faces, 'report': report, 'geometry': geo}


def tail_capsule(result, pelvis_world, length=CAPSULE_LENGTH_M, margin=CAPSULE_MARGIN_M, start=CAPSULE_START_M):
    """Pelvis-local capsule along the first `length` m (centreline arc) of the
    re-rooted tail, for a cape solver (models.json tailCollision):
    {'bone','from','to','radius','lengthM'}. The radius is the 95th
    percentile radial distance of the tail vertices between `start` m (about
    where it leaves the seat) and `length`, plus `margin`; the flared root
    inside the seat is not counted. `pelvis_world` is the pelvis rest world
    matrix (inverse of its IBM)."""
    geo = result['geometry']
    p = np.asarray(result['POSITION'], float)
    s_row = geo['dist'][geo['ids']]
    knots, arcs, curve = geo['knots'], geo['newArcs'], geo['newCentreline']
    a = curve[0]
    b = np.array([np.interp(length, arcs, curve[:, k]) for k in range(3)])
    s_end = float(np.interp(length, arcs, knots))
    rows = np.unique(result['faces'])
    sel = rows[(s_row[rows] >= start) & (s_row[rows] <= s_end)]
    ab = b-a
    t = np.clip((p[sel]-a)@ab/(ab@ab), 0, 1)
    radial = np.linalg.norm(p[sel]-(a+t[:, None]*ab), axis=1)
    radius = float(np.percentile(radial, 95))+margin
    inv = np.linalg.inv(np.asarray(pelvis_world, float))
    local = [(inv@np.append(x, 1.))[:3] for x in (a, b)]
    return {'bone': 'pelvis', 'from': [round(float(v), 5) for v in local[0]],
            'to': [round(float(v), 5) for v in local[1]], 'radius': round(radius, 4), 'lengthM': length,
            'radialMaxM': round(float(radial.max()), 4), 'worldRest': {'from': a.tolist(), 'to': b.tolist()}}


def rest_checks(result, body_surface_tris):
    """Rest-pose numbers for the rewritten V18: root-ring depth inside the
    Human surface (winding > .5 = inside), the welded root-ring centroid's x,
    the arc ratio, and where the tail emerges (first geodesic distance from the
    root ring with a vertex outside the surface)."""
    p = np.asarray(result['POSITION'], float)
    geo = result['geometry']
    ids, dist = geo['ids'], geo['dist']
    rows = np.flatnonzero(np.isin(ids, geo['root']))
    depth, _ = surface_depth(p[rows], body_surface_tris)
    used = np.unique(result['faces'])
    near = used[dist[ids[used]] < .2]
    inside = winding(p[near], body_surface_tris) > .5
    s = dist[ids[near]]
    emerge = float(s[~inside].min()) if (~inside).any() else None
    last_inside = float(s[inside].max()) if inside.any() else None
    welded = np.zeros((ids.max()+1, 3)); welded[ids] = p
    return {'rootCentreX': float(welded[geo['root']].mean(0)[0]), 'rootDepthM': {'min': float(depth.min()), 'median': float(np.median(depth)),
                                                                      'max': float(depth.max())},
            'rootAllInside': bool((depth > 0).all()),
            'emergesAtArcM': emerge, 'lastInsideArcM': last_inside,
            'arcLengthRatio': result['report']['arcLengthM']['ratio']}


# ---------------------------------------------------------------------------
# Offline clip evaluation (NativeAnimationImporter semantics)
# ---------------------------------------------------------------------------

def quat_to_mat(q):
    x, y, z, w = q
    return np.array([[1-2*(y*y+z*z), 2*(x*y-z*w), 2*(x*z+y*w)],
                     [2*(x*y+z*w), 1-2*(x*x+z*z), 2*(y*z-x*w)],
                     [2*(x*z-y*w), 2*(y*z+x*w), 1-2*(x*x+y*y)]])


def _trs(t, r, s):
    m = np.eye(4)
    m[:3, :3] = quat_to_mat(r)*np.asarray(s, float)
    m[:3, 3] = t
    return m


def _node_trs(node):
    if 'matrix' in node:
        m = np.asarray(node['matrix'], float).reshape(4, 4).T
        s = np.linalg.norm(m[:3, :3], axis=0)
        r = m[:3, :3]/s
        from scipy.spatial.transform import Rotation
        return m[:3, 3].copy(), Rotation.from_matrix(r).as_quat(), s
    return (np.array(node.get('translation', [0, 0, 0]), float), np.array(node.get('rotation', [0, 0, 0, 1]), float),
            np.array(node.get('scale', [1, 1, 1]), float))


class ClipLibrary:
    """Tracks of a glTF animation library by bone name (one parse)."""

    def __init__(self, path):
        d, b = ea.read_glb(Path(path))
        self.path = str(path)
        names = [n.get('name') for n in d['nodes']]
        self.clips = {}
        for a in d['animations']:
            channels = {}
            for c in a['channels']:
                node = c['target'].get('node')
                kind = c['target']['path']
                if node is None or kind not in ('translation', 'rotation', 'scale'):
                    continue
                s = a['samplers'][c['sampler']]
                t = ea.accessor_array(d, b, s['input']).astype(float).ravel()
                v = ea.accessor_array(d, b, s['output']).astype(float)
                mode = s.get('interpolation', 'LINEAR')
                if mode == 'CUBICSPLINE':
                    v = v.reshape(len(t), 3, -1)[:, 1]
                    mode = 'LINEAR'
                channels.setdefault(names[node], {})[kind] = (t, v, mode)
            self.clips[a['name']] = channels

    def duration(self, clip):
        return max(t[-1] for tracks in self.clips[clip].values() for t, _, _ in tracks.values())

    def sample(self, clip, time):
        """{bone: {'translation'|'rotation'|'scale': value}} at `time`."""
        out = {}
        for bone, tracks in self.clips[clip].items():
            values = {}
            for kind, (t, v, mode) in tracks.items():
                k = int(np.searchsorted(t, time, side='right'))
                if k <= 0:
                    val = v[0]
                elif k >= len(t):
                    val = v[-1]
                elif mode == 'STEP':
                    val = v[k-1]
                else:
                    a = (time-t[k-1])/max(t[k]-t[k-1], 1e-9)
                    if kind == 'rotation':
                        q0, q1 = v[k-1], v[k]
                        if q0@q1 < 0:
                            q1 = -q1
                        val = _slerp(q0, q1, a)
                    else:
                        val = v[k-1]*(1-a)+v[k]*a
                values[kind] = val
            out[bone] = values
        return out

    def times(self, clip, fps=SAMPLE_FPS):
        return np.arange(0, self.duration(clip)+1e-6, 1/fps)


def _slerp(q0, q1, a):
    dot = float(np.clip(q0@q1, -1, 1))
    if dot > .9995:
        q = q0+(q1-q0)*a
        return q/np.linalg.norm(q)
    th = np.arccos(dot)
    return (np.sin((1-a)*th)*q0+np.sin(a*th)*q1)/np.sin(th)


class BodyRig:
    """The body's skeleton: rest TRS per joint, parents, IBMs; `pose` applies
    library tracks by bone name (aliases as models.json boneAliases), keeping
    untracked channels at the body's rest, as the client's retarget does."""

    def __init__(self, d, b, aliases=None):
        skin = d['skins'][0]
        self.joint_nodes = list(skin['joints'])
        self.names = [d['nodes'][j]['name'] for j in self.joint_nodes]
        parent = {c: i for i, n in enumerate(d['nodes']) for c in n.get('children', [])}
        world = ea.global_matrices(d)
        index = {node: k for k, node in enumerate(self.joint_nodes)}
        self.parent = [index.get(parent.get(node, -1), -1) for node in self.joint_nodes]
        # Non-joint ancestors are fixed (BodyRoot is identity on the race GLBs).
        self.base = [world[parent[node]] if (parent.get(node) is not None and self.parent[k] < 0) else np.eye(4)
                     for k, node in enumerate(self.joint_nodes)]
        self.rest = [_node_trs(d['nodes'][node]) for node in self.joint_nodes]
        ibm = ea.accessor_array(d, b, skin['inverseBindMatrices']).astype(float).reshape(-1, 4, 4).transpose(0, 2, 1)
        self.ibm = ibm
        self.order = self._order()
        alias = dict(DEFAULT_ALIASES if aliases is None else aliases)
        self.lookup = {name: alias.get(name, name) for name in set(alias)}
        self.rest_world = self.pose({})

    def _order(self):
        order, seen = [], set()

        def visit(k):
            if k in seen:
                return
            if self.parent[k] >= 0:
                visit(self.parent[k])
            seen.add(k)
            order.append(k)
        for k in range(len(self.names)):
            visit(k)
        return order

    def pose(self, tracks):
        """World matrices (n, 4, 4) of every skin joint for sampled tracks
        ({library bone: {kind: value}})."""
        by_name = {}
        for bone, values in tracks.items():
            by_name[self.lookup.get(bone, bone)] = values
        world = np.zeros((len(self.names), 4, 4))
        for k in self.order:
            t, r, s = self.rest[k]
            v = by_name.get(self.names[k])
            if v:
                t = v.get('translation', t)
                r = v.get('rotation', r)
                s = v.get('scale', s)
            local = _trs(t, r, s)
            world[k] = (world[self.parent[k]] if self.parent[k] >= 0 else self.base[k])@local
        return world

    def skin_matrices(self, world, names=None, ibm=None):
        """Per-joint skinning matrices for a mesh whose skin lists `names`
        (default: the body's own joints) with its own IBMs."""
        if names is None:
            return world@self.ibm
        idx = [self.names.index(n) for n in names]
        return world[idx]@np.asarray(ibm, float)


def skin(points, joints, weights, mats):
    """Linear blend skinning of rest points (n,3)."""
    p = np.concatenate([np.asarray(points, float), np.ones((len(points), 1))], 1)
    out = np.zeros((len(p), 3))
    w = np.asarray(weights, float)
    j = np.asarray(joints, int)
    for col in range(j.shape[1]):
        m = mats[j[:, col]]
        out += w[:, col, None]*np.einsum('nij,nj->ni', m, p)[:, :3]
    return out


def skinned_pieces(path, include=None):
    """Skinned mesh primitives of an equipment/body GLB:
    [{'node','POSITION','NORMAL','JOINTS_0','WEIGHTS_0','faces','names','ibm'}]."""
    d, b = ea.read_glb(Path(path))
    out = []
    for n in d['nodes']:
        if 'mesh' not in n or n.get('skin') is None:
            continue
        if include is not None and n['name'] not in include:
            continue
        skin_ = d['skins'][n['skin']]
        names = [d['nodes'][j]['name'] for j in skin_['joints']]
        ibm = ea.accessor_array(d, b, skin_['inverseBindMatrices']).astype(float).reshape(-1, 4, 4).transpose(0, 2, 1)
        for prim in d['meshes'][n['mesh']]['primitives']:
            a = prim['attributes']
            out.append({'node': n['name'], 'material': d['materials'][prim['material']].get('name') if 'material' in prim else None,
                        'POSITION': ea.accessor_array(d, b, a['POSITION']).astype(float),
                        'NORMAL': ea.accessor_array(d, b, a['NORMAL']).astype(float),
                        'JOINTS_0': ea.accessor_array(d, b, a['JOINTS_0']).astype(int),
                        'WEIGHTS_0': ea.accessor_array(d, b, a['WEIGHTS_0']).astype(float),
                        'faces': ea.accessor_array(d, b, prim['indices']).astype(int).reshape(-1, 3),
                        'names': names, 'ibm': ibm})
    return out


def kit_scene(root, slug, key, equipment=None):
    """Scene file the runtime picks for equipment model `key` ('4:220') on
    `slug`: the first fitGroups variant present, else the model scene."""
    root = Path(root)
    if equipment is None:
        equipment = json.loads((root/'godot-client/data/actors/equipment.json').read_text(encoding='utf-8'))
    model = equipment['models'][key]
    scene = model['scene']
    for group in equipment.get('fitGroups', {}).get(slug, []):
        if group in model.get('variants', {}):
            scene = model['variants'][group]['scene']
            break
    return root/'godot-client'/scene.replace('res://', '')


def segment_crossings(a, b, tris, eps=1e-9):
    """Indices of segments (a[i] -> b[i]) that cross any triangle (Moller-Trumbore)."""
    if not len(tris) or not len(a):
        return np.zeros(len(a), bool)
    v0, e1, e2 = tris[:, 0], tris[:, 1]-tris[:, 0], tris[:, 2]-tris[:, 0]
    lo_t, hi_t = tris.min(1), tris.max(1)
    hit = np.zeros(len(a), bool)
    for i in range(len(a)):
        lo, hi = np.minimum(a[i], b[i]), np.maximum(a[i], b[i])
        box = np.flatnonzero(((hi_t >= lo) & (lo_t <= hi)).all(1))
        if not len(box):
            continue
        d = b[i]-a[i]
        h = np.cross(d, e2[box])
        det = (e1[box]*h).sum(1)
        ok = np.abs(det) > eps
        inv = np.where(ok, 1/np.where(ok, det, 1), 0)
        s = a[i]-v0[box]
        u = (s*h).sum(1)*inv
        q = np.cross(s, e1[box])
        v = (q@d)*inv
        t = (e2[box]*q).sum(1)*inv
        hit[i] = bool((ok & (u >= 0) & (v >= 0) & (u+v <= 1) & (t >= 0) & (t <= 1)).any())
    return hit


def _leg_clearance(q, world, names):
    worst = np.inf
    for side in 'lr':
        for a_name, b_name, r in LEG_CAPSULES:
            a = world[names.index(f'{a_name}_{side}')][:3, 3]
            b = world[names.index(f'{b_name}_{side}')][:3, 3]
            ab = b-a
            t = np.clip((q-a)@ab/max(ab@ab, 1e-12), 0, 1)
            worst = min(worst, float((np.linalg.norm(q-(a+t[:, None]*ab), axis=1)-r).min()))
    return worst


def action_clips(root, library, animation_map=None):
    """Library clips the actor can play: the action map's clips plus the
    CombatAnimationLibrary recipe sources (Combat_* are re-timed sources)."""
    root = Path(root)
    path = Path(animation_map) if animation_map else root/'godot-client/data/animations/luminous.json'
    actions = json.loads(path.read_text(encoding='utf-8'))['actions']
    recipes = {'Combat_Channel_Enter': ['Spell_Simple_Enter'], 'Combat_Channel': ['Spell_Simple_Idle'],
               'Combat_Cast_Aggressive': ['Spell_Simple_Enter', 'Two-hand_Blast', 'Spell_Simple_Exit'],
               'Combat_Cast_Defensive': ['Defend'], 'Combat_Heal': ['Spell_Simple_Enter', 'Spell_Simple_Idle', 'Spell_Simple_Exit'],
               'Combat_Slash_A': ['Sword_Regular_A', 'Sword_Regular_A_Rec'], 'Combat_Slash_B': ['Sword_Regular_B', 'Sword_Regular_B_Rec'],
               'Combat_Bow_Draw': ['Bow_Pull_Back'], 'Combat_Bow_Hold': ['Bow_Pull_Hold'], 'Combat_Bow_Release': ['Bow_Release']}
    out = []
    for clip in actions.values():
        for name in recipes.get(clip, [clip]):
            if name in library.clips and name not in out:
                out.append(name)
    return out


def clip_clearance(rig, library, tail, s, clips, slug=None, pieces=None, fps=SAMPLE_FPS, root_band=ROOT_BAND_M,
                   centre_bins=None):
    """Per clip: leg-capsule clearance of the skinned tail beyond `root_band`,
    the tail's lowest point, its highest point above the pelvis joint, the
    tip's height range (rows within TIP_BAND_M of the tip), and per piece the
    tail-centreline crossings (arc distances) and the tail-vertex clearance
    beyond the root band.

    tail:   {'POSITION','JOINTS_0','WEIGHTS_0', 'faces'} rest arrays (body joints)
    s:      geodesic arc distance per tail row (from reroot_tail geometry)
    pieces: {label: [skinned_pieces() entries]} (optional)"""
    rows = np.unique(tail['faces'])
    p = np.asarray(tail['POSITION'], float)[rows]
    jj = np.asarray(tail['JOINTS_0'], int)[rows]
    ww = np.asarray(tail['WEIGHTS_0'], float)[rows]
    sr = np.asarray(s, float)[rows]
    free = sr >= root_band
    length = float(sr.max())
    tip = sr >= length-TIP_BAND_M
    pelvis = rig.names.index('pelvis')
    nb = centre_bins or CENTRELINE_BINS
    band = np.minimum((sr/length*nb).astype(int), nb-1)
    band_s = (np.arange(nb)+.5)*length/nb
    prepared = {}
    for label, items in (pieces or {}).items():
        prepared[label] = items
    results = {}
    for clip in clips:
        worst_leg, worst_t, ymin, ymin_t = np.inf, None, np.inf, None
        foot, rise, tip_lo, tip_hi = np.inf, -np.inf, np.inf, -np.inf
        per_piece = {label: {'crossArcM': [], 'framesCrossing': 0, 'minClearanceM': np.inf, 'crossingsBeyond': 0}
                     for label in prepared}
        for time in library.times(clip, fps):
            world = rig.pose(library.sample(clip, time))
            mats = world@rig.ibm
            q = skin(p, jj, ww, mats)
            leg = _leg_clearance(q[free], world, rig.names)
            if leg < worst_leg:
                worst_leg, worst_t = leg, float(time)
            y = float(q[:, 1].min())
            if y < ymin:
                ymin, ymin_t = y, float(time)
            foot = min(foot, min(float(world[rig.names.index(n)][1, 3]) for n in ('foot_l', 'foot_r', 'ball_l', 'ball_r')))
            rise = max(rise, float(q[:, 1].max()-world[pelvis][1, 3]))
            tip_y = float(q[tip, 1].min())
            tip_lo, tip_hi = min(tip_lo, tip_y), max(tip_hi, tip_y)
            if not prepared:
                continue
            centre = np.array([q[band == k].mean(0) for k in range(nb)])
            for label, items in prepared.items():
                rec = per_piece[label]
                tri_sets, verts = [], []
                for it in items:
                    m = rig.skin_matrices(world, it['names'], it['ibm'])
                    pq = skin(it['POSITION'], it['JOINTS_0'], it['WEIGHTS_0'], m)
                    tri_sets.append(pq[it['faces']])
                    verts.append(np.concatenate([pq, pq[it['faces']].mean(1)]))
                tris = np.concatenate(tri_sets)
                hit = segment_crossings(centre[:-1], centre[1:], tris)
                if hit.any():
                    arcs = (.5*(band_s[:-1]+band_s[1:]))[hit]
                    rec['framesCrossing'] += 1
                    rec['crossArcM'].extend(arcs.tolist())
                    rec['crossingsBeyond'] += int((arcs >= root_band).sum())
                dmin, _ = cKDTree(np.concatenate(verts)).query(q[free])
                rec['minClearanceM'] = min(rec['minClearanceM'], float(dmin.min()))
        entry = {'legClearanceM': worst_leg, 'legClearanceAtS': worst_t, 'minTailY': ymin, 'minTailYAtS': ymin_t,
                 'minFootJointY': foot, 'maxTailAbovePelvisM': rise, 'tipYM': [tip_lo, tip_hi],
                 'frames': int(len(library.times(clip, fps)))}
        if prepared:
            entry['pieces'] = {label: {'framesCrossing': rec['framesCrossing'],
                                       'crossArcM': [round(min(rec['crossArcM']), 3), round(max(rec['crossArcM']), 3)] if rec['crossArcM'] else None,
                                       'crossingsBeyondRootBand': rec['crossingsBeyond'],
                                       'minClearanceBeyondRootBandM': rec['minClearanceM']}
                               for label, rec in per_piece.items()}
        results[clip] = entry
    return results


def clip_gates(results, slug):
    """V18 clip gates on clip_clearance output: in every clip of `results`
    leg clearance (LEG_CLEARANCE_MIN_M), lowest tail point (FLOOR_MIN_M) and
    rise above the pelvis (RISE_MAX_M), each at the design limit unless
    TAIL_CLIP_WAIVERS waives that clip; leg clearance and floor in
    LOCOMOTION_CLIPS at the locomotion limits. A locomotion or waived clip
    missing from `results` fails."""
    need = LEG_CLEARANCE_MIN_M.get(slug, min(LEG_CLEARANCE_MIN_M.values()))
    loco_need = LOCOMOTION_LEG_MIN_M.get(slug, min(LOCOMOTION_LEG_MIN_M.values()))
    waivers = TAIL_CLIP_WAIVERS.get(slug, {})

    def limit(clip, key, design):
        return waivers.get(clip, {}).get(key, design)
    legs = {c: r['legClearanceM'] for c, r in results.items() if c not in LOCOMOTION_CLIPS}
    loco = {c: results[c]['legClearanceM'] for c in LOCOMOTION_CLIPS if c in results}
    loco_floor = {c: results[c]['minTailY'] for c in LOCOMOTION_CLIPS if c in results}
    floor = {c: r['minTailY'] for c, r in results.items()}
    rise = {c: r['maxTailAbovePelvisM'] for c, r in results.items()}
    missing = sorted(c for c in (*LOCOMOTION_CLIPS, *waivers) if c not in results)
    worst_leg = min(legs, key=legs.get) if legs else None
    waived = {c: {k: {'limit': v, 'achieved': {'legM': legs, 'floorM': floor, 'riseM': rise}[k].get(c)}
                  for k, v in w.items()} for c, w in waivers.items()}
    gates = {'legClearanceMinM': need, 'worstLegClip': worst_leg, 'worstLegClearanceM': legs.get(worst_leg),
             'legFailures': sorted(c for c, v in legs.items() if v < limit(c, 'legM', need)),
             'locomotionLegMinM': loco_need, 'locomotionLegM': loco,
             'locomotionLegFailures': sorted(c for c, v in loco.items() if v < loco_need),
             'locomotionFloorMinM': LOCOMOTION_FLOOR_MIN_M, 'locomotionFloor': loco_floor,
             'locomotionFloorFailures': sorted(c for c, v in loco_floor.items() if v < LOCOMOTION_FLOOR_MIN_M),
             'floorMinM': FLOOR_MIN_M, 'floorFailures': sorted(c for c, v in floor.items() if v < limit(c, 'floorM', FLOOR_MIN_M)),
             'riseMaxM': RISE_MAX_M, 'riseFailures': sorted(c for c, v in rise.items() if v > limit(c, 'riseM', RISE_MAX_M)),
             'waivers': waived, 'waiversPending': 'the lead tail call (TAIL_CLIP_WAIVERS)',
             'clipsOverDesign': sorted(waivers), 'missingClips': missing}
    gates['ok'] = bool(legs) and not missing and not any(gates[k] for k in (
        'legFailures', 'locomotionLegFailures', 'locomotionFloorFailures', 'floorFailures', 'riseFailures'))
    return gates


# ---------------------------------------------------------------------------
# Glue for v2 / installed bodies (used by `check` and by the integrator)
# ---------------------------------------------------------------------------

def body_arrays(d, b):
    """Tail primitive, trouser rows, rest joints and names of a race GLB."""
    skin_ = d['skins'][0]
    names = [d['nodes'][j]['name'] for j in skin_['joints']]
    ibm = ea.accessor_array(d, b, skin_['inverseBindMatrices']).astype(float).reshape(-1, 4, 4).transpose(0, 2, 1)
    joints = {n: np.linalg.inv(m)[:3, 3] for n, m in zip(names, ibm)}
    tail = trouser = None
    for mesh in d['meshes']:
        for prim in mesh['primitives']:
            role = prim.get('extras', {}).get('sourceRole')
            a = prim['attributes']
            if role == 'race_tail':
                tail = {k: ea.accessor_array(d, b, a[k]).copy() for k in ('POSITION', 'NORMAL', 'TEXCOORD_0', 'JOINTS_0', 'WEIGHTS_0')}
                tail['faces'] = ea.accessor_array(d, b, prim['indices']).astype(int).reshape(-1, 3)
            if mesh['name'] == 'wardrobe_pants':
                f = ea.accessor_array(d, b, prim['indices']).astype(int).reshape(-1, 3)
                rows = np.unique(f)
                trouser = {k: ea.accessor_array(d, b, a[k])[rows].copy() for k in ('POSITION', 'JOINTS_0', 'WEIGHTS_0')}
    return tail, trouser, joints, names, ibm


def body_surface(d, b):
    """Triangles (n,3,3) of the Human below-neck surfaces of a race GLB."""
    tris = []
    for mesh in d['meshes']:
        if mesh['name'] not in ea.BODY_SURFACES:
            continue
        for prim in mesh['primitives']:
            if prim.get('extras', {}).get('sourceRole') not in ('shared_body', 'shared_neck', None):
                continue
            if mesh['name'] == 'body' and prim.get('extras', {}).get('sourceRole') != 'shared_body':
                continue
            p = ea.accessor_array(d, b, prim['attributes']['POSITION']).astype(float)
            tris.append(p[ea.accessor_array(d, b, prim['indices']).astype(int).reshape(-1, 3)])
    return np.concatenate(tris)


def triangle_uv_signatures(a, faces):
    """Multiset of per-triangle TEXCOORD_0 bytes (order-free face identity)."""
    from collections import Counter
    uv = np.ascontiguousarray(np.asarray(a['TEXCOORD_0'], '<f4'))
    return Counter(uv[f].tobytes() for f in faces)


def row_map(a, faces, b, b_faces):
    """Rows of `b` matching each row of `a`, through triangles with equal
    TEXCOORD_0 bytes (corner order is kept by the packer); -1 if unmatched."""
    ua = np.ascontiguousarray(np.asarray(a['TEXCOORD_0'], '<f4'))
    ub = np.ascontiguousarray(np.asarray(b['TEXCOORD_0'], '<f4'))
    index = {ub[f].tobytes(): f for f in b_faces}
    out = np.full(len(ua), -1)
    for f in faces:
        g = index.get(ua[f].tobytes())
        if g is not None:
            out[f] = g
    return out


def band_arc(points, s, ring_centre, bins=CENTRELINE_BINS):
    """Length of the polyline root-ring centre -> smoothed centroids of the
    rows in `bins` equal bands of arc distance s."""
    length = float(s.max())
    band = np.minimum((s/length*bins).astype(int), bins-1)
    centre = gaussian_filter1d(np.array([points[band == k].mean(0) for k in range(bins)]), CENTRELINE_SIGMA,
                               axis=0, mode='nearest')
    knots = np.vstack([ring_centre, centre])
    return float(np.linalg.norm(np.diff(knots, axis=0), axis=1).sum())


def v18_gate(root, slug, candidate, head, fps=SAMPLE_FPS):
    """V18 for a re-rooted tail, measured on the built candidate GLB against
    its v2 head: (ok, values).

    shape: the build recorded (sharedBodyShape.tail.shape) TAIL_SHAPE with
           its current parameters.
    rest:  triangles are the v2 tail's minus its loose fragments (per-triangle
           UV bytes equal); centreline arc length within ARC_TOLERANCE of the
           shape's length times v2's; welded root-ring centroid |x| <=
           ROOT_X_MAX_M; every root-ring vertex >= SINK_DEPTH_M/2 inside the
           Human below-neck surface.
    clips: on the clips the actor can play (action map + combat recipe
           sources, the library the client loads, NativeAnimationImporter
           semantics): clip_gates (leg clearance past ROOT_BAND_M, floor and
           rise above the pelvis in every playable clip at the design limits
           or the clip's TAIL_CLIP_WAIVERS entry; idle/walk/run legs and
           floor). The lowest tail points of every playable clip are
           reported."""
    root = Path(root)
    cd, cb = ea.read_glb(Path(candidate))
    hd, hb = ea.read_glb(Path(head))
    tail, _, joints, names, _ = body_arrays(cd, cb)
    v2, _, _, v2_names, _ = body_arrays(hd, hb)
    if tail is None or v2 is None:
        return False, {'reason': 'no race_tail primitive', 'candidate': tail is not None, 'v2': v2 is not None}
    if v2_names != names:
        return False, {'reason': 'skeletons differ'}
    name, shape = tail_shape()
    expected = {'name': name, 'pitchDegrees': [list(k) for k in shape['pitch']],
                'yawDegrees': [list(k) for k in shape['yaw']], 'length': shape['length']}
    recorded = cd['asset'].get('extras', {}).get('sharedBodyShape', {}).get('tail', {}).get('shape')
    p = np.asarray(tail['POSITION'], float)
    ids, pw, dist, ring, loops = tail_geodesic(p, tail['faces'], joints['pelvis'])
    v2_faces, fragments = drop_fragments(np.asarray(v2['POSITION'], float), v2['faces'])
    v2_ids, v2_pw, v2_dist, v2_ring, _ = tail_geodesic(np.asarray(v2['POSITION'], float), v2_faces, joints['pelvis'])
    uv_same = triangle_uv_signatures(tail, tail['faces']) == triangle_uv_signatures(v2, v2_faces)
    # arc length on the v2 tail's geodesic bands, carried to the candidate rows
    match = row_map(tail, tail['faces'], v2, v2_faces)
    rows_c = np.unique(tail['faces'])
    rows_c = rows_c[match[rows_c] >= 0]
    s_v2 = v2_dist[v2_ids]
    arc = band_arc(p[rows_c], s_v2[match[rows_c]], pw[ring].mean(0))
    v2_rows = np.unique(v2_faces)
    v2_arc = band_arc(np.asarray(v2['POSITION'], float)[v2_rows], s_v2[v2_rows], v2_pw[v2_ring].mean(0))
    centre = pw[ring].mean(0)
    rows = np.flatnonzero(np.isin(ids, ring))
    depth, _ = surface_depth(p[rows], body_surface(cd, cb))
    library = ClipLibrary(root/'godot-client/assets/actors/native/shared/Universal_Animation_Library.glb')
    clips = action_clips(root, library)
    results = clip_clearance(BodyRig(cd, cb), library, tail, dist[ids], clips, slug, fps=fps)
    gates = clip_gates(results, slug)
    values = {'shape': {'expected': expected, 'recorded': recorded, 'ok': recorded == expected},
              'trianglesV2': int(len(v2['faces'])), 'fragmentTriangles': fragments['fragmentTriangles'],
              'triangles': int(len(tail['faces'])), 'uvTrianglesEqualV2': bool(uv_same),
              'arcLengthM': {'v2': v2_arc, 'candidate': arc, 'ratio': arc/v2_arc, 'shapeLength': shape['length'],
                             'tolerance': ARC_TOLERANCE,
                             'rowsMatched': int(len(rows_c)), 'measure': 'root-ring centre + smoothed centroids of '
                             'the v2 geodesic bands (rows matched through UV-equal triangles)'},
              'rootRing': {'centre': centre.tolist(), 'sacrum': list(SACRUM.get(slug, (np.nan,)*3)),
                           'absXMaxM': ROOT_X_MAX_M, 'depthM': {'min': float(depth.min()), 'median': float(np.median(depth))},
                           'depthMinRequiredM': SINK_DEPTH_M/2, 'openLoops': loops},
              'clipGates': gates, 'clipsChecked': len(clips), 'sampleFps': fps,
              'lowestTail': sorted(([c, r['minTailY']] for c, r in results.items()), key=lambda x: x[1])[:8],
              'legClearanceM': {c: r['legClearanceM'] for c, r in results.items()}}
    ok = (recorded == expected and uv_same and abs(arc/v2_arc/shape['length']-1) <= ARC_TOLERANCE
          and abs(centre[0]) <= ROOT_X_MAX_M
          and depth.min() >= SINK_DEPTH_M/2 and gates['ok'])
    return bool(ok), values


def check(root, slug, head=None, body=None, clips='action', kits=True, fps=SAMPLE_FPS, shape=None):
    """Re-root the tail of `head` (v2 backup; default the installed body) onto
    the trousers of `body` (default: the installed race GLB) and measure."""
    root = Path(root)
    races = root/'godot-client/assets/actors/native/races'
    body = Path(body or races/f'{slug}.glb')
    head = Path(head or body)
    bd, bb = ea.read_glb(body)
    hd, hb = ea.read_glb(head)
    _, trouser, joints, names, ibm = body_arrays(bd, bb)
    tail, _, _, hnames, _ = body_arrays(hd, hb)
    if hnames != names:
        raise ValueError('head and body skeletons differ')
    surface = body_surface(bd, bb)
    result = reroot_tail(tail, trouser, joints, names, slug=slug, shape=shape, surface_tris=surface)
    rest = rest_checks(result, surface)
    capsule = tail_capsule(result, np.linalg.inv(ibm[names.index('pelvis')]))
    library = ClipLibrary(root/'godot-client/assets/actors/native/shared/Universal_Animation_Library.glb')
    rig = BodyRig(bd, bb)
    chosen = action_clips(root, library) if clips in ('action', 'all') else list(clips)
    s = result['geometry']['featherArc']
    new_tail = {'POSITION': result['POSITION'], 'JOINTS_0': result['JOINTS_0'], 'WEIGHTS_0': result['WEIGHTS_0'],
                'faces': result['faces']}
    old = {'POSITION': tail['POSITION'], 'JOINTS_0': tail['JOINTS_0'], 'WEIGHTS_0': tail['WEIGHTS_0'], 'faces': result['faces']}
    report = {'slug': slug, 'head': str(head), 'body': str(body), 'reroot': result['report'], 'rest': rest,
              'tailCollision': capsule}
    report['clips'] = clip_clearance(rig, library, new_tail, s, chosen, slug, fps=fps)
    report['clipGates'] = clip_gates(report['clips'], slug)
    report['clipGates']['clips'] = 'action map + combat recipe sources' if clips in ('action', 'all') else 'given'
    report['lowestTail'] = sorted(([c, r['minTailY']] for c, r in report['clips'].items()), key=lambda x: x[1])[:8]
    if clips == 'all':
        others = sorted(c for c in library.clips if c not in chosen)
        report['otherLibraryClips'] = clip_clearance(rig, library, new_tail, s, others, slug, fps=fps)
        report['otherLibraryClipGates'] = clip_gates(report['otherLibraryClips'], slug)
    old_s = tail_geodesic(np.asarray(tail['POSITION'], float), result['faces'], joints['pelvis'])
    report['clipsBefore'] = clip_clearance(rig, library, old, old_s[2][old_s[0]], chosen, slug, fps=fps)
    if kits:
        equipment = json.loads((root/'godot-client/data/actors/equipment.json').read_text(encoding='utf-8'))
        pieces = {}
        for kit, loadout in CLASS_KITS.items():
            for part, item in loadout.items():
                key = f'{part}:{item}'
                path = kit_scene(root, slug, key, equipment)
                pieces[f'{kit} {key} {path.name}'] = skinned_pieces(path)
        pieces['bare wardrobe_pants'] = [x for x in skinned_pieces(body, include={'wardrobe_pants'})]
        kit_clips = [c for c in chosen if c in ('Idle_Subtle', 'Walk', 'Run_Female', 'Fighting_Idle', 'Sitting_Idle',
                                                'Death_A', 'Sword_Regular_A', 'Bow_Pull_Back', 'Farm_Harvest', 'Meditate')]
        report['kitClips'] = clip_clearance(rig, library, new_tail, s, kit_clips, slug, pieces=pieces, fps=fps/1.5)
    return report, result


def main():
    ap = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    sub = ap.add_subparsers(dest='cmd', required=True)
    c = sub.add_parser('check')
    c.add_argument('--root', required=True)
    c.add_argument('--slug', required=True)
    c.add_argument('--head')
    c.add_argument('--body')
    c.add_argument('--clips', default='action', help="'action' (gated), 'all' (action gated + the rest of the "
                                                     "library reported) or a comma list")
    c.add_argument('--no-kits', action='store_true')
    c.add_argument('--shape', choices=sorted(TAIL_SHAPES), help=f'drape shape (default {TAIL_SHAPE})')
    c.add_argument('--out')
    args = ap.parse_args()
    clips = args.clips if args.clips in ('action', 'all') else args.clips.split(',')
    report, _ = check(args.root, args.slug, args.head, args.body, clips, not args.no_kits, shape=args.shape)
    text = json.dumps(report, indent=2, default=float)+'\n'
    if args.out:
        out = Path(args.out).resolve()
        if 'godot-client' in out.parts:
            raise ValueError('write reports outside godot-client')
        out.write_text(text, encoding='utf-8')
    print(json.dumps({'reroot': {k: report['reroot'][k] for k in ('arcLengthM', 'rootCentre', 'tip', 'weights')},
                      'rest': report['rest'], 'tailCollision': report['tailCollision'], 'clipGates': report['clipGates'],
                      'lowestTail': report['lowestTail']}, indent=1, default=float))


if __name__ == '__main__':
    main()
