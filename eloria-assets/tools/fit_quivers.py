"""Fit imported Meshy quivers to the sixteen current player bodies.

The case and seated arrows are rigid spine equipment. The existing shoulder
strap is reshaped around the wearer and inherits the body's own skin blend.
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
from scipy.interpolate import CubicSpline
from scipy.spatial import cKDTree

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


def write_mesh(path, surface, texture, rig=None, joints=None, weights=None):
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
    glb.mesh('Quiver', [primitive], skin=0 if rig is not None else None)
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


def fit(entry, source, rig):
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
    fixed += center
    width = float(np.quantile(torso[:,0], .98)-np.quantile(torso[:,0], .02))
    front = float(np.quantile(torso[:,2], .985))+.035*stature
    middle_z = float(np.median(torso[:,2]))
    upper = center+target_u*(length*.44*scale)+target_v*(length*.14*scale)
    lower = center-target_u*(length*.44*scale)+target_v*(length*.14*scale)
    anchors = np.array([
        upper,
        [-width*.32, shoulder_y+.025*stature, middle_z],
        [-width*.26, shoulder_y-.08*stature, front],
        [width*.08, float(rig.origin('spine_02')[1])+.06*stature, front],
        [width*.48, pelvis_y+.10*stature, front*.75+middle_z*.25],
        [width*.55, pelvis_y+.07*stature, middle_z],
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
    line = curve(t)
    tangent = normalise(curve(t,1))
    radial = line-np.column_stack([np.zeros(len(line)),line[:,1],
                                   np.full(len(line), middle_z)])
    radial = normalise(radial)
    side = normalise(np.cross(tangent, radial))
    loop_depth = float(np.median(depth[blend > .8])) if (blend > .8).any() else 0.
    strap = line+side*radial_offset[:,None]+radial*((depth-loop_depth)*scale)[:,None]
    fitted = fixed*(1.-blend[:,None])+strap*blend[:,None]
    tree = cKDTree(samples)
    _, nearest = tree.query(fitted)
    delta = fitted-samples[nearest]
    gap = np.einsum('ij,ij->i',delta,body_normals[nearest])
    push = np.maximum(0., .018*stature-gap)*blend
    fitted += body_normals[nearest]*push[:,None]
    candidates = ['pelvis','spine_01','spine_02','spine_03','clavicle_l','clavicle_r']
    skin_joints, skin_weights = rig.weights_for(fitted, candidates)
    body_weight = blend*np.sin(np.pi*t)**.7
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
        'bounds':[fitted.min(0).tolist(),fitted.max(0).tolist()],
        'rigidBone':'spine_03','bodySha256':digest(NATIVE/'races'/f'{rig.source_slug}.glb')}


def build(out, assets, races):
    records=[]
    for race in races:
        rig=ea.load_rig(NATIVE/'races'/f'{race}.glb')
        for entry in assets:
            surface,texture,joints,weights,report=fit(entry,SOURCE/(entry['id']+'.glb'),rig)
            destination=out/'variants'/race/(entry['id']+'.glb')
            write_mesh(destination,surface,texture,rig,joints,weights)
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
