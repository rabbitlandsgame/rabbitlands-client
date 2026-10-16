"""Enforce one-shot surface contacts at export cadence on native geometry."""
import time,json
import numpy as np
from scipy.optimize import least_squares
from .actions import body_support_ids
from .contact import PawSurfaces
from .rig import LEG_NAMES
from .action_polish import native_hinge
from scipy.interpolate import PchipInterpolator


def terminal_support_pose(rig,reference):
    """Solve body contacts together; no later limb/tail edit may break them."""
    mapping={c['role']:i for i,c in enumerate(rig.controls)};body=body_support_ids(rig)
    reference=np.asarray(reference).copy();reference[mapping['jaw']]=0
    # Lying limbs must fold away from the torso's supports. A longer target
    # limb can otherwise prop the body up and defeat any torso-only solve.
    ids=[i for r,i in mapping.items() if r not in ['jaw','tail_lower','tail_end','tail_tip']]+[rig.dof-1]
    reference[mapping['head']]=np.deg2rad(35)
    reference[mapping['head_roll']]=np.deg2rad(65)
    reference[mapping['tail_splay']]=np.deg2rad(18)
    reference[mapping['tail']]=np.deg2rad(35)
    def residual(x):
        p=reference.copy();p[ids]=x;surface=rig.asset.skin(rig.pose(p,world_only=True)[2]);h=rig.asset.height
        r=[min(0,float(surface[:,1].min())-.0005)/h*2500]
        r.extend([(surface[keep,1].min()-.0005)/h*2000 for keep in body.values()])
        r.extend((x-reference[ids])*.5)
        r.extend([(p[mapping['head']]-np.deg2rad(35))*2,(p[mapping['head_roll']]-np.deg2rad(65))*2])
        return r
    best=None
    for roll_degrees in [-75,-90,-105,-65]:
        start=reference[ids].copy();start[ids.index(mapping['body_roll'])]=np.deg2rad(roll_degrees)
        result=least_squares(residual,np.clip(start,rig.lower[ids]+1e-7,rig.upper[ids]-1e-7),
            bounds=(rig.lower[ids]+1e-8,rig.upper[ids]-1e-8),max_nfev=200,ftol=1e-9,xtol=1e-9,gtol=1e-9)
        if best is None or result.cost<best.cost:best=result
        if best.cost<1:break
    reference[ids]=best.x
    return reference,{'cost':float(best.cost),'evaluations':int(best.nfev)}


def refine(rig,times,values,contract,windows,baseline_height=0,flight_paths=None):
    """Fit the evaluated sole at dense poses, retaining the existing action."""
    mapping={c['role']:i for i,c in enumerate(rig.controls)};paws=PawSurfaces(rig)
    values=np.asarray(values).copy();values[:,-1]+=baseline_height
    hold=contract['event_times_seconds'].get('recovery_end',contract['event_times_seconds'].get('settled_start'))
    # Equivalent revolutions are not anatomical motion. Select continuous
    # representations before interpolation, and store the widened bounds.
    for limb in LEG_NAMES:
        values[:,mapping[limb+'_foot']]=np.unwrap(values[:,mapping[limb+'_foot']])
    terminal_diagnostic=None
    started=time.monotonic();neutral=None
    lower,upper=rig.lower.copy(),rig.upper.copy()
    rest_world=rig.pose(np.zeros(rig.dof))[2]
    for limb in ['hind_left','hind_right']:
        for segment,role in [('knee','lower'),('hock','ankle')]:
            angle=native_hinge(rig,rest_world,limb,segment,0,0)
            if angle<0:upper[mapping[limb+'_'+role]]=min(upper[mapping[limb+'_'+role]],-angle-.10)
            else:lower[mapping[limb+'_'+role]]=max(lower[mapping[limb+'_'+role]],-angle+.10)
    values=np.clip(values,lower,upper)
    flight_functions={l:{k:PchipInterpolator(p['times_seconds'],p[k]) for k in ['forward_native','minimum_y_native','pitch_radians']} for l,p in (flight_paths or {}).items()}
    if contract['clip']=='Death_A':
        final,terminal_diagnostic=terminal_support_pose(rig,values[-1])
        alpha=np.clip((times-(hold-.65))/.65,0,1);alpha=alpha*alpha*(3-2*alpha)
        values=(1-alpha[:,None])*values+alpha[:,None]*final
        values[times>=hold-1e-8]=final
    for f,second in enumerate(times):
        pose=values[f].copy()
        if neutral is not None and (second<=.75 or (contract['clip']=='Sword_Attack' and second>=hold)):
            values[f]=neutral;continue
        if contract['clip']=='Death_A' and second>=hold-1e-8:continue
        active=[w for w in windows if w['support'] in LEG_NAMES and w['start_seconds']-1e-8<=second<=w['end_seconds']+1e-8]
        for limb in LEG_NAMES:
            w=next((w for w in active if w['support']==limb),None)
            path=(flight_paths or {}).get(limb)
            flying=w is None and path is not None and path['times_seconds'][0]<=second<=path['times_seconds'][-1]
            if w is None and not flying:continue
            goal_y=.0005 if w else max(.0005,float(flight_functions[limb]['minimum_y_native'](second)))
            goal_z=w['anchor_forward_native'] if w else float(flight_functions[limb]['forward_native'](second))
            goal_pitch=0 if w else float(flight_functions[limb]['pitch_radians'](second))
            ids=[mapping[limb+'_'+r] for r in ['anchor','upper','lower','foot'] if limb+'_'+r in mapping]
            if limb.startswith('hind'):ids.append(mapping[limb+'_ankle'])
            reference=pose.copy()
            def residual(x):
                p=reference.copy();p[ids]=x;world=rig.pose(p,world_only=True)[2];points=paws.points(limb,world)
                center=points[paws.bottom_ids[limb]].mean(0)
                residuals=np.r_[(points[:,1].min()-goal_y)/rig.asset.height*1000,
                    (center[2]-goal_z)/rig.asset.height*(1000 if w else 140),
                    (paws.pitch(limb,world)-goal_pitch)*(20 if w else 3),(x-reference[ids])*.005]
                if limb.startswith('hind'):
                    residuals=np.r_[residuals,[max(0,.10-np.sign(native_hinge(rig,rest_world,limb,segment,0,0))*native_hinge(rig,world,limb,segment,p[mapping['body_roll']],p[mapping[limb+'_splay']]))*30 for segment in ['knee','hock']]]
                return residuals
            result=least_squares(residual,np.clip(reference[ids],lower[ids]+1e-7,upper[ids]-1e-7),
                bounds=(lower[ids]+1e-8,upper[ids]-1e-8),max_nfev=15,ftol=1e-9,xtol=1e-9,gtol=1e-9)
            pose[ids]=result.x
        # During the unsupported fall, fit contact through pose controls before
        # export. Fixed paws are never moved to compensate for a low tail.
        surface=rig.asset.skin(rig.pose(pose,world_only=True)[2])
        if not active and float(surface[:,1].min())<.0002:
            ids=[mapping[r] for r in ['driver','hips','chest','neck','head','head_roll','tail','tail_splay','body_roll'] if r in mapping]+[rig.dof-1]
            reference=pose.copy()
            def residual(x):
                p=reference.copy();p[ids]=x;surf=rig.asset.skin(rig.pose(p,world_only=True)[2])
                return np.r_[min(0,float(surf[:,1].min())-.0005)/rig.asset.height*2000,(x-reference[ids])*.5]
            result=least_squares(residual,np.clip(reference[ids],rig.lower[ids]+1e-7,rig.upper[ids]-1e-7),bounds=(rig.lower[ids]+1e-8,rig.upper[ids]-1e-8),max_nfev=15)
            pose[ids]=result.x
        values[f]=pose
        if f==0:neutral=pose.copy()
        if f%96==0:print(json.dumps({'refine_frame':f,'of':len(times),'elapsed_seconds':round(time.monotonic()-started,1)}),flush=True)
    return values,{'terminal_support_solve':terminal_diagnostic,'sample_fps':float((len(times)-1)/times[-1]),'baseline_height_native':baseline_height}
