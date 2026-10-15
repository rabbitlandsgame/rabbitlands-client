# Sunmane Steppe — landmark checklist

Tracked from the written region description (`eloria-assets/qa/regions/sunmane-steppe/README.md`,
`NYMARA_ASSET_MANIFEST.md`), the aerial overview (`references/01-aerial-overview.png`) and the
ten-panel detail board (`references/00-concept-detail-board.png`).

Authority order: written description > aerial composition > player-scale detail board > runtime conventions.

## Region frame

| Property | Value | Source |
|---|---|---|
| Server arrival datum | `(58, 58)` | region description / `regions-connections.json` |
| Metres per tile | 1.0 | `godot-client/data/maps/registry.json` |
| World span | 280 m x 280 m, centred on godot `(36, -36)` | derived |
| Addressable band | godot X -58..133, Z -133..58 | server tiles are non-negative |
| North axis | `-Z` | `world-manifest-1.schema.json` |
| West crossing | server `(6, 58)` -> godot `(-52, 0)` | Mirrorhold link (west road) |
| North crossing | server `(66, 184)` -> godot `(8, -126)` | Amethyst Barrens link (desert track) |
| South crossing | server `(62, 18)` -> godot `(4, 40)` | Verdant Stair link (shore road) |
| North barrow | server `(58, 100)` -> godot `(0, -42)` | sealed passage; the Archive is entered from the Ssarathi Ruins |

## Written-description inventory (exact counts asserted by regional QA)

| # | Item | Count | Status |
|---|---|---:|---|
| A1 | Orun clan camps | 4 | **done** |
| A2 | Round tents | 12 | **done** |
| A3 | Seasonal market structures | 4 | **done** |
| A4 | Banner shrines | 8 | **done** |
| A5 | Caravanserais (on travel axes) | 4 | **done** |
| A6 | Windmills | 6 | **done** |
| A7 | Wells | 4 | **done** |
| A8 | Animal pens | 6 | **done** |
| A9 | Burial mounds | 6 | **done** |
| A10 | Warm landmark lights | 8 | **done** |
| A11 | Transition lights | 4 | **done** |
| A12 | Terrain classes: clan clearing, open steppe, caravan road, dry grass | 4 | **done** |
| A13 | Ceremonial crossroads at the arrival datum | 1 | **done** |

## Expansion inventory (north and east)

Added after the original build, at the user's request: the desert, the cave
entrances and the mountain boundary. These have no count in the written region
description - they extend the region toward its neighbours - so the target is
the continent design rather than a QA number.

| # | Item | Count | Status |
|---|---|---:|---|
| D1 | Desert ground: dune trains, salt pans, wash-interlocked margin | 12.2% of the map | **done** |
| D2 | Amethyst badland ground, carrying the Barrens' violet muted | 6.7% | **done** |
| D3 | Mountain scree and bare stone closing the north and east | 12.7% | **done** |
| D4 | Named summits along the Whitehorn front | 11 | **done** |
| D5 | Wind-carved badland spires | 8 | **done** |
| D6 | Cave entrances | 4 | **done** |
| D7 | ...of which lead to explorable interiors | 2 | **done** |
| D8 | Desert water stations on the sand road | 2 | **done** |
| D9 | Waystones marking the sand and badland tracks | 8 | **done** |
| D10 | Additional outposts (desert, mountain, eastern pass) | 3 | **done** |
| D11 | Desert drovers' camps | 3 | **done** |
| D12 | New roads: desert road, salt-pan spur, badland track, dune crossing, mountain approach, east pass, spire walk | 7 | **done** |
| D13 | Amethyst crystal clusters | 12 placed + scatter | **done** |
| D14 | Desert cover: dead scrub, bleached bone, loose stone, scree fans | scatter | **done** |

### Cave interiors

| # | Item | Wind Caves | Crystal Hollow | Status |
|---|---|---|---|---|
| C1 | Chambers | 5 | 5 | **done** |
| C2 | Connecting passages | 4 | 4 | **done** |
| C3 | Timbered passage sets | 7 | 10 | **done** |
| C4 | Brazier light markers | 5 | 5 | **done** |
| C5 | Crystal light markers | - | 3 | **done** |
| C6 | Underground camp | 1 | 1 | **done** |
| C7 | Still-water pool | 1 | - | **done** |
| C8 | Exit portal back to the steppe | 1 | 1 | **done** |

Both interiors continue the region's material language - pale canvas is absent
underground, but the timber, iron, leather and bone are the kit the surface
uses, and the amethyst is the same crystal family as the badland.

## Aerial-overview composition

| # | Feature | Status |
|---|---|---|
| B1 | Central fortified encampment on a polygonal timber palisade ring | **done** |
| B2 | Monumental white-canopied central hall with gold finial | **done** |
| B3 | Two substantial gatehouses with paired ornamental towers | **done** |
| B4 | Palisade corner watchtowers and wall walk | **done** |
| B5 | Roads radiating from the settlement into the landscape | **done** |
| B6 | Rugged coastline west and south-west, turquoise water, coves and beaches | **done** |
| B7 | Sea stacks, rocky headlands and cliff barriers at the world rim | **done** |
| B8 | Landing point / timber dock on the south-west cove | **done** |
| B9 | Flat-topped mesas north, eroded formations east | **done** |
| B10 | Standing-stone circles (two sites) | **done** |
| B11 | Waterholes / ponds fed by a steppe stream | **done** |
| B12 | Satellite tent clusters away from the main camp | **done** |
| B13 | Remote outpost towers on rock | **done** |
| B14 | Circular and rectilinear horse paddocks with grazing herds | **done** |
| B15 | Wheat / dry grass fields with rough fences | **done** |
| B16 | Sparse trees along the coast and eastern breaks | **done** |

## Detail-board panels (player scale)

| Panel | Subject | Required in client view | Status |
|---|---|---|---|
| P1 | Caravan road | wheat field edge, riders, banner poles, settlement silhouette, mesas | **done** |
| P2 | Round-tent camp | timber door frame, entry steps, gold finial, cook fire, barrels, pots | **done** |
| P3 | Seasonal market | canopy row, goods, crowd, horses, banners, hall behind | **done** |
| P4 | Banner shrine | tall frame with hanging pennants, ornate shrine box on stone base, standing stones | **done** |
| P5 | Caravanserai gate | dark timber palisade, twin gold-tipped gate towers, hanging banners | **done** |
| P6 | Windmill | timber tower mill with four sails, hay, fences, wheat, coast beyond | **done** |
| P7 | Well and pens | stone well ring, A-frame and pulley, pottery, horses, tents | **done** |
| P8 | Golden-hour standing stones | hilltop stones, rider, low sun over the sea | **done** |
| P9 | Steppe overlook | rider on a ridge above the settlement and coast | **done** |
| P10 | Prop language | carved bone, leather and buckles, hammered metal, woven red/ochre textile, rope, wood | **done** |

## Verified counts in the exported package

- animal-pen: 6
- banner-shrine: 8
- bridge: 3
- burial-mound: 6
- caravanserai: 4
- gate: 4
- great-hall: 1
- landing: 1
- outpost: 5
- round-tent: 12
- seasonal-market: 4
- standing-stones: 13
- well: 4
- windmill: 6

Asserted on every run by `maps/nymara-regions/sunmane_steppe/source/validate_package.py`.

## Runtime population

| # | Item | Status |
|---|---|---|
| C1 | Grazing and hitched horses registered as runtime actors | **done** |
| C2 | Orun inhabitants placed through the actor runtime | **done** |
| C3 | Harvestable / resource nodes | **done** |
| C4 | Interaction points (wells, market, shrines, gates, dock) | **done** |


## Evidence

Every row above is evidenced by a capture in `comparison/` or by an assertion in
`maps/nymara-regions/sunmane_steppe/source/validate_package.py`:

| Item group | Evidence |
|---|---|
| A1-A13 exact counts | `validate_package.py` landmark inventory assertions |
| A10-A11 lighting | `world.json` -> `lighting.markers`, 8 warm + 4 transition |
| A12 terrain classes | `world.json` -> `terrain.classes`, six classes including the four described |
| B1-B5 settlement | `comparison/panel-05-*`, `comparison/aerial-overview.png`, `minimap.webp` |
| B6-B8 coast | `test-artifacts/sunmane-steppe/coast-southwest.png` |
| B9 mesas | `test-artifacts/sunmane-steppe/mesa-north.png` |
| B10 standing stones | `comparison/panel-08-*` |
| B11 waterholes | visible in `minimap.webp` and the aerial capture |
| B12-B13 satellites and outposts | `test-artifacts/sunmane-steppe/outpost-ridge.png` |
| B14 paddocks and herds | `test-artifacts/sunmane-steppe/animal-pens.png` |
| B15-B16 fields and trees | `comparison/panel-06-*`, `coast-southwest.png` |
| P1-P10 panels | `comparison/panel-01-*` through `comparison/panel-10-*` |
| C1 livestock | 84 animals across 15 groups, spawned at runtime |
| C2 inhabitants | recorded for the server in `server-integration.md` |
| C3-C4 resources and interactions | `world.json` -> `runtimePopulation.resources`, `interactives` |

### Known deviations from the concept art

Stated plainly rather than glossed:

1. **No human crowds.** The concept panels show people at the market, the gate
   and the camps. Inhabitants are networked actors owned by the server; they are
   specified in `server-integration.md` and are not placed by this package.
2. **Lower prop density than the painting.** The concept is a painted image with
   effectively unlimited detail. The map is denser than any sibling region here
   but still reads sparser than the reference at close range.
3. **Ambient animals do not wander.** They idle in place with offset animation
   phases; locomotion belongs to the server-driven actor path.
4. **Grass is opaque blade geometry, not alpha cards.** This avoids alpha
   sorting and cutout artefacts at the cost of a thinner sward than the painted
   grassland implies.
5. **The palette runs slightly cooler and paler** than the concept's painted
   golden hour under the default daylight profile. The declared `golden-hour`
   environment variant is closer to the reference; daylight was chosen as the
   default because it keeps the playable scene readable rather than muddy, which
   the brief asks for explicitly. Panel 8 is compared against the golden-hour
   capture, since its reference is painted at dusk.
6. **Panel 10 is compared at stall scale, not macro.** Its reference is an
   extreme close-up of tack, bone, buckles and woven cloth - a framing no
   gameplay camera reaches. The comparison uses the nearest view a player can
   actually stand in, which shows the same material language on the market
   counter, pottery, crates, pennants and awning.
