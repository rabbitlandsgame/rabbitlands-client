# Comment repair batch 01 — review drafts

Update, 2026-10-28: the user accepted all five exact versions below and requested installation. They are now installed; [accepted-repair-delivery.json](accepted-repair-delivery.json) binds their hashes, approval events, qualified metadata and retained limitations. The following review-stage findings remain historical evidence, including the original pre-acceptance status.

These five candidates are **new, unapproved review drafts**. They have not replaced the installed models. Their local repairs intentionally change selected geometry, skinning or animation, so none is described as a universal fidelity pass or lossless conversion.

Separately, 191 previously approved models were installed in commits `fb61cb2d` and `1b5002ec`: their raw GLBs fell from **1,985,636,548 to 259,808,988 bytes**. That installation does not approve these five repairs. **22 of the 27 commented actors remain queued.**

## Candidate sizes

“Before” is the previous draft that received the comment, rather than the original corrective-heavy source. Sizes are raw GLB bytes, not compressed installer sizes. All five new drafts have zero corrective targets.

| Creature | Previous draft | New repair draft | Change | New SHA-256 prefix |
| --- | ---: | ---: | ---: | --- |
| Skeleton | 683,740 | 1,265,036 | +581,296 | `4f5c4b538e04` |
| Tengu | 675,900 | 675,900 | 0 | `e5fca05f5671` |
| Giant Wasp | 1,383,972 | 1,481,000 | +97,028 | `3ba6501be3dd` |
| Heartwood Treant | 1,480,724 | 1,480,724 | 0 | `fe4cb0869906` |
| Nightweave Spider | 1,089,072 | 1,089,356 | +284 | `3155e74a9021` |

## Changes and review limits

- **Skeleton:** Thirty-eight island controls restore intact gait bones, stature and the previously erased breakup death at 30 Hz. Original bone curves remain. Across 380 client states, original-source clip error is 54.63 mm maximum / 2.97 mm RMS; default/RESET maximum is 0.085 mm. Rigid death-to-live rotation differs from source morph collapse by up to 487.40 mm. Feet lose some flex; normals follow rigid geometry rather than the inconsistent source field. Full-speed transition media and seeded effects are not newly qualified. The 60 Hz alternative showed no clear sampled visual benefit for another 224,252 bytes. See [measurements](skeleton-rigid-island-repair.json).
- **Tengu:** Eight thumb-tip vertices receive a restored contour and local hand skinning, removing the inspected thumb-to-thigh web. The other 4,374 vertices, all bones and placement are unchanged across 490 client states; no bones or surfaces are added. Blender recomputes corner normals within the cap/boundary ring, so editor-imported shading equivalence is not claimed. Other bake approximations remain.
- **Giant Wasp:** Four controls make 240 wing-panel vertices rigid, retaining original curves and nonpanel attributes. Across 490 client states, panel edge-length change falls from 248.56% to 0.0000225%. Body deviations remain: source comparison reaches 199.71 mm during a switch and normal differences reach 166.13 degrees. Finite PBR captures cover all eight clips; this local wing fix does not establish whole-body equivalence.
- **Heartwood Treant:** Ankle skinning changes 106 rows in 39 complete coincident groups, preserving geometry arrays, curves, binds and materials; no bones/surfaces/slots are added. Outside vertices and bones are unchanged in 380 client states. Across 1,292 native poses, maximum excess edge stretch falls from 294.96% to 107.77%; at the exact Jog comment pose, 117.99% becomes 39.97%. Final client captures show a smoother, less pinched ankle crease, but only partial improvement. Substantial stretch remains, and overall maximum source-position error worsens from 198.76 to 215.44 model-space mm.
- **Nightweave Spider:** Restoring 38 physical pieces to existing owner bones repairs the abdomen and middle leg, retaining 65 bones and the surface count. Standalone clips differ by 6.76 mm maximum / 0.40 mm RMS; sampled Walk/Jog retain at least three supporting tips. Pieces retain shape during blends. However, death-to-live arcs differ by up to 193.60 mm and dip 99.25 mm below the inherited stance plane, which is not game-ground world zero. A joint-opening tip-pivot alternative was rejected.

## Measured CPU and allocation tradeoffs

Isolated headless measurements use one fresh process per variant, warm OS file cache, nine batches of 1,200 updates per clip after warmup, including skeleton transforms. They exclude GPU rendering/skinning and whole-game FPS. Retained allocation includes scene/library caches; it is not resident RAM. No cross-process confidence interval was measured.

| Creature / variant | Native bones | Jog update, µs | Other measured update, µs | Retained Godot allocation, decimal MB |
| --- | ---: | ---: | ---: | ---: |
| Skeleton sampled source | 19 | 16.86 | Death: 14.16 | 40.99 |
| Skeleton previous broken draft | 19 | 6.22 | Death: 3.60 | 10.17 |
| Skeleton repair draft | 58 | 27.38 | Death: 25.34 | 12.46 |
| Giant Wasp previous draft | 70 | 12.28 | Fly: 6.51 | 11.54 |
| Giant Wasp repair draft | 75 | 17.58 | Fly: 10.32 | 11.99 |

The added controls cost CPU time. Skeleton retains substantially less allocation than its corrective-bearing source, but more than its broken zero-bake. No timing or total-memory result is inferred for the other three repairs. See the [Skeleton component receipt](skeleton-component-benchmark.json) and [Wasp repair receipt](giant-wasp-rigid-panel-repair.json).

All five require a new user review before installation. Numeric, Blender and selected capture checks do not confer artistic acceptance.
