"""Race-only headwear clearance: the socket calibration and the post-passes of the P5 refit.

refit_race_headwear.py fits every headwear piece to a race body with the
unchanged canonical fitter (refit_canonical_equipment.build_one, which runs
limb_head_remap.head_frame) and then hands the fitted piece to this module.
Nothing here runs inside head_frame (test_limb_head_remap.py pins that
transform on the Human), and every pass is gated on a race body: on the two
Human bodies (luminous_male / luminous_female) the socket is the measured one
and no pass touches the piece, so a Human fit reproduces bit for bit.

Inputs per body are read from its own GLB:

* the cranium: the feature-free head (``body`` race_head + ``scalp``), with
  an ellipsoid fitted behind the face (the ray origin for every measurement);
* ears: race_head triangles more than 10 mm outside that ellipsoid at the side
  of the head (pointed ears, the Ssarathi side frills);
* features: the ``race_feature_head`` node (Votary horns, Stoneborn crown,
  Glasswarden crystals), whose hide/show policy is headwear_race_policy.json;
* the neck: race neck skin above the chin line counts as head skin
  (``neck_skin``), below it as collar;
* the collar: ``wardrobe_shirt``, the upper shared body and the lower race neck
  (on a Human body, its own skin under the chin).

Steps, in the order refit_race_headwear.race_pass applies them:

``head_transfer`` (the socket calibration)
    The canonical fitter seats a piece by an enclosure search whose choice of
    centre jumps between bodies (a hood's wrap lands across the mouth on one
    race and under the chin on the next), and its socket is the bounding-box
    centre of the Head-weighted vertices, horns included.  A race fit is
    instead the Human fit of the same piece carried onto the race head: both
    raw fits are similarity images of one source (head_frame is a uniform
    scale and a translation, ``frame_map``), so the race piece becomes the
    Human piece scaled by the head size ``k`` about the eye anchor (eye line,
    midline, depth of the feature-free cranium's centre), and its socket is
    the Human's socket carried the same way: socket to eye line = k x the
    Human's.  ``k`` is measured on the feature-free cranium along rays from
    the anchor.  Drapes (every kind but ``helm``) fade back to the Human's
    own placement below the chin and the nape (``transfer_points(drape=True)``),
    where every race wears the Human's shoulders.  Open bands are carried too:
    the fitter's own band seat jumps 6 cm between bodies (a second enclosure
    solution on glasswarden_male and votary_male).

``helm_grow`` (rigid helms)
    Up to 25 % larger about the eye anchor until the head (the face and jaw
    included, a snout excepted) stops coming through, then seated up to 2 cm
    lower and 1 cm forward if a chin still hangs under the hem: a larger
    helm, not a dent or a crumpled visor.

``band_grow`` (open bands)
    Up to 15 % larger about the eye anchor until the race's hair cap (every
    offered style, as headwear_envelope.py replays them from the installed
    client, within 12 mm of the head) and a show crown or crystals come
    through no more than the Human band lets the Human's own hair cap.

``ear_bulge`` (policy ``ears: tuck``; an open band where an ear comes through it)
    Each shell vertex moves radially (from the cranium centre) by the amount
    that clears the outermost ear in its 1-degree direction bin by 6 mm.  On
    cloth the lobe has a narrow top and a parabolic fall (it follows the ear);
    on a helm it is broad and gentle (6-degree dilation, 5-degree blur).

``snout_opening`` (rigid helms on SNOUT_RACES)
    The visor is opened round the snout, with a turned rim, where pushing the
    metal out 4-6 cm would tear it off the helm (``pass_through``).

``feature_bulge`` (``raceFeatures: show``; Stoneborn crown, Glasswarden crystals)
    The same push over the feature triangles, spread with a parabolic falloff
    so a crown is covered by one rounded cap, on a grid whose poles sit at the
    sides of the head.  On an open band, ``band_feature_bulge``: only the
    feature triangles still coming through push it, with a narrow tent.

``horn_bulge`` (``horns: passThrough``, and open bands on Votary)
    The shell drapes over the horn roots where a horn runs inside it.

``collar_clearance``
    Drape triangles near the collar that need a push are split, then vertices, centroids and
    edge midpoints below the mouth that lie inside, or within 3 mm of, the
    collar move out along its normal (three rounds, at most 15 mm each, spread
    to neighbours within 8 mm and faded by 25 mm) -- but only as far as the
    same point of the Human fit clears the Human's collar: a wrap tucked into
    the Human's collar by design may be as deep on the race, never deeper; a
    point more than 8 mm inside the Human's own collar (a lining) is left.

``head_bulge`` (every piece), last of the pushes
    The same radial push, narrow and parabolic, over whatever of the head and
    neck still comes through: a nose through a veil, the back of a large
    cranium, a nape through a cap's hem, a snout through a circlet's pendant.
    On a rigid helm the push is the broad, gentle one of the ear cups.

Every bulge reads the shell's inner wall from points spread over its faces
(``dense_samples``), not from its corners alone: a helm's large flat side
face covers an ear while none of its corners lies in the ear's direction.
Small parts (rivets, buckles, beads) and flat closed ones (two-sided cards)
move as one through the drape carry, every bulge and the collar rounds
(``rigid_small_parts``), so none is turned inside out
(audit_canonical_batch.py's inward closed shells).

``horn_pass_through`` (``horns: passThrough``; Votary)
    The shell where a horn crosses it is split along the cut, cut along the
    8 mm offset of the horn surface (an exact iso-line, so the hole is round),
    and every opening gets a turned rim: a 6 mm band folded in toward the
    skull with the edge's own texture.

On a single-sided material every bulge evens its push over faces it would
turn over (a turned-over face would read as a hole).  Every headwear material
is double sided, so the evening is off there: raising a face to its corners'
largest push lifted inner linings and straps out through the shell (black
flaps on the Gilt Bascinet, torn veils).  The driver reports the faces turned
over against the Human fit, and the welded copies a pass moved apart.

``measure``
    The gates: ear poke (cm2, mm), face, neck and scalp poke, feature poke
    and feature edges crossing the piece (radial, from the cranium centre,
    beyond the outermost hit), body edges crossing the piece (the rebase
    tool's headwear_crossings method) and collar crossings under the chin
    line by one rule for every body, the Human included (the baseline).
    Collar crossings count every body edge through the piece, a lining
    inside the neck under the outer layer included, and scale with the
    density of each body's neck mesh; ``collar_clip`` is the visible part:
    exposed shirt, neck and shoulder with the piece just under them and
    nothing over them (cm2).

``band ears`` (refit_race_headwear.race_pass)
    An open band leaves the ears free (policy ``ears: none``), but where a
    race ear still comes through it (the Starglass Circlet's veil hangs
    past the ears) the band takes the cloth ear lobe of ``ear_bulge``.

Memory: trimesh's ray and closest-point queries are chunked (``_chunks``);
one unchunked parity cast over a refined shell took 22 GB.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path

import numpy as np

import equipment_authoring as ea

HERE = Path(__file__).resolve().parent
POLICY_PATH = HERE / 'headwear_race_policy.json'
HUMAN_BODIES = frozenset({'luminous_male', 'luminous_female'})
#: Feature node and what each race carries on it.
FEATURE_NODE = 'race_feature_head'
FEATURE_KIND = {'votary': 'horns', 'stoneborn': 'crown', 'glasswarden': 'crystals'}

FEATURE_MM = 10.0        # protrusion beyond the cranium ellipsoid that makes an ear
EAR_CLEARANCE = .006
EAR_DILATE_DEG = 3
EAR_BLUR_DEG = 4
EAR_DOME = 4e-5
#: An ear lobe clears the ear by EAR_CLEARANCE: its faces may stray this far
#: from the push field before they are split (BULGE_TOL), down to this edge,
#: so a variant keeps fewer of the split triangles that are most of its size.
EAR_BULGE_TOL = .0045
EAR_BULGE_EDGE = .010
HEAD_CLEARANCE = .004
FEATURE_CLEARANCE = .006
BULGE_DILATE_DEG = 6
BULGE_BLUR_DEG = 5
BULGE_EDGE = .008        # a bulge splits the faces it bends (BULGE_TOL) down to this edge length
FLIP_ROUNDS = 12        # rounds of evening a bulge's push over faces it would turn over
BULGE_TOL = .003         # how far a face may stray from the push field before it is split
FEATURE_DILATE_DEG = 6
FEATURE_BLUR_DEG = 5
FEATURE_DOME = 3e-5      # metres per square degree: 27 mm lower 30 degrees off a spike
DOME_WINDOW = 30
COLLAR_CLEARANCE = .003
COLLAR_REACH = .03       # vertices further than this from the collar surface are never tested
COLLAR_SPREAD = (.008, .025)
COLLAR_ROUNDS = 3
COLLAR_STEP = .015
SMALL_PART = .04          # a welded part smaller than this moves as one (rigid_small_parts)
FLAT_PART = .002          # ... and a closed one with |volume| under this x its box diagonal cubed
COLLAR_INTERIOR = .008     # a Human fit this deep inside its own collar is hidden lining: never pushed
#: The radial neck map (neck_clearance) pushed drapes 4-6 cm sideways off a
#: sloping neck base (flared hems); the collar surface now includes the lower
#: race neck, so the map is off.  Kept for diagnosis.
NECK_PASS = False
COLLAR_REFINE = .020       # drape triangles within this of the collar are split to this edge
COLLAR_NECK_BELOW_EYE = .095   # race neck faces this far under the eye line count as collar
COLLAR_UNDER_SHIRT = .015  # body skin with the shirt this close over it is under the shirt (collar_clip)
COLLAR_CLIP_DEPTH = .03    # collar_clip: the piece this far under an exposed collar point is inside the body
HORN_OPENING = .008
HORN_RIM = .006
HORN_SWALLOW = .02
HORN_CLEARANCE = .004
HORN_EDGE = .010          # the shell along an opening's edge is split this fine, so the hole is round
SNOUT_EDGE = .012
SNOUT_DEPTH = .03         # the face: in front of the cranium centre by this much, below the brow
SNOUT_OPEN_CM2 = 2.0      # face poke through a piece that opens it round the snout
SNOUT_RACES = frozenset({'ssarathi'})
HEAD_DILATE_DEG = 2
HEAD_DOME = 6e-5          # metres per square degree: 6 mm lower 10 degrees off a nose tip
HELM_GROW_MAX = 1.25      # a rigid helm grows at most this much to clear the head
HELM_GROW_CM2 = .5        # head poke a rigid helm is grown to
#: seat shifts (character space: down, forward) a grown helm may take to clear a chin under its hem
HELM_SHIFTS = tuple((0., -dy, dz) for dy in (0., .005, .01, .015, .02) for dz in (0., .005, .01) if dy or dz)
BAND_GROW_MAX = 1.15      # an open band grows at most this much over the hair cap
BAND_HAIR_REACH = .012    # hair within this of the head is the cap a band sits on
BAND_ALLOWED_CM2 = 1.0    # hair cap and head an open band may leave poking (or 1.2 x the Human's)
TRANSFER_RANGE = (.85, 1.3)   # the race cranium against the Human's
#: Below the head the races wear the Human body itself (shirt and shoulders
#: are the same vertices), so a drape fades from the head transfer to no
#: transfer under the Human's eye line: from DRAPE_FRONT (the chin) at the
#: front and DRAPE_BACK (the nape) at the back, over DRAPE_SPAN of height.
DRAPE_FRONT = .125
DRAPE_BACK = .055
DRAPE_SPAN = .075
DEG = 1.0
RAY_CHUNK = 200          # rays per trimesh query (memory: see _chunks)
CLOSEST_CHUNK = 400
NA, NE = int(360 / DEG), int(180 / DEG)


def is_race_body(slug: str) -> bool:
    """Every body but the two Human ones takes the race passes."""
    return slug not in HUMAN_BODIES


@lru_cache(maxsize=1)
def _policy_table():
    return json.loads(POLICY_PATH.read_text(encoding='utf-8'))['pieces']


def policy(key: str) -> dict:
    """The headwear_race_policy.json row of one visual key (``3:N``)."""
    return dict(_policy_table()[key])


def race_of(slug: str) -> str:
    return slug.rsplit('_', 1)[0]


# ---------------------------------------------------------------------------
# Body geometry
# ---------------------------------------------------------------------------

def _primitives(d, b):
    from verify_shared_player_bodies import primitives
    return primitives(d, b)


def _triangles(d, b, names=None, roles=None):
    out = []
    for name, role, attrs, faces in _primitives(d, b):
        if names is not None and name not in names:
            continue
        if roles is not None and role not in roles:
            continue
        out.append(attrs['POSITION'].astype(float)[faces])
    return np.concatenate(out) if out else np.empty((0, 3, 3))


def _head_matrix(d):
    world = ea.global_matrices(d)
    index = next(i for i, n in enumerate(d['nodes']) if n.get('name') == 'Head')
    return np.asarray(world[index], dtype=float)


def _fit_cranium(local, eye_y, eye_z):
    """Ellipsoid through the cranium behind the face and above the cheek, with
    the ear band left out; refitted without >6 mm outliers (ears, crest)."""
    from scipy.optimize import least_squares
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
        s = s[_protrusion(s, centre, radii) < .006]
        p0 = fit.x
    return centre, radii


def _protrusion(local, centre, radii):
    """Approximate metric distance outside the ellipsoid along the radial line."""
    q = (local - centre) / radii
    k = np.linalg.norm(q, axis=1)
    r = np.linalg.norm(local - centre, axis=1)
    return r * (1 - 1 / np.maximum(k, 1e-9))


@dataclass
class HeadGeometry:
    slug: str
    head: np.ndarray            # Head rest matrix (character space)
    eye_y: float                # median eye height, character space
    eye_top: float              # 95 % eye height
    eye_z: float                # front of the eyes
    centre_local: np.ndarray    # cranium ellipsoid centre, Head-local
    radii: np.ndarray
    cranium_top: float          # highest Head-weighted feature-free vertex
    cranium_back: float         # back of the skull (z) between eye line and +8 cm
    ears: np.ndarray            # (n, 3, 3) lateral protrusions of race_head
    skin: np.ndarray            # (n, 3, 3) the rest of race_head (face, jaw, snout, cranium skin)
    scalp: np.ndarray           # (n, 3, 3) scalp (drawn under a show piece, hidden under the rest)
    features: np.ndarray        # (m, 3, 3) race_feature_head
    feature_kind: str | None
    collar: np.ndarray          # (k, 3, 3) shirt + upper shared body
    neck: np.ndarray            # (j, 3, 3) the near-vertical neck skin (shared_neck, neck_join)
    neck_axis: np.ndarray       # (x, z) of the neck's vertical axis
    edges: tuple = field(default=(), repr=False)   # body edges (a, b) for crossings
    neck_skin: np.ndarray = field(default_factory=lambda: np.empty((0, 3, 3)), repr=False)  # neck above the collar
    collar_edges: tuple = field(default=(), repr=False)  # body + shirt edges under the chin (any body, Human too)
    feature_edges: tuple = field(default=(), repr=False)
    collar_surface: tuple = field(default=(), repr=False)  # exposed collar (centroids, normals, areas): collar_clip

    @property
    def origin(self) -> np.ndarray:
        """Cranium centre in character space: every radial ray starts here."""
        return self.head[:3, 3] + self.head[:3, :3] @ self.centre_local

    def to_local(self, points):
        return (np.asarray(points, dtype=float) - self.head[:3, 3]) @ self.head[:3, :3]

    def to_world(self, local):
        return np.asarray(local, dtype=float) @ self.head[:3, :3].T + self.head[:3, 3]


def _edges_of(tris):
    if not len(tris):
        return np.empty((0, 3)), np.empty((0, 3))
    a = np.concatenate([tris[:, 0], tris[:, 1], tris[:, 2]])
    b = np.concatenate([tris[:, 1], tris[:, 2], tris[:, 0]])
    ka, kb = np.round(a, 7), np.round(b, 7)
    swap = np.zeros(len(a), dtype=bool)
    decided = np.zeros(len(a), dtype=bool)
    for axis in range(3):
        swap |= ~decided & (ka[:, axis] > kb[:, axis])
        decided |= ka[:, axis] != kb[:, axis]
    lo = np.where(swap[:, None], kb, ka)
    hi = np.where(swap[:, None], ka, kb)
    _, unique = np.unique(np.hstack([lo, hi]), axis=0, return_index=True)
    a, b = a[unique], b[unique]
    keep = np.linalg.norm(b - a, axis=1) > 1e-7
    return a[keep], b[keep]


@lru_cache(maxsize=32)
def head_geometry(path: str) -> HeadGeometry:
    """Every measurement this module needs from one body GLB (cached by path)."""
    path = Path(path)
    slug = path.stem
    d, b = ea.read_glb(path)
    head = _head_matrix(d)
    eyes = _triangles(d, b, names={'eyes'}).reshape(-1, 3)
    eye_y = float(np.median(eyes[:, 1]))
    eye_top = float(np.quantile(eyes[:, 1], .95))
    eye_z = float(eyes[:, 2].max())
    face_tris = _triangles(d, b, names={'body'}, roles={'race_head'})
    scalp_tris = _triangles(d, b, names={'scalp'})
    head_tris = np.concatenate([face_tris, scalp_tris])
    rig = ea.load_rig(path, ea.BODY_SURFACES)
    index = rig.joint_names.index('Head')
    weight = sum(np.where(rig.joints[:, c] == index, rig.weights[:, c], 0.)
                 for c in range(rig.joints.shape[1]))
    cranium = rig.positions[weight >= .5]
    cranium_top = float(cranium[:, 1].max())
    band = cranium[(cranium[:, 1] > eye_y) & (cranium[:, 1] < eye_y + .08)]
    cranium_back = float(np.quantile(band[:, 2], .02))
    eyes_local = (eyes - head[:3, 3]) @ head[:3, :3]
    local_eye_y = float(np.median(eyes_local[:, 1]))
    local_eye_z = float(eyes_local[:, 2].max())
    local = (head_tris.reshape(-1, 3) - head[:3, 3]) @ head[:3, :3]
    centre, radii = _fit_cranium(local, local_eye_y, local_eye_z)
    tri_local = (head_tris.mean(1) - head[:3, 3]) @ head[:3, :3]
    out = _protrusion(tri_local, centre, radii) * 1000
    face = (tri_local[:, 2] > local_eye_z - .03) & (tri_local[:, 1] < local_eye_y + .035)
    face |= tri_local[:, 1] < local_eye_y - .045
    lateral = (abs(tri_local[:, 0]) > .06) & (tri_local[:, 1] < local_eye_y + .06)
    is_ear = (out > FEATURE_MM) & lateral & ~face
    ears = head_tris[is_ear]
    is_scalp = np.arange(len(head_tris)) >= len(face_tris)
    features = _triangles(d, b, names={FEATURE_NODE})
    shared = _triangles(d, b, names={'body'}, roles={'shared_body'})
    if not len(shared):
        # A Human body is one role: its skin under the chin plays the shared body.
        whole = _triangles(d, b, names={'body'})
        shared = whole[whole.mean(1)[:, 1] < eye_y - COLLAR_NECK_BELOW_EYE]
    collar = np.concatenate([_triangles(d, b, names={'wardrobe_shirt'}), shared])
    collar = collar[collar[..., 1].max(1) > head[1, 3] - .32 * rig.fit_scale]
    neck = _triangles(d, b, names={'body'}, roles={'shared_neck', 'neck_join'})
    # The race neck below the chin is collar too: a drape crosses its sloping
    # base (trapezius, the turn under the jaw) where the radial neck map,
    # which reads only near-vertical skin, cannot see it.
    collar = np.concatenate([collar, neck[neck.mean(1)[:, 1] < eye_y - COLLAR_NECK_BELOW_EYE]])
    # ...and above it the neck is skin the piece must clear like the head's
    # (a cap's back hem across the nape).
    neck_skin = neck[neck.mean(1)[:, 1] >= eye_y - COLLAR_NECK_BELOW_EYE]
    normal = np.cross(neck[:, 1] - neck[:, 0], neck[:, 2] - neck[:, 0])
    normal /= np.maximum(np.linalg.norm(normal, axis=1, keepdims=True), 1e-12)
    # The side of the neck only: the bridge under the chin faces down, and a
    # point above it is inside the jaw, not inside the neck.
    neck = neck[np.abs(normal[:, 1]) < .5]
    lower = _triangles(d, b, names={'body'}, roles={'shared_neck'}).reshape(-1, 3)
    neck_axis = np.median(lower[:, [0, 2]], axis=0) if len(lower) else head[[0, 2], 3]
    crossing_edges = _triangles(d, b, roles={'shared_body', 'shared_neck', 'neck_join'})
    ea_, eb_ = _edges_of(crossing_edges)
    keep = np.maximum(ea_[:, 1], eb_[:, 1]) > 1.25
    # One rule for every body, the Human included (whose body is one role):
    # body and shirt edges with both ends between 1.25 m and the chin line.
    ca, cb = _edges_of(np.concatenate([_triangles(d, b, names={'body'}), _triangles(d, b, names={'wardrobe_shirt'})]))
    low = eye_y - COLLAR_NECK_BELOW_EYE
    band = (np.minimum(ca[:, 1], cb[:, 1]) > 1.25) & (np.maximum(ca[:, 1], cb[:, 1]) < low)
    exposed = _exposed_collar(_triangles(d, b, names={'body'}), _triangles(d, b, names={'wardrobe_shirt'}), low)
    return HeadGeometry(
        slug=slug, head=head, eye_y=eye_y, eye_top=eye_top, eye_z=eye_z,
        centre_local=centre, radii=radii, cranium_top=cranium_top, cranium_back=cranium_back,
        ears=ears, skin=head_tris[~is_ear & ~is_scalp], scalp=head_tris[~is_ear & is_scalp], features=features,
        feature_kind=FEATURE_KIND.get(race_of(slug)) if len(features) else None,
        collar=collar, neck=neck, neck_axis=neck_axis, edges=(ea_[keep], eb_[keep]),
        feature_edges=_edges_of(features) if len(features) else (),
        neck_skin=neck_skin, collar_edges=(ca[band], cb[band]), collar_surface=exposed)


def _exposed_collar(body, shirt, low):
    """The collar as it is seen: shirt triangles, and body triangles not under
    the shirt (their outward ray meets the shirt within COLLAR_UNDER_SHIRT),
    reaching into the band between 1.25 m and ``low`` (the chin line).
    Returns (centroids, unit outward normals, areas)."""
    def band(t):
        y = t[..., 1]
        return t[(y.max(1) > 1.25) & (y.min(1) < low)] if len(t) else t

    def geometry(t):
        n = np.cross(t[:, 1] - t[:, 0], t[:, 2] - t[:, 0])
        area = np.linalg.norm(n, axis=1) / 2
        return t.mean(1), n / np.maximum(2 * area, 1e-12)[:, None], area
    sc, sn, sa = geometry(band(shirt))
    bc, bn, ba = geometry(band(body))
    if len(shirt) and len(bc):
        t = _first_hit(_intersector(shirt), bc + bn * 1e-4, bn)
        exposed = t >= COLLAR_UNDER_SHIRT
        bc, bn, ba = bc[exposed], bn[exposed], ba[exposed]
    return np.concatenate([sc, bc]), np.concatenate([sn, bn]), np.concatenate([sa, ba])


def _first_hit(engine, origins, directions) -> np.ndarray:
    """Distance to the first hit along each ray (inf: none)."""
    t = np.full(len(origins), np.inf)
    for chunk in _chunks(len(origins), RAY_CHUNK):
        loc, ray, _ = engine.intersects_location(origins[chunk], directions[chunk], multiple_hits=False)
        if len(ray):
            rows = np.arange(len(origins))[chunk][ray]
            t[rows] = np.linalg.norm(loc - origins[chunk][ray], axis=1)
    return t


def collar_clip(engine, surface) -> float:
    """Visible collar clipping (cm2): exposed collar (shirt, bare neck and
    shoulders under the chin line) with the piece within COLLAR_CLIP_DEPTH
    under it (inside the body) and none within that over it.  A lining inside
    the neck under the piece's outer layer is not seen and does not count
    (edge crossings count it); a wrap or an aventail tucked under the shirt
    collar does, on the Human fit as on a race fit."""
    centres, normals, areas = surface
    if not len(centres):
        return 0.0
    inner = _first_hit(engine, centres - normals * 1e-4, -normals) < COLLAR_CLIP_DEPTH
    outer = _first_hit(engine, centres + normals * 1e-4, normals) < COLLAR_CLIP_DEPTH
    return round(float(areas[inner & ~outer].sum() * 1e4), 2)


# ---------------------------------------------------------------------------
# Socket calibration: the Human fit carried onto the race head
# ---------------------------------------------------------------------------

def human_slug(slug: str) -> str:
    return 'luminous_' + slug.rsplit('_', 1)[1]


def cranium_rays() -> np.ndarray:
    """Unit directions over the cranium: every 10 degrees of azimuth and
    elevation above the eye line, without the face (low rays to the front)."""
    out = []
    for el in range(0, 91, 10):
        for az in range(0, 360, 10):
            e, a = np.radians(el), np.radians(az)
            d = np.array([np.cos(e) * np.sin(a), np.sin(e), np.cos(e) * np.cos(a)])
            if el < 35 and d[2] > .2:
                continue
            if el == 90 and az:
                continue
            out.append(d)
    return np.asarray(out)


def eye_anchor(g: HeadGeometry) -> np.ndarray:
    """The point both fits are aligned on: the eye line, on the midline, at
    the depth of the feature-free cranium's centre."""
    return np.array([0.0, g.eye_y, g.origin[2]])


def cranium_distances(g: HeadGeometry, anchor, rays) -> np.ndarray:
    """Outermost hit of each ray on the feature-free cranium (race_head
    without the ears, plus the scalp); NaN where a ray leaves through an ear."""
    engine = _intersector(np.concatenate([g.skin, g.scalp]))
    origins = np.broadcast_to(anchor, rays.shape).copy()
    loc, ray, _ = engine.intersects_location(origins, rays, multiple_hits=True)
    t = np.full(len(rays), -np.inf)
    if len(ray):
        np.maximum.at(t, ray, np.einsum('ij,ij->i', loc - origins[ray], rays[ray]))
    return np.where(t > 0, t, np.nan)


@lru_cache(maxsize=32)
def head_transfer(race_path: str, human_path: str) -> dict:
    """How a Human fit is carried onto a race head: a uniform scale ``k`` about
    the eye anchor (eye line, midline, cranium depth).

    ``k`` is the race cranium against the Human's along the cranium rays from
    each body's anchor: the 75th percentile of the per-ray ratio, but never
    below the mean ratio at the sides or the back of the head (a Ssarathi's
    eyes sit high, so its rays upward are short while its skull is as wide as
    a Human's), clamped to TRANSFER_RANGE.  Everything is read from the
    feature-free cranium: horns, crown and crystals are the passes' business.
    """
    g, h = head_geometry(race_path), head_geometry(human_path)
    rays = cranium_rays()
    ar, ah = eye_anchor(g), eye_anchor(h)
    q = cranium_distances(g, ar, rays) / cranium_distances(h, ah, rays)
    side = (np.abs(rays[:, 0]) > .8) & (rays[:, 1] < .5)
    back = (rays[:, 2] < -.5) & (rays[:, 1] < .5)
    p75 = float(np.nanpercentile(q, 75))
    k_raw = max(p75, float(np.nanmean(q[side])), float(np.nanmean(q[back])))
    k = float(np.clip(k_raw, *TRANSFER_RANGE))
    return {'k': k, 'kRaw': round(k_raw, 4), 'p75': round(p75, 4),
            'side': round(float(np.nanmean(q[side])), 4), 'back': round(float(np.nanmean(q[back])), 4),
            'up': round(float(np.nanmean(q[rays[:, 1] > .7])), 4),
            'anchor': ar.tolist(), 'humanAnchor': ah.tolist(),
            'humanEye': h.eye_y}


def transfer_points(human_world, transfer, drape=False) -> np.ndarray:
    """Human character-space points carried onto the race head.

    ``drape``: below the Human's chin the carry fades out (smoothstep) and
    is gone at the Human's neck base, where every race wears the Human's own
    shoulders; so a hood's wrap and curtain, a coif's mail and a hat's cords
    keep resting where they rest on the Human, while the part around the head
    follows the head (the face down to the chin, the back of the skull down to
    the nape: DRAPE_FRONT, DRAPE_BACK).  Rigid helms are carried whole."""
    p = np.asarray(human_world, dtype=float)
    anchor = np.asarray(transfer['humanAnchor'])
    head = np.asarray(transfer['anchor']) + transfer['k'] * (p - anchor)
    if not drape:
        return head
    t = np.clip((p[..., 2] - anchor[2] + .04) / .08, 0, 1)
    front = t * t * (3 - 2 * t)
    top = transfer['humanEye'] - (DRAPE_BACK + (DRAPE_FRONT - DRAPE_BACK) * front)
    t = np.clip((p[..., 1] - (top - DRAPE_SPAN)) / DRAPE_SPAN, 0, 1)
    w = (t * t * (3 - 2 * t))[..., None]
    return w * head + (1 - w) * p


def frame_map(race_frame: dict, human_frame: dict):
    """The fitter's head_frame is ``(source - sourceCenter) * scale + targetCenter``
    for every body, so a race fit and the Human fit of one piece are two
    similarity images of the same source.  Returns f(race_world) -> human_world."""
    sr, cr, tr = race_frame['scale'], np.asarray(race_frame['sourceCenter']), np.asarray(race_frame['targetCenter'])
    sh, ch, th = human_frame['scale'], np.asarray(human_frame['sourceCenter']), np.asarray(human_frame['targetCenter'])

    def to_human(points):
        source = (np.asarray(points, dtype=float) - tr) / sr + cr
        return (source - ch) * sh + th
    return to_human


# ---------------------------------------------------------------------------
# Radial direction grid (shared by the bulges and the poke measurement)
# ---------------------------------------------------------------------------

def _to_grid(local, pole='y'):
    """1-degree azimuth/elevation bins about the cranium centre.  ``pole`` is
    the axis the grid's poles sit on: 'y' (top and chin) for the ears, 'x'
    (the sides) for anything on top of the head, where a y-pole grid would
    put a centimetre-wide patch across ninety azimuth bins."""
    if pole == 'x':
        local = local[:, [1, 0, 2]]
    r = np.linalg.norm(local, axis=1)
    az = np.degrees(np.arctan2(local[:, 0], local[:, 2])) % 360
    el = np.degrees(np.arcsin(np.clip(local[:, 1] / np.maximum(r, 1e-9), -1, 1))) + 90
    return (np.minimum((az / DEG).astype(int), NA - 1),
            np.minimum((el / DEG).astype(int), NE - 1), r)


def _samples(tris):
    """Vertices, centroids and edge midpoints: dense enough for a 1-degree grid."""
    if not len(tris):
        return np.empty((0, 3))
    return np.vstack([tris.reshape(-1, 3), tris.mean(1), (tris[:, 0] + tris[:, 1]) / 2,
                      (tris[:, 1] + tris[:, 2]) / 2, (tris[:, 2] + tris[:, 0]) / 2])


def _barycentric(n):
    """Barycentric weights of a triangle grid with n steps per edge."""
    i, j = np.meshgrid(np.arange(n + 1), np.arange(n + 1), indexing='ij')
    keep = i + j <= n
    i, j = i[keep], j[keep]
    return np.stack([n - i - j, i, j], 1) / n


def dense_samples(tris, step=.0025, cap=24, owners=False):
    """Points over every triangle, at most ``step`` apart (``cap`` steps per
    edge): a large flat triangle of a helm's side covers many 1-degree bins
    while its three corners sit in none of them.  ``owners`` also returns
    each sample's triangle and weights."""
    if not len(tris):
        return (np.empty((0, 3)), np.empty(0, dtype=np.int64), np.empty((0, 3))) if owners else np.empty((0, 3))
    edge = np.linalg.norm(tris[:, [1, 2, 0]] - tris, axis=2).max(1)
    steps = np.clip(np.ceil(edge / step), 1, cap).astype(int)
    points, index, weights = [], [], []
    for n in np.unique(steps):
        sel = np.flatnonzero(steps == n)
        w = _barycentric(int(n))
        points.append(np.einsum('kw,twc->tkc', w, tris[sel]).reshape(-1, 3))
        index.append(np.repeat(sel, len(w)))
        weights.append(np.tile(w, (len(sel), 1)))
    points = np.concatenate(points)
    if owners:
        return points, np.concatenate(index), np.concatenate(weights)
    return points


def radial_push(g: HeadGeometry, obstacle_tris, shell_points, clearance,
                dilate_deg=BULGE_DILATE_DEG, blur_deg=BULGE_BLUR_DEG, swallow=None, limit=None, dome=None, pole='y',
                grid_only=False, shell_tris=None):
    """Move shell points radially so they clear the obstacle by ``clearance``.

    ``grid_only`` returns the push per direction bin instead of moving anything.

    ``dome`` (metres per square degree): instead of a flat dilation, the
    obstacle's radius is spread with a parabolic falloff, so a cluster of
    spikes is covered by one rounded cap rather than a tent over each spike.

    ``swallow``: only obstacle samples less than this far outside the shell's
    inner wall (in their direction bin) are covered; whatever stands further
    out is left to pierce the shell.  ``limit`` caps the push.
    ``shell_tris``: the shell's inner wall is read from points spread over
    these triangles (dense_samples) instead of from ``shell_points`` alone.
    Returns (moved points, per-point push in metres).
    """
    from scipy.ndimage import gaussian_filter, grey_dilation
    if not len(obstacle_tris):
        return shell_points.copy(), np.zeros(len(shell_points))
    c = g.centre_local
    fl = g.to_local(_samples(obstacle_tris)) - c
    ia, ie, r = _to_grid(fl, pole)
    wall_points = shell_points if shell_tris is None else np.vstack([shell_points, dense_samples(shell_tris)])
    if swallow is not None:
        sa0, se0, sr0 = _to_grid(g.to_local(wall_points) - c, pole)
        wall = np.full((NA, NE), np.inf)
        np.minimum.at(wall, (sa0, se0), sr0)
        wall = -grey_dilation(np.where(np.isfinite(wall), -wall, -np.inf), size=(5, 5), mode='wrap')
        keep = r < wall[ia, ie] + swallow
        ia, ie, r = ia[keep], ie[keep], r[keep]
    R = np.zeros((NA, NE))
    np.maximum.at(R, (ia, ie), r)
    sl = g.to_local(shell_points) - c
    sa, se, sr = _to_grid(sl, pole)
    wa, we, wr = _to_grid(g.to_local(wall_points) - c, pole)
    rin = np.full((NA, NE), np.inf)
    np.minimum.at(rin, (wa, we), wr)
    k = int(round(dilate_deg / DEG)) * 2 + 1
    Rd = grey_dilation(R, size=(k, k), mode='wrap')
    if dome is not None:
        w = DOME_WINDOW
        j, i = np.meshgrid(np.arange(-w, w + 1), np.arange(-w, w + 1))
        Rd = np.maximum(Rd, grey_dilation(R, structure=-dome * ((i * DEG) ** 2 + (j * DEG) ** 2), mode='wrap'))
    rin_f = np.where(np.isfinite(rin), rin, np.nan)
    fill = -grey_dilation(np.nan_to_num(-rin_f, nan=-1.0), size=(k, k), mode='wrap')
    rin_f = np.where(np.isnan(rin_f), fill, rin_f)
    delta = np.where(Rd > 0, np.maximum(0, Rd + clearance - rin_f), 0)
    delta = np.maximum(delta, gaussian_filter(grey_dilation(delta, size=(k, k), mode='wrap'),
                                              blur_deg / DEG, mode='wrap'))
    if limit is not None:
        delta = np.minimum(delta, limit)
    if grid_only:
        return delta
    dv = delta[sa, se]
    moved = sl + (sl / np.maximum(sr, 1e-9)[:, None]) * dv[:, None]
    return g.to_world(moved + c), dv


def _weld(points):
    _, canonical = np.unique(np.round(points, 6), axis=0, return_inverse=True)
    return canonical.ravel()


def rigid_small_parts(points, faces, displacement, size=None):
    """Move every small or flat part (a welded component) by the mean of its
    vertices' displacements, so no pass turns it inside out:

    * a part whose box is under ``size`` (SMALL_PART): a rivet, a buckle, a
      bead; a push that differs across a stud a few millimetres wide turns
      its closed shell inside out;
    * a closed part with next to no volume (under FLAT_PART x its box
      diagonal cubed): a two-sided card or tassel, whose signed volume flips
      with any bend;
    * any closed part the per-vertex move would turn inside out (its signed
      volume changes sign): a thin antler tine across the edge of an ear lobe.

    audit_canonical_batch.py fails a piece on an inward closed shell.
    Larger parts keep their per-vertex push."""
    from scipy.sparse import coo_matrix
    from scipy.sparse.csgraph import connected_components
    size = SMALL_PART if size is None else size
    if not len(faces):
        return displacement
    _, welded = np.unique(np.round(points, 5), axis=0, return_inverse=True)
    welded = welded.ravel()
    f = welded[faces]
    n = int(welded.max()) + 1
    graph = coo_matrix((np.ones(len(f) * 3), (np.concatenate([f[:, 0], f[:, 1], f[:, 2]]),
                                              np.concatenate([f[:, 1], f[:, 2], f[:, 0]]))), shape=(n, n))
    _, label = connected_components(graph, directed=False)
    part = label[welded]
    count = int(part.max()) + 1
    lo = np.full((count, 3), np.inf)
    hi = np.full((count, 3), -np.inf)
    np.minimum.at(lo, part, points)
    np.maximum.at(hi, part, points)
    diagonal = np.linalg.norm(hi - lo, axis=1)
    rigid = diagonal < size
    # closed (every welded edge used an even number of times) and flat parts
    face_part = part[faces[:, 0]]
    edges = np.sort(np.concatenate([f[:, [0, 1]], f[:, [1, 2]], f[:, [2, 0]]]), axis=1)
    _, inverse, used = np.unique(edges, axis=0, return_inverse=True, return_counts=True)
    odd = np.zeros(count, dtype=bool)
    np.logical_or.at(odd, np.tile(face_part, 3), (used[inverse.ravel()] % 2) == 1)
    centre = (lo + hi) / 2

    def volumes(p):
        q = p[faces] - centre[face_part][:, None]
        out = np.zeros(count)
        np.add.at(out, face_part, np.einsum('ij,ij->i', q[:, 0], np.cross(q[:, 1], q[:, 2])) / 6)
        return out
    volume = volumes(points)
    rigid |= ~odd & (np.abs(volume) < FLAT_PART * diagonal ** 3)
    rigid |= ~odd & (volume * volumes(points + displacement) <= 0)
    if not rigid.any():
        return displacement
    total = np.zeros((count, 3))
    np.add.at(total, part, displacement)
    mean = total / np.maximum(np.bincount(part, minlength=count), 1)[:, None]
    out = displacement.copy()
    rows = rigid[part]
    out[rows] = mean[part[rows]]
    return out


def seam_gaps(reference, points, tol=1e-5) -> dict:
    """Welded copies that a pass moved apart: vertices at one position in the
    reference (each vertex's position in the Human fit, carried through every
    pass) that no longer coincide.  An open UV seam is a see-through crack;
    rim vertices carry their own reference (pass_through), so a turned rim
    is not counted."""
    canon = _weld(np.asarray(reference, dtype=float))
    groups = int(canon.max(initial=-1)) + 1
    lo = np.full((groups, 3), np.inf)
    hi = np.full((groups, 3), -np.inf)
    np.minimum.at(lo, canon, points)
    np.maximum.at(hi, canon, points)
    spread = np.linalg.norm(hi - lo, axis=1)
    open_ = spread > tol
    return {'seamGaps': int(open_.sum()), 'seamGapMaxMm': round(float(spread.max(initial=0)) * 1000, 2)}


def refine(points, faces, uvs, select, max_edge=.008, rounds=2):
    """Split the selected triangles in four (``rounds`` times, while their
    longest edge exceeds ``max_edge``) with a red-green closure: a neighbour
    sharing one or two split edges is split to match, so the refined patch has
    no T-junction and later vertex moves cannot open a crack.  Edges are matched
    by welded position, so a UV seam splits on both sides (each keeping its
    own UVs).  ``select(points, faces)`` returns the face mask to split.
    Returns (points, faces, uvs, added faces)."""
    start = len(faces)
    for _ in range(rounds):
        mask = np.asarray(select(points, faces), dtype=bool)
        e = points[faces[:, [1, 2, 0]]] - points[faces]
        mask &= np.linalg.norm(e, axis=2).max(1) > max_edge
        if not mask.any():
            break
        canon = _weld(points)
        c = canon[faces]
        pairs = np.sort(np.stack([c[:, [0, 1]], c[:, [1, 2]], c[:, [2, 0]]], 1), axis=2)
        split = set(map(tuple, pairs[mask].reshape(-1, 2).tolist()))
        flags = np.array([[tuple(pair) in split for pair in face_pairs] for face_pairs in pairs.tolist()])
        new_p, new_uv, cache = list(points), list(uvs), {}

        def mid(i, j):
            key = (min(i, j), max(i, j))
            if key not in cache:
                cache[key] = len(new_p)
                new_p.append((points[i] + points[j]) / 2)
                new_uv.append((uvs[i] + uvs[j]) / 2)
            return cache[key]

        out = []
        for face, flag in zip(faces.tolist(), flags):
            n = int(flag.sum())
            if n == 0:
                out.append(face)
                continue
            if n == 3:
                a, b, cc = face
                ab, bc, ca = mid(a, b), mid(b, cc), mid(cc, a)
                out += [[a, ab, ca], [ab, b, bc], [ca, bc, cc], [ab, bc, ca]]
            elif n == 1:
                r = int(np.flatnonzero(flag)[0])
                a, b, cc = (face[(r + k) % 3] for k in range(3))
                m = mid(a, b)
                out += [[a, m, cc], [m, b, cc]]
            else:
                r = (int(np.flatnonzero(~flag)[0]) + 1) % 3
                a, b, cc = (face[(r + k) % 3] for k in range(3))
                m1, m2 = mid(a, b), mid(b, cc)
                out += [[a, m1, m2], [m1, b, m2], [a, m2, cc]]
        points, uvs, faces = np.asarray(new_p), np.asarray(new_uv), np.asarray(out, dtype=np.int64)
    return points, faces, uvs, len(faces) - start


def _near_faces(obstacle_tris, reach):
    """A refine selector: faces with a vertex, centroid or edge midpoint within
    ``reach`` of the obstacle."""
    from scipy.spatial import cKDTree
    tree = cKDTree(_samples(obstacle_tris))

    def select(points, faces):
        t = points[faces]
        probes = np.stack([t[:, 0], t[:, 1], t[:, 2], t.mean(1), (t[:, 0] + t[:, 1]) / 2,
                           (t[:, 1] + t[:, 2]) / 2, (t[:, 2] + t[:, 0]) / 2], 1)
        d, _ = tree.query(probes.reshape(-1, 3), distance_upper_bound=reach)
        return np.isfinite(d.reshape(len(faces), -1)).any(1)
    return select


def _bent_faces(g, delta, pole, tol=None):
    """A refine selector: faces the push would bend.  A face is split where
    the push at an edge midpoint or at the centroid differs by more than
    ``tol`` (BULGE_TOL) from the flat interpolation of its corners' pushes:
    a large outer-wall triangle whose corners all lie outside the bulge would
    otherwise stay flat while the refined inner wall bulges through it, and a
    face that the push only translates needs no split (the triangle budget)."""
    tol = BULGE_TOL if tol is None else tol

    def push(points):
        a, e, _ = _to_grid(g.to_local(points) - g.centre_local, pole)
        return delta[a, e]

    def select(points, faces):
        # The push over a grid of points inside each face (dense enough that
        # a bump inside a large face is seen) against the flat interpolation
        # of its corners' pushes.
        t = points[faces]
        corner = push(t.reshape(-1, 3)).reshape(len(faces), 3)
        samples, owner, weight = dense_samples(t, step=.006, cap=8, owners=True)
        flat = np.einsum('kc,kc->k', weight, corner[owner])
        bad = np.abs(push(samples) - flat) > tol
        out = np.zeros(len(faces), dtype=bool)
        out[owner[bad]] = True
        return out
    return select


def _bulge(g, obstacle, points, faces, uvs, clearance, name, even=False, tol=None, edge=None, **kw):
    if not len(obstacle):
        return points, faces, uvs, {'name': name, 'moved': 0, 'maxMm': 0.0, 'addedTriangles': 0}
    delta = radial_push(g, obstacle, points, clearance, grid_only=True, shell_tris=points[faces], **kw)
    # Only faces the push moves are split (BULGE_EDGE): the triangle budget
    # of a variant stays a few times the Human fit's.
    bent = _bent_faces(g, delta, kw.get('pole', 'y'), tol)
    p, f, uv, added = refine(points, faces, uvs, bent, max_edge=edge or BULGE_EDGE, rounds=3)
    _, dv = radial_push(g, obstacle, p, clearance, shell_tris=p[f], **kw)
    # A face standing edge-on to the push (a rim, a strap's side) turns over
    # when its corners, a degree apart, are pushed different amounts; on a
    # single-sided material it then vanishes and the piece shows a hole.
    # Such faces take their corners' largest push, until none turns over.
    local = g.to_local(p) - g.centre_local
    direction = (local / np.maximum(np.linalg.norm(local, axis=1), 1e-9)[:, None]) @ g.head[:3, :3].T
    # The push is evened over welded copies: a glTF mesh splits a vertex at
    # every UV seam, and copies pushed different amounts open the seam into
    # a see-through crack (a hole that no turned-over-face count sees).
    canon = _weld(p)
    groups = int(canon.max(initial=-1)) + 1
    evened = 0
    for _ in range(FLIP_ROUNDS if even else 0):
        flips = _flipped(p, p + direction * dv[:, None], f)
        if not flips.any():
            break
        evened += int(flips.sum())
        np.maximum.at(dv, f[flips].ravel(), np.repeat(dv[f[flips]].max(1), 3))
        welded = np.zeros(groups)
        np.maximum.at(welded, canon, dv)
        dv = welded[canon]
    moved = p + rigid_small_parts(p, f, direction * dv[:, None])
    return moved, f, uv, {'name': name, 'moved': int((dv > 1e-5).sum()),
                          'maxMm': round(float(dv.max(initial=0)) * 1000, 1), 'addedTriangles': int(added),
                          'evenedFaces': evened, 'flippedFaces': int(_flipped(p, moved, f).sum())}


def _flipped(before, after, faces) -> np.ndarray:
    """Faces a move turned over (normal reversed)."""
    def normal(points):
        t = points[faces]
        return np.cross(t[:, 1] - t[:, 0], t[:, 2] - t[:, 0])
    a, b = normal(before), normal(after)
    big = (np.linalg.norm(a, axis=1) > 1e-10) & (np.linalg.norm(b, axis=1) > 1e-10)
    return (np.einsum('ij,ij->i', a, b) < 0) & big


def ear_bulge(g: HeadGeometry, points, faces, uvs, rigid=False, even=False):
    """Rounded lobes over the ears (policy ``ears: tuck``).  On cloth,
    EAR_DILATE_DEG / EAR_DOME shape the lobe: a narrow flat top over the ear,
    then a parabolic fall to the shell, so the lobe follows the ear instead of
    standing out as a wing.  On a rigid helm the steeper fall folds the metal
    over (flipped faces read as holes), so a helm takes the broad, gentle
    lobe (BULGE_DILATE_DEG, BULGE_BLUR_DEG): an ear cup."""
    if rigid:
        return _bulge(g, g.ears, points, faces, uvs, EAR_CLEARANCE, 'ear_bulge', even,
                      tol=EAR_BULGE_TOL, edge=EAR_BULGE_EDGE)
    return _bulge(g, g.ears, points, faces, uvs, EAR_CLEARANCE, 'ear_bulge', even, tol=EAR_BULGE_TOL,
                  edge=EAR_BULGE_EDGE, dilate_deg=EAR_DILATE_DEG, blur_deg=EAR_BLUR_DEG, dome=EAR_DOME)


def horn_bulge(g: HeadGeometry, points, faces, uvs, even=False):
    """Drape the shell over the horn roots where a horn runs inside it; the
    part of the horn standing more than HORN_SWALLOW past the shell's inner
    wall is left to pierce it (horn_pass_through opens it there)."""
    return _bulge(g, g.features, points, faces, uvs, HORN_CLEARANCE, 'horn_bulge', even,
                  swallow=HORN_SWALLOW, limit=HORN_SWALLOW, pole='x')


def poking(g: HeadGeometry, tris, piece_tris, tol=.001):
    """The triangles of ``tris`` beyond the piece's outermost hit on their ray
    from the cranium centre (through a closed part of it, not an opening)."""
    if not len(tris):
        return tris
    r, _, t_out = _ray_extents(_intersector(piece_tris), g.origin, tris.mean(1))
    return tris[np.isfinite(t_out) & (r > t_out + tol)]


def head_bulge(g: HeadGeometry, points, faces, uvs, show_scalp, rigid=False, even=False):
    """Bulge the piece over whatever of the head still comes through it after
    the ears: a nose through a veil, a chin through a scarf, the back of a
    large cranium through a hood, a nape through a cap's hem.  Only the
    poking triangles are obstacles, so the push stays local.

    ``rigid`` (helms, already grown by helm_grow): the broad, gentle push of
    the ear cups instead of a tent, which folds a visor over itself."""
    head = np.concatenate([g.skin, g.scalp, g.neck_skin] if show_scalp else [g.skin, g.neck_skin])
    obstacle = poking(g, head, points[faces])
    if rigid:
        p, f, uv, r = _bulge(g, obstacle, points, faces, uvs, HEAD_CLEARANCE, 'head_bulge', even)
    else:
        # A flat dilation lifts every shell bin near a nose to the nose's
        # radius, boxing a visor or winging a veil out; a narrow dilation with
        # a parabolic falloff tents the shell over the point that pokes instead.
        p, f, uv, r = _bulge(g, obstacle, points, faces, uvs, HEAD_CLEARANCE, 'head_bulge', even,
                             dilate_deg=HEAD_DILATE_DEG, dome=HEAD_DOME)
    r['pokingTriangles'] = int(len(obstacle))
    return p, f, uv, r


def feature_bulge(g: HeadGeometry, points, faces, uvs, even=False):
    """Cover the Stoneborn crown / Glasswarden crystals under a show piece."""
    p, f, uv, r = _bulge(g, g.features, points, faces, uvs, FEATURE_CLEARANCE, 'feature_bulge', even,
                         dilate_deg=FEATURE_DILATE_DEG, blur_deg=FEATURE_BLUR_DEG, dome=FEATURE_DOME, pole='x')
    r['feature'] = g.feature_kind
    return p, f, uv, r


def band_feature_bulge(g: HeadGeometry, points, faces, uvs, even=False):
    """An open band over a crown or crystals (after band_grow): only the
    feature triangles that still come through the band push it, with the
    narrow tent of head_bulge.  feature_bulge's cover (every feature in a
    direction bin raises the whole bin) is a hood's: on a band it lifts the
    ring over crystals standing above it."""
    obstacle = poking(g, g.features, points[faces])
    p, f, uv, r = _bulge(g, obstacle, points, faces, uvs, FEATURE_CLEARANCE, 'band_feature_bulge', even,
                         dilate_deg=HEAD_DILATE_DEG, dome=HEAD_DOME, pole='x')
    r['pokingTriangles'] = int(len(obstacle))
    r['feature'] = g.feature_kind
    return p, f, uv, r


# ---------------------------------------------------------------------------
# Collar clearance
# ---------------------------------------------------------------------------

def _closest(tris, points):
    """Closest point on a triangle soup, its triangle's unit normal and the
    signed distance along it."""
    import trimesh
    mesh = trimesh.Trimesh(tris.reshape(-1, 3), np.arange(len(tris) * 3).reshape(-1, 3), process=False)
    q, dist, tri = np.empty((len(points), 3)), np.empty(len(points)), np.empty(len(points), dtype=np.int64)
    for chunk in _chunks(len(points), CLOSEST_CHUNK):
        q[chunk], dist[chunk], tri[chunk] = trimesh.proximity.closest_point(mesh, points[chunk])
    n = np.cross(tris[tri, 1] - tris[tri, 0], tris[tri, 2] - tris[tri, 0])
    n /= np.maximum(np.linalg.norm(n, axis=1, keepdims=True), 1e-12)
    return q, n, np.einsum('ij,ij->i', points - q, n), dist


def _spread(points, push, inner, outer):
    """Spread per-point push vectors: unchanged within ``inner``, fading to
    nothing at ``outer``; each point takes its strongest neighbour's push."""
    from scipy.spatial import cKDTree
    moving = np.flatnonzero(np.linalg.norm(push, axis=1) > 1e-6)
    if not len(moving):
        return push
    tree = cKDTree(points)
    best = np.zeros(len(points))
    result = np.zeros_like(push)
    for i in moving:
        size = float(np.linalg.norm(push[i]))
        for j in tree.query_ball_point(points[i], outer):
            d = float(np.linalg.norm(points[j] - points[i]))
            t = np.clip((d - inner) / (outer - inner), 0, 1)
            k = 1 - t * t * (3 - 2 * t)
            if size * k > best[j]:
                best[j] = size * k
                result[j] = push[i] * k
    return result


def _probes(points, faces):
    """Vertices, face centroids and edge midpoints of an indexed mesh."""
    t = points[faces]
    return np.concatenate([points, t.mean(1), (t[:, 0] + t[:, 1]) / 2, (t[:, 1] + t[:, 2]) / 2,
                           (t[:, 2] + t[:, 0]) / 2])


def _collar_targets(g: HeadGeometry, probes, reference):
    """The clearance each probe must reach: COLLAR_CLEARANCE, or, where the
    Human fit of the same point lies closer to (or inside) its own collar,
    the Human's distance.  A hood's wrap is tucked into the Human's collar by
    design; the race fit may be as deep, never deeper."""
    target = np.full(len(probes), COLLAR_CLEARANCE)
    if reference is None or not len(probes):
        return target
    human, human_probes = reference
    q, n, sd, dist = _closest(human.collar, human_probes)
    along = np.abs(np.einsum('ij,ij->i', human_probes - q, n)) >= .5 * np.maximum(dist, 1e-9)
    known = along | (dist < 1e-4)
    target = np.where(known, np.minimum(sd, COLLAR_CLEARANCE), COLLAR_CLEARANCE)
    # Deep inside the Human's own neck or shoulders (a hood's inner lining,
    # the under-chin part of a wrap) the piece is never seen: it is left
    # where it is.  Holding it to a 3 mm clearance instead dragged whole
    # curtains 45 mm out of the neck (three rounds at the step limit).
    return np.where(known & (sd < -COLLAR_INTERIOR), -np.inf, target)


def _needs_push(probes, q, n, sd, dist, target):
    """A probe inside (or within its target of) a collar face it lies over:
    the offset from its nearest point runs along that face's normal, so a
    point above the neck rim, inside the head, is never pushed."""
    along = np.abs(np.einsum('ij,ij->i', probes - q, n)) >= .5 * np.maximum(dist, 1e-9)
    return (sd < target) & (dist < COLLAR_REACH) & (along | (dist < 1e-4))


def _collar_need(g: HeadGeometry, probes, targets=None) -> np.ndarray:
    """Which probes (below the mouth) _collar_push would move."""
    if targets is None:
        targets = np.full(len(probes), COLLAR_CLEARANCE)
    out = np.zeros(len(probes), dtype=bool)
    test = np.flatnonzero(probes[:, 1] < g.eye_y - .040)
    if len(test):
        q, n, sd, dist = _closest(g.collar, probes[test])
        out[test] = _needs_push(probes[test], q, n, sd, dist, targets[test])
    return out


def _collar_push(g: HeadGeometry, points, faces, targets=None):
    """One round: push curtain vertices out of the shirt, the upper shared
    body and the lower neck to their target clearance (at most COLLAR_STEP).

    Tested at every vertex, face centroid and edge midpoint below the mouth (a
    large curtain triangle can be crossed between its corners by a convex
    shoulder); a sample's push goes to its face's vertices.  A sample counts
    as inside only where it lies over a collar face (the offset from its
    nearest point runs along that face's normal), so a point above the neck
    rim, inside the head, is never pushed.  ``targets`` (per probe, from
    _collar_targets) default to COLLAR_CLEARANCE."""
    top = g.eye_y - .040
    probes = _probes(points, faces)
    owners = [np.arange(len(points))[:, None], faces, faces[:, [0, 1]], faces[:, [1, 2]], faces[:, [2, 0]]]
    width = 3
    owner = np.full((len(probes), width), -1)
    at = 0
    for o in owners:
        owner[at:at + len(o), :o.shape[1]] = o
        at += len(o)
    if targets is None:
        targets = np.full(len(probes), COLLAR_CLEARANCE)
    test = np.flatnonzero(probes[:, 1] < top)
    push_size = np.zeros(len(points))
    push = np.zeros_like(points)
    if len(test):
        q, n, sd, dist = _closest(g.collar, probes[test])
        target = targets[test]
        need = _needs_push(probes[test], q, n, sd, dist, target)
        fade = np.clip((top - probes[test, 1]) / .03, 0, 1)
        amount = np.where(need, np.minimum(target - sd, COLLAR_STEP) * fade, 0.)
        order = np.argsort(amount)
        owner_sorted = owner[test[order]]
        amount_sorted = amount[order]
        normal_sorted = n[order]
        for k in range(width):
            v = owner_sorted[:, k]
            ok = (v >= 0) & (amount_sorted > 1e-6)
            vv, aa, nn = v[ok], amount_sorted[ok], normal_sorted[ok]
            # ascending order: where a vertex repeats, the strongest push is written last
            stronger = aa >= push_size[vv]
            push[vv[stronger]] = nn[stronger] * aa[stronger][:, None]
            np.maximum.at(push_size, vv, aa)
    return _spread(points, push, *COLLAR_SPREAD), int((push_size > 0).sum())


NECK_BIN = (.005, 5.0)    # metres of height, degrees round the neck axis


def neck_clearance(g: HeadGeometry, points):
    """Push points inside the neck out to its skin plus COLLAR_CLEARANCE,
    horizontally from the neck axis.  The neck is read as a radius per 5 mm of
    height and 5 degrees round its axis, from its near-vertical skin only, so
    a point in the jaw above the under-chin bridge has no neck to be inside."""
    if not len(g.neck):
        return np.zeros_like(points)
    from scipy.ndimage import grey_dilation
    samples = _samples(g.neck)
    y0 = samples[:, 1].min()
    nh = int(np.ceil((samples[:, 1].max() - y0) / NECK_BIN[0])) + 1
    na = int(round(360 / NECK_BIN[1]))

    def bins(pts):
        rel = pts[:, [0, 2]] - g.neck_axis
        r = np.linalg.norm(rel, axis=1)
        a = (np.degrees(np.arctan2(rel[:, 0], rel[:, 1])) % 360 / NECK_BIN[1]).astype(int) % na
        h = np.floor((pts[:, 1] - y0) / NECK_BIN[0]).astype(int)
        return h, a, r, rel
    h, a, r, _ = bins(samples)
    R = np.full((nh, na), -1.0)
    np.maximum.at(R, (h, a), r)
    R = grey_dilation(R, size=(3, 3), mode=('nearest', 'wrap'))
    ph, pa, pr, prel = bins(points)
    inside = (ph >= 0) & (ph < nh)
    need = np.zeros(len(points))
    idx = np.flatnonzero(inside)
    radius = R[ph[idx], pa[idx]]
    need[idx] = np.where(radius > 0, np.maximum(0, radius + COLLAR_CLEARANCE - pr[idx]), 0)
    push = np.zeros_like(points)
    out = prel / np.maximum(pr, 1e-9)[:, None]
    push[:, 0], push[:, 2] = out[:, 0] * need, out[:, 1] * need
    return _spread(points, push, *COLLAR_SPREAD)


def collar_clearance(g: HeadGeometry, points, faces, uvs, human: HeadGeometry | None = None):
    """Up to COLLAR_ROUNDS rounds of the shirt / shared body / lower neck.

    A drape's triangles near the collar are split first (COLLAR_REFINE): a
    coarse curtain triangle lies flat across a convex shoulder, so its corners
    can all clear the body while its middle does not.  With ``human`` (the
    Human body the piece was carried from), ``uvs[:, 2:5]`` hold every
    vertex's position in the Human fit and each point need only clear the
    collar as far as it clears the Human's (_collar_targets)."""
    added = 0
    if len(g.collar):
        top = g.eye_y - .040
        near = _near_faces(g.collar, COLLAR_REFINE)
        # Only round the samples that need a push (the triangle budget): a
        # drape that already clears the collar keeps its faces.
        probes = _probes(points, faces)
        targets = None
        if human is not None and uvs.shape[1] >= 5:
            targets = _collar_targets(g, probes, (human, _probes(uvs[:, 2:5], faces)))
        needing = probes[_collar_need(g, probes, targets)]
        if len(needing):
            from scipy.spatial import cKDTree
            tree = cKDTree(needing)

            def select(pp, ff):
                t = pp[ff]
                around = np.stack([t[:, 0], t[:, 1], t[:, 2], t.mean(1)], 1).reshape(-1, 3)
                d, _ = tree.query(around, distance_upper_bound=COLLAR_SPREAD[1])
                return (near(pp, ff) & (t[..., 1].min(1) < top)
                        & np.isfinite(d.reshape(len(ff), -1)).any(1))
            points, faces, uvs, added = refine(points, faces, uvs, select, max_edge=COLLAR_REFINE, rounds=2)
    start = points.copy()
    neck = neck_clearance(g, points) if NECK_PASS else np.zeros_like(points)
    points = points + neck
    rounds = 0
    if len(g.collar):
        targets = None
        if human is not None and uvs.shape[1] >= 5:
            targets = _collar_targets(g, _probes(points, faces), (human, _probes(uvs[:, 2:5], faces)))
        for rounds in range(1, COLLAR_ROUNDS + 1):
            step, pushed = _collar_push(g, points, faces, targets)
            if not pushed:
                break
            points = points + rigid_small_parts(points, faces, step)
    size = np.linalg.norm(points - start, axis=1)
    return points, faces, uvs, {'name': 'collar_clearance', 'moved': int((size > 1e-5).sum()),
                                'neckMaxMm': round(float(np.linalg.norm(neck, axis=1).max(initial=0)) * 1000, 1),
                                'maxMm': round(float(size.max(initial=0)) * 1000, 1), 'rounds': rounds,
                                'addedTriangles': int(added), 'humanReferenced': human is not None}


# ---------------------------------------------------------------------------
# Votary horns: openings with a turned rim
# ---------------------------------------------------------------------------

def _clip_scalar(points, faces, uvs, value):
    """Keep the part of the surface where ``value >= 0``; cut along the exact
    zero line, interpolating positions and UVs."""
    out_p, out_uv, out_v = list(points), list(uvs), list(value)
    cache = {}
    inside = value >= 0

    def cut(i, j):
        key = (min(i, j), max(i, j))
        if key not in cache:
            t = value[i] / (value[i] - value[j])
            cache[key] = len(out_p)
            out_p.append(points[i] * (1 - t) + points[j] * t)
            out_uv.append(uvs[i] * (1 - t) + uvs[j] * t)
            out_v.append(0.0)
        return cache[key]

    kept = []
    for face in faces:
        poly = []
        for i, j in zip(face, np.roll(face, -1)):
            if inside[i]:
                poly.append(int(i))
            if inside[i] != inside[j]:
                poly.append(cut(int(i), int(j)))
        if len(poly) >= 3:
            kept.extend([[poly[0], poly[k], poly[k + 1]] for k in range(1, len(poly) - 1)])
    kept = np.asarray(kept, dtype=np.int64).reshape(-1, 3)
    used, inverse = np.unique(kept, return_inverse=True)
    return (np.asarray(out_p)[used], inverse.reshape(-1, 3), np.asarray(out_uv)[used],
            np.isin(used, np.arange(len(points), len(out_p))))


def _signed_horn_distance(g: HeadGeometry, horn, points):
    """Distance to the horn surface, negative inside a horn.

    The horns are open shells standing on the capped skull, so inside is
    decided by parity along the radial ray (from the cranium centre outward):
    a point inside a horn leaves it once, a point under an arching horn
    crosses it twice or not at all."""
    import trimesh
    dist = _closest_distance(horn, points)
    direction = points - g.origin
    direction /= np.maximum(np.linalg.norm(direction, axis=1, keepdims=True), 1e-12)
    engine = trimesh.ray.ray_triangle.RayMeshIntersector(horn)
    hits = np.zeros(len(points), dtype=int)
    near = np.flatnonzero(dist < .05)
    for chunk in _chunks(len(near), RAY_CHUNK):
        rows = near[chunk]
        loc, ray, _ = engine.intersects_location(points[rows], direction[rows], multiple_hits=True)
        if len(ray):
            t = np.einsum('ij,ij->i', loc - points[rows][ray], direction[rows][ray])
            np.add.at(hits, rows[ray[t > 1e-7]], 1)
    return np.where(hits % 2 == 1, -dist, dist)


def _chunks(count, size):
    """Slices of at most ``size``: trimesh's ray and closest-point queries
    hold a candidate array per query, so one call over tens of thousands of
    points can take gigabytes (a single unchunked parity cast peaked at 22 GB)."""
    for start in range(0, count, size):
        yield slice(start, min(start + size, count))


def _closest_distance(mesh, points):
    import trimesh
    dist = np.empty(len(points))
    for chunk in _chunks(len(points), CLOSEST_CHUNK):
        dist[chunk] = trimesh.proximity.closest_point(mesh, points[chunk])[1]
    return dist


def _weld_components(points, faces, selected):
    """Connected components of the selected faces, welded by position (a glTF
    mesh splits its vertices at UV seams)."""
    from scipy.sparse import coo_matrix
    from scipy.sparse.csgraph import connected_components
    _, canonical = np.unique(np.round(points, 6), axis=0, return_inverse=True)
    canonical = canonical.ravel()
    f = canonical[faces[selected]]
    count = int(canonical.max()) + 1
    rows = np.concatenate([f[:, 0], f[:, 1]])
    cols = np.concatenate([f[:, 1], f[:, 2]])
    graph = coo_matrix((np.ones(len(rows)), (rows, cols)), shape=(count, count))
    _, label = connected_components(graph, directed=False)
    return label[canonical]


def horn_pass_through(g: HeadGeometry, points, faces, uvs):
    """Open the piece where a horn pierces it (8 mm round the piercing) and turn a rim in.

    Only shell regions that a horn actually enters are opened: a horn that
    runs along or arches over the piece within 8 mm of it, without entering
    it, leaves the shell whole."""
    return pass_through(g, g.features, points, faces, uvs, 'horn_pass_through', HORN_EDGE)


def snout_tris(g: HeadGeometry) -> np.ndarray:
    """The snout: the face in front of the eyes and below the brow.  The cheeks
    and the jaw behind the eyes are bulged over (head_bulge), not opened."""
    c = g.skin.mean(1)
    return g.skin[(c[:, 2] > g.eye_z - .01) & (c[:, 1] < g.eye_y + .03)]


def snout_opening(g: HeadGeometry, points, faces, uvs):
    """A rimmed opening in a rigid visor where the face comes through it.

    A Ssarathi snout stands up to 6 cm proud of a Human visor; pushing the
    metal out that far tears the visor off the helm, so the visor is opened
    round the snout the way a show hood is opened round a horn.  Runs only
    when the face of a snouted race (SNOUT_RACES) pokes through more than
    SNOUT_OPEN_CM2; a nose through a veil is bulged (head_bulge)."""
    if race_of(g.slug) not in SNOUT_RACES:
        return points, faces, uvs, {'name': 'snout_opening', 'openings': 0}
    snout = snout_tris(g)
    poke = radial_poke(g, _intersector(points[faces]), snout)
    if poke['pokeCm2'] <= SNOUT_OPEN_CM2:
        return points, faces, uvs, {'name': 'snout_opening', 'openings': 0, 'skipped': poke}
    p, f, uv, report = pass_through(g, snout, points, faces, uvs, 'snout_opening', SNOUT_EDGE)
    report['before'] = poke
    return p, f, uv, report


def helm_grow(g: HeadGeometry, points, faces, anchor):
    """Grow a rigid helm about the eye anchor (up to HELM_GROW_MAX) until the
    head stops coming through it: a bump pushed out of a metal shell reads as
    a dent or a crumpled visor, a slightly larger helm does not.

    The head is the feature-free race head and scalp, the face and jaw
    included (a Stoneborn jaw through a great helm's visor), except a snout
    (SNOUT_RACES), which snout_opening opens instead.  Only covered skin
    counts (radial_poke), so a face opening never grows the helm.  The
    smallest factor that leaves at most HELM_GROW_CM2 is taken; what still
    pokes at HELM_GROW_MAX is left to the broad head_bulge."""
    tris = np.concatenate([g.skin, g.scalp])
    if race_of(g.slug) in SNOUT_RACES:
        c = tris.mean(1)
        tris = tris[~((c[:, 2] > g.eye_z - .01) & (c[:, 1] < g.eye_y + .03))]
    anchor = np.asarray(anchor, dtype=float)

    def area(factor, shift=(0., 0., 0.)):
        moved = anchor + (points - anchor) * factor + np.asarray(shift)
        return radial_poke(g, _intersector(moved[faces]), tris)['pokeCm2']
    before = area(1.0)
    best, shift, after = 1.0, (0., 0., 0.), before
    if before > HELM_GROW_CM2:
        lo, hi = 1.0, HELM_GROW_MAX
        if area(hi) <= HELM_GROW_CM2:
            for _ in range(6):
                mid = (lo + hi) / 2
                lo, hi = (lo, mid) if area(mid) <= HELM_GROW_CM2 else (mid, hi)
        best = hi
        after = area(best)
        if after > HELM_GROW_CM2:
            # A chin or jaw still hangs under the front of the hem: the helm
            # is seated a little lower and further forward, never more than
            # HELM_SHIFT_MAX, at the smallest shift that clears it.
            for candidate in sorted(HELM_SHIFTS, key=lambda v: np.linalg.norm(v)):
                a = area(best, candidate)
                if a < after - .05:
                    shift, after = candidate, a
                if after <= HELM_GROW_CM2:
                    break
    moved = anchor + (points - anchor) * best + np.asarray(shift)
    return moved, {'name': 'helm_grow', 'factor': round(best, 4), 'shiftMm': [round(v * 1000, 1) for v in shift],
                   'pokeCm2Before': before, 'pokeCm2After': after, 'maxMm': 0.0}


@lru_cache(maxsize=32)
def hair_cap(slug: str) -> np.ndarray:
    """The hair an open band sits on: every offered style of the body (as
    headwear_envelope.py replays them from the installed client) within
    BAND_HAIR_REACH of the head, so buns and hanging locks, which stand
    beyond an open band by design, are left out."""
    from scipy.spatial import cKDTree
    import headwear_envelope
    hair = headwear_envelope.hair_triangles(slug)
    if not len(hair):
        return hair
    g = head_geometry(str(Path(headwear_envelope.CLIENT) / f'assets/actors/native/races/{slug}.glb'))
    head = _samples(np.concatenate([g.skin, g.scalp]))
    distance, _ = cKDTree(head).query(hair.mean(1), distance_upper_bound=BAND_HAIR_REACH)
    return hair[np.isfinite(distance)]


def band_grow(g: HeadGeometry, points, faces, anchor, obstacle, allowed_cm2):
    """Grow an open band about the eye anchor (up to BAND_GROW_MAX) until the
    hair cap, the head and the show features it rings stop coming through it
    beyond ``allowed_cm2`` (what the Human band leaves of the Human's own hair
    cap): a ring that pinches the hair reads as a band sunk into the head, a
    slightly larger one as a band worn over it."""
    anchor = np.asarray(anchor, dtype=float)

    def area(factor):
        moved = anchor + (points - anchor) * factor
        return radial_poke(g, _intersector(moved[faces]), obstacle)['pokeCm2']
    before = area(1.0)
    best, after = 1.0, before
    if before > allowed_cm2:
        lo, hi = 1.0, BAND_GROW_MAX
        if area(hi) <= allowed_cm2:
            for _ in range(5):
                mid = (lo + hi) / 2
                lo, hi = (lo, mid) if area(mid) <= allowed_cm2 else (mid, hi)
        best = hi
        after = area(best)
    moved = anchor + (points - anchor) * best
    return moved, {'name': 'band_grow', 'factor': round(best, 4), 'pokeCm2Before': before,
                   'pokeCm2After': after, 'allowedCm2': round(float(allowed_cm2), 2), 'maxMm': 0.0}


def pass_through(g: HeadGeometry, obstacle, points, faces, uvs, name, edge):
    """Open the piece where ``obstacle`` (a horn, a snout) pierces it, 8 mm
    round the piercing, and turn a rim in."""
    import trimesh
    report = {'name': name, 'removedTriangles': 0, 'openings': 0, 'rimTriangles': 0,
              'openedCm2': 0.0}
    if not len(obstacle):
        return points, faces, uvs, report
    horn = trimesh.Trimesh(obstacle.reshape(-1, 3), np.arange(len(obstacle) * 3).reshape(-1, 3), process=False)
    signed = _signed_horn_distance(g, horn, points)
    if not (signed < 0).any():
        return points, faces, uvs, report
    from scipy.spatial import cKDTree
    tree = cKDTree(_samples(obstacle))

    def crossing(pp, ff):
        # Only the faces the opening's edge runs through (or nearly): the cut
        # is round where it is, and the rest of the shell keeps its faces.
        # Faces far from the obstacle are ruled out before the (costly)
        # signed distance is taken.
        t = pp[ff]
        size = np.linalg.norm(t[:, [1, 2, 0]] - t, axis=2).max(1)
        gap, _ = tree.query(t.mean(1))
        candidate = np.flatnonzero(gap < size + HORN_OPENING + .01)
        out = np.zeros(len(ff), dtype=bool)
        if not len(candidate):
            return out
        tc = t[candidate]
        probes = np.concatenate([tc.reshape(-1, 3), tc.mean(1)])
        value = _signed_horn_distance(g, horn, probes) - HORN_OPENING
        corner = value[:len(candidate) * 3].reshape(-1, 3)
        centre = value[len(candidate) * 3:]
        low = np.minimum(corner.min(1), centre)
        high = np.maximum(corner.max(1), centre)
        out[candidate] = (low < size[candidate]) & (high > -size[candidate])
        return out
    p, f, uv, _ = refine(points, faces, uvs, crossing, max_edge=edge, rounds=2)
    signed = _signed_horn_distance(g, horn, p)
    within = signed[f].min(1) < HORN_OPENING
    label = _weld_components(p, f, within)
    pierced = set(label[np.flatnonzero(signed < 0)])
    opened = np.isin(label, list(pierced)) & (signed < HORN_OPENING)
    value = np.where(opened, signed - HORN_OPENING, np.maximum(signed - HORN_OPENING, 1e-4))
    area = np.linalg.norm(np.cross(p[f[:, 1]] - p[f[:, 0]], p[f[:, 2]] - p[f[:, 0]]), axis=1) / 2
    report['openedCm2'] = round(float(area[(value[f] < 0).all(1)].sum() * 1e4), 1)
    before = len(f)
    p2, f2, uv2, created = _clip_scalar(p, f, uv, value)
    report['removedTriangles'] = int(before - len(f2))
    # The opening's edge: boundary edges (in the welded mesh, so a UV seam is
    # not an edge) whose both ends the cut created.  Each gets a rim quad; a
    # rim vertex is made per vertex copy, so where the edge crosses a UV seam
    # the rim is split the same way (and stays closed).
    canon = _weld(p2)
    e = np.concatenate([f2[:, [0, 1]], f2[:, [1, 2]], f2[:, [2, 0]]])
    key = np.sort(canon[e], axis=1)
    _, inv, cnt = np.unique(key, axis=0, return_inverse=True, return_counts=True)
    edge = e[(cnt[inv.ravel()] == 1) & created[e[:, 0]] & created[e[:, 1]]]
    if len(edge):
        from scipy.sparse import coo_matrix
        from scipy.sparse.csgraph import connected_components
        n = int(canon.max()) + 1
        graph = coo_matrix((np.ones(len(edge)), (canon[edge[:, 0]], canon[edge[:, 1]])), shape=(n, n))
        _, label = connected_components(graph, directed=False)
        report['openings'] = len(set(label[canon[edge[:, 0]]].tolist()))
        ring = np.unique(edge.ravel())
        inward = g.origin - p2[ring]
        inward /= np.maximum(np.linalg.norm(inward, axis=1, keepdims=True), 1e-12)
        rim = dict(zip(ring.tolist(), range(len(p2), len(p2) + len(ring))))
        rim_uv = uv2[ring].copy()
        if rim_uv.shape[1] >= 5:
            # its own reference (seam_gaps): the rim leaves the shell on purpose
            rim_uv[:, 2:5] += inward * HORN_RIM
        # one winding: every headwear material is double sided
        rim_f = [[b, a, rim[a]] for a, b in edge.tolist()] + [[b, rim[a], rim[b]] for a, b in edge.tolist()]
        p2 = np.vstack([p2, p2[ring] + inward * HORN_RIM])
        uv2 = np.vstack([uv2, rim_uv])
        f2 = np.vstack([f2, np.asarray(rim_f, dtype=np.int64)])
        report['rimTriangles'] = len(rim_f)
    return p2, f2, uv2, report


# ---------------------------------------------------------------------------
# Measurements (the gates)
# ---------------------------------------------------------------------------

def _intersector(tris):
    try:
        import trimesh
    except ImportError:
        # A checkout without trimesh (CI installs numpy, scipy, PIL, pytest):
        # the measurements run on the numpy ray caster.
        return NumpyRays(tris)
    mesh = trimesh.Trimesh(tris.reshape(-1, 3), np.arange(len(tris) * 3).reshape(-1, 3), process=False)
    return trimesh.ray.ray_triangle.RayMeshIntersector(mesh)


class NumpyRays:
    """The two queries of trimesh's RayMeshIntersector the measurements use
    (``intersects_location``, ``intersects_any``) in numpy: a bounding-sphere
    cull per block of rays, then the Moller-Trumbore test on what is left.
    Hits are strictly in front of the origin, as trimesh's are."""
    BLOCK = 64

    def __init__(self, tris):
        t = np.asarray(tris, dtype=float).reshape(-1, 3, 3)
        self.v0, self.e1, self.e2 = t[:, 0], t[:, 1] - t[:, 0], t[:, 2] - t[:, 0]
        self.centre = t.mean(1)
        self.radius2 = (np.linalg.norm(t - self.centre[:, None], axis=2).max(1) + 1e-7) ** 2

    def _hits(self, origins, directions):
        origins = np.asarray(origins, dtype=float)
        directions = np.asarray(directions, dtype=float)
        rays, tris, dist = [np.empty(0, dtype=np.int64)], [np.empty(0, dtype=np.int64)], [np.empty(0)]
        for start in range(0, len(origins), self.BLOCK):
            o, d = origins[start:start + self.BLOCK], directions[start:start + self.BLOCK]
            rel = self.centre[None] - o[:, None]
            along = np.einsum('rtk,rk->rt', rel, d) / np.einsum('rk,rk->r', d, d)[:, None]
            near = np.einsum('rtk,rtk->rt', rel, rel) - along ** 2 * np.einsum('rk,rk->r', d, d)[:, None]
            r, t = np.nonzero((near <= self.radius2[None]) & (along * np.linalg.norm(d, axis=1)[:, None]
                                                               >= -np.sqrt(self.radius2)[None]))
            if not len(r):
                continue
            dd, s = d[r], o[r] - self.v0[t]
            p = np.cross(dd, self.e2[t])
            det = np.einsum('ik,ik->i', p, self.e1[t])
            ok = np.abs(det) > 1e-18
            inv = 1.0 / np.where(ok, det, 1.0)
            u = np.einsum('ik,ik->i', s, p) * inv
            q = np.cross(s, self.e1[t])
            v = np.einsum('ik,ik->i', dd, q) * inv
            w = np.einsum('ik,ik->i', q, self.e2[t]) * inv
            hit = ok & (u >= -1e-9) & (v >= -1e-9) & (u + v <= 1 + 1e-9) & (w > 1e-12)
            rays.append(r[hit] + start)
            tris.append(t[hit])
            dist.append(w[hit])
        return np.concatenate(rays), np.concatenate(tris), np.concatenate(dist)

    def intersects_location(self, origins, directions, multiple_hits=True):
        ray, tri, w = self._hits(origins, directions)
        if not multiple_hits and len(ray):
            order = np.lexsort((w, ray))
            ray, tri, w = ray[order], tri[order], w[order]
            first = np.r_[True, ray[1:] != ray[:-1]]
            ray, tri, w = ray[first], tri[first], w[first]
        loc = np.asarray(origins, dtype=float)[ray] + np.asarray(directions, dtype=float)[ray] * w[:, None]
        return loc, ray, tri

    def intersects_any(self, origins, directions):
        ray, _, _ = self._hits(origins, directions)
        out = np.zeros(len(origins), dtype=bool)
        out[ray] = True
        return out


def _ray_extents(engine, origin, points):
    direction = points - origin
    r = np.linalg.norm(direction, axis=1)
    direction /= np.maximum(r, 1e-12)[:, None]
    origins = np.broadcast_to(origin, points.shape).copy()
    t_in = np.full(len(points), np.inf)
    t_out = np.full(len(points), -np.inf)
    for start in range(0, len(points), RAY_CHUNK):
        sl = slice(start, start + RAY_CHUNK)
        loc, ray, _ = engine.intersects_location(origins[sl], direction[sl], multiple_hits=True)
        if len(ray):
            t = np.einsum('ij,ij->i', loc - origins[sl][ray], direction[sl][ray])
            ray = ray + start
            ok = t > 1e-4
            np.minimum.at(t_in, ray[ok], t[ok])
            np.maximum.at(t_out, ray[ok], t[ok])
    return r, t_in, t_out


def radial_poke(g: HeadGeometry, engine, tris, tol=.001):
    """Area (cm2) and depth (mm) of triangles beyond the piece's outermost hit
    on the ray from the cranium centre; uncovered triangles do not count."""
    if not len(tris):
        return {'pokeCm2': 0.0, 'maxPokeMm': 0.0, 'insideCm2': 0.0}
    c = tris.mean(1)
    area = np.linalg.norm(np.cross(tris[:, 1] - tris[:, 0], tris[:, 2] - tris[:, 0]), axis=1) / 2
    r, t_in, t_out = _ray_extents(engine, g.origin, c)
    hit = np.isfinite(t_out)
    poke = hit & (r > t_out + tol)
    inside = hit & ~poke & (r > t_in + tol)
    depth = np.where(poke, r - t_out, 0) * 1000
    return {'pokeCm2': round(float(area[poke].sum() * 1e4), 2),
            'maxPokeMm': round(float(depth.max(initial=0)), 1),
            'insideCm2': round(float(area[inside].sum() * 1e4), 2)}


def edge_crossings(engine, a, b):
    """Edges (a -> b) that cross the piece's surface."""
    if not len(a):
        return 0
    d = b - a
    length = np.linalg.norm(d, axis=1)
    d = d / np.maximum(length, 1e-12)[:, None]
    count = 0
    for chunk in _chunks(len(a), RAY_CHUNK):
        loc, ray, _ = engine.intersects_location(a[chunk], d[chunk], multiple_hits=False)
        if len(ray):
            count += int((np.linalg.norm(loc - a[chunk][ray], axis=1) < length[chunk][ray] - 1e-7).sum())
    return count


def piece_triangles(path, socket_world):
    """The piece's triangles in character space, hung at ``socket_world``."""
    d, b = ea.read_glb(Path(path))
    world = ea.global_matrices(d)
    tris = []
    for i, node in enumerate(d['nodes']):
        if 'mesh' not in node:
            continue
        m = np.asarray(world[i])
        for p in d['meshes'][node['mesh']]['primitives']:
            v = ea.accessor_array(d, b, p['attributes']['POSITION']).astype(float) @ m[:3, :3].T + m[:3, 3]
            tris.append(v[ea.accessor_array(d, b, p['indices']).astype(int).reshape(-1, 3)])
    return np.concatenate(tris) + np.asarray(socket_world)


def measure(g: HeadGeometry, tris, key=None) -> dict:
    """All gate values for one fitted piece (triangles in character space)."""
    engine = _intersector(tris)
    out = {'ears': radial_poke(g, engine, g.ears), 'skin': radial_poke(g, engine, g.skin),
           'scalp': radial_poke(g, engine, g.scalp),
           'neck': radial_poke(g, engine, g.neck_skin),
           'bodyCrossings': edge_crossings(engine, *g.edges) if len(g.edges) else 0,
           'collarCrossings': edge_crossings(engine, *g.collar_edges) if len(g.collar_edges) else 0,
           'collarClipCm2': collar_clip(engine, g.collar_surface) if len(g.collar_surface) else 0.0}
    # The features are drawn only under a show piece (the hide pieces hide
    # race_feature_head), and only horns are gated on crossings (a crown or
    # crystals on poke): the feature rays are most of a measurement's cost.
    shown = key is None or policy(key).get('raceFeatures') == 'show'
    if len(g.features) and shown:
        out['features'] = radial_poke(g, engine, g.features)
        if g.feature_kind == 'horns':
            out['featureCrossings'] = edge_crossings(engine, *g.feature_edges)
    if key is not None and policy(key).get('kind') == 'band':
        # an open band shows the hair: the hair cap through it (Human: the baseline)
        out['hairCap'] = radial_poke(g, engine, hair_cap(g.slug))
    return out
