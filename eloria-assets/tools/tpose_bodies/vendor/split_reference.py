"""Split a race body's fused mesh into the named appearance surfaces.

The runtime's appearance system tints and toggles by mesh-node name --
``body``, ``eyes``, ``hair``, ``wardrobe_shirt``, ``wardrobe_pants``,
``wardrobe_boots`` -- but the luminous bodies ship as one fused primitive
called ``char1``, so the skin, eye and head options match nothing, the
built-in hair cannot be hidden under a chosen style, and the painted
outfit cannot be recoloured.

The split shares every vertex attribute: each surface becomes its own
mesh node carrying the SAME position/normal/uv/skin accessors and only
its own index buffer, so the geometry is bit-identical and the fitter's
measurements do not move.  Faces are classified by the texel under their
UV centroid plus height priors.  The wardrobe surfaces get a grayscale
copy of the texture so the runtime's albedo colour multiplies into true
cloth colours; a plain band and cap are generated for the head styles
the runtime already knows how to toggle.

Usage:
    python split_race_surfaces.py [--race luminous_male] [--calibrate]
"""
from __future__ import annotations

import argparse
import io
import json
import struct
import sys
from pathlib import Path

import numpy as np
from PIL import Image

TOOLS = Path(__file__).resolve().parent
RACES = (TOOLS.parent.parent / "godot-client" / "assets" / "actors"
         / "native" / "races")

CLASSES = ("body", "eyes", "hair", "wardrobe_shirt", "wardrobe_pants",
           "wardrobe_boots", "skin_accent")
EYE_COLOUR_OUTLIER_PERCENT = 8
ISLAND_MAX_FACES = 100
CLASS_COLOURS = {
    "body": (205, 170, 140), "eyes": (0, 255, 255), "hair": (255, 0, 255),
    "wardrobe_shirt": (40, 160, 220), "wardrobe_pants": (60, 60, 200),
    "wardrobe_boots": (200, 120, 40),
}


def read_glb(path: Path):
    data = path.read_bytes()
    assert data[:4] == b"glTF", path
    json_len, json_type = struct.unpack_from("<I4s", data, 12)
    assert json_type == b"JSON"
    document = json.loads(data[20:20 + json_len])
    binary = bytearray(data[20 + json_len:])
    assert binary[4:7] == b"BIN"
    return document, binary


def write_glb(path: Path, document, binary) -> None:
    struct.pack_into("<I", binary, 0, len(binary) - 8)
    payload = json.dumps(document, separators=(",", ":")).encode()
    payload += b" " * (-len(payload) % 4)
    out = bytearray(b"glTF")
    out += struct.pack("<II", 2, 12 + 8 + len(payload) + len(binary))
    out += struct.pack("<I4s", len(payload), b"JSON")
    out += payload
    out += binary
    path.write_bytes(bytes(out))


def accessor_array(document, binary, index):
    acc = document["accessors"][index]
    view = document["bufferViews"][acc["bufferView"]]
    comp = {5121: np.uint8, 5123: np.uint16, 5125: np.uint32,
            5126: np.float32}[acc["componentType"]]
    n = {"SCALAR": 1, "VEC2": 2, "VEC3": 3, "VEC4": 4,
         "MAT4": 16}[acc["type"]]
    offset = 8 + view.get("byteOffset", 0) + acc.get("byteOffset", 0)
    raw = np.frombuffer(bytes(binary[offset:offset
                                     + acc["count"] * n * np.dtype(comp).itemsize]),
                        dtype=comp)
    out = raw.reshape(acc["count"], n).astype(np.float64)
    if acc.get("normalized"):
        out = out / np.iinfo(comp).max
    return out


def append_view(document, binary, payload: bytes, target=None) -> int:
    while len(binary) % 4:
        binary.append(0)
    offset = len(binary) - 8
    binary.extend(payload)
    view = {"buffer": 0, "byteOffset": offset, "byteLength": len(payload)}
    if target:
        view["target"] = target
    document["bufferViews"].append(view)
    return len(document["bufferViews"]) - 1


def append_accessor(document, binary, array, ctype, atype,
                    target=None) -> int:
    payload = np.ascontiguousarray(array).tobytes()
    view = append_view(document, binary, payload, target)
    accessor = {"bufferView": view, "componentType": ctype,
                "count": int(len(array)), "type": atype}
    if atype == "VEC3" and ctype == 5126:
        accessor["min"] = [float(v) for v in array.min(axis=0)]
        accessor["max"] = [float(v) for v in array.max(axis=0)]
    document["accessors"].append(accessor)
    return len(document["accessors"]) - 1


def overwrite_accessor(document, binary, index: int, array: np.ndarray) -> None:
    """Overwrite an existing accessor's data in place, same count/dtype/width.

    Same buffer-addressing math as ``accessor_array``'s read, run in
    reverse, so that nothing else in the buffer moves -- every other
    accessor, including the OTHER split primitives that share this one,
    stays valid with no renumbering.
    """
    acc = document["accessors"][index]
    view = document["bufferViews"][acc["bufferView"]]
    comp = {5121: np.uint8, 5123: np.uint16, 5125: np.uint32,
            5126: np.float32}[acc["componentType"]]
    n = {"SCALAR": 1, "VEC2": 2, "VEC3": 3, "VEC4": 4,
         "MAT4": 16}[acc["type"]]
    offset = 8 + view.get("byteOffset", 0) + acc.get("byteOffset", 0)
    packed = np.ascontiguousarray(array, dtype=comp)
    assert packed.shape == (acc["count"], n), (packed.shape, acc["count"], n)
    raw = packed.tobytes()
    binary[offset:offset + len(raw)] = raw
    if n == 3 and comp == np.float32:
        acc["min"] = [float(v) for v in array.min(axis=0)]
        acc["max"] = [float(v) for v in array.max(axis=0)]


def smooth_normals(positions: np.ndarray, indices: np.ndarray,
                    crease_deg: float = 100.0) -> np.ndarray:
    """Re-average vertex normals within each crease-angle-limited group.

    Checked directly: the shirt's duplicate-position vertices (the ones the
    exporter split apart, at the SAME 3D point) disagree in normal
    direction across a broad, near-continuous spread from 0 to 180 degrees
    -- not a small handful of deliberate hard edges among otherwise-smooth
    duplicates. That is a mesh that was never smooth-shaded to begin with,
    not something the surface split introduced: the split (see the module
    docstring) copies the source's own POSITION/NORMAL accessors into every
    class primitive UNCHANGED, so it cannot have moved a single normal.
    Blender's viewport and Godot's own import-preview both light with
    soft, non-shadow-casting fill, so this pre-existing per-facet noise is
    invisible there; the character-creation screen's raking, shadow-casting
    key light (main.tscn's KeyLight) turns every one of those facets into a
    crisp self-shadowed line -- confirmed by re-rendering the same camera
    with that light's shadow turned off, which removes nearly all of it.

    Re-averaging by POSITION rather than by vertex index is what actually
    reunites duplicates the exporter treats as separate vertices into the
    one surface point they really are. A high crease-angle cap still keeps
    this from smoothing over the rare duplicate that is genuinely two
    surfaces meeting at an open boundary loop (a collar or cuff rim's
    outer and inner shell, close to 180 degrees apart) rather than a
    spurious split of one continuous face -- averaging those would produce
    a degenerate, near-zero normal instead of preserving either surface.
    """
    faces = indices.reshape(-1, 3).astype(np.int64)
    v0, v1, v2 = positions[faces[:, 0]], positions[faces[:, 1]], positions[faces[:, 2]]
    face_normals = np.cross(v1 - v0, v2 - v0)
    lengths = np.maximum(np.linalg.norm(face_normals, axis=1, keepdims=True), 1e-12)
    unit_face_normals = face_normals / lengths

    position_groups = {}
    for i, key in enumerate(map(tuple, np.round(positions, 4))):
        position_groups.setdefault(key, []).append(i)

    vertex_faces = {}
    for f, (a, b, c) in enumerate(faces):
        vertex_faces.setdefault(int(a), []).append(f)
        vertex_faces.setdefault(int(b), []).append(f)
        vertex_faces.setdefault(int(c), []).append(f)

    cos_thresh = np.cos(np.radians(crease_deg))
    out = np.array(positions, copy=True) * 0.0
    for idxs in position_groups.values():
        group_faces = sorted({f for i in idxs for f in vertex_faces.get(i, [])})
        if not group_faces:
            continue
        group_fn = unit_face_normals[group_faces]
        group_fw = face_normals[group_faces]
        for i in idxs:
            own_faces = vertex_faces.get(i)
            if not own_faces:
                continue
            own_ref = face_normals[own_faces].sum(axis=0)
            own_norm = np.linalg.norm(own_ref)
            if own_norm < 1e-12:
                continue
            own_ref = own_ref / own_norm
            mask = (group_fn @ own_ref) >= cos_thresh
            accum = group_fw[mask].sum(axis=0)
            accum_norm = np.linalg.norm(accum)
            out[i] = accum / accum_norm if accum_norm > 1e-12 else own_ref
    return out.astype(np.float32)


def resmooth_shared_surfaces(document, binary) -> int:
    """Recompute and overwrite the shared body/wardrobe NORMAL accessor.

    Runs on an already-split (v14) file. The class primitives still all
    point at the ORIGINAL mesh's shared POSITION/NORMAL accessors -- that
    sharing is the whole point of the split -- so finding the one NORMAL
    accessor those primitives use, rebuilding it from ALL of their faces
    combined, and overwriting it in place reaches every split surface
    through the accessor they still share, exactly as if this had run
    before the class split instead of after.
    """
    shared_nodes = [n for n in document["nodes"]
                    if n.get("name") in CLASSES and "mesh" in n]
    if not shared_nodes:
        return 0
    prims = [document["meshes"][n["mesh"]]["primitives"][0] for n in shared_nodes]
    position_acc = prims[0]["attributes"]["POSITION"]
    normal_acc = prims[0]["attributes"]["NORMAL"]
    assert all(p["attributes"]["POSITION"] == position_acc for p in prims)
    assert all(p["attributes"]["NORMAL"] == normal_acc for p in prims)
    positions = accessor_array(document, binary, position_acc)
    all_indices = np.concatenate([
        accessor_array(document, binary, p["indices"]).reshape(-1).astype(np.int64)
        for p in prims])
    smoothed = smooth_normals(positions, all_indices)
    overwrite_accessor(document, binary, normal_acc, smoothed)
    return int(len(np.unique(all_indices)))


def largest_component_per_side(face_indices: np.ndarray, faces: np.ndarray,
                               positions: np.ndarray,
                               side: np.ndarray) -> np.ndarray:
    """Keep only the largest position-connected group of faces per side.

    ``side`` is a boolean array over ALL faces (True/False, e.g. x >= 0)
    splitting candidates into left/right before grouping, so a same-size
    stray fragment on one side can never be mistaken for the other eye.
    Connectivity is by shared 3D position rather than shared vertex INDEX
    -- this mesh duplicates vertices at UV/normal seams (see
    smooth_normals), so two triangles that visibly touch often do not
    share an index, only a position. The same union-find add_scalp
    already uses for its own connected pieces, scoped to just the
    candidate faces so an unrelated face elsewhere can't bridge two
    fragments into one.
    """
    if len(face_indices) == 0:
        return face_indices
    position_id = {}
    def pid(vertex_index):
        key = tuple(np.round(positions[vertex_index], 4))
        return position_id.setdefault(key, len(position_id))

    parent = {}
    def find(a):
        while parent.setdefault(a, a) != a:
            parent[a] = parent[parent[a]]
            a = parent[a]
        return a
    def union(a, b):
        ra, rb = find(a), find(b)
        if ra != rb:
            parent[ra] = rb

    for face_index in face_indices:
        a, b, c = (pid(v) for v in faces[face_index])
        union(a, b)
        union(b, c)

    kept = []
    for side_value in (True, False):
        side_faces = [f for f in face_indices if bool(side[f]) == side_value]
        if not side_faces:
            continue
        groups = {}
        for face_index in side_faces:
            root = find(pid(faces[face_index][0]))
            groups.setdefault(root, []).append(face_index)
        kept.extend(max(groups.values(), key=len))
    return np.array(kept, dtype=face_indices.dtype)


def absorb_small_islands(faces: np.ndarray, positions: np.ndarray,
                         labels: np.ndarray,
                         target_labels: tuple) -> np.ndarray:
    """Fold small, disconnected fragments of target_labels into whichever
    label actually borders them.

    "Keep only the single largest piece per label" -- the rule that
    cleaned up the eyes -- is the WRONG rule for body/wardrobe: a real
    boot or hand is naturally its own connected piece (left and right
    are never vertex-connected to each other or to the torso, and even
    one boot can split into an upper-cuff piece and a lower-foot piece
    across a seam), so that rule would discard both hands and every
    boot but one. Checked directly (component sizes dumped per label on
    both bodies): what actually marks a piece as a stray -- like the
    sliver of "wardrobe_pants" colour that re-registers down at the
    sole, inside boot territory, and shows up as a red patch through
    the boot once pants are tinted, or the handful of "wardrobe_shirt"
    triangles that land out at the wrist -- is that a real anatomical
    piece runs to the hundreds of triangles (both hands: 749-793 on the
    female body; both boots: 238-750) while a stray runs to the tens
    (in the same dump: 6-83). ISLAND_MAX_FACES sits in the gap between
    those two populations. Below it, a fragment is relabelled to
    whichever OTHER label is most common among the faces actually
    touching it (by shared position, not shared vertex index, for the
    same reason largest_component_per_side uses position); at or above
    it, left alone even when it is not that label's largest piece.
    """
    position_id = {}
    def pid(vertex_index):
        key = tuple(np.round(positions[vertex_index], 4))
        return position_id.setdefault(key, len(position_id))

    face_pids = [tuple(pid(v) for v in f) for f in faces]
    position_faces = {}
    for face_index, face_pid in enumerate(face_pids):
        for p in face_pid:
            position_faces.setdefault(p, []).append(face_index)

    new_labels = labels.copy()
    for target in target_labels:
        member = np.flatnonzero(labels == target)
        if len(member) == 0:
            continue
        member_set = set(int(i) for i in member)
        parent = {}
        def find(a):
            while parent.setdefault(a, a) != a:
                parent[a] = parent[parent[a]]
                a = parent[a]
            return a
        def union(a, b):
            ra, rb = find(a), find(b)
            if ra != rb:
                parent[ra] = rb
        for face_index in member:
            for p in face_pids[face_index]:
                for other in position_faces[p]:
                    if other in member_set:
                        union(int(face_index), other)
        groups = {}
        for face_index in member:
            groups.setdefault(find(int(face_index)), []).append(int(face_index))
        for pieces in groups.values():
            if len(pieces) >= ISLAND_MAX_FACES:
                continue
            neighbour_labels = []
            for face_index in pieces:
                for p in face_pids[face_index]:
                    for other in position_faces[p]:
                        if other not in member_set:
                            neighbour_labels.append(labels[other])
            if neighbour_labels:
                values, counts = np.unique(neighbour_labels, return_counts=True)
                winner = values[np.argmax(counts)]
                for face_index in pieces:
                    new_labels[face_index] = winner
    return new_labels


def bone_rest_y(document, binary, skin_index: int, joint_name: str) -> float:
    """A joint's own rest-pose Y, in this mesh's coordinate space.

    Every body on the common skeleton binds to the identical rig, so
    this is an anchor for "where a body part is" that does not depend
    on THIS body's own sculpt -- unlike a fraction of the whole mesh's
    Y span, which silently assumes every body divides up the same way
    top to bottom. That held for the bald, average-proportioned
    Luminous pilot but breaks for a body whose concept art gives it
    horns (a fraction-of-total-height band lands on the horns instead
    of the head) or, measured directly on Ssarathi, legs whose own
    thigh-to-calf bone is barely three quarters the length of every
    other common-skeleton body's own -- the fixed 0.30-0.50 "pants"
    band no longer lands anywhere near mid-thigh, so it samples
    whatever else is at that height instead (see classify()'s pants
    fallback).
    """
    skin = document["skins"][skin_index]
    joints_list = skin["joints"]
    names = [document["nodes"][j].get("name", "") for j in joints_list]
    ibms = accessor_array(document, binary, skin["inverseBindMatrices"])
    row = names.index(joint_name)
    ibm = np.asarray(ibms[row], dtype=np.float64).reshape(4, 4).T
    return float(np.linalg.inv(ibm)[1, 3])


def bone_rest_position(document, binary, skin_index: int, joint_name: str) -> np.ndarray:
    """A joint's full rest-pose position (see bone_rest_y for the same
    thing in Y alone). Used where a Y band alone cannot tell a leg's own
    geometry apart from something else that happens to pass through the
    same height -- Ssarathi's tail runs alongside the upper leg for a
    while rather than staying behind it, so any Y-only band at hip-to-
    knee height samples a mix of both; distance to the thigh-to-calf
    bone's own 3D axis (see classify()'s pants fallback) does not."""
    skin = document["skins"][skin_index]
    names = [document["nodes"][j].get("name", "") for j in skin["joints"]]
    ibms = accessor_array(document, binary, skin["inverseBindMatrices"])
    row = names.index(joint_name)
    ibm = np.asarray(ibms[row], dtype=np.float64).reshape(4, 4).T
    return np.linalg.inv(ibm)[:3, 3]


def head_bone_y(document, binary, skin_index: int) -> float:
    return bone_rest_y(document, binary, skin_index, "Head")


#: (near joint, far joint) for every non-finger limb/torso/head segment,
#: used to find geometry that belongs to none of them -- see classify()'s
#: tail exclusion.
BODY_SEGMENTS = (
    ("pelvis", "spine_01"), ("spine_01", "spine_02"), ("spine_02", "spine_03"),
    ("spine_03", "neck_01"), ("neck_01", "Head"),
    ("spine_03", "clavicle_l"), ("clavicle_l", "upperarm_l"),
    ("upperarm_l", "lowerarm_l"), ("lowerarm_l", "hand_l"), ("hand_l", "middle_02_l"),
    ("spine_03", "clavicle_r"), ("clavicle_r", "upperarm_r"),
    ("upperarm_r", "lowerarm_r"), ("lowerarm_r", "hand_r"), ("hand_r", "middle_02_r"),
    ("pelvis", "thigh_l"), ("thigh_l", "calf_l"), ("calf_l", "foot_l"), ("foot_l", "ball_l"),
    ("pelvis", "thigh_r"), ("thigh_r", "calf_r"), ("calf_r", "foot_r"), ("foot_r", "ball_r"),
)


def classify(positions, uvs, indices, texture: Image.Image,
            document, binary, skin_index: int):
    """Boots/pants/shirt/skin by nearest colour to a per-body sample of
    each; eyes by geometry.

    The original version thresholded absolute Y and a "teal" hue tuned to
    one body's blue-green shirt -- and both assumptions broke on the
    common-skeleton redraw art (Luminous Human, and the races still to
    come on the same skeleton): the male shirt here is off-white, not
    teal, and a garment's OWN height range is not a narrow band -- a
    sleeve runs from the shoulder down past the hip, overlapping pants'
    Y range while still being shirt-coloured.  A first version that kept
    Y as the classifier (proportional this time, not absolute) still put
    every sleeve and cuff in "body" for exactly that reason: the sleeve's
    centroids scatter across the whole torso-to-hip range, and no single
    band contains them.

    What generalises across both colour schemes AND that shape problem is
    colour distance to a small set of reference colours -- but sampled
    from THIS body, not hard-coded, because the palette differs per race.
    Each reference is the median texel colour in the middle of a Y-band
    that is unambiguous by construction (boots at the ankle, pants at
    mid-thigh, shirt at mid-chest, skin at the crown of the head, all
    picked well clear of any seam); every face then goes to whichever
    reference it is nearest, with no Y restriction on the match itself,
    so a shirt-coloured sleeve at hip height still reads as shirt.

    Eyes are a handful of triangles on a body this low-poly, and "most
    forward" geometry alone does not find them: sweeping the most-forward
    Z across fine Y slices up the face finds one continuous ridge (nose
    tip, then brow), centred on X in every slice -- this low-poly a
    sculpt has no eye socket concavity distinguishing eyes from the nose
    or brow ridge, so "forward-facing" just picks whichever of those a
    Y-band happens to contain, which is how a first version coloured half
    the face.  What does hold, measured on both Luminous Human bodies:
    eyes sit ABOVE the nose tip -- the actual most-forward point of the
    head, found by that same Y-sweep -- as two lobes symmetric about the
    face's own centreline.  Anthropometric, not discovered per body, but
    expressed as a fraction of THIS head's own vertical span so it scales
    with head size rather than assuming one body's absolute measurements.

    That geometric zone is only a coarse net, though: checked directly
    (Godot's own import preview, isolating the "eyes" primitive) there
    IS a real painted eye -- iris, pupil, sclera -- sitting in a small
    UV island, but most of the zone's triangles are the plain-skin eyelid
    and brow around it, so classifying the whole zone as "eyes" pulled in
    far more skin than eye.  What separates the two within the zone is
    colour: the painted eye is nowhere near this body's skin tone, while
    the surrounding eyelid triangles ARE that skin tone almost by
    definition. So the zone is sampled for its own local skin reference
    (median of everything in it, since skin is the overwhelming
    majority) and only the zone's outliers -- far enough from that local
    reference -- keep the "eyes" label; the rest fall back to "body".

    That colour outlier test still keeps a few triangles that are far
    from skin for an unrelated reason -- a UV chart border sampled at the
    face centroid, a stray fold catching a highlight -- and, checked
    directly by tinting the classified "eyes" primitive a saturated
    colour in the live creation preview, those show up as small jagged
    wedges disconnected from the eye itself, not touching it at any
    shared vertex. The real eye is one connected patch of geometry (per
    side), so the fix is connectivity, not a better colour rule: group
    the colour-selected triangles by shared position into left/right
    sides, keep only the largest connected piece on each side, and
    return the rest to "body". Measured on both Luminous Human bodies,
    the true eye is always the largest piece by a wide margin -- the
    female zone's outliers split into two 47-48 triangle eyes plus eight
    fragments of 8 or fewer.
    """
    tex = np.asarray(texture.convert("RGB")).astype(np.float64) / 255.0
    height, width = tex.shape[:2]
    faces = indices.reshape(-1, 3)
    centroids = positions[faces].mean(axis=1)
    head_anchor = bone_rest_y(document, binary, skin_index, "Head")
    leg_axes = [(bone_rest_position(document, binary, skin_index, "thigh_%s" % side),
                bone_rest_position(document, binary, skin_index, "calf_%s" % side))
               for side in ("l", "r")]
    uv = uvs[faces].mean(axis=1)
    px = np.clip((uv[:, 0] % 1.0) * (width - 1), 0, width - 1).astype(int)
    py = np.clip((uv[:, 1] % 1.0) * (height - 1), 0, height - 1).astype(int)
    rgb = tex[py, px]
    y, x, z = centroids[:, 1], centroids[:, 0], centroids[:, 2]
    span = float(y.max() - y.min())
    frac = (y - y.min()) / span if span > 1e-9 else np.zeros_like(y)

    def band_colour(lo, hi):
        sel = (frac >= lo) & (frac < hi)
        return np.median(rgb[sel], axis=0) if sel.any() else None

    # The middle third of each unambiguous band, well clear of the
    # transition seams measured on both Luminous Human bodies (boots/pants
    # at 0.17-0.22, pants/shirt at 0.57-0.61, shirt/skin at 0.74-0.87).
    references = {
        "wardrobe_boots": band_colour(0.04, 0.14),
        "wardrobe_pants": band_colour(0.30, 0.50),
        "wardrobe_shirt": band_colour(0.63, 0.72),
        "body": band_colour(0.92, 0.98),
    }
    # The 0.30-0.50 pants band assumes legs make up roughly the same share
    # of total height on every body -- checked directly, Ssarathi's own
    # thigh-to-calf bone is barely three quarters the length of every
    # other common-skeleton body's, so that fraction no longer lands on
    # mid-thigh at all; it samples whatever else is at that height
    # instead (tail and hip skin, close enough to this body's own "body"
    # reference that the ACTUAL pants fabric -- measured directly, a
    # warm dark brown nothing like either reference -- voted for "shirt"
    # rather than "pants"). A pants reference this close to skin is the
    # signal that it sampled skin, not a low-contrast wardrobe on
    # purpose: checked directly against all 16 bodies, the two Ssarathi
    # ones are 0.10-0.13 apart here, every other body 0.29 or more.
    #
    # The fallback anchors to the thigh-to-calf bone's own 3D axis, not
    # just its Y range: checked directly, a Y-band restricted to that
    # same joint span still returned the contaminated colour, because
    # Ssarathi's tail runs alongside the upper leg for a stretch rather
    # than staying behind it -- same height, so a Y-only band cannot
    # separate them. Distance to the bone's own axis can: restricted to
    # within 0.12 m of it (comfortably past the leg's own measured
    # girth, see thicken_limbs.py) and the middle 40% of the segment
    # (clear of hip and knee creases), both legs agree on the same warm
    # brown regardless of radius threshold tried between 0.08 and 0.15 m.
    if (references["wardrobe_pants"] is not None and references["body"] is not None
            and np.linalg.norm(references["wardrobe_pants"] - references["body"]) < 0.15):
        thigh_samples = []
        for thigh_pos, calf_pos in leg_axes:
            axis = calf_pos - thigh_pos
            axis_len = np.linalg.norm(axis)
            if axis_len < 1e-6:
                continue
            unit = axis / axis_len
            v = centroids - thigh_pos
            t = v @ unit
            perp = v - np.outer(t, unit)
            radius = np.linalg.norm(perp, axis=1)
            sel = (t >= 0.3 * axis_len) & (t <= 0.7 * axis_len) & (radius < 0.12)
            if sel.any():
                thigh_samples.append(rgb[sel])
        if thigh_samples:
            references["wardrobe_pants"] = np.median(
                np.concatenate(thigh_samples, axis=0), axis=0)
    # The crown alone is not always a big enough sample of "skin": checked
    # directly on Whitehorn Votary, whose shirt and skin are both pale
    # (0.29 apart, versus 0.85 on Luminous), the hand -- reliably bare
    # skin too, out at the T-pose's own wingspan -- reads as a colour
    # 0.16 from the crown but only 0.14 from the shirt, so the whole hand
    # (thousands of triangles, not a handful a size-based cleanup could
    # absorb) voted for "shirt". A patch of confirmed-correct jaw skin
    # measured the same way reads closer to the hand than the crown too
    # (baked shading, not a UV or geometry bug -- checked directly by
    # comparing a confirmed-correct patch of chin skin against known
    # crown and hand samples). Whatever bakes into this body's skin
    # shading differently in different places, one blended midpoint
    # does not represent either extreme it was built from. Keeping the
    # crown and hand as TWO SEPARATE anchors for "body" -- instead of
    # averaging them into one colour -- lets a face match whichever one
    # it actually resembles; checked directly, this alone recovers
    # 1500+ of Whitehorn Votary's jaw faces with no extra sampling, and
    # changes under 10 faces total across both Luminous bodies (isolated
    # single triangles at the mesh's own top/bottom extremes, the kind
    # absorb_small_islands (below) already cleans up regardless of which
    # side they land on).
    names, colours = [], []
    for name, colour in references.items():
        if name != "body" and colour is not None:
            names.append(name)
            colours.append(colour)
    if references["body"] is not None:
        names.append("body")
        colours.append(references["body"])
    wingspan = float(np.abs(x).max())
    hand_sel = np.abs(x) > 0.7 * wingspan
    if hand_sel.any():
        names.append("body")
        colours.append(np.median(rgb[hand_sel], axis=0))
    # The same baked-shading gap shows up between two WARDROBE classes
    # too, not just body-vs-shirt: checked directly on Glasswarden
    # Female, the sleeve cuff -- just inboard of the hand, at 0.50-0.68
    # of the model's own wingspan -- reads noticeably darker than the
    # torso sample "wardrobe_shirt" was built from (0.63-0.72 of mesh
    # height, chest-level), and by coincidence that darker shade sits
    # closer to THIS body's own pants reference than to its own shirt
    # one, so the cuff voted for "pants" ("pants mixed in the shirt").
    # A second, cuff-level anchor for "wardrobe_shirt" fixes it the same
    # way the hand anchor fixed skin, but the cuff band is not always
    # sleeve: checked directly on Mycelari Female it is half bare
    # forearm, and on both Ssarathi bodies it is a three-way mix with
    # pants, because those bodies' own proportions or rest pose put the
    # wrist somewhere else. Rather than guess a narrower band per body,
    # gate the anchor on the sample's own colour spread -- a sleeve is
    # one material and reads as a tight cluster (spread under 0.024 on
    # the 13 bodies checked directly where this band is clean); a band
    # that is actually straddling two different materials reads far
    # looser (0.198-0.573 on the 3 checked directly where it is not).
    # 0.05 sits in the wide gap between those two populations.
    cuff_sel = (np.abs(x) > 0.50 * wingspan) & (np.abs(x) <= 0.68 * wingspan)
    if references["wardrobe_shirt"] is not None and cuff_sel.sum() > 20:
        cuff_colour = np.median(rgb[cuff_sel], axis=0)
        cuff_spread = float(np.median(
            np.linalg.norm(rgb[cuff_sel] - cuff_colour, axis=1)))
        if cuff_spread < 0.05:
            names.append("wardrobe_shirt")
            colours.append(cuff_colour)
    labels = np.full(len(faces), "body", dtype=object)
    if colours:
        palette = np.stack(colours)
        dist = np.linalg.norm(rgb[:, None, :] - palette[None, :, :], axis=2)
        nearest = np.argmin(dist, axis=1)
        for i, name in enumerate(names):
            labels[nearest == i] = name

    # Boots and pants are not always a shading gap like the two above --
    # checked directly on Orun Male, EVERY 0.04-wide slice of mesh height
    # from the sole (0.00) up through mid-thigh (0.50) reads the same
    # dark brown, [50-57, 33-39, 23-26], so their reference samples land
    # only 0.03 apart (versus 0.10-0.24 on every other body checked) and
    # the colour vote has nothing real to key off between them: tinting
    # each a saturated colour in the live preview showed a jagged,
    # interleaved speckle up the whole shin, not a clean seam. No colour
    # fix can separate two regions that are the same colour, but boots
    # and pants do not need one -- unlike skin and a collar, a boot is
    # never above a knee on this rig, so the split is just Y position.
    # 0.22 is not a guess: it is where Luminous's own boots/pants seam
    # already measures (see the reference-band comment above), reused
    # here as the ordinary case for this rig rather than a new number.
    # Gating on the two references' own distance -- not on this body by
    # name -- means only a pair this close ever gets overridden by
    # position: every other body's boots and pants, including the
    # closest of the rest at 0.05, are left on the colour vote that
    # already works for them.
    boots_ref, pants_ref = references["wardrobe_boots"], references["wardrobe_pants"]
    if (boots_ref is not None and pants_ref is not None
            and np.linalg.norm(boots_ref - pants_ref) < 0.04):
        ambiguous = (labels == "wardrobe_boots") | (labels == "wardrobe_pants")
        labels[ambiguous & (frac < 0.22)] = "wardrobe_boots"
        labels[ambiguous & (frac >= 0.22)] = "wardrobe_pants"

    # Nearest-reference-colour is a per-face vote with no notion of its
    # neighbours, so a handful of faces near a seam -- a fold's shading,
    # a sliver of sole geometry that registers as pants-coloured -- vote
    # for the WRONG side of it. Absorb those into whichever real region
    # actually surrounds them before eyes (below) carves its own labels
    # out of "body"; see absorb_small_islands for why this is a size
    # threshold and not "keep the biggest piece".
    labels = absorb_small_islands(
        faces, positions, labels,
        ("body", "wardrobe_shirt", "wardrobe_pants", "wardrobe_boots"))

    # Eyes: two lobes, symmetric about centre. The search is bounded to a
    # window around the skeleton's own Head joint (head_anchor) rather
    # than a fraction of the whole mesh's height -- a fraction assumes
    # nothing sits above the head, which held for the bald Luminous
    # pilot but not for a body whose concept art gives it horns: checked
    # directly on Whitehorn Votary, the old "top 20% of total height"
    # band landed mostly ON the horns ("eyes" ending up ON a horn was
    # never a colour bug; it was this). HEAD_LO_OFFSET/HEAD_HI_OFFSET
    # are metres from the joint, not a fraction, deliberately: a head is
    # much the same size regardless of how tall the rest of the body is.
    #
    # The window is wide on both sides because the joint's OWN position
    # relative to the face turned out not to be consistent enough to
    # trim it tighter: checked directly, Whitehorn Votary's nose tip
    # sits 1.5-2.5 cm BELOW its Head joint, while both Luminous bodies'
    # sit 7.5-9 cm ABOVE theirs -- over 10 cm of spread from a single
    # other body, from what should be the same joint on the same rig. A
    # first version bounded this at +0.025 specifically (comfortably
    # below both Luminous noses) and it silently cost Whitehorn Votary
    # its own nose entirely: every slice inside that window was still on
    # the rising side of the true peak, so the sweep below just kept
    # picking the window's own lower edge, and everything downstream
    # inherited a nose position that was never a real local maximum.
    # -0.10 clears that with margin; +0.20 stays short of where Whitehorn
    # Votary's horns start mattering (measured past +0.24).
    HEAD_LO_OFFSET, HEAD_HI_OFFSET = -0.10, 0.20
    head = ((y >= head_anchor + HEAD_LO_OFFSET)
            & (y <= head_anchor + HEAD_HI_OFFSET))
    if head.any():
        head_lo, head_hi = float(y[head].min()), float(y[head].max())
        head_span = head_hi - head_lo
        if head_span > 1e-9:
            # Within that window, WHERE the eyes actually sit is anchored
            # to the nose tip, not to a fraction of the window itself:
            # checked directly, the Head joint's own position relative to
            # the face varies far more across bodies (2.5-9 cm to the
            # nose tip, Whitehorn Votary vs both Luminous bodies) than
            # the nose-to-eye distance does on a face (3.7-3.8 cm on
            # both Luminous bodies, despite one having a visibly bigger
            # head span than the other) -- the joint's placement is an
            # artefact of how each concept image happened to generate,
            # the nose-to-eye gap is an actual facial proportion. Find
            # it the same way the old fraction was originally measured:
            # sweep max Z (most forward) across 1 cm Y-slices within the
            # head window near the centreline, and take the Y of
            # whichever slice reaches furthest forward.
            near_axis = np.abs(x) < 0.06
            slice_lo = np.floor(head_lo * 100) / 100
            nose_y, nose_z = head_lo, -1e9
            for edge in np.arange(slice_lo, head_hi, 0.01):
                sel = head & near_axis & (y >= edge) & (y < edge + 0.01)
                if sel.any():
                    z_max = float(z[sel].max())
                    if z_max > nose_z:
                        nose_z, nose_y = z_max, edge + 0.005
            eye_level = (y >= nose_y + 0.017) & (y < nose_y + 0.057)
            # gap/half-width stay fractions of head_span, which still
            # scales with this body's own head size regardless of how
            # its eye level was found. Checked directly against the real
            # eye's own X on both Luminous bodies, it sits at 0.10-0.29
            # of head_span depending on body and side -- the two genders
            # alone span nearly that whole range, so this stays wide
            # enough to hold either. The colour and connected-component
            # filters below are what actually finds the eye inside this
            # net; widening the net does not weaken them.
            gap = 0.05 * head_span
            half_width = 0.35 * head_span
            eye_zone = eye_level & (np.abs(x) >= gap) & (np.abs(x) < gap + half_width)
            # The zone is mostly eyelid/brow skin around a small painted
            # eye -- keep only the zone's own colour outliers, measured
            # against a reference sampled from the zone itself (its
            # median, since skin is the overwhelming majority there) so
            # this adapts to each body's own skin tone with no hard-coded
            # colour. The cut itself is a PERCENTILE of the zone's own
            # distance distribution, not a fixed absolute number: a fixed
            # 0.30 (tuned against Luminous, where the painted iris/pupil/
            # sclera sits 0.4-1.2 from its skin) was checked directly
            # against the other seven common-skeleton races and left two
            # of them with zero eye triangles -- Stoneborn's own skin is
            # a dark stone-grey, so a dark eye never reaches 0.30 away
            # from it (its zone tops out at 0.235); Votary's whole
            # palette is lower-contrast the same way (tops out at 0.290).
            # EYE_COLOUR_OUTLIER_PERCENT is chosen so this reproduces
            # Luminous's own already-verified result closely (checked by
            # re-rendering both Luminous bodies after the change): its
            # zone's outlier population thins out in the same 6-10% range
            # this percentile sits in, on both bodies.
            if eye_zone.any():
                # Each eye gets its own contrast threshold. One side's baked
                # lighting must not consume the other eye's entire budget.
                candidates = []
                for side in (x >= 0, x < 0):
                    side_zone = eye_zone & side
                    if not side_zone.any():
                        continue
                    zone_rgb = rgb[side_zone]
                    local_skin = np.median(zone_rgb, axis=0)
                    zone_dist = np.linalg.norm(zone_rgb - local_skin, axis=1)
                    zone_indices = np.flatnonzero(side_zone)
                    cut = np.percentile(zone_dist, 100 - EYE_COLOUR_OUTLIER_PERCENT)
                    candidates.extend(zone_indices[zone_dist >= cut])
                colour_outliers = np.asarray(candidates, dtype=int)
                # A handful of those outliers are far from skin for a
                # reason that has nothing to do with being an eye (a UV
                # chart border sampled at the face centroid, a stray
                # highlight) -- checked directly, by tinting the
                # classified primitive in the live preview, these show up
                # as small wedges disconnected from the eye itself. The
                # real eye is the largest connected piece on each side by
                # a wide margin, so keep only that.
                eye_faces = largest_component_per_side(
                    colour_outliers, faces, positions, x >= 0)
                labels[eye_faces] = "eyes"

    # A tail is not clothing, but the colour vote has no way to know
    # that: checked directly on Ssarathi, whichever of body/shirt/pants/
    # boots its own shading happens to land nearest keeps changing face
    # by face along its length (its base votes pants, most of its length
    # votes body, the male's tail-tip and most of the female's tail vote
    # boots) since none of the four references was ever sampled FROM a
    # tail. What is true regardless of colour: nothing on any of the
    # other 15 common-skeleton bodies sits more than 0.26 m from the
    # nearest point on its own limb/torso/head bone chain, while
    # Ssarathi's tail reaches 0.50-0.55 m -- it is not close to being
    # part of any of them. A cutoff at 0.30 m sits in that gap and forces
    # only genuinely orphaned geometry to "body": checked directly
    # against all 16 bodies, it fires a little on two others (Mycelari
    # Female, Whitehorn Votary Female) but only on faces the colour vote
    # already called "body", so it changes nothing there.
    min_dist = None
    for near, far in BODY_SEGMENTS:
        a = bone_rest_position(document, binary, skin_index, near)
        b = bone_rest_position(document, binary, skin_index, far)
        axis = b - a
        axis_len = np.linalg.norm(axis)
        unit = axis / axis_len
        v = centroids - a
        t = np.clip(v @ unit, -0.05, axis_len + 0.05)
        dist = np.linalg.norm(centroids - (a + np.outer(t, unit)), axis=1)
        min_dist = dist if min_dist is None else np.minimum(min_dist, dist)
    labels[min_dist > 0.30] = "body"
    # A customisable "secondary skin" surface for whichever body actually
    # has one: distinct from the generic 0.30 m safety net above so that
    # the two other bodies which cross THAT cutoff by a little (Mycelari
    # Female tops out at 0.351 m, Whitehorn Votary Female at 0.318 m) --
    # already "body" before this ran, so unaffected by it -- do not get
    # promoted to a whole new mesh node over a handful of stray faces.
    # 0.40 m sits clear of both while Ssarathi's tail, the only body that
    # actually reaches this, still clears it almost everywhere (measured
    # directly: 0.50-0.55 m at its own furthest point).
    labels[min_dist > 0.40] = "skin_accent"

    # The open, laced collar every common-skeleton shirt shares exposes a
    # triangle of chest skin -- but on every one of 12 bodies checked
    # directly, a meaningful share of the "body" faces framing that
    # triangle (30-84% of them) sit within a few millimetres of a
    # "wardrobe_shirt" face, which two genuinely separate surfaces do
    # not do; two nearly-coincident ones fighting for the same screen
    # pixel do (confirmed visually: a jagged, dithered fleck of both
    # colours at the notch on every body tinted and re-rendered, not a
    # clean edge). Reclassifying only the ones actually THIS close closes
    # the gap exactly where it is fighting -- both surfaces now render
    # the same colour, so the dithering between them stops being visible
    # -- without touching the genuinely separate, non-overlapping skin
    # elsewhere near the collar (jaw and neck above it) that was never
    # fighting anything. Restricted to near the centreline and above the
    # torso specifically so this cannot reach the sleeve cuffs or waist
    # hem, where skin sits close to a wardrobe surface for entirely
    # unrelated, correct reasons (see the shirt-cuff anchor above).
    collar_zone = ((np.abs(x) < 0.10) & (y < head_anchor)
                   & (y > head_anchor - 0.40) & (labels == "body"))
    shirt_positions = centroids[labels == "wardrobe_shirt"]
    if collar_zone.any() and len(shirt_positions):
        collar_indices = np.flatnonzero(collar_zone)
        # Pairwise distance in chunks -- collar_indices x shirt_positions
        # is at most a few thousand by a few thousand, comfortably small
        # for a dense numpy broadcast, no need for a spatial index.
        nearest = np.array([
            np.linalg.norm(shirt_positions - centroids[i], axis=1).min()
            for i in collar_indices])
        labels[collar_indices[nearest < 0.010]] = "wardrobe_shirt"

    return faces, labels


def reclassify_surfaces(document, binary) -> str:
    """Re-run full classification on an already-split file and repoint
    every existing class primitive at the result.

    classify() is what actually changes between migrations -- eye
    colour/connectivity, then absorb_small_islands for the wardrobe
    seams -- so this just re-derives every shared-surface face's label
    from scratch and moves faces between whichever of the EXISTING
    primitives changed. Only classes that already have a node are ever
    written to: a label classify() produces with nowhere to hold it
    would otherwise vanish silently, so that raises instead. Faces move
    by writing each primitive a freshly classified index accessor and
    repointing "indices" at it; the previous index accessors are left
    as orphaned, unreferenced buffer bytes, the same way add_scalp's
    v2->v14 migration leaves its old scalp accessors -- harmless in a
    GLB, and simpler than compacting the buffer.
    """
    by_name = {n["name"]: n for n in document["nodes"]
               if n.get("name") in CLASSES and "mesh" in n}
    first_prim = document["meshes"][next(iter(by_name.values()))["mesh"]]["primitives"][0]
    positions = accessor_array(document, binary, first_prim["attributes"]["POSITION"])
    uvs = accessor_array(document, binary, first_prim["attributes"]["TEXCOORD_0"])

    all_faces = []
    owners = []
    for name, n in by_name.items():
        prim = document["meshes"][n["mesh"]]["primitives"][0]
        idx = accessor_array(document, binary, prim["indices"]).reshape(-1).astype(np.uint32)
        all_faces.append(idx.reshape(-1, 3))
        owners += [name] * (len(idx) // 3)
    all_faces = np.concatenate(all_faces, axis=0)
    owners = np.array(owners)
    old_counts = {name: int((owners == name).sum()) for name in by_name}

    image = document["images"][0]
    view = document["bufferViews"][image["bufferView"]]
    start = 8 + view.get("byteOffset", 0)
    texture = Image.open(io.BytesIO(bytes(binary[start:start + view["byteLength"]])))
    skin_index = next(iter(by_name.values()))["skin"]
    _, labels = classify(positions, uvs, all_faces.reshape(-1), texture,
                         document, binary, skin_index)

    orphaned = set(np.unique(labels).tolist()) - set(by_name)
    # "eyes" is the one label expected to appear with no node yet: a body
    # whose zone never crossed the old fixed colour cut got zero eye
    # faces at its original split, so add_mesh_node was never called for
    # it (see the CLASSES loop in split()) and no "eyes" node exists to
    # repoint. A later, more sensitive classify() can still find eyes on
    # such a body -- that is the whole point of making the cut adaptive
    # -- so build the missing node the same way the fresh-split path
    # would have, from "body"'s own primitive (attributes and material
    # are shared across every class in this split; see the module
    # docstring), rather than treating it as an error. "skin_accent" is
    # the same situation for a body that never had a tail (or anything
    # else classify()'s tail exclusion catches) at its original split.
    ON_DEMAND_CLASSES = {"eyes", "skin_accent"}
    if orphaned - ON_DEMAND_CLASSES:
        raise RuntimeError("reclassify_surfaces produced label(s) %s with "
                            "no matching node to hold them"
                            % sorted(orphaned - ON_DEMAND_CLASSES))
    for name in orphaned & ON_DEMAND_CLASSES:
        body_node = by_name["body"]
        body_prim = document["meshes"][body_node["mesh"]]["primitives"][0]
        body_index = next(i for i, n in enumerate(document["nodes"])
                          if n is body_node)
        parent = next(i for i, n in enumerate(document["nodes"])
                      if body_index in n.get("children", []))
        document["meshes"].append({"name": name, "primitives": [{
            "attributes": dict(body_prim["attributes"]),
            "indices": body_prim["indices"],
            "material": body_prim.get("material", 0)}]})
        document["nodes"].append({"name": name,
                                  "mesh": len(document["meshes"]) - 1,
                                  "skin": body_node["skin"]})
        new_index = len(document["nodes"]) - 1
        document["nodes"][parent]["children"].append(new_index)
        by_name[name] = document["nodes"][new_index]

    def repoint(node, faces):
        prim = document["meshes"][node["mesh"]]["primitives"][0]
        acc = append_accessor(document, binary,
                              faces.reshape(-1).astype(np.uint32), 5125,
                              "SCALAR", 34963)
        prim["indices"] = acc

    changes = []
    for name, node in by_name.items():
        new_faces = all_faces[labels == name]
        repoint(node, new_faces)
        changes.append("%s %d->%d" % (name, old_counts.get(name, 0), len(new_faces)))
    return ", ".join(changes)


def grayscale_texture(texture: Image.Image) -> bytes:
    """Desaturate for tinting, without carrying the source's full contrast.

    Checked directly (a pixel-position diff against the untinted render):
    the dark lines a saturated wardrobe tint made look like cuts in the
    mesh are real-time shading on the model's OWN fold/seam geometry, at
    the exact same screen positions with or without any of this -- not
    baked texture detail, so no amount of filtering the source image
    (median, Gaussian blur, nearest-neighbour sampling: all three were
    tried here and none moved those pixels) can remove them.  What this
    function can still do something about is the texture's OWN dark
    values -- e.g. this body's navy trousers reads as near-black once
    desaturated -- so straight per-pixel luminance is remapped into
    [floor, 1.0] rather than [0.0, 1.0], which keeps a lit fabric looking
    like fabric instead of a flat colour swatch without also making a
    dark source garment crush to black once tinted.  The shading itself
    is addressed separately, in replicated_actor_3d.gd, the same way
    eyes already avoid the same problem: a floor under how dark real-time
    shadow can take the material, not a change to what it is shaded with.
    """
    tex = np.asarray(texture.convert("RGB")).astype(np.float64) / 255.0
    lum = tex @ np.array([0.299, 0.587, 0.114])
    floor = 0.5
    ceiling = max(float(np.percentile(lum, 90)), 1e-6)
    lifted = floor + (1.0 - floor) * np.clip(lum / ceiling, 0, 1)
    img = Image.fromarray((lifted * 255).astype(np.uint8)).convert("RGB")
    out = io.BytesIO()
    img.save(out, format="PNG")
    return out.getvalue()


def ring(radius, y0, y1, segments=24):
    verts, norms, uv = [], [], []
    for level, yy in ((0, y0), (1, y1)):
        for s in range(segments):
            a = 2 * np.pi * s / segments
            verts.append([radius * np.sin(a), yy, -radius * np.cos(a)])
            norms.append([np.sin(a), 0.0, -np.cos(a)])
            uv.append([s / segments, level])
    faces = []
    for s in range(segments):
        n = (s + 1) % segments
        faces += [[s, segments + s, segments + n], [s, segments + n, n]]
    return (np.array(verts), np.array(norms), np.array(uv),
            np.array(faces, dtype=np.uint32).reshape(-1))


def dome(radius, y0, segments=24, rows=5):
    verts, norms, uv = [], [], []
    for row in range(rows + 1):
        t = row / rows * (np.pi / 2)
        for s in range(segments):
            a = 2 * np.pi * s / segments
            direction = np.array([np.cos(t) * np.sin(a), np.sin(t),
                                  -np.cos(t) * np.cos(a)])
            verts.append([direction[0] * radius, y0 + direction[1] * radius,
                          direction[2] * radius])
            norms.append(direction)
            uv.append([s / segments, row / rows])
    faces = []
    for row in range(rows):
        for s in range(segments):
            n = (s + 1) % segments
            a0 = row * segments + s
            a1 = row * segments + n
            b0 = (row + 1) * segments + s
            b1 = (row + 1) * segments + n
            faces += [[a0, b0, b1], [a0, b1, a1]]
    return (np.array(verts), np.array(norms), np.array(uv),
            np.array(faces, dtype=np.uint32).reshape(-1))


def add_scalp(document, binary) -> int:
    """A skull under the hair: the sculpted hair IS the head's outer
    surface, so hiding it under a chosen style opened a hole.  The scalp
    duplicates the hair surface pulled inward along its normals -- same
    topology, so it meets the face boundary exactly -- with a plain skin
    material the runtime tints with the rest of the body."""
    hair_node = next((n for n in document["nodes"]
                      if n.get("name") == "hair" and "mesh" in n), None)
    if hair_node is None:
        return 0
    prim = document["meshes"][hair_node["mesh"]]["primitives"][0]
    positions = accessor_array(document, binary, prim["attributes"]["POSITION"])
    normals = accessor_array(document, binary, prim["attributes"]["NORMAL"])
    uvs = accessor_array(document, binary, prim["attributes"]["TEXCOORD_0"])
    joints = accessor_array(document, binary, prim["attributes"]["JOINTS_0"])
    weights = accessor_array(document, binary, prim["attributes"]["WEIGHTS_0"])
    indices = accessor_array(document, binary,
                             prim["indices"]).reshape(-1).astype(np.int64)
    # Skull-adjacent faces only: the sculpted hair can carry a ponytail
    # or a crest, and a scalp cloned from those hangs off the head as a
    # skin-coloured streamer.  The hole that needs closing hugs the
    # skull, so faces keep only if every corner sits near the head joint.
    skin = document["skins"][0]
    joints_list = skin["joints"]
    names = [document["nodes"][j].get("name", "") for j in joints_list]
    ibms = accessor_array(document, binary, skin["inverseBindMatrices"])
    head_row = names.index("Head")
    ibm = np.asarray(ibms[head_row], dtype=np.float64).reshape(4, 4).T
    head_global = np.linalg.inv(ibm)[:3, 3]
    # The scalp is a fitted cranium dome, not a shrunk hair clone: tall
    # sculpted hair (the male pompadour, the female tail) reaches far
    # enough from the skull that pulling its shell inward either leaves
    # crown holes or dangles streamers.  A sphere least-squares fitted to
    # the head's own SKIN vertices gives the true cranium; the dome is
    # its upper reach with the rim tucked slightly inward under the
    # hairline.
    body_node = next(n for n in document["nodes"]
                     if n.get("name") == "body" and "mesh" in n)
    body_prim = document["meshes"][body_node["mesh"]]["primitives"][0]
    body_positions = accessor_array(document, binary,
                                    body_prim["attributes"]["POSITION"])
    body_indices = accessor_array(
        document, binary, body_prim["indices"]).reshape(-1).astype(np.int64)
    skin_used = np.unique(body_indices)
    del skin_used
    # The whole hair shell, pulled inward, proved the right scalp -- its
    # seam meets the face exactly and the crown reads as a buzz cut (the
    # painted forehead hairline hides the 12 mm inset fringe).  The one
    # genuine defect was cloning geometry that hangs BELOW the head
    # joint: a ponytail became a skin streamer down the neck.  So: every
    # hair face whose centroid sits above the joint, nothing else.
    faces3 = indices.reshape(-1, 3)
    centroids = positions[faces3].mean(axis=1)
    horizontal = np.linalg.norm(
        centroids[:, [0, 2]] - head_global[[0, 2]], axis=1)
    near = ((centroids[:, 1] > float(head_global[1]) + 0.005)
            & (horizontal < 0.115))
    kept3 = faces3[near]
    # Every piece that hugs the skull, not merely the biggest: a sculpt
    # is many separate locks, so keeping only the largest left an eight
    # centimetre patch instead of a cap.  Each connected piece is judged
    # on its own -- close to the head's axis and not a stray chip.
    parent = {}
    def find(a):
        while parent.setdefault(a, a) != a:
            parent[a] = parent[parent[a]]
            a = parent[a]
        return a
    for a, b, c in kept3:
        ra, rb, rc = find(int(a)), find(int(b)), find(int(c))
        parent[rb] = ra
        parent[find(rc)] = find(ra)
    groups = {}
    for face_index, face in enumerate(kept3):
        groups.setdefault(find(int(face[0])), []).append(face_index)
    keep_face = np.zeros(len(kept3), dtype=bool)
    for root, members in groups.items():
        block = kept3[members]
        centre = positions[block.reshape(-1)].mean(axis=0)
        reach = float(np.linalg.norm(centre[[0, 2]] - head_global[[0, 2]]))
        if len(members) >= 8 and reach < 0.09:
            keep_face[members] = True
    kept = kept3[keep_face].reshape(-1)
    used = np.unique(kept)
    remap = np.full(len(positions), -1, dtype=np.int64)
    remap[used] = np.arange(len(used))
    unit = normals[used]
    unit = unit / np.maximum(np.linalg.norm(unit, axis=1, keepdims=True),
                             1e-9)
    scalp_positions = (positions[used] - unit * 0.012).astype(np.float32)
    dome_indices = remap[kept].astype(np.uint32)
    scalp_normals = unit.astype(np.float32)
    scalp_uv = uvs[used].astype(np.float32)
    pos_acc = append_accessor(document, binary, scalp_positions, 5126,
                              "VEC3", 34962)
    norm_acc = append_accessor(document, binary, scalp_normals, 5126,
                               "VEC3", 34962)
    uv_acc = append_accessor(document, binary, scalp_uv, 5126, "VEC2",
                             34962)
    joints_acc = append_accessor(document, binary,
                                 joints[used].astype(np.uint16), 5123,
                                 "VEC4", 34962)
    weights_acc = append_accessor(document, binary,
                                  weights[used].astype(np.float32), 5126,
                                  "VEC4", 34962)
    idx_acc = append_accessor(document, binary, dome_indices, 5125,
                              "SCALAR", 34963)
    document["materials"].append({
        "name": "Scalp",
        "pbrMetallicRoughness": {
            "baseColorFactor": [0.78, 0.60, 0.47, 1.0],
            "metallicFactor": 0.0, "roughnessFactor": 0.85,
        },
    })
    mesh_node_skin = next(n["skin"] for n in document["nodes"]
                          if n.get("name") == "hair")
    document["meshes"].append({"name": "scalp", "primitives": [{
        "attributes": {"POSITION": pos_acc, "NORMAL": norm_acc,
                       "TEXCOORD_0": uv_acc, "JOINTS_0": joints_acc,
                       "WEIGHTS_0": weights_acc},
        "indices": idx_acc,
        "material": len(document["materials"]) - 1}]})
    document["nodes"].append({"name": "scalp",
                              "mesh": len(document["meshes"]) - 1,
                              "skin": mesh_node_skin})
    parent = next(i for i, n in enumerate(document["nodes"])
                  if any(document["nodes"][c].get("name") == "hair"
                         for c in n.get("children", [])))
    document["nodes"][parent]["children"].append(len(document["nodes"]) - 1)
    return int(len(scalp_positions))


def split(path: Path, calibrate: bool) -> str:
    document, binary = read_glb(path)
    extras = document.setdefault("asset", {}).setdefault("extras", {})
    if int(extras.get("eloriaSurfacesSplit", 0)) >= 34:
        return "already split"
    if int(extras.get("eloriaSurfacesSplit", 0)) in (15, 16, 17, 18, 19, 20, 21, 22, 23, 24, 25, 26, 27, 28, 29, 30, 31, 32, 33):
        report = reclassify_surfaces(document, binary)
        extras["eloriaSurfacesSplit"] = 34
        write_glb(path, document, binary)
        return "%s -> v34" % report
    if int(extras.get("eloriaSurfacesSplit", 0)) == 14:
        count = resmooth_shared_surfaces(document, binary)
        extras["eloriaSurfacesSplit"] = 15
        write_glb(path, document, binary)
        return "shading seams smoothed (%d verts) -> v15" % count
    if extras.get("eloriaSurfacesSplit"):
        # v2's scalp cloned the whole hair; rebuild it skull-only by
        # pointing the existing scalp mesh at freshly written accessors.
        for i, n in enumerate(document["nodes"]):
            if n.get("name") == "scalp" and "mesh" in n:
                scalp_mesh = n["mesh"]
                document["nodes"] = [m for m in document["nodes"]]
                count = add_scalp(document, binary)
                document["meshes"][scalp_mesh]["primitives"] =                     document["meshes"][-1]["primitives"]
                document["meshes"].pop()
                dangling = len(document["nodes"]) - 1
                for m in document["nodes"]:
                    if dangling in m.get("children", []):
                        m["children"].remove(dangling)
                document["nodes"].pop()
                break
        else:
            count = add_scalp(document, binary)
        extras["eloriaSurfacesSplit"] = 14
        write_glb(path, document, binary)
        return "scalp rebuilt (whole shell above the joint, -> v14)"
    mesh_node_index = next(i for i, n in enumerate(document["nodes"])
                           if "mesh" in n and "skin" in n)
    mesh_node = document["nodes"][mesh_node_index]
    prim = document["meshes"][mesh_node["mesh"]]["primitives"][0]
    positions = accessor_array(document, binary, prim["attributes"]["POSITION"])
    uvs = accessor_array(document, binary, prim["attributes"]["TEXCOORD_0"])
    indices = accessor_array(document, binary, prim["indices"]).reshape(-1).astype(np.uint32)
    image = document["images"][0]
    view = document["bufferViews"][image["bufferView"]]
    start = 8 + view.get("byteOffset", 0)
    texture = Image.open(io.BytesIO(bytes(binary[start:start + view["byteLength"]])))

    smoothed = smooth_normals(positions, indices.astype(np.int64))
    overwrite_accessor(document, binary, prim["attributes"]["NORMAL"], smoothed)

    faces, labels = classify(positions, uvs, indices, texture,
                             document, binary, mesh_node["skin"])
    counts = {c: int((labels == c).sum()) for c in CLASSES}
    if calibrate:
        return "faces per class: %s" % counts

    grey_png = grayscale_texture(texture)
    grey_view = append_view(document, binary, grey_png)
    document["images"].append({"name": "wardrobe_grey",
                               "mimeType": "image/png",
                               "bufferView": grey_view})
    sampler = 0 if document.get("samplers") else None
    document.setdefault("textures", []).append(
        {"source": len(document["images"]) - 1}
        | ({"sampler": sampler} if sampler is not None else {}))
    grey_texture = len(document["textures"]) - 1
    original_material = prim.get("material", 0)
    wardrobe_material = {
        "name": "Wardrobe",
        "pbrMetallicRoughness": {
            "baseColorTexture": {"index": grey_texture},
            "baseColorFactor": [1.0, 1.0, 1.0, 1.0],
            "metallicFactor": 0.0, "roughnessFactor": 0.9,
        },
    }
    document["materials"].append(wardrobe_material)
    wardrobe_index = len(document["materials"]) - 1
    plain_material = {
        "name": "WardrobePlain",
        "pbrMetallicRoughness": {
            "baseColorFactor": [0.9, 0.9, 0.9, 1.0],
            "metallicFactor": 0.0, "roughnessFactor": 0.9,
        },
    }
    document["materials"].append(plain_material)
    plain_index = len(document["materials"]) - 1

    parent = next(i for i, n in enumerate(document["nodes"])
                  if mesh_node_index in n.get("children", []))
    skin_index = mesh_node["skin"]
    scene_children = document["nodes"][parent]["children"]

    def add_mesh_node(name, primitive):
        document["meshes"].append({"name": name, "primitives": [primitive]})
        document["nodes"].append({"name": name,
                                  "mesh": len(document["meshes"]) - 1,
                                  "skin": skin_index})
        scene_children.append(len(document["nodes"]) - 1)

    for cls in CLASSES:
        member = labels == cls
        if not member.any():
            continue
        cls_indices = faces[member].reshape(-1).astype(np.uint32)
        acc = append_accessor(document, binary, cls_indices, 5125, "SCALAR",
                              34963)
        material = (wardrobe_index if cls.startswith("wardrobe_")
                    else original_material)
        add_mesh_node(cls, {"attributes": dict(prim["attributes"]),
                            "indices": acc, "material": material})

    # The head styles the runtime toggles: a plain band and cap, skinned
    # rigid to the Head joint so they ride (and scale) with it.
    joints = document["skins"][skin_index]["joints"]
    names = [document["nodes"][j].get("name", "") for j in joints]
    head_row = names.index("Head")
    for name, (verts, norms, uv, faces_extra) in (
            ("wardrobe_head_band", ring(0.104, 1.655, 1.685)),
            ("wardrobe_head_cap", dome(0.105, 1.665))):
        count = len(verts)
        pos_acc = append_accessor(document, binary,
                                  verts.astype(np.float32), 5126, "VEC3",
                                  34962)
        norm_acc = append_accessor(document, binary,
                                   norms.astype(np.float32), 5126, "VEC3",
                                   34962)
        uv_acc = append_accessor(document, binary, uv.astype(np.float32),
                                 5126, "VEC2", 34962)
        j = np.zeros((count, 4), dtype=np.uint16)
        j[:, 0] = head_row
        joints_acc = append_accessor(document, binary, j, 5123, "VEC4",
                                     34962)
        w = np.zeros((count, 4), dtype=np.float32)
        w[:, 0] = 1.0
        weights_acc = append_accessor(document, binary, w, 5126, "VEC4",
                                      34962)
        idx_acc = append_accessor(document, binary, faces_extra, 5125,
                                  "SCALAR", 34963)
        add_mesh_node(name, {"attributes": {
            "POSITION": pos_acc, "NORMAL": norm_acc, "TEXCOORD_0": uv_acc,
            "JOINTS_0": joints_acc, "WEIGHTS_0": weights_acc},
            "indices": idx_acc, "material": plain_index})

    del mesh_node["mesh"]
    add_scalp(document, binary)
    extras["eloriaSurfacesSplit"] = 34
    write_glb(path, document, binary)
    return "split: %s" % counts


def main() -> int:
    ap = argparse.ArgumentParser(description="split race body surfaces")
    ap.add_argument("--race", default=None)
    ap.add_argument("--calibrate", action="store_true")
    args = ap.parse_args()
    races = ([args.race] if args.race
             else ["luminous_male", "luminous_female"])
    for race in races:
        print("%-18s %s" % (race, split(RACES / (race + ".glb"),
                                        args.calibrate)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
