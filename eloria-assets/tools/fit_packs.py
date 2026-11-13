"""Fit the two imported Meshy packs to current bodies; never generate geometry.

The portable source meshes, UVs and triangle order stay unchanged. Bag vertices
are rigid on spine_03; existing shoulder loops inherit the torso's skin blend.
All intermediate files go to a fresh ignored --out stage.
"""
from __future__ import annotations
import argparse
import json
from pathlib import Path

import numpy as np
from scipy.spatial import cKDTree

import conform_equipment as ce
import equipment_authoring as ea
from fit_quivers import digest, surface_normals, front_depth, body_samples, write_mesh

ROOT = Path(__file__).resolve().parents[2]
CLIENT = ROOT / 'godot-client'
NATIVE = CLIENT / 'assets/actors/native'
SOURCE = ROOT / 'eloria-assets/source/packs'


def fit(entry, rig):
    surface, texture = ce.read_source(SOURCE / (entry['id'] + '.glb'))
    p = surface.positions.copy()
    stature = rig.fit_scale
    shoulder = float(rig.origin('upperarm_l')[1])
    pelvis = float(rig.origin('pelvis')[1])
    scale = float(entry['scale']) * stature
    trunk, normals = body_samples(rig)
    region = trunk[(trunk[:, 1] > pelvis) & (trunk[:, 1] < shoulder)
                   & (abs(trunk[:, 0]) < .18 * stature)]
    back = float(np.quantile(region[:, 2], .02)) - .035 * stature
    center_y = shoulder + entry['topAboveShoulder'] * stature - entry['sourceTop'] * scale
    fixed = p * [-scale, scale, -scale] + [0., center_y, back]
    # Measured source-space regions contain only the original shoulder loops.
    # Blend at their attached roots; no disconnected strap or synthetic band.
    blend = np.clip((entry['strapRearZ'] - p[:, 2]) / .065, 0., 1.)
    if entry['id'] == 'rl-small-pack':
        blend = np.maximum(blend, np.clip((p[:, 1] - .28) / .07, 0., 1.)
                           * np.clip((.13 - p[:, 2]) / .07, 0., 1.))
    else:
        blend *= np.clip((.32 - p[:, 1]) / .045, 0., 1.)
    strap = fixed.copy()
    strap[:, 1] = np.interp(p[:, 1], entry['strapY'],
                            [pelvis + .09 * stature, shoulder + .025 * stature])
    strap[:, 2] = back - p[:, 2] * entry['strapDepthScale'] * stature
    fitted = fixed * (1. - blend[:, None]) + strap * blend[:, None]
    # Match the actual front surface while retaining the imported band relief.
    chest = (fitted[:, 2] > .025 * stature) & (blend > 0.)
    if chest.any():
        front = front_depth(rig, fitted[chest])
        fitted[chest, 2] += np.where(np.isfinite(front),
            np.maximum(0., front + .012 * stature - fitted[chest, 2]), 0.)
    _, nearest = cKDTree(trunk).query(fitted)
    gap = np.einsum('ij,ij->i', fitted - trunk[nearest], normals[nearest])
    fitted += normals[nearest] * (np.maximum(0., .009 * stature - gap) * blend)[:, None]
    candidates = ['pelvis', 'spine_01', 'spine_02', 'spine_03', 'clavicle_l', 'clavicle_r']
    joints, weights = rig.weights_for(fitted, candidates)
    combined = np.zeros((len(p), len(rig.joint_names)))
    rows = np.arange(len(p))
    for column in range(joints.shape[1]):
        combined[rows, joints[:, column]] += weights[:, column] * blend
    combined[:, rig.joint_names.index('spine_03')] += 1. - blend
    joints = np.argsort(combined, axis=1)[:, -4:]
    weights = np.take_along_axis(combined, joints, axis=1)
    weights /= weights.sum(axis=1, keepdims=True)
    surface.positions = fitted
    surface.normals = surface_normals(fitted, surface.indices.reshape(-1, 3))
    if not np.isfinite(fitted).all() or not np.allclose(weights.sum(1), 1.):
        raise ValueError('Invalid fitted geometry or skin')
    return surface, texture, joints, weights, {
        'bounds': [fitted.min(0).tolist(), fitted.max(0).tolist()],
        'rigidVertices': int((blend == 0).sum()), 'strapVertices': int((blend > 0).sum()),
        'triangles': len(surface.indices)//3, 'backPlane': back,
        'bodySha256': digest(NATIVE/'races'/f'{rig.source_slug}.glb'),
        'sourceSha256': digest(SOURCE/(entry['id']+'.glb')),
        'uvAndIndicesPreserved': True, 'rigidBone': 'spine_03'}


def install(out, assets, records, registry):
    import pack_canonical_equipment as pack
    from build_native_nymara_glbs import validate_glb
    stage = out / 'packed'
    stage.mkdir()
    registry.setdefault('fitProfiles', {})['packs'] = {'canonicalHeadRestY': 0., 'bodyGirth': {}}
    catalog_path = CLIENT/'data/actors/native_asset_catalog.json'
    catalog = json.loads(catalog_path.read_bytes())
    for entry in assets:
        variants = {}
        for record in records:
            if record['id'] != entry['id']: continue
            race = record['race']
            target = pack.PREFIX/'variants'/race/(entry['id']+'.glb')
            textures = pack.pack_glb(Path(record['path']), target, stage)
            for relative in [*textures, target]:
                dest = ROOT/relative
                dest.parent.mkdir(parents=True, exist_ok=True)
                incoming = (stage/relative).read_bytes()
                if dest.exists() and relative != target and dest.read_bytes() != incoming:
                    raise ValueError(f'Shared texture differs: {relative}')
                dest.write_bytes(incoming)
            group = registry['fitGroups'][race][0]
            variants[group] = {'scene': 'res://'+target.relative_to('godot-client').as_posix(),
                               'authoredFor': race, 'fitProfile': 'packs'}
            catalog['validation']['results'][target.as_posix()] = validate_glb(ROOT/target)
        if len(variants) != len(registry['bodyTemplates']):
            raise ValueError('All body fits required')
        registry['models'][f'2:{entry["visual"]}'] = {
            **variants['canonical_human_male'], 'name': entry['name'],
            'attach': 'skinned', 'kind': 'pack', 'skinRegion': 'pack', 'variants': variants}
    (CLIENT/'data/actors/equipment.json').write_bytes((json.dumps(registry, indent=2, ensure_ascii=False)+'\n').encode('utf-8'))
    catalog['validation']['files'] = sum(1 for _ in NATIVE.rglob('*.glb'))
    catalog_path.write_bytes((json.dumps(catalog, indent=2, ensure_ascii=False)+'\n').encode('utf-8'))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out', type=Path, required=True)
    parser.add_argument('--races', nargs='+')
    parser.add_argument('--install', action='store_true')
    args = parser.parse_args()
    args.out.mkdir(parents=True, exist_ok=False)
    assets = json.loads((SOURCE/'catalog.json').read_bytes())['assets']
    registry = json.loads((CLIENT/'data/actors/equipment.json').read_bytes())
    races = args.races or sorted(registry['bodyTemplates'])
    records = []
    for race in races:
        rig = ea.load_rig(NATIVE/'races'/f'{race}.glb')
        for entry in assets:
            surface, texture, joints, weights, report = fit(entry, rig)
            dest = args.out/'variants'/race/(entry['id']+'.glb')
            write_mesh(dest, surface, texture, rig, joints, weights, name=entry['name'])
            records.append(dict(report, race=race, id=entry['id'], path=str(dest.resolve()), sha256=digest(dest)))
        print('Fitted packs to '+race, flush=True)
    (args.out/'fits.json').write_text(json.dumps(records, indent=2)+'\n')
    if args.install:
        if set(races) != set(registry['bodyTemplates']): raise ValueError('All bodies required')
        install(args.out, assets, records, registry)


if __name__ == '__main__':
    main()
