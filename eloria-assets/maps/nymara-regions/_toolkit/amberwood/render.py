"""Offline preview renderer.

Binds the C rasteriser in native/libraster.so and provides the camera, sky and
lighting rigs used for the concept-comparison captures.
"""
from __future__ import annotations

import ctypes
import math
import os
from dataclasses import dataclass, field

import numpy as np
from PIL import Image

_LIB_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                         "native", "libraster.so")


class _Material(ctypes.Structure):
    _fields_ = [
        ("base", ctypes.c_float * 4),
        ("roughness", ctypes.c_float),
        ("metallic", ctypes.c_float),
        ("emissive", ctypes.c_float * 3),
        ("albedo_layer", ctypes.c_int32),
        ("orm_layer", ctypes.c_int32),
        ("alpha_mode", ctypes.c_int32),
        ("alpha_cutoff", ctypes.c_float),
        ("double_sided", ctypes.c_int32),
    ]


class _Geometry(ctypes.Structure):
    _fields_ = [
        ("positions", ctypes.POINTER(ctypes.c_float)),
        ("normals", ctypes.POINTER(ctypes.c_float)),
        ("uvs", ctypes.POINTER(ctypes.c_float)),
        ("indices", ctypes.POINTER(ctypes.c_int32)),
        ("tri_material", ctypes.POINTER(ctypes.c_int32)),
        ("vertex_count", ctypes.c_int32),
        ("triangle_count", ctypes.c_int32),
    ]


class _TextureArray(ctypes.Structure):
    _fields_ = [("data", ctypes.POINTER(ctypes.c_uint8)),
                ("size", ctypes.c_int32), ("layers", ctypes.c_int32)]


class _Lighting(ctypes.Structure):
    _fields_ = [
        ("sun_direction", ctypes.c_float * 3),
        ("sun_color", ctypes.c_float * 3),
        ("sky_color", ctypes.c_float * 3),
        ("ground_color", ctypes.c_float * 3),
        ("fog_color", ctypes.c_float * 3),
        ("fog_density", ctypes.c_float),
        ("fog_height_falloff", ctypes.c_float),
        ("exposure", ctypes.c_float),
        ("ambient_strength", ctypes.c_float),
        ("shadow_bias", ctypes.c_float),
        ("shadow_strength", ctypes.c_float),
    ]


_lib = None


def _library():
    """Load the offline preview rasterizer only when a preview is requested.

    Continent retained-library generation imports the regional source modules
    for their authored geometry but never renders their optional minimaps. A
    clean checkout therefore does not need a platform C toolchain merely to
    compose production geometry.
    """
    global _lib
    if _lib is None:
        try:_lib = ctypes.CDLL(_LIB_PATH)
        except OSError as error:
            raise RuntimeError(
                f"offline preview rasterizer is unavailable at {_LIB_PATH}; run make -C native before rendering previews") from error
        _lib.render_scene.argtypes = [
            ctypes.POINTER(_Geometry), ctypes.POINTER(_Material), ctypes.c_int32,
            ctypes.POINTER(_TextureArray), ctypes.POINTER(ctypes.c_float),
            ctypes.POINTER(ctypes.c_float), ctypes.POINTER(_Lighting),
            ctypes.POINTER(ctypes.c_float), ctypes.POINTER(ctypes.c_float), ctypes.c_int32,
            ctypes.POINTER(ctypes.c_float), ctypes.POINTER(ctypes.c_float),
            ctypes.c_int32, ctypes.c_int32]
        _lib.render_shadow.argtypes = [
            ctypes.POINTER(_Geometry), ctypes.POINTER(ctypes.c_float),
            ctypes.POINTER(ctypes.c_float), ctypes.c_int32]
    return _lib


# --------------------------------------------------------------------------
# maths
# --------------------------------------------------------------------------

def look_at(eye, target, up=(0.0, 1.0, 0.0)) -> np.ndarray:
    eye = np.asarray(eye, dtype=np.float64)
    target = np.asarray(target, dtype=np.float64)
    forward = target - eye
    forward /= max(np.linalg.norm(forward), 1e-9)
    up = np.asarray(up, dtype=np.float64)
    right = np.cross(forward, up)
    if np.linalg.norm(right) < 1e-6:
        right = np.cross(forward, np.array([0.0, 0.0, 1.0]))
    right /= max(np.linalg.norm(right), 1e-9)
    true_up = np.cross(right, forward)
    m = np.eye(4)
    m[0, :3] = right
    m[1, :3] = true_up
    m[2, :3] = -forward
    m[0, 3] = -float(np.dot(right, eye))
    m[1, 3] = -float(np.dot(true_up, eye))
    m[2, 3] = float(np.dot(forward, eye))
    return m


def perspective(fov_degrees: float, aspect: float, near: float, far: float) -> np.ndarray:
    f = 1.0 / math.tan(math.radians(fov_degrees) * 0.5)
    m = np.zeros((4, 4))
    m[0, 0] = f / aspect
    m[1, 1] = f
    m[2, 2] = (far + near) / (near - far)
    m[2, 3] = 2.0 * far * near / (near - far)
    m[3, 2] = -1.0
    return m


def orthographic(width: float, height: float, near: float, far: float) -> np.ndarray:
    m = np.eye(4)
    m[0, 0] = 2.0 / width
    m[1, 1] = 2.0 / height
    m[2, 2] = -2.0 / (far - near)
    m[2, 3] = -(far + near) / (far - near)
    return m


def light_view_projection(direction, center, radius: float) -> np.ndarray:
    """Orthographic shadow frustum looking down the sun direction.

    The C side reads clip.w as the light-space depth, so the projection keeps
    w = distance along the light axis rather than 1.
    """
    direction = np.asarray(direction, dtype=np.float64)
    direction = direction / max(np.linalg.norm(direction), 1e-9)
    eye = np.asarray(center, dtype=np.float64) + direction * radius * 2.2
    view = look_at(eye, center)
    projection = np.eye(4)
    projection[0, 0] = 1.0 / radius
    projection[1, 1] = 1.0 / radius
    projection[2, 2] = -1.0     # clip.z = -view_z = metres in front of the light
    projection[3, 3] = 1.0
    return projection @ view


# --------------------------------------------------------------------------
# scene
# --------------------------------------------------------------------------

@dataclass
class RenderMaterial:
    name: str
    base_color: tuple = (1.0, 1.0, 1.0, 1.0)
    roughness: float = 0.9
    metallic: float = 0.0
    emissive: tuple = (0.0, 0.0, 0.0)
    albedo: str | None = None
    orm: str | None = None
    alpha_mode: str = "OPAQUE"
    alpha_cutoff: float = 0.5
    double_sided: bool = False


@dataclass
class Lighting:
    sun_direction: tuple = (-0.46, 0.46, 0.76)
    sun_color: tuple = (1.34, 1.06, 0.70)
    sky_color: tuple = (0.30, 0.38, 0.50)
    ground_color: tuple = (0.13, 0.10, 0.07)
    fog_color: tuple = (0.50, 0.48, 0.45)
    fog_density: float = 0.0016
    fog_height_falloff: float = 0.010
    exposure: float = 1.05
    ambient_strength: float = 0.40
    shadow_bias: float = 0.14
    shadow_strength: float = 0.88
    saturation: float = 1.0
    sky_zenith: tuple = (0.20, 0.31, 0.49)
    sky_horizon: tuple = (0.66, 0.62, 0.53)


class Scene:
    """Flattened, world-space triangle soup ready for the rasteriser."""

    def __init__(self) -> None:
        self.positions: list[np.ndarray] = []
        self.normals: list[np.ndarray] = []
        self.uvs: list[np.ndarray] = []
        self.indices: list[np.ndarray] = []
        self.tri_material: list[np.ndarray] = []
        self.materials: list[RenderMaterial] = []
        self._material_index: dict[str, int] = {}
        self._textures: dict[str, int] = {}
        self._texture_images: list[np.ndarray] = []
        self._offset = 0
        self._packed = None
        self._packed_textures = None

    def add_material(self, material: RenderMaterial) -> int:
        if material.name in self._material_index:
            return self._material_index[material.name]
        self.materials.append(material)
        index = len(self.materials) - 1
        self._material_index[material.name] = index
        return index

    def add_texture(self, name: str, rgba: np.ndarray) -> int:
        if name in self._textures:
            return self._textures[name]
        self._texture_images.append(rgba)
        index = len(self._texture_images) - 1
        self._textures[name] = index
        return index

    def add_mesh(self, mesh, transform: np.ndarray | None = None) -> None:
        if mesh.triangle_count == 0:
            return
        positions = mesh.positions
        normals = mesh.normals
        if transform is not None:
            homogeneous = np.hstack([positions, np.ones((positions.shape[0], 1))])
            positions = (homogeneous @ transform.T)[:, :3]
            normal_matrix = np.linalg.inv(transform[:3, :3]).T
            normals = normals @ normal_matrix.T
            normals /= np.maximum(np.linalg.norm(normals, axis=1, keepdims=True), 1e-9)
        self.positions.append(positions.astype(np.float32))
        self.normals.append(normals.astype(np.float32))
        self.uvs.append(mesh.uvs.astype(np.float32))
        self.indices.append((mesh.indices + self._offset).astype(np.int32))
        material = self._material_index.get(mesh.material, 0)
        self.tri_material.append(np.full(mesh.triangle_count, material, dtype=np.int32))
        self._offset += mesh.vertex_count

    def triangle_count(self) -> int:
        return int(sum(a.shape[0] for a in self.tri_material))

    def _pack(self):
        if getattr(self, "_packed", None) is not None:
            return self._packed
        positions = np.ascontiguousarray(np.vstack(self.positions), dtype=np.float32)
        normals = np.ascontiguousarray(np.vstack(self.normals), dtype=np.float32)
        uvs = np.ascontiguousarray(np.vstack(self.uvs), dtype=np.float32)
        indices = np.ascontiguousarray(np.concatenate(self.indices), dtype=np.int32)
        tri_material = np.ascontiguousarray(np.concatenate(self.tri_material), dtype=np.int32)
        geometry = _Geometry(
            positions.ctypes.data_as(ctypes.POINTER(ctypes.c_float)),
            normals.ctypes.data_as(ctypes.POINTER(ctypes.c_float)),
            uvs.ctypes.data_as(ctypes.POINTER(ctypes.c_float)),
            indices.ctypes.data_as(ctypes.POINTER(ctypes.c_int32)),
            tri_material.ctypes.data_as(ctypes.POINTER(ctypes.c_int32)),
            positions.shape[0], indices.shape[0] // 3)
        self._packed = (geometry, (positions, normals, uvs, indices, tri_material))
        return self._packed

    def _pack_textures(self):
        if getattr(self, "_packed_textures", None) is not None:
            return self._packed_textures
        size = 512
        if not self._texture_images:
            blob = np.full((1, size, size, 4), 255, dtype=np.uint8)
        else:
            layers = []
            for image in self._texture_images:
                if image.shape[0] != size:
                    pil = Image.fromarray(image, "RGBA").resize((size, size), Image.BILINEAR)
                    image = np.asarray(pil)
                layers.append(image)
            blob = np.stack(layers)
        blob = np.ascontiguousarray(blob, dtype=np.uint8)
        array = _TextureArray(blob.ctypes.data_as(ctypes.POINTER(ctypes.c_uint8)),
                              size, blob.shape[0])
        self._packed_textures = (array, blob)
        return self._packed_textures

    def _pack_materials(self):
        out = (_Material * len(self.materials))()
        for i, material in enumerate(self.materials):
            out[i].base = (ctypes.c_float * 4)(*material.base_color)
            out[i].roughness = material.roughness
            out[i].metallic = material.metallic
            out[i].emissive = (ctypes.c_float * 3)(*material.emissive)
            out[i].albedo_layer = self._textures.get(material.albedo, -1) \
                if material.albedo else -1
            out[i].orm_layer = self._textures.get(material.orm, -1) if material.orm else -1
            out[i].alpha_mode = {"OPAQUE": 0, "MASK": 1, "BLEND": 2}[material.alpha_mode]
            out[i].alpha_cutoff = material.alpha_cutoff
            out[i].double_sided = 1 if material.double_sided else 0
        return out

    # ---------------------------------------------------------------- render
    def probe(self, eye, target, fov: float = 55.0, width: int = 80,
              height: int = 56, near: float = 0.08, far: float = 1400.0) -> dict:
        """Cheap depth-only probe used to keep cameras out of solid geometry."""
        geometry, keep = self._pack()
        texture_array, texture_blob = self._pack_textures()
        materials = self._pack_materials()
        view_projection = np.ascontiguousarray(
            perspective(fov, width / height, near, far) @ look_at(eye, target),
            dtype=np.float32)
        camera_position = np.ascontiguousarray(np.asarray(eye, dtype=np.float32))
        light = _Lighting((ctypes.c_float * 3)(0.0, 1.0, 0.0),
                          (ctypes.c_float * 3)(1.0, 1.0, 1.0),
                          (ctypes.c_float * 3)(0.0, 0.0, 0.0),
                          (ctypes.c_float * 3)(0.0, 0.0, 0.0),
                          (ctypes.c_float * 3)(0.0, 0.0, 0.0),
                          0.0, 0.0, 1.0, 0.5, 0.1, 0.0)
        color = np.zeros(width * height * 3, dtype=np.float32)
        depth = np.zeros(width * height, dtype=np.float32)
        identity = np.ascontiguousarray(np.eye(4), dtype=np.float32)
        _library().render_scene(
            ctypes.byref(geometry), materials, len(self.materials),
            ctypes.byref(texture_array),
            view_projection.ctypes.data_as(ctypes.POINTER(ctypes.c_float)),
            camera_position.ctypes.data_as(ctypes.POINTER(ctypes.c_float)),
            ctypes.byref(light),
            identity.ctypes.data_as(ctypes.POINTER(ctypes.c_float)),
            None, 0,
            color.ctypes.data_as(ctypes.POINTER(ctypes.c_float)),
            depth.ctypes.data_as(ctypes.POINTER(ctypes.c_float)),
            width, height)
        del keep, texture_blob
        hit = depth < 1e29
        finite = depth[hit]
        sky = float(1.0 - finite.size / depth.size)
        if finite.size == 0:
            return {"median": float("inf"), "near_fraction": 0.0, "sky": 1.0,
                    "open_fraction": 1.0}
        return {"median": float(np.median(finite)),
                "near_fraction": float((finite < 2.0).mean()),
                "sky": sky,
                "depth": depth}

    def render(self, eye, target, width: int = 1024, height: int = 640,
               fov: float = 55.0, lighting: Lighting | None = None,
               shadows: bool = True, shadow_size: int = 2048,
               shadow_center=None, shadow_radius: float = 120.0,
               near: float = 0.12, far: float = 1400.0) -> Image.Image:
        lighting = lighting or Lighting()
        geometry, keep = self._pack()
        texture_array, texture_blob = self._pack_textures()
        materials = self._pack_materials()

        view_projection = np.ascontiguousarray(
            perspective(fov, width / height, near, far) @ look_at(eye, target),
            dtype=np.float32)
        camera_position = np.ascontiguousarray(np.asarray(eye, dtype=np.float32))

        shadow_depth_ptr = None
        light_matrix = np.ascontiguousarray(np.eye(4), dtype=np.float32)
        shadow_buffer = None
        if shadows:
            center = np.asarray(shadow_center if shadow_center is not None else target,
                                dtype=np.float64)
            light_matrix = np.ascontiguousarray(
                light_view_projection(lighting.sun_direction, center, shadow_radius),
                dtype=np.float32)
            shadow_buffer = np.zeros(shadow_size * shadow_size, dtype=np.float32)
            _library().render_shadow(ctypes.byref(geometry),
                               light_matrix.ctypes.data_as(ctypes.POINTER(ctypes.c_float)),
                               shadow_buffer.ctypes.data_as(ctypes.POINTER(ctypes.c_float)),
                               shadow_size)
            shadow_depth_ptr = shadow_buffer.ctypes.data_as(ctypes.POINTER(ctypes.c_float))

        light = _Lighting(
            (ctypes.c_float * 3)(*_normalised(lighting.sun_direction)),
            (ctypes.c_float * 3)(*lighting.sun_color),
            (ctypes.c_float * 3)(*lighting.sky_color),
            (ctypes.c_float * 3)(*lighting.ground_color),
            (ctypes.c_float * 3)(*lighting.fog_color),
            lighting.fog_density, lighting.fog_height_falloff, lighting.exposure,
            lighting.ambient_strength, lighting.shadow_bias, lighting.shadow_strength)

        color = _sky_background(width, height, eye, target, fov, lighting)
        depth = np.zeros(width * height, dtype=np.float32)
        color_flat = np.ascontiguousarray(color.reshape(-1), dtype=np.float32)
        _library().render_scene(
            ctypes.byref(geometry), materials, len(self.materials),
            ctypes.byref(texture_array),
            view_projection.ctypes.data_as(ctypes.POINTER(ctypes.c_float)),
            camera_position.ctypes.data_as(ctypes.POINTER(ctypes.c_float)),
            ctypes.byref(light),
            light_matrix.ctypes.data_as(ctypes.POINTER(ctypes.c_float)),
            shadow_depth_ptr, shadow_size if shadows else 0,
            color_flat.ctypes.data_as(ctypes.POINTER(ctypes.c_float)),
            depth.ctypes.data_as(ctypes.POINTER(ctypes.c_float)),
            width, height)
        del keep, texture_blob, shadow_buffer

        image = color_flat.reshape(height, width, 3)
        return _tonemap(image, lighting.exposure, lighting.saturation)


def _normalised(v):
    v = np.asarray(v, dtype=np.float64)
    return v / max(np.linalg.norm(v), 1e-9)


def _sky_background(width: int, height: int, eye, target, fov: float,
                    lighting: Lighting) -> np.ndarray:
    """Gradient sky with a sun glow, projected through the same camera."""
    eye = np.asarray(eye, dtype=np.float64)
    target = np.asarray(target, dtype=np.float64)
    forward = _normalised(target - eye)
    right = _normalised(np.cross(forward, np.array([0.0, 1.0, 0.0])))
    up = np.cross(right, forward)
    aspect = width / height
    half = math.tan(math.radians(fov) * 0.5)
    xs = (np.arange(width) + 0.5) / width * 2.0 - 1.0
    ys = 1.0 - (np.arange(height) + 0.5) / height * 2.0
    gx, gy = np.meshgrid(xs * half * aspect, ys * half)
    directions = (forward[None, None, :] + right[None, None, :] * gx[..., None]
                  + up[None, None, :] * gy[..., None])
    directions /= np.linalg.norm(directions, axis=2, keepdims=True)
    elevation = np.clip(directions[..., 1], -1.0, 1.0)
    t = np.clip(elevation * 1.35 + 0.12, 0.0, 1.0) ** 0.75
    zenith = np.asarray(lighting.sky_zenith)
    horizon = np.asarray(lighting.sky_horizon)
    sky = horizon[None, None, :] + (zenith - horizon)[None, None, :] * t[..., None]
    sun = _normalised(lighting.sun_direction)
    glow = np.clip(np.einsum("ijk,k->ij", directions, sun), 0.0, 1.0)
    sky += np.asarray(lighting.sun_color)[None, None, :] * (glow ** 90.0)[..., None] * 0.85
    sky += np.asarray(lighting.sun_color)[None, None, :] * (glow ** 9.0)[..., None] * 0.16
    below = np.clip(-elevation * 4.0, 0.0, 1.0)
    sky = sky * (1.0 - below[..., None]) + np.asarray(lighting.fog_color)[None, None, :] \
        * below[..., None]
    return sky.astype(np.float32)


def _tonemap(image: np.ndarray, exposure: float, saturation: float = 1.0) -> Image.Image:
    x = np.clip(image * exposure, 0.0, 60.0)
    # filmic-ish shoulder keeps the amber highlights from clipping to white
    mapped = (x * (2.51 * x + 0.03)) / (x * (2.43 * x + 0.59) + 0.14)
    mapped = np.clip(mapped, 0.0, 1.0)
    if abs(saturation - 1.0) > 1e-3:
        luma = (mapped * np.array([0.2126, 0.7152, 0.0722])).sum(axis=-1, keepdims=True)
        mapped = np.clip(luma + (mapped - luma) * saturation, 0.0, 1.0)
    mapped = mapped ** (1.0 / 2.2)
    return Image.fromarray((mapped * 255.0 + 0.5).astype(np.uint8), "RGB")
