# Mossbound Stone Golem: shoulder-spin review draft

The new draft removes the shoulder stone's large axial spin during Ground Pound while preserving the forearm and fist paths, the rounded V7 geometry and the other seven animations. It adds one control for the shoulder stone rather than changing the strike or repainting the rest of the arm. The inherited quick wind-up and elbow aiming remain; this is a targeted spin correction, not a complete reauthoring of the attack.

The review compares uninstalled V7 (`8d778fc3...`) on the left with candidate `4929864488eac9c6937bdbef2267892f6bff86f1bf71c48630ed649bd8d80d16` on the right. The installed `e056751f...` Golem remains unchanged.

The IK frame previously projected an animated reference axis onto the arm's aiming plane. Near alignment, small changes to that reference produced very large twist changes. The new control counteracts that twist around the fixed shoulder-to-elbow axis, retaining the existing joint centres and downstream motion. It is neutral outside Ground Pound.

Independent dense evaluation covers 3,792 poses, including 2,805 Ground Pound times. The rendered shoulder control's transported axial-roll range falls from **365.05 to 4.15 degrees**, and recovery roll falls from 347.98 to 1.65 degrees. Peak axial-roll speed falls from about 4,776 to 5.1 degrees per second. These are axial-twist measurements, not total upper-arm rotation. The original aim still travels about 798 degrees cumulatively and has a peak speed near 2,271 degrees per second; the early wind-up retains a sharp reversal.

An additional actual-client check samples the rendered control at 127 attack poses, including key midpoints and former failure times. On that coarser transport grid, axial range falls from 370.35 to 7.84 degrees. This is a separate measurement from the dense GLB result; it does not certify an exact 4.15-degree native range. It confirms the large visible turn is removed in the client. Full-motion paired sequences and temporal strips supplement the numeric result.

| Component | Reviewed V7 | Spin-control draft |
| --- | ---: | ---: |
| Uncompressed bytes | 2,000,032 | 2,007,416 |
| Native bones / active skin palette | 35 / 34 | 36 / 35 |
| Vertices / triangles | 9,816 / 3,272 | 9,816 / 3,272 |
| Retargeted keys / tracks | 15,260 / 319 | 15,344 / 323 |
| Draw surfaces / corrective shapes | 1 / 0 | 1 / 0 |

The addition is **7,384 bytes**. The [component benchmark](mossbound-stone-golem-shoulder-motion-component-benchmark-v8.json) measured about 13 KB more retained first-actor static allocation, including shared caches. There is one extra animated bone and no extra geometry or draw surface. Timing snapshots varied; they do not establish a speedup, GPU cost or whole-game FPS effect.

All positions, normals, UVs, triangle indices, weight values, materials and textures remain exact. Only the joint index for the 834 upper-stone vertices changes. Every old node, bind and animation channel is retained. Two configured raw-client comparisons each cover 1,418 states across eight clips, defaults, held ends and directed first-tick/frame-stepped switches. All 35 old native bone worlds and the 8,982 vertices outside the upper stone retain exact positions and unit normals against V7. Another 898 default, non-attack and held states preserve the complete mesh exactly; 44 paired non-attack/RESET renders are pixel-identical. All 1,044 native cap peers remain closed with equal packed skin coefficients.

Fresh Blender imports and 232 paired captures cover the full attack, other actions, RESET and selected transitions. The inherited articulated rims, brisk swing and earlier V6 fist phase remain visible. This is an uninstalled review draft requiring an exact-version visual decision. The [V7 shoulder report](mossbound-stone-golem-shoulder-repair-v7.md) records the retained socket and rounded cap.
