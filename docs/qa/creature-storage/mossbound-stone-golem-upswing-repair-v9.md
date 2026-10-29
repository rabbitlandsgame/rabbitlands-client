# Mossbound Stone Golem: controlled upswing review draft

The Ground Pound wind-up now makes one controlled lift with a modest elbow bend. The previous shoulder-roll fix left the inherited arm-aiming loop intact; this draft deliberately replaces that early visible arm and fist motion. It rejoins the existing raised pose before the main strike. The other seven animations and the rounded shoulder geometry are unchanged.

The comparison displays last-reviewed, uninstalled V8 (`4929864488eac9c6937bdbef2267892f6bff86f1bf71c48630ed649bd8d80d16`) on the left and V9 (`5230858a864b77cb29c147f48f44e73b46e307be5b2fe43ce15b8bec9f3bc7e3`) on the right. The installed `e056751f...` Golem remains unchanged. This is an unapproved motion-repair draft.

Four existing helper rotation tracks change only at source keys 1–19. Key zero and keys 20–79 retain literal clocks and values. The source join is **0.668354 seconds**, including about 67 ms of settling beyond the old wrist apex. The anatomical hand's previously shared sampler is preserved by cloning the physical-hand output. Geometry, skin, binds, hierarchy, materials, textures and all original anatomical animation curves remain unchanged.

Independent evaluation covers 2,799 dense Ground Pound times and 453 bounded surface observations across all eight actions. During the replaced prefix, cumulative visible upper-stone rotation falls from **565 to 129 degrees**, and peak angular speed from **2,271 to 288 degrees/second**. Forearm rotation falls from 477 to 195 degrees; fist rotation falls from 675 to 198 degrees. The fist rises without the previous repeated height reversals, with peak vertical speed falling from 20.72 to 1.69 model units/second. These source/palette measurements are separate from actual-client observations.

The lift retains a smooth, limited material-orientation adjustment of about 78 degrees. It is not zero-twist. A single modest elbow flex avoids the earlier deep fold while preserving the eventual raised pose. The source join preserves pose continuity; finite velocity changes remain, so this does not claim continuous velocity or a complete physically simulated attack.

Two configured native-client comparisons each cover **2,210 states**, including all eight actions, defaults, held ends, directed first-tick and frame-stepped switches, key midpoints and dense join probes. Against V8, all **32 protected bone worlds** and all **7,608 vertices outside the 2,208-row arm domain** retain exact world positions and unit normals. All candidate positions and normals are finite, and actor/model placement and selection remain unchanged. The large whole-arm error against V8 is intentional early-motion reauthoring, not a close-match fidelity result.

Native import resampling extends the changed interval slightly beyond the literal source join: the sampled whole-mesh difference is 6.97 world-mm at 0.668354 seconds and 1.75 mm at 0.691667 seconds. All **81 tested Ground Pound poses from 0.700 seconds through the end** have exact positions and unit normals against V8. This is sampled native equivalence, not an assertion about every continuous time or a velocity-continuous join. A further **1,592 default, other-action, held-end and RESET states** preserve the complete mesh exactly, including the Ground Pound held end. All 1,044 native cap peer pairs retain equal positions and packed skin coefficients.

Fresh Blender imports pass for both models. Final visual qualification includes **254 paired captures**, covering the full Ground Pound from front and rear, all other actions, RESET, first ticks, frame-stepped switches and the join. The 44 paired non-attack/RESET views are pixel-identical. A further 62 diagnostic pairs are retained separately. Whole-body framing stays within the viewport.

| Component | Reviewed V8 | Upswing V9 |
| --- | ---: | ---: |
| Uncompressed bytes | 2,007,416 | 2,009,044 |
| Native bones / active skin palette | 36 / 35 | 36 / 35 |
| Retargeted keys / tracks | 15,344 / 323 | 15,344 / 323 |
| Vertices / triangles | 9,816 / 3,272 | 9,816 / 3,272 |
| Draw surfaces / corrective shapes | 1 / 0 | 1 / 0 |

The draft adds **1,628 bytes** and no new bone, key, track or geometry workload. The [component benchmark](mossbound-stone-golem-upswing-component-benchmark-v9.json) reports fresh-process animation-update medians of 13.51 versus 10.65 microseconds for Ground Pound and 12.36 versus 13.28 for Walk. Scheduling is uncontrolled; these snapshots establish neither a speedup nor a meaningful slowdown. The 616-byte allocation difference is negligible variation in first-actor allocations including shared caches. GPU time, VRAM and whole-game FPS were not measured.

Existing articulated stone rims, the earlier V6 strike interpretation and low-point phase, reach limits and any pre-existing collision/contact issues remain. This draft requires an exact-version visual decision before installation. The [previous motion report](mossbound-stone-golem-shoulder-motion-repair-v8.md) explains why removing axial spin alone did not resolve the upswing.
