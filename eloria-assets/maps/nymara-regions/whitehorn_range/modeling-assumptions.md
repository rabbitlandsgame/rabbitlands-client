# Whitehorn Range modelling assumptions

Decisions taken where the brief, the concept art and the existing runtime did
not fully determine the answer. Each is a place a reviewer may reasonably want
to overrule the build.

1. **Region extent.** 576 m x 576 m on a 96 x 96-tile server map at one metre
   per tile, matching Amberwood so the two regions share a coordinate
   convention and the same server-side change shape. The arrival datum moves
   from server (58, 58) to (174, 174) so it still lands on the Godot origin.
   `../server-collision/whitehorn_range.bin` is regenerated to match and must be
   loaded server-side. The whole composition is written in a 192 m design space
   and scaled by `region.SCALE`, so the extent is one constant.

2. **Snow is the default surface, not a high-altitude band.** The first pass
   made rock the default and put snow above a 62 m line. It rendered as a brown
   bowl with a white rim — the opposite of the painting, which is white almost
   everywhere. Snow is now the base class and rock is what breaks through where
   the ground is too steep to hold it, with the steepness threshold rising with
   altitude so peaks stay white and only their faces go grey. Turf survives
   only on low, sheltered, shallow ground in the south.

3. **`terrain.assign_surface_by_rule` is not used.** It is written for a
   coastal region and assigns SHORE around a sea level Whitehorn does not have.
   `region.assign_surfaces` replaces it. This is a region-local decision, not a
   toolkit defect.

4. **The gorge floor is deliberately not walkable.** It sits 22 m below the
   valley datum, past what the legacy six-bit collision height field can
   encode. More to the point it is a chasm: the two rope bridges exist because
   it is not something a player crosses on foot. Marking its bed unwalkable
   states the design rather than working around the encoding.

5. **The gorge is cut twice.** `grade_path` levels a road corridor to a
   smoothed profile along the route, which happily bridges a 22 m chasm and
   fills it in. Two routes cross the gorge, so grading them erased the one
   feature the bridges exist to span. The cut is therefore repeated after the
   roads rather than before, so it wins.

6. **Bridge spans are fixed constants, not derived from the terrain.** The
   gorge is a V cut into a mountainside, so the ground keeps climbing away from
   it and there is no height at which a "rim" can be detected. Searching for
   one either stops inside the chasm — the first attempt put the deck 29 m
   below the road, invisible from it — or runs away up the slope, giving an
   80 m span with ends 17 m apart in height. `populate.SPANS` sets 34 m and
   30 m, measured from the cut, with the deck at the mean of its two landings.

7. **Elevated decks own their server cells.** The client grounds actors on the
   first walk surface below a downward ray, and a flat server grid cannot hold
   two levels. The bridge decks take their footprint in `collision.bin` at deck
   height; the gorge beneath them is not separately walkable. This is a design
   decision, not an oversight.

8. **Kit pieces are region-local rather than in the shared toolkit.**
   `source/kit.py` holds the cairn, waystone, rope bridge, mine portal, ice
   cave mouth, frozen cascade, shrine alcove, gate and conifer. Four region
   builds were appending to the shared kits concurrently while this was
   authored, and adding a sixth set of names into that would create exactly the
   merge conflict the production guide warns about. `cairn`, `waystone`,
   `rope_bridge` and `mine_portal` are generic enough to promote to
   `_toolkit/` once that settles, and should be.

9. **Materials are reused from the shared table, not duplicated.**
   `snow_pack`, `glacier_ice`, `veined_marble`, `pale_ashlar`, `blue_crystal`,
   `gilt_brass` and `alpine_turf` were added to the toolkit by the Mirrorhold
   build; Whitehorn takes them by name. No `whitehorn_`-prefixed recipe was
   needed in the end. The build pins its material set by name so later
   additions by other regions cannot change this package's bytes.

10. **No reduced LOD package.** Amberwood ships `world-lod2.glb` because it is
    9.5 triangles per square metre. Whitehorn is 2.09, and 12.2 MB in total, so
    a second package would add maintenance for no measurable gain. If the
    region gains a dense settlement later this should be revisited.

11. **Conifers are gated on height, slope and surface class**, not scattered.
    The aerial puts trees on the lower southern slopes and nowhere near the
    glacier, so placement requires ground below the snow line plus 16 m, slope
    under 0.85, and a snow or turf surface. 870 instances.

12. **Lore names are invented.** The authoritative written region description
    and server name data were not available to this build. Every place name in
    `world.json` — "Glacier Temple", "Whitehorn Gate", "Whitehorn Mine" and the
    rest — is a placeholder chosen to fit the concept art, and is expected to
    be replaced. This is the same limitation Amberwood shipped with.

13. **Portal destinations follow the server profile.** The three edge portals
    are pinned to the server tiles `config/eloria/maps.txt` already assigns to
    `whitehorn_range`, converted through the region's own transform, so the
    client marker and the server transition sit on the same cell. The server
    owns the actual transition.

14. **Population markers are metadata.** NPCs, harvestables and portals are
    recorded as positions carrying `"authority": "server"`. Nothing dynamic is
    baked into the static mesh.

15. **The mine and the ice cave are facades, not interiors.** Both present a
    recessed dark volume rather than an actual cave. Whitehorn has no interior
    package in this build; `whitehorn_glacier_temple.elm` exists as a separate
    interior and the temple portal points at it.

## September 2026 circulation decisions

The gate refuge now owns arrival at world (-12, 69), server (162, 105).
Services and four existing NPCs share its court. Eight low weather shelters
use the existing snow, pale masonry and timber recipes; the mine bench and
5.5 m road support haulage around the gorge head. The temple ascent follows
seventeen documented road/approach polylines and two surveyed rope crossings.
The main temple remains the navigation landmark and gains three snowy pinnacles.

New reusable geometry belongs to amberwood/mountaincraft.py: suspension_bridge,
temple_pinnacle and ore_sledge. Whitehorn's kit.rope_bridge is now only a palette
wrapper. The original regional cave recipe is reused at the western watch.
No surface classes are allocated. See layout-review.md for verification and
the remaining visual limitations; earlier geometry counts above are historical.
