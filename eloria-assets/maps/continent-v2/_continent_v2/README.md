# Continent v2 section partition

Active map IDs, exact polygons and ownership priority come from the catalog's partition: since Landfall A3
(owner-approved 2026-10-19, revised the same day) that is `partition-inputs-a3/sections_spec.json`, seventeen maps
with 35 shared borders, every section one ring. Borders are near-rectangular and open sea belongs to no map; shared sea
edges are kept only across narrow straits, so the isles still preload from the coasts. Its `input-provenance.json` names its predecessor (`partition-inputs/`, the fifteen-map
partition of 2026-10-10, kept unchanged as history), the frozen ground it crops and the files it shares with the
predecessor; `plan-amendments.json` retires the B13, B14, B22 and B24 decks, cuts R42 to its Spindle Hill strand, makes
the knob a jetty, records the scene content decisions (`sceneContent`) and the merged maps (`mergedMaps`). `authoring/` keeps the scripts
that drew the polygons.

All editor bases are byte crops of the hash-pinned frozen ground, now `group-terrain-v2`, built from the untouched v1
`group-terrain` by `godot-client/tools/build_continent_v2_ground.py` and its recipe in `ground-v2/` (the strait
fills, the boat-only Verdant + Ssarathi isle round Tollholm and Spindle Hill, the Whitehorn + Mirrorhold isle; the
old north-east stub sunk). Its grid is a data parent outside the active catalog. A3 also renamed `spindle_hill` to
`jadestair` and `tollholm` to `coilmere` (`godot-client/tools/migrate_continent_v2_map_ids.py`, markers in
`marker-renames-a3.json`), then merged `jadestair` into `coilmere` before release (`mergedMaps`; its markers map
straight to Coilmere's, its harvestables renumbered past Coilmere's), and added `suncoil`, `hornmere` and `whitepeak`.

The tools that replay a partition change, in order: the ground builder; `migrate_continent_v2_map_ids.py`; the
bootstrap with `--partition` and `--rebase-scenes` (surviving maps keep their translations; their frames only grow
and their crop windows stay the predecessor's while those still cover them); `carry_continent_v2_grade.py` (the
ground-colour grades follow the re-cut crops); `repartition_continent_v2_content.py` (retire, re-ground and move
scene content and spawn rows; a merge runs it before the bootstrap, while the merged map is still in the catalog); `generate_continent_v2_arrivals.py --rebind`; `publish_look.py` (its source palettes
are pinned in `look-sources/`); `retarget_underground.py`; then the publication below.

Run `python godot-client/tools/bootstrap_continent_v2_territory.py --check` to replay immutable crop/frame/plan checks.
The bootstrap does not reset existing authored scenes and preserves gameplay/authority spec fields. Edit those
scenes normally, then run `python godot-client/tools/continent_v2_territories.py` to validate seams and ownership.
Do not re-run the original Meshy conditioning. Source kit libraries are shared by catalog metadata; placements
remain authored content. Original source scene/content/package directories retire after their saved content and
publication move; the three catalog-declared kit folders remain shared libraries without active source editors.

## Region borders

Neighbouring maps change gradually, never at a line. The ground-colour grade over the frozen vertex colours ramps
linearly across each border, `featherMetres` (130 m) on each side, about 260 m in all. The border it ramps across is
warped by smooth noise (`borderWarpMetres` 60 m, `borderWarpScaleMetres` 80 m), so maps interfinger, and border zones
lean toward a neutral meadow `ecotone` colour, so two strong palettes meet through grassland rather than a muddy mix.
Each `godot-client/world_authoring/regions/<map>/colour-grade.json` records these values beside its graded copy
`base-colors-graded.rgba8`; all the maps graded on 2026-10-14 use the same ones (A3's re-cut crops carry them,
`carried` in the record; the three new maps read their frozen crop colours until their own pass). Flora and ground-region bands that cross a border
follow the same rule at roughly 150-250 m.

## Light and weather

Each map's sky, sun, ambient light, fog and saturation are its stub's `environment` block (`<map>/world.json`), and
`publish_client.py` copies the block verbatim into the territory manifest and every chunk manifest. A light-only
change needs no re-bake: edit the stub, then run `publish_client.py --environment --region <map> --out
<map>/client`, which rewrites that block and nothing else (no digest covers it).
`tests/test_publish_client_environment.py` fails while any package's block differs from its stub's.

`environment.variants` names a map's own `night` (sky zenith and horizon, fog, ambient and moon colours), `dawn` and
`dusk` (sun, sky horizon and fog colours); `DayNightBinder` and the painted sky blend towards them by the hour, and
a colour a variant omits stays the shared one. Only colours move: how dark the night is stays the same everywhere.
`golden-hour` is a fixed pose for a still frame and is not read. `environment.presentation` may declare map-wide
`mist` (lying at dawn, dusk, night and in rain) and `gulls` (by day), each `{"enabled": true, "density": 0..1}`;
`PresentationEffects` draws them around the camera. An entry with `zones` is left for a zone reader.

Across a border the client blends two isles' light over `ExteriorRegionStream.ISLE_LIGHT_BLEND_METRES` (130 m) on
each side of the shared border, the same width as the ground. Weather is the server's: climates are rows in
`config/eloria/weather.txt` (the base profile, not the continent-v2 overlay), and rain greys the sky, dims the sun
and thickens the haze in the client (`WeatherSky`). The kits' lantern posts, lamp buoys and lighthouses light at
dusk by their model names (`NightLamps.LAMPS`), with a small pool of real lights for the lamps nearest the camera.

## Server publication

After all active saved scenes are committed, bake every catalog map and publish its client package from that
exact bake. Export collision, crossings and the other shared publication steps before running `publish_server.py`.
Pass one `--bake MAP_ID=BAKE_DIRECTORY` argument for each active catalog entry, plus `--server`, `--stage m4` and
either `--check` or `--apply`. The publisher validates the catalog/frame/content-table map set dynamically; it has
no fixed fifteen-map list. Apply is followed by check using the same inputs.

The generated server overlay carries per-map rows and map-qualified chapter targets, approaches, NPC posts and
register/ferry objects. `landing.json` retains schema `eloria-landing-v1`: each target and cast post includes `map`,
and register/ferry object descriptors are `{map, id}`. The hub is `landfall`; chapter steps 1-6 occur there, step 7
in Warrenmead, step 9 in Reedfall and step 10 in Greenlight. Runtime isle membership comes from the served manifest.
Retired map saves return home; fresh map IDs have no character position migration.

Seven maps have authored default spawn markers (the three conserved ones in Landfall, Boarsend and Coilmere; A3's
Suncoil, Hornmere and Whitepeak; and Greenlight's quay, whose generated arrival ground v2 left under water). Ten maps
use separately hash-bound generated arrival metadata, validated by `arrivals.py` against the recorded source/frame/ownership contract. Generated
arrivals are outside gameplay marker arrays and do not increase the authored marker total. Marker rename history
and shared kit identities retain pinned historical source names; active ownership uses the new catalog IDs.

The overlay sits beside certified legacy tables. A runtime change to a certified source such as `world.py` needs
the owner's separate certificate-advance kit; publication does not overwrite the immutable legacy authority.

Five public shared-storage chests are authored in Landfall (beside Ressa on the arrival plaza), Greenlight (the ferry quay),
Hearthcroft (the roadside hamlet), Stagheath (the red lighthouse courtyard), and Coilmere (beside Tollholm's square).
Each uses per-map object ID 22 and the existing server `storage` role. The server stamps its 3x3 solid body;
publication requires the complete two-tile approach ring to be open and connected to an arrival. Client packages
retain the storage positions for generated cartography. Brown dots matching the Storage legend identify chests
on live Tab maps and minimaps, on other-area Tab previews, and on the Landfall overview. The original 254 conserved source markers
remain recorded in marker-renames.json; these five additions, eight Cotton plants, four underground entrances, and Rowan's tool shop bring the active authored total to 272.

Rowan Hale runs Rowan's Tools beside the Landfall civic square. The
shop sells Pickaxes, Hatchets, Needles, Mortar and Pestle, Smith's Hammer and basic
supplies. NPC scene extras `occupation` publishes the line a client draws under the
name (`npcs.txt` gains `occupation=` beside `actor_type=`; names stay simple, so a
name that starts with its own occupation is refused). NPC scene extras `mapCategory`
and `mapLabel` publish permanent service
markers: `general_store` is green and `tavern` is orange. Rowan's Tools and Bettany
Orl's Tavern appear on live maps, minimaps, region previews and the isle overview.

Two Cotton patches in Landfall provide beginner Thread and Cloth Roll supplies.
Each has four plants: one near the register and arrival, and one beside the Sage
meadow. The saved scene owns their positions and IDs 336-343. Publication checks
that every plant's approach ring is walkable with NPC posts and storage blocking
their occupied ground. Cotton uses the existing plant model and needs no tool.

Four cave mouths lead to `landfall_insides`: Lantern Mine, Pinebrow Deep Workings,
Cenote Deeps (Coilmere), and Boarsend Old Barrow. Their rooms share one interior
map with unfloored blackspace between sections. The peaceful Lantern Mine
supplies beginner Coal and Iron Ore; the deeper areas contain intermediate
encounters and additional minerals. See `../landfall_insides/README.md` for
locations, resources, encounter tiers, and the rebuild workflow. `build_underground.py` was retired on 2026-10-16 and runs only with
`--owner-approved` (re-enabled 2026-10-20 to rebuild the Cenote Deeps as a jungle cenote); when a
partition change moves a door's exterior map or frame, `retarget_underground.py` rewrites only the door ends, and a section renamed in
the source only its labels (the Spindle Mineral Cavern became Coilmere's Cenote Deeps for Landfall A3; its
id `spindle_cavern` and entrance marker id stay; its rooms are the cenote's).

## Landfall Town interiors

Owner-approved 2026-10-27 (chat: "Implement your plan"): the rooms behind Landfall town's street doors (the tavern
and its guest floor, the general store and the flower shop, the magic shop, the smithy, four homes and the keep; and,
2026-10-28, "Add a library with a book seller NPC": Calloway's Books, the bookseller's shop, reading room and stacks)
are one interior map, `landfall_town` (alias LFT, 324 cells), beside the caves' `landfall_insides`. Each building, or each
storey of one, is a section with unfloored blackspace round it, as the caves' are. See
`../landfall_town/README.md` for the package and its rebuild.

- `content/landfall_town.json` is the source, in `underground.json`'s shape (schema, map, sections, passages) so the
  shared publication helpers apply. A section adds `roomNames` (chamber names, which also choose each room's music:
  tavern/inn, shop/store/forge/workshop, castle/hall, archive/library, house/home/cottage), `floors`, `walls`,
  `windows`, `decals`, `props` (reused kit scenery, with `blockBox` and `wall`), `lights`, `npcs` and
  `interactives`. Its doors are building doors (`kind: "building"`): no scene marker; `tile` and `returnTile` are
  checked on Landfall's served grid, `position` is the painted door on the facade (cartography draws it there),
  `category` is the shop's dot colour (none for the tan entrance dot), `label` names the door outside and
  `exitLabel` the way out inside. The tavern's two storeys are joined by a passage whose ends are stairs
  (`stairs_up`/`stairs_down`), each end with its own `label`. Object ids: building doors 59201-59220 (one id serves
  both ends), passage ends 59221-59240, interior interactives 59251-59299. An interactive may add `label` (its short
  hover name, else its text's first clause), `at` [x, y] (the point of the prop or picture it describes: its click
  shape stands there, not on its tile), `target` (the server's target column; by default `notice` for information
  and `crafting` for a station, the smithy's anvil `smithing`) and `height`/`radius` (its pick's size, else the
  packaged prop's at `at`). A prop may add `palette` {stone, mineral} (tinted by the client's MineralAppearance
  shader: the Hall of Eight Seats' lichen and standing stone; a tint recolours the whole model, a bookcase's books
  too) and `mirror` true (drawn left for right: the library's bookcases). A section may add `specialAreas` [{kind, room,
  factor?}]: a server special area (eloria/areas.py kinds; factor by default the kind's, fast_reading 3) over that
  room's floor inside its walls (`town_source.room_tiles`); the library's reading room is the one fast_reading room.
- `town_source.py` is the only reader, checker and writer of that file (its docstring is the format); it reuses
  `underground_source.py`'s helpers without changing them.
- `build_town_interiors.py` is the owner-approved builder of the room shells (floors, walls, partitions, doorways,
  windows, decals, stairs and the lit street doors) and the package's walk grid, served grid, minimap and
  `world.json`; it runs only with `--owner-approved "<who, when, what>"`. Furniture is reviewed kit scenery:
  `tools/prepare_underground_scenery.py` writes its placements to `godot-client/data/world/town-scenery.json`
  (`--map landfall_town` packages the town's TOWN_SELECTION pieces, the `lf-interiors` furniture kit among them,
  records them in `reused-scenery.json` and writes that config only; the caves' config and pieces stay as they are).
  A prop against a wall carries its wall's node (`cutawayWall`) into the config, so it is cut away exactly with that
  wall. Decal textures clamp to their edge; surfaces repeat. A theme (THEMES, by the section's `style`) with
  `doorLeaves` - the keep's - draws its street door's two plank leaves folded back against the wall either side of
  the opening, iron-strapped and inside the wall's walk margin (the walk grid is unchanged); a window within that
  reach of the door (`door_reach`) is refused. The manifest's `minimap.liveSpanMetres` (MINIMAP_LIVE_SPAN, 40 m)
  sets the live minimap's span on the map (main.gd `_bind_minimap_span`, scaled by the player's zoom), so a room
  reads at minimap size; a map that states none keeps the player's zoom. The package's provenance pins the builder
  and the helpers it imports (`build_underground.py`, `town_source.py`, `underground_source.py`): an edit to any of
  them needs a town rebuild before anything publishes. The map loads raw (it is a geometry-cache interior candidate, not in the
  production scope); `godot-client/tools/interior_load_benchmark.py --target landfall_town` qualifies it.
- `map_categories.py` is the one table of shop categories and their dot colours (tavern, general_store,
  flower_shop, magic_shop, blacksmith, bookshop - the legend's red Books dot; the tan entrance dot for a door without
  one). The client's copy is
  `godot-client/src/ui/service_map_overlay.gd` and the legend in `main.tscn`; `test_continent_v2_cartography.py`
  keeps the three equal. A category the table does not hold is refused by every publisher, never dropped.

Two interior sources publish side by side: `underground.py` SOURCES lists the caves (`underground.json`,
`landfall_insides`, built by `build_underground.py`) and then the town (`landfall_town.json`, `landfall_town`, built
by `build_town_interiors.py`). Each package must have been built from its source by the builder its own provenance
names; object ids are unique across both interiors and apart from every exterior object; an absent source publishes
nothing. `publish_server.py` appends each interior's rows under its own heading in `maps.txt`, `spawns.txt`,
`harvesting.txt`, `npcs.txt` and `interactives.txt` (the caves' rows do not move), vendors both grids, and lists both
under the manifest block's `interiorMaps` (the town's entry carries `kind: "building"`): the caves' doors and
passages under `undergroundPortals` / `undergroundRows`, the town's doors and stairs under `buildingPortals` /
`buildingRows` (with the town's special areas counted). A room's special areas are the overlay's own
`special_areas.txt` (the town's rows under its heading), which the server's `eloria/areas.py` reads after its base
rows (a base row may not name an overlay map); the run checks that the server's loader reads every one. Keys of the
block another tool wrote (`publish_npc_metadata.py`'s `npcMetadataAmendments`) are carried
over as they stand. An interior interactive's target is its source `target` when it names one (the smithy's anvil:
`smithing`), else its role's (`underground.py` INTERACTIVE_TARGETS: `notice`, `crafting`). The other tools read both
sources too:
`retarget_underground.py` (with `--map <interior>` it rewrites one interior only, its source, package and
`objects.json` records, and leaves the other's alone), `publish_cartography.py` (door dots with `kind` and
`category`, and the shop dots inside), `tools/prepare_underground_scenery.py` (one config per interior) and the
server's `tools/continent_v2_registry.py`.

The town's `objects.json` records come from `retarget_underground.py`: each building door's `{entrance, building,
exteriorTile, modelOffset, label, exitLabel, exitOffset, category?}` (no `scene`: the door is painted on the facade;
`modelOffset` moves the pick and label from the door tile onto the painted door, `exitOffset` into the interior
doorway), each stair end's `{passage, label}` and each interior interactive's pick-only record `{interactive: true,
pickOnly: true, label, modelOffset, height, radius}`: `modelOffset` is the source's `at` minus the tile's centre and
the size is the source's or the packaged prop's, and the client stands only a click shape there, named under the
pointer, with no ring, model or map mark (the prop is already in the room's scenery). Its music: the client source
`eloria-assets/source/audio/music-program.json` gives the map `home_day`/`home_night`, and
`eloria-assets/tools/sync_music_program.py` adds a zone per room from the package's chamber and space names, with the
digest of the `world.json` they came from (`zone_source_sha256`). The server copy carries the A3 isles' music, which the
client source does not, so the tool's whole-file run would revert it: `--map landfall_town` rewrites only that map's
block of the server file and leaves every other byte as it stands (a map the file lacks goes where the client source
orders it), and `--check` exits 1 while the block is stale. The server serves the map only to clients that declare
`landfall_town_v1`.

After a town source edit, in order: `build_town_interiors.py --owner-approved ...`;
`tools/prepare_underground_scenery.py --map landfall_town`; `retarget_underground.py --map landfall_town --server
<server checkout>`; `publish_cartography.py`; `eloria-assets/tools/sync_music_program.py --server <server checkout>
--map landfall_town` (the block records the package `world.json`'s digest, so any rebuild that changes it needs
this); then the publication above (`publish_server.py --check`, and `--apply` only with the owner's approval).

## Boats

Owner-approved 2026-10-19 as in Eternal Lands: one boat per destination, several boats at a dock, all free, so players
chain boats to cross Landfall quickly. `content/boat-network.json` lists the docks and 12 of the 14 approved routes
(one boat each way). The hub is Lakehead Landing, a lake jetty on Reedfall's lake, with boats to Stagheath, Ravenhead,
Greenlight and Boarsend. It stands on the lake's east shore by Reedfall's arrival: the west shore at the Landfall
border is a 60 m cliff. The isles are reached from their nearest ports: Coilmere from Ravenhead (the 2026-10-14 ferry)
and Greenlight; Suncoil from Ringholm and Ravenhead; Hornmere from Stagheath; Whitepeak from Saltsound. Coastal
shortcuts join Boarsend-Greenlight and Stagheath-Saltsound. Warrenmead's two routes (Lakehead and Stagheath) wait on
the owner: the whole west coast (Warrenmead, Pinebrow, Twinbrook) is cliff, its nearest reached ground 136 m up and
78 m from deep water, so no dock is reachable without a cliff path.

`godot-client/tools/author_continent_v2_boats.py --apply` writes the network into the scenes and server rows. Every
generated node carries `boatNetwork: <dock id>`, and a rerun replaces the previous generation; `--check` refuses stale
output. A new dock is a `bridge_control` pier deck (walkable once exported) with trestle spans and a lantern. Each berth
has:
- a boat prop at the water level: the ferry ship for an isle crossing, a packet (fishing) boat otherwise, small lake
  boats at Lakehead (the lake is 1 m deep, so their keels sit in its bed);
- a harbour banner by the gangway;
- the boat's interactive `<map>--obj-boat-<dock>`, an object portal from object ID 30 up. Its text starts
  "Bound for <place>.", which the client shows as the destination;
- the landing `<map>--boat-landing-<dock>` 4 m shoreward, within `publish_server.BOAT_LANDING_REACH` of the boat that
  sails back.
The tool keeps each touched map's `runtimePointCount` equal to its scene's runtime points and adjusts
`authoredMarkerCount`. The A3 build stage's `boats/make_boat_network.py` designed the docks from the publisher's own
walk and reach grids (`publish_server.union_reach`): a pier's root stands on reached ground, its deck one step (under
0.9 m) from that shore (2.5 m above the sea where the shore allows, down to 1 m on low beaches), and it is the shortest
jetty whose berths float at draught inside the map, clear of solid props and moored boats. A berth on an existing pier
also needs its gangway and landing rings open and reached on the served grid. Greenlight's
boats use a jetty off the town quay, because the lighthouse pier B23 stands on a 1-1.8 m bank. The Coilmere knob quay
shelves too fast for the ferry, so route B (Greenlight-Coilmere) sails packet boats.

## Publication order

New kit GLB or PNG files need `godot --headless --path godot-client --import` before the bake. A bake made without it
was seen to pass, and `publish_client.py` then refused the package because an external image "is not hash-bound by the
snapshot" (`_embed_external_images` in `eloria-assets/maps/nymara-regions/_continent/authoring.py`); delete those
maps' bakes and bake again after the import. `publish_server.py` refuses a bake whose scene SHA-256 is not the
checkout's scene file (`read_bake`), so bake from the committed scene.

`publish_server.py --apply` writes `_continent_v2/publication.json` into the client checkout, and the server's sync
records the client checkout's HEAD as `clientCommit` in the server's `tools/collision/manifest.json`. Apply, commit
the record, then apply again so that provenance names the commit holding it; `--check` still passes when only that
recorded commit differs, and notes it as `provenanceOnly`. After a merge, regenerate the generated outputs
(crossings, publication records, each package's `world.json`, `collision.bin` and served grid) from the merged
sources instead of hand-merging them.

## Harvest presentation

Owner-approved 2026-10-14 (`work-output/landfall-audit-2026-10-14/harvest/FINDINGS.md` 5.1-5.6): inside a harvest
grouping every visible plant or rock of that kind is harvestable, as a patch node (the node's model is the whole
natural unit; only its centre tile blocks) or as promoted scenery (a placed kit model is the node's art). A
`Gameplay/Harvestables` marker may carry `variant`, `yaw`, `footprint`, `grouping`, `groupingName` and
`bindPlacement` extras; `harvest_presentation.py` is the schema and its checks. `publish_client.py` writes every
harvest marker into the territory manifest's `harvestables` (with `harvestablesSchema`) and the groupings into
`harvestGroupings`; packages from before carry an empty list and the client presents their nodes as it always did.
`publish_server.py` refuses a node whose tile centre lies within a road's half-width (D11) and judges harvest nodes
by the reach-side approach rule (D4: three ring tiles open and reached, or a reached tile within Chebyshev 2, and
the server's walk-to tile reached); `HARVEST_APPROACH_RULE = "ring"` restores the eight-neighbour rule.
