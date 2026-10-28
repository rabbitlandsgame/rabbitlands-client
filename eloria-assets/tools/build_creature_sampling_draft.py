"""Freeze the current creature and create a separate sampled animation draft.

python eloria-assets/tools/build_creature_sampling_draft.py --actor crystalback_tortoise --fps 30
"""
from pathlib import Path
import argparse,copy,json,math
import numpy as np
import zstandard
from video_motion.asset import accessor,digest,read_glb,write_glb
from video_motion.packing import append_array,compact
from video_motion.storage_components import inspect_glb
from build_foal_240_draft import uniform_clock,resample,verify_static
ROOT=Path(__file__).resolve().parents[2]

def folder(actor):
    registry=json.loads((ROOT/'godot-client/data/actors/models.json').read_text())['models']
    assert actor in registry and str(registry[actor]['scene']).startswith('res://assets/actors/native/creatures/')
    return ROOT/'.local/creature-sampling'/actor

def reference(actor):
    base=folder(actor); path=base/'original'/f'{actor}.glb'; manifest_path=base/'reference.json'
    if not manifest_path.exists():
        registry=json.loads((ROOT/'godot-client/data/actors/models.json').read_text())['models']
        current=ROOT/'godot-client'/registry[actor]['scene'].removeprefix('res://')
        raw=current.read_bytes(); path.parent.mkdir(parents=True,exist_ok=True)
        assert not path.exists(), 'Unrecorded reference exists; preserve and reconcile it before retrying.'
        path.write_bytes(raw); d,_=read_glb(path)
        manifest={'actor':actor,'source_sha256':digest(path),'runtime_path':current.relative_to(ROOT).as_posix(),'source_bake_fps':d['asset'].get('extras',{}).get('rabbitlands_animation_bake_fps',30),'clips':[a['name']for a in d['animations']]}
        manifest_path.write_text(json.dumps(manifest,indent=2)+'\n',encoding='utf-8',newline='\n')
    manifest=json.loads(manifest_path.read_text());assert digest(path)==manifest['source_sha256']
    return path,manifest

def build(actor="crystalback_tortoise", fps=30):
    assert fps in (30, 240)
    source, manifest = reference(actor)
    source_sha = manifest["source_sha256"]
    output = folder(actor) / f"fps-{fps}"
    assert digest(source) == source_sha
    output.mkdir(parents=True, exist_ok=True)
    a, ab = read_glb(source)
    d, blob = copy.deepcopy(a), bytearray(ab)
    clips = []
    for original, animation in zip(a['animations'], d['animations'], strict=True):
        before = after = 0
        paths = {}
        for si, sampler in enumerate(animation['samplers']):
            old = original['samplers'][si]
            assert old.get('interpolation', 'LINEAR') == 'LINEAR', 'Review STEP/cubic semantics before resampling'
            kinds = {c['target']['path'] for c in animation['channels'] if c['sampler'] == si}
            assert len(kinds) == 1
            kind = next(iter(kinds))
            ts = accessor(a, ab, old['input']).ravel()
            values = accessor(a, ab, old['output']).reshape(len(ts), -1)
            assert np.all(np.diff(ts) > 0) and np.isfinite(values).all()
            query = uniform_clock(float(ts[0]), float(ts[-1]), fps)
            if np.array_equal(values, np.repeat(values[:1], len(values), axis=0)):
                query = ts[[0, -1]].astype(np.float32)
                v = values[[0, -1]]
            else:
                v = resample(ts, values, query, kind == 'rotation')
                # Retain the original one-shot endpoints, including quaternion bits.
                v[0], v[-1] = values[0], values[-1]
            sampler['input'] = append_array(d, blob, query[:, None], 'SCALAR')
            sampler['output'] = append_array(d, blob, v.reshape(-1, 1) if kind == 'weights' else v, a['accessors'][old['output']]['type'])
            before += len(ts); after += len(query)
            paths[kind] = paths.get(kind, 0) + 1
        clips.append({'name': animation['name'], 'source_sampler_keys': before, 'draft_sampler_keys': after, 'channels_by_path': paths})
    d['asset'].setdefault('extras', {})['rabbitlands_animation_bake_fps'] = fps
    d['asset']['extras']['rabbitlands_sampling_pilot'] = {'status': 'draft_for_comparison', 'source_sha256': source_sha, 'maximum_samples_per_second': fps, 'method': 'uniform per-sampler LINEAR / quaternion SLERP; preserve endpoints and all channels'}
    d, blob, packing = compact(d, blob)
    candidate = output / f'{actor}_{fps}.glb'
    write_glb(candidate, d, blob)
    b, bb = read_glb(candidate)
    verify_static(a, ab, b, bb)
    maximum_rate = 0.
    for old, new, record in zip(a['animations'], b['animations'], clips, strict=True):
        assert old['channels'] == new['channels'] and old['name'] == new['name']
        record['packed_draft_sampler_keys'] = sum(b['accessors'][sampler['input']]['count'] for sampler in new['samplers'])
        record['duration_seconds'] = max(float(accessor(b, bb, s['input'])[-1, 0]) for s in new['samplers'])
        for sa, sb in zip(old['samplers'], new['samplers'], strict=True):
            ta = accessor(a, ab, sa['input']).ravel(); tb = accessor(b, bb, sb['input']).ravel()
            va = accessor(a, ab, sa['output']).reshape(len(ta), -1); vb = accessor(b, bb, sb['output']).reshape(len(tb), -1)
            assert ta[0] == tb[0] and ta[-1] == tb[-1]
            assert np.array_equal(va[[0, -1]], vb[[0, -1]])
            assert np.isfinite(vb).all() and np.all(np.diff(tb) > 0)
            maximum_rate = max(maximum_rate, float(1 / np.diff(tb).min()))
    assert maximum_rate <= fps
    source_raw, draft_raw = source.stat().st_size, candidate.stat().st_size
    package = lambda p: len(zstandard.ZstdCompressor(level=3).compress(p.read_bytes())) + 56
    before, after = inspect_glb(source), inspect_glb(candidate)
    for name, audit in [('before', before), ('after', after)]:
        (output / f'{name}-components.json').write_text(json.dumps(audit, indent=2) + '\n', encoding='utf-8', newline='\n')
    report = {'source_bake_fps': manifest['source_bake_fps'], 'source_path': str(source), 'actor': actor, 'status': 'draft_not_installed_or_artist_approved', 'source_sha256': digest(source), 'candidate_sha256': digest(candidate), 'maximum_nominal_samples_per_second': fps, 'maximum_float32_interval_rate': maximum_rate, 'source_bytes': source_raw, 'candidate_bytes': draft_raw, 'source_rlcz_bytes': package(source), 'candidate_rlcz_bytes': package(candidate), 'clips': clips, 'static_mesh_skin_skeleton_rest_morph_targets_material_images': 'exactly preserved', 'runtime_bake_fps': fps, 'packing': packing, 'limits': 'Approximate animation draft. Surface/contact/normal and runtime measurements are separate evidence; no old lossless acceptance claimed. RLCZ bytes include the 56-byte header, using packaging Zstandard level 3.'}
    (output / 'build-report.json').write_text(json.dumps(report, indent=2) + '\n', encoding='utf-8', newline='\n')
    print(json.dumps(report, indent=2))
    return report

if __name__ == '__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--actor',default='crystalback_tortoise')
    parser.add_argument('--fps',type=int,choices=[30,240],default=30)
    args=parser.parse_args();build(args.actor,args.fps)
