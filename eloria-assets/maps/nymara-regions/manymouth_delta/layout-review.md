# Manymouth Delta circulation review - 8 September 2026

The stilt town now occupies a legible working waterfront. Arrival stands on
the service landing at world (36, 2.2, -48), server tile (210, 222), instead of
the fallback point about 130 metres away. Information, storage, crafting and
training group around this court. The quay points toward the Great Arch,
which remains the delta's main silhouette. Its descent now stands on the
arch platform itself.

Thirty-one surveyed timber routes share thirty-two landing levels. The town
hall, market, quay, overlook and arch platform own their rectangular floors;
the connecting walks end at those edges. Curved runs have mitred bends and
continuous plank tops. Short shore branches and grading on existing dry bars
connect the network to its islands. The bed is recessed beneath each span.

The nine central houses and sixty-three outlying houses face connected
porches, with space between their roofs. The hall's gallery posts use the
correct height and depth arguments. The market roof follows the approach,
has a separate inner lining, and covers two stall rows with an open aisle.
Two orderly boat rows frame the floating-market landing. A lateen packet
uses a shared procedural rig and hull. The temple faces its southwest
approach, and a new branch reaches the lore Stelae Court.

Named NPCs keep their roles and dialogue. Wetland creatures and harvest
districts occupy the paddies, fishing reaches and groves; pirates and the
strongest enemies occupy outer fishing ground, ruined courts and the temple.
All thirty-eight previous creature records are retained by species. The
Green Temple Spring secret has moved clear of the temple mass; its identity
and contents remain unchanged.

## Measured access and cost

| Check | Before | Current |
| --- | ---: | ---: |
| Native cells connected to arrival | 316,588 / 401,409 (78.87%) | 328,145 / 414,885 (79.09%) |
| Reachable server tiles | 75,671 | 79,864 |
| Native portal positions reachable | 10 / 12 | 12 / 12 |
| Server portal positions reachable | 12 / 12 | 12 / 12 |
| Declared crossings tested on server | 0 | 31 / 31 |
| Existing creature spawns | 38, including 3 unreachable | 38, all reachable |
| Unreachable content records | 11 | 0 |
| Coplanarity checker report | 1,652.3 square metres / 199 pairs | 294.9 square metres / 31 pairs |
| Full GLB | 33,190,208 bytes | 29,783,880 bytes |
| Reduced GLB | 21,104,640 bytes | 17,783,748 bytes |
| Instanced triangles | 2,472,509 | 2,307,227 |

Native connected-cell counts use four-neighbour connectivity. Server access
uses the actual climb and corner rules from the primary town arrival.
All fourteen NPCs, thirty-eight creature spawns, sixty harvestables and
twenty-two interactives are reachable. One harvest position moves by one tile
in the final correction pass. Repeating content authoring plus that correction
reproduces all five scoped configuration files. Other regions' NPC, spawn,
harvest and interactive rows are unchanged.

The new walking recipes pass four regression tests covering plank seams,
sloping bends, landing chords and rejection of overlapping sharp bends.
Across the exported route centrelines, 1,068 ray samples find no holes and
at least 0.388 metres of clearance above terrain. These samples do not
certify every edge of every deck; the unit tests separately exercise joins.

## Verification

A fresh second build reproduces world.glb, world-lod2.glb, world.json,
collision.bin and minimap.webp byte for byte. The documented refine, open and
stamp passes ran in order after each exterior build, followed by secrets,
server collision sync, map generation, portals, content and relocation.
The canonical combined interior and secrets packages were rebuilt.

The full server suite passes: 1,563 tests and 351 subtests. The client suite
reports 134 passed, 95 failed and 8,926 passing subtests. Its failure count
matches the Ssarathi checkpoint; the failures remain in the existing actor,
equipment, torso and GDScript work. Both exterior GLBs validate with zero
errors and warnings. Runtime verification samples all 331,776 server tiles
with zero grounding misses and zero errors.

Twenty-seven offline views and twenty-seven Godot GL Compatibility views
were regenerated and reviewed. Godot used --environment=manifest. The
comparison sheets use those actual engine frames. Captures demonstrate the
layout and lighting; no frame-time benchmark was taken.

## Remaining visual work

The overlap scanner still reports legacy timber-wall and door joints,
foliage cards, boats at the waterline, temple trim and small terrain contacts.
One report names the upper-paddy deck/terrain edge; the centreline clearance
survey is clear, but this is not a claim that every reported contact is solved.
Runtime warnings remain for expected cliff/deck height discontinuities and
the raised paddy watch floor above its wet bed.

The old labyrinth facade is still a plain stone face, and several original
coverage cameras favour vegetation or a pier over their subject. The full
capture boards retain those limitations visibly. The distant southeast
jungle and open sea have not been converted into additional playable content.
The reduced package still has unused pinned textures. No surface classes,
imported models or third-party textures were added.

Evidence is in references/layout-audit, including access, population,
content-repeat and reproducibility reports, three runtime contact sheets
and the town comparison.
