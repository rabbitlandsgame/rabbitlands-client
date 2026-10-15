"""Derive strict actor collision from the shared field and exported geometry.

Half-metre cells cover logical tiles [2(t-min):2(t-min)+2] on both axes. Terrain follows the
same two triangles per two-metre square as the continent master. Declared Walk
faces may support bridges and thresholds; structural triangle intersections
close the actual actor volume, without filling an archway beneath its roof.
No toolkit state, source GLB, or world height is modified by this exporter.
"""
from __future__ import annotations

import copy
import hashlib
import math
from pathlib import Path
import struct
import sys

import numpy as np
from storage_bounds import StorageBounds, authoring_storage

TOOLKIT = Path(__file__).resolve().parents[1] / '_toolkit'
if str(TOOLKIT) not in sys.path:
    sys.path.insert(0, str(TOOLKIT))
import glb_reader as GR

CELL = .5
MAX_GRADE = .65
WADE = .35
ACTOR_FLOOR_CLEARANCE = .06
ACTOR_HEIGHT = 2.1
GATE_DEPTH = 2.0
GATE_INWARD_DEPTH = 4.0
GATE_HALF_WIDTH = 4.0
CEILINGS = ('ceiling', 'soffit', 'underside', 'roof')


def _field_indices(world, x, z):
    spacing = float(getattr(world, 'cell', 2.0))
    fx = np.clip((x - world.x0) / spacing, 0, world.height.shape[1] - 1.0000001)
    fz = np.clip((z - world.z0) / spacing, 0, world.height.shape[0] - 1.0000001)
    return fx.astype(np.int32), fz.astype(np.int32), fx % 1, fz % 1, spacing


def terrain_grade(world, x, z):
    ix, iz, u, v, spacing = _field_indices(world, x, z)
    a, b = world.height[iz, ix], world.height[iz, ix + 1]
    c, d = world.height[iz + 1, ix], world.height[iz + 1, ix + 1]
    dx = np.where(u + v <= 1, b - a, d - c) / spacing
    dz = np.where(u + v <= 1, c - a, d - b) / spacing
    return np.hypot(dx, dz)


def water_samples(world, x, z):
    from terrain_export import sample_water_surface
    return sample_water_surface(world,x,z)


def gate_halo(world, region, gx, gz):
    halo = np.zeros(gx.shape, dtype=bool)
    for connection in world.connections:
        regions = connection.get('regions', [])
        if connection.get('type') in ('ferry', 'boat', 'ship') or region not in regions:
            continue
        anchor = np.asarray(connection['anchor'], dtype=float)
        normal = np.asarray(connection['normal'], dtype=float)
        normal /= max(np.linalg.norm(normal), 1e-12)
        outward = normal if regions[0] == region else -normal
        dx, dz = gx - anchor[0], gz - anchor[1]
        along = dx * outward[0] + dz * outward[1]
        across = -dx * outward[1] + dz * outward[0]
        other = regions[1] if regions[0] == region else regions[0]
        # The raster ownership edge can step to either side of the surveyed
        # centre line across seven lanes. Match the authored threshold's full
        # -4..+2 m footprint; its actual Walk triangles are still mandatory.
        halo |= ((along >= -GATE_INWARD_DEPTH - 1e-8) & (along <= GATE_DEPTH + 1e-8)
                 & (np.abs(across) <= GATE_HALF_WIDTH + 1e-8)
                 & (world.owner_at(gx, gz) == world.ids.index(other)))
    return halo


def seam_collar(world, region, gx, gz):
    """The first tile of a neighbour's ground beyond an open shared border.

    A crossing is stood on the far side of the boundary: a lane's departure
    tile is the neighbour's first tile across it, and an actor has to be able
    to stand there on this map before the portal under it can fire. The
    authored gate thresholds open that strip for the seven lanes of a gate
    (`gate_halo`, which needs the threshold deck beneath it); a seam crossed
    wherever the ground allows needs it along the whole border instead.

    One tile deep and eight-connected, because a walker's step is: nothing
    beyond a border can be reached without standing on the strip. It is the
    same ground either way - one shared height field, one water plan - so what
    is opened here is what the neighbour already walks on, minus whatever this
    map's own slope, water and structures refuse.
    """
    from scipy.ndimage import binary_dilation
    from crossings import widened
    collar = np.zeros(gx.shape, dtype=bool)
    # Roadless borders too (crossings.open_borders): a walker crosses them
    # wherever the ground allows, as they cross a road's.
    opened = [c for c in list(world.connections) + list(getattr(world, 'open_border_links', ()))
              if widened(c.get('id')) and c.get('type') not in ('ferry', 'boat', 'ship')
              and region in c.get('regions', [])]
    if not opened:
        return collar
    owner = world.owner_at(gx, gz)
    # Two half-cells to the tile, so a tile eight-adjacent to this territory is
    # every one of whose cells stands within two cells of a cell of its own.
    beside = binary_dilation(owner == world.ids.index(region), np.ones((5, 5), dtype=bool))
    saved = {record['id'] for record in getattr(world, 'saved_seam_approaches', ())}
    for connection in opened:
        regions = connection['regions']
        other = regions[1] if regions[0] == region else regions[0]
        collar |= beside & (owner == world.ids.index(other))
        if connection.get('id') in saved:
            # A saved seam's seven canonical triggers are built from
            # anchor +/- one metre, and therefore occupy the second server
            # tile when the ownership raster happens to step at the anchor.
            # Keep that exact two-metre apron on both maps.  This is still
            # neighbour ground and still has to pass slope, water and solid
            # collision below; it does not grade or annex any terrain.
            anchor = np.asarray(connection['anchor'], dtype=float)
            normal = np.asarray(connection['normal'], dtype=float)
            normal /= max(np.linalg.norm(normal), 1e-12)
            outward = normal if regions[0] == region else -normal
            dx, dz = gx - anchor[0], gz - anchor[1]
            along = dx * outward[0] + dz * outward[1]
            across = -dx * outward[1] + dz * outward[0]
            collar |= ((along >= -1e-8) & (along <= GATE_DEPTH + 1e-8)
                       & (np.abs(across) <= GATE_HALF_WIDTH + 1e-8)
                       & (owner == world.ids.index(other)))
    return collar


def _mesh_groups(document, body, manifest):
    """Classify mesh descendants, preserving declared structural root identity."""
    nodes = document['nodes']
    matrices, parents = GR.hierarchy(document)
    solid_roots = set(manifest.get('collision', {}).get('nodeNames', []))
    prefixes = tuple(manifest.get('navigation', {}).get('surfaceNodePrefixes', ['Terrain_', 'Walk_']))
    primitive_cache = {}
    closed_cache = {}
    walk, structures = [], []
    statistics = {'walkMeshes': 0, 'structuralMeshes': 0, 'structuralTriangles': 0}
    for index, node in enumerate(nodes):
        if 'mesh' not in node:
            continue
        ancestry, current = [], index
        while True:
            ancestry.append(nodes[current].get('name', ''))
            if current not in parents:
                break
            current = parents[current]
        surface = any(name.startswith(prefixes) for name in ancestry)
        ceiling = any(any(word in name.lower() for word in CEILINGS) for name in ancestry)
        deck = surface and any(name.startswith('Walk_') for name in ancestry) and not ceiling
        solid = any(name in solid_roots for name in ancestry) and not (surface and not ceiling)
        if not deck and not solid:
            continue
        mesh_index = node['mesh']
        if mesh_index not in primitive_cache:
            parts = []
            for primitive in document['meshes'][mesh_index]['primitives']:
                if primitive.get('mode', 4) != 4:
                    continue
                vertices = GR.accessor(document, body, primitive['attributes']['POSITION']).astype(float)
                indices = (GR.accessor(document, body, primitive['indices']).ravel().astype(np.int64)
                           if 'indices' in primitive else np.arange(len(vertices)))
                parts.append(vertices[indices].reshape(-1, 3, 3))
            primitive_cache[mesh_index] = np.concatenate(parts) if parts else np.empty((0, 3, 3))
        local = primitive_cache[mesh_index]
        matrix = matrices[index]
        triangles = local @ matrix[:3, :3].T + matrix[:3, 3]
        if deck:
            walk.append(triangles)
            statistics['walkMeshes'] += 1
        if solid:
            if mesh_index not in closed_cache:
                closed_cache[mesh_index] = closed_mesh(local)
            structures.append((triangles, closed_cache[mesh_index]))
            statistics['structuralMeshes'] += 1
            statistics['structuralTriangles'] += len(triangles)
    return np.concatenate(walk) if walk else np.empty((0, 3, 3)), structures, statistics


def closed_mesh(triangles):
    """Closed solid primitives require interior occupancy as well as surfaces."""
    if len(triangles) < 4:
        return False
    _, indices = np.unique(np.round(triangles.reshape(-1, 3), 6), axis=0, return_inverse=True)
    faces = indices.reshape(-1, 3)
    valid = (faces[:, 0] != faces[:, 1]) & (faces[:, 1] != faces[:, 2]) & (faces[:, 0] != faces[:, 2])
    faces = faces[valid]
    edges = np.sort(np.concatenate([faces[:, [0, 1]], faces[:, [1, 2]], faces[:, [2, 0]]]), axis=1)
    _, counts = np.unique(edges, axis=0, return_counts=True)
    return bool(len(counts) and np.all(counts == 2))


def _window(triangle, shape, x0, z1, margin=.25):
    low, high = triangle.min(axis=0), triangle.max(axis=0)
    xa = max(0, math.ceil((low[0] - margin - x0) / CELL - .5))
    xb = min(shape[1], math.floor((high[0] + margin - x0) / CELL - .5) + 1)
    za = max(0, math.ceil((z1 - high[2] - margin) / CELL - .5))
    zb = min(shape[0], math.floor((z1 - low[2] + margin) / CELL - .5) + 1)
    return slice(za, max(za, zb)), slice(xa, max(xa, xb))


def triangle_prism_overlap(triangle, cx, cy, cz):
    """Vectorised separating-axis test, including vertical/edge-on triangles."""
    half = np.array([CELL * .5, (ACTOR_HEIGHT - ACTOR_FLOOR_CLEARANCE) * .5, CELL * .5])
    low, high = triangle.min(axis=0), triangle.max(axis=0)
    possible = ((cx + half[0] >= low[0]) & (cx - half[0] <= high[0])
                & (cy + half[1] >= low[1]) & (cy - half[1] <= high[1])
                & (cz + half[2] >= low[2]) & (cz - half[2] <= high[2]))
    edges = np.roll(triangle, -1, axis=0) - triangle
    axes = [np.cross(edges[0], edges[1])]
    axes.extend(np.cross(edge, axis) for edge in edges for axis in np.eye(3))
    for axis in axes:
        if not possible.any():
            break
        if float(axis @ axis) < 1e-18:
            continue
        projections = triangle @ axis
        center = cx * axis[0] + cy * axis[1] + cz * axis[2]
        radius = np.abs(axis) @ half
        possible &= (projections.min() - center <= radius + 1e-9) & (projections.max() - center >= -radius - 1e-9)
    return possible


def _ray_crossing(triangle, gx, gz, standing):
    """Signed solid winding at the actor mid-height, with a half-open raster."""
    a, b, c = triangle
    normal = np.cross(b - a, c - a)
    if abs(normal[1]) < 1e-10:
        return np.zeros(gx.shape, dtype=np.int16)
    vertices = triangle[:, [0, 2]].copy()
    edge_a, edge_b = vertices[1] - vertices[0], vertices[2] - vertices[0]
    oriented = edge_a[0] * edge_b[1] - edge_a[1] * edge_b[0]
    if oriented < 0:
        vertices[[1, 2]] = vertices[[2, 1]]
    inside = np.ones(gx.shape, dtype=bool)
    for start, stop in zip(vertices, np.roll(vertices, -1, axis=0)):
        edge = stop - start
        side = edge[0] * (gz - start[1]) - edge[1] * (gx - start[0])
        inclusive = edge[1] > 0 or edge[1] == 0 and edge[0] < 0
        inside &= (side > 1e-9) | ((np.abs(side) <= 1e-9) & inclusive)
    hit = a[1] - (normal[0] * (gx - a[0]) + normal[2] * (gz - a[2])) / normal[1]
    inside &= hit > standing + ACTOR_HEIGHT * .5
    return inside.astype(np.int16) * (1 if normal[1] > 0 else -1)


def structural_mask(groups, surface, x0, z1):
    blocked = np.zeros(surface.shape, dtype=bool)
    for triangles, closed in groups:
        if not len(triangles):
            continue
        region = _window(triangles.reshape(-1, 3), surface.shape, x0, z1)
        ground = surface[region]
        if ground.size == 0 or triangles[:, :, 1].max() < ground.min() + ACTOR_FLOOR_CLEARANCE:
            continue
        if triangles[:, :, 1].min() > ground.max() + ACTOR_HEIGHT:
            continue
        winding = np.zeros(ground.shape, dtype=np.int16) if closed else None
        for triangle in triangles:
            window = _window(triangle, surface.shape, x0, z1)
            floor = surface[window]
            if not floor.size:
                continue
            xs = x0 + (np.arange(window[1].start, window[1].stop) + .5) * CELL
            zs = z1 - (np.arange(window[0].start, window[0].stop) + .5) * CELL
            gx, gz = np.meshgrid(xs, zs)
            if triangle[:, 1].max() >= floor.min() + ACTOR_FLOOR_CLEARANCE and triangle[:, 1].min() <= floor.max() + ACTOR_HEIGHT:
                cy = floor + (ACTOR_FLOOR_CLEARANCE + ACTOR_HEIGHT) * .5
                blocked[window] |= triangle_prism_overlap(triangle, gx, cy, gz)
            if winding is not None and triangle[:, 1].max() > floor.min() + ACTOR_HEIGHT * .5:
                relative = (slice(window[0].start - region[0].start, window[0].stop - region[0].start),
                            slice(window[1].start - region[1].start, window[1].stop - region[1].start))
                winding[relative] += _ray_crossing(triangle, gx, gz, floor)
        if winding is not None:
            blocked[region] |= winding != 0
    return blocked


def encode_heights(heights, walkable, basis=None):
    """Encode walkable ground into the 255 steps a served grid has.

    ``basis`` is the ground whose range decides the scale, and is this
    territory's own. The seam collar is the neighbour's ground a step beyond
    the border, and how high the land stands over there is no business of this
    map's height scale: a low territory beside a high one would otherwise have
    its steps coarsened, or its own highest ground pushed past the 255th step,
    by a strip of somebody else's hillside. A collar cell the scale cannot
    express is simply not walkable here - the crossing there does not open -
    and a territory with no widened border keeps exactly the scale it had.
    """
    reference = walkable if basis is None or not basis.any() else basis
    if not reference.any():
        return np.zeros(heights.shape, dtype=np.uint8), {'origin': -.2, 'step': .2, 'range': [1, 255]}
    low, high = float(heights[reference].min()), float(heights[reference].max())
    step = max(.2, (high - low) / 253)
    origin = low - step
    values = np.rint((heights - origin) / step)
    inside = (values >= 1) & (values <= 255)
    return (np.where(walkable & inside, np.clip(values, 1, 255), 0).astype(np.uint8),
            {'origin': origin, 'step': step, 'range': [1, 255]})


def storage_contract(world, region):
    """Use World's source authority; historical World-like fixtures are zero-min."""
    if hasattr(world, 'storage_contract'):
        return world.storage_contract(region)
    origin, cells = world.address(region)
    bounds = world.storage(region) if hasattr(world, 'storage') else StorageBounds(*cells)
    return {'serverOrigin': list(origin), 'serverCells': list(cells), **bounds.metadata()}


def validate_storage_frame(world, region, manifest):
    """Check metadata before reading geometry or reusing any collision cache."""
    declared = storage_contract(world, region)
    bounds = StorageBounds.from_metadata(declared['serverCells'], declared)
    transform = manifest['coordinateTransform']
    if list(transform['serverOrigin']) != declared['serverOrigin']:
        raise ValueError(f'{region}: authored world and manifest address origins differ')
    if list(transform['serverCells']) != declared['serverCells']:
        raise ValueError(f'{region}: authored world and manifest address extents differ')
    if StorageBounds.from_metadata(transform['serverCells'], transform) != bounds:
        raise ValueError(f'{region}: authored world and manifest storage minima differ')
    x0, z1 = bounds.physical_origin(declared['serverOrigin'])
    server = {'origin': declared['serverOrigin'], 'cells': declared['serverCells'],
              **bounds.metadata(), 'localOrigin': transform.get('origin', [0, 0, 0]),
              'metresPerTile': transform.get('metresPerTile', 1),
              'invertServerY': transform.get('invertServerY', True),
              'collisionOriginMetres': [x0, z1]}
    authoring_storage(server)
    collision = manifest.get('collision', {})
    if 'originMetres' in collision and collision['originMetres'] != [x0, z1]:
        raise ValueError(f'{region}: collision physical storage origin differs')
    if ('serverStorageVersion' in collision or 'serverTileMin' in collision or 'serverCells' in collision):
        if StorageBounds.from_metadata(collision.get('serverCells', declared['serverCells']), collision) != bounds:
            raise ValueError(f'{region}: collision metadata storage differs')
    return declared, bounds


def export_collision(world, region, manifest, glb_path, output_path):
    """Return collision metadata plus arrays; write only the requested EWCG file.

Keys: ``collision`` is JSON-safe metadata; ``heights`` contains metre heights,
``walkable`` the authoritative half-cell mask, and ``grid`` encoded EWCG bytes.
The caller installs collision metadata into its final world manifest itself.
    """
    declared, bounds = validate_storage_frame(world, region, manifest)
    origin, cells = declared['serverOrigin'], declared['serverCells']
    center = np.asarray(world.regions[region]['center'], dtype=float)
    width, rows = int(cells[0] * 2), int(cells[1] * 2)
    x0, z1 = map(float, bounds.physical_origin(origin))
    lx, lz = np.meshgrid(x0 + (np.arange(width) + .5) * CELL, z1 - (np.arange(rows) + .5) * CELL)
    gx, gz = lx + center[0], lz + center[1]
    surface = np.asarray(world.height_at(gx, gz), dtype=float)
    grade = terrain_grade(world, gx, gz)
    own = world.owner_at(gx, gz) == world.ids.index(region)
    own &= (gx >= world.x0) & (gz >= world.z0) & (gx < world.x1) & (gz < world.z1)
    wet, water = water_samples(world, gx, gz)
    document, body = GR.load(Path(glb_path))
    walk_triangles, structures, statistics = _mesh_groups(document, body, manifest)
    covered, deck = GR.rasterise(walk_triangles, width, rows, x0, z1, CELL,
                                upward=1 / math.sqrt(1 + MAX_GRADE ** 2) - 1e-9)
    deck_support = covered & (deck >= surface - .03)
    np.copyto(surface, deck, where=deck_support)
    slope_allowed = (grade <= MAX_GRADE + 1e-9) | deck_support
    halo = gate_halo(world, region, gx, gz) & deck_support
    collar = seam_collar(world, region, gx, gz)
    collar &= (gx >= world.x0) & (gz >= world.z0) & (gx < world.x1) & (gz < world.z1)
    submerged = wet & (surface < water - WADE)
    structure = structural_mask(structures, surface, x0, z1)
    standable = slope_allowed & ~submerged & ~structure & np.isfinite(surface)
    # This territory's own ground, which is what its height scale is built from.
    settled = (own | halo) & standable
    walkable = settled | (collar & standable)
    grid, encoding = encode_heights(surface, walkable, basis=settled)
    walkable &= grid != 0
    path = Path(output_path)
    if storage_contract(world, region) != declared:
        raise ValueError(f'{region}: storage source changed during collision export; recompose')
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(struct.pack('<4sHHII', b'EWCG', 2, 0, width, rows) + grid.tobytes())
    collision = copy.deepcopy(manifest.get('collision', {}))
    collision.update(binary=path.name, format='EWCG-v2', width=width, height=rows, cellMetres=CELL,
        **bounds.metadata(), serverCells=cells,
        originMetres=[x0, z1], heightEncoding=encoding, gridAlignment='tile-centres-v1',
        authoredSurfaceExport=True, maxTerrainGrade=MAX_GRADE, maximumWadingDepth=WADE,
        thresholdHalo={'inwardMetres': GATE_INWARD_DEPTH, 'outwardMetres': GATE_DEPTH,
                       'halfWidthMetres': GATE_HALF_WIDTH},
        actorVolume={'floorClearance': ACTOR_FLOOR_CLEARANCE, 'height': ACTOR_HEIGHT, 'halfCellWidth': CELL},
        walkableCells=int(walkable.sum()), walkableFraction=round(float(walkable.mean()), 6),
        sourceGlbSha256=hashlib.sha256(Path(glb_path).read_bytes()).hexdigest(),
        exportStatistics={**statistics, 'walkTriangles': len(walk_triangles),
            'steepCells': int((own & ~slope_allowed).sum()), 'waterCells': int((own & submerged).sum()),
            'structuralCells': int((own & structure).sum()), 'thresholdHaloCells': int(halo.sum()),
            'seamCollarCells': int((collar & ~own & ~halo & walkable).sum())})
    if 'authoringSpecSha256' in declared:
        collision['authoringSpecSha256'] = declared['authoringSpecSha256']
    return {'collision': collision, 'heights': surface.astype(np.float32), 'walkable': walkable, 'grid': grid}
