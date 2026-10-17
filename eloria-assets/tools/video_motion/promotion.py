"""Preserve current runtime clips when a reviewed input adds/reparents rig joints."""
import copy
import numpy as np
from scipy.spatial.transform import Rotation
from .asset import accessor
from .packing import append_array


PRESERVED_CLIPS = ('Idle_A', 'Fighting_Idle', 'Hit_Chest', 'Jog')
FITTED_CLIPS = ('Walk', 'Sword_Attack', 'Death_A')


def world_batch(asset, times, clip):
    t, q = asset.sample(clip, times)
    local = np.broadcast_to(np.eye(4), (len(times), asset.n, 4, 4)).copy()
    local[:, :, :3, :3] = Rotation.from_quat(q.reshape(-1, 4)).as_matrix().reshape(
        len(times), asset.n, 3, 3) * asset.s[None, :, None, :]
    local[:, :, :3, 3] = t
    world = np.empty_like(local)
    for node in asset.order:
        parent = asset.parent[node]
        world[:, node] = local[:, node] if parent < 0 else world[:, parent] @ local[:, node]
    return world


def preserve_runtime_clips(current, fitted):
    """Copy unchanged channels exactly; rebase changed parents in world space.

    This intentionally requires the original node prefix (duplicate names included).
    It is not a generic anatomy retargeter. Dynamic parent changes are baked at
    3072 Hz and must pass independent world-transform verification by the caller.
    """
    if current.names != fitted.names[:current.n]:
        raise ValueError('Original node prefix/order differs; explicit correspondence needed')
    if not np.allclose(current.world_rest, fitted.world_rest[:current.n], atol=2e-6):
        raise ValueError('Original joint rest worlds differ')
    doc, blob = copy.deepcopy(fitted.document), bytearray(fitted.blob)
    cadence = max(current.document.get('asset', {}).get('extras', {}).get('rabbitlands_animation_bake_fps', 30),
                  fitted.document.get('asset', {}).get('extras', {}).get('rabbitlands_animation_bake_fps', 30))
    if cadence > 30:
        doc['asset'].setdefault('extras', {})['rabbitlands_animation_bake_fps'] = cadence
    records = {}
    for clip in PRESERVED_CLIPS:
        original = current.animations[clip]
        out = {'name': clip, 'channels': [], 'samplers': [],
               'extras': {'runtime_clip_preserved': True}}
        duration = current.duration(clip)
        changed = [n for n in range(current.n) if current.parent[n] != fitted.parent[n]]
        def add(node, path, times, values, mode='LINEAR'):
            out['channels'].append({'target': {'node': int(node), 'path': path},
                                    'sampler': len(out['samplers'])})
            out['samplers'].append({'input': append_array(doc, blob, np.asarray(times)[:, None], 'SCALAR'),
                'output': append_array(doc, blob, values, {'translation':'VEC3','rotation':'VEC4','scale':'VEC3'}[path]),
                'interpolation': mode})
        for ch in original['channels']:
            if ch['target']['node'] in changed:
                continue
            sampler = original['samplers'][ch['sampler']]
            if sampler.get('interpolation', 'LINEAR') not in ('LINEAR', 'STEP'):
                raise ValueError('Unsupported preserved interpolation')
            add(ch['target']['node'], ch['target']['path'],
                accessor(current.document, current.blob, sampler['input']).ravel(),
                accessor(current.document, current.blob, sampler['output']), sampler.get('interpolation','LINEAR'))
        dynamic = []
        for node in changed:
            parent = int(fitted.parent[node])
            ancestor = parent
            while ancestor >= current.n:
                ancestor = int(fitted.parent[ancestor])
            source_times = [accessor(current.document, current.blob, s['input']).ravel()
                            for s in original['samplers']]
            if ancestor == current.parent[node]:
                # New neutral joints form a constant bridge under the old parent.
                times = np.unique(np.concatenate(source_times + [np.array([0., duration])]))
                parent_rest = np.eye(4) if parent < 0 else fitted.world_rest[parent]
                old_rest = np.eye(4) if current.parent[node] < 0 else current.world_rest[current.parent[node]]
                correction = np.linalg.inv(parent_rest) @ old_rest
                if not np.allclose(correction[:3,:3].T @ correction[:3,:3], np.eye(3), atol=1e-6):
                    raise ValueError('Nonrigid inserted bridge')
                t, q = current.sample(clip, times)
                new_t = t[:, node] @ correction[:3,:3].T + correction[:3,3]
                new_q = (Rotation.from_matrix(correction[:3,:3]) * Rotation.from_quat(q[:,node])).as_quat()
            else:
                dynamic.append(node)
                times = np.unique(np.concatenate(source_times + [np.linspace(0, duration, int(np.ceil(duration * 3072)) + 1)]).astype('<f4')).astype(float)
                worlds = world_batch(current, times, clip)
                if parent >= current.n:
                    raise ValueError('Dynamic parent under added controls needs explicit adaptation')
                local = np.linalg.inv(worlds[:, parent]) @ worlds[:, node]
                new_t = local[:, :3, 3]
                new_q = Rotation.from_matrix(local[:, :3,:3] / fitted.s[node][None,None,:]).as_quat()
            for i in range(1, len(new_q)):
                if np.dot(new_q[i-1], new_q[i]) < 0:
                    new_q[i] *= -1
            add(node, 'translation', times, new_t)
            add(node, 'rotation', times, new_q)
        for node in range(current.n, fitted.n):
            add(node, 'translation', [0., duration], np.tile(fitted.t[node], (2,1)))
            add(node, 'rotation', [0., duration], np.tile(fitted.q[node], (2,1)))
        doc['animations'] = [a for a in doc['animations'] if a['name'] != clip] + [out]
        records[clip] = {'reparented_nodes': changed, 'dynamically_rebased_nodes': dynamic}
    return doc, blob, records
