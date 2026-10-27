"""Rebind current creature receipts/physical identities without new observations."""
import argparse
import json
import math
import shutil
from pathlib import Path

import numpy as np

from video_motion.asset import digest, read_glb
from video_motion.storage_metadata import remap_witness, remap_vertex_fields, vertex_permutation


def update(root, actor, source, candidate, processing, receipt, profile=None, backup=None):
    old_hash, new_hash = digest(source), digest(candidate)
    if processing['source_sha256'] != old_hash or processing['candidate_sha256'] != new_hash:
        raise ValueError('Processing receipt does not bind original and installed bytes')
    document, _ = read_glb(source)
    permutation = vertex_permutation(document, processing.get('partition'))
    runtime_path = candidate.resolve().relative_to(root.resolve()).as_posix()
    changed = []
    files = list((root/'docs/qa').glob('*/actors.json')) + list((root/'godot-client/tests/fixtures').rglob('*.json'))
    def transform(value, eligible=False):
        if isinstance(value, dict):
            eligible = eligible or value.get('actor') == actor or value.get('runtime_path') == runtime_path
            if eligible and value.get('sha256') == old_hash:
                if 'clips' in value or 'surface_rest' in value:
                    result = remap_witness(value, document, processing.get('inactive_targets', {}),
                                           processing.get('partition'), old_hash, new_hash, profile)
                    if profile and profile.get('numeric_budget') and 'height' in result:
                        budget = profile['numeric_budget']
                        result['representation_numeric_budget'] = {'source_position_ulps': 4,
                            'source_normal_angle_degrees': float(budget['source_normal_angle_limit_degrees'])}
                        result['surface_numeric_tolerance_over_height'] = float(budget['source_position_absolute_limit'])/float(result['height'])
                        result['normal_numeric_tolerance'] = 2*math.sin(math.radians(float(budget['source_normal_angle_limit_degrees']))/2)
                else:
                    result = remap_vertex_fields(value, permutation)
                    result['sha256'] = new_hash
                for field in ('bytes', 'runtime_bytes'):
                    if field in result: result[field] = candidate.stat().st_size
                if 'runtime_path' in result: result['storage_equivalence_report'] = receipt
                return result
            return {key: transform(child, eligible or key == actor) for key, child in value.items()}
        if isinstance(value, list): return [transform(child, eligible) for child in value]
        return value
    for path in files:
        text = path.read_text(encoding='utf-8')
        if old_hash not in text: continue
        data = json.loads(text)
        result = transform(data, path.stem == actor)
        if result == data: continue
        if backup is not None:
            destination = backup/path.relative_to(root); destination.parent.mkdir(parents=True, exist_ok=True)
            if not destination.exists(): shutil.copy2(path, destination)
        options = {'separators': (',', ':')} if text.count('\n') <= 1 else {'indent': 2}
        path.write_text(json.dumps(result, **options)+'\n', encoding='utf-8', newline='\n')
        changed.append(path.relative_to(root).as_posix())
    path = root/'eloria-assets/source/model-development-roster.json'
    roster = json.loads(path.read_text(encoding='utf-8'))
    for row in roster['creatures']:
        if row['id'] == actor:
            if row['sha256'] not in (old_hash, new_hash): raise ValueError('Current roster has a newer/unrelated source')
            row['sha256'] = new_hash
            if 'storage optimized' not in row['status']: row['status'] += '; storage optimized'
    if backup is not None:
        destination = backup/path.relative_to(root); destination.parent.mkdir(parents=True, exist_ok=True)
        if not destination.exists(): shutil.copy2(path, destination)
    path.write_text(json.dumps(roster, indent=2)+'\n', encoding='utf-8', newline='\n')
    changed.append(path.relative_to(root).as_posix())
    return changed


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, default=Path(__file__).resolve().parents[2])
    parser.add_argument('--actor', required=True)
    parser.add_argument('--source', type=Path, required=True)
    parser.add_argument('--candidate', type=Path, required=True)
    parser.add_argument('--processing', type=Path, required=True)
    parser.add_argument('--profile', type=Path)
    parser.add_argument('--receipt', required=True)
    parser.add_argument('--backup', type=Path, required=True)
    args = parser.parse_args()
    processing = json.loads(args.processing.read_text(encoding='utf-8'))
    profile = json.loads(args.profile.read_text(encoding='utf-8')) if args.profile else None
    print(json.dumps(update(args.root, args.actor, args.source, args.candidate, processing, args.receipt, profile, args.backup), indent=2))


if __name__ == '__main__': main()
