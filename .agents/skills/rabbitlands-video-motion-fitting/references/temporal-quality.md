# Temporal quality and native muzzle reach

Use this when a contact-valid one-shot still looks jerky, or a transferred bite folds the head without reaching forward. Continue from the selected actor input; keep its skin/rest corrections and unrelated clips. The seven-actor revision is `canine_motion_transfer_pilot/delivery-v3`.

## Validate motion as well as support

A planted-paw and grounded-body pass can coexist with abrupt head, limb or torso changes. Endpoint equality does not establish a smooth approach to that endpoint. Inspect actual exported joint and skinned-surface trajectories at the original timestamps. Record speed, acceleration and jerk through release, roll, impact and recovery, and include a normal-speed comparison. Angular-control smoothness alone cannot certify the composed skin motion.

`video_motion.temporal.motion_quality` reports physical surface diagnostics. Compare like vertices, units and cadence against the prior version. This revision used 24/48/96 Hz diagnostics separately from 1536/3072 Hz contact/export checks. Choose future rates and quality limits from the motion and failure intervals; those numbers are not category requirements. Legitimate impact acceleration differs from an isolated pose jump. User visual acceptance remains separate.

## Fit a trajectory with contacts

Filtering native angles alone moved paws and buried body skin in this pilot. Fit temporal regularity together with actual support positions, paw orientation and whole-skin clearance. A useful initialization minimizes third differences with nonperiodic boundaries. Keep the actual neutral and settled/recovered native poses fixed and approach them continuously; preserve source event times and the terminal hold.

The revision's `fit_temporal.py` optimizes the complete native trajectory with sparse per-pose physical Jacobians and a shared temporal term. Native segment lengths and bounds stay in force. Body height can participate in the coupled pose solve; an after-the-fact whole-actor lift would move planted paws. Validate the actual exported interpolation, not just fitted knots. More export keys do not repair a discontinuous underlying fit.

Treat rotation representation separately from anatomical motion. Equivalent foot revolutions can need unwrapping, but unrestricted unwrapping of Briarhide's hind upper control introduced a full leg turn during recovery. Preserve the native hinge branch and endpoint posture. Do not widen a range merely to accommodate that representation. Check the intervening physical limb path even when the two endpoints are equivalent rotations.

## Aim the physical muzzle

Copying neck/head angles between different rest chains can point a snout into the chest or leave an upright neck unextended. Fit native-length reach and physical upper-muzzle direction instead. Review explicit nose and rear-muzzle/cheek vertices, including mixed neck/head ownership, and exclude inappropriate lower-jaw or ornament geometry. A strict Head-only ownership threshold missed the source's actual nose; a head-pivot-to-nose vector also gave the wrong aiming axis. An aiming patch and a ground-support patch serve different purposes.

Use calibrated source surface features as intent and adapt them to target anatomy. `family-pilot-v3/category-motion/attack.muzzle-intent.json` records height-normalized source reach and pitch at original video timestamps. These features come from the fitted source model, not measured hidden 3D video joints. The semantic source motion payload remains unchanged.

Preserve native bone lengths and the intended jaw hinge. Maximize feasible reach while following the source aim, with a floor on already good forward reach. A strict shared cheek-bridge angle shortened the already extended Fox and Thornbark poses; relax that geometric angle rather than retracting a healthy bite. Keep the gesture confined to launch/bite/recovery and check the actual upper snout and lower jaw separately.

## Project shared skin together

Separate skeleton chains do not imply independent skin. Small per-leg contact corrections broke another planted paw where vertices carried cross-limb influences. Solve all active physical soles together using the current skin, including every influence set. In this revision, the final coupled correction kept body, jaw and tail parameters exactly fixed while solving the remaining shared-skin slide. Verify the combined result at keys and half-keys; a successful per-leg solve is insufficient.

Use a continuous correction through unsupported intervals and preserve the endpoint hold. Inspect both contact velocity and posture after projection so contact repair does not restore the original jerk. Bind every result to the final model, prepared input, profile and parameter hashes.

## Batched implementation and delivery

`action_worlds` and `SkinFeatures` accelerate world-space constraints and exact weighted centroids. Their outputs are world transforms/features, not local animation channels. Use scalar `ActionRig.pose` for local T/Q export. Test batch/scalar agreement with jaw arcs, body roll, shoulder compensation, helper paws and eight-weight skins. Bounds still need validation before export; derivative probes can lie just outside a bound.

Reimport the final combined GLBs and verify engine playback, stopping and Idle restoration. Preserve meshes, binds, weights and unrelated clip dictionaries when only motion changes. Portable rebakes should reproduce actual final skin on keys and half-keys. Keep the original reference speed and a previous-version comparison available; disclose that each full-body video is framed independently when making pixel-based comparisons.
