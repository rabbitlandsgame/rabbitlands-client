"""Bounded runtime export of reviewed native skin/corrective animation.

The complete authoring file stays private. Runtime meshes keep geometry, binds,
materials and joint curves, pack at most eight influences, compensate the
packing in pose space, and replace redundant shapes with a positive affine basis.
Every supported clip participates, including idle and dedicated attacks.
"""
from pathlib import Path
import copy
import json
import numpy as np
from .asset import accessor, digest, write_glb
from .packing import append_array, compact
from .native_shapes import NativeShapeAsset


def append_joints(document, blob, values):
    values = np.asarray(values, dtype='<u2')
    blob.extend(b'\0' * (-len(blob) % 4))
    document['bufferViews'].append({'buffer': 0, 'byteOffset': len(blob), 'byteLength': values.nbytes})
    blob.extend(values.tobytes())
    document['accessors'].append({'bufferView': len(document['bufferViews']) - 1,
        'componentType': 5123, 'count': len(values), 'type': 'VEC4'})
    return len(document['accessors']) - 1


def sample_shapes(part, weights):
    values = np.zeros((len(weights), len(part['position']), 3))
    for i, row in enumerate(weights):
        active = np.flatnonzero(row != 0)
        if len(active):
            values[i] = np.einsum('m,mvc->vc', row[active], part['targets'][active])
    return values


def blended(part, world, joints=None, weights=None):
    matrices = world[part['nodes']] @ part['bind']
    joints = part['joints'] if joints is None else joints
    weights = part['weights'] if weights is None else weights
    out = np.zeros((len(weights), 3, 4))
    for slot in range(weights.shape[1]):
        out += matrices[joints[:, slot], :3] * weights[:, slot, None, None]
    return out


def positive_affine_basis(values, tolerance):
    """Project actual animated fields, with an explicit worst-vertex error bound."""
    shape = values.shape
    x = values.reshape(len(values), -1)
    if np.linalg.norm(x.reshape(-1, 3), axis=1).max(initial=0) <= tolerance:
        return np.empty((0, *shape[1:])), np.zeros((len(x), 0)), 0.0
    maximum = min(x.shape)
    rng = np.random.default_rng(17010)
    for rank in [16, 32, 64, 128, 256, 512, 768, 1024]:
        rank = min(rank, maximum)
        q = np.linalg.qr(x.T @ rng.normal(size=(len(x), rank)), mode='reduced')[0]
        for _ in range(2):
            q = np.linalg.qr(x.T @ (x @ q), mode='reduced')[0]
        _, _, vt = np.linalg.svd(x @ q, full_matrices=False)
        basis = vt @ q.T
        coefficients = x @ basis.T
        residual = (x - coefficients @ basis).reshape(shape)
        error = float(np.linalg.norm(residual, axis=2).max())
        print('RUNTIME_BASIS_FIT',rank,error/tolerance,flush=True)
        if error <= tolerance:
            scales = np.maximum(abs(coefficients).max(0), 1e-20)
            targets = (basis * scales[:, None]).reshape(-1, *shape[1:])
            weights = coefficients / scales
            lo, hi = weights.min(0), weights.max(0)
            span = np.maximum(hi-lo, 1e-20)
            bias = np.einsum('m,mvc->vc', lo, targets)
            positive = np.concatenate([bias[None], targets*span[:,None,None]])
            amounts = np.c_[np.ones(len(weights)), (weights-lo)/span]
            return positive, amounts, error
        if rank == maximum:
            break
    raise ValueError(f'Corrective rank budget cannot meet {tolerance}: {error}')


def export_runtime(source, output, height, tolerance_fraction=0.00002, packing_hz=768):
    a = NativeShapeAsset(source)
    d, blob = copy.deepcopy(a.d), bytearray(a.b)
    reports = []
    mesh_ids = [n['mesh'] for n in a.d['nodes'] if 'mesh' in n]
    if len(mesh_ids) != len(set(mesh_ids)) or any(len(m['primitives']) != 1 for m in a.d['meshes']):
        raise ValueError('Runtime basis export requires unique single-primitive meshes')
    for part_index, part in enumerate(a.parts):
        if 'joints' not in part:
            continue
        node = part['node']
        mesh = d['meshes'][d['nodes'][node]['mesh']]
        primitive_index = sum(p['node'] == node for p in a.parts[:part_index])
        primitive = mesh['primitives'][primitive_index]
        if any(set(t) - {'POSITION', 'NORMAL'} for t in primitive.get('targets', [])):
            raise ValueError('Review tangent or extension corrective attributes before exporting')
        order = np.argsort(-part['weights'], axis=1, kind='stable')[:, :8]
        joints = np.take_along_axis(part['joints'], order, axis=1)
        weights = np.take_along_axis(part['weights'], order, axis=1)
        dropped = 1 - weights.sum(1)
        weights /= weights.sum(1, keepdims=True)
        # Exactly preserve existing four/eight slots; reorder only oversized layouts.
        if part['weights'].shape[1] <= 8:
            joints, weights = part['joints'].copy(), part['weights'].copy()
            dropped[:] = 0
        changed = bool(np.max(dropped) > 1e-7)
        attributes = primitive['attributes']
        for key in list(attributes):
            if key.startswith(('JOINTS_', 'WEIGHTS_')):
                del attributes[key]
        for start in range(0, joints.shape[1], 4):
            attributes[f'JOINTS_{start//4}'] = append_joints(d, blob, joints[:, start:start+4])
            attributes[f'WEIGHTS_{start//4}'] = append_array(d, blob, weights[:, start:start+4], 'VEC4')
        rest_source = blended(part, a.rest)
        rest_packed = blended(part, a.rest, joints, weights)
        base = part['position']
        rest_field = sample_shapes(part, a.default_weights[node][None])[0]
        wanted = np.einsum('vab,vb->va', rest_source, base + np.c_[rest_field, np.zeros(len(base))])
        plain = np.einsum('vab,vb->va', rest_packed, base)
        fields = [np.linalg.solve(rest_packed[:, :, :3], (wanted-plain)[..., None])[..., 0][None]]
        has_normals = 'NORMAL' in primitive['attributes'] and (changed or any('NORMAL' in t for t in primitive.get('targets', [])))
        normal_fields = []
        normal_scale = .05 * height
        if has_normals:
            normal_base = accessor(a.d, a.b, a.d['meshes'][a.d['nodes'][node]['mesh']]['primitives'][primitive_index]['attributes']['NORMAL'])
            normal_part = {'position': part['position'], 'targets': np.array([accessor(a.d,a.b,t['NORMAL']) if 'NORMAL' in t else np.zeros_like(normal_base) for t in a.d['meshes'][a.d['nodes'][node]['mesh']]['primitives'][primitive_index].get('targets',[])])}
            original_normal = normal_base + sample_shapes(normal_part,a.default_weights[node][None])[0]
            normal_fields.append((np.linalg.solve(rest_packed[:,:,:3],np.einsum('vab,vb->va',rest_source[:,:,:3],original_normal)[...,None])[...,0]-normal_base)[None])
        clocks, ranges = {}, {}
        for clip, animation in a.animations.items():
            channels = [ch for ch in animation['channels'] if ch['target'] == {'node': node, 'path': 'weights'}]
            if changed:
                ts = np.unique(np.r_[np.linspace(0, a.duration(clip), round(a.duration(clip)*packing_hz)+1),
                    *[accessor(a.d, a.b, s['input']).ravel() for s in animation['samplers']]].astype('float32'))
            elif channels:
                sampler = animation['samplers'][channels[0]['sampler']]
                if sampler.get('interpolation', 'LINEAR') != 'LINEAR':
                    raise ValueError('Only linear corrective clocks have a convex error bound')
                ts = accessor(a.d, a.b, sampler['input']).ravel()
            else:
                ts = np.array([0., a.duration(clip)], dtype='float32')
            t, q, scale, morph = a.sample(clip, ts)
            local = sample_shapes(part, morph[node])
            normal_local = sample_shapes(normal_part, morph[node]) if has_normals else None
            if changed:
                for k in range(len(ts)):
                    world = a.world(t[k], q[k], scale[k])
                    full = blended(part, world)
                    packed = blended(part, world, joints, weights)
                    desired = np.einsum('vab,vb->va', full, base + np.c_[local[k], np.zeros(len(base))])
                    plain = np.einsum('vab,vb->va', packed, base)
                    local[k] = np.linalg.solve(packed[:, :, :3], (desired-plain)[..., None])[..., 0]
                    if has_normals:
                        normal_local[k] = np.linalg.solve(packed[:,:,:3],np.einsum('vab,vb->va',full[:,:,:3],normal_base+normal_local[k])[...,None])[...,0]-normal_base
            start = sum(len(v) for v in fields)
            fields.append(local)
            if has_normals: normal_fields.append(normal_local)
            ranges[clip] = (start, start+len(ts))
            clocks[clip] = ts
        values = np.concatenate(fields)
        if has_normals: values = np.concatenate([values, np.concatenate(normal_fields)*normal_scale],axis=1)
        targets, coefficients, error = positive_affine_basis(values, tolerance_fraction*height)
        primitive['targets'] = [{'POSITION': append_array(d, blob, target[:len(base)], 'VEC3'), **({'NORMAL':append_array(d,blob,target[len(base):]/normal_scale,'VEC3')} if has_normals else {})} for target in targets]
        mesh.setdefault('extras', {})['targetNames'] = [f'RL_Runtime_{i:04d}' for i in range(len(targets))]
        mesh['weights'] = coefficients[0].tolist()
        d['nodes'][node]['weights'] = coefficients[0].tolist()
        for animation in d['animations']:
            animation['channels'] = [ch for ch in animation['channels'] if ch['target'] != {'node': node, 'path': 'weights'}]
            if not len(targets):
                continue
            lo, hi = ranges[animation['name']]
            animation['channels'].append({'target': {'node': node, 'path': 'weights'}, 'sampler': len(animation['samplers'])})
            animation['samplers'].append({'input': append_array(d, blob, clocks[animation['name']][:, None], 'SCALAR'),
                'output': append_array(d, blob, coefficients[lo:hi].reshape(-1, 1), 'SCALAR'), 'interpolation': 'LINEAR'})
        reports.append({'part': part_index, 'vertices': len(base), 'source_shapes': len(part['targets']),
            'runtime_shapes': len(targets), 'skin_slots': joints.shape[1], 'maximum_dropped_weight': float(max(dropped)),
            'packing_compensated': changed, 'shape_samples': len(values), 'maximum_local_fit_error_over_height': error/height})
    for animation in d['animations']:
        used = sorted({ch['sampler'] for ch in animation['channels']})
        remap = {old: new for new, old in enumerate(used)}
        animation['samplers'] = [animation['samplers'][i] for i in used]
        for ch in animation['channels']:
            ch['sampler'] = remap[ch['sampler']]
    extras = a.d.get('asset', {}).get('extras', {})
    d['asset']['extras'] = {'rabbitlands_animation_bake_fps': extras.get('rabbitlands_animation_bake_fps', 3072),
        'rabbitlands_motion_baseline': 10, 'rabbitlands_iterative_baseline': True}
    d, blob, packing = compact(d, blob)
    text = json.dumps(d)
    if 'C:/' in text or 'C:\\\\' in text or 'eloria-project' in text:
        raise ValueError('Private authoring path in exported document')
    write_glb(output, d, blob)
    return {'source_sha256': digest(source), 'runtime_sha256': digest(output), 'source_bytes': Path(source).stat().st_size,
        'runtime_bytes': Path(output).stat().st_size, 'parts': reports, 'packing': packing,
        'basis_representation':'positive_affine', 'method': 'Positive affine corrective basis over all native actions, bounded local error; compensated eight-slot skin. Original native joint curves retained.'}


def reduce_affine_basis(path, output, height, keep, prior_error_fraction, maximum_total_error=.0001):
    """Bound a prefix reduction at every encoded LINEAR corrective knot.

    Supported for one position-only affine basis. Reject normals and multiple
    corrected meshes rather than silently discarding their fields.
    """
    from .asset import read_glb
    d,b=read_glb(path)
    meshes=[(i,d['meshes'][n['mesh']]) for i,n in enumerate(d['nodes']) if 'mesh' in n and d['meshes'][n['mesh']]['primitives'][0].get('targets')]
    if len(meshes)!=1: raise ValueError('Prefix reduction needs one corrected mesh')
    node_id,mesh=meshes[0];primitive=mesh['primitives'][0];targets=primitive['targets'];count=len(targets);rank=count-1
    if not 0 < keep < rank: raise ValueError('Prefix must retain a positive proper subset of basis vectors')
    if any(set(t)!={'POSITION'} for t in targets): raise ValueError('Prefix reduction requires position-only targets')
    basis=np.array([accessor(d,b,t['POSITION']) for t in targets[1:]]);bias=accessor(d,b,targets[0]['POSITION']);flat=basis.reshape(rank,-1)
    norms=np.einsum('ij,ij->i',flat,flat)
    if np.any(norms<1e-30): raise ValueError('Degenerate affine basis')
    projection=(flat@bias.ravel())/norms
    channels=[]
    default=np.array(d['nodes'][node_id].get('weights',mesh.get('weights',[0.]*count)))
    if default[0]!=1: raise ValueError('Expected constant default affine bias')
    rest_residual=((default[1:]+projection)[keep:]@flat[keep:]).reshape(-1,3)
    maximum=float(np.linalg.norm(rest_residual,axis=1).max())
    for animation in d['animations']:
        for channel in animation['channels']:
            if channel['target']!={'node':node_id,'path':'weights'}: continue
            sampler=animation['samplers'][channel['sampler']]
            if sampler.get('interpolation','LINEAR')!='LINEAR': raise ValueError('Prefix bound requires linear shape clocks')
            values=accessor(d,b,sampler['output']).reshape(-1,count)
            if not np.all(values[:,0]==1): raise ValueError('Expected constant affine bias')
            coefficients=values[:,1:]+projection
            for i in range(0,len(values),24):
                residual=(coefficients[i:i+24,keep:]@flat[keep:]).reshape(-1,len(bias),3)
                maximum=max(maximum,float(np.linalg.norm(residual,axis=2).max()))
            channels.append((sampler,values))
    total=prior_error_fraction+maximum/height
    if total>maximum_total_error: raise ValueError(f'Prefix error {total} exceeds {maximum_total_error}')
    new_bias=bias-np.einsum('m,mvc->vc',projection[keep:],basis[keep:]);blob=bytearray(b)
    primitive['targets']=[{'POSITION':append_array(d,blob,new_bias,'VEC3')}]+targets[1:keep+1]
    mesh['extras']['targetNames']=mesh['extras']['targetNames'][:keep+1]
    for owner in [mesh,d['nodes'][node_id]]: owner['weights']=owner['weights'][:keep+1]
    for sampler,values in channels: sampler['output']=append_array(d,blob,values[:,:keep+1].reshape(-1,1),'SCALAR')
    d,blob,_=compact(d,blob);write_glb(output,d,blob)
    return {'prefix_added_local_error_over_height':maximum/height,'maximum_total_local_fit_error_over_height':total,'runtime_shapes':keep+1,'runtime_sha256':digest(output),'runtime_bytes':Path(output).stat().st_size}


def main():
    import argparse
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--source',required=True);p.add_argument('--output',required=True);p.add_argument('--height',required=True,type=float)
    p.add_argument('--tolerance',type=float,default=.00002);p.add_argument('--packing-hz',type=int,default=768)
    p.add_argument('--basis-prefix',type=int);p.add_argument('--maximum-total-error',type=float,default=.0001);p.add_argument('--report',required=True)
    args=p.parse_args()
    report=export_runtime(args.source,args.output,args.height,args.tolerance,args.packing_hz)
    if args.basis_prefix:
        reduced=reduce_affine_basis(args.output,args.output,args.height,args.basis_prefix,max(x['maximum_local_fit_error_over_height'] for x in report['parts']),args.maximum_total_error)
        report.update(reduced)
    Path(args.report).write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8')

if __name__=='__main__': main()
