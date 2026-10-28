# Crystalback Tortoise: current storage and 30 FPS draft

The current reference in this task worktree is the earlier shell-partition pilot, SHA-256
`fcec0718567c0f426a3ba81b7004d5b4cf39ecf60bcb94c37a6bb4cf4f12aa89`.
It has 5,368 vertices: 3,328 in the soft body with 577 corrective shapes, and
2,040 in the separate rigid shell. Its skeleton has 21 joints and its native
animation bake declaration is 4,096 Hz.

The new draft contains all seven clips at a maximum of 30 animation samples
per second, including corrective activation weights. It preserves mesh, skin,
bind/rest transforms, hierarchy, corrective geometry, mounted-skin metadata,
materials, images, clip names/durations, exported endpoints and action mapping.
The current runtime model and its import settings have not been replaced.

## Exact raw-file distribution

| Component | Current MB | Current share | 30 FPS MB | 30 FPS share |
| --- | ---: | ---: | ---: | ---: |
| Corrective geometry | 23.083 | 55.00% | 23.083 | 89.86% |
| Animation | 17.210 | 41.01% | 0.913 | 3.56% |
| Embedded textures | 0.796 | 1.90% | 0.796 | 3.10% |
| File metadata, headers and alignment | 0.581 | 1.39% | 0.595 | 2.32% |
| Base geometry and UVs | 0.190 | 0.45% | 0.190 | 0.74% |
| Skin weights, joint indices and binds | 0.109 | 0.26% | 0.109 | 0.42% |
| **Total raw GLB** | **41.970** | **100%** | **25.687** | **100%** |

MB means 1,000,000 bytes. These are physical byte counts, with shared and
overlapping storage counted once. Corrective storage comprises 8,825,856 bytes
of position data, 14,217,216 bytes of normal data and 39,936 bytes shared between
position/normal targets. Those bytes are unchanged in the draft.

The animation breakdown explains most of the saving:

| Animation data | Current bytes | 30 FPS bytes |
| --- | ---: | ---: |
| Corrective activation weights | 14,928,144 | 798,568 |
| Joint/object rotations | 1,338,288 | 70,272 |
| Joint/object scales | 754,956 | 37,008 |
| Joint/object translations | 141,840 | 6,348 |
| Shared timestamps | 47,268 | 1,264 |
| **Total** | **17,210,496** | **913,460** |

Raw storage falls **38.8%**, saving 16,282,960 bytes. Packaged RLCZ falls from
**25.051 MB to 13.064 MB**, saving 11,987,775 bytes (**47.9%**), including the
56-byte header and existing level-3 Zstandard compression. The component table
describes the raw GLB; whole-file compression does not have an exact independent
share for each component.

## Runtime and sampled motion

One fresh-process run per version through the actual client scene cache, Actor
and native importer measured retained static CPU allocations of **529.6 MB
versus 116.8 MB**. This includes shared scene/source/library caches and the first
actor; it is not OS RSS, VRAM, or a saving repeated per additional tortoise.
Warm-file-cache loose-model loading measured 2.62 versus 1.29 seconds. Runtime
retargeted animation keys fall from 4,208,956 to 190,405. These are focused
component measurements, not whole-game FPS or packaged-decode benchmarks.

The corrective GPU payload remains 38,405,120 bytes per shared mesh set; no GPU
memory saving is claimed. The two draw surfaces and all corrective targets
remain intact.

Every vertex of the actual client soft body and unskinned shell was evaluated
at 909 states: full clips at 60 Hz plus six off-grid times each, all 42 directed
crossfade pairs at four steps, and RESET. Static native P/N/skin/corrective
arrays and binds match byte-for-byte. At import scale 0.588, the largest sampled
position difference is **9.25 mm**, during Jog at 0.483333 seconds. Per-clip
maxima are Idle 0.038 mm, Fighting Idle 0.00013 mm, Walk 7.43 mm, Jog 9.25 mm,
Sword Attack 5.82 mm, Hit Chest 0.447 mm and Death 1.25 mm.

This is an approximate draft awaiting visual review. These samples are not a
continuous-time bound, normal-shading/contact certification or mounted-rider
qualification. The previous lossless pilot's exactness claims do not apply to
the new animation curves.

## Compare both versions

Run `godot-client/open-crystalback-30fps-comparison.bat`, or:

```powershell
python eloria-assets/tools/preview_creature_sampling.py --actor crystalback_tortoise --fps 30
```

The original appears on the left and the 30 FPS draft on the right, using the
actual client Actor/importer and Forward+ renderer. Drag either pane to orbit
both cameras, use the wheel to zoom, choose animations, change speed, pause,
restart or scrub both versions together. The viewer interpolates the animation
at its normal display frame rate; it is not capped to 30 rendered FPS. A button
jumps to the largest measured movement difference for close inspection.

All seven clips, 49 switches, end holds/repeats, reset, keyboard controls, mouse
orbit and zoom pass the preview smoke check. Profile, reference copy, candidate,
before/after audits, benchmark data and captures stay in the ignored directory
`.local/creature-sampling/crystalback_tortoise/`. The current model remains
unchanged. Rebuild with `build_creature_sampling_draft.py --actor
crystalback_tortoise --fps 30` and measure with `measure_creature_sampling.py
--actor crystalback_tortoise --fps 30`, both under `eloria-assets/tools/`.

The [machine-readable audit](crystalback-tortoise-30fps.json) binds the before/
after byte counts, draft, validation scope and ignored evidence to exact hashes.
