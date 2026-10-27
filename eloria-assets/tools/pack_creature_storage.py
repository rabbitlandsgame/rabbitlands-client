"""Prepare exact storage reductions and optional qualified island partitions.

This produces a candidate and hash-bound receipt; it does not install assets.
Keep the source immutable and qualify Blender/Godot playback and appearance
before copying any candidate into the runtime asset tree.
"""
import argparse
import json
import math
from pathlib import Path

from video_motion.asset import digest, read_glb, write_glb
from video_motion.creature_storage import prune_zero_targets
from video_motion.exact_animation_packing import reduce_constant_runs
from video_motion.partial_correctives import split_corrective_partition
from video_motion.packing import compact


def prepare(source, output, profile=None, bounds=None):
    if source.resolve() == output.resolve():
        raise ValueError('The original source must remain immutable')
    source_hash = digest(source)
    if profile is not None and profile.get('source_sha256') != source_hash:
        raise ValueError('Partition profile does not match source SHA256')
    document, binary = read_glb(source)
    document, binary, inactive = prune_zero_targets(document, binary)
    document, binary, runs = reduce_constant_runs(document, binary)
    partition = None
    if profile is not None:
        node = document['nodes'][int(profile['source_node'])]
        primitive = document['meshes'][node['mesh']]['primitives'][int(profile.get('primitive', 0))]
        if primitive.get('targets'):
            document, binary, partition = split_corrective_partition(document, binary, profile)
        else:
            partition = {'skipped': 'Exact pruning already removed all corrective storage; original skin retained'}
    if bounds is not None:
        if bounds.get('source_sha256') != source_hash:
            raise ValueError('Logical actor bounds do not match source SHA256')
        for record in bounds['meshes']:
            vectors = [record['position'], record['size']]
            if any(len(v) != 3 or any(type(x) not in (int, float) or not math.isfinite(x) or abs(x) > 3.4e38 for x in v) for v in vectors) or min(record['size']) < 0 or max(record['size']) <= 0:
                raise ValueError('Invalid original logical actor bounds')
            source_node = int(record['source_node'])
            mesh_ids = [document['nodes'][source_node]['mesh']]
            if partition and partition.get('source_node') == source_node:
                mesh_ids.append(document['nodes'][partition['new_node']]['mesh'])
            for mesh_id in mesh_ids:
                extras = document['meshes'][mesh_id].setdefault('extras', {})
                extras['rabbitlands_actor_bounds_v1'] = {key: record[key] for key in ('position', 'size')}
                if record['size'][1] > 0:
                    extras['rabbitlands_coat_pattern_height'] = record['size'][1]
    document, binary, packing = compact(document, binary)
    output.parent.mkdir(parents=True, exist_ok=True)
    write_glb(output, document, binary)
    return {'source_sha256': source_hash, 'candidate_sha256': digest(output),
            'source_bytes': source.stat().st_size, 'candidate_bytes': output.stat().st_size,
            'inactive_targets': inactive, 'constant_runs': runs,
            'partition': partition, 'logical_actor_bounds': bounds, 'packing': packing,
            'qualification': 'candidate only; source, independent import and runtime visual checks required'}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--profile', type=Path)
    parser.add_argument('--bounds', type=Path, help='Hash-bound original Godot mesh bounds; preserves actor placement after unused envelopes are removed')
    parser.add_argument('--report', type=Path, required=True)
    args = parser.parse_args()
    profile = json.loads(args.profile.read_text(encoding='utf-8')) if args.profile else None
    bounds = json.loads(args.bounds.read_text(encoding='utf-8')) if args.bounds else None
    report = prepare(args.source, args.output, profile, bounds)
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps(report, indent=2) + '\n', encoding='utf-8', newline='\n')
    print('CREATURE_STORAGE_CANDIDATE', report['source_bytes'], report['candidate_bytes'])


if __name__ == '__main__':
    main()
