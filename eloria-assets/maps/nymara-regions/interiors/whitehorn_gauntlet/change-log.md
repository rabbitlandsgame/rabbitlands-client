# The Ice Stair — change log

## 2026-09-08 — silver mine inside the glacier

Turned the plain rooms into a worked mining route with silver faces, ore
sledges, winches, timber bracing and frozen falls. The bridge now carries a
gently sagging plank deck and lamps hung clear of their posts. Glacier ice and
a snowy timber adit distinguish the fork, while paired frozen wings give the
Rime Court its silhouette. A rear dais step keeps the reward doorway reachable.
Shorter gate passages remove 36 metres of empty traversal.

Added parameterised frozen-cascade and ore-face recipes to mountaincraft,
reusing the existing palette. The export grows from 24,678 to 43,464 triangles
and from 4.43 to 5.65 MB. Its 223 local material meshes let the Compatibility
renderer select nearby point lights. Coplanar joint clipping removes shimmer;
overhead room shells remain separate for gameplay cutaways.

Visual review exposed an index-shape bug in spatial material batching: NumPy's
inverse array retained the triangle shape, causing small parts to be counted
as empty during merge. Flattening the index stream restores the bridge deck
and small panels. A regression checks triangle preservation and one-dimensional
indices, and an independent test now ray-checks every walkable tile against
the exported GLBs for all eight gauntlets. The Resin Road was re-exported
with this shared fix; its collision and server content are unchanged.

Added a server layout refresh that updates coordinates from the manifest while
preserving the published encounters, rules, rewards, keeper and exterior return
points. Refreshed both bands, three grids, gates, interactives, arrival constants
and the client registry. The refresh is idempotent, and unrelated routes are
unchanged.

Validation: 1,802 server tests and 546 subtests pass. Client: 192 pass, with the
same 88 pre-existing failures and 9,284 passing subtests as the integrated
baseline; failure identities were compared. glTF reports zero errors and
warnings; the geometry scan reports zero coplanar overlap. Runtime checks
report zero errors and one expected warning for the surrounding void. All
4,007 walkable tiles have exported ground. GLB, manifest and both collision
artifacts reproduce byte-for-byte in an isolated build.

Eighteen final eye-level and isometric captures were reviewed in Godot's
Compatibility renderer with the manifest environment. The comparison uses
the same capture harness for the original and revised package. Builds,
captures and tests were limited to CPU affinity mask 15 (four cores).
See references/comparison.jpg and references/validation.json.
