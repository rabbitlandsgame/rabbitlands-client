# Asset kinds and backend selection

## Player

- Must use the canonical 65-joint Eloria player skeleton with exact required bone names.
- Equipment compatibility depends on the skeleton contract; a plausible humanoid rig is not sufficient.
- Use the shared animation library and rest-pose-aware retargeting where possible.
- Validate equipment rebinding and socket behavior by bone name.
- Player bodies play only the shared library named by `animationLibrary` in `godot-client/data/actors/models.json` (`Universal_Animation_Library.glb`); clips baked into a race GLB are not played. `godot-client/src/actors/native_animation_importer.gd` copies library keys onto the body by bone name without bind compensation, so a body's bind pose must equal the library's `Rest_Pose` clip. The library's node defaults are a posed state, not a rest.
- glTF carries no loop flag. A clip loops only when the action map's `loopingClips` (`godot-client/data/animations/luminous.json`) lists it; keep death, pain and transitions one-shot. `godot-client/tests/test_protocol.gd` and `godot-client/tests/test_animation_looping.gd` pin both directions.
- Locomotion playback speed is the actor's travel speed divided by the action's `strideMetresPerSecond`, clamped to 0.35-3.5 (`ReplicatedActor3D._playback_speed_for`). Re-measure the stride when a travel clip changes.
- Verify any rig-level rest scale in the engine, not with an offline probe. In a client measurement a joint rest scale did not reach the skinned body, because the import rebuilds binds from the scaled rest, while `BoneAttachment3D` children inherited it.

## Creature

- May use its own skeleton, sized and oriented to the actual body plan.
- Supported body-plan routing includes biped, quadruped, hexapod, serpent, flyer, and hover; unusual anatomy may require a custom graph.
- Learned riggers can provide a starting point, but they invent joints and require inspection. They are not evidence of anatomical correctness.
- Human motion models must not be forced onto non-bipeds. Use body-plan procedural, AniMo/OmniMotionGPT when deliberately integrated, or custom authored motion.

## Equipment

- Socket props usually have no skeleton and attach to a named runtime socket.
- Skinned garments must bind to the shared player rig and be tested through the full relevant motion range.
- Avoid an extra incompatible armature inside equipment assets.

## Local CLI

`.local/asset-authoring/workspace/eloria-tools/rig_glb.py` supports:

- rig backends: `auto`, `blender`, `pinocchio`, `rignet`, `unirig`, `riganything`, `magicarticulate`, `mia`, `none`;
- animation backends: `auto`, `library`, `procedural`, `mdm`, `momask`, `motiongpt`, `animationgpt`, `animo`, `omnimotiongpt`, `none`;
- kinds: `player`, `creature`, `equipment`;
- bone naming: `auto`, `eloria`, `generic`;
- body plans and skeleton modes;
- action lists, animation library, bone map, FPS, profile output, batch patterns, reports, dry-run, and overwrite controls.

Use `--anim library` for production retargeting when a compatible library and map exist. Use procedural animation as an explicit blockout or when a project generator defines the intended creature motion. Use `--dry-run` before batches and preserve reports.

The local batch creature pipeline is `.local/asset-authoring/workspace/lowpoly_rigged/`: `run_pipeline.py` builds from a manifest such as `models.meshy.json` (per-model repair options), acceptance is recorded in `models/<slug>/review.json`, and the donor-free `auto_animate.py` is described in `REPORT-auto-animate.md`. It runs under `eloria-tools/.venv`, which was not migrated; recreate that environment before running it.

## Rig review

- Joint centers sit inside the intended articulation volumes.
- Left/right and parent/child assignments match geometry.
- Bone rolls and local axes are stable.
- Skin weights sum to one and contain no invalid joint indices.
- Influences are pruned to the destination runtime's supported limit and renormalized; recheck that pruning did not remove the last useful influence.
- Rigid accessories follow one intentional owner.
- Deformable transitions blend narrowly enough to avoid rubbery motion.
- Feet, paws, claws, wing roots, heads, jaws, tails, and tentacles deform without tearing or detaching.
- Rest transforms and inverse bind matrices round-trip through GLB import/export.

When a limb collapses, inspect evaluated bones, IK reach, pole direction, targets, and interpolated trajectories before repainting weights. A rig failure can resemble a skinning failure. Assess ground contact from the deformed sole, paw, claw, or body surface—not from the controller or ankle origin alone.

Keep global placement/root travel separate from local body motion. Retain non-deforming runtime bones when they carry required hierarchy, heading, or body motion; do not delete them merely because they have no weights.
