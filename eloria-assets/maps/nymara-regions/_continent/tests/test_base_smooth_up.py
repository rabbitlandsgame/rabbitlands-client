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


def test_a_forest_floor_gives_way_on_a_cliff_but_keeps_its_brink():
    # Level ground and an 80 degree wall under one forest-floor patch and one other glaze: the floor's coverage is
    # scaled at each facet corner by forest_floor_keep; it keeps the authored 0.4 on every level facet, the brink's
    # included, loses all of it on the wall, and every other glaze keeps its coverage on the wall.
    from types import SimpleNamespace
    import authoring as A
    from amberwood import gltf as G

    pbr = {"albedoColor": [0.52, 0.5, 0.4, 1.], "roughness": 1., "metallic": 0., "normalScale": 1.,
           "uvScale": [1., 1., 1.]}

    def region(region_id, preset, priority):
        matrix = np.eye(4)
        matrix[0, 3], matrix[2, 3] = 11., 11.
        return {"id": region_id, "enabled": True, "priority": priority, "shape": "rectangle", "size": [40., 40.],
                "blendWidth": 0., "opacity": 0.4, "matrix": matrix.ravel(order="F").tolist(),
                "surface": {"preset": preset, "rotationDegrees": 0, "pbr": pbr, "pbrOverrides": pbr}}

    class Snapshot:
        translation = np.array([0., 0., 0.])
        terrain_width = terrain_height = 12

        @staticmethod
        def base_colors():
            return np.full((12, 12, 4), 200, dtype=np.uint8)
        document = {"terrain": {"origin": [0., 0.], "cellMetres": 2., "previewUvMetresInverse": .24,
                                "baseSurface": {"preset": "Desert", "rotationDegrees": 0}},
                    "groundRegions": [region("forest-01", T.FOREST_FLOOR_PRESET, 1),
                                      region("meadow-01", "Custom", 2)], "paths": []}
    x = np.arange(0., 24., 2.)
    gx, gz = np.meshgrid(x, x)
    height = np.where(gx >= 12., (gx - 12.) * np.tan(np.radians(80)), 0.)
    world = SimpleNamespace(authoring_snapshot=Snapshot(), ids=[A.SUNMANE], owner=np.zeros(gx.shape, int),
                            gx=gx, gz=gz, height=height, x=x, z=x, x0=0., z0=0.)
    world.owner_at = lambda px, pz: np.zeros(np.broadcast_arrays(px, pz)[0].shape, dtype=int)
    overlays = {item["name"]: item["mesh"] for item in T.authored_overlays(world, G.GltfBuilder("test"))}
    forest, meadow = overlays["AuthoredGround_forest-01"], overlays["AuthoredGround_meadow-01"]
    positions = np.stack([gx, height + .006, gz], axis=-1).reshape(-1, 3)
    row, col = np.nonzero(np.ones((11, 11), bool))
    a = row * 12 + col
    tri = np.stack((a, a + 12, a + 1, a + 1, a + 12, a + 12 + 1), axis=1).reshape(-1, 3)
    up = T.base_smooth_up(positions, tri)
    by_key = {tuple(k): u for k, u in zip(np.round(positions[:, [0, 2]], 6).tolist(), up)}
    smooth = np.array([by_key[tuple(k)] for k in np.round(forest.positions[:, [0, 2]], 6).tolist()])
    corners = np.arange(len(forest.positions)).reshape(-1, 3)
    np.testing.assert_allclose(forest.colors[:, 3].reshape(-1, 3),
                               0.4 * T.forest_floor_keep(forest.positions, smooth, corners), atol=1e-9)
    # The brink's vertices are smoothed to a cliff (under 0.6, where the smoothed slope alone keeps under 0.9 of the
    # floor, under the look's 0.36 rim), yet every level facet, the brink's too, keeps the authored 0.4 at all three
    # corners: the floor reaches the crease, with no teeth cut into the brink.
    brink = smooth[forest.positions[:, 0] == 12.]
    assert np.median(brink) < 0.6
    assert 0.4 * T.L.smoothstep(*T.FOREST_FLOOR_SMOOTH_UP, brink).min() < 0.36
    assert np.all(forest.colors[:, 3] == pytest.approx(0.4))
    # Facets lying on the wall are not emitted at all; the other glaze covers them.
    assert forest.positions[:, 0].max() == pytest.approx(12.)
    assert meadow.positions[:, 0].max() > 20.
    assert np.all(meadow.colors[:, 3] == pytest.approx(0.4))


def _facet(facet_up):
    """One lattice triangle whose own world-up normal component is `facet_up`."""
    rise = 2. * np.sqrt(1. / facet_up ** 2 - 1.)
    return np.array([[0., 0., 0.], [2., rise, 0.], [0., 0., 2.]]), np.array([[0, 1, 2]])


def test_a_forest_floor_leaves_a_riser_and_a_sheer_face_but_keeps_a_short_bank():
    def keep(facet_up, smooth):
        positions, triangles = _facet(facet_up)
        return T.forest_floor_keep(positions, np.asarray(smooth, float), triangles)[0]

    # Landfall forest-21: a terrace step one facet wide (facet up 0.28-0.57, smoothed 0.65-0.87 at its corners)
    # loses its floor; the short bank beside it (facet up 0.42-0.57, smoothed at least 0.82) keeps all of it.
    for facet_up, smooth in ((0.28, (0.66, 0.82, 0.65)), (0.525, (0.78, 0.86, 0.84)), (0.569, (0.74, 0.84, 0.87))):
        assert keep(facet_up, smooth).max() < 0.1
    for facet_up, smooth in ((0.416, (0.82, 0.9, 0.84)), (0.501, (0.85, 0.86, 0.82)), (0.567, (0.91, 0.84, 0.9))):
        assert keep(facet_up, smooth) == pytest.approx(np.ones(3))
    # A face steeper than about 66 degrees sheds it however gentle the ground around it.
    assert keep(0.3, (0.95, 0.95, 0.95)).max() == 0.
    # A level facet keeps it at a cliff's brink or foot, a steep one inside a cliff keeps none.
    assert keep(0.95, (0.3, 0.45, 0.9)) == pytest.approx(np.ones(3))
    assert keep(0.5, (0.3, 0.4, 0.45)).max() == 0.
    # A brink facet keeps it whole up to the crease: as level as about 37 degrees (Landfall (-263, -83), at the top of
    # a sheer drop, two corners smoothed under 0.4), or with a corner on ground the floor keeps by the smoothed slope
    # (Spindle Hill's lip, coilmere (-254, 73)).
    assert keep(0.844, (0.357, 0.369, 0.639)) == pytest.approx(np.ones(3))
    assert keep(0.777, (0.604, 0.776, 0.78)) == pytest.approx(np.ones(3))
    # A ledge facet inside the face, every corner smoothed under 0.61, is not kept whole by its levelness: Spindle
    # Hill's lip wedge (C24, facets 13619 / 13618) keeps none at its corners in the face, and its steeper half stays
    # under the look's 0.36 rim (authored 0.4) everywhere.
    wedge = keep(0.728, (0.333, 0.604, 0.584))
    assert wedge[0] < 0.02 and wedge[1:].min() > 0.9
    wedge = keep(0.687, (0.584, 0.318, 0.333))
    assert wedge[1:].max() == 0. and 0.4 * wedge.max() < 0.34
    # There it keeps it per corner where the look's stone leaves that corner, so the floor meets the stone along
    # the smoothed contour.
    ledge = keep(0.73, (0.3, 0.45, 0.6))
    assert ledge[0] == 0. < ledge[1] < ledge[2] == pytest.approx(1.)
    # On a broad slope smoothed gentler than 46 degrees a facet of 50 degrees or less keeps it all, and the keep
    # follows the smoothed contour per corner, never a facet's edge, where the facet is level enough for the face
    # cut to leave it.
    assert keep(0.66, (0.7, 0.72, 0.75)) == pytest.approx(np.ones(3))
    inside = keep(0.62, (0.5, 0.6, 0.7))
    assert inside[0] < inside[1] < inside[2]
    # Never more as the facet steepens or the ground around it does.
    ups = np.linspace(0.05, 1., 96)
    for smooth in (0.3, 0.55, 0.7, 0.8, 0.9):
        values = np.array([keep(u, (smooth,) * 3)[0] for u in ups])
        assert np.all(np.diff(values) >= -1e-12)
    for facet_up in (0.3, 0.5, 0.6, 0.7, 0.9):
        values = np.array([keep(facet_up, (s,) * 3)[0] for s in np.linspace(0., 1., 101)])
        assert np.all(np.diff(values) >= -1e-12)
