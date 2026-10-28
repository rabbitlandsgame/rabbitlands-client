"""Build the eight-clip Dun foal sampling pilot; never replace the roster asset.

Run from the client repository: python eloria-assets/tools/build_foal_240_draft.py
Requires numpy, scipy and zstandard. Output and evidence are local-only.
"""
from __future__ import annotations

import argparse
import copy
import json
import math
from pathlib import Path

import numpy as np
from scipy.spatial.transform import Rotation, Slerp
import zstandard

from video_motion.asset import accessor, digest, read_glb, write_glb
from video_motion.packing import append_array, compact

ROOT = Path(__file__).resolve().parents[2]
SOURCE = ROOT / 'godot-client/assets/actors/native/creatures/sunmane_foal_dun.glb'
SOURCE_SHA = 'b15e77e1b20a7eb768e0313fe4a49518b9b3e8403e0b429d61cc741706426f8a'
OUTPUT = ROOT / '.local/foal-240-draft'


def uniform_clock(start, end, rate):
    # Distribute the endpoint remainder across the whole clip: appending a short
    # final interval would accidentally exceed the requested maximum cadence.
    intervals = max(1, math.floor((end - start) * rate - 1e-4))
    return np.linspace(start, end, intervals + 1, dtype=np.float32)


def resample(times, values, query, rotation=False):
    if len(times) == 1:
        return np.repeat(values[:1], len(query), axis=0)
    if rotation:
        return Slerp(times, Rotation.from_quat(values))(query).as_quat()
    right = np.clip(np.searchsorted(times, query, side='right'), 1, len(times) - 1)
    left = right - 1
    alpha = ((query - times[left]) / (times[right] - times[left]))[:, None]
    return values[left] * (1 - alpha) + values[right] * alpha


def verify_static(a, ab, b, bb):
    # Accessor/view IDs change during compaction; compare their decoded data and
    # all non-buffer mesh/skin metadata independently of those IDs.
    for field in ['nodes', 'scenes', 'scene', 'materials', 'textures', 'samplers']:
        assert a.get(field) == b.get(field), field
    for am, bm in zip(a['meshes'], b['meshes'], strict=True):
        aa, ba = copy.deepcopy(am), copy.deepcopy(bm)
        for ap, bp in zip(aa['primitives'], ba['primitives'], strict=True):
            for key in ap['attributes']:
                assert np.array_equal(accessor(a, ab, ap['attributes'][key]), accessor(b, bb, bp['attributes'][key]))
            for at, bt in zip(ap.get('targets', []), bp.get('targets', []), strict=True):
                for key in at:
                    assert np.array_equal(accessor(a, ab, at[key]), accessor(b, bb, bt[key]))
                    bt[key] = at[key]
            if 'indices' in ap:
                assert np.array_equal(accessor(a, ab, ap['indices']), accessor(b, bb, bp['indices']))
                bp['indices'] = ap['indices']
            bp['attributes'] = ap['attributes']
        assert aa == ba
    for sa, sb in zip(a['skins'], b['skins'], strict=True):
        sb = copy.deepcopy(sb)
        assert np.array_equal(accessor(a, ab, sa['inverseBindMatrices']), accessor(b, bb, sb['inverseBindMatrices']))
        sb['inverseBindMatrices'] = sa['inverseBindMatrices']
        assert sa == sb
    for ia, ib in zip(a['images'], b['images'], strict=True):
        va, vb = a['bufferViews'][ia['bufferView']], b['bufferViews'][ib['bufferView']]
        assert ab[va.get('byteOffset', 0):va.get('byteOffset', 0)+va['byteLength']] == bb[vb.get('byteOffset', 0):vb.get('byteOffset', 0)+vb['byteLength']]
        assert {k:v for k,v in ia.items() if k != 'bufferView'} == {k:v for k,v in ib.items() if k != 'bufferView'}


def build(source=SOURCE, output=None, fps=240):
    assert fps in (30, 240)
    output = output or ROOT / f'.local/foal-{fps}-draft'
    assert digest(source) == SOURCE_SHA, 'Baseline changed; review and rebind this pilot explicitly.'
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
    d['asset']['extras']['rabbitlands_sampling_pilot'] = {'status': 'draft_for_comparison', 'source_sha256': SOURCE_SHA, 'maximum_samples_per_second': fps, 'method': 'uniform per-sampler LINEAR / quaternion SLERP; preserve endpoints and all channels'}
    d, blob, packing = compact(d, blob)
    candidate = output / f'sunmane_foal_dun_{fps}.glb'
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
    report = {'actor': 'sunmane_foal_dun', 'status': 'draft_not_installed_or_artist_approved', 'source_sha256': digest(source), 'candidate_sha256': digest(candidate), 'maximum_nominal_samples_per_second': fps, 'maximum_float32_interval_rate': maximum_rate, 'source_bytes': source_raw, 'candidate_bytes': draft_raw, 'source_rlcz_bytes': package(source), 'candidate_rlcz_bytes': package(candidate), 'clips': clips, 'static_mesh_skin_skeleton_rest_morph_targets_material_images': 'exactly preserved', 'runtime_bake_fps': fps, 'packing': packing, 'limits': 'Approximate animation draft. Surface/contact/normal and runtime measurements are separate evidence; no old lossless acceptance claimed. RLCZ bytes include the 56-byte header, using packaging Zstandard level 3.'}
    (output / 'build-report.json').write_text(json.dumps(report, indent=2) + '\n', encoding='utf-8', newline='\n')
    print(json.dumps(report, indent=2))
    return report


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--fps', type=int, choices=[30, 240], default=240)
    parser.add_argument('--output', type=Path)
    args = parser.parse_args()
    build(output=args.output, fps=args.fps)
