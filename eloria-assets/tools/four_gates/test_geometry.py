#!/usr/bin/env python3
"""Geometry orientation regression tests for the Four Gates toolkit.

glTF front faces are counter-clockwise and Godot culls back faces, so geometry
wound the wrong way renders inside-out: the outward faces are culled and the
viewer looks straight through the wall at the interior of the far side. The
silhouette is unchanged, which is why it survives a casual visual review.

These tests assert the invariant directly:

  * every closed primitive has a positive signed volume (outward winding),
  * every convex closed primitive has no face whose normal points at its own
    centroid,
  * every ground surface has normals pointing +Y,
  * the authored NORMAL attribute agrees with the winding.

Run: python3 eloria-assets/tools/four_gates/test_geometry.py
"""

from __future__ import annotations

import math
import os
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import meshlib as M  # noqa: E402


def signed_volume(geo) -> float:
    p = geo.v[geo.f].astype(np.float64)
    return float(np.einsum("ij,ij->i", p[:, 0], np.cross(p[:, 1], p[:, 2])).sum() / 6.0)


def inward_faces(geo) -> int:
    p = geo.v[geo.f].astype(np.float64)
    centres = p.mean(axis=1)
    centroid = geo.v.mean(axis=0)
    n = np.cross(p[:, 1] - p[:, 0], p[:, 2] - p[:, 0])
    lengths = np.linalg.norm(n, axis=1, keepdims=True)
    lengths[lengths == 0] = 1.0
    n = n / lengths
    return int((np.einsum("ij,ij->i", n, centres - centroid) <= 0).sum())


def normals_match_winding(geo) -> float:
    """Worst-case agreement between the authored NORMAL and the face winding.

    Smooth-shaded primitives average their vertex normals across neighbouring
    faces, so an exact match is not expected; what must never happen is a
    normal pointing into the opposite hemisphere from its winding, which is the
    signature of an inside-out surface.
    """
    p = geo.v[geo.f]
    n = np.cross(p[:, 1] - p[:, 0], p[:, 2] - p[:, 0])
    lengths = np.linalg.norm(n, axis=1, keepdims=True)
    lengths[lengths == 0] = 1.0
    n = n / lengths
    per_vertex = np.stack([
        np.einsum("ij,ij->i", n, geo.n[geo.f[:, k]]) for k in range(3)], axis=1)
    return float(per_vertex.min())


CLOSED = {
    "box": lambda: M.box(4, 3, 5),
    "box_corner": lambda: M.box(4, 3, 5, origin="corner"),
    "tapered_box": lambda: M.tapered_box(4, 5, 3, 4, 6),
    "cylinder": lambda: M.cylinder(2, 5, 16),
    "cylinder_tapered": lambda: M.cylinder(2, 5, 16, top_radius=1.2),
    "cone": lambda: M.cone(2, 4, 12),
    "pyramid": lambda: M.pyramid(3, 3, 4),
    "gable_roof_x": lambda: M.gable_roof(6, 8, 3),
    "gable_roof_z": lambda: M.gable_roof(6, 8, 3, ridge_along_x=False),
    "hip_roof": lambda: M.hip_roof(6, 8, 3),
    "prism": lambda: M.prism([(0, 0), (3, 0), (3, 3), (0, 3)], 4),
    "arch_ring": lambda: M.arch_ring(4, 6, 3, 0.0, math.pi, 10),
    "revolve": lambda: M.revolve([(0, 0), (1.2, 1), (0.8, 3), (0, 4)], 12),
    "icosphere": lambda: M.icosphere(2, 2),
    "stairs": lambda: M.stairs(6, 3, 8, 10),
    "ramp": lambda: M.ramp(4, 8, 3),
    "torus_arc": lambda: M.torus_arc(4, 0.5, 0.0, math.tau, 24, 8),
}

# convex shapes additionally allow the stricter per-face centroid test
CONVEX = {"box", "box_corner", "tapered_box", "cylinder", "cylinder_tapered",
          "cone", "pyramid", "prism", "icosphere", "ramp"}

SURFACES = {
    "plane": lambda: M.plane(100, 100, 0, 4.0, 0.0, 8),
    "grid_surface": lambda: M.grid_surface(
        -50, 50, -50, 50, 8, 8, lambda X, Z: 3 * np.sin(X * 0.05)),
    "polar_surface": lambda: M.polar_surface(
        np.linspace(10, 200, 20), 48, lambda X, Z: np.full_like(X, 5.0)),
    "ring_band": lambda: M.ring_band(10, 20, 32, lambda x, z: 0.0),
    "quad_strip_z": lambda: M.quad_strip([(0, 0), (0, 50), (0, 100)], 10,
                                         lambda x, z: 0.0),
    "quad_strip_x": lambda: M.quad_strip([(0, 0), (50, 0), (100, 0)], 10,
                                         lambda x, z: 0.0),
}


def split_quads(geo, diagonal_fn) -> int:
    """Quads whose two triangles were given different surface classes.

    A quad's two triangles meet along its diagonal; two triangles from
    neighbouring quads meet along a grid line. `diagonal_fn` tells the two
    apart from the shared edge's endpoints alone, so this never has to know how
    the surface happened to order its faces. A class boundary is allowed to run
    along a grid line -- that is what a boundary between two patches of ground
    looks like -- but a boundary along a diagonal means one patch of ground was
    handed to two classes, which reads from above as a comb of slivers.
    """
    shared: dict[tuple[int, int], list[int]] = {}
    for face_index, face in enumerate(geo.f):
        for first, second in ((0, 1), (1, 2), (2, 0)):
            edge = (int(min(face[first], face[second])),
                    int(max(face[first], face[second])))
            shared.setdefault(edge, []).append(face_index)
    split = 0
    for (lo, hi), faces in shared.items():
        if len(faces) != 2:
            continue
        if not diagonal_fn(geo.v[lo], geo.v[hi]):
            continue
        if geo.m[faces[0]] != geo.m[faces[1]]:
            split += 1
    return split


def cartesian_diagonal(p, q) -> bool:
    return abs(float(p[0]) - float(q[0])) > 1e-4 and abs(float(p[2]) - float(q[2])) > 1e-4


def polar_diagonal(p, q) -> bool:
    radii = [math.hypot(float(v[0]), float(v[2])) for v in (p, q)]
    angles = [math.atan2(float(v[2]), float(v[0])) for v in (p, q)]
    turn = abs(angles[0] - angles[1]) % math.tau
    turn = min(turn, math.tau - turn)
    return abs(radii[0] - radii[1]) > 1e-4 and turn > 1e-6


# A surface class chosen per triangle rather than per quad splits a quad along
# its own diagonal wherever the ground crosses a threshold, so each of these
# uses a field that crosses one right through the middle of the sheet.
CLASSIFIED = {
    "grid_surface": (lambda: M.grid_surface(
        -50, 50, -50, 50, 9, 9, lambda X, Z: 3.0 * np.sin(X * 0.05),
        material_fn=lambda pts, nrm: (pts[:, 1] > 0.0).astype(np.int32)),
        cartesian_diagonal),
    "polar_surface": (lambda: M.polar_surface(
        np.linspace(10, 200, 21), 47, lambda X, Z: 3.0 * np.sin(X * 0.05),
        material_fn=lambda pts, nrm: (pts[:, 1] > 0.0).astype(np.int32)),
        polar_diagonal),
}


def main() -> int:
    failures = []
    print("projected UVs -- every box/cylinder face keeps two texture axes")
    for name,geo in [('box',M.box(7,4,9)),('cylinder',M.cylinder(4,3,24))]:
        uv=geo.t[geo.f]
        a,b=uv[:,1]-uv[:,0],uv[:,2]-uv[:,0]
        area=abs(a[:,0]*b[:,1]-a[:,1]*b[:,0])
        collapsed=int(np.count_nonzero(area<1e-8))
        if collapsed:failures.append(f'{name}: {collapsed} faces have collapsed UVs')
        print(f'  {name}: collapsed={collapsed}')
    print("closed primitives -- signed volume must be positive")
    for name, factory in CLOSED.items():
        geo = factory()
        volume = signed_volume(geo)
        note = ""
        if volume <= 0.0:
            failures.append(f"{name}: inside-out (signed volume {volume:.2f})")
        if name in CONVEX:
            bad = inward_faces(geo)
            note = f" inward_faces={bad}"
            if bad:
                failures.append(f"{name}: {bad} face(s) point inward")
        agree = normals_match_winding(geo)
        if agree <= 0.0:
            failures.append(
                f"{name}: NORMAL points opposite its winding (worst dot {agree:.3f})")
        print(f"  {name:18s} volume={volume:10.2f}{note}")

    print("\nground surfaces -- normals must point +Y")
    for name, factory in SURFACES.items():
        geo = factory()
        mean_y = float(geo.n[:, 1].mean())
        if mean_y < 0.9:
            failures.append(f"{name}: surface normals point away from +Y ({mean_y:.3f})")
        print(f"  {name:18s} mean normal Y={mean_y:6.3f}")

    print("\nclassified surfaces -- a quad belongs to one surface class")
    for name, (factory, diagonal_fn) in CLASSIFIED.items():
        geo = factory()
        split = split_quads(geo, diagonal_fn)
        classes = len(np.unique(geo.m))
        if classes < 2:
            failures.append(
                f"{name}: the test field produced one class, so it proves nothing")
        if split:
            failures.append(f"{name}: {split} quad(s) split across two classes")
        print(f"  {name:18s} classes={classes} split_quads={split}")

    print()
    if failures:
        for failure in failures:
            print("FAIL:", failure)
        print(f"\n{len(failures)} geometry orientation failure(s)")
        return 1
    print("PASS: all primitives are wound outward and all surfaces face +Y")
    return 0


if __name__ == "__main__":
    sys.exit(main())
