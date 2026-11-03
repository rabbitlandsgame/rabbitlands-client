# Actor geometry LODs

Package-time geometry for actor glTFs: masked lining faces, LOD index chains and
optional vertex compaction, delivered as per-file sidecars and attached to the
runtime parse. Vertex attributes are never rewritten (compaction only drops whole
runs of unused vertices), so face sculpt, body refinement, cover cuts, cape fits
and the RL head body cut keep reading the arrays they read today.

Status: the shared format (`src/actors/actor_geometry_format.gd`) and the runtime
applier (`src/actors/actor_geometry.gd`) exist and are tested
(`tests/test_actor_geometry.gd`). Nothing calls the applier yet: the call in the
actor parse (`GlbSceneCache._build_raw`) and the cook arrive in later steps, so
the game draws exactly what it drew before.

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
