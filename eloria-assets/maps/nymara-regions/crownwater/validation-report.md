# Crownwater validation report

## glTF 2.0

`_toolkit/validate_gltf.py` implements the structural and semantic checks that
matter for Godot's `GLTFDocument` import path: chunk structure, accessor bounds
against buffer views, declared min/max against actual data, index range against
vertex count, unit-length normals, tangent handedness, material and texture
references, embedded image signatures, node parenting and cycles, scene roots,
and node-name uniqueness.

| Package | Result |
| --- | --- |
| `world.glb` | **0 errors, 0 warnings**, 3 infos (`world.glb.validator.json`) |
| `world-lod2.glb` | **0 errors, 0 warnings**, 3 infos (`world-lod2.glb.validator.json`) |

No glTF extensions are used or declared required; every buffer and image is
embedded; triangles only.

## Runtime contract

`_toolkit/verify_runtime.py` reproduces what the client does at load time rather
than trusting that it will work. It rebuilds the navigation surface exactly as
`WorldLoader` does, casts the same downward ray `Main._place_actor_on_surface`
uses at the centre of every reachable server tile, and cross-checks the
collision grid against that surface.

| Check | Result |
| --- | --- |
| Walk-surface nodes / triangles | 205 nodes, 206,698 triangles |
| Server tiles sampled | **331,776** - every tile of the 576-cell map |
| **Grounding-ray misses** | **0** |
| Spawn points grounded | 3 / 3 |
| Collision binary | `EWCG` v1, 1152 x 1152, dimensions multiples of six, payload size exact |
| Elevated decks owning their cells | 84 |
| Errors | **0** |
| Warnings | 2, both documented below |

### The two warnings

1. **`GROUNDING_DISCONTINUITY`, 224 adjacent tile pairs differ by more than 6 m.**
   Expected and deliberate. Every one is a causeway deck beside open water: the
   deck owns its cells at 4-8 m and the lagoon floor beside it is at -5 to -9.
   This is exactly the "deliberate overhead deck" case the check exists to
   surface. It is not a walkability defect - the decks are reached by their
   landings, not by stepping off the side.

2. **`COLLISION_SURFACE_MISMATCH`, 5 of ~4,000 sampled walkable cells.**
   All five encode *lower* than the rendered surface, at deck and quay edges,
   where the half-metre collision cell straddles a boundary between a deck and
   the ground beside it. The six-bit height field cannot express the step. The
   grid stays authoritative for walkability and the loader takes elevation from
   the rendered surface, so the practical effect is nil. Amberwood documents the
   same class of warning at a comparable rate.

## In-client verification

**This is the part Amberwood could not do.** A Godot 4.7.2 binary and a GPU were
available in this session, so the package was loaded through the client's own
code path rather than only through the offline validators.

`godot-client/tests/integration/rendered_crownwater.gd` loads `world.json`
through the real `WorldLoader`, binds the manifest environment through the real
`WorldEnvironmentBinder`, and captures all 23 framings.

```
world_load stage=manifest_valid asset=crownwater
world_load stage=glb_imported
world_load stage=scene_attached node=/root/.../ImportedWorld_crownwater
world_load stage=static_batching batches=29 instances=470
rendered Crownwater: PASS
```

| Check | Result |
| --- | --- |
| GLB imports through `WorldLoader` | pass |
| Manifest environment binds | pass |
| Captures at reference dimensions | 23 / 23 |
| Captures containing scene detail (>= 64 distinct colours) | 23 / 23 |
| All ten detail-board panels have a framing | pass |

Everything in `references/captures/` is therefore a **real client frame**, and
is labelled as such on the comparison sheets. Renderer: OpenGL 3.3 compatibility
on an RTX 5080.

## A defect this found in the shared manifest convention

`WorldEnvironmentBinder` aims the sun with
`sun.look_at_from_position(Vector3.ZERO, direction)`, and a `DirectionalLight3D`
emits along its local -Z. **`environment.sun.direction` is therefore the
direction the light travels, not the direction of the sun in the sky.** A `+Y`
component lights the world from underneath.

Crownwater's first in-client capture came back lit from below and reading as
night. Crownwater now declares `[-0.30, -0.84, 0.45]`.

**Amberwood's `world.json` declares `[-0.46, 0.50, 0.73]`** and Four Gates
declares a positive-Y direction too. Neither has been rendered through this path,
so neither has been caught. This is not Crownwater's to fix, but any region
relying on that convention should expect the same result.

## What this report does *not* cover

State it plainly rather than letting the numbers above imply more than they do.

- **End-to-end login and live server play.** The map was never loaded by a
  running `eloria-server`. The 96x96 ELM is written and its header verified, but
  no server has read it.
- **The server-side change is unmerged.** The generator and contract-test edits
  are on a branch; the contract test was run locally and passes, but it has not
  been through CI.
- **Every place name.** No authoritative written region description or server
  name data was available. All names are placeholders.
- **Panel-level visual fidelity is judged by eye, not measured.** An intact
  detail board was supplied and the ten panels are now a genuine side-by-side in
  `panel-comparison.webp`, but "close" and "partial" in `comparison-report.md`
  are judgements.
- **Performance under load.** Triangle and byte counts are measured; frame rate
  with actors, NPCs and effects present is not.
- **Interiors.** Crownwater declares no interior portals. The cathedral,
  campanile and pavilions are exterior shells.
- **Water shading.** The GLB ships a flat lit plane with a turquoise texture.
  Depth-tinting and caustics are declared in `environment.water` as presentation
  settings for whoever writes the shader; they are not implemented.
