"""One-shot foundations: native body roll, nonperiodic sampling and support QA.

This does not infer a video's hidden lateral motion. Reviewed observations,
support windows and event times remain required before fitting or acceptance.
"""
import numpy as np
from scipy.interpolate import PchipInterpolator
from scipy.spatial.transform import Rotation
from .asset import digest
from .rig import Rig,LEG_NAMES
from .contact import PawSurfaces
from .contact import elbow_flexion,elbow_endpoint
from scipy.optimize import least_squares
from scipy.ndimage import map_coordinates
from scipy.spatial import cKDTree
import cv2,json,time
from pathlib import Path


class ActionRig:
    """Add a body roll about the posed hips to the native canine controls.

    Layout: original angular controls, optional limb/head/tail orientation
    controls, body_roll radians, root_height native units. Keeping height last
    permits semantic mapping without quaternion
    copying. No mesh, rest, skin, joint name or parent is changed.
    """
    def __init__(self,asset,profile):
        self.base=Rig(asset,profile)
        self.asset,self.profile=asset,profile
        roll_node=profile.get('body_roll_node',self.base.driver)
        self.roll_node=asset.name_to_id[roll_node] if isinstance(roll_node,str) else int(roll_node)
        if self.roll_node not in asset.joints:raise ValueError('Body roll must use a skin joint')
        ancestor=self.base.driver
        while ancestor>=0 and ancestor!=self.roll_node:ancestor=int(asset.parent[ancestor])
        if ancestor!=self.roll_node:raise ValueError('Body roll must act at or above the body driver')
        self.roles={**self.base.roles,'body_roll':self.roll_node,'head_roll':self.base.roles['head'],'tail_splay':self.base.roles['tail']}
        self.axis,self.up,self.forward=self.base.axis,self.base.up,self.base.forward
        self.driver=self.base.driver
        extra=[{'role':l+'_splay','axis':self.forward.tolist(),'bounds_degrees':[-45,45]} for l in LEG_NAMES]
        extra.append({'role':'head_roll','axis':self.forward.tolist(),'bounds_degrees':[-75,75]})
        extra.append({'role':'tail_splay','axis':self.forward.tolist(),'bounds_degrees':[-35,35]})
        for custom in profile.get('action_secondary_axis_controls',[]):
            if custom['role'] in [c['role'] for c in extra]:raise ValueError('Duplicate secondary action control')
            if custom['pivot_role'] not in self.base.roles:raise ValueError('Map the secondary action pivot')
            extra.append(dict(custom));self.roles[custom['role']]=self.base.roles[custom['pivot_role']]
        for c in extra:
            if c['role'] in profile.get('action_extra_control_bounds_degrees',{}):c['bounds_degrees']=profile['action_extra_control_bounds_degrees'][c['role']]
        self.controls=[*self.base.controls,*extra,{'role':'body_roll','axis':self.forward.tolist(),
            'bounds_degrees':profile.get('action_body_roll_bounds_degrees',[-100,100])}]
        bounds=self.controls[-1]['bounds_degrees']
        height_bounds=profile.get('action_body_height_bounds_height',[-1.15,.25])
        # Accepted walk bounds can exclude the neutral reference stance (e.g.
        # its authored shoulder preference). One-shot startup must include
        # that neutral pose without altering any accepted walking channel.
        self.lower=np.r_[np.minimum(self.base.lower[:-1],0),np.deg2rad([c['bounds_degrees'][0] for c in extra]),np.deg2rad(bounds[0]),height_bounds[0]*asset.height]
        self.upper=np.r_[np.maximum(self.base.upper[:-1],0),np.deg2rad([c['bounds_degrees'][1] for c in extra]),np.deg2rad(bounds[1]),height_bounds[1]*asset.height]
        self.rest_markers=self.base.rest_markers
        self.leg_lengths=self.base.leg_lengths
        self.markers=self.base.markers
        self.scapula_offsets=self.base.scapula_offsets
        self.paw_followers=self.base.paw_followers
        self.descendants={self.roll_node}
        for node in asset.order:
            if asset.parent[node] in self.descendants:self.descendants.add(node)
        self.jaw_arc=profile.get('action_jaw_arc',False)
        self.jaw_index=next((i for i,c in enumerate(self.base.controls) if c['role']=='jaw'),None)
        self.extra_pose_nodes=[]
        for control in extra:
            role=control['role'];node=self.roles[control['pivot_role']] if 'pivot_role' in control else (self.roles['head'] if role=='head_roll' else (self.roles['tail'] if role=='tail_splay' else self.roles[role.replace('_splay','_upper')]))
            descendants={node}
            for child in asset.order:
                if asset.parent[child] in descendants:descendants.add(child)
            axis=np.asarray(control['axis'],float);axis/=np.linalg.norm(axis);self.extra_pose_nodes.append((node,np.asarray(sorted(descendants),int),axis))
        self.roll_nodes=np.asarray(sorted(self.descendants),int)

    @property
    def dof(self):return len(self.controls)+1

    def pose(self,parameters,world_only=False):
        """Return (local T, local Q, world); only world is valid in fast mode."""
        values=np.asarray(parameters,float)
        if values.shape!=(self.dof,) or not np.isfinite(values).all():
            raise ValueError('Action parameters must be finite and match the semantic layout')
        if np.any(values<self.lower-1e-8) or np.any(values>self.upper+1e-8):
            raise ValueError('Action parameters exceed the reviewed native bounds')
        t,q,world=self.base.pose(np.r_[values[:len(self.base.controls)],values[-1]],world_only=world_only)
        if self.jaw_arc and self.jaw_index is not None and abs(values[self.jaw_index])>1e-14:
            jaw=self.roles['jaw'];hinge=self.roles['jaw_hinge']
            if self.asset.parent[jaw]!=hinge:
                raise ValueError('Jaw arc must use the existing native parent hinge')
            index=next(i for i,c in enumerate(self.base.controls) if c['role']=='jaw')
            jaw_delta=Rotation.from_rotvec(self.axis*values[index]).as_matrix()
            shift=world[hinge,:3,3]+jaw_delta@(world[jaw,:3,3]-world[hinge,:3,3])-world[jaw,:3,3]
            descendants={jaw}
            for node in self.asset.order:
                if self.asset.parent[node] in descendants:descendants.add(node)
            for node in descendants:world[node,:3,3]+=shift
            if not world_only:
                local=np.linalg.solve(world[hinge],world[jaw]);t[jaw]=local[:3,3]
            for name in self.profile.get('action_jaw_follow_subtrees',[]):
                node=self.asset.name_to_id[name]
                if self.asset.parent[node]!=hinge:raise ValueError('Review jaw follower parent')
                descendants={node}
                for child in self.asset.order:
                    if self.asset.parent[child] in descendants:descendants.add(child)
                for child in descendants:
                    world[child,:3,3]=world[hinge,:3,3]+jaw_delta@(world[child,:3,3]-world[hinge,:3,3])
                    world[child,:3,:3]=jaw_delta@world[child,:3,:3]
                if not world_only:
                    local=np.linalg.solve(world[hinge],world[node]);t[node]=local[:3,3]
                    q[node]=Rotation.from_matrix(local[:3,:3]/self.asset.s[node]).as_quat()
        for k,(node,descendants,axis) in enumerate(self.extra_pose_nodes):
            angle=values[len(self.base.controls)+k]
            if abs(angle)<1e-14:continue
            pivot=world[node,:3,3].copy();delta=Rotation.from_rotvec(axis*angle).as_matrix()
            world[descendants,:3,3]=(world[descendants,:3,3]-pivot)@delta.T+pivot
            world[descendants,:3,:3]=np.einsum('ab,nbc->nac',delta,world[descendants,:3,:3])
            if not world_only:
                parent=int(self.asset.parent[node]);local=np.linalg.solve(world[parent],world[node])
                q[node]=Rotation.from_matrix(local[:3,:3]/self.asset.s[node]).as_quat()
        angle=values[-2]
        if abs(angle)<1e-14:return t,q,world
        delta=Rotation.from_rotvec(self.forward*angle).as_matrix()
        pivot=world[self.roles['hips'],:3,3].copy()
        world[self.roll_nodes,:3,3]=(world[self.roll_nodes,:3,3]-pivot)@delta.T+pivot
        world[self.roll_nodes,:3,:3]=np.einsum('ab,nbc->nac',delta,world[self.roll_nodes,:3,:3])
        # A single native driver transform carries the whole subtree. Leaf
        # paw helper and compensated shoulder transforms remain covariant.
        if not world_only:
            parent=int(self.asset.parent[self.roll_node])
            parent_world=np.eye(4) if parent<0 else world[parent]
            local=np.linalg.solve(parent_world,world[self.roll_node])
            t[self.roll_node]=local[:3,3]
            q[self.roll_node]=Rotation.from_matrix(local[:3,:3]/self.asset.s[self.roll_node]).as_quat()
        return t,q,world

    def marker_positions(self,world):return self.base.marker_positions(world)
    def landmarks(self,world):return self.base.landmarks(world)
    def follower_metadata(self):return self.base.follower_metadata()


def body_support_ids(rig):
    """Native torso/head ownership, including weighted fur helper descendants."""
    a=rig.asset
    head={rig.roles['head']};tail={rig.roles['tail']}
    for n in a.order:
        if a.parent[n] in head:head.add(n)
        if a.parent[n] in tail:tail.add(n)
    chest=set();hips={rig.roles['hips'],rig.roles['hind_left_anchor'],rig.roles['hind_right_anchor']}
    hips.update(a.name_to_id[n] if isinstance(n,str) else int(n) for n in rig.profile.get('body_support_hip_rigid_nodes',[]))
    for n in a.order:
        if a.names[n].lower().startswith('spine_') or a.parent[n] in chest:chest.add(n)
    limbs={rig.roles[l+'_'+r] for l in LEG_NAMES for r in ['anchor','upper']}
    for n in a.order:
        if a.parent[n] in limbs:limbs.add(n)
    forbidden=head|tail|limbs
    chest-=forbidden
    # Compensated attachment controls retain the torso orientation. Their
    # rigid armor is a physical chest support even though native skin labels
    # place it on a named shoulder; the articulated upper limb stays excluded.
    if rig.profile.get('body_support_include_compensated_anchors',False):
        chest.update(anchor for anchor,upper in rig.scapula_offsets)
    center=.5*(a.world_rest[rig.roles['hips'],2,3]+a.world_rest[rig.roles['chest'],2,3])
    result={label:[] for label in ['body_chest','body_hips','body_head','body_tail']};offset=0
    for part in a.parts:
        if 'joints' in part:
            nodes=part['nodes'][part['joints']];v=a.rest_vertices[offset:offset+len(part['position'])]
            for label,owned in [('body_chest',chest),('body_hips',hips),('body_head',head),('body_tail',tail)]:
                mass=np.sum(np.isin(nodes,list(owned))*part['weights'],axis=1)
                keep=mass>.35
                if label=='body_chest':keep&=(v[:,2]>center)&(v[:,1]>.3*a.height)
                if label=='body_hips':keep&=(v[:,2]<=center)&(v[:,1]>.3*a.height)
                if label=='body_head':keep=(mass>.65)&(v[:,2]>a.world_rest[rig.roles['head'],2,3]+.03*a.height)
                if label=='body_tail':keep=(mass>.65)&(v[:,2]<a.world_rest[rig.roles['tail'],2,3]-.02*a.height)
                result[label].extend((offset+np.flatnonzero(keep)).tolist())
        offset+=len(part['position'])
    for label,declared in rig.profile.get('native_body_support_vertex_ids',{}).items():
        ids=np.asarray(declared)
        if label not in result or ids.ndim!=1 or not np.issubdtype(ids.dtype,np.integer) or len(np.unique(ids))!=len(ids) or len(ids)<3:
            raise ValueError('Reviewed body support regions need a known label and unique integer IDs')
        if np.any(ids<0) or np.any(ids>=len(a.rest_vertices)):
            raise ValueError('Reviewed body support vertices are outside this asset')
        result[label]=np.sort(ids).tolist()
    if any(len(ids)<3 for ids in result.values()):raise ValueError('Review the native weighted body support regions')
    return result


def action_elbow_flexion(rig,world,limb,body_roll,splay=0):
    upper=world[rig.roles[limb+'_upper'],:3,3]
    elbow=world[rig.roles[limb+'_lower'],:3,3]
    foot=world[elbow_endpoint(rig,limb),:3,3]
    a,b=elbow-upper,foot-elbow
    axis=Rotation.from_rotvec(rig.forward*(body_roll+splay)).apply(rig.axis)
    return float(np.arctan2(np.cross(a,b)@axis,a@b))


def validate_contract(contract,duration):
    if contract.get('loop') is not False or contract.get('clip') not in ('Sword_Attack','Death_A'):
        raise ValueError('Action contract must identify a supported nonlooping clip')
    if duration<=0 or contract.get('root_motion')!='in_place':
        raise ValueError('The current action pilot requires positive duration and in-place root policy')
    events=contract.get('event_times_seconds')
    if not isinstance(events,dict) or not events:
        raise ValueError('Review and record event times before fitting or export')
    event_values=np.asarray(list(events.values()),float)
    if not np.isfinite(event_values).all() or np.any(event_values<0) or np.any(event_values>duration):
        raise ValueError('Action events must be finite seconds inside the clip')
    if contract['clip']=='Sword_Attack':
        required=('anticipation_start','bite_contact','recovery_end')
    else:required=('support_loss','body_ground_contact','settled_start')
    if any(e not in events for e in required) or np.any(np.diff([events[e] for e in required])<0):
        raise ValueError('Review the required action events in temporal order')
    if contract['clip']=='Death_A' and events['settled_start']>=duration:
        raise ValueError('Death requires a measurable terminal held interval')


def bake_action(rig,times,parameters,fps=192):
    """Preserve one-shot endpoint/hold and avoid unconstrained floor lifting."""
    times=np.asarray(times,float);parameters=np.asarray(parameters,float)
    if times.ndim!=1 or len(times)<2 or times[0]!=0 or np.any(np.diff(times)<=0):
        raise ValueError('One-shot timestamps must start at zero and increase strictly')
    if parameters.shape!=(len(times),rig.dof) or not np.isfinite(parameters).all():
        raise ValueError('One-shot parameters must match the rig and timestamps')
    dense=np.linspace(0,times[-1],round(times[-1]*fps)+1)
    values=PchipInterpolator(times,parameters,axis=0)(dense)
    poses=[rig.pose(p) for p in values]
    return dense,np.asarray([p[0] for p in poses]),np.asarray([p[1] for p in poses])


def evaluate_action(asset,rig,contract,support_windows,fps=192):
    """Sample exported surfaces, support drift and terminal hold independently.

    Windows carry start_seconds/end_seconds and support names: each limb or
    body_chest/body_hips/body_head. Body regions use actual native weights.
    This evaluator does not invent support windows from a walking cycle.
    """
    duration=float(asset.duration(contract['clip']));validate_contract(contract,duration)
    if not support_windows:raise ValueError('One-shot support windows must be reviewed')
    times=np.linspace(0,duration,round(duration*fps)+1)
    t,q=asset.sample(contract['clip'],times)
    worlds=[asset.world(ti,qi) for ti,qi in zip(t,q)]
    surfaces=np.asarray([asset.skin(w) for w in worlds])
    paws=PawSurfaces(rig)
    body=body_support_ids(rig)
    measurements=[]
    for window in support_windows:
        support=window['support'];start=window['start_seconds'];end=window['end_seconds']
        if not 0<=start<end<=duration:raise ValueError('Support windows must lie inside the clip')
        selection=np.flatnonzero((times>=start)&(times<=end))
        if len(selection)<3:raise ValueError('Support interval is too short for the declared sample rate')
        if support in LEG_NAMES:
            points=np.asarray([paws.points(support,worlds[i]) for i in selection])
            centers=points[:,paws.bottom_ids[support]].mean(1)
        elif support in body:
            points=surfaces[selection][:,body[support]]
            # After roll, choose the lowest actual patch in each body sample;
            # distinguish its contact height from terminal whole-surface drift.
            centers=np.asarray([p[np.argsort(p[:,1])[:min(12,len(p))]].mean(0) for p in points])
        else:raise ValueError('Map each native support region explicitly')
        velocity=np.gradient(centers[:,[0,2]],times[selection],axis=0)
        rms=float(np.sqrt(np.mean(np.sum(velocity**2,axis=1))))
        floor_error=float(np.max(np.abs(points[:,:,1].min(1)-window.get('floor_height_native',0))))
        measurements.append({'support':support,'start_seconds':start,'end_seconds':end,
            'support_floor_max_error_native':floor_error,'horizontal_drift_rms_native_per_second':rms})
    hold_start=contract['event_times_seconds']['settled_start'] if contract['clip']=='Death_A' else contract['event_times_seconds']['recovery_end']
    held=surfaces[times>=hold_start]
    hold_drift=float(np.linalg.norm(held-held[0],axis=2).max()) if len(held)>1 else 0
    height=rig.asset.height
    return {'export_sha256':digest(asset.path),'clip':contract['clip'],'sampling_fps':fps,'loop':False,
        'minimum_entire_surface_y':float(surfaces[:,:,1].min()),'reviewed_support_windows':measurements,
        'terminal_hold_surface_maximum_drift_native':hold_drift,'terminal_hold_start_seconds':hold_start,
        'contact_pass':bool(surfaces[:,:,1].min()>=-.002*height and all(m['support_floor_max_error_native']<=.002*height and m['horizontal_drift_rms_native_per_second']<=.015*height for m in measurements)),
        'hold_pass':bool(hold_drift<=.001*height),
        'support_patch_schema':3 if rig.profile.get('native_body_support_vertex_ids') else 2,'body_support_vertex_counts':{label:len(ids) for label,ids in body.items()},
        'policy':'Declared one-shot support windows and deformed surfaces; head uses forward face/muzzle vertices with >65% head ownership, excluding shared neck fur. Tail uses distal tail-owned vertices. No looping-stance speed or per-frame global floor lift.'}


def fit_action(rig,camera,observations,frames,contract,support_windows,mask_dir=None,
               pose_guides=None,max_evaluations=40):
    """Fit reviewed one-shot features and surfaces without a global floor lift."""
    lookup={o['frame']:o for o in observations['observations']}
    chosen=[lookup[f] for f in frames]
    times=np.array([o['time_seconds'] for o in chosen]);times-=times[0]
    validate_contract(contract,float(times[-1]))
    mapping={c['role']:i for i,c in enumerate(rig.controls)}
    guides=pose_guides or []
    for guide in guides:
        if guide['role'] not in mapping:raise ValueError('Map the authored pose guide role on the native rig')
    if contract['clip']=='Death_A' and not any(g['role']=='body_roll' for g in guides):
        raise ValueError('Review the direction and timing of the unobserved body roll')
    camera_matrix,offset=np.asarray(camera['pixel_matrix_gltf']),np.asarray(camera['pixel_offset'])
    paws=PawSurfaces(rig);height=rig.asset.height
    sample_ids=np.linspace(0,len(rig.asset.rest_vertices)-1,min(900,len(rig.asset.rest_vertices))).astype(int)
    body_ids=body_support_ids(rig)
    results=[];diagnostics=[];previous=None;started=time.monotonic()
    seed=np.zeros(rig.dof)
    for index,(observation,second) in enumerate(zip(chosen,times)):
        seed=np.zeros(rig.dof) if previous is None else previous.copy()
        targets=[]
        for guide in guides:
            value=float(PchipInterpolator(guide['times_seconds'],guide['radians'])(second))
            seed[mapping[guide['role']]]=value
            targets.append((mapping[guide['role']],value,guide.get('weight',5)))
        active=[w for w in support_windows if w['start_seconds']-1e-8<=second<=w['end_seconds']+1e-8]
        contour=distance=None
        if mask_dir is not None:
            mask=cv2.imread(str(Path(mask_dir)/f'{observation["frame"]:04d}.png'),0)
            distance=cv2.distanceTransform(255-mask,cv2.DIST_L2,5)
            contours,_=cv2.findContours(mask,cv2.RETR_EXTERNAL,cv2.CHAIN_APPROX_NONE)
            full=max(contours,key=cv2.contourArea).reshape(-1,2)
            contour=full[np.linspace(0,len(full)-1,min(100,len(full))).astype(int)]
        def residual(values):
            world=rig.pose(values)[2];surface=rig.asset.skin(world)
            predicted=rig.landmarks(world);r=[]
            for role,feature in observation['landmarks'].items():
                confidence=feature.get('confidence',0)*(1 if feature.get('reviewed') else .25)
                if role in predicted and confidence>.03:
                    r.extend((camera_matrix@predicted[role]+offset-feature['xy'])*np.sqrt(confidence)/8)
            if distance is not None:
                points=surface[sample_ids]@camera_matrix.T+offset
                outside=map_coordinates(distance,[points[:,1],points[:,0]],order=1,mode='constant',cval=100)
                r.extend(outside/24/np.sqrt(len(points)/70))
                r.extend(cKDTree(points).query(contour)[0]/20/np.sqrt(len(contour)/70))
            # Whole-surface penetration is a pose constraint, not a body lift.
            r.append(min(0,float(surface[:,1].min())-.0004)/height*650)
            for support in active:
                limb=support['support']
                if limb in LEG_NAMES:
                    points=paws.points(limb,world);center=points[paws.bottom_ids[limb]].mean(0)
                    r.extend([(points[:,1].min()-.0005)/height*500,
                        (center[2]-support['anchor_forward_native'])/height*320,
                        paws.pitch(limb,world)*12])
                else:
                    points=surface[body_ids[limb]]
                    r.append((points[:,1].min()-.0005)/height*220)
            for limb in ('fore_left','fore_right'):
                r.append(max(0,.10+action_elbow_flexion(rig,world,limb,values[mapping['body_roll']]))*12)
            for column,value,weight in targets:r.append((values[column]-value)*weight)
            if all(role in mapping for role in ('tail_lower','tail_end','tail_tip')):
                weights=np.asarray(rig.profile.get('action_tail_bend_distribution',[.55,.3,.15]))
                bend=np.array([values[mapping[r]] for r in ['tail_lower','tail_end','tail_tip']])/weights
                r.extend((bend[1:]-bend[0])*25)
            # Body roll is kept neutral during the bite; death supplies its
            # reviewed authored guide because side-camera sign is ambiguous.
            if contract['clip']=='Sword_Attack':r.append(values[mapping['body_roll']]*30)
            r.extend((values[:-1]-seed[:-1])*.05)
            if previous is not None:r.extend((values[:-1]-previous[:-1])*.12)
            return np.asarray(r)
        # Keep the terminal hold identical rather than refitting noisy video
        # texture after the reviewed settling/recovery event.
        hold=contract['event_times_seconds']['settled_start'] if contract['clip']=='Death_A' else contract['event_times_seconds']['recovery_end']
        if previous is not None and second>hold+1e-8:
            solved_values=previous.copy();cost=0.;success=True
        else:
            solved=least_squares(residual,np.clip(seed,rig.lower+1e-7,rig.upper-1e-7),bounds=(rig.lower+1e-8,rig.upper-1e-8),
                max_nfev=max_evaluations,ftol=1e-5,xtol=1e-5,gtol=1e-5)
            solved_values=solved.x;cost=float(solved.cost);success=bool(solved.success)
        results.append(solved_values);previous=solved_values.copy()
        diagnostics.append({'frame':observation['frame'],'time_seconds':float(second),'cost':cost,'converged':success})
        if index%10==0:print(json.dumps({'action_fit_frame':index,'of':len(times),'cost':round(cost,3),'elapsed_seconds':round(time.monotonic()-started,1)}),flush=True)
    return times,np.asarray(results),diagnostics
