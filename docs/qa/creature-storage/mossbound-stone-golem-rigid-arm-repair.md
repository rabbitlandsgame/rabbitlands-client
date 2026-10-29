# Mossbound Stone Golem: solid-arm review draft

The new draft makes the right upper arm, forearm and fist into closed, rigid stone sections. They retain their shape through Ground Pound and all seven other animations, including client animation blends. This resolves the flattened stone and stretched sheets seen in the preceding draft, but introduces a more visibly articulated stone assembly and **substantially changes the visible arm motion**. It requires a new visual decision and has not been installed.

The comparison's left model is the last reviewed, uninstalled V5 (`f9a54ff9...`). The right model is `3cee2609447cbd0013fe1ebb07654c84d1e6b625c4ec32fc57aff7b332dec4c7`. The installed model remains `e056751f...`. Earlier rejected fitting experiments remain separate private evidence.

| Component | Reviewed V5 | Solid-arm draft |
| --- | ---: | ---: |
| Uncompressed GLB bytes | 1,947,032 | 1,967,072 |
| Native skeleton bones | 33 | 35 |
| Active skin palette joints | 32 | 34 |
| Vertices | 9,000 | 9,414 |
| Triangles | 3,000 | 3,138 |
| Draw surfaces / corrective shapes | 1 / 0 | 1 / 0 |
| Retargeted animation keys | 14,761 | 15,260 |

The increase is **20,040 bytes (1.03%)** versus V5, or 70,260 bytes versus the current installed model. The 414 added vertices close both sides of the shoulder, elbow and wrist separations. All original 9,000 positions, normals, UVs and triangle indices remain exact; textures and materials are unchanged. The natural surface partition contains 244 original fist faces, 158 forearm faces, 169 upper-arm faces and 2,429 torso/rest faces. Original rotation samplers are reused where appropriate; Ground Pound uses new support curves and a local wrist grip, at the 30 Hz delivery cadence.

The original anatomical animation channels remain exact, but the rendered arm follows a different physical support chain. The existing forearm support is redefined, two controls are added, and 16 torso vertices lose leftover forearm-support influence. The calf and foot repairs remain unchanged. The earlier thumb separation and its original geometry remain, while its skin now follows the new rigid fist control.

## Shape checks and visible tradeoffs

Two actual-client comparisons each cover 738 states across all eight animations, defaults, held ends, between-key wind-up poses and directed first-tick/frame-stepped switches. The 7,271 original vertices outside the declared affected region retain exact positions and unit normals versus V5. All 32 protected native bone worlds remain exact; the intentionally redefined forearm control is excluded from that assertion.

Every one of the 682 arm-piece faces, including the new caps, retains its edge lengths and areas in those native states, within about one part per million. Independent GLB evaluation covers another 1,633 poses and confirms the same shape retention. The engine's packed skin representation closes all 276 old-to-new cap boundary pairs and 270 duplicate cap corners exactly. These checks establish rigid pieces and closed caps, **not continuously welded joints or collision freedom**.

The capped stone ends open visibly during deep bends. Their joint centres remain aligned, but the corresponding rim points rotate apart; the largest measured rim separations are about 0.23, 0.34 and 0.31 model units at wrist, elbow and shoulder. The appearance is a three-stone articulated arm rather than a continuous flexible surface. Review the deep wind-up around 0.375–0.521 seconds from several angles.

The right arm's reach and grip differ across the animation set. Ground Pound has a revised wind-up and downstroke, with a reach-limited wrist target. On corresponding physical fist vertices, its lowest sampled point occurs at about **1.13 seconds rather than 1.57 seconds** in the authored reference. That is a 0.43-second phase change, even though all clip durations remain exact. Matching the original anatomical bone channels does not mean matching the visible fist path, hand orientation, impact timing or contact. Native comparison against V5 measures up to about 2.39 metres of local surface change during the fast wind-up; this is an intentional rig/gesture alternative, not a close-match compression result.

Fresh Blender imports, complete Ground Pound renders, all-clip start/middle/held-end views, RESET and selected transitions supplement the numeric checks. Additional renders cover the exact measured wrist, elbow and shoulder opening poses. The reviewer opens playing Ground Pound and retains the full animation selection, orbit, zoom and comment controls. Approval must apply to this exact new candidate.

## Runtime cost

The [component benchmark](mossbound-stone-golem-ground-pound-component-benchmark-v6.json) recorded about **130 KB more retained first-actor static allocation**, including shared caches. Ground Pound animation advance plus forced bone updates increased from 12.81 to 16.25 microseconds in these snapshots; Walk varied from 11.96 to 11.53 microseconds. Background activity and scheduling were uncontrolled, so these are scoped measurements rather than a causal speed or whole-game FPS claim. GPU rendering was not benchmarked. The candidate adds two bones and 4.6% more vertices/triangles while retaining one draw surface and zero corrective shapes.

The installed Golem and runtime metadata remain unchanged pending review of the different motion and articulated-joint appearance. The preceding [V5 report](mossbound-stone-golem-ground-pound-repair.md) remains a separate historical account of the partial forearm/calf repair.
