"""Feather the prototype head's baked neck pigment to its retained body.

This offline stage changes only one existing embedded PNG. Geometry, skinning,
rig, animation, materials and every other image remain exact. The input GLB is
never overwritten. Color ratios are measured from the two skin maps near their
shared neck plane, then applied in linear RGB with a smooth zero-slope falloff.
"""
from __future__ import annotations

import argparse
import copy
import hashlib
import io
import json
from pathlib import Path
import struct

import numpy as np
from PIL import Image
from scipy.ndimage import map_coordinates
from scipy.spatial import cKDTree


DTYPES = {5120: 'i1', 5121: 'u1', 5122: '<i2', 5123: '<u2', 5125: '<u4', 5126: '<f4'}
COMPONENTS = {'SCALAR': 1, 'VEC2': 2, 'VEC3': 3, 'VEC4': 4, 'MAT2': 4, 'MAT3': 9, 'MAT4': 16}
PLANE = np.array([0., 1., .6])
PLANE_OFFSET = 1.5
PLANE_LENGTH = np.linalg.norm(PLANE)


def sha(data):
    return hashlib.sha256(data).hexdigest()


class Glb:
    def __init__(self, path):
        raw = Path(path).read_bytes()
        if struct.unpack_from('<4sI', raw) != (b'glTF', 2):
            raise ValueError('Expected a glTF2 binary file')
        length, kind = struct.unpack_from('<I4s', raw, 12)
        if kind != b'JSON':
            raise ValueError('Expected a JSON chunk')
        self.doc = json.loads(raw[20:20 + length])
        binary_length, binary_kind = struct.unpack_from('<I4s', raw, 20 + length)
        if binary_kind != b'BIN\0' or len(self.doc.get('buffers', [])) != 1:
            raise ValueError('Expected one embedded binary buffer')
        self.binary = raw[28 + length:28 + length + binary_length]

    def view(self, index):
        view = self.doc['bufferViews'][index]
        if view.get('buffer', 0) != 0:
            raise ValueError('External buffers are not supported')
        start = view.get('byteOffset', 0)
        return self.binary[start:start + view['byteLength']]

    def read(self, index):
        accessor = self.doc['accessors'][index]
        if accessor.get('sparse'):
            raise ValueError('Sparse accessors are not supported by this study stage')
        view = self.doc['bufferViews'][accessor['bufferView']]
        dtype = np.dtype(DTYPES[accessor['componentType']])
        columns = COMPONENTS[accessor['type']]
        result = np.ndarray((accessor['count'], columns), dtype=dtype, buffer=self.binary,
                            offset=view.get('byteOffset', 0) + accessor.get('byteOffset', 0),
                            strides=(view.get('byteStride', columns * dtype.itemsize), dtype.itemsize)).copy()
        return result[:, 0] if columns == 1 else result

    def image(self, primitive):
        material = self.doc['materials'][primitive['material']]['pbrMetallicRoughness']
        texture = self.doc['textures'][material['baseColorTexture']['index']]
        index = texture['source']
        image = self.doc['images'][index]
        data = self.view(image['bufferView'])
        factor = np.array(material.get('baseColorFactor', [1., 1., 1., 1.]))[:3]
        return index, Image.open(io.BytesIO(data)), factor

    def replace_image(self, image_index, png, destination):
        doc = copy.deepcopy(self.doc)
        selected = doc['images'][image_index]['bufferView']
        binary = bytearray()
        for index, view in enumerate(doc['bufferViews']):
            payload = png if index == selected else self.view(index)
            binary.extend(b'\0' * (-len(binary) % 4))
            view['byteOffset'], view['byteLength'] = len(binary), len(payload)
            binary.extend(payload)
        doc['buffers'][0]['byteLength'] = len(binary)
        binary.extend(b'\0' * (-len(binary) % 4))
        encoded = json.dumps(doc, separators=(',', ':')).encode()
        encoded += b' ' * (-len(encoded) % 4)
        raw = struct.pack('<4sII', b'glTF', 2, 28 + len(encoded) + len(binary))
        raw += struct.pack('<I4s', len(encoded), b'JSON') + encoded
        raw += struct.pack('<I4s', len(binary), b'BIN\0') + binary
        destination.write_bytes(raw)


def linear(rgb):
    return np.where(rgb <= .04045, rgb / 12.92, ((rgb + .055) / 1.055) ** 2.4)


def srgb(rgb):
    return np.where(rgb <= .0031308, rgb * 12.92, 1.055 * np.maximum(rgb, 0) ** (1 / 2.4) - .055)


def geometry(glb, primitive):
    attrs = primitive['attributes']
    return (glb.read(attrs['POSITION']), glb.read(attrs['NORMAL']),
            glb.read(attrs['TEXCOORD_0']), glb.read(primitive['indices']).reshape(-1, 3))


def sample_image(image, uv):
    pixels = np.asarray(image.convert('RGB'), dtype=np.float64) / 255
    # glTF UVs already use the image's top-left origin in this export.
    x, y = uv[:, 0] * image.width - .5, uv[:, 1] * image.height - .5
    return np.stack([map_coordinates(pixels[:, :, c], [y, x], order=1, mode='wrap') for c in range(3)], -1)


def seam_samples(glb, primitive):
    positions, normals, uv, triangles = geometry(glb, primitive)
    points = np.concatenate((positions, positions[triangles].mean(1)))
    directions = np.concatenate((normals, normals[triangles].mean(1)))
    coords = np.concatenate((uv, uv[triangles].mean(1)))
    plane_value = points @ PLANE - PLANE_OFFSET
    selected = ((abs(plane_value) < .012) & (abs(points[:, 0]) < .13) & (directions[:, 2] > .5))
    if selected.sum() < 10:
        raise ValueError('Not enough front-neck skin samples to derive a tone match')
    return coords[selected], int(selected.sum())


def raster_head_distance(positions, uv, triangles, size):
    field = np.full((size[1], size[0]), np.nan, dtype=np.float32)
    for tri in triangles:
        coords = uv[tri] * np.array(size) - .5
        x0, y0 = np.maximum(np.floor(coords.min(0)).astype(int), 0)
        x1, y1 = np.minimum(np.ceil(coords.max(0)).astype(int), np.array(size) - 1)
        a, b = coords[1] - coords[0], coords[2] - coords[0]
        det = a[0] * b[1] - a[1] * b[0]
        if abs(det) < 1e-9 or x1 < x0 or y1 < y0:
            continue
        yy, xx = np.mgrid[y0:y1 + 1, x0:x1 + 1]
        dx, dy = xx - coords[0, 0], yy - coords[0, 1]
        w1 = (dx * b[1] - dy * b[0]) / det
        w2 = (a[0] * dy - a[1] * dx) / det
        w0 = 1 - w1 - w2
        inside = (w0 >= -1e-6) & (w1 >= -1e-6) & (w2 >= -1e-6)
        distances = (positions[tri] @ PLANE - PLANE_OFFSET) / PLANE_LENGTH
        field[yy[inside], xx[inside]] = (w0[inside] * distances[0] +
                                        w1[inside] * distances[1] + w2[inside] * distances[2])
    return field


def boundary_normals(glb, head, body):
    samples = []
    for primitive in (head, body):
        vertices, normals, _, _ = geometry(glb, primitive)
        mask = ((abs(vertices @ PLANE - PLANE_OFFSET) < 1e-5) &
                (abs(vertices[:, 0]) < .13) & (normals[:, 2] > .5))
        samples.append((vertices[mask], normals[mask]))
    if not all(len(s[0]) for s in samples):
        return {'matched': False}
    distances, ids = cKDTree(samples[1][0]).query(samples[0][0])
    dots = np.einsum('ij,ij->i', samples[0][1], samples[1][1][ids])
    close = distances < .002
    return {'matched': True, 'head_boundary_samples': len(dots), 'pairs_within_2mm': int(close.sum()),
            'normal_dot_median': float(np.median(dots)), 'normal_dot_min': float(dots.min()),
            'normal_dot_min_within_2mm': float(dots[close].min()) if close.any() else None,
            'nearest_boundary_distance_mm_max': float(distances.max() * 1000),
            'limitation': 'Color baking cannot correct local source normal differences.'}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--input', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True, help='New GLB path, separate from input')
    parser.add_argument('--texture-output', type=Path, required=True)
    parser.add_argument('--receipt', type=Path, required=True)
    args = parser.parse_args()
    if args.input.resolve() == args.output.resolve():
        raise ValueError('Input must remain unchanged; use a new output stage')
    glb = Glb(args.input)
    head, body = glb.doc['meshes'][0]['primitives'][:2]
    head_index, image, head_factor = glb.image(head)
    _, body_image, body_factor = glb.image(body)
    head_uv, head_count = seam_samples(glb, head)
    body_uv, body_count = seam_samples(glb, body)
    head_rgb = sample_image(image, head_uv)
    body_rgb = sample_image(body_image, body_uv)
    source_median = np.median(linear(head_rgb) * head_factor, axis=0)
    target_median = np.median(linear(body_rgb) * body_factor, axis=0)
    ratio = target_median / np.maximum(source_median, 1e-5)
    if np.any((ratio < .5) | (ratio > 2)):
        raise ValueError('Skin tone ratio is too large for a subtle neck match')
    positions, _, uv, triangles = geometry(glb, head)
    distances = raster_head_distance(positions, uv, triangles, image.size)
    valid = np.isfinite(distances)
    amount = np.zeros_like(distances)
    t = np.clip((distances[valid] - .005) / (.06 - .005), 0, 1)
    amount[valid] = 1 - t * t * (3 - 2 * t)
    pixels = np.array(image)
    source = pixels[:, :, :3].astype(np.float64) / 255
    correction = 1 + (ratio[None, None, :] - 1) * amount[:, :, None]
    result = pixels.copy()
    result[:, :, :3] = np.rint(np.clip(srgb(linear(source) * correction), 0, 1) * 255).astype(np.uint8)
    protected = valid & (distances >= .06)
    changed = np.any(result[:, :, :3] != pixels[:, :, :3], axis=2)
    if changed[protected].any() or changed[amount == 0].any():
        raise ValueError('The tone change escaped its neck fade')
    args.texture_output.parent.mkdir(parents=True, exist_ok=True)
    Image.fromarray(result).save(args.texture_output, optimize=True)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    glb.replace_image(head_index, args.texture_output.read_bytes(), args.output)
    check = Glb(args.output)
    for key in ('nodes', 'skins', 'meshes', 'accessors', 'materials', 'textures', 'samplers', 'animations'):
        if glb.doc.get(key) != check.doc.get(key):
            raise ValueError(f'Unexpected structural change: {key}')
    for index in range(len(glb.doc['accessors'])):
        if not np.array_equal(glb.read(index), check.read(index)):
            raise ValueError(f'Changed accessor {index}')
    image_view = glb.doc['images'][head_index]['bufferView']
    for index in range(len(glb.doc['bufferViews'])):
        if index != image_view and glb.view(index) != check.view(index):
            raise ValueError(f'Unexpected binary change outside skin image: {index}')
    receipt = {'input': str(args.input.resolve()), 'input_sha256': sha(args.input.read_bytes()),
               'tool_sha256': sha(Path(__file__).read_bytes()), 'output': str(args.output.resolve()),
               'output_sha256': sha(args.output.read_bytes()), 'texture_sha256': sha(args.texture_output.read_bytes()),
               'disk_delta_bytes': args.output.stat().st_size - args.input.stat().st_size,
               'skin_image_index': head_index, 'source_seam_samples': head_count, 'target_seam_samples': body_count,
               'source_srgb_median_255': (srgb(source_median) * 255).tolist(),
               'target_srgb_median_255': (srgb(target_median) * 255).tolist(), 'linear_rgb_multiplier_at_seam': ratio.tolist(),
               'seam_plane': [0, 1, .6, -1.5], 'fade_orthogonal_distance_metres': [.005, .06],
               'changed_neck_texels': int(changed.sum()), 'protected_face_texels': int(protected.sum()),
               'protected_face_max_pixel_change': int(abs(result.astype(int) - pixels.astype(int))[protected].max()),
               'outside_neck_fade_changed_texels': int(changed[amount == 0].sum()),
               'geometry_accessors_exact': len(glb.doc['accessors']), 'all_other_buffer_views_exact': True,
               'rig_materials_and_animation_exact': True, 'normal_audit': boundary_normals(glb, head, body),
               'runtime_materials_added': 0, 'runtime_textures_added': 0, 'runtime_shader_operations_added': 0}
    args.receipt.parent.mkdir(parents=True, exist_ok=True)
    args.receipt.write_text(json.dumps(receipt, indent=2) + '\n')
    print(json.dumps(receipt, indent=2))


if __name__ == '__main__':
    main()
