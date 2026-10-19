"""Fit in-place foot contacts on the current imported undead rigs.

Keeps the source rest, skin, textures and non-locomotion clips. Upper-body
motion and corrective shapes retain the original gait's phase. New local
leg curves solve against physical foot surfaces, not named ankle heights.
Outputs are candidates until contact, deformation and engine review pass.
"""
from __future__ import annotations

import argparse
import copy
import json
from pathlib import Path

import numpy as np
from scipy.spatial.transform import Rotation

from video_motion.asset import digest, write_glb
from video_motion.native_shapes import NativeShapeAsset
from video_motion.packing import append_array

STRIDES = {'Walk': .40, 'Jog': .65}


def unit(v):
    return v/max(np.linalg.norm(v), 1e-12)


def align(a, b):
    a, b = unit(a), unit(b)
    cross = np.cross(a, b)
    cosine = np.clip(a@b, -1, 1)
    if np.linalg.norm(cross) < 1e-10:
        if cosine > 0:
            return np.eye(3)
        cross = np.cross(a, [1, 0, 0] if abs(a[0]) < .9 else [0, 1, 0])
    return Rotation.from_rotvec(unit(cross)*np.arccos(cosine)).as_matrix()


class GaitFit:
    def __init__(self, source):
        self.a = a = NativeShapeAsset(source)
        self.height = float(np.ptp(a.vertices[:, 1]))
        self.floor = float(a.vertices[:, 1].min()) + .001*self.height
        self.chains, self.soles, self.paws, self.centres = {}, {}, {}, {}
        self.quadruped = 'leg_b_l_01' in a.ids
        self.strides = {'Walk':.30,'Jog':.50} if self.quadruped else STRIDES
        legs = [('fore_left','a','l'),('fore_right','a','r'),('hind_left','b','l'),('hind_right','b','r')] if self.quadruped else [('left','a','l'),('right','a','r')]
        for side, group, suffix in legs:
            chain = [a.ids[f'leg_{group}_{suffix}_{index:02}'] for index in (1, 2, 3)]
            self.chains[side] = chain
            owner = a.own([chain[-1]])
            ids = np.flatnonzero(owner > .8)
            if len(ids) < 6:
                raise ValueError(f'{side}: foot needs an explicit skin preparation')
            bottom = a.vertices[ids, 1].min()
            sole = ids[a.vertices[ids, 1] < bottom + .012*self.height]
            if len(sole) < 3:
                raise ValueError(f'{side}: no complete sole patch')
            self.soles[side] = sole
            self.paws[side] = ids
            self.centres[side] = a.vertices[sole].mean(0)

    def solve_leg(self, world, side, centre, foot_rotation):
        a = self.a
        hip, knee, foot = self.chains[side]
        origin = world[hip, :3, 3].copy()
        ankle = centre - foot_rotation@(self.centres[side]-a.rest[foot, :3, 3])
        delta = ankle-origin
        length = np.linalg.norm(delta)
        lengths = np.linalg.norm(np.diff(a.rest[[hip, knee, foot], :3, 3], axis=0), axis=1)
        radius = float(np.clip(length, abs(lengths[0]-lengths[1])+1e-5,
                               sum(lengths)-1e-5))
        direction = unit(delta)
        if self.quadruped:
            # These short stylized chains carry their bend in the prepared
            # rest. Preserve that anatomical plane instead of assigning a
            # human knee or an assumed canine elbow by the bone's label.
            rest_axis = unit(a.rest[foot,:3,3]-a.rest[hip,:3,3])
            rest_knee = a.rest[knee,:3,3]-a.rest[hip,:3,3]
            pole = rest_knee-rest_axis*(rest_knee@rest_axis)
        else:
            pole = np.array([0.,0.,1.])
        pole = unit(pole-direction*(pole@direction))
        along = (lengths[0]**2-lengths[1]**2+radius**2)/(2*radius)
        middle = origin+direction*along+pole*np.sqrt(max(0, lengths[0]**2-along**2))
        ankle = origin+direction*radius
        for node, start, end, child in [(hip, origin, middle, knee), (knee, middle, ankle, foot)]:
            rotation = align(a.rest[child, :3, 3]-a.rest[node, :3, 3], end-start)
            world[node, :3, :3] = rotation@a.rest[node, :3, :3]
            world[node, :3, 3] = start
        world[foot, :3, :3] = foot_rotation@a.rest[foot, :3, :3]
        world[foot, :3, 3] = ankle
        return abs(length-radius)

    def pose(self, clip, time, duration):
        a = self.a
        phase = (time/duration) % 1
        translations, rotations, scales, shapes = a.sample(clip, [phase*a.duration(clip)])
        translations[0, a.ids['hips'], 1] -= .015*self.height
        world = a.world(translations[0], rotations[0], scales[0])
        weights = {n: w[0] for n, w in shapes.items()}
        stance = .64 if clip == 'Walk' else .44
        stride = self.strides[clip]*self.height
        goals, foot_rotations, contacts = {}, {}, {}
        offsets = self.phase_offsets(clip)
        for side in self.chains:
            p = (phase-offsets[side]) % 1
            goal = self.centres[side].copy()
            if self.quadruped:
                hip,_,ankle = self.chains[side]
                # The static modelling pose has every paw ahead of its hip.
                # Centre the travel sweep under the support joint, keeping
                # its lateral stance and physical sole/ankle offset intact.
                goal[2] += .25*(a.rest[hip,2,3]-a.rest[ankle,2,3])
            goal[1] += self.floor-float(a.vertices[self.soles[side], 1].min())
            foot_rotation = np.eye(3)
            if p <= stance:
                goal[2] += stride*(stance/2-p)
                contacts[side] = True
            else:
                u = (p-stance)/(1-stance)
                smooth = u**3*(10+u*(-15+6*u))
                goal[2] += stride*(-stance/2-(1-stance)*u+smooth)
                lift = (.05 if clip == 'Walk' else .08) if self.quadruped else (.09 if clip == 'Walk' else .13)
                goal[1] += lift*self.height*np.sin(np.pi*u)**2
                foot_rotation = Rotation.from_euler('x', 8*np.sin(np.pi*u)**2, degrees=True).as_matrix()
                contacts[side] = False
            goals[side], foot_rotations[side] = goal, foot_rotation
        adjusted = {side: goal.copy() for side, goal in goals.items()}
        reach = 0.
        for unused in range(8):
            for side in self.chains:
                reach = max(reach, self.solve_leg(world, side, adjusted[side], foot_rotations[side]))
            vertices = a.skin(world, weights)
            error = 0.
            for side in self.chains:
                correction = goals[side]-vertices[self.soles[side]].mean(0)
                adjusted[side] += correction
                error = max(error, np.linalg.norm(correction))
                if not contacts[side]:
                    lift = max(0, self.floor-vertices[self.paws[side], 1].min())
                    adjusted[side][1] += lift
                    goals[side][1] += lift
                    error = max(error, lift)
            if error < 1e-7:
                break
        for side, chain in self.chains.items():
            for node in chain:
                parent = int(a.parent[node])
                local = np.linalg.solve(world[parent], world[node])
                translations[0, node] = local[:3, 3]
                rotations[0, node] = Rotation.from_matrix(local[:3, :3]/scales[0, node][None, :]).as_quat()
        return translations[0], rotations[0], scales[0], weights, reach

    def phase_offsets(self, clip):
        if not self.quadruped: return {'left':0.,'right':.5}
        if clip == 'Walk': return {'fore_left':0.,'hind_right':.25,'fore_right':.5,'hind_left':.75}
        return {'fore_left':0.,'hind_right':0.,'fore_right':.5,'hind_left':.5}

    def build(self, output, rate):
        output.parent.mkdir(parents=True, exist_ok=True)
        a = self.a
        document, blob = copy.deepcopy(a.d), bytearray(a.b)
        report = {'sourceSha256': digest(a.path), 'geometryAndRestPreserved': True, 'clips': {},
                  'bodyPlan':'quadruped' if self.quadruped else 'biped',
                  'chains':self.chains,'soleVertices':{k:v.tolist() for k,v in self.soles.items()}}
        durations = [('Walk',a.duration('Walk')),('Jog',a.duration('Jog'))] if self.quadruped else [('Walk',1.12),('Jog',.72)]
        for clip, duration in durations:
            times = np.linspace(0, duration, round(duration*rate)+1).astype('float32')
            frames = [self.pose(clip, float(t), duration) for t in times[:-1]]
            frames.append(frames[0])
            t, q, s = [np.array([f[i] for f in frames]) for i in range(3)]
            time_accessor = append_array(document, blob, times[:, None], 'SCALAR')
            animation = {'name': clip, 'channels': [], 'samplers': []}
            def channel(node, kind, values, value_type):
                output_accessor = append_array(document, blob, values, value_type)
                animation['channels'].append({'sampler': len(animation['samplers']),
                                               'target': {'node': int(node), 'path': kind}})
                animation['samplers'].append({'input': time_accessor, 'output': output_accessor,
                                               'interpolation': 'LINEAR'})
            for node in a.joints:
                channel(node, 'translation', t[:, node], 'VEC3')
                quaternions = q[:, node].copy()
                for i in range(1, len(quaternions)):
                    if quaternions[i]@quaternions[i-1] < 0:
                        quaternions[i] *= -1
                channel(node, 'rotation', quaternions, 'VEC4')
                channel(node, 'scale', s[:, node], 'VEC3')
            for node, defaults in a.default_weights.items():
                if len(defaults):
                    values = np.array([f[3][node] for f in frames]).reshape(-1, 1)
                    channel(node, 'weights', values, 'SCALAR')
            document['animations'] = [old for old in document['animations'] if old['name'] != clip]+[animation]
            report['clips'][clip] = {'duration': duration, 'frames': len(times),
                                     'strideNative': self.strides[clip]*self.height,
                                     'speedNative': self.strides[clip]*self.height/duration,
                                     'phaseOffsets':self.phase_offsets(clip),'stanceFraction':.64 if clip == 'Walk' else .44,
                                     'maxReachClamp': max(f[4] for f in frames)}
            print(clip, report['clips'][clip], flush=True)
        document['asset'].setdefault('extras', {})['rabbitlands_animation_bake_fps'] = rate
        write_glb(output, document, blob)
        candidate = NativeShapeAsset(output)
        assert candidate.b[:len(a.b)] == a.b
        for key in ('meshes', 'nodes', 'skins', 'materials', 'images'):
            assert candidate.d[key] == a.d[key], key
        for clip in a.animations:
            if clip not in ('Walk', 'Jog'):
                assert candidate.animations[clip] == a.animations[clip]
        report['sha256'] = digest(output)
        output.with_suffix('.fit.json').write_text(json.dumps(report, indent=2)+'\n')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source', required=True)
    parser.add_argument('--output', required=True)
    parser.add_argument('--rate', type=int, default=192)
    args = parser.parse_args()
    GaitFit(args.source).build(Path(args.output), args.rate)
