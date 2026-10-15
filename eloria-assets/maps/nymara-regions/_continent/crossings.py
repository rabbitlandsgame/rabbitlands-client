"""Survey reciprocal territory gates in the single global coordinate system."""
from __future__ import annotations
from collections import deque
import copy
import numpy as np
from storage_bounds import StorageBounds

# A land crossing has been a gate: seven lanes about a surveyed anchor, with an
# authored threshold deck under them, and the rest of the border impassable
# however gentle the ground either side of it. A seam is crossed instead
# wherever the ground allows, which is every tile of the border a walker can
# stand on on both maps: its lanes come from the two served collision grids and
# its collar from the whole border (collision_export.seam_collar).
#
# Manymouth Delta to Verdant Stair was opened first, on its own, and went from
# seven lanes a side to 298 and 290 with no contract failing. A seam named here
# keeps only the seven lanes of its gate.
GATED_SEAMS = ()


def widened(identity):
    """Whether a land seam is crossed along its length or only at its gate."""
    return identity not in GATED_SEAMS


def storage_bounds(world, region):
    """Logical envelope; legacy World-like fixtures retain zero minima."""
    return world.storage(region) if hasattr(world, 'storage') else StorageBounds(*world.address(region)[1])


def tile_for(world, region, global_xz):
    origin, _ = world.address(region)
    p = np.asarray(global_xz) - world.regions[region]['center']
    return [int(np.floor(p[0] + origin[0])), int(np.floor(origin[1] - p[1]))]


def global_tile(world, region, tile):
    origin, _ = world.address(region)
    center = world.regions[region]['center']
    return np.array([tile[0] + .5 - origin[0] + center[0],
                     origin[1] - tile[1] - .5 + center[1]])


def tiles_at(world, region, gx, gz):
    """The tiles under global points, in one region's own tile frame.

    Every territory's tile grid is the same metre grid in the shared frame -
    the server origins are whole tiles and the translations whole metres - so
    this is exact, and the tile of one map that answers to a global point names
    the same ground as the tile of another map that answers to it.
    """
    origin, _ = world.address(region)
    center = world.regions[region]['center']
    return (np.rint(np.asarray(gx, dtype=float) - center[0] + origin[0] - .5).astype(int),
            np.rint(origin[1] + center[1] - np.asarray(gz, dtype=float) - .5).astype(int))


def seam_tiles(world, link, side):
    """The tiles either side of one border, in the near region's own tile frame.

    ``outward`` is the neighbour's first tile beyond the border and ``inward``
    the near territory's last tile inside it. A crossing is stood on the
    outward ring: a walker steps off their own ground onto the first tile of
    the neighbour's, and the portal under it hands them to the neighbour's map
    at that same cell - which is why a crossing moves nobody and needs no fade.
    Both rings are eight-connected because a walker's step is, so there is no
    tile beyond a border that can be reached without standing on a crossing.
    """
    from scipy.ndimage import binary_dilation
    region, other = link['regions'][side], link['regions'][1 - side]
    origin, _ = world.address(region)
    bounds = storage_bounds(world, region)
    segments = np.asarray(link['edgeSegments'], dtype=float).reshape(-1, 2)
    low, high = segments.min(axis=0) - 4., segments.max(axis=0) + 4.
    x0, y1 = tiles_at(world, region, low[0], low[1])
    x1, y0 = tiles_at(world, region, high[0], high[1])
    xs = np.arange(max(bounds.min_x, int(x0)), min(bounds.max_x, int(x1) + 1))
    ys = np.arange(max(bounds.min_y, int(y0)), min(bounds.max_y, int(y1) + 1))
    if xs.size == 0 or ys.size == 0:
        return None
    tx, ty = np.meshgrid(xs, ys)
    gx = tx + .5 - origin[0] + world.regions[region]['center'][0]
    gz = origin[1] - ty - .5 + world.regions[region]['center'][1]
    owner = world.owner_at(gx, gz)
    mine, theirs = owner == world.ids.index(region), owner == world.ids.index(other)
    step = np.ones((3, 3), dtype=bool)
    return {'tx': tx, 'ty': ty, 'gx': gx, 'gz': gz,
            'outward': theirs & binary_dilation(mine, step),
            'inward': mine & binary_dilation(theirs, step)}


def own_ground(world, region, grid):
    """A map's served grid and the tiles its territory owns."""
    origin, _ = world.address(region)
    bounds = storage_bounds(world, region)
    if grid.shape != (bounds.height, bounds.width):
        raise ValueError(f'{region}: served grid dimensions differ from storage')
    center = world.regions[region]['center']
    ys, xs = np.indices(grid.shape)
    xs, ys = xs + bounds.min_x, ys + bounds.min_y
    mine = np.asarray(world.owner_at(xs + .5 - origin[0] + center[0], origin[1] - ys - .5 + center[1])) \
        == world.ids.index(region)
    return {'grid': grid, 'own': mine}


def crossing_lanes(world, link, side, served, step):
    """Every lane this border offers: walkable ground on both sides and a legal step between.

    ``served`` holds each map's ``own_ground``; ``step(heights, y, x, dy, dx)`` is
    the server's step test (collision_sources.walk_step_ok at the contract's
    climb limit). A lane is the neighbour's first tile across the border that
    this map's grid lets an actor stand on and step onto from a tile of its own
    territory beside it, and whose cell the neighbour's grid lets an actor stand
    on; it is paired with the tile it is stepped onto from, where a walker
    arriving the other way lands.

    Nothing here asks whether either map's hub can reach the spot. It did, and
    that closed every stretch of border where one side is a pocket its own hub
    cannot walk to - the Manymouth strip between the Four Gates south wall and
    the Mirrorwater, cut off from the delta by the river, left 120 of the 141
    walkable segments of that border without a crossing, and a walker outside
    the south gate was sent back through the town to the nearest one. The rule
    is the owner's: ground walkable on both sides of a border is a way across.
    Nobody can be stranded by it, since every lane's reverse stands at the same
    place: a walker who crosses into a pocket can always step back.
    """
    rings = seam_tiles(world, link, side)
    region, other = link['regions'][side], link['regions'][1 - side]
    near, far = served.get(region), served.get(other)
    if rings is None or near is None or far is None:
        return []
    mask = rings['outward']
    tx, ty = rings['tx'][mask], rings['ty'][mask]
    ox, oy = tiles_at(world, other, rings['gx'][mask], rings['gz'][mask])
    near_bounds, far_bounds = storage_bounds(world, region), storage_bounds(world, other)
    lanes = []
    for x, y, fx, fy in zip(tx.tolist(), ty.tolist(), ox.tolist(), oy.tolist()):
        far_index = far_bounds.index_xy(fx, fy)
        if far_index is None or not far['grid'][far_index[1], far_index[0]]:
            continue
        # From each tile of this map's own ground beside it, straight steps
        # first so a straight seam pairs straight across.
        partners = []
        for dx in (0, -1, 1):
            for dy in (0, -1, 1):
                if not (dx or dy):
                    continue
                index = near_bounds.index_xy(x + dx, y + dy)
                if index is not None:
                    ix, iy = index
                    if (near['own'][iy, ix] and near['grid'][iy, ix]
                            and step(near['grid'], iy, ix, -dy, -dx)):
                        partners.append((x + dx, y + dy))
        if not partners:
            continue
        partner = min(partners, key=lambda t: (abs(t[0] - x) + abs(t[1] - y), t[1], t[0]))
        lanes.append({'tile': [x, y], 'arrival': [partner[0], partner[1]]})
    return lanes


def departs_outward(world, region, lane):
    """Whether a lane is stood on beyond its own territory, as a crossing must be.

    A gate's lanes are laid by geometry - seven offsets along the surveyed
    seam from its anchor - and where the ownership raster steps near the anchor
    one of them can land on its own map's side of the border. While that seam
    was nowhere else crossable it did no harm. Once the other map's lanes run
    the whole border, that tile is also the other map's first tile across, so
    each map would send a walker to the other from the one cell: the arrival
    would trigger the crossing back at once.
    """
    point = global_tile(world, region, lane['tile'])
    return int(np.asarray(world.owner_at(point[0], point[1]))) != world.ids.index(region)


def reseat(world, end):
    """Keep an end's own crossing - its tile, arrival and position - on one of its lanes.

    The end's tile is the gate's middle lane, and its position is where a
    client walking to the neighbour aims its first leg. When the border opens,
    the gate's lanes become the border lanes nearest them, so the end moves to
    the lane that now carries the gate's middle offset, or failing that the
    lane nearest where it stood.
    """
    if not end['lanes'] or any(lane['tile'] == end['tile'] and lane.get('gate') == 0 for lane in end['lanes']):
        return
    middle = [lane for lane in end['lanes'] if lane.get('gate') == 0]
    lane = middle[0] if middle else min(end['lanes'], key=lambda lane: (
        (lane['tile'][0] - end['tile'][0]) ** 2 + (lane['tile'][1] - end['tile'][1]) ** 2, lane['tile']))
    region = end['region']
    center = np.asarray(world.regions[region]['center'], dtype=float)
    point = global_tile(world, region, lane['tile'])
    end['tile'], end['arrival'] = list(lane['tile']), list(lane['arrival'])
    end['position'] = [float(point[0] - center[0]), float(world.height_at(*point)), float(point[1] - center[1])]


def widen_seams(world, connections, served, step, gated=None):
    """Give each open seam every lane its two maps' ground allows, and nothing else.

    Every published lane is a border lane (``crossing_lanes``): the neighbour's
    first tile across the border, stepped onto from ground this map's hub
    reaches without crossing. The gate's surveyed lanes are not kept for their
    own sake. The survey lays one side's on the second tile beyond the border,
    which a walker can only reach over the first - a border lane that fires
    before it - and where the ownership raster steps beside an anchor it lays
    others on the map's own side of the border (``departs_outward``) or where no
    step reaches them. The live proof walks every lane by the server's own
    rules and refused all of those. So each gate lane that is a border lane
    keeps its offset along the seam ('gate'), and each that is not hands its
    offset to the free border lane nearest it: the gate's walks still start at
    the gate. A seam whose border offers no lane at all keeps its gate as
    surveyed, where it has always worked.
    """
    report = []
    # A world with no surveyed links has no seam to widen: several contract tests
    # exercise the export against a stand-in that carries only what it reads.
    links = {link['id']: link for link in list(getattr(world, 'connections', ()))
             + list(getattr(world, 'open_border_links', ()))}
    for connection in connections:
        if connection.get('type') != 'walk' or connection['id'] in (GATED_SEAMS if gated is None else gated):
            continue
        link = links[connection['id']]
        widths = []
        for side, end in enumerate(connection['ends']):
            border = {tuple(lane['tile']): lane for lane in crossing_lanes(world, link, side, served, step)}
            gate = [lane for lane in end['lanes'] if 'gate' in lane]
            if not border:
                widths.append({'region': end['region'], 'gateLanes': len(gate), 'gateLanesMoved': 0,
                               'lanes': len(end['lanes']), 'keptSurveyedGate': bool(gate)})
                continue
            direct = [lane for lane in gate if tuple(lane['tile']) in border]
            for lane in direct:
                border[tuple(lane['tile'])]['gate'] = lane['gate']
            moved = 0
            for lane in gate:
                if tuple(lane['tile']) in border:
                    continue
                free = [key for key, candidate in border.items() if 'gate' not in candidate]
                if free:
                    key = tuple(lane['tile'])
                    nearest = min(free, key=lambda t: ((t[0] - key[0]) ** 2 + (t[1] - key[1]) ** 2, t))
                    border[nearest]['gate'] = lane['gate']
                    moved += 1
            end['lanes'] = [border[key] for key in sorted(border, key=lambda t: (t[1], t[0]))]
            reseat(world, end)
            widths.append({'region': end['region'], 'gateLanes': len(direct), 'gateLanesMoved': moved,
                           'lanes': len(border)})
        report.append({'id': connection['id'], 'ends': widths})
    return report


def open_borders(world):
    """The borders no road or boat crosses, as links a walker may cross wherever the ground allows.

    Twelve territories meet along twenty-four borders and eighteen of them were
    planned as roads. The other borders were drawn but never crossable: Grey
    Moors met Four Gates along forty metres of open moor that a walker could
    see across and not step over, and a click on the far side walked to the
    middle of that border and stopped. The owner's rule is that ground walkable
    on both sides of a border is a way across, road or no road, so each of these
    is surveyed like a road's seam - its lanes are its ground's, from both
    served grids (``crossing_lanes``) - with no gate, no road and no threshold.

    A pair a boat joins is left alone: Crownwater's shore is reached by ferry,
    and the server tells a boat from a walk by the pair of maps a portal joins,
    so a walkable border beside a ferry would turn the ferry into a walk.

    Each link's anchor is the point of its border nearest the border's middle,
    and its normal points from the first territory's centre to the second's, as
    a view-only link's does.
    """
    if not hasattr(world, 'adjacent_edges'):
        return []
    joined = {tuple(sorted(c['regions'])) for c in getattr(world, 'connections', ())}
    links = []
    for (ia, ib), segments in sorted(world.adjacent_edges().items()):
        ra, rb = world.ids[ia], world.ids[ib]
        if tuple(sorted((ra, rb))) in joined:
            continue
        segments = np.asarray(segments, dtype=float)
        middle = segments.mean(axis=(0, 1))
        start, end = segments[:, 0], segments[:, 1]
        along = np.clip(((middle - start) * (end - start)).sum(axis=1)
                        / np.maximum(((end - start) ** 2).sum(axis=1), 1e-12), 0., 1.)
        points = start + along[:, None] * (end - start)
        anchor = points[np.argmin(((points - middle) ** 2).sum(axis=1))]
        delta = np.asarray(world.centers[ib], dtype=float) - np.asarray(world.centers[ia], dtype=float)
        links.append({'id': 'border--' + ra + '--' + rb, 'type': 'walk', 'road': False,
                      'regions': [ra, rb], 'anchor': anchor.tolist(),
                      'normal': (delta / np.linalg.norm(delta)).tolist(), 'edgeSegments': segments.tolist()})
    return links


def open_border_contracts(world):
    """A walk contract for each roadless border, its lanes still to be surveyed.

    Each end starts at the border's first tile out from the anchor; the
    survey (``widen_seams``) gives it the border's lanes and seats it on the
    one nearest there.
    """
    contracts = []
    for link in world.open_border_links:
        ends = []
        for side, region in enumerate(link['regions']):
            other = link['regions'][1 - side]
            center = np.asarray(world.regions[region]['center'])
            anchor = np.asarray(link['anchor'])
            normal = np.asarray(link['normal']) * (1 if side == 0 else -1)
            frame = frame_for(world, link, region, side)
            frame['portal'] = 'border-to-' + other
            tile = tile_for(world, region, anchor + normal)
            p = global_tile(world, region, tile)
            ends.append({'region': region, 'portal': frame['portal'], 'tile': tile,
                         'arrival': tile_for(world, region, anchor - normal), 'lanes': [],
                         'position': [float(p[0] - center[0]), float(world.height_at(*p)), float(p[1] - center[1])],
                         'frame': frame, 'preloadEdges': (np.asarray(link['edgeSegments']) - center).tolist()})
        contracts.append({'id': link['id'], 'type': 'walk', 'road': False, 'ends': ends})
    return contracts


# The server's eight steps as (dy, dx), in collision_sources.STEPS order.
STEPS = ((0, 1), (1, 1), (1, 0), (1, -1), (0, -1), (-1, -1), (-1, 0), (-1, 1))


def step_bits(heights, limit):
    """Every step the server allows off each tile, as bit k of ``bits[y][x]`` for STEPS[k].

    collision_sources.walk_step_ok for the whole grid at once: both tiles
    open, a climb within the limit, and a diagonal only where both of its
    straight steps are allowed from the same tile. Nested lists, because the
    flood reads them one tile at a time.
    """
    h = np.asarray(heights, dtype=np.int16)
    rows, columns = h.shape

    def allowed(dy, dx):
        there = np.zeros_like(h)
        there[max(0, -dy):rows - max(0, dy), max(0, -dx):columns - max(0, dx)] = \
            h[max(0, dy):rows - max(0, -dy), max(0, dx):columns - max(0, -dx)]
        return (h != 0) & (there != 0) & (np.abs(there - h) <= limit)

    bits = np.zeros(h.shape, dtype=np.uint8)
    for k, (dy, dx) in enumerate(STEPS):
        mask = allowed(dy, dx)
        if dy and dx:
            mask &= allowed(dy, 0) & allowed(0, dx)
        bits |= mask.astype(np.uint8) << k
    return bits.tolist()


def flood(bits, seen, seeds, terminals):
    """Grow ``seen`` from ``seeds`` by the server's steps; a terminal is stepped onto, never off."""
    rows, columns = seen.shape
    queue = deque()
    for x, y in seeds:
        if 0 <= x < columns and 0 <= y < rows and not seen[y, x]:
            seen[y, x] = True
            queue.append((x, y))
    while queue:
        x, y = queue.popleft()
        if (x, y) in terminals:
            continue
        row = bits[y][x]
        for k, (dy, dx) in enumerate(STEPS):
            if row >> k & 1 and not seen[y + dy, x + dx]:
                seen[y + dy, x + dx] = True
                queue.append((x + dx, y + dy))


def prune_lanes(world, connections, served, hubs, limit):
    """Withdraw every lane a walker cannot get onto, or cannot step off the far end of.

    A lane is walkable ground on both sides of its border (``crossing_lanes``),
    which holds as well for a scrap of moor fenced by cliff on both maps, that
    no walker from either can reach, and for a single tile of the neighbour's
    ground with nowhere to go from it but back over the border. Both were
    published once the lanes stopped asking for a hub, and the live proof
    refused 206 of them: a crossing on ground nobody can walk to, and an
    arrival whose every first step is another crossing.

    Reach is the proof's own: from each map's hub by the server's steps, onto
    a lane and never off it (a lane fires where it is stood on), and over each
    lane that lands where a walker can take a first step that is not another
    lane - into the far map, from that landing. Withdrawing a lane changes what
    is reachable, so the survey is repeated until nothing more is withdrawn.
    Returns how many lanes were withdrawn.
    """
    walks = [c for c in connections if c.get('type') == 'walk']
    bits = {region: step_bits(entry['grid'], limit) for region, entry in served.items()}
    bounds = {region: storage_bounds(world, region) for region in served}
    withdrawn = 0
    while True:
        lanes, terminals = [], {region: set() for region in served}
        for connection in walks:
            for end, other in (connection['ends'], connection['ends'][::-1]):
                region, far = end['region'], other['region']
                if region not in served or far not in served:
                    continue
                for lane in end['lanes']:
                    tile = (int(lane['tile'][0]), int(lane['tile'][1]))
                    point = global_tile(world, region, tile)
                    cell = tuple(int(v) for v in tiles_at(world, far, point[0], point[1]))
                    tile_index, cell_index = bounds[region].index_xy(*tile), bounds[far].index_xy(*cell)
                    lanes.append((region, tile_index, far, cell_index, lane))
                    if tile_index is not None:
                        terminals[region].add(tile_index)

        def lands(region, cell):
            if cell is None:
                return False
            x, y = cell
            rows, columns = served[region]['grid'].shape
            if not (0 <= x < columns and 0 <= y < rows) or not served[region]['grid'][y, x]:
                return False
            row = bits[region][y][x]
            return any(row >> k & 1 and (x + dx, y + dy) not in terminals[region]
                       for k, (dy, dx) in enumerate(STEPS))

        landing = {(far, cell): lands(far, cell) for _, _, far, cell, _ in lanes}
        seen = {region: np.zeros(entry['grid'].shape, dtype=bool) for region, entry in served.items()}
        seeds = {region: [index] for region in served if region in hubs
                 if (index := bounds[region].index_xy(*map(int, hubs[region]))) is not None}
        while seeds:
            for region, points in seeds.items():
                flood(bits[region], seen[region], points, terminals[region])
            seeds = {}
            for region, index, far, cell, _ in lanes:
                if index is not None and seen[region][index[1], index[0]] and landing[far, cell] and not seen[far][cell[1], cell[0]]:
                    seeds.setdefault(far, []).append(cell)
        gone = {id(lane) for region, index, far, cell, lane in lanes
                if index is None or not (seen[region][index[1], index[0]] and landing[far, cell])}
        if not gone:
            return withdrawn
        withdrawn += len(gone)
        for connection in walks:
            for end in connection['ends']:
                end['lanes'] = [lane for lane in end['lanes'] if id(lane) not in gone]
                reseat(world, end)


def settle_crossings(world, publication, served, step, hubs, limit=2):
    """Open the roadless borders, then keep every lane a walker can use.

    Each roadless border (``open_borders``) is surveyed like a road's seam and
    joins the published links; a border whose two maps offer no lane either
    way - water, cliff or wall the length of it - keeps its view-only link,
    which draws the neighbour without offering a way across. Then every land
    crossing, road or roadless, keeps only the lanes a walker can get onto and
    step off (``prune_lanes``). A roadless border left without a lane either
    way is withdrawn and becomes a view again, and the survey is repeated
    without it, since it may have been the only way into ground beyond it.
    An opened border's view-only twin is withdrawn: one link per pair of
    territories. Returns the survey of the roadless borders, the identities of
    those opened and how many lanes were withdrawn.
    """
    candidates = copy.deepcopy(getattr(world, 'open_connections', []))
    report = widen_seams(world, candidates, served, step, gated=())
    opened = [c for c in candidates if all(end['lanes'] for end in c['ends'])]
    roads = [c for c in publication['connections'] if c.get('type') == 'walk']
    withdrawn = 0
    while True:
        withdrawn += prune_lanes(world, roads + opened, served, hubs, limit)
        kept = [c for c in opened if all(end['lanes'] for end in c['ends'])]
        if len(kept) == len(opened):
            break
        opened = kept
    stranded = [c['id'] for c in roads if not all(end['lanes'] for end in c['ends'])]
    if stranded:
        raise ValueError('no walker can reach or leave any lane of ' + ', '.join(stranded))
    pairs = {frozenset(end['region'] for end in c['ends']) for c in opened}
    publication['connections'].extend(opened)
    publication['visualConnections'] = [v for v in publication.get('visualConnections', [])
                                        if frozenset(end['map'] for end in v['ends']) not in pairs]
    return {'roadless': report, 'opened': [c['id'] for c in opened], 'withdrawnLanes': withdrawn}


def frame_for(world, link, region, side):
    center = np.asarray(world.regions[region]['center'])
    anchor = np.asarray(link['anchor']); normal = np.asarray(link['normal']) * (1 if side == 0 else -1)
    height = float(world.height_at(*anchor))
    other = link['regions'][1-side]
    return {'id':link['id'], 'portal':'road-to-' + other, 'destination':other,
        'anchor':[float(anchor[0]-center[0]),height,float(anchor[1]-center[1])],
        'globalAnchor':[float(anchor[0]),height,float(anchor[1])],
        'globalTranslation':[float(center[0]),0,float(center[1])],
        'outward':normal.tolist(), 'uvSign':1, 'preloadDistance':320, 'retainDistance':420,
        'blendDistance':0, 'collarDepth':2, 'halfWidthTiles':3, 'viewHalfWidth':240,
        'viewDepth':320, 'geometryMode':'continent-chunks-v1', 'sceneNodes':[]}


def ferry_arrival(world, link, region, landing):
    """Return along the actual fitted bank, inside its four-metre quay apron."""
    landing=np.asarray(landing,dtype=float)
    fits=getattr(world,'ferry_shore_report',{}).get('finalFits',[])
    matches=[fit for fit in fits if fit.get('region')==region
        and link['id'] in fit.get('connections',[])
        and np.array_equal(np.asarray(fit.get('landing'),dtype=float),landing)]
    if len(matches)!=1:
        raise ValueError(f"{link['id']}:{region}: ferry arrival needs one exact final bank fit")
    forward=np.asarray(matches[0].get('forward'),dtype=float)
    if forward.shape!=(2,) or not np.isfinite(forward).all() or abs(np.linalg.norm(forward)-1)>1e-7:
        raise ValueError(f"{link['id']}:{region}: final bank direction must be a finite unit vector")
    # Rounding the full four-metre endpoint can put part of the actor beyond
    # the deck. One metre of margin keeps all four half-cells on the apron.
    arrival=tile_for(world,region,landing-forward*3)
    if arrival==tile_for(world,region,landing):
        raise ValueError(f"{link['id']}:{region}: ferry arrival overlaps its return trigger")
    return arrival


def authored_portal(world, connection, end):
    """Keep saved marker fields; derive trigger tiles from the legal connection."""
    region = end['region']
    snapshots = getattr(world, 'authoring_snapshots', {})
    if region not in snapshots:
        return None
    document = snapshots[region].document
    identity = end['portal']
    prefix = f'{region}:{identity}: authored crossing portal'
    matches = [record for record in document['gameplay']['portals']
               if record.get('id') == identity]
    if len(matches) != 1:
        raise ValueError(f'{prefix} requires one exact source record, found {len(matches)}')
    record = matches[0]
    others = [other for other in connection['ends'] if other['region'] != region]
    if len(others) != 1:
        raise ValueError(f'{prefix} requires one destination endpoint')
    other = others[0]
    center = world.regions[region]['center']
    origin, _ = world.address(region)
    if (document.get('regionId') != region
            or document.get('coordinateSpace') != 'territory-local'
            or document.get('axes') != {'x': 'east', 'y': 'up', 'z': 'south'}
            or document.get('continentTranslation') != [center[0], 0, center[1]]
            or document.get('server', {}).get('origin') != list(origin)
            or document.get('server', {}).get('metresPerTile') != 1):
        raise ValueError(f'{prefix} source frame differs from the generated crossing')
    position = record.get('position')
    if (not isinstance(position, list) or len(position) != 3
            or not all(isinstance(v, (int, float)) and not isinstance(v, bool)
                       and np.isfinite(v) for v in position)):
        raise ValueError(f'{prefix} requires a finite local XYZ position')
    if (record.get('type') != connection['type']
            or record.get('destinationMap') != other['region']):
        raise ValueError(f'{prefix} type or destination differs from the generated crossing')
    projected = [int(np.floor(position[0] + origin[0])),
                 int(np.floor(origin[1] - position[2]))]
    if record.get('serverTile') != projected:
        raise ValueError(f'{prefix} source tile differs from its marker projection')
    for tile in (end['tile'], other['arrival']):
        if (not isinstance(tile, list) or len(tile) != 2
                or not all(isinstance(v, int) and not isinstance(v, bool) for v in tile)):
            raise ValueError(f'{prefix} requires integer derived trigger tiles')
    if connection['type'] == 'walk' and not any(
            lane['tile'] == end['tile'] for lane in end.get('lanes', [])):
        raise ValueError(f'{prefix} selected departure is not a surviving crossing lane')
    endpoint = end.get('position')
    point = global_tile(world, region, end['tile'])
    if (not isinstance(endpoint, list) or len(endpoint) != 3
            or not all(isinstance(v, (int, float)) and not isinstance(v, bool)
                       and np.isfinite(v) for v in endpoint)
            or endpoint[0] != point[0] - center[0] or endpoint[2] != point[1] - center[1]):
        raise ValueError(f'{prefix} runtime position differs from its derived trigger cell')
    # Snapshot serverTile is the marker projection, not necessarily the first
    # legal tile across a widened border. Its inherited destinationTile is not
    # the settled counterpart's arrival either. Preserve the editable marker
    # while publishing the trigger contract consumed by runtime and playtest.
    result = copy.deepcopy(record)
    result['serverTile'] = list(end['tile'])
    # Match publish_diagonal_continent.connection_rows: walking hands the actor
    # over at this same physical cell, independently of the reverse lane's
    # partner. Boats instead land at the explicit destination quay arrival.
    if connection['type'] not in ('ferry', 'ship', 'boat', 'teleport'):
        destination = list(map(int, tiles_at(world, other['region'], *point)))
        if (not storage_bounds(world, other['region']).contains(*destination)
                or not np.array_equal(global_tile(world, other['region'], destination), point)):
            raise ValueError(f'{prefix} departure has no matching destination cell')
        result['destinationTile'] = destination
    else:
        result['destinationTile'] = list(other['arrival'])
    return result


def authored_portals(world, region, connections=None):
    """Join named source markers to initial or settled connections by identity."""
    if region not in getattr(world, 'authoring_snapshots', {}):
        return {}
    if not hasattr(world, 'publication_connections'):
        raise ValueError(f'{region}: authored crossing portals require prepared connections')
    records = {}
    actual = world.publication_connections if connections is None else connections
    for original in world.publication_connections:
        if not any(end['region'] == region for end in original['ends']):
            continue
        matches = [connection for connection in actual if connection['id'] == original['id']]
        if len(matches) != 1:
            raise ValueError(f"{original['id']}: authored crossing requires one derived connection")
        connection = matches[0]
        if sorted((end['region'], end['portal']) for end in connection['ends']) != sorted(
                (end['region'], end['portal']) for end in original['ends']):
            raise ValueError(f"{original['id']}: authored crossing endpoint identities changed")
        for end in connection['ends']:
            if end['region'] != region:
                continue
            identity = end['portal']
            if identity in records:
                raise ValueError(f'{region}:{identity}: duplicate generated crossing portal')
            records[identity] = authored_portal(world, connection, end)
    return records


def prepare_contracts(world):
    """Same physical cell for departure/arrival; reverse triggers are across it."""
    connections=[]
    for link in world.connections:
        ends=[]
        for side,region in enumerate(link['regions']):
            other=link['regions'][1-side]; center=np.asarray(world.regions[region]['center'])
            if link['type']=='walk':
                anchor=np.asarray(link['anchor']);normal=np.asarray(link['normal'])*(1 if side==0 else -1)
                # A common global tangent keeps lane ordering stable on both ends.
                tangent=np.array([-link['normal'][1],link['normal'][0]])
                lanes=[]
                for offset in range(-3,4):
                    departure=tile_for(world,region,anchor+normal+offset*tangent)
                    arrival=tile_for(world,region,anchor-normal+offset*tangent)
                    # 'gate' is the lane's offset along the surveyed seam: what tells the gate's
                    # own lanes from the rest of an open border, and which of them is which.
                    lanes.append({'tile':departure,'arrival':arrival,'gate':offset})
                frame=frame_for(world,link,region,side)
                p=global_tile(world,region,lanes[3]['tile']);height=float(world.height_at(*p))
                edges=(np.asarray(link['edgeSegments'])-center).tolist()
                ends.append({'region':region,'portal':frame['portal'],**lanes[3], 'lanes':lanes,
                    'position':[float(p[0]-center[0]),height,float(p[1]-center[1])],
                    'frame':frame,'preloadEdges':edges})
            else:
                landing=np.asarray(link['landings'][side]); tile=tile_for(world,region,landing)
                p=global_tile(world,region,tile);height=float(world.height_at(*p))
                arrival=ferry_arrival(world,link,region,landing)
                ends.append({'region':region,'portal':'ferry-to-'+other,'tile':tile,'arrival':arrival,
                    'position':[float(p[0]-center[0]),height,float(p[1]-center[1])]})
        connections.append({'id':link['id'],'type':link['type'],'ends':ends})
    world.publication_connections=connections
    for region in getattr(world, 'authoring_snapshots', {}):
        authored_portals(world, region)
    existing={tuple(sorted(c['regions'])) for c in world.connections if c['type']=='walk'}
    visuals=[]
    for (ia,ib),segments in world.adjacent_edges().items():
        ra,rb=world.ids[ia],world.ids[ib]
        if tuple(sorted((ra,rb))) in existing:continue
        mid=np.asarray(segments).mean(axis=(0,1));delta=world.centers[ib]-world.centers[ia]
        normal=delta/np.linalg.norm(delta)
        link={'id':'view--'+ra+'--'+rb,'anchor':mid.tolist(),'normal':normal.tolist(),'regions':[ra,rb]}
        ends=[]
        for side,region in enumerate((ra,rb)):
            center=np.asarray(world.regions[region]['center']);frame=frame_for(world,link,region,side)
            ends.append({'map':region,'portal':'','frame':frame,'position':frame['anchor'],
                'preloadEdges':(np.asarray(segments)-center).tolist()})
        visuals.append({'id':link['id'],'seamless':True,'visualOnly':True,'ends':ends})
    world.visual_connections=visuals
    # Roadless borders are surveyed beside the roads but published only once
    # export_contracts has found their lanes (settle_open_borders); the geometry
    # stage builds no road, deck or marker for them.
    world.open_border_links=open_borders(world)
    world.open_connections=open_border_contracts(world)
    return connections


def apply_manifest(world,region,manifest):
    authored = authored_portals(world, region)
    for connection in world.publication_connections:
        end=next((e for e in connection['ends'] if e['region']==region),None)
        if end is None:continue
        other=next(e for e in connection['ends'] if e['region']!=region)
        portal=authored.get(end['portal'], {'id':end['portal'],'name':('Road to ' if connection['type']=='walk' else 'Ferry to ')+other['region'].replace('_',' ').title(),
            'position':end['position'],'serverTile':end['tile'],'destinationMap':other['region'],
            'destinationTile':other['arrival'],'type':connection['type']})
        manifest.setdefault('portals',[]).append(portal)
        if 'frame' in end:manifest.setdefault('streamingBorders',[]).append(end['frame'])
