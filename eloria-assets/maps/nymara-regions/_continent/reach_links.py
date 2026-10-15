"""Reach links: authored ground written onto the finished composition so the served walk grid joins its areas.

The seventeenth contracts run (2026-09-17) refused placements that bands of ground steeper than the walkable .65
grade cut off from their territory's arrival. A plan terrain edit cannot link them reliably: it applies before the
foundations and the roads, so a road that re-routes onto the gentle ground it makes, or a footing feather, grades it
again. A reach link is the same authored shape as a terrain edit (landscape's ramp, flatten, raise or lower, with its
feather and strength), listed under the plan's "reach_links", and applied once the roads are settled and the support
stages have finished the ground: nothing after it moves the ground but the road heights refreshed onto it and the
placements regrounded on it. It never reaches a river's centreline (the carved beds and the bridge banks stay as the
drainage made them) and never moves the ground under a rigid compound's member by more than a quarter metre (reground
does not move compound members; a tree member's ground is the three metres round its trunk, not its canopy's box).
Outside the links' bands the linked ground is smoothed (smooth_link_change): no two neighbouring 2 m cells differ by
more than WALL_METRES, or than the ground before did, so a deep cut or fill on a steep face ends as a broader terrace.
The smoothing moves only ground too steep to walk: every corner of a walkable triangle keeps its linked height.
"""
from __future__ import annotations

import numpy as np

import landscape as L

PLAN_KEY = 'reach_links'


def links(plan):
    return list(plan.get(PLAN_KEY) or [])


def validate_reach_links(plan):
    """Every problem with the plan's reach links, in the terrain edit validator's words; empty means valid."""
    value = plan.get(PLAN_KEY)
    if value is None:
        return []
    if not isinstance(value, list):
        return [f"'{PLAN_KEY}' must be a list of links"]
    problems = L.validate_terrain_edits({'terrain_edits': value, 'bounds': plan.get('bounds')})
    return [problem.replace('terrain edit', 'reach link') for problem in problems]


def river_contacts(plan, link):
    """(river id, largest weight) for every plan river whose centreline the link's weight reaches."""
    contacts = []
    for river in plan.get('rivers') or []:
        if len(river.get('points') or []) < 2:
            continue
        # The channel's own centreline: the plan's Catmull-Rom curve, sampled at a metre or finer.
        curve = np.asarray(L.river_points(river), dtype=float)[:, :2]
        points = [curve[:1]]
        for a, b in zip(curve[:-1], curve[1:]):
            count = max(1, int(np.ceil(np.linalg.norm(b - a))))
            points.append(a + (b - a) * (np.arange(1, count + 1)[:, None] / count))
        points = np.vstack(points)
        weight = np.asarray(L._edit_weight(points[:, 0], points[:, 1], link), dtype=float)
        if (weight > 0).any():
            contacts.append((river.get('id'), float(weight.max())))
    return contacts


COMPOUND_TOLERANCE_METRES = .25   # the ground under a rigid compound member may move this little, as a seat settles
TRUNK_RADIUS_METRES = 3.          # a tree member's ground: this far round its pivot, not its canopy's box
# Compound members that stand on no ground of their own: the canopy walkways and platforms hang between trees
# (assemblies.supports_ground names them too). Their boxes span tens of metres of ground they never touch.
ELEVATED_MEMBER_PREFIXES = ('landmark_canopyplatform', 'landmark_canopywalkway')


def trunk_pivot(obj):
    """Where a tree member meets the ground: its source pivot carried by its shift, else its box centre."""
    if obj.get('sourcePivot') is not None and obj.get('shift') is not None:
        return np.asarray(obj['sourcePivot'], dtype=float) + np.asarray(obj['shift'], dtype=float)
    return (np.asarray(obj['low'], dtype=float) + np.asarray(obj['high'], dtype=float)) * .5


def compound_contacts(world, content, change):
    """(region, node, metres) of rigid compound members over whose footprint the ground ``change`` (a composed-grid
    array of metres) exceeds COMPOUND_TOLERANCE_METRES: reground does not move a compound member with its ground."""
    if content is None:
        return []
    found = []
    for obj in getattr(content, 'objects', []):
        if not obj.get('assembly') or str(obj.get('node', '')).lower().startswith(ELEVATED_MEMBER_PREFIXES):
            continue
        low, high = np.asarray(obj['low'], dtype=float), np.asarray(obj['high'], dtype=float)
        if obj.get('kind') == 'tree':
            # A tree stands on its trunk: its box is the canopy's, metres wider than the ground it touches.
            pivot = trunk_pivot(obj)
            low = np.array([pivot[0] - TRUNK_RADIUS_METRES, 0., pivot[2] - TRUNK_RADIUS_METRES])
            high = np.array([pivot[0] + TRUNK_RADIUS_METRES, 0., pivot[2] + TRUNK_RADIUS_METRES])
        under = (world.gx >= low[0] - 1.) & (world.gx <= high[0] + 1.) & (world.gz >= low[2] - 1.) & (world.gz <= high[2] + 1.)
        if not under.any():
            continue
        moved = float(np.max(change[under]))
        if moved > COMPOUND_TOLERANCE_METRES:
            found.append((obj.get('region'), obj.get('node'), round(moved, 3)))
    return found


WALL_METRES = 4.   # outside a link's band no two neighbouring 2 m cells differ by more than this, or than the natural ground did
CATCH_UP_METRES = 1.   # plus this: where the natural ground is steeper, a cut or fill still closes on it by a metre a cell
# A triangle of the linked ground this gentle may carry served walking (collision_export.MAX_GRADE is .65, and a
# margin): the smoothing never moves its corners, so it cannot take walkable ground or a connection away.
WALKABLE_GRADE = .7
WALL_GROWTH = 1.5   # where the fixed ground leaves no room for WALL_METRES, each further pass allows half again
WALL_PASSES = 9     # 4 m up to about 100 m; a cell no pass can place keeps the linked ground


def _walk_corners(height, cell, grade=WALKABLE_GRADE):
    """Grid nodes that are corners of a triangle no steeper than ``grade``, on the composed grid's own triangulation
    (collision_export.terrain_grade: each cell splits into its (a, b, c) and (b, c, d) triangles)."""
    height = np.asarray(height, dtype=float)
    a, b = height[:-1, :-1], height[:-1, 1:]
    c, d = height[1:, :-1], height[1:, 1:]
    lower = np.hypot(b - a, c - a) / cell <= grade
    upper = np.hypot(d - c, d - b) / cell <= grade
    corners = np.zeros(height.shape, bool)
    corners[:-1, :-1] |= lower
    corners[:-1, 1:] |= lower | upper
    corners[1:, :-1] |= lower | upper
    corners[1:, 1:] |= upper
    return corners


def _river_cells(plan, x0, z0, cell, shape):
    """Composed-grid cells every river centreline passes through (the channel keeps the drainage's ground)."""
    mask = np.zeros(shape, bool)
    for river in plan.get('rivers') or []:
        if len(river.get('points') or []) < 2:
            continue
        curve = np.asarray(L.river_points(river), dtype=float)[:, :2]
        for a, b in zip(curve[:-1], curve[1:]):
            count = max(1, int(np.ceil(np.linalg.norm(b - a) / (cell * .5))))
            points = a + (b - a) * (np.arange(count + 1)[:, None] / count)
            iz = np.rint((points[:, 1] - z0) / cell).astype(int); ix = np.rint((points[:, 0] - x0) / cell).astype(int)
            keep = (iz >= 0) & (ix >= 0) & (iz < shape[0]) & (ix < shape[1])
            mask[iz[keep], ix[keep]] = True
    return mask


def _compound_cells(gx, gz, content):
    """Composed-grid cells under rigid compound members (a tree member: round its trunk), one metre wider."""
    mask = np.zeros(gx.shape, bool)
    for obj in getattr(content, 'objects', []) if content is not None else []:
        if not obj.get('assembly') or str(obj.get('node', '')).lower().startswith(ELEVATED_MEMBER_PREFIXES):
            continue
        low, high = np.asarray(obj['low'], dtype=float), np.asarray(obj['high'], dtype=float)
        if obj.get('kind') == 'tree':
            pivot = trunk_pivot(obj)
            low = np.array([pivot[0] - TRUNK_RADIUS_METRES, 0., pivot[2] - TRUNK_RADIUS_METRES])
            high = np.array([pivot[0] + TRUNK_RADIUS_METRES, 0., pivot[2] + TRUNK_RADIUS_METRES])
        mask |= (gx >= low[0] - 1.) & (gx <= high[0] + 1.) & (gz >= low[2] - 1.) & (gz <= high[2] + 1.)
    return mask


def _envelope(values, wall_x, wall_z, upper):
    """Step-bounded envelope on the composed grid: the largest field under ``values`` (upper=True) or the smallest
    over it whose neighbouring cells differ by at most ``wall_x`` (between columns) and ``wall_z`` (between rows)."""
    value = np.asarray(values, dtype=float).copy()
    for _ in range(sum(value.shape)):
        new = value.copy()
        if upper:
            new[:, 1:] = np.minimum(new[:, 1:], value[:, :-1] + wall_x); new[:, :-1] = np.minimum(new[:, :-1], value[:, 1:] + wall_x)
            new[1:, :] = np.minimum(new[1:, :], value[:-1, :] + wall_z); new[:-1, :] = np.minimum(new[:-1, :], value[1:, :] + wall_z)
        else:
            new[:, 1:] = np.maximum(new[:, 1:], value[:, :-1] - wall_x); new[:, :-1] = np.maximum(new[:, :-1], value[:, 1:] - wall_x)
            new[1:, :] = np.maximum(new[1:, :], value[:-1, :] - wall_z); new[:-1, :] = np.maximum(new[:-1, :], value[1:, :] - wall_z)
        if np.array_equal(new, value):
            break
        value = new
    return value


def smooth_link_change(gx, gz, before, after, links, plan, content=None, wall=WALL_METRES):
    """(ground, report): the linked ground with no new walls. Outside the links' bands, neighbouring 2 m cells may
    differ by at most ``wall`` metres, or by what the ground before the links did plus CATCH_UP_METRES where it was
    steeper. A band keeps its surface exactly, and so does every corner of a walkable triangle (_walk_corners): the
    smoothing reshapes only ground too steep to walk, so it never takes a walkable cell or a connection away. River
    centreline cells and the ground under rigid compound members keep the ground before the links; a deeper cut or
    fill is carried outward through the steep ground, so it ends as a broader terrace instead of a wall. Where the
    fixed ground leaves no room for ``wall`` (a hairpin's crowded legs), the wall grows by half again pass by pass
    (WALL_GROWTH, WALL_PASSES), so the fall is shared out as evenly as the fixed ground allows; a step between two
    fixed cells stays as the links made it. The report counts the widened and relaxed cells and the walls left."""
    from scipy.ndimage import binary_dilation, find_objects, label
    before = np.asarray(before, dtype=float); after = np.asarray(after, dtype=float)
    report = {'wallMetres': wall, 'widenedCells': 0, 'relaxedCells': 0, 'unplacedCells': 0, 'wallsLeft': 0,
              'tallestWallLeftMetres': 0.}
    touched = np.abs(after - before) > 1e-6
    if not touched.any():
        return after.copy(), report
    cell = float(gx[0, 1] - gx[0, 0]); x0, z0 = float(gx[0, 0]), float(gz[0, 0])
    core = np.zeros(gx.shape, bool)
    for link in links:
        core |= np.asarray(L._edit_weight(gx, gz, link), dtype=float) >= .999 * float(link.get('strength', 1.))
    margin = int(np.ceil(float(np.abs(after - before).max()) / CATCH_UP_METRES)) + 3
    groups, _ = label(binary_dilation(touched | core, iterations=margin))
    anchors = None
    walk = _walk_corners(after, cell)
    result = after.copy()
    for window in find_objects(groups):
        if window is None:
            continue
        if anchors is None:
            anchors = _river_cells(plan, x0, z0, cell, gx.shape) | _compound_cells(gx, gz, content)
        h0, h1, k = before[window], after[window], core[window]
        anchored = anchors[window] & ~k & ~walk[window]
        placed = k | walk[window] | anchored
        smoothed = np.where(anchored, h0, h1)
        natural_x = np.abs(np.diff(h0, axis=1)) + CATCH_UP_METRES
        natural_z = np.abs(np.diff(h0, axis=0)) + CATCH_UP_METRES
        for step in range(WALL_PASSES):
            limit = wall * WALL_GROWTH ** step
            wall_x, wall_z = np.maximum(limit, natural_x), np.maximum(limit, natural_z)
            # The linked ground made wall-bounded on its own (the mean of its smallest majorant and largest minorant),
            # held between the cones of the placed cells: min and max of wall-bounded fields stay wall-bounded, so
            # every cell a pass places keeps its wall to its neighbours placed by that pass or before it.
            regular = .5 * (_envelope(h1, wall_x, wall_z, False) + _envelope(h1, wall_x, wall_z, True))
            upper = _envelope(np.where(placed, smoothed, np.inf), wall_x, wall_z, True)
            lower = _envelope(np.where(placed, smoothed, -np.inf), wall_x, wall_z, False)
            room = ~placed & (lower <= upper + 1e-9)
            smoothed = np.where(room, np.clip(regular, lower, upper), smoothed)
            if step:
                report['relaxedCells'] += int(np.count_nonzero(room & (np.abs(smoothed - h1) > .01)))
            placed |= room
            if placed.all():
                break
        report['unplacedCells'] += int(np.count_nonzero(~placed))
        report['widenedCells'] += int(np.count_nonzero(np.abs(smoothed - h1) > .01))
        for axis, natural in ((1, natural_x), (0, natural_z)):
            steps = np.abs(np.diff(smoothed, axis=axis))
            free = ~(k[:, 1:] & k[:, :-1]) if axis == 1 else ~(k[1:, :] & k[:-1, :])   # a band's own steps are its surface
            left = free & (steps > np.maximum(wall, natural) + .01)
            report['wallsLeft'] += int(np.count_nonzero(left))
            report['tallestWallLeftMetres'] = round(max(report['tallestWallLeftMetres'], float(steps[left].max(initial=0.))), 3)
        result[window] = smoothed
    return result, report


def apply_reach_links(world, content=None):
    """Write the plan's reach links onto the composed ground, in list order; returns and records the report."""
    authored = links(world.plan)
    problems = validate_reach_links(world.plan)
    if problems:
        raise ValueError('Reach links: ' + '; '.join(problems))
    report = {'links': len(authored), 'perLink': []}
    if not authored:
        world.reach_links = report
        return report
    for link in authored:
        rivers = river_contacts(world.plan, link)
        if rivers:
            raise ValueError(f"Reach link {link['id']!r} reaches river centrelines {rivers}; keep its shape and feather off the channel")
    before = np.asarray(world.height, dtype=float).copy()
    # Kept for the reach proxy, which designs further links from this ground and replays the links and smoothing.
    world.ground_before_reach_links = before.astype(np.float32)
    height = before
    for link in authored:
        after = L._terrain_edit_height(world.gx, world.gz, height, {'terrain_edits': [link]})
        changed = np.abs(after - height)
        compounds = compound_contacts(world, content, changed)
        if compounds:
            raise ValueError(f"Reach link {link['id']!r} moves the ground under rigid compound members {compounds[:6]} by more than "
                             f"{COMPOUND_TOLERANCE_METRES} m; reground cannot move them with it")
        report['perLink'].append({'id': link['id'], 'op': link.get('op'), 'changedCells': int((changed > .01).sum()),
                                  'maximumChangeMetres': round(float(changed.max(initial=0.)), 3)})
        height = after
    height, smoothing = smooth_link_change(world.gx, world.gz, before, height, authored, world.plan, content)
    report['smoothing'] = smoothing
    compounds = compound_contacts(world, content, np.abs(height - before))
    if compounds:
        raise ValueError(f"Reach links together move the ground under rigid compound members {compounds[:6]} by more than "
                         f"{COMPOUND_TOLERANCE_METRES} m once smoothed")
    world.height = height
    total = np.abs(height - before)
    report.update(changedCells=int((total > .01).sum()), maximumChangeMetres=round(float(total.max(initial=0.)), 3))
    world.reach_links = report
    return report
