"""Measure authored skin albedo on mesh UVs for consistent runtime dyes.

Calibration is area weighted, excludes protected eye/brow pixels, and does not
modify source textures, geometry or animation. Each skin material retains its
own lighting detail while all characters use the same named target colors.

Race bodies rebased onto the Human body (sharedBodyShape version 3, see
rebase_race_body.py) join four skin surfaces along seams: shared_body,
shared_neck, neck_join and race_head. Their per-surface references come from
different texels, so equal texels either side of a seam would dye
differently. When any adjacent pair differs by more than 2% in linear
luminance, every skin-surface reference takes the face reference, and
skinPalette.bodySeams records the calibrated values and the reason. A
race_tail surface (Ssarathi) has its own texture and keeps its own reference.
"""
import argparse
import json
from pathlib import Path

import numpy as np
from PIL import Image
from shared_player_bodies import g, material_image, sample_image, digest

LUMA = np.array([.2126, .7152, .0722])
SEAM_PAIRS = (('shared_body', 'shared_neck'), ('shared_neck', 'neck_join'), ('neck_join', 'race_head'))
SEAM_TOLERANCE = .02


def weighted_median(values, weights):
    result = []
    for column in values.T:
        order = np.argsort(column)
        result.append(float(column[order[np.searchsorted(np.cumsum(weights[order]), weights.sum() / 2)]]))
    return result


def linear_luminance(rgb):
    c = np.asarray(rgb, float)
    return float(np.where(c <= .04045, c / 12.92, ((c + .055) / 1.055) ** 2.4) @ LUMA)


def unify_rebased_seams(document, refs, face_surface):
    """Rebased bodies: one body reference when an adjacent seam pair differs."""
    if document['asset'].get('extras', {}).get('sharedBodyShape', {}).get('version', 0) < 3:
        return None
    body = next(mesh for mesh in document['meshes'] if mesh['name'] == 'body')
    roles = [primitive.get('extras', {}).get('sourceRole') for primitive in body['primitives']]
    lum = [linear_luminance(value) for value in refs['body']]
    ratios = {f'{a}/{b}': lum[roles.index(a)] / lum[roles.index(b)] for a, b in SEAM_PAIRS}
    seams = {'roles': roles, 'calibrated': [list(value) for value in refs['body']],
             'linearLuminanceRatios': ratios, 'tolerance': SEAM_TOLERANCE,
             'unified': any(abs(ratio - 1) > SEAM_TOLERANCE for ratio in ratios.values())}
    if seams['unified']:
        skin = {role for pair in SEAM_PAIRS for role in pair}
        refs['body'] = [list(refs['body'][face_surface]) if role in skin else value
                        for role, value in zip(roles, refs['body'])]
        seams['reason'] = ('an adjacent skin-surface pair differed by more than 2% in linear luminance, so equal '
                           'texels either side of that seam would dye differently; every body reference takes the '
                           'face (race_head) reference')
    return seams


def calibrate(root, slugs=None):
    """The calibrated models.json document and its path; nothing is written."""
    client = root / 'godot-client'
    path = client / 'data/actors/models.json'
    models = json.loads(path.read_text())
    for slug, config in models['models'].items():
        if 'bodyTemplate' not in config or (slugs is not None and slug not in slugs):
            continue
        model = client / config['scene'][6:]
        document, binary = g.read(model)
        spec = config['faceAppearance']
        mask = np.asarray(Image.open(client / spec['mask'][6:]).convert('RGB'))
        refs = {}
        for mesh in document['meshes']:
            part = mesh['name']
            if part not in ('body', 'scalp', 'eyes', 'eyebrows'):
                continue
            refs[part] = []
            for surface, primitive in enumerate(mesh['primitives']):
                vertices = g.accessor(document, binary, primitive['attributes']['POSITION'])
                uv = g.accessor(document, binary, primitive['attributes']['TEXCOORD_0'])
                faces = g.accessor(document, binary, primitive['indices']).astype(int).reshape(-1, 3)
                area = np.linalg.norm(np.cross(vertices[faces[:, 1]] - vertices[faces[:, 0]], vertices[faces[:, 2]] - vertices[faces[:, 0]]), axis=1)
                centers = uv[faces].mean(1)
                _, pixels = material_image(document, binary, primitive['material'])
                colors = sample_image(pixels, centers)
                use = area > 1e-12
                is_face = part != 'body' or surface == spec['sourceSurface']
                if is_face:
                    crop = spec.get('groups', {}).get(part, {})
                    regions = sample_image(mask, centers * crop.get('uvScale', [1, 1]) + crop.get('uvOffset', [0, 0]))
                    use &= regions.max(1) < .094
                # Pure black atlas gutters and eye pupils are not skin albedo.
                use &= colors.max(1) > .10
                refs[part].append(weighted_median(colors[use], area[use]) if use.any() else [0.7, 0.6, 0.5])
        # The face partitions share one skin calibration: tiny eyelid strips
        # and forehead islands must not establish independent brightness.
        face = refs['body'][spec['sourceSurface']]
        for part in ('eyes', 'eyebrows', 'scalp'):
            if part in refs:
                refs[part] = [face for _ in refs[part]]
        seams = unify_rebased_seams(document, refs, spec['sourceSurface'])
        config['skinPalette'] = {'version': 1, 'sourceSHA256': digest(model), 'references': refs}
        if seams is not None:
            config['skinPalette']['bodySeams'] = seams
        print(slug, np.round(face, 3).tolist(), flush=True)
    return models, path


def run(root, slugs=None):
    models, path = calibrate(root, slugs)
    path.write_text(json.dumps(models, indent=2) + '\n')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, required=True)
    parser.add_argument('--slugs', nargs='+', help='Recalibrate only these models; others keep their palettes')
    args = parser.parse_args()
    run(args.root, set(args.slugs) if args.slugs else None)
