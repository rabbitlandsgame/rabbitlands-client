"""Replay a qualified native fit offline, preserving the client's other clips."""
import argparse
import json
import sys
import tempfile
from pathlib import Path
import numpy as np

LIBRARY = Path(__file__).resolve().parent
ASSETS = LIBRARY.parents[2]
REPOSITORY = ASSETS.parent
sys.path.insert(0, str(ASSETS / 'tools'))
from video_motion.asset import Asset, digest, write_glb
from video_motion.rig import Rig
from video_motion.actions import ActionRig, bake_action
from video_motion.contact import contact_bake
from video_motion.packing import compact
from video_motion.promotion import preserve_runtime_clips


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--actor', required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--preserve-runtime-from', type=Path)
    args = parser.parse_args()
    folder = LIBRARY / 'actors' / args.actor
    if not folder.is_dir() or folder.parent != LIBRARY / 'actors':
        parser.error('Unknown packaged actor')
    runtime = args.preserve_runtime_from or (REPOSITORY /
        f'godot-client/assets/actors/native/creatures/{args.actor}.glb')
    output = args.output.resolve()
    if output == runtime.resolve() or output.is_relative_to(LIBRARY):
        parser.error('Output must preserve packaged inputs and current runtime assets')
    output.parent.mkdir(parents=True, exist_ok=True)
    current = None
    with tempfile.TemporaryDirectory(prefix='canine-replay-', dir=output.parent) as tmp:
        for kind, clip in [('walk', 'Walk'), ('attack', 'Sword_Attack'), ('death', 'Death_A')]:
            profile = json.loads((folder / f'{kind}.rig.json').read_text(encoding='utf-8'))
            source_path = (folder / profile['source_glb']).resolve()
            if digest(source_path) != profile['source_sha256']:
                raise ValueError('Prepared input does not match its profile')
            source = Asset(source_path)
            data = json.loads((folder / f'{kind}.motion.json').read_text(encoding='utf-8'))
            rig = (Rig if kind == 'walk' else ActionRig)(source, profile)
            if data.get('complete_surface_projection') or data.get('intermediate_surface_refinement'):
                times = np.asarray(data['times_seconds'])
                poses = [rig.pose(np.asarray(row))[:2] for row in data['parameters_radians_and_root_height']]
                t, q = np.array([p[0] for p in poses]), np.array([p[1] for p in poses])
            else:
                times, t, q = (contact_bake if kind == 'walk' else bake_action)(
                    rig, data['times_seconds'], data['parameters_radians_and_root_height'],
                    int(data.get('export_key_fps', 768)))
            metadata = {'loop': kind == 'walk', 'root_motion': 'in_place',
                'source_motion_sha256': data['source_motion_sha256'],
                'paw_follow_helpers': rig.follower_metadata(),
                'events_seconds': (data.get('action_contract') or {}).get('event_times_seconds', {})}
            if kind == 'walk':
                metadata['virtual_forward_speed'] = data['gait_contact_model']['speed_native_units_per_second']
            target = Path(tmp) / f'{kind}.glb'
            (current or source).export(target, clip, times, t, q, metadata)
            current = Asset(target)
        doc, blob, _ = preserve_runtime_clips(Asset(runtime), current)
        doc, blob, _ = compact(doc, blob)
        write_glb(output, doc, blob)
    print('REPLAYED', args.actor, digest(output))


if __name__ == '__main__':
    main()
