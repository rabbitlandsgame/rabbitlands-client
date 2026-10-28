"""Measure the foal draft in fresh isolated client-component processes.

Uses a headless renderer; results describe CPU animation work and Godot memory,
not whole-client FPS or GPU time. Output stays in .local/foal-240-draft.
"""
import argparse
import json
import os
from pathlib import Path
import statistics
import subprocess

from preview_foal_240 import OUTPUT, prepare


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--godot', type=Path, default=Path(os.environ.get('GODOT', 'C:/rabbitlands/rabbitlands-client/godot-client/Godot_v4.7.2-stable_win64.exe')))
    parser.add_argument('--repeats', type=int, default=3)
    args = parser.parse_args()
    project, job_path, environment = prepare(args.godot)
    fixtures = json.loads(job_path.read_text())['models']
    records = [[], []]
    for repeat in range(args.repeats):
        for index in ([0, 1] if repeat % 2 == 0 else [1, 0]):
            prefix = OUTPUT / f'benchmark-{index}-{repeat}'
            job = {**fixtures[index], 'report': str(prefix.with_suffix('.json'))}
            prefix.with_name(prefix.name + '-job.json').write_text(json.dumps(job))
            with prefix.with_suffix('.stdout.log').open('w') as out, prefix.with_suffix('.stderr.log').open('w') as err:
                subprocess.run([str(args.godot), '--headless', '--path', str(project), '--script', 'res://tests/benchmark_foal_animation.gd', '--', str(prefix.with_name(prefix.name + '-job.json'))], env=environment, stdout=out, stderr=err, check=True, timeout=240, creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0)
            errors = prefix.with_suffix('.stderr.log').read_text()
            assert not any(token in errors for token in ['ERROR:', 'SCRIPT ERROR:']), errors
            record = json.loads(prefix.with_suffix('.json').read_text())
            records[index].append(record)
            print('BENCH', index, repeat, record['load_ms'], record['retained_static_memory_delta_bytes'], flush=True)
    summary = {'repeats_per_version': args.repeats, 'models': fixtures, 'versions': []}
    for rows in records:
        entry = {key: statistics.median(row[key] for row in rows) for key in ['load_ms', 'retained_static_memory_delta_bytes', 'load_peak_static_memory_increase_bytes', 'retargeted_keys', 'retargeted_tracks', 'bones']}
        entry['animation_update_usec'] = {name: statistics.median(row['animation_update'][name]['median_usec_per_update'] for row in rows) for name in rows[0]['animation_update']}
        entry['raw_runs'] = rows
        summary['versions'].append(entry)
    summary['scope'] = records[0][0]['scope']
    (OUTPUT / 'runtime-measurements.json').write_text(json.dumps(summary, indent=2) + '\n', encoding='utf-8', newline='\n')
    print(json.dumps({k:v for k,v in summary.items() if k != 'versions'}, indent=2))
    for entry in summary['versions']: print({k:v for k,v in entry.items() if k != 'raw_runs'})


if __name__ == '__main__': main()
