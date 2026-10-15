# Ssarathi Ruins modelling assumptions

These are the decisions taken where the brief, the concept art and the existing
runtime did not fully determine the answer. Each one is a place a reviewer may
reasonably want to overrule the build.

1. **Region extent.** Ssarathi Ruins is authored at 576 m x 576 m — three times
   its original linear extent, nine times the area — on the instruction to match
   the other five production regions. One metre per tile is kept, so movement
   granularity is unchanged; the server map grows instead, from 32x32 to 96x96
   ELM tiles. The arrival datum keeps its position relative to the map, moving
   from server (58, 58) to (174, 174), so it still lands on the Godot origin.
   The whole composition is written in the original 192 m design space and
   scaled by `region.SCALE`, so the aerial concept's layout is preserved rather
   than stretched.

2. **The region is a flooded basin, not a ruin field.** The aerial is a city
   standing in shallow water, so the datum that governs everything is the
   waterline at y = 0 with a basin floor at −1.55 m. Water covers about 58% of
   the playable footprint and is ankle-to-knee deep across most of that. The
   three carved channels go to −4.6 m and are the only water a player could not
   wade. This reading is the single largest interpretive decision in the build;
   if the region is meant to be a dry ruin with ponds, almost everything else
   follows differently.

3. **The basin floor is terrain, not a hole.** The client casts its grounding
   ray at *every* server tile, not only walkable ones, so a region whose middle
   is water still needs continuous ground under it. The heightfield covers the
   whole footprint and simply sits below the waterline across most of it. Those
   tiles ground successfully and are marked unwalkable in `collision.bin`.

4. **The causeways are terrain, not decks.** Crownwater spans its open water
   with built bridge decks because its islands stand in deep lagoon. Ssarathi's
   water is shallow and the concept's causeways are plainly solid stone
   embankments retained at the waterline, so they are built as terrain plateaus
   carrying a paved surface class. This is both the accurate reading and the
   safe one for grounding: the walkable city is terrain, which the ray cannot
   miss, and only the seven genuine spans over carved channels are `Walk_`
   decks. A reviewer who wants viaducts instead should expect the grounding
   guarantee to become much harder to hold.

5. **Elevated decks own their server cell.** The client grounds actors on the
   highest walk surface below a downward ray, and a flat server grid cannot hold
   two levels. The seven channel bridges and the eight dock jetties therefore
   take their footprint in `collision.bin` at deck height; the water beneath
   them is not separately walkable.

6. **Where the crossings are, is computed, not authored.** Bridges are placed
   at the true intersections of the street polylines with the channel
   polylines. An earlier version listed the crossings by hand and three of the
   five were nowhere near the channel they were supposed to span — one of them
   re-cut the west dock down to the channel floor.

7. **Vertical relief is concentrated in one place.** The concept is a flat
   composition: its drama is in its water, its density and its temple, not in
   its topography. The basin floor, the causeways and the quarters all sit
   within four metres of the waterline; the only real verticality is the temple
   precinct (three terraced tiers to 21 m, carrying a 35 m ziggurat) and the
   jungle-clad valley walls that close the world. Playable relief is −9.9 m to
   +104.7 m, but almost all of that range is the rim.

8. **The rim closes the world on all four sides.** Amberwood leaves its west
   open because the sea closes it; Crownwater walls nothing and closes with the
   collision grid. Ssarathi is a sunken valley, so ground rises out of the water
   toward every edge and keeps rising into rock walls raised inside the margin,
   with the north wall tallest because the waterfalls come off it.

9. **New surface classes, registered rather than committed.** Ssarathi adds four
   terrain classes (23–26: silt, jade paving, jungle floor, moss stone) and
   twelve material recipes. Both are appended to the shared toolkit's tables
   **at build time** from this region's own modules, the same build-time
   extension `crownwater/source/crownkit.py` uses and for the same reason:
   nothing in `_toolkit/` is edited, so there is no shared-file merge to
   resolve, and promotion later is a copy-paste. Ids 23–26 continue the
   documented per-region allocation (7–10 Mirrorhold, 11–14 Whitehorn, 15–18
   Amethyst Barrens, 19–22 Crownwater).

10. **Ssarathi does not use the toolkit's `assign_surface_by_rule`.** That rule
    ends with an unconditional `surface = where(height < sea_level − 1, SHORE,
    surface)` with no authored-class guard, which in a region whose subject is
    drowned paving turned the ritual plaza's pool floor and the whole drowned
    quarter into beach shingle. `region._classify_surfaces` replaces it with a
    rule for a flooded basin. The shared rule is unchanged.

11. **The quarters between the streets are generated, not authored.** The
    concept's basin is packed with ruined blocks and tree-covered islets, and
    placing sixty-nine of them by hand would be sixty-nine numbers to maintain.
    They are scattered on a jittered grid, rejected wherever their footprint
    overlaps ground the streets, plazas or precincts have already claimed, and
    then built on by `populate.populate_ruin_blocks`. Their *number* is the
    knob that sets how dense the region reads from the air.

12. **Lore names are invented.** The brief said to take official names from the
    written region description and server data; neither was available to this
    build. Every name in `world.json` — "Temple of the Coiled Sun", "The Sun
    Vault", "The Strangled Arch", "The Coil Bridge", the three marchstone
    shrines — is a placeholder chosen to fit the concept art and is expected to
    be replaced.

13. **Portal destinations follow the client registry's map ids.** The server
    owns the actual transitions; the four portal entries here are alignment
    metadata. The server branch rescales only the two transitions that already
    existed (verdant_stair and manymouth_delta) rather than adding the two the
    client declares — adding inter-region routes is a gameplay change, not part
    of serving this map at 96x96.

14. **The server does not consume the regenerated ELM.** `../source-elm/`
    `ssarathi_ruins.elm` is regenerated here at 96x96 with real elevation and
    42.4% walkability, but the server still generates its own procedural
    heights: `validate_generated_map` rejects any map containing blocked cells,
    and a flooded city is 58% blocked. Growing the server map to 96x96 makes the
    two agree on size and datum, which is what the client needs; making the
    server actually load this ELM needs a validator change and is left as a
    follow-up. This matches what Whitehorn Range and Crownwater did.

15. **`collision.bin` height bytes clamp at 63.** The legacy six-bit height
    field cannot express the temple precinct's relief. The grid is authoritative
    for walkability; the Godot loader takes elevation from the rendered walk
    surfaces, not from this file. The encoding datum is recorded in `world.json`.

16. **Tangents are not exported.** Godot's glTF importer generates them for
    normal-mapped materials, and shipping them would add sixteen bytes a vertex
    to a package already dominated by vertex data.

17. **The reduced package is a second GLB, not a runtime LOD switch.**
    `world-lod2.glb` carries far-tier vegetation only, no ground clutter and
    half-resolution textures. Nothing in the current Godot loader selects
    between them.

18. **Population markers are metadata.** NPCs, creature groups and harvestables
    are recorded as positions with `"authority": "server"`. Nothing is baked
    into the static mesh.

19. **The truncated concept board was replaced, not worked around.** Every
    region package ships a `references/00-concept-detail-board.png` cut to
    exactly 786,444 bytes, of which only the top row of five panels decodes.
    The intact 1983x793 board was supplied for this build and now sits at that
    path, so all ten panels are real comparison material rather than five panels
    and five placeholders.

## September 2026 circulation assumptions

This section supersedes the legacy server-size, portal and height-encoding
assumptions above. CONTINENT.md and region-connections.json own the eleven-region
graph. The server consumes the corrected authored grid at the current 576-tile
extent. The ordered refine/open/stamp passes restate its full byte encoding.

The arrival is an inhabited supply quay beside the ceremonial approach; the
eastern court is its trading district. Market rows face a clear aisle. Water
routes use surveyed shore heights and beds recessed at least 0.22 m beneath
their walking skins. Eight jetties point into water; the Crownwater ferry uses
the western southern jetty, retaining south-gate as its stable id.

The cistern work floor is pile-supported and its shaft is scenery, not a raised
walkable lid. The approach and trigger share the actual deck level. The temple
focus secret belongs on the reachable Sun Vault forecourt. Its prefer_near
placement option may ignore a vegetation reservation while still respecting
the real structure footprints.

Rebuild the canonical archive with source/build_insides.py; the older
build_interiors.py writes separate legacy room packages. Rebuild/export it
before the exterior correction triplet and secrets. See layout-review.md for
current counts, comparisons and explicitly outstanding old geometry warnings.

The final player-height review also turned the Water Gate across the causeway.
Separate pylon footprints leave its opening clear; the original quarter-turn
and whole-gate circular blocker obstructed the approach. Its camera now
stands on the rendered deck instead of the channel bed.
