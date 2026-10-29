# Mossbound Stone Golem: forearm twist review draft

The remaining Ground Pound rotation comes from the forearm stone rolling about its elbow-to-wrist axis. V10 stabilizes that stone while preserving the improved V9 lift, upper arm, fist path and all existing bone motion. It is a new unapproved draft; the installed Golem remains unchanged.

The comparison uses uninstalled V9 `5230858a864b77cb29c147f48f44e73b46e307be5b2fe43ce15b8bec9f3bc7e3` on the left and V10 `61d9bbc85cf6d85d8ec1e62fd0dc5dbb01153f36449471d69de6854d2cfeaeea` on the right. A small control, parented to the existing physical forearm, owns only its closed 200-face, 600-vertex surface. It rotates about the existing elbow-to-wrist axis and is neutral outside Ground Pound. No geometry, weight values, material, texture or original animation channel changes. Only those 600 rows' joint ownership changes.

A trial that rekeyed the existing forearm and compensated the hand matched the keys but drifted by 33 model-mm and 13.7 degrees at the hand between keys. The separate surface control avoids that downstream error. It uses a transported frame relative to the **visible upper-arm stone**, with a smooth shortest terminal orientation adjustment. Measuring against the hidden kinematic parent would conceal some of the visible twist.

Independent dense evaluation reduces the forearm's visible-upper-relative transported roll range from about **312 to 48 degrees** across Ground Pound. Lift roll falls from about 184 to 8 degrees; recovery roll falls from about 79 to 19 degrees on the independent phase grid. The remaining orientation adjustment is gradual. A brief approximately **7.5-degree deviation** from the smooth closure trend remains near 1.084 seconds during the fast downstroke. Focused off-grid client captures include this interval; no extra sampling keys were added. Existing fast aiming remains, so this is not a claim that all forearm angular motion is slow or twist-free.

Two actual native-client comparisons each cover **2,282 states** across all eight clips, default/RESET, held ends, key midpoints, former failure times and directed first-tick/frame-stepped switches. Against V9, all **36 existing native bone worlds** and all **9,216 vertices outside the forearm** retain exact world positions and unit normals. Candidate positions and normals are finite, and actor/model placement and selection are unchanged. The forearm surface deliberately changes orientation; its source-distance error is not a close-match fidelity result.

A separate actual-client audit evaluates 235 Ground Pound poses using the rendered forearm control relative to the visible upper arm. On that coarser transport grid, roll range falls from **313.81 to 46.19 degrees**; this does not certify the dense source's exact 48.33-degree value in the client. The elbow-to-wrist axis is unchanged within a normalized-vector difference of 5.8e-7. All **1,655 default, other-action, held-end and RESET states** preserve the complete mesh exactly. All 1,044 native cap peer pairs retain equal positions and packed skin coefficients.

Fresh Blender imports pass all eight actions for both files. Visual qualification combines 188 paired full-action/off-grid diagnostic captures with 84 supplement pairs: **272 pairs / 544 PNGs**. It includes lift, strike, recovery, the 1.084-second residual, unrelated actions, RESET and switching. Three tight diagnostic closeups crop only unchanged fist tips by at most 1.55%; the changed forearm remains visible. Six additional whole-body witness pairs cover those same times from two views. The focused diagnostic is reused unchanged and bound to the same final model hash.

| Component | Reviewed V9 | Forearm V10 |
| --- | ---: | ---: |
| Raw GLB bytes | 2,009,044 | 2,016,188 |
| Native bones | 36 | 37 |
| Retargeted keys / tracks | 15,344 / 323 | 15,428 / 327 |
| Vertices / triangles | 9,816 / 3,272 | 9,816 / 3,272 |
| Draw surfaces / corrective shapes | 1 / 0 | 1 / 0 |

The [component benchmark](mossbound-stone-golem-forearm-component-benchmark-v10.json) records **7,144 extra raw bytes**, one additional native bone and about **13 KB** more retained first-actor static allocation, including shared caches. This is not per-instance memory or VRAM. Timing snapshots vary with scheduling and establish no causal speedup or whole-game FPS result. GPU rendering was not benchmarked. The actual installed `e056751f...` model is older: 1,896,812 bytes and 30 native bones; V10 is 119,376 bytes and seven bones above it, including the preceding uninstalled repairs.

The delivery stays at 30 samples/second with exact clip lengths and endpoints. Existing separated stone joints, strike interpretation, low-point timing and collision/contact limits remain. Review the exact draft before installation. The [V9 report](mossbound-stone-golem-upswing-repair-v9.md) describes the retained single-lift repair.
