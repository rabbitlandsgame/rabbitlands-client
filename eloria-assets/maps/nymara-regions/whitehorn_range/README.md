# Whitehorn Range production map package

Whitehorn is Nymara's high alpine region: a glaciated bowl that climbs from an
inhabited southern approach to a temple standing below the head of the ice. The
pilgrim road enters through a gate on the low ground, climbs cairn-lined
switchbacks, crosses a gorge on rope bridges, and ends at the Glacier Temple. An
ice cave opens in the west, a worked mine in the east, and frozen cascades hang
off the shoulders of the central glacier.

The region is authored at **576 m x 576 m** on a 96 x 96-tile server map at one
metre per tile, matching Amberwood's extent and arrival datum.

This directory is the runtime package plus everything needed to rebuild it.

## Runtime files

| File | What it is |
| --- | --- |
| `world.glb` | Self-contained glTF 2.0 scene: geometry, materials and every texture embedded. No external files, no glTF extensions. |
| `world.json` | GLB world manifest, schema version 1 — bounds, coordinate transform, spawns, collision and navigation declarations, landmarks, interactives, NPC and creature markers, harvestables, portals, environment, minimap transform, provenance. |
| `collision.bin` | Half-metre walkability grid, `EWCG` version 1, 1152 x 1152 cells over the server footprint. |
| `minimap.webp` | North-up minimap rendered from the final geometry, not drawn by hand. |
| `world.glb.validator.json` | glTF 2.0 validation report. |
| `performance-summary.md` | Triangle, node, texture and package budgets. |

There is no `world-lod2.glb`. Whitehorn is 2.09 triangles per square metre
against Amberwood's 9.5, so the reduced package Amberwood needed does not earn
its place here; see `modeling-assumptions.md`.

## Source

`source/` holds this region's own build. The shared authoring toolkit lives in
`../_toolkit/` and is documented there. Everything is pure Python (numpy +
Pillow); nothing imports a model, a texture or an asset pack.

```sh
cd source
python3 build_whitehorn.py                        # writes the package one directory up
python3 ../../_toolkit/verify_runtime.py --package ..
python3 ../../_toolkit/validate_gltf.py ../world.glb
python3 ../../_toolkit/export_server_collision.py --package ..
cd ..
python3 ../_toolkit/capture_views.py              # comparison captures (run from the package)
python3 ../_toolkit/make_comparison.py
```

The build is deterministic: the same seed reproduces the same bytes. Runtime
startup never depends on rerunning it — the committed artefacts load directly.

## Coordinates

Right-handed, metres, Y up, north toward `-Z`. The server's 576-cell grid maps
at one metre per tile with the arrival datum at server `(174, 174)`:

```
godot_x = server_x - 174        godot_z = 174 - server_y
```

so the reachable footprint is `x ∈ [-174, 401]`, `z ∈ [-401, 174]`. Terrain is
cut 30 m larger on every side and the surplus is raised into mountain wall, so a
character cannot reach an unfinished void.

**This needs a matching server map.** `../server-collision/whitehorn_range.bin` is
regenerated here at 96 x 96 tiles (576 x 576 height cells) with real elevation
and walkability, replacing the flat 32 x 32 placeholder. The corresponding
server change is on `feature/whitehorn-range-576m-server-map` in `eloria-server`.

## Navigation contract

The Godot client turns every `MeshInstance3D` whose name begins with an entry in
`navigation.surfaceNodePrefixes` into collision on its navigation layer, then
grounds actors with a downward ray from y = 400 to y = -100. This package uses
two prefixes:

* `Terrain_` — the six terrain surface classes in use (snow, ice, rock, trail,
  paving, marble, alpine turf).
* `Walk_` — authored walkable decks only: the two rope-bridge decks, the temple
  stair and the temple forecourt.

Structural geometry is deliberately **not** a walk surface, so the grounding ray
never snaps a character onto a lintel, a mine gantry or an icicle.

## Editor kit

`source/prepare_meshy_kit.py --input <whitehorn models> <mirrorhold models> <amethyst models>` seats
the generated models in the territory palette's kit
(`godot-client/world_authoring/regions/whitehorn_range/assets/prototypes/kit-*.glb`). Each model is
taken from the first folder that has it.

- The Whitehorn set, from `work-output/whitehorn-range-2026-09-28/asset-prompts.md`: granite spires,
  crags, a knife ridge, boulders, a rockfall and an icicle arch; frozen waterfalls, ice shards, a
  glacier block, frozen ponds and icicle fringes; snow-laden firs, a wind-bent pine, a frosted larch
  and juniper; expedition tents, firewood shelters, sledges, ski racks, gear baskets, trail lanterns
  and windbreaks; horn waystones, horn shrines, cairn towers and prayer bells and flags; snow drifts,
  frost grass and lichen stones.
- Mirrorhold's snow-capped boulders, snow scree, alpine firs and pines, juniper, tussock grass and
  flower cushions.
- Amethyst Barrens' lantern post, supply crates, ore cart, mine rails and tool rack for the mine yard.

The delivery sizes its models with wrapper nodes. The prepare step bakes each mesh node's transform
into its vertices, then scales the model to its size in `SIZES`, stands it on the origin, and shrinks
and content-addresses its textures into `assets/textures/`. `source/prepare-meshy-kit.json` records
the input and output digests, and `--check` verifies them.

## Verification

| Check | Result |
| --- | --- |
| `validate_gltf.py` | **0 errors, 0 warnings, 0 infos** |
| `verify_runtime.py` | **0 errors**, 331,776 tiles sampled, **0 grounding misses** |
| Godot 4.7.2, real `WorldLoader.load_world()` | loads, batches, **0 misses** over 5,184 sampled tiles; all three spawns ground within 0.02 m of the manifest |

The one `verify_runtime` warning is `GROUNDING_DISCONTINUITY` at the boundary
rim and the gorge walls, which is the documented cliff case.

See `validation-report.md` for the full picture, including what is **not**
verified.
