"""Rebuild the northern five-map group and publish matching server contracts.

Run with --server <checkout> --data <generated ELM directory>. --skip-build
integrates already reviewed packages; --stage allows a failed contract stage to
be resumed without repeating asset generation. Other regions retain their data.
"""
import argparse
import json
import re
from pathlib import Path
import subprocess
import sys

from legacy_content import read_base_only

CLIENT = Path(__file__).resolve().parents[2]
REGIONS = CLIENT / 'eloria-assets/maps/nymara-regions'
EXTERIORS = ('amberwood', 'whitehorn_range', 'grey_moors', 'mirrorhold', 'amethyst_barrens')
NEW = ('grey_moors', 'mirrorhold', 'amethyst_barrens')
FAMILY = EXTERIORS + ('amberwood_estate', 'whitehorn_glacier_temple',
    'grey_moor_barrows', 'mirrorhold_interiors', 'resonant_vault') + tuple(r+'_secrets' for r in EXTERIORS)


def run(cwd, *args):
    print('RUN', *map(str, args), flush=True)
    subprocess.run([sys.executable, '-u', *map(str, args)], cwd=cwd, check=True)


def collision(server, data, *, family=FAMILY):
    for region in family:
        run(server, server/'tools/sync_authored_collision.py', '--client',
            CLIENT/'eloria-assets/maps', '--region', region)
    run(server, server/'tools/generate_nymara_maps.py', data)


def content(server, data, *, exteriors=EXTERIORS, new=NEW, family=FAMILY):
    for region in exteriors:
        run(CLIENT, CLIENT/'eloria-assets/tools/continent_portals.py', '--server',
            server, '--maps', data, '--region', region, '--apply')
    for region in exteriors:
        run(server, server/'tools/author_region_content.py',
            'all' if region in new else 'services', '--maps', data,
            '--client', CLIENT, '--region', region, '--apply')
    sys.path[:0] = [str(server/'tools'), str(server)]
    import relocate_map_content as relocate
    import sync_authored_collision as collision_publication
    profile = server/'config/eloria'
    maps, portals = relocate.load_maps(profile/'maps.txt')
    cache = {}
    def mask_for(map_id):
        if map_id not in family:
            return None, 0
        if map_id not in cache:
            c = relocate.load_elm_collision(data/maps[map_id].file)
            cache[map_id] = (relocate.standable(c.heights, c.width,
                relocate.arrivals_for(map_id, portals),
                # Guarded decks deliberately cross the final addressable tiles.
                # A generic empty-map margin would move the surveyed handoff.
                margin=0 if collision_publication.strictly_authored(map_id,
                    CLIENT/'eloria-assets/maps') else relocate.MARGIN), c.width)
        return cache[map_id]
    moves, taken, resolved, pending = [], {}, {}, []
    for name in relocate.COORDINATE_FIELDS:
        path = profile/name
        if path.exists():
            original = path.read_bytes()
            text = relocate.rewrite(path, mask_for, moves, taken, resolved)
            pending.append((path, text.replace('\n', '\r\n' if b'\r\n' in original else '\n').encode()))
    print(json.dumps({'relocations': moves}, indent=2), flush=True)
    if any(m[4] is None or max(abs(m[3][i]-m[4][i]) for i in (0, 1)) > 12 for m in moves):
        raise SystemExit('A stranded post needs an authored approach; no relocations written')
    for path, payload in pending:
        if path.read_bytes() != payload:
            path.write_bytes(payload)
    text, _ = relocate.follow_manifest(profile, moves)
    if text is not None:
        (profile/'client_content_manifest.json').write_text(text, encoding='utf-8')
    if 'amberwood' in exteriors:
        run(CLIENT, CLIENT/'eloria-assets/tools/sync_package_content.py', '--manifest',
            profile/'client_content_manifest.json', '--package', 'nymara-regions/amberwood',
            '--write-source-posts', '--apply')


def publish(server, *, exteriors=EXTERIORS, family=FAMILY, before_digests=None):
    sync_instance_returns(server, exteriors=exteriors)
    run(CLIENT, CLIENT/'eloria-assets/tools/publish_northern_content.py', '--server', server,
        *[arg for region in exteriors for arg in ('--region', region)])
    if before_digests is not None:
        before_digests()
    sys.path[:0] = [str(server/'tools'), str(server), str(CLIENT/'eloria-assets/tools')]
    import sync_package_content as packages
    from eloria.maps import load_maps
    from generate_nymara_maps import ARRIVAL_TILES, MAP_TILES_WIDE_BY_NAME
    profile = server/'config/eloria'
    _, portals = load_maps(profile/'maps.txt')
    path = profile/'client_content_manifest.json'
    data = json.loads(path.read_text(encoding='utf-8'))
    registry = packages.registry_packages()
    for region in family:
        if region not in registry or region not in ARRIVAL_TILES or region not in MAP_TILES_WIDE_BY_NAME:
            raise ValueError(f'{region}: served family lacks a complete registry/generator contract')
    existing = {entry['id'] for entry in data['maps']}
    for region in sorted(set(family)-existing):
        manifest = json.loads(registry[region].read_text(encoding='utf-8'))
        data['maps'].append({'id': region, 'coordinateTransform': manifest['coordinateTransform']})
    for entry in data['maps']:
        region = entry['id']
        if region not in family:
            continue
        digest = packages.digest_for(registry[region])
        if not isinstance(digest, str) or len(digest) != 64:
            raise ValueError(f'{region}: served family package is incomplete; cannot publish its digest')
        entry['packageSha256'] = digest
        entry['arrival'] = list(ARRIVAL_TILES[region])
        entry['server_cells'] = MAP_TILES_WIDE_BY_NAME[region]*6
        if 'coordinateTransform' in entry:
            entry['coordinateTransform'] = json.loads(registry[region].read_text(encoding='utf-8'))['coordinateTransform']
        entry['portals'] = [{'server_tile': [p.x, p.y], 'destination': p.destination}
                           for p in portals if p.source == region]
    path.write_text(json.dumps(data, indent=2)+'\n', encoding='utf-8')
    run(CLIENT, CLIENT/'eloria-assets/tools/build_exterior_streaming.py', '--server', server)


def sync_instance_returns(server, *, exteriors=EXTERIORS):
    """Instance completion and bailout use the same surveyed return as portals."""
    sys.path.insert(0, str(server))
    from eloria.maps import load_maps
    profile = server/'config/eloria'
    _, portals = load_maps(profile/'maps.txt')
    for path in sorted((profile/'instances').glob('*.def')):
        text = path.read_text(encoding='utf-8')
        fields = dict(re.findall(r'^([a-z_]+):\s*(.*?)\s*$', text, re.M))
        region = fields.get('exit_map')
        if region not in exteriors or not fields.get('copies'):
            continue
        copies = set(fields['copies'].split(', '))
        returns = {(p.destination_x, p.destination_y) for p in portals
                   if p.source in copies and p.destination == region}
        if len(returns) != 1:
            raise ValueError(f'{path.name}: expected one shared exterior return, found {returns}')
        x, y = returns.pop()
        for key, value in (('exit_x', x), ('exit_y', y)):
            text, count = re.subn(r'^'+key+r':[^\r\n]*', f'{key}: {value}', text, flags=re.M)
            if count != 1:
                raise ValueError(f'{path.name}: expected exactly one {key}')
        if text != path.read_text(encoding='utf-8'):
            path.write_text(text, encoding='utf-8')
            print('instance return', path.name, region, x, y)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--server', type=Path, required=True)
    parser.add_argument('--data', type=Path, required=True)
    parser.add_argument('--skip-build', action='store_true')
    parser.add_argument('--stage', choices=('all', 'collision', 'content', 'publish'), default='all')
    args = parser.parse_args()
    server, data = args.server.resolve(), args.data.resolve()
    # Legacy content only: every loader this run calls reads the base tables, never the continent-v2 overlay (serve
    # plan CV13). The tools it runs as subprocesses switch themselves off the same way.
    read_base_only(server)
    if not args.skip_build:
        for region in EXTERIORS:
            source = REGIONS/region/'source'
            extra = ['--passes-only'] if region in ('amberwood', 'whitehorn_range') else []
            run(source, source/'rebuild_landscape.py', *extra)
    for region in NEW:
        source = REGIONS/region/'source'
        extra = [server] if region == 'grey_moors' else ['--server', server, '--apply']
        run(source, source/'migrate_compact_server.py', *extra)
    stages = {'collision': collision, 'content': content, 'publish': lambda s, d: publish(s)}
    for name, function in stages.items():
        if args.stage in ('all', name):
            function(server, data)


if __name__ == '__main__':
    main()
