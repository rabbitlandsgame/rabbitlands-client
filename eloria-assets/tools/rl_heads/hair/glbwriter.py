"""Minimal glTF-binary writer used by the hair / beard builds (accessors incl. sparse
morph targets, materials, nodes, skins). Vendored copy of .local/rl-heads/scripts/glbw.py
(the RL head build writer) so this folder is self-contained.

Inverse-bind matrices are written column-major: numpy (column-vector) M -> M.T.reshape(16).
"""
import json, struct, numpy as np


class GLB:
    def __init__(self):
        self.g = {'asset': {'version': '2.0', 'generator': 'RL head build (MPFB hm08 derived)'},
                  'scenes': [{'nodes': []}], 'scene': 0, 'nodes': [], 'meshes': [], 'accessors': [],
                  'bufferViews': [], 'buffers': [{'byteLength': 0}], 'materials': [], 'skins': []}
        self.blob = bytearray()

    def _view(self, data: bytes, target=None):
        while len(self.blob) % 4:
            self.blob += b'\0'
        v = {'buffer': 0, 'byteOffset': len(self.blob), 'byteLength': len(data)}
        if target:
            v['target'] = target
        self.blob += data
        self.g['bufferViews'].append(v)
        return len(self.g['bufferViews']) - 1

    def accessor(self, arr, kind, comp=5126, target=None, minmax=False, normalized=False):
        arr = np.ascontiguousarray(arr)
        dt = {5126: np.float32, 5125: np.uint32, 5123: np.uint16, 5121: np.uint8}[comp]
        a = arr.astype(dt)
        bv = self._view(a.tobytes(), target)
        acc = {'bufferView': bv, 'componentType': comp, 'count': int(a.shape[0]), 'type': kind}
        if normalized:
            acc['normalized'] = True
        if minmax:
            flat = a.reshape(a.shape[0], -1)
            acc['min'] = [float(x) for x in flat.min(0)]
            acc['max'] = [float(x) for x in flat.max(0)]
        self.g['accessors'].append(acc)
        return len(self.g['accessors']) - 1

    def sparse_vec3(self, delta, eps=1e-7, minmax=False):
        """A VEC3 morph accessor stored sparsely (only rows that move)."""
        delta = np.asarray(delta, np.float32)
        idx = np.nonzero(np.abs(delta).max(1) > eps)[0].astype(np.uint32)
        acc = {'componentType': 5126, 'count': int(delta.shape[0]), 'type': 'VEC3'}
        if minmax:
            acc['min'] = [float(x) for x in (delta.min(0) if len(delta) else [0, 0, 0])]
            acc['max'] = [float(x) for x in (delta.max(0) if len(delta) else [0, 0, 0])]
        if len(idx):
            iv = self._view(idx.tobytes())
            vv = self._view(delta[idx].tobytes())
            acc['sparse'] = {'count': int(len(idx)), 'indices': {'bufferView': iv, 'componentType': 5125},
                             'values': {'bufferView': vv}}
        self.g['accessors'].append(acc)
        return len(self.g['accessors']) - 1

    def material(self, name, color=(1, 1, 1, 1), double=False, alpha=None, extras=None):
        m = {'name': name, 'pbrMetallicRoughness': {'baseColorFactor': list(color), 'metallicFactor': 0.0, 'roughnessFactor': 0.8}}
        if double:
            m['doubleSided'] = True
        if alpha:
            m['alphaMode'] = alpha
        if extras:
            m['extras'] = extras
        self.g['materials'].append(m)
        return len(self.g['materials']) - 1

    def node(self, **kw):
        self.g['nodes'].append(kw)
        return len(self.g['nodes']) - 1

    def save(self, path):
        while len(self.blob) % 4:
            self.blob += b'\0'
        self.g['buffers'][0]['byteLength'] = len(self.blob)
        if not self.g['skins']:
            del self.g['skins']
        if not self.g['materials']:
            del self.g['materials']
        js = json.dumps(self.g, separators=(',', ':')).encode()
        js += b' ' * ((4 - len(js) % 4) % 4)
        out = struct.pack('<III', 0x46546C67, 2, 12 + 8 + len(js) + 8 + len(self.blob))
        out += struct.pack('<II', len(js), 0x4E4F534A) + js
        out += struct.pack('<II', len(self.blob), 0x004E4942) + bytes(self.blob)
        open(path, 'wb').write(out)
        return len(out)
