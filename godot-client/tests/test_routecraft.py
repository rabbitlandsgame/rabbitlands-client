"""Surveyed roads meet their stations; tidal decks expose a continuous top."""
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[2] /
                       "eloria-assets/maps/nymara-regions/_toolkit"))
from amberwood import routecraft as RC
from amberwood.terrain import Terrain


def test_unequal_road_segments_meet_their_surveyed_landings():
    terrain = Terrain(-10, -10, 50, 30, cell=0.5)
    terrain.height[:] = -8
    RC.grade_road(terrain, [(0, 0), (4, 0), (30, 0)], [2, 3, 6], width=6)
    for x, expected in ((0, 2), (4, 3), (17, 4.5), (30, 6)):
        for z in (-2, 0, 2):
            assert abs(terrain.height_at(x, z) - expected) < 1e-6
    assert terrain.height_at(17, 12) == -8


def test_bent_causeway_has_upward_decks_meeting_at_the_same_edge():
    deck = RC.graded_causeway([(0, 2, 0), (10, 3, 0), (20, 5, 5)])
    assert len(deck.walk_parts) == 2
    a, b = deck.walk_parts
    assert np.all(a.normals[:, 1] > 0.9)
    assert np.all(b.normals[:, 1] > 0.9)
    assert np.allclose(a.positions[1], b.positions[0])
    assert np.allclose(a.positions[2], b.positions[3])
    # The only upward skin at the road's centre belongs to the walk bucket.
    assert not any(np.allclose(part.positions[:, 1], 3) for part in deck.parts)


def test_ground_preview_uses_its_texture_instead_of_material_zero(monkeypatch):
    from types import SimpleNamespace
    from amberwood import mesh as M, render as R
    import preview

    scene = R.Scene()
    scene.add_material(R.RenderMaterial("oak", albedo="wood"))
    scene.add_material(R.RenderMaterial("paving", albedo="stone"))
    monkeypatch.setattr(preview, "new_scene", lambda _: scene)
    ground = M.quad([(0, 0, 0), (1, 0, 0), (1, 0, 1), (0, 0, 1)],
                    material="paving_ground")
    build = SimpleNamespace(terrain_meshes={"path": ground}, water_meshes={},
                            placements=[])
    rendered = preview.scene_from_build(build, {})
    material = rendered.materials[int(rendered.tri_material[0][0])]
    assert material.name == "paving_ground"
    assert material.albedo == "stone"
    assert material.alpha_mode == "MASK"


def test_annular_promenade_is_visible_to_grounding_ray():
    from amberwood import routecraft
    mesh = routecraft.annular_walk(24.2, 9.45)
    triangles = mesh.positions[mesh.indices.reshape(-1, 3)]
    normals = np.cross(triangles[:, 1] - triangles[:, 0],
                       triangles[:, 2] - triangles[:, 0])
    top = np.all(np.isclose(triangles[:, :, 1], 0.16), axis=1)
    assert top.sum() == 80
    assert np.all(normals[top, 1] > 0)
    assert not np.any(normals[:, 1] < -1e-8)


def test_fitted_stair_has_one_tread_layer_and_meets_both_landings():
    from amberwood import junglecraft
    from verify_runtime import VerticalRayIndex
    width, length, height = 9.5, 68.0, 22.0
    stairs = junglecraft.grand_stair(width=width, height=height, length=length, landings=2)
    triangles = np.concatenate([
        part.positions[part.indices.reshape(-1, 3)] for part in stairs.walk_parts])
    normal = np.cross(triangles[:, 1] - triangles[:, 0],
                      triangles[:, 2] - triangles[:, 0])
    upward = normal[:, 1] > 1e-8
    assert abs(normal[upward, 1].sum() * 0.5 - width * length) < 1e-6
    ray = VerticalRayIndex(triangles, cell=2)
    assert 0 < ray.top_hit(0, 0.01) < 0.21
    assert abs(ray.top_hit(0, length - 0.01) - height) < 1e-6


def test_crossing_standing_points_are_inside_the_rendered_deck():
    from verify_runtime import VerticalRayIndex
    stations = [(0, 2, 0), (0.5, 2.1, 0), (10, 4, 5), (16, 5, 12)]
    deck = RC.graded_causeway(stations)
    triangles = np.concatenate([
        part.positions[part.indices.reshape(-1, 3)] for part in deck.walk_parts])
    ray = VerticalRayIndex(triangles, cell=2)
    ends = RC.crossing_endpoints(stations)
    for x, y, z in ends:
        assert abs(ray.top_hit(x, z) - y) < 0.05  # triangulated mitres vary by centimetres
    assert ends[0][0] > 0.5  # a short first segment does not clamp the inset
    assert ends[1][2] < 12


def test_arcaded_causeway_meets_unrounded_shores_with_one_walk_skin():
    from amberwood import civiccraft
    from verify_runtime import VerticalRayIndex
    bridge = civiccraft.arcaded_causeway(37.25, 3.43, 6.18, arches=3)
    triangles = np.concatenate([
        p.positions[p.indices.reshape(-1,3)] for p in bridge.walk_parts])
    normal = np.cross(triangles[:,1]-triangles[:,0],
                      triangles[:,2]-triangles[:,0])
    assert np.all(normal[:,1] > 0)
    assert abs(normal[:,1].sum()/2 - 37.25*5.4) < 1e-4
    ray = VerticalRayIndex(triangles,cell=2)
    for x in (-18.62,0,18.62):
        expected = 3.43+(x+37.25/2)/37.25*(6.18-3.43)
        assert abs(ray.top_hit(x,0)-expected) < 1e-5
    assert len(bridge.walk_parts) == 1


def test_sloped_plank_walk_has_no_grounding_holes_at_its_seams():
    from amberwood import civiccraft
    from verify_runtime import VerticalRayIndex
    length,near,far,width=53.27,2.37,4.19,3.0
    bridge=civiccraft.sloped_boardwalk(length,near,far,width=width)
    triangles=np.concatenate([p.positions[p.indices.reshape(-1,3)]
                              for p in bridge.walk_parts])
    normal=np.cross(triangles[:,1]-triangles[:,0],triangles[:,2]-triangles[:,0])
    assert np.all(normal[:,1]>0)
    assert abs(normal[:,1].sum()/2-length*width)<1e-4
    ray=VerticalRayIndex(triangles,cell=2)
    # Both seams and plank middles must hit exactly the surveyed grade.
    for z in np.linspace(0,length,len(bridge.walk_parts)*2+1)[1:-1]:
        for x in (-1.35,0,1.35):
            assert abs(ray.top_hit(x,z)-(near+(far-near)*z/length))<1e-5


def test_observatory_stair_reaches_an_open_podium_without_opening_the_drum():
    from amberwood import observatorycraft
    from verify_runtime import VerticalRayIndex
    piece=observatorycraft.observatory()
    triangles=np.concatenate([p.positions[p.indices.reshape(-1,3)] for p in piece.walk_parts])
    ray=VerticalRayIndex(triangles,cell=2)
    assert ray.top_hit(0,0) is None
    assert abs(ray.top_hit(0,9)-2.9)<1e-5
    heights=[ray.top_hit(0,z) for z in np.linspace(18.1,10.4,29)]
    assert all(h is not None for h in heights)
    assert all(-1e-5<=b-a<=0.22 for a,b in zip(heights,heights[1:]))
    assert abs(heights[-1]-2.9)<1e-5


def test_channel_removes_a_downstream_rise_without_raising_its_banks():
    from amberwood import terrain as TER
    t=TER.Terrain(-2,-2,24,8,1)
    t.height=9-0.1*t.gx+3*np.exp(-((t.gx-12)/3)**2)
    before=t.height.copy()
    RC.incise_channel(t,[(0,0),(20,0)],width=3,shoulder=2)
    assert np.all(t.height<=before+1e-10)
    bed=t.height_at(np.arange(1,20),np.zeros(19))
    assert np.max(np.diff(bed))<1e-6
    assert t.height_at(12,0)<before[2,14]-2


def test_sounding_stage_has_an_open_shaft_and_a_continuous_work_floor():
    from amberwood import civiccraft
    from verify_runtime import VerticalRayIndex
    piece=civiccraft.sounding_stage()
    triangles=np.concatenate([p.positions[p.indices.reshape(-1,3)] for p in piece.walk_parts])
    ray=VerticalRayIndex(triangles,cell=1)
    assert ray.top_hit(0,0) is None
    for x,z in ((5.9,-1.6),(5.9,0),(5.9,1.6),(-5,0),(0,4),(0,-4),(3,3)):
        assert abs(ray.top_hit(x,z))<1e-6
    normal=np.cross(triangles[:,1]-triangles[:,0],triangles[:,2]-triangles[:,0])
    assert np.all(normal[:,1]>0)
    # The faceted circular opening approximates the coping circle.
    assert abs(normal[:,1].sum()/2-(12*10-np.pi*1.84**2))<0.03


def test_near_secret_uses_reserved_paving_but_respects_real_structures():
    from amberwood import terrain as TER
    import secretdoors as SD
    t=TER.Terrain(-80,-80,160,160,2)
    t.height[:]=5
    t.surface[:]=next(iter(TER.AUTHORED_SURFACES))
    t.tree_block[:]=np.hypot(t.gx,t.gz)<25
    prints=np.array([[0,0,5]])
    old=SD._site(t,0,0,0,prints=prints)
    near=SD._site(t,0,0,0,prints=prints,prefer_near=True)
    assert np.linalg.norm(old)>25
    assert 7<np.linalg.norm(near)<=14
