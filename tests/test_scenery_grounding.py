"""Ground contact regressions for the scenery found in the map-wide audit."""
import sys
from pathlib import Path

import numpy as np
import pytest

CLIENT = Path(__file__).resolve().parents[1]
REGIONS = CLIENT / "eloria-assets/maps/nymara-regions"
sys.path.insert(0, str(REGIONS / "_toolkit"))
import glb_reader as G
from verify_runtime import VerticalRayIndex
from amberwood import mesh as M
from amberwood.terrain import Terrain


def test_prop_height_matches_the_rendered_triangles_on_a_saddle():
    terrain = Terrain(-3, -5, 4, 4, cell=2)
    terrain.height[:] = [[0, 8, 1], [6, 0, 4], [1, 3, 2]]
    mesh = M.heightfield(terrain.height, terrain.x0, terrain.z0, terrain.cell)
    rays = VerticalRayIndex(mesh.positions[mesh.indices].reshape(-1, 3, 3))
    x = np.array([-2.6, -2, -1.4, -.8, .2])
    z = np.array([-4.4, -4, -3.7, -2.2, -1.8])
    actual = terrain.mesh_height_at(x, z)
    np.testing.assert_allclose(actual, [rays.top_hit(a, b) for a, b in zip(x, z)])
    assert terrain.height_at(-2, -4) > terrain.mesh_height_at(-2, -4) + 3



def world_anchor(doc, index):
    """The world-space origin of a node, composed through its parents."""
    nodes = doc["nodes"]
    parent = {child: i for i, node in enumerate(nodes) for child in node.get("children", [])}
    matrix = np.eye(4)
    while index is not None:
        node = nodes[index]
        local = np.eye(4)
        if "matrix" in node:
            local = np.array(node["matrix"], dtype=float).reshape(4, 4).T
        else:
            qx, qy, qz, qw = node.get("rotation", [0, 0, 0, 1])
            rotation = np.array([[1 - 2 * (qy * qy + qz * qz), 2 * (qx * qy - qz * qw), 2 * (qx * qz + qy * qw)],
                                 [2 * (qx * qy + qz * qw), 1 - 2 * (qx * qx + qz * qz), 2 * (qy * qz - qx * qw)],
                                 [2 * (qx * qz - qy * qw), 2 * (qy * qz + qx * qw), 1 - 2 * (qx * qx + qy * qy)]])
            local[:3, :3] = rotation @ np.diag(node.get("scale", [1, 1, 1]))
            local[:3, 3] = node.get("translation", [0, 0, 0])
        matrix = local @ matrix
        index = parent.get(index)
    return [float(v) for v in matrix[:3, 3]]

@pytest.mark.parametrize("region,name", [
    ("amberwood", "Prop_BurntBrazier_2"),
    ("verdant_stair", "Signpost_TempleCourt"),
    ("westhaven", "Prop_Lamp_market_climb_03"),
    ("ssarathi_ruins", "Tree_779"),
])
def test_corrected_prop_anchor_touches_the_actual_floor_in_each_lod(region, name):
    checked = 0
    for path in sorted((REGIONS / region).glob("world*.glb")):
        doc, body = G.load(path)
        matches = [n for n in doc["nodes"] if n.get("name") == name]
        if not matches:
            assert path.name == "world-lod2.glb", f"Missing prop in {path}"
            continue
        rays = VerticalRayIndex(G.triangles(doc, body, G.named(doc, "Terrain_") + G.named(doc, "Walk_")))
        # Continent packages wrap each placed prop in a `<region>_<name>_WorldPlacement`
        # parent that carries the world transform; the prop's own translation is local.
        x, y, z = world_anchor(doc, doc["nodes"].index(matches[0]))
        floor = rays.top_hit(x, z)
        assert floor is not None
        assert abs(y - floor) < .025, (region, name, path.name, y, floor)
        checked += 1
    assert checked


def test_crownwater_rows_end_before_the_unsupported_stations():
    for path in sorted((REGIONS / "crownwater").glob("world*.glb")):
        doc, _ = G.load(path)
        names = {n.get("name", "") for n in doc["nodes"]}
        assert "Prop_Lamp_Harbour_6" in names
        assert "Prop_Banner_Harbour_2" in names
        assert not any(n.startswith(("Prop_Lamp_Harbour_7", "Prop_Banner_Harbour_3")) for n in names)
