"""Project stable follicle pigment onto existing Human UVs; no model generation."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

import numpy as np
from PIL import Image
from scipy.ndimage import distance_transform_edt


def smooth(a, b, x):
    t = np.clip((x - a) / (b - a), 0, 1)
    return t * t * (3 - 2 * t)


def coverage(point, eye):
    x, y, z = np.abs(point[..., 0]), point[..., 1] - eye, point[..., 2]
    cheek = -.073 + .033 * smooth(.014, .070, x)
    jaw = 1 - smooth(cheek - .004, cheek + .005, y)
    mouth = np.sqrt((point[..., 0] / .024) ** 2 + ((y + .063) / .009) ** 2)
    jaw *= smooth(.95, 1.20, mouth)
    centre = -.053 - .011 * (x / .040) ** 2
    moustache = smooth(centre - .008, centre - .004, y) * (1 - smooth(centre + .003, centre + .007, y))
    moustache *= smooth(.002, .007, x) * (1 - smooth(.033, .043, x))
    front = smooth(-.012, .014, z)
    edge = 1 - smooth(.073, .086, x)
    bottom = smooth(-.123, -.100, y)
    return np.clip(np.maximum(jaw, moustache) * front * edge * bottom, 0, 1)


def bake(source: Path, destination: Path, size: int):
    data = json.loads(source.read_text())
    vertices = np.asarray(data['vertices'], dtype=np.float64)
    indices = np.asarray(data['indices']).reshape(-1, 3)
    mask = np.zeros((size, size), dtype=np.float32)
    filled = np.zeros((size, size), dtype=bool)
    for tri in indices:
        v = vertices[tri]
        # Head surface only; never project ear backs, inner mouth or torso UVs.
        if np.max(v[:, 1]) < data['eye_height'] - .15 or np.min(v[:, 1]) > data['eye_height'] + .02 or np.max(v[:, 5]) < .12:
            continue
        uv = v[:, 3:5] * size - .5
        low = np.maximum(np.floor(uv.min(axis=0)).astype(int), 0)
        high = np.minimum(np.ceil(uv.max(axis=0)).astype(int), size - 1)
        if np.any(high < low):
            continue
        xx, yy = np.meshgrid(np.arange(low[0], high[0] + 1), np.arange(low[1], high[1] + 1))
        den = (uv[1, 1] - uv[2, 1]) * (uv[0, 0] - uv[2, 0]) + (uv[2, 0] - uv[1, 0]) * (uv[0, 1] - uv[2, 1])
        if abs(den) < 1e-12:
            continue
        a = ((uv[1, 1] - uv[2, 1]) * (xx - uv[2, 0]) + (uv[2, 0] - uv[1, 0]) * (yy - uv[2, 1])) / den
        b = ((uv[2, 1] - uv[0, 1]) * (xx - uv[2, 0]) + (uv[0, 0] - uv[2, 0]) * (yy - uv[2, 1])) / den
        c = 1 - a - b
        inside = (a >= -1e-6) & (b >= -1e-6) & (c >= -1e-6)
        p = a[..., None] * v[0, :3] + b[..., None] * v[1, :3] + c[..., None] * v[2, :3]
        base = coverage(p, data['eye_height'])
        # Fixed follicles in anatomical space, then baked and mip filtered.
        cell = np.floor(p[..., :2] * 680)
        random = np.mod(np.sin(cell[..., 0] * 127.1 + cell[..., 1] * 311.7) * 43758.5453, 1)
        # The original body atlas gives the face relatively few texels. Keep
        # follicles close in value so bilinear filtering reads as fine shadow,
        # rather than merging high-contrast dots into a camouflage pattern.
        grain = .82 + .18 * smooth(.20, .80, random)
        shade = base * grain
        old = mask[yy, xx]
        mask[yy[inside], xx[inside]] = np.maximum(old[inside], shade[inside])
        filled[yy[inside], xx[inside]] = True
    distance, nearest = distance_transform_edt(~filled, return_indices=True)
    pad = (~filled) & (distance < 6)
    mask[pad] = mask[nearest[0][pad], nearest[1][pad]]
    image = Image.fromarray(np.round(mask * 255).astype(np.uint8))
    destination.parent.mkdir(parents=True, exist_ok=True)
    image.save(destination, optimize=True)
    # Imported as linear scalar data. Mips remove follicle aliasing at distance.
    import_path = Path(str(destination) + '.import')
    if not import_path.exists():
        import_path.write_text('''[remap]
importer="texture"
type="CompressedTexture2D"
[deps]
source_file="res://data/actors/grooming/''' + destination.name + '''"
[params]
compress/mode=0
mipmaps/generate=true
detect_3d/compress_to=0
''', newline="\n")
    return {'source_sha256': data['source_sha256'], 'mask_sha256': hashlib.sha256(destination.read_bytes()).hexdigest(),
            'size': size, 'bytes': destination.stat().st_size, 'nonzero_texels': int(np.count_nonzero(mask))}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--input', required=True, type=Path)
    parser.add_argument('--output', required=True, type=Path)
    parser.add_argument('--size', default=1024, type=int)
    args = parser.parse_args()
    records = {sex: bake(args.input / (sex + '.json'), args.output / ('stubble_' + sex + '.png'), args.size)
               for sex in ('male', 'female')}
    (args.output / 'manifest.json').write_text(json.dumps({'version': 1, 'masks': records}, indent=2) + '\n', newline="\n")
    print(json.dumps(records, indent=2))


if __name__ == '__main__':
    main()
