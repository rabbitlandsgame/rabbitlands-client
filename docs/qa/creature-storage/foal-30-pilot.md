# Sunmane Foal (Dun): 30 FPS evaluation draft

All eight animations have a separate 30 FPS sampling draft, made directly from
the unchanged current foal. The 240 FPS draft is retained. Both drafts preserve
the mesh, rig, eight-influence skin, corrective shape geometry, textures, clip
names, durations, exported endpoints and gameplay action/event mapping.

| Measurement | Current | 240 FPS draft | 30 FPS draft |
| --- | ---: | ---: | ---: |
| Raw GLB | 96.54 MB | 38.93 MB | 33.91 MB |
| Packaged RLCZ | 57.58 MB | 15.59 MB | 13.45 MB |
| Stored sampler key entries | 4,655,060 | 515,487 | 69,209 |
| Runtime retargeted keys | 3,973,403 | 312,221 | 40,785 |
| Retained CPU allocations: shared caches + first actor | 510.20 MB | 126.69 MB | 96.53 MB |

The 30 FPS draft removes another 86.6% of stored sampler key entries compared
with the 240 FPS draft. Raw storage falls another 5.02 MB and packaged storage
another 2.13 MB. Compared with the current model it is 64.9% smaller raw and
76.6% smaller packaged. MB means 1,000,000 bytes. Most remaining storage is the
unchanged corrective geometry; GPU buffers have not been reduced.

CPU allocations are isolated Godot static CPU memory measurements, including
shared scene/source/animation-library caches and one actual client Actor. They
are not OS RSS, VRAM, or a saving repeated for each additional foal. The 30 FPS
case had one fresh-process benchmark run per version; the earlier 240 FPS values
are medians of three. In the 30 FPS run, original/draft loading took 6.32/1.27
seconds with a warm file cache and loose GLBs. These are component measurements,
not whole-client startup or FPS results.

Run `godot-client/open-foal-30fps-comparison.bat`, or from the repository root:

```powershell
python eloria-assets/tools/preview_foal_240.py --fps 30
```

The original is on the left and the 30 FPS draft on the right. Animation,
scrubbing, pause, speed and camera controls affect both versions together. The
client continues rendering at its normal frame rate and interpolates the lower
rate animation keys. This does not cap the viewer to 30 rendered frames/second.
Use `open-foal-animation-comparison.bat` to reopen the retained 240 FPS comparison.

The new draft and local measurements are in `.local/foal-30-draft/`. Rebuild with
`python eloria-assets/tools/build_foal_240_draft.py --fps 30`; benchmark with
`python eloria-assets/tools/measure_foal_240.py --fps 30`.

The builder checks exact preservation of static data, clip/channel inventory,
durations and exported endpoint values. Stored float32 intervals never exceed
30 samples/second; the maximum is 29.7601 Hz because full clip endpoints are kept
without adding a short final interval. Native runtime bake cadence is 30 Hz.
All eight clips, 64 switches, end holds/repeats, reset, scrubbing, keyboard,
mouse orbit and zoom pass the Forward+ preview smoke check. The shared previewer
also passes its retained 240 FPS headless regression check and now frees its
scene/library caches on window close.

This is an approximate draft for user visual evaluation. The detailed 240 FPS
surface/normal error results do not apply to the 30 FPS file. No production
model or import policy has been replaced. Exact hashes and scope are recorded
in [the 30 FPS receipt](foal-30-pilot.json).
