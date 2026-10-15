"""Open the delta approach into a low, broad ruin-side channel bench.

The shared causeway crosses an old exterior ridge. Cutting only its seven
lanes exposed that ridge as two tall walls. This local lowering pass follows
the existing channel, preserving actual ruin feet, water and every walking
mesh. It runs after connector seating and before geographic paint allocation.
"""
from copy import copy

import numpy as np

import connector_finish as F

NATURAL = {'tree', 'foliage', 'rock', 'undergrowth', 'stone', 'scatter', 'fern', 'vine'}


def structural_footings(build):
    """Actual low connected structural geometry, independent of terrain LOD.

    A buried roof is not a foundation. Testing structure vertices against the
    current coarse terrain used to preserve different masks in the two LODs.
    The fixed assembly's real lowest contact band provides one stable mask.
    """
    from scipy.sparse import coo_matrix
    from scipy.sparse.csgraph import connected_components
    from scipy.spatial import ConvexHull, QhullError
    result = []
    fixed = {m.get('node') for m in build.landmarks}
    for p in build.placements:
        if p.node not in fixed and not p.landmark and (p.kind in NATURAL or not p.collides):
            continue
        item = build.meshes.get(p.mesh)
        if item is None:
            continue
        rotation = F.M.rotation_y(p.rotation_y)[:3, :3]
        triangles = []
        for part in getattr(item, 'all_parts', [item]):
            if part.triangle_count:
                vertices = part.positions * p.scale @ rotation.T + p.position
                triangles.append(vertices[part.indices.reshape(-1, 3)])
        if not triangles:
            continue
        vertices = np.concatenate(triangles).reshape(-1, 3)
        shell = F.M.Mesh(positions=vertices, normals=np.zeros_like(vertices),
                         uvs=np.zeros((len(vertices), 2)), indices=np.arange(len(vertices)))
        low = F.R._clip_scalar(shell, vertices[:, 1] - vertices[:, 1].min() - .6)
        points, labels = np.unique(np.round(low.positions, 7), axis=0, return_inverse=True)
        faces = labels[low.indices.reshape(-1, 3)]
        edges = np.concatenate([faces[:, [0, 1]], faces[:, [1, 2]], faces[:, [2, 0]]])
        graph = coo_matrix((np.ones(len(edges)), (edges[:, 0], edges[:, 1])), shape=(len(points), len(points)))
        count, groups = connected_components(graph, directed=False)
        for component in range(count):
            xz = np.unique(points[groups == component][:, [0, 2]], axis=0)
            try:
                polygon = xz[ConvexHull(xz).vertices]
            except QhullError:
                lo, hi = xz.min(0) - .025, xz.max(0) + .025
                polygon = np.array([lo, [hi[0], lo[1]], hi, [lo[0], hi[1]]])
            result.append(polygon)
    return result


def root_low_y(item, scale):
    """Use the trunk's root band; low hanging palm fronds are not feet."""
    parts = [p for p in getattr(item, 'all_parts', [item]) if p.triangle_count]
    trunks = [p for p in parts if 'bark' in p.material.lower()]
    return min(float(p.positions[:, 1].min()) * scale for p in (trunks or parts))


def _smooth(value):
    value = np.clip(value, 0., 1.)
    return value * value * (3. - 2. * value)


def distance_to_channel(xz):
    closest = np.c_[np.clip(xz[:, 0], -149.5, -107.5), np.full(len(xz), -73.5)]
    return np.linalg.norm(xz - closest, axis=1)


def shape(points, footprints=()):
    """Lower shoulders only; the common three-metre strip is immutable."""
    result = points.copy()
    xz = points[:, [0, 2]]
    distance = distance_to_channel(xz)
    selected = distance < 52.
    if not selected.any():
        return result
    ids = np.flatnonzero(selected)
    q = xz[ids]
    # A five-metre near-bank shelf rises gently into the former ridge.
    cap = 4. + .020 * np.maximum(distance[ids] - 5., 0.) ** 2
    weight = _smooth((52. - distance[ids]) / 16.)
    edge = F.G.boundary_sample('ssarathi_ruins', q, maximum=16.)[0]
    weight *= _smooth((edge - 3.) / 9.)
    for polygon in footprints:
        near = np.all(q >= polygon.min(0) - 3., axis=1) & np.all(q <= polygon.max(0) + 3., axis=1)
        if near.any():
            weight[near] *= _smooth(F._footing_distance(q[near], polygon) / 3.)
    result[ids, 1] += weight * (np.minimum(points[ids, 1], cap) - points[ids, 1])
    return result


def apply(build):
    if getattr(build, 'west_bank_finish', None) is not None:
        return build.west_bank_finish
    # Ground-contact polygons use actual connected low mesh geometry. The
    # low Ruin_0 court stays intact without retaining its old 22m hill skirt.
    nearby = copy(build)
    fixed = {m.get('node') for m in build.landmarks}
    nearby.placements = [p for p in build.placements
                         if -205. < p.position[0] < -50. and -135. < p.position[2] < -15.
                         and (p.node in fixed or p.landmark or p.kind not in NATURAL)]
    footprints = structural_footings(nearby)
    base_names = [n for n, m in build.terrain_meshes.items() if F._base(n) and m.triangle_count]
    before = F.VerticalRayIndex(F._triangles([build.terrain_meshes[n] for n in base_names]))
    changed = 0
    stone_faces = 0
    stone_keys = set()
    additions = {}
    for name in base_names:
        mesh = build.terrain_meshes[name]
        old = mesh.positions.copy()
        mesh.positions = shape(old, footprints)
        delta = old[:, 1] - mesh.positions[:, 1]
        changed += int((delta > 1e-7).sum())
        if not (delta > 1e-7).any():
            continue
        mesh.recompute_normals(180)
        faces = mesh.indices.reshape(-1, 3)
        tri = mesh.positions[faces]
        normal = np.cross(tri[:, 1] - tri[:, 0], tri[:, 2] - tri[:, 0])
        steep = np.linalg.norm(normal[:, [0, 2]], axis=1) > .65 * abs(normal[:, 1])
        cut = (delta[faces].mean(axis=1) > 2.) & steep
        if not cut.any():
            continue
        # Literal disjoint substrate faces, never an overlapping rock decal.
        rock = mesh.copy()
        rock.indices = faces[cut].ravel()
        rock.material = 'cliff_rock_ground'
        rock.uvs = rock.positions[:, [0, 2]] * .12
        new_name = name + '_StreamCell_WestBankStone'
        additions[new_name] = rock
        for triangle in tri[cut]:
            stone_keys.add(tuple(sorted(tuple(v) for v in np.rint(triangle[:, [0, 2]] * 1e6).astype(np.int64))))
        mesh.indices = faces[~cut].ravel()
        stone_faces += int(cut.sum())
        for frame in build.streaming_borders:
            if name in frame.get('sceneNodes', []):
                frame['sceneNodes'].append(new_name)
    build.terrain_meshes.update(additions)
    # Geographic paint is reseated by terrain_paint next. At exposed cuts,
    # the actual stone substrate should show through instead of grass paint.
    for name, mesh in build.terrain_meshes.items():
        if not name.startswith('Terrain_') or F._base(name) or not mesh.triangle_count:
            continue
        faces = mesh.indices.reshape(-1, 3)
        keep = []
        for triangle in mesh.positions[faces][:, :, [0, 2]]:
            key = tuple(sorted(tuple(v) for v in np.rint(triangle * 1e6).astype(np.int64)))
            keep.append(key not in stone_keys)
        mesh.indices = faces[np.asarray(keep)].ravel()
    after = F.VerticalRayIndex(F._triangles([m for n, m in build.terrain_meshes.items() if F._base(n)]))
    moved, removed = {}, set()
    for placement in build.placements:
        if placement.node in fixed or placement.landmark or placement.walk_surface:
            continue
        if placement.kind not in NATURAL or placement.node.startswith('LilyRaft_'):
            continue
        x, y, z = placement.position
        if distance_to_channel(np.array([[x, z]]))[0] >= 40.:
            continue
        old_y, new_y = before.top_hit(x, z), after.top_hit(x, z)
        if old_y is None or new_y is None:
            continue
        if new_y < -.5:
            removed.add(placement.node)
            continue
        target_y = y + new_y - old_y
        if placement.kind == 'tree':
            # Prior boundary grading could leave trees high above actual soil.
            # Reusing that old offset perpetuates the visible floating trunk.
            target_y = new_y - root_low_y(build.meshes[placement.mesh], placement.scale)
        if abs(target_y - y) > 1e-5:
            placement.position = (x, target_y, z)
            moved[placement.node] = float(target_y - y)
    build.placements[:] = [p for p in build.placements if p.node not in removed]
    for frame in build.streaming_borders:
        frame['sceneNodes'] = [n for n in frame.get('sceneNodes', []) if n not in removed]
    terrain = build.terrain
    points = np.c_[terrain.gx.ravel(), terrain.height.ravel(), terrain.gz.ravel()]
    terrain.height = shape(points, footprints)[:, 1].reshape(terrain.height.shape)
    report = dict(changedTerrainVertices=changed, exposedStoneFaces=stone_faces,
                  movedScatter=moved, removedSubmergedScatter=sorted(removed),
                  protectedFootingPolygons=len(footprints))
    build.west_bank_finish = report
    build.notes.append('The western delta road runs through a broad low ruin-side bench, with exposed stone cuts and preserved causeway, water and actual ruin foundations.')
    return report
