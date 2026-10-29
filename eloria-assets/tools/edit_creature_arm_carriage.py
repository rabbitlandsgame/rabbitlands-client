"""Create an unapproved, explicitly selected arm-carriage clip variant.

Only an audited upper-arm quaternion curve is changed. Existing clocks, rest,
mesh/skin, other curves and original bones remain. This is an authoring edit,
not a lossless optimization or automatic anatomical/visual approval.
"""
from pathlib import Path
import argparse,json
import numpy as np
from scipy.spatial.transform import Rotation
from video_motion.asset import read_glb,write_glb,accessor,digest
from video_motion.native_shapes import NativeShapeAsset
from video_motion.creature_storage import _array,_append,_compact_reachable
from add_creature_bake_helpers import _curve_signature


def swing(current, goal, maximum_degrees):
    current=np.asarray(current,float).copy();goal=np.asarray(goal,float).copy()
    if not np.isfinite([current,goal]).all() or min(np.linalg.norm(current),np.linalg.norm(goal))<1e-12:
        raise ValueError('Finite nonzero direction vectors required')
    current/=np.linalg.norm(current);goal/=np.linalg.norm(goal)
    axis=np.cross(current,goal);sine=np.linalg.norm(axis);cosine=np.dot(current,goal)
    if sine<1e-12 and cosine<0:raise ValueError('Antiparallel swing needs an explicit anatomical plane')
    angle=min(np.arctan2(sine,cosine),np.deg2rad(maximum_degrees))
    return Rotation.from_rotvec(axis/max(sine,1e-20)*angle),float(np.degrees(angle))


def edit(source, output, *, clip, upper, child, toward_rest=.55, maximum_degrees=25., report=None):
    source,output=Path(source).resolve(),Path(output).resolve()
    if output.exists() or source==output:raise ValueError('Use a new versioned output')
    if not 0<toward_rest<=1 or not 0<maximum_degrees<90:raise ValueError('Explicit bounded authoring parameters required')
    source_hash=digest(source);asset=NativeShapeAsset(source)
    if upper not in asset.joints or child not in asset.joints or asset.parent[child]!=upper:
        raise ValueError('Explicit original upper-arm/child joint correspondence required')
    parent=int(asset.parent[upper])
    if parent<0:raise ValueError('Arm root must have an audited original parent')
    d,binary=read_glb(source);binary=bytearray(binary)
    animation=next(a for a in d['animations']if a['name']==clip)
    channel=next(c for c in animation['channels']if c['target']=={'node':upper,'path':'rotation'})
    sampler=animation['samplers'][channel['sampler']]
    if sampler.get('interpolation','LINEAR')!='LINEAR':raise ValueError('Continuous quaternion curve required')
    times=accessor(d,binary,sampler['input']).ravel()
    if len(times)>1 and (np.diff(times)<=0).any():raise ValueError('Strictly increasing clock required')
    if len(times)>1 and float(np.max(1/np.diff(times)))>30.0001:
        raise ValueError('Use an explicitly sampled delivery clock at or below30Hz')
    t,q,s,_=asset.sample(clip,times)
    rest_direction=asset.rest[child,:3,3]-asset.rest[upper,:3,3]
    rest_local_parent=np.linalg.inv(asset.rest[parent,:3,:3])@rest_direction
    new=[];angles=[];keep=float(format(1-toward_rest,'.15g'))
    for k,time in enumerate(times):
        world=asset.world(t[k],q[k],s[k]);basis=world[parent,:3,:3]
        normalized=basis/np.linalg.norm(basis,axis=0)
        if np.max(abs(normalized.T@normalized-np.eye(3)))>1e-5 or np.linalg.det(basis)<=0:
            raise ValueError('Sheared/reflected animated parent needs an explicit rig solution')
        parent_rotation=Rotation.from_matrix(basis)
        current=world[child,:3,3]-world[upper,:3,3];current/=np.linalg.norm(current)
        rest=parent_rotation.apply(rest_local_parent);rest/=np.linalg.norm(rest)
        goal=keep*current+toward_rest*rest;goal/=np.linalg.norm(goal)
        delta,angle=swing(current,goal,maximum_degrees)
        new.append((parent_rotation.inv()*delta*parent_rotation*Rotation.from_quat(q[k,upper])).as_quat());angles.append(angle)
    new=np.array(new)
    for k in range(1,len(new)):
        if new[k-1]@new[k]<0:new[k]*=-1
    if sum(c['sampler']==channel['sampler']for c in animation['channels'])>1:
        sampler=dict(sampler);animation['samplers'].append(sampler);channel['sampler']=len(animation['samplers'])-1
    sampler['output']=_append(d,binary,new.astype('<f4'),d['accessors'][sampler['output']])
    d,binary=_compact_reachable(d,binary);write_glb(output,d,binary);candidate=NativeShapeAsset(output)
    for old,changed in zip(_curve_signature(asset),_curve_signature(candidate)):
        if old[0]==clip and old[1]=={'node':upper,'path':'rotation'}:continue
        assert old==changed
    assert asset.d['nodes']==candidate.d['nodes']and np.array_equal(asset.rest,candidate.rest)
    assert len(asset.parts)==len(candidate.parts)
    for old,newpart in zip(asset.parts,candidate.parts):
        for key in ['position','joints','weights','bind','nodes']:
            if key in old:assert np.array_equal(old[key],newpart[key])
    assert all(asset.duration(name)==candidate.duration(name)for name in asset.animations)
    assert digest(source)==source_hash
    result={'status':'unapproved_arm_carriage_authoring_draft','baseline_sha256':source_hash,
        'candidate_sha256':digest(output),'baseline_bytes':source.stat().st_size,
        'candidate_bytes':output.stat().st_size,'clip':clip,'upper_node':upper,'child_node':child,
        'toward_parent_relative_rest':toward_rest,'maximum_degrees':maximum_degrees,
        'measured_maximum_rotation_change_degrees':max(angles),'existing_keys':len(times),
        'added_keys':0,'added_bones':0,'original_nodes_rest_skin_mesh_other_curves_exact':True,
        'limits':['Anatomical node identity must be established before calling this tool.',
                  'Skin leakage can move distant surfaces: inspect actual feet, canopy and contacts.',
                  'Independent client default/RESET/blends, fresh import and multi-angle full-cycle visual review required.']}
    if report is not None:Path(report).write_text(json.dumps(result,indent=2)+'\n',encoding='utf-8')
    return result


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    for name in ['source','output']:parser.add_argument('--'+name,type=Path,required=True)
    parser.add_argument('--clip',required=True);parser.add_argument('--upper',type=int,required=True);parser.add_argument('--child',type=int,required=True)
    parser.add_argument('--toward-rest',type=float,default=.55);parser.add_argument('--maximum-degrees',type=float,default=25.)
    parser.add_argument('--report',type=Path);args=parser.parse_args()
    print(json.dumps(edit(args.source,args.output,clip=args.clip,upper=args.upper,child=args.child,toward_rest=args.toward_rest,maximum_degrees=args.maximum_degrees,report=args.report),indent=2))
