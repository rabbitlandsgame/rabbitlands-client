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


def bind_sleeves(fit, rig, triangles, passes=2):
    """Bind sleeves with torso_remap's continuous arm field, keeping the idle shell.

    The design fit weights every vertex from the posed body surface nearest it
    in idle, where the arms hang against the coat: a sleeve's inner wall picks
    up chest weights and its hem stays behind as the arm rises, so a drawn bow
    tore every sleeve into shards. As torso_remap binds its sleeves, each
    vertex the fit gave to an arm (``arm_share`` > .5) instead follows that
    arm by its rest position along the upper arm and forearm (lowerarm from
    43% to 59% of the way to the wrist). The trunk keeps the fit's weights,
    tassets on thighs included. The weights are smoothed over the mesh with
    the sleeve/coat bridges opened, again as torso_remap does, except across the
    shoulder yoke. The rest pose is then solved again from the idle shell
    (``inverse_skin``), so the client still returns the fitted shell exactly
    in idle; two passes let the arm field see the sleeves' new rest positions.

    Returns rest positions, joints, weights and the triangles to keep.
    """
    import equipment_seams
    from equipment_skinning import smoothstep
    posed, skin = fit["posed"], fit["skin"]
    part = np.where(fit["arm_share"][:, 0] > .5, 1, np.where(fit["arm_share"][:, 1] > .5, 2, 0))
    rest, joints, weights = fit["positions"], fit["joints"], fit["weights"]
    # Bridges between a sleeve and the coat open; the shoulder yoke above the
    # arm root stays sewn (torso_remap's shoulder_seam).
    yoke = min(rig.origin("upperarm_l")[1], rig.origin("upperarm_r")[1]) - .03 * rig.fit_scale
    same = np.ptp(part[triangles], axis=1) == 0
    keep = same | (rest[triangles, 1].min(axis=1) > yoke)
    count = len(rig.joint_names)
    for _ in range(passes):
        dense = np.zeros((len(rest), count))
        for slot in range(joints.shape[1]):
            np.add.at(dense, (np.arange(len(rest)), joints[:, slot].astype(int)), weights[:, slot])
        for col, side in enumerate("lr"):
            own = part == col + 1
            root, wrist = rig.origin("upperarm_" + side), rig.origin("hand_" + side)
            axis = wrist - root
            lower = smoothstep((rest[own] - root) @ axis / (axis @ axis), .43, .59)
            dense[own] = 0.
            dense[own, rig.joint_names.index("upperarm_" + side)] = 1 - lower
            dense[own, rig.joint_names.index("lowerarm_" + side)] = lower
        joints = np.argsort(-dense, axis=1)[:, :4].astype(np.uint16)
        weights = np.take_along_axis(dense, joints.astype(int), axis=1)
        weights /= np.maximum(weights.sum(axis=1, keepdims=True), 1e-12)
        joints, weights = equipment_seams.smooth_skin(rest, triangles[keep], joints, weights, count, strength=2.)
        rest = inverse_skin(posed, joints, weights, skin)
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
