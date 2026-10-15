# The Coil Causeway — change log

## 2026-09-08 — ceremonial waterworks and hatchery

Organised the route around its procession and hatchery lore. Three supported
sun-marked gateways divide the Lily Causeway into short reaches. The Water
Gate has paired lily basins, and the Hatchery separates a wall-fed trough
from dry incubation beds. Repeating gallery seals lead to a wet, rooted branch
or a carved ceremonial branch. A large spiral sun seal crowns the court's
reward doorway. Shorter gate passages remove 36 metres of empty traversal.

Added reusable templecraft recipes for seals, gateways, open basins,
spillways, lily clusters and nesting mounds. All retain the jade, weathered
stone, gold and muted vegetation of Ssarathi's concept board. Close-up review
replaced masonry on eggs and fern cutouts on lily pads with dedicated
procedural eggshell and opaque leaf textures. Both material recipes are
appended; terrain surface classes are unchanged.

The review also caught inward-facing cylinders on the new opaque discs and
a spillway facing the wall. The new recipes explicitly face them outward,
and leaf UVs now centre the radial veins. Two regression cases check face
winding against declared normals. Existing primitive defaults remain intact.

The package grows from 15,462 to 79,200 triangles and from 3.38 to 6.66 MB.
Its 258 local material meshes keep the 46 point lights near their surfaces.
Twenty final eye-level, isometric and detail captures were reviewed with
Godot Compatibility, OpenGL 3, manifest lighting and gameplay cutaways.

Refreshed both published bands, all three collision copies, arrival constants,
gates, interactives and the Lichen node. Creature types, counts, variants,
rules, rewards, keeper coordinates and exterior return points are preserved;
unrelated routes are unchanged. Fixed the layout refresh to read a
harvestable's resource field. Its regression exercises preview, apply and a
second apply while preserving the label, object ID and file newlines.

Validation: all 1,803 server tests and 546 subtests pass. The final client suite
has 194 passes and the same 88 known failures, with 9,284 passing subtests;
failure identities match the previous pass. Every one of the 3,686 walkable
server tiles has exported ground, and legal routes through either fork reach
the court and vault. glTF has zero errors and warnings; the coplanar scan
reports zero overlap. The runtime verifier has zero errors and one expected
warning for the blocked void around the rooms.

GLB, manifest and both collision artifacts reproduce byte-for-byte in an
isolated build. The final material and face corrections leave the tested
collision artifacts unchanged. CPU affinity mask 15 limited all builds,
captures and tests to four cores. See references/comparison.jpg and
references/validation.json for the evidence.
