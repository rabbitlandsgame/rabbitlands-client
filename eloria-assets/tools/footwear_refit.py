#!/usr/bin/env python3
"""The runtime's garment refit, run offline so it can be measured.

One authored mesh is worn by sixteen bodies.  It is not worn *as authored*: the
client rebinds it to the wearer's skeleton and lets it out per bone, and the
shape a player actually sees is the result of that, not the file on disk.
Measuring the authored file against another race therefore answers a question
nobody asked.  This module reproduces ``replicated_actor_3d.gd``'s
``_rebound_skin`` exactly - the same rig fit scale, the same per-bone span
ratio, the same girth widening, the same clamps - so a fit report for a race
that is not the authored one is the geometry that race will really wear.

The chain, per bone ``b``::

    vertex' = sum_b weight_b * target_rest_b * (fit * scale_b) * author_rest_b^-1 * vertex

``fit`` is the whole-rig height ratio, ``scale_b`` the per-bone widening, and
both are uniform scales about the origin - deliberately, because skinning
carries normals through the same matrix and only a uniform scale leaves them
correct.
"""
from __future__ import annotations

import json
import struct
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

import numpy as np

from garment_fit import _DTYPES, _WIDTHS, _document

#: ``_bone_fit``'s clamps, and ``_girth_ratios``'s, copied from the client.
SPAN_CLAMP = (0.4, 2.5)
SCALE_CLAMP = (1.0, 2.0)
GIRTH_CLAMP = (1.0, 2.0)
#: Below this the client returns the plain fit scale rather than a widened one.
SCALE_DEADBAND = 0.02
#: ``_ground_ratios``'s clamp. Wider than the girth clamp at the bottom end
#: because this one is allowed to take a boot in.
GROUND_CLAMP = (0.5, 2.0)


def _accessor(document: dict, binary: bytes, index: int) -> np.ndarray:
    spec = document["accessors"][index]
    view = document["bufferViews"][spec["bufferView"]]
    dtype = np.dtype(_DTYPES[spec["componentType"]])
    width = _WIDTHS[spec["type"]]
    start = view.get("byteOffset", 0) + spec.get("byteOffset", 0)
    stride = view.get("byteStride", dtype.itemsize * width)
    shape = (spec["count"],) if width == 1 else (spec["count"], width)
    strides = (stride,) if width == 1 else (stride, dtype.itemsize)
    values = np.ndarray(shape, dtype=dtype, buffer=binary, offset=start,
                        strides=strides).copy()
    if spec.get("normalized") and dtype.kind == "u":
        values = values.astype(np.float64) / np.iinfo(dtype).max
    return values


def _node_matrix(node: dict) -> np.ndarray:
    if "matrix" in node:
        return np.asarray(node["matrix"], dtype=np.float64).reshape(4, 4).T
    matrix = np.eye(4)
    if "scale" in node:
        matrix = np.diag([*node["scale"], 1.0]) @ matrix
    if "rotation" in node:
        x, y, z, w = node["rotation"]
        rotation = np.array([
            [1 - 2 * (y * y + z * z), 2 * (x * y - z * w), 2 * (x * z + y * w), 0],
            [2 * (x * y + z * w), 1 - 2 * (x * x + z * z), 2 * (y * z - x * w), 0],
            [2 * (x * z - y * w), 2 * (y * z + x * w), 1 - 2 * (x * x + y * y), 0],
            [0, 0, 0, 1]])
        matrix = rotation @ matrix
    if "translation" in node:
        move = np.eye(4)
        move[:3, 3] = node["translation"]
        matrix = move @ matrix
    return matrix


@dataclass(frozen=True)
class Skeleton:
    """A rig's rest pose, by bone name, in the space the GLB was written in."""

    rest: dict[str, np.ndarray]
    children: dict[str, list[str]]

    def head_y(self) -> float:
        for name in ("Head", "head", "head_01"):
            if name in self.rest:
                return float(self.rest[name][1, 3])
        raise KeyError("rig carries no head bone to scale against")


@lru_cache(maxsize=64)
def skeleton(path: str) -> Skeleton:
    """Global rest matrices of every joint in a GLB's skin."""
    document, _ = _document(Path(path))
    nodes = document.get("nodes", [])
    parent: dict[int, int] = {}
    for index, node in enumerate(nodes):
        for child in node.get("children", []):
            parent[child] = index
    globals_: dict[int, np.ndarray] = {}

    def resolve(index: int) -> np.ndarray:
        if index not in globals_:
            local = _node_matrix(nodes[index])
            owner = parent.get(index)
            globals_[index] = local if owner is None else resolve(owner) @ local
        return globals_[index]

    joints = document.get("skins", [{}])[0].get("joints", [])
    rest, children = {}, {}
    for index in joints:
        name = str(nodes[index].get("name", ""))
        rest[name] = resolve(index)
        children[name] = [str(nodes[child].get("name", ""))
                          for child in nodes[index].get("children", [])]
    return Skeleton(rest=rest, children=children)


@dataclass
class SkinnedMesh:
    """One skinned primitive as the runtime sees it."""

    positions: np.ndarray
    triangles: np.ndarray
    joints: np.ndarray
    weights: np.ndarray
    bones: list[str]
    author_rest: dict[str, np.ndarray]


def skinned_primitives(path: Path) -> list[SkinnedMesh]:
    document, binary = _document(Path(path))
    skins = document.get("skins", [])
    if not skins:
        return []
    nodes = document.get("nodes", [])
    bones = [str(nodes[index].get("name", "")) for index in skins[0]["joints"]]
    inverse_binds = _accessor(document, binary,
                              skins[0]["inverseBindMatrices"]).reshape(-1, 4, 4)
    # glTF stores matrices column-major; the authored global rest is the inverse
    # of the inverse bind, which is what ``author_rest`` is in the client.
    author_rest = {name: np.linalg.inv(inverse_binds[index].T)
                   for index, name in enumerate(bones)}
    result = []
    for mesh in document.get("meshes", []):
        for primitive in mesh["primitives"]:
            attributes = primitive["attributes"]
            if "JOINTS_0" not in attributes:
                continue
            result.append(SkinnedMesh(
                positions=_accessor(document, binary,
                                    attributes["POSITION"]).astype(np.float64),
                triangles=_accessor(document, binary,
                                    primitive["indices"]).astype(np.int64).reshape(-1, 3),
                joints=_accessor(document, binary, attributes["JOINTS_0"]).astype(np.int64),
                weights=_accessor(document, binary,
                                  attributes["WEIGHTS_0"]).astype(np.float64),
                bones=bones, author_rest=author_rest))
    return result


def girth_ratios(registry: dict, author_rig: str, wearer_rig: str) -> dict[str, float]:
    """``_girth_ratios``: how much broader the wearer is, bone by bone."""
    if not author_rig or author_rig == wearer_rig:
        return {}
    table = registry.get("bodyGirth", {})
    author, wearer = table.get(author_rig, {}), table.get(wearer_rig, {})
    if not author or not wearer:
        return {}
    ratios = {}
    for bone, value in author.items():
        source, target = float(value), float(wearer.get(bone, 0.0))
        if source > .0005 and target > .0005:
            ratios[bone] = float(np.clip(target / source, *GIRTH_CLAMP))
    return ratios


def ground_drops(registry: dict, author_rig: str, wearer_rig: str,
                 skin_region: str) -> dict[str, tuple]:
    """``_ground_drops``: where each foot sits relative to the joint carrying it.

    Footwear only.  Every other region is refitted by stature and girth as
    before.  The value is a signed offset from the bone origin to the foot -
    across and along in the ground plane, and down to the floor the body rests
    on - so the pair of them says where the authored boot would land and where
    this body's foot actually is.
    """
    if skin_region != "boots" or not author_rig or author_rig == wearer_rig:
        return {}
    table = registry.get("footAnchor", {})
    author, wearer = table.get(author_rig, {}), table.get(wearer_rig, {})
    if not author or not wearer:
        return {}
    # Per bone, not one datum for the whole chain: collapsing them onto the
    # ankle's figure was measured and was five times worse, because the shell is
    # skinned rather than rigid and shears instead of moving.
    drops = {}
    for bone, value in author.items():
        source = np.asarray(value, dtype=np.float64)
        target = np.asarray(wearer.get(bone, []), dtype=np.float64)
        if source.shape == (3,) and target.shape == (3,):
            drops[bone] = (source, target)
    return drops


def _widening(bone: str, author_rest: dict[str, np.ndarray], target: Skeleton,
              girth: float) -> float:
    """``clampf(maxf(ratio, girth), 1.0, 2.0)`` - how much broader to cut."""
    ratio = 1.0
    kin = [child for child in target.children.get(bone, []) if child in author_rest]
    if kin and bone in target.rest:
        author_tip = np.mean([author_rest[child][:3, 3] for child in kin], axis=0)
        target_tip = np.mean([target.rest[child][:3, 3] for child in kin], axis=0)
        rest = author_rest.get(bone)
        if rest is not None:
            local = np.linalg.inv(rest) @ np.append(author_tip, 1.0)
            author_span = float(np.linalg.norm(local[:3]))
            target_span = float(np.linalg.norm(target_tip - target.rest[bone][:3, 3]))
            if author_span > .0005 and target_span > .0005:
                ratio = float(np.clip(target_span / author_span, *SPAN_CLAMP))
    return float(np.clip(max(ratio, girth), *SCALE_CLAMP))


def _bone_basis(bone: str, author_rest: dict[str, np.ndarray], target: Skeleton,
                fit: float, girth: float, ground: float = 0.0) -> np.ndarray:
    """``_bone_fit``, as the 3x3 it resolves to in the authored bone's space."""
    ratio = 1.0
    axis = np.array([0., 1., 0.])
    measured = False
    kin = [child for child in target.children.get(bone, []) if child in author_rest]
    if kin and bone in target.rest:
        author_tip = np.mean([author_rest[child][:3, 3] for child in kin], axis=0)
        target_tip = np.mean([target.rest[child][:3, 3] for child in kin], axis=0)
        rest = author_rest.get(bone)
        if rest is not None:
            local = np.linalg.inv(rest) @ np.append(author_tip, 1.0)
            author_span = float(np.linalg.norm(local[:3]))
            target_span = float(np.linalg.norm(target_tip - target.rest[bone][:3, 3]))
            if author_span > .0005 and target_span > .0005:
                ratio = float(np.clip(target_span / author_span, *SPAN_CLAMP))
                axis = local[:3] / author_span
                measured = True
    across = float(np.clip(max(ratio, girth), *SCALE_CLAMP))
    along = across if not measured else float(np.clip(ratio, *SPAN_CLAMP))
    if abs(across - 1.0) < SCALE_DEADBAND and abs(along - 1.0) < SCALE_DEADBAND:
        return np.eye(3) * fit
    return fit * (np.eye(3) * across + np.outer(axis, axis) * (along - across))


def _bone_scale(bone: str, author_rest: dict[str, np.ndarray], target: Skeleton,
                fit: float, girth: float, ground: float = 0.0) -> float:
    """The isotropic part, for callers that only want a single number."""
    basis = _bone_basis(bone, author_rest, target, fit, girth)
    return float(np.cbrt(abs(np.linalg.det(basis))))


def refit(piece: SkinnedMesh, wearer: Skeleton, canonical_head_y: float,
          girth: dict[str, float], ground: dict[str, float] | None = None) -> np.ndarray:
    """Linear-blend the authored positions onto the wearer's rest pose."""
    fit = wearer.head_y() / canonical_head_y if canonical_head_y > 0 else 1.0
    matrices = np.zeros((len(piece.bones), 4, 4))
    for index, bone in enumerate(piece.bones):
        rest = wearer.rest.get(bone)
        author = piece.author_rest.get(bone)
        if rest is None or author is None:
            matrices[index] = np.eye(4)
            continue
        drops = (ground or {}).get(bone)
        middle = np.eye(4)
        if drops:
            # Widened, then moved to the floor: see ``_bone_fit`` in the client.
            wide = _widening(bone, piece.author_rest, wearer,
                             float(girth.get(bone, 1.0)))
            middle[:3, :3] = np.eye(3) * (fit * wide)
            landed, wanted = drops[0] * (fit * wide), drops[1]
            move = wanted - landed
            middle[:3, 3] = np.linalg.inv(rest[:3, :3]) @ move
        else:
            middle[:3, :3] = _bone_basis(bone, piece.author_rest, wearer, fit,
                                         float(girth.get(bone, 1.0)))
        matrices[index] = rest @ middle @ np.linalg.inv(author)

    homogeneous = np.concatenate(
        [piece.positions, np.ones((len(piece.positions), 1))], axis=1)
    weights = piece.weights
    total = weights.sum(axis=1, keepdims=True)
    weights = np.divide(weights, total, out=np.zeros_like(weights), where=total > 0)
    moved = np.zeros((len(piece.positions), 3))
    for slot in range(piece.joints.shape[1]):
        bone_index = np.clip(piece.joints[:, slot], 0, len(piece.bones) - 1)
        weight = weights[:, slot:slot + 1]
        if not weight.any():
            continue
        transformed = np.einsum("nij,nj->ni", matrices[bone_index], homogeneous)
        moved += weight * transformed[:, :3]
    return moved


def worn_geometry(boot: Path, wearer_rig: Path, registry: dict, author_rig: str,
                  skin_region: str = "boots") -> list[tuple[np.ndarray, np.ndarray]]:
    """The garment's geometry as ``wearer_rig`` will actually wear it."""
    wearer = skeleton(str(wearer_rig))
    canonical = float(registry.get("canonicalHeadRestY", 0.0))
    name = Path(wearer_rig).stem
    girth = girth_ratios(registry, author_rig, name)
    ground = ground_drops(registry, author_rig, name, skin_region)
    result = []
    for piece in skinned_primitives(boot):
        result.append((refit(piece, wearer, canonical, girth, ground),
                       piece.triangles))
    return result
