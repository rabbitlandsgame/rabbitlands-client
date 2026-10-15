"""Authoring-time geometry checks.

These run inside the builder so a malformed primitive is caught before export
rather than after a client render. The winding check in particular is what
catches faces that are invisible under back-face culling and simultaneously
transparent to the grounding raycast, because Godot's ConcavePolygonShape3D
ignores back faces.
"""
from __future__ import annotations

import numpy as np

from glb import Geometry


def winding_report(geometry: Geometry, name: str = "") -> dict:
    """Compare each triangle's geometric normal with its vertex normals."""
    positions, normals, _, indices, _ = geometry.arrays(with_colors=True)
    if len(indices) == 0:
        return {"name": name, "triangles": 0, "reversed": 0, "degenerate": 0}
    tri = indices.reshape(-1, 3).astype("int64")
    p0, p1, p2 = positions[tri[:, 0]], positions[tri[:, 1]], positions[tri[:, 2]]
    face = np.cross(p1 - p0, p2 - p0)
    area = np.linalg.norm(face, axis=1)
    degenerate = int((area < 1e-9).sum())
    valid = area >= 1e-9
    face_normal = np.zeros_like(face)
    face_normal[valid] = face[valid] / area[valid, None]
    vertex_normal = (normals[tri[:, 0]] + normals[tri[:, 1]] + normals[tri[:, 2]]) / 3.0
    length = np.linalg.norm(vertex_normal, axis=1)
    ok = length > 1e-6
    agreement = np.einsum("ij,ij->i", face_normal[ok], vertex_normal[ok] / length[ok, None])
    return {"name": name, "triangles": int(len(tri)),
            "reversed": int((agreement < -0.2).sum()), "degenerate": degenerate,
            "minAgreement": float(agreement.min()) if agreement.size else 1.0}


def volume_report(geometry: Geometry, name: str = "") -> dict:
    """Signed volume via the divergence theorem.

    For a closed solid this is positive when the surface is wound outward and
    negative when it is inside-out, which a winding check alone cannot detect
    because inside-out faces still agree with their own vertex normals.
    """
    positions, _, _, indices, _ = geometry.arrays(with_colors=True)
    if len(indices) == 0:
        return {"name": name, "volume": 0.0}
    tri = indices.reshape(-1, 3).astype("int64")
    p0, p1, p2 = (positions[tri[:, i]].astype("float64") for i in range(3))
    return {"name": name,
            "volume": float(np.einsum("ij,ij->i", p0, np.cross(p1, p2)).sum() / 6.0)}


def assert_solid(geometry: Geometry, name: str) -> dict:
    """A closed primitive must be well formed and enclose positive volume."""
    report = assert_well_formed(geometry, name)
    volume = volume_report(geometry, name)["volume"]
    if volume <= 0.0:
        raise AssertionError(
            f"{name}: signed volume {volume:.4f} is not positive, so the solid "
            "is inside-out")
    report["volume"] = volume
    return report


def assert_well_formed(geometry: Geometry, name: str, *,
                       allow_reversed: bool = False) -> dict:
    report = winding_report(geometry, name)
    if report["degenerate"]:
        raise AssertionError(f"{name}: {report['degenerate']} degenerate triangles")
    if report["reversed"] and not allow_reversed:
        raise AssertionError(
            f"{name}: {report['reversed']} of {report['triangles']} triangles are "
            "wound against their vertex normals (they would be invisible and "
            "would not stop a grounding ray)")
    positions, normals, uvs, _, _ = geometry.arrays(with_colors=True)
    if not np.isfinite(positions).all():
        raise AssertionError(f"{name}: non-finite positions")
    if not np.isfinite(uvs).all():
        raise AssertionError(f"{name}: non-finite UVs")
    lengths = np.linalg.norm(normals, axis=1)
    if lengths.size and (np.abs(lengths - 1.0).max() > 1e-3):
        raise AssertionError(f"{name}: normals are not unit length")
    return report
