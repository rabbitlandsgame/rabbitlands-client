"""Inspect actual exported trunks on the lowered northern hillside."""
from pathlib import Path
import sys

import numpy as np
import pytest

REGIONS = Path(__file__).resolve().parents[2] / 'eloria-assets/maps/nymara-regions'
sys.path.insert(0, str(REGIONS / '_toolkit'))
import glb_reader as G
from verify_runtime import VerticalRayIndex


@pytest.mark.parametrize('filename', ['world.glb', 'world-lod2.glb'])
def test_lowered_bank_tree_trunks_touch_physical_soil(filename):
    doc, body = G.load(REGIONS / 'verdant_stair' / filename)
    matrices, _ = G.hierarchy(doc)
    ground_nodes = [i for i, node in enumerate(doc['nodes'])
                    if 'mesh' in node and node.get('name', '').startswith('Terrain_')
                    and not any(label in node['name'] for label in
                                ('_StreamCollar_', '_ContinentBlend_', 'OuterEscarpment', '_StreamThreshold_'))]
    soil = VerticalRayIndex(G.triangles(doc, body, ground_nodes))
    checked = 0
    # The central cut contains both tall broadleaf trees and hanging palms.
    # Read the trunk primitives; the lowest frond is not a root contact.
    for i, node in enumerate(doc['nodes']):
        if not node.get('name', '').startswith('Tree_') or '__' in node['name']:
            continue
        x, _, z = matrices[i][:3, 3]
        if not (-34 < x < 75 and -248 < z < -202):
            continue
        root_heights = []
        for child in node.get('children', []):
            piece = doc['nodes'][child]
            for primitive in doc['meshes'][piece['mesh']]['primitives']:
                material = doc['materials'][primitive['material']].get('name', '')
                if 'bark' not in material.lower():
                    continue
                points = G.accessor(doc, body, primitive['attributes']['POSITION']).astype(float)
                ids = G.accessor(doc, body, primitive['indices']).ravel().astype(int)
                matrix = matrices[child]
                root_heights.append(float((points[ids] @ matrix[:3, :3].T + matrix[:3, 3])[:, 1].min()))
        assert root_heights, node['name']
        ground = soil.top_hit(x, z)
        assert ground is not None, node['name']
        assert abs(min(root_heights) - ground) < .002, (node['name'], min(root_heights), ground)
        checked += 1
    assert checked >= 8, (filename, checked)
