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
from scipy.spatial import ConvexHull, cKDTree

import assemble
import headref
import rlglb


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def attrs(g, b, p):
    return {k: rlglb.accessor(g, b, v) for k, v in p['attributes'].items()}


def clear_oral_faces(points, triangles, polygon, planes, clearance=.0012):
    """Exact convex separating-axis test in the canonical mouth plane.

    The source sheet may approach the moustache and mouth corners, but no
    retained triangle may span the lip aperture. Both triangle and lip-hull
    edge axes are needed; testing vertices alone misses crossing triangles.
    """
    q = points[triangles, :2]
    signed = q @ planes[:, :2].T + planes[:, 2]
    separated = (signed.min(axis=1) > clearance).any(axis=1)
    candidates = np.flatnonzero(~separated)
    if len(candidates):
        v = q[candidates]
        edges = v[:, [1, 2, 0]] - v
        axes = headref.unit(np.stack((-edges[:, :, 1], edges[:, :, 0]), axis=2))
        tp = np.einsum('nvi,nai->nva', v, axes)
        lp = np.einsum('vi,nai->nva', polygon, axes)
        separate_on_triangle = ((tp.min(axis=1) > lp.max(axis=1) + clearance) |
                                (lp.min(axis=1) > tp.max(axis=1) + clearance)).any(axis=1)
        separated[candidates] = separate_on_triangle
    return separated


def mouth_clump_depth(points, coverage, lip_planes):
    """Shared anatomical depth field for underlay and its painted outer locks."""
    x, y, z = points.T
    margin = (points[:, :2] @ lip_planes[:, :2].T + lip_planes[:, 2]).max(1)
    upper = 1.584 + .017 * assemble.smoothstep((np.abs(x) - .018) / .025)
    extent = assemble.smoothstep((upper - y) / .010)
    extent *= assemble.smoothstep((y - 1.530) / .018)
    extent *= 1 - assemble.smoothstep((np.abs(x) - .042) / .022)
    extent *= assemble.smoothstep((z - .020) / .025)
    edge = assemble.smoothstep((margin - .0011) / .0045)
    phase = (x * (1.0 + 3.0 * (y - 1.570)) + .12 * (y - 1.570)) / .009
    ridge = .70 + .30 * (.5 + .5 * np.cos(2 * np.pi * phase))
    # The complete existing low-coverage attachment fringe stays on skin.
    boost = .010 * extent * edge * assemble.smoothstep((coverage - .5) / .5) * ridge
    boost[boost < .00001] = 0.
    return boost


def fill_mouth_foundation(attributes, triangles, deltas, head_attributes,
                          head_triangles, head_deltas, lip_planes):
    """Give the mouth-side and lower-lip underlay actual rooted clump depth.

    The original continuous foundation was only 3.25 mm thick, so moving the
    hanging reference locks could never fill its flat U-shaped oral band.
    Sculpt this existing attached surface instead. Its feather root and lip
    aperture stay fixed; extra depth follows each bound skin normal through
    every identity/expression target rather than forming a rigid oral sheet.
    """
    original = attributes['POSITION'].copy()
    skin_points = head_attributes['POSITION']
    surface = trimesh.Trimesh(skin_points, head_triangles, process=False)
    cp, _, ti = trimesh.proximity.closest_point(surface, original)
    tv = head_triangles[ti]
    bc = headref.barycentric(cp, skin_points[tv[:, 0]],
                            skin_points[tv[:, 1]], skin_points[tv[:, 2]])
    _, weld = np.unique(np.round(skin_points, 6), axis=0, return_inverse=True)
    skin_normals = headref.vertex_normals(skin_points, head_triangles, weld)
    normal = headref.unit((skin_normals[tv] * bc[:, :, None]).sum(1))
    # Keep the upper central moustache, lip line and skin feather roots exact.
    # Both lateral corners and the complete lower band gain broad depth.
    coverage = np.minimum(attributes['COLOR_0'][:, 0] * 2., 1.)
    foundation = attributes['COLOR_0'][:, 0] < .6
    # Fine cards inherit the underlying local cap density, rather than treating
    # their R=1 material marker as full beard coverage at a feather root.
    if (~foundation).any():
        _, near = cKDTree(cp[foundation]).query(cp[~foundation])
        coverage[~foundation] = coverage[foundation][near]
    # Eight-to-ten-millimetre broad locks, lightly leaning with downward flow.
    # Geometry and normals supply the clump form; atlas contract is unchanged.
    boost = mouth_clump_depth(cp, coverage, lip_planes)
    attributes['POSITION'] = original + normal * boost[:, None]
    for index, hd in enumerate(head_deltas):
        morphed_normals = headref.vertex_normals(skin_points + hd, head_triangles, weld)
        nm = headref.unit((morphed_normals[tv] * bc[:, :, None]).sum(1))
        deltas[index] = deltas[index] + (nm - normal) * boost[:, None]
    # Original UV splits must share the sculpted normal so they do not facet.
    _, beard_weld = np.unique(np.round(attributes['POSITION'], 6), axis=0,
                              return_inverse=True)
    normals = headref.vertex_normals(attributes['POSITION'], triangles, beard_weld)
    changed = foundation & (boost > 0)
    valid = np.linalg.norm(normals, axis=1) > .5
    attributes['NORMAL'][changed & valid] = normals[changed & valid]
    return {'changed_vertices': int((boost > 0).sum()),
            'changed_foundation_vertices': int(changed.sum()),
            'maximum_added_depth_mm': float(boost.max() * 1000),
            'median_added_depth_over_1mm_mm': float(np.median(boost[boost > .001]) * 1000),
            'mouth_root_exact_margin_mm': 1.1,
            'broad_clump_spacing_mm': 9.0}


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
    lip_points = head.P[head.vgroups['lips'], :2]
    lip_hull = ConvexHull(lip_points)
    lip_polygon = lip_points[lip_hull.vertices]
    lip_planes = lip_hull.equations
    writer = assemble.Writer('Rabbit Lands attached elder full beard')
    mat = writer.material('rl_beard', [1, 1, 1, 1], cutoff=.35, double=True,
                          extras={'texture': 'full_beard.png', 'referenceSurface': True,
                                  'softHairline': True, 'featheredRoots': True,
                                  'skinAttachedFoundation': True})
    writer.embed_texture(mat, str(texture_out))
    report = {'source_sha256': digest(source), 'foundation_sha256': digest(foundation),
              'texture_sha256': digest(a.texture), 'head_sha256': digest(head.glb_path),
              'tool_sha256': digest(__file__), 'lods': {},
              'method': 'Painted cheek and lower locks over continuous attached foundation; cheek roots blended higher and central chin rounded; oral source sheet removed'}
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
        source_positions = sa['POSITION']
        # Preserve the painted cheek locks as well as the chin. A horizontal
        # cut at the lower lip had removed every upper cheek lock, leaving a
        # short flat cheek panel above an abruptly long chin. Only the central
        # oral sheet is excluded; the attached foundation still owns the lips.
        cheek = assemble.smoothstep((np.abs(source_positions[:, 0]) - .043) / .014)
        root_height = 1.565 + .054 * cheek
        source_root_margin = root_height - source_positions[:, 1] - .002
        st = st[(source_positions[st, 1] < root_height[st] - .002).all(1)]
        st = st[clear_oral_faces(source_positions, st, lip_polygon, lip_planes)]
        used, inv = np.unique(st, return_inverse=True)
        st = inv.reshape(-1, 3)
        old = sa['POSITION'][used]
        cut_margin = source_root_margin[used]
        # Carry real cheek locks inward/up to the moustache corners. Do not
        # restore the old broad oral sheet: it produces projecting wedges even
        # when its triangles avoid the mouth aperture in a front projection.
        lift = assemble.smoothstep((old[:, 1] - 1.545) / .040)
        lift *= assemble.smoothstep((.075 - np.abs(old[:, 0])) / .030)
        old[:, 0] -= np.sign(old[:, 0]) * .010 * lift
        old[:, 1] += .008 * lift
        hm = next(m for m in hg['meshes'] if m['name'] == f'rl_head_lod{lod}')
        assert names == sm['extras']['targetNames'] == hm['extras']['targetNames']
        hp = hm['primitives'][0]
        ha = attrs(hg, hb, hp)
        ht = rlglb.accessor(hg, hb, hp['indices']).astype(int).reshape(-1, 3)
        hP = ha['POSITION']
        hd = [rlglb.accessor(hg, hb, t['POSITION']) for t in hp['targets']]
        mouth_fill = fill_mouth_foundation(fa, ft, fd, ha, ht, hd, lip_planes)
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
        cheek = assemble.smoothstep((np.abs(old[:, 0]) - .025) / .025)
        root_height = 1.595 + .024 * cheek
        retain = assemble.smoothstep((root_height - old[:, 1]) / .044)
        retain *= assemble.smoothstep(cut_margin / .014)
        residual = old - cp
        # Keep the long beard, with a slightly rounder chin and fuller cheeks.
        # This narrows the abrupt length difference while retaining the source
        # lock detail rather than inflating the skin-attached lip foundation.
        residual[:, 1] *= .84 + .16 * cheek
        # Re-root the existing painted perioral lock relief on the thicker
        # attached band too. Otherwise its old 2.2mm backing is swallowed by
        # the new underlay, leaving a smooth cuff instead of painted clumps.
        source_fill = mouth_clump_depth(cp, np.ones(len(cp)), lip_planes)
        source_fill *= assemble.smoothstep((old[:, 1] - 1.540) / .020)
        p = cp + n * (.0022 + source_fill[:, None]) + residual * retain[:, None]
        # Close to the lips, long locks must become a shallow rooted layer.
        # Preserve the hanging volume below the chin and farther out on the
        # cheeks, while preventing a source wedge beside a mouth corner.
        oral_margin = (p[:, :2] @ lip_planes[:, :2].T + lip_planes[:, 2]).max(axis=1)
        oral_band = (old[:, 1] > 1.555) & (oral_margin < .020)
        offset = p - cp
        distance = np.linalg.norm(offset, axis=1)
        limit = .0035 + source_fill + .0045 * assemble.smoothstep(np.clip(oral_margin / .020, 0, 1))
        scale = np.minimum(1., limit / np.maximum(distance, 1e-12))
        p[oral_band] = cp[oral_band] + offset[oral_band] * scale[oral_band, None]
        st = st[np.linalg.norm(headref.tri_normals(p, st), axis=1) > 1e-12]
        st = st[clear_oral_faces(p, st, lip_polygon, lip_planes)]
        # Fade the reference's newly cut upper boundary into the underlay;
        # no opaque polygon edge is left around the face or lower lip.
        coverage = assemble.smoothstep((root_height - old[:, 1]) / .014)
        coverage *= assemble.smoothstep(cut_margin / .010)
        lip_margin = (p[:, :2] @ lip_planes[:, :2].T + lip_planes[:, 2]).max(axis=1)
        coverage *= assemble.smoothstep((lip_margin - .0012) / .003)
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
            deltas.append((hd[tv] * bc[:, :, None]).sum(1) + (nm - n) * (.0022 + source_fill[:, None]))
        # Preserve UV seams while sharing normals at coincident reference points.
        _, pweld = np.unique(np.round(p, 6), axis=0, return_inverse=True)
        normal = headref.vertex_normals(p, st, pweld)
        normal[np.linalg.norm(normal, axis=1) < .5] = n[np.linalg.norm(normal, axis=1) < .5]
        # The imported lower LODs omit strips of the hanging reference shell.
        # A small inset envelope closes those interior views without replacing
        # the painted outer locks or their irregular silhouette.
        # Only the hanging lower shell needs an inset closure. Extending its
        # convex envelope over the cheeks would span the oral opening with
        # broad triangles even though the painted oral sheet was removed.
        # Separate cheek closures cover sparse lower-LOD strips without a
        # single hull spanning between the cheeks in front of the mouth.
        backing_regions = [old[:, 1] < 1.562]
        backing_regions.extend((old[:, 0] * side > .034) & (old[:, 1] > 1.53)
                               for side in (-1, 1))
        backing_faces = []
        for region in backing_regions:
            backing_source = np.flatnonzero(region)
            hull = ConvexHull(p[backing_source])
            faces = backing_source[hull.simplices]
            flip = (headref.tri_normals(p, faces) * hull.equations[:, :3]).sum(1) < 0
            faces[flip] = faces[flip][:, [0, 2, 1]]
            backing_faces.append(faces)
        bt = np.vstack(backing_faces)
        bv, bi = np.unique(bt, return_inverse=True)
        bt = bi.reshape(-1, 3)
        centre = p[bv].mean(0)
        bp = centre + (p[bv] - centre) * .95
        bn = headref.vertex_normals(bp, bt)
        buv = np.column_stack((.88 + .08 * np.clip(bp[:, 0] / .08, -1, 1),
                               .73 + .20 * np.clip((1.61 - bp[:, 1]) / .14, 0, 1)))
        back_cheek = assemble.smoothstep((np.abs(bp[:, 0]) - .025) / .025)
        bcov = assemble.smoothstep((1.592 + .024 * back_cheek - bp[:, 1]) / .006)
        bcov *= assemble.smoothstep(cut_margin[bv] / .010)
        back_lip_margin = (bp[:, :2] @ lip_planes[:, :2].T + lip_planes[:, 2]).max(axis=1)
        bcov *= assemble.smoothstep((back_lip_margin - .0012) / .003)
        bt = bt[clear_oral_faces(bp, bt, lip_polygon, lip_planes)]
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
            'cheek_root_height_m': 1.619,
            'central_chin_length_ratio': .84,
            'medial_root_height_m': 1.595,
            'oral_clearance_mm': 1.2,
            'oral_edge_feather_mm': 3.0,
            'cheek_lock_lift_mm': 8.0,
            'cheek_lock_medial_shift_mm': 10.0,
            'upper_root_volume_blend_mm': 14.0,
            'upper_root_coverage_feather_mm': 10.0,
            'mouth_foundation_volume': mouth_fill,
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
