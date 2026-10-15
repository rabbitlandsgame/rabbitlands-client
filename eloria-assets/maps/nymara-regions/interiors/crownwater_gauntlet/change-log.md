# The Drowned Arcades — change log

## 2026-09-08 — the customs road beneath Crownwater

Organised the flooded route around bonded cargo inspection and civic
waterworks. Raised storage plinths and counters border the Customs Arcade,
while repeated marble frames lead along the Long Arcade. The Bell Walk
now has three masonry arches reaching the chamber bed and arcade frames
above its balustrades. Cistern troughs, screw lifts, handwheels and visible
outfalls explain the water. The fork separates an intact valve aisle from
a silted passage with fallen marble piers, and the great bell marks the
reward doorway above the upper court.

Shorter connecting passages remove thirty-six metres of empty traversal;
the route footprint is 325 metres and arrival to vault is 311 metres.
The existing seven legs, timed crossing, branch choice, boss court, Kelp
node, cache and waystones retain their roles. Cargo and machinery occupy
side bays so the published encounters retain clear fight floors. A rear
dais step completes the climb to the vault.

Added reusable arcadecraft recipes and promoted Crownwater's six material
recipes to the shared crownmaterials module. The exterior keeps a crownkit
compatibility entry point. All eighteen texture arrays and material specs
match the former implementation; exterior binaries were not rebuilt.
The gauntlet now uses that same marble, mosaic, sand, verdigris, gilt and
lagoon palette. Existing surface IDs and material names are preserved.

Manifest-lit review added walkable stone thresholds to retain the shallow
water, cut the flood around raised cisterns, and checked the hollow bell
from below. Liquid scenery has an explicit non-blocking material policy
while solid floor, walls and gate cuts still own the grid. Three regression
tests check that policy, bell orientation and repeatable material registration.
Twenty-two eye-level, isometric and detail captures were reviewed in Godot
Compatibility with OpenGL 3.

The package grows from 19,870 to 64,393 triangles and from 3.82 to 7.41 MB.
Its 256 local material meshes keep the 61 point lights near the intended
surfaces. Lids retain the gameplay cutaway contract.

Refreshed both published bands, the three collision copies, arrival constants,
gates, interactives, wave positions and the Kelp node. An audit confirms
creature types, counts, variants, rules, rewards, keeper coordinates and
exterior returns are preserved, and unrelated routes are unchanged. A
second layout refresh writes no files.

Validation: 1,809 server tests and 546 subtests pass. The client suite has
199 passes and the same 88 known failures, with 9,296 passing subtests;
failure identities match the preceding Barrow Run baseline. Every one of
the 3,637 walkable server tiles has exported ground. Legal routes through
both branches reach the court and vault. glTF has no errors or warnings,
and the coplanar scan reports zero overlap. The runtime verifier has no
errors and one expected warning for the blocked void around the rooms.

GLB, manifest and both collision artifacts reproduce byte-for-byte in an
isolated build. All builds, captures and tests used affinity mask 15 and
at most four CPU cores. See references/comparison.jpg and
references/validation.json for the evidence.
