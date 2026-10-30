#!/usr/bin/env python3
"""Refit existing equipment from the second review; retain every source GLB.

This edits imported geometry, never generates replacement models. Candidates
stay in an ignored stage until --install. Unrelated intervening edits are
rejected. Headwear is measured against the bald head, not a hair envelope.
"""
from __future__ import annotations

import argparse
import copy
import io
import json
import shutil
import subprocess
from functools import lru_cache
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw
from scipy.ndimage import distance_transform_edt
from scipy.spatial import cKDTree

from refine_equipment_review import Edit, smooth, sha

ROOT = Path(__file__).resolve().parents[2]
CLIENT = ROOT / 'godot-client'
OPEN_RL = {111, 112, 114, 119}
SHORT_SLEEVES = {210, 211, 232, 234, 238, 242}
TORSOS = SHORT_SLEEVES | {186, 190, 209, 218, 219}
LEGS = {185, 219}


def ray_radii(points, faces, levels, axis):
    tri = points[faces]
    e1, e2 = tri[:, 1] - tri[:, 0], tri[:, 2] - tri[:, 0]
    samples = []
    for y in levels:
        for angle in np.linspace(0, 2 * np.pi, 16, endpoint=False):
            direction = np.array([np.sin(angle), 0., np.cos(angle)])
            h = np.cross(direction, e2)
            det = np.einsum('ij,ij->i', e1, h)
            valid = abs(det) > 1e-9
            inv = np.zeros_like(det)
            inv[valid] = 1 / det[valid]
            s = np.array([axis[0], y, axis[1]]) - tri[:, 0]
            u = inv * np.einsum('ij,ij->i', s, h)
            q = np.cross(s, e1)
            v = inv * (q @ direction)
            t = inv * np.einsum('ij,ij->i', e2, q)
            valid &= (u >= 0) & (v >= 0) & (u + v <= 1) & (t > .025) & (t < .4)
            if valid.any():
                samples.append(float(t[valid].min()))
    return samples


@lru_cache(maxsize=16)
def head_surface(body):
    actor = Edit(CLIENT / f'assets/actors/native/races/{body}.glb')
    worlds = __import__('equipment_authoring').global_matrices(actor.doc)
    head_index = actor.doc['skins'][0]['joints'][actor.joints().index('Head')]
    origin = worlds[head_index][:3, 3]
    meshes = actor.doc['meshes']
    eye_mesh = next(m for m in meshes if m.get('name') == 'eyes')
    p = eye_mesh['primitives'][0]
    eyes = actor.read(p['attributes']['POSITION'])[np.unique(actor.faces(p))]
    eye_y = float((eyes[:, 1].min() + eyes[:, 1].max()) * .5)
    # High Humans use the RL head. Size the shell to clear both render paths.
    if body.startswith('luminous_'):
        model = Edit(CLIENT / f'assets/actors/native/rl_heads/rl_head_{body.split("_")[-1]}.glb')
        p = model.doc['meshes'][0]['primitives'][0]
        eye_y = 1.645 if body.rsplit('_', 1)[-1] == 'male' else 1.637
        v = model.read(p['attributes']['POSITION'])
        f = model.faces(p)
        all_normals = model.read(p['attributes']['NORMAL'])
    else:
        points, faces, normals = [], [], []
        offset = 0
        for mesh in meshes:
            if mesh.get('name') not in ['body', 'scalp']:
                continue
            for p in mesh['primitives']:
                if actor.doc['materials'][p['material']].get('name') != 'Race head':
                    continue
                values = actor.read(p['attributes']['POSITION'])
                points.append(values); faces.append(actor.faces(p) + offset)
                normals.append(actor.read(p['attributes']['NORMAL'])); offset += len(values)
        v, f, all_normals = np.concatenate(points), np.concatenate(faces), np.concatenate(normals)
    forehead = v[(v[:, 1] > eye_y + .02) & (v[:, 1] < eye_y + .06)]
    axis = (forehead[:, [0, 2]].min(0) + forehead[:, [0, 2]].max(0)) * .5
    levels = [eye_y + .025, eye_y + .045, eye_y + .065]
    samples = ray_radii(v, f, levels, axis)
    assert len(samples) >= 20, (body, 'head sections')
    selected = (v[:, 1] > eye_y - .09) & (v[:, 1] < eye_y + .15)
    ids = np.flatnonzero(selected)
    _, unique = np.unique(np.round(v[ids], 5), axis=0, return_index=True)
    ids = ids[unique]
    normals = all_normals[ids]
    return dict(origin=origin, eye_y=eye_y, axis=axis, levels=levels,
                radius=float(np.median(samples)), points=v[ids], normals=normals,
                tree=cKDTree(v[ids]))


def headwear(edit, spec, kind, body, visual):
    if not body.startswith('luminous_'):
        # These retained heads already have ear-, crown- and horn-specific
        # native fits. A Human skull reduction breaks their cleared openings.
        # Preserve that geometry; the Antler palette correction still applies.
        if visual == 122:
            for mesh in edit.doc['meshes']:
                mesh.setdefault('extras', {})['matchAntlerPalette'] = True
            edit.changes.append({'retained_race_geometry': body, 'antler_palette': True})
            return True
        return False
    if visual in OPEN_RL and body.startswith('luminous_'):
        return False  # Existing RL band fits are calibrated to these sources.
    head = head_surface(body)
    offset = np.array(spec['socket']['offset']) + head['origin']
    primitive = edit.doc['meshes'][0]['primitives'][0]
    source = edit.read(primitive['attributes']['POSITION']) + offset
    samples = ray_radii(source, edit.faces(primitive), head['levels'], head['axis'])
    if len(samples) < 8:
        raise ValueError(f'Insufficient headwear section samples: {edit.path}')
    radius = float(np.median(samples))
    scale = float(np.clip((head['radius'] + .009) / radius, .64, 1.))
    drop = {'helm': .010, 'hood': .016, 'cap': .022, 'hat': .024,
            'coif': .010, 'turban': .014, 'wrap': .014, 'band': .006, 'veil': .008}[kind]
    center = np.array([head['axis'][0], head['eye_y'] + .035, head['axis'][1]])
    for mesh in edit.doc['meshes']:
        if visual == 122:
            mesh.setdefault('extras', {})['matchAntlerPalette'] = True
        for p in mesh['primitives']:
            v = edit.read(p['attributes']['POSITION']) + offset
            q = center + (v - center) * [scale, scale * .92, scale]
            q[:, 1] -= drop
            if visual == 116:
                skirt = 1 - smooth(head['eye_y'] - .07, head['eye_y'] - .015, v[:, 1])
                q[:, 1] -= .025 * skirt
            if kind in ['hood', 'coif', 'wrap']:
                lower = 1 - smooth(head['eye_y'] - .055, head['eye_y'], v[:, 1]) if kind == 'hood' else \
                    1 - smooth(head['eye_y'] - .10, head['eye_y'] - .025, v[:, 1])
                q[:, 1] -= (.115 if kind == 'hood' else .080) * lower
                # A cloth skirt enters the torso opening rather than resting
                # on its outside. Preserve the upper crown and ornaments.
                neck = np.array([0., -.038])
                radial = q[:, [0, 2]] - neck
                length = np.linalg.norm(radial, axis=1)
                target = .063 + .018 * smooth(1.49, 1.56, q[:, 1])
                fitted_radius = target + (length - target) * .12
                factor = fitted_radius / np.maximum(length, 1e-6) if kind == 'hood' else \
                    np.minimum(1., .062 / np.maximum(length, 1e-6))
                q[:, [0, 2]] = neck + radial * (1 - lower + lower * factor)[:, None]
            distance, nearest = head['tree'].query(q)
            normals = head['normals'][nearest]
            signed = np.einsum('ij,ij->i', q - head['points'][nearest], normals)
            correction = np.maximum(.005 - signed, 0.) * (distance < .055) * (q[:, 1] > head['eye_y'] - .075)
            q += normals * correction[:, None]
            faces = edit.faces(p)
            def areas(points):
                return np.linalg.norm(np.cross(points[faces[:, 1]] - points[faces[:, 0]],
                                               points[faces[:, 2]] - points[faces[:, 0]]), axis=1)
            original_area = areas(v)
            for blend in [.01, .025, .05]:
                if not ((original_area > 1e-8) & (areas(q) < 1e-10)).any():
                    break
                # Dense native horn/trim rims contain micrometre-wide faces.
                # Retain a little of their authored shape if projection would
                # flatten them; the repair is deterministic and submillimetric.
                q = q * (1 - blend) + v * blend
                edit.changes.append({'thin_face_shape_retention': blend})
            edit.positions(p, q - offset)
    edit.changes.append({'headwear_fit': body, 'kind': kind, 'section_samples': len(samples),
                         'before_radius_m': radius, 'head_radius_m': head['radius'],
                         'scale_xz': scale, 'scale_y': scale * .92, 'drop_m': drop})
    if visual == 116:
        edit.changes.append({'lower_neck_guard_m': .025})
    return True


@lru_cache(maxsize=2)
def skin_patch(sex):
    body = Edit(CLIENT / f'assets/actors/native/races/luminous_{sex}.glb')
    primitive = next(m for m in body.doc['meshes'] if m.get('name') == 'body')['primitives'][0]
    material = body.doc['materials'][primitive['material']]
    texture = body.doc['textures'][material['pbrMetallicRoughness']['baseColorTexture']['index']]
    view = body.doc['bufferViews'][body.doc['images'][texture['source']]['bufferView']]
    start = view.get('byteOffset', 0)
    image = Image.open(io.BytesIO(body.blob[start:start + view['byteLength']])).convert('RGB')
    pixels = np.asarray(image) / 255.
    r, g, b = pixels.transpose(2, 0, 1)
    skin = (r > .62) & (g > .40) & (b > .30) & (r > g * 1.05) & (g > b * 1.02) & (r - b > .10)
    vertices = body.read(primitive['attributes']['POSITION'])
    uvs = body.read(primitive['attributes']['TEXCOORD_0'])
    hand_mask = Image.new('1', image.size)
    draw = ImageDraw.Draw(hand_mask)
    for face in body.faces(primitive):
        x = abs(vertices[face, 0])
        if x.min() > .74 and x.max() < .90:
            draw.polygon([(float(u * image.width), float(v * image.height)) for u, v in uvs[face]], fill=1)
    hand_skin = skin & np.asarray(hand_mask)
    if hand_skin.sum() > 100:
        skin = hand_skin
    distance = distance_transform_edt(skin)
    y, x = np.unravel_index(distance.argmax(), distance.shape)
    radius = min(float(distance[y, x]) * .28, 12.)
    return np.array([x / image.width, y / image.height]), radius / np.array(image.size)


def forearms(edit, mesh):
    from equipment_authoring import global_matrices
    worlds = global_matrices(edit.doc)
    names = edit.joints(); joints = edit.doc['skins'][0]['joints']
    sex = 'female' if '/human_female/' in edit.path.as_posix() else 'male'
    uv_center, uv_radius = skin_patch(sex)
    for p in mesh['primitives']:
        # Separate the anatomical arm attributes from the cloth lining.
        for semantic in ['POSITION', 'NORMAL', 'TEXCOORD_0']:
            old = p['attributes'][semantic]
            p['attributes'][semantic] = len(edit.doc['accessors'])
            edit.doc['accessors'].append(copy.deepcopy(edit.doc['accessors'][old]))
        v = edit.read(p['attributes']['POSITION']); q = v.copy()
        uv = edit.read(p['attributes']['TEXCOORD_0'])
        faces = edit.faces(p)
        wrist_x = abs(worlds[joints[names.index('hand_l')]][0, 3])
        # The backing included duplicate mitten/hand geometry. End the exposed
        # arm underneath the actual hand instead of squeezing those fingers
        # into the wrist and creating folded, overlapping skin triangles.
        faces = faces[np.max(abs(v[faces, 0]), axis=1) < wrist_x + .009]
        edit.put(p['indices'], faces.reshape(-1))
        used = np.unique(faces)
        for side, sign in [('l', 1), ('r', -1)]:
            shoulder = worlds[joints[names.index('upperarm_' + side)]][:3, 3]
            elbow = worlds[joints[names.index('lowerarm_' + side)]][:3, 3]
            wrist = worlds[joints[names.index('hand_' + side)]][:3, 3]
            ids = used[sign * v[used, 0] > .25]
            x = sign * v[ids, 0]
            t = (x - sign * elbow[0]) / abs(wrist[0] - elbow[0])
            u = (x - sign * shoulder[0]) / abs(elbow[0] - shoulder[0])
            axis = elbow + (wrist - elbow) * t[:, None]
            upper = t < 0
            axis[upper] = shoulder + (elbow - shoulder) * u[upper, None]
            radius = np.interp(t, [0, .25, .65, 1.], [.035, .041, .033, .024])
            radius[upper] = np.interp(u[upper], [0, .55, 1], [.050, .048, .035])
            stations, centers, radii = [], [], []
            for station in np.linspace(x.min(), x.max(), 10):
                band = v[ids[abs(x - station) < .035], 1:3]
                if len(band) < 8:
                    continue
                low, high = np.percentile(band, [3, 97], axis=0)
                stations.append(station); centers.append((low + high) * .5)
                radii.append(np.maximum((high - low) * .5, .015))
            centers, radii = np.array(centers), np.array(radii)
            original_axis = np.c_[np.interp(x, stations, centers[:, 0]),
                                     np.interp(x, stations, centers[:, 1])]
            original_radius = np.c_[np.interp(x, stations, radii[:, 0]),
                                       np.interp(x, stations, radii[:, 1])]
            radial = (v[ids, 1:3] - original_axis) / original_radius
            q[ids, 1:3] = axis[:, 1:3] + radial * radius[:, None] * [.88, 1.]
            angle = np.arctan2(radial[:, 1], radial[:, 0])
            uv[ids] = uv_center + np.c_[np.cos(angle), np.sin(angle)] * uv_radius
        edit.positions(p, q)
        edit.put(p['attributes']['TEXCOORD_0'], uv)
    edit.changes.append({'anatomical_forearms': sex, 'native_skin_uv_center': uv_center.tolist()})


def torso(edit, visual):
    for mesh in edit.doc['meshes']:
        if mesh.get('name') == 'EquipmentForearmSkin':
            forearms(edit, mesh)
            continue
        for p in mesh['primitives']:
            v = edit.read(p['attributes']['POSITION'])
            q = v.copy()
            if visual == 186:
                blend = smooth(1.02, 1.22, v[:, 1]) * (1 - smooth(1.40, 1.49, v[:, 1]))
                blend *= 1 - smooth(.20, .31, abs(v[:, 0]))
                q[:, 0] *= 1 - .13 * blend
                q[:, 2] = -.02 + (v[:, 2] + .02) * (1 - .18 * blend)
            if visual in [190, 219]:
                # Pull the proud central breast ornament back onto its shell.
                front = smooth(.11, .20, v[:, 2])
                middle = 1 - smooth(.105, .20, abs(v[:, 0]))
                height = smooth(1.07, 1.17, v[:, 1]) * (1 - smooth(1.39, 1.46, v[:, 1]))
                q[:, 2] -= (.065 if visual == 190 else .040) * front * middle * height
            if visual in [209, 218]:
                collar = smooth(1.425, 1.495, v[:, 1]) * (1 - smooth(.12, .20, abs(v[:, 0])))
                if visual == 218:
                    q[:, 2] = -.038 + (v[:, 2] + .038) * (1 - .10 * collar)
                else:
                    # Blend the narrow collar root into the front placket.
                    root = smooth(1.425, 1.46, v[:, 1]) * (1 - smooth(1.48, 1.51, v[:, 1]))
                    root *= smooth(-.01, .025, v[:, 2]) * (1 - smooth(.045, .09, abs(v[:, 0])))
                    q[:, 1] -= .018 * root
                    q[:, 2] += .006 * root
                    edit.rebind(p, root * .5, 'spine_03')
            edit.positions(p, q)
            if visual == 209 and 'JOINTS_0' in p['attributes']:
                # UV/material splits at the collar root must keep identical
                # ownership or a head turn pulls the seam open.
                attrs = p['attributes']; js = edit.read(attrs['JOINTS_0']).astype(int)
                ws = edit.read(attrs['WEIGHTS_0']); groups = {}
                for i in np.unique(edit.faces(p)):
                    if q[i, 1] > 1.42 and abs(q[i, 0]) < .16:
                        groups.setdefault(tuple(np.round(q[i], 5)), []).append(i)
                for group in groups.values():
                    if len(group) < 2:
                        continue
                    dense = np.zeros(len(edit.joints()))
                    np.add.at(dense, js[group].reshape(-1), ws[group].reshape(-1))
                    indices = np.argsort(dense)[-4:][::-1]
                    js[group] = indices; ws[group] = dense[indices] / dense[indices].sum()
                edit.put(attrs['JOINTS_0'], js); edit.put(attrs['WEIGHTS_0'], ws)
    edit.changes.append({'second_review_torso': visual, 'native_exposed_arms': visual in SHORT_SLEEVES})


def legs(edit, visual):
    if visual == 185:
        for material in edit.doc['materials']:
            if material.get('name', '').endswith('Backing'):
                material['pbrMetallicRoughness']['baseColorFactor'] = [.64, .60, .50, 1.]
    for mesh in edit.doc['meshes']:
        for p in mesh['primitives']:
            v = edit.read(p['attributes']['POSITION']); q = v.copy()
            if visual == 219:
                waist = smooth(.94, 1.02, v[:, 1])
                q[:, 0] *= 1 - .07 * waist
                q[:, 2] *= 1 - .13 * waist
                q[:, 1] -= .018 * waist
            else:
                if mesh.get('name') != 'Acolyte Legguards':
                    lower = 1 - smooth(.38, .58, v[:, 1])
                    axis_x = np.sign(v[:, 0]) * .105
                    q[:, 0] = axis_x + (v[:, 0] - axis_x) * (1 - .30 * lower)
                    q[:, 2] *= 1 - .30 * lower
                    edit.positions(p, q)
                    continue  # Retain the continuous anatomical leg lining.
                faces = edit.faces(p)
                keep = np.min(v[faces, 1], axis=1) > .28
                edit.put(p['indices'], faces[keep].reshape(-1))
                # Only the trouser tube enters a boot; preserve hanging panels.
                for side in [-1, 1]:
                    axis = side * .105
                    radial = v[:, [0, 2]] - [axis, .005]
                    tube = 1 - smooth(.082, .125, np.linalg.norm(radial, axis=1))
                    lower = (1 - smooth(.40, .60, v[:, 1])) * (side * v[:, 0] > 0)
                    share = tube * lower
                    q[:, 0] -= radial[:, 0] * .22 * share
                    q[:, 2] -= radial[:, 1] * .22 * share
                # Trim the source's cloth foot-wrap at the shin, inside the
                # boot. Keep the original calf ownership and continuous lining.
                hem = 1 - smooth(.46, .57, v[:, 1])
                q[:, 0] = np.sign(v[:, 0]) * .105 + (q[:, 0] - np.sign(v[:, 0]) * .105) * (1 - .32 * hem)
                q[:, 2] *= 1 - .35 * hem
            edit.positions(p, q)
    edit.changes.append({'second_review_legs': visual})


def run(stage, install, only, bodies, source_ref=None):
    stage = stage.resolve()
    if '.local' not in stage.parts:
        raise ValueError('Use an ignored .local stage')
    stage.mkdir(parents=True, exist_ok=True)
    registry = json.loads((CLIENT / 'data/actors/equipment.json').read_text())['models']
    policy = json.loads((ROOT / 'eloria-assets/tools/headwear_race_policy.json').read_text())['pieces']
    jobs = {}
    for key, spec in registry.items():
        part, visual = map(int, key.split(':'))
        if not (part == 3 or (part == 5 and visual in TORSOS) or (part == 4 and visual in LEGS)):
            continue
        if only and key not in only:
            continue
        for entry in [spec, *spec.get('variants', {}).values()]:
            jobs[entry['scene']] = (key, entry)
    prior_path = stage / 'manifest.json'
    prior = {r['scene']: r for r in json.loads(prior_path.read_text())['items']} if prior_path.exists() else {}
    records = []
    for scene, (key, entry) in sorted(jobs.items()):
        rel = Path(scene[6:]); current = CLIENT / rel; original = stage / 'originals' / rel
        if key.startswith('3:') and bodies and rel.parent.name.replace('human_', 'luminous_') not in bodies:
            continue
        if not original.exists():
            original.parent.mkdir(parents=True, exist_ok=True)
            if source_ref:
                content = subprocess.run(['git', 'show', f'{source_ref}:godot-client/{rel.as_posix()}'],
                                         cwd=ROOT, capture_output=True, check=True).stdout
                original.write_bytes(content)
            else:
                shutil.copy2(current, original)
        edit = Edit(original); part, visual = map(int, key.split(':'))
        changed = True
        if part == 3:
            body = rel.parent.name.replace('human_', 'luminous_')
            changed = headwear(edit, entry, policy[key]['kind'], body, visual)
        elif part == 5:
            torso(edit, visual)
        else:
            legs(edit, visual)
        if not changed:
            if scene in prior and install:
                if sha(current) not in {sha(original), prior[scene]['after_sha256']}:
                    raise ValueError(f'Newer edits to retained fit: {scene}')
                shutil.copy2(original, current)
                prior.pop(scene)
            continue
        out = stage / 'revised' / rel; edit.finish(out)
        row = {'key': key, 'scene': scene, 'before_sha256': sha(original),
               'after_sha256': sha(out), 'changes': edit.changes, 'validation': edit.validation}
        if install:
            allowed = {row['before_sha256'], row['after_sha256'], prior.get(scene, {}).get('after_sha256')}
            if sha(current) not in allowed:
                raise ValueError(f'Newer edits to {scene}')
            shutil.copy2(out, current)
        records.append(row)
    # A scoped revision does not discard receipts for the other fitted files.
    prior.update({r['scene']: r for r in records})
    report = {'schema': 1, 'scope': 'Second equipment review and headwear fit', 'items': list(prior.values())}
    prior_path.write_bytes((json.dumps(report, indent=2) + '\n').encode())
    print(json.dumps({'processed': len(records), 'total': len(prior), 'installed': install}))


def validate(stage):
    """Compare the installed exports with their retained pre-review originals."""
    report = json.loads((stage / 'manifest.json').read_text(encoding='utf-8'))
    collapsed = 0
    max_weight_error = 0.
    for row in report['items']:
        rel = Path(row['scene'][6:])
        before, after = stage / 'originals' / rel, CLIENT / rel
        assert sha(before) == row['before_sha256'] and sha(after) == row['after_sha256'], rel
        a, b = Edit(before), Edit(after)
        assert a.doc['nodes'] == b.doc['nodes'], (rel, 'node/rest contract')
        assert a.doc.get('skins') == b.doc.get('skins'), (rel, 'skin contract')
        for skin in a.doc.get('skins', []):
            assert np.array_equal(a.read(skin['inverseBindMatrices']), b.read(skin['inverseBindMatrices'])), rel
        for field in ['materials', 'images', 'textures', 'samplers', 'animations']:
            if field == 'materials' and row['key'] == '4:185':
                expected = copy.deepcopy(a.doc[field])
                for material in expected:
                    if material.get('name', '').endswith('Backing'):
                        material['pbrMetallicRoughness']['baseColorFactor'] = [.64, .60, .50, 1.]
                assert expected == b.doc[field], (rel, 'lining palette')
                continue
            assert a.doc.get(field) == b.doc.get(field), (rel, field)
        for ma, mb in zip(a.doc['meshes'], b.doc['meshes'], strict=True):
            assert ma.get('name') == mb.get('name'), rel
            arm = ma.get('name') == 'EquipmentForearmSkin'
            trimmed_hem = row['key'] == '4:185' and ma.get('name') == 'Acolyte Legguards'
            for pa, pb in zip(ma['primitives'], mb['primitives'], strict=True):
                aa, ab = a.arrays(pa), b.arrays(pb)
                assert aa.keys() == ab.keys(), rel
                fa, fb = a.faces(pa), b.faces(pb)
                if arm or trimmed_hem:
                    source_faces = {tuple(face) for face in fa.tolist()}
                    assert all(tuple(face) in source_faces for face in fb.tolist()), (rel, 'arm trim')
                else:
                    assert np.array_equal(fa, fb), (rel, 'topology')
                assert pa.get('material') == pb.get('material'), rel
                for name in aa:
                    assert aa[name].shape == ab[name].shape and np.isfinite(ab[name]).all(), (rel, name)
                    if name not in ['POSITION', 'NORMAL', 'JOINTS_0', 'WEIGHTS_0'] and not (arm and name == 'TEXCOORD_0'):
                        assert np.array_equal(aa[name], ab[name]), (rel, name)
                p, q = aa['POSITION'], ab['POSITION']
                def areas(points):
                    return np.linalg.norm(np.cross(points[fb[:, 1]] - points[fb[:, 0]],
                                                   points[fb[:, 2]] - points[fb[:, 0]]), axis=1)
                collapsed += int(((areas(p) > 1e-8) & (areas(q) < 1e-10)).sum())
                if 'WEIGHTS_0' in ab:
                    total = ab['WEIGHTS_0'].sum(axis=1)
                    if 'WEIGHTS_1' in ab:
                        total += ab['WEIGHTS_1'].sum(axis=1)
                    max_weight_error = max(max_weight_error, float(abs(total - 1).max()))
                    assert max_weight_error < .0081, (rel, 'normalized weights')
    result = {'status': 'passed' if collapsed == 0 else 'failed', 'files': len(report['items']),
              'new_collapsed_faces': collapsed, 'max_weight_sum_error': max_weight_error,
              'preserved': ['nodes/rests', 'inverse binds', 'image payloads/references',
                            'non-arm UVs', 'headwear and torso-shell topology'],
              'scoped_exceptions': ['forearm UVs sample the native skin atlas',
                                    'duplicate hand faces trimmed from the forearm lining',
                                    'cloth foot-wrap trimmed from Acolyte leggings inside the boot shaft',
                                    'Acolyte lining color matched to pale cloth']}
    (stage / 'independent-validation.json').write_bytes((json.dumps(result, indent=2) + '\n').encode())
    print(json.dumps(result))
    assert collapsed == 0, 'New collapsed faces'


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--stage', type=Path, required=True)
    parser.add_argument('--install', action='store_true')
    parser.add_argument('--keys', default='')
    parser.add_argument('--bodies', default='')
    parser.add_argument('--validate', action='store_true')
    parser.add_argument('--source-ref')
    args = parser.parse_args()
    if args.validate:
        validate(args.stage.resolve())
    else:
        run(args.stage, args.install, args.keys.split(',') if args.keys else [],
            args.bodies.split(',') if args.bodies else [], args.source_ref)
