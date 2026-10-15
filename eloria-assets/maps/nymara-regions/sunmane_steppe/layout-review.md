# Sunmane Steppe layout review

Reviewed September 2026 in Godot 4.7.2, GL Compatibility with
`--environment=manifest`. Builds, captures and tests shared the same four CPU
cores through processor affinity. These are static package captures; server
NPC and service placement is checked against the content and collision data.

The central hall remains the navigation landmark. Its red canopy is visible
above the palisade from the pasture and western road. Arrivals pass through a
ford, gate or saddle, then reach the market service court. Inns face side
forecourts, grain sits below the settlement, and the beck has a continuous
downstream survey. Safe pasture surrounds the market, stronger wildlife
occupies the outer breaks, and the badland and dune margins carry the dangerous
groups. The northern traverse has water stations, a sheltered camp, salt work
and menhirs between the market and the border.

| Review | Images |
|---|---|
| Settlement, inn, cove and badland | [Sheet 1](references/layout-review-1.jpg) |
| Hall, gates, roads and market | [Sheet 2](references/layout-review-2.jpg) |
| Bridges, wells and northern approaches | [Sheet 3](references/layout-review-3.jpg) |
| Court, waterhole, arrival, inn and salt pan | [Sheet 4](references/layout-review-4.jpg) |
| Concept comparisons | [Comparison index](comparison/index.json) |

The final review corrected a stream entering the west inn, gaps under the
hall's roof tiers, a camp embedded in a hillside and outdated camera positions.
The three bridges meet dry approaches at player height. The market's open
aisle and the hall remain readable at the default and wider gameplay views.

The machine-readable [validation record](references/layout-validation.json)
includes the final hashes, access counts and runtime findings.

## Access and retained content

Flood fill starts only at the actual arrival, server (79, 37), world (21, 21).
Secret returns do not seed disconnected habitat.

| Measure | Before | After |
|---|---:|---:|
| Reachable exterior departures | 19 / 19 | 19 / 19 |
| NPC posts | 27 | 27 |
| Wildlife posts / species | 54 / 18 | 54 / 18 |
| Harvest nodes | 35 | 48 |
| Interactive rows | 20 | 21 |
| Unreachable authored content rows | 13 | 0 |
| Server walkable tiles connected to arrival | 25,920 / 28,105 | 24,428 / 26,248 |
| Native walkable cells connected to arrival | 108,117 / 119,023 | 103,223 / 112,959 |

Total walkable area decreases because actual walls and water now block walking.
All content is connected despite remaining isolated scenery ground. The extra
interactive is training in the service court. The 13 extra harvest nodes use
existing catalogue resources with explicit local habitats. Territory (79, 43)
moves one tile to dry ground at (79, 42). Content rows outside the three scoped
Sunmane maps remain unchanged.

## Validation

The full server suite passes 1,776 tests and 546 subtests. The client suite has
178 passes and the same 86 existing failures, with 9,078 subtests passing.
Failure identities match the preceding Amberwood baseline. The focused map,
crossing and collision suite passed 112 tests before the final camp adjustment;
the complete suites cover the final artifact.

The package validator passes all 825 checks. Both surface detail levels pass
the Khronos glTF validator with zero errors and zero warnings. The runtime
verifier samples all 36,864 server tiles with zero grounding misses and zero
errors. Its one warning reports 135 large adjacent height differences at
cliffs, bridge layers and the addressable boundary.

The two GLBs, both manifests and native collision reproduce byte for byte in
a separate output directory. Repeating the scoped server sync, portal,
content and relocation pipeline converges with no changed files. Rebuild LOD2
after refreshing source/server-content.json so its marker metadata uses the
same final posts.

The overlap scanner falls from 47.2 to 37.2 square metres. Its residual 31 pairs
include legacy cart, cave-frame, scree, tent trim and small structure/terrain
contacts, including an underside contact at the downstream bridge landing.
This is not a claim of zero residual overlap. The reviewed walking decks and
water skins have no visible shimmer in the captured views.

## Cost and remaining limits

LOD1 is 19,249,384 bytes, 244,565 unique mesh triangles and 958 nodes. LOD2 is
10,171,192 bytes, 152,687 triangles and 334 nodes. The existing ten embedded PBR
families and 30 textures remain. Grass still uses sparse opaque blades and the
outer mesas keep the established stylised heightfield forms.

The minimap now matches its declared one pixel per metre: 280 by 280, with a
1024-square full map and 512-square preview. Historical frame-time measurements
in performance.json predate this layout and are not a measurement of the new
package. The current pass verifies geometry, grounding, content and rendered
composition, not live multiplayer crowds or new frame-time benchmarks.
