# Verdant Stair validation report

Current layout measurements are in [the 2026-09-07 review](layout-review.md).
The measurements below record the earlier production pass.

What was measured, how, and — at the end — what was **not** verified. A clean
validator report covers structure, not whether the map looks right; the two
sections are kept apart on purpose.

## glTF 2.0

`_toolkit/validate_gltf.py` implements the structural and semantic checks that
matter for Godot's `GLTFDocument` import path: chunk structure, accessor bounds
against buffer views, declared min/max against actual data, index range against
vertex count, unit-length normals, tangent handedness, material and texture
references, embedded image signatures, node parenting and cycles, scene roots,
and node-name uniqueness. It was written for this project because the Khronos
`gltf-validator` binary cannot be fetched in the build environment; run against
the repository's own `four-gates-city.glb` it agrees with the committed Khronos
report.

Result for `world.glb`: **0 errors, 0 warnings, 0 infos**
(`world.glb.validator.json`).
Result for `world-lod2.glb`: **0 errors, 0 warnings**
(`world-lod2.glb.validator.json`).

The package uses no glTF extensions, declares none as required, embeds every
buffer and image, and uses triangles only.

## Runtime contract, offline

`_toolkit/verify_runtime.py` reproduces what the client does at load time
rather than trusting that it will work:

* It rebuilds the navigation surface exactly as `WorldLoader` does — every mesh
  node whose name begins with a `navigation.surfaceNodePrefixes` entry, with
  accumulated node transforms.
* It casts the same downward ray `Main._place_actor_on_surface` uses, from
  y = 400 to y = −100, at the centre of **all 331,776 reachable server tiles**.
* It cross-checks the collision grid's encoded heights against that surface.

Result: **0 errors. 0 grounding misses across all 331,776 tiles.**

One warning, expected and deliberate:

| Warning | Count | Why it is expected |
| --- | ---: | --- |
| `GROUNDING_DISCONTINUITY` | 1,412 tile pairs | Adjacent tiles differing by more than 6 m of surface height. This region is a staircase of eight terraces joined by 7–28 m cliff risers; a discontinuity at every riser is the whole design. The check exists to catch *unintended* steps, and there are none away from the risers and the gorges. |


Five warnings that appeared during development and were **fixed rather than
documented away**, because each was a real defect:

* `LANDMARK_BELOW_SURFACE` on the aqueduct — the arcade was sized from its
  abutments, which both stand on the terrace, so it was built 8 m tall from the
  terrace level and ended up 7.6 m proud of the deck it carries. Sized from the
  deepest ground along the span now.
* `LANDMARK_BELOW_SURFACE` on two stair landmarks — recorded at the terrace
  below rather than on the graded route that climbs the riser.
* `LANDMARK_FLOATING` on the cenote and the root crossing — the cenote's marker
  hung 18 m over the water; it now sits at the head of the stair where a player
  stands. The root crossing was a false positive that disappeared once the
  landmark entries used `type` rather than `kind`, which is the key the check's
  own exemption list reads.
* `LANDMARK_BELOW_SURFACE` on the two NPC premises — a terrace house has a
  verandah deck two and a half metres up, and the marker sat at the building's
  centre, under its own floor. Moved onto the ground in front of the door.
* `COLLISION_SURFACE_MISMATCH` on two cells — both under scattered terrace-edge
  stair flights that were cut for a separate reason (see `change-log.md`); the
  warning went with them.

## Runtime contract, in Godot

The production guide assumes no Godot binary is available. One is: **Godot
4.7.2-stable**, with a Vulkan device, so this region's runtime contract was
also measured *inside the engine* rather than only reproduced offline.

`_toolkit/region_client_check.gd` loads `world.glb` through the project's own
`WorldLoader`, rebuilds collision and navigation from the manifest, and casts
the grounding ray on a sampled grid. Its report is `client-check-report.json`.

Result: **pass**.

| Measure | Value |
| --- | --- |
| Engine | Godot 4.7.2-stable (official), headless |
| Tiles sampled | 82,944 (every 2nd server tile) |
| **Grounding misses** | **0** |
| Surface height range | −21.49 m to 128.40 m |
| Spawn `default` | manifest 24.59 m, client 24.54 m — 0.05 m |
| Spawn `west-quay` | manifest 7.05 m, client 6.999 m — 0.051 m |
| Spawn `temple-court` | manifest 98.25 m, client 98.199 m — 0.051 m |

The 0.05 m deltas are the manifest's deliberate 5 cm lift above the surface, so
the engine is agreeing with the offline check to within a rounding error.

`default` reads 24.59 rather than the 24.05 an earlier build of this branch
reported, and the difference is the point: it stands on the waygate's platform,
not on the ground under it. Both numbers passed this table. Agreement between
the manifest and the client is only worth something when the two derive the
height by different routes — see change log item 13.

One loader warning, `navigation polygons did not produce collision`: the
manifest declares `navmesh.format = "surface-prefix-v1"` with an empty polygon
list, because collision in this package comes from the node-name prefixes, not
from baked polygons. Amberwood's client check reports the same line.

A note on how this was run: a fresh git worktree has no `.godot` import cache,
so the project's `class_name` globals — `WorldLoader`, `CoordinateAdapter`,
`WorldEnvironmentBinder` — are not registered and the script fails to parse.
Copying `global_script_class_cache.cfg` from an imported checkout is enough;
a full `--import` is not needed.

## Manifest

`world.json` is complete against `godot-client/schemas/world-manifest-1.schema.json`:
bounds, playable bounds, coordinate transform, spawn points, collision
declaration with its height encoding, navigation prefixes and notes, terraces,
landmarks, interactives, NPC and creature markers, harvestables, portals,
roads, water bodies, streams, gorges, environment, minimap transform,
performance, sources, provenance and build notes.

`collision.bin` is `EWCG` version 1, 1152 × 1152 cells at 0.5 m — both
dimensions positive multiples of six — covering the 576 m server footprint.
Rows are indexed by server tile Y, so row 0 is the +Z southern edge; the
cell-to-surface cross-check in `verify_runtime.py` is what catches that being
written the other way round, and it passes.

The minimap is rendered from the final geometry by the build, not drawn.

## Provenance

Every mesh and every texel is generated by `_toolkit/amberwood/*` and this
region's `source/`. No model, texture or asset pack is imported; no image is
sampled or traced. The build is seeded and deterministic.

## The server map — the real open gap

`../server-collision/verdant_stair.bin` is regenerated here at 96 × 96 tiles with
real elevation and walkability, replacing the flat 32 × 32 placeholder.

**The server does not read it.** `eloria-server/tools/generate_nymara_maps.py`
generates its own procedural heights, and its `validate_generated_map` rejects
any ELM containing a blocked cell:

```python
if not heights or 0 in heights:
    raise RuntimeError(f"generated collision contains blocked cells: {path}")
```

Verdant Stair's honest ELM is **20.4% blocked** — it has cliffs, four gorges, a
cenote and open water — so it cannot be loaded through that path today. There
is a second obstacle behind the first: the same validator requires the arrival
cell to read exactly 11, and this region's arrival sits at 24 m, which the
six-bit height field clamps to 63. Both checks assume a map the server itself
generated. The
server change on `feature/verdant-stair-576m-server-map` therefore does what
Amberwood, Mirrorhold, Amethyst Barrens, Whitehorn Range and Crownwater all
did: it grows the map to 96 × 96, moves the arrival datum to (174, 174), and
rescales the portal endpoints, while the server keeps generating its own
heights.

**Client walk surfaces and server collision are therefore not guaranteed to
agree cell for cell.** This is inherited from Amberwood rather than introduced
here, and Whitehorn's author recorded the same gap, but it is real and it is
the single thing about this region most worth a decision. Closing it needs a
server-side change — relaxing `validate_generated_map` for regions that ship a
real ELM, and adding an import path — which was explicitly out of scope for
this pass.

## Determinism

The build is seeded. Rebuilding the package from a clean run reproduces
`world.glb`, `world-lod2.glb`, `collision.bin` and the exported ELM
byte-for-byte; the checksums are compared as part of the final pass rather than
asserted. `source/` is committed and the runtime never depends on rerunning it.

## The insides

`../interiors/verdant_stair_insides/` is four interiors on one map with
blackspace between them, reached from four doors on this region's surface. Its
own results, and the three defects building it exposed in already-shipped code,
are in `../interiors/VERDANT_STAIR_INTERIORS.md`. One of those defects is in
this package and is only worked around, not fixed — see item 2 below.

It is judged in-engine by develop's own criterion — zero grounding misses on
cells `collision.bin` marks walkable — and meets it exactly, with all 15,283
misses falling on blocked cells. An earlier version of this branch carried a
weaker rule of my own for the same problem; it is gone, and this branch no
longer modifies the shared check at all. See items 12 and 18 of the change log.

## What was not verified

Stated plainly, because a clean report above should not be read as covering
more than it does.

1. **End-to-end login and play.** The map was never loaded by a running client
   connected to a running server. No character has walked it.
2. **The server map.** The regenerated ELM has not been loaded server-side,
   for the reason above. The 19 affected server tests pass; that is not the
   same as the map being served.
3. **Performance on real hardware.** 3.54 M instanced triangles is measured
   from the GLB, not from a frame time. The Godot capture pass renders every
   view at 1600x1000 without complaint, which is evidence the package loads and
   draws — not that it holds a frame rate in play. Nothing in the current
   loader selects between `world.glb` and `world-lod2.glb`, and nothing
   streams.
4. **Place names for the terrain.** The NPCs, creatures, harvestables and
   interactives are the server's own. The names of the *places* — the Green
   Temple, the Grand Stair, the Green Cenote, the terraces themselves — are
   invented to fit the concept art, because no authoritative written
   description of the region was available. Expect them to be replaced.
5. **The `qa/regions/verdant-stair/` brief's own validation script.** The QA
   README documents `generate_all_assets.py` / `validate_generated_assets.py`
   against the *placeholder* generator's plan, which this package replaces.
   Those scripts were not run against it.
6. **Frame rate.** The in-engine check runs headless; it proves the map loads
   and grounds in the real engine, not that it renders at a playable rate.
7. **`collision.bin` is wrong over the cenote.** `build_collision` stamps every
   elevated walk surface as a filled disc over its own footprint. That is right
   for a bridge deck and wrong for a ring, and the cenote's spiral stair winds
   around an open shaft — so the grid marks a disc of walkable cells across the
   top of an eighteen-metre hole, at rim height. Spawns and portals no longer
   read their height from it, but the grid itself still says this. The
   cell-to-surface cross-check in `verify_runtime` did not surface it. Fixing it
   properly means rasterising walk triangles the way the interiors' own
   `build_collision` already does.
