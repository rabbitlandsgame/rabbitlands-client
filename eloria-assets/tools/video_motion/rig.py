"""Semantic quadruped controls; no dependency on matching raw bone names."""
from __future__ import annotations
import json
from pathlib import Path
import numpy as np
from scipy.spatial.transform import Rotation
from .asset import Asset, digest, rotation_matrix

LEG_NAMES = ('fore_left', 'fore_right', 'hind_left', 'hind_right')


def map_control_intent(source_controls, source_values, target_rig):
    """Map semantic angular intent; native surface IK still defines transfer.

    If the explicitly mapped neck aliases the chest, compose source neck
    pitch on the head. Dropping it would lose its counter-rotation. Height
    remains zero until the caller applies its native proportion adapter.
    """
    source=np.asarray(source_values,float)
    if source.ndim!=2 or source.shape[1]!=len(source_controls)+1:
        raise ValueError('Source control samples require angular columns plus height')
    mapping={role:i for i,role in enumerate(source_controls)}
    target={c['role']:i for i,c in enumerate(target_rig.controls)}
    result=np.zeros((len(source),target_rig.dof))
    for role,i in target.items():
        if role in mapping:result[:,i]=source[:,mapping[role]]
    if ('neck' in mapping and 'neck' not in target and 'head' in target and
            target_rig.roles.get('neck')==target_rig.roles.get('chest')):
        result[:,target['head']]+=source[:,mapping['neck']]
    return result


def auto_profile(asset: Asset):
    roles = {}
    def bind(role, *names, required=True):
        match = next((n for n in names if n in asset.name_to_id), None)
        if match is None and required:
            raise ValueError(f'Map the {role} role explicitly; none of {names} exists')
        if match is not None:
            roles[role] = match
    bind('driver', 'root', 'Root')
    bind('hips', 'Hips', 'hips')
    bind('chest', 'Spine_2001', 'Spine_2')
    bind('neck', 'Spine_3', required=False)
    bind('head', 'Head', 'head')
    bind('tail', 'Tail_Base', required=False)
    for limb in LEG_NAMES:
        prefix = 'Front_Leg' if limb.startswith('fore') else 'Back_Leg'
        side = 'L' if limb.endswith('left') else 'R'
        bind(limb + '_anchor', f'{prefix}_Shoulder_{side}', f'{prefix}_Pelvis_{side}')
        for segment in ('Upper', 'Lower', 'Ankle', 'Foot'):
            bind(limb + '_' + segment.lower(), f'{prefix}_{segment}_{side}', required=segment != 'Ankle')
    profile = {'schema_version': 1, 'category': 'quadruped', 'subcategory': 'canine',
        'source_glb': str(asset.path.resolve()), 'source_sha256': digest(asset.path),
        'up_axis': [0, 1, 0], 'forward_axis': [0, 0, 1], 'depth_axis': [1, 0, 0],
        'roles': roles, 'marker_local': {}, 'controls': [], 'depth_observability': 'unobserved_single_side_view'}
    for limb in LEG_NAMES:
        foot = asset.name_to_id[roles[limb + '_foot']]
        descendants = {foot}
        for i in asset.order:
            if asset.parent[i] in descendants:
                descendants.add(i)
        candidates = []
        offset = 0
        for part in asset.parts:
            if 'joints' in part:
                owned = np.isin(part['nodes'][part['joints']], list(descendants))
                mass = (owned * part['weights']).sum(1)
                candidates.extend((np.flatnonzero(mass > .35) + offset).tolist())
            offset += len(part['position'])
        points = asset.rest_vertices[candidates] if candidates else asset.world_rest[foot, None, :3, 3]
        bottom = points[points[:, 1] <= np.quantile(points[:, 1], .15) + .001 * asset.height]
        marker = np.median(bottom, 0)
        local = np.linalg.inv(asset.world_rest[foot]) @ np.r_[marker, 1]
        profile['marker_local'][limb] = local[:3].tolist()
    def control(role, degrees):
        if role in roles:
            profile['controls'].append({'role': role, 'bounds_degrees': [-degrees, degrees]})
    control('driver', 12)
    control('hips', 12)
    control('chest', 12)
    control('neck', 20)
    control('head', 25)
    control('tail', 30)
    for limb in LEG_NAMES:
        control(limb + '_anchor', 25)
        control(limb + '_upper', 75)
        control(limb + '_lower', 100)
        control(limb + '_ankle', 70)
        control(limb + '_foot', 80)
    return profile


class Rig:
    def __init__(self, asset, profile):
        self.asset, self.profile = asset, profile
        self.roles = {r: asset.name_to_id[n] if isinstance(n, str) else int(n) for r, n in profile['roles'].items()}
        for node in self.roles.values():
            if node not in asset.joints:
                raise ValueError('A mapped bone role is not part of the supplied skin')
        self.controls = profile['controls']
        self.control_nodes = {self.roles[c['role']]: i for i, c in enumerate(self.controls)}
        if len(self.control_nodes) != len(self.controls):
            raise ValueError('Two controls map to the same bone')
        self.axis = np.asarray(profile['depth_axis'], float)
        self.axis /= np.linalg.norm(self.axis)
        self.up = np.asarray(profile['up_axis'], float)
        self.forward = np.asarray(profile['forward_axis'], float)
        self.driver = self.roles['driver']
        height_node=profile.get('body_height_node',self.driver)
        self.height_node=asset.name_to_id[height_node] if isinstance(height_node,str) else int(height_node)
        if self.height_node not in asset.joints:
            raise ValueError('The body height node must be a skin joint')
        ancestor=self.driver
        while ancestor>=0 and ancestor!=self.height_node:ancestor=int(asset.parent[ancestor])
        if ancestor!=self.height_node:raise ValueError('Body height must act at or above the body driver')
        height_bounds = profile.get('body_height_bounds_height', [-.10,.10])
        self.lower = np.r_[np.deg2rad([c['bounds_degrees'][0] for c in self.controls]), height_bounds[0] * asset.height]
        self.upper = np.r_[np.deg2rad([c['bounds_degrees'][1] for c in self.controls]), height_bounds[1] * asset.height]
        self.markers = {}
        for limb in LEG_NAMES:
            if limb + '_foot' not in self.roles or limb not in profile['marker_local']:
                raise ValueError('Every limb requires its own foot role and sole marker')
            chain = [self.roles[limb + '_' + role] for role in ('anchor', 'upper', 'lower', 'foot')]
            for parent, child in zip(chain, chain[1:]):
                current = child
                while current >= 0 and current != parent:
                    current = int(asset.parent[current])
                if current != parent:
                    raise ValueError(f'Invalid {limb} hierarchy')
            self.markers[limb] = (self.roles[limb + '_foot'], np.r_[profile['marker_local'][limb], 1])
        self.rest_markers = self.marker_positions(asset.world_rest)
        self.leg_lengths = {limb: float(np.linalg.norm(asset.world_rest[self.roles[limb + '_upper'], :3, 3] -
                                                    asset.world_rest[self.roles[limb + '_lower'], :3, 3]) +
                                          np.linalg.norm(asset.world_rest[self.roles[limb + '_lower'], :3, 3] -
                                                         self.rest_markers[limb])) for limb in LEG_NAMES}
        self.paw_followers=[]
        for limb in profile.get('paw_follow_helpers',[]):
            helper,foot=self.roles[limb+'_ankle'],self.roles[limb+'_foot']
            if asset.parent[helper]!=asset.parent[foot] or np.any(asset.parent==helper):
                raise ValueError('Paw following is restricted to a leaf helper sharing the foot parent')
            self.paw_followers.append((helper,foot))
        self.scapula_offsets=[]
        for limb in profile.get('scapula_offset_controls',[]):
            anchor,upper=self.roles[limb+'_anchor'],self.roles[limb+'_upper']
            if asset.parent[upper]!=anchor or np.flatnonzero(asset.parent==anchor).tolist()!=[upper]:
                raise ValueError('Scapula offset compensation requires the upper joint to be the anchor\'s only child')
            self.scapula_offsets.append((anchor,upper))
        self.local_rest=np.tile(np.eye(4),(asset.n,1,1))
        self.local_rest[:,:3,:3]=rotation_matrix(asset.q)*asset.s[:,None,:]
        self.local_rest[:,:3,3]=asset.t
        self.follow_rest={foot:np.linalg.inv(asset.world_rest[foot])@asset.world_rest[helper] for helper,foot in self.paw_followers}
        active={self.driver,self.height_node,*self.control_nodes}
        for node in asset.order:
            if asset.parent[node] in active:active.add(node)
        self.active_order=[node for node in asset.order if node in active]

    @property
    def dof(self):
        return len(self.controls) + 1

    def pose(self, parameters, world_only=False):
        a = self.asset
        t, q = a.t.copy(), a.q.copy()
        world = a.world_rest.copy()
        deltas = Rotation.from_rotvec(np.asarray(parameters[:-1])[:, None] * self.axis).as_matrix()
        for node in self.active_order:
            parent = int(a.parent[node])
            parent_world = np.eye(4) if parent < 0 else world[parent]
            if node == self.height_node:
                t[node] += np.linalg.solve(parent_world[:3, :3], self.up * parameters[-1])
            local = self.local_rest[node].copy()
            local[:3, 3] = t[node]
            posed = parent_world @ local
            if node in self.control_nodes:
                delta = deltas[self.control_nodes[node]]
                posed[:3, :3] = delta @ posed[:3, :3]
                if not world_only:
                    local_r = np.linalg.solve(parent_world[:3, :3], posed[:3, :3]) / a.s[node]
                    q[node] = Rotation.from_matrix(local_r).as_quat()
            world[node] = posed
        # Some shoulder weights include chest ornaments and fur that should
        # retain their body-relative orientation. Animate the upper origin on
        # the same native-length arc, then express that pose as local joint
        # translation/rotation under the uncompensated shoulder. Rest/bind data,
        # weights and every anatomical parent distance remain unchanged.
        for anchor,upper in self.scapula_offsets:
            parent=a.parent[anchor]
            parent_world=np.eye(4) if parent<0 else world[parent]
            local=self.local_rest[anchor]
            world[anchor]=parent_world@local
            q[anchor]=a.q[anchor]
            if not world_only:
                upper_local=np.linalg.solve(world[anchor],world[upper])
                t[upper]=upper_local[:3,3]
                q[upper]=Rotation.from_matrix(upper_local[:3,:3]/a.s[upper]).as_quat()
        # A sibling heel helper must carry the same skin transform as the paw.
        # Its parent distance is a deform-control offset, not a limb segment.
        for helper,foot in self.paw_followers:
            desired=world[foot] @ self.follow_rest[foot]
            parent_world=world[a.parent[helper]]
            if not world_only:
                local=np.linalg.solve(parent_world,desired)
                t[helper]=local[:3,3]
                q[helper]=Rotation.from_matrix(local[:3,:3]/a.s[helper]).as_quat()
            world[helper]=desired
        return t, q, world

    def follower_metadata(self):
        return [{'helper':self.asset.names[h],'foot':self.asset.names[f]} for h,f in self.paw_followers]

    def marker_positions(self, world):
        return {limb: (world[node] @ local)[:3] for limb, (node, local) in self.markers.items()}

    def landmarks(self, world):
        result = self.marker_positions(world)
        for role in ('hips', 'chest', 'head', 'tail'):
            if role in self.roles:
                result[role] = world[self.roles[role], :3, 3]
        return result

    def save_profile(self, path):
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        Path(path).write_text(json.dumps(self.profile, indent=2), encoding='utf-8')
