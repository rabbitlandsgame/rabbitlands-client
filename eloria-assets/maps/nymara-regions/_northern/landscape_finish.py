"""Finish the three northern passes without flattening their terrain paint.

Paint is sampled from the finished substrate, not independently clamped to a
valley ceiling. This also restores offsets compressed by overlapping border
grades. The masks, material recipes and texture coordinates remain authored.
"""
from collections import defaultdict
import re

import numpy as np

import northern_passes
from verify_runtime import VerticalRayIndex
from road_profiles import refresh, seat_ground, add_supports, refine_bed


def substrate_name(name):
    return re.split(r'_StreamCollar_|_ContinentBlend_|_StreamCell_', name)[0]


def collar_layers(name):
    return re.findall(r'_StreamCollar_(.*?)_(Turf|Frost|Road)(?=_|$)', name)


def paint_bias(name, slots, peers=()):
    collars = collar_layers(name)
    if collars:
        # Nested copies have already been removed. Later border recipes take
        # precedence at intersections, all below the 3cm physical road deck.
        ranks = {'Turf': 1, 'Frost': 2, 'Road': 3}
        connection, kind = collars[-1]
        return .002 * (3 * slots[connection] + ranks[kind])
    blend = re.search(r'_ContinentBlend_(.*)_([01])$', name)
    if blend:
        return .020 + .001 * (2 * list(peers).index(blend.group(1)) + int(blend.group(2)))
    return 0.


def _keys(xz):
    # Shared clipping can evaluate the same edge in opposite directions.
    values = np.ascontiguousarray(np.rint(xz * 1e7).astype(np.int64))
    return values.view(np.dtype([('x', '<i8'), ('z', '<i8')])).ravel()


class Substrate:
    """Exact shared vertices first; real triangle interpolation for new cuts."""
    def __init__(self, meshes):
        self.meshes = meshes
        points = np.concatenate([m.positions for m in meshes])
        keys = _keys(points[:, [0, 2]])
        self.keys, inverse = np.unique(keys, return_inverse=True)
        self.heights = np.full(len(self.keys), -np.inf)
        np.maximum.at(self.heights, inverse, points[:, 1])
        self.rays = None

    def sample(self, xz):
        keys = _keys(xz)
        at = np.searchsorted(self.keys, keys)
        safe = np.minimum(at, len(self.keys)-1)
        found = (at < len(self.keys)) & (self.keys[safe] == keys)
        result = self.heights[safe].copy()
        if not found.all():
            if self.rays is None:
                triangles = np.concatenate([
                    m.positions[m.indices].reshape(-1, 3, 3) for m in self.meshes])
                self.rays = VerticalRayIndex(triangles)
            missing = np.flatnonzero(~found)
            unique, inverse = np.unique(xz[missing], axis=0, return_inverse=True)
            samples = []
            for x, z in unique:
                height = self.rays.top_hit(float(x), float(z))
                if height is None:
                    raise ValueError(f'Northern terrain paint has no substrate at {x}, {z}')
                samples.append(height)
            result[missing] = np.asarray(samples)[inverse]
        return result


def apply(build, region):
    import continent_geography as G
    refresh(build, region)
    paint = {name: mesh for name, mesh in build.terrain_meshes.items()
             if name.startswith('Terrain_') and ('_StreamCollar_' in name or '_ContinentBlend_' in name)}
    painted_roads = {identity for name in paint for identity, _ in collar_layers(name)}
    order = [spec['id'] for spec in build.streaming_borders if spec['id'] in painted_roads]
    slots = {identity: index for index, identity in enumerate(order)}
    peers = sorted({peer for edge in G.boundary_segments(region) for peer in edge['regions'] if peer != region})
    if len(slots) > 3 or len(peers) > 5:
        raise ValueError('Northern terrain paint needs a revised bounded layer allocation')
    for name in paint:
        del build.terrain_meshes[name]
    northern_passes.apply(build, region)
    seat_ground(build, region)
    add_supports(build, region)
    bases = defaultdict(list)
    for name, mesh in build.terrain_meshes.items():
        if name.startswith('Terrain_') and mesh.triangle_count:
            bases[substrate_name(name)].append(mesh)
    samplers = {}
    dropped = set()
    selected_roads = [road for road in getattr(build, 'geography_roads', [])
                      if road['id'] in northern_passes.ROADS.get(region, set())]
    for name, mesh in paint.items():
        # A->B repeats B's material with additional A coverage restrictions.
        # Direct B already covers that subset using the same substrate alpha.
        if len(collar_layers(name)) > 1:
            dropped.add(name)
            continue
        root = substrate_name(name)
        if root not in samplers:
            if root not in bases:
                raise ValueError(f'Northern terrain paint lost its substrate: {name}')
            samplers[root] = Substrate(bases[root])
        if selected_roads:
            refine_bed(mesh, selected_roads)
        mesh.positions[:, 1] = samplers[root].sample(mesh.positions[:, [0, 2]]) + paint_bias(name, slots, peers)
        mesh.recompute_normals(180)
        build.terrain_meshes[name] = mesh
    for spec in build.streaming_borders:
        if 'sceneNodes' in spec:
            spec['sceneNodes'] = [name for name in spec['sceneNodes'] if name not in dropped]
    build.notes.append('Northern surface finish: paint follows the actual shaped substrate with distinct layer offsets; valley grades use the finished road decks.')
