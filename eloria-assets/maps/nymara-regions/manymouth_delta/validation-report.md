# Manymouth Delta validation report

## glTF 2.0

`_toolkit/validate_gltf.py` implements the structural and semantic checks that
matter for Godot's `GLTFDocument` import path — chunk structure, accessor bounds
against buffer views, declared min/max against actual data, index range against
vertex count, unit-length normals, tangent handedness, material and texture
references, embedded image signatures, node parenting and cycles, scene roots,
and node-name uniqueness.

| Package | Errors | Warnings |
| --- | --- | --- |
| `world.glb` | **0** | **0** |
| `world-lod2.glb` | **0** | **0** |

The package uses no glTF extensions, declares none as required, embeds every
buffer and image, and uses triangles only. Reports are committed as
`world.glb.validator.json` and `world-lod2.glb.validator.json`.

## Runtime contract, offline

`_toolkit/verify_runtime.py` reproduces what the client does at load time rather
than trusting that it will work: it rebuilds the navigation surface exactly as
`WorldLoader` does, casts the same downward ray `Main._place_actor_on_surface`
uses at the centre of every reachable server tile, and cross-checks the collision
grid's encoded heights against that surface.

| Check | Result |
| --- | --- |
| Walk-surface nodes / triangles | 205 nodes, 254,558 triangles |
| Server tiles sampled | **331,776** — every reachable tile of the 576-cell map |
| Grounding-ray misses | **0** |
| Spawn points grounded | 3 / 3 |
| Collision binary | `EWCG` v1, 1152 × 1152, dimensions multiples of six, payload size exact |
| Errors | **0** |
| Warnings | 4 |

### The four warnings, and why each stands

* **`GROUNDING_DISCONTINUITY` — 241 adjacent tile pairs differ by more than 6 m.**
  The temple mount (four 3.4 m stages plus its stair), the rock headland the
  labyrinth runs into, and the edges of elevated decks, which own their footprint
  by design. The largest, 15.2 m, is the temple's west face. Expected.
* **`SPAWN_NEIGHBOURHOOD_ROUGH` — `temple-quay`.** The quay bar is small and its
  terrace edge drops 2.2 m to the water within 1.2 m of the spawn. The spawn
  itself is grounded to within 0.05 m and the ground under the actor is flat;
  what the check is measuring is the bar's edge, not the standing surface.
* **`LANDMARK_BELOW_SURFACE` — `moot-hall`, 2.71 m.** The landmark anchor is the
  hall's foot on the walkway; its own first-tier gallery floor is a walk surface
  2.7 m above. Amberwood documents the identical shape for `great-tree`.
* **`COLLISION_SURFACE_MISMATCH` — 8 of ~4,000 sampled cells.** All on
  deck-to-ground transitions, where `build_collision` claims a rotated deck's
  bounding rectangle at a single height while the rendered geometry ramps (the
  landing stairs) or stops short of the rectangle's corners. 0.2% of sampled
  cells. Amberwood shipped with 1 such cell and Crownwater with a comparable
  handful; this region has a far denser deck network.

## The same contract, in-engine

`_toolkit/region_client_check.gd` loads the package with the project's own
`WorldLoader.load_world()` and casts `main.gd`'s grounding ray against the real
physics world — the offline check run the other way round.

```
engine              4.7.2-stable (official)
static batching     95 batches, 3673 instances
tiles sampled       20736 (every 4th server tile in each axis)
grounding misses    0
surface height      -24.59 .. 28.47
spawn default       manifest 1.33, client 1.277, delta 0.053 m
spawn arch-stair    manifest 1.30, client 1.250, delta 0.050 m
spawn temple-quay   manifest 1.10, client 1.050, delta 0.050 m
PASS
```

Committed as `client-check-report.json`. The single loader warning,
`navigation polygons did not produce collision`, is structural: `navigation.navmesh`
is `surface-prefix-v1` with an empty `polygons` list because navigation comes
from the surface prefixes. Amberwood, Mirrorhold and Crownwater produce the same
warning.

Note that this check needs the project's global class cache. In a freshly
created worktree `.godot/` does not exist, `class_name` identifiers such as
`WorldLoader` and `CoordinateAdapter` do not resolve, and the script fails to
parse with what looks like a code error. Run
`Godot --headless --path . --import` once first. A plain `--quit-after` run does
not build the cache.

## Captures: which are real client frames

* **`references/godot-captures/`** — **real client frames.** 27 views rendered by
  Godot 4.7.2 on an NVIDIA RTX 5080 through Vulkan, loading `world.glb` through
  `GLTFDocument` exactly as a runtime package. `index.json` beside them records
  the camera for each and stamps the engine version.
* **`references/captures/`** — the **offline preview renderer**
  (`_toolkit/native/`, software, CPU). Same camera table, same material table,
  but it is not Godot.

The comparison sheets in `references/comparisons/` are built from the **real
client frames** and are labelled `real Godot frame` on each row.

**Do not judge water from the offline set.** `native/raster.c` has no BLEND path:
it handles `alpha_mode == 1` (MASK) and draws everything else opaque. Every
blended material in every region renders fully opaque there. This is a
pre-existing limitation of the previewer, it affects Crownwater and Mirrorhold
equally, and it could not be fixed here because there is no C compiler on this
machine (see below).

## What has **not** been verified

1. **End-to-end login and movement.** No server was started. Click-to-move, WASD,
   camera, portals, the tab map and coordinate reporting are unverified against
   the live protocol. The grounding contract they depend on is verified twice,
   offline and in-engine.
2. **The server map in a running server.** `tools/generate_nymara_maps.py`
   produces the 96×96 map and the Nymara test modules pass, but no server
   process was run against it.
3. **Lore and naming.** No written region description was available. Every place
   name in `world.json` is an invented placeholder.
4. **`world-lod2.glb` in the client.** It validates and loads through the same
   path, but nothing selects it, so it has never been rendered by Godot.
5. **Anything about the Flooded Labyrinth interior.** It remains a flat 32×32
   placeholder. This package ships only its threshold.

## Reproducibility

The build is deterministic and seeded. `source/` is committed complete;
`build_manymouth_delta.py` regenerates `world.glb`, `world-lod2.glb`,
`world.json`, `collision.bin`, `minimap.webp`, `camera-views.json`,
`performance.json` and both validator reports from nothing but the toolkit and
this region's five source modules. Runtime startup never depends on rerunning it.

**Demonstrated, not just asserted.** Merging `develop` into this branch and
rebuilding produced `world.glb`, `world-lod2.glb`, `collision.bin` and
`minimap.webp` **byte-for-byte identical** to the committed artefacts - a second
build, hours later, against a toolkit that had moved on underneath it. Only
`world.json`, `performance.json` and the two validator reports differ, and only
in fields that are meant to move: the validators' `validatedAt` timestamps, and
`performance.embeddedTextureBytes` / `textureMemoryBytesUncompressed`.

Those last two are worth a note, because they are misleading and not only here.
They sum **every generated texture set**, not the ones the package actually
embeds, so they grew from 20,986,319 to 24,555,232 bytes when `develop` brought
in three more regions' recipes - while `world.glb` did not change by one byte.
The pinned set is what ships; that stat measures the workshop, not the package.
It is inherited from the shared build shape and every region reports it the same
way.

## Environment limits that shaped this build

* **No C compiler.** `gcc`, `cc`, `clang` and MSVC are all absent; only mingw
  runtime DLLs are on this machine. `_toolkit/native/libraster.so` could be
  *used* (it is already a Windows PE and is not committed, per `.gitignore`) but
  not rebuilt. Two rasteriser defects found during this work — the missing BLEND
  path, and an out-of-bounds read — therefore could not be fixed in C. The
  second was worked around in Python; see `change-log.md`.
* **A GPU and a Godot 4.7.2 binary were available**, which the production guide
  assumes will not be the case. That is why this region has real client frames
  and an in-engine grounding check, and why the guide's advice to label every
  capture as offline does not apply to `godot-captures/`.
