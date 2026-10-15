"""glbkit.py -- minimal glTF-binary reader/writer and the rotation maths the
retarget needs.

Self-contained on purpose: this tool sits beside `rigged_races/`, it does not
import from it, and it runs on a plain `python` with numpy rather than
`eloria-tools\\.venv`.

Everything here works in glTF conventions: quaternions are [x, y, z, w],
matrices are column-vector 4x4 (M @ v), and a node's local transform is
T * R * S.
"""

from __future__ import annotations

import json
import struct
from pathlib import Path

import numpy as np

JSON_CHUNK = 0x4E4F534A
BIN_CHUNK = 0x004E4942
GLB_MAGIC = 0x46546C67

COMPONENT = {5120: "i1", 5121: "u1", 5122: "i2", 5123: "u2", 5125: "u4", 5126: "f4"}
COUNT = {"SCALAR": 1, "VEC2": 2, "VEC3": 3, "VEC4": 4, "MAT2": 4, "MAT3": 9, "MAT4": 16}


# --------------------------------------------------------------------------
# container
# --------------------------------------------------------------------------

def read(path: Path) -> tuple[dict, bytes]:
    """Return (gltf json, binary chunk) for a .glb."""
    data = Path(path).read_bytes()
    magic, _version, _length = struct.unpack_from("<III", data, 0)
    if magic != GLB_MAGIC:
        raise ValueError("%s is not a glb" % path)
    offset = 12
    gltf: dict | None = None
    blob = b""
    while offset < len(data):
        chunk_length, chunk_type = struct.unpack_from("<II", data, offset)
        chunk = data[offset + 8:offset + 8 + chunk_length]
        if chunk_type == JSON_CHUNK:
            gltf = json.loads(chunk.decode("utf-8"))
        elif chunk_type == BIN_CHUNK:
            blob = chunk
        offset += 8 + chunk_length
        if offset % 4:
            offset += 4 - offset % 4
    if gltf is None:
        raise ValueError("%s has no JSON chunk" % path)
    return gltf, blob


def write(path: Path, gltf: dict, blob: bytes) -> None:
    """Write a .glb, padding both chunks to the 4-byte alignment the spec wants."""
    if gltf.get("buffers"):
        gltf["buffers"][0]["byteLength"] = len(blob)
        gltf["buffers"][0].pop("uri", None)
    text = json.dumps(gltf, separators=(",", ":")).encode("utf-8")
    text += b" " * ((4 - len(text) % 4) % 4)
    body = bytes(blob) + b"\0" * ((4 - len(blob) % 4) % 4)
    total = 12 + 8 + len(text) + (8 + len(body) if body else 0)
    out = bytearray()
    out += struct.pack("<III", GLB_MAGIC, 2, total)
    out += struct.pack("<II", len(text), JSON_CHUNK) + text
    if body:
        out += struct.pack("<II", len(body), BIN_CHUNK) + body
    Path(path).write_bytes(bytes(out))


def accessor(gltf: dict, blob: bytes, index: int) -> np.ndarray:
    """Read accessor `index` as float64, shape (count, components)."""
    acc = gltf["accessors"][index]
    n = COUNT[acc["type"]]
    dtype = np.dtype("<" + COMPONENT[acc["componentType"]])
    if "bufferView" not in acc:
        return np.zeros((acc["count"], n))
    view = gltf["bufferViews"][acc["bufferView"]]
    start = view.get("byteOffset", 0) + acc.get("byteOffset", 0)
    stride = view.get("byteStride") or n * dtype.itemsize
    if stride == n * dtype.itemsize:
        flat = np.frombuffer(blob, dtype=dtype, count=acc["count"] * n, offset=start)
        return flat.reshape(acc["count"], n).astype(np.float64)
    out = np.zeros((acc["count"], n), dtype=np.float64)
    for i in range(acc["count"]):
        out[i] = np.frombuffer(blob, dtype=dtype, count=n, offset=start + i * stride)
    return out


def compact(gltf: dict, blob: bytes) -> tuple[dict, bytes]:
    """Drop accessors and bufferViews nothing references any more.

    Replacing a model's animations orphans every accessor the old clips used;
    without this the bytes stay in the file and glasswarden_female's ten
    discarded clips would ride along in all sixteen outputs.
    """
    used_accessors: set[int] = set()
    for mesh in gltf.get("meshes", []):
        for prim in mesh.get("primitives", []):
            used_accessors.update(prim.get("attributes", {}).values())
            if "indices" in prim:
                used_accessors.add(prim["indices"])
            for morph in prim.get("targets", []):
                used_accessors.update(morph.values())
    for skin in gltf.get("skins", []):
        if "inverseBindMatrices" in skin:
            used_accessors.add(skin["inverseBindMatrices"])
    for clip in gltf.get("animations", []):
        for sampler in clip.get("samplers", []):
            used_accessors.update((sampler["input"], sampler["output"]))

    accessors = gltf.get("accessors", [])
    keep_accessors = sorted(used_accessors)
    accessor_map = {old: new for new, old in enumerate(keep_accessors)}

    used_views = {accessors[i]["bufferView"] for i in keep_accessors
                  if "bufferView" in accessors[i]}
    used_views.update(image["bufferView"] for image in gltf.get("images", [])
                      if "bufferView" in image)
    keep_views = sorted(used_views)
    view_map = {old: new for new, old in enumerate(keep_views)}

    out = bytearray()
    new_views = []
    for old in keep_views:
        view = dict(gltf["bufferViews"][old])
        start = view.get("byteOffset", 0)
        chunk = bytes(blob[start:start + view["byteLength"]])
        while len(out) % 4:
            out.append(0)
        view["byteOffset"] = len(out)
        out += chunk
        new_views.append(view)

    new_accessors = []
    for old in keep_accessors:
        acc = dict(accessors[old])
        if "bufferView" in acc:
            acc["bufferView"] = view_map[acc["bufferView"]]
        new_accessors.append(acc)

    gltf["bufferViews"] = new_views
    gltf["accessors"] = new_accessors
    for mesh in gltf.get("meshes", []):
        for prim in mesh.get("primitives", []):
            prim["attributes"] = {k: accessor_map[v] for k, v in prim["attributes"].items()}
            if "indices" in prim:
                prim["indices"] = accessor_map[prim["indices"]]
            for morph in prim.get("targets", []):
                for key in list(morph):
                    morph[key] = accessor_map[morph[key]]
    for skin in gltf.get("skins", []):
        if "inverseBindMatrices" in skin:
            skin["inverseBindMatrices"] = accessor_map[skin["inverseBindMatrices"]]
    for clip in gltf.get("animations", []):
        for sampler in clip.get("samplers", []):
            sampler["input"] = accessor_map[sampler["input"]]
            sampler["output"] = accessor_map[sampler["output"]]
    for image in gltf.get("images", []):
        if "bufferView" in image:
            image["bufferView"] = view_map[image["bufferView"]]
    return gltf, bytes(out)


class BufferAppender:
    """Accumulates new bufferViews/accessors onto an existing glb's buffer 0."""

    def __init__(self, gltf: dict, blob: bytes) -> None:
        self.gltf = gltf
        self.blob = bytearray(blob)
        gltf.setdefault("bufferViews", [])
        gltf.setdefault("accessors", [])
        gltf.setdefault("buffers", [{"byteLength": 0}])

    def add(self, values: np.ndarray, kind: str) -> int:
        """Append float32 data and return the new accessor index."""
        data = np.ascontiguousarray(values, dtype="<f4")
        while len(self.blob) % 4:
            self.blob.append(0)
        offset = len(self.blob)
        self.blob += data.tobytes()
        self.gltf["bufferViews"].append(
            {"buffer": 0, "byteOffset": offset, "byteLength": data.nbytes})
        flat = data.reshape(data.shape[0], -1)
        self.gltf["accessors"].append({
            "bufferView": len(self.gltf["bufferViews"]) - 1,
            "componentType": 5126,
            "count": int(data.shape[0]),
            "type": kind,
            "min": [float(v) for v in flat.min(axis=0)],
            "max": [float(v) for v in flat.max(axis=0)],
        })
        return len(self.gltf["accessors"]) - 1


# --------------------------------------------------------------------------
# transforms
# --------------------------------------------------------------------------

def quat_to_matrix(q: np.ndarray) -> np.ndarray:
    """[x,y,z,w] (possibly batched) -> (..., 3, 3) rotation matrix."""
    q = np.asarray(q, dtype=np.float64)
    q = q / np.linalg.norm(q, axis=-1, keepdims=True)
    x, y, z, w = q[..., 0], q[..., 1], q[..., 2], q[..., 3]
    m = np.empty(q.shape[:-1] + (3, 3))
    m[..., 0, 0] = 1 - 2 * (y * y + z * z)
    m[..., 0, 1] = 2 * (x * y - z * w)
    m[..., 0, 2] = 2 * (x * z + y * w)
    m[..., 1, 0] = 2 * (x * y + z * w)
    m[..., 1, 1] = 1 - 2 * (x * x + z * z)
    m[..., 1, 2] = 2 * (y * z - x * w)
    m[..., 2, 0] = 2 * (x * z - y * w)
    m[..., 2, 1] = 2 * (y * z + x * w)
    m[..., 2, 2] = 1 - 2 * (x * x + y * y)
    return m


def matrix_to_quat(m: np.ndarray) -> np.ndarray:
    """(3,3) rotation matrix -> [x,y,z,w]. Shepperd's method, branch on trace."""
    m = np.asarray(m, dtype=np.float64)
    trace = m[0, 0] + m[1, 1] + m[2, 2]
    if trace > 0.0:
        s = np.sqrt(trace + 1.0) * 2.0
        q = np.array([(m[2, 1] - m[1, 2]) / s, (m[0, 2] - m[2, 0]) / s,
                      (m[1, 0] - m[0, 1]) / s, 0.25 * s])
    elif m[0, 0] > m[1, 1] and m[0, 0] > m[2, 2]:
        s = np.sqrt(1.0 + m[0, 0] - m[1, 1] - m[2, 2]) * 2.0
        q = np.array([0.25 * s, (m[0, 1] + m[1, 0]) / s, (m[0, 2] + m[2, 0]) / s,
                      (m[2, 1] - m[1, 2]) / s])
    elif m[1, 1] > m[2, 2]:
        s = np.sqrt(1.0 + m[1, 1] - m[0, 0] - m[2, 2]) * 2.0
        q = np.array([(m[0, 1] + m[1, 0]) / s, 0.25 * s, (m[1, 2] + m[2, 1]) / s,
                      (m[0, 2] - m[2, 0]) / s])
    else:
        s = np.sqrt(1.0 + m[2, 2] - m[0, 0] - m[1, 1]) * 2.0
        q = np.array([(m[0, 2] + m[2, 0]) / s, (m[1, 2] + m[2, 1]) / s, 0.25 * s,
                      (m[1, 0] - m[0, 1]) / s])
    return q / np.linalg.norm(q)


def orthonormalise(m: np.ndarray) -> np.ndarray:
    """Nearest rotation matrix, so accumulated scale never leaks into a quaternion."""
    u, _s, vt = np.linalg.svd(m[:3, :3])
    r = u @ vt
    if np.linalg.det(r) < 0:
        u[:, -1] *= -1
        r = u @ vt
    return r


def rotations_of(m: np.ndarray) -> np.ndarray:
    """(..., 4, 4) or (..., 3, 3) -> (..., 3, 3) with unit-length columns.

    The batched stand-in for orthonormalise(). These matrices are products of
    rotations and uniform scales -- the meshy rigs hang their joints under an
    Armature scaled to 0.01 -- so normalising each column recovers the rotation
    exactly, without an SVD per frame.
    """
    r = np.asarray(m, dtype=np.float64)[..., :3, :3]
    return r / np.maximum(np.linalg.norm(r, axis=-2, keepdims=True), 1e-12)


def matrices_to_quats(m: np.ndarray) -> np.ndarray:
    """(N, 3, 3) rotation matrices -> (N, 4) [x,y,z,w]. Batched Shepperd."""
    m = np.asarray(m, dtype=np.float64)
    m00, m01, m02 = m[:, 0, 0], m[:, 0, 1], m[:, 0, 2]
    m10, m11, m12 = m[:, 1, 0], m[:, 1, 1], m[:, 1, 2]
    m20, m21, m22 = m[:, 2, 0], m[:, 2, 1], m[:, 2, 2]
    trace = m00 + m11 + m22
    out = np.zeros((m.shape[0], 4))

    big_trace = trace > 0
    big_x = (~big_trace) & (m00 >= m11) & (m00 >= m22)
    big_y = (~big_trace) & (~big_x) & (m11 >= m22)
    big_z = ~(big_trace | big_x | big_y)

    def branch(mask, s, x, y, z, w):
        if not mask.any():
            return
        out[mask, 0] = (x / s)[mask]
        out[mask, 1] = (y / s)[mask]
        out[mask, 2] = (z / s)[mask]
        out[mask, 3] = (w / s)[mask]

    s = np.sqrt(np.maximum(trace + 1.0, 1e-20)) * 2.0
    branch(big_trace, s, m21 - m12, m02 - m20, m10 - m01, 0.25 * s * s)
    s = np.sqrt(np.maximum(1.0 + m00 - m11 - m22, 1e-20)) * 2.0
    branch(big_x, s, 0.25 * s * s, m01 + m10, m02 + m20, m21 - m12)
    s = np.sqrt(np.maximum(1.0 + m11 - m00 - m22, 1e-20)) * 2.0
    branch(big_y, s, m01 + m10, 0.25 * s * s, m12 + m21, m02 - m20)
    s = np.sqrt(np.maximum(1.0 + m22 - m00 - m11, 1e-20)) * 2.0
    branch(big_z, s, m02 + m20, m12 + m21, 0.25 * s * s, m10 - m01)

    return out / np.maximum(np.linalg.norm(out, axis=1, keepdims=True), 1e-12)


def slerp_batch(a: np.ndarray, b: np.ndarray, t: np.ndarray) -> np.ndarray:
    """Per-row slerp of (N,4) to (N,4) at (N,) parameters."""
    a = np.asarray(a, dtype=np.float64)
    b = np.asarray(b, dtype=np.float64)
    dot = np.sum(a * b, axis=1)
    b = np.where(dot[:, None] < 0, -b, b)
    dot = np.clip(np.abs(dot), -1.0, 1.0)
    theta = np.arccos(dot)
    sin_theta = np.sin(theta)
    safe = np.maximum(sin_theta, 1e-9)
    out = (np.sin((1 - t) * theta) / safe)[:, None] * a + (np.sin(t * theta) / safe)[:, None] * b
    linear = a + (b - a) * t[:, None]
    out = np.where((dot > 0.9995)[:, None], linear, out)
    return out / np.maximum(np.linalg.norm(out, axis=1, keepdims=True), 1e-12)


def trs_matrix(translation, rotation, scale) -> np.ndarray:
    m = np.eye(4)
    m[:3, :3] = quat_to_matrix(np.asarray(rotation, dtype=np.float64)) * np.asarray(
        scale, dtype=np.float64)
    m[:3, 3] = np.asarray(translation, dtype=np.float64)
    return m


def node_matrix(node: dict) -> np.ndarray:
    if "matrix" in node:
        return np.asarray(node["matrix"], dtype=np.float64).reshape(4, 4).T
    return trs_matrix(node.get("translation", [0, 0, 0]),
                      node.get("rotation", [0, 0, 0, 1]),
                      node.get("scale", [1, 1, 1]))


def slerp(a: np.ndarray, b: np.ndarray, t: float) -> np.ndarray:
    a = np.asarray(a, dtype=np.float64)
    b = np.asarray(b, dtype=np.float64)
    dot = float(np.dot(a, b))
    if dot < 0.0:
        b = -b
        dot = -dot
    if dot > 0.9995:
        out = a + t * (b - a)
        return out / np.linalg.norm(out)
    theta = np.arccos(np.clip(dot, -1.0, 1.0))
    sin_theta = np.sin(theta)
    return (np.sin((1 - t) * theta) / sin_theta) * a + (np.sin(t * theta) / sin_theta) * b


def unroll(quats: np.ndarray) -> np.ndarray:
    """Flip signs so consecutive quaternions take the short way round.

    glTF LINEAR interpolation of rotations is a slerp per segment, and a sign
    flip between two keys makes that segment spin the long way. Blender writes
    curves already unrolled; anything we rebuild key by key has to be too.
    """
    out = np.array(quats, dtype=np.float64, copy=True)
    if len(out) < 2:
        return out
    # Flipping key i also flips how key i+1 is judged, so the running sign is
    # the cumulative product of the raw pairwise signs.
    pairwise = np.sum(out[1:] * out[:-1], axis=1)
    signs = np.concatenate([[1.0], np.cumprod(np.where(pairwise < 0, -1.0, 1.0))])
    return out * signs[:, None]


# --------------------------------------------------------------------------
# hierarchy
# --------------------------------------------------------------------------

def parents_of(gltf: dict) -> dict[int, int]:
    parent: dict[int, int] = {}
    for index, node in enumerate(gltf.get("nodes", [])):
        for child in node.get("children", []):
            parent[child] = index
    return parent


def globals_of(gltf: dict, locals_: dict[int, np.ndarray] | None = None) -> dict[int, np.ndarray]:
    """World matrix per node, walking every scene root.

    `locals_` overrides a node's local matrix, which is how a sampled animation
    frame is posed without touching the document.
    """
    out: dict[int, np.ndarray] = {}
    nodes = gltf.get("nodes", [])
    roots = set()
    for scene in gltf.get("scenes", []):
        roots.update(scene.get("nodes", []))
    if not roots:
        child_of = parents_of(gltf)
        roots = {i for i in range(len(nodes)) if i not in child_of}

    stack = [(index, np.eye(4)) for index in sorted(roots)]
    while stack:
        index, parent_matrix = stack.pop()
        local = (locals_ or {}).get(index)
        if local is None:
            local = node_matrix(nodes[index])
        world = parent_matrix @ local
        out[index] = world
        for child in nodes[index].get("children", []):
            stack.append((child, world))
    return out


def topological(gltf: dict, indices) -> list[int]:
    """`indices` ordered parents-before-children."""
    parent = parents_of(gltf)
    wanted = set(indices)
    depth = {}
    for index in wanted:
        d, walk = 0, index
        while walk in parent:
            walk = parent[walk]
            d += 1
        depth[index] = d
    return sorted(wanted, key=lambda i: (depth[i], i))
