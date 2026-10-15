# The Resin Road â€” change log

## 2026-09-08 â€” underground haul route

Replaced scattered wall stumps with working bays, using shared timber bents,
open resin vats, hand winches, carts and stacked logs. Packed-earth floors mark
the former working rooms. The fork now contrasts a wet collection hollow with
dry timber storage, and increasingly large roots frame the route to the Boar
King. Shorter gate passages remove 36 metres of empty traversal.

Added reusable forestcraft recipes, spatial render batches and coplanar face
clipping to the toolkit. The latter removes the old room-joint shimmer while
preserving navigation coverage and UVs. Corrected the bridge pit's overhead
ownership. Geometry grows from 26,014 to 31,293 triangles; the self-contained GLB
grows from 4.00 to 5.51 MB, including the existing packed-earth texture set.
Local material batches increase mesh count to 208 so interior lamps remain
local in the Compatibility renderer.

Fixed the shared capture harness to wait for the scene tree before creating
manifest lights, honour manifest lighting for sealed interiors, and use the
game's declared ceiling/wall cutaways. Eighteen final eye-level and isometric
captures were reviewed. The comparison uses the same corrected harness for both
the published original package and this revision.

Updated the client registry, three vendored server grids, arrival constants,
gate portals, interactives, bonus node, instance bounds and wave positions.
Existing creature types, counts, boss definitions, variants, rewards, keeper
coordinates and exterior return points are preserved. Other map packages and
their generated server content are unchanged.

Validation: 1,797 server tests and 546 subtests pass. Client: 191 pass, with the
same 88 pre-existing failures and 9,284 passing subtests as the integrated
develop baseline; failure identities were compared. Eleven focused geometry
and gauntlet tests pass. glTF reports zero errors and warnings, and the geometry
scan reports zero coplanar overlap. The runtime verifier reports zero errors
and one expected warning for the surrounding void; a separate exhaustive check
finds ground beneath all 3,900 walkable tiles. World GLB, world JSON, client
collision and exported server collision reproduce byte-for-byte in an isolated
second build. Validator report timestamps and absolute report paths are
diagnostic metadata.

See references/comparison.jpg, references/godot-captures/index.json and
references/validation.json for the evidence.

## 2026-09-08 — preserve small exported mesh panels

The Ice Stair review found that local material batching could retain a
two-dimensional inverse index array. Small parts were then counted as empty
during merge. Flattening that array restores 130 triangles in the Resin Road,
bringing it to 31,423 triangles and 5.54 MB. Client and server collision remain
byte-identical to the published layout, and its server content is unchanged.

Re-exported and reviewed all eighteen captures, refreshed the comparison and
validation evidence, and verified a second isolated build byte-for-byte.
The shared regression checks triangle preservation, while an independent
exported-ground test covers every walkable tile across all eight gauntlets.
Current suites: 1,802 server tests and 546 subtests pass; 192 client tests and
9,284 subtests pass with the same 88 known failures.
