# Sunmane Steppe - production region package

The Sunmane Steppe is the Orun horse culture's grassland: four clan camps ring a
shared seasonal market at a ceremonial crossroads, caravanserais guard the
travel axes, and windmills, wells, animal pens, banner shrines and burial mounds
carry the wider pastoral landscape out to a rugged western coast.

North and east the region continues past the grassland: a dune field with salt
pans and a sand road, the violet Amethyst badland with its wind-carved spires,
and the Whitehorn front, whose foothills and summits close the world on those
two sides. Four cave mouths open off that ground; two of them lead to explorable
interiors that ship as their own packages under `../interiors/`.

The September 2026 circulation pass gives the market grouped services, side-court
inns, three surveyed bridges and watered grain plots. The actual arrival is
server (79, 37); (58, 58) remains the coordinate datum. See
[layout-review.md](layout-review.md), [coverage-map.md](coverage-map.md) and
[change-log.md](change-log.md) for the current design and validation.

This package replaces the earlier starter conversion, which carried landmark
silhouettes borrowed from other regions' name-spaces and no authored
architecture.

## Runtime files

| File | Purpose |
|---|---|
| `world.glb` | Self-contained glTF 2.0 region: terrain, water, architecture, props, vegetation, embedded PBR textures |
| `world.json` | Schema 1.1 manifest: bounds, coordinate transform, spawn points, collision, navigation, landmarks, interactives, environment, population, minimap transform |
| `world-lod2.glb` / `world-lod2.json` | Reduced package for low-end settings: ground clutter and road dressing removed, textures at half resolution |
| `minimap.webp`, `full-map.webp` | Rendered orthographically from `world.glb` through the client's own world loader |
| `camera-views.json` | Reproducible client camera framings, derived from the exported landmark positions |
| `textures/` | The authored PBR kit as editable source; the same maps are embedded in the GLB |
| `references/` | Aerial overview and the ten-panel detail board, the visual authority for the region |
| `comparison/` | Concept-versus-client sheets, one per reference panel, plus contact sheets for the desert, badland and mountain ground and for the two cave interiors |
| `world-statistics.json`, `world-lod2-statistics.json` | Current geometry and package cost |
| `performance.json`, `performance-summary.md` | Historical runtime measurements, with current package costs identified separately |

Nothing at runtime depends on rerunning the build: the committed GLB, manifest
and minimap load directly.

## Region frame

| Property | Value |
|---|---|
| Coordinate datum | `(58, 58)` -> Godot `(0, 0)` |
| Current server arrival | (79, 37) -> Godot (21, 21) |
| Metres per server tile | 1.0 |
| World span | 280 m x 280 m, centred on Godot `(36, -36)` |
| World bounds | X -104..176, Z -176..104 |
| Addressable band | X -58..133, Z -133..58 (server tiles 0..191 on both axes) |
| Elevation range | -20.5 m to 74.0 m |
| North axis | `-Z` |
| West crossing | server `(6, 58)`, the caravan road to Mirrorhold |
| North crossing | server `(66, 184)`, the desert track into the Amethyst Barrens |
| South crossing | server `(62, 18)`, the shore road to the Verdant Stair |
| North barrow | server `(58, 100)`, a sealed passage; the Ssarathi Royal Archive is entered from the Ssarathi Ruins |
| Wind Caves entrance | server `(128, 175)` -> `sunmane_wind_caves` |
| Crystal Hollow entrance | server `(182, 154)` -> `sunmane_wind_caves` (both cave systems share the map) |

Everything outside the addressable band is scenery: the far spires, the summits
and the open sea. Landmarks out there are marked `"reachable": false` in the
manifest and may not carry an interaction; `validate_package.py` asserts it.

## Landmark inventory

The counts the written region description specifies are asserted by
`maps/nymara-regions/sunmane_steppe/source/validate_package.py`.

| Landmark | Count |
|---|---:|
| animal-pen | 6 |
| badland-spire | 8 |
| banner-shrine | 8 |
| bridge | 3 |
| burial-mound | 6 |
| caravanserai | 4 |
| cave-entrance | 4 |
| gate | 4 |
| great-hall | 1 |
| landing | 1 |
| outpost | 8 |
| round-tent | 12 |
| seasonal-market | 4 |
| standing-stones | 13 |
| water-station | 2 |
| waystone | 8 |
| well | 4 |
| windmill | 6 |

Ambient livestock: 111 animals across 22 groups, instanced by
the client's ambient population system rather than baked into the world mesh.
Server-owned NPCs, harvestables and creature spawns are recorded under
`runtimePopulation` for the matching server profile.

## Rebuilding

```sh
python3 eloria-assets/maps/nymara-regions/sunmane_steppe/source/build_sunmane.py                 # world.glb + world.json
python3 eloria-assets/maps/nymara-regions/sunmane_steppe/source/build_sunmane.py --lod 2         # world-lod2.glb
python3 eloria-assets/maps/nymara-regions/sunmane_steppe/source/creatures.py             # steppe horses
python3 eloria-assets/maps/nymara-regions/sunmane_steppe/source/views.py                 # camera-views.json
python3 eloria-assets/maps/nymara-regions/sunmane_steppe/source/validate_package.py      # package checks

godot --headless --path godot-client --script res://tests/integration/sunmane_grounding.gd
xvfb-run -a godot --display-driver x11 --rendering-method gl_compatibility \
  --path godot-client --script res://tests/integration/sunmane_minimap.gd
xvfb-run -a godot --display-driver x11 --rendering-method gl_compatibility \
  --path godot-client --script res://tests/integration/rendered_sunmane_steppe.gd
python3 eloria-assets/maps/nymara-regions/sunmane_steppe/source/caves.py                 # both cave interiors
python3 eloria-assets/maps/nymara-regions/sunmane_steppe/source/comparison.py            # comparison sheets
```

For the current layout, follow each exterior build with the correction passes
in this order from nymara-regions, then rebuild the secrets:

```sh
python _toolkit/refine_walk_heights.py sunmane_steppe
python _toolkit/open_walk_surfaces.py sunmane_steppe
python _toolkit/stamp_solid_landmarks.py sunmane_steppe
python _toolkit/secrets_build.py sunmane_steppe
```

On the server, sync authored collision for sunmane_steppe,
sunmane_wind_caves and sunmane_steppe_secrets, generate the served maps, apply
continent_portals.py --region sunmane_steppe, then author_region_content.py all
--region sunmane_steppe and relocate content using those maps. The full rebuild
order in CONTINENT.md remains authoritative. Refresh source/server-content.json
with sync_package_content.py --package nymara-regions/sunmane_steppe
--write-source-posts --apply and regenerate LOD2 after the final server posts.

For current surface review, regenerate source/views.py and use the shared
_toolkit/godot_capture.gd with --package=<this package>,
--out=<this package>/references/godot-captures and --environment=manifest.
Use a real GL Compatibility context. Then run source/comparison.py
--surface-only; its default mode retains the historical golden-hour and cave
capture workflow. The shipped current frames are WebP review images, while
references/captures/index.json is camera input only.

The render and minimap passes need a real GL context, so they run under `xvfb`
without `--headless`; the grounding, traversal and cave tests are pure physics
and run headless.

All geometry, textures and creature assets in this package are original Eloria
project work under CC-BY-4.0. No third-party asset packs and no Eternal Lands
assets were used, converted or traced.

## The ground is cut inside the cell, not at its corners

`terrain_mesh.build_chunks` gave each quad whole to the majority class of its
four corners - "so a quad never straddles two materials" - which meant a class
edge could only ever run along a cell boundary and a diagonal caravan road read
as a flight of 1.4 m steps.

Every class the quad touches now takes it, each copy carrying a per-vertex
coverage in COLOR_0's alpha and drawn with an alpha-tested material, so each
pixel goes to whichever class covers it. The roads know where their own edge is
- `road_mask` and `trail_mask` are polyline falloffs and the class flips where
they cross their threshold - so `Landform.strength` records how far each sample
sits from that crossing and the cut lands on the real edge. Elsewhere the cut
falls half way between samples, which is still a diagonal rather than a
staircase. `terrain.despeckle` clears class islands under twelve cells first.

An alpha test is opaque: it writes depth and sorts like any other ground.

Two related repairs. The herd seeds were `abs(hash(identifier))`, and `hash()`
on a str is salted per process, so every build produced a different
`ambientPopulation` - the trap `caves.py` had already documented and fixed for
itself. `noise.stable_seed` is now shared by both. And vertex colours are
written as normalised bytes rather than floats, four bytes a vertex instead of
sixteen.

Costs 11,466 triangles (+5.0%) and 0.71 MB (+3.9%). `collision.bin` is
byte-identical: heights and classes did not move, only the way they are drawn.

See `whitehorn_range/change-log.md` for the full account of the technique.
