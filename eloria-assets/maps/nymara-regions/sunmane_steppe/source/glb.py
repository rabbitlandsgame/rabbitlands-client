"""Production glTF 2.0 / GLB writer for Eloria region packages.

The pre-existing `build_native_nymara_glbs.GLB` helper bakes every transform
into vertex data, exposes only a base-colour texture and never emits tangents.
A production region needs true node instancing, a full metallic-roughness
material set and tangent vectors for normal mapping, so this writer replaces it
for map work while keeping the same self-contained single-buffer GLB layout the
Godot loader expects (`GLTFDocument.append_from_file`).

Only core glTF 2.0 is emitted - no extensions - because the client's loader is
stock `GLTFDocument` and unsupported extensions would have to be implemented in
the client first.
"""
from __future__ import annotations

import json
import math
import struct
from pathlib import Path

import numpy as np

ARRAY_BUFFER = 34962
ELEMENT_ARRAY_BUFFER = 34963

COMPONENT_TYPES = {
    np.dtype("float32"): 5126,
    np.dtype("uint32"): 5125,
    np.dtype("uint16"): 5123,
    np.dtype("uint8"): 5121,
}

TYPE_COMPONENTS = {"SCALAR": 1, "VEC2": 2, "VEC3": 3, "VEC4": 4}


def _align(value: int, alignment: int = 4) -> int:
    return (value + alignment - 1) // alignment * alignment


class Geometry:
    """Indexed triangle soup in a mesh's own local space."""

    __slots__ = ("positions", "normals", "uvs", "indices", "colors")

    def __init__(self) -> None:
        self.positions: list[np.ndarray] = []
        self.normals: list[np.ndarray] = []
        self.uvs: list[np.ndarray] = []
        self.indices: list[np.ndarray] = []
        self.colors: list[np.ndarray] = []

    # ---------------------------------------------------------------- adding
    def add(self, positions, normals, uvs, indices, colors=None) -> None:
        positions = np.asarray(positions, dtype="float32").reshape(-1, 3)
        normals = np.asarray(normals, dtype="float32").reshape(-1, 3)
        uvs = np.asarray(uvs, dtype="float32").reshape(-1, 2)
        indices = np.asarray(indices, dtype="uint32").reshape(-1)
        if not (len(positions) == len(normals) == len(uvs)):
            raise ValueError("attribute counts differ")
        if colors is None:
            colors = np.ones((len(positions), 4), dtype="float32")
        else:
            colors = np.asarray(colors, dtype="float32").reshape(-1, 4)
            if len(colors) != len(positions):
                raise ValueError("colour count differs from vertex count")
        offset = self.vertex_count
        self.positions.append(positions)
        self.normals.append(normals)
        self.uvs.append(uvs)
        self.colors.append(colors)
        self.indices.append(indices + offset)

    def extend(self, other: "Geometry", transform: np.ndarray | None = None,
               color=None) -> None:
        if other.vertex_count == 0:
            return
        positions, normals, uvs, indices, colors = other.arrays(with_colors=True)
        if transform is not None:
            positions = transform_points(transform, positions)
            normals = transform_normals(transform, normals)
        if color is not None:
            colors = np.tile(np.asarray(color, dtype="float32").reshape(1, 4),
                             (len(positions), 1))
        self.add(positions, normals, uvs, indices, colors)

    # --------------------------------------------------------------- queries
    @property
    def vertex_count(self) -> int:
        return sum(len(chunk) for chunk in self.positions)

    @property
    def triangle_count(self) -> int:
        return sum(len(chunk) for chunk in self.indices) // 3

    def weld(self, tolerance: float = 1e-4) -> "Geometry":
        """Merge vertices identical in position, normal, UV and colour.

        Primitives are authored quad-by-quad for clarity, which duplicates every
        shared corner. Welding typically removes three quarters of the terrain
        vertices at no visual cost, since only exactly-matching attributes merge.
        """
        positions, normals, uvs, indices, colors = self.arrays(with_colors=True)
        if len(positions) == 0:
            return self
        quantum = 1.0 / max(tolerance, 1e-9)
        key = np.concatenate([
            np.rint(positions * quantum).astype("int64"),
            np.rint(normals * 10000.0).astype("int64"),
            np.rint(uvs * 10000.0).astype("int64"),
            np.rint(colors * 10000.0).astype("int64")], axis=1)
        _, first, inverse = np.unique(key, axis=0, return_index=True, return_inverse=True)
        order = np.argsort(first)
        remap = np.empty(len(first), dtype="int64")
        remap[order] = np.arange(len(first))
        welded = Geometry()
        welded.add(positions[first[order]], normals[first[order]], uvs[first[order]],
                   remap[inverse][indices].astype("uint32"), colors[first[order]])
        return welded

    @property
    def has_colors(self) -> bool:
        return any(not np.allclose(chunk, 1.0) for chunk in self.colors)

    def arrays(self, with_colors: bool = False):
        if not self.positions:
            empty = np.zeros((0, 3), dtype="float32")
            blank = (empty, empty, np.zeros((0, 2), dtype="float32"),
                     np.zeros(0, dtype="uint32"))
            return blank + (np.zeros((0, 4), dtype="float32"),) if with_colors else blank
        result = (np.concatenate(self.positions), np.concatenate(self.normals),
                  np.concatenate(self.uvs), np.concatenate(self.indices))
        if with_colors:
            result = result + (np.concatenate(self.colors),)
        return result


def transform_points(matrix: np.ndarray, points: np.ndarray) -> np.ndarray:
    points = np.asarray(points, dtype="float64").reshape(-1, 3)
    homogeneous = np.concatenate([points, np.ones((len(points), 1))], axis=1)
    return (homogeneous @ matrix.T)[:, :3].astype("float32")


def transform_normals(matrix: np.ndarray, normals: np.ndarray) -> np.ndarray:
    normal_matrix = np.linalg.inv(matrix[:3, :3]).T
    result = np.asarray(normals, dtype="float64").reshape(-1, 3) @ normal_matrix.T
    lengths = np.linalg.norm(result, axis=1, keepdims=True)
    lengths[lengths == 0.0] = 1.0
    return (result / lengths).astype("float32")


def compose(translation=(0.0, 0.0, 0.0), rotation_y: float = 0.0,
            scale=(1.0, 1.0, 1.0), rotation_x: float = 0.0,
            rotation_z: float = 0.0) -> np.ndarray:
    """Build a TRS matrix. Rotations are applied Z, X then Y (yaw last)."""
    sx, sy, sz = (scale, scale, scale) if isinstance(scale, (int, float)) else scale
    matrix = np.diag([float(sx), float(sy), float(sz), 1.0])
    for angle, axis in ((rotation_z, "z"), (rotation_x, "x"), (rotation_y, "y")):
        if angle:
            matrix = _rotation(axis, angle) @ matrix
    matrix[:3, 3] = translation
    return matrix


def _rotation(axis: str, angle: float) -> np.ndarray:
    c, s = math.cos(angle), math.sin(angle)
    matrix = np.eye(4)
    if axis == "x":
        matrix[1, 1], matrix[1, 2], matrix[2, 1], matrix[2, 2] = c, -s, s, c
    elif axis == "y":
        matrix[0, 0], matrix[0, 2], matrix[2, 0], matrix[2, 2] = c, s, -s, c
    else:
        matrix[0, 0], matrix[0, 1], matrix[1, 0], matrix[1, 1] = c, -s, s, c
    return matrix


def compute_tangents(positions: np.ndarray, normals: np.ndarray, uvs: np.ndarray,
                     indices: np.ndarray) -> np.ndarray:
    """Per-vertex glTF VEC4 tangents (xyz + handedness) accumulated per triangle."""
    tangent = np.zeros((len(positions), 3), dtype="float64")
    bitangent = np.zeros((len(positions), 3), dtype="float64")
    tri = indices.reshape(-1, 3).astype("int64")
    p0, p1, p2 = (positions[tri[:, i]].astype("float64") for i in range(3))
    w0, w1, w2 = (uvs[tri[:, i]].astype("float64") for i in range(3))
    edge1, edge2 = p1 - p0, p2 - p0
    delta1, delta2 = w1 - w0, w2 - w0
    determinant = delta1[:, 0] * delta2[:, 1] - delta2[:, 0] * delta1[:, 1]
    safe = np.abs(determinant) > 1e-12
    scale = np.zeros_like(determinant)
    scale[safe] = 1.0 / determinant[safe]
    face_t = (edge1 * delta2[:, 1, None] - edge2 * delta1[:, 1, None]) * scale[:, None]
    face_b = (edge2 * delta1[:, 0, None] - edge1 * delta2[:, 0, None]) * scale[:, None]
    for corner in range(3):
        np.add.at(tangent, tri[:, corner], face_t)
        np.add.at(bitangent, tri[:, corner], face_b)
    normals = normals.astype("float64")
    # Gram-Schmidt against the vertex normal.
    projected = tangent - normals * np.einsum("ij,ij->i", normals, tangent)[:, None]
    lengths = np.linalg.norm(projected, axis=1)
    degenerate = lengths < 1e-9
    if degenerate.any():
        # Any stable perpendicular will do where UVs gave no usable direction.
        fallback = np.cross(normals[degenerate], np.array([0.0, 0.0, 1.0]))
        short = np.linalg.norm(fallback, axis=1) < 1e-6
        if short.any():
            fallback[short] = np.cross(normals[degenerate][short], np.array([0.0, 1.0, 0.0]))
        projected[degenerate] = fallback
        lengths = np.linalg.norm(projected, axis=1)
    lengths[lengths == 0.0] = 1.0
    projected /= lengths[:, None]
    handedness = np.where(
        np.einsum("ij,ij->i", np.cross(normals, projected), bitangent) < 0.0, -1.0, 1.0)
    return np.concatenate([projected, handedness[:, None]], axis=1).astype("float32")


class GLBWriter:
    def __init__(self, generator: str) -> None:
        self.binary = bytearray()
        self.doc: dict = {
            "asset": {"version": "2.0", "generator": generator},
            "scene": 0,
            "scenes": [{"name": "Scene", "nodes": []}],
            "nodes": [], "meshes": [], "materials": [], "accessors": [],
            "bufferViews": [], "buffers": [{"byteLength": 0}],
        }
        self._image_cache: dict[bytes, int] = {}
        self._sampler = None

    # --------------------------------------------------------------- buffers
    def _view(self, raw: bytes, *, target: int | None = None, alignment: int = 4) -> int:
        while len(self.binary) % alignment:
            self.binary.append(0)
        offset = len(self.binary)
        self.binary.extend(raw)
        view = {"buffer": 0, "byteOffset": offset, "byteLength": len(raw)}
        if target is not None:
            view["target"] = target
        self.doc["bufferViews"].append(view)
        return len(self.doc["bufferViews"]) - 1

    def accessor(self, values: np.ndarray, gltf_type: str, *, target: int | None = None,
                 bounds: bool = False, normalized: bool = False) -> int:
        values = np.ascontiguousarray(values)
        component = COMPONENT_TYPES[values.dtype]
        # glTF requires accessor offsets aligned to the component size.
        view = self._view(values.tobytes(), target=target,
                          alignment=max(4, values.dtype.itemsize))
        spec = {"bufferView": view, "componentType": component,
                "count": int(values.shape[0]), "type": gltf_type}
        if normalized:
            spec["normalized"] = True
        if bounds:
            matrix = values.reshape(len(values), -1)
            spec["min"] = [float(v) for v in matrix.min(axis=0)]
            spec["max"] = [float(v) for v in matrix.max(axis=0)]
        self.doc["accessors"].append(spec)
        return len(self.doc["accessors"]) - 1

    # -------------------------------------------------------------- textures
    def _sampler_index(self) -> int:
        if self._sampler is None:
            self.doc.setdefault("samplers", []).append(
                {"magFilter": 9729, "minFilter": 9987, "wrapS": 10497, "wrapT": 10497})
            self._sampler = len(self.doc["samplers"]) - 1
        return self._sampler

    def texture(self, png: bytes, name: str) -> int:
        cached = self._image_cache.get(png)
        if cached is not None:
            return cached
        view = self._view(png)
        self.doc.setdefault("images", []).append(
            {"name": name, "bufferView": view, "mimeType": "image/png"})
        self.doc.setdefault("textures", []).append(
            {"source": len(self.doc["images"]) - 1, "sampler": self._sampler_index()})
        index = len(self.doc["textures"]) - 1
        self._image_cache[png] = index
        return index

    def material(self, name: str, *, base_color=(1.0, 1.0, 1.0, 1.0),
                 metallic: float = 0.0, roughness: float = 0.85,
                 base_color_texture: int | None = None,
                 normal_texture: int | None = None, normal_scale: float = 1.0,
                 orm_texture: int | None = None, emissive=None,
                 double_sided: bool = False, alpha_mode: str | None = None,
                 alpha_cutoff: float | None = None) -> int:
        pbr = {"baseColorFactor": [float(v) for v in base_color],
               "metallicFactor": float(metallic), "roughnessFactor": float(roughness)}
        if base_color_texture is not None:
            pbr["baseColorTexture"] = {"index": base_color_texture}
        if orm_texture is not None:
            # ORM packs occlusion in R and metallic-roughness in G/B, so the same
            # texture serves both slots exactly as the glTF spec intends.
            pbr["metallicRoughnessTexture"] = {"index": orm_texture}
        material: dict = {"name": name, "pbrMetallicRoughness": pbr,
                          "doubleSided": bool(double_sided)}
        if normal_texture is not None:
            material["normalTexture"] = {"index": normal_texture, "scale": float(normal_scale)}
        if orm_texture is not None:
            material["occlusionTexture"] = {"index": orm_texture}
        if emissive is not None:
            material["emissiveFactor"] = [float(v) for v in emissive]
        if alpha_mode is not None:
            material["alphaMode"] = alpha_mode
            if alpha_mode == "MASK":
                material["alphaCutoff"] = 0.5 if alpha_cutoff is None else float(alpha_cutoff)
        self.doc["materials"].append(material)
        return len(self.doc["materials"]) - 1

    # ----------------------------------------------------------------- mesh
    def mesh(self, name: str, parts: list[tuple[Geometry, int]], *,
             tangents: bool | None = None) -> int | None:
        """Create a mesh from (geometry, material) pairs. Returns a mesh index.

        By default tangents are emitted exactly for the primitives whose
        material carries a normal map, and omitted everywhere else. Emitting
        them everywhere wastes roughly a fifth of the package on data no
        renderer reads; omitting them where a normal map exists makes the
        tangent frame renderer-dependent and the glTF validator warns about
        portability. Deciding per primitive satisfies both.
        """
        primitives = []
        for geometry, material in parts:
            if geometry.triangle_count == 0:
                continue
            positions, normals, uvs, indices, colors = geometry.arrays(with_colors=True)
            attributes = {
                "POSITION": self.accessor(positions, "VEC3", target=ARRAY_BUFFER, bounds=True),
                "NORMAL": self.accessor(normals, "VEC3", target=ARRAY_BUFFER),
                "TEXCOORD_0": self.accessor(uvs, "VEC2", target=ARRAY_BUFFER),
            }
            needs_tangents = (tangents if tangents is not None
                              else "normalTexture" in self.doc["materials"][material])
            if needs_tangents:
                attributes["TANGENT"] = self.accessor(
                    compute_tangents(positions, normals, uvs, indices), "VEC4",
                    target=ARRAY_BUFFER)
            if geometry.has_colors:
                # A normalized byte a channel, not a float. The ground's
                # coverage only has to resolve an alpha test, 1/255 is finer
                # than the cut can see, and floats cost twelve more bytes on
                # every terrain vertex in the map.
                packed = np.rint(np.clip(colors, 0.0, 1.0) * 255.0).astype("uint8")
                attributes["COLOR_0"] = self.accessor(
                    packed, "VEC4", target=ARRAY_BUFFER, normalized=True)
            index_values = (indices.astype("uint16") if len(positions) <= 65535
                            else indices.astype("uint32"))
            primitives.append({
                "attributes": attributes,
                "indices": self.accessor(index_values, "SCALAR", target=ELEMENT_ARRAY_BUFFER),
                "material": material, "mode": 4})
        if not primitives:
            return None
        self.doc["meshes"].append({"name": name, "primitives": primitives})
        return len(self.doc["meshes"]) - 1

    # ----------------------------------------------------------------- nodes
    def node(self, name: str, *, mesh: int | None = None, matrix: np.ndarray | None = None,
             parent: int | None = None, children: list[int] | None = None,
             translation=None, skin: int | None = None,
             in_scene: bool = True) -> int:
        spec: dict = {"name": name}
        if mesh is not None:
            spec["mesh"] = mesh
        if skin is not None:
            spec["skin"] = skin
        if translation is not None:
            spec["translation"] = [float(v) for v in translation]
        if matrix is not None:
            identity = np.allclose(matrix, np.eye(4))
            if not identity:
                # glTF matrices are column-major.
                spec["matrix"] = [float(v) for v in np.asarray(matrix).T.reshape(-1)]
        if children:
            spec["children"] = list(children)
        self.doc["nodes"].append(spec)
        index = len(self.doc["nodes"]) - 1
        if parent is not None:
            self.doc["nodes"][parent].setdefault("children", []).append(index)
        elif in_scene:
            self.doc["scenes"][0]["nodes"].append(index)
        return index

    # ------------------------------------------------------------- skinning
    def skinned_mesh(self, name: str, parts: list[tuple[int, Geometry, int]],
                     joint_count: int) -> int | None:
        """Build one rigidly-skinned mesh from (joint index, geometry, material).

        Each authored part belongs wholly to one joint, which is how the
        existing Eloria creature assets are rigged, so a single-influence
        JOINTS_0/WEIGHTS_0 pair is exact rather than an approximation.
        """
        by_material: dict[int, list[tuple[int, Geometry]]] = {}
        for joint, geometry, material in parts:
            if geometry.triangle_count:
                by_material.setdefault(material, []).append((joint, geometry))
        primitives = []
        for material, grouped in sorted(by_material.items()):
            positions, normals, uvs, indices, joints, weights = [], [], [], [], [], []
            offset = 0
            for joint, geometry in grouped:
                part_positions, part_normals, part_uvs, part_indices = geometry.arrays()
                positions.append(part_positions)
                normals.append(part_normals)
                uvs.append(part_uvs)
                indices.append(part_indices + offset)
                count = len(part_positions)
                joint_row = np.zeros((count, 4), dtype="uint16")
                joint_row[:, 0] = joint
                joints.append(joint_row)
                weight_row = np.zeros((count, 4), dtype="float32")
                weight_row[:, 0] = 1.0
                weights.append(weight_row)
                offset += count
            positions = np.concatenate(positions)
            indices = np.concatenate(indices)
            attributes = {
                "POSITION": self.accessor(positions, "VEC3", target=ARRAY_BUFFER,
                                          bounds=True),
                "NORMAL": self.accessor(np.concatenate(normals), "VEC3",
                                        target=ARRAY_BUFFER),
                "TEXCOORD_0": self.accessor(np.concatenate(uvs), "VEC2",
                                            target=ARRAY_BUFFER),
                "JOINTS_0": self.accessor(np.concatenate(joints), "VEC4",
                                          target=ARRAY_BUFFER),
                "WEIGHTS_0": self.accessor(np.concatenate(weights), "VEC4",
                                           target=ARRAY_BUFFER),
            }
            index_values = (indices.astype("uint16") if len(positions) <= 65535
                            else indices.astype("uint32"))
            primitives.append({
                "attributes": attributes,
                "indices": self.accessor(index_values, "SCALAR",
                                         target=ELEMENT_ARRAY_BUFFER),
                "material": material, "mode": 4})
        if not primitives:
            return None
        self.doc["meshes"].append({"name": name, "primitives": primitives})
        return len(self.doc["meshes"]) - 1

    def skin(self, name: str, joint_nodes: list[int],
             global_positions: list) -> int:
        """Create a skin whose inverse bind matrices undo each joint's rest pose."""
        matrices = []
        for position in global_positions:
            matrix = np.eye(4, dtype="float32")
            matrix[:3, 3] = -np.asarray(position, dtype="float32")
            matrices.append(matrix.T.reshape(-1))
        accessor = self.accessor(np.asarray(matrices, dtype="float32"), "MAT4")
        self.doc.setdefault("skins", []).append({
            "name": name, "joints": list(joint_nodes), "skeleton": joint_nodes[0],
            "inverseBindMatrices": accessor})
        return len(self.doc["skins"]) - 1

    def animation(self, name: str, channels: dict) -> int:
        """Add an animation. `channels` maps node index -> (path, times, values)."""
        animation = {"name": name, "samplers": [], "channels": []}
        for node, (path, times, values) in channels.items():
            sampler_input = self.accessor(np.asarray(times, dtype="float32"),
                                          "SCALAR", bounds=True)
            width = "VEC4" if path == "rotation" else "VEC3"
            sampler_output = self.accessor(np.asarray(values, dtype="float32"), width)
            animation["samplers"].append({"input": sampler_input,
                                          "output": sampler_output,
                                          "interpolation": "LINEAR"})
            animation["channels"].append({"sampler": len(animation["samplers"]) - 1,
                                          "target": {"node": node, "path": path}})
        self.doc.setdefault("animations", []).append(animation)
        return len(self.doc["animations"]) - 1

    # ----------------------------------------------------------------- write
    def statistics(self) -> dict:
        triangles = 0
        for mesh in self.doc["meshes"]:
            for primitive in mesh["primitives"]:
                triangles += self.doc["accessors"][primitive["indices"]]["count"] // 3
        return {"nodes": len(self.doc["nodes"]), "meshes": len(self.doc["meshes"]),
                "materials": len(self.doc["materials"]),
                "textures": len(self.doc.get("textures", [])),
                "accessors": len(self.doc["accessors"]),
                "uniqueMeshTriangles": triangles}

    def write(self, path: Path) -> int:
        self.doc["buffers"][0]["byteLength"] = len(self.binary)
        encoded = json.dumps(self.doc, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
        encoded += b" " * (_align(len(encoded)) - len(encoded))
        binary = bytes(self.binary) + b"\x00" * (_align(len(self.binary)) - len(self.binary))
        total = 12 + 8 + len(encoded) + 8 + len(binary)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b"glTF" + struct.pack("<II", 2, total)
                         + struct.pack("<II", len(encoded), 0x4E4F534A) + encoded
                         + struct.pack("<II", len(binary), 0x004E4942) + binary)
        return total
