# Crystalback Tortoise: corrective shape and skin audit

The reviewed 30 FPS tortoise is the reference. Neither experiment replaces the installed creature. The best storage result keeps the original base mesh and skin weights: it reduces 577 corrective shapes to 328 and the packaged model from 13.06 MB to 6.90 MB. This is a measured approximation requiring visual acceptance, not a lossless replacement.

The skin experiments show that better weights can explain much of the deformation, but ordinary reweighting or a single baked mesh cannot safely replace the whole corrective system. Keeping the original weights gives a smaller, closer matching compression draft than the conservative skin repair. We should take the storage reduction separately from further rig development.

## What the corrective shapes contain

The 577 shapes are compressed pose bases: 221 contain position changes and 356 contain normal/shading changes. They are not 577 separate tearing fixes. The existing corrective packer builds these bases from a dense pose cache; a basis can contribute to many poses and clips, including through negative coefficients. All seven animations use explicit corrective weight tracks. The body has 3,328 render vertices and 21 joints; the 2,040-vertex rigid shell already has no corrective payload.

| Stored component in reviewed 30 FPS model | Bytes |
|---|---:|
| Corrective positions | 8,825,856 |
| Corrective normals | 14,217,216 |
| Shared zero position/normal block | 39,936 |
| All corrective data | **23,083,008** |
| All animation curves | 913,460 |
| Textures | 796,382 |
| Base geometry, UVs and indices | 189,770 |
| Skin and binds | 108,704 |
| Metadata, container and alignment | 595,360 |

Correctives occupy 89.86% of the raw file; normals account for most of that corrective storage. Reducing only the position corrections leaves the larger shading payload behind.

## Mesh and weight experiments

The audit reconstructs the final corrected surface from actual client mesh arrays, morph weights and skeleton matrices. It checks all seven clips, neutral/reset and directed animation blends. Fitting shares weights and rest-position changes between coincident vertices to preserve seams. There are 1,042 unique positions and 982 coincident groups; none of those groups originally has conflicting weights. There is no simple UV-seam weight mismatch to repair.

| Alternative, without retained dynamic corrections | Measured result |
|---|---|
| Remove all corrections | 20.24 mm RMS; 163.89 mm maximum surface difference |
| Best fixed mesh displacement, original weights | 11.25 mm RMS; 97.74 mm maximum remaining difference |
| Fit nonnegative weights on nearby existing joints, four influences | 1.60 mm RMS on held-out animation states; 42.90 mm maximum |
| Eight influences instead of four | 1.59 mm RMS; essentially the same maximum |
| Alternate mesh and weight fitting | 1.39 mm RMS; approximately 39.29 mm maximum, plus 18.53 mm neutral/reset change |

These are displayed, world-space millimetres at the actor's configured scale. Training used alternating non-blended clip samples; the weight-only validation includes withheld samples and blends. Static and alternating mesh fits are useful feasibility tests, not approved authoring edits. The best static fit would move some source vertices by 149.9 mm locally, or 88.1 mm at the displayed scale.

The largest remaining position failures occur at front upper-limb/shoulder transitions and rear feet during Death_A, with other errors around bending limbs. Fixed weights cannot reproduce every contact and volume adjustment. A fixed-normal fit with improved weights puts 2,204 vertices within one degree at every sampled pose, but leaves severe localized shading errors; baking the normals also cannot replace all normal corrections.

The conservative skin draft restores the original weight distribution wherever the aggressive repair failed the surface or shading checks, then reconstructs a smaller residual corrective set. It permits fitted weights at 962 vertices, but only 116 differ from the original distribution by more than 0.001 in any joint weight. It keeps four influences and all original bones. Normalizing the exported weights introduces a measured 0.052 mm maximum reset difference. The base position, normal, UV and index arrays remain exact.

## Two concrete drafts

| Measurement | Reviewed reference | Conservative skin draft | Original-skin reduction draft |
|---|---:|---:|---:|
| Position / normal shapes | 221 / 356 | 156 / 176 | 154 / 174 |
| Total shapes | 577 | 332 | **328** |
| Raw GLB | 25.686684 MB | 15.444868 MB | **15.270560 MB** |
| Full packaged RLCZ | 13.063531 MB | 7.491126 MB | **6.895690 MB** |
| Corrective GPU buffer payload | 38.405120 MB | 22.097920 MB | **21.831680 MB** |
| New hold-out maximum position difference | — | 0.2371 mm | **0.1031 mm** |
| New hold-out maximum normal difference | — | 0.2036 degrees | 0.2037 degrees |
| Neutral/reset position difference | — | 0.0520 mm | **0 mm** |

MB is decimal. Packaged payloads include the complete 56-byte RLCZ header and were actually encoded and decoded back to identical GLB bytes. GPU numbers cover corrective buffers only, not total VRAM or GPU frame time.

The original-skin draft saves **10.416124 MB raw (40.55%)**, **6.167841 MB packaged (47.21%)** and **16.573440 MB of corrective GPU buffers (43.15%)**. Its base geometry, weights, joints, hierarchy, binds, textures, materials, bone animation arrays, clip clocks and mounted-shell metadata are exact. Only the corrective representation, its weight curves and logical actor-bound metadata change. Stored logical bounds preserve actor placement when the unused morph envelope changes.

Both drafts select a smaller set of pose bases at the existing 30 FPS knots. Normal basis endpoints are unit-normal poses because Godot normalizes those endpoints. Arbitrary PCA normal vectors would not retain their intended values. There is no new per-frame corrective solver: the client uses its existing animation, skinning and morph paths.

For the 328-shape draft, two fresh processes per version measured retained Godot static CPU allocations of **116.76 → 82.39 MB**, warm-file-cache component loading of **1.55 → 0.82 seconds**, and animation updates approximately **14–45% cheaper**, depending on the clip. Retargeted keys fall from 190,405 to 118,912 and tracks from 4,423 to 2,786. The allocation figure includes shared scene/library caches and the first actor. These isolated measurements exclude GPU rendering, other game systems and whole-client frame-rate claims; load and timing results vary with the machine and cache state.

The 332-shape skin draft passed 4,827 qualification states and then 4,827 new hold-out states, with shifted 240 Hz clip samples, off-grid queries and 2,016 blends per set. Qualification maxima were 0.253 mm and 0.249 degrees. The separate 328-shape control passed the new 4,827-state set. These are sampled bounds, not mathematical guarantees over every possible pose or transition. Fresh Blender imports additionally check all seven actions, original bone matrices and 119 independent clip poses per draft. Actual Forward+ client previews exercise all clips, 49 directed switches, reset/end behavior and camera/playback input; captures include close and side views of measured hotspots. Normal-map/tangent appearance still requires visual review.

The initial aggressive skin prototype saved bytes but produced up to 17.46 mm transition error and large localized normal differences. It is rejected. The storage savings in the conservative draft must not all be credited to skin repair: the unchanged-skin control is smaller and closer to the reference.

## What to do with the remaining corrections

Use the original-skin reduction draft for the next visual acceptance decision. Keep the base mesh unchanged; the tested base edits do not justify the neutral-shape change. Keep the residual dynamic corrections until an equivalent rig has been demonstrated.

For a larger structural reduction, the next useful rig experiment is targeted volume/contact controls around the front limb roots and rear feet, followed by a fit of bind normals and residual shading. Fit those controls against the corrected final surface, keep explicit neutral and all-clip keys, and test blended poses before removing any corresponding cache. Additional bones trade a small set of transform curves and skeleton work for dense per-vertex corrective data, but the amount recoverable with those controls has not yet been demonstrated. Simply running a corrective once and packaging the resulting neutral mesh does not reproduce these pose-dependent effects.

Open `godot-client/open-crystalback-corrective-comparison.bat` for the reviewed 30 FPS model beside the 328-shape original-skin draft. To inspect the separate skin experiment, run `python eloria-assets/tools/preview_tortoise_corrective_repair.py --variant skin` from the worktree. Both support synchronized orbit/zoom, all seven clips, scrubbing, speed and blended switches. Inputs are hash checked against the accompanying JSON receipt. Generated models and detailed authoring evidence remain in ignored `.local/tortoise-corrective-repair/` storage.

The [machine-readable receipt](crystalback-tortoise-corrective-repair.json) records exact input/output hashes, scope checks, per-category errors, runtime measurements and private evidence hashes. No native asset was replaced, and no changes were pushed.

## Fixed mesh bake review

The one-time bake is also available through `godot-client/open-crystalback-static-bake-comparison.bat`, or `python eloria-assets/tools/preview_tortoise_corrective_repair.py --variant bake`. The reviewed 30 FPS model is on the left; the fixed body positions and fixed normals, with all corrective shapes removed, are on the right. Original skin weights, bones and all seven bone animations remain intact. This is the audit's best constant least-squares mesh fit across training poses, rather than the mesh from one chosen animation frame.

The actual client export reproduces the predicted **97.735 mm maximum** surface difference at **Death_A, 2.55 seconds**. The preview has jump buttons for that pose and the largest sampled normal difference at **Jog, 0.2 seconds**. The maximum reset-shape difference is 88.13 mm. Its 8.86 mm RMS across all 5,368 vertices includes the unchanged shell; the earlier 11.25 mm RMS measures just the body. Static normal fitting removes runtime shading corrections too, so this candidate also exposes large localized shading differences.

The fixed bake is **1.558860 MB raw / 0.998255 MB packaged**, with zero corrective GPU buffers. It passes fresh Blender import/action checks and actual-client inspection of 909 states, including 168 directed crossfade states and reset. The large shape differences are intentional evidence for this visual experiment, not an equivalence qualification. The installed asset remains unchanged. `build_tortoise_static_bake.py` exports it from the preserved private audit fits, and the JSON receipt binds the fit and output hashes.

## Improved fixed bake V2

V2 fits the rest mesh and skin weights together, retaining the original 21 bones, bind matrices, all seven bone animations and four influences. It still has no runtime corrective shapes. The first joint least-squares fit suggested a 39.3 mm maximum difference. A further ten offline iterations give the worst training poses greater weight using a p=6 deformation objective, rather than optimizing average error alone. A fixed normal fit is recomputed for the new weights. Coincident vertices share positions and weights throughout; UVs, triangle indices and the shell remain unchanged.

| Same 4,827 client states, body only | First fixed bake | Improved V2 |
|---|---:|---:|
| Maximum position difference | 97.776 mm | **33.505 mm** |
| RMS position difference | 11.447 mm | **1.561 mm** |
| RMS normal difference | 7.367 degrees | 6.500 degrees |
| Maximum normal difference | 178.309 degrees | 177.116 degrees |
| Full packaged size | 998,255 bytes | 1,003,225 bytes |
| Corrective shapes / GPU buffers | 0 / 0 bytes | 0 / 0 bytes |

The first bake's exported mesh arrays are evaluated at the exact same native skeleton states for this comparison; source/V2 native bone matrices are checked equal. Thus the table excludes sampling differences and the unchanged shell. The denser sample set changes the first bake's measured maximum slightly from its earlier 97.735 mm result. V2 reduces maximum position error by about 66% and body RMS error by about 86%, for 4,970 additional packaged bytes.

V2 is an improvement, not an equivalent replacement. The largest remaining sampled position difference is at **Walk, 1.2433875 seconds**. Blended-pose position error reaches 29.54 mm. Reset/neutral position difference falls from 88.13 to 15.80 mm. Shading remains a major separate limitation: the static normals do not follow every pose-dependent surface change, with the largest sampled angular error at **Jog, 0.1975542 seconds**. The average surface fit improves much more than the shading fit.

Fresh Blender import checks cover 119 clip poses and unchanged bone matrices. Actual client testing covers 2,810 clip states, 2,016 directed crossfade states and reset, including shifted 240 Hz samples and off-grid queries outside the optimizer's training times. Neither this test nor visual approval is a continuous-time guarantee. The original zero-shape bake and the reviewed 30 FPS reference remain preserved.

Open `godot-client/open-crystalback-improved-bake-comparison.bat`, or use `preview_tortoise_corrective_repair.py --variant bake-v2`. It shows the reviewed 30 FPS model on the left and V2 on the right, with jump buttons for remaining position and shading differences. To rebuild from the preserved private fits, use `build_tortoise_static_bake.py --fit robust`; `--fit refined` also exports the earlier joint least-squares fit. These exports do not install either asset.

Further options are targeted helper joints for limb volume/contact and a small residual corrective set for the difficult poses. Helper joints would trade additional skeleton transforms and keys for per-vertex data; a residual set would trade some corrective storage/work for a closer match. Neither extension has yet been implemented or benchmarked for this bake, so their achievable quality and cost remain unmeasured. More fixed-mesh iteration alone cannot be assumed to eliminate the remaining pose-dependent deformation and shading.
