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

## Direct blending in the existing ground pass

`terrain_blend_trial.gd` is a separate opt-in experiment. Suncoil disables biome
blending and its opaque `AuthoredGround_suncoilBase` surface covers `Terrain`
by 6 mm. This trial changes that visible ground surface's material, retaining
its geometry, original ground shading and render modes. It adds no visual nodes,
`material_overlay`, `next_pass` or road draw pass. The production loader does not
call it.

```gdscript
const Blend := preload("res://src/dev/road_texture_trial/terrain_blend_trial.gd")
var result := Blend.apply(world_root, absolute_trial_json, "blend")
```

The producer `eloria-assets/tools/road_terrain_blend_trial.py` requires equivalent
road PBR definitions, source image bytes, sampler settings and vertex RGB.
It currently selects a single common material for the two Suncoil trails.
It combines raw coverage by maximum and selects the highest-coverage fragment's
UV, with stable authored triangle order breaking ties. This approximates the
original overlapping ribbons; their separately sampled textures and lighting
are not retained individually.

Generate fresh ignored fields inside the source map asset root, for example:

```powershell
python eloria-assets/tools/road_terrain_blend_trial.py `
  --out eloria-assets/maps/continent-v2/suncoil/client/.local/road-terrain-blend-trial `
  --ppm 4 --ppm 8
```

An optional `--original-root` selects a pre-consolidation asset fixture for
accounting. Prior generations are never overwritten. The producer validates
compact collision, every stored mip, encoded and decoded hashes, and shared
covered gutter samples. Coverage is R8 PNG; UV is lossless RG32F Zstd with a full
mip stream. A second RGBA32F Zstd field stores each selected triangle's affine
UV derivatives `(dU/dX, dU/dZ, dV/dX, dV/dZ)`, without mips.

Filtering unrelated overlap UVs creates huge false texture gradients and flat
patches. The shader instead fetches a single level-zero UV/Jacobian pair,
reconstructs the UV at the fragment and derives the original texture footprint
from world-position derivatives. Normal mapping uses an orthogonal frame with
the source UV handedness. Void UV cells must be extrapolated to their own cell
centers using the nearest selected affine map; copying a neighbor's center UV
shifts the texture at filtered edges. The producer checks that covered cells
and lower UV mip bytes survive this halo correction. All old UV mips remain
stored, validated and counted even though this shader reads level zero only.

`terrain_blend_contract_check.gd` checks material namespace separation, affine
reconstruction, sheared normal frames, actual field layouts/hashes and bad-input
rejection. The existing collision checker also accepts these compact payloads.
Use benchmark variants `blend4`/`blend8`, generated road-free manifests and their
parallel `trials` paths. The harness checks the before/after regular-mesh,
surface, material-chain and overlay inventories to reject added road passes.

Road physics remains at terrain +55 mm while these visuals lie on Base at
+6 mm: a 49 mm visual/physical difference. Road albedo and normal/PBR values
are combined before lighting, which differs from separately lit alpha ribbons.
Coverage edges, overlap texture choice and distant taper can therefore change.
Decorative grass still needs its CPU road-coverage adapter. This trial does not
promote runtime assets or rebuild production caches.

The final edge-corrected 2026-10-28 test used the same engine, hardware, high
quality settings and two-chunk route as the earlier experiment. Three accepted
runs per variant produced these medians:

| Variant | Asset bytes, MB | GPU ms | Frame ms | GPU allocation, MB |
| --- | ---: | ---: | ---: | ---: |
| Consolidated geometry | 19.828 | 0.676 | 1.019 | 336.7 |
| Previous overlay, 4 pixels/metre | 18.825 | 1.106 | 1.459 | 354.6 |
| Direct blend, 4 pixels/metre | 19.725 | 0.474 | 0.809 | 341.8 |
| Direct blend, 8 pixels/metre | 25.004 | 0.475 | 0.815 | 363.9 |

The direct 4-pixel blend saves about 30% GPU time against geometry and 57%
against the earlier overlay, but saves only 103,393 asset bytes (0.52%). It adds
about 5.1 MB GPU allocation against geometry. The 8-pixel version adds 5.18 MB
of asset data for little visual improvement. Correct affine UV values in empty
cells are less compressible than nearest-value copies: the final 4-pixel UV
stream alone occupies 1.79 MB. Per-file zlib-6 comparison grows from 13.338 MB
for consolidated geometry to 15.132 MB for direct 4-pixel data; these figures
are not an exported package or download measurement.

Seven matched views include the original five, the exact shared chunk edge and
a fork where road flow directions differ by about 70 degrees. Road layout and
colour remain recognizable, without an obvious seam crack or large UV smears,
but edge silhouette, taper, grain and lighting differ from geometry. Doubling
resolution provides only small improvements and does not restore independent
overlap samples. GPU captures also pass in the compatibility renderer.

Focused validation passed 53 Python tests, and the actual final fields passed
69 material/codec checks and 57 importer/physics checks. Twelve live road probes
retain their footstep classes and heights within 0.031 mm. The two regular-mesh
inventories across both chunks have 102 visible surfaces with geometry roads, 117 in the old
overlay trial and 98 in the direct blend; no overlay or next pass is added.

Unfocused attempts are rejected. Two control measurements from the preceding
cohort filled rejected final control slots only after their complete input-hash
dictionaries matched the final controls exactly. All six direct-blend timings
use the final halo-corrected asset generation. Startup and tail frame times
varied, so treat the steady GPU result as the useful component comparison.

For a further disk experiment, store shared affine coefficients or a compact
triangle lookup and reconstruct the floating-point fields at load time. Avoid
persisting dense extrapolated UVs and unused UV mip levels. That encoding has
not been implemented or measured here; direct blending currently improves
rendering cost without a meaningful asset-size reduction.
