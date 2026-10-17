# Repairing transferred skin and complete tails

Use this when transferred motion exposes stretched forelegs, moving body ornaments or a tail leaning away from the body center. Keep the repair as a versioned actor input, separate from the unchanged category motion. The seven-actor example is `canine_motion_transfer_pilot/delivery-v2`; its manifest selects exact inputs and curves. Intermediate folders include rejected experiments.

## Identify the physical defect

Apparent tearing can be stretched triangles rather than a separated UV seam. Measure coincident-vertex gaps and triangle edge strain through the affected clips, then inspect the worst frames. Compare **fixed original anatomical vertex/edge IDs** before and after repainting: selecting by the new weights alone can exclude the bad region and falsely improve the score. An edge ratio alone does not establish visual acceptance.

Inspect geometry, connected shells, real joints and existing influence fields together. A spatial leg mask can grab hanging chest fringe; a generic distance-to-segment repaint can worsen articulated skin. Preserve good native donors and smooth the reviewed ownership transitions. Rigid ornaments need coherent attachment ownership instead of foreleg motion. Review duplicated seam vertices together. In this pilot, eight influences avoided discontinuities from truncating a smooth field to four slots. This is an actor-specific remedy. Verify actual engine surface weights per vertex after import, not merely successful playback.

## Center the actual appendage

Bone labels and current tail weights do not reliably delimit the tail. Moss Armored Hound has a long visible tail despite its tiny named weighted chain; Thornhide's named Tail chain is a hind leg. Review the whole tail core plus its attached disconnected shells. A convenient Y/Z bounding region can miss a hooked tip and include hind fur. Save explicit reviewed IDs and show rear and top views against the physical body midplane. X is lateral, Y is up and Z is forward in this tool convention.

Correct an approved horizontal rest lean along cross sections of the complete appendage, preserving its vertical/forward silhouette and attachment transition. Preserve bind/rest structure where feasible, transform normals consistently, and compare the unchanged body outside the tail. Geometric centering and an animated tail-wave adapter are separate operations. Existing bone pivots may remain off center after a mesh correction; evaluate the actual skinned surface in every clip rather than claiming the chain itself was centered.

Audit complete-tail skin ownership too. Distal tail vertices with hindleg influences continued pulling the corrected tip sideways in this family. Remove foreign leg ownership only in the reviewed distal tail and blend into its native base attachment. Drive adjacent sections with a coherent distributed bend, avoiding independent tip compensation. An actor-specific constant base clearance bias can preserve the wave without lifting the torso or moving planted paws. Native range and side-collapse adapters belong to the actor profile.

## Keep contact regions physical

Freeze reviewed physical sole IDs, not an erroneous automatic selection. Four Crystal tail vertices had been incorrectly included in a hind sole. Remove such contamination, remeasure actual bottom-pad centroids and rebase stance/support anchors. Airborne paths need the target paw's rotating offset too. Bind reviewed IDs to the prepared input hash and evaluate their current geometry and weights, including additional influence sets.

`native_paw_surface_vertex_ids` and `native_paw_bottom_vertex_ids` override automatic patches in `contact.py`. Bottom IDs must be a valid subset of their own paw. Validate each cached subset against full evaluated skin after repairs. A sole-only fit can bury mixed foreleg or neck fringe; project full-skin clearance and supported soles together.

For a settled tail, a low proximal bridge can falsely certify contact while the actual tip floats. `native_body_support_vertex_ids` overrides reviewed body regions in `actions.py` (support patch schema 3). Use the true distal region and inspect it. Do not force every short anatomical tail onto the ground, but do not infer short geometry from a small named chain.

## Refit changing support without a hold jump

Recheck affected clips against the same prepared actor. Preserve original stride and event timing where possible; skin repair does not authorize changing category motion. Surface changes can require native body/limb corrections and a restrained coherent tail bend for clearance.

During a roll the body contact patch can move. A no-slide stable body window normally starts at the settled event, not first impact. Approach all newly active body support constraints before the hold boundary while locking supported paws. Copy the actual preceding dense constrained pose into the hold. Blindly freezing an earlier pose can preserve a floating head, hips or tail; adding the prior correction twice can instead create a boundary jump. Check exact keys and half-keys around every support transition.

Keep semantic intent knots, native constrained samples, export keys and video cadence distinct. Export authoritative dense constrained poses on their stored timestamps. Resampling onto a nearly equal uniform grid can alter surface contact. Portable rebakes must reproduce the actual final skin, including hold boundaries. Bind checkpoints to prepared input, profile, parameters and solver version; close NumPy archive handles before replacing checkpoint files on Windows.

## Final evidence

Freeze combined GLBs before rendering. Bind contact/preservation, fresh Blender reimports, engine playback, actual influence counts and movie cadence to those exact hashes. Show front views for forelegs and rear/top views for horizontal tail alignment with the reference at its original speed. Dense fidelity curves are not runtime optimized; recheck after reduction or importer changes. Keep numerical success, visual inspection and user acceptance separate.
