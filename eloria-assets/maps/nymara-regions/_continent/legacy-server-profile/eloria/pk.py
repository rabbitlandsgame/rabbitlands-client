from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class PKZone:
    """One player-killing map or bounded arena."""

    map_id: str
    x1: int | None = None
    y1: int | None = None
    x2: int | None = None
    y2: int | None = None
    attack_defense_cap: int | None = None
    no_drops: bool = False
    no_rostogol: bool = False
    multi_combat: bool = False
    label: str = "PK area"

    def contains(self, map_id: str, x: int, y: int) -> bool:
        if map_id != self.map_id:
            return False
        if None in (self.x1, self.y1, self.x2, self.y2):
            return True
        return self.x1 <= x <= self.x2 and self.y1 <= y <= self.y2


# Provisional Eloria zones. These were Eternal Lands': Kilaran Field, the
# Tahraji Desert, Nordcarn's north cave, the Lucky Punch arena and the two
# capped arenas on Desert Pines. Not one of those maps is served, so there was
# nowhere on this world a player could be attacked and no cap ever applied.
#
# Where the real ones go is a design decision that has not been taken. What is
# here keeps the mechanics exercised on ground that exists: two full-map areas
# on the harshest open regions, one barrow interior, and two capped arenas
# inside Four Gates whose bounds are fully walkable on the map's own collision
# grid, so a duel in them can actually be fought. Expect the labels, the caps
# and the coordinates to change; expect the shape of this table not to.
PK_ZONES: tuple[PKZone, ...] = (
    PKZone("grey_moors", no_drops=True, multi_combat=True,
           label="The Grey Moors"),
    PKZone("amethyst_barrens", no_rostogol=True, multi_combat=True,
           label="Amethyst Barrens"),
    PKZone("grey_moor_barrows", multi_combat=True,
           label="Grey Moor Barrows"),
    PKZone("four_gates", 13, 25, 47, 59, 40, True,
           label="Four Gates 40 A/D arena"),
    PKZone("four_gates", 358, 27, 392, 61, 60, True,
           label="Four Gates 60 A/D arena"),
)


def pk_zone_at(map_id: str, x: int, y: int) -> PKZone | None:
    return next((zone for zone in PK_ZONES if zone.contains(map_id, x, y)), None)


def shared_pk_zone(first, second) -> PKZone | None:
    """Return the PK zone occupied by both characters, if any."""
    if first.map_id != second.map_id:
        return None
    zone = pk_zone_at(first.map_id, first.x, first.y)
    return zone if zone and zone.contains(second.map_id, second.x, second.y) else None


def capped_level(level: int, zone: PKZone) -> int:
    return min(level, zone.attack_defense_cap) if zone.attack_defense_cap else level
