"""Minimal, spec-conformant glTF 2.0 / GLB writer for the Eloria Four Gates map.

Written for this project because no third-party glTF library is available in the
build environment.  Emits only core glTF 2.0 features -- no extensions -- so the
result loads in Godot's GLTFDocument, the Khronos validator and three.js without
any optional-extension support.

Conventions:
  * metres, right handed, +Y up, -Z north
  * non-interleaved vertex attributes, one bufferView per accessor
  * textures embedded as PNG bufferViews (self-contained GLB)
"""

from __future__ import annotations

import io
import json
import struct
from typing import Dict, Iterable, List, Optional, Sequence, Tuple

import numpy as np

FLOAT = 5126
UNSIGNED_INT = 5125
UNSIGNED_SHORT = 5123
ARRAY_BUFFER = 34962
ELEMENT_ARRAY_BUFFER = 34963

NEAREST = 9728
LINEAR = 9729
LINEAR_MIPMAP_LINEAR = 9987
REPEAT = 10497
CLAMP_TO_EDGE = 33071


def _pad4(n: int) -> int:
    return (4 - (n % 4)) % 4


class GLB:
    def __init__(self, generator: str = "Eloria Four Gates map builder"):
        self.generator = generator
        self._buffer = bytearray()
        self.buffer_views: List[dict] = []
        self.accessors: List[dict] = []
        self.meshes: List[dict] = []
        self.materials: List[dict] = []
        self.textures: List[dict] = []
        self.images: List[dict] = []
        self.samplers: List[dict] = []
        self.nodes: List[dict] = []
        self.animations: List[dict] = []
        self.scene_roots: List[int] = []
        self._material_index: Dict[str, int] = {}
        self._texture_index: Dict[Tuple[int, int], int] = {}
        self._node_names: Dict[str, int] = {}

    # ------------------------------------------------------------------ buffer
    def _write(self, data: bytes, alignment: int = 4) -> int:
        pad = (alignment - (len(self._buffer) % alignment)) % alignment
        self._buffer.extend(b"\x00" * pad)
        offset = len(self._buffer)
        self._buffer.extend(data)
        return offset

    def _buffer_view(self, data: bytes, target: Optional[int] = None,
                     byte_stride: Optional[int] = None) -> int:
        offset = self._write(data)
        view = {"buffer": 0, "byteOffset": offset, "byteLength": len(data)}
        if target is not None:
            view["target"] = target
        if byte_stride is not None:
            view["byteStride"] = byte_stride
        self.buffer_views.append(view)
        return len(self.buffer_views) - 1

    # --------------------------------------------------------------- accessors
    def _accessor(self, array: np.ndarray, kind: str, component: int,
                  target: Optional[int], normalized: bool = False,
                  with_bounds: bool = False) -> int:
        array = np.ascontiguousarray(array)
        components = {"SCALAR": 1, "VEC2": 2, "VEC3": 3, "VEC4": 4}[kind]
        comp_size = {FLOAT: 4, UNSIGNED_INT: 4, UNSIGNED_SHORT: 2}[component]
        stride = components * comp_size
        view = self._buffer_view(array.tobytes(), target,
                                 stride if target == ARRAY_BUFFER else None)
        accessor = {
            "bufferView": view,
            "componentType": component,
            "count": int(array.size // components),
            "type": kind,
        }
        if normalized:
            accessor["normalized"] = True
        if with_bounds:
            flat = array.reshape(-1, components).astype(np.float64)
            accessor["min"] = [float(v) for v in flat.min(axis=0)]
            accessor["max"] = [float(v) for v in flat.max(axis=0)]
        self.accessors.append(accessor)
        return len(self.accessors) - 1

    # ---------------------------------------------------------------- textures
    def add_sampler(self, wrap: int = REPEAT) -> int:
        sampler = {"magFilter": LINEAR, "minFilter": LINEAR_MIPMAP_LINEAR,
                   "wrapS": wrap, "wrapT": wrap}
        for i, existing in enumerate(self.samplers):
            if existing == sampler:
                return i
        self.samplers.append(sampler)
        return len(self.samplers) - 1

    @staticmethod
    def encode_png(pil_image, optimise: bool = True) -> bytes:
        stream = io.BytesIO()
        image = pil_image
        if optimise and image.mode == "RGBA":
            alpha = image.getchannel("A")
            if alpha.getextrema() == (255, 255):
                image = image.convert("RGB")
        image.save(stream, format="PNG", optimize=True, compress_level=9)
        return stream.getvalue()

    def add_image_bytes(self, png_bytes: bytes, name: str) -> int:
        view = self._buffer_view(png_bytes)
        self.images.append({"bufferView": view, "mimeType": "image/png", "name": name})
        return len(self.images) - 1

    def add_image(self, pil_image, name: str, optimise: bool = True) -> int:
        return self.add_image_bytes(self.encode_png(pil_image, optimise), name)

    def add_texture_bytes(self, png_bytes: bytes, name: str, wrap: int = REPEAT) -> int:
        image = self.add_image_bytes(png_bytes, name)
        sampler = self.add_sampler(wrap)
        key = (image, sampler)
        self.textures.append({"sampler": sampler, "source": image, "name": name})
        index = len(self.textures) - 1
        self._texture_index[key] = index
        return index

    def add_texture(self, pil_image, name: str, wrap: int = REPEAT) -> int:
        image = self.add_image(pil_image, name)
        sampler = self.add_sampler(wrap)
        key = (image, sampler)
        if key in self._texture_index:
            return self._texture_index[key]
        self.textures.append({"sampler": sampler, "source": image, "name": name})
        index = len(self.textures) - 1
        self._texture_index[key] = index
        return index

    # --------------------------------------------------------------- materials
    def add_material(self, name: str, base_color=(1, 1, 1, 1),
                     base_color_texture: Optional[int] = None,
                     metallic: float = 0.0, roughness: float = 0.85,
                     metallic_roughness_texture: Optional[int] = None,
                     normal_texture: Optional[int] = None,
                     normal_scale: float = 1.0,
                     occlusion_texture: Optional[int] = None,
                     emissive=(0.0, 0.0, 0.0),
                     emissive_texture: Optional[int] = None,
                     alpha_mode: str = "OPAQUE", alpha_cutoff: float = 0.5,
                     double_sided: bool = False) -> int:
        if name in self._material_index:
            return self._material_index[name]
        pbr: dict = {
            "baseColorFactor": [float(c) for c in base_color],
            "metallicFactor": float(metallic),
            "roughnessFactor": float(roughness),
        }
        if base_color_texture is not None:
            pbr["baseColorTexture"] = {"index": base_color_texture}
        if metallic_roughness_texture is not None:
            pbr["metallicRoughnessTexture"] = {"index": metallic_roughness_texture}
        material: dict = {"name": name, "pbrMetallicRoughness": pbr}
        if normal_texture is not None:
            material["normalTexture"] = {"index": normal_texture, "scale": float(normal_scale)}
        if occlusion_texture is not None:
            material["occlusionTexture"] = {"index": occlusion_texture}
        if any(emissive):
            material["emissiveFactor"] = [float(c) for c in emissive]
        if emissive_texture is not None:
            material["emissiveTexture"] = {"index": emissive_texture}
        if alpha_mode != "OPAQUE":
            material["alphaMode"] = alpha_mode
            if alpha_mode == "MASK":
                material["alphaCutoff"] = float(alpha_cutoff)
        if double_sided:
            material["doubleSided"] = True
        self.materials.append(material)
        index = len(self.materials) - 1
        self._material_index[name] = index
        return index

    def material_id(self, name: str) -> int:
        return self._material_index[name]

    # ------------------------------------------------------------------ meshes
    def add_mesh(self, name: str, primitives: Sequence[dict]) -> int:
        """primitives: list of dicts with keys positions, normals, uvs, tangents,
        colors, indices, material."""
        gl_primitives = []
        for prim in primitives:
            positions = np.asarray(prim["positions"], dtype=np.float32)
            indices = np.asarray(prim["indices"], dtype=np.uint32)
            if positions.shape[0] == 0 or indices.size == 0:
                continue
            attributes = {
                "POSITION": self._accessor(positions, "VEC3", FLOAT, ARRAY_BUFFER,
                                           with_bounds=True)
            }
            if prim.get("normals") is not None:
                attributes["NORMAL"] = self._accessor(
                    np.asarray(prim["normals"], dtype=np.float32), "VEC3", FLOAT,
                    ARRAY_BUFFER)
            if prim.get("uvs") is not None:
                attributes["TEXCOORD_0"] = self._accessor(
                    np.asarray(prim["uvs"], dtype=np.float32), "VEC2", FLOAT,
                    ARRAY_BUFFER)
            if prim.get("tangents") is not None:
                attributes["TANGENT"] = self._accessor(
                    np.asarray(prim["tangents"], dtype=np.float32), "VEC4", FLOAT,
                    ARRAY_BUFFER)
            if prim.get("colors") is not None:
                attributes["COLOR_0"] = self._accessor(
                    np.asarray(prim["colors"], dtype=np.float32), "VEC4", FLOAT,
                    ARRAY_BUFFER)
            flat_indices = indices.reshape(-1)
            if positions.shape[0] <= 65535:
                index_accessor = self._accessor(
                    flat_indices.astype(np.uint16), "SCALAR", UNSIGNED_SHORT,
                    ELEMENT_ARRAY_BUFFER)
            else:
                index_accessor = self._accessor(
                    flat_indices, "SCALAR", UNSIGNED_INT, ELEMENT_ARRAY_BUFFER)
            gl_primitive = {"attributes": attributes, "indices": index_accessor,
                            "mode": 4}
            if prim.get("material") is not None:
                gl_primitive["material"] = prim["material"]
            gl_primitives.append(gl_primitive)
        if not gl_primitives:
            raise ValueError(f"mesh {name!r} has no primitives")
        self.meshes.append({"name": name, "primitives": gl_primitives})
        return len(self.meshes) - 1

    # ------------------------------------------------------------------- nodes
    def add_node(self, name: str, mesh: Optional[int] = None,
                 translation: Optional[Sequence[float]] = None,
                 rotation: Optional[Sequence[float]] = None,
                 scale: Optional[Sequence[float]] = None,
                 children: Optional[Iterable[int]] = None,
                 extras: Optional[dict] = None) -> int:
        if name in self._node_names:
            raise ValueError(f"duplicate node name {name!r}")
        node: dict = {"name": name}
        if mesh is not None:
            node["mesh"] = mesh
        if translation is not None and any(abs(float(v)) > 1e-9 for v in translation):
            node["translation"] = [float(v) for v in translation]
        if rotation is not None:
            node["rotation"] = [float(v) for v in rotation]
        if scale is not None and any(abs(float(v) - 1.0) > 1e-9 for v in scale):
            node["scale"] = [float(v) for v in scale]
        if children:
            node["children"] = [int(c) for c in children]
        if extras:
            node["extras"] = extras
        self.nodes.append(node)
        index = len(self.nodes) - 1
        self._node_names[name] = index
        return index

    def set_children(self, node: int, children: Iterable[int]) -> None:
        children = [int(c) for c in children]
        if children:
            self.nodes[node]["children"] = children

    def node_id(self, name: str) -> int:
        return self._node_names[name]

    def has_node(self, name: str) -> bool:
        return name in self._node_names

    # -------------------------------------------------------------- animations
    def add_animation(self, name: str, channels: Sequence[dict]) -> None:
        """channels: dicts with node, path, times (np float32), values (np float32)."""
        samplers = []
        gl_channels = []
        for channel in channels:
            times = np.asarray(channel["times"], dtype=np.float32)
            values = np.asarray(channel["values"], dtype=np.float32)
            time_accessor = self._accessor(times.reshape(-1, 1), "SCALAR", FLOAT, None,
                                           with_bounds=True)
            kind = {"translation": "VEC3", "scale": "VEC3", "rotation": "VEC4"}[channel["path"]]
            value_accessor = self._accessor(values, kind, FLOAT, None)
            samplers.append({"input": time_accessor, "output": value_accessor,
                             "interpolation": channel.get("interpolation", "LINEAR")})
            gl_channels.append({"sampler": len(samplers) - 1,
                                "target": {"node": channel["node"], "path": channel["path"]}})
        self.animations.append({"name": name, "samplers": samplers, "channels": gl_channels})

    # ------------------------------------------------------------------- write
    def save(self, path: str) -> dict:
        document = {
            "asset": {"version": "2.0", "generator": self.generator},
            "scene": 0,
            "scenes": [{"name": "FourGates", "nodes": self.scene_roots}],
            "nodes": self.nodes,
            "meshes": self.meshes,
            "materials": self.materials,
            "accessors": self.accessors,
            "bufferViews": self.buffer_views,
            "buffers": [{"byteLength": len(self._buffer)}],
        }
        if self.textures:
            document["textures"] = self.textures
            document["images"] = self.images
            document["samplers"] = self.samplers
        if self.animations:
            document["animations"] = self.animations

        json_bytes = json.dumps(document, separators=(",", ":")).encode("utf-8")
        json_bytes += b" " * _pad4(len(json_bytes))
        bin_bytes = bytes(self._buffer)
        bin_bytes += b"\x00" * _pad4(len(bin_bytes))
        document["buffers"][0]["byteLength"] = len(self._buffer)
        # re-serialise so the declared buffer length matches exactly
        json_bytes = json.dumps(document, separators=(",", ":")).encode("utf-8")
        json_bytes += b" " * _pad4(len(json_bytes))

        total = 12 + 8 + len(json_bytes) + 8 + len(bin_bytes)
        with open(path, "wb") as handle:
            handle.write(struct.pack("<III", 0x46546C67, 2, total))
            handle.write(struct.pack("<II", len(json_bytes), 0x4E4F534A))
            handle.write(json_bytes)
            handle.write(struct.pack("<II", len(bin_bytes), 0x004E4942))
            handle.write(bin_bytes)

        triangles = 0
        for mesh in self.meshes:
            for prim in mesh["primitives"]:
                triangles += self.accessors[prim["indices"]]["count"] // 3
        return {
            "path": path,
            "bytes": total,
            "nodes": len(self.nodes),
            "meshes": len(self.meshes),
            "materials": len(self.materials),
            "textures": len(self.textures),
            "animations": len(self.animations),
            "uniqueTriangles": triangles,
        }
