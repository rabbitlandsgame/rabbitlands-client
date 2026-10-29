"""Prepare and open the local in-client two-actor creature comparison.

Copies current client scripts/data/UI dependencies into an ignored, isolated
Godot project; uses the real ReplicatedActor3D and native animation importer.
Neither the game's model selection nor player settings are changed.
"""
from __future__ import annotations
import argparse
import json
import os
from pathlib import Path
import shutil
import subprocess

from build_creature_sampling_draft import ROOT, folder, reference, build
from video_motion.asset import digest


def prepare(godot, fps=30, actor="crystalback_tortoise"):
    source, manifest = reference(actor)
    source_sha = manifest["source_sha256"]
    output = folder(actor) / f"fps-{fps}"
    candidate = output / f"{actor}_{fps}.glb"
    report_path = output / 'build-report.json'
    if not candidate.exists() or not report_path.exists():
        build(actor=actor, fps=fps)
    report = json.loads(report_path.read_text())
    assert digest(source) == source_sha and digest(candidate) == report['candidate_sha256'], 'Comparison input changed; rebuild and remeasure.'
    client = ROOT / 'godot-client'
    project = output / 'client-preview'
    project.mkdir(parents=True, exist_ok=True)
    for directory in ['src', 'data', 'addons', 'assets/ui']:
        shutil.copytree(client / directory, project / directory, dirs_exist_ok=True,
                        ignore=shutil.ignore_patterns('__pycache__', '*.pyc', '*.import'))
    (project / 'prototypes').mkdir(exist_ok=True)
    shutil.copy2(client / 'prototypes/creature_animation_comparison.gd', project / 'prototypes/creature_animation_comparison.gd')
    (project / 'tests').mkdir(exist_ok=True)
    shutil.copy2(client / 'tests/benchmark_creature_animation.gd', project / 'tests/benchmark_creature_animation.gd')
    # No editor plugins, game startup, network autoloads or player configuration.
    (project / 'project.godot').write_text('''config_version=5
[application]
config/name="Rabbit Lands - Creature animation comparison"
[display]
window/size/viewport_width=1440
window/size/viewport_height=920
[rendering]
renderer/rendering_method="forward_plus"
''', encoding='utf-8', newline='\n')
    environment = dict(os.environ, APPDATA=str(output / 'profile/roaming'), LOCALAPPDATA=str(output / 'profile/local'))
    for key in ['APPDATA', 'LOCALAPPDATA']: Path(environment[key]).mkdir(parents=True, exist_ok=True)
    job = {'actor': actor, 'display_name': actor.replace('_', ' ').title(), 'clips': manifest['clips'], 'fps': fps, 'models': [
        {'label': f'CURRENT  /  {manifest["source_bake_fps"]:g} Hz runtime bake', 'path': str(source), 'sha256': source_sha},
        {'label': f'DRAFT  /  Maximum {fps} samples per second', 'path': str(candidate), 'sha256': report['candidate_sha256']}],
        'summary': f"Raw: {report['source_bytes']/1e6:.1f} -> {report['candidate_bytes']/1e6:.1f} MB    |    Packaged: {report['source_rlcz_bytes']/1e6:.1f} -> {report['candidate_rlcz_bytes']/1e6:.1f} MB    |    Drag / zoom either pane to move both cameras.",
        'output': str(output / 'preview-captures')}
    motion_path = output / 'motion-measurements.json'
    if motion_path.exists():
        motion = json.loads(motion_path.read_text())
        assert motion['source_sha256'] == source_sha and motion['candidate_sha256'] == report['candidate_sha256']
        job['review_points'] = []
        for key, caption in [('worst_position', 'Largest movement difference'), ('worst_normal', 'Largest normal difference')]:
            if key not in motion: continue
            name, time = motion[key]['label'].split('@')
            assert '->' not in name
            point = {'id': key, 'caption': caption, 'clip': name, 'time': float(time)}
            if 'source_world_position' in motion[key]:
                position = motion[key]['source_world_position']
                point['focus'] = [position[0] - 0.5, position[1], position[2] + 0.5]
            job['review_points'].append(point)
    runtime_path = output / 'runtime-measurements.json'
    if runtime_path.exists():
        runtime = json.loads(runtime_path.read_text())
        assert [model['sha256'] for model in runtime['models']] == [model['sha256'] for model in job['models']]
        current, draft = runtime['versions']
        changes = [100 * (draft['animation_update_usec'][name] / value - 1) for name, value in current['animation_update_usec'].items()]
        job['runtime_summary'] = f"Isolated CPU: shared caches + first actor {current['retained_static_memory_delta_bytes']/1e6:.1f} -> {draft['retained_static_memory_delta_bytes']/1e6:.1f} MB  |  Load {current['load_ms']/1000:.2f} -> {draft['load_ms']/1000:.2f} s  |  Animation CPU cost {min(changes):+.0f}% to {max(changes):+.0f}%  |  GPU buffers unchanged"
    job_path = output / 'preview-job.json'
    job_path.write_text(json.dumps(job, indent=2) + '\n', encoding='utf-8', newline='\n')
    flags = subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0
    with (output / 'preview-import.stdout.log').open('w') as stdout, (output / 'preview-import.stderr.log').open('w') as stderr:
        subprocess.run([str(godot), '--headless', '--editor', '--import', '--path', str(project)],
                       stdout=stdout, stderr=stderr, env=environment, creationflags=flags, check=True, timeout=240)
    import_errors = (output / 'preview-import.stderr.log').read_text()
    assert not any(token in import_errors for token in ['ERROR:', 'SCRIPT ERROR:']), import_errors[-3000:]
    return project, job_path, environment


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--godot', type=Path, default=Path(os.environ.get('GODOT', 'C:/rabbitlands/rabbitlands-client/godot-client/Godot_v4.7.2-stable_win64.exe')))
    parser.add_argument('--actor', default='crystalback_tortoise')
    parser.add_argument('--fps', type=int, choices=[30, 240], default=30)
    parser.add_argument('--prepare-only', action='store_true')
    parser.add_argument('--smoke', action='store_true', help='Exercise all clips/controls, capture both panes, then exit')
    parser.add_argument('--headless', action='store_true')
    args = parser.parse_args()
    project, job, environment = prepare(args.godot, args.fps, args.actor)
    output = project.parent
    print('CREATURE_PREVIEW_PREPARED', project, flush=True)
    if args.prepare_only: return
    command = [str(args.godot), '--path', str(project), '--script', 'res://prototypes/creature_animation_comparison.gd']
    if args.headless: command.append('--headless')
    command.extend(['--', str(job)])
    if args.smoke: command.append('--smoke')
    with (output / 'preview.stdout.log').open('w') as stdout, (output / 'preview.stderr.log').open('w') as stderr:
        result = subprocess.run(command, env=environment, stdout=stdout, stderr=stderr,
                                creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0,
                                timeout=180 if args.smoke else None)
    if result.returncode: raise SystemExit(f"Preview failed; inspect {output / 'preview.stderr.log'}")
    if args.smoke:
        assert 'CREATURE_COMPARISON_SMOKE_PASS' in (output / 'preview.stdout.log').read_text()
        assert 'ERROR:' not in (output / 'preview.stderr.log').read_text()


if __name__ == '__main__': main()
