> Historical report: the September 2026 circulation pass is documented in
> [layout-review.md](layout-review.md). Its measurements supersede this report.

# Ssarathi Ruins validation report

Everything below is re-measured on the shipped package.

## glTF 2.0

`_toolkit/validate_gltf.py` implements the structural and semantic checks that
matter for Godot's `GLTFDocument` import path — chunk structure, accessor bounds
against buffer views, declared min/max against actual data, index range against
vertex count, unit-length normals, tangent handedness, material and texture
references, embedded image signatures, node parenting and cycles, scene roots,
and node-name uniqueness. It was written for this project because the Khronos
`gltf-validator` binary cannot be fetched in the build environment; run against
the repository's own `four-gates-city.glb` it agrees with the committed Khronos
report.

| File | Result |
| --- | --- |
| `world.glb` | **0 errors, 0 warnings** (1 info) |
| `world-lod2.glb` | **0 errors, 0 warnings** (2 infos) |

Both use no glTF extensions, declare none as required, embed every buffer and
image, and use triangles only.

## Runtime contract, offline

`_toolkit/verify_runtime.py` reproduces what the client does at load time rather
than trusting that it will work: it rebuilds the navigation surface exactly as
`WorldLoader` does, casts the same downward ray `Main._place_actor_on_surface`
uses at the centre of every reachable server tile, and cross-checks the
collision grid against that surface.

| Check | Result |
| --- | --- |
| Walk-surface nodes / triangles | 29 nodes, 206,578 triangles |
| Server tiles sampled | **331,776** — every reachable tile of the 576-cell map |
| Grounding-ray misses | **0** |
| Spawn points grounded | 3 / 3 |
| Collision binary | `EWCG` v1, 1152 x 1152, dimensions multiples of six, payload size exact |
| Errors | **0** |
| Warnings | 3 |

## Runtime contract, in the real client

This is the check the production guide lists as unverifiable and Amberwood's
report lists as outstanding. It ran here.

Godot **4.7.2-stable**, headless, loading `world.json` through the project's own
`WorldLoader` — the same code path the game uses — building collision and
navigation from the manifest, then casting `main.gd`'s grounding ray
(y = 400 down to y = −100, on `NAVIGATION_SURFACE_LAYER`) against the physics
world:

| Check | Result |
| --- | --- |
| Grounding-ray misses | **0** across 20,736 sampled tiles (every 4th) |
| Surface height range | −9.44 m .. 56.81 m |
| Spawns | 3 / 3, each within **0.06 m** of its manifest height |
| Loader warnings | 1 — `navigation polygons did not produce collision` |
| Verdict | **pass** |

Full report in `client-check-report.json`.

The single loader warning is expected and is not specific to this region:
`navigation.navmesh.polygons` is an empty array in every Nymara package, because
navigation is built from the `surfaceNodePrefixes` contract rather than from
authored polygons. Amberwood produces the same warning.

The offline and in-engine checks therefore agree, which is what makes the
offline one trustworthy for this package.

## The three warnings, and why each is expected

* **`GROUNDING_DISCONTINUITY` — 227 adjacent tile pairs differ by more than 6 m.**
  These are the temple precinct's three terrace faces, the jungle-clad valley
  walls, the stela knoll and the seven channel bridges, which own their
  footprint at deck height over water 6.4 m below. All are deliberate; none is
  a hole.

* **`LANDMARK_BELOW_SURFACE` for `great-temple` — 35.32 m below the surface.**
  The landmark anchor is the temple's *base*, at the centre of its footprint,
  and 35 m of ziggurat stands on top of it. That is the intended position: a
  landmark marks where you go, not where the roof is. Amberwood carries the
  identical warning for `great-tree`.

* **`LANDMARK_FLOATING` for `east-falls` — 22.23 m above the walk surface.**
  A waterfall's landmark is its lip, which is 22 m up the valley wall. The same
  is true of `north-falls`, which sits just under the 3 m reporting threshold's
  companion check.

## Determinism

The build is seeded throughout and name-derived seeds use `noise.stable_hash()`,
never the built-in `hash()`. Verified by building twice from a cleared texture
cache in separate interpreter runs: `world.glb`, `world-lod2.glb`,
`collision.bin`, `minimap.webp` and `world.json` are all **byte-identical**.

## What has **not** been verified

State these plainly rather than letting the table above imply more than it
covers.

1. **End-to-end login and movement.** No server was started against this map, so
   click-to-move, WASD, camera behaviour, portal transitions, the tab map and
   coordinate reporting are unverified against the live protocol. The grounding
   contract they depend on is verified twice over, offline and in-engine.

2. **The server does not load this region's ELM.**
   `../server-collision/ssarathi_ruins.bin` is regenerated at 96x96 with real
   elevation, but the server still generates its own procedural heights;
   `validate_generated_map` rejects maps containing blocked cells and this one
   is 58% blocked. The server branch makes the two maps agree on size and datum,
   which is what the client needs, and nothing more. Same position as Whitehorn
   Range and Crownwater.

3. **Frame rate, draw calls and GPU memory.** Real client frames exist but no
   profiling session was run. The loader batches this package into 41
   `MultiMeshInstance3D` groups; that number, not the triangle count, is the one
   to check first.

4. **Every place name.** No authoritative written Ssarathi region description
   exists in the repository, so all fourteen landmark names, the eight
   interactive names and the thirteen NPC role names are invented placeholders.
   See `modeling-assumptions.md` item 12.

5. **Whether the ten panels are matched, as opposed to addressed.** Every panel
   has a corresponding built subject and a comparison capture, and the
   comparison sheets are the evidence. `comparison-report.md` states where they
   fall short; a clean validator report says nothing about that.

6. **The two toolkit changes this region made** were exercised only by this
   region. `capture_views.py` gained a region-materials hook and a `FIXED_VIEWS`
   opt-out, and `godot_capture.gd` gained `--environment=manifest`. All three
   are additive and default to the previous behaviour, so no other region's
   output changes — but no other region was rebuilt to confirm that.

## Provenance

Every mesh and every texel in this package is generated by the committed source.
No imported models, no sampled or traced textures, no third-party assets.
