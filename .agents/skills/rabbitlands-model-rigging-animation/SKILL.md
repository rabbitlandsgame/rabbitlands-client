---
name: rabbitlands-model-rigging-animation
description: Rig, skin, animate, retarget, validate, and hand off Rabbit Lands GLB assets using the project's local rigging tools and runtime animation contracts. Use for players, creatures, and equipment; for choosing a rig or animation backend; for producing the seven standard creature clips; or for diagnosing deformation, locomotion, root-motion, import, and playback problems.
---

Paths are relative to the Rabbit Lands client checkout. Original assets, authoring stages, scripts and private memory are consolidated under `.local/asset-authoring/workspace/`. Read [the local authoring workspace](../../../docs/asset-authoring.md) for current tools, path relocation and historical receipt handling. Preserve Eloria lore and compatibility-sensitive identifiers.


# Rabbit Lands Model Rigging and Animation

Preserve the source mesh and create a new versioned stage for rigging and every material animation revision. Geometry, skin, skeleton, morph-target, clip, and manifest changes must be attributable and reproducible.

Read [references/asset-kinds-and-backends.md](references/asset-kinds-and-backends.md) before choosing a rig. For creatures, also read [references/creature-animation-contract.md](references/creature-animation-contract.md). Use [references/validation-and-handoff.md](references/validation-and-handoff.md) for every final delivery.

## Workflow

1. Audit the source from all sides. Record bounds, orientation, scale assumptions, primitives, materials, topology, disconnected islands, anatomy, likely joints, and known fused/thin surfaces.
2. Classify the asset as player, creature, socket equipment, or skinned equipment. Determine the body plan from geometry, not filename alone.
3. Establish the gameplay animation contract before authoring motion: required clips, up/forward axes, gameplay scale, FPS, loop policy, root-motion policy, durations, contact or release events, interruption behavior, and intended game camera. Record event times in seconds as well as source frames.
4. Establish final rest pose, root placement, and authoring-to-runtime basis. Select the rig backend and skeleton contract. Use `.local/asset-authoring/workspace/eloria-tools/rig_glb.py --help` as the current CLI authority. Dry-run batches before writing outputs.
5. Fit joint pivots to the actual geometry. Separate or rigidly bind distinct pieces deliberately. Paint weights with joint clearance and preserve anatomical ownership of faces, hands, feathers, horns, hair, cloth, and layered surfaces.
6. Select the animation method:
   - shared-library retargeting for compatible production skeletons;
   - body-plan-aware procedural motion for blockout or creatures whose motion is defined in project tools;
   - custom authored rig/motion for unusual anatomy, folded wings, tentacles, multiple heads, fused surfaces, or high-risk deformation.
   - video-derived motion using [Eloria Video Motion Fitting](../rabbitlands-video-motion-fitting/SKILL.md), with calibrated model renders, reviewed observations and category-aware transfer.
7. Author or retarget against the fitted rest pose. Retarget world-space motion deltas rather than copying raw local curves between unlike rests.
8. Block support, flight, contact, and recovery first. Review the motion at normal speed from the actual gameplay camera before adding secondary overlap or polish. Preserve locked event times and approved channels.
9. Bake and export GLB. Sample as densely as needed, then reduce curves by measured error rather than blindly resampling every channel.
10. Validate numerically, reopen in a fresh Blender import, and test in Godot. Review full cycles, between-key samples, action switching, and all sides at intended gameplay scale.
11. Package the final GLB, fitted rig, action mapping, rig graph, reports, preview evidence, source links, hashes, and limitations.

For the wolf video pipeline, read `.local/asset-authoring/workspace/memory/wolf-video-motion.md` from the workspace root before selecting a continuation input. The user-accepted walk is `.local/asset-authoring/workspace/generate_models/wolf_video_motion_pilot/delivery-v8`; the current technically validated attack/death candidate is `wolf_action_motion_pilot/delivery-v2`, pending user visual acceptance. Preserve the latest selected clip set when iterating a pilot. Read the motion-fitting skill's one-shot action reference before fitting these actions.

## Non-negotiable invariants

- Do not overwrite the raw Meshy/source GLB.
- Do not silently rename bones, clips, materials, or stable asset IDs.
- For animation-only revisions, preserve mesh, skeleton, bind matrices, skin weights, and rest transforms unless the revision explicitly documents a required correction.
- Preserve all required morph POSITION/NORMAL targets, activation tracks, and zero-weight reset tracks. A static fitted rig may not reproduce clip-specific corrections.
- Do not add weapons, VFX, projectiles, hitboxes, or anatomy merely because a runtime action name suggests them.
- Keep locomotion loops in place unless the runtime contract explicitly uses root motion. Eliminate accumulated root translation and yaw.
- Preserve approved actions while revising another clip. Newly introduced controls need explicit neutral/default keys in actions that do not animate them so poses cannot leak when the runtime switches clips.
- Treat structural validation as necessary but insufficient. Artistic deformation review is always separate.
- Report authored-source validation, export fidelity, Godot integration, and user visual approval as separate facts.
- For current Rabbit Lands runtime promotion, follow the motion-fitting skill's [integration reference](../rabbitlands-video-motion-fitting/references/rabbitlands-integration.md). Compare against the current client before replacing unrelated clips, preserve eight influences throughout validation/import, and account for runtime visual scale when matching stride speed.

## Fast local preview

Use `.local/asset-authoring/workspace/eloria-tools/preview_pipeline.py` to stage simplification, rigging, animation, texture capping, headless checks, and a Godot view while keeping numbered intermediate folders. Use `--no-view` for automated checks. The preview is a diagnostic; the versioned production pipeline and its manifest remain the delivery authority.

## Project precedents

- `.local/asset-authoring/workspace/generate_models/basic_creature_expansion_100_animated/` is the broad creature reference and current seven-clip delivery pattern.
- `.local/asset-authoring/workspace/generate_models/frost_stone_golem_animations/` is the strongest example of source audit, independent sampling validation, fresh-import rendering, contact tests, and hash-gated packaging.
- `.local/asset-authoring/workspace/generate_models/meshy_to_client/` documents player-rig retargeting with rest-pose-aware world-space deltas.
