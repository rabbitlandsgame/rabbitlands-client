"""Minimal, spec-correct glTF 2.0 / GLB writer.

Everything is embedded in the single binary chunk: vertex data, index data and
PNG images. The output has no external dependencies and no glTF extensions, so
it loads through Godot's GLTFDocument and through any conformant viewer.
"""
from __future__ import annotations

import json
import struct
from dataclasses import dataclass, field

import numpy as np

COMPONENT_FLOAT = 5126
COMPONENT_UBYTE = 5121
COMPONENT_USHORT = 5123
COMPONENT_UINT = 5125
TARGET_ARRAY_BUFFER = 34962
TARGET_ELEMENT_ARRAY_BUFFER = 34963

ALPHA_OPAQUE = "OPAQUE"
ALPHA_MASK = "MASK"
ALPHA_BLEND = "BLEND"


@dataclass
class Material:
    name: str
    base_color: tuple[float, float, float, float] = (1.0, 1.0, 1.0, 1.0)
    metallic: float = 0.0
    roughness: float = 0.85
    base_color_texture: str | None = None
    orm_texture: str | None = None
    normal_texture: str | None = None
    normal_scale: float = 1.0
    emissive: tuple[float, float, float] = (0.0, 0.0, 0.0)
    emissive_texture: str | None = None
    alpha_mode: str = ALPHA_OPAQUE
    alpha_cutoff: float = 0.5
    double_sided: bool = False
    uv_scale: float = 1.0


@dataclass
class Node:
    name: str
    mesh: str | None = None
    translation: tuple[float, float, float] | None = None
    rotation_y: float | None = None
    scale: tuple[float, float, float] | None = None
    children: list["Node"] = field(default_factory=list)
    extras: dict | None = None

    def add(self, node: "Node") -> "Node":
        self.children.append(node)
        return node


class GltfBuilder:
    """Accumulates meshes, materials, images and a node tree, then writes a GLB."""

    def __init__(self, generator: str = "Eloria Amberwood builder") -> None:
        self.generator = generator
        self._buffer = bytearray()
        self._buffer_views: list[dict] = []
        self._accessors: list[dict] = []
        self._meshes: list[dict] = []
        self._mesh_index: dict[str, int] = {}
        self._materials: list[dict] = []
        self._material_index: dict[str, int] = {}
        self._images: list[dict] = []
        self._image_index: dict[str, int] = {}
        self._textures: list[dict] = []
        self._texture_index: dict[tuple[int, int], int] = {}
        self._samplers: list[dict] = [{
            "magFilter": 9729, "minFilter": 9987, "wrapS": 10497, "wrapT": 10497}]
        self._nodes: list[dict] = []
        self._roots: list[int] = []
        self.mesh_triangles: dict[str, int] = {}
        self.mesh_vertices: dict[str, int] = {}

    # -- buffer plumbing --------------------------------------------------
    def _align(self, alignment: int = 4) -> None:
        while len(self._buffer) % alignment:
            self._buffer.append(0)

    def _add_view(self, data: bytes, target: int | None = None,
                  byte_stride: int | None = None) -> int:
        self._align(4)
        offset = len(self._buffer)
        self._buffer.extend(data)
        view = {"buffer": 0, "byteOffset": offset, "byteLength": len(data)}
        if target is not None:
            view["target"] = target
        if byte_stride is not None:
            view["byteStride"] = byte_stride
        self._buffer_views.append(view)
        return len(self._buffer_views) - 1

    def _add_accessor(self, array: np.ndarray, kind: str, component: int,
                      target: int, normalized: bool = False) -> int:
        dtype = {COMPONENT_FLOAT: np.float32, COMPONENT_UBYTE: np.uint8,
                 COMPONENT_USHORT: np.uint16, COMPONENT_UINT: np.uint32}[component]
        if normalized and dtype is not np.float32:
            # glTF reads a normalized integer back as value / max, so the
            # rounding has to happen here rather than in the caller.
            scale = float(np.iinfo(dtype).max)
            array = np.rint(np.clip(np.asarray(array, dtype=np.float64),
                                    0.0, 1.0) * scale)
        data = np.ascontiguousarray(array, dtype=dtype)
        view = self._add_view(data.tobytes(), target)
        accessor = {
            "bufferView": view,
            "componentType": component,
            "count": int(data.shape[0]),
            "type": kind,
        }
        if normalized:
            accessor["normalized"] = True
        if kind != "SCALAR":
            accessor["min"] = [float(v) for v in data.min(axis=0)]
            accessor["max"] = [float(v) for v in data.max(axis=0)]
        else:
            accessor["min"] = [int(np.asarray(array).min())]
            accessor["max"] = [int(np.asarray(array).max())]
        self._accessors.append(accessor)
        return len(self._accessors) - 1

    # -- images / textures / materials -------------------------------------
    def add_image(self, name: str, png_bytes: bytes) -> int:
        if name in self._image_index:
            return self._image_index[name]
        view = self._add_view(png_bytes)
        self._images.append({"name": name, "mimeType": "image/png", "bufferView": view})
        index = len(self._images) - 1
        self._image_index[name] = index
        return index

    def _texture(self, image_name: str) -> int:
        image = self._image_index[image_name]
        key = (image, 0)
        if key in self._texture_index:
            return self._texture_index[key]
        self._textures.append({"sampler": 0, "source": image})
        index = len(self._textures) - 1
        self._texture_index[key] = index
        return index

    def add_material(self, material: Material) -> int:
        if material.name in self._material_index:
            return self._material_index[material.name]
        pbr: dict = {
            "baseColorFactor": list(material.base_color),
            "metallicFactor": float(material.metallic),
            "roughnessFactor": float(material.roughness),
        }
        if material.base_color_texture:
            pbr["baseColorTexture"] = {"index": self._texture(material.base_color_texture)}
        if material.orm_texture:
            pbr["metallicRoughnessTexture"] = {"index": self._texture(material.orm_texture)}
        entry: dict = {"name": material.name, "pbrMetallicRoughness": pbr}
        if material.orm_texture:
            entry["occlusionTexture"] = {"index": self._texture(material.orm_texture)}
        if material.normal_texture:
            entry["normalTexture"] = {"index": self._texture(material.normal_texture)}
            if abs(material.normal_scale - 1.0) > 1e-6:
                entry["normalTexture"]["scale"] = float(material.normal_scale)
        if any(c > 0.0 for c in material.emissive):
            entry["emissiveFactor"] = list(material.emissive)
        if material.emissive_texture:
            entry["emissiveTexture"] = {"index": self._texture(material.emissive_texture)}
        if material.alpha_mode != ALPHA_OPAQUE:
            entry["alphaMode"] = material.alpha_mode
            if material.alpha_mode == ALPHA_MASK:
                entry["alphaCutoff"] = float(material.alpha_cutoff)
        if material.double_sided:
            entry["doubleSided"] = True
        self._materials.append(entry)
        index = len(self._materials) - 1
        self._material_index[material.name] = index
        return index

    # -- meshes -----------------------------------------------------------
    def add_mesh(self, name: str, mesh, with_tangents: bool = False) -> int:
        """Register a reusable mesh. Multiple nodes may instance it."""
        if name in self._mesh_index:
            return self._mesh_index[name]
        if mesh.triangle_count == 0:
            raise ValueError(f"mesh '{name}' has no triangles")
        if mesh.material not in self._material_index:
            raise KeyError(f"mesh '{name}' uses unregistered material '{mesh.material}'")
        attributes = {
            "POSITION": self._add_accessor(mesh.positions, "VEC3", COMPONENT_FLOAT,
                                           TARGET_ARRAY_BUFFER),
            "NORMAL": self._add_accessor(mesh.normals, "VEC3", COMPONENT_FLOAT,
                                         TARGET_ARRAY_BUFFER),
            "TEXCOORD_0": self._add_accessor(mesh.uvs, "VEC2", COMPONENT_FLOAT,
                                             TARGET_ARRAY_BUFFER),
        }
        if with_tangents:
            attributes["TANGENT"] = self._add_accessor(mesh.tangents(), "VEC4",
                                                       COMPONENT_FLOAT, TARGET_ARRAY_BUFFER)
        if mesh.colors is not None:
            # A normalized byte a channel, not a float: the ground's coverage
            # only has to resolve an alpha test, 1/255 is finer than the cut
            # can see, and floats cost twelve more bytes on every terrain
            # vertex in the map.
            attributes["COLOR_0"] = self._add_accessor(
                np.clip(mesh.colors, 0.0, 1.0), "VEC4", COMPONENT_UBYTE,
                TARGET_ARRAY_BUFFER, normalized=True)
        component = COMPONENT_USHORT if mesh.vertex_count <= 65535 else COMPONENT_UINT
        indices = self._add_accessor(mesh.indices, "SCALAR", component,
                                     TARGET_ELEMENT_ARRAY_BUFFER)
        self._meshes.append({
            "name": name,
            "primitives": [{
                "attributes": attributes,
                "indices": indices,
                "mode": 4,
                "material": self._material_index[mesh.material],
            }],
        })
        index = len(self._meshes) - 1
        self._mesh_index[name] = index
        self.mesh_triangles[name] = mesh.triangle_count
        self.mesh_vertices[name] = mesh.vertex_count
        return index

    def has_mesh(self, name: str) -> bool:
        return name in self._mesh_index

    # -- nodes ------------------------------------------------------------
    def add_node(self, node: Node, parent: int | None = None) -> int:
        entry: dict = {"name": node.name}
        if node.mesh is not None:
            entry["mesh"] = self._mesh_index[node.mesh]
        if node.translation is not None:
            entry["translation"] = [float(v) for v in node.translation]
        if node.rotation_y is not None:
            half = float(node.rotation_y) * 0.5
            entry["rotation"] = [0.0, float(np.sin(half)), 0.0, float(np.cos(half))]
        if node.scale is not None:
            entry["scale"] = [float(v) for v in node.scale]
        if node.extras:
            entry["extras"] = node.extras
        self._nodes.append(entry)
        index = len(self._nodes) - 1
        if parent is None:
            self._roots.append(index)
        else:
            self._nodes[parent].setdefault("children", []).append(index)
        for child in node.children:
            self.add_node(child, index)
        return index

    # -- output -----------------------------------------------------------
    def statistics(self) -> dict:
        return {
            "nodes": len(self._nodes),
            "meshes": len(self._meshes),
            "materials": len(self._materials),
            "images": len(self._images),
            "textures": len(self._textures),
            "accessors": len(self._accessors),
            "bufferViews": len(self._buffer_views),
            "uniqueTriangles": int(sum(self.mesh_triangles.values())),
            "uniqueVertices": int(sum(self.mesh_vertices.values())),
        }

    def instanced_triangles(self) -> int:
        total = 0
        for node in self._nodes:
            if "mesh" in node:
                name = self._meshes[node["mesh"]]["name"]
                total += self.mesh_triangles.get(name, 0)
        return total

    def to_json(self) -> dict:
        document: dict = {
            "asset": {"version": "2.0", "generator": self.generator},
            "scene": 0,
            "scenes": [{"nodes": self._roots}],
            "nodes": self._nodes,
            "meshes": self._meshes,
            "materials": self._materials,
            "accessors": self._accessors,
            "bufferViews": self._buffer_views,
            "buffers": [{"byteLength": len(self._buffer)}],
        }
        if self._images:
            document["images"] = self._images
            document["textures"] = self._textures
            document["samplers"] = self._samplers
        return document

    def write_glb(self, path: str) -> int:
        self._align(4)
        document = self.to_json()
        json_bytes = json.dumps(document, separators=(",", ":")).encode("utf-8")
        while len(json_bytes) % 4:
            json_bytes += b" "
        binary = bytes(self._buffer)
        while len(binary) % 4:
            binary += b"\x00"
        total = 12 + 8 + len(json_bytes) + 8 + len(binary)
        with open(path, "wb") as handle:
            handle.write(struct.pack("<III", 0x46546C67, 2, total))
            handle.write(struct.pack("<II", len(json_bytes), 0x4E4F534A))
            handle.write(json_bytes)
            handle.write(struct.pack("<II", len(binary), 0x004E4942))
            handle.write(binary)
        return total
