"""Finish Amethyst's new southern approach and its northern public-road merge.

These are regional corrections to generated roads. Native architecture and
the exact three-metre common-boundary contours remain unchanged.
"""
from collections import defaultdict
import numpy as np

REGION = 'amethyst_barrens'
ROAD = 'amethyst-sunmane'


def _smooth(value):
    value = np.clip(value, 0., 1.)
    return value * value * (3. - 2. * value)


def _merge_weight(xz):
    # Cover the actual White deck edge that meets the flat Mirror carriageway,
    # with room to blend back into the White approach on every side.
    distance = np.linalg.norm(np.maximum(np.maximum(
        np.array([-114., -230.5]) - xz,
        xz - np.array([-109., -226.5])), 0.), axis=1)
    return 1. - _smooth(distance / 4.)


def apply(build):
    import continent_geography as G
    from northern_passes import _footprints
    from road_profiles import _corridor, _stations, _edge_distance, refine_bed
    from landscape_finish import Substrate, substrate_name, paint_bias, collar_layers
    from verify_runtime import VerticalRayIndex

    road = next(r for r in build.geography_roads if r['id'] == ROAD)
    meshes = [m for n, m in build.terrain_meshes.items()
              if n.startswith('Walk_ContinentRoad_' + ROAD)]
    # A modest, readable bend replaces the disconnected zigzag quad ends.
    points, distance = _stations([[54.5, 19., 71.5], [48.5, 18.7, 73.5],
                                 [42.5, 18.15, 78.], [40.5, 18., 80.5],
                                 [40.5, 18., 122.5]])
    _corridor(build, REGION, meshes, points, distance)
    ray = VerticalRayIndex(meshes[0].positions[meshes[0].indices.reshape(-1, 3)])
    for p in points:
        height = ray.top_hit(p[0], p[2])
        if height is not None:
            p[1] = height - .03
    road['stations'] = points.tolist()
    road['length'] = float(distance[-1])
    road['maximumGrade'] = float(np.max(np.abs(np.diff(points[:, 1])) / np.diff(distance)))
    lengths = distance / distance[-1]
    footprints = _footprints(build)

    def protection(xz):
        weight = _smooth((_edge_distance(build, REGION, xz) - 3.) / 3.)
        for low, high in footprints:
            d = np.linalg.norm(np.maximum(np.maximum(low - xz, xz - high), 0.), axis=1)
            weight *= _smooth(d / 1.5)
        return weight

    def shape(vertices):
        result = vertices.copy()
        xz = vertices[:, [0, 2]]
        across, along = G._road_coordinates(xz, points[:, [0, 2]])
        protect = protection(xz)
        weight = (1. - _smooth((across - 5.5) / 5.)) * protect
        for i in np.flatnonzero(weight > 1e-8):
            center = np.array([np.interp(along[i], lengths, points[:, 0]),
                               np.interp(along[i], lengths, points[:, 2])])
            vector = xz[i] - center
            query = center + vector * min(1., 3.75 / max(across[i], 1e-9))
            height = ray.top_hit(*query)
            if height is None:
                height = ray.top_hit(*center)
            if height is not None:
                target = height - .03 - .035 * max(across[i] - 4.25, 0.) ** 2
                result[i, 1] += (target - result[i, 1]) * weight[i]
        merge = _merge_weight(xz) * protect
        result[:, 1] += (24.05 - result[:, 1]) * merge
        return result

    # The shared Mirror carriageway is already level. Blend only the generated
    # White deck into it, leaving the actual native Walk meshes intact.
    for name, mesh in build.terrain_meshes.items():
        if name.startswith('Walk_ContinentRoad_whitehorn-amethyst'):
            refine_bed(mesh, [{'stations': [[-114.,24.05,-228.5],[-109.,24.05,-228.5]]}])
            weight = _merge_weight(mesh.positions[:, [0, 2]]) * protection(mesh.positions[:, [0, 2]])
            mesh.positions[:, 1] += (24.08 - mesh.positions[:, 1]) * weight
            mesh.recompute_normals(180)

    paint = {n: m for n, m in build.terrain_meshes.items()
             if n.startswith('Terrain_') and ('_StreamCollar_' in n or '_ContinentBlend_' in n)}
    refinement_roads = [road, {'stations': [[-114., 24.05, -228.5], [-109., 24.05, -228.5]]}]
    G._lift_unprotected_scatter(build, shape)
    bases = defaultdict(list)
    for name, mesh in build.terrain_meshes.items():
        if not name.startswith('Terrain_') or name in paint:
            continue
        refine_bed(mesh, refinement_roads)
        mesh.positions = shape(mesh.positions)
        mesh.recompute_normals(180)
        bases[substrate_name(name)].append(mesh)
    painted = {identity for name in paint for identity, _ in collar_layers(name)}
    slots = {s['id']: i for i, s in enumerate(s for s in build.streaming_borders if s['id'] in painted)}
    peers = sorted({p for e in G.boundary_segments(REGION) for p in e['regions'] if p != REGION})
    samplers = {}
    for name, mesh in paint.items():
        refine_bed(mesh, refinement_roads)
        xz = mesh.positions[:, [0, 2]]
        across, _ = G._road_coordinates(xz, points[:, [0, 2]])
        affected = ((across < 10.5) | (_merge_weight(xz) > 0.)) & (protection(xz) > 0.)
        if not affected.any():
            continue
        root = substrate_name(name)
        if root not in samplers:
            samplers[root] = Substrate(bases[root])
        mesh.positions[affected, 1] = samplers[root].sample(xz[affected]) + paint_bias(name, slots, peers)
        mesh.recompute_normals(180)
    terrain = build.terrain
    vertices = np.c_[terrain.gx.ravel(), terrain.height.ravel(), terrain.gz.ravel()]
    terrain.height = shape(vertices)[:, 1].reshape(terrain.height.shape)
    white = next(r for r in build.geography_roads if r['id'] == 'whitehorn-amethyst')
    white_ray = VerticalRayIndex(np.concatenate([m.positions[m.indices.reshape(-1, 3)]
        for n, m in build.terrain_meshes.items() if n.startswith('Walk_ContinentRoad_whitehorn-amethyst')]))
    for p in white['stations']:
        height = white_ray.top_hit(p[0], p[2])
        if height is not None:
            p[1] = height - .03
    build.notes.append('Amethyst southern connector: continuous bend with a supported graded bed; White/Mirror deck merge blended to the shared carriageway. Native structures and common boundaries retained.')
