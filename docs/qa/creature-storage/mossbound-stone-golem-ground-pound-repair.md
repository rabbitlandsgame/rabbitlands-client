# Mossbound Stone Golem: Ground Pound repair draft

The new **unapproved partial repair** keeps the forearm and calf stone sections from collapsing while preserving the original attack's bone motion, hand path and timing. It also corrects a root-owned foot corner and removes remaining arm influence from the leg-side cap. The earlier detached thumb and compact fist are retained.

The reviewer's left side is the **previous, uninstalled V4 draft**; the right side is candidate `f9a54ff96ebb62738e0e14630f9640958eea963274b181e76ed9915233bf5fd0`. The installed Golem remains `e056751f...`. No runtime replacement or push is part of preparing this draft.

| Component | V4 | New draft |
| --- | ---: | ---: |
| Uncompressed GLB bytes | 1,896,812 | 1,947,032 |
| Active skin palette joints | 30 | 32 |
| Native Godot skeleton bones | 30 | 33 |
| Retargeted animation keys | 12,780 | 14,761 |
| Corrective shapes | 0 | 0 |
| Vertices / body surfaces | 9,000 / 1 | 9,000 / 1 |

The increase is **50,220 bytes (2.65%)**. Two new controls store ordinary rotation/translation curves at the delivery cadence; an existing ancestor also becomes a native skeleton bone under the identity wrapper. Vertex positions, normals, UVs, triangle indices, textures, materials and all original animation sampler values remain unchanged from V4. The controls supply motion about actual mesh-section centres, avoiding the off-axis pivots that failed in a direct rigid-bone trial.

The [final component benchmark](mossbound-stone-golem-ground-pound-component-benchmark-v2.json) measured about **0.30 MB** more retained static allocation for the first actor, including shared caches. Animation advance plus forced bone updates took roughly 9–12 microseconds in these snapshots. One fresh process per model and uncontrolled scheduling do not establish a speedup or a whole-game FPS result. GPU rendering was not benchmarked.

## Validation and remaining limits

Two actual-client comparisons each covered 490 states across all eight clips, defaults, held ends and first-tick/frame-stepped switches. All 30 original bone world transforms remain exact. Outside the 1,419 changed skin rows, the other 7,581 vertices and their unit normals remain exact relative to V4. The complete vertex mapping is identity; skeleton bones are matched by name because the wrapper changes their paths and indices.

Independent checks confirm the rigid forearm/calf cores retain their rest section widths across the animation set, and the original hand strike trajectory is unchanged. All 19 cap boundary/centre pairs remain coincident with exactly matching native packed skin coefficients. Fresh Blender import and 270 paired rendered captures cover a complete Ground Pound cycle, all eight clip midpoints, additional failures, RESET and selected transitions.

**This is not a complete tearing fix.** A pointed shoulder/upper-forearm facet and wrist/ankle creasing remain visible. Some local boundary area/strain metrics still worsen even though the large core collapse improves. The fixed stone sections are fuller than the previously compressed surface, so matching the bad reference numerically is not the acceptance criterion. One copied render-scope sentence names an earlier candidate; the sealed job fixtures, actual render placement hashes and separate annotation identify the final `f9a54ff9...` payload correctly.

The local reviewer now uses source-based framing rather than the old oversized gameplay bounds. **Commented pose** jumps to the early Ground Pound wind-up. Rotate, zoom and play the whole attack before accepting; the draft remains separate from the installed model. See the [full QA receipt](mossbound-stone-golem-ground-pound-repair-v5.json) for hashes, scopes and limitations.
