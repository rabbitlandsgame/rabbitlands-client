#!/usr/bin/env python3
"""Fit existing breastplates and remove detached under-helmet neck shells.

Retain source bytes in an ignored stage. No rig, animation, material, UV or
image is replaced. A second run always starts from the retained originals.
"""
from __future__ import annotations

import argparse
import json
import shutil
import subprocess
from pathlib import Path

import numpy as np
from scipy.sparse import coo_matrix
from scipy.sparse.csgraph import connected_components

from refine_equipment_review import Edit, sha, smooth
from refine_equipment_review_second import head_surface

ROOT = Path(__file__).resolve().parents[2]
CLIENT = ROOT / 'godot-client'


def islands(edit, primitive):
    points = edit.read(primitive['attributes']['POSITION'])
    _, remap = np.unique(np.round(points, 5), axis=0, return_inverse=True)
    faces = remap[edit.faces(primitive)]
    a = np.r_[faces[:, 0], faces[:, 1], faces[:, 2]]
    b = np.r_[faces[:, 1], faces[:, 2], faces[:, 0]]
    count = int(remap.max()) + 1
    _, labels = connected_components(coo_matrix((np.ones(len(a)), (a, b)),
                                               shape=(count, count)), directed=False)
    return labels[remap]


def chest(edit):
    shell = edit.doc['meshes'][0]['primitives'][0]
    values = edit.read(shell['attributes']['POSITION'])[np.unique(edit.faces(shell))]
    center = values[(abs(values[:, 0]) < .17) & (values[:, 1] > 1.18) & (values[:, 1] < 1.39)]
    front = float(np.percentile(center[:, 2], 98)) if len(center) else 0.
    if front <= .165:
        return False
    factor = float(np.clip((.145 - .05) / (front - .05), .52, .85))
    done = set()
    for mesh in edit.doc['meshes']:
        if mesh.get('name') == 'EquipmentForearmSkin':
            continue
        for primitive in mesh['primitives']:
            index = primitive['attributes']['POSITION']
            if index in done:
                continue
            done.add(index)
            v = edit.read(index); q = v.copy()
            mask = smooth(.025, .070, v[:, 2])
            mask *= 1 - smooth(.18, .29, abs(v[:, 0]))
            mask *= smooth(1.04, 1.16, v[:, 1]) * (1 - smooth(1.40, 1.49, v[:, 1]))
            q[:, 2] -= (v[:, 2] - .05) * (1 - factor) * mask
            edit.positions(primitive, q)
    edit.changes.append({'chest_front_98_before_m': front, 'front_depth_factor': factor})
    return True


def guards(edit, entry, body):
    """Remove only disconnected neck shells entirely below the face opening.

    Their upper edge hangs below the jaw after the Human shell refit. Main
    helmet, face, ear and crest components remain intact. Existing shoulder
    skirts such as Crystalward extend outside this small neck-shell volume.
    """
    head = head_surface(body)
    offset = np.array(entry['socket']['offset']) + head['origin']
    removed = 0
    for mesh in edit.doc['meshes']:
        for primitive in mesh['primitives']:
            v = edit.read(primitive['attributes']['POSITION']) + offset
            f = edit.faces(primitive); labels = islands(edit, primitive)
            delete = []
            for label in np.unique(labels[np.unique(f)]):
                points = v[np.unique(f[labels[f[:, 0]] == label])]
                low, high = points.min(0), points.max(0)
                if (high[1] < head['eye_y'] - .012 and low[1] < head['eye_y'] - .10
                        and high[1] - low[1] > .045 and max(abs(low[0]), abs(high[0])) < .14
                        and low[2] > -.19 and high[2] < .14):
                    delete.append(label)
            keep = ~np.isin(labels[f[:, 0]], delete)
            if not keep.all():
                assert keep.any(), 'Neck repair cannot remove a complete helmet'
                edit.put(primitive['indices'], f[keep].reshape(-1))
                removed += int((~keep).sum())
    if removed:
        edit.changes.append({'removed_detached_neck_shell_triangles': removed})
    return bool(removed)


def run(stage, install, source_ref=None):
    stage = stage.resolve()
    if '.local' not in stage.parts:
        raise ValueError('Use an ignored .local stage')
    stage.mkdir(parents=True, exist_ok=True)
    registry = json.loads((CLIENT / 'data/actors/equipment.json').read_text())['models']
    policy = json.loads((ROOT / 'eloria-assets/tools/headwear_race_policy.json').read_text())['pieces']
    jobs = {}
    for key, spec in registry.items():
        if not (key.startswith('5:') or (key.startswith('3:') and policy[key]['kind'] == 'helm')):
            continue
        for entry in [spec, *spec.get('variants', {}).values()]:
            if key.startswith('3:') and '/human_' not in entry['scene']:
                continue
            jobs[entry['scene']] = (key, entry)
    prior_path = stage / 'manifest.json'
    prior = {r['scene']: r for r in json.loads(prior_path.read_text())['items']} if prior_path.exists() else {}
    records, audit = [], []
    for scene, (key, entry) in sorted(jobs.items()):
        rel = Path(scene[6:]); current = CLIENT / rel; original = stage / 'originals' / rel
        if not original.exists():
            original.parent.mkdir(parents=True, exist_ok=True)
            if source_ref:
                content = subprocess.run(['git', 'show', f'{source_ref}:godot-client/{rel.as_posix()}'],
                                         cwd=ROOT, capture_output=True, check=True).stdout
                original.write_bytes(content)
            else:
                shutil.copy2(current, original)
        edit = Edit(original)
        changed = chest(edit) if key.startswith('5:') else guards(edit, entry, rel.parent.name.replace('human_', 'luminous_'))
        audit.append({'key': key, 'scene': scene, 'changed': changed, 'changes': edit.changes})
        if not changed:
            continue
        out = stage / 'revised' / rel; edit.finish(out)
        row = {'key': key, 'scene': scene, 'before_sha256': sha(original),
               'after_sha256': sha(out), 'changes': edit.changes, 'validation': edit.validation}
        if install:
            allowed = {row['before_sha256'], row['after_sha256'], prior.get(scene, {}).get('after_sha256')}
            if sha(current) not in allowed:
                raise ValueError(f'Newer edits to {scene}')
            shutil.copy2(out, current)
        records.append(row)
    prior_path.write_bytes((json.dumps({'schema': 1, 'items': records, 'audit': audit}, indent=2) + '\n').encode())
    print(json.dumps({'audited': len(audit), 'changed': len(records), 'installed': install,
                      'keys': sorted({r['key'] for r in records})}))


def validate(stage):
    rows = json.loads((stage / 'manifest.json').read_text())['items']
    triangles_removed, max_weights, collapsed = 0, 0., 0
    for row in rows:
        rel = Path(row['scene'][6:]); a = Edit(stage / 'originals' / rel); b = Edit(CLIENT / rel)
        assert sha(a.path) == row['before_sha256'] and sha(b.path) == row['after_sha256'], rel
        for field in ['nodes', 'skins', 'materials', 'textures', 'images', 'samplers', 'animations']:
            assert a.doc.get(field) == b.doc.get(field), (rel, field)
        for skin in a.doc.get('skins', []):
            assert np.array_equal(a.read(skin['inverseBindMatrices']), b.read(skin['inverseBindMatrices']))
        for am, bm in zip(a.doc['meshes'], b.doc['meshes'], strict=True):
            for ap, bp in zip(am['primitives'], bm['primitives'], strict=True):
                av, bv = a.read(ap['attributes']['POSITION']), b.read(bp['attributes']['POSITION'])
                af, bf = a.faces(ap), b.faces(bp)
                assert len(av) == len(bv)
                if row['key'].startswith('5:'):
                    assert np.array_equal(af, bf)
                else:
                    assert np.array_equal(av, bv)
                    assert set(map(tuple, bf)) <= set(map(tuple, af))
                triangles_removed += len(af) - len(bf)
                for semantic in ap['attributes']:
                    if semantic not in ['POSITION', 'NORMAL']:
                        assert np.array_equal(a.read(ap['attributes'][semantic]), b.read(bp['attributes'][semantic]))
                for semantic in ['WEIGHTS_0', 'WEIGHTS_1']:
                    if semantic == 'WEIGHTS_0' and semantic in bp['attributes']:
                        weights = b.read(bp['attributes'][semantic]).sum(1)
                        if 'WEIGHTS_1' in bp['attributes']:weights += b.read(bp['attributes']['WEIGHTS_1']).sum(1)
                        max_weights = max(max_weights, float(abs(weights - 1).max()))
                for image in a.doc.get('images', []):
                    if 'bufferView' in image:
                        def payload(e):
                            view=e.doc['bufferViews'][image['bufferView']];start=view.get('byteOffset',0)
                            return e.blob[start:start+view['byteLength']]
                        assert payload(a) == payload(b)
                def area(v):return np.linalg.norm(np.cross(v[bf[:,1]]-v[bf[:,0]], v[bf[:,2]]-v[bf[:,0]]),axis=1)
                collapsed += int(((area(av)>1e-8)&(area(bv)<1e-10)).sum())
    assert collapsed == 0 and max_weights < .0081
    result={'status':'passed','files':len(rows),'new_collapsed_faces':collapsed,
            'removed_neck_shell_triangles':triangles_removed,'max_weight_sum_error':max_weights}
    (stage/'validation.json').write_bytes((json.dumps(result,indent=2)+'\n').encode())
    print(json.dumps(result))


if __name__ == '__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--stage',type=Path,required=True)
    parser.add_argument('--install',action='store_true')
    parser.add_argument('--validate',action='store_true')
    parser.add_argument('--source-ref',help='Read originals from this client revision in a fresh stage')
    args=parser.parse_args()
    validate(args.stage) if args.validate else run(args.stage,args.install,args.source_ref)
