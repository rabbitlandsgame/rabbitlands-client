"""Standalone rooms expose real floor and doorway geometry to the server."""
import json
from pathlib import Path
import sys

import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] /
                     'eloria-assets/maps/nymara-regions/_toolkit'))
from amberwood import mesh as M
from amberwood.gltf import GltfBuilder, Material, Node
import glb_reader as GLB
from export_interior_collision import export


def room(package):
    writer = GltfBuilder()
    writer.add_material(Material('default'))
    meshes = {
        'Floor_Room': M.box((12, .2, 12), center=(0, -.1, 0)),
        # Two pieces deliberately share one node: an AABB would seal the door.
        'Shell_Wall_South': M.merge([
            M.box((5, 3, .5), center=(-3.5, 1.5, 5)),
            M.box((5, 3, .5), center=(3.5, 1.5, 5))]),
        'Desk': M.box((2, 1, 2), center=(0, .5, 0)),
        'Roof': M.box((12, .2, 12), center=(0, 4, 0)),
    }
    for name, mesh in meshes.items():
        writer.add_mesh(name, mesh)
        writer.add_node(Node(name, mesh=name,
                             translation=(3, 0, -2) if name == 'Desk' else None))
    writer.write_glb(str(package / 'world.glb'))
    manifest = {
        'asset': {'interior': True, 'glb': 'world.glb'},
        'coordinateTransform': {'serverOrigin': [12, 12]},
        'navigation': {'surfaceNodePrefixes': ['Floor_']},
        'collision': {'nodeNames': ['Shell_Wall_South', 'Desk']},
    }
    (package / 'world.json').write_text(json.dumps(manifest), encoding='utf-8')


def test_rendered_floor_door_gap_solids_and_void(tmp_path):
    room(tmp_path)
    summary = export(tmp_path, 24)
    grid, manifest = GLB.read_grid(tmp_path)

    def value(x, z):
        return grid[int((12-z)/.5), int((x+12)/.5)]

    assert summary['floorMeshNodes'] == 1
    assert summary['solidMeshNodes'] == 2
    assert grid.shape == (48, 48)
    assert value(0, 0) > 0  # Undeclared overhead roof does not replace the floor.
    assert value(0, 5) > 0  # Gap within the multi-piece south wall stays open.
    assert value(3, 5) == 0
    assert value(3, -2) == 0  # Transformed desk blocks its actual footprint.
    assert value(8, 0) == 0  # No guessed rectangular room outside the mesh.
    encoding = manifest['collision']['heightEncoding']
    assert encoding['origin'] + float(value(0, 0))*encoding['step'] == pytest.approx(0)
    assert manifest['coordinateTransform']['serverCells'] == [24, 24]
    first = (tmp_path / 'collision.bin').read_bytes()
    export(tmp_path, 24)
    assert (tmp_path / 'collision.bin').read_bytes() == first


def test_missing_walk_surfaces_fail_instead_of_opening_the_room(tmp_path):
    room(tmp_path)
    path = tmp_path / 'world.json'
    manifest = json.loads(path.read_text())
    manifest['navigation']['surfaceNodePrefixes'] = ['Missing_']
    path.write_text(json.dumps(manifest))
    with pytest.raises(ValueError, match='No exposed walkable floor'):
        export(tmp_path, 24)
    assert not (tmp_path / 'collision.bin').exists()
