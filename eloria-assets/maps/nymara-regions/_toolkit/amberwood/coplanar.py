"""Remove overlapping, same-facing planes while preserving surface ownership.

Room shells deliberately overlap at joints to close corners. Exporting both
faces makes those joints shimmer in the Compatibility renderer. Clip the later
face against earlier coplanar triangles, interpolating its own UVs and normals.
Walk surfaces take priority, and cutaway lids are processed separately so hiding
a roof cannot expose a hole in the visible structure. No dependency beyond NumPy.
"""
from __future__ import annotations

from collections import defaultdict
import numpy as np



def _half(poly, a, b, positive):
    """Clip a polygon (full vertex attributes) to one directed 2D half plane."""
    out = []
    def distance(v):
        return (b[0] - a[0]) * (v[1] - a[1]) - (b[1] - a[1]) * (v[0] - a[0])
    for p, q in zip(poly, poly[1:] + poly[:1]):
        dp, dq = distance(p), distance(q)
        pin = dp >= -1e-9 if positive else dp <= 1e-9
        qin = dq >= -1e-9 if positive else dq <= 1e-9
        if pin:
            out.append(p)
        if pin != qin and abs(dp - dq) > 1e-12:
            out.append(p + (q - p) * (dp / (dp - dq)))
    return out


def _subtract(poly, cut):
    # cut is CCW. The portions outside its successive edges are disjoint;
    # the remainder after all three edges is exactly the unwanted overlap.
    inside = poly
    outside = []
    for a, b in zip(cut, np.roll(cut, -1, axis=0)):
        part = _half(inside, a, b, False)
        if len(part) >= 3:
            outside.append(part)
        inside = _half(inside, a, b, True)
        if len(inside) < 3:
            break
    return outside


def trim_coplanar(group, tolerance=.012):
    """In-place trim of same-facing duplicate coverage, stable in recipe order."""
    def trim(parts):
        planes = defaultdict(list)
        for mesh in parts:
            positions, normals, uvs, colors, indices = [], [], [], [], []
            vertices = {}
            for face in mesh.indices.reshape(-1, 3):
                xyz = mesh.positions[face]
                cross = np.cross(xyz[1] - xyz[0], xyz[2] - xyz[0])
                length = np.linalg.norm(cross)
                if length < 1e-9:
                    continue
                normal = cross / length
                drop = int(np.argmax(np.abs(normal)))
                axes = [(drop + 1) % 3, (drop + 2) % 3]
                flat = xyz[:, axes]
                offset = float(np.dot(normal, xyz[0]))
                key = tuple(np.round(normal, 6))
                low, high = flat.min(axis=0), flat.max(axis=0)
                attrs = [flat, xyz, mesh.normals[face], mesh.uvs[face]]
                if mesh.colors is not None:
                    attrs.append(mesh.colors[face])
                poly = list(np.hstack(attrs))
                pieces = [poly]
                for old_offset, old_low, old_high, cut in planes[key]:
                    if abs(old_offset - offset) >= tolerance:
                        continue
                    if np.any(low >= old_high - 1e-8) or np.any(old_low >= high - 1e-8):
                        continue
                    pieces = [piece for p in pieces for piece in _subtract(p, cut)]
                    if not pieces:
                        break
                a, b = flat[1] - flat[0], flat[2] - flat[0]
                cut = flat if a[0] * b[1] - a[1] * b[0] > 0 else flat[::-1]
                planes[key].append((offset, low, high, cut))
                for piece in pieces:
                    for j in range(1, len(piece) - 1):
                        tri = np.asarray([piece[0], piece[j], piece[j + 1]])
                        if np.linalg.norm(np.cross(tri[1, 2:5] - tri[0, 2:5],
                                                   tri[2, 2:5] - tri[0, 2:5])) < 1e-8:
                            continue
                        for vertex in tri:
                            key_vertex = tuple(vertex[2:])
                            if key_vertex not in vertices:
                                vertices[key_vertex] = len(positions)
                                positions.append(vertex[2:5])
                                normals.append(vertex[5:8])
                                uvs.append(vertex[8:10])
                                if mesh.colors is not None:
                                    colors.append(vertex[10:])
                            indices.append(vertices[key_vertex])
            mesh.positions = np.asarray(positions, dtype=np.float64).reshape(-1, 3)
            mesh.normals = np.asarray(normals, dtype=np.float64).reshape(-1, 3)
            mesh.uvs = np.asarray(uvs, dtype=np.float64).reshape(-1, 2)
            mesh.indices = np.asarray(indices, dtype=np.int64)
            if mesh.colors is not None:
                mesh.colors = np.asarray(colors, dtype=np.float64).reshape(-1, mesh.colors.shape[1])
    trim(group.walk_parts + group.parts)
    trim(group.overhead_parts)
