"""Add the Lakehead shoreline patches without rebuilding certified map geometry.

Only the pinned source scene plus the seven planned markers may change. Every
node must already have all four half-cells closed, on both the current client
and the independently sealed server grid. Production harvesting approach and
road checks run before writing. Existing geometry, collision and boats retain
their original hashes; a source amendment records the additional markers.
Run with --base-bake DIR --server CHECKOUT --apply, then --check.
"""
from __future__ import annotations

import argparse
import copy
import hashlib
import json
from pathlib import Path
import struct
import sys

import numpy as np
import frames
import harvest_presentation as HP
import publish_server as P

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[3]
PLAN = HERE / 'content/reedfall-lakehead-resources.json'
KEY = 'shoreResourceAmendments'


def sha(data):
    return hashlib.sha256(data).hexdigest()


def require(condition, message):
    if not condition:
        raise ValueError(message)


def read(path):
    return json.loads(path.read_bytes())


def serialise(value, original, indent=1):
    result = (json.dumps(value, ensure_ascii=False, indent=indent) + '\n').encode()
    return result.replace(b'\n', b'\r\n') if b'\r\n' in original else result


def prepare(server, base_bake):
    sys.path.insert(0, str(server))
    from eloria.served_grid import decode_file
    from eloria.harvesting import load_harvesting
    from eloria.interactives import load_interactives
    from eloria.npcs import load_npcs

    plan, base = read(PLAN), read(base_bake / 'continent-authoring.json')
    region = plan['region']
    frame = frames.load(region, ROOT)
    package = ROOT / f'eloria-assets/maps/continent-v2/{region}/client'
    scene = ROOT / base['sources']['scene']['path']
    spec_path = ROOT / base['sources']['authoringSpec']['path']
    world_path, publication_path = package / 'world.json', package / 'publication.json'
    world, publication = read(world_path), read(publication_path)
    scene_bytes = scene.read_bytes()
    # The appended source block is deterministic; removing it recovers the exact
    # pinned original, including its line endings, for an idempotent check.
    boundary = b'\n[node name="reedfall--harvest-2140-kelp"'
    original_scene = scene_bytes.split(boundary)[0] if boundary in scene_bytes else scene_bytes
    require(sha(original_scene) == plan['baseSceneSha256'] == base['sources']['scene']['sha256'],
            'Source scene changed outside the planned additions.')
    require(sha((base_bake / 'continent-authoring.json').read_bytes()) == world['provenance']['snapshotSha256'],
            'Base bake is not the certified Reedfall package.')
    heights_path = base_bake / base['terrain']['resolvedHeights']['path']
    require(sha(heights_path.read_bytes()) == base['terrain']['resolvedHeights']['sha256'], 'Terrain hash differs.')
    terrain = base['terrain']
    heights = np.fromfile(heights_path, dtype='<f4').reshape(terrain['height'], terrain['width'])
    additions, blocks = [], []
    for group in plan['groups']:
        for index, (oid, tx, ty) in enumerate(group['nodes']):
            x, z = frame.local(tx, ty)
            col, row = [(v - terrain['origin'][i]) / terrain['cellMetres'] for i, v in enumerate((x, z))]
            ix, iy = int(col), int(row)
            fx, fy = col - ix, row - iy
            h = ((1-fy)*((1-fx)*heights[iy, ix]+fx*heights[iy, ix+1])
                 + fy*((1-fx)*heights[iy+1, ix]+fx*heights[iy+1, ix+1]))
            water = [w for w in base['waterRegions'] if w['shape'] == 'ellipse' and
                     sum(((v-w['center'][i])/w['radii'][i])**2 for i, v in enumerate((x, z))) <= 1]
            require(water, f'{oid}: outside the authored lake.')
            y = round(max(float(h), max(w['level'] for w in water)) + 0.02, 3)
            identity = f'{region}--harvest-{oid}-{group["resource"].lower()}'
            extras = dict(authority='server', objectId=oid, resource=group['resource'],
                          cluster=group['id'], grouping=group['id'], groupingName=group['name'],
                          footprint=group['footprint'], variant=index, zone='lakehead-shore')
            mark = dict(id=identity, label=group['resource'], position=[x, y, z], serverTile=[tx, ty], **extras)
            additions.append(mark)
            blocks.append(f'\n[node name="{identity}" type="Marker3D" parent="Gameplay/Harvestables"]\n'
                          f'gizmo_extents = 0.8\nscript = ExtResource("s0_marker")\nrecord_id = "{identity}"\n'
                          f'kind = "harvestable"\nlabel = "{group["resource"]}"\n'
                          f'extras = {json.dumps(extras, indent=0)}\n'
                          f'transform = Transform3D(1, 0, 0, 0, 1, 0, 0, 0, 1, {x}, {y}, {z})\n')
    require(len({m['objectId'] for m in additions}) == len(additions), 'Duplicate object IDs.')
    source = original_scene + ''.join(blocks).encode()
    require(scene_bytes in (original_scene, source), 'Unexpected appended source content.')
    spec = read(spec_path)
    count = len(additions)
    base_spec = copy.deepcopy(spec)
    if KEY in publication:
        base_spec['gameplay']['authoredMarkerCount'] -= count
    require(sha(serialise(base_spec, spec_path.read_bytes())) == base['sources']['authoringSpec']['sha256'],
            'Authoring specification changed outside the marker count.')
    spec['gameplay']['authoredMarkerCount'] = base_spec['gameplay']['authoredMarkerCount'] + count
    nodes = [{'id': m['id'], 'tile': m['serverTile']} for m in additions]
    require(not HP.road_offenders(base['paths'], nodes, frame.local), 'A patch overlaps a road.')
    profile = server / 'config/eloria'
    manifest_path = profile / 'client_content_manifest.json'
    manifest = read(manifest_path)
    server_map = manifest['continentV2']['maps'][region]
    resources, served_nodes = load_harvesting(profile / 'harvesting.txt')
    _, overlay_nodes = load_harvesting(profile / 'continent-v2/harvesting.txt', overlay=True)
    served_nodes.update(overlay_nodes)
    interactives = load_interactives(profile / 'continent-v2/interactives.txt', overlay=False)
    people = load_npcs(profile / 'continent-v2/npcs.txt', overlay=False) + load_npcs(profile / 'continent-v2/home_npcs.txt', overlay=False)
    evidence = {}
    for label, path, expected in (
        ('client', package / 'served-grid.escg.gz', world['collision']['servedGrid']['sha256']),
        ('server', server / f'tools/collision/{region}.escg.gz', server_map['servedGridSha256'])):
        data = path.read_bytes()
        require(sha(data) == expected, f'{label}: served grid hash differs.')
        grid = decode_file(data)
        codes, _ = P.eroded_codes(region, {'grid': grid}, set())
        ground = codes.copy()
        for person in people:
            if person.map_id == region:
                codes[person.y, person.x] = 0
        reached = P.union_reach({region: codes}, {region: server_map['arrival']}, [], grid.climb_units)
        checker = P.Checker({region: codes}, reached, {region: frame},
                            {region: world['continentGeography']['ownershipPolygon']}, ground={region: ground})
        for mark in additions:
            tx, ty = mark['serverTile']
            require(not grid.code(tx, ty), f'{label}: {mark["id"]} would change walk collision.')
            require((region, mark['objectId']) not in interactives, 'Object ID already used by an interactive.')
            old = served_nodes.get((region, mark['objectId']))
            require(old is None or (old.x, old.y, old.resource) == (tx, ty, mark['resource']), 'Harvest ID reused.')
            require(not any(n.map_id == region and (n.x, n.y) == (tx, ty) and n.object_id != mark['objectId']
                            for n in served_nodes.values()), 'Occupied harvest tile.')
            checker.node(region, [tx, ty], mark['id'])
        require(not checker.failures, f'{label}: approach failures: {checker.failures}')
        evidence[label] = dict(servedGridSha256=expected, approach='production reach-side checks passed')
    raw = (package / 'collision.bin').read_bytes()
    require(sha(raw) == world['collision']['sha256'], 'Client collision hash differs.')
    magic, version, _, width, height = struct.unpack('<4sHHII', raw[:16])
    require((magic, version, len(raw)) == (b'EWCG', 2, 16+width*height), 'Collision header differs.')
    half = np.frombuffer(raw[16:], dtype=np.uint8).reshape(height, width)
    for mark in additions:
        x, y = mark['serverTile']
        require(not half[2*y:2*y+2, 2*x:2*x+2].any(), 'A new marker changes half-cell collision.')
    receipt = dict(plan=PLAN.relative_to(ROOT).as_posix(), planSha256=sha(PLAN.read_bytes()),
                   baseSceneSha256=plan['baseSceneSha256'], sourceSceneSha256=sha(source),
                   baseSnapshotSha256=world['provenance']['snapshotSha256'],
                   addedNodes=[[m['objectId'], m['resource'], *m['serverTile']] for m in additions],
                   geometry='unchanged', collision='unchanged; nodes occupy existing closed shoreline cells',
                   validation=evidence)
    # Source amendment, deliberately not a new geometry bake or a replacement
    # of the sealed server exterior packages (which predate the current client).
    entries, groups = HP.package_entries(additions, [], frame.origin)
    ids = {e['objectId'] for e in entries}
    old_entries = [e for e in world['harvestables'] if e['objectId'] not in ids]
    require(old_entries == HP.package_entries(base['gameplay']['harvestables'], [], frame.origin)[0], 'Existing harvest metadata differs.')
    world['harvestables'] = sorted(old_entries + entries, key=lambda e: e['objectId'])
    group_ids = {g['id'] for g in groups}
    world['harvestGroupings'] = sorted([g for g in world['harvestGroupings'] if g['id'] not in group_ids] + groups, key=lambda g: g['id'])
    world['provenance'][KEY] = [receipt]
    world_bytes = serialise(world, world_path.read_bytes(), 2)
    # Backgrounds render static chunks; harvest props and map dots are runtime
    # objects. Prove all static inputs and image bytes before retaining them.
    old_world = copy.deepcopy(world)
    old_world['harvestables'] = old_entries
    old_world['harvestGroupings'] = [g for g in world['harvestGroupings'] if g['id'] not in group_ids]
    old_world['provenance'].pop(KEY)
    catalog_path = ROOT / 'godot-client/data/maps/map-backgrounds.json'
    catalog = read(catalog_path)
    picture = catalog['maps'][region]
    world_key = world_path.relative_to(ROOT).as_posix()
    old_world_sha = sha(serialise(old_world, world_path.read_bytes(), 2))
    require(picture['sourceInputs'][world_key] in (old_world_sha, sha(world_bytes)), 'Background baseline differs.')
    for relative, digest in picture['sourceInputs'].items():
        if relative != world_key:
            require(sha((ROOT / relative).read_bytes()) == digest, f'Static render input differs: {relative}')
    image_path = (ROOT / 'godot-client' / picture['path'][6:]).resolve()
    require(sha(image_path.read_bytes()) == picture['sha256'], 'Background image differs.')
    picture['sourceInputs'][world_key] = sha(world_bytes)
    publication[KEY] = [receipt]
    harvest_path = profile / 'continent-v2/harvesting.txt'
    harvest = harvest_path.read_bytes()
    newline = b'\r\n' if b'\r\n' in harvest else b'\n'
    for mark in additions:
        row = f'node | {region} | {mark["objectId"]} | {mark["serverTile"][0]} | {mark["serverTile"][1]} | {mark["resource"]}'.encode()
        if row not in harvest.splitlines():
            harvest += row + newline
    record_path = HERE / 'publication.json'
    record = read(record_path)
    manifest['continentV2'][KEY] = record[KEY] = [receipt]
    manifest['continentV2']['overlay']['files']['harvesting.txt'] = record['server']['overlay']['harvesting.txt'] = sha(harvest)
    record['maps'][region]['rows']['nodes'] = len(world['harvestables'])
    manifest['continentV2']['rowCounts']['nodes'] = sum(l.startswith(b'node |') for l in harvest.splitlines())
    for stage, item in record['server']['stages'].items():
        value = {k: copy.deepcopy(v) for k, v in manifest['continentV2'].items() if k in P.OWNED_BLOCK_KEYS}
        value['stage'] = stage
        value['overlay']['files'] = {name: record['server']['overlay'][name] for name in item['files']}
        item.pop('sha256', None)
        item['manifestBlockSha256'] = sha(json.dumps(value, sort_keys=True).encode())
    return {scene: source, spec_path: serialise(spec, spec_path.read_bytes()),
            world_path: world_bytes,
            catalog_path: serialise(catalog, catalog_path.read_bytes()),
            publication_path: serialise(publication, publication_path.read_bytes()),
            harvest_path: harvest, manifest_path: serialise(manifest, manifest_path.read_bytes(), 2),
            record_path: serialise(record, record_path.read_bytes())}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--server', required=True, type=Path)
    parser.add_argument('--base-bake', required=True, type=Path)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument('--apply', action='store_true')
    mode.add_argument('--check', action='store_true')
    args = parser.parse_args()
    updates = prepare(args.server.resolve(), args.base_bake.resolve())
    differences = [str(p.relative_to(ROOT)) if p.is_relative_to(ROOT) else str(p) for p, b in updates.items() if p.read_bytes() != b]
    if args.apply:
        for path, data in updates.items():
            path.write_bytes(data)
    print(json.dumps(dict(mode='apply' if args.apply else 'check', files=differences), indent=2))
    return int(bool(differences) and args.check)


if __name__ == '__main__':
    raise SystemExit(main())
