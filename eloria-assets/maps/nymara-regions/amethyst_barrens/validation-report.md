# September 2026 update

Current layout measurements, visual review and limitations are in
[layout-review.md](layout-review.md). The current comparison sheets use the
35 frames in references/godot-captures with the manifest environment.
Validator JSON and verification-report.json describe the current package.

The original report below is historical. Its counts, camera descriptions and
grades are superseded by the current review and performance summary.

---

# Amethyst Barrens â€” validation report

All figures below are from the committed artefacts. Reproduce with:

```bash
cd source && python build_amethyst.py
cd .. && PYTHONPATH=../_toolkit python ../_toolkit/validate_gltf.py world.glb
PYTHONPATH=../_toolkit python ../_toolkit/verify_runtime.py --report verification-report.json
```

## glTF validation â€” `validate_gltf.py`

```
errors=0 warnings=0 infos=0
```

The package is self-contained: no glTF extensions, no external buffers, no
external images. 13 materials and 39 embedded images, 4.25 MB of texture
bytes - the shared table holds 56 materials, and the build pins the subset this
region uses.

## Runtime contract â€” `verify_runtime.py`

```
[nav]        24 walk-surface nodes, 205,564 triangles
[grounding]  331,776 tiles sampled, 0 misses (0.00%)
[collision]  1152x1152, 81.3% walkable
[verify]     0 errors, 1 warning
```

**0 grounding misses across every server tile.** The ray is cast at all
576 Ã— 576 tiles, not only reachable ones, so this covers the seabed and the
mountain interiors as well as the playable basin.

### The one warning

```
GROUNDING_DISCONTINUITY: 73 adjacent tile pairs differ by more than 6 m
                         of surface height (expected at cliffs and under bridges)
```

Two documented causes, both intended:

1. **The eastern rim.** Most of the 73 pairs are at tile x = 575, where the
   clamped world boundary meets the sea shelf. That is a cliff falling into the
   water at the edge of the map, outside anywhere a player has business being.
2. **Under the seven crystal bridges.** A bridge deck owns its cells at deck
   height, so the tile at the end of a deck and the tile on the channel floor
   beside it differ by the height of the span. This is the deliberate
   overhead-deck case the guide describes.

### Warnings that were fixed rather than documented

These appeared during the build and were treated as defects:

| Warning | Count | Cause | Fix |
| --- | --- | --- | --- |
| `LANDMARK_BELOW_SURFACE` | 17 | `walk_surface=True` on `MeshGroup` placements renamed the container to `Walk_`, so every solid child inherited the prefix and the observatory dome and armillary sphere became walk surfaces | dropped the flag; the groups already mark their own decks with `add_walk` |
| `COLLISION_SURFACE_MISMATCH` | 7 â†’ 0 | bridge decks were placed by a no-op expression (`ground - ground + 6.5`), so every deck sat 0.2 m above the terrain with its arches buried | deck height is now set from the **banks** the roadway meets, and the collision footprint is a rotated rectangle rather than a circle |

Walk-surface node count fell from 86 to 24 as a result â€” the correct number is
the terrain classes plus the real decks.

## Collision binary

- `EWCG` version 1, 1152 Ã— 1152 at 0.5 m â€” both dimensions are positive
  multiples of six.
- 81.3% walkable.
- Height encoding `origin -2.2, step 0.2, range [1, 63]`, zero means blocked.
- **106,166 saturated cells (9.8% of walkable).** Everything else carries a real
  height. See `modeling-assumptions.md` for why this matters and how it compares
  to Amberwood.

## Server-side ELM

`../server-collision/amethyst_barrens.bin`, 341,112 bytes, 96 Ã— 96 tiles,
576 Ã— 576 height cells, 81.3% walkable. Loaded through **eloria-server's own**
`eloria.collision.load_elm_collision`:

```
server loaded: 576x576 cells
arrival (174,174): walkable=True elevation_byte=37   (5.2 m)
distinct height bytes: 52 (min 0 max 63)
can_step at arrival: True
```

`tests/test_nymara_collision_contract.py` passes with the new size and arrival
on `feature/amethyst-barrens-576m-server-map`.

## Determinism

Two builds run in independent processes:

```
IDENTICAL  world.glb      (19,520,164 bytes)
IDENTICAL  world.json     (55,539 bytes)
IDENTICAL  collision.bin  (1,327,120 bytes)
IDENTICAL  minimap.webp   (176,972 bytes)
DIFFERS    world.glb.validator.json
```

The validator report differs only in the two fields that describe the run
itself â€” the absolute `uri` of the file it validated and `validatedAt`. No
build output differs.

## What this report does not cover

A clean validator run says the package is well-formed and that the grounding
contract holds. It does not say the map looks right. For that, see
`comparison-report.md`, which lists the places where the build does not match
the concept.

Specifically **not** verified:

- End-to-end login, or play of any kind.
- The map running under `main.gd` as an actual game session. The client
  captures in `references/client-captures/` drive the real
  `WorldLoader.load_world()` and render on a GPU, but they are a capture
  harness with its own fixed lighting rig, not the game.
- Whether an actor walks correctly. Grounding is verified geometrically,
  offline, by reproducing the ray; no character was moved.
- Three place names (see `modeling-assumptions.md`).
