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
FORMAT = 1
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
    return {"positions": data["positions"].astype(np.float64), "joints": joints,
            "weights": weights, "posed": data["posed"].astype(np.float64),
            "scale": float(data["scale"]), "sha256": _digest(str(path)), "file": path.name}


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
