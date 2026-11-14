"""Publish the resource-only isle diversity amendment, retaining certified routes.

The plan pins ordinary, reachable development commits in both sanitized repos.
Replaying from those exact baselines makes the amendment reviewable/idempotent;
an unrelated change to an output refuses the write. No terrain, geometry,
collision, textures, encounters, NPCs, portals or object identities are changed.
Source scene markers and underground node/vein labels remain the authoring truth.
Run --server CHECKOUT --apply, then --check. No remote uploads are performed.
"""
from __future__ import annotations

import argparse
import copy
import hashlib
import json
from pathlib import Path
import re
import subprocess
import sys

import frames
import harvest_presentation as HP
import publish_server as P

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[3]
V2 = 'eloria-assets/maps/continent-v2'
PLAN = HERE / 'content/harvest-diversity.json'
KEY = 'harvestDiversityAmendments'


def sha(data): return hashlib.sha256(data).hexdigest()


def encode(value, original):
    first_key = re.search(rb'\n( +)"', original)
    indent = len(first_key[1]) if first_key else 2
    data = (json.dumps(value, ensure_ascii=False, indent=indent) + '\n').encode()
    return data.replace(b'\n', b'\r\n') if b'\r\n' in original else data


def require(condition, message):
    if not condition: raise ValueError(message)


def baseline(repo, commit, relative):
    data = subprocess.check_output(['git', '-C', str(repo), 'show', f'{commit}:{relative}'])
    # These certified source/publication files use -text: their exact bytes,
    # including a few historical mixed-newline blocks, are authoritative.
    return data


def groups_for(world, names):
    records = [dict(n, **({'groupingName':names[n['grouping']]} if n.get('grouping') else {}))
               for n in world['harvestables']]
    # Use the normal publisher's floor-to-tile rule, including fractional means.
    return HP.package_entries(records, [], world['coordinateTransform']['serverOrigin'])[1]


def scene_change(data, changes):
    text = data.decode()
    found = set()
    blocks = re.split(r'(?=\[node )', text)
    for i, block in enumerate(blocks):
        if 'parent="Gameplay/Harvestables"' not in block: continue
        match = re.search(r'"objectId"\s*:\s*(\d+)', block)
        if match is None or int(match[1]) not in changes: continue
        oid = int(match[1]); group = changes[oid]
        require(f'label = "{group["previousResource"]}"' in block, f'{oid}: unexpected scene label')
        block = block.replace(f'label = "{group["previousResource"]}"', f'label = "{group["resource"]}"', 1)
        for key, value in [('resource',group['resource']),('grouping',group['grouping']),
                           ('groupingName',group['name'])]:
            pattern = rf'"{key}"\s*:\s*"[^"]*"'
            if re.search(pattern,block): block = re.sub(pattern,f'"{key}": "{value}"',block,count=1)
            else: block = block.replace('extras = {',f'extras = {{\n"{key}": "{value}",',1)
        blocks[i] = block; found.add(oid)
    require(found == set(changes), f'Source scene lacks nodes {set(changes)-found}')
    return ''.join(blocks).encode()


def underground_change(data, groups):
    text = data.decode()
    design = json.loads(data)
    for group in groups:
        section = next(s for s in design['sections'] if s['id'] == group['section'])
        ids = {n['objectId'] for n in group['nodes']}
        for node in section['nodes']:
            if node[0] not in ids: continue
            require(node[1] == group['previousResource'], 'Underground source resource differs')
            pattern = r'\['+str(node[0])+r',\s*"'+re.escape(node[1])+r'"'
            text, count = re.subn(pattern, f'[{node[0]},"{group["resource"]}"', text)
            require(count == 1, 'Underground node not uniquely represented')
        for vein in section.get('veins',[]):
            if not ids.intersection(vein['nodes']): continue
            require(ids == set(vein['nodes']), 'Only complete wall veins may be reassigned')
            node_list = r'\[\s*' + r'\s*,\s*'.join(map(str,vein['nodes'])) + r'\s*\]'
            pattern = r'\{"resource":\s*"'+re.escape(vein['resource'])+r'",\s*"nodes":\s*'+node_list+r'\}'
            text, count = re.subn(pattern,json.dumps(dict(resource=group['resource'],nodes=vein['nodes'])),text)
            require(count == 1, 'Underground vein not uniquely represented')
    result = text.encode()
    import underground_source as S
    S.check(json.loads(result))
    return result


def prepare(server):
    plan_bytes = PLAN.read_bytes()
    plan = json.loads(plan_bytes)
    updates = {}; watched = {PLAN:plan_bytes}
    def old(repo, relative):
        path = repo / relative
        current = path.read_bytes()
        require(path not in watched or watched[path] == current, f'Input changed while preparing: {path}')
        watched[path] = current
        return baseline(repo, plan['clientBase' if repo == ROOT else 'serverBase'], relative)
    def document(repo, relative): return json.loads(old(repo,relative))
    def write(repo, relative, value):
        raw = old(repo,relative)
        updates[repo/relative] = value if isinstance(value,bytes) else encode(value,raw)
    receipt = dict(plan=PLAN.relative_to(ROOT).as_posix(), planSha256=sha(PLAN.read_bytes()),
        nodes=sum(len(g['nodes']) for g in plan['groups']), geometry='unchanged', collision='unchanged',
        operation='resource labels and gathering art only; stable IDs, positions and routes',
        resources=[r['name'] for r in plan['resources']])
    manifest_relative = 'config/eloria/client_content_manifest.json'
    record_relative = V2+'/_continent_v2/publication.json'
    pinned_manifest = document(server,manifest_relative)
    # This amendment owns only continentV2 metadata. Catalogue updates, map
    # registrations and other independent top-level records must survive it.
    manifest = json.loads(watched[server/manifest_relative])
    manifest['continentV2'] = copy.deepcopy(pinned_manifest['continentV2'])
    record = document(ROOT,record_relative)
    catalog_relative = 'godot-client/data/maps/map-backgrounds.json'
    catalog = document(ROOT,catalog_relative)
    by_map = {}
    for group in plan['groups']: by_map.setdefault(group['map'],[]).append(group)
    underground_relative = V2+'/_continent_v2/content/underground.json'
    underground = underground_change(old(ROOT,underground_relative),by_map['landfall_insides'])
    write(ROOT,underground_relative,underground)
    for region, groups in by_map.items():
        relative = f'{V2}/{region}/client/world.json'
        raw = old(ROOT,relative); world = json.loads(raw)
        changes = {n['objectId']:g for g in groups for n in g['nodes']}
        targets = {n['objectId']:n for g in groups for n in g['nodes']}
        names = {g['id']:g['name'] for g in world.get('harvestGroupings',[])}
        names.update({g['grouping']:g['name'] for g in groups})
        for node in world['harvestables']:
            if node['objectId'] not in changes: continue
            group = changes[node['objectId']]; target = targets[node['objectId']]
            require(node['resource'] == group['previousResource'] and node['serverTile'] == target['tile']
                    and node['position'] == target['position'], 'Node identity/position differs from reviewed plan')
            node['resource'] = group['resource']
            # Preserve all pick dimensions/yaw and use a compact clump in place of the old patch.
            if region != 'landfall_insides': node['grouping'] = group['grouping']
        if region != 'landfall_insides':
            # Preserve unaffected group records byte-for-byte in the document.
            rebuilt = {g['id']:g for g in groups_for(world,names)}
            touched = {g['grouping'] for g in groups}
            old_world = json.loads(raw)
            touched.update(n.get('grouping') for n in old_world['harvestables'] if n['objectId'] in changes)
            untouched = [g for g in world.get('harvestGroupings',[]) if g['id'] not in touched]
            world['harvestGroupings'] = sorted(untouched+[g for k,g in rebuilt.items() if k in touched],key=lambda g:g['id'])
            scene_relative=f'godot-client/world_authoring/regions/{region}/{region}.tscn'
            source=scene_change(old(ROOT,scene_relative),changes)
            write(ROOT,scene_relative,source)
            per_map=dict(receipt, sourceSceneSha256=sha(source), baseSceneSha256=sha(old(ROOT,scene_relative)))
            pub_relative=f'{V2}/{region}/client/publication.json'
            pub=document(ROOT,pub_relative);pub[KEY]=[per_map];write(ROOT,pub_relative,pub)
        else:
            per_map=dict(receipt,sourceSha256=sha(underground))
            world['provenance']['sourceSha256']=sha(underground)
        world['provenance'][KEY]=[per_map]
        encoded=encode(world,raw);write(ROOT,relative,encoded)
        # Harvest art is dynamic: retain backgrounds only after proving every other input and image.
        picture=catalog['maps'][region]
        require(picture['sourceInputs'][relative]==sha(raw),'Background source baseline differs')
        for source,digest in picture['sourceInputs'].items():
            if source!=relative: require(sha((ROOT/source).read_bytes())==digest,f'Static input differs: {source}')
        images=picture.get('sections',{}).values() if picture.get('sectioned') else [picture]
        for image in images:
            image_path=(ROOT/'godot-client'/image['path'].removeprefix('res://')).resolve()
            require(sha(image_path.read_bytes())==image['sha256'],'Background image differs')
        picture['sourceInputs'][relative]=sha(encoded)
        if region=='landfall_insides':
            for entry in (record['interiors'][region],manifest['continentV2']['interiorMaps'][region]):
                entry['sourceSha256']=sha(underground);entry['manifestSha256']=sha(encoded)
    scenery_relative='godot-client/data/world/underground-scenery.json'
    scenery=document(ROOT,scenery_relative);scenery['sourcePlanSha256']=sha(underground)
    for group in by_map['landfall_insides']:
        for node in group['nodes']:
            hint=scenery['harvestPresentation'][str(node['objectId'])]
            require(hint['resource']==group['previousResource'],'Scenery presentation differs')
            hint['resource']=group['resource']
    write(ROOT,scenery_relative,scenery)
    tables_relative=V2+'/_continent_v2/content/server-tables.json'
    tables=document(ROOT,tables_relative)
    require(not {r['name'] for r in tables['resources']} & {r['name'] for r in plan['resources']},'Resource already defined')
    tables['resources'].extend(copy.deepcopy(plan['resources']))
    policy_path = server/'config/eloria/harvest_levels.json'
    if policy_path.exists():
        watched[policy_path] = policy_path.read_bytes()
        policy = json.loads(watched[policy_path])
        require(policy.get('schema') == 'rabbitlands-harvest-levels-v1', 'Unknown harvest level policy')
        levels = policy['levels']
        base_path = server/'config/eloria/harvesting.txt'
        watched[base_path] = base_path.read_bytes()
        base_levels = {row.split('|')[1].strip():int(row.split('|')[2])
                       for row in watched[base_path].decode().splitlines() if row.startswith('resource |')}
        require(set(levels) == set(base_levels) | {r['name'] for r in tables['resources']}, 'Harvest policy must cover every resource exactly')
        require(all(type(v) is int and 0 <= v <= 179 for v in levels.values()), 'Invalid recommended level')
        require(all(levels[n] == v for n,v in base_levels.items()), 'Apply the approved base harvest levels first')
        for resource in tables['resources']: resource['level'] = levels[resource['name']]
        policy_record = dict(path=policy_path.relative_to(server).as_posix(),sha256=sha(watched[policy_path]))
        manifest['continentV2']['harvestLevelPolicy'] = record['harvestLevelPolicy'] = policy_record
    write(ROOT,tables_relative,tables)
    # Keep the publisher input digest current; geometry bake identities are retained.
    record['inputs']['contentTables'][tables_relative]=sha(updates[ROOT/tables_relative])
    harvest_relative='config/eloria/continent-v2/harvesting.txt'
    harvest=old(server,harvest_relative).decode();newline='\r\n' if '\r\n' in harvest else '\n'
    resources=''.join(f'resource | {r["name"]} | {r["level"]} | {r["experience"]} | {r["seconds"]} | {r["tool"]}{newline}' for r in plan['resources'])
    where=harvest.index('node |');harvest=harvest[:where]+resources+harvest[where:]
    table_levels = {r['name']:r['level'] for r in tables['resources']}
    def level_row(match):
        return match[1] + str(table_levels[match[2].strip()])
    harvest = re.sub(r'(?m)^(resource\s*\|\s*([^|]+)\|\s*)\d+(?=\s*\|)', level_row, harvest)
    for group in plan['groups']:
        for node in group['nodes']:
            prefix=f'node | {group["map"]} | {node["objectId"]} | {node["tile"][0]} | {node["tile"][1]} | '
            require(harvest.count(prefix+group['previousResource']+newline)==1,f'Server node differs: {prefix}{group["previousResource"]}')
            harvest=harvest.replace(prefix+group['previousResource']+newline,prefix+group['resource']+newline,1)
    write(server,harvest_relative,harvest.encode())
    digest=sha(harvest.encode())
    manifest['continentV2']['overlay']['files']['harvesting.txt']=record['server']['overlay']['harvesting.txt']=digest
    manifest['continentV2'][KEY]=record[KEY]=[receipt]
    for stage,item in record['server']['stages'].items():
        value={k:copy.deepcopy(v) for k,v in manifest['continentV2'].items() if k in P.OWNED_BLOCK_KEYS}
        value['stage']=stage
        value['overlay']['files']={name:record['server']['overlay'][name] for name in item['files']}
        item.pop('sha256',None);item['manifestBlockSha256']=sha(json.dumps(value,sort_keys=True).encode())
    write(ROOT,catalog_relative,catalog);write(ROOT,record_relative,record);write(server,manifest_relative,manifest)
    # Do all preparation before writes. Only the baseline or this exact result is accepted.
    for path,data in updates.items():
        if path == server/manifest_relative:
            # Independent manifest authors may update unowned catalogue fields.
            # A baseline continentV2 block or this exact result is still required.
            require(json.loads(watched[path])['continentV2'] in
                    (pinned_manifest['continentV2'],json.loads(data)['continentV2']),f'Unrelated continent publication change: {path}')
            continue
        require(watched[path] in (old(ROOT if path.is_relative_to(ROOT) else server,
            path.relative_to(ROOT if path.is_relative_to(ROOT) else server).as_posix()),data),f'Unrelated change: {path}')
    return updates,watched


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--server',required=True,type=Path)
    mode=parser.add_mutually_exclusive_group(required=True)
    mode.add_argument('--apply',action='store_true');mode.add_argument('--check',action='store_true')
    args=parser.parse_args();updates,watched=prepare(args.server.resolve())
    different=[str(p) for p,b in updates.items() if p.read_bytes()!=b]
    if args.apply:
        require(all(p.read_bytes()==b for p,b in watched.items()),'A watched input changed before publication')
        for path,data in updates.items(): path.write_bytes(data)
    print(json.dumps(dict(mode='check' if args.check else 'apply',files=different),indent=2))
    return int(args.check and bool(different))


if __name__=='__main__': raise SystemExit(main())
