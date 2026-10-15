# Manymouth Delta coverage map

What is authored where, so a reviewer can find any of it and see what is thin.

Coordinates are Godot metres (`x`, `z`), north toward `-Z`. The playable
footprint is `x ∈ [-174, 401]`, `z ∈ [-401, 174]`; server tile `(sx, sy)` maps
as `x = sx - 174`, `z = 174 - sy`.

## The region at a glance

| | |
| --- | --- |
| Extent | 576 m × 576 m, 331,776 reachable server tiles |
| Terrain relief | −25.83 m (whirlpool throat) to +14.82 m (temple summit) |
| Sea level | 0.0 |
| Walkable | **30.0%** of tiles — bar tops, walkway decks, quays, stairs |
| Swimmable | **64.1%** of tiles, mean depth 5.1 m, max 24.6 m |
| Blocked and dry | the remainder: steep bar edges and the rock headland |
| Islands | 23 named, ~270 unnamed bars |
| Walkway network | 27 routes, 73 deck segments, 28 landing stairs |

## Named places

### Ring one — the subject of the aerial

| Place | World (x, z) | Server tile | What is there |
| --- | --- | --- | --- |
| The Manymouth Arch | (114, −114) | (288, 288) | The broken glyph ring over the whirlpool, its drowned approach platform, 14 stelae in the shallows |
| Arch stair | (81, −93) | (255, 267) | The paved landing and spawn point on the ruin's approach |
| Stilt town | (36, −48) | (210, 222) | 22 stilt houses over water, the region's default spawn |
| The Tide Hall | (30, −61.5) | (204, 235.5) | Three-tier hipped hall, bronze ridge caps and finial (panel 2) |
| The Long Market | (13.5, −27) | (187.5, 201) | Bent-timber barrel hall with a stretched canopy (panel 4) |
| Town quay | (54, −33) | (228, 207) | Railed quay deck with ladder, net racks, traps and jars (panel 3) |
| Floating market | (−36, −9) | (138, 183) | 24 moored awning boats with produce (panel 6) |
| The Root Landing | (81, −180) | (255, 354) | A great banyan and a deck built beside its roots (panel 5) |
| The Long Look | (156, 18) | (330, 156) | Plank overlook deck onto the whole fan (panel 9) |

### Ring two

| Place | World (x, z) | What is there |
| --- | --- | --- |
| Paddy terraces | (−51, −258) | Three stepped paddies, 219 lotus beds, 301 rice clumps (panel 7) |
| The Paddy Watch | (−12, −276) | A tall two-storey stilt watch |
| Paddy hamlet | (−84, −234) | 8 stilt houses |
| The Green Temple | (297, −309) | Four-stage battered temple, bronze string courses, summit shrine, processional stair |
| Temple quay | (264, −276) | 6 stilt houses, quay, spawn point |
| Mouth of the Flooded Labyrinth | (198, −3) | Cut arch in the rock headland, portal to the interior map (panel 8, threshold only) |
| Mangrove reach | (−114, −144) | The dense mangrove channel of panel 1 |
| Sea landing | (−132, −330) | 5 stilt houses where the delta gives out into open sea |
| The Stelae Court | (228, −228) | Nine standing stones and ruin rubble on a bar |

### Ring three

`east_hamlet` (351, −174) · `south_hamlet` (174, 99) · `west_hamlet` (−129, 39) ·
`north_fishing` (102, −351) · `boat_yard` (−18, 84) · `upper_paddy` (48, −330) ·
`far_bar` (297, 57) · `east_watch` (363, −36) · `south_shrine` (72, 123) ·
`deep_grove` (204, −138)

## Watercourses

Seven named distributaries, all in `world.json` under `water.channels` as
waypoint polylines.

| Channel | Type | Floor |
| --- | --- | --- |
| `great_mouth`, `north_mouth`, `temple_mouth`, `south_mouth` | navigable | −7.2 m |
| `market_reach`, `mangrove_cut`, `cave_run` | shallow braid | −5.1 m |

Plus an unnamed ridged-noise braid network cut 3.6 m into the flats between the
bars, which is what makes the aerial read as a delta rather than an archipelago.

## Population and metadata

All carry `"authority": "server"`; nothing is baked into the mesh.

| | Count | Where |
| --- | --- | --- |
| Landmarks | 12 | Listed above |
| Interactives | 7 | Arch gate, labyrinth door, hall door, market scales, ferry post, temple altar, paddy sluice |
| NPC markers | 46 | Villagers, traders, ferrymen, acolytes, farmers, fishers, a shipwright |
| Creature markers | 26 | Delta crocodile, drowned sentinel, labyrinth crawler, shore raider, canopy serpent, silt wight |
| Harvestables | 51 | Lotus root, rice, mangrove bark, banyan resin, river fish, shell lime, salt pan, palm heart |
| Portals | 5 | Four edge landings plus the labyrinth mouth |
| Spawns | 3 | `default` (town bar), `arch-stair`, `temple-quay` |

**Only two of the five portals exist server-side.** The Ssarathi Ruins pair and
the Flooded Labyrinth pair are in `config/eloria/maps.txt` on the server branch.
The Verdant Stair, Westhaven and Crownwater landings are client-side alignment
metadata only: wiring them would mean editing three other regions' map entries,
which is outside this region's scope.

## Where the coverage is thin

Stated plainly, because a coverage map that only lists what exists is a sales
document.

* **The north-west quarter is nearly empty.** By design — it is the open sea the
  painting shows — but it means roughly an eighth of the playable footprint has
  one hamlet (`sea_landing`) and nothing else. A player who swims out there
  finds water.
* **The jungle head in the south-east corner is scenery, not a place.** It has
  ground, trees and a horizon, and no authored content at all.
* **Interiors: four, on one map.** The Flooded Labyrinth, the Underdeck, the
  Tide Hall and the Sanctum, at `../interiors/manymouth_delta_insides/`. Every
  *other* building in this region is exterior-only: the twenty-two houses of the
  stilt town, the market hall, the hamlets and the watchtowers have no insides.
* **No sailing craft.** The region has dugouts and awning boats. Panel 4's
  lateen-rigged boats do not exist as a kit piece.
* **No pink.** Two panels use blossom as their accent colour and the region has
  no blossom material; the study vignette's petals are green foliage cards.
* **Creature and NPC markers are evenly scattered around their anchors**, not
  placed to a designed encounter layout. They are positions for the server to
  use or ignore.


## September 8 coverage update

This supersedes the portal, settlement and sailing-craft counts above.
The region has four connected exterior landings and eight doors into the
shared flooded-labyrinth interior map. All are surveyed from the town arrival.
Thirty-one routes include shore spurs and a branch to the lore Stelae Court.
The town service floor groups information, storage, crafting and training;
the quay points toward the Great Arch and its descent.

The shared waterfront recipes supply continuous floors, cut landing joins and
a lateen rig. Houses have road-facing porches; the market aisle and its boat
rows are deliberate. Existing server NPC identities, dialogue, wildlife
populations and resource labels are preserved. The open sea remains scenery;
the pass does not turn the entire water footprint into traversable land.
See layout-review.md and references/layout-audit for measured results and
current views. The original captures and notes are no longer the layout spec.
