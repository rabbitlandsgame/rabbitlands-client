"""Open the hash-checked, local Crystalback Tortoise corrective repair pilot.

The inputs and authoring evidence live in ignored .local storage. This preview
uses the actual client actor/importer without changing the installed model.
"""
from pathlib import Path
import argparse
import json
import os
import shutil
import subprocess

from video_motion.asset import digest

ROOT = Path(__file__).resolve().parents[2]


def prepare(godot, variant='rebasis'):
    output = ROOT / '.local/tortoise-corrective-repair'
    receipt = ROOT / 'docs/qa/creature-storage/crystalback-tortoise-corrective-repair.json'
    evidence = json.loads(receipt.read_text(encoding='utf-8'))
    models = []
    records = evidence['models'] if variant == 'skin' else [evidence['models'][0], evidence['control']]
    for record in records:
        path = ROOT / record['artifact']
        if not path.is_file() or digest(path) != record['sha256']:
            raise RuntimeError(f'Missing or changed private pilot input: {path}. Preserve and reconcile authoring evidence before previewing.')
        models.append({'path': str(path), 'sha256': record['sha256'], 'label': record['label']})
    project = output / 'client-preview'
    project.mkdir(parents=True, exist_ok=True)
    client = ROOT / 'godot-client'
    for directory in ['src', 'data', 'addons', 'assets/ui']:
        shutil.copytree(client / directory, project / directory, dirs_exist_ok=True,
                        ignore=shutil.ignore_patterns('__pycache__', '*.pyc', '*.import'))
    (project / 'prototypes').mkdir(exist_ok=True)
    shutil.copy2(client / 'prototypes/creature_animation_comparison.gd', project / 'prototypes/creature_animation_comparison.gd')
    (project / 'project.godot').write_text('''config_version=5
[application]
config/name="Rabbit Lands - Tortoise corrective repair"
[display]
window/size/viewport_width=1440
window/size/viewport_height=920
[rendering]
renderer/rendering_method="forward_plus"
''', encoding='utf-8', newline='\n')
    environment = dict(os.environ, APPDATA=str(output / 'preview-profile/roaming'), LOCALAPPDATA=str(output / 'preview-profile/local'))
    for key in ['APPDATA', 'LOCALAPPDATA']:
        Path(environment[key]).mkdir(parents=True, exist_ok=True)
    a, b = records
    count = b['corrective_targets']
    job = {'actor': 'crystalback_tortoise', 'display_name': 'Crystalback Tortoise', 'fps': 30,
           'title': 'Rabbit Lands | Tortoise corrective repair pilot',
           'heading': 'Crystalback Tortoise / Corrective repair pilot',
           'description': f"Both use 30 FPS. Right: {count} corrective shapes; {'revised skin weights' if variant == 'skin' else 'original mesh and skin weights retained'}. Approximate draft for review.",
           'clips': evidence['clips'], 'models': models, 'output': str(output / ('preview-captures' if variant == 'skin' else 'control-preview-captures')),
           'summary': f"Raw {a['raw_bytes']/1e6:.2f} -> {b['raw_bytes']/1e6:.2f} MB | Packaged {a['rlcz_bytes']/1e6:.2f} -> {b['rlcz_bytes']/1e6:.2f} MB | Drag / zoom either pane to move both cameras.",
           'runtime_summary': f"21 bones and four skin influences retained. Corrective GPU buffers: {a['corrective_gpu_buffer_bytes']/1e6:.2f} -> {b['corrective_gpu_buffer_bytes']/1e6:.2f} MB. Installed model unchanged.",
           'review_points': evidence.get('preview_review_points' if variant == 'skin' else 'control_preview_review_points', [])}
    job_path = output / f'preview-job-{variant}.json'
    job_path.write_text(json.dumps(job, indent=2) + '\n', encoding='utf-8', newline='\n')
    with (output / 'preview-import.stdout.log').open('w') as stdout, (output / 'preview-import.stderr.log').open('w') as stderr:
        subprocess.run([str(godot), '--headless', '--editor', '--import', '--path', str(project)],
                       env=environment, stdout=stdout, stderr=stderr,
                       creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0,
                       check=True, timeout=240)
    errors = (output / 'preview-import.stderr.log').read_text(encoding='utf-8')
    assert not any(token in errors for token in ['ERROR:', 'SCRIPT ERROR:']), errors[-3000:]
    return output, project, job_path, environment


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--godot', type=Path, default=Path(os.environ.get('GODOT', 'C:/rabbitlands/rabbitlands-client/godot-client/Godot_v4.7.2-stable_win64.exe')))
    parser.add_argument('--prepare-only', action='store_true')
    parser.add_argument('--smoke', action='store_true')
    parser.add_argument('--variant', choices=['rebasis', 'skin'], default='rebasis', help='Compare fewer shapes with the original skin, or the skin repair experiment')
    args = parser.parse_args()
    output, project, job, environment = prepare(args.godot, args.variant)
    print('TORTOISE_REPAIR_PREVIEW_PREPARED', project, flush=True)
    if args.prepare_only:
        return
    command = [str(args.godot), '--path', str(project), '--script', 'res://prototypes/creature_animation_comparison.gd', '--', str(job)]
    if args.smoke:
        command.append('--smoke')
    with (output / 'preview.stdout.log').open('w') as stdout, (output / 'preview.stderr.log').open('w') as stderr:
        subprocess.run(command, env=environment, stdout=stdout, stderr=stderr,
                       creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0,
                       check=True, timeout=180 if args.smoke else None)
    errors = (output / 'preview.stderr.log').read_text(encoding='utf-8')
    assert 'ERROR:' not in errors, errors[-3000:]
    if args.smoke:
        assert 'CREATURE_COMPARISON_SMOKE_PASS' in (output / 'preview.stdout.log').read_text(encoding='utf-8')


if __name__ == '__main__':
    main()
