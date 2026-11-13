"""Paired source, visible-art and publication contracts for the isle resources."""
import copy
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import sys

import pytest

HERE = Path(__file__).resolve().parents[1]
ROOT = HERE.parents[3]
sys.path[:0] = [str(HERE),str(ROOT/'tools')]
import harvest_presentation as HP
import publish_harvest_diversity as P
import prepare_isle_harvestables as art

PLAN = json.loads(P.PLAN.read_bytes())


def read(relative): return json.loads((ROOT/relative).read_bytes())


def test_authoring_markers_and_native_resource_labels_agree():
    underground = read(P.V2+'/_continent_v2/content/underground.json')
    for group in PLAN['groups']:
        world = read(f'{P.V2}/{group["map"]}/client/world.json')
        nodes = {n['objectId']:n for n in world['harvestables']}
        if group['section']:
            section = next(s for s in underground['sections'] if s['id']==group['section'])
            source = {n[0]:n for n in section['nodes']}
        else:
            text = (ROOT/f'godot-client/world_authoring/regions/{group["map"]}/{group["map"]}.tscn').read_text()
            source = {}
            for block in re.split(r'(?=\[node )',text):
                if 'parent="Gameplay/Harvestables"' not in block: continue
                extras = re.search(r'extras = (\{.*?\n\})',block,re.S)
                if extras:
                    values = json.loads(extras[1]);source[values['objectId']]=values
        for target in group['nodes']:
            node=nodes[target['objectId']]
            assert node['resource']==group['resource']
            assert node['serverTile']==target['tile'] and node['position']==target['position']
            authored=source[target['objectId']]
            assert (authored[1] if group['section'] else authored['resource'])==group['resource']
            if not group['section']:
                assert authored['grouping']==node['grouping']==group['grouping']
                assert authored['groupingName']==group['name']


def test_changed_group_markers_use_the_normal_tile_rounding_rule():
    for region in {g['map'] for g in PLAN['groups'] if not g['section']}:
        world=read(f'{P.V2}/{region}/client/world.json')
        names={g['id']:g['name'] for g in world['harvestGroupings']}
        records=[dict(n,**({'groupingName':names[n['grouping']]} if n.get('grouping') else {})) for n in world['harvestables']]
        expected=HP.package_entries(records,[],world['coordinateTransform']['serverOrigin'])[1]
        assert world['harvestGroupings']==expected


def test_resource_only_amendment_keeps_all_static_world_fields():
    for region in {g['map'] for g in PLAN['groups']}:
        relative=f'{P.V2}/{region}/client/world.json'
        old=json.loads(subprocess.check_output(['git','-C',str(ROOT),'show',PLAN['clientBase']+':'+relative]))
        new=read(relative)
        for document in (old,new):
            document.pop('harvestables');document.pop('harvestGroupings',None)
            document['provenance'].pop(P.KEY,None)
            if region=='landfall_insides': document['provenance'].pop('sourceSha256')
        assert old==new,region


def test_new_imported_art_and_palettes_are_bound_to_real_source_files():
    source=read(art.SOURCE)
    catalog=read('godot-client/data/world/objects.json')['harvestables']
    total_bytes=0
    for record in source['models']:
        original=ROOT/record['source'];output=ROOT/record['output']
        assert hashlib.sha256(original.read_bytes()).hexdigest()==record['sourceSha256']
        assert hashlib.sha256(output.read_bytes()).hexdigest()==record['sha256']
        assert record['sourceBinaryPrefixPreserved'] and not record['newModelGeneration']
        entry=catalog['models'][catalog['resources'][record['resource']]]
        assert not entry.get('retired') and 90<=entry['triangles']<=2600
        assert entry['sha256']==record['sha256']
        total_bytes+=output.stat().st_size
    assert total_bytes<20*1024*1024
    for name in art.MINERALS:
        entry=catalog['models'][catalog['resources'][name]]
        assert not entry.get('retired') and entry['resourcePalette']==source['mineralPalettes'][name]
        if name!='Bog Iron':
            assert len(catalog['wallVariants'][name])==3
            assert all(catalog['models'][key]['label']==name and catalog['models'][key]['placement']=='wall'
                       for key in catalog['wallVariants'][name])


def test_paired_server_rows_match_every_amended_site():
    server=os.environ.get('RABBITLANDS_SERVER_ROOT')
    if not server: pytest.skip('Set RABBITLANDS_SERVER_ROOT to the paired server checkout')
    sys.path.insert(0,server)
    from eloria.harvesting import load_harvesting
    resources,nodes=load_harvesting(Path(server)/'config/eloria/harvesting.txt',overlay=True)
    for group in PLAN['groups']:
        assert group['resource'] in resources
        for target in group['nodes']:
            node=nodes[group['map'],target['objectId']]
            assert [node.x,node.y]==target['tile'] and node.resource==group['resource']
