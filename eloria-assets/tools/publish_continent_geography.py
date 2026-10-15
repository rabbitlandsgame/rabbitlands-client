"""Publish integer grid translations without moving native places or content IDs.

Dry run is the default. --check also requires the expanded client packages;
--apply performs the same checks before writing. Collision, continent portal
generation and content placement remain separate coordinator stages.
"""
from __future__ import annotations

import argparse
import ast
import bisect
import copy
import hashlib
import json
import re
import struct
from pathlib import Path

CLIENT = Path(__file__).resolve().parents[2]
GEOGRAPHY = CLIENT / 'eloria-assets/maps/nymara-regions/continent-geography.json'
STATE = 'continentGeography'
RULES = {
    'npcs.txt': [('npc', 2, 3, 4)],
    'spawns.txt': [('spawn', 1, 3, 4)],
    'harvesting.txt': [('node', 1, 3, 4)],
    'maps.txt': [('portal7', 1, 2, 3), ('portal7', 4, 5, 6),
                 ('portal8', 1, 3, 4), ('portal8', 5, 6, 7)],
    'interactives.txt': [(None, 0, 2, 3)],
    'territories.txt': [(None, 2, 4, 5), (None, 2, 6, 7), (None, 2, 8, 9)],
    'special_areas.txt': [('area', 2, 3, 4), ('area', 2, 5, 6)],
}


def digest(payload):
    return hashlib.sha256(payload).hexdigest()


def json_bytes(data):
    return (json.dumps(data, indent=2, ensure_ascii=False) + '\n').encode('utf-8')


def integer_pair(value, label):
    if not isinstance(value, (list, tuple)) or len(value) != 2:
        raise ValueError(f'{label}: expected a two-coordinate array')
    if any(isinstance(n, bool) or not isinstance(n, (int, float)) or int(n) != n for n in value):
        raise ValueError(f'{label}: grid coordinates must be integers: {value}')
    return tuple(map(int, value))


def contracts(geography, previous):
    if geography.get('schema') != 1 or geography.get('geometryMode') != 'continent-owned-v1':
        raise ValueError('Unsupported continent geography schema or geometry mode')
    result = {}
    for region, raw in geography['regions'].items():
        native = integer_pair(raw['nativeServerOrigin'], region + ' native origin')
        origin = integer_pair(raw['serverOrigin'], region + ' origin')
        cells = integer_pair(raw['serverCells'], region + ' cells')
        if cells[0] != cells[1] or cells[0] <= 0 or cells[0] % 6:
            raise ValueError(f'{region}: server generator requires positive square cells divisible by six: {cells}')
        if raw.get('rotationDegrees', 0) != 0:
            raise ValueError(f'{region}: only unchanged native axes are supported')
        if integer_pair(raw['serverTileShift'], region + ' tile shift') != tuple(origin[i] - native[i] for i in range(2)):
            raise ValueError(f'{region}: origin and declared tile shift disagree')
        old = integer_pair(previous.get(region, {}).get('serverOrigin', native), region + ' previous origin')
        result[region] = {'nativeServerOrigin': list(native), 'nativeServerCells': list(integer_pair(raw.get('nativeServerCells', cells), region + ' native cells')), 'serverOrigin': list(origin),
                          'serverCells': list(cells), 'translation': raw['translation'],
                          'delta': [origin[i] - old[i] for i in range(2)]}
    return result


def shifted(point, region, maps):
    x, y = integer_pair(point, region + ' coordinate')
    spec = maps.get(region, {})
    if spec.get('_native_mapper'):
        x, y = integer_pair(spec['_native_mapper']((x, y)), region + ' native mapped coordinate')
    dx, dy = spec.get('delta', [0, 0])
    return [x + dx, y + dy]


def map_axis(value, axis):
    old, new = axis['old'], axis['new']
    if len(old) != len(new) or len(old) < 2 or any(a >= b for a, b in zip(old, old[1:])) or any(a >= b for a, b in zip(new, new[1:])):
        raise ValueError('Native remap axes must be strictly monotone paired knots')
    index = max(0, min(len(old) - 2, bisect.bisect_right(old, value) - 1))
    return new[index] + (value - old[index]) * (new[index + 1] - new[index]) / (old[index + 1] - old[index])


def native_mapper(data, previous_origin):
    legacy = integer_pair(data['legacyOrigin'], 'native migration legacy origin')
    native = integer_pair(data['nativeOrigin'], 'native migration new origin')
    prior_padding = [previous_origin[i] - legacy[i] for i in (0, 1)]
    def convert(point):
        old = [point[i] - prior_padding[i] for i in (0, 1)]
        x = map_axis(old[0] - legacy[0], data['axes']['x'])
        z = map_axis(legacy[1] - old[1], data['axes']['z'])
        return [round(x + native[0]), round(native[1] - z)]
    # Validate both axes before a tool can prepare any output.
    convert(legacy)
    return convert


def native_arrival(spec):
    return [spec['nativeArrival'][i] + spec['serverOrigin'][i] - spec['nativeServerOrigin'][i] for i in (0, 1)]


def field_number(field, value):
    match = re.fullmatch(r'(\s*)(-?\d+)(\s*)', field)
    if match is None:
        raise ValueError(f'Malformed coordinate field: {field!r}')
    return match[1] + str(value).rjust(len(match[2])) + match[3]


def rewrite_profile(text, rules, maps):
    rows, count = [], 0
    for line in text.splitlines(keepends=True):
        if not line.strip() or line.lstrip().startswith('#'):
            rows.append(line)
            continue
        fields = line.split('|')
        for keyword, mi, xi, yi in rules:
            if keyword and keyword.startswith('portal'):
                match = fields[0].strip() == 'portal' and len(fields) == int(keyword[-1])
            else:
                match = keyword is None or fields[0].strip() == keyword
            if not match or len(fields) <= max(mi, xi, yi):
                continue
            region = fields[mi].strip()
            if region not in maps or (maps[region]['delta'] == [0, 0] and not maps[region].get('_native_mapper')):
                continue
            old = [int(fields[xi]), int(fields[yi])]
            new = shifted(old, region, maps)
            fields[xi], fields[yi] = field_number(fields[xi], new[0]), field_number(fields[yi], new[1])
            count += 1
        rows.append('|'.join(fields))
    return ''.join(rows), count


def map_name(raw):
    return Path(raw.strip().replace('\\', '/')).name.removesuffix('.gz').removesuffix('.elm')


def rewrite_definition(text, maps, *, point_mapper=None):
    """Rewrite coordinate pairs, optionally with certified record context.

    A mapper returns a two-integer target or None for the legacy map shift.
    Context identifies syntax, never a mutable served coordinate; the caller
    supplies the source path and validates uniqueness/certified provenance.
    """
    current, destination, count, pairs = '', '', 0, {}
    section, record_id, record_field, section_ordinal = '', '', '', -1
    rows = text.splitlines(keepends=True)
    for index, line in enumerate(rows):
        if line.strip() in ('[spawn]', '[instance]', '[stage]'):
            section = line.strip()[1:-1]
            record_id, record_field = '', ''
            section_ordinal += 1
            current, destination = '', ''
            pairs.clear()
        match = re.fullmatch(r'(\s*)([a-z_]+)(\s*:\s*)([^\r\n]*)(\r?\n)?', line)
        if not match:
            continue
        key, value = match[2], match[4]
        if key == 'spawn_name' or (key in ('id', 'key') and not record_field):
            record_id, record_field = value.strip(), key
        if key in ('map_id', 'map'):
            current = map_name(value)
        elif key == 'exit_map':
            destination = map_name(value)
        spec = {'x_pos': (current, 0), 'y_pos': (current, 1),
                'x': (current, 0), 'y': (current, 1),
                'entry_x': (current, 0), 'entry_y': (current, 1),
                'exit_x': (destination, 0), 'exit_y': (destination, 1)}.get(key)
        if spec and spec[0] in maps:
            kind = 'monster' if key.endswith('_pos') else ('entry' if key.startswith('entry_') else 'exit' if key.startswith('exit_') else 'stage')
            pair = pairs.setdefault((spec[0], kind), {})
            pair[spec[1]] = (index, match)
            if len(pair) == 2:
                old = [int(pair[axis][1][4]) for axis in (0, 1)]
                point = None
                if point_mapper is not None:
                    context = {'section': section, 'recordId': record_id,
                               'recordField': record_field, 'sectionOrdinal': section_ordinal,
                               'pairKind': kind, 'fields': [pair[i][1][2] for i in (0, 1)],
                               'map': spec[0], 'sourceIndices': [pair[i][0] for i in (0, 1)]}
                    point = point_mapper(spec[0], list(old), context)
                    if point is not None:
                        if (not isinstance(point, (list, tuple)) or len(point) != 2 or
                                any(isinstance(n, bool) or not isinstance(n, int) for n in point)):
                            raise ValueError('Definition point mapper must return two exact integers or None')
                if point is None:
                    point = shifted(old, spec[0], maps)
                for axis in (0, 1):
                    at, found = pair[axis]
                    if point[axis] != old[axis]:
                        rows[at] = found[1] + found[2] + found[3] + field_number(found[4], point[axis]) + (found[5] or '')
                        count += 1
                pairs.pop((spec[0], kind))
    return ''.join(rows), count


def quest_visit(text, key, region, point):
    """Reseat an explicitly approved visit stage, preserving its prose/rewards."""
    current, kind, stage_map, rows, found = '', '', '', [], 0
    for line in text.splitlines(keepends=True):
        if line.strip() == '[quest]':
            current = ''
        if line.strip() == '[stage]':
            kind, stage_map = '', ''
        match = re.fullmatch(r'(\s*)([a-z_]+)(\s*:\s*)([^\r\n]*)(\r?\n)?', line)
        if match:
            field, value = match[2], match[4].strip()
            if field == 'key':
                current = value
            elif field == 'kind':
                kind = value
            elif field == 'map':
                stage_map = value
            elif current == key and kind == 'visit' and stage_map == region and field in ('x', 'y'):
                line = match[1] + field + match[3] + field_number(match[4], point[0 if field == 'x' else 1]) + (match[5] or '')
                found += 1
        rows.append(line)
    if found != 2:
        raise ValueError(f'{key}: expected one explicit {region} visit stage, found {found} coordinate fields')
    return ''.join(rows)


class SourceEdits:
    """Replace only selected AST expressions, leaving surrounding source intact."""
    def __init__(self, text):
        self.text = text
        self.tree = ast.parse(text)
        self.lines = text.splitlines(keepends=True)
        self.starts = [0]
        for line in self.lines:
            self.starts.append(self.starts[-1] + len(line))
        self.edits = []

    def offset(self, line, byte_column):
        return self.starts[line - 1] + len(self.lines[line - 1].encode('utf-8')[:byte_column].decode('utf-8'))

    def replace(self, node, value):
        start, end = self.offset(node.lineno, node.col_offset), self.offset(node.end_lineno, node.end_col_offset)
        self.edits.append((start, end, repr(value)))

    def assignment(self, name):
        for node in self.tree.body:
            if isinstance(node, ast.Assign) and any(isinstance(t, ast.Name) and t.id == name for t in node.targets):
                return node.value
        raise ValueError(f'Missing required source contract {name}')

    def finish(self):
        result, limit = self.text, len(self.text) + 1
        for start, end, value in sorted(self.edits, reverse=True):
            if end > limit:
                raise ValueError('Overlapping coordinate source edits')
            result = result[:start] + value + result[end:]
            limit = start
        ast.parse(result)
        return result


def rewrite_python(text, kind, maps):
    edit = SourceEdits(text)
    if kind == 'generator':
        for name in ('MAP_TILES_WIDE_BY_NAME', 'ARRIVAL_TILES'):
            node = edit.assignment(name)
            if not isinstance(node, ast.Dict):
                raise ValueError(name + ' must remain a dictionary')
            found = set()
            for key, value in zip(node.keys, node.values):
                region = ast.literal_eval(key) if key is not None else None
                if region not in maps:
                    continue
                found.add(region)
                new = maps[region]['serverCells'][0] // 6 if name == 'MAP_TILES_WIDE_BY_NAME' else tuple(
                    native_arrival(maps[region]) if 'nativeArrival' in maps[region] else shifted(ast.literal_eval(value), region, maps))
                edit.replace(value, new)
            if found != set(maps):
                raise ValueError(f'{name} lacks geography maps {sorted(set(maps)-found)}')
        if 'four_gates' in maps:
            edit.replace(edit.assignment('FOUR_GATES_TILES_WIDE'), maps['four_gates']['serverCells'][0] // 6)
    elif kind == 'layout':
        if 'four_gates' in maps:
            node = edit.assignment('FOUR_GATES_ARRIVAL')
            edit.replace(node, tuple(shifted(ast.literal_eval(node), 'four_gates', maps)))
        for name in ('COASTAL_ARRIVALS', 'SOUTHERN_ARRIVALS'):
            node = edit.assignment(name)
            for key, value in zip(node.keys, node.values):
                region = ast.literal_eval(key)
                if region in maps and not isinstance(value, ast.Name):
                    edit.replace(value, tuple(shifted(ast.literal_eval(value), region, maps)))
    elif kind in ('world', 'walkthrough'):
        if 'four_gates' in maps and maps['four_gates']['delta'] != [0, 0]:
            if kind == 'walkthrough':
                node = edit.assignment('PLAZA')
                edit.replace(node, tuple(shifted(ast.literal_eval(node), 'four_gates', maps)))
            else:
                node = edit.assignment('TUTORIAL_ROUTE_MARKERS')
                edit.replace(node, tuple(tuple(shifted(p, 'four_gates', maps)) for p in ast.literal_eval(node)))
                node = edit.assignment('TUTORIAL_HARVESTS')
                edit.replace(node, tuple((p[0], *shifted(p[1:3], 'four_gates', maps), *p[3:]) for p in ast.literal_eval(node)))
    elif kind in ('daily', 'pk'):
        for node in ast.walk(edit.tree):
            if not isinstance(node, ast.Call) or not isinstance(node.func, ast.Name):
                continue
            if kind == 'daily' and node.func.id == 'DailyTask' and len(node.args) >= 7:
                region = ast.literal_eval(node.args[4])
                if region in maps and ast.literal_eval(node.args[1]) != 'kill':
                    for index, value in zip((5, 6), shifted([ast.literal_eval(n) for n in node.args[5:7]], region, maps)):
                        edit.replace(node.args[index], value)
            elif kind == 'pk' and node.func.id == 'PKZone' and len(node.args) >= 5:
                region = ast.literal_eval(node.args[0])
                if region in maps:
                    for indices in ((1, 2), (3, 4)):
                        for index, value in zip(indices, shifted([ast.literal_eval(node.args[i]) for i in indices], region, maps)):
                            edit.replace(node.args[index], value)
    return edit.finish()


def shift_markers(value, region, maps):
    if isinstance(value, list):
        return [shift_markers(item, region, maps) for item in value]
    if not isinstance(value, dict):
        return value
    result = {}
    region = value.get('map_id', value.get('map', region))
    for key, item in value.items():
        if key in ('serverTile', 'server_tile', 'arrival') and region in maps:
            result[key] = shifted(item, region, maps)
        elif key == 'serverTiles' and region in maps:
            result[key] = [shifted(point, region, maps) for point in item]
        elif key == 'destinationTile':
            destination = value.get('destinationMap', value.get('destination', value.get('targetMap', '')))
            result[key] = shifted(item, destination, maps)
        else:
            result[key] = shift_markers(item, region, maps)
    return result


def runtime_migration_source(maps):
    """A restart-safe database hook; no database is opened by publication."""
    saved = {k: {n: v[n] for n in ('nativeServerOrigin', 'serverOrigin', 'serverCells', 'arrival', 'nativeRevision', 'terrainRevision') if n in v}
             for k, v in sorted(maps.items())}
    return '''"""Generated continent migration data; rebuilt with the paired map publication."""
from .geography_migration import migrate_geography

MAPS = ''' + repr(saved) + '''
STATE_KEY = 'continent_geography_origins_v1'

def migrate(db):
    migrate_geography(db, MAPS, STATE_KEY)
'''


def package(client, region):
    return client / 'eloria-assets/maps' / ('four-gates' if region == 'four_gates' else 'nymara-regions/' + region)


def plan(client, server, geography_path, require_built=False):
    raw = geography_path.read_bytes()
    geography = json.loads(raw)
    profile = server / 'config/eloria'
    manifest_path = profile / 'client_content_manifest.json'
    manifest = json.loads(manifest_path.read_text(encoding='utf-8'))
    maps = contracts(geography, manifest.get(STATE, {}).get('regions', {}))
    before, pending, records, checks, overrides = {geography_path: raw}, {}, [], [], []
    native_checks = []
    previous_regions = manifest.get(STATE, {}).get('regions', {})
    for region, spec in maps.items():
        path = package(client, region) / 'source/continent-migration.json'
        if not path.exists():
            if region == 'manymouth_delta':
                native_checks.append({'map': region, 'ready': False, 'reason': 'Manymouth compact mapping is pending'})
                if require_built:
                    raise ValueError('Manymouth compact native mapping is required before publication')
            continue
        before[path] = path.read_bytes()
        data = json.loads(before[path])
        if integer_pair(data['nativeOrigin'], region + ' native mapper origin') != tuple(spec['nativeServerOrigin']):
            raise ValueError(f'{region}: native mapping and geography origins disagree')
        native_cells = data['nativeCells']
        if isinstance(native_cells, int):
            native_cells = [native_cells, native_cells]
        if integer_pair(native_cells, region + ' mapper native cells') != tuple(spec['nativeServerCells']):
            raise ValueError(f'{region}: native mapping and geography grid dimensions disagree')
        ready = data.get('ready') is True
        native_checks.append({'map': region, 'revision': data['revision'], 'ready': ready})
        if require_built and not ready:
            raise ValueError(f'{region}: native coordinate mapping has not passed its physical route audit')
        previous = previous_regions.get(region, {})
        spec.update(nativeRevision=data['revision'], nativeMigrationSha256=digest(before[path]),
                    nativeArrival=list(integer_pair(data['nativeArrival'], region + ' native arrival')))
        if previous.get('nativeRevision') != data['revision']:
            if previous.get('nativeRevision') and data.get('legacyRevision') != previous['nativeRevision']:
                raise ValueError(f'{region}: native remap does not declare the previously published revision')
            old_origin = previous.get('serverOrigin', data['legacyOrigin'])
            spec['_native_mapper'] = native_mapper(data, old_origin)
            spec['delta'] = [spec['serverOrigin'][i] - spec['nativeServerOrigin'][i] for i in (0, 1)]
            spec['nativeMappingApplied'] = True

    def stage(path, payload):
        old = path.read_bytes() if path.exists() else None
        if old != payload:
            before[path], pending[path] = old, payload

    for filename, rules in RULES.items():
        path = profile / filename
        if not path.is_file():
            raise ValueError(f'Missing profile contract {path}')
        text, count = rewrite_profile(path.read_bytes().decode('utf-8'), rules, maps)
        stage(path, text.encode('utf-8'))
        records.append({'file': filename, 'coordinatePairs': count})
    definition_paths = [*profile.glob('instances/*.def'), *profile.glob('spawn_groups/**/*.def')]
    if (profile / 'questlines.txt').exists():
        definition_paths.append(profile / 'questlines.txt')
    for path in sorted(definition_paths):
        text, count = rewrite_definition(path.read_bytes().decode('utf-8'), maps)
        if path.name == 'questlines.txt' and 'whitehorn_range' in maps:
            harvest_path = profile / 'harvesting.txt'
            harvest = pending.get(harvest_path, harvest_path.read_bytes()).decode('utf-8')
            targets = [row.split('|') for row in harvest.splitlines() if row.startswith('node')]
            targets = [fields for fields in targets if len(fields) >= 6 and fields[1].strip() == 'whitehorn_range'
                       and fields[2].strip() == '67' and fields[5].strip() == 'Silverleaf']
            if len(targets) != 1:
                raise ValueError('whitehorn_tag requires its existing Silverleaf harvest node 67')
            point = [int(targets[0][3]), int(targets[0][4])]
            text = quest_visit(text, 'whitehorn_tag', 'whitehorn_range', point)
            overrides.append({'quest': 'whitehorn_tag', 'map': 'whitehorn_range', 'node': 67, 'resource': 'Silverleaf',
                              'serverTile': point, 'reason': 'Replace the inherited out-of-grid visit with the existing silverleaf ledge east of the cascade; quest identity, prose and rewards are preserved.'})
        stage(path, text.encode('utf-8'))
        if count:
            records.append({'file': str(path.relative_to(profile)), 'coordinateFields': count})
    for relative, kind in [('tools/generate_nymara_maps.py', 'generator'), ('eloria/map_layout.py', 'layout'),
                           ('eloria/world.py', 'world'), ('eloria/walkthrough.py', 'walkthrough'),
                           ('eloria/pk.py', 'pk'), ('eloria/daily_quests.py', 'daily')]:
        path = server / relative
        stage(path, rewrite_python(path.read_bytes().decode('utf-8'), kind, maps).encode('utf-8'))
    arrival_node = SourceEdits((server / 'tools/generate_nymara_maps.py').read_text(encoding='utf-8')).assignment('ARRIVAL_TILES')
    arrival_by_id = {ast.literal_eval(k): ast.literal_eval(v) for k, v in zip(arrival_node.keys, arrival_node.values)
                     if k is not None and ast.literal_eval(k) in maps}
    known_maps = {entry['id'] for entry in manifest['maps']}
    for region in maps:
        if region not in known_maps:
            manifest['maps'].append({'id': region, 'arrival': list(arrival_by_id[region])})
    for entry in manifest['maps']:
        region = entry['id']
        entry.update(shift_markers(entry, region, maps))
        if region in maps:
            if 'nativeArrival' in maps[region]:
                entry['arrival'] = native_arrival(maps[region])
            entry.update(server_cells=maps[region]['serverCells'][0], server_origin=maps[region]['serverOrigin'])
            maps[region]['arrival'] = entry['arrival']
    for key, value in list(manifest.items()):
        if key in ('maps', STATE):
            continue
        region = next((r for r in sorted(maps, key=len, reverse=True)
                       if key.startswith(r + '_') or r == 'sunmane_steppe' and key in ('sunmane_npcs', 'sunmane_resources')), None)
        if region and isinstance(value, (dict, list)):
            manifest[key] = shift_markers(value, region, maps)
    for region in maps:
        if 'arrival' not in maps[region]:
            raise ValueError(f'{region}: server content manifest lacks map arrival')
    catalog_path = profile / 'invasion_wave_catalog.json'
    if catalog_path.exists():
        catalog = json.loads(catalog_path.read_text(encoding='utf-8'))
        for item in catalog.get('maps', []):
            if item.get('id') in maps:
                item.update(width=maps[item['id']]['serverCells'][0], height=maps[item['id']]['serverCells'][1])
        stage(catalog_path, json_bytes(catalog))
    registry_path = client / 'godot-client/data/maps/registry.json'
    registry = json.loads(registry_path.read_text(encoding='utf-8'))
    for region, spec in maps.items():
        root = package(client, region)
        path = root / 'world.json'
        before[path] = path.read_bytes()
        built = json.loads(before[path])
        transform = built.get('coordinateTransform', {})
        built_cells = transform.get('serverCells', built.get('asset', {}).get('serverCells'))
        if isinstance(built_cells, int):
            built_cells = [built_cells, built_cells]
        valid = (transform.get('serverOrigin') == spec['serverOrigin'] and built_cells == spec['serverCells'])
        valid &= built.get(STATE, {}).get('geographySha256') == digest(raw)
        collision = root / 'collision.bin'
        if collision.exists():
            before[collision] = collision.read_bytes()
            magic, version, _, width, height = struct.unpack('<4sHHII', before[collision][:16])
            valid &= (magic == b'EWCG' and version == 2
                      and [width, height] == [n * 2 for n in spec['serverCells']]
                      and len(before[collision]) >= 16 + width * height)
        else:
            valid = False
        checks.append({'map': region, 'expandedPackageReady': valid})
        if require_built and not valid:
            raise ValueError(f'{region}: expanded client transform/EWCG is not ready')
        entry = registry['maps'].get(region)
        if entry is None:
            raise ValueError(f'{region}: missing client registry identity')
        transform = copy.deepcopy(transform)
        transform.update(serverOrigin=spec['serverOrigin'], serverCells=spec['serverCells'])
        entry['coordinateTransform'] = transform
        # Every geographic exterior authors its crossing in the resident scene.
        # Without this flag the active map adds a generic portal obelisk at a
        # continuous road, which then pops away on the next map handoff.
        entry['landscapeTransitions'] = True
        entry[STATE] = {'translation': spec['translation'], 'geometryMode': 'continent-owned-v1'}
    stage(registry_path, json_bytes(registry))
    runtime = runtime_migration_source(maps)
    compile(runtime, 'continent_geography.py', 'exec')
    stage(server / 'eloria/continent_geography.py', runtime.encode('utf-8'))
    database_path = server / 'eloria/database.py'
    database = database_path.read_bytes().decode('utf-8')
    database = install_geography_hook(database)
    stage(database_path, database.encode('utf-8'))
    # Last profile write is the coordinate-state marker. Other publication
    # stages may regenerate rosters but must retain this map-origin ledger.
    manifest[STATE] = {'schema': 1, 'geographySha256': digest(raw), 'regions': {
        r: {k: v for k, v in spec.items() if k not in ('delta', 'nativeMappingApplied') and not k.startswith('_')} for r, spec in sorted(maps.items())}}
    stage(manifest_path, json_bytes(manifest))
    report = {'schema': 1, 'geographySha256': digest(raw), 'maps': {
                  region: {k: v for k, v in spec.items() if not k.startswith('_')} for region, spec in maps.items()},
              'records': records, 'packageChecks': checks, 'nativeMigrationChecks': native_checks, 'authoredOverrides': overrides,
              'savedPlayers': 'Translated transactionally on next Database initialization; native-compacted Manymouth residents reset once to their safe arrival. Out-of-bounds saves also use their map arrival. Inventory and progression are retained.',
              'files': [{'path': str(p), 'beforeSha256': digest(before[p]) if before[p] is not None else None,
                         'afterSha256': digest(data)} for p, data in pending.items()]}
    return before, pending, report


def install_geography_hook(database):
    """Grid migration precedes older resets that use today's safe arrivals."""
    newline = '\r\n' if '\r\n' in database else '\n'
    hook = ('        from .continent_geography import migrate as migrate_continent_geography\n'
            '        migrate_continent_geography(self.db)\n').replace('\n', newline)
    needle = '        migration = "coastal_landscapes_396_v1"'
    call = 'migrate_continent_geography(self.db)'
    if database.count(needle) != 1 or database.count(call) > 1:
        raise ValueError('Cannot identify the database migration slot before coastal safe arrivals')
    if call in database:
        if database.count(hook) != 1:
            raise ValueError('Unrecognized existing geographic database migration hook')
        if database.index(hook) < database.index(needle):
            return database
        database = database.replace(hook, '')
    return database.replace(needle, hook + needle)


def apply_plan(before, pending):
    """Refuse concurrent changes; rollback every completed file on write failure."""
    for path, expected in before.items():
        actual = path.read_bytes() if path.exists() else None
        if actual != expected:
            raise ValueError(f'Publication input changed during planning: {path}')
    written = []
    try:
        for path, payload in pending.items():
            path.parent.mkdir(parents=True, exist_ok=True)
            written.append(path)
            path.write_bytes(payload)
    except BaseException:
        for path in reversed(written):
            if before[path] is None:
                path.unlink(missing_ok=True)
            else:
                path.write_bytes(before[path])
        raise


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--server', required=True, type=Path)
    parser.add_argument('--client', default=CLIENT, type=Path)
    parser.add_argument('--geography', default=GEOGRAPHY, type=Path)
    parser.add_argument('--apply', action='store_true')
    parser.add_argument('--check', action='store_true', help='Require already-expanded client manifests and EWCG grids')
    parser.add_argument('--report', type=Path)
    args = parser.parse_args()
    before, pending, report = plan(args.client.resolve(), args.server.resolve(), args.geography.resolve(), args.check or args.apply)
    if args.apply:
        apply_plan(before, pending)
    report['applied'] = args.apply
    if args.report:
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_bytes(json_bytes(report))
    print(json.dumps(report, indent=2))


if __name__ == '__main__':
    main()
