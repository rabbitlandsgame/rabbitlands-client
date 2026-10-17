---
name: rabbitlands-video-motion-fitting
description: Fit reference-video motion to Rabbit Lands creature rigs and package it for transfer to compatible actors of the same anatomical category. Use for Meshy image-to-video pilots, correcting limb tracking, building category motion libraries, and validating fitted or retargeted GLBs.
---

Paths are relative to the Rabbit Lands client checkout. Original assets, authoring stages, scripts and private memory are consolidated under `.local/asset-authoring/workspace/`. Read [the local authoring workspace](../../../docs/asset-authoring.md) for current tools, path relocation and historical receipt handling. Preserve Eloria lore and compatibility-sensitive identifiers.


# Rabbit Lands Video Motion Fitting

Use a calibrated render of the actual fitted model as the image-to-video input. Keep source models, video, observations, motion package, transferred exports and evidence in a versioned stage.

For continuing the project wolves, read `.local/asset-authoring/workspace/memory/wolf-video-motion.md` from the workspace root before choosing a starting artifact. It records accepted versus pending revisions and actor-specific lessons; verify the referenced manifests against later user instructions.

Use `eloria-assets/tools/video_motion_cli.py` and `eloria-assets/tools/video_motion/`. Read [the workflow](references/workflow.md) for commands and tracking review, and [category transfer](references/category-transfer.md) before reusing a clip.
For stride reach, planted-paw polish or sliding, read [contact and stride fitting](references/contact-polish.md).
For collars, rigid ornaments, dorsal skin movement or distal tail polish, read [attachments and secondary motion](references/secondary-motion.md).
For attacks and death/fall actions, read [one-shot actions](references/one-shot-actions.md). These need event timing, changing support and explicit endpoint handling; the looping walk contact model is not their action contract.
For a batch of wolf-like actors with differing rigs, read [family transfer](references/family-transfer.md) for anatomical maps, long-paw offsets, rigid armor supports and endpoint continuity.

For jerky one-shots or weak forward bite reach, read [temporal quality and native muzzle reach](references/temporal-quality.md).
For incorrect leg folding or a lunge with the wrong body rise despite valid contacts, read [the anatomical motion audit](references/anatomical-motion-audit.md). Review physical source and target chains from multiple model angles before reusing semantic control names.
For stretched foreleg skin, complete-tail centering or contact changes after a weight repair, read [skin and tail repair](references/skin-and-tail-repair.md).
For merging selected animation assets into the current Rabbit Lands client, read [runtime integration](references/rabbitlands-integration.md). Preserve the current client's unrelated clips, import fidelity, eight-weight evaluation and actual scaled stride speed.

The gait solver is a side-view planar canine pilot. One-shot controls add native body roll, lateral limb folding, head counter-roll and jaw arcs. Those lateral choices need explicit review because a single side video does not identify them uniquely. A matching silhouette does not certify hidden limbs, interactions with props or another anatomical family. New categories need their own profiles, constraints and pilot.

- For motion fitting, preserve meshes, skin weights, bind/rest transforms, textures and unrelated clips. A requested skin/rig defect repair is a separate versioned input, with explicit changed-vertex scope and preservation checks; do not transfer source skin repairs as category motion. Follow the Eloria rigging/animation skill for runtime clip/event contracts.
- Distinguish a provider-created video from an accepted motion source. Reject camera changes, cuts, anatomy changes and inappropriate motion; retain task IDs and rejected takes.
- Paid generation requires scoped authorization. Existing approval covers the authorized job; record its exact task ID, inputs, prompt, settings, quoted credits, approval and downloaded-video hash. Resolve an unknown outcome before considering another paid submission.
- Automatic segmentation, optical flow, paw detection and cycle selection produce candidates. Inspect each limb through a complete stride; a silhouette can repeat after half a stride while near/far identities exchange. Keep merged or hidden observations at low confidence and record identity corrections.
- Prefer neutral initialization for unfamiliar rigs. A library clip is an optional seed, never video evidence; its full local transforms may not be representable by planar controls.
- Fit visible landmarks and deformed silhouette with bounded joint rotations and temporal constraints. Do not change bone lengths, skin weights or geometry to hide a tracking failure.
- Deliver the category motion package separately from actor exports. It carries semantic roles, canonical axes, normalized sole trajectories, support contacts, timing and provenance. Do not copy raw local quaternion curves between unlike rest poses.
- Adapt target proportions with contact-aware IK. Extra target controls can start neutral; changed anatomy still needs review. Both actors having four legs is insufficient compatibility evidence.
- Compare per-paw reach with the reference independently of silhouette overlap. Contact locking must retain the reference's stride. A smooth silhouette fit can still produce a short shuffle.
- Match the intermediate limb pose as well as the paw path. Review hinge direction and airborne folding; contact checks alone do not catch a straight-looking swing. Confirm whether a named ankle is a serial joint or a separate weighted helper.
- For bites, verify upper snout versus lower-jaw skin ownership and the target's native hinge policy. For collapses, check early elbow folding and head/chest drop at the reference timestamps independently of final ground contact.
- Review the shoulder attachment separately from the elbow and paw. Fur can hide the pivot; label an authored placement preference accordingly. Transfer chest-relative shoulder intent through native-length offsets, and inspect shoulder-owned decorations before accepting a large rotation.
- For in-place walks, evaluate sliding after adding the declared actor forward speed. All stance paws share that speed. Fit the evaluated paw/heel surface, including ankle-weighted vertices, and handle low tails separately from support contacts.
- Test exported keys and between-key poses. Video cadence, package sample rate and GLB key density are separate quantities. Retain denser keys when reduction would introduce floor penetration or deformation error.
- Review the source and a transferred actor at normal speed from game, front and rear cameras. Report source fit, numerical preservation, Blender reimport, Godot playback and visual acceptance separately.
- For tails, prioritize coherent section shape over a single endpoint residual. Adapt amplitude and bend distribution to the target's native rest chain, and include an opposite isometric or rear quarter view when the body hides the tail.

The accepted walk is `.local/asset-authoring/workspace/generate_models/wolf_video_motion_pilot/fit-v13` / `delivery-v8`, using Moorland Dire Wolf as source and Dire Wolf as transfer target. Its acceptance receipt identifies the unchanged GLBs and motion hash. The current attack/death candidate is `.local/asset-authoring/workspace/generate_models/wolf_action_motion_pilot/delivery-v2`, technically validated and awaiting user visual acceptance. Start new action pilots with the accepted animated inputs; continue existing pilots from their latest selected stage and preserve unrelated clips. Record later acceptance separately rather than rewriting the motion payload. Runtime replacement remains separate.

For the integrated seven-actor development selection and current engine fidelity requirements, also use [creature-animation integration](../rabbitlands-creature-animation/SKILL.md) and `docs/creature-video-motion.md`. Original source-pilot acceptance remains distinct from the later authorized runtime publication.

For the approved Moss Bear source and current imported bear family, read [ursine transfer](references/ursine-transfer.md). It covers nonanatomical imported parenting, native planted-paw orientation, separate skin preparation and contact-aware death release. Retired procedural bears are excluded.

For Rabbit and Jackalope hopping, native head/forelimb skin repair and authored attack/death, read [rabbit-family motion](references/leporid-transfer.md).
