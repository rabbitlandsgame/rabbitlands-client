# Four Gates map change log

## 1.0.0 — production GLB package

First authored production pass, replacing the `four-gates-city` graybox
(4,538 unique triangles of untextured primitives).

- New self-contained authoring pipeline under `eloria-assets/tools/four_gates/`:
  a core-only glTF 2.0 writer, an indexed mesh toolkit, procedural PBR material
  synthesis, modular kits, landmark assemblies, an analytic terrain field and a
  deterministic city layout.
- Sculpted terrain: flat civic plateau, battered cliff, continuous turquoise
  water ring, four causeway crossings, outer highland rim, alpine skyline and a
  northern massif carrying the sanctuary shelf. Terrain surfacing is driven by
  height **and slope**, so steep ground reads as rock everywhere.
- 29 original tileable PBR material sets (base colour, tangent normal, packed
  ORM; emissive for the sapphire crystal).
- Landmarks: five twin-drum gatehouses with animated portcullises, 40 curtain
  wall bays and 8 drum towers, four arched bridges, the plaza mandala and
  crystal-crowned monument, four arcaded porticos, and the northern sanctuary
  with a ceremonial stair, glowing portal and beacon.
- 346 district buildings across four kits with authored variation, plus market
  squares, farm plots, docks, cranes, street furniture and ~850 planted trees.
- Manifest-driven environment (sky, sun, ambient, fog, tonemap, water) applied
  by a new `WorldEnvironmentApplier`, so the map ships with its art direction.
- Collision proxies inset inside their parent geometry (never visible), a
  navigation surface prefix contract, and 28 convex navigation polygons.
- Khronos glTF-Validator: **0 errors, 0 warnings**.

## 1.0.1 — face winding correction

Reported after merge: some building walls did not read as solid.

**Cause.** Almost every primitive in `meshlib.py` listed its quad corners
clockwise as seen from outside. glTF front faces are counter-clockwise and
Godot culls back faces, so those surfaces rendered inside-out: the outward face
was culled and the viewer looked through the near wall at the interior of the
far one. `explode()` derives normals from the winding, so the authored NORMAL
attribute pointed inward too and agreed with the bad winding — which is why
lighting looked merely *dark* rather than obviously broken, and why the defect
survived the earlier visual review. Silhouettes were unaffected; only depth
ordering and shading were, so it read as an art problem at a distance and as
see-through walls up close.

**Fix.** `_quad_indices` now emits outward-CCW triangles; `arch_ring`,
`ring_band`, `quad_strip` and `torus_arc` had their corner order reversed to
match; the explicit triangle lists in `pyramid`, `gable_roof` and `hip_roof`
were flipped; and the end caps of `cylinder` and `prism` were corrected
independently of their sides.

**Guard.** `eloria-assets/tools/four_gates/test_geometry.py` asserts the
invariant directly — positive signed volume for every closed primitive, no
inward-facing faces on convex ones, +Y normals on every ground surface, and no
authored normal pointing into the opposite hemisphere from its winding. It
fails loudly on any regression.

Side effect: the authored collision proxies now block all four movement probes
in the gameplay test rather than three; a trimesh built from an inside-out mesh
was missing rays from one direction.

### Defects found and fixed during the initial pass

These were caught by the validator, the independent viewer and the client:

- glTF index accessors declared a third of their true element count, so only
  one triangle in three would have been drawn by any conformant loader.
- Flat-shaded normals were computed against stale indices after vertex
  duplication, giving null normals on hard-surface geometry.
- Ground, ring, strip and polar surfaces were wound clockwise, so every terrain
  and road surface faced downward.
- Bridge arches sprang above the deck and occluded the whole crossing.
- The bridge deck slab and its fascia were exactly coincident, producing
  z-fighting bands across the causeway.

## Interiors — six street-level rooms

Six interiors now open off the Four Gates streets, each shipped as an ordinary
world package (`world.glb` + `world.json`) under `eloria-assets/maps/`:

| Package | Room | Quarter |
| --- | --- | --- |
| `four-gates-lantern-row` | Lantern Row — covered market hall | agricultural |
| `four-gates-stormglass-house` | The Stormglass House — glazier and alchemist | service |
| `four-gates-mirrorsmith-forge` | Mirrorsmith's Forge — repair and reforge | service |
| `four-gates-reedworks` | The Reedworks — reed and cordage works | industrial |
| `four-gates-ferrymans-rest` | The Ferryman's Rest — tavern | harbour |
| `four-gates-deposit-four-keys` | The Deposit of Four Keys — storage vault | civic |

They are authored by `eloria-assets/tools/four_gates/build_interiors.py` from
the interior kit in `interiors.py`, with every door position taken from
`interior_index.py` so the city shopfronts and the interiors' exit portals can
never drift apart. Each embeds a ten-to-twelve material subset at interior
resolution rather than the city's full thirty, which is why a room is under
3.2 MB against the city's 23.5 MB.

Nothing about the wire protocol changed. A door is a `CHANGE_MAP` to another
map id exactly like any other map change; the server stays authoritative over
where the player is.

### The interior camera

The isometric rig is framed for open ground: 26 m back at −60°. Indoors that
puts the camera above the roof and behind the near wall, and the player sees a
ceiling and nothing else. Two changes fix it, and both are manifest-driven so
the city is untouched:

- **`camera` block** — an interior declares its own framing (pitch −48°,
  distance scaled to the room's long axis, tighter zoom limits).
  `WorldEnvironmentApplier.apply_camera()` applies it on load.
- **`cutaway` block** — names the roof nodes to hide outright and the four wall
  nodes with their outward normals. `InteriorCutaway` hides the roof, and hides
  any wall whose outward normal points back towards the camera, following the
  rig as it rotates. Only visibility changes: the static bodies the loader
  builds from those meshes stay in place, so a cut-away wall is still solid.

The room shell is therefore emitted as six nodes (`Shell_Ceiling`,
`Shell_Beams`, and one per wall) rather than one fused mesh, which is what
makes the cutaway addressable at all.

### Verified

- Khronos glTF-Validator 2.0.0-dev.3.10: **0 errors, 0 warnings** on all six.
- `tests/integration/rendered_interiors.gd` — 66 checks, 0 failures. Each room
  is rendered twice: once from inside, and once at its own camera profile with
  the cutaway applied, asserting the roof is hidden, the near wall is hidden,
  the far wall is still drawn, and all four walls keep their collision.
- `tests/integration/rendered_map_transition.gd` — 16 checks, 0 failures.
  City → interior → city through an authoritative `CHANGE_MAP`, with grounding
  confirmed at both ends. This closes the "portals and map transitions
  unverified" gap flagged in the original validation report.
- `tests/integration/rendered_four_gates_gameplay.gd` — 28 checks, 0 failures,
  confirming the city is unaffected by the client changes.

## 1.0.2 — plaza grounding and coplanar paving

Reported from a client screenshot of the plaza: the benches float, and the
paving is shot through with shimmering stripes.

**Cause — floating dressing.** `build_plaza()` hung every prop off a literal
`PLATEAU_Y + 0.96` (benches off `PLATEAU_Y + 1.42`), a datum that matches no
surface in the map. The paving apron sits at `PLATEAU_Y + 0.06` and the raised
inner terrace at `PLATEAU_Y + 0.48`, so the whole plaza set stood in the air:
benches by 0.94 m, planters by 0.96 m, statues and lamps by 0.90 m, fountains
by 0.48 m, and the monument by 0.42 m. Every other prop in the city is placed
with `self.ground()` and was unaffected, which is why only the plaza showed it.

**Cause — striped paving.** Two independent sets of exactly coplanar faces.
`plaza_disc()` built its two steps as full-radius cylinders that kept their top
caps, then laid an overlapping inner disc over each, putting up to four
identical surfaces at the same height across the middle of the plaza. Separately
`build_roads()` authored the plaza disc, the three ring roads, the four
ceremonial avenues and the four diagonal streets all at one height, and the
avenues ran from `r = 0`, so they paved over the mandala and over each other at
the centre. A sampled sweep of the walking surfaces found 443 coplanar hits in
900 probes; the depth test then picked a winner per pixel and the plaza
shimmered.

**Fix.**

- `plaza_disc()` is now one apron annulus, one capless riser and three abutting
  terrace annuli (the middle one in `stone_trim`, so the step ring still reads).
  No two paving faces share a plane. The profile is unchanged — apron at the
  plateau datum, terrace 0.42 m above it — so nothing else moves.
- `build_roads()` gives each carriageway class its own datum: radials and
  diagonals 3 cm under the apron, ring roads 3 cm over them. The avenues now
  start at `PLAZA_RADIUS - 4`, so the mandala covers their inner ends without a
  gap and the four of them no longer overlap at the centre.
- `WorldBuild.plaza_surface(x, z)` returns the real top of the paving — terrace,
  apron or `ground()` beyond the disc — and the monument, fountains, statues,
  benches, planters and lamps all stand on it.

### Verified

- Coplanar sweep over the walking surfaces: **443 → 0** overlapping hits in the
  same 900 probes.
- Prop grounding audit (mesh base against the highest surface beneath it):
  benches, fountains, statues and lamps all at **0.00 m**; the four planters
  that sit on an avenue are 3 cm into the paving, the same convention as every
  `ground()`-placed prop.
- `collision.bin` is byte-identical to 1.0.1 — the walk grid is derived from the
  terrain field, so none of this touches collision or `walkingHeight`.
- 5,376 fewer unique triangles (189,551 → 184,175); the duplicates were the
  hidden mandala surfaces.

## 1.0.3 — coplanar surfaces across the map

Reported from a client screenshot: textures on the models flicker, most visibly
around the gates.

**Cause — collision proxies were drawn.** `collider()` builds a low-poly box
inside each of the 428 buildings and landmarks it stands for, and the manifest's
note claimed those boxes were "fully enclosed and never visible". They are
inset by 5 to 10 mm, which is not a clearance the depth buffer can resolve at
the distance a district is seen from, and `COLLISION_Sanctuary_Body` is flush
with the sanctuary's own wall. Every large townhouse in the city therefore drew
two same-facing walls in the same plane. A proxy is a physics volume, not a
surface: the manifest now says so with `collision.nodesAreProxies`, and the
client hides the nodes while keeping the shapes built from them.

**Cause — surfaces sharing a datum.** Six independent cases, all the same
mistake in different kits:

- Every townhouse ran its wall to the top of its own cornice, so the wall head
  and the cornice cap were one plane on all 346 district buildings. The wall now
  stops at the cornice soffit, which is where a cornice actually sits.
- The four plaza porticos stood at `PLATEAU_Y`, putting their stylobate exactly
  on the ground under it; they now sit on the `PLAZA_LIFT` paving datum, like
  the paving and the carriageways.
- The sanctuary's paved terrace met its authored shelf to 2.6 mm; it moves onto
  the same paving datum.
- Bridge decks ran out onto causeway ground authored at exactly `CAUSEWAY_Y`.
  They now carry `BRIDGE_LIFT` clear of it.
- Each bridge's cutwaters sprang off the pier crown with their base caps facing
  up out of it, and the spandrels either side of a pier were sized to overlap.
  The noses spring from inside the soffit and the spandrels stop short.
- Curtain-wall bays cut their band and parapet to the bay length exactly, so
  three end caps shared the joint plane; both now run past it.
- Farm plots were sized 22-34 m radially in an 18 m ring step and cached in six
  slots shared by forty plots of different sizes, so most fields were handed a
  plane too big for their cell and ran over their neighbours. Each is now a
  fraction of its own cell and the cache is keyed on the size it holds.

### Verified

- `eloria-assets/tools/check_zfighting.py` (new) measures the real overlap area
  between coplanar same-facing surfaces, clipping every candidate pair in-plane
  so adjacent terrain triangles are not counted, and skipping whatever the
  manifest declares hidden. Four Gates: **82,424 → 1,584 m²**, a 98% reduction,
  with nothing left above 180 m².
- Client-side, `main.tscn`'s camera near plane moves from the engine default
  0.05 m to 1.0 m. The client renders through GL Compatibility, whose depth
  buffer is fixed point, so the resolvable step at distance z is about
  `z^2 / (near * 2^24)`: 12 mm at 100 m before, 0.6 mm after. The isometric rig
  never brings the camera nearer than 8 m to its focus, so nothing is clipped.
- 414 more unique triangles (184,175 -> 184,589): the farm-plot cache now holds
  a plane per field size instead of six shared ones. `collision.bin` is
  byte-identical, so none of this touches the walk grid or `walkingHeight`.
- Khronos-shaped validator: 0 errors, 0 warnings.

## 1.0.4 — the outer ring's surface classes

Reported from the client's top-down map: the outer rocky band between the water
and the map's edge reads as a jagged, speckled interleave rather than an edge,
and looks like z-fighting.

**It is not z-fighting.** Every pixel out there is drawn once. The terrain is one
mesh split into five sub-meshes by surface class, and the split is a strict
partition: 48,832 + 18,310 + 23,028 + 6,556 + 2,154 = 98,880 triangles, which is
the whole mesh and no triangle twice. Painting every drawn surface a flat colour
keyed on its mesh and shooting the rim orthographically from above returns one
unbroken colour under the trees — no second surface is competing for those
pixels — and `check_zfighting.py` reports nothing in the ring at all. Squeezing
the map camera's depth range from 0.05–2500 m to 100–700 m, which is a fourfold
gain in depth resolution, moves seven pixels in a 1024² frame.

**Cause — one class per triangle instead of one per quad.** `polar_surface`
asked `material_fn` once per *triangle*. A quad's two triangles are two
different planes and their centroids sit a radial step apart, so wherever the
ground hovers near a class threshold the two halves of one quad came back in
different classes and the boundary ran along the quad's own diagonal. On the
plateau that happened to 1% of quads; on the outer rim, where the slope sits
either side of the rock cut-off for two hundred metres, it happened to **9%**,
and since a polar quad out there is 4.5 m radially by 12.8 m around, each tooth
is a long thin sliver. Seen from 448 m up at 2.2 m per pixel, several thousand
of those slivers is the "dithered mess".

**Fix.** `meshlib.polar_surface` decides the class once per quad, from the
quad's centre and its own normal, and hands both triangles that class. A patch
of ground belongs to one surface class; how the mesh happened to cut it into
triangles is not the ground's business. This is the Four Gates counterpart of
the rule the region toolkit already carries — *splitting one field into
sub-meshes selects quads, not vertices*.

### Verified

- Rock/grass/sand boundaries in the rim read as coherent bands in the packaged
  minimap render and in a 3072² shot of the in-game full-map framing; the long
  interleaved slivers are gone. Ground-level views are visually unchanged.
- 98,880 terrain triangles before and after, and the same 184,589 unique
  triangles map-wide: no geometry moved, only which sub-mesh owns it. The class
  mix shifts by under 4% (rock 18,310 → 19,004 triangles).
- `collision.bin` is byte-identical, so the walk grid and `walkingHeight` are
  untouched. `check_zfighting.py`: 1,584.2 m² across 83 pairs, unchanged.
- 37 KB smaller (23,545,448 → 23,508,048 bytes): fewer vertices duplicated at
  class seams.
- `rendered_four_gates_map.gd`, `rendered_four_gates_views.gd`,
  `test_world_lighting.gd` and `test_occluder_fade.gd` all pass.

## 1.0.5 — the packaged minimap catches up

`minimap.webp` had drifted from the geometry it claims to be derived from. It
was stale before 1.0.4 and 1.0.4 moved the ground under it again, so the
packaged cartography showed a rim that no longer existed.

It is regenerated from `rendered_four_gates_minimap.gd`, which is the fixture
written for exactly this — an orthographic top-down shot of the shipped
`world.glb`, 1024², north up, centred on the mesh, "so the cartography can never
drift". Re-encoded at WebP quality 92, which lands at 261 KB against the old
303 KB.

A note for anyone comparing the two: WebP at this quality moves fine dithered
ground by up to 95 per channel on its own, so a large maximum per-pixel
difference against a fresh render is not by itself evidence that the image came
from different geometry.

The manifest's `minimap.pixelsPerMetre` is computed from `WORLD_EDGE * 2`
(1584 m) while the render frames the mesh's own bounds (1620 m), so the declared
scale is 2.3% out. Nothing reads it — the client loads the image and renders its
live minimap from the GLB — so it is recorded here rather than changed.

### Also in this build

`meshlib.grid_surface` carried the same per-triangle classification bug that
1.0.4 fixed in `polar_surface`, latent because no caller passes it a
`material_fn`. It now decides the class per quad as well, and
`test_geometry.py` grew a check that fails on the old behaviour for both
surfaces: it pairs triangles across their shared edge, tells a quad's diagonal
from a grid line geometrically rather than by face order, and counts quads whose
two halves disagree. Against the per-triangle rule that count is 9 for
`grid_surface` and 40 for `polar_surface`; it is 0 for both now. No geometry
changed — `world.glb` is untouched by this entry.

## 1.0.6 — one pixel to the metre

Four families of map had grown four answers to "how big is a metre on the
minimap": the ten Nymara regions at 1.336 px/m, Four Gates at 0.646 (declared;
0.632 as actually rendered), the Sunmane steppe at 3.657, and the two Sunmane
cave interiors at 8.533. They also described it three different ways —
`pixelsPerMetre` against `metresPerPixel`, `size` against `pixels` against
`imageSize`, `image` against `file` — so no two could be compared without a
conversion first.

Every minimap is now drawn at **one pixel to the metre**. That makes the image's
pixel dimensions the map's own size in metres, and it makes the two rival
spellings of the scale numerically identical: at 1.0, `metresPerPixel` and
`pixelsPerMetre` are the same number, so the old keys stay beside the new ones
for one release without ever disagreeing with them.

Four Gates goes 1024 → 1620 px. It is the only map whose image had to grow, so
it was re-rendered rather than upscaled: `rendered_four_gates_minimap.gd` now
sizes its viewport from the geometry instead of a fixed 1024 square, which is
also what removes the 2.3% error between the declared scale and the image — the
manifest said 1584 m for a picture covering 1620 m.

The remaining thirteen were resampled down, and every generator was changed to
keep the standard on the next rebuild: the ten region build scripts, the Four
Gates manifest builder (which now takes the square from the mesh bounds it
already writes, rather than from `WORLD_EDGE`), and the two Sunmane manifest
builders.

`eloria-assets/tools/unify_minimap_scale.py` applies and re-checks the standard,
and is idempotent — a second run reports every map already at 1.0000 and
rewrites nothing.

**Known consequence:** at this scale the two Sunmane cave interiors, which are
60 m across, become 60 × 60 px images. They are legible as a shape and not much
else. Nothing reads them today beyond the invasion assistant's map picker, and
exempting interiors is a one-value change in the tool if a cave map is ever
wanted at a useful size.

## 1.0.7 — one tile to the metre

Four Gates was the last Nymara map that did not answer the server at one metre
per tile. The regions are 96 map tiles across a 576 m landform, and 96 × 6
collision tiles divides 576 m exactly; Four Gates was authored 256 map tiles —
1536 walk tiles — across a 714.4 m island, so a walk tile was 0.465 m and this
manifest had to carry `metresPerTile: 0.4651162791` to talk to it. That single
number was the only reason the client needed a per-map conversion at all.

The island was not stretched to fit its tile grid, which would have made it 2.15
times larger against a character that stayed the same height, and would have
made every server step cover 2.15× more ground than the walk cycle is authored
for. The tile grid was shrunk to fit the island instead: **120 map tiles, 720
walk tiles, `metresPerTile: 1.0`, `serverOrigin: [360, 360]`**.

Every stored Four Gates coordinate moved with it, on both sides:

    new = round((old - 768) × 0.4651162791) + 360

which is the identity at the island's centre. The server's fifty NPC, spawn,
harvest-node, portal and interactive coordinates were migrated with
`tools/retile_four_gates.py`, its arrival, respawn and walkthrough anchors with
them, and standing characters move with the grid through a new
`four_gates_grid_720` database migration — the same shape as the
`four_gates_grid_1536` migration that re-gridded this map once before.

Checked afterwards: all fifty migrated coordinates describe the same spot on the
island as before, the worst drift being 0.61 m, which is the rounding to a
coarser grid and nothing else. The server suite fails exactly the 83 tests it
fails on a clean `develop` — no new failures.

The addressable band is 720 m against an authored playable span of 714.4 m, so
it overhangs by 2.8 m on each side; that band is the scenery ring the collision
grid already refuses.

**Not included:** the six Four Gates interiors still carry `metresPerTile: 0.25`.
They are registered in the client but no server serves them yet, so there is no
tile grid to migrate them onto — re-tiling them would mean inventing one.

## 1.0.8 — the roads' paving

Reported from the client: the street and avenue surfaces shade dark to light
and back over and over down their length, which reads as banding rather than as
stone.

**Cause.** Two defects in the two paving materials in `texturing.py`, both of
them in how the Worley cell field was read.

The stone tone came from `(cell % 53) / 52`, meant as a per-flagstone hash.
`worley` numbers its cells in raster order, and the street field has 7×7 = 49 of
them, so the modulo is a no-op and the "hash" is the cell's row: the tile ramps
smoothly from dark at one edge to light at the other. The avenue's 9×9 = 81
cells wrap the divisor exactly once, giving a ramp and one hard step. The street
tile spans 6.5 m, so that gradient repeated every 6.5 m of carriageway — a 1.6×
swing in brightness, tile after tile, which is the banding as seen.

The mortar came from `1 - dist × 11` on the *nearest* distance. That distance is
zero at the cell's seed and largest at its rim, so thresholding it darkened a
disc in the middle of every flagstone and left the seams between them bright:
each stone carried a soft round shadow at its centre instead of a joint around
its edge, over 31% of the street's area.

**Fix.** `worley` now returns the second-nearest distance alongside the first,
which is the form the other region toolkits already use (`order=1`). The gap
between the two falls to zero along the seam between neighbouring cells, so the
joint is cut from that instead and runs where mortar belongs. A `cell_hash`
helper scatters cell ids over [0, 1) so neighbouring stones are uncorrelated,
and the roads shade from it, tightened to 55% of its range so stones differ
without checkerboarding.

Tile-scale brightness drift across the street tile falls from 0.233 to 0.049 —
what is left is the weathering noise, not a ramp — and the joints cover 9% of
the surface as lines along the cell edges.

The remaining 29 materials draw from the same generator in the same order and
are **bit-identical** before and after; only `paving_road` and
`paving_ceremonial` change. The rebuilt `world.glb` differs from its predecessor
in exactly those six texture images: all 2,919 geometry and animation buffers,
and the glTF structure, are unchanged, so the manifest and the walk grid are
untouched.

**Not included:** the six interiors floor their rooms with `paving_road` and
still carry the old synthesis. Rebuilding them is a separate package pass.

## 1.0.9 — the rest of the Worley surfaces, and 1.0.8's missing joints

**1.0.8 landed only half of itself.** `worley` returns `(nearest, second
nearest, cell id)`, and the two paving materials bound the second distance to a
name of `gap` and then thresholded it directly, without subtracting the first.
The intended mask needs the *difference*: F2 alone runs from about half the seed
spacing at a cell edge to a full spacing at its centre and never approaches
zero, so `1 - F2 x 80` clipped to zero across the whole tile. The streets and
avenues shipped with no mortar at all — no groove in the height field, no
occlusion in the seams. What did land was the tone hash, which is what removed
the banding, so the defect the fix was reported against was genuinely gone and
this went unnoticed. Both now read `1 - (far - near) x K`, and the joints cover
10.8% of the street tile and 12.0% of the avenue.

Two more materials carried the 1.0.8 defects. They were found by measuring
every material in the library rather than by eye: a raster-ramp correlation
against a 400-sample random null on the same cell grid, and the spread of
neighbouring cell values against the same null.

**`stone_rubble`** — the base course under nearly every building in the city,
so it sits at eye level along every street. It had both defects. Its tone came
from `(cell % 71) / 70` over 81 Worley cells, which wraps the divisor once and
so ramps and then steps (ramp r = 0.477 against a null 95th percentile of
0.169; neighbour spread z = +3.8). Its `cracks` came from the nearest distance
and covered 64% of the tile as hollows in the middle of each block rather than
seams between them. Tile-scale tone drift falls from 0.190 to 0.122.

**`roof_slate`** — a different failure of the same kind. `brick_mask` numbers
its bricks `(row * 977 + col * 131) % 9973`, and reducing that modulo 61 again
leaves a lattice: the slates correlated along diagonals into chevrons a roof
wide, repeating every 2.4 m. The row-ramp test does not see it because the
correlation is diagonal, not vertical; the neighbour-spread test does
(z = +2.6). Hashing the brick id scatters them, and drift falls from 0.135 to
0.021.

Cleared by the same measurements, and deliberately left alone: `stone_ashlar`
(z = -0.4) and `roof_tile` (z = +1.6, inside the null) hash acceptably;
`cloth_banner` has the library's largest tone drift, 0.236, because that is the
authored crest; and `foliage_flowers` thresholds the nearest distance on
purpose, since a bloom *should* be a blob at the seed.

**Not included:** `terrain_rock` and `crystal_blue` still cut an edge mask from
the nearest distance (33% and 41% coverage). Their tone hashes measure clean and
neither bands, so the symptom is missing detail — cliffs get soft discs instead
of cracks, crystals glow at the centre rather than the facet edges — on
surfaces tiled at 17 m and 1.2 m. Worth a pass, but not this one.

27 of the 31 materials are bit-identical across this change, and the rebuilt
`world.glb` differs only in the twelve texture images of the four that moved;
all 2,919 geometry and animation buffers and the glTF structure are unchanged.

## 1.0.10 — the last two edge masks, and the interiors catch up

Closes out the Worley audit begun in 1.0.9.

**`terrain_rock`** and **`crystal_blue`** were the two materials left cutting an
edge mask from the nearest distance. Neither banded — their tone hashes measure
inside the random null — so the symptom was absent detail rather than an
artefact: the cliff's `crack` darkened a disc in the middle of each block
instead of a fissure between them, and the beacon crystal's `edges` lit a blob
at the centre of every facet instead of a vein along its seams. Both now read
`1 - (far - near) * K`, at 17.3% coverage for the rock and 9.9% for the crystal.
Their tone hashes are left alone: `(cell_id % 37) / 36` measures clean
(z = +1.0), though it is clean by luck rather than by construction, and would
want `cell_hash` if the cell count ever moved.

**Deliberately not changed: `stone_rubble`'s remaining tone drift.** At 0.122 it
is still the largest in the library after `cloth_banner`'s authored crest, and
all of it is the material's own `fbm(S, 6, 6)` layer rather than a defect.
Measured against the heights the material is actually used at — plinths,
podiums and chimney stacks, against a 4.5 m tile — the drift resolves to a tone
difference *between* objects of 0.060 for a 0.6 m plinth, 0.036 at 1.6 m and
0.000 across a full tile. That is variation from one building's base course to
the next, which is what rubble should do, not banding within one. Flattening it
would need either a fresh draw from the generator, which would perturb every
material after it, or a high-pass that rewrites the material's character.

Rebuilt `world.glb` differs from its predecessor in the five texture images of
those two materials; geometry, animation and glTF structure are unchanged.

## Interiors — floors catch up with the street

The six interiors floor their rooms with `paving_road` and had not been rebuilt
since 1.0.7, so they still carried the pre-1.0.8 synthesis: the raster tone
ramp, the hollow in the middle of every flagstone, and no mortar at all. A room
opened onto a street whose paving no longer matched it. All six are rebuilt
against the current library.

Of the 41 texture maps in each package, 36 come back **pixel-identical**; the
five that move are `paving_road`'s three and `crystal_blue`'s base colour and
emissive. The GLB bytes nonetheless change throughout, because the PNGs are
re-encoded by a newer zlib than the checked-in files were written with — which
is also why every material's compressed payload differs while its pixels do not.

Geometry is unchanged and was checked rather than assumed: vertex POSITION and
NORMAL deltas are exactly zero and the index buffers are identical. TANGENT and
TEXCOORD_0 differ by at most 4.8e-7, and one quaternion component by one ULP,
which is float32 rounding from a different numpy build and not a change in the
authored scene. Each `world.json` moves by one line, the recorded GLB byte size.
