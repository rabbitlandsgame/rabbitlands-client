# The Barrow Run — change log

## 2026-09-08 — a family visitation road under the peat

Organised the route around the joined-barrows lore. Family cists, deep
offering shelves and low stone lintels mark the road through the Peat Cut,
First Barrow and Fifth Chamber. The Bog Board now stands on driven piles,
bearers and braced trestles over black water, with three lamp frames dividing
the span. The fork contrasts an intact carved passage with rooted, disturbed
tombs. A crown of split stones marks the Reeve's reward doorway.

Shorter connecting passages remove thirty-six metres of empty traversal;
the route footprint is 325 metres and arrival to vault is 311 metres.
The existing seven legs, timed crossing, fork choice, boss court, Moss node,
cache and waystones retain their roles. Open fight floors remain between
the burial furniture. A rear dais step completes the climb to the vault.

Added reusable barrowcraft recipes for dolmen frames, sealed or opened
cists, candle niches and supported plank walkways. The close-set boards
have a continuous substrate four centimetres below their tops, so a
grounding ray through a joint cannot fall to the water. Two regression
cases sample the deck at dense, incommensurate intervals and along its edges.
Existing material recipes and terrain surface classes are unchanged.

Manifest-lit review corrected candle banks facing their walls, moved candles
off displaced lids, enlarged the stone pattern on grave furniture, and
raised the final crown. The muted granite, wet timber, dead roots and warm
votives follow the Grey Moors concept board. Twenty eye-level, isometric
and detail captures were reviewed in Godot Compatibility with OpenGL 3.

The package grows from 26,610 to 60,291 triangles and from 5.00 to 8.62 MB.
Its 261 local material meshes keep the 53 point lights near the intended
surfaces. The explicit lids still use the gameplay cutaway contract.

Refreshed both published bands, the three collision copies, arrival constants,
gates, interactives, wave positions and the Moss node. An audit confirms
creature types, counts, variants, rules, rewards, keeper coordinates and
exterior returns are preserved, and unrelated routes are unchanged. A
second layout refresh writes no files.

Validation: 1,809 server tests and 546 subtests pass. The client suite has
196 passes and the same 88 known failures, with 9,296 passing subtests;
failure identities match the publish baseline. Every one of the 3,851
walkable server tiles has exported ground. Legal routes through both
branches reach the court and vault. glTF has no errors or warnings, and
the coplanar scan reports zero overlap. The runtime verifier has no errors
and one expected warning for the blocked void around the rooms.

GLB, manifest and both collision artifacts reproduce byte-for-byte in an
isolated build. All builds, captures and tests used affinity mask 15 and
at most four CPU cores. See references/comparison.jpg and
references/validation.json for the evidence.
