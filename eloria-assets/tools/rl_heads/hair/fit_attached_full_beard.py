"""Fit the preserved elder beard volume over a skin-attached foundation.

First build --foundation with fit_attached_beard.py from the same source and
texture. This stage keeps the imported beard's hanging lower silhouette while
replacing its floating oral sheet and upper roots with that anatomical surface.
Inputs are immutable; reports and outputs must use a separate ignored stage.
"""
import argparse
import copy
import hashlib
import json
from pathlib import Path

import numpy as np
import trimesh
from PIL import Image
from scipy.spatial import ConvexHull

import assemble
import headref
import rlglb


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def attrs(g, b, p):
    return {k: rlglb.accessor(g, b, v) for k, v in p['attributes'].items()}


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    for key in ('source', 'foundation', 'texture', 'out'):
        ap.add_argument('--' + key, required=True)
    a = ap.parse_args()
    source, foundation, dest = map(Path, (a.source, a.foundation, a.out))
    assert dest.resolve() not in (source.resolve(), foundation.resolve())
    dest.parent.mkdir(parents=True, exist_ok=True)
    # This unused strand-sheet panel supplies underlay detail. Seal only its
    # interior alpha pinholes; foundation edge feathering comes from vertex
    # coverage. Reference islands and retained whisker panels remain untouched.
    atlas = np.array(Image.open(a.texture).convert('RGBA'))
    height, width = atlas.shape[:2]
    atlas[int(.72 * height):int(.95 * height), int(.77 * width):int(.99 * width), 3] = 255
    texture_out = dest.with_suffix('.png')
    assert texture_out.resolve() != Path(a.texture).resolve()
    Image.fromarray(atlas).save(texture_out)
    sg, sb = rlglb.read(str(source))
    fg, fb = rlglb.read(str(foundation))
    head = headref.Head('male')
    hg, hb = head.gltf, head.blob
    writer = assemble.Writer('Rabbit Lands attached elder full beard')
    mat = writer.material('rl_beard', [1, 1, 1, 1], cutoff=.35, double=True,
                          extras={'texture': 'full_beard.png', 'referenceSurface': True,
                                  'softHairline': True, 'featheredRoots': True,
                                  'skinAttachedFoundation': True})
    writer.embed_texture(mat, str(texture_out))
    report = {'source_sha256': digest(source), 'foundation_sha256': digest(foundation),
              'texture_sha256': digest(a.texture), 'head_sha256': digest(head.glb_path),
              'tool_sha256': digest(__file__), 'lods': {},
              'method': 'Retained lower reference mass over continuous attached foundation; oral source sheet removed'}
    for lod in range(3):
        fm = fg['meshes'][lod]
        fp = fm['primitives'][0]
        fa = attrs(fg, fb, fp)
        ft = rlglb.accessor(fg, fb, fp['indices']).astype(int).reshape(-1, 3)
        names = fm['extras']['targetNames']
        fd = [rlglb.accessor(fg, fb, t['POSITION']) for t in fp['targets']]
        # The Meshy reference has many small UV islands. Projecting one island
        # independently onto each underlay triangle creates gray tonal facets.
        # Reuse the atlas's continuous opaque strand patch for this underlay;
        # the hanging reference volume keeps its original painted UVs below.
        foundation_vertices = fa['COLOR_0'][:, 0] < .6
        face = fa['POSITION'][foundation_vertices]
        horizontal = np.arctan2(face[:, 0], np.maximum(face[:, 2] + .035, .001))
        fa['TEXCOORD_0'][foundation_vertices, 0] = .78 + .20 * np.clip(horizontal / 2.2 + .5, 0, 1)
        fa['TEXCOORD_0'][foundation_vertices, 1] = .73 + .20 * np.clip((1.61 - face[:, 1]) / .14, 0, 1)
        sm = sg['meshes'][lod]
        sp = sm['primitives'][0]
        sa = attrs(sg, sb, sp)
        st = rlglb.accessor(sg, sb, sp['indices']).astype(int).reshape(-1, 3)
        # The reference occupies the top 65% of its preserved texture atlas.
        st = st[(sa['TEXCOORD_0'][st, 1] < .6505).all(1)]
        # No old moustache/oral backing survives: these triangles cross the
        # opening under jaw morphs. The foundation owns the entire mouth rim.
        st = st[(sa['POSITION'][st, 1] < 1.567).all(1)]
        used, inv = np.unique(st, return_inverse=True)
        st = inv.reshape(-1, 3)
        old = sa['POSITION'][used]
        hm = next(m for m in hg['meshes'] if m['name'] == f'rl_head_lod{lod}')
        assert names == sm['extras']['targetNames'] == hm['extras']['targetNames']
        hp = hm['primitives'][0]
        ha = attrs(hg, hb, hp)
        ht = rlglb.accessor(hg, hb, hp['indices']).astype(int).reshape(-1, 3)
        hP = ha['POSITION']
        # Hanging hair is rooted at the chin, never at the nearer throat.
        anchor = old.copy()
        anchor[:, 1] = np.maximum(anchor[:, 1], 1.545)
        skin = trimesh.Trimesh(hP, ht, process=False)
        cp, _, ti = trimesh.proximity.closest_point(skin, anchor)
        tv = ht[ti]
        bc = headref.barycentric(cp, hP[tv[:, 0]], hP[tv[:, 1]], hP[tv[:, 2]])
        _, weld = np.unique(np.round(hP, 6), axis=0, return_inverse=True)
        hN = headref.vertex_normals(hP, ht, weld)
        n = headref.unit((hN[tv] * bc[:, :, None]).sum(1))
        retain = assemble.smoothstep((1.565 - old[:, 1]) / .055)
        p = cp + n * .0022 + (old - cp) * retain[:, None]
        st = st[np.linalg.norm(headref.tri_normals(p, st), axis=1) > 1e-12]
        # Fade the reference's newly cut upper boundary into the underlay;
        # no opaque polygon edge is left around the face or lower lip.
        coverage = assemble.smoothstep((1.565 - old[:, 1]) / .014)
        col = sa['COLOR_0'][used].copy()
        col[:, 0] = coverage * .5
        col[:, 1] = .65
        col[:, 2] = .93
        dense = np.zeros((len(p), len(head.skin_joints)))
        for corner in range(3):
            for slot in range(4):
                np.add.at(dense, (np.arange(len(p)), ha['JOINTS_0'][tv[:, corner], slot].astype(int)),
                          bc[:, corner] * ha['WEIGHTS_0'][tv[:, corner], slot])
        j, w = assemble.top4(dense)
        deltas = []
        for target in hp['targets']:
            hd = rlglb.accessor(hg, hb, target['POSITION'])
            hn = headref.vertex_normals(hP + hd, ht, weld)
            nm = headref.unit((hn[tv] * bc[:, :, None]).sum(1))
            deltas.append((hd[tv] * bc[:, :, None]).sum(1) + (nm - n) * .0022)
        # Preserve UV seams while sharing normals at coincident reference points.
        _, pweld = np.unique(np.round(p, 6), axis=0, return_inverse=True)
        normal = headref.vertex_normals(p, st, pweld)
        normal[np.linalg.norm(normal, axis=1) < .5] = n[np.linalg.norm(normal, axis=1) < .5]
        # The imported lower LODs omit strips of the hanging reference shell.
        # A small inset envelope closes those interior views without replacing
        # the painted outer locks or their irregular silhouette.
        hull = ConvexHull(p)
        bt = hull.simplices.copy()
        flip = (headref.tri_normals(p, bt) * hull.equations[:, :3]).sum(1) < 0
        bt[flip] = bt[flip][:, [0, 2, 1]]
        bv, bi = np.unique(bt, return_inverse=True)
        bt = bi.reshape(-1, 3)
        centre = p[bv].mean(0)
        bp = centre + (p[bv] - centre) * .95
        bn = headref.vertex_normals(bp, bt)
        buv = np.column_stack((.88 + .08 * np.clip(bp[:, 0] / .08, -1, 1),
                               .73 + .20 * np.clip((1.61 - bp[:, 1]) / .14, 0, 1)))
        bcov = assemble.smoothstep((1.562 - bp[:, 1]) / .006)
        bcol = np.ones((len(bp), 4));bcol[:, 0] = bcov * .5;bcol[:, 1] = .65;bcol[:, 2] = .93
        backing_tris = len(bt)
        mass_count = len(p)
        p = np.vstack((p, bp));normal = np.vstack((normal, bn));j = np.vstack((j, j[bv]));w = np.vstack((w, w[bv]));col = np.vstack((col, bcol))
        mass_uv = np.vstack((sa['TEXCOORD_0'][used], buv))
        st = np.vstack((st, bt + mass_count))
        deltas = [np.vstack((d, d[bv].mean(0) + (d[bv] - d[bv].mean(0)) * .95)) for d in deltas]
        combined = {
            'POSITION': np.vstack((fa['POSITION'], p)),
            'NORMAL': np.vstack((fa['NORMAL'], normal)),
            'TEXCOORD_0': np.vstack((fa['TEXCOORD_0'], mass_uv)),
            'JOINTS_0': np.vstack((fa['JOINTS_0'], j)),
            'WEIGHTS_0': np.vstack((fa['WEIGHTS_0'], w)),
            'COLOR_0': np.vstack((fa['COLOR_0'], col)),
        }
        t = np.vstack((ft, st + len(fa['POSITION'])))
        ds = [np.vstack((x, y)) for x, y in zip(fd, deltas)]
        primitive = writer.primitive(combined['POSITION'].astype('f4'), combined['NORMAL'].astype('f4'),
                                     combined['TEXCOORD_0'].astype('f4'), t,
                                     np.rint(combined['COLOR_0'] * 255).astype('u1'),
                                     combined['JOINTS_0'].astype('u1'), combined['WEIGHTS_0'].astype('f4'),
                                     mat, [(x, None) for x in ds])
        writer.mesh(f'beard_lod{lod}', [primitive], names)
        report['lods'][f'lod{lod}'] = {
            'tris': len(t), 'foundation_tris': len(ft), 'retained_long_mass_tris': len(st) - backing_tris,
            'inset_backing_tris': backing_tris,
            'reference_bottom_y_m': float(old[:, 1].min()), 'repaired_bottom_y_m': float(p[:, 1].min()),
            'mouth_sheet_triangles': 0, 'morph_count': len(names),
        }
        print('ATTACHED_FULL_BEARD', lod, report['lods'][f'lod{lod}'], flush=True)
    writer.g.g['nodes'] = copy.deepcopy(fg['nodes'])
    writer.g.g['scenes'] = copy.deepcopy(fg['scenes'])
    skin = copy.deepcopy(fg['skins'][0])
    skin['inverseBindMatrices'] = writer.g.accessor(rlglb.accessor(fg, fb, skin['inverseBindMatrices']).astype('f4'), 'MAT4')
    writer.g.g['skins'] = [skin]
    writer.g.g['asset']['extras'] = copy.deepcopy(sg['asset']['extras'])
    info = writer.g.g['asset']['extras']['rlBeard']
    info['tris'] = {k: v['tris'] for k, v in report['lods'].items()}
    info['skinAttachedFoundation'] = True
    info['referenceLongMassRetained'] = True
    writer.save(str(dest))
    report['output_sha256'] = digest(dest)
    report['output_texture_sha256'] = digest(texture_out)
    dest.with_suffix('.attachment.json').write_text(json.dumps(report, indent=2))
    print('ATTACHED_FULL_BEARD_WRITTEN', dest, flush=True)


if __name__ == '__main__':
    main()
