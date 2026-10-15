# Whitehorn Range layout review — September 2026

The low southern gate is now a provisioned refuge on the approach to the range.
The Ration House and repair shelter flank one open court. Sister Arel, Korrin,
the gate brother and the ration sister have deliberate posts beside the bank,
field crafting, information board and training point. Arrival is world
(-12, 19.75, 69), server tile (162, 105). The three continent crossing ids and
destinations remain unchanged.

The eastern mine road goes around the gorge head on a 5.5 m haul road and
reaches a broad worked bench, ore sledges, fuel and a shelter. It no longer
asks carts to cross an unbridged cut. Eight weather refuges give the lower
camp, bridge watch, overlook, east camp, mine yard and last pilgrim rest a
purpose. Seventeen authored road and approach polylines describe their
connections in the manifest.

The pilgrim ascent skirts the frozen falls and climbs the temple shelf in
switchbacks. The obsolete direct trail and oversized lower terrace were
removed. Twelve encroaching rock/tree placements were cleared from the authored
roads with the shared corridor pass. Three slender snowy pinnacles carry the temple's silhouette above
its existing marble facade. The western watch's Cascade Cave has a visible
ice mouth, backing shoulder and approach; its interior trigger no longer
stands inside the watch cairns. The temple return spawn uses its podium.

The two rope bridges have frozen bank surveys under navigation.crossings:
(41, 18, -54) to (61, 22.3, -104), and (186, 42.2, -75) to
(186, 49.4, -126). The shared suspension bridge uses a continuous profiled
walking skin, with ropes outside its 2.4 m width. The previous terrain search
could select a gorge slope, or both landings on the same bank, after another
road or yard changed the terrain.

Wildlife keeps every existing species and count. Grazers occupy lower
sheltered shelves; predators and glacier creatures range beyond the gorge;
the most dangerous roster occupies the northern slopes. Mine and ridge rock
carry coal, quartz and flint; low pine shelves carry bramble and toadstool.
Names, rare ingredients, secret keys and contents are retained.

## Verification

| Check | Result |
| --- | --- |
| Reachable from primary arrival | 24 departures, 14 NPCs, 59 creature spawns, 55 harvest nodes, 21 interactives |
| Unreachable authored content rows | 7 before, 0 after |
| Native walkable cells in arrival component | 880,752 / 930,123 before; 890,976 / 929,582 after |
| Server walkable tiles in arrival component | 218,336 before; 217,795 after |
| Full server Python suite | 1,767 passed; 546 subtests passed |
| Full client Python suite | 169 passed; 86 failed; 9,078 subtests passed |
| Client failure comparison | Exact same failure set as the freshly rebased develop baseline |
| Crossing, connection, collision, maps and layout checks | 113 passed |
| Runtime grounding | 331,776 samples, no misses, no errors |
| GLTF validation | No errors or warnings; four informational unused material notices |
| Coplanar overlap report | 120.8 square metres / 39 pairs before; 49.3 / 37 after |
| Determinism | Fresh exterior GLB, manifest, collision and minimap reproduce byte-for-byte |
| Content preservation | All species/resource counts retained; unrelated maps' NPC, spawn, harvest and interactive rows unchanged |

The corrected native grid is refined, opened and stamped in the documented
order. Interiors and secrets are rebuilt and exported. The server collision,
generated maps, portals, authored content and scoped relocation have been
regenerated. Content regeneration repeats the same five profile files.
After the updated profile's protection points settle, a repeat collision sync
reproduces the identical vendored grid.

The GLB grows from 19,501,176 to 19,889,316 bytes, while instanced triangles
fall from 752,036 to 744,858. The 39 materials and 86 embedded
images are unchanged. No new surface classes or imported assets are used.

## Visual review and remaining work

The concept boards, 31 offline frames and 31 Godot GL Compatibility frames
were inspected. Godot used --environment=manifest. Reviewed WebP frames and
four contact sheets are under references; comparisons were rebuilt against
the concept boards. The gate, bridge deck, mine yard, eastern saddle and
temple ascent include deliberately placed player-height views.

The remaining overlap warnings are mostly legacy march-station walls,
foliage, small masonry contacts, temple statuary and its stair foot. The
runtime discontinuity warning describes cliffs and ground below bridges.
The fold also reports stranded legacy scenery/metadata samples; the actual
server-owned content audit above uses the primary arrival and has none.

Snow/rock boundary dithering and repetitive cliff textures remain apparent
in Godot. The original shrine backs, frozen cascade backing masses and broad
mountain walls are still simpler than the concept art. This pass establishes
circulation and inhabited places; those older forms remain candidates for a
later asset-quality pass. Shelters are open weather protection, not a new town
of inaccessible facade houses.
