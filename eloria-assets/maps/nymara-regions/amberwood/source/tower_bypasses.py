"""Amberwood's public cart roads pass the towers rather than their footings.

The continent connector finisher consumes contactStations after sampling its
original generated meshes. The fixed marches and their common contour remain
unchanged; these are local requested road beds and one fallen roadside tree.
"""
import numpy as np
from amberwood import mesh as M
from verify_runtime import VerticalRayIndex


def _triangles(meshes):
    return np.concatenate([m.positions[m.indices.reshape(-1, 3)] for m in meshes
                           if m.triangle_count])


def _sampled_road(build, road):
    from road_profiles import _stations
    points, _ = _stations(road['stations'], spacing=.5)
    prefix = 'Walk_ContinentRoad_' + road['id']
    ray = VerticalRayIndex(_triangles([m for n, m in build.terrain_meshes.items()
                                      if n.startswith(prefix)]))
    for point in points:
        height = ray.top_hit(*point[[0, 2]])
        if height is not None:
            point[1] = height - .03
    return points


def _smooth(value):
    value = np.clip(value, 0., 1.)
    return value * value * (3. - 2. * value)


def _mirror_road(build, road):
    points = _sampled_road(build, road)
    # Four and a half metres north around the Cinder Tower's actual stone
    # body, with full shoulders. Finish the bend before the common 3 m strip.
    x, z = points[:, 0], points[:, 2]
    rise = _smooth((x - 231.5) / 8.5)
    fall = 1. - _smooth((x - 253.) / 15.5)
    bend = (np.abs(z - 29.5) < 1e-6) * rise * fall
    points[:, 2] -= 4.5 * bend
    # Meet the existing low door approach. Retaining the old high cartway
    # level here would force a metre-high berm across the short tower path.
    points[:, 1] -= bend
    road['contactStations'] = points.tolist()
    road['contactNote'] = 'The public cartway bends north of the intact Cinder Tower foundation.'


def _white_road(build, road):
    original = _sampled_road(build, road)
    join = np.array([50., -220.])
    index = int(np.argmin(np.linalg.norm(original[:, [0, 2]] - join, axis=1)))
    # The old route began inside the stone tower. Its logical survey station
    # remains recorded in road['stations']; the public carriageway begins on
    # clear ground east of the tower and rounds its northern side.
    control = np.array([[76.5, 49.21056514309974, -214.5],
                        [77., 49.85, -217.5], [76.5, 50.65, -221.],
                        [74., 51.2, -223.], [70., 51.5, -224.],
                        [63., 51.8, -224.], [56., 51.8, -223.],
                        original[index]], dtype=float)
    # Catmull-Rom gives a rounded cartway silhouette rather than another
    # sequence of sharp planar corners. Its exact endpoints remain authored.
    extended = np.vstack([control[0], control, original[min(index+1, len(original)-1)]])
    curve = []
    for i in range(1, len(control)):
        a, b, c, d = extended[i-1:i+3]
        count = max(2, int(np.ceil(np.linalg.norm(c[[0, 2]]-b[[0, 2]])/.4)))
        for t in np.linspace(0., 1., count, endpoint=False):
            curve.append(.5*((2*b)+(-a+c)*t+(2*a-5*b+4*c-d)*t*t+(-a+3*b-3*c+d)*t*t*t))
    points = np.vstack([curve, original[index:]])
    road['contactStations'] = points.tolist()
    road['contactStartReason'] = ('The original inland survey point lies inside North Gate Tower masonry; '
        'the clear public road begins east of the tower and curves around its northern footing. '
        'The original logical station and continental seam remain preserved.')
    road['contactNote'] = 'North Gate Tower retains its foundation and room-scale identity beside the rounded public approach.'


def _seat_fallen_tree(build):
    """Put the unlinked fallen tree on the meadow contour beside the road."""
    p = next((p for p in build.placements if p.node == 'FallenLog_0070'), None)
    # The far tier deliberately omits ground-detail logs.
    if p is None:
        return
    if p.landmark:
        raise ValueError('The movable roadside fallen tree acquired a landmark role')
    ground = VerticalRayIndex(_triangles([m for name, m in build.terrain_meshes.items()
        if name.startswith('Terrain_') and not any(part in name for part in
            ('_StreamCollar_', '_ContinentBlend_', 'OuterEscarpment', '_StreamThreshold_'))]))
    mesh = build.meshes[p.mesh].copy()
    local = mesh.positions * p.scale @ M.rotation_y(p.rotation_y)[:3, :3].T
    origin = np.array([135., 0., 75.])
    # Fit the local meadow plane, then rigidly pitch the whole trunk to it.
    # This retains its shape and avoids balancing a ten-metre log at one end.
    sample = np.array([[x, z] for x in (-9., -4.5, 0.) for z in (-1., 0., 1.)])
    heights = np.array([ground.top_hit(*(origin[[0, 2]] + q)) for q in sample])
    if not np.isfinite(heights).all():
        raise ValueError('Amber fallen-tree meadow lacks actual terrain support')
    coefficients = np.linalg.lstsq(np.c_[sample, np.ones(len(sample))], heights, rcond=None)[0]
    normal = np.array([-coefficients[0], 1., -coefficients[1]])
    normal /= np.linalg.norm(normal)
    axis = np.cross([0., 1., 0.], normal)
    cosine = normal[1]
    cross = np.array([[0., -axis[2], axis[1]], [axis[2], 0., -axis[0]], [-axis[1], axis[0], 0.]])
    rotation = np.eye(3) + cross + cross @ cross / (1. + cosine)
    local = local @ rotation.T
    # The lowest mesh vertex makes literal contact, with a modest bark sink.
    bottom = int(np.argmin(local[:, 1] - local[:, [0, 2]] @ coefficients[:2]))
    contact = origin[[0, 2]] + local[bottom, [0, 2]]
    origin[1] = float(ground.top_hit(*contact) - local[bottom, 1] - .035)
    mesh.positions = local
    mesh.recompute_normals(180)
    mesh_name = 'FallenLog_0070_Meadow'
    build.meshes[mesh_name] = mesh
    previous = list(p.position)
    p.mesh, p.position, p.rotation_y, p.scale = mesh_name, tuple(origin), 0., 1.
    p.kind = 'scatter'
    build.amber_roadside_corrections = {'fallenTree': {'node': p.node,
        'before': previous, 'after': list(p.position), 'groundContact': contact.tolist(),
        'contactSink': .035}}


def apply(build):
    if getattr(build, '_amber_tower_bypasses', False):
        raise ValueError('Amber local tower approaches applied twice')
    roads = {road['id']: road for road in build.geography_roads}
    _mirror_road(build, roads['amberwood-mirrorhold'])
    _white_road(build, roads['amberwood-whitehorn'])
    _seat_fallen_tree(build)
    build._amber_tower_bypasses = True
