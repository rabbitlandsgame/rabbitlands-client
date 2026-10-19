"""Independent full-skin contact/strain checks for an undead gait candidate."""
import argparse
import json
from pathlib import Path

import numpy as np

from video_motion.asset import accessor, digest
from video_motion.native_shapes import NativeShapeAsset


def evaluate(path, fit=None):
    actor = NativeShapeAsset(path)
    fit_path = Path(path).with_suffix('.fit.json')
    if fit is None and fit_path.exists(): fit = json.loads(fit_path.read_text())
    height = float(np.ptp(actor.vertices[:, 1]))
    feet = {}
    quadruped = 'leg_b_l_01' in actor.ids
    legs = [('fore_left','a','l'),('fore_right','a','r'),('hind_left','b','l'),('hind_right','b','r')] if quadruped else [('left','a','l'),('right','a','r')]
    foot_nodes = fit.get('footNodes') if fit else None
    if foot_nodes:
        legs = [(side,None,None) for side in foot_nodes]
    for side, group, suffix in legs:
        owner = actor.own(foot_nodes[side] if foot_nodes else [actor.ids[f'leg_{group}_{suffix}_03']])
        owned = np.flatnonzero(owner > .8)
        low = actor.vertices[owned, 1].min()
        feet[side] = (owned, owned[actor.vertices[owned, 1] < low+.012*height])
    edge_parts, offset = [], 0
    for node in actor.d['nodes']:
        if 'mesh' not in node:
            continue
        for primitive in actor.d['meshes'][node['mesh']]['primitives']:
            count = actor.d['accessors'][primitive['attributes']['POSITION']]['count']
            indices = accessor(actor.d, actor.b, primitive['indices']).astype(int).reshape(-1, 3)
            edges = np.concatenate([indices[:, [0, 1]], indices[:, [1, 2]], indices[:, [2, 0]]])+offset
            edge_parts.append(edges)
            offset += count
    edges = np.unique(np.sort(np.concatenate(edge_parts), axis=1), axis=0)
    rest_lengths = np.linalg.norm(np.diff(actor.vertices[edges], axis=1)[:, 0], axis=1)
    edges = edges[rest_lengths > height*1e-5]
    rest_lengths = rest_lengths[rest_lengths > height*1e-5]
    result = {'sha256': digest(path), 'height': height, 'clips': {}}
    for clip in ('Walk', 'Jog'):
        duration = actor.duration(clip)
        samples = max(768, round(duration*768))
        times = np.linspace(0, duration, samples+1)
        translations, rotations, scales, shapes = actor.sample(clip, times)
        centres = {side: [] for side in feet}
        sole_floor = {side: [] for side in feet}
        all_floor, stretches, excess, substantial_stretches = [], [], [], []
        for index, t in enumerate(times):
            world = actor.world(translations[index], rotations[index], scales[index])
            vertices = actor.skin(world, {n: w[index] for n, w in shapes.items()})
            all_floor.append(float(vertices[:, 1].min()))
            for side, (owned, sole) in feet.items():
                centres[side].append(vertices[sole].mean(0))
                sole_floor[side].append(vertices[owned, 1].min())
            if index % 24 == 0:
                lengths = np.linalg.norm(np.diff(vertices[edges], axis=1)[:, 0], axis=1)
                stretches.extend((lengths/rest_lengths).tolist())
                excess.extend(np.maximum(0,lengths-rest_lengths).tolist())
                substantial_stretches.extend((lengths/rest_lengths)[rest_lengths > height*.01].tolist())
        metrics = {'fullSkinFloorMin': min(all_floor), 'edgeStretchP99': float(np.percentile(stretches, 99)),
                   'edgeStretchMax': max(stretches), 'edgeExcessMax': max(excess),
                   'substantialEdgeStretchMax': max(substantial_stretches), 'feet': {}}
        stance = fit['clips'][clip].get('stanceFraction',.64 if clip == 'Walk' else .44) if fit else (.64 if clip == 'Walk' else .44)
        speed = fit['clips'][clip]['speedNative'] if fit else 0
        for side in feet:
            centres[side] = np.array(centres[side])
            offsets = fit['clips'][clip].get('phaseOffsets') if fit else None
            offset = offsets[side] if offsets else (0 if side == 'left' else .5)
            phases = (times/duration-offset) % 1
            contact = (phases > .01) & (phases < stance-.01)
            velocity = np.gradient(centres[side], times, axis=0)
            velocity[:, 2] += speed
            metrics['feet'][side] = {'stanceSlipP95': float(np.percentile(np.linalg.norm(velocity[contact], axis=1), 95)),
                                    'stanceFloorMin': float(np.min(np.array(sole_floor[side])[contact])),
                                    'stanceFloorMax': float(np.max(np.array(sole_floor[side])[contact]))}
        result['clips'][clip] = metrics
    return result


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('model')
    parser.add_argument('--output', required=True)
    args = parser.parse_args()
    report = evaluate(args.model)
    Path(args.output).write_text(json.dumps(report, indent=2)+'\n')
    print(json.dumps(report, indent=2))
