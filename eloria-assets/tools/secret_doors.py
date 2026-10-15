"""What the server needs to know about the secrets, read from the packages.

Shared by `continent_portals.py` (which writes the portal lines) and the
server's `tools/author_region_content.py` (which writes the interactives,
spawns, harvest nodes and special areas), so the two never disagree about an
object id or a tile.

Sources:

* `interiors/<region>_secrets/world.json` - the sections: arrival tile, the
  tiles each area and spawn covers, the harvest nodes and interactives, and
  the exits its stones and tunnels open.
* the region manifests (and the insides manifests, and Four Gates) - the
  entrances: `interactives` of kind `secret`, each naming the map and spawn
  it opens onto, its key item and the text a player reads on using it.

Object ids: entrances take 500 upward on the map they stand on, in id order;
a secrets map's own interactives take 600 upward and its harvest nodes 700
upward, so nothing collides with the boards, caches and waygates the content
tool numbers from 13 and 20.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

REGIONS_DIR = "maps/nymara-regions"
SECRET_REGIONS = ("amberwood", "mirrorhold", "amethyst_barrens", "crownwater", "westhaven",
                  "grey_moors", "manymouth_delta", "verdant_stair", "whitehorn_range",
                  "ssarathi_ruins", "sunmane_steppe", "four_gates")
# insides map id -> package directory under interiors/
INSIDES_PACKAGES = {
    "resonant_vault": "amethyst_barrens_insides", "grey_moor_barrows": "grey_moors_insides",
    "westhaven_insides": "westhaven_insides", "verdant_stair_insides": "verdant_stair_insides",
    "manymouth_flooded_labyrinth": "manymouth_delta_insides",
    "whitehorn_glacier_temple": "whitehorn_insides", "ssarathi_royal_archive": "ssarathi_insides",
    "drowned_crown": "crownwater_insides", "mirrorhold_interiors": "mirrorhold_interiors",
}
ENTRANCE_BASE = 500
FURNITURE_BASE = 600
NODE_BASE = 700


@dataclass
class Entrance:
    map_id: str
    object_id: int
    id: str
    tile: tuple[int, int]
    destination: str
    spawn: str
    key: str
    label: str
    name: str
    position: list = field(default_factory=list)


def _manifest(assets: Path, relative: str) -> dict | None:
    path = assets / relative
    if not path.is_file():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def to_tile(position, transform) -> tuple[int, int]:
    origin = transform["serverOrigin"]
    metres = float(transform.get("metresPerTile", 1.0) or 1.0)
    return (int(round(position[0] / metres + origin[0])), int(round(origin[1] - position[2] / metres)))


def secrets_manifests(assets: Path) -> dict[str, dict]:
    """secrets map id -> its manifest, for every region that has one."""
    out = {}
    for region in SECRET_REGIONS:
        doc = _manifest(assets, f"{REGIONS_DIR}/interiors/{region}_secrets/world.json")
        if doc:
            out[f"{region}_secrets"] = doc
    return out


def entrance_maps(assets: Path) -> dict[str, dict]:
    """map id -> manifest, for every map that can carry a secret entrance."""
    out = {}
    for region in SECRET_REGIONS:
        rel = ("maps/four-gates/world.json" if region == "four_gates"
               else f"{REGIONS_DIR}/{region}/world.json")
        doc = _manifest(assets, rel)
        if doc:
            out[region] = doc
    for map_id, package in INSIDES_PACKAGES.items():
        doc = _manifest(assets, f"{REGIONS_DIR}/interiors/{package}/world.json")
        if doc:
            out[map_id] = doc
    return out


def entrances(assets: Path) -> dict[str, list[Entrance]]:
    """Every secret entrance, by the map it stands on, numbered from 500."""
    out: dict[str, list[Entrance]] = {}
    for map_id, doc in entrance_maps(assets).items():
        transform = doc["coordinateTransform"]
        records = [e for e in doc.get("interactives", []) if e.get("kind") == "secret"]
        records.sort(key=lambda e: e["id"])
        for index, entry in enumerate(records):
            tile = entry.get("serverTile") or to_tile(entry["position"], transform)
            out.setdefault(map_id, []).append(Entrance(
                map_id=map_id, object_id=ENTRANCE_BASE + index, id=entry["id"],
                tile=(int(tile[0]), int(tile[1])), destination=entry["destinationMap"],
                spawn=entry["destinationSpawn"], key=entry.get("key", "") or "",
                label=entry.get("label", "") or "A way down.", name=entry.get("name", entry["id"]),
                position=list(entry.get("position", []))))
    return out


def spawn_tile(manifest: dict, spawn_id: str) -> tuple[int, int] | None:
    transform = manifest["coordinateTransform"]
    for spawn in manifest.get("spawnPoints", []):
        if spawn["id"] == spawn_id:
            return to_tile(spawn["position"], transform)
    return None


def sections(manifest: dict) -> list[dict]:
    return list(manifest.get("sections", []))


def furniture(manifest: dict) -> list[dict]:
    """A secrets map's own interactives, numbered from 600 in id order."""
    items = sorted(manifest.get("interactives", []), key=lambda e: e["id"])
    out = []
    for index, entry in enumerate(items):
        tile = entry.get("serverTile") or to_tile(entry["position"], manifest["coordinateTransform"])
        out.append(dict(entry, object_id=FURNITURE_BASE + index, tile=(int(tile[0]), int(tile[1]))))
    return out


def nodes(manifest: dict) -> list[dict]:
    """A secrets map's harvest nodes, numbered from 700 in id order."""
    items = sorted(manifest.get("harvestables", []), key=lambda e: e["id"])
    out = []
    for index, entry in enumerate(items):
        tile = entry.get("serverTile") or to_tile(entry["position"], manifest["coordinateTransform"])
        out.append(dict(entry, object_id=NODE_BASE + index, tile=(int(tile[0]), int(tile[1]))))
    return out


def nearest_open(walkable, tile, minimum: int = 0, limit: int = 4):
    """The nearest tile `walkable(x, y)` accepts, between `minimum` and `limit`
    steps out from `tile`; the entrance prop itself is solid, so the tile a
    player stands on to use it is the first open one beside it."""
    x, y = tile
    for radius in range(minimum, limit + 1):
        ring = []
        for dy in range(-radius, radius + 1):
            for dx in range(-radius, radius + 1):
                if max(abs(dx), abs(dy)) == radius:
                    ring.append((x + dx, y + dy))
        ring.sort(key=lambda t: ((t[0] - x) ** 2 + (t[1] - y) ** 2, t))
        for candidate in ring:
            if walkable(*candidate):
                return candidate
    return None
