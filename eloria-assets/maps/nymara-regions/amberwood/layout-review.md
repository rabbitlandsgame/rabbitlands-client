# Amberwood layout review - September 2026

The arrival now belongs to a market town above the mill: world
(24, 40.8, -171), server (198, 345). Storage, crafting, training and information
share one clear court. The civic hall faces that court, lodges face its
streets, and the Mother rises above the northern roofline. The existing
continent crossings retain their IDs and destinations.

The north beck skirts the west of town and feeds an exposed mill wheel below
it. Its water uses a frozen descending bed survey. The western coves occupy
dry shore benches, the packet lies offshore beyond a descending quay, and
the kelp landing has its own complete timber approach. The quarry has a
six-metre haul road and freight shelter; the orchard approach has cultivated
rows. Smaller outland clearings bring the forest nearer its paths.

Seven crossings have complete bank surveys: the old bridge, long span,
ridge span, mill keeper's walk, grove footbridge, packet quay and kelp landing.
The grove path passes around the civic hall before crossing the beck.
Terrain is recessed below emitted walking skins, and road shoulders meet
their endpoints. Closed lodges and the guild hall declare their real solid
footprints. The great arch faces its forecourt and has a continuous stair
and podium; the Gate Undercroft has a visible entrance beside it.

The toolkit gains an open paddle wheel, watermill and continuous surveyed
water ribbon. Existing lodges and halls can retain their timber, plaster,
stone and shingle materials. The opt-in roof follows the lodge's longitudinal
ridge; its gables meet the roof edge. Existing callers keep their defaults.
No surface classes, imported meshes or external textures were added.

Every existing wildlife species and count is retained. Meadow grazers,
working-forest creatures and the remote ridge/ash roster occupy successive
habitats away from the main cart roads. Existing resource names, rare
ingredients, secret keys and room contents remain intact. The new training
post brings the exterior interactive count from 22 to 23.

The server-owned marker contract follows stable resource object IDs and NPC
names. Its 31 harvest markers and 14 NPC markers are recorded as tile data in
source/server-content.json. The builder resolves them onto its rendered
standing surface, so an independent rebuild does not restore stale positions.

## Verification

| Check | Result |
| --- | --- |
| Reachable from primary arrival | 23 departures, 29 NPCs, 88 creature spawns, 60 harvest nodes, 23 interactives |
| Unreachable authored content rows | 6 before, 0 after |
| Native walkable cells in arrival component | 903,425 / 914,181 before; 883,623 / 893,504 after |
| Server walkable tiles in arrival component | 219,623 / 221,890 before; 211,961 / 216,797 after |
| Full server Python suite | 1,774 passed; 546 subtests passed |
| Full client Python suite | 175 passed; 86 failed; 9,078 subtests passed |
| Client failure comparison | Exact same failed and subfailed entries as the rebased develop baseline |
| Geometry regressions | Six passed: materials, roof profile, arch stair, water ribbon, all surveyed decks and mill immersion |
| Runtime grounding | 331,776 samples, no misses, no errors; three scenery/discontinuity warnings |
| GLTF validation | No errors or warnings; five informational unused material notices |
| Coplanar overlap report | 1,074.5 square metres / 37 pairs before; 456.1 / 53 after |
| Determinism | Fresh exterior GLB, reduced GLB, manifest, corrected collision and minimap reproduce byte-for-byte |
| Content regeneration | Seven profile files, three vendored grids and client marker data repeat unchanged after protection points settle |
| Content preservation | Species/resource counts retained; unrelated NPC, spawn, harvest and interactive rows unchanged |
| Client marker contract | All 14 NPC and 31 harvest marker tiles agree with the server contract |

The exterior GLB grows from 34,413,056 to 36,445,172 bytes. Instanced
triangles grow from 2,798,632 to 3,084,104, mainly from the denser forest
around smaller clearings, working buildings and complete crossings.
The 51 materials and 114 embedded images are unchanged. Correct building
footprints and water channels reduce the nominal walkable area; the actual
content audit above is the test of access.

The complete exterior, four individual interiors, combined estate and secrets
were rebuilt. The exterior correction passes ran in order: refine heights,
open walking surfaces, stamp solid landmarks. Server collision, generated
maps, portals, authored content and scoped relocation were regenerated.
The guild master's post was moved off a steep edge onto the graded approach
after repeated generation exposed an oscillation between neighbouring tiles.

## Visual review and remaining work

The concept boards, 42 offline captures and 42 real Godot GL Compatibility
frames were reviewed. Godot used --environment=manifest. Fixed player-height
views cover the court, millrace, bridges, quay, cove, quarry and Mother
sightline. Reviewed WebP frames, four JPEG contact sheets and comparisons
are under references.

The underlying forest cards, broad cliff walls and some older waterfall
backings remain simpler than the concepts. Several original ground-level
camera subjects are obscured by foliage; the new fixed views document the
actual routes and service areas. The manifest's warm lighting leaves deep
shadows beneath the canopy, and the aerial view is intentionally hazy.

Residual overlap warnings include older lodge framing, roof intersections,
foliage and small masonry contacts. This pass reduces their area substantially
but does not claim that the entire legacy kit is free of overlap. Runtime
warnings describe cliff/bridge height discontinuities and two landmark
metadata points below nearby tree surfaces. Actual authored server content
is checked from the primary arrival, independently of those scenery points.
