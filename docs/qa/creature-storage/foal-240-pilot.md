# Sunmane Foal (Dun): 240 sample/second draft

All eight current animations have a separate local draft for comparison. The
production model, roster, action/event map and import policy remain unchanged.
This is an approximate sampling pilot awaiting user review.

| Measurement | Current | Draft | Reduction |
| --- | ---: | ---: | ---: |
| Raw GLB | 96.54 MB | 38.93 MB | 59.7% |
| Packaged RLCZ | 57.58 MB | 15.59 MB | 72.9% |
| Retained CPU allocations, shared caches + first actor | 510.20 MB | 126.69 MB | 75.2% |
| First actor/component load, warm file cache | 8.07 s | 1.93 s | 76.0% |
| Retargeted runtime animation keys | 3,973,403 | 312,221 | 92.1% |
| Corrective buffer payload | 24.76 MB | 24.76 MB | 0% |

MB means 1,000,000 bytes. Disk savings are 57,611,828 raw bytes and 41,992,613
packaged bytes, using the existing level-3 Zstandard packaging and 56-byte RLCZ
header. An actual encoded draft was decoded and verified byte-for-byte.

CPU values are medians of three fresh-process runs through the actual client
`GlbSceneCache`, `ReplicatedActor3D` and `NativeAnimationImporter`. Memory includes
the shared scene/source/library caches and the first actor. It is a Godot static
CPU allocation delta, not OS RSS, VRAM or savings for every additional foal.
Load measurements use loose GLBs with a warm OS file cache; release decode and
whole-client/map loading were not timed.

| Animation | Current CPU update | Draft CPU update | Lower CPU cost |
| --- | ---: | ---: | ---: |
| Idle A | 39.00 µs | 31.47 µs | 19.3% |
| Fighting Idle | 45.97 µs | 35.30 µs | 23.2% |
| Walk | 70.63 µs | 53.62 µs | 24.1% |
| Jog | 62.94 µs | 57.65 µs | 8.4% |
| Gallop | 119.52 µs | 99.25 µs | 17.0% |
| Sword Attack | 63.22 µs | 54.18 µs | 14.3% |
| Hit Chest | 34.33 µs | 31.64 µs | 7.8% |
| Death A | 78.42 µs | 56.54 µs | 27.9% |

These are headless AnimationPlayer advance + forced skeleton-transform costs at
240 updates/second, after warmup, nine batches of 1,200 updates per clip per run.
They exclude GPU rendering/skinning and other game logic. No whole-game FPS gain
is claimed. For example, Walk saves about 0.017 ms per actor update in this test.
The skeleton, two surfaces and corrective buffers are unchanged; no GPU saving
is claimed.

## What changes and what is preserved

The draft resamples every animation sampler, including corrective activation
weights. Rotations use quaternion SLERP; other channels use linear interpolation.
Each sampler keeps its exact original first/last timestamp and value. Uniform
intervals are spread over the full duration so there is no short extra interval
at the end. The largest stored float32 interval rate is 239.620 samples/second.
The native runtime bake declaration is 240 Hz. Binary compaction then removes
unreachable storage, deduplicates identical bytes and collapses exact constants.

Mesh geometry, UVs, triangles, the 180-joint hierarchy, eight-influence skin,
bind/rest transforms, all 130 corrective POSITION/NORMAL targets, materials and
embedded textures are preserved. Names, all 4,352 animation channels, durations,
endpoints, action mappings and event timing remain intact. Between-key motion
and corrective activation curves are approximate.

## Observed differences

All 10,521 actual client vertices and reconstructed normals were compared at
4,922 states: 480 Hz through every full clip plus off-grid times/endpoints, all
56 directed crossfade pairs at four steps, and RESET. Static native mesh/skin/
corrective arrays and binds match byte-for-byte. RESET positions match exactly.

| Clip | Largest observed position difference |
| --- | ---: |
| Idle A | 0.289 mm |
| Fighting Idle | 0.430 mm |
| Walk | 0.112 mm |
| Jog | 0.250 mm |
| Gallop | 2.424 mm |
| Sword Attack | 0.779 mm |
| Hit Chest | 0.529 mm |
| Death A | 0.419 mm |

The largest movement difference occurs in Gallop at 0.0770833 seconds. All
crossfade samples stay within 0.582 mm. Independent fresh Blender imports also
preserve all vertices/bones/actions; 33 poses per clip give a maximum position
difference of 0.927 mm at gameplay scale 0.65. Blender and Godot use different
sampling/interpolation paths, so their sampled maxima need not agree.

Gallop has a localized foreleg shading difference at 0.4833333 seconds. Its
largest reconstructed normal-angle difference is 44.894 degrees; at that pose,
18 of 10,521 vertices exceed one degree, three exceed ten degrees, and one
exceeds thirty degrees. The 99th percentile is 0.126 degrees. The corrective
normal contributions strongly cancel at the most sensitive vertex, amplifying
the activation-curve change. The preview includes a close inspection button for
this pose. This draft does **not** pass the previous lossless normal/pixel budgets.

These are sampled observations, not continuous-time bounds, contact/foot-slide
certification or user artistic approval. Review full cycles and the Gallop
hotspots before considering a replacement.

## Open the comparison

Run `godot-client/open-foal-animation-comparison.bat` in this task worktree, or:

```powershell
python eloria-assets/tools/preview_foal_240.py
```

Both versions appear together using the actual client actor/importer and Forward+
renderer. Drag either pane to orbit both cameras; use the wheel to zoom. Select
any of the eight animations, pause, restart, scrub, or change speed together.
Space toggles playback and arrow keys change animation. One-shots hold their
last pose unless repeat is enabled. Optional switches blend for 0.15 seconds.
The two Gallop inspection buttons pause at the measured hotspots. Reset camera
returns to the full model.

The launcher stages current client scripts/data/UI into an ignored isolated
project and redirects its profile locally. It does not launch the game network
session or change player settings. Both model hashes are checked before loading.
Native actor GLBs are read directly rather than editor-imported.

The draft is `.local/foal-240-draft/sunmane_foal_dun_240.glb`. Measurements,
fresh-import evidence, full comparison stills and detailed hotspot captures are
alongside it. These generated review files remain ignored and deliberately keep
the reference and draft available. They are not added to the production install.

Rebuild or repeat measurements from the repository root:

```powershell
python eloria-assets/tools/build_foal_240_draft.py
python eloria-assets/tools/measure_foal_240.py
python eloria-assets/tools/preview_foal_240.py --smoke
```

The builder requires NumPy, SciPy and Zstandard and is bound to the current
baseline SHA-256. The launcher accepts `--godot PATH` or the `GODOT` environment
variable. The [machine-readable receipt](foal-240-pilot.json) binds measurements
and limitations to the exact source/draft and ignored evidence hashes.
