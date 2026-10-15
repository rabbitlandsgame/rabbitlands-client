> Historical record of the previous 576m package. The current 396m coordinate contract and layout are documented in [README.md](README.md) and [layout-review.md](layout-review.md); current metrics are generated in `performance.json` and `verification-report.json`.

# Westhaven: coverage map

What the concept art contains, and where it is in the map. Coordinates are the
aerial's 8 x 8 reading grid (`region.cell(u, v)`), with Godot metres alongside.
`u` runs west to east, `v` north to south.

The mapping is 1:1 — the painting's four edges are the playable square's four
edges — so any feature can be located in the painting by its grid cell.

## The aerial, feature by feature

| painting | grid (u, v) | world (x, z) | in the map |
| --- | --- | --- | --- |
| north-west cliff headland | 0.0–1.5, 0.0–1.9 | -174…-66, -325…-188 | `LEVEL["headland"]` 78 m mass, cliff face cut on its western flank, forced to `ROCK` surface |
| dark bell tower | 2.30, 1.62 | -7, -191 | `Landmark_Campanile`, 36 m |
| domed civic building | 3.52, 1.82 | 79, -177 | `Landmark_Domed_Hall`, brass dome, panel 9 |
| high civic terrace | 3.30, 1.52 | 64, -215 | `LEVEL["crown"]` 52 m band |
| citadel / cathedral mass | 3.24, 2.62 | 59, -136 | `Landmark_Cathedral`, aisled nave, crossing tower, apse |
| tall pale spire | 4.20, 2.40 | 128, -152 | `Landmark_High_Spire`, 30 m |
| long arcaded terrace | 2.62, 2.46 | 15, -148 | `Landmark_Great_Arcade`, 14 bays |
| great arched city gate | 2.32, 3.42 | -7, -78 | `Landmark_City_Gate` |
| dense red-tile roofs | 0.3–5.5, 0.9–4.6 | | 385 houses on 12 variants, aligned to the contour, terracotta pantile |
| arched span over west inlet | 0.98, 4.02 | -103, -29 | `Landmark_Harbour_Gate`, panel 1 |
| big moored ship, west quay | 0.72, 4.28 | -122, -11 | `Ship_Anchored_04` and the west quay run |
| custom house | 1.42, 4.34 | -72, -7 | `Landmark_Custom_House` |
| fish market | 2.34, 4.42 | -6, -6 | `Landmark_Fish_Market`, arcade + 9 stalls, panel 7 |
| working quay, whole front | 0.9–5.4, 4.6 | -100…160, +10 | one deck at `LEVEL["quay"]` 3.4 m, 6 quay-wall runs, 26 bollards |
| finger piers | 3.62 / 4.34, 4.86 | 28 / 80, +32 | `Landmark_Pier_A`, `Landmark_Pier_B`, panels 4 and 5 |
| cargo crane | 4.34, 4.88 | 80, +33 | `Landmark_Harbour_Crane`, treadwheel, panel 5 |
| shipyard, hull on stocks | 5.34, 4.66 | 210, +11 | `Landmark_Shipyard_Hull`, open frames, panel 6 |
| ropewalk | 5.02, 4.44 | 187, -5 | `Landmark_Ropewalk` |
| curved mole | 1.06→4.62, 4.62→5.18 | -98→158, +9→+50 | 10 `Mole_Run` sections, rubble mound + masonry deck |
| bastion on the mole | 1.62, 5.02 | -57, +37 | `Landmark_Mole_Bastion`, banner, panel 8 |
| light at the harbour mouth | 4.62, 5.18 | 159, +48 | `Landmark_Mole_Light` |
| ships at anchor | various, 4.9–5.1 | | 5 `Ship_Anchored_*` plus 2 alongside |
| sandy east bay | 6.72, 4.92 | 305, +26 | `SHORE` terrace, 3 boats drawn up |
| south-west rocky island | 0.5–3.3, 5.3–7.5 | | Gullstone, `LEVEL["gull_isle"]` 31 m, `ROCK` |
| tower on that island | 1.34, 5.94 | -78, +36 | `Landmark_Gullstone_Watch` |
| sea arch | 2.96, 6.42 | 55, +105 | `Landmark_Sea_Arch` |
| south-east lighthouse rock | 5.3–7.9, 5.5–7.5 | | Lamp Rock, joined to shore by a low neck |
| the great lighthouse | 6.62, 6.18 | 303, +120 | `Landmark_Great_Lighthouse`, 28 m, panel 2 |
| upland pasture, tree belts | 4.5–8.0, 0.0–4.5 | | `LEVEL["upland"]` 34 m, 257 trees in belts |
| roadside chapel | 6.28, 0.58 | 278, -283 | `Landmark_Upland_Chapel` |
| upland farm | 5.42, 0.96 | 216, -256 | `Landmark_Upland_Farm` |
| villa on the east hillside | 7.18, 3.58 | 343, -67 | `Landmark_Hill_Estate` |
| switchbacked hill roads | 4.3–7.4, 0.4–4.1 | | `north_road`, `east_road`, graded |
| east watchtower | 6.86, 2.34 | 320, -156 | `Landmark_East_Watch` |

## The ten panels

Every panel has a subject in the map and a camera framing it. The framings are
in `source/views.py` and are shared by the offline previews and the real client
captures, so the two line up.

| # | panel subject | capture | built as |
| --- | --- | --- | --- |
| 1 | arched harbour gate over the water | `01-harbour-gate` | `havenarch.gate_arch`: single tall arch on cutwatered piers, flanking towers |
| 2 | lighthouse on a wave-battered rock | `02-lighthouse` | `havenarch.lighthouse`: battered tower, corbelled gallery, glazed lantern, lead dome |
| 3 | cobbled street climbing through an arch | `03-quay-street` | `market_climb` ramp street, granite setts, warehouse frontage |
| 4 | ship alongside with a gantry | `04-cargo-pier` | `havenarch.pier` + `gantry` + `ship_hull` |
| 5 | timber cargo crane with a laden net | `05-harbour-crane` | `havenarch.harbour_crane`: A-frames, treadwheel, raked jib, net |
| 6 | hull under construction on the stocks | `06-shipyard` | `havenarch.ship_on_stocks`: keel, stem, sternpost, 15 open frames, garboard strakes, shores |
| 7 | fish stalls under awnings in an arcade | `07-fish-market` | `arcade_range` + 9 `fish_stall` with striped awnings and catch |
| 8 | sea wall bastion with a banner | `08-mole-bastion` | `havenarch.bastion`: battered drum, merlons, banner mast, stair from the mole deck |
| 9 | rooftop terrace over a brass dome | `09-crown-terrace` | `havenarch.domed_hall`: colonnaded drum, ribbed brass dome, balustraded terrace |
| 10 | dockside still-life of crate, rope, chain, fish | `10-chandlery-macro` | a composed prop cluster at the chandlery, with the random quay scatter excluded within 7 m |

## Coverage gaps

Things visible in the concept that are **not** in the map, and why:

- **Figures.** No NPCs, dock workers or crowds are modelled. The board's panels
  are full of people; the static mesh carries none, because actors are the
  server's and the client's actor system, not the map's. Twenty NPC markers
  record where they belong.
- **Rigging detail.** Ships carry masts, one yard, one sail and three shrouds
  each. The painting's ships have full standing and running rigging. At the
  distance any camera sees them from this is a triangle budget decision.
- **Chain and rope as physical objects.** Panel 10 shows heavy chain and coiled
  rope. The map has the toolkit's `fishing_gear` and mooring rings; a dedicated
  chain-link and coiled-rope prop was not written.
- **Interior spaces.** Nothing is enterable. The five finished regions each got
  an interiors pass on a separate branch; Westhaven has not had one.
- **Smoke, gulls, spray, banners in wind.** Declared in
  `environment.presentation` as zones and flags for whoever writes those
  systems; no particle geometry ships.
## Circulation additions, September 2026

| Feature | World x, z | Purpose |
| --- | --- | --- |
| cart climb | (49, 6) to (228, -136) | quay to upland loop, with the watch spire above the climb |
| crown link / upland gate | (64, -215) to (138, -205) | framed landward approach and a clear route back to the harbour |
| Gullscar fields | (212, -224), (240, -234) | enclosed growing strips below the farmhouse and cistern |
| Yard Bridge | (232, 5) to (284, 29) | carries the coast track over the shipyard gully |
| Lamp Causeway | (377, 22) to (371, 85) | raised route over the tidal saddle to the lighthouse |
| harbour service court | (22…48, -2…8) | information, storage, crafting and combat practice |

Views 21–25 document the cart approach, fields, tidal crossing, yard bridge and
service court at walking height. Their cameras are pinned; deck heights are
sampled from triangles rather than the top of each crossing's bounding box.
