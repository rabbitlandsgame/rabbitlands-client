"""Hand a set-level design fit to the torso and limb remappers.

Added 2026-10-16.  ``design_fit_blender.py`` (run in Blender) fits the
pieces of one armour set together, on the posed body, and writes for each
original source ``<source>.npz`` under ``eloria-assets/source/equipment-design-fit/<body>/``:
rest positions in the rig's axes, four joint names and weights per vertex, and
the fitted shell in the idle pose it was solved in.  When such a file exists
for the source and body being fitted, torso_remap and limb_head_remap take the
shell from it instead of their own per-piece retarget; backings, inseams,
normals, materials and the GLB are built as before.

The file pins the source, body and set-spec hashes it was solved against, and
``override`` refuses one whose source or body no longer match, so a stale fit
can never be packed onto a changed body.
"""
from __future__ import annotations

import hashlib
from functools import lru_cache
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1] / "source" / "equipment-design-fit"
#: 2 (2026-10-17): the npz also carries each vertex's arm share and the idle
#: skinning matrices, for bind_sleeves.
FORMAT = 2
#: A triangle the rest pose stretches past this multiple of its fitted (idle)
#: edge length bridges the sleeve and the coat; it is opened like torso_remap's
#: fused seams and the fitted backing closes it.
MAX_STRETCH = 2.5


@lru_cache(maxsize=64)
def _digest(path: str) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def path_for(source: Path, rig) -> Path:
    return ROOT / rig.source_slug / (source.name.removesuffix(".orig") + ".npz")


def override(source: Path, rig, body_path: Path | None = None):
    """The design-fit shell for ``source`` on ``rig``'s body, or None.

    ``source`` is the file the remapper reads (``.glb.orig``); the npz is keyed
    by the source name without that suffix.  Returns positions (N, 3), joint
    indices into ``rig.joint_names`` (N, 4), weights (N, 4), the posed shell and
    the file's digest.
    """
    path = path_for(source, rig)
    if not path.exists():
        return None
    data = np.load(path)
    if int(data["format"]) != FORMAT:
        raise ValueError(f"{path.name}: design-fit format {int(data['format'])} != {FORMAT}")
    if str(data["source_sha256"]) != _digest(str(source)):
        raise ValueError(f"{path}: solved against a different source; rebuild the design fit")
    if body_path is not None and str(data["body_sha256"]) != _digest(str(body_path)):
        raise ValueError(f"{path}: solved against a different body; rebuild the design fit")
    names = [str(n) for n in data["joint_names"]]
    lookup = np.array([rig.joint_names.index(n) for n in names])
    joints = lookup[data["joints"].astype(int)].astype(np.uint16)
    weights = data["weights"].astype(np.float64)
    weights /= np.maximum(weights.sum(1, keepdims=True), 1e-12)
    skin = np.tile(np.eye(4), (len(rig.joint_names), 1, 1))
    skin[lookup] = data["skin"]
    return {"positions": data["positions"].astype(np.float64), "joints": joints,
            "weights": weights, "posed": data["posed"].astype(np.float64),
            "arm_share": data["arm_share"].astype(np.float64), "skin": skin,
            "scale": float(data["scale"]), "sha256": _digest(str(path)), "file": path.name}


def inverse_skin(posed, joints, weights, skin):
    """Rest positions whose linear-blend skinning gives ``posed`` (rig axes)."""
    blend = np.einsum("nk,nkij->nij", weights, skin[joints.astype(int)])
    return np.linalg.solve(blend, np.c_[posed, np.ones(len(posed))][..., None])[:, :3, 0]


def seam_distance(points, triangles, part, limit):
    """Surface (welded-graph) distance from each vertex to the seam between parts, inf past ``limit``."""
    from scipy.sparse import coo_matrix
    from scipy.sparse.csgraph import dijkstra
    key = np.unique(np.round(points / 1e-5).astype(np.int64), axis=0, return_inverse=True)[1].ravel()
    count = int(key.max()) + 1
    first = np.zeros(count, dtype=int); first[key] = np.arange(len(points))
    edges = np.r_[triangles[:, [0, 1]], triangles[:, [1, 2]], triangles[:, [2, 0]]]
    a, b = key[edges[:, 0]], key[edges[:, 1]]
    length = np.maximum(np.linalg.norm(points[first[a]] - points[first[b]], axis=1), 1e-9)
    graph = coo_matrix((length, (a, b)), shape=(count, count)).tocsr()
    seam = np.unique(key[triangles[np.ptp(part[triangles], axis=1) > 0].ravel()])
    if not len(seam):
        return np.full(len(points), np.inf)
    return dijkstra(graph, directed=False, indices=seam, min_only=True, limit=limit)[key]


#: A sleeve/coat seam triangle the fit itself stretches past this multiple of
#: its source size (the piece's scale) spans a gap the fit opened between
#: sleeve and coat; it is cut, as before, and the fitted lining shows behind.
SEAM_STRETCH = 1.6
#: Width (rig units) of the band across the sleeve/coat seam over which the
#: arm field and the fit's trunk weights blend: on the sleeve, on the coat.
SLEEVE_BAND, COAT_BAND = .05, .06


def bind_sleeves(fit, rig, triangles, passes=2, source=None):
    """Bind sleeves with torso_remap's continuous arm field, keeping the idle shell.

    The design fit weights every vertex from the posed body surface nearest it
    in idle, where the arms hang against the coat: a sleeve's inner wall picks
    up chest weights and its hem stays behind as the arm rises, so a drawn bow
    tore every sleeve into shards. As torso_remap binds its sleeves, each
    vertex the fit gave to an arm (``arm_share`` > .5) instead follows that
    arm by its rest position along the upper arm and forearm (lowerarm from
    43% to 59% of the way to the wrist). The trunk keeps the fit's weights,
    tassets on thighs included.

    Across the seam the two blend (revised after the owner's second review,
    2026-10-17). A hard switch with the sleeve/coat bridges opened let the arm
    slide through the coat's arm hole in idle and walk and opened gaps at the
    armpit and the back of the shoulder in a drawn bow. Now, over a band
    SLEEVE_BAND wide on the sleeve and COAT_BAND on the coat (surface
    distance from the seam), each side takes a share of the other's
    weights, half at the seam and none at the band's edge, so the arm hole
    moves with the arm and the seam stays sewn. The weights are smoothed over
    the whole mesh, and the rest pose is then solved again from the idle shell
    (``inverse_skin``), so the client still returns the fitted shell exactly
    in idle; two passes let the arm field see the sleeves' new rest positions.

    Only seam triangles the fit already stretched in idle past SEAM_STRETCH
    times their ``source`` size (raw art, the piece's scale applied) are cut:
    sewn, they smeared the art across the gap (the Studded Jack's back beside
    the sleeve). keep_triangles still opens any bridge the rest pose
    overstretches. Returns rest positions, joints, weights and the triangles
    to keep.
    """
    import equipment_seams
    from equipment_skinning import smoothstep
    posed, skin = fit["posed"], fit["skin"]
    part = np.where(fit["arm_share"][:, 0] > .5, 1, np.where(fit["arm_share"][:, 1] > .5, 2, 0))
    rest, joints, weights = fit["positions"], fit["joints"], fit["weights"]
    count = len(rig.joint_names)
    trunk_fit = np.zeros((len(rest), count))
    for slot in range(joints.shape[1]):
        np.add.at(trunk_fit, (np.arange(len(rest)), joints[:, slot].astype(int)), weights[:, slot])
    scale = rig.fit_scale
    distance = seam_distance(posed, triangles, part, max(SLEEVE_BAND, COAT_BAND) * scale)
    on_sleeve = .5 * (1 - smoothstep(distance, 0., SLEEVE_BAND * scale))
    on_coat = .5 * (1 - smoothstep(distance, 0., COAT_BAND * scale))
    for _ in range(passes):
        dense = trunk_fit.copy()
        for col, side in enumerate("lr"):
            root, wrist = rig.origin("upperarm_" + side), rig.origin("hand_" + side)
            axis = wrist - root
            lower = smoothstep((rest - root) @ axis / (axis @ axis), .43, .59)
            field = np.zeros((len(rest), count))
            field[:, rig.joint_names.index("upperarm_" + side)] = 1 - lower
            field[:, rig.joint_names.index("lowerarm_" + side)] = lower
            own = part == col + 1
            dense[own] = ((1 - on_sleeve[own])[:, None] * field[own]
                          + on_sleeve[own][:, None] * trunk_fit[own])
            near = (part == 0) & (on_coat > 0) & ((rest[:, 0] > 0) == (side == "l"))
            dense[near] = ((1 - on_coat[near])[:, None] * trunk_fit[near]
                           + on_coat[near][:, None] * field[near])
        joints = np.argsort(-dense, axis=1)[:, :4].astype(np.uint16)
        weights = np.take_along_axis(dense, joints.astype(int), axis=1)
        weights /= np.maximum(weights.sum(axis=1, keepdims=True), 1e-12)
        joints, weights = equipment_seams.smooth_skin(rest, triangles, joints, weights, count, strength=2.)
        rest = inverse_skin(posed, joints, weights, skin)
    keep = np.ones(len(triangles), dtype=bool)
    if source is not None:
        seam = np.ptp(part[triangles], axis=1) > 0
        stretch = np.ones(len(triangles))
        for a, b in ((0, 1), (1, 2), (2, 0)):
            fitted = np.linalg.norm(posed[triangles[:, a]] - posed[triangles[:, b]], axis=1)
            drawn = np.linalg.norm(source[triangles[:, a]] - source[triangles[:, b]], axis=1) * fit["scale"]
            stretch = np.maximum(stretch, fitted / np.maximum(drawn, 1e-9))
        keep = ~(seam & (stretch > SEAM_STRETCH))
    return rest, joints, weights, keep


def keep_triangles(fit, triangles) -> np.ndarray:
    """Triangles to keep: drop the bridges the rest pose stretches (see MAX_STRETCH)."""
    rest, posed = fit["positions"], fit["posed"]
    stretch = np.ones(len(triangles))
    for a, b in ((0, 1), (1, 2), (2, 0)):
        before = np.linalg.norm(posed[triangles[:, a]] - posed[triangles[:, b]], axis=1)
        after = np.linalg.norm(rest[triangles[:, a]] - rest[triangles[:, b]], axis=1)
        stretch = np.maximum(stretch, after / np.maximum(before, 1e-9))
    return stretch < MAX_STRETCH


def source_coordinates(points, fit, raw, neighbours=4):
    """Carry fitted-space points (a backing) back into the original art's space.

    The design fit is a blend of per-bone similarities followed by an inverse
    skin, with no closed-form inverse; near the shell it is locally a scale by
    the piece's girth scale.  Each point returns through its nearest rest-shell
    vertices: their source positions plus the offset undone by that scale, so
    a backing samples the art of the shell it sits under.
    """
    from scipy.spatial import cKDTree
    rest = fit["positions"]
    distance, index = cKDTree(rest).query(points, k=neighbours)
    weight = 1.0 / np.maximum(distance, 1e-5) ** 2
    weight /= weight.sum(1, keepdims=True)
    offset = (points[:, None, :] - rest[index]) / fit["scale"]
    return (weight[..., None] * (raw[index] + offset)).sum(1)
