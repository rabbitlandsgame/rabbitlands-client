# Amethyst Barrens production map

A 384 m × 384 m Nymara region: a storm-scoured crystal basin under permanent
cloud, with the Glasswarden Observatory on its terrace in the north-west, a
crystal massif erupting from the northern uplands, mountains closing the north
and west, and the sea biting into the north-east and south-east corners.

| | |
| --- | --- |
| Extent | 384 m × 384 m, one metre per server tile |
| Server map | 64 × 64 ELM tiles (384 × 384 collision cells) |
| Arrival datum | primary server tile (140, 85); server origin (116, 116) |
| `world.glb` | reproduced exterior with LOD and reciprocal receiving strips; see performance in world.json |
| `collision.bin` | 768 × 768 at 0.5 m; corrected from exported walking surfaces |
| Landmarks | 62, with stable legacy names |
| Status | `production-geometry-materials-population` |

See [landscape-redesign.md](landscape-redesign.md) for the inhabited-basin pass,
compact coordinate decisions, retained content, reciprocal borders and review evidence.

## Contents

```
world.glb                 self-contained glTF 2.0, no extensions, no external files
world.json                world manifest, schema version 1
collision.bin             half-metre walkability grid (EWCG v1)
minimap.webp              rendered from the final geometry, north-up
world.glb.validator.json  glTF validator report (0 errors, 0 warnings)
references/
  00-concept-detail-board.png    ten-panel board, player-scale authority
  01-concept-aerial-overview.png aerial concept, composition authority
  captures/                      offline preview renders (NOT client frames)
  client-captures/               real Godot 4.7.2 frames through WorldLoader
  comparisons/                   concept-to-build sheets
source/                   the region build; see source/README.md
```

## Building

```bash
cd source && python rebuild_landscape.py --verify
```

The seeded build reproduces the authored region and includes reciprocal
receiving strips from the shared border specifications. Rebuild the frozen
set of neighboring sources together when reproducing a release. Validation
reports also record their absolute path and timestamp.

The shared authoring toolkit lives at `../_toolkit/` and is imported, not
copied. Region-specific code is `source/region.py` (extent, anchors, routes,
watercourses, terrain), `source/populate.py` (placement passes) and
`source/views.py` (cameras, panel mapping and this region's capture lighting).

## Verification

```bash
PYTHONPATH=../_toolkit python ../_toolkit/validate_gltf.py world.glb
PYTHONPATH=../_toolkit python ../_toolkit/verify_runtime.py
```

- `validate_gltf.py`: **0 errors, 0 warnings**
- `verify_runtime.py`: **0 errors**, 147,456 tiles sampled, **0 grounding
  misses**; see `verification-report.json` for current cliff-and-bridge warnings

The current compact review is recorded in `landscape-redesign.md` and the
northern rollout artifacts. Older `validation-report.md` and
`comparison-report.md` document the original 576m production package.

## Server side

The region needs the regenerated 64 × 64 ELM at
`../server-collision/amethyst_barrens.bin`, written by
`../_toolkit/export_server_collision.py` from the same terrain the GLB is built from.
The rollout coordinator applies `source/migrate_compact_server.py`, then
synchronizes collision, portals, secrets and content against the final package.

Client collision bytes use the refined height encoding in `world.json`, with
zero meaning blocked. The server exporter applies the server's own height
encoding and conservative tile folding; it must read the final corrected
collision after the sequential rebuild completes.
