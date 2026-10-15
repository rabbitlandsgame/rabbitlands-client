# Ssarathi Ruins circulation review — 7 September 2026

The drowned city's working ground now explains how people enter, trade and
maintain it. The great temple remains the northern silhouette and the paved
axis points toward it. The arrival is an Archive Supply Quay with two lined
shelters, cargo at its edges and grouped information, storage, crafting and
training posts. Existing NPC names, roles and dialogue remain intact.

The eastern market has ten stalls in two facing rows, an open aisle and a
shrine at its head. Obsolete kerbs across both courts are removed. Lowland
wetland creatures occupy the docks and courts; dangerous constructs, wyverns
and the dragon occupy the northern terraces and jungle rim. All 26 existing
spawn records are retained by species, including the three gloom wyverns.

## Water routes and destinations

Five surveyed stone bridges now meet their shore levels. The Water Gate
faces across the ceremonial axis, with separate solid footprints for its
pylons and a clear opening beneath the lintel. Its old quarter-turn put a
pylon in the approach; the player-height review exposed that mistake. The southern spur
roads converge on the Water Gate's main crossing; the two overlapping angled
spans there are removed. Eight sloping, pile-supported jetties point into actual
water across the three landings. Three procedural punts provide a visible
reason for the docks. A ruin block that enclosed the southern berth is removed.

The stable south-gate portal id still leads to Crownwater. Its trigger is now
on the western of the two southern jetties, at world (8, 99), with its cargo
station on the dry quay at (8, 132). No continent graph edge changes.

The formerly drowned cistern entrance has a 58 m approach from Lily Court and
a pile-supported sounding stage with an open shaft and windlass. Its trigger
and return stand on the work floor at (-97, 2, -60). The Great Temple Focus
secret now stands on the Sun Vault forecourt instead of beneath the closed
temple mass; its Iron Rune requirement and contents are unchanged.

## Reachability and geometry

| Check | Before | Current |
| --- | ---: | ---: |
| Native ground reachable from arrival | 478,536 / 540,340 (88.56%) | 485,525 / 542,590 (89.48%) |
| Reachable server tiles | 115,353 | 115,869 |
| Authored portal positions reachable in native grid | 10 / 11 | 11 / 11 |
| Authored portal positions reachable in server grid | 11 / 11 | 11 / 11 |
| Complete declared crossings | one legacy short stub | 14 / 14 |
| Coplanarity checker overlap | 1,117.1 m² / 91 pairs | 852.9 m² / 86 pairs |
| Full GLB | 24,809,384 bytes | 26,215,864 bytes |
| Instanced triangles | 1,820,656 | 1,847,337 |

The Water Gate also passes 99 approach samples across a four-metre-wide
central lane in both native and server grids. Both pylon centres remain
blocked, and the ground is continuous beneath the opening.

The 14 declared crossings cover five bridges, eight jetties and the cistern
approach. Direct ray probes across all their widths and lengths tested
4,510 points: zero deck holes, zero survey-height
deviations at the reported precision, and minimum terrain separation 0.22 m.
The bed is recessed beneath decks; no water is filled to manufacture access.

All 14 NPCs, 26 creature spawns, 37 harvestables and 22 interactives are reachable
in the final authored server grid. Scoped relocation moved zero records after
the final content pass. A second content authoring pass reproduced all five
configuration files' scoped records. Other regions' NPC, spawn, harvest,
interactive and special-area records are unchanged. Portal regeneration also
refreshes inbound links belonging to Ssarathi's secret package.

## Verification and captures

A clean second build reproduced world.glb, world-lod2.glb, world.json,
collision.bin and minimap.webp byte for byte. Both GLBs pass structural
validation with zero errors and zero warnings. The canonical combined interior
was rebuilt with build_insides.py, then its collision exported. The exterior
ran refine_walk_heights, open_walk_surfaces and stamp_solid_landmarks in that
order, followed by its secret build and scoped server synchronization.

Runtime verification sampled 331,776 positions with zero grounding misses and
zero errors. Five warnings remain: temple/cliff height discontinuities, the
rough existing Tenth Mouth threshold, the temple landmark's base below its
summit, the waterfall landmark at its lip, and two native half-cell samples
outside the edge of a diagonal bridge. Both edge samples were already open
without rendered decks in the baseline; the shared whole-tile expansion extends
the diagonal footprint. One server centre lies 0.13 m outside the deck. This
pass does not claim those legacy edge cells are repaired.

The coplanarity report is improved, not clean. Remaining overlaps include
existing temple stage skins, colonnade joins, ruin masonry, vegetation and
waterfalls. New bridge and jetty walking skins are separated from the terrain.
The full package's 1.85 million instanced triangles remains above the historical
1.5 million visible-triangle guideline; visibility and frame time were not
profiled. LOD2 carries 978,596 instanced triangles.

Thirty offline views and thirty real Godot GL Compatibility views were
recaptured from the same camera index. Godot used --environment=manifest.
The capture search adjusts nine older unpinned views; the six new player-height
views and corrected Water Gate are fixed and retain their authored positions.
The player-height review includes the service quay, cistern approach and
stage, ferry berth, market aisle and Coil Bridge. Conflicting kerbs and the
jetty ruin were removed after that review, then the full camera set recaptured.
The comparison boards now use those real engine frames.

- [Service quay](references/godot-captures/50-quay-services.webp)
- [Cistern approach](references/godot-captures/51-cistern-walk.webp)
- [Sounding stage](references/godot-captures/52-sounding-stage.webp)
- [Ferry berth](references/godot-captures/53-packet-berth.webp)
- [Market aisle](references/godot-captures/54-market-aisle.webp)
- [Coil Bridge](references/godot-captures/55-coil-bridge-walk.webp)
- [Concept panels](references/comparisons/panel-comparison.webp)
- [Aerial comparison](references/comparisons/aerial-comparison.webp)

The full server suite passes: 1,532 tests and 351 subtests. The client suite
reports 130 passes, 95 failures and 8,926 passing subtests. Its exact failure
set matches the published baseline, including upstream rig/equipment and
GDScript failures; no new failure is introduced by this pass. The 12 shared
routecraft tests pass, including the open-shaft floor and nearby secret
placement checks.
All build, capture and test processes use the same four logical CPU cores.

## Shared kit and remaining art work

The shared civiccraft.sounding_stage recipe takes region materials and supplies
the open circular work floor, piles, coping and windlass. Existing shared
arcaded_causeway, sloped_boardwalk, market_shelter, pitched_canopy and rowing_boat
recipes supply the other pieces. Ssarathi keeps its jade masonry, gold trim,
grey timber, striped canvas and procedural foliage; no asset packs or new
surface-class numbers are introduced.

The concept's elaborate temple relief, finer ruin facades and suspended
platform remain future art work. The northern skyline is still less dense
than the painting, and some old masonry is visibly coarse at eye level.
