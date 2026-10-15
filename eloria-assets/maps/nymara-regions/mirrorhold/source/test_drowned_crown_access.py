"""Compacted Drowned Crown decks retain one walkable annular promenade."""
from pathlib import Path
import math
import sys
import unittest

import numpy as np

HERE = Path(__file__).resolve().parent
REGIONS = HERE.parents[1]
sys.path[:0] = [str(HERE), str(REGIONS / "_toolkit"),
                str(REGIONS / "_continent")]

from amberwood import routecraft as RC
import collision_export as COLLISION
import crossing_contracts as CONTRACTS
import glb_reader as GLB
import landmarks as LANDMARKS
import landscape_plan as LANDSCAPE
import region as REGION
import ring_links as RING_LINKS


CELL = 0.5
X0, Z1 = 20.0, 105.0
WIDTH, HEIGHT = 300, 240
RING_RADIUS = 15.0 * REGION.LOCAL
INNER_RADIUS = RING_RADIUS * 0.42
OUTER_RADIUS = RING_RADIUS + 1.7


def triangles(mesh):
    return mesh.positions[mesh.indices].reshape(-1, 3, 3)


def transformed_link(stations):
    # This is the walk-surface branch of CompactLandscape.apply without a
    # terrain or full RegionBuild: transform the complete placed mesh once.
    points = np.asarray(stations, dtype=float)
    centre = (points.min(axis=0) + points.max(axis=0)) * 0.5
    centre[1] = 0.0
    group = RING_LINKS.graded_ring_link(
        next(name for name, value in REGION.LAKE_LINKS.items()
             if value is stations), points, centre,
        ring_z=REGION.ANCHORS["ring"][1], width=6.5,
        foot=-12.0, parapet=0.8)
    for part in group.all_parts:
        part.translate(*centre)
    return LANDSCAPE.PLAN.mesh(group)


def mesh_equal(left, right):
    return (left.material == right.material
            and np.array_equal(left.positions, right.positions)
            and np.array_equal(left.normals, right.normals)
            and np.array_equal(left.uvs, right.uvs)
            and np.array_equal(left.indices, right.indices))


def position_keys(parts):
    return {tuple(row) for part in parts for row in part.positions}


class DrownedCrownAccess(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        # PLAN.point consumes x,y,z.  Keep the explicit source Y so its output
        # matches Landmark_Ring's placement in populate_lake.
        rx, rz = REGION.ANCHORS["ring"]
        cls.ring_position = np.asarray(
            LANDSCAPE.PLAN.point([rx, REGION.LEVEL["quay"] - 1.0, rz]), float)
        cls.ring_center = cls.ring_position[[0, 2]]
        cls.ring = LANDMARKS.colonnade_ring(RING_RADIUS, 24, 5.8).translate(
            *cls.ring_position)
        cls.links = {name: transformed_link(stations)
                     for name, stations in REGION.LAKE_LINKS.items()}

        groups = [cls.ring, *cls.links.values()]
        walk = np.concatenate([triangles(part) for group in groups
                               for part in group.walk_parts])
        structures = []
        for group in groups:
            for part in group.parts:
                tri = triangles(part)
                structures.append((tri, COLLISION.closed_mesh(tri)))
        covered, deck = GLB.rasterise(walk, WIDTH, HEIGHT, X0, Z1, CELL,
                                      upward=0.70)
        surface = np.where(covered, deck, -100.0)
        blocked = COLLISION.structural_mask(structures, surface, X0, Z1)
        cls.walkable = covered & ~blocked
        cls.grid, _ = COLLISION.encode_heights(surface, cls.walkable)
        cls.parts = CONTRACTS.climb_parts(cls.walkable, cls.grid, climb=2)
        cls.labels = np.zeros(cls.walkable.shape, dtype=np.int32)
        for number, part in enumerate(cls.parts, 1):
            cells = np.asarray(part, dtype=int)
            cls.labels[cells[:, 0], cells[:, 1]] = number

    @classmethod
    def nearest_walkable(cls, point, radius=2.0):
        px, pz = point
        cx = (px - X0) / CELL - 0.5
        cz = (Z1 - pz) / CELL - 0.5
        rows, cols = np.nonzero(cls.walkable)
        distance = np.hypot(cols - cx, rows - cz) * CELL
        choice = int(np.argmin(distance))
        if distance[choice] > radius:
            raise AssertionError(f"no walk cell within {radius} m of {point}")
        return int(rows[choice]), int(cols[choice])

    def test_baseline_stations_placements_bounds_and_non_parapet_geometry_are_exact(self):
        expected = {
            "Sanctuary": [(156, 3.70, 80.8), (156, 4.6, 118),
                          (145, 5.2, 138), (120, 6.06, 158)],
            "City": [(156, 3.70, 39.2), (156, 3.70, 4),
                     (156, 3.70, -16)],
            "WestPier": [(135.2, 3.70, 60), (94.5, 3.70, 60)],
            "EastPier": [(176.8, 3.70, 60), (217.5, 3.70, 60)],
        }
        self.assertEqual(REGION.LAKE_LINKS, expected)
        roads = {road["id"]: road["waypoints"]
                 for road in REGION.access_waypoints(self._flat_terrain())}
        for name, stations in expected.items():
            self.assertEqual(roads["lake-" + name.lower()], stations)

            points = np.asarray(stations, dtype=float)
            centre = (points.min(axis=0) + points.max(axis=0)) * 0.5
            centre[1] = 0.0
            baseline = RC.graded_causeway(points - centre, width=6.5,
                                           foot=-12.0, parapet=0.8)
            actual = RING_LINKS.graded_ring_link(
                name, points, centre, ring_z=REGION.ANCHORS["ring"][1],
                width=6.5, foot=-12.0, parapet=0.8)
            with self.subTest(name=name):
                self.assertTrue(np.array_equal(actual.bounds()[0], baseline.bounds()[0]))
                self.assertTrue(np.array_equal(actual.bounds()[1], baseline.bounds()[1]))
                self.assertEqual(len(actual.walk_parts), len(baseline.walk_parts))
                self.assertTrue(all(mesh_equal(a, b) for a, b in
                                    zip(actual.walk_parts, baseline.walk_parts)))
                if name in ("City", "Sanctuary"):
                    pairs = list(zip(actual.parts[:3], baseline.parts[:3]))
                    pairs += list(zip(actual.parts[9:], baseline.parts[9:]))
                    self.assertTrue(all(mesh_equal(a, b) for a, b in pairs))
                    first_run_piers = max(1, math.ceil(
                        np.linalg.norm(points[1, [0, 2]] - points[0, [0, 2]]) / 9))
                    next_parapet = 3 + 6 + first_run_piers + 3
                    unchanged_next = baseline.parts[next_parapet:next_parapet + 6]
                    expected_handoff = (position_keys(baseline.parts[3:9])
                                        & position_keys(unchanged_next))
                    actual_handoff = (position_keys(actual.parts[3:9])
                                      & position_keys(unchanged_next))
                    self.assertTrue(expected_handoff)
                    self.assertEqual(actual_handoff, expected_handoff)
                else:
                    self.assertEqual(len(actual.parts), len(baseline.parts))
                    self.assertTrue(all(mesh_equal(a, b) for a, b in
                                        zip(actual.parts, baseline.parts)))

    @staticmethod
    def _flat_terrain():
        class Flat:
            @staticmethod
            def height_at(x, z):
                return 0.0
        return Flat()

    def test_city_and_sanctuary_parapets_begin_at_the_emitted_ring_join(self):
        for name in ("City", "Sanctuary"):
            points = np.asarray(REGION.LAKE_LINKS[name], dtype=float)
            centre = (points.min(axis=0) + points.max(axis=0)) * 0.5
            centre[1] = 0.0
            group = RING_LINKS.graded_ring_link(
                name, points, centre, ring_z=REGION.ANCHORS["ring"][1],
                width=6.5, foot=-12.0, parapet=0.8)
            for part in group.parts[3:9]:
                part.translate(*centre)
            emitted = LANDSCAPE.PLAN.mesh(group)
            vertices = np.concatenate(
                [part.positions for part in emitted.parts[3:9]])
            longitudinal = np.abs(vertices[:, 2] - self.ring_center[1])
            with self.subTest(name=name):
                # The parapet is laterally outside the deck edge. Its nearest
                # vertices therefore have a larger radial norm; the authored
                # join is its longitudinal start plane at the ring opening.
                self.assertAlmostEqual(float(longitudinal.min()),
                                       RING_LINKS.RING_JOIN_RADIUS, delta=1e-4)
                self.assertGreater(float(longitudinal.max()),
                                   float(longitudinal.min()))

    def test_actual_walk_and_structure_collision_keeps_all_four_arms_connected(self):
        labels = {}
        for name in ("City", "Sanctuary", "WestPier", "EastPier"):
            point = LANDSCAPE.PLAN.point(REGION.LAKE_LINKS[name][0])
            cell = self.nearest_walkable((point[0], point[2]))
            labels[name] = int(self.labels[cell])
        self.assertNotIn(0, labels.values())
        self.assertEqual(len(set(labels.values())), 1, labels)

    def test_pool_and_columns_remain_physical_obstacles(self):
        centre_cell = self.nearest_walkable(self.ring_center, radius=INNER_RADIUS + 1.0)
        cx = int(math.floor((self.ring_center[0] - X0) / CELL))
        cz = int(math.floor((Z1 - self.ring_center[1]) / CELL))
        self.assertFalse(self.walkable[cz, cx], "the central pool must stay closed")
        self.assertGreater(np.linalg.norm(np.asarray([
            X0 + (centre_cell[1] + .5) * CELL,
            Z1 - (centre_cell[0] + .5) * CELL]) - self.ring_center), INNER_RADIUS)

        # The diagonal columns remain; only the four cardinal openings omit a
        # column.  Each sampled shaft must still close at least one deck cell.
        for angle in (math.pi / 4, 3 * math.pi / 4,
                      5 * math.pi / 4, 7 * math.pi / 4):
            point = self.ring_center + RING_RADIUS * np.array(
                [math.cos(angle), math.sin(angle)])
            col = int(math.floor((point[0] - X0) / CELL))
            row = int(math.floor((Z1 - point[1]) / CELL))
            window = self.walkable[row-1:row+2, col-1:col+2]
            self.assertTrue((~window).any(), f"column at {angle} lost collision")


if __name__ == "__main__":
    unittest.main()
