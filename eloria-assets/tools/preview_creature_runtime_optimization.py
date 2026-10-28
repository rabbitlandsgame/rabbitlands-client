"""Compare any hash-bound creature sampling/bake candidate in the real client."""
from pathlib import Path
import argparse
import json
import os
import shutil
import subprocess
from video_motion.asset import read_glb, digest

ROOT = Path(__file__).resolve().parents[2]
GODOT = Path('C:/rabbitlands/rabbitlands-client/godot-client/Godot_v4.7.2-stable_win64.exe')


def prepare(actor, source, candidate, output, godot=GODOT, source_label='REFERENCE', candidate_label='DRAFT'):
    source, candidate, output = map(lambda p: Path(p).resolve(), (source, candidate, output))
    if '.local' not in output.parts:
        raise ValueError('Comparison projects and evidence belong under ignored .local storage')
    original, _ = read_glb(source)
    draft, _ = read_glb(candidate)
    clips = [a['name'] for a in original['animations'] if a['name'] != 'RESET']
    if set(clips) != {a['name'] for a in draft['animations'] if a['name'] != 'RESET'}:
        raise ValueError('Complete animation sets differ')
    project = output / 'project'
    if source.is_relative_to(project) or candidate.is_relative_to(project):
        raise ValueError('Source models must be outside the generated comparison project')
    project.mkdir(parents=True, exist_ok=True)
    for relative in ['src', 'data', 'addons', 'assets/ui']:
        shutil.copytree(ROOT / 'godot-client' / relative, project / relative, dirs_exist_ok=True,
                        ignore=shutil.ignore_patterns('__pycache__', '*.pyc', '*.import'))
    (project / 'prototypes').mkdir(exist_ok=True)
    shutil.copy2(ROOT / 'godot-client/prototypes/creature_animation_comparison.gd', project / 'prototypes/creature_animation_comparison.gd')
    (project / 'project.godot').write_text('''config_version=5
[application]
config/name="Rabbit Lands - Creature delivery review"
[display]
window/size/viewport_width=1440
window/size/viewport_height=920
[rendering]
renderer/rendering_method="forward_plus"
''', encoding='utf-8', newline='\n')
    target_counts = lambda d: [len(p.get('targets', [])) for m in d['meshes'] for p in m['primitives']]
    job = {'actor': actor, 'display_name': actor.replace('_', ' ').title(), 'fps': 30,
           'heading': actor.replace('_', ' ').title() + ' / Delivery optimization review',
           'description': 'Synchronized full animation sets. Draft appearance and movement require review.',
           'clips': clips, 'models': [{'label': source_label, 'path': str(source), 'sha256': digest(source)},
                                    {'label': candidate_label, 'path': str(candidate), 'sha256': digest(candidate)}],
           'summary': f'Raw GLB {source.stat().st_size/1e6:.2f} -> {candidate.stat().st_size/1e6:.2f} MB | Drag / zoom either pane to move both cameras.',
           'runtime_summary': f'Corrective slots (maximum per primitive): {max(target_counts(original), default=0)} -> {max(target_counts(draft), default=0)}. Ordinary GLBs; this viewer does not change the installed selection.',
           'output': str(output / 'captures')}
    job_path = output / 'job.json'
    job_path.write_text(json.dumps(job, indent=2) + '\n', encoding='utf-8', newline='\n')
    env = dict(os.environ, APPDATA=str(output / 'profile/roaming'), LOCALAPPDATA=str(output / 'profile/local'))
    for key in ['APPDATA', 'LOCALAPPDATA']: Path(env[key]).mkdir(parents=True, exist_ok=True)
    flags = subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0
    with (output / 'import.stdout.log').open('w') as stdout, (output / 'import.stderr.log').open('w') as stderr:
        subprocess.run([str(godot), '--headless', '--editor', '--import', '--path', str(project)],
                       env=env, stdout=stdout, stderr=stderr, creationflags=flags, check=True, timeout=240)
    errors = (output / 'import.stderr.log').read_text(encoding='utf-8')
    if 'ERROR:' in errors: raise RuntimeError(errors[-3000:])
    return project, job_path, env


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--actor', required=True)
    parser.add_argument('--source', type=Path, required=True)
    parser.add_argument('--candidate', type=Path, required=True)
    parser.add_argument('--output', type=Path)
    parser.add_argument('--godot', type=Path, default=GODOT)
    parser.add_argument('--source-label', default='REFERENCE')
    parser.add_argument('--candidate-label', default='DRAFT')
    parser.add_argument('--prepare-only', action='store_true')
    parser.add_argument('--smoke', action='store_true')
    args = parser.parse_args()
    output = args.output or ROOT / '.local/creature-runtime-retrofit/review' / args.actor
    project, job, env = prepare(args.actor, args.source, args.candidate, output, args.godot, args.source_label, args.candidate_label)
    print('CREATURE_REVIEW_PREPARED', job, flush=True)
    if not args.prepare_only:
        command = [str(args.godot), '--path', str(project), '--script', 'res://prototypes/creature_animation_comparison.gd', '--', str(job)]
        if args.smoke: command.append('--smoke')
        with (output / 'preview.stdout.log').open('w') as stdout, (output / 'preview.stderr.log').open('w') as stderr:
            subprocess.run(command, env=env, stdout=stdout, stderr=stderr, check=True,
                           creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0,
                           timeout=240 if args.smoke else None)
        errors = (output / 'preview.stderr.log').read_text(encoding='utf-8')
        if 'ERROR:' in errors: raise RuntimeError(errors[-3000:])
        if args.smoke:
            assert 'CREATURE_COMPARISON_SMOKE_PASS' in (output / 'preview.stdout.log').read_text(encoding='utf-8')
