# Whitehorn Range validation report

What was checked, how, and — more importantly — what was not.

## Automated checks, all passing

| Check | Command | Result |
| --- | --- | --- |
| glTF 2.0 validity | `_toolkit/validate_gltf.py ../world.glb` | **0 errors, 0 warnings, 0 infos** |
| Runtime contract | `_toolkit/verify_runtime.py --package ..` | **0 errors**, 1 warning |
| Grounding | same | **331,776 tiles sampled, 0 misses (0.00%)** |
| Collision grid | same | 1152 x 1152 @ 0.5 m, 72.1% walkable, both dimensions multiples of six (1152 = 6 x 192) |
| Server tests | `pytest tests/` in `eloria-server` | 431 passed, 80 failed — **identical to the develop baseline with the change stashed**, so none are caused by this work |
| Nymara server tests specifically | `pytest tests/test_nymara_*.py tests/test_client_content_sync.py` | 21 passed |

The single `verify_runtime` warning is `GROUNDING_DISCONTINUITY`: 347 adjacent
tile pairs differ by more than 6 m of surface height. Those are the boundary rim
and the gorge walls. That is the documented cliff case the guide permits.

## Verified in the real client

This is the check the Amberwood build could not run, because that session had no
Godot binary. Godot 4.7.2 is available here and renders on the GPU, so the
package was loaded through the **shipped loader path**, not a reimplementation:

```
godot --path godot-client res://tools/region_client_check.tscn -- \
    --manifest res://../eloria-assets/.../whitehorn_range/world.json --step 6
```

The harness is the shared `_toolkit/region_client_check.gd`, written by the
Mirrorhold build; this region adopted it rather than keeping a second copy, and
contributed the `--check-sun` mode below. It calls `WorldLoader.load_world()`,
waits for physics, and casts the identical ray `main.gd:2250` casts in
`_place_actor_on_surface` — y = 400 down to y = -100 on
`NAVIGATION_SURFACE_LAYER`. Results:

```
[client-check] server grid 576x576, sampling every 6 tiles
[client-check] grounding: 9216 tiles sampled, 0 misses (0.00%)
[client-check] surface height range: -34.20 .. 149.55
[client-check] spawn { "id": "whitehorn-arrival", "manifestY": 17.59, "clientY": 17.587, "deltaMetres": 0.003 }
[client-check] spawn { "id": "whitehorn-temple",  "manifestY": 54.06, "clientY": 54.062, "deltaMetres": 0.002 }
[client-check] spawn { "id": "whitehorn-mine",    "manifestY": 49.66, "clientY": 49.645, "deltaMetres": 0.015 }
[client-check] PASS
```

So the engine agrees with `verify_runtime.py`: the GLB imports, the navigation
layer builds from the node-name prefixes, and every sampled tile and every
declared spawn grounds. Spawn heights agree with the manifest to 0.02 m.

### One loader warning, and the control that explains it

`WorldLoader` accumulates non-fatal findings on the manifest rather than
printing them. There is one:

```
[client-check] loader warnings=1
    warning: navigation polygons did not produce collision
```

Both this package and Amberwood's declare
`{"format": "surface-prefix-v1", "polygons": []}` — the polygon path is unused
by design and the navigation layer is built from node-name prefixes instead,
which is what the grounding then succeeds on. Running the same harness against
the committed Amberwood package as a control produces the identical warning and
also passes, so it is structural to the manifest format and not a finding
against this region.

### The sun is verified to point downward

`--check-sun=1` binds the manifest through the real `WorldEnvironmentBinder`
and reports the key light's actual travel vector:

```
[client-check] sun { "environmentBound": true,
                     "travelDirection": [0.382, -0.623, -0.683],
                     "lightsFromBelow": false, "energy": 1.05 }
```

`environment.sun.direction` is the direction the light **travels**, not where
the sun sits, so a positive Y lights the world from underneath. Nothing else in
the pipeline can catch this — the offline renderer uses the opposite convention
and a capture harness with its own neutral sky never reads the manifest at all.
Amberwood declares `[-0.46, 0.50, 0.73]` and is in exactly that state.

The full report is committed at `references/godot-client-check.json`.

## What is NOT verified

Stated plainly, because a clean validator report does not cover any of this.

1. **End-to-end play.** No server was run, no client logged in, no character
   walked this map. The grounding contract is verified by ray casts in both
   Python and Godot; actual movement, collision response, and map transitions
   are not.

2. **Appearance in the real client.** No client frame is committed for this
   region. The in-engine check runs headless, which has no renderer, and the
   earlier windowed frame was dropped when this region adopted the shared
   harness. The environment block is verified to bind and to light from above,
   but nobody has looked at this region rendered by the game with its own art
   direction. Every image in `references/` is from the offline rasteriser.

3. **Every other capture is an offline preview.** Everything in
   `references/captures/` other than the `90-` frame comes from the toolkit's C
   rasteriser (`_toolkit/native/libraster.so`), not from Godot. They are
   labelled that way on the comparison sheets. They are an art-direction tool,
   not client screenshots.

4. **The detail board could not be compared automatically.** The supplied
   `references/00-concept-detail-board.png` is truncated to 786,445 bytes and
   will not decode at all — `Image.open().load()` raises. Only Amberwood's and
   Sunmane's boards were ever re-supplied intact. The ten panels were worked
   from the board as shown in the authoring conversation, so the *build* follows
   it; but `references/comparisons/panel-comparison.webp` shows a placeholder on
   the concept side of every panel. Drop an intact board at that path and
   `make_comparison.py` regenerates a real sheet with no other change.

5. **Place names.** Every name is invented. See `modeling-assumptions.md` §12.

6. **Server map content.** The server change makes `whitehorn_range` a 96 x 96
   map with the arrival datum at (174, 174), matching Amberwood. The server
   still generates its own procedural heights; it does **not** consume
   `server-collision/whitehorn_range.bin`. The server's validator forbids blocked
   cells entirely (`if not heights or 0 in heights: raise`), and this region's
   exported ELM is 28% blocked, so the two cannot currently be the same file.
   Client-rendered walk surfaces and server collision are therefore *not*
   guaranteed to agree cell for cell. This is inherited from the Amberwood
   design, not introduced here, but it is a real gap and someone should decide
   whether the server should ingest the client ELM.

7. **Performance under load.** Triangle and byte counts are measured; frame rate
   is not. Nothing streams and nothing switches LOD.

8. **The `noise.stable_hash` overflow warning.** Every build prints
   `RuntimeWarning: overflow encountered in scalar multiply` from
   `_toolkit/amberwood/noise.py:17`. The wraparound is intentional and
   deterministic, and Amberwood builds through it identically, but it is
   untidy and nobody has silenced it.

## Reproducibility

The build is deterministic for a fixed seed. Two independent builds of Whitehorn
from identical source produced byte-identical `world.glb`, `world.json`,
`collision.bin` and `minimap.webp`, **and the committed package matches a fresh
build byte for byte** — so what is in this directory is exactly what `source/`
produces.

The same check on Amberwood (two consecutive builds, all five artefacts
identical) is what establishes that the toolkit itself is sound on this
machine.

Note for anyone repeating the production guide's TASK ZERO: **the committed
Amberwood artefacts are stale and a rebuild cannot match them.**
`amberwood/world.glb` was last written in `b169ed70`, which predates `626ee5ea`
— the commit that moved five seeds from salted `hash()` to `stable_hash()`.
Seeds changed; the package was never regenerated. A current build produces
31.55 MB / 535,709 triangles against the committed 28.97 MB / 534,697. The
meaningful determinism check is build-vs-build, not build-vs-committed.
