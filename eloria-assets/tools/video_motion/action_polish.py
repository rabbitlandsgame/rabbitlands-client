"""Surface-constrained one-shot polish and native actor transfer."""
import numpy as np,time,json
from scipy.interpolate import PchipInterpolator
from scipy.optimize import least_squares
from scipy.spatial.transform import Rotation
from .actions import body_support_ids,action_elbow_flexion
from .contact import PawSurfaces
from .rig import LEG_NAMES


def layout_values(package,rig,times):
    source=np.asarray(package['parameters_radians_and_root_height']);mapping={r:i for i,r in enumerate(package['controls'])}
    old=PchipInterpolator(package['times_seconds'],source,axis=0)(times)
    result=np.zeros((len(times),rig.dof))
    for i,c in enumerate(rig.controls):
        if c['role'] in mapping:result[:,i]=old[:,mapping[c['role']]]
    result[:,-1]=old[:,-1]
    return np.clip(result,rig.lower,rig.upper)


def native_hinge(rig,world,limb,segment,roll,splay):
    names=['upper','lower','ankle'] if segment=='knee' else ['lower','ankle','foot']
    p=[world[rig.roles[limb+'_'+r],:3,3] for r in names]
    a,b=p[1]-p[0],p[2]-p[1]
    axis=Rotation.from_rotvec(rig.forward*(roll+splay)).apply(rig.axis)
    return float(np.arctan2(np.cross(a,b)@axis,a@b))


def polish(rig,times,seed,contract,windows,flight_paths=None,max_evaluations=35):
    paws=PawSurfaces(rig);height=rig.asset.height
    mapping={c['role']:i for i,c in enumerate(rig.controls)}
    body=body_support_ids(rig);values=np.asarray(seed).copy()
    hold=contract['event_times_seconds']['recovery_end'] if contract['clip']=='Sword_Attack' else contract['event_times_seconds']['settled_start']
    diagnostics=[];started=time.monotonic();previous=None
    lower,upper=rig.lower.copy(),rig.upper.copy()
    # Keep both rear articulations on their native bend branch, avoiding a
    # branch jump during touchdown and a through-floor interpolated knee.
    zero=np.zeros(rig.dof);rest_world=rig.pose(zero)[2]
    for limb in ['hind_left','hind_right']:
        for segment,role in [('knee','lower'),('hock','ankle')]:
            angle=native_hinge(rig,rest_world,limb,segment,0,0)
            if angle<0:upper[mapping[limb+'_'+role]]=min(upper[mapping[limb+'_'+role]],-angle-.10)
            else:lower[mapping[limb+'_'+role]]=max(lower[mapping[limb+'_'+role]],-angle+.10)
    if contract['clip']=='Sword_Attack':
        extras=[mapping[r] for r in ['body_roll','head_roll','tail_splay']+[l+'_splay' for l in LEG_NAMES]]
        values[:,extras]=0
        # Reference recovers to the original standing pose. Make this an
        # explicit endpoint constraint rather than a local IK minimum.
        blend=np.clip((times-4.0)/.5,0,1);blend=blend*blend*(3-2*blend)
        values*=1-blend[:,None]
    else:
        ramp=np.clip((times-2.05)/1.36,0,1);ramp=ramp*ramp*(3-2*ramp)
        values[:,mapping['head_roll']]=np.deg2rad(rig.profile.get('action_head_counter_roll_degrees',55))*ramp
        values[:,mapping['tail_splay']]=np.deg2rad(rig.profile.get('action_tail_settle_splay_degrees',9))*ramp
        tuck=rig.profile.get('action_limb_tuck_degrees',16)
        for limb in LEG_NAMES:values[:,mapping[limb+'_splay']]=np.deg2rad(-tuck if limb.endswith('left') else tuck)*ramp
    values[times<=.75]=0
    values=np.clip(values,lower,upper)
    # Exact weighted limb subsets retain high knee/thigh vertices which can
    # penetrate even when the bottom-of-paw subset remains above the floor.
    limb_ids={}
    for limb in LEG_NAMES:
        nodes={rig.roles[limb+'_anchor']}
        for n in rig.asset.order:
            if rig.asset.parent[n] in nodes:nodes.add(n)
        ids=[];offset=0
        for part in rig.asset.parts:
            if 'joints' in part:
                mass=np.sum(np.isin(part['nodes'][part['joints']],list(nodes))*part['weights'],axis=1)
                ids.extend((offset+np.flatnonzero(mass>.35)).tolist())
            offset+=len(part['position'])
        limb_ids[limb]=ids
    for f,second in enumerate(times):
        pose=values[f].copy()
        active=[w for w in windows if w['start_seconds']-1e-8<=second<=w['end_seconds']+1e-8]
        body_active=[w for w in active if w['support'].startswith('body_')]
        if previous is not None and second>hold+1e-8:
            values[f]=previous;continue
        if second<=.75 or (contract['clip']=='Sword_Attack' and second>=hold-1e-8):
            values[f]=0;previous=values[f].copy();continue
        if body_active or (contract['clip']=='Death_A' and second>2.05):
            ids=[mapping[r] for r in ['driver','hips','chest','neck','head','head_roll','tail','tail_splay']]+[rig.dof-1]
            if body_active:
                ids+= [mapping[r] for l in LEG_NAMES for r in [l+'_anchor',l+'_upper',l+'_lower',l+'_ankle',l+'_foot',l+'_splay'] if r in mapping]
            reference=pose.copy()
            def body_residual(x):
                p=reference.copy();p[ids]=x
                world=rig.pose(p)[2];surface=rig.asset.skin(world)
                r=[min(0,float(surface[:,1].min())-.0005)/height*1400]
                for support in body_active:r.append((surface[body[support['support']],1].min()-.0005)/height*1000)
                for support in active:
                    limb=support['support']
                    if limb not in LEG_NAMES:continue
                    points=paws.points(limb,world);center=points[paws.bottom_ids[limb]].mean(0)
                    r.extend([(points[:,1].min()-.0005)/height*700,
                        (center[2]-support['anchor_forward_native'])/height*650,
                        (center[0]-support.get('anchor_lateral_native',paws.rest_centers[limb][0]))/height*650,
                        paws.pitch(limb,world)*15])
                r.extend((p[ids]-reference[ids])*.15)
                return r
            start=reference[ids] if previous is None else .75*previous[ids]+.25*reference[ids]
            solved=least_squares(body_residual,np.clip(start,lower[ids]+1e-7,upper[ids]-1e-7),bounds=(lower[ids]+1e-8,upper[ids]-1e-8),max_nfev=max_evaluations,ftol=1e-7,xtol=1e-7,gtol=1e-7)
            pose[ids]=solved.x
        for limb in LEG_NAMES:
            supported=next((w for w in active if w['support']==limb),None)
            original_world=rig.pose(pose)[2]
            original_center=paws.center(limb,original_world)
            goal=original_center.copy();target_pitch=paws.pitch(limb,original_world)
            goal_y=max(.0005,float(paws.points(limb,original_world)[:,1].min()))
            if supported:
                goal[2]=supported['anchor_forward_native'];goal[0]=supported.get('anchor_lateral_native',paws.rest_centers[limb][0]);goal_y=.0005;target_pitch=0
            elif flight_paths and limb in flight_paths:
                path=flight_paths[limb]
                if path['times_seconds'][0]<=second<=path['times_seconds'][-1]:
                    goal[2]=float(PchipInterpolator(path['times_seconds'],path['forward_native'])(second))
                    goal_y=float(PchipInterpolator(path['times_seconds'],path['minimum_y_native'])(second))
                    target_pitch=float(PchipInterpolator(path['times_seconds'],path['pitch_radians'])(second))
            ids=[i for i,c in enumerate(rig.controls) if c['role'].startswith(limb+'_') and c['role']!=limb+'_ankle']
            if limb.startswith('hind') and limb+'_ankle' in mapping:ids.append(mapping[limb+'_ankle'])
            if contract['clip']=='Sword_Attack':ids=[i for i in ids if not rig.controls[i]['role'].endswith('_splay')]
            reference=pose.copy()
            def leg_residual(x):
                p=reference.copy();p[ids]=x;world=rig.pose(p)[2]
                points=paws.points(limb,world);center=points[paws.bottom_ids[limb]].mean(0);surface=rig.asset.skin(world)
                r=[(points[:,1].min()-goal_y)/height*900,
                   (center[2]-goal[2])/height*(900 if supported else 110),
                   (center[0]-goal[0])/height*(900 if supported else 15),
                   (paws.pitch(limb,world)-target_pitch)*(20 if supported else 3),
                   min(0,float(surface[limb_ids[limb],1].min())-.0004)/height*1300]
                roll=p[mapping['body_roll']];splay=p[mapping[limb+'_splay']]
                if limb.startswith('fore'):r.append(max(0,.10+action_elbow_flexion(rig,world,limb,roll,splay))*30)
                else:
                    for segment in ['knee','hock']:r.append(max(0,.10+native_hinge(rig,world,limb,segment,roll,splay))*30)
                r.extend((p[ids]-reference[ids])*.015)
                if previous is not None:r.extend((p[ids]-previous[ids])*.025)
                return r
            start=reference[ids] if previous is None else .8*previous[ids]+.2*reference[ids]
            solved=least_squares(leg_residual,np.clip(start,lower[ids]+1e-7,upper[ids]-1e-7),bounds=(lower[ids]+1e-8,upper[ids]-1e-8),max_nfev=max_evaluations,ftol=1e-8,xtol=1e-8,gtol=1e-8)
            pose[ids]=solved.x
        values[f]=pose;previous=pose.copy()
        if f%24==0:print(json.dumps({'action_polish_frame':f,'of':len(times),'elapsed_seconds':round(time.monotonic()-started,1)}),flush=True)
    return values,diagnostics
