"""Author five distinct hairstyles and fit them to every canonical player head.

Uses existing neutral hair textures and caps; added swept locks are actual
geometry. Raw styles remain unskinned and fitted copies use the body's 77-joint
bind pose. Existing style IDs and assets are preserved.

RETIRED (2026-10, race programme P7): `run` refuses. It refits every player
body's hair with the retired protrusion proxy and rewrites models.json and the
catalogue, which would overwrite the P5 race fits and the Human fits. The raw
styles it authored (native/hair/<style>_<sex>.glb, recorded as
"expand_hairstyles.py:<style>" in the catalogue) stay the inputs of
fit_human_hair.py (Human) and fit_character_appearance.py --race (races).
"""
import argparse
import copy
import json
from pathlib import Path

import numpy as np
from scipy.interpolate import CubicSpline
import trimesh
from shared_player_bodies import g, append_array
from fit_character_appearance import fit_hair, sha
from race_hair_skull import hair_skull, allows_protrusions

STYLES = {5: 'bob', 6: 'ponytail', 7: 'braid', 8: 'topknot', 9: 'mohawk'}


def swept_lock(points, radii, sides=10, steps=18, flatten=1.):
    points = np.asarray(points)
    t = np.linspace(0, 1, steps)
    curve = CubicSpline(np.linspace(0, 1, len(points)), points, axis=0)
    centers = curve(t)
    tangents = curve(t, 1)
    tangents /= np.linalg.norm(tangents, axis=1)[:, None]
    # Locks predominantly travel down/back; x is a stable cross section axis.
    reference = np.tile([1., 0, 0], (len(tangents), 1))
    reference[abs(tangents[:, 0]) > .9] = [0, 1, 0]
    cross = np.cross(tangents, reference)
    cross /= np.linalg.norm(cross, axis=1)[:, None]
    across = np.cross(cross, tangents)
    radius = np.interp(t, np.linspace(0, 1, len(radii)), radii)
    angle = np.linspace(0, 2*np.pi, sides+1)
    vertices = (centers[:, None, :] + radius[:, None, None] *
                (np.cos(angle)[None, :, None] * across[:, None, :] +
                 flatten * np.sin(angle)[None, :, None] * cross[:, None, :])).reshape(-1, 3)
    uv = np.stack(np.meshgrid(np.linspace(0, 1, sides+1), t), -1).reshape(-1, 2)
    faces = []
    for row in range(steps-1):
        for side in range(sides):
            a = row*(sides+1)+side; b = a+sides+1
            faces.extend([[a,b,a+1],[a+1,b,b+1]])
    for row, reverse in ((0, True), (steps-1, False)):
        for side in range(1, sides-1):
            face = [row*(sides+1), row*(sides+1)+side, row*(sides+1)+side+1]
            faces.append(face[::-1] if reverse else face)
    mesh = trimesh.Trimesh(vertices, faces, process=False)
    trimesh.repair.fix_normals(mesh, multibody=True)
    return vertices, np.asarray(mesh.faces), np.asarray(mesh.vertex_normals), uv


def add_lock(document, binary, points, radii, **kwargs):
    vertices, faces, normals, uv = swept_lock(points, radii, **kwargs)
    primitive = {'material': 0, 'attributes': {
        'POSITION': append_array(document, binary, vertices, 'VEC3'),
        'NORMAL': append_array(document, binary, normals, 'VEC3'),
        'TEXCOORD_0': append_array(document, binary, uv, 'VEC2')},
        'indices': append_array(document, binary, faces.ravel(), 'SCALAR', 5125)}
    document['meshes'][0]['primitives'].append(primitive)


def author(root):
    folder = root / 'godot-client/assets/actors/native/hair'
    for sex in ('female', 'male'):
        for style in STYLES.values():
            document, source = g.read(folder / f'{"long" if style == "bob" else "buzzed"}_{sex}.glb')
            binary = bytearray(source)
            primitive = document['meshes'][0]['primitives'][0]
            vertices = g.accessor(document, source, primitive['attributes']['POSITION'])
            cap = vertices[(abs(vertices[:, 0]) < .04) & (abs(vertices[:, 2]) < .055)]
            document.setdefault('asset', {}).setdefault('extras', {})['hairCapTopM'] = float(cap[:, 1].max())
            document['asset']['extras']['hairstyle'] = style
            document['meshes'][0]['name'] = f'{style}_{sex}'
            if style == 'bob':
                # Preserve the authored swept fringe and shorten the hanging
                # side/back locks to a rounded, jaw-length bob.
                for primitive in document['meshes'][0]['primitives']:
                    v = g.accessor(document, source, primitive['attributes']['POSITION'])
                    lower = v[:, 1] < .075
                    v[lower, 1] = .075 + (v[lower, 1]-.075)*.40
                    v[lower, 0] *= 1.05
                    primitive['attributes']['POSITION'] = append_array(document, binary, v, 'VEC3')
            elif style == 'ponytail':
                # Five overlapping tapered locks form one tied, curved tail.
                for i in range(5):
                    x = (i-2)*.012
                    add_lock(document, binary, [[x*.3,.16,-.077],[x,.13,-.145],
                        [x*1.25,.015,-.182],[x*.7,-.14+abs(i-2)*.012,-.157]],
                        [.018,.025,.020,.001], steps=22, flatten=.7)
            elif style == 'braid':
                add_lock(document, binary, [[0,.13,-.09],[0,.085,-.135],[0,.035,-.145]], [.03,.028,.023])
                # Two crossing strands weave around a narrow core; their phase
                # offset alternates the visible over/under lobes down the back.
                for strand in range(2):
                    points = []
                    for t in np.linspace(0,1,31):
                        phase = t*8*np.pi+strand*np.pi
                        radius = .018*(1-.4*t)
                        points.append([radius*np.sin(phase), .06-.29*t, -.146+radius*.6*np.cos(phase)])
                    add_lock(document,binary,points,[.015,.014,.011,.003],steps=85,sides=8)
                add_lock(document,binary,[[0,-.225,-.146],[0,-.265,-.148]],[.016,.001],steps=5)
            elif style == 'topknot':
                # Coiled layers taper into a rounded knot behind the crown.
                for i, radius in enumerate([.027, .033, .023]):
                    points = [[radius*np.cos(t), .203+i*.013+.004*np.sin(2*t),
                               -.065+radius*.8*np.sin(t)] for t in np.linspace(0,2*np.pi,25)]
                    add_lock(document,binary,points,[.018,.018,.018],steps=40,flatten=.85)
            elif style == 'mohawk':
                # A continuous narrow swept ridge, with tapered overlapping
                # crests, leaves the close-cropped sides visible.
                for i,z in enumerate(np.linspace(.065,-.082,8)):
                    y = .19-.25*abs(z)
                    lift = .065*(1-.35*abs(i-3.5)/3.5)
                    add_lock(document,binary,[[0,y,z],[0,y+lift*.75,z-.009],
                        [0,y+lift,z-.028]], [.022,.018,.001],steps=8,flatten=.9)
            document,binary = g.compact(document,bytes(binary))
            g.write(folder/f'{style}_{sex}.glb',document,binary)


RETIRED = ('expand_hairstyles.py is retired (2026-10, race programme P7): its refit would overwrite the '
           'installed hair fits. Fit Human hair with fit_human_hair.py and race hair with '
           'fit_character_appearance.py --race <slug>.')


def run(root, slugs):
    raise SystemExit(RETIRED)
    author(root)
    client = root/'godot-client'
    model_path = client/'data/actors/models.json'
    catalog_path = client/'data/actors/native_asset_catalog.json'
    models = json.loads(model_path.read_text())
    catalog = json.loads(catalog_path.read_text())
    for sex in ('female', 'male'):
        for style in STYLES.values():
            path = client/f'assets/actors/native/hair/{style}_{sex}.glb'
            raw, data = g.read(path)
            vertices = np.concatenate([g.accessor(raw,data,p['attributes']['POSITION']) for m in raw['meshes'] for p in m['primitives']])
            catalog['hair'][f'{style}_{sex}'] = {'style':style, 'gender':sex,
                'source':f'expand_hairstyles.py:{style}', 'vertices':len(vertices),
                'triangles':sum(raw['accessors'][p['indices']]['count']//3 for m in raw['meshes'] for p in m['primitives']),
                'bounds':{'min':vertices.min(0).tolist(),'max':vertices.max(0).tolist()},
                'path':path.relative_to(root).as_posix(), 'sha256':sha(path)}
    for slug, config in models['models'].items():
        if 'bodyTemplate' not in config or (slugs and slug not in slugs):
            continue
        sex = slug.rsplit('_',1)[1]
        document,binary = g.read(client/config['scene'][6:])
        head = hair_skull(document,binary,slug)
        horizontal = .95 if allows_protrusions(slug) else 1.
        for index, style in STYLES.items():
            source = client/f'assets/actors/native/hair/{style}_{sex}.glb'
            target = client/f'assets/actors/native/hair/fitted/{slug}_{style}_{sex}.glb'
            report = fit_hair(source,target,head,{'scale':[horizontal,1,horizontal], 'offset':[0,0,-.015]},document,binary)
            while len(config['hairStyles']) <= index:
                config['hairStyles'].append('')
            config['hairStyles'][index] = 'res://'+target.relative_to(client).as_posix()
            fitted,_ = g.read(target)
            catalog['fittedHair'][f'{slug}:{index}'] = {
                'path':target.relative_to(root).as_posix(), 'sha256':sha(target), 'joints':77,
                'triangles':sum(fitted['accessors'][p['indices']]['count']//3 for m in fitted['meshes'] for p in m['primitives'])}
            print(slug,style,round(report['maxRadialCorrectionM'],4),flush=True)
        model_path.write_text(json.dumps(models,indent=2)+'\n')
        catalog_path.write_text(json.dumps(catalog,indent=2)+'\n')
    # Refresh structural inventory after adding raw and fitted assets. This
    # also accounts for earlier fitted hair omitted from the old manifest.
    from build_native_nymara_glbs import validate_glb
    results = catalog.setdefault('validation', {}).setdefault('results', {})
    for path in (client/'assets/actors/native').rglob('*.glb'):
        key = path.relative_to(root).as_posix()
        if key not in results or path.parent.name == 'fitted' or path.parent.name == 'hair':
            results[key] = validate_glb(path)
    catalog['validation']['files'] = len(results)
    catalog_path.write_text(json.dumps(catalog,indent=2)+'\n')


if __name__ == '__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root',type=Path,required=True)
    parser.add_argument('--slugs',nargs='*')
    args=parser.parse_args()
    run(args.root.resolve(),args.slugs)
