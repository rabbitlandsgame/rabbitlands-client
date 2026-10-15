"""Original geometry construction toolkit for the Four Gates production map.

Everything here builds indexed triangle geometry with authored normals and UVs.
UVs are projected in *local* space (so instanced kits keep identical UVs) using a
dominant-axis planar projection scaled in metres-per-UV-unit, which keeps texel
density consistent across the whole environment without hand unwrapping.
"""

from __future__ import annotations

import math
from typing import List, Optional, Sequence

import numpy as np

TAU = math.pi * 2.0


# --------------------------------------------------------------------- geometry
class Geo:
    """Indexed triangle soup with a per-face material slot."""

    __slots__ = ("v", "n", "t", "f", "m")

    def __init__(self, v, n, t, f, m):
        self.v = np.asarray(v, dtype=np.float32).reshape(-1, 3)
        self.n = np.asarray(n, dtype=np.float32).reshape(-1, 3)
        self.t = np.asarray(t, dtype=np.float32).reshape(-1, 2)
        self.f = np.asarray(f, dtype=np.uint32).reshape(-1, 3)
        self.m = np.asarray(m, dtype=np.int32).reshape(-1)
        if self.m.size == 1 and self.f.shape[0] != 1:
            self.m = np.full(self.f.shape[0], int(self.m[0]), dtype=np.int32)

    # ------------------------------------------------------------ construction
    @staticmethod
    def empty() -> "Geo":
        return Geo(np.zeros((0, 3)), np.zeros((0, 3)), np.zeros((0, 2)),
                   np.zeros((0, 3)), np.zeros((0,)))

    @staticmethod
    def concat(parts: Sequence["Geo"]) -> "Geo":
        parts = [p for p in parts if p is not None and p.f.shape[0] > 0]
        if not parts:
            return Geo.empty()
        offsets = np.cumsum([0] + [p.v.shape[0] for p in parts[:-1]])
        return Geo(
            np.concatenate([p.v for p in parts]),
            np.concatenate([p.n for p in parts]),
            np.concatenate([p.t for p in parts]),
            np.concatenate([p.f + off for p, off in zip(parts, offsets)]),
            np.concatenate([p.m for p in parts]),
        )

    def copy(self) -> "Geo":
        return Geo(self.v.copy(), self.n.copy(), self.t.copy(), self.f.copy(), self.m.copy())

    @property
    def triangles(self) -> int:
        return int(self.f.shape[0])

    # -------------------------------------------------------------- transforms
    def transform(self, matrix: np.ndarray) -> "Geo":
        matrix = np.asarray(matrix, dtype=np.float64)
        rot = matrix[:3, :3]
        self.v = ((self.v @ rot.T) + matrix[:3, 3]).astype(np.float32)
        normal_matrix = np.linalg.inv(rot).T
        n = self.n @ normal_matrix.T
        lengths = np.linalg.norm(n, axis=1, keepdims=True)
        lengths[lengths == 0] = 1.0
        self.n = (n / lengths).astype(np.float32)
        if np.linalg.det(rot) < 0:
            self.f = self.f[:, ::-1].copy()
        return self

    def translate(self, x=0.0, y=0.0, z=0.0) -> "Geo":
        self.v = (self.v + np.array([x, y, z], dtype=np.float32)).astype(np.float32)
        return self

    def scale(self, sx=1.0, sy=None, sz=None) -> "Geo":
        sy = sx if sy is None else sy
        sz = sx if sz is None else sz
        return self.transform(np.diag([sx, sy, sz, 1.0]))

    def rotate_y(self, radians: float) -> "Geo":
        c, s = math.cos(radians), math.sin(radians)
        matrix = np.eye(4)
        matrix[0, 0], matrix[0, 2] = c, s
        matrix[2, 0], matrix[2, 2] = -s, c
        return self.transform(matrix)

    def rotate_x(self, radians: float) -> "Geo":
        c, s = math.cos(radians), math.sin(radians)
        matrix = np.eye(4)
        matrix[1, 1], matrix[1, 2] = c, -s
        matrix[2, 1], matrix[2, 2] = s, c
        return self.transform(matrix)

    def rotate_z(self, radians: float) -> "Geo":
        c, s = math.cos(radians), math.sin(radians)
        matrix = np.eye(4)
        matrix[0, 0], matrix[0, 1] = c, -s
        matrix[1, 0], matrix[1, 1] = s, c
        return self.transform(matrix)

    def set_material(self, material: int) -> "Geo":
        self.m = np.full(self.f.shape[0], int(material), dtype=np.int32)
        return self

    def bounds(self):
        if self.v.shape[0] == 0:
            return np.zeros(3), np.zeros(3)
        return self.v.min(axis=0), self.v.max(axis=0)

    # --------------------------------------------------------------------- UVs
    def project_uv(self, scale: float = 1.0, offset=(0.0, 0.0)) -> "Geo":
        """Dominant-axis planar projection in local space, metres per UV unit."""
        face_normals = self._face_normals()
        axis = np.argmax(np.abs(face_normals), axis=1)
        uv = np.zeros((self.v.shape[0], 2), dtype=np.float32)
        for face_index in range(self.f.shape[0]):
            idx = self.f[face_index]
            a = axis[face_index]
            p = self.v[idx]
            if a == 0:
                uv[idx] = np.stack([p[:, 2], p[:, 1]], axis=1) / scale
            elif a == 1:
                uv[idx] = np.stack([p[:, 0], p[:, 2]], axis=1) / scale
            else:
                uv[idx] = np.stack([p[:, 0], p[:, 1]], axis=1) / scale
        self.t = (uv + np.asarray(offset, dtype=np.float32)).astype(np.float32)
        return self

    def scale_uv(self, su: float, sv: Optional[float] = None) -> "Geo":
        sv = su if sv is None else sv
        self.t = (self.t * np.array([su, sv], dtype=np.float32)).astype(np.float32)
        return self

    def offset_uv(self, du: float, dv: float) -> "Geo":
        self.t = (self.t + np.array([du, dv], dtype=np.float32)).astype(np.float32)
        return self

    def _face_normals(self) -> np.ndarray:
        p = self.v[self.f]
        n = np.cross(p[:, 1] - p[:, 0], p[:, 2] - p[:, 0])
        lengths = np.linalg.norm(n, axis=1, keepdims=True)
        lengths[lengths == 0] = 1.0
        return n / lengths

    def drop_degenerate(self, eps: float = 1e-9) -> "Geo":
        """Remove zero-area triangles so no vertex ends up with a null normal."""
        if self.f.shape[0] == 0:
            return self
        p = self.v[self.f]
        area = np.linalg.norm(np.cross(p[:, 1] - p[:, 0], p[:, 2] - p[:, 0]), axis=1)
        keep = area > eps
        if not keep.all():
            self.f = self.f[keep]
            self.m = self.m[keep]
        return self

    def recompute_normals(self, smooth: bool = False) -> "Geo":
        self.drop_degenerate()
        if smooth:
            face_normals = self._face_normals()
            acc = np.zeros_like(self.v, dtype=np.float64)
            for k in range(3):
                np.add.at(acc, self.f[:, k], face_normals)
            lengths = np.linalg.norm(acc, axis=1, keepdims=True)
            null = lengths[:, 0] < 1e-9
            lengths[null] = 1.0
            acc[null] = np.array([0.0, 1.0, 0.0])
            self.n = (acc / lengths).astype(np.float32)
        else:
            self.explode()
        return self

    def explode(self) -> "Geo":
        """Split shared vertices so every face is flat shaded."""
        face_normals = np.repeat(self._face_normals(), 3, axis=0)
        idx = self.f.reshape(-1)
        self.v = self.v[idx]
        self.t = self.t[idx]
        self.n = face_normals.astype(np.float32)
        self.f = np.arange(idx.size, dtype=np.uint32).reshape(-1, 3)
        return self


# ------------------------------------------------------------------- utilities
def _quad_indices(a, b, c, d):
    """Two triangles for a quad whose corners are given counter-clockwise as
    seen from the *outside* of the surface.

    glTF front faces are counter-clockwise, and Godot culls back faces, so a
    quad listed clockwise renders inside-out: the outward faces are culled and
    the viewer sees the interior. Builders must therefore list corners in
    outward-CCW order; `tools/four_gates/test_geometry.py` asserts it.
    """
    return [(a, c, b), (a, d, c)]


def make(vertices, faces, material=0, uv_scale: float = 2.0,
         smooth: bool = False) -> Geo:
    v = np.asarray(vertices, dtype=np.float32).reshape(-1, 3)
    f = np.asarray(faces, dtype=np.uint32).reshape(-1, 3)
    geo = Geo(v, np.zeros_like(v), np.zeros((v.shape[0], 2)), f,
              np.full(f.shape[0], material))
    geo.recompute_normals(smooth)
    # UV projection requires separate corners at changes of projection axis.
    # Projecting the shared box/cylinder vertices first lets the last face
    # overwrite all earlier axes, collapsing top and front texture triangles.
    if smooth:
        saved_normals = geo.n[geo.f.reshape(-1)].copy()
        geo.explode()
        geo.n = saved_normals
    geo.project_uv(uv_scale)
    return geo


# ---------------------------------------------------------------- primitives
def box(sx: float, sy: float, sz: float, material: int = 0, uv_scale: float = 2.0,
        origin: str = "center") -> Geo:
    hx, hz = sx * 0.5, sz * 0.5
    y0, y1 = (-sy * 0.5, sy * 0.5) if origin == "center" else (0.0, sy)
    v = [(-hx, y0, -hz), (hx, y0, -hz), (hx, y0, hz), (-hx, y0, hz),
         (-hx, y1, -hz), (hx, y1, -hz), (hx, y1, hz), (-hx, y1, hz)]
    f = []
    f += _quad_indices(4, 5, 6, 7)          # top
    f += _quad_indices(3, 2, 1, 0)          # bottom
    f += _quad_indices(0, 1, 5, 4)          # -Z
    f += _quad_indices(2, 3, 7, 6)          # +Z
    f += _quad_indices(1, 2, 6, 5)          # +X
    f += _quad_indices(3, 0, 4, 7)          # -X
    return make(v, f, material, uv_scale)


def tapered_box(sx0, sz0, sx1, sz1, sy, material=0, uv_scale=2.0,
                shear_x=0.0, shear_z=0.0) -> Geo:
    """Box with independent bottom and top footprints -- battered stone walls."""
    b, t = 0.5, 0.5
    v = [(-sx0 * b, 0, -sz0 * b), (sx0 * b, 0, -sz0 * b),
         (sx0 * b, 0, sz0 * b), (-sx0 * b, 0, sz0 * b),
         (-sx1 * t + shear_x, sy, -sz1 * t + shear_z),
         (sx1 * t + shear_x, sy, -sz1 * t + shear_z),
         (sx1 * t + shear_x, sy, sz1 * t + shear_z),
         (-sx1 * t + shear_x, sy, sz1 * t + shear_z)]
    f = []
    f += _quad_indices(4, 5, 6, 7)
    f += _quad_indices(3, 2, 1, 0)
    f += _quad_indices(0, 1, 5, 4)
    f += _quad_indices(2, 3, 7, 6)
    f += _quad_indices(1, 2, 6, 5)
    f += _quad_indices(3, 0, 4, 7)
    return make(v, f, material, uv_scale)


def cylinder(radius: float, height: float, sides: int = 16, material: int = 0,
             uv_scale: float = 2.0, cap_top: bool = True, cap_bottom: bool = True,
             top_radius: Optional[float] = None, smooth: bool = True,
             start_angle: float = 0.0, sweep: float = TAU) -> Geo:
    top_radius = radius if top_radius is None else top_radius
    closed = abs(sweep - TAU) < 1e-6
    count = sides if closed else sides + 1
    angles = start_angle + np.linspace(0.0, sweep, count, endpoint=not closed)
    cos, sin = np.cos(angles), np.sin(angles)
    bottom = np.stack([cos * radius, np.zeros_like(cos), sin * radius], axis=1)
    top = np.stack([cos * top_radius, np.full_like(cos, height), sin * top_radius], axis=1)
    v = np.concatenate([bottom, top])
    f = []
    limit = count if closed else count - 1
    for i in range(limit):
        j = (i + 1) % count
        f += _quad_indices(i, j, count + j, count + i)
    v = list(map(tuple, v))
    if cap_bottom:
        centre = len(v)
        v.append((0.0, 0.0, 0.0))
        for i in range(limit):
            j = (i + 1) % count
            f.append((centre, i, j))          # faces -Y
    if cap_top:
        centre = len(v)
        v.append((0.0, height, 0.0))
        for i in range(limit):
            j = (i + 1) % count
            f.append((centre, count + j, count + i))    # faces +Y
    geo = Geo(np.asarray(v, dtype=np.float32), np.zeros((len(v), 3)),
              np.zeros((len(v), 2)), np.asarray(f, dtype=np.uint32),
              np.full(len(f), material))
    # cylindrical UV keeps brickwork running around towers correctly
    p = geo.v
    theta = np.arctan2(p[:, 2], p[:, 0])
    circumference = max(radius, top_radius) * TAU
    u = (theta / TAU) * circumference / uv_scale
    geo.t = np.stack([u, p[:, 1] / uv_scale], axis=1).astype(np.float32)
    geo.recompute_normals(smooth)
    # Caps require planar UVs; cylindrical V is constant there. Split corners
    # before assigning cap UVs so side brickwork keeps its cylindrical wrap.
    saved_normals = geo.n[geo.f.reshape(-1)].copy()
    geo.explode()
    geo.n = saved_normals
    cap_faces = np.abs(geo._face_normals()[:, 1]) > .999
    cap_vertices = geo.f[cap_faces].reshape(-1)
    geo.t[cap_vertices] = geo.v[cap_vertices][:, [0, 2]] / uv_scale
    uv = geo.t[geo.f]
    seam = (~cap_faces) & (np.ptp(uv[:, :, 0], axis=1) > circumference / uv_scale * .5)
    for face in geo.f[seam]:
        negative = face[geo.t[face, 0] < 0]
        geo.t[negative, 0] += circumference / uv_scale
    return geo


def cone(radius: float, height: float, sides: int = 12, material: int = 0,
         uv_scale: float = 2.0, smooth: bool = False) -> Geo:
    return cylinder(radius, height, sides, material, uv_scale, cap_top=False,
                    top_radius=0.0001, smooth=smooth)


def pyramid(sx: float, sz: float, height: float, material: int = 0,
            uv_scale: float = 2.0, apex_offset=(0.0, 0.0)) -> Geo:
    hx, hz = sx * 0.5, sz * 0.5
    v = [(-hx, 0, -hz), (hx, 0, -hz), (hx, 0, hz), (-hx, 0, hz),
         (apex_offset[0], height, apex_offset[1])]
    f = [(0, 4, 1), (1, 4, 2), (2, 4, 3), (3, 4, 0), (0, 2, 3), (0, 1, 2)]
    return make(v, f, material, uv_scale)


def gable_roof(sx: float, sz: float, height: float, overhang: float = 0.35,
               material: int = 0, uv_scale: float = 2.0, ridge_along_x: bool = True) -> Geo:
    hx, hz = sx * 0.5 + overhang, sz * 0.5 + overhang
    if ridge_along_x:
        v = [(-hx, 0, -hz), (hx, 0, -hz), (hx, 0, hz), (-hx, 0, hz),
             (-hx, height, 0.0), (hx, height, 0.0)]
        f = [(0, 5, 1), (0, 4, 5), (2, 4, 3), (2, 5, 4),
             (0, 3, 4), (1, 5, 2), (0, 2, 3), (0, 1, 2)]
    else:
        v = [(-hx, 0, -hz), (hx, 0, -hz), (hx, 0, hz), (-hx, 0, hz),
             (0.0, height, -hz), (0.0, height, hz)]
        f = [(1, 5, 2), (1, 4, 5), (3, 4, 0), (3, 5, 4),
             (0, 4, 1), (2, 5, 3), (0, 2, 3), (0, 1, 2)]
    return make(v, f, material, uv_scale)


def hip_roof(sx: float, sz: float, height: float, ridge: float = 0.45,
             overhang: float = 0.3, material: int = 0, uv_scale: float = 2.0) -> Geo:
    hx, hz = sx * 0.5 + overhang, sz * 0.5 + overhang
    rx = hx * ridge
    v = [(-hx, 0, -hz), (hx, 0, -hz), (hx, 0, hz), (-hx, 0, hz),
         (-rx, height, 0.0), (rx, height, 0.0)]
    f = [(0, 5, 1), (0, 4, 5), (2, 4, 3), (2, 5, 4),
         (1, 5, 2), (3, 4, 0), (0, 2, 3), (0, 1, 2)]
    return make(v, f, material, uv_scale)


def prism(polygon: Sequence[Sequence[float]], height: float, material: int = 0,
          uv_scale: float = 2.0, cap: bool = True, base_y: float = 0.0) -> Geo:
    """Extrude a convex or star-shaped 2D polygon (x,z) upward."""
    poly = np.asarray(polygon, dtype=np.float64)
    n = poly.shape[0]
    bottom = np.stack([poly[:, 0], np.full(n, base_y), poly[:, 1]], axis=1)
    top = np.stack([poly[:, 0], np.full(n, base_y + height), poly[:, 1]], axis=1)
    v = np.concatenate([bottom, top])
    f = []
    for i in range(n):
        j = (i + 1) % n
        f += _quad_indices(i, j, n + j, n + i)
    v = list(map(tuple, v))
    if cap:
        centroid = poly.mean(axis=0)
        top_c = len(v)
        v.append((centroid[0], base_y + height, centroid[1]))
        bottom_c = len(v)
        v.append((centroid[0], base_y, centroid[1]))
        for i in range(n):
            j = (i + 1) % n
            f.append((top_c, n + j, n + i))    # faces +Y
            f.append((bottom_c, i, j))         # faces -Y
    return make(v, f, material, uv_scale)


def arch_ring(inner: float, outer: float, depth: float, start: float, sweep: float,
              segments: int = 12, material: int = 0, uv_scale: float = 2.0) -> Geo:
    """Extruded annulus sector in the XY plane, extruded along Z -- gate arches."""
    angles = start + np.linspace(0.0, sweep, segments + 1)
    cos, sin = np.cos(angles), np.sin(angles)
    hz = depth * 0.5
    rings = []
    for radius in (inner, outer):
        for z in (-hz, hz):
            rings.append(np.stack([cos * radius, sin * radius, np.full_like(cos, z)], axis=1))
    inner_back, inner_front, outer_back, outer_front = rings
    v = np.concatenate([inner_back, inner_front, outer_back, outer_front])
    count = segments + 1
    ib, if_, ob, of = 0, count, 2 * count, 3 * count
    f = []
    for i in range(segments):
        j = i + 1
        f += _quad_indices(ib + i, ib + j, if_ + j, if_ + i)       # intrados
        f += _quad_indices(of + i, of + j, ob + j, ob + i)         # extrados
        f += _quad_indices(if_ + i, of + i, of + j, if_ + j)       # front face
        f += _quad_indices(ib + j, ob + j, ob + i, ib + i)         # back face
    f += _quad_indices(ob, of, if_, ib)
    f += _quad_indices(ob + segments, ib + segments, if_ + segments, of + segments)
    return make(v, f, material, uv_scale)


def torus_arc(radius: float, thickness: float, start: float, sweep: float,
              segments: int = 24, sides: int = 8, material: int = 0,
              uv_scale: float = 1.0) -> Geo:
    angles = start + np.linspace(0.0, sweep, segments + 1)
    ring = np.linspace(0.0, TAU, sides, endpoint=False)
    verts = []
    for a in angles:
        cx, cz = math.cos(a) * radius, math.sin(a) * radius
        tx, tz = -math.sin(a), math.cos(a)
        for r in ring:
            nx, nz = math.cos(a) * math.cos(r), math.sin(a) * math.cos(r)
            verts.append((cx + nx * thickness, math.sin(r) * thickness, cz + nz * thickness))
    f = []
    for i in range(segments):
        for k in range(sides):
            k2 = (k + 1) % sides
            a = i * sides + k
            b = i * sides + k2
            c = (i + 1) * sides + k2
            d = (i + 1) * sides + k
            f += _quad_indices(d, c, b, a)
    geo = make(verts, f, material, uv_scale, smooth=True)
    return geo


def stairs(width: float, total_rise: float, total_run: float, steps: int,
           material: int = 0, uv_scale: float = 1.5, solid: bool = True) -> Geo:
    """Solid flight of steps: each tread is carried down to the base so the
    flight has no open sides and no gaps under the nosing."""
    parts = []
    rise = total_rise / steps
    run = total_run / steps
    for i in range(steps):
        height = (i + 1) * rise if solid else rise
        base = 0.0 if solid else i * rise
        tread = box(width, height, run, material, uv_scale, origin="corner")
        tread.translate(0.0, base, -total_run * 0.5 + run * (i + 0.5))
        parts.append(tread)
    return Geo.concat(parts)


def ramp(width: float, length: float, rise: float, material: int = 0,
         uv_scale: float = 2.0, thickness: float = 0.6) -> Geo:
    hw, hl = width * 0.5, length * 0.5
    v = [(-hw, -thickness, -hl), (hw, -thickness, -hl), (hw, 0.0, -hl), (-hw, 0.0, -hl),
         (-hw, rise - thickness, hl), (hw, rise - thickness, hl),
         (hw, rise, hl), (-hw, rise, hl)]
    f = []
    f += _quad_indices(3, 2, 6, 7)
    f += _quad_indices(0, 4, 5, 1)
    f += _quad_indices(0, 1, 2, 3)
    f += _quad_indices(5, 4, 7, 6)
    f += _quad_indices(1, 5, 6, 2)
    f += _quad_indices(4, 0, 3, 7)
    return make(v, f, material, uv_scale)


def revolve(profile: Sequence[Sequence[float]], sides: int = 16, material: int = 0,
            uv_scale: float = 2.0, smooth: bool = True, sweep: float = TAU) -> Geo:
    """Lathe a (radius, height) profile about the Y axis."""
    profile = np.asarray(profile, dtype=np.float64)
    closed = abs(sweep - TAU) < 1e-6
    count = sides if closed else sides + 1
    angles = np.linspace(0.0, sweep, count, endpoint=not closed)
    verts = []
    for a in angles:
        c, s = math.cos(a), math.sin(a)
        for radius, height in profile:
            verts.append((c * radius, height, s * radius))
    rows = profile.shape[0]
    f = []
    limit = count if closed else count - 1
    for i in range(limit):
        j = (i + 1) % count
        for k in range(rows - 1):
            a = i * rows + k
            b = j * rows + k
            f += _quad_indices(a, b, b + 1, a + 1)
    geo = Geo(np.asarray(verts, dtype=np.float32), np.zeros((len(verts), 3)),
              np.zeros((len(verts), 2)), np.asarray(f, dtype=np.uint32),
              np.full(len(f), material))
    p = geo.v
    theta = np.arctan2(p[:, 2], p[:, 0])
    radius = np.maximum(np.hypot(p[:, 0], p[:, 2]), 1e-4)
    geo.t = np.stack([(theta / TAU) * radius * TAU / uv_scale, p[:, 1] / uv_scale],
                     axis=1).astype(np.float32)
    geo.recompute_normals(smooth)
    return geo


def grid_surface(x0, x1, z0, z1, nx, nz, height_fn, material_fn=None,
                 material: int = 0, uv_scale: float = 4.0, smooth: bool = True) -> Geo:
    xs = np.linspace(x0, x1, nx + 1)
    zs = np.linspace(z0, z1, nz + 1)
    gx, gz = np.meshgrid(xs, zs, indexing="ij")
    gy = height_fn(gx, gz)
    v = np.stack([gx.ravel(), gy.ravel(), gz.ravel()], axis=1)
    idx = np.arange((nx + 1) * (nz + 1)).reshape(nx + 1, nz + 1)
    a = idx[:-1, :-1].ravel()
    b = idx[1:, :-1].ravel()
    c = idx[1:, 1:].ravel()
    d = idx[:-1, 1:].ravel()
    # wound so the surface normal points +Y for an upward-facing height field
    f = np.concatenate([np.stack([a, c, b], axis=1), np.stack([a, d, c], axis=1)])
    if material_fn is not None:
        # One class per quad, as in polar_surface and for the same reason: a
        # quad's two triangles are two different planes, so asking each of them
        # on its own puts a class edge along the quad's own diagonal wherever
        # the ground is near a threshold. Here the two triangles of a quad are
        # a fixed stride apart rather than adjacent - every first triangle is
        # emitted before any second one - so the pairing is by that stride.
        quads = a.shape[0]
        centre = v[f].mean(axis=1).reshape(2, quads, 3).mean(axis=0)
        normal = _face_normals_for(v, f).reshape(2, quads, 3).mean(axis=0)
        lengths = np.linalg.norm(normal, axis=1, keepdims=True)
        lengths[lengths == 0.0] = 1.0
        chosen = np.asarray(material_fn(centre, normal / lengths))
        m = np.tile(chosen, 2)
    else:
        m = np.full(f.shape[0], material)
    geo = Geo(v, np.zeros_like(v), np.zeros((v.shape[0], 2)), f, m)
    geo.t = (np.stack([v[:, 0], v[:, 2]], axis=1) / uv_scale).astype(np.float32)
    geo.recompute_normals(smooth)
    return geo


def _face_normals_for(v: np.ndarray, f: np.ndarray) -> np.ndarray:
    p = v[f]
    n = np.cross(p[:, 1] - p[:, 0], p[:, 2] - p[:, 0])
    lengths = np.linalg.norm(n, axis=1, keepdims=True)
    lengths[lengths == 0] = 1.0
    return n / lengths


def polar_surface(radii: np.ndarray, sides: int, height_fn, material_fn=None,
                  material: int = 0, uv_scale: float = 4.0, smooth: bool = True,
                  jitter: float = 0.0, seed: int = 7) -> Geo:
    """Concentric radial mesh -- ideal for a circular city plateau."""
    rng = np.random.default_rng(seed)
    angles = np.linspace(0.0, TAU, sides, endpoint=False)
    rr, aa = np.meshgrid(radii, angles, indexing="ij")
    if jitter > 0.0:
        rr = rr + rng.normal(0.0, jitter, rr.shape) * (rr / max(radii[-1], 1.0))
    gx = np.cos(aa) * rr
    gz = np.sin(aa) * rr
    gy = height_fn(gx, gz)
    v = np.stack([gx.ravel(), gy.ravel(), gz.ravel()], axis=1)
    rows = len(radii)
    idx = np.arange(rows * sides).reshape(rows, sides)
    f = []
    for i in range(rows - 1):
        a = idx[i]
        b = idx[i + 1]
        an = np.roll(a, -1)
        bn = np.roll(b, -1)
        f.append(np.stack([a, bn, b], axis=1))
        f.append(np.stack([a, an, bn], axis=1))
    f = np.concatenate(f)
    if material_fn is not None:
        # One class per quad, not one per triangle. A quad's two triangles are
        # two different planes and their centroids sit a radial step apart, so
        # asking each of them on its own puts a class edge along the quad's own
        # diagonal wherever the ground is near a threshold. On the Four Gates
        # outer rim, where the slope hovers either side of the rock cut-off for
        # a couple of hundred metres, nine per cent of quads came back split,
        # and the rock band's edge read from directly above -- which is what the
        # map and minimap cameras are -- as a comb of interleaved slivers rather
        # than a shoreline. It looks like z-fighting and is not: each pixel is
        # drawn once, by whichever half of the quad owns it. A patch of ground
        # belongs to one surface class; how the mesh happened to cut it into
        # triangles is not the ground's business.
        quads = (rows - 1, 2, sides)
        centre = v[f].mean(axis=1).reshape(*quads, 3).mean(axis=1)
        normal = _face_normals_for(v, f).reshape(*quads, 3).mean(axis=1)
        lengths = np.linalg.norm(normal, axis=2, keepdims=True)
        lengths[lengths == 0.0] = 1.0
        chosen = material_fn(centre.reshape(-1, 3),
                             (normal / lengths).reshape(-1, 3))
        m = np.repeat(np.asarray(chosen).reshape(rows - 1, 1, sides), 2,
                      axis=1).ravel()
    else:
        m = np.full(f.shape[0], material)
    geo = Geo(v, np.zeros_like(v), np.zeros((v.shape[0], 2)), f, m)
    geo.t = (np.stack([v[:, 0], v[:, 2]], axis=1) / uv_scale).astype(np.float32)
    geo.recompute_normals(smooth)
    return geo


def ring_band(inner: float, outer: float, sides: int, y_fn, material: int = 0,
              uv_scale: float = 4.0, start: float = 0.0, sweep: float = TAU,
              smooth: bool = True) -> Geo:
    closed = abs(sweep - TAU) < 1e-6
    count = sides if closed else sides + 1
    angles = start + np.linspace(0.0, sweep, count, endpoint=not closed)
    verts = []
    for a in angles:
        for radius in (inner, outer):
            x, z = math.cos(a) * radius, math.sin(a) * radius
            verts.append((x, y_fn(x, z), z))
    f = []
    limit = count if closed else count - 1
    for i in range(limit):
        j = (i + 1) % count
        a0, a1 = i * 2, i * 2 + 1
        b0, b1 = j * 2, j * 2 + 1
        f += _quad_indices(a1, b1, b0, a0)
    geo = make(verts, f, material, uv_scale, smooth=smooth)
    return geo


def icosphere(radius: float, subdivisions: int = 1, material: int = 0,
              uv_scale: float = 2.0, smooth: bool = True) -> Geo:
    t = (1.0 + math.sqrt(5.0)) / 2.0
    verts = [(-1, t, 0), (1, t, 0), (-1, -t, 0), (1, -t, 0),
             (0, -1, t), (0, 1, t), (0, -1, -t), (0, 1, -t),
             (t, 0, -1), (t, 0, 1), (-t, 0, -1), (-t, 0, 1)]
    faces = [(0, 11, 5), (0, 5, 1), (0, 1, 7), (0, 7, 10), (0, 10, 11),
             (1, 5, 9), (5, 11, 4), (11, 10, 2), (10, 7, 6), (7, 1, 8),
             (3, 9, 4), (3, 4, 2), (3, 2, 6), (3, 6, 8), (3, 8, 9),
             (4, 9, 5), (2, 4, 11), (6, 2, 10), (8, 6, 7), (9, 8, 1)]
    verts = [tuple(np.array(v) / np.linalg.norm(v)) for v in verts]
    for _ in range(subdivisions):
        cache = {}
        new_faces = []

        def midpoint(a, b):
            key = (min(a, b), max(a, b))
            if key not in cache:
                p = (np.array(verts[a]) + np.array(verts[b])) / 2.0
                verts.append(tuple(p / np.linalg.norm(p)))
                cache[key] = len(verts) - 1
            return cache[key]

        for a, b, c in faces:
            ab, bc, ca = midpoint(a, b), midpoint(b, c), midpoint(c, a)
            new_faces += [(a, ab, ca), (b, bc, ab), (c, ca, bc), (ab, bc, ca)]
        faces = new_faces
    v = np.asarray(verts, dtype=np.float32) * radius
    return make(v, faces, material, uv_scale, smooth=smooth)


def plane(sx: float, sz: float, material: int = 0, uv_scale: float = 4.0,
          y: float = 0.0, subdivisions: int = 1) -> Geo:
    return grid_surface(-sx * 0.5, sx * 0.5, -sz * 0.5, sz * 0.5,
                        subdivisions, subdivisions,
                        lambda X, Z: np.full_like(X, y), material=material,
                        uv_scale=uv_scale)


def quad_strip(points: Sequence[Sequence[float]], width: float, y_fn,
               material: int = 0, uv_scale: float = 4.0, lift: float = 0.0) -> Geo:
    """Flat ribbon following a polyline in XZ -- roads, paths, channels."""
    pts = np.asarray(points, dtype=np.float64)
    verts = []
    for i in range(len(pts)):
        if i == 0:
            direction = pts[1] - pts[0]
        elif i == len(pts) - 1:
            direction = pts[-1] - pts[-2]
        else:
            direction = pts[i + 1] - pts[i - 1]
        direction = direction / max(np.linalg.norm(direction), 1e-6)
        normal = np.array([-direction[1], direction[0]])
        for side in (-1.0, 1.0):
            p = pts[i] + normal * side * width * 0.5
            verts.append((p[0], y_fn(p[0], p[1]) + lift, p[1]))
    f = []
    for i in range(len(pts) - 1):
        a0, a1 = i * 2, i * 2 + 1
        b0, b1 = (i + 1) * 2, (i + 1) * 2 + 1
        f += _quad_indices(b0, b1, a1, a0)
    return make(verts, f, material, uv_scale, smooth=True)


def tangents_for(positions: np.ndarray, normals: np.ndarray, uvs: np.ndarray,
                 indices: np.ndarray) -> np.ndarray:
    """Per-vertex Mikk-style tangents (averaged, Gram-Schmidt orthogonalised)."""
    tan = np.zeros((positions.shape[0], 3), dtype=np.float64)
    bit = np.zeros((positions.shape[0], 3), dtype=np.float64)
    p = positions[indices]
    t = uvs[indices]
    e1 = p[:, 1] - p[:, 0]
    e2 = p[:, 2] - p[:, 0]
    du1 = t[:, 1] - t[:, 0]
    du2 = t[:, 2] - t[:, 0]
    denom = du1[:, 0] * du2[:, 1] - du2[:, 0] * du1[:, 1]
    r = np.where(np.abs(denom) < 1e-12, 0.0, 1.0 / np.where(denom == 0, 1.0, denom))
    sdir = (e1 * du2[:, 1:2] - e2 * du1[:, 1:2]) * r[:, None]
    tdir = (e2 * du1[:, 0:1] - e1 * du2[:, 0:1]) * r[:, None]
    for k in range(3):
        np.add.at(tan, indices[:, k], sdir)
        np.add.at(bit, indices[:, k], tdir)
    n = normals.astype(np.float64)
    projected = tan - n * np.einsum("ij,ij->i", n, tan)[:, None]
    lengths = np.linalg.norm(projected, axis=1, keepdims=True)
    fallback = np.tile(np.array([1.0, 0.0, 0.0]), (positions.shape[0], 1))
    alt = np.tile(np.array([0.0, 0.0, 1.0]), (positions.shape[0], 1))
    degenerate = (lengths[:, 0] < 1e-8)
    if degenerate.any():
        choice = np.where(np.abs(n[:, 0:1]) > 0.9, alt, fallback)
        projected[degenerate] = choice[degenerate]
        projected[degenerate] -= n[degenerate] * np.einsum(
            "ij,ij->i", n[degenerate], projected[degenerate])[:, None]
        lengths = np.linalg.norm(projected, axis=1, keepdims=True)
    lengths[lengths < 1e-12] = 1.0
    projected = projected / lengths
    handed = np.sign(np.einsum("ij,ij->i", np.cross(n, projected), bit))
    handed[handed == 0] = 1.0
    return np.concatenate([projected, handed[:, None]], axis=1).astype(np.float32)
