"""Put a race body's limbs back on its bones, size the arm bones to the body,
re-donate the limb weights from Luminous, and thin the limbs toward the
adjusted Luminous body.

  python fix_limbs.py <race>_<g>_redraw.glb <luminous_<g>.glb> out.glb
                      [--report r.json] [--limb-target 0.9] [--no-thin] [--no-transfer] [--no-legs] [--no-rig]

Why.  The client copies the shared library's rotation keys onto every race
by bone name (only the pelvis has a translation track), every race rig
carries Luminous's rest rotations, and the arm offsets point the same way as
Luminous's (compare_rigs.py), so all sixteen SKELETONS take the same pose.
What differs is where the skin was when it was bound: the redrawn Meshy
bodies keep an A-pose droop, 10-45 degrees below the horizontal arm bones,
and skin bound off its bone swings on that lever the moment the shoulder
rotates -- the akimbo Stoneborn idle, the flared forearms elsewhere.
Luminous's own sleeves wrap its bones, which is why it animates right.  On
top of that, every body has arms shorter than the rig it was handed (reach
0.28-0.34 of height against the rigs' 0.39), so the wrist joint sat past
the mitt.

What this does:

  1. per limb, find the mesh's own chain: the vertices the file already
     weights to that limb seed a centreline fitted through their binned
     centroids (binned by distance from the joint); everything inside the
     tube joins, hand and cuff included.  The wrist is where the file's
     forearm/hand weights cross (rigged_races' weight_mitts cut, calibrated
     on the body's own reach); the elbow sits at the rig's own upper:lower
     proportion between shoulder and wrist.  Knee and ankle come from the
     same crossings.  A body whose cloth spans both legs away from either
     (a robe) keeps its legs as they are;
  2. arms only: the rig's upperarm and forearm bones are re-lengthed to the
     mesh's own segments (directions kept, so the pose stays Luminous's),
     the inverse binds are rebuilt and the baked clips' constant
     translation keys updated -- the rest rotations the client contract
     protects are untouched;
  3. straighten by skinning: each mesh segment is rotated (legs also scaled
     a little along the axis) onto the rig's segment about its own proximal
     joint, blended across the joints and faded in over the first few
     centimetres from the torso, exactly as a clip would move it.  The
     hand (foot) rides rigidly on the end of the forearm (calf).  Skin two
     limbs both claim (legs fused at the thigh or the boot) moves by a
     proximity blend of the two;
  4. re-donate the limb weights from the adjusted Luminous body, mapped per
     segment (same fraction along the bone, same offset from it) so the two
     arms' different lengths do not matter, by the nearest-six
     inverse-distance blend rigged_races used.  The mitt keeps its hand-bone
     weights, the torso keeps its own, cloth bound to both legs keeps its
     authored blend;
  5. thin: each of upperarm/forearm/thigh/calf is scaled radially about its
     bone toward Luminous's own girth for that segment (measured the same
     way on both, never thickened), blended by skin weight.

Only POSITION, NORMAL, JOINTS_0, WEIGHTS_0, the inverse binds, the two arm
joints' translations and their constant clip keys change; materials,
textures, node order and rest rotations are untouched.
"""
from __future__ import annotations

import argparse
import json
import math
import struct
import sys
from pathlib import Path

import numpy as np
from scipy.spatial import cKDTree

# ----------------------------------------------------------------- glb io

COMP = {5121: np.uint8, 5123: np.uint16, 5125: np.uint32, 5126: np.float32}
WIDTH = {"SCALAR": 1, "VEC2": 2, "VEC3": 3, "VEC4": 4, "MAT4": 16}


def read_glb(path):
    data = Path(path).read_bytes()
    assert data[:4] == b"glTF", path
    json_len, json_type = struct.unpack_from("<I4s", data, 12)
    assert json_type == b"JSON"
    document = json.loads(data[20:20 + json_len])
    binary = bytearray(data[20 + json_len:])
    assert binary[4:7] == b"BIN"
    return document, binary


def write_glb(path, document, binary):
    struct.pack_into("<I", binary, 0, len(binary) - 8)
    payload = json.dumps(document, separators=(",", ":")).encode()
    payload += b" " * (-len(payload) % 4)
    out = bytearray(b"glTF")
    out += struct.pack("<II", 2, 12 + 8 + len(payload) + len(binary))
    out += struct.pack("<I4s", len(payload), b"JSON")
    out += payload
    out += binary
    Path(path).write_bytes(bytes(out))


def accessor_array(document, binary, index):
    acc = document["accessors"][index]
    view = document["bufferViews"][acc["bufferView"]]
    comp = COMP[acc["componentType"]]
    n = WIDTH[acc["type"]]
    offset = 8 + view.get("byteOffset", 0) + acc.get("byteOffset", 0)
    raw = np.frombuffer(bytes(binary[offset:offset + acc["count"] * n * np.dtype(comp).itemsize]), dtype=comp)
    out = raw.reshape(acc["count"], n).astype(np.float64)
    if acc.get("normalized"):
        out = out / np.iinfo(comp).max
    return out


def overwrite_accessor(document, binary, index, array):
    acc = document["accessors"][index]
    view = document["bufferViews"][acc["bufferView"]]
    comp = COMP[acc["componentType"]]
    n = WIDTH[acc["type"]]
    offset = 8 + view.get("byteOffset", 0) + acc.get("byteOffset", 0)
    arr = np.asarray(array, dtype=np.float64)
    if acc.get("normalized"):
        arr = np.clip(np.round(arr * np.iinfo(comp).max), 0, np.iinfo(comp).max)
    packed = np.ascontiguousarray(arr, dtype=comp)
    assert packed.shape == (acc["count"], n), (packed.shape, acc["count"], n)
    raw = packed.tobytes()
    binary[offset:offset + len(raw)] = raw
    if n == 3 and comp == np.float32:
        acc["min"] = [float(v) for v in arr.min(axis=0)]
        acc["max"] = [float(v) for v in arr.max(axis=0)]


# ----------------------------------------------------------------- skeleton

def joint_names(document, skin_index=0):
    skin = document["skins"][skin_index]
    return [document["nodes"][j].get("name", "") for j in skin["joints"]]


def joint_rest(document, binary, skin_index=0):
    """{name: rest world position} from the inverse binds (the mesh node is
    at identity in these files)."""
    skin = document["skins"][skin_index]
    names = joint_names(document, skin_index)
    ibms = accessor_array(document, binary, skin["inverseBindMatrices"])
    out = {}
    for row, name in enumerate(names):
        ibm = np.asarray(ibms[row], dtype=np.float64).reshape(4, 4).T
        out[name] = np.linalg.inv(ibm)[:3, 3]
    return out


def quat_to_mat(q):
    x, y, z, w = q
    return np.array([
        [1 - 2 * (y * y + z * z), 2 * (x * y - z * w), 2 * (x * z + y * w)],
        [2 * (x * y + z * w), 1 - 2 * (x * x + z * z), 2 * (y * z - x * w)],
        [2 * (x * z - y * w), 2 * (y * z + x * w), 1 - 2 * (x * x + y * y)],
    ])


def node_local(node):
    if "matrix" in node:
        return np.asarray(node["matrix"], dtype=np.float64).reshape(4, 4).T
    m = np.eye(4)
    m[:3, :3] = quat_to_mat(node.get("rotation", [0, 0, 0, 1])) @ np.diag(node.get("scale", [1, 1, 1]))
    m[:3, 3] = node.get("translation", [0, 0, 0])
    return m


def node_worlds(document):
    nodes = document["nodes"]
    parent = {i: -1 for i in range(len(nodes))}
    for i, n in enumerate(nodes):
        for c in n.get("children", []):
            parent[c] = i
    world = {}

    def w(i):
        if i in world:
            return world[i]
        p = parent[i]
        m = node_local(nodes[i]) if p < 0 else w(p) @ node_local(nodes[i])
        world[i] = m
        return m
    for i in range(len(nodes)):
        w(i)
    return world, parent


def set_joint_translations(document, binary, names, new_local, report, key="joint_edits"):
    """Set the given joints' local translations, rebuild every inverse bind
    from the new rest, and rewrite the constant translation keys of the
    baked clips for those joints."""
    skin = document["skins"][0]
    nodes = document["nodes"]
    joints = skin["joints"]
    world, _ = node_worlds(document)
    ibms = accessor_array(document, binary, skin["inverseBindMatrices"])
    err = max(float(np.abs(np.linalg.inv(np.asarray(ibms[r]).reshape(4, 4).T)[:3, 3] - world[j][:3, 3]).max()) for r, j in enumerate(joints))
    if err > 2e-3:
        raise SystemExit("inverse binds do not match the node rest (%.4f m): a mesh node transform is in play" % err)
    changed = {}
    for name, vec in new_local.items():
        j = joints[names.index(name)]
        old_t = np.asarray(nodes[j].get("translation", [0, 0, 0]), dtype=np.float64)
        changed[j] = (name, old_t, np.asarray(vec, dtype=np.float64))
        nodes[j]["translation"] = [float(v) for v in vec]
    world, _ = node_worlds(document)
    new_ibms = np.zeros((len(joints), 16))
    for r, j in enumerate(joints):
        new_ibms[r] = np.linalg.inv(world[j]).T.reshape(-1)
    overwrite_accessor(document, binary, skin["inverseBindMatrices"], new_ibms)
    patched = 0
    for anim in document.get("animations", []):
        for ch in anim["channels"]:
            j = ch["target"]["node"]
            if ch["target"]["path"] == "translation" and j in changed:
                acc = anim["samplers"][ch["sampler"]]["output"]
                vals = accessor_array(document, binary, acc)
                vals[:] = changed[j][2]
                overwrite_accessor(document, binary, acc, vals)
                patched += 1
    report.setdefault(key, {}).update({v[0]: {"old_mm": [round(x * 1000) for x in v[1]], "new_mm": [round(x * 1000) for x in v[2]]} for v in changed.values()})
    report["clip_translation_keys_patched"] = report.get("clip_translation_keys_patched", 0) + patched


def set_arm_lengths(document, binary, names, lengths, report):
    """Re-length the given joints' local translations, direction kept."""
    nodes = document["nodes"]
    joints = document["skins"][0]["joints"]
    new_local = {}
    for name, L in lengths.items():
        t = np.asarray(nodes[joints[names.index(name)]].get("translation", [0, 0, 0]), dtype=np.float64)
        n = float(np.linalg.norm(t))
        if n > 1e-9:
            new_local[name] = t / n * L
    set_joint_translations(document, binary, names, new_local, report, key="arm_bones_edit")
    report["arm_bones"] = {k: {"old_mm": round(float(np.linalg.norm(v["old_mm"])), 0), "new_mm": round(float(np.linalg.norm(v["new_mm"])), 0)}
                           for k, v in report["arm_bones_edit"].items()}


BODY_SEGMENTS = [
    ("pelvis", "spine_01"), ("spine_01", "spine_02"), ("spine_02", "spine_03"), ("spine_03", "neck_01"),
    ("neck_01", "Head"), ("spine_03", "clavicle_l"), ("spine_03", "clavicle_r"),
    ("clavicle_l", "upperarm_l"), ("clavicle_r", "upperarm_r"),
    ("upperarm_l", "lowerarm_l"), ("lowerarm_l", "hand_l"), ("hand_l", "middle_01_l"),
    ("upperarm_r", "lowerarm_r"), ("lowerarm_r", "hand_r"), ("hand_r", "middle_01_r"),
    ("pelvis", "thigh_l"), ("thigh_l", "calf_l"), ("calf_l", "foot_l"), ("foot_l", "ball_l"),
    ("pelvis", "thigh_r"), ("thigh_r", "calf_r"), ("calf_r", "foot_r"), ("foot_r", "ball_r"),
]
ORPHAN_DISTANCE = 0.30      # a tail with no bones of its own sits this far from every segment
HEAD_REACH = 0.35           # the head segment is extended this much past the Head joint


def segment_distance(points, a, b, pad=0.05):
    axis = b - a
    L = float(np.linalg.norm(axis))
    unit = axis / L
    v = points - a
    t = np.clip(v @ unit, -pad, L + pad)
    return np.linalg.norm(points - (a + np.outer(t, unit)), axis=1)


def orphan_mask(points, rest):
    best = None
    for near, far in BODY_SEGMENTS:
        a, b = rest[near], rest[far]
        if near == "neck_01":
            b = a + (b - a) / max(np.linalg.norm(b - a), 1e-9) * HEAD_REACH
        d = segment_distance(points, a, b)
        best = d if best is None else np.minimum(best, d)
    return best > ORPHAN_DISTANCE


# ----------------------------------------------------------------- geometry helpers

def smoothstep(x, lo, hi):
    t = np.clip((x - lo) / max(hi - lo, 1e-9), 0.0, 1.0)
    return t * t * (3 - 2 * t)


def minimal_rotation(a, b):
    a = a / np.linalg.norm(a); b = b / np.linalg.norm(b)
    v = np.cross(a, b); c = float(np.dot(a, b)); s = float(np.linalg.norm(v))
    if s < 1e-9:
        if c > 0:
            return np.eye(3)
        p = np.array([1.0, 0, 0]) if abs(a[0]) < 0.9 else np.array([0, 1.0, 0])
        p = p - a * np.dot(p, a); p /= np.linalg.norm(p)
        return 2 * np.outer(p, p) - np.eye(3)
    vx = np.array([[0, -v[2], v[1]], [v[2], 0, -v[0]], [-v[1], v[0], 0]])
    return np.eye(3) + vx + vx @ vx * ((1 - c) / (s * s))


def polyline_project(points, poly):
    """Nearest point on a polyline for every point: (arc length u, distance, foot)."""
    best_d = np.full(len(points), np.inf)
    best_u = np.zeros(len(points))
    best_p = np.zeros_like(points)
    cum = np.concatenate([[0.0], np.cumsum(np.linalg.norm(np.diff(poly, axis=0), axis=1))])
    for i in range(len(poly) - 1):
        a, b = poly[i], poly[i + 1]
        axis = b - a; L = float(np.linalg.norm(axis))
        if L < 1e-9:
            continue
        unit = axis / L
        t = np.clip((points - a) @ unit, 0.0, L)
        foot = a + np.outer(t, unit)
        d = np.linalg.norm(points - foot, axis=1)
        better = d < best_d
        best_d[better] = d[better]
        best_u[better] = cum[i] + t[better]
        best_p[better] = foot[better]
    return best_u, best_d, best_p


def fit_centreline(points, start, bin_w=0.025, start_gap=0.04):
    """Polyline through the centroids of the points binned by their distance
    from `start` (monotonic down a limb), beginning at `start`.  Returns
    (polyline, r, dist, local tube radius per point) with r the distance
    from `start`, or None."""
    r = np.linalg.norm(points - start, axis=1)
    nb = max(int(float(r.max()) / bin_w) + 1, 2)
    idx = np.clip((r / bin_w).astype(int), 0, nb - 1)
    cents = []
    rads = []
    for k in range(nb):
        sel = idx == k
        if sel.sum() >= 8 and k * bin_w >= start_gap:
            c = points[sel].mean(axis=0)
            cents.append(c)
            rads.append(float(np.median(np.linalg.norm(points[sel] - c, axis=1))))
    if len(cents) < 2:
        return None
    cents = np.asarray(cents)
    sm = cents.copy()
    for _ in range(2):
        prev = sm.copy()
        for k in range(1, len(sm) - 1):
            sm[k] = 0.25 * prev[k - 1] + 0.5 * prev[k] + 0.25 * prev[k + 1]
    poly = np.concatenate([[start], sm], axis=0)
    radius = np.asarray([rads[0]] + rads)
    _, d, _ = polyline_project(points, poly)
    r_at = np.interp(r, np.linalg.norm(poly - start, axis=1), radius)
    return poly, r, d, r_at


def point_at_distance(poly, start, rr):
    """First point along the polyline at distance rr from start."""
    dist = np.linalg.norm(poly - start, axis=1)
    if rr >= dist[-1]:
        tail = poly[-1] - poly[-2]
        tail /= max(np.linalg.norm(tail), 1e-9)
        return poly[-1] + tail * (rr - dist[-1])
    for i in range(len(poly) - 1):
        if dist[i] <= rr <= dist[i + 1] or (i == 0 and rr < dist[1]):
            span = dist[i + 1] - dist[i]
            f = 0.0 if span < 1e-9 else (rr - dist[i]) / span
            return poly[i] + (poly[i + 1] - poly[i]) * f
    return poly[-1]


def poly_length(poly):
    return float(np.sum(np.linalg.norm(np.diff(poly, axis=0), axis=1)))


def angle(a, b):
    a = a / max(np.linalg.norm(a), 1e-12); b = b / max(np.linalg.norm(b), 1e-12)
    return math.degrees(math.acos(max(-1.0, min(1.0, float(np.dot(a, b))))))


# ----------------------------------------------------------------- limbs

LIMBS = {
    "arm_l": ("upperarm_l", "lowerarm_l", "hand_l"),
    "arm_r": ("upperarm_r", "lowerarm_r", "hand_r"),
    "leg_l": ("thigh_l", "calf_l", "foot_l"),
    "leg_r": ("thigh_r", "calf_r", "foot_r"),
}
FINGERS = ("index", "middle", "ring", "pinky", "thumb")
SKIP_DEG = 3.0              # a limb this close to its bones is left alone
SKIP_JOINT = 0.015          # ... and whose mesh joints land this close (m)
AXIAL_CLAMP = (0.85, 1.2)


def chain_bones(names, limb):
    side = limb[-1]
    if limb.startswith("arm"):
        return [n for n in names if n in ("upperarm_%s" % side, "lowerarm_%s" % side, "hand_%s" % side)
                or (n.startswith(FINGERS) and n.endswith("_" + side))]
    return ["%s_%s" % (p, side) for p in ("thigh", "calf", "foot", "ball")]


def chain_weight(dense, names, bones):
    idx = [names.index(b) for b in bones if b in names]
    return dense[:, idx].sum(axis=1)


def both_legs(dense, names, floor=0.15):
    """Skin the file binds to BOTH legs: a robe, a skirt, the crotch of a
    pair of trousers, boots fused at the ankle."""
    l = chain_weight(dense, names, ["thigh_l", "calf_l", "foot_l", "ball_l"])
    r = chain_weight(dense, names, ["thigh_r", "calf_r", "foot_r", "ball_r"])
    return (l >= floor) & (r >= floor)


def skirt_vertices(points, rest, dense, names, gap=0.09):
    """Both-leg cloth that hangs away from either whole leg below mid-thigh:
    a robe or a skirt.  A tunic hem sits at the hips, fused boots sit on a
    calf, so neither counts."""
    both = both_legs(dense, names)
    d = None
    for side in ("l", "r"):
        for a, b in (("thigh", "calf"), ("calf", "foot")):
            dd = segment_distance(points, rest["%s_%s" % (a, side)], rest["%s_%s" % (b, side)])
            d = dd if d is None else np.minimum(d, dd)
    low = points[:, 1] < 0.5 * (rest["thigh_l"][1] + rest["thigh_r"][1]) - 0.25
    return int((both & low & (d > gap)).sum())


def tip_joint(names, limb):
    side = limb[-1]
    if limb.startswith("arm"):
        for cand in ("middle_04_leaf_%s" % side, "middle_03_%s" % side, "middle_02_%s" % side, "middle_01_%s" % side):
            if cand in names:
                return cand
        return "hand_%s" % side
    return "ball_%s" % side


def weight_crossing(u, w_upper, w_lower, u_lo, u_hi, bin_w=0.015):
    """First distance between u_lo and u_hi where the lower segment's mean
    weight overtakes the upper's for three bins running, or None."""
    nb = int(u_hi / bin_w) + 2
    idx = np.clip((u / bin_w).astype(int), 0, nb - 1)
    means = []
    for k in range(nb):
        sel = idx == k
        if sel.sum() >= 4:
            means.append((k * bin_w + 0.5 * bin_w, float(w_upper[sel].mean()), float(w_lower[sel].mean())))
    for i in range(len(means) - 2):
        uu = means[i][0]
        if uu < u_lo or uu > u_hi:
            continue
        if all(means[i + j][2] > means[i + j][1] for j in range(3)):
            return uu
    return None


def analyse_limb(points, rest, orphan, dense, names, limb):
    """Fit the mesh chain of one limb and compare it with the rig's.  The
    limb parameter is the distance from the proximal joint."""
    a_name, b_name, c_name = LIMBS[limb]
    S, E, W = rest[a_name], rest[b_name], rest[c_name]
    T = rest[tip_joint(names, limb)]
    bones = chain_bones(names, limb)
    w_chain = chain_weight(dense, names, bones)
    other_limbs = [b for l2 in LIMBS if l2 != limb for b in chain_bones(names, l2)]
    w_other = chain_weight(dense, names, other_limbs)
    w_head = chain_weight(dense, names, [n for n in names if n in ("Head", "neck_01", "neck_02")])
    ok = (~orphan) & (w_other < 0.3) & (w_head < 0.3)
    if limb.startswith("arm"):
        ok &= points[:, 1] < S[1] + 0.10
        far = 0.20
        tube_k, beyond_k, min_w, rad_fade = 1.5, 2.5, 0.0, (2.5, 3.2)
    else:
        ok &= points[:, 1] < S[1] + 0.05
        far = 0.25
        tube_k, beyond_k, min_w, rad_fade = 1.5, 1.5, 0.2, (1.5, 2.0)
    seeds0 = ok & (w_chain >= 0.5)
    if seeds0.sum() < 100:
        return None
    fit = fit_centreline(points[seeds0], S)
    if fit is None:
        return None
    poly = fit[0]
    r_all = np.linalg.norm(points - S, axis=1)
    _, d_all, _ = polyline_project(points, poly)
    rad_bins = {}
    for uu, rr in zip(fit[1], fit[3]):
        rad_bins.setdefault(int(uu / 0.025), []).append(rr)

    def radius_at(uu):
        k = int(uu / 0.025)
        for kk in (k, k - 1, k + 1, k - 2, k + 2, k - 3, k + 3):
            if kk in rad_bins:
                return float(np.median(rad_bins[kk]))
        return 0.05
    tube_r = np.asarray([radius_at(uu) for uu in r_all])
    # seeds far outside the tube are growths that happen to carry limb
    # weights (Mycelari's shoulder brackets): not limb.  Near the torso the
    # file's own weights arbitrate; beyond it anything in the tube is limb
    # (the hand and the sleeve cuff included).
    seeds = seeds0 & (d_all < 2.0 * tube_r)
    near = ok & (d_all < tube_k * tube_r) & (r_all > 0.05) & (r_all <= far) & (w_chain >= 0.1)
    beyond = ok & (d_all < beyond_k * tube_r) & (r_all > far) & (w_chain >= min_w)
    cand = np.where(seeds | near | beyond)[0]
    if len(cand) < 100:
        return None
    fit = fit_centreline(points[cand], S)
    if fit is None:
        return None
    poly, u, d, r_at = fit
    reach = float(np.linalg.norm(poly[-1] - S))
    L_rig = float(np.linalg.norm(E - S) + np.linalg.norm(W - E) + np.linalg.norm(T - W))
    rho = float(np.linalg.norm(E - S) / (np.linalg.norm(E - S) + np.linalg.norm(W - E)))
    wl = dense[cand][:, names.index(b_name)]
    wh = chain_weight(dense[cand], names, [b for b in bones if b not in (a_name, b_name)])
    uW_prop = (float(np.linalg.norm(E - S)) + float(np.linalg.norm(W - E))) * reach / L_rig
    xW = weight_crossing(u, wl, wh, 0.5 * uW_prop, 1.4 * uW_prop)
    src = {"wrist": "weights" if xW is not None else "proportion", "elbow": "proportion"}
    uW = xW if xW is not None else uW_prop
    uE = rho * uW
    if not limb.startswith("arm"):
        wu = dense[cand][:, names.index(a_name)]
        xE = weight_crossing(u, wu, wl, 0.7 * uE, 1.3 * uE)
        if xE is not None:
            uE = xE; src["elbow"] = "weights"
    Em, Wm = point_at_distance(poly, S, uE), point_at_distance(poly, S, uW)
    f_w = smoothstep(w_chain[cand], 0.05, 0.5)
    return {
        "limb": limb, "cand": cand, "u": u, "d": d, "r_at": r_at, "poly": poly, "f_w": f_w, "far": far, "rad_fade": rad_fade,
        "S": S, "E": E, "W": W, "Em": Em, "Wm": Wm, "uE": uE, "uW": uW, "reach": reach, "joint_source": src,
        "wiggle": poly_length(poly) / max(reach, 1e-6), "seeds": int(seeds.sum()),
        "dev_upper": angle(Em - S, E - S), "dev_lower": angle(Wm - Em, W - E),
        "off_E": float(np.linalg.norm(Em - E)), "off_W": float(np.linalg.norm(Wm - W)),
        "len_upper_mesh": float(np.linalg.norm(Em - S)), "len_lower_mesh": float(np.linalg.norm(Wm - Em)),
    }


def membership(info, fade_len):
    """How much each candidate vertex belongs to the limb: faded in from the
    torso along the limb, by the file's own weights over the first
    centimetres and by tube membership beyond; faded out radially far
    outside the tube."""
    u, d, r_at, f_w = info["u"], info["d"], info["r_at"], info["f_w"]
    f_u = smoothstep(u, 0.0, fade_len)
    f = f_u * np.maximum(f_w, smoothstep(u, 0.08, 0.14))
    lo, hi = info["rad_fade"]
    f = f * (1.0 - smoothstep(d / np.maximum(r_at, 1e-3), lo, hi))
    return f


def straighten_raw(points, info, axial_clamp=AXIAL_CLAMP):
    """Where each candidate vertex goes when the mesh chain is laid on the
    rig's (unfaded displacement per candidate, plus the axial scales)."""
    cand, u = info["cand"], info["u"]
    S, E, W, Em, Wm = info["S"], info["E"], info["W"], info["Em"], info["Wm"]
    uE, uW = info["uE"], info["uW"]
    segs = []
    scales = []
    for (a_m, b_m, a_r, b_r) in ((S, Em, S, E), (Em, Wm, E, W)):
        dm = b_m - a_m; dr = b_r - a_r
        Lm = float(np.linalg.norm(dm)); Lr = float(np.linalg.norm(dr))
        R = minimal_rotation(dm, dr)
        s = float(np.clip(Lr / max(Lm, 1e-9), *axial_clamp))
        segs.append((a_m, a_r, dm / max(Lm, 1e-9), R, s))
        scales.append(s)
    a_m, a_r, um, R1, s1 = segs[1]
    Wm_mapped = a_r + R1 @ (um * (float(np.linalg.norm(Wm - a_m)) * s1))
    segs.append((Wm, Wm_mapped, um, R1, 1.0))
    pts = points[cand]
    out = np.zeros_like(pts)
    w0 = 1.0 - smoothstep(u, uE - 0.02, uE + 0.02)
    w2 = smoothstep(u, uW - 0.015, uW + 0.015)
    w1 = np.clip(1.0 - w0 - w2, 0.0, 1.0)
    for w, (a_m, a_r, unit, R, s) in zip((w0, w1, w2), segs):
        rel = pts - a_m
        axial = rel @ unit
        mapped = a_r + (R @ (rel + np.outer(axial * (s - 1.0), unit)).T).T
        out += mapped * w[:, None]
    return out - pts, scales


# ----------------------------------------------------------------- shoulders

def chest_halfwidth(points, rest, dense, names):
    """90th percentile |x| of trunk skin in a band just above spine_02, below
    the armpits, where the arms do not interfere."""
    trunk = chain_weight(dense, names, ["spine_01", "spine_02", "spine_03"])
    arms = chain_weight(dense, names, [n for n in names if n.startswith(("upperarm", "lowerarm", "hand", "clavicle"))])
    y0 = rest["spine_02"][1]
    band = (points[:, 1] > y0) & (points[:, 1] < y0 + 0.08) & (trunk > 0.5) & (arms < 0.2)
    return float(np.percentile(np.abs(points[band][:, 0]), 90)) if band.sum() >= 20 else float("nan")


def shoulder_targets(points, rest, dense, names, ref_ratios, max_dx=0.06, max_dy=0.08):
    """Where each shoulder joint should sit: the reference body's height
    fraction between spine_03 and neck_01, and its lateral ratio to the
    chest half-width, applied to this body; moves capped."""
    hw = chest_halfwidth(points, rest, dense, names)
    out = {}
    for s in ("l", "r"):
        sh = rest["upperarm_" + s]
        y_t = rest["spine_03"][1] + ref_ratios["height"] * (rest["neck_01"][1] - rest["spine_03"][1])
        x_t = np.sign(sh[0]) * ref_ratios["lateral"] * hw if np.isfinite(hw) else sh[0]
        dy = float(np.clip(y_t - sh[1], -max_dy, max_dy))
        dx = float(np.clip(x_t - sh[0], -max_dx, max_dx))
        # never push the joint outward: the ask is arms nearer the body
        if np.sign(dx) == np.sign(sh[0]):
            dx = 0.0
        out[s] = np.array([dx, dy, 0.0])
    return out, hw


def shoulder_ratios(points, rest, dense, names):
    hw = chest_halfwidth(points, rest, dense, names)
    sh = rest["upperarm_l"]
    return {"height": float((sh[1] - rest["spine_03"][1]) / (rest["neck_01"][1] - rest["spine_03"][1])),
            "lateral": float(abs(sh[0]) / hw) if np.isfinite(hw) else 1.0}


def shift_shoulder(points, rest, dense, names, side, delta):
    """Move the arm, its sleeve and the shoulder of the trunk by delta: the
    arm rigidly, the trunk fading in from 45 to 95 percent of the shoulder
    joint's lateral offset over the shoulder band, so the shoulder line
    slopes and the trunk stretches or compresses between neck and arm."""
    sh = rest["upperarm_" + side]
    x0 = abs(sh[0])
    same_side = np.sign(points[:, 0]) == np.sign(sh[0])
    arm = chain_weight(dense, names, chain_bones(names, "arm_" + side))
    lateral = smoothstep(np.abs(points[:, 0]), 0.45 * x0, 0.95 * x0)
    band = smoothstep(points[:, 1], sh[1] - 0.18, sh[1] - 0.06) * (1.0 - smoothstep(points[:, 1], sh[1] + 0.05, sh[1] + 0.12))
    w = np.maximum(smoothstep(arm, 0.05, 0.4), lateral * band)
    w = np.where(same_side, w, 0.0)
    return points + np.outer(w, delta), w


# ----------------------------------------------------------------- weights

def dense_weights(joints, weights, n_joints):
    dense = np.zeros((len(joints), n_joints))
    for k in range(joints.shape[1]):
        np.add.at(dense, (np.arange(len(joints)), joints[:, k]), weights[:, k])
    return dense


def sparse_weights(dense, slots=4):
    order = np.argsort(-dense, axis=1)[:, :slots]
    w = np.take_along_axis(dense, order, axis=1)
    s = w.sum(axis=1, keepdims=True)
    w = np.where(s > 1e-9, w / np.maximum(s, 1e-12), 0.0)
    w[:, 0] = np.where(s[:, 0] > 1e-9, w[:, 0], 1.0)
    order = np.where(w > 0, order, 0)
    return order, w


def transfer_segmented(points, sel, chain, donor_chain, donor_tree, donor_dense, k=6):
    """Weights for points[sel] from the donor, looked up at the corresponding
    place on the donor's limb: same fraction along the same segment, same
    offset from the bone."""
    poly = np.asarray(chain); dpoly = np.asarray(donor_chain)
    u, _, foot = polyline_project(points[sel], poly)
    perp = points[sel] - foot
    cum = np.concatenate([[0.0], np.cumsum(np.linalg.norm(np.diff(poly, axis=0), axis=1))])
    q = np.zeros_like(perp)
    for i in range(len(poly) - 1):
        L = cum[i + 1] - cum[i]
        in_seg = (u >= cum[i]) & (u <= cum[i + 1]) if i < len(poly) - 2 else (u >= cum[i])
        if not in_seg.any() or L < 1e-9:
            continue
        t = (u[in_seg] - cum[i]) / L
        R = minimal_rotation(poly[i + 1] - poly[i], dpoly[i + 1] - dpoly[i])
        q[in_seg] = dpoly[i] + np.outer(t, dpoly[i + 1] - dpoly[i]) + (R @ perp[in_seg].T).T
    d, idx = donor_tree.query(q, k=k)
    inv = 1.0 / np.maximum(d, 1e-4)
    inv /= inv.sum(axis=1, keepdims=True)
    return np.einsum("nk,nkj->nj", inv, donor_dense[idx]), d[:, 0]


# ----------------------------------------------------------------- girth

THIN_SEGMENTS = {"upperarm": "lowerarm", "lowerarm": "hand", "thigh": "calf", "calf": "foot"}


def girth(points, rest, orphan, dense, names, part, side, lo=0.35, hi=0.65, rmax=0.16):
    a = rest["%s_%s" % (part, side)]; b = rest["%s_%s" % (THIN_SEGMENTS[part], side)]
    axis = b - a; L = float(np.linalg.norm(axis)); unit = axis / L
    v = points - a
    t = v @ unit
    perp = np.linalg.norm(v - np.outer(t, unit), axis=1)
    w = dense[:, names.index("%s_%s" % (part, side))] + dense[:, names.index("%s_%s" % (THIN_SEGMENTS[part], side))]
    sel = (~orphan) & (t > lo * L) & (t < hi * L) & (perp < rmax) & (w > 0.5)
    if sel.sum() < 20:
        return float("nan")
    return float(np.median(perp[sel]))


def thin(points, rest, orphan, dense, names, scales):
    disp = np.zeros_like(points)
    keep = orphan | both_legs(dense, names)
    for (part, side), s in scales.items():
        if abs(s - 1.0) < 1e-4:
            continue
        a = rest["%s_%s" % (part, side)]; b = rest["%s_%s" % (THIN_SEGMENTS[part], side)]
        axis = b - a; unit = axis / np.linalg.norm(axis)
        v = points - a
        t = v @ unit
        perp = v - np.outer(t, unit)
        w = dense[:, names.index("%s_%s" % (part, side))]
        w = np.where(keep, 0.0, w)
        disp += perp * (s - 1.0) * w[:, None]
    return points + disp


# ----------------------------------------------------------------- normals

def smooth_normals(positions, tris, normals, touched):
    """Area-weighted normals accumulated per welded position, written back for
    the touched vertices and their neighbours."""
    key = np.round(positions / 1e-5).astype(np.int64)
    _, inv = np.unique(key, axis=0, return_inverse=True)
    inv = inv.reshape(-1)
    fn = np.cross(positions[tris[:, 1]] - positions[tris[:, 0]], positions[tris[:, 2]] - positions[tris[:, 0]])
    acc = np.zeros((inv.max() + 1, 3))
    for c in range(3):
        np.add.at(acc, inv[tris[:, c]], fn)
    n = acc[inv]
    l = np.linalg.norm(n, axis=1, keepdims=True)
    n = np.where(l > 1e-12, n / np.maximum(l, 1e-12), normals)
    touched_pos = np.zeros(inv.max() + 1, dtype=bool)
    touched_pos[inv[touched]] = True
    tri_touch = touched_pos[inv[tris]].any(axis=1)
    grow = np.zeros(len(positions), dtype=bool)
    grow[tris[tri_touch].reshape(-1)] = True
    grow |= touched
    out = normals.copy()
    out[grow] = n[grow]
    return out


# ----------------------------------------------------------------- main

def load_body(path):
    doc, blob = read_glb(path)
    prims = [p for n in doc["nodes"] if "mesh" in n and "skin" in n for p in doc["meshes"][n["mesh"]]["primitives"]]
    pos_acc = max(set(p["attributes"]["POSITION"] for p in prims),
                  key=lambda a: sum(1 for p in prims if p["attributes"]["POSITION"] == a))
    shared = [p for p in prims if p["attributes"]["POSITION"] == pos_acc]
    a0 = shared[0]["attributes"]
    names = joint_names(doc)
    rest = joint_rest(doc, blob)
    points = accessor_array(doc, blob, pos_acc)
    joints = accessor_array(doc, blob, a0["JOINTS_0"]).astype(np.int64)
    weights = accessor_array(doc, blob, a0["WEIGHTS_0"])
    dense = dense_weights(joints, weights, len(names))
    return doc, blob, pos_acc, shared, names, rest, points, dense


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("src"); ap.add_argument("luminous"); ap.add_argument("out")
    ap.add_argument("--report")
    ap.add_argument("--limb-target", type=float, default=0.9, help="girth target as a fraction of Luminous's")
    ap.add_argument("--thin-floor", type=float, default=0.8, help="never thin below this fraction of the body's own girth")
    ap.add_argument("--no-thin", action="store_true")
    ap.add_argument("--arm-scale", type=float, default=1.0, help="extra radial scale on upperarm and forearm (0.8 = 20 percent thinner)")
    ap.add_argument("--sleeve-frac", type=float, default=None, help="fit the arm: target radius = max(--sleeve-min, frac x segment length) for upperarm and forearm")
    ap.add_argument("--sleeve-min", type=float, default=0.045)
    ap.add_argument("--sleeve-floor", type=float, default=0.5, help="never scale the arm below this fraction of its own radius")
    ap.add_argument("--shoulders-from", default=None, help="place the shoulder joints like this body's (height between spine_03 and neck, lateral ratio to chest width), moving the mesh with them")
    ap.add_argument("--shoulder-max-move", type=float, default=0.04, help="cap on how far a shoulder joint moves, per axis (m)")
    ap.add_argument("--min-reach", type=float, default=None, help="shoulder-to-fingertip reach as a fraction of height; shorter arms get their bones and mesh stretched up to 25 percent")
    ap.add_argument("--only-thin", action="store_true", help="skip the chain analysis, rig and weights: thin only")
    ap.add_argument("--no-transfer", action="store_true")
    ap.add_argument("--no-legs", action="store_true")
    ap.add_argument("--no-rig", action="store_true", help="keep the rig's arm lengths and stretch the mesh instead")
    ap.add_argument("--skirt-vertices", type=int, default=150, help="this much both-leg cloth away from either leg is a robe: legs are left alone")
    ap.add_argument("--fade", type=float, default=0.07, help="fade-in length from the torso (m)")
    args = ap.parse_args(argv)

    out_norm = str(Path(args.out).resolve()).replace("\\", "/")
    if "/rabbitlands-client/" in out_norm or "/eloria-client/" in out_norm or "/wt-" in out_norm or "/dev-server/" in out_norm:
        raise SystemExit("refusing to write into a client checkout: " + out_norm)

    doc, blob, pos_acc, shared, names, rest, points, dense = load_body(args.src)
    a0 = shared[0]["attributes"]
    nrm_acc, j_acc, w_acc = a0.get("NORMAL"), a0["JOINTS_0"], a0["WEIGHTS_0"]
    assert all(p["attributes"]["JOINTS_0"] == j_acc and p["attributes"]["WEIGHTS_0"] == w_acc for p in shared)
    normals = accessor_array(doc, blob, nrm_acc) if nrm_acc is not None else None
    tris = np.concatenate([accessor_array(doc, blob, p["indices"]).astype(np.int64).reshape(-1, 3) for p in shared])
    orphan = orphan_mask(points, rest)
    _, _, _, _, lnames, lrest, lpos, ldense = load_body(args.luminous)
    assert lnames == names, "Luminous rig differs from the body's"
    both = both_legs(dense, names)
    report = {"source": args.src, "luminous": args.luminous, "output": args.out,
              "vertices": int(len(points)), "orphan_vertices": int(orphan.sum()),
              "both_leg_vertices": int(both.sum()), "skirt_vertices": skirt_vertices(points, rest, dense, names), "limbs": {}}
    skirted = report["skirt_vertices"] > args.skirt_vertices
    report["skirted"] = skirted

    # ---- 0: shoulders like the reference body's
    if args.shoulders_from and not args.only_thin:
        _, _, _, _, rnames, rrest, rpos, rdense = load_body(args.shoulders_from)
        ratios = shoulder_ratios(rpos, rrest, rdense, rnames)
        deltas, hw = shoulder_targets(points, rest, dense, names, ratios, max_dx=args.shoulder_max_move, max_dy=args.shoulder_max_move)
        moved_w = np.zeros(len(points))
        for side in ("l", "r"):
            points, w = shift_shoulder(points, rest, dense, names, side, deltas[side])
            moved_w = np.maximum(moved_w, w)
        world, _ = node_worlds(doc)
        joints = doc["skins"][0]["joints"]
        new_local = {}
        for side in ("l", "r"):
            j = joints[names.index("upperarm_" + side)]
            c = joints[names.index("clavicle_" + side)]
            p_new = world[j][:3, 3] + deltas[side]
            new_local["upperarm_" + side] = np.linalg.inv(world[c])[:3, :3] @ (p_new - world[c][:3, 3])
        set_joint_translations(doc, blob, names, new_local, report, key="shoulder_edit")
        rest = joint_rest(doc, blob)
        orphan = orphan_mask(points, rest)
        report["shoulders"] = {"reference_ratios": {k: round(v, 3) for k, v in ratios.items()}, "chest_halfwidth_mm": round(hw * 1000) if np.isfinite(hw) else None,
                               "moved_mm": {sd: [round(float(v) * 1000) for v in deltas[sd]] for sd in deltas},
                               "vertices_moved": int((moved_w > 0.01).sum())}

    # ---- 1: analyse every limb on the file as it is
    infos = {}
    for limb in LIMBS:
        if args.only_thin:
            report["limbs"][limb] = {"status": "skipped: thin only"}
            continue
        if (args.no_legs or skirted) and limb.startswith("leg"):
            report["limbs"][limb] = {"status": "skipped: robe or skirt bound to both legs" if skirted else "skipped"}
            continue
        info = analyse_limb(points, rest, orphan, dense, names, limb)
        if info is None:
            report["limbs"][limb] = {"status": "no chain found"}
            continue
        infos[limb] = info
        report["limbs"][limb] = {
            "candidates": int(len(info["cand"])), "seeds": info["seeds"], "wiggle": round(info["wiggle"], 3),
            "reach_mm": round(info["reach"] * 1000), "joint_source": info["joint_source"],
            "mesh_segment_mm": [round(info["len_upper_mesh"] * 1000), round(info["len_lower_mesh"] * 1000)],
            "rig_segment_mm": [round(float(np.linalg.norm(info["E"] - info["S"])) * 1000), round(float(np.linalg.norm(info["W"] - info["E"])) * 1000)],
            "before": {"upper_deg": round(info["dev_upper"], 1), "lower_deg": round(info["dev_lower"], 1),
                       "elbow_off_mm": round(info["off_E"] * 1000, 1), "wrist_off_mm": round(info["off_W"] * 1000, 1)}}

    # ---- 2: size the arm bones to the mesh
    stretch = {}
    if not args.no_rig:
        lengths = {}
        height = float(points[:, 1].max() - points[:, 1].min())
        for limb in ("arm_l", "arm_r"):
            info = infos.get(limb)
            if info is None:
                continue
            a_name, b_name, c_name = LIMBS[limb]
            factor = 1.0
            if args.min_reach is not None and info["reach"] < args.min_reach * height:
                factor = float(np.clip(args.min_reach * height / max(info["reach"], 1e-6), 1.0, 1.25))
            stretch[limb] = factor
            lengths[b_name] = info["len_upper_mesh"] * factor
            lengths[c_name] = info["len_lower_mesh"] * factor
        report["arm_stretch"] = {k: round(v, 3) for k, v in stretch.items()}
        report["reach_over_height"] = {k: round(infos[k]["reach"] / height, 3) for k in stretch}
        if lengths:
            set_arm_lengths(doc, blob, names, lengths, report)
            rest = joint_rest(doc, blob)
            for limb in ("arm_l", "arm_r"):
                if limb in infos:
                    i = infos[limb]
                    a_name, b_name, c_name = LIMBS[limb]
                    i["S"], i["E"], i["W"] = rest[a_name], rest[b_name], rest[c_name]
                    i["dev_upper"] = angle(i["Em"] - i["S"], i["E"] - i["S"]); i["dev_lower"] = angle(i["Wm"] - i["Em"], i["W"] - i["E"])
                    i["off_E"] = float(np.linalg.norm(i["Em"] - i["E"])); i["off_W"] = float(np.linalg.norm(i["Wm"] - i["W"]))

    # ---- 3: straighten, every limb measured on the same original points and
    # blended by proximity where two limbs claim the same skin
    original = points.copy()
    members = {}
    disp_sum = np.zeros_like(points); claim = np.zeros(len(points)); strength = np.zeros(len(points))
    straightened = []
    for limb, info in infos.items():
        entry = report["limbs"][limb]
        f = membership(info, args.fade)
        full = np.zeros(len(points)); full[info["cand"]] = f
        members[limb] = full
        needs = (info["dev_upper"] > SKIP_DEG or info["dev_lower"] > SKIP_DEG
                 or info["off_E"] > SKIP_JOINT or info["off_W"] > SKIP_JOINT * 1.5)
        if not needs:
            entry["status"] = "already on the bones"
            continue
        clamp = (0.9, max(1.1, stretch.get(limb, 1.0) + 0.02)) if limb.startswith("arm") else AXIAL_CLAMP
        raw, scales = straighten_raw(original, info, clamp)
        c = f / (info["d"] + 0.02)
        cand = info["cand"]
        disp_sum[cand] += raw * c[:, None]
        claim[cand] += c
        strength[cand] = np.maximum(strength[cand], f)
        entry["axial_scale"] = [round(s, 3) for s in scales]
        entry["status"] = "straightened"
        straightened.append(limb)
    has = claim > 1e-12
    points[has] = original[has] + disp_sum[has] / claim[has][:, None] * strength[has][:, None]
    for limb in straightened:
        after = analyse_limb(points, rest, orphan, dense, names, limb)
        if after is not None:
            report["limbs"][limb]["after"] = {"upper_deg": round(after["dev_upper"], 1), "lower_deg": round(after["dev_lower"], 1),
                                              "elbow_off_mm": round(after["off_E"] * 1000, 1), "wrist_off_mm": round(after["off_W"] * 1000, 1)}

    # ---- 4: re-donate the limb weights from Luminous, per segment; skin two
    # limbs both claim gets a proximity crossfade, both-leg cloth keeps its own
    if not args.no_transfer:
        cape = np.array([n.startswith("cape") for n in names])
        ldense = ldense.copy(); ldense[:, cape] = 0.0
        tree = cKDTree(lpos)
        stats = {}
        donated = np.zeros_like(dense); wclaim = np.zeros(len(points)); wstrength = np.zeros(len(points))
        for limb, info in infos.items():
            entry = report["limbs"][limb]
            if limb.startswith("leg") and entry["status"] != "straightened":
                continue
            a_name, b_name, c_name = LIMBS[limb]
            cand, u = info["cand"], info["u"]
            f = members[limb][cand] * (1.0 - smoothstep(u, info["uW"] - 0.03, info["uW"] - 0.005))
            f = np.where(both[cand], 0.0, f)
            pick = f > 0.01
            sel = cand[pick]; fsel = f[pick]
            if len(sel) == 0:
                continue
            chain = [rest[a_name], rest[b_name], rest[c_name]]
            dchain = [lrest[a_name], lrest[b_name], lrest[c_name]]
            new, dist = transfer_segmented(points, sel, chain, dchain, tree, ldense)
            prox = 1.0 / (info["d"][pick] + 0.02)
            donated[sel] += new * (fsel * prox)[:, None]
            wclaim[sel] += fsel * prox
            wstrength[sel] = np.maximum(wstrength[sel], fsel)
            stats[limb] = {"vertices": int(len(sel)), "donor_distance_median_mm": round(float(np.median(dist)) * 1000, 1),
                           "donor_distance_p95_mm": round(float(np.percentile(dist, 95)) * 1000, 1)}
        hasw = wclaim > 1e-12
        mix = donated[hasw] / wclaim[hasw][:, None]
        dense[hasw] = dense[hasw] * (1.0 - wstrength[hasw][:, None]) + mix * wstrength[hasw][:, None]
        report["weight_transfer"] = stats

    # ---- 5: thin toward Luminous
    if not args.no_thin:
        lorphan = orphan_mask(lpos, lrest)
        scales = {}
        girths = {}
        for part in THIN_SEGMENTS:
            if skirted and part in ("thigh", "calf"):
                continue
            target = float(np.nanmean([girth(lpos, lrest, lorphan, ldense, lnames, part, s) for s in ("l", "r")])) * args.limb_target
            owns = {side: girth(points, rest, orphan, dense, names, part, side) for side in ("l", "r")}
            finite = [v for v in owns.values() if np.isfinite(v)]
            sym = float(np.mean(finite)) if finite else float("nan")      # one girth per segment, or the arms come out uneven
            for side in ("l", "r"):
                own = sym
                girths["%s_%s" % (part, side)] = {"own_mm": round(own * 1000, 1), "target_mm": round(target * 1000, 1), "measured_mm": round(owns[side] * 1000, 1) if np.isfinite(owns[side]) else None}
                if not np.isfinite(own) or not np.isfinite(target) or own < 1e-4:
                    scales[(part, side)] = 1.0
                    continue
                scales[(part, side)] = float(np.clip(target / own, args.thin_floor, 1.0))
        for (part, side) in list(scales):
            if part in ("upperarm", "lowerarm"):
                if args.sleeve_frac is not None:
                    own = girths["%s_%s" % (part, side)]["own_mm"] / 1000.0
                    L = float(np.linalg.norm(rest["%s_%s" % (THIN_SEGMENTS[part], side)] - rest["%s_%s" % (part, side)]))
                    target = max(args.sleeve_min, args.sleeve_frac * L)
                    girths["%s_%s" % (part, side)]["target_mm"] = round(target * 1000, 1)
                    scales[(part, side)] = float(np.clip(target / own, args.sleeve_floor, 1.0)) if own > 1e-4 else 1.0
                scales[(part, side)] *= args.arm_scale
        points = thin(points, rest, orphan, dense, names, scales)
        report["thin"] = {"%s_%s" % k: {"scale": round(v, 3), **girths["%s_%s" % k]} for k, v in scales.items()}

    # ---- write back
    moved = np.linalg.norm(points - original, axis=1) > 1e-7
    report["vertices_moved"] = int(moved.sum())
    report["max_move_mm"] = round(float(np.linalg.norm(points - original, axis=1).max()) * 1000, 1)
    overwrite_accessor(doc, blob, pos_acc, points)
    if normals is not None:
        overwrite_accessor(doc, blob, nrm_acc, smooth_normals(points, tris, normals, moved))
    order, w = sparse_weights(dense)
    overwrite_accessor(doc, blob, j_acc, order)
    overwrite_accessor(doc, blob, w_acc, w)
    extras = doc.setdefault("asset", {}).setdefault("extras", {})
    extras["eloriaLimbFix"] = {"straightened": [k for k, v in report["limbs"].items() if v.get("status") == "straightened"],
                               "armBones": report.get("arm_bones"), "thinned": not args.no_thin, "limbTarget": args.limb_target,
                               "armScale": args.arm_scale, "skirted": skirted}
    write_glb(args.out, doc, blob)
    if args.report:
        Path(args.report).write_text(json.dumps(report, indent=1))
    summary = ", ".join("%s %s (%.0f/%.0f -> %s)" % (k, v.get("status", "?"), v.get("before", {}).get("upper_deg", 0), v.get("before", {}).get("lower_deg", 0),
                        "%.0f/%.0f" % (v["after"]["upper_deg"], v["after"]["lower_deg"]) if "after" in v else "-") for k, v in report["limbs"].items())
    print("[limbfix] %s: %s; arm bones %s; moved %d verts (max %.0f mm) -> %s" % (
        Path(args.src).name, summary, report.get("arm_bones", "-"), report["vertices_moved"], report["max_move_mm"], args.out))
    return 0


if __name__ == "__main__":
    sys.exit(main())
