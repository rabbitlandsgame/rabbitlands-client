"""Reshape a race's proportions by scaling skeleton joints in place.

The luminous bodies are built to realistic proportions -- a head 0.164 m
wide on a 1.82 m frame -- while the game's look calls for the classic
stylised read: a rounder, wider head on the same body.  Rather than
resculpting the mesh, the scale rides the JOINT: a rest scale on the Head
bone reaches everything that follows the bone -- the skinned head
vertices (blending smoothly into the neck through the existing skin
weights), the hair sockets, and the helm sockets -- so the mesh, the
hair and every already-built piece of headgear stay consistent without a
rebuild.  The animation library carries no scale tracks (the Head bone
has no tracks at all), so nothing at runtime overrides the rest value.

Targets are ABSOLUTE: the tool writes the scale, not a multiplier, so
running it twice is safe and re-tuning means editing the numbers below.

Usage:
    python adjust_race_proportions.py [--race luminous_male] [--dry-run]
"""
from __future__ import annotations

import argparse
import json
import struct
import sys

import numpy as np
from pathlib import Path

TOOLS = Path(__file__).resolve().parent
CLIENT = TOOLS.parent.parent / "godot-client"
RACES = CLIENT / "assets" / "actors" / "native" / "races"

#: The head grows in VERTEX space, weighted by how much each vertex
#: belongs to the head joint.
#:
#: It used to be a rest scale on the Head node, which measurement showed
#: is a phantom: Godot rebuilds the bind matrices from the scaled rest,
#: so the skinned body renders at exactly its authored size -- the head
#: never actually grew in game -- while BoneAttachment3D children DO
#: inherit the scale, so every hairstyle and every socketed helm was
#: sized against a head that only existed offline.  Scaling the vertices
#: makes the head real and leaves the joint alone.
HEAD_SCALE = (1.35, 1.10, 1.15)

#: Boxy torso: the authored chest is a 1.7x superhero V (0.56 m shoulder
#: line over a 0.32 m waist); the reference reads nearer 1.3x.  The edit
#: is one smooth displacement field baked into the mesh,
#:     dx = -sign(x) * min(|x|, anchor) * (1 - s(y)),
#: so the trunk narrows inside the shoulder-joint radius while everything
#: beyond it -- deltoids, the whole hanging arm -- slides inboard rigidly
#: (arm verts use the plateau factor whatever their height, or the field
#: would shear across the arm's own thickness).  s(y) ramps from 1 at the
#: ribs to the scale across the chest, holds through the shoulder band,
#: and fades back to 1 up the neck so the throat and face stay put.  The
#: shoulder joints ride the same field: their node translations move and
#: their inverse binds are rewritten to the new rest, which keeps the
#: authored vertex data exact at rest and every rotation-only clip
#: pivoting from the new, narrower shoulders.
TORSO_TAPER = {
    "scale": 0.82,
    "rampLo": 1.20, "rampHi": 1.42,
    "fadeLo": 1.50, "fadeHi": 1.62,
}
MOVED_ROOTS = ("clavicle_l", "clavicle_r")

#: Even out the arm, the Eternal Lands way: the authored bicep is half
#: again the forearm's girth (radii 0.074 vs 0.048) where the reference
#: wears near-uniform tubes.  Radial scaling about each arm's own bone
#: line, parametrized by the fraction along shoulder-to-wrist so both
#: bodies work: the deltoid and bicep draw in, the forearm swells, the
#: hand stays.  No joints move and no binds change -- the field is
#: purely radial.
ARM_BALANCE = {
    "upper": 0.88,     # deltoid + bicep
    "forearm": 1.18,
    "blendLo": 0.50, "blendHi": 0.58,   # elbow crossfade, as fraction
    "fadeLo": 0.85, "fadeHi": 1.00,     # back to 1.0 at the wrist
}

#: Sloped shoulders, the Eternal Lands way: the shoulder line falls away
#: from the neck instead of running out as a square shelf.  Same recipe
#: as the taper, turned vertical --
#:     dy = -drop * (min(|x|, anchor) / anchor) * w(x, y)
#: so the drop grows linearly from the spine to the shoulder point and
#: the arms beyond the anchor ride down rigidly with it.  w fades the
#: trunk's share in at the chest band and out again up the neck so the
#: waist and face stay put; arm vertices always take the full plateau,
#: because any height dependence would shear across the arm itself.
SHOULDER_DROOP = {
    "drop": 0.020,
    "bandLo": 1.28, "bandHi": 1.38,
    "fadeLo": 1.52, "fadeHi": 1.62,
}


def scale_head_vertices(document, binary) -> bool:
    """Grow the head about its joint, in the mesh rather than the rig.

    Blended by each vertex's own head weight, so the jaw and neck taper
    into the unscaled body instead of tearing at a seam, and applied to
    every skinned primitive -- the split surfaces and the generated
    scalp, band and cap all ride it.
    """
    extras = document.setdefault("asset", {}).setdefault("extras", {})
    if extras.get("eloriaHeadVertexScale"):
        return False

    bin_len, bin_tag = struct.unpack_from("<I4s", binary, 0)
    assert bin_tag[:3] == b"BIN", bin_tag
    payload = 8
    nodes = document["nodes"]
    names = [n.get("name", "") for n in nodes]

    # The phantom rest scale goes back to identity in the same pass; a
    # file carrying both would grow the head twice for attachments.
    head_node = next(n for n in nodes if n.get("name") == "Head")
    head_node.pop("scale", None)

    globals_, _ = _matrices(document)
    head_index = names.index("Head")
    anchor = globals_[head_index][:3, 3].copy()
    scale = np.asarray(HEAD_SCALE, dtype=np.float64)

    skin = document["skins"][0]
    joint_rows = {row: index for index, row in enumerate(skin["joints"])}
    head_row = joint_rows[head_index]

    moved = 0
    seen = set()
    for node in nodes:
        if "mesh" not in node or "skin" not in node:
            continue
        for prim in document["meshes"][node["mesh"]]["primitives"]:
            acc_index = prim["attributes"]["POSITION"]
            if acc_index in seen:
                continue
            seen.add(acc_index)
            weights = _read_vec4(document, binary, payload,
                                 prim["attributes"]["WEIGHTS_0"])
            joints = _read_vec4(document, binary, payload,
                                prim["attributes"]["JOINTS_0"])
            acc = document["accessors"][acc_index]
            view = document["bufferViews"][acc["bufferView"]]
            offset = (payload + view.get("byteOffset", 0)
                      + acc.get("byteOffset", 0))
            stride = view.get("byteStride", 12)
            for v in range(acc["count"]):
                share = float(weights[v][joints[v] == head_row].sum())
                if share <= 0.001:
                    continue
                at = offset + v * stride
                x, y, z = struct.unpack_from("<3f", binary, at)
                point = np.array([x, y, z], dtype=np.float64)
                grown = anchor + (point - anchor) * scale
                blended = point + (grown - point) * share
                struct.pack_into("<3f", binary, at, *[float(c) for c in blended])
                moved += 1

    extras["eloriaHeadVertexScale"] = list(HEAD_SCALE)
    print("head vertex scale %s: %d vertices grown, joint scale cleared"
          % (list(HEAD_SCALE), moved))
    return True


def _read_vec4(document, binary, payload, index):
    acc = document["accessors"][index]
    view = document["bufferViews"][acc["bufferView"]]
    offset = payload + view.get("byteOffset", 0) + acc.get("byteOffset", 0)
    kind = {5121: ("<4B", 4, 255.0), 5123: ("<4H", 8, 65535.0),
            5126: ("<4f", 16, None)}[acc["componentType"]]
    fmt, size, norm = kind
    stride = view.get("byteStride", size)
    out = np.empty((acc["count"], 4), dtype=np.float64)
    for v in range(acc["count"]):
        values = struct.unpack_from(fmt, binary, offset + v * stride)
        out[v] = values
    if norm is not None and acc.get("normalized"):
        out /= norm
    return out


def _matrices(document):
    nodes = document["nodes"]
    parent = {}
    for index, node in enumerate(nodes):
        for child in node.get("children", []):
            parent[child] = index

    def local(node):
        m = np.eye(4)
        if "matrix" in node:
            return np.array(node["matrix"], dtype=np.float64).reshape(4, 4).T
        t = node.get("translation", [0, 0, 0])
        r = node.get("rotation", [0, 0, 0, 1])
        s = node.get("scale", [1, 1, 1])
        x, y, z, w = r
        rot = np.array([
            [1 - 2 * (y * y + z * z), 2 * (x * y - z * w), 2 * (x * z + y * w)],
            [2 * (x * y + z * w), 1 - 2 * (x * x + z * z), 2 * (y * z - x * w)],
            [2 * (x * z - y * w), 2 * (y * z + x * w), 1 - 2 * (x * x + y * y)],
        ])
        m[:3, :3] = rot @ np.diag(s)
        m[:3, 3] = t
        return m

    globals_ = [None] * len(nodes)

    def resolve(i):
        if globals_[i] is None:
            loc = local(nodes[i])
            p = parent.get(i)
            globals_[i] = loc if p is None else resolve(p) @ loc
        return globals_[i]

    for i in range(len(nodes)):
        resolve(i)
    return globals_, parent


def _field_factory(spec):
    lo, hi = spec["rampLo"], spec["rampHi"]
    flo, fhi = spec["fadeLo"], spec["fadeHi"]
    top = spec["scale"]

    def s_of_y(y):
        if y <= lo:
            return 1.0
        if y <= hi:
            t = (y - lo) / (hi - lo)
            return 1.0 + (top - 1.0) * (3 * t * t - 2 * t * t * t)
        if y <= flo:
            return top
        if y <= fhi:
            t = (y - flo) / (fhi - flo)
            return top + (1.0 - top) * (3 * t * t - 2 * t * t * t)
        return 1.0

    def dx(x, y, anchor, plateau):
        reach = min(abs(x), anchor)
        factor = plateau if abs(x) >= anchor else s_of_y(y)
        return -np.sign(x) * reach * (1.0 - factor)

    return dx


def balance_arms(document, binary) -> bool:
    spec = ARM_BALANCE
    extras = document.setdefault("asset", {}).setdefault("extras", {})
    current = float(extras.get("eloriaArmBalance", 0.0))
    if abs(current - spec["upper"]) < 1e-6:
        print("arm balance already %.2f -- nothing to do" % current)
        return False
    if abs(current) > 1e-6:
        print("arm balance is %.2f, target %.2f: restore the GLB from git "
              "first (balance edits do not compose)"
              % (current, spec["upper"]))
        raise SystemExit(1)

    bin_len, bin_tag = struct.unpack_from("<I4s", binary, 0)
    assert bin_tag[:3] == b"BIN", bin_tag
    payload = 8

    nodes = document["nodes"]
    names = [n.get("name", "") for n in nodes]
    globals_, parent = _matrices(document)

    def joint(name):
        for i, n in enumerate(names):
            if n == name:
                return globals_[i][:3, 3]
        raise KeyError(name)

    sides = {}
    for side in ("l", "r"):
        sides[side] = (joint("upperarm_" + side),
                       joint("lowerarm_" + side),
                       joint("hand_" + side))

    def smoothstep(t):
        t = min(max(t, 0.0), 1.0)
        return 3 * t * t - 2 * t * t * t

    def factor(u):
        if u <= spec["blendLo"]:
            f = spec["upper"]
        elif u <= spec["blendHi"]:
            f = spec["upper"] + (spec["forearm"] - spec["upper"]) * smoothstep(
                (u - spec["blendLo"]) / (spec["blendHi"] - spec["blendLo"]))
        elif u <= spec["fadeLo"]:
            f = spec["forearm"]
        else:
            f = spec["forearm"] + (1.0 - spec["forearm"]) * smoothstep(
                (u - spec["fadeLo"]) / (spec["fadeHi"] - spec["fadeLo"]))
        return f

    seen = set()
    moved = 0
    for node in nodes:
        if "mesh" not in node or "skin" not in node:
            continue
        for prim in document["meshes"][node["mesh"]]["primitives"]:
            acc_index = prim["attributes"]["POSITION"]
            if acc_index in seen:
                continue
            seen.add(acc_index)
            acc = document["accessors"][acc_index]
            view = document["bufferViews"][acc["bufferView"]]
            offset = (payload + view.get("byteOffset", 0)
                      + acc.get("byteOffset", 0))
            stride = view.get("byteStride", 12)
            for v in range(acc["count"]):
                at = offset + v * stride
                x, y, z = struct.unpack_from("<3f", binary, at)
                if y < 1.25:
                    continue
                side = "l" if x >= 0 else "r"
                sh, el, wr = sides[side]
                span = wr[0] - sh[0]
                u = (x - sh[0]) / span if span > 1e-6 else -1.0
                if u < 0.02 or u > 1.05:
                    continue
                f = factor(min(u, 1.0))
                if abs(f - 1.0) < 1e-6:
                    continue
                if x < el[0] if side == "l" else x > el[0]:
                    a, b = sh, el
                else:
                    a, b = el, wr
                t = (x - a[0]) / (b[0] - a[0]) if abs(b[0] - a[0]) > 1e-9 else 0.0
                cy = a[1] + t * (b[1] - a[1])
                cz = a[2] + t * (b[2] - a[2])
                ny = cy + (y - cy) * f
                nz = cz + (z - cz) * f
                struct.pack_into("<3f", binary, at, x, ny, nz)
                moved += 1

    extras["eloriaArmBalance"] = spec["upper"]
    print("arm balance %.2f/%.2f: %d vertices scaled"
          % (spec["upper"], spec["forearm"], moved))
    return True


def droop_shoulders(document, binary) -> bool:
    spec = SHOULDER_DROOP
    extras = document.setdefault("asset", {}).setdefault("extras", {})
    current = float(extras.get("eloriaShoulderDroop", 0.0))
    if abs(current - spec["drop"]) < 1e-6:
        print("shoulder droop already %.3f -- nothing to do" % current)
        return False
    if abs(current) > 1e-6:
        print("shoulder droop is %.3f, target %.3f: restore the GLB from "
              "git first (droop edits do not compose)"
              % (current, spec["drop"]))
        raise SystemExit(1)

    bin_len, bin_tag = struct.unpack_from("<I4s", binary, 0)
    assert bin_tag[:3] == b"BIN", bin_tag
    payload = 8

    nodes = document["nodes"]
    names = [n.get("name", "") for n in nodes]
    globals_, parent = _matrices(document)
    anchor = None
    for i, n in enumerate(names):
        if n == "upperarm_l":
            anchor = abs(float(globals_[i][0, 3]))
    assert anchor and anchor > 0.05, "no upperarm_l joint"

    def smoothstep(t):
        t = min(max(t, 0.0), 1.0)
        return 3 * t * t - 2 * t * t * t

    def dy(x, y):
        share = min(abs(x), anchor) / anchor
        if abs(x) >= anchor:
            # The plateau is for the arm band only: after the width taper
            # the hips reach the anchor too, and an ungated plateau sagged
            # three hundred hip-side vertices by the full drop.
            w = 1.0 if y >= 1.30 else 0.0
        else:
            w = smoothstep((y - spec["bandLo"])
                           / (spec["bandHi"] - spec["bandLo"]))
            w *= 1.0 - smoothstep((y - spec["fadeLo"])
                                  / (spec["fadeHi"] - spec["fadeLo"]))
        return -spec["drop"] * share * w

    seen = set()
    moved_verts = 0
    for node in nodes:
        if "mesh" not in node or "skin" not in node:
            continue
        for prim in document["meshes"][node["mesh"]]["primitives"]:
            acc_index = prim["attributes"]["POSITION"]
            if acc_index in seen:
                continue
            seen.add(acc_index)
            acc = document["accessors"][acc_index]
            view = document["bufferViews"][acc["bufferView"]]
            offset = (payload + view.get("byteOffset", 0)
                      + acc.get("byteOffset", 0))
            stride = view.get("byteStride", 12)
            for v in range(acc["count"]):
                at = offset + v * stride
                x, y, z = struct.unpack_from("<3f", binary, at)
                shift = dy(x, y)
                if shift:
                    struct.pack_into("<3f", binary, at, x, y + shift, z)
                    moved_verts += 1

    index_of = {n: i for i, n in enumerate(names)}
    moved = []

    def collect(i):
        moved.append(i)
        for child in nodes[i].get("children", []):
            collect(child)

    for root in MOVED_ROOTS:
        collect(index_of[root])
    new_global_t = {}
    for i in moved:
        g = globals_[i]
        x, y = float(g[0, 3]), float(g[1, 3])
        new_global_t[i] = g[:3, 3] + np.array([0.0, dy(x, y), 0.0])
    for i in moved:
        p = parent.get(i)
        parent_g = globals_[p].copy() if p is not None else np.eye(4)
        if p in new_global_t:
            parent_g[:3, 3] = new_global_t[p]
        child_g = globals_[i].copy()
        child_g[:3, 3] = new_global_t[i]
        local_new = np.linalg.inv(parent_g) @ child_g
        nodes[i]["translation"] = [round(float(v), 6)
                                   for v in local_new[:3, 3]]

    for skin in document.get("skins", []):
        acc = document["accessors"][skin["inverseBindMatrices"]]
        view = document["bufferViews"][acc["bufferView"]]
        offset = (payload + view.get("byteOffset", 0)
                  + acc.get("byteOffset", 0))
        for row, joint in enumerate(skin["joints"]):
            if joint not in new_global_t:
                continue
            g = globals_[joint].copy()
            g[:3, 3] = new_global_t[joint]
            ibm = np.linalg.inv(g)
            struct.pack_into("<16f", binary, offset + row * 64,
                             *ibm.T.reshape(-1))

    extras["eloriaShoulderDroop"] = spec["drop"]
    print("shoulder droop %.3f: %d vertices lowered, %d joints moved"
          % (spec["drop"], moved_verts, len(moved)))
    return True


def taper_torso(document, binary) -> bool:
    spec = TORSO_TAPER
    extras = document.setdefault("asset", {}).setdefault("extras", {})
    current = float(extras.get("eloriaTorsoTaper", 1.0))
    if abs(current - spec["scale"]) < 1e-6:
        print("torso taper already %.2f -- nothing to do" % current)
        return False
    if abs(current - 1.0) > 1e-6:
        print("torso taper is %.2f, target %.2f: restore the GLB from git "
              "first (taper edits do not compose)" % (current, spec["scale"]))
        raise SystemExit(1)

    # ``binary`` still carries its 8-byte chunk header (length + BIN tag);
    # accessor offsets are relative to the payload after it.  Forgetting
    # this once scrambled every shifted vertex: reads landed 8 bytes early,
    # so the field was computed from a neighbour's Y and written over it.
    bin_len, bin_tag = struct.unpack_from("<I4s", binary, 0)
    assert bin_tag[:3] == b"BIN", bin_tag
    payload = 8

    nodes = document["nodes"]
    names = [n.get("name", "") for n in nodes]
    globals_, parent = _matrices(document)
    anchor = None
    for i, n in enumerate(names):
        if n == "upperarm_l":
            anchor = abs(float(globals_[i][0, 3]))
    assert anchor and anchor > 0.05, "no upperarm_l joint"
    dx = _field_factory(spec)

    # Every skinned primitive's positions, each accessor exactly once.
    seen = set()
    moved_verts = 0
    for node in nodes:
        if "mesh" not in node or "skin" not in node:
            continue
        for prim in document["meshes"][node["mesh"]]["primitives"]:
            acc_index = prim["attributes"]["POSITION"]
            if acc_index in seen:
                continue
            seen.add(acc_index)
            acc = document["accessors"][acc_index]
            view = document["bufferViews"][acc["bufferView"]]
            offset = (payload + view.get("byteOffset", 0)
                      + acc.get("byteOffset", 0))
            stride = view.get("byteStride", 12)
            for v in range(acc["count"]):
                at = offset + v * stride
                x, y, z = struct.unpack_from("<3f", binary, at)
                shift = dx(x, y, anchor, spec["scale"])
                if shift:
                    struct.pack_into("<3f", binary, at, x + shift, y, z)
                    moved_verts += 1

    # The clavicle subtrees ride the same field: new globals from the
    # field, locals rebuilt top-down, inverse binds rewritten to the new
    # rest (they were exact inverses of the old one).
    index_of = {n: i for i, n in enumerate(names)}
    moved = []

    def collect(i):
        moved.append(i)
        for child in nodes[i].get("children", []):
            collect(child)

    for root in MOVED_ROOTS:
        collect(index_of[root])
    new_global_t = {}
    for i in moved:
        g = globals_[i]
        x, y = float(g[0, 3]), float(g[1, 3])
        new_global_t[i] = g[:3, 3] + np.array(
            [dx(x, y, anchor, spec["scale"]), 0.0, 0.0])
    for i in moved:
        p = parent.get(i)
        parent_g = globals_[p].copy() if p is not None else np.eye(4)
        if p in new_global_t:
            parent_g[:3, 3] = new_global_t[p]
        child_g = globals_[i].copy()
        child_g[:3, 3] = new_global_t[i]
        local_new = np.linalg.inv(parent_g) @ child_g
        nodes[i]["translation"] = [round(float(v), 6)
                                   for v in local_new[:3, 3]]

    for skin in document.get("skins", []):
        acc = document["accessors"][skin["inverseBindMatrices"]]
        view = document["bufferViews"][acc["bufferView"]]
        offset = (payload + view.get("byteOffset", 0)
                  + acc.get("byteOffset", 0))
        for row, joint in enumerate(skin["joints"]):
            if joint not in new_global_t:
                continue
            g = globals_[joint].copy()
            g[:3, 3] = new_global_t[joint]
            ibm = np.linalg.inv(g)
            struct.pack_into("<16f", binary, offset + row * 64,
                             *ibm.T.reshape(-1))

    extras["eloriaTorsoTaper"] = spec["scale"]
    print("torso taper %.2f: %d vertices shifted, %d joints moved"
          % (spec["scale"], moved_verts, len(moved)))
    return True


def main() -> int:
    ap = argparse.ArgumentParser(
        description="scale skeleton joints of a race GLB in place")
    ap.add_argument("--race", default="luminous_male")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    path = RACES / ("%s.glb" % args.race)
    data = path.read_bytes()
    assert data[:4] == b"glTF", path
    json_len, json_type = struct.unpack_from("<I4s", data, 12)
    assert json_type == b"JSON", "unexpected first chunk"
    document = json.loads(data[20:20 + json_len])
    binary = bytearray(data[20 + json_len:])

    changed = []

    tapered = False
    if not args.dry_run:
        tapered = scale_head_vertices(document, binary)
        tapered = taper_torso(document, binary) or tapered
        tapered = droop_shoulders(document, binary) or tapered
        tapered = balance_arms(document, binary) or tapered

    if args.dry_run:
        print("\nnothing written (--dry-run)")
        return 0
    if not changed and not tapered:
        print("nothing to change")
        return 1

    payload = json.dumps(document, separators=(",", ":")).encode()
    payload += b" " * (-len(payload) % 4)
    out = bytearray(b"glTF")
    out += struct.pack("<II", 2, 12 + 8 + len(payload) + len(binary))
    out += struct.pack("<I4s", len(payload), b"JSON")
    out += payload
    out += binary
    path.write_bytes(bytes(out))
    print("\nwrote %s (%d joints scaled)" % (path.name, len(changed)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
