"""Derive the shared cape's tangent-space normal map from its greyscale cloth texture.

    python cape_normal.py <cape_grey.png> <generic_cape.glb> <cape_normal.png> [--size 1024] [--strength 4]

The Meshy delivery carries no normal map, and the client's equipment contract
wants one on every material (test_native_glb_assets: material detail).  The
painted greyscale already holds the relief a normal map would: the woven
knotwork of the trim is drawn light on its strands and dark in its gaps, and
the cloth carries a fine weave.  So the height is the texture's own luminance,
band-passed: details finer than ~1.5 texels are noise, and anything broader
than ~24 texels is the painted fold shading the base colour already shows
(lighting it twice would double it).

The atlas is Meshy's: hundreds of small UV islands with streaked padding
between them.  A blur that crosses an island's border mixes the padding in and
draws a ridge along every mesh seam, so both blurs are normalised over the
islands alone (rasterised from the cape's own UVs) and the result is carried
out into the padding from the nearest island texel.

Convention: OpenGL / glTF (+X right, +Y up the image, +Z out), so the green
channel rises where the height climbs toward the top of the image.
"""
from __future__ import annotations

import argparse
import json
import struct
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw
from scipy.ndimage import distance_transform_edt, gaussian_filter

MAX_TILT = 35.0


def island_mask(glb: Path, size: int) -> np.ndarray:
    data = glb.read_bytes()
    n = struct.unpack('<I', data[12:16])[0]
    doc = json.loads(data[20:20 + n])
    blob = data[20 + n + 8:]

    def accessor(i, dtype, k):
        a = doc['accessors'][i]
        v = doc['bufferViews'][a['bufferView']]
        return np.frombuffer(blob, dtype, a['count'] * k, v.get('byteOffset', 0) + a.get('byteOffset', 0)).reshape(-1, k)

    canvas = Image.new('L', (size, size), 0)
    draw = ImageDraw.Draw(canvas)
    for mesh in doc['meshes']:
        for prim in mesh['primitives']:
            uv = accessor(prim['attributes']['TEXCOORD_0'], '<f4', 2) * size
            for tri in accessor(prim['indices'], '<u4', 1).reshape(-1, 3):
                draw.polygon([tuple(uv[t]) for t in tri], fill=255, outline=255)
    return np.asarray(canvas) > 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('grey', type=Path)
    ap.add_argument('glb', type=Path)
    ap.add_argument('out', type=Path)
    ap.add_argument('--size', type=int, default=1024)
    ap.add_argument('--strength', type=float, default=4.0)
    args = ap.parse_args()
    lum = np.asarray(Image.open(args.grey).convert('L'), np.float32) / 255.0
    inside = island_mask(args.glb, lum.shape[0]).astype(np.float32)
    scale = lum.shape[0] / 2048.0

    def blur(sigma):
        return gaussian_filter(lum * inside, sigma) / np.maximum(gaussian_filter(inside, sigma), 1e-4)

    band = (blur(1.5 * scale) - blur(24.0 * scale)) * inside
    # carry each island's height out over its padding, so a bilinear read at a
    # seam meets the island's own relief rather than a cliff
    _, (rows, cols) = distance_transform_edt(inside == 0, return_indices=True)
    band = band[rows, cols]
    height = Image.fromarray(band.astype(np.float32)).resize((args.size, args.size), Image.LANCZOS)
    h = np.asarray(height, np.float32) * args.strength * (args.size / 1024.0)
    d_col = np.gradient(h, axis=1)
    d_row = np.gradient(h, axis=0)
    # height rising to the right tilts the normal left; rising toward the top
    # of the image (falling rows) tilts it down
    slope = np.stack([-d_col, d_row], -1)
    # a painted hard edge is a cliff in this height; hold every tilt under
    # MAX_TILT so it reads as a crease, not a hole
    steep = np.linalg.norm(slope, axis=-1, keepdims=True)
    slope *= np.minimum(1.0, np.tan(np.radians(MAX_TILT)) / np.maximum(steep, 1e-9))
    n = np.concatenate([slope, np.ones_like(h)[..., None]], -1)
    n /= np.linalg.norm(n, axis=-1, keepdims=True)
    rgb = np.clip(np.round((n * 0.5 + 0.5) * 255.0), 0, 255).astype(np.uint8)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    Image.fromarray(rgb, 'RGB').save(args.out, optimize=True)
    tilt = np.degrees(np.arccos(np.clip(n[..., 2], -1, 1)))
    print({'out': str(args.out), 'bytes': args.out.stat().st_size, 'island_cover': round(float(inside.mean()), 3),
           'tilt_deg_p50': round(float(np.percentile(tilt, 50)), 1), 'tilt_deg_p95': round(float(np.percentile(tilt, 95)), 1)})
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
