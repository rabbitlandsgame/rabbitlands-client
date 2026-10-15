"""Authored points: server records deliberately relocated to reachable ground, listed in the plan.

A record's position normally follows its linked architecture through the retained transform. Some secret doors,
their returns and their interactives stand where no served ground can reach them on the composed continent (a door
on a cliff face or a tower wall, a return inside a building's box). The plan's "authored_points" pins such a record,
by the tile it has in the authored server profile, to a point of open ground beside its entrance, exactly as the Four
Gates Sage records are pinned (four_gates_sage.py): the contract placer still resolves the pin to actual standing
ground within the record's own displacement budget, and the door roads are routed to it.

Each entry: {"region", "tile": [x, y] (the record's authored server tile), "point": [x, z] (continent metres),
"record" (the contract record it serves, for the report), "reason"}, and optionally "roads": "pin" (the default: the
door and discovery roads serve the point) or "entrance" (the roads keep serving the record's own entrance; only the
served standing point moves). A road re-routed to a pin re-settles its territory's road earthworks, which can move
the ground far from the pin under links designed for the old ground; "entrance" leaves the roads, and so the ground,
exactly as they were. A point must stand inside its territory on dry ground; its height is read from the finished
ground after the reach links.
"""
from __future__ import annotations

import numpy as np

PLAN_KEY = 'authored_points'
MINIMUM_DRY_METRES = .8
ROAD_CHOICES = ('pin', 'entrance')


def entries(plan):
    return list(plan.get(PLAN_KEY) or [])


def validate_authored_points(plan):
    """Every problem with the plan's authored points; empty means valid."""
    value = plan.get(PLAN_KEY)
    if value is None:
        return []
    if not isinstance(value, list):
        return [f"'{PLAN_KEY}' must be a list of points"]
    problems, seen = [], set()
    regions = {region['id'] for region in plan.get('regions') or []}
    for index, entry in enumerate(value):
        where = f'authored point {index}'
        if not isinstance(entry, dict):
            problems.append(f'{where}: each point must be an object'); continue
        region, tile, point = entry.get('region'), entry.get('tile'), entry.get('point')
        if regions and region not in regions:
            problems.append(f'{where}: unknown region {region!r}')
        if not (isinstance(tile, list) and len(tile) == 2 and all(isinstance(v, int) and not isinstance(v, bool) for v in tile)):
            problems.append(f'{where}: tile must be the record\'s two integer server coordinates, not {tile!r}')
            continue
        if not (isinstance(point, list) and len(point) == 2 and all(isinstance(v, (int, float)) and not isinstance(v, bool)
                                                                   and np.isfinite(v) for v in point)):
            problems.append(f'{where}: point must be finite [x, z] continent metres, not {point!r}')
        key = (region, tuple(tile))
        if key in seen:
            problems.append(f'{where}: {region} tile {tile} is pinned twice')
        seen.add(key)
        if not isinstance(entry.get('reason'), str) or not entry['reason'].strip():
            problems.append(f'{where}: say why the record moves ("reason")')
        if entry.get('roads', 'pin') not in ROAD_CHOICES:
            problems.append(f'{where}: roads must be one of {list(ROAD_CHOICES)}, not {entry.get("roads")!r}')
    return problems


def prepare_authored_points(world, content):
    """Pin the plan's authored points on the content before the door roads are routed; returns the report."""
    problems = validate_authored_points(world.plan)
    if problems:
        raise ValueError('Authored points: ' + '; '.join(problems))
    if not hasattr(content, 'authored_server_points'):
        content.authored_server_points = {}
    if not hasattr(content, 'entrance_road_tiles'):
        content.entrance_road_tiles = set()
    report = {'points': []}
    saved = set(getattr(world, 'authoring_snapshots', {}))
    for entry in entries(world.plan):
        region, tile = entry['region'], tuple(entry['tile'])
        # The source profile record is now bound to a saved marker by identity.
        # A retired plan pin must not override or recreate that marker.
        if region in saved:
            continue
        x, z = (float(v) for v in entry['point'])
        if (region, tile) in content.authored_server_points:
            raise ValueError(f'{region}:{list(tile)}: already pinned by another module')
        if int(world.owner_at(x, z)) != world.ids.index(region):
            raise ValueError(f'{region}:{list(tile)}: authored point ({x}, {z}) lies outside its territory')
        height = float(world.height_at(x, z))
        if height < MINIMUM_DRY_METRES:
            raise ValueError(f'{region}:{list(tile)}: authored point ({x}, {z}) is not dry ground ({height:.2f} m)')
        point = np.array([x, height, z])
        content.authored_server_points[(region, tile)] = point
        roads = entry.get('roads', 'pin')
        if roads == 'entrance':
            content.entrance_road_tiles.add((region, tile))
        report['points'].append({'region': region, 'tile': list(tile), 'point': point.tolist(), 'roads': roads,
                                 'record': entry.get('record'), 'reason': entry['reason']})
    world.authored_points = report
    return report


def refresh_authored_point_heights(world, content):
    """Read every pinned point's height from the finished ground."""
    report = getattr(world, 'authored_points', {'points': []})
    for row in report['points']:
        point = content.authored_server_points[(row['region'], tuple(row['tile']))]
        point[1] = float(world.height_at(point[0], point[2]))
        if point[1] < MINIMUM_DRY_METRES:
            raise ValueError(f"{row['region']}:{row['tile']}: final ground under the authored point is not dry")
        row['point'] = point.tolist()
