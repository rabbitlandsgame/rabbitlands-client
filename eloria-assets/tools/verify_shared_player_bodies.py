"""Independent source-preservation and join checks for shared body candidates."""
from __future__ import annotations

import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
import sys

import numpy as np
from scipy.spatial import cKDTree
from scipy.sparse import coo_matrix
from scipy.sparse.csgraph import connected_components

import equipment_authoring as ea

FIELDS = ('POSITION', 'NORMAL', 'TEXCOORD_0', 'JOINTS_0', 'WEIGHTS_0')
GEOMETRY_FIELDS = tuple(k for k in FIELDS if k != 'TEXCOORD_0')


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def primitives(d, b):
    cache = {}
    for mesh in d['meshes']:
        for p in mesh['primitives']:
            attrs = p['attributes']
            key = tuple(sorted(attrs.items()))
            if key not in cache:
                cache[key] = {name: ea.accessor_array(d, b, index) for name, index in attrs.items()}
            yield mesh['name'], p.get('extras', {}).get('sourceRole'), cache[key], ea.accessor_array(d, b, p['indices']).astype(int).reshape(-1, 3)


def signatures(a, faces, fields=FIELDS):
    return Counter(hashlib.sha256(b''.join(a[k][f].tobytes() for k in fields)).hexdigest() for f in faces)


def image_payloads(d, b):
    # Unused template resources may be stripped during lossless packaging.
    from compact_character_materials import compact_materials
    d = compact_materials(d, b)
    result = []
    for image in d['images']:
        view = d['bufferViews'][image['bufferView']]
        start = view.get('byteOffset', 0)
        result.append(hashlib.sha256(b[start:start+view['byteLength']]).hexdigest())
    return result


def neck_edges(parts, origin, axis, height):
    edges = []
    for name, role, a, faces in parts:
        if role not in ('shared_body', 'shared_neck', 'race_head', 'neck_join'):
            continue
        v = a['POSITION']
        plane = np.abs((v-origin)@axis-height) < 5e-7
        for edge in (faces[:, [0, 1]], faces[:, [1, 2]], faces[:, [2, 0]]):
            edges.extend(v[edge[plane[edge].all(1)]])
    points = np.asarray(edges).reshape(-1, 3)
    pairs = cKDTree(points).query_pairs(1e-6, output_type='ndarray')
    _, ids = connected_components(coo_matrix((np.ones(len(pairs)), (pairs[:, 0], pairs[:, 1])),
                                             shape=(len(points), len(points))).tocsr(), directed=False)
    ee = ids.reshape(-1, 2)
    counts = Counter(tuple(sorted(pair)) for pair in ee if pair[0] != pair[1])
    unmatched = [edge for edge, count in counts.items() if count != 2]
    return {'geometricEdges': len(counts), 'unmatchedEdges': len(unmatched),
            'collapsedSubMicronEdges': int((ee[:, 0] == ee[:, 1]).sum())}



def neck_attributes(parts, origin, axis, height):
    """Joined copies must shade and deform together, not merely meet at rest."""
    def collect(roles):
        pp,nn,ww=[],[],[]
        for name,role,a,faces in parts:
            if role not in roles: continue
            used=np.unique(faces)
            ids=used[np.abs((a['POSITION'][used]-origin)@axis-height)<5e-7]
            if not len(ids):continue
            dense=np.zeros((len(ids),77))
            for k in range(4):
                dense[np.arange(len(ids)),a['JOINTS_0'][ids,k]]+=a['WEIGHTS_0'][ids,k]
            pp.append(a['POSITION'][ids]);nn.append(a['NORMAL'][ids]);ww.append(dense)
        return np.concatenate(pp),np.concatenate(nn),np.concatenate(ww)
    p,n,w=collect({'neck_join'})
    other,on,ow=collect({'shared_body','shared_neck','race_head'})
    matches=cKDTree(other).query_ball_point(p,1e-6)
    distances=[];normal_errors=[];weight_errors=[]
    for i,ids in enumerate(matches):
        if not ids:continue
        distances.append(float(np.linalg.norm(other[ids]-p[i],axis=1).min()))
        normal_errors.append(float(np.linalg.norm(on[ids]-n[i],axis=1).min()))
        weight_errors.append(float(np.abs(ow[ids]-w[i]).sum(1).min()))
    return {'boundaryCopies':len(p),'unmatchedCopies':sum(not ids for ids in matches),
            'maxPositionDeltaM':max(distances,default=0),
            'maxNormalDelta':max(normal_errors,default=0),
            'maxWeightL1Delta':max(weight_errors,default=0)}


def neck_join_checks(parts, boundary_plane=None):
    """Check the actual bridge boundary, including nonplanar chest cuts.

    Checking only a horizontal band can miss every edge of a shaped neck base.
    Join copies must have identical normals and full joint distributions so
    their positions and shading remain continuous under arbitrary LBS poses.
    """
    positions, normals, weights, faces, roles = [], [], [], [], []
    offset = 0
    for name, role, a, f in parts:
        if role not in ('shared_body', 'shared_neck', 'race_head', 'neck_join'):
            continue
        used, inverse = np.unique(f, return_inverse=True)
        positions.append(a['POSITION'][used]); normals.append(a['NORMAL'][used])
        dense = np.zeros((len(used), 77))
        for column in range(4):
            dense[np.arange(len(used)), a['JOINTS_0'][used, column]] += a['WEIGHTS_0'][used, column]
        weights.append(dense)
        faces.append(inverse.reshape(-1, 3) + offset)
        roles.extend([role] * len(used)); offset += len(used)
    p, n, w, f = np.concatenate(positions), np.concatenate(normals), np.concatenate(weights), np.concatenate(faces)
    roles = np.asarray(roles)
    pairs = cKDTree(p).query_pairs(1e-6, output_type='ndarray')
    _, ids = connected_components(coo_matrix((np.ones(len(pairs)), (pairs[:, 0], pairs[:, 1])),
                                            shape=(len(p), len(p))).tocsr(), directed=False)
    def edge_counts(ff):
        edges = ids[np.concatenate([ff[:, [0, 1]], ff[:, [1, 2]], ff[:, [2, 0]]])]
        return Counter(tuple(sorted(e)) for e in edges if e[0] != e[1])
    bridge = f[(roles[f] == 'neck_join').all(1)]
    bridge_counts = edge_counts(bridge)
    boundary = [edge for edge, count in bridge_counts.items() if count == 1]
    if boundary_plane is not None:
        # Once clothing has a baked clearance, the lower anatomical cut ends
        # underneath a separate garment. Keep the exact head/neck seam check;
        # garment coverage is checked independently against the rendered shell.
        origin, axis, height = boundary_plane
        _, representatives = np.unique(ids, return_index=True)
        on_plane = np.abs((p[representatives] - origin) @ axis - height) < 2e-6
        boundary = [edge for edge in boundary if on_plane[list(edge)].all()]
    all_counts = edge_counts(f)
    report = {'geometricEdges': len(boundary),
              'unmatchedEdges': sum(all_counts[e] != 2 for e in boundary)}
    boundary_ids = set(i for edge in boundary for i in edge)
    selected = np.flatnonzero((roles == 'neck_join') & np.isin(ids, list(boundary_ids)))
    other = np.flatnonzero(roles != 'neck_join')
    matches = cKDTree(p[other]).query_ball_point(p[selected], 1e-6)
    distances, normal_errors, weight_errors = [], [], []
    for row, neighbours in zip(selected, matches):
        if not neighbours: continue
        nearby = other[neighbours]
        distances.append(float(np.linalg.norm(p[nearby]-p[row], axis=1).min()))
        normal_errors.append(float(np.linalg.norm(n[nearby]-n[row], axis=1).min()))
        weight_errors.append(float(np.abs(w[nearby]-w[row]).sum(1).min()))
    attributes = {'boundaryCopies': len(selected), 'unmatchedCopies': sum(not v for v in matches),
                  'maxPositionDeltaM': max(distances, default=0),
                  'maxNormalDelta': max(normal_errors, default=0),
                  'maxWeightL1Delta': max(weight_errors, default=0)}
    return report, attributes


def verify(candidate, source, template):
    d, b = ea.read_glb(candidate); sd, sb = ea.read_glb(source); td, tb = ea.read_glb(template)
    report = {'candidateSHA256': sha(candidate), 'sourceSHA256': sha(source),
              'templateSHA256': sha(template), 'errors': []}
    def require(ok, label):
        if not ok: report['errors'].append(label)
    skin, source_skin = d['skins'][0], sd['skins'][0]
    names = [d['nodes'][j]['name'] for j in skin['joints']]
    require(names == [sd['nodes'][j]['name'] for j in source_skin['joints']] and len(names) == 77,
            'joint names/order changed')
    world, source_world = ea.global_matrices(d), ea.global_matrices(sd)
    require(np.array_equal(np.array(world)[skin['joints']], np.array(source_world)[source_skin['joints']]),
            'rig rest matrices changed')
    require(np.array_equal(ea.accessor_array(d, b, skin['inverseBindMatrices']),
                          ea.accessor_array(sd, sb, source_skin['inverseBindMatrices'])), 'inverse binds changed')
    if candidate.stem.startswith('luminous_') and 'sharedBodyShape' not in d.get('asset',{}).get('extras',{}):
        require(sha(candidate) == sha(source) == sha(template), 'reference body changed')
        return report
    spec = d['asset']['extras']['sharedBodyShape']
    require(spec['templateSHA256'] == sha(template), 'template hash differs')
    require(spec['headSourceSHA256'] == sha(source), 'source hash differs')
    origin = world[skin['joints'][names.index('neck_01')]][:3, 3]
    axis = world[skin['joints'][names.index('Head')]][:3, 3]-origin
    axis /= np.linalg.norm(axis)
    parts = list(primitives(d, b))
    common, head, tail = Counter(), Counter(), Counter()
    common_uv = Counter(); expected_common_uv = Counter()
    counts = Counter()
    for name, role, a, f in parts:
        counts[role or 'head_accessory'] += len(f)
        require(np.isfinite(a['POSITION']).all(), 'nonfinite positions')
        require(np.max(np.abs(a['WEIGHTS_0'].sum(1)-1)) < 1e-5, 'weights do not sum to one')
        if role in ('shared_body', 'shared_neck', 'shared_wardrobe'):
            common.update(signatures(a, f, GEOMETRY_FIELDS))
            if role in ('shared_body', 'shared_wardrobe'):common_uv.update(signatures(a, f))
            require(role == 'shared_wardrobe' or float(((a['POSITION'][np.unique(f)]-origin)@axis).max()) < spec['lowerCutM']+5e-7,
                    'common body extends above its neck boundary')
        elif role == 'race_head':
            head.update(signatures(a, f))
            require(float(((a['POSITION'][np.unique(f)]-origin)@axis).min()) > spec['upperCutM']-5e-7,
                    'race head contains lower body geometry')
        elif role == 'race_tail':
            tail.update(signatures(a, f))
            require(candidate.stem.startswith('ssarathi_'), 'tail on non-Ssarathi body')
    expected_common, expected_head, expected_tail = Counter(), Counter(), Counter()
    for name, role, a, f in primitives(td, tb):
        if name not in ea.BODY_SURFACES: continue
        relative = a['POSITION']-origin
        travel = relative@axis
        signed = travel-spec['lowerCutM']
        if spec.get('neckBase') and spec.get('bodyCutMode') != 'neck-plane':
            radius = np.linalg.norm(relative-travel[:,None]*axis,axis=1)
            base = spec['neckBase']
            signed = np.maximum(signed, np.minimum(travel-base['startM'],base['radiusM']-radius))
        selected = (signed[f] < 0).all(1)
        if spec.get('neckBase') and name == 'wardrobe_shirt':
            selected |= (signed[f] > 0).all(1)
        expected_common.update(signatures(a, f[selected], GEOMETRY_FIELDS))
        # Only local neck triangles get a new, continuous texture atlas.
        v = a['POSITION']
        neck_uv = ((name == "body") & (((v-origin)@axis)[f].max(1) > .005) & (np.abs(v[f,:,][...,0]).max(1) < .12))
        expected_common_uv.update(signatures(a, f[selected & ~neck_uv]))
    for name, role, a, f in primitives(sd, sb):
        if name not in ea.BODY_SURFACES: continue
        selected = (((a['POSITION']-origin)@axis)[f] > spec['upperCutM']).all(1)
        expected_head.update(signatures(a, f[selected]))
        if candidate.stem.startswith('ssarathi_'):
            v = a['POSITION']
            selected = ((v[:, 0] > .30) & (v[:, 1] < .94))[f].all(1)
            expected_tail.update(signatures(a, f[selected]))
    for label, expected, actual in [('common', expected_common, common), ('head', expected_head, head), ('tail', expected_tail, tail)]:
        missing = expected-actual
        report[label+'SourceTriangles'] = sum(expected.values())
        report[label+'MissingOrChangedTriangles'] = sum(missing.values())
        require(not missing, label+' source triangles changed or lost')
    report['commonUnchangedUVTriangles'] = sum(expected_common_uv.values())
    require(not expected_common_uv-common_uv, 'common body UVs outside the neck changed')
    originals = Counter(image_payloads(sd, sb))
    require(not originals-Counter(image_payloads(d, b)), 'original race atlas changed or lost')
    if spec.get('neckBase'):
        edges, attributes = neck_join_checks(parts)
        report['joins'], report['joinAttributes'] = [edges], [attributes]
    else:
        report['joins'] = [neck_edges(parts, origin, axis, spec[key]) for key in ('lowerCutM', 'upperCutM')]
    require(all(q['unmatchedEdges'] == 0 for q in report['joins']), 'neck join has unmatched edges')
    require(all(q['unmatchedCopies'] == 0 and q['maxNormalDelta'] < 2e-6
                and q['maxWeightL1Delta'] < 2e-6 for q in report['joinAttributes']),
            'neck shading or skinning differs across joined copies')
    report['trianglesByRole'] = dict(counts)
    report['totalTriangles'] = sum(counts.values())
    return report


if __name__ == '__main__':
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('candidate', type=Path)
    ap.add_argument('--source', type=Path, required=True)
    ap.add_argument('--template', type=Path, required=True)
    ap.add_argument('--out', type=Path, required=True)
    args = ap.parse_args()
    result = verify(args.candidate, args.source, args.template)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(result, indent=2)+'\n', encoding='utf-8')
    print(json.dumps(result, indent=2))
    raise SystemExit(bool(result['errors']))
