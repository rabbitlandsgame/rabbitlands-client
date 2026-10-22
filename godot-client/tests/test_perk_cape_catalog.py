"""The ten design entries resolve to distinct, usable imported cape variants."""
import json
from pathlib import Path
import xml.etree.ElementTree as ET

CLIENT = Path(__file__).resolve().parents[2]
PROJECT = CLIENT / 'godot-client'

def test_perk_cape_designs_have_unique_materials_and_back_emblems():
    designs = json.loads((CLIENT / 'eloria-assets/source/perk-capes/catalog.json').read_text())
    registry = json.loads((PROJECT / 'data/actors/equipment.json').read_text())['models']
    assert len(designs) == 10
    for field in ('name', 'perk', 'itemId', 'visualId', 'emblem'):
        assert len({entry[field] for entry in designs}) == 10
    for entry in designs:
        model = registry[f"2:{entry['visualId']}"]
        assert model['scene'] == 'res://assets/actors/native/equipment/generic_cape.glb'
        assert model['emblem'] == entry['emblem']
        assert model['skinRegion'] == 'cape'
        assert model['tint'] == [[int(c[i:i+2], 16) for i in (1, 3, 5)]
                                 for c in entry['colours']]
        svg = PROJECT / entry['emblem'].removeprefix('res://')
        assert ET.parse(svg).getroot().tag == '{http://www.w3.org/2000/svg}svg'
