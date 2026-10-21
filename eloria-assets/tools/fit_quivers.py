"""Fit imported Meshy quivers to the sixteen current player bodies.

The case and seated arrows are rigid spine equipment. The existing shoulder
strap is reshaped around the wearer and inherits the body's own skin blend.
Thin cases include an authored Cape_Clearance morph for the cape-on fit;
their default geometry stays fitted to the body when the cape is removed.
No geometry is generated and no retired equipment is selected.

Prepare compact sources once with --prepare <original-model-directory>.
Build into a new --out stage; --install promotes only this quiver set.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

import numpy as np
from scipy.interpolate import CubicSpline, UnivariateSpline
from scipy.spatial import cKDTree
from scipy.ndimage import gaussian_filter1d

import conform_equipment as ce
import equipment_authoring as ea

ROOT = Path(__file__).resolve().parents[2]
CLIENT = ROOT / 'godot-client'
SOURCE = ROOT / 'eloria-assets/source/quivers'
NATIVE = CLIENT / 'assets/actors/native'
CATALOG = SOURCE / 'catalog.json'
PART = 8


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def normalise(values):
    return values / np.maximum(np.linalg.norm(values, axis=-1, keepdims=True), 1e-12)


def surface_normals(points, faces):
    # Weld normals across UV seams without merging or reindexing source UVs.
    _, inverse = np.unique(np.round(points, 6), axis=0, return_inverse=True)
    face_normals = np.cross(points[faces[:, 1]] - points[faces[:, 0]],
                            points[faces[:, 2]] - points[faces[:, 0]])
    result = np.zeros((int(inverse.max()) + 1, 3))
    for corner in range(3):
        np.add.at(result, inverse[faces[:, corner]], face_normals)
    return normalise(result)[inverse]


def write_mesh(path, surface, texture, rig=None, joints=None, weights=None,
               cape_surface=None):
    glb = ea.EquipmentGLB(generator='Rabbit Lands imported Meshy quiver fitting')
    material = ce.textured_material(glb, 'Quiver painted base', texture,
                                    double_sided=True)
    if texture and texture.startswith(b'\xff\xd8'):
        glb.doc['images'][0]['mimeType'] = 'image/jpeg'
    if rig is not None:
        glb.skeleton(rig)
    primitive = glb.primitive(surface.positions, surface.normals, surface.uvs,
                              surface.indices, material, joints=joints,
                              weights=weights, weight_floats=True)
    if cape_surface is not None:
        primitive['targets'] = [{
            'POSITION': glb.accessor(np.asarray(
                cape_surface.positions-surface.positions, dtype='float32'),
                'VEC3', target=34962, bounds=True),
            'NORMAL': glb.accessor(np.asarray(
                cape_surface.normals-surface.normals, dtype='float32'),
                'VEC3', target=34962),
        }]
    glb.mesh('Quiver', [primitive], skin=0 if rig is not None else None)
    if cape_surface is not None:
        glb.doc['meshes'][-1].update(
            weights=[0.0], extras={'targetNames': ['Cape_Clearance']})
    glb.write(path)


def prepare(originals, assets):
    records = []
    for entry in assets:
        original = originals / (entry['id'] + '.glb')
        source = SOURCE / (entry['id'] + '.glb')
        surface, texture = ce.read_source(original)
        # Preserve the approved base colour; the website pilot's incidental
        # PBR maps are not part of the painted runtime material.
        write_mesh(source, surface, texture)
        records.append({'id': entry['id'], 'providerSourceSha256': digest(original),
                        'sourceSha256': digest(source), 'triangles': len(surface.indices)//3})
    (SOURCE/'sources.json').write_bytes((json.dumps(records, indent=2)+'\n').encode('utf-8'))


def body_samples(rig):
    wanted = ['spine_01', 'spine_02', 'spine_03', 'clavicle_l', 'clavicle_r', 'pelvis']
    dominant = rig.joints[np.arange(len(rig.joints)), rig.weights.argmax(axis=1)]
    mask = np.isin(dominant, [rig.joint_names.index(n) for n in wanted])
    if rig.tail is not None:
        mask &= ~rig.tail
    points = rig.positions[mask]
    normals = surface_normals(rig.positions, rig.faces)[mask]
    return points, normals


def strap_section(t, radial, depth, blend):
    """Unwrap the imported loop about its measured centre, keeping its buckle.

    A constant depth centre and an elliptical radius turn a crooked source
    loop into a twisted chest band. Measure the centre along the actual loop
    before turning its broad cross-section onto the wearer's chest.
    """
    centers = []
    residuals = []
    sections = []
    for low in np.arange(.06, .94, .035):
        mask = (blend > .99) & (t >= low) & (t < low+.035)
        if mask.sum() < 6:
            continue
        points = np.column_stack([radial[mask], depth[mask]])
        center = np.median(points, axis=0)
        centers.append([np.median(t[mask]), *center])
        _, section_axes = np.linalg.eigh(np.cov((points-center).T))
        section_axis = section_axes[:, -1]
        sections.append([np.median(t[mask]),
                         np.arctan2(-section_axis[1], section_axis[0])])
        if .2 < low < .75:
            residuals.extend(points-center)
    centers = np.asarray(centers)
    _, axes = np.linalg.eigh(np.cov(np.asarray(residuals).T))
    axis = axes[:, -1]
    roll = float(np.arctan2(-axis[1], axis[0]) % np.pi)
    sections = np.asarray(sections)
    angles = np.unwrap(2.*sections[:, 1])/2.
    angles += np.pi*round((roll-np.median(angles))/np.pi)
    local_roll = UnivariateSpline(sections[:, 0], angles,
                                  s=len(sections)*.04, ext=3)(t)
    radial_center = UnivariateSpline(centers[:, 0], centers[:, 1],
                                    s=len(centers)*.00015, ext=3)(t)
    depth_center = UnivariateSpline(centers[:, 0], centers[:, 2],
                                   s=len(centers)*.00015, ext=3)(t)
    radial -= radial_center
    depth -= depth_center
    side = radial*np.cos(local_roll)-depth*np.sin(local_roll)
    outside = radial*np.sin(local_roll)+depth*np.cos(local_roll)
    return side, outside, float(np.rad2deg(roll))


def front_depth(rig, points):
    """Intersect the actual body's triangles along +Z, without an oval proxy."""
    triangles = rig.positions[rig.faces]
    triangles = triangles[(triangles[:, :, 1].max(1) >= points[:, 1].min()) &
                          (triangles[:, :, 1].min(1) <= points[:, 1].max())]
    a, b, c = triangles[:, 0], triangles[:, 1], triangles[:, 2]
    determinant = (b[:, 1]-c[:, 1])*(a[:, 0]-c[:, 0])+(c[:, 0]-b[:, 0])*(a[:, 1]-c[:, 1])
    valid = abs(determinant) > 1e-12
    a, b, c, determinant = a[valid], b[valid], c[valid], determinant[valid]
    result = []
    for start in range(0, len(points), 128):
        p = points[start:start+128, None, :]
        u = ((b[:, 1]-c[:, 1])*(p[:, :, 0]-c[:, 0])+
             (c[:, 0]-b[:, 0])*(p[:, :, 1]-c[:, 1]))/determinant
        v = ((c[:, 1]-a[:, 1])*(p[:, :, 0]-c[:, 0])+
             (a[:, 0]-c[:, 0])*(p[:, :, 1]-c[:, 1]))/determinant
        inside = (u >= -1e-6) & (v >= -1e-6) & (u+v <= 1.000001)
        z = u*a[:, 2]+v*b[:, 2]+(1-u-v)*c[:, 2]
        result.extend(np.where(inside, z, -np.inf).max(1))
    return np.asarray(result)


def trunk_radius(rig, points, middle_z):
    """Intersect horizontal rays with the skinned trunk, excluding sleeves."""
    owners = rig.joints[np.arange(len(rig.joints)), rig.weights.argmax(1)]
    names = ['pelvis', 'spine_01', 'spine_02', 'spine_03', 'clavicle_l', 'clavicle_r']
    trunk = np.isin(owners, [rig.joint_names.index(n) for n in names])
    faces = rig.faces[trunk[rig.faces].all(1)]
    triangles = rig.positions[faces]
    a, b, c = triangles[:, 0], triangles[:, 1], triangles[:, 2]
    ab, ac = b-a, c-a
    output = []
    for point in points:
        origin = np.array([0., point[1], middle_z])
        direction = point-origin
        direction[1] = 0.
        direction = normalise(direction)
        h = np.cross(np.broadcast_to(direction, ac.shape), ac)
        determinant = np.einsum('ij,ij->i', ab, h)
        divisor = np.where(abs(determinant) > 1e-12, determinant, np.inf)
        relative = origin-a
        u = np.einsum('ij,ij->i', relative, h)/divisor
        q = np.cross(relative, ab)
        v = (q@direction)/divisor
        distance = np.einsum('ij,ij->i', ac, q)/divisor
        hit = (u >= -1e-6) & (v >= -1e-6) & (u+v <= 1.000001) & (distance > 0.)
        output.append(float(distance[hit].max()) if hit.any() else np.nan)
    return np.asarray(output)


def fit(entry, source, rig, *, back_offset=0.0, case_tilt_degrees=0.0):
    surface, texture = ce.read_source(source)
    original = surface.positions.copy()
    bottom, top = np.array(entry['bottom']), np.array(entry['top'])
    length = float(np.linalg.norm(top-bottom))
    u = normalise(top-bottom)
    v = np.array(entry['loop'], dtype=float)
    v = normalise(v-u*np.dot(u, v))
    w = np.cross(u, v)
    local = (original-(top+bottom)*.5) @ np.stack([u, v, w], axis=1)
    along, across, depth = local.T
    samples, body_normals = body_samples(rig)
    stature = float(rig.origin('Head')[1])/1.568490028858185
    shoulder_y = float(rig.origin('upperarm_r')[1])
    pelvis_y = float(rig.origin('pelvis')[1])
    target_u = normalise(np.array([-.33, .944, 0.]))
    outward = np.array([0., 0., -1.])
    if entry['front'] == '-v':
        target_v = -outward
        target_w = np.cross(target_u, target_v)
    else:
        target_w = outward * (1 if entry['front'] == '+w' else -1)
        target_v = np.cross(target_w, target_u)
    target_basis = np.stack([target_u, target_v, target_w], axis=1)
    case_scale = float(entry.get('caseScale', 1.0))
    if not np.isfinite(case_scale) or case_scale <= 0:
        raise ValueError(f'Invalid case scale for {entry["id"]}: {case_scale}')
    scale = (shoulder_y-pelvis_y-.05*stature)/length * case_scale
    fixed = local @ target_basis.T * scale
    # Limit the strap mask to the loop side of the measured case frame.
    blend = np.clip((across-length*float(entry.get("strapStart", .17)))/(length*.07), 0., 1.)
    blend = blend*blend*(3.-2.*blend)
    bag = blend < .01
    torso = samples[(samples[:,1] > pelvis_y+.10*stature) &
                    (samples[:,1] < shoulder_y-.05*stature)]
    back = float(np.quantile(torso[:,2], .015))
    center = np.array([0., (shoulder_y+pelvis_y)*.5,
                       back-float(fixed[bag,2].max())-.012*stature])
    center[2] -= back_offset
    fixed += center
    if case_tilt_degrees:
        angle=np.deg2rad(case_tilt_degrees)
        rotation=np.array([[1.,0.,0.],[0.,np.cos(angle),-np.sin(angle)],
                           [0.,np.sin(angle),np.cos(angle)]])
        # Keep the opening at the shoulder while the rigid lower case tips
        # out over a shorter body's flared cape. No case scaling or bending.
        pivot=center+target_u*(length*.44*scale)
        fixed=(fixed-pivot)@rotation.T+pivot
        center=rotation@(center-pivot)+pivot
        target_u=rotation@target_u
        target_v=rotation@target_v
    width = float(np.quantile(torso[:,0], .98)-np.quantile(torso[:,0], .02))
    front = float(np.quantile(torso[:,2], .985))+.035*stature
    middle_z = float(np.median(torso[:,2]))
    upper = center+target_u*(length*.44*scale)+target_v*(length*.14*scale)
    lower = center-target_u*(length*.44*scale)+target_v*(length*.14*scale)
    anchors = np.array([
        upper,
        [-width*.43, shoulder_y+.025*stature, middle_z],
        [-width*.36, shoulder_y-.08*stature, front],
        [width*.07, (shoulder_y+pelvis_y)*.5+.015*stature, front],
        [width*.48, pelvis_y+.10*stature, front*.75+middle_z*.25],
        [width*.48, pelvis_y+.07*stature, middle_z],
        lower,
    ])
    parameters = np.r_[0., np.cumsum(np.linalg.norm(np.diff(anchors,axis=0),axis=1))]
    parameters /= parameters[-1]
    curve = CubicSpline(parameters, anchors, bc_type='natural')
    loop_radius = max(float(np.quantile(across, .99))-length*.10, length*.20)
    axial_radius = length*.60
    theta = np.arctan2(along/axial_radius, (across-length*.10)/loop_radius)
    t = np.clip((np.pi*.5-theta)/np.pi, 0., 1.)
    ring = np.sqrt((along/axial_radius)**2+((across-length*.10)/loop_radius)**2)
    radial_offset = (ring-1.)*min(loop_radius,axial_radius)*scale
    # Fit a dense centreline to the actual chest before orienting the ribbon.
    # A shared depth plane bridges a narrow waist and cuts through a bust.
    path_t = np.linspace(0., 1., 257)
    line = curve(path_t)
    radii = trunk_radius(rig, line, middle_z)
    valid_chest = np.flatnonzero(np.isfinite(radii))
    smoothed = gaussian_filter1d(np.interp(path_t, path_t[valid_chest],
                                          radii[valid_chest]), 3.0)
    radii[valid_chest] = smoothed[valid_chest]
    follow = np.clip((path_t[valid_chest]-.08)/.12, 0., 1.)
    follow *= np.clip((.94-path_t[valid_chest])/.12, 0., 1.)
    follow = follow*follow*(3.-2.*follow)
    origins = np.column_stack([np.zeros(len(line)), line[:, 1],
                               np.full(len(line), middle_z)])
    directions = normalise(line-origins)
    wanted = origins[valid_chest]+directions[valid_chest]*(radii[valid_chest]+.016*stature)[:, None]
    line[valid_chest] += (wanted-line[valid_chest])*follow[:, None]
    front_line = curve(path_t)
    front_mask = (path_t > .26) & (path_t < .73)
    measured_front = front_depth(rig, front_line[front_mask])
    ids = np.flatnonzero(front_mask)[np.isfinite(measured_front)]
    front_line[ids, 2] = measured_front[np.isfinite(measured_front)]+.016*stature
    front_share = np.clip((path_t[ids]-.26)/.08, 0., 1.)
    front_share *= np.clip((.73-path_t[ids])/.08, 0., 1.)
    front_share = front_share*front_share*(3.-2.*front_share)
    line[ids] += (front_line[ids]-line[ids])*front_share[:, None]
    line = gaussian_filter1d(line, 2.0, axis=0)
    # The local direction follows the fitted chest line, rather than the
    # uncorrected oval the source loop happened to have.
    path = CubicSpline(path_t, line)
    line = path(t)
    tangent = normalise(path(t, 1))
    radial = line-np.column_stack([np.zeros(len(line)),line[:,1],
                                   np.full(len(line), middle_z)])
    radial = normalise(radial)
    # Over the shoulder the broad face lies on its top, whose outward normal
    # is up. A horizontal trunk radius turns that panel onto its thin edge.
    shoulder_share = np.exp(-((t-.205)/.08)**4)
    radial = normalise(radial*(1.-shoulder_share[:, None])+
                       np.array([0., 1., 0.])*shoulder_share[:, None])
    front_share = np.clip((t-.25)/.09, 0., 1.)*np.clip((.74-t)/.09, 0., 1.)
    front_share = front_share*front_share*(3.-2.*front_share)
    radial = normalise(radial*(1.-front_share[:, None])+
                       np.array([0., 0., 1.])*front_share[:, None])
    side = normalise(np.cross(tangent, radial))
    radial = normalise(np.cross(side, tangent))
    side_offset, outside_offset, measured_roll = strap_section(
        t, radial_offset/scale, depth.copy(), blend)
    side_offset *= scale
    outside_offset *= scale
    strap = line+side*side_offset[:,None]+radial*outside_offset[:,None]
    fitted = fixed*(1.-blend[:,None])+strap*blend[:,None]
    tree = cKDTree(samples)
    _, nearest = tree.query(fitted)
    delta = fitted-samples[nearest]
    gap = np.einsum('ij,ij->i',delta,body_normals[nearest])
    push = np.maximum(0., .006*stature-gap)*blend
    fitted += body_normals[nearest]*push[:,None]
    candidates = ['pelvis','spine_01','spine_02','spine_03','clavicle_l','clavicle_r']
    skin_joints, skin_weights = rig.weights_for(fitted, candidates)
    body_weight = blend*np.clip((t-.08)/.16, 0., 1.)*np.clip((.95-t)/.15, 0., 1.)
    owner = rig.joint_names.index('spine_03')
    # Combine the body weights with one rigid case owner, retaining four
    # influences and welding identical source vertices to identical blends.
    combined = np.zeros((len(fitted),len(rig.joint_names)))
    rows = np.arange(len(fitted))
    for column in range(4):
        combined[rows,skin_joints[:,column]] += skin_weights[:,column]*body_weight
    combined[:,owner] += 1.-body_weight
    joints = np.argsort(combined,axis=1)[:,-4:]
    weights = np.take_along_axis(combined,joints,axis=1)
    weights /= weights.sum(axis=1,keepdims=True)
    _, inverse = np.unique(np.round(original,6),axis=0,return_inverse=True)
    for label in np.unique(inverse):
        ids = np.flatnonzero(inverse==label)
        if len(ids)>1:
            fitted[ids]=fitted[ids].mean(axis=0)
            combined[ids]=combined[ids].mean(axis=0)
    joints = np.argsort(combined,axis=1)[:,-4:]
    weights = np.take_along_axis(combined,joints,axis=1)
    weights /= weights.sum(axis=1,keepdims=True)
    surface.positions = fitted
    surface.normals = surface_normals(fitted,surface.indices.reshape(-1,3))
    return surface, texture, joints, weights, {
        'rigidVertices':int((blend==0).sum()),'strapVertices':int((blend>0).sum()),
        'scale':scale,'caseScale':case_scale,
        'caseBackZ':float(np.quantile(fitted[bag,2], .02)),
        'backOffset':float(back_offset),
        'caseTiltDegrees':float(case_tilt_degrees),
        'chestStrapRollDegrees':measured_roll,
        'bounds':[fitted.min(0).tolist(),fitted.max(0).tolist()],
        'rigidBone':'spine_03','bodySha256':digest(NATIVE/'races'/f'{rig.source_slug}.glb')}


def build(out, assets, races):
    records=[]
    for race in races:
        rig=ea.load_rig(NATIVE/'races'/f'{race}.glb')
        reference=next(a for a in json.loads(CATALOG.read_text())['assets']
                       if a['id']=='rl-quiver-basic')
        basic_fit=fit(reference,SOURCE/(reference['id']+'.glb'),rig)
        reference_back=basic_fit[-1]['caseBackZ']
        stature=float(rig.origin('Head')[1])/1.568490028858185
        for entry in assets:
            result=(basic_fit if entry['id']==reference['id'] else
                    fit(entry,SOURCE/(entry['id']+'.glb'),rig))
            surface,texture,joints,weights,report=result
            # Thin cases need the same outer back line as the accepted Basic
            # fit while a cape is worn. Author a second shape rather than
            # making them float behind a character who has taken the cape off.
            cape_offset=(0.0 if entry['id']==reference['id'] else max(
                0.0, report['caseBackZ']-reference_back+.012*stature))
            cape_tilt=(0.0 if entry['id']==reference['id'] else float(
                json.loads(CATALOG.read_text()).get('capeTiltDegreesByBody',{}).get(race,0.0)))
            cape_surface=(None if cape_offset==0.0 and cape_tilt==0.0 else
                fit(entry,SOURCE/(entry['id']+'.glb'),rig,
                    back_offset=cape_offset,case_tilt_degrees=cape_tilt)[0])
            if cape_surface is not None:
                # A cape changes the case and its rear attachments. The chest
                # strap keeps the same lay, with or without that outer layer.
                chest = surface.positions[:, 2] > .025*stature
                cape_surface.positions[chest] = surface.positions[chest]
                cape_surface.normals = surface_normals(
                    cape_surface.positions, cape_surface.indices.reshape(-1, 3))
            report['capeClearanceOffset']=cape_offset
            report['capeCaseTiltDegrees']=cape_tilt
            report['capeReference']='rl-quiver-basic'
            destination=out/'variants'/race/(entry['id']+'.glb')
            write_mesh(destination,surface,texture,rig,joints,weights,cape_surface)
            records.append(dict(report,id=entry['id'],race=race,path=str(destination),
                                sha256=digest(destination),triangles=len(surface.indices)//3))
        print(f'Fitted {len(assets)} quivers to {race}',flush=True)
    (out/'fits.json').write_bytes((json.dumps(records,indent=2)+'\n').encode('utf-8'))


def install(out, assets):
    import pack_canonical_equipment as pack
    from build_native_nymara_glbs import validate_glb
    registry_path=CLIENT/'data/actors/equipment.json'
    registry=json.loads(registry_path.read_bytes())
    catalog_path=CLIENT/'data/actors/native_asset_catalog.json'
    catalog=json.loads(catalog_path.read_bytes())
    registry['parts'][str(PART)]={'name':'quiver','attachment':'back','fallback':'body','bareWhenEmpty':True}
    registry.setdefault('fitProfiles',{})['quivers']={'canonicalHeadRestY':0.,'bodyGirth':{}}
    records=json.loads((out/'fits.json').read_text())
    expected={(race, entry['id']) for race in registry['bodyTemplates'] for entry in assets}
    if (not assets or len(records) != len(expected)
            or {(r['race'], r['id']) for r in records} != expected):
        raise ValueError('Install requires every selected quiver fitted to all sixteen bodies')
    stage=out/'packed'
    stage.mkdir(exist_ok=True)
    for entry in assets:
        variants={}
        for record in records:
            if record['id']!=entry['id']: continue
            race=record['race']
            target=pack.PREFIX/'variants'/race/(entry['id']+'.glb')
            textures=pack.pack_glb(Path(record['path']),target,stage)
            for relative in [*textures,target]:
                destination=ROOT/relative
                destination.parent.mkdir(parents=True,exist_ok=True)
                incoming=(stage/relative).read_bytes()
                if destination.exists() and relative!=target and destination.read_bytes()!=incoming:
                    raise ValueError(f'Shared texture differs: {relative}')
                destination.write_bytes(incoming)
            group=registry['fitGroups'][race][0]
            variants[group]={'scene':'res://'+str(target.relative_to('godot-client')).replace('\\','/'),
                             'authoredFor':race,'fitProfile':'quivers'}
            catalog.setdefault('validation',{}).setdefault('results',{})[target.as_posix()]=validate_glb(ROOT/target)
        base=variants['canonical_human_male']
        registry['models'][f'{PART}:{entry["visual"]}']={**base,'name':entry['name'],
            'attach':'skinned','kind':'quiver','skinRegion':'quiver','variants':variants}
    registry_path.write_bytes((json.dumps(registry,indent=2)+'\n').encode('utf-8'))
    catalog['validation']['files']=sum(1 for _ in NATIVE.rglob('*.glb'))
    catalog_path.write_bytes((json.dumps(catalog,indent=2)+'\n').encode('utf-8'))


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--prepare',type=Path)
    parser.add_argument('--out',type=Path,required=True)
    parser.add_argument('--races',nargs='+')
    parser.add_argument('--pieces',nargs='+')
    parser.add_argument('--install',action='store_true')
    args=parser.parse_args()
    assets=json.loads(CATALOG.read_text())['assets']
    if args.pieces: assets=[a for a in assets if a['id'] in args.pieces]
    if args.prepare: prepare(args.prepare,assets)
    args.out.mkdir(parents=True,exist_ok=True)
    races=args.races or sorted(json.loads((CLIENT/'data/actors/equipment.json').read_bytes())['bodyTemplates'])
    build(args.out,assets,races)
    if args.install: install(args.out,assets)


if __name__=='__main__':
    main()
