"""Replay every canonical wearer and summarize full-cycle equipment stretch.

Each worker writes its complete edge measurements as well as a small summary.
No asset or animation is modified. Run after a candidate batch has completed.
"""
from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
import json
import os
from pathlib import Path
import subprocess
import sys


def audit(directory, output, races, jobs):
    output.mkdir(parents=True, exist_ok=True)
    script = Path(__file__).with_name('replay_canonical_equipment.py')
    environment = dict(os.environ, OPENBLAS_NUM_THREADS='1', OMP_NUM_THREADS='1')

    def run(race):
        report = output / (race + '.json')
        if report.exists():
            raise FileExistsError(f'Use a new report directory: {report}')
        paths = sorted((directory / race).glob('*.glb'))
        if len(paths) != 264:
            raise ValueError(f'Incomplete wearer: {race}, {len(paths)} pieces')
        with report.with_suffix('.log').open('x') as log:
            subprocess.run([sys.executable, str(script), str(directory / race),
                            '--race', race, '--out', str(report)],
                           stdout=log, stderr=subprocess.STDOUT, env=environment, check=True)
        data = json.loads(report.read_text())
        rows = [dict(row, clip=clip) for clip, measurements in data['clips'].items()
                for row in measurements]
        summary = {'race': race, 'records': len(rows), 'assets': len(paths),
                   'worst_max': max(rows, key=lambda r: r['max_extension_mm']),
                   'worst_p99': max(rows, key=lambda r: r['p99_extension_mm']),
                   'max_loop_error_mm': max(r['loop_error_mm'] for r in rows)}
        print(f"REPLAY {race}: {len(rows)} surfaces/clips; "
              f"max {summary['worst_max']['max_extension_mm']:.2f} mm; "
              f"p99 {summary['worst_p99']['p99_extension_mm']:.2f} mm", flush=True)
        return summary

    summaries = []
    with ThreadPoolExecutor(max_workers=jobs) as pool:
        futures = [pool.submit(run, race) for race in races]
        for future in as_completed(futures):
            summaries.append(future.result())
    summaries.sort(key=lambda row: row['race'])
    with (output / 'summary.json').open('x') as handle:
        json.dump(summaries, handle, indent=2, allow_nan=False)
        handle.write('\n')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('directory', type=Path)
    parser.add_argument('--out', required=True, type=Path)
    parser.add_argument('--races', default='all')
    parser.add_argument('--jobs', type=int, default=4)
    args = parser.parse_args()
    races = sorted(p.name for p in args.directory.iterdir() if p.is_dir()) \
        if args.races == 'all' else args.races.split(',')
    audit(args.directory, args.out, races, args.jobs)
