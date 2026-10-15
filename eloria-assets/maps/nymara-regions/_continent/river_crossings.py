"""River crossing sites: the only places a road may cross a plan river, and the water and bank it may not travel.

The owner's rules (2026-09-16): a road crosses a river only on a bridge, at the locally shortest crossing, square to
the flow and at a narrow reach; several bridges on one river are allowed when they stand at least 100 m apart along
it; a road travelling in a river's direction runs parallel on the bank outside a setback, never along or over the
channel.

Cross sections. Every plan river is cut every ``sample_metres`` along its curved centreline (the curve
landscape.water_fields uses). A section's cost is its wet width square to the centreline plus an approach term: the
bank rise, between the deck (the water surface plus ``deck_clearance_metres``) and the ground ``landing_metres``
beyond each wet edge, that ``approach_grade`` cannot absorb over that landing. A section is excluded when its span or
its routed landings touch a lake or the sea, come within ``confluence_metres`` of another river's channel, cross the
rigid core of a settlement footing (``footing_weight``), cross a retained solid, come within ``seam_metres`` of a territory
seam, stand more than ``perpendicular_tolerance_degrees`` off square to the local flow, land on anything but dry
ground above the sea, or need a deck that would stand more than ``deck_lift_metres`` over its banks (deck_fit).

Candidates. A section is a candidate when its cost is within a quarter metre of the cheapest valid section within
``local_window_metres`` along its river; candidates closer than ``CANDIDATE_SPACING_METRES`` keep only the cheapest,
so a uniform reach still offers a crossing every twenty metres. A candidate whose approach term exceeds
``maximum_approach_metres`` is a last resort, offered only to a leg that finds no other way.

Authored crossings. The plan key ``authored_crossings`` names a river section (river id and metres along it) that
is a candidate although the model excludes it, when every reason is one landscape.AUTHORED_CROSSING_WAIVERS allows: a
deck that cannot sit at water level between high banks, or a retained solid beside a routed landing. It replaces the
candidates within CANDIDATE_SPACING_METRES of it and is never a last resort.

Sites are claimed by roads. The router (world_layout.World._route) treats river water and its setback as impassable
and joins the two routed landings of every available crossing with one bridge edge: each site already claimed in the
leg's territory, and each candidate there that stands ``minimum_spacing_metres`` along its river from every claimed
site. A new crossing costs ``bridge_cost_metres`` of alignment on top of its length; a site a public road (seam, ferry
or door road) already crosses costs ``shared_bridge_factor`` of that, so later roads share it. A routed road claims
the candidates it crosses; the claimed set is the continent's bridge sites, always at least the spacing apart.
"""
from __future__ import annotations

import math

import numpy as np
from scipy.ndimage import distance_transform_edt, label

import landscape as L

CELL = 2.0                      # the composed grid (world_layout.CELL); world_layout imports this module lazily
LANDING_ROUTE_METRES = 9.0      # a routed landing stands this far beyond its wet edge: outside every road's setback
SCAN_REACH_METRES = 30.0        # beyond the half width, how far a cross section looks for its wet edges
WET_DEPTH_METRES = .02          # water shallower than this is bank, not channel
CANDIDATE_TOLERANCE_METRES = .25
CANDIDATE_SPACING_METRES = 20.0
SPAN_HALF_WIDTH_METRES = 6.0    # a site's span box half width across its axis (a seam road's 4 m plus shoulder)
DECK_AXIS_GRADE = .64 / math.sqrt(2)   # bridge_export.bounded_floor's step along a grid axis, per metre


def _sample(grid, x, z, world):
    from world_layout import triangle_sample
    return triangle_sample(np.asarray(grid, float), x, z, world.x0, world.z0)


def _cell(world, x, z):
    iz = np.clip(np.rint((np.asarray(z, float) - world.z0) / CELL).astype(int), 0, world.height.shape[0] - 1)
    ix = np.clip(np.rint((np.asarray(x, float) - world.x0) / CELL).astype(int), 0, world.height.shape[1] - 1)
    return iz, ix


def policy_of(world):
    """The world's crossing policy (landscape.crossing_policy of its plan), cached on the world."""
    policy = getattr(world, 'crossing_policy', None)
    if policy is None:
        policy = L.crossing_policy(getattr(world, 'plan', {}) or {})
        world.crossing_policy = policy
    return policy


def setback_metres(policy, width):
    """How far a road of this half width keeps from river water: max(the minimum, half width + the margin)."""
    width = 1.65 if width is None else float(width)
    return max(float(policy['setback_minimum_metres']), width + float(policy['setback_margin_metres']))


def lake_mask(world, x=None, z=None, scale=1.0):
    """Points inside a plan lake's ellipse (scaled), on the composed grid by default."""
    x = world.gx if x is None else np.asarray(x, float)
    z = world.gz if z is None else np.asarray(z, float)
    inside = np.zeros(np.shape(x), bool)
    for lake in (getattr(world, 'plan', {}) or {}).get('lakes', []):
        inside |= L._ellipse_distance(x, z, lake) <= scale
    return inside


def prepare_water(world):
    """River and lake water on the composed grid, and every vertex's distance from it in metres (cached on the world).

    The router keeps roads out of this water and its setback. The sea keeps the router's own soft penalty."""
    river = np.asarray(world.water.get('river_mask', np.zeros_like(world.height, bool)), bool)
    world.river_water = river
    world.river_water_distance = distance_transform_edt(~river) * CELL if river.any() else np.full(world.height.shape, np.inf)
    return river


def water_distance_at(world, x, z):
    """Metres from river water at points (nearest composed vertex); infinite before the water is prepared."""
    grid = getattr(world, 'river_water_distance', None)
    if grid is None:
        return np.full(np.shape(np.asarray(x, float)), np.inf)
    iz, ix = _cell(world, x, z)
    return grid[iz, ix]


def seam_distance(world):
    """Metres from each composed vertex to the nearest territory seam (a change of owner between cells)."""
    cached = getattr(world, '_seam_distance', None)
    if cached is not None:
        return cached
    owner = world.owner
    boundary = np.zeros(owner.shape, bool)
    vertical = owner[:-1, :] != owner[1:, :]
    horizontal = owner[:, :-1] != owner[:, 1:]
    boundary[:-1, :] |= vertical
    boundary[1:, :] |= vertical
    boundary[:, :-1] |= horizontal
    boundary[:, 1:] |= horizontal
    cells = distance_transform_edt(~boundary) * CELL if boundary.any() else np.full(owner.shape, np.inf)
    world._seam_distance = np.pad(cells, ((0, 1), (0, 1)), mode='edge')
    return world._seam_distance


def settlement_weight(world):
    """How firmly a settlement's rigid footing (an assembly: a village, a city, a compound) holds each vertex."""
    footing = getattr(world, 'road_footing_weight', getattr(world, 'assembly_weight', None))
    return np.zeros_like(world.height) if footing is None else footing


def standing_weight(world):
    footing = getattr(world, 'road_footing_weight', getattr(world, 'assembly_weight', None))
    footing = np.zeros_like(world.height) if footing is None else footing
    foundation = np.clip(getattr(world, 'foundation_weight', np.zeros_like(world.height)), 0, 1)
    return np.maximum(footing, foundation)


def river_curve(river):
    """(arc, centre xz, unit tangent per segment, level) of a plan river's curved centreline."""
    points = L.river_points(river)
    length = np.linalg.norm(np.diff(points[:, :2], axis=0), axis=1)
    points = points[np.r_[True, length > 1e-9]]
    xz = points[:, :2]
    seg = np.diff(xz, axis=0)
    length = np.linalg.norm(seg, axis=1)
    return np.r_[0., np.cumsum(length)], xz, seg / length[:, None], points[:, 2]


def _at_arc(arc, xz, unit, s):
    k = np.clip(np.searchsorted(arc, s, side='right') - 1, 0, len(unit) - 1)
    t = np.clip((s - arc[k]) / np.maximum(arc[k + 1] - arc[k], 1e-9), 0, 1)
    return xz[k] + t[:, None] * (xz[k + 1] - xz[k]), unit[k]


def _mean_tangent(arc, unit, s, half):
    """The length-weighted mean flow direction over [s - half, s + half] along the curve."""
    mids = (arc[:-1] + arc[1:]) * .5
    lengths = np.diff(arc)
    result = np.zeros((len(s), 2))
    for i, (value, reach) in enumerate(zip(s, half)):
        near = np.abs(mids - value) <= reach
        if not near.any():
            near = np.zeros(len(mids), bool)
            near[int(np.argmin(np.abs(mids - value)))] = True
        vector = (unit[near] * lengths[near][:, None]).sum(axis=0)
        result[i] = vector / max(float(np.linalg.norm(vector)), 1e-9)
    return result


def _polyline_distance(points, xz):
    best = np.full(len(points), np.inf)
    for a, b in zip(xz[:-1], xz[1:]):
        d = b - a
        t = np.clip(((points[:, 0] - a[0]) * d[0] + (points[:, 1] - a[1]) * d[1]) / max(float(d @ d), 1e-9), 0, 1)
        best = np.minimum(best, np.hypot(points[:, 0] - a[0] - t * d[0], points[:, 1] - a[1] - t * d[1]))
    return best


def deck_fit(world, left_edge, right_edge, policy):
    """(highest lift over dry ground, lift at the landing ends) of the deck a site would carry, solved along its span
    line as bridge_export solves it on its grid: the water clearance over deep water, straight across each deep run
    between its banks, then the smallest majorant of the bridge floor grade along a grid axis (bounded_floor's
    step), over the span plus deck_landing_metres on each bank, 2.5 cm over the bed on dry ground."""
    left_edge, right_edge = np.asarray(left_edge, float), np.asarray(right_edge, float)
    axis = right_edge - left_edge
    length = float(np.linalg.norm(axis))
    if length < 1e-9:
        return 0., 0.
    unit = axis / length
    landing = float(policy['deck_landing_metres'])
    t = np.arange(-landing, length + landing + 1e-9, 1.)
    points = left_edge + unit * t[:, None]
    bed = _sample(world.height, points[:, 0], points[:, 1], world)
    depth = _sample(np.where(world.water['mask'], world.water['depth'], 0.), points[:, 0], points[:, 1], world)
    surface = _sample(world.water['surface'], points[:, 0], points[:, 1], world)
    deep = depth > .35
    lower = np.where(deep, np.maximum(bed + .025, surface + float(policy['deck_clearance_metres'])), bed + .025)
    profile = lower.copy()
    runs = np.flatnonzero(np.diff(np.r_[0, deep.astype(int), 0]))
    for a, b in zip(runs[::2], runs[1::2]):
        if a > 0 and b < len(profile):
            profile[a:b] = np.maximum(lower[a:b], np.interp(t[a:b], [t[a - 1], t[b]], [lower[a - 1], lower[b]]))
    step = DECK_AXIS_GRADE
    for i in range(1, len(profile)):
        profile[i] = max(profile[i], profile[i - 1] - step)
    for i in range(len(profile) - 2, -1, -1):
        profile[i] = max(profile[i], profile[i + 1] - step)
    # Over any water (the shallow margins too) a deck stands over the river, not over its banks.
    lift = np.where(depth > WET_DEPTH_METRES, 0., profile - bed)
    return float(lift.max()), float(max(profile[0] - bed[0], profile[-1] - bed[-1]))


def river_sections(world, river, policy):
    """One plan river's cross sections: wet edges, routed landings, cost and every exclusion that applies."""
    arc, xz, unit, _ = river_curve(river)
    s = np.arange(0., arc[-1], float(policy['sample_metres']))
    rows = []
    if not len(s):
        return rows
    centre, tangent = _at_arc(arc, xz, unit, s)
    normal = np.c_[-tangent[:, 1], tangent[:, 0]]
    width = np.asarray(L.river_field(centre[:,0],centre[:,1],river)[2],float)
    reach = float(width.max()) + SCAN_REACH_METRES
    offsets = np.arange(-reach, reach + 1e-9, .5)
    depth = np.where(world.water['mask'], world.water['depth'], 0.)
    wet = _sample(depth, centre[:, 0][:, None] + normal[:, 0][:, None] * offsets[None, :],
                  centre[:, 1][:, None] + normal[:, 1][:, None] * offsets[None, :], world) > WET_DEPTH_METRES
    middle = len(offsets) // 2
    for i in range(len(s)):
        row = {'arc': float(s[i]), 'centre': centre[i], 'normal': normal[i], 'tangent': tangent[i], 'reasons': []}
        run = wet[i]
        near_half = int(width[i] * 2)
        first = max(0, middle - near_half)
        near = np.flatnonzero(run[first:middle + near_half + 1])
        if not len(near):
            row['reasons'].append('dry centreline')
            rows.append(row)
            continue
        seed = first + int(near[np.argmin(np.abs(near + first - middle))])
        lo = seed
        while lo > 0 and run[lo - 1]:
            lo -= 1
        hi = seed
        while hi < len(run) - 1 and run[hi + 1]:
            hi += 1
        if lo == 0 or hi == len(run) - 1:
            row['reasons'].append('wet beyond the scan')
        row['edges'] = (float(offsets[lo] - .25), float(offsets[hi] + .25))
        row['wetWidth'] = row['edges'][1] - row['edges'][0]
        rows.append(row)
    valid = [r for r in rows if 'edges' in r]
    if not valid:
        return rows
    centres = np.array([r['centre'] for r in valid])
    normals = np.array([r['normal'] for r in valid])
    edges = np.array([r['edges'] for r in valid])
    route_left = centres + normals * (edges[:, 0] - LANDING_ROUTE_METRES)[:, None]
    route_right = centres + normals * (edges[:, 1] + LANDING_ROUTE_METRES)[:, None]
    wet_left = centres + normals * edges[:, 0][:, None]
    wet_right = centres + normals * edges[:, 1][:, None]
    landing = float(policy['landing_metres'])
    approach_left = centres + normals * (edges[:, 0] - landing)[:, None]
    approach_right = centres + normals * (edges[:, 1] + landing)[:, None]
    surface = _sample(world.water['surface'], centres[:, 0], centres[:, 1], world)
    deck = surface + float(policy['deck_clearance_metres'])
    bank_left = _sample(world.height, approach_left[:, 0], approach_left[:, 1], world)
    bank_right = _sample(world.height, approach_right[:, 0], approach_right[:, 1], world)
    absorbed = float(policy['approach_grade']) * landing
    approach = np.maximum(0., np.abs(bank_left - deck) - absorbed) + np.maximum(0., np.abs(bank_right - deck) - absorbed)
    count = int(math.ceil(float((edges[:, 1] - edges[:, 0]).max()) + 2 * LANDING_ROUTE_METRES)) + 1
    fractions = np.linspace(0., 1., max(count, 2))
    line_x = route_left[:, 0][:, None] + (route_right[:, 0] - route_left[:, 0])[:, None] * fractions[None, :]
    line_z = route_left[:, 1][:, None] + (route_right[:, 1] - route_left[:, 1])[:, None] * fractions[None, :]
    iz, ix = _cell(world, line_x, line_z)
    lakes = lake_mask(world, line_x, line_z, 1.15).any(axis=1)
    sea = np.asarray(world.water.get('sea_mask', np.zeros_like(world.height, bool)), bool)[iz, ix].any(axis=1)
    solids = getattr(world, 'solids', None)
    solid = solids[iz, ix].any(axis=1) if solids is not None else np.zeros(len(valid), bool)
    footing = _sample(settlement_weight(world), line_x, line_z, world).max(axis=1) >= float(policy['footing_weight'])
    owners = np.asarray(world.owner_at(line_x, line_z))
    # Two reasons, not one. Standing near a seam is a preference - a bridge belongs to the territory that exports it,
    # and one built at the boundary serves two hubs badly - so an authored crossing may waive it. A span whose own
    # line lies in two territories (or in none) is not a preference: each territory exports only its own geometry, so
    # such a deck would be built in halves. That one no authored crossing may waive.
    seams = seam_distance(world)[iz, ix].min(axis=1) < float(policy['seam_metres'])
    split = ~np.all(owners == owners[:, :1], axis=1) | (owners[:, 0] < 0)
    confluence = np.zeros(len(valid), bool)
    for other in world.plan.get('rivers', []):
        if other.get('id') == river.get('id'):
            continue
        reach_other = float(other['width']) + float(policy['confluence_metres'])
        other_xz = river_curve(other)[1]
        for points in (wet_left, wet_right, centres):
            confluence |= _polyline_distance(points, other_xz) <= reach_other
    ends = np.r_[route_left, route_right, approach_left, approach_right]
    wet_landing = world.water['mask'][_cell(world, ends[:, 0], ends[:, 1])].reshape(4, len(valid)).any(axis=0)
    # The routed landings stand outside every road's setback (the widest road's, a seam road's 4 m half width).
    widest = setback_metres(policy, 4.)
    wet_landing |= (water_distance_at(world, ends[:, 0], ends[:, 1]).reshape(4, len(valid))[:2] <= widest).any(axis=0)
    low_landing = _sample(world.height, ends[:, 0], ends[:, 1], world).reshape(4, len(valid)).min(axis=0) < float(world.plan.get('sea_level', 0.)) + .3
    flow = _mean_tangent(arc, unit, np.array([r['arc'] for r in valid]), (edges[:, 1] - edges[:, 0]) * .5 + 6.)
    off_square = np.degrees(np.arcsin(np.clip(np.abs(np.sum(flow * normals, axis=1)), 0, 1)))
    lift_limit = float(policy['deck_lift_metres']) + .025
    for k, row in enumerate(valid):
        misfit = False
        if not row['reasons'] and not (lakes[k] or sea[k] or solid[k] or footing[k] or seams[k] or split[k] or confluence[k] or wet_landing[k] or low_landing[k]):
            dry_lift, end_lift = deck_fit(world, wet_left[k], wet_right[k], policy)
            misfit = dry_lift > lift_limit or end_lift > .12
            row['deckLift'] = round(dry_lift, 3)
        row.update(routeLandings=[route_left[k].tolist(), route_right[k].tolist()], wetEdges=[wet_left[k].tolist(), wet_right[k].tolist()],
                   surface=float(surface[k]), deckLevel=float(deck[k]), bankHeights=[float(bank_left[k]), float(bank_right[k])],
                   approach=float(approach[k]), cost=float(row['wetWidth'] + approach[k]), deviationDegrees=float(off_square[k]),
                   region=int(owners[k, 0]))
        for flag, reason in ((lakes[k], 'lake'), (sea[k], 'sea'), (solid[k], 'retained solid'), (footing[k], 'footing'),
                             (seams[k], 'territory seam'), (split[k], 'two territories'), (confluence[k], 'confluence'), (wet_landing[k], 'wet landing'),
                             (low_landing[k], 'landing at sea level'), (misfit, 'deck lifts over its banks'),
                             (off_square[k] > float(policy['perpendicular_tolerance_degrees']), 'oblique to the flow')):
            if flag:
                row['reasons'].append(reason)
    return rows


def local_minima(rows, policy):
    """Valid sections within a quarter metre of the cheapest valid section within the local window, thinned so that
    candidates closer than CANDIDATE_SPACING_METRES keep only the cheapest (then the first along the river)."""
    window = float(policy['local_window_metres'])
    valid = [r for r in rows if 'cost' in r and not r['reasons']]
    if not valid:
        return []
    arcs = np.array([r['arc'] for r in valid])
    costs = np.array([r['cost'] for r in valid])
    minima = [i for i in range(len(valid))
              if costs[i] <= costs[np.abs(arcs - arcs[i]) <= window].min() + CANDIDATE_TOLERANCE_METRES]
    chosen = []
    for i in sorted(minima, key=lambda i: (costs[i], arcs[i])):
        if all(abs(arcs[i] - arcs[j]) >= CANDIDATE_SPACING_METRES for j in chosen):
            chosen.append(i)
    return [valid[i] for i in sorted(chosen, key=lambda i: arcs[i])]


def authored_sections(world, river, rows, policy):
    """The sections the plan authors as crossings of this river (plan key "authored_crossings"): for each entry the
    measured section nearest its arc, with the reasons it would otherwise be excluded kept as "waived". Refuses an
    entry with no measured section within two samples of its arc, or with a reason no authored crossing may waive."""
    chosen = []
    for entry in (world.plan.get('authored_crossings') or []):
        if entry['river'] != river['id']:
            continue
        label = f"authored crossing {river['id']}@{float(entry['arcMetres']):g}"
        measured = [row for row in rows if 'cost' in row]
        row = min(measured, key=lambda r: abs(r['arc'] - float(entry['arcMetres'])), default=None)
        if row is None or abs(row['arc'] - float(entry['arcMetres'])) > 2 * float(policy['sample_metres']):
            raise ValueError(f'{label}: no measured cross section there (dry centreline or water beyond the scan)')
        refused = [reason for reason in row['reasons'] if reason not in L.AUTHORED_CROSSING_WAIVERS]
        if refused:
            raise ValueError(f"{label}: {', '.join(refused)} cannot be waived")
        chosen.append(dict(row, reasons=[], waived=list(row['reasons']), note=entry['note']))
    return chosen


def crossing_candidates(world, policy=None):
    """Every river's candidate crossings, cheapest first."""
    policy = policy or policy_of(world)
    problems = L.validate_authored_crossings(world.plan)
    if problems:
        raise ValueError('; '.join(problems))
    candidates = []
    for order, river in enumerate(world.plan.get('rivers', [])):
        rows = river_sections(world, river, policy)
        authored = authored_sections(world, river, rows, policy)
        chosen = [row for row in local_minima(rows, policy)
                  if all(abs(row['arc'] - own['arc']) >= CANDIDATE_SPACING_METRES for own in authored)]
        for row in sorted(chosen + authored, key=lambda r: r['arc']):
            candidates.append({'key': f"{river['id']}@{row['arc']:.0f}", 'river': river['id'], 'riverName': river.get('name', river['id']),
                               'riverOrder': order, 'region': world.ids[row['region']], 'arcMetres': round(row['arc'], 2),
                               'centre': [float(v) for v in row['centre']], 'normal': [float(v) for v in row['normal']],
                               'tangent': [float(v) for v in row['tangent']], 'edges': [float(v) for v in row['edges']],
                               'wetWidthMetres': round(row['wetWidth'], 2), 'approachMetres': round(row['approach'], 2),
                               'cost': round(row['cost'], 3), 'surface': row['surface'], 'deckLevel': row['deckLevel'],
                               'bankHeights': row['bankHeights'], 'deviationDegrees': round(row['deviationDegrees'], 2),
                               'routeLandings': row['routeLandings'], 'wetEdges': row['wetEdges'],
                               'lastResort': bool(row['approach'] > float(policy['maximum_approach_metres'])) and 'waived' not in row,
                               'authored': 'waived' in row, 'waived': row.get('waived', [])})
    candidates.sort(key=lambda c: (c['cost'], c['riverOrder'], c['arcMetres']))
    return candidates


def spaced(candidate, sites, policy):
    """Whether a crossing keeps the minimum spacing along its river from every site (itself excepted).

    The spacing is a rule for the crossings the model sites itself: rivers should be bridged where a road needs them
    and not every hundred metres. A crossing the plan authors is a decision already taken - a gate is to have its
    bridge whatever stands upstream - so it keeps its place, and so does a site beside it."""
    spacing = float(policy['minimum_spacing_metres'])
    if candidate.get('authored'):
        return True
    return all(site['key'] == candidate['key'] or site['river'] != candidate['river'] or site.get('authored')
               or abs(site['arcMetres'] - candidate['arcMetres']) >= spacing - 1e-9 for site in sites)


def prepare_river_crossings(world):
    """River water, its distance field and the candidate crossings, before any road is routed (after the solids are
    registered where they stand and the footings have settled)."""
    policy = policy_of(world)
    prepare_water(world)
    world._seam_distance = None
    world.__dict__.pop('_bank_labels', None)
    world.crossing_candidates = crossing_candidates(world, policy)
    world.crossing_sites = []
    world.crossing_site_use = {}
    world.crossing_site_roads = {}
    world.crossing_version = getattr(world, 'crossing_version', 0) + 1
    world.river_crossings = {'policy': policy, 'candidates': len(world.crossing_candidates),
                             'lastResortCandidates': sum(1 for c in world.crossing_candidates if c['lastResort']),
                             'lastResortClaims': [], 'unroutedLegs': [],
                             'rule': 'Roads cross plan rivers only at claimed sites; river water and its setback are impassable elsewhere.'}
    return world.river_crossings


def available_crossings(world, region, last_resort=False):
    """The crossings a leg in ``region`` may use: its claimed sites, and every candidate there that keeps the spacing."""
    if not getattr(world, 'crossing_candidates', None) and not getattr(world, 'crossing_sites', None):
        return []
    policy = policy_of(world)
    sites = world.crossing_sites
    claimed = {site['key'] for site in sites}
    result = [site for site in sites if region is None or site['region'] == region]
    for candidate in world.crossing_candidates:
        if candidate['key'] in claimed or (region is not None and candidate['region'] != region):
            continue
        if candidate['lastResort'] and not last_resort:
            continue
        if spaced(candidate, sites, policy):
            result.append(candidate)
    return result


def crossing_cost(world, crossing):
    """Alignment metres a bridge edge adds on top of its own length."""
    policy = policy_of(world)
    base = float(policy['bridge_cost_metres'])
    site = next((s for s in world.crossing_sites if s['key'] == crossing['key']), None)
    if site is not None and world.crossing_site_use.get(site['id'], 0) > 0:
        return base * float(policy['shared_bridge_factor'])
    return base


def claim(world, keys, road, public):
    """Make the crossings a routed road uses into sites (keeping the spacing) and record the road's use of them."""
    policy = policy_of(world)
    ids = []
    by_key = {c['key']: c for c in world.crossing_candidates}
    for key in keys:
        site = next((s for s in world.crossing_sites if s['key'] == key), None)
        if site is None:
            candidate = by_key[key]
            if not spaced(candidate, world.crossing_sites, policy):
                raise ValueError(f'{road}: crossing {key} stands within {policy["minimum_spacing_metres"]:g} m of a claimed site on {candidate["river"]}')
            site = dict(candidate, id=len(world.crossing_sites))
            world.crossing_sites.append(site)
            world.crossing_version = getattr(world, 'crossing_version', 0) + 1
            if site['lastResort']:
                world.river_crossings['lastResortClaims'].append({'site': site['id'], 'key': key, 'road': road})
        ids.append(site['id'])
        world.crossing_site_roads.setdefault(site['id'], set()).add(road)
        if public:
            world.crossing_site_use[site['id']] = world.crossing_site_use.get(site['id'], 0) + 1
    return ids


def within_spacing(world, keys):
    """Keys of every unclaimed candidate within the minimum spacing of one of ``keys`` on the same river."""
    policy = policy_of(world)
    spacing = float(policy['minimum_spacing_metres'])
    by_key = {c['key']: c for c in world.crossing_candidates}
    by_key.update({s['key']: s for s in world.crossing_sites})
    anchors = [by_key[key] for key in keys if key in by_key]
    return {c['key'] for c in world.crossing_candidates
            if any(c['key'] != a['key'] and c['river'] == a['river'] and abs(c['arcMetres'] - a['arcMetres']) < spacing for a in anchors)}


def snapshot_claims(world):
    """What a road about to be routed may change: the claimed sites, their use, and the routing records."""
    return (len(getattr(world, 'crossing_sites', [])), dict(getattr(world, 'crossing_site_use', {})),
            {key: set(value) for key, value in getattr(world, 'crossing_site_roads', {}).items()},
            len(getattr(world, 'routing', [])), len(getattr(world, 'river_crossings', {}).get('lastResortClaims', [])))


def restore_claims(world, snapshot):
    """Undo the claims (and routing records) of a road that was not built after all."""
    sites, use, roads, routing, last = snapshot
    if hasattr(world, 'crossing_sites'):
        del world.crossing_sites[sites:]
        world.crossing_site_use = use
        world.crossing_site_roads = roads
        world.crossing_version = getattr(world, 'crossing_version', 0) + 1
    if hasattr(world, 'routing'):
        del world.routing[routing:]
    if hasattr(world, 'river_crossings'):
        del world.river_crossings['lastResortClaims'][last:]


def conflicting(world, keys):
    """Unclaimed crossings in ``keys`` that fall within the spacing of an earlier one in the same list (or of a site)."""
    policy = policy_of(world)
    by_key = {c['key']: c for c in world.crossing_candidates}
    taken = list(world.crossing_sites)
    bad = []
    for key in keys:
        crossing = next((s for s in taken if s['key'] == key), None) or by_key.get(key)
        if crossing is None:
            continue
        if not spaced(crossing, taken, policy):
            bad.append(key)
        elif all(s['key'] != key for s in taken):
            taken.append(crossing)
    return bad


def box_of(crossing, pad=0., half=SPAN_HALF_WIDTH_METRES):
    a = np.asarray(crossing['routeLandings'][0], float)
    b = np.asarray(crossing['routeLandings'][1], float)
    axis = b - a
    length = float(np.linalg.norm(axis))
    return a, axis / max(length, 1e-9), length, half + pad, pad


def on_span(world, points, pad=2., sites=None):
    """Whether each xz point stands on a claimed site's span or routed landings (plus ``pad``)."""
    points = np.asarray(points, float).reshape(-1, 2)
    result = np.zeros(len(points), bool)
    for site in (world.crossing_sites if sites is None else sites):
        origin, axis, length, half, pad_ = box_of(site, pad)
        rel = points - origin
        along = rel @ axis
        across = rel @ np.array([-axis[1], axis[0]])
        result |= (along >= -pad_) & (along <= length + pad_) & (np.abs(across) <= half)
    return result


def bank_labels(world, region):
    """Connected dry land of one territory (8-connected, river water removed), cached per territory."""
    cache = world.__dict__.setdefault('_bank_labels', {})
    if region not in cache:
        owned = np.pad(world.owner == world.ids.index(region), ((0, 1), (0, 1)), mode='edge')
        river = getattr(world, 'river_water', None)
        land = owned & ~river if river is not None else owned
        cache[region] = label(land, structure=np.ones((3, 3)))[0]
    return cache[region]


def bank_of(world, region, points):
    """The dry-land component under each xz point (0 in river water or outside the territory)."""
    points = np.asarray(points, float).reshape(-1, 2)
    return bank_labels(world, region)[_cell(world, points[:, 0], points[:, 1])]


def branch_start(world, region, stations, end, width=None, toward=None):
    """(start, gap): the road station a branch or trail to ``end`` starts from. Only stations of the territory count;
    of those, dry ones outside the branch's river setback and off every bridge span, and of those the ones on the
    end's own bank (the same dry land, no river between), when any exist. ``toward`` (the portal a pinned end
    serves) keeps the stations on the pin's side of it. The nearest remaining station wins; (None, inf) without one."""
    stations = np.asarray(stations, float).reshape(-1, 2)
    end = np.asarray(end, float)
    candidates = stations[np.asarray(world.owner_at(stations[:, 0], stations[:, 1])) == world.ids.index(region)] if len(stations) else stations
    if not len(candidates):
        return None, np.inf
    if getattr(world, 'river_water_distance', None) is not None:
        dry = (water_distance_at(world, candidates[:, 0], candidates[:, 1]) > setback_metres(policy_of(world), width)) & ~on_span(world, candidates)
        if dry.any():
            candidates = candidates[dry]
        bank = int(bank_of(world, region, end)[0])
        if bank:
            same = bank_of(world, region, candidates) == bank
            if same.any():
                candidates = candidates[same]
    if toward is not None:
        toward = np.asarray(toward, float)
        side = (candidates - toward) @ (end - toward) > 0
        if side.any():
            candidates = candidates[side]
    gaps = np.linalg.norm(candidates - end, axis=1)
    nearest = int(np.argmin(gaps))
    return candidates[nearest], float(gaps[nearest])


def dry_end(world, point, width=None, region=None, reach=12.):
    """(end, moved): a road end on dry ground outside its setback. The point itself when it already stands there,
    else the nearest such ground within ``reach`` in its territory, else the point unchanged (moved False)."""
    point = np.asarray(point, float)
    if getattr(world, 'river_water_distance', None) is None:
        return point, False
    setback = setback_metres(policy_of(world), width)
    if float(water_distance_at(world, point[0], point[1])) > setback:
        return point, False
    region_id = world.ids.index(region) if region is not None else None
    for radius in np.arange(1., reach + 1e-9, 1.):
        angles = np.linspace(0, 2 * math.pi, 32, endpoint=False)
        candidates = point + radius * np.c_[np.cos(angles), np.sin(angles)]
        inside = (candidates[:, 0] >= world.x0) & (candidates[:, 0] <= world.x1) & (candidates[:, 1] >= world.z0) & (candidates[:, 1] <= world.z1)
        dry = water_distance_at(world, candidates[:, 0], candidates[:, 1]) > setback
        owned = np.asarray(world.owner_at(candidates[:, 0], candidates[:, 1])) == region_id if region_id is not None else True
        good = np.flatnonzero(inside & dry & owned)
        if len(good):
            return candidates[good[0]], True
    return point, False


def crossing_report(world):
    """The composition's record of the claimed sites and the roads that cross them."""
    sites = []
    for site in getattr(world, 'crossing_sites', []):
        sites.append({key: site[key] for key in ('id', 'key', 'river', 'riverName', 'region', 'arcMetres', 'centre', 'normal', 'edges',
                                                 'wetWidthMetres', 'approachMetres', 'cost', 'deckLevel', 'deviationDegrees',
                                                 'routeLandings', 'wetEdges', 'lastResort')}
                     | {'authored': bool(site.get('authored', False)), 'waived': list(site.get('waived', []))}
                     | {'publicRoads': int(world.crossing_site_use.get(site['id'], 0)),
                        'roads': sorted(world.crossing_site_roads.get(site['id'], []))})
    report = {key: value for key, value in getattr(world, 'river_crossings', {}).items()}
    report['sites'] = sites
    return report
