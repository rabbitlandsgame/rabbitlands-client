"""Compare runtime corrective packing against a frozen reviewed native model."""
import argparse
import json
from pathlib import Path
import numpy as np
from .asset import accessor, digest
from .native_shapes import NativeShapeAsset


def surface_sampler(asset, ids=None):
    """Cache a fixed physical field; avoid copying all shape targets each frame."""
    fields = []
    offset = 0
    for p in asset.parts:
        local = np.arange(len(p['position'])) if ids is None else np.asarray(ids)[(np.asarray(ids)>=offset)&(np.asarray(ids)<offset+len(p['position']))]-offset
        offset += len(p['position'])
        if not len(local): continue
        fields.append((p, local, p['targets'][:,local].reshape(len(p['targets']),-1) if len(p['targets']) else None))
    def evaluate(world, morph):
        out=[]
        for p, local, targets in fields:
            pos=p['position'][local].copy()
            if targets is not None:
                weights=morph.get(p['node'],asset.default_weights[p['node']])
                active=np.flatnonzero(weights)
                if len(active)==len(weights): pos[:,:3]+=(weights@targets).reshape(-1,3)
                elif len(active): pos[:,:3]+=np.einsum('m,mv->v',weights[active],targets[active]).reshape(-1,3)
            if 'joints' not in p: out.append((world[p['node']]@pos.T).T[:,:3]);continue
            matrices=world[p['nodes']]@p['bind']; v=np.zeros((len(local),3))
            for slot in range(p['joints'].shape[1]):
                v+=np.einsum('vab,vb->va',matrices[p['joints'][local,slot],:3],pos)*p['weights'][local,slot,None]
            out.append(v)
        return np.concatenate(out)
    return evaluate


def compare_runtime(source, runtime, height, foot_fields=None, gait_speeds=None):
    a,b=NativeShapeAsset(source),NativeShapeAsset(runtime)
    assert a.names==b.names and np.array_equal(a.parent,b.parent), 'Hierarchy changed'
    assert np.array_equal(a.rest,b.rest), 'Rest transforms changed'
    assert a.d['skins']==b.d['skins'] or all(np.array_equal(x['bind'],y['bind']) and np.array_equal(x['nodes'],y['nodes']) for x,y in zip(a.parts,b.parts) if 'bind' in x), 'Binds changed'
    assert len(a.parts)==len(b.parts)
    for pa,pb in zip(a.parts,b.parts): assert np.array_equal(pa['position'],pb['position']), 'Base geometry changed'
    for ma,mb in zip(a.d['meshes'],b.d['meshes']):
        for pa,pb in zip(ma['primitives'],mb['primitives']):
            assert pa.get('material')==pb.get('material')
            for key,value in pa['attributes'].items():
                if key.startswith(('WEIGHTS_','JOINTS_')): continue
                assert np.array_equal(accessor(a.d,a.b,value),accessor(b.d,b.b,pb['attributes'][key])), key
            if 'indices' in pa: assert np.array_equal(accessor(a.d,a.b,pa['indices']),accessor(b.d,b.b,pb['indices']))
    assert a.d.get('materials')==b.d.get('materials')
    for ia,ib in zip(a.d.get('images',[]),b.d.get('images',[])):
        va,vb=a.d['bufferViews'][ia['bufferView']],b.d['bufferViews'][ib['bufferView']]
        assert a.b[va.get('byteOffset',0):va.get('byteOffset',0)+va['byteLength']]==b.b[vb.get('byteOffset',0):vb.get('byteOffset',0)+vb['byteLength']], 'Texture changed'
    assert set(a.animations)==set(b.animations)
    for clip in a.animations:
        aa,bb=a.animations[clip],b.animations[clip]
        ca=[c for c in aa['channels'] if c['target']['path']!='weights'];cb=[c for c in bb['channels'] if c['target']['path']!='weights']
        assert len(ca)==len(cb)
        for x,y in zip(ca,cb):
            assert x['target']==y['target']
            sx,sy=aa['samplers'][x['sampler']],bb['samplers'][y['sampler']]
            assert sx.get('interpolation','LINEAR')==sy.get('interpolation','LINEAR')
            for key in ['input','output']: assert np.array_equal(accessor(a.d,a.b,sx[key]),accessor(b.d,b.b,sy[key])), 'Joint curve changed'
    sa,sb=surface_sampler(a),surface_sampler(b)
    rest_error=float(np.linalg.norm(sa(a.rest,{})-sb(b.rest,{}),axis=1).max()/height)
    clips={};maximum=rest_error
    for clip in a.animations:
        assert a.duration(clip)==b.duration(clip)
        times=np.unique(np.r_[np.linspace(0,a.duration(clip),13),np.array([.11337,.29381,.53119,.76347,.95131])*a.duration(clip)])
        ta,qa,za,wa=a.sample(clip,times);tb,qb,zb,wb=b.sample(clip,times);err=0.
        for k in range(len(times)):
            va=sa(a.world(ta[k],qa[k],za[k]),{n:x[k] for n,x in wa.items()});vb=sb(b.world(tb[k],qb[k],zb[k]),{n:x[k] for n,x in wb.items()})
            err=max(err,float(np.linalg.norm(va-vb,axis=1).max()/height))
        clips[clip]={'surface_samples':len(times),'max_surface_error_over_height':err};maximum=max(maximum,err)
    contact={}
    if foot_fields:
        ids=sorted({int(i) for f in foot_fields.values() for i in f.get('sole_vertices',f['vertices'])})
        if ids:
            fa,fb=surface_sampler(a,ids),surface_sampler(b,ids)
            for clip in ['Walk','Jog']:
                times=np.linspace(0,a.duration(clip),513);ta,qa,za,wa=a.sample(clip,times);tb,qb,zb,wb=b.sample(clip,times);delta=[]
                for k in range(len(times)):
                    va=fa(a.world(ta[k],qa[k],za[k]),{n:x[k] for n,x in wa.items()});vb=fb(b.world(tb[k],qb[k],zb[k]),{n:x[k] for n,x in wb.items()});delta.append(vb-va)
                delta=np.array(delta);speed=np.linalg.norm(np.diff(delta,axis=0),axis=2)/(times[1]-times[0]);reference=max((gait_speeds or {}).get(clip,0),height*.1)
                contact[clip]={'sole_vertices':len(ids),'samples':len(times),'max_surface_error_over_height':float(np.linalg.norm(delta,axis=2).max()/height),'p95_added_velocity_over_ground_speed':float(np.percentile(speed,95)/reference),'max_added_velocity_over_ground_speed':float(speed.max()/reference)}
    passed=maximum<.00015 and all(c['p95_added_velocity_over_ground_speed']<.05 for c in contact.values())
    return {'passed':passed,'source_sha256':digest(source),'runtime_sha256':digest(runtime),'rest_error_over_height':rest_error,'max_surface_error_over_height':maximum,'clips':clips,'contact_preservation':contact,'preserved':['geometry','topology','textures','materials','hierarchy','binds','rest transforms','native non-morph curves','native clip durations'],'interpretation':'Export fidelity and added sole velocity relative to reviewed source; not artistic acceptance.'}


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--source',required=True);p.add_argument('--runtime',required=True);p.add_argument('--height',type=float,required=True);p.add_argument('--report',required=True);a=p.parse_args()
    report=compare_runtime(a.source,a.runtime,a.height);Path(a.report).write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8');return 0 if report['passed'] else 1

if __name__=='__main__': raise SystemExit(main())
