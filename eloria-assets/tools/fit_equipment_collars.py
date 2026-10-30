#!/usr/bin/env python3
"""Audit and refit existing torso collars against the canonical neck.

Preserves native artwork, topology, skeletons, bind matrices and unrelated
garment geometry. Original GLBs and every candidate remain in an ignored stage.
"""
from __future__ import annotations

import argparse
import json
import shutil
import subprocess
from pathlib import Path

import numpy as np

from refine_equipment_review import Edit, smooth, sha

ROOT = Path(__file__).resolve().parents[2]
CLIENT = ROOT / 'godot-client'
NECK_Z = -.038
BASE_Y = 1.435
TARGET_RX = .070
TARGET_RZ = .070
SKIN_CLEARANCE_RX = .078
SKIN_CLEARANCE_RZ = .078


def rays(points, faces):
    tri = points[faces]
    edge1 = tri[:,1]-tri[:,0]
    edge2 = tri[:,2]-tri[:,0]
    samples=[]
    for y in [1.48,1.50,1.52,1.54]:
        origin=np.array([0.,y,NECK_Z])
        for angle in np.linspace(0,2*np.pi,16,endpoint=False):
            direction=np.array([np.cos(angle),0,np.sin(angle)])
            h=np.cross(direction,edge2);det=np.einsum('ij,ij->i',edge1,h)
            valid=abs(det)>1e-9;inv=np.zeros_like(det);inv[valid]=1/det[valid]
            s=origin-tri[:,0];u=inv*np.einsum('ij,ij->i',s,h)
            q=np.cross(s,edge1);v=inv*(q@direction)
            t=inv*np.einsum('ij,ij->i',edge2,q)
            valid&=(u>=0)&(v>=0)&(u+v<=1)&(t>.025)&(t<.23)
            if valid.any():samples.append([y,float(angle),float(t[valid].min())])
    return samples


def profile(edit):
    primitive=edit.doc['meshes'][0]['primitives'][0]
    v=edit.read(primitive['attributes']['POSITION']);f=edit.faces(primitive)
    used=np.unique(f);p=v[used]
    central=p[(abs(p[:,0])<.145)&(abs(p[:,2]-NECK_Z)<.17)&(p[:,1]>1.45)]
    samples=rays(v,f)
    side=[t for y,a,t in samples if abs(np.sin(a))<.001]
    depth=[t for y,a,t in samples if abs(np.cos(a))<.001]
    left=[t for y,a,t in samples if np.cos(a)<-.99]
    right=[t for y,a,t in samples if np.cos(a)>.99]
    centre_x=np.clip((np.median(right)-np.median(left))*.5,-.022,.022) if left and right else 0.
    rx=float(np.median(side)) if side else .105
    rz=float(np.median(depth)) if depth else .115
    return {'rx_m':rx,'rz_m':rz,'center_x_m':float(centre_x),
            'upper_y_m':float(central[:,1].max()) if len(central) else None,
            'ray_samples':samples, 'central_vertices':len(central)}


def neck_surface(sex):
    """Use the real body's neck ownership, including its head-driven nape.

    The neck joint's bind basis is angled relative to the head. Assigning a
    whole collar to it tilts the opening away from the skin during idle.
    """
    source = CLIENT / f'assets/actors/native/races/luminous_{sex}.glb'
    body = Edit(source)
    primitive = next(m for m in body.doc['meshes'] if m.get('name') == 'body')['primitives'][0]
    attrs = body.arrays(primitive)
    points = attrs['POSITION']
    selected = ((points[:, 1] > 1.40) & (points[:, 1] < 1.55)
                & (abs(points[:, 0]) < .10) & (abs(points[:, 2] - NECK_Z) < .12))
    indices = np.flatnonzero(selected)
    _, unique = np.unique(np.round(points[indices], 5), axis=0, return_index=True)
    indices = indices[unique]
    joints = attrs['JOINTS_0'][indices].astype(int)
    weights = attrs['WEIGHTS_0'][indices]
    if 'JOINTS_1' in attrs:
        joints = np.concatenate([joints, attrs['JOINTS_1'][indices].astype(int)], axis=1)
        weights = np.concatenate([weights, attrs['WEIGHTS_1'][indices]], axis=1)
    return points[indices], joints, weights, body.joints(), sha(source)


def fit(edit, before, neck):
    scale_x=min(1.,max(.58,TARGET_RX/before['rx_m']))
    scale_z=min(1.,max(.50,TARGET_RZ/before['rz_m']))
    processed=set()
    total_moved=0
    for mesh in edit.doc['meshes']:
        if mesh.get('name')=='EquipmentForearmSkin':continue
        for primitive in mesh['primitives']:
            acc=primitive['attributes']['POSITION']
            if acc in processed:continue
            processed.add(acc)
            original=edit.read(acc);v=original.copy()
            used=np.unique(edit.faces(primitive));active=np.zeros(len(v),bool);active[used]=True
            radius=np.sqrt((v[:,0]/.17)**2+((v[:,2]-NECK_Z)/.18)**2)
            zone=smooth(1.405,1.49,v[:,1])*(1-smooth(1.0,1.55,radius))*active
            x=(v[:,0]-before['center_x_m'])*scale_x
            z=NECK_Z+(v[:,2]-NECK_Z)*scale_z
            y=BASE_Y+(v[:,1]-BASE_Y)*.55
            # An aggregate aperture measurement also sees the broader base of
            # a flared collar. Keep its narrower upper rim outside the actual
            # neck instead of shrinking that rim into the wearer.
            radius_after = np.sqrt((x / SKIN_CLEARANCE_RX) ** 2
                                   + ((z - NECK_Z) / SKIN_CLEARANCE_RZ) ** 2)
            minimum = smooth(1.43, 1.48, y)
            expansion = np.maximum(1., minimum / np.maximum(radius_after, .05))
            x *= expansion
            z = NECK_Z + (z - NECK_Z) * expansion
            v[:,0]+=(x-v[:,0])*zone
            v[:,1]+=(y-v[:,1])*zone
            v[:,2]+=(z-v[:,2])*zone
            if np.max(abs(v-original),initial=0)<1e-7:continue
            total_moved+=int((np.linalg.norm(v-original,axis=1)>1e-7).sum())
            edit.positions(primitive,v)
            # The upper collar follows the neck skin; the chest/shoulders retain
            # their authored ownership outside this smoothly fading region.
            _skin(edit,primitive,zone,v,neck)
    edit.changes.append({'collar_scale_x':scale_x,'collar_scale_z':scale_z,
                         'height_scale':.55,'target_center_z_m':NECK_Z,
                         'collar_vertices':total_moved,
                         'neck_weight_source_sha256':neck[-1]})


def _skin(edit,primitive,zone,points,neck):
    attrs=primitive['attributes']
    if 'JOINTS_0' not in attrs:return
    names=edit.joints()
    body_points, body_js, body_ws, body_names, _ = neck
    mapped = np.array([names.index(name) for name in body_names])
    sets=2 if 'JOINTS_1' in attrs else 1
    js=np.concatenate([edit.read(attrs[f'JOINTS_{s}']).astype(int) for s in range(sets)],axis=1)
    ws=np.concatenate([edit.read(attrs[f'WEIGHTS_{s}']) for s in range(sets)],axis=1)
    for i in np.flatnonzero(zone>1e-7):
        dense=np.bincount(js[i],weights=ws[i]*(1-zone[i]),minlength=len(names))
        distance = np.linalg.norm(body_points - points[i], axis=1)
        nearest = np.argsort(distance)[:6]
        share = 1 / np.maximum(distance[nearest], .001) ** 2
        share /= share.sum()
        for vertex, fraction in zip(nearest, share):
            np.add.at(dense, mapped[body_js[vertex]], body_ws[vertex] * fraction * zone[i])
        indices=np.argsort(dense)[-js.shape[1]:][::-1]
        js[i]=indices;ws[i]=dense[indices]/dense[indices].sum()
    for s in range(sets):
        edit.put(attrs[f'JOINTS_{s}'],js[:,s*4:(s+1)*4])
        edit.put(attrs[f'WEIGHTS_{s}'],ws[:,s*4:(s+1)*4])


def run(stage,install,audit_only,source_ref):
    stage=stage.resolve()
    if '.local' not in stage.parts:raise ValueError('Use an ignored .local stage')
    stage.mkdir(parents=True,exist_ok=True)
    registry=json.loads((CLIENT/'data/actors/equipment.json').read_text())['models']
    jobs={}
    for key,spec in registry.items():
        if not key.startswith('5:'):continue
        for row in [spec,*spec.get('variants',{}).values()]:
            jobs[row['scene']]=key
    prior_path=stage/'manifest.json';prior={}
    if prior_path.exists():prior={r['scene']:r.get('after_sha256') for r in json.loads(prior_path.read_text())['items']}
    records=[]
    necks = {sex: neck_surface(sex) for sex in ['male', 'female']}
    for scene,key in sorted(jobs.items()):
        rel=Path(scene[6:]);src=CLIENT/rel;original=stage/'originals'/rel
        if not original.exists():
            original.parent.mkdir(parents=True,exist_ok=True)
            if source_ref:
                result=subprocess.run(['git','show',f'{source_ref}:godot-client/{rel.as_posix()}'],cwd=ROOT,check=True,capture_output=True)
                original.write_bytes(result.stdout)
            else:shutil.copy2(src,original)
        edit=Edit(original);before=profile(edit)
        record={'key':key,'scene':scene,'before_sha256':sha(original),'before':before}
        if not audit_only:
            sex = 'female' if '/human_female/' in scene else 'male'
            fit(edit,before,necks[sex]);out=stage/'revised'/rel;edit.finish(out)
            check=Edit(out);record.update(after=profile(check),after_sha256=sha(out),changes=edit.changes,validation=edit.validation)
            if install:
                if sha(src) not in {record['before_sha256'],prior.get(scene),record['after_sha256']}:
                    raise ValueError(f'Active model has newer edits: {scene}')
                shutil.copy2(out,src)
        records.append(record)
    report={'schema':1,'scope':'Existing native torso collar fit','items':records}
    report_path = stage / ('audit.json' if audit_only else 'manifest.json')
    report_path.write_bytes((json.dumps(report,indent=2)+'\n').encode())
    print(json.dumps({'files':len(records),'designs':len({r['key'] for r in records}),'installed':install}))


def validate(stage):
    """Independently compare installed results with retained source bytes."""
    report = json.loads((stage / 'manifest.json').read_text(encoding='utf-8'))
    worst_weight_error = 0.
    max_outside_displacement = 0.
    for row in report['items']:
        rel = Path(row['scene'][6:])
        original = stage / 'originals' / rel
        installed = CLIENT / rel
        assert sha(original) == row['before_sha256'], rel
        assert sha(installed) == row['after_sha256'], rel
        a, b = Edit(original), Edit(installed)
        assert a.doc['nodes'] == b.doc['nodes'], (rel, 'rig nodes')
        for sa, sb in zip(a.doc['skins'], b.doc['skins'], strict=True):
            assert {k: v for k, v in sa.items() if k != 'inverseBindMatrices'} == {
                k: v for k, v in sb.items() if k != 'inverseBindMatrices'}, rel
            assert np.array_equal(a.read(sa['inverseBindMatrices']),
                                  b.read(sb['inverseBindMatrices'])), (rel, 'binds')
        for field in ['materials', 'images', 'textures', 'samplers', 'animations']:
            assert a.doc.get(field) == b.doc.get(field), (rel, field)
        for ma, mb in zip(a.doc['meshes'], b.doc['meshes'], strict=True):
            assert ma.get('name') == mb.get('name') and ma.get('extras') == mb.get('extras'), rel
            for pa, pb in zip(ma['primitives'], mb['primitives'], strict=True):
                fa, fb = a.faces(pa), b.faces(pb)
                assert np.array_equal(fa, fb), (rel, 'topology')
                aa, ab = a.arrays(pa), b.arrays(pb)
                assert aa.keys() == ab.keys() and pa.get('material') == pb.get('material'), rel
                for name in aa:
                    assert aa[name].shape == ab[name].shape and np.isfinite(ab[name]).all(), (rel, name)
                    if name not in ['POSITION', 'NORMAL', 'JOINTS_0', 'JOINTS_1', 'WEIGHTS_0', 'WEIGHTS_1']:
                        assert np.array_equal(aa[name], ab[name]), (rel, name)
                p, q = aa['POSITION'], ab['POSITION']
                radius = np.sqrt((p[:, 0] / .17) ** 2 + ((p[:, 2] - NECK_Z) / .18) ** 2)
                outside = (p[:, 1] <= 1.405) | (radius >= 1.55)
                displacement = float(np.linalg.norm(q[outside] - p[outside], axis=1).max(initial=0))
                max_outside_displacement = max(max_outside_displacement, displacement)
                assert displacement < 1e-7, (rel, 'unrelated geometry')
                def areas(v):
                    return np.linalg.norm(np.cross(v[fa[:, 1]] - v[fa[:, 0]],
                                                   v[fa[:, 2]] - v[fa[:, 0]]), axis=1)
                assert not ((areas(p) > 1e-8) & (areas(q) < 1e-10)).any(), (rel, 'collapsed faces')
                if 'WEIGHTS_0' in ab:
                    total = ab['WEIGHTS_0'].sum(axis=1)
                    if 'WEIGHTS_1' in ab:
                        total += ab['WEIGHTS_1'].sum(axis=1)
                    error = float(abs(total - 1).max(initial=0))
                    worst_weight_error = max(worst_weight_error, error)
                    assert error < .0081, (rel, 'weight normalization')
                    for name in ['JOINTS_0', 'JOINTS_1']:
                        if name in ab:
                            assert ab[name].min() >= 0 and ab[name].max() < len(b.joints()), (rel, name)
    result = {'status': 'passed', 'files': len(report['items']),
              'max_unrelated_displacement_m': max_outside_displacement,
              'max_weight_sum_error': worst_weight_error, 'new_collapsed_faces': 0,
              'preserved': ['topology', 'UVs', 'materials', 'images', 'rig nodes', 'inverse binds']}
    (stage / 'independent-validation.json').write_bytes((json.dumps(result, indent=2) + '\n').encode())
    print(json.dumps(result))


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--stage',type=Path,required=True)
    p.add_argument('--install',action='store_true');p.add_argument('--audit-only',action='store_true')
    p.add_argument('--source-ref');p.add_argument('--validate',action='store_true');a=p.parse_args()
    if a.validate:
        validate(a.stage.resolve())
    else:
        run(a.stage,a.install,a.audit_only,a.source_ref)
