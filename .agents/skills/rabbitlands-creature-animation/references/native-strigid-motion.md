# Native hovering owl motion

Use this guidance for the current imported Amberwood Owl, Amberwood Great Owl and Leafwing Owl. Consult the private owl continuation record and review queue before selecting or promoting a draft. All three have technically qualified local drafts. Read the family continuation record for the selected files and combined review; technical qualification does not mark them approved.

## Choose motion from the sculpt

These owl sources have tucked talons and hovering silhouettes, with seven generic action names and no native Fly clip. The pilot uses hover, slow flight and fast flight in the locomotion slots, a beak-and-talon swoop and a supported forward fall. Its map records airborne locomotion. Do not label flight as a certified planted-foot gait or infer toe-contact requirements from Walk/Jog names. Different requested locomotion would need its own physical contact fit.

The three rigs differ in joint count, wing chains, foot symmetry and body-to-wing proportions. Leafwing's raised wings contribute substantially to its total height; that height alone is not a transferable head or shoulder frame. Inspect the physical body, head, talons and feather roots for each actor.

## Feather controls and skin

The original skin assigns some torso and lower feather surfaces to wing or leg controls. Broad wing motion on those weights stretched body triangles. Keep the core coat with the body, repair complete medial ankle/leg transitions smoothly and distinguish physical talons from tail feathers carrying foot weights.

Separate rigid feather islands can use appended native controls at their own proximal attachment points. Keep the original node/rest/bind prefix and source geometry, normals, UVs and images intact. Verify feather edge lengths and fixed anchor-to-body separation through the whole beat. A body stretch check alone cannot certify a detached plate's attachment. Choose each source's anchors from actual geometry; do not copy a count or world pivot from the pilot.

Position-welded components can connect long flight feathers to the torso at a single coincident point. Compare shared-edge face groups and inspect the actual plate roots before classifying a large connected component as body. The Great Owl transfer initially left much of one wing fixed because of this mistake. Merge feather sections that share moving junctions onto a common control; choosing independent pivots at those junctions can stretch the plates even when every bone keeps its length. Keep body-mounted back plates with their actual torso attachment rather than flapping them because the source assigns wing weight.

Check complete talon/ankle components when the source foot is a separate physical piece. A foot-only influence mask cut through the Great Owl's medial ankle and mixed adjacent rows with the torso. The corrected field retains the whole physical component and uses broad, continuous tail ownership across the lower back. Source influence names alone do not distinguish talons, tail feathers and coat.

Inspect descendants before applying head counter-rotation to a spine or neck control. The Great Owl's upper spine also owns a long back-feather chain. Rotating that control as a neck stretched the back and tail. The selected transfer keeps its close face/collar assembly coherent with the body; Leafwing uses head-only release and a separate leg fold for its collapse.

Leafwing's large connected wing sections use common anatomical wing roots rather than the pilot's many individually anchored plates. A rearward wing plane clears its face through the upstroke. Sweep direction is actor-specific: check the full head and talon surfaces across the stroke, attack and fall; solving head clearance alone can introduce foot intersections.

Per-plate rigidity does not certify a complete wing. The Great Owl's independent feather pivots kept each panel intact but separated the overlapping flight feathers during the stroke. Its corrected feather fans use a common shoulder hinge, derived from the connected right-wing junctions and mirrored in the torso frame for the left guide. Check the left guide against its physical shoulder cover rather than assuming mirroring alone is sufficient.

Keep fixed cross-panel seam pairs from the source and measure their separation between exported keys. Check actual shoulder junctions and a bounded root patch against the shoulder cover; a nearest-body measurement at each moving feather's original private pivot is not an attachment test once the whole wing shares a hinge. Recheck opposing-wing, head and talon intersections through the upstroke, downstroke, swoop and fall. Preserve the corrected head and unrelated body motion while repairing the wing fan.

When adding a skinned control, its inverse bind must include the source mesh rest frame: inverse(new joint rest world) multiplied by mesh rest world. The latter can be recovered from an original rest joint world multiplied by its inverse bind. Assuming an identity mesh frame can silently change the rest surface.

Use typed integer writers for JOINTS attributes. The shared packing append_array helper writes float accessors, even when given an integer NumPy array. glTF joint components must be UNSIGNED_BYTE or UNSIGNED_SHORT. The initial owl file passed a lenient engine import but failed the independent Blender import because of float joint indices; verify the accessor component types as well as logical index values. Preserve all required influence sets and bind the explicit skin preparation to its actual file hash.

Classify shoulder coverts separately from the long flight feathers. The larger pilot upstroke drove two collar panels into the head. Reducing those panels to gentle body-following motion preserved the primary wing stroke and its clearance; source wing influence alone did not distinguish the roles.

Native anchored controls kept the pilot export compact without a large corrective-shape basis. Use a representation appropriate to the physical surfaces; the corvid ground-motion corrective exporter is not automatically needed for a hovering owl.

## Review and qualification

Measure head direction from physical facial landmarks in the torso frame, including the eye line and beak. A straight bone axis can still carry sculpted yaw: the Great Owl needed about 13 degrees of head correction and a small eye-line roll correction. Apply the correction in the body's moving frame and keep close collar pieces coherent with the face; recheck all wing/head intersections afterward.

Review the stroke silhouette at native speed. The pilot's first hover stroke was too small despite passing geometric checks; the selected draft widens the upstroke. Check all phases for head/talon clearance after changing it. Keep the head directed forward, feet tucked during flight and talon reach clear of the torso in the swoop.

Evaluate breast/pelvis support separately from feather tips and talons during collapse. Select the terminal body pitch and wing/tail release on the actual mesh, then qualify the full fall, exported interpolation and held end. Released feet may rotate with the fallen body; flight talons should not remain artificially floor-facing.

Fresh game and Blender imports must match independent bone, surface and normal witnesses, including appended controls and the real influence count. Require nonempty physical fields and an explicit render completion receipt; Blender may exit successfully after a Python error. Review the exact final file from side, front, rear and opposing game angles. Preserve earlier deferred families in the review queue without treating numerical qualification as human approval.
