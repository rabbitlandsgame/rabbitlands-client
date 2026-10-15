"""Broad northern cols around the surveyed roads, with intact civic footings.

The road survey fixes travel elevations. This second landscape pass opens the
surrounding mountain shoulders so that those roads inhabit valleys instead of
seven-metre trenches. No water, road deck, common edge or structure is moved.
"""
import numpy as np

ROADS = {
    'whitehorn_range': {'whitehorn-amethyst'},
    'mirrorhold': {'mirrorhold-amethyst'},
    'amethyst_barrens': {'whitehorn-amethyst', 'mirrorhold-amethyst'},
}
NATURAL_KINDS = {'tree', 'foliage', 'rock', 'undergrowth', 'stone', 'scatter', 'scrub', 'crystal'}


def _fixed_nodes(build):
    # Wayfinding poles can follow their verge; built/discovery landmarks and
    # deliberately floating shards retain their actual footprint and pose.
    return {e.get('node') for e in getattr(build, 'landmarks', [])
            if e.get('node') and not e['node'].endswith('_Signpost')} | {
        p.node for p in build.placements if p.landmark or p.node.startswith('Secret_')}


def _smooth(value):
    value = np.clip(value, 0., 1.)
    return value * value * (3. - 2. * value)


def _footprints(build):
    """Protect real transformed rectangular footings, not circumscribed circles."""
    from amberwood.mesh import rotation_y
    result = []
    fixed = _fixed_nodes(build)
    for p in build.placements:
        if p.node not in fixed and (not p.collides or p.kind in NATURAL_KINDS):
            continue
        mesh = build.meshes.get(p.mesh)
        if mesh is None:
            continue
        lo, hi = mesh.bounds()
        corners = np.array([[x, y, z] for x in (lo[0], hi[0])
                            for y in (lo[1], hi[1]) for z in (lo[2], hi[2])])
        world = corners * p.scale @ rotation_y(p.rotation_y)[:3, :3].T + p.position
        result.append((world[:, [0, 2]].min(axis=0), world[:, [0, 2]].max(axis=0)))
    return result


def apply(build, region):
    import continent_geography as G
    roads = [r for r in getattr(build, 'geography_roads', []) if r['id'] in ROADS.get(region, set())]
    if not roads:
        return
    footprints = _footprints(build)
    profiles = []
    for road in roads:
        p = np.array(road['stations'], float)
        lengths = np.r_[0., np.cumsum(np.linalg.norm(np.diff(p[:, [0, 2]], axis=0), axis=1))]
        profiles.append((p, lengths / lengths[-1]))

    def shape(points):
        points = np.asarray(points, float)
        xz = points[:, [0, 2]]
        distance = np.full(len(points), np.inf)
        level = np.zeros(len(points))
        for stations, lengths in profiles:
            d, along = G._road_coordinates(xz, stations[:, [0, 2]])
            nearer = d < distance
            level[nearer] = np.interp(along[nearer], lengths, stations[:, 1])
            distance[nearer] = d[nearer]
        # A cart-width bed opens into a broad meadow/scree floor, then the
        # mountain grows continuously into the retained distant ridge.
        flank = np.maximum(distance - 5., 0.)
        ceiling = level + .012 * flank ** 2
        lower = level - .06 - .055 * flank ** 2
        target = np.clip(points[:, 1], lower, ceiling)
        weight = 1. - _smooth((distance - 65.) / 65.)
        # Keep the committed common contour exactly, including its inserted
        # knots. Its own broad saddle is already low near each road mouth.
        boundary, _ = G.boundary_sample(region, xz, maximum=3.)
        weight *= _smooth(boundary / 3.)
        for lo, hi in footprints:
            outside = np.linalg.norm(np.maximum(np.maximum(lo-xz, xz-hi), 0.), axis=1)
            weight *= _smooth(outside / 8.)
        result = points.copy()
        result[:, 1] += (target - points[:, 1]) * weight
        return result

    # Small natural objects follow the reshaped slope with their authored
    # contact offset; service and discovery structures retain their footings.
    t = build.terrain
    fixed = _fixed_nodes(build)
    scatter = [p for p in build.placements if p.node not in fixed
               and (G._is_scatter(p) or p.kind in NATURAL_KINDS)]
    lifts = {}
    if scatter:
        original = np.array([p.position for p in scatter], float)
        original[:, 1] = t.height_at(original[:, 0], original[:, 2])
        for p, delta in zip(scatter, shape(original)[:, 1] - original[:, 1]):
            if abs(delta) > 1e-8:
                p.position = (p.position[0], p.position[1] + float(delta), p.position[2])
                lifts[p.node] = float(delta)
    landmarks = {e.get('id'):e.get('node') for e in getattr(build, 'landmarks', [])}
    seen = set()
    for collection in ('landmarks', 'interactives', 'npc_markers', 'harvestables', 'portals', 'spawns'):
        for entry in getattr(build, collection, []):
            if id(entry) in seen:
                continue
            seen.add(id(entry))
            node = entry.get('node') or landmarks.get(entry.get('landmark'))
            if node in lifts and 'position' in entry:
                entry['position'][1] += lifts[node]
    for name, mesh in build.terrain_meshes.items():
        if name.startswith('Terrain_'):
            mesh.positions = shape(mesh.positions)
            mesh.recompute_normals(180)
    points = np.c_[t.gx.ravel(), t.height.ravel(), t.gz.ravel()]
    t.height = shape(points)[:, 1].reshape(t.height.shape)
    build.notes.append('Northern cols: broad connected valley floors and curved scree shoulders around the surveyed roads; exact common contours and real structure footings retained.')
