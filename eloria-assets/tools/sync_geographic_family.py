"""Synchronize served room returns after exterior grid publication.

This tool edits client metadata only. The default is a dry run; --apply checks
all inputs before replacing any manifest. Local room tiles and world-space
positions are not grid coordinates. Native sources remain unchanged.
"""
from __future__ import annotations

import argparse
import copy
import json
import math
from pathlib import Path

from publish_continent_geography import (CLIENT, GEOGRAPHY, apply_plan, digest,
                                        json_bytes, map_axis, native_mapper)

LEDGER = 'geographicFamily'
TILE_FIELDS = {'destinationTile': ('destinationMap', 'destination', 'targetMap'),
               'targetTile': ('targetMap', 'destinationMap'),
               'returnTile': ('returnMap', 'exitMap', 'exit_map'),
               'exitTile': ('exitMap', 'exit_map', 'returnMap')}
WORLD_FIELDS = {'targetPosition': ('targetMap', 'destinationMap'),
                'destinationPosition': ('destinationMap', 'targetMap'),
                'returnPosition': ('returnMap', 'exitMap')}


def read(path):
    return json.loads(path.read_text(encoding='utf-8'))


def resolve(registry, identity):
    seen = set()
    while registry.get(identity, {}).get('alias'):
        if identity in seen:
            raise ValueError(f'Registry alias cycle at {identity}')
        seen.add(identity)
        identity = registry[identity]['alias']
    return identity


def family(client, server, regions):
    """Return every actually served ID, retaining shared-package gauntlet IDs."""
    registry = read(client / 'godot-client/data/maps/registry.json')['maps']
    served = {fields[1].strip() for line in
              (server / 'config/eloria/maps.txt').read_text(encoding='utf-8').splitlines()
              if len(fields := line.split('|')) >= 2 and fields[0].strip() == 'map'}
    selected = set(regions)
    result = {}
    for identity in sorted(served):
        canonical = resolve(registry, identity)
        entry = registry.get(canonical, {})
        owner = resolve(registry, entry.get('interiorOf', canonical))
        if owner not in selected:
            continue
        if not entry.get('manifest'):
            raise ValueError(f'Served family map {identity} has no client manifest')
        path = (client / 'godot-client' / entry['manifest'].removeprefix('res://')).resolve()
        if not path.is_relative_to(client.resolve()):
            raise ValueError(f'Manifest escapes client checkout: {path}')
        if not path.is_file():
            raise ValueError(f'Missing served family manifest: {path}')
        result[identity] = {'owner': owner, 'canonical': canonical, 'path': path}
    missing = selected - result.keys()
    if missing:
        raise ValueError(f'Selected exteriors are not served: {sorted(missing)}')
    return result


def family_ids(client, server, regions):
    return tuple(family(Path(client), Path(server), regions))


def world_tile(position, transform):
    x, _, z = position
    scale = transform.get('metresPerTile', 1)
    origin = transform['serverOrigin']
    local = transform.get('origin', [0, 0, 0])
    return [round(origin[0] + (x-local[0])/scale),
            round(origin[1] + (-1 if transform.get('invertServerY', True) else 1)*(z-local[2])/scale)]


def sync_sun_returns(room, exterior):
    """Derive the actual outward mouth normal; never assume origin 116."""
    doors = {p['id']: p for p in exterior.get('portals', [])}
    mapping = {'sunmane_wind_caves': 'cave-wind_caves',
               'sunmane_crystal_hollow': 'cave-crystal_hollow'}
    for section in room.get('sections', []):
        if section.get('id') not in mapping:
            continue
        door = doors[mapping[section['id']]]
        x, height, z = door['position']
        px, _, pz = door['propPosition']
        length = math.hypot(x-px, z-pz)
        if length < .01:
            raise ValueError(f"Sunmane mouth {door['id']} has no outward normal")
        tile = world_tile([x+(x-px)/length*3, height, z+(z-pz)/length*3],
                          exterior['coordinateTransform'])
        section.update(returnMap='sunmane_steppe', returnTile=tile)
        exits = [p for p in room.get('portals', []) if
                 p.get('section') == section['id'] or p.get('id') == 'exit-'+section.get('spawn', '')]
        if not exits:
            raise ValueError(f"Sunmane section {section['id']} has no return portal")
        for portal in exits:
            portal.update(destinationMap='sunmane_steppe', destinationTile=list(tile))


def restate_returns(manifest, specs, registry, migrations):
    """Only explicitly destination-owned coordinates are moved.

    Each field keeps its authored native value and last output. A fresh source
    build drops the ledger. An edited field becomes a new authored input, while
    unchanged output can be republished with another origin without accumulating
    deltas. Section exit `tile` and portal `serverTile` always belong to the room.
    """
    previous = manifest.get(LEDGER, {}).get('fields', {})
    records = {}

    def walk(obj, path=''):
        if isinstance(obj, list):
            for i, value in enumerate(obj):
                walk(value, path+'/'+str(i))
        elif isinstance(obj, dict):
            for key, value in list(obj.items()):
                if key == LEDGER:
                    continue
                at = path+'/'+key
                candidates = TILE_FIELDS.get(key, WORLD_FIELDS.get(key))
                target = next((obj[k] for k in candidates or () if k in obj), None)
                target = resolve(registry, target) if target else None
                if target in specs and isinstance(value, list):
                    if key in WORLD_FIELDS and target not in migrations:
                        continue  # Translation of an address grid cannot move a world target.
                    old = previous.get(at, {})
                    baseline = copy.deepcopy(old['native'] if old.get('published') == value
                                             and old.get('map') == target else value)
                    migration = migrations.get(target)
                    native = copy.deepcopy(baseline)
                    if migration:
                        if key in TILE_FIELDS:
                            native = native_mapper(migration, migration['legacyOrigin'])(native)
                        else:
                            native = [map_axis(native[0], migration['axes']['x']), native[1],
                                      map_axis(native[2], migration['axes']['z'])]
                    if key in TILE_FIELDS:
                        spec = specs[target]
                        value = [native[i]+spec['serverOrigin'][i]-spec['nativeServerOrigin'][i]
                                 for i in (0, 1)]
                    else:
                        value = native
                    obj[key] = value
                    records[at] = {'map': target, 'native': baseline, 'published': copy.deepcopy(value)}
                else:
                    walk(value, at)
    walk(manifest)
    return records


def sync_family(client=CLIENT, server=None, regions=None, geography=GEOGRAPHY, *, apply=False,
                require_built=True):
    client, server, geography = Path(client).resolve(), Path(server).resolve(), Path(geography).resolve()
    raw = geography.read_bytes()
    plan = json.loads(raw)
    regions = regions or list(plan['regions'])
    members = family(client, server, regions)
    registry_path = client/'godot-client/data/maps/registry.json'
    registry = read(registry_path)['maps']
    before = {geography: raw, registry_path: registry_path.read_bytes(),
              server/'config/eloria/maps.txt': (server/'config/eloria/maps.txt').read_bytes()}
    pending, exteriors, migrations = {}, {}, {}
    # Cross-family exits can target an exterior outside a scoped rebuild.
    for region, spec in plan['regions'].items():
        canonical = resolve(registry, region)
        path = (client/'godot-client'/registry[canonical]['manifest'].removeprefix('res://')).resolve()
        before[path] = path.read_bytes()
        exterior = json.loads(before[path])
        if require_built and region in regions:
            if exterior.get('continentGeography', {}).get('geographySha256') != digest(raw):
                raise ValueError(f'{region}: final expanded geography metadata is not ready')
            if exterior['coordinateTransform']['serverOrigin'] != spec['serverOrigin']:
                raise ValueError(f'{region}: exterior origin does not match geographic contract')
        exteriors[region] = exterior
        source = path.parent/'source/continent-migration.json'
        if source.is_file():
            before[source] = source.read_bytes()
            migration = json.loads(before[source])
            if require_built and not migration.get('ready'):
                raise ValueError(f'{region}: native coordinate mapping is not ready')
            migrations[region] = migration
    files = []
    for path in sorted({m['path'] for m in members.values()}):
        identities = [k for k, v in members.items() if v['path'] == path]
        if any(k in plan['regions'] for k in identities):
            continue  # Exterior expansion already owns its marker frame.
        before[path] = path.read_bytes()
        manifest = json.loads(before[path])
        records = restate_returns(manifest, plan['regions'], registry, migrations)
        if 'sunmane_wind_caves' in identities:
            sync_sun_returns(manifest, exteriors['sunmane_steppe'])
            # The freshly derived posts are already in the current frame.
            for at, record in records.items():
                if record['map'] == 'sunmane_steppe':
                    obj = manifest
                    for component in at.strip('/').split('/'):
                        obj = obj[int(component)] if isinstance(obj, list) else obj[component]
                    delta = plan['regions']['sunmane_steppe']['serverTileShift']
                    record.update(native=[obj[i]-delta[i] for i in (0, 1)], published=list(obj))
        if records:
            manifest[LEDGER] = {'schemaVersion': 1, 'geographySha256': digest(raw), 'fields': records}
        payload = json_bytes(manifest)
        # Do not normalize or tag metadata which has no affected references.
        changed = manifest != json.loads(before[path])
        if changed:
            pending[path] = payload
        files.append({'maps': identities, 'manifest': str(path.relative_to(client)),
                      'changed': changed, 'explicitReturns': len(records)})
    if apply:
        apply_plan(before, pending)
    return {'family': list(members), 'uniquePackages': len({m['path'] for m in members.values()}),
            'changedFiles': len(pending), 'files': files}


LOD_CONTENT = ('coordinateTransform', 'contentLayout', 'runtimePopulation', 'npcMarkers',
               'harvestables', 'interactives', 'spawns', 'spawnPoints', 'portals',
               'landmarks', 'ambientPopulation', 'minimap', 'landscapeRevision', 'bounds')


def sync_lods(client=CLIENT, server=None, regions=None, geography=GEOGRAPHY, *, apply=False):
    """Copy final authoritative metadata after roster publication, before digests.

    Geometry-specific LOD nodes, navigation, materials and statistics are kept.
    Main metadata is already in its served frame, so sidecars are not remapped.
    """
    client, server = Path(client).resolve(), Path(server).resolve()
    members = family(client, server, regions or list(read(Path(geography))['regions']))
    before, pending, files = {}, {}, []
    for main_path in sorted({m['path'] for m in members.values()}):
        path = main_path.with_name('world-lod2.json')
        if not path.is_file():
            continue
        before[main_path], before[path] = main_path.read_bytes(), path.read_bytes()
        main, lod = json.loads(before[main_path]), json.loads(before[path])
        for key in LOD_CONTENT:
            if key in main:
                lod[key] = copy.deepcopy(main[key])
        for key in ('serverCells', 'regionSpanMeters', 'mapBounds'):
            if key in main['asset']:
                lod['asset'][key] = copy.deepcopy(main['asset'][key])
        nodes = lod.get('collision', {}).get('nodeNames')
        lod['collision'] = copy.deepcopy(main['collision'])
        if nodes is not None:
            lod['collision']['nodeNames'] = nodes
        if 'continentGeography' in main:
            lod['continentGeography'] = copy.deepcopy(main['continentGeography'])
            glb = path.parent/lod['asset']['glb']
            before[glb] = glb.read_bytes()
            lod['continentGeography'].update(geometrySha256=digest(before[glb]), collisionGeometry=main['asset']['glb'])
        if lod != json.loads(before[path]):
            pending[path] = json_bytes(lod)
        files.append(str(path.relative_to(client)))
    if apply:
        apply_plan(before, pending)
    return {'changedFiles': len(pending), 'lodManifests': files}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--client', type=Path, default=CLIENT)
    parser.add_argument('--server', type=Path, required=True)
    parser.add_argument('--geography', type=Path, default=GEOGRAPHY)
    parser.add_argument('--region', action='append')
    parser.add_argument('--lod-only', action='store_true')
    modes = parser.add_mutually_exclusive_group()
    modes.add_argument('--apply', action='store_true')
    modes.add_argument('--check', action='store_true')
    parser.add_argument('--report', type=Path)
    args = parser.parse_args()
    fn = sync_lods if args.lod_only else sync_family
    report = fn(args.client, args.server, args.region, args.geography, apply=args.apply)
    print(json.dumps(report, indent=2))
    if args.report:
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_bytes(json_bytes(report))


if __name__ == '__main__':
    main()
