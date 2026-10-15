"""Content.load renders the authored open sheets of winding.DOUBLE_SIDED_SHEETS from both sides.

The table is applied to each territory's private document copy straight after the winding correction, so the
exported scene, the atlas and every later stage read the doubleSided materials, while the certified library on
disk keeps its own flags.
"""
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import scene_io as S
import test_retained_attachments as RA
import winding as W

PLAIN_DOCUMENT = RA.document


def sheet_document():
    document = PLAIN_DOCUMENT()
    document['materials'] = [{'name': 'canvas'}, {'name': 'stone'}]
    names = ('Temple_Body__stone', 'Temple_Icicles__canvas', 'Steeple__stone', 'Cairn__stone')
    for mesh, name in zip(document['meshes'], names):
        mesh['name'] = name
        mesh['primitives'][0]['material'] = 1 if name.endswith('stone') else 0
    return document


def test_content_load_turns_the_listed_sheets_double_sided_in_its_private_copy_only(tmp_path, monkeypatch):
    monkeypatch.setattr(RA, 'document', sheet_document)
    monkeypatch.setattr(W, 'DOUBLE_SIDED_SHEETS', {RA.REGION: {'materials': ('canvas',), 'meshes': (('Steeple__*', 'stone'),)},
                                                   'whitehorn_range': {'materials': ('stone',)}})
    world, content = RA.loaded(tmp_path, monkeypatch, transform=[0., 0., 0.])
    document, _ = content.documents[RA.REGION]
    materials = document['materials']
    assert materials[0] == {'name': 'canvas', 'doubleSided': True}
    assert materials[1] == {'name': 'stone'}, 'a material shared with other meshes keeps its own flag'
    assert materials[2] == {'name': 'stone', 'doubleSided': True}
    by_mesh = {mesh['name']: mesh['primitives'][0]['material'] for mesh in document['meshes']}
    assert by_mesh == {'Temple_Body__stone': 1, 'Temple_Icicles__canvas': 0, 'Steeple__stone': 2, 'Cairn__stone': 1}
    assert content.double_sided[RA.REGION]['materials'] == ['canvas']
    assert content.double_sided[RA.REGION]['primitives'] == [['Steeple__stone', 0, 'stone']]
    # The steeple still places as before: sides change materials, never geometry or bounds.
    assert (RA.REGION, 'Landmark_Steeple') in content.placement_by_name
    on_disk, _ = S.GR.load(tmp_path / RA.REGION / 'library.glb')
    assert on_disk['materials'] == [{'name': 'canvas'}, {'name': 'stone'}]
