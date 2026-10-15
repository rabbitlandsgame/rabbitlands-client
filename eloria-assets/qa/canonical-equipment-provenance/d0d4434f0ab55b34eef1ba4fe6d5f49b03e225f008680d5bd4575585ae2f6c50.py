#!/usr/bin/env python3
"""Body-conforming equipment authoring for the Nymara native actor library.

Added 2026-08-28 for Eloria Client.

The first equipment pass emitted small primitive blobs authored in an arbitrary
item space and attached them to raw ``BoneAttachment3D`` bones with an identity
transform.  That produced three defects the runtime could not correct:

* Bone rest bases are not axis aligned.  ``hand_r`` rests with its local +Y along
  world -X, so every weapon left the grip pointing sideways out of the body.
* The blobs were authored at three to five times body scale, so helmets, amulets
  and cuirasses engulfed the actor.
* Wearables were rigid children of a single bone, so a cuirass could not follow
  the spine and leg armour could not follow the knees.

This module authors equipment against the *measured* rest geometry of the shared
77-joint canonical Rest_Pose rig.  Garments are lofted as offset shells around the real
body cross sections and are skinned to the same joints as the body, so they
deform with every clip in the universal animation library.  Rigid props keep a
socket, but the socket is now expressed in character space and the runtime
cancels the bone rest basis before applying it.
"""
from __future__ import annotations

import io
import json
import math
import struct
from contextlib import contextmanager
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path

import numpy as np
from PIL import Image

# Character space used by every authored value in this module:
#   +Y up, +Z the direction the actor faces, +X the actor's own left.
# It is the space of the race GLB skeleton, which the runtime preserves.
CANONICAL_HEAD_REST_Y = 1.5684900288581848

# Source-derived surfaces of the canonical bodies. The generated head band
# and cap are appearance attachments, not anatomy to fit another hat around.
BODY_SURFACES = ("body", "eyes", "eyebrows", "scalp", "wardrobe_shirt",
                 "wardrobe_pants", "wardrobe_boots")

SKIN_BONE_LIMIT = 4


# ---------------------------------------------------------------------------
# glTF reading
# ---------------------------------------------------------------------------

_COMPONENT_DTYPES = {5120: "<i1", 5121: "<u1", 5122: "<i2", 5123: "<u2",
                     5125: "<u4", 5126: "<f4"}
_TYPE_WIDTHS = {"SCALAR": 1, "VEC2": 2, "VEC3": 3, "VEC4": 4, "MAT4": 16}


def read_glb(path: Path) -> tuple[dict, bytes]:
    raw = path.read_bytes()
    if raw[:4] != b"glTF":
        raise ValueError(f"not a GLB: {path}")
    total = struct.unpack_from("<I", raw, 8)[0]
    offset, document, binary = 12, None, b""
    while offset < total:
        length, kind = struct.unpack_from("<II", raw, offset)
        chunk = raw[offset + 8:offset + 8 + length]
        offset += 8 + length
        if kind == 0x4E4F534A:
            document = json.loads(chunk)
        elif kind == 0x004E4942:
            binary = bytes(chunk)
    if document is None:
        raise ValueError(f"GLB has no JSON chunk: {path}")
    return document, binary


def read_gltf(path: Path) -> tuple[dict, bytes]:
    if path.suffix == ".glb":
        return read_glb(path)
    document = json.loads(path.read_text(encoding="utf-8"))
    binary = (path.parent / document["buffers"][0]["uri"]).read_bytes()
    return document, binary


def accessor_array(document: dict, binary: bytes, index: int) -> np.ndarray:
    spec = document["accessors"][index]
    width = _TYPE_WIDTHS[spec["type"]]
    dtype = np.dtype(_COMPONENT_DTYPES[spec["componentType"]])
    count = spec["count"]
    if "bufferView" not in spec:
        return np.zeros((count, width), dtype=dtype)
    view = document["bufferViews"][spec["bufferView"]]
    start = view.get("byteOffset", 0) + spec.get("byteOffset", 0)
    stride = view.get("byteStride") or width * dtype.itemsize
    if stride == width * dtype.itemsize:
        flat = np.frombuffer(binary, dtype=dtype, count=count * width, offset=start)
        return flat.reshape(count, width)
    out = np.empty((count, width), dtype=dtype)
    for row in range(count):
        out[row] = np.frombuffer(binary, dtype=dtype, count=width,
                                 offset=start + row * stride)
    return out


def _node_matrix(node: dict) -> np.ndarray:
    if "matrix" in node:
        return np.asarray(node["matrix"], dtype=np.float64).reshape(4, 4).T
    matrix = np.eye(4)
    if "scale" in node:
        matrix = matrix @ np.diag([*node["scale"], 1.0])
    if "rotation" in node:
        x, y, z, w = node["rotation"]
        rotation = np.array([
            [1 - 2 * (y * y + z * z), 2 * (x * y - z * w), 2 * (x * z + y * w)],
            [2 * (x * y + z * w), 1 - 2 * (x * x + z * z), 2 * (y * z - x * w)],
            [2 * (x * z - y * w), 2 * (y * z + x * w), 1 - 2 * (x * x + y * y)]])
        homogeneous = np.eye(4)
        homogeneous[:3, :3] = rotation
        matrix = homogeneous @ matrix
    if "translation" in node:
        homogeneous = np.eye(4)
        homogeneous[:3, 3] = node["translation"]
        matrix = homogeneous @ matrix
    return matrix


def global_matrices(document: dict) -> list[np.ndarray]:
    nodes = document.get("nodes", [])
    parent: dict[int, int] = {}
    for index, node in enumerate(nodes):
        for child in node.get("children", []):
            parent[child] = index
    resolved: dict[int, np.ndarray] = {}

    def resolve(index: int) -> np.ndarray:
        if index in resolved:
            return resolved[index]
        matrix = _node_matrix(nodes[index])
        if index in parent:
            matrix = resolve(parent[index]) @ matrix
        resolved[index] = matrix
        return matrix

    return [resolve(index) for index in range(len(nodes))]


# ---------------------------------------------------------------------------
# Rig and body sampling
# ---------------------------------------------------------------------------

@dataclass
class Rig:
    """Rest pose and skinned body geometry of one race GLB."""

    joint_names: list[str]
    rest: dict[str, np.ndarray]
    parent: dict[str, str | None]
    positions: np.ndarray
    joints: np.ndarray
    weights: np.ndarray
    #: Body mesh triangles as indices into ``positions`` -- carried so a
    #: fitter can ask parity questions (is this vertex inside the skin?)
    #: against the actual body surface rather than a ring approximation.
    faces: np.ndarray | None = None
    source_slug: str = ""

    @property
    def fit_scale(self) -> float:
        return float(self.rest["Head"][1, 3]) / CANONICAL_HEAD_REST_Y

    def origin(self, bone: str) -> np.ndarray:
        return np.asarray(self.rest[bone][:3, 3], dtype=np.float64)

    def basis(self, bone: str) -> np.ndarray:
        return np.asarray(self.rest[bone][:3, :3], dtype=np.float64)

    def children(self, bone: str) -> list[str]:
        return [name for name, value in self.parent.items() if value == bone]

    def segment(self, bone: str) -> tuple[np.ndarray, np.ndarray]:
        """Bone origin and the point its chain continues to."""
        start = self.origin(bone)
        children = [c for c in self.children(bone) if not c.endswith("_leaf")]
        if children:
            ends = np.array([self.origin(child) for child in children])
            return start, ends.mean(axis=0)
        direction = self.basis(bone)[:, 1]
        return start, start + direction * .06

    def weights_for(self, points: np.ndarray, candidates: list[str],
                    falloff: float = 2.6) -> tuple[np.ndarray, np.ndarray]:
        """Skin weights for garment vertices, taken from the body beneath them.

        Modified 2026-08-28 for Eloria Client.  These used to be solved from the
        distance to each bone's segment, which is a different rule from the one
        the body itself was weighted with.  At rest the two agree; the moment a
        knee bends they do not, and the leg comes through the trouser it is
        supposed to be inside - the thinner the garment, the worse it is.  A
        garment vertex now inherits the blend of the body surface nearest to it,
        so cloth and skin bend as one and the shell can be cut close.

        ``candidates`` still scopes the search: a boot looks only at the parts
        of the body a boot covers, so a cuff near the knee cannot pick up
        weights from the other leg standing beside it.
        """
        inherited = self._weights_from_body(points, candidates)
        if inherited is not None:
            return inherited
        return self._weights_by_distance(points, candidates, falloff)

    def _weights_from_body(self, points: np.ndarray, candidates: list[str],
                           neighbours: int = 2):
        """Blend the weights of the nearest body vertices under each point.

        Two neighbours, sharply weighted, rather than a wide average: a boot's
        instep sits a centimetre above skin that belongs to the foot and skin
        that belongs to the shin, and averaging across that crease bound half of
        it to the calf.  The ankle then flexed and tore the boot open along the
        top of the foot.  The body's own weights are already smooth, so sampling
        them closely is enough.
        """
        indices = {self.joint_names.index(bone) for bone in candidates
                   if bone in self.joint_names}
        if not indices:
            return None
        dominant = self.joints[np.arange(len(self.joints)),
                               np.argmax(self.weights, axis=1)]
        region = np.isin(dominant, list(indices))
        if self.source_slug.startswith('ssarathi_'):
            # Nearby pelvis-bound tail vertices are not trouser/coat samples.
            region &= ~tail_region(self.positions, self)
        if region.sum() < neighbours * 4:
            return None
        source = self.positions[region]
        source_joints = self.joints[region]
        source_weights = self.weights[region]
        count = min(neighbours, len(source))
        # Chunked brute force rather than a tree: the body is a few thousand
        # vertices and a garment a couple of thousand, and the authoring tools
        # deliberately depend on nothing beyond numpy.
        nearest = np.empty((len(points), count), dtype=np.int64)
        distance = np.empty((len(points), count))
        # Squared distances by expansion rather than by differencing.  The
        # obvious `norm(block[:, None] - source[None], axis=2)` builds a
        # (block, body, 3) temporary on the way, which is three times the size
        # of the answer; the torso set trebled the vertex count of a garment and
        # the build ran out of memory on it.  Ordering is unchanged by working
        # in squares, so only the picked distances need a root.
        square = (source ** 2).sum(axis=1)
        for start in range(0, len(points), 512):
            block = points[start:start + 512]
            gaps = ((block ** 2).sum(axis=1)[:, None] + square[None, :]
                    - 2.0 * (block @ source.T))
            np.maximum(gaps, 0.0, out=gaps)
            picked = np.argpartition(gaps, count - 1, axis=1)[:, :count]
            rows = np.arange(len(block))[:, None]
            nearest[start:start + 512] = picked
            distance[start:start + 512] = np.sqrt(gaps[rows, picked])
        share = 1.0 / np.maximum(distance, 1e-4) ** 6
        share /= share.sum(axis=1, keepdims=True)
        # Accumulate the neighbours' bone weights into one blend per point.
        pooled: dict[int, np.ndarray] = {}
        for column in range(count):
            picked = nearest[:, column]
            for slot in range(source_joints.shape[1]):
                bones = source_joints[picked, slot]
                values = source_weights[picked, slot] * share[:, column]
                for bone in np.unique(bones):
                    if bone not in indices:
                        continue
                    mask = bones == bone
                    total = pooled.setdefault(int(bone), np.zeros(len(points)))
                    total[mask] += values[mask]
        if not pooled:
            return None
        bones = np.array(sorted(pooled))
        stacked = np.stack([pooled[int(bone)] for bone in bones], axis=1)
        order = np.argsort(-stacked, axis=1)[:, :SKIN_BONE_LIMIT]
        rows = np.arange(len(points))[:, None]
        best = stacked[rows, order]
        totals = best.sum(axis=1, keepdims=True)
        if not np.all(totals > 1e-6):
            return None
        best = best / totals
        joints = np.zeros((len(points), SKIN_BONE_LIMIT), dtype=np.uint16)
        values = np.zeros((len(points), SKIN_BONE_LIMIT), dtype=np.float32)
        joints[:, :order.shape[1]] = bones[order]
        values[:, :order.shape[1]] = best
        return joints, values

    def _weights_by_distance(self, points: np.ndarray, candidates: list[str],
                             falloff: float = 2.6) -> tuple[np.ndarray, np.ndarray]:
        """Fallback: inverse-distance weights against a candidate bone subset.

        Distance is measured to the bone *segment*, not its origin, so a vertex
        beside the middle of a thigh binds to the thigh rather than to whichever
        joint happens to be nearest in a straight line.
        """
        segments = [self.segment(bone) for bone in candidates]
        indices = [self.joint_names.index(bone) for bone in candidates]
        distances = np.empty((len(points), len(candidates)))
        for column, (start, end) in enumerate(segments):
            axis = end - start
            length_squared = float(axis @ axis)
            if length_squared < 1e-9:
                distances[:, column] = np.linalg.norm(points - start, axis=1)
                continue
            travel = np.clip(((points - start) @ axis) / length_squared, 0.0, 1.0)
            closest = start + travel[:, None] * axis
            distances[:, column] = np.linalg.norm(points - closest, axis=1)
        influence = 1.0 / np.power(np.maximum(distances, 1e-3), falloff)
        order = np.argsort(-influence, axis=1)[:, :SKIN_BONE_LIMIT]
        rows = np.arange(len(points))[:, None]
        best = influence[rows, order]
        best /= np.maximum(best.sum(axis=1, keepdims=True), 1e-9)
        joints = np.zeros((len(points), SKIN_BONE_LIMIT), dtype=np.uint16)
        values = np.zeros((len(points), SKIN_BONE_LIMIT), dtype=np.float32)
        for column in range(order.shape[1]):
            joints[:, column] = [indices[i] for i in order[:, column]]
            values[:, column] = best[:, column]
        return joints, values

    def surface_radius(self, axis_start: np.ndarray, axis_end: np.ndarray,
                       travel: float, angle: float, *, bones: list[str] | None = None,
                       slab: float = .055, default: float = .10,
                       centre: np.ndarray | None = None,
                       percentile: float = 96.0) -> float:
        """Measured body half-width along one radial direction of a limb axis.

        Garments are lofted from these samples, so a cuirass follows the real
        chest silhouette instead of approximating it with a scaled sphere.
        """
        axis = axis_end - axis_start
        length = float(np.linalg.norm(axis))
        if length < 1e-6:
            return default
        axis = axis / length
        reference = np.array([0., 1., 0.]) if abs(axis[1]) < .8 else np.array([0., 0., 1.])
        right = np.cross(axis, reference)
        right /= np.linalg.norm(right)
        forward = np.cross(right, axis)
        # ``centre`` overrides where the ring is measured from.  A caller that
        # draws its rings somewhere other than on the bone has to measure from
        # there too, or it sizes one circle and draws another.
        if centre is None:
            centre = axis_start + axis * (travel * length)
        direction = right * math.cos(angle) + forward * math.sin(angle)
        points = self._region(bones)
        offsets = points - centre
        along = offsets @ axis
        near = np.abs(along) <= slab
        if not near.any():
            return default
        radial = offsets[near] - np.outer(along[near], axis)
        projection = radial @ direction
        lateral = np.linalg.norm(radial - np.outer(projection, direction), axis=1)
        sector = (projection > 0) & (lateral <= .055 + projection * .30)
        if not sector.any():
            return default
        # ``percentile`` trims outliers out of the sector.  96 is right for a
        # broad, smooth surface like a chest or a thigh, where a stray vertex
        # would balloon the loft.  It is wrong at a sharp apex: the Luminous arm
        # section comes to a point at the back, only two vertices are out there,
        # and 96 discards exactly those two - the sleeve was then cut 4 mm
        # inside the skin it was measuring.  Callers wrapping a limb pass 100.
        return float(np.percentile(projection[sector], percentile))

    def slab_centre(self, axis_start: np.ndarray, axis_end: np.ndarray,
                    travel: float, *, bones: list[str] | None = None,
                    slab: float = .06) -> np.ndarray | None:
        """Middle of the body in the plane cut across a limb axis at ``travel``.

        ``surface_radius`` says how wide the body is in one direction; this says
        where it is.  A shoulder cap needs both, because a humerus does not run
        down the middle of the shoulder it belongs to.
        """
        axis = axis_end - axis_start
        length = float(np.linalg.norm(axis))
        if length < 1e-6:
            return None
        axis = axis / length
        centre = axis_start + axis * (travel * length)
        points = self._region(bones)
        along = (points - centre) @ axis
        near = np.abs(along) <= slab
        if near.sum() < 6:
            return None
        radial = (points[near] - centre) - np.outer(along[near], axis)
        return centre + radial.mean(axis=0)

    def _region(self, bones: list[str] | None) -> np.ndarray:
        if bones is None:
            return self.positions
        key = tuple(sorted(bones))
        cached = self._region_cache.get(key)
        if cached is None:
            indices = {self.joint_names.index(bone) for bone in bones}
            mask = np.zeros(len(self.positions), dtype=bool)
            for column in range(self.joints.shape[1]):
                belongs = np.isin(self.joints[:, column], list(indices))
                mask |= belongs & (self.weights[:, column] > .18)
            if not mask.any():
                # Some canonical bodies carry their toes entirely on foot,
                # without ball weights. Measure the actual weighted forefoot;
                # falling back to the whole body included a Ssarathi tail and
                # reported a 237 mm toe radius. Other absent regions are empty.
                for bone in bones:
                    if bone.startswith("ball_"):
                        side = bone[-1]
                        mask |= (_foot_region(self, side)
                                 & (self.positions[:, 2] >= self.origin(bone)[2] - .04*self.fit_scale))
            cached = self.positions[mask]
            self._region_cache[key] = cached
        return cached

    _region_cache: dict = field(default_factory=dict, repr=False)


class RigSet:
    """A rest pose plus every race silhouette a garment has to clear.

    Modified 2026-08-28 for Eloria Client.  Garments were lofted against
    ``luminous_male`` alone and then worn by every race under a single uniform
    fit scale.  Any race the reference did not bound - a wider seat, a deeper
    chest - pushed straight through the shell, which is how the trousers came
    to leave the wearer's backside bare.  Every measurement now takes the
    widest reading across the whole cast, so one authored garment encloses all
    of them; the rest pose, weights and bone frames still come from the
    reference rig so the authored geometry is unchanged in spirit.
    """

    def __init__(self, primary: Rig, others: "list[Rig]" = ()):
        self.primary = primary
        self.others = [rig for rig in others if rig is not primary]

    # -- delegated rest-pose queries ---------------------------------------
    @property
    def fit_scale(self) -> float:
        return self.primary.fit_scale

    @property
    def joint_names(self) -> list[str]:
        return self.primary.joint_names

    @property
    def rest(self) -> dict:
        return self.primary.rest

    @property
    def positions(self) -> np.ndarray:
        return self.primary.positions

    @property
    def joints(self) -> np.ndarray:
        return self.primary.joints

    @property
    def weights(self) -> np.ndarray:
        return self.primary.weights

    @property
    def parent(self) -> dict:
        return self.primary.parent

    def origin(self, bone: str) -> np.ndarray:
        return self.primary.origin(bone)

    def basis(self, bone: str) -> np.ndarray:
        return self.primary.basis(bone)

    def children(self, bone: str) -> list[str]:
        return self.primary.children(bone)

    def segment(self, bone: str):
        return self.primary.segment(bone)

    def weights_for(self, points: np.ndarray, candidates: list[str],
                    falloff: float = 2.6):
        return self.primary.weights_for(points, candidates, falloff)

    # -- the measurement that actually differs ------------------------------
    def surface_radius(self, axis_start, axis_end, travel, angle, *,
                       bones=None, slab: float = .055, default: float = .10,
                       centre=None, percentile: float = 96.0) -> float:
        radius = self.primary.surface_radius(
            axis_start, axis_end, travel, angle, bones=bones, slab=slab,
            default=default, centre=centre, percentile=percentile)
        for rig in self.others:
            radius = max(radius, rig.surface_radius(
                axis_start, axis_end, travel, angle, bones=bones, slab=slab,
                default=default, centre=centre, percentile=percentile))
        return radius

    def slab_centre(self, axis_start, axis_end, travel, *, bones=None,
                    slab: float = .06):
        return self.primary.slab_centre(axis_start, axis_end, travel,
                                        bones=bones, slab=slab)


# Current bodies share all 77 rest transforms, but retain different surfaces.
# Source-art variants are fitted to each surface instead of narrowing a garment
# with one radius per bone. Legacy props retain their recorded runtime profile.
CANONICAL_RACES = tuple(f"{race}_{sex}"
    for race in ("luminous", "votary", "glasswarden", "orun", "greyhaven",
                 "ssarathi", "stoneborn", "mycelari")
    for sex in ("male", "female"))
FIT_GROUPS = {"canonical_" + race: {
    "rig": race, "races": (race,),
    "kinds": ("pants", "legs", "kilt", "boots", "shirt", "cuirass", "coat",
              "robe", "helm", "hood", "circlet"),
} for race in CANONICAL_RACES}

# Bones a garment is measured around.  Fingers and face bones carry no garment,
# so they are left out rather than shipped as dead weight in every registry.
GIRTH_BONES = ("pelvis", "spine_01", "spine_02", "spine_03", "neck_01",
               "clavicle_l", "clavicle_r", "upperarm_l", "upperarm_r",
               "lowerarm_l", "lowerarm_r", "hand_l", "hand_r",
               "thigh_l", "thigh_r", "calf_l", "calf_r",
               "foot_l", "foot_r", "ball_l", "ball_r")


def body_girth(rig: Rig, bones=GIRTH_BONES) -> dict:
    """How far the body stands off each bone, sampled the way a loft measures.

    Modified 2026-08-28 for Eloria Client.  One authored garment is worn by
    every race, so it used to be lofted around the widest silhouette in the
    cast - which fitted the broadest race and hung off everyone else.  Shipping
    the measurement instead lets a garment be authored close to the body it was
    built on and let out per wearer at runtime, so nobody wears a tent.

    The samples come from ``surface_radius``, the same probe the lofts use, so
    the ratio between two races means the same thing to the runtime as a
    thickness does to the authoring code.
    """
    girth: dict[str, float] = {}
    for bone in bones:
        if bone not in rig.rest:
            continue
        start, end = rig.segment(bone)
        if float(np.linalg.norm(end - start)) < 1e-6:
            continue
        samples = [rig.surface_radius(start, end, travel,
                                      2 * math.pi * step / 16, bones=[bone],
                                      slab=.05, default=0.0)
                   for travel in (.15, .4, .65, .9) for step in range(16)]
        samples = [value for value in samples if value > 1e-4]
        if len(samples) < 8:
            continue
        # A high quantile rather than a mean: what a garment has to clear is the
        # silhouette, not the average distance to the bone.  Not the maximum,
        # so one vertex flung out by a tail or a wing cannot decide how wide the
        # shirt around the spine has to be.
        girth[bone] = round(float(np.quantile(samples, .80)), 5)
    return girth


def foot_anchor(rig: Rig) -> dict:
    """Weighted foot-surface anchors relative to the shared canonical joints.

    Foot surfaces and left/right sole heights still differ. Pelvis-bound tails
    are excluded, so a tail tip cannot move a boot's ground anchor.
    """
    anchors: dict[str, list] = {}
    for side in ("l", "r"):
        for bone in (f"foot_{side}", f"ball_{side}"):
            if bone not in rig.rest:
                continue
            origin = rig.origin(bone)
            flesh = rig.positions[_foot_region(rig, side)]
            if len(flesh) < 24:
                continue
            ground = weighted_sole(rig, side)
            middle = (flesh.min(axis=0) + flesh.max(axis=0)) * .5
            anchors[bone] = [round(float(middle[0] - origin[0]), 5),
                             round(float(ground - origin[1]), 5),
                             round(float(middle[2] - origin[2]), 5)]
    return anchors


def _foot_region(rig: Rig, side: str) -> "np.ndarray":
    """Body vertices belonging to one foot: below the joint, around its axis."""
    ankle = rig.origin(f"foot_{side}")
    toe = rig.segment(f"ball_{side}")[1]
    span = toe - ankle
    length = float(np.linalg.norm(span)) or 1.0
    axis = span / length
    offsets = rig.positions - ankle
    along = np.clip(offsets @ axis, 0.0, length)
    aside = np.linalg.norm(offsets - np.outer(along, axis), axis=1)
    same = np.sign(rig.positions[:, 0]) == np.sign(ankle[0] or 1.0)
    candidates = [rig.joint_names.index(f"{bone}_{side}")
                  for bone in ("calf", "foot", "ball")]
    share = np.where(np.isin(rig.joints, candidates), rig.weights, 0.).sum(axis=1)
    return same & (share > .5) & (rig.positions[:, 1] < ankle[1] + .025) & (aside < .130)


def weighted_sole(rig: Rig, side: str) -> float:
    """Sole carried by this foot chain; a pelvis-bound tail cannot set it."""
    feet = [rig.joint_names.index(f"{bone}_{side}") for bone in ("foot", "ball")]
    share = np.where(np.isin(rig.joints, feet), rig.weights, 0.).sum(axis=1)
    selected = rig.positions[share > .5]
    if not len(selected):
        raise ValueError(f"no weighted sole for {side}")
    return float(selected[:, 1].min())

def sole_drop(rig: Rig) -> dict:
    """Legacy scalar metadata, measured on each actual weighted foot surface."""
    drops: dict[str, float] = {}
    for bone in ("foot_l", "foot_r", "ball_l", "ball_r"):
        if bone not in rig.rest:
            continue
        drop = float(rig.rest[bone][1, 3]) - weighted_sole(rig, bone[-1])
        if drop > 1e-4:
            drops[bone] = round(drop, 5)
    return drops


def load_rig(path: Path, body_mesh_names=BODY_SURFACES) -> Rig:
    document, binary = read_gltf(path)
    nodes = document["nodes"]
    matrices = global_matrices(document)
    skin = document["skins"][0]
    joints = skin["joints"]
    joint_names = [nodes[node].get("name", "") for node in joints]
    rest = {joint_names[i]: matrices[node] for i, node in enumerate(joints)}
    parent_of: dict[int, int] = {}
    for index, node in enumerate(nodes):
        for child in node.get("children", []):
            parent_of[child] = index
    parent = {}
    for index, node in enumerate(joints):
        owner = parent_of.get(node)
        name = nodes[owner].get("name", "") if owner is not None else None
        parent[joint_names[index]] = name if name in joint_names else None
    positions: list[np.ndarray] = []
    bone_indices: list[np.ndarray] = []
    bone_weights: list[np.ndarray] = []
    faces: list[np.ndarray] = []
    offset = 0
    # A split body's surfaces SHARE one attribute set and differ only in
    # their index buffers; gathering per primitive would take every vertex
    # once per surface, and duplicated points collapse the two-neighbour
    # weight inheritance onto single verts.  Each attribute accessor is
    # read once; later primitives that reuse it only contribute faces.
    seen: dict[tuple, int] = {}
    for node in nodes:
        if "mesh" not in node or "skin" not in node:
            continue
        mesh = document["meshes"][node["mesh"]]
        if body_mesh_names and mesh.get("name", "") not in body_mesh_names:
            continue
        for primitive in mesh["primitives"]:
            attributes = primitive["attributes"]
            key = (node["skin"], tuple(sorted(attributes.items())))
            if key in seen:
                base = seen[key]
            else:
                base = offset
                seen[key] = base
                positions.append(accessor_array(document, binary, attributes["POSITION"]).astype(np.float64))
                bone_indices.append(accessor_array(document, binary, attributes["JOINTS_0"]).astype(np.int32))
                weights = accessor_array(document, binary, attributes["WEIGHTS_0"])
                divisor = (np.iinfo(weights.dtype).max if document["accessors"][attributes["WEIGHTS_0"]].get("normalized")
                           and weights.dtype.kind in "ui" else 1.)
                bone_weights.append(weights.astype(np.float64) / divisor)
                offset += len(positions[-1])
            if "indices" in primitive:
                tri = accessor_array(document, binary, primitive["indices"])
                faces.append(tri.reshape(-1, 3).astype(np.int64) + base)
    if not positions or not faces:
        raise ValueError(f"{path}: no skinned faces in selected surfaces {body_mesh_names}")
    # A shared accessor also contains vertices of excluded surfaces. Sampling
    # only the referenced union makes explicit surface selections meaningful.
    used, inverse = np.unique(np.vstack(faces), return_inverse=True)
    return Rig(joint_names=joint_names, rest=rest, parent=parent,
               positions=np.vstack(positions)[used], joints=np.vstack(bone_indices)[used],
               weights=np.vstack(bone_weights)[used], faces=inverse.reshape(-1, 3),
               source_slug=path.stem)


def tail_region(points, rig):
    """Same anatomical exclusion as the approved Ssarathi tail extraction.

    This selects geometry for preservation only; no body position or binding
    changes. Both the striped underside and green upper surface are included.
    """
    distance = np.full(len(points), np.inf)
    for side in ('l', 'r'):
        chain = [rig.origin(name+'_'+side) for name in ('thigh','calf','foot','ball')]
        chain.append(chain[-1] + np.array([0.,0.,.15]))
        for a,b in zip(chain,chain[1:]):
            axis=b-a
            t=np.clip((points-a)@axis/(axis@axis),0.,1.)
            distance=np.minimum(distance,np.linalg.norm(points-a-t[:,None]*axis,axis=1))
    return ((distance > .115) & ((points[:,0] > .13) | (points[:,2] < -.11))
            & (points[:,1] < rig.origin('pelvis')[1]+.02))


def garment_faces(rig, region=None):
    """Body/wardrobe face union with the Ssarathi tail left outside clothing."""
    faces=rig.faces
    if region == 'torso':
        protected = [rig.joint_names.index(name) for name in ('Head', 'neck_01')]
        influence = (rig.weights * np.isin(rig.joints, protected)).sum(axis=1)
        faces = faces[influence[faces].mean(axis=1) <= .5]
    if rig.source_slug.startswith('ssarathi_'):
        faces=faces[~tail_region(rig.positions[faces].mean(axis=1),rig)]
    return faces


def cape_weights(rig, points: np.ndarray, chains=("l", "c", "r"), links: int = 4):
    """Bind a cape to the rig's cape chains, keeping the collar on the body.

    The usual garment weighting samples the weights of the nearest body
    vertices, which cannot reach these bones at all: the body carries no cape
    weight to sample.  A cape is bound to them directly instead, by where each
    vertex sits along the hang and across it.

    The top of the cape stays on `spine_03` so the collar rides the shoulders
    and follows the per-race fit; below that the weight crosses into the
    chains, so the solver owns everything that can reach a leg.
    """
    origins = {}
    for chain in chains:
        for link in range(links):
            name = f"cape_{chain}_{link + 1:02d}"
            if name not in rig.joint_names:
                return None
            origins[(chain, link)] = rig.origin(name)
    anchor = rig.joint_names.index("spine_03")
    ladder = [origins[(chains[0], link)][1] for link in range(links)]
    top, bottom = max(ladder), min(ladder)
    if top - bottom < 1e-6:
        return None
    across = np.array([origins[(chain, 0)][0] for chain in chains])

    joints = np.zeros((len(points), 4), dtype=np.uint16)
    weights = np.zeros((len(points), 4), dtype=np.float32)
    for index, point in enumerate(points):
        # Along the hang: 0 at the collar, 1 at the hem.
        travel = float(np.clip((top - point[1]) / (top - bottom), 0., 1.))
        # The collar stays on the body, and lets go over the first fifth.
        body = float(np.clip(1. - travel / .20, 0., 1.))
        step = travel * (links - 1)
        low = int(np.clip(math.floor(step), 0, links - 2))
        along = float(step - low)
        # Across: the two nearest chains, weighted by how close they are.
        order = np.argsort(np.abs(across - point[0]))
        near, far = chains[int(order[0])], chains[int(order[1])]
        gap = abs(across[int(order[0])] - across[int(order[1])])
        side = float(np.clip(1. - abs(point[0] - across[int(order[0])])
                             / max(gap, 1e-6), 0., 1.))
        share = 1. - body
        entries = [
            (anchor, body),
            (rig.joint_names.index(f"cape_{near}_{low + 1:02d}"),
             share * side * (1. - along)),
            (rig.joint_names.index(f"cape_{near}_{low + 2:02d}"),
             share * side * along),
            (rig.joint_names.index(f"cape_{far}_{low + 2:02d}"),
             share * (1. - side)),
        ]
        total = sum(value for _slot, value in entries) or 1.
        for slot, (bone, value) in enumerate(entries):
            joints[index, slot] = bone
            weights[index, slot] = value / total
    return joints, weights


def smooth_profile(values: list[float], floor: float, passes: int = 2) -> list[float]:
    """Clamp and relax a measured radius ring so lofts stay watertight.

    The relaxed ring is never allowed to fall below the measurement it came
    from.  Two [1, 2, 1] passes take about sixty per cent off an isolated
    bump, and the most isolated bumps on a torso are precisely the ones a
    shirt has to clear: the nipple on both bodies and the bust on the female.
    Relaxed away, they came back through an eleven millimetre shell as two
    dark ovals on the chest of every clothed character.

    Keeping the maximum of the two leaves the smoothing where it earns its
    place -- filling hollows, so the loft stays watertight and uncreased --
    and takes it away where it would cut into the body.
    """
    raw = [max(floor, value) for value in values]
    data = list(raw)
    count = len(data)
    for _ in range(passes):
        data = [(data[(i - 1) % count] + 2. * data[i] + data[(i + 1) % count]) / 4.
                for i in range(count)]
    return [max(relaxed, measured) for relaxed, measured in zip(data, raw)]


# ---------------------------------------------------------------------------
# Surface authoring
# ---------------------------------------------------------------------------

def _mirror_bone(bone: str | None) -> str | None:
    """The same bone on the other side of the body."""
    if bone is None:
        return None
    if bone.endswith("_l"):
        return bone[:-2] + "_r"
    if bone.endswith("_r"):
        return bone[:-2] + "_l"
    return bone


class Surface:
    """Dense, smooth-shaded surface authoring with per-material groups.

    Every builder in this module emits geometry through ``Surface`` so equipment
    carries the same vertex density, smooth normals and UV coverage as the
    skinned body meshes it sits on.
    """

    def __init__(self, groups: int = 3):
        self.groups = [([], [], []) for _ in range(groups)]
        # Which bones each vertex should be skinned against, when the whole
        # piece must not share one scope.  Added 2026-08-29 for Eloria Client:
        # a boot's sole was inheriting the body's own heel weighting, which is
        # 31 per cent `calf`, and the runtime scales every bone about its own
        # origin - `calf`'s being the knee.  A sole vertex a metre below the
        # knee, widened by the thirty per cent an Orun calf needs, was dragged
        # 62 mm under the floor.  The sole is bound to the foot chain instead,
        # and the shaft keeps the calf, so each part of the boot is refitted
        # against the part of the leg it actually sits on.
        self.scopes = [[] for _ in range(groups)]
        self._scope = ""
        # Bone each vertex is pinned to, parallel to the positions of its group.
        # ``None`` means "inherit from the body underneath", which is what every
        # vertex did before pinning existed and what almost all of them still do.
        self.pins = [[] for _ in range(groups)]
        self._pin: str | None = None

    @contextmanager
    def scoped(self, name: str):
        """Tag everything emitted inside the block with a skin scope."""
        previous = self._scope
        self._scope = name
        try:
            yield self
        finally:
            self._scope = previous

    def _tag(self, material: int, count: int) -> None:
        self.scopes[material].extend([self._scope] * count)

    @contextmanager
    def pinned(self, bone: str | None):
        """Bind everything built in this block rigidly to one bone.

        Added 2026-08-29 for Eloria Client.  Garment vertices inherit the skin
        weights of the body surface nearest them, which is right for cloth that
        should bend with what it lies on and wrong for the one piece that must
        *not*: a shoulder cap swept about the humerus stays over the deltoid at
        any arm angle only if it turns with the humerus alone.  Blended against
        the clavicle it lags the arm, and the seam it exists to close opens
        again at abduction - which is the defect this whole rebuild is for.
        """
        previous = self._pin
        self._pin = bone
        try:
            yield self
        finally:
            self._pin = previous

    def _record(self, group: int, count: int) -> None:
        self.pins[group].extend([self._pin] * count)

    # -- primitives ---------------------------------------------------------

    def loft(self, rings: list[np.ndarray], material: int = 0, *,
             closed: bool = True, cap_start: bool = False, cap_end: bool = False,
             v_start: float = 0.0, v_end: float = 1.0) -> None:
        """Stitch a stack of equal-length rings into a tube."""
        rings = [np.asarray(ring, dtype=np.float64) for ring in rings]
        if len(rings) < 2:
            return
        sides = len(rings[0])
        positions, uvs, faces = self.groups[material]
        base = len(positions)
        rows = len(rings)
        for row, ring in enumerate(rings):
            v = v_start + (v_end - v_start) * (row / (rows - 1))
            for side in range(sides):
                positions.append(tuple(ring[side]))
                uvs.append((side / sides, v))
        self._tag(material, rows * sides)
        self._record(material, rows * sides)
        span = sides if closed else sides - 1
        for row in range(rows - 1):
            for side in range(span):
                nxt = (side + 1) % sides
                a = base + row * sides + side
                b = base + row * sides + nxt
                c = base + (row + 1) * sides + side
                d = base + (row + 1) * sides + nxt
                faces.extend((a, c, b, b, c, d))
        # Modified 2026-08-28 for Eloria Client: the cap winding used to be
        # fixed, but a ring's own winding depends on the frame it was built in.
        # Torso and hip rings run the other way from limb rings, so every
        # garment's waist and collar was capped with an inward-facing lid that
        # the renderer culls - the shirt was an open bowl and the trouser waist
        # a hole.  The caps now take their orientation from the loft itself.
        if cap_start:
            self.fan(rings[0], material,
                     flip=self._cap_flip(rings[0], rings[1]))
        if cap_end:
            self.fan(rings[-1], material,
                     flip=self._cap_flip(rings[-1], rings[-2]))

    @staticmethod
    def _cap_flip(ring: np.ndarray, inward: np.ndarray) -> bool:
        """True when an unflipped fan over ``ring`` would face into the tube."""
        centre = ring.mean(axis=0)
        spokes = ring - centre
        normal = np.cross(spokes, np.roll(spokes, -1, axis=0)).sum(axis=0)
        outward = centre - np.asarray(inward, dtype=np.float64).mean(axis=0)
        return float(normal @ outward) < 0.0

    def fan(self, ring: np.ndarray, material: int = 0, *, flip: bool = False,
            apex: np.ndarray | None = None) -> None:
        ring = np.asarray(ring, dtype=np.float64)
        positions, uvs, faces = self.groups[material]
        centre = np.asarray(apex, dtype=np.float64) if apex is not None else ring.mean(axis=0)
        base = len(positions)
        positions.append(tuple(centre))
        uvs.append((.5, .5))
        sides = len(ring)
        for side in range(sides):
            angle = 2 * math.pi * side / sides
            positions.append(tuple(ring[side]))
            uvs.append((.5 + .5 * math.cos(angle), .5 + .5 * math.sin(angle)))
        self._tag(material, sides + 1)
        self._record(material, sides + 1)
        for side in range(sides):
            nxt = (side + 1) % sides
            triangle = (base, base + 1 + side, base + 1 + nxt)
            faces.extend(triangle[::-1] if flip else triangle)

    def revolve(self, profile: list[tuple[float, float]], material: int = 0, *,
                sides: int = 32, centre: tuple[float, float, float] = (0., 0., 0.),
                axis: str = "y", squash: tuple[float, float] = (1., 1.)) -> None:
        """Lathe a (radius, height) profile around an axis."""
        rings = []
        for radius, height in profile:
            ring = np.empty((sides, 3))
            for side in range(sides):
                angle = 2 * math.pi * side / sides
                u = radius * math.cos(angle) * squash[0]
                v = radius * math.sin(angle) * squash[1]
                if axis == "y":
                    ring[side] = (centre[0] + u, centre[1] + height, centre[2] + v)
                elif axis == "z":
                    ring[side] = (centre[0] + u, centre[1] + v, centre[2] + height)
                else:
                    ring[side] = (centre[0] + height, centre[1] + u, centre[2] + v)
            rings.append(ring)
        self.loft(rings, material)

    def tube(self, points: list[np.ndarray], radii: list[float], material: int = 0,
             *, sides: int = 16, cap: bool = True, twist: float = 0.0,
             squash: float = 1.0) -> None:
        """Sweep a circular section along a poly-line with parallel transport."""
        centres = np.asarray(points, dtype=np.float64)
        if len(centres) < 2:
            return
        rings = []
        previous_right = None
        for row, centre in enumerate(centres):
            if row == 0:
                tangent = centres[1] - centre
            elif row == len(centres) - 1:
                tangent = centre - centres[row - 1]
            else:
                tangent = centres[row + 1] - centres[row - 1]
            tangent = tangent / max(np.linalg.norm(tangent), 1e-9)
            if previous_right is None:
                reference = np.array([1., 0., 0.]) if abs(tangent[0]) < .82 else np.array([0., 0., 1.])
                right = np.cross(tangent, reference)
            else:
                right = previous_right - tangent * float(previous_right @ tangent)
            if np.linalg.norm(right) < 1e-6:
                right = np.cross(tangent, np.array([0., 1., 0.]))
            right = right / max(np.linalg.norm(right), 1e-9)
            forward = np.cross(right, tangent)
            previous_right = right
            ring = np.empty((sides, 3))
            for side in range(sides):
                angle = 2 * math.pi * side / sides + twist * row
                ring[side] = centre + (right * math.cos(angle) * radii[row]
                                       + forward * math.sin(angle) * radii[row] * squash)
            rings.append(ring)
        self.loft(rings, material, cap_start=cap, cap_end=cap)

    def sphere(self, centre, size, material: int = 0, *, rings: int = 18,
               sides: int = 28) -> None:
        cx, cy, cz = centre
        sx, sy, sz = (v * .5 for v in size)
        stack = []
        for ring in range(rings + 1):
            theta = math.pi * ring / rings
            circle = np.empty((sides, 3))
            for side in range(sides):
                phi = 2 * math.pi * side / sides
                circle[side] = (cx + sx * math.sin(theta) * math.cos(phi),
                                cy + sy * math.cos(theta),
                                cz + sz * math.sin(theta) * math.sin(phi))
            stack.append(circle)
        self.loft(stack, material)

    def box(self, centre, size, material: int = 0, *, bevel: float = .0) -> None:
        cx, cy, cz = centre
        sx, sy, sz = (v * .5 for v in size)
        inset = min(bevel, min(sx, sy, sz) * .48)
        profile = [(-sy, inset), (-sy + inset, 0.), (sy - inset, 0.), (sy, inset)]
        rings = []
        for height, shrink in profile:
            ring = np.array([
                (cx - sx + shrink, cy + height, cz - sz + shrink),
                (cx + sx - shrink, cy + height, cz - sz + shrink),
                (cx + sx - shrink, cy + height, cz + sz - shrink),
                (cx - sx + shrink, cy + height, cz + sz - shrink)])
            rings.append(ring)
        self.loft(rings, material, cap_start=True, cap_end=True)

    # -- assembly -----------------------------------------------------------

    def transform(self, matrix: np.ndarray) -> None:  # noqa: D102 - pins unmoved
        for positions, _, _ in self.groups:
            for index, point in enumerate(positions):
                vector = np.array([*point, 1.0])
                positions[index] = tuple((matrix @ vector)[:3])

    def mirrored_x(self) -> "Surface":
        clone = Surface(len(self.groups))
        for index, (positions, uvs, faces) in enumerate(self.groups):
            # A mirrored piece belongs to the mirrored bone, or the left cap
            # would arrive on the right shoulder still bound to the left arm.
            clone.pins[index].extend(_mirror_bone(bone) for bone in self.pins[index])
            target_positions, target_uvs, target_faces = clone.groups[index]
            target_positions.extend((-x, y, z) for x, y, z in positions)
            target_uvs.extend(uvs)
            clone.scopes[index].extend(self.scopes[index])
            # Mirroring reverses winding; restore it so back-faces stay culled.
            for i in range(0, len(faces), 3):
                target_faces.extend((faces[i], faces[i + 2], faces[i + 1]))
        return clone

    def extend(self, other: "Surface") -> None:
        for index, (positions, uvs, faces) in enumerate(other.groups):
            self.pins[index].extend(other.pins[index])
            target_positions, target_uvs, target_faces = self.groups[index]
            base = len(target_positions)
            target_positions.extend(positions)
            target_uvs.extend(uvs)
            target_faces.extend(base + i for i in faces)
            # A scope that was never set carries the empty string, which the
            # skinning falls back on; padding keeps the arrays aligned even
            # when the two surfaces disagree about whether they use scopes.
            scopes = other.scopes[index]
            self.scopes[index].extend(
                scopes + [""] * (len(positions) - len(scopes)))

    def face_outward(self) -> None:
        """Make every closed shell wind outwards, whatever built it.

        Added 2026-08-29 for Eloria Client.  A loft's winding follows the order
        of its rings, and a solid assembled from several lofts - a plate is two
        faces and four walls - has no single ring order to follow, so it comes
        out with its faces disagreeing.  An inside-out shell does not vanish:
        the renderer culls the near wall and it reads as an open-toed sandal
        with the foot inside it, which is how the sole of the shell this
        replaces shipped enclosing negative volume.

        Two passes per connected component.  First the faces are made to agree
        with each other by walking the adjacency graph and flipping any face
        that shares an edge in the same direction as its neighbour - on a
        manifold, neighbours traverse a shared edge in opposite directions.
        Then, if the agreed-upon orientation encloses negative volume, the whole
        component is flipped.  Components that enclose nothing are sheets and
        are left alone: they have no outside to face.
        """
        for material, (positions, _uvs, faces) in enumerate(self.groups):
            if not faces:
                continue
            points = np.asarray(positions, dtype=np.float64)
            triangles = np.asarray(faces, dtype=np.int64).reshape(-1, 3)
            _, inverse = np.unique(np.round(points, 5), axis=0,
                                   return_inverse=True)
            welded = inverse.reshape(-1)[triangles]
            fixed = _consistent_winding(points, triangles, welded)
            self.groups[material][2][:] = fixed.reshape(-1).tolist()

    def scope_array(self, material: int, count: int) -> np.ndarray:
        """Per-vertex skin scope for one material group, padded to ``count``."""
        scopes = self.scopes[material]
        if len(scopes) < count:
            scopes = scopes + [""] * (count - len(scopes))
        return np.asarray(scopes[:count], dtype=object)

    def arrays(self) -> list[tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]]:
        """Weld, smooth-shade and emit one array set per material group."""
        result = []
        for positions, uvs, faces in self.groups:
            if not faces:
                result.append((np.zeros((0, 3), "float32"), np.zeros((0, 3), "float32"),
                               np.zeros((0, 2), "float32"), np.zeros(0, "uint32")))
                continue
            points = np.asarray(positions, dtype=np.float64)
            indices = np.asarray(faces, dtype=np.int64)
            # Weld by position so lofted seams shade smoothly across the join.
            keys = np.round(points, 5)
            _, unique, inverse = np.unique(keys, axis=0, return_index=True,
                                           return_inverse=True)
            normals = np.zeros((len(points), 3))
            triangles = indices.reshape(-1, 3)
            edge_a = points[triangles[:, 1]] - points[triangles[:, 0]]
            edge_b = points[triangles[:, 2]] - points[triangles[:, 0]]
            face_normals = np.cross(edge_a, edge_b)
            welded = np.zeros((len(unique), 3))
            for column in range(3):
                np.add.at(welded, inverse[triangles[:, column]], face_normals)
            normals = welded[inverse]
            lengths = np.linalg.norm(normals, axis=1, keepdims=True)
            normals = np.where(lengths > 1e-9, normals / np.maximum(lengths, 1e-9),
                               np.array([0., 1., 0.]))
            result.append((points.astype("float32"), normals.astype("float32"),
                           np.asarray(uvs, dtype="float32").reshape(-1, 2),
                           indices.astype("uint32")))
        return result


def _consistent_winding(points: np.ndarray, triangles: np.ndarray,
                        welded: np.ndarray) -> np.ndarray:
    """Orient each connected component consistently, then outwards."""
    count = len(triangles)
    # Map every undirected welded edge to the faces that use it.
    edges: dict[tuple[int, int], list[int]] = {}
    for face in range(count):
        a, b, c = welded[face]
        for lo, hi in ((a, b), (b, c), (c, a)):
            edges.setdefault((min(lo, hi), max(lo, hi)), []).append(face)

    flipped = np.zeros(count, dtype=bool)
    seen = np.zeros(count, dtype=bool)
    result = triangles.copy()
    for seed in range(count):
        if seen[seed]:
            continue
        component = [seed]
        seen[seed] = True
        queue = [seed]
        while queue:
            face = queue.pop()
            tri = welded[face]
            if flipped[face]:
                tri = tri[::-1]
            for index in range(3):
                lo, hi = tri[index], tri[(index + 1) % 3]
                for other in edges.get((min(lo, hi), max(lo, hi)), ()):
                    if other == face or seen[other]:
                        continue
                    peer = welded[other]
                    # Neighbours on a manifold traverse a shared edge in
                    # opposite directions; agreeing means one of them is wrong.
                    # ``lo, hi`` already carries this face's own flip, so the
                    # neighbour is wrong exactly when it runs the shared edge
                    # the same way round.
                    flipped[other] = any(
                        peer[j] == lo and peer[(j + 1) % 3] == hi
                        for j in range(3))
                    seen[other] = True
                    component.append(other)
                    queue.append(other)
        block = np.array(component)
        oriented = np.where(flipped[block][:, None],
                            triangles[block][:, ::-1], triangles[block])
        verts = points[oriented]
        middle = verts.reshape(-1, 3).mean(axis=0)
        local = verts - middle
        volume = float(np.einsum("ij,ij->i", local[:, 0],
                                 np.cross(local[:, 1], local[:, 2])).sum() / 6.)
        result[block] = oriented[:, ::-1] if volume < 0.0 else oriented
    return result


# ---------------------------------------------------------------------------
# Body-conforming garment shells
# ---------------------------------------------------------------------------

TORSO_BONES = ["spine_01", "spine_02", "spine_03", "pelvis",
               "clavicle_l", "clavicle_r"]
# The seat, the outer hip and the top of the thigh belong to one silhouette.
# Trousers measured against the torso set alone never saw any of it.
HIP_BONES = ["pelvis", "spine_01", "thigh_l", "thigh_r"]
LEG_MEASURE_L = ["thigh_l", "calf_l", "pelvis"]
LEG_MEASURE_R = ["thigh_r", "calf_r", "pelvis"]
LEG_BONES_L = ["thigh_l", "calf_l"]
FOOT_BONES_L = ["foot_l", "ball_l"]
ARM_BONES_L = ["upperarm_l", "lowerarm_l"]

GARMENT_SKIN = {
    "torso": ["spine_01", "spine_02", "spine_03", "pelvis", "clavicle_l",
              "clavicle_r", "upperarm_l", "upperarm_r"],
    "skirt": ["pelvis", "spine_01", "thigh_l", "thigh_r", "calf_l", "calf_r"],
    "sleeve": ["upperarm_l", "upperarm_r", "lowerarm_l", "lowerarm_r",
               "clavicle_l", "clavicle_r"],
    "legs": ["pelvis", "thigh_l", "thigh_r", "calf_l", "calf_r", "foot_l", "foot_r"],
    "boots": ["calf_l", "calf_r", "foot_l", "foot_r", "ball_l", "ball_r"],
    "cape": ["spine_02", "spine_03", "clavicle_l", "clavicle_r", "pelvis", "spine_01"],
    "hands": ["hand_l", "hand_r", "lowerarm_l", "lowerarm_r",
              "index_01_l", "index_01_r", "middle_01_l", "middle_01_r",
              "ring_01_l", "ring_01_r", "pinky_01_l", "pinky_01_r",
              "thumb_01_l", "thumb_01_r"],
}


#: How far the tucked part of a shell is held off the skin, in metres.  Enough
#: to cover it and no more; it is under the trousers.
TUCK_CLEARANCE = .004


def chord_allowance(sides: int) -> float:
    """How much a ring has to be let out so its flats clear what it measured.

    Opt-in, through the ``chord`` flag on the ring builders, because it moves
    every vertex of anything that asks for it.  The torso set asks; the leg,
    boot and cape pipelines are left exactly as they were rather than quietly
    resized by a change that is not about them.  It applies to them too and they
    should take it when they are next touched.

    Added 2026-08-29 for Eloria Client.  A ring is a polygon through points
    sampled *on* the surface it is measuring, so between two samples it cuts
    inside that surface by the sagitta of the chord - about a millimetre at
    24 sides on a forearm, which is exactly the margin a close-cut sleeve has.
    One vertex per side, at the sharpest point of the Luminous arm section, came
    through there and nowhere else.  Scaling each radius by 1/cos(pi/sides)
    circumscribes the sampled surface instead of inscribing it, so the flats
    clear it and the sample points sit proud rather than flush.
    """
    return 1.0 / math.cos(math.pi / max(sides, 3))


def torso_rings(rig: Rig, y_low: float, y_high: float, *, rows: int = 14,
                sides: int = 28, thickness: float = .016,
                flare: float = 0.0, flare_low: float = 0.0, taper: float = 1.0,
                floor: float = .055, percentile: float = 96.0,
                chord: bool = False, tuck: float = 0.0, tuck_span: float = .18,
                bones: list[str] | None = None) -> list[np.ndarray]:
    """Rings that follow the measured torso silhouette between two heights."""
    axis_start = np.array([0., y_low, 0.])
    axis_end = np.array([0., y_high, 0.])
    rings = []
    for row in range(rows + 1):
        travel = row / rows
        height = y_low + (y_high - y_low) * travel
        measured = [rig.surface_radius(axis_start, axis_end, travel,
                                       2 * math.pi * side / sides,
                                       bones=bones or TORSO_BONES, slab=.05,
                                       default=floor, percentile=percentile)
                    for side in range(sides)]
        smoothed = smooth_profile(measured, floor)
        widen = thickness + flare * travel + flare_low * (1. - travel) ** 1.4
        scale = 1.0 + (taper - 1.0) * travel
        clearance = chord_allowance(sides) if chord else 1.0
        # Drawn in over the bottom of the shell only, and only as far as there
        # is room.  ``flare_low`` reaches a third of the way up even at its own
        # exponent, so using it to tuck a hem narrows the chest too and pays
        # coverage everywhere to fix one seam; this dies inside ``tuck_span``.
        #
        # The clamp is the other half of it.  Rings are sized from a slab that
        # reaches the hips, so at the waist a ring is hip-sized and stands clear
        # of the skin by however much the hips exceed the waist - and that is
        # the slack the tuck spends.  How much there is depends on the body: a
        # narrow waist under wide hips has plenty, a stoneborn female has about
        # 10 mm of it at the front, and taking a fixed 39 mm regardless left the
        # shell 7 to 16 mm inside her belly.  The tight measurement below says
        # where the skin is at this height and the tuck stops there.
        drawn = (tuck * (1. - travel / tuck_span) ** 2
                 if tuck and travel < tuck_span else 0.0)
        local = None
        if drawn:
            local = [rig.surface_radius(axis_start, axis_end, travel,
                                        2 * math.pi * side / sides,
                                        bones=bones or TORSO_BONES, slab=.016,
                                        default=floor, percentile=percentile)
                     for side in range(sides)]
        ring = np.empty((sides, 3))
        for side in range(sides):
            angle = 2 * math.pi * side / sides
            radius = (smoothed[side] * clearance + widen) * scale
            if drawn:
                # Held off the skin by ``TUCK_CLEARANCE`` rather than by the
                # garment's own thickness: this stretch of shell is inside the
                # trousers and never seen, and on a body where the trousers sit
                # close - a glasswarden female at y 1.062 - insisting on the
                # full thickness put the hem back outside them.  It only has to
                # clear the skin, not look like cloth.
                radius = max(radius - drawn * scale,
                             (local[side] * clearance + TUCK_CLEARANCE) * scale)
            ring[side] = (math.cos(angle) * radius, height, math.sin(angle) * radius)
        rings.append(ring)
    return rings


def limb_rings(rig: Rig, chain: list[str], *, rows: int = 12, sides: int = 20,
               thickness: float = .014, start: float = 0.0, end: float = 1.0,
               taper_end: float = 1.0, floor: float = .035,
               bones: list[str] | None = None,
               percentile: float = 96.0,
               chord: bool = False) -> list[np.ndarray]:
    """Rings around a limb chain, sampled from the real body surface."""
    joints = [rig.origin(bone) for bone in chain]
    tail = rig.segment(chain[-1])[1]
    spine = np.array(joints + [tail])
    lengths = np.linalg.norm(np.diff(spine, axis=0), axis=1)
    total = float(lengths.sum())
    cumulative = np.concatenate([[0.], np.cumsum(lengths)]) / max(total, 1e-9)
    rings = []
    for row in range(rows + 1):
        travel = start + (end - start) * (row / rows)
        centre = np.array([np.interp(travel, cumulative, spine[:, axis])
                           for axis in range(3)])
        segment = min(int(np.searchsorted(cumulative, travel, side="right")) - 1,
                      len(chain) - 1)
        segment = max(segment, 0)
        bone = chain[segment]
        bone_start, bone_end = rig.segment(bone)
        local = float(np.clip(np.linalg.norm(centre - bone_start)
                              / max(np.linalg.norm(bone_end - bone_start), 1e-9), 0., 1.))
        # The trouser leg used to measure against the leg chain alone.  The
        # seat and the outer hip are weighted to the pelvis, so at the top of
        # the thigh every sample fell back to the floor radius and the shell
        # closed *inside* the wearer - the backside came straight through it.
        measured = [rig.surface_radius(bone_start, bone_end, local,
                                       2 * math.pi * side / sides,
                                       bones=bones or chain, slab=.05,
                                       default=floor, percentile=percentile)
                    for side in range(sides)]
        smoothed = smooth_profile(measured, floor)
        axis = bone_end - bone_start
        axis = axis / max(np.linalg.norm(axis), 1e-9)
        reference = np.array([0., 1., 0.]) if abs(axis[1]) < .8 else np.array([0., 0., 1.])
        right = np.cross(axis, reference)
        right /= np.linalg.norm(right)
        forward = np.cross(right, axis)
        grow = 1.0 + (taper_end - 1.0) * (row / rows)
        ring = np.empty((sides, 3))
        for side in range(sides):
            angle = 2 * math.pi * side / sides
            clearance = chord_allowance(sides) if chord else 1.0
            radius = (smoothed[side] * clearance + thickness) * grow
            ring[side] = centre + (right * math.cos(angle)
                                   + forward * math.sin(angle)) * radius
        rings.append(ring)
    return rings


# ---------------------------------------------------------------------------
# Sockets
# ---------------------------------------------------------------------------

@dataclass
class Socket:
    """Rest placement of a rigid prop, expressed in character space.

    ``offset`` is measured from the anchor bone's rest origin and ``basis`` is
    the prop's rest orientation.  The runtime cancels the bone rest basis before
    applying either, so these numbers stay readable and rig independent.
    """

    bone: str
    offset: np.ndarray
    basis: np.ndarray

    def as_json(self, decimals: int = 5) -> dict:
        return {"bone": self.bone,
                "offset": [round(float(v), decimals) for v in self.offset],
                "rotationDegrees": [round(float(v), decimals)
                                    for v in basis_to_euler_degrees(self.basis)]}


def basis_to_euler_degrees(basis: np.ndarray) -> tuple[float, float, float]:
    """Decompose a rotation into Godot's YXZ intrinsic Euler convention."""
    matrix = np.asarray(basis, dtype=np.float64)
    sy = -matrix[1, 2]
    if abs(sy) < 1. - 1e-7:
        x = math.asin(sy)
        y = math.atan2(matrix[0, 2], matrix[2, 2])
        z = math.atan2(matrix[1, 0], matrix[1, 1])
    else:
        x = math.copysign(math.pi / 2, sy)
        y = math.atan2(-matrix[2, 0], matrix[0, 0])
        z = 0.0
    return tuple(math.degrees(v) for v in (x, y, z))


def euler_degrees_to_basis(angles) -> np.ndarray:
    x, y, z = (math.radians(v) for v in angles)
    cx, sx, cy, sy, cz, sz = (math.cos(x), math.sin(x), math.cos(y),
                              math.sin(y), math.cos(z), math.sin(z))
    rx = np.array([[1, 0, 0], [0, cx, -sx], [0, sx, cx]], dtype=np.float64)
    ry = np.array([[cy, 0, sy], [0, 1, 0], [-sy, 0, cy]], dtype=np.float64)
    rz = np.array([[cz, -sz, 0], [sz, cz, 0], [0, 0, 1]], dtype=np.float64)
    return ry @ rx @ rz


def grip_frame(rig: Rig, side: str) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Anatomical fist frame of one hand, in character space.

    Returned as (finger axis, grip axis, palm normal).  The grip axis runs
    through a closed fist and exits on the thumb side, which is where a hilt or
    a haft leaves the hand.
    """
    hand = f"hand_{side}"
    origin = rig.origin(hand)
    fingers = np.mean([rig.origin(f"{name}_03_{side}")
                       for name in ("index", "middle", "ring", "pinky")], axis=0) - origin
    fingers /= np.linalg.norm(fingers)
    thumb = rig.origin(f"thumb_03_{side}") - origin
    grip = thumb - fingers * float(thumb @ fingers)
    grip /= np.linalg.norm(grip)
    palm = np.cross(fingers, grip)
    palm /= np.linalg.norm(palm)
    return fingers, grip, palm


def palm_centre(rig: Rig, side: str) -> np.ndarray:
    fingers, _, _ = grip_frame(rig, side)
    return rig.origin(f"hand_{side}") + fingers * .052


def build_sockets(rig: Rig, idle_bases: dict[str, np.ndarray] | None = None,
                  kind: str = "") -> dict[int, Socket]:
    """Rest placement for every rigid equipment part, derived from the rig.

    Weapon and shield grips are solved in the reference idle pose when the idle
    hand bases are supplied, because that is the pose players spend their time
    looking at.  Head and chest sockets are pose independent.
    """
    sockets: dict[int, Socket] = {}

    fingers_r, grip_r, palm_r = grip_frame(rig, "r")
    # Model space for a weapon: +Y along the blade or haft, +X across the guard,
    # +Z through the flat.  Mapping +Y onto the fist's grip axis is what makes a
    # hilt sit in the hand instead of skewering it.
    weapon_basis = np.column_stack((fingers_r, grip_r, palm_r))
    if idle_bases is not None and kind in GRIP_UPRIGHT:
        weapon_basis = upright_grip_basis(rig, "r", idle_bases["r"],
                                          forward_lean=6.0)
    sockets[0] = Socket("hand_r", palm_centre(rig, "r") - rig.origin("hand_r"),
                        weapon_basis)

    fingers_l, grip_l, palm_l = grip_frame(rig, "l")
    # A centre-grip shield presents its face away from the fist and hangs its
    # long axis back along the forearm, so the point drops when the arm lowers.
    shield_y = -fingers_l
    shield_z = -grip_l
    shield_x = np.cross(shield_y, shield_z)
    shield_x /= np.linalg.norm(shield_x)
    shield_basis = np.column_stack((shield_x, shield_y, shield_z))
    if idle_bases is not None:
        shield_basis = posed_socket_basis(
            rig, "l", idle_bases["l"],
            up=np.array([0., 1., -.16]), face=np.array([.42, 0., 1.]))
    sockets[1] = Socket("hand_l", palm_centre(rig, "l") - rig.origin("hand_l"),
                        shield_basis)

    head_low, head_high = _bone_cluster_bounds(rig, ["Head"])
    head_centre = (head_low + head_high) * .5
    sockets[3] = Socket("Head", head_centre - rig.origin("Head"), np.eye(3))

    chest_low, chest_high = _bone_cluster_bounds(rig, ["spine_03"])
    collar = np.array([0., chest_high[1] - .055, chest_high[2] - .012])
    sockets[7] = Socket("spine_03", collar - rig.origin("spine_03"), np.eye(3))
    return sockets


def posed_socket_basis(rig: Rig, side: str, idle_basis: np.ndarray,
                       up: np.ndarray, face: np.ndarray) -> np.ndarray:
    """Rest-space socket basis that realises a desired idle-pose orientation."""
    up = np.asarray(up, dtype=np.float64)
    up = up / np.linalg.norm(up)
    face = np.asarray(face, dtype=np.float64)
    face = face - up * float(face @ up)
    face = face / np.linalg.norm(face)
    across = np.cross(up, face)
    desired = np.column_stack((across, up, face))
    return rig.basis(f"hand_{side}") @ (np.linalg.inv(idle_basis) @ desired)


def _bone_cluster_bounds(rig: Rig, bones: list[str], threshold: float = .5):
    indices = {rig.joint_names.index(bone) for bone in bones}
    mask = np.zeros(len(rig.positions), dtype=bool)
    total = np.zeros(len(rig.positions))
    for column in range(rig.joints.shape[1]):
        belongs = np.isin(rig.joints[:, column], list(indices))
        total += np.where(belongs, rig.weights[:, column], 0.0)
    mask = total >= threshold
    points = rig.positions[mask] if mask.any() else rig.positions
    return points.min(axis=0), points.max(axis=0)


# ---------------------------------------------------------------------------
# Prop geometry (authored in item space: +Y along the item, origin at the grip)
# ---------------------------------------------------------------------------

MATERIAL_BASE, MATERIAL_TRIM, MATERIAL_DETAIL = 0, 1, 2


def _hilt(surface: Surface, *, grip_low: float = -.11, grip_high: float = .015,
          guard_span: float = .105, pommel: bool = True) -> None:
    surface.tube([np.array([0., grip_low, 0.]), np.array([0., grip_low + .02, 0.]),
                  np.array([0., grip_high - .02, 0.]), np.array([0., grip_high, 0.])],
                 [.014, .019, .019, .015], MATERIAL_DETAIL, sides=14)
    surface.revolve([(.0, .0), (.026, .008), (.030, .018), (.020, .030), (.0, .036)],
                    MATERIAL_TRIM, sides=18, centre=(0., grip_high, 0.),
                    squash=(guard_span / .030, 1.))
    if pommel:
        surface.sphere((0., grip_low - .012, 0.), (.040, .042, .040),
                       MATERIAL_TRIM, rings=10, sides=16)


def _blade(surface: Surface, length: float, width: float, *, base: float = .02,
           thickness: float = .011, curve: float = 0.0, fuller: bool = True) -> None:
    rows = 18
    rings = []
    for row in range(rows + 1):
        travel = row / rows
        height = base + (length - base) * travel
        taper = math.sin((1. - travel) * math.pi * .5) ** .55
        half = max(width * .5 * taper, .002)
        depth = max(thickness * .5 * (taper ** .6), .0016)
        drift = curve * (travel ** 1.7)
        waist = .62 if fuller else 1.0
        ring = np.array([
            (drift, height, -depth),
            (drift + half * .55, height, -depth * waist),
            (drift + half, height, 0.),
            (drift + half * .55, height, depth * waist),
            (drift, height, depth),
            (drift - half * .55, height, depth * waist),
            (drift - half, height, 0.),
            (drift - half * .55, height, -depth * waist)])
        rings.append(ring)
    surface.loft(rings, MATERIAL_BASE, cap_start=True)
    surface.fan(rings[-1], MATERIAL_BASE, apex=np.array([curve, length + .045, 0.]))


def _haft(surface: Surface, low: float, high: float, radius: float,
          material: int = MATERIAL_DETAIL, *, sides: int = 16) -> None:
    rows = 10
    points = [np.array([0., low + (high - low) * i / rows, 0.]) for i in range(rows + 1)]
    radii = [radius * (1. - .16 * abs(i / rows - .5)) for i in range(rows + 1)]
    surface.tube(points, radii, material, sides=sides)
    for height in (low + (high - low) * .28, low + (high - low) * .72):
        surface.revolve([(.0, -.014), (radius * 1.5, -.010), (radius * 1.5, .010), (.0, .014)],
                        MATERIAL_TRIM, sides=sides, centre=(0., height, 0.))


def prop_geometry(kind: str) -> Surface:
    """Dense, silhouette-correct props authored at real weapon scale."""
    surface = Surface()
    if kind == "sword":
        _hilt(surface)
        _blade(surface, .74, .062, base=.03, thickness=.012)
    elif kind == "greatsword":
        # A two-hander: longer grip, wider quillons, a heavier blade.
        _hilt(surface, grip_low=-.20, grip_high=.020, guard_span=.150)
        _blade(surface, .96, .086, base=.04, thickness=.016)
    elif kind == "curved_sword":
        _hilt(surface, grip_low=-.10, grip_high=.012, guard_span=.085)
        _blade(surface, .70, .066, base=.03, thickness=.012, curve=.115,
               fuller=False)
        # Knuckle bow, which is what reads a cutlass apart from a longsword.
        surface.tube([np.array([.030, .010, 0.]), np.array([.105, -.040, 0.]),
                      np.array([.090, -.115, 0.]), np.array([.010, -.130, 0.])],
                     [.011, .013, .013, .011], MATERIAL_TRIM, sides=10)
    elif kind == "rapier":
        _hilt(surface, grip_low=-.10, grip_high=.010, guard_span=.052,
              pommel=True)
        _blade(surface, .82, .028, base=.03, thickness=.020, fuller=False)
        # Swept cup guard.
        cup = []
        for travel, radius, depth in ((.0, .022, .010), (.35, .056, -.010),
                                       (.70, .070, -.040), (1.0, .066, -.070)):
            ring = np.empty((20, 3))
            for index in range(20):
                angle = 2 * math.pi * index / 20
                ring[index] = (math.cos(angle) * radius, .010 - depth,
                               math.sin(angle) * radius)
            cup.append(ring)
        surface.loft(cup, MATERIAL_TRIM)
    elif kind == "glaive":
        _haft(surface, -.42, .58, .019)
        _blade(surface, 1.02, .085, base=.55, thickness=.014, curve=.055)
        surface.revolve([(.0, .0), (.030, .012), (.024, .034), (.0, .046)],
                        MATERIAL_TRIM, sides=18, centre=(0., .55, 0.))
    elif kind in {"spear", "harpoon"}:
        _haft(surface, -.52, 1.02, .017)
        surface.revolve([(.0, .0), (.034, .05), (.026, .13), (.011, .21), (.0, .27)],
                        MATERIAL_BASE, sides=20, centre=(0., 1.00, 0.))
        if kind == "harpoon":
            for sign in (-1., 1.):
                surface.tube([np.array([0., 1.10, 0.]), np.array([sign * .055, 1.02, 0.])],
                             [.012, .004], MATERIAL_TRIM, sides=10)
    elif kind == "staff":
        _haft(surface, -.48, .92, .017, sides=18)
        surface.revolve([(.0, .0), (.028, .022), (.036, .060), (.030, .100), (.0, .126)],
                        MATERIAL_TRIM, sides=22, centre=(0., .92, 0.))
        surface.sphere((0., 1.08, 0.), (.105, .118, .105), MATERIAL_BASE,
                       rings=16, sides=24)
    elif kind == "mace":
        _haft(surface, -.34, .50, .018)
        surface.sphere((0., .565, 0.), (.098, .105, .098), MATERIAL_BASE,
                       rings=14, sides=20)
        head = np.array([0., .565, 0.])
        for index in range(6):
            angle = 2 * math.pi * index / 6
            radial = np.array([math.cos(angle), 0., math.sin(angle)])
            surface.tube([head + radial * .055, head + radial * .148],
                         [.030, .004], MATERIAL_TRIM, sides=10)
        surface.tube([np.array([0., .625, 0.]), np.array([0., .70, 0.])],
                     [.030, .004], MATERIAL_TRIM, sides=10)
    elif kind == "battleaxe":
        _haft(surface, -.34, .46, .021)
        # A bearded double head: two swept crescents either side of the haft.
        for sign in (-1., 1.):
            blade = []
            for travel in np.linspace(0., 1., 12):
                reach = sign * (.052 + .150 * math.sin(travel * math.pi) ** .70)
                height = .560 - .230 * travel
                half = .020 + .020 * math.sin(travel * math.pi)
                blade.append(np.array([
                    (sign * .034, height + half, -.011),
                    (reach, height + half * .55, -.007),
                    (reach, height - half * .55, .007),
                    (sign * .034, height - half, .011)]))
            surface.loft(blade, MATERIAL_BASE, cap_start=True, cap_end=True)
        surface.revolve([(.0, .0), (.036, .020), (.030, .052), (.0, .070)],
                        MATERIAL_TRIM, sides=18, centre=(0., .500, 0.))
    elif kind == "club":
        # A knot of bone or a stripped branch: no edge, all weight at the end.
        surface.tube([np.array([0., -.30, 0.]), np.array([0., -.10, 0.]),
                      np.array([0., .16, 0.]), np.array([0., .40, 0.]),
                      np.array([0., .58, 0.])],
                     [.021, .024, .030, .042, .050], MATERIAL_BASE, sides=14)
        surface.sphere((0., .615, 0.), (.108, .096, .102), MATERIAL_BASE,
                       rings=12, sides=18)
        for index in range(4):
            angle = 2 * math.pi * index / 4 + .4
            surface.sphere((math.cos(angle) * .052, .630, math.sin(angle) * .050),
                           (.040, .036, .038), MATERIAL_TRIM, rings=8, sides=12)
    elif kind == "quiver":
        # Worn on the off-hand slot, so it is authored like a held prop.
        surface.revolve([(.0, -.20), (.058, -.19), (.062, .0), (.066, .18),
                         (.060, .21)], MATERIAL_BASE, sides=20)
        for height in (-.14, .04, .17):
            surface.revolve([(.0, -.014), (.070, -.010), (.070, .010), (.0, .014)],
                            MATERIAL_TRIM, sides=20, centre=(0., height, 0.))
        for index in range(7):
            angle = 2 * math.pi * index / 7
            base = np.array([math.cos(angle) * .030, .190, math.sin(angle) * .030])
            surface.tube([base, base + np.array([0., .155, 0.])],
                         [.005, .005], MATERIAL_DETAIL, sides=6)
            surface.revolve([(.0, .0), (.017, .020), (.0, .042)], MATERIAL_TRIM,
                            sides=8, centre=(base[0], .330, base[2]))
    elif kind == "hammer":
        _haft(surface, -.36, .52, .020)
        surface.box((0., .565, 0.), (.215, .105, .105), MATERIAL_BASE, bevel=.022)
        for sign in (-1., 1.):
            surface.revolve([(.052, .0), (.050, .014), (.030, .026), (.0, .030)],
                            MATERIAL_TRIM, sides=16, centre=(sign * .107, .565, 0.),
                            axis="x")
    elif kind == "pick":
        _haft(surface, -.36, .52, .019)
        surface.tube([np.array([-.235, .520, 0.]), np.array([-.10, .585, 0.]),
                      np.array([.06, .585, 0.]), np.array([.225, .512, 0.])],
                     [.006, .034, .034, .006], MATERIAL_BASE, sides=14)
        surface.sphere((0., .578, 0.), (.070, .062, .062), MATERIAL_TRIM,
                       rings=10, sides=16)
    elif kind in {"bow", "crossbow"}:
        limb = [np.array([0., -.62, .015]), np.array([.030, -.40, -.010]),
                np.array([.046, -.14, -.026]), np.array([.050, 0., -.028]),
                np.array([.046, .14, -.026]), np.array([.030, .40, -.010]),
                np.array([0., .62, .015])]
        radii = [.008, .017, .021, .022, .021, .017, .008]
        surface.tube(limb, radii, MATERIAL_BASE, sides=12)
        surface.tube([np.array([0., -.61, .014]), np.array([0., 0., .012]),
                      np.array([0., .61, .014])], [.0035, .0035, .0035],
                     MATERIAL_TRIM, sides=8)
        surface.tube([np.array([0., -.075, -.030]), np.array([0., .075, -.030])],
                     [.026, .026], MATERIAL_DETAIL, sides=12)
        if kind == "crossbow":
            surface.box((0., -.05, -.16), (.050, .052, .380), MATERIAL_DETAIL, bevel=.014)
            surface.box((0., -.10, -.30), (.036, .088, .090), MATERIAL_TRIM, bevel=.012)
    elif kind in {"roundshield", "kite", "shell"}:
        surface.extend(_shield_body(kind))
    elif kind in {"helm", "crest"}:
        surface.extend(_helm_body(crest=(kind == "crest")))
    elif kind == "hood":
        surface.extend(_hood_body())
    elif kind == "circlet":
        surface.extend(_circlet_body())
    elif kind == "mushroom":
        surface.extend(_mushroom_body())
    elif kind == "amulet":
        surface.extend(_amulet_body())
    return surface


def _shield_outline(kind: str, sides: int) -> np.ndarray:
    """Half-extents of the shield face, sampled once per rim vertex."""
    outline = np.empty((sides, 2))
    for side in range(sides):
        angle = 2 * math.pi * side / sides
        x, y = math.cos(angle), math.sin(angle)
        if kind == "kite":
            # Rounded shoulders that draw down to a point.
            taper = .58 + .42 * max(y, 0.) ** .8 if y < 0 else 1.0
            outline[side] = (x * .215 * taper, y * (.30 if y > 0 else .40))
        elif kind == "shell":
            ridge = 1.0 + .10 * math.cos(angle * 5.)
            outline[side] = (x * .235 * ridge, y * .235 * ridge)
        else:
            outline[side] = (x * .245, y * .245)
    return outline


def _shield_body(kind: str) -> Surface:
    """A dished shield: rim, face, boss and back-side arm straps."""
    surface = Surface()
    sides = 40
    outline = _shield_outline(kind, sides)
    rings = []
    # Depth profile: the face dishes forward, the rim rolls back.
    for scale, depth in ((.0, .052), (.30, .048), (.58, .038), (.80, .024),
                         (.94, .006), (1.0, -.004), (.985, -.020), (.92, -.026)):
        ring = np.empty((sides, 3))
        for side in range(sides):
            ring[side] = (outline[side][0] * scale, outline[side][1] * scale, depth)
        rings.append(ring)
    surface.loft(rings, MATERIAL_BASE)
    surface.fan(rings[0], MATERIAL_BASE, flip=True,
                apex=np.array([0., 0., .060]))
    back = []
    for scale, depth in ((.92, -.026), (.60, -.030), (.28, -.032), (.0, -.030)):
        ring = np.empty((sides, 3))
        for side in range(sides):
            ring[side] = (outline[side][0] * scale, outline[side][1] * scale, depth)
        back.append(ring)
    surface.loft(back, MATERIAL_DETAIL)
    surface.revolve([(.0, .058), (.042, .070), (.062, .056), (.070, .030), (.0, .018)],
                    MATERIAL_TRIM, sides=24, axis="z")
    for offset in (-.085, .085):
        surface.tube([np.array([-.11, offset, -.030]), np.array([-.05, offset, -.062]),
                      np.array([.05, offset, -.062]), np.array([.11, offset, -.030])],
                     [.011, .014, .014, .011], MATERIAL_DETAIL, sides=10)
    if kind == "shell":
        for index in range(5):
            angle = math.pi * (index / 4.) - math.pi * .5
            surface.tube([np.array([0., 0., .052]),
                          np.array([math.cos(angle) * .225, math.sin(angle) * .225, .010])],
                         [.016, .006], MATERIAL_TRIM, sides=8)
    return surface


def _helm_body(*, crest: bool) -> Surface:
    """A skull-fitting helm: dome, brow band, cheek guards, optional crest."""
    surface = Surface()
    dome = []
    rows = 14
    for row in range(rows + 1):
        travel = row / rows
        theta = math.pi * .5 * travel
        ring = np.empty((26, 3))
        for side in range(26):
            phi = 2 * math.pi * side / 26
            falloff = max(math.cos(theta), 0.) ** .82
            radius_x = .108 * falloff
            radius_z = .122 * falloff
            ring[side] = (math.cos(phi) * radius_x,
                          -.020 + math.sin(theta) * .148,
                          math.sin(phi) * radius_z)
        dome.append(ring)
    surface.loft(dome, MATERIAL_BASE)
    surface.fan(dome[-1], MATERIAL_BASE, apex=np.array([0., .132, 0.]))
    skirt = []
    for travel, radius, height in ((.0, 1.00, -.020), (.35, 1.03, -.062),
                                   (.70, 1.01, -.100), (1.0, .94, -.126)):
        ring = np.empty((26, 3))
        for side in range(26):
            phi = 2 * math.pi * side / 26
            ring[side] = (math.cos(phi) * .108 * radius, height,
                          math.sin(phi) * .122 * radius)
        skirt.append(ring)
    surface.loft(skirt, MATERIAL_BASE)
    surface.revolve([(.0, .0), (.118, .006), (.126, .020), (.118, .034), (.0, .040)],
                    MATERIAL_TRIM, sides=26, centre=(0., -.028, 0.),
                    squash=(1., 1.13))
    # Nasal bar and brow, so the face reads through the opening.
    surface.tube([np.array([0., .030, .116]), np.array([0., -.052, .124]),
                  np.array([0., -.096, .110])], [.014, .016, .012],
                 MATERIAL_TRIM, sides=10)
    if crest:
        fin = []
        for travel in np.linspace(0., 1., 12):
            height = .128 + .086 * math.sin(travel * math.pi) ** .7
            depth = -.088 + .200 * travel
            fin.append(np.array([
                (-.011, height - .010, depth), (.011, height - .010, depth),
                (.011, height, depth), (-.011, height, depth)]))
        surface.loft(fin, MATERIAL_TRIM, cap_start=True, cap_end=True)
    return surface


def _hood_body() -> Surface:
    """A soft hood: cowl shell, folded brim and a shoulder drape."""
    surface = Surface()
    rows, sides = 16, 26
    shell = []
    for row in range(rows + 1):
        travel = row / rows
        theta = math.pi * .50 * travel
        ring = np.empty((sides, 3))
        for side in range(sides):
            phi = 2 * math.pi * side / sides
            back = max(0., -math.sin(phi))
            falloff = max(math.cos(theta), 0.) ** .52
            radius_x = .122 * falloff
            radius_z = .134 * falloff * (1. + .26 * back)
            ring[side] = (math.cos(phi) * radius_x,
                          -.056 + math.sin(theta) * .142 + back * .020 * travel,
                          math.sin(phi) * radius_z - back * .030 * travel)
        shell.append(ring)
    surface.loft(shell, MATERIAL_BASE)
    surface.fan(shell[-1], MATERIAL_BASE, apex=np.array([0., .098, -.026]))
    brim = []
    for scale, height, depth in ((1.0, -.052, .0), (1.10, -.076, .012),
                                  (1.12, -.104, .022), (1.02, -.124, .014)):
        ring = np.empty((sides, 3))
        for side in range(sides):
            phi = 2 * math.pi * side / sides
            front = max(0., math.sin(phi))
            ring[side] = (math.cos(phi) * .120 * scale, height + front * .020,
                          math.sin(phi) * .132 * scale + front * .022)
        brim.append(ring)
    surface.loft(brim, MATERIAL_TRIM)
    return surface


def _circlet_body() -> Surface:
    surface = Surface()
    sides = 34
    band = []
    for height, radius in ((.020, 1.0), (.036, 1.03), (.058, 1.03), (.074, 1.0)):
        ring = np.empty((sides, 3))
        for side in range(sides):
            phi = 2 * math.pi * side / sides
            ring[side] = (math.cos(phi) * .104 * radius, height,
                          math.sin(phi) * .118 * radius)
        band.append(ring)
    surface.loft(band, MATERIAL_BASE)
    for index in range(9):
        phi = math.pi * (.18 + .64 * index / 8.)
        height = .076 + .034 * math.sin(index / 8. * math.pi) ** .6
        base = np.array([math.cos(phi) * .104, .066, math.sin(phi) * .118])
        surface.tube([base, base * np.array([1., 0., 1.]) + np.array([0., height, 0.])],
                     [.014, .003], MATERIAL_TRIM, sides=8)
    surface.sphere((0., .092, .118), (.044, .046, .034), MATERIAL_TRIM,
                   rings=12, sides=18)
    return surface


def _mushroom_body() -> Surface:
    surface = Surface()
    surface.revolve([(.020, -.048), (.086, -.030), (.104, .0), (.098, .034),
                     (.070, .058)], MATERIAL_DETAIL, sides=24)
    cap = []
    for radius, height in ((.0, .152), (.070, .140), (.132, .108), (.176, .062),
                            (.196, .018), (.190, -.006), (.150, -.014),
                            (.090, -.026), (.0, -.030)):
        ring = np.empty((28, 3))
        for side in range(28):
            phi = 2 * math.pi * side / 28
            wobble = 1. + .045 * math.cos(phi * 6.)
            ring[side] = (math.cos(phi) * radius * wobble, height,
                          math.sin(phi) * radius * wobble)
        cap.append(ring)
    surface.loft(cap, MATERIAL_BASE)
    for index in range(11):
        phi = 2 * math.pi * index / 11
        surface.sphere((math.cos(phi) * .118, .114, math.sin(phi) * .118),
                       (.030, .020, .030), MATERIAL_TRIM, rings=8, sides=12)
    return surface


def _amulet_body() -> Surface:
    """A cord that follows the collar line, with a pendant on the sternum."""
    surface = Surface()
    cord = []
    steps = 44
    for step in range(steps + 1):
        angle = math.pi * (-.92 + 1.84 * step / steps)
        drop = .052 * math.sin(step / steps * math.pi) ** 1.6
        cord.append(np.array([math.sin(angle) * .082, -drop,
                              -math.cos(angle) * .062 + .020]))
    surface.tube(cord, [.0055] * len(cord), MATERIAL_DETAIL, sides=8, cap=False)
    surface.revolve([(.0, -.030), (.030, -.018), (.038, .0), (.030, .018), (.0, .030)],
                    MATERIAL_BASE, sides=20, centre=(0., -.086, .028), axis="z",
                    squash=(1., 1.))
    surface.sphere((0., -.086, .034), (.034, .034, .020), MATERIAL_TRIM,
                   rings=12, sides=18)
    surface.tube([np.array([0., -.052, .022]), np.array([0., -.070, .026])],
                 [.008, .008], MATERIAL_TRIM, sides=8)
    return surface


# ---------------------------------------------------------------------------
# Garment geometry (authored in character space at the rig's rest pose)
# ---------------------------------------------------------------------------

@dataclass
class Garment:
    surface: Surface
    skin_region: str


def _belt(surface: Surface, rig: Rig, height: float, *, thickness: float = .030,
          sides: int = 28, material: int = MATERIAL_TRIM) -> None:
    rings = torso_rings(rig, height - .022, height + .022, rows=3, sides=sides,
                        thickness=thickness)
    surface.loft(rings, material)


# ---------------------------------------------------------------------------
# The waist datum, shared with the leg-garment pipeline
# ---------------------------------------------------------------------------
# World Y on the reference rig ``luminous_male``.  The torso garment is the
# *inner* layer at this seam: its hem runs inside the trousers, whose waist is
# at 1.0770 and whose belt is at 1.0550.  A hem at or below 1.0300 therefore
# keeps at least 45 mm of itself inside the trousers on the reference body.
#
# The torso garment no longer carries a belt of its own.  There used to be two,
# 52 mm apart on the same waist - this one at 1.1070 and the trouser's at 1.0550
# - and the upper one sat 30 mm *above* the trouser top, so the eye read the
# shirt as ending at its own belt and the trousers as starting somewhere behind
# it.  The belt belongs to the trousers.  A torso piece asks for one only where
# its concept sheet draws a belt that is part of the garment - a plate fauld
# strap, a sash - and gets it high enough on the ribs to read as part of the
# garment rather than as a second waist.
TORSO_HEM = 1.0220
SKIRTED_HEM = 1.0100
COLLAR = 1.4920
COLLAR_TOP = 1.5400

#: Where a sleeve may not end, as a fraction of the shoulder-to-wrist chain.
#:
#: The arm is not round.  Its section at mid humerus is a teardrop - on the
#: reference body, 10 mm in front of the bone and 155 mm behind it - and it
#: comes to a point at the back.  An opening cut across that point sits on the
#: sharpest, most mobile part of the limb, where the skin's blend and the
#: cloth's stop agreeing, and two vertices per arm come through it when the
#: elbow bends.  Widening the cuff does not help, because the opening moves out
#: with it.  Every other length measures clean on every race in every clip, so
#: the fix is simply not to cut a sleeve here - which is also why a real sleeve
#: is not cut at the elbow.
SLEEVE_APEX = (.36, .50)


def sleeve_clear(end: float) -> bool:
    """Is this a length a sleeve may end at?  See ``SLEEVE_APEX``."""
    return not SLEEVE_APEX[0] < end < SLEEVE_APEX[1]


def _shoulder_cap(surface: Surface, rig: Rig, *, inboard: float = -.85,
                  outboard: float = .46, swell: float = 1.38,
                  thickness: float = .012, lift: float = .026,
                  material: int = MATERIAL_BASE, sides: int = 20,
                  rows: int = 9) -> None:
    """The closed cap over each shoulder, turning with the arm it covers.

    This is the fix for the defect the whole rebuild exists to close: skin
    showing through at the shoulder.  Two things were wrong with the pad it
    replaces.

    It was *open* - a bare tube, capped at neither end - so it enclosed nothing,
    and the body shell and the sleeve had to meet it edge to edge across the
    deltoid.  Three open edges over a joint is three chances to part.

    And it was *blended*, taking its skin weights from the body underneath like
    every other garment vertex, which means part clavicle and part humerus.  The
    clavicle barely turns when an arm goes up, so a blended cap lags behind the
    arm it is covering and the seam opens exactly when the arm is raised - which
    is why the gap survived a bind-pose screenshot and still appeared in play.

    The cap here is a closed capsule swept about the humerus and pinned wholly
    to it, so it is rigid with respect to the joint it covers: at any arm angle
    it holds the same skin it held in the T-pose.  It reaches inboard far enough
    to sit inside the body shell and outboard far enough to sit inside the
    sleeve, so the three overlap as solids instead of meeting as edges.

    ``inboard`` and ``outboard`` are fractions of the humerus, measured from the
    shoulder joint.  ``swell`` is how much wider than the arm the cap runs, which
    is where a linen shirt and a steel pauldron part company.
    """
    for side in ("l", "r"):
        joint = rig.origin(f"upperarm_{side}")
        elbow = rig.origin(f"lowerarm_{side}")
        axis = elbow - joint
        span = float(np.linalg.norm(axis))
        axis = axis / max(span, 1e-9)
        reference = np.array([0., 1., 0.]) if abs(axis[1]) < .8 else np.array([0., 0., 1.])
        right = np.cross(axis, reference)
        right /= np.linalg.norm(right)
        forward = np.cross(right, axis)
        # The arm alone.  Measuring the shoulder *region* - clavicle and
        # spine_03 as well - and then taking the widest reading in the sector
        # meant the cap sized itself against the far side of the upper back: it
        # covered everything the checker asked about by being an enormous block
        # across both shoulders and over the head.  Coverage is not silhouette,
        # and a number that only counts skin will happily accept a tent.
        measure = [f"upperarm_{side}"]
        # The arm's own half-width just below the joint, which every ring is
        # sized relative to.
        arm = max(rig.surface_radius(joint, elbow, .12, angle, bones=measure,
                                     slab=.05, default=.055)
                  for angle in (0.0, math.pi * .5, math.pi, math.pi * 1.5))
        rings = []
        for row in range(rows + 1):
            travel = inboard + (outboard - inboard) * (row / rows)
            # A plateau, not an arch.  Tapering away from the joint made the cap
            # narrowest at its outboard end, which is exactly where a sleeveless
            # design has nothing else covering the arm - two vertices behind each
            # deltoid came through there.  Full width across the middle two
            # thirds, rounded off only close enough to each end to close.
            edge = min(row, rows - row) / (rows * .11)
            arch = .12 + .88 * min(1., edge) ** .34
            centre = joint + axis * (travel * span) + np.array([0., lift, 0.])
            # Pull the ring onto the middle of the shoulder.  Fully at the
            # deltoid, less so at the ends, where the cap has to close into the
            # body shell and the sleeve rather than wander off the bone they are
            # both built around.
            found = rig.slab_centre(joint, elbow, travel, bones=measure)
            if found is not None:
                pull = .78 * min(1., min(row, rows - row) / (rows * .34))
                centre = centre + (found + np.array([0., lift, 0.]) - centre) * pull
            measured = [rig.surface_radius(joint, elbow, max(travel, .02),
                                           2 * math.pi * slot / sides,
                                           bones=measure, slab=.06, default=.050,
                                           centre=centre, percentile=100.0)
                        for slot in range(sides)]
            smoothed = smooth_profile(measured, .042)
            # No ring wider than this: a pauldron is a pauldron, not a barrel.
            # Measured against the arm at the joint, which is the thing the cap
            # is actually a cap for.
            ceiling = arm * 2.4
            ring = np.empty((sides, 3))
            for slot in range(sides):
                angle = 2 * math.pi * slot / sides
                radius = (min(smoothed[slot], ceiling) * swell
                          * chord_allowance(sides) + thickness) * arch
                ring[slot] = centre + (right * math.cos(angle)
                                       + forward * math.sin(angle)) * radius
            rings.append(ring)
        # Pinned to the humerus alone - see the docstring.  Closed at both ends:
        # the inboard lid sits inside the body shell and the outboard one inside
        # the sleeve, so neither is ever seen.
        with surface.pinned(f"upperarm_{side}"):
            surface.loft(rings, material, cap_start=True, cap_end=True)


def _sleeves(surface: Surface, rig: Rig, *, end: float, material: int,
             thickness: float = .020, start: float = .10,
             cuff: float = .020) -> None:
    """A closed sleeve down each arm, rooted inside the shoulder cap.

    ``start`` used to be .02 - the sleeve began at the shoulder joint itself, so
    the cap had to close a seam sitting right on the axis of rotation.  It now
    starts well down the humerus, inside the cap, and the two overlap as solids.

    ``cuff`` is a second, wider tube over the last of the sleeve.  A sleeve cut
    to the arm all the way to its opening is the one place left where skin gets
    out: the last ring of it is only millimetres clear, and the elbow bending
    slides the arm inside the cloth by more than that - twelve vertices on the
    back of each forearm came through at ``Jog`` and at nothing else.  A real
    sleeve is wider at the opening than along its length, and so is this one.
    """
    for side in ("l", "r"):
        chain = [f"upperarm_{side}", f"lowerarm_{side}"]
        # 24 sides, not 18.  The Luminous arm is not round: its section at mid
        # humerus reaches 10 mm in front of the bone and 155 mm behind it, and
        # at 18 sides the loft cuts the corner at the back of that sweep.
        # A slight flare towards the opening, which is how a sleeve is cut and
        # also what lifts the last rings clear of an arm sliding inside them.
        rings = limb_rings(rig, chain, rows=14, sides=28, thickness=thickness,
                           start=start, end=end, floor=.040, taper_end=1.07,
                           percentile=100.0, chord=True)
        # Closed at both ends.  The shoulder lid is buried in the cap; the cuff
        # lid is an annulus no wider than the cloth is thick, which is what the
        # edge of a sleeve looks like anyway.
        surface.loft(rings, material, cap_start=True, cap_end=True)
        if cuff:
            opening = limb_rings(rig, chain, rows=4, sides=28,
                                 thickness=thickness + cuff,
                                 start=max(start, end - .12), end=end + .016,
                                 floor=.040, taper_end=1.10, percentile=100.0,
                                 chord=True)
            surface.loft(opening, material, cap_start=True, cap_end=True)


#: Sweep hooks: set by the calibration sweep so the shell's clearance can be
#: measured rather than argued about.  See torso_prototype.py.
_SHELL_PERCENTILE = 100.0
_SHELL_FLARE = .012
#: How far the hem is drawn in so it finishes *inside* the trousers.
#:
#: The torso garment is the inner layer at the waist, and being long enough is
#: not sufficient - a hem that reaches inside the waistband but is cut wider
#: than it pushes straight back out through it, which on screen is
#: indistinguishable from a gap.  Both pipelines size their rings from a slab
#: that reaches the hips, so at the narrow waist both are hip-sized and the
#: difference between them is not the difference between the two declared
#: thicknesses: measured garment against garment over all sixteen races, the
#: untucked shell stood 30 mm proud of the trousers.
_SHELL_TUCK = .055
#: How far up the shell the tuck reaches, as a fraction of its height.
#:
#: At .18 the taper had died out 40 mm above the hem and a shirt still stood
#: 3 mm outside the trousers there.  Nothing shallower closes it: .22 span fails,
#: and so does .040 of tuck over this span.
#:
#: This setting is a trade and it is worth stating.  With trousers on - which is
#: every state the protocol can produce, since part 4 always carries at least an
#: appearance byte - it costs nothing: 207 exposed body vertices against 206 at
#: .18, and the shoulder figure does not move at all.  With bare legs it costs
#: a good deal: 655 against 206, worst 20 on a mesh against 6.  The waist seam
#: the player can actually see was the reported defect; a torso garment worn
#: over nothing is a test construct.
_SHELL_TUCK_SPAN = .26


def _torso_shell(rig: Rig, waist: float, *, thickness: float = .011,
                 sides: int = 30, rows: int = 26) -> list:
    """Rings from the hem to the top of the collar, as one continuous tube.

    26 rows, not 18.  A loft chords straight between its rings, and at 18 rows
    they are 26 mm apart - far enough that the chord cuts inside a belly that
    bulges between two of them.  Fifteen vertices came through the front of a
    stoneborn female's waist that way, not because the shell was too narrow
    there but because it was too coarse.

    The body used to stop at the collar and a separate band carry on above it.
    Two lofts in two material groups are two primitives and so two shells, and
    the lower one was closed at neither end - a bowl the neck sat in.  The base
    layer now runs the whole way up and draws in around the neck, and the collar
    trim is a band worn over it rather than the only thing closing it.
    """
    rings = torso_rings(rig, waist, COLLAR, rows=rows, sides=sides,
                        thickness=thickness, flare_low=_SHELL_FLARE,
                        percentile=_SHELL_PERCENTILE, chord=True,
                        tuck=_SHELL_TUCK, tuck_span=_SHELL_TUCK_SPAN,
                        # Deliberately not the arms.  Measuring the arm root
                        # here widens the whole chest ring towards it, and the
                        # shell then follows neither: it measured 33 vertices
                        # through on a stoneborn and 189 on a Luminous female,
                        # against 1 and 0 without.  The armhole is the shoulder
                        # cap's job, not the body shell's.
                        bones=TORSO_BONES + ["thigh_l", "thigh_r"])
    neck = torso_rings(rig, COLLAR, COLLAR_TOP, rows=3, sides=sides,
                       thickness=thickness * .72, taper=.70, floor=.046,
                       bones=["neck_01", "spine_03", "clavicle_l", "clavicle_r"])
    return rings + neck


def _collar_band(surface: Surface, rig: Rig, *, material: int = MATERIAL_TRIM,
                 sides: int = 30, low: float = COLLAR - .012,
                 high: float = COLLAR_TOP + .008, taper: float = .72,
                 thickness: float = .014) -> None:
    """The trim collar: a closed band worn over the base shell's neck."""
    band = torso_rings(rig, low, high, rows=3, sides=sides, thickness=thickness,
                       taper=taper, floor=.048,
                       bones=["neck_01", "spine_03", "clavicle_l", "clavicle_r"])
    surface.loft(band, material, cap_start=True, cap_end=True)


@dataclass(frozen=True)
class Style:
    """The dial settings that make one torso design differ from another.

    Every design in the set is the same four shells - body, collar, two shoulder
    caps, two sleeves, and whatever skirt its kind calls for - with these turned.
    Keeping the differences declarative is what makes sixty-four designs
    affordable to check: the fit is a property of the construction, not of any
    one design, so a design cannot quietly reintroduce a hole in the shoulder.
    """

    #: How far the shoulder cap runs down the humerus, and how wide it swells.
    #: A linen shirt wants a seam; a pauldron wants to be seen.
    cap_outboard: float = .46
    #: How far *past* the joint, towards the neck, the cap reaches.  This is
    #: what buries its inboard end inside the body shell; too shallow and the
    #: rear shoulder slips out between the two when the arm swings.
    cap_inboard: float = -.85
    cap_swell: float = 1.38
    #: How far above the shoulder joint the cap is centred.  Lowering this to
    #: sit the cap flatter on the shoulder looks tidier and measurably is not:
    #: over the whole set it takes the meshes that read exactly zero at the
    #: shoulder from 70 of 80 down to 48, and the shoulder is what this
    #: construction exists for.  A sweep that said the difference was nil had
    #: been run through a harness that did not resolve fit variants, so every
    #: reading was dominated by female bodies wearing the male piece.
    cap_lift: float = .026
    #: Sleeve end along the arm chain, 0 at the shoulder and 1 at the wrist.
    #: ``None`` leaves the design sleeveless, which is what makes it a cuirass.
    #: A sleeveless design still gets the short facing below.
    sleeve_end: float | None = None
    sleeve_thickness: float = .015
    #: Where a sleeveless design's armhole rim ends along the arm chain.  See
    #: ``_torso_garment``: this is what actually closes a cuirass's arm opening.
    facing_end: float = .21
    #: Raised front plate (low, high) and how far round the chest it wraps.
    plate: tuple[float, float] | None = None
    plate_span: float = .58
    plate_thickness: float = .040
    #: A yoke across the top of the chest and shoulders.
    yoke: bool = False
    #: A skirt hanging from the waist: (hem Y, flare).
    skirt: tuple[float, float] | None = None
    #: Trim band at the very bottom of a skirt.
    hem_band: bool = False
    #: Lapel or placket down the front.
    lapel: bool = False
    #: A belt that belongs to the *garment* rather than to the trousers, given
    #: as a world Y.  Left out of almost every design - see TORSO_HEM.
    belt: float | None = None
    belt_thickness: float = .016
    #: Overall thickness of the body shell.  Cloth is thin; plate stands off.
    thickness: float = .011
    #: Shoulder cap material, so a leather spaulder can differ from its sleeve.
    cap_trim: bool = False
    #: How much wider than the sleeve its opening runs.  See ``_sleeves``.
    sleeve_cuff: float = .020


def _torso_garment(kind: str, rig: Rig, style: Style) -> Garment:
    """One torso garment, built as overlapping closed shells.

    Every piece here closes on itself and overlaps its neighbours, rather than
    meeting them along a seam.  That is the whole design: a seam between two
    open sheets is a hole waiting for a pose to open it, and the shoulder is
    where the cast disagrees most - stone shoulders are square where a Luminous
    one is round.  Solids that overlap have nothing to come apart.
    """
    surface = Surface()
    waist = SKIRTED_HEM if kind in {"coat", "robe"} else TORSO_HEM

    # 1. The body: hem to the top of the collar, closed at both ends.  The hem
    #    lid sits inside the trousers and the neck lid inside the neck.
    surface.loft(_torso_shell(rig, waist, thickness=style.thickness),
                 MATERIAL_BASE, cap_start=True, cap_end=True)
    _collar_band(surface, rig)

    # 2. The shoulders, before anything else that might want to sit over them.
    cap_material = MATERIAL_TRIM if style.cap_trim else MATERIAL_BASE
    _shoulder_cap(surface, rig, inboard=style.cap_inboard,
                  outboard=style.cap_outboard,
                  swell=style.cap_swell, lift=style.cap_lift,
                  thickness=style.thickness, material=cap_material)

    # 3. Sleeves, rooted inside the caps - or, where a design has none, the
    #    rim around its arm opening.  Both are built by ``limb_rings``, which
    #    measures the body per angle and so follows a shoulder that sweeps
    #    backwards; a swept cap cannot, and that is the whole reason the rim
    #    exists rather than the cap simply being made longer.
    if style.sleeve_end is not None:
        if not sleeve_clear(style.sleeve_end):
            raise ValueError(
                f"sleeve ends at {style.sleeve_end}, inside the apex band "
                f"{SLEEVE_APEX} where an opening does not stay closed")
        _sleeves(surface, rig, end=style.sleeve_end, material=MATERIAL_BASE,
                 thickness=style.sleeve_thickness, cuff=style.sleeve_cuff)
    else:
        _sleeves(surface, rig, end=style.facing_end,
                 material=MATERIAL_TRIM if style.cap_trim else MATERIAL_BASE,
                 thickness=style.sleeve_thickness, start=.06,
                 cuff=style.sleeve_cuff)

    # 4. Whatever the design puts on top.
    if style.plate is not None:
        low, high = style.plate
        plate = torso_rings(rig, low, high, rows=8, sides=30,
                            thickness=style.plate_thickness)
        # An open sheet on purpose: a breastplate is a shell over the chest, not
        # a tube round it.  It encloses nothing, so it is not asked to - the body
        # shell underneath is what covers the skin here.
        surface.loft([_front_arc(ring, style.plate_span) for ring in plate],
                     MATERIAL_TRIM, closed=False)
    if style.yoke:
        yoke = torso_rings(rig, 1.400, COLLAR + .022, rows=4, sides=30,
                           thickness=style.plate_thickness * .75)
        surface.loft(yoke, MATERIAL_TRIM, cap_start=True, cap_end=True)
    if style.lapel:
        lapel = torso_rings(rig, 1.140, COLLAR - .020, rows=5, sides=30,
                            thickness=style.plate_thickness)
        surface.loft(lapel, MATERIAL_TRIM, cap_start=True, cap_end=True)
    if style.skirt is not None:
        hem, flare = style.skirt
        rows = max(6, int(round((waist - hem) * 20)))
        skirt = torso_rings(rig, hem, waist + .020, rows=rows, sides=30,
                            thickness=.034, flare_low=flare,
                            bones=HIP_BONES + ["calf_l", "calf_r"])
        surface.loft(skirt, MATERIAL_BASE, cap_start=True, cap_end=True,
                     v_start=1.0, v_end=0.0)
        if style.hem_band:
            band = torso_rings(rig, hem, hem + .060, rows=2, sides=30,
                               thickness=.038, flare_low=flare)
            surface.loft(band, MATERIAL_TRIM, cap_start=True, cap_end=True)
    if style.belt is not None:
        _belt(surface, rig, style.belt, thickness=style.belt_thickness)
    return Garment(surface, "torso")


def garment_geometry(kind: str, rig: Rig, style: "Style | None" = None,
                     features: tuple[str, ...] = ()) -> Garment:
    """Body-conforming wearables, lofted from the measured rest silhouette."""
    surface = Surface()
    if kind in {"cuirass", "coat", "robe", "shirt"}:
        style = style or Style()
        return _torso_garment(kind, rig, style)

    if kind in {"legs", "pants", "kilt"}:
        # Modified 2026-08-29 for Eloria Client: the sixty-four rebuilt leg
        # garments are recipes rather than one shape, so the geometry moved to
        # `legwear_geometry` and this branch is the seam between them.  The
        # import is deferred because that module lofts through the primitives
        # defined here and importing it at module scope would be circular.
        from legwear_geometry import legwear_geometry
        return legwear_geometry(kind, rig, features or ())

    if kind == "boots":
        for side in ("l", "r"):
            # The shaft runs past the ankle joint rather than stopping on it, so
            # the boot and the foot shell overlap instead of meeting at a seam
            # that opens up the moment the leg it is worn on is not the leg it
            # was measured against.
            # A boot's shaft is the outer layer: the trouser tucks into it, so
            # it is deliberately thicker than the trouser leg at every height
            # they share.  It also stops well short of the knee - reaching up
            # to meet a flared cuff only put the boot through the trouser.
            shaft = limb_rings(rig, [f"calf_{side}"], rows=10, sides=20,
                               thickness=.024, start=.54, end=1.08, floor=.044,
                               bones=[f"calf_{side}", f"foot_{side}"])
            surface.loft(shaft, MATERIAL_BASE, cap_start=True)
            surface.extend(_foot_shell(rig, side))
            cuff = limb_rings(rig, [f"calf_{side}"], rows=3, sides=20,
                              thickness=.032, start=.52, end=.62, floor=.044,
                              bones=[f"calf_{side}"])
            surface.loft(cuff, MATERIAL_TRIM)
        return Garment(surface, "boots")

    if kind == "cape":
        surface.extend(_cape_body(rig))
        return Garment(surface, "cape")

    if kind == "gloves":
        for side in ("l", "r"):
            surface.extend(_glove_shell(rig, side))
        return Garment(surface, "hands")

    raise ValueError(f"unknown garment kind: {kind}")


def _glove_shell(rig: Rig, side: str) -> Surface:
    """A glove over one hand: cuff down the forearm, back plate, thumb roll."""
    surface = Surface()
    fingers, _, palm = grip_frame(rig, side)
    wrist = rig.origin(f"hand_{side}")
    cuff = limb_rings(rig, [f"lowerarm_{side}"], rows=5, sides=16,
                      thickness=.020, start=.62, end=1.06, floor=.032)
    surface.loft(cuff, MATERIAL_TRIM, cap_start=True)
    across = np.cross(fingers, palm)
    across /= np.linalg.norm(across)
    rings = []
    for travel, width, depth in ((-.02, .048, .034), (.34, .054, .036),
                                  (.72, .052, .032), (1.02, .044, .026),
                                  (1.24, .030, .018)):
        centre = wrist + fingers * (travel * .118)
        ring = np.empty((16, 3))
        for index in range(16):
            angle = 2 * math.pi * index / 16
            ring[index] = centre + (across * math.cos(angle) * width
                                    + palm * math.sin(angle) * depth)
        rings.append(ring)
    surface.loft(rings, MATERIAL_BASE, cap_start=True, cap_end=True)
    thumb = rig.origin(f"thumb_01_{side}")
    thumb_tip = rig.origin(f"thumb_03_{side}")
    surface.tube([wrist + (thumb - wrist) * .35, thumb,
                  thumb + (thumb_tip - thumb) * .80],
                 [.030, .026, .018], MATERIAL_BASE, sides=12)
    return surface


# How thick a boot sole is, measured from the plane the bare foot stands on
# upwards. The actor is placed on the ground by its body, not by whatever it is
# wearing, so a sole authored below that plane sinks into the floor.
SOLE_THICKNESS = .019
# How far the sole is allowed to stand proud of that plane, and how far it
# reaches up inside the upper. The slab and the upper have to overlap: meeting
# them exactly leaves a sliver along the welt where neither covers the foot.
SOLE_PROUD = .004
SOLE_OVERLAP = .009
# A foot is a rounded box, not an ellipse. Rings drawn as true ellipses cut the
# corners off the shape they are sized to contain, so the outer edge of the
# instep and the top of the toe box came through a boot that was wide enough
# and tall enough everywhere it was measured. A squircle of this exponent hugs
# a rounded rectangle instead, without widening the silhouette.
SHELL_CORNER = 2.6


def _squircle(phi: float) -> tuple[float, float]:
    """Unit rounded-rectangle offsets for one angle around a shell ring."""
    power = 2. / SHELL_CORNER
    across, along = math.cos(phi), math.sin(phi)
    return (math.copysign(abs(across) ** power, across),
            math.copysign(abs(along) ** power, along))


def _foot_shell(rig: Rig, side: str) -> Surface:
    """A boot foot lofted around the real foot, heel through toe.

    Modified 2026-08-28 for Eloria Client.  Every offset here used to be a
    constant in world axes, and the toe was extrapolated past the ball of the
    foot along the ankle's own direction.  That only ever described a foot laid
    out like the reference rig's.  The Ssarathi stand on a digitigrade leg: the
    ankle is a quarter of a metre off the ground, the metatarsal runs steeply
    down from it and the toes turn horizontal again at the ball, so the old
    shell sat beside the foot and drove its toe box into the floor - which is
    what put their feet out in front of the boot.  The shell is now built along
    the two segments the rig actually has, ankle-to-ball and ball-to-toe, so it
    follows either anatomy once the runtime retargets it.
    """
    surface = Surface()
    ankle = rig.origin(f"foot_{side}")
    ball = rig.origin(f"ball_{side}")
    toe_tip = rig.segment(f"ball_{side}")[1]
    lateral = np.array([1., 0., 0.])

    def frame(start: np.ndarray, end: np.ndarray):
        """Unit axis from start to end, its length, and 'down' square to it."""
        axis = end - start
        length = float(np.linalg.norm(axis))
        axis = axis / max(length, 1e-9)
        down = np.array([0., -1., 0.])
        down = down - axis * float(down @ axis)
        if float(down @ down) < 1e-6:
            down = np.array([0., 0., -1.])
        return axis, length, down / max(np.linalg.norm(down), 1e-9)

    instep, arch, under_arch = frame(ankle, ball)
    forward, toe_span, under_toe = frame(ball, toe_tip)
    # The toe box runs a little past the last joint so claws and long toes stay
    # inside it, and the heel only reaches back far enough to close the shell.
    # Ring centres stay where a plantigrade foot's flesh actually is - hung
    # below the ankle - so the sole keeps sitting under the human foot.  The
    # instep side is then raised by ``lift`` and the ring grown by the same
    # amount, which extends the upper over the bone without moving the sole:
    # a digitigrade metatarsal, whose bone runs through the middle of the foot
    # rather than along the top of it, ends up inside the boot too.
    lift = [.018, .024, .024, .020, .015, .011]
    # How far the heel actually reaches behind the ankle, measured rather than
    # assumed: a plantigrade heel runs back nearly four tenths of the arch and a
    # digitigrade one barely two, and a fixed fraction leaves one of them either
    # sticking out through the back of the boot or trailing a spur behind it.
    heel_reach = arch * .38
    # Measured off the body itself rather than off the skin weights: the heel
    # is largely bound to the calf, so a bone-scoped region misses exactly the
    # part of the foot the back of the boot has to contain.
    span = toe_tip - ankle
    length = float(np.linalg.norm(span)) or 1.0
    axis = span / length
    offsets = rig.positions - ankle
    along = np.clip(offsets @ axis, 0.0, length)
    aside = np.linalg.norm(offsets - np.outer(along, axis), axis=1)
    same_side = np.sign(rig.positions[:, 0]) == np.sign(ankle[0] or 1.0)
    foot_flesh = same_side & (aside < .085)
    rear = rig.positions[foot_flesh & (along < length * .45)]
    if len(rear) > 16:
        behind = -((rear - ankle) @ instep)
        heel_reach = float(np.clip(np.quantile(behind, .995),
                                   arch * .16, arch * .60))
    # And the same for the front: toe length varies far more between races than
    # any multiple of the last joint's span predicts, and a toe box guessed from
    # one leaves the others' toes out in front of the boot.
    toe_reach = toe_span * 1.18
    front = rig.positions[foot_flesh & (along > length * .5)]
    if len(front) > 16:
        ahead = (front - ball) @ forward
        toe_reach = float(np.clip(np.quantile(ahead, .995) + .022,
                                  toe_span * .8, toe_span * 2.4))
    heel = ankle - instep * (heel_reach + .026) + under_arch * .030
    spine = [heel,
             ankle + under_arch * .038 - instep * (heel_reach * .42),
             ankle + instep * (arch * .46) + under_arch * .044,
             ball + under_arch * .026,
             ball + forward * (toe_reach * .46) + under_toe * .018,
             ball + forward * toe_reach + under_toe * .010]
    downs = [under_arch, under_arch, under_arch, under_arch, under_toe, under_toe]
    # Floors, not the answer.  A boot has a minimum heft whatever it is worn on,
    # but the foot inside decides how big it has to be, and the two directions
    # are not the same: the spine these rings hang off runs under the foot, so a
    # ring centred on it and sized symmetrically covers the sole twice over and
    # stops short on the instep.  That gap along the top of the foot is what
    # showed skin through a boot that looked closed from every other angle.
    # Up and down are therefore measured separately and the ring is recentred
    # on the flesh it has to contain.
    widths = [.050, .058, .060, .056, .050, .038]
    heights = [.046, .054, .050, .044, .034, .028]
    flesh = rig.positions[foot_flesh]
    if len(flesh) > 24:
        seats, sized = [], []
        for point, down, floor_w, floor_h in zip(spine, downs, widths, heights):
            seat = float((point - ankle) @ axis)
            near = flesh[np.abs((flesh - ankle) @ axis - seat) < .030]
            if len(near) < 8:
                # Past the last toe there is no flesh to measure.  Carry the
                # previous ring forward, tapered, rather than dropping to a
                # floor value: a tip built to a small constant left the
                # undersides of the toes below the sole that was meant to cap
                # them.
                if sized:
                    last_w, last_h = sized[-1]
                    seats.append(point + down * (seats[-1] - spine[len(sized) - 1])
                                 @ down)
                    sized.append((max(floor_w, last_w * .82),
                                  max(floor_h, last_h * .82)))
                else:
                    seats.append(point)
                    sized.append((floor_w, floor_h))
                continue
            # The extremes, not the 99th percentile. The last one per cent of
            # a foot is the joint at the base of the little toe and the point
            # of the heel - the two places a shell sized to the rest of it
            # leaves skin showing - and they are real geometry, not noise: the
            # flesh sampled here is already scoped to this foot.
            offset = near - point
            side = float(np.abs(offset @ lateral).max()) + .013
            reach = offset @ down
            below = float(reach.max()) + .011
            above = -float(reach.min()) + .011
            # Recentre between the two, then take the larger half-height.
            seats.append(point + down * (below - above) * .5)
            sized.append((max(floor_w, side),
                          max(floor_h, (below + above) * .5)))
        spine = seats
        widths = [value for value, _ in sized]
        heights = [value for _, value in sized]
    else:
        spine = [point - down * rise for point, down, rise in zip(spine, downs, lift)]
        heights = [height + rise for height, rise in zip(heights, lift)]
    # Where the wearer's own foot meets the floor. A boot may stand a few
    # millimetres proud of it and no more: the actor is placed on the ground by
    # its body, not by what it is wearing, so anything below that is boot under
    # the floor - three centimetres of it, in the shell this replaces.
    ground = float(flesh[:, 1].min()) if len(flesh) else float(
        min(point[1] - abs(down[1]) * height
            for point, down, height in zip(spine, downs, heights)))
    floor_plane = ground - SOLE_PROUD
    # Each ring is then seated on the flesh directly beneath it rather than on
    # one plane. A ring that stops above the foot leaves a slot for it to show
    # through - the toe rings, built past the last joint where there is no
    # flesh left to measure, were the ones stopping short - and a ring that
    # runs below the floor is the drooping heel. Reading the flesh station by
    # station rather than assuming a single sole height is also what keeps this
    # honest on a digitigrade leg, where only the toes are on the ground and
    # the hock is a quarter of a metre above it. Moving the underside without
    # moving the top is a matched change of centre and half-height, so the
    # instep stays where the measurement put it either way.
    seated = []
    for point, down, width, height in zip(spine, downs, widths, heights):
        drop = abs(float(down[1]))
        if drop > 1e-6:
            seat = float((point - ankle) @ axis)
            under = (flesh[np.abs((flesh - ankle) @ axis - seat) < .045]
                     if len(flesh) else flesh)
            target = float(under[:, 1].min()) - .006 if len(under) else ground
            target = max(target, floor_plane)
            shift = (float(point[1]) - drop * height - target) / (2. * drop)
            point = point + np.array([0., -shift * drop, 0.])
            height = height + shift
        seated.append((point, down, width, max(height, .004)))
    rings = []
    for point, down, width, height in seated:
        ring = np.empty((18, 3))
        for index in range(18):
            # Traversed so that the loft's winding faces outwards.  Sweeping the
            # other way builds the same ellipse inside out, and the renderer
            # culls the near wall - which is what made a closed boot look like
            # an open-toed sandal with the foot showing through it.
            phi = 2 * math.pi * index / 18
            across, along = _squircle(phi)
            ring[index] = (point + lateral * across * width
                           + down * along * height)
        rings.append(ring)
    surface.loft(rings, MATERIAL_BASE, cap_start=True, cap_end=True)
    # The sole hangs off each ring's own underside, in world axes. Sweeping it
    # along ``down`` instead is what broke it into pieces: that axis is square
    # to whichever segment its ring belongs to, so the arch rings and the toe
    # rings pointed different ways and the slab jumped between them - parts of
    # it floating above the toes, the back of it three centimetres under the
    # foot, which is what made the heel look lower than the foot it was on.
    sole = []
    for point, down, width, height in seated:
        base = float(point[1]) - abs(float(down[1])) * height
        floor = max(base - SOLE_THICKNESS, floor_plane)
        ceiling = base + SOLE_OVERLAP
        middle = (floor + ceiling) * .5
        reach = max((ceiling - floor) * .5, .003)
        ring = np.empty((18, 3))
        for index in range(18):
            phi = 2 * math.pi * index / 18
            across, along = _squircle(phi)
            ring[index] = np.array([
                float(point[0]) + across * (width + .010),
                middle + along * reach,
                float(point[2])])
        sole.append(ring)
    surface.loft(sole, MATERIAL_DETAIL, cap_start=True, cap_end=True)
    return surface


def _cape_body(rig: Rig) -> Surface:
    """A cape that hangs behind the actor from a collar across the shoulders."""
    surface = Surface()
    shoulder = rig.origin("spine_03")[1] + .16
    hem = .30
    columns, rows = 22, 18
    grid = []
    for row in range(rows + 1):
        travel = row / rows
        height = shoulder - (shoulder - hem) * travel
        half_width = .16 + .19 * travel ** .8
        # The cape wraps the shoulders at the top and falls free below.
        wrap = max(0., 1. - travel * 3.4)
        line = []
        for column in range(columns + 1):
            across = column / columns * 2. - 1.
            depth = -.10 - .075 * (1. - abs(across) ** 2.) * (1. - wrap)
            depth += wrap * (.055 * (1. - abs(across) ** 1.6))
            sway = math.sin(travel * math.pi * 1.1) * .022 * math.sin(across * math.pi * 2.)
            line.append(np.array([across * half_width,
                                  height + sway - abs(across) ** 2.2 * .05,
                                  depth - travel * .03]))
        grid.append(np.array(line))
    thickness = .010
    front, back = [], []
    for line in grid:
        front.append(line + np.array([0., 0., thickness]))
        back.append(line)
    surface.loft(front, MATERIAL_BASE, closed=False)
    surface.loft([row[::-1] for row in back], MATERIAL_BASE, closed=False)
    # Close the outline so the cape is a solid, not a one-sided sheet.
    for pair in ((0, 0), (columns, columns)):
        edge = [np.array([grid[row][pair[0]], grid[row][pair[0]]
                          + np.array([0., 0., thickness])]) for row in range(rows + 1)]
        surface.loft(edge, MATERIAL_BASE, closed=False)
    top = [np.array([grid[0][column], grid[0][column] + np.array([0., 0., thickness])])
           for column in range(columns + 1)]
    surface.loft(top, MATERIAL_TRIM, closed=False)
    bottom = [np.array([grid[rows][column] + np.array([0., 0., thickness]),
                        grid[rows][column]]) for column in range(columns + 1)]
    surface.loft(bottom, MATERIAL_TRIM, closed=False)
    collar = torso_rings(rig, rig.origin("spine_03")[1] + .10,
                         rig.origin("spine_03")[1] + .17, rows=3, sides=26,
                         thickness=.034)
    surface.loft(collar, MATERIAL_TRIM)
    return surface


def _front_arc(ring: np.ndarray, span: float = .58) -> np.ndarray:
    """The forward-facing run of a torso ring, used for breastplates and lapels."""
    sides = len(ring)
    keep = [index for index in range(sides)
            if math.sin(2 * math.pi * index / sides) >= math.cos(math.pi * span)]
    if len(keep) < 3:
        return ring
    return ring[keep]


# ---------------------------------------------------------------------------
# Pose-referenced grips
# ---------------------------------------------------------------------------

# Players see the idle pose far more than the authoring T-pose, so weapon grips
# are solved there and converted back into a rest-space socket.  A hilt keeps
# the anatomical fist angle, while a haft or a bow riser is asked to stand
# upright the way a person actually carries one.
GRIP_REFERENCE_CLIP = "Idle_A"

GRIP_UPRIGHT = {"staff", "spear", "harpoon", "bow", "crossbow", "glaive"}


def _sample_clip_rotations(document: dict, binary: bytes, clip: str,
                           time: float = 0.0) -> dict[str, dict]:
    animation = next((a for a in document.get("animations", [])
                      if a.get("name") == clip), None)
    if animation is None:
        return {}
    sampled: dict[str, dict] = {}
    for channel in animation["channels"]:
        path = channel["target"].get("path")
        node = channel["target"].get("node")
        if path == "weights" or node is None:
            continue
        sampler = animation["samplers"][channel["sampler"]]
        times = accessor_array(document, binary, sampler["input"]).astype(np.float64).ravel()
        values = accessor_array(document, binary, sampler["output"]).astype(np.float64)
        index = int(np.clip(np.searchsorted(times, time), 0, len(times) - 1))
        name = document["nodes"][node].get("name", "")
        sampled.setdefault(name, {})[path] = values[index]
    return sampled


@lru_cache(maxsize=8)
def _idle_hand_bases(race_path: str, library_path: str,
                     clip: str = GRIP_REFERENCE_CLIP) -> dict[str, np.ndarray]:
    """Character-space basis of each hand during one clip's pose.

    The clip is an argument rather than the module constant so that it takes
    part in the cache key.  It used to be read from the global, which meant a
    caller that set the global and called again got the first clip's answer
    back -- and since a socket solved against a pose is then verified against
    that same pose, the two cancel and the check passes no matter how wrong the
    clip was.  A weapon solved against Idle_A sits 43 degrees across the body in
    Idle_Subtle, which is the clip the client actually idles in.
    """
    document, binary = read_gltf(Path(race_path))
    library, library_binary = read_gltf(Path(library_path))
    pose = _sample_clip_rotations(library, library_binary, clip)
    nodes = document["nodes"]
    locals_: dict[int, np.ndarray] = {}
    for index, node in enumerate(nodes):
        base = _node_matrix(node)
        channel = pose.get(node.get("name", ""))
        if channel is not None:
            matrix = np.eye(4)
            if "scale" in channel:
                matrix = matrix @ np.diag([*channel["scale"], 1.0])
            if "rotation" in channel:
                x, y, z, w = channel["rotation"]
                rotation = np.array([
                    [1 - 2 * (y * y + z * z), 2 * (x * y - z * w), 2 * (x * z + y * w)],
                    [2 * (x * y + z * w), 1 - 2 * (x * x + z * z), 2 * (y * z - x * w)],
                    [2 * (x * z - y * w), 2 * (y * z + x * w), 1 - 2 * (x * x + y * y)]])
                homogeneous = np.eye(4)
                homogeneous[:3, :3] = rotation
                matrix = homogeneous @ matrix
            translation = channel.get("translation", base[:3, 3])
            homogeneous = np.eye(4)
            homogeneous[:3, 3] = translation
            matrix = homogeneous @ matrix
            base = matrix
        locals_[index] = base
    parent: dict[int, int] = {}
    for index, node in enumerate(nodes):
        for child in node.get("children", []):
            parent[child] = index
    cache: dict[int, np.ndarray] = {}

    def resolve(index: int) -> np.ndarray:
        if index in cache:
            return cache[index]
        matrix = locals_[index]
        if index in parent:
            matrix = resolve(parent[index]) @ matrix
        cache[index] = matrix
        return matrix

    by_name = {node.get("name", ""): index for index, node in enumerate(nodes)}
    return {side: resolve(by_name[f"hand_{side}"])[:3, :3].copy() for side in ("l", "r")}


def upright_grip_basis(rig: Rig, side: str, idle_basis: np.ndarray,
                       *, forward_lean: float = 0.0) -> np.ndarray:
    """Rest-space socket basis that stands a haft upright in the idle pose."""
    rest_basis = rig.basis(f"hand_{side}")
    up = np.array([0., math.cos(math.radians(forward_lean)),
                   math.sin(math.radians(forward_lean))])
    across = np.array([1., 0., 0.])
    flat = np.cross(across, up)
    flat /= np.linalg.norm(flat)
    across = np.cross(up, flat)
    desired = np.column_stack((across, up, flat))
    bone_local = np.linalg.inv(idle_basis) @ desired
    return rest_basis @ bone_local


# ---------------------------------------------------------------------------
# Material detail
# ---------------------------------------------------------------------------

@lru_cache(maxsize=32)
def detail_maps(family: str, size: int = 128) -> tuple[bytes, bytes]:
    """Neutral base-colour detail and a matching normal map for one surface family.

    Kept grey so the runtime can tint a piece per culture, and generated from a
    height field so the normal map always agrees with the colour variation.
    """
    yy, xx = np.mgrid[0:size, 0:size].astype(np.float64)
    u, v = xx / size, yy / size
    if family == "metal":
        height = (np.sin(u * math.pi * 48.) * .10 + np.sin(v * math.pi * 7.) * .22
                  + np.sin((u + v) * math.pi * 23.) * .07)
        height += (np.sin(u * math.pi * 4.) * np.sin(v * math.pi * 4.)) * .18
    elif family == "cloth":
        height = (np.sign(np.sin(u * math.pi * 64.)) * .12
                  + np.sign(np.sin(v * math.pi * 64.)) * .12
                  + np.sin((u * 3. + v * 5.) * math.pi) * .10)
    elif family == "leather":
        height = (np.sin(u * 41. + np.sin(v * 17.) * 2.3) * .16
                  + np.sin(v * 53. + np.sin(u * 11.) * 1.9) * .14)
        height += (((xx * 17 + yy * 29) % 113) < 4) * -.30
    elif family == "wood":
        rings = np.sin((v * 26. + np.sin(u * 5.) * 1.4) * math.pi)
        height = rings * .22 + np.sin(v * math.pi * 110.) * .06
    elif family == "crystal":
        facet = np.floor(u * 9.) + np.floor(v * 11.) * .5
        height = np.sin(facet * 2.4) * .30 + np.sin((u - v) * math.pi * 18.) * .10
    elif family == "scale":
        row = np.floor(v * 22.)
        stagger = u * 22. + (row % 2) * .5
        cell = np.abs((stagger % 1.) - .5) * 2.
        height = (1. - cell ** 1.6) * .34 - .17
    else:  # fur and other soft trims
        height = (np.sin(u * math.pi * 75. + np.sin(v * 30.) * 3.) * .16
                  + np.sin(v * math.pi * 45.) * .12)
    height = np.clip(height, -1., 1.)
    alpha = None
    shade = np.clip(.80 + height * .17, 0., 1.)
    channel = (shade * 255.).astype(np.uint8)
    colour = io.BytesIO()
    # Greyscale: the detail only modulates the material's base colour factor, so
    # a single channel carries it at a third of the bytes.
    Image.fromarray(channel, "L").save(colour, format="PNG", optimize=True)
    # The normal map is derived from a relaxed copy of the same height field.
    # Blurring first keeps the two maps in agreement while letting the encoded
    # PNG stay small enough to ship sixty-six pieces of equipment.
    relaxed = height
    for _ in range(3):
        relaxed = (relaxed
                   + np.roll(relaxed, 1, 0) + np.roll(relaxed, -1, 0)
                   + np.roll(relaxed, 1, 1) + np.roll(relaxed, -1, 1)) / 5.
    half = max(size // 2, 8)
    relaxed = np.asarray(Image.fromarray(
        ((relaxed * .5 + .5) * 255.).astype(np.uint8)).resize(
            (half, half), Image.Resampling.BILINEAR), dtype=np.float64) / 255. * 2. - 1.
    strength = 3.0
    dx = np.gradient(relaxed, axis=1) * half / 24. * strength
    dy = np.gradient(relaxed, axis=0) * half / 24. * strength
    normal = np.dstack((-dx, -dy, np.ones_like(relaxed)))
    normal /= np.maximum(np.linalg.norm(normal, axis=2, keepdims=True), 1e-9)
    encoded = np.round(((normal * .5 + .5) * 255.) / 4.).astype(np.uint8) * 4
    normal_png = io.BytesIO()
    Image.fromarray(encoded, "RGB").save(normal_png, format="PNG", optimize=True)
    return colour.getvalue(), normal_png.getvalue()


# ---------------------------------------------------------------------------
# GLB emission
# ---------------------------------------------------------------------------

def srgb_to_linear(colour) -> list[float]:
    """Convert an authored sRGB byte triple into the linear factor glTF wants."""
    converted = []
    for channel in colour:
        value = channel / 255.
        converted.append(value / 12.92 if value <= .04045
                         else ((value + .055) / 1.055) ** 2.4)
    return converted


def _align4(value: int) -> int:
    return (value + 3) & ~3


class EquipmentGLB:
    """Minimal glTF 2.0 writer for one equipment piece."""

    def __init__(self, generator: str = "Eloria equipment authoring") -> None:
        self.binary = bytearray()
        self.doc: dict = {"asset": {"version": "2.0", "generator": generator},
                          "scene": 0, "scenes": [{"nodes": []}], "nodes": [],
                          "meshes": [], "materials": [], "bufferViews": [],
                          "accessors": [], "buffers": [{"byteLength": 0}]}

    def view(self, raw: bytes, target: int | None = None) -> int:
        while len(self.binary) & 3:
            self.binary.append(0)
        offset = len(self.binary)
        self.binary.extend(raw)
        spec = {"buffer": 0, "byteOffset": offset, "byteLength": len(raw)}
        if target is not None:
            spec["target"] = target
        self.doc["bufferViews"].append(spec)
        return len(self.doc["bufferViews"]) - 1

    def accessor(self, values: np.ndarray, kind: str, *, target: int | None = None,
                 bounds: bool = False, normalized: bool = False) -> int:
        values = np.ascontiguousarray(values)
        component = {np.dtype("uint8"): 5121, np.dtype("uint16"): 5123,
                     np.dtype("uint32"): 5125, np.dtype("float32"): 5126}[values.dtype]
        spec = {"bufferView": self.view(values.tobytes(), target),
                "componentType": component, "count": int(values.shape[0]), "type": kind}
        if normalized:
            spec["normalized"] = True
        if bounds:
            matrix = values.reshape(len(values), -1)
            spec["min"] = [float(v) for v in matrix.min(axis=0)]
            spec["max"] = [float(v) for v in matrix.max(axis=0)]
        self.doc["accessors"].append(spec)
        return len(self.doc["accessors"]) - 1

    def texture(self, png: bytes) -> int:
        cached = getattr(self, "_texture_cache", None)
        if cached is None:
            cached = self._texture_cache = {}
        key = hash(png)
        if key in cached:
            return cached[key]
        self.doc.setdefault("images", []).append(
            {"bufferView": self.view(png), "mimeType": "image/png"})
        self.doc.setdefault("samplers", []).append(
            {"magFilter": 9729, "minFilter": 9987, "wrapS": 10497, "wrapT": 10497})
        self.doc.setdefault("textures", []).append(
            {"source": len(self.doc["images"]) - 1,
             "sampler": len(self.doc["samplers"]) - 1})
        cached[key] = len(self.doc["textures"]) - 1
        return cached[key]

    def material(self, name: str, colour, *, metallic: float, roughness: float,
                 family: str, emissive=None, double_sided: bool = False) -> int:
        base, normal = detail_maps(family)
        # Palettes are picked as sRGB but glTF defines these factors as linear,
        # so they are converted on the way in. Writing the bytes raw would land
        # roughly forty percent bright and turn iron plate into near-white.
        pbr = {"baseColorFactor": srgb_to_linear(colour) + [1.],
               "metallicFactor": metallic, "roughnessFactor": roughness,
               "baseColorTexture": {"index": self.texture(base)}}
        spec = {"name": name, "pbrMetallicRoughness": pbr,
                "normalTexture": {"index": self.texture(normal)},
                "doubleSided": double_sided}
        if emissive is not None:
            spec["emissiveFactor"] = srgb_to_linear(emissive)
        self.doc["materials"].append(spec)
        return len(self.doc["materials"]) - 1

    def primitive(self, positions, normals, uvs, indices, material, *,
                  joints=None, weights=None, weight_floats=False) -> dict:
        attributes = {
            "POSITION": self.accessor(positions.astype("float32"), "VEC3",
                                      target=34962, bounds=True),
            "NORMAL": self.accessor(normals.astype("float32"), "VEC3", target=34962),
            "TEXCOORD_0": self.accessor(uvs.astype("float32"), "VEC2", target=34962)}
        if joints is not None and weight_floats:
            # For geometry that must deform bit-identically with another mesh
            # -- a torso underlayer carrying the body's own blend -- byte
            # quantisation is a real error: half a step of 1/255 opens a
            # millimetre at a bent elbow, and a needle of whatever the layer
            # was hiding comes through it.
            attributes["JOINTS_0"] = self.accessor(joints.astype("uint8"), "VEC4",
                                                   target=34962)
            attributes["WEIGHTS_0"] = self.accessor(
                np.asarray(weights, dtype=np.float64).astype("float32"), "VEC4",
                target=34962)
        elif joints is not None:
            # The shared rig has 77 joints, so byte indices and normalized byte
            # weights fit here and save a third of the vertex payload.
            quantised = np.round(np.asarray(weights, dtype=np.float64) * 255.)
            quantised[np.arange(len(quantised)), quantised.argmax(axis=1)] += (
                255. - quantised.sum(axis=1))
            attributes["JOINTS_0"] = self.accessor(joints.astype("uint8"), "VEC4",
                                                   target=34962)
            attributes["WEIGHTS_0"] = self.accessor(
                np.clip(quantised, 0, 255).astype("uint8"), "VEC4", target=34962,
                normalized=True)
        return {"attributes": attributes, "mode": 4, "material": material,
                "indices": self.accessor(indices.astype("uint32").reshape(-1), "SCALAR",
                                         target=34963)}

    def skeleton(self, rig: Rig) -> int:
        """Emit the shared joint hierarchy so the piece is a valid skinned glTF."""
        index_of: dict[str, int] = {}
        for name in rig.joint_names:
            self.doc["nodes"].append({"name": name})
            index_of[name] = len(self.doc["nodes"]) - 1
        for name in rig.joint_names:
            parent = rig.parent.get(name)
            local = rig.rest[name]
            if parent is not None:
                local = np.linalg.inv(rig.rest[parent]) @ local
                self.doc["nodes"][index_of[parent]].setdefault(
                    "children", []).append(index_of[name])
            self.doc["nodes"][index_of[name]]["matrix"] = [
                float(v) for v in np.asarray(local, dtype=np.float32).T.reshape(-1)]
        root = index_of[rig.joint_names[0]]
        inverse = np.array([np.linalg.inv(rig.rest[name]).T
                            for name in rig.joint_names], dtype="float32")
        self.doc["skins"] = [{"name": "EloriaActorRig",
                              "joints": [index_of[name] for name in rig.joint_names],
                              "skeleton": root,
                              "inverseBindMatrices": self.accessor(
                                  inverse.reshape(len(rig.joint_names), 16), "MAT4")}]
        self.doc["scenes"][0]["nodes"].append(root)
        return root

    def mesh(self, name: str, primitives: list[dict], *, skin: int | None = None) -> int:
        self.doc["meshes"].append({"name": name, "primitives": primitives})
        node = {"name": name, "mesh": len(self.doc["meshes"]) - 1}
        if skin is not None:
            node["skin"] = skin
        self.doc["nodes"].append(node)
        index = len(self.doc["nodes"]) - 1
        self.doc["scenes"][0]["nodes"].append(index)
        return index

    def write(self, path: Path) -> None:
        self.doc["buffers"][0]["byteLength"] = len(self.binary)
        encoded = json.dumps(self.doc, separators=(",", ":"), ensure_ascii=False).encode()
        encoded += b" " * (_align4(len(encoded)) - len(encoded))
        binary = bytes(self.binary) + b"\0" * (_align4(len(self.binary)) - len(self.binary))
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b"glTF" + struct.pack("<II", 2, 12 + 8 + len(encoded) + 8 + len(binary))
                         + struct.pack("<II", len(encoded), 0x4E4F534A) + encoded
                         + struct.pack("<II", len(binary), 0x004E4942) + binary)


# ---------------------------------------------------------------------------
# Finishes and the equipment build
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class Finish:
    families: tuple[str, str, str]
    metallic: tuple[float, float, float]
    roughness: tuple[float, float, float]
    emissive: float = 0.0
    double_sided: bool = False


FINISHES = {
    "plate": Finish(("metal", "metal", "leather"), (.78, .86, .05), (.34, .22, .62)),
    "mail": Finish(("scale", "metal", "leather"), (.62, .84, .05), (.44, .26, .62)),
    "leather": Finish(("leather", "metal", "leather"), (.04, .58, .04), (.70, .36, .74)),
    "cloth": Finish(("cloth", "cloth", "leather"), (.0, .06, .05), (.88, .64, .70),
                    double_sided=True),
    "fur": Finish(("fur", "leather", "cloth"), (.0, .06, .0), (.92, .62, .86),
                  double_sided=True),
    "crystal": Finish(("crystal", "crystal", "metal"), (.26, .34, .70), (.18, .12, .30),
                      emissive=.16),
    "wood": Finish(("wood", "metal", "leather"), (.0, .68, .04), (.74, .32, .68)),
    "shell": Finish(("scale", "metal", "leather"), (.10, .62, .05), (.40, .30, .68)),
    "spore": Finish(("scale", "fur", "cloth"), (.0, .0, .0), (.76, .90, .82),
                    double_sided=True),
    # Enchanted metal: the same plate, lit along its trim so an elemental blade
    # reads as enchanted at a glance rather than only in its tooltip.
    "fire": Finish(("metal", "metal", "leather"), (.74, .82, .05), (.36, .24, .62),
                   emissive=.62),
    "cold": Finish(("crystal", "metal", "leather"), (.60, .80, .05), (.22, .20, .62),
                   emissive=.52),
    "magic": Finish(("crystal", "crystal", "leather"), (.52, .70, .05), (.20, .16, .62),
                    emissive=.58),
    "thermal": Finish(("metal", "crystal", "leather"), (.78, .74, .05), (.30, .18, .62),
                      emissive=.66),
}

# Which finish each authored piece wears.  Kept beside the geometry rather than
# in the actor builder so a new piece only needs one line here.
#: Per-design torso construction, keyed by slug.  Populated from
#: ``torso_designs`` at import time below; empty for everything that predates it,
#: which keeps its previous default construction.
GARMENT_STYLES: dict[str, "Style"] = {}


def style_for(slug: str) -> "Style | None":
    """The construction one piece was designed with, variant suffix and all."""
    return GARMENT_STYLES.get(slug.split("__")[0])


EQUIPMENT_FINISH = {
    "amberwood_longbow": "wood", "ranger_leafblade": "plate",
    "glasswarden_staff": "crystal", "glasswarden_pick": "crystal",
    "greyhaven_cutlass": "plate", "greyhaven_harpoon": "plate",
    "orun_sun_spear": "plate", "ssarathi_glaive": "plate",
    "luminous_mace": "plate", "votary_ice_sword": "crystal",
    "stoneborn_hammer": "plate", "mycelari_staff": "spore",
    "four_gates_guard_spear_native": "plate", "maritime_crossbow": "wood",
    "amberwood_roundshield": "wood", "glasswarden_shield": "crystal",
    "greyhaven_anchor_shield": "plate", "orun_sun_shield": "plate",
    "ssarathi_shell_shield": "shell", "four_gates_guard_shield_native": "plate",
    "amberwood_leaf_cape": "cloth", "glasswarden_crystal_cape": "cloth",
    "greyhaven_storm_cape": "cloth", "orun_rider_cape": "cloth",
    "ssarathi_frond_cape": "cloth", "four_gates_guard_cape_native": "cloth",
    "amberwood_ranger_hood": "leather", "glasswarden_helm": "crystal",
    "greyhaven_helm": "plate", "orun_sunmane_helm": "plate",
    "ssarathi_crest_helm": "shell", "luminous_circlet": "plate",
    "votary_fur_hood": "fur", "stoneborn_crown": "crystal",
    "mycelari_cap": "spore",
    "amberwood_ranger_legs": "leather", "glasswarden_greaves": "crystal",
    "greyhaven_trousers": "cloth", "orun_rider_legs": "leather",
    "ssarathi_scale_legs": "mail", "votary_winter_legs": "fur",
    "luminous_casual_pants": "cloth",
    "amberwood_ranger_cuirass": "leather", "glasswarden_cuirass": "crystal",
    "greyhaven_coat": "cloth", "orun_sun_cuirass": "plate",
    "ssarathi_scale_cuirass": "mail", "luminous_turquoise_robe": "cloth",
    "votary_fur_mantle": "fur", "stoneborn_plate": "plate",
    "mycelari_mantle": "spore", "four_gates_guard_cuirass": "plate",
    "luminous_short_sleeve_shirt": "cloth",
    "amberwood_ranger_boots": "leather", "glasswarden_boots": "crystal",
    "greyhaven_boots": "leather", "orun_rider_boots": "leather",
    "ssarathi_scale_boots": "mail", "votary_winter_boots": "fur",
    "luminous_casual_boots": "leather",
    "amberwood_amulet": "wood", "glasswarden_resonator": "crystal",
    "greyhaven_compass": "plate", "orun_sun_amulet": "plate",
    "ssarathi_shell_amulet": "shell", "luminous_orbit_amulet": "plate",
}

GARMENT_KINDS = {"cuirass", "coat", "robe", "shirt", "legs", "pants", "kilt",
                 "boots", "cape", "gloves"}


def build_equipment_piece(path: Path, rig: Rig, slug: str, label: str, kind: str,
                          base: tuple[int, int, int], accent: tuple[int, int, int],
                          *, finish: str | None = None,
                          style: "Style | None" = None,
                          features: tuple[str, ...] = (),
                          surface: "Surface | None" = None) -> dict:
    """Author and write one equipment GLB, skinning it when it is a garment.

    ``surface`` lets a caller supply geometry it built itself rather than take
    the shell ``garment_geometry`` would loft.  The footwear catalogue does
    that: sixty-four designs are not one lofted tube under different colours.
    """
    finish_name = finish or EQUIPMENT_FINISH.get(slug, "leather")
    profile = FINISHES[finish_name]
    skinned = kind in GARMENT_KINDS
    if skinned:
        region = garment_region(kind)
        if surface is None:
            # A fit variant is built through the same call under a suffixed
            # slug, so the lookup has to see past the suffix or a variant would
            # be built with the default construction while its reference piece
            # used the design's.
            garment = garment_geometry(kind, rig, style or style_for(slug),
                                       features or ())
            surface, region = garment.surface, garment.skin_region
    else:
        surface, region = (surface or prop_geometry(kind)), ""
    glb = EquipmentGLB()
    detail = tuple(round(c * .46 + 18) for c in base)
    palette = (base, accent, detail)
    names = ("Base", "Trim", "Detail")
    materials = []
    for slot in range(3):
        emissive = None
        if profile.emissive and slot == 1:
            emissive = tuple(round(c * profile.emissive) for c in accent)
        materials.append(glb.material(
            f"{label} {names[slot]}", palette[slot],
            metallic=profile.metallic[slot], roughness=profile.roughness[slot],
            family=profile.families[slot], emissive=emissive,
            double_sided=profile.double_sided))
    skin = glb.skeleton(rig) if skinned else None
    primitives = []
    vertices = triangles = 0
    for slot, (positions, normals, uvs, indices) in enumerate(surface.arrays()):
        if not len(indices):
            continue
        joints = weights = None
        if skinned:
            bound = (cape_weights(rig, positions.astype(np.float64))
                     if region == "cape" else None)
            joints, weights = bound if bound is not None else _scoped_weights(
                rig, surface, slot, positions.astype(np.float64), region)
            joints, weights = apply_pins(rig, surface.pins[slot], joints, weights)
        primitives.append(glb.primitive(positions, normals, uvs, indices,
                                        materials[slot], joints=joints,
                                        weights=weights))
        vertices += len(positions)
        triangles += len(indices) // 3
    glb.mesh(label, primitives, skin=0 if skinned else None)
    glb.write(path)
    return {"id": slug, "name": label, "kind": kind, "finish": finish_name,
            "attach": "skinned" if skinned else "socket", "skinRegion": region,
            "vertices": vertices, "triangles": triangles,
            "joints": len(rig.joint_names) if skinned else 0,
            "bytes": path.stat().st_size}


# ---------------------------------------------------------------------------
# Runtime registry
# ---------------------------------------------------------------------------

# ``hides`` names the actor's own skinned wardrobe surfaces a piece covers.  The
# garments are lofted with clearance, but a body whose wardrobe is bulkier than
# the reference would otherwise poke through the armour worn over it.
PARTS = {
    0: {"name": "weapon", "attachment": "right_hand", "fallback": "weapon"},
    1: {"name": "shield", "attachment": "left_hand", "fallback": "shield"},
    2: {"name": "cape", "attachment": "back", "fallback": "body"},
    3: {"name": "helmet", "attachment": "head", "fallback": "head",
        "hides": ["wardrobe_head_band", "wardrobe_head_cap"]},
    4: {"name": "legs", "attachment": "pelvis", "fallback": "body",
        "hides": ["wardrobe_pants", "wardrobe_pants_seam"]},
    5: {"name": "body", "attachment": "body", "fallback": "body",
        "hides": ["wardrobe_shirt", "wardrobe_shirt_trim"]},
    # Boots follow both feet.  The previous registry pointed them at the pelvis,
    # which parked a pair of boots around the actor's hips.
    6: {"name": "boots", "attachment": "feet", "fallback": "feet",
        "hides": ["wardrobe_boots", "wardrobe_boots_seam"]},
    7: {"name": "neck", "attachment": "neck", "fallback": "head"},
}

# Enclosing headwear also covers the hairstyle; open headwear leaves it alone.
ENCLOSING_HEADWEAR = {"helm", "crest", "hood", "mushroom"}

# No aliases. The three that existed - weapon 11, shield 5, cape 11 - redirected
# legacy ids to Four Gates guard gear because the legacy tier had no geometry.
# Those ids are now STAFF_4, SHIELD_BRONZE and CAPE_GOLD and render as
# themselves; bespoke NPC gear comes from npcLooks, which names native ids.
ALIASES: dict[str, str] = {}


#: Bone sets a vertex may be scoped to, beyond its region's default.  A boot's
#: sole is the case this exists for: the body binds its own heel 31 per cent to
#: the calf, and the runtime scales every bone about its own origin - the calf's
#: being the knee - so a sole that inherited that weighting was dragged 62 mm
#: under the floor on the broadest races.  Scoping the sole to the foot chain
#: leaves it anchored on the joint that actually tracks the ground.
SKIN_SCOPES = {
    "boot_foot": ["foot_l", "foot_r", "ball_l", "ball_r"],
    "boot_shaft": ["calf_l", "calf_r", "foot_l", "foot_r"],
}


def _scoped_weights(rig: Rig, surface: Surface, slot: int, points: np.ndarray,
                    region: str):
    """Skin weights, solved separately for each scope the surface declares."""
    scopes = surface.scope_array(slot, len(points))
    named = sorted({str(name) for name in scopes} & set(SKIN_SCOPES))
    if not named:
        return rig.weights_for(points, GARMENT_SKIN[region])
    joints = np.zeros((len(points), 4), dtype=np.int64)
    weights = np.zeros((len(points), 4), dtype=np.float64)
    rest = np.ones(len(points), dtype=bool)
    for name in named:
        picked = scopes == name
        if not picked.any():
            continue
        rest &= ~picked
        block_joints, block_weights = rig.weights_for(
            points[picked], SKIN_SCOPES[name])
        joints[picked] = block_joints
        weights[picked] = block_weights
    if rest.any():
        block_joints, block_weights = rig.weights_for(
            points[rest], GARMENT_SKIN[region])
        joints[rest] = block_joints
        weights[rest] = block_weights
    return joints, weights


def detail_colour(base) -> tuple:
    """Third material slot: the same hue, dropped back for straps and soles."""
    return tuple(round(channel * .46 + 18) for channel in base)


def variant_slug(slug: str, group: str) -> str:
    return f"{slug}__{group}"


def _model_entry(rig: Rig, idle_bases: dict | None, scene_root: str, slug: str,
                 part: int, kind: str, author_rig: str = "") -> dict:
    model = {"scene": f"{scene_root}/{slug}.glb"}
    if kind in GARMENT_KINDS:
        model["attach"] = "skinned"
        model["skinRegion"] = garment_region(kind)
        # The kind as well as the region.  `skinRegion` says which bones a
        # piece is bound to and several kinds share one - `pants` and `legs`
        # are both `legs` - but they are cut to different hems and are checked
        # against different seams, so the tests need to tell them apart.
        model["kind"] = kind
        # Which body this piece was lofted around.  The runtime divides the
        # wearer's measurements by this rig's to refit the garment, so a piece
        # that forgot to say would be worn at the reference's proportions.
        if author_rig:
            model["authoredFor"] = author_rig
        variants = {group: {
            "scene": f"{scene_root}/{variant_slug(slug, group)}.glb",
            "authoredFor": spec["rig"]}
            for group, spec in FIT_GROUPS.items() if kind in spec["kinds"]}
        if variants:
            model["variants"] = variants
    else:
        model["attach"] = "socket"
        socket = build_sockets(rig, idle_bases, kind).get(part)
        if socket is not None and (
                idle_bases is not None and kind in GRIP_UPRIGHT):
            model["socket"] = socket.as_json()
    if part == 3:
        hides = list(PARTS[3]["hides"])
        if kind in ENCLOSING_HEADWEAR:
            hides.append("hair")
        model["hides"] = hides
    return model


def build_equipment_registry(rig: Rig, entries, idle_bases: dict | None = None,
                             scene_root: str = "res://assets/actors/native/equipment",
                             generic=None, author_rig: str = "",
                             girths: dict | None = None,
                             sole_drops: dict | None = None,
                             foot_anchors: dict | None = None,
                             footwear=None) -> dict:
    """Emit ``data/actors/equipment.json`` for the runtime attachment path."""
    # Resolved here rather than as a default: the generic catalogue is declared
    # further down the module, beside the geometry it describes.
    generic = GENERIC_EQUIPMENT if generic is None else generic
    default_sockets = build_sockets(rig, idle_bases)
    models: dict[str, dict] = {}
    for slug, _label, part, visual, kind, *_ in entries:
        models[f"{part}:{visual}"] = _model_entry(
            rig, idle_bases, scene_root, slug, part, kind, author_rig)
    # The footwear catalogue: sixty-four designs, one authored mesh each rather
    # than one mesh under sixty-four tints, so no ``tint`` is emitted for them.
    for visual, design in (footwear or {}).items():
        model = _model_entry(rig, idle_bases, scene_root, design.slug, 6,
                             "boots", author_rig)
        model["name"] = design.label
        model["concept"] = {"sheet": design.sheet, "cell": list(design.cell)}
        models[f"6:{visual}"] = model
    # The generic tier shares one mesh across a material ladder, so each legacy
    # id is the same scene under a different tint rather than its own asset.
    for piece in generic:
        for visual, name, base, accent in piece.variants:
            model = _model_entry(rig, idle_bases, scene_root, piece.slug,
                                 piece.part, piece.kind, author_rig)
            model["name"] = name
            model["tint"] = [list(base), list(accent), list(detail_colour(base))]
            models[f"{piece.part}:{visual}"] = model
    return {
        "schemaVersion": 3,
        "canonicalHeadRestY": round(float(rig.rest["Head"][1, 3]), 5),
        "parts": {str(part): value for part, value in PARTS.items()},
        "sockets": {str(part): socket.as_json()
                    for part, socket in sorted(default_sockets.items())},
        "skinRegions": {name: list(bones) for name, bones in sorted(GARMENT_SKIN.items())},
        "models": models,
        "aliases": dict(ALIASES),
        # Groups resolve explicit body variants; ordered lists retain the
        # registry's existing first-matching-variant behaviour.
        "fitGroups": {race: [group for group, spec in FIT_GROUPS.items()
                             if spec["kinds"] and race in spec["races"]]
                      for race in sorted({race for spec in FIT_GROUPS.values()
                                          if spec["kinds"]
                                          for race in spec["races"]})},
        # Per-race body measurements the runtime refits garments with.
        "bodyGirth": girths or {},
        # Weighted surface distances; the joint rest height is shared.
        "soleDrop": sole_drops or {},
        # Actual foot centres and soles, relative to their shared joints.
        "footAnchor": foot_anchors or {},
    }


def apply_pins(rig: Rig, pins: list, joints: np.ndarray,
               weights: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """Replace inherited weights with a rigid binding where a vertex is pinned.

    See ``Surface.pinned``.  A pinned vertex is bound wholly to one bone, so the
    piece it belongs to turns with that bone and nothing else.
    """
    if not pins or not any(pins):
        return joints, weights
    index = {name: slot for slot, name in enumerate(rig.joint_names)}
    joints, weights = joints.copy(), weights.copy()
    for slot, bone in enumerate(pins):
        if bone is None or bone not in index or slot >= len(joints):
            continue
        joints[slot] = 0
        weights[slot] = 0.0
        joints[slot, 0] = index[bone]
        weights[slot, 0] = 1.0
    return joints, weights


def garment_region(kind: str) -> str:
    if kind in {"cuirass", "coat", "robe", "shirt"}:
        return "torso"
    if kind in {"legs", "pants"}:
        return "legs"
    if kind == "kilt":
        # A hanging panel wants `spine_01` so it falls from the torso instead of
        # folding with the hips, which is what the `skirt` region is for.
        return "skirt"
    if kind == "boots":
        return "boots"
    if kind == "cape":
        return "cape"
    if kind == "gloves":
        return "hands"
    raise ValueError(f"not a garment: {kind}")


# ---------------------------------------------------------------------------
# Generic equipment: the legacy visual-id space
# ---------------------------------------------------------------------------

# The protocol's appearance bytes still carry the original wearable ids, and the
# craftable economy is built almost entirely on that generic tier: 168 of the
# 388 manufacturing outputs are wearable or wieldable.  Only the culture pieces
# had geometry, so an iron sword or a pair of leather boots drew nothing at all.
#
# One authored mesh serves a whole material ladder.  The ladder is a tint the
# runtime applies to the shared scene, so covering 155 ids costs 43 GLBs rather
# than 155.

# Material ladders, reused across every part so a steel helm and steel greaves
# read as the same alloy.
IRON = ((122, 126, 132), (170, 175, 182))
STEEL = ((172, 179, 188), (216, 222, 229))
TITANIUM = ((198, 208, 217), (236, 242, 248))
BRONZE = ((174, 122, 60), (219, 170, 90))
WOOD = ((124, 92, 58), (168, 133, 84))
LEATHER = ((108, 76, 48), (152, 113, 67))
AUGMENTED = ((84, 60, 42), (190, 151, 84))
FUR = ((156, 142, 124), (208, 197, 181))
RACOON = ((110, 104, 98), (226, 224, 218))
SKUNK = ((44, 42, 46), (232, 231, 228))

# Dye ladders for cloth.
DYES = {
    "black": ((44, 44, 48), (86, 86, 92)),
    "blue": ((52, 76, 124), (104, 133, 186)),
    "bluegray": ((84, 100, 122), (140, 156, 178)),
    "brown": ((96, 70, 46), (146, 113, 76)),
    "browngray": ((104, 92, 80), (152, 140, 126)),
    "gray": ((98, 100, 104), (148, 150, 155)),
    "green": ((62, 92, 58), (108, 143, 98)),
    "greengray": ((92, 106, 92), (140, 155, 138)),
    "purple": ((92, 62, 124), (144, 108, 182)),
    "white": ((208, 206, 198), (240, 239, 234)),
    "gold": ((178, 142, 58), (232, 200, 108)),
    "red": ((132, 48, 44), (186, 88, 78)),
    "orange": ((186, 108, 44), (232, 158, 84)),
    "darkbrown": ((64, 46, 32), (108, 84, 60)),
    "lightbrown": ((146, 112, 74), (192, 160, 118)),
    "dullbrown": ((98, 82, 64), (142, 124, 100)),
    "pink": ((198, 130, 152), (234, 180, 196)),
    "yellow": ((206, 178, 72), (240, 219, 128)),
    "indigo": ((58, 62, 118), (108, 114, 178)),
    "teal": ((46, 108, 112), (96, 162, 166)),
    "crimson": ((122, 34, 46), (180, 74, 84)),
    "moss": ((78, 96, 62), (126, 146, 104)),
    "slate": ((72, 82, 92), (122, 134, 146)),
    "sand": ((176, 156, 116), (218, 203, 168)),
    "wine": ((94, 44, 62), (146, 84, 102)),
    "ash": ((118, 116, 112), (168, 166, 162)),
}


def dye(name: str) -> tuple:
    return DYES[name]


@dataclass(frozen=True)
class GenericPiece:
    """One authored mesh serving a run of legacy visual ids."""

    slug: str
    label: str
    part: int
    kind: str
    finish: str
    # (visual id, name, base rgb, accent rgb)
    variants: tuple

    @property
    def base(self):
        return self.variants[0][2]

    @property
    def accent(self):
        return self.variants[0][3]


def _sword_ladder():
    """Seven tiers of blade, from a plain bar to a polished alloy."""
    return (
        (1, "Iron Sword", *IRON),
        (2, "Iron Broad Sword", (134, 138, 144), (178, 183, 190)),
        (3, "Steel Sword", *STEEL),
        (4, "Steel Broad Sword", (182, 189, 197), (222, 228, 234)),
        (5, "Titanium Sword", *TITANIUM),
        (6, "Titanium Long Sword", (206, 216, 224), (240, 246, 250)),
        (7, "Titanium Serpent Sword", (214, 224, 231), (246, 250, 253)),
        (58, "Bronze Sword", *BRONZE),
    )


def _elemental(ids_and_names, accent):
    return tuple((visual, name, (146, 152, 160), accent)
                 for visual, name in ids_and_names)


GENERIC_EQUIPMENT = (
    # -- part 0: weapons ---------------------------------------------------
    GenericPiece("generic_sword", "Sword", 0, "sword", "plate", _sword_ladder()),
    GenericPiece("generic_sword_fire", "Sword of Fire", 0, "sword", "fire",
                 _elemental(((15, "Iron Sword of Fire"), (16, "Iron Broad Sword of Fire"),
                             (18, "Steel Sword of Fire"), (21, "Steel Broad Sword of Fire"),
                             (25, "Titanium Sword of Fire"), (29, "Titanium Long Sword of Fire"),
                             (33, "Titanium Serpent Sword of Fire")), (236, 116, 44))),
    GenericPiece("generic_sword_ice", "Sword of Ice", 0, "sword", "cold",
                 _elemental(((17, "Iron Broad Sword of Ice"), (19, "Steel Sword of Ice"),
                             (22, "Steel Broad Sword of Ice"), (26, "Titanium Sword of Ice"),
                             (30, "Titanium Long Sword of Ice"),
                             (34, "Titanium Serpent Sword of Ice")), (142, 208, 238))),
    GenericPiece("generic_sword_magic", "Sword of Magic", 0, "sword", "magic",
                 _elemental(((20, "Steel Sword of Magic"), (23, "Steel Broad Sword of Magic"),
                             (27, "Titanium Sword of Magic"),
                             (31, "Titanium Long Sword of Magic"),
                             (35, "Titanium Serpent Sword of Magic")), (180, 126, 236))),
    GenericPiece("generic_sword_thermal", "Thermal Sword", 0, "sword", "thermal",
                 _elemental(((24, "Steel Broad Thermal Sword"), (28, "Titanium Thermal Sword"),
                             (32, "Titanium Long Thermal Sword"),
                             (36, "Titanium Serpent Thermal Sword")), (242, 172, 76))),
    GenericPiece("generic_greatsword", "Great Sword", 0, "greatsword", "plate", (
        (51, "Emerald Claymore", (168, 182, 176), (96, 198, 142)),
        (53, "Sunbreaker", (196, 176, 128), (240, 198, 96)),
        (54, "Orc Slayer", (146, 142, 136), (188, 96, 72)),
        (55, "Eagle Wing", (200, 206, 212), (232, 226, 196)))),
    GenericPiece("generic_cutlass", "Cutlass", 0, "curved_sword", "plate", (
        (52, "Cutlass", (162, 168, 176), (206, 178, 96)),
        (57, "Jagged Saber", (150, 156, 164), (198, 200, 204)))),
    GenericPiece("generic_rapier", "Rapier", 0, "rapier", "plate", (
        (56, "Rapier", (188, 194, 202), (216, 186, 104)),)),
    GenericPiece("generic_staff", "Staff", 0, "staff", "wood", (
        (8, "Wooden Staff", *WOOD),
        (9, "Ash Staff", (104, 80, 54), (150, 122, 84)),
        (10, "Bound Staff", (88, 66, 46), (182, 150, 96)),
        (11, "Runed Staff", (72, 58, 46), (140, 176, 206)))),
    GenericPiece("generic_battleaxe", "Battle Axe", 0, "battleaxe", "plate", (
        (38, "Iron Battle Axe", *IRON), (39, "Steel Battle Axe", *STEEL),
        (40, "Titanium Battle Axe", *TITANIUM))),
    GenericPiece("generic_battleaxe_fire", "Battle Axe of Fire", 0, "battleaxe",
                 "fire", _elemental(
                     ((41, "Iron Battle Axe of Fire"), (43, "Steel Battle Axe of Fire"),
                      (45, "Titanium Battle Axe of Fire")), (236, 116, 44))),
    GenericPiece("generic_battleaxe_ice", "Battle Axe of Ice", 0, "battleaxe",
                 "cold", _elemental(
                     ((42, "Steel Battle Axe of Ice"),
                      (44, "Titanium Battle Axe of Ice")), (142, 208, 238))),
    GenericPiece("generic_battleaxe_magic", "Battle Axe of Magic", 0, "battleaxe",
                 "magic", _elemental(
                     ((46, "Titanium Battle Axe of Magic"),), (180, 126, 236))),
    GenericPiece("generic_club_bone", "Bone Club", 0, "club", "shell", (
        (49, "Bone", (218, 212, 196), (240, 236, 226)),)),
    GenericPiece("generic_club_wood", "Wooden Club", 0, "club", "wood", (
        (50, "Stick", *WOOD),)),
    GenericPiece("generic_hammer", "War Hammer", 0, "hammer", "plate", (
        (12, "Iron War Hammer", *IRON),
        (13, "Steel War Hammer", *STEEL))),
    GenericPiece("generic_pickaxe", "Pickaxe", 0, "pick", "plate", (
        (14, "Pickaxe", *IRON),)),
    GenericPiece("generic_pickaxe_magic", "Magic Pickaxe", 0, "pick", "magic", (
        (37, "Magic Pickaxe", (146, 152, 160), (180, 126, 236)),)),
    GenericPiece("generic_bow", "Bow", 0, "bow", "wood", (
        (64, "Long Bow", *WOOD),
        (65, "Short Bow", (140, 106, 68), (182, 148, 98)),
        (66, "Recurve Bow", (96, 70, 46), (162, 126, 78)),
        (67, "Elven Bow", (118, 128, 96), (196, 206, 168)))),
    GenericPiece("generic_crossbow", "Crossbow", 0, "crossbow", "wood", (
        (68, "Crossbow", (110, 84, 56), (156, 160, 166)),)),
    GenericPiece("generic_gloves_leather", "Leather Gloves", 0, "gloves", "leather", (
        (48, "Leather Gloves", *LEATHER),)),
    GenericPiece("generic_gloves_fur", "Fur Gloves", 0, "gloves", "fur", (
        (47, "Fur Gloves", *FUR),)),

    # -- part 1: shields ---------------------------------------------------
    GenericPiece("generic_shield_wood", "Wooden Shield", 1, "roundshield", "wood", (
        (0, "Wooden Shield", *WOOD),
        (1, "Enhanced Wooden Shield", (104, 78, 50), (188, 154, 92)))),
    GenericPiece("generic_shield_metal", "Metal Shield", 1, "kite", "plate", (
        (2, "Iron Shield", *IRON),
        (3, "Steel Shield", *STEEL),
        (4, "Titanium Shield", *TITANIUM),
        (5, "Bronze Shield", *BRONZE))),

    GenericPiece("generic_quiver", "Quiver", 1, "quiver", "leather", (
        (7, "Quiver of Arrows", *LEATHER),
        (13, "Quiver of Bolts", (88, 70, 52), (162, 134, 88)))),

    # -- part 2: capes -----------------------------------------------------
    # Twenty-two dyes over one cape, plus a fur cape that needs its own pelt.
    GenericPiece("generic_cape", "Cape", 2, "cape", "cloth", (
        (0, "Black Cape", *dye("black")), (1, "Blue Cape", *dye("blue")),
        (2, "Blue-Gray Cape", *dye("bluegray")), (3, "Brown Cape", *dye("brown")),
        (4, "Brown-Gray Cape", *dye("browngray")), (5, "Gray Cape", *dye("gray")),
        (6, "Green Cape", *dye("green")), (7, "Green-Gray Cape", *dye("greengray")),
        (8, "Purple Cape", *dye("purple")), (9, "White Cape", *dye("white")),
        (11, "Gold Cape", *dye("gold")), (12, "Red Cape", *dye("red")),
        (13, "Orange Cape", *dye("orange")),
        (14, "Warden Cape", *dye("indigo")), (15, "Tidewatch Cape", *dye("teal")),
        (16, "Nightfall Cape", *dye("crimson")), (17, "Quiet Cape", *dye("moss")),
        (18, "Highreach Cape", *dye("slate")), (19, "Dawnward Cape", *dye("sand")),
        (20, "Sunwake Cape", *dye("wine")), (21, "Farhold Cape", *dye("ash")),
        (22, "Learner Cape", *dye("lightbrown")))),
    GenericPiece("generic_cape_fur", "Fur Cape", 2, "cape", "fur", (
        (10, "Fur Cape", *FUR),)),

    # -- part 3: helmets ---------------------------------------------------
    GenericPiece("generic_helm", "Helm", 3, "helm", "plate", (
        (0, "Iron Helmet", *IRON), (7, "Steel Helmet", *STEEL),
        (8, "Titanium Helmet", *TITANIUM), (9, "Bronze Helmet", *BRONZE))),
    GenericPiece("generic_hood_leather", "Leather Cap", 3, "hood", "leather", (
        (2, "Leather Helmet", *LEATHER),)),
    GenericPiece("generic_hood_fur", "Fur Cap", 3, "hood", "fur", (
        (1, "Fur Helmet", *FUR), (3, "Racoon Cap", *RACOON),
        (4, "Skunk Cap", *SKUNK))),
    GenericPiece("generic_crown", "Crown", 3, "circlet", "crystal", (
        (5, "Crown of Mana", (72, 82, 138), (128, 176, 240)),
        (6, "Crown of Life", (76, 118, 84), (140, 224, 152)))),

    # -- part 4: leg armour ------------------------------------------------
    GenericPiece("generic_pants", "Pants", 4, "pants", "cloth", (
        (0, "Black Pants", *dye("black")), (1, "Blue Pants", *dye("blue")),
        (2, "Brown Pants", *dye("brown")), (3, "Dark Brown Pants", *dye("darkbrown")),
        (4, "Grey Pants", *dye("gray")), (5, "Green Pants", *dye("green")),
        (6, "Light Brown Pants", *dye("lightbrown")), (7, "Red Pants", *dye("red")),
        (8, "White Pants", *dye("white")))),
    GenericPiece("generic_legs_leather", "Leather Leggings", 4, "legs", "leather", (
        (9, "Leather Pants", *LEATHER),
        (15, "Augmented Leather Cuisses", *AUGMENTED))),
    GenericPiece("generic_legs_fur", "Fur Leggings", 4, "legs", "fur", (
        (11, "Fur Pants", *FUR),)),
    GenericPiece("generic_cuisses", "Cuisses", 4, "legs", "plate", (
        (10, "Iron Cuisses", *IRON), (12, "Steel Cuisses", *STEEL),
        (13, "Titanium Cuisses", *TITANIUM), (14, "Bronze Cuisses", *BRONZE))),

    # -- part 5: body armour -----------------------------------------------
    GenericPiece("generic_shirt", "Shirt", 5, "shirt", "cloth", (
        (0, "Black Shirt", *dye("black")), (1, "Blue Shirt", *dye("blue")),
        (2, "Brown Shirt", *dye("brown")), (3, "Grey Shirt", *dye("gray")),
        (4, "Green Shirt", *dye("green")), (5, "Light Brown Shirt", *dye("lightbrown")),
        (6, "Orange Shirt", *dye("orange")), (7, "Pink Shirt", *dye("pink")),
        (8, "Purple Shirt", *dye("purple")), (9, "Red Shirt", *dye("red")),
        (10, "White Shirt", *dye("white")), (11, "Yellow Shirt", *dye("yellow")))),
    GenericPiece("generic_leather_armor", "Leather Armor", 5, "cuirass", "leather", (
        (12, "Leather Armor", *LEATHER),
        (17, "Augmented Leather Armor", *AUGMENTED))),
    GenericPiece("generic_chain_armor", "Chain Armor", 5, "cuirass", "mail", (
        (13, "Chain Mail", *IRON), (14, "Steel Chain Mail", *STEEL),
        (15, "Titanium Chain Mail", *TITANIUM))),
    GenericPiece("generic_plate_armor", "Plate Armor", 5, "cuirass", "plate", (
        (16, "Iron Plate Mail", *IRON), (19, "Steel Plate Mail", *STEEL),
        (20, "Titanium Plate Mail", *TITANIUM), (21, "Bronze Plate Mail", *BRONZE))),
    GenericPiece("generic_fur_coat", "Fur Coat", 5, "coat", "fur", (
        (18, "Fur Coat", *FUR),)),

    # -- part 6: boots -----------------------------------------------------
    GenericPiece("generic_boots", "Boots", 6, "boots", "leather", (
        (0, "Black Boots", *dye("black")), (1, "Brown Boots", *dye("brown")),
        (2, "Dark Brown Boots", *dye("darkbrown")),
        (3, "Dull Brown Boots", *dye("dullbrown")),
        (4, "Light Brown Boots", *dye("lightbrown")),
        (5, "Orange Boots", *dye("orange")), (6, "Leather Boots", *LEATHER),
        (12, "Augmented Leather Greaves", *AUGMENTED))),
    GenericPiece("generic_boots_fur", "Fur Boots", 6, "boots", "fur", (
        (7, "Fur Boots", *FUR),)),
    GenericPiece("generic_greaves", "Greaves", 6, "boots", "plate", (
        (8, "Iron Greaves", *IRON), (9, "Steel Greaves", *STEEL),
        (10, "Titanium Greaves", *TITANIUM), (11, "Bronze Greaves", *BRONZE))),
)
