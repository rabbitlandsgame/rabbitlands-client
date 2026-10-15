"""Declared bridge crossings, taken from the served collision fold.

A territory's ``navigation.crossings`` names two standing points on each
continental bridge floor. The server keeps the deck through its own fold and
walks every declared pair on the vendored grid, so a declaration is only true
when both points sit on tiles that the fold actually serves and that a walker
can reach from one another under the climb limit.

The geometry stage cannot know that: the fold blocks any metre tile whose four
authored half-cells are not all walkable, so a point one bridge-field cell
inside a narrow diagonal floor can land on a pinched tile. This module runs in
the contracts stage, after the fold, on exactly the grid the server will hold:
it rasterises each ``Walk_ContinentalBridgeUnion_*_<region>`` floor with the
collision exporter's own rasteriser, keeps the tiles the floor fully covers,
joins them through at most one plain walkable ground tile (a floor interrupted
by a metre of bank is still one crossing), takes the largest climb-connected
part and declares its two extreme tiles along the floor's long axis. Since the
roads pass (R1) every floor is one bridge site's deck (bridge_export names it
by the site: its number is the site's id plus one; decks over deep water away
from any site number from 500), so a declaration is a site's crossing and
names the site it serves. Floors
whose largest part holds fewer than three deck tiles, or no more than half of
the floor's deck tiles, are reported instead of declared: a structure standing on
the deck, or a pinch, is something to fix or to state, not to hide behind a
declaration the server would fail.
"""
from __future__ import annotations
import math
import re
from collections import deque

import numpy as np
from scipy.ndimage import binary_dilation

from collision_export import CELL, GR, MAX_GRADE
from storage_bounds import StorageBounds

FLOOR_PREFIX = 'Walk_ContinentalBridgeUnion_'
LOOSE_DECK_BASE = 500   # bridge_export numbers decks away from every crossing site from here
UPWARD = 1 / math.sqrt(1 + MAX_GRADE ** 2) - 1e-9
MINIMUM_DECK_TILES = 3
# Declared points sit .2 m inside their tile's centre so the server's rounding
# (round(ox+x), round(oy-z)) names the tile that contains them.
INSET = .2
POLICY = ('Largest climb-connected part of the tiles each union floor fully covers on the served fold, '
          'joined through at most one plain walkable ground tile; declared when it holds at least three '
          'deck tiles and more than half of the floor; ends are its extreme tiles along the long axis.')


def floor_ids(document, region):
    """Union floor numbers this territory's package carries."""
    pattern = re.compile(r'^' + re.escape(FLOOR_PREFIX) + r'(\d{3})_' + re.escape(region) + r'(?:_WorldPlacement)*$')
    found = set()
    for node in document.get('nodes', []):
        match = pattern.match(node.get('name', ''))
        if match:
            found.add(match.group(1))
    return sorted(found)


def site_of(identity):
    """The crossing site a union floor number carries (bridge_export: site id + 1), or None for a deck away from a site."""
    number = int(identity)
    return number - 1 if 0 < number < LOOSE_DECK_BASE else None


def floor_triangles(document, body, region, identity):
    return GR.triangles(document, body, GR.named(document, f'{FLOOR_PREFIX}{identity}_{region}'))


def climb_parts(field, grid, climb):
    """4-neighbour parts of ``field`` whose neighbouring tiles differ by at most ``climb`` stages."""
    seen = np.zeros(field.shape, dtype=bool)
    parts = []
    for y, x in zip(*np.nonzero(field)):
        if seen[y, x]:
            continue
        seen[y, x] = True
        queue = deque([(int(y), int(x))])
        part = []
        while queue:
            cy, cx = queue.popleft()
            part.append((cy, cx))
            for dy, dx in ((1, 0), (-1, 0), (0, 1), (0, -1)):
                ny, nx = cy + dy, cx + dx
                if (0 <= ny < field.shape[0] and 0 <= nx < field.shape[1] and field[ny, nx] and not seen[ny, nx]
                        and abs(int(grid[ny, nx]) - int(grid[cy, cx])) <= climb):
                    seen[ny, nx] = True
                    queue.append((ny, nx))
        parts.append(part)
    return parts


def extreme_tiles(tiles):
    """The two tiles furthest apart along the tiles' principal axis, chosen deterministically."""
    tiles = np.asarray(tiles, dtype=float)
    spread = tiles - tiles.mean(axis=0)
    axis = np.linalg.svd(spread, full_matrices=False)[2][0]
    along = spread @ axis
    first = np.lexsort((tiles[:, 1], tiles[:, 0], along))[0]
    last = np.lexsort((tiles[:, 1], tiles[:, 0], -along))[0]
    return [int(v) for v in tiles[first]], [int(v) for v in tiles[last]]


def crossing_point(tile, floor, origin):
    """A declared end in package metres: inside its tile under the server's rounding rule."""
    tile_x, tile_y = int(tile[0]), int(tile[1])
    return [tile_x + .5 - origin[0] - INSET, float(floor), origin[1] - tile_y - .5 + INSET]


def declare_crossings(document, body, region, grid, climb, origin, cells, heights, *, bounds=None):
    """(crossings, declared, notWalkable) for one territory on its served grid.

    ``grid`` is the folded, requantised and rescaled server grid (``[y, x]``),
    ``heights`` the exporter's half-cell surface heights in metres.
    """
    width, rows = int(cells[0]) * 2, int(cells[1]) * 2
    bounds = StorageBounds(*cells) if bounds is None else bounds
    if ((bounds.width, bounds.height) != tuple(cells) or
            np.shape(grid) != (bounds.height, bounds.width) or np.shape(heights) != (rows, width)):
        raise ValueError(f'{region}: crossing arrays differ from storage dimensions')
    x0, z1 = bounds.physical_origin(origin)
    walkable = np.asarray(grid) != 0
    crossings, declared, not_walkable = [], [], []
    for identity in floor_ids(document, region):
        triangles = floor_triangles(document, body, region, identity)
        covered, _ = GR.rasterise(triangles, width, rows, x0, z1, CELL, upward=UPWARD)
        deck = covered.reshape(rows // 2, 2, width // 2, 2).all(axis=(1, 3)) & walkable
        record = {'id': f'ContinentalBridgeUnion_{identity}', 'site': site_of(identity), 'deckTiles': int(deck.sum()), 'parts': []}
        parts = []
        if deck.any():
            field = deck | (binary_dilation(deck) & walkable)
            for part in climb_parts(field, grid, climb):
                on_deck = [(y, x) for y, x in part if deck[y, x]]
                if on_deck:
                    parts.append(on_deck)
            parts.sort(key=lambda part: (-len(part), part[0]))
            record['parts'] = [len(part) for part in parts]
        largest = parts[0] if parts else []
        if len(largest) < MINIMUM_DECK_TILES or 2 * len(largest) <= int(deck.sum()):
            record['reason'] = ('no deck tile the fold serves' if not deck.any() else
                                f'largest walkable part holds {len(largest)} of {int(deck.sum())} deck tiles')
            not_walkable.append(record)
            continue
        ends = extreme_tiles([(x, y) for y, x in largest])
        record['endTiles'] = [list(bounds.logical_xy(x, y)) for x, y in ends]
        declared.append(record)
        endpoints = []
        for x, y in ends:
            floor = float(np.mean(np.asarray(heights, dtype=float)[y * 2:y * 2 + 2, x * 2:x * 2 + 2]))
            endpoints.append(crossing_point(bounds.logical_xy(x, y), floor, origin))
        crossings.append({'id': record['id'], 'site': record['site'], 'endpoints': endpoints})
    return crossings, declared, not_walkable
