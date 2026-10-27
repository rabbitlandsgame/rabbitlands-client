"""Offline regression checks for the installed, still-unreviewed creature drafts."""
from pathlib import Path
import json,argparse,sys
import numpy as np
from video_motion.native_shapes import NativeShapeAsset
from video_motion.asset import accessor,digest
from video_motion.runtime_validation import surface_sampler
ROOT=Path(__file__).resolve().parents[2]
read=lambda p:json.loads(p.read_text(encoding='utf-8'))


def numeric_limits(witness, vertices):
    """Keep defaults strict; explicitly bound fitted representation roundoff."""
    surface_limit=float(witness.get('surface_numeric_tolerance_over_height',1e-8))
    normal_limit=float(witness.get('normal_numeric_tolerance',1e-8))
    allowed_surface=allowed_normal=1e-7
    budget=witness.get('representation_numeric_budget')
    if budget is not None:
        ulps=budget.get('source_position_ulps',0)
        angle=float(budget.get('source_normal_angle_degrees',0.0))
        assert type(ulps) is int and 0<=ulps<=4 and 0.0<=angle<=.0001
        extent=max(float(np.max(np.abs(vertices))),float(np.ptp(vertices,axis=0).max()))
        if ulps:allowed_surface=max(allowed_surface,ulps*float(np.spacing(np.float32(extent)))/float(witness['height']))
        allowed_normal=max(allowed_normal,2.0*np.sin(np.deg2rad(angle)/2.0))
    assert 0<surface_limit<=allowed_surface*(1+1e-12) and 0<normal_limit<=allowed_normal*(1+1e-12)
    if surface_limit>1e-8 or normal_limit>1e-8:
        assert len(witness.get('reference_sha256',''))==64 and witness['reference_sha256']!=witness['sha256']
    return surface_limit,normal_limit

def normal_sampler(a,ids):
    fields=[];offset=0;primitives=[pr for n in a.d['nodes'] if 'mesh' in n for pr in a.d['meshes'][n['mesh']]['primitives']]
    for part,pr in zip(a.parts,primitives):
        take=np.flatnonzero((ids>=offset)&(ids<offset+len(part['position'])));ix=ids[take]-offset;offset+=len(part['position'])
        base=accessor(a.d,a.b,pr['attributes']['NORMAL'])[ix]
        targets=np.array([accessor(a.d,a.b,t['NORMAL'])[ix] if 'NORMAL' in t else np.zeros_like(base) for t in pr.get('targets',[])])
        fields.append((part,take,ix,base,targets))
    def sample(world,morph):
        result=np.zeros((len(ids),3))
        for part,take,ix,base,targets in fields:
            if not len(ix):continue
            local=base.copy();weights=morph.get(part['node'],a.default_weights[part['node']])
            if len(targets):local+=(weights@targets.reshape(len(targets),-1)).reshape(-1,3)
            if 'joints' not in part:out=local@world[part['node'],:3,:3].T
            else:
                transforms=world[part['nodes']]@part['bind'];out=np.zeros_like(base)
                for slot in range(part['weights'].shape[1]):out+=np.einsum('vij,vj->vi',transforms[part['joints'][ix,slot],:3,:3],local)*part['weights'][ix,slot,None]
            out/=np.maximum(np.linalg.norm(out,axis=1)[:,None],1e-20);result[take]=out
        return result
    return sample

def main():
    ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('--report',type=Path);ap.add_argument('--actor');args=ap.parse_args()
    actors=read(ROOT/'docs/qa/completed-creature-motion/actors.json');registry=read(ROOT/'godot-client/data/actors/models.json')['models'];results={}
    assert len(actors)==47
    for actor,p in actors.items():
        if args.actor and args.actor!=actor:continue
        a=NativeShapeAsset(ROOT/p['runtime_path']);w=read(ROOT/f'godot-client/tests/fixtures/completed-creature-motion/{actor}.json');entry=registry[actor];mapping=read(ROOT/'godot-client'/entry['animationMap'].removeprefix('res://'))
        assert digest(a.path)==p['sha256']==w['sha256'];assert p['human_approved'] is False and mapping['reviewStatus']=='draft_needs_review'
        assert {'Idle_A','Fighting_Idle','Hit_Chest','Walk','Jog','Sword_Attack','Death_A'}<=set(a.animations)
        assert set(a.animations)==set(w['clips']);assert all(c in a.animations for c in mapping['actions'].values())
        assert entry['scene']==entry['animationLibrary'];assert all(v in a.ids for v in entry['attachments'].values())
        assert mapping['actions']['attack_primary']=='Sword_Attack' and mapping['actions']['death']=='Death_A'
        assert all(mapping['playbackSpeeds'][action]==1 for action in ['walk','run','attack_primary','death'])
        for action,clip in [('walk','Walk'),('run','Jog')]:
            if p['gaits']:
                g=p['gaits'][clip];assert abs(mapping['strideMetresPerSecond'][action]-g['stride']/g['duration']*entry['import']['scale'])<1e-10
        if 'walk_speed_native' in p:assert abs(mapping['strideMetresPerSecond']['walk']-p['walk_speed_native']*entry['import']['scale'])<1e-10
        assert a.d['asset']['extras']['rabbitlands_animation_bake_fps']==p['bake_fps']
        policy=Path(str(a.path)+'.import').read_text(encoding='utf-8');assert 'animation/fps='+str(p['bake_fps']) in policy and 'meshes/force_disable_compression=true' in policy and '"optimizer/enabled": false' in policy and '"compression/enabled": false' in policy
        for mesh in a.d['meshes']:
            for pr in mesh['primitives']:
                for name,ai in pr['attributes'].items():
                    if name.startswith('JOINTS_'):assert a.d['accessors'][ai]['componentType'] in [5121,5123] and a.d['accessors'][ai]['type']=='VEC4'
        assert max(int((part['weights']>1e-8).sum(1).max()) for part in a.parts if 'weights' in part)<=8
        ids=np.array(w['surface_vertex_ids']);sample=surface_sampler(a,ids);normal=normal_sampler(a,ids);se=ne=be=0.
        for clip,entries in w['clips'].items():
            assert abs(a.duration(clip)-w['durations'][clip])<1e-10
            t,q,s,m=a.sample(clip,[x['time'] for x in entries])
            for k,probe in enumerate(entries):
                world=a.world(t[k],q[k],s[k]);mm={n:v[k] for n,v in m.items()};se=max(se,float(np.linalg.norm(sample(world,mm)-probe['surface'],axis=1).max()/p['height']));ne=max(ne,float(np.linalg.norm(normal(world,mm)-probe['surface_normals'],axis=1).max()))
                for name,values in probe['bones'].items():be=max(be,float(np.max(abs(world[a.ids[name]]-np.array(values).reshape(4,4)))))
        # Physical observations remain immutable. Flat creatures use a bounded
        # float32 coordinate budget, rather than magnifying it by small height.
        surface_limit,normal_limit=numeric_limits(w,a.vertices)
        assert se<surface_limit and ne<normal_limit and be<1e-9,(actor,se,ne,be)
        results[actor]={'passed':True,'sha256':p['sha256'],'reference_sha256':w.get('reference_sha256',w['sha256']),'clips':len(w['clips']),'surface_probes':len(ids),'surface_error_over_height':se,'normal_error':ne,'bone_error':be,'surface_numeric_tolerance_over_height':surface_limit,'normal_numeric_tolerance':normal_limit}
        print('NATIVE_CREATURE_PASS',actor,flush=True)
    report={'passed':True,'actors':results,'scope':'Exact installed hash, seven mapped slots plus retained native clips, import cadence, unsigned joint storage, influence budget, current attachments, travel-speed metadata and independent off-grid native bone/surface/normal witnesses. Artistic review remains pending.'}
    if args.report:args.report.write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8')
    print('COMPLETED_CREATURE_NATIVE_PASS',len(results),flush=True)
if __name__=='__main__':main()
