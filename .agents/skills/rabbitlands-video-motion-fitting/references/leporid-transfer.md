# Rabbit-family authored motion

Use this continuation for the active imported Rabbit and Jackalope. Both have a serial three-joint chain per limb and a common named 25-joint hierarchy, but different fore/hind proportions and surface ownership. Native forward is glTF +Z. Do not extend the category to kangaroos or retired procedural models from a name or four-limb count.

The private stage is `.local/asset-authoring/working/leporid-motion-pilot-20261016`; continuation state is `working/memory/leporid-motion-20261016.json`. Read its current selection and exact reports before rebuilding. The user chose locally authored hopping and skin repair after four local Wan/VACE reference attempts failed motion/framing/anatomy review, then requested attack and death. These clips are authored choreography, not video-fitted motion. Frozen failed takes remain separate from the native motion and acceptance records.

## Native skin and shape support

Jackalope retains 25 corrective morph targets. The canine `Asset` reader deliberately rejects morph geometry; use the pilot's explicit morph/scale-aware reader for these inputs. Evaluate morph deltas before skinning, retain all static targets and inherited channels, and give revised clips explicit neutral shape tracks. Test a deliberately nonzero prior shape followed by playback and RESET; a list of shape names alone does not prove restoration.

Treat skin fixes as separate versioned prepared inputs. Rabbit's upper ears and forward muzzle contained neck, torso or foreleg influences beside rigid head ownership. Its repaired anatomical head uses feathered ear-root/throat transitions. Jackalope's forelimbs mixed head and opposing-leg influences; its repair removes those influences only within the reviewed native forelimb regions. Preserve geometry, rest/bind transforms, textures, morph arrays and unaffected weight rows exactly. Record changed vertex IDs and input/output hashes. The current inputs have four influences; do not silently expand or truncate another actor's format.

Check repaired boundaries in the same final poses with original and corrected skin. Comparing two different clips can hide a repair-induced crease. Jackalope's direct influence removal improved one foreleg edge but created a sharper neighboring transition; localized relaxation across welded mesh neighbors reduced that strain while pinning low paw weights. A broader Rabbit torso rebinding worsened the surface and was rejected. Keep such actor-specific masks and relaxation parameters in the prepared-input receipt, not as category-wide defaults.

An intentional shared-skin repair changes surfaces in inherited actions even when their joint/morph curves remain exact. Describe that distinction explicitly. Preserve the current Idle_A, Fighting_Idle and Hit_Chest curves and joint worlds; do not claim identical old/new skin after a weight correction.

## Paired hopping and reach

Carry one category cadence, common stance travel speed, paired fore/hind support windows and normalized body arc, then solve the native physical chains and evaluated soles. Recover the signed hinge from the actual rest chain. Do not copy local angles or scale bone lengths. Short hind chains need an early airborne tuck while the hip is rising. A smooth-looking loop and valid planted feet can coexist with an unreachable free-paw goal; report reach residuals during flight too.

Match swing endpoint velocity to the preceding/following negative stance speed. Smooth position endpoints with zero swing velocity create a velocity discontinuity at touchdown. Keep periodic body derivatives at the loop seam, preserve exact float32 events with consistent tolerance, and check exported half-keys. The pilot's dense export and import rates are measured fidelity choices, not defaults for all creatures.

## Attack and collapse

Rabbit uses a forward hop-lunge and Jackalope a lowered-antler jab. Preserve native head ownership and measure the physical snout's forward reach after torso adaptation. These inputs have no independently articulated jaw; do not describe a mouth-opening bite unless a separate jaw control/skin revision is actually added and verified.

For collapse, fold the forelegs while they still support the descending head/chest, release the two support pairs explicitly, and carry native body-floor corrections through release. Settle and hold the one-shot endpoint exactly. Refit the head's native yaw and roll against the actual muzzle and body-side support surfaces. A forward-extreme head patch can include ears or antlers and falsely certify muzzle contact. Bound the patch anatomically around the native head pivot and inspect its actual vertices. Likewise, a high torso-bone ownership threshold excludes a rabbit's weight-bearing haunch fur; use a reviewed physical body-side patch rather than a bone-name test alone.

Wide released paws can touch down before the body side and keep the torso floating. Jackalope needs a native inward fold of the released limbs before terminal body/head contact. Keep that adapter with the actor, preserve side identity and hinge branch, and verify the full skin; do not solve it with a post-export whole-actor lift or a looser contact limit.

Fit terminal muzzle and body-side support together. A head-only floor fit can leave the muzzle propping up a floating torso. Free-paw floor projection also changes the body's deformed surface as the root moves, so a lift estimated before that projection can overshoot. Refine against the actual projected surface, retain a smooth conservative envelope, and recheck between-key clearance and the exact terminal hold. Do not raise a contact tolerance to accept a floating body.

## Qualification and delivery

Bind evidence to the exact combined export: eight authored motions, three preserved native actions per actor, skin preparation, full-surface clearance, stance sliding, native lengths, free-paw reach, loop seams, one-shot holds and physical head/body support. Fresh Blender and the real client scene-cache/native-importer/action-resolver probe must use independent off-grid worlds and actual corrective weights. Review side, front, rear and both game-quarter views at original speed. Separate technical qualification, user artistic acceptance and runtime installation; current pilot work does not itself authorize replacement or publication.

The user selected delivery-v2 for client integration and develop publication on 2026-10-17. Installed motion, metadata and focused verification are documented in [rabbit-family integration](../../../../docs/leporid-motion.md). Public contact QA uses `eloria-assets/tools/test_leporid_motion.py`; engine playback uses `godot-client/tests/test_leporid_motion.gd`. The exact selected curves/static payload remain bound by published hashes. Private sources and videos remain ignored.
