"""Fit moustache and circle-beard variants by trimming an imported attached beard.

Reuses the approved short-beard foundation's painted UVs, skin, identity and
expression deltas. This is a source-mesh processor, not a beard generator.
Raw sources are immutable; use a fresh ignored output directory for each run.
"""
import argparse
import copy
import hashlib
import json
from pathlib import Path

import numpy as np
import trimesh

import assemble
import headref
import rlglb


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def smoothstep(x):
    x = np.clip(x, 0, 1)
    return x * x * (3 - 2 * x)


def field(points, centre, style):
    q = points - centre
    lon = np.degrees(np.arctan2(q[:, 0], q[:, 2]))
    lat = np.degrees(np.arctan2(q[:, 1], np.linalg.norm(q[:, [0, 2]], axis=1)))
    side = (26.0 - np.abs(lon)) * .0025
    if style == 'moustache':
        bottom = np.interp(np.abs(lon), [0, 14, 22, 26], [-.5, -2.5, -7, -9])
    else:
        bottom = np.interp(np.abs(lon), [0, 12, 20, 26], [-46, -44, -36, -20])
    return np.minimum(side, (lat - bottom) * .0025)


def clipped_rows(rows, distance):
    """Clip existing triangles, interpolating every imported vertex channel."""
    result = []
    for index, point in enumerate(rows):
        following = rows[(index + 1) % len(rows)]
        a, b = distance[index], distance[(index + 1) % len(rows)]
        if a >= 0:
            result.append(point)
        if (a < 0) != (b < 0):
            result.append(point + (following - point) * (a / (a - b)))
    return result


def process(source, metadata, texture, head_path, output, centre, style):
    assert source.resolve() != output.resolve()
    g, blob = rlglb.read(source)
    old, _ = rlglb.read(metadata)
    hg, hb = rlglb.read(head_path)
    writer = assemble.Writer('Rabbit Lands imported skin-attached ' + style)
    material = writer.material('rl_beard', [1, 1, 1, 1], cutoff=.35, double=True,
        extras={'texture': 'short_beard.png', 'referenceSurface': True,
                'softHairline': True, 'featheredRoots': True,
                'skinAttachedFoundation': True, 'importedSourceStyle': 'short_beard'})
    writer.embed_texture(material, str(texture))
    report = {'style': style, 'source_sha256': sha(source),
              'prior_style_sha256': sha(metadata), 'texture_sha256': sha(texture),
              'tool_sha256': sha(__file__), 'region_centre': centre.tolist(),
              'head_sha256': sha(head_path), 'edge_feather_mm': 3, 'root_offset_mm': .4, 'lods': {},
              'central_moustache_coverage_gain': 1.65 if style == 'moustache' else 1.0,
              'source_morphs_skin_and_uvs_interpolated': True,
              'canonical_surface_bind_recalculated_at_new_feather_roots': True,
              'new_free_floating_cards': False, 'head_body_skeleton_modified': False}
    for lod, mesh in enumerate(g['meshes']):
        primitive = mesh['primitives'][0]
        attrs = {k: rlglb.accessor(g, blob, v) for k, v in primitive['attributes'].items()}
        triangles = rlglb.accessor(g, blob, primitive['indices']).astype(int).reshape(-1, 3)
        # Keep the imported continuous foundation. Old detached strand cards
        # deliberately do not reappear in these dense oral variants.
        triangles = triangles[(attrs['TEXCOORD_0'][triangles, 1] < .6505).all(1)]
        names = mesh['extras']['targetNames']
        deltas = [rlglb.accessor(g, blob, t['POSITION']) for t in primitive['targets']]
        assert len(deltas) == len(names) == 75
        joints = attrs['JOINTS_0'].astype(int)
        joint_count = int(joints.max()) + 1
        dense = np.zeros((len(joints), joint_count))
        for slot in range(4):
            np.add.at(dense, (np.arange(len(joints)), joints[:, slot]), attrs['WEIGHTS_0'][:, slot])
        # Packed channels allow boundary interpolation without losing skin
        # ownership, UV seams, or any of the live expression/corrective shapes.
        packed = np.concatenate([attrs['POSITION'], attrs['NORMAL'], attrs['TEXCOORD_0'],
                                 attrs['COLOR_0'], dense, *deltas], axis=1)
        points, faces = [], []
        for tri in triangles:
            a, b, c = packed[tri]
            # One local subdivision gives even LOD2 enough samples to feather
            # the narrow moustache. It adds no independent source geometry.
            ab, bc, ca = (a+b)/2, (b+c)/2, (c+a)/2
            for small in [(a, ab, ca), (ab, b, bc), (ca, bc, c), (ab, bc, ca)]:
                rows = np.asarray(small)
                poly = clipped_rows(rows, field(rows[:, :3], centre, style))
                start = len(points)
                points.extend(poly)
                for index in range(1, len(poly)-1):
                    faces.append([start, start+index, start+index+1])
        data = np.asarray(points, dtype=np.float32)
        triangles = np.asarray(faces, int)
        # Weld only vertices whose complete serialized channels match. UV or
        # morph discontinuities stay split; redundant clipped corners vanish.
        _, first, inverse = np.unique(data, axis=0, return_index=True, return_inverse=True)
        data = data[first]
        triangles = inverse[triangles]
        pos, norm, uv, colour = data[:, :3], data[:, 3:6], data[:, 6:8], data[:, 8:12]
        density = data[:, 12:12+joint_count]
        delta_start = 12+joint_count
        deltas = [data[:, delta_start+k*3:delta_start+(k+1)*3] for k in range(len(names))]
        distance = field(pos, centre, style)
        source_coverage = colour[:, 0]*2
        if style == 'moustache':
            central = smoothstep((.028-np.abs(pos[:, 0]))/.012)
            source_coverage = np.minimum(1, source_coverage*(1+.65*central))
        colour[:, 0] = .5*np.minimum(source_coverage, smoothstep(distance / .003))
        # A trimmed opaque cap edge was previously an interior point standing
        # 3.25mm off skin. Rebind the new feather boundary onto the head instead
        # of merely making that floating interior point transparent.
        hm = hg['meshes'][lod]
        hp = hm['primitives'][0]
        hpos = rlglb.accessor(hg, hb, hp['attributes']['POSITION'])
        htri = rlglb.accessor(hg, hb, hp['indices']).astype(int).reshape(-1, 3)
        assert hm['extras']['targetNames'] == names
        hdelta = [rlglb.accessor(hg, hb, x['POSITION']) for x in hp['targets']]
        surface = trimesh.Trimesh(hpos, htri, process=False)
        cp, _, ti = trimesh.proximity.closest_point(surface, pos)
        tv = htri[ti]
        bary = headref.barycentric(cp, hpos[tv[:, 0]], hpos[tv[:, 1]], hpos[tv[:, 2]])
        _, weld = np.unique(np.round(hpos, 6), axis=0, return_inverse=True)
        hn = headref.vertex_normals(hpos, htri, weld)
        norm = headref.unit((hn[tv] * bary[:, :, None]).sum(1))
        thickness = .0004 + .00285 * np.minimum(colour[:, 0]*2, 1)**3
        pos = cp + norm * thickness[:, None]
        deltas = []
        for hd in hdelta:
            morphed_normal = headref.vertex_normals(hpos+hd, htri, weld)
            mn = headref.unit((morphed_normal[tv] * bary[:, :, None]).sum(1))
            deltas.append((hd[tv] * bary[:, :, None]).sum(1)
                          + (mn-norm)*thickness[:, None])
        hj = rlglb.accessor(hg, hb, hp['attributes']['JOINTS_0']).astype(int)
        hw = rlglb.accessor(hg, hb, hp['attributes']['WEIGHTS_0'])
        density = np.zeros((len(pos), joint_count))
        for corner in range(3):
            for slot in range(4):
                np.add.at(density, (np.arange(len(pos)), hj[tv[:, corner], slot]),
                          bary[:, corner]*hw[tv[:, corner], slot])
        j, w = assemble.top4(density)
        assert np.isfinite(data).all() and np.allclose(w.sum(1), 1, atol=1e-6)
        pr = writer.primitive(pos.astype('f4'), norm.astype('f4'), uv.astype('f4'),
            triangles, np.rint(np.clip(colour, 0, 1)*255).astype('u1'),
            j.astype('u1'), w.astype('f4'), material, [(d, None) for d in deltas])
        writer.mesh('beard_lod%d' % lod, [pr], names)
        report['lods'][str(lod)] = {'vertices': len(pos), 'triangles': len(triangles),
            'bounds': [pos.min(0).tolist(), pos.max(0).tolist()],
            'identity_shapes': sum(n.startswith('id_') for n in names),
            'expression_corrective_shapes': sum(n.startswith('ex_') for n in names),
            'opaque_foundation_vertices': int((colour[:, 0] > .49).sum())}
    writer.g.g['nodes'] = copy.deepcopy(g['nodes'])
    writer.g.g['scenes'] = copy.deepcopy(g['scenes'])
    skin = copy.deepcopy(g['skins'][0])
    skin['inverseBindMatrices'] = writer.g.accessor(rlglb.accessor(g, blob,
        skin['inverseBindMatrices']).astype('f4'), 'MAT4')
    writer.g.g['skins'] = [skin]
    writer.g.g['asset']['extras'] = copy.deepcopy(old['asset']['extras'])
    info = writer.g.g['asset']['extras']['rlBeard']
    info.update(name=style, style=style, skinAttachedFoundation=True,
        importedFoundationSourceSHA256=sha(source),
        tris={'lod'+key: value['triangles'] for key, value in report['lods'].items()})
    info['texture'] = {'file': 'short_beard.png', 'columns': 1, 'cards': [], 'shell': 0}
    output.parent.mkdir(parents=True, exist_ok=True)
    assert not output.exists(), 'Use a new versioned stage.'
    writer.save(str(output))
    report['output_sha256'] = sha(output)
    output.with_suffix('.attachment.json').write_text(json.dumps(report, indent=2)+'\n')
    print(json.dumps({'style': style, 'output': str(output), 'sha256': sha(output),
                      'lods': report['lods']}), flush=True)


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    for name in ['source', 'metadata_dir', 'texture', 'head', 'out']:
        ap.add_argument('--'+name.replace('_', '-'), required=True)
    ap.add_argument('--frame', type=float, nargs=3, required=True,
                    help='Measured canonical beard centre x y z; record its source/profile.')
    args = ap.parse_args()
    hg, hb = rlglb.read(args.head)
    # This is the existing beard frame, measured from canonical lip vertices.
    # Its centre is recorded for reproducibility; no authoring head is rebuilt.
    extras = hg['asset']['extras']['rlHead']
    centre = np.asarray(args.frame)
    # Explicit currently installed canonical frame. A changed base head needs
    # a fresh frame/attachment qualification rather than silently adapting it.
    assert len(extras['controls']) == 23 and np.isfinite(centre).all()
    for style in ['moustache', 'goatee']:
        process(Path(args.source), Path(args.metadata_dir)/(style+'.glb'),
                Path(args.texture), Path(args.head), Path(args.out)/(style+'.glb'), centre, style)


if __name__ == '__main__':
    main()
