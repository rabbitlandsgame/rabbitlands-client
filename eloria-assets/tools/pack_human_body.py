"""Pack a split T-pose body (tpose_bodies/surfaces.py output) into the shipped race-GLB layout.

    python eloria-assets/tools/pack_human_body.py <split.glb> <out.glb> [--size 2048]

The Human bodies regenerated on 2026-10-05 come out of rigged_races and
tpose_bodies/surfaces.py as one 4K colour atlas shared by the skin surfaces,
one greyscale copy shared by the tintable wardrobe surfaces, the clips the
rigger baked in, and (for some Meshy deliveries) normal and metallic maps.
The shipped race GLBs carry none of the extras: the client rebuilds clips from
the shared animation library and materials are base colour only.

This keeps every vertex, index, skin and node exactly as the split wrote them
and changes only what the client never reads or what it pays for in memory:

* drops the baked animations;
* drops normal / metallic-roughness / occlusion / emissive textures;
* resizes each remaining image to at most --size pixels (Lanczos) and stores
  it as RGB JPEG (the wardrobe greyscale atlas too: an L8 texture would
  render red-only once imported);
* names the armature root `BodyRoot`, as the shipped bodies do;
* points eyes, eyebrows and scalp at the skin's colour material (the face
  mask colours them per pixel; tinting their triangles painted eye patches);
* writes the race contract every shipped body carries (tag_race_contract):
  `asset.extras.sourceSHA256` (the split this was packed from, the value
  the catalogue's races.<slug>.sourceSHA256 pins) and
  `extras.sourceRole = "race_head"` on the body, eyes, eyebrows and scalp
  primitives, the surfaces the face mask is baked over and the face tests
  sample (faceAppearance.sourceSurface 0 is the body primitive).
"""
from __future__ import annotations

import argparse
import copy
import hashlib
import io
import json
import sys
from pathlib import Path

from PIL import Image

sys.path.insert(0, str(Path(__file__).parent / 'tpose_bodies' / 'vendor'))
import glbkit as g  # noqa: E402

DROP_TEXTURE_KEYS = ('normalTexture', 'occlusionTexture', 'emissiveTexture')
# The surfaces the face-appearance mask covers (bake_human_face_mask.PARTS).
HEAD_SURFACES = ('body', 'eyes', 'eyebrows', 'scalp')


def tag_race_contract(gltf: dict, source_sha256: str) -> None:
    """Write the JSON-only metadata the shipped race bodies carry.

    Touches no accessor, view, image or skin, so applying it to an already
    packed body changes the JSON chunk only.
    """
    meshes = {gltf['meshes'][n['mesh']]['name']: gltf['meshes'][n['mesh']]
              for n in gltf['nodes'] if 'mesh' in n}
    for part in HEAD_SURFACES:
        for prim in meshes.get(part, {}).get('primitives', []):
            prim.setdefault('extras', {})['sourceRole'] = 'race_head'
    gltf.setdefault('asset', {}).setdefault('extras', {})['sourceSHA256'] = source_sha256


def _image_bytes(gltf, blob, image):
    view = gltf['bufferViews'][image['bufferView']]
    start = view.get('byteOffset', 0)
    return bytes(blob[start:start + view['byteLength']])


def pack(source: Path, out: Path, size: int, quality: int = 92) -> dict:
    gltf, blob = g.read(source)
    gltf = copy.deepcopy(gltf)
    gltf.pop('animations', None)
    # Eyes and brows are coloured by the face-appearance mask, which samples
    # the surface's own atlas: they must carry the skin's colour atlas, not
    # the wardrobe's greyscale copy the splitter gave them.
    by_name = {gltf['meshes'][n['mesh']]['name']: gltf['meshes'][n['mesh']] for n in gltf['nodes'] if 'mesh' in n}
    skin_material = by_name['body']['primitives'][0]['material']
    for part in ('eyes', 'eyebrows', 'scalp'):
        if part in by_name:
            for prim in by_name[part]['primitives']:
                prim['material'] = skin_material
    used_textures = set()
    for material in gltf.get('materials', []):
        for key in DROP_TEXTURE_KEYS:
            material.pop(key, None)
        pbr = material.setdefault('pbrMetallicRoughness', {})
        pbr.pop('metallicRoughnessTexture', None)
        pbr['metallicFactor'] = 0.0
        pbr['roughnessFactor'] = max(float(pbr.get('roughnessFactor', 1.0)), 0.8)
        if 'baseColorTexture' in pbr:
            used_textures.add(pbr['baseColorTexture']['index'])
    # Re-index textures and images to the ones still referenced.
    tex_order = sorted(used_textures)
    tex_map = {old: new for new, old in enumerate(tex_order)}
    image_order = sorted({gltf['textures'][t]['source'] for t in tex_order})
    image_map = {old: new for new, old in enumerate(image_order)}
    for material in gltf.get('materials', []):
        pbr = material['pbrMetallicRoughness']
        if 'baseColorTexture' in pbr:
            pbr['baseColorTexture'] = {'index': tex_map[pbr['baseColorTexture']['index']]}
    textures = []
    for t in tex_order:
        entry = dict(gltf['textures'][t])
        entry['source'] = image_map[entry['source']]
        textures.append(entry)
    encoded = []
    for old in image_order:
        im = Image.open(io.BytesIO(_image_bytes(gltf, blob, gltf['images'][old]))).convert('RGB')
        if max(im.size) > size:
            scale = size / max(im.size)
            im = im.resize((round(im.width * scale), round(im.height * scale)), Image.LANCZOS)
        buf = io.BytesIO()
        im.save(buf, 'JPEG', quality=quality, optimize=True)
        encoded.append((gltf['images'][old].get('name') or f'atlas_{len(encoded)}', buf.getvalue(), im.size))
    # Rebuild the binary: every accessor view first, then the new images.
    new_blob = bytearray()
    view_map = {}
    used_views = sorted({a['bufferView'] for a in gltf.get('accessors', []) if 'bufferView' in a})
    views = []
    for old in used_views:
        view = dict(gltf['bufferViews'][old])
        data = bytes(blob[view.get('byteOffset', 0):view.get('byteOffset', 0) + view['byteLength']])
        while len(new_blob) % 4:
            new_blob.append(0)
        view['byteOffset'] = len(new_blob)
        new_blob += data
        view_map[old] = len(views)
        views.append(view)
    for accessor in gltf.get('accessors', []):
        if 'bufferView' in accessor:
            accessor['bufferView'] = view_map[accessor['bufferView']]
    images = []
    for name, data, _size in encoded:
        while len(new_blob) % 4:
            new_blob.append(0)
        views.append({'buffer': 0, 'byteOffset': len(new_blob), 'byteLength': len(data)})
        new_blob += data
        images.append({'name': name, 'mimeType': 'image/jpeg', 'bufferView': len(views) - 1})
    gltf['bufferViews'] = views
    gltf['images'] = images
    gltf['textures'] = textures
    gltf['buffers'] = [{'byteLength': len(new_blob)}]
    for index in gltf['scenes'][gltf.get('scene', 0)]['nodes']:
        node = gltf['nodes'][index]
        if 'children' in node and 'mesh' not in node:
            node['name'] = 'BodyRoot'
    source_sha256 = hashlib.sha256(source.read_bytes()).hexdigest()
    extras = gltf.setdefault('asset', {}).setdefault('extras', {})
    extras['eloriaHumanPack'] = {'version': 1, 'maxTexture': size, 'sourceSHA256': source_sha256}
    tag_race_contract(gltf, source_sha256)
    out.parent.mkdir(parents=True, exist_ok=True)
    g.write(out, gltf, bytes(new_blob))
    return {'out': str(out), 'bytes': out.stat().st_size,
            'images': [(n, s, len(d)) for n, d, s in encoded]}


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('source', type=Path)
    ap.add_argument('out', type=Path)
    ap.add_argument('--size', type=int, default=2048)
    args = ap.parse_args()
    if 'godot-client' in args.out.resolve().parts:
        raise SystemExit('write to scratch; installing into the client is a separate, reviewed step')
    print(json.dumps(pack(args.source, args.out, args.size), indent=1))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
