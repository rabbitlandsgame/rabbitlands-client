"""Small GLB animation editor preserving the source binary payload.

Transforms use glTF's Y-up coordinates, column vectors and xyzw quaternions.
The source reader/writer conventions follow the project's existing glbkit.
"""
from __future__ import annotations
import copy
import hashlib
import json
import struct
from pathlib import Path

import numpy as np
from scipy.spatial.transform import Rotation, Slerp

DTYPES = {5120: 'i1', 5121: 'u1', 5122: 'i2', 5123: 'u2', 5125: 'u4', 5126: 'f4'}
COUNTS = {'SCALAR': 1, 'VEC2': 2, 'VEC3': 3, 'VEC4': 4, 'MAT4': 16}


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def read_glb(path):
    data = Path(path).read_bytes()
    if struct.unpack_from('<III', data) != (0x46546C67, 2, len(data)):
        raise ValueError('Invalid GLB header')
    offset, document, blob = 12, None, b''
    while offset < len(data):
        length, kind = struct.unpack_from('<II', data, offset)
        value = data[offset + 8:offset + 8 + length]
        if kind == 0x4E4F534A:
            document = json.loads(value)
        elif kind == 0x004E4942:
            blob = value
        offset += 8 + length
    if document is None or len(document.get('buffers', [])) != 1:
        raise ValueError('A self-contained single-buffer GLB is required')
    if document['buffers'][0].get('uri'):
        raise ValueError('External buffers are not supported')
    return document, blob


def accessor(document, blob, index):
    spec = document['accessors'][index]
    if spec.get('sparse'):
        raise ValueError('Sparse accessors need explicit expansion before fitting')
    count, width = spec['count'], COUNTS[spec['type']]
    dtype = np.dtype('<' + DTYPES[spec['componentType']])
    if 'bufferView' not in spec:
        result = np.zeros((count, width), dtype=float)
    else:
        view = document['bufferViews'][spec['bufferView']]
        if view.get('buffer', 0) != 0:
            raise ValueError('External buffer view')
        offset = view.get('byteOffset', 0) + spec.get('byteOffset', 0)
        stride = view.get('byteStride', width * dtype.itemsize)
        result = np.ndarray((count, width), dtype=dtype, buffer=blob,
                            offset=offset, strides=(stride, dtype.itemsize)).astype(float)
    if spec.get('normalized') and spec['componentType'] != 5126:
        limits = np.iinfo(dtype)
        result = np.maximum(result / limits.max, -1) if limits.min < 0 else result / limits.max
    return result


def rotation_matrix(quaternion):
    return Rotation.from_quat(quaternion).as_matrix()


def write_glb(path, document, blob):
    document['buffers'][0]['byteLength'] = len(blob)
    text = json.dumps(document, separators=(',', ':')).encode('utf-8')
    text += b' ' * (-len(text) % 4)
    blob = bytes(blob) + b'\0' * (-len(blob) % 4)
    body = struct.pack('<II', len(text), 0x4E4F534A) + text
    body += struct.pack('<II', len(blob), 0x004E4942) + blob
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    Path(path).write_bytes(struct.pack('<III', 0x46546C67, 2, 12 + len(body)) + body)


class Asset:
    def __init__(self, path):
        self.path = Path(path)
        self.document, self.blob = read_glb(path)
        nodes = self.document['nodes']
        self.n = len(nodes)
        self.names = [n.get('name', f'node_{i}') for i, n in enumerate(nodes)]
        self.name_to_ids = {}
        for i,name in enumerate(self.names):self.name_to_ids.setdefault(name,[]).append(i)
        # Preserve names, including accessory rigs reusing generic names.
        # Ambiguous names cannot resolve a role; profiles must use node IDs.
        self.name_to_id = {name:ids[0] for name,ids in self.name_to_ids.items() if len(ids)==1}
        self.parent = np.full(self.n, -1, dtype=int)
        for i, node in enumerate(nodes):
            for child in node.get('children', []):
                self.parent[child] = i
        self.order = []
        def visit(i):
            if i in self.order:
                return
            if self.parent[i] >= 0:
                visit(int(self.parent[i]))
            self.order.append(i)
        for i in range(self.n):
            visit(i)
        self.t = np.asarray([n.get('translation', [0, 0, 0]) for n in nodes], float)
        self.q = np.asarray([n.get('rotation', [0, 0, 0, 1]) for n in nodes], float)
        self.s = np.asarray([n.get('scale', [1, 1, 1]) for n in nodes], float)
        for i, node in enumerate(nodes):
            if 'matrix' in node:
                matrix = np.asarray(node['matrix']).reshape(4, 4).T
                self.t[i] = matrix[:3, 3]
                self.s[i] = np.linalg.norm(matrix[:3, :3], axis=0)
                self.q[i] = Rotation.from_matrix(matrix[:3, :3] / self.s[i]).as_quat()
                if not np.allclose(rotation_matrix(self.q[i]) * self.s[i], matrix[:3, :3]):
                    raise ValueError('Sheared rest matrices are not supported')
        self.world_rest = self.world(self.t, self.q)
        self.joints = {i for skin in self.document.get('skins', []) for i in skin['joints']}
        self.parts = []
        for node_id, node in enumerate(nodes):
            if 'mesh' not in node:
                continue
            for primitive in self.document['meshes'][node['mesh']]['primitives']:
                if primitive.get('mode', 4) != 4:
                    raise ValueError('Only triangle meshes are supported')
                if primitive.get('targets') or node.get('weights'):
                    raise ValueError('Active morph geometry requires a morph-aware fitting profile')
                attrs = primitive['attributes']
                positions = accessor(self.document, self.blob, attrs['POSITION'])
                part = {'node': node_id, 'position': np.c_[positions, np.ones(len(positions))],
                        'indices': accessor(self.document, self.blob, primitive['indices']).astype(int).reshape(-1, 3)
                        if 'indices' in primitive else np.arange(len(positions)).reshape(-1, 3)}
                if 'skin' in node:
                    skin = self.document['skins'][node['skin']]
                    pairs = [k for k in range(8) if f'JOINTS_{k}' in attrs]
                    part['joints'] = np.concatenate([accessor(self.document, self.blob, attrs[f'JOINTS_{k}']).astype(int) for k in pairs], 1)
                    part['weights'] = np.concatenate([accessor(self.document, self.blob, attrs[f'WEIGHTS_{k}']) for k in pairs], 1)
                    if not np.allclose(part['weights'].sum(1), 1, atol=2e-4):
                        raise ValueError('Unnormalized source skin weights')
                    part['nodes'] = np.asarray(skin['joints'], int)
                    part['inverse_bind'] = accessor(self.document, self.blob, skin['inverseBindMatrices']).reshape(-1, 4, 4).transpose(0, 2, 1)
                self.parts.append(part)
        self.rest_vertices = self.skin(self.world_rest)
        self.height = float(np.ptp(self.rest_vertices[:, 1]))
        self.animations = {a.get('name'): a for a in self.document.get('animations', [])}

    def world(self, translations, quaternions):
        local = np.tile(np.eye(4), (self.n, 1, 1))
        local[:, :3, :3] = rotation_matrix(quaternions) * self.s[:, None, :]
        local[:, :3, 3] = translations
        world = np.empty_like(local)
        for i in self.order:
            world[i] = local[i] if self.parent[i] < 0 else world[self.parent[i]] @ local[i]
        return world

    def skin(self, world):
        parts = []
        for part in self.parts:
            if 'joints' not in part:
                positions = (world[part['node']] @ part['position'].T).T[:, :3]
            else:
                transforms = world[part['nodes']] @ part['inverse_bind']
                positions = np.zeros((len(part['position']), 3))
                for k in range(part['joints'].shape[1]):
                    positions += np.einsum('vab,vb->va', transforms[part['joints'][:, k], :3], part['position']) * part['weights'][:, k, None]
            parts.append(positions)
        return np.concatenate(parts)

    def sample(self, clip, times):
        times = np.asarray(times)
        translations = np.tile(self.t, (len(times), 1, 1))
        rotations = np.tile(self.q, (len(times), 1, 1))
        animation = self.animations[clip]
        for channel in animation['channels']:
            target = channel['target']
            sampler = animation['samplers'][channel['sampler']]
            ts = accessor(self.document, self.blob, sampler['input']).ravel()
            values = accessor(self.document, self.blob, sampler['output'])
            x = np.clip(times, ts[0], ts[-1])
            mode = sampler.get('interpolation', 'LINEAR')
            if mode not in ('LINEAR', 'STEP'):
                raise ValueError(f'Unsupported animation interpolation: {mode}')
            if len(ts) == 1:
                result = np.tile(values[0], (len(times), 1))
            elif mode == 'STEP':
                result = values[np.clip(np.searchsorted(ts, x, side='right') - 1, 0, len(ts) - 1)]
            elif target['path'] == 'rotation':
                result = Slerp(ts, Rotation.from_quat(values))(x).as_quat()
            else:
                result = np.array([np.interp(x, ts, values[:, k]) for k in range(values.shape[1])]).T
            if target['path'] == 'translation':
                translations[:, target['node']] = result
            elif target['path'] == 'rotation':
                rotations[:, target['node']] = result
            elif target['path'] == 'scale' and not np.allclose(result, self.s[target['node']]):
                raise ValueError('Animated scales are not supported by this pilot')
            elif target['path'] == 'weights':
                raise ValueError('Morph animation requires a morph-aware profile')
        return translations, rotations

    def duration(self, clip):
        return max(accessor(self.document, self.blob, s['input']).ravel()[-1] for s in self.animations[clip]['samplers'])

    def export(self, path, clip, times, translations, quaternions, metadata):
        if Path(path).resolve() == self.path.resolve():
            raise ValueError('Animation export must not overwrite its source')
        document = copy.deepcopy(self.document)
        blob = bytearray(self.blob)
        def append(values, kind):
            values = np.ascontiguousarray(values, dtype='<f4')
            blob.extend(b'\0' * (-len(blob) % 4))
            offset = len(blob)
            blob.extend(values.tobytes())
            document['bufferViews'].append({'buffer': 0, 'byteOffset': offset, 'byteLength': values.nbytes})
            flat = values.reshape(len(values), -1)
            document['accessors'].append({'bufferView': len(document['bufferViews']) - 1,
                'componentType': 5126, 'count': len(values), 'type': kind,
                'min': flat.min(0).tolist(), 'max': flat.max(0).tolist()})
            return len(document['accessors']) - 1
        if np.any(np.diff(times) <= 0):
            raise ValueError('Export times must increase strictly')
        time_accessor = append(np.asarray(times)[:, None], 'SCALAR')
        animation = {'name': clip, 'samplers': [], 'channels': [], 'extras': metadata}
        for node in sorted(self.joints):
            for kind, values in [('translation', translations[:, node]), ('rotation', quaternions[:, node])]:
                values = values.copy()
                if kind == 'rotation':
                    values /= np.linalg.norm(values, axis=1, keepdims=True)
                    for i in range(1, len(values)):
                        if np.dot(values[i - 1], values[i]) < 0:
                            values[i] *= -1
                output = append(values, 'VEC4' if kind == 'rotation' else 'VEC3')
                animation['channels'].append({'sampler': len(animation['samplers']), 'target': {'node': node, 'path': kind}})
                animation['samplers'].append({'input': time_accessor, 'output': output, 'interpolation': 'LINEAR'})
        document['animations'] = [a for a in document.get('animations', []) if a.get('name') != clip] + [animation]
        write_glb(path, document, blob)
