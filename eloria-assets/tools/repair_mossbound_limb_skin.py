"""Explicit, unapproved Mossbound Golem forearm/calf skin-weight experiment.

Keep the accepted fixed geometry, curves, rig and eight-slot budget. Apply a
bounded anatomical ownership cleanup with a spatial boundary fade. This is a
partial local repair requiring client/Blender/visual review, not a fidelity pass.
The positive-X source-named left chains identify the selected anatomy; screen
right/left depends on the review camera and must not be inferred from names.
"""
from pathlib import Path
import argparse,json
import numpy as np
from video_motion.asset import read_glb,write_glb,digest,accessor
from video_motion.native_shapes import NativeShapeAsset
from video_motion.creature_storage import _array,_append,_compact_reachable
from add_creature_bake_helpers import _curve_signature


def budget(weights, slots=8):
    result=np.asarray(weights,float).copy()
    if np.any(result<0) or not np.isfinite(result).all():
        raise ValueError('Finite nonnegative skin coefficients required')
    for row in result:
        keep=np.argsort(row)[-slots:]
        row[np.setdiff1d(np.arange(len(row)),keep)]=0
        if row.sum()<=0:raise ValueError('Empty skin support')
        row/=row.sum()
    return result


def dense(part):
    result=np.zeros((len(part['position']),len(part['nodes'])))
    for slot in range(part['joints'].shape[1]):
        np.add.at(result,(np.arange(len(result)),part['joints'][:,slot]),part['weights'][:,slot])
    return result


def repair(reference, baseline, output, *, strength=.25, report=None):
    reference,baseline,output=map(lambda x:Path(x).resolve(),(reference,baseline,output))
    if output.exists() or output in (reference,baseline):
        raise ValueError('Use a new versioned output; inputs are immutable')
    if not 0<strength<=1:raise ValueError('Explicit bounded strength in (0,1] required')
    hashes={str(path):digest(path)for path in (reference,baseline)}
    source=NativeShapeAsset(reference);asset=NativeShapeAsset(baseline)
    if len(source.parts)!=1 or len(asset.parts)!=1:raise ValueError('Audited single-body correspondence required')
    part=asset.parts[0];sp=source.parts[0]
    if len(asset.vertices)!=9000 or len(part['nodes'])!=30 or part['joints'].shape[1]!=8:
        raise ValueError('Audited Mossbound topology/palette/influence layout changed')
    if not np.array_equal(part['nodes'],sp['nodes']):raise ValueError('Original joint identities differ')
    if any(len(m.get('weights',[]))for m in asset.d['meshes']) or any(
            primitive.get('targets')for m in asset.d['meshes']for primitive in m['primitives']):
        raise ValueError('Baseline must already have zero corrective targets')
    document,blob=read_glb(baseline);blob=bytearray(blob)
    primitive=document['meshes'][document['nodes'][part['node']]['mesh']]['primitives'][0]
    faces=accessor(document,blob,primitive['indices']).astype(int).reshape(-1,3)
    edges=np.unique(np.sort(np.r_[faces[:,[0,1]],faces[:,[1,2]],faces[:,[2,0]]],axis=1),axis=0)
    _,reps,group=np.unique(sp['position'][:,:3],axis=0,return_index=True,return_inverse=True)
    # The active baseline has no morphs: equal local positions and complete
    # dense skin coefficients prove equal trajectories for arbitrary poses.
    # The corrective reference supplies anatomy, not a new seam tolerance.
    if not np.array_equal(part['position'],part['position'][reps[group]]):
        raise ValueError('Reference rest contacts differ in the active baseline')
    baseline_dense=dense(part)
    if not np.array_equal(baseline_dense,baseline_dense[reps[group]]):
        raise ValueError('Coincident baseline points have different skin motion')
    members=[np.flatnonzero(group==i)for i in range(len(reps))]
    physical_edges=np.unique(np.sort(group[edges],axis=1),axis=0)
    adjacency=[set()for _ in reps]
    for i,j in physical_edges:
        if i!=j:adjacency[i].add(j);adjacency[j].add(i)
    weights=baseline_dense[reps];source_weights=dense(sp)[reps]
    names={asset.names[n]:i for i,n in enumerate(part['nodes'])}
    arm=[names[n]for n in ['upperarm_l','lowerarm_l','hand_l','RL_left_2_skin_blend','RL_left_1_skin_blend']]
    leg=[names[n]for n in ['thigh_l','calf_l','foot_l','ball_l','ball_leaf_l']]
    hip=names['pelvis'];x,y=asset.vertices[reps,0],asset.vertices[reps,1]
    armmask=(x>.11)&(y<.23)&(y>-.18)&(source_weights[:,arm].sum(1)>.35)
    legmask=(x>.02)&(y<-.06)&(y>-.44)&(source_weights[:,leg].sum(1)>.4)
    armalpha=np.clip((x-.11)/.07,0,1)*np.clip((.23-y)/.07,0,1)*np.clip((y+.18)/.08,0,1)*armmask
    legalpha=np.clip((x-.02)/.05,0,1)*np.clip((-.06-y)/.08,0,1)*np.clip((y+.44)/.08,0,1)*legmask
    selected=(armalpha>0)|(legalpha>0);proposed=weights.copy()
    for i in np.flatnonzero(selected):
        allowed=arm if armalpha[i]>0 else leg+([hip]if y[i]>-.14 else[])
        clean=np.zeros(weights.shape[1]);good=weights[i,allowed].copy();good/=good.sum();clean[allowed]=good
        alpha=max(armalpha[i],legalpha[i]);proposed[i]=(1-alpha)*weights[i]+alpha*clean
    for _ in range(2):
        updated=proposed.copy()
        for i in np.flatnonzero(selected):
            updated[i]=.8*proposed[i]+.2*np.mean(proposed[list(adjacency[i])],axis=0)
        proposed=updated
    proposed[selected]=budget(proposed[selected])
    fitted=budget((1-strength)*weights[selected]+strength*proposed[selected])
    groups=np.flatnonzero(selected);ids=np.concatenate([members[g]for g in groups]);outside=np.setdiff1d(np.arange(9000),ids)
    attrs=primitive['attributes']
    joints=np.c_[_array(document,blob,attrs['JOINTS_0']),_array(document,blob,attrs['JOINTS_1'])]
    stored_weights=np.c_[_array(document,blob,attrs['WEIGHTS_0']),_array(document,blob,attrs['WEIGHTS_1'])]
    for i,g in enumerate(groups):
        order=np.argsort(-fitted[i])[:8]
        joints[members[g]]=order.astype(joints.dtype)
        stored_weights[members[g]]=fitted[i,order].astype(stored_weights.dtype)
    for name,values in [('JOINTS_0',joints[:,:4]),('JOINTS_1',joints[:,4:]),
                        ('WEIGHTS_0',stored_weights[:,:4]),('WEIGHTS_1',stored_weights[:,4:])]:
        attrs[name]=_append(document,blob,values,document['accessors'][attrs[name]])
    document,blob=_compact_reachable(document,blob);write_glb(output,document,blob)
    new=NativeShapeAsset(output);old_d,old_b=read_glb(baseline);new_d,new_b=read_glb(output)
    old_p=old_d['meshes'][old_d['nodes'][part['node']]['mesh']]['primitives'][0]
    new_p=new_d['meshes'][new_d['nodes'][part['node']]['mesh']]['primitives'][0]
    for name,index in old_p['attributes'].items():
        old_values,new_values=_array(old_d,old_b,index),_array(new_d,new_b,new_p['attributes'][name])
        assert old_values[outside].tobytes()==new_values[outside].tobytes()
        if not name.startswith(('JOINTS_','WEIGHTS_')):assert old_values.tobytes()==new_values.tobytes()
    assert _array(old_d,old_b,old_p['indices']).tobytes()==_array(new_d,new_b,new_p['indices']).tobytes()
    assert old_d['nodes']==new_d['nodes']and old_d['materials']==new_d['materials']
    assert _curve_signature(asset)==_curve_signature(new)
    assert np.array_equal(part['bind'],new.parts[0]['bind'])
    assert all(digest(Path(path))==sha for path,sha in hashes.items())
    result={'status':'unapproved_local_skin_repair_draft','actor':'mossbound_stone_golem',
        'reference_sha256':digest(reference),'baseline_sha256':digest(baseline),
        'candidate_sha256':digest(output),'baseline_bytes':baseline.stat().st_size,
        'candidate_bytes':output.stat().st_size,'strength':strength,'coincident_groups':len(groups),
        'changed_original_vertex_ids':ids.tolist(),'outside_vertices':len(outside),
        'original_geometry_uv_topology_curves_nodes_binds_materials_preserved':True,
        'influence_slots':8,'palette_bones':30,'helpers_added':0,'corrective_targets':0,
        'baseline_coincident_position_and_dense_skin_exact':True,
        'selection':'Positive-X source-named left forearm/calf; source ownership and rest-space gates; complete original coincident groups. Distal soles excluded.',
        'limits':['Partial local proposal, not automatic improvement across every pose.',
                  'Measure actual-client selected/outside motion, edge strain, support, normals and all native clips/blends independently.',
                  'Fresh Blender and version-bound visual review required; no runtime installation.']}
    if report is not None:Path(report).write_text(json.dumps(result,indent=2)+'\n',encoding='utf-8')
    return result


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    for name in ('reference','baseline','output'):parser.add_argument('--'+name,type=Path,required=True)
    parser.add_argument('--strength',type=float,default=.25);parser.add_argument('--report',type=Path)
    args=parser.parse_args();print(json.dumps(repair(args.reference,args.baseline,args.output,strength=args.strength,report=args.report),indent=2))
