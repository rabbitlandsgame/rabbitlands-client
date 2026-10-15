"""Repair shared torso linings and rebuild source pieces with cuff defects.

Build a candidate registry first. Installation checks the original file hashes
and writes only the selected torso GLBs and their new content-addressed images.
Existing artwork, UVs, textures, skeletons and item definitions are retained.
"""
from __future__ import annotations

import argparse
import copy
import hashlib
import json
import os
from concurrent.futures import ProcessPoolExecutor, as_completed
from functools import lru_cache
from pathlib import Path

os.environ.setdefault('OPENBLAS_NUM_THREADS', '1')
os.environ.setdefault('OMP_NUM_THREADS', '1')
import numpy as np

import conform_equipment as ce
import equipment_authoring as ea
import import_generated_equipment as batch
import pack_canonical_equipment as pack
import torso_remap as remap
from equipment_skinning import smoothstep

ROOT = Path(__file__).resolve().parents[2]
SOURCE_REBUILDS = {'militia_torso_armor_02', 'leather_ranger_torso_02', 'eloria_arcane_armor_06'}
CLOTH_SLEEVE_REPAIRS = {f'eloria_frontier_shirt_{n:02d}' for n in range(1, 8)}


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


@lru_cache(maxsize=2)
def rig_for(race):
    registry = json.loads((ce.CLIENT / 'data/actors/equipment.json').read_text())
    body = registry.get('authoringRigs', {}).get(race, race)
    return ea.load_rig(ce.RACES / (body + '.glb'), ce.BODY_MESH)


def update_normals(document, data, primitive):
    attrs = primitive['attributes']
    p = ea.accessor_array(document, data, attrs['POSITION'])
    faces = ea.accessor_array(document, data, primitive['indices']).reshape(-1, 3)
    normal = np.zeros_like(p)
    cross = np.cross(p[faces[:, 1]] - p[faces[:, 0]], p[faces[:, 2]] - p[faces[:, 0]])
    for corner in range(3):
        np.add.at(normal, faces[:, corner], cross)
    normal /= np.maximum(np.linalg.norm(normal, axis=1, keepdims=True), 1e-10)
    ea.accessor_array(document, data, attrs['NORMAL'])[:] = normal
    document['accessors'][attrs['POSITION']]['min'] = p.min(axis=0).tolist()
    document['accessors'][attrs['POSITION']]['max'] = p.max(axis=0).tolist()


def repair_cloth_sleeves(document, binary, rig):
    """Center already retargeted loose sleeves while retaining their seams.

    Their source puffed shoulders are part of a single coarse cloth sheet.
    Preserve that existing anatomical split instead of cutting it again.
    UVs, triangles, material assignments and the skeleton remain identical.
    """
    result, data = copy.deepcopy(document), bytearray(binary)
    moved, maximum = 0, 0.
    for mesh in result['meshes']:
        if mesh.get('name') == 'GeneratedArmorBacking':
            continue
        for primitive in mesh['primitives']:
            attrs = primitive['attributes']
            p = ea.accessor_array(result, data, attrs['POSITION'])
            before = p.copy()
            j = ea.accessor_array(result, data, attrs['JOINTS_0'])
            w = ea.accessor_array(result, data, attrs['WEIGHTS_0']).astype(float)
            w /= w.sum(axis=1, keepdims=True)
            for side in ('l', 'r'):
                sign = 1. if side == 'l' else -1.
                bones = [rig.joint_names.index(b + '_' + side) for b in ('upperarm', 'lowerarm')]
                share = (w * np.isin(j, bones)).sum(axis=1)
                shoulder = (p[:, 0] * sign > .185 * rig.fit_scale) & (p[:, 1] > 1.30 * rig.fit_scale)
                remap.settle_cloth_sleeve(p, (share > .5) | shoulder, rig, side, (-.05, .10))
                root, wrist = rig.origin('upperarm_' + side), rig.origin('hand_' + side)
                axis = wrist - root
                travel = (p - root) @ axis / (axis @ axis)
                cap = (share > .5) & (travel < .12)
                center = root + travel[cap, None] * axis
                radial = p[cap] - center
                radius = np.linalg.norm(radial, axis=1)
                factor = np.minimum(1., .075 * rig.fit_scale / np.maximum(radius, 1e-8))
                p[cap] = center + radial * factor[:, None]
            # Medial cap folds belong to the clavicle. An upper-arm bind on
            # points behind the arm root swings them outward and upward as
            # the arm drops, producing pointed fins above the shoulder.
            dense = np.zeros((len(p), len(rig.joint_names)))
            for slot in range(4):
                dense[np.arange(len(p)), j[:, slot]] += w[:, slot]
            for side in ('l', 'r'):
                root, wrist = rig.origin('upperarm_' + side), rig.origin('hand_' + side)
                axis = wrist - root
                travel = (p - root) @ axis / (axis @ axis)
                upper, lower = [rig.joint_names.index(b + '_' + side) for b in ('upperarm', 'lowerarm')]
                share = dense[:, upper] + dense[:, lower]
                arm = smoothstep(travel, -.02, .10)
                elbow = smoothstep(travel, .43, .59)
                dense[:, upper] = share * arm * (1 - elbow)
                dense[:, lower] = share * arm * elbow
                dense[:, rig.joint_names.index('clavicle_' + side)] += share * (1 - arm)
            fitted_j = np.argsort(-dense, axis=1)[:, :4]
            fitted_w = np.take_along_axis(dense, fitted_j, axis=1)
            fitted_w /= fitted_w.sum(axis=1, keepdims=True)
            ea.accessor_array(result, data, attrs['JOINTS_0'])[:] = fitted_j
            target_w = ea.accessor_array(result, data, attrs['WEIGHTS_0'])
            target_w[:] = (np.rint(fitted_w * np.iinfo(target_w.dtype).max)
                           if np.issubdtype(target_w.dtype, np.integer) else fitted_w)
            motion = np.linalg.norm(p - before, axis=1)
            moved += int(np.count_nonzero(motion > 1e-6))
            maximum = max(maximum, float(motion.max()))
            update_normals(result, data, primitive)
    return result, data, {'sleeveVerticesMoved': moved, 'maximumSleeveMove': maximum,
                          'artworkTopologyPreserved': True}


def repair_lining(document, binary, rig):
    """Restore shoulder ease and use the same weights around sleeve rings."""
    result = copy.deepcopy(document)
    data = bytearray(binary)
    moved = 0
    repaired = 0
    for mesh in result['meshes']:
        if mesh.get('name') != 'GeneratedArmorBacking':
            continue
        for primitive in mesh['primitives']:
            attrs = primitive['attributes']
            specs = [result['accessors'][attrs[k]] for k in ('POSITION', 'JOINTS_0', 'WEIGHTS_0')]
            if any(result['bufferViews'][s['bufferView']].get('byteStride') for s in specs):
                raise ValueError('Expected non-interleaved fitted backing')
            p = ea.accessor_array(result, data, attrs['POSITION'])
            faces = ea.accessor_array(result, data, primitive['indices']).reshape(-1, 3)
            canonical, edges, count = ce._weld(p, faces)
            labels = ce._components(edges, count)
            # Newer packed assets also contain small closed seam patches.
            # Those inherit the artwork's shape and skinning. Only the large
            # continuous body lining needs the anatomical sleeve field.
            core = labels[canonical] == np.argmax(np.bincount(labels))
            x, y = np.abs(p[:, 0]) / rig.fit_scale, p[:, 1] / rig.fit_scale
            rise = .018 * rig.fit_scale * smoothstep(x, .15, .23)
            rise *= 1 - smoothstep(x, .35, .45)
            rise *= smoothstep(y, 1.445, 1.482)
            rise *= core
            p[:, 1] += rise
            moved += int(np.count_nonzero(rise > 1e-6))
            unique, inverse = np.unique(np.round(p[core], 6), axis=0, return_inverse=True)
            j, w = remap.lining_weights(unique, rig)
            ea.accessor_array(result, data, attrs['JOINTS_0'])[core] = j[inverse]
            target = ea.accessor_array(result, data, attrs['WEIGHTS_0'])
            if np.issubdtype(target.dtype, np.integer):
                values = np.rint(w[inverse] * np.iinfo(target.dtype).max).astype(target.dtype)
                target[core] = values
            else:
                target[core] = w[inverse]
            old_normals = ea.accessor_array(result, data, attrs['NORMAL']).copy()
            update_normals(result, data, primitive)
            ea.accessor_array(result, data, attrs['NORMAL'])[~core] = old_normals[~core]
            repaired += 1
    if not repaired:
        raise ValueError('No fitted torso backing found')
    # Every artwork primitive remains byte-identical, including its skinning.
    for mesh in document['meshes']:
        if mesh.get('name') == 'GeneratedArmorBacking':
            continue
        for primitive in mesh['primitives']:
            for accessor in [*primitive['attributes'].values(), primitive['indices']]:
                if not np.array_equal(ea.accessor_array(document, binary, accessor),
                                      ea.accessor_array(result, data, accessor)):
                    raise ValueError('Lining repair changed artwork')
    return result, data, {'shoulderVerticesRaised': moved, 'artworkPreserved': True}


def build_one(piece, race, target, output, reviewed):
    source = ROOT / target
    before = sha(source)
    rig = rig_for(race)
    candidate = output / 'raw' / race / (piece.slug + '.glb')
    if piece.slug in SOURCE_REBUILDS:
        previous = reviewed / (race + '-' + piece.slug + '.glb') if reviewed else None
        if previous and previous.exists():
            candidate.parent.mkdir(parents=True, exist_ok=True)
            candidate.write_bytes(previous.read_bytes())
            report = json.loads(previous.with_suffix('.json').read_text())
        else:
            report = ce.build(piece.source, candidate, rig, piece.kind, piece.name)
    else:
        document, binary = ea.read_glb(source)
        cloth_report = {}
        if piece.slug in CLOTH_SLEEVE_REPAIRS:
            document, binary, cloth_report = repair_cloth_sleeves(document, binary, rig)
        document, binary, report = repair_lining(document, binary, rig)
        if cloth_report:
            report.update(cloth_report)
            report['artworkPreserved'] = False
        # Resolve old external textures while the candidate is in scratch.
        for image in document.get('images', []):
            if 'uri' in image:
                image['uri'] = (source.parent / image['uri']).resolve().as_posix()
        glb = ea.EquipmentGLB(generator='Eloria torso lining repair')
        glb.doc, glb.binary = document, binary
        glb.write(candidate)
    pack.validate(candidate)
    textures = pack.pack_glb(candidate, Path(target), output / 'packed')
    packed = output / 'packed' / target
    if sha(source) != before:
        raise ValueError('Installed torso changed during candidate build')
    return {'path': target, 'expectedSHA256': before, 'candidateSHA256': sha(packed),
            'race': race, 'slug': piece.slug, 'report': report,
            'textures': [p.as_posix() for p in textures]}


def build(output, reviewed=None, jobs=4):
    if output.exists():
        raise FileExistsError('Use a new candidate directory')
    output.mkdir(parents=True)
    registry = json.loads((ce.CLIENT / 'data/actors/equipment.json').read_text())
    work = []
    for piece in batch.roster():
        if piece.part != 5:
            continue
        model = registry['models'][f'5:{piece.visual}']
        seen = set()
        for variant in [model, *model.get('variants', {}).values()]:
            race = variant.get('authoredFor', model['authoredFor'])
            target = 'godot-client/' + variant['scene'].removeprefix('res://')
            if target not in seen:
                work.append((piece, race, target, output, reviewed))
                seen.add(target)
            variant['scene'] = (output / 'packed' / target).as_posix()
    records = []
    with ProcessPoolExecutor(max_workers=jobs) as pool:
        futures = [pool.submit(build_one, *args) for args in work]
        for future in as_completed(futures):
            records.append(future.result())
            if len(records) % 8 == 0:
                print(f'Torso fits: {len(records)}/{len(work)}', flush=True)
    (output / 'equipment.json').write_text(json.dumps(registry, indent=2) + '\n')
    (output / 'manifest.json').write_text(json.dumps(records, indent=2) + '\n')


def install(output):
    records = json.loads((output / 'manifest.json').read_text())
    for record in records:
        target = (ROOT / record['path']).resolve()
        if not target.is_relative_to(ROOT) or sha(target) != record['expectedSHA256']:
            raise ValueError('Installed torso differs from candidate input')
        if sha(output / 'packed' / record['path']) != record['candidateSHA256']:
            raise ValueError('Candidate changed')
    images = {image for record in records for image in record['textures']}
    for image in images:
        source, target = output / 'packed' / image, ROOT / image
        if target.exists() and sha(target) != sha(source):
            raise ValueError('Content-addressed texture collision')
        if not target.exists():
            target.write_bytes(source.read_bytes())
    for record in records:
        target = ROOT / record['path']
        if sha(target) != record['expectedSHA256']:
            raise ValueError('Concurrent torso edit')
        target.write_bytes((output / 'packed' / record['path']).read_bytes())
    print(f'Installed {len(records)} torso fits', flush=True)


if __name__ == '__main__':
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('command', choices=['build', 'install'])
    ap.add_argument('--output', type=Path, required=True)
    ap.add_argument('--reviewed', type=Path)
    ap.add_argument('--jobs', type=int, default=4)
    args = ap.parse_args()
    if args.command == 'build':
        build(args.output.resolve(), args.reviewed.resolve() if args.reviewed else None, args.jobs)
    else:
        install(args.output.resolve())
