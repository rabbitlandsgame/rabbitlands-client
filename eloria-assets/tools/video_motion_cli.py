"""CLI for the staged Eloria video-motion pilot; run --help for subcommands."""
import argparse
import json
from pathlib import Path
import cv2
import numpy as np
from PIL import Image, ImageDraw
from video_motion.asset import Asset, digest
from video_motion.rig import Rig, auto_profile
from video_motion.video import extract, choose_cycle, optical_observations, contour_paw_observations
from video_motion.solve import fit, periodic_motion, motion_package, transfer, validate_export, dense_bake
from video_motion.contact import fit_contacts, contact_bake, contact_package, transfer_contact_motion, evaluate_contacts
from scipy.interpolate import CubicSpline


def load(path):
    return json.loads(Path(path).read_text(encoding='utf-8'))


def save(path, record):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(record, indent=2), encoding='utf-8')


def make_rig(args):
    asset = Asset(args.model)
    return Rig(asset, load(args.profile) if args.profile else auto_profile(asset))


def contact_sheet(folder, frames, output, observations=None):
    width, height = 320, 204
    columns = 4
    canvas = Image.new('RGB', (columns * width, ((len(frames) + columns - 1) // columns) * height), '#20242b')
    draw = ImageDraw.Draw(canvas)
    palette = {'fore_left': '#ff4e55', 'fore_right': '#ffd24a', 'hind_left': '#22d6ee', 'hind_right': '#8a80ff'}
    lookups = {o['frame']: o for o in observations['observations']} if observations else {}
    for k, frame in enumerate(frames):
        picture = Image.open(Path(folder) / 'frames' / f'{frame:04d}.png').convert('RGB')
        if frame in lookups:
            pd = ImageDraw.Draw(picture)
            for role, value in lookups[frame]['landmarks'].items():
                if role not in palette:
                    continue
                x, y = value['xy']
                pd.ellipse((x - 6, y - 6, x + 6, y + 6), fill=palette[role])
                pd.text((x + 7, y - 12), role, fill=palette[role])
        picture.thumbnail((width, 180))
        x, y = k % columns * width, k // columns * height
        canvas.paste(picture, (x, y))
        draw.text((x + 8, y + 183), f'Frame {frame}  ({frame / 24:.3f}s)', fill='white')
    canvas.save(output)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest='command', required=True)
    def rig_arguments(p):
        p.add_argument('--model', required=True)
        p.add_argument('--profile')
    inspect = sub.add_parser('inspect')
    rig_arguments(inspect)
    inspect.add_argument('--out', required=True)
    decode = sub.add_parser('extract')
    decode.add_argument('--video', required=True)
    decode.add_argument('--out', required=True)
    track = sub.add_parser('track')
    rig_arguments(track)
    track.add_argument('--camera', required=True)
    track.add_argument('--tracking', required=True)
    track.add_argument('--contour-paws', action='store_true')
    solve = sub.add_parser('fit')
    rig_arguments(solve)
    solve.add_argument('--camera', required=True)
    solve.add_argument('--tracking', required=True)
    solve.add_argument('--out', required=True)
    solve.add_argument('--max-evaluations', type=int, default=45)
    solve.add_argument('--no-silhouette', action='store_true')
    solve.add_argument('--clip', default='Walk')
    solve.add_argument('--initial-clip', default='Walk')
    solve.add_argument('--one-shot', action='store_true')
    retarget = sub.add_parser('retarget')
    rig_arguments(retarget)
    retarget.add_argument('--motion', required=True)
    retarget.add_argument('--out', required=True)
    polish = sub.add_parser('polish')
    rig_arguments(polish)
    polish.add_argument('--motion', required=True)
    polish.add_argument('--gait', required=True)
    polish.add_argument('--out', required=True)
    polish.add_argument('--solve-fps', type=int, default=96)
    polish.add_argument('--max-evaluations', type=int, default=65)
    validate = sub.add_parser('validate')
    validate.add_argument('--source', required=True)
    validate.add_argument('--export', required=True)
    validate.add_argument('--out', required=True)
    validate.add_argument('--clip', default='Walk')
    sheet = sub.add_parser('sheet')
    sheet.add_argument('--tracking', required=True)
    sheet.add_argument('--out', required=True)
    sheet.add_argument('--start', type=int, default=0)
    sheet.add_argument('--end', type=int, default=120)
    sheet.add_argument('--step', type=int, default=8)
    args = parser.parse_args()
    if args.command == 'inspect':
        rig = make_rig(args)
        rig.save_profile(args.out)
        print(json.dumps({'roles': rig.profile['roles'], 'height': rig.asset.height,
                          'rest_sole_markers': {r: v.tolist() for r, v in rig.rest_markers.items()}}))
    elif args.command == 'extract':
        record, masks = extract(args.video, args.out)
        save(Path(args.out) / 'cycle.json', choose_cycle(masks, record['sample_fps']))
    elif args.command == 'track':
        rig = make_rig(args)
        data = optical_observations(rig, load(args.camera), args.tracking)
        cycle = load(Path(args.tracking) / 'cycle.json')
        if args.contour_paws:
            data = contour_paw_observations(rig, load(args.camera), args.tracking,
                                            cycle['start_frame'], cycle['end_frame'])
        contact_sheet(args.tracking, list(range(cycle['start_frame'], cycle['end_frame'] + 1, 2)),
                      Path(args.tracking) / 'tracking-candidates.jpg', data)
    elif args.command == 'fit':
        rig = make_rig(args)
        folder, output = Path(args.tracking), Path(args.out)
        cycle, video = load(folder / 'cycle.json'), load(folder / 'video.json')
        frames = list(range(cycle['start_frame'], cycle['end_frame'] + 1))
        times, parameters, metrics = fit(rig, load(args.camera), load(folder / 'observations.json'), frames,
            folder / 'masks', initial_clip=args.initial_clip,
            max_evaluations=args.max_evaluations, use_silhouette=not args.no_silhouette)
        save(output / 'raw-solve.json', {'times_seconds': times.tolist(), 'parameters': parameters.tolist(), 'metrics': metrics})
        if not args.one_shot:
            times, parameters = periodic_motion(times, parameters)
        package, t, q = motion_package(rig, load(args.camera), times, parameters,
            {'provider': 'Meshy', 'video_sha256': video['source_sha256'],
             'selected_cycle': cycle, 'input_frame_times_seconds': [video['sample_times_seconds'][f] for f in frames]},
             metrics, clip=args.clip, loop=not args.one_shot)
        save(output / 'quadruped_walk.motion.json', package)
        dense_times, t, q = dense_bake(rig, times, np.asarray(package['parameters_radians_and_root_height']), loop=package['loop'])
        rig.asset.export(output / (rig.asset.path.stem + '__video_walk.glb'), args.clip, dense_times, t, q,
            {'loop': not args.one_shot, 'source': 'video_fit', 'motion_package': 'quadruped_walk.motion.json',
             'source_video_sha256': video['source_sha256'], 'root_motion': 'in_place'})
    elif args.command == 'polish':
        rig, prior, gait = make_rig(args), load(args.motion), load(args.gait)
        if prior['clip'] != 'Walk' or not prior.get('loop'):
            raise ValueError('The current contact-polish path supports looped Walk clips')
        if prior['source_model_sha256'] != digest(rig.asset.path):
            raise ValueError('Polish the same source actor; use retarget for a different actor')
        times = np.linspace(0,prior['duration_seconds'],round(prior['duration_seconds']*args.solve_fps)+1)
        body = CubicSpline(prior['times_seconds'],prior['parameters_radians_and_root_height'],bc_type='periodic')(times)
        mapping={r:i for i,r in enumerate(prior['controls'])}
        body=np.column_stack([*[body[:,mapping[c['role']]] for c in rig.controls],body[:,-1]])
        for i,c in enumerate(rig.controls):
            if any(c['role'].startswith(l+'_') for l in ('fore_left','fore_right','hind_left','hind_right')):
                body[:,i] = 0
            elif c['role'] in ('driver','hips','chest'):
                body[:,i] *= gait.get('body_angle_scale',.3)
        parameters,diagnostics = fit_contacts(rig,times,body,gait,args.max_evaluations)
        package = contact_package(prior,rig,times,parameters,gait,diagnostics)
        output = Path(args.out)
        save(output/'source-contact-fit.json',{'times_seconds':times.tolist(),
            'parameters':parameters.tolist(),'diagnostics':diagnostics})
        save(output/'quadruped_walk.motion.json',package)
        dense_times,t,q = contact_bake(rig,times,parameters)
        file = output/(rig.asset.path.stem+'__video_walk.glb')
        rig.asset.export(file,package['clip'],dense_times,t,q,{'loop':True,'root_motion':'in_place',
            'source':'reference_guided_surface_contact_polish','virtual_forward_speed':gait['speed_native_units_per_second'],
            'paw_follow_helpers':rig.follower_metadata()})
        save(output/'contact-validation.json',evaluate_contacts(Asset(file),rig,gait))
    elif args.command == 'retarget':
        rig, package = make_rig(args), load(args.motion)
        output = Path(args.out)
        if package.get('schema_version',1) >= 2 and 'gait_contact_model' in package:
            parameters,diagnostics,gait = transfer_contact_motion(package,rig)
            dense_times,t,q = contact_bake(rig,np.asarray(package['times_seconds']),parameters)
            save(output/'target-gait.json',gait)
        else:
            t, q, parameters, diagnostics = transfer(package, rig)
            dense_times, t, q = dense_bake(rig, np.asarray(package['times_seconds']), parameters, loop=package['loop'])
        metadata={'loop': package['loop'], 'source': 'category_motion_transfer',
            'motion_package_sha256':digest(args.motion),'root_motion':'in_place'}
        if 'gait_contact_model' in package:
            metadata['virtual_forward_speed']=gait['speed_native_units_per_second']
            metadata['paw_follow_helpers']=rig.follower_metadata()
            metadata['scapula_offset_controls']=rig.profile.get('scapula_offset_controls',[])
        rig.asset.export(output / (rig.asset.path.stem + '__transferred_walk.glb'), package['clip'],
            dense_times, t, q, metadata)
        save(output / (rig.asset.path.stem + '__transfer.json'),
             {'source_motion_sha256': digest(args.motion), 'target_source_sha256': digest(rig.asset.path),
              'category': package['category'], 'role_map': rig.profile['roles'], 'diagnostics': diagnostics,
              'parameters_radians_and_root_height': parameters.tolist()})
        if 'gait_contact_model' in package:
            save(output/'contact-validation.json',evaluate_contacts(Asset(output/(rig.asset.path.stem+'__transferred_walk.glb')),rig,gait))
    elif args.command == 'validate':
        report = validate_export(Asset(args.source), args.export, clip=args.clip)
        save(args.out, report)
        print(json.dumps(report, indent=2))
        if not report['numerical_pass']:
            raise SystemExit(1)
    elif args.command == 'sheet':
        contact_sheet(args.tracking, list(range(args.start, args.end + 1, args.step)), args.out)


if __name__ == '__main__':
    main()
