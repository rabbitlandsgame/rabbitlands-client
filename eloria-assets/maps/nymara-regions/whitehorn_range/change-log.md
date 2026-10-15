# Whitehorn Range change log

## From placeholder to production

The starting package was the `terrain-landmark-material-pass` placeholder, with
every defect listed in section 3 of the production guide. All were confirmed
present before any work started:

| Defect | Confirmed | Resolution |
| --- | --- | --- |
| Terrain flat | `Terrain_ELM_Authority` y = 0.0, extent only ±96 m | sculpted heightfield, -37.7 m to 180.1 m, full 576 m footprint |
| Landmarks belong to other regions | 12 of 20 meshes foreign: Grey Moor, Westhaven, Amethyst, Amberwood, Ssarathi, Mirrorhold, Sunmane, Manymouth, Orun, Crownwater | all discarded; nothing from the placeholder is preserved |
| No bounds, no coordinate transform | `bounds: null`, `coordinateTransform: null` | both written, arrival datum at server (174, 174) |
| Navigation prefix incomplete | `["Terrain_"]` only | `["Terrain_", "Walk_"]` |
| `source-elm` is a flat placeholder | 32 x 32 tiles, height 11 everywhere | regenerated at 96 x 96 tiles / 576 x 576 cells |
| Detail board truncated | 786,445 bytes, IDAT fails to decode | **not resolved** — see `validation-report.md` §4 |

## Build history

1. **Terrain pass.** Heightfield, built ground, alpine surface classification.
   Committed on its own once `validate_gltf` reported 0/0 and `verify_runtime`
   reported 0 errors and 0 grounding misses across all 331,776 tiles, as the
   guide requires before any detail work.

2. **Population.** Landmarks, crossings, satellites, roadside markers, seracs,
   vegetation, scatter, metadata markers.

3. **Corrections found by looking at the captures**, in the order they were
   caught. Each was a real defect that the validators did not and could not
   catch:

   - *The region rendered brown.* Rock was the default surface and snow a
     high-altitude band, producing a brown bowl with a white rim against a
     concept that is white almost everywhere. Snow became the base class and
     rock what breaks through on steep ground.
   - *The boundary became a brown apron.* Widening the rim to soften it pushed
     a 74 m continuously-sloped ramp into playable ground, and a continuous
     ramp is all slope, so all of it classified as rock. The rim narrowed and
     the scour threshold became altitude-dependent so high ground keeps snow.
   - *The lighting was Amberwood's.* `capture_views` hardcoded a warm autumn
     sun at saturation 1.30, which renders snow as sand. Regions can now
     declare `DAY_LIGHTING` / `GOLDEN_LIGHTING` overrides.
   - *The temple showed its back.* Kit pieces are built facing `-Z`; the temple
     was placed unrotated, so a player approaching from the south met the
     mountain mass behind it. Rotated a half turn.
   - *The temple floated.* Its backing mass was sized to the facade, and the
     shelf falls away behind it. The mass now runs 30 m below grade.
   - *The glowing portal was invisible.* The crystal sat 0.1 m behind the
     facade's front face. Pushed proud of it.
   - *The gorge had been filled in.* `grade_path` levels a road corridor to a
     smoothed profile, which bridged the 22 m chasm two routes cross. The gorge
     is now re-cut after the roads so it wins.
   - *The bridges sat at the bottom of the gorge.* A 26 m span sampled its
     "rims" from inside a 30 m cut, putting the deck 29 m below the road. Spans
     are now fixed constants measured from the cut.
   - *The pine was entirely bark-coloured.* `mesh.merge` collapses every part
     onto the first part's material. The conifer became a `MeshGroup`.
   - *Landmark markers sat under their own decks.* The temple and bridge
     markers recorded raw terrain height, which `verify_runtime` correctly
     reported as "landmark below surface". They now record deck height.
   - *The gorge floor disagreed with its collision encoding.* At -26 m it is
     past what the six-bit height field expresses. It is now explicitly
     unwalkable, which is also the correct design.
   - *Two empty group nodes.* The GLB emitted `Group_Ice` and `Group_Boundary`
     with no children, which the validator reported as `NODE_EMPTY` infos.
     Group nodes are now created on first use. Report went 2 infos → 0.

## Toolkit changes

Made in `_toolkit/`, additively, because the region genuinely needed
capabilities that were not there. Announced to the other four concurrent region
sessions before landing.

| Change | Why |
| --- | --- |
| `regionpaths.load_region_build()` / `load_region_module()` | shared module discovery, previously duplicated in `export_server_collision.py` |
| `capture_views.py` no longer imports `build_amberwood` and `amberwood.region` by name | it rendered Amberwood's terrain whichever package you pointed it at |
| `capture_views.py` sea-level guard | a region with no sea has no sea level to reject a camera against |
| `capture_views.py` `DAY_LIGHTING` / `GOLDEN_LIGHTING` hooks | the presets are tuned for an autumn forest; a snow region under them renders brown. Regions that declare neither are unaffected |
| `make_comparison.py` region-aware labels | sheets said "Amberwood build" for every region |
| `make_comparison.py` tolerates an undecodable board | nine of eleven region packages ship a truncated board; crashing on it loses the aerial sheet and the contact sheet too |

`export_server_collision.py`'s local `load_region_build` now delegates to
`regionpaths`, so there is one implementation. Amberwood was re-checked through
the new path and resolves to the same modules.

No existing toolkit behaviour was changed. Nothing was forked.

## Server change

`eloria-server`, branch `feature/whitehorn-range-576m-server-map`, following the
shape Amberwood and Mirrorhold used:

- `tools/generate_nymara_maps.py`: `MAP_TILES_WIDE_BY_NAME["whitehorn_range"] = 96`,
  `ARRIVAL_TILES["whitehorn_range"] = (174, 174)`
- `config/eloria/client_content_manifest.json`: register the map at 576 cells
- `config/eloria/maps.txt`: rescale all eight `whitehorn_range` portal endpoints
  from the 192-tile map to the 576-tile map (x3; 58 → 174)
- `tests/`: expected dimensions, arrivals and sizes in four test modules

431 passed / 80 failed, identical to the develop baseline with the change
stashed. None of the failures are caused by this work.

## Shared files touched

- `godot-client/data/maps/registry.json` — Whitehorn's entry only
- `eloria-assets/maps/nymara-regions/production-index.json` — Whitehorn's entry only

Both are expected to conflict with the other four region branches; resolve by
keeping both sides.

## After the intact detail board arrived

The board that shipped in the package was truncated and would not decode, so
the first panel sheet was a placeholder. An intact copy was found in the main
working tree and committed, and comparing against real concept art immediately
showed defects the wide-angle captures had hidden:

- **Panel cameras were 50–90 m back.** The board's panels are intimate; at that
  distance every subject was a speck in a snowfield. Moved to 7–25 m.
- **The ice cave was a plain pale ball.** One icosphere with a throat pushed
  into it: the mass swallowed the opening. Rebuilt as flanking shoulders and a
  brow with an actual void between them.
- **The frozen cascades were flat cardboard on open snow.** Rebuilt as many thin
  overlapping columns on a rock backing, with a frozen pool and ice rubble.
- **`timber_dark` is not dark.** Both the mine adit and the cave void read as
  tan boards across their openings. Both now use `dark_iron`.
- **The cascades faced away**, the same trap the temple hit — built facing -Z
  and placed unrotated on a valley approached from the south, so the rock
  backing sat between the camera and the ice.
- **Panel 3 was aimed into the gorge bed.** The deck sits ~44 m above the floor,
  so a target taken as "2 m above ground" pointed downward. Now shot in profile
  from the east.

## Corrections from the other region builds

Running four regions concurrently caught things no single session would have:

- **The rope bridges made their own ropes walkable.** `walk_surface=True` on a
  MeshGroup placement renames the container node, and every solid child then
  inherits the `Walk_` prefix. 13 walk-surface nodes where there should have
  been 2. Found by the Amethyst Barrens build hitting it on an observatory dome.
- **`environment.sun.direction` is the direction light travels.** A positive Y
  lights the world from underneath, and no offline preview can show it. Found
  by the Crownwater build. Whitehorn had no sun block at all and now declares
  one, with the sign verified in-engine.
- **`capture_views` imported Amberwood by name**, so it rendered Amberwood's
  terrain whichever package it was pointed at. Found here, fixed in the shared
  toolkit, and re-run by the other regions.

## Base

Rebased onto `origin/develop` after the Mirrorhold work and the Amberwood
regeneration landed there. The toolkit changes this region originally made were
dropped in favour of the equivalent ones already on develop, except the
`DAY_LIGHTING`/`GOLDEN_LIGHTING` hooks and the `--check-sun` mode, which are
this region's contributions to the shared harness.

## The glacier was blended

Reported from live play: whole slabs of the range showed a different surface
through them, with hard rectangular edges that moved as the camera turned.

`glacier_ice` was authored for Mirrorhold's frozen lake as a blended material
at 94% opacity, and this region's `SURFACE_MATERIALS` mapped the whole `TER.ICE`
class onto it. `Terrain_Ice` is a 140 x 436 m sheet folded 128 m down the gorge,
so the client - which renders through GL Compatibility, where an alpha-blended
surface writes no depth and where Godot's depth pre-pass mode falls back to
plain blending - drew it with no depth of its own and sorted the whole sheet as
one instance. Its far folds painted over its near ones, the seracs standing on
it washed out as the sorting flipped, and the shadow map skipped it entirely.

The material is now opaque, here and in Mirrorhold and both ice interiors. The
6% of translucency never showed: ice reads through its texture and its 0.30
roughness. `_toolkit/amberwood/materials.py` carries the change for any later
rebuild; the shipped GLBs were edited in place by
`eloria-assets/tools/make_glacier_ice_opaque.py`, which touches the material
entry in the JSON chunk and nothing else.

## Neither rope bridge could be crossed

Reported from live play, of the lower bridge: it did not work as a crossing.

Three things were wrong, and all three had to go for a player to get over the
gorge.

**The walk grid gave each deck a disc.** `build_collision` stamped an elevated
walk surface as a circle of radius `min(half_x, half_z) * 0.85` about the
placement, and ignored `rotation_y`. That shape is right for the temple's floor
and ruinous for a span: a 34 x 1.9 m deck became 1.6 m of walkable cells over
the middle of the chasm, 20 m from either bank and reachable from neither. The
footprint is the deck's own rectangle now, in the deck's own frame, grown half a
cell along its run so it meets the ground it lands on and held in half a cell
across its width so an actor on a deck cell is over planks.

**Both spans were too short, and landed inside the cut.** The span was the fixed
34 m of a `SPANS` table and the deck sat at the mean of the ground at its two
ends - ends which were themselves part-way down a 70-degree wall, 11 m below the
first ground a walker can stand on. `_crossings` measures out from the anchor
now to the first ground on each side gentle enough for the walk grid to accept,
and builds the deck to that width: 42 m here, 40 m upper. The shoulder test is
deliberately under `MAX_WALK_GRADIENT` rather than at it, because a landing on
ground already at the climb limit leaves a step the grid rejects, which is a
crossing one cell short of usable.

**A level deck could not meet both shoulders.** The gorge is cut across a
mountainside, so one side stands above the other almost everywhere along it -
8.7 m apart at the lower crossing. `kit.rope_bridge` takes a `rise`, the deck
running straight between its two ends under its own sag, and `build_collision`
follows that slope instead of putting the whole deck at one height. The lower
bridge climbs 10.6 m over 42 m to the north, the upper 6.2 m over 40 m; both
land within 0.2 m of the ground at each end.

While the ray was on the deck: the planks were spaced at 0.82 of their pitch,
leaving an 0.2 m gap between each pair, and the client grounds an actor with a
single ray straight down. A step landing in a gap went through the deck to the
gorge floor forty metres below - about every sixth pace. The planks overlap now.

Measured on the walk grid, bank to bank: 873 m round the end of the gorge
before, 49 m across the bridge after. The upper crossing goes 878 m to 50 m.
A ray cast every 0.1 m along both decks, through the client's own loader and
grounding layer, lands on the deck 832 times out of 832.

`build_whitehorn` also advertised the walk grid as EWCG v1 with a 0.2 m height
step while writing a v2 file with a 2.6 m one, so the manifest had to be
corrected by hand after every build. It reports what it writes now.

## The crossings now land on the road

The span still did not meet the brown of the pilgrim road at either end. The
landings were being looked for square across the cut, and the road does not
cross the cut square: it comes down from the south-west and leaves to the
north-east, so a span laid on the world axes lands beside the road at both ends
however long it is made.

`_road_landings` looks for the nearest ground on each side of the gorge that is
classed PATH or PAVING and that the walk grid will accept, and the span is laid
between those two points at whatever angle they ask for - 66 degrees at the
lower crossing, 46 m between landings both of them on `Terrain_Trail`. The
upper crossing keeps its square line: its approach is steep enough that
`assign_surfaces` calls it rock, so there is no brown there to aim at, and it
falls back to the shoulder search.

Two details that cost a rebuild each. A landing is judged on the walk grid's
half-metre lattice rather than the heightfield's two-metre one, because ground
that reads at 0.79 across two metres can be past the climb limit inside one
cell of it - which is how a landing was picked that the grid then refused. And
a deck reaches 1.5 m past its landings rather than stopping on them: stopping
exactly on the cell the search picked still left one cell of nothing between
the deck and the road, and one cell is enough to make a crossing useless.

Both decks now land within 0.08 m of the ground, on cells the grid marks
walkable, and 894 rays cast every 0.1 m along the two decks through the
client's own grounding layer all land on the deck.


## The ground is cut inside the cell, not at its corners

The roads read as a flight of steps two metres wide. `build_meshes` gave each
quad whole to the class of one corner, so a class edge could only ever run
along cell boundaries, and the heightfield is sampled every two metres while
the server walks the map on a one-metre grid.

Raising the heightfield to one metre was measured and rejected: it multiplies
terrain triangles by four (202k to 809k here), takes the package from 12.2 to
30.2 MB and the map load from 0.8 s to 2.4 s, moves every height sample - so
collision, grounding and every placed height with them - and still leaves a
staircase, only a finer one. Frame time, measured through the client at three
resolutions, does not change either way: the frame is spent submitting about
1,200 mesh nodes, not on terrain vertices or terrain pixels.

The ground is now cut inside the cell instead. A class takes every quad it
touches and carries a per-vertex coverage in COLOR_0's alpha - 1 where the
class holds, 0 where it does not - and draws with an alpha-tested copy of its
material, so each pixel goes to whichever class covers it. Where an operator
knows where its own edge is, `Terrain.surface_strength` records how far each
sample sits from it and the cut lands on the real edge: `grade_path` writes the
road's falloff, `plateau` its rim. Elsewhere the cut falls half way between two
samples, which still turns a corner staircase into a diagonal.

It is opaque - an alpha test writes depth and sorts like any other ground - so
none of the transparency trouble the glacier had applies. The classes overlap
by design where they meet, and `check_zfighting.py` now skips pairs that are
both alpha-tested with vertex coverage, because the test hands each pixel to
exactly one of them: the region's real coplanar overlap is 92.3 m2 across 30
pairs either way.

Costs 27,460 triangles (+11.6%) and 1.8 MB (+15%), with the vertex colours
packed as normalised bytes rather than floats - four bytes a vertex instead of
sixteen, which is finer than an alpha test can see. `collision.bin` is
byte-identical: heights and classes did not move, only the way they are drawn.

The client has to turn `vertex_color_use_as_albedo` on for these materials.
Godot's glTF importer brings the colours in and sets the alpha mode but leaves
that flag off, and without it the coverage never reaches the shader.

## September 2026 — provisioned gate and mountain circulation

The previous camps were crates on broad empty pads, and the mine road crossed
the gorge without a cart crossing. The gate now gathers services around
weather shelters; the mine has a worked bench and an eastern haul road.
Seventeen road/approach polylines, eight shelters, a visible Cascade Cave
entrance and the temple switchbacks give the journey deliberate stops.

The rope bridges now use fixed bank surveys and the shared mountaincraft
recipe. Continuous profiled plank skins remove overlapping plank boxes.
Temple pinnacles reinforce the destination silhouette, its brass inlay is
separated from the floor, and its return spawn stands on the podium. Secret
sites, NPC posts and wildlife/resource geography follow the intended routes.

The full server suite passes 1,767 tests. Client failures remain the same
86 as the rebased baseline, with 169 passing tests. All actual content is
reachable from arrival, counts are retained, runtime grounding has no misses,
and the four exterior package files reproduce byte-for-byte. Geometry cost,
remaining overlap warnings and reviewed captures are recorded in layout-review.md.
