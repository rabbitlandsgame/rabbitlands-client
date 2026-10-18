# Native horse-family motion

Use this reference for pony/horse gaits, native multi-joint leg fitting and tack preparation. The approved Moor Pony selection and portable checks are documented in `docs/equid-motion.md`; consult current private equid memory for selection and publication state. Other imported equids need their own anatomical fitting and visual review.

The pony's five-node serial limbs can be fitted as two IK sections while retaining intermediate hock/carpal nodes within their native segment groups. Check every serial length, the physical hoof plane and the whole hoof silhouette. Named ankle controls alone do not establish which vertices belong to a hoof.

The source pony's separate hoof components contained opposing-leg influences. A low-pad blend improved contact while leaving the upper hoof torn across independent legs. Weld coincident source positions for analysis, identify each complete physical hoof, then bind the whole component coherently to its native ankle. Preserve exported geometry and duplicate vertices. Keep the anatomical ownership actor-specific rather than applying these component IDs to another model.

Tack has separate physical attachments. The source saddle, girth and stirrups mixed foreleg/head/ear influences; a coherent saddle-control attachment removed their stretching. Bridle pieces belong with the head, while mane/neck straps need a smooth body-to-neck transition. Inspect the exact pieces at the same old/new poses and track original edges. The approved source geometry and all three inherited idle/hit sampler arrays remain exact; prepared skin is explicitly different.

A long hanging tail can reach the floor when the body lowers or rears. Fit a connected root-to-tip lift and coherent wave in the body's frame. A small tip-only correction does not account for torso rotation. Recheck the full surface floor, including tack and tail, alongside physical sole contact.

When creating a fresh-import surface witness, clear imported armature pose bases and update the dependency graph before matching rest-space mesh vertices. Disabled actions can leave an imported pose in place. Match and evaluate the actual deforming mesh, excluding helper shapes. Independent off-grid bone poses and repaired-surface samples certify different parts of the import.

For mount handoff, provide the approved installed file hash, actual registry scale/facing, clip durations and measured stride speeds. Node 24 (`Bone_021`) is the pony saddle frame; rider offsets still need mount-specific visual review. Keep a new gait draft separate from the approved walk/trot selection. Gallop requires its own four-foot timing and support/airborne audit; its eventual runtime action mapping is a separate integration decision.


## Family transfers and physical leg volume

The six reviewed horse-family transfers add an independent Gallop action while retaining the normal run mapping to Jog. Use the current actor registry scale and facing; preserve the separately maintained mounted Moor Pony. Consult `docs/equid-motion.md` and the ignored current selection rather than copying a pilot baseline over newer runtime work.

A valid hoof trajectory and unchanged bone lengths do not certify muscle shape. Compare the actual same-vertex upper-leg, shin and thigh dimensions at gathered, landing and push-off phases, in side/front/rear and quarter views. Foal, donkey and zebra belly tissue initially followed leg controls and made the upper legs appear to change size. Correct body ownership and the physical shoulder attachment separately. Bound repairs along the body axis so a low muzzle is not included. Preserve complete physical hoof skin and coincident rows. A mane-root repair can also require correcting the underlying body surface.

Compare native skeletons as well as weights. The Dun Foal's left ankle pivot was too high, and its shin ownership formed a long boot. Rebase the changed joint, child fields and inverse binds together; preserve inherited world surfaces. Refit every affected gait. Correcting Gallop alone left the same visible defect in Walk/Jog. Fit bend planes in the anatomical body frame and retain native segment lengths rather than assuming matching joint names imply matching proportions.

Linear blends can shrink muscles despite acceptable contact. Intermediate rigid controls or localized pose-space corrections can preserve volume, but require explicit action scope. Freeze physical low-hoof/sole paths and body anchors, preserve accepted original curves, and neutralize new controls in unrelated actions. The Dun's Gallop needed a separate shin-to-pastern transition correction: core dimensions and contact passed before a gathered-phase crease was noticed. Inspect tight-fold closeups and actual imported surfaces before selection.

Evaluate all skin influence sets and corrective targets. Blender actions can contain OBJECT and KEY slots; select both, clear pose bases/shape actions/NLA before matching rest witnesses, and use the actual deforming mesh. Positive affine shape coefficients avoid preview slider clipping of signed controls. Quantize combined sampler input times to float32 before deduplicating them. Bind native, fresh Blender and client witnesses to the final combined file, including shapes and repaired surfaces.

Before publication, remove unreachable samplers/storage and only exactly redundant constant plateaus, grouping flattened morph outputs by their input timestamps. Preserve both plateau boundaries, clip endpoints, all retained values and embedded static arrays. Do not equate smaller files with cheaper animation: many corrective shapes and dense tracks still need separate gameplay performance evaluation. Keep full-resolution stages and review media ignored; publish only the runtime candidate and portable checks.
