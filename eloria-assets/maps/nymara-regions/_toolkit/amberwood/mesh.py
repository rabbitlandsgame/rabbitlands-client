"""Triangle mesh container and modelling primitives.

Conventions (matched to the Godot world loader and the glTF export):
  * right-handed, metres, Y up, -Z north
  * counter-clockwise winding when viewed from the front face
  * every vertex carries POSITION, NORMAL, TEXCOORD_0; TANGENT is generated on
    demand for the materials that use a normal map
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Iterable, Sequence

import numpy as np

Vec3 = Sequence[float]


# --------------------------------------------------------------------------
# transforms
# --------------------------------------------------------------------------

def identity() -> np.ndarray:
    return np.eye(4, dtype=np.float64)


def translation(x: float, y: float, z: float) -> np.ndarray:
    m = np.eye(4)
    m[0, 3], m[1, 3], m[2, 3] = x, y, z
    return m


def scaling(x: float, y: float = None, z: float = None) -> np.ndarray:
    if y is None:
        y = x
    if z is None:
        z = x
    m = np.eye(4)
    m[0, 0], m[1, 1], m[2, 2] = x, y, z
    return m


def rotation_x(radians: float) -> np.ndarray:
    c, s = math.cos(radians), math.sin(radians)
    m = np.eye(4)
    m[1, 1], m[1, 2], m[2, 1], m[2, 2] = c, -s, s, c
    return m


def rotation_y(radians: float) -> np.ndarray:
    c, s = math.cos(radians), math.sin(radians)
    m = np.eye(4)
    m[0, 0], m[0, 2], m[2, 0], m[2, 2] = c, s, -s, c
    return m


def rotation_z(radians: float) -> np.ndarray:
    c, s = math.cos(radians), math.sin(radians)
    m = np.eye(4)
    m[0, 0], m[0, 1], m[1, 0], m[1, 1] = c, -s, s, c
    return m


def basis_from_direction(direction: Vec3) -> np.ndarray:
    """Orthonormal basis whose +Y maps onto `direction`."""
    d = np.asarray(direction, dtype=np.float64)
    length = np.linalg.norm(d)
    if length < 1e-9:
        return np.eye(4)
    d = d / length
    reference = np.array([0.0, 0.0, 1.0]) if abs(d[1]) > 0.95 else np.array([0.0, 1.0, 0.0])
    right = np.cross(reference, d)
    right /= max(np.linalg.norm(right), 1e-9)
    forward = np.cross(d, right)
    m = np.eye(4)
    m[:3, 0] = right
    m[:3, 1] = d
    m[:3, 2] = forward
    return m


# --------------------------------------------------------------------------
# mesh
# --------------------------------------------------------------------------

@dataclass
class Mesh:
    positions: np.ndarray = field(default_factory=lambda: np.zeros((0, 3), np.float64))
    normals: np.ndarray = field(default_factory=lambda: np.zeros((0, 3), np.float64))
    uvs: np.ndarray = field(default_factory=lambda: np.zeros((0, 2), np.float64))
    colors: np.ndarray | None = None
    indices: np.ndarray = field(default_factory=lambda: np.zeros((0,), np.int64))
    material: str = "default"

    # -- basic queries ----------------------------------------------------
    @property
    def vertex_count(self) -> int:
        return int(self.positions.shape[0])

    @property
    def triangle_count(self) -> int:
        return int(self.indices.shape[0] // 3)

    def bounds(self) -> tuple[np.ndarray, np.ndarray]:
        if self.vertex_count == 0:
            zero = np.zeros(3)
            return zero, zero.copy()
        return self.positions.min(axis=0), self.positions.max(axis=0)

    def copy(self) -> "Mesh":
        return Mesh(
            positions=self.positions.copy(),
            normals=self.normals.copy(),
            uvs=self.uvs.copy(),
            colors=None if self.colors is None else self.colors.copy(),
            indices=self.indices.copy(),
            material=self.material,
        )

    # -- transforms -------------------------------------------------------
    def transform(self, matrix: np.ndarray) -> "Mesh":
        m = np.asarray(matrix, dtype=np.float64)
        if self.vertex_count:
            homogeneous = np.hstack([self.positions, np.ones((self.vertex_count, 1))])
            self.positions = (homogeneous @ m.T)[:, :3]
            normal_matrix = np.linalg.inv(m[:3, :3]).T
            n = self.normals @ normal_matrix.T
            lengths = np.linalg.norm(n, axis=1, keepdims=True)
            self.normals = n / np.maximum(lengths, 1e-9)
            if np.linalg.det(m[:3, :3]) < 0:
                self.flip_winding()
        return self

    def transformed(self, matrix: np.ndarray) -> "Mesh":
        return self.copy().transform(matrix)

    def translate(self, x: float, y: float, z: float) -> "Mesh":
        return self.transform(translation(x, y, z))

    def scale(self, x: float, y: float = None, z: float = None) -> "Mesh":
        return self.transform(scaling(x, y, z))

    def rotate_y(self, radians: float) -> "Mesh":
        return self.transform(rotation_y(radians))

    def rotate_x(self, radians: float) -> "Mesh":
        return self.transform(rotation_x(radians))

    def rotate_z(self, radians: float) -> "Mesh":
        return self.transform(rotation_z(radians))

    def flip_winding(self) -> "Mesh":
        idx = self.indices.reshape(-1, 3)[:, ::-1]
        self.indices = idx.reshape(-1)
        return self

    def with_material(self, material: str) -> "Mesh":
        self.material = material
        return self

    # -- editing ----------------------------------------------------------
    def set_color(self, rgba) -> "Mesh":
        rgba = np.asarray(rgba, dtype=np.float64)
        if rgba.shape == (3,):
            rgba = np.concatenate([rgba, [1.0]])
        self.colors = np.tile(rgba, (self.vertex_count, 1))
        return self

    def tint_by_height(self, low_rgba, high_rgba, y_low: float, y_high: float) -> "Mesh":
        low = np.asarray(low_rgba, dtype=np.float64)
        high = np.asarray(high_rgba, dtype=np.float64)
        t = np.clip((self.positions[:, 1] - y_low) / max(y_high - y_low, 1e-6), 0.0, 1.0)
        self.colors = low[None, :] + (high - low)[None, :] * t[:, None]
        return self

    def jitter(self, amount: float, seed: int = 0, axis_scale=(1.0, 1.0, 1.0)) -> "Mesh":
        """Break up machine-perfect surfaces. Shared positions move together."""
        if self.vertex_count == 0 or amount <= 0.0:
            return self
        keys = np.round(self.positions * 512.0).astype(np.int64)
        unique, inverse = np.unique(keys, axis=0, return_inverse=True)
        rng = np.random.default_rng(seed)
        offsets = rng.normal(0.0, amount, size=(unique.shape[0], 3))
        offsets *= np.asarray(axis_scale, dtype=np.float64)[None, :]
        self.positions = self.positions + offsets[inverse]
        return self

    def weld(self, tolerance: float = 1e-5) -> "Mesh":
        """Merge coincident vertices that also share normal and uv."""
        if self.vertex_count == 0:
            return self
        quantum = max(tolerance, 1e-9)
        key = np.hstack([
            np.round(self.positions / quantum),
            np.round(self.normals * 4096.0),
            np.round(self.uvs * 4096.0),
        ]).astype(np.int64)
        _, first, inverse = np.unique(key, axis=0, return_index=True, return_inverse=True)
        order = np.argsort(first)
        remap = np.zeros(order.shape[0], dtype=np.int64)
        remap[order] = np.arange(order.shape[0])
        keep = first[order]
        self.positions = self.positions[keep]
        self.normals = self.normals[keep]
        self.uvs = self.uvs[keep]
        if self.colors is not None:
            self.colors = self.colors[keep]
        self.indices = remap[inverse[self.indices]]
        return self

    def recompute_normals(self, smooth_angle_degrees: float = 60.0) -> "Mesh":
        """Angle-weighted smoothing; hard edges above the crease angle survive."""
        if self.triangle_count == 0:
            return self
        tris = self.indices.reshape(-1, 3)
        p0 = self.positions[tris[:, 0]]
        p1 = self.positions[tris[:, 1]]
        p2 = self.positions[tris[:, 2]]
        face_normals = np.cross(p1 - p0, p2 - p0)
        lengths = np.linalg.norm(face_normals, axis=1, keepdims=True)
        face_normals = face_normals / np.maximum(lengths, 1e-12)

        position_key = np.round(self.positions * 4096.0).astype(np.int64)
        _, group = np.unique(position_key, axis=0, return_inverse=True)

        accumulated = np.zeros((int(group.max()) + 1, 3))
        for corner in range(3):
            np.add.at(accumulated, group[tris[:, corner]], face_normals)
        lengths = np.linalg.norm(accumulated, axis=1, keepdims=True)
        averaged = accumulated / np.maximum(lengths, 1e-12)

        threshold = math.cos(math.radians(smooth_angle_degrees))
        out = np.zeros_like(self.positions)
        counts = np.zeros(self.vertex_count)
        for corner in range(3):
            vertex_ids = tris[:, corner]
            smooth = averaged[group[vertex_ids]]
            dot = np.einsum("ij,ij->i", smooth, face_normals)
            chosen = np.where((dot >= threshold)[:, None], smooth, face_normals)
            np.add.at(out, vertex_ids, chosen)
            np.add.at(counts, vertex_ids, 1.0)
        lengths = np.linalg.norm(out, axis=1, keepdims=True)
        self.normals = np.where(lengths > 1e-12, out / np.maximum(lengths, 1e-12),
                                np.array([0.0, 1.0, 0.0])[None, :])
        return self

    def tangents(self) -> np.ndarray:
        """Mikk-style averaged tangents with handedness in w."""
        tangent = np.zeros((self.vertex_count, 3))
        bitangent = np.zeros((self.vertex_count, 3))
        tris = self.indices.reshape(-1, 3)
        p0, p1, p2 = (self.positions[tris[:, i]] for i in range(3))
        w0, w1, w2 = (self.uvs[tris[:, i]] for i in range(3))
        e1, e2 = p1 - p0, p2 - p0
        d1, d2 = w1 - w0, w2 - w0
        denominator = d1[:, 0] * d2[:, 1] - d2[:, 0] * d1[:, 1]
        r = np.where(np.abs(denominator) < 1e-12, 0.0, 1.0 / np.where(
            np.abs(denominator) < 1e-12, 1.0, denominator))
        t = (e1 * d2[:, 1:2] - e2 * d1[:, 1:2]) * r[:, None]
        b = (e2 * d1[:, 0:1] - e1 * d2[:, 0:1]) * r[:, None]
        for corner in range(3):
            np.add.at(tangent, tris[:, corner], t)
            np.add.at(bitangent, tris[:, corner], b)
        n = self.normals
        t = tangent - n * np.einsum("ij,ij->i", n, tangent)[:, None]
        lengths = np.linalg.norm(t, axis=1, keepdims=True)
        fallback = np.cross(n, np.array([0.0, 0.0, 1.0])[None, :])
        fallback_len = np.linalg.norm(fallback, axis=1, keepdims=True)
        fallback = np.where(fallback_len > 1e-6, fallback / np.maximum(fallback_len, 1e-9),
                            np.array([1.0, 0.0, 0.0])[None, :])
        t = np.where(lengths > 1e-6, t / np.maximum(lengths, 1e-9), fallback)
        handedness = np.sign(np.einsum("ij,ij->i", np.cross(n, t), bitangent))
        handedness[handedness == 0.0] = 1.0
        return np.hstack([t, handedness[:, None]])

    def scale_uv(self, u: float, v: float = None) -> "Mesh":
        if v is None:
            v = u
        self.uvs = self.uvs * np.array([u, v])
        return self

    def offset_uv(self, u: float, v: float) -> "Mesh":
        self.uvs = self.uvs + np.array([u, v])
        return self

    def project_uv_triplanar(self, scale: float = 1.0) -> "Mesh":
        """World-space triplanar UVs - constant texel density on organic shapes."""
        n = np.abs(self.normals)
        p = self.positions * scale
        uv = np.where((n[:, 0:1] >= n[:, 1:2]) & (n[:, 0:1] >= n[:, 2:3]),
                      p[:, [2, 1]],
                      np.where(n[:, 1:2] >= n[:, 2:3], p[:, [0, 2]], p[:, [0, 1]]))
        self.uvs = uv
        return self

    def sanitise_normals(self, fallback=(0.0, 1.0, 0.0)) -> "Mesh":
        """Guarantee unit-length normals; glTF requires them and Godot shades
        a zero-length normal as black."""
        if self.vertex_count == 0:
            return self
        lengths = np.linalg.norm(self.normals, axis=1, keepdims=True)
        bad = lengths < 1e-6
        if bad.any():
            self.normals = np.where(bad, np.asarray(fallback, dtype=np.float64)[None, :],
                                    self.normals)
            lengths = np.linalg.norm(self.normals, axis=1, keepdims=True)
        self.normals = self.normals / np.maximum(lengths, 1e-12)
        return self

    def drop_degenerate(self, min_area: float = 1e-10) -> "Mesh":
        tris = self.indices.reshape(-1, 3)
        p0, p1, p2 = (self.positions[tris[:, i]] for i in range(3))
        area = 0.5 * np.linalg.norm(np.cross(p1 - p0, p2 - p0), axis=1)
        keep = area > min_area
        self.indices = tris[keep].reshape(-1)
        return self


def merge(meshes: Iterable[Mesh], material: str | None = None) -> Mesh:
    meshes = [m for m in meshes if m is not None and m.triangle_count > 0]
    if not meshes:
        return Mesh(material=material or "default")
    positions = np.vstack([m.positions for m in meshes])
    normals = np.vstack([m.normals for m in meshes])
    uvs = np.vstack([m.uvs for m in meshes])
    any_colors = any(m.colors is not None for m in meshes)
    colors = None
    if any_colors:
        colors = np.vstack([
            m.colors if m.colors is not None else np.ones((m.vertex_count, 4))
            for m in meshes])
    indices = []
    offset = 0
    for m in meshes:
        indices.append(m.indices + offset)
        offset += m.vertex_count
    return Mesh(positions, normals, uvs, colors, np.concatenate(indices),
                material or meshes[0].material)


# --------------------------------------------------------------------------
# primitives
# --------------------------------------------------------------------------

def _make(positions, normals, uvs, indices, material="default") -> Mesh:
    return Mesh(np.asarray(positions, np.float64), np.asarray(normals, np.float64),
                np.asarray(uvs, np.float64), None,
                np.asarray(indices, np.int64).reshape(-1), material)


def quad(corners: Sequence[Vec3], uv_scale: float = 1.0, material: str = "default") -> Mesh:
    p = np.asarray(corners, dtype=np.float64)
    n = np.cross(p[1] - p[0], p[2] - p[0])
    n = n / max(np.linalg.norm(n), 1e-12)
    du = np.linalg.norm(p[1] - p[0]) * uv_scale
    dv = np.linalg.norm(p[3] - p[0]) * uv_scale
    uvs = np.array([[0, 0], [du, 0], [du, dv], [0, dv]], dtype=np.float64)
    return _make(p, np.tile(n, (4, 1)), uvs, [0, 1, 2, 0, 2, 3], material)


def box(size: Vec3, center: Vec3 = (0, 0, 0), uv_scale: float = 1.0,
        material: str = "default") -> Mesh:
    sx, sy, sz = (float(v) * 0.5 for v in size)
    cx, cy, cz = center
    faces = [
        # (corner order CCW seen from outside, normal, uv extents)
        ([(-sx, -sy, sz), (sx, -sy, sz), (sx, sy, sz), (-sx, sy, sz)], (0, 0, 1), (sx, sy)),
        ([(sx, -sy, -sz), (-sx, -sy, -sz), (-sx, sy, -sz), (sx, sy, -sz)], (0, 0, -1), (sx, sy)),
        ([(sx, -sy, sz), (sx, -sy, -sz), (sx, sy, -sz), (sx, sy, sz)], (1, 0, 0), (sz, sy)),
        ([(-sx, -sy, -sz), (-sx, -sy, sz), (-sx, sy, sz), (-sx, sy, -sz)], (-1, 0, 0), (sz, sy)),
        ([(-sx, sy, sz), (sx, sy, sz), (sx, sy, -sz), (-sx, sy, -sz)], (0, 1, 0), (sx, sz)),
        ([(-sx, -sy, -sz), (sx, -sy, -sz), (sx, -sy, sz), (-sx, -sy, sz)], (0, -1, 0), (sx, sz)),
    ]
    positions, normals, uvs, indices = [], [], [], []
    for corners, normal, (eu, ev) in faces:
        base = len(positions)
        for corner in corners:
            positions.append((corner[0] + cx, corner[1] + cy, corner[2] + cz))
            normals.append(normal)
        u = 2.0 * eu * uv_scale
        v = 2.0 * ev * uv_scale
        uvs.extend([[0, 0], [u, 0], [u, v], [0, v]])
        indices.extend([base, base + 1, base + 2, base, base + 2, base + 3])
    return _make(positions, normals, uvs, indices, material)


def cylinder(radius_bottom: float, radius_top: float, height: float, segments: int = 12,
             cap_bottom: bool = True, cap_top: bool = True, uv_scale: float = 1.0,
             material: str = "default", radial_profile=None) -> Mesh:
    """Y-axis tapered cylinder starting at y=0.

    `radial_profile` is an optional callable(angle_index, segments) -> multiplier
    used to give trunks and columns a non-circular cross-section.
    """
    positions, normals, uvs, indices = [], [], [], []
    angles = np.linspace(0.0, 2.0 * math.pi, segments + 1)
    profile = np.ones(segments + 1)
    if radial_profile is not None:
        profile = np.array([radial_profile(i % segments, segments) for i in range(segments + 1)])
    circumference = 2.0 * math.pi * max(radius_bottom, radius_top)
    for i, angle in enumerate(angles):
        c, s = math.cos(angle), math.sin(angle)
        rb = radius_bottom * profile[i]
        rt = radius_top * profile[i]
        slope = (rb - rt) / max(height, 1e-6)
        n = np.array([c, slope, s])
        n /= max(np.linalg.norm(n), 1e-9)
        u = circumference * (i / segments) * uv_scale
        positions.append((c * rb, 0.0, s * rb))
        normals.append(n)
        uvs.append([u, 0.0])
        positions.append((c * rt, height, s * rt))
        normals.append(n)
        uvs.append([u, height * uv_scale])
    for i in range(segments):
        a = i * 2
        indices.extend([a, a + 2, a + 3, a, a + 3, a + 1])
    for cap, y, radius, normal, flip in (
            (cap_bottom, 0.0, radius_bottom, (0, -1, 0), True),
            (cap_top, height, radius_top, (0, 1, 0), False)):
        if not cap or radius <= 1e-6:
            continue
        center = len(positions)
        positions.append((0.0, y, 0.0))
        normals.append(normal)
        uvs.append([0.0, 0.0])
        ring = []
        for i in range(segments):
            angle = angles[i]
            c, s = math.cos(angle), math.sin(angle)
            r = radius * profile[i]
            ring.append(len(positions))
            positions.append((c * r, y, s * r))
            normals.append(normal)
            uvs.append([c * r * uv_scale, s * r * uv_scale])
        for i in range(segments):
            a, b = ring[i], ring[(i + 1) % segments]
            indices.extend([center, b, a] if flip else [center, a, b])
    return _make(positions, normals, uvs, indices, material)


def tube(path: np.ndarray, radii: Sequence[float], segments: int = 8,
         cap_start: bool = False, cap_end: bool = False, uv_scale: float = 1.0,
         twist: float = 0.0, material: str = "default",
         radial_profile=None) -> Mesh:
    """Swept tube along a polyline - trunks, branches, roots, ropes, pipes."""
    path = np.asarray(path, dtype=np.float64)
    if path.shape[0] < 2:
        return Mesh(material=material)
    radii = np.asarray(radii, dtype=np.float64)
    if radii.ndim == 0:
        radii = np.full(path.shape[0], float(radii))
    tangents = np.zeros_like(path)
    tangents[1:-1] = path[2:] - path[:-2]
    tangents[0] = path[1] - path[0]
    tangents[-1] = path[-1] - path[-2]
    lengths = np.linalg.norm(tangents, axis=1, keepdims=True)
    tangents = tangents / np.maximum(lengths, 1e-9)

    # parallel transport frame keeps the tube from spinning at bends
    reference = np.array([0.0, 0.0, 1.0])
    if abs(float(np.dot(tangents[0], reference))) > 0.95:
        reference = np.array([1.0, 0.0, 0.0])
    normal = reference - tangents[0] * float(np.dot(reference, tangents[0]))
    normal /= max(np.linalg.norm(normal), 1e-9)
    frames = [normal]
    for i in range(1, path.shape[0]):
        previous = frames[-1]
        axis = np.cross(tangents[i - 1], tangents[i])
        axis_length = np.linalg.norm(axis)
        if axis_length < 1e-9:
            frames.append(previous)
            continue
        axis = axis / axis_length
        angle = math.atan2(axis_length, float(np.dot(tangents[i - 1], tangents[i])))
        c, s = math.cos(angle), math.sin(angle)
        rotated = (previous * c + np.cross(axis, previous) * s
                   + axis * float(np.dot(axis, previous)) * (1.0 - c))
        rotated -= tangents[i] * float(np.dot(rotated, tangents[i]))
        rotated /= max(np.linalg.norm(rotated), 1e-9)
        frames.append(rotated)

    distances = np.concatenate([[0.0], np.cumsum(np.linalg.norm(np.diff(path, axis=0), axis=1))])
    profile = np.ones(segments)
    if radial_profile is not None:
        profile = np.array([radial_profile(i, segments) for i in range(segments)])

    positions, normals, uvs = [], [], []
    for i in range(path.shape[0]):
        binormal = np.cross(tangents[i], frames[i])
        for j in range(segments + 1):
            k = j % segments
            angle = 2.0 * math.pi * j / segments + twist * distances[i]
            direction = frames[i] * math.cos(angle) + binormal * math.sin(angle)
            r = radii[i] * profile[k]
            positions.append(path[i] + direction * r)
            normals.append(direction)
            uvs.append([2.0 * math.pi * radii.max() * (j / segments) * uv_scale,
                        distances[i] * uv_scale])
    stride = segments + 1
    indices = []
    for i in range(path.shape[0] - 1):
        for j in range(segments):
            a = i * stride + j
            b = a + 1
            c = a + stride
            d = c + 1
            indices.extend([a, c, d, a, d, b])
    mesh = _make(positions, normals, uvs, indices, material)
    caps = []
    if cap_start:
        caps.append(_disc(path[0], -tangents[0], radii[0], segments, material))
    if cap_end:
        caps.append(_disc(path[-1], tangents[-1], radii[-1], segments, material))
    if caps:
        mesh = merge([mesh] + caps, material)
    return mesh


def _disc(center: np.ndarray, normal: np.ndarray, radius: float, segments: int,
          material: str) -> Mesh:
    normal = np.asarray(normal, dtype=np.float64)
    normal = normal / max(np.linalg.norm(normal), 1e-9)
    reference = np.array([0.0, 0.0, 1.0]) if abs(normal[1]) > 0.95 else np.array([0.0, 1.0, 0.0])
    u = np.cross(reference, normal)
    u /= max(np.linalg.norm(u), 1e-9)
    v = np.cross(normal, u)
    positions = [center]
    normals = [normal]
    uvs = [[0.0, 0.0]]
    for i in range(segments):
        angle = 2.0 * math.pi * i / segments
        offset = (u * math.cos(angle) + v * math.sin(angle)) * radius
        positions.append(center + offset)
        normals.append(normal)
        uvs.append([math.cos(angle) * radius, math.sin(angle) * radius])
    indices = []
    for i in range(segments):
        indices.extend([0, 1 + i, 1 + (i + 1) % segments])
    return _make(positions, normals, uvs, indices, material)


def lathe(profile: Sequence[Sequence[float]], segments: int = 16, arc: float = 2.0 * math.pi,
          uv_scale: float = 1.0, material: str = "default") -> Mesh:
    """Revolve a 2D (radius, height) profile around +Y."""
    profile = np.asarray(profile, dtype=np.float64)
    rings = profile.shape[0]
    closed = abs(arc - 2.0 * math.pi) < 1e-6
    count = segments if closed else segments + 1
    positions, normals, uvs, indices = [], [], [], []
    for i in range(count):
        angle = arc * (i / segments)
        c, s = math.cos(angle), math.sin(angle)
        for j in range(rings):
            r, y = profile[j]
            positions.append((c * r, y, s * r))
            if j == 0:
                dr, dy = profile[1] - profile[0]
            elif j == rings - 1:
                dr, dy = profile[-1] - profile[-2]
            else:
                dr, dy = profile[j + 1] - profile[j - 1]
            n = np.array([c * dy, -dr, s * dy])
            n /= max(np.linalg.norm(n), 1e-9)
            normals.append(n)
            uvs.append([arc * profile[:, 0].max() * (i / segments) * uv_scale, y * uv_scale])
    for i in range(count if closed else count - 1):
        i_next = (i + 1) % count if closed else i + 1
        for j in range(rings - 1):
            a = i * rings + j
            b = i * rings + j + 1
            c = i_next * rings + j
            d = i_next * rings + j + 1
            indices.extend([a, c, d, a, d, b])
    return _make(positions, normals, uvs, indices, material)


def extrude(polygon: Sequence[Sequence[float]], height: float, cap: bool = True,
            uv_scale: float = 1.0, material: str = "default") -> Mesh:
    """Extrude a CCW XZ polygon upward from y=0."""
    poly = np.asarray(polygon, dtype=np.float64)
    n = poly.shape[0]
    positions, normals, uvs, indices = [], [], [], []
    running = 0.0
    for i in range(n):
        a = poly[i]
        b = poly[(i + 1) % n]
        edge = b - a
        length = float(np.linalg.norm(edge))
        if length < 1e-9:
            continue
        normal = np.array([edge[1], 0.0, -edge[0]])
        normal /= max(np.linalg.norm(normal), 1e-9)
        base = len(positions)
        positions.extend([(a[0], 0.0, a[1]), (b[0], 0.0, b[1]),
                          (b[0], height, b[1]), (a[0], height, a[1])])
        normals.extend([normal] * 4)
        uvs.extend([[running * uv_scale, 0.0], [(running + length) * uv_scale, 0.0],
                    [(running + length) * uv_scale, height * uv_scale],
                    [running * uv_scale, height * uv_scale]])
        indices.extend([base, base + 1, base + 2, base, base + 2, base + 3])
        running += length
    if cap:
        for y, normal, flip in ((height, (0, 1, 0), False), (0.0, (0, -1, 0), True)):
            base = len(positions)
            for point in poly:
                positions.append((point[0], y, point[1]))
                normals.append(normal)
                uvs.append([point[0] * uv_scale, point[1] * uv_scale])
            for i in range(1, n - 1):
                tri = [base, base + i, base + i + 1]
                indices.extend(tri[::-1] if flip else tri)
    return _make(positions, normals, uvs, indices, material)


def loft(sections: Sequence[np.ndarray], closed_rings: bool = True, cap_ends: bool = False,
         uv_scale: float = 1.0, material: str = "default") -> Mesh:
    """Skin a stack of equal-length 3D rings."""
    rings = [np.asarray(s, dtype=np.float64) for s in sections]
    count = rings[0].shape[0]
    positions, uvs, indices = [], [], []
    for i, ring in enumerate(rings):
        for j in range(count):
            positions.append(ring[j])
            uvs.append([j / count * uv_scale * 4.0, i / max(len(rings) - 1, 1) * uv_scale * 4.0])
    for i in range(len(rings) - 1):
        for j in range(count if closed_rings else count - 1):
            j2 = (j + 1) % count
            a = i * count + j
            b = i * count + j2
            c = (i + 1) * count + j
            d = (i + 1) * count + j2
            indices.extend([a, c, d, a, d, b])
    mesh = _make(positions, np.zeros((len(positions), 3)), uvs, indices, material)
    mesh.recompute_normals(75.0)
    return mesh


def heightfield(heights: np.ndarray, x0: float, z0: float, cell: float,
                uv_scale: float = 1.0, material: str = "default",
                mask: np.ndarray | None = None,
                cells: np.ndarray | None = None) -> Mesh:
    """Grid mesh from a (rows, cols) height array. rows advance +Z, cols advance +X.

    `mask` is a per-vertex predicate and keeps a quad only when all four of its
    corners pass; that is what "is this sample under water" wants. `cells` is a
    per-quad predicate of shape (rows - 1, cols - 1) and keeps exactly the quads
    it selects. A caller splitting one field into class sub-meshes must use
    `cells`: expressing the split as a vertex mask emits every quad whose four
    corners merely touch the class, so a quad surrounded by another class lands
    in both sub-meshes and the two copies z-fight.
    """
    rows, cols = heights.shape
    xs = x0 + np.arange(cols) * cell
    zs = z0 + np.arange(rows) * cell
    gx, gz = np.meshgrid(xs, zs)
    positions = np.stack([gx, heights, gz], axis=-1).reshape(-1, 3)
    uvs = np.stack([gx * uv_scale, gz * uv_scale], axis=-1).reshape(-1, 2)
    i0 = np.arange(rows - 1)[:, None] * cols + np.arange(cols - 1)[None, :]
    a = i0
    b = i0 + 1
    c = i0 + cols
    d = i0 + cols + 1
    tris = np.stack([a, c, d, a, d, b], axis=-1).reshape(-1, 3)
    cell_mask = None
    if mask is not None:
        cell_mask = mask[:-1, :-1] & mask[1:, :-1] & mask[:-1, 1:] & mask[1:, 1:]
    if cells is not None:
        cell_mask = cells if cell_mask is None else (cell_mask & cells)
    if cell_mask is not None:
        keep = np.repeat(cell_mask.reshape(-1), 2)
        tris = tris[keep]
    mesh = _make(positions, np.zeros_like(positions), uvs, tris.reshape(-1), material)
    mesh.recompute_normals(180.0)
    return mesh


def icosphere(radius: float = 1.0, subdivisions: int = 2, material: str = "default") -> Mesh:
    t = (1.0 + math.sqrt(5.0)) / 2.0
    verts = np.array([
        [-1, t, 0], [1, t, 0], [-1, -t, 0], [1, -t, 0],
        [0, -1, t], [0, 1, t], [0, -1, -t], [0, 1, -t],
        [t, 0, -1], [t, 0, 1], [-t, 0, -1], [-t, 0, 1]], dtype=np.float64)
    faces = np.array([
        [0, 11, 5], [0, 5, 1], [0, 1, 7], [0, 7, 10], [0, 10, 11],
        [1, 5, 9], [5, 11, 4], [11, 10, 2], [10, 7, 6], [7, 1, 8],
        [3, 9, 4], [3, 4, 2], [3, 2, 6], [3, 6, 8], [3, 8, 9],
        [4, 9, 5], [2, 4, 11], [6, 2, 10], [8, 6, 7], [9, 8, 1]], dtype=np.int64)
    verts = verts / np.linalg.norm(verts, axis=1, keepdims=True)
    for _ in range(subdivisions):
        midpoints: dict[tuple[int, int], int] = {}
        new_faces = []
        verts = list(verts)

        def midpoint(a: int, b: int) -> int:
            key = (min(a, b), max(a, b))
            if key not in midpoints:
                m = (verts[a] + verts[b]) / 2.0
                m = m / np.linalg.norm(m)
                midpoints[key] = len(verts)
                verts.append(m)
            return midpoints[key]

        for f in faces:
            a, b, c = int(f[0]), int(f[1]), int(f[2])
            ab, bc, ca = midpoint(a, b), midpoint(b, c), midpoint(c, a)
            new_faces.extend([[a, ab, ca], [b, bc, ab], [c, ca, bc], [ab, bc, ca]])
        verts = np.array(verts)
        faces = np.array(new_faces, dtype=np.int64)
    positions = verts * radius
    normals = verts
    u = 0.5 + np.arctan2(verts[:, 2], verts[:, 0]) / (2.0 * math.pi)
    v = 0.5 - np.arcsin(np.clip(verts[:, 1], -1.0, 1.0)) / math.pi
    uvs = np.stack([u, v], axis=-1)
    return _make(positions, normals, uvs, faces.reshape(-1), material)


def stairs(width: float, rise: float, run: float, steps: int, uv_scale: float = 1.0,
           material: str = "default", side_walls: bool = False,
           wall_height: float = 0.0) -> Mesh:
    """Solid staircase climbing +Z, base at y=0 - always has thickness underneath."""
    parts = []
    for i in range(steps):
        y = i * rise
        depth_remaining = (steps - i) * run
        parts.append(box((width, rise, depth_remaining),
                         center=(0.0, y + rise * 0.5, i * run + depth_remaining * 0.5),
                         uv_scale=uv_scale, material=material))
    if side_walls and wall_height > 0.0:
        for sign in (-1.0, 1.0):
            for i in range(steps):
                y = i * rise
                parts.append(box((0.28, wall_height, run),
                                 center=(sign * (width * 0.5 + 0.14),
                                         y + wall_height * 0.5, i * run + run * 0.5),
                                 uv_scale=uv_scale, material=material))
    return merge(parts, material)


def arch(span: float, rise: float, thickness: float, depth: float, segments: int = 14,
         uv_scale: float = 1.0, material: str = "default") -> Mesh:
    """Semicircular arch ring in the XY plane, extruded along Z."""
    inner_r = span * 0.5
    outer_r = inner_r + thickness
    positions, normals, uvs, indices = [], [], [], []
    half_depth = depth * 0.5
    ring = []
    for i in range(segments + 1):
        angle = math.pi * i / segments
        c, s = math.cos(angle), math.sin(angle)
        ring.append(((c * inner_r, s * inner_r * (rise / inner_r)),
                     (c * outer_r, s * outer_r * (rise / inner_r))))
    for i in range(segments + 1):
        (ix, iy), (ox, oy) = ring[i]
        for z, nz in ((half_depth, 1.0), (-half_depth, -1.0)):
            base = len(positions)
            positions.extend([(ix, iy, z), (ox, oy, z)])
            normals.extend([(0, 0, nz)] * 2)
            uvs.extend([[ix * uv_scale, iy * uv_scale], [ox * uv_scale, oy * uv_scale]])
    stride = 4
    for i in range(segments):
        a = i * stride
        b = (i + 1) * stride
        indices.extend([a, a + 1, b + 1, a, b + 1, b])          # front
        indices.extend([a + 2, b + 2, b + 3, a + 2, b + 3, a + 3])  # back
    for i in range(segments):
        a = i * stride
        b = (i + 1) * stride
        indices.extend([a + 1, a + 3, b + 3, a + 1, b + 3, b + 1])  # outer
        indices.extend([a, b, b + 2, a, b + 2, a + 2])              # inner (soffit)
    mesh = _make(positions, normals, uvs, indices, material)
    mesh.recompute_normals(50.0)
    return mesh


def gable_roof(width: float, depth: float, height: float, overhang: float = 0.35,
               thickness: float = 0.18, uv_scale: float = 1.0,
               material: str = "default") -> Mesh:
    """Steep pitched roof with real slab thickness and eaves."""
    hw = width * 0.5 + overhang
    hd = depth * 0.5 + overhang
    parts = []
    slope_length = math.hypot(hw, height)
    pitch = math.atan2(height, hw)
    for sign in (-1.0, 1.0):
        slab = box((slope_length, thickness, hd * 2.0), uv_scale=uv_scale, material=material)
        slab.rotate_z(-sign * pitch)
        slab.translate(sign * hw * 0.5, height * 0.5, 0.0)
        parts.append(slab)
    # gable end walls close the roof volume so it is never an open shell
    for sign in (-1.0, 1.0):
        positions = [(-hw, 0.0, sign * hd), (hw, 0.0, sign * hd), (0.0, height, sign * hd)]
        normal = (0.0, 0.0, sign)
        tri = _make(positions, [normal] * 3,
                    [[-hw * uv_scale, 0], [hw * uv_scale, 0], [0, height * uv_scale]],
                    [0, 1, 2] if sign > 0 else [0, 2, 1], material)
        parts.append(tri)
    return merge(parts, material)
