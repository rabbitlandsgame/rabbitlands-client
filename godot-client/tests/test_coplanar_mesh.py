"""Geometry-level checks for room-joint clipping, independent of any map layout."""
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "eloria-assets/maps/nymara-regions/_toolkit"))
from amberwood import mesh as M
from amberwood.coplanar import trim_coplanar
from amberwood.stonework import MeshGroup


def sheet(x0, z0, x1, z1, y=0):
    m = M.quad([(x0, y, z0), (x0, y, z1), (x1, y, z1), (x1, y, z0)])
    m.uvs = m.positions[:, [0, 2]].copy()
    return m


def area(m):
    t = m.positions[m.indices.reshape(-1, 3)]
    return float(np.linalg.norm(np.cross(t[:, 1] - t[:, 0], t[:, 2] - t[:, 0]), axis=1).sum() / 2)


def test_partial_overlap_preserves_union_uvs_and_winding():
    g = MeshGroup()
    a, b = sheet(0, 0, 2, 2), sheet(1, 1, 3, 3)
    g.add(a).add(b)
    trim_coplanar(g)
    assert abs(area(a) + area(b) - 7) < 1e-7
    assert abs(area(b) - 3) < 1e-7
    np.testing.assert_allclose(b.uvs, b.positions[:, [0, 2]], atol=1e-9)
    t = b.positions[b.indices.reshape(-1, 3)]
    assert np.all(np.cross(t[:, 1] - t[:, 0], t[:, 2] - t[:, 0])[:, 1] > 0)


def test_navigation_keeps_coverage_and_roofs_cannot_erase_visible_structure():
    g = MeshGroup()
    solid, walk, roof = sheet(0, 0, 2, 2), sheet(0, 0, 2, 2), sheet(0, 0, 2, 2)
    g.add(solid).add_walk(walk).add_overhead(roof)
    trim_coplanar(g)
    assert area(walk) == 4
    assert solid.triangle_count == 0
    assert area(roof) == 4


def test_back_faces_and_separated_planes_survive():
    g = MeshGroup()
    front, back, above = sheet(0, 0, 2, 2), sheet(0, 0, 2, 2).flip_winding(), sheet(0, 0, 2, 2, y=.1)
    g.add(front).add(back).add(above)
    trim_coplanar(g)
    assert [area(m) for m in g.parts] == [4, 4, 4]


def test_small_depth_offsets_are_clipped_but_disjoint_coverage_remains():
    g = MeshGroup()
    a, b, c = sheet(0, 0, 2, 2), sheet(1, 0, 3, 2, y=.01), sheet(5, 0, 7, 2)
    g.add(a).add(b).add(c)
    trim_coplanar(g)
    assert [area(m) for m in g.parts] == [4, 2, 4]

def test_spatial_batches_preserve_every_face_uv_and_surface_class():
    from amberwood.spatial import sections
    g = MeshGroup()
    g.add_walk(sheet(0, 0, 2, 30))
    g.add(M.box((2, 4, 30)))
    g.add_overhead(sheet(0, 0, 2, 30, y=4))
    result = sections(g, "test", cell_metres=10)
    assert len(result) > 1
    # NumPy can return inverse indices in the input's 2D shape. Mesh expects
    # a flat index stream; otherwise two-triangle panels count as empty and
    # the material merge silently drops them at export.
    assert sum(part.triangle_count for _, chunk in result for part in chunk.all_parts) == g.triangle_count
    assert all(part.indices.ndim == 1 for _, chunk in result for part in chunk.all_parts)
    for bucket in ("parts", "walk_parts", "overhead_parts"):
        def faces(parts):
            return sorted(tuple(np.concatenate([p.positions[t], p.uvs[t]], axis=1).ravel())
                          for p in parts for t in p.indices.reshape(-1, 3))
        assert faces(getattr(g, bucket)) == faces([p for _, chunk in result for p in getattr(chunk, bucket)])


def test_pit_lid_remains_a_cutaway_without_making_water_walkable():
    from amberwood.interiors import Interior
    from gauntlets.rooms import _room_
    g = Interior("test", "Test", "gauntlet", "", [0, 0, 0], "default")
    _room_(g, "pit", -4, 0, 4, 10, -3, 8,
           {"floor": "water_pool", "wall": "cliff_rock", "ceil": "cliff_rock"}, walk=False)
    assert g.group.overhead_parts
    assert not g.group.walk_parts
