# Verdant Stair landmark checklist

Region extent: 576 m × 576 m (server tiles 0–575 at one metre per tile, arrival
datum at server (174, 174)). Coordinates below are Godot metres, north toward
−Z. "Terrace" names the shelf a place stands on; see `modeling-assumptions.md`
for the stair coordinates the whole region is laid out in.

Status key: **built** — modelled, placed, grounded and verified in the package;
**partial** — present but below the standard the concept describes.

## The stair

| Terrace | Height | What is on it |
| --- | ---: | --- |
| seabed | −13 m | the lagoon, its inlet and sea stacks |
| strand | 0.4 m | beach, boat landing, mangrove bight, the Ssarathi Temple Road |
| quay | 7 m | west quay, quay market, plunge pool below the first fall |
| lower | 24 m | the arrival town: waygate, plaza, Tessara, Orru Moss, gardens, foot of the Grand Stair |
| middle | 46 m | the cenote, the canopy village, the market, the root and rope crossings |
| upper | 72 m | the water shrine, the aqueduct, the hanging gardens, the reclaimed terrace |
| temple | 100 m | the Green Temple, its court, the processional stair, the sun pavilion |
| summit | 124 m | ridge shrine, cloud terrace, the quarry, the Sunmane Steppe Pass |

## Checklist

| # | Item | Status | Where | Node / evidence |
| --- | --- | --- | --- | --- |
| 1 | Terraced cliff city climbing a diagonal | built | whole region | eight shelves, seven cliff risers, `terraces[]` in `world.json` |
| 2 | Monumental balustraded stair between levels | built | (−3, 24, −21) | `Landmark_GrandStair` — three flights, two landings, raked cheek walls, turned balusters, carved shrine posts |
| 3 | Helical stair descending a sink pool | built | (−18, 46, −102) | `Landmark_CenoteStair` — treads cut into the shaft wall, wet material below the splash line, broken rim balustrade |
| 4 | Banyan-root bridge over a gorge | built | (90, 47, −54) | `Landmark_Crossing_RootCrossing` — six braided roots, plank deck, hanging aerial roots, rope handlines |
| 5 | Rope suspension crossings high over gorges | built | four | `Landmark_Crossing_RopeCrossingLow/High`, `_RavineBridge`, `_VineBridgeNorth` |
| 6 | Canopy village: stilt huts and plank walkways among great trees | built | (−66, 46, −126) | seven banyans with aerial roots, four canopy platforms, five stilt huts, six plank walkways |
| 7 | Jade water-shrine gateway above a pool | built | (114, 72, −126) | `Landmark_WaterShrine` — carved piers on stepped plinths, double lintel with upturned ends, guardians, steps into the pool |
| 8 | Jungle trail through the understory | built | 25 routes | `roads[]` in `world.json`; trail surface class, graded and cleared of trees |
| 9 | Terrace overview: stacked levels, aqueducts, pools | built | whole region | `minimap.webp`, `09-terrace-overview` capture |
| 10 | Carved jade meander relief | built | temple screen, waygate | `verdant_carved_jade` material, `junglecraft.relief_panel` |
| 11 | Great temple as the region's summit landmark | built | (204, 100, −198) | `Landmark_GreatTemple` — four-tier pagoda, two wings, eleven-column screen, five relief panels |
| 12 | Multi-arch aqueduct crossing a gorge | built | (−57, 73, −345) | `Landmark_Aqueduct` — arcade sized from the gorge floor, real voids in solid masonry |
| 13 | Waterfalls where watercourses cross the risers | built | 21 sites found, 15 built | `Water_Falls_*`; sites computed from stream/riser intersections, not listed by hand |
| 14 | Turquoise cenotes and terrace pools | built | seven | `Water_Cenote_*` in `water_cenote` |
| 15 | Lagoon, beach and boat landing | built | (−105, 0, −18) | `Landmark_Quay`, five boats, `verdant_lagoon_sand` strand, `water_lagoon` |
| 16 | Terrace retaining walls with weep holes and vines | built | 30+ | `Wall_*`, `junglecraft.terrace_wall` |
| 17 | Colonnades and balustraded terrace edges | built | 24 courts | `Arcade_*`, `Rail_*` |
| 18 | Outlying camps and works | built | eight | fern camp, high camp, kiln yard, north pass, strand camp, south watch, north watch, quarry |
| 19 | Ruined and reclaimed terraces | built | five sites | `Ruin_*` at the reclaimed terrace, standing ring, north watch, deep jungle, marchstone |
| 20 | Two map transitions matching the server's own | built | (−168, 0.5, 0) and (390, 124, −150) | `portals[]`; Ssarathi Temple Road west, Sunmane Steppe Pass east |
| 21 | Natural boundaries preventing access to unfinished voids | built | all four sides | lagoon closes the south-west, 46 m cliff rim on the north and east, partial rim west and south where the ground is landward |
| 22 | Server population placed at the server's own tiles | built | 60 markers | NPCs, creature groups, harvestables and interactives from `config/eloria/*.txt`; 11 moved to standable ground, listed in `buildNotes` |

## Concept-panel coverage

| Panel | Subject | Capture |
| --- | --- | --- |
| 1 | Turquoise lagoon at the cliff foot, boat and landing | `01-lagoon-landing` |
| 2 | The monumental balustraded stair between terraces | `02-grand-stair` |
| 3 | Helical stair descending into a green sink pool | `03-cenote` |
| 4 | Banyan-root and plank bridge over a gorge | `04-root-bridge` |
| 5 | Rope suspension crossing high in the canopy | `05-rope-bridge` |
| 6 | Stilt huts and plank walkways among great banyans | `06-canopy-village` |
| 7 | Jade gateway and statues above a reflecting pool | `07-water-shrine` |
| 8 | Narrow trail through tree ferns and understory | `08-jungle-trail` |
| 9 | The stacked terraces, aqueducts and pools from above | `09-terrace-overview` |
| 10 | Material study: carved jade meander, mossy stone, rope, water | `10-relief-study` |

Captures live in `references/godot-captures/` (real client frames, rendered
through the project's own `WorldLoader` by `_toolkit/godot_capture.gd`) and in
`references/captures/` (offline previews from the authoring renderer). Every
sheet in `references/comparisons/` names which set it was built from.
