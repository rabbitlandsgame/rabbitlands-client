"""Inherit a fitted Native corrective at ribbon roots without changing High data.

No fitting, paid generation, upload or runtime registration is performed here.
The caller independently qualifies the fitted core and any remaining free tips.
"""
import argparse
import copy
import hashlib
import json
from pathlib import Path
import shutil
import numpy as np
from scipy.sparse import coo_matrix
from scipy.sparse.csgraph import connected_components
import assemble
import glbwriter
import rlglb
from attach_surface_details import root_columns

SHAPE = 'hl_native_fit'


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def native_digest(document, blob):
    """Canonical decoded POSITION/NORMAL array digest, including signed zeros."""
    digest = hashlib.sha256()
    for mesh in document['meshes']:
        names = mesh['extras']['targetNames']
        assert names.count(SHAPE) == 1
        at = names.index(SHAPE)
        for pi, primitive in enumerate(mesh['primitives']):
            count = document['accessors'][primitive['attributes']['POSITION']]['count']
            digest.update(json.dumps([mesh['name'], pi], separators=(',', ':')).encode())
            for name in ['POSITION', 'NORMAL']:
                target = primitive['targets'][at]
                array = rlglb.accessor(document, blob, target[name], normalize=False) if name in target else np.zeros((count, 3))
                assert array.shape == (count, 3) and np.isfinite(array).all()
                digest.update(name.encode())
                digest.update(np.asarray(array.shape, dtype='<i8').tobytes())
                digest.update(np.ascontiguousarray(array, dtype='<f4').tobytes())
    return digest.hexdigest()


def inherit(source, output, max_root_distance_mm=.5, max_delta_mm=14):
    source, output = Path(source), Path(output)
    assert source.name == output.name and source.resolve() != output.resolve()
    assert not output.exists() and 0 < max_root_distance_mm <= 5 and 0 < max_delta_mm <= 14
    g, blob = rlglb.read(str(source))
    assert len(g['buffers']) == 1 and 'uri' not in g['buffers'][0]
    metadata = g['asset']['extras']['rlHair']['nativeFit']
    assert metadata['shape'] == SHAPE
    writer = glbwriter.GLB()
    writer.g, writer.blob = copy.deepcopy(g), bytearray(blob)
    records = []
    for mi, mesh in enumerate(g['meshes']):
        names = mesh['extras']['targetNames']
        assert names.count(SHAPE) == 1
        at = names.index(SHAPE)
        parent = mesh['primitives'][0]
        assert g['materials'][parent['material']]['name'] == 'rl_hair_clump'
        P = rlglb.accessor(g, blob, parent['attributes']['POSITION'])
        C = rlglb.accessor(g, blob, parent['attributes']['COLOR_0'])
        T = rlglb.accessor(g, blob, parent['indices'], normalize=False).astype(int).reshape(-1, 3)
        cs, ce = parent['extras']['partVertexRanges']['shell']
        eligible = ~((T >= cs) & (T < ce)).any(1) & (C[T, 0] >= .55).all(1)
        eligible &= np.linalg.norm(np.cross(P[T[:, 1]] - P[T[:, 0]], P[T[:, 2]] - P[T[:, 0]]), axis=1) > 1e-14
        faces = T[eligible]
        assert len(faces)
        parent_delta = rlglb.accessor(g, blob, parent['targets'][at]['POSITION'])
        for pi, primitive in enumerate(mesh['primitives'][1:], 1):
            assert g['materials'][primitive['material']]['name'] == 'rl_hair_card'
            F = rlglb.accessor(g, blob, primitive['attributes']['POSITION'])
            N = rlglb.accessor(g, blob, primitive['attributes']['NORMAL'])
            FC = rlglb.accessor(g, blob, primitive['attributes']['COLOR_0'])
            UV = rlglb.accessor(g, blob, primitive['attributes']['TEXCOORD_0'])
            FT = rlglb.accessor(g, blob, primitive['indices'], normalize=False).astype(int).reshape(-1, 3)
            assert len(np.unique(FT)) == len(F), 'Compact unindexed detail rows before inheriting roots'
            edges = FT[:, [0, 1, 1, 2, 2, 0]].reshape(-1, 2)
            _, labels = connected_components(coo_matrix((np.ones(len(edges)), (edges[:, 0], edges[:, 1])),
                                                         shape=(len(F), len(F))).tocsr(), directed=False)
            D = np.zeros_like(F)
            bindings = []
            for label in np.unique(labels):
                group = np.flatnonzero(labels == label)
                along = FC[group, 1]
                roots = group[along <= along.min() + .01]
                assert len(roots) == 2, 'Expected two-column ribbons'
                assert abs(UV[roots[0], 0] - UV[roots[1], 0]) > 1e-8
                columns = np.argmin(abs(UV[group, 0, None] - UV[roots, 0][None]), axis=1)
                local_roots = np.array([int(np.flatnonzero(group == root)[0]) for root in roots])
                adjusted, inherited, proof = root_columns(P, faces, {SHAPE: parent_delta}, F[group],
                                                          {SHAPE: np.zeros((len(group), 3))}, local_roots, columns)
                assert max(proof['original_root_distance_mm']) <= max_root_distance_mm
                # High positions remain untouched. Its existing source offset is
                # absorbed only into Native so both roots meet the fitted core.
                D[group] = inherited[SHAPE] + adjusted - F[group]
                tv = np.asarray(proof['parent_triangles'], int)
                for attribute in ['JOINTS_0', 'WEIGHTS_0']:
                    assert (attribute in parent['attributes']) == (attribute in primitive['attributes'])
                    if attribute in parent['attributes']:
                        pa = rlglb.accessor(g, blob, parent['attributes'][attribute], normalize=False)
                        fa = rlglb.accessor(g, blob, primitive['attributes'][attribute], normalize=False)
                        for column, root in enumerate(roots):
                            np.testing.assert_array_equal(pa[tv[column]], np.repeat(fa[root][None], 3, axis=0))
                bindings.append({'root_indices': roots.tolist(), **proof})
            assert np.isfinite(D).all() and np.linalg.norm(D, axis=1).max() * 1000 <= max_delta_mm
            _, weld = np.unique(np.round(F / 1e-6), axis=0, return_inverse=True)
            normal = assemble.morph_normals(F, FT, N, D, weld)
            target = {'POSITION': writer.sparse_vec3(D, eps=0)}
            if np.any(normal):
                target['NORMAL'] = writer.sparse_vec3(normal, eps=0)
            writer.g['meshes'][mi]['primitives'][pi]['targets'][at] = target
            records.append({'mesh': mesh['name'], 'primitive': pi, 'bindings': bindings,
                            'maximum_delta_mm': float(np.linalg.norm(D, axis=1).max() * 1000),
                            'high_attributes_and_all_other_shapes_exact': True})
    assert records, 'No ribbon detail streams found'
    native = writer.g['asset']['extras']['rlHair']['nativeFit']
    previous_digest = native['deltaSHA256']
    native['deltaSHA256'] = native_digest(writer.g, writer.blob)
    native['detailRootSourceDeltaSHA256'] = previous_digest
    native['detailRootSourceSHA256'] = sha(source)
    native['detailRootToolSHA256'] = sha(__file__)
    output.parent.mkdir(parents=True, exist_ok=True)
    atlas = source.with_suffix('.png')
    if atlas.exists():
        assert not output.with_suffix('.png').exists()
    writer.g.setdefault('skins', [])
    writer.g.setdefault('materials', [])
    writer.save(str(output))
    if atlas.exists():
        shutil.copy2(atlas, output.with_suffix('.png'))
    actual, packed = rlglb.read(str(output))
    assert packed[:len(blob)] == blob
    for before, after in zip(g['meshes'], actual['meshes']):
        assert before['extras'] == after['extras'] and before.get('weights') == after.get('weights')
        at = before['extras']['targetNames'].index(SHAPE)
        for pi, (p, q) in enumerate(zip(before['primitives'], after['primitives'])):
            assert p['attributes'] == q['attributes'] and p['indices'] == q['indices']
            for ti, (old, new) in enumerate(zip(p['targets'], q['targets'])):
                if pi == 0 or ti != at:
                    assert old == new
    assert actual['nodes'] == g['nodes'] and actual.get('skins') == g.get('skins')
    assert native_digest(actual, packed) == native['deltaSHA256']
    maximum_root_error_mm = 0.
    for record in records:
        mesh = next(m for m in actual['meshes'] if m['name'] == record['mesh'])
        at = mesh['extras']['targetNames'].index(SHAPE)
        parent, primitive = mesh['primitives'][0], mesh['primitives'][record['primitive']]
        P = rlglb.accessor(actual, packed, parent['attributes']['POSITION'])
        PD = rlglb.accessor(actual, packed, parent['targets'][at]['POSITION'])
        F = rlglb.accessor(actual, packed, primitive['attributes']['POSITION'])
        FD = rlglb.accessor(actual, packed, primitive['targets'][at]['POSITION'])
        for binding in record['bindings']:
            tv = np.asarray(binding['parent_triangles'], int)
            bc = np.asarray(binding['barycentric'])
            expected = ((P + PD)[tv] * bc[:, :, None]).sum(1)
            observed = (F + FD)[binding['root_indices']]
            maximum_root_error_mm = max(maximum_root_error_mm, float(np.linalg.norm(expected - observed, axis=1).max() * 1000))
    assert maximum_root_error_mm <= .001, 'Encoded Native roots differ from their exact parents'
    return {'source_sha256': sha(source), 'output_sha256': sha(output), 'records': records,
            'native_position_normal_digest': native['deltaSHA256'],
            'maximum_encoded_native_root_error_mm': maximum_root_error_mm,
            'all_high_attributes_shapes_indices_skin_scene_exact': True,
            'core_native_corrective_exact': True, 'authoring_source_preserved': True,
            'qualified': False}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source', required=True)
    parser.add_argument('--out', required=True)
    parser.add_argument('--report', required=True, help='Ignored/private root binding receipt')
    args = parser.parse_args()
    report = inherit(args.source, args.out)
    Path(args.report).write_text(json.dumps(report, indent=2) + '\n')
    print('NATIVE_DETAIL_ROOTS_INHERITED', report['output_sha256'])
