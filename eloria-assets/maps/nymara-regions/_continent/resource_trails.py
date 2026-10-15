"""Trails from the road network to authored resource sites on steep ground and to posts out of reach.

The contract placer seats every harvest node and territory marker on a
hub-connected tile within its movement budget (35 m). A site in broadly
steep ground has such a tile only where a road corridor crosses the slope:
the Whitehorn peat nodes and the range's territory marker were reached
through the fourteenth publication because a public road happened to run past
them, and alignments that keep off steep traverses no longer do. After the
public, door and discovery roads exist, this module routes a narrow trail from
the nearest road station to every cluster of such sites, so the served fold
keeps a walkable corridor at each site whatever the public network does. A
site on a locally steep spot with gentler ground inside its budget, or with a
road inside its budget, needs none: the placer moves it there. A road station
counts as within reach only when the ground between can be walked: one 25 m
away and 24 m higher serves nothing. An NPC post (npcs.txt, budget 12 m) with
a station within 30 m is served by one inside its budget or within walkable
reach, and gets a trail otherwise, whatever its ground: the Motherroot Voice
stands on the Great Tree's root plateau, a rigid footing nine metres above
the village floor whose flanks no corridor can grade, and the fourteenth and
the fifteenth's first chains reached her only where a discovery branch
happened to pass. A post with no station within 30 m follows the site rule:
level quay and moor posts far from any road stand on ground the placer
serves, and only steep ground earns a trail. The post rule is built and
tested but the vendored posts are not read yet (POST_RULES stands apart from
RULES): the fifteenth's chains showed that the reach test cannot see an
island (a station within reach on the far side of an ungradable flank still
counted as service for the Motherroot Voice) and that the trail built for
another Amberwood post cut the Amberwood-Whitehorn crossing off from the hub.

The authored records are read from the vendored server profile with the same
columns the publisher rewrites (``publish_continent_geography.RULES``):
harvesting.txt node rows carry their map in column 1 and tile in columns 3-4;
territories.txt rows carry their map in column 2 and three tiles in columns
4-5, 6-7 and 8-9.
"""
from __future__ import annotations
from pathlib import Path

import numpy as np
from scipy.ndimage import maximum_filter, uniform_filter
from scipy.spatial import cKDTree

from world_layout import CELL

TRAIL_WIDTH_METRES = 1.65
STEEP_SITE_GRADE = .65          # the walkable limit: steeper ground across a station needs a corridor
BUDGET_METRES = 35.             # the placer's movement budget for harvest nodes and territory markers
STEEP_GROUND_SHARE = .6         # the site needs a trail only when most ground within the budget is steep
ROAD_REACH_METRES = 30.         # a road this close lies within the budget: the site moves to its corridor
CLUSTER_METRES = 20.            # sites this close share one trail
MAXIMUM_TRAILS_PER_REGION = 12
TRAIL_LENGTH_FACTOR = 3.        # a trail may wind up to three times its gap ...
TRAIL_LENGTH_ALLOWANCE_METRES = 20.   # ... plus twenty metres; longer alignments are skipped and recorded
REACH_GRADE = .65               # a station within reach stands no higher or lower than this grade over its distance
POST_BUDGET_METRES = 12.        # the placer's movement budget for NPC posts
RULES = {'harvesting.txt': [('node', 1, 3, 4)],
         'territories.txt': [(None, 2, 4, 5), (None, 2, 6, 7), (None, 2, 8, 9)]}
# NPC posts (npcs.txt: ('npc', 2, 3, 4)) are read by the same rules once POST_RULES joins RULES; see the module docstring.
POST_RULES = {'npcs.txt': [('npc', 2, 3, 4)]}
POST_FILES = tuple(POST_RULES)
READ_POSTS = False


def profile_rows(text):
    """(line number, stripped fields) for every data row of a pipe-separated profile file."""
    for number, line in enumerate(text.splitlines(), 1):
        body = line.split('#', 1)[0]
        if not body.strip():
            continue
        yield number, [part.strip() for part in body.split('|')]


def authored_sites(profile, ids):
    """{region: [(label, [x, y], kind)]} for every harvest node, territory marker (site) and NPC post (post) in the vendored profile."""
    sites = {region: [] for region in ids}
    for filename, rules in {**RULES, **({} if not READ_POSTS else POST_RULES)}.items():
        path = Path(profile) / filename
        if not path.exists():
            continue
        for number, fields in profile_rows(path.read_text(encoding='utf-8')):
            for keyword, map_column, x_column, y_column in rules:
                if len(fields) <= max(map_column, x_column, y_column) or fields[map_column] not in sites:
                    continue
                if keyword and fields[0] != keyword:
                    continue
                try:
                    tile = [int(fields[x_column]), int(fields[y_column])]
                except ValueError:
                    continue
                sites[fields[map_column]].append((f'{filename}:{number}:{x_column}', tile, 'post' if filename in POST_FILES else 'site'))
    return sites


def station_slope(world):
    """The steepest two-metre gradient within each vertex's six-metre block, as the router sees it."""
    gz, gx = np.gradient(world.height, CELL)
    return maximum_filter(np.hypot(gx, gz), size=3)


def steep_ground_share(slope):
    """The share of ground steeper than the walkable limit within the movement budget of each vertex."""
    return uniform_filter((slope > STEEP_SITE_GRADE).astype(float), size=max(1, int(round(2 * BUDGET_METRES / CELL))), mode='nearest')


def cluster(points, metres):
    """Single-linkage groups of point indices within ``metres`` of each other."""
    points = np.asarray(points, float)
    parent = list(range(len(points)))

    def find(i):
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i
    tree = cKDTree(points) if len(points) else None
    if tree is not None:
        for i, j in tree.query_pairs(metres):
            parent[find(i)] = find(j)
    groups = {}
    for i in range(len(points)):
        groups.setdefault(find(i), []).append(i)
    return list(groups.values())


def site_kind(entry):
    """'site' (harvest node, territory marker) or 'post' (NPC) for a site entry; older two-field entries are sites."""
    return entry[2] if len(entry) > 2 else 'site'


def within_reach(point, height, stations, heights, tree, budget):
    """A road station inside the site's own budget, or one within ROAD_REACH_METRES standing no steeper than REACH_GRADE from it."""
    if tree is None or not len(stations):
        return False
    distances, indices = tree.query(point, k=min(8, len(stations)))
    for distance, index in zip(np.atleast_1d(distances), np.atleast_1d(indices)):
        if not np.isfinite(distance) or distance > ROAD_REACH_METRES:
            break
        if distance <= budget or abs(float(heights[index]) - height) <= REACH_GRADE * max(float(distance), CELL):
            return True
    return False


def prepare_resource_trails(world, content, profile, *, exclude_regions=()):
    """Route a trail to every cluster of authored sites on steep ground, or posts, with no road station within walkable reach."""
    exclude_regions=set(exclude_regions)
    sites = authored_sites(profile, world.ids)
    slope = station_slope(world)
    share = steep_ground_share(slope)
    stations = [(np.asarray(road['points'], float), road['id']) for road in world.roads]
    all_stations = np.vstack([p for p, _ in stations]) if stations else np.zeros((0, 3))
    all_points = all_stations[:, [0, 2]]
    # Trails are planned before the road grade solve: a station's profile is the
    # surface the corridor will be graded to, where the ground under it is not.
    station_heights = all_stations[:, 1] if len(all_stations) else np.zeros(0)
    owners = np.asarray(world.owner_at(all_points[:, 0], all_points[:, 1]), int) if len(all_points) else np.zeros(0, int)
    all_tree = cKDTree(all_points) if len(all_points) else None
    report = {'trails': [], 'sitesRead': sum(1 for v in sites.values() for site in v if site_kind(site) == 'site'), 'postsRead': sum(1 for v in sites.values() for site in v if site_kind(site) == 'post'),
              'steepSites': 0, 'servedSites': 0, 'postsServed': 0, 'postsOutOfReach': 0, 'reachGrade': REACH_GRADE, 'postBudgetMetres': POST_BUDGET_METRES,
              'trailWidthMetres': TRAIL_WIDTH_METRES, 'steepSiteGrade': STEEP_SITE_GRADE, 'budgetMetres': BUDGET_METRES,
              'steepGroundShare': STEEP_GROUND_SHARE, 'roadReachMetres': ROAD_REACH_METRES, 'clusterMetres': CLUSTER_METRES, 'skipped': [],
              'policy': 'A harvest node or territory marker on ground steeper than .65 across a station, with most ground within its 35 m '
                        'budget as steep and no road station within 30 m, gets a 1.65 m trail from the nearest road '
                        'station of its territory to its cluster; an NPC post with a station within 30 m but none within its 12 m budget nor within .65 of its height across the gap gets one whatever its ground, and a post with no station within 30 m follows the site rule; '
                        'clusters join sites within 20 m.'}
    for region in world.ids:
        if region in exclude_regions:continue
        index = world.ids.index(region)
        candidates = []
        for entry in sites.get(region, []):
            label, tile, kind = entry[0], entry[1], site_kind(entry)
            point = np.asarray(content.mapped_server_point(region, tile, roads=True), float)[[0, 2]]
            if int(world.owner_at(float(point[0]), float(point[1]))) != index:
                continue
            distance = float(all_tree.query(point)[0]) if all_tree is not None else np.inf
            if kind == 'post' and distance <= ROAD_REACH_METRES:
                # A post near a road: served by a station inside its budget or within walkable reach.
                if within_reach(point, float(world.height_at(float(point[0]), float(point[1]))), all_points, station_heights, all_tree, POST_BUDGET_METRES):
                    report['postsServed'] += 1
                    continue
                report['postsOutOfReach'] += 1
                candidates.append((label, point))
                continue
            # A site, or a post with no station within reach distance: only steep ground far from any road earns a trail.
            iz = int(np.clip(round((point[1] - world.z0) / CELL), 0, slope.shape[0] - 1))
            ix = int(np.clip(round((point[0] - world.x0) / CELL), 0, slope.shape[1] - 1))
            if float(slope[iz, ix]) <= STEEP_SITE_GRADE or float(share[iz, ix]) < STEEP_GROUND_SHARE:
                if kind == 'post':
                    report['postsServed'] += 1
                continue
            report['steepSites'] += 1
            if distance <= ROAD_REACH_METRES:
                report['servedSites'] += 1
                continue
            candidates.append((label, point))
        if not candidates:
            continue
        own = all_points[owners == index] if len(all_points) else all_points
        if not len(own):
            report['skipped'].append({'region': region, 'reason': 'no road station in the territory', 'sites': [c[0] for c in candidates]})
            continue
        groups = cluster([p for _, p in candidates], CLUSTER_METRES)
        groups.sort(key=lambda g: -len(g))
        for number, group in enumerate(groups):
            if number >= MAXIMUM_TRAILS_PER_REGION:
                report['skipped'].append({'region': region, 'reason': 'trail limit', 'sites': [candidates[i][0] for i in group]})
                continue
            centre = np.mean([candidates[i][1] for i in group], axis=0)
            if int(world.owner_at(float(centre[0]), float(centre[1]))) != index:
                # A cluster straddling a boundary bulge: aim at its site nearest the centroid, which is inside.
                centre = min((candidates[i][1] for i in group), key=lambda p: float(np.linalg.norm(p - centre)))
            # A trail starts on dry land outside its river setback, never on a bridge, and on its sites' bank when
            # a station there exists (river_crossings.branch_start, the discovery branches' rule).
            import river_crossings as RC
            start, distance = RC.branch_start(world, region, own, centre, TRAIL_WIDTH_METRES)
            name = f'trail-{region}-{number}'
            try:
                # The start is a road station, not a structure of the trail's own.
                path = world.route(start, centre, region=region, own=world.solids_at_ends(centre), width=TRAIL_WIDTH_METRES, name=name)
            except ValueError as error:
                report['skipped'].append({'region': region, 'reason': str(error), 'sites': [candidates[i][0] for i in group]})
                continue
            length = float(np.sum(np.linalg.norm(np.diff(np.asarray(path, float), axis=0), axis=1)))
            if length > TRAIL_LENGTH_FACTOR * float(distance) + TRAIL_LENGTH_ALLOWANCE_METRES:
                # A trail that must wind far around steep ground to close a short gap is a road, not a trail.
                report['skipped'].append({'region': region, 'reason': f'alignment {length:.0f} m for a {float(distance):.0f} m gap',
                                          'sites': [candidates[i][0] for i in group]})
                continue
            world.add_road(path, width=TRAIL_WIDTH_METRES, name=name)
            report['trails'].append({'id': name, 'region': region, 'sites': [candidates[i][0] for i in group],
                                     'from': [float(start[0]), float(start[1])], 'to': [float(centre[0]), float(centre[1])],
                                     'stations': int(len(path)), 'roadDistanceMetres': round(float(distance), 1)})
    world.resource_trails = report
    return report
