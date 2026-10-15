"""Rebuild the southern landscapes and migrate all surveyed approaches.

The paired checkout owns publication. Regional builds never write another
region's source or shared server configuration. Use --stage to resume a phase.
"""
from pathlib import Path
import argparse
import json
import re
import sys

import rebuild_northern_regions as shared
from legacy_content import read_base_only

CLIENT = Path(__file__).resolve().parents[2]
MAPS = CLIENT / 'eloria-assets/maps'
REGIONS = MAPS / 'nymara-regions'
NEW = ('sunmane_steppe', 'verdant_stair', 'ssarathi_ruins')
RECEIVERS = ('amethyst_barrens', 'four_gates', 'amberwood', 'whitehorn_range',
             'grey_moors', 'mirrorhold', 'westhaven', 'crownwater')
EXTERIORS = RECEIVERS + NEW
FAMILY = EXTERIORS + ('resonant_vault', 'sunmane_wind_caves',
    'verdant_stair_insides', 'ssarathi_royal_archive') + tuple(
        region + '_secrets' for region in EXTERIORS)


def package(region):
    return MAPS / 'four-gates' if region == 'four_gates' else REGIONS / region


def rebuild_geometry(region):
    """Migrate all surveyed approaches without replaying old server migrations."""
    source = package(region) / 'source'
    if region in ('amberwood','whitehorn_range'):
        builder = 'build_amberwood.py' if region == 'amberwood' else 'build_whitehorn.py'
        shared.run(source, source / builder)
        for script in ('refine_walk_heights.py','open_walk_surfaces.py','stamp_solid_landmarks.py'):
            shared.run(REGIONS, REGIONS / '_toolkit' / script, region)
        shared.run(REGIONS, REGIONS / '_toolkit/guard_actor_surfaces.py', '--package', package(region))
        shared.run(REGIONS, REGIONS / '_toolkit/verify_runtime.py', '--package', package(region),
                   '--report', package(region) / 'verification-report.json')
    else:
        extra = ['--skip-secrets'] if region == 'mirrorhold' else (
            ['--verify'] if region in ('amethyst_barrens','crownwater') else [])
        shared.run(source, source / 'rebuild_landscape.py', *extra)


def update_registry():
    path = CLIENT / 'godot-client/data/maps/registry.json'
    registry = json.loads(path.read_text(encoding='utf-8'))
    for region in NEW:
        manifest = json.loads((package(region) / 'world.json').read_text(encoding='utf-8'))
        entry = registry['maps'][region]
        entry['coordinateTransform'] = manifest['coordinateTransform']
        entry['landscapeTransitions'] = True
    path.write_text(json.dumps(registry, indent=2) + '\n', encoding='utf-8')


def prepare(server, data):
    for region in NEW:
        source = package(region) / 'source'
        shared.run(source, source / 'migrate_compact_server.py', '--server', server, '--apply')
    sys.path[:0] = [str(server / 'tools'), str(server)]
    from generate_nymara_maps import ARRIVAL_TILES, MAP_TILES_WIDE_BY_NAME
    path = server / 'config/eloria/client_content_manifest.json'
    manifest = json.loads(path.read_text(encoding='utf-8'))
    by_id = {entry['id']: entry for entry in manifest['maps']}
    for region in FAMILY:
        entry = by_id.get(region)
        if entry is None:
            entry = {'id': region}
            manifest['maps'].append(entry)
        entry.update(server_cells=MAP_TILES_WIDE_BY_NAME[region] * 6,
                     arrival=list(ARRIVAL_TILES[region]))
    path.write_text(json.dumps(manifest, indent=2) + '\n', encoding='utf-8')
    update_registry()


def collision(server, data):
    shared.collision(server, data, family=FAMILY)


def content(server, data):
    sync_interior_working_posts(server)
    shared.run(CLIENT, package('verdant_stair') / 'source/reseat_guarded_content.py',
               '--server', server, '--apply')
    for region in RECEIVERS:
        # Receiver collision can move a secret's adjacent standing tile too.
        # Publish that object contract before the shared relocation audit.
        shared.run(server, server / 'tools/author_region_content.py', 'secrets',
            '--maps', data, '--client', CLIENT, '--region', region, '--apply')
    shared.content(server, data, exteriors=EXTERIORS, new=NEW, family=FAMILY)
    # Sunmane retains legacy server-owned markers as well as the served roster.
    shared.run(CLIENT, CLIENT / 'eloria-assets/tools/sync_package_content.py',
        '--manifest', server / 'config/eloria/client_content_manifest.json',
        '--package', 'nymara-regions/sunmane_steppe', '--write-source-posts', '--apply')
    sync_sunmane_lod()
    sync_harvest_assignments(server)


def sync_interior_working_posts(server):
    """Interior residents work beside the door, leaving arrivals clear."""
    path=server/'config/eloria/npcs.txt'
    rows=path.read_text(encoding='utf-8').splitlines()
    posts={('Archive Copyist Uln-Sath','ssarathi_royal_archive'):['31','287'],
           ('Physick Apprentice Osu-Nell','verdant_stair_insides'):['47','280'],
           ('Stair Provisioner Belm Ott','verdant_stair_insides'):['197','278'],
           ('Wind-Cave Echo Reader Tul Marrow','sunmane_wind_caves'):['45','30'],
           ('Cave Prospector Ashen Duru','sunmane_wind_caves'):['170','30']}
    found=set()
    for index,row in enumerate(rows):
        fields=[f.strip() for f in row.split('|')]
        if len(fields)>5 and fields[0]=='npc' and (fields[1],fields[2]) in posts:
            key=(fields[1],fields[2]);fields[3:5]=posts[key];rows[index]=' | '.join(fields);found.add(key)
    if found!=set(posts):raise ValueError(f'Missing existing interior residents: {set(posts)-found}')
    text='\n'.join(rows)+'\n'
    if text!=path.read_text(encoding='utf-8'):path.write_text(text,encoding='utf-8')


def sync_harvest_assignments(server):
    """Keep daily task indices/rewards while following actual harvest plots."""
    sys.path.insert(0, str(server))
    from eloria.harvesting import load_harvesting
    _, nodes = load_harvesting(server / 'config/eloria/harvesting.txt')
    path = server / 'eloria/daily_quests.py'
    original = path.read_text(encoding='utf-8')
    found = set()
    def replace(match):
        prefix, resource, region = match[1], match[2], match[3]
        if region not in ('sunmane_steppe','verdant_stair'):
            return match[0]
        choices = [node for node in nodes.values()
                   if node.map_id == region and node.resource == resource]
        if not choices:
            raise ValueError(f'{region}: daily harvest has no {resource}')
        node = min(choices,key=lambda n:n.object_id)
        found.add(region)
        return f'{prefix}{node.x},{node.y},'
    updated = re.sub(r'(DailyTask\("[^"\n]+","harvest","([^"\n]+)",\d+,"([^"\n]+)",)-?\d+,-?\d+,',
                     replace, original)
    if found != {'sunmane_steppe','verdant_stair'}:
        raise ValueError(f'Missing southern daily harvest definitions: {found}')
    if updated != original:
        path.write_text(updated,encoding='utf-8')


def sync_sunmane_lod():
    """LOD markers use the same identities and tiles, on their own drawn floor."""
    sys.path.insert(0, str(REGIONS / '_toolkit'))
    from contentposts import apply, apply_runtime
    root = package('sunmane_steppe')
    path = root / 'world-lod2.json'
    if not path.is_file():
        return
    manifest = json.loads(path.read_text(encoding='utf-8'))
    posts = json.loads((root / 'source/server-content.json').read_text(encoding='utf-8'))
    apply(manifest, root, posts, glb_name='world-lod2.glb')
    apply_runtime(manifest, root)
    path.write_text(json.dumps(manifest, indent=2) + '\n', encoding='utf-8')


def publish(server, data):
    update_registry()
    shared.publish(server, exteriors=EXTERIORS, family=FAMILY)
    sync_sunmane_lod()
    shared.run(CLIENT, CLIENT / 'eloria-assets/tools/build_continent_map.py')
    # Wave anchors depend on the final ground, door and service positions too.
    shared.run(server, server / 'tools/generate_nymara_invasion_spawns.py')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--server', type=Path, required=True)
    parser.add_argument('--data', type=Path, required=True)
    parser.add_argument('--skip-build', action='store_true')
    parser.add_argument('--stage', choices=('all', 'prepare', 'collision', 'content', 'publish'), default='all')
    args = parser.parse_args()
    server, data = args.server.resolve(), args.data.resolve()
    # Legacy content only: base tables, never the continent-v2 overlay (serve plan CV13; see legacy_content.py).
    read_base_only(server)
    if not args.skip_build:
        for region in EXTERIORS:
            rebuild_geometry(region)
    for name, action in (('prepare', prepare), ('collision', collision),
                         ('content', content), ('publish', publish)):
        if args.stage in ('all', name):
            action(server, data)


if __name__ == '__main__':
    main()
