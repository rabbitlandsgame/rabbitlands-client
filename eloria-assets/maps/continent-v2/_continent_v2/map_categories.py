"""map_categories.py: the shop categories a map dot is coloured by - one table for the publishers and the client.

A service NPC's `mapCategory` (an NPC marker in a territory's scene, or an interior shopkeeper in
content/landfall_town.json) and a building door's `category` (content/landfall_town.json) name one of CATEGORIES. The
client draws the shopkeeper's dot in that colour on the minimap, the Tab map and the region preview, and the door of
the building the shop is in in the same colour; a door without a category is the tan entrance dot (ENTRANCE_COLOUR),
as a cave mouth is.

The client's copy is godot-client/src/ui/service_map_overlay.gd CATEGORY_COLOURS (the tan dot is
entrance_map_overlay.gd DOT_COLOUR), and the map legend (godot-client/src/app/main.tscn, MapLegend) names every
category with a round dot in its colour. godot-client/tests/test_continent_v2_cartography.py keeps the three equal.

A category the table does not hold is refused (CategoryError), never dropped: publish_client.py and
publish_npc_metadata.py used to keep only general_store and tavern markers and drop any other without a word, and a
shop without its dot is a shop nobody finds. Add a category here, in the client's table and in the legend together.
Pure Python: no third-party imports.
"""
from __future__ import annotations

# category -> (dot colour as RRGGBB, the legend's name for it)
CATEGORIES = {
    "tavern": ("ef795f", "Tavern"),
    "general_store": ("4fc67a", "General store"),
    "flower_shop": ("e687da", "Flower shop"),
    "magic_shop": ("e2cf48", "Magic shop"),
    "blacksmith": ("9d73d8", "Blacksmith"),
}
# A door without a category (a cave mouth, a house, the keep): the tan entrance dot, and its legend line.
ENTRANCE_COLOUR = "e8d09b"
ENTRANCE_LEGEND = "Insides entrance"


class CategoryError(ValueError):
    """A map category the table does not hold."""


def check(category, where: str = "") -> str:
    """The category, when the table holds it; CategoryError otherwise (`where` names the record for the message)."""
    if category not in CATEGORIES:
        prefix = f"{where}: " if where else ""
        raise CategoryError(f"{prefix}map category {category!r} is not one of {sorted(CATEGORIES)} "
                            "(map_categories.py; the client's table and the legend name the same ones)")
    return category


def colour(category=None) -> str:
    """The RRGGBB a door is drawn in: its shop's, or the tan entrance dot's for a door without a category."""
    return ENTRANCE_COLOUR if category is None else CATEGORIES[check(category)][0]


def service_category(mark: dict, where: str = ""):
    """An NPC marker's `mapCategory`, checked; None for a marker without one (an NPC that keeps no shop dot)."""
    category = mark.get("mapCategory")
    if category in (None, ""):
        return None
    return check(category, where or str(mark.get("id", mark.get("name", "an NPC marker"))))


def service_markers(npc_markers) -> list[dict]:
    """A territory manifest's `serviceMarkers`: one per NPC marker with a map category, in marker order."""
    return [{"id": mark["id"], "name": mark["name"], "label": mark.get("mapLabel", mark["name"]),
             "category": mark["mapCategory"], "position": mark["position"], "serverTile": mark["serverTile"]}
            for mark in npc_markers if service_category(mark) is not None]
