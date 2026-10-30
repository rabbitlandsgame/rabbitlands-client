"""Shared readers for the RL-head open-headwear audit and fit.

Everything is in the body's model space (glTF / Godot skeleton space): +Y up,
the face looks +Z, +X is the character's left. The shipped luminous bodies of
both sexes share one skeleton rest, so the Head joint and the headwear socket
frame are the same for the RL heads and the legacy (shipped) heads.

Read-only: nothing here writes an asset.
"""
from __future__ import annotations

import os as _o, sys as _s
_s.path.insert(0, _o.path.normpath(_o.path.join(_o.path.dirname(_o.path.abspath(__file__)), '..')))  # paths.py (Blender runs need this)
import paths  # repository-relative locations
import json
import os
import sys
from functools import lru_cache

import numpy as np

ROOT = paths.REPO
CLIENT = ROOT + '/godot-client'
sys.path.insert(0, ROOT + '/eloria-assets/tools/tpose_bodies/vendor')
import glbkit  # noqa: E402

EQUIPMENT = CLIENT + '/data/actors/equipment.json'
MODELS = CLIENT + '/data/actors/models.json'
POLICY = ROOT + '/eloria-assets/tools/headwear_race_policy.json'
PRESETS = CLIENT + '/data/actors/rl_head_presets.json'
RL_HEAD = CLIENT + '/assets/actors/native/rl_heads/rl_head_{sex}.glb'
RL_HAIR_DIR = os.environ.get('RL_HEAD_HAIR_DIR') or CLIENT + '/assets/actors/native/rl_heads/hair'
RL_HAIR = RL_HAIR_DIR + '/{style}.glb'
LEGACY_HAIR = CLIENT + '/assets/actors/native/hair/fitted/luminous_{sex}_{style}_{sex}.glb'
BODY = CLIENT + '/assets/actors/native/races/luminous_{sex}.glb'
LEGACY_HAIR_STYLES = ['parted', 'long', 'buns', 'buzzed', 'bob', 'ponytail', 'braid', 'topknot', 'mohawk']
OUT = ROOT + '/.local/rl-heads/evidence/headwear_audit'


def res(path: str) -> str:
    return CLIENT + '/' + path.removeprefix('res://')


@lru_cache(maxsize=None)
def equipment() -> dict:
    return json.load(open(EQUIPMENT, encoding='utf-8'))


@lru_cache(maxsize=None)
def policy() -> dict:
    return json.load(open(POLICY, encoding='utf-8'))['pieces']


def head_ids() -> list[int]:
    return sorted(int(k[2:]) for k in equipment()['models'] if k.startswith('3:'))


def model(visual: int) -> dict:
    return equipment()['models']['3:%d' % visual]


def variant(visual: int, sex: str) -> dict:
    """The model resolved for the luminous body (fit group canonical_human_<sex>)."""
    m = dict(model(visual))
    v = m.get('variants', {}).get('canonical_human_' + sex, {})
    m.pop('variants', None)
    m.update(v)
    return m


# ------------------------------------------------------------------ glb

def accessor(g, b, index):
    """glbkit.accessor plus glTF sparse substitution (morph targets are sparse)."""
    acc = g['accessors'][index]
    out = glbkit.accessor(g, b, index).copy()
    sp = acc.get('sparse')
    if sp:
        n = glbkit.COUNT[acc['type']]
        iv = g['bufferViews'][sp['indices']['bufferView']]
        idt = np.dtype('<' + glbkit.COMPONENT[sp['indices']['componentType']])
        idx = np.frombuffer(b, dtype=idt, count=sp['count'],
                            offset=iv.get('byteOffset', 0) + sp['indices'].get('byteOffset', 0)).astype(np.int64)
        vv = g['bufferViews'][sp['values']['bufferView']]
        vdt = np.dtype('<' + glbkit.COMPONENT[acc['componentType']])
        vals = np.frombuffer(b, dtype=vdt, count=sp['count'] * n,
                             offset=vv.get('byteOffset', 0) + sp['values'].get('byteOffset', 0)).reshape(-1, n)
        out[idx] = vals
    return out


def _skinned_rest(g, b, node_index, prim, P):
    node = g['nodes'][node_index]
    if 'skin' not in node or 'JOINTS_0' not in prim['attributes']:
        return None
    skin = g['skins'][node['skin']]
    G = glbkit.globals_of(g)
    ibm = glbkit.accessor(g, b, skin['inverseBindMatrices']).reshape(-1, 4, 4)
    # glTF stores matrices column-major; accessor gives rows of 16 -> transpose.
    ibm = np.transpose(ibm, (0, 2, 1))
    joint_mats = np.array([G[j] @ ibm[k] for k, j in enumerate(skin['joints'])])
    J = glbkit.accessor(g, b, prim['attributes']['JOINTS_0']).astype(np.int64)
    W = glbkit.accessor(g, b, prim['attributes']['WEIGHTS_0'])
    W = W / np.maximum(W.sum(1, keepdims=True), 1e-9)
    Ph = np.c_[P, np.ones(len(P))]
    out = np.zeros_like(P)
    for k in range(J.shape[1]):
        M = joint_mats[J[:, k]]
        out += W[:, k:k + 1] * np.einsum('nij,nj->ni', M, Ph)[:, :3]
    return out


def glb_primitives(path: str, targets: bool = False) -> list[dict]:
    """Every primitive with rest positions in model space (node or skin applied)."""
    g, b = glbkit.read(path)
    G = glbkit.globals_of(g)
    out = []
    for ni, node in enumerate(g['nodes']):
        if 'mesh' not in node:
            continue
        mesh = g['meshes'][node['mesh']]
        names = (mesh.get('extras') or {}).get('targetNames', [])
        for pi, prim in enumerate(mesh['primitives']):
            a = prim['attributes']
            P = glbkit.accessor(g, b, a['POSITION'])
            I = (glbkit.accessor(g, b, prim['indices']).astype(np.int64).reshape(-1, 3)
                 if 'indices' in prim else np.arange(len(P)).reshape(-1, 3))
            skinned = _skinned_rest(g, b, ni, prim, P)
            if skinned is not None:
                Pw = skinned
                M = None
            else:
                M = G[ni]
                Pw = P @ M[:3, :3].T + M[:3, 3]
            entry = dict(node=node.get('name', ''), mesh=mesh.get('name', ''),
                         material=g['materials'][prim['material']]['name'] if 'material' in prim else '',
                         P=Pw, I=I, extras=mesh.get('extras') or {}, raw=P, matrix=M)
            if 'TEXCOORD_0' in a:
                entry['UV'] = glbkit.accessor(g, b, a['TEXCOORD_0'])
            if targets and 'targets' in prim:
                entry['targets'] = {names[k] if k < len(names) else str(k):
                                    accessor(g, b, t['POSITION'])
                                    for k, t in enumerate(prim['targets']) if 'POSITION' in t}
            out.append(entry)
    return out


# ------------------------------------------------------------------ skeleton

@lru_cache(maxsize=None)
def body_rest(sex: str) -> dict:
    """Joint rest matrices (model space) by name, from the shipped body."""
    g, b = glbkit.read(BODY.format(sex=sex))
    G = glbkit.globals_of(g)
    skin = g['skins'][0]
    return {g['nodes'][j]['name']: G[j] for j in skin['joints']}


def head_rest(sex: str = 'female') -> np.ndarray:
    return body_rest(sex)['Head']


def fit_scale(sex: str) -> float:
    return float(head_rest(sex)[1, 3]) / float(equipment()['canonicalHeadRestY'])


def euler_yxz(deg) -> np.ndarray:
    x, y, z = np.radians(np.asarray(deg, dtype=float))
    cx, sx, cy, sy, cz, sz = np.cos(x), np.sin(x), np.cos(y), np.sin(y), np.cos(z), np.sin(z)
    Rx = np.array([[1, 0, 0], [0, cx, -sx], [0, sx, cx]])
    Ry = np.array([[cy, 0, sy], [0, 1, 0], [-sy, 0, cy]])
    Rz = np.array([[cz, -sz, 0], [sz, cz, 0], [0, 0, 1]])
    return Ry @ Rx @ Rz


def socket_matrix(visual: int, sex: str) -> np.ndarray:
    """replicated_actor_3d._socket_placement for the luminous body, model space."""
    m = variant(visual, sex)
    socket = m.get('socket') or equipment()['sockets']['3']
    fit = fit_scale(sex)
    scale = fit * float(m.get('scale', 1.0))
    M = np.eye(4)
    M[:3, :3] = euler_yxz(socket.get('rotationDegrees', [0, 0, 0])) * scale
    M[:3, 3] = head_rest(sex)[:3, 3] + np.asarray(socket.get('offset', [0, 0, 0]), float) * fit
    return M


def piece(visual: int, sex: str) -> dict:
    """The piece's triangles in model space, as the runtime places it at rest."""
    m = variant(visual, sex)
    path = res(m['scene'])
    prims = glb_primitives(path)
    M = socket_matrix(visual, sex)
    Ps, Is, n = [], [], 0
    covers = False
    for p in prims:
        Ps.append(p['P'] @ M[:3, :3].T + M[:3, 3])
        Is.append(p['I'] + n)
        n += len(p['P'])
        covers = covers or bool(p['extras'].get('coversHair', False))
    return dict(visual=visual, sex=sex, name=m.get('name', ''), scene=m['scene'], path=path,
                P=np.concatenate(Ps), I=np.concatenate(Is), coversHair=covers, socket=M,
                primitives=len(prims))


# ------------------------------------------------------------------ heads

@lru_cache(maxsize=None)
def _rl_head_prims(sex: str):
    return glb_primitives(RL_HEAD.format(sex=sex), targets=True)


def rl_head_info(sex: str) -> dict:
    g, _ = glbkit.read(RL_HEAD.format(sex=sex))
    return g['asset']['extras']['rlHead']


def rl_head(sex: str, controls: dict | None = None, parts=('rl_skin',), lod: str = 'rl_head_lod0') -> dict:
    """The RL head's surfaces (model space), with identity controls applied."""
    Ps, Is, n = [], [], 0
    for p in _rl_head_prims(sex):
        if p['node'] != lod or p['material'] not in parts:
            continue
        P = p['P'].copy()
        for control, value in (controls or {}).items():
            key = 'id_%s_%s' % (control, 'p' if value > 0 else 'n')
            if key in p.get('targets', {}):
                P += abs(value) * p['targets'][key]
        Ps.append(P)
        Is.append(p['I'] + n)
        n += len(P)
    return dict(P=np.concatenate(Ps), I=np.concatenate(Is))


def landmarks(sex: str) -> dict:
    return {k: np.asarray(v) for k, v in rl_head_info(sex)['landmarks'].items()}


@lru_cache(maxsize=None)
def _body_prims(sex: str):
    g, b = glbkit.read(BODY.format(sex=sex))
    skin = g['skins'][0]
    head_joint = [g['nodes'][j]['name'] for j in skin['joints']].index('Head')
    out = {}
    for p in glb_primitives(BODY.format(sex=sex)):
        out[p['node']] = p
    # Head weights per mesh, for the head region
    for ni, node in enumerate(g['nodes']):
        if 'mesh' not in node:
            continue
        prim = g['meshes'][node['mesh']]['primitives'][0]
        if 'JOINTS_0' not in prim['attributes']:
            continue
        J = glbkit.accessor(g, b, prim['attributes']['JOINTS_0']).astype(np.int64)
        W = glbkit.accessor(g, b, prim['attributes']['WEIGHTS_0'])
        if node.get('name') in out:
            out[node['name']]['head_w'] = (W * (J == head_joint)).sum(1)
    return out


def legacy_head(sex: str, meshes=('body', 'scalp', 'eyes', 'eyebrows')) -> dict:
    """The shipped head shell: Head-weighted triangles of the body meshes."""
    prims = _body_prims(sex)
    Ps, Is, n = [], [], 0
    for name in meshes:
        p = prims.get(name)
        if p is None:
            continue
        w = p.get('head_w', np.ones(len(p['P'])))
        keep = w[p['I']].mean(1) > 0.5
        Ps.append(p['P'])
        Is.append(p['I'][keep] + n)
        n += len(p['P'])
    return dict(P=np.concatenate(Ps), I=np.concatenate(Is))


def body_mesh(sex: str, names=('body',)) -> dict:
    prims = _body_prims(sex)
    Ps, Is, n = [], [], 0
    for name in names:
        p = prims[name]
        Ps.append(p['P'])
        Is.append(p['I'] + n)
        n += len(p['P'])
    return dict(P=np.concatenate(Ps), I=np.concatenate(Is))


def shipped_hair_styles(sex: str) -> dict:
    """The shipped body's hairStyles by file stem (what a luminous actor without
    an RL head draws for appearance hair 1..n; 0 is bald)."""
    m = json.load(open(MODELS, encoding='utf-8'))['models']['luminous_' + sex]
    return {os.path.basename(p)[:-4]: res(p) for p in m.get('hairStyles', [])}


def hair(sex: str, style: str, lod: str = '0') -> dict | None:
    """RL hair (`mira_bun`), a shipped fitted style (`legacy:long`) or a shipped
    hairStyles file by stem (`buzzed_female`), model space."""
    if style in ('', 'none'):
        return None
    shipped = shipped_hair_styles(sex)
    if style.startswith('legacy:'):
        path = LEGACY_HAIR.format(sex=sex, style=style.split(':', 1)[1])
    elif style in shipped:
        path = shipped[style]
    else:
        path = RL_HAIR.format(style=style)
    if not os.path.exists(path):
        return None
    Ps, Is, n = [], [], 0
    for p in glb_primitives(path):
        if not style.startswith('legacy:') and style not in shipped and not p['node'].endswith('lod' + lod) \
                and 'lod' in p['node']:
            continue
        Ps.append(p['P'])
        Is.append(p['I'] + n)
        n += len(p['P'])
    if not Ps:
        return None
    return dict(P=np.concatenate(Ps), I=np.concatenate(Is), path=path)


def rl_hair_styles() -> list[str]:
    d = RL_HAIR_DIR
    return sorted(f[:-4] for f in os.listdir(d) if f.endswith('.glb'))


def presets() -> dict:
    return json.load(open(PRESETS, encoding='utf-8'))['presets']


# ------------------------------------------------------------------ geometry

def trimesh_of(m: dict):
    import trimesh
    return trimesh.Trimesh(vertices=m['P'], faces=m['I'], process=False)


def components(I: np.ndarray, n: int) -> np.ndarray:
    """Connected-component label per vertex (by shared vertex index and position)."""
    from scipy.sparse import coo_matrix
    from scipy.sparse.csgraph import connected_components
    rows = np.r_[I[:, 0], I[:, 1], I[:, 2]]
    cols = np.r_[I[:, 1], I[:, 2], I[:, 0]]
    A = coo_matrix((np.ones(len(rows)), (rows, cols)), shape=(n, n))
    return connected_components(A, directed=False)[1]


def weld_components(P: np.ndarray, I: np.ndarray, tol: float = 1e-5) -> np.ndarray:
    """Components after welding split (UV seam) vertices by position."""
    q = np.round(P / tol).astype(np.int64)
    _, first, inv = np.unique(q, axis=0, return_index=True, return_inverse=True)
    inv = inv.ravel()
    labels = components(inv[I], len(first))
    return labels[inv]


def head_frame(sex: str, kind: str = 'rl') -> dict:
    """Cranium centre and anatomical heights from the RL head landmarks."""
    lm = landmarks(sex)
    eye = (lm['eyeL'] + lm['eyeR']) / 2
    return dict(eye=eye, top=lm['headTop'], nose=lm['nose'], menton=lm['menton'],
                head=head_rest(sex)[:3, 3])
