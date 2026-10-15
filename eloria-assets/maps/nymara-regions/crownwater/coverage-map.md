# Crownwater coverage map

The 2026-09-07 layout pass supersedes older statements about shared causeway
length classes, landmark-centred door triggers and random harbour services.
See [layout-review.md](layout-review.md) for the current surveyed routes,
service court, habitat rings, captures and measurements.


Every authored place, what is built there, and how it is reached. Positions are
Godot metres; server tiles are `(x + 174, 174 - z)`.

## The crown isle - centre (114, -114), radius ~95 m, deck 8.0 m

| Place | Position | What is built | Reached by |
| --- | --- | --- | --- |
| The Drowned Crown (cathedral) | (114, -132) | Cruciform marble mass, great verdigris dome on a colonnaded drum, four lesser domes, west portico, walkable ceremonial stair | crown plaza |
| The Tide Campanile | (162, -150) | 26 m marble bell tower, arcaded belfry, verdigris cap, gilt finial | crown plaza |
| Crown plaza | (114, -87) | Mosaic paving, inlaid gilt compass rose (11 m), fountain, eight statues | 8 causeway spokes |
| Crown garden | (63, -102) | Planted ground | plaza |
| Crown quay south | (117, -33) | 34 m quay run, coping, apron, 4 bollards | plaza |
| Crown quay north | (108, -195) | 34 m quay run, coping, apron, 4 bollards | plaza |

## The pavilion ring - eight islets at radius ~162 m, decks 4.0-4.8 m

Seven carry a 6.4 m domed pavilion on a stepped walkable podium with a
twelve-column drum; each islet has four short quay runs on its cardinal faces.

| Islet | Position | Note |
| --- | --- | --- |
| `pavilion_east` | (276, -114) | pavilion |
| `pavilion_southeast` | (228, -35) | pavilion |
| `pavilion_south` | (114, -6) | pavilion |
| **`harbour_isle`** | **(-0.6, 0.6)** | **arrival islet - no pavilion, a working harbour** |
| `pavilion_west` / garden isle | (-48, -114) | pavilion + concentric planting beds and fountain (panel 8) |
| `pavilion_northwest` | (-0.6, -228) | pavilion |
| `pavilion_north` | (114, -276) | pavilion |
| `pavilion_northeast` | (228, -228) | pavilion |

## The harbour - the arrival islet, and the densest ground on the map

| Place | Position | What is built |
| --- | --- | --- |
| Default spawn | (-0.55, 4.55, 0.55) | on the islet, facing the city across the water |
| Harbour quay | (26, -20) | 42 m quay run, 6 bollards, 4 moored boats |
| Lamp walk | (5, -32) | 36 m quay run, 8 lamp standards, 4 banner poles (panel 6) |
| Harbour market | (-25, 10) | 7 canvas-awning stalls |

## The outer ring - eight islets at radius ~264 m, decks ~3.0 m

Six carry a 4.2 m pavilion; `outer_northeast` carries a 19 m watch tower and
`outer_southwest` a 23 m lighthouse. Four are portal quays.

| Portal | Islet | Destination |
| --- | --- | --- |
| `north-quay` (Mirrorhold Packet) | `outer_north` (215, -358) | `maps/nymara/mirrorhold.elm` |
| `east-quay` (Amethyst Barrens Packet) | `outer_east` (358, -13) | `maps/nymara/amethyst_barrens.elm` |
| `south-quay` (Westhaven Packet) | `outer_south` (13, 130) | `maps/nymara/westhaven.elm` |
| `west-quay` (Amberwood Packet) | `outer_west` (-130, -215) | `maps/nymara/amberwood.elm` |

## Under the water

| Place | Position | What is built |
| --- | --- | --- |
| The Sunken Court | (-6, -78), floor -1.90 m | 13 m mosaic platform with a gilt inlaid glyph, nine ruin fragments around it (panel 7). Scenery, not a walk surface. |

## Causeways - 22 crossings, 3 unique meshes instanced

| Group | Count | Deck |
| --- | --- | --- |
| Spokes, crown isle to each pavilion islet | 8 | 8.0 m |
| Ring, pavilion to adjacent pavilion | 8 | ~4.8 m |
| Reaches, pavilion to outer islet | 8 | ~4.0 m |

Each deck is a registered walk surface and owns its footprint in `collision.bin`
at deck height; the water beneath is not separately walkable. 84 elevated decks
in total, counting quay aprons and pavilion podiums.

## Traversal

Every island on the map is reachable on foot from the default spawn: the outer
ring connects to the pavilion ring, the pavilion ring connects around itself and
inward to the crown isle. There is no island that requires swimming, and no
walkable ground that is not connected.

25.6% of the 576 x 576 footprint is walkable. The remaining 74.4% is water,
which is correct for this region and is why the walkable fraction is far below
Amberwood's 70.3%.

## Population markers - server authoritative, nothing baked

| Kind | Count |
| --- | --- |
| NPC markers | 12 |
| Interactives | 5 (cathedral doors, two fountains, harbour bell, sunken glyph) |
| Harvestables | 26 (shellfish, reed, coral) |
| Portals | 4 |
| Landmarks | 10 |
