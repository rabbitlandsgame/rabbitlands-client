"""Lining visibility masks: which generated lining triangles no camera can see.

    python eloria-assets/tools/lining_visibility.py masks --sample review --out <dir>
    python eloria-assets/tools/lining_visibility.py masks --all
    python eloria-assets/tools/lining_visibility.py finalise --sample review --out <dir> --margin 0.01
    python eloria-assets/tools/lining_visibility.py review --sample review --out <dir> --sheets
    python eloria-assets/tools/lining_visibility.py check <mask.json> [<garment.glb>] [--rewritten]

Added 2026-11-02 (actor LOD plan, chunk C3).  Skinned garments carry
``Generated*`` lining surfaces (``GeneratedArmorBacking``,
``GeneratedLegBacking[WithBoots]``, ``GeneratedBootBacking[WithLegs]``) that sit
inside the authored shell.  They are about half of all actor triangles, and
most of them can never be seen.  This tool proves which ones, per garment and
per lining, so the actor geometry cook (C4) can drop them from the index
buffer.  Nothing here changes an asset: the output is a mask file per garment.

Method (``lining_visibility_blender.py`` does the posing and ray casting in
background Blender; this file plans, schedules, finalises and reports):

1. The garment is posed with the shared posekit (library world deltas from
   ``Rest_Pose``, the same retarget design_fit uses) in every pose of the pose
   set: the bind pose, idle, walk and run extremes, attack swings, casts, arms
   raised, bow draw, sit and meditate, death, emotes, and mounted straddles
   rebuilt from ``data/mounts/*.json`` with the rider seat solver's two-bone IK.
   The posed vertices come from linear blend skinning in numpy on the glTF data
   itself, so triangle order is the glTF order the runtime parse keeps.
2. Occluders are only the piece's own non-lining surfaces (shell, inseams,
   forearm skin) and the lining itself.  The body, the twin lining and every
   other worn item are left out: a face hidden from this set is hidden whatever
   else is worn.  Back faces of single-sided materials are passed through, as
   the GPU culls them; alpha materials never occlude.
3. A lining triangle is visible when a ray from one of its sample points
   towards the camera escapes, for one of N directions over the whole sphere
   (directions the GPU would cull for a single-sided lining are skipped).
   Samples: the centroid, or a k x k subdivision for triangles larger than the
   sample spacing.  ``visible_upper`` is the same over camera elevations of
   -10 degrees and above (gameplay pitches are -15 to -80, the sun is above).
4. ``keep`` = visible, grown by a rest-space surface margin (2 cm): every
   triangle that comes within the margin of a visible triangle is kept too,
   which absorbs relative motion at openings, poses between the sampled ones
   and the gaps between sample points.

Output (one file per garment, ``<out>/<variant>/<stem>.lining.json``; byte
deterministic): the source path and SHA-256, the tool and input digests, the
settings and resolved pose list, and per lining the triangle count, a digest of
the glTF index buffer, eight check centroids, and base64 little-endian bitsets
``visible``, ``visible_upper``, ``visible_bind``, ``keep``, ``keep_upper`` and
``keep_bind`` (bit i = glTF triangle i).  ``check`` validates one against its
garment (``--rewritten``: against build-tree bytes, by geometry alone).  The raw ray-cast result is cached as ``<stem>.visibility.json`` so a
new margin needs no Blender run; both are reused while the garment, tool,
library, posekit, mount data and settings digests match (``finalise`` re-applies
a margin to cached records without Blender).

``review`` renders, for poses and camera directions that were not sampled,
which pixels would change if the removed faces were dropped, for this mask
and for any comparison mask (the bind-pose-only mask, or the 2 cm rest-pose
point-splat masks of the design experiment E4), and optional contact sheets:
as worn with removed faces drawn red (they should never show), and the lining
alone with removed faces red.

Blender runs in background mode only, at most four processes at a time.
"""
from __future__ import annotations

import argparse
import base64
import concurrent.futures
import hashlib
import json
import math
import os
import shutil
import struct
import subprocess
import sys
import time
import zlib
from pathlib import Path

import numpy as np

TOOLS = Path(__file__).resolve().parent
CLIENT_REPO = TOOLS.parent.parent
GODOT = CLIENT_REPO / "godot-client"
NATIVE = GODOT / "assets/actors/native"
VARIANTS = NATIVE / "equipment/variants"
LIBRARY = NATIVE / "shared/Universal_Animation_Library.glb"
MOUNTS = GODOT / "data/mounts"
POSEKIT = TOOLS / "shared_cape/posekit.py"
BLENDER_SCRIPT = TOOLS / "lining_visibility_blender.py"
DEFAULT_OUT = CLIENT_REPO / ".local/actor-geometry/lining-masks"
BLENDER_CANDIDATES = (
    Path(r"C:\Program Files\Blender Foundation\Blender 5.2\blender.exe"),
)

SCHEMA = 1
POLICY = "rl-lining-visibility-v1"
LINING_PREFIX = "Generated"
#: Surfaces whose runtime material replaces the GLB's: EquipmentForearmSkin
#: draws with the body's material (replicated_actor_3d.gd), so its GLB
#: sidedness is not trusted; single-sided is the conservative reading.
RUNTIME_SINGLE_SIDED = ("EquipmentForearmSkin",)
#: Mesh extras that make the runtime draw every textured surface of the mesh
#: with a cull_disabled shader (replicated_actor_3d.gd
#: _restore_piece_render_state: equipment_quilt / equipment_antler_palette).
#: A lining carrying one draws its back faces too, so it counts as
#: double-sided; other surfaces keep their glTF sidedness (as occluders that
#: is the conservative reading).
RUNTIME_TWO_SIDED_EXTRAS = ("repairQuiltPaint", "matchAntlerPalette")
#: Largest |rest world(joint) x inverse bind - I| a garment may have.  Poses
#: are applied to the glTF positions as rest-space vertices, which matches the
#: runtime only while every skin's bind pose is the node rest pose (all 400
#: lining garments: <= 1.7e-7 on 2026-11-02).
BIND_REST_TOLERANCE = 1e-4
#: The project's machine rule: at most four Blender/Python pool workers.
MAX_WORKERS = 4

DEFAULT_SETTINGS = {
    "directions": 128,
    "upper_min_elevation_deg": -10.0,
    "spacing_m": 0.03,
    "max_subdivision": 4,
    "eps_m": 1e-5,
    "max_layers": 64,
}
DEFAULT_MARGIN_M = 0.02
DEFAULT_MARGIN_RULE = "surface"
#: Rest-space sample spacing for the surface margin test (geometry only).
MARGIN_SPACING_M = 0.005
#: Keep variants the review measures beside the mask's own (rule, metres).
REVIEW_VARIANTS = (("surface", 0.0), ("surface", 0.01), ("surface", 0.02),
                   ("centroid", 0.01), ("centroid", 0.02))
CHECK_TRIANGLES = 8

#: Pose set v1.  A pose is the bind pose, a library clip at a fraction of its
#: length, or a mounted straddle (resolved from the mount's rider profile).
POSES_V1 = (
    "bind",
    "Rest_Pose@0", "Idle_Subtle@0", "Idle_A@0.5", "Fighting_Idle@0",
    "Walk@0", "Walk@0.25", "Walk@0.5", "Walk@0.75",
    "Run_Female@0", "Run_Female@0.25", "Run_Female@0.5", "Run_Female@0.75",
    "Sword_Regular_A@0.4", "Sword_Regular_A@0.82",
    "Sword_Regular_B@0.42", "Sword_Regular_B@0.82",
    "Sword_Regular_C@0.5", "Sword_Regular_C@1",
    "Two-hand_Blast@0.28", "Two-hand_Blast@0.72",
    "Spell_Simple_Idle@0", "Defend@0.5", "Power_Up@0.5", "Bow_Pull_Hold@0",
    "Shield_OneShot@0.5", "Chop_Tree@0.5", "Jump_air@0",
    "Meditate@0.5", "Sitting_Idle@0.5", "Sitting_Exit@0.5", "Death_A@1",
    "Backflip@0.5", "Jumping_Jacks@0.25", "Bow@0.5", "Victory_Fist_Pump@0.5",
    "Dance_Simple@0.25", "PickUp_Table@0.5", "Farm_Harvest@0.5", "Throw_Object@0.5",
    "mount:golden_plains_horse", "mount:lantern_stag", "mount:cave_salamander",
    "mount:crystalback_tortoise",
)
#: Poses the review renders.  None of them is in POSES_V1, so the review
#: measures what the sampled set misses between its frames.
REVIEW_POSES = (
    "Idle_A@0.25", "Walk@0.125", "Walk@0.625", "Run_Female@0.375", "Run_Female@0.875",
    "Sword_Regular_A@0.6", "Sword_Regular_C@0.75", "Two-hand_Blast@0.5",
    "Bow_Pull_Back@0.6", "Meditate@0.25", "Death_A@0.6", "Victory@0.5",
    "Crouch_Idle@0", "mount:giant_rat", "mount:jadefeather_raptor",
)
SHEET_POSES = ("Idle_Subtle@0", "Run_Female@0.25", "Power_Up@0.5", "mount:crystalback_tortoise")

#: The design experiment E4 measured these sixteen garments at rest pose
#: (actor-lod.md 3(c); three of them on the female variant, as its triangle
#: counts show); the review sample adds four more female variants.
SAMPLES = {
    "review": (
        "human_male/amberwood_woodland_cuirass_01", "human_male/amberwood_woodland_cuirass_02",
        "human_male/eloria_frontier_shirt_01", "human_male/knightly_torso_armor_03",
        "human_male/leather_ranger_torso_04", "human_female/legendary_hero_cuirass_05",
        "human_male/militia_torso_armor_02", "human_male/sunmane_steppe_shirt_06",
        "human_male/amberwood_woodland_legguards_01", "human_male/amberwood_woodland_legguards_02",
        "human_female/humble_frontier_pants_02", "human_male/militia_leg_armor_03",
        "human_male/arcane_fantasy_boots_02", "human_female/frontier_boots_03",
        "human_male/knightly_greaves_04", "human_male/leather_adventurer_boots_05",
        "human_female/amberwood_woodland_cuirass_02", "human_female/eloria_frontier_shirt_01",
        "human_female/amberwood_woodland_legguards_02", "human_female/arcane_fantasy_boots_02",
    ),
    "sheets": (
        "human_male/amberwood_woodland_cuirass_02", "human_male/eloria_frontier_shirt_01",
        "human_male/amberwood_woodland_legguards_02", "human_female/humble_frontier_pants_02",
        "human_male/arcane_fantasy_boots_02", "human_male/knightly_greaves_04",
    ),
}

# --------------------------------------------------------------------------- GLB

_COMPONENT = {5120: "<i1", 5121: "<u1", 5122: "<i2", 5123: "<u2", 5125: "<u4", 5126: "<f4"}
_WIDTH = {"SCALAR": 1, "VEC2": 2, "VEC3": 3, "VEC4": 4, "MAT4": 16}


def read_glb(path):
    """The JSON document and BIN chunk of a self-contained GLB."""
    data = Path(path).read_bytes()
    magic, version, length = struct.unpack_from("<III", data, 0)
    if magic != 0x46546C67 or version != 2 or length != len(data):
        raise ValueError(f"{path}: not a glTF 2.0 binary")
    offset, document, blob = 12, None, b""
    while offset < length:
        size, kind = struct.unpack_from("<II", data, offset)
        chunk = data[offset + 8:offset + 8 + size]
        if kind == 0x4E4F534A:
            document = json.loads(chunk.decode("utf-8"))
        elif kind == 0x004E4942:
            blob = chunk
        offset += 8 + size
    if document is None:
        raise ValueError(f"{path}: no JSON chunk")
    return document, blob


def read_glb_json(path):
    """Only the JSON chunk (cheap: used to scan hundreds of garments)."""
    with open(path, "rb") as handle:
        magic, version, _length, size, kind = struct.unpack("<IIIII", handle.read(20))
        if magic != 0x46546C67 or version != 2 or kind != 0x4E4F534A:
            raise ValueError(f"{path}: not a glTF 2.0 binary")
        return json.loads(handle.read(size).decode("utf-8"))


def accessor(document, blob, index):
    """An accessor as an (count, width) array (normalised integers to floats)."""
    spec = document["accessors"][index]
    if spec.get("sparse"):
        raise ValueError("sparse accessors are not supported")
    count, width = spec["count"], _WIDTH[spec["type"]]
    dtype = np.dtype(_COMPONENT[spec["componentType"]])
    if "bufferView" not in spec:
        return np.zeros((count, width), dtype=np.float64)
    view = document["bufferViews"][spec["bufferView"]]
    offset = view.get("byteOffset", 0) + spec.get("byteOffset", 0)
    stride = view.get("byteStride", 0) or width * dtype.itemsize
    array = np.ndarray((count, width), dtype=dtype, buffer=blob, offset=offset,
                       strides=(stride, dtype.itemsize)).copy()
    if spec.get("normalized") and spec["componentType"] != 5126:
        limit = np.iinfo(dtype)
        array = array.astype(np.float64) / limit.max
        if limit.min < 0:
            array = np.maximum(array, -1.0)
    return array


def _node_matrix(node):
    if "matrix" in node:
        return np.array(node["matrix"], dtype=np.float64).reshape(4, 4).T
    x, y, z, w = node.get("rotation", (0.0, 0.0, 0.0, 1.0))
    rotation = np.array([
        [1 - 2 * (y * y + z * z), 2 * (x * y - z * w), 2 * (x * z + y * w)],
        [2 * (x * y + z * w), 1 - 2 * (x * x + z * z), 2 * (y * z - x * w)],
        [2 * (x * z - y * w), 2 * (y * z + x * w), 1 - 2 * (x * x + y * y)]])
    matrix = np.eye(4)
    matrix[:3, :3] = rotation * np.array(node.get("scale", (1.0, 1.0, 1.0)), dtype=np.float64)
    matrix[:3, 3] = node.get("translation", (0.0, 0.0, 0.0))
    return matrix


def node_world_matrices(document):
    nodes = document.get("nodes", [])
    parent = {child: index for index, node in enumerate(nodes) for child in node.get("children", [])}
    cache = {}

    def world(index):
        if index not in cache:
            local = _node_matrix(nodes[index])
            cache[index] = world(parent[index]) @ local if index in parent else local
        return cache[index]

    return [world(index) for index in range(len(nodes))], parent


def is_lining(name):
    return str(name).startswith(LINING_PREFIX)


def lining_names(document):
    """Names of the lining meshes of a garment document, in mesh order."""
    return [m.get("name", "") for m in document.get("meshes", []) if is_lining(m.get("name", ""))]


def garment_parts(document, blob):
    """Every triangle primitive of the garment, ready to pose.

    Each part: ``mesh`` (name), ``mesh_index``, ``primitive``, ``lining``,
    ``positions`` (n, 3; glTF mesh space), ``triangles`` (m, 3; glTF order),
    ``joints``/``weights`` (n, k) for skinned parts with ``skin_joints`` (node
    names), or ``rigid`` (a node name the part follows) and ``matrix`` (its rest
    world matrix) for static ones; ``double_sided``, ``alpha`` and
    ``occludes`` from the material.
    """
    nodes = document.get("nodes", [])
    worlds, parent = node_world_matrices(document)
    joint_nodes = {j for skin in document.get("skins", []) for j in skin["joints"]}
    materials = document.get("materials", [])
    parts = []
    for node_index, node in enumerate(nodes):
        if "mesh" not in node:
            continue
        mesh = document["meshes"][node["mesh"]]
        name = mesh.get("name", node.get("name", ""))
        extras = mesh.get("extras") if isinstance(mesh.get("extras"), dict) else {}
        runtime_two_sided = is_lining(name) and any(extras.get(key) for key in RUNTIME_TWO_SIDED_EXTRAS)
        for primitive_index, primitive in enumerate(mesh.get("primitives", [])):
            if primitive.get("mode", 4) != 4:
                continue
            attributes = primitive["attributes"]
            positions = accessor(document, blob, attributes["POSITION"]).astype(np.float64)
            if "indices" in primitive:
                triangles = accessor(document, blob, primitive["indices"]).astype(np.int64).reshape(-1, 3)
            else:
                triangles = np.arange(len(positions) - len(positions) % 3, dtype=np.int64).reshape(-1, 3)
            material = materials[primitive["material"]] if primitive.get("material") is not None else {}
            double_sided = ((bool(material.get("doubleSided", False)) or runtime_two_sided)
                            and name not in RUNTIME_SINGLE_SIDED)
            alpha = material.get("alphaMode", "OPAQUE")
            part = {"mesh": name, "mesh_index": node["mesh"], "primitive": primitive_index,
                    "node": node.get("name", ""), "lining": is_lining(name),
                    "positions": positions, "triangles": triangles,
                    "material": material.get("name", ""), "double_sided": double_sided,
                    "alpha": alpha, "occludes": alpha == "OPAQUE"}
            if "skin" in node and "JOINTS_0" in attributes:
                skin = document["skins"][node["skin"]]
                sets = [k for k in range(8) if f"JOINTS_{k}" in attributes]
                joints = np.concatenate([accessor(document, blob, attributes[f"JOINTS_{k}"]) for k in sets], axis=1)
                weights = np.concatenate([accessor(document, blob, attributes[f"WEIGHTS_{k}"]) for k in sets], axis=1)
                total = weights.sum(axis=1, keepdims=True)
                weights = np.where(total > 0, weights / np.maximum(total, 1e-12), 0.0)
                part.update(joints=joints.astype(np.int64), weights=weights.astype(np.float64),
                            skin_joints=[nodes[j].get("name", "") for j in skin["joints"]])
            else:
                ancestor = node_index
                while ancestor in parent and ancestor not in joint_nodes:
                    ancestor = parent[ancestor]
                part.update(rigid=nodes[ancestor].get("name", "") if ancestor in joint_nodes else None,
                            matrix=worlds[node_index])
            parts.append(part)
    return parts


def skin_rest_deviation(document, blob):
    """Largest |rest world(joint) x inverse bind - I| over the garment's skins.

    Zero when every skin was bound in the node rest pose, which the posing
    assumes (it moves the glTF positions by posed x rest^-1 per joint).
    """
    worlds, _ = node_world_matrices(document)
    worst = 0.0
    for skin in document.get("skins", []):
        joints = skin.get("joints", [])
        if "inverseBindMatrices" in skin:
            inverse = accessor(document, blob, skin["inverseBindMatrices"]).astype(np.float64)
            inverse = inverse.reshape(-1, 4, 4).transpose(0, 2, 1)
        else:
            inverse = np.repeat(np.eye(4)[None], len(joints), axis=0)
        for slot, joint in enumerate(joints):
            worst = max(worst, float(np.abs(worlds[joint] @ inverse[slot] - np.eye(4)).max()))
    return worst


def triangle_corners(positions, triangles):
    return positions[triangles]


def face_normals(corners):
    normal = np.cross(corners[:, 1] - corners[:, 0], corners[:, 2] - corners[:, 0])
    length = np.linalg.norm(normal, axis=1, keepdims=True)
    return np.where(length > 1e-20, normal / np.maximum(length, 1e-30), 0.0)


def index_digest(triangles):
    return hashlib.sha256(np.ascontiguousarray(triangles, dtype="<u4").tobytes()).hexdigest()


def check_centroids(corners, count=CHECK_TRIANGLES):
    """[[triangle, x, y, z], ...] at evenly spread triangles (rest, glTF space)."""
    n = len(corners)
    if n == 0:
        return []
    picks = sorted({int(round(i * (n - 1) / max(count - 1, 1))) for i in range(min(count, n))})
    centre = corners.mean(axis=1)
    return [[p] + [round(float(v), 6) for v in centre[p]] for p in picks]


# ---------------------------------------------------------------- sampling, bits

def fibonacci_directions(count):
    """Unit directions (towards the camera) spread evenly over the sphere, +Y up."""
    i = np.arange(count, dtype=np.float64) + 0.5
    y = 1.0 - 2.0 * i / count
    r = np.sqrt(np.maximum(0.0, 1.0 - y * y))
    theta = math.pi * (1.0 + 5.0 ** 0.5) * i
    return np.c_[r * np.cos(theta), y, r * np.sin(theta)]


def upper_flags(directions, min_elevation_deg):
    return directions[:, 1] >= math.sin(math.radians(min_elevation_deg))


def subdivision_barycentrics(k):
    """Centroids of the k*k triangles of a k-fold subdivision (rows sum to 1)."""
    rows = []
    for i in range(k):
        for j in range(k - i):
            rows.append(((i + 1.0 / 3.0) / k, (j + 1.0 / 3.0) / k))
            if i + j < k - 1:
                rows.append(((i + 2.0 / 3.0) / k, (j + 2.0 / 3.0) / k))
    uv = np.array(rows, dtype=np.float64)
    return np.c_[1.0 - uv.sum(axis=1), uv]


def sample_plan(corners, spacing, max_subdivision):
    """(owner, barycentric) sample points: the centroid, or a k x k subdivision."""
    edges = np.stack([np.linalg.norm(corners[:, 1] - corners[:, 0], axis=1),
                      np.linalg.norm(corners[:, 2] - corners[:, 1], axis=1),
                      np.linalg.norm(corners[:, 0] - corners[:, 2], axis=1)], axis=1)
    k = np.clip(np.ceil(edges.max(axis=1) / spacing), 1, max_subdivision).astype(np.int64)
    owners, barys = [], []
    for value in np.unique(k):
        faces = np.nonzero(k == value)[0]
        bary = subdivision_barycentrics(int(value))
        owners.append(np.repeat(faces, len(bary)))
        barys.append(np.tile(bary, (len(faces), 1)))
    if not owners:
        return np.zeros(0, np.int64), np.zeros((0, 3))
    owner = np.concatenate(owners)
    bary = np.concatenate(barys)
    order = np.argsort(owner, kind="stable")
    return owner[order], bary[order]


def apply_samples(corners, owner, bary):
    return np.einsum("sk,skj->sj", bary, corners[owner])


def pack_bits(mask):
    return base64.b64encode(np.packbits(np.asarray(mask, dtype=bool), bitorder="little").tobytes()).decode("ascii")


def unpack_bits(text, count):
    raw = np.frombuffer(base64.b64decode(text.encode("ascii"), validate=True), dtype=np.uint8)
    if len(raw) != (count + 7) // 8:
        raise ValueError(f"bitset holds {len(raw)} bytes for {count} triangles")
    bits = np.unpackbits(raw, bitorder="little").astype(bool)
    if bits[count:].any():
        raise ValueError("bitset has bits set past the triangle count")
    return bits[:count]


def run_count(mask):
    mask = np.asarray(mask, dtype=bool)
    if not mask.any():
        return 0
    return int(mask[0]) + int(np.count_nonzero(mask[1:] & ~mask[:-1]))


MARGIN_RULES = ("surface", "centroid")


def keep_with_margin(corners, visible, margin, rule="surface", spacing=MARGIN_SPACING_M):
    """Visible triangles plus those within ``margin`` of one (rest space).

    ``surface``: some point of the triangle lies within the margin of some
    point of a visible triangle (both sampled every ``spacing``, so the
    distance is accurate to about that).  ``centroid``: the triangle's
    centroid lies within the margin of a visible triangle's centroid (the
    rule of the design experiment E4; weak for large triangles).
    """
    from scipy.spatial import cKDTree  # driver side only (Blender has no scipy)

    visible = np.asarray(visible, dtype=bool)
    keep = visible.copy()
    if not visible.any() or visible.all() or margin <= 0.0:
        return keep
    if rule == "centroid":
        centre = corners.mean(axis=1)
        distance, _ = cKDTree(centre[visible]).query(centre[~visible], k=1, distance_upper_bound=margin)
        keep[np.nonzero(~visible)[0][np.isfinite(distance)]] = True
        return keep
    if rule != "surface":
        raise ValueError(f"unknown margin rule {rule!r}")
    owner, bary = sample_plan(corners, spacing, 64)
    points = apply_samples(corners, owner, bary)
    query = ~visible[owner]
    distance, _ = cKDTree(points[~query]).query(points[query], k=1, distance_upper_bound=margin)
    keep[owner[query][np.isfinite(distance)]] = True
    return keep


# ---------------------------------------------------------------------- poses

def parse_pose(name, mounts_dir=MOUNTS):
    """A resolved pose recipe: bind, a clip frame, or a mounted straddle."""
    if name == "bind":
        return {"name": name, "kind": "bind"}
    if name.startswith("mount:"):
        mount = name.split(":", 1)[1]
        profile = json.loads((Path(mounts_dir) / f"{mount}.json").read_text(encoding="utf-8"))
        rider = {key: [float(v) for v in profile[source]] for key, source in (
            ("foot", "footOffsetMetres"), ("knee", "kneePoleOffsetMetres"),
            ("hand", "handOffsetMetres"), ("elbow", "elbowPoleOffsetMetres"))}
        rider["lean_deg"] = float(profile.get("pelvisLeanDegrees", 3.0))
        return {"name": name, "kind": "mount", "clip": "Idle_Subtle", "at": 0.0, "rider": rider}
    clip, _, at = name.partition("@")
    if not clip or not at:
        raise ValueError(f"pose {name!r}: expected bind, Clip@fraction or mount:<id>")
    fraction = float(at)
    if not 0.0 <= fraction <= 1.0:
        raise ValueError(f"pose {name!r}: fraction outside 0..1")
    return {"name": name, "kind": "clip", "clip": clip, "at": fraction}


def resolve_poses(names, mounts_dir=MOUNTS):
    if len(set(names)) != len(names):
        raise ValueError("duplicate pose names")
    return [parse_pose(name, mounts_dir) for name in names]


def library_clips(library=LIBRARY):
    return {a.get("name", "") for a in read_glb_json(library).get("animations", [])}


# -------------------------------------------------------------------- digests

def file_sha256(path):
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for block in iter(lambda: handle.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def json_sha256(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":")).encode("utf-8")).hexdigest()


def tool_inputs(library=LIBRARY):
    return {"tool_sha256": file_sha256(__file__), "blender_tool_sha256": file_sha256(BLENDER_SCRIPT),
            "posekit_sha256": file_sha256(POSEKIT), "library_sha256": file_sha256(library)}


def res_path(path):
    path = Path(path).resolve()
    try:
        return "res://" + path.relative_to(GODOT.resolve()).as_posix()
    except ValueError:
        return path.as_posix()


def variant_stem(path):
    path = Path(path)
    return f"{path.parent.name}/{path.stem}"


# ------------------------------------------------------------------ discovery

def discover(root=VARIANTS):
    """Garment GLBs under ``root`` that carry at least one lining, sorted."""
    found = []
    for path in sorted(Path(root).glob("*/*.glb")):
        try:
            if lining_names(read_glb_json(path)):
                found.append(path)
        except (OSError, ValueError, struct.error):
            continue
    return found


def sample_paths(name, root=VARIANTS):
    if name not in SAMPLES:
        raise SystemExit(f"unknown sample {name!r}; known: {', '.join(sorted(SAMPLES))}")
    return [Path(root) / f"{entry}.glb" for entry in SAMPLES[name]]


def visibility_path(out_dir, glb):
    return Path(out_dir) / f"{variant_stem(glb)}.visibility.json"


def mask_path(out_dir, glb):
    return Path(out_dir) / f"{variant_stem(glb)}.lining.json"


def review_path(out_dir, glb):
    return Path(out_dir) / f"{variant_stem(glb)}.review.json"


def _load_json(path):
    try:
        return json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def visibility_current(doc, sha256, settings_sha256, inputs):
    return (isinstance(doc, dict) and doc.get("schema") == SCHEMA and doc.get("policy") == POLICY
            and doc.get("source", {}).get("sha256") == sha256
            and doc.get("settings_sha256") == settings_sha256 and doc.get("inputs") == inputs
            and not doc.get("errors"))


def plan_visibility(glbs, out_dir, settings, poses, inputs, force=False):
    """(jobs, reused): garments that need a Blender visibility run."""
    settings_sha256 = json_sha256({"settings": settings, "poses": poses})
    jobs, reused = [], []
    for glb in glbs:
        glb = Path(glb)
        sha256 = file_sha256(glb)
        target = visibility_path(out_dir, glb)
        if not force and visibility_current(_load_json(target), sha256, settings_sha256, inputs):
            reused.append(glb)
            continue
        document = read_glb_json(glb)
        cost = 0
        for mesh in document.get("meshes", []):
            if is_lining(mesh.get("name", "")):
                for primitive in mesh.get("primitives", []):
                    if "indices" in primitive:
                        cost += document["accessors"][primitive["indices"]]["count"] // 3
        jobs.append({"path": str(glb.resolve()), "res_path": res_path(glb), "sha256": sha256,
                     "bytes": glb.stat().st_size, "out": str(target.resolve()), "cost": cost})
    return jobs, reused


def balance(jobs, bins):
    """Longest-processing-time split of jobs into at most ``bins`` lists."""
    bins = max(1, min(bins, len(jobs)))
    loads = [[0, i, []] for i in range(bins)]
    for job in sorted(jobs, key=lambda j: (-int(j.get("cost", 0)), j["path"])):
        target = min(loads, key=lambda entry: (entry[0], entry[1]))
        target[0] += int(job.get("cost", 0)) + 1
        target[2].append(job)
    return [entry[2] for entry in loads if entry[2]]


# ----------------------------------------------------------------- finalising

def finalise(visibility, glb, margin=DEFAULT_MARGIN_M, rule=DEFAULT_MARGIN_RULE):
    """The mask document for a visibility result (adds the margin keeps)."""
    document, blob = read_glb(glb)
    parts = {(p["mesh"], p["primitive"]): p for p in garment_parts(document, blob)}
    linings = {}
    for name, entry in sorted(visibility["linings"].items()):
        part = parts[(entry["mesh"], entry["primitive"])]
        corners = triangle_corners(part["positions"], part["triangles"])
        count = entry["triangles"]
        if len(corners) != count or index_digest(part["triangles"]) != entry["gltf_index_sha256"]:
            raise ValueError(f"{glb}: {name} no longer matches its visibility record")
        # Own copies: the cached visibility record must not pick up keep counts.
        out = dict(entry, counts=dict(entry.get("counts", {})), runs=dict(entry.get("runs", {})))
        for key in ("", "_upper", "_bind"):
            bits = entry.get("visible" + key)
            if bits is None:
                continue
            keep = keep_with_margin(corners, unpack_bits(bits, count), margin, rule)
            out["keep" + key] = pack_bits(keep)
            out["counts"]["keep" + key] = int(keep.sum())
            out["runs"]["keep" + key] = run_count(keep)
        linings[name] = out
    mask = {key: visibility[key] for key in ("schema", "policy", "source", "inputs", "settings",
                                             "settings_sha256", "poses", "occluders")}
    mask["margin_m"] = margin
    mask["margin_rule"] = rule
    mask["linings"] = linings
    return mask


def check_mask(mask, glb=None, rewritten=False):
    """Problems with a mask file (an empty list when it is sound).

    With ``glb`` the mask is bound to that garment: its source SHA-256 must
    match, and per lining the triangle count, the glTF index digest and the
    check centroids.  ``rewritten`` accepts a garment whose bytes were rewritten
    after the cast (a build tree: quantised attributes, stripped images) on the
    geometric binding alone; the SHA-256 is then not compared.
    """
    problems = []
    if mask.get("schema") != SCHEMA or mask.get("policy") != POLICY:
        return [f"schema/policy {mask.get('schema')}/{mask.get('policy')} not {SCHEMA}/{POLICY}"]
    parts = None
    if glb is not None:
        if not rewritten and file_sha256(glb) != mask.get("source", {}).get("sha256"):
            problems.append("source sha256 differs from the garment (a build tree: check --rewritten)")
        document, blob = read_glb(glb)
        deviation = skin_rest_deviation(document, blob)
        if deviation > BIND_REST_TOLERANCE:
            problems.append(f"a skin's bind pose differs from the node rest pose by {deviation:.3g}: "
                            "the posed garment would not match the runtime")
        parts = {(p["mesh"], p["primitive"]): p for p in garment_parts(document, blob)}
        missing = sorted(set(lining_names(document)) - set(mask.get("linings", {})))
        if missing:
            problems.append(f"linings without a mask: {missing}")
    for name, entry in sorted(mask.get("linings", {}).items()):
        count = int(entry.get("triangles", -1))
        try:
            bits = {key: unpack_bits(entry[key], count) for key in
                    ("visible", "visible_upper", "visible_bind", "keep", "keep_upper", "keep_bind")
                    if key in entry}
        except (KeyError, ValueError) as error:
            problems.append(f"{name}: {error}")
            continue
        if "keep" not in bits or "visible" not in bits:
            problems.append(f"{name}: keep/visible missing")
            continue
        if (bits["visible"] & ~bits["keep"]).any():
            problems.append(f"{name}: a visible triangle is not kept")
        if "visible_upper" in bits and (bits["visible_upper"] & ~bits["visible"]).any():
            problems.append(f"{name}: visible_upper is not inside visible")
        if "keep_upper" in bits and (bits["keep_upper"] & ~bits["keep"]).any():
            problems.append(f"{name}: keep_upper is not inside keep")
        if "visible_bind" in bits:
            if (bits["visible_bind"] & ~bits["visible"]).any():
                problems.append(f"{name}: visible_bind is not inside visible")
            if "keep_bind" in bits and (bits["visible_bind"] & ~bits["keep_bind"]).any():
                problems.append(f"{name}: a bind-visible triangle is not in keep_bind")
        if parts is not None:
            part = parts.get((entry.get("mesh"), entry.get("primitive")))
            if part is None or len(part["triangles"]) != count:
                problems.append(f"{name}: triangle count differs from the garment")
                continue
            if index_digest(part["triangles"]) != entry.get("gltf_index_sha256"):
                problems.append(f"{name}: index buffer differs from the garment")
            centre = triangle_corners(part["positions"], part["triangles"]).mean(axis=1)
            for row in entry.get("check", []):
                if np.abs(centre[int(row[0])] - np.array(row[1:4])).max() > 1e-4:
                    problems.append(f"{name}: check centroid {row[0]} moved")
                    break
    return problems


# ------------------------------------------------------------------- Blender

def find_blender(explicit=None):
    if explicit:
        return Path(explicit)
    for candidate in BLENDER_CANDIDATES:
        if candidate.exists():
            return candidate
    found = shutil.which("blender")
    if found:
        return Path(found)
    raise SystemExit("could not find blender.exe (pass --blender)")


def blender_env():
    env = dict(os.environ)
    for key in ("OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS", "MKL_NUM_THREADS"):
        env[key] = "1"
    return env


def run_blender_jobs(batches, work_dir, blender, label, threads=1):
    """Run one background Blender per batch (at most MAX_WORKERS at once)."""
    work_dir = Path(work_dir)
    work_dir.mkdir(parents=True, exist_ok=True)
    if len(batches) > MAX_WORKERS:
        raise ValueError("more batches than the four-worker limit")

    def launch(index_batch):
        index, batch = index_batch
        job_file = work_dir / f"{label}-{index}.job.json"
        log_file = work_dir / f"{label}-{index}.log"
        job_file.write_text(json.dumps(batch, indent=1), encoding="utf-8")
        with open(log_file, "w", encoding="utf-8", errors="replace") as log:
            code = subprocess.call([str(blender), "-b", "--factory-startup", "-noaudio", "-t", str(threads),
                                    "--python", str(BLENDER_SCRIPT), "--", "--job", str(job_file)],
                                   stdout=log, stderr=subprocess.STDOUT, env=blender_env())
        return index, code, log_file

    results = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=len(batches) or 1) as pool:
        for index, code, log_file in pool.map(launch, list(enumerate(batches))):
            results.append((index, code, log_file))
    return results


def common_job(settings, poses, library=LIBRARY):
    return {"library": str(Path(library).resolve()), "posekit": str(POSEKIT.resolve()),
            "settings": settings, "poses": poses}


# ------------------------------------------------------------------- reports

def summarise(masks, e4=None):
    """Rows per lining: triangles, visible, removable, and E4's figures."""
    rows = []
    for stem, mask in sorted(masks.items()):
        for name, entry in sorted(mask["linings"].items()):
            count = entry["triangles"]
            counts = entry["counts"]
            row = {"garment": stem, "lining": name, "triangles": count,
                   "visible_bind": counts.get("visible_bind"), "visible": counts["visible"],
                   "visible_upper": counts["visible_upper"],
                   "removable_bind": count - counts["keep_bind"] if "keep_bind" in counts else None,
                   "removable": count - counts["keep"], "removable_upper": count - counts["keep_upper"],
                   "keep_runs": entry["runs"].get("keep")}
            record = (e4 or {}).get(Path(stem).name + ".glb", {}).get(name)
            if record and record.get("tris") == count:
                row.update(e4_visible=record["sphere_visible"],
                           e4_removable=record["sphere_hidden_margin2cm"],
                           e4_removable_upper=record["upper_hidden_margin2cm"])
            rows.append(row)
    return rows


def load_e4(paths):
    merged = {}
    for path in paths or ():
        merged.update(json.loads(Path(path).read_text(encoding="utf-8")))
    return merged


def _pct(part, whole):
    return "-" if part is None or not whole else f"{100.0 * part / whole:.0f}%"


def summary_markdown(rows):
    lines = ["| garment | lining | tris | visible bind / all poses | removable bind / all poses | E4 visible / removable | removable upper |",
             "| --- | --- | ---: | --- | --- | --- | --- |"]
    for r in rows:
        e4 = f"{r['e4_visible']} / {_pct(r['e4_removable'], r['triangles'])}" if "e4_visible" in r else "-"
        lines.append(
            f"| {r['garment']} | {r['lining']} | {r['triangles']} | {r['visible_bind']} / {r['visible']} | "
            f"{_pct(r['removable_bind'], r['triangles'])} / {_pct(r['removable'], r['triangles'])} | {e4} | "
            f"{_pct(r['removable_upper'], r['triangles'])} |")
    return "\n".join(lines) + "\n"


def write_png(path, rgb):
    """Write an (h, w, 3) uint8 image as PNG (no dependencies)."""
    rgb = np.ascontiguousarray(rgb, dtype=np.uint8)
    height, width = rgb.shape[:2]
    raw = b"".join(b"\x00" + rgb[row].tobytes() for row in range(height))

    def chunk(kind, data):
        return struct.pack(">I", len(data)) + kind + data + struct.pack(">I", zlib.crc32(kind + data) & 0xFFFFFFFF)

    Path(path).parent.mkdir(parents=True, exist_ok=True)
    Path(path).write_bytes(b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0))
                           + chunk(b"IDAT", zlib.compress(raw, 9)) + chunk(b"IEND", b""))


def compose_sheet(panel_dir, rows, columns, out_path, title):
    """Label and tile a garment's panels with PIL (skipped when PIL is absent)."""
    try:
        from PIL import Image, ImageDraw
    except ImportError:
        return None
    tiles = [[Image.open(Path(panel_dir) / f"{r}__{c}.png") for c in columns] for r in rows]
    w = max(t.width for row in tiles for t in row)
    h = max(t.height for row in tiles for t in row)
    left, top = 150, 40
    sheet = Image.new("RGB", (left + w * len(columns), top + 18 + h * len(rows)), (250, 250, 250))
    draw = ImageDraw.Draw(sheet)
    draw.text((6, 6), title, fill=(0, 0, 0))
    for ci, column in enumerate(columns):
        draw.text((left + ci * w + 4, top), column, fill=(0, 0, 0))
    for ri, row in enumerate(rows):
        draw.text((6, top + 18 + ri * h + h // 2), row, fill=(0, 0, 0))
        for ci, tile in enumerate(tiles[ri]):
            sheet.paste(tile, (left + ci * w, top + 18 + ri * h))
    sheet.save(out_path)
    return out_path


# ----------------------------------------------------------------------- CLI

def _settings_from(args):
    settings = dict(DEFAULT_SETTINGS)
    for key in ("directions", "spacing_m", "max_subdivision"):
        value = getattr(args, key, None)
        if value is not None:
            settings[key] = value
    return settings


def _glbs_from(args):
    if args.all:
        return discover()
    if args.sample:
        return sample_paths(args.sample)
    if not args.glbs:
        raise SystemExit("name garments, or pass --sample NAME or --all")
    return [Path(g) for g in args.glbs]


def _poses_from(text):
    if text in (None, "v1"):
        return list(POSES_V1)
    return [p for p in text.split(",") if p]


def command_masks(args):
    settings = _settings_from(args)
    poses = resolve_poses(_poses_from(args.poses))
    clips = library_clips()
    unknown = sorted({p["clip"] for p in poses if p.get("clip") and p["clip"] not in clips})
    if unknown:
        raise SystemExit(f"poses name clips the library lacks: {unknown}")
    out_dir = Path(args.out)
    inputs = tool_inputs()
    glbs = _glbs_from(args)
    jobs, reused = plan_visibility(glbs, out_dir, settings, poses, inputs, force=args.force)
    print(f"{len(glbs)} garments: {len(jobs)} to cast, {len(reused)} cached", flush=True)
    failures = []
    if jobs:
        workers = min(args.workers, MAX_WORKERS)
        batches = [dict(common_job(settings, poses), mode="visibility", inputs=inputs, glbs=batch)
                   for batch in balance(jobs, workers)]
        started = time.perf_counter()
        for index, code, log_file in run_blender_jobs(batches, out_dir / "_runs", find_blender(args.blender), "visibility"):
            if code != 0:
                failures.append(f"batch {index} exited {code}: see {log_file}")
        print(f"ray casting took {time.perf_counter() - started:.0f} s", flush=True)
    settings_sha256 = json_sha256({"settings": settings, "poses": poses})
    return _write_masks(args, glbs, out_dir, failures,
                        lambda doc, glb: visibility_current(doc, file_sha256(glb), settings_sha256, inputs))


def _write_masks(args, glbs, out_dir, failures, accept):
    out_dir.mkdir(parents=True, exist_ok=True)
    masks, visibilities = {}, {}
    for glb in glbs:
        visibility = _load_json(visibility_path(out_dir, glb))
        if not accept(visibility, glb):
            failures.append(f"{glb}: no usable visibility record")
            continue
        mask = finalise(visibility, glb, args.margin, args.margin_rule)
        problems = check_mask(mask, glb)
        if problems:
            failures.append(f"{glb}: {problems}")
            continue
        target = mask_path(out_dir, glb)
        target.write_text(json.dumps(mask, sort_keys=True, indent=1) + "\n", encoding="utf-8")
        masks[variant_stem(glb)] = mask
        visibilities[variant_stem(glb)] = visibility
    rows = summarise(masks, load_e4(args.e4))
    gains = pose_gains(visibilities)
    (out_dir / "summary.json").write_text(json.dumps({"rows": rows, "pose_gains": gains}, indent=1) + "\n",
                                          encoding="utf-8")
    text = summary_markdown(rows) + "\n" + pose_gains_markdown(gains)
    (out_dir / "summary.md").write_text(text, encoding="utf-8")
    print(text)
    for failure in failures:
        print("FAILED", failure, file=sys.stderr)
    return 1 if failures else 0


def pose_gains(visibilities):
    """Per pose: triangles first proven visible there, summed over garments.

    Poses run in the listed order (bind first), so a pose's gain is what the
    earlier poses had not already shown: a pose that adds nothing on a
    representative sample is a candidate to drop from the set.
    """
    gains = {}
    for doc in visibilities.values():
        for entry in doc["linings"].values():
            for pose, count in entry["new_visible_by_pose"].items():
                gains[pose] = gains.get(pose, 0) + int(count)
    order = next(iter(visibilities.values()))["poses"] if visibilities else sorted(gains)
    return [[pose, gains.get(pose, 0)] for pose in order]


def pose_gains_markdown(gains):
    lines = ["| pose (in cast order) | triangles first seen |", "| --- | ---: |"]
    lines += [f"| {pose} | {count} |" for pose, count in gains]
    return "\n".join(lines) + "\n"


def command_finalise(args):
    """Rewrite mask files from cached visibility records (new margin, no Blender).

    Accepts a record cast by an older tool as long as the garment is unchanged;
    the mask keeps that record's tool digests, so its provenance stays exact.
    """
    out_dir = Path(args.out)
    failures = []
    return _write_masks(args, _glbs_from(args), out_dir, failures,
                        lambda doc, glb: isinstance(doc, dict) and not doc.get("errors")
                        and doc.get("schema") == SCHEMA and doc.get("policy") == POLICY
                        and doc.get("source", {}).get("sha256") == file_sha256(glb))


def _e4_masks(e4_dir, glb, mask):
    """E4's 2 cm keep masks for this garment (uint8 per triangle), if present."""
    found = {}
    if not e4_dir:
        return found
    for name, entry in mask["linings"].items():
        path = Path(e4_dir) / f"{Path(glb).stem}__{name}.mask"
        if path.exists():
            keep = np.fromfile(path, dtype=np.uint8).astype(bool)
            if len(keep) == entry["triangles"]:
                found[name] = pack_bits(keep)
    return found


def variant_label(rule, margin):
    return f"{rule[0]}{round(margin * 100):d}cm"


def review_variants(mask, glb, e4_dir=None):
    """{label: {lining: bits}} keeps the review measures beside the mask's own."""
    document, blob = read_glb(glb)
    parts = {(p["mesh"], p["primitive"]): p for p in garment_parts(document, blob)}
    variants = {}
    for name, entry in mask["linings"].items():
        part = parts[(entry["mesh"], entry["primitive"])]
        corners = triangle_corners(part["positions"], part["triangles"])
        visible = unpack_bits(entry["visible"], entry["triangles"])
        for rule, margin in REVIEW_VARIANTS:
            variants.setdefault(variant_label(rule, margin), {})[name] = pack_bits(
                keep_with_margin(corners, visible, margin, rule))
        if "keep_bind" in entry:
            variants.setdefault("bind", {})[name] = entry["keep_bind"]
    e4 = _e4_masks(e4_dir, glb, mask)
    if e4:
        variants["e4"] = e4
    return variants


def review_rows(glb, mask, review, variants):
    """Per lining and keep variant: removable share and changed pixels."""
    rows = []
    for name, entry in sorted(review["linings"].items()):
        totals = entry["totals"]
        count = mask["linings"][name]["triangles"]
        removed = {"mask": count - mask["linings"][name]["counts"]["keep"]}
        for label, bits in variants.items():
            if name in bits:
                removed[label] = count - int(unpack_bits(bits[name], count).sum())
        for label in ["mask"] + sorted(variants):
            if label not in totals["changed_px"]:
                continue
            rows.append({"garment": variant_stem(glb), "lining": name, "variant": label, "triangles": count,
                         "removed": removed.get(label), "changed_px": totals["changed_px"][label],
                         "lining_px": totals["lining_px"], "garment_px": totals["garment_px"],
                         "views": totals["views"]})
    return rows


def review_markdown(rows):
    labels = []
    for row in rows:
        if row["variant"] not in labels:
            labels.append(row["variant"])
    head = "| garment | lining | tris | lining px | " + " | ".join(f"{l}: removed / changed px" for l in labels) + " |"
    lines = [head, "| --- | --- | ---: | ---: |" + " ---: |" * len(labels)]
    grouped = {}
    for row in rows:
        grouped.setdefault((row["garment"], row["lining"]), {})[row["variant"]] = row
    for (garment, lining), by in grouped.items():
        first = next(iter(by.values()))
        cells = [f"{_pct(by[l]['removed'], by[l]['triangles'])} / {by[l]['changed_px']}" if l in by else "-"
                 for l in labels]
        lines.append(f"| {garment} | {lining} | {first['triangles']} | {first['lining_px']} | " + " | ".join(cells) + " |")
    totals = {l: [0, 0, 0] for l in labels}
    for row in rows:
        t = totals[row["variant"]]
        t[0] += row["removed"] or 0
        t[1] += row["triangles"]
        t[2] += row["changed_px"]
    lines.append("| all | | | | " + " | ".join(f"{_pct(t[0], t[1])} / {t[2]}" for t in totals.values()) + " |")
    return "\n".join(lines) + "\n"


def command_review(args):
    out_dir = Path(args.out)
    glbs = _glbs_from(args)
    poses = resolve_poses(list(REVIEW_POSES) if args.poses is None else _poses_from(args.poses))
    sheet_glbs = {str(p.resolve()) for p in sample_paths("sheets")} if args.sheets else set()
    jobs, masks, variants = [], {}, {}
    for glb in glbs:
        mask_file = mask_path(out_dir, glb)
        mask = _load_json(mask_file)
        if mask is None or check_mask(mask, glb):
            raise SystemExit(f"{glb}: no sound mask; run `masks` first")
        masks[glb] = mask
        variants[glb] = review_variants(mask, glb, args.e4_masks)
        job = {"path": str(Path(glb).resolve()), "mask": str(mask_file.resolve()), "compare": variants[glb],
               "out": str(review_path(out_dir, glb).resolve()),
               "cost": sum(e["triangles"] for e in mask["linings"].values())}
        if str(Path(glb).resolve()) in sheet_glbs:
            job["sheet"] = {"poses": resolve_poses(list(SHEET_POSES)),
                            "dir": str((out_dir / "sheets" / variant_stem(glb)).resolve())}
        jobs.append(job)
    settings = dict(DEFAULT_SETTINGS, review_views=args.views, review_pixel_m=args.pixel, review_seed=args.seed)
    batches = [dict(common_job(settings, poses), mode="review", glbs=batch)
               for batch in balance(jobs, min(args.workers, MAX_WORKERS))]
    failures = [f"batch {i} exited {code}: see {log}" for i, code, log in
                run_blender_jobs(batches, out_dir / "_runs", find_blender(args.blender), "review") if code != 0]
    rows = []
    for glb in glbs:
        review = _load_json(review_path(out_dir, glb))
        if review is None or review.get("errors"):
            failures.append(f"{glb}: review failed: {(review or {}).get('errors')}")
            continue
        rows.extend(review_rows(glb, masks[glb], review, variants[glb]))
        for name, panels in review.get("sheet", {}).items():
            compose_sheet(panels["dir"], panels["rows"], panels["columns"],
                          Path(panels["dir"]).parent / f"{Path(glb).stem}__{name}.png",
                          f"{variant_stem(glb)} {name}: blue = kept lining, red = removed lining "
                          f"(as worn, red must never show)")
    (out_dir / "review.json").write_text(json.dumps(rows, indent=1) + "\n", encoding="utf-8")
    (out_dir / "review.md").write_text(review_markdown(rows), encoding="utf-8")
    print(review_markdown(rows))
    for failure in failures:
        print("FAILED", failure, file=sys.stderr)
    return 1 if failures else 0


def command_check(args):
    mask = json.loads(Path(args.mask).read_text(encoding="utf-8"))
    glb = args.glb or (GODOT / mask["source"]["path"].removeprefix("res://"))
    problems = check_mask(mask, glb, rewritten=args.rewritten)
    for problem in problems:
        print(problem)
    print("ok" if not problems else f"{len(problems)} problem(s)")
    return 1 if problems else 0


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    sub = parser.add_subparsers(dest="command", required=True)

    def common(p):
        p.add_argument("glbs", nargs="*")
        p.add_argument("--all", action="store_true", help="every garment with a lining")
        p.add_argument("--sample", choices=sorted(SAMPLES))
        p.add_argument("--out", default=str(DEFAULT_OUT))
        p.add_argument("--workers", type=int, default=MAX_WORKERS)
        p.add_argument("--blender")
        p.add_argument("--poses", help="v1 (default) or a comma list (bind, Clip@0.5, mount:<id>)")

    masks = sub.add_parser("masks", help="ray cast and write mask files")
    common(masks)
    masks.add_argument("--directions", type=int)
    masks.add_argument("--spacing-m", dest="spacing_m", type=float)
    masks.add_argument("--max-subdivision", dest="max_subdivision", type=int)
    masks.add_argument("--margin", type=float, default=DEFAULT_MARGIN_M)
    masks.add_argument("--margin-rule", choices=MARGIN_RULES, default=DEFAULT_MARGIN_RULE)
    masks.add_argument("--force", action="store_true")
    masks.add_argument("--e4", nargs="*", help="E4 vis_*.json files to compare with")
    masks.set_defaults(func=command_masks)

    final = sub.add_parser("finalise", help="rewrite mask files from cached visibility (no Blender)")
    common(final)
    final.add_argument("--margin", type=float, default=DEFAULT_MARGIN_M)
    final.add_argument("--margin-rule", choices=MARGIN_RULES, default=DEFAULT_MARGIN_RULE)
    final.add_argument("--e4", nargs="*", help="E4 vis_*.json files to compare with")
    final.set_defaults(func=command_finalise)

    review = sub.add_parser("review", help="changed-pixel validation and contact sheets")
    common(review)
    review.add_argument("--views", type=int, default=16, help="random camera directions per pose")
    review.add_argument("--pixel", type=float, default=0.003, help="pixel size in metres")
    review.add_argument("--seed", type=int, default=20261102)
    review.add_argument("--sheets", action="store_true", help="contact sheets for the sheet sample")
    review.add_argument("--e4-masks", help="folder of E4 <stem>__<lining>.mask files")
    review.set_defaults(func=command_review)

    check = sub.add_parser("check", help="validate a mask file against its garment")
    check.add_argument("mask")
    check.add_argument("glb", nargs="?")
    check.add_argument("--rewritten", action="store_true",
                       help="the garment's bytes were rewritten after the cast (a build tree): "
                            "bind by triangle count, index digest and check centroids, not SHA-256")
    check.set_defaults(func=command_check)

    args = parser.parse_args(argv)
    if getattr(args, "workers", 1) > MAX_WORKERS:
        parser.error(f"--workers is limited to {MAX_WORKERS}")
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
