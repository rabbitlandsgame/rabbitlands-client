"""Publish one exported continent into stable, named server territories.

The exporter owns geometry and explicit standing-point placements. This tool
owns paired coordinate contracts, never invents content identities, and never
opens a live database. Dry run is the default. --apply writes a validated plan;
--build additionally folds strict authored collision, writes ELMs, regenerates
invasion candidates, and publishes final package digests in sequential steps.
Run through the task's run_limited.py so child builds inherit its CPU ceiling.
"""
from __future__ import annotations

import argparse
import ast
import copy
import hashlib
import json
import math
import os
from pathlib import Path
import struct
import subprocess
import sys

import publish_continent_geography as shared

CLIENT = Path(__file__).resolve().parents[2]
CONTINENT = CLIENT / 'eloria-assets/maps/nymara-regions/_continent'
if str(CONTINENT) not in sys.path:
    sys.path.insert(0, str(CONTINENT))
from storage_bounds import StorageBounds, authoring_storage, storage_record
PUBLICATION = CLIENT / 'eloria-assets/maps/nymara-regions/_continent/publication.json'
STATE = 'diagonalContinent'
BEGIN = '# --- Diagonal continent crossings: generated from the shared continent ---'
END = '# --- end diagonal continent crossings ---'
CONTENT = {'npcs.txt': ('npc', 2, 3, 4, 'npcs', 1),
           'harvesting.txt': ('node', 1, 3, 4, 'harvest', 2),
           'spawns.txt': ('spawn', 1, 3, 4, 'spawns', None),
           'interactives.txt': (None, 0, 2, 3, 'interactives', 1)}
TILE_FIELDS = {'serverTile', 'server_tile', 'arrival', 'spawnTile', 'destinationTile',
               'targetTile', 'returnTile', 'exitTile'}
WORLD_FIELDS = {'targetPosition', 'destinationPosition', 'returnPosition'}


def read_json(path):
    return json.loads(path.read_text(encoding='utf-8'))


def resolve_input(client, publication, value):
    path = Path(value)
    if not path.is_absolute():
        path = publication.parent / path
    path = path.resolve()
    if not path.is_relative_to(client.resolve()):
        raise ValueError(f'Export input escapes the client checkout: {path}')
    if not path.is_file():
        raise ValueError(f'Missing exported continent input: {path}')
    return path


def point_key(point):
    x, y = shared.integer_pair(point, 'standing point')
    return f'{x}:{y}'


def content_local(transform, x, z, translation):
    """A source point (x, z) in continent metres relative to the territory's centre.

    ``scale`` about ``sourceCenter``, plus ``targetCenter``, is the rule for a layout that only scales. A layout
    that turns or squeezes per axis publishes ``scale`` null with its exact ``affine`` [a, b, c, d, e, f]:
    continent X = a*x + b*z + e and Z = c*x + d*z + f in absolute metres, so the centre, the spec's
    ``translation``, comes off it."""
    scale = transform['scale']
    if scale is None:
        a, b, c, d, e, f = transform['affine']
        return a * x + b * z + e - translation[0], c * x + d * z + f - translation[2]
    source, target = transform['sourceCenter'], transform['targetCenter']
    return (x - source[0]) * scale + target[0], (z - source[1]) * scale + target[1]


def transform_tile(point, spec):
    explicit = spec.get('tilePositions', {}).get(point_key(point))
    if explicit is not None:
        return list(shared.integer_pair(explicit, 'exact standing point'))
    old = spec['previousServerOrigin']
    origin = spec['serverOrigin']
    # Server coordinates name cell centres; server Y runs opposite local Z.
    x, z = content_local(spec['contentTransform'], point[0] + .5 - old[0], old[1] - point[1] - .5, spec.get('translation'))
    return [math.floor(x + origin[0]), math.floor(origin[1] - z)]


def world_point(region, tile, specs):
    spec = specs[region]
    return (round(tile[0] + .5 - spec['serverOrigin'][0] + spec['translation'][0], 6),
            round(spec['serverOrigin'][1] - tile[1] - .5 + spec['translation'][2], 6))


def destination_tile(region, point, specs):
    """The tile of `region` under a global cell centre, or None where it has none.

    Every territory's tile grid is the same metre grid in the shared frame, so
    a crossing that hands a walker over at the cell they stand on only has to
    read that cell in the other map's own numbering.
    """
    spec = specs[region]
    x = int(round(point[0] - spec['translation'][0] + spec['serverOrigin'][0] - .5))
    y = int(round(spec['serverOrigin'][1] + spec['translation'][2] - point[1] - .5))
    if not StorageBounds.from_metadata(spec['serverCells'], spec).contains(x, y):
        return None
    return [x, y] if world_point(region, (x, y), specs) == point else None


def validate_spec(region, spec, previous):
    for name in ('serverOrigin', 'previousServerOrigin', 'serverCells', 'arrival'):
        spec[name] = list(shared.integer_pair(spec.get(name), f'{region}.{name}'))
    size = spec['serverCells']
    storage_record(size, spec)
    if size[0] != size[1] or size[0] <= 0 or size[0] % 6:
        raise ValueError(f'{region}: served envelope must be square and divisible by six')
    if previous and spec['previousServerOrigin'] != previous.get('serverOrigin'):
        raise ValueError(f'{region}: export was authored against a different server address frame')
    transform = spec.get('contentTransform', {})
    if transform.get('scale') is None and 'scale' in transform:
        affine = transform.get('affine')
        if (not isinstance(affine, list) or len(affine) != 6
                or not all(isinstance(n, (int, float)) and not isinstance(n, bool) and math.isfinite(n) for n in affine)):
            raise ValueError(f'{region}: a contentTransform with no uniform scale requires its exact affine')
        if affine[0] * affine[3] - affine[1] * affine[2] <= 0:
            raise ValueError(f'{region}: contentTransform affine must keep orientation and area')
    elif not isinstance(transform.get('scale'), (int, float)) or transform['scale'] <= 0:
        raise ValueError(f'{region}: contentTransform requires a positive uniform scale')
    for key in ('sourceCenter', 'targetCenter'):
        if len(transform.get(key, [])) != 2 or not all(isinstance(n, (int, float)) and math.isfinite(n) for n in transform[key]):
            raise ValueError(f'{region}: contentTransform.{key} requires two finite coordinates')
    translation = spec.get('translation', [])
    if len(translation) != 3 or not all(isinstance(n, (int, float)) and math.isfinite(n) for n in translation):
        raise ValueError(f'{region}: translation requires three finite coordinates')
    if not spec.get('terrainRevision'):
        raise ValueError(f'{region}: reshaped terrain must declare a save migration revision')
    spec.setdefault('tilePositions', {})
    for portal, value in spec.get('portalPositions', {}).items():
        if not isinstance(value, dict) or 'oldTile' not in value or 'tile' not in value:
            raise ValueError(f'{region}.{portal}: portalPositions requires oldTile and tile')
        spec['tilePositions'][point_key(value['oldTile'])] = list(shared.integer_pair(value['tile'], portal))
    bindings = spec.get('runtimeBindings', {})
    positions = spec.get('runtimeBindingPositions', {})
    source_tiles = spec.get('runtimeBindingSourceTiles', {})
    if set(bindings) != set(positions) or set(bindings) != set(source_tiles):
        missing = sorted(set(bindings) - set(positions))
        extra = sorted(set(positions) - set(bindings))
        missing_sources = sorted(set(bindings) - set(source_tiles))
        raise ValueError(f'{region}: runtime binding positions disagree with bindings; '
                         f'missing={missing[:4]}, extra={extra[:4]}, missingSources={missing_sources[:4]}')
    for identity, tile in positions.items():
        positions[identity] = list(shared.integer_pair(tile, f'{region}.runtimeBindingPositions.{identity}'))
        source_tiles[identity] = list(shared.integer_pair(
            source_tiles[identity], f'{region}.runtimeBindingSourceTiles.{identity}'))


def storage_fields(spec):
    """Carry declared storage while preserving unversioned legacy output shape."""
    if any(key in spec for key in ('serverStorageVersion', 'serverTileMin', 'authoringSpecSha256')):
        return storage_record(spec['serverCells'], spec)
    return {}


def validate_package_storage(region, spec, world, collision_bytes):
    """A spec, package, collision and publication certificate name one storage."""
    wanted = storage_record(spec['serverCells'], spec)
    transform = world['coordinateTransform']
    if (transform['serverOrigin'] != spec['serverOrigin'] or
            storage_record(transform['serverCells'], transform) != wanted):
        raise ValueError(f'{region}: final client package and publication use different address/storage frames')
    collision = world.get('collision', {})
    if storage_record(collision.get('serverCells', spec['serverCells']), collision) != wanted:
        raise ValueError(f'{region}: collision storage certificate differs from publication')
    bounds = StorageBounds.from_metadata(spec['serverCells'], spec)
    origin = list(bounds.physical_origin(spec['serverOrigin']))
    authoring_storage({'origin':spec['serverOrigin'], 'cells':spec['serverCells'], **bounds.metadata(),
        'localOrigin':transform.get('origin',[0,0,0]), 'metresPerTile':transform.get('metresPerTile',1),
        'invertServerY':transform.get('invertServerY',True),
        **({'walkingHeight':transform['walkingHeight']} if 'walkingHeight' in transform else {}),
        'collisionOriginMetres':collision.get('originMetres',origin)})
    if 'addressableWorldBounds' in transform:
        expected = dict(zip(('min','max'),bounds.physical_bounds(spec['serverOrigin'])))
        if transform['addressableWorldBounds'] != expected:
            raise ValueError(f'{region}: addressable physical bounds differ from storage')
    for name in ('continentPublication', 'singleContinentSource', 'streamingChunks'):
        certificate = world.get(name,{})
        if 'storage' in certificate and certificate['storage'] != wanted:
            raise ValueError(f'{region}: {name} storage certificate differs from publication')
    certificate = world.get('continentPublication', {})
    if 'collisionSha256' in certificate and certificate['collisionSha256'] != shared.digest(collision_bytes):
        raise ValueError(f'{region}: final collision bytes differ from publication certificate')
    return wanted


def instance_exit_records(relative, text, regions):
    """Identify exterior instance exits without using their mutable coordinates."""
    result = {}
    def observe(region, old, context):
        if context['section'] != 'instance' or context['pairKind'] != 'exit':
            return None
        if (not relative.startswith('config/eloria/instances/') or
                context['recordField'] != 'spawn_name' or not context['recordId'] or
                context['fields'] != ['exit_x', 'exit_y'] or context['map'] != region):
            raise ValueError(f'{relative}: instance exit requires a named, complete source context')
        identity = json.dumps([relative, context['recordId'], 'exit_x', 'exit_y', region],
                              separators=(',', ':'), ensure_ascii=False)
        if identity in result:
            raise ValueError(f'{relative}: duplicate instance exit context {identity}')
        result[identity] = {'path': relative, 'spawnName': context['recordId'],
                            'fields': ['exit_x', 'exit_y'], 'map': region, 'originalTile': list(old),
                            'line': context['sourceIndices'][0] + 1}
        return list(old)
    shared.rewrite_definition(text, {r: {'delta': [0, 0]} for r in regions}, point_mapper=observe)
    return result


def certified_instance_exit_sources(client, regions):
    root = client / 'eloria-assets/maps/nymara-regions/_continent/legacy-server-profile'
    certificate = json.loads((root / 'snapshot.json').read_text(encoding='utf-8'))
    result = {}
    for relative, expected in certificate['files'].items():
        if not relative.startswith('config/eloria/instances/') or not relative.endswith('.def'):
            continue
        payload = (root / relative).read_bytes()
        if shared.digest(payload) != expected:
            raise ValueError(f'{relative}: immutable instance source digest changed')
        for identity, source in instance_exit_records(relative, payload.decode('utf-8'), regions).items():
            source['sha256'] = expected
            result[identity] = source
    return result


def validate_instance_binding(client, identity, source, binding):
    """Join one saved control to a coordinate-free, committed source amendment."""
    if not isinstance(binding, dict) or binding.get('id') != identity:
        raise ValueError(f'{identity}: exact authored instance binding is missing')
    bound_source = binding.get('source', {})
    wanted = {'path': source['path'], 'recordId': source['spawnName'],
              'line': source['line'], 'fields': ['exit_x', 'exit_y'], 'oldTile': source['originalTile']}
    if {k: v for k, v in bound_source.items() if k != 'amendmentReport'} != wanted:
        raise ValueError(f'{identity}: authored instance source identity differs from certified definition')
    marker = binding.get('marker', {})
    if (binding.get('role') != 'return' or binding.get('roads') != 'marker' or binding.get('aliases') != [] or
            binding.get('targetOffset') != [0, 0, 0] or marker.get('section') != 'runtimePoints' or
            not isinstance(marker.get('id'), str) or not marker['id']):
        raise ValueError(f'{identity}: instance exit needs an independent, unoffset return control')
    if binding.get('provenance', {}).get('sourceProfileSha256') != source['sha256']:
        raise ValueError(f'{identity}: instance source profile digest differs')
    amendment = bound_source.get('amendmentReport', {})
    relative = amendment.get('path', '')
    if not isinstance(relative, str) or not relative or Path(relative).is_absolute() or '..' in Path(relative).parts:
        raise ValueError(f'{identity}: invalid instance amendment path')
    path = (client / relative).resolve()
    if not path.is_relative_to(client.resolve()) or not path.is_file():
        raise ValueError(f'{identity}: committed instance amendment is missing')
    payload = path.read_bytes()
    if shared.digest(payload) != amendment.get('sha256'):
        raise ValueError(f'{identity}: committed instance amendment digest differs')
    report = json.loads(payload)
    if report.get('schema') != 'eloria-instance-exit-binding-amendment-v1' or not isinstance(report.get('records'), list):
        raise ValueError(f'{identity}: unsupported instance amendment schema')
    records = {}
    for row in report['records']:
        if not isinstance(row, dict) or not isinstance(row.get('id'), str) or row['id'] in records:
            raise ValueError(f'{identity}: duplicate or invalid amendment identity')
        records[row['id']] = row
    wanted_row = {'id': identity, 'region': source['map'],
                  'source': {**wanted, 'sha256': source['sha256']}, 'marker': marker}
    if records.get(identity) != wanted_row:
        raise ValueError(f'{identity}: amendment source/region/marker association differs')
    return records


def validate_authored_instance_entries(client, specs, sources, entries):
    amendment_source = None
    for region, spec in specs.items():
        for identity, entry in spec['instanceExitPositions'].items():
            binding = entry.get('authoredBinding')
            if binding != spec.get('runtimeBindings', {}).get(identity):
                raise ValueError(f'{identity}: independent instance binding differs from publication bindings')
            amendment = validate_instance_binding(client, identity, sources[identity], binding)
            reference = binding['source']['amendmentReport']
            if amendment_source is None:
                amendment_source = reference
            elif reference != amendment_source:
                raise ValueError('Authored instance exits require one identical amendment report')
            if set(amendment) != set(sources):
                raise ValueError('Instance amendment does not exactly cover all certified definitions')
            if (spec.get('runtimeBindingPositions', {}).get(identity) != entry['tile'] or
                    spec.get('runtimeBindingSourceTiles', {}).get(identity) != sources[identity]['originalTile']):
                raise ValueError(f'{identity}: independent instance binding target/source differs')
            expected = entry.get('expectedSource', {})
            point = expected.get('globalPosition')
            if (expected.get('bindingId') != identity or expected.get('region') != region or
                    expected.get('marker') != binding['marker'] or
                    expected.get('serverOrigin') != spec['serverOrigin'] or
                    expected.get('translation') != spec['translation'] or
                    not isinstance(point, list) or len(point) != 3 or
                    any(type(v) not in (int, float) or not math.isfinite(v) for v in point)):
                raise ValueError(f'{identity}: invalid saved instance expected-point provenance')
            projected = [point[0] - spec['translation'][0] + spec['serverOrigin'][0] - .5,
                         spec['serverOrigin'][1] - (point[2] - spec['translation'][2]) - .5]
            if projected != entry['expectedTile']:
                raise ValueError(f'{identity}: expected tile differs from its saved authored point')


def validate_instance_exit_table(specs, sources, *, client=None, require_authored=False):
    """Require one independently placed record for every certified source exit."""
    entries = {}
    for region, spec in specs.items():
        table = spec.get('instanceExitPositions')
        if not isinstance(table, dict):
            raise ValueError(f'{region}: missing instance exit table')
        for identity, entry in table.items():
            expected_source = copy.deepcopy(sources.get(identity))
            # Schema 1 predates explicit source lines and authored exit controls.
            if not require_authored and isinstance(expected_source, dict) and 'line' not in entry.get('source', {}):
                expected_source.pop('line', None)
            if identity in entries or identity not in sources or entry.get('source') != expected_source:
                raise ValueError(f'{identity}: duplicate or changed instance source provenance')
            if entry['source']['map'] != region:
                raise ValueError(f'{identity}: instance exit is stored under the wrong region')
            for field in ('previousTile', 'tile'):
                pair = entry.get(field)
                if (not isinstance(pair, list) or len(pair) != 2 or
                        any(type(v) is not int for v in pair)):
                    raise ValueError(f'{identity}: invalid instance {field}')
            expected = entry.get('expectedTile')
            if (not isinstance(expected, list) or len(expected) != 2 or
                    any(type(v) not in (int, float) or not math.isfinite(v) for v in expected) or
                    entry.get('maximumDisplacementMetres') != 5 or
                    math.dist(expected, entry['tile']) > 5 + 1e-8):
                raise ValueError(f'{identity}: independent instance placement exceeds its five metre budget')
            if entry.get('postContent') != {'standing': True, 'hubAccessible': True, 'noPortalTrigger': True}:
                raise ValueError(f'{identity}: missing post-content instance access proof')
            entries[identity] = entry
    if set(entries) != set(sources):
        raise ValueError('Instance exit table is incomplete for the certified source inventory')
    if require_authored:
        validate_authored_instance_entries(CLIENT if client is None else client, specs, sources, entries)
    return entries


def rewrite_instance_exits(relative, text, mappings, entries, *, mode):
    """Use the same identity join for guard reconstruction and actual publication."""
    found = instance_exit_records(relative, text, mappings)
    wanted = {k: v for k, v in entries.items() if v['source']['path'] == relative}
    if set(found) != set(wanted):
        raise ValueError(f'{relative}: missing or unexpected instance exit context')
    for identity, source in found.items():
        entry = wanted[identity]
        expected = (entry['source']['originalTile'] if mode == 'source' else
                    entry['tile'] if mode == 'repeated' else entry['previousTile'])
        if source['originalTile'] != expected:
            raise ValueError(f'{identity}: instance field differs from certified {mode} coordinates')
    def mapper(region, old, context):
        if context['section'] != 'instance' or context['pairKind'] != 'exit':
            return None
        identity = json.dumps([relative, context['recordId'], 'exit_x', 'exit_y', region],
                              separators=(',', ':'), ensure_ascii=False)
        return list(wanted[identity]['tile'])
    return shared.rewrite_definition(text, mappings, point_mapper=mapper)


def _runtime_binding_profile_texts(client, specs):
    """Load the immutable profile rows named by authored binding provenance."""
    expected = {}
    for spec in specs.values():
        for binding in spec.get('runtimeBindings', {}).values():
            path = binding['source']['path']
            if path not in ('config/eloria/maps.txt', 'config/eloria/territories.txt'):
                continue
            filename = path.removeprefix('config/eloria/')
            sha = binding.get('provenance', {}).get('sourceProfileSha256')
            if not sha:
                raise ValueError(f'{binding["id"]}: runtime binding lacks sourceProfileSha256')
            if filename in expected and expected[filename] != sha:
                raise ValueError(f'{filename}: runtime bindings name conflicting certified profiles')
            expected[filename] = sha
    result = {}
    root = client / 'eloria-assets/maps/nymara-regions/_continent/legacy-server-profile/config/eloria'
    for filename, sha in expected.items():
        path = root / filename
        payload = path.read_bytes()
        if shared.digest(payload) != sha:
            raise ValueError(f'{filename}: certified runtime binding profile digest changed')
        result[filename] = payload.decode('utf-8')
    return result


def _runtime_binding_live_line(filename, identity, binding, old, current_text,
                               certified_text, previous_tile):
    """Resolve one immutable binding onto the current, possibly republished row."""
    source = binding['source']
    line_number = int(source['line'])
    certified = certified_text.splitlines()
    if line_number <= 0 or line_number > len(certified):
        raise ValueError(f'{identity}: certified source line is unavailable')
    fields = certified[line_number - 1].split('|')
    live = current_text.splitlines()
    expected = previous_tile if previous_tile is not None else old

    if filename == 'maps.txt':
        if not fields or fields[0].strip() != 'portal' or len(fields) not in (7, 8):
            raise ValueError(f'{identity}: certified maps source is no longer a portal row')
        start = 2 if len(fields) == 7 else 3
        role = binding['role']
        index = start if role == 'door' else start + 3 if role == 'return' else None
        if index is None or [int(fields[index]), int(fields[index + 1])] != old:
            raise ValueError(f'{identity}: portal role or old tile changed in its certified profile')
        stable = (0, 1, 4) if len(fields) == 7 else (0, 1, 2, 5)
        signature = tuple(fields[i].strip() for i in stable)
        record_id = source.get('recordId')
        if record_id:
            certified_id = fields[2].strip() if len(fields) == 8 else f'{fields[2].strip()}:{fields[3].strip()}'
            if certified_id != str(record_id):
                raise ValueError(f'{identity}: certified portal recordId changed')
        candidates = []
        for number, line in enumerate(live, 1):
            candidate = line.split('|')
            if len(candidate) != len(fields):
                continue
            if tuple(candidate[i].strip() for i in stable) != signature:
                continue
            if [int(candidate[index]), int(candidate[index + 1])] == expected:
                candidates.append((number, index))
    else:
        occurrences = [index for index in range(len(fields) - 1)
                       if fields[index].strip() == str(old[0])
                       and fields[index + 1].strip() == str(old[1])]
        if len(occurrences) != 1:
            raise ValueError(f'{identity}: territory old tile is absent or ambiguous in its certified profile')
        index = occurrences[0]
        signature = tuple(value.strip() for value in fields[:4])
        candidates = []
        for number, line in enumerate(live, 1):
            candidate = line.split('|')
            if len(candidate) != len(fields) or tuple(value.strip() for value in candidate[:4]) != signature:
                continue
            if [int(candidate[index]), int(candidate[index + 1])] == expected:
                candidates.append((number, index))
    if len(candidates) != 1:
        raise ValueError(f'{identity}: current source row is absent or ambiguous for certified tile {expected}')
    return candidates[0]


def rewrite_runtime_binding_sources(original_texts, rewritten_texts, specs,
                                    previous_placements=None, certified_texts=None):
    """Apply exact saved coordinates to source rows whose old tiles are not unique.

    The normal native mapper is intentionally tile based. Runtime authoring is
    record based, so maps and multi-point territory rows are patched by their
    certified source line after the ordinary transform has run.
    """
    for region, spec in specs.items():
        for identity, binding in spec.get('runtimeBindings', {}).items():
            source = binding['source']
            path = source['path']
            if path not in ('config/eloria/maps.txt', 'config/eloria/territories.txt'):
                continue
            filename = path.removeprefix('config/eloria/')
            if filename not in original_texts or filename not in rewritten_texts:
                raise ValueError(f'{region}:{identity}: bound source {path} was not loaded')
            original_text = original_texts[filename]
            original = original_text.splitlines(keepends=True)
            rewritten = rewritten_texts[filename].splitlines(keepends=True)
            if len(original) != len(rewritten):
                raise ValueError(f'{region}:{identity}: current source row count changed during rewrite')
            old = list(shared.integer_pair(
                spec['runtimeBindingSourceTiles'][identity], f'{identity}.runtimeBindingSourceTile'))
            prior = None
            if previous_placements:
                previous = previous_placements.get(region, {})
                # Record-bound aliases may share one immutable source tile but
                # have distinct served positions.  Their qualified binding
                # history is the exact live-row identity; the collapsed tile
                # map remains only a compatibility fallback for publications
                # that predate runtime binding positions.
                prior = previous.get('runtimeBindingPositions', {}).get(identity)
                if prior is None:
                    prior = previous.get('baselineTilePositions', {}).get(point_key(old))
                if prior is not None:
                    prior = list(shared.integer_pair(prior, f'{identity}.previousRuntimeBindingTile'))
            certified = original_text if certified_texts is None else certified_texts.get(filename)
            if certified is None:
                raise ValueError(f'{region}:{identity}: certified source profile was not loaded')
            line_number, index = _runtime_binding_live_line(
                filename, f'{region}:{identity}', binding, old, original_text, certified, prior)
            original_line = original[line_number - 1]
            output_line = rewritten[line_number - 1]
            ending = '\r\n' if output_line.endswith('\r\n') else '\n' if output_line.endswith('\n') else ''
            fields = original_line.rstrip('\r\n').split('|')
            output = output_line.rstrip('\r\n').split('|')
            tile = spec['runtimeBindingPositions'][identity]
            output[index] = shared.field_number(output[index], tile[0])
            output[index + 1] = shared.field_number(output[index + 1], tile[1])
            rewritten[line_number - 1] = '|'.join(output) + ending
            rewritten_texts[filename] = ''.join(rewritten)


def content_source_tile_counts(texts):
    """Count content source tiles across all profile files, including other record types."""
    counts = {}
    for filename, text in texts.items():
        keyword, mi, xi, yi, _, _ = CONTENT[filename]
        for line in text.splitlines():
            fields = [field.strip() for field in line.split('|')]
            if line.lstrip().startswith('#') or len(fields) <= max(mi, xi, yi):
                continue
            if keyword is not None and fields[0] != keyword:
                continue
            source_key = (fields[mi], point_key([int(fields[xi]), int(fields[yi])]))
            counts[source_key] = counts.get(source_key, 0) + 1
    return counts


def rewrite_content(text, filename, specs, repeated, source_tile_counts=None):
    keyword, mi, xi, yi, group, identity_index = CONTENT[filename]
    rows, counts, used, retired = [], {}, {}, {}
    if source_tile_counts is None:
        source_tile_counts = content_source_tile_counts({filename: text})
    source_identity_counts = {}
    if identity_index is not None:
        for source_line in text.splitlines():
            source = [field.strip() for field in source_line.split('|')]
            if source_line.lstrip().startswith('#') or len(source) <= max(mi, xi, yi):
                continue
            if source[mi] not in specs or keyword is not None and source[0] != keyword:
                continue
            source_identity = (source[mi], source[identity_index])
            source_identity_counts[source_identity] = source_identity_counts.get(source_identity, 0) + 1
    for line_number, line in enumerate(text.splitlines(keepends=True), 1):
        fields = line.split('|')
        if line.lstrip().startswith('#') or len(fields) <= max(mi, xi, yi):
            rows.append(line)
            continue
        region = fields[mi].strip()
        if region not in specs or keyword is not None and fields[0].strip() != keyword:
            rows.append(line)
            continue
        old = [int(fields[xi]), int(fields[yi])]
        ordinal = counts.get(region, 0)
        counts[region] = ordinal + 1
        identity = str(ordinal) if identity_index is None else fields[identity_index].strip()
        spec = specs[region]
        if filename == 'interactives.txt' and identity in {str(value) for value in spec.get('removedInteractiveIds', [])}:
            if len(fields) < 6 or fields[4].strip() != 'portal' or fields[5].strip() != 'maps.txt':
                raise ValueError(f'{region}.{identity}: only obsolete generic portal interactives can be removed')
            retired.setdefault(region, set()).add(identity)
            continue
        used.setdefault(region, set()).add(identity)
        explicit = spec.get('contentPositions', {}).get(group, {}).get(identity)
        new = (list(shared.integer_pair(explicit, f'{region}.{group}.{identity}')) if explicit is not None
               else old if repeated else transform_tile(old, spec))
        if not repeated:
            key = point_key(old)
            existing = spec['tilePositions'].get(key)
            if existing is not None and list(existing) != new:
                unique_content_record = (explicit is not None and
                                         source_tile_counts[(region, key)] == 1 and
                                         (identity_index is None or source_identity_counts[(region, str(identity))] == 1))
                # A unique saved content row has its own stable ID even when
                # an unrelated portal uses the same generic tile mapping.
                # Preserve a meaningful non-identity mapping; only replace
                # an identity mapping. Shared content source tiles instead
                # require a qualified saved row/identity binding.
                qualified = [binding_id for binding_id, binding in spec.get('runtimeBindings', {}).items()
                    if binding.get('role') == group and
                    binding.get('source', {}).get('path') == 'config/eloria/' + filename and
                    binding['source'].get('line') == line_number and
                    str(binding['source'].get('recordId')) == str(identity) and
                    binding['source'].get('oldTile') is not None and
                    binding['source']['oldTile'] == spec.get('runtimeBindingSourceTiles', {}).get(binding_id) and
                    (binding['source']['oldTile'] == old or
                     spec.get('baselineTilePositions', {}).get(point_key(binding['source']['oldTile'])) == old) and
                    spec.get('runtimeBindingPositions', {}).get(binding_id) == new]
                if not unique_content_record and (explicit is None or len(qualified) != 1):
                    raise ValueError(f'{region}: conflicting authored destinations for standing point {key}')
            elif explicit is None:
                spec['tilePositions'][key] = new
        fields[xi], fields[yi] = shared.field_number(fields[xi], new[0]), shared.field_number(fields[yi], new[1])
        rows.append('|'.join(fields))
    for region, spec in specs.items():
        expected = set(spec.get('contentPositions', {}).get(group, {}))
        if filename == 'interactives.txt':
            expected -= {str(value) for value in spec.get('removedInteractiveIds', [])}
        missing = expected - used.get(region, set()) - retired.get(region, set())
        if missing:
            raise ValueError(f'{region}.{group}: exported identities absent from the source profile: {sorted(missing)}')
        if filename == 'interactives.txt' and not repeated:
            missing = {str(value) for value in spec.get('removedInteractiveIds', [])} - retired.get(region, set())
            if missing:
                raise ValueError(f'{region}: removedInteractiveIds absent from source profile: {sorted(missing)}')
    return ''.join(rows), counts


def runtime_specs(specs, previous):
    result = {}
    for region, spec in specs.items():
        legacy = previous.get(region, {})
        result[region] = {key: copy.deepcopy(spec[key]) for key in (
            'serverOrigin', 'serverCells', 'arrival', 'translation', 'terrainRevision')}
        result[region].update(storage_fields(spec))
        result[region].update(nativeServerOrigin=legacy.get('nativeServerOrigin', spec['previousServerOrigin']),
                              nativeServerCells=legacy.get('nativeServerCells', spec['serverCells']),
                              previousServerOrigin=spec['previousServerOrigin'],
                              contentTransform=copy.deepcopy(spec['contentTransform']))
        if legacy.get('nativeRevision'):
            result[region]['nativeRevision'] = legacy['nativeRevision']
    return result


def placement_contracts(specs):
    """Vendor immutable landmark correspondence for standalone server checks.

    Keep the baseline table on later publications: tilePositions is then keyed
    by the previous diagonal layout, not by the original semantic source frame.
    """
    return {region: {
        **({'storage':storage_fields(spec)} if storage_fields(spec) else {}),
        'baselineServerOrigin': copy.deepcopy(spec.get('baselineServerOrigin', spec['previousServerOrigin'])),
        'baselineTilePositions': copy.deepcopy(spec.get('baselineTilePositions', spec.get('tilePositions', {}))),
        'baselineContentTransform': copy.deepcopy(spec.get('baselineContentTransform', spec['contentTransform'])),
        'contentPositions': copy.deepcopy(spec.get('contentPositions', {})),
        'portalPositions': copy.deepcopy(spec.get('portalPositions', {})),
        **({'instanceExitPositions': copy.deepcopy(spec['instanceExitPositions'])}
           if 'instanceExitPositions' in spec else {}),
        'runtimeBindings': copy.deepcopy(spec.get('runtimeBindings', {})),
        'runtimeBindingPositions': copy.deepcopy(spec.get('runtimeBindingPositions', {})),
        'runtimeBindingSourceTiles': copy.deepcopy(spec.get('runtimeBindingSourceTiles', {})),
    } for region, spec in specs.items()}


def rewrite_exact_arrivals(text, kind, specs):
    edit = shared.SourceEdits(text)
    if kind == 'generator':
        edit.replace(edit.assignment('FOUR_GATES_TILES_WIDE'), specs['four_gates']['serverCells'][0] // 6)
        for name, field in (('MAP_TILES_WIDE_BY_NAME', 'serverCells'), ('ARRIVAL_TILES', 'arrival')):
            node = edit.assignment(name)
            for key, value in zip(node.keys, node.values):
                region = ast.literal_eval(key) if key else None
                if region in specs:
                    edit.replace(value, specs[region][field][0] // 6 if field == 'serverCells' else tuple(specs[region][field]))
    else:
        edit.replace(edit.assignment('FOUR_GATES_ARRIVAL'), tuple(specs['four_gates']['arrival']))
        for name in ('COASTAL_ARRIVALS', 'SOUTHERN_ARRIVALS'):
            node = edit.assignment(name)
            for key, value in zip(node.keys, node.values):
                region = ast.literal_eval(key)
                if region in specs and not isinstance(value, ast.Name):
                    edit.replace(value, tuple(specs[region]['arrival']))
    return edit.finish()


def rewrite_gameplay_source(text, kind, mappings):
    if kind not in ('world', 'walkthrough'):
        return shared.rewrite_python(text, kind, mappings)
    edit = shared.SourceEdits(text)
    if kind == 'walkthrough':
        node = edit.assignment('PLAZA')
        edit.replace(node, tuple(shared.shifted(ast.literal_eval(node), 'four_gates', mappings)))
    else:
        node = edit.assignment('TUTORIAL_ROUTE_MARKERS')
        edit.replace(node, tuple(tuple(shared.shifted(point, 'four_gates', mappings)) for point in ast.literal_eval(node)))
        node = edit.assignment('TUTORIAL_HARVESTS')
        edit.replace(node, tuple((point[0], *shared.shifted(point[1:3], 'four_gates', mappings), *point[3:])
                                 for point in ast.literal_eval(node)))
    return edit.finish()


def remap_metadata(value, specs, mapping, region=None):
    if isinstance(value, list):
        return [remap_metadata(item, specs, mapping, region) for item in value]
    if not isinstance(value, dict):
        return value
    own = value.get('map_id', value.get('map', region))
    result = {}
    for key, item in value.items():
        if key in (STATE, 'continentGeography', 'geographicFamily'):
            result[key] = item
            continue
        target = own
        if key in ('destinationTile', 'destinationPosition', 'targetTile', 'targetPosition'):
            target = value.get('destinationMap', value.get('destination', value.get('targetMap')))
        elif key in ('returnTile', 'exitTile', 'returnPosition'):
            target = value.get('returnMap', value.get('exitMap', value.get('exit_map')))
        if key in TILE_FIELDS and target in specs and isinstance(item, list) and len(item) == 2:
            result[key] = shared.shifted(item, target, mapping)
        elif key in WORLD_FIELDS and target in specs and isinstance(item, list) and len(item) == 3:
            spec = specs[target]
            old = [math.floor(item[0] + spec['previousServerOrigin'][0]),
                   math.floor(spec['previousServerOrigin'][1] - item[2])]
            tile = shared.shifted(old, target, mapping)
            height=spec.get('tileHeights',{}).get(f'{tile[0]}:{tile[1]}',item[1])
            result[key] = [tile[0] + .5 - spec['serverOrigin'][0], height,
                           spec['serverOrigin'][1] - tile[1] - .5]
        else:
            result[key] = remap_metadata(item, specs, mapping, own)
    return result


def connection_rows(connections, specs):
    lines, entries, identities, sources = [], [], set(), set()
    for connection in connections:
        identity = connection['id']
        if identity in identities or len(connection.get('ends', [])) != 2:
            raise ValueError(f'{identity}: connection identity must be unique with two ends')
        identities.add(identity)
        a, b = connection['ends']
        if a['region'] not in specs or b['region'] not in specs or a['region'] == b['region']:
            raise ValueError(f'{identity}: connection must join two exported territories')
        seamless = connection.get('type', 'land') not in ('ferry', 'ship', 'boat', 'teleport')
        lines.append(f'# {identity} ({connection.get("type", "land")})\n')
        for source, destination in ((a, b), (b, a)):
            lanes = source.get('lanes', [{'tile': source['tile'], 'arrival': source['arrival']}])
            for lane in lanes:
                tile = list(shared.integer_pair(lane['tile'], identity + ' departure'))
                # A seamless crossing hands the walker over at the very cell
                # they are standing on, so the arrival is that cell read in the
                # destination's own tile frame. While a seam was a gate seven
                # lanes wide this was found by matching the far side's own lane
                # list, which needs the two sides to have lane for lane the same
                # tiles; a border crossed along its length has one more tile on
                # the outside of every step in it than on the inside.
                arrival = (destination_tile(destination['region'], world_point(source['region'], tile, specs), specs)
                           if seamless else destination['arrival'])
                if arrival is None:
                    raise ValueError(f'{identity}: departure {tile} of {source["region"]} stands on no cell of {destination["region"]}')
                arrival = list(shared.integer_pair(arrival, identity + ' arrival'))
                trigger = (source['region'], *tile)
                if trigger in sources:
                    raise ValueError(f'{identity}: duplicate exterior departure {trigger}')
                sources.add(trigger)
                entries.append((source['region'], *tile, destination['region'], *arrival))
                lines.append('portal | ' + ' | '.join(map(str, entries[-1])) + '\n')
    triggered = [(source, x, y, target, tx, ty) for source, x, y, target, tx, ty in entries if (target, tx, ty) in sources]
    if triggered:
        source, x, y, target, tx, ty = triggered[0]
        raise ValueError(f'{source}->{target}: arrival immediately triggers another exterior crossing: '
                         + ', '.join(f'{s} {[a, b]} -> {t} {[c, d]}' for s, a, b, t, c, d in triggered[:8])
                         + f' ({len(triggered)} in all)')
    return ''.join(lines), entries


def replace_crossings(text, connections, specs):
    if BEGIN in text:
        if END not in text:
            raise ValueError('Previous diagonal crossing block is incomplete')
        start, stop = text.index(BEGIN), text.index(END) + len(END)
        text = text[:start] + text[stop:]
    rows = []
    for line in text.splitlines(keepends=True):
        fields = [field.strip() for field in line.split('|')]
        if len(fields) in (7, 8) and fields[0] == 'portal':
            mi = 4 if len(fields) == 7 else 5
            if fields[1] in specs and fields[mi] in specs:
                continue
        rows.append(line)
    emitted, entries = connection_rows(connections, specs)
    return ''.join(rows).rstrip() + '\n\n' + BEGIN + '\n' + emitted + END + '\n', entries


def validate_standing_points(specs, blobs, texts, connections, definition_exits=None):
    """Reject blocked/out-of-envelope content; never repair geometry silently."""
    grids = {}
    for region, spec in specs.items():
        blob = blobs[region]
        if len(blob) < 16:
            raise ValueError(f'{region}: truncated collision header')
        magic, version, _, width, height = struct.unpack_from('<4sHHII', blob)
        if magic != b'EWCG' or version != 2 or [width, height] != [n * 2 for n in spec['serverCells']]:
            raise ValueError(f'{region}: exported EWCGv2 dimensions do not match the served frame')
        if len(blob) < 16 + width * height:
            raise ValueError(f'{region}: truncated collision payload')
        grids[region] = (width, blob[16:16 + width * height], StorageBounds.from_metadata(spec['serverCells'], spec))
    checked = set()
    def check(region, point, label):
        if region not in specs:
            return
        x, y = shared.integer_pair(point, label)
        stride, data, bounds = grids[region]
        index = bounds.index_xy(x, y)
        if index is None:
            raise ValueError(f'{label}: {region} tile {(x, y)} is outside its served envelope')
        column, row = index
        at = 2 * row * stride + 2 * column
        if not all(data[index] for index in (at, at + 1, at + stride, at + stride + 1)):
            raise ValueError(f'{label}: {region} tile {(x, y)} is blocked by the authored collision')
        checked.add((region, x, y))
    for region, spec in specs.items():
        check(region, spec['arrival'], 'safe arrival')
    for source, x, y, target, tx, ty in connections:
        check(source, [x,y], 'exterior departure')
        check(target, [tx,ty], 'exterior arrival')
    for filename, rules in shared.RULES.items():
        for number, line in enumerate(texts.get(filename, '').splitlines(), 1):
            if line.lstrip().startswith('#'):
                continue
            fields = [f.strip() for f in line.split('|')]
            for keyword, mi, xi, yi in rules:
                if len(fields) <= max(mi, xi, yi):
                    continue
                matches = (fields[0] == 'portal' and len(fields) == int(keyword[-1])
                           if keyword and keyword.startswith('portal') else keyword is None or fields[0] == keyword)
                # Area rectangle corners bound a zone and need not be walkable.
                if matches and filename != 'special_areas.txt':
                    check(fields[mi], [int(fields[xi]), int(fields[yi])], f'{filename}:{number}')
    departures = set()
    for line in texts.get('maps.txt', '').splitlines():
        fields = [v.strip() for v in line.split('|')]
        if fields[0] == 'portal' and len(fields) in (7, 8):
            start = 2 if len(fields) == 7 else 3
            departures.add((fields[1], int(fields[start]), int(fields[start + 1])))
    for identity, entry in (definition_exits or {}).items():
        region, point = entry['source']['map'], entry['tile']
        check(region, point, identity)
        if (region, *point) in departures:
            raise ValueError(f'{identity}: instance exit immediately triggers an unrelated portal')
    return len(checked)


def crossing_runs(tiles):
    """A border's crossing tiles as the fewest straight runs along one axis.

    A client walking to a neighbour aims at the crossing that makes the
    shortest walk, so it has to know where the crossings are; a border open
    along its length is hundreds of them, and the survey is written indented.
    Along ``x`` a run is ``[y, x0, x1]``, along ``y`` it is ``[x, y0, y1]``.
    """
    def along(axis):
        other, runs = 1 - axis, []
        for tile in sorted(tiles, key=lambda tile: (tile[other], tile[axis])):
            if runs and runs[-1][0] == tile[other] and runs[-1][2] + 1 == tile[axis]:
                runs[-1][2] = tile[axis]
            else:
                runs.append([tile[other], tile[axis], tile[axis]])
        return runs
    x, y = along(0), along(1)
    return {'axis': 'x', 'runs': x} if len(x) <= len(y) else {'axis': 'y', 'runs': y}


def connection_manifests(publication, worlds, specs):
    graph, streaming = [], []
    for connection in publication['connections']:
        a, b = connection['ends']
        # The graph is the roads and boats between territories, each between two
        # named portals, and the atlas draws each as a route. A border no road
        # crosses is walked over wherever its ground allows and has neither.
        road = connection.get('road', True)
        if road:
            graph.append({'id': connection['id'], 'from': a['region'], 'from_portal': a['portal'],
                          'to': b['region'], 'to_portal': b['portal'], 'type': connection.get('type', 'land'),
                          'note': connection.get('note', 'Shared-continent authored connection')})
        if connection.get('type', 'land') in ('ferry', 'ship', 'boat', 'teleport'):
            continue
        ends = []
        for end in (a, b):
            region = end['region']
            world = worlds[region]
            frame = end.get('frame') or next((frame for frame in world.get('streamingBorders', [])
                                              if frame.get('portal') == end['portal']), None)
            if not frame:
                raise ValueError(f'{connection["id"]}: exported land crossing lacks its authored frame')
            if 'globalTranslation' in frame and frame['globalTranslation'] != specs[region]['translation']:
                raise ValueError(f'{connection["id"]}: endpoint frame translation differs from publication')
            tile, origin = end['tile'], specs[region]['serverOrigin']
            position = end.get('position', [tile[0] + .5 - origin[0], frame['anchor'][1], origin[1] - tile[1] - .5])
            ends.append({'map': region, 'portal': end['portal'], 'position': position,
                         'frame': copy.deepcopy(frame), 'coordinateTransform': copy.deepcopy(world['coordinateTransform']),
                         'preloadEdges':copy.deepcopy(end.get('preloadEdges',[])),
                         'crossingRuns': crossing_runs([lane['tile'] for lane in end.get('lanes', [end])])})
        streaming.append({'id': connection['id'], 'seamless': True, 'ends': ends, **({} if road else {'road': False})})
    identities={c['id'] for c in streaming}
    for visual in publication.get('visualConnections',[]):
        if visual.get('id') in identities or len(visual.get('ends',[]))!=2 or not visual.get('visualOnly'):
            raise ValueError('Visual adjacency requires a unique identity, two ends, and visualOnly=true')
        entry=copy.deepcopy(visual)
        for end in entry['ends']:
            if end.get('map') not in worlds or not end.get('preloadEdges') or not end.get('frame'):
                raise ValueError('Visual adjacency requires existing territories and surveyed edges/frames')
            end['coordinateTransform']=copy.deepcopy(worlds[end['map']]['coordinateTransform'])
        identities.add(entry['id']);streaming.append(entry)
    settings = {key: publication.get(key, default) for key, default in (
        ('preloadDistance', 320), ('retainDistance', 420), ('maximumNeighbours', 3))}
    return ({'schema': 1, 'revision': publication['revision'], 'connections': graph},
            {'schema': 1, **settings, 'connections': streaming})


def plan(client, server, publication_path):
    client, server, publication_path = client.resolve(), server.resolve(), publication_path.resolve()
    raw = publication_path.read_bytes()
    publication = json.loads(raw)
    if publication.get('schema') != 1 or not publication.get('revision') or not publication.get('regions'):
        raise ValueError('Publication requires schema 1, a revision and named territories')
    master = resolve_input(client, publication_path, publication['masterPath'])
    master_bytes = master.read_bytes()
    if shared.digest(master_bytes) != publication['masterSha256']:
        raise ValueError('Master continent digest does not match the exported publication')
    profile = server / 'config/eloria'
    manifest_path = profile / 'client_content_manifest.json'
    manifest = read_json(manifest_path)
    previous = manifest.get('continentGeography', {}).get('regions', {})
    current = manifest.get(STATE, {})
    publication_hash = shared.digest(raw)
    repeated = current.get('publicationSha256') == publication_hash
    if current and not repeated and publication.get('sourcePublicationSha256') != current.get('publicationSha256'):
        raise ValueError('A revised export must name sourcePublicationSha256 and map from the currently published coordinates')
    specs = copy.deepcopy(publication['regions'])
    if set(specs) != set(previous):
        raise ValueError('This release must retain all twelve existing exterior identities; identity changes require an explicit migration')
    before, pending = {publication_path: raw, master: master_bytes}, {}
    worlds, blobs, world_paths = {}, {}, {}

    def read(path):
        payload = path.read_bytes()
        before.setdefault(path, payload)
        return payload

    def stage(path, payload):
        old = read(path) if path.exists() else None
        before.setdefault(path, old)
        if old != payload:
            pending[path] = payload

    read(manifest_path)
    if not repeated:
        for filename, expected in publication.get('sourceProfileSha256', {}).items():
            path = (profile / filename).resolve()
            if not path.is_relative_to(profile.resolve()) or not path.is_file():
                raise ValueError(f'Invalid source profile fingerprint path: {filename}')
            if shared.digest(read(path)) != expected:
                raise ValueError(f'{filename}: source profile changed after continent export')
        for relative,expected in publication.get('sourceCodeSha256',{}).items():
            path=(server/relative).resolve()
            if not path.is_relative_to(server) or not path.is_file():
                raise ValueError(f'Invalid source code fingerprint path: {relative}')
            if shared.digest(read(path))!=expected:
                raise ValueError(f'{relative}: gameplay source changed after continent export')
    for region, spec in specs.items():
        validate_spec(region, spec, None if repeated else previous.get(region))
        world_path = resolve_input(client, publication_path, spec['worldManifestPath'])
        collision_path = resolve_input(client, publication_path, spec['collisionPath'])
        world, collision = json.loads(read(world_path)), read(collision_path)
        validate_package_storage(region, spec, world, collision)
        if not world.get('collision', {}).get('authoredSurfaceExport'):
            raise ValueError(f'{region}: shared-continent collision requires authoredSurfaceExport to prohibit legacy carving')
        if world['collision'].get('gridAlignment') != 'tile-centres-v1':
            raise ValueError(f'{region}: shared-continent collision requires explicit tile-centres-v1 alignment')
        worlds[region], blobs[region], world_paths[region] = world, collision, world_path

    texts, records = {}, {}
    original_texts = {filename: read(profile / filename).decode('utf-8') for filename in CONTENT}
    source_tile_counts = content_source_tile_counts(original_texts)
    # Establish exact shared-point mappings before rewriting portals or quests.
    for filename in CONTENT:
        texts[filename], records[filename] = rewrite_content(
            original_texts[filename], filename, specs, repeated, source_tile_counts)
    mappings = {region: {'delta': [0, 0], '_native_mapper':
                        (lambda point: list(point)) if repeated else (lambda point, spec=spec: transform_tile(point, spec))}
                for region, spec in specs.items()}
    for filename, rules in shared.RULES.items():
        if filename in texts:
            continue
        path = profile / filename
        original_texts[filename] = read(path).decode('utf-8')
        texts[filename], _ = shared.rewrite_profile(original_texts[filename], rules, mappings)
    if not repeated:
        rewrite_runtime_binding_sources(
            original_texts, texts, specs,
            previous_placements=current.get('placements', {}),
            certified_texts=_runtime_binding_profile_texts(client, specs))
    texts['maps.txt'], portal_entries = replace_crossings(texts['maps.txt'], publication['connections'], specs)
    instance_entries = None
    schema = publication.get('instanceExitSchema')
    if schema is not None and (type(schema) is not int or schema not in (1, 2)):
        raise ValueError('Unsupported instance exit schema')
    if (any('instanceExitPositions' in spec for spec in current.get('placements', {}).values()) and schema not in (1, 2)) or (current.get('instanceExitSchema') == 2 and schema != 2):
        raise ValueError('A revised publication cannot discard certified instance exit identities')
    if schema in (1, 2):
        instance_entries = validate_instance_exit_table(specs, certified_instance_exit_sources(client, specs),
                                                       client=client, require_authored=schema == 2)
    elif any('instanceExitPositions' in spec for spec in specs.values()):
        raise ValueError('Instance exit table requires its explicit publication schema')
    for filename, text in texts.items():
        stage(profile / filename, text.encode('utf-8'))
    staged_exits = {}
    definitions = [*profile.glob('instances/*.def'), *profile.glob('spawn_groups/**/*.def'), profile / 'questlines.txt']
    for path in sorted(definitions):
        if path.exists():
            original = read(path).decode('utf-8')
            relative = 'config/eloria/' + path.relative_to(profile).as_posix()
            if instance_entries is not None and relative.startswith('config/eloria/instances/'):
                text, _ = rewrite_instance_exits(relative, original, mappings, instance_entries,
                                                  mode='repeated' if repeated else 'served')
                actual = instance_exit_records(relative, text, specs)
                for identity, source in actual.items():
                    entry = instance_entries[identity]
                    if source['originalTile'] != entry['tile']:
                        raise ValueError(f'{identity}: staged instance exit differs from its contract')
                    staged_exits[identity] = entry
            else:
                text, _ = shared.rewrite_definition(original, mappings)
            stage(path, text.encode('utf-8'))
    if instance_entries is not None and set(staged_exits) != set(instance_entries):
        raise ValueError('Staged definition exits do not cover the certified instance table')
    checked = validate_standing_points(specs, blobs, texts, portal_entries, staged_exits)
    for relative, kind in (('tools/generate_nymara_maps.py', 'generator'), ('eloria/map_layout.py', 'layout'),
                           ('eloria/world.py', 'world'), ('eloria/walkthrough.py', 'walkthrough'),
                           ('eloria/pk.py', 'pk'), ('eloria/daily_quests.py', 'daily')):
        path = server / relative
        text = read(path).decode('utf-8')
        if kind in ('generator', 'layout'):
            text = rewrite_exact_arrivals(text, kind, specs)
        else:
            text = rewrite_gameplay_source(text, kind, mappings)
        stage(path, text.encode('utf-8'))

    registry_path = client / 'godot-client/data/maps/registry.json'
    registry = json.loads(read(registry_path))
    for region, spec in specs.items():
        if region not in registry['maps']:
            raise ValueError(f'{region}: missing existing client registry identity')
        entry = registry['maps'][region]
        entry.update(coordinateTransform=copy.deepcopy(worlds[region]['coordinateTransform']), landscapeTransitions=True,
                     continentGeography={'translation': spec['translation'], 'geometryMode': 'continent-chunks-v1',
                                         **storage_fields(spec)})
    stage(registry_path, shared.json_bytes(registry))
    # Room-local positions stay local. Only metadata naming an exterior target
    # follows the continent deformation, including gauntlet completion returns.
    seen_paths = set(world_paths.values())
    for entry in registry['maps'].values():
        if not entry.get('manifest'):
            continue
        path = (client / 'godot-client' / entry['manifest'].removeprefix('res://')).resolve()
        if path in seen_paths:
            continue
        seen_paths.add(path)
        if not path.is_relative_to(client) or not path.is_file():
            raise ValueError(f'Registry manifest is missing or outside client: {path}')
        data = json.loads(read(path))
        updated = remap_metadata(data, specs, mappings)
        if updated != data:
            stage(path, shared.json_bytes(updated))

    for index, entry in enumerate(manifest.get('maps', [])):
        region = entry['id']
        manifest['maps'][index] = remap_metadata(entry, specs, mappings, region)
        if region in specs:
            spec = specs[region]
            manifest['maps'][index].update(arrival=spec['arrival'], server_cells=spec['serverCells'][0],
                                           server_origin=spec['serverOrigin'],
                                           **storage_fields(spec),
                                           coordinateTransform=copy.deepcopy(worlds[region]['coordinateTransform']))
    for key, value in list(manifest.items()):
        if key in ('maps', STATE, 'continentGeography'):
            continue
        region = next((region for region in sorted(specs, key=len, reverse=True)
                       if key.startswith(region + '_') or region == 'sunmane_steppe' and key in ('sunmane_npcs', 'sunmane_resources')), None)
        manifest[key] = remap_metadata(value, specs, mappings, region)
    # Derive every manifest portal from the final authoritative table.
    all_portals = {}
    for line in texts['maps.txt'].splitlines():
        fields = [field.strip() for field in line.split('|')]
        if len(fields) in (7, 8) and fields[0] == 'portal':
            start = 2 if len(fields) == 7 else 3
            all_portals.setdefault(fields[1], []).append({'server_tile': [int(fields[start]), int(fields[start + 1])],
                                                         'destination': fields[start + 2]})
    for entry in manifest.get('maps', []):
        entry['portals'] = all_portals.get(entry['id'], [])
    runtime = runtime_specs(specs, previous)
    manifest['continentGeography'] = {'schema': 1, 'geometryMode': 'continent-chunks-v1',
        'geographySha256': publication_hash, 'masterSha256': publication['masterSha256'], 'regions': runtime}
    placements = (copy.deepcopy(current['placements']) if repeated and 'placements' in current
                  else placement_contracts(specs))
    manifest[STATE] = {'schema': 1, 'revision': publication['revision'], 'publicationSha256': publication_hash,
                      'masterSha256': publication['masterSha256'], 'placements': placements, 'collisionSha256':
                      {region: shared.digest(blob) for region, blob in blobs.items()}}
    if schema is not None:
        manifest[STATE]['instanceExitSchema'] = schema
    declared_storage = {region:storage_fields(spec) for region,spec in specs.items() if storage_fields(spec)}
    if declared_storage:
        manifest[STATE]['storageByRegion'] = declared_storage
    stage(manifest_path, shared.json_bytes(manifest))
    stage(server / 'eloria/continent_geography.py', shared.runtime_migration_source(runtime).encode('utf-8'))
    database_path = server / 'eloria/database.py'
    stage(database_path, shared.install_geography_hook(read(database_path).decode('utf-8')).encode('utf-8'))
    graph, streaming = connection_manifests(publication, worlds, specs)
    stage(client / 'eloria-assets/maps/nymara-regions/region-connections.json', shared.json_bytes(graph))
    stage(client / 'godot-client/data/maps/exterior_connections.json', shared.json_bytes(streaming))
    stage(profile / 'exterior_connections.json', shared.json_bytes(streaming))
    report = {'schema': 1, 'revision': publication['revision'], 'publicationSha256': publication_hash,
              'repeatedPublication': repeated, 'masterSha256': publication['masterSha256'],
              'territories': len(specs), 'connections': len(publication['connections']),
              'exteriorPortalLanes': len(portal_entries), 'verifiedStandingPoints': checked,
              'instanceExits': copy.deepcopy(staged_exits),
              'contentRecords': records, 'files': [{'path': str(path),
                  'beforeSha256': shared.digest(before[path]) if before[path] is not None else None,
                  'afterSha256': shared.digest(payload)} for path, payload in pending.items()]}
    return before, pending, report


def apply_publication(before, pending, publication_path):
    """Keep signed storage inactive until persisted standing points are migrated."""
    publication = json.loads(before[Path(publication_path).resolve()])
    signed = [region for region,spec in publication['regions'].items()
              if StorageBounds.from_metadata(spec['serverCells'],spec).metadata()['serverTileMin'] != [0,0]]
    if signed:
        raise ValueError('Signed-storage publication requires the not-yet-implemented validity-based persistence migration; '
                         'no target writes are allowed for nonzero storage minima: '+', '.join(sorted(signed)))
    shared.apply_plan(before,pending)


def build_contracts(client, server, publication_path, data):
    if int(os.environ.get('ELORIA_BUILD_CORES', '999')) > 8:
        raise ValueError('Run --build through run_limited.py to enforce the eight-core ceiling')
    publication = read_json(publication_path)
    def run(cwd, script, *arguments):
        subprocess.run([sys.executable, '-u', str(script), *map(str, arguments)], cwd=cwd, check=True)
    for region in publication['regions']:
        run(server, server / 'tools/sync_authored_collision.py', '--client', client / 'eloria-assets/maps', '--region', region)
    run(server, server / 'tools/generate_nymara_maps.py', data)
    run(server, server / 'tools/generate_nymara_invasion_spawns.py')
    run(client, client / 'eloria-assets/tools/sync_package_content.py', '--manifest',
        server / 'config/eloria/client_content_manifest.json', '--digests', '--apply')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--client', type=Path, default=CLIENT)
    parser.add_argument('--server', type=Path, required=True)
    parser.add_argument('--publication', type=Path, default=PUBLICATION)
    parser.add_argument('--apply', action='store_true')
    parser.add_argument('--build', action='store_true')
    parser.add_argument('--data', type=Path)
    parser.add_argument('--report', type=Path)
    args = parser.parse_args()
    if args.build and (not args.apply or args.data is None):
        parser.error('--build requires --apply and --data')
    before, pending, report = plan(args.client, args.server, args.publication)
    if args.apply:
        apply_publication(before, pending, args.publication)
    if args.build:
        build_contracts(args.client.resolve(), args.server.resolve(), args.publication.resolve(), args.data.resolve())
    report.update(applied=args.apply, built=args.build)
    if args.report:
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_bytes(shared.json_bytes(report))
    print(json.dumps(report, indent=2))


if __name__ == '__main__':
    main()
