# Offline road texture trial

This experiment is not called by the production game. It qualifies a bounded
replacement for selected Suncoil road visuals after loading the baker's
road-free `base.glb` through the normal `WorldLoader` path.

```gdscript
const Trial := preload("res://src/dev/road_texture_trial/road_texture_trial.gd")
var result := Trial.apply(world_root, absolute_trial_json, "mask")
```

`baseline`, `original`, and `consolidated` are explicit no-ops. `mask` (also
`mask2`/`mask4`) accepts a chunk `trial.json` or its variant index containing
relative chunk metadata paths. It returns `{ok, errors, metrics}`. All fields
and colliders are prepared before placeholders change. Errors abort the trial;
there is no fallback rendering of the original road ribbons.

The baker's `rabbitlands-road-texture-trial-v1` contract is defined by
`eloria-assets/tools/road_texture_trial.py`. Each layer contains an R8 coverage
PNG mip chain, a losslessly Zstd-compressed little-endian RG32F unwrapped-UV
mip chain (raw references are also supported), explicit grid
bounds/gutters, source material glTF JSON, original node frames and compact
exact position/index collision inputs. Source materials are parsed by Godot
using only their referenced images. Their ordinary `LookGround.painted_for`
treatment is adapted from the current production shader with checked textual
anchors; class texture mapping, regional paint, rim noise, source detail
normal and roughness remain the production code's responsibility.

The visual uses the existing terrain mesh once per road sheet, with a shader
lift of 0.055 metres in the source frame. It is an extra masked overlay pass,
not a single-pass terrain blend. Its geometry is shared; the entire terrain
mesh is submitted for every sheet. Measure GPU cost rather than assuming a
performance improvement. Flat face normals and the road's tangent frame are
derived from terrain geometry and the sampled flow UVs.

Invisible compact collision meshes retain the old road node/material naming,
layer-8 collision, source-local positions and expanded triangle byte hashes.
After checking the source-order hash, their triangle corners 1 and 2 are
exchanged exactly as Godot's glTF importer does. Both the compact mesh and its
one-sided collision use that engine winding; backface collision stays disabled.
This keeps road height, grounding, and the existing footstep parent-material
lookup. It does not make the original visual mesh available for fallback.

Full painted mode with decorative grass is rejected explicitly: its CPU
grass classifier still needs a coverage adapter for the compact colliders.
The qualification harness must report that limit. Cartography and production
cache cooking are outside this offline renderer. No production replacement,
asset promotion, upload or release is enabled by these files.

The headless `contract_check.gd` verifies baseline behavior, source-shader
anchors, the material GLB container, decoded field layout/hashes and rejection
of a wrong decoded size, plus the exact collision triangle hash. Pass a variant
or chunk metadata file after `-- --trial PATH`. A passing headless check is not
a shader-compilation, screenshot or frame-time qualification.

`collision_contract_check.gd` separately imports the actual source chunk with
Godot, compares its CPU ImporterMesh triangle bytes with every compact collider,
waits four physics ticks and compares downward ray heights/normals on twelve
deterministic road witnesses. This guards the glTF-to-engine winding conversion,
which a raw source-byte check alone cannot establish.

## Repeating the comparison

`tools/road_texture_compare.py` launches `tests/integration/road_texture_benchmark.gd`
in a fresh process and isolated player/editor profile. Run from the repository
root with `--godot PATH_TO_GODOT --config CONFIG.json --output
godot-client/test-artifacts/UNIQUE_RUN`. Add `--qualification` for screenshots;
omit it for timing. `--project` can select a task-owned original-asset fixture,
and `--renderer gl_compatibility` selects the compatibility renderer. The runner
holds the shared client performance lock and rejects engine errors, leaks,
changed inputs, mismatched rendering settings and unfocused timed frames.

The configuration supplies `manifests`, `lighting_manifest`, `region`,
`look: "painted_ground"`, fixed `probes` in world coordinates, and `views` with
`target`, `yaw`, `pitch` and `distance`. Timing uses `measure_seconds: 10` and
five views, each visited twice with a small continuous camera orbit. For texture
roads use `variant: "mask2"` or `"mask4"`, the generated road-free `world.json`
manifests and a parallel `trials` array of generated chunk `trial.json` paths.
For geometry use `variant: "baseline"` and the ordinary chunk manifests.
`expected_ground` can contain the original report's `ground` witnesses to
require road collision, matching footstep classes and positions within 0.1 mm.
Equal-height ribbon overlaps may choose a different road collider after a BVH
rebuild, so the comparison checks the road class rather than that tie winner.

Bake with `eloria-assets/tools/road_texture_trial.py`. Its output must be a new,
locally ignored `.local` directory inside this worktree's map asset root so the
normal manifest path guards continue to apply. `--original-root` optionally
provides a task-owned pre-consolidation asset snapshot for size accounting.
All stored coverage/flow mips and compact colliders count toward disk totals;
content-identical files at different paths are counted separately. Per-file
zlib figures are a compression comparison, not an exported package measurement.

The harness loads Suncoil chunks `06_09` and `06_10` through the normal raw
`WorldLoader` path with high quality, full textures, native VRAM sidecars off,
decorative grass off, a 1280x720 foreground window, VSync off and no frame cap.
It binds the Suncoil environment and waits for visible frames and physics
registration before readiness/probes. Qualification freezes animated shader
time and captures five fixed views; timing performs no pixel or mesh readbacks.
Reported readiness includes chunk loading, trial installation and first-view
preparation; it is not the chunk-load call alone.

Keep qualification and timing separate, use the same engine, views and probes
for every arm, and counterbalance run order. Record GPU timing, wall frame
percentiles, draw calls, primitives, GPU memory and process peak working set.
The report includes each input hash and effective settings. Fresh processes
retain OS and driver caches; hashing inputs also warms the filesystem cache.
These are offline component measurements without an avatar, streaming or a
network connection, and do not establish whole-game FPS or cold disk load time.

## Initial Suncoil result

The 2026-10-28 local trial used Godot 4.7.2 Forward+ on an RTX 5080 Laptop GPU.
The table gives three-run medians; disk includes the complete two-chunk runtime
dependency closure. The 2/4 pixel-per-metre versions remain experimental.

| Variant | Disk MB | GPU ms | Frame ms | p95 frame ms |
| --- | ---: | ---: | ---: | ---: |
| Original geometry | 23.77 | 0.692 | 1.027 | 1.169 |
| Exact consolidation | 19.83 | 0.679 | 1.015 | 1.154 |
| Texture roads, 2 pixels/metre | 17.99 | 1.080 | 1.423 | 1.609 |
| Texture roads, 4 pixels/metre | 18.83 | 1.107 | 1.440 | 1.638 |

The texture variants save another 9.3%/5.1% against consolidation, but add
59%/63% GPU time in this scene. Lower resolution has conspicuous stepped edges
and flat texture patches; higher resolution is closer but retains small seams
and border artifacts. Per-file zlib-6 comparison reduces the lower-resolution
saving to 76 KB and makes the higher-resolution variant 757 KB larger. A future
trial should blend a packed road mask in the existing terrain pass and reduce
UV reconstruction cost before considering production use; those savings and
quality are not yet measured.

Exact consolidation saved 276,409,840 bytes across 1,286 outdoor GLBs without
changing expanded corner attributes, triangles or bounds. All ten matched
Suncoil/Landfall qualification views were pixel-identical. The texture trial's
twelve road-ground probes matched footstep classes and remained within 0.031 mm
of the original height after the importer-winding correction. Its masked passes
also compiled and rendered in the compatibility renderer. Focused validation
passed 41 Python tests, 99 protocol checks and 57 importer/physics checks. Two
unfocused timing attempts were rejected; twelve accepted runs form the table.
