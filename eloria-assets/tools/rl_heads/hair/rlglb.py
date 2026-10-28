"""GLB reading helpers for the RL hair/beard tooling.

Self-contained (numpy only): container reading, node globals, quaternion
helpers, accessors with sparse substitution (the head module's morph targets
are sparse) and the `normalized` flag.

Matrix conventions: numpy 4x4 matrices here are column-vector (M @ v, the
translation in the last column) like globals_of(). glTF stores MAT4
column-major, so a matrix M is written as M.T.reshape(16) -- this is exactly
the flat layout the body / head GLBs store (read back by accessor()).
"""
import os, sys, json, struct
import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)


def read(path):
    """(gltf json, binary chunk) of a .glb."""
    data = open(path, 'rb').read()
    magic, _v, _n = struct.unpack_from('<III', data, 0)
    if magic != 0x46546C67:
        raise ValueError('%s is not a glb' % path)
    off, g, blob = 12, None, b''
    while off < len(data):
        n, typ = struct.unpack_from('<II', data, off)
        chunk = data[off + 8:off + 8 + n]
        if typ == 0x4E4F534A:
            g = json.loads(chunk.decode('utf-8'))
        elif typ == 0x004E4942:
            blob = chunk
        off += 8 + n
        off += (4 - off % 4) % 4
    return g, blob


def quat_to_matrix(q):
    x, y, z, w = np.asarray(q, np.float64) / np.linalg.norm(q)
    return np.array([[1 - 2 * (y * y + z * z), 2 * (x * y - z * w), 2 * (x * z + y * w)],
                     [2 * (x * y + z * w), 1 - 2 * (x * x + z * z), 2 * (y * z - x * w)],
                     [2 * (x * z - y * w), 2 * (y * z + x * w), 1 - 2 * (x * x + y * y)]])


def matrix_to_quat(m):
    """(3,3) rotation -> [x, y, z, w] (Shepperd)."""
    m = np.asarray(m, np.float64)
    tr = m[0, 0] + m[1, 1] + m[2, 2]
    if tr > 0:
        s = np.sqrt(tr + 1.0) * 2
        q = [(m[2, 1] - m[1, 2]) / s, (m[0, 2] - m[2, 0]) / s, (m[1, 0] - m[0, 1]) / s, 0.25 * s]
    elif m[0, 0] > m[1, 1] and m[0, 0] > m[2, 2]:
        s = np.sqrt(1.0 + m[0, 0] - m[1, 1] - m[2, 2]) * 2
        q = [0.25 * s, (m[0, 1] + m[1, 0]) / s, (m[0, 2] + m[2, 0]) / s, (m[2, 1] - m[1, 2]) / s]
    elif m[1, 1] > m[2, 2]:
        s = np.sqrt(1.0 + m[1, 1] - m[0, 0] - m[2, 2]) * 2
        q = [(m[0, 1] + m[1, 0]) / s, 0.25 * s, (m[1, 2] + m[2, 1]) / s, (m[0, 2] - m[2, 0]) / s]
    else:
        s = np.sqrt(1.0 + m[2, 2] - m[0, 0] - m[1, 1]) * 2
        q = [(m[0, 2] + m[2, 0]) / s, (m[1, 2] + m[2, 1]) / s, 0.25 * s, (m[1, 0] - m[0, 1]) / s]
    q = np.array(q)
    return q / np.linalg.norm(q)


def node_matrix(nd):
    if 'matrix' in nd:
        return np.asarray(nd['matrix'], np.float64).reshape(4, 4).T
    M = np.eye(4)
    if 'scale' in nd:
        M = np.diag(list(nd['scale']) + [1.0]) @ M
    if 'rotation' in nd:
        R = np.eye(4); R[:3, :3] = quat_to_matrix(nd['rotation']); M = R @ M
    if 'translation' in nd:
        T = np.eye(4); T[:3, 3] = nd['translation']; M = T @ M
    return M


def globals_of(g):
    """World matrix per node index (column-vector convention)."""
    nodes = g.get('nodes', [])
    roots = set()
    for sc in g.get('scenes', []):
        roots.update(sc.get('nodes', []))
    if not roots:
        child = {c for nd in nodes for c in nd.get('children', [])}
        roots = {i for i in range(len(nodes)) if i not in child}
    out, stack = {}, [(i, np.eye(4)) for i in sorted(roots)]
    while stack:
        i, P = stack.pop()
        W = P @ node_matrix(nodes[i])
        out[i] = W
        stack.extend((c, W) for c in nodes[i].get('children', []))
    return out


COMPONENT = {5120: '<i1', 5121: '<u1', 5122: '<i2', 5123: '<u2', 5125: '<u4', 5126: '<f4'}
NCOMP = {'SCALAR': 1, 'VEC2': 2, 'VEC3': 3, 'VEC4': 4, 'MAT2': 4, 'MAT3': 9, 'MAT4': 16}
NORM_DIV = {5120: 127.0, 5121: 255.0, 5122: 32767.0, 5123: 65535.0}


def _view_array(g, blob, view_index, dtype, count, ncomp, byte_offset=0):
    view = g['bufferViews'][view_index]
    start = view.get('byteOffset', 0) + byte_offset
    item = np.dtype(dtype).itemsize
    stride = view.get('byteStride') or ncomp * item
    if stride == ncomp * item:
        return np.frombuffer(blob, dtype=dtype, count=count * ncomp, offset=start).reshape(count, ncomp)
    out = np.zeros((count, ncomp), dtype=dtype)
    for i in range(count):
        out[i] = np.frombuffer(blob, dtype=dtype, count=ncomp, offset=start + i * stride)
    return out


def accessor(g, blob, index, normalize=True):
    """Accessor as float64 (count, ncomp); applies sparse substitution and
    the `normalized` flag for integer components."""
    acc = g['accessors'][index]
    n = NCOMP[acc['type']]
    ct = acc['componentType']
    dt = COMPONENT[ct]
    if 'bufferView' in acc:
        out = _view_array(g, blob, acc['bufferView'], dt, acc['count'], n, acc.get('byteOffset', 0)).astype(np.float64)
    else:
        out = np.zeros((acc['count'], n))
    sp = acc.get('sparse')
    if sp:
        idx = _view_array(g, blob, sp['indices']['bufferView'], COMPONENT[sp['indices']['componentType']],
                          sp['count'], 1, sp['indices'].get('byteOffset', 0)).ravel().astype(np.int64)
        val = _view_array(g, blob, sp['values']['bufferView'], dt, sp['count'], n,
                          sp['values'].get('byteOffset', 0)).astype(np.float64)
        out = out.copy()
        out[idx] = val
    if normalize and acc.get('normalized') and ct in NORM_DIV:
        out = out / NORM_DIV[ct]
    return out


def mat4_to_gltf(M):
    """numpy column-vector 4x4 -> glTF flat column-major list layout (16,)."""
    return np.asarray(M, np.float64).T.reshape(16)


def quat_from_matrix(R):
    return matrix_to_quat(np.asarray(R, np.float64)[:3, :3])


def trs_from_matrix(M):
    """Decompose a rigid (orthonormal, unit-scale) 4x4 into glTF TRS lists."""
    M = np.asarray(M, np.float64)
    R = M[:3, :3]
    s = np.linalg.norm(R, axis=0)
    q = matrix_to_quat(R / s)
    q = q / np.linalg.norm(q)
    out = {'translation': [float(x) for x in M[:3, 3]], 'rotation': [float(x) for x in q]}
    if np.abs(s - 1).max() > 1e-6:
        out['scale'] = [float(x) for x in s]
    return out


def glb_json(path):
    data = open(path, 'rb').read()
    jl = struct.unpack_from('<I', data, 12)[0]
    return json.loads(data[20:20 + jl])
