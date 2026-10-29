# Mossbound Stone Golem: shoulder review draft

The new shoulder draft adds a small body-attached stone socket, rounds the exposed end of the upper-arm stone and fixes the torso cap's centre weights. It preserves the improved V6 arm movement exactly. The shoulder reads as a rounded stone connection instead of the former flat fan; an articulated rim is still visible during deep bends.

The comparison shows the last reviewed, uninstalled V6 (`3cee2609...`) on the left and candidate `8d778fc385cc0b363ec0cde251fd478bd892385e3a77058608451cfc5a4b4483` on the right. This remains a review draft. The installed `e056751f...` Golem is unchanged.

| Component | Reviewed V6 | Shoulder draft |
| --- | ---: | ---: |
| Uncompressed GLB bytes | 1,967,072 | 2,000,032 |
| Vertices | 9,414 | 9,816 |
| Triangles | 3,138 | 3,272 |
| Native bones / active skin palette | 35 / 34 | 35 / 34 |
| Retargeted animation keys / tracks | 15,260 / 319 | 15,260 / 319 |
| Draw surfaces / corrective shapes | 1 / 0 | 1 / 0 |

The addition is **32,960 bytes**, about 33 KB. The [component benchmark](mossbound-stone-golem-shoulder-component-benchmark-v7.json) measured about 50 KB more retained first-actor static allocation, including shared caches. There are no new animated bones, keys or tracks. GPU rendering was not benchmarked; the mesh has about 4.3% more vertices and triangles. Lower candidate timing snapshots reflect uncontrolled scheduling variation and are not evidence of a speedup.

The torso-side cap previously averaged skin weights from arbitrary coincident representatives after the arm partition. Its 27 duplicated centre vertices therefore inherited substantial influence from the moving arm. They now follow the body-side clavicle control. The cover uses that same existing control, and the shallow rounded end uses the existing upper-arm control. Original textures and all 9,000 original surface vertices retain their positions, normals, UVs and skin fields.

Changes to retained V6 data are confined to 81 generated upper-cap vertices and the 27 torso-cap centre weights. Some old cap-centre ordinals now represent an inner ring, so their measured displacement is a deliberate geometry rewrite rather than arm-motion error. The remaining 9,306 retained vertices preserve exact posed positions and unit normals in the client. All animation channels, binds, clip durations and all 35 native bone worlds remain unchanged, including Ground Pound and animation blends. The forearm, fist, thumb, calf and foot motion remain exactly as reviewed in V6.

Two configured raw-client comparisons each cover 738 states across all eight clips, defaults, held ends, between-key poses and directed first-tick/frame-stepped transitions. All 1,044 candidate-derived cap peers have equal native positions and packed skin coefficients. The new socket and rounded end retain their face dimensions in those states within about one part per million. Independent GLB checks cover 1,311 poses. Fresh Blender imports and 280 paired renders cover the attack, other clips, RESET, transitions and shoulder failure poses.

This is still a hard stone articulation, with visible facets and a rim at some angles. It is not a seamless flexible shoulder or a collision guarantee. V6's changed gesture and earlier lowest-fist phase remain; this pass introduces no further retiming. The [V6 report](mossbound-stone-golem-rigid-arm-repair.md) records those inherited tradeoffs. Dense surface containment estimates are geometry evidence, not pixel occlusion or automatic visual acceptance.
