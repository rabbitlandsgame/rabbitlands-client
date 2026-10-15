"""Regressions for the folded groin and upper back reported on 2026-09-08.

Check the serialized rest surface itself: smooth weights can still leave a
fold baked into positions when source/canonical pelvis origins differ.

The Human (luminous_*) bodies these were written against were regenerated
from Meshy on 2026-10-05, so the checks now hold the new bodies to the same
contract. The new bodies share one position buffer across all seven body
surfaces, so a surface is only the vertices its own triangles use. They are
also coarser (a fifth to two-fifths of the old faces in these regions), and
their skin/shirt/trouser borders are cut along the painted seams, which
leaves many sliver triangles at the neckline and armholes. A count of
reversed faces therefore measures sliver count, not fold size, so the fold
checks weigh reversed faces by area.
"""
import hashlib
from pathlib import Path
import sys

import numpy as np
import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'eloria-assets/tools'))
from shared_player_bodies import g


@pytest.fixture(params=['male', 'female'])
def model(request):
    path = ROOT / f'godot-client/assets/actors/native/races/luminous_{request.param}.glb'
    d, b = g.read(path)
    return request.param, d, b


def surfaces(d, b):
    for mesh in d['meshes']:
        for p in mesh['primitives']:
            yield (mesh['name'],
                   {k: g.accessor(d, b, v) for k, v in p['attributes'].items()},
                   g.accessor(d, b, p['indices']).astype(int).reshape(-1, 3))


def orientation(a, f):
    points = a['POSITION'][f]
    geometric = np.cross(points[:, 1]-points[:, 0], points[:, 2]-points[:, 0])
    area = np.linalg.norm(geometric, axis=1) / 2
    geometric /= np.maximum(np.linalg.norm(geometric, axis=1, keepdims=True), 1e-15)
    authored = a['NORMAL'][f].mean(1)
    authored /= np.maximum(np.linalg.norm(authored, axis=1, keepdims=True), 1e-15)
    return points.mean(1), (geometric*authored).sum(1), area


def reversed_share(dot, area, region):
    """Fraction of the region's surface area whose winding opposes its normals."""
    return area[region & (dot < 0)].sum() / area[region].sum()


def test_front_trousers_do_not_fold_back_through_themselves(model):
    _, d, b = model
    for name, a, f in surfaces(d, b):
        if name != 'wardrobe_pants':
            continue
        c, dot, area = orientation(a, f)
        region = (abs(c[:, 0]) < .16) & (c[:, 1] > .72) & (c[:, 1] < 1.02) & (c[:, 2] > 0)
        # 296 male / 687 female faces on the regenerated bodies.
        assert region.sum() > 200
        # The previous male/female bodies had 180/114 reversed faces here,
        # 12.6%/8.6% of the area. The regenerated female has one 1.5 mm2
        # sliver standing edge-on in the centre-front seam valley
        # (0.001, 0.928, 0.074); its neighbours do not fold back over it.
        assert reversed_share(dot, area, region) < .001


def test_upper_back_has_no_broad_fold(model):
    _, d, b = model
    for name, a, f in surfaces(d, b):
        if name != 'wardrobe_shirt':
            continue
        c, dot, area = orientation(a, f)
        region = (abs(c[:, 0]) < .20) & (c[:, 1] > 1.24) & (c[:, 1] < 1.52) & (c[:, 2] < -.025)
        # 915 male / 1179 female faces on the regenerated bodies.
        assert region.sum() > 600
        # Allow the source collar's small sharp lips; reject the broad
        # crumpled patch. By area the reported models were 0.68% male /
        # 2.20% female (0.92% / 1.67% by count, against the old 0.8% limit),
        # the repaired 2026-09-08 bodies 0.05% / 0.14%, and the regenerated
        # bodies 0.10% / 0.00%: the male's 23 reversed faces (2.5% by count)
        # are slivers along the armhole border (|x| 0.185-0.191, y 1.415-1.494)
        # and the collar lip (y 1.48-1.51), 171 mm2 in all.
        assert reversed_share(dot, area, region) < .003


def test_waistband_still_follows_the_pelvis(model):
    _, d, b = model
    names = [d['nodes'][j]['name'] for j in d['skins'][0]['joints']]
    pelvis = names.index('pelvis')
    for name, a, f in surfaces(d, b):
        if name != 'wardrobe_pants':
            continue
        used = np.unique(f)
        influence = (a['WEIGHTS_0'][used] * (a['JOINTS_0'][used] == pelvis)).sum(1)
        # Moving the geometric fit anchor must not bind the whole waistband
        # to the lumbar spine merely because the donor Hips origin was high.
        assert influence.max() > .99
        assert np.count_nonzero(influence > .5) > 500


def test_body_repair_preserves_the_approved_head(model):
    sex, d, b = model
    # Positions, normals and UVs above the neck of the regenerated Human
    # heads approved on 2026-10-05 (installed bodies d30a505f / c3814266).
    # Only the vertices each head surface's triangles use are hashed, since
    # the surfaces share one buffer; on the old per-surface buffers this
    # reproduces release f53ceda2's 67c6cba8... / 81ed608e... exactly.
    expected = {'male': 'e09456849c78779d4b0c39e21e6b002324d9651a189136236b5934d22ece72de',
                'female': '78448088ddedf2e3bd8984e4420ee63f069f3a8a547daddff4138dbe40acd5e0'}
    head = hashlib.sha256()
    for name, a, f in surfaces(d, b):
        if name not in ('body', 'eyes', 'eyebrows', 'scalp'):
            continue
        used = np.unique(f)
        mask = used[a['POSITION'][used, 1] > 1.54]
        for key in ('POSITION', 'NORMAL', 'TEXCOORD_0'):
            head.update(a[key][mask].tobytes())
    assert head.hexdigest() == expected[sex]
