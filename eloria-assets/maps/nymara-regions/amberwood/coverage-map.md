# Amberwood landmark checklist

Region extent: 576 m x 576 m (server tiles 0-575 at one metre per tile,
arrival datum at server (174, 174)). Coordinates below are Godot metres.

Status key: **built** — modelled, placed, grounded and verified in the package;
**partial** — present but below the standard the brief describes.

| # | Checklist item | Status | Where | Node / evidence |
| --- | --- | --- | --- | --- |
| 1 | Central water-linked woodland settlement | built | (20, -116) | `Landmark_MootHall`, `Landmark_AmberHall`, 16 lodges, market, mill pool, streams |
| 2 | Monumental central tree canopy | built | (52, -176) | `Landmark_GreatTree_Wood` + five old-growth giants |
| 3 | Ancient arched stone landmark with ceremonial stair | built | (116, -68) | `Landmark_GreatArch` — podium, 23-step stair, cheek walls, water channels, ruined entablature |
| 4 | Colossal hollow-tree interior / root-integrated structure | built | (-52, -172) | `Landmark_HollowTreeHall` — chamber, stone stair, lanterns, buttress roots |
| 5 | Multi-storey timber-and-stone manor or civic building | built | (-8, -128) | `Landmark_MootHall` — three storeys, turrets, tracery, dormers, arched entry |
| 6 | Player-scale timber lodge with porch, balcony, chimney, workshop | built | 31 sites | `Building_Lodge_00` … `_15` |
| 7 | Ancient stone forest gate overtaken by trees and roots | built | (-12, -52), (148, -60) | `Landmark_ForestGate_0/1`, plus four root-grown arches |
| 8 | Formal garden, fountain, statue, courtyard, ceremonial terrace | built | (104, 20) | `Landmark_GardenFountain`, four statues, balustrades, `Landmark_GardenRotunda`, terrace fall |
| 9 | High stone bridge crossing a rocky stream or ravine | built | (80, -132), (104, -200) | `Landmark_HighBridge` (26 m, three arches over a 9.5 m ravine); `Landmark_OldBridge` in town |
| 10 | Elevated tree platform, suspension walkway, canopy work area | built | six platforms, five walkways | four `Landmark_CanopyPlatform_*`, three `Landmark_CanopyWalkway_*`, `Landmark_CanopyDwelling` |
| 11 | Amber / resin harvesting and craft presentation | built | 6 stations + diggings | `Interact_AmberBench_0..2`, `Interact_AmberBench_Canopy`, amber market stalls, amber harvestables |
| 12 | Coastal settlement and dock or ship landing | built | (-90, 12), (-40, 24), west cove | `Landmark_Harbour_Dock`, second dock, boats, fishing racks, harbour village |
| 13 | Multiple waterfalls / visible water descents | built | seven | `Water_Falls` at the coast cliffs, ravine and garden terrace |
| 14 | Road and trail network connecting all major locations | built | 21 routes | `roads[]` in `world.json`; graded into the terrain, lamp-lit on the main axes |
| 15 | Forest lookout structures and remote towers | built | eight | `Landmark_Watchtower_0..3` |
| 16 | Small outlying settlements or lodge clusters | built | eight | harbour village, hill hamlet, east lodge |
| 17 | Working forestry / timber / craft location | built | timber yard, charcoal camp, quarry, burnt mill, amber diggings | `Prop_TimberStack_*`, `Landmark_CharcoalKiln_*` |
| 18 | Eastern transition into damaged / barren environment | built | x > 188, with a burnt battlefield and cinder tower | ash surface class, burnt snags, abandoned camps, `ash-flats` landmark |
| 19 | Natural boundaries preventing access to unfinished voids | built | all four sides | sea to the west, 26 m mountain rim east/north/south, plus a coarse distant backdrop |

## Concept-panel coverage

| Panel | Subject | Capture |
| --- | --- | --- |
| 1 | Forest road under the amber canopy | `references/captures/01-forest-road.png` |
| 2 | Multi-storey stone-and-timber hall | `02-moot-hall.png` |
| 3 | Player-scale forest lodge | `03-forest-lodge.png` |
| 4 | Colossal hollow-tree entrance | `04-hollow-tree.png` |
| 5 | High stone bridge and watercourse | `05-high-bridge.png` |
| 6 | Root-overgrown ancient arch | `06-root-arch.png` |
| 7 | Garden, fountain, statue, terrace | `07-garden-terrace.png` |
| 8 | Canopy platform and amber working | `08-canopy-amber.png` |
| 9 | High overlook toward the settlement | `09-high-overlook.png` |
| 10 | Close material study | `10-material-study.png` |

Twenty further captures cover the remaining landmarks, the movement and
collision test locations and a golden-hour pass; see
`references/captures/index.json`.


## Every landmark in the shipped manifest

51 landmarks, 10 interactives, 30 roads.

| id | name | type | position (x, z) |
| --- | --- | --- | --- |
| `moot-hall` | The Moot Hall | civic | (-12, -192) |
| `amber-hall` | The Amber Hall | guild | (66, -150) |
| `amberwood-town` | Amberwood | settlement | (30, -174) |
| `great-arch` | The Amber Gate | monument | (174, -102) |
| `high-bridge` | The Long Span | bridge | (120, -198) |
| `old-bridge` | Millrace Bridge | bridge | (30, -132) |
| `west-forest-arch` | The Weeping Arch | ruin | (-48, -102) |
| `north-forest-arch` | The Kneeling Arch | ruin | (114, -276) |
| `axis-arch` | The Broken Arch | ruin | (138, -60) |
| `hollow-way-arch` | The Root Arch | ruin | (-48, -186) |
| `grove-arch` | The Sleeping Arch | ruin | (-102, -300) |
| `ridge-arch` | The Watcher's Arch | ruin | (252, -222) |
| `ash-arch` | The Cinder Arch | ruin | (312, -102) |
| `forest-gate-0` | The West Forest Gate | gate | (-18, -78) |
| `forest-gate-1` | The Ash Gate | gate | (222, -90) |
| `hollow-tree` | The Hollow Warden | tree-hall | (-78, -258) |
| `great-tree` | The Amberwood Mother | monumental-tree | (78, -264) |
| `canopy-camp` | The Resin Walk | canopy-works | (66, -210) |
| `garden-terrace` | The Sunken Garden | garden | (156, 30) |
| `garden-rotunda` | The Amber Rotunda | pavilion | (156, 20) |
| `harbour` | Resinlanding | harbour | (-135, 18) |
| `lookout-0` | The East Watch | lookout | (258, -210) |
| `lookout-1` | The North Watch | lookout | (240, -336) |
| `lookout-2` | South Gate Tower | lookout | (138, 120) |
| `lookout-3` | North Gate Tower | lookout | (72, -312) |
| `lookout-4` | The South Watch | lookout | (-48, 156) |
| `lookout-5` | The Cinder Tower | lookout | (366, 36) |
| `lookout-6` | Shrine Hill Tower | lookout | (210, -276) |
| `lookout-7` | Cove Watch | lookout | (-126, -180) |
| `wayshrine` | The Amber Wayshrine | shrine | (108, -42) |
| `timber-yard` | The Long Yard | industry | (216, 102) |
| `charcoal-camp` | The Burner's Camp | industry | (252, 24) |
| `ash-flats` | The Ashen Reach | transition | (324, -42) |
| `stone-ring` | The Nine Watchers | ruin | (-90, -42) |
| `sea-arch` | The Drowned Arch | sea-stack | (-44, -60) |
| `kelp-landing` | Kelp Landing | landing | (-98, 72) |
| `south-orchard` | The Long Orchard | agriculture | (48, 138) |
| `beekeeper` | The Skep Rows | agriculture | (90, 102) |
| `long-meadow` | The Long Meadow | clearing | (-12, 24) |
| `coppice` | The Coppice | industry | (156, -366) |
| `ridge-camp` | The Ridge Camp | camp | (222, -330) |
| `boundary-stone` | The Marchstone | marker | (288, -288) |
| `ash-chapel` | The Cinder Chapel | ruin | (312, -222) |
| `cinder-field` | The Cinder Field | battlefield | (378, -174) |
| `smoke-vents` | The Smoking Ground | transition | (354, -24) |
| `east-quarry` | The Long Cut | industry | (348, 132) |
| `far-watch` | The Far Watch | lookout | (384, 90) |
| `far-grove` | The Far Grove | old-growth | (-120, -384) |
| `east-grove` | The East Grove | old-growth | (198, -180) |
| `deep-grove` | The Deep Grove | old-growth | (-60, -330) |
| `upper-falls` | The Upper Falls | shrine | (60, -372) |

## September 2026 circulation coverage

The market arrival, civic frontage, Mother sightline, mill and its race,
old bridge, high span, ridge span, packet quay, dry western cove and quarry
haul road now have explicit layout treatment. New fixed player-height
views cover the market, mill, stone bridge, quay approach, cove, quarry and
Mother. The separate interiors and combined estate are rebuilt with the
exterior package. See layout-review.md for measured validation and limits.
