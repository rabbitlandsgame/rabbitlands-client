# Landfall Town

The building interiors of Landfall's walled town share one interior map,
`landfall_town` ("Landfall Town", alias LFT, 324 x 324 tiles). Each building (or
storey) is a section of sharp-cornered rooms; at least 19 tiles of unfloored,
blocked blackspace separate the sections, and the client draws only the section
the player stands in. A door painted on a town facade is an object portal: click
it and the server walks the player to the door tile and in; inside, the same object
stands on the exit tile by the street door and leads back out to the door's return
tile. Entry requires a client declaring `landfall_town_v1`.

| Section | Building, door | Rooms | Floor / walls |
|---|---|---|---|
| `tavern_ground` The Unlit Boat | #14, door A (tavern) | Taproom, kitchen, stair hall with the stairs up | oak / plaster, soot brick in the kitchen |
| `tavern_upper` The Unlit Boat, upstairs | stairs from the stair hall | Landing, three guest rooms, the Orl family room | oak / plaster |
| `market` The avenue shops | #20 door B (general store), #19 door C (flower shop) | General store and flower shop, one floor through a wide arch | oak and cobalt tile / plaster |
| `magic_shop` The True Note | #24, door D (magic shop) | Shop, workshop | cobalt tile / plaster |
| `smithy` The forge | #12, door E (blacksmith) | Forge, the smith's kitchen and bedroom | packed earth and oak / soot brick and plaster |
| `clerk_house` Hemmen's house | #22, door G | Study, kitchen, bedroom | oak / plaster |
| `weaver_house` The weaver's house | #27, door H (north wall) | Loom workroom, kitchen, bedroom | oak / plaster |
| `watch_house` The watch house | #11, door I (west wall) | Mess, bunk room | oak / plaster |
| `netmender_house` The net-mender's house | #56, door J (west wall) | Hearth kitchen, net loft | oak / plaster |
| `castle` The keep | #1, door K (west wall) | Gate Hall, Hall of Eight Seats, Register Archive, Palace Chancery, the sealed-stair alcove | limestone flagstone / ashlar |

Each street door stands in the interior wall matching its facade's direction
(south for the avenue's north side and the SW-facing main row, north for #27, west
for #11, #56 and the keep). Building doors use objects 59201-59210 (one id serves
both ends), the tavern stairs 59221/59222; the keep's sealed stair is art only,
with no portal. The first draft carries reused kit props only (barrels, crates,
sacks, chests, pots, baskets, rope, a tool rack, a lens grinder); furniture,
shopkeepers and interior interactives follow in the source.

## Sources and rebuilding

`_continent_v2/content/landfall_town.json` is the single authored plan (rooms, room
names, doorways, floors, walls, windows, decals, doors, stairs, props, lights,
NPCs, interactives); `_continent_v2/town_source.py` reads, checks and writes it
(its docstring has the format). `_continent_v2/build_town_interiors.py` builds the
package (shell, collision, served grid, spawn points, chambers and room spaces,
portals, lights, cutaway, minimap) and moves its images into the shared pool
(`eloria-assets/tools/shared_images.py`). It is an owner-approved generator
(2026-10-27, `docs/procedural-model-archive.md`) and runs only with
`--owner-approved`. It imports `build_underground.py` without changing it, so the
underground package stays byte-identical. Its surfaces are the codex textures in
`godot-client/src/world/look/textures/interior/` (packed earth: the class texture
`packed-earth-path.png`); the builder's SURFACES table names a placeholder for any
that is missing, and the package's `provenance.surfaces` says which was used.

```powershell
python -B eloria-assets/maps/continent-v2/_continent_v2/build_town_interiors.py --server ../rabbitlands-server --owner-approved "<who, when, what>"
python -B tools/prepare_underground_scenery.py
python -B eloria-assets/maps/continent-v2/_continent_v2/retarget_underground.py --check
python -B -m pytest -p no:cacheprovider -q eloria-assets/maps/continent-v2/_continent_v2/tests/test_town_interiors_builder.py
```

A plan change that moves a room, a door or a prop is a rebuild: the scenery must
follow the same `dressing()` the walk grid was cut from. The builder refuses rooms
off the tile rows, a doorway that leaves no open tile, a door, arrival or stair tile
that a prop or stair closes, an NPC post without its eight open neighbours, and any
pocket of floor larger than six tiles cut off from a section's arrival.

## Package

10 sections, 30 rooms, 1,684 walkable tiles (tavern 162 + upstairs 155, shops 159,
magic shop 85, smithy 117, houses 56-74, keep 743), 70 light markers. `world.glb`
is 804 KB with its 22 images in the shared pool; `collision.bin` (EWCG-v2),
`served-grid.escg.gz` (ESCG-v2) and `minimap.webp` beside it. Outer walls cut away
by facing (threshold 0.35) and props against a wall drop with it; partition walls
are left to the occluder fade.
