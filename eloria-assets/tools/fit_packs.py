"""Fit the two imported Meshy packs to current bodies; never generate geometry.

The portable source meshes, UVs and triangle order stay unchanged. Bag vertices
are rigid on spine_03; existing shoulder loops inherit the torso's skin blend.
All intermediate files go to a fresh ignored --out stage.
"""
from __future__ import annotations
import argparse
import json
from pathlib import Path

import numpy as np
from scipy.spatial import cKDTree
from scipy.interpolate import PchipInterpolator

import conform_equipment as ce
import equipment_authoring as ea
from fit_quivers import digest, surface_normals, front_depth, body_samples, write_mesh

ROOT = Path(__file__).resolve().parents[2]
CLIENT = ROOT / 'godot-client'
NATIVE = CLIENT / 'assets/actors/native'
SOURCE = ROOT / 'eloria-assets/source/packs'


def shoulder_roof(rig, points):
    """Top-down triangle intersections on the actual upper torso and deltoids.

    Nearest-vertex normals cannot reliably detect a band crossing the roof of
    a shoulder. Exclude head/neck geometry so a strap never projects to a jaw.
    """
    names = ['spine_02', 'spine_03', 'clavicle_l', 'clavicle_r',
             'upperarm_l', 'upperarm_r']
    owners = rig.joints[np.arange(len(rig.joints)), rig.weights.argmax(1)]
    selected = np.isin(owners, [rig.joint_names.index(n) for n in names])
    faces = rig.faces[selected[rig.faces].all(1)]
    triangles = rig.positions[faces]
    shoulder = float(rig.origin('upperarm_l')[1])
    triangles = triangles[(triangles[:, :, 1].max(1) > shoulder-.11*rig.fit_scale)
                          & (triangles[:, :, 1].max(1) < shoulder+.08*rig.fit_scale)]
    a, b, c = triangles[:, 0], triangles[:, 1], triangles[:, 2]
    determinant = (b[:, 2]-c[:, 2])*(a[:, 0]-c[:, 0])+(c[:, 0]-b[:, 0])*(a[:, 2]-c[:, 2])
    valid = abs(determinant) > 1e-12
    a, b, c, determinant = a[valid], b[valid], c[valid], determinant[valid]
    roof = []
    for start in range(0, len(points), 128):
        p = points[start:start+128, None, :]
        u = ((b[:, 2]-c[:, 2])*(p[:, :, 0]-c[:, 0])+
             (c[:, 0]-b[:, 0])*(p[:, :, 2]-c[:, 2]))/determinant
        v = ((c[:, 2]-a[:, 2])*(p[:, :, 0]-c[:, 0])+
             (a[:, 0]-c[:, 0])*(p[:, :, 2]-c[:, 2]))/determinant
        inside = (u >= -1e-6) & (v >= -1e-6) & (u+v <= 1.000001)
        y = u*a[:, 1]+v*b[:, 1]+(1-u-v)*c[:, 1]
        roof.extend(np.where(inside, y, -np.inf).max(1))
    return np.asarray(roof)


def fit_shoulder_loops(rig, source, fitted, blend):
    """Bend whole imported strap sections over the shoulder, retaining thickness.

    Moving isolated vertices to the roof folds the broad band. Its measured
    source angle supplies one continuous centre line for each shoulder loop.
    """
    original = fitted.copy()
    stature = rig.fit_scale
    shoulder = float(rig.origin('upperarm_l')[1])
    pelvis = float(rig.origin('pelvis')[1])
    theta = np.arctan2((source[:, 1]-.05)/.4, (.05-source[:, 2])/.5)
    radius = np.hypot((source[:, 1]-.05)/.4, (.05-source[:, 2])/.5)
    for side in [-1, 1]:
        band = (source[:, 0]*side > 0.) & (blend > 0.)
        measured = band & (blend > .8)
        sections = []
        for angle in np.arange(-1.7, 1.76, .08):
            mask = measured & (abs(theta-angle) < .06)
            if mask.sum() >= 3:
                sections.append([angle, np.median(radius[mask]), np.median(source[mask, 0])])
        sections = np.asarray(sections)
        if len(sections) < 5: continue
        # Repose the existing ring to a continuous shoulder/chest route. This
        # adds or removes no vertices and preserves indices, UVs and paint.
        angles = np.array([-1.68,-1.2,-.65,0.,.5,.9,1.2,1.68])
        back = float(np.median(original[band & (source[:, 2] > -.02), 2]))
        center_x = float(np.median(source[measured,0]))
        x = -center_x*.54*stature
        ys = np.array([pelvis+.11*stature,pelvis+.10*stature,pelvis+.23*stature,
                       pelvis+.39*stature,shoulder-.045*stature,
                       shoulder+.020*stature,shoulder+.020*stature,shoulder-.065*stature])
        zs = np.array([back,.055*stature,.12*stature,.14*stature,.13*stature,
                       .055*stature,-.075*stature,back])
        probes = np.column_stack([np.full(len(angles),x),ys,zs])
        chest = front_depth(rig,probes)
        for index in [1,2,3,4]:
            if np.isfinite(chest[index]):zs[index]=chest[index]+.018*stature
        roofs = shoulder_roof(rig,probes)
        for index in [4,5,6]:
            if np.isfinite(roofs[index]):ys[index]=max(ys[index],roofs[index]+.012*stature)
        y_curve=PchipInterpolator(angles,ys)
        z_curve=PchipInterpolator(angles,zs)
        ids=np.flatnonzero(band)
        t=np.clip(theta[ids],angles[0],angles[-1])
        residual=(radius[ids]-np.interp(t,sections[:,0],sections[:,1]))*.24*stature
        width=-(source[ids,0]-center_x)*.54*stature
        dy,dz=y_curve.derivative()(t),z_curve.derivative()(t)
        norm=np.maximum(np.hypot(dy,dz),1e-9)
        target=np.column_stack([x+width,y_curve(t)-residual*dz/norm,
                                z_curve(t)+residual*dy/norm])
        amount=np.clip((-.005-source[ids,2])/.08,0.,1.)
        amount=np.maximum(amount,np.clip((source[ids,1]-.29)/.06,0.,1.)
                          *np.clip((.15-source[ids,2])/.08,0.,1.))
        upper=np.clip((theta[ids]-.48)/.25,0.,1.)
        amount *= upper*upper*(3.-2.*upper)
        fitted[ids]=original[ids]*(1.-amount[:,None])+target*amount[:,None]
    return fitted[:, 1]-original[:, 1]


def fit(entry, rig):
    surface, texture = ce.read_source(SOURCE / (entry['id'] + '.glb'))
    p = surface.positions.copy()
    stature = rig.fit_scale
    shoulder = float(rig.origin('upperarm_l')[1])
    pelvis = float(rig.origin('pelvis')[1])
    scale = float(entry['scale']) * stature
    trunk, normals = body_samples(rig)
    region = trunk[(trunk[:, 1] > pelvis) & (trunk[:, 1] < shoulder)
                   & (abs(trunk[:, 0]) < .18 * stature)]
    back = float(np.quantile(region[:, 2], .02)) - .035 * stature
    center_y = shoulder + entry['topAboveShoulder'] * stature - entry['sourceTop'] * scale
    fixed = p * [-scale, scale, -scale] + [0., center_y, back]
    # Measured source-space regions contain only the original shoulder loops.
    # Blend at their attached roots; no disconnected strap or synthetic band.
    blend = np.clip((entry['strapRearZ'] - p[:, 2]) / .065, 0., 1.)
    if entry['id'] == 'rl-small-pack':
        blend = np.maximum(blend, np.clip((p[:, 1] - .28) / .07, 0., 1.)
                           * np.clip((.13 - p[:, 2]) / .07, 0., 1.))
    else:
        blend *= np.clip((.32 - p[:, 1]) / .045, 0., 1.)
    strap = fixed.copy()
    strap[:, 1] = np.interp(p[:, 1], entry['strapY'],
                            [pelvis + .09 * stature, shoulder + .025 * stature])
    strap[:, 2] = back - p[:, 2] * entry['strapDepthScale'] * stature
    fitted = fixed * (1. - blend[:, None]) + strap * blend[:, None]
    # Match the actual front surface while retaining the imported band relief.
    chest = (fitted[:, 2] > .025 * stature) & (blend > 0.)
    if chest.any():
        front = front_depth(rig, fitted[chest])
        fitted[chest, 2] += np.where(np.isfinite(front),
            np.maximum(0., front + .012 * stature - fitted[chest, 2]), 0.)
    _, nearest = cKDTree(trunk).query(fitted)
    gap = np.einsum('ij,ij->i', fitted - trunk[nearest], normals[nearest])
    fitted += normals[nearest] * (np.maximum(0., .009 * stature - gap) * blend)[:, None]
    candidates = ['pelvis', 'spine_01', 'spine_02', 'spine_03', 'clavicle_l', 'clavicle_r']
    joints, weights = rig.weights_for(fitted, candidates)
    combined = np.zeros((len(p), len(rig.joint_names)))
    rows = np.arange(len(p))
    for column in range(joints.shape[1]):
        combined[rows, joints[:, column]] += weights[:, column] * blend
    combined[:, rig.joint_names.index('spine_03')] += 1. - blend
    if entry['id'] == 'rl-small-pack':
        theta = np.arctan2((p[:,1]-.05)/.4,(.05-p[:,2])/.5)
        shoulder_owner = np.clip((theta-.48)/.25,0.,1.)
        shoulder_owner = shoulder_owner*shoulder_owner*(3.-2.*shoulder_owner)*blend
        combined *= (1.-shoulder_owner[:,None])
        combined[:,rig.joint_names.index('spine_03')] += shoulder_owner
    joints = np.argsort(combined, axis=1)[:, -4:]
    weights = np.take_along_axis(combined, joints, axis=1)
    weights /= weights.sum(axis=1, keepdims=True)
    shoulder_lifts = np.zeros(len(fitted))
    if entry['id'] == 'rl-small-pack':
        shoulder_lifts = fit_shoulder_loops(rig, p, fitted, blend)
    surface.positions = fitted
    surface.normals = surface_normals(fitted, surface.indices.reshape(-1, 3))
    if not np.isfinite(fitted).all() or not np.allclose(weights.sum(1), 1.):
        raise ValueError('Invalid fitted geometry or skin')
    return surface, texture, joints, weights, {
        'bounds': [fitted.min(0).tolist(), fitted.max(0).tolist()],
        'rigidVertices': int((blend == 0).sum()), 'strapVertices': int((blend > 0).sum()),
        'triangles': len(surface.indices)//3, 'backPlane': back,
        'bodySha256': digest(NATIVE/'races'/f'{rig.source_slug}.glb'),
        'sourceSha256': digest(SOURCE/(entry['id']+'.glb')),
        'uvAndIndicesPreserved': True, 'rigidBone': 'spine_03',
        'shoulderLiftedVertices': int((shoulder_lifts > 0.).sum()),
        'shoulderMaximumLiftMetres': float(shoulder_lifts.max())}


def install(out, assets, records, registry):
    import pack_canonical_equipment as pack
    from build_native_nymara_glbs import validate_glb
    stage = out / 'packed'
    stage.mkdir()
    registry.setdefault('fitProfiles', {})['packs'] = {'canonicalHeadRestY': 0., 'bodyGirth': {}}
    catalog_path = CLIENT/'data/actors/native_asset_catalog.json'
    catalog = json.loads(catalog_path.read_bytes())
    for entry in assets:
        variants = {}
        for record in records:
            if record['id'] != entry['id']: continue
            race = record['race']
            target = pack.PREFIX/'variants'/race/(entry['id']+'.glb')
            textures = pack.pack_glb(Path(record['path']), target, stage)
            for relative in [*textures, target]:
                dest = ROOT/relative
                dest.parent.mkdir(parents=True, exist_ok=True)
                incoming = (stage/relative).read_bytes()
                if dest.exists() and relative != target and dest.read_bytes() != incoming:
                    raise ValueError(f'Shared texture differs: {relative}')
                dest.write_bytes(incoming)
            group = registry['fitGroups'][race][0]
            variants[group] = {'scene': 'res://'+target.relative_to('godot-client').as_posix(),
                               'authoredFor': race, 'fitProfile': 'packs'}
            catalog['validation']['results'][target.as_posix()] = validate_glb(ROOT/target)
        if len(variants) != len(registry['bodyTemplates']):
            raise ValueError('All body fits required')
        registry['models'][f'2:{entry["visual"]}'] = {
            **variants['canonical_human_male'], 'name': entry['name'],
            'attach': 'skinned', 'kind': 'pack', 'skinRegion': 'pack', 'variants': variants}
    (CLIENT/'data/actors/equipment.json').write_bytes((json.dumps(registry, indent=2, ensure_ascii=False)+'\n').encode('utf-8'))
    catalog['validation']['files'] = sum(1 for _ in NATIVE.rglob('*.glb'))
    catalog_path.write_bytes((json.dumps(catalog, indent=2, ensure_ascii=False)+'\n').encode('utf-8'))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out', type=Path, required=True)
    parser.add_argument('--races', nargs='+')
    parser.add_argument('--pieces', nargs='+', choices=['rl-small-pack', 'rl-large-pack'])
    parser.add_argument('--install', action='store_true')
    args = parser.parse_args()
    args.out.mkdir(parents=True, exist_ok=False)
    assets = json.loads((SOURCE/'catalog.json').read_bytes())['assets']
    if args.pieces:
        assets = [a for a in assets if a['id'] in args.pieces]
    registry = json.loads((CLIENT/'data/actors/equipment.json').read_bytes())
    races = args.races or sorted(registry['bodyTemplates'])
    records = []
    for race in races:
        rig = ea.load_rig(NATIVE/'races'/f'{race}.glb')
        for entry in assets:
            surface, texture, joints, weights, report = fit(entry, rig)
            dest = args.out/'variants'/race/(entry['id']+'.glb')
            write_mesh(dest, surface, texture, rig, joints, weights, name=entry['name'])
            records.append(dict(report, race=race, id=entry['id'], path=str(dest.resolve()), sha256=digest(dest)))
        print('Fitted packs to '+race, flush=True)
    (args.out/'fits.json').write_text(json.dumps(records, indent=2)+'\n')
    if args.install:
        if set(races) != set(registry['bodyTemplates']): raise ValueError('All bodies required')
        install(args.out, assets, records, registry)


if __name__ == '__main__':
    main()
