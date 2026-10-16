"""Explicit tail-only rest-pose correction, skin baking, and native rebinding."""
import copy,json
from pathlib import Path
import numpy as np
from scipy.spatial.transform import Rotation
from .asset import Asset,accessor,digest,write_glb


def center_hanging_tail(source,output,report_path):
    a=Asset(source)
    chain=[a.name_to_id[n] for n in ('Tail_Base','Tail_Mid','Tail_Mid001','Tail_End','Tail_Tip','Bone_020')]
    if len(a.parts)!=1 or any(a.parent[c]!=p for p,c in zip(chain,chain[1:])):
        raise ValueError('Review the native serial chain and mesh layout before tail rest correction')
    if any(set(np.flatnonzero(a.parent==p))-set(chain) for p in chain):
        raise ValueError('Tail subtree contains an unreviewed branch')
    world=a.world_rest.copy()
    angles=[]
    for parent,child in zip(chain,chain[1:]):
        v=a.world_rest[child,:3,3]-a.world_rest[parent,:3,3]
        angle=-np.pi/2-np.arctan2(v[1],v[0])
        delta=Rotation.from_rotvec([0,0,angle]).as_matrix()
        world[parent,:3,:3]=delta@a.world_rest[parent,:3,:3]
        world[child,:3,3]=world[parent,:3,3]+np.array([0,-np.hypot(v[0],v[1]),v[2]])
        angles.append(float(angle))
    # The small weighted fur helper follows the terminal section's orientation.
    world[chain[-1],:3,:3]=Rotation.from_rotvec([0,0,angles[-2]]).as_matrix()@a.world_rest[chain[-1],:3,:3]
    nt,nq=a.t.copy(),a.q.copy()
    for node in chain:
        local=np.linalg.solve(world[a.parent[node]],world[node])
        nt[node]=local[:3,3]
        nq[node]=Rotation.from_matrix(local[:3,:3]/a.s[node]).as_quat()
    part=a.parts[0]
    mass=np.sum(np.isin(part['nodes'][part['joints']],chain)*part['weights'],axis=1)
    changed=np.flatnonzero(mass>1e-8)
    posed=a.skin(world)
    document=copy.deepcopy(a.document);blob=bytearray(a.blob)
    def append(values,kind):
        values=np.ascontiguousarray(values,dtype='<f4')
        blob.extend(b'\0'*(-len(blob)%4));offset=len(blob);blob.extend(values.tobytes())
        document['bufferViews'].append({'buffer':0,'byteOffset':offset,'byteLength':values.nbytes})
        flat=values.reshape(len(values),-1)
        document['accessors'].append({'bufferView':len(document['bufferViews'])-1,'componentType':5126,
            'count':len(values),'type':kind,'min':flat.min(0).tolist(),'max':flat.max(0).tolist()})
        return len(document['accessors'])-1
    attrs=document['meshes'][document['nodes'][part['node']]['mesh']]['primitives'][0]['attributes']
    rest_skin=a.world_rest[part['nodes']]@part['inverse_bind']
    if np.max(np.abs(rest_skin-np.eye(4)))>2e-6:
        raise ValueError('Normalize the mesh bind basis before applying this reviewed tail repair')
    positions=part['position'][:,:3].copy();positions[changed]=posed[changed]
    attrs['POSITION']=append(positions,'VEC3')
    normals=accessor(a.document,a.blob,attrs['NORMAL']);new_normals=normals.copy()
    transforms=world[part['nodes']]@part['inverse_bind']
    blended=np.zeros((len(normals),3,3))
    for k in range(part['joints'].shape[1]):
        blended+=transforms[part['joints'][:,k],:3,:3]*part['weights'][:,k,None,None]
    normal_matrix=np.linalg.inv(blended[changed]).transpose(0,2,1)
    new_normals[changed]=np.einsum('vab,vb->va',normal_matrix,normals[changed])
    new_normals[changed]/=np.linalg.norm(new_normals[changed],axis=1,keepdims=True)
    attrs['NORMAL']=append(new_normals,'VEC3')
    for node in chain:
        document['nodes'][node].pop('matrix',None)
        document['nodes'][node]['translation']=nt[node].tolist()
        document['nodes'][node]['rotation']=nq[node].tolist()
    skin=document['skins'][document['nodes'][part['node']]['skin']]
    ibm=part['inverse_bind'].copy()
    for index,node in enumerate(part['nodes']):
        if node in chain:ibm[index]=np.linalg.solve(world[node],a.world_rest[node]@ibm[index])
    skin['inverseBindMatrices']=append(ibm.transpose(0,2,1).reshape(-1,16),'MAT4')
    # Rest correction belongs to all actions. Keep non-tail channels exactly;
    # rebase native local tail deltas and key defaults for omitted controls.
    clip_audit={}
    for clip in document['animations']:
        paths=set();changed_channels=0
        for channel in clip['channels']:
            node=channel['target']['node'];path=channel['target']['path']
            if node not in chain:continue
            if path not in ('translation','rotation'):continue
            paths.add((node,path));sampler=clip['samplers'][channel['sampler']]
            values=accessor(a.document,a.blob,sampler['output'])
            if sampler.get('interpolation','LINEAR') not in ('LINEAR','STEP'):
                raise ValueError('Expand cubic tail channels before rebasing rest')
            if path=='translation':values=values-a.t[node]+nt[node]
            else:values=(Rotation.from_quat(nq[node])*Rotation.from_quat(a.q[node]).inv()*Rotation.from_quat(values)).as_quat()
            sampler['output']=append(values,'VEC3' if path=='translation' else 'VEC4');changed_channels+=1
        default_time=append(np.array([[0]]),'SCALAR')
        for node in chain:
            for path,values,kind in [('translation',nt[node],'VEC3'),('rotation',nq[node],'VEC4')]:
                if (node,path) in paths:continue
                sampler_id=len(clip['samplers'])
                clip['samplers'].append({'input':default_time,'output':append(values[None],kind),'interpolation':'LINEAR'})
                clip['channels'].append({'sampler':sampler_id,'target':{'node':node,'path':path}})
        clip_audit[clip['name']]={'rebased_tail_channels':changed_channels,'non_tail_channels_and_payload_preserved':True}
    write_glb(output,document,blob)
    new=Asset(output)
    untouched=np.ones(len(positions),bool);untouched[changed]=False
    lengths=[abs(np.linalg.norm(new.world_rest[c,:3,3]-new.world_rest[p,:3,3])-np.linalg.norm(a.world_rest[c,:3,3]-a.world_rest[p,:3,3])) for p,c in zip(chain,chain[1:])]
    hip_x=float(new.world_rest[new.name_to_id['Hips'],0,3])
    offsets={new.names[n]:float(new.world_rest[n,0,3]-hip_x) for n in chain}
    report={'input_sha256':digest(source),'repaired_sha256':digest(output),'tail_nodes':[a.names[n] for n in chain],
        'changed_geometry_vertex_ids':changed.tolist(),'changed_geometry_vertex_count':len(changed),
        'weights_and_joint_indices_unchanged':bool(np.array_equal(new.parts[0]['weights'],part['weights']) and np.array_equal(new.parts[0]['joints'],part['joints'])),
        'outside_tail_position_max_error':float(np.max(np.abs(new.parts[0]['position'][untouched]-part['position'][untouched]))),
        'maximum_tail_segment_length_error':float(max(lengths)),
        'rest_joint_lateral_offsets_from_hips':offsets,'terminal_fur_vertex_0_offset_from_hips':float(new.rest_vertices[0,0]-hip_x),
        'rest_surface_repose_max_error':float(np.max(np.abs(new.rest_vertices-posed))),
        'clips':clip_audit,'correction_policy':'Tail-only XY-plane straightening preserves each segment length and rearward Z offset; bake weighted rest surface, transform normals, rebind six native joints and rebase only tail channels.'}
    report['repair_pass']=bool(report['weights_and_joint_indices_unchanged'] and report['outside_tail_position_max_error']<1e-8 and max(lengths)<1e-5 and max(abs(x) for x in offsets.values())<1e-5 and report['rest_surface_repose_max_error']<2e-6)
    Path(report_path).write_text(json.dumps(report,indent=2))
    return report
