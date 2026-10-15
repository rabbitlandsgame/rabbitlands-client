"""Derived v2 race heads for rebase_race_body.py build (race programme P4/P6).

    python eloria-assets/tools/race_head_prepare.py scale --root <wt> --slug votary_male --out <dir>
    python eloria-assets/tools/race_head_prepare.py regions --root <wt> --heads <dir> [--check]
    python eloria-assets/tools/race_head_prepare.py landmarks --head <dir>/votary_male.v2.glb
    python eloria-assets/tools/race_head_prepare.py from-meshy --root <wt> --slug glasswarden_female --out <dir> [--archive <dir>]
    python eloria-assets/tools/race_head_prepare.py mask --root <wt> --slug glasswarden_female --head <dir>/glasswarden_female.crowned-v2.glb
    python eloria-assets/tools/race_head_prepare.py canvas --root <wt> --slug votary_male --head <glb> --out <png>

`rebase_race_body.py build` takes only a v2 race body as --head. This tool
writes such v2 bodies; build then treats them like the pre-install backups.

scale (decision 9): every race_head primitive (body[race_head], eyes,
eyebrows, scalp) and the wardrobe head band and cap of a v2 backup are scaled
uniformly by HEAD_SCALES[slug] about the rim centre: the area centroid of the
race-head rim loop on the upperCutM plane (travel along neck_01->Head). The rim
stays on that plane; skeleton, inverse binds, UVs, normals, indices, images,
the v2 neck and the tail keep their bytes. The output <slug>.v2.glb carries
asset.extras.headRescale {factor, centre, upperCutM, derivedFromSHA256, ...}
and highResolutionHead.scale/headTranslationM composed with the rescale. The
shipped v2 face mask is copied beside it unchanged (UVs are unchanged, so it
still addresses the same texels): rebase verify's shipped_mask finds it there.
rebase build copies asset.extras, so the built body carries headRescale too.

A front-view landmark (x, y) of the v2 head moves to
    (cx + f*(x-cx), cy + f*(y-cy))        f = factor, (cx, cy, cz) = centre
(rescale_xy), exactly: a uniform scale keeps the front-most hit front-most.
`landmarks` prints the iris/brow/skin-probe landmarks of rebase_race_body.py
V14 and test_face_texture_mapping.py transformed that way, from the v2 values
pinned in V2_LANDMARKS (never from the edited constants, so it is idempotent).

regions: face_regions.json polygons of the scaled slugs are the v2 polygons
(V2_REGIONS, pinned from face_regions.json at abc6e9dd0) under the same
transform in canvas pixels, rounded to whole pixels. Applying is idempotent:
the result depends only on V2_REGIONS and the derived head, never on what the
file holds; an entry that is neither the v2 nor the derived one is refused.
Only the slug's own line of the file is rewritten (CRLF kept).

from-meshy (decision 10, glasswarden_female): the crowned 2026-10 Meshy head
(generate_models/race_heads_2026-10/meshy) through prepare_race_head.extract;
a landmark alignment (eye-to-chin length matched, eye midpoint onto the
current eye line: x.9582 about (0, 1.6795, .033) onto (0, 1.6437, .033));
reduce_race_head_blender.py on Blender 5.2.1 with budgets neck 2000 / head
12000 / face 6000; prepare_race_head.bind; shared_player_bodies.run onto the
v2 template luminous_female@160d1d272; fit_neck (R2: the cropped-stump nape
taper at the cut eased onto the v2 head's nape, back half only; recorded in
asset.extras.neckFit); then asset.extras sourceSHA256 and
eloriaSurfacesSplit as install_high_resolution_race_heads.py stamped them and
its compact_materials pass, and a canonical buffer layout (the graft writes
attributes in hash-seed order). Template and semantic source come from git
blobs pinned by SHA-256, so the output is byte-reproducible (the archived
copy is its only other provenance). Its face polygons are hand-drawn in
face_regions.json on this head; `mask` bakes the face mask beside a v2 head
from the current entry, as install does (browStrokes dropped).
CROWNED_LANDMARKS are the iris/brow landmarks measured on the crowned head.

Nothing here writes into godot-client; `regions` edits face_regions.json only.
"""
from __future__ import annotations

import argparse
import copy
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import sys
import time

import numpy as np
from scipy.sparse import coo_matrix
from scipy.sparse.csgraph import connected_components
from scipy.spatial import cKDTree

sys.path.insert(0, str(Path(__file__).parent/'tpose_bodies/vendor'))
import glbkit as g  # noqa: E402
import equipment_authoring as ea  # noqa: E402

# Decision 9: relative head sizes, uniform about the rim centre.
HEAD_SCALES = {'votary_male': 1.12, 'votary_female': 1.12, 'orun_female': .95, 'ssarathi_female': 1.05}
DERIVED_SUFFIX = '.v2.glb'
CROWNED_SUFFIX = '.crowned-v2.glb'
HEAD_BAND_NODES = ('wardrobe_head_band', 'wardrobe_head_cap')
RIM_TOL = 2e-6
# The 14 v2 backups (sharedBodyShape.headSourceSHA256 of the bodies installed
# at abc6e9dd0): work-output/race-rebase/pre-install/<slug>.glb, Greyhaven in
# pre-install-pilot/.
V2_HEADS = {
    'glasswarden_female': '789d51e34e143732805749e3f00ed2ee1c3638d069f577347aade6743d267044',
    'glasswarden_male': 'b9e0ad4cf0211560d043b33836dc754a9e7ad4ebdd9c89658433a978c87b5eea',
    'greyhaven_female': '583c48a20a1e437fdc6038a248b396d635273e61af0f7ecd4830b4b06954853c',
    'greyhaven_male': 'ca3b23bd7916e41833570a941dbfb02446d441a0955cf35c5c07582ac7e52a7f',
    'mycelari_female': '86a0b972971c9f7bf6ee1992c089a28a5aba2aef5c6e177b4cbb69ccf77a1c37',
    'mycelari_male': 'db41829eaeddad1b42817e5a07ed6b0548801342cce42461cfdd5cd2318ec671',
    'orun_female': 'cb547d406c26228c99e8cc5707192a40c1a8ab8b56b410c394a9cc935d502903',
    'orun_male': '9044aebf2ea13cf82a9bdb40641481115e25521ec02e8a78df760a9b01299fd8',
    'ssarathi_female': 'f084e009872678aae4970a552410fd7eafa7c8532ece3875db32032014f69855',
    'ssarathi_male': '43451e600b853d75a40c5485c0d3619e216eef30933b939e8db5976856616d9a',
    'stoneborn_female': '6840b6df0b690dfdcee777a02c41b35f6126319453300a56245c286400e44e89',
    'stoneborn_male': 'b2016fbc3e43f31811858442618574e1b188dbf48daa11abb80cb7f7ba66337a',
    'votary_female': '1e25f34203feb96ac1e541f24c852996752ce0837513e6a0990f717fd6d2d5b6',
    'votary_male': '6657944d8a42e7ee3ce295b85e5d7bb7e5f7b677e3bcfc1c8774ae6f2044e5fe'}
# face_regions.json entries of the scaled slugs at abc6e9dd0, drawn on the v2
# heads (canvas: projection xMin -.15, yMax 1.76, 3000 px/m, x offset cropX).
V2_REGIONS = {
    'orun_female': {"cropY": 309, "eyes": [[[135, 73], [149, 60], [165, 56], [187, 60], [209, 72], [229, 92], [211, 98], [182, 100], [158, 93], [140, 86]], [[376, 93], [391, 74], [409, 60], [434, 56], [456, 62], [470, 74], [456, 89], [435, 97], [411, 102], [388, 100]]], "irises": [[180, 77, 28, 29], [420, 76, 28, 29]], "brows": [[[85, -3], [85, 2], [89, 6], [110, -7], [125, -7], [128, -10], [152, -8], [159, 1], [162, -1], [204, 26], [207, 24], [230, 38], [233, 36], [240, 43], [243, 40], [249, 46], [253, 43], [252, 32], [246, 23], [237, 22], [221, 9], [219, 11], [198, -3], [184, -6], [178, -12], [153, -21], [117, -22], [100, -15], [96, -19]], [[513, 2], [506, -15], [496, -16], [482, -23], [461, -24], [441, -20], [364, 17], [355, 24], [346, 41], [351, 47], [362, 38], [365, 40], [391, 29], [455, -6], [459, -4], [472, -8], [476, -5], [481, -10], [498, -4], [510, 6]]]},
    'ssarathi_female': {"cropY": 159, "eyes": [[[145, 51], [160, 52], [170, 64], [175, 79], [168, 95], [154, 102], [143, 94], [139, 79]], [[434, 56], [447, 50], [459, 56], [460, 72], [466, 86], [459, 98], [443, 102], [430, 96], [426, 82], [429, 68]]]},
    'votary_female': {"cropY": 378, "eyes": [[[167, 82], [183, 76], [204, 77], [221, 81], [232, 91], [217, 100], [198, 102], [181, 97]], [[361, 90], [374, 79], [391, 76], [412, 77], [434, 83], [424, 96], [405, 102], [386, 102], [371, 97]]], "irises": [[201, 86, 22, 23], [394, 86, 23, 22]], "brows": [[[139, 26], [171, 26], [205, 33], [235, 51], [238, 59], [205, 43], [171, 35], [141, 36]], [[354, 50], [386, 34], [428, 24], [447, 26], [432, 34], [391, 43], [355, 59]]]},
    'votary_male': {"cropY": 396, "eyes": [[[199, 59], [218, 57], [237, 60], [254, 65], [243, 73], [225, 76], [209, 72]], [[345, 65], [362, 58], [379, 55], [397, 58], [414, 64], [399, 73], [380, 77], [361, 73]]], "irises": [[225, 65, 24, 17], [377, 65, 24, 17]], "brows": [[[171, 43], [204, 37], [236, 39], [270, 47], [270, 53], [235, 47], [203, 45], [171, 49]], [[328, 47], [357, 39], [390, 37], [418, 42], [431, 50], [414, 48], [390, 45], [361, 47], [328, 54]]]}}
# v2 landmarks (front ray-cast x, y) of rebase_race_body.py IRISES/BROWS and
# test_face_texture_mapping.py LANDMARKS / brow centres at abc6e9dd0, and the
# skin probes both check for no eye colour.
V2_LANDMARKS = {
    'orun_female': {'irises': [(-.038, 1.631), (.038, 1.631)], 'brows': (.047, 1.650)},
    'ssarathi_female': {'irises': [(-.048, 1.680), (.048, 1.680)], 'brows': None},
    'votary_female': {'irises': [(-.031, 1.607), (.031, 1.607)], 'brows': (.035, 1.622)},
    'votary_male': {'irises': [(-.025, 1.607), (.025, 1.607)], 'brows': (.029, 1.613)}}
SKIN_PROBES = [(0, 1.68), (0, 1.63), (-.06, 1.595), (.06, 1.595)]

# Decision 10: the crowned Glasswarden female (P6 dry run, scratch race_p47/gwf).
MESHY_HEADS = {
    'glasswarden_female': {
        'original': 'generate_models/race_heads_2026-10/meshy/glasswarden_female_tpose.glb',
        'originalSHA256': 'b9ed0125b47bb8a5737250d79bb59aa09260d0d45aa386fd07419ec4a9880643',
        # The crowned v2 head from-meshy writes (byte-reproducible; V23 pins it).
        'outputSHA256': '77bbae1f9e2a9eb108d6fe73b384d7d923425634250ff7f540865479a0f72241',
        'donor': 'generate_models/race_heads_2026-10/meshy/glasswarden_female_tpose_rigged.glb',
        'donorSHA256': '8a3b3fe598d3f122378c4e95704fde3e4ab1c73f8ebd822e2bdc366eb075eea7',
        # v2 template: the old Luminous female (SPB asserts bit-equal rigs).
        'template': ('160d1d272', 'godot-client/assets/actors/native/races/luminous_female.glb',
                     '963726cc3180a57d8a8921c51a8695828d77bdac633a5bcf6f075472d6890dc7'),
        # Installed v3 body: extract's Head anchor and bind's region labels.
        'semantic': ('abc6e9dd0', 'godot-client/assets/actors/native/races/glasswarden_female.glb',
                     '01ff562f730e0ced0ba19554e3daa1db9267b1b1697ae3a38e7ebf69029fa611'),
        # Landmarks (orthographic front/side, race_p47/gwf/landmarks.json): the
        # current head's eye line 1.6437 and eye-to-chin .1123; the new head as
        # extract() places it 1.6795 / .1172 (its Meshy Head joint sits 4.8 cm
        # lower on the mesh). Scale about the eye midpoint, chin lands at 1.5314.
        'alignment': {'scale': .1123/.1172, 'pivotFrom': [0., 1.6795, .033], 'pivotTo': [0., 1.6437, .033],
                      'landmarks': {'current': {'eyeY': 1.6437, 'chinBottomY': 1.5314, 'eyeToChinM': .1123},
                                    'extracted': {'eyeY': 1.6795, 'chinBottomY': 1.5623, 'eyeToChinM': .1172}},
                      'rule': 'eye midpoint onto the current head eye line; eye-to-chin length matched'},
        'budgets': {'neck': 2000, 'head': 12000, 'face': 6000},
        'blenderVersion': 'Blender 5.2.1',
        # R2 (fit_neck): the nape taper at the cut, eased onto the v2 head's.
        'neckFit': {'bandM': .04, 'azFullDeg': 50., 'azZeroDeg': 100., 'azBinDeg': 10., 'travelBinM': .005}}}
# Front-view landmarks measured on the crowned head (face_regions canvas,
# head-atlas colour): iris = centroid of the glowing disc (lum >= 201),
# brow = centroid of the painted stroke (high-pass < -9 levels).
CROWNED_LANDMARKS = {'glasswarden_female': {'irises': [(-.0365, 1.6445), (.0368, 1.6445)], 'brows': (.042, 1.6656)}}
BLENDER = Path('C:/Program Files/Blender Foundation/Blender 5.2/blender.exe')
REDUCE_BUDGETS = '[(0,2000),(1,8000),(2,6000)]'


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def project_root(root):
    """The folder holding generate_models/ and work-output/ (a parent of the worktree)."""
    for base in (root, *root.parents):
        if (base/'generate_models').is_dir():
            return base
    raise FileNotFoundError(f'no generate_models/ above {root}')


def find_v2_head(root, slug, explicit=None):
    """The pre-install v2 backup of a race (sha pinned in V2_HEADS)."""
    if explicit:
        options = [Path(explicit)]
    else:
        rr = project_root(root)/'work-output/race-rebase'
        options = [rr/'pre-install'/f'{slug}.glb', rr/'pre-install-pilot'/f'{slug}.glb']
    for path in options:
        if path.exists() and digest(path) == V2_HEADS[slug]:
            return path
    raise FileNotFoundError(f'no v2 head with sha256 {V2_HEADS[slug]} in {[str(p) for p in options]}')


def rig_frame(d):
    """neck_01 origin and the unit neck_01->Head axis (rebase_race_body.rig_frame)."""
    skin = d['skins'][0]
    names = [d['nodes'][j]['name'] for j in skin['joints']]
    world = np.array(ea.global_matrices(d))[skin['joints']]
    origin = world[names.index('neck_01')][:3, 3]
    axis = world[names.index('Head')][:3, 3]-origin
    return origin, axis/np.linalg.norm(axis)


def weld(p, tol=1e-6):
    pairs = cKDTree(p).query_pairs(tol, output_type='ndarray')
    return connected_components(coo_matrix((np.ones(len(pairs)), (pairs[:, 0], pairs[:, 1])),
                                           shape=(len(p), len(p))).tocsr(), directed=False)[1]


def head_targets(d):
    """(node name, primitive) of every primitive the rescale moves; their
    POSITION accessors must not be shared with anything that stays."""
    moved, kept = [], []
    for node in d['nodes']:
        if 'mesh' not in node:
            continue
        if any(k in node for k in ('translation', 'rotation', 'scale', 'matrix')):
            raise ValueError(f'mesh node {node["name"]} carries a transform')
        for p in d['meshes'][node['mesh']]['primitives']:
            if p.get('targets'):
                raise ValueError(f'{node["name"]} has morph targets')
            role = p.get('extras', {}).get('sourceRole')
            (moved if role == 'race_head' or node['name'] in HEAD_BAND_NODES else kept).append((node['name'], p))
    shared = {p['attributes']['POSITION'] for _, p in moved} & {p['attributes']['POSITION'] for _, p in kept}
    if shared:
        raise ValueError(f'POSITION accessors {sorted(shared)} are shared with primitives that do not scale')
    return moved


def rim_centre(d, b, origin, axis, upper_cut):
    """Area centroid of the race-head rim loop on the upperCutM plane."""
    pos, faces, off = [], [], 0
    for mesh in d['meshes']:
        for p in mesh['primitives']:
            if p.get('extras', {}).get('sourceRole') != 'race_head':
                continue
            v = g.accessor(d, b, p['attributes']['POSITION'])
            pos.append(v); faces.append(g.accessor(d, b, p['indices']).astype(int).reshape(-1, 3)+off); off += len(v)
    p, f = np.concatenate(pos), np.concatenate(faces)
    ids = weld(p)
    e = np.sort(ids[np.concatenate([f[:, [0, 1]], f[:, [1, 2]], f[:, [2, 0]]])], axis=1)
    key = e[:, 0].astype(np.int64)*(ids.max()+1)+e[:, 1]
    _, inverse, count = np.unique(key, return_inverse=True, return_counts=True)
    travel = np.zeros(ids.max()+1); travel[ids] = (p-origin)@axis
    point = np.zeros((ids.max()+1, 3)); point[ids] = p
    open_edges = e[(count[inverse.ravel()] == 1)]
    open_edges = np.unique(open_edges[(np.abs(travel[open_edges]-upper_cut) < RIM_TOL).all(1)], axis=0)
    neighbours = {}
    for i, j in open_edges:
        neighbours.setdefault(int(i), []).append(int(j)); neighbours.setdefault(int(j), []).append(int(i))
    if any(len(v) != 2 for v in neighbours.values()):
        raise ValueError('race-head rim is not manifold')
    loops, pending = [], set(neighbours)
    while pending:
        first = min(pending); ring, prev, cur = [], None, first
        while True:
            ring.append(cur); pending.discard(cur)
            nxt = next(k for k in sorted(neighbours[cur]) if k != prev)
            prev, cur = cur, nxt
            if cur == first:
                break
        loops.append(np.array(ring))

    def centroid(ring):
        q = point[ring]; m = q.mean(0); a, c = q, np.roll(q, -1, axis=0)
        area = np.cross(a-m, c-m)@axis/2
        return (area[:, None]*(m+a+c)/3).sum(0)/area.sum(), abs(float(area.sum()))
    measured = [centroid(r) for r in loops]
    best = int(np.argmax([m[1] for m in measured]))
    centre = measured[best][0]
    centre = centre-((centre-origin)@axis-upper_cut)*axis
    ring = point[loops[best]]
    return centre, {'rimLoops': [len(r) for r in loops], 'rimVertices': len(loops[best]),
                    'rimAreaM2': measured[best][1],
                    'rimMeanRadiusM': float(np.linalg.norm(ring-centre, axis=1).mean()),
                    'rimMaxOffPlaneM': float(np.abs((ring-origin)@axis-upper_cut).max())}


def rescale_point(rescale, p):
    """A canonical-frame point of the v2 head on the derived head."""
    c = np.asarray(rescale['centre'], float)
    return c+rescale['factor']*(np.asarray(p, float)-c)


def rescale_xy(rescale, x, y):
    """A front-view landmark (x, y) of the v2 head on the derived head."""
    cx, cy = rescale['centre'][:2]
    f = rescale['factor']
    return cx+f*(x-cx), cy+f*(y-cy)


def head_rescale(path):
    """asset.extras.headRescale of a derived head or of a body built from one (or None)."""
    d, _ = g.read(path)
    return d['asset'].get('extras', {}).get('headRescale')


def rescaled_landmarks(slug, rescale):
    """V14 / test_face_texture_mapping landmarks of a derived head, from the pinned v2 values."""
    v2 = V2_LANDMARKS[slug]
    r = lambda xy: [round(v, 4)+0. for v in rescale_xy(rescale, *xy)]
    out = {'irises': [r(xy) for xy in v2['irises']], 'skinProbes': [r(xy) for xy in SKIN_PROBES],
           'v2': {'irises': [list(xy) for xy in v2['irises']], 'skinProbes': [list(xy) for xy in SKIN_PROBES]}}
    if v2['brows']:
        out['brows'] = r(v2['brows']); out['v2']['brows'] = list(v2['brows'])
    return out


def scale_head(root, slug, out, factor=None, head=None):
    root, out = Path(root).resolve(), Path(out).resolve()
    if 'godot-client' in out.parts:
        raise ValueError('Use an --out outside godot-client')
    factor = float(factor if factor is not None else HEAD_SCALES[slug])
    head = find_v2_head(root, slug, head)
    target = out/f'{slug}{DERIVED_SUFFIX}'
    if target.exists():
        raise FileExistsError(target)
    d, b = g.read(head)
    extras = d['asset'].get('extras', {})
    shape = extras.get('sharedBodyShape', {})
    if shape.get('version') != 2 or 'headRescale' in extras:
        raise ValueError(f'{head} is not an underived v2 race body')
    upper_cut = float(shape['upperCutM'])
    origin, axis = rig_frame(d)
    centre, rim = rim_centre(d, b, origin, axis, upper_cut)
    binary = bytearray(b)
    moved, done = head_targets(d), {}
    for name, p in moved:
        old = p['attributes']['POSITION']
        if old not in done:
            pos = g.accessor(d, b, old)
            done[old] = spb_append(d, binary, (centre+factor*(pos-centre)).astype('<f4'))
        p['attributes']['POSITION'] = done[old]
    rescale = {'version': 1, 'factor': factor, 'centre': centre.tolist(), 'upperCutM': upper_cut,
               'neckOrigin': origin.tolist(), 'neckAxis': axis.tolist(),
               'rule': 'uniform scale of every race_head primitive and the head band/cap about the area centroid '
                       'of the race-head rim loop on the upperCutM plane; skeleton, inverse binds, UVs, normals, '
                       'indices, images, v2 neck and tail unchanged',
               'scaledMeshes': sorted({name for name, _ in moved}),
               'derivedFrom': head.name, 'derivedFromSHA256': digest(head)}
    provenance = extras['highResolutionHead']
    rescale['highResolutionHeadBefore'] = {k: provenance[k] for k in ('scale', 'headTranslationM')}
    provenance['scale'] = float(provenance['scale'])*factor
    provenance['headTranslationM'] = rescale_point(rescale, provenance['headTranslationM']).tolist()
    extras['headRescale'] = rescale
    d, binary = g.compact(d, bytes(binary))
    out.mkdir(parents=True, exist_ok=True)
    g.write(target, d, binary)
    # Check: the rim is still one planar loop, only the moved accessors changed.
    nd, nb = g.read(target)
    after_centre, after_rim = rim_centre(nd, nb, origin, axis, upper_cut)
    if np.abs(after_centre-centre).max() > 1e-5 or after_rim['rimMaxOffPlaneM'] > RIM_TOL:
        raise ValueError(f'rim moved off its plane: {after_rim}')
    mask = head.with_suffix('.png')
    if mask.exists():
        shutil.copyfile(mask, out/f'{slug}.png')
    report = {'slug': slug, 'head': str(head), 'headSHA256': rescale['derivedFromSHA256'], 'output': str(target),
              'outputSHA256': digest(target), 'headRescale': rescale, 'rimBefore': rim, 'rimAfter': after_rim,
              'mask': str(out/f'{slug}.png') if mask.exists() else None,
              'landmarks': rescaled_landmarks(slug, rescale) if slug in V2_LANDMARKS else None,
              'faceRegions': derived_regions(slug, rescale, face_regions(root)['projection']) if slug in V2_REGIONS else None}
    target.with_suffix('.json').write_text(json.dumps(report, indent=2)+'\n', encoding='utf-8')
    return report


def spb_append(d, binary, values):
    import shared_player_bodies as spb
    return spb.append_array(d, binary, values, 'VEC3')


# ---------------------------------------------------------------------------
# face_regions.json
# ---------------------------------------------------------------------------

def regions_path(root):
    return Path(root)/'eloria-assets/tools/face_regions.json'


def face_regions(root):
    return json.loads(regions_path(root).read_text(encoding='utf-8'))


def derived_regions(slug, rescale, projection):
    """V2_REGIONS[slug] under the head rescale, in canvas pixels (whole px)."""
    if projection['cropX'] != 150:
        raise ValueError('build_face_masks offsets the polygons by 150 px')
    ppm, f = projection['pixelsPerMetre'], rescale['factor']
    v2 = V2_REGIONS[slug]
    cx = (rescale['centre'][0]-projection['xMin'])*ppm-projection['cropX']
    cy = (projection['yMax']-rescale['centre'][1])*ppm-v2['cropY']
    point = lambda x, y: [int(round(cx+f*(x-cx))), int(round(cy+f*(y-cy)))]
    out = {}
    for key, value in v2.items():
        if key in ('eyes', 'brows'):
            out[key] = [[point(*xy) for xy in poly] for poly in value]
        elif key == 'irises':
            out[key] = [point(x, y)+[int(round(f*rx)), int(round(f*ry))] for x, y, rx, ry in value]
        elif key == 'browStrokes':
            out[key] = [{'curve': [point(*xy) for xy in s['curve']], 'width': int(round(f*s['width']))} for s in value]
        elif key == 'cropY':
            out[key] = value
        else:
            raise ValueError(f'no rescale rule for face region key {key}')
    return out


def entry_line(slug, entry, comma):
    return f'    {json.dumps(slug)}: {json.dumps(entry, separators=(",", ":"))}'+(',' if comma else '')


def write_region_entries(root, entries, allowed):
    """Rewrite only these slugs' lines of face_regions.json; refuse when a
    current entry is not in `allowed[slug]` (the v2 or the derived entry)."""
    path = regions_path(root)
    raw = path.read_bytes()
    eol = b'\r\n' if b'\r\n' in raw else b'\n'
    lines = raw.split(eol)
    current = json.loads(raw)['models']
    changed = []
    for slug, entry in entries.items():
        if current.get(slug) == entry:
            continue
        if allowed.get(slug) is not None and current.get(slug) not in allowed[slug]:
            raise ValueError(f'face_regions.json {slug} is neither its v2 nor its derived entry; refusing')
        prefix = f'    {json.dumps(slug)}: '.encode()
        index = [i for i, line in enumerate(lines) if line.startswith(prefix)]
        if len(index) != 1:
            raise ValueError(f'{slug} is not one line of face_regions.json')
        comma = lines[index[0]].rstrip().endswith(b',')
        lines[index[0]] = entry_line(slug, entry, comma).encode()
        changed.append(slug)
    if changed:
        text = eol.join(lines)
        parsed = json.loads(text)
        for slug, entry in entries.items():
            if parsed['models'][slug] != entry:
                raise ValueError(f'{slug} did not round-trip')
        if {k: v for k, v in parsed['models'].items() if k not in entries} != \
                {k: v for k, v in current.items() if k not in entries}:
            raise ValueError('other face_regions entries changed')
        path.write_bytes(text)
    return changed


def apply_regions(root, heads, check=False):
    """Derived polygons of every scaled slug whose <slug>.v2.glb is in `heads`."""
    root = Path(root).resolve()
    projection = face_regions(root)['projection']
    current = face_regions(root)['models']
    entries, allowed, report = {}, {}, {}
    for slug in HEAD_SCALES:
        path = Path(heads)/f'{slug}{DERIVED_SUFFIX}'
        if not path.exists():
            continue
        rescale = head_rescale(path)
        if rescale is None or rescale['derivedFromSHA256'] != V2_HEADS[slug]:
            raise ValueError(f'{path} is not derived from the {slug} v2 head')
        entries[slug] = derived_regions(slug, rescale, projection)
        allowed[slug] = [V2_REGIONS[slug], entries[slug]]
        report[slug] = {'factor': rescale['factor'], 'current': 'derived' if current[slug] == entries[slug]
                        else 'v2' if current[slug] == V2_REGIONS[slug] else 'other'}
    if check:
        return {'ok': all(r['current'] == 'derived' for r in report.values()), 'slugs': report}
    changed = write_region_entries(root, entries, allowed)
    return {'changed': changed, 'slugs': report}


# ---------------------------------------------------------------------------
# P6: the crowned Glasswarden female from the 2026-10 Meshy run
# ---------------------------------------------------------------------------

def git_blob(root, commit, path, sha, target):
    data = subprocess.run(['git', '-C', str(root), 'show', f'{commit}:{path}'], check=True, capture_output=True).stdout
    if hashlib.sha256(data).hexdigest() != sha:
        raise ValueError(f'{commit}:{path} is not sha256 {sha}')
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(data)
    return target


def align_landmarks(source, target, alignment):
    """P' = s(P - pivotFrom) + pivotTo on the extracted source head; the
    composed original->canonical scale/translation go to highResolutionHead."""
    import shared_player_bodies as spb
    d, b = g.read(source)
    p = d['meshes'][0]['primitives'][0]
    s = float(alignment['scale'])
    pivot_from, pivot_to = np.array(alignment['pivotFrom']), np.array(alignment['pivotTo'])
    pos = (g.accessor(d, b, p['attributes']['POSITION'])-pivot_from)*s+pivot_to
    binary = bytearray(b)
    p['attributes']['POSITION'] = spb.append_array(d, binary, pos.astype('<f4'), 'VEC3')
    hr = d['asset']['extras']['highResolutionHead']
    translation = pivot_to-s*pivot_from
    hr['landmarkAlignment'] = {'scale': s, 'pivotFrom': pivot_from.tolist(), 'pivotTo': pivot_to.tolist(),
                               'translationM': translation.tolist(), 'rule': alignment['rule'],
                               'landmarks': alignment['landmarks'],
                               'extractScale': hr['scale'], 'extractTranslationM': hr['headTranslationM']}
    hr['scale'] = float(hr['scale'])*s
    hr['headTranslationM'] = (s*np.array(hr['headTranslationM'])+translation).tolist()
    d, binary = g.compact(d, bytes(binary))
    g.write(target, d, binary)


def blender_reduce(blender, source, target, budgets, log):
    """reduce_race_head_blender.py with the region budgets replaced."""
    script = Path(__file__).with_name('reduce_race_head_blender.py').read_text(encoding='utf-8')
    wanted = f'[(0,{budgets["neck"]}),(1,{budgets["head"]}),(2,{budgets["face"]})]'
    if script.count(REDUCE_BUDGETS) != 1:
        raise ValueError('reduce_race_head_blender.py no longer carries the expected budget list')
    patched = target.with_name('reduce_race_head_budgets.py')
    patched.write_text(script.replace(REDUCE_BUDGETS, wanted), encoding='utf-8')
    with open(log, 'w', encoding='utf-8') as handle:
        subprocess.run([str(blender), '--background', '--factory-startup', '--threads', '8', '--python-exit-code', '1',
                        '--python', str(patched), '--', str(source), str(target)],
                       stdout=handle, stderr=subprocess.STDOUT, check=True)
    text = Path(log).read_text(encoding='utf-8', errors='replace')
    return {'script': 'eloria-assets/tools/reduce_race_head_blender.py',
            'scriptSHA256': hashlib.sha256(script.replace('\r\n', '\n').encode()).hexdigest(),
            'budgets': budgets, 'regions': [line for line in text.splitlines() if line.startswith(('REGION', 'REDUCED_HEAD'))]}


def canonical_layout(d, b):
    """Re-pack the binary chunk in document order (meshes, primitives, sorted
    attribute names, indices; skins; images), dropping unreferenced data:
    shared_player_bodies writes a primitive's attributes in set order, which
    follows the interpreter's hash seed, so its bytes differ run to run."""
    order = []
    for mesh in d['meshes']:
        for p in mesh['primitives']:
            order += [p['attributes'][k] for k in sorted(p['attributes'])]
            order += [p['indices']] if 'indices' in p else []
            for target in p.get('targets', []):
                order += [target[k] for k in sorted(target)]
    for skin in d.get('skins', []):
        order += [skin['inverseBindMatrices']] if 'inverseBindMatrices' in skin else []
    for clip in d.get('animations', []):
        for sampler in clip['samplers']:
            order += [sampler['input'], sampler['output']]
    accessors = list(dict.fromkeys(order))
    if any('sparse' in d['accessors'][i] for i in accessors):
        raise ValueError('sparse accessors are not re-packed')
    views = list(dict.fromkeys([d['accessors'][i]['bufferView'] for i in accessors if 'bufferView' in d['accessors'][i]]
                               + [im['bufferView'] for im in d.get('images', []) if 'bufferView' in im]))
    amap = {old: new for new, old in enumerate(accessors)}
    vmap = {old: new for new, old in enumerate(views)}
    out, new_views = bytearray(), []
    for old in views:
        view = dict(d['bufferViews'][old])
        start = view.get('byteOffset', 0)
        out += b'\0'*(-len(out) % 4)
        view['byteOffset'] = len(out)
        out += b[start:start+view['byteLength']]
        new_views.append(view)
    new_accessors = []
    for old in accessors:
        acc = dict(d['accessors'][old])
        if 'bufferView' in acc:
            acc['bufferView'] = vmap[acc['bufferView']]
        new_accessors.append(acc)
    d['bufferViews'], d['accessors'] = new_views, new_accessors
    for mesh in d['meshes']:
        for p in mesh['primitives']:
            p['attributes'] = {k: amap[p['attributes'][k]] for k in sorted(p['attributes'])}
            if 'indices' in p:
                p['indices'] = amap[p['indices']]
            for target in p.get('targets', []):
                for k in target:
                    target[k] = amap[target[k]]
    for skin in d.get('skins', []):
        if 'inverseBindMatrices' in skin:
            skin['inverseBindMatrices'] = amap[skin['inverseBindMatrices']]
    for clip in d.get('animations', []):
        for sampler in clip['samplers']:
            sampler['input'], sampler['output'] = amap[sampler['input']], amap[sampler['output']]
    for image in d.get('images', []):
        if 'bufferView' in image:
            image['bufferView'] = vmap[image['bufferView']]
    return d, bytes(out)


def triangles(d):
    count = {}
    for node in d['nodes']:
        if 'mesh' in node:
            for p in d['meshes'][node['mesh']]['primitives']:
                key = f'{node["name"]}:{p.get("extras", {}).get("sourceRole")}'
                count[key] = count.get(key, 0)+d['accessors'][p['indices']]['count']//3
    return count


def fit_neck(d, b, reference, spec):
    """R2 (review of the P6 pilot): the crowned head's nape tapers in to its
    cut like the stump of a cropped Meshy neck (radius 43 mm at the back of
    the rim against 73 mm on the v2 head, 76 mm 3 cm higher), so the Human
    neck flared out under it as a collar ledge with a recessed nape. Body and
    scalp race_head vertices in the band [upperCutM, upperCutM + bandM] move
    out radially from the neck axis (inside the plane across it, so the rim
    stays planar) toward the reference v2 head's surface radius at their
    azimuth and travel, by smoothstep weights: 1 at the rim, 0 at the band top,
    1 within azFullDeg of the back, 0 beyond azZeroDeg (the throat and chin
    never move). A vertex already outside the reference radius (crest
    crystals, ears) stays. Normals of the moved vertices are recomputed
    (area-weighted over both primitives, welded). Returns the new (d, binary)
    and the report."""
    import shared_player_bodies as spb
    origin, axis = rig_frame(d)
    upper_cut = float(d['asset']['extras']['sharedBodyShape']['upperCutM'])
    ex = np.array([1., 0, 0]); ex -= (ex@axis)*axis; ex /= np.linalg.norm(ex); ez = np.cross(ex, axis)

    def polar(p):
        rel = np.asarray(p, float)-origin
        t = rel@axis
        radial = rel-np.outer(t, axis)
        return t, np.linalg.norm(radial, axis=1), np.degrees(np.arctan2(radial@ex, radial@ez)) % 360, radial
    rd, rb = g.read(reference)
    ref = np.concatenate([g.accessor(rd, rb, p['attributes']['POSITION'])[np.unique(g.accessor(rd, rb, p['indices']).astype(int))]
                          for m in rd['meshes'] if m['name'] in ('body', 'scalp') for p in m['primitives']
                          if p.get('extras', {}).get('sourceRole') == 'race_head'])
    rt, rr, ra, _ = polar(ref)
    band, az_step, t_step = spec['bandM'], spec['azBinDeg'], spec['travelBinM']
    az_bins = np.arange(0, 360, az_step)
    t_bins = np.arange(upper_cut, upper_cut+band+t_step/2, t_step)
    table = np.full((len(az_bins), len(t_bins)), np.nan)
    for i, a in enumerate(az_bins):
        near_a = np.abs(((ra-a+180) % 360)-180) < az_step
        for j, tb in enumerate(t_bins):
            sel = near_a & (np.abs(rt-tb) < t_step)
            if sel.any():
                table[i, j] = float(np.median(rr[sel]))
    if np.isnan(table).any():
        raise ValueError('reference head leaves neck bins empty')

    def reference_radius(t, a):
        fi = np.clip((t-upper_cut)/t_step, 0, len(t_bins)-1)
        ai = (a/az_step) % len(az_bins)
        i0 = np.floor(ai).astype(int); i1 = (i0+1) % len(az_bins); wa = ai-i0
        j0 = np.floor(fi).astype(int); j1 = np.minimum(j0+1, len(t_bins)-1); wt = fi-j0
        return ((table[i0, j0]*(1-wt)+table[i0, j1]*wt)*(1-wa)+(table[i1, j0]*(1-wt)+table[i1, j1]*wt)*wa)

    def smooth(x):
        x = np.clip(x, 0, 1)
        return x*x*(3-2*x)
    prims = [p for m in d['meshes'] if m['name'] in ('body', 'scalp') for p in m['primitives']
             if p.get('extras', {}).get('sourceRole') == 'race_head']
    positions = [g.accessor(d, b, p['attributes']['POSITION']).astype(float) for p in prims]
    normals = [g.accessor(d, b, p['attributes']['NORMAL']).astype(float) for p in prims]
    faces = [g.accessor(d, b, p['indices']).astype(int).reshape(-1, 3) for p in prims]
    if len({p['attributes']['POSITION'] for p in prims}) != len(prims):
        raise ValueError('race_head primitives share a POSITION accessor')
    moved_p, moves = [], []
    for p in positions:
        t, r, a, radial = polar(p)
        delta = np.abs(((a-180+180) % 360)-180)
        w = smooth((upper_cut+band-t)/band)*(t >= upper_cut-1e-6)*smooth((spec['azZeroDeg']-delta)/(spec['azZeroDeg']-spec['azFullDeg']))
        target = reference_radius(t, a)
        grow = np.where(w > 0, np.maximum(target-r, 0)*w, 0.)
        q = p+radial/np.maximum(r, 1e-9)[:, None]*grow[:, None]
        moved_p.append(q); moves.append(grow)
    # Normals: area-weighted over both primitives, welded; only moved rows change.
    allp = np.concatenate(moved_p); offs = np.cumsum([0]+[len(p) for p in positions])
    ids = weld(np.concatenate(positions))
    acc = np.zeros((ids.max()+1, 3))
    for k, f in enumerate(faces):
        ff = f+offs[k]
        n = np.cross(allp[ff[:, 1]]-allp[ff[:, 0]], allp[ff[:, 2]]-allp[ff[:, 0]])
        for c in range(3):
            np.add.at(acc, ids[ff[:, c]], n)
    acc /= np.maximum(np.linalg.norm(acc, axis=1, keepdims=True), 1e-20)
    binary = bytearray(b)
    for k, p in enumerate(prims):
        rows = ids[offs[k]:offs[k+1]]
        moved = moves[k] > 0
        n = normals[k].copy(); n[moved] = acc[rows[moved]]
        p['attributes']['POSITION'] = spb.append_array(d, binary, moved_p[k].astype('<f4'), 'VEC3')
        p['attributes']['NORMAL'] = spb.append_array(d, binary, n.astype('<f4'), 'VEC3')
    grow = np.concatenate(moves)
    report = {**spec, 'reference': Path(reference).name, 'referenceSHA256': digest(reference),
              'movedVertices': int((grow > 0).sum()), 'maxMoveM': float(grow.max()),
              'rule': 'body/scalp race_head vertices in [upperCutM, +bandM] move out radially toward the reference '
                      'head surface radius at their azimuth and travel (smoothstep in travel and azimuth about the back)'}
    d, binary = g.compact(d, bytes(binary))
    return d, binary, report


def from_meshy(root, slug, out, blender=BLENDER, archive=None):
    from prepare_race_head import extract, bind
    import shared_player_bodies as spb
    from compact_character_materials import compact_materials
    root, out = Path(root).resolve(), Path(out).resolve()
    if 'godot-client' in out.parts:
        raise ValueError('Use an --out outside godot-client')
    spec = MESHY_HEADS[slug]
    target = out/f'{slug}{CROWNED_SUFFIX}'
    work = out/f'{slug}.work'
    if target.exists() or work.exists():
        raise FileExistsError(f'{target} or {work} exists')
    version = subprocess.run([str(blender), '--version'], check=True, capture_output=True, text=True).stdout.splitlines()[0]
    if not version.startswith(spec['blenderVersion']):
        raise ValueError(f'{blender} is {version}, not {spec["blenderVersion"]}')
    project = project_root(root)
    original, donor = project/spec['original'], project/spec['donor']
    for path, sha in ((original, spec['originalSHA256']), (donor, spec['donorSHA256'])):
        if digest(path) != sha:
            raise ValueError(f'{path} is not sha256 {sha}')
    template = git_blob(root, *spec['template'], work/'inputs/luminous_female.glb')
    semantic = git_blob(root, *spec['semantic'], work/'inputs'/f'{slug}.glb')
    timings, t = {}, time.time()
    extracted, aligned = work/'source-head.extracted.glb', work/'source-head.glb'
    extract(original, donor, semantic, extracted)
    timings['extract'] = time.time()-t; t = time.time()
    align_landmarks(extracted, aligned, spec['alignment'])
    reduced = work/'reduced.glb'
    reduction = blender_reduce(blender, aligned, reduced, spec['budgets'], work/'reduction.log')
    timings['reduce'] = time.time()-t; t = time.time()
    bound = work/'head.glb'
    bind(aligned, reduced, template, semantic, bound)
    timings['bind'] = time.time()-t; t = time.time()
    body = work/'body_v2.glb'
    graft = spb.run(bound, template, body, texture_source=aligned)
    timings['graft'] = time.time()-t
    d, b = g.read(body)
    neck = None
    if 'neckFit' in spec:
        d, b, neck = fit_neck(d, b, find_v2_head(root, slug), spec['neckFit'])
    extras = d['asset']['extras']
    if neck:
        extras['neckFit'] = neck
    provenance = extras['highResolutionHead']
    if provenance['originalSHA256'] != spec['originalSHA256'] or extras['sharedBodyShape'].get('version') != 2:
        raise ValueError('graft lost the head provenance')
    provenance['originalPath'] = spec['original']
    extras['sourceSHA256'] = provenance['originalSHA256']
    extras['eloriaSurfacesSplit'] = 14
    d = compact_materials(d, b)
    d, binary = canonical_layout(d, b)
    # Hair and headwear binds: the race skeleton and inverse binds stay the v2 head's.
    v2d, v2b = g.read(find_v2_head(root, slug))
    ibm = (ea.accessor_array(d, binary, d['skins'][0]['inverseBindMatrices']).tobytes()
           == ea.accessor_array(v2d, v2b, v2d['skins'][0]['inverseBindMatrices']).tobytes())
    names = [d['nodes'][j]['name'] for j in d['skins'][0]['joints']]
    if not ibm or names != [v2d['nodes'][j]['name'] for j in v2d['skins'][0]['joints']]:
        raise ValueError('crowned head skeleton differs from the v2 head')
    g.write(target, d, binary)
    report = {'slug': slug, 'output': str(target), 'outputSHA256': digest(target),
              'inputs': {'original': str(original), 'originalSHA256': spec['originalSHA256'],
                         'donor': str(donor), 'donorSHA256': spec['donorSHA256'],
                         'template': ':'.join(spec['template'][:2]), 'templateSHA256': spec['template'][2],
                         'semantic': ':'.join(spec['semantic'][:2]), 'semanticSHA256': spec['semantic'][2],
                         'blender': version},
              'highResolutionHead': provenance, 'sharedBodyShape': extras['sharedBodyShape'],
              'reduction': reduction, 'graft': {k: graft[k] for k in ('lowerBoundaryLoops', 'upperBoundaryLoops',
                                                                      'headWardrobeTrianglesReclassifiedAsSkin')},
              'triangles': triangles(d), 'ibmBytesEqualV2': ibm, 'seconds': timings, 'neckFit': neck,
              'next': ['face_regions.json glasswarden_female eyes/irises/brows for this head, then `mask`',
                       f'build --head {target} --head-texture {original}']}
    target.with_suffix('.json').write_text(json.dumps(report, indent=2)+'\n', encoding='utf-8')
    if archive:
        archive = Path(archive); archive.mkdir(parents=True, exist_ok=True)
        for path in (target, target.with_suffix('.json')):
            shutil.copyfile(path, archive/path.name)
    return report


def bake_mask(root, slug, head):
    """Face mask of a v2 head from the current face_regions.json entry, written
    beside it as <slug>.png (rebase verify's shipped_mask), as install bakes."""
    from build_face_masks import bake
    from PIL import Image
    regions = face_regions(root)
    region = copy.deepcopy(regions['models'][slug]); region.pop('browStrokes', None)
    mask, info = bake(Path(head), region, regions['projection'])
    target = Path(head).parent/f'{slug}.png'
    Image.fromarray(mask).save(target, optimize=True)
    info['maskSHA256'] = digest(target)
    info['mask'] = str(target)
    return info


def canvas(root, slug, head, target, regions=None):
    """Review image: the head's front projection in the face_regions canvas
    with the slug's polygons (eyes red, irises green, brows orange)."""
    from PIL import Image, ImageDraw
    import rebase_race_body as rrb
    data = face_regions(root)
    region = regions or data['models'][slug]
    colour, _, depth = rrb.front_projection(head, np.zeros((4, 4, 3), 'u1'))
    image = Image.fromarray((np.clip(np.where(np.isfinite(depth)[..., None], colour, 1), 0, 1)*255).astype('u1'))
    draw = ImageDraw.Draw(image)
    off = (150, region['cropY'])
    for poly in region.get('eyes', []):
        draw.polygon([(x+off[0], y+off[1]) for x, y in poly], outline=(255, 0, 0))
    for poly in region.get('brows', []):
        draw.polygon([(x+off[0], y+off[1]) for x, y in poly], outline=(255, 150, 0))
    for x, y, rx, ry in region.get('irises', []):
        draw.ellipse((x+off[0]-rx, y+off[1]-ry, x+off[0]+rx, y+off[1]+ry), outline=(0, 200, 0))
    image.save(target)
    return target


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('action', choices=['scale', 'regions', 'landmarks', 'from-meshy', 'mask', 'canvas'])
    parser.add_argument('--root', type=Path, default=Path(__file__).resolve().parents[2])
    parser.add_argument('--slug')
    parser.add_argument('--out', type=Path)
    parser.add_argument('--head', type=Path)
    parser.add_argument('--heads', type=Path)
    parser.add_argument('--factor', type=float)
    parser.add_argument('--check', action='store_true')
    parser.add_argument('--blender', type=Path, default=BLENDER)
    parser.add_argument('--archive', type=Path)
    args = parser.parse_args()
    if args.action == 'scale':
        result = scale_head(args.root, args.slug, args.out, args.factor, args.head)
    elif args.action == 'regions':
        result = apply_regions(args.root, args.heads, args.check)
    elif args.action == 'landmarks':
        rescale = head_rescale(args.head)
        if rescale is None:
            result = {'slug': args.slug, **CROWNED_LANDMARKS[args.slug], 'skinProbes': SKIN_PROBES}
        else:
            slug = args.slug or next(s for s, sha in V2_HEADS.items() if sha == rescale['derivedFromSHA256'])
            result = {'slug': slug, 'factor': rescale['factor'], 'centre': rescale['centre'],
                      **rescaled_landmarks(slug, rescale)}
    elif args.action == 'from-meshy':
        result = from_meshy(args.root, args.slug, args.out, args.blender, args.archive)
    elif args.action == 'mask':
        result = bake_mask(args.root, args.slug, args.head)
    else:
        result = str(canvas(args.root, args.slug, args.head, args.out))
    print(json.dumps(result, indent=2))
    if args.action == 'regions' and args.check and not result['ok']:
        raise SystemExit(1)


if __name__ == '__main__':
    main()
