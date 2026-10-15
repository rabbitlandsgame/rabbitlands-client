# The Red Canyon — change log

## 2026-09-08 — an open herd wash through the sandstone

Replaced the gauntlet's enclosed masonry treatment with open eroded banks,
full-height mouths and short rock slots. Wind-cut remnants, undercut herd
shelters and sparse dry bedding give the rooms a physical purpose. A
surviving rock rib crosses the dry ravine; the Shade Fork has broad ledges
while the Sun Fork stays exposed. Staggered remnants divide the Long Wash,
and a split sandstone crown marks Duskmane's court and the reward gap.

Connecting passages shorten from twelve to eight metres, removing
thirty-six metres from arrival to vault: 347 becomes 311 metres. The
geometry footprint, including the backs of the banks, is about 331 metres.
The existing seven legs, two-abreast timed crossing, fork choice, Seed
node, boss shelf, cache and waystones retain their roles. A rear step
completes the route from the boss shelf to the vault.

Added shared canyoncraft recipes for eroded banks, open cuts, surveyed
ramps, rock ribs, remnants, undercut shelters and dry grass. A new
procedural sandstone family and a sand variant append two material names
without changing existing IDs or terrain classes. The sand reuses the
shared packed-earth map; timber, cloth, lamps and bones retain existing
recipes. The exterior Sunmane package was not rebuilt.

The collision contract caught a long ramp triangle becoming a three-metre
step under conservative peak-height sampling. Its walking skin now uses
strips no longer than 0.4 metres, matching the visible slope without a
grid patch. Three regression cases check diagonal and reversed ramp
surveys, ray coverage and the exported height progression.

Manifest-lit review corrected shelter orientation, seated the ridge
standards, softened sunlight and closed eroded corner seams. Dry-grass reverse faces now carry reverse
normals, so the two sides light correctly. Small corner
remnants leave the narrow landing centres clear. Buried passage end caps
were removed where they nearly shared the adjoining bank plane. Twenty-two
eye-level, isometric and detail captures were reviewed in Godot
Compatibility with OpenGL 3, including the final affected joins.

The package grows from 17,310 to 42,713 triangles and from 3.97 to 7.15 MB.
It uses 105 local material meshes, eight materials and six point lights,
with sunlight doing the main lighting. The small visible ledges over side
bays provide shade; the main route remains open to the sky.

Refreshed both published bands, the three collision copies, arrival
constants, gates, interactives, wave positions and the Seed node. A scoped
audit confirms creature types, counts, variants, rules, rewards, keeper
coordinates and exterior returns are preserved, and unrelated routes are
unchanged. A second layout refresh changes no files.

Validation: 2,033 server tests and 498 subtests pass. The client suite has
202 passes and the same 88 known failures, with 9,305 passing subtests;
failure identities match the rebased publish baseline. Every one of the
3,640 walkable server tiles has exported ground. Both branches, every gate,
the climb, court and vault pass the route contract. glTF has no errors or
warnings, and the coplanar scan reports zero overlap. The runtime verifier
has no errors and one expected warning for blocked void outside the route.

GLB, manifest and both collision artifacts reproduce byte-for-byte in an
isolated build. All builds, captures and tests used affinity mask 15 and
at most four CPU cores. See references/comparison.jpg and
references/validation.json for the evidence.
