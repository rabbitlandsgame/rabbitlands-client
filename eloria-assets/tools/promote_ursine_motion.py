"""Promote an explicitly selected ursine delivery; preserve native rigs and exact curves."""
from pathlib import Path
import argparse, copy, json, re, shutil, sys
import numpy as np
from scipy.spatial.transform import Rotation, Slerp
sys.path.insert(0, str(Path(__file__).resolve().parent))
from video_motion.asset import Asset, accessor, digest, write_glb
from video_motion.packing import compact, append_array
ACTORS = ('obsidian_bear', 'crystal_polar_bear', 'owlbear')
CLIPS = ('Idle_A', 'Fighting_Idle', 'Hit_Chest', 'Walk', 'Jog', 'Sword_Attack', 'Death_A')
ROLES = {c: 'Attack_Combo_Rise' if c == 'Sword_Attack' else c for c in CLIPS}
ROOT = Path(__file__).resolve().parents[2]

def clean(value):
    if isinstance(value, dict):
        return {k: clean(v) for k, v in value.items() if k != 'extras'}
    if isinstance(value, list):
        return [clean(v) for v in value]
    return value

def worlds(asset, clip, times):
    """Evaluate inherited translation, rotation AND scale channels independently."""
    times = np.asarray(times)
    t = np.tile(asset.t, (len(times), 1, 1))
    q = np.tile(asset.q, (len(times), 1, 1))
    scale = np.tile(asset.s, (len(times), 1, 1))
    anim = asset.animations[clip]
    for ch in anim['channels']:
        sam = anim['samplers'][ch['sampler']]
        ts = accessor(asset.document, asset.blob, sam['input']).ravel()
        values = accessor(asset.document, asset.blob, sam['output'])
        x = np.clip(times, ts[0], ts[-1])
        mode = sam.get('interpolation', 'LINEAR')
        kind = ch['target']['path']
        if mode not in ['LINEAR', 'STEP']:
            raise ValueError('Unsupported inherited interpolation')
        if len(ts) == 1:
            result = np.tile(values[0], (len(times), 1))
        elif mode == 'STEP':
            result = values[np.clip(np.searchsorted(ts, x, side='right') - 1, 0, len(ts) - 1)]
        elif kind == 'rotation':
            result = Slerp(ts, Rotation.from_quat(values))(x).as_quat()
        else:
            result = np.array([np.interp(x, ts, values[:, k]) for k in range(values.shape[1])]).T
        target = {'translation': t, 'rotation': q, 'scale': scale}.get(kind)
        if target is None:
            raise ValueError('Unsupported inherited channel ' + kind)
        target[:, ch['target']['node']] = result
    local = np.broadcast_to(np.eye(4), (len(times), asset.n, 4, 4)).copy()
    local[:, :, :3, :3] = Rotation.from_quat(q.reshape(-1, 4)).as_matrix().reshape(len(times), asset.n, 3, 3) * scale[:, :, None, :]
    local[:, :, :3, 3] = t
    world = np.empty_like(local)
    for n in asset.order:
        world[:, n] = local[:, n] if asset.parent[n] < 0 else world[:, asset.parent[n]] @ local[:, n]
    return world

def exact_clip(a, b, ac, bc):
    x, y = (a.animations[ac], b.animations[bc])
    if len(x['channels']) != len(y['channels']):
        return False
    for cx, cy in zip(x['channels'], y['channels']):
        if cx['target'] != cy['target']:
            return False
        sx, sy = (x['samplers'][cx['sampler']], y['samplers'][cy['sampler']])
        if sx.get('interpolation', 'LINEAR') != sy.get('interpolation', 'LINEAR'):
            return False
        tx, ty = [accessor(z.document, z.blob, s['input']) for z, s in [(a, sx), (b, sy)]]
        vx, vy = [accessor(z.document, z.blob, s['output']) for z, s in [(a, sx), (b, sy)]]
        if np.array_equal(tx, ty) and np.array_equal(vx, vy):
            continue
        if not (len(tx) == 2 and np.array_equal(tx, ty[[0, -1]]) and np.all(vy == vy[0]) and np.array_equal(vx, vy[[0, -1]])):
            return False
    return bool(a.duration(ac) == b.duration(bc))

def bake_object_translation(document, binary, source, clip):
    """Move a translated armature object's motion into its direct root bones.

 The native loader consumes bone tracks. The rest rig, remaining curves and
 skinned world motion stay intact; arbitrary animated parent rotation is rejected.
 """
    animation = next((x for x in document['animations'] if x['name'] == clip))
    object_channels = [x for x in animation['channels'] if x['target']['node'] not in source.joints]
    blob = bytearray(binary)
    records = []
    for channel in object_channels:
        parent = channel['target']['node']
        if channel['target']['path'] != 'translation' or source.parent[parent] >= 0:
            raise ValueError('An explicit animated-parent adapter is required')
        roots = [n for n in source.joints if source.parent[n] == parent]
        if not roots:
            raise ValueError('Object track has no direct physical root')
        parent_sampler = animation['samplers'][channel['sampler']]
        for root in roots:
            root_channel = next((x for x in animation['channels'] if x['target'] == {'node': root, 'path': 'translation'}), None)
            if root_channel is None:
                raise ValueError('Root translation channel is required')
            root_sampler = animation['samplers'][root_channel['sampler']]
            times = np.unique(np.r_[accessor(document, blob, parent_sampler['input']).ravel(), accessor(document, blob, root_sampler['input']).ravel()])
            original = worlds(source, clip, times)
            local = np.linalg.inv(source.world_rest[parent])[None] @ original[:, root]
            root_sampler['input'] = append_array(document, blob, times[:, None], 'SCALAR')
            root_sampler['output'] = append_array(document, blob, local[:, :3, 3], 'VEC3')
            root_sampler['interpolation'] = 'LINEAR'
        animation['channels'].remove(channel)
        records.append({'object_node': int(parent), 'root_bones': [int(n) for n in roots]})
    used = sorted({x['sampler'] for x in animation['channels']})
    remap = {old: new for new, old in enumerate(used)}
    animation['samplers'] = [animation['samplers'][n] for n in used]
    for ch in animation['channels']:
        ch['sampler'] = remap[ch['sampler']]
    return (document, blob, records)

def static_equal(a, b):
    ok = {k: clean(a.document.get(k)) == clean(b.document.get(k)) for k in ['nodes', 'materials', 'textures', 'samplers', 'scenes', 'scene']}
    ok['rest_worlds'] = bool(np.array_equal(a.world_rest, b.world_rest))
    ok['mesh_skin_arrays'] = True
    for ma, mb in zip(a.document['meshes'], b.document['meshes']):
        for pa, pb in zip(ma['primitives'], mb['primitives']):
            for key in pa['attributes']:
                ok['mesh_skin_arrays'] &= bool(np.array_equal(accessor(a.document, a.blob, pa['attributes'][key]), accessor(b.document, b.blob, pb['attributes'][key])))
            ok['mesh_skin_arrays'] &= bool(np.array_equal(accessor(a.document, a.blob, pa['indices']), accessor(b.document, b.blob, pb['indices'])))
    ok['binds'] = all((np.array_equal(accessor(a.document, a.blob, x['inverseBindMatrices']), accessor(b.document, b.blob, y['inverseBindMatrices'])) and x['joints'] == y['joints'] for x, y in zip(a.document['skins'], b.document['skins'])))

    def images(z):
        result = []
        for im in z.document.get('images', []):
            bv = z.document['bufferViews'][im['bufferView']]
            start = bv.get('byteOffset', 0)
            result.append(z.blob[start:start + bv['byteLength']])
        return result
    ok['embedded_texture_bytes'] = images(a) == images(b)
    return ok

def policy(source):
    text = source.read_text()
    text = re.sub('animation/fps=.*', 'animation/fps=1536', text)
    for field, val in [('animation/trimming', 'false'), ('animation/remove_immutable_tracks', 'false'), ('animation/import_rest_as_RESET', 'false')]:
        text = re.sub(re.escape(field) + '=.*', field + '=' + val, text)
    start = text.index('_subresources=')
    end = text.index('\ngltf/', start)
    text = text[:start] + '_subresources={\n"nodes": {\n"PATH:AnimationPlayer": {\n"compression/enabled": false,\n"optimizer/enabled": false\n}\n}\n}\n' + text[end:]
    return text

def promote(delivery, out, apply=False):
    manifest = json.loads((delivery / 'manifest.json').read_text())
    assert json.loads((delivery / 'validation.json').read_text())['passed']
    assert json.loads((delivery / 'godot-playback.json').read_text())['passed']
    registry_path = ROOT / 'godot-client/data/actors/models.json'
    registry = json.loads(registry_path.read_text())
    original_registry = copy.deepcopy(registry)
    mapping_base = json.loads((ROOT / 'godot-client/data/animations/ursine/moss_bear.json').read_text())
    out.mkdir(parents=True, exist_ok=True)
    (out / 'before').mkdir(exist_ok=True)
    records = {}
    witness = {}
    moss = ROOT / 'godot-client/assets/actors/native/creatures/moss_bear.glb'
    moss_hash = digest(moss)
    for name in ACTORS:
        source = delivery / name / (name + '.glb')
        assert digest(source) == manifest['actors'][name]['candidate_sha256']
        a = Asset(source)
        runtime = ROOT / 'godot-client/assets/actors/native/creatures' / (name + '.glb')
        baseline = out / 'before' / (name + '.glb')
        shutil.copy2(runtime, baseline) if not baseline.exists() else None
        old = Asset(baseline)
        d = clean(copy.deepcopy(a.document))
        d['animations'] = [copy.deepcopy(d['animations'][list(a.animations).index(ROLES[c])]) for c in CLIPS]
        for c, animation in zip(CLIPS, d['animations']):
            animation['name'] = c
            animation['extras'] = {'loop': c in ['Idle_A', 'Fighting_Idle', 'Walk', 'Jog'], 'hold_end': c in ['Sword_Attack', 'Death_A']}
        d['asset'] = {'version': '2.0', 'generator': 'Rabbit Lands reviewed ursine motion', 'extras': {'rabbitlands_animation_bake_fps': 1536}}
        root_bake = []
        binary = a.blob
        if name == 'owlbear':
            d, binary, root_bake = bake_object_translation(d, binary, a, 'Idle_A')
        d, b, packing = compact(d, binary)
        dest = out / (name + '.glb')
        write_glb(dest, d, b)
        p = Asset(dest)
        static = static_equal(p, a)
        assert all(static.values()), (name, static)
        fitted = {c: exact_clip(p, a, c, ROLES[c]) for c in CLIPS}
        assert all((value or (name == 'owlbear' and c == 'Idle_A') for c, value in fitted.items())), (name, fitted)
        root_world_error = 0.0
        root_skin_error = 0.0
        if root_bake:
            keys = np.unique(np.concatenate([accessor(a.document, a.blob, x['input']).ravel() for x in a.animations['Idle_A']['samplers']]))
            times = np.unique(np.r_[keys, (keys[:-1] + keys[1:]) / 2])
            before = worlds(a, 'Idle_A', times)
            after = worlds(p, 'Idle_A', times)
            root_world_error = float(np.abs(before[:, sorted(a.joints)] - after[:, sorted(p.joints)]).max())
            root_skin_error = max((float(np.abs(a.skin(x) - p.skin(y)).max()) for x, y in zip(before, after)))
            assert root_world_error < 5e-06 and root_skin_error < 5e-06
        for text in ['C:/', 'C:\\', 'eloria-project', 'source_candidate_sha256']:
            assert text not in json.dumps(p.document), ('private metadata', text)
        original_idle = {c: exact_clip(p, old, c, c) for c in ['Idle_A', 'Fighting_Idle', 'Hit_Chest']}
        nonface = None
        if name == 'obsidian_bear':
            head = {14, 1, 0}
            other = [n for n in p.joints if n not in head]
            nonface = 0.0
            for c in original_idle:
                keys = np.unique(np.concatenate([accessor(old.document, old.blob, s['input']).ravel() for s in old.animations[c]['samplers']]))
                ts = np.unique(np.r_[keys, (keys[:-1] + keys[1:]) / 2])
                t0, q0 = old.sample(c, ts)
                t1, q1 = p.sample(c, ts)
                for x, y, u, v in zip(t0, q0, t1, q1):
                    nonface = max(nonface, float(np.abs(old.world(x, y)[other] - p.world(u, v)[other]).max()))
            assert nonface < 5e-05
        else:
            assert all((value or (name == 'owlbear' and c == 'Idle_A' and (root_world_error < 5e-06)) for c, value in original_idle.items()))
        profile = json.loads((delivery / name / 'options-profile.json').read_text())['native_profile']
        sole = profile['bottom_vertex_ids']
        speeds = {}
        for action, clip, duty in [('walk', 'Walk', 0.68), ('run', 'Jog', 0.58)]:
            samples = []
            duration = float(p.duration(clip))
            for leg, phase in zip(['fore_left', 'fore_right', 'hind_left', 'hind_right'], [0.2, 0.7, 0, 0.5]):
                dt = (duty - 0.22) * duration
                stamps = np.array([(phase + 0.1) * duration, (phase + duty - 0.12) * duration]) % duration
                t, q = p.sample(clip, stamps)
                centers = [p.skin(p.world(x, y))[sole[leg]].mean(0) for x, y in zip(t, q)]
                samples.append(float(-(centers[1][2] - centers[0][2]) / dt))
            assert max(samples) - min(samples) < 0.01, (name, action, samples)
            speeds[action] = float(np.median(samples) * registry['models'][name]['import']['scale'])
        mapping = copy.deepcopy(mapping_base)
        mapping['strideMetresPerSecond'] = speeds
        mapfile = out / (name + '.json')
        mapfile.write_text(json.dumps(mapping, indent=2) + '\n', newline='\n')
        registry['models'][name]['animationMap'] = 'res://data/animations/ursine/' + name + '.json'
        imports = out / (name + '.glb.import')
        imports.write_text(policy(Path(str(runtime) + '.import')), newline='\n')
        witness[name] = {'sha256': digest(dest), 'clips': {}}
        for c in CLIPS:
            stamps = np.array([0, 0.113, 0.393, 0.617, 0.831, 1]) * p.duration(c)
            witness[name]['clips'][c] = [{'time': float(ti), 'bones': {p.names[n]: w[n, :3].ravel().tolist() for n in p.joints}} for ti, w in zip(stamps, worlds(p, c, stamps))]
        records[name] = {'previous_runtime_sha256': digest(baseline), 'reviewed_sha256': digest(source), 'runtime_sha256': digest(dest), 'bytes': dest.stat().st_size, 'static_vs_reviewed': static, 'selected_clip_arrays_exact': fitted, 'source_clip_selection': ROLES, 'previous_idle_hit_payloads_exact': original_idle, 'obsidian_nonface_idle_hit_world_error': nonface, 'reviewed_face_alignment': {'yaw_degrees': -18, 'muzzle_lift_degrees': 4} if name == 'obsidian_bear' else None, 'reviewed_skin_preparation_vertices': 80 if name == 'obsidian_bear' else 0, 'stride_metres_per_second_at_import_scale': speeds, 'import_scale': registry['models'][name]['import']['scale'], 'packing': packing, 'idle_object_translation_bake': root_bake, 'idle_world_preservation_max_error': root_world_error, 'idle_skin_preservation_max_error': root_skin_error}
    (out / 'models.json').write_text(json.dumps(registry, indent=2) + '\n', newline='\n')
    (out / 'world-witnesses.json').write_text(json.dumps(witness), newline='\n')
    receipt = {'status': 'Selected delivery-v5 approved for client integration and develop publication.', 'actors': records, 'review_manifest_sha256': digest(delivery / 'manifest.json'), 'moss_bear_unchanged_sha256': moss_hash, 'scope': 'Walk, Jog, final descending attack and Death_A on three imported bears. Only the selected seven runtime slots retained. No server damage or attack scheduling change.', 'validation_inheritance': 'Selected curves and static arrays match the qualified review. Owlbear idle object translation is rebased to its root bone with key/half-key world and skin preservation; the attack is renamed for the existing action contract.', 'authoring_sources': 'High-resolution inputs, working profiles and rejected choices remain private and Git-ignored.'}
    (out / 'promotion.json').write_text(json.dumps(receipt, indent=2) + '\n', newline='\n')
    if apply:
        for name in ACTORS:
            runtime = ROOT / 'godot-client/assets/actors/native/creatures' / (name + '.glb')
            shutil.copy2(out / (name + '.glb'), runtime)
            shutil.copy2(out / (name + '.glb.import'), Path(str(runtime) + '.import'))
            shutil.copy2(out / (name + '.json'), ROOT / 'godot-client/data/animations/ursine' / (name + '.json'))
        text = registry_path.read_text()
        for name in ACTORS:
            pattern = '("' + re.escape(name) + '": \\{.*?"animationMap": ")[^"]+(\\")'
            text, count = re.subn(pattern, lambda m: m[1] + 'res://data/animations/ursine/' + name + '.json' + m[2], text, count=1, flags=re.S)
            assert count == 1, name
        registry_path.write_text(text, newline='\n')
        actual = json.loads(text)
        expected = copy.deepcopy(original_registry)
        for name in ACTORS:
            expected['models'][name]['animationMap'] = registry['models'][name]['animationMap']
        assert actual == expected
    assert digest(moss) == moss_hash
    print('URSINE_PROMOTION_READY', json.dumps({n: {'bytes': x['bytes'], 'sha256': x['runtime_sha256']} for n, x in records.items()}), flush=True)
    return receipt
if __name__ == '__main__':
    p = argparse.ArgumentParser()
    p.add_argument('--delivery', type=Path, required=True)
    p.add_argument('--output', type=Path, required=True)
    p.add_argument('--apply', action='store_true')
    args = p.parse_args()
    promote(args.delivery.resolve(), args.output.resolve(), args.apply)
