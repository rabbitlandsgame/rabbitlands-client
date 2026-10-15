# Mirrorhold change log

## Production pass — 576 m region

Branch: `feature/mirrorhold-production-glb-map` (client),
`feature/mirrorhold-576m-server-map` (server).

### Replaced

The whole package. The previous one was the shared placeholder generator's
output and carried the defects section 3 of the region production guide lists,
all of which were confirmed here before anything was built:

- **The terrain was flat.** `Terrain_ELM_Authority` was y = 0.0 everywhere over
  a ±96 m extent, and `production-index.json` recorded
  `terrainHeightRange: [0.0, 0.0]`.
- **Twelve of nineteen landmark names belonged to other regions**: Amberwood
  Hollow Tree, Grey Moor Ritual Shrine, Manymouth Tidal Waystone, Ssarathi Ruin
  Arch, Sunmane Burial Mound, Sunmane Caravan Camp, Verdant Water Shrine,
  Westhaven Harbor Crane, Westhaven Lighthouse, Westhaven Sea Cave, Whitehorn
  Glacier. Only seven of the fifty-four instances were Mirrorhold's own. None
  of it was preserved.
- **`server-collision/mirrorhold.bin` was a 32x32 flat placeholder** at height 11.
- **`references/00-concept-detail-board.png` is truncated** to 786,446 bytes;
  only its top row of five panels decodes. Still true in this commit — see
  `validation-report.md`.
- The `textures/` directory of loose region maps is gone; the package embeds
  its textures in the GLB.

### Added

- 576 m x 576 m terrain: a mountain massif rising north, two glacier cirques,
  a lake basin in the south, stamped civic terraces, four graded roads and
  three watercourses. Relief 0 to about 195 m.
- The citadel: orrery and armillary, high and great courts, gate wall and
  wings, rose gallery, two lens towers, mirror basins.
- The civic descent: fountain plaza, canal terraces, aqueduct, north overlook,
  the stair town in five shelves, the east stair, retaining walls along the
  switchbacks, eight cliff waterfalls.
- The lake: the ring and four causeways, the north quay with three docks and
  boats, two islets, the south watch.
- Eighteen satellite sites, an alpine spruce belt, and road, harbour and
  terrace dressing.
- 31 landmarks, 8 interactives, 18 NPC and creature markers, 38 harvestables,
  6 portals, 3 spawns.
- `source/` in full, and a regenerated 96x96 `server-collision/mirrorhold.bin`.

### Shared toolkit

Changes made in `../_toolkit/` for this region, all additive:

- `noise.stable_hash()` and its five call sites — the build was not
  deterministic, because seeds were derived from Python's salted `hash()`.
- `preview.py`'s texture cache keyed on a digest of the recipe sources, and
  moved off a hardcoded `/tmp` that Windows resolves to `C:\tmp`. Before this,
  a stale cache silently shipped textures that no longer matched the source.
- `regionbuild.py`: `Placement` and `RegionBuild` moved out of
  `amberwood/region.py` and re-exported.
- `regionpaths.py`: region package, plan, build-module and views resolution, so
  the relocated scripts stop assuming they live inside one region.
- `terrain.build_meshes(materials=...)`: per-region surface-class materials.
- Terrain surface classes `SNOW=7`, `ICE=8`, `MARBLE=9`, `TURF=10`, appended.
- Texture recipes: `snow_pack`, `glacier_ice`, `blue_crystal`,
  `veined_marble`, `pale_ashlar`, `gilt_brass`, `slate_roof`, `alpine_turf`,
  a `lake` tone for `water_surface`, and a `mirror_glass` material.
- `terrain.backdrop(open_side=, clip_interior=)`: the mask could never exclude
  the interior, because the distance it tested is clamped at zero. Harmless on
  a map whose border is lower than its middle, which is why Amberwood never
  showed it; on Mirrorhold the coarse backdrop sheet poked up through the
  slopes as scattered white patches. The old behaviour is still the default.
- `godot_capture.gd`: renders a package's camera set through Godot itself.
- Material sets are now pinned per region, so a recipe added for one region
  cannot change another region's GLB.

### Known defects fixed during the pass

- `Placement.walk_surface=True` on a `MeshGroup` prefixed every part of the
  group with `Walk_`, making roofs and domes walk surfaces. Walk-surface nodes
  dropped from 81 to 28 when corrected.
- The gate wall and the rose gallery were placed inside the citadel court's
  footprint.
- The snow line at 104 m put snow across the civic terraces.
- The orrery's dome hid the armillary it was built to display.


## Interiors pass

Three Mirrorhold interiors added - the Lens Vault under the orrery, the Mirror
Cistern under the fountain plaza, and the Stair Cellars behind the cliff town -
with sixteen rooms and nine passages between them, on **one map** in the
Eternal Lands manner: separate blocks on a 204 m square with unreachable ground
between them, entered at three arrivals. Full account in
`../interiors/MIRRORHOLD_INTERIORS.md`.

The first layout put the blocks in a row, 296 x 56 m. That could never have
been served: the server's ELM validator requires width == height, and a map is
a whole number of six-metre tiles. Blocks are now on a grid and the map squared
up to the next tile boundary, with the fourth quarter left free.

Region changes this required:

- **The `resonant_vault` portal was wrong and is removed.** That interior
  declares `parentRegion: amethyst_barrens` and the server links it to
  `four_gates`; Mirrorhold never had a claim on it. It was an error in the
  first production pass of this region, not a data conflict.
- Three interior entrances added, at the orrery, the plaza and the cliff town.
- The `drowned_crown` portal is removed. Its concept declares Crownwater as
  parent and the user has settled it as Crownwater's, against a `maps.txt` link
  that had pointed it here since before this region was authored. The
  pre-existing 192-scale server pair is left for whoever repoints it.
- **The declared sun direction was inverted.** `environment.sun.direction` is
  read by the client's `WorldEnvironmentBinder` as the direction light
  *travels* - it does `look_at_from_position(ZERO, direction)` and a
  `DirectionalLight3D` shines along its own `-Z`. The value shipped was the
  offline rasteriser's convention, whose `sun_direction` is documented in
  `native/raster.c` as "points from surface toward the sun", i.e. the exact
  opposite. A `+Y` component lights the region from underneath. Both the day
  and golden-hour suns are negated. **Amberwood and Four Gates still declare
  the uncorrected vector.**
- `build_mirrorhold.py` now warns when a pinned material is unreferenced, so an
  over-broad pin cannot be silent. Mirrorhold's pin is exact: 26 pinned, 26
  embedded, 26 referenced. The warning is suppressed for the reduced package,
  which drops ground dressing by design.

Toolkit changes, all additive:

- `region_client_check.gd` now tests the contract that holds for interiors as
  well as regions - every cell the collision grid marks walkable has a surface
  - instead of requiring floor under every tile in the bounding box, which only
  a region satisfies.
- `godot_capture.gd` honours a package's declared `environment` and `lights`
  when it declares `sky: "none"`, so an interior is captured under its own
  lamps rather than an outdoor sun.
- `interior_views.py` derives an interior's camera set from its manifest's own
  space list.

## The frozen lake was blended

`glacier_ice` originated here, as a blended material at 94% opacity for the
frozen lake. That was wrong for a walk surface: this region's `Terrain_Ice` is
a 448 x 108 m sheet with 78 m of relief, and the client renders through GL
Compatibility, where an alpha-blended surface writes no depth and where Godot's
depth pre-pass mode falls back to plain blending. The lake sorted as one whole
instance, drew over its own nearer folds and lost its shadow. Whitehorn Range,
which reuses the material for a far larger glacier, reported it from live play.

The material is opaque now, here and in Whitehorn Range and both ice interiors.
See `whitehorn_range/change-log.md` for the full account.

## The ground is cut inside the cell, not at its corners

The heightfield is sampled every two metres and `build_meshes` gave each quad
whole to the class of one corner, so a road could only ever turn on a cell
boundary and read as a flight of two-metre steps.

A class now takes every quad it touches and carries a per-vertex coverage in
COLOR_0's alpha, drawn with an alpha-tested copy of its material, so each pixel
goes to whichever class covers it. Where an operator knows its own edge -
`grade_path` for a road, `plateau` for a rim - `Terrain.surface_strength` puts
the cut on the real edge; elsewhere it falls half way between samples, which is
still a diagonal rather than a staircase. `despeckle_surfaces` clears class
islands under six cells first, because a crumb that read as a stray square at
whole-quad ownership reads as a deliberate blob once it is cut smoothly.

An alpha test is opaque, so it writes depth and sorts like any other ground.
The classes overlap where they meet by design, and `check_zfighting.py` skips
pairs that are both alpha-tested with vertex coverage.

See `whitehorn_range/change-log.md` for the full account, including why the
heightfield was not taken to one metre instead.


## 2026-09-07: connected lake approach and civic thresholds

Replaced the four raised, short radial causeways with continuous marble decks
at the promenade's level. The southern arm bends to the Sanctuary Road and
its watch apron; the northern arm reaches the quay road. Side piers now have
fishing boats and crates. Cardinal gaps in the colonnade keep approaches clear.

Moved all three interior triggers from scenery centres to authored entrance
buildings. Cut a broader lower-town court and graded the cellar lane from the
arrival's surveyed height. Grouped the civic services beside the fountain.

Corrected the ring walking surface's downward triangle winding and rasterised
actual deck triangles in the region's initial collision build. The prescribed
height refinement, walk-surface opening and solid-landmark passes still follow
the build. Added a shared optional waystation position so the southern march
station can use the shore apron instead of its old underwater setback.

The shared preview tool now resolves deck cameras from the emitted walk
triangles for regions without a camera manifest. New recipes retain the
existing material palette. See layout-review.md for captures and validation.
