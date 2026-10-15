"""Focused geometry contract for the decorative cliff-house balcony."""
from __future__ import annotations

from collections import Counter
import hashlib
from pathlib import Path
import sys
import unittest

import numpy as np

PACKAGE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PACKAGE.parent / "_toolkit"))
import landmarks as L


LOCAL = 1.5
SEED = 20260828
VARIANTS = tuple(
    (
        variant,
        (4.4 + variant * 0.6) * LOCAL,
        (5.0 + (variant % 2) * 0.8) * LOCAL,
        2 + variant % 3,
    )
    for variant in range(4)
)
BASELINE_PREFIX_SHA256 = {
    0: "7d4fe7b43cfa68da13df0220f7288b1bcb865b012452dbc296cd3e13152304f5",
    1: "485cb91a518dc842453133586bad2873a28fe19563890a6bbe243b34154aee39",
    2: "047e3bf829ac4ba3f091b9c574c4d1f4062b289365d8e3d68e1f9c41c3ed9173",
    3: "689873d709e668d97e8007f44703b038d483736068872fbb003a351974f1e77a",
}
BASELINE_WHOLE_SHA256 = {
    0: "31a2b24b7cbef7f8ff2d0c9fc15b23d357ee0d15f9ba6d868519c08bbc671e33",
    1: "3038cc66ed195cbb8b9013db3f3625b82dbbf2501668fab347d3e4a45eea6e9d",
    2: "06f6333e867ea543c877937287660e7bbd8734bbfa87cebf9c7560b162f72f2e",
    3: "fc92cc5d46fe55e8841d8add758342ca61d6325acfe3f38dbbaa16a0e1664a8a",
}
BASELINE_BOUNDS = {
    0: ([-4.187464972240292, 0.0, -4.6000000000000005],
        [4.187464972240292, 7.3818313867353735, 4.6000000000000005]),
    1: ([-4.6343584138977825, 0.0, -5.2],
        [4.6343584138977825, 10.083183528384103, 5.2]),
    2: ([-5.081692489828823, 0.0, -4.6000000000000005],
        [5.081692489828823, 12.78423530191345, 4.6000000000000005]),
    3: ([-5.529386822751825, 0.0, -5.2],
        [5.529386822751825, 7.385067118492123, 5.2]),
}


def _mesh_digest(parts) -> str:
    digest = hashlib.sha256()
    for part in parts:
        digest.update(np.asarray(part.positions, dtype="<f8").tobytes())
        digest.update(np.asarray(part.indices, dtype="<i8").tobytes())
        digest.update(part.material.encode())
    return digest.hexdigest()


def _triangles(mesh):
    return mesh.positions[np.asarray(mesh.indices).reshape(-1, 3)]


def _signed_volume(mesh) -> float:
    tri = _triangles(mesh)
    return float(np.einsum("ij,ij->i", tri[:, 0],
                           np.cross(tri[:, 1], tri[:, 2])).sum() / 6.0)


def _is_closed(mesh) -> bool:
    counts = Counter()
    vertices = [tuple(np.round(point, 9)) for point in mesh.positions]
    for triangle in np.asarray(mesh.indices).reshape(-1, 3):
        for a, b in ((triangle[0], triangle[1]),
                     (triangle[1], triangle[2]),
                     (triangle[2], triangle[0])):
            counts[tuple(sorted((vertices[int(a)], vertices[int(b)])))] += 1
    return bool(counts) and set(counts.values()) == {2}


def _inside_open_box(points, low, high, eps=1e-8):
    points = np.asarray(points)
    low = np.asarray(low) + eps
    high = np.asarray(high) - eps
    return np.all((points > low) & (points < high), axis=1)


def _emitted_vertex_inside(mesh, solid) -> bool:
    low, high = solid.bounds()
    return bool(np.any(_inside_open_box(mesh.positions, low, high)))


def _segment_hits_open_box(a, b, low, high, eps=1e-8) -> bool:
    low = np.asarray(low) + eps
    high = np.asarray(high) - eps
    direction = np.asarray(b) - np.asarray(a)
    enter, leave = 0.0, 1.0
    for axis in range(3):
        if abs(direction[axis]) < 1e-12:
            if a[axis] <= low[axis] or a[axis] >= high[axis]:
                return False
            continue
        t0 = (low[axis] - a[axis]) / direction[axis]
        t1 = (high[axis] - a[axis]) / direction[axis]
        enter = max(enter, min(t0, t1))
        leave = min(leave, max(t0, t1))
        if enter >= leave:
            return False
    return enter < leave


def _mesh_hits_open_box(mesh, low, high) -> bool:
    if np.any(_inside_open_box(mesh.positions, low, high)):
        return True
    for triangle in _triangles(mesh):
        for a, b in ((triangle[0], triangle[1]),
                     (triangle[1], triangle[2]),
                     (triangle[2], triangle[0])):
            if _segment_hits_open_box(a, b, low, high):
                return True
    return False


def _clip_polygon(polygon, coordinate, bound, keep_above, eps=1e-9):
    if not polygon:
        return []
    result = []
    previous = polygon[-1]
    previous_inside = (previous[coordinate] >= bound - eps if keep_above
                       else previous[coordinate] <= bound + eps)
    for current in polygon:
        current_inside = (current[coordinate] >= bound - eps if keep_above
                          else current[coordinate] <= bound + eps)
        if current_inside != previous_inside:
            fraction = ((bound - previous[coordinate]) /
                        (current[coordinate] - previous[coordinate]))
            crossing = previous + fraction * (current - previous)
            result.append(crossing)
        if current_inside:
            result.append(current)
        previous, previous_inside = current, current_inside
    return result


def _polygon_area(polygon):
    if len(polygon) < 3:
        return 0.0
    points = np.asarray(polygon)
    return abs(float(np.dot(points[:, 0], np.roll(points[:, 1], -1)) -
                     np.dot(points[:, 1], np.roll(points[:, 0], -1)))) * 0.5


def _emitted_plane_contact_area(mesh, axis, value, other, eps=1e-7):
    low, high = other.bounds()
    other_axes = [candidate for candidate in range(3) if candidate != axis]
    area = 0.0
    for triangle in _triangles(mesh):
        if not np.all(np.abs(triangle[:, axis] - value) <= eps):
            continue
        polygon = [point.copy() for point in triangle[:, other_axes]]
        for coordinate in range(2):
            polygon = _clip_polygon(polygon, coordinate,
                                    low[other_axes[coordinate]], True)
            polygon = _clip_polygon(polygon, coordinate,
                                    high[other_axes[coordinate]], False)
        area += _polygon_area(polygon)
    return area


class CliffHouseBalcony(unittest.TestCase):
    def _house(self, variant, width, depth, storeys):
        return L.cliff_house(seed=SEED + 51 + variant, width=width,
                             depth=depth, storeys=storeys)

    def test_existing_house_geometry_is_bit_identical(self):
        for variant, width, depth, storeys in VARIANTS:
            with self.subTest(variant=variant):
                house = self._house(variant, width, depth, storeys)
                self.assertEqual(_mesh_digest(house.parts[:-1]),
                                 BASELINE_WHOLE_SHA256[variant])

    def test_new_sill_is_closed_outward_and_positive_volume(self):
        for variant, width, depth, storeys in VARIANTS:
            with self.subTest(variant=variant):
                sill = self._house(variant, width, depth, storeys).parts[-1]
                self.assertTrue(_is_closed(sill))
                self.assertGreater(_signed_volume(sill), 1e-6)

    def test_emitted_sill_contacts_jetty_and_original_railing(self):
        for variant, width, depth, storeys in VARIANTS:
            with self.subTest(variant=variant):
                house = self._house(variant, width, depth, storeys)
                jetty, sill = house.parts[1], house.parts[-1]
                prefix_count = next(index for index in range(3, len(house.parts))
                                    if _mesh_digest(house.parts[:index]) ==
                                    BASELINE_PREFIX_SHA256[variant])
                original_rail = house.parts[prefix_count:-1]
                jetty_low, jetty_high = jetty.bounds()
                self.assertTrue(_mesh_hits_open_box(sill, jetty_low, jetty_high))
                sill_low, sill_high = sill.bounds()
                self.assertTrue(any(_mesh_hits_open_box(part, sill_low, sill_high)
                                    for part in original_rail))
                rail_low = np.min([part.bounds()[0] for part in original_rail], axis=0)
                self.assertAlmostEqual(sill_high[1], rail_low[1] + 0.02,
                                       delta=1e-8)

    def test_new_sill_clears_emitted_windows_and_door_volume(self):
        for variant, width, depth, storeys in VARIANTS:
            with self.subTest(variant=variant):
                house = self._house(variant, width, depth, storeys)
                sill = house.parts[-1]
                windows = [part for part in house.parts[:-1]
                           if part.material in (L.BRASS, L.CRYSTAL)]
                for window in windows:
                    low, high = window.bounds()
                    self.assertFalse(_mesh_hits_open_box(sill, low, high))

                door_low = np.array([-0.8, 0.0, depth * 0.5 - 0.10])
                door_high = np.array([0.8, 2.35, depth * 0.5 + 0.45])
                self.assertFalse(_mesh_hits_open_box(sill, door_low, door_high))

    def test_bounds_are_preserved_and_no_walk_surface_is_added(self):
        for variant, width, depth, storeys in VARIANTS:
            with self.subTest(variant=variant):
                house = self._house(variant, width, depth, storeys)
                low, high = house.bounds()
                old_low, old_high = map(np.asarray, BASELINE_BOUNDS[variant])
                self.assertTrue(np.array_equal(low, old_low))
                self.assertTrue(np.array_equal(high, old_high))
                self.assertEqual(house.walk_parts, [])


if __name__ == "__main__":
    unittest.main()
