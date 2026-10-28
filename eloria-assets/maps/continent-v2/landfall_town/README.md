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
| `market` The avenue shops | #20 door B Hanne's Provisions (general store), #19 door C Bryony's Flowers (flower shop) | General store and flower shop, one floor through a wide arch | oak and cobalt tile / plaster |
| `magic_shop` The True Note | #24, door D (magic shop) | Shop, workshop | cobalt tile / plaster |
| `smithy` The forge | #12, door E Hild's Forge (blacksmith) | Forge, the smith's kitchen and bedroom | packed earth and oak / soot brick and plaster |
| `clerk_house` Hemmen's house | #22, door G | Study, kitchen, bedroom | oak / plaster |
| `weaver_house` The weaver's house | #27, door H (north wall) | Loom workroom, kitchen, bedroom | oak / plaster |
| `watch_house` The watch house | #11, door I (west wall) | Mess, bunk room | oak / plaster |
| `netmender_house` The net-mender's house | #56, door J (west wall) | Hearth kitchen, net loft | oak / plaster |
| `castle` The keep | #1, door K (west wall) | Gate Hall, Hall of Eight Seats, Register Archive, Palace Chancery, the sealed-stair alcove | limestone flagstone / ashlar |

Each street door stands in the interior wall matching its facade's direction
(south for the avenue's north side and the SW-facing main row, north for #27, west
for #11, #56 and the keep). Building doors use objects 59201-59210 (one id serves
both ends), the tavern stairs 59221/59222; the keep's sealed stair is art only,
with no portal. A coloured door is named as its shopkeeper is on the map.

The rooms are furnished with 308 placed pieces: the 35-piece `lf-interiors`
furniture kit (beds, tables, benches, counters, shelves, hearths, the forge, the
anvil, the loom, the eight high seats and the council map table; Meshy pieces
prepared at real size) and reused kit scenery (barrels, milk churns, crates, sacks,
pots, planters, carts). 121 of them stand against an outer wall and 47 against a
partition; each is cut away with its wall (`cutawayWall`). Four are tinted through
the prop palette (`palette`, drawn by the client's MineralAppearance shader): the
three lichen crusts on the Mycelari seat and the Stoneborn standing stone in the
Hall of Eight Seats. Twenty people stand at their posts (five shopkeepers: Hob
Tennant, Hanne Ashby, Bryony Larch, Ilka Tarn and Hild Ashlar), and 16 interior
interactives (59251-59254, 59271-59278, 59281-59284) hold the lore objects and the
smithy's anvil, a crafting station that publishes as `smithing`. A lore object is
a pick-only record in `objects.json` (`pickOnly`): a click shape and a hover name
on the prop it describes (the source's `at`), with no ring or stand-in model.

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
python -B tools/prepare_underground_scenery.py --map landfall_town
python -B eloria-assets/maps/continent-v2/_continent_v2/retarget_underground.py --map landfall_town --server ../rabbitlands-server
python -B eloria-assets/tools/sync_music_program.py --server ../rabbitlands-server --map landfall_town
python -B -m pytest -p no:cacheprovider -q eloria-assets/maps/continent-v2/_continent_v2/tests/test_town_interiors_builder.py
```

The music step rewrites only the `landfall_town` block of the server's
`config/eloria/music-program.json`: the client source's `home_day`/`home_night`
record with one zone per room, named and classified from the package's chambers
and room spaces, and the digest of the `world.json` they came from
(`zone_source_sha256`). Every other byte of the server file stays as it is (it
carries A3 music the client source does not, which a run without `--map` would
revert). `--check` writes nothing and exits 1 while the block is stale: after any
rebuild that changes `world.json` (its digest), and with new zones when a room
moved or was renamed.

A plan change that moves a room, a door or a prop is a rebuild: the scenery must
follow the same `dressing()` the walk grid was cut from. The builder refuses rooms
off the tile rows, a doorway that leaves no open tile, a door, arrival or stair tile
that a prop or stair closes, an NPC post without its eight open neighbours, and any
pocket of floor larger than six tiles cut off from a section's arrival.

## Package

10 sections, 30 rooms, 1,645 walkable tiles (tavern 130 + upstairs 133, shops 142,
magic shop 86, smithy 96, houses 77-114, keep 668), 100 light markers (86 lights
and 14 lamp props). `world.glb` is 941,328 bytes with its 27 images in the shared
pool (decals clamp to their edge, surfaces repeat); `collision.bin` (EWCG-v2),
`served-grid.escg.gz` (ESCG-v2) and `minimap.webp` beside it. The manifest's
`minimap.liveSpanMetres` (40) frames the live minimap at a room's scale, so a room
spans 45-60 px of it instead of 10-20.

Cutaway: the roofs are always hidden; the outer walls cut away by facing
(threshold 0.35), with the props set against them. The 28 partitions (94
`cutaway.partitions` rows: each one's wall, trim and hung decals) are cut away by
the client while one stands between the camera and the player inside its
section and span, or - seen edge-on, running toward the camera - while it stands
in the line from the player's body to the camera (`interior_cutaway.gd`); the
props against a partition drop with it. Main also hides the name of anyone behind
a standing partition of the shown section. (The manifest's `cutaway.reason` still
says the partitions fade: the builder wrote it before the cutaway did this.) The
keep's street door draws its two plank leaves folded back against the wall
(`doorLeaves`); the other street doors are lit openings.

## Preload and parking

The registry flags the map `preloadOnApproach` with `interiorOf: landfall`
(`godot-client/src/world/world_park.gd`, its rules in `world_park_policy.gd`):

- Binding Landfall reads the Town's doors, estimates it from its textures (about
  120 MiB) and warms its shaders behind the arrival curtain: the six material keys
  its shell binds and the palette tint its scenery's four tinted pieces use
  (`interior_material_warmup.gd`). Arriving over Landfall's border with no
  curtain spreads the same warm-up over the following frames, one material a
  frame, and holds the preload until it has run.
- Within 24 tiles of any of the ten street doors the Town is built in the
  background: the package on a worker, then published on the main thread in
  slices of at most 4 ms (`interior_scenery_stepper.gd` places the scenery).
  Clicking a door adopts it; a map change waits behind the curtain (up to 15 s)
  for a preload still building, and otherwise loads the Town itself.
- Inside, Landfall is kept detached (parked) and re-attached on the way out; the
  Town is then parked in turn. A built Town stays while the player is within 48
  tiles of its doors. It is let go after a minute farther away, on travel to any
  other map, or when the kept worlds' estimates pass the 1.5 GiB budget; one let
  go for the budget is built again within 8 tiles of a door.
- `godot-client/tests/integration/landfall_town_park.gd` (rendered) measures it.
  Five runs on 2026-10-27, the first two on new Godot profiles (an empty shader
  cache): the preload's worst frames were 5.4, 22.9, 16.7, 19.9 and 5.1 ms (the
  check allows 50) and its main-thread slices at most 4.2 ms; the preloaded
  entry was ready in 27-49 ms (644-885 ms cold) and the parked return to Landfall
  in 35-54 ms (1.4-1.7 s cold). Before the tint shader was warmed, runs on an
  empty cache had a 67-79 ms preload frame.
