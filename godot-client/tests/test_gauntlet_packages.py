"""The gauntlet packages and their registry entries hold together.

A gauntlet map is one linear route: a staging hall, seven legs each behind a
barred way, and a vault. The manifest's `gauntlet` block is what the server
tool reads, so its tiles have to be inside the map, every gate has to carry
the tile a player stands on and the tile beyond its cut, and the registry has
to know the map and its copies or the client cannot place anyone on them.
"""
import json
import struct
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
INTERIORS = ROOT / "eloria-assets" / "maps" / "nymara-regions" / "interiors"
REGISTRY = ROOT / "godot-client" / "data" / "maps" / "registry.json"
THEMES = ("amberwood_gauntlet", "whitehorn_gauntlet", "ssarathi_gauntlet", "grey_moors_gauntlet",
          "crownwater_gauntlet", "sunmane_gauntlet", "amethyst_gauntlet", "manymouth_gauntlet")
TILES = 384
WALK = ROOT / "eloria-assets" / "maps" / "nymara-regions" / "server-collision"
CLIMB = 2          # the server's max_walk_height_change, in its 0.2 m steps
STEPS = ((0, 1), (1, 1), (1, 0), (1, -1), (0, -1), (-1, -1), (-1, 0), (-1, 1))


def read_walk_grid(path):
    """The EWCG grid the server reads, as rows of height codes (0 = blocked)."""
    raw = path.read_bytes()
    magic, version, _, width, height = struct.unpack_from("<4sHHII", raw, 0)
    assert magic == b"EWCG", path
    return [raw[16 + row * width:16 + (row + 1) * width] for row in range(height)]


def flood(grid, start):
    """Every tile the server lets a walker reach from `start`: both tiles walkable, no more
    than CLIMB codes apart, and a diagonal only where both of its straight steps are."""
    height, width = len(grid), len(grid[0])

    def step(x, y, dx, dy):
        nx, ny = x + dx, y + dy
        if not (0 <= nx < width and 0 <= ny < height) or not grid[y][x] or not grid[ny][nx]:
            return False
        return abs(grid[ny][nx] - grid[y][x]) <= CLIMB

    seen = {start}
    queue = [start]
    while queue:
        x, y = queue.pop()
        for dx, dy in STEPS:
            if (x + dx, y + dy) in seen or not step(x, y, dx, dy):
                continue
            if dx and dy and not (step(x, y, dx, 0) and step(x, y, 0, dy)):
                continue
            seen.add((x + dx, y + dy))
            queue.append((x + dx, y + dy))
    return seen


class GauntletPackages(unittest.TestCase):
    def manifest(self, theme):
        return json.loads((INTERIORS / theme / "world.json").read_text(encoding="utf-8"))

    def test_every_route_has_seven_legs_a_fork_and_a_court(self):
        for theme in THEMES:
            g = self.manifest(theme)["gauntlet"]
            kinds = [leg["kind"] for leg in g["legs"]]
            self.assertEqual(len(kinds), 7, theme)
            self.assertEqual(kinds[-1], "court", theme)
            self.assertEqual(kinds.count("fork"), 1, theme)
            self.assertTrue({"hall", "cavern", "bridge", "stair"} <= set(kinds), theme)

    def test_every_gate_and_tile_is_inside_the_map(self):
        for theme in THEMES:
            g = self.manifest(theme)["gauntlet"]
            tiles = [g["staging"]["arrivalTile"], g["vault"]["spotTile"], g["vault"]["cache"]["serverTile"],
                     g["staging"]["exit"]["serverTile"], g["vault"]["exit"]["serverTile"]]
            gates = []
            for leg in g["legs"]:
                gates.append(leg["gate"])
                gates.extend(branch["gate"] for branch in leg.get("branches", []))
                tiles.extend(leg["spawnTiles"])
                if "bossTile" in leg:
                    tiles.append(leg["bossTile"])
            for gate in gates:
                self.assertIn("objectId", gate)
                tiles.append(gate["tile"])
                tiles.append(gate["beyondTile"])
                self.assertNotEqual(gate["tile"], gate["beyondTile"])
            for x, y in tiles:
                self.assertTrue(0 <= x < TILES and 0 <= y < TILES, (theme, x, y))
            ids = [gate["objectId"] for gate in gates]
            self.assertEqual(len(ids), len(set(ids)), theme)

    def test_the_registry_knows_each_route_and_its_copies(self):
        registry = json.loads(REGISTRY.read_text(encoding="utf-8"))["maps"]
        for theme in THEMES:
            entry = registry[theme]
            self.assertTrue(entry.get("gauntlet"), theme)
            self.assertEqual(entry["manifest"],
                             f"res://../eloria-assets/maps/nymara-regions/interiors/{theme}/world.json")
            transform = self.manifest(theme)["coordinateTransform"]
            self.assertEqual(entry["coordinateTransform"]["serverOrigin"], transform["serverOrigin"])
            for copy in (f"{theme}_2", f"{theme}_3"):
                self.assertEqual(registry[copy], {"alias": theme}, copy)

    def test_the_route_reads_as_one_walk_from_the_arrival(self):
        """The staging arrival and the vault stand at opposite ends of the map,
        so the road really runs the length of it."""
        for theme in THEMES:
            g = self.manifest(theme)["gauntlet"]
            start_y = g["staging"]["arrivalTile"][1]
            end_y = g["vault"]["spotTile"][1]
            self.assertGreater(abs(start_y - end_y), 300, theme)

    def test_the_server_grid_walks_every_leg_and_carries_every_spawn(self):
        """The walk grid the server reads climbs each stair, crosses each room to the next gate
        and holds every spawn tile, so no gate stands behind a step the server refuses and no
        wave lands in a wall. Every stair was shut and every wall walkable until 2026-09-06."""
        for theme in THEMES:
            grid = read_walk_grid(WALK / f"{theme}.bin")
            g = self.manifest(theme)["gauntlet"]
            legs = g["legs"]
            checks = [(tuple(g["staging"]["arrivalTile"]), tuple(legs[0]["gate"]["tile"]))]
            for index, leg in enumerate(legs):
                beyond = tuple(leg["gate"]["beyondTile"])
                after = (tuple(legs[index + 1]["gate"]["tile"]) if index + 1 < len(legs)
                         else tuple(g["vault"]["spotTile"]))
                if leg.get("branches"):
                    for branch in leg["branches"]:
                        checks.append((beyond, tuple(branch["gate"]["tile"])))
                        checks.append((tuple(branch["gate"]["beyondTile"]), after))
                else:
                    checks.append((beyond, after))
                if "bossTile" in leg:
                    checks.append((beyond, tuple(leg["bossTile"])))
                for room in (leg, *leg.get("branches", [])):
                    self.assertGreaterEqual(len(room["spawnTiles"]), 8, (theme, room["id"]))
                    for x, y in room["spawnTiles"]:
                        self.assertTrue(grid[y][x], (theme, room["id"], (x, y)))
            for start, goal in checks:
                self.assertIn(goal, flood(grid, start), (theme, start, goal))

    def test_every_walkable_tile_has_exported_ground(self):
        # The collision builder sees authored geometry before GLB batching.
        # A successful flood cannot prove the exporter retained a bridge deck.
        import sys
        sys.path.insert(0, str(INTERIORS.parent / "_toolkit"))
        import verify_runtime as runtime
        for theme in THEMES:
            package = INTERIORS / theme
            manifest = self.manifest(theme)
            document, binary = runtime.load_glb(package / "world.glb")
            triangles, _ = runtime.collect_triangles(
                document, binary, lambda name: name.startswith("Walk_"))
            rays = runtime.VerticalRayIndex(triangles)
            ox, oz = manifest["coordinateTransform"]["serverOrigin"]
            missing = []
            for y, row in enumerate(read_walk_grid(WALK / f"{theme}.bin")):
                for x, height in enumerate(row):
                    if height and rays.top_hit(x - ox, oz - y) is None:
                        missing.append((x, y))
            self.assertFalse(missing, (theme, len(missing), missing[:12]))


if __name__ == "__main__":
    unittest.main()
