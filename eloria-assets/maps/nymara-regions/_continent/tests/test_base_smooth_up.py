"""The base ground's smoothed up component (terrain_export.base_smooth_up), carried in its vertex alpha."""
from __future__ import annotations

from pathlib import Path
import sys

import numpy as np
import pytest

HERE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(HERE))
import terrain_export as T


def lattice(height, cell=2.0):
    """Vertices and triangles of a height grid (rows z, columns x), split as the exporter splits its cells."""
    nz, nx = height.shape
    gx, gz = np.meshgrid(np.arange(nx) * cell, np.arange(nz) * cell)
    positions = np.stack([gx, height, gz], axis=-1).reshape(-1, 3)
    row, col = np.nonzero(np.ones((nz - 1, nx - 1), bool))
    a = row * nx + col
    tri = np.stack((a, a + nx, a + 1, a + 1, a + nx, a + nx + 1), axis=1).reshape(-1, 3)
    return positions, tri


def test_a_plane_keeps_its_own_normal():
    x = np.arange(8) * 2.0
    height = np.tile(x * 0.5, (8, 1))
    positions, tri = lattice(height)
    up = T.base_smooth_up(positions, tri)
    assert up == pytest.approx(np.full(len(up), 1 / np.sqrt(1.25)), abs=1e-9)


def test_one_steep_facet_in_level_grass_stays_level_but_a_cliff_does_not():
    # A single raised vertex: its facets are steep, its neighbours level.
    height = np.zeros((9, 9))
    height[4, 4] = 2.4
    positions, tri = lattice(height)
    n = np.cross(positions[tri[:, 1]] - positions[tri[:, 0]], positions[tri[:, 2]] - positions[tri[:, 0]])
    flat = np.abs(n[:, 1]) / np.linalg.norm(n, axis=1)
    assert flat.min() < 0.7                          # its facets are rock-steep on their own
    up = T.base_smooth_up(positions, tri)
    assert up.min() > 0.8                            # in context it is a bump in the grass
    # A 60 degree wall across the whole grid: steep in context too.
    wall = np.tile(np.arange(9) * 2.0 * np.tan(np.radians(60)), (9, 1)).T
    positions, tri = lattice(wall)
    up = T.base_smooth_up(positions, tri)
    assert np.median(up) == pytest.approx(0.5, abs=1e-6)


def test_it_is_one_value_per_vertex_so_facets_agree_at_their_edges():
    rng = np.random.default_rng(3)
    positions, tri = lattice(rng.normal(0, 1.5, (10, 10)))
    up = T.base_smooth_up(positions, tri)
    assert up.shape == (len(positions),)
    assert np.all((up >= 0) & (up <= 1))
    # Corners shared by two triangles read the same per-vertex value.
    corner = up[tri]
    assert corner.shape == tri.shape


def test_the_byte_alpha_never_reads_as_none_carried():
    assert round(T.BASE_SMOOTH_UP_MAX * 255) == 254
    level = np.minimum(1.0, T.BASE_SMOOTH_UP_MAX)
    assert round(level * 255) < 255


def test_the_base_ground_carries_it_in_its_vertex_alpha():
    from types import SimpleNamespace
    import authoring as A
    from amberwood import gltf as G

    class Snapshot:
        translation = np.array([1.3, 0., 2.7])
        terrain_width = terrain_height = 4

        @staticmethod
        def base_colors():
            return np.arange(4 * 4 * 4, dtype=np.uint8).reshape(4, 4, 4)
        document = {"terrain": {"origin": [-1.3, -2.7], "cellMetres": 2., "previewUvMetresInverse": .24,
                                "baseSurface": {"preset": "Desert", "rotationDegrees": 0}},
                    "groundRegions": [], "paths": []}
    x = np.arange(0., 8., 2.)
    gx, gz = np.meshgrid(x, x)
    height = np.where(gx >= 4., 3.5, 0.)   # a 60 degree step across the middle column of cells
    world = SimpleNamespace(authoring_snapshot=Snapshot(), ids=[A.SUNMANE], owner=np.zeros(gx.shape, int),
                            gx=gx, gz=gz, height=height, x=x, z=x, x0=0., z0=0.)
    world.owner_at = lambda x, z: np.zeros(np.broadcast_arrays(x, z)[0].shape, dtype=int)
    overlays = T.authored_overlays(world, G.GltfBuilder("test"))
    base = next(item["mesh"] for item in overlays if item["name"] == "AuthoredGround_SunmaneBase")
    alpha = base.colors[:, 3]
    # The RGB stays the authored colour; the alpha is the smoothed up component of each lattice vertex.
    assert np.all(alpha <= T.BASE_SMOOTH_UP_MAX)
    positions = np.stack([gx, height + .006, gz], axis=-1).reshape(-1, 3)
    row, col = np.nonzero(np.ones((3, 3), bool))
    a = row * 4 + col
    tri = np.stack((a, a + 4, a + 1, a + 1, a + 4, a + 4 + 1), axis=1).reshape(-1, 3)
    expected = np.minimum(T.base_smooth_up(positions, tri), T.BASE_SMOOTH_UP_MAX)
    np.testing.assert_allclose(alpha, expected[tri].ravel())
    # Facets on the step and the level ground beside it meet with one value at their shared vertices.
    by_vertex = {}
    for p, v in zip(np.round(base.positions[:, [0, 2]], 6).tolist(), alpha):
        by_vertex.setdefault(tuple(p), set()).add(round(float(v), 9))
    assert all(len(values) == 1 for values in by_vertex.values())
    # One 60 degree strip between level ground is a bank in context: its edge vertices read about 0.8,
    # the ground away from it nearly level.
    assert alpha.min() < 0.85 < 0.95 < alpha.max()


def test_a_territory_published_alone_smooths_over_its_whole_field():
    # continent-v2 publishes one territory at a time (owner -1 outside its window): the vertices on its border
    # take the same value as its neighbour's, which sees the same field from the other side.
    from types import SimpleNamespace
    import authoring as A
    from amberwood import gltf as G

    class Snapshot:
        translation = np.array([0., 0., 0.])
        terrain_width = terrain_height = 6

        @staticmethod
        def base_colors():
            return np.full((6, 6, 4), 200, dtype=np.uint8)
        document = {"terrain": {"origin": [0., 0.], "cellMetres": 2., "previewUvMetresInverse": .24,
                                "baseSurface": {"preset": "Desert", "rotationDegrees": 0}},
                    "groundRegions": [], "paths": []}
    x = np.arange(0., 12., 2.)
    gx, gz = np.meshgrid(x, x)
    height = np.where(gx >= 6., (gx - 4.) * 1.7, 0.)
    alphas = {}
    for side, owner in (("west", np.where(gx < 6., 0, -1)), ("east", np.where(gx >= 6., 0, -1))):
        world = SimpleNamespace(authoring_snapshot=Snapshot(), ids=[A.SUNMANE], owner=owner,
                                gx=gx, gz=gz, height=height, x=x, z=x, x0=0., z0=0.)
        world.owner_at = lambda px, pz, owner=owner: np.zeros(np.broadcast_arrays(px, pz)[0].shape, dtype=int)
        base = next(item["mesh"] for item in T.authored_overlays(world, G.GltfBuilder("test"))
                    if item["name"] == "AuthoredGround_SunmaneBase")
        alphas[side] = {tuple(p): float(a) for p, a in zip(np.round(base.positions[:, [0, 2]], 6).tolist(),
                                                           base.colors[:, 3])}
    shared = set(alphas["west"]) & set(alphas["east"])
    assert shared
    assert all(alphas["west"][k] == pytest.approx(alphas["east"][k]) for k in shared)
