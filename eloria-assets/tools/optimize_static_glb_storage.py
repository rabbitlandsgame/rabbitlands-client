"""Lossless raw storage changes for published static world-object GLBs.

No compression, vertex sharing, precision conversion or model generation.
Image pruning is opt-in and accounts for every declared material, including
variant materials and alternate texture sources. Index narrowing changes only
the scalar storage width, never vertex records or numeric index order.

The CLI stages candidates and recovery copies in a Git-ignored directory. It
never replaces input assets. Promote verified candidates before image
externalization, then refresh current asset hashes/provenance and native caches.
"""
from __future__ import annotations

import argparse
import copy
import hashlib
import json
from pathlib import Path
import subprocess

import numpy as np

import consolidate_map_vertices as GLB

SCHEMA = 'rabbitlands-static-glb-storage-v1'
REPO = Path(__file__).resolve().parents[2]
TEXTURE_SOURCES = {'KHR_texture_basisu', 'EXT_texture_webp', 'EXT_texture_avif', 'MSFT_texture_dds'}
SAFE_EXTENSIONS = TEXTURE_SOURCES | {
    'KHR_mesh_quantization', 'KHR_texture_transform', 'KHR_materials_variants',
    'KHR_materials_unlit', 'KHR_materials_emissive_strength', 'KHR_materials_clearcoat',
    'KHR_materials_transmission', 'KHR_materials_volume', 'KHR_materials_ior',
    'KHR_materials_specular', 'KHR_materials_sheen', 'KHR_materials_iridescence',
    'KHR_materials_anisotropy', 'KHR_materials_pbrSpecularGlossiness',
    'MSFT_packing_occlusionRoughnessMetallic', 'MSFT_packing_normalRoughnessMetallic',
}


class StorageError(ValueError):
    pass


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _json(value) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(',', ':'), allow_nan=False).encode()


def _index(value, size: int, label: str) -> int:
    if not isinstance(value, int) or isinstance(value, bool) or not 0 <= value < size:
        raise StorageError('invalid ' + label)
    return value


def _slots(value):
    if isinstance(value, dict):
        for key, child in value.items():
            if key.endswith('Texture') and isinstance(child, dict) and 'index' in child:
                yield child
            else:
                yield from _slots(child)
    elif isinstance(value, list):
        for child in value:
            yield from _slots(child)


def _extension_names(value) -> set[str]:
    if isinstance(value, dict):
        names = set(value.get('extensions', {}))
        return names | set().union(*(_extension_names(v) for v in value.values()), set())
    if isinstance(value, list):
        return set().union(*(_extension_names(v) for v in value), set())
    return set()


def _ambiguous_image_extras(value) -> bool:
    if isinstance(value, dict):
        extras = value.get('extras')
        if isinstance(extras, dict) and any(str(k).lower() in {
                'image', 'images', 'imageindex', 'image_index', 'texture', 'textures',
                'textureindex', 'texture_index'} for k in extras):
            return True
        return any(_ambiguous_image_extras(v) for v in value.values())
    return isinstance(value, list) and any(_ambiguous_image_extras(v) for v in value)


def _supported(d: dict, binary: bytes) -> str | None:
    buffers = d.get('buffers', [])
    if len(buffers) != 1 or 'uri' in buffers[0]:
        return 'external_or_multiple_buffers'
    if d.get('skins') or d.get('animations') or any(n.get('skin') is not None for n in d.get('nodes', [])):
        return 'deformation_or_animation'
    if any(p.get('targets') for m in d.get('meshes', []) for p in m['primitives']):
        return 'morph_targets'
    extensions = _extension_names(d) | set(d.get('extensionsUsed', [])) | set(d.get('extensionsRequired', []))
    if extensions - SAFE_EXTENSIONS:
        return 'unqualified_extension:' + ','.join(sorted(extensions - SAFE_EXTENSIONS))
    if any('sparse' in a for a in d.get('accessors', [])):
        return 'sparse_accessor'
    logical = buffers[0].get('byteLength')
    if not isinstance(logical, int) or logical < 0 or logical > len(binary) or len(binary) - logical > 3:
        raise StorageError('invalid binary length')
    covered = np.zeros(logical, np.bool_)
    for view in d.get('bufferViews', []):
        start, size = view.get('byteOffset', 0), view.get('byteLength', -1)
        if view.get('buffer', 0) != 0 or start < 0 or size < 0 or start + size > logical:
            raise StorageError('buffer view outside declared buffer')
        covered[start:start + size] = True
    if np.any(np.frombuffer(binary[:logical], np.uint8)[~covered]) or any(binary[logical:]):
        return 'unreferenced_nonzero_binary_payload'
    return None


def dependencies(d: dict) -> dict:
    """Conservative live image closure, not just the default primitive material."""
    textures = d.get('textures', [])
    images = d.get('images', [])
    materials = d.get('materials', [])
    used_textures = {_index(slot['index'], len(textures), 'material texture')
                     for material in materials for slot in _slots(material)}
    variants = set()
    for mesh in d.get('meshes', []):
        for primitive in mesh['primitives']:
            if 'material' in primitive:
                _index(primitive['material'], len(materials), 'primitive material')
            mappings = primitive.get('extensions', {}).get('KHR_materials_variants', {}).get('mappings', [])
            for mapping in mappings:
                variants.add(_index(mapping.get('material'), len(materials), 'variant material'))
    used_images = set()
    for i in used_textures:
        texture = textures[i]
        if 'source' in texture:
            used_images.add(_index(texture['source'], len(images), 'texture image'))
        for extension, value in texture.get('extensions', {}).items():
            if extension in TEXTURE_SOURCES and 'source' in value:
                used_images.add(_index(value['source'], len(images), 'alternate texture image'))
    return {'allMaterialCount': len(materials), 'variantMaterials': sorted(variants),
            'textures': sorted(used_textures), 'images': sorted(used_images)}


def _image(d: dict, binary: bytes, i: int) -> dict:
    image = copy.deepcopy(d['images'][i])
    if 'bufferView' in image:
        view = d['bufferViews'][image.pop('bufferView')]
        start = view.get('byteOffset', 0)
        data = binary[start:start + view['byteLength']]
        image['encodedSha256'] = sha(data)
        image['encodedBytes'] = len(data)
    return image


def _materials(d: dict, binary: bytes) -> list:
    def texture(i: int) -> dict:
        out = copy.deepcopy(d['textures'][i])
        if 'source' in out:
            out['source'] = _image(d, binary, out['source'])
        for extension, value in out.get('extensions', {}).items():
            if extension in TEXTURE_SOURCES and 'source' in value:
                value['source'] = _image(d, binary, value['source'])
        return out
    result = copy.deepcopy(d.get('materials', []))
    for material in result:
        for slot in _slots(material):
            slot['index'] = texture(slot['index'])
    return result


def verify_equivalent(before: bytes, after: bytes, *, removed_images: list[int],
                      narrowed_accessors: list[int]) -> dict:
    """Independent storage proof, including unused vertex records and variants."""
    left, lb = GLB.decode(before)
    right, rb = GLB.decode(after)
    closure = dependencies(left)
    if set(removed_images) & set(closure['images']):
        raise StorageError('removed an image reachable from a material or texture variant')
    if any(i not in range(len(left.get('images', []))) for i in removed_images):
        raise StorageError('removed image index outside source')
    structural = set(left) | set(right)
    structural -= {'accessors', 'bufferViews', 'buffers', 'images', 'textures', 'materials'}
    if any(left.get(k) != right.get(k) for k in structural):
        raise StorageError('scene, node, mesh, bounds or other metadata changed')
    if left.get('samplers', []) != right.get('samplers', []):
        raise StorageError('samplers changed')
    if _materials(left, lb) != _materials(right, rb):
        raise StorageError('material or texture/variant image content changed')
    kept = [i for i in range(len(left.get('images', []))) if i not in removed_images]
    if [_image(left, lb, i) for i in kept] != [_image(right, rb, i) for i in range(len(right.get('images', [])))]:
        raise StorageError('retained image order, metadata or encoded pixels changed')
    if len(left.get('accessors', [])) != len(right.get('accessors', [])):
        raise StorageError('accessor identities changed')
    digest = hashlib.sha256()
    for i, (a, b) in enumerate(zip(left.get('accessors', []), right.get('accessors', []))):
        am = {k: v for k, v in a.items() if k not in {'bufferView', 'byteOffset'}}
        bm = {k: v for k, v in b.items() if k not in {'bufferView', 'byteOffset'}}
        av, bv = GLB.accessor(left, lb, i), GLB.accessor(right, rb, i)
        if i in narrowed_accessors:
            if am.get('componentType') != 5125 or bm.get('componentType') != 5123:
                raise StorageError('unexpected index width change')
            am.pop('componentType'); bm.pop('componentType')
            if not np.array_equal(av, bv):
                raise StorageError('numeric index values/order changed')
        elif av.tobytes() != bv.tobytes():
            raise StorageError('vertex or other accessor records changed')
        if am != bm:
            raise StorageError('accessor bounds or component contract changed')
        digest.update(av.tobytes())
    triangles = sum((left['accessors'][p['indices']]['count'] if 'indices' in p else
                     left['accessors'][p['attributes']['POSITION']]['count']) // 3
                    for m in left.get('meshes', []) for p in m['primitives'] if p.get('mode', 4) == 4)
    return {'triangles': triangles, 'allAccessorRecordsSha256': digest.hexdigest(),
            'vertexRecordsUnchanged': True, 'numericIndexOrderUnchanged': True,
            'sceneMaterialBoundsUnchanged': True, 'retainedImagesByteIdentical': True,
            'dependencyProof': closure}


def optimize(data: bytes, *, prune_unused_images: bool = False, narrow_indices: bool = True) -> dict:
    d, binary = GLB.decode(data)
    reason = _supported(d, binary)
    if reason:
        return {'status': 'skipped', 'reason': reason}
    if prune_unused_images and _ambiguous_image_extras(d):
        return {'status': 'skipped', 'reason': 'unqualified_image_or_texture_extras'}
    source = copy.deepcopy(d)
    closure = dependencies(d)
    removed_images = []
    removed_views = set()
    texture_map = {i: i for i in range(len(d.get('textures', [])))}
    image_map = {i: i for i in range(len(d.get('images', [])))}
    if prune_unused_images:
        kept_images = closure['images']
        removed_images = sorted(set(range(len(d.get('images', [])))) - set(kept_images))
        image_map = {old: new for new, old in enumerate(kept_images)}
        texture_map = {old: new for new, old in enumerate(closure['textures'])}
        for i in removed_images:
            if 'bufferView' in d['images'][i]: removed_views.add(d['images'][i]['bufferView'])
        d['images'] = [d['images'][i] for i in kept_images]
        d['textures'] = [d['textures'][i] for i in closure['textures']]
        for texture in d['textures']:
            if 'source' in texture: texture['source'] = image_map[texture['source']]
            for extension, value in texture.get('extensions', {}).items():
                if extension in TEXTURE_SOURCES and 'source' in value: value['source'] = image_map[value['source']]
        for material in d.get('materials', []):
            for slot in _slots(material): slot['index'] = texture_map[slot['index']]
        for key in ('images', 'textures'):
            if not d[key]: d.pop(key)
    body = bytearray(binary)
    narrowed = []
    candidates = {p['indices'] for m in d.get('meshes', []) for p in m['primitives'] if 'indices' in p}
    vertex_accessors = {i for m in d.get('meshes', []) for p in m['primitives'] for i in p['attributes'].values()}
    for i in sorted(candidates) if narrow_indices else []:
        a = d['accessors'][i]
        if i in vertex_accessors or a.get('componentType') != 5125 or a.get('type') != 'SCALAR' or a.get('normalized', False): continue
        values = GLB.accessor(source, binary, i)
        # glTF reserves the all-ones value for primitive restart.
        if not values.size or int(values.max()) >= 65535: continue
        old_view = a['bufferView']
        removed_views.add(old_view)
        body.extend(b'\0' * (-len(body) % 4))
        payload = values.astype('<u2').tobytes()
        view = copy.deepcopy(d['bufferViews'][old_view])
        view.update(buffer=0, byteOffset=len(body), byteLength=len(payload), target=34963)
        view.pop('byteStride', None)
        d['bufferViews'].append(view)
        body.extend(payload)
        a.update(bufferView=len(d['bufferViews']) - 1, componentType=5123)
        a.pop('byteOffset', None)
        narrowed.append(i)
    if not removed_images and not narrowed:
        return {'status': 'unchanged', 'reason': 'no_eligible_storage_change'}
    used_views = {a['bufferView'] for a in d.get('accessors', []) if 'bufferView' in a}
    used_views |= {image['bufferView'] for image in d.get('images', []) if 'bufferView' in image}
    keep = [i for i in range(len(d.get('bufferViews', []))) if i not in removed_views or i in used_views]
    view_map = {old: new for new, old in enumerate(keep)}
    packed = bytearray(); aliases = {}
    for i in keep:
        view = d['bufferViews'][i]; key = (view.get('byteOffset', 0), view['byteLength'])
        if key not in aliases:
            packed.extend(b'\0' * (-len(packed) % 4)); aliases[key] = len(packed)
            packed.extend(body[key[0]:key[0] + key[1]])
        view.update(buffer=0, byteOffset=aliases[key])
    d['bufferViews'] = [d['bufferViews'][i] for i in keep]
    for a in d.get('accessors', []):
        if 'bufferView' in a: a['bufferView'] = view_map[a['bufferView']]
    for image in d.get('images', []):
        if 'bufferView' in image: image['bufferView'] = view_map[image['bufferView']]
    packed.extend(b'\0' * (-len(packed) % 4)); d['buffers'][0]['byteLength'] = len(packed)
    after = GLB.encode(d, bytes(packed))
    proof = verify_equivalent(data, after, removed_images=removed_images, narrowed_accessors=narrowed)
    if len(after) >= len(data):
        return {'status': 'unchanged', 'reason': 'container_not_smaller'}
    return {'status': 'changed', 'data': after, 'oldBytes': len(data), 'newBytes': len(after),
            'savedBytes': len(data) - len(after), 'removedImages': removed_images,
            'imageIndexMap': image_map, 'textureIndexMap': texture_map, 'narrowedAccessors': narrowed,
            'bufferViewIndexMap': view_map,
            'removedBufferViews': sorted(set(range(len(source.get('bufferViews', [])))) - set(keep)),
            'removedImageRecords': [{'index': i, **_image(source, binary, i)} for i in removed_images], 'proof': proof}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('paths', nargs='+', type=Path)
    parser.add_argument('--prune-images-for', action='append', type=Path, default=[])
    parser.add_argument('--stage', type=Path, help='new ignored stage/recovery directory; default is report only')
    args = parser.parse_args()
    files = sorted({p.resolve() for raw in args.paths for p in (raw.rglob('*.glb') if raw.is_dir() else [raw])})
    pruning = {p.resolve() for p in args.prune_images_for}
    if pruning - set(files): parser.error('image pruning targets must be explicitly included in paths')
    if args.stage:
        args.stage = args.stage.resolve()
        relative = args.stage.relative_to(REPO)
        if args.stage.exists(): parser.error('use a fresh ignored stage directory')
        if subprocess.run(['git', 'check-ignore', '-q', '--', relative.as_posix() + '/'], cwd=REPO).returncode:
            parser.error('stage must be Git-ignored')
        args.stage.mkdir(parents=True)
    records = []
    for path in files:
        relative = path.relative_to(REPO).as_posix(); before = path.read_bytes()
        result = optimize(before, prune_unused_images=path in pruning)
        row = {'path': relative, 'oldSha256': sha(before), **{k: v for k, v in result.items() if k != 'data'}}
        if result['status'] == 'changed':
            row['sha256'] = sha(result['data'])
            if args.stage:
                for folder, payload in [('recovery', before), ('staged', result['data'])]:
                    target = args.stage / folder / relative; target.parent.mkdir(parents=True, exist_ok=True)
                    target.write_bytes(payload)
                    if target.read_bytes() != payload: raise StorageError('staged write differs')
        records.append(row)
    report = {'schema': SCHEMA, 'sourceCommit': subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=REPO, text=True).strip(),
              'toolSha256': sha(Path(__file__).read_bytes()), 'files': records,
              'savedBytes': sum(r.get('savedBytes', 0) for r in records)}
    if args.stage: (args.stage / 'receipt.json').write_text(json.dumps(report, indent=2) + '\n', encoding='utf8', newline='\n')
    print(json.dumps({'files': len(records), 'changed': sum(r['status'] == 'changed' for r in records), 'savedBytes': report['savedBytes']}))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
