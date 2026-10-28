"""Fit a fixed mesh, local skin and directions to an explicit <=30 Hz creature.

This is an APPROXIMATE authoring experiment, never a lossless conversion or an
installation tool.  It does not resample/rewrite bone animation.  Read the
measured independent errors and perform fresh engine/artistic QA before use.
NumPy/SciPy are required; callers should limit BLAS threads for batch work.

``bake(source, output, iterations=6, report=None, fit_skin=True)`` preserves the
source and refuses to overwrite an existing output.  ``fit_skin=False`` gives
the original-skin constant-mesh fallback.  No helper bones are introduced.
"""
from __future__ import annotations

import argparse
import copy
import hashlib
import json
import shutil
from pathlib import Path

import numpy as np
from scipy.optimize import minimize

from .asset import accessor, digest, read_glb, write_glb
from .native_shapes import NativeShapeAsset
from .packing import append_array, compact


FPS = 30
_EPS = 1e-30


def _hash_array(values):
    return hashlib.sha256(np.ascontiguousarray(values).tobytes()).hexdigest()


def _unit(values):
    return values / np.maximum(np.linalg.norm(values, axis=-1, keepdims=True), _EPS)


def _preflight(document, blob, allow_step_exceptions=False):
    """Reject dense/cubic/ambiguous input rather than silently changing it."""
    names, maximum_hz, continuous_hz, exceptions = [], 0., 0., []
    for animation in document.get('animations', []):
        name = animation.get('name')
        if not name or name in names:
            raise ValueError('Unique explicit clip names are required')
        names.append(name)
        if not any(c['target']['path'] != 'weights' for c in animation['channels']):
            raise ValueError('A morph-only clip cannot retain its duration without adding a node curve')
        for si, sampler in enumerate(animation['samplers']):
            if sampler.get('interpolation', 'LINEAR') not in ('LINEAR', 'STEP'):
                raise ValueError('Only LINEAR/STEP source interpolation is supported')
            times = accessor(document, blob, sampler['input']).ravel()
            if not len(times) or not np.isfinite(times).all():
                raise ValueError('Empty or nonfinite animation times')
            if len(times) > 1:
                delta = np.diff(times)
                if (delta <= 0).any():
                    raise ValueError('Source animation timestamps must increase')
                hz = float(1 / delta.min())
                maximum_hz = max(maximum_hz, hz)
                if sampler.get('interpolation', 'LINEAR') == 'LINEAR':
                    continuous_hz = max(continuous_hz, hz)
                # Float32 timestamps at long clip times can round one interval.
                if delta.min() < 1 / FPS - 2e-5:
                    if allow_step_exceptions and sampler.get('interpolation') == 'STEP':
                        exceptions.append({'clip': name, 'sampler': si,
                            'targets': [c['target'] for c in animation['channels'] if c['sampler'] == si],
                            'knots': len(times), 'minimum_interval': float(delta.min()),
                            'input_sha256': _hash_array(times), 'preserved_exactly': True})
                    else:
                        raise ValueError('Expected an explicit already-30-Hz source; '
                                         f'{name!r} contains {hz:.4f} Hz knots')
    for mesh in document.get('meshes', []):
        for primitive in mesh['primitives']:
            if primitive.get('mode', 4) != 4:
                raise ValueError('Only triangle primitives are supported')
            for target in primitive.get('targets', []):
                if set(target) - {'POSITION', 'NORMAL', 'TANGENT'}:
                    raise ValueError('Unknown corrective field')
            attrs = primitive['attributes']
            sets = sorted(int(k.split('_')[1]) for k in attrs if k.startswith('JOINTS_'))
            if sets and sets not in ([0], [0, 1]):
                raise ValueError('Only the original four/eight influence layouts are supported')
            for k in sets:
                spec = document['accessors'][attrs[f'JOINTS_{k}']]
                if spec['componentType'] not in (5121, 5123) or spec.get('normalized'):
                    raise ValueError('JOINTS must be unsigned non-normalized integers')
    return {'maximum_source_knot_hz': maximum_hz, 'maximum_continuous_knot_hz': continuous_hz,
            'clips': names, 'continuous_training_hz': FPS,
            'training_clock': 'densest original continuous clock plus exact STEP knots and endpoints',
            'allow_step_exceptions': allow_step_exceptions, 'step_exceptions': exceptions,
            'all_source_keys_at_most_30_hz': not exceptions,
            'dense_source_was_resampled': False}


def _slerp(a, b, alpha):
    b = b.copy()
    dot = np.einsum('ij,ij->i', a, b)
    b[dot < 0] *= -1
    angle = np.arccos(np.clip(np.abs(dot), 0, 1))
    sine = np.sin(angle)
    x = np.full(len(a), 1 - alpha)
    y = np.full(len(a), alpha)
    active = sine > 1e-8
    x[active] = np.sin((1 - alpha) * angle[active]) / sine[active]
    y[active] = np.sin(alpha * angle[active]) / sine[active]
    return _unit(x[:, None] * a + y[:, None] * b)


def _states(asset, *, training):
    """Independent shifted cadence and all directed clip-pair local-TRS blends."""
    worlds, morphs, labels, categories = [], [], [], []

    def add(t, q, s, mw, label, category):
        worlds.append(asset.world(t, q, s))
        morphs.append({n: np.asarray(w, float) for n, w in mw.items()})
        labels.append(label)
        categories.append(category)

    for clip in asset.animations:
        duration = asset.duration(clip)
        samplers = asset.animations[clip]['samplers']
        continuous = [accessor(asset.d, asset.b, sm['input']).ravel() for sm in samplers
                      if sm.get('interpolation', 'LINEAR') == 'LINEAR']
        steps = [accessor(asset.d, asset.b, sm['input']).ravel() for sm in samplers
                 if sm.get('interpolation') == 'STEP']
        step_times = np.unique(np.concatenate(steps)) if steps else np.array([])
        if training:
            clock = max(continuous, key=len) if continuous else np.arange(0., duration, 1 / FPS)
            times = np.unique(np.r_[0., clock, step_times, duration])
        else:
            times = np.arange(.38196601125 / FPS, duration, 1 / FPS)
            if not len(times):
                times = np.array([duration * .38196601125])
        t, q, s, mw = asset.sample(clip, times)
        for i, time in enumerate(times):
            add(t[i], q[i], s[i], {n: w[i] for n, w in mw.items()},
                f'{clip}@{time:.12g}', 'training' if training else 'off_grid')
        if not training and len(step_times):
            # Query the exact representable side of each authored jump. Never
            # retime/smooth a STEP curve or move its boundary for fitting.
            boundaries = np.unique(np.r_[np.nextafter(step_times, -np.inf),
                                          np.nextafter(step_times, np.inf)])
            boundaries = boundaries[(boundaries >= 0) & (boundaries <= duration)]
            t, q, s, mw = asset.sample(clip, boundaries)
            for i, time in enumerate(boundaries):
                add(t[i], q[i], s[i], {n: w[i] for n, w in mw.items()},
                    f'{clip}:STEP_side@{time:.17g}', 'step_boundary')
    add(asset.t, asset.q, asset.s, asset.default_weights, 'NEUTRAL', 'neutral')
    if not training:
        for first in asset.animations:
            for second in asset.animations:
                if first == second:
                    continue
                a = asset.sample(first, [asset.duration(first) * .731])
                b = asset.sample(second, [asset.duration(second) * .193])
                for alpha in (.237, .613):
                    add((1 - alpha) * a[0][0] + alpha * b[0][0],
                        _slerp(a[1][0], b[1][0], alpha),
                        (1 - alpha) * a[2][0] + alpha * b[2][0],
                        {n: (1 - alpha) * a[3][n][0] + alpha * b[3][n][0]
                         for n in asset.default_weights},
                        f'{first}->{second}@{alpha}', 'crossfade')
    return {'world': np.asarray(worlds), 'morph': morphs,
            'labels': labels, 'categories': np.asarray(categories)}


def _primitive_data(asset, part, primitive):
    attrs = primitive['attributes']
    n = len(part['position'])
    base = part['position'][:, :3].copy()
    normal = accessor(asset.d, asset.b, attrs['NORMAL']) if 'NORMAL' in attrs else None
    tangent = accessor(asset.d, asset.b, attrs['TANGENT']) if 'TANGENT' in attrs else None
    targets = {}
    for field in ('POSITION', 'NORMAL', 'TANGENT'):
        targets[field] = np.asarray([
            accessor(asset.d, asset.b, target[field]) if field in target
            else np.zeros((n, 3)) for target in primitive.get('targets', [])])
    if 'joints' in part:
        dense = np.zeros((n, len(part['nodes'])))
        for slot in range(part['joints'].shape[1]):
            np.add.at(dense, (np.arange(n), part['joints'][:, slot]), part['weights'][:, slot])
        if not np.isfinite(dense).all() or (dense < 0).any() or (dense.sum(1) <= 0).any():
            raise ValueError('Invalid original skin weights')
    else:
        dense = np.ones((n, 1))
    for values in (base, normal, tangent, *targets.values()):
        if values is not None and not np.isfinite(values).all():
            raise ValueError('Nonfinite source geometry')
    return {'base': base, 'normal': normal, 'tangent': tangent,
            'targets': targets, 'weights': dense}


def _skin(part, states):
    if 'joints' not in part:
        return states['world'][:, part['node'], None, :3]
    return (states['world'][:, part['nodes']] @ part['bind'])[:, :, :3]


def _target(data, part, states, skin, field):
    """Float64 native TRS/relative-morph reference, not GPU-quantized readback."""
    base = data[{'POSITION': 'base', 'NORMAL': 'normal', 'TANGENT': 'tangent'}[field]]
    if base is None:
        return None
    base = base[:, :3]
    result = np.empty((len(skin), len(base), 3))
    count = len(data['targets'][field])
    for start in range(0, len(skin), 16):
        end = min(start + 16, len(skin))
        local = np.broadcast_to(base, (end - start, *base.shape)).copy()
        if count:
            mw = np.asarray([s[part['node']][:count] for s in states['morph'][start:end]])
            local += np.einsum('tm,mvc->tvc', mw, data['targets'][field])
        blend = np.einsum('vj,tjab->tvab', data['weights'], skin[start:end])
        value = np.einsum('tvab,tvb->tva', blend[..., :3], local)
        result[start:end] = value + blend[..., 3] if field == 'POSITION' else _unit(value)
    return result


def _groups(data):
    """Only exact full source trajectories may share fitted position/skin.

    Equal position + equal dense skin + every POSITION delta equal is an
    all-time certificate, unlike coincident rest positions or sampled equality.
    Normal/UV seams keep separate direction fits.
    """
    groups = {}
    for vertex in range(len(data['base'])):
        key = b''.join(np.ascontiguousarray(x).tobytes() for x in (
            data['base'][vertex], data['weights'][vertex],
            data['targets']['POSITION'][:, vertex]))
        groups.setdefault(key, []).append(vertex)
    return list(groups.values())


def _allowed(asset, part, weights):
    if 'nodes' not in part:
        return [np.array([0]) for _ in weights]
    lookup = {int(n): i for i, n in enumerate(part['nodes'])}
    parents = np.array([lookup.get(int(asset.parent[n]), -1) for n in part['nodes']])
    # Geometry is mesh-local. Joint rest translations are world-space, so an
    # untransformed comparison can select the opposite limb on placed/scaled
    # meshes. Include real parent segments even outside the skin palette.
    inverse_mesh = np.linalg.inv(asset.rest[part['node']])
    heads_world = asset.rest[part['nodes'], :3, 3]
    starts_world = np.array([asset.rest[asset.parent[n], :3, 3]
                             if asset.parent[n] >= 0 else asset.rest[n, :3, 3]
                             for n in part['nodes']])
    heads = (inverse_mesh @ np.c_[heads_world, np.ones(len(heads_world))].T).T[:, :3]
    starts = (inverse_mesh @ np.c_[starts_world, np.ones(len(starts_world))].T).T[:, :3]
    line = heads - starts
    length2 = np.maximum(np.sum(line * line, axis=1), 1e-20)
    result = []
    for i, row in enumerate(weights):
        support = set(np.flatnonzero(row > 0).tolist())
        allowed = set(support)
        for joint in support:
            if parents[joint] >= 0:
                allowed.add(int(parents[joint]))
            allowed.update(np.flatnonzero(parents == joint).tolist())
        position = part['position'][i, :3]
        fraction = np.clip(np.sum((position - starts) * line, axis=1) / length2, 0, 1)
        distance = np.linalg.norm(position - (starts + fraction[:, None] * line), axis=1)
        allowed.update(np.argsort(distance, kind='stable')[:3].tolist())
        result.append(np.array(sorted(allowed), dtype=int))
    return result


def _fit_position(skin, target, weights, base, importance=None):
    blend = np.einsum('j,tjab->tab', weights, skin)
    if importance is None:
        importance = np.full(len(skin), 1 / len(skin))
    matrix = blend[..., :3]
    h = np.einsum('t,tai,taj->ij', importance, matrix, matrix)
    rhs = np.einsum('t,tai,ta->i', importance, matrix, target - blend[..., 3])
    regularizer = max(float(np.trace(h)) * 1e-10, 1e-14)
    return np.linalg.solve(h + np.eye(3) * regularizer, rhs + base * regularizer)


def _score(skin, target, weights, position, radius):
    error = np.einsum('j,tjab,b->ta', weights, skin, np.r_[position, 1.]) - target
    # Scale by radius to avoid sixth powers of large/small world units.
    return float(np.mean((1 + np.sum(error * error, axis=1) / radius**2)**3))


def _ordinary_score(skin, target, weights, position):
    error = np.einsum('j,tjab,b->ta', weights, skin, np.r_[position, 1.]) - target
    return float(np.mean(np.sum(error * error, axis=1)))


def _fit_weights(skin, target, position, current, allowed, budget, importance):
    a = np.einsum('tjab,b->taj', skin[:, allowed], np.r_[position, 1.])
    # Sum-to-one makes a common trajectory cancel exactly. Center it out to
    # avoid subtracting large world-position normal-equation terms near a
    # translated mesh; this does not change the constrained problem.
    origin = a[:, :, 0].copy()
    a -= origin[:, :, None]
    target = target - origin
    h = np.einsum('t,tai,taj->ij', importance, a, a)
    g = np.einsum('t,tai,ta->i', importance, a, target)
    scale = max(float(np.trace(h)), 1e-20)
    h, g = h / scale, g / scale

    def solve(indices, seed):
        hh, gg = h[np.ix_(indices, indices)], g[indices]
        start = seed[indices].copy()
        start = start / start.sum() if start.sum() else np.full(len(indices), 1 / len(indices))
        # A small proximity term resolves indistinguishable bone trajectories.
        hh = hh + np.eye(len(indices)) * 1e-10
        gg = gg + start * 1e-10
        solution = minimize(lambda z: float(z @ hh @ z - 2 * gg @ z), start,
                            jac=lambda z: 2 * (hh @ z - gg), method='SLSQP',
                            bounds=[(0., 1.)] * len(indices),
                            constraints={'type': 'eq', 'fun': lambda z: z.sum() - 1,
                                         'jac': lambda z: np.ones(len(z))},
                            options={'ftol': 1e-13, 'maxiter': 100})
        if not solution.success or not np.isfinite(solution.x).all():
            return None
        row = np.zeros(len(allowed))
        row[indices] = np.maximum(solution.x, 0)
        return row / row.sum()

    seed = current[allowed]
    row = solve(np.arange(len(allowed)), seed)
    if row is None:
        return current.copy()
    if np.count_nonzero(row > 0) > budget:
        indices = np.argsort(-row, kind='stable')[:budget]
        row = solve(indices, row)
        if row is None:
            return current.copy()
    result = np.zeros_like(current)
    result[allowed] = row
    return result


def _fit_directions(skin, weights, target, original):
    if target is None:
        return None
    h = np.zeros((len(weights), 3, 3))
    for start in range(0, len(skin), 16):
        c = np.einsum('vj,tjab->tvab', weights, skin[start:start + 16, :, :, :3])
        n = target[start:start + 16]
        projected = c - np.einsum('tvi,tvj->tvij', n, np.einsum('tvab,tva->tvb', c, n))
        h += np.einsum('tvai,tvaj->vij', c, projected)
    _, vectors = np.linalg.eigh(h)
    result = vectors[:, :, 0]
    dot = np.zeros(len(weights))
    for start in range(0, len(skin), 16):
        c = np.einsum('vj,tjab->tvab', weights, skin[start:start + 16, :, :, :3])
        dot += np.einsum('tvi,tvi->v', np.einsum('tvab,vb->tva', c, result),
                         target[start:start + 16])
    result[dot < 0] *= -1
    degenerate = np.max(np.abs(h), axis=(1, 2)) < 1e-20
    result[degenerate] = _unit(original[degenerate, :3])
    result[np.max(np.linalg.norm(target, axis=2), axis=0) == 0] = 0
    return _unit(result)


def _fit(asset, part, data, skin, targets, height, iterations, fit_skin):
    weights = data['weights'].copy()
    positions = data['base'].copy()
    original_fixed = positions.copy()
    groups = _groups(data)
    allowed = _allowed(asset, part, weights)
    budget = part['joints'].shape[1] if 'joints' in part else 1
    radius = max(height * .00015, 1e-12)
    uniform = np.full(len(skin), 1 / len(skin))
    for ids in groups:
        i = ids[0]
        original_fixed[ids] = _fit_position(skin, targets[:, i], weights[i], data['base'][i])
        if fit_skin:
            weights[ids] /= weights[i].sum()
            # First learn weights at the ORIGINAL base. Starting with a large
            # original-skin displacement traps alternating solves in a worse
            # local minimum and prevents a nearby joint from explaining motion.
            proposed = _fit_weights(skin, targets[:, i], data['base'][i], weights[i],
                                    allowed[i], budget, uniform)
            if _ordinary_score(skin, targets[:, i], proposed, data['base'][i]) < _ordinary_score(
                    skin, targets[:, i], weights[i], data['base'][i]):
                weights[ids] = proposed
        else:
            positions[ids] = original_fixed[ids]
    ordinary_iterations = 12 if fit_skin and iterations else 0
    for _ in range(ordinary_iterations):
        for ids in groups:
            i = ids[0]
            y, w, x = targets[:, i], weights[i].copy(), positions[i].copy()
            proposed = _fit_weights(skin, y, x, w, allowed[i], budget, uniform)
            if _ordinary_score(skin, y, proposed, x) < _ordinary_score(skin, y, w, x):
                w = proposed
            x = _fit_position(skin, y, w, data['base'][i])
            weights[ids], positions[ids] = w, x
    if fit_skin and not ordinary_iterations:
        for ids in groups:
            i = ids[0]
            positions[ids] = _fit_position(skin, targets[:, i], weights[i], data['base'][i])
    for _ in range(iterations):
        for ids in groups:
            i = ids[0]
            y, w, x = targets[:, i], weights[i].copy(), positions[i].copy()
            prediction = np.einsum('j,tjab,b->ta', w, skin, np.r_[x, 1.])
            error2 = np.sum((prediction - y)**2, axis=1)
            importance = (error2 + radius**2)**2
            importance = np.maximum(importance / max(float(importance.max()), _EPS), 1e-6)
            importance /= importance.sum()
            best = _score(skin, y, w, x, radius)
            if fit_skin:
                proposed = _fit_weights(skin, y, x, w, allowed[i], budget, importance)
                score = _score(skin, y, proposed, x, radius)
                if score < best:
                    w, best = proposed, score
            proposed = _fit_position(skin, y, w, data['base'][i], importance)
            delta = proposed - data['base'][i]
            limit = height * .03
            if np.linalg.norm(delta) > limit:
                proposed = data['base'][i] + delta * limit / np.linalg.norm(delta)
            for alpha in (1., .5, .25, .125):
                trial = x + alpha * (proposed - x)
                if _score(skin, y, w, trial, radius) < best:
                    x = trial
                    break
            weights[ids], positions[ids] = w, x
    fallback_groups = 0
    if fit_skin:
        # Keep the separate original-skin solution as a final competing model,
        # never as the weight solver's initial displaced base. A perfectly
        # static correction should not become worse merely because we also
        # tried to explain it with joint motion.
        for ids in groups:
            i = ids[0]
            old = data['weights'][i] / data['weights'][i].sum()
            fixed = _fit_position(skin, targets[:, i], old, data['base'][i])
            if _score(skin, targets[:, i], old, fixed, radius) < _score(
                    skin, targets[:, i], weights[i], positions[i], radius):
                weights[ids], positions[ids] = old, fixed
                fallback_groups += 1
    return positions, weights, original_fixed, {
        'coincident_certified_groups': sum(len(g) > 1 for g in groups),
        'independent_fit_groups': len(groups), 'influence_budget': budget,
        'local_joint_policy': 'original positive support, immediate palette parents/children, '
                              'and three nearest anatomical rest segments in mesh-local space',
        'segment_distance_space': 'inverse(mesh.rest) applied to joint/parent rest world positions',
        'weight_only_seed_at_original_base': fit_skin,
        'ordinary_alternating_iterations': ordinary_iterations,
        'final_original_skin_fallback_groups': fallback_groups,
        'robust_objective': 'p6 residual with height-scaled smoothing; descending alternating steps',
        'robust_smoothing_radius_over_height': radius / height,
        'proposal_displacement_limit_over_height': .03,
        'iterations': iterations, 'fit_skin': fit_skin}


def _pack_skin(document, blob, attrs, dense, budget):
    joints = np.argsort(-dense, axis=1, kind='stable')[:, :budget]
    weights = np.take_along_axis(dense, joints, axis=1)
    if joints.shape[1] < budget:
        pad = ((0, 0), (0, budget - joints.shape[1]))
        joints, weights = np.pad(joints, pad), np.pad(weights, pad)
    weights /= weights.sum(1, keepdims=True)
    weights = weights.astype('<f4')
    if not np.isfinite(weights).all() or (weights < 0).any():
        raise ValueError('Invalid fitted skin')
    for slot in range(budget // 4):
        old_spec = document['accessors'][attrs[f'JOINTS_{slot}']]
        dtype = '<u1' if old_spec['componentType'] == 5121 else '<u2'
        if joints.max() > np.iinfo(np.dtype(dtype)).max:
            raise ValueError('Fitted JOINTS overflow original unsigned component type')
        values = np.ascontiguousarray(joints[:, slot * 4:(slot + 1) * 4], dtype=dtype)
        blob.extend(b'\0' * (-len(blob) % 4))
        document['bufferViews'].append({'buffer': 0, 'byteOffset': len(blob), 'byteLength': values.nbytes})
        blob.extend(values.tobytes())
        document['accessors'].append({'bufferView': len(document['bufferViews']) - 1,
                                     'componentType': old_spec['componentType'],
                                     'count': len(values), 'type': 'VEC4'})
        attrs[f'JOINTS_{slot}'] = len(document['accessors']) - 1
        attrs[f'WEIGHTS_{slot}'] = append_array(document, blob,
            weights[:, slot * 4:(slot + 1) * 4], 'VEC4')
    return joints, weights


def _statistics(position_error, normal_error, tangent_error, height):
    result = {'observations': int(position_error.size),
              'maximum_position': float(position_error.max(initial=0)),
              'rms_position': float(np.sqrt(np.mean(position_error**2))) if position_error.size else 0.}
    result['maximum_position_over_height'] = result['maximum_position'] / height
    result['rms_position_over_height'] = result['rms_position'] / height
    for field, values in (('normal', normal_error), ('tangent', tangent_error)):
        if values is not None:
            result[f'maximum_{field}_degrees'] = float(values.max(initial=0))
            result[f'rms_{field}_degrees'] = float(np.sqrt(np.mean(values**2))) if values.size else 0.
    return result


def _evaluate(data, part, states, skin, position, weights, normal, tangent, height):
    reference = {field: _target(data, part, states, skin, field)
                 for field in ('POSITION', 'NORMAL', 'TANGENT')}
    errors = {field: [] for field in reference}
    for start in range(0, len(skin), 16):
        end = min(start + 16, len(skin))
        blend = np.einsum('vj,tjab->tvab', weights, skin[start:end])
        predicted = np.einsum('tvab,vb->tva', blend[..., :3], position) + blend[..., 3]
        errors['POSITION'].append(np.linalg.norm(predicted - reference['POSITION'][start:end], axis=2))
        for field, local in (('NORMAL', normal), ('TANGENT', tangent)):
            if local is not None:
                value = _unit(np.einsum('tvab,vb->tva', blend[..., :3], local[:, :3]))
                # atan2 is stable near zero and avoids a spurious arccos floor.
                ref = reference[field][start:end]
                angle = np.degrees(np.arctan2(np.linalg.norm(np.cross(value, ref), axis=2),
                                             np.sum(value * ref, axis=2)))
                # A direction appearing/disappearing is not a zero-degree match.
                undefined = (np.linalg.norm(value, axis=2) < 1e-12) != (np.linalg.norm(ref, axis=2) < 1e-12)
                angle[undefined] = 180.
                errors[field].append(angle)
    errors = {k: np.concatenate(v) if v else None for k, v in errors.items()}
    categories = {}
    for category in sorted(set(states['categories'])):
        mask = states['categories'] == category
        categories[str(category)] = _statistics(errors['POSITION'][mask],
            None if errors['NORMAL'] is None else errors['NORMAL'][mask],
            None if errors['TANGENT'] is None else errors['TANGENT'][mask], height)
        categories[str(category)]['poses'] = int(mask.sum())
    worst = np.unravel_index(np.argmax(errors['POSITION']), errors['POSITION'].shape)
    return {'all': _statistics(errors['POSITION'], errors['NORMAL'], errors['TANGENT'], height),
            'categories': categories, 'worst_position': {
                'label': states['labels'][worst[0]], 'primitive_vertex': int(worst[1])}}


def _preservation(asset, output):
    """Read the written file back; attest arrays, not accessor IDs/JSON order."""
    document, blob = read_glb(output)
    original = asset.d
    assert len(document.get('skins', [])) == len(original.get('skins', []))
    arrays = []
    for i, old in enumerate(original.get('skins', [])):
        new = document['skins'][i]
        assert {k: v for k, v in old.items() if k != 'inverseBindMatrices'} == {
            k: v for k, v in new.items() if k != 'inverseBindMatrices'}
        if 'inverseBindMatrices' in old:
            a = accessor(original, asset.b, old['inverseBindMatrices'])
            b = accessor(document, blob, new['inverseBindMatrices'])
            assert _hash_array(a) == _hash_array(b)
            arrays.append({'array': f'skin:{i}:inverseBindMatrices', 'sha256': _hash_array(a)})
    assert len(original.get('animations', [])) == len(document.get('animations', []))
    for old, new in zip(original.get('animations', []), document.get('animations', [])):
        old_channels = [c for c in old['channels'] if c['target']['path'] != 'weights']
        assert len(old_channels) == len(new['channels'])
        for a, b in zip(old_channels, new['channels']):
            assert a['target'] == b['target']
            sa, sb = old['samplers'][a['sampler']], new['samplers'][b['sampler']]
            assert {k: v for k, v in sa.items() if k not in ('input', 'output')} == {
                k: v for k, v in sb.items() if k not in ('input', 'output')}
            for field in ('input', 'output'):
                va, vb = accessor(original, asset.b, sa[field]), accessor(document, blob, sb[field])
                assert _hash_array(va) == _hash_array(vb)
                arrays.append({'array': f"{old['name']}:{a['target']['node']}:{a['target']['path']}:{field}",
                               'sha256': _hash_array(va)})
    for i, old_node in enumerate(original['nodes']):
        assert {k: v for k, v in old_node.items() if k not in ('mesh', 'weights')} == {
            k: v for k, v in document['nodes'][i].items() if k not in ('mesh', 'weights')}
        if 'mesh' not in old_node:
            continue
        old_mesh = original['meshes'][old_node['mesh']]
        new_mesh = document['meshes'][document['nodes'][i]['mesh']]
        for key, value in old_mesh.get('extras', {}).items():
            if key != 'targetNames':
                assert new_mesh['extras'][key] == value
        for pi, (a, b) in enumerate(zip(old_mesh['primitives'], new_mesh['primitives'])):
            changed = bool(a.get('targets'))
            for field, index in a['attributes'].items():
                if changed and field in ('POSITION', 'NORMAL', 'TANGENT', 'JOINTS_0', 'JOINTS_1', 'WEIGHTS_0', 'WEIGHTS_1'):
                    continue
                va, vb = accessor(original, asset.b, index), accessor(document, blob, b['attributes'][field])
                assert _hash_array(va) == _hash_array(vb)
                arrays.append({'array': f'node:{i}:primitive:{pi}:{field}', 'sha256': _hash_array(va)})
            if 'indices' in a:
                va, vb = accessor(original, asset.b, a['indices']), accessor(document, blob, b['indices'])
                assert _hash_array(va) == _hash_array(vb)
                arrays.append({'array': f'node:{i}:primitive:{pi}:indices', 'sha256': _hash_array(va)})
            assert a.get('material') == b.get('material')
            assert {k: v for k, v in a.items() if k not in ('attributes', 'indices', 'targets')} == {
                k: v for k, v in b.items() if k not in ('attributes', 'indices', 'targets')}
            assert not b.get('targets')
    for key in ('materials', 'textures', 'samplers'):
        assert original.get(key) == document.get(key)
    assert len(original.get('images', [])) == len(document.get('images', []))
    for i, (a, b) in enumerate(zip(original.get('images', []), document.get('images', []))):
        av, bv = original['bufferViews'][a['bufferView']], document['bufferViews'][b['bufferView']]
        raw_a = asset.b[av.get('byteOffset', 0):av.get('byteOffset', 0) + av['byteLength']]
        raw_b = blob[bv.get('byteOffset', 0):bv.get('byteOffset', 0) + bv['byteLength']]
        assert raw_a == raw_b
        arrays.append({'array': f'image:{i}', 'sha256': hashlib.sha256(raw_a).hexdigest()})
    return arrays


def _summary(rows, state_count, height, field, category=None):
    """Pool errors over the WHOLE surface, including untouched zero-error parts."""
    result = {'observations': 0, 'maximum_position': 0., 'rms_position': 0.}
    sums, counts = {}, {}
    for row in rows:
        if row['status'] == 'morph_free_untouched':
            count = row['vertices'] * state_count
            result['observations'] += count
            for direction in row['direction_fields']:
                name = f'rms_{direction}_degrees'
                counts[name] = counts.get(name, 0) + count
                sums.setdefault(name, 0.)
                result.setdefault(f'maximum_{direction}_degrees', 0.)
            continue
        if category is not None and category not in row[field]['categories']:
            continue
        item = row[field]['all'] if category is None else row[field]['categories'][category]
        count = item['observations']
        result['observations'] += count
        for name, value in item.items():
            if name.startswith('maximum_'):
                result[name] = max(result.get(name, 0.), value)
            elif name.startswith('rms_'):
                sums[name] = sums.get(name, 0.) + value**2 * count
                counts[name] = counts.get(name, 0) + count
    for name, value in sums.items():
        # Position includes every vertex, including untouched parts. Direction
        # RMS covers only vertices that actually carry that direction field.
        denominator = result['observations'] if name.startswith('rms_position') else counts[name]
        result[name] = float(np.sqrt(value / max(denominator, 1)))
    result['maximum_position_over_height'] = result['maximum_position'] / height
    result['rms_position_over_height'] = result['rms_position'] / height
    return result


def _original_mesh_bounds(document, binary, mesh):
    """Raw ArrayMesh envelope: float32 base AND each morph endpoint.

    This deliberately includes inactive corrective endpoints: actor grounding
    and normalization use the original mesh envelope, not a selected pose or
    only the smaller base/fitted mesh. Existing authored metadata wins.
    """
    low = np.full(3, np.inf, dtype='f4')
    high = np.full(3, -np.inf, dtype='f4')
    for primitive in mesh['primitives']:
        base = accessor(document, binary, primitive['attributes']['POSITION']).astype('f4')
        low, high = np.minimum(low, base.min(0)), np.maximum(high, base.max(0))
        for target in primitive.get('targets', []):
            if 'POSITION' not in target:
                continue
            endpoint = base + accessor(document, binary, target['POSITION']).astype('f4')
            low, high = np.minimum(low, endpoint.min(0)), np.maximum(high, endpoint.max(0))
    return {'position': low.tolist(), 'size': (high - low).tolist()}


def bake(source: Path, output: Path, *, iterations=6, report: Path = None,
         fit_skin=True, allow_step_exceptions=False) -> dict:
    """Create a measured fixed-mesh candidate; never install or change source.

    Output errors include float32 serialization, every vertex, neutral defaults,
    shifted off-grid clips and all directed local-TRS crossfades.  These offline
    native-convention errors are not a GPU/Editor/visual acceptance certificate.
    """
    source, output = Path(source).resolve(), Path(output).resolve()
    if report is not None:
        report = Path(report).resolve()
        if report in (source, output):
            raise ValueError('Report must differ from source and GLB output')
    if source == output:
        raise ValueError('Source and output must differ')
    if output.exists():
        raise FileExistsError(output)
    if not isinstance(iterations, int) or iterations < 0:
        raise ValueError('iterations must be a nonnegative integer')
    source_hash = digest(source)
    document, binary = read_glb(source)
    if not any(p.get('targets') for m in document.get('meshes', []) for p in m['primitives']):
        output.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, output)
        if digest(source) != source_hash or digest(output) != source_hash:
            raise RuntimeError('Source changed during copy; candidate is unqualified')
        result = {'status': 'already_baked', 'artifact': str(output), 'sha256': digest(output),
                  'source': str(source), 'source_sha256': source_hash,
                  'raw_bytes': output.stat().st_size, 'skin_recomputed': False,
                  'source_preserved': digest(source) == source_hash, 'primitive_reports': []}
        if report is not None:
            Path(report).parent.mkdir(parents=True, exist_ok=True)
            Path(report).write_text(json.dumps(result, indent=2) + '\n', encoding='utf-8')
        return result
    source_sampling = _preflight(document, binary, allow_step_exceptions)
    asset = NativeShapeAsset(source)
    height = float(np.ptp(asset.vertices[:, 1]))
    if not np.isfinite(height) or height <= 1e-12:
        raise ValueError('Nonzero original native Y height is required')
    training, validation = _states(asset, training=True), _states(asset, training=False)
    original_document = copy.deepcopy(document)
    blob = bytearray(binary)
    # Different skin instances of one shared mesh need distinct fitted arrays.
    for node in document['nodes']:
        if 'mesh' in node and any(p.get('targets') for p in document['meshes'][node['mesh']]['primitives']):
            old_mesh = document['meshes'][node['mesh']]
            document['meshes'].append(copy.deepcopy(old_mesh))
            node['mesh'] = len(document['meshes']) - 1
    rows, part_index = [], 0
    for ni, old_node in enumerate(original_document['nodes']):
        if 'mesh' not in old_node:
            continue
        mesh = document['meshes'][document['nodes'][ni]['mesh']]
        for pi, primitive in enumerate(mesh['primitives']):
            part = asset.parts[part_index]
            part_index += 1
            row = {'node': ni, 'primitive': pi, 'vertices': len(part['position']),
                   'direction_fields': [x.lower() for x in ('NORMAL', 'TANGENT')
                                        if x in primitive['attributes']]}
            if not primitive.get('targets'):
                rows.append({**row, 'status': 'morph_free_untouched'})
                continue
            data = _primitive_data(asset, part, primitive)
            sk = _skin(part, training)
            targets = _target(data, part, training, sk, 'POSITION')
            positions, weights, fallback, fit_report = _fit(
                asset, part, data, sk, targets, height, iterations, fit_skin)
            normal = _fit_directions(sk, weights, _target(data, part, training, sk, 'NORMAL'), data['normal'])
            tangent = _fit_directions(sk, weights, _target(data, part, training, sk, 'TANGENT'), data['tangent'])
            fallback_normal = _fit_directions(sk, data['weights'],
                _target(data, part, training, sk, 'NORMAL'), data['normal'])
            fallback_tangent = _fit_directions(sk, data['weights'],
                _target(data, part, training, sk, 'TANGENT'), data['tangent'])
            if tangent is not None and normal is not None:
                tangent = _unit(tangent - normal * np.sum(tangent * normal, axis=1, keepdims=True))
            attrs = primitive['attributes']
            attrs['POSITION'] = append_array(document, blob, positions, 'VEC3')
            if normal is not None:
                attrs['NORMAL'] = append_array(document, blob, normal, 'VEC3')
            if tangent is not None:
                attrs['TANGENT'] = append_array(document, blob, np.c_[tangent, data['tangent'][:, 3]], 'VEC4')
            if fit_skin and 'joints' in part:
                joints, packed = _pack_skin(document, blob, attrs, weights, fit_report['influence_budget'])
                weights[:] = 0
                for slot in range(joints.shape[1]):
                    np.add.at(weights, (np.arange(len(weights)), joints[:, slot]), packed[:, slot])
            # Evaluate the actual float32 arrays written, not optimizer doubles.
            positions = positions.astype('f4').astype(float)
            normal = None if normal is None else normal.astype('f4').astype(float)
            tangent = None if tangent is None else tangent.astype('f4').astype(float)
            test_skin = _skin(part, validation)
            row.update(status='approximate_fixed_fit_not_installed', removed_targets=len(primitive['targets']),
                       fit=fit_report, training=_evaluate(data, part, training, sk, positions, weights,
                                                        normal, tangent, height),
                       independent=_evaluate(data, part, validation, test_skin, positions, weights,
                                             normal, tangent, height),
                       original_skin_fallback=_evaluate(data, part, validation, test_skin,
                           fallback.astype('f4').astype(float), data['weights'],
                           None if fallback_normal is None else fallback_normal.astype('f4').astype(float),
                           None if fallback_tangent is None else fallback_tangent.astype('f4').astype(float), height),
                       maximum_rest_position_change=float(np.linalg.norm(positions - data['base'], axis=1).max()),
                       source_weight_sum_maximum_error=float(np.abs(data['weights'].sum(1) - 1).max()),
                       fitted_weight_sum_maximum_error=float(np.abs(weights.sum(1) - 1).max()),
                       maximum_positive_influences=int((weights > 0).sum(1).max()))
            primitive.pop('targets', None)
            rows.append(row)
        if any(r['node'] == ni and r['status'] != 'morph_free_untouched' for r in rows):
            mesh.pop('weights', None)
            mesh.get('extras', {}).pop('targetNames', None)
            document['nodes'][ni].pop('weights', None)
            # Raw ArrayMesh AABB includes every morph endpoint, even inactive
            # ones. Using base-only bounds would move normalization/grounding.
            mesh.setdefault('extras', {}).setdefault('rabbitlands_actor_bounds_v1', {
                **_original_mesh_bounds(original_document, binary,
                                        original_document['meshes'][old_node['mesh']])})
    # Every corrective mesh has a fitted clone. Remove unused originals too.
    used = sorted({n['mesh'] for n in document['nodes'] if 'mesh' in n})
    remap = {old: new for new, old in enumerate(used)}
    document['meshes'] = [document['meshes'][m] for m in used]
    for node in document['nodes']:
        if 'mesh' in node:
            node['mesh'] = remap[node['mesh']]
    for animation in document.get('animations', []):
        channels = [c for c in animation['channels'] if c['target']['path'] != 'weights']
        used = sorted({c['sampler'] for c in channels})
        remap = {old: new for new, old in enumerate(used)}
        for channel in channels:
            channel['sampler'] = remap[channel['sampler']]
        animation['channels'] = channels
        animation['samplers'] = [animation['samplers'][i] for i in used]
    # Disable even exact constant-TRS collapse: preserve original key arrays.
    document, binary, packing = compact(document, blob, collapse_paths=())
    write_glb(output, document, binary)
    preserved = _preservation(asset, output)
    if digest(source) != source_hash:
        raise RuntimeError('Source changed during fitting; candidate is unqualified')
    result = {'schema': 1, 'status': 'approximate_candidate_requires_engine_and_visual_QA',
              'implementation_sha256': digest(Path(__file__)),
              'artifact': str(output), 'sha256': digest(output), 'raw_bytes': output.stat().st_size,
              'source': str(source), 'source_sha256': source_hash, 'source_raw_bytes': source.stat().st_size,
              'source_preserved': True, 'corrective_targets': 0, 'helper_bones_added': 0,
              'height': height, 'height_basis': 'original neutral native world Y extent',
              'sampling': source_sampling, 'training_poses': len(training['labels']),
              'independent_poses': len(validation['labels']),
              'independent_labels': validation['labels'], 'primitive_reports': rows,
              'whole_surface': {
                  'training': _summary(rows, len(training['labels']), height, 'training'),
                  'independent': _summary(rows, len(validation['labels']), height, 'independent'),
                  'neutral': _summary(rows, 1, height, 'independent', 'neutral'),
                  'off_grid': _summary(rows, int(sum(validation['categories'] == 'off_grid')),
                                       height, 'independent', 'off_grid'),
                  'original_skin_fallback': _summary(rows, len(validation['labels']), height,
                                                      'original_skin_fallback')},
              'preserved_arrays': preserved, 'packing': packing,
              'evaluator_scope': 'float64 native TRS/relative morph conventions, float32 fitted arrays; '
                  'all raw morph weights included; no GPU weight/vertex quantization or engine import',
              'actual_engine_validated': False, 'acceptance_threshold_assumed': None,
              'limitations': ['Approximate fit; no lossless claim or automatic acceptance.',
                  'No helper bones; support restricted to hierarchy neighbors and three nearest rest segments; '
                  'crowded/crossing anatomy still needs individual review.',
                  'Crossfades are offline local-TRS blends, not an actual engine AnimationMixer.',
                  'Actor/dissolve/silhouette/reference-skin behavior requires separate runtime QA.',
                  'Normal-mapped materials require rendered tangent/normal inspection.']}
    if 'crossfade' in validation['categories']:
        result['whole_surface']['crossfade'] = _summary(rows,
            int(sum(validation['categories'] == 'crossfade')), height, 'independent', 'crossfade')
    if 'step_boundary' in validation['categories']:
        result['whole_surface']['step_boundary'] = _summary(rows,
            int(sum(validation['categories'] == 'step_boundary')), height, 'independent', 'step_boundary')
    if report is not None:
        report = Path(report)
        report.parent.mkdir(parents=True, exist_ok=True)
        report.write_text(json.dumps(result, indent=2) + '\n', encoding='utf-8')
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('source', type=Path)
    parser.add_argument('output', type=Path)
    parser.add_argument('--iterations', type=int, default=6)
    parser.add_argument('--report', type=Path)
    parser.add_argument('--original-skin', action='store_true')
    parser.add_argument('--allow-step-exceptions', action='store_true',
                        help='Retain/report dense original STEP clocks; continuous tracks stay <=30 Hz')
    args = parser.parse_args()
    result = bake(args.source, args.output, iterations=args.iterations,
                  report=args.report, fit_skin=not args.original_skin,
                  allow_step_exceptions=args.allow_step_exceptions)
    print(json.dumps({k: result[k] for k in ('status', 'artifact', 'sha256', 'raw_bytes')}, indent=2))


if __name__ == '__main__':
    main()
