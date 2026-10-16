"""Evaluated paw surfaces and continuous, speed-consistent stance fitting.

An in-place planted foot moves backwards. Adding the declared actor speed
must make its surface stationary; a frozen local foot is not a valid lock.
"""
from __future__ import annotations
import copy
import numpy as np
from scipy.interpolate import CubicSpline
from scipy.optimize import least_squares
from scipy.spatial.transform import Rotation
from .rig import LEG_NAMES,map_control_intent
from .asset import digest


def retarget_paw_forward(source_forward,source_pitch,source_center,source_pivot,
                         target_center,target_pivot,scale,pitch_scale=1.):
    """Transfer paw-pivot travel, then restore the target's own toe offset.

    A long claw must not shorten the rear half of a planted stride simply
    because its sole centroid is farther ahead of its ankle than the source.
    """
    if scale<=0 or pitch_scale<=0:raise ValueError('Paw transfer scales must be positive')
    source_offset=np.asarray(source_center)-np.asarray(source_pivot)
    target_offset=np.asarray(target_center)-np.asarray(target_pivot)
    angle=np.asarray(source_pitch,float);target_angle=angle*pitch_scale
    source_z=source_offset[1]*np.sin(angle)+source_offset[2]*np.cos(angle)
    target_z=target_offset[1]*np.sin(target_angle)+target_offset[2]*np.cos(target_angle)
    return target_pivot[2]+(np.asarray(source_forward)-source_z-source_pivot[2])*scale+target_z


class SurfacePatches:
    """Exact cached native skin subsets, indexed by reviewed anatomical regions."""
    def __init__(self,asset,regions):
        self.subsets={}
        for key,global_ids in regions.items():
            pieces=[];offset=0;global_ids=np.asarray(global_ids,int)
            for part in asset.parts:
                ids=global_ids[(global_ids>=offset)&(global_ids<offset+len(part['position']))]-offset
                if len(ids) and 'joints' in part:
                    subset={k:part[k] for k in ['nodes','inverse_bind']}
                    subset.update({k:part[k][ids] for k in ['position','joints','weights']});pieces.append(subset)
                offset+=len(part['position'])
            if not pieces:raise ValueError(f'{key} has no weighted surface')
            self.subsets[key]=pieces

    def points(self,key,world):
        result=[]
        for part in self.subsets[key]:
            transforms=world[part['nodes']]@part['inverse_bind'];points=np.zeros((len(part['position']),3))
            for k in range(part['joints'].shape[1]):
                points+=np.einsum('vab,vb->va',transforms[part['joints'][:,k],:3],part['position'])*part['weights'][:,k,None]
            result.append(points)
        return np.concatenate(result)


class PawSurfaces:
    """Small exact skin subsets, including toe/claw descendants and blending."""
    def __init__(self, rig):
        self.rig = rig
        self.subsets = {}
        self.bottom_ids = {}
        self.rest_centers = {}
        self.vertex_ids = {}
        self.bottom_vertex_ids = {}
        a = rig.asset
        for limb in LEG_NAMES:
            foot = rig.roles[limb + '_foot']
            # Some rest-floor heel vertices are mostly weighted to the ankle
            # or lower joint. Ownership by foot alone misses their penetration.
            descendants = {rig.roles[limb + '_lower']}
            for node in a.order:
                if a.parent[node] in descendants:
                    descendants.add(node)
            pieces, points, selected = [], [], []
            explicit=rig.profile.get('native_paw_surface_vertex_ids',{}).get(limb)
            if explicit is not None:
                raw=np.asarray(explicit)
                if raw.ndim!=1 or not np.issubdtype(raw.dtype,np.integer) or len(np.unique(raw))!=len(raw):
                    raise ValueError('Native paw vertex IDs must be unique integers')
                if np.any(raw<0) or np.any(raw>=len(a.rest_vertices)):
                    raise ValueError('Native paw vertex IDs are outside this asset')
                explicit=np.sort(raw)
            offset = 0
            for part in a.parts:
                if 'joints' not in part:
                    offset += len(part['position'])
                    continue
                owned = np.isin(part['nodes'][part['joints']], list(descendants))
                low = a.rest_vertices[offset:offset+len(part['position']),1] < rig.rest_markers[limb][1] + .20*a.height
                ids = (np.asarray(explicit,int) if explicit is not None else np.array([],int))
                ids = (ids[(ids>=offset)&(ids<offset+len(part['position']))]-offset if explicit is not None
                       else np.flatnonzero(((owned * part['weights']).sum(1) > .35) & low))
                if len(ids):
                    selected.extend((offset+ids).tolist())
                    subset = {k: part[k] for k in ('nodes', 'inverse_bind')}
                    subset.update({k: part[k][ids] for k in ('position', 'joints', 'weights')})
                    pieces.append(subset)
                offset += len(part['position'])
            self.subsets[limb] = pieces
            self.vertex_ids[limb]=np.asarray(selected,int)
            p = self.points(limb, a.world_rest)
            if len(p) < 3:
                raise ValueError(f'{limb} has no usable weighted paw surface')
            declared=rig.profile.get('native_paw_bottom_vertex_ids',{}).get(limb)
            if declared is not None and (np.asarray(declared).ndim!=1 or
                    not np.issubdtype(np.asarray(declared).dtype,np.integer) or
                    len(np.unique(declared))!=len(declared) or
                    not np.isin(declared,self.vertex_ids[limb]).all()):
                raise ValueError('Native bottom vertices must belong to the paw surface')
            self.bottom_ids[limb] = (np.flatnonzero(np.isin(self.vertex_ids[limb],declared)) if declared is not None
                                   else np.flatnonzero(p[:, 1] <= np.quantile(p[:, 1], .15) + .001 * a.height))
            if len(self.bottom_ids[limb])<3:raise ValueError('A native sole patch needs at least three bottom vertices')
            self.bottom_vertex_ids[limb]=self.vertex_ids[limb][self.bottom_ids[limb]]
            self.rest_centers[limb] = p[self.bottom_ids[limb]].mean(0)

    def points(self, limb, world):
        result = []
        for part in self.subsets[limb]:
            transforms = world[part['nodes']] @ part['inverse_bind']
            positions = np.zeros((len(part['position']), 3))
            for k in range(part['joints'].shape[1]):
                positions += np.einsum('vab,vb->va', transforms[part['joints'][:, k], :3], part['position']) * part['weights'][:, k, None]
            result.append(positions)
        return np.concatenate(result)

    def center(self, limb, world):
        return self.points(limb, world)[self.bottom_ids[limb]].mean(0)

    def pitch(self, limb, world, segment='foot'):
        node = self.rig.roles[limb + '_' + segment]
        delta = world[node, :3, :3] @ np.linalg.inv(self.rig.asset.world_rest[node, :3, :3])
        return float(Rotation.from_matrix(delta).as_rotvec() @ self.rig.axis)


def trajectory(times, duration, touchdown_phase, duty, speed, center, lift):
    """C1 periodic path: linear stance, smooth return with matching end speeds."""
    phase = (np.asarray(times) / duration - touchdown_phase) % 1
    stance = phase <= duty
    stride = speed * duration * duty
    z = center + stride / 2 - speed * phase * duration
    y = np.zeros_like(z)
    u = (phase[~stance] - duty) / (1 - duty)
    # Hermite return has the same backwards velocity at lift-off/touchdown.
    tangent = -speed * duration * (1 - duty)
    z[~stance] = center - stride / 2 + stride * (3*u*u - 2*u*u*u) + tangent * (2*u*u*u - 3*u*u + u)
    y[~stance] = lift * np.sin(np.pi * u)**2
    return np.column_stack([y, z]), stance


def swing_orientation(times, duration, leg, segment):
    """Pose-guide rotations vanish smoothly at both contact transitions."""
    guide=leg.get('swing_'+segment+'_pitch_guide')
    if guide is None:
        return np.zeros(len(times))
    phase=(np.asarray(times)/duration-leg['touchdown_phase'])%1
    airborne=phase>leg['stance_fraction']
    u=(phase[airborne]-leg['stance_fraction'])/(1-leg['stance_fraction'])
    knots=np.asarray(guide['swing_fractions'])
    degrees=np.asarray(guide['degrees'])
    if knots[0]!=0 or knots[-1]!=1 or degrees[0]!=0 or degrees[-1]!=0:
        raise ValueError('Swing orientation guides must begin/end at neutral contact')
    result=np.zeros(len(times))
    result[airborne]=np.deg2rad(CubicSpline(knots,degrees,bc_type=((1,0),(1,0)))(u))
    return result


def elbow_flexion(rig,world,limb):
    """Real elbow: wrist for a serial carpus, paw for a sibling heel helper."""
    upper=world[rig.roles[limb+'_upper'],:3,3]
    elbow=world[rig.roles[limb+'_lower'],:3,3]
    foot=world[elbow_endpoint(rig,limb),:3,3]
    a,b=elbow-upper,foot-elbow
    return float(np.arctan2(np.cross(a,b)@rig.axis,a@b))


def elbow_endpoint(rig,limb):
    foot=rig.roles[limb+'_foot'];ankle=rig.roles.get(limb+'_ankle')
    if ankle is not None:
        parent=int(rig.asset.parent[foot])
        while parent>=0 and parent!=ankle:parent=int(rig.asset.parent[parent])
        if parent==ankle:return ankle
    return foot


def shoulder_direction(rig, world, limb):
    """Scapula-to-upper offset in the chest's rest-aligned side plane.

    This is a rotation goal, not an anatomical joint inferred through fur.
    Native anchor lengths and unobserved depth remain unchanged on transfer.
    """
    anchor, upper = (rig.roles[limb+'_'+s] for s in ('anchor','upper'))
    chest = rig.roles['chest']
    delta = world[chest,:3,:3] @ np.linalg.inv(rig.asset.world_rest[chest,:3,:3])
    offset = np.linalg.solve(delta, world[upper,:3,3]-world[anchor,:3,3])
    rest = rig.asset.world_rest[upper,:3,3]-rig.asset.world_rest[anchor,:3,3]
    length = np.linalg.norm([rest@rig.up, rest@rig.forward])
    if length < 1e-6:
        raise ValueError('A shoulder direction guide requires a nonzero side-plane anchor offset')
    return np.array([offset@rig.up,offset@rig.forward])/length


def fit_contacts(rig, times, body_parameters, gait, max_evaluations=65,
                 limbs=LEG_NAMES, preserve_stance=False):
    """Keep body motion, solve each actual paw against its own target surface."""
    paws = PawSurfaces(rig)
    limb_surfaces=None
    if gait.get('enforce_limb_clearance',False):
        regions={}
        for limb in LEG_NAMES:
            owned={rig.roles[limb+'_upper']}
            for node in rig.asset.order:
                if rig.asset.parent[node] in owned:owned.add(node)
            ids=[];offset=0
            for part in rig.asset.parts:
                mass=(np.isin(part['nodes'][part['joints']],list(owned))*part['weights']).sum(1)
                ids.extend((offset+np.flatnonzero(mass>.35)).tolist());offset+=len(part['position'])
            regions[limb]=ids
        limb_surfaces=SurfacePatches(rig.asset,regions)
    if not (np.allclose(rig.up,[0,1,0]) and np.allclose(rig.forward,[0,0,1]) and np.allclose(rig.axis,[1,0,0])):
        raise ValueError('The current contact solver requires Y-up, +Z forward, +X depth; canonicalize the actor first')
    times = np.asarray(times)
    height, duration = rig.asset.height, float(times[-1])
    speed = gait['speed_native_units_per_second']
    if speed <= 0 or duration <= 0 or set(gait['legs']) != set(LEG_NAMES):
        raise ValueError('A walking contact model requires positive speed/duration and four identified limbs')
    if any(not 0 < leg['stance_fraction'] < 1 or leg['swing_clearance_height'] <= 0 for leg in gait['legs'].values()):
        raise ValueError('Each leg requires a stance fraction within (0,1) and positive swing clearance')
    paths, contacts,orientation = {}, {},{}
    for limb, leg in gait['legs'].items():
        center = paws.rest_centers[limb][2] + leg.get('center_offset_height', 0) * height
        paths[limb], contacts[limb] = trajectory(times, duration, leg['touchdown_phase'],
            leg['stance_fraction'], speed, center, leg['swing_clearance_height'] * height)
        orientation[limb]={seg:swing_orientation(times,duration,leg,seg) for seg in ('foot','ankle')}
    result = np.asarray(body_parameters).copy()
    diagnostics = []
    role_ids = {c['role']: i for i, c in enumerate(rig.controls)}
    # Proportion adapters can lower the target body without stretching bones.
    result[:, -1] = gait['body_height_offset_native'] + gait.get('body_bob_height', .005) * height * np.cos(4*np.pi*times/duration)
    if 'tail_angle_degrees' in gait and 'tail' in role_ids:
        result[:, role_ids['tail']] = np.deg2rad(gait['tail_angle_degrees'])
    requested=list(limbs)
    groups=[]
    for group in gait.get('coupled_contact_groups',[]):
        if len(group)<2 or len(set(group))!=len(group) or any(l not in LEG_NAMES for l in group):
            raise ValueError('Coupled contact groups require distinct identified limbs')
        if all(l in requested for l in group):
            groups.append(group)
            requested=[l for l in requested if l not in group]
    groups.extend([[l] for l in requested])
    for group in groups:
        ids = [i for i,c in enumerate(rig.controls) if any(c['role'].startswith(l+'_') for l in group)]
        previous = None
        for f in range(len(times)-1):
            values = result[f].copy()
            seed = values[ids].copy()
            if preserve_stance and all(contacts[l][f] for l in group):
                previous=seed
                continue
            if preserve_stance and len(group)>1:
                raise ValueError('Mixed-support coupled fitting cannot freeze a stance subset')
            def residual(x):
                pose = values.copy()
                pose[ids] = x
                world = rig.pose(pose,world_only=True)[2]
                residuals=[]
                for limb in group:
                    target_y, target_z = paths[limb][f]
                    points = paws.points(limb, world)
                    center = points[paws.bottom_ids[limb]].mean(0)
                    # Shared skin influences require simultaneous surface
                    # constraints; a sequential solve can move the first paw.
                    position_weight=gait.get('contact_position_weight',160)
                    residuals.extend([(points[:, 1].min() - target_y - .0005) / height * position_weight,
                                 (center[2] - target_z) / height * position_weight,
                                 (paws.pitch(limb, world)-orientation[limb]['foot'][f]) * gait.get('foot_orientation_weight',12)])
                    if limb_surfaces is not None:
                        residuals.append(min(0,limb_surfaces.points(limb,world)[:,1].min()-.0003)/height*300)
                        elbow=world[rig.roles[limb+'_lower'],1,3]
                        residuals.append(min(0,elbow-center[1]-.03*height)/height*160 if contacts[limb][f] else 0)
                    if limb+'_ankle' in rig.roles:
                        weight=gait.get('ankle_orientation_weight',8)
                        if 'swing_ankle_pitch_guide' in gait['legs'][limb] and not contacts[limb][f]:
                            weight=gait['legs'][limb].get('swing_ankle_orientation_weight',12)
                        residuals.append((paws.pitch(limb,world,'ankle')-orientation[limb]['ankle'][f])*weight)
                    if 'elbow_pole_sign' in gait['legs'][limb]:
                        sign=gait['legs'][limb]['elbow_pole_sign']
                        residuals.append(max(0,.10-sign*elbow_flexion(rig,world,limb))*20)
                    guide = gait['legs'][limb].get('shoulder_direction_guide')
                    if guide is not None:
                        target = np.asarray(guide['up_forward_unit_vector'],float)
                        if target.shape != (2,) or not np.isclose(np.linalg.norm(target),1):
                            raise ValueError('A shoulder direction guide requires a unit [up, forward] vector')
                        residuals.extend((shoulder_direction(rig,world,limb)-target)*guide.get('weight',12))
                residuals.extend((x - seed) * .09)
                if previous is not None:
                    residuals.extend((x - previous) * .06)
                return np.asarray(residuals)
            lower, upper = rig.lower[ids], rig.upper[ids]
            start = seed if previous is None else previous
            solved = least_squares(residual, np.clip(start, lower+1e-7, upper-1e-7),
                bounds=(lower, upper), max_nfev=max_evaluations, ftol=1e-8, xtol=1e-8, gtol=1e-8)
            # Weighted sole minima are piecewise smooth. A previous-frame
            # seed can stall on the wrong skin feature even when neutral
            # reaches the same native branch. Retry, without weakening goals.
            if solved.cost>.05:
                alternate=least_squares(residual,np.clip(seed,lower+1e-7,upper-1e-7),
                    bounds=(lower,upper),max_nfev=max(120,max_evaluations),
                    ftol=1e-10,xtol=1e-10,gtol=1e-10,diff_step=1e-5)
                if alternate.cost<solved.cost:solved=alternate
            result[f, ids] = solved.x
            previous = solved.x.copy()
            diagnostics.extend({'limb': limb, 'coupled_group':group,'frame': f, 'cost': float(solved.cost),
                                'converged': bool(solved.success)} for limb in group)
        result[-1, ids] = result[0, ids]
        print('CONTACT_FIT', ','.join(group), flush=True)
    result[-1] = result[0]
    return result, diagnostics


def contact_bake(rig, times, parameters, fps=192):
    """Contact already solved in the pose; never shift every paw to clear a tail."""
    times = np.asarray(times)
    dense_times = np.linspace(0, times[-1], round(times[-1] * fps) + 1)
    values = CubicSpline(times, parameters, bc_type='periodic')(dense_times)
    t, q = [], []
    for row in values:
        translations, rotations, _ = rig.pose(row)
        t.append(translations)
        q.append(rotations)
    return dense_times, np.asarray(t), np.asarray(q)


def contact_package(prior, rig, times, parameters, gait, diagnostics):
    package = copy.deepcopy(prior)
    paws = PawSurfaces(rig)
    paths = {l: [] for l in LEG_NAMES}
    for row in parameters:
        world = rig.pose(row)[2]
        for limb in LEG_NAMES:
            paths[limb].append((paws.center(limb, world)-paws.rest_centers[limb])/rig.leg_lengths[limb])
    duration = float(times[-1])
    package.update({'schema_version': 2, 'times_seconds': times.tolist(),
        'sample_fps': float((len(times)-1)/duration), 'duration_seconds': duration,
        'parameters_radians_and_root_height': parameters.tolist(),
        'controls': [c['role'] for c in rig.controls], 'gait_contact_model': gait,
        'source_sole_rest_centers': {l:p.tolist() for l,p in paws.rest_centers.items()},
        'normalized_sole_trajectories': {l:np.asarray(v).tolist() for l,v in paths.items()},
        'contact_flags': {l:(((times/duration-gait['legs'][l]['touchdown_phase'])%1)<=gait['legs'][l]['stance_fraction']).tolist() for l in LEG_NAMES},
        'contact_fit_diagnostics': diagnostics,
        'post_processing': {'method':'continuous stance plus exact weighted surface IK',
            'export_bake_fps':192, 'loop_policy':'periodic trajectories and pose spline; no terminal stride compression'},
        'status':'contact_polish_candidate_pending_independent_review'})
    return package


def transfer_contact_motion(package, target_rig, max_evaluations=65):
    if package['category'] != target_rig.profile['category'] or package.get('subcategory') != target_rig.profile.get('subcategory'):
        raise ValueError('Contact transfer requires a compatible category and gait family')
    times = np.asarray(package['times_seconds'])
    source = np.asarray(package['parameters_radians_and_root_height'])
    mapping = {r:i for i,r in enumerate(package['controls'])}
    seed = map_control_intent(package['controls'],source,target_rig)
    from .secondary import apply_tail_intent
    seed = apply_tail_intent(package, target_rig, seed)
    ratio = float(np.median([target_rig.leg_lengths[l]/package['source_leg_lengths'][l] for l in LEG_NAMES]))
    height_ratio = target_rig.asset.height/package['source_height']
    paws = PawSurfaces(target_rig)
    source_y = float(np.median([p[1] for p in package['source_sole_rest_centers'].values()]))
    target_y = float(np.median([p[1] for p in paws.rest_centers.values()]))
    gait = copy.deepcopy(package['gait_contact_model'])
    gait['speed_native_units_per_second'] *= ratio
    gait['body_height_offset_native'] = gait['body_height_offset_native']*height_ratio + source_y*height_ratio - target_y
    gait['body_bob_height'] = gait.get('body_bob_height',.005)*ratio/height_ratio
    for leg in gait['legs'].values():
        leg['swing_clearance_height'] *= ratio/height_ratio
        leg['center_offset_height'] = leg.get('center_offset_height',0)*ratio/height_ratio
    # Rest-pose-specific clearance belongs to the target profile, not the
    # category gait. E.g. the Dire Wolf's hanging tail needs separate lifting.
    gait.update(target_rig.profile.get('contact_adaptation',{}))
    gait['transfer_policy'] = {'common_step_scale':ratio, 'scale_basis':'median target/source leg length',
        'stance_speed':'one speed for all four paws', 'contact':'target evaluated paw vertices',
        'extra_target_joints':'neutral rest pose'}
    result, diagnostics = fit_contacts(target_rig,times,seed,gait,max_evaluations)
    return result, diagnostics, gait


def evaluate_contacts(asset, rig, gait, fps=192):
    """Independent exported sampling with a declared moving-world speed."""
    paws = PawSurfaces(rig)
    duration = asset.duration('Walk')
    times = np.linspace(0, duration, round(duration * fps)+1)
    t, q = asset.sample('Walk', times)
    positions = {l: [] for l in LEG_NAMES}
    minima = {l: [] for l in LEG_NAMES}
    pitch = {l: [] for l in LEG_NAMES}
    surface_minimum = float('inf')
    for ti, qi in zip(t, q):
        world = asset.world(ti, qi)
        surface_minimum = min(surface_minimum, float(asset.skin(world)[:, 1].min()))
        for limb in LEG_NAMES:
            p = paws.points(limb, world)
            positions[limb].append(p[paws.bottom_ids[limb]].mean(0))
            minima[limb].append(float(p[:, 1].min()))
            pitch[limb].append(paws.pitch(limb, world))
    speed = gait['speed_native_units_per_second']
    legs = {}
    for limb in LEG_NAMES:
        position = np.asarray(positions[limb])
        leg = gait['legs'][limb]
        phase = (times/duration - leg['touchdown_phase']) % 1
        # Exclude 1/192 s at transitions from derivative statistics.
        core = (phase > 1/(fps*duration)) & (phase < leg['stance_fraction']-1/(fps*duration))
        velocity = np.gradient(position, times, axis=0)
        velocity[:,2] += speed
        residual = np.linalg.norm(velocity[:,[0,2]],axis=1)
        floor = np.asarray(minima[limb])
        legs[limb] = {'forward_excursion_native': float(np.ptp(position[:,2])),
            'forward_excursion_height_fraction': float(np.ptp(position[:,2])/rig.asset.height),
            'stance_floor_max_abs_native': float(np.max(np.abs(floor[core]))),
            'stance_horizontal_slide_rms_native_per_second': float(np.sqrt(np.mean(residual[core]**2))),
            'stance_horizontal_slide_p95_native_per_second': float(np.quantile(residual[core],.95)),
            'stance_foot_pitch_max_degrees': float(np.max(np.abs(np.asarray(pitch[limb])[core]))*180/np.pi),
            'swing_clearance_max_native': float(np.max(floor)),
            'minimum_paw_surface_y': float(floor.min())}
    contact_pass = all(leg['stance_floor_max_abs_native'] <= .002*rig.asset.height and
        leg['stance_horizontal_slide_rms_native_per_second'] <= .01*speed and
        leg['stance_horizontal_slide_p95_native_per_second'] <= .02*speed and
        leg['stance_foot_pitch_max_degrees'] < 3 for leg in legs.values())
    contact_pass = contact_pass and surface_minimum >= -.001*rig.asset.height
    return {'speed_native_units_per_second': speed, 'duration_seconds': duration,
        'sampling_fps': fps, 'minimum_entire_surface_y': surface_minimum, 'legs': legs,
        'contact_pass': bool(contact_pass),
        'pass_tolerances': {'stance_floor_abs_height_fraction':.002,
            'stance_slide_rms_speed_fraction':.01,'stance_slide_p95_speed_fraction':.02,
            'foot_pitch_degrees':3,'entire_surface_floor_height_fraction':.001},
        'slide_measurement': 'Horizontal velocity of the same evaluated sole vertices after adding actor forward speed; stance cores only.'}


def evaluate_foreleg_articulation(asset,rig,gait,fps=192):
    """Check actual hinge direction and airborne pose independently of contacts."""
    paws=PawSurfaces(rig)
    duration=asset.duration('Walk')
    times=np.linspace(0,duration,round(duration*fps)+1)
    t,q=asset.sample('Walk',times)
    reports={}
    for limb in ('fore_left','fore_right'):
        leg=gait['legs'][limb]
        phase=(times/duration-leg['touchdown_phase'])%1
        u=(phase-leg['stance_fraction'])/(1-leg['stance_fraction'])
        swing=(u>.1)&(u<.9)
        flexion,pitch=[],[]
        for ti,qi in zip(t,q):
            world=asset.world(ti,qi)
            flexion.append(elbow_flexion(rig,world,limb)*180/np.pi)
            pitch.append(paws.pitch(limb,world)*180/np.pi)
        flexion,pitch=np.asarray(flexion),np.asarray(pitch)
        expected=swing_orientation(times,duration,leg,'foot')*180/np.pi
        sign=leg.get('elbow_pole_sign')
        error=float(np.sqrt(np.mean((pitch[swing]-expected[swing])**2)))
        # A swing-only gate missed the wrong stance bow. Check the complete
        # cycle against the reviewed branch, independently of terminal pitch.
        pole_pass=sign is None or float((sign*flexion).min())>5
        upper_yz=[]
        for ti,qi in zip(t,q):
            world=asset.world(ti,qi)
            upper,elbow,foot=(world[rig.roles[limb+'_'+s],:3,3] for s in ('upper','lower','foot'))
            chord=foot-upper
            fraction=float((elbow-upper)@chord/max(chord@chord,1e-12))
            upper_yz.append(float((upper+fraction*chord-elbow)@rig.forward))
        reports[limb]={'signed_elbow_flexion_min_degrees':float(flexion[swing].min()),
            'signed_elbow_flexion_max_degrees':float(flexion[swing].max()),
            'whole_cycle_signed_elbow_min_degrees':float(flexion.min()),
            'whole_cycle_signed_elbow_max_degrees':float(flexion.max()),
            'elbow_backward_bow_min_native':float(min(upper_yz)),
            'elbow_backward_bow_max_native':float(max(upper_yz)),
            'airborne_paw_pitch_max_degrees':float(pitch[swing].max()),
            'airborne_pose_guide_rms_error_degrees':error,'elbow_pole_pass':bool(pole_pass),
            'passed':bool(pole_pass and error<3)}
    return {'exported_motion_sampled':True,'export_sha256':digest(asset.path),'sampling_fps':fps,'forelegs':reports,
        'articulation_pass':all(r['passed'] for r in reports.values()),
        'measurement':'True upper/lower/foot hinge; named ankle helper is not assumed to be in the serial chain.'}


def evaluate_shoulders(asset,rig,gait,fps=384):
    """Sample exported chest-relative orientation and upper origins.

    A passing direction goal certifies authored placement intent, not a hidden
    joint's position in the generated video. Deformed images are a separate gate.
    """
    duration=asset.duration('Walk')
    times=np.linspace(0,duration,round(duration*fps)+1)
    t,q=asset.sample('Walk',times)
    reports={}
    for limb in ('fore_left','fore_right'):
        guide=gait['legs'][limb]['shoulder_direction_guide']
        target=np.asarray(guide['up_forward_unit_vector'])
        directions,origins=[],[]
        for ti,qi in zip(t,q):
            world=asset.world(ti,qi)
            directions.append(shoulder_direction(rig,world,limb))
            origins.append(world[rig.roles[limb+'_upper'],:3,3])
        directions=np.asarray(directions)
        angles=np.rad2deg(np.arccos(np.clip(directions@target,-1,1)))
        reports[limb]={'guide_angular_error_rms_degrees':float(np.sqrt(np.mean(angles**2))),
            'guide_angular_error_max_degrees':float(angles.max()),
            'mean_upper_origin_gltf':np.mean(origins,axis=0).tolist(),
            'mean_chest_relative_up_forward_direction':directions.mean(0).tolist(),
            'passed':bool(angles.max()<3)}
    return {'export_sha256':digest(asset.path),'sampling_fps':fps,'forelegs':reports,
        'shoulder_pass':all(v['passed'] for v in reports.values()),
        'measurement':'Authored chest-relative scapula orientation; native lengths/depth preserved; the fur-occluded video pivot is not claimed as measured.'}
