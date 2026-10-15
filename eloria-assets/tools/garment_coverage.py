#!/usr/bin/env python3
"""Does a garment actually cover the body underneath it, in every pose?

Renamed from ``garment_fit`` on 2026-08-30 for Eloria Client.  Two sessions
wrote a coverage checker at that name within a day of each other and the second
landed on top of the first, which left ``legwear_fit`` importing six names -
``Component``, ``FitReport``, ``body_points``, ``check``, ``covered_region``,
``garment_components`` - that no longer existed anywhere in the tree.  The two
modules answer different questions and both are wanted, so they now have
different names: ``garment_fit`` is the rest-pose enclosure check the footwear
and legwear sets are measured with, and this is the posed-coverage sweep the
torso set needs.

Added 2026-08-29 for Eloria Client.  Coverage used to be judged by looking at
it, which is how "there are still gaps in the shoulder areas of the shirt"
survived several rounds of fixing: a seam that closes in the T-pose the rig is
authored in opens the moment the arm leaves it, and a bind-pose screenshot
never shows that.

The measurement is enclosure by ray-cast parity - a body vertex is covered when
a ray leaving it crosses the garment an odd number of times - with two details
that decide whether the number means anything.

**Components, not primitives.**  A torso garment's body shell, its two sleeves
and its shoulder caps are separate closed volumes packed into one glTF
primitive.  Parity run over the whole primitive reports a point inside two of
them as *outside*, because it crosses an even number of faces.  Every primitive
is therefore split into connected components over position-welded edges, the
closed ones are kept, and a point counts as covered when it is inside **any** of
them.  The same mistake on the footwear reported 142 vertices poking through
where the real number was 14.

**The wearer's body, not the author's.**  A garment is authored once and refit
per race at runtime, so checking it against the rig it was built on proves
nothing about the fifteen other races that wear it.  ``refit`` reproduces the
runtime's own transform - the fit scale, the per-bone span ratio and the girth
widening from ``equipment.json`` - so the shell measured here is the shell the
player sees.

Poses come from the shared animation library and are applied to garment and
body alike, so a shoulder can be asked the only question that matters: is it
still closed at full abduction?
"""
from __future__ import annotations

import argparse
import json
import math
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path

import numpy as np

from equipment_authoring import (accessor_array, global_matrices, read_gltf,
                                 CANONICAL_HEAD_REST_Y)

#: Vertices closer together than this are the same point.  Lofts emit each ring
#: twice where two surfaces meet, so without welding every seam reads as a
#: boundary and no shell is ever closed.
WELD = 1e-5

#: A body vertex is allowed to sit this far outside the garment before it counts
#: as showing through.  Zero would fail on floating-point noise at a seam the
#: garment shares with the skin it wraps.
SKIN_TOLERANCE = 2.0e-4

#: How much of a garment's own opening is excluded from what it is answerable
#: for, measured along the arm.
#:
#: A sleeve ends somewhere.  The ring of skin lying in the plane of that opening
#: is *at* the edge of the cloth, and whether it reads as inside or outside turns
#: on tenths of a millimetre once an elbow bends and slides the arm within the
#: sleeve.  Widening the cuff does not help: the opening moves out with it and
#: the same ring of skin arrives at the new rim.  Eight vertices on the back of
#: each forearm behaved exactly this way, at ``Jog`` and at no other clip.
#:
#: So the last centimetre of an opening is excluded, deliberately and in one
#: place rather than by quietly widening a tolerance.  It does not touch the
#: shoulder figure - the shoulder band is up against the torso, a long way
#: inboard of any cuff - and a garment that shrank away from the arm would show
#: it as a fall in ``checked``, not as a pass.
OPENING_RIM = .012


# ---------------------------------------------------------------------------
# Geometry
# ---------------------------------------------------------------------------

@dataclass
class Primitive:
    """One glTF primitive: positions, triangles and the skin binding them."""

    points: np.ndarray            # (n, 3)
    triangles: np.ndarray         # (m, 3) int
    joints: np.ndarray | None     # (n, 4) int
    weights: np.ndarray | None    # (n, 4) float


@dataclass
class Skeleton:
    """The joint hierarchy of one GLB, in the space its meshes are authored in."""

    names: list[str]
    rest: dict[str, np.ndarray]           # bone -> 4x4 global rest
    inverse_bind: dict[str, np.ndarray]   # bone -> 4x4
    parent: dict[str, str | None]
    node_local: dict[str, np.ndarray] = field(default_factory=dict)

    @property
    def fit_scale(self) -> float:
        head = self.rest.get("Head")
        return float(head[1, 3]) / CANONICAL_HEAD_REST_Y if head is not None else 1.0

    def children(self, bone: str) -> list[str]:
        return [name for name, owner in self.parent.items() if owner == bone]

    def tip(self, bone: str) -> np.ndarray | None:
        """Where the bone's chain continues, or None for a leaf."""
        kids = [c for c in self.children(bone) if not c.endswith("_leaf")]
        if not kids:
            return None
        return np.mean([self.rest[c][:3, 3] for c in kids], axis=0)


def _quaternion(values) -> np.ndarray:
    x, y, z, w = (float(v) for v in values)
    return np.array([
        [1 - 2 * (y * y + z * z), 2 * (x * y - z * w), 2 * (x * z + y * w)],
        [2 * (x * y + z * w), 1 - 2 * (x * x + z * z), 2 * (y * z - x * w)],
        [2 * (x * z - y * w), 2 * (y * z + x * w), 1 - 2 * (x * x + y * y)]])


def _local_matrix(node: dict) -> np.ndarray:
    if "matrix" in node:
        return np.array(node["matrix"], dtype=np.float64).reshape(4, 4).T
    matrix = np.eye(4)
    if "scale" in node:
        matrix = matrix @ np.diag([*node["scale"], 1.0])
    if "rotation" in node:
        rotation = np.eye(4)
        rotation[:3, :3] = _quaternion(node["rotation"])
        matrix = rotation @ matrix
    if "translation" in node:
        translation = np.eye(4)
        translation[:3, 3] = node["translation"]
        matrix = translation @ matrix
    return matrix


@lru_cache(maxsize=64)
def load(path: str) -> tuple[tuple[Primitive, ...], Skeleton, tuple[str, ...]]:
    """Primitives, skeleton and per-primitive mesh names of one GLB."""
    document, binary = read_gltf(Path(path))
    nodes = document["nodes"]
    matrices = global_matrices(document)
    parent_of: dict[int, int] = {}
    for index, node in enumerate(nodes):
        for child in node.get("children", []):
            parent_of[child] = index

    skin = (document.get("skins") or [{}])[0]
    joint_nodes = skin.get("joints", [])
    names = [nodes[node].get("name", "") for node in joint_nodes]
    rest = {names[i]: matrices[node] for i, node in enumerate(joint_nodes)}
    node_local = {names[i]: _local_matrix(nodes[node])
                  for i, node in enumerate(joint_nodes)}
    inverse_bind: dict[str, np.ndarray] = {}
    if "inverseBindMatrices" in skin:
        raw = accessor_array(document, binary, skin["inverseBindMatrices"])
        raw = np.asarray(raw, dtype=np.float64).reshape(-1, 4, 4)
        for index, name in enumerate(names):
            inverse_bind[name] = raw[index].T
    parent: dict[str, str | None] = {}
    for index, node in enumerate(joint_nodes):
        owner = parent_of.get(node)
        owner_name = nodes[owner].get("name", "") if owner is not None else None
        parent[names[index]] = owner_name if owner_name in names else None

    primitives: list[Primitive] = []
    mesh_names: list[str] = []
    for node in nodes:
        if "mesh" not in node:
            continue
        mesh = document["meshes"][node["mesh"]]
        for primitive in mesh["primitives"]:
            attributes = primitive["attributes"]
            if "indices" not in primitive:
                continue
            points = accessor_array(document, binary,
                                    attributes["POSITION"]).astype(np.float64)
            triangles = accessor_array(document, binary,
                                       primitive["indices"]).astype(np.int64).reshape(-1, 3)
            joints = weights = None
            if "JOINTS_0" in attributes and "WEIGHTS_0" in attributes:
                joints = accessor_array(document, binary,
                                        attributes["JOINTS_0"]).astype(np.int64)
                weights = accessor_array(document, binary,
                                         attributes["WEIGHTS_0"]).astype(np.float64)
                # WEIGHTS_0 may be float, normalized u8 or normalized u16, and
                # the accessor reader hands back the raw integers.  glTF
                # requires the four weights of a vertex to sum to one, so
                # rescaling by their own sum decodes every encoding without
                # having to branch on componentType.
                total = weights.sum(axis=1, keepdims=True)
                weights = weights / np.where(total > 0, total, 1.0)
            primitives.append(Primitive(points, triangles, joints, weights))
            mesh_names.append(mesh.get("name", ""))
    return tuple(primitives), Skeleton(names, rest, inverse_bind, parent,
                                       node_local), tuple(mesh_names)


# ---------------------------------------------------------------------------
# Closed components
# ---------------------------------------------------------------------------

def weld_map(points: np.ndarray, tolerance: float = WELD) -> np.ndarray:
    """Index of the canonical vertex each point collapses onto."""
    keys = np.round(points / tolerance).astype(np.int64)
    _, inverse = np.unique(keys, axis=0, return_inverse=True)
    return inverse.ravel()


class _Union:
    def __init__(self, size: int) -> None:
        self.parent = np.arange(size)

    def find(self, node: int) -> int:
        root = node
        while self.parent[root] != root:
            root = self.parent[root]
        while self.parent[node] != root:
            self.parent[node], node = root, self.parent[node]
        return root

    def union(self, left: int, right: int) -> None:
        left, right = self.find(left), self.find(right)
        if left != right:
            self.parent[right] = left


@dataclass
class Shell:
    """One connected component of a primitive, and whether it closes."""

    points: np.ndarray
    triangles: np.ndarray
    closed: bool
    volume: float


def components(points: np.ndarray, triangles: np.ndarray) -> list[Shell]:
    """Split a primitive into connected shells over position-welded edges.

    This is the step that decides whether the whole measurement means anything.
    A garment's overlapping closed volumes live in one primitive, and parity run
    across all of them cancels: a point genuinely inside the body shell *and*
    inside a shoulder cap crosses four faces on its way out and reports as
    uncovered.
    """
    if len(triangles) == 0:
        return []
    welded = weld_map(points)
    union = _Union(int(welded.max()) + 1)
    for a, b in ((0, 1), (1, 2), (2, 0)):
        for left, right in zip(welded[triangles[:, a]], welded[triangles[:, b]]):
            union.union(int(left), int(right))
    roots = np.array([union.find(int(v)) for v in welded[triangles[:, 0]]])
    shells: list[Shell] = []
    for root in np.unique(roots):
        face = triangles[roots == root]
        used = np.unique(face)
        remap = np.full(len(points), -1, dtype=np.int64)
        remap[used] = np.arange(len(used))
        local_points = points[used]
        local_faces = remap[face]
        # Boundary edges, counted on the welded topology so a seam where two
        # rings coincide is not mistaken for a hole.
        local_weld = weld_map(local_points)
        edges = np.concatenate([
            local_weld[local_faces[:, [0, 1]]],
            local_weld[local_faces[:, [1, 2]]],
            local_weld[local_faces[:, [2, 0]]]])
        edges = np.sort(edges, axis=1)
        _, counts = np.unique(edges, axis=0, return_counts=True)
        closed = bool((counts % 2 == 0).all())
        middle = local_points.mean(axis=0)
        local = local_points - middle
        # Double-sided flat decoration can have paired boundary edges while
        # enclosing no space. It is a sheet, not an inside-out volume. Keep
        # true (including inverted or very thin) 3D shells in the winding test.
        if closed and np.linalg.matrix_rank(local) < 3:
            closed = False
        volume = float(np.einsum(
            "ij,ij->i", local[local_faces[:, 0]],
            np.cross(local[local_faces[:, 1]], local[local_faces[:, 2]])).sum() / 6.0)
        shells.append(Shell(local_points, local_faces, closed, volume))
    return shells


# ---------------------------------------------------------------------------
# Enclosure
# ---------------------------------------------------------------------------

class Enclosure:
    """Inside-test for a set of closed shells, by ray parity along +X.

    Triangles are binned by their (y, z) footprint so a query only intersects
    the few hundred that could possibly be in its way.  Without that this runs
    for hours across sixty-four designs, sixteen races and six poses.
    """

    def __init__(self, shells: list[Shell], cell: float = .02) -> None:
        self.shells = [shell for shell in shells if shell.closed]
        self.cell = cell
        self._grids = []
        self._bounds = []
        for shell in self.shells:
            self._bounds.append((shell.points.min(axis=0), shell.points.max(axis=0)))
            corners = shell.points[shell.triangles]        # (m, 3, 3)
            low = corners[:, :, 1:].min(axis=1)
            high = corners[:, :, 1:].max(axis=1)
            origin = low.min(axis=0) - cell
            span = np.maximum(np.ceil((high.max(axis=0) + cell - origin) / cell), 1).astype(int)
            buckets: dict[tuple[int, int], list[int]] = {}
            lo = np.floor((low - origin) / cell).astype(int)
            hi = np.floor((high - origin) / cell).astype(int)
            for index in range(len(corners)):
                for row in range(lo[index, 0], hi[index, 0] + 1):
                    for column in range(lo[index, 1], hi[index, 1] + 1):
                        buckets.setdefault((row, column), []).append(index)
            self._grids.append((origin, span, {key: np.array(value)
                                               for key, value in buckets.items()},
                                corners))

    def inside(self, points: np.ndarray, tolerance: float = SKIN_TOLERANCE) -> np.ndarray:
        """True for every point enclosed by at least one shell."""
        covered = np.zeros(len(points), dtype=bool)
        if not self.shells:
            return covered
        # Skip shells that cannot contain any of these points.  When a wearer's
        # trousers are on, most of what is in here is two leg tubes and a boot,
        # none of which is ever going to enclose a shoulder; testing them anyway
        # made the full audit hours rather than minutes.
        low, high = points.min(axis=0), points.max(axis=0)
        reach = range(len(self.shells))
        # The tolerance is applied by pulling each query point towards the body
        # centreline, so a vertex sitting exactly on the garment's inner wall -
        # which is where a close-cut shell puts most of them - reads as inside.
        probe = points.copy()
        radial = probe[:, [0, 2]]
        length = np.linalg.norm(radial, axis=1, keepdims=True)
        probe[:, [0, 2]] = radial * (1.0 - tolerance / np.maximum(length, 1e-6))
        for index in reach:
            bounds = self._bounds[index]
            if (bounds[1] < low - 1e-6).any() or (bounds[0] > high + 1e-6).any():
                continue
            (origin, span, buckets, corners) = self._grids[index]
            remaining = np.flatnonzero(~covered)
            if len(remaining) == 0:
                break
            cells = np.floor((probe[remaining][:, 1:] - origin) / self.cell).astype(int)
            for slot, point_index in enumerate(remaining):
                key = (int(cells[slot, 0]), int(cells[slot, 1]))
                candidates = buckets.get(key)
                if candidates is None:
                    continue
                if self._parity(probe[point_index], corners[candidates]):
                    covered[point_index] = True
        return covered

    @staticmethod
    def _parity(point: np.ndarray, corners: np.ndarray) -> bool:
        """Odd number of +X crossings through these triangles?

        Solved in the (y, z) plane: the ray is axis-aligned, so a triangle is
        crossed when the point is inside its projected footprint and the
        intersection lies ahead of the point along x.
        """
        a, b, c = corners[:, 0], corners[:, 1], corners[:, 2]
        py, pz = point[1], point[2]
        # Barycentric coordinates of the point in each projected triangle.
        v0 = b[:, 1:] - a[:, 1:]
        v1 = c[:, 1:] - a[:, 1:]
        v2 = np.stack([py - a[:, 1], pz - a[:, 2]], axis=1)
        denominator = v0[:, 0] * v1[:, 1] - v1[:, 0] * v0[:, 1]
        alive = np.abs(denominator) > 1e-14
        if not alive.any():
            return False
        u = np.zeros(len(a))
        v = np.zeros(len(a))
        u[alive] = (v2[alive, 0] * v1[alive, 1] - v1[alive, 0] * v2[alive, 1]) / denominator[alive]
        v[alive] = (v0[alive, 0] * v2[alive, 1] - v2[alive, 0] * v0[alive, 1]) / denominator[alive]
        hit = alive & (u >= 0) & (v >= 0) & (u + v <= 1)
        if not hit.any():
            return False
        x = a[hit, 0] + u[hit] * (b[hit, 0] - a[hit, 0]) + v[hit] * (c[hit, 0] - a[hit, 0])
        return bool(np.count_nonzero(x > point[0]) % 2 == 1)



def _closest_on_triangles(points: np.ndarray, corners: np.ndarray):
    """Nearest point on each triangle, for every query point.

    Returns ``(distance, offset, normal)`` shaped (points, triangles, ...).
    Plain Ericson point-triangle clamping, vectorised over both axes.
    """
    a, b, c = corners[:, 0], corners[:, 1], corners[:, 2]
    ab, ac = b - a, c - a
    normal = np.cross(ab, ac)
    length = np.linalg.norm(normal, axis=1, keepdims=True)
    normal = normal / np.maximum(length, 1e-16)
    ap = points[:, None, :] - a[None, :, :]
    d1 = np.einsum("ptk,tk->pt", ap, ab)
    d2 = np.einsum("ptk,tk->pt", ap, ac)
    bp = points[:, None, :] - b[None, :, :]
    d3 = np.einsum("ptk,tk->pt", bp, ab)
    d4 = np.einsum("ptk,tk->pt", bp, ac)
    cp = points[:, None, :] - c[None, :, :]
    d5 = np.einsum("ptk,tk->pt", cp, ab)
    d6 = np.einsum("ptk,tk->pt", cp, ac)
    va = d3 * d6 - d5 * d4
    vb = d5 * d2 - d1 * d6
    vc = d1 * d4 - d3 * d2
    denominator = np.maximum(va + vb + vc, 1e-16)
    v = np.clip(vb / denominator, 0.0, 1.0)
    w = np.clip(vc / denominator, 0.0, 1.0)
    # Region tests, applied in the order the barycentric solution degrades.
    vertex_a = (d1 <= 0) & (d2 <= 0)
    vertex_b = (d3 >= 0) & (d4 <= d3)
    vertex_c = (d6 >= 0) & (d5 <= d6)
    edge_ab = (vc <= 0) & (d1 >= 0) & (d3 <= 0)
    edge_ac = (vb <= 0) & (d2 >= 0) & (d6 <= 0)
    edge_bc = (va <= 0) & ((d4 - d3) >= 0) & ((d5 - d6) >= 0)
    v = np.where(vertex_a | vertex_c | edge_ac, 0.0, v)
    w = np.where(vertex_a | vertex_b | edge_ab, 0.0, w)
    v = np.where(vertex_b, 1.0, v)
    w = np.where(vertex_c, 1.0, w)
    with np.errstate(divide="ignore", invalid="ignore"):
        t_ab = np.nan_to_num(d1 / np.where(d1 - d3 == 0, 1e-16, d1 - d3))
        t_ac = np.nan_to_num(d2 / np.where(d2 - d6 == 0, 1e-16, d2 - d6))
        t_bc = np.nan_to_num((d4 - d3) / np.where((d4 - d3) - (d5 - d6) == 0, 1e-16,
                                                 (d4 - d3) - (d5 - d6)))
    v = np.where(edge_ab, np.clip(t_ab, 0, 1), v)
    w = np.where(edge_ac, np.clip(t_ac, 0, 1), w)
    bc = np.clip(t_bc, 0, 1)
    v = np.where(edge_bc, 1.0 - bc, v)
    w = np.where(edge_bc, bc, w)
    closest = (a[None] + v[:, :, None] * ab[None] + w[:, :, None] * ac[None])
    offset = points[:, None, :] - closest
    return np.linalg.norm(offset, axis=2), offset, normal


def open_surface_exposed(points: np.ndarray, shells: "list[Shell]", *,
                         reach: float = .045,
                         tolerance: float = SKIN_TOLERANCE) -> np.ndarray:
    """Skin showing through a garment that is *not* a closed shell.

    Parity needs a closed volume, and the garments this work replaces are stacks
    of open tubes - not one of them encloses anything, so parity reports every
    vertex uncovered and the before column of a comparison says nothing about
    where the holes actually are.  This is the weaker test that still works on
    an open sheet: a vertex is covered when the nearest garment surface within
    reach faces away from it.  It is only ever used to describe the old shells;
    acceptance is decided by ``Enclosure``.
    """
    exposed = np.ones(len(points), dtype=bool)
    if not shells:
        return exposed
    corners = np.concatenate([shell.points[shell.triangles] for shell in shells])
    for start in range(0, len(points), 128):
        block = points[start:start + 128]
        distance, offset, normal = _closest_on_triangles(block, corners)
        nearest = np.argmin(distance, axis=1)
        rows = np.arange(len(block))
        near = distance[rows, nearest]
        side = np.einsum("pk,pk->p", offset[rows, nearest], normal[nearest])
        exposed[start:start + 128] = (near > reach) | (side > tolerance)
    return exposed


# ---------------------------------------------------------------------------
# Refit: what the runtime does to a garment before the player sees it
# ---------------------------------------------------------------------------

def girth_ratios(registry: dict, author_rig: str, wearer: str) -> dict[str, float]:
    """``_girth_ratios`` from replicated_actor_3d.gd, in Python."""
    if not author_rig or author_rig == wearer:
        return {}
    table = registry.get("bodyGirth", {})
    author, worn = table.get(author_rig, {}), table.get(wearer, {})
    if not author or not worn:
        return {}
    ratios = {}
    for bone, value in author.items():
        source, target = float(value), float(worn.get(bone, 0.0))
        if source > .0005 and target > .0005:
            ratios[bone] = float(np.clip(target / source, 1.0, 2.0))
    return ratios


def bone_binds(garment: Skeleton, wearer: Skeleton,
               girth: dict[str, float]) -> dict[str, np.ndarray]:
    """The bind matrix the runtime hands each bone: ``_bone_fit * authored_bind``."""
    fit = wearer.fit_scale
    binds: dict[str, np.ndarray] = {}
    for bone in garment.names:
        authored = garment.inverse_bind.get(bone)
        if authored is None or bone not in wearer.rest:
            continue
        ratio = 1.0
        author_tip, target_tip = garment.tip(bone), wearer.tip(bone)
        if author_tip is not None and target_tip is not None:
            author_span = float(np.linalg.norm(author_tip - garment.rest[bone][:3, 3]))
            target_span = float(np.linalg.norm(target_tip - wearer.rest[bone][:3, 3]))
            if author_span > .0005 and target_span > .0005:
                ratio = float(np.clip(target_span / author_span, .4, 2.5))
        scale = float(np.clip(max(ratio, girth.get(bone, 1.0)), 1.0, 2.0))
        factor = fit if abs(scale - 1.0) < .02 else fit * scale
        binds[bone] = np.diag([factor, factor, factor, 1.0]) @ authored
    return binds


def skin(points: np.ndarray, joints: np.ndarray, weights: np.ndarray,
         names: list[str], matrices: dict[str, np.ndarray]) -> np.ndarray:
    """Linear blend skinning with whatever per-bone matrix is handed in."""
    out = np.zeros_like(points)
    homogeneous = np.concatenate([points, np.ones((len(points), 1))], axis=1)
    for slot in range(joints.shape[1]):
        weight = weights[:, slot]
        active = weight > 1e-6
        if not active.any():
            continue
        for bone_index in np.unique(joints[active, slot]):
            if bone_index >= len(names):
                continue
            matrix = matrices.get(names[int(bone_index)])
            if matrix is None:
                continue
            rows = active & (joints[:, slot] == bone_index)
            out[rows] += weight[rows, None] * (homogeneous[rows] @ matrix.T)[:, :3]
    return out


def pose_globals(skeleton: Skeleton, pose: dict[str, dict]) -> dict[str, np.ndarray]:
    """Global transform of every bone under a sampled animation frame."""
    locals_: dict[str, np.ndarray] = {}
    for bone in skeleton.names:
        base = skeleton.node_local.get(bone, np.eye(4))
        channel = pose.get(bone)
        if channel is None:
            locals_[bone] = base
            continue
        matrix = np.eye(4)
        if "scale" in channel:
            matrix = matrix @ np.diag([*channel["scale"], 1.0])
        if "rotation" in channel:
            rotation = np.eye(4)
            rotation[:3, :3] = _quaternion(channel["rotation"])
            matrix = rotation @ matrix
        translation = channel.get("translation", base[:3, 3])
        shift = np.eye(4)
        shift[:3, 3] = translation
        locals_[bone] = shift @ matrix
    cache: dict[str, np.ndarray] = {}

    def resolve(bone: str) -> np.ndarray:
        if bone in cache:
            return cache[bone]
        matrix = locals_.get(bone, np.eye(4))
        owner = skeleton.parent.get(bone)
        if owner:
            matrix = resolve(owner) @ matrix
        cache[bone] = matrix
        return matrix

    return {bone: resolve(bone) for bone in skeleton.names}


@lru_cache(maxsize=32)
def clip_pose(library: str, clip: str, time: float) -> tuple:
    """A frozen frame of one clip, as (bone, channel, values) triples."""
    from equipment_authoring import _sample_clip_rotations
    document, binary = read_gltf(Path(library))
    sampled = _sample_clip_rotations(document, binary, clip, time)
    return tuple((bone, tuple((path, tuple(np.asarray(value).ravel().tolist()))
                              for path, value in channels.items()))
                 for bone, channels in sampled.items())


def _thaw(frozen: tuple) -> dict[str, dict]:
    return {bone: {path: np.array(value) for path, value in channels}
            for bone, channels in frozen}


# ---------------------------------------------------------------------------
# The measurement
# ---------------------------------------------------------------------------

#: Bones whose skin a torso garment is answerable for.
TORSO_REGION = ("spine_01", "spine_02", "spine_03", "clavicle_l", "clavicle_r",
                "upperarm_l", "upperarm_r")
#: The deltoid, reported on its own because it is the defect this work exists
#: to close and a whole-body total hides fourteen vertices in three thousand.
SHOULDER_BONES = ("clavicle_l", "clavicle_r", "upperarm_l", "upperarm_r")


@dataclass
class Coverage:
    """What one garment does to one body in one pose."""

    rig: str
    clip: str
    checked: int
    exposed: int
    shoulder_checked: int
    shoulder_exposed: int
    #: The weaker open-surface reading, kept so a stack of open tubes can be
    #: compared against a closed shell at all.  See ``open_surface_exposed``.
    loose_exposed: int = 0
    loose_shoulder_exposed: int = 0
    shells: int = 0
    closed_shells: int = 0

    @property
    def clean(self) -> bool:
        return self.exposed == 0

    def line(self) -> str:
        return (f"{self.rig:<20} {self.clip:<16} "
                f"body {self.exposed:>4}/{self.checked:<5} "
                f"shoulder {self.shoulder_exposed:>3}/{self.shoulder_checked:<4} "
                f"[open {self.loose_exposed:>4}/{self.loose_shoulder_exposed:<4}] "
                f"shells {self.closed_shells}/{self.shells}")


def region_mask(points: np.ndarray, joints: np.ndarray, weights: np.ndarray,
                names: list[str], bones, floor: float, ceiling: float,
                arm_reach: float = 1e9) -> np.ndarray:
    """Body vertices a torso garment is responsible for.

    Skin weight decides *which* part of the body a vertex belongs to; the
    garment's own extent decides *whether* it is claimed.  A hem tucked inside
    the trousers is the trousers' problem, and the bare forearm below a
    short sleeve is nobody's - a shirt that does not reach the elbow is not
    failing to cover it.

    ``arm_reach`` is taken from the garment itself rather than from the design's
    intent, so a design cannot quietly excuse a hole by declaring a smaller
    region: shrink the sleeve and the *claimed* count drops with it, which shows
    up in the report beside the exposure it would otherwise have hidden.
    """
    wanted = {index for index, name in enumerate(names) if name in set(bones)}
    influence = np.zeros(len(points))
    for slot in range(joints.shape[1]):
        rows = np.isin(joints[:, slot], list(wanted))
        influence[rows] += weights[rows, slot]
    return ((influence > .5) & (points[:, 1] >= floor) & (points[:, 1] <= ceiling)
            & (np.abs(points[:, 0]) <= arm_reach))


def measure(garment_path: Path, race_path: Path, registry: dict, *,
            author_rig: str, clip: str = "bind", library: Path | None = None,
            time: float = 0.0, floor: float = 1.030, ceiling: float = 1.492,
            tolerance: float = SKIN_TOLERANCE,
            loose_metric: bool = False,
            also: "tuple[tuple[Path, str], ...]" = ()) -> Coverage:
    """How much skin one garment leaves showing on one race, in one pose."""
    garment_prims, garment_rig, _ = load(str(garment_path))
    body_prims, wearer, mesh_names = load(str(race_path))
    wearer_name = race_path.stem
    # Other layers worn at the same time.  ``also`` is (path, authoring rig)
    # pairs - trousers, usually - and they join the enclosure without joining
    # the claim: what the torso piece is answerable for does not change because
    # something else happens to cover part of it.  What changes is the answer.

    ratios = girth_ratios(registry, author_rig, wearer_name)
    binds = bone_binds(garment_rig, wearer, ratios)

    if clip == "bind":
        posed = {bone: wearer.rest[bone] for bone in wearer.names}
    else:
        posed = pose_globals(wearer, _thaw(clip_pose(str(library), clip, time)))

    garment_matrices = {bone: posed[bone] @ binds[bone]
                        for bone in binds if bone in posed}
    body_matrices = {bone: posed[bone] @ wearer.inverse_bind[bone]
                     for bone in wearer.names
                     if bone in posed and bone in wearer.inverse_bind}

    shells: list[Shell] = []
    for primitive in garment_prims:
        if primitive.joints is None:
            continue
        moved = skin(primitive.points, primitive.joints, primitive.weights,
                     garment_rig.names, garment_matrices)
        shells.extend(components(moved, primitive.triangles))
    for layer_path, layer_rig_name in also:
        layer_prims, layer_rig, _ = load(str(layer_path))
        layer_binds = bone_binds(layer_rig, wearer,
                                 girth_ratios(registry, layer_rig_name, wearer_name))
        layer_matrices = {bone: posed[bone] @ layer_binds[bone]
                          for bone in layer_binds if bone in posed}
        for primitive in layer_prims:
            if primitive.joints is None:
                continue
            moved = skin(primitive.points, primitive.joints, primitive.weights,
                         layer_rig.names, layer_matrices)
            shells.extend(components(moved, primitive.triangles))
    enclosure = Enclosure(shells)
    # Taken in the bind pose whatever pose is being tested - see the module note
    # on why the claimed set has to be the same in every frame.
    arm_reach = _rest_reach(garment_prims, garment_rig, wearer, binds)

    checked = exposed = shoulder_checked = shoulder_exposed = 0
    loose = loose_shoulder = 0
    for primitive, name in zip(body_prims, mesh_names):
        if primitive.joints is None or name != "Body":
            continue
        mask = region_mask(primitive.points, primitive.joints, primitive.weights,
                           wearer.names, TORSO_REGION, floor, ceiling, arm_reach)
        if not mask.any():
            continue
        shoulder = mask & region_mask(primitive.points, primitive.joints,
                                      primitive.weights, wearer.names,
                                      SHOULDER_BONES, 1.380, ceiling, arm_reach)
        moved = skin(primitive.points[mask], primitive.joints[mask],
                     primitive.weights[mask], wearer.names, body_matrices)
        covered = enclosure.inside(moved, tolerance)
        shoulder_here = shoulder[mask]
        checked += int(mask.sum())
        exposed += int((~covered).sum())
        shoulder_checked += int(shoulder_here.sum())
        shoulder_exposed += int((~covered & shoulder_here).sum())
        if loose_metric:
            # Only ever asked of the shells this work replaces: it is many times
            # slower than parity and strictly weaker.
            adrift = open_surface_exposed(moved, shells, tolerance=tolerance)
            loose += int(adrift.sum())
            loose_shoulder += int((adrift & shoulder_here).sum())
    return Coverage(wearer_name, clip, checked, exposed,
                    shoulder_checked, shoulder_exposed, loose, loose_shoulder,
                    len(shells), sum(shell.closed for shell in shells))


def _rest_reach(garment_prims, garment_rig: Skeleton, wearer: Skeleton,
                binds: dict) -> float:
    """How far out the arm this garment wraps, measured on the wearer at rest."""
    rest = {bone: wearer.rest[bone] for bone in wearer.names}
    matrices = {bone: rest[bone] @ binds[bone] for bone in binds if bone in rest}
    shells: list[Shell] = []
    furthest = 0.0
    for primitive in garment_prims:
        if primitive.joints is None:
            continue
        moved = skin(primitive.points, primitive.joints, primitive.weights,
                     garment_rig.names, matrices)
        furthest = max(furthest, float(np.abs(moved[:, 0]).max()))
        shells.extend(components(moved, primitive.triangles))
    return wrapped_reach(Enclosure(shells), rest) or (furthest - .010)


def wrapped_reach(enclosure: "Enclosure", posed: dict, stations: int = 48) -> float:
    """How far out the arm the garment still wraps, in |x| on the posed body.

    Taking the garment's furthest vertex instead reads a cap that closes to a
    rounded point as covering the arm out to its tip, which it does not - and
    then reports the bare skin under that tip as a defect.  What is wanted is
    the last place the garment is still *around* the arm, so the arm's own axis
    is walked from the shoulder to the wrist and the last enclosed station wins.

    Everything beyond it is bare arm by design: a short sleeve is not failing to
    cover an elbow it was never drawn to reach.
    """
    best = 0.0
    for side in ("l", "r"):
        joint = posed.get(f"upperarm_{side}")
        wrist = posed.get(f"hand_{side}")
        if joint is None or wrist is None:
            continue
        start, end = joint[:3, 3], wrist[:3, 3]
        walk = np.array([start + (end - start) * (step / stations)
                         for step in range(stations + 1)])
        inside = enclosure.inside(walk, tolerance=0.0)
        if not inside.any():
            continue
        last = walk[np.flatnonzero(inside)[-1]]
        # Back off the rim - see OPENING_RIM.
        along = last - start
        span = float(np.linalg.norm(along))
        if span > OPENING_RIM:
            last = last - along / span * OPENING_RIM
        best = max(best, float(abs(last[0])))
    return best


def resolve(registry: dict, key: str, wearer: str) -> tuple[str, str]:
    """The scene and authoring rig one race resolves a registry entry to.

    Mirrors ``_fit_variant``: a race in a fit group wears the variant built on
    its own rig where the piece ships one, and the reference piece otherwise.
    """
    model = dict(registry["models"][key])
    groups = registry.get("fitGroups", {}).get(wearer, [])
    if isinstance(groups, str):
        groups = [groups] if groups else []
    for group in groups:
        variant = (model.get("variants") or {}).get(group)
        if variant:
            model.update(variant)
            break
    return str(model["scene"]), str(model.get("authoredFor", ""))


def layers(client: Path, registry: dict, keys, wearer: str):
    """Resolve other registry entries this wearer would have on at the time."""
    resolved = []
    for key in keys:
        if key not in registry["models"]:
            continue
        scene, author = resolve(registry, key, wearer)
        resolved.append((client / scene.removeprefix("res://"), author))
    return tuple(resolved)


def survey(client: Path, key: str, races=None, clips=None, *,
           loose_metric: bool = False, **kwargs) -> "list[Coverage]":
    """One registry entry measured on every race that wears it, in every pose."""
    registry = json.loads((client / "data/actors/equipment.json").read_text())
    root = client / "assets/actors/native/races"
    library = client / "assets/actors/native/shared/Universal_Animation_Library.glb"
    wanted = races or sorted(path.stem for path in root.glob("*.glb"))
    results = []
    worn = kwargs.pop("worn_with", ())
    for race in wanted:
        scene, author = resolve(registry, key, race)
        garment = client / scene.removeprefix("res://")
        also = layers(client, registry, worn, race)
        for clip, time in (clips or (("bind", 0.0),)):
            results.append(measure(garment, root / f"{race}.glb", registry,
                                   author_rig=author, clip=clip, library=library,
                                   time=time, loose_metric=loose_metric,
                                   also=also, **kwargs))
    return results


#: The clips a shoulder seam has to survive.  The T-pose the rig is authored in
#: is the *easiest* case for a deltoid, not a representative one; the two attack
#: poses take the arm through the seam and the sit pose folds the waist.
POSE_CLIPS = (("bind", 0.0), ("Idle_Subtle", .5), ("Jog", .3), ("Sprint", .25),
              ("Sword_Attack", .35), ("Bow_Pull_Hold", .4), ("Meditate", .5))


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--client", type=Path, required=True)
    parser.add_argument("--garment", type=Path, action="append", required=True)
    parser.add_argument("--race", action="append", default=[])
    parser.add_argument("--author-rig", default="luminous_male")
    parser.add_argument("--posed", action="store_true")
    arguments = parser.parse_args()

    client = arguments.client
    registry = json.loads((client / "data/actors/equipment.json").read_text())
    races = client / "assets/actors/native/races"
    library = client / "assets/actors/native/shared/Universal_Animation_Library.glb"
    wanted = arguments.race or sorted(path.stem for path in races.glob("*.glb"))
    clips = POSE_CLIPS if arguments.posed else (("bind", 0.0),)

    worst = 0
    for garment in arguments.garment:
        print(f"\n== {garment.name}")
        for race in wanted:
            for clip, time in clips:
                result = measure(garment, races / f"{race}.glb", registry,
                                 author_rig=arguments.author_rig, clip=clip,
                                 library=library, time=time)
                worst = max(worst, result.exposed)
                print("  " + result.line())
    raise SystemExit(1 if worst else 0)


if __name__ == "__main__":
    main()
