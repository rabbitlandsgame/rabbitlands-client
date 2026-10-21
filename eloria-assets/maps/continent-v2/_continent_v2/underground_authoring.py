"""underground_authoring.py: helpers for the content scripts that lay out Landfall's underground (pass 2, 2026-10-21).

Nothing here writes a file: a content script loads the source (build_underground.load_design), calls these helpers,
edits the design in memory and writes it back with its own source_format.dump (which skips the `_` keys the loader
adds). Then: the builder, the packager, retarget_underground.py and the layout check, as always.

ARCHETYPES (rooms and links for a section; see the EL research, work-output/underground-pass2/el-research/REPORT.md
section 8). Each returns {'rooms': [[x, y, rx, ry], ...], 'links': [[a, b, width, [[x, y], ...]], ...],
'anchors': {...}} in tile units; combine() joins pieces into one section's rooms and links. measure() says what was
built (walkable tiles, corridor share, rock islands, longest walk) so a script can hit a size band.
  pocket(x, y, tiles)                      one chamber of about `tiles` walkable tiles (150-450 for the pocket band)
  strip_tunnel(start, end, width, ...)     a corridor-heavy tunnel at least 3:1 with small chambers along it; its
                                           anchors 'ends' are the two end chambers (a door at each end)
  looped_cavern(x, y, columns, rows, ...)  a lattice of chambers whose links close (columns-1) x (rows-1) loops round
                                           rock islands (8-30 for the looped band)
  branching_mine(start, heading, length, alcoves, ...)  a drift with dead-end alcoves left and right; anchors
                                           'alcoves' are the alcove ends, where veins go
VEINS
  rim(design, section_id)                  the section's rim tiles: blocked, with a reached 4-neighbour, within
                                           VEIN_FACE_MAX of a rock face, clear of doors, mouths, props and water
  vein(design, section_id, resource, anchor, count, ids)   picks `count` contiguous rim tiles nearest `anchor` and
                                           (apply=True) adds them to the section's nodes and veins
  suggest_anchors(design, section_id, n)   n rim anchors spread through the cave, a share of them near the entry and
                                           the rest favouring alcoves (the EL placement: 15% in the first fifth)
"""
from __future__ import annotations

from collections import deque
import math
import random

import numpy as np

import build_underground as B
import underground_source as S

# --- archetypes -------------------------------------------------------------------------------------------------------


def _r(value):
    return round(float(value) * 2) / 2


def pocket(x, y, tiles=300, seed=0, lobes=2):
    """One chamber of about `tiles` walkable tiles: a main lobe and `lobes`-1 smaller ones overlapping it."""
    rng = random.Random(seed)
    # a lobe of radius r walks about 0.9 pi (r - 1.7)^2 tiles inside a 1 m margin (calibrated on the builder's grid)
    radius = math.sqrt(max(tiles, 60) * 1.12 / math.pi / (1 + .35 * (lobes - 1))) + 1.7
    rooms = [[_r(x), _r(y), _r(radius * 1.1), _r(radius * .9)]]
    links = []
    for index in range(1, lobes):
        angle = rng.uniform(0, math.tau)
        rooms.append([_r(x + math.cos(angle) * radius * .9), _r(y + math.sin(angle) * radius * .9),
                      _r(radius * .6), _r(radius * .55)])
        links.append([0, index, _r(radius * .8)])
    return {'rooms': rooms, 'links': links, 'anchors': {'centre': [x, y]}}


def strip_tunnel(start, end, width=5.0, chambers=3, wiggle=3.0, chamber_radius=5.5, seed=0):
    """A tunnel from `start` to `end` (tile points) at least 3:1: `chambers` small chambers spaced along it, joined by
    links `width` wide that wind sideways by up to `wiggle` tiles. anchors: 'ends' (the end chambers' centres, for a
    door at each end), 'chambers'."""
    rng = random.Random(seed)
    (x0, y0), (x1, y1) = start, end
    length = math.hypot(x1 - x0, y1 - y0)
    ux, uy = (x1 - x0) / length, (y1 - y0) / length
    vx, vy = -uy, ux
    count = max(2, chambers + 2)
    rooms = []
    for index in range(count):
        t = index / (count - 1)
        side = 0 if index in (0, count - 1) else rng.uniform(-wiggle, wiggle)
        cx, cy = x0 + (x1 - x0) * t + vx * side, y0 + (y1 - y0) * t + vy * side
        r = chamber_radius * rng.uniform(.8, 1.15)
        rooms.append([_r(cx), _r(cy), _r(r), _r(r * rng.uniform(.75, 1.0))])
    links = []
    for index in range(count - 1):
        (ax, ay), (bx, by) = rooms[index][:2], rooms[index + 1][:2]
        mid = rng.uniform(-wiggle, wiggle)
        waypoints = [[_r((ax + bx) / 2 + vx * mid), _r((ay + by) / 2 + vy * mid)]]
        links.append([index, index + 1, width, waypoints])
    return {'rooms': rooms, 'links': links,
            'anchors': {'ends': [rooms[0][:2], rooms[-1][:2]], 'chambers': [r[:2] for r in rooms]}}


def looped_cavern(x, y, columns=4, rows=4, spacing=14.0, room=6.0, link=6.0, jitter=2.0, seed=0):
    """A lattice of `columns` x `rows` chambers `spacing` tiles apart, every neighbour linked: each lattice cell the
    links close round is a rock island (a walled pillar), (columns-1) x (rows-1) of them. Keep spacing - room - link/2
    above about 3 tiles so the islands stay rock. anchors: 'islands' (the cells' centres), 'corners'."""
    rng = random.Random(seed)
    rooms, index = [], {}
    for j in range(rows):
        for i in range(columns):
            cx = x + (i - (columns - 1) / 2) * spacing + rng.uniform(-jitter, jitter)
            cy = y + (j - (rows - 1) / 2) * spacing + rng.uniform(-jitter, jitter)
            r = room * rng.uniform(.8, 1.2)
            index[i, j] = len(rooms)
            rooms.append([_r(cx), _r(cy), _r(r), _r(r * rng.uniform(.8, 1.1))])
    links = []
    for j in range(rows):
        for i in range(columns):
            if i + 1 < columns:
                links.append([index[i, j], index[i + 1, j], _r(link * rng.uniform(.8, 1.15))])
            if j + 1 < rows:
                links.append([index[i, j], index[i, j + 1], _r(link * rng.uniform(.8, 1.15))])
    islands = [[x + (i + .5 - (columns - 1) / 2) * spacing, y + (j + .5 - (rows - 1) / 2) * spacing]
               for j in range(rows - 1) for i in range(columns - 1)]
    corners = [rooms[index[0, 0]][:2], rooms[index[columns - 1, rows - 1]][:2]]
    return {'rooms': rooms, 'links': links, 'anchors': {'islands': islands, 'corners': corners}}


def branching_mine(start, heading, length=80.0, alcoves=8, drift_width=6.0, step=12.0, alcove_length=(8.0, 13.0),
                   alcove_width=4.5, seed=0):
    """A drift from `start` along `heading` (degrees, tile frame: 0 = +x, 90 = +y) for `length` tiles, a chamber every
    `step` tiles, with `alcoves` dead-end alcoves branching left and right, each `alcove_length` tiles long and ending in
    a small chamber. anchors: 'alcoves' (the alcove ends: put veins there), 'drift' (the drift's chambers), 'start',
    'end'."""
    rng = random.Random(seed)
    angle = math.radians(heading)
    ux, uy = math.cos(angle), math.sin(angle)
    count = max(2, int(length // step) + 1)
    rooms = []
    for index in range(count):
        bend = rng.uniform(-2.0, 2.0) if 0 < index < count - 1 else 0
        cx, cy = start[0] + ux * step * index - uy * bend, start[1] + uy * step * index + ux * bend
        r = drift_width * rng.uniform(.75, 1.05)
        rooms.append([_r(cx), _r(cy), _r(r), _r(r * rng.uniform(.8, 1.0))])
    links = [[i, i + 1, drift_width] for i in range(count - 1)]
    ends = []
    slots = [i for i in range(1, count)]
    rng.shuffle(slots)
    for n in range(alcoves):
        base = slots[n % len(slots)]
        side = 1 if (n // len(slots) + n) % 2 else -1
        reach = rng.uniform(*alcove_length)
        tilt = rng.uniform(-25, 25)
        a = angle + side * math.radians(90 + tilt)
        bx, by = rooms[base][:2]
        ex, ey = bx + math.cos(a) * reach, by + math.sin(a) * reach
        r = rng.uniform(3.0, 3.8)
        rooms.append([_r(ex), _r(ey), _r(r), _r(r * .85)])
        links.append([base, len(rooms) - 1, alcove_width])
        ends.append([_r(ex), _r(ey)])
    return {'rooms': rooms, 'links': links,
            'anchors': {'alcoves': ends, 'drift': [r[:2] for r in rooms[:count]], 'start': rooms[0][:2],
                        'end': rooms[count - 1][:2]}}


def combine(*parts, joins=()):
    """One section's rooms and links from several archetype pieces, in order; `joins` [(part a, room a, part b,
    room b, width), ...] links rooms of different pieces. Returns {'rooms', 'links', 'anchors': [each piece's]}."""
    rooms, links, offsets = [], [], []
    for part in parts:
        offsets.append(len(rooms))
        rooms += [list(r) for r in part['rooms']]
        links += [[a + offsets[-1], b + offsets[-1], *rest] for a, b, *rest in part['links']]
    for pa, ra, pb, rb, width in joins:
        links.append([offsets[pa] + ra, offsets[pb] + rb, width])
    return {'rooms': rooms, 'links': links, 'anchors': [part.get('anchors', {}) for part in parts]}


# --- what a layout gives --------------------------------------------------------------------------------------------


def _grids(design):
    half, coarse = B.masks(design, strict=False)
    _walk, codes = B.walk_codes(design, half, coarse)
    return coarse, codes


def reach(design, section, grids=None, start=None):
    """{(x, y): steps} for the section's floor from its primary arrival (or `start`): four-way steps that climb at most
    1 m, as the server walks."""
    coarse, codes = grids or _grids(design)
    sx, sy = start or section['_arrival']
    if not coarse[sy, sx]:
        return {}
    steps = {(sx, sy): 0}
    queue = deque([(sx, sy)])
    while queue:
        x, y = queue.popleft()
        for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1)):
            t = (x + dx, y + dy)
            if t not in steps and coarse[t[1], t[0]] and abs(int(codes[t[1], t[0]]) - int(codes[y, x])) <= 20:
                steps[t] = steps[(x, y)] + 1
                queue.append(t)
    return steps


def measure(design, section_id, grids=None):
    """What the built layout gives: walkable tiles, bounding box and its aspect, corridor share (floor narrower than
    3 m: not covered by a 3 x 3 opening), rock islands (pillars), the longest walk (double sweep) and the farthest
    floor from the primary arrival, in steps."""
    from scipy import ndimage
    section = next(s for s in design['sections'] if s['id'] == section_id)
    grids = grids or _grids(design)
    steps = reach(design, section, grids)
    if not steps:
        return {'walkableTiles': 0}
    tiles = np.array(list(steps))
    x0, y0 = tiles.min(0); x1, y1 = tiles.max(0)
    mask = np.zeros((y1 - y0 + 3, x1 - x0 + 3), dtype=bool)
    mask[tiles[:, 1] - y0 + 1, tiles[:, 0] - x0 + 1] = True
    opened = ndimage.binary_opening(mask, structure=np.ones((3, 3), dtype=bool))
    far = max(steps, key=steps.get)
    sweep = reach(design, section, grids, start=far)
    w, h = int(x1 - x0 + 1), int(y1 - y0 + 1)
    return {'walkableTiles': len(steps), 'box': [w, h], 'aspect': round(max(w, h) / max(1, min(w, h)), 2),
            'fill': round(len(steps) / (w * h), 3),
            'corridorShare': round(float(1 - opened.sum() / mask.sum()), 3), 'islands': len(B.outline(section).interiors),
            'farthestFromArrival': steps[far], 'longestWalk': max(sweep.values())}


# --- veins ----------------------------------------------------------------------------------------------------------


def _face(section, rings, x, y):
    centre = B.Point(x + .5, y + .5)
    ring, pillar = min(rings, key=lambda entry: entry[0].distance(centre))
    along = ring.project(centre)
    p = ring.interpolate(along)
    a, b = ring.interpolate(max(0., along - .6)), ring.interpolate(min(ring.length, along + .6))
    dx, dy = b.x - a.x, b.y - a.y
    rx, ry = B.into_rock(ring, pillar, dx, dy, max(1e-9, math.hypot(dx, dy)))
    return (centre.x - p.x) * -rx + (centre.y - p.y) * -ry, pillar


def rim(design, section_id, grids=None, keep_clear=3.0):
    """The section's rim tiles {(x, y): {'distance', 'pillar', 'steps'}}: blocked, with a 4-neighbour on the reached
    floor (`steps`: that neighbour's walk from the primary arrival), the tile's centre within VEIN_FACE_MAX of a rock
    face, and not a node already, not within `keep_clear` tiles of a door's exit or a passage end, not under a prop's
    block or in water."""
    from shapely import contains_xy
    section = next(s for s in design['sections'] if s['id'] == section_id)
    grids = grids or _grids(design)
    coarse, _codes = grids
    steps = reach(design, section, grids)
    shape = B.outline(section)
    rings = B.wall_rings(shape)
    taken = {(x, y) for _, _, x, y in section['nodes']}
    clear = [door['exit'] for door in S.doors(section)] + [end['tile'] for end in section['_ends']]
    clear += [mouth['face'] for mouth in B.mouths(section)]
    props = [(item['x'], item['y'], item['block'] + .6) for item in B.dressing(section) if item['block'] > 0]
    water = B.pools(section)
    result = {}
    for (x, y), walked in steps.items():
        for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1)):
            t = (x + dx, y + dy)
            if coarse[t[1], t[0]] or t in taken or t in result:
                continue
            cx, cy = t[0] + .5, t[1] + .5
            if any(math.hypot(cx - px, cy - py) < keep_clear for px, py in clear):
                continue
            if any(math.hypot(cx - px, cy - py) < r for px, py, r in props):
                continue
            if water is not None and contains_xy(water.buffer(.5), cx, cy):
                continue
            distance, pillar = _face(section, rings, *t)
            if distance > B.VEIN_FACE_MAX - .1:
                continue
            best = min(steps.get((t[0] + ex, t[1] + ey), 10 ** 9) for ex, ey in ((1, 0), (-1, 0), (0, 1), (0, -1)))
            result[t] = {'distance': round(distance, 2), 'pillar': pillar, 'steps': best}
    return result


def vein(design, section_id, resource, anchor, count, ids, where='any', grids=None, apply=True, rims=None):
    """A vein of `count` nodes of `resource` along the rock face nearest `anchor` [x, y]: contiguous rim tiles (eight-
    way neighbours along the face, grown from the rim tile nearest the anchor). `where` 'wall' or 'pillar' limits it to
    the outer wall or the rock pillars. `ids` are the nodes' object ids (one per node). With `apply`, the nodes join
    the section's `nodes` and the vein its `veins`. Returns the node rows [[id, resource, x, y], ...]."""
    section = next(s for s in design['sections'] if s['id'] == section_id)
    if len(ids) != count:
        raise ValueError(f'{section_id}: give {count} object ids for a {count}-node vein')
    candidates = rims if rims is not None else rim(design, section_id, grids)
    if where != 'any':
        candidates = {t: info for t, info in candidates.items() if info['pillar'] == (where == 'pillar')}
    if not candidates:
        raise ValueError(f'{section_id}: no rim tile left for a vein')
    ax, ay = anchor

    def grow(start):
        order = {start: 0}
        queue = deque([start])
        while queue:
            x, y = queue.popleft()
            for dx in (-1, 0, 1):
                for dy in (-1, 0, 1):
                    t = (x + dx, y + dy)
                    if t in candidates and t not in order:
                        order[t] = order[(x, y)] + 1
                        queue.append(t)
        return order
    # start on the nearest rim tile whose stretch of face (eight-way neighbours) holds the whole vein
    for start in sorted(candidates, key=lambda t: math.hypot(t[0] + .5 - ax, t[1] + .5 - ay)):
        order = grow(start)
        if len(order) >= count:
            break
    else:
        raise ValueError(f'{section_id}: no stretch of {count} contiguous rim tiles for a vein near {anchor}')
    picked = sorted(order, key=lambda t: (order[t], math.hypot(t[0] + .5 - ax, t[1] + .5 - ay)))[:count]
    rows = [[oid, resource, x, y] for oid, (x, y) in zip(ids, sorted(picked))]
    if apply:
        section['nodes'] += rows
        section.setdefault('veins', []).append({'resource': resource, 'nodes': list(ids)})
        if rims is not None:
            for t in picked:
                rims.pop(t, None)
    return rows


def passage_end(design, section_id, anchor, art='stairs', grids=None, back=2.5):
    """A passage end near `anchor` [x, y] (a point at the wall where its mouth should be): the reached floor tile
    whose centre stands close in front of a rock face yet far enough off it for `art`'s mouth (a stairs or flooded
    pit needs about 2.2 m), its facing (toward that face), and an arrival about `back` tiles out into the room.
    Returns {section, tile, arrival, facing, art}, ready for a passage's `ends`."""
    section = next(s for s in design['sections'] if s['id'] == section_id)
    grids = grids or _grids(design)
    steps = reach(design, section, grids)
    shape = B.outline(section)
    rings = [ring for ring, _pillar in B.wall_rings(shape)]
    low = B.MOUTH_TILE_CLEAR + 1.25 if B.MOUTHS[art]['pit'] else 1.3
    best = None
    for (x, y) in steps:
        centre = B.Point(x + .5, y + .5)
        ring = min(rings, key=lambda r: r.distance(centre))
        p = ring.interpolate(ring.project(centre))
        d = math.hypot(p.x - centre.x, p.y - centre.y)
        if not low <= d <= low + 1.2:
            continue
        score = math.hypot(x + .5 - anchor[0], y + .5 - anchor[1])
        if best is None or score < best[0]:
            best = (score, (x, y), ((p.x - centre.x) / d, (p.y - centre.y) / d))
    if best is None:
        raise ValueError(f'{section_id}: no floor tile near {anchor} fits a {art} mouth')
    _, (x, y), (ux, uy) = best
    want = (x + .5 - ux * back, y + .5 - uy * back)
    arrival = min((t for t in steps if t != (x, y)), key=lambda t: math.hypot(t[0] + .5 - want[0], t[1] + .5 - want[1]))
    return {'section': section_id, 'tile': [x, y], 'arrival': list(arrival), 'facing': [round(ux, 3), round(uy, 3)],
            'art': art}


def suggest_anchors(design, section_id, n, near_entry=.15, spacing=6.0, grids=None, seed=0):
    """`n` vein anchors on the section's rim: about `near_entry` of them within the first fifth of the walk from the
    primary arrival, the rest spread through the cave at least `spacing` tiles apart, favouring enclosed rim tiles
    (alcoves and dead ends: many blocked tiles round them)."""
    rng = random.Random(seed)
    grids = grids or _grids(design)
    coarse, _ = grids
    tiles = rim(design, section_id, grids)
    if not tiles:
        return []
    deepest = max(info['steps'] for info in tiles.values()) or 1

    def enclosure(t):
        x, y = t
        window = coarse[max(0, y - 3):y + 4, max(0, x - 3):x + 4]
        return 1 - window.mean()
    chosen = []

    def pick(pool, k):
        ranked = sorted(pool, key=lambda t: -(enclosure(t) + rng.uniform(0, .15)))
        for t in ranked:
            if len(chosen) >= k:
                break
            if all(math.hypot(t[0] - c[0], t[1] - c[1]) >= spacing for c in chosen):
                chosen.append(t)
    early = [t for t, info in tiles.items() if info['steps'] / deepest < .2]
    pick(early, max(1, round(n * near_entry)) if n > 1 else 0)
    pick(list(tiles), n)
    return [[t[0] + .5, t[1] + .5] for t in chosen]
