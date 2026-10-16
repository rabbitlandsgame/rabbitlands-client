"""Explicit, localized skin repair kept separate from motion fitting."""
from __future__ import annotations
import copy
import json
from pathlib import Path
import numpy as np
from scipy.spatial import cKDTree
from .asset import Asset,accessor,write_glb,digest,DTYPES


def repair_dorsal_neck(source, output, report_path):
    """Remove reviewed leg influences from the Moorland dorsal neck only.

    Keep torso/fur influences and smooth the reviewed central mane's neck/chest
    transition. Where no valid influences remain, interpolate nearby torso
    weights in rest space. Coincident seam vertices get identical repaired
    weights. This region is actor-specific, not a generic skinning rule.
    """
    a=Asset(source)
    document=copy.deepcopy(a.document)
    blob=bytearray(a.blob)
    if len(a.parts)!=1:
        raise ValueError('The reviewed Moorland repair requires one mesh primitive')
    part=a.parts[0]
    attrs=document['meshes'][document['nodes'][part['node']]['mesh']]['primitives'][0]['attributes']
    if 'JOINTS_1' in attrs or part['joints'].shape[1]!=4:
        raise ValueError('Review multi-set influences before adapting this four-influence repair')
    positions=a.rest_vertices
    region=(positions[:,1]>1.27)&(positions[:,2]>.20)&(positions[:,2]<.85)
    forbidden=np.array([n.startswith(('Front_Leg_','Back_Leg_')) for n in a.names])
    node_ids=part['nodes'][part['joints']]
    bad=forbidden[node_ids]
    wrong_mass=np.sum(part['weights']*bad,axis=1)
    changed=region&(wrong_mass>1e-6)
    if not np.any(changed):
        raise ValueError('No reviewed neck/leg influence defect found')
    dense=np.zeros((len(positions),len(part['nodes'])))
    for col in range(4):
        np.add.at(dense,(np.arange(len(positions)),part['joints'][:,col]),part['weights'][:,col]*(~bad[:,col]))
    valid_mass=dense.sum(1)
    donors=np.flatnonzero(region&(valid_mass>.05))
    tree=cKDTree(positions[donors])
    repaired=dense.copy()
    fallback=[]
    for i in np.flatnonzero(changed):
        if valid_mass[i]>.05:
            repaired[i]/=valid_mass[i]
        else:
            distances,near=tree.query(positions[i],k=min(8,len(donors)))
            if np.max(distances)>.30*a.height:
                raise ValueError('A fully misweighted neck vertex lacks nearby reviewed donors')
            donor_ids=donors[np.atleast_1d(near)]
            weights=1/np.maximum(np.atleast_1d(distances),.002*a.height)**2
            repaired[i]=np.average(dense[donor_ids]/valid_mass[donor_ids,None],axis=0,weights=weights)
            fallback.append(int(i))
    # The top central tuft also had abrupt 0/100% neck-vs-chest weights on
    # adjacent corners. Smooth a continuous spatial blend over this reviewed
    # mane region, leaving head/ear ownership and the shoulder boundary alone.
    def smoothstep(x):
        x=np.clip(x,0,1)
        return x*x*(3-2*x)
    neck_index=int(np.flatnonzero(part['nodes']==a.name_to_id['Spine_3'])[0])
    chest_index=int(np.flatnonzero(part['nodes']==a.name_to_id['Spine_2001'])[0])
    head_ear=np.array([a.names[n].startswith('Ear_') or a.names[n]=='Head' for n in part['nodes']])
    protected=(dense[:,head_ear].sum(1)>.15)
    alpha=smoothstep((positions[:,1]-1.40)/.18)*smoothstep((.30-np.abs(positions[:,0]))/.12)
    alpha*=region&(~protected)
    blend_ids=np.flatnonzero(alpha>1e-6)
    for i in blend_ids:
        base=repaired[i].copy()
        base/=base.sum()
        body=base.copy()
        body[neck_index]=0
        if body.sum()<1e-6:
            body[chest_index]=1
        body/=body.sum()
        fraction=float(smoothstep((positions[i,2]-.50)/.45))
        desired=body*(1-fraction)
        desired[neck_index]=fraction
        repaired[i]=(1-alpha[i])*base+alpha[i]*desired
        changed[i]=True
    # Shared spatial vertices can be split by UV or normal seams. Make the
    # local repair coherent across those duplicates without welding geometry.
    groups={}
    for i in np.flatnonzero(changed):
        groups.setdefault(tuple(np.round(positions[i],6)),[]).append(i)
    for ids in groups.values():
        repaired[ids]=repaired[ids].mean(0)
    new_joints=part['joints'].copy()
    new_weights=part['weights'].copy()
    for i in np.flatnonzero(changed):
        order=np.argsort(repaired[i])[-4:][::-1]
        weights=repaired[i,order]
        new_joints[i]=order
        new_weights[i]=weights/weights.sum()
    def append(values,component_type,kind):
        nonlocal blob
        dtype=np.dtype('<'+DTYPES[component_type])
        values=np.ascontiguousarray(values,dtype=dtype)
        blob.extend(b'\0'*(-len(blob)%4))
        offset=len(blob)
        blob.extend(values.tobytes())
        document['bufferViews'].append({'buffer':0,'byteOffset':offset,'byteLength':values.nbytes})
        document['accessors'].append({'bufferView':len(document['bufferViews'])-1,
            'componentType':component_type,'count':len(values),'type':kind})
        return len(document['accessors'])-1
    joint_type=a.document['accessors'][attrs['JOINTS_0']]['componentType']
    attrs['JOINTS_0']=append(new_joints,joint_type,'VEC4')
    attrs['WEIGHTS_0']=append(new_weights,5126,'VEC4')
    document.setdefault('extras',{})['localized_skin_repair']={
        'original_sha256':digest(source),'changed_vertices':int(changed.sum()),
        'region':'Reviewed dorsal neck: rest Y>1.27, .20<Z<.85; native actor units',
        'method':'Remove limb influences; preserve/normalize torso/fur weights; local donors where none remain; smooth the reviewed central mane neck/chest transition'}
    write_glb(output,document,blob)
    b=Asset(output)
    other_keys=('nodes','skins','materials','textures','images','animations')
    unchanged={k:a.document.get(k)==b.document.get(k) for k in other_keys}
    rest_error=float(np.max(np.abs(a.rest_vertices-b.rest_vertices)))
    untouched=~changed
    report={'original_sha256':digest(source),'repaired_sha256':digest(output),
        'changed_vertex_ids':np.flatnonzero(changed).tolist(),'changed_vertex_count':int(changed.sum()),
        'mane_transition_processed_vertex_count':len(blend_ids),
        'fully_misweighted_vertex_ids_requiring_donors':fallback,
        'wrong_limb_mass_before_max':float(wrong_mass[region].max()),
        'wrong_limb_mass_after_max':float(np.sum(b.parts[0]['weights']*forbidden[b.parts[0]['nodes'][b.parts[0]['joints']]],axis=1)[region].max()),
        'outside_region_weights_and_joints_unchanged':bool(np.array_equal(part['weights'][untouched],b.parts[0]['weights'][untouched]) and np.array_equal(part['joints'][untouched],b.parts[0]['joints'][untouched])),
        'rest_surface_max_error':rest_error,'unchanged':unchanged,
        'position_normal_uv_index_accessors_unchanged':all(a.document['meshes'][0]['primitives'][0]['attributes'].get(k)==attrs.get(k) for k in ('POSITION','NORMAL','TEXCOORD_0')) and a.document['meshes'][0]['primitives'][0].get('indices')==document['meshes'][0]['primitives'][0].get('indices'),
        'repair_scope':'Skin influences only in reviewed dorsal neck; rest geometry, rig and animation curves preserved. Appearance of other clips can improve/change with the repaired skin.'}
    report['repair_pass']=all(unchanged.values()) and rest_error<1e-5*a.height and report['outside_region_weights_and_joints_unchanged'] and report['wrong_limb_mass_after_max']<1e-6 and report['position_normal_uv_index_accessors_unchanged']
    Path(report_path).parent.mkdir(parents=True,exist_ok=True)
    Path(report_path).write_text(json.dumps(report,indent=2))
    if not report['repair_pass']:
        raise ValueError('Localized skin repair failed preservation checks')
    return report


def evaluate_neck_deformation(asset,reference_asset,clip='Walk',fps=192):
    """Compare dorsal neck edge stretch and motion relative to the chest.

    Each actor uses identical geometry. This tests the skin independently from
    paw contact/articulation gates, which cannot detect a misweighted mane.
    """
    v=reference_asset.rest_vertices
    region=(v[:,1]>1.27)&(v[:,2]>.20)&(v[:,2]<.85)
    face=reference_asset.parts[0]['indices']
    edges=np.unique(np.sort(np.concatenate([face[:,[0,1]],face[:,[1,2]],face[:,[2,0]]]),1),axis=0)
    edges=edges[np.all(region[edges],axis=1)]
    rest=np.linalg.norm(v[edges[:,0]]-v[edges[:,1]],axis=1)
    keep=rest>.02
    edges,rest=edges[keep],rest[keep]
    times=np.linspace(0,asset.duration(clip),round(asset.duration(clip)*fps)+1)
    t,q=asset.sample(clip,times)
    stretches=[]
    for ti,qi in zip(t,q):
        p=asset.skin(asset.world(ti,qi))
        stretches.append(np.linalg.norm(p[edges[:,0]]-p[edges[:,1]],axis=1)/rest)
    ratios=np.asarray(stretches)
    return {'export_sha256':digest(asset.path),'clip':clip,'sampling_fps':fps,
        'reviewed_region_vertices':int(region.sum()),'reviewed_edges':len(edges),
        'maximum_edge_length_ratio':float(ratios.max()),
        'minimum_edge_length_ratio':float(ratios.min()),
        'edge_length_ratio_p99':float(np.quantile(ratios,.99)),
        'deformation_pass':bool(ratios.max()<1.25 and ratios.min()>.75),
        'measurement':'Dorsal neck triangle edges >.02 native units; ratios against unchanged rest geometry. Declared pilot gate, supplemented by side/front/rear renders.'}


def repair_collar_back(source,output,reviewed_components,report_path):
    """Rebind reviewed collar shells rigidly to the neck; calm dorsal skin.

    This source-specific repair uses explicit reviewed component vertex IDs,
    not a color threshold during mutation. The accepted limb rig/motion is
    untouched. Upper-back leg/tail influences are replaced by torso ownership.
    """
    a=Asset(source)
    if len(a.parts)!=1 or a.parts[0]['joints'].shape[1]!=4:
        raise ValueError('Review this repair for other mesh/influence layouts')
    part=a.parts[0]
    document=copy.deepcopy(a.document)
    blob=bytearray(a.blob)
    attrs=document['meshes'][document['nodes'][part['node']]['mesh']]['primitives'][0]['attributes']
    joints,weights=part['joints'].copy(),part['weights'].copy()
    collar=np.array(sorted({i for c in reviewed_components for i in c['vertex_ids']}),int)
    neck_index=int(np.flatnonzero(part['nodes']==a.name_to_id['Spine_3'])[0])
    joints[collar]=neck_index
    weights[collar]=[1,0,0,0]
    v=a.rest_vertices
    back=(v[:,1]>1.30)&(v[:,2]>-.70)&(v[:,2]<.20)
    wrong=np.array([n.startswith(('Front_Leg_','Back_Leg_','Tail_')) for n in a.names])
    bad=wrong[part['nodes'][part['joints']]]
    wrong_mass=np.sum(part['weights']*bad,axis=1)
    back_ids=np.flatnonzero(back&(wrong_mass>1e-6))
    dense=np.zeros((len(v),len(part['nodes'])))
    for col in range(4):
        np.add.at(dense,(np.arange(len(v)),part['joints'][:,col]),part['weights'][:,col]*(~bad[:,col]))
    valid=dense.sum(1)
    donors=np.flatnonzero(back&(valid>.05))
    tree=cKDTree(v[donors])
    for i in back_ids:
        row=dense[i].copy()
        if valid[i]>.05:
            row/=valid[i]
        else:
            dist,near=tree.query(v[i],k=min(8,len(donors)))
            ids=donors[np.atleast_1d(near)]
            if np.max(dist)>.30*a.height:
                raise ValueError('The reviewed dorsal back lacks nearby torso donors')
            row=np.average(dense[ids]/valid[ids,None],axis=0,weights=1/np.maximum(np.atleast_1d(dist),.002*a.height)**2)
        order=np.argsort(row)[-4:][::-1]
        joints[i]=order
        weights[i]=row[order]/row[order].sum()
    # Coherent duplicate seam influences, without changing geometry/topology.
    grouped={}
    for i in back_ids:
        grouped.setdefault(tuple(np.round(v[i],6)),[]).append(i)
    for ids in grouped.values():
        ref=ids[0]
        joints[ids]=joints[ref]
        weights[ids]=weights[ref]
    def append(values,component_type):
        values=np.ascontiguousarray(values,dtype=np.dtype('<'+DTYPES[component_type]))
        blob.extend(b'\0'*(-len(blob)%4))
        offset=len(blob)
        blob.extend(values.tobytes())
        document['bufferViews'].append({'buffer':0,'byteOffset':offset,'byteLength':values.nbytes})
        document['accessors'].append({'bufferView':len(document['bufferViews'])-1,'componentType':component_type,'count':len(values),'type':'VEC4'})
        return len(document['accessors'])-1
    attrs['JOINTS_0']=append(joints,a.document['accessors'][attrs['JOINTS_0']]['componentType'])
    attrs['WEIGHTS_0']=append(weights,5126)
    changed=np.zeros(len(v),bool)
    changed[collar]=True
    changed[back_ids]=True
    document.setdefault('extras',{})['collar_back_skin_repair']={
        'input_sha256':digest(source),'collar_vertices':len(collar),'back_vertices':len(back_ids),
        'collar_attachment':'Spine_3; one rigid influence per reviewed shell',
        'back_policy':'Remove limb/tail influences only in reviewed dorsal torso; retain native torso/fur influence ratios'}
    write_glb(output,document,blob)
    b=Asset(output)
    untouched=~changed
    other=('nodes','skins','materials','images','textures','animations')
    unchanged={k:a.document.get(k)==b.document.get(k) for k in other}
    after=b.parts[0]
    rest_error=float(np.max(np.abs(a.rest_vertices-b.rest_vertices)))
    report={'input_sha256':digest(source),'repaired_sha256':digest(output),
        'collar_components':reviewed_components,'collar_vertex_ids':collar.tolist(),
        'collar_vertex_count':len(collar),'back_vertex_ids':back_ids.tolist(),'back_vertex_count':len(back_ids),
        'changed_vertex_ids':np.flatnonzero(changed).tolist(),'changed_vertex_count':int(changed.sum()),
        'outside_repair_weights_and_joints_unchanged':bool(np.array_equal(part['weights'][untouched],after['weights'][untouched]) and np.array_equal(part['joints'][untouched],after['joints'][untouched])),
        'rest_surface_max_error':rest_error,'unchanged':unchanged,
        'collar_rigid_neck_attachment_pass':bool(np.all(after['joints'][collar,0]==neck_index) and np.all(after['weights'][collar,0]==1)),
        'back_unwanted_limb_tail_mass_after_max':float(np.sum(after['weights']*wrong[after['nodes'][after['joints']]],axis=1)[back].max()),
        'policy':'Actor-specific attachment repair; source leg transforms and geometry unchanged; other clips retain curves but their skin deformation can change.'}
    report['repair_pass']=all(unchanged.values()) and report['outside_repair_weights_and_joints_unchanged'] and rest_error<1e-5*a.height and report['collar_rigid_neck_attachment_pass'] and report['back_unwanted_limb_tail_mass_after_max']<1e-6
    Path(report_path).parent.mkdir(parents=True,exist_ok=True)
    Path(report_path).write_text(json.dumps(report,indent=2))
    if not report['repair_pass']:
        raise ValueError('Collar/back repair failed preservation checks')
    return report
