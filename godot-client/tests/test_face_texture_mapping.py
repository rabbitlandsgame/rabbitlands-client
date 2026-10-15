"""Sample the shipped masks at independently reviewed anatomical landmarks."""
import hashlib
import json
from pathlib import Path
import sys
import unittest
import numpy as np
from PIL import Image
import trimesh
from scipy.ndimage import gaussian_filter1d
from scipy.signal import find_peaks

ROOT = Path(__file__).resolve().parents[2]
CLIENT = ROOT/'godot-client'
sys.path.insert(0, str(ROOT/'eloria-assets/tools'))
from build_face_masks import g, source_image

# Painted iris centres in canonical rest coordinates, measured from source
# renders; independent of the polygons used by the mask baker. The Human
# (luminous_*) heads were regenerated on 2026-10-05: theirs are re-measured
# from an orthographic front ray-cast of the installed body's own base-colour
# atlas (iris = the low-saturation dark disc inside the eye opening), and agree
# with the split's calibration (Head joint y 1.5685 + eye_y .0727 / .0682).
LANDMARKS = {
    'glasswarden_female': [(-.037, 1.643), (.037, 1.643)],
    'glasswarden_male': [(-.035, 1.653), (.036, 1.653)],
    'greyhaven_female': [(-.035, 1.613), (.035, 1.613)],
    'greyhaven_male': [(-.032, 1.624), (.032, 1.624)],
    'luminous_female': [(-.036, 1.637), (.036, 1.637)],
    'luminous_male': [(-.032, 1.641), (.032, 1.641)],
    'mycelari_female': [(-.038, 1.628), (.038, 1.628)],
    'mycelari_male': [(-.036, 1.637), (.038, 1.637)],
    'orun_female': [(-.038, 1.631), (.038, 1.631)],
    'orun_male': [(-.036, 1.635), (.036, 1.635)],
    'ssarathi_female': [(-.048, 1.680), (.048, 1.680)],
    'ssarathi_male': [(-.054, 1.662), (.054, 1.662)],
    'stoneborn_female': [(-.034, 1.624), (.034, 1.624)],
    'stoneborn_male': [(-.031, 1.627), (.031, 1.627)],
    'votary_female': [(-.031, 1.607), (.031, 1.607)],
    'votary_male': [(-.025, 1.607), (.025, 1.607)],
}


def rescaled(d, x, y):
    """A front landmark measured on the v2 head, on a body whose head was
    scaled uniformly about its rim centre (race programme decision 9:
    asset.extras.headRescale, written by race_head_prepare.py scale and
    carried by rebase_race_body.py): (cx + f(x - cx), cy + f(y - cy))."""
    rescale = d['asset'].get('extras', {}).get('headRescale')
    if not rescale:
        return x, y
    cx, cy, f = rescale['centre'][0], rescale['centre'][1], rescale['factor']
    return cx+f*(x-cx), cy+f*(y-cy)


def mask_at(mesh, uv, mask, x, y):
    points, _, faces = mesh.ray.intersects_location([[x, y, 1]], [[0, 0, -1]], multiple_hits=False)
    if not len(points):
        raise AssertionError(('No head at landmark', x, y))
    bary = trimesh.triangles.points_to_barycentric(mesh.triangles[faces], points)[0]
    coord = bary @ uv[mesh.faces[faces[0]]]
    xy = np.floor((coord % 1)*np.array(mask.shape[:2][::-1])).astype(int)
    return mask[xy[1], xy[0]]/255.


def atlas_uv(d, b, part):
    uv = g.accessor(d, b, part['attributes']['TEXCOORD_0'])
    extra = part.get('extras', {})
    return uv * extra.get('sourceUVScale', [1, 1]) + extra.get('sourceUVOffset', [0, 0])


class FaceTextureMappingTest(unittest.TestCase):
    def test_humanoid_faces_have_two_brows_above_the_eyes(self):
        # Independently measured brow centres, rather than the baker's curves.
        # luminous_*: centroid of the painted brow in the same front ray-cast
        # of the regenerated Human heads' atlas as LANDMARKS above.
        centres = {
            'glasswarden_female': (.047, 1.667), 'glasswarden_male': (.040, 1.667),
            'greyhaven_female': (.041, 1.639), 'greyhaven_male': (.042, 1.642),
            'luminous_female': (.034, 1.658), 'luminous_male': (.033, 1.658),
            'mycelari_female': (.050, 1.655), 'mycelari_male': (.040, 1.650),
            'orun_female': (.047, 1.650), 'orun_male': (.043, 1.650),
            'votary_female': (.035, 1.622), 'votary_male': (.029, 1.613),
        }
        for slug, (x, y) in centres.items():
            with self.subTest(model=slug):
                d, b = g.read(CLIENT/f'assets/actors/native/races/{slug}.glb')
                vertices, uvs, faces, offset = [], [], [], 0
                for m in d['meshes']:
                    for p in m['primitives']:
                        if p.get('extras', {}).get('sourceRole') != 'race_head':
                            continue
                        a = p['attributes']
                        v = g.accessor(d, b, a['POSITION'])
                        vertices.append(v)
                        uvs.append(atlas_uv(d, b, p))
                        faces.append(g.accessor(d, b, p['indices']).astype(int).reshape(-1, 3)+offset)
                        offset += len(v)
                mesh = trimesh.Trimesh(np.concatenate(vertices), np.concatenate(faces), process=False)
                uv = np.concatenate(uvs)
                mask = np.asarray(Image.open(CLIENT/f'assets/actors/native/face_masks/{slug}.png'))
                for sign in [-1, 1]:
                    bx, by = rescaled(d, sign*x, y)
                    values = [mask_at(mesh, uv, mask, bx+dx, by+dy)[2]
                              for dx in np.linspace(-.012, .012, 15)
                              for dy in np.linspace(-.004, .004, 9)]
                    self.assertGreater(max(values), .1, ('missing eyebrow', sign))
                    self.assertGreater(np.count_nonzero(np.array(values) > .05), 1)
                self.assertLess(mask_at(mesh, uv, mask, *rescaled(d, 0, y))[2], .02, 'brows join across nose')

    def test_every_race_mask_matches_its_source_and_both_eyes(self):
        models = json.loads((CLIENT/'data/actors/models.json').read_text())['models']
        manifest = json.loads((CLIENT/'assets/actors/native/face_masks/manifest.json').read_text())
        self.assertEqual(set(LANDMARKS), set(manifest))
        for slug, landmarks in LANDMARKS.items():
            with self.subTest(model=slug):
                model = CLIENT/models[slug]['scene'].removeprefix('res://')
                spec = models[slug]['faceAppearance']
                path = CLIENT/spec['mask'].removeprefix('res://')
                self.assertEqual(manifest[slug]['modelSHA256'], hashlib.sha256(model.read_bytes()).hexdigest())
                self.assertEqual(manifest[slug]['maskSHA256'], hashlib.sha256(path.read_bytes()).hexdigest())
                mask = np.asarray(Image.open(path).convert('RGB'))
                d, b = g.read(model)
                body = next(m for m in d['meshes'] if m['name'] == 'body')
                head = body['primitives'][spec['sourceSurface']]
                self.assertEqual('race_head', head['extras']['sourceRole'])
                if 'groups' in spec:
                    for name, crop in spec['groups'].items():
                        part = next(m for m in d['meshes'] if m['name'] == name)['primitives'][0]
                        texture = source_image(d, b, part['material'])
                        np.testing.assert_array_equal(np.rint(np.array(crop['uvScale']) * mask.shape[:2][::-1]), texture.shape[:2][::-1])
                else:
                    self.assertEqual(mask.shape, source_image(d, b, head['material']).shape)
                vertices, uvs, faces = [], [], []
                offset = 0
                for m in d['meshes']:
                    for p in m['primitives']:
                        if p.get('extras', {}).get('sourceRole') != 'race_head':
                            continue
                        a = p['attributes']
                        v = g.accessor(d, b, a['POSITION'])
                        uv = atlas_uv(d, b, p)
                        self.assertTrue(np.isfinite(uv).all())
                        vertices.append(v); uvs.append(uv)
                        faces.append(g.accessor(d, b, p['indices']).astype(int).reshape(-1, 3)+offset)
                        offset += len(v)
                mesh = trimesh.Trimesh(np.concatenate(vertices), np.concatenate(faces), process=False)
                uv = np.concatenate(uvs)
                for x, y in (rescaled(d, *xy) for xy in landmarks):
                    # A small iris patch avoids a single painted white glint.
                    values = np.array([mask_at(mesh, uv, mask, x+dx, y+dy)
                                       for dx in [-.001, 0, .001] for dy in [-.001, 0, .001]])
                    self.assertGreater(values[:, 0].max(), .8, ('eye protection', x, y))
                    self.assertGreater(values[:, 1].max(), .15, ('iris colour', x, y))
                # Mid-forehead, nose bridge and cheeks must never receive eye
                # colour. These would catch the former Votary ear/Orun brow leak.
                for x, y in [(0, 1.68), (0, 1.63), (-.06, 1.595), (.06, 1.595)]:
                    self.assertLess(mask_at(mesh, uv, mask, *rescaled(d, x, y))[:2].max(), .02)

    def test_rebaked_necks_match_the_models_and_keep_the_head_boundary(self):
        models = json.loads((CLIENT/'data/actors/models.json').read_text())['models']
        manifest = json.loads((CLIENT/'assets/actors/native/neck_textures/manifest.json').read_text())
        joined = {slug for slug in LANDMARKS if 'neckTexture' in models[slug]['faceAppearance']}
        self.assertEqual(joined, set(manifest))
        for slug in joined:
            with self.subTest(model=slug):
                config = models[slug]
                d, b = g.read(CLIENT/config['scene'].removeprefix('res://'))
                spec = config['faceAppearance']
                body = next(m for m in d['meshes'] if m['name'] == 'body')
                part = body['primitives'][spec['neckSurface']]
                self.assertEqual('neck_join', part['extras']['sourceRole'])
                original = source_image(d, b, part['material'])
                path = CLIENT/spec['neckTexture'].removeprefix('res://')
                repaired = np.asarray(Image.open(path).convert('RGB'))
                self.assertEqual(original.shape, repaired.shape)
                np.testing.assert_array_equal(original[-1], repaired[-1])
                self.assertEqual(hashlib.sha256(path.read_bytes()).hexdigest(), manifest[slug]['textureSHA256'])
                self.assertEqual(hashlib.sha256((CLIENT/config['scene'].removeprefix('res://')).read_bytes()).hexdigest(), manifest[slug]['modelSHA256'])

    def test_necks_do_not_repeat_painted_lips(self):
        # The original cylindrical atlases repeated 3-7 dark lip bands along
        # the front of these necks. A single source neck may shade once, but
        # must not alternate between lips and skin repeatedly down the throat.
        for slug in ['greyhaven_female', 'votary_female', 'votary_male',
                     'orun_female', 'orun_male']:
            with self.subTest(model=slug):
                path = CLIENT/f'assets/actors/native/neck_textures/{slug}.png'
                rgb = np.asarray(Image.open(path).convert('RGB')).astype(float)/255.
                front = gaussian_filter1d(rgb[:480, 245:267].mean((1, 2)), 4)
                bands = find_peaks(-front, prominence=.025, distance=40)[0]
                self.assertLessEqual(len(bands), 1, 'repeated painted mouth/jaw bands')


if __name__ == '__main__':
    unittest.main()
