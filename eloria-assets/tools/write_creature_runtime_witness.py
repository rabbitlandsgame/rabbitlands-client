"""Write regression observations for an explicitly selected optimized creature.

These observations pin the new candidate; they do not replace frozen authoring
observations or prove visual equivalence to an earlier model.
"""
from pathlib import Path
import argparse
import json
import numpy as np
from video_motion.asset import digest, accessor
from video_motion.native_shapes import NativeShapeAsset
from video_motion.runtime_validation import surface_sampler
from test_completed_creature_motion import normal_sampler


def write(source, output, *, reference_sha256, ids=None, height=None):
    asset = NativeShapeAsset(source)
    if ids is None:
        count = len(asset.vertices)
        ids = np.unique(np.r_[np.linspace(0, count - 1, min(96, count)).astype(int),
                              asset.vertices.argmin(0), asset.vertices.argmax(0)])
    ids = np.asarray(ids, int)
    height = float(height or np.ptp(asset.vertices, axis=0)[1])
    sample, normal = surface_sampler(asset, ids), normal_sampler(asset, ids)
    result = {'sha256': digest(source), 'reference_sha256': reference_sha256,
              'height': height, 'bake_fps': asset.d['asset'].get('extras', {}).get('rabbitlands_animation_bake_fps', 30),
              'scope': 'Regression observations of the selected optimized candidate, not replacement physical observations or a source-equivalence claim.',
              'surface_vertex_ids': ids.tolist(), 'surface_rest': sample(asset.rest, asset.default_weights).tolist(),
              'surface_rest_normals': normal(asset.rest, asset.default_weights).tolist(),
              'surface_numeric_tolerance_over_height': 1e-8, 'normal_numeric_tolerance': 1e-8,
              'durations': {}, 'clips': {}}
    for clip in asset.animations:
        duration = asset.duration(clip)
        result['durations'][clip] = duration
        times = duration * np.array([0, .03713, .29381, .49913, .73129, .93317, 1.0])
        translations, rotations, scales, morphs = asset.sample(clip, times)
        entries = []
        for index, time in enumerate(times):
            world = asset.world(translations[index], rotations[index], scales[index])
            weights = {node: values[index] for node, values in morphs.items()}
            entries.append({'time': float(time), 'bones': {asset.names[node]: world[node].reshape(-1).tolist() for node in asset.joints},
                            'morph_weights': {asset.names[node]: value.tolist() for node, value in weights.items() if len(value)},
                            'surface': sample(world, weights).tolist(), 'surface_normals': normal(world, weights).tolist()})
        result['clips'][clip] = entries
    Path(output).parent.mkdir(parents=True, exist_ok=True)
    Path(output).write_text(json.dumps(result, separators=(',', ':')) + '\n', encoding='utf-8', newline='\n')
    return result


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--reference-sha256', required=True)
    args = parser.parse_args()
    write(args.source, args.output, reference_sha256=args.reference_sha256)
