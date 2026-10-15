"""Explicit terrain-source migration, separate from destructive bootstrap import.

prepare only writes the external transaction directory; apply is recoverable and
hash-guarded. This never selects a runtime plan or changes server storage/frames.
"""
import argparse
import json
from pathlib import Path
import re
import sys

import numpy as np

import terrain_source_migration as M

FIELD_PATH = 'godot-client/world_authoring/terrain/shared-field-v1/manifest.json'


def prepare(root, transaction, contract_path, seed_root):
    continent = root/'eloria-assets/maps/nymara-regions/_continent'
    sys.path.insert(0, str(continent))
    import ownership_contract
    contract = ownership_contract.load_contract(M.checked_path(root, contract_path))
    manifest, field, arrays = M.load_shared_field(seed_root, FIELD_PATH)
    ids = manifest['provenance']['ownerRegionOrder']
    xx, zz = np.meshgrid((np.arange(field.width-1)+field.x)*2+1,
                         (np.arange(field.height-1)+field.z)*2+1)
    owners = contract.sample(xx, zz, ids)
    if M.sha256(owners.astype('<i4').tobytes()) != manifest['provenance']['newOwnerI32LESha256']:
        raise ValueError('migration ownership differs from reviewed field manifest')
    replacements = {FIELD_PATH: M.checked_path(seed_root, FIELD_PATH).read_bytes()}
    for key in ('heights', 'colors'):
        replacements[manifest[key]['path']] = arrays[key]
    preconditions = {}
    # Bind the complete saved regional source tree, including unchanged Sunmane.
    for file in sorted((root/'godot-client/world_authoring/regions').rglob('*')):
        if file.is_file() and file.suffix in ('.tscn', '.tres', '.json', '.f32le', '.rgba8'):
            preconditions[file.relative_to(root).as_posix()] = M.sha256(file.read_bytes())
    preconditions[contract_path] = M.sha256(M.checked_path(root, contract_path).read_bytes())
    records = []
    for index, rid in enumerate(ids):
        spec_path = f'godot-client/world_authoring/regions/{rid}/region-authoring-spec.json'
        spec = json.loads(M.checked_path(root, spec_path).read_bytes())
        terrain = spec['terrain']; old_origin = terrain['origin']; old_size = terrain['vertices']
        if terrain['cellMetres'] != manifest['lattice']['spacing'] or spec['continentTranslation'][1] != 0:
            raise ValueError(f'{rid}: unsupported source lattice or vertical frame')
        translation = np.array(spec['continentTranslation'])[[0, 2]]
        old = M.global_window(old_origin, translation, old_size, terrain['cellMetres'])
        mask = M.required_vertices(owners, index)
        new = old.union(M.required_window(mask, field))
        M.validate_required_coverage(mask, field, new)
        record = {'region': rid, 'oldGlobalVertexMin': [old.x, old.z], 'newGlobalVertexMin': [new.x, new.z],
                  'oldVertices': old_size, 'newVertices': [new.width, new.height],
                  'addedVertices': new.width*new.height-old.width*old.height,
                  'requiredVertices': int(mask.sum())}
        records.append(record)
        if old == new:
            prior = terrain.get('migration')
            if prior and (prior.get('sharedFieldPath') != FIELD_PATH or
                          prior.get('sharedFieldSha256') != M.sha256(replacements[FIELD_PATH]) or
                          prior.get('globalVertexMin') != [old.x, old.z]):
                raise ValueError(f'{rid}: existing migration is bound to a different field/window')
            record['status'] = 'unchanged'
            continue
        scene_path = spec['paths']['scene']; scene = M.checked_path(root, scene_path).read_bytes()
        snapshot_path = spec['paths']['snapshot']
        snapshot_file = M.checked_path(root, snapshot_path)
        snapshot = json.loads(snapshot_file.read_bytes())
        if snapshot['sources']['scene']['sha256'] != M.sha256(scene):
            raise ValueError(f'{rid}: saved snapshot scene is stale')
        preconditions[snapshot_path] = M.sha256(snapshot_file.read_bytes())
        for entry in snapshot['sources'].get('dependencies', []):
            path = M.checked_path(root, entry['path'])
            if path.suffix in ('.tscn', '.tres', '.f32le', '.rgba8'):
                if M.sha256(path.read_bytes()) != entry['sha256']:
                    raise ValueError(f'{rid}: saved snapshot terrain dependency is stale: {entry["path"]}')
        modifiers = (any(p.get('properties', {}).get('terrainConform', True) for p in snapshot['paths']) or
                     any(p.get('enabled', True) for p in snapshot['terrain'].get('patches', [])) or
                     bool(re.search(rb'^sculpt_layer = ', scene, re.M)))
        if modifiers:
            raise ValueError(f'{rid}: growing scene has active modifiers')
        resolved_entry = snapshot['terrain']['resolvedHeights']
        resolved = (snapshot_file.parent/resolved_entry['path']).read_bytes()
        base_path = spec['inputs']['baseHeights']; color_path = spec['inputs']['baseColors']
        base = M.checked_path(root, base_path).read_bytes(); colors = M.checked_path(root, color_path).read_bytes()
        if M.sha256(resolved) != resolved_entry['sha256'] or base != resolved:
            raise ValueError(f'{rid}: unresolved base differs from saved resolution')
        new_origin = [float(new.x*2-translation[0]), float(new.z*2-translation[1])]
        for path, payload, shared in [(base_path, base, arrays['heights']), (color_path, colors, arrays['colors'])]:
            output = M.remap_grid_by_global_id(payload, old, new, shared, field)
            if M.preserved_old_bytes(output, old, new) != payload:
                raise ValueError('lossless preservation invariant failed')
            replacements[path] = output
        replacements[scene_path] = M.replace_terrain_grid(scene, old_origin, old_size, new_origin, [new.width, new.height])
        terrain['origin'] = new_origin; terrain['vertices'] = [new.width, new.height]
        terrain['migration'] = {'revision': 'global-lattice-envelope-v1', 'sharedFieldPath': FIELD_PATH,
                                'sharedFieldSha256': M.sha256(replacements[FIELD_PATH]),
                                'globalVertexMin': [new.x, new.z], 'previousGridSha256': M.sha256(base)}
        replacements[spec_path] = (json.dumps(spec, indent=2)+'\n').encode()
        record.update(status='staged', scene=scene_path, spec=spec_path, base=base_path, colors=color_path,
                      origin=new_origin, oldOrigin=old_origin, preservedBaseSha256=M.sha256(base),
                      preservedColorSha256=M.sha256(colors), newBaseSha256=M.sha256(replacements[base_path]),
                      newColorSha256=M.sha256(replacements[color_path]), activeModifiers=0)
    journal = M.stage_transaction(root, transaction, replacements, preconditions)
    report = {'schema': 'eloria-terrain-migration-plan-v1', 'sharedField': FIELD_PATH,
              'contract': contract_path, 'contractSha256': preconditions[contract_path], 'regions': records,
              'allowedFileCount': len(journal['entries']), 'preconditionCount': len(preconditions)}
    M._write_json(transaction/'plan.json', report)
    return report


def verify(root, transaction):
    journal = json.loads((transaction/'journal.json').read_bytes())
    plan = json.loads((transaction/'plan.json').read_bytes())
    entries = {item['path']: item for item in journal['entries']}
    for path, expected in journal['preconditions'].items():
        expected = entries[path]['after'] if path in entries else expected
        if M.sha256(M.checked_path(root, path).read_bytes()) != expected:
            raise ValueError(f'changed source invariant: {path}')
    for row in plan['regions']:
        if row['status'] == 'unchanged':
            continue
        old = M.Window(*row['oldGlobalVertexMin'], *row['oldVertices'])
        new = M.Window(*row['newGlobalVertexMin'], *row['newVertices'])
        for key, digest_key in [('base', 'preservedBaseSha256'), ('colors', 'preservedColorSha256')]:
            old_bytes = M.preserved_old_bytes(M.checked_path(root, row[key]).read_bytes(), old, new)
            if M.sha256(old_bytes) != row[digest_key]:
                raise ValueError(f'{row["region"]}: old {key} changed')
    manifest, _, _ = M.load_shared_field(root, FIELD_PATH)
    return {'verifiedSourcePreconditions': len(journal['preconditions']),
            'migratedRegions': sum(row['status'] == 'staged' for row in plan['regions']),
            'addedVertices': sum(row['addedVertices'] for row in plan['regions']),
            'preservedOldGridBytes': True, 'sharedFieldRevision': manifest['revision']}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('operation', choices=('prepare', 'apply', 'verify', 'rollback'))
    parser.add_argument('--checkout', type=Path, default=Path(__file__).resolve().parents[2])
    parser.add_argument('--transaction', required=True, type=Path)
    parser.add_argument('--contract', help='checkout-relative explicitly approved ownership source; does not activate it')
    parser.add_argument('--seed-checkout', type=Path, help='staging root containing the portable shared-field package')
    args = parser.parse_args(); root = args.checkout.resolve(); tx = args.transaction.resolve()
    if args.operation == 'prepare':
        if not args.contract or not args.seed_checkout:
            parser.error('prepare requires --contract and --seed-checkout')
        result = prepare(root, tx, args.contract, args.seed_checkout.resolve())
        result = {k: v for k, v in result.items() if k != 'regions'}
    elif args.operation == 'apply':
        result = {'writes': M.apply_transaction(root, tx)}
    elif args.operation == 'rollback':
        M.rollback_transaction(root, tx); result = {'status': 'rolled-back'}
    else:
        result = verify(root, tx)
    print(json.dumps(result, indent=2))


if __name__ == '__main__':
    main()
