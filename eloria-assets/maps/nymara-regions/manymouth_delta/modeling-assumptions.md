# Manymouth Delta modelling assumptions

These are the decisions taken where the concept art, the brief and the existing
runtime did not fully determine the answer. Each one is a place a reviewer may
reasonably want to overrule the build.

1. **Region extent.** Manymouth is authored at 576 m × 576 m, matching Amberwood,
   Amethyst Barrens, Crownwater, Whitehorn Range and Mirrorhold. One metre per
   tile is kept, so movement granularity is unchanged; the server map grows
   instead, from 32×32 to 96×96 ELM tiles (192 to 576 height cells). The arrival
   datum moves from server (58, 58) to (174, 174), so it still lands on the Godot
   origin. `../server-collision/manymouth_delta.bin` is regenerated to match and must
   be loaded server-side, together with
   `feature/manymouth-delta-96-server-map` in `eloria-server`.
   The whole composition is written in a 192 m design space and scaled by
   `region.SCALE`, so the aerial's layout is preserved rather than stretched.

2. **The delta floor is terrain, not a hole.** The client grounds actors by
   casting a ray down at *every* server tile, not only walkable ones. A region
   that is two-thirds water therefore still needs a continuous surface under all
   of it. The heightfield covers the whole footprint and simply sits below sea
   level across most of it. This is the single decision that makes zero
   grounding misses achievable here. Crownwater reached the same conclusion from
   the same direction; it matters more in this region because there is more
   water.

3. **The walkway network is the road network.** There is not one graded road in
   this region. In the concept you do not walk between two places, you walk over
   water between them, so the connective tissue is built geometry: 27 routes,
   73 deck segments and 28 landing stairs, resolved *before* any building pass
   runs so that every hut, hall and quay reads its height off the walkway it
   opens onto. `world.json` records them under `roads` with `type: "walkway"`.

4. **A walkway is capped 2.2 m above its lower landing.** Taking a deck's level
   from the higher of its two ends — which is what Crownwater's causeways do,
   correctly, between islands of similar height — sent the stelae-court-to-temple
   route dead level at 14.8 m for a hundred metres, because the temple mount is
   14.8 m high. A walkway crosses water; where the ground rises out of reach it
   stops, and the temple's own processional stair continues.

5. **Elevated decks own their server cell**, as in every other region: the client
   grounds on the highest walk surface below the ray and a flat server grid
   cannot hold two levels. The fraction of walkable area that is deck rather than
   ground is much higher here than elsewhere, which is a design decision and not
   an oversight.

6. **Bars are lens-shaped, not round.** A braid bar is deposited by a current, so
   it is drawn out along the flow and blunt across it. A field of circles does
   not look like a delta at any density, and the first island pass proved it.

7. **Sand keeps only the last 0.9 m at the water's edge.** The toolkit's
   `assign_surface_by_rule` paints SHORE over everything within 1.6 m of the
   water line, which is right for a region whose land stands well clear of the
   sea and wrong for one whose islands are 1–2.5 m of silt: it turned every bar
   into a sandbank and the first client aerial came back as a white sand flat.
   The rule still runs; the bar tops are taken back off it afterwards.

8. **The glyph inlay is painted, not lit.** glTF's `emissiveFactor` has no mask
   without an `emissiveTexture`, and `materials.MaterialSpec` has no field for
   one, so a factor applies uniformly across a whole surface. On the Amethyst
   crystals that is correct; on near-black ruin stone it swamps the albedo, and
   the first real client frame of this region showed the great arch as a solid
   glowing teal ring with the stone gone. The inlay is authored into base colour
   instead. **Cost:** the ruins do not glow at dusk. Fixing that properly needs
   an emissive-texture field in the shared material table.

9. **Water is authored at alpha 0.44**, lower than Crownwater's 0.70, because
   this region's channels are shallower and the aerial's whole signature is that
   the bars read *through* the water. Note that the offline preview renderer
   cannot show this: `native/raster.c` has no BLEND path at all and draws every
   blended material opaque. Judge the water from `references/godot-captures/`,
   never from `references/captures/`.

10. **Nine new material recipes and one new texture atlas.** `deltakit.py` adds
    teak decking, woven bamboo, delta silt, paddy, jungle floor, sandbar, delta
    water, glyph stone and a pinnate frond atlas. The frond atlas is the one
    that matters most: the shared `foliage_atlas` draws broadleaf sprays, and a
    palm profile wearing them is a dark blob on a stick — the region read as
    temperate woodland with the colour turned up until the fronds existed.

11. **`collision.bin` height bytes clamp at 63.** The legacy six-bit field cannot
    express the range from the channel floor to the temple summit. The grid is
    authoritative for walkability; the Godot loader takes elevation from the
    rendered walk surfaces. The encoding datum is recorded in `world.json`.

12. **Water is classified, not re-encoded.** `collision.swimmable` records the
    rule, the cell count, the fraction and the depths, so a future swim or
    aquatic-form traversal mode needs no rebuild. `collision.bin` itself is
    untouched — EWCG v1 has no spare bit and inventing v2 for a flag no client
    reads would be worse. See `traversal-modes.md`.

13. **Panel 8 is an interior and is out of scope.** The board's flooded cavern
    with the ring-portal is the `manymouth_flooded_labyrinth` map, which already
    exists server-side. This package ships its **threshold** — the cut arch in
    the rock headland, portalled and walkable up to the door — and the panel
    sheet says so on the sheet itself rather than pretending otherwise.

14. **The Flooded Labyrinth is routed from Manymouth, not Amberwood.** It was
    attached to Amberwood only because Amberwood was the one production exterior
    when it was added. Moving it is the same shape of fix `3ff5561` made for the
    Amethyst insides, and it is required by this package's own cave-mouth portal.

15. **No rim wall.** Amberwood closes its world with mountains because it is
    land. The delta's horizon is open water on three sides and its own jungle
    head on the fourth, and a raised rim outside the playable footprint reads
    from any elevated camera as a slab floating at the map edge. The world is
    closed by the collision grid instead: water is not walkable, the bed still
    grounds every tile, and nothing reaches a void.

16. **Lore names are invented.** No written region description and no server
    naming data was available, so every place name in `world.json` is a
    placeholder chosen to fit the concept art and is expected to be replaced.

17. **Population markers are metadata.** NPCs, creature groups and harvestables
    are recorded as positions carrying `"authority": "server"`. Nothing dynamic
    is baked into the static mesh.

18. **The reduced package is a second GLB, not a runtime LOD switch**, as in
    every other region. Nothing in the current Godot loader selects between them.


## September 8 layout revision

The earlier numbered notes describe the first package. The current layout is
defined by source/layout.py and layout-review.md. One surveyed level belongs
to each landing; roads slope between those levels. The default arrival is
the stilt-town service court, server tile (210, 222). The hall, market and
quay own their rectangular floors; connectors stop at their edges.

Houses face their porch connections and have separate solid interior floors.
The market has two stall rows, a central aisle and orderly boat moorings. A
procedural lateen packet identifies the quay. The Green Temple faces its
southwest approach, and the Great Arch descent is on its actual platform.
Difficulty follows the occupied town, working paddies and fishing reaches,
then the remote groves, ruined courts and temple. The server contentLayout
is authoritative for the existing named NPCs, services and habitats.
