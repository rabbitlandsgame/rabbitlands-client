> Historical record of the previous 576m package. The current 396m coordinate contract and layout are documented in [README.md](README.md) and [layout-review.md](layout-review.md); current metrics are generated in `performance.json` and `verification-report.json`.

Current checkpoint: [2026-09-07 layout review](layout-review.md). The earlier
counts and camera comments below describe the previous build.

# Westhaven: validation report

What was checked, what passed, and — the part that matters — what these checks
do **not** cover.

## Results

### glTF validity

```
python3 ../_toolkit/validate_gltf.py world.glb
errors=0 warnings=0 infos=1

python3 ../_toolkit/validate_gltf.py world-lod2.glb
errors=0 warnings=0 infos=1
```

The single info in each is `NODE_EMPTY` on the group container nodes, which are
transform-only parents by design. Machine-readable copies are in
`world.glb.validator.json` and `world-lod2.glb.validator.json`.

Both packages are self-contained: no glTF extensions, no external buffers, no
external images.

### Runtime contract, reproduced offline

```
python3 ../_toolkit/verify_runtime.py --package .
[nav] 25 walk-surface nodes, 206,648 triangles
[grounding] 331,776 tiles sampled, 0 misses (0.00%)
[collision] 1152x1152, 55.9% walkable
[verify] 0 errors, 1 warnings
```

**Zero grounding misses across every one of the 331,776 server tiles.** That was
established on bare terrain, before a single piece of geometry was placed, and
re-established on the finished package.

The one warning is `GROUNDING_DISCONTINUITY`: 202 adjacent tile pairs whose
surface height differs by more than 6 m. Every one of them is deliberate — the
city's terrace risers, the sea cliffs on the headland and the two rocks, and the
map's north and east rim. The check exists to catch an accidental hole; these
are walls.

### Runtime contract, in the real engine

```
Godot_v4.7.2-stable_win64_console.exe --path . --headless \
  --script _toolkit/region_client_check.gd -- --manifest=<...>/world.json --step=4

[client-check] loader warnings=1
[client-check] server grid 576x576, sampling every 4 tiles
[client-check] grounding: 20,736 tiles sampled, 0 misses (0.00%)
[client-check] surface height range: -18.60 .. 99.95
[client-check] spawn default        manifestY 3.45  clientY 3.400  delta 0.050
[client-check] spawn fish-market    manifestY 9.55  clientY 9.499  delta 0.051
[client-check] spawn crown-terrace  manifestY 52.05 clientY 52.000 delta 0.050
[client-check] spawn lighthouse     manifestY 18.00 clientY 17.949 delta 0.051
[client-check] PASS
```

This is not the offline check repeated. It loads the package through the
project's own `WorldLoader`, lets it build collision and navigation exactly as
the game does, and casts `main.gd`'s grounding ray (y = 400 down to y = -100 on
`NAVIGATION_SURFACE_LAYER`) against the real physics world. The two agree, which
is what makes the offline check trustworthy for this package.

The loader warning — "navigation polygons did not produce collision" — is
expected: the manifest declares an empty `navmesh.polygons` array and navigation
comes from the `surfaceNodePrefixes` path, which is how every region in this
directory works.

Machine-readable copy: `client-check-report.json`.

### Determinism

`world.glb` was rebuilt from a clean run and is byte-identical to the previous
build. Name-derived seeds go through `noise.stable_hash()`, never the builtin
`hash()`.

### Collision binary

- dimensions 1152 x 1152, both positive multiples of six
- 0.5 m cells over the 576 m playable square
- 742,398 walkable cells, 55.9%
- 19 elevated decks claim their footprint (the mole runs, the two pier decks,
  the bastion platform, the arcade and market walkways, the lighthouse
  galleries)
- row 0 is the +Z southern edge, column 0 the -X western edge — the order
  `verify_runtime`'s cell-to-surface cross-check verifies, and the one thing
  nothing else would catch

## What these checks do not cover

This is the important half of this document.

**No claim is made that the map looks right.** A clean validator report says the
file is well-formed and the grounding contract holds. It says nothing about
composition, proportion, colour or whether the region resembles its concept art.
For that, see `comparison-report.md` and the sheets in
`references/comparisons/`, and then look at the captures yourself.

**Not verified:**

- **End-to-end login.** The package was never loaded by a running client
  connected to a running server. The server-side 96 x 96 map exists on
  `feature/westhaven-576m-server-map` in `eloria-server` and generates and
  validates, but client and server were never run together.
- **Every place name.** All invented. See `modeling-assumptions.md`.
- **Gameplay balance of any kind.** NPC markers, harvestables, interactives and
  portals are editor/visual metadata carrying `"authority": "server"`. Nothing
  dynamic is baked into the static mesh and none of it was tested in play.
- **Performance on real hardware.** The triangle and texture figures in
  `performance-summary.md` are counted from the package, not measured in a
  frame. No profiling was done, and nothing streams or switches LOD yet.
- **The LOD2 package in the engine.** It validates and loads through the
  offline path; it was not swapped in and rendered.
- **Portal destinations.** Eight portals: four naming neighbouring region maps
  by registry key, and four doors into `westhaven_insides`. Every one of the
  eight, and every spawn, was checked against the finished collision grid and
  stands on a walkable cell — six had to be moved onto one, and the build
  reports each. Whether the transitions actually *fire* is the server's business
  and was not exercised.
- **Water shading.** The GLB ships a flat lit plane. `environment.water`
  declares shallow/deep tint and caustics as presentation settings for whoever
  writes the shader; none of that is implemented or verified.

## About the captures

Two sets ship, and they are different things:

- `references/godot-captures/` — **real client frames**, rendered by Godot
  4.7.2 with the Vulkan driver through the project's own `WorldLoader`. 23
  frames at 1600 x 1000.
- `references/captures/` — **offline previews** from the toolkit's C
  rasteriser. Same camera table, so they line up with the client frames, but
  they are an authoring aid and not what the engine draws.

The comparison sheets are built from the Godot frames and are labelled
"real Godot frame" on the sheet itself. Where a sheet or a caption says
"offline preview", that is exactly what it is.

The two sets differ visibly in exposure and sun angle: the client frames are
brighter and cooler, the offline previews warmer. That is a difference between
two renderers, not a defect in either, and it is why the comparison sheets use
the client frames.
