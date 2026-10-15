"""Race headwear at rest (P5): the class-kit headwear on the fourteen race bodies.

The race variants of every headwear piece are the Human fit carried onto the
race head and cleared by eloria-assets/tools/race_headwear_clearance.py
(refit_race_headwear.py).  This pins what that refit promises, on the
installed files, with the refit's own measurements:

* the registry: every piece has a variant per race body, authored for it,
  and ``raceFeatures`` / ``raceShoulders`` match headwear_race_policy.json;
* the seat: the socket sits k x the Human's below the eye line (k, the head
  size the refit measured), within 6 mm;
* the four class-kit pieces (Leather Helm 3:134, Buckled Hood 3:159, Acolyte
  Hood 3:115, Antler Hood 3:122) on every race: no ear comes through
  (<= 2 cm2, <= 5 mm), no head skin comes through (<= 2 cm2), a show hood
  covers a crown or crystals (<= 2 cm2) and Votary horns leave through its
  openings (no horn edge crosses the hood);
* the four open bands (3:111, 3:112, 3:119, 3:170) on every race: no ear
  comes through (the Starglass Circlet's veil hangs past the ears).

numpy and scipy only: without trimesh the measurements run on the module's
numpy ray caster (race_headwear_clearance.NumpyRays, which gives the same
values), so CI can run it:
    python -m pytest godot-client/tests/test_race_headwear_clearance.py -q
"""
import json
from pathlib import Path
import sys
import unittest

import numpy as np

ROOT = Path(__file__).resolve().parents[2]
CLIENT = ROOT / 'godot-client'
sys.path.insert(0, str(ROOT / 'eloria-assets/tools'))
import race_headwear_clearance as rc

RACE_BODIES = tuple(f'{race}_{sex}' for race in ('glasswarden', 'greyhaven', 'mycelari', 'orun',
                                                 'ssarathi', 'stoneborn', 'votary')
                    for sex in ('male', 'female'))
KIT_HEADWEAR = ('3:134', '3:159', '3:115', '3:122')
OPEN_BANDS = ('3:111', '3:112', '3:119', '3:170')
BODIES = CLIENT / 'assets/actors/native/races'


def body(slug):
    return str(BODIES / f'{slug}.glb')


def scene_path(scene):
    return CLIENT / scene.removeprefix('res://')


class RaceHeadwearClearanceTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.registry = json.loads((CLIENT / 'data/actors/equipment.json').read_text(encoding='utf-8'))
        cls.policy = json.loads((ROOT / 'eloria-assets/tools/headwear_race_policy.json').read_text())['pieces']

    def test_every_piece_has_a_race_variant_with_the_policy(self):
        for key, rule in self.policy.items():
            model = self.registry['models'][key]
            with self.subTest(piece=key):
                self.assertEqual(model.get('raceFeatures'), rule['raceFeatures'])
                self.assertEqual(model.get('raceShoulders') == 'hide', rule['shoulders'] == 'hide')
            for slug in RACE_BODIES:
                variant = model['variants'].get('canonical_' + slug)
                with self.subTest(piece=key, body=slug):
                    self.assertIsNotNone(variant)
                    self.assertEqual(variant['authoredFor'], slug)
                    self.assertEqual(variant['fitProfile'], 'canonical')
                    self.assertEqual(variant['socket']['bone'], 'Head')
                    self.assertTrue(scene_path(variant['scene']).is_file(), variant['scene'])

    def test_the_seat_follows_the_head_size(self):
        """Socket to eye line = k x the Human's (the refit carries the Human
        fit about the eye line); the old per-race seats sat 44 mm under to
        59 mm over it."""
        for slug in RACE_BODIES:
            human = rc.human_slug(slug)
            k = rc.head_transfer(body(slug), body(human))['k']
            g, h = rc.head_geometry(body(slug)), rc.head_geometry(body(human))
            group = 'canonical_human_' + slug.rsplit('_', 1)[1]
            for key in self.policy:
                variants = self.registry['models'][key]['variants']
                race = variants['canonical_' + slug]['socket']['offset'][1] + g.head[1, 3] - g.eye_y
                base = variants[group]['socket']['offset'][1] + h.head[1, 3] - h.eye_y
                with self.subTest(piece=key, body=slug):
                    self.assertLess(abs(race - k * base), .006)

    def engine(self, g, slug, key):
        variant = self.registry['models'][key]['variants']['canonical_' + slug]
        socket = g.head[:3, 3] + np.asarray(variant['socket']['offset'])
        return rc._intersector(rc.piece_triangles(scene_path(variant['scene']), socket))

    def test_class_kit_headwear_keeps_the_race_head_inside(self):
        for slug in RACE_BODIES:
            g = rc.head_geometry(body(slug))
            for key in KIT_HEADWEAR:
                rule = self.policy[key]
                engine = self.engine(g, slug, key)
                ears = rc.radial_poke(g, engine, g.ears)
                skin = rc.radial_poke(g, engine, g.skin)['pokeCm2'] + rc.radial_poke(g, engine, g.neck_skin)['pokeCm2']
                with self.subTest(piece=key, body=slug):
                    self.assertLessEqual(ears['pokeCm2'], 2.0)
                    self.assertLessEqual(ears['maxPokeMm'], 5.0)
                    self.assertLessEqual(skin, 2.0)
                    if rule['raceFeatures'] == 'show' and g.feature_kind in ('crown', 'crystals'):
                        self.assertLessEqual(rc.radial_poke(g, engine, g.features)['pokeCm2'], 2.0)
                    if rule['horns'] == 'passThrough' and g.feature_kind == 'horns':
                        self.assertEqual(rc.edge_crossings(engine, *g.feature_edges), 0)

    def test_open_bands_keep_the_ears_inside_a_veil(self):
        """An open band leaves the ears free, but a veil or a cloth top that
        hangs past them keeps them in (3:112 let pointed ears through)."""
        for slug in RACE_BODIES:
            g = rc.head_geometry(body(slug))
            for key in OPEN_BANDS:
                ears = rc.radial_poke(g, self.engine(g, slug, key), g.ears)
                with self.subTest(piece=key, body=slug):
                    self.assertLessEqual(ears['pokeCm2'], 2.0)
                    self.assertLessEqual(ears['maxPokeMm'], 5.0)


if __name__ == '__main__':
    unittest.main()
