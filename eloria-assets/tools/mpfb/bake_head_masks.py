"""Pack MPFB brow, vermilion and stubble into the existing head PNG alpha.

This is offline coverage data, not a repaint: RGB stays byte-exact. Neutral128
separates disjoint brow/lip(0..127) and stubble(129..255) regions. A padded lip
UV rectangle distinguishes lip satin coverage from eyebrow pigment coverage.
No map, material,
vertex, draw or rig is added. Preserve the source stage; write a new output root.
"""
from __future__ import annotations

import argparse
import hashlib
import io
import json
from pathlib import Path
import shutil

import numpy as np
from PIL import Image
from scipy.ndimage import distance_transform_edt
from scipy.sparse import coo_matrix
from scipy.sparse.csgraph import connected_components

from match_neck_tone import Glb
from refine_concept_eyes import world_matrices, transform


NEUTRAL = 128


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def smooth(a, b, value):
    t = np.clip((value - a) / (b - a), 0., 1.)
    return t * t * (3. - 2. * t)


def raster_geometry(glb, primitive, to_head, dimensions):
    """Raster actual head-local coordinates, normals and canonical seam distance.

    UV coordinates use the export's glTF top-left convention. At shared pixels,
    prefer the front-facing surface over hidden mouth/socket fragments.
    """
    attrs = primitive['attributes']
    canonical = glb.read(attrs['POSITION']).astype(float)
    points = transform(canonical, to_head)
    normals = glb.read(attrs['NORMAL']) @ np.linalg.inv(to_head[:3, :3])
    normals /= np.maximum(np.linalg.norm(normals, axis=1, keepdims=True), 1e-12)
    uv = glb.read(attrs['TEXCOORD_0'])
    indices = glb.read(primitive['indices']).reshape(-1, 3)
    # The source retains disconnected inner-mouth, tongue and socket islands.
    # Restrict coverage to the largest connected outer-skin component.
    edges = np.concatenate([indices[:, [0, 1]], indices[:, [1, 2]], indices[:, [2, 0]]])
    _, groups = connected_components(coo_matrix((np.ones(len(edges)), (edges[:, 0], edges[:, 1])), shape=(len(points), len(points))), directed=False)
    main = int(np.bincount(groups).argmax())
    indices = indices[np.all(groups[indices]==main, axis=1)]
    width, height = dimensions
    position_map = np.zeros((height, width, 3), np.float32)
    normal_map = np.zeros_like(position_map)
    seam_map = np.zeros((height, width), np.float32)
    best = np.full((height, width), -np.inf, np.float32)
    for tri in indices:
        coords = uv[tri] * np.array([width, height]) - .5
        lo = np.maximum(np.floor(coords.min(0)).astype(int), 0)
        hi = np.minimum(np.ceil(coords.max(0)).astype(int), [width-1, height-1])
        a, b = coords[1]-coords[0], coords[2]-coords[0]
        det = a[0]*b[1]-a[1]*b[0]
        if abs(det)<1e-10 or np.any(hi<lo):
            continue
        yy, xx = np.mgrid[lo[1]:hi[1]+1, lo[0]:hi[0]+1]
        dx, dy = xx-coords[0, 0], yy-coords[0, 1]
        w1 = (dx*b[1]-dy*b[0])/det
        w2 = (a[0]*dy-a[1]*dx)/det
        w0 = 1-w1-w2
        inside = (w0>=-1e-6)&(w1>=-1e-6)&(w2>=-1e-6)
        if not inside.any():
            continue
        weights = np.column_stack([w0[inside], w1[inside], w2[inside]])
        p = weights @ points[tri]
        n = weights @ normals[tri]
        n /= np.maximum(np.linalg.norm(n, axis=1, keepdims=True), 1e-12)
        score = n[:, 2]+p[:, 2]*.1
        ys, xs = yy[inside], xx[inside]
        keep = score>best[ys, xs]
        ys, xs = ys[keep], xs[keep]
        best[ys, xs] = score[keep]
        position_map[ys, xs] = p[keep]
        normal_map[ys, xs] = n[keep]
        c = weights @ canonical[tri]
        seam_map[ys, xs] = (c[:, 1]+.6*c[:, 2]-1.5)[keep]/np.sqrt(1.36)
    return position_map, normal_map, seam_map, np.isfinite(best)


def semantic_coverage(position, normal, seam_distance, valid, rgb, frame):
    scale = float(frame['scale'])
    center_x = float(np.mean([frame['eye_left'][0], frame['eye_right'][0]]))
    x = (position[:, :, 0]-center_x)/scale
    y = (position[:, :, 1]-float(frame['mouth_y']))/scale
    z = (position[:, :, 2]-float(frame['eye_z']))/scale
    eye_y = (position[:, :, 1]-float(frame['eye_y']))/scale
    ax = np.abs(x)
    front = smooth(-.018, .008, z)*smooth(.05, .45, normal[:, :, 2])
    # Beard pigment wraps onto lateral cheek/jaw planes. Ear/rear-head and
    # neck exclusions remain anatomical; a front-only normal gate would cut
    # the beard off well before the sideburn when viewed in profile.
    beard_surface = smooth(-.060, -.020, z)*smooth(-.18, .20, normal[:, :, 2])
    face_width = 1-smooth(.063, .078, ax)
    # Jaw/chin below the vermilion. The narrow mouth exclusion follows UVs
    # when identity shape changes, protecting both upper and lower lips.
    jaw = smooth(-.055, -.041, y)*(1-smooth(-.004, .012, y))
    cheek = smooth(.027, .044, ax)*smooth(-.025, -.010, y)*(1-smooth(.020, .037, y))
    moustache = smooth(.010, .017, y)*(1-smooth(.022, .029, y))*(1-smooth(.024, .035, ax))
    sideburn = smooth(.046, .060, ax)*(1-smooth(.070, .078, ax))
    sideburn *= smooth(-.010, .012, y)*(1-smooth(-.018, .002, eye_y))
    lip_bounds = frame.get('mouth_bounds', [])
    lip_half_width = .033
    lip_half_height = .0115
    if len(lip_bounds)==2:
        lip_half_width = max(.026, (float(lip_bounds[1][0])-float(lip_bounds[0][0]))/(2*scale))
        lip_half_height = max(lip_half_height, (float(lip_bounds[1][1])-float(lip_bounds[0][1]))/(2*scale)+.001)
    # Ellipse has a soft outer edge instead of a hard painted moustache cut.
    lip_radius = np.sqrt((x/(lip_half_width+.001))**2+(y/lip_half_height)**2)
    lip_clearance = smooth(1.0, 1.30, lip_radius)
    nose_clearance = 1-smooth(.022, .031, y)*(1-smooth(.017, .026, ax))
    # Canonical cut-plane protection is independent of head-frame scale.
    neck_clearance = smooth(.020, .035, seam_distance)
    stubble = np.maximum.reduce([jaw, cheek*.80, moustache*.88, sideburn*.75])
    stubble *= beard_surface*face_width*lip_clearance*nose_clearance*neck_clearance*valid
    # Color strength is technical pigment segmentation, confined to an upper
    # orbital band. Dark eyelid, nostril and inner-bridge pixels cannot enter.
    eye_x = np.where(x<0, float(frame['eye_left'][0]), float(frame['eye_right'][0]))
    ex = np.abs((position[:, :, 0]-eye_x)/scale)
    brow_band = smooth(.006, .011, eye_y)*(1-smooth(.024, .032, eye_y))
    brow_band *= (1-smooth(.022, .035, ex))*smooth(.010, .017, ax)*front*valid
    luminance = np.sum(rgb.astype(float)/255*np.array([.2126, .7152, .0722]), axis=2)
    pigment = 1-smooth(.28, .55, luminance)
    brow = brow_band*pigment
    # External vermilion is red/magenta relative to the adjacent warm skin.
    # Anatomy gates this pigment test to the existing mouth surface; the
    # largest skin component already excludes oral cavity/tongue/socket UVs.
    colors = rgb.astype(float)/255
    r, g, b = colors[:, :, 0], colors[:, :, 1], colors[:, :, 2]
    red_pigment = smooth(.055, .18, r-2*g+b)*smooth(.065, .17, r-g)
    red_pigment *= smooth(.075, .20, luminance)
    lip_anatomy = 1-smooth(.90, 1.12, np.sqrt((x/(lip_half_width+.001))**2+(y/lip_half_height)**2))
    lips = lip_anatomy*red_pigment*front*valid
    # These regions are anatomically disjoint; guard future profile changes.
    stubble[(brow>.001)|(lips>.001)] = 0
    return np.clip(brow, 0, 1), np.clip(stubble, 0, 1), np.clip(lips, 0, 1)


def lip_uv_rectangle(lips, brow):
    # Include bilinear padding and several mip footprints, without touching
    # the disjoint brow region. Only the low-alpha pixels select the finish.
    yy, xx = np.where(np.rint(lips*NEUTRAL)>0)
    if len(xx)<30:
        raise ValueError('External lip pigment coverage unexpectedly empty')
    height, width = lips.shape
    padding = 10
    x0, y0 = max(0, int(xx.min())-padding), max(0, int(yy.min())-padding)
    x1, y1 = min(width, int(xx.max())+padding+1), min(height, int(yy.max())+padding+1)
    brow_overlap = int(np.count_nonzero(np.rint(brow[y0:y1, x0:x1]*NEUTRAL)>0))
    if brow_overlap:
        raise ValueError('Padded lip rectangle overlaps eyebrow coverage')
    return [x0/width, y0/height, x1/width, y1/height], [x0, y0, x1, y1], padding


def build_one(input_root, output_root, sex):
    source_dir = input_root/sex
    destination = output_root/sex
    destination.mkdir(parents=True, exist_ok=True)
    source = source_dir/f'luminous_{sex}.glb'
    target = destination/source.name
    glb = Glb(source)
    fit = json.loads((source_dir/'fit.json').read_text())
    node_index = next(i for i, node in enumerate(glb.doc['nodes']) if node.get('name')=='body')
    head_index = next(i for i, node in enumerate(glb.doc['nodes']) if node.get('name')=='Head')
    primitive = glb.doc['meshes'][glb.doc['nodes'][node_index]['mesh']]['primitives'][0]
    worlds = world_matrices(glb.doc)
    to_head = np.linalg.inv(worlds[head_index]) @ worlds[node_index]
    image_index, image, _factor = glb.image(primitive)
    original = np.array(image.convert('RGBA'))
    coordinates, normals, seam, valid = raster_geometry(glb, primitive, to_head, image.size)
    brow, stubble, lips = semantic_coverage(coordinates, normals, seam, valid, original[:, :, :3], fit['face_frame_head_local'])
    lip_bounds, lip_pixels, lip_padding = lip_uv_rectangle(lips, brow)
    alpha = np.full(valid.shape, NEUTRAL, np.uint8)
    alpha = np.rint(NEUTRAL-NEUTRAL*np.maximum(brow,lips)+(255-NEUTRAL)*stubble).clip(0, 255).astype(np.uint8)
    # Pad only coverage data two texels beyond UV-island boundaries. This
    # protects bilinear sampling without copying pigment between islands.
    distance, nearest = distance_transform_edt(~valid, return_indices=True)
    pad = (~valid)&(distance<=2)
    alpha[pad] = alpha[nearest[0][pad], nearest[1][pad]]
    result = original.copy()
    result[:, :, 3] = alpha
    buffer = io.BytesIO()
    Image.fromarray(result).save(buffer, format='PNG', optimize=True)
    glb.replace_image(image_index, buffer.getvalue(), target)
    check = Glb(target)
    for key in ('nodes','skins','meshes','accessors','materials','textures','samplers','animations'):
        if glb.doc.get(key)!=check.doc.get(key):
            raise ValueError('Unexpected structural change: '+key)
    for index in range(len(glb.doc['accessors'])):
        if not np.array_equal(glb.read(index), check.read(index)):
            raise ValueError(f'Changed accessor{index}')
    selected_view = glb.doc['images'][image_index]['bufferView']
    for index in range(len(glb.doc['bufferViews'])):
        if index!=selected_view and glb.view(index)!=check.view(index):
            raise ValueError(f'Changed binary outside head PNG:{index}')
    _, checked_image, _ = check.image(primitive)
    if not np.array_equal(np.array(checked_image.convert('RGB')), original[:, :, :3]):
        raise ValueError('Head RGB changed')
    if np.count_nonzero(alpha<NEUTRAL)<30 or np.count_nonzero(alpha>NEUTRAL)<500:
        raise ValueError('Mask coverage unexpectedly empty')
    fit['head_masks'] = True
    fit['head_lip_uv_bounds'] = lip_bounds
    fit['head_masks_encoding'] = {'neutral':NEUTRAL,'brow':'max((128-alpha)/128,0) outside head_lip_uv_bounds','lip':'max((128-alpha)/128,0) inside head_lip_uv_bounds','stubble':'max((alpha-128)/127,0)','channel':'existing head PNG alpha; RGB unchanged'}
    fit['output_sha256'] = sha(target)
    (destination/'fit.json').write_text(json.dumps(fit, indent=2)+'\n')
    copied = []
    for path in source_dir.iterdir():
        regenerated = (source.name,'fit.json','head-mask-receipt.json','head-mask-alpha.png','brow-coverage.png','stubble-coverage.png','lip-coverage.png')
        if path.is_file() and path.name not in regenerated:
            shutil.copy2(path, destination/path.name)
            copied.append({'file':path.name,'sha256':sha(path)})
    # Separate technical mask previews; never alter actual game screenshots.
    Image.fromarray(alpha).save(destination/'head-mask-alpha.png')
    Image.fromarray(np.rint(brow*255).astype(np.uint8)).save(destination/'brow-coverage.png')
    Image.fromarray(np.rint(stubble*255).astype(np.uint8)).save(destination/'stubble-coverage.png')
    Image.fromarray(np.rint(lips*255).astype(np.uint8)).save(destination/'lip-coverage.png')
    report = {'sex':sex,'input':str(source.resolve()),'input_sha256':sha(source),
        'output':str(target.resolve()),'output_sha256':sha(target),'tool_sha256':sha(__file__),
        'head_image_index':image_index,'dimensions':list(image.size),'rgb_byte_exact':True,
        'geometry_accessors_exact':len(glb.doc['accessors']),'other_buffer_views_exact':True,
        'rig_materials_animation_exact':True,'neutral_alpha':NEUTRAL,
        'brow_texels':int(np.count_nonzero(np.rint(brow*NEUTRAL)>0)),
        'lip_texels':int(np.count_nonzero(np.rint(lips*NEUTRAL)>0)),
        'low_alpha_texels':int(np.count_nonzero(alpha<NEUTRAL)),
        'lip_uv_bounds':lip_bounds,'lip_pixel_bounds':lip_pixels,'lip_rectangle_padding_px':lip_padding,
        'brow_texels_inside_lip_rectangle':0,
        'stubble_texels':int(np.count_nonzero(alpha>NEUTRAL)),
        'minimum_alpha':int(alpha.min()),'maximum_alpha':int(alpha.max()),
        'overlap_texels':int(np.count_nonzero((np.maximum(brow,lips)>.001)&(stubble>.001))),
        'disk_delta_bytes':target.stat().st_size-source.stat().st_size,
        'maps_materials_vertices_draws_added':0,'runtime_texture_samples_added':0,
        'copied_sidecars':copied,'encoding':fit['head_masks_encoding'],
        'scope':'Soft static jaw/upperlip/sideburn coverage excludes lips, nose, ears and neck seam; dark brow pigment restricted to upper orbit. Lip satin coverage is bounded to external vermilion pigment with a disjoint padded UV rectangle; RGB remains exact.'}
    (destination/'head-mask-receipt.json').write_text(json.dumps(report, indent=2)+'\n')
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--input-root',type=Path,required=True)
    parser.add_argument('--output-root',type=Path,required=True)
    args = parser.parse_args()
    if args.input_root.resolve()==args.output_root.resolve():
        raise ValueError('Keep the input stage unchanged; choose a new output root')
    if args.output_root.exists() and any(args.output_root.iterdir()):
        raise ValueError('Choose a new empty output stage')
    args.output_root.mkdir(parents=True, exist_ok=True)
    records = [build_one(args.input_root,args.output_root,sex) for sex in ('male','female')]
    (args.output_root/'head-mask-manifest.json').write_text(json.dumps({'schema':'RL MPFB packed head coverage1','models':records},indent=2)+'\n')
    print(json.dumps({'output':str(args.output_root.resolve()),'models':records},indent=2))


if __name__=='__main__':
    main()
