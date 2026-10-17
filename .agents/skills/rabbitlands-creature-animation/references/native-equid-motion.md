# Native horse-family motion

Use this reference for pony/horse gaits, native multi-joint leg fitting and tack preparation. The approved Moor Pony selection and portable checks are documented in `docs/equid-motion.md`; consult current private equid memory for selection and publication state. Other imported equids need their own anatomical fitting and visual review.

The pony's five-node serial limbs can be fitted as two IK sections while retaining intermediate hock/carpal nodes within their native segment groups. Check every serial length, the physical hoof plane and the whole hoof silhouette. Named ankle controls alone do not establish which vertices belong to a hoof.

The source pony's separate hoof components contained opposing-leg influences. A low-pad blend improved contact while leaving the upper hoof torn across independent legs. Weld coincident source positions for analysis, identify each complete physical hoof, then bind the whole component coherently to its native ankle. Preserve exported geometry and duplicate vertices. Keep the anatomical ownership actor-specific rather than applying these component IDs to another model.

Tack has separate physical attachments. The source saddle, girth and stirrups mixed foreleg/head/ear influences; a coherent saddle-control attachment removed their stretching. Bridle pieces belong with the head, while mane/neck straps need a smooth body-to-neck transition. Inspect the exact pieces at the same old/new poses and track original edges. The approved source geometry and all three inherited idle/hit sampler arrays remain exact; prepared skin is explicitly different.

A long hanging tail can reach the floor when the body lowers or rears. Fit a connected root-to-tip lift and coherent wave in the body's frame. A small tip-only correction does not account for torso rotation. Recheck the full surface floor, including tack and tail, alongside physical sole contact.

When creating a fresh-import surface witness, clear imported armature pose bases and update the dependency graph before matching rest-space mesh vertices. Disabled actions can leave an imported pose in place. Match and evaluate the actual deforming mesh, excluding helper shapes. Independent off-grid bone poses and repaired-surface samples certify different parts of the import.

For mount handoff, provide the approved installed file hash, actual registry scale/facing, clip durations and measured stride speeds. Node 24 (`Bone_021`) is the pony saddle frame; rider offsets still need mount-specific visual review. Keep a new gait draft separate from the approved walk/trot selection. Gallop requires its own four-foot timing and support/airborne audit; its eventual runtime action mapping is a separate integration decision.
