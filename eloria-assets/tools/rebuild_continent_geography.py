"""Rebuild the geographic continent, then publish its paired server contracts.

Native source coordinates remain stable. The shared geography pass authors
outer roads and ownership; collision expansion changes the served address
frame. Run stages in order, or resume an individual stage after correcting a
reported contract. No editor import, live database mutation or push is needed.
"""
from pathlib import Path
from collections import Counter
import argparse
import ast
import hashlib
import json
import math
import subprocess
import sys

import rebuild_northern_regions as shared
import sync_geographic_family as rooms

CLIENT = Path(__file__).resolve().parents[2]
MAPS = CLIENT / 'eloria-assets/maps'
REGIONS = MAPS / 'nymara-regions'
TOOLKIT = REGIONS / '_toolkit'
NORTHERN_FINISH = ('whitehorn_range', 'mirrorhold', 'amethyst_barrens')
OUTER_FINISH = ('whitehorn_range', 'amberwood', 'amethyst_barrens', 'grey_moors',
                'sunmane_steppe', 'ssarathi_ruins', 'verdant_stair', 'manymouth_delta')
CONNECTOR_FINISH = ('four_gates', 'whitehorn_range', 'amberwood', 'mirrorhold',
                    'grey_moors', 'westhaven', 'crownwater', 'sunmane_steppe',
                    'ssarathi_ruins', 'verdant_stair', 'manymouth_delta')
COLOR_FINISH = ('crownwater', 'four_gates', 'manymouth_delta', 'ssarathi_ruins', 'grey_moors', 'sunmane_steppe', 'amberwood', 'verdant_stair')
BUILDERS = {
    'four_gates': 'build_four_gates.py',
    'sunmane_steppe': 'build_landscape.py',
    'verdant_stair': 'build_verdant_stair.py',
    'ssarathi_ruins': 'build_ssarathi.py',
    'amberwood': 'build_amberwood.py',
    'whitehorn_range': 'build_whitehorn.py',
    'mirrorhold': 'build_mirrorhold.py',
    'amethyst_barrens': 'build_amethyst.py',
    'grey_moors': 'build_grey_moors.py',
    'westhaven': 'build_westhaven.py',
    'crownwater': 'build_crownwater.py',
    'manymouth_delta': 'build_manymouth_delta.py',
}


def package(region):
    return MAPS / 'four-gates' if region == 'four_gates' else REGIONS / region


def run(cwd, *args):
    shared.run(cwd, *args)


def geometry_sources(region):
    """The exact per-region dependency set used by builds and validation."""
    root = package(region)
    return sorted({REGIONS / 'continent-geography.json',
                   *TOOLKIT.rglob('*.py'), *(root / 'source').glob('*.py'),
                   *((REGIONS / '_northern').glob('*.py') if region in NORTHERN_FINISH + CONNECTOR_FINISH else ()),
                   *((REGIONS / '_finishing').glob('*.py') if region in CONNECTOR_FINISH else ()),
                   *((REGIONS / '_outer').glob('*.py') if region in OUTER_FINISH else ()),
                   *((REGIONS / '_color').glob('*.py') if region in COLOR_FINISH else ())})


def validate_geometry_inputs(regions):
    """A later edit must not silently invalidate an earlier region's build."""
    current = {}
    for region in regions:
        manifest = json.loads((package(region) / 'world.json').read_text(encoding='utf-8'))
        inputs = manifest.get('authoredGeometry', {}).get('inputs')
        if not inputs:
            raise ValueError(f'{region}: no completed geographic build input certificate')
        expected = {p.relative_to(CLIENT).as_posix() for p in geometry_sources(region)}
        if set(inputs) != expected:
            missing, obsolete = sorted(expected - set(inputs)), sorted(set(inputs) - expected)
            raise ValueError(f'{region}: geometry input set changed after build; missing={missing}; obsolete={obsolete}; rebuild before publication')
        for relative, expected in inputs.items():
            path = (CLIENT / relative).resolve()
            if not path.is_relative_to(CLIENT.resolve()):
                raise ValueError(f'{region}: geometry input escapes client: {relative}')
            if relative not in current:
                current[relative] = hashlib.sha256(path.read_bytes()).hexdigest() if path.is_file() else None
            if current[relative] != expected:
                raise ValueError(f'{region}: geometry input changed after build: {relative}; rebuild before publication')


def validate_prepare_scope(server, regions):
    """Origin preparation is global; the first publication cannot be partial."""
    geography_path = REGIONS / 'continent-geography.json'
    raw = geography_path.read_bytes()
    names = set(json.loads(raw)['regions'])
    if set(regions) == names:
        return
    profile = json.loads((server / 'config/eloria/client_content_manifest.json').read_text(encoding='utf-8'))
    previous = profile.get('continentGeography', {})
    if (set(previous.get('regions', {})) != names
            or previous.get('geographySha256') != hashlib.sha256(raw).hexdigest()):
        raise ValueError('Initial or revised geographic origin publication requires all twelve regions; --region is only a same-revision repair')


def geometry(regions):
    for region in regions:
        root = package(region)
        sources = geometry_sources(region)
        def hashes():
            return {p.relative_to(CLIENT).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest() for p in sources}
        before = hashes()
        run(root / 'source', root / 'source' / BUILDERS[region])
        if before != hashes():
            raise RuntimeError(f'{region}: authored geometry inputs changed during its build; rebuild after sources are frozen')
        # Expand before the final walkability passes so a new border cell is
        # verified at its real actor position in the new authoritative grid.
        run(CLIENT, CLIENT / 'eloria-assets/tools/expand_continent_collision.py',
            '--region', region, '--apply')
        sys.path.insert(0, str(TOOLKIT))
        from refine_walk_heights import refine
        from open_walk_surfaces import open_package
        from stamp_solid_landmarks import stamp
        from guard_actor_surfaces import guard
        refine(root, True)
        open_package(root, True)
        stamp(root)
        guard(root, True)
        path = root / 'world.json'
        manifest = json.loads(path.read_text(encoding='utf-8'))
        manifest['authoredGeometry'] = {'generator': 'eloria-assets/tools/rebuild_continent_geography.py',
                                        'inputs': before}
        path.write_text(json.dumps(manifest, indent=2)+'\n', encoding='utf-8')
        run(CLIENT, TOOLKIT / 'verify_runtime.py', '--package', root,
            '--report', root / 'geographic-validation.json')


def prepare(server, regions):
    validate_prepare_scope(server, regions)
    validate_geometry_inputs(BUILDERS)
    run(CLIENT, CLIENT / 'eloria-assets/tools/export_continent_water.py', '--apply')
    run(CLIENT, CLIENT / 'eloria-assets/tools/publish_continent_geography.py',
        '--server', server, '--apply')
    rooms.sync_family(CLIENT, server, regions, apply=True)


def collision(server, data, regions):
    family = rooms.family_ids(CLIENT, server, regions)
    if 'manymouth_flooded_labyrinth' in family:
        # The composed interior grid is a source of the served ELM. Refresh it
        # from the rebuilt room package before the shared collision publisher.
        source = package('manymouth_delta') / 'source/export_insides_collision.py'
        run(source.parent, source)
    shared.collision(server, data, family=family)


def content(server, data, regions):
    # Manymouth also changed native terrain and habitats: its scatter must use
    # the authored layout rather than only the nonlinear coordinate migration.
    new = tuple(region for region in regions if region == 'manymouth_delta')
    before = {region: living_identities(server, region) for region in new}
    for region in regions:
        run(server, server / 'tools/author_region_content.py', 'secrets',
            '--maps', data, '--client', CLIENT, '--region', region, '--apply')
    shared.content(server, data, exteriors=tuple(regions), new=new,
                   family=rooms.family_ids(CLIENT, server, regions))
    for region, expected in before.items():
        actual = living_identities(server, region)
        if actual != expected:
            raise ValueError(f'{region}: authored content changed NPC/resource identities or species counts; review before publishing')
    sync_manymouth_daily_harvest(server, regions)
    # Reapply authored room staff positions after generic collision relocation,
    # before room markers and package digests are finalized.
    run(CLIENT, CLIENT / 'eloria-assets/tools/publish_interior_staff.py',
        '--server', server, '--data', data, '--client', CLIENT, '--apply')


def sync_manymouth_daily_harvest(server, regions):
    """Follow retained Lotus 58 after habitat authoring and collision relocation.

    The daily quest counts harvests within eight tiles of its post. Mapping its
    old position alone does not follow the newly authored resource habitat.
    Keep its task, quantity and rewards intact; change only its two coordinates.
    """
    if 'manymouth_delta' not in regions:
        return None
    from publish_continent_geography import SourceEdits

    rows = ([part.strip() for part in line.split('|')] for line in
            (server / 'config/eloria/harvesting.txt').read_text(encoding='utf-8').splitlines())
    nodes = [row for row in rows if len(row) >= 3 and
             row[:3] == ['node', 'manymouth_delta', '58']]
    if len(nodes) != 1 or len(nodes[0]) < 6 or nodes[0][5] != 'Lotus':
        raise ValueError('Manymouth daily harvest requires exactly one retained Lotus node 58')
    position = tuple(int(value) for value in nodes[0][3:5])
    path = server / 'eloria/daily_quests.py'
    original = path.read_bytes()
    edit = SourceEdits(original.decode('utf-8'))
    calls = []
    for node in ast.walk(edit.tree):
        if not (isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
                and node.func.id == 'DailyTask' and len(node.args) >= 7):
            continue
        if all(isinstance(node.args[index], ast.Constant) and node.args[index].value == value
               for index, value in ((0, 'Mara Tide'), (1, 'harvest'),
                                    (2, 'Lotus'), (4, 'manymouth_delta'))):
            calls.append(node)
    if len(calls) != 1:
        raise ValueError('Expected exactly one Mara Tide Manymouth Lotus daily task')
    call = calls[0]
    previous = tuple(ast.literal_eval(call.args[index]) for index in (5, 6))
    if previous != position:
        for index, value in zip((5, 6), position):
            edit.replace(call.args[index], value)
        path.write_bytes(edit.finish().encode('utf-8'))
    return {'region': 'manymouth_delta', 'resourceId': 58, 'resource': 'Lotus',
            'previous': list(previous), 'position': list(position), 'changed': previous != position}


def living_identities(server, region):
    """Coordinates may move; residents, resource identities and species may not."""
    profile = server / 'config/eloria'
    result = {}
    for name, marker, map_index, identity in (
        ('npcs.txt', 'npc', 2, lambda row: row[1]),
        ('spawns.txt', 'spawn', 1, lambda row: row[2]),
        ('harvesting.txt', 'node', 1, lambda row: (row[2], row[5])),
    ):
        rows = ([value.strip() for value in line.split('|')]
                for line in (profile/name).read_text(encoding='utf-8').splitlines())
        result[name] = Counter(identity(row) for row in rows
                               if len(row) > map_index and row[0] == marker and row[map_index] == region)
    return result


def layout():
    path = REGIONS / 'continent-layout.json'
    current = json.loads(path.read_text(encoding='utf-8'))
    geographic = json.loads((REGIONS / 'continent-geography.json').read_text(encoding='utf-8'))
    all_points = [p for spec in geographic['regions'].values() for p in spec['ownershipPolygon']]
    low = [math.floor((min(p[i] for p in all_points)-24)/20)*20 for i in (0, 1)]
    high = [math.ceil((max(p[i] for p in all_points)+24)/20)*20 for i in (0, 1)]
    current.update(schema=2,
        note='North-up metre coordinates from continent-geography.json; the atlas and actual exterior frames share the same translations and ownership polygons.',
        sea=[79,150,157], originMetres=low, canvasMetres=[high[i]-low[i] for i in (0, 1)])
    current.pop('lake', None)
    current['routeBends'] = {}
    for region, spec in geographic['regions'].items():
        low, high = spec['nativePlayableBounds']
        current['regions'][region] = [spec['translation'][0]+(low[0]+high[0])/2,
                                      spec['translation'][2]+(low[1]+high[1])/2]
    path.write_text(json.dumps(current, indent=2)+'\n', encoding='utf-8')


def publish_approach_reader(server):
    """Ship the same pure approach contract reader with standalone server tools."""
    relative = 'eloria-assets/tools/continent_approaches.py'
    server_relative = 'tools/continent_approaches.py'
    source = CLIENT / relative
    raw = source.read_bytes()
    compile(raw, str(source), 'exec')
    profile_path = server / 'config/eloria/client_content_manifest.json'
    profile = json.loads(profile_path.read_text(encoding='utf-8'))
    geography = profile['continentGeography']
    record = {'source': relative, 'serverPath': server_relative,
              'sha256': hashlib.sha256(raw).hexdigest()}
    target = server / server_relative
    if not target.is_file() or target.read_bytes() != raw:
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(raw)
    if geography.get('approachReader') != record:
        geography['approachReader'] = record
        profile_path.write_text(json.dumps(profile, indent=2)+'\n', encoding='utf-8')
    return record


def publish(server, artifacts, regions):
    validate_geometry_inputs(BUILDERS)
    layout()
    run(CLIENT, CLIENT / 'eloria-assets/tools/render_region_cartography.py',
        '--regions', *regions, '--output-dir', artifacts / 'cartography-final', '--apply')
    publish_approach_reader(server)
    shared.publish(server, exteriors=tuple(regions), family=rooms.family_ids(CLIENT, server, regions),
                   before_digests=lambda: rooms.sync_lods(CLIENT, server, regions, apply=True))
    run(CLIENT, CLIENT / 'eloria-assets/tools/build_continent_map.py')
    run(server, server / 'tools/generate_nymara_invasion_spawns.py')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--server', type=Path, required=True)
    parser.add_argument('--data', type=Path, required=True)
    parser.add_argument('--artifacts', type=Path, required=True)
    parser.add_argument('--region', action='append', choices=tuple(BUILDERS))
    parser.add_argument('--stage', choices=('all','geometry','prepare','collision','content','publish'), default='all')
    args = parser.parse_args()
    geography_path = REGIONS / 'continent-geography.json'
    if geography_path.is_file() and json.loads(geography_path.read_text(encoding='utf-8')).get('geometryMode') == 'continent-chunks-v1':
        raise SystemExit('This continent is authored as one shared master. Rebuild with eloria-assets/maps/nymara-regions/_continent/build_pipeline.py --server SERVER --data DATA --artifacts ARTIFACTS. The legacy per-region geography rebuild would replace its canonical terrain and contracts.')
    server, data, artifacts = args.server.resolve(), args.data.resolve(), args.artifacts.resolve()
    artifacts.mkdir(parents=True, exist_ok=True)
    regions = args.region or list(BUILDERS)
    if args.stage in ('all','geometry'): geometry(regions)
    if args.stage in ('all','prepare'): prepare(server, regions)
    if args.stage in ('all','collision'): collision(server, data, regions)
    if args.stage in ('all','content'): content(server, data, regions)
    if args.stage in ('all','publish'): publish(server, artifacts, regions)


if __name__ == '__main__':
    main()
