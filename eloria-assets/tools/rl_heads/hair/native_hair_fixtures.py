"""Check hair against independently evaluated native client surfaces.

The input manifest and NPZs are ignored authoring evidence, not runtime assets.
Each case supplies exact mapped hair identity controls and native bind-to-pose
bone transforms. No static native skull is substituted for a moving case.
"""
import argparse
import copy
import hashlib
import json
from pathlib import Path
import numpy as np
import rlglb
from native_hair_clearance import NativeHeadSurface

GROOM_CASES = {
    'neutral': {}, 'length_min': {'hl_length_n': 1},
    'length_max': {'hl_length_p': 1}, 'volume_min': {'hl_volume_n': 1},
    'volume_max': {'hl_volume_p': 1},
    'length_min_volume_min': {'hl_length_n': 1, 'hl_volume_n': 1},
    'length_min_volume_max': {'hl_length_n': 1, 'hl_volume_p': 1},
    'length_max_volume_min': {'hl_length_p': 1, 'hl_volume_n': 1},
    'length_max_volume_max': {'hl_length_p': 1, 'hl_volume_p': 1},
}

def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()

def matrix(columns):
    assert np.asarray(columns).shape == (4, 3)
    out = np.eye(4)
    out[:3, :3] = np.asarray(columns[:3], float).T
    out[:3, 3] = columns[3]
    assert np.isfinite(out).all()
    return out

def identity_weights(controls):
    return {'id_' + name + ('_p' if value >= 0 else '_n'): abs(float(value))
            for name, value in controls.items() if value != 0}

def morph_positions(base, targets, weights):
    result = np.asarray(base, float).copy()
    for name, amount in weights.items():
        if amount and name in targets:
            result += targets[name] * amount
    return result

def skin_positions(points, joints, weights, names, deltas, aliases=None):
    aliases = aliases or {}
    transforms = []
    for name in names:
        key = name if name in deltas else aliases.get(name, '')
        assert key in deltas, 'No evaluated native pose for hair joint: ' + name
        transforms.append(matrix(deltas[key]))
    result = np.zeros_like(points, dtype=float)
    for slot in range(joints.shape[1]):
        for joint in np.unique(joints[:, slot]):
            mask = (joints[:, slot] == joint) & (weights[:, slot] > 0)
            if not mask.any(): continue
            transform = transforms[int(joint)]
            result[mask] += (points[mask] @ transform[:3, :3].T + transform[:3, 3]) * weights[mask, slot, None]
    return result

def load_hair(path):
    gltf, blob = rlglb.read(str(path))
    meta = gltf['asset']['extras']['rlHair']
    skin = gltf['skins'][0]
    names = [gltf['nodes'][j]['name'] for j in skin['joints']]
    parents = {child: at for at, node in enumerate(gltf['nodes']) for child in node.get('children', [])}
    aliases = {}
    for joint in skin['joints']:
        at = joint
        while at in parents and gltf['nodes'][at].get('name') != 'hair_root': at = parents[at]
        if gltf['nodes'][at].get('name') == 'hair_root': aliases[gltf['nodes'][joint]['name']] = 'Head'
    levels = []
    for lod, mesh in enumerate(gltf['meshes']):
        target_names = mesh.get('extras', {}).get('targetNames', [])
        parts = []
        for primitive in mesh['primitives']:
            attributes = primitive['attributes']
            targets = {name: rlglb.accessor(gltf, blob, target['POSITION'])
                       for name, target in zip(target_names, primitive.get('targets', []))}
            joints = rlglb.accessor(gltf, blob, attributes['JOINTS_0'], normalize=False).astype(int)
            weights = rlglb.accessor(gltf, blob, attributes['WEIGHTS_0'])
            if 'JOINTS_1' in attributes:
                joints = np.column_stack([joints, rlglb.accessor(gltf, blob, attributes['JOINTS_1'], normalize=False).astype(int)])
                weights = np.column_stack([weights, rlglb.accessor(gltf, blob, attributes['WEIGHTS_1'])])
            assert np.abs(weights.sum(1) - 1).max() < 0.001
            parts.append({'P': rlglb.accessor(gltf, blob, attributes['POSITION']), 'targets': targets,
                'T': rlglb.accessor(gltf, blob, primitive['indices'], normalize=False).astype(int).reshape(-1, 3),
                'J': joints, 'W': weights, 'names': names, 'aliases': aliases,
                'ranges': primitive.get('extras', {}).get('partVertexRanges', {})})
        levels.append(parts)
    return {'sex': meta['sex'], 'levels': levels, 'sha256': sha(path)}

class EvaluatedNativeSurface(NativeHeadSurface):
    """Keep open-cut shading normals from misclassifying distant outside points."""
    def __init__(self,P,N,T,horizontal_slice_proof=False,complete_fixture_mesh=None):
        super().__init__(P,N,T)
        self.horizontal_slice_proof=bool(horizontal_slice_proof);self._slice_bounds=None
        if self.horizontal_slice_proof:
            assert complete_fixture_mesh is not None,'Horizontal proof requires the complete verified evaluated fixture, before contact-region filtering'
            from native_slice_bounds import HorizontalSliceBounds
            self._slice_bounds=HorizontalSliceBounds(complete_fixture_mesh)

    def proven_outside(self,points):
        points=np.asarray(points);outside=np.zeros(len(points),bool);bounds=self.mesh.bounds
        if ((bounds[1]-bounds[0])>1e-6).all():
            outside=((points<bounds[0]-1e-9)|(points>bounds[1]+1e-9)).any(1)
        if self._slice_bounds is not None:outside|=self._slice_bounds.outside(points)
        return outside

    def signed(self, points):
        distance, closest, normal = super().signed(points)
        # A complete three-dimensional actor cannot enclose a point outside
        # its bounds. Retain the original sign test within that envelope and
        # for planar authoring fixtures; the geometric distance never changes.
        if self.horizontal_slice_proof:
            # An outside proof can change only a negative sign. Avoid building
            # horizontal contours for already positive probes; include -0.0
            # so the optimized path preserves the reference result bitwise.
            negative=np.flatnonzero(np.signbit(distance))
            if len(negative):
                outside=self.proven_outside(np.asarray(points)[negative])
                corrected=negative[outside]
                distance[corrected]=np.abs(distance[corrected])
        else:
            outside=self.proven_outside(points)
            distance[outside] = np.abs(distance[outside])
        return distance, closest, normal


def load_fixture(manifest_path, record, horizontal_slice_proof=False):
    stage = Path(manifest_path).parent
    points, normals, triangles, offset = [], [], [], 0
    full_points,full_triangles,full_offset=[],[],0
    for part in record['parts']:
        if part['mesh'] not in ['body', 'scalp', 'wardrobe_shirt']: continue
        path = stage / part['file']
        assert sha(path) == part['sha256'], 'Evaluated fixture changed: ' + str(path)
        with np.load(path) as data:
            P, N, T = data['P'], data['N'], data['I']
        if horizontal_slice_proof:
            full_ids,full_inverse=np.unique(T,return_inverse=True)
            full_points.append(P[full_ids]);full_triangles.append(full_inverse.reshape(-1,3)+full_offset);full_offset+=len(full_ids)
        # Lower body and arms outside this region cannot contact head hair.
        used = ((P[T, 1].max(1) > 1.05) & (np.abs(P[T, 0]).min(1) < .40))
        T = T[used]
        if not len(T): continue
        ids, inverse = np.unique(T, return_inverse=True)
        points.append(P[ids]); normals.append(N[ids]); triangles.append(inverse.reshape(-1, 3) + offset)
        offset += len(ids)
    assert points, 'No actual native collision surfaces in fixture'
    complete=None
    if horizontal_slice_proof:
        import trimesh
        complete=trimesh.Trimesh(np.vstack(full_points),np.vstack(full_triangles),process=False)
    return EvaluatedNativeSurface(np.vstack(points), np.vstack(normals), np.vstack(triangles),
        horizontal_slice_proof=horizontal_slice_proof,complete_fixture_mesh=complete)

def interior_samples(points, triangles, minimum_edge_mm=5):
    if not len(triangles): return np.empty((0, 3))
    tri = points[triangles]
    edges = np.linalg.norm(tri - np.roll(tri, 1, axis=1), axis=2)
    tri = tri[edges.max(1) * 1000 >= minimum_edge_mm]
    return np.concatenate([tri.mean(1), (tri[:, 0] + tri[:, 1]) / 2,
                           (tri[:, 1] + tri[:, 2]) / 2, (tri[:, 2] + tri[:, 0]) / 2])

def verified_fixture_signature(manifest_path, record):
    """Verify ordered physical sources and every named bind-to-pose delta."""
    parts=[]
    for part in record.get('parts',[]):
        if part['mesh'] not in ['body','scalp','wardrobe_shirt']:continue
        path=Path(manifest_path).parent/part['file']
        assert sha(path)==part['sha256'],'Evaluated fixture changed: '+str(path)
        parts.append({'mesh':part['mesh'],'sha256':part['sha256']})
    if not parts:return None,None
    payload={'version':1,'sex':record['sex'],'parts':parts,
             'rl_hair_identity_controls':record['rl_hair_identity_controls'],
             'bone_deltas':record['bone_deltas']}
    key=hashlib.sha256(json.dumps(payload,sort_keys=True,separators=(',',':'),allow_nan=False).encode()).hexdigest()
    return key,parts


def check_hair(path, manifest_path, lods=(0, 1, 2), grooms=None, minimum_mm=2,
               minimum_edge_mm=5, stop_on_first=False, case_names=None,
               cache_results=True, horizontal_slice_proof=False):
    manifest = json.loads(Path(manifest_path).read_text())
    assert manifest.get('hair_identity_policy') == 'native_fixed_skull', 'Use evaluated native fixture v2 or later; High identity targets do not belong to the fixed native skull'
    hair = load_hair(path)
    results = []
    exact_results={};source_receipts=[];cache_hits=0;queries=0
    grooms = GROOM_CASES if grooms is None else grooms
    for record in manifest['cases']:
        if record['sex'] != hair['sex'] or (case_names is not None and record['case'] not in case_names): continue
        assert not record['rl_hair_identity_controls'], 'Native skull perimeter is fixed; reject High head identity weights'
        signature,sources=verified_fixture_signature(manifest_path,record)
        source_receipts.append({'case':record['case'],'quality':record['quality'],
            'fixture_signature_sha256':signature,'parts':sources})
        native = None
        for lod in lods:
            for label, groom in grooms.items():
                weights = identity_weights(record['rl_hair_identity_controls']) | groom | {'hl_native_fit': 1}
                key=(signature,hair['sha256'],lod,
                     json.dumps(weights,sort_keys=True,separators=(',',':'),allow_nan=False),
                     float(minimum_mm),float(minimum_edge_mm),bool(horizontal_slice_proof))
                cached=exact_results.get(key) if cache_results and signature is not None else None
                if cached is not None:
                    numerical,origin=cached;result=copy.deepcopy(numerical)
                    result.update(case=record['case'],quality=record['quality'],lod=lod,groom=label)
                    result['result_cache_reuse']={'reason':'Identical verified ordered fixture hashes, complete bone deltas, hair SHA, effective shape weights and probe thresholds',
                        'fixture_signature_sha256':signature,**origin}
                    cache_hits+=1;results.append(result)
                    print(json.dumps({k:v for k,v in result.items() if k!='worst'}),flush=True)
                    violations=result['violations']
                    if violations and stop_on_first:break
                    continue
                if native is None:
                    native=load_fixture(manifest_path,record,horizontal_slice_proof=True) if horizontal_slice_proof else load_fixture(manifest_path,record)
                queries+=1
                minimum = float('inf'); violations = 0; samples = 0; worst = None
                for part in hair['levels'][lod]:
                    points = morph_positions(part['P'], part['targets'], weights)
                    points = skin_positions(points, part['J'], part['W'], part['names'], record['bone_deltas'], part['aliases'])
                    probes = np.vstack([points, interior_samples(points, part['T'], minimum_edge_mm)])
                    probes = np.unique(probes, axis=0)
                    distances, closest, normals = native.signed(probes)
                    bad = distances * 1000 < minimum_mm - .00001
                    at = int(distances.argmin())
                    if distances[at] * 1000 < minimum:
                        minimum = float(distances[at] * 1000)
                        worst = {'point': probes[at].tolist(), 'closest': closest[at].tolist(), 'normal': normals[at].tolist()}
                    violations += int(bad.sum()); samples += len(probes)
                result = {'case': record['case'], 'quality': record['quality'], 'lod': lod,
                    'groom': label, 'minimum_clearance_mm': minimum, 'violations': violations,
                    'samples': samples, 'worst': worst}
                if cache_results and signature is not None:
                    numerical={k:copy.deepcopy(v) for k,v in result.items() if k not in ['case','quality','lod','groom']}
                    exact_results[key]=(numerical,{'from_case':record['case'],'from_quality':record['quality'],'from_groom':label})
                results.append(result)
                print(json.dumps({k: v for k, v in result.items() if k != 'worst'}), flush=True)
                if violations and stop_on_first: break
            if violations and stop_on_first: break
        if violations and stop_on_first: break
    assert results, 'No matching evaluated fixture cases'
    return {'hair_sha256': hair['sha256'], 'manifest_sha256': sha(manifest_path),
        'native_fit_weight': 1,
        'horizontal_slice_proof':bool(horizontal_slice_proof),
        'minimum_clearance_mm': minimum_mm, 'triangle_sample_minimum_edge_mm': minimum_edge_mm,
        'grooms': list(grooms), 'cases': results,
        'result_cache':{'enabled':bool(cache_results),'reused_cases':cache_hits,'evaluated_queries':queries,
            'requested_results_emitted':len(results),'fixture_sources':source_receipts},
        'failures': sum(r['violations'] > 0 for r in results),
        'complete_requested_scan': not (stop_on_first and results[-1]['violations'] > 0)}

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('hair'); parser.add_argument('--manifest', required=True)
    parser.add_argument('--out', required=True); parser.add_argument('--lods', default='0,1,2')
    parser.add_argument('--neutral-groom-only', action='store_true')
    parser.add_argument('--cases'); parser.add_argument('--stop-on-first', action='store_true')
    parser.add_argument('--no-result-cache', action='store_true',help='Evaluate duplicate cases through the full reference path')
    parser.add_argument('--horizontal-slice-proof',action='store_true',help='Opt into conservative outside proof from each complete evaluated fixture')
    args = parser.parse_args()
    result = check_hair(args.hair, args.manifest, tuple(map(int, args.lods.split(','))),
        {'neutral': {}} if args.neutral_groom_only else None,
        stop_on_first=args.stop_on_first, case_names=args.cases.split(',') if args.cases else None,
        cache_results=not args.no_result_cache,horizontal_slice_proof=args.horizontal_slice_proof)
    Path(args.out).write_text(json.dumps(result, indent=2) + '\n')
    raise SystemExit(int(result['failures'] > 0))

if __name__ == '__main__': main()
