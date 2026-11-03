# Actor geometry LODs

Package-time geometry for actor glTFs: masked lining faces, LOD index chains and
optional vertex compaction, delivered as per-file sidecars and attached to the
runtime parse. Vertex attributes are never rewritten (compaction only drops whole
runs of unused vertices), so face sculpt, body refinement, cover cuts, cape fits
and the RL head body cut keep reading the arrays they read today.

Status: the shared format (`src/actors/actor_geometry_format.gd`) and the runtime
applier (`src/actors/actor_geometry.gd`) exist and are tested
(`tests/test_actor_geometry.gd`), and so does the offline tool that decides which
lining triangles are hidden (`eloria-assets/tools/lining_visibility.py`, below).
Nothing calls the applier yet: the call in the actor parse
(`GlbSceneCache._build_raw`) and the cook arrive in later steps, so the game
draws exactly what it drew before.

## Sidecar

One file per actor glTF, content-addressed as `blobs/<sha256>.rlgeo`: the 8-byte
magic `RLGEO001`, the decoded size as a little-endian u64, then
`zstd(var_to_bytes(Dictionary))`. It is read with `bytes_to_var`, never with
objects.

```
{schema: 1, policy: "rl-actor-geometry-v1", engine: "4.7.2.stable.official.ed1daf0bf",
 source: {path: "res://assets/actors/native/...glb", sha256, bytes},
 meshes: [{name, surfaces: [{vertex_count, index_count, index_digest,
   base?: PackedInt32Array, compact_runs?: PackedInt32Array,
   lods: [[edge_length, PackedInt32Array], ...]}]}]}
```

- `meshes` follows `GLTFState.get_meshes()` order and names; every surface of
  every mesh is listed, changed or not.
- `index_digest` is the SHA-256 of the parsed index buffer
  (`PackedInt32Array.to_byte_array()`), as `GLTFDocument` produced it with the
  project's glTF extensions registered.
- `base` replaces the index buffer (for linings: the faces the visibility masks
  keep). `compact_runs` lists `[start, length]` pairs of original vertices to
  keep, ascending and disjoint; with it, `base` and the LODs index the compacted
  order. Compaction needs a `base`.
- LOD edge lengths ascend strictly and each level has fewer indices than the one
  before it (and than the base). Godot skips a level that is not smaller than
  the base.
- Index ranges are checked against the (compacted) vertex count.
- Unknown surface keys are rejected, not ignored: a runtime that predates a
  later stage (for example vertex-colour lining replacement) never half-applies
  a sidecar.

## Catalogue and roots

`catalog.json` beside `blobs/`:

```
{schema: 1, policy, engine, source_check: "file" | "parsed",
 entries: {"res://assets/actors/native/...glb": {source_sha256, source_bytes,
   sidecar: "blobs/<sidecar_sha256>.rlgeo", sidecar_sha256, sidecar_bytes, inputs?}}}
```

Keys are `res://` paths under `res://assets/actors/native/`, except
`rl_heads/` (authored LODs). Roots, first match wins:

1. `RABBITLANDS_ACTOR_GEOMETRY_ROOT` (tests, measuring a cook);
2. an editor checkout: `<client repo>/.local/actor-geometry/rl-actor-geometry-v1/`;
3. the installed release root (added with release packaging).

The catalogue is read once per process (`ActorGeometry.warm()` reads it early;
`reset()` forgets it). Its entries only point at sidecars; every sidecar is
hashed as it is consumed and bound to the parse it changes.

## Runtime

`ActorGeometry.apply(state, path[, source_sha256])` runs after the glTF parse and
before `generate_scene()`. It checks, in order, and on any failure leaves the
parse untouched:

| Reason | Check |
| --- | --- |
| `not_listed` | the catalogue lists the file (not logged: routine) |
| `catalog` | the entry is well formed and agrees with the sidecar's `source` (path, SHA-256 and size) |
| `sidecar_missing`, `sidecar_digest` | the sidecar exists, with the catalogued size and SHA-256 |
| `decode` | magic, size, zstd and structure |
| `engine` | catalogue and sidecar were cooked by this exact engine build |
| `source` | with `source_check` "file" (the default), the actor file's SHA-256 (or the caller's hash of the bytes it parsed) matches |
| `shape` | mesh count, mesh names and surface counts |
| `surface` | vertex and index counts of every surface; for changed surfaces the primitive type, the index digest and an even split of every per-vertex array |

Each changed `ImporterMesh` is rebuilt (clear, blend shape names and mode,
lightmap hint, then every surface with its arrays, blend shapes, LODs, material,
name and flags). If the engine refused a surface, every mesh rebuilt so far gets
its parsed surfaces back (`rebuild`). Mismatches log one warning per file;
`ActorGeometry.snapshot()` returns the counters (statuses, reasons, surfaces
rebuilt, LOD levels, apply time).

`source_check` "parsed" skips the file hash: meant for an installed root that was
verified together with the actor files. "file" protects a developer root from
stale sidecars after an actor file changes without changing its index buffer
(a refit that keeps topology). For a text `.gltf` the file hash covers the JSON
only; its `.bin` buffers are bound by the parsed index digests alone.

Threads: CPU only, no RenderingServer or scene calls; the memoized catalogue and
counters sit behind one mutex. A creature parse on a worker applies the same way.
Do not join a parsing worker from a blocked main thread (see `GlbSceneCache`
"Threads"); the test polls it, like `ActorResourceWarmup`.

Switch: `RABBITLANDS_ACTOR_GEOMETRY=sidecar` (default), `off`, or `generate`
(editor binary only: `ImporterMesh.generate_lods` at parse time, for comparison;
an exported build treats it as `sidecar`). Only these three names count; any
other value is the default. `ActorGeometry.resolve_mode` and
`HardwareTier.resolve_actor_geometry` (the startup record) resolve it alike,
which the test checks.

Every process on the editor binary reads the dev root, headless tests
included. Once the actor parse calls the applier, a worktree with a cooked dev
root draws (and tests) actors with sidecars; set
`RABBITLANDS_ACTOR_GEOMETRY=off` to compare against the plain parse.

## Lining visibility masks

`eloria-assets/tools/lining_visibility.py` decides which triangles of each
`Generated*` lining (`GeneratedArmorBacking`, `GeneratedLegBacking[WithBoots]`,
`GeneratedBootBacking[WithLegs]`) no camera can see; the cook's lining stage
turns a mask's `keep` into that surface's `base`. It is an offline tool: it
reads the garment GLBs and writes mask files, and changes no asset.

```
python eloria-assets/tools/lining_visibility.py masks --all            # or GLBs, or --sample review
python eloria-assets/tools/lining_visibility.py finalise --all --margin 0.02 --margin-rule surface
python eloria-assets/tools/lining_visibility.py review --sample review --sheets
python eloria-assets/tools/lining_visibility.py check <mask.json> [<garment.glb>] [--rewritten]
```

Method (`lining_visibility_blender.py` runs in background Blender, at most four
processes at a time):

- Poses: the bind pose, then 43 more (pose set v1 in the tool): idle, walk and
  run at quarter cycles, the three sword swings and their ends, casts, channel,
  defend, arms raised, bow hold, shield, chop, jump, meditate (the client's sit),
  chair sit, stand, death, eight emotes, and four mounted straddles rebuilt from
  `data/mounts/*.json` with the rider seat solver's two-bone IK (narrow horse to
  wide tortoise). Library clips are retargeted with the shared posekit, as the
  design fit does. Posed vertices come from linear blend skinning of the glTF
  data itself (checked against Blender's own deformation to 1e-6 m), so triangle
  `i` of a mask is glTF triangle `i`, which the raw parse keeps (it may drop
  unreferenced vertices and swaps the winding inside a triangle, but keeps the
  triangle order; the design experiment's masks applied with zero centroid
  deviation).
- Occluders: only the piece's own non-lining surfaces (shell, inseams, forearm
  skin) and the lining itself. The body, the twin lining and every other worn
  item are left out, so a triangle hidden from this set is hidden whatever else
  is worn. Back faces of single-sided materials are passed through (the GPU
  culls them); `EquipmentForearmSkin` counts as single-sided because it draws
  with the body's material; a lining whose mesh extras ask for the quilt or
  antler-palette shader (`repairQuiltPaint`, `matchAntlerPalette`; drawn
  `cull_disabled`) counts as double-sided; alpha materials never occlude.
- Visibility: a triangle is visible when a ray from one of its sample points
  (the centroid, or a k x k subdivision every 3 cm, up to 16) to the camera
  escapes, for one of 128 directions over the whole sphere (directions a
  single-sided lining would cull are skipped). `visible_upper` uses camera
  elevations of -10 degrees and above only.
- Margin: `keep` adds every triangle that comes within the margin (default 2 cm,
  rest pose) of a visible one, measured between points sampled every 5 mm
  (`surface`), or between centroids as the design experiment did (`centroid`).

Mask file `<out>/<variant>/<stem>.lining.json` (default out:
`<client repo>/.local/actor-geometry/lining-masks/`), byte deterministic:

```
{schema: 1, policy: "rl-lining-visibility-v1", source: {path, sha256, bytes},
 inputs: {tool_sha256, blender_tool_sha256, posekit_sha256, library_sha256},
 settings, settings_sha256, poses: [...], margin_m, margin_rule, occluders: [...],
 linings: {<mesh>: {mesh, primitive, triangles, vertices, double_sided, material,
   gltf_index_sha256, check: [[triangle, x, y, z] x 8], samples, rays,
   new_visible_by_pose, counts, runs,
   visible, visible_upper, visible_bind, keep, keep_upper, keep_bind}}}
```

The six masks are base64 bitsets, little-endian bit order, bit `i` = triangle
`i`; `*_bind` uses the bind pose alone. A consumer checks the source SHA-256
against the file it cooks, or, for a build tree whose bytes were rewritten
(quantisation), the triangle count, the glTF index digest and the eight check
centroids (within 0.1 mm). `check` compares the SHA-256 and the geometry;
`check --rewritten` binds build-tree bytes by the geometry alone. It also
refuses a garment whose skin bind pose is not its node rest pose, which the
posing assumes (all 400 lining garments match to 2e-7). The raw ray-cast
result is cached beside it as `<stem>.visibility.json` and reused while the
garment, tool, library, posekit, mount data and settings digests match;
`finalise` applies a new margin to cached records without Blender.

`review` renders, for 15 poses that are not in the set (in-between frames,
other clips, two more mounts) and 16 random camera directions each,
orthographic first-hit images at 3 mm and counts the pixels whose first drawn
surface is a removed triangle, for the mask and for comparison masks (other
margins, the bind pose alone, the design experiment's masks). `--sheets` adds a
contact sheet per lining for six garments in four poses: as worn (kept lining
blue, removed lining red; red must never show) and the lining alone.

Measured on the review sample (2026-11-02; 20 garments, 30 linings, 313,301
lining triangles; dev laptop, four Blender 5.2 workers): the cast took 43 min
(9,193 worker-seconds, 29 ms per lining triangle, about 3.8 us per ray). All
400 garments with linings (6.74 M lining triangles) would take about 55
worker-hours, 14 hours on four workers, once per garment change. Review over
7,200 unsampled views (14.2 M lining pixels at 3 mm):

| Keep rule | Lining triangles removed | Changed pixels |
| --- | ---: | ---: |
| visible only | 58% | 91,878 |
| visible + 1 cm surface margin | 16% | 232 |
| **visible + 2 cm surface margin (default)** | **12%** | **43** (at most 4 in one view) |
| visible + 2 cm centroid margin | 19% | 6,273 |
| bind pose alone, 2 cm surface margin | 25% | 199,875 |
| design experiment E4 masks (rest pose, splats, 2 cm centroid) | 45% | 947,796 |
| cheaper cast (64 directions, centroids, 27 poses; 1/5.6 of the cost), 2 cm surface | 16% | 910 |

By class at the default: torsos 0-11% (most of the interior is seen through the
collar, hem and cuffs once the body is not an occluder), legs 14-60%, boots
0-6%. A rest-pose mask and a mask without a margin both open visible holes in
poses and views they did not sample.

## Measured cost

Dev laptop (Ultra 9 275HX), editor binary 4.7.2 headless, best of 5-7, Mossbound
Coat (`amberwood_woodland_cuirass_02`, 44,868-vertex lining soup):

| Sidecar | Apply | Of which |
| --- | --- | --- |
| masked lining base + shell chain | 1.2-1.6 ms | sidecar SHA 0.15, decode 0.17, validation 0.3, binding (index digest) 0.47, rebuild 0.04 |
| + compaction, 1,703 runs (measured mask) | 3.3 ms | rebuild 2.0 |
| + compaction, gaps of up to 2 / 4 / 8 hidden triangles kept (728 / 368 / 108 runs) | 2.7 / 2.5 / 2.4 ms | 30.7k / 34.3k / 39.0k of 44.9k vertices kept |
| `source_check` "file" | +6 ms | SHA-256 of the 2.6 MB file |

Compaction above roughly 700 runs exceeds the 3 ms per torso budget on this
machine; the cook should merge short gaps or leave such linings uncompacted.
Reading a 2,070-entry catalogue (0.84 MB) takes about 21 ms once. Storing
indices as u16 would shrink a torso sidecar from 76 to 65 KB after zstd, but the
runtime would need a GDScript widening loop, so v1 stores `PackedInt32Array`.
