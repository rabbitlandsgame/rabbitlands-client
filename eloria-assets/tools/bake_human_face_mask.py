"""Bake an orthographic front-view face mask into a packed Human body's UV atlas.

    python eloria-assets/tools/bake_human_face_mask.py <body.glb> <front_mask.png> <out_mask.png>
        --centre-y 1.6385 --metres-per-pixel 0.0003 [--centre-x 0]

`face_appearance.gdshader` reads an RGB region texture in the body atlas's UV
space: R keeps the whole eye out of the skin dye, G selects the iris for the
eye colour, B selects brow pigment for the hair colour.  The regenerated Human
heads (2026-10-05) are annotated in an orthographic front render of the rest
pose instead of `face_regions.json`'s fixed frame: the mask's pixel (u, v)
looks at x = centre_x + (u - w/2) * m, y = centre_y - (v - h/2) * m.

Every triangle of the head's skin, eye and brow surfaces is rasterised in UV
space at the atlas's resolution; each texel's rest position is projected into
the front mask and sampled.  Only forward-facing head texels take a value, and
the result is padded a few texels into empty atlas so mip/bilinear filtering
never darkens a chart edge.

With --manifest (normally godot-client/assets/actors/native/face_masks/
manifest.json) the run also writes the mask's entry there, keyed by --slug
(default: the body file's stem): the body and mask hashes, the source
material, the atlas size, the texels above 0.1 per channel and the UV groups
it was baked in.  The baker samples each part's raw TEXCOORD_0, so every
group is scale 1, offset 0.  Bake from the packed body exactly as it will be
installed: modelSHA256 pins those bytes.  manifest_entry() recomputes an entry
from an installed body and mask without re-baking.
"""
from __future__ import annotations

import argparse
import hashlib
import io
import json
import sys
from pathlib import Path

import numpy as np
from PIL import Image
from scipy.ndimage import map_coordinates, maximum_filter

sys.path.insert(0, str(Path(__file__).parent / 'tpose_bodies' / 'vendor'))
import glbkit as g  # noqa: E402

PARTS = ('body', 'eyes', 'eyebrows', 'scalp')


def atlas_size(gltf, blob, material):
    tex = gltf['materials'][material]['pbrMetallicRoughness']['baseColorTexture']['index']
    image = gltf['images'][gltf['textures'][tex]['source']]
    view = gltf['bufferViews'][image['bufferView']]
    start = view.get('byteOffset', 0)
    return Image.open(io.BytesIO(bytes(blob[start:start + view['byteLength']]))).size


def bake(body: Path, front: Path, centre_x: float, centre_y: float, mpp: float):
    gltf, blob = g.read(body)
    world = g.globals_of(gltf)
    skin = gltf['skins'][0]
    names = [gltf['nodes'][j]['name'] for j in skin['joints']]
    head = world[skin['joints'][names.index('Head')]][:3, 3]
    mask_src = np.asarray(Image.open(front).convert('RGB')).astype(np.float32) / 255.0
    mh, mw = mask_src.shape[:2]
    meshes = {gltf['meshes'][n['mesh']]['name']: gltf['meshes'][n['mesh']] for n in gltf['nodes'] if 'mesh' in n}
    material = meshes['body']['primitives'][0]['material']
    w, h = atlas_size(gltf, blob, material)
    out = np.zeros((h, w, 3), np.float32)
    occupied = np.zeros((h, w), bool)
    for part in PARTS:
        if part not in meshes:
            continue
        for prim in meshes[part]['primitives']:
            attrs = prim['attributes']
            v = g.accessor(gltf, blob, attrs['POSITION'])
            uv = g.accessor(gltf, blob, attrs['TEXCOORD_0']) * [w, h] - 0.5
            faces = g.accessor(gltf, blob, prim['indices']).astype(int).reshape(-1, 3)
            for face in faces:
                p = v[face]
                # forward-facing head skin only (the mask is a front projection)
                if p[:, 1].max() < head[1] - 0.02 or p[:, 2].max() < head[2] - 0.01:
                    continue
                n = np.cross(p[1] - p[0], p[2] - p[0])
                if n[2] <= 0:
                    continue
                q = uv[face]
                lo = np.maximum(np.floor(q.min(0)).astype(int), 0)
                hi = np.minimum(np.ceil(q.max(0)).astype(int), [w - 1, h - 1])
                if np.any(lo > hi):
                    continue
                e1, e2 = q[1] - q[0], q[2] - q[0]
                det = e1[0] * e2[1] - e1[1] * e2[0]
                if abs(det) < 1e-9:
                    continue
                yy, xx = np.mgrid[lo[1]:hi[1] + 1, lo[0]:hi[0] + 1]
                dx, dy = xx - q[0, 0], yy - q[0, 1]
                a = (dx * e2[1] - dy * e2[0]) / det
                b = (e1[0] * dy - e1[1] * dx) / det
                bary = np.stack((1 - a - b, a, b), -1)
                inside = bary.min(-1) >= -1e-4
                pos = bary @ p
                px = mw / 2 + (pos[..., 0] - centre_x) / mpp
                py = mh / 2 - (pos[..., 1] - centre_y) / mpp
                vals = np.stack([map_coordinates(mask_src[..., c], [py, px], order=1, mode='constant')
                                 for c in range(3)], -1)
                out[yy[inside], xx[inside]] = np.maximum(out[yy[inside], xx[inside]], vals[inside])
                occupied[yy[inside], xx[inside]] = True
    for c in range(3):
        pad = maximum_filter(out[..., c], size=5)
        out[..., c][~occupied] = pad[~occupied]
    return (np.clip(out, 0, 1) * 255).round().astype(np.uint8), {
        'atlas': [w, h], 'texels': {k: int((out[..., i] > 0.1).sum()) for i, k in enumerate('RGB')}}


def _sha256(path: Path) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def manifest_entry(body: Path, mask: Path) -> dict:
    """The face_masks/manifest.json entry for a baked mask, from the files themselves.

    Same fields as build_face_masks.py writes for the other races; the pixel
    counts are taken from the saved mask, so re-deriving an entry from the
    installed files gives the bake's own numbers.
    """
    gltf, blob = g.read(body)
    meshes = {gltf['meshes'][n['mesh']]['name']: gltf['meshes'][n['mesh']] for n in gltf['nodes'] if 'mesh' in n}
    material = meshes['body']['primitives'][0]['material']
    pixels = np.asarray(Image.open(mask).convert('RGB')).astype(np.float32) / 255.0
    w, h = atlas_size(gltf, blob, material)
    if pixels.shape[:2] != (h, w):
        raise ValueError(f'{mask} is {pixels.shape[1]}x{pixels.shape[0]}, the body atlas is {w}x{h}')
    return {
        'modelSHA256': _sha256(body),
        'maskSHA256': _sha256(mask),
        'sourceMaterial': material,
        'size': [w, h],
        'pixelsPerChannel': (pixels > 0.1).sum((0, 1)).tolist(),
        'sourceUVGroups': {part: {'uvScale': [1.0, 1.0], 'uvOffset': [0.0, 0.0]}
                           for part in PARTS if part in meshes},
    }


def write_manifest_entry(manifest: Path, slug: str, entry: dict) -> None:
    """Replace (or add) one race's entry, keeping every other entry and the key order."""
    data = json.loads(manifest.read_text(encoding='utf-8')) if manifest.exists() else {}
    data[slug] = entry
    with open(manifest, 'w', encoding='utf-8', newline='\n') as handle:
        handle.write(json.dumps(data, indent=2) + '\n')


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('body', type=Path)
    ap.add_argument('front', type=Path)
    ap.add_argument('out', type=Path)
    ap.add_argument('--centre-x', type=float, default=0.0)
    ap.add_argument('--centre-y', type=float, required=True)
    ap.add_argument('--metres-per-pixel', type=float, required=True)
    ap.add_argument('--manifest', type=Path, help='face_masks/manifest.json to write this mask\'s entry into')
    ap.add_argument('--slug', help='manifest key (default: the body file\'s stem, e.g. luminous_male)')
    args = ap.parse_args()
    pixels, report = bake(args.body, args.front, args.centre_x, args.centre_y, args.metres_per_pixel)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    Image.fromarray(pixels).save(args.out, optimize=True)
    if args.manifest:
        slug = args.slug or args.body.stem
        write_manifest_entry(args.manifest, slug, manifest_entry(args.body, args.out))
        report['manifest'] = {'path': str(args.manifest), 'slug': slug}
    print(json.dumps(report))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
