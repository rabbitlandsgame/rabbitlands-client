"""Constrained planar pose fitting and proportion-aware category transfer.

Single-camera depth is deliberately held to the fitted rest geometry. This is
an observable-motion pilot, not a reconstruction of hidden 3D movement.
"""
from __future__ import annotations
import json
import time
from pathlib import Path
import cv2
import numpy as np
from scipy.interpolate import CubicSpline
from scipy.ndimage import map_coordinates
from scipy.ndimage import gaussian_filter1d
from scipy.optimize import least_squares
from scipy.spatial import cKDTree
from scipy.spatial.transform import Rotation
from .asset import accessor, digest, rotation_matrix
from .rig import LEG_NAMES
from .video import apply_anchors


def initial_parameters(rig, clip, times):
    """Use an existing gait only as initialization, never as video evidence."""
    a = rig.asset
    if clip not in a.animations:
        return np.zeros((len(times), rig.dof))
    t, q = a.sample(clip, np.asarray(times) % a.duration(clip))
    result = []
    for translations, rotations in zip(t, q):
        world = a.world(translations, rotations)
        parameters = np.zeros(rig.dof)
        for i, control in enumerate(rig.controls):
            node = rig.roles[control['role']]
            parent = a.parent[node]
            parent_r = np.eye(3) if parent < 0 else Rotation.from_matrix(world[parent, :3, :3]).as_matrix()
            posed_r = Rotation.from_matrix(world[node, :3, :3]).as_matrix()
            delta = posed_r @ (parent_r @ rotation_matrix(a.q[node])).T
            parameters[i] = np.dot(Rotation.from_matrix(delta).as_rotvec(), rig.axis)
        parameters[-1] = np.dot(world[rig.driver, :3, 3] - a.world_rest[rig.driver, :3, 3], rig.up)
        result.append(np.clip(parameters, rig.lower + 1e-6, rig.upper - 1e-6))
    return np.asarray(result)


def fit(rig, camera, observations, frames, mask_dir=None, initial_clip='Walk',
        max_evaluations=45, use_silhouette=True):
    observations = apply_anchors(observations)
    all_observations = {o['frame']: o for o in observations['observations']}
    chosen = [all_observations[f] for f in frames]
    ts = np.asarray([o['time_seconds'] for o in chosen])
    # Initialize one library cycle over the selected video period.
    duration = rig.asset.duration(initial_clip) if initial_clip in rig.asset.animations else ts[-1] - ts[0]
    phase = (ts - ts[0]) / max(ts[-1] - ts[0], 1e-6)
    seeds = initial_parameters(rig, initial_clip, phase * duration)
    matrix, offset = np.asarray(camera['pixel_matrix_gltf']), np.asarray(camera['pixel_offset'])
    height, width = camera['height'], camera['width']
    sample_ids = np.linspace(0, len(rig.asset.rest_vertices) - 1,
                             min(1500, len(rig.asset.rest_vertices))).astype(int)
    solutions, metrics = [], []
    previous = None
    started = time.monotonic()
    for ordinal, (observation, seed) in enumerate(zip(chosen, seeds)):
        landmarks = observation['landmarks']
        contour = distance = None
        if use_silhouette and mask_dir is not None:
            mask = cv2.imread(str(Path(mask_dir) / f'{observation["frame"]:04d}.png'), cv2.IMREAD_GRAYSCALE)
            if mask is None:
                raise ValueError('Missing segmentation mask')
            outside = cv2.distanceTransform(255 - mask, cv2.DIST_L2, 5)
            distance = outside
            contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_NONE)
            full = max(contours, key=cv2.contourArea).reshape(-1, 2)
            contour = full[np.linspace(0, len(full) - 1, min(180, len(full))).astype(int)].astype(float)
        def residual(parameters):
            _, _, world = rig.pose(parameters)
            result = []
            predicted = rig.landmarks(world)
            for role, value in landmarks.items():
                if role not in predicted:
                    continue
                confidence = value.get('confidence', 0)
                # Unreviewed flow can drift through occlusion; do not certify it.
                confidence *= 1 if value.get('reviewed') else .2
                if confidence > .01:
                    result.extend((matrix @ predicted[role] + offset - value['xy']) * np.sqrt(confidence) / 6)
            if distance is not None:
                points = rig.asset.skin(world)[sample_ids] @ matrix.T + offset
                outside_values = map_coordinates(distance, [points[:, 1], points[:, 0]], order=1, mode='constant', cval=100)
                result.extend(outside_values / 18 / np.sqrt(len(points) / 100))
                nearest = cKDTree(points).query(contour)[0]
                result.extend(nearest / 14 / np.sqrt(len(contour) / 100))
            result.extend((parameters[:-1] - seed[:-1]) * .07)
            result.append((parameters[-1] - seed[-1]) / rig.asset.height * .5)
            if previous is not None:
                result.extend((parameters[:-1] - previous[:-1]) * .25)
                result.append((parameters[-1] - previous[-1]) / rig.asset.height * .8)
            return np.asarray(result)
        start = seed if previous is None else .8 * previous + .2 * seed
        lower, upper = rig.lower.copy(), rig.upper.copy()
        if previous is not None:
            dt = ts[ordinal] - ts[ordinal - 1]
            maximum_step = np.r_[np.full(rig.dof - 1, np.deg2rad(360) * dt), rig.asset.height * .5 * dt]
            lower = np.maximum(lower, previous - maximum_step)
            upper = np.minimum(upper, previous + maximum_step)
        solution = least_squares(residual, np.clip(start, lower + 1e-7, upper - 1e-7),
            bounds=(lower, upper), max_nfev=max_evaluations, loss='soft_l1', f_scale=2,
            diff_step=1e-4, ftol=2e-4, xtol=2e-4, gtol=2e-4)
        previous = solution.x.copy()
        solutions.append(previous)
        _, _, world = rig.pose(previous)
        errors = {r: float(np.linalg.norm(matrix @ point + offset - landmarks[r]['xy']))
                  for r, point in rig.landmarks(world).items() if r in landmarks and landmarks[r].get('confidence', 0) > .1}
        metrics.append({'frame': observation['frame'], 'cost': float(solution.cost),
                        'evaluations': solution.nfev, 'converged': bool(solution.success),
                        'landmark_error_pixels': errors})
        print(json.dumps({'fit_frame': ordinal + 1, 'of': len(chosen), 'cost': round(solution.cost, 3),
                          'elapsed_seconds': round(time.monotonic() - started, 1)}), flush=True)
    return ts - ts[0], np.asarray(solutions), metrics


def periodic_motion(times, parameters, fps=24):
    parameters = parameters.copy()
    # Spread endpoint reconciliation across the cycle rather than one final snap.
    phase = (times - times[0]) / (times[-1] - times[0])
    mismatch = parameters[-1] - parameters[0]
    blend = np.clip((phase - .8) / .2, 0, 1)
    weight = blend * blend * (3 - 2 * blend)
    parameters -= weight[:, None] * mismatch
    parameters[-1] = parameters[0]
    # Remove per-frame IK/segmentation jitter before baking surface contact.
    parameters[:-1] = gaussian_filter1d(parameters[:-1], .8, axis=0, mode='wrap')
    parameters[-1] = parameters[0]
    output_times = np.linspace(0, times[-1], round(times[-1] * fps) + 1)
    values = CubicSpline(times, parameters, bc_type='periodic')(output_times)
    return output_times, values


def bake(rig, times, parameters, ground=True):
    translations, rotations, markers = [], [], []
    corrected = parameters.copy()
    for i, values in enumerate(corrected):
        t, q, world = rig.pose(values)
        if ground:
            minimum = float(rig.asset.skin(world)[:, 1].min())
            # Preserve the fitted limbs; vertically place the evaluated surface.
            corrected[i, -1] += .0005 - minimum
            t, q, world = rig.pose(corrected[i])
        translations.append(t)
        rotations.append(q)
        markers.append(rig.marker_positions(world))
    return np.asarray(translations), np.asarray(rotations), markers, corrected


def dense_bake(rig, times, parameters, fps=192, loop=True):
    dense_times = np.linspace(0, times[-1], round(times[-1] * fps) + 1)
    spline = CubicSpline(times, parameters, bc_type='periodic' if loop else 'not-a-knot')
    dense_parameters = spline(dense_times)
    t, q, _, _ = bake(rig, dense_times, dense_parameters)
    return dense_times, t, q


def motion_package(rig, camera, times, parameters, source, metrics, clip='Walk', loop=True):
    t, q, markers, parameters = bake(rig, times, parameters)
    trajectories = {limb: np.asarray([m[limb] for m in markers]) for limb in LEG_NAMES}
    contacts = {}
    for limb, positions in trajectories.items():
        heights = positions @ rig.up
        velocities = np.gradient(positions @ rig.forward, times)
        contacts[limb] = ((heights <= heights.min() + rig.asset.height * .018) &
                          (velocities <= .05 * rig.asset.height)).tolist()
    basis = np.column_stack([rig.axis, rig.up, rig.forward])
    normalized = {limb: (((positions - rig.rest_markers[limb]) @ basis) / rig.leg_lengths[limb]).tolist()
                  for limb, positions in trajectories.items()}
    package = {'schema_version': 1, 'category': rig.profile['category'],
        'subcategory': rig.profile.get('subcategory'), 'clip': clip, 'loop': loop,
        'root_motion': 'in_place', 'sample_fps': 24, 'times_seconds': times.tolist(),
        'duration_seconds': float(times[-1]), 'controls': [c['role'] for c in rig.controls],
        'parameters_radians_and_root_height': parameters.tolist(), 'source_height': rig.asset.height,
        'source_model_sha256': digest(rig.asset.path), 'source_video': source,
        'source_role_map': rig.profile['roles'], 'source_camera': camera,
        'normalized_sole_trajectories': normalized, 'contact_flags': contacts,
        'source_leg_lengths': rig.leg_lengths, 'fit_metrics': metrics,
        'depth_policy': 'Rest-depth retained; hidden lateral motion is unobserved.',
        'post_processing': {'joint_velocity_limit_degrees_per_second': 360,
                            'loop_reconciliation': 'last 20 percent of cycle' if loop else 'none',
                            'periodic_gaussian_sigma_frames': .8 if loop else 0,
                            'surface_clearance_native_units': .0005,
                            'export_bake_fps': 192},
        'status': 'pilot_candidate_pending_visual_and_runtime_acceptance'}
    return package, t, q


def transfer(package, target_rig, max_evaluations=55):
    if package['category'] != target_rig.profile['category']:
        raise ValueError('Motion category and target profile differ')
    if package.get('subcategory') != target_rig.profile.get('subcategory'):
        raise ValueError('Different gait families require explicit compatibility review')
    names = package['controls']
    mapping = {role: i for i, role in enumerate(names)}
    # Extra target joints start neutral and are adapted by contact IK. Core
    # limb identity is carried by the four normalized sole trajectories.
    if set(package['normalized_sole_trajectories']) != set(LEG_NAMES):
        raise ValueError('A quadruped package must contain four sole trajectories')
    source = np.asarray(package['parameters_radians_and_root_height'])
    times = np.asarray(package['times_seconds'])
    fitted, diagnostics = [], []
    previous = None
    trajectories = {limb: np.asarray(v) for limb, v in package['normalized_sole_trajectories'].items()}
    for frame in range(len(times)):
        seed = np.r_[[source[frame, mapping[c['role']]] if c['role'] in mapping else 0 for c in target_rig.controls],
                     source[frame, -1] * target_rig.asset.height / package['source_height']]
        basis = np.column_stack([target_rig.axis, target_rig.up, target_rig.forward])
        targets = {limb: target_rig.rest_markers[limb] + basis @ trajectories[limb][frame] * target_rig.leg_lengths[limb]
                   for limb in LEG_NAMES}
        def residual(values):
            _, _, world = target_rig.pose(values)
            positions = target_rig.marker_positions(world)
            result = []
            for limb in LEG_NAMES:
                result.extend((positions[limb] - targets[limb]) / target_rig.leg_lengths[limb] * 18)
                if package['contact_flags'][limb][frame]:
                    result.append(np.dot(positions[limb], target_rig.up) / target_rig.asset.height * 25)
            result.extend((values[:-1] - seed[:-1]) * .2)
            result.append((values[-1] - seed[-1]) / target_rig.asset.height * 2)
            if previous is not None:
                result.extend((values[:-1] - previous[:-1]) * .1)
            return np.asarray(result)
        solved = least_squares(residual, np.clip(seed, target_rig.lower + 1e-6, target_rig.upper - 1e-6),
                               bounds=(target_rig.lower, target_rig.upper), max_nfev=max_evaluations)
        fitted.append(solved.x)
        previous = solved.x
        diagnostics.append({'frame': frame, 'cost': float(solved.cost), 'converged': bool(solved.success)})
    if package['loop']:
        fitted[-1] = fitted[0]
    t, q, _, corrected = bake(target_rig, times, np.asarray(fitted))
    return t, q, corrected, diagnostics


def validate_export(source_asset, output, clip='Walk', fps=192):
    from .asset import Asset
    exported = Asset(output)
    unchanged = {key: source_asset.document.get(key) == exported.document.get(key)
                 for key in ('nodes', 'meshes', 'skins', 'materials', 'images', 'textures', 'samplers')}
    prefix = exported.blob[:len(source_asset.blob)] == source_asset.blob
    key_times = np.unique(np.concatenate([accessor(exported.document, exported.blob, sampler['input']).ravel()
                                         for sampler in exported.animations[clip]['samplers']]))
    times = np.unique(np.r_[key_times, (key_times[:-1] + key_times[1:]) / 2,
                           np.linspace(0, exported.duration(clip), round(exported.duration(clip) * fps) + 1)])
    translations, rotations = exported.sample(clip, times)
    minimum = float('inf')
    bone_errors, surface_endpoints = [], []
    followers={}
    for pair in exported.animations[clip].get('extras',{}).get('paw_follow_helpers',[]):
        helper,foot=exported.name_to_id[pair['helper']],exported.name_to_id[pair['foot']]
        if (helper not in exported.joints or foot not in exported.joints or
            exported.parent[helper]!=exported.parent[foot] or np.any(exported.parent==helper) or
            not pair['helper'].startswith('Front_Leg_Ankle_') or not pair['foot'].startswith('Front_Leg_Foot_')):
            raise ValueError('Invalid declared leaf paw-helper follow relationship')
        followers[helper]=foot
    helper_errors,follow_errors=[],[]
    for i, (t, q) in enumerate(zip(translations, rotations)):
        world = exported.world(t, q)
        skin = exported.skin(world)
        minimum = min(minimum, float(skin[:, 1].min()))
        if i in (0, len(times) - 1):
            surface_endpoints.append(skin)
        for node in exported.joints:
            parent = exported.parent[node]
            if parent in exported.joints:
                original = np.linalg.norm(exported.world_rest[node, :3, 3] - exported.world_rest[parent, :3, 3])
                posed = np.linalg.norm(world[node, :3, 3] - world[parent, :3, 3])
                if node in followers:
                    helper_errors.append(abs(original-posed))
                    expected=world[followers[node]] @ np.linalg.inv(exported.world_rest[followers[node]]) @ exported.world_rest[node]
                    follow_errors.append(float(np.max(np.abs(expected-world[node]))))
                else:
                    bone_errors.append(abs(original - posed))
    old_clips = {name: animation for name, animation in source_asset.animations.items() if name != clip}
    preserved_clips = all(exported.animations.get(name) == animation for name, animation in old_clips.items())
    loop_gap = float(np.linalg.norm(surface_endpoints[-1] - surface_endpoints[0], axis=1).max())
    quaternion_error = float(np.abs(np.linalg.norm(rotations, axis=2) - 1).max())
    is_loop = bool(exported.animations[clip].get('extras', {}).get('loop', False))
    record = {'source_sha256': digest(source_asset.path), 'export_sha256': digest(output),
        'unchanged_structure': unchanged, 'original_binary_prefix_preserved': prefix,
        'other_clips_preserved': preserved_clips, 'sampled_poses': len(times),
        'minimum_surface_y': minimum,
        'maximum_bone_length_change': float(max(bone_errors, default=0)),
        'bone_length_policy':'All segment lengths; separately declared leaf heel-helper offsets may follow the paw.',
        'paw_follow_helpers':exported.animations[clip].get('extras',{}).get('paw_follow_helpers',[]),
        'maximum_helper_parent_distance_change':float(max(helper_errors,default=0)),
        'maximum_helper_follow_transform_error':float(max(follow_errors,default=0)),
        'loop_surface_gap': loop_gap, 'maximum_quaternion_norm_error': quaternion_error,
        'sampling_fps': fps, 'keys_and_between_key_poses': True,
        'numerical_pass': bool(all(unchanged.values()) and prefix and preserved_clips and
                          minimum >= -source_asset.height * .004 and
                          max(bone_errors, default=0) < source_asset.height * 1e-4 and
                          max(follow_errors,default=0) < source_asset.height * 1e-4 and
                          quaternion_error < 1e-5 and (not is_loop or loop_gap < source_asset.height * 1e-5)),
        'visual_acceptance': 'pending', 'godot_integration': 'pending'}
    return record
