# Manymouth Delta production map package

Manymouth is Nymara's braided river delta: a 480 m × 396 m distributary fan of
turquoise channels and low silt bars, inhabited by stilt villages linked by
plank walkways, carrying a drowned glyph-cut ring-arch on its central axis and
a stepped bronze-banded temple on its eastern rim, thinning north-west into
open sea and thickening south-east into jungle.

The region is authored at **480 m × 396 m** inside a 480 × 480 native server
grid, at one metre per tile with origin [138,120]. Shared continent geography
adds addressable padding for its land approaches; the atlas follows the owned
physical footprint. The market, houses and monumental geometry retain their
original scale. See [source/README.md](source/README.md) for the reproducible
compact field, physical path audit and one-time content migration.

Two thirds of it is water. That is not a gap in the map; it is the map. See
`modeling-assumptions.md` for what follows from it, and `traversal-modes.md`
for the swim/dive/shapeshift design the package is authored to support.

## Interiors

Four insides on one map with blackspace between them, at
`../interiors/manymouth_delta_insides/`: the Flooded Labyrinth, the Underdeck,
the Tide Hall and the Sanctum. Built by `source/build_interiors.py` and
`source/interiors.py`; the server map key is `manymouth_flooded_labyrinth`,
grown from 32 to 64 ELM tiles. Four doors on this map target it, differing only
in `destinationSpawn`, and each has a matching return spawn here so both
directions resolve. See that package's README.

## Runtime files

| File | What it is |
| --- | --- |
| `world.glb` | Self-contained glTF 2.0 scene: geometry, materials and every texture embedded. No external files, no glTF extensions. |
| `world.json` | GLB world manifest, schema version 1 — bounds, coordinate transform, spawns, collision and navigation declarations, landmarks, interactives, NPC and creature markers, harvestables, portals, walkway routes, water, environment, minimap transform, provenance. |
| `world-lod2.glb` | Reduced package: far-tier vegetation only, no ground clutter or root mats, a thinned mangrove belt, half-resolution textures. |
| `collision.bin` | Half-metre EWCG v2 surface grid over the current server footprint; its exact dimensions and encoding are in `world.json`. |
| `minimap.webp` | North-up minimap rendered from the final geometry, not drawn by hand. |
| `world.glb.validator.json` | glTF 2.0 validation report. |
| `verification-report.json` | Runtime contract report: grounding, navigation, collision and spawn checks. |
| `client-check-report.json` | The same contract re-run **inside Godot**, through the project's own `WorldLoader`. |
| `camera-views.json` | The capture camera set, resolved to world space, shared by the offline previewer and the in-client harness. |
| `performance.json` | Machine-written measurements. `performance-summary.md` is the human-written reading of them. |

## Source

`source/` holds this region's composition and its build entry point. The shared
authoring toolkit lives in `../_toolkit/` and is imported, not copied.

| File | What it is |
| --- | --- |
| `region.py` | The plan: extents, surface classes, anchors, the island field, the distributaries, terrain sculpting and built ground. |
| `populate.py` | The placement passes, in largest-to-smallest order. |
| `deltakit.py` | Nine procedural material recipes the shared kit has not got, and the pin of exactly which materials this region embeds. |
| `stiltkit.py` | The building kit — everything that stands in water — and five tree species. |
| `views.py` | The camera set and the detail-board panel mapping. |
| `build_manymouth_delta.py` | The build: GLB, manifest, collision, minimap, validator report. |

```sh
cd source
python3 rebuild_landscape.py --server <paired-server-checkout>
python3 ../../_toolkit/verify_runtime.py --package ..
python3 ../../_toolkit/validate_gltf.py ../world.glb
## Server collision and content publication are owned by the shared coordinator.
python3 ../../_toolkit/capture_views.py          # offline preview captures
python3 ../../_toolkit/compress_captures.py      # PNG -> WebP
python3 ../../_toolkit/make_comparison.py        # concept/build comparison sheets
```

Real client frames, from the repository's own Godot project:

```sh
cd ../../../../godot-client
Godot_v4.7.2-stable_win64_console.exe --path . \
  --script ../eloria-assets/maps/nymara-regions/_toolkit/godot_capture.gd \
  --rendering-driver vulkan --resolution 1600x1000 -- \
  --package=<abs>/manymouth_delta --out=<abs>/manymouth_delta/references/godot-captures

Godot_v4.7.2-stable_win64_console.exe --path . --headless \
  --script ../eloria-assets/maps/nymara-regions/_toolkit/region_client_check.gd \
  -- --manifest=<abs>/manymouth_delta/world.json
```

Note the texture cache: `preview.py` keys it on a digest of the *shared*
`textures.py` and `materials.py` only, so it does not notice an edit to
`deltakit.py`. This region's own recipes are therefore generated fresh on every
run rather than cached, which is why `register()` never reads from that cache.

## Editor kit

`source/prepare_meshy_kit.py --input <manymouth> <ssarathi> <verdant> <four gates> <westhaven models>`
seats generated models in the territory palette's kit
(`godot-client/world_authoring/regions/manymouth_delta/assets/prototypes/kit-*.glb`). Each model is
taken from the first folder that has it.

- The Manymouth set, from `work-output/manymouth-delta-2026-09-28/asset-prompts.md`: stilt houses, a
  net shed, a spirit shrine, a stone lantern and a bamboo gate; sampans, a market boat, a reed raft and
  floating lanterns; a banyan, a fan palm, bamboo, a flame tree, water lilies and papyrus; rice
  paddies, sheaves, a rice store and a fish weir; water jars, a hearth, a hammock, a fish line,
  offerings and heron decoys.
- Ssarathi's palms, mangroves, undergrowth, lotus pads, reeds, fish traps, canoes, fishing platforms,
  lantern poles and banners.
- Verdant Stair's tree ferns, saplings, shrubs, reeds, drying racks, baskets, pots, lantern strings and
  produce stall.
- Four Gates' autumn maples, scarecrow and stooks.
- Westhaven's fishing boat, skiff, rope, fish crates and lemon tree.

Wrapper-node transforms are baked into the vertices before each model is scaled to its size in
`SIZES`. It is then stood on the origin, except the floating pieces (`WATERLINE`), which keep their
waterline there. Its textures are shrunk and content-addressed into `assets/textures/`.
`source/prepare-meshy-kit.json` records the input and output digests, and `--check` verifies them.

## Coordinates

Right-handed, metres, Y up, north toward `-Z`. The server's 576-cell grid maps
at one metre per tile with the arrival datum at server `(174, 174)`:

```
godot_x = server_x - 174        godot_z = 174 - server_y
```

so the reachable footprint is `x ∈ [-174, 401]`, `z ∈ [-401, 174]`. Terrain is
cut 30 m larger than that on every side and the surplus is drowned.

**This needs a matching server map.** `../server-collision/manymouth_delta.bin` is
regenerated here at 96 × 96 tiles (576 × 576 height cells) with real elevation
and walkability, replacing the flat 32 × 32 placeholder. The server-side change
that serves it at that size is `feature/manymouth-delta-96-server-map` in
`eloria-server`; the two must land together, because this manifest declares
`serverOrigin [174, 174]`.

## Navigation contract

The Godot client turns every `MeshInstance3D` whose name begins with an entry in
`navigation.surfaceNodePrefixes` into collision on its navigation layer, then
grounds actors with a downward ray. This package uses two prefixes:

* `Terrain_` — the six terrain surface classes, **including the ones below sea
  level**. The delta bed is terrain everywhere. That is what makes zero
  grounding misses achievable on a map that is two-thirds water.
* `Walk_` — authored walkable decks only: walkway decking, bamboo causeways,
  quays, house verandas, landing stairs, the arch platform, the temple stair
  and the labyrinth threshold.

Structural geometry is deliberately **not** a walk surface. No placement in
`populate.py` sets `walk_surface=True`; every walkable piece is a `MeshGroup`
that declares its deck through `add_walk`. There is a comment in `populate.py`
explaining why, and it is worth reading before adding a placement — setting the
flag on a `MeshGroup` prefixes the node `Walk_`, which every *solid* child then
inherits, and the boardwalk handrails become walkable.

`verify_runtime.py` casts the client's exact ray at all **331,776** reachable
server tiles and reports **zero misses**. `region_client_check.gd` re-runs the
same contract inside Godot 4.7.2 against the real physics world.
