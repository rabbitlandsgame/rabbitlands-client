"""Publish added NPC markers when the baked geometry is byte-for-byte unchanged.

The base bake must be the currently certified package. Every exported field
except NPC markers and the two source records must match. Existing NPCs cannot
move or change. Collision binaries are checked and preserved; a receipt records
why their original export remains valid for the new snapshot. With --server,
the added posts and their approach rings are checked against the server's actual
served grid, without republishing unrelated spawn or collision work.
"""
from __future__ import annotations

import argparse
import copy
import hashlib
import json
from pathlib import Path
import sys

HERE = Path(__file__).resolve().parent
CHECKOUT = HERE.parents[3]


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def invariant(document: dict) -> dict:
    value = copy.deepcopy(document)
    value.pop('sources')
    value['gameplay'].pop('npcMarkers')
    return value


def receipt(base: dict, current: dict, base_sha: str, current_sha: str) -> dict:
    if base['regionId'] != current['regionId'] or invariant(base) != invariant(current):
        raise ValueError('Geometry or non-NPC gameplay changed: use the full publication pipeline.')
    before, after = base['sources'], current['sources']
    if (before.keys() != after.keys()
            or any(before[key] != after[key] for key in before if key not in ('scene', 'authoringSpec'))
            or any(before[key]['path'] != after[key]['path'] for key in ('scene', 'authoringSpec'))):
        raise ValueError('Source dependencies changed: use the full publication pipeline.')
    old = {mark['id']: mark for mark in base['gameplay']['npcMarkers']}
    new = {mark['id']: mark for mark in current['gameplay']['npcMarkers']}
    if len(old) != len(base['gameplay']['npcMarkers']) or len(new) != len(current['gameplay']['npcMarkers']):
        raise ValueError('Duplicate NPC marker ids.')
    if not old.keys() < new.keys() or any(new.get(key) != value for key, value in old.items()):
        raise ValueError('Only additional NPC markers are supported; existing posts must stay identical.')
    return {
        'tool': 'eloria-assets/maps/continent-v2/_continent_v2/publish_npc_metadata.py',
        'region': current['regionId'], 'baseSnapshotSha256': base_sha,
        'snapshotSha256': current_sha, 'sceneSha256': current['sources']['scene']['sha256'],
        'unchangedContentSha256': digest(json.dumps(invariant(base), sort_keys=True,
                                                  separators=(',', ':')).encode()),
        'addedNpcMarkers': sorted(new.keys() - old.keys()),
        'preserved': ['geometry', 'terrain', 'paths', 'collision.bin', 'served-grid.escg.gz'],
    }


def read(path: Path) -> dict:
    return json.loads(path.read_text(encoding='utf-8'))


def append_receipt(container: dict, entry: dict) -> None:
    amendments = container.setdefault('npcMetadataAmendments', [])
    if entry not in amendments:
        amendments.append(entry)


def prepare(checkout: Path, base_path: Path, current_path: Path) -> dict[Path, dict]:
    base, current = read(base_path), read(current_path)
    old_sha, new_sha = digest(base_path.read_bytes()), digest(current_path.read_bytes())
    entry = receipt(base, current, old_sha, new_sha)
    region = current['regionId']
    for key in ('scene', 'authoringSpec'):
        source = current['sources'][key]
        if digest((checkout / source['path']).read_bytes()) != source['sha256']:
            raise ValueError(f'{key} changed since the new bake.')
    packages = checkout / 'eloria-assets/maps/continent-v2'
    target = read(packages / region / 'client/world.json')
    if (target['provenance']['snapshotSha256'] not in (old_sha, new_sha)
            or target['collision']['sourceSnapshotSha256'] not in (old_sha, new_sha)):
        raise ValueError('The base bake is not the currently certified package.')
    updates = {}
    # Group exports name every member's snapshot. Keep every package's group
    # record in agreement, even though their geometry and binaries are unchanged.
    for path in sorted(packages.glob('*/client/world.json')):
        manifest = read(path)
        collision = manifest.get('collision', {})
        group = collision.get('groupExport', {}).get('maps', {})
        if region not in group:
            continue
        if group[region]['snapshotSha256'] not in (old_sha, new_sha):
            raise ValueError(f'{path}: group export names an unrelated source snapshot.')
        for binary, expected in ((collision['binary'], collision['sha256']),
                                 (collision['servedGrid']['binary'], collision['servedGrid']['sha256'])):
            if digest((path.parent / binary).read_bytes()) != expected:
                raise ValueError(f'{path}: certified binary changed: {binary}')
        group[region]['snapshotSha256'] = new_sha
        append_receipt(collision, entry)
        publication_path = path.parent / 'publication.json'
        publication = read(publication_path)
        append_receipt(publication['collision'], entry)
        if path.parent.parent.name == region:
            manifest['provenance'].update(snapshotSha256=new_sha, sceneSha256=entry['sceneSha256'])
            append_receipt(manifest['provenance'], entry)
            collision.update(sourceSnapshotSha256=new_sha, sourceSceneSha256=entry['sceneSha256'])
            # publish_client.py's rows (map_categories.py): an unknown category is refused, never dropped.
            import map_categories
            manifest['serviceMarkers'] = map_categories.service_markers(current['gameplay']['npcMarkers'])
            publication['snapshot'].update(sha256=new_sha, sceneSha256=entry['sceneSha256'])
            publication['collision']['sourceSnapshotSha256'] = new_sha
        updates[path] = manifest
        updates[publication_path] = publication
    if not updates:
        raise ValueError('No certified packages matched the requested region.')
    return updates


def prepare_server(checkout: Path, server: Path, base_path: Path,
                   current_path: Path) -> tuple[dict[Path, dict], dict[Path, bytes]]:
    """Add only the new NPC rows, checking the server's actual currently served grid.

    Other in-progress spawn, harvest and collision work is outside this update.
    Blocking the new post must not make any formerly reachable ground unreachable.
    """
    import numpy as np
    import frames
    import publish_server as publisher
    sys.path.insert(0, str(server))
    from eloria.served_grid import decode_file
    from eloria.npcs import load_npcs
    from eloria.interactives import load_interactives
    from eloria.shops import load_shops

    base, current = read(base_path), read(current_path)
    proof = receipt(base, current, digest(base_path.read_bytes()), digest(current_path.read_bytes()))
    region = current['regionId']
    frame = frames.load(region, checkout)
    marker_table = {mark['id']: mark for mark in current['gameplay']['npcMarkers']}
    rows_path = checkout / 'eloria-assets/maps/continent-v2/_continent_v2/content/server-rows.json'
    entries = read(rows_path)['maps'][region]['npcs']
    profile = server / 'config/eloria'
    npc_path = profile / 'continent-v2/npcs.txt'
    people = load_npcs(npc_path, overlay=False)
    homes = load_npcs(profile / 'continent-v2/home_npcs.txt', overlay=False)
    grid_path = server / 'tools/collision' / f'{region}.escg.gz'
    grid_bytes = grid_path.read_bytes()
    grid = decode_file(grid_bytes)
    storage = { (obj.x, obj.y) for obj in load_interactives(
        profile / 'continent-v2/interactives.txt', overlay=False).values()
        if obj.map_id == region and obj.role == 'storage' }
    codes, _ground = publisher.eroded_codes(region, {'grid': grid}, storage)
    manifest_path = profile / 'client_content_manifest.json'
    server_manifest = read(manifest_path)
    arrival = server_manifest['continentV2']['maps'][region]['arrival']
    rows, new_posts, names = [], [], set()
    shops = load_shops(profile / 'shops.txt')
    existing_lines = npc_path.read_text(encoding='utf-8').splitlines()
    for identity in proof['addedNpcMarkers']:
        mark, entry = marker_table[identity], entries[identity]
        name = publisher.plain_field(entry['name'], identity)
        if name.casefold() in names:
            raise ValueError(f'{name}: duplicate new NPC name.')
        tile = list(frame.tile(mark['position'][0], mark['position'][2]))
        body = entry['actorType']
        block = mark.get('actorTypeBlock', [])
        if (tile != mark['serverTile'] or name != mark['name'] or entry['group'] != 'new'
                or not (mark.get('actorType') == body or len(block) == 2 and block[0] <= body <= block[1])):
            raise ValueError(f'{identity}: NPC table and authored marker disagree.')
        if entry['role'] == 'shop' and name.casefold() not in shops:
            raise ValueError(f'{name}: a shop NPC needs shop stock.')
        occupation = publisher.occupation_field(mark.get('occupation'), name, identity)
        portrait = publisher.npc_portrait(body, occupation, publisher.npc_facing(mark))
        line = ' | '.join(['npc', name, region, *map(str, tile), entry['role'], portrait,
                           publisher.plain_field(entry['greeting'], identity)])
        matching = [p for p in people if p.name.casefold() == name.casefold()]
        if matching and line not in existing_lines:
            raise ValueError(f'{name}: an existing NPC already uses this name differently.')
        if any(p.name.casefold() == name.casefold() for p in homes):
            raise ValueError(f'{name}: a home NPC already uses this name.')
        rows.append(line)
        new_posts.append(tile)
        names.add(name.casefold())
    if len({tuple(tile) for tile in new_posts}) != len(new_posts):
        raise ValueError('Two new NPC posts share a tile.')
    old_walk = codes.copy()
    for person in (*people, *homes):
        if person.map_id == region and person.name.casefold() not in names:
            old_walk[person.y, person.x] = 0
    new_walk = old_walk.copy()
    for x, y in new_posts:
        if not frame.contains(x, y) or not codes[y, x] or not old_walk[y, x]:
            raise ValueError(f'NPC post {(x, y)} is blocked or occupied.')
        new_walk[y, x] = 0
    old_reach = publisher.union_reach({region: old_walk}, {region: arrival}, [], grid.climb_units)[region]
    new_reach = publisher.union_reach({region: new_walk}, {region: arrival}, [], grid.climb_units)[region]
    lost = old_reach & ~new_reach
    for x, y in new_posts:
        lost[y, x] = False
    if lost.any():
        raise ValueError(f'The NPC would disconnect {int(lost.sum())} reachable tiles.')
    package = read(checkout / f'eloria-assets/maps/continent-v2/{region}/client/world.json')
    checker = publisher.Checker({region: new_walk}, {region: new_reach}, {region: frame},
                               {region: package['continentGeography']['ownershipPolygon']},
                               ground={region: codes})
    for tile, line in zip(new_posts, rows):
        checker.ring(region, tile, 'npc', line.split(' | ')[1], post=True)
    if checker.failures:
        raise ValueError(f'NPC approach failed: {checker.failures}')
    text = npc_path.read_bytes()
    missing = [line for line in rows if line not in existing_lines]
    if missing:
        newline = '\r\n' if b'\r\n' in text else '\n'
        text += ((newline if not text.endswith(b'\n') else '') + newline.join(missing) + newline).encode('utf-8')
    served_proof = {**proof, 'scope': 'added NPC rows only', 'servedGridSha256': digest(grid_bytes),
                    'npcTableSha256': digest(text), 'approachRings': 'all open and reached',
                    'otherReachableTilesLost': 0}
    overlay = server_manifest['continentV2']
    append_receipt(overlay, served_proof)
    overlay['overlay']['files']['npcs.txt'] = digest(text)
    overlay['rowCounts']['newNpcs'] = sum(line.startswith('npc |') for line in text.decode('utf-8').splitlines())
    record_path = checkout / 'eloria-assets/maps/continent-v2/_continent_v2/publication.json'
    record = read(record_path)
    append_receipt(record, served_proof)
    record['maps'][region]['bake'].update(snapshotSha256=proof['snapshotSha256'],
                                          sceneSha256=proof['sceneSha256'])
    record['maps'][region]['rows']['npcs'] = sum(e['group'] == 'new' for e in entries.values())
    record['maps'][region]['npcPosts'] = len(entries)
    record['server']['overlay']['npcs.txt'] = digest(text)
    relative_rows = rows_path.relative_to(checkout).as_posix()
    record['inputs']['contentTables'][relative_rows] = digest(rows_path.read_bytes())
    return {manifest_path: server_manifest, record_path: record}, {npc_path: text}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--base-bake', required=True, type=Path)
    parser.add_argument('--snapshot', required=True, type=Path)
    parser.add_argument('--checkout', type=Path, default=CHECKOUT)
    parser.add_argument('--server', type=Path, help='also append and validate the added NPCs in this server checkout')
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument('--apply', action='store_true')
    mode.add_argument('--check', action='store_true')
    args = parser.parse_args()
    updates = prepare(args.checkout, args.base_bake, args.snapshot)
    package_count = len(updates) // 2
    binary_updates = {}
    if args.server:
        server_updates, binary_updates = prepare_server(args.checkout, args.server,
                                                        args.base_bake, args.snapshot)
        updates.update(server_updates)
    differences = []
    for path, document in updates.items():
        if read(path) == document:
            continue
        if args.apply:
            indent = 2 if path.name == 'client_content_manifest.json' else 1
            newline = '\r\n' if b'\r\n' in path.read_bytes() else '\n'
            path.write_bytes((json.dumps(document, indent=indent, ensure_ascii=False) + '\n').replace('\n', newline).encode('utf-8'))
        else:
            differences.append(str(path))
    for path, data in binary_updates.items():
        if path.read_bytes() != data:
            if args.apply:
                path.write_bytes(data)
            else:
                differences.append(str(path))
    print(json.dumps({'mode': 'apply' if args.apply else 'check', 'packages': package_count,
                      'serverNpcs': bool(args.server),
                      'differences': differences, 'collisionBinaries': 'verified and unchanged'}, indent=2))
    return int(bool(differences))


if __name__ == '__main__':
    raise SystemExit(main())
