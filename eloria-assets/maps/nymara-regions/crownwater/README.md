# Crownwater production map

Current package: **396 × 396 metres**, one metre per server tile, origin
**(120,120)** and arrival in the working harbour at world (0,0). See
[coastal-review.md](coastal-review.md) for the inhabited coastal composition,
reproducible build, current verification and preserved travel/content identities.
Main geometry is 22.13 MB; the far package is 13.29 MB. Both validators report
zero errors and warnings; all 156,816 server positions have a grounding surface.

The current served-grid fixture contains **18 routes and 39 exact path legs**,
including all seven ordinary interior entries, a two-metre walk away from each
threshold, and its real return. Service stops check positive replies or opened
storage. Configured NPC footprints and conservative 3×3 service furniture stay
clear of those standing posts. The undercroft verger works at (45,277), beside
the arrival/exit at (43,277); the migration preserves this correction on reruns.

**Historical production notes follow.** The measurements below describe the
previous 576-metre iteration and are retained as its record.

The Nymara lagoon city, taken from its placeholder package to a production
runtime map at **576 m x 576 m, one metre per tile** (96x96 server ELM tiles).

Composition authority is
`eloria-assets/concepts/nymara-regions/crownwater_region_concept.png`. Player
scale was worked from the ten-panel detail board, which is **truncated on disk**
and was supplied to this session separately - see `comparison-report.md`, which
does not pretend otherwise.

## What is here

| File | What it is |
| --- | --- |
| `world.glb` | self-contained glTF 2.0, 23.4 MB, 587,106 unique / 1,271,396 instanced triangles |
| `world-lod2.glb` | reduced package, 14.0 MB, 42% smaller |
| `world.json` | schema-1 manifest: bounds, transform, spawns, collision, navigation, landmarks, interactives, NPC and creature markers, harvestables, portals, roads, water, environment, minimap, provenance |
| `collision.bin` | EWCG v1, 1152 x 1152 half-metre cells, 25.6% walkable |
| `minimap.webp` | rendered from the final geometry, not drawn |
| `camera-views.json` | 23 framings, emitted from `source/views.py` |
| `performance.json` | raw measurements written by the build |
| `references/captures/` | **real Godot 4.7.2 client frames**, not offline previews |
| `references/comparisons/` | aerial and panel comparison sheets, contact sheet |
| `source/` | the complete, reproducible build |

## Editor kit

`source/prepare_meshy_kit.py --input <crownwater> <westhaven> <four gates> <mirrorhold> <ssarathi> <verdant models>`
seats generated models in the territory palette's kit
(`godot-client/world_authoring/regions/crownwater/assets/prototypes/kit-*.glb`). Each model is taken
from the first folder that has it.

- The Crownwater set, from `work-output/crownwater-2026-09-28/asset-prompts.md`: a gondola, a
  ceremonial barge, a flower barge, lamp buoys and divers' floats; bricole posts, a gondola post, a
  water stair and a sea wall; a teal-domed gazebo, a crown fountain, balustrades, citrus planters,
  obelisk lamps and a pergola; oyster baskets, a pearl-sorting table, a net-mending frame, market
  parasols and a sunken statue head.
- Westhaven's fishing boats, skiff, sloop, caravel, mooring buoy, cypress, stone pine, lemon tree,
  bougainvillea, beach rocks, rope and fish crates.
- Four Gates' blue-dome kiosk, topiary, urns, hedges, rose arches, reflecting pool, well and autumn
  maples.
- Mirrorhold's potted cypress, flower planters, drinking fountain, benches and mooring posts.
- Ssarathi's coastal rocks, sea stacks, lotus pads and lagoon reeds.
- Verdant Stair's meadow flowers and flowering shrubs.

Wrapper-node transforms are baked into the vertices before each model is scaled to its size in
`SIZES`. It is then stood on the origin, except the floating pieces (`WATERLINE`), which keep their
waterline there. Its textures are shrunk and content-addressed into `assets/textures/`.
`source/prepare-meshy-kit.json` records the input and output digests, and `--check` verifies them.

## Building it

```sh
cd source && python build_crownwater.py
python ../../_toolkit/verify_runtime.py --package ..
python make_sheets.py
```

Deterministic: the same seed reproduces the same bytes. Verified - two
independent runs produce byte-identical `world.glb`, `world-lod2.glb`,
`world.json`, `collision.bin`, `minimap.webp`, `camera-views.json` and
`performance.json`. The two `*.validator.json` files differ only in the
absolute path they record and their timestamp. The build imports the
shared toolkit at `maps/nymara-regions/_toolkit/` and **modifies nothing in it**.

Real client captures (needs a Godot 4.7.2 binary and a display):

```sh
ELORIA_ARTIFACT_DIR=<dir> godot --audio-driver Dummy \
  --rendering-method gl_compatibility --path godot-client \
  --script res://tests/integration/rendered_crownwater.gd
```

## Verification

| Check | Result |
| --- | --- |
| `validate_gltf.py` on `world.glb` | **0 errors, 0 warnings** |
| `validate_gltf.py` on `world-lod2.glb` | **0 errors, 0 warnings** |
| `verify_runtime.py` | **0 errors**, 2 documented warnings |
| Grounding-ray misses | **0** across all 331,776 reachable server tiles |
| Loads through the real `world_loader.gd` | **yes** - 23/23 captures pass |

See `validation-report.md` for what those numbers do and do not cover, and
`modeling-assumptions.md` for the decisions a reviewer may want to overrule.

## Interiors

Four insides open off this map - The Drowned Crown (under the basilica), The
Tide Cistern (under the garden islet), The Harbour Customs Hall and The Tide
Campanile - and they share **one map with unwalkable blackspace between them**,
as Eternal Lands lays out a region's interiors. Built by
`source/build_insides.py`, verified by `source/verify_interiors.py`, server map
written by `source/export_insides_collision.py`, documented in
`../interiors/CROWNWATER_INTERIORS.md`.

## Server

Crownwater needs a bigger server map, as Amberwood does.
`../server-collision/crownwater.bin` is regenerated to 96x96 tiles / 576x576 height
cells from this build's own collision grid and must be loaded server-side. The
matching generator and contract-test change is on the `eloria-server` branch
`feature/crownwater-96-server-map`.
