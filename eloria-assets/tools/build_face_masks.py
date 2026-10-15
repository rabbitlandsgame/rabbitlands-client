"""Bake painted-eye/brow regions into the retained head's existing UV atlas.

The reviewed annotations in face_regions.json use an orthographic view of the
canonical rest mesh (+Z facing the viewer). RGB encodes eye protection, iris
colour, and brow pigment. Sampling these masks per fragment avoids recolouring
entire low-poly triangles. Geometry, UVs, source art and skin weights are intact.
"""
from __future__ import annotations
import argparse
import hashlib
import io
import json
from pathlib import Path
import sys
import numpy as np
from PIL import Image, ImageDraw, ImageFilter
from scipy.ndimage import map_coordinates, maximum_filter

sys.path.insert(0, str(Path(__file__).parent / 'tpose_bodies/vendor'))
import glbkit as g


def source_image(d, b, material):
    t = d['materials'][material]['pbrMetallicRoughness']['baseColorTexture']['index']
    im = d['images'][d['textures'][t]['source']]
    v = d['bufferViews'][im['bufferView']]
    start = v.get('byteOffset', 0)
    return np.asarray(Image.open(io.BytesIO(b[start:start + v['byteLength']])).convert('RGB'))


def brow_strokes(region):
    """Soft tapered hair strokes for faces whose source atlas has bare brows.

    Each cubic runs from the inner brow to its tail. A sparse, directional
    stroke layer breaks up the silhouette instead of painting a solid wedge.
    """
    layer = Image.new('L', (900, 600))
    draw = ImageDraw.Draw(layer)
    for spec in region.get('browStrokes', []):
        controls = np.array(spec['curve'], dtype=float) + [150, region['cropY']]
        t = np.linspace(0, 1, 96)[:, None]
        curve = ((1-t)**3*controls[0]+3*(1-t)**2*t*controls[1]+
                 3*(1-t)*t*t*controls[2]+t**3*controls[3])
        tangent = np.gradient(curve, axis=0)
        tangent /= np.linalg.norm(tangent, axis=1, keepdims=True)
        normal = np.stack([-tangent[:, 1], tangent[:, 0]], axis=1)
        normal *= np.where(normal[:, 1:2] > 0, -1, 1)
        width = spec['width']*(.60+.40*np.sin(np.pi*t[:, 0]))*(1-t[:, 0])**.48
        edge1 = curve+normal*width[:, None]*.42
        edge2 = curve-normal*width[:, None]*.42
        draw.polygon([tuple(v) for v in np.concatenate([edge1, edge2[::-1]])], fill=100)
        for i in range(0, len(curve)-1, 2):
            start = curve[i]-normal[i]*width[i]*.35
            end = curve[i]+normal[i]*width[i]*(.45+.14*np.sin(i*2.4))+tangent[i]*2.8
            draw.line([tuple(start), tuple(end)], fill=185+int(35*np.sin(i*1.7)), width=1)
    return np.asarray(layer.filter(ImageFilter.GaussianBlur(.55)))/255.


def projection_masks(region):
    layers = []
    for channel in range(3):
        layer = Image.new('L', (900, 600))
        draw = ImageDraw.Draw(layer)
        for points in region.get('brows' if channel == 2 else 'eyes', []):
            draw.polygon([(x + 150, y + region['cropY']) for x, y in points], fill=255)
        if channel == 1 and 'irises' in region:
            irises = Image.new('L', layer.size)
            brush = ImageDraw.Draw(irises)
            for x, y, rx, ry in region['irises']:
                x += 150
                y += region['cropY']
                brush.ellipse((x-rx, y-ry, x+rx, y+ry), fill=255)
            layer = Image.fromarray(np.minimum(np.asarray(layer), np.asarray(irises)))
        layers.append(np.asarray(layer.filter(ImageFilter.GaussianBlur(0.7))) / 255.)
    layers.append(brow_strokes(region))
    return np.stack(layers, -1)


def bake(path, region, projection):
    d, b = g.read(path)
    head = next(p for m in d['meshes'] if m['name'] == 'body'
                for p in m['primitives'] if p.get('extras', {}).get('sourceRole') == 'race_head')
    pixels = source_image(d, b, head['material'])
    h, w = pixels.shape[:2]
    masks = np.zeros((h, w, 4), dtype=np.float32)
    occupied = np.zeros((h, w), dtype=bool)
    projected = projection_masks(region)
    for mesh in d['meshes']:
        for p in mesh['primitives']:
            if p.get('extras', {}).get('sourceRole') != 'race_head':
                continue
            a = p['attributes']
            v = g.accessor(d, b, a['POSITION'])
            uv = g.accessor(d, b, a['TEXCOORD_0']) * [w, h] - .5
            faces = g.accessor(d, b, p['indices']).astype(int).reshape(-1, 3)
            for face in faces:
                positions = v[face]
                if positions[:, 2].max() < .02 or positions[:, 1].max() < 1.57:
                    continue
                points = uv[face]
                lo = np.maximum(np.floor(points.min(0)).astype(int), [0, 0])
                hi = np.minimum(np.ceil(points.max(0)).astype(int), [w-1, h-1])
                if np.any(lo > hi):
                    continue
                edge1, edge2 = points[1:] - points[0]
                det = edge1[0]*edge2[1] - edge1[1]*edge2[0]
                if abs(det) < 1e-8:
                    continue
                yy, xx = np.mgrid[lo[1]:hi[1]+1, lo[0]:hi[0]+1]
                dx, dy = xx-points[0, 0], yy-points[0, 1]
                u = (dx*edge2[1]-dy*edge2[0])/det
                t = (edge1[0]*dy-edge1[1]*dx)/det
                weights = np.stack((1-u-t, u, t), -1)
                world = weights @ positions
                valid = (weights.min(-1) >= -1e-5) & (world[..., 2] > .02)
                py = (projection['yMax']-world[..., 1])*projection['pixelsPerMetre']
                px = (world[..., 0]-projection['xMin'])*projection['pixelsPerMetre']
                values = np.stack([map_coordinates(projected[..., c], [py, px], order=1,
                                                   mode='constant') for c in range(4)], -1)
                masks[yy[valid], xx[valid]] = values[valid]
                occupied[yy[valid], xx[valid]] = True
    # Tint the painted brow pigment, preserving the skin between fine hairs.
    # Preserve near-white sclera/specular pixels even where an iris ellipse
    # crosses their painted boundary. Grey/blue irises remain below this level.
    neutral = pixels.min(-1)/255.
    masks[..., 1] *= 1-np.clip((neutral-.65)/.22, 0, 1)
    brow = masks[..., 2] > .1
    if brow.any():
        lum = pixels.mean(-1)/255.
        skin = float(np.percentile(lum[brow], 95))
        masks[..., 2] *= np.clip((skin-lum)/max(skin*.4, .03), 0, 1)
    # New hair strokes carry their own coverage: bare skin has no source
    # pigment from which to derive a contrast mask.
    masks[..., 2] = np.maximum(masks[..., 2], masks[..., 3])
    masks = masks[..., :3]
    # Atlas padding prevents seams under bilinear and mip filtering; it never
    # grows a region onto a different, occupied chart.
    for c in range(3):
        padding = maximum_filter(masks[..., c], size=5)
        masks[..., c][~occupied] = padding[~occupied]
    return np.rint(np.clip(masks, 0, 1)*255).astype('u1'), {
        'modelSHA256': hashlib.sha256(path.read_bytes()).hexdigest(),
        'sourceMaterial': head['material'], 'size': [w, h],
        'pixelsPerChannel': (masks > .1).sum((0, 1)).tolist(),
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--models', type=Path, required=True)
    parser.add_argument('--out', type=Path, required=True)
    args = parser.parse_args()
    regions = json.loads(Path(__file__).with_name('face_regions.json').read_text())
    args.out.mkdir(parents=True, exist_ok=True)
    reports = {}
    for slug, region in regions['models'].items():
        pixels, report = bake(args.models/(slug+'.glb'), region, regions['projection'])
        target = args.out/(slug+'.png')
        Image.fromarray(pixels).save(target, optimize=True)
        report['maskSHA256'] = hashlib.sha256(target.read_bytes()).hexdigest()
        reports[slug] = report
        print(slug, report['pixelsPerChannel'])
    (args.out/'manifest.json').write_text(json.dumps(reports, indent=2)+'\n')


if __name__ == '__main__':
    main()
