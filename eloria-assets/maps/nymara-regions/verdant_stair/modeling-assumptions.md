# Verdant Stair modelling assumptions

These are the decisions taken where the brief, the concept art and the existing
runtime did not fully determine the answer. Each one is a place a reviewer may
reasonably want to overrule the build.

1. **The region is a diagonal staircase, and the terrain is authored as one.**
   The aerial concept is a single composition: a turquoise lagoon in the low
   south-west corner, and from it a flight of great terraces climbing
   north-east — each a level shelf of cut limestone edged by a cliff riser with
   waterfalls pouring off it — up to the temple on the highest shelf. Rather
   than sculpt noise and drop places on it, the heightfield is a function of
   position along that diagonal. Everything is placed in **stair coordinates**:

       s = (x - z) / 2    how far up the stair
       c = (x + z) / 2    how far along a terrace

   `s` alone decides which shelf a place stands on. `region._check_anchors()`
   asserts every anchor's `s` falls inside the shelf it claims, at import, so a
   courtyard that would sit halfway down a cliff is a build error rather than
   something noticed in a capture six hours later.

2. **Eight terraces, and their heights do not scale with the region.**
   Seabed −13, strand 0.4, quay 7, lower 24, middle 46, upper 72, temple 100,
   summit 124 metres. The riser gaps are deliberately narrow: 2.5 units of
   design space is about 10.6 m of ground for a 17–28 m rise, which is a cliff.
   The first draft used 6-unit gaps — 25 m of ground for the same rise, a
   40° ramp a player simply walks up — and the region stopped reading as a
   stair at all. The one wide gap is seabed to strand, which is a beach and
   should be a ramp.

   A 24 m cliff is a 24 m cliff whether the map is 192 m or 576 m across.
   Doubling relief along with area would double every climb a player makes and
   change no picture, so only the horizontal composition is scaled.

3. **The extent is 576 m × 576 m on a 96 × 96-tile server map at one metre per
   tile**, the shape Amberwood, Mirrorhold, Amethyst Barrens and Crownwater
   already use. The arrival datum moves from server (58, 58) to (174, 174), so
   it still lands on the Godot origin. `../server-collision/verdant_stair.bin` is
   regenerated to match and must be loaded server-side — see
   `validation-report.md` for what the server does and does not do with it.

4. **The previous package's bounds were wrong.** It centred a flat ±96 m
   terrain on the origin with `terrainHeightRange: [0, 0]`, which leaves every
   server tile beyond about (154, 154) with no ground under it. This build
   covers the whole reachable footprint and verifies it tile by tile.

5. **The gorges are cut after the roads, not before.** Every gorge is a bridge
   site, so a route runs up to each one, and `grade_path` levels its corridor
   with `flatten=0.90`. Carving the ravines first — the obvious order — meant
   the roads quietly filled them back in: the aqueduct arcade ended up standing
   on ground a metre below its own deck with nothing to span, and the rope
   bridges crossed a shallow dip. `region.carve_ravines()` therefore runs last,
   and a road that meets a gorge now ends at a real edge, which is what the
   bridge is for.

6. **Sea level is y = 0 and the lagoon closes the south-west corner.** The
   north and east edges are walled by cliffs inside a 30 m margin. The west and
   south edges are partly water, so those two are raised only where the ground
   is already landward of the shoreline — a rim applied to the whole edge would
   have walled off the open sea.

7. **Wet rock is placed where a fall actually lands.** The class is authored,
   not derived from slope: the rule is proximity to a watercourse *and* being
   on a riser. Applied to whole riser bands instead — the first attempt — it
   turned a seventh of the map into spray-wet stone.

8. **Jungle density is per area, not per region.** Trees are scattered on an
   8.6 m nominal grid and thinned on paths, above 110 m and below 6 m. Detail
   tier is chosen by distance to the nearest authored route: high inside 12 m,
   mid inside 30 m, far beyond. Those thresholds are tight on purpose. At the
   first attempt's 26 m / 70 m, thirty-odd routes cross the map and almost
   every tree was "near" one, so almost nothing landed on the far tier and the
   wood alone came to 9.7 M triangles.

9. **Elevated decks own their server cell.** The client grounds actors on the
   highest walk surface below a downward ray, and a flat server grid cannot
   hold two levels. Bridge decks, canopy platforms, the quay and the stair
   treads therefore take their footprint in `collision.bin` at deck height; the
   ground beneath them is not separately walkable. This is a design decision,
   not an oversight.

10. **Population is the server's, not invented.** Unlike Amberwood — whose
    names are all placeholders because no authoritative source was available —
    every NPC, creature group, harvestable and interactive in `world.json` is
    transcribed from `eloria-server/config/eloria/*.txt` for `verdant_stair`,
    at the tile the server records, scaled from the 192-cell map to 576 by
    three. Where a recorded tile lands on water or on a cliff face the marker
    is moved to the nearest standable cell and the move is listed in
    `world.json`'s `buildNotes`. Place names for the *terrain* — the terraces,
    the temple, the cenote — are still invented, because nothing authoritative
    names them.

11. **Two portals, because the server has two.** `config/eloria/maps.txt` gives
    Verdant Stair has two exterior neighbours in CONTINENT.md: Ssarathi
    Ruins at the western Temple Road and Sunmane Steppe at the eastern pass.
    The western trigger stands on the strand; a fitted stair climbs to the
    quay road, then the lower town. The eastern pass follows the quarry shelf.

12. **Jade is a cut stone, not verdigris and not metal.** `metallic` stays at
    zero. The Amethyst Barrens notes record what a metallic surface does in a
    client with no reflection probe: every spire cap came out charcoal.

13. **Tangents are not exported.** Godot's glTF importer generates them for
    normal-mapped materials, and shipping them would add sixteen bytes a vertex
    to a package already dominated by vertex data.

14. **`collision.bin` height bytes clamp at 63.** The legacy six-bit field
    tops out at 10.4 m and cannot express this region's 0–129 m relief. The
    grid is authoritative for walkability; the Godot loader takes elevation
    from the rendered walk surfaces, not from this file. The encoding datum is
    recorded in `world.json`.

15. **The reduced package is a second GLB, not a runtime LOD switch.**
    `world-lod2.glb` carries far-tier vegetation only, no ground clutter and
    half-resolution textures. Nothing in the current Godot loader selects
    between them.

16. **The QA README and the asset manifest disagree, and the painting wins.**
    `qa/regions/verdant-stair/README.md` describes "a stepped basalt route";
    `NYMARA_ASSET_MANIFEST.md` says "jungle limestone stairs and waterfalls".
    The concept art shows pale bedded limestone with jade-green architecture,
    so the region is built in limestone and the conflict is noted rather than
    silently resolved.
