"""Reviewed early collapse guides with native foreleg folding and sole support."""
import numpy as np
from scipy.interpolate import PchipInterpolator
from scipy.optimize import least_squares
from .actions import action_elbow_flexion,body_support_ids
from .contact import PawSurfaces,SurfacePatches
from .action_polish import native_hinge
from .rig import LEG_NAMES


def fit_early_collapse(rig,times,values,guides,anchors):
    """Refit the head-drop phase only; retain the existing roll and settled pose.

    Heights are fractions of each actor's standing chest/hips/head height.
    They describe visible pose intent, not measured hidden joint positions.
    All legs use native geometry and actual weighted soles. The returned pose
    array is unchanged outside guides['times_seconds'].
    """
    m={c['role']:i for i,c in enumerate(rig.controls)};paws=PawSurfaces(rig)
    times=np.asarray(times);original=np.asarray(values);result=original.copy()
    functions={k:PchipInterpolator(guides['times_seconds'],guides[k]) for k in ['chest_height_fraction','hips_height_fraction','head_height_fraction','fore_elbow_degrees','blend']}
    standing=rig.pose(original[0],world_only=True)[2]
    standing_y={k:standing[rig.roles[k],1,3] for k in ['chest','hips','head']}
    bodyids=[m[k] for k in ['driver','hips','chest','neck','head','tail','tail_splay']]+[rig.dof-1]
    regions=body_support_ids(rig)
    for limb in LEG_NAMES:
        owned={rig.roles[limb+'_anchor']}
        for n in rig.asset.order:
            if rig.asset.parent[n] in owned:owned.add(n)
        ids=[];offset=0
        for part in rig.asset.parts:
            if 'joints' in part:
                mass=np.sum(np.isin(part['nodes'][part['joints']],list(owned))*part['weights'],axis=1)
                ids.extend((offset+np.flatnonzero(mass>.35)).tolist())
            offset+=len(part['position'])
        regions[limb]=ids
    patches=SurfacePatches(rig.asset,regions)
    previous=None;diagnostics=[]
    for f,second in enumerate(times):
        if second<guides['times_seconds'][0] or second>guides['times_seconds'][-1]:continue
        blend=float(functions['blend'](second))
        if blend<1e-9:continue
        reference=original[f].copy();p=reference.copy()
        polish=guides.get('polish_seed',False);reference_world=rig.pose(reference,world_only=True)[2]
        goals={k:reference_world[rig.roles[k],1,3] if polish else (1-blend)*reference_world[rig.roles[k],1,3]+blend*standing_y[k]*float(functions[k+'_height_fraction'](second)) for k in standing_y}
        # Match torso/head lowering before solving each supported native leg.
        def torso(x):
            candidate=reference.copy();candidate[bodyids]=x;world=rig.pose(candidate,world_only=True)[2]
            return np.r_[[(world[rig.roles[k],1,3]-goals[k])/rig.asset.height*100 for k in goals],
                [min(0,float(patches.points(k,world)[:,1].min())-.0005)/rig.asset.height*2500 for k in regions if k.startswith('body_')],(x-reference[bodyids])*.6]
        if not polish or any(patches.points(k,reference_world)[:,1].min()<.0002 for k in regions if k.startswith('body_')):
            start=reference[bodyids] if previous is None or polish else previous[bodyids]
            solve=least_squares(torso,np.clip(start,rig.lower[bodyids]+1e-7,rig.upper[bodyids]-1e-7),bounds=(rig.lower[bodyids]+1e-8,rig.upper[bodyids]-1e-8),max_nfev=20 if polish else 35,ftol=1e-9,xtol=1e-9,gtol=1e-9)
            p[bodyids]=solve.x
        for limb in LEG_NAMES:
            fore=limb.startswith('fore');support_end=guides['fore_support_end'] if fore else guides['hind_support_end']
            # Release the supports smoothly into the unchanged roll trajectory.
            release=np.clip((second-support_end)/guides['release_seconds'],0,1);release=release*release*(3-2*release)
            oldworld=rig.pose(reference,world_only=True)[2];oldpoints=paws.points(limb,oldworld);oldcenter=oldpoints[paws.bottom_ids[limb]].mean(0)
            y=(1-release)*.0005+release*max(.0005,float(oldpoints[:,1].min()))
            z=(1-release)*anchors[limb]+release*oldcenter[2]
            pitch=release*paws.pitch(limb,oldworld)
            elbowgoal=(1-blend)*np.rad2deg(action_elbow_flexion(rig,oldworld,limb,reference[m['body_roll']],reference[m[limb+'_splay']]))+blend*float(functions['fore_elbow_degrees'](second)) if fore else None
            if polish:
                y=.0005 if second<=support_end else max(.0005,float(oldpoints[:,1].min()))
                z=anchors[limb] if second<=support_end else oldcenter[2]
                pitch=0 if second<=support_end else paws.pitch(limb,oldworld)
                if fore:elbowgoal=np.rad2deg(action_elbow_flexion(rig,oldworld,limb,reference[m['body_roll']],reference[m[limb+'_splay']]))
            ids=[m[limb+'_'+k] for k in ['anchor','upper','lower','foot']]
            if not fore:ids.append(m[limb+'_ankle'])
            lower,upper=rig.lower[ids].copy(),rig.upper[ids].copy()
            if not fore:
                for segment,role in [('knee','lower'),('hock','ankle')]:
                    angle=native_hinge(rig,rig.asset.world_rest,limb,segment,0,0)
                    if angle<0:upper[ids.index(m[limb+'_'+role])]=min(upper[ids.index(m[limb+'_'+role])],-angle-.1)
            base=p.copy()
            def leg(x):
                candidate=base.copy();candidate[ids]=x;world=rig.pose(candidate,world_only=True)[2];pts=paws.points(limb,world);center=pts[paws.bottom_ids[limb]].mean(0)
                residual=[(pts[:,1].min()-y)/rig.asset.height*2000,(center[2]-z)/rig.asset.height*2000,(paws.pitch(limb,world)-pitch)*50]
                residual.append(min(0,float(patches.points(limb,world)[:,1].min())-.0005)/rig.asset.height*4000)
                if fore:
                    angle=action_elbow_flexion(rig,world,limb,candidate[m['body_roll']],candidate[m[limb+'_splay']])
                    residual.extend([(angle-np.deg2rad(elbowgoal))*8,max(0,angle+.12)*100])
                else:residual.extend([max(0,.1+native_hinge(rig,world,limb,seg,candidate[m['body_roll']],candidate[m[limb+'_splay']]))*30 for seg in ['knee','hock']])
                return np.r_[residual,(x-base[ids])*.008]
            start=base[ids] if previous is None or polish else previous[ids]
            solve=least_squares(leg,np.clip(start,lower+1e-7,upper-1e-7),bounds=(lower+1e-8,upper-1e-8),max_nfev=12 if polish else 45,ftol=1e-9,xtol=1e-9,gtol=1e-9)
            if fore and np.linalg.norm(np.asarray(leg(solve.x))[:2])>1:
                seed=base[ids].copy();restangle=action_elbow_flexion(rig,rig.asset.world_rest,limb,0)
                elbow=ids.index(m[limb+'_lower']);upper_index=ids.index(m[limb+'_upper']);foot=ids.index(m[limb+'_foot'])
                seed[elbow]=np.deg2rad(elbowgoal)-restangle
                seed[upper_index]+=.5*(base[ids][elbow]-seed[elbow])
                seed[foot]-=(seed[elbow]-base[ids][elbow])+(seed[upper_index]-base[ids][upper_index])
                alternative=least_squares(leg,np.clip(seed,lower+1e-7,upper-1e-7),bounds=(lower+1e-8,upper-1e-8),max_nfev=65,ftol=1e-9,xtol=1e-9,gtol=1e-9)
                if alternative.cost<solve.cost:solve=alternative
            p[ids]=solve.x
        # Once both pairs release, refine the unsupported body/limb pose
        # together. The trajectory is a solve variable; planted paws are
        # never lifted afterwards to repair an upper-limb collision.
        if second>max(guides['fore_support_end'],guides['hind_support_end']):
            world=rig.pose(p,world_only=True)[2]
            if rig.asset.skin(world)[:,1].min()<.0002:
                ids=[i for i,c in enumerate(rig.controls) if c['role'] not in ['jaw','tail_lower','tail_end','tail_tip']]+[rig.dof-1]
                base=p.copy()
                def clearance(x):
                    candidate=base.copy();candidate[ids]=x;w=rig.pose(candidate,world_only=True)[2]
                    return np.r_[[min(0,float(patches.points(k,w)[:,1].min())-.0005)/rig.asset.height*4000 for k in regions],
                        min(0,float(rig.asset.skin(w)[:,1].min())-.0005)/rig.asset.height*4000,(x-base[ids])*.2,(candidate[-1]-base[-1])*4]
                solve=least_squares(clearance,np.clip(base[ids],rig.lower[ids]+1e-7,rig.upper[ids]-1e-7),bounds=(rig.lower[ids]+1e-8,rig.upper[ids]-1e-8),max_nfev=20,ftol=1e-9,xtol=1e-9,gtol=1e-9)
                p[ids]=solve.x
        result[f]=p;previous=p
        if f%24==0:
            world=rig.pose(p,world_only=True)[2];diagnostics.append({'second':float(second),'chest_y':float(world[rig.roles['chest'],1,3]),'fore_elbow_degrees':float(np.rad2deg(action_elbow_flexion(rig,world,'fore_left',p[m['body_roll']],p[m['fore_left_splay']]))),'whole_surface_min_y':float(rig.asset.skin(world)[:,1].min())})
        if f%96==0:print('COLLAPSE_FRAME',f,'of',len(times),flush=True)
    return result,diagnostics
