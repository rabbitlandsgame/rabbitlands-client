"""Seat authoritative content on the exported continent's actual walking grid.

This is an export stage, not a profile editor. It freezes the input profile,
folds all four half-metre samples exactly as the server does, and emits explicit
old-to-new standing points. A disconnected doorway or road is a geometry error:
the diagnostic is written, and no publication is emitted to conceal it.
"""
from __future__ import annotations

import ast
import copy
import hashlib
import importlib
import json
import math
from pathlib import Path
import struct
import subprocess
import sys
import time

import numpy as np
from storage_bounds import storage_record
import runtime_content_amendment as amendments

HERE = Path(__file__).resolve().parent
TOOLS = HERE.parents[2] / 'tools'
REVISION = 'diagonal-spine-v1'
GAMEPLAY_SOURCES = ('eloria/daily_quests.py', 'eloria/world.py', 'eloria/walkthrough.py', 'eloria/pk.py')
# The coordinated build regenerates these from the served profile after the
# plan is applied; a re-run accepts only their exact deterministic regeneration.
BUILD_REGENERATED = ('config/eloria/spawn_groups/invasion/invasion_nymara.def',)
BUILD_REGENERATED_PROFILE = frozenset(
    path.removeprefix('config/eloria/') for path in BUILD_REGENERATED)


def write_json(path, value):
    def clean(item):
        if isinstance(item, np.ndarray):
            return item.tolist()
        if isinstance(item, np.generic):
            return item.item()
        raise TypeError(type(item).__name__)
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    Path(path).write_text(json.dumps(value, indent=2, ensure_ascii=False, default=clean) + '\n', encoding='utf-8', newline='\n')


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def terrain_revision(spec, collision, server_grid):
    """Content-address saved standing space independently for each territory.

    The release label is a schema identity, not a terrain identity. Reusing it
    after moving a cliff or building must not strand an existing character.
    Baseline/current-source bookkeeping is excluded so a repeated export keeps
    the same migration marker, including after its first profile publication.
    """
    geometry = collision['collision']
    identity = {'schema': 1, 'release': REVISION,
        'geometrySha256': geometry['sourceGlbSha256'],
        'collisionSha256': sha(spec['collisionPath']),
        'heightEncoding': geometry['heightEncoding'],
        'serverGridSha256': hashlib.sha256(np.ascontiguousarray(server_grid, dtype=np.uint8).tobytes()).hexdigest(),
        **{field: spec[field] for field in ('serverOrigin', 'serverCells', 'translation', 'arrival',
                                           'contentPositions')},
        'runtimeBindingPositions': spec.get('runtimeBindingPositions', {}),
        'instanceExitPositions': {identity: entry['tile'] for identity, entry in spec.get('instanceExitPositions', {}).items()}}
    storage = storage_record(spec['serverCells'], spec)
    if storage['serverTileMin'] != [0, 0] or 'authoringSpecSha256' in storage:
        identity['storage'] = storage
    encoded = json.dumps(identity, sort_keys=True, separators=(',', ':'), allow_nan=False).encode('utf-8')
    return REVISION + ':' + hashlib.sha256(encoded).hexdigest()


def revision_metadata(path, manifest, spec, master_sha):
    """Prepare consistent territory/chunk metadata, without writing any files."""
    manifest['terrainRevision'] = spec['terrainRevision']
    manifest['continentPublication'] = {'revision': REVISION, 'masterSha256': master_sha,
        'collisionSha256': sha(Path(spec['collisionPath'])), 'terrainRevision': spec['terrainRevision']}
    storage = storage_record(spec['serverCells'], spec) if 'serverCells' in spec else None
    if storage is not None:
        transform=manifest['coordinateTransform']
        if 'serverCells' in transform and storage_record(transform['serverCells'],transform)!=storage:
            raise ValueError('Final manifest storage differs from placement certificate')
        collision=manifest.get('collision',{})
        if storage_record(collision.get('serverCells',spec['serverCells']),collision)!=storage:
            raise ValueError('Final collision storage differs from placement certificate')
        manifest['coordinateTransform'].update(storage)
        manifest.setdefault('collision', {}).update(storage)
        manifest['continentPublication']['storage'] = copy.deepcopy(storage)
    children = []
    if 'streamingChunks' in manifest:
        manifest['streamingChunks']['terrainRevision'] = spec['terrainRevision']
        if storage is not None:
            manifest['streamingChunks']['storage'] = copy.deepcopy(storage)
        folder = Path(path).parent.resolve()
        for entry in manifest['streamingChunks']['chunks']:
            child_path = (folder / entry['manifest']).resolve()
            if not child_path.is_relative_to(folder):
                raise ValueError(f'{child_path}: chunk revision metadata must remain inside its named territory')
            child = json.loads(child_path.read_text(encoding='utf-8'))
            if storage is not None and 'serverCells' in child.get('coordinateTransform',{}):
                transform=child['coordinateTransform']
                if storage_record(transform['serverCells'],transform)!=storage:
                    raise ValueError(f'{child_path}: chunk storage differs from placement certificate')
            child['terrainRevision'] = spec['terrainRevision']
            child['continentPublication'] = copy.deepcopy(manifest['continentPublication'])
            # The territory frame is final only after contracts (arrival walking
            # height); every independent cell must carry the identical frame.
            child['coordinateTransform'] = copy.deepcopy(manifest['coordinateTransform'])
            if storage is not None:
                child.setdefault('collision', {}).update(storage)
            children.append((child_path, child))
    return children


def frozen_profile(server, shared, baseline=None):
    """Freeze the original authored frame before any coordinated publication."""
    baseline = Path(baseline or HERE / 'legacy-server-profile')
    certificate_path = baseline / 'snapshot.json'
    current_manifest = json.loads((server / 'config/eloria/client_content_manifest.json').read_text(encoding='utf-8'))
    if not certificate_path.exists():
        if current_manifest.get('diagonalContinent'):
            raise ValueError('Server already uses diagonal coordinates, but immutable legacy-server-profile is missing; restore the original snapshot before re-exporting')
        profile = server / 'config/eloria'
        paths = {profile / name for name in (*shared.RULES, 'client_content_manifest.json', 'creatures.txt')}
        paths.update(profile.glob('instances/*.def'))
        paths.update(profile.glob('spawn_groups/**/*.def'))
        paths.add(profile / 'questlines.txt')
        paths.update(server / relative for relative in GAMEPLAY_SOURCES)
        files = {}
        for source in sorted(path for path in paths if path.exists()):
            relative = source.relative_to(server).as_posix()
            target = baseline / relative
            payload = source.read_bytes()
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(payload)
            files[relative] = hashlib.sha256(payload).hexdigest()
        write_json(certificate_path, {'schema': 1, 'purpose': 'Immutable pre-diagonal authored coordinate profile', 'files': files})
    certificate = json.loads(certificate_path.read_text(encoding='utf-8'))
    for relative, expected in certificate['files'].items():
        if not (baseline / relative).exists() or sha(baseline / relative) != expected:
            raise ValueError(f'Immutable baseline changed: {relative}; restore its certified original bytes')
    return baseline, certificate, current_manifest


def previous_release(current, history=None):
    published = current.get('diagonalContinent', {}).get('publicationSha256')
    if not published:
        return None
    path = Path(history or HERE / 'publication-history') / (published + '.json')
    if not path.exists() or sha(path) != published:
        raise ValueError(f'Published diagonal coordinates require their exact publication history {published}; cannot safely deform current coordinates without it')
    previous = json.loads(path.read_text(encoding='utf-8'))
    if any('baselineTilePositions' not in spec for spec in previous['regions'].values()):
        raise ValueError('Previous publication lacks baseline point history; restore an audited publication before re-exporting')
    return previous


def freeze_return_targets(baseline, publisher):
    """Snapshot exterior targets declared by rooms, before their manifests move."""
    path = baseline / 'interior-return-targets.json'
    if path.exists():
        data = json.loads(path.read_text(encoding='utf-8'))
        return data['targets']
    current = json.loads((baseline / 'config/eloria/client_content_manifest.json').read_text(encoding='utf-8'))
    specs = {r: {'serverOrigin': v['serverOrigin'], 'previousServerOrigin': v['serverOrigin']}
             for r, v in current['continentGeography']['regions'].items()}
    client = TOOLS.parents[1]
    registry = json.loads((client / 'godot-client/data/maps/registry.json').read_text(encoding='utf-8'))
    targets, files = [], {}
    context = {'file': ''}
    def record(region, point):
        targets.append({'region': region, 'oldTile': list(point), 'source': context['file']})
        return list(point)
    mappings = {r: {'delta': [0, 0], '_native_mapper': lambda point, r=r: record(r, point)} for r in specs}
    for region, entry in registry['maps'].items():
        if region in specs or not entry.get('manifest'):
            continue
        source = (client / 'godot-client' / entry['manifest'].removeprefix('res://')).resolve()
        if not source.is_relative_to(client) or not source.exists():
            raise ValueError(f'Missing interior source manifest {source}')
        context['file'] = source.relative_to(client).as_posix()
        files[context['file']] = sha(source)
        publisher.remap_metadata(json.loads(source.read_text(encoding='utf-8')), specs, mappings)
    unique = {(v['region'], *v['oldTile'], v['source']): v for v in targets}
    data = {'schema': 1, 'sourceManifestSha256': files, 'targets': list(unique.values())}
    write_json(path, data)
    return data['targets']


def profile_fields(text):
    """A pipe-delimited profile's rows as stripped fields, blank lines dropped."""
    return [[field.strip() for field in line.split('|')] for line in text.splitlines() if line.strip()]


def verify_current_profile(server, baseline, certificate, previous, shared, publisher, amendment=None):
    """Reject content edits that an old snapshot would silently overwrite.

    ``amendment`` (runtime_content_amendment.load) lists rows appended to the
    frozen content files after their freeze; they are rebuilt with the rest.
    """
    if previous is None:
        if amendment is not None:
            raise ValueError('A runtime content amendment needs a certified publication to seat its rows')
        for relative, expected in certificate['files'].items():
            if not (server / relative).exists() or sha(server / relative) != expected:
                raise ValueError(f'{relative}: current server differs from immutable pre-publication baseline')
        return
    specs = copy.deepcopy(previous['regions'])
    # Reconstruct the currently served coordinates from the immutable frame.
    for region, spec in specs.items():
        spec['tilePositions'] = copy.deepcopy(spec['baselineTilePositions'])
        spec['previousServerOrigin'] = spec['baselineServerOrigin']
        spec['contentTransform'] = spec['baselineContentTransform']
        spec['removedInteractiveIds'] = spec['baselineRemovedInteractiveIds']
        # A generic definition can name the same original exterior tile as
        # several record-bound portals.  Publication resolves those portals in
        # their saved order, so the last explicit portal is also the tile that
        # the generic mapper served.  Reconstruct that result from the prior
        # publication's qualified binding provenance rather than treating the
        # collapsed baseline tile as an unrelated server edit.
        sources = spec.get('runtimeBindingSourceTiles', {})
        for portal in spec.get('portalPositions', {}).values():
            identity = portal.get('runtimeBindingId')
            if identity is None:
                continue
            source = sources.get(identity)
            if source is None:
                raise ValueError(f'{region}:{identity}: previous publication lost its runtime binding source tile')
            spec['tilePositions'][key(source)] = list(portal['tile'])
    mappings = {r: {'delta': [0, 0], '_native_mapper': lambda old, spec=spec: publisher.transform_tile(old, spec)} for r, spec in specs.items()}
    # Maps and territory rows are record-bound after the ordinary tile rewrite.
    # Rebuild those explicit aliases directly from the immutable profile, just
    # as the publisher did, so a repeated contract run verifies the served
    # rows rather than mistaking their distinct positions for manual edits.
    bound_profiles = {binding['source']['path'].removeprefix('config/eloria/')
                      for spec in specs.values()
                      for binding in spec.get('runtimeBindings', {}).values()
                      if binding['source']['path'] in ('config/eloria/maps.txt',
                                                      'config/eloria/territories.txt')}
    bound_originals, bound_rewritten = {}, {}
    for name in sorted(bound_profiles):
        relative = 'config/eloria/' + name
        if relative not in certificate['files']:
            raise ValueError(f'{relative}: previous runtime binding source is absent from the immutable profile')
        original = (baseline / relative).read_text(encoding='utf-8')
        bound_originals[name] = original
        bound_rewritten[name], _ = shared.rewrite_profile(original, shared.RULES[name], mappings)
    if bound_profiles:
        publisher.rewrite_runtime_binding_sources(
            bound_originals, bound_rewritten, specs,
            previous_placements=None, certified_texts=bound_originals)
    certified_content = amendments.amend(
        {name: (baseline / 'config/eloria' / name).read_text(encoding='utf-8')
         for name in publisher.CONTENT}, amendment)
    content_source_tiles = publisher.content_source_tile_counts(certified_content) if certified_content else {}
    instance_entries = None
    schema = previous.get('instanceExitSchema')
    if schema is not None and (type(schema) is not int or schema not in (1, 2)):
        raise ValueError('Unsupported instance exit schema in previous publication')
    if any('instanceExitPositions' in spec for spec in specs.values()) and schema not in (1, 2):
        raise ValueError('Previous instance exit table requires its explicit schema')
    if schema in (1, 2):
        sources = {}
        for relative, digest in certificate['files'].items():
            if relative.startswith('config/eloria/instances/') and relative.endswith('.def'):
                for identity, source in publisher.instance_exit_records(
                        relative, (baseline / relative).read_text(encoding='utf-8'), specs).items():
                    source['sha256'] = digest
                    sources[identity] = source
        instance_entries = publisher.validate_instance_exit_table(specs, sources, require_authored=schema == 2)
    regenerated = []
    for relative, expected in certificate['files'].items():
        path = server / relative
        if not path.exists():
            raise ValueError(f'{relative}: authoritative source disappeared after the preceding publication')
        old_text = (baseline / relative).read_text(encoding='utf-8')
        name = Path(relative).name
        if name == 'client_content_manifest.json':
            continue  # Digests and generated package metadata legitimately change at publication.
        if name in publisher.CONTENT:
            old_text = certified_content[name]
            text, _ = publisher.rewrite_content(old_text, name, specs, False, content_source_tiles)
        elif name in shared.RULES:
            if name in bound_rewritten:
                text = bound_rewritten[name]
            else:
                text, _ = shared.rewrite_profile(old_text, shared.RULES[name], mappings)
            if name == 'maps.txt':
                text, _ = publisher.replace_crossings(text, previous['connections'], specs)
        elif name.endswith('.def') or name == 'questlines.txt':
            if instance_entries is not None and relative.startswith('config/eloria/instances/'):
                text, _ = publisher.rewrite_instance_exits(relative, old_text, mappings, instance_entries, mode='source')
            else:
                text, _ = shared.rewrite_definition(old_text, mappings)
        elif relative in GAMEPLAY_SOURCES:
            kind = {'daily_quests.py': 'daily', 'world.py': 'world', 'walkthrough.py': 'walkthrough', 'pk.py': 'pk'}[name]
            text = publisher.rewrite_gameplay_source(old_text, kind, mappings)
        else:
            text = old_text
        current = path.read_text(encoding='utf-8')
        same = current == text
        if not same and (name in publisher.CONTENT or name in shared.RULES):
            # The publisher pads a coordinate to the width its field had in the
            # text it rewrote, so a record served through two publications can
            # carry an earlier padding; only the fields themselves are content.
            same = profile_fields(current) == profile_fields(text)
        if not same:
            if relative in BUILD_REGENERATED:
                regenerated.append(relative)
                continue
            raise ValueError(f'{relative}: server content changed beyond the previous coordinated publication; reconcile the immutable baseline explicitly')
    if regenerated:
        result = subprocess.run([sys.executable, str(server / 'tools/generate_nymara_invasion_spawns.py'), '--check'],
                                cwd=server, capture_output=True, text=True)
        if result.returncode != 0:
            raise ValueError('Build-regenerated content differs from its deterministic regeneration: ' + ', '.join(regenerated)
                             + ' ' + (result.stdout + result.stderr)[-1500:].strip())


def estimated_served_tile(old_key, prior):
    """Where the previous publication serves an original tile it never placed explicitly.

    Mirrors publish_diagonal_continent.transform_tile for that publication's
    baseline frame: the content transform of the original cell centre into the
    published address frame.
    """
    old = [int(value) for value in old_key.split(':')]
    origin = prior['serverOrigin']
    previous_origin = prior['baselineServerOrigin']
    transform = prior['baselineContentTransform']
    x = old[0] + .5 - previous_origin[0]
    z = previous_origin[1] - old[1] - .5
    if transform['scale'] is None:
        # A turned or per-axis squeezed layout: its exact affine lands on absolute continent metres.
        a, b, c, d, e, f = transform['affine']
        translation = prior['translation']
        x, z = a * x + b * z + e - translation[0], c * x + d * z + f - translation[2]
    else:
        source, target, scale = transform['sourceCenter'], transform['targetCenter'], transform['scale']
        x, z = (x - source[0]) * scale + target[0], (z - source[1]) * scale + target[1]
    return [int(math.floor(x + origin[0])), int(math.floor(origin[1] - z))]


def rebase_publication(publication, previous):
    """Keep geometry in its original frame, publish remaps from today's frame."""
    for region, spec in publication['regions'].items():
        baseline = copy.deepcopy(spec['tilePositions'])
        spec['baselineTilePositions'] = baseline
        spec['baselineServerOrigin'] = list(spec['previousServerOrigin'])
        spec['baselineContentTransform'] = copy.deepcopy(spec['contentTransform'])
        spec['baselineRemovedInteractiveIds'] = list(spec['removedInteractiveIds'])
        if previous is None:
            continue
        prior = previous['regions'][region]
        old_baseline = prior['baselineTilePositions']
        mapping = {}
        estimated = []
        for old_key, target in baseline.items():
            current = old_baseline.get(old_key)
            if current is None:
                # A record the authored baseline gained after the previous
                # publication is served today at that publication's content
                # transform of its original tile: exactly where the profile
                # reconciliation put it, and where the publisher's rewrite
                # will find it.
                current = estimated_served_tile(old_key, prior)
                estimated.append(old_key)
            current_key = key(current)
            if current_key in mapping and mapping[current_key] != target:
                raise ValueError(f'{region}:{current_key}: distinct original points collapsed in the previous publication but need different revised targets')
            mapping[current_key] = target
        spec['tilePositions'] = mapping
        spec['estimatedSourceTiles'] = estimated
        for portal_id, portal in spec['portalPositions'].items():
            identity = portal.get('runtimeBindingId')
            if identity is not None:
                current = prior.get('runtimeBindingPositions', {}).get(identity)
                source = prior.get('runtimeBindingSourceTiles', {}).get(identity)
                if current is None or source != portal['oldTile']:
                    raise ValueError(f'{region}:{identity}: previous qualified portal provenance is missing')
            else:
                old_portal = prior.get('portalPositions', {}).get(portal_id)
                if old_portal is None:
                    raise ValueError(f'{region}:{portal_id}: previous portal identity is missing')
                current = old_portal['tile']
            portal['oldTile'] = list(current)
        spec['previousServerOrigin'] = list(prior['serverOrigin'])
        # All semantic points are explicit. The continuous fallback is identity
        # in the previous local frame; changed geographic rectangles are also
        # recorded explicitly before reaching this stage.
        spec['contentTransform'] = {'scale': 1., 'sourceCenter': [0, 0], 'targetCenter': [0, 0]}
        spec['removedInteractiveIds'] = []  # These IDs were removed by the first release.


def key(point):
    return f'{int(point[0])}:{int(point[1])}'


def rows(text):
    for number, line in enumerate(text.splitlines(), 1):
        if line.strip() and not line.lstrip().startswith('#'):
            yield number, [field.strip() for field in line.split('|')]


def server_modules(server):
    """Use the selected paired server's actual stage and footprint contracts."""
    server = Path(server).resolve()
    for directory in (server, server / 'tools', TOOLS):
        if str(directory) not in sys.path:
            sys.path.insert(0, str(directory))
    result = {}
    for name in ('collision_sources', 'sync_authored_collision', 'eloria.creatures',
                 'eloria.footprint', 'publish_continent_geography', 'publish_diagonal_continent'):
        module = importlib.import_module(name)
        if name.startswith('eloria.') or name in ('collision_sources', 'sync_authored_collision'):
            if not Path(module.__file__).resolve().is_relative_to(server):
                raise ValueError(f'{name} was loaded from a different server checkout')
        result[name] = module
    return result


def fold_server_grid(result, sources, sync):
    """Four subcells, maximum floor, zero if any part of an actor tile is blocked."""
    grid = np.asarray(result['grid'], dtype=np.uint8)
    height, width = grid.shape
    if height % 2 or width % 2 or height != width:
        raise ValueError('Named territory collision must have a square even half-cell envelope')
    from storage_bounds import StorageBounds
    collision=result['collision']
    bounds=StorageBounds.from_metadata([width//2,height//2],collision)
    if collision.get('serverCells',[width//2,height//2])!=[width//2,height//2]:
        raise ValueError('EWCG declared logical storage dimensions differ from half-cell arrays')
    blocks = grid.reshape(height // 2, 2, width // 2, 2)
    folded = blocks.max(axis=(1, 3))
    folded[~blocks.all(axis=(1, 3))] = 0
    encoding = result['collision']['heightEncoding']
    transform = sources.GridTransform(cell_tiles=.5, shift=0,
        metres_per_unit=encoding['step'], height_origin=encoding['origin'])
    quantised = sources.requantise(folded, transform)
    factor, largest, detail = sync.choose_stage(quantised)
    detail=dict(detail)
    detail['storage']={'serverCells':[bounds.width,bounds.height],**bounds.metadata()}
    if 'authoringSpecSha256' in collision:
        detail['storage']['authoringSpecSha256']=collision['authoringSpecSha256']
    return sync.rescale(quantised, factor), factor, largest, detail


def collision_world_digest(world):
    """Include every shared field used by exact collision, excluding content posts."""
    from collision_export import storage_contract
    digest = hashlib.sha256()
    for name, value in (('height', world.height), ('owner', world.owner),
                        ('water-mask', world.water['mask']), ('water-surface', world.water['surface'])):
        array = np.ascontiguousarray(value)
        digest.update(name.encode()); digest.update(str((array.shape, array.dtype.str)).encode())
        digest.update(memoryview(array).cast('B'))
    digest.update(json.dumps({'bounds': [world.x0, world.z0, world.x1, world.z1],
        'cell': getattr(world, 'cell', 2.), 'ids': world.ids,
        'storage':{region:storage_contract(world,region) for region in world.ids},
        'waterPlan': {name: getattr(world, 'plan', {}).get(name) for name in ('sea_level', 'rivers', 'lakes')}}, sort_keys=True).encode())
    return digest.hexdigest()


def cached_collision(world, region, manifest, glb_path, collision_path, output, world_digest):
    """Keep expensive completed rasters after a later placement failure."""
    import collision_export as exporter
    if 'coordinateTransform' in manifest:
        exporter.validate_storage_frame(world,region,manifest)
    signature = {'schema': 2, 'worldSha256': world_digest, 'region': region, 'glbSha256': sha(glb_path),
        'storage':exporter.storage_contract(world,region),'coordinateTransform':manifest.get('coordinateTransform'),
        'address': world.address(region), 'center': world.regions[region]['center'],
        'collisionRoots': sorted(manifest.get('collision', {}).get('nodeNames', [])),
        'surfacePrefixes': manifest.get('navigation', {}).get('surfaceNodePrefixes', ['Terrain_', 'Walk_']),
        'connections': [c for c in world.connections if region in c.get('regions', [])],
        'sources': {name: sha(HERE / name) for name in ('collision_export.py', 'world_layout.py', 'storage_bounds.py', 'terrain_export.py', 'landscape.py', 'crossings.py')},
        'readerSha256': sha(Path(exporter.GR.__file__))}
    signature_text = json.dumps(signature, sort_keys=True, default=lambda a: np.asarray(a).tolist())
    signature_hash = hashlib.sha256(signature_text.encode()).hexdigest()
    folder = output / 'collision-cache'; folder.mkdir(exist_ok=True)
    metadata_path, array_path = folder / (region + '.json'), folder / (region + '.npz')
    if metadata_path.exists() and array_path.exists():
        metadata = json.loads(metadata_path.read_text(encoding='utf-8'))
        if metadata.get('inputSha256') == signature_hash and metadata.get('arraysSha256') == sha(array_path):
            with np.load(array_path, allow_pickle=False) as arrays:
                result = {'collision': metadata['collision'], 'grid': arrays['grid'],
                          'heights': arrays['heights'], 'walkable': arrays['walkable']}
            grid = result['grid']; height, width = grid.shape
            collision_path.write_bytes(struct.pack('<4sHHII', b'EWCG', 2, 0, width, height) + grid.tobytes())
            print(f'{region}: reused certified collision raster', flush=True)
            return result
    result = exporter.export_collision(world, region, manifest, glb_path, collision_path)
    np.savez(array_path, grid=result['grid'], heights=result['heights'], walkable=result['walkable'])
    write_json(metadata_path, {'inputSha256': signature_hash, 'inputs': signature,
        'arraysSha256': sha(array_path), 'collision': result['collision']})
    return result


class PlacementError(ValueError):
    pass


class RegionPlacement:
    """Deterministic bounded searches on one hub-connected server component."""
    def __init__(self, world, content, region, spec, collision, grid, sources, report, previous=None):
        self.world, self.content, self.region, self.spec = world, content, region, spec
        self.collision, self.grid, self.sources = collision, grid.copy(), sources
        from storage_bounds import StorageBounds
        self.bounds = StorageBounds.from_metadata(spec.get('serverCells', [grid.shape[1], grid.shape[0]]), spec)
        if (grid.shape != (self.bounds.height, self.bounds.width) or
                hasattr(world, 'storage') and world.storage(region) != self.bounds):
            raise ValueError(f'{region}: placement grid/spec differs from World storage')
        if 'collision' in collision:
            declared = collision['collision']
            if StorageBounds.from_metadata(declared.get('serverCells', [grid.shape[1], grid.shape[0]]), declared) != self.bounds:
                raise ValueError(f'{region}: placement fold differs from collision storage')
        self.report = report
        self.previous = previous
        self.moved = {}   # served tile lost this publication -> where its first point went
        self.continuity = {'keptServedTile': 0, 'movedTogether': 0, 'movedFromServedTile': 0}
        self.records, self.failures = report['placements'], report['failures']
        self.reserved = np.zeros(grid.shape, dtype=bool)
        self.reachable = grid != 0
        self.storage = set()
        self.bodies = set()
        self.fixed = set()
        # An open border's lanes: kept clear of content, but - unlike the fixed
        # tiles - never asked to be reachable from the hub.
        self.held = set()
        self.actor_tiles = set()
        self.old_entries = {}
        self.entry_by_identity = {}
        self._index_metadata(content.templates[region])

    def runtime_binding(self, identity):
        return getattr(self.content, 'runtime_bindings', {}).get(identity)

    def runtime_binding_region(self, identity):
        """Return the one saved scene that owns a qualified binding marker."""
        if identity is None:
            return None
        qualified = getattr(self.content, 'runtime_bindings_by_region', None)
        if qualified is None:
            return self.region if self.runtime_binding(identity) is not None else None
        owners = [region for region, bindings in qualified.items() if identity in bindings]
        if len(owners) > 1:
            raise PlacementError(
                f'{self.region}:{identity}: authored runtime binding has ambiguous region owners {sorted(owners)}')
        if not owners:
            if self.runtime_binding(identity) is not None:
                raise PlacementError(f'{self.region}:{identity}: authored runtime binding lost its region owner')
            return None
        return owners[0]

    def runtime_identity(self, source_path, old, line=None):
        """Resolve one saved binding by certified source identity, never by tile alone."""
        old = tuple(map(int, old))
        prior_positions = (self.previous or {}).get('regions', {}).get(
            self.region, {}).get('runtimeBindingPositions', {})
        if line is not None:
            matches = getattr(self.content, 'runtime_binding_source_lines', {}).get(
                (source_path, int(line)), ())
            if len(matches) == 1:
                return matches[0]
            prior = [identity for identity in matches
                     if tuple(prior_positions.get(identity, ())) == old]
            if len(prior) > 1:
                raise PlacementError(
                    f'{self.region}:{source_path}:{line}:{key(old)} has ambiguous authored runtime bindings')
            if prior:
                return prior[0]
            seeded = [identity for identity in matches
                      if tuple(self.content.runtime_bindings[identity]['source']['oldTile']) == old]
            if len(seeded) > 1:
                raise PlacementError(
                    f'{self.region}:{source_path}:{line}:{key(old)} has ambiguous authored runtime bindings')
            return seeded[0] if seeded else None
        prior = [identity for identity, tile in prior_positions.items()
                 if tuple(tile) == old and self.runtime_binding(identity) is not None and
                 self.runtime_binding(identity).get('source', {}).get('path') == source_path]
        if len(prior) > 1:
            raise PlacementError(
                f'{self.region}:{source_path}:{key(old)} has ambiguous authored runtime bindings')
        if prior:
            return prior[0]
        matches = getattr(self.content, 'runtime_binding_source_tiles', {}).get(
            (source_path, old), ())
        if len(matches) > 1:
            raise PlacementError(
                f'{self.region}:{source_path}:{key(old)} has ambiguous authored runtime bindings')
        return matches[0] if matches else None

    def _index_metadata(self, value):
        if isinstance(value, list):
            for entry in value:
                self._index_metadata(entry)
        elif isinstance(value, dict):
            point = value.get('serverTile', value.get('server_tile'))
            if point is not None:
                self.old_entries.setdefault(key(point), []).append(value)
            for name in ('id', 'name'):
                if name in value:
                    self.entry_by_identity.setdefault(str(value[name]).casefold(), value)
            for entry in value.values():
                if isinstance(entry, (dict, list)):
                    self._index_metadata(entry)

    def expected(self, old, identity=None):
        origin = self.spec['previousServerOrigin']
        point = [old[0] + .5 - origin[0], 0., origin[1] - old[1] - .5]
        entry = self.entry_by_identity.get(str(identity).casefold()) if identity else None
        if entry is None:
            entries = self.old_entries.get(key(old), [])
            entry = next((e for e in entries if e.get('doorNode') or e.get('node')), entries[0] if entries else {})
        # Server coordinates are authoritative. A linked architectural root
        # determines displacement, but stale marker coordinates cannot move it.
        binding_region = self.runtime_binding_region(identity)
        authored = (getattr(self.content, 'authored_runtime_points', {}).get((binding_region, identity))
                    if binding_region is not None else None)
        if identity and self.runtime_binding(identity) is not None and authored is None:
            raise PlacementError(f'{self.region}:{identity}: saved runtime marker is missing')
        if authored is None:
            authored = (getattr(self.content, 'authored_actor_points', {}).get((self.region, identity))
                        if identity else None)
        if authored is None:
            authored = getattr(self.content, 'authored_server_points', {}).get((self.region, tuple(old)))
        if authored is not None:
            # Deliberately relocated doors and their separate return squares
            # have exact authored global coordinates. Both must use the same
            # override already consumed by Content.mapped_server_point.
            p = np.asarray(authored, float)
            if p.shape != (3,) or not np.isfinite(p).all():
                raise ValueError(f'{self.region}:{key(old)}: invalid authored semantic position')
        else:
            p = self.content.mapped_point(self.region, point,
                entry.get('node', entry.get('doorNode')), entry.get('landmark'))
        center = self.world.regions[self.region]['center']
        return np.array([p[0] - center[0] + self.spec['serverOrigin'][0] - .5,
                         self.spec['serverOrigin'][1] - (p[2] - center[1]) - .5])

    def previous_tile(self, old):
        """The tile this original point was served at by the previous publication, if any."""
        if not self.previous:
            return None
        prior = self.previous.get('regions', {}).get(self.region, {})
        served = prior.get('baselineTilePositions', {}).get(key(old))
        return None if served is None else [int(served[0]), int(served[1])]

    def in_grid(self, tile):
        return self.bounds.index_xy(*map(int, tile)) is not None

    def array_tile(self, tile):
        """Convert one logical public tile at an array/flood boundary."""
        index = self.bounds.index_xy(*map(int, tile))
        if index is None:
            raise ValueError(f'{self.region}: logical tile {tile} is outside storage')
        return index

    def valid(self, tile, shape=(1, 1), allow_reserved=False, mask=None):
        width, depth = shape
        x0, y0 = tile[0] - (width - 1) // 2, tile[1] - (depth - 1) // 2
        index = self.bounds.index_xy(int(x0), int(y0))
        if index is None:
            return False
        x0, y0 = index
        x1, y1 = x0 + width, y0 + depth
        if x1 > self.bounds.width or y1 > self.bounds.height:
            return False
        ground = self.reachable if mask is None else mask
        return bool(ground[y0:y1, x0:x1].all() and
                    (allow_reserved or not self.reserved[y0:y1, x0:x1].any()))

    def reserve(self, tile, shape=(1, 1), margin=0):
        width, depth = shape
        x, y = self.array_tile(tile)
        x0 = max(0, x - (width - 1) // 2 - margin)
        y0 = max(0, y - (depth - 1) // 2 - margin)
        self.reserved[y0:min(self.grid.shape[0], y0 + depth + 2 * margin),
                      x0:min(self.grid.shape[1], x0 + width + 2 * margin)] = True

    def failure(self, label, old, expected, radius, reason):
        origin = self.spec['serverOrigin']
        center = self.world.regions[self.region]['center']
        self.failures.append({'region': self.region, 'record': label, 'oldTile': old,
            'expectedTile': np.round(expected, 3).tolist(),
            'expectedGlobalXZ': [round(float(expected[0] + .5 - origin[0] + center[0]), 3),
                                 round(float(origin[1] - expected[1] - .5 + center[1]), 3)],
            'maximumDisplacementMetres': radius, 'reason': reason})

    def nearest(self, expected, radius, shape=(1, 1), allow_reserved=False, mask=None):
        x, y = expected
        x0, x1 = max(self.bounds.min_x, math.ceil(x - radius)), min(self.bounds.max_x, math.floor(x + radius) + 1)
        y0, y1 = max(self.bounds.min_y, math.ceil(y - radius)), min(self.bounds.max_y, math.floor(y + radius) + 1)
        if x0 >= x1 or y0 >= y1:
            return None
        ground = self.reachable if mask is None else mask
        ix, iy = self.bounds.index_xy(x0, y0)
        ys, xs = np.nonzero(ground[iy:iy+y1-y0, ix:ix+x1-x0])
        xs, ys = xs + x0, ys + y0
        distance = (xs - x) ** 2 + (ys - y) ** 2
        # Stable y/x tie-breaking makes byte-identical source produce byte-identical output.
        for i in np.argsort(distance, kind='stable'):
            if distance[i] > radius ** 2 + 1e-8:
                break
            tile = (int(xs[i]), int(ys[i]))
            if self.valid(tile, shape, allow_reserved, mask):
                return list(tile)
        return None

    def place_body(self, expected, radius, shape, label):
        """Nearest standing point whose static body seals no ground beyond its footprint.

        The live server routes every walker around the tiles an actor stands
        on, so a body in a one-tile mouth would cut a whole pocket of placed
        or later content off the inhabited arrival. Ground behind an accepted
        body is likewise withdrawn from every later placement.
        """
        width, depth = shape
        excluded = np.zeros(self.grid.shape, dtype=bool)
        arrival = self.array_tile(self.spec['arrival'])
        placed = {tuple(t) for t in self.spec['tilePositions'].values()} | set(self.fixed) | set(self.held)
        placed = {self.array_tile(tile) for tile in placed}
        # Held lanes run the length of every border: thousands of tiles, asked after every trial body.
        px, py = (np.array(v, dtype=int) for v in zip(*placed)) if placed else (np.zeros(0, int), np.zeros(0, int))
        for _ in range(256):
            tile = self.nearest(expected, radius, shape, mask=self.reachable & ~excluded)
            if tile is None:
                return None
            x, y = self.array_tile(tile)
            x0, y0 = x - (width - 1) // 2, y - (depth - 1) // 2
            window = np.s_[y0:y0 + depth, x0:x0 + width]
            saved = self.grid[window].copy()
            self.grid[window] = 0
            reachable = self.sources.reachable_from(self.grid, arrival, 2)
            lost = int(self.reachable.sum()) - int(reachable.sum())
            cut = self.reachable[py, px] & ~reachable[py, px] & ((px != x) | (py != y))
            severed = lost > width * depth + 2 or bool(cut.any())
            if severed:
                self.grid[window] = saved
                excluded[window] = True
                self.report['regions'][self.region].setdefault('bodyRelocations', []).append(
                    {'record': label, 'rejectedTile': list(tile), 'sealedTiles': lost})
                continue
            self.reachable = reachable
            self.bodies.add(tuple(tile))
            return tile
        return None

    def place(self, old, label, radius, shape=(1, 1), reserve=False, identity=None, body=False,
              reuse_existing=False):
        old = list(map(int, old))
        expected = self.expected(old, identity)
        if (label == 'territories.txt' and identity is None and self.previous is not None and
                self.region in getattr(self.content, 'authored_regions', ()) and
                self.nearest(expected, radius, shape, allow_reserved=True) is None):
            # These legacy attacker/defender coordinates have no scene marker.
            # Once the terrain is saved, its source frame is no longer the
            # procedural layout transform. If that raw position has no
            # reachable ground within the original budget, the last certified
            # publication supplies the served source frame instead. Ordinary
            # viable points and exact authored bindings retain their behavior.
            served = self.previous_tile(old)
            if served is not None:
                expected = np.asarray(served, float)
        binding = self.runtime_binding(identity)
        if binding is not None:
            self.spec.setdefault('runtimeBindings', {}).setdefault(identity, copy.deepcopy(binding))
        marker_key = None if binding is None else (
            binding['marker']['section'], binding['marker']['id'],
            tuple(map(float, binding['targetOffset'])))
        existing = (self.spec['runtimeMarkerPositions'].get(marker_key)
                    if marker_key is not None else self.spec['tilePositions'].get(key(old)))
        # A high-level contract can seat a shared point before its record is
        # visited.  The territory arrival is the concrete case: connect_hub()
        # chooses its exact walkable tile before territories.txt is rewritten.
        # Preserve that tile while still consuming the qualified authored
        # binding; marker aliases remain governed by runtimeMarkerPositions.
        if (reuse_existing and existing is None and binding is not None
                and key(old) in self.spec['tilePositions']):
            candidate = self.spec['tilePositions'][key(old)]
            if (list(candidate) == list(self.spec['arrival']) and
                    float(np.linalg.norm(np.asarray(candidate, float) - expected)) <= radius + 1e-8):
                existing = candidate
        served = None if body or binding is not None else self.previous_tile(old)
        if existing is not None:
            # Records that share both a marker and its semantic endpoint offset
            # must keep one served tile. Distinct offsets intentionally remain
            # distinct (for example a cave door and its return square), while a
            # marker edit translates every endpoint by the same delta.
            tile = list(existing) if self.valid(existing, shape, allow_reserved=True) else None
        elif body:
            tile = self.place_body(expected, radius, shape, label)
        elif (served is not None and self.valid(served, shape)
              and float(np.linalg.norm(np.asarray(served, float) - expected)) <= radius + 1e-8):
            # Continuity: a point keeps the tile it was served at in the previous
            # publication while that tile still stands within its movement
            # budget. Saved positions keep their mapping, and points that shared
            # one served tile keep sharing it, which the rebase table requires.
            tile = list(served)
            self.continuity['keptServedTile'] += 1
        elif (served is not None and self.moved.get(key(served)) is not None
              and self.valid(self.moved[key(served)], shape, allow_reserved=True)
              and float(np.linalg.norm(np.asarray(self.moved[key(served)], float) - expected)) <= radius + 1e-8):
            # The served tile was lost (blocked or reserved this time): points
            # that shared it move together to where the first of them went.
            tile = list(self.moved[key(served)])
            self.continuity['movedTogether'] += 1
        else:
            tile = self.nearest(expected, radius, shape)
            if served is not None and tile is not None and list(tile) != list(served):
                self.moved.setdefault(key(served), list(tile))
                self.continuity['movedFromServedTile'] += 1
        if tile is None:
            self.failure(label, old, expected, radius, 'No hub-connected unoccupied standing point with the required footprint')
            return None
        displacement = float(np.linalg.norm(np.asarray(tile) - expected))
        if displacement > radius + 1e-8:
            self.failure(label, old, expected, radius, 'Shared source tile was already resolved outside this record\'s movement budget')
            return None
        if binding is not None:
            self.spec['runtimeBindingPositions'][identity] = list(tile)
            self.spec['runtimeBindingSourceTiles'][identity] = list(old)
            self.spec['runtimeMarkerPositions'][marker_key] = list(tile)
            # Keep one deterministic compatibility mapping for generic source
            # references. Exact bound profile rows use runtimeBindingPositions.
            self.spec['tilePositions'].setdefault(key(old), list(tile))
        else:
            self.spec['tilePositions'][key(old)] = tile
        if reserve:
            self.reserve(tile, shape)
        self.records.append({'region': self.region, 'record': label, 'oldTile': old, 'tile': tile,
            'expectedTile': np.round(expected, 3).tolist(), 'displacementMetres': round(displacement, 3),
            'maximumDisplacementMetres': radius, 'footprint': list(shape),
            **({'runtimeBindingId': identity} if binding is not None else {})})
        return tile

    def place_instance_exit(self, identity, source, previous_tile):
        """Reserve an independently identified return, never the generic tile cache."""
        old = source['originalTile']
        publisher = importlib.import_module('publish_diagonal_continent')
        binding = self.runtime_binding(identity)
        if self.runtime_binding_region(identity) != self.region:
            raise PlacementError(f'{identity}: instance binding belongs to another or missing region')
        publisher.validate_instance_binding(publisher.CLIENT, identity, source, binding)
        expected = self.expected(old, identity=identity)
        table = self.spec.setdefault('instanceExitPositions', {})
        if identity in table:
            raise PlacementError(f'{identity}: duplicate instance placement')
        shared_exit = next((entry['tile'] for entry in table.values()
                            if entry['expectedTile'] == expected.tolist() and
                            self.valid(entry['tile'], allow_reserved=True)), None)
        tile = shared_exit
        preferred = list(map(int, np.rint(expected)))
        if tile is None and self.valid(preferred):
            tile = preferred
        if tile is None:
            tile = self.nearest(expected, 5.)
        if tile is None:
            self.failure(identity, old, expected, 5., 'No independent hub-connected instance exit within five metres')
            return None
        tile = list(map(int, tile))
        entry = {'source': copy.deepcopy(source), 'previousTile': list(previous_tile),
                 'expectedTile': expected.tolist(), 'tile': tile, 'maximumDisplacementMetres': 5}
        point = np.asarray(self.content.authored_runtime_points[(self.region, identity)], dtype=float)
        entry['authoredBinding'] = copy.deepcopy(binding)
        entry['expectedSource'] = {'bindingId': identity, 'region': self.region,
            'marker': copy.deepcopy(binding['marker']), 'globalPosition': point.tolist(),
            'serverOrigin': list(self.spec['serverOrigin']),
            'translation': list(self.spec['translation'])}
        table[identity] = entry
        self.spec.setdefault('runtimeBindings', {})[identity] = copy.deepcopy(binding)
        self.spec.setdefault('runtimeBindingPositions', {})[identity] = list(tile)
        self.spec.setdefault('runtimeBindingSourceTiles', {})[identity] = list(old)
        self.fixed.add(tuple(tile))
        self.reserve(tile)
        self.records.append({'region': self.region, 'record': identity, 'oldTile': list(old),
                             'previousTile': list(previous_tile), 'expectedTile': expected.tolist(),
                             'tile': tile, 'displacementMetres': math.dist(tile, expected),
                             'previousServedDisplacementMetres': math.dist(tile, previous_tile),
                             'maximumDisplacementMetres': 5, 'footprint': [1, 1],
                             'binding': 'independent instance exit'})
        return tile

    def validate_instance_exits(self, departures):
        # NPC placement owns a copy of the served grid. Recompute from that final
        # grid, not the earlier crossing fold, before certifying every return.
        self.reachable = self.sources.reachable_from(self.grid, self.array_tile(self.spec['arrival']), 2)
        for identity, entry in self.spec.get('instanceExitPositions', {}).items():
            tile = entry['tile']
            if not self.valid(tile, allow_reserved=True) or tuple(tile) in departures:
                raise PlacementError(f'{identity}: post-content instance exit lost hub access or triggers a portal')
            entry['postContent'] = {'standing': True, 'hubAccessible': True, 'noPortalTrigger': True}

    def authored_default_spawn_tile(self):
        """Return the saved default spawn tile for an authored territory.

        A saved default spawn is a visible authoring control even when no
        immutable server-profile record names it.  It therefore seats the
        contract hub without inventing a runtime binding identity.
        """
        authored_regions = getattr(self.content, 'authored_regions', None)
        if authored_regions is None or self.region not in authored_regions:
            return None
        spawns = self.content.templates[self.region].get('spawnPoints', [])
        if not spawns:
            raise PlacementError(f'{self.region}: authored publication lost every spawn point')
        defaults = [spawn for spawn in spawns if spawn.get('default')]
        if len(defaults) > 1:
            raise PlacementError(f'{self.region}: authored publication has multiple default spawns')
        selected = defaults[0] if defaults else spawns[0]
        tile = selected.get('serverTile', selected.get('server_tile'))
        if not (isinstance(tile, (list, tuple)) and len(tile) == 2
                and all(isinstance(value, (int, np.integer)) for value in tile)):
            raise PlacementError(
                f'{self.region}:{selected.get("id")}: authored default spawn has no exact server tile')
        return list(map(int, tile))

    def connect_hub(self, old_arrival, preferred=None):
        center = np.asarray(self.world.regions[self.region]['center'], dtype=float)
        hub = np.asarray(self.world.hub(self.region) if hasattr(self.world, 'hub') else center, dtype=float)
        # The inhabited arrival can differ from the geographic ownership seed.
        # Express it in the same unchanged territory-local server address.
        offset = hub - center
        expected = np.asarray(self.spec['serverOrigin'], dtype=float) + offset * [1., -1.] - .5
        authored_spawn_tile = self.authored_default_spawn_tile()
        if authored_spawn_tile is not None:
            expected = np.asarray(authored_spawn_tile, dtype=float)
        arrival = self.nearest(expected, 12., mask=preferred) if preferred is not None else None
        preference = 'largest component within hub budget' if arrival is not None else 'nearest local component'
        if arrival is None:
            arrival = self.nearest(expected, 12.)
        if arrival is None:
            self.failure('safe arrival', old_arrival, expected, 12, 'No ground within 12 m of the inhabited hub')
            self.reachable[:] = False
            return
        self.spec['arrival'] = arrival
        self.spec['tilePositions'][key(old_arrival)] = arrival
        if authored_spawn_tile is not None:
            self.spec['tilePositions'][key(authored_spawn_tile)] = arrival
        self.reachable = self.sources.reachable_from(self.grid, self.array_tile(arrival), 2)
        self.reserve(arrival, margin=2)
        self.fixed.add(tuple(arrival))
        self.report['regions'][self.region]['hubReachableTiles'] = int(self.reachable.sum())
        self.report['regions'][self.region]['arrivalSelection'] = {
            'method': preference, 'tile': arrival, 'displacementMetres': round(float(np.linalg.norm(arrival - expected)), 3)}
        if int(self.reachable.sum()) < 64:
            self.failure('safe arrival', old_arrival, expected, 12, 'Hub component has fewer than 64 tiles')

    def hold(self, tile):
        """Keep content off a tile without asking that the hub reach it: an open border's lane."""
        tile = list(map(int, tile))
        self.held.add(tuple(tile))
        self.reserve(tile, margin=1)

    def check_fixed(self, tile, label):
        tile = list(map(int, tile))
        if not self.valid(tile, allow_reserved=True):
            self.failure(label, None, np.array(tile), 0, 'Exact crossing or return is not reachable from the hub')
            return False
        self.fixed.add(tuple(tile))
        self.reserve(tile, margin=1)
        return True

    def stamp_storage(self, tiles):
        for tile in tiles:
            self.storage.add(tuple(tile))
            x, y = self.array_tile(tile)
            self.grid[max(0, y - 1):y + 2, max(0, x - 1):x + 2] = 0
            self.reserve(tile, (3, 3))
        self.reachable = self.sources.reachable_from(self.grid, self.array_tile(self.spec['arrival']), 2)
        for tile in self.fixed:
            self.check_fixed(tile, 'fixed route after storage bodies')
        for tile in tiles:
            access = self.nearest(tile, 4, allow_reserved=True)
            if access is None:
                self.failure('storage access', None, np.array(tile), 4, 'Storage has no hub-connected access within four tiles')
        self.report['regions'][self.region]['hubReachableAfterStorageTiles'] = int(self.reachable.sum())

    def local_position(self, tile):
        x, y = tile
        ix, iy = self.array_tile(tile)
        floor = float(np.mean(self.collision['heights'][iy * 2:iy * 2 + 2, ix * 2:ix * 2 + 2]))
        return [x + .5 - self.spec['serverOrigin'][0], floor,
                self.spec['serverOrigin'][1] - y - .5]


def content_rows(profile_text, ids, publisher):
    records = {group: {r: [] for r in ids} for group in ('npcs', 'harvest', 'spawns', 'interactives')}
    for filename, (keyword, mi, xi, yi, group, identity_index) in publisher.CONTENT.items():
        counts = {}
        for number, fields in rows(profile_text[filename]):
            if len(fields) <= max(mi, xi, yi) or fields[mi] not in ids or keyword and fields[0] != keyword:
                continue
            region = fields[mi]
            ordinal = counts.get(region, 0)
            counts[region] = ordinal + 1
            identity = str(ordinal) if identity_index is None else fields[identity_index]
            records[group][region].append({'id': identity, 'old': [int(fields[xi]), int(fields[yi])],
                'fields': fields, 'label': f'{filename}:{number}:{identity}'})
    return records


def place_doors(text, placements, connections):
    ids = set(placements)
    old_departures = {r: set() for r in ids}
    # Reserve automatic thresholds first: a room return must never be seated on
    # an unrelated road trigger and immediately transfer the player again.
    for connection in connections:
        for end in connection['ends']:
            p = placements[end['region']]
            for index, lane in enumerate(end.get('lanes', [end])):
                # The gate's lanes are where its road meets the border and must be
                # reachable from the hub; the rest of an open border is held clear
                # of content wherever it runs, pockets its hub cannot reach included.
                if connection.get('type') == 'walk' and 'lanes' in end and 'gate' not in lane:
                    p.hold(lane['tile']); p.hold(lane['arrival'])
                    continue
                p.check_fixed(lane['tile'], f'{connection["id"]}:departure:{index}')
                p.check_fixed(lane['arrival'], f'{connection["id"]}:arrival:{index}')
    for number, fields in rows(text):
        if fields[0] != 'portal' or len(fields) not in (7, 8):
            continue
        start = 2 if len(fields) == 7 else 3
        source, target = fields[1], fields[start + 2]
        point, arrival = list(map(int, fields[start:start + 2])), list(map(int, fields[start + 3:start + 5]))
        if source in ids and target in ids:
            old_departures[source].add(tuple(point))
            continue
        for region, old, direction in ((source, point, 'door'), (target, arrival, 'return')):
            if region not in ids:
                continue
            p = placements[region]
            label = f'maps.txt:{number}:{direction}:{source}->{target}'
            binding_id = p.runtime_identity('config/eloria/maps.txt', old, number)
            tile = p.place(old, label, 5, identity=binding_id)
            if tile is not None:
                portal_id = next((str(e['id']) for e in p.old_entries.get(key(old), []) if 'id' in e and
                    any(k in e for k in ('destinationMap', 'targetMap'))), f'profile-{number}-{direction}')
                p.spec['portalPositions'][portal_id] = {'oldTile': old, 'tile': tile,
                                                        'runtimeBindingId': binding_id}
                p.fixed.add(tuple(tile))
                p.reserve(tile)
    return old_departures


def instance_exit_predecessors(server, baseline, certificate, placements, publisher):
    """Called only after the unchanged predecessor profile guard succeeded."""
    result = {}
    for relative, digest in certificate['files'].items():
        if not relative.startswith('config/eloria/instances/') or not relative.endswith('.def'):
            continue
        original = publisher.instance_exit_records(relative, (baseline / relative).read_text(encoding='utf-8'), placements)
        current = publisher.instance_exit_records(relative, (server / relative).read_text(encoding='utf-8'), placements)
        if set(original) != set(current):
            raise PlacementError(f'{relative}: predecessor instance identities changed')
        for identity, source in original.items():
            source['sha256'] = digest
            result[identity] = (source, current[identity]['originalTile'])
    return result


def collect_gameplay_points(server, profile_text, placements, records, shared, publisher):
    """Exercise publication's own readers, so no supported source coordinate is omitted."""
    current = {'label': '', 'radius': 12., 'area': False, 'source': ''}
    def remap(region, old):
        p = placements[region]
        if key(old) in p.spec['tilePositions']:
            identity = p.runtime_identity(current['source'], old)
            if identity is not None:
                binding = p.runtime_binding(identity)
                reuse_arrival = bool(binding and binding.get('role') == 'territory' and
                                     binding.get('marker', {}).get('section') == 'spawnPoints')
                return p.place(old, current['label'], current['radius'], identity=identity,
                               reuse_existing=reuse_arrival)
            return p.spec['tilePositions'][key(old)]
        if current['area']:
            # Region rectangles are bounds, not standing points; preserve their
            # shape by using the continuous transform without snapping to a path.
            point = publisher.transform_tile(old, p.spec)
            p.spec['tilePositions'][key(old)] = point
            return point
        identity = p.runtime_identity(current['source'], old)
        tile = p.place(old, current['label'], current['radius'], identity=identity)
        return tile if tile is not None else list(map(int, np.rint(p.expected(old))))
    mappings = {r: {'delta': [0, 0], '_native_mapper': lambda old, r=r: remap(r, old)} for r in placements}
    # Bind daily objectives to the retained authoritative resource or recipient.
    daily_path = server / 'eloria/daily_quests.py'
    if daily_path.exists():
        for node in ast.walk(ast.parse(daily_path.read_text(encoding='utf-8'))):
            if not isinstance(node, ast.Call) or not isinstance(node.func, ast.Name) or node.func.id != 'DailyTask' or len(node.args) < 7:
                continue
            values = [ast.literal_eval(v) for v in node.args[:7]]
            recipient, kind_, resource, _, region, x, y = values
            if region not in placements or kind_ == 'kill':
                continue
            p = placements[region]
            if key((x, y)) in p.spec['tilePositions']:
                continue
            if kind_ == 'harvest':
                candidates = [v for v in records['harvest'][region] if v['fields'][5] == resource and
                              math.dist(v['old'], (x, y)) <= 8.01]
                candidates.sort(key=lambda v: (math.dist(v['old'], (x, y)), v['id']))
                target = p.spec['contentPositions']['harvest'].get(candidates[0]['id']) if candidates else None
            else:
                target = p.spec['contentPositions']['npcs'].get(recipient)
            if target is not None:
                p.spec['tilePositions'][key((x, y))] = list(target)
                p.records.append({'region': region, 'record': f'daily:{kind_}:{resource}',
                    'oldTile': [x, y], 'tile': list(target), 'binding': 'retained resource' if kind_ == 'harvest' else 'retained recipient'})
            else:
                p.failure(f'daily:{kind_}:{resource}', [x, y], p.expected((x, y)), 8,
                          'No retained daily resource within the old completion radius, or recipient missing')
    for filename in ('territories.txt', 'special_areas.txt'):
        if filename in profile_text:
            current.update(label=filename, radius=35., area=filename == 'special_areas.txt',
                           source='config/eloria/' + filename)
            shared.rewrite_profile(profile_text[filename], shared.RULES[filename], mappings)
    for relative, text in profile_text.items():
        if relative.endswith('.def') or relative == 'questlines.txt':
            # The publisher regenerates these deterministic files after it has
            # synced the current authored collision. Their old generated
            # coordinates are not source placements to preserve or remap.
            if relative in BUILD_REGENERATED_PROFILE:
                continue
            radius = 5. if relative.startswith('instances/') else 80. if relative.startswith('spawn_groups/') else 35.
            current.update(label=relative, radius=radius, area=False, source=relative)
            if relative.startswith('instances/') and all('instanceExitPositions' in p.spec for p in placements.values()):
                entries = {identity: entry for p in placements.values()
                           for identity, entry in p.spec['instanceExitPositions'].items()}
                publisher.rewrite_instance_exits('config/eloria/' + relative, text, mappings, entries, mode='source')
            else:
                shared.rewrite_definition(text, mappings)
    for relative, kind_ in (('eloria/world.py', 'world'), ('eloria/walkthrough.py', 'walkthrough'),
                             ('eloria/pk.py', 'pk'), ('eloria/daily_quests.py', 'daily')):
        path = server / relative
        if path.exists():
            current.update(label=relative, radius=12., area=kind_ == 'pk', source=relative)
            publisher.rewrite_gameplay_source(path.read_text(encoding='utf-8'), kind_, mappings)
    manifest = json.loads(profile_text['client_content_manifest.json'])
    specs = {r: p.spec for r, p in placements.items()}
    for entry in manifest.get('maps', []):
        region = entry.get('id')
        if region not in placements:
            continue
        entry = copy.deepcopy(entry)
        # The final portal table is rebuilt from the new graph. Its removed
        # source triggers do not remain standing-point promises.
        entry.pop('portals', None)
        current.update(label='client_content_manifest.json:' + region, radius=12., area=False)
        publisher.remap_metadata(entry, specs, mappings, region)
    for name, value in manifest.items():
        if name in ('maps', 'continentGeography', 'diagonalContinent'):
            continue
        region = next((r for r in sorted(placements, key=len, reverse=True) if name.startswith(r + '_')
                       or r == 'sunmane_steppe' and name in ('sunmane_npcs', 'sunmane_resources')), None)
        current.update(label='client_content_manifest.json:' + name,
                       radius=35. if 'harvest' in name or 'resource' in name else 12., area=False)
        publisher.remap_metadata(value, specs, mappings, region)
    return mappings


def update_markers(placement, manifest, crossing_markers=None):
    """Keep authored marker identities and room targets while seating their posts."""
    from crossings import authored_portals
    protected = (authored_portals(getattr(placement, 'world', None), placement.region)
                 if crossing_markers is None else crossing_markers)
    trigger_fields = {'serverTile', 'destinationTile'}
    for identity, source in protected.items():
        matches = [entry for entry in manifest.get('portals', [])
                   if isinstance(entry, dict) and entry.get('id') == identity]
        if len(matches) != 1 or {k: v for k, v in matches[0].items() if k not in trigger_fields} != {
                k: v for k, v in source.items() if k not in trigger_fields}:
            raise PlacementError(f'{placement.region}:{identity}: authored crossing portal changed before placement')
        for field in trigger_fields:
            matches[0][field] = list(source[field])
    template = placement.content.templates[placement.region]
    metadata_keys = ('portals', 'harvestables', 'npcMarkers', 'interactives', 'pointsOfInterest', 'creatureSpawns', 'spawns')
    updated = 0
    for group in metadata_keys:
        originals = template.get(group, [])
        by_id = {str(v['id']): v for v in originals if isinstance(v, dict) and 'id' in v}
        for index, entry in enumerate(manifest.get(group, [])):
            if not isinstance(entry, dict):
                continue
            if group == 'portals' and entry.get('id') in protected:
                # Lane legality is checked separately against the served fold.
                # A generic tile remap must not reseat the saved marker's XYZ.
                continue
            old_entry = by_id.get(str(entry.get('id')))
            if old_entry is None:
                continue
            old = old_entry.get('serverTile', old_entry.get('server_tile'))
            if old is None and 'position' in old_entry:
                origin = placement.spec['previousServerOrigin']
                old = [math.floor(old_entry['position'][0] + origin[0]),
                       math.floor(origin[1] - old_entry['position'][2])]
            tile = placement.spec['tilePositions'].get(key(old)) if old is not None else None
            if tile is None:
                continue
            entry['serverTile'] = list(tile)
            if 'server_tile' in entry:
                entry['server_tile'] = list(tile)
            entry['position'] = placement.local_position(tile)
            if 'arrivalPosition' in old_entry:
                origin = placement.spec['previousServerOrigin']
                v = old_entry['arrivalPosition']
                old_return = [math.floor(v[0] + origin[0]), math.floor(origin[1] - v[2])]
                return_tile = placement.spec['tilePositions'].get(key(old_return))
                if return_tile is not None:
                    entry['arrivalPosition'] = placement.local_position(return_tile)
            updated += 1
    authored_regions = getattr(placement.content, 'authored_regions', None)
    is_authored = (placement.region in authored_regions if authored_regions is not None
                   else placement.region == 'sunmane_steppe')
    if is_authored:
        spawns=manifest.get('spawnPoints',[])
        if not spawns:raise PlacementError(f'{placement.region}: authored publication lost every spawn point')
        defaults=[spawn for spawn in spawns if spawn.get('default')]
        if len(defaults)>1:raise PlacementError(f'{placement.region}: authored publication has multiple default spawns')
        selected=defaults[0] if defaults else spawns[0]
        manifest.setdefault('navigation', {})['defaultSpawn']=str(selected['id'])
        walking_height=float(selected['position'][1])
    else:
        arrival = placement.spec['arrival']
        manifest['spawnPoints'] = [{'id': 'continent-arrival', 'default': True,
                                   'position': placement.local_position(arrival), 'serverTile': arrival}]
        manifest.setdefault('navigation', {})['defaultSpawn'] = 'continent-arrival'
        walking_height=placement.local_position(arrival)[1]
    source_contract=getattr(getattr(placement,'world',None),'_storage_contracts',{}).get(placement.region)
    if source_contract is not None and source_contract.server_frame[4]:
        walking_height=source_contract.server_frame[5]
    manifest['coordinateTransform']['walkingHeight']=walking_height
    placement.report['regions'][placement.region]['updatedAuthoredMarkers'] = updated


def region_runtime_bindings(content, region):
    """Return only one authored region's bindings for its publication.

    Old single-region Sunmane compositions predate the qualified mapping.  Its
    flat dictionary remains a compatibility source only when no qualified map
    exists at all; once any region map is present, a missing key means that
    region deliberately has no bindings.
    """
    qualified = getattr(content, 'runtime_bindings_by_region', None)
    if qualified is not None:
        return copy.deepcopy(qualified.get(region, {}))
    if region == 'sunmane_steppe':
        return copy.deepcopy(getattr(content, 'runtime_bindings', {}))
    return {}


def content_transform(content, region):
    """The published mapping from one territory's source frame into continent metres.

    ``scale`` about ``sourceCenter``, with ``targetCenter``, is the old rule and all that
    publish_diagonal_continent.transform_tile, estimated_served_tile above, and the paired server's
    geographic_contracts.native_area_tile can read: one uniform scale, no turn. A retained transform may
    squeeze its layout per axis and turn it about its own point, which no scalar carries, so the exact
    mapping is published as ``affine`` [a, b, c, d, e, f] besides, giving continent
    X = a*x + b*z + e and Z = c*x + d*z + f for a source point (x, z). It is read straight off
    ``content.mapped_xz`` at (0, 0), (1, 0) and (0, 1), so it reproduces landscape.retained_map_xz for a
    retained territory and the centre-and-scale rule for every other one, with no second copy of either
    to drift. Note the frames: ``affine`` lands on absolute continent metres, while the old fields land
    relative to the territory's centre, this spec's ``translation``, which is what the server address
    frame is built on.

    ``scale`` stays a number wherever that mapping really is a uniform scale -- every territory on the
    centre-and-scale rule, and a retained transform that is a rigid translation -- and is null where the
    layout squeezes per axis or turns, where a scalar would be a wrong answer rather than a rounded one.
    A dict transform also publishes its own ``yawDegrees`` and ``squeeze`` [sx, sz] for a reader that
    would rather compose the turn itself than read it out of the affine.
    """
    if str(HERE) not in sys.path:
        sys.path.insert(0, str(HERE))
    import landscape as L
    probe = np.asarray(content.mapped_xz(region, [[0., 0.], [1., 0.], [0., 1.]]), float).reshape(3, 2)
    a, c = probe[1] - probe[0]
    b, d = probe[2] - probe[0]
    e, f = probe[0]
    declared = np.asarray(content.scales[region], float).ravel()
    tolerance = 1e-9 * max(1., abs(a), abs(d))
    uniform = abs(b) <= tolerance and abs(c) <= tolerance and abs(a - d) <= tolerance
    published = {'scale': float(declared[0]) if uniform else None,
        'sourceCenter': np.asarray(content.source_centers[region], float).ravel().tolist(), 'targetCenter': [0, 0],
        'affine': [float(a), float(b), float(c), float(d), float(e), float(f)]}
    transform = getattr(content, 'transforms', {}).get(region)
    if isinstance(transform, dict):
        published['yawDegrees'] = float(L.retained_yaw_degrees(transform))
        published['squeeze'] = [float(value) for value in L.retained_affine(transform)[1]]
    return published


def export_contracts(world, content, manifests, output, server_path):
    """Export exact placement/publication data; leave authoritative server files alone."""
    output, server = Path(output).resolve(), Path(server_path).resolve()
    output.mkdir(parents=True, exist_ok=True)
    exported = json.loads((output / 'export.json').read_text(encoding='utf-8'))
    if not hasattr(world, 'publication_connections'):
        raise ValueError('Survey exact crossing contracts before exporting standing points')
    modules = server_modules(server)
    sources, sync = modules['collision_sources'], modules['sync_authored_collision']
    shared, publisher = modules['publish_continent_geography'], modules['publish_diagonal_continent']
    baseline, certificate, current_manifest = frozen_profile(server, shared)
    previous = previous_release(current_manifest)
    if previous and not (baseline / 'interior-return-targets.json').exists():
        raise ValueError('Original interior return snapshot is missing after publication; do not sample already-transformed room metadata')
    interior_returns = freeze_return_targets(baseline, publisher)
    # Rows added after the freeze are certified by the committed amendment.
    amendment = amendments.for_certificate(amendments.load(HERE / amendments.PATH.name), certificate)
    amendments.validate(amendment, {name: (baseline / 'config/eloria' / name).read_text(encoding='utf-8')
                                    for name in publisher.CONTENT}, publisher.CONTENT)
    verify_current_profile(server, baseline, certificate, previous, shared, publisher, amendment)
    profile = baseline / 'config/eloria'
    relative_paths = [relative for relative in certificate['files'] if relative.startswith('config/eloria/')]
    profile_paths = [server / relative for relative in relative_paths]
    fingerprints = {relative.removeprefix('config/eloria/'): sha(server / relative) for relative in relative_paths}
    texts = amendments.amend({relative.removeprefix('config/eloria/'): (baseline / relative).read_text(encoding='utf-8')
                              for relative in relative_paths}, amendment)
    old_manifest = json.loads(texts['client_content_manifest.json'])
    old_maps = {v['id']: v for v in old_manifest['maps']}
    creatures = modules['eloria.creatures'].load_creatures(profile / 'creatures.txt')
    records = content_rows(texts, world.ids, publisher)
    report = {'schema': 1, 'revision': REVISION, 'placements': [], 'failures': [], 'regions': {},
        'sourceProfileSha256': fingerprints, 'sourceCodeSha256': {relative: sha(server / relative)
        for relative in GAMEPLAY_SOURCES if (server / relative).exists()}, 'baselineSha256': sha(baseline / 'snapshot.json')}
    if amendment is not None:
        report['contentAmendmentSha256'] = amendment['sha256']
    publication = {'schema': 1, 'revision': REVISION, 'masterPath': exported['masterPath'],
        'masterSha256': exported['masterSha256'], 'sourceProfileSha256': fingerprints,
        'instanceExitSchema': 2,
        'regions': {}, 'connections': copy.deepcopy(world.publication_connections),
        'visualConnections': copy.deepcopy(getattr(world, 'visual_connections', [])),
        'preloadDistance': 320, 'retainDistance': 420, 'maxResidentAdjacentMaps': 3,
        'baselineSha256': report['baselineSha256'], 'sourceCodeSha256': report['sourceCodeSha256'],
        **({'contentAmendmentSha256': amendment['sha256']} if amendment is not None else {})}
    previous_publication = current_manifest.get('diagonalContinent', {}).get('publicationSha256')
    if previous_publication:
        publication['sourcePublicationSha256'] = previous_publication
    placements, outputs, served = {}, {}, {}
    if str(HERE) not in sys.path:
        sys.path.insert(0, str(HERE))
    from collision_export import export_collision, storage_contract
    from crossing_contracts import GR, POLICY as CROSSING_POLICY, declare_crossings
    from crossings import storage_bounds
    world_digest = None
    try:
        for region in world.ids:
            started = time.monotonic()
            manifest = copy.deepcopy(manifests[region])
            origin, cells = world.address(region)
            center = world.regions[region]['center']
            world_path = Path(exported['regions'][region]['world']).resolve()
            collision_path = world_path.parent / 'collision.bin'
            glb_path = world_path.parent / manifest['asset'].get('glb', 'world.glb')
            result = getattr(world, 'collision_exports', {}).get(region)
            if result is None:
                if world_digest is None:
                    world_digest = collision_world_digest(world)
                result = cached_collision(world, region, manifest, glb_path, collision_path, output, world_digest)
            elif not collision_path.exists():
                raise ValueError(f'{region}: cached collision requires its matching exported EWCG file')
            manifest['collision'] = copy.deepcopy(result['collision'])
            grid, factor, largest, detail = fold_server_grid(result, sources, sync)
            # Declared crossings come from this served fold, never from the geometry stage.
            document, body = GR.load(glb_path)
            crossings, declared, not_walkable = declare_crossings(document, body, region, grid, sync.CLIMB_LIMIT,
                                                                  origin, cells, result['heights'], bounds=storage_bounds(world, region))
            del document, body
            manifest.setdefault('navigation', {})['crossings'] = crossings
            report['regions'][region] = {'stageFactor': factor, 'stageMetres': factor * .2,
                'walkableServerTiles': int((grid != 0).sum()), 'largestComponentTiles': int(largest.sum()), **detail,
                'crossings': {'declared': declared, 'notWalkable': not_walkable, 'climbLimit': sync.CLIMB_LIMIT, 'policy': CROSSING_POLICY}}
            spec = {'serverOrigin': list(origin), 'serverCells': list(cells),
                **storage_record(cells, storage_contract(world, region)),
                'translation': [float(center[0]), 0, float(center[1])], 'arrival': list(origin),
                'terrainRevision': REVISION,
                'previousServerOrigin': list(content.templates[region]['coordinateTransform']['serverOrigin']),
                'contentTransform': content_transform(content, region),
                'contentPositions': {group: {} for group in records}, 'tilePositions': {},
                # Runtime bindings are published by the server record's region,
                # not by the saved marker's region. A Whitehorn door can be
                # driven by an Amethyst marker, for example. ``place`` installs
                # each exact binding when that qualified source record is used.
                'runtimeBindings': {},
                'runtimeBindingPositions': {}, 'runtimeBindingSourceTiles': {},
                'runtimeMarkerPositions': {},
                'portalPositions': {}, 'removedInteractiveIds': [],
                'collisionPath': str(collision_path), 'worldManifestPath': str(world_path)}
            p = RegionPlacement(world, content, region, spec, result, grid, sources, report, previous=previous)
            p.connect_hub(old_maps[region]['arrival'], largest)
            # A seam is crossed wherever both maps' grids can stand, from this
            # map's own ground beside it (crossings.crossing_lanes); which of those
            # lanes a walker can actually get to is settled once every map's grid
            # is folded (crossings.settle_crossings).
            from crossings import own_ground
            if any(c.get('type') == 'walk' and region in c.get('regions', ())
                   for c in list(getattr(world, 'connections', ())) + list(getattr(world, 'open_border_links', ()))):
                served[region] = own_ground(world, region, grid)
            placements[region], outputs[region], publication['regions'][region] = p, (world_path, manifest), spec
            print(f'{region}: exact server grid, stage {factor}, hub reaches {int(p.reachable.sum())} tiles in {time.monotonic()-started:.1f}s', flush=True)
        # Every seam's lanes come from the served grids of both its maps, so
        # this waits until the last of them has been folded.
        from crossings import settle_crossings, widen_seams, authored_portals
        step = lambda heights, y, x, dy, dx: sources.walk_step_ok(heights, y, x, dy, dx, 2)
        report['seams'] = widen_seams(world, publication['connections'], served, step)
        # Borders no road crosses, opened wherever their ground meets; then only
        # the lanes a walker from some hub can get onto and step off are kept.
        settled = settle_crossings(world, publication, served, step,
                                    {region: p.spec['arrival'] for region, p in placements.items()})
        crossing_markers = {region: authored_portals(world, region, publication['connections'])
                            for region in placements}
        report['seams'] += settled['roadless']
        report['openBorders'], report['withdrawnLanes'] = settled['opened'], settled['withdrawnLanes']
        print('open roadless borders: %s; %d lanes no walker can use withdrawn' % (
            ', '.join(settled['opened']) or 'none', settled['withdrawnLanes']), flush=True)
        for seam in report['seams']:
            print('%s: %s' % (seam['id'], ', '.join(
                '%s %d lanes (gate %d on its own lanes, %d moved)' % (
                    end['region'], end['lanes'], end['gateLanes'], end.get('gateLanesMoved', 0))
                for end in seam['ends'])), flush=True)
        _, crossing_rows = publisher.connection_rows(publication['connections'], publication['regions'])
        # The publish tool used to prove a departure against the far side's own
        # lane list; now that it reads the arrival straight out of the shared
        # grid, this is the question that check was standing in for - can an
        # actor be put down where the crossing sends them.
        widened = {(end['region'], other['region']) for seam in report['seams']
                   for end, other in (seam['ends'], seam['ends'][::-1])}
        def arrival_stands(row):
            index = placements[row[3]].bounds.index_xy(int(row[4]), int(row[5]))
            return index is not None and bool(served[row[3]]['grid'][index[1], index[0]])
        stranded = [row for row in crossing_rows if row[0] in served and row[3] in served and not arrival_stands(row)]
        report['crossingArrivals'] = {'rows': len(crossing_rows), 'unreachable': len(stranded),
                                      'examples': [list(row) for row in stranded[:8]]}
        refused = [row for row in stranded if (row[0], row[3]) in widened]
        if refused:
            raise ValueError('crossing arrivals stand on ground the destination refuses: '
                             + ', '.join('%s %s -> %s %s' % (r[0], r[1:3], r[3], r[4:6]) for r in refused[:8]))
        # Where a crossing puts a walker down is kept clear of content on the far
        # map as well: an actor stood there would leave the arrival nowhere to go.
        for row in crossing_rows:
            if (row[0], row[3]) in widened and row[3] in placements:
                placements[row[3]].hold([row[4], row[5]])
        place_doors(texts['maps.txt'], placements, publication['connections'])
        for p in placements.values():
            p.spec['instanceExitPositions'] = {}
        instance_sources = instance_exit_predecessors(server, baseline, certificate, placements, publisher)
        for identity, (source, previous_tile) in instance_sources.items():
            placements[source['map']].place_instance_exit(identity, source, previous_tile)
        if report['failures']:
            raise PlacementError('Instance exit placement failed; see contract-placement-report.json')
        chunk_metadata = []
        for region, p in placements.items():
            storage = []
            for row in records['interactives'][region]:
                fields = row['fields']
                if fields[4:6] == ['portal', 'maps.txt']:
                    p.spec['removedInteractiveIds'].append(row['id'])
                    source_file, source_line, _ = row['label'].split(':', 2)
                    binding_id = p.runtime_identity('config/eloria/' + source_file,
                                                    row['old'], int(source_line))
                    if binding_id is not None:
                        p.place(row['old'], row['label'], 5., identity=binding_id)
                    continue
                if fields[4] != 'storage':
                    continue
                source_file, source_line, _ = row['label'].split(':', 2)
                binding_id = p.runtime_identity('config/eloria/' + source_file, row['old'], int(source_line))
                tile = p.place(row['old'], row['label'], 12., shape=(3, 3), reserve=True,
                               identity=binding_id)
                if tile is not None:
                    p.spec['contentPositions']['interactives'][row['id']] = tile
                    storage.append(tile)
            if storage:
                p.stamp_storage(storage)
            for group in ('interactives', 'npcs', 'harvest', 'spawns'):
                for row in records[group][region]:
                    if group == 'interactives' and (row['id'] in p.spec['removedInteractiveIds'] or row['id'] in p.spec['contentPositions'][group]):
                        continue
                    shape = (1, 1)
                    if group == 'spawns':
                        species = row['fields'][2]
                        if species not in creatures:
                            raise ValueError(f'{row["label"]}: unknown authoritative creature {species}')
                        creature = creatures[species]
                        shape = (creature.footprint_width, creature.footprint_depth)
                    radius = {'interactives': 12, 'npcs': 12, 'harvest': 35, 'spawns': 80}[group]
                    source_file, source_line, _ = row['label'].split(':', 2)
                    binding_id = p.runtime_identity('config/eloria/' + source_file,
                                                    row['old'], int(source_line))
                    identity = binding_id if p.runtime_binding(binding_id) is not None else (
                        row['id'] if group == 'npcs' else None)
                    tile = p.place(row['old'], row['label'], radius, shape, reserve=True,
                                   identity=identity, body=group == 'npcs')
                    if tile is not None:
                        p.spec['contentPositions'][group][row['id']] = tile
        collect_gameplay_points(baseline, texts, placements, records, shared, publisher)
        for target in interior_returns:
            p = placements[target['region']]
            # Return metadata may name the same point as a bound doorway.
            identity = p.runtime_identity('config/eloria/maps.txt', target['oldTile'])
            p.place(target['oldTile'], 'interior return:' + target['source'], 5., identity=identity)
        # Exact published departures include room doors as well as shared borders.
        instance_specs = {r: p.spec for r, p in placements.items()}
        instance_maps = {r: {'delta': [0, 0], '_native_mapper': lambda old, spec=spec: publisher.transform_tile(old, spec)}
                         for r, spec in instance_specs.items()}
        bound_originals = {name: texts[name] for name in ('maps.txt', 'territories.txt')}
        bound_rewritten = {name: shared.rewrite_profile(text, shared.RULES[name], instance_maps)[0]
                           for name, text in bound_originals.items()}
        publisher.rewrite_runtime_binding_sources(bound_originals, bound_rewritten, instance_specs,
                                                  certified_texts=bound_originals)
        staged_maps, _ = publisher.replace_crossings(bound_rewritten['maps.txt'], publication['connections'], instance_specs)
        departures = {r: set() for r in placements}
        for _, fields in rows(staged_maps):
            if fields[0] == 'portal' and len(fields) in (7, 8) and fields[1] in departures:
                start = 2 if len(fields) == 7 else 3
                departures[fields[1]].add(tuple(map(int, fields[start:start + 2])))
        for region, p in placements.items():
            p.validate_instance_exits(departures[region])
        publisher.validate_instance_exit_table(instance_specs, {k: v[0] for k, v in instance_sources.items()},
                                               require_authored=True)
        expected_bindings = set(getattr(content, 'runtime_bindings', {}))
        binding_regions = {}
        for region, placement in placements.items():
            for identity in placement.spec['runtimeBindings']:
                if identity in binding_regions:
                    raise PlacementError(
                        f'{identity}: authored runtime binding was consumed by both '
                        f'{binding_regions[identity]} and {region}')
                binding_regions[identity] = region
        if set(binding_regions) != expected_bindings:
            missing = sorted(expected_bindings - set(binding_regions))
            extra = sorted(set(binding_regions) - expected_bindings)
            raise PlacementError(
                f'authored runtime bindings were not consumed exactly once; '
                f'missing={missing[:8]}, extra={extra[:8]}')
        if report['failures']:
            raise PlacementError(f'{len(report["failures"])} continent contracts need authored geometry or placement corrections; see contract-placement-report.json')
        # The frozen inputs must still be the source of every remap we emit.
        for path in profile_paths:
            if sha(path) != fingerprints[path.relative_to(server / 'config/eloria').as_posix()]:
                raise ValueError(f'{path}: profile changed during content placement')
        for region, p in placements.items():
            path, manifest = outputs[region]
            update_markers(p, manifest, crossing_markers[region])
            p.spec.pop('runtimeMarkerPositions', None)
            p.spec['terrainRevision'] = terrain_revision(p.spec, p.collision, p.grid)
            report['regions'][region]['terrainRevision'] = p.spec['terrainRevision']
            report['regions'][region]['servedTileContinuity'] = dict(p.continuity)
            chunk_metadata.extend(revision_metadata(path, manifest, p.spec, publication['masterSha256']))
            chosen = set(tuple(v) for v in p.spec['tilePositions'].values())
            chosen.update(p.fixed)
            chosen.update(p.held)
            p.spec['tileHeights'] = {key(tile): p.local_position(tile)[1] for tile in sorted(chosen)
                                    if p.in_grid(tile)}
        rebase_publication(publication, previous)
        for child_path, child in chunk_metadata:
            write_json(child_path, child)
        for region, (path, manifest) in outputs.items():
            manifests[region].clear()
            manifests[region].update(manifest)
            write_json(path, manifest)
        write_json(output / 'publication.json', publication)
        history = HERE / 'publication-history' / (sha(output / 'publication.json') + '.json')
        history.parent.mkdir(parents=True, exist_ok=True)
        history.write_bytes((output / 'publication.json').read_bytes())
        report['ready'] = True
        return publication
    finally:
        report.setdefault('ready', False)
        write_json(output / 'contract-placement-report.json', report)
