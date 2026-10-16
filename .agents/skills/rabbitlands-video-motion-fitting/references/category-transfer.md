# Category transfer contract

The initial contract is `quadruped` / `canine`: four individually identified limbs, fore/hind distinction, compatible hinge chains and a canine gait. It does not establish transfer to horses, arthropods or unusual monsters.

A rig profile maps driver, hips, chest, head and optional neck/tail roles. Each limb has anchor, upper, lower, optional ankle and foot roles. Sole markers come from the actor's surface rather than its ankle origin. The initial automatic mapper recognizes the project's named wolf rigs; unnamed bones require explicit reviewed maps.

Bone names, lengths, rest orientations and extra joints may differ. Inspect hierarchy and marker ownership. The original schema-version-1 motion package contains:

- category/subcategory, clip, loop and root-motion policy;
- sample times and duration, separate from export key density;
- ordered semantic planar controls and body-height motion;
- sole displacements in canonical depth/up/forward coordinates, normalized by each source leg's length;
- support/contact intervals and source role map, sizes, hashes, camera and video provenance;
- fit metrics, depth policy and acceptance status.

Transfer reconstructs controls around the target's canonical depth axis in its own rest pose. It scales body-height motion by height and paw excursions by each target leg's length, then solves target rotations against sole trajectories and support constraints. Extra controls start neutral and can adapt through IK. Preserve the target's mesh, skeleton, bind transforms and weights; preserve unrelated actions and export reset channels in the new clip.

For planted walks, prefer schema version 2 with `gait_contact_model` and `source_sole_rest_centers`. It carries continuous stance speed, per-limb touchdown phases, stance fractions, swing clearance and reviewed center offsets. The transfer uses one common step scale and speed across all four limbs, then fits the target's weighted paw/heel surfaces. This avoids the four different stance speeds introduced by independent limb-length scaling. Per-actor `contact_adaptation` supplies body-height and tail-clearance corrections without baking one actor's rest pose into the category gait. Legacy normalized trajectories remain for inspection; version-2 transfer uses the continuous contact model. See [contact polish](contact-polish.md).

The same contact model can carry reviewed `elbow_pole_sign`, airborne orientation guides and a chest-relative `shoulder_direction_guide`. Fit their intent on the target's own chain; copying local hinge or shoulder angles is insufficient. A changed shoulder offset can require additional target-specific body lowering to keep the full stride reachable. Preserve shared speed and cadence rather than silently reducing one paw's reach. An ankle role may be a sibling helper rather than a serial joint, and an actor lacking that helper can still be compatible. Actor deformation adapters such as `scapula_offset_controls` remain in profiles. Validate the true upper/lower/foot hinge, parent distances, weighted mesh deformation, stance, swing pose and restoration after switching back to another clip separately.

For the one-shot pilots, schema version 3 stores semantic action controls, explicit event/support windows, nonlooping endpoint policy, normalized evaluated sole trajectories and per-actor adapters. The trajectories are fitted native skin motion, not measurements of hidden video joints. Adaptive `times_seconds` are authoritative; never infer uniform spacing from sample count or a nominal FPS. Source and transferred actors need independent native contact, intermediate-pose, floor and hold checks. See [one-shot actions](one-shot-actions.md).

Map anatomical ownership and hinge policy separately from a shared control name. The Dire Wolf's upper snout must stay with the head while its lower jaw opens about its native pivot; it cannot inherit the Moorland jaw-origin arc merely through a `jaw` role. Early collapse guides can express fractions of each actor's standing chest/hips/head height, followed by native limb folding and sole IK. Save geometry/rest repairs only with the actor. Portable profiles resolve `source_glb` relative to the declared profile directory and record the input hash separately from fitting/export provenance; moving the library must not silently change which input is used.

Review unreachable targets, stance direction, foot slide, penetration, limb crossover, support balance and deformation. A second actor with different proportions or hierarchy must demonstrate reuse. Hidden lateral movement remains at rest depth; multiple-view capture needs synchronized motion/cameras and a new solver/profile validation pilot.
