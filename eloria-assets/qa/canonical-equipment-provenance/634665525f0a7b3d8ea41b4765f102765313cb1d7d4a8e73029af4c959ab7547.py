"""Build original-art equipment candidates in scratch, with measured body metadata.

No item definitions are written. Candidate scenes and registry are consumed by
canonical_equipment_preview.gd through the real client equipment path.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from concurrent.futures import ProcessPoolExecutor, as_completed
from functools import lru_cache
from pathlib import Path

# Each worker owns a mesh; nested BLAS thread pools oversubscribe a batch.
os.environ.setdefault('OPENBLAS_NUM_THREADS', '1')
os.environ.setdefault('OMP_NUM_THREADS', '1')
import numpy as np

import conform_equipment as ce
import equipment_authoring as ea
import import_generated_equipment as batch

ROOT = Path(__file__).resolve().parents[2]
SCRATCH = ROOT / 'equipment-fit-build'
PILOT = {'militia_helmet_01', 'militia_torso_armor_01',
         'militia_leg_armor_01', 'militia_greaves_01'}


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def write_json(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, allow_nan=False) + '\n')


def measure():
    records = {}
    for path in sorted(ce.RACES.glob('*.glb')):
        rig = ea.load_rig(path, ea.BODY_SURFACES)
        feet = {}
        for side in ('l', 'r'):
            p = rig.positions[ea._foot_region(rig, side)]
            feet[side] = {'sole': ea.weighted_sole(rig, side),
                          'min': p.min(axis=0).tolist(), 'max': p.max(axis=0).tolist()}
        records[path.stem] = {'sha256': digest(path), 'samples': len(rig.positions),
            'faces': len(rig.faces), 'headRestY': float(rig.origin('Head')[1]),
            'pelvisRestY': float(rig.origin('pelvis')[1]),
            'bodyGirth': ea.body_girth(rig), 'footAnchor': ea.foot_anchor(rig),
            'feet': feet, 'rest': {n: rig.rest[n].tolist() for n in rig.joint_names}}
        print(path.stem, len(rig.positions), len(rig.faces),
              'soles mm', [round(feet[s]['sole'] * 1000, 2) for s in ('l', 'r')], flush=True)
    write_json(SCRATCH / 'reports/body-measurements.json', records)
    return records


@lru_cache(maxsize=16)
def cached_rig(race):
    return ea.load_rig(ce.RACES / f'{race}.glb', ea.BODY_SURFACES)


def tool_hashes():
    names = ['conform_equipment.py','equipment_authoring.py','torso_remap.py',
             'limb_head_remap.py','equipment_seams.py','equipment_seam_texture.py',
             'equipment_skinning.py','headwear_envelope.py','refit_canonical_equipment.py']
    return {n:digest(Path(__file__).with_name(n)) for n in names}


def prepare_registry(registry, metadata):
    # The client registry is an immutable input during scratch builds. Preserve
    # the legacy unit system before replacing the current measurements.
    old = json.loads((ce.CLIENT/'data/actors/equipment.json').read_text())
    legacy = old.get('fitProfiles',{}).get('legacy',
        {key:old[key] for key in ('canonicalHeadRestY','bodyGirth','footAnchor')})
    registry.setdefault('fitProfiles',{})['legacy'] = legacy
    registry['canonicalHeadRestY'] = ea.CANONICAL_HEAD_REST_Y
    registry['bodyGirth'] = {s:m['bodyGirth'] for s,m in metadata.items()}
    registry['footAnchor'] = {s:m['footAnchor'] for s,m in metadata.items()}
    registry['soleDrop'] = {s:{bone:round(-anchor[1],5) for bone,anchor in m['footAnchor'].items() if anchor[1]<-.0001} for s,m in metadata.items()}
    for model in registry['models'].values():
        model.setdefault('fitProfile','legacy')
        for group,variant in model.get('variants',{}).items():
            if group.startswith('canonical_'):variant['fitProfile']='canonical'
    return registry


def build_one(piece, race, tag, body_hash, code_hashes, resume):
    rig = cached_rig(race)
    body = ce.RACES/f'{race}.glb'
    dest = SCRATCH/'out'/tag/race/f'{piece.slug}.glb'
    record = dest.with_suffix('.fit.json')
    source = piece.source.with_name(piece.source.name+'.orig')
    if source.name.startswith('Eight_legendary_fantasy_sabatons__'):
        source = source.with_name(source.name.replace('Eight_legendary_fantasy_sabatons__',
                                                     'Eight_legendary_fantasy_leg_armor_designs__'))
    if not source.exists():raise ValueError(f'Original source missing: {source}')
    before = digest(source)
    expected = {'source_sha256':before,'body_sha256':body_hash,'tool_sha256':code_hashes}
    if digest(body)!=body_hash or tool_hashes()!=code_hashes:
        raise ValueError('Body or fitter changed before candidate build')
    if dest.exists():
        if resume and record.exists():
            report=json.loads(record.read_text())
            if all(report.get(k)==v for k,v in expected.items()) and digest(dest)==report['asset_sha256']:
                return report
        raise FileExistsError(f'Use a new tag; candidate is not an unchanged resumable build: {dest}')
    report=ce.build(piece.source,dest,rig,piece.kind,piece.name)
    if digest(source)!=before or digest(body)!=body_hash or tool_hashes()!=code_hashes:
        raise ValueError('Source, body or fitter changed during candidate build')
    report.update(expected, race=race,slug=piece.slug,key=f'{piece.part}:{piece.visual}',
                  asset_sha256=digest(dest))
    variant={'scene':dest.as_posix(),'authoredFor':race,'fitProfile':'canonical'}
    if piece.part==3:
        variant['socket']={'bone':'Head','offset':(ce.socket_origin(rig,3)-rig.origin('Head')).tolist(),
                           'rotationDegrees':[0,0,0]}
    report['variant']=variant
    write_json(record,report)
    return report


def build(slugs, races, tag, inherit=None, jobs=1, resume=False):
    if Path(tag).name!=tag or tag in ('.','..'):raise ValueError('Tag must be a directory name')
    registry_path = SCRATCH/f'out/{inherit}/equipment.json' if inherit else ce.CLIENT/'data/actors/equipment.json'
    registry = json.loads(registry_path.read_text())
    metadata = json.loads((SCRATCH/'reports/body-measurements.json').read_text())
    registry=prepare_registry(registry,metadata)
    if races==['all']:races=sorted(metadata)
    roster=[p for p in batch.roster() if slugs=={'all'} or p.slug in slugs]
    if not roster:raise ValueError('No pieces selected')
    codes=tool_hashes();reports=[]
    for race in races:
        if race not in metadata:raise ValueError(f'Unmeasured body {race}')
        if not np.isclose(metadata[race]['headRestY'],ea.CANONICAL_HEAD_REST_Y,atol=1e-5):
            raise ValueError('Expected approved canonical Rest_Pose')
        registry['fitGroups'][race]=['canonical_'+race]
    work=[(p,race,tag,metadata[race]['sha256'],codes,resume) for race in races for p in roster]
    def accept(report):
        reports.append(report)
        registry['models'][report['key']].setdefault('variants',{})['canonical_'+report['race']]=report['variant']
        print(f"{len(reports)}/{len(work)} {report['race']} {report['slug']}",flush=True)
    if jobs==1:
        for args in work:accept(build_one(*args))
    else:
        with ProcessPoolExecutor(max_workers=jobs) as pool:
            futures=[pool.submit(build_one,*args) for args in work]
            for future in as_completed(futures):accept(future.result())
    reports.sort(key=lambda r:(r['race'],r['slug']))
    write_json(SCRATCH/f'reports/{tag}-fit.json',reports)
    write_json(SCRATCH/f'out/{tag}/equipment.json',registry)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command', choices=['measure', 'build'])
    parser.add_argument('--races', default='luminous_male,luminous_female')
    parser.add_argument('--pieces', default=','.join(sorted(PILOT)))
    parser.add_argument('--tag', default='pilot')
    parser.add_argument('--jobs', type=int, default=1)
    parser.add_argument('--resume', action='store_true')
    parser.add_argument('--inherit', help='Validated scratch registry to extend with a new candidate iteration')
    args = parser.parse_args()
    if args.command == 'measure':
        measure()
    else:
        build(set(args.pieces.split(',')), args.races.split(','), args.tag, args.inherit, args.jobs, args.resume)
