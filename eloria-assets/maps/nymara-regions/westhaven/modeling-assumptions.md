> Historical record of the previous 576m package. The current 396m coordinate contract and layout are documented in [README.md](README.md) and [layout-review.md](layout-review.md); current metrics are generated in `performance.json` and `verification-report.json`.

# Westhaven: modelling assumptions

What had to be decided without an authority, and on what grounds. Read this
before changing anything structural, because most of it is load-bearing.

## Authorities used

| Question | Authority |
| --- | --- |
| what is where, relative to what | `references/01-concept-aerial-overview.png` |
| what things look like at 1.7 m | `references/00-concept-detail-board.png`, ten panels |
| how the client grounds an actor | `godot-client/src/world/world_loader.gd`, `main.gd::_place_actor_on_surface` |
| server tile to Godot metres | `godot-client/src/world/coordinate_adapter.gd` |
| the manifest's shape | `godot-client/schemas/world-manifest-1.schema.json` |
| what a finished package looks like | `maps/four-gates-city/`, and `amberwood/`, `crownwater/`, `mirrorhold/` |

The detail board that shipped in this package was truncated to 786,445 bytes
and only its top row of five panels decoded. An intact 1983 x 793 board was
supplied and is what `references/00-concept-detail-board.png` now holds; it
inflates cleanly and all ten panels are readable.

**No authoritative written description of Westhaven was available.** Every
proper name in this package is invented. See "Names" below.

## Reading the aerial

The painting is a working port, not a coastal village. Four things in it drive
the whole composition:

1. **The city steps down to the water in level bands** with retaining walls
   between them. That is what makes its silhouette read from the harbour, and
   it is why the terrain is authored as an explicit terrace staircase rather
   than as a smooth slope with houses dropped onto it. An early version did the
   latter and produced a hillside of scattered roofs with no skyline.
2. **A curved mole closes a harbour basin.** The water inside it is calm and
   shallow; the water outside is not. That is the difference the region is
   built around.
3. **The waterfront is one continuous working deck** with piers, cranes and a
   shipyard along it - a port's quay is a single datum because cargo has to
   roll along it. It is authored at one level (`LEVEL["quay"]`, 3.4 m) for its
   whole length.
4. **Two rocky masses stand out in the water to the south**, each carrying a
   light. They are bare stone, not green islands.

### The 1:1 mapping

The aerial is read on an 8 x 8 cell grid with cell (0, 0) at its north-west
corner. `region.cell(u, v)` converts a grid coordinate to design space, and
`region.SCALE` (3.0) converts design space to world metres, so one reading cell
is 72 m and the painting's eight cells are exactly the playable 576 m.

The offsets are chosen so the painting's four edges *are* the playable square's
four edges. Nothing is invented beyond the concept and nothing is trimmed out
of it. That required moving the arrival datum - see below.

## Decisions

### The arrival datum is at server (174, 250), not (174, 174)

The five finished 576 m regions share (174, 174), which puts the spawn 30% of
the way up the map from the south. Westhaven's concept is 40% open water and
its spawn belongs on the quay, so at (174, 174) only 30% of the map could be
sea: the harbour, the mole and both lighthouse rocks would be crushed into a
third of the frame while the upland got more room than the painting gives it.

Moving the datum 76 cells south buys the exact 1:1 mapping above. It is data on
both sides - `coordinateTransform.serverOrigin` in `world.json`, `ARRIVAL_TILES`
in the server's `tools/generate_nymara_maps.py` - and no code changed.

### The sea floor is terrain, not a hole

The client casts a grounding ray down at **every** server tile, not only
walkable ones. A region that is 30% open water still needs a continuous surface
underneath it, so the heightfield covers the whole footprint and simply sits
below sea level across the south. That is what makes zero grounding misses
achievable here at all. Those tiles ground successfully and are marked
unwalkable in `collision.bin`.

### One water body, not two

The painting does show the sheltered harbour reading differently from the open
sea, and the first version modelled that as two planes - a greener, more opaque
harbour body two centimetres above the sea plane. Two blended planes that close
together z-fight, and the whole basin came back as a checkerboard.

The distinction is a shader concern, not a geometry one. The manifest declares
`environment.water.shallowColor` and `deepColor`, and the depth that would drive
them is already in the terrain: the basin is dredged to -7.5 m and the sea
outside the mole falls to -17.

### Lamp Rock is joined to the shore; Gullstone is not

Panel 2 frames its lighthouse on a wave-battered islet. The aerial is ambiguous
about whether that mass is an island or a headland. Lamp Rock is modelled as a
promontory joined to the east shore by a low neck the surf breaks over: it reads
as an islet from the harbour, which is panel 2's framing, and it is walkable,
which makes the lighthouse a place a player can go rather than scenery.

Gullstone, to the south-west, is a genuine island. Its tiles are grounded and
walkable but form an isolated component, reachable only by boat - which the
client does not model yet. That is recorded in `knownLimitations`.

### Terrace risers are not walkable

The city's level bands are separated by retaining walls of 6 to 12 m. Those
risers exceed the walkable slope limit deliberately: they are walls. Every
terrace is reachable along the graded ramp streets (`market_climb`,
`gate_climb`, `arcade_walk`, `crown_climb`), and the 202 grounding
discontinuities `verify_runtime` reports are these risers plus the sea cliffs
and the map's north and east rim.

### No landmass backdrop

Amberwood ships one because its mountain walls need something to stand in front
of. `terrain.backdrop` takes a single `open_side`, and Westhaven is open on two
- the sea closes both the south and the west - so any single choice walls one of
them off. The first aerial came back with a continent of grey rock standing out
of the ocean along the whole western horizon.

Nothing is lost. The north and east are closed by an 88 m rim and the highest
place a player can stand is the crown terrace at 52 m, 200 m short of it, so no
viewpoint sees over the rim to the sky behind it.

### The world boundary

North and east are closed by rising ground, which is what the painting shows
anyway. South and west are closed by open sea and are given no wall: a rim on
all four sides reads from any elevated camera as a dark slab floating at the map
edge.

## Materials and kit

Westhaven adds nine material specs and eight texture recipes, all
`westhaven_`-prefixed, in `source/havenkit.py`. They are registered by extending
`materials.SPECS` **in memory at build time** rather than by editing the shared
table, because four unfinished regions are queued to append to that tuple and
three independent appends is the silent-corruption case its own comment warns
about. Promotion later is a copy-paste. The same applies to `source/havenarch.py`,
the maritime kit.

What the shared table could not supply:

| | why not the shared one |
| --- | --- |
| `westhaven_sett` | `cobble_paving` is a mossy woodland courtyard; a quay is square-cut kerbstone in courses, worn in the cart ruts |
| `westhaven_quay_plank` | `timber_grey` is a dry building plank, not tarred salt-bleached decking |
| `westhaven_tide_shingle` | `shore_shingle` is a dry beach and reads bone-pale against this water |
| `westhaven_salt_turf` | `meadow_grass` is inland pasture, far too lush for a headland |
| `westhaven_sea_rock` | `cliff_rock` is warm inland sandstone; this is cold grey stone banded at the tide line, which is panel 8's whole subject |
| `westhaven_pantile` | `shingles` is a grey-brown wooden shake. Terracotta roofs are the concept's loudest colour and roofing the city in shakes lost it |
| `westhaven_sailcloth` | `canvas_awning` is a bright striped market awning - right for panel 7, and it turned every ship in the harbour into a fairground tent |
| `westhaven_harbour_water` | a retint of the shared water texture, not a new surface |
| `westhaven_brass` | a retint of `dark_iron`; panel 9's dome was reading as cast iron |

The material set embedded in the GLB is pinned to what the region actually
references. `shingles`, `cobble_paving`, `bark_pale` and `water_sea` were all in
the pin and all superseded by a Westhaven recipe; the build's own
unreferenced-material warning caught them and each was costing its textures in
every package.

## One addition to the shared toolkit

`_toolkit/regionpaths.py` gained `region_material_sets()`, and
`_toolkit/capture_views.py` now calls it. Before this, `capture_views` built its
preview scene from the shared material table only, so a region that registers
its own materials at build time rendered them through whatever the lookup fell
back to. For Westhaven, whose terrain materials are *all* its own, every offline
preview came back as one flat sand colour with no water in it and nothing said
so.

The hook is opt-in: a region defines `register_materials(sets)` in its build
module or it does not, and regions using only shared materials are unaffected.
Crownwater has the same latent problem and can adopt it with one function.

## Names

Every proper name here is a placeholder. The authoritative written region
descriptions were not available, so these were chosen to fit the concept art and
should be replaced by whoever owns the setting:

Gullstone (island, bastion, watch), Lamp Rock, the Lamp Rock Light, the Mole
Light, the Harbour Gate, the Sea Gate, the Long Arcade, the Haven Church, the
Bell Tower, the Astronomers' Hall, the Watch Spire, the Mariners' Guild, the
Custom House, the Fish Market, the Ropewalk, the Westhaven Yard, the Wayside
Chapel, Gullscar Farm, the Factor's House, the East Watch, and all twenty NPC
markers.

The region's own name, "Westhaven", comes from the registry key and is not
invented.
## September 2026 circulation and working-ground pass

The city still occupies the concept's terraced headland, with the campanile,
spire and brass dome retaining their skyline. A cart climb now connects the
working waterfront to the upland crossroads. Its switchbacks follow the east
shoulder; a second connection joins the crown terrace to the north gate, making
a loop instead of a road that ends behind the city.

The farm road passes south of the farmhouse, and the coast road passes west
of the Factor's House. Their doors face a lane rather than a carriageway through
the building. Gullscar's enclosed strips sit below its house, with a cistern
above them. This remains a rainwater-fed coastal farm: no river has been
invented where the concept shows none.

The existing shore route crosses the shipyard gully on the Yard Bridge and
the Lamp Rock tidal saddle on a raised causeway. These are authored walking
surfaces with masonry piers, sloping decks and broad landings. Gullstone remains
the separate island described above.

The server service court uses the main quay's geometry: information, shared
storage, crafting and combat practice form one short circuit, with the Amber
berth nearby. Habitat discs put grazers around the farm, crabs and herons by the
east bay, and hounds in the outer upland. Roads are excluded from wildlife
placement. This is geographic placement of the existing species, not a change
to their combat statistics.

New recipes live in shared `amberwood.routecraft`; existing Westhaven timber,
stone, grain and paving materials carry them. No surface classes were added.
