"""Minimal, self-contained glTF 2.0 (.glb / .gltf) reader and GLB writer.

Reader: every triangle primitive of every mesh instance in the default scene,
node transforms applied (world space of the file), with TEXCOORD_n of the base
colour texture, COLOR_0, the decoded base-colour image (float32 sRGB 0..1) and
the baseColorFactor. Sparse accessors, normalized integers, byteStride,
triangle strips/fans, KHR_texture_transform and data-URI / external buffers are
handled. Draco / meshopt compressed files are rejected with a clear message.
Skinned primitives keep their bind-pose positions (glTF ignores the node
transform of a skinned mesh node).

Writer: one node + mesh + material per part (positions, optional normals, UVs,
COLOR_0, embedded PNG texture), an optional node matrix. Used by the self-test.
"""
import os, io, json, struct, base64
import numpy as np
from PIL import Image

COMPONENT = {5120: np.int8, 5121: np.uint8, 5122: np.int16, 5123: np.uint16, 5125: np.uint32, 5126: np.float32}
NCOMP = {'SCALAR': 1, 'VEC2': 2, 'VEC3': 3, 'VEC4': 4, 'MAT2': 4, 'MAT3': 9, 'MAT4': 16}
NORM_DIV = {5120: 127.0, 5121: 255.0, 5122: 32767.0, 5123: 65535.0}


class GltfError(RuntimeError):
    pass


def _read_container(path):
    data = open(path, 'rb').read()
    if data[:4] == b'glTF':
        off = 12; gj = None; blob = b''
        while off < len(data):
            ln, ty = struct.unpack_from('<II', data, off)
            chunk = data[off + 8: off + 8 + ln]
            if ty == 0x4E4F534A:
                gj = json.loads(chunk.decode('utf-8'))
            elif ty == 0x004E4942:
                blob = chunk
            off += 8 + ln
            off += (-off) % 4
        if gj is None:
            raise GltfError('no JSON chunk')
        return gj, blob
    return json.loads(data.decode('utf-8')), None


def _buffers(g, blob, base_dir):
    out = []
    for i, b in enumerate(g.get('buffers', [])):
        uri = b.get('uri')
        if uri is None:
            out.append(blob if blob is not None else b'')
        elif uri.startswith('data:'):
            out.append(base64.b64decode(uri.split(',', 1)[1]))
        else:
            out.append(open(os.path.join(base_dir, uri), 'rb').read())
    return out


def _view_bytes(g, bufs, vi):
    v = g['bufferViews'][vi]
    b = bufs[v.get('buffer', 0)]
    o = v.get('byteOffset', 0)
    return b, o, v.get('byteStride'), v.get('byteLength', 0)


def _typed(g, bufs, vi, dtype, count, ncomp, byte_offset=0):
    b, o, stride, _ = _view_bytes(g, bufs, vi)
    item = np.dtype(dtype).itemsize
    start = o + byte_offset
    if not stride or stride == item * ncomp:
        return np.frombuffer(b, dtype=dtype, count=count * ncomp, offset=start).reshape(count, ncomp)
    raw = np.frombuffer(b, dtype=np.uint8, count=(count - 1) * stride + item * ncomp, offset=start)
    rows = np.lib.stride_tricks.as_strided(raw, shape=(count, item * ncomp), strides=(stride, 1))
    return np.ascontiguousarray(rows).view(dtype).reshape(count, ncomp)


def accessor(g, bufs, index, normalize=True):
    acc = g['accessors'][index]
    n = NCOMP[acc['type']]; ct = acc['componentType']; dt = COMPONENT[ct]
    if 'bufferView' in acc:
        out = _typed(g, bufs, acc['bufferView'], dt, acc['count'], n, acc.get('byteOffset', 0)).astype(np.float64)
    else:
        out = np.zeros((acc['count'], n))
    sp = acc.get('sparse')
    if sp:
        idx = _typed(g, bufs, sp['indices']['bufferView'], COMPONENT[sp['indices']['componentType']], sp['count'], 1,
                     sp['indices'].get('byteOffset', 0)).ravel().astype(np.int64)
        val = _typed(g, bufs, sp['values']['bufferView'], dt, sp['count'], n,
                     sp['values'].get('byteOffset', 0)).astype(np.float64)
        out = out.copy(); out[idx] = val
    if normalize and acc.get('normalized') and ct in NORM_DIV:
        out = np.maximum(out / NORM_DIV[ct], -1.0)
    return out


def _quat_matrix(q):
    x, y, z, w = q
    return np.array([[1 - 2 * (y * y + z * z), 2 * (x * y - z * w), 2 * (x * z + y * w)],
                     [2 * (x * y + z * w), 1 - 2 * (x * x + z * z), 2 * (y * z - x * w)],
                     [2 * (x * z - y * w), 2 * (y * z + x * w), 1 - 2 * (x * x + y * y)]])


def node_matrix(nd):
    if 'matrix' in nd:
        return np.array(nd['matrix'], np.float64).reshape(4, 4).T
    M = np.eye(4)
    S = np.diag(nd.get('scale', [1, 1, 1]))
    R = _quat_matrix(nd.get('rotation', [0, 0, 0, 1]))
    M[:3, :3] = R @ S
    M[:3, 3] = nd.get('translation', [0, 0, 0])
    return M


def world_matrices(g):
    nodes = g.get('nodes', [])
    scenes = g.get('scenes', [])
    if scenes:
        si = g.get('scene', 0)
        roots = list(scenes[si].get('nodes', []))
    else:
        child = {c for nd in nodes for c in nd.get('children', [])}
        roots = [i for i in range(len(nodes)) if i not in child]
    out = {}
    stack = [(r, np.eye(4)) for r in roots]
    while stack:
        i, Mp = stack.pop()
        W = Mp @ node_matrix(nodes[i])
        out[i] = W
        for c in nodes[i].get('children', []):
            stack.append((c, W))
    return out


def _image(g, bufs, base_dir, ii):
    im = g['images'][ii]
    if 'bufferView' in im:
        b, o, _, ln = _view_bytes(g, bufs, im['bufferView'])
        data = bytes(b[o:o + ln])
    elif im.get('uri', '').startswith('data:'):
        data = base64.b64decode(im['uri'].split(',', 1)[1])
    else:
        data = open(os.path.join(base_dir, im['uri']), 'rb').read()
    img = Image.open(io.BytesIO(data))
    img.load()
    return img


def _tex_transform(uv, info):
    ext = (info or {}).get('extensions', {}).get('KHR_texture_transform')
    if not ext:
        return uv
    off = np.array(ext.get('offset', [0, 0])); rot = float(ext.get('rotation', 0)); sc = np.array(ext.get('scale', [1, 1]))
    c, s = np.cos(rot), np.sin(rot)
    M = np.array([[c, s], [-s, c]]) * sc[None, :]
    return uv @ M.T + off


def read(path, want_texture=True):
    """Parts of a glTF file: list of dicts (name, V world (n,3), F (m,3), UV (n,2) or None,
    vcol (n,3) sRGB or None, tex (H,W,3) float32 sRGB or None, factor (4,), skinned)."""
    base_dir = os.path.dirname(os.path.abspath(path))
    g, blob = _read_container(path)
    for ext in g.get('extensionsRequired', []):
        if ext in ('KHR_draco_mesh_compression', 'EXT_meshopt_compression', 'KHR_mesh_quantization'):
            raise GltfError(f'{os.path.basename(path)} needs {ext}, which this reader does not decode; '
                            're-export the GLB uncompressed (e.g. Blender: Import, then Export glTF without compression)')
    bufs = _buffers(g, blob, base_dir)
    Wm = world_matrices(g)
    tex_cache = {}
    parts = []
    for ni, W in Wm.items():
        nd = g['nodes'][ni]
        if 'mesh' not in nd:
            continue
        mesh = g['meshes'][nd['mesh']]
        skinned = 'skin' in nd
        for pi, prim in enumerate(mesh['primitives']):
            mode = prim.get('mode', 4)
            if mode not in (4, 5, 6):
                continue
            at = prim['attributes']
            if 'POSITION' not in at:
                continue
            V = accessor(g, bufs, at['POSITION'])
            n = len(V)
            if 'indices' in prim:
                idx = accessor(g, bufs, prim['indices'], normalize=False).ravel().astype(np.int64)
            else:
                idx = np.arange(n)
            if mode == 4:
                F = idx[: len(idx) // 3 * 3].reshape(-1, 3)
            elif mode == 5:
                k = np.arange(len(idx) - 2)
                F = np.stack([idx[k], idx[k + 1 + (k % 2)], idx[k + 2 - (k % 2)]], 1)
            else:
                k = np.arange(1, len(idx) - 1)
                F = np.stack([np.full(len(k), idx[0]), idx[k], idx[k + 1]], 1)
            F = F[(F[:, 0] != F[:, 1]) & (F[:, 1] != F[:, 2]) & (F[:, 0] != F[:, 2])]
            if not skinned:
                V = V @ W[:3, :3].T + W[:3, 3]
                if np.linalg.det(W[:3, :3]) < 0:
                    F = F[:, [0, 2, 1]]
            mat = g['materials'][prim['material']] if 'material' in prim and g.get('materials') else {}
            pbr = mat.get('pbrMetallicRoughness', {})
            factor = np.array(pbr.get('baseColorFactor', [1, 1, 1, 1]), np.float64)
            info = pbr.get('baseColorTexture')
            UV = None; tex = None
            if info is not None and want_texture:
                tc = f"TEXCOORD_{info.get('texCoord', 0)}"
                if tc in at:
                    UV = _tex_transform(accessor(g, bufs, at[tc]), info)
                    ti = info['index']
                    if ti not in tex_cache:
                        t = g['textures'][ti]
                        src = t.get('source')
                        for e in ('EXT_texture_webp', 'KHR_texture_basisu', 'MSFT_texture_dds'):
                            if src is None and e in t.get('extensions', {}):
                                src = t['extensions'][e].get('source')
                        try:
                            img = _image(g, bufs, base_dir, src)
                            tex_cache[ti] = np.asarray(img.convert('RGB'), np.float32) / 255.0
                        except Exception as ex:  # undecodable image: fall back to factor / vertex colour
                            tex_cache[ti] = None
                    tex = tex_cache[ti]
            vcol = None
            if 'COLOR_0' in at:
                c = accessor(g, bufs, at['COLOR_0'])
                # glTF COLOR_0 is linear; convert to sRGB like a texture sample
                from fitcommon import linear_to_srgb
                vcol = linear_to_srgb(c[:, :3])
            parts.append({'name': f"{mesh.get('name', 'mesh')}[{pi}]", 'V': V, 'F': F, 'UV': UV, 'tex': tex,
                          'vcol': vcol, 'factor': factor, 'skinned': skinned, 'node': ni})
    if not parts:
        raise GltfError(f'{path}: no triangle meshes in the default scene')
    return parts


def read_any(path):
    """glTF via read(); other formats through trimesh (geometry + colours when present)."""
    ext = os.path.splitext(path)[1].lower()
    if ext in ('.glb', '.gltf'):
        return read(path)
    import trimesh
    sc = trimesh.load(path, force='scene', process=False)
    parts = []
    for node in sc.graph.nodes_geometry:
        M, gname = sc.graph[node]
        m = sc.geometry[gname]
        V = np.asarray(m.vertices, np.float64) @ M[:3, :3].T + M[:3, 3]
        UV = None; tex = None; vcol = None
        vis = m.visual
        if getattr(vis, 'kind', None) == 'texture' and getattr(vis, 'uv', None) is not None:
            UV = np.asarray(vis.uv, np.float64).copy(); UV[:, 1] = 1 - UV[:, 1]
            img = getattr(vis.material, 'image', None) or getattr(vis.material, 'baseColorTexture', None)
            if img is not None:
                tex = np.asarray(img.convert('RGB'), np.float32) / 255.0
        elif getattr(vis, 'kind', None) == 'vertex':
            vcol = np.asarray(vis.vertex_colors, np.float64)[:, :3] / 255.0
        parts.append({'name': gname, 'V': V, 'F': np.asarray(m.faces, np.int64), 'UV': UV, 'tex': tex, 'vcol': vcol,
                      'factor': np.ones(4), 'skinned': False, 'node': node})
    return parts


# ------------------------------------------------------------------ writer
def _pad4(b, pad=b'\x00'):
    return b + pad * ((-len(b)) % 4)


def write_glb(path, parts, node_matrix=None):
    """parts: dicts with V (n,3), F (m,3), optional N, UV (glTF convention: v down),
    vcol (n,3 linear 0..1), png (bytes), name."""
    g = {'asset': {'version': '2.0', 'generator': 'rl-heads fit selftest'}, 'scene': 0, 'scenes': [{'nodes': []}],
         'nodes': [], 'meshes': [], 'materials': [], 'accessors': [], 'bufferViews': [], 'buffers': []}
    blob = bytearray()

    def view(data, target=None):
        off = len(blob)
        blob.extend(_pad4(bytes(data)))
        v = {'buffer': 0, 'byteOffset': off, 'byteLength': len(data)}
        if target:
            v['target'] = target
        g['bufferViews'].append(v)
        return len(g['bufferViews']) - 1

    def acc(arr, ctype, typ, target=None, minmax=False):
        arr = np.ascontiguousarray(arr)
        vi = view(arr.tobytes(), target)
        a = {'bufferView': vi, 'componentType': ctype, 'count': int(arr.shape[0]), 'type': typ}
        if minmax:
            a['min'] = [float(x) for x in arr.min(0)]; a['max'] = [float(x) for x in arr.max(0)]
        g['accessors'].append(a)
        return len(g['accessors']) - 1

    for k, p in enumerate(parts):
        attrs = {'POSITION': acc(np.asarray(p['V'], np.float32), 5126, 'VEC3', 34962, True)}
        if p.get('N') is not None:
            attrs['NORMAL'] = acc(np.asarray(p['N'], np.float32), 5126, 'VEC3', 34962)
        if p.get('UV') is not None:
            attrs['TEXCOORD_0'] = acc(np.asarray(p['UV'], np.float32), 5126, 'VEC2', 34962)
        if p.get('vcol') is not None:
            attrs['COLOR_0'] = acc(np.asarray(p['vcol'], np.float32), 5126, 'VEC3', 34962)
        ind = acc(np.asarray(p['F'], np.uint32).reshape(-1, 1), 5125, 'SCALAR', 34963)
        mat = {'name': p.get('name', f'mat{k}'), 'pbrMetallicRoughness': {'metallicFactor': 0.0, 'roughnessFactor': 0.8}}
        if p.get('png') is not None:
            g.setdefault('images', []); g.setdefault('textures', []); g.setdefault('samplers', [{}])
            vi = view(p['png'])
            g['images'].append({'bufferView': vi, 'mimeType': 'image/png'})
            g['textures'].append({'source': len(g['images']) - 1, 'sampler': 0})
            mat['pbrMetallicRoughness']['baseColorTexture'] = {'index': len(g['textures']) - 1}
        g['materials'].append(mat)
        g['meshes'].append({'name': p.get('name', f'mesh{k}'),
                            'primitives': [{'attributes': attrs, 'indices': ind, 'material': len(g['materials']) - 1}]})
        nd = {'name': p.get('name', f'node{k}'), 'mesh': len(g['meshes']) - 1}
        if node_matrix is not None:
            nd['matrix'] = [float(x) for x in np.asarray(node_matrix, np.float64).T.reshape(16)]
        g['nodes'].append(nd)
        g['scenes'][0]['nodes'].append(len(g['nodes']) - 1)
    g['buffers'].append({'byteLength': len(blob)})
    js = _pad4(json.dumps(g, separators=(',', ':')).encode('utf-8'), b' ')
    bb = _pad4(bytes(blob))
    total = 12 + 8 + len(js) + 8 + len(bb)
    with open(path, 'wb') as fh:
        fh.write(struct.pack('<III', 0x46546C67, 2, total))
        fh.write(struct.pack('<II', len(js), 0x4E4F534A)); fh.write(js)
        fh.write(struct.pack('<II', len(bb), 0x004E4942)); fh.write(bb)
    return total
