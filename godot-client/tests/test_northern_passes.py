"""A low pass must have readable shoulders without moving its fixed contracts."""
from pathlib import Path
from types import SimpleNamespace
import sys
import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'eloria-assets/maps/nymara-regions/_toolkit'))
from amberwood import mesh as M
from amberwood.terrain import Terrain
import continent_geography as G
import northern_passes as N
from regionbuild import Placement, RegionBuild


def test_col_opens_camera_space_preserving_road_edge_and_real_footing(monkeypatch):
    terrain = Terrain(-80, -100, 160, 200, cell=1)
    terrain.height[:] = 150
    # Vertical common boundary at x=70; otherwise native mountain plateaux.
    monkeypatch.setattr(G, 'boundary_sample', lambda region, p, maximum: (abs(p[:, 0]-70), np.full(len(p), 24.)))
    monkeypatch.setattr(N, '_footprints', lambda build: [(np.array([25., 30.]), np.array([35., 40.]))])
    points = np.array([[0., 150., 0.], [0., 150., 10.], [0., 150., 20.],
                       [0., 150., 40.], [70., 24., 0.], [30., 150., 35.]])
    native = M.Mesh(positions=points.copy(), indices=np.array([], dtype=int))
    road = M.quad([[-50,24, -3.5], [70,24,-3.5], [70,24,3.5], [-50,24,3.5]], material='test')
    road_before = road.positions.copy()
    build = SimpleNamespace(terrain=terrain, placements=[], notes=[],
        terrain_meshes={'Terrain_Test':native, 'Walk_Test':road},
        geography_roads=[dict(id='mirrorhold-amethyst', stations=[[-50,24,0],[70,24,0]])])
    N.apply(build, 'mirrorhold')
    assert np.allclose(native.positions[:4, 1], [24,24.3,26.7,38.7])
    assert np.array_equal(native.positions[4:], points[4:])
    assert np.array_equal(road.positions, road_before)
    assert np.isclose(terrain.height_at(0,10), 24.3)


def test_owned_scene_uses_actual_land_instead_of_obsolete_distant_ring(monkeypatch):
    import streaming_borders as S
    monkeypatch.setattr(G, 'apply_geometry', lambda *args: None)
    monkeypatch.setattr(G, 'finalize_geometry', lambda *args: None)
    monkeypatch.setattr(S, 'region_specs', lambda region: [dict(geometryMode='continent-owned-v1',
        anchor=[0,0,0], outward=[1,0], portal='test')])
    monkeypatch.setattr(S, 'materials_for', lambda region: set())
    monkeypatch.setattr(S, '_apply_one', lambda *args: None)
    monkeypatch.setattr(S, '_owned_threshold', lambda *args: None)
    monkeypatch.setattr(S, 'partition_shared_approaches', lambda *args: None)
    build = SimpleNamespace(terrain_meshes={'Backdrop_Distant':object(), 'Terrain_Real':object()},
        water_meshes={}, portals=[])
    S.apply(build, 'mirrorhold')
    assert set(build.terrain_meshes) == {'Terrain_Real'}


def test_natural_kinds_and_linked_pole_markers_follow_ground_but_discoveries_keep_pose(monkeypatch):
    terrain = Terrain(-80, -100, 160, 200, cell=1)
    terrain.height[:] = 150
    monkeypatch.setattr(G, 'boundary_sample', lambda region, p, maximum: (np.full(len(p), 100.), np.zeros(len(p))))
    build = RegionBuild(terrain)
    build.meshes['piece'] = M.box((2, 1, 2))
    build.placements = [Placement('March_test_Signpost', 'piece', (0,150.1,10)),
        Placement('Scrub_LeeTuft_0', 'piece', (10,150,10), kind='scrub'),
        Placement('Crystal_Outcrop_0', 'piece', (20,149.7,10), kind='crystal', collides=True),
        Placement('Secret_test', 'piece', (0,150,60))]
    marker = dict(id='march', node='March_test_Signpost', position=[0,150.8,10])
    build.landmarks.append(marker)
    build.interactives.append(marker)
    build.geography_roads = [dict(id='mirrorhold-amethyst', stations=[[-50,24,0],[70,24,0]])]
    N.apply(build, 'mirrorhold')
    assert np.allclose([p.position[1] for p in build.placements], [24.4,24.3,24.,150.])
    assert np.isclose(marker['position'][1],25.1)  # Shared record moves once.
    assert np.isclose(terrain.height_at(0,60),150.)
