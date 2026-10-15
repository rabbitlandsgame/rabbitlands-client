"""Publish the finished Cinder cartway and clear its four unlinked plants.

This runs after all land, road and water shaping. Only the named whole plant
assemblies move; actual terrain triangles and every semantic post stay fixed.
"""
import numpy as np
from amberwood import mesh as M
from verify_runtime import VerticalRayIndex

ROAD = 'amberwood-mirrorhold'
MOVES = {
    'Undergrowth_0310': (253.6867, 14.197),
    'March_east_road_tree_000': (265.2325, 15.4614),
    'March_east_road_tree_002': (261.1115, 14.342),
    'Tree_0857_dark_pine_Wood': (220.332, 34.2278),
}


def export(build):
    """Serialize actual final bed stations, rather than pre-finish survey Y."""
    road = next(r for r in build.geography_roads if r['id'] == ROAD)
    frame = next(r for r in build.streaming_borders if r['id'] == ROAD)
    points = np.asarray(road['stations'], dtype=float)
    if points.ndim != 2 or points.shape[1] != 3 or len(points) < 2 or not np.isfinite(points).all():
        raise ValueError('Cinder cartway needs finite final XYZ stations')
    anchor = np.asarray(frame['anchor'], dtype=float)
    if np.linalg.norm(points[-1, [0, 2]]-anchor[[0, 2]]) > 1e-6:
        raise ValueError('Cinder cartway final station no longer meets its published seam')
    landing = anchor[[0, 2]] - np.asarray(frame['outward'])*42.
    start = int(np.argmin(np.linalg.norm(points[:, [0, 2]]-landing, axis=1)))
    if start >= len(points)-1:
        raise ValueError('Cinder cartway has no authored inland collar')
    frame['approachCenterline'] = {
        'schemaVersion': 1,
        'stationHeight': 'bed', 'walkingBias': .03,
        'stations': points.tolist(), 'collarStartIndex': start,
        'laneHalfWidth': 3., 'physicalHalfWidth': 4.25,
        'commonBoundaryLength': 3.,
        'direction': 'inland-to-seam',
        'reason': road['contactNote'],
    }


def clear_dressing(build):
    triangles = [m.positions[m.indices.reshape(-1, 3)]
                  for name, m in build.terrain_meshes.items()
                  if name.startswith('Terrain_') and m.triangle_count
                  and not any(p in name for p in ('StreamCollar', 'ContinentBlend', 'OuterEscarpment'))]
    ground = VerticalRayIndex(np.concatenate(triangles))
    corrections = []
    for name, target in MOVES.items():
        root = next((p for p in build.placements if p.node == name), None)
        # Ground-detail plants can be intentionally absent from the far tier.
        if root is None:
            continue
        canopy = name[:-5] + '_Canopy' if name.endswith('_Wood') else name + '_Canopy'
        assembly = [p for p in build.placements if p.node in (name, canopy)]
        references = [r for field in ('landmarks', 'interactives', 'npc_markers', 'harvestables', 'portals')
                      for r in getattr(build, field, [])
                      if any(p.node in str(r) for p in assembly)]
        if references or any(p.landmark for p in assembly):
            raise ValueError('Roadside dressing acquired a semantic/resource reference: '+name)
        local = build.meshes[root.mesh].positions * root.scale @ M.rotation_y(root.rotation_y)[:3, :3].T
        index = int(np.argmin(local[:, 1]))
        contact = np.asarray(target) + local[index, [0, 2]]
        height = ground.top_hit(*contact)
        if height is None:
            raise ValueError('Roadside plant has no actual final substrate: '+name)
        new = np.array([target[0], height-local[index, 1]-.02, target[1]])
        delta = new-np.asarray(root.position)
        for p in assembly:
            before = list(p.position)
            p.position = tuple(np.asarray(p.position)+delta)
            corrections.append({'node': p.node, 'before': before, 'after': list(p.position),
                                'rootContactXZ': contact.tolist(), 'rootGroundY': float(height),
                                'rootSink': .02})
    build.amber_approach_dressing = corrections


def apply(build):
    clear_dressing(build)
    export(build)
