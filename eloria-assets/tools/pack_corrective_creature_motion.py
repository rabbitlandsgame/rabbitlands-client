"""Pack dense corrective motion using measured, actual-pose subset bases.

Unlike an arbitrary normal PCA basis, each retained NORMAL target is an original
unit-normal pose. Godot can normalize its endpoints without changing the basis.
No joint keys, base geometry, skin, textures, or native durations are reduced.
"""
import argparse, copy, json
from pathlib import Path
import numpy as np
from scipy.linalg.interpolative import interp_decomp
from video_motion.asset import read_glb, write_glb, accessor, digest
from video_motion.packing import append_array, compact


def subset_basis(rows, height, limit, label):
    rows = np.asarray(rows, dtype=float)
    if not np.any(rows):
        return np.empty((0, rows.shape[1])), np.zeros((len(rows), 0)), {"rank": 0, "error": 0.0}
    eps = 1e-4
    for attempt in range(7):
        rank, indices, projection = interp_decomp(rows.T, eps, rand=True, rng=np.random.default_rng(427))
        basis = rows[indices[:rank]].astype(np.float32).astype(float)
        coefficients = np.zeros((len(rows), rank))
        coefficients[indices[:rank]] = np.eye(rank)
        coefficients[indices[rank:]] = projection.T
        coefficients = coefficients.astype(np.float32).astype(float)
        error = float(np.linalg.norm((coefficients @ basis - rows).reshape(len(rows), -1, 3), axis=2).max())
        print(label, "rank", rank, "error", error, flush=True)
        if error <= limit:
            return basis, coefficients, {"rank": rank, "error": error, "limit": limit, "relative_tolerance": eps}
        eps *= .2
    raise ValueError(label + " cannot meet the representation bound")


def pack(source, baseline, output, height):
    d, raw = read_glb(source)
    old, old_raw = read_glb(baseline)
    d = copy.deepcopy(d); blob = bytearray(raw)
    assert len(d['meshes']) == len(old['meshes']) == 1, 'Explicit one-mesh correspondence required'
    mesh = d['meshes'][0]; primitives = mesh['primitives']
    original_count = len(old['meshes'][0]['primitives'][0].get('targets', []))
    count = len(primitives[0]['targets'])
    assert all(len(pr['targets']) == count for pr in primitives)
    assert len(primitives) == len(old['meshes'][0]['primitives'])
    for pr, original in zip(primitives, old['meshes'][0]['primitives']):
        for i in range(original_count):
            assert set(pr['targets'][i]) == set(original['targets'][i])
            for key, ai in pr['targets'][i].items():
                assert np.array_equal(accessor(d, blob, ai), accessor(old, old_raw, original['targets'][i][key])), 'Original corrective prefix changed'
    positions = np.concatenate([np.array([accessor(d,blob,t['POSITION']).ravel() for t in pr['targets']]) for pr in primitives], axis=1)
    normals = np.concatenate([np.array([accessor(d,blob,t['NORMAL']).ravel() for t in pr['targets']]) for pr in primitives], axis=1)
    extras = np.arange(original_count, count)
    pi = extras[np.any(positions[extras],axis=1)]
    ni = extras[np.any(normals[extras],axis=1)]
    assert not set(pi) & set(ni), 'Appended mixed targets require a separate representation'
    assert all(set(t) <= {'POSITION','NORMAL'} for pr in primitives for t in pr['targets'])
    tracks=[]; rows=[]; cursor=0
    for animation in d['animations']:
        for ch in animation['channels']:
            if ch['target']['path'] != 'weights': continue
            sampler=animation['samplers'][ch['sampler']]
            assert sampler.get('interpolation','LINEAR') in ('LINEAR','STEP')
            times=accessor(d,blob,sampler['input'])
            values=accessor(d,blob,sampler['output']).reshape(len(times),count)
            rows.append(values);tracks.append((sampler,cursor,len(values)));cursor+=len(values)
    defaults=[]
    for obj in [mesh]+[n for n in d['nodes'] if n.get('mesh')==0]:
        values=np.array(obj.get('weights',mesh.get('weights',[0.]*count)))
        defaults.append((obj,cursor));rows.append(values[None]);cursor+=1
    weights=np.concatenate(rows)
    pb, pc, pos_report = subset_basis(weights[:,pi] @ positions[pi],height,.00010*height,'position')
    # Input normal poses are convex at every original knot. The L1 envelope also
    # bounds LINEAR intervals and includes defaults and retained native actions.
    amplification=max(1.,float(abs(weights[:,ni]).sum(1).max()))
    nb, nc, normal_report=subset_basis(normals[ni],height,.003/amplification,'normal')
    transformed=np.concatenate([weights[:,:original_count],pc,weights[:,ni]@nc],axis=1).astype(np.float32)
    output_count=transformed.shape[1]
    for sampler,start,length in tracks:
        sampler['output']=append_array(d,blob,transformed[start:start+length].reshape(-1,1),'SCALAR')
    for obj,start in defaults: obj['weights']=transformed[start].tolist()
    split=0
    for pr in primitives:
        width=len(accessor(d,blob,pr['attributes']['POSITION']))*3
        zero=append_array(d,blob,np.zeros((width//3,3)),'VEC3')
        new=pr['targets'][:original_count]
        for row in pb:
            new.append({'POSITION':append_array(d,blob,row[split:split+width].reshape(-1,3),'VEC3'),'NORMAL':zero})
        for row in nb:
            new.append({'POSITION':zero,'NORMAL':append_array(d,blob,row[split:split+width].reshape(-1,3),'VEC3')})
        pr['targets']=new;split+=width
    names=mesh.get('extras',{}).get('targetNames',[str(i) for i in range(count)])
    mesh.setdefault('extras',{})['targetNames']=names[:original_count]+['RL_PositionPose_'+str(i) for i in range(len(pb))]+['RL_NormalPose_'+str(i) for i in range(len(nb))]
    packed,binary,lossless=compact(d,blob)
    write_glb(output,packed,binary)
    return {'passed':True,'source_sha256':digest(source),'runtime_sha256':digest(output),'source_bytes':Path(source).stat().st_size,'runtime_bytes':Path(output).stat().st_size,'original_target_prefix':original_count,'source_targets':count,'runtime_targets':output_count,'position_basis':pos_report,'normal_basis':normal_report,'normal_l1_envelope':amplification,'preserved':['all joint sampler knots','original morph target prefix','base geometry','normals','UVs','skin','binds','materials','textures','hierarchy','clip durations'],'lossless':lossless,'interpretation':'Measured corrective representation; artistic acceptance is separate. Complete-surface and engine qualification must also pass.'}


def main():
    ap=argparse.ArgumentParser(description=__doc__)
    for flag in ['source','baseline','output','report']:ap.add_argument('--'+flag,type=Path,required=True)
    ap.add_argument('--height',type=float,required=True);a=ap.parse_args()
    result=pack(a.source,a.baseline,a.output,a.height)
    a.report.write_text(json.dumps(result,indent=2)+'\n',encoding='utf-8')
    print('PACK_CORRECTIVE',result['runtime_bytes'],result['runtime_targets'],flush=True)
if __name__=='__main__':main()
