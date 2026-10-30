#!/usr/bin/env python3
"""Scoped repairs to existing equipment, with original bytes retained in a stage.

This does not generate equipment. It adjusts existing shell positions, skin
ownership and UVs. No rig, inverse bind, animation or texture image is replaced.
Run with --stage <ignored directory>; inspect outputs before --install.
"""
from __future__ import annotations

import argparse
import copy
import hashlib
import json
import shutil
import subprocess
from pathlib import Path

import numpy as np
import trimesh

import equipment_authoring as ea
from tpose_bodies.vendor import glbkit

ROOT = Path(__file__).resolve().parents[2]
CLIENT = ROOT / 'godot-client'


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def smooth(a, b, x):
    t = np.clip((x-a)/(b-a), 0, 1)
    return t*t*(3-2*t)


class Edit:
    def __init__(self, path):
        self.path = path
        self.doc, blob = ea.read_glb(path)
        self.original_doc = copy.deepcopy(self.doc)
        self.blob = bytearray(blob)
        self.changes = []
        self.suppressed_nodes = set()

    def read(self, acc):
        return ea.accessor_array(self.doc, self.blob, acc).copy()

    def put(self, acc, values):
        spec = self.doc['accessors'][acc]
        dtype = ea._COMPONENT_DTYPES[spec['componentType']]
        if spec.get('normalized') and np.dtype(dtype).kind in 'iu':
            values = np.rint(np.asarray(values)*np.iinfo(np.dtype(dtype)).max)
        values = np.asarray(values, dtype=dtype)
        while len(self.blob) % 4:
            self.blob.append(0)
        view = {'buffer': 0, 'byteOffset': len(self.blob), 'byteLength': values.nbytes}
        self.blob.extend(values.tobytes())
        spec['bufferView'] = len(self.doc['bufferViews'])
        spec['byteOffset'] = 0
        spec['count'] = len(values)
        self.doc['bufferViews'].append(view)
        if 'min' in spec:
            spec['min'] = np.atleast_1d(values.min(axis=0)).tolist()
        if 'max' in spec:
            spec['max'] = np.atleast_1d(values.max(axis=0)).tolist()

    def arrays(self, primitive):
        return {name: self.read(acc) for name, acc in primitive['attributes'].items()}

    def faces(self, primitive):
        return self.read(primitive['indices']).reshape(-1, 3).astype(int)

    def positions(self, primitive, points):
        old = self.read(primitive['attributes']['POSITION'])
        moved = np.linalg.norm(points-old, axis=1)
        if moved.max(initial=0) < 1e-7:
            return
        self.put(primitive['attributes']['POSITION'], points)
        # Recompute the affected vertex normals using welded authored positions.
        faces = self.faces(primitive)
        unique, inv = np.unique(np.round(points, 6), axis=0, return_inverse=True)
        mesh = trimesh.Trimesh(unique, inv[faces], process=False)
        if 'NORMAL' in primitive['attributes']:
            prior_unique, prior_inv = np.unique(np.round(old, 6), axis=0, return_inverse=True)
            prior = trimesh.Trimesh(prior_unique, prior_inv[faces], process=False)
            normals = self.read(primitive['attributes']['NORMAL'])
            normals += mesh.vertex_normals[inv]-prior.vertex_normals[prior_inv]
            normals /= np.maximum(np.linalg.norm(normals, axis=1)[:, None], 1e-8)
            self.put(primitive['attributes']['NORMAL'], normals)
        self.changes.append({'moved_vertices': int((moved>1e-7).sum()),
                             'max_displacement_m': round(float(moved.max()), 6)})

    def joints(self):
        return [self.doc['nodes'][i]['name'] for i in self.doc['skins'][0]['joints']]

    def rebind(self, primitive, share, name):
        attrs = primitive['attributes']
        names = self.joints()
        # These fitted garment sources have four influences; do not truncate a
        # source that supplies the second influence set.
        assert 'JOINTS_1' not in attrs
        j = self.read(attrs['JOINTS_0']).astype(int)
        w = self.read(attrs['WEIGHTS_0'])
        for i in np.flatnonzero(share > 0):
            field = np.bincount(j[i], weights=w[i]*(1-share[i]), minlength=len(names))
            field[names.index(name)] += share[i]
            ids = np.argsort(field)[-4:][::-1]
            j[i] = ids
            w[i] = field[ids]/field[ids].sum()
        self.put(attrs['JOINTS_0'], j)
        self.put(attrs['WEIGHTS_0'], w)

    def finish(self, target):
        # The skeleton and its inverse binds remain byte-for-byte equivalent.
        assert self.doc.get('skins') == self.original_doc.get('skins')
        for index, original in enumerate(self.original_doc['nodes']):
            expected = copy.deepcopy(original)
            if index in self.suppressed_nodes:
                expected.pop('mesh',None);expected.pop('skin',None)
            assert self.doc['nodes'][index] == expected
        d, b = glbkit.compact(self.doc, bytes(self.blob))
        validation = {'vertices':0,'triangles':0,'max_weight_sum_error':0.0}
        for mesh in d['meshes']:
            for primitive in mesh['primitives']:
                attrs=primitive['attributes']
                points=ea.accessor_array(d,b,attrs['POSITION'])
                faces=ea.accessor_array(d,b,primitive['indices']).reshape(-1,3)
                assert np.isfinite(points).all() and faces.min()>=0 and faces.max()<len(points)
                validation['vertices']+=len(points);validation['triangles']+=len(faces)
                for semantic,accessor in attrs.items():
                    array=ea.accessor_array(d,b,accessor)
                    assert len(array)==len(points) and np.isfinite(array).all(),semantic
                if 'WEIGHTS_0' in attrs:
                    weights=ea.accessor_array(d,b,attrs['WEIGHTS_0'])
                    error=float(np.abs(weights.sum(1)-1).max())
                    assert error<.0081, error
                    validation['max_weight_sum_error']=max(validation['max_weight_sum_error'],error)
        self.validation=validation
        target.parent.mkdir(parents=True, exist_ok=True)
        glbkit.write(target, d, b)


def short_sleeves(edit):
    shell = edit.doc['meshes'][0]['primitives'][0]
    points = edit.read(shell['attributes']['POSITION'])
    end = float(abs(points[:, 0]).max())
    if not .25 < end < .56:
        return False
    # The existing sleeve itself hides this overlap; expose the actual body
    # beyond it, retaining its selected skin appearance on every race.
    cut = end-.055
    for mesh in edit.doc['meshes']:
        if mesh.get('name') != 'GeneratedArmorBacking':
            continue
        for p in mesh['primitives']:
            v = edit.read(p['attributes']['POSITION'])
            f = edit.faces(p)
            keep = np.max(abs(v[f, 0]), axis=1) < cut
            skin_primitive = copy.deepcopy(p)
            skin_primitive['indices'] = len(edit.doc['accessors'])
            edit.doc['accessors'].append(copy.deepcopy(edit.doc['accessors'][p['indices']]))
            edit.put(skin_primitive['indices'], f[~keep].reshape(-1))
            names = edit.joints()
            worlds = ea.global_matrices(edit.doc)
            skin_j = edit.read(p['attributes']['JOINTS_0']).astype(int)
            skin_w = edit.read(p['attributes']['WEIGHTS_0'])
            for side, sign in [('l',1),('r',-1)]:
                lower = names.index('lowerarm_'+side)
                upper = names.index('upperarm_'+side)
                hand = names.index('hand_'+side)
                elbow_x = abs(worlds[edit.doc['skins'][0]['joints'][lower]][0,3])
                wrist_x = abs(worlds[edit.doc['skins'][0]['joints'][hand]][0,3])
                mask = sign*v[:,0]>cut-.01
                x = sign*v[mask,0]
                forearm = smooth(elbow_x-.035,elbow_x+.035,x)
                palm = smooth(wrist_x-.035,wrist_x+.010,x)
                skin_j[mask] = [upper,lower,hand,0]
                skin_w[mask] = np.c_[1-forearm,forearm*(1-palm),forearm*palm,np.zeros(len(x))]
            for semantic,values in [('JOINTS_0',skin_j),('WEIGHTS_0',skin_w)]:
                index = len(edit.doc['accessors'])
                edit.doc['accessors'].append(copy.deepcopy(edit.doc['accessors'][p['attributes'][semantic]]))
                skin_primitive['attributes'][semantic] = index
                edit.put(index,values)
            skin_mesh = len(edit.doc['meshes'])
            edit.doc['meshes'].append({'name':'EquipmentForearmSkin', 'primitives':[skin_primitive]})
            skin_node = len(edit.doc['nodes'])
            edit.doc['nodes'].append({'name':'EquipmentForearmSkin', 'mesh':skin_mesh, 'skin':0})
            edit.doc['scenes'][edit.doc.get('scene',0)]['nodes'].append(skin_node)
            edit.put(p['indices'], f[keep].reshape(-1))
        edit.changes.append({'short_sleeve_skin_split_x_m': round(cut, 6)})
    return True


def collar(edit):
    p = edit.doc['meshes'][0]['primitives'][0]
    v = edit.read(p['attributes']['POSITION'])
    # Soft collars should follow the neck instead of the unrelated clavicles.
    share = smooth(1.45, 1.535, v[:, 1])*(1-smooth(.12, .18, abs(v[:, 0])))
    cap = (v[:, 1]>1.49)&(abs(v[:, 0])<.14)
    center_x = (v[cap, 0].min()+v[cap, 0].max())*.5
    v[:, 0] -= share*center_x
    edit.positions(p, v)
    edit.rebind(p, share*.85, 'neck_01')
    edit.changes.append({'collar_neck_weight': .85, 'collar_x_offset_m': float(-center_x)})


def cuff(edit):
    p = edit.doc['meshes'][0]['primitives'][0]
    v = edit.read(p['attributes']['POSITION'])
    names = edit.joints()
    worlds = ea.global_matrices(edit.doc)
    for side, sign in [('l', 1), ('r', -1)]:
        elbow = worlds[edit.doc['skins'][0]['joints'][names.index('lowerarm_'+side)]][:3, 3]
        wrist = worlds[edit.doc['skins'][0]['joints'][names.index('hand_'+side)]][:3, 3]
        end = sign*v[:, 0].max() if sign == 1 else -v[:, 0].min()
        mask = sign*v[:, 0] > end-.045
        center = (v[mask].min(0)+v[mask].max(0))*.5
        axis = elbow+(wrist-elbow)*(center[0]-elbow[0])/(wrist[0]-elbow[0])
        shift = axis[1:]-center[1:]
        blend = smooth(.49, .65, sign*v[:, 0])
        v[:, 1:] += blend[:, None]*shift
        v[:, 0] += sign*blend*(abs(wrist[0])-.015-end)
    edit.positions(p, v)


def boots(edit, key):
    names = edit.joints()
    world = ea.global_matrices(edit.doc)
    for mesh in edit.doc['meshes']:
        for p in mesh['primitives']:
            v = edit.read(p['attributes']['POSITION'])
            if key in ['6:240', '6:241']:
                drop = .060 if key == '6:240' else .080
                v[:, 1] -= drop*smooth(.16, .48, v[:, 1])
                if 'bodyCover' in mesh.get('extras', {}):
                    cover = mesh['extras']['bodyCover']
                    cover[1] -= drop*float(smooth(.16, .48, cover[1]))
            elif key == '6:250' and not mesh.get('name', '').startswith('Generated'):
                # Retain the original ankle and toe; open only the shaft over
                # the fitted trouser tube on both sides.
                for side, sign in [('l', 1), ('r', -1)]:
                    knee = world[edit.doc['skins'][0]['joints'][names.index('calf_'+side)]][:3, 3]
                    foot = world[edit.doc['skins'][0]['joints'][names.index('foot_'+side)]][:3, 3]
                    mask = sign*v[:, 0] > 0
                    t = ((v[mask, 1]-foot[1])/(knee[1]-foot[1]))[:, None]
                    axis = foot+(knee-foot)*t
                    radial = v[mask][:, [0, 2]]-axis[:, [0, 2]]
                    length = np.linalg.norm(radial, axis=1)
                    add = .009*smooth(.15, .29, v[mask, 1])
                    v[np.ix_(mask, [0, 2])] += radial/np.maximum(length[:, None], 1e-6)*add[:, None]
            edit.positions(p, v)


def hood(edit):
    for p in edit.doc['meshes'][0]['primitives']:
        v = edit.read(p['attributes']['POSITION'])
        # Keep the hood crown, brow and ornaments. Lower only the front cowl
        # below the chin, and taper the skirt inward to enter a torso collar.
        lower = 1-smooth(-.025, .045, v[:, 1])
        front = smooth(-.03, .075, v[:, 2])
        v[:, 1] -= .072*lower*front
        skirt = 1-smooth(-.10, -.035, v[:, 1])
        v[:, 0] *= 1-.30*skirt
        v[:, 2] *= 1-.34*skirt
        edit.positions(p, v)


def eye_slit(edit):
    for p in edit.doc['meshes'][0]['primitives']:
        v = edit.read(p['attributes']['POSITION'])
        front = smooth(.035,.080,v[:,2])
        band = smooth(-.04,.04,v[:,1])*(1-smooth(.095,.115,v[:,1]))
        v[:,1] -= .035*front*band
        edit.positions(p,v)


def mirrored_native_patch(edit, key):
    """Mirror existing triangles, UVs and matching bone ownership exactly."""
    p = edit.doc['meshes'][0]['primitives'][0]
    arrays = edit.arrays(p)
    assert set(arrays) == {'POSITION','NORMAL','TEXCOORD_0','JOINTS_0','WEIGHTS_0'}
    v = arrays['POSITION'];f = edit.faces(p);names = edit.joints();count = len(names)
    dense = np.zeros((len(v), count))
    for slot in range(4):
        dense[np.arange(len(v)), arrays['JOINTS_0'][:,slot].astype(int)] += arrays['WEIGHTS_0'][:,slot]
    fields = np.c_[v, arrays['NORMAL'], arrays['TEXCOORD_0'], dense]
    selected = np.ones(len(f), dtype=bool)
    if key=='4:188':
        unique, inv = np.unique(np.round(v,4), axis=0, return_inverse=True)
        mesh = trimesh.Trimesh(unique, inv[f], process=False)
        for comp in trimesh.graph.connected_components(mesh.edges_unique, min_len=3, nodes=np.arange(len(unique))):
            q = unique[comp]
            match = (key=='4:188' and 10<=len(comp)<=18 and q[:,1].min()>.95 and q[:,1].max()<1.06 and q[:,2].min()>.10)
            if match:
                selected = np.isin(inv[f[:,0]], comp)
                break
        else:
            raise ValueError(f'Expected native front panel not found: {key} {edit.path}')
        if key=='4:188':
            for material in edit.doc['materials']:
                if material.get('name','').endswith('Backing'):
                    # Its old olive lining showed as untextured grey wedges
                    # between blue quilted panels. Match the actual cloth.
                    material['pbrMetallicRoughness']['baseColorFactor']=[.018,.024,.035,1]
            # Discard the flattened cloth scraps below the native belt badge.
            # Its actual shield-shaped badge becomes the hanging front plate.
            centers = v[f].mean(1)
            scrap = (~selected)&(abs(centers[:,0])<.115)&(centers[:,1]>.74)&(centers[:,1]<.95)&(centers[:,2]>.045)
            f = f[~scrap];selected = selected[~scrap]
            for index,node in enumerate(edit.doc['nodes']):
                if node.get('name')=='ReconstructedInseams':
                    node.pop('mesh',None);node.pop('skin',None)
                    edit.suppressed_nodes.add(index)

    def clip(poly, axis, level, sign):
        out = []
        for a, b in zip(poly, poly[1:]+poly[:1]):
            da = sign*(a[axis]-level);db = sign*(b[axis]-level)
            if da>=-1e-9:
                out.append(a)
            if (da>0 and db<0) or (da<0 and db>0):
                out.append(a+(b-a)*da/(da-db))
        return out

    mirror_bones = np.arange(count)
    for i, name in enumerate(names):
        opposite = name[:-2]+('_r' if name.endswith('_l') else '_l')
        if (name.endswith('_l') or name.endswith('_r')) and opposite in names:
            mirror_bones[i] = names.index(opposite)
    output = []

    def emit(poly, mirror=False):
        if len(poly)<3:
            return
        for i in range(1,len(poly)-1):
            tri = np.array([poly[0],poly[i],poly[i+1]])
            if np.linalg.norm(np.cross(tri[1,:3]-tri[0,:3],tri[2,:3]-tri[0,:3]))<1e-10:
                continue
            if mirror:
                tri = tri[[0,2,1]]
                tri[:,[0,3]] *= -1
                tri[:,8:] = tri[:,8:][:,mirror_bones]
            output.extend(tri)

    source_sign = 1 if key=='4:189' else -1
    for index, face in enumerate(f):
        poly = list(fields[face].copy())
        if not selected[index]:
            emit(poly);continue
        if key=='5:212':
            emit(clip(poly,1,1.055,1))
            poly = clip(poly,1,1.055,-1)
        if key=='4:189':
            emit(clip(poly,1,.73,-1))
            poly = clip(poly,1,.73,1)
        if key=='4:188':
            for vertex in poly:
                vertex[1] = 1.032+(vertex[1]-1.032)*2.2
                vertex[2] += .020
                vertex[8:] = 0
                vertex[8+names.index('pelvis')] = 1
        half = clip(poly,0,0,source_sign)
        emit(half);emit(half,True)
    data = np.asarray(output)
    j = np.argsort(data[:,8:],axis=1)[:,-4:][:,::-1]
    w = np.take_along_axis(data[:,8:],j,axis=1)
    w /= np.maximum(w.sum(1)[:,None],1e-9)
    normal = data[:,3:6];normal /= np.maximum(np.linalg.norm(normal,axis=1)[:,None],1e-9)
    for name, values in {'POSITION':data[:,:3],'NORMAL':normal,'TEXCOORD_0':data[:,6:8],'JOINTS_0':j,'WEIGHTS_0':w}.items():
        edit.put(p['attributes'][name], values)
    edit.put(p['indices'],np.arange(len(data)))
    edit.changes.append({'mirrored_native_triangles':int(selected.sum()),'source_half':source_sign})


def run(stage, install, source_ref=None):
    stage = stage.resolve()
    if '.local' not in stage.parts:
        raise ValueError('A private ignored .local stage is required')
    registry = json.loads((CLIENT/'data/actors/equipment.json').read_text())['models']
    jobs = {}
    for key, spec in registry.items():
        if not (key in ['3:115','3:133','3:141','4:188','4:189','5:208','5:212','5:214','5:225','6:240','6:241','6:250'] or key.startswith('5:')):
            continue
        scenes = {spec.get('scene', '')}
        scenes.update(v.get('scene', '') for v in spec.get('variants', {}).values())
        for scene in scenes:
            if scene:
                jobs.setdefault(scene, key)
    prior_path=stage/'manifest.json'
    prior={r['scene']:r['after_sha256'] for r in json.loads(prior_path.read_text())['items']} if prior_path.exists() else {}
    records = []
    for scene, key in sorted(jobs.items()):
        rel = Path(scene[6:])
        src = CLIENT/rel
        original = stage/'originals'/rel
        if not original.exists():
            original.parent.mkdir(parents=True, exist_ok=True)
            if source_ref:
                result=subprocess.run(['git','show',f'{source_ref}:godot-client/{rel.as_posix()}'],cwd=ROOT,check=True,capture_output=True)
                original.write_bytes(result.stdout)
            else:
                shutil.copy2(src, original)
        edit = Edit(original)
        if any(m.get('name')=='EquipmentForearmSkin' or m.get('extras',{}).get('repairQuiltPaint') for m in edit.doc['meshes']):
            raise ValueError('Input already contains these repairs; use the preserved original stage or --source-ref.')
        # Resolve texture dependencies through their original active directory.
        edit.path = src
        if key.startswith('5:'):
            short_sleeves(edit)
        if key in ['5:208', '5:225']:
            collar(edit)
        if key == '5:214':
            cuff(edit)
        if key.startswith('6:'):
            boots(edit, key)
        if key == '3:115':
            hood(edit)
        if key == '3:133':
            edit.doc['meshes'][0].setdefault('extras',{})['repairQuiltPaint'] = True
            edit.changes.append({'repair_quilt_paint':True,'uvs_and_source_texture_preserved':True})
        if key == '3:141':
            eye_slit(edit)
        if key == '5:212':
            mirrored_native_patch(edit, key)
        if key in ['4:188','4:189']:
            mirrored_native_patch(edit, key)
        if not edit.changes:
            continue
        out = stage/'revised'/rel
        edit.finish(out)
        records.append({'key':key, 'scene':scene, 'before_sha256':sha(original),
                        'after_sha256':sha(out), 'changes':edit.changes, 'validation':edit.validation})
        if install:
            if sha(src) not in {sha(original),prior.get(scene),sha(out)}:
                raise ValueError(f'Active equipment has newer edits; compare them before installing: {scene}')
            shutil.copy2(out, src)
    report = {'schema':1, 'scope':'Existing native equipment repairs from equipment review', 'items':records}
    (stage/'manifest.json').write_text(json.dumps(report, indent=2)+'\n')
    print(json.dumps({'files':len(records), 'keys':sorted({r['key'] for r in records}), 'installed':install}))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--stage', type=Path, required=True)
    parser.add_argument('--install', action='store_true')
    parser.add_argument('--source-ref', help='Read pristine inputs from this client Git revision when starting a new stage')
    args = parser.parse_args()
    run(args.stage, args.install, args.source_ref)
