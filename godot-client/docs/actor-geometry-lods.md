# Actor geometry LODs

Package-time geometry for actor glTFs: masked lining faces, LOD index chains and
optional vertex compaction, delivered as per-file sidecars and attached to the
runtime parse. Vertex attributes are never rewritten (compaction only drops whole
runs of unused vertices), so face sculpt, body refinement, cover cuts, cape fits
and the RL head body cut keep reading the arrays they read today.

Status: the shared format (`src/actors/actor_geometry_format.gd`) and the runtime
applier (`src/actors/actor_geometry.gd`) exist and are tested
(`tests/test_actor_geometry.gd`), and so do the cook that writes a developer
catalogue (`tools/actor_geometry_cache.py`, below) and the offline tool that
decides which lining triangles are hidden
(`eloria-assets/tools/lining_visibility.py`, below). Nothing calls the applier
yet: the call in the actor parse (`GlbSceneCache._build_raw`), lining masks in
the cook and release packaging arrive in later steps, so the game draws exactly
what it drew before.

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

## Cook

`tools/actor_geometry_cache.py` decides what needs cooking and writes the
catalogue; the headless Godot script `tools/actor_geometry/cook.gd` parses each
file exactly as the runtime parses an actor glTF (the project's glTF
extensions registered, `ActorImages` enabled, `CreaturePayload.append`) and
plans every surface with `tools/actor_geometry/lod_policy.gd`. Nothing is
written beside the sources.

```
python godot-client/tools/actor_geometry_cache.py cook   --godot <editor exe> [--wrapper "<prefix>"] [--jobs 2]
python godot-client/tools/actor_geometry_cache.py verify --godot <editor exe> [--wrapper "<prefix>"] [--jobs 2]
python godot-client/tools/actor_geometry_cache.py report
python godot-client/tools/actor_geometry_cache.py compare <root A> <root B>
python godot-client/tools/actor_geometry_cache.py predict --census <crowd census json>
```

- Scope: tracked `.glb`/`.gltf` files under `assets/actors/native/` (the
  applier's `in_scope` rule: not `rl_heads/`), minus retired models; 2,072
  files today. `--paths` cooks or verifies a subset and keeps every other
  entry.
- Output (default `<repository>/.local/actor-geometry/`, which must be
  Git-ignored): the catalogue root `rl-actor-geometry-v1/` (`catalog.json`,
  `blobs/`), read by an editor checkout, and the driver state `cook/`
  (`summary.json` with every surface's plan, the newest eight run folders with
  jobs, reports and Godot logs, and an isolated Godot profile). Unreferenced
  blobs are removed after each cook.
- Reuse: a file is cooked again only when its bytes, the external buffers it
  reads (the `.bin` of a `.gltf`), its model scale or the policy digest
  (engine build from `godot --version`, `cook.gd`, `lod_policy.gd`,
  `actor_geometry_format.gd`) change, or its blob is damaged. The project's
  glTF extensions are not in the digest: a parse change that alters vertex or
  index counts or index buffers is caught at runtime (the file is drawn as
  parsed) and by `verify`, one that only moves vertex data is not, so recook
  with `--force` after changing them.
- One driver per output folder: `cook` and `verify` hold an OS lock on
  `cook/driver.lock`, and a second driver on the same folder stops with an
  error.
- Godot runs: headless, `--log-file` before `--path`, one process per batch
  (`--batch-size`, default 250 files), up to `--jobs` at a time, each prefixed
  by `--wrapper` (for example a machine-wide slot lock). The timeout
  (`--timeout-seconds`) starts when Godot opens its log. Before each file the
  script prints `actor geometry cook: <path>`; engine `ERROR:` lines are
  attributed to that file in the summary, and a `SCRIPT ERROR` fails it (no
  catalogue entry).
- The catalogue is compact JSON with sorted keys and `source_check: "file"`
  (`--source-check parsed` for a root verified with its actor files); entries
  carry `inputs.policy_digest`. A file with no chain at all gets no entry (the
  runtime counts it `not_listed`).
- `verify` applies every catalogued sidecar with `ActorGeometry.apply` to a
  fresh runtime parse and, after `generate_scene()`, compares the LOD levels
  the RenderingServer holds with the sidecar's.
- `predict` maps the pieces of a crowd triangle census (the wave-2 design
  census format: `triangleCensus` per actor with distances) to cooked meshes
  through `equipment.json` (one race variant) and the race body, and reports
  the triangles the chains would draw at each body's distance and lod_bias,
  plus the share of drawn triangles on surfaces with two or more levels.

### LOD policy v1

For every triangle surface of at least 64 triangles (`lod_policy.gd`):

- Chain: `ImporterMesh.generate_lods(60, 25, [])` on a one-surface copy of the
  exact parsed surface. Vertex buffers are never touched.
- A triangle soup (one vertex per corner) whose corners, welded by position,
  disagree on UV or skin for more than 5 % of corners has per-face atlas tiles
  and gets no chain (`per_face_tiles`): simplifying it smears tiles. These are
  the 128 torso linings, 7 other equipment pieces, 5 creatures (moth, badger,
  golem, sprite, dryad queen) and the giant rat mount; vertex-colour linings
  (C10) are their route.
- A surface Godot gives no chain is simplified as a position-welded proxy, and
  each proxy corner is mapped back to an original vertex at that position,
  preferring one UV island for the whole triangle. A proxy level is kept only
  when the surface's welded corners agree on UV and skin (>= 95 %) or >= 95 % of
  the level's triangles stay on one UV island (`seams` otherwise: the generic
  cape's three surfaces and `crystal_dire_wolf`, whose proxy levels would cross
  seams on 40-50 % of triangles).
- Kept levels: per target fraction 50 / 25 / 12 / 5 % of the base triangles,
  the generated level nearest to it (within 1.5x, at least 32 triangles, each
  smaller and later than the one before).
- Edge length of the level kept for target k:
  `max(band_k * 1.658 / (1920 * model_scale), error / 3)`, bands 8 / 18 / 36 /
  70 m. Godot draws level i while `edge * model_scale * lod_bias / (depth *
  1.658) <= 1 / viewport_width` (1.658 = 2 tan(hfov/2) at the 50 degree
  gameplay FOV and 16:9; depth is the camera's distance to the near side of
  the instance's AABB, model_scale its largest axis scale), so at 1920 px and lod_bias 1 (High) a level never
  draws nearer than its band, and never before its geometric error (Godot's
  own figure, in mesh units) covers at most 3 px. Medium (lod_bias 0.65) and
  Low (0.35) reach the bands at 0.65x and 0.35x the depth, where the error
  clamp allows 4.6 px and 8.6 px. A smaller viewport (1280 px) switches
  proportionally nearer.
- `model_scale` = the catalogue import scale of a `models.json` scene (red fox
  0.176) times the smallest node scale that draws the mesh in the glTF, so the
  bands hold in world metres; gameplay size scales are not known to the cook
  (larger instances switch later).

### Measured (2026-11-03, dev laptop, editor binary 4.7.2 headless)

| | |
| --- | --- |
| Cook, all 2,072 files | 56-62 s wall with two Godot processes (68 s of process time: parse 34 s, planning 15 s); a rerun with nothing changed 1.6-2.1 s |
| Output | 2,061 sidecars, 47.3 MB (i32 indices, zstd); catalogue 0.99 MB; 11 files without a chain |
| Levels | 8,975 on 3,281 chained surfaces (1,253 with two levels, 551 with three, 1,113 with four, 364 with one) |
| Coverage | 82 % of the 14.4 M source triangles on surfaces with >= 2 levels (hair 100 %, creatures 95 %, races 83 %, equipment 78 %); 141 per-face-tile surfaces hold 2.03 M triangles |
| Determinism | two independent full cooks: catalogue and all 2,061 blobs byte-identical |
| Editor vs release template | `generate_lods` on 24 surfaces of 10 files: identical indices and errors in the official 4.7.2 release template, which reports the same engine identity; the cook's chains (project parse) match them |
| `verify` | 2,061 of 2,061 applied to the runtime parse; 8,967 levels on the RenderingServer, no mismatch (8 more on a mesh no node draws); apply median 2.0 ms, p95 12 ms, max 0.2-0.23 s, all with `source_check: "file"` hashing the actor file (the maximum is a 57 MB creature) |

Census prediction (the design census of `s3-market-160`, 36 bodies in view at
23-46 m, 1280 px, chains only, no lining masks or far tier): High 1.56 M ->
1.06 M triangles (-32 %), lod_bias 0.65 -36 %, the Low capture at 0.35 1.54 M ->
0.89 M (-42 %). Only 43-47 % of the drawn actor triangles are on surfaces with
two or more levels: the torso lining soups (about 15k triangles per body) and
the cape (6k) have none, and RL heads keep their authored levels.

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
