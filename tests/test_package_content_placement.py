"""A server-authority marker is drawn where the server runs it.

Harvest nodes and NPC markers are declared twice in a package manifest: a
placement in metres, which is where the client draws the model, and a
`serverTile`, which is the tile the server runs the node on.

They drifted once. Several were authored on tiles their own package's walk
grid blocks, so when the server began enforcing that collision the node moved
and the model stayed behind, leaving a harvestable you could see but not
reach. `eloria-assets/tools/sync_package_content.py` moves the models onto the
server's tiles; this holds them there.
"""
import json
import math
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

# package -> the marker lists it keeps, as (path into the manifest, the field
# the placement lives in). A package may declare them at the top level or
# nested, and a point uses `position` where something with an extent uses
# `center`.
PACKAGES = {
    "stillglass": ((("interactives",), "position"),),
    "four-gates": (
        (("harvestables",), "position"),
        (("npcMarkers",), "position"),
        (("interactives",), "position"),
    ),
    "nymara-regions/amberwood": (
        (("harvestables",), "position"),
        (("npcMarkers",), "position"),
        (("interactives",), "position"),
    ),
    "nymara-regions/sunmane_steppe": (
        (("runtimePopulation", "npcs"), "position"),
        (("runtimePopulation", "resources"), "center"),
    ),
}


def entries(data, path):
    node = data
    for step in path:
        node = node.get(step) if isinstance(node, dict) else None
        if node is None:
            return ()
    return node if isinstance(node, list) else ()


class PackageContentPlacement(unittest.TestCase):
    def test_markers_stand_on_the_tile_they_declare(self):
        checked = 0
        for relative, sections in PACKAGES.items():
            path = ROOT / "eloria-assets" / "maps" / relative / "world.json"
            if not path.is_file():
                continue
            data = json.loads(path.read_text(encoding="utf-8"))
            transform = data["coordinateTransform"]
            origin_x, origin_y = transform["serverOrigin"]
            metres = transform["metresPerTile"]
            for section, field in sections:
                for entry in entries(data, section):
                    tile = entry.get("serverTile")
                    placement = entry.get(field)
                    if not tile or not placement or len(placement) != 3:
                        continue
                    # invertServerY: the server's y runs north to south. A
                    # marker stands on the tile that contains it: with the
                    # tile-centres-v1 convention every centre lies at x.5,
                    # which round() would split by parity, so floor.
                    rounded = [math.floor(placement[0] / metres + origin_x),
                               math.floor(origin_y - placement[2] / metres)]
                    self.assertEqual(
                        rounded, list(tile),
                        f"{relative} {'/'.join(section)} {entry.get('id')} is "
                        f"drawn at {placement[0]}, {placement[2]} - tile "
                        f"{rounded} - but declares tile {tile}")
                    checked += 1
        self.assertGreater(checked, 80)


if __name__ == "__main__":
    unittest.main()
