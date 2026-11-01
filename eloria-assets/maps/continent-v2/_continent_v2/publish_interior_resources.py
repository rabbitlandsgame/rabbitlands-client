"""Amend the three approved Upper Galleries coal nodes while retaining certified geometry.

This deliberately supports only IDs 19901..19903 and four known half-cell closures.
Inputs are genuine base/proposed build packages (with their resource closures),
source plans and scenery configs. Rebuilt GLBs must agree with each other; they
are never promoted. The certified GLB is pinned below: Shapely enumeration and
image canonicalisation make a fresh baseline differ from that older export.
Unchanged exterior/door validation is inherited from the sealed publication,
not reconstructed with invented bakes. Full publish_server --check is separate.
If server exteriors predate the current client, --frozen-exteriors names an
explicit historical REGION/client package view. Its binaries must match the
sealed server publication; newer current client exterior files stay immutable.
The view also supplies crossings.json for that same sealed server publication.
prepare() writes nothing. --bundle saves a reviewable recovery bundle before
--apply replaces local files. --resume continues that exact bundle after a crash.
"""
from __future__ import annotations

import argparse
import copy
import hashlib
import json
import os
from pathlib import Path
import shutil
import struct
import sys
import tempfile
from types import SimpleNamespace

import numpy as np
import underground as U
import underground_source as S

HERE = Path(__file__).resolve().parent
RELATIVE = Path('eloria-assets/maps/continent-v2/_continent_v2')
REGION, SECTION = 'landfall_insides', 'lantern_upper_galleries'
NODES = [[19901, 'Coal', 510, 550], [19902, 'Coal', 511, 551], [19903, 'Coal', 512, 552]]
CLOSURES = {(1022, 1102), (1023, 1102), (1023, 1103), (1025, 1104)}
CERTIFIED_GLB_SHA = 'f0e294abec5a56a59c13f697bb9dcdb6180d36ae5064078edcfc2fe2f85f89b4'
BACKGROUND_CATALOG_SHA = '2323ae3660669d1fbd6f36cd012ef97eb283873e50fc0a2c370e04caa19dc6fc'
RECEIPTS = 'interiorResourceAmendments'


def sha(data): return hashlib.sha256(data).hexdigest()
def read_json(data): return json.loads(data)
def require(condition, message):
    if not condition: raise ValueError(message)


def source_delta(base, proposed):
    S.check(base); S.check(proposed)
    expected = copy.deepcopy(base)
    require(base['map']['id'] == REGION and base['map']['cells'] == 720, 'Unsupported interior frame.')
    section = next(s for s in expected['sections'] if s['id'] == SECTION)
    require(not section['nodes'] and not section.get('veins'), 'Expected the certified node-free galleries.')
    section['nodes'] = copy.deepcopy(NODES)
    section['veins'] = [{'resource': 'Coal', 'nodes': [n[0] for n in NODES]}]
    require(expected == proposed, 'Only the three approved nodes and their vein may change; doors/layout/content changed.')


def collision_delta(base, proposed):
    header = struct.pack('<4sHHII', b'EWCG', 2, 0, 1440, 1440)
    require(base[:16] == proposed[:16] == header and len(base) == len(proposed) == 16 + 1440**2,
            'Unexpected EWCG header or payload.')
    changes = {(i % 1440, i // 1440): (a, b) for i, (a, b) in enumerate(zip(base[16:], proposed[16:])) if a != b}
    require(changes == {tile: (1, 0) for tile in CLOSURES}, 'EWCG may only close the four approved half-cells.')


def scenery_delta(base, proposed, old_sha, new_sha, current=None):
    expected = copy.deepcopy(base)
    require(expected['sourcePlanSha256'] == old_sha, 'Scenery baseline source is stale.')
    expected['sourcePlanSha256'] = new_sha
    for index, (yaw, inset) in enumerate(((83.3, 1.009), (42.0, 1.375), (32.3, 1.11))):
        oid = str(19901 + index)
        require(oid not in expected['harvestPresentation'], 'Scenery already contains an added node.')
        expected['harvestPresentation'][oid] = dict(resource='Coal', placement='wall', variant=index, yaw=yaw, inset=inset)
    removals = []
    for x, y, yaw, scale, outward in ((508.77, 550.19, 67, 1.02, [-1.0, 0, -0.014]),
                                     (510.89, 553.71, 204, 1.09, [-0.546, 0, -0.838])):
        placement = dict(asset='veined_crag_4', position=[x, -0.3, 720-y], yaw=yaw, scale=scale,
                         outward=outward, palette={'stone': '#77736c', 'mineral': '#e0a64c'})
        require(expected['placements'].count(placement) == 1, 'Expected nonblocking wall-rock placement is absent/duplicated.')
        expected['placements'].remove(placement)
        removals.append(placement)
    require(expected == proposed, 'Scenery changed beyond three wall seams and two nonblocking wall rocks.')
    # GEOS may enumerate unrelated old wall faces differently in a fresh build.
    # Keep every certified placement/hint, changing only the proved local delta.
    current = copy.deepcopy(base if current is None else current)
    require(all(current[k] == base[k] for k in set(base) - {'placements', 'harvestPresentation'}),
            'Certified scenery frame/assets/surfaces/source differ from baseline.')
    for placement in removals:
        require(current['placements'].count(placement) == 1, 'Affected certified wall rock differs from genuine baseline.')
        current['placements'].remove(placement)
    for oid, *_ in NODES:
        require(str(oid) not in current['harvestPresentation'], 'Certified scenery already contains a new node.')
        current['harvestPresentation'][str(oid)] = proposed['harvestPresentation'][str(oid)]
    current['sourcePlanSha256'] = new_sha
    return current


def harvest_block(data, base, proposed):
    """Replace one exact interior block, preserving every prefix/suffix byte."""
    newline = b'\r\n' if b'\r\n' in data else b'\n'
    def block(source):
        rows = [f'node | {REGION} | {oid} | {x} | {y} | {res}'.encode()
                for s in source['sections'] for oid, res, x, y in s['nodes']]
        return U.SOURCES[0].banner.encode() + newline + newline.join(rows) + newline
    old, new = block(base), block(proposed)
    require(data.count(old) == 1, 'Certified underground harvest rows differ or are duplicated.')
    return data.replace(old, new, 1)


def serialise(document, original, indent=2):
    encoded = (json.dumps(document, ensure_ascii=False, indent=indent) + '\n').encode()
    return encoded.replace(b'\n', b'\r\n') if b'\r\n' in original else encoded


def stage_hash(block, stage, files, hashes, owned):
    value = {key: copy.deepcopy(value) for key, value in block.items() if key in owned}
    value['stage'] = stage
    value['overlay']['files'] = {name: hashes[name] for name in files}
    return sha(json.dumps(value, sort_keys=True).encode())


def render_manifest_invariant(document):
    value = copy.deepcopy(document)
    value.pop('harvestables'); value.pop('provenance'); value['collision'].pop('sha256')
    return value


def background_carry_forward(checkout, before, after, read, verified):
    """Carry certified images only when every manifest field the renderer could read is unchanged."""
    require(render_manifest_invariant(before) == render_manifest_invariant(after), 'Map-background render fields changed.')
    catalog_path = checkout / 'godot-client/data/maps/map-backgrounds.json'
    catalog = read_json(verified(catalog_path, BACKGROUND_CATALOG_SHA))
    require(catalog['schemaVersion'] == 1 and catalog['generator'] == 'eloria-assets/tools/render_map_backgrounds.py',
            'Unexpected map-background catalog renderer.')
    require(catalog['renderSettings'] == dict(pixelsPerMetre=4., supersample=1, minimumLongestSide=512,
            maximumLongestSide=2048, roofPolicy='declared-cutaway-and-named-cave-lids'), 'Map-background render settings changed.')
    for relative, digest in catalog['rendererInputs'].items(): verified(checkout / relative, digest)
    package = checkout / 'eloria-assets/maps/continent-v2/landfall_insides/client'
    world_key = (package / 'world.json').relative_to(checkout).as_posix()
    sources = {world_key: sha(read(package / 'world.json')), (package / 'world.glb').relative_to(checkout).as_posix(): CERTIFIED_GLB_SHA}
    for uri, digest in before['externalResources'].items():
        relative = (package / uri).resolve().relative_to(checkout.resolve()).as_posix()
        sources[relative] = digest
    row = catalog['maps'][REGION]
    require(row['sourceInputs'] == sources, 'Map-background source closure is stale or differs from certified inputs.')
    for relative, digest in sources.items(): verified(checkout / relative, digest)
    require(row['rendererPolicy'] == 'prerendered-map-background-v1' and row['sectioned'] is True and not row.get('path')
            and before['sectioned'] is True, 'Expected sectioned map-background policy.')
    def frame(bounds):
        low, high = bounds['min'], bounds['max']
        return (low, high) if len(low) == 2 else ([low[0], low[2]], [high[0], high[2]])
    require((row['worldMin'], row['worldMax']) == frame(before['asset']['bounds']), 'Map-background frame differs.')
    require(len(row['sections']) == 23 and set(row['sections']) == {s['id'] for s in before['sections']}, 'Map-background section coverage differs.')
    for section in before['sections']:
        picture = row['sections'][section['id']]
        require((picture['worldMin'], picture['worldMax']) == frame(section['bounds']), 'Map-background section frame differs.')
        require(picture['path'].startswith('res://../'), 'Unexpected map-background image path.')
        path = (checkout / 'godot-client' / picture['path'][6:]).resolve()
        require(path.is_relative_to(checkout.resolve()), 'Map-background image escapes checkout.')
        verified(path, picture['sha256'])
    proof = dict(catalogBaseSha256=BACKGROUND_CATALOG_SHA, retainedPictures=23,
                 rendererInputsSha256=sha(json.dumps(catalog['rendererInputs'], sort_keys=True).encode()),
                 renderSettings=catalog['renderSettings'], imageRowsSha256=sha(json.dumps(row['sections'], sort_keys=True).encode()),
                 contract='exact renderer inputs/image bytes retained; only non-render manifest fields change')
    return catalog_path, catalog, world_key, proof


def prepare(checkout, server, base_source, proposed_source, base_package, proposed_package, base_scenery, proposed_scenery,
            frozen_exteriors=None):
    """Return (updates, watched inputs, receipt); caller reviews before saving/applying a bundle."""
    import publish_server as P
    sys.path[:0] = [str(server), str(server / 'tools')]
    from collision_sources import read_served_package
    from eloria.collision import CollisionMap
    from eloria.harvesting import load_harvesting
    watched = {}
    def read(path):
        path = Path(path).resolve(); data = path.read_bytes()
        require(path not in watched or watched[path] == data, f'Input changed during preparation: {path}')
        watched[path] = data
        return data
    def document(path): return read_json(read(path))
    def verified(path, expected):
        data = read(path); require(sha(data) == expected, f'Stale sealed file: {path}')
        return data
    packages = checkout / 'eloria-assets/maps/continent-v2'
    target, profile = packages / REGION / 'client', server / 'config/eloria'
    record_path, manifest_path = checkout / RELATIVE / 'publication.json', profile / 'client_content_manifest.json'
    record, manifest = document(record_path), document(manifest_path)
    block = manifest['continentV2']; sealed = record['interiors'][REGION]
    old, new = document(base_source), document(proposed_source)
    source_delta(old, new)
    old_sha, new_sha = sha(read(base_source)), sha(read(proposed_source))
    require(old_sha == sealed['sourceSha256'], 'Base source is not the sealed publication source.')
    require(read(checkout / U.SOURCE) == read(base_source), 'Live source changed before amendment preparation.')
    current = read_json(verified(target / 'world.json', sealed['manifestSha256']))
    require(current['collision']['sha256'] == sealed['collisionSha256']
            and current['collision']['servedGrid']['sha256'] == sealed['servedGridSha256'], 'Certified interior binary metadata is stale.')
    before, after = document(base_package / 'world.json'), document(proposed_package / 'world.json')
    for doc, source_sha in ((current, old_sha), (before, old_sha), (after, new_sha)):
        provenance = doc['provenance']
        require(provenance['sourceSha256'] == source_sha and provenance['builder'] == '_continent_v2/build_underground.py'
                and provenance['source'] == '_continent_v2/content/underground.json',
                'Package provenance does not identify the genuine source/builder.')
        verified(checkout / RELATIVE / 'build_underground.py', provenance['builderSha256'])
        for name, digest in provenance.get('imports', {}).items(): verified(checkout / RELATIVE / Path(name).name, digest)
    expected = copy.deepcopy(before)
    additions = [dict(id=f'{SECTION}-{oid}', objectId=oid, resource=res, serverTile=[x, y],
                      position=[x+.5, 0, 720-y-.5], section=SECTION, authority='server') for oid, res, x, y in NODES]
    expected['harvestables'].extend(additions)
    expected['provenance']['sourceSha256'] = new_sha
    expected['collision']['sha256'] = after['collision']['sha256']
    require(expected == after, 'Genuine build manifests differ beyond the approved resource delta.')
    require(current['harvestables'] == before['harvestables'], 'Certified harvestables differ from the genuine baseline.')
    verified(target / 'world.glb', CERTIFIED_GLB_SHA)
    require(read(base_package / 'world.glb') == read(proposed_package / 'world.glb'), 'Resource change altered rebuilt shell geometry.')
    for package, doc in ((target, current), (base_package, before), (proposed_package, after)):
        for uri, digest in doc.get('externalResources', {}).items(): verified(package / uri, digest)
        verified(package / 'collision.bin', doc['collision']['sha256'])
        verified(package / 'served-grid.escg.gz', doc['collision']['servedGrid']['sha256'])
    old_collision, new_collision = read(base_package / 'collision.bin'), read(proposed_package / 'collision.bin')
    require(read(target / 'collision.bin') == old_collision, 'Fresh baseline collision differs from certified collision.')
    collision_delta(old_collision, new_collision)
    grid_bytes = read(target / 'served-grid.escg.gz')
    require(grid_bytes == read(base_package / 'served-grid.escg.gz') == read(proposed_package / 'served-grid.escg.gz'),
            'The served grid changed.')
    for package in (base_package, proposed_package, target): read_served_package(package / 'collision.bin', 720)
    require(read(target / 'minimap.webp') == read(base_package / 'minimap.webp'), 'Baseline minimap differs from certified minimap.')
    scenery_path = checkout / 'godot-client/data/world/underground-scenery.json'
    scenery = scenery_delta(document(base_scenery), document(proposed_scenery), old_sha, new_sha, document(scenery_path))
    scenery_bytes = serialise(scenery, read(scenery_path))
    # Validate all sealed exterior/interior binaries and the overlay; no bake or door marker is fabricated.
    require(len(record['maps']) == 17, 'Expected the sealed 17 exterior maps.')
    exterior_packages = packages if frozen_exteriors is None else Path(frozen_exteriors)
    retained_exteriors, sealed_exteriors = {}, {}
    for region, item in record['maps'].items():
        live = packages / region / 'client'; live_doc = document(live / 'world.json')
        retained_exteriors[region] = dict(manifestSha256=sha(read(live / 'world.json')),
            collisionSha256=sha(verified(live / 'collision.bin', live_doc['collision']['sha256'])),
            servedGridSha256=sha(verified(live / 'served-grid.escg.gz', live_doc['collision']['servedGrid']['sha256'])))
        package = exterior_packages / region / 'client'; doc = document(package / 'world.json')
        require(all(doc['provenance'][key] == value for key, value in item['bake'].items()), f'{region}: stale exterior bake provenance.')
        require(doc['collision']['sha256'] == item['package']['collisionSha256']
                and doc['collision']['servedGrid']['sha256'] == item['package']['servedGridSha256'], f'{region}: stale exterior binary metadata.')
        require(all(block['maps'][region][key] == value for key, value in {**item['bake'], **item['package']}.items()),
                f'{region}: exterior manifest no longer agrees with sealed publication.')
        sealed_exteriors[region] = dict(manifestSha256=sha(read(package / 'world.json')),
            collisionSha256=sha(verified(package / 'collision.bin', item['package']['collisionSha256'])),
            servedGridSha256=sha(verified(package / 'served-grid.escg.gz', item['package']['servedGridSha256'])))
    require(set(record['server']['vendored']) == set(record['maps']) | set(record['interiors']), 'Incomplete sealed vendored map set.')
    for region, digest in record['server']['vendored'].items():
        verified(server / f'tools/collision/{region}.escg.gz', digest)
        package_root = exterior_packages if region in record['maps'] else packages
        verified(package_root / region / 'client/served-grid.escg.gz', digest)
    for region, item in record['interiors'].items():
        if region != REGION: verified(packages / region / 'client/world.json', item['manifestSha256'])
    for relative, digest in record['inputs']['contentTables'].items(): verified(checkout / relative, digest)
    live_crossings = read(checkout / RELATIVE / 'crossings.json')
    sealed_crossings_path = (checkout / RELATIVE / 'crossings.json' if frozen_exteriors is None
                             else exterior_packages / 'crossings.json')
    verified(sealed_crossings_path, record['inputs']['crossingsSha256'])
    overlay = {name: verified(profile / 'continent-v2' / name, digest) for name, digest in record['server']['overlay'].items()}
    require(block['interiorMaps'][REGION] == {k: v for k, v in sealed.items() if k not in ('rows', 'walkableTiles')},
            'Interior server metadata is stale.')
    for stage, item in record['server']['stages'].items():
        require(stage_hash(block, stage, item['files'], record['server']['overlay'], P.OWNED_BLOCK_KEYS) == item['manifestBlockSha256'],
                f'{stage}: stale sealed server manifest block.')
    loaded = []
    for spec in U.SOURCES:
        path = checkout / spec.source; design = new if spec.kind == 'underground' else document(path)
        require(spec.kind == 'underground' or sha(read(path)) == record['interiors'][design['map']['id']]['sourceSha256'],
                'Another interior source changed.')
        reader = U.reader_of(spec); reader.check(design); loaded.append((spec, reader, path, design))
    # Only nodes are added. The full publisher permits nodes to reuse exterior
    # IDs on other maps; unchanged door/interactive-vs-exterior checks are inherited.
    U.check_ids(loaded, SimpleNamespace(nodes=[], interactives=[]), ValueError)
    read(profile / 'harvesting.txt')
    resources, _ = load_harvesting(profile / 'harvesting.txt', overlay=False)
    _, grid, _ = read_served_package(target / 'collision.bin', 720)
    collision = CollisionMap.from_grid(grid)
    section = next(s for s in new['sections'] if s['id'] == SECTION)
    posts = {tuple(p['tile']) for s in new['sections'] for p in U.section_npcs(S, s)}
    arrival = tuple(S.primary_arrival(new, section))
    require(collision.walkable(*arrival) and arrival not in posts, 'Galleries arrival is blocked.')
    reach = U.walk_component(collision, arrival, posts)
    codes = np.frombuffer(grid.codes, dtype=np.uint16).reshape(720, 720)
    for node in NODES: U.checked_node_row(REGION, SECTION, node, codes, reach, resources)
    harvest_path = profile / 'continent-v2/harvesting.txt'
    harvest = harvest_block(overlay['harvesting.txt'], old, new)
    entry = dict(tool=RELATIVE.joinpath(Path(__file__).name).as_posix(), region=REGION, addedNodes=NODES,
                 basePublicationSha256=sha(read(record_path)),
                 baseSourceSha256=old_sha, sourceSha256=new_sha, frozenExteriorMapsSha256=sha(json.dumps(record['maps'], sort_keys=True).encode()),
                 exteriorValidation=('live client packages match sealed server publication' if frozen_exteriors is None else
                    'explicit historical server package view matches sealed publication; newer client exterior files retained unchanged'),
                 frozenExteriorFilesSha256=sha(json.dumps(sealed_exteriors, sort_keys=True).encode()),
                 retainedClientExteriorFilesSha256=sha(json.dumps(retained_exteriors, sort_keys=True).encode()),
                 clientExteriorDrift=sorted(region for region in retained_exteriors if retained_exteriors[region] != sealed_exteriors[region]),
                 sealedCrossingsSha256=record['inputs']['crossingsSha256'], retainedClientCrossingsSha256=sha(live_crossings),
                 baseManifestSha256=sealed['manifestSha256'], proposedBuildManifestSha256=sha(read(proposed_package / 'world.json')),
                 certifiedGlbSha256=CERTIFIED_GLB_SHA, rebuiltGlbSha256=sha(read(base_package / 'world.glb')),
                 retainedResourcesSha256=sha(json.dumps(current.get('externalResources', {}), sort_keys=True).encode()),
                 geometry='retain certified shell and resource closure; genuine base/proposed shell bytes equal',
                 doorValidation='inherited unchanged doors/passages from sealed publication; no exterior bakes supplied',
                 halfCellClosures=sorted(map(list, CLOSURES)), servedGridSha256=sha(grid_bytes),
                 collisionSha256=sha(new_collision), scenerySha256=sha(scenery_bytes),
                 minimapSha256=sha(read(proposed_package / 'minimap.webp')), harvestingSha256=sha(harvest),
                 renderedAcceptance='pending')
    old_world = copy.deepcopy(current)
    current['harvestables'].extend(additions); current['collision']['sha256'] = sha(new_collision)
    current['provenance']['sourceSha256'] = new_sha
    background_path, backgrounds, world_key, proof = background_carry_forward(checkout, old_world, current, read, verified)
    entry['backgroundCarryForward'] = proof
    current['provenance'].setdefault(RECEIPTS, []).append(entry)
    world_bytes = serialise(current, read(target / 'world.json'))
    backgrounds['maps'][REGION]['sourceInputs'][world_key] = sha(world_bytes)
    catalog_bytes = read(background_path)
    old_binding = (json.dumps(world_key) + ': ' + json.dumps(sha(read(target / 'world.json')))).encode()
    new_binding = (json.dumps(world_key) + ': ' + json.dumps(sha(world_bytes))).encode()
    require(catalog_bytes.count(old_binding) == 1, 'Map-background world binding is absent or duplicated.')
    catalog_bytes = catalog_bytes.replace(old_binding, new_binding, 1)
    require(read_json(catalog_bytes) == backgrounds, 'Map-background update changed more than its world dependency hash.')
    sealed.update(sourceSha256=new_sha, manifestSha256=sha(world_bytes), collisionSha256=sha(new_collision))
    sealed['rows']['nodes'] += len(NODES)
    block['interiorMaps'][REGION] = {k: v for k, v in sealed.items() if k not in ('rows', 'walkableTiles')}
    block['undergroundRows']['nodes'] += len(NODES)
    block['overlay']['files']['harvesting.txt'] = record['server']['overlay']['harvesting.txt'] = sha(harvest)
    block.setdefault(RECEIPTS, []).append(entry); record.setdefault(RECEIPTS, []).append(entry)
    for stage, item in record['server']['stages'].items():
        item['manifestBlockSha256'] = stage_hash(block, stage, item['files'], record['server']['overlay'], P.OWNED_BLOCK_KEYS)
    updates = {checkout / U.SOURCE: read(proposed_source), target / 'world.json': world_bytes,
               target / 'collision.bin': new_collision, target / 'minimap.webp': read(proposed_package / 'minimap.webp'),
               scenery_path: scenery_bytes, harvest_path: harvest,
               background_path: catalog_bytes,
               manifest_path: serialise(manifest, read(manifest_path)), record_path: serialise(record, read(record_path), 1)}
    return {path.resolve(): data for path, data in updates.items()}, watched, entry


def save_bundle(directory, updates, watched):
    """Persist every old/new byte before any target write; publish the bundle directory last."""
    require(not directory.exists(), 'Recovery bundle already exists; review/resume it instead.')
    require(all(path.read_bytes() == data for path, data in watched.items()), 'Inputs changed after preparation.')
    stage = Path(tempfile.mkdtemp(prefix='.' + directory.name + '.', dir=directory.parent))
    try:
        entries = []
        for index, (path, data) in enumerate(updates.items()):
            old = watched[path]; old_file, new_file = f'{index}.old', f'{index}.new'
            (stage / old_file).write_bytes(old); (stage / new_file).write_bytes(data)
            entries.append(dict(path=str(path), old=sha(old), new=sha(data), oldFile=old_file, newFile=new_file))
        proof = dict(schema='eloria-interior-resource-bundle-v1', targets=entries,
                     inputs={str(path): sha(data) for path, data in watched.items() if path not in updates})
        (stage / 'bundle.json').write_bytes(serialise(proof, b''))
        for path in stage.iterdir():
            with path.open('rb') as stream: os.fsync(stream.fileno())
        os.rename(stage, directory)
    finally:
        if stage.exists(): shutil.rmtree(stage)


def apply_bundle(directory):
    """Resume only old/new states; validate the entire bundle before changing another target."""
    proof = read_json((directory / 'bundle.json').read_bytes())
    require(proof['schema'] == 'eloria-interior-resource-bundle-v1', 'Unknown recovery bundle.')
    for path, digest in proof['inputs'].items(): require(sha(Path(path).read_bytes()) == digest, f'Immutable input changed: {path}')
    for item in proof['targets']:
        for kind in ('old', 'new'):
            require(sha((directory / item[kind + 'File']).read_bytes()) == item[kind], 'Recovery bytes are damaged.')
        require(sha(Path(item['path']).read_bytes()) in (item['old'], item['new']), f'Foreign target edit: {item["path"]}')
    for item in proof['targets']:
        path = Path(item['path'])
        if sha(path.read_bytes()) == item['new']: continue
        require(sha(path.read_bytes()) == item['old'], f'Target changed during apply: {path}')
        temporary_path = None
        try:
            with tempfile.NamedTemporaryFile(dir=path.parent, prefix='.' + path.name + '.', delete=False) as stream:
                temporary_path = Path(stream.name); stream.write((directory / item['newFile']).read_bytes())
                stream.flush(); os.fsync(stream.fileno())
            os.chmod(temporary_path, path.stat().st_mode & 0o777); os.replace(temporary_path, path)
        finally:
            if temporary_path is not None: temporary_path.unlink(missing_ok=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('checkout', 'server', 'base-source', 'proposed-source', 'base-package', 'proposed-package', 'base-scenery', 'proposed-scenery'):
        parser.add_argument('--' + name, type=Path)
    parser.add_argument('--bundle', type=Path, help='new private recovery-bundle directory (parent must exist)')
    parser.add_argument('--frozen-exteriors', type=Path, help='historical continent-v2 view containing crossings.json and REGION/client/{world.json,collision.bin,served-grid.escg.gz}')
    parser.add_argument('--resume', type=Path, help='apply/resume an already prepared recovery bundle')
    parser.add_argument('--apply', action='store_true', help='apply the reviewed local bundle; default is validation only')
    args = vars(parser.parse_args()); write, bundle, resume = args.pop('apply'), args.pop('bundle'), args.pop('resume')
    frozen_exteriors = args.pop('frozen_exteriors')
    if resume:
        require(not bundle and not frozen_exteriors and not any(args.values()), '--resume takes only the existing bundle path.')
        apply_bundle(resume); return 0
    require(all(args.values()), 'Give all source/package/scenery/checkouts, or --resume BUNDLE.')
    updates, watched, entry = prepare(**args, frozen_exteriors=frozen_exteriors)
    if bundle: save_bundle(bundle, updates, watched)
    if write:
        require(bundle is not None, '--apply requires --bundle for crash recovery.'); apply_bundle(bundle)
    print(json.dumps(dict(applied=write, files=[str(path) for path in updates], receipt=entry,
                          bundleSha256=sha((bundle / 'bundle.json').read_bytes()) if bundle else None), indent=2))
    return 0


if __name__ == '__main__': raise SystemExit(main())
