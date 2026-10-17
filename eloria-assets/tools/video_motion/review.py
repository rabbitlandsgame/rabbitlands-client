"""Independent CPU silhouette and landmark review of exported GLB samples."""
import json
from pathlib import Path
import cv2
import numpy as np
from PIL import Image, ImageDraw
from .asset import Asset,digest
from .rig import Rig


def rasterize(asset, world, camera):
    points = asset.skin(world) @ np.asarray(camera['pixel_matrix_gltf']).T + np.asarray(camera['pixel_offset'])
    mask = np.zeros((camera['height'], camera['width']), dtype='uint8')
    offset = 0
    for part in asset.parts:
        for face in part['indices']:
            cv2.fillConvexPoly(mask, np.rint(points[face + offset]).astype('int32'), 255)
        offset += len(part['position'])
    return mask


def compare(model, profile, motion, tracking, output):
    asset = Asset(model)
    rig = Rig(asset, json.loads(Path(profile).read_text()))
    package = json.loads(Path(motion).read_text())
    camera = package['source_camera']
    source_frames = list(range(package['source_video']['selected_cycle']['start_frame'],
                               package['source_video']['selected_cycle']['end_frame'] + 1))
    # Compare at the video's native selected cadence, even if contact solving
    # and baking used denser samples.
    times = np.linspace(0,package['duration_seconds'],len(source_frames))
    ts, qs = asset.sample(package['clip'], times)
    frames, ious = [], []
    colors = {'fore_left': (255, 70, 80), 'fore_right': (255, 210, 60),
              'hind_left': (30, 200, 255), 'hind_right': (170, 120, 255)}
    for i, (t, q) in enumerate(zip(ts, qs)):
        world = asset.world(t, q)
        mask = rasterize(asset, world, camera)
        frame_number = source_frames[min(i, len(source_frames) - 1)]
        reference = cv2.imread(str(Path(tracking) / 'frames' / f'{frame_number:04d}.png'))
        target = cv2.imread(str(Path(tracking) / 'masks' / f'{frame_number:04d}.png'), 0) > 0
        iou = np.count_nonzero(target & (mask > 0)) / max(1, np.count_nonzero(target | (mask > 0)))
        ious.append(iou)
        left = cv2.cvtColor(reference, cv2.COLOR_BGR2RGB)
        overlay = left.copy()
        contour, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        cv2.drawContours(overlay, contour, -1, (80, 230, 255), 2)
        for limb in colors:
            nodes = [rig.roles[limb + '_' + role] for role in ('anchor', 'upper', 'lower', 'foot')]
            p = np.asarray([world[node, :3, 3] for node in nodes]) @ np.asarray(camera['pixel_matrix_gltf']).T + np.asarray(camera['pixel_offset'])
            cv2.polylines(overlay, [np.rint(p).astype('int32')], False, colors[limb], 3)
        combined = np.concatenate([left, overlay], axis=1)
        picture = Image.fromarray(combined)
        picture.thumbnail((960, 270))
        canvas = Image.new('RGB', (960, 298), '#20242b')
        canvas.paste(picture)
        ImageDraw.Draw(canvas).text((12, 276), f'Meshy frame {frame_number} | Exported rig / silhouette | IoU {iou:.3f}', fill='white')
        frames.append(canvas)
    output = Path(output)
    output.mkdir(parents=True, exist_ok=True)
    frames[0].save(output / 'video-fit-comparison.gif', save_all=True, append_images=frames[1:],
                   duration=round(1000 / 24), loop=0)
    selected = [frames[i] for i in np.linspace(0, len(frames) - 1, 6).astype(int)]
    sheet = Image.new('RGB', (960, 298 * len(selected)))
    for i, frame in enumerate(selected):
        sheet.paste(frame, (0, i * 298))
    sheet.save(output / 'video-fit-comparison.jpg')
    report = {'export_sha256':digest(model),'motion_package_sha256':digest(motion),
              'mean_exported_silhouette_iou': float(np.mean(ious)), 'minimum_exported_silhouette_iou': float(min(ious)),
              'per_frame_iou': ious, 'measurement': 'Original camera, exported GLB; ground correction and loop closure included.'}
    (output / 'silhouette-validation.json').write_text(json.dumps(report, indent=2))
    return report
