"""Decode timing, segment the subject and obtain editable motion observations."""
from __future__ import annotations
import json
from pathlib import Path
import cv2
import numpy as np
from scipy.signal import find_peaks
from scipy.optimize import linear_sum_assignment
from .asset import digest


def foreground(frame):
    gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
    border = np.concatenate([gray[:, :12], gray[:, -12:]], 1)
    background = np.median(border, axis=1)[:, None]
    mask = (gray.astype(float) < background - 30).astype('uint8') * 255
    mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, np.ones((3, 3), 'uint8'))
    count, labels, stats, _ = cv2.connectedComponentsWithStats(mask)
    if count < 2:
        raise ValueError('No foreground subject detected against the neutral background')
    label = 1 + np.argmax(stats[1:, cv2.CC_STAT_AREA])
    return (labels == label).astype('uint8') * 255


def extract(video_path, output, fps=24, width=960, height=540):
    output = Path(output)
    (output / 'frames').mkdir(parents=True, exist_ok=True)
    (output / 'masks').mkdir(exist_ok=True)
    capture = cv2.VideoCapture(str(video_path))
    if not capture.isOpened():
        raise ValueError('Cannot decode the supplied video')
    native_fps = capture.get(cv2.CAP_PROP_FPS)
    native_count = int(capture.get(cv2.CAP_PROP_FRAME_COUNT))
    native_size = [int(capture.get(cv2.CAP_PROP_FRAME_WIDTH)), int(capture.get(cv2.CAP_PROP_FRAME_HEIGHT))]
    if native_fps <= 0:
        raise ValueError('Video timing is unavailable')
    if abs(native_size[0] / native_size[1] - width / height) > .01:
        raise ValueError('Video aspect ratio differs from the reference camera')
    decoded, changes, previous = [], [], None
    while True:
        okay, frame = capture.read()
        if not okay:
            break
        frame = cv2.resize(frame, (width, height), interpolation=cv2.INTER_AREA)
        tiny = cv2.resize(cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY), (120, 68))
        changes.append(float(np.mean(np.abs(tiny.astype(float) - previous))) if previous is not None else None)
        previous = tiny.astype(float)
        decoded.append(frame)
    capture.release()
    if not decoded:
        raise ValueError('Empty video')
    duration = len(decoded) / native_fps
    times = np.arange(0, duration - 1e-7, 1 / fps)
    indices = np.clip(np.rint(times * native_fps).astype(int), 0, len(decoded) - 1)
    masks = []
    for number, original in enumerate(indices):
        frame = decoded[original]
        mask = foreground(frame)
        cv2.imwrite(str(output / 'frames' / f'{number:04d}.png'), frame)
        cv2.imwrite(str(output / 'masks' / f'{number:04d}.png'), mask)
        masks.append(mask)
    duplicate_count = sum(v is not None and v < .05 for v in changes)
    record = {'schema_version': 1, 'source_video': str(Path(video_path).resolve()),
        'source_sha256': digest(video_path), 'container_fps': native_fps,
        'container_declared_frames': native_count, 'decoded_frames': len(decoded),
        'native_size': native_size, 'duration_seconds': duration, 'sample_fps': fps,
        'sample_size': [width, height], 'sample_times_seconds': times.tolist(),
        'source_frame_indices': indices.tolist(), 'near_duplicate_native_frames': duplicate_count,
        'estimated_distinct_frames_per_second': (len(decoded) - duplicate_count) / duration,
        'cadence_note': 'Decode by timestamps; distinct-frame rate is diagnostic, not a new playback speed.'}
    (output / 'video.json').write_text(json.dumps(record, indent=2), encoding='utf-8')
    return record, masks


def choose_cycle(masks, fps):
    small = np.asarray([cv2.resize(m, (120, 68), interpolation=cv2.INTER_AREA) / 255 for m in masks])
    # Compare the lower body where foot progression dominates.
    features = small[:, 28:, :].reshape(len(small), -1)
    lags = np.arange(max(6, round(fps * .4)), min(round(fps * 2), len(small) // 2) + 1)
    errors = np.asarray([np.mean(np.abs(features[lag:] - features[:-lag])) for lag in lags])
    valleys = find_peaks(-errors, prominence=.001)[0]
    best = min(valleys, key=lambda i: errors[i]) if len(valleys) else int(np.argmin(errors))
    # Prefer one stride over two strides when both have comparable recurrence.
    comparable = [i for i in valleys if errors[i] <= errors[best] * 1.3]
    if comparable:
        best = min(comparable, key=lambda i: lags[i])
    period = int(lags[best])
    starts = np.arange(min(round(fps * .6), max(0, len(small) - period - 1)), len(small) - period)
    endpoint_errors = np.asarray([np.mean(np.abs(small[s] - small[s + period])) for s in starts])
    start = int(starts[np.argmin(endpoint_errors)])
    return {'start_frame': start, 'end_frame': start + period,
        'period_frames': period, 'duration_seconds': period / fps,
        'mean_recurrence_error': float(errors[best]), 'endpoint_mask_error': float(endpoint_errors.min()),
        'tested_lags': lags.tolist(), 'lag_errors': errors.tolist(),
        'selection': 'automatic candidate; confirm limb identity and gait before accepting'}


def optical_observations(rig, camera, output):
    output = Path(output)
    meta = json.loads((output / 'video.json').read_text())
    files = sorted((output / 'frames').glob('*.png'))
    matrix = np.asarray(camera['pixel_matrix_gltf'])
    offset = np.asarray(camera['pixel_offset'])
    rest = rig.landmarks(rig.asset.world_rest)
    roles = list(rest)
    points = np.asarray([matrix @ rest[r] + offset for r in roles], dtype=np.float32)
    # A sole marker is at the silhouette edge; track slightly inside the paw.
    for i, role in enumerate(roles):
        if role in ('fore_left', 'fore_right', 'hind_left', 'hind_right'):
            points[i, 1] -= 5
    current = points.reshape(-1, 1, 2)
    prior = cv2.cvtColor(cv2.imread(str(files[0])), cv2.COLOR_BGR2GRAY)
    observations = []
    for frame_number, path in enumerate(files):
        gray = cv2.cvtColor(cv2.imread(str(path)), cv2.COLOR_BGR2GRAY)
        if frame_number:
            following, status, error = cv2.calcOpticalFlowPyrLK(prior, gray, current, None,
                winSize=(31, 31), maxLevel=4,
                criteria=(cv2.TERM_CRITERIA_EPS | cv2.TERM_CRITERIA_COUNT, 30, .01))
            reverse, reverse_status, _ = cv2.calcOpticalFlowPyrLK(gray, prior, following, None,
                                                               winSize=(31, 31), maxLevel=4)
            consistency = np.linalg.norm(reverse - current, axis=2).ravel()
            confidence = np.exp(-consistency / 2) * status.ravel() * reverse_status.ravel()
            confidence *= np.exp(-error.ravel() / 25)
            good = confidence > .15
            current[good] = following[good]
        else:
            confidence = np.ones(len(roles)) * .5
        landmarks = {}
        for i, role in enumerate(roles):
            point = current[i, 0].astype(float).copy()
            if role in ('fore_left', 'fore_right', 'hind_left', 'hind_right'):
                point[1] += 5
            landmarks[role] = {'xy': point.tolist(), 'confidence': float(confidence[i]),
                               'method': 'optical_flow_candidate', 'reviewed': False}
        observations.append({'frame': frame_number, 'time_seconds': meta['sample_times_seconds'][frame_number],
                             'landmarks': landmarks})
        prior = gray
    data = {'schema_version': 1, 'video_sha256': meta['source_sha256'], 'roles': roles,
            'observations': observations, 'anchors': [],
            'note': 'Optical flow does not resolve overlapping limbs. Supply reviewed anchors; unobserved far limbs must retain low confidence.'}
    (output / 'observations.json').write_text(json.dumps(data, indent=2), encoding='utf-8')
    return data


def apply_anchors(data):
    """Interpolate reviewed corrections; absent/occluded observations stay uncertain."""
    result = json.loads(json.dumps(data))
    for role in data['roles']:
        anchors = sorted([a for a in data.get('anchors', []) if a['role'] == role], key=lambda a: a['frame'])
        if not anchors:
            continue
        frames = [a['frame'] for a in anchors]
        xy = np.asarray([a['xy'] for a in anchors])
        for observation in result['observations']:
            f = observation['frame']
            if f < frames[0] or f > frames[-1]:
                continue
            point = [float(np.interp(f, frames, xy[:, axis])) for axis in range(2)]
            confidence = float(np.interp(f, frames, [a.get('confidence', .9) for a in anchors]))
            observation['landmarks'][role] = {'xy': point, 'confidence': confidence,
                                            'method': 'reviewed_anchor_interpolation', 'reviewed': True}
    return result


def contour_paw_observations(rig, camera, output, start, end):
    """Track separated lower-leg components; label merged feet as occluded.

    Identity is an inference from temporal continuity, not depth measurement.
    These observations remain editable and require visual review.
    """
    output = Path(output)
    data = json.loads((output / 'observations.json').read_text())
    matrix, offset = np.asarray(camera['pixel_matrix_gltf']), np.asarray(camera['pixel_offset'])
    last = {limb: matrix @ point + offset for limb, point in rig.rest_markers.items()}
    velocity = {limb: np.zeros(2) for limb in last}
    for observation in data['observations']:
        if observation['frame'] < start or observation['frame'] > end:
            continue
        mask = cv2.imread(str(output / 'masks' / f'{observation["frame"]:04d}.png'), 0)
        ys, xs = np.where(mask > 0)
        ground, top = np.quantile(ys, .995), ys.min()
        cutoff = round(ground - (ground - top) * .22)
        lower = mask.copy()
        lower[:cutoff] = 0
        count, labels, stats, centers = cv2.connectedComponentsWithStats(lower)
        candidates = []
        for label in range(1, count):
            px_y, px_x = np.where(labels == label)
            if len(px_y) < 30 or px_y.max() < ground - 42:
                continue
            bottom = px_y >= px_y.max() - 3
            point = np.array([np.median(px_x[bottom]), np.median(px_y[bottom])], float)
            candidates.append(point)
        division = (matrix @ rig.asset.world_rest[rig.roles['chest'], :3, 3] + offset)[0] + 115
        for pair, group in [(('fore_left', 'fore_right'), [p for p in candidates if p[0] < division]),
                            (('hind_left', 'hind_right'), [p for p in candidates if p[0] >= division])]:
            for limb in pair:
                observation['landmarks'][limb]['confidence'] = .02
                observation['landmarks'][limb]['identity_status'] = 'occluded_or_merged'
            if not group:
                continue
            expected = np.asarray([last[limb] + velocity[limb] for limb in pair])
            candidates_array = np.asarray(group)
            costs = np.linalg.norm(expected[:, None] - candidates_array[None], axis=2)
            rows, cols = linear_sum_assignment(costs)
            for row, col in zip(rows, cols):
                limb, point = pair[row], group[col]
                confidence = .85 if len(group) == 2 else .35
                observation['landmarks'][limb] = {'xy': point.tolist(), 'confidence': confidence,
                    'method': 'lower_leg_silhouette_component', 'reviewed': False,
                    'identity_status': 'inferred_temporal_assignment'}
                velocity[limb] = .5 * velocity[limb] + .5 * (point - last[limb])
                last[limb] = point
        observation['paw_candidates'] = [p.tolist() for p in candidates]
    (output / 'observations.json').write_text(json.dumps(data, indent=2), encoding='utf-8')
    return data
