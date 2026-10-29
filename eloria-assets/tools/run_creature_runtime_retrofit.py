"""Run hash-bound creature optimization in largest-first batches of five.

The private handoff selects installed sets versus newer local drafts. This
worker writes candidates and evidence only; runtime promotion is separate.
"""
from pathlib import Path
import argparse
import json
import os
import sys
import time
import traceback

os.environ['OPENBLAS_NUM_THREADS'] = '2'
os.environ['OMP_NUM_THREADS'] = '2'
sys.dont_write_bytecode = True
sys.path.insert(0, str(Path(__file__).resolve().parent))
from optimize_creature_sampling import sample
from video_motion.asset import digest


def save(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + '.tmp')
    temporary.write_text(json.dumps(data, indent=2) + '\n', encoding='utf-8', newline='\n')
    temporary.replace(path)


def run(manifest, output, batches, phase='sample', iterations=6, project=None, actors=None):
    manifest, output = Path(manifest).resolve(), Path(output).resolve()
    if not output.is_relative_to(Path.cwd().resolve()) or '.local' not in output.parts:
        raise ValueError('Worker output must be inside this task worktree\'s ignored .local folder')
    plan = json.loads(manifest.read_text(encoding='utf-8'))
    records = []
    for actor in plan['actors']:
        if actor.get('batch') not in batches or (actors is not None and actor['id'] not in actors):
            continue
        folder = output / actor['id']
        source = Path(actor['source'])
        record = {'actor': actor['id'], 'batch': actor['batch'], 'phase': phase,
                  'source_sha256': actor['sha256'], 'manifest_sha256': digest(manifest),
                  'source_bytes': actor['source_bytes'], 'was_installed': actor['was_installed'],
                  'selected_local_draft': actor['selected_local_draft']}
        started = time.monotonic()
        try:
            if digest(source) != actor['sha256']:
                raise ValueError('Frozen source changed')
            if phase == 'sample':
                result = sample(source, folder / 'sampled.glb', expected_sha256=actor['sha256'],
                                report=folder / 'sampling.json')
                record.update(status='sampled', candidate=str(folder / 'sampled.glb'),
                              candidate_sha256=result['candidate_sha256'], candidate_bytes=result['candidate_bytes'],
                              cadence_exceptions=result['cadence_exceptions'], measurements=result['native_measurements'])
            elif phase == 'close':
                from check_creature_runtime_client import check
                if project is None:
                    raise ValueError('Close-match search requires a prepared isolated --project')
                measured = json.loads((folder / 'client-sample/client-validation.json').read_text(encoding='utf-8'))
                first = measured['summary']['all']
                # This is a cost heuristic, never an acceptance prediction.
                # Difficult corrective caches retain their 30 Hz review/bake
                # candidates rather than silently raising the quality budget.
                eligible = actor['targets'] == 0 or (first['maximum_position_mm'] <= 64 and first['maximum_normal_degrees'] <= 32)
                record['attempts'] = []
                record['close_match'] = False
                if not eligible:
                    record.update(status='review_required', reason='Large measured sampling difference; existing reference retained')
                else:
                    rates = [120, 240] if first['maximum_position_mm'] <= 16 and first['maximum_normal_degrees'] <= 8 else [240]
                    for rate in rates:
                        candidate = folder / f'sampled-{rate}.glb'
                        result = sample(source, candidate, fps=rate, expected_sha256=actor['sha256'],
                                        report=folder / f'sampling-{rate}.json')
                        result_client = check(actor['id'], source, candidate, folder / f'client-{rate}',
                                              client_root=Path(__file__).resolve().parents[2], project=project, prepare=False,
                                              source_sha256=actor['sha256'], candidate_sha256=result['candidate_sha256'],
                                              position_limit_mm=1.0, normal_limit_degrees=.5)
                        record['attempts'].append({'fps': rate, 'candidate': str(candidate), 'sha256': result['candidate_sha256'],
                                                   'raw_bytes': result['candidate_bytes'], 'client_summary': result_client['summary']['all'],
                                                   'close_match': result_client['within_requested_limits']})
                        if result_client['within_requested_limits']:
                            record.update(close_match=True, candidate=str(candidate), candidate_sha256=result['candidate_sha256'],
                                          candidate_bytes=result['candidate_bytes'], fps=rate)
                            break
                    record['status'] = 'close_measured' if record['close_match'] else 'review_required'
            else:
                sampled = folder / 'sampled.glb'
                prior = json.loads((folder / 'sampling.json').read_text(encoding='utf-8'))
                if digest(sampled) != prior['candidate_sha256'] or prior['source_sha256'] != actor['sha256']:
                    raise ValueError('Sampled candidate changed or belongs to another source')
                if phase == 'bake':
                    from video_motion.creature_bake_fit import bake
                    baked, baking_report = folder / 'baked.glb', folder / 'baking.json'
                    if baked.exists() and baking_report.exists():
                        result = json.loads(baking_report.read_text(encoding='utf-8'))
                        if result['source_sha256'] != digest(sampled) or result['sha256'] != digest(baked):
                            raise ValueError('Existing bake differs from recorded input/output; preserve and reconcile it')
                        record['resumed'] = True
                    else:
                        result = bake(sampled, baked, iterations=iterations, report=baking_report,
                                      allow_step_exceptions=bool(prior['cadence_exceptions']))
                    record.update(status='bake_evaluated', baking=result)
                else:
                    from check_creature_runtime_client import check
                    if project is None:
                        raise ValueError('Client QA requires a prepared isolated --project')
                    candidate = sampled if phase == 'client-sample' else folder / 'baked.glb'
                    reference = source if phase in ('client-sample', 'client-final') else sampled
                    result = check(actor['id'], reference, candidate, folder / phase,
                                   client_root=Path(__file__).resolve().parents[2], project=project, prepare=False,
                                   source_sha256=digest(reference), candidate_sha256=digest(candidate))
                    record.update(status='client_measured', client=result)
        except Exception as error:
            record.update(status='error', error=str(error), traceback=traceback.format_exc())
        record['seconds'] = time.monotonic() - started
        save(folder / f'{phase}-state.json', record)
        records.append(record)
        save(output / f'{phase}-progress.json', {'manifest_sha256': digest(manifest), 'phase': phase,
                                               'batches': sorted(batches), 'actors': records})
        print(json.dumps({k: record[k] for k in ('actor', 'batch', 'status', 'seconds')}), flush=True)
    return records


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--manifest', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--batches', required=True, help='Comma-separated batch numbers')
    parser.add_argument('--phase', choices=['sample', 'bake', 'client-sample', 'client-bake', 'client-final', 'close'], default='sample')
    parser.add_argument('--iterations', type=int, default=6)
    parser.add_argument('--project', type=Path)
    parser.add_argument('--actors', help='Optional comma-separated actor subset for recorded retries')
    args = parser.parse_args()
    records = run(args.manifest, args.output, {int(x) for x in args.batches.split(',')}, args.phase, args.iterations,
                  args.project, None if args.actors is None else set(args.actors.split(',')))
    raise SystemExit(1 if any(row['status'] == 'error' for row in records) else 0)
