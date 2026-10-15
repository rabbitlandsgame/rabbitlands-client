"""A trail gauntlet's package walks as one road with no shortcut.

A trail gauntlet is one open map: arenas joined by the road itself, with no
gate or portal between them. What keeps the run in order is the ground, so
the served grid (ESCG v2, the server's own walk rule) is checked here: the
arrival reaches the vault, every arena lies on the only way between the one
before it and the one after it, every creature mouth reaches its own arena
without crossing another, and every spawn, respawn and object tile is open.
TRAIL_FORMAT.md describes the package.
"""
import gzip
import json
import math
import struct
import unittest
from collections import deque
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
GAUNTLETS = ROOT / "eloria-assets" / "maps" / "gauntlets"
REGISTRY = ROOT / "godot-client" / "data" / "maps" / "registry.json"
ROUTES = ("harrowcrag_gauntlet", "resin_road_gauntlet", "ice_stair_gauntlet", "coil_causeway_gauntlet",
          "barrow_run_gauntlet", "drowned_arcades_gauntlet", "red_canyon_gauntlet", "resonant_cut_gauntlet",
          "bund_run_gauntlet")
STEPS = ((0, 1), (1, 1), (1, 0), (1, -1), (0, -1), (-1, -1), (-1, 0), (-1, 1))


def read_served_grid(path):
    """(width, height, codes[y][x], climb in codes) of an ESCG v2 file."""
    raw = gzip.decompress(path.read_bytes())
    magic, version, size, width, height, _datum, unit, climb, filter_, _f, _r, _crc = \
        struct.unpack_from("<4sHHIIiHHBBHI", raw, 0)
    assert magic == b"ESCG" and version == 2 and size == 32, path
    values = struct.unpack_from(f"<{width * height}H", raw, 32)
    rows = [list(values[y * width:(y + 1) * width]) for y in range(height)]
    if filter_ == 1:                               # row delta
        for row in rows:
            running = 0
            for x, value in enumerate(row):
                running = (running + value) & 0xFFFF
                row[x] = running
    return width, height, rows, climb // unit


def inside(polygon, x, y):
    """Is the tile (x, y) inside a tile-corner polygon (by its centre)?"""
    px, py = x + 0.5, y + 0.5
    hit = False
    for (ax, ay), (bx, by) in zip(polygon, polygon[1:] + polygon[:1]):
        if (ay > py) != (by > py) and px < ax + (py - ay) * (bx - ax) / (by - ay):
            hit = not hit
    return hit


class Grid:
    def __init__(self, path):
        self.width, self.height, self.codes, self.climb = read_served_grid(path)

    def open(self, x, y):
        return 0 <= x < self.width and 0 <= y < self.height and self.codes[y][x] != 0

    def step(self, x, y, dx, dy):
        nx, ny = x + dx, y + dy
        if not self.open(x, y) or not self.open(nx, ny):
            return False
        return abs(self.codes[ny][nx] - self.codes[y][x]) <= self.climb

    def neighbours(self, x, y):
        for dx, dy in STEPS:
            if not self.step(x, y, dx, dy):
                continue
            if dx and dy and not (self.step(x, y, dx, 0) and self.step(x, y, 0, dy)):
                continue
            yield x + dx, y + dy

    def flood(self, starts, closed=frozenset()):
        seen = {tuple(s) for s in starts if tuple(s) not in closed and self.open(*s)}
        queue = deque(seen)
        while queue:
            x, y = queue.popleft()
            for n in self.neighbours(x, y):
                if n not in seen and n not in closed:
                    seen.add(n)
                    queue.append(n)
        return seen


class TrailGauntletPackages(unittest.TestCase):
    def load(self, route):
        client = GAUNTLETS / route / "client"
        manifest = json.loads((client / "world.json").read_text(encoding="utf-8"))
        return manifest, Grid(client / manifest["collision"]["servedGrid"]["binary"])

    def area_tiles(self, grid, polygon):
        xs = [p[0] for p in polygon]
        ys = [p[1] for p in polygon]
        return frozenset((x, y) for x in range(int(min(xs)) - 1, int(max(xs)) + 2)
                         for y in range(int(min(ys)) - 1, int(max(ys)) + 2)
                         if grid.open(x, y) and inside(polygon, x, y))

    def test_the_block_names_the_route_and_its_frame(self):
        for route in ROUTES:
            manifest, grid = self.load(route)
            block = manifest["gauntlet"]
            self.assertEqual(block["schema"], "eloria-trail-gauntlet-v1")
            self.assertEqual(block["style"], "trail")
            self.assertEqual(block["serverCells"], [grid.width, grid.height])
            self.assertEqual(manifest["coordinateTransform"]["serverCells"], [grid.width, grid.height])
            kinds = [s["kind"] for s in block["sections"]]
            self.assertEqual(kinds[-1], "court", route)
            self.assertEqual(sum(1 for k in kinds if k == "arena"), 5, route)
            self.assertEqual([s["order"] for s in block["sections"]], list(range(1, len(kinds) + 1)))

    def test_the_registry_knows_the_route_and_its_copies(self):
        maps = json.loads(REGISTRY.read_text(encoding="utf-8"))["maps"]
        for route in ROUTES:
            entry = maps[route]
            self.assertTrue(entry["gauntlet"])
            self.assertFalse(entry["landscapeTransitions"])
            self.assertEqual(entry["manifest"], f"res://../eloria-assets/maps/gauntlets/{route}/client/world.json")
            manifest, _ = self.load(route)
            self.assertEqual(entry["coordinateTransform"], manifest["coordinateTransform"])
            for copy in (f"{route}_2", f"{route}_3"):
                self.assertEqual(maps[copy], {"alias": route})

    def test_the_arrival_reaches_the_vault_along_the_route(self):
        for route in ROUTES:
            manifest, grid = self.load(route)
            block = manifest["gauntlet"]
            reach = grid.flood([block["arrival"]["tile"]])
            self.assertEqual(len(reach), manifest["collision"]["servedGrid"]["walkableTiles"],
                             f"{route}: walkable ground the arrival cannot reach")
            vault = self.area_tiles(grid, block["vault"]["area"])
            self.assertTrue(vault and vault <= reach, route)
            for tile in block["route"]:
                self.assertTrue(grid.open(*tile), f"{route}: route tile {tile} is closed")

    def test_there_is_no_shortcut_round_any_arena(self):
        """Close an arena and the arena before it no longer reaches the one after it."""
        for route in ROUTES:
            manifest, grid = self.load(route)
            block = manifest["gauntlet"]
            areas = [self.area_tiles(grid, s["area"]) for s in block["sections"]]
            stops = [frozenset({tuple(block["arrival"]["tile"])})] + areas + \
                    [self.area_tiles(grid, block["vault"]["area"])]
            for index in range(1, len(stops) - 1):
                before, closed, after = stops[index - 1], stops[index], stops[index + 1]
                reach = grid.flood(sorted(before - closed), closed=closed)
                self.assertFalse(reach & after, f"{route}: a way round {block['sections'][index - 1]['id']}")

    def test_every_mouth_reaches_its_own_arena_and_no_other(self):
        for route in ROUTES:
            manifest, grid = self.load(route)
            block = manifest["gauntlet"]
            areas = {s["id"]: self.area_tiles(grid, s["area"]) for s in block["sections"]}
            for section in block["sections"]:
                others = frozenset().union(*(t for sid, t in areas.items() if sid != section["id"]))
                for mouth in section["mouths"]:
                    tiles = [tuple(t) for t in mouth["spawnTiles"]]
                    self.assertGreaterEqual(len(tiles), 60, f"{route}: {mouth['id']} has room for too few")
                    for tile in tiles:
                        self.assertTrue(grid.open(*tile), f"{route}: {mouth['id']} spawn {tile} closed")
                    if mouth["kind"] == "floor":
                        self.assertTrue(set(tiles) <= areas[section["id"]], mouth["id"])
                        continue
                    reach = grid.flood(tiles[:1], closed=others)
                    self.assertTrue(reach & areas[section["id"]], f"{route}: {mouth['id']} cannot reach its arena")
                    pocket = grid.flood(tiles[:1], closed=areas[section["id"]])
                    self.assertFalse(pocket & others, f"{route}: {mouth['id']} touches another arena")
                    self.assertLess(len(pocket), 400, f"{route}: {mouth['id']} leaks into the road")

    def test_checkpoints_objects_and_respawns_stand_on_open_ground(self):
        for route in ROUTES:
            manifest, grid = self.load(route)
            block = manifest["gauntlet"]
            objects = block["objects"]
            for key in ("stagingExit", "vaultExit", "cache"):
                self.assertTrue(grid.open(*objects[key]["tile"]), f"{route}: {key}")
            for plaque in objects["plaques"]:
                self.assertTrue(grid.open(*plaque["tile"]), f"{route}: plaque {plaque['objectId']}")
            ids = [objects[k]["objectId"] for k in ("stagingExit", "vaultExit", "cache")] + \
                  [p["objectId"] for p in objects["plaques"]]
            self.assertEqual(len(ids), len(set(ids)))
            for checkpoint in block["checkpoints"]:
                self.assertGreaterEqual(len(checkpoint["respawnTiles"]), 8, checkpoint["id"])
                for tile in checkpoint["respawnTiles"]:
                    self.assertTrue(grid.open(*tile), f"{route}: {checkpoint['id']} respawn {tile}")
                self.assertTrue(any(inside(checkpoint["reach"], *t) for t in block["route"]),
                                f"{route}: {checkpoint['id']} is off the road")
            for side in block["sides"]:
                self.assertTrue(grid.open(*side["nodeTile"]) and grid.open(*side["plaqueTile"]), side["id"])

    def test_the_client_grid_matches_the_served_grid(self):
        """The EWCG half-metre grid folds onto the served grid's open tiles."""
        for route in ROUTES:
            manifest, grid = self.load(route)
            raw = (GAUNTLETS / route / "client" / "collision.bin").read_bytes()
            magic, version, _, width, height = struct.unpack_from("<4sHHII", raw, 0)
            self.assertEqual((magic, version, width, height), (b"EWCG", 2, 2 * grid.width, 2 * grid.height))
            cells = raw[16:]
            mismatched = 0
            for y in range(grid.height):
                for x in range(grid.width):
                    folded = all(cells[(2 * y + dy) * width + 2 * x + dx] for dy in (0, 1) for dx in (0, 1))
                    mismatched += folded != grid.open(x, y)
            self.assertEqual(mismatched, 0, route)


if __name__ == "__main__":
    unittest.main()
