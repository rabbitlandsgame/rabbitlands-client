# Audit the motion of the whole limb

Read this when a transferred action passes support and smoothness checks but its legs still move incorrectly. The canine revision-4 stage illustrates the workflow. Keep its manifest and user-review state separate from technical diagnostics.

## Establish the physical reference

Use the exact established animated wolf GLB and its reviewed rig profile. Evaluate that model from side, front, rear, top and opposing game cameras at the original timestamps. Additional views reveal the existing authored 3D fit; they are not additional captured views or measured hidden joints from the original single side video. Keep the Meshy video available as the original visible-motion reference.

Overlay individually colored physical chains on the evaluated skin. Follow each leg through the head drop, release, roll, body contact and held pose. Compare the motion throughout these phases; a smooth endpoint approach or a correct paw endpoint can still conceal an incorrect elbow, knee, hock or airborne paw.

Audit the established 3D source itself. This pilot exposed an abrupt fitted leg snap around 2.76 seconds which was difficult to see in the earlier presentation. Its raw unit-vector trajectory was useful pose evidence but unsuitable temporal ground truth. Preserve that source and disclose the authored cleanup. Fit a continuous native trajectory with physical supports, fixed starting/held poses and unchanged event times; compare actual skinned acceleration and jerk in the failing interval as well as the whole clip. Smoothing control values alone still needs the coupled physical solve. Never copy a hidden IK artifact solely because it belongs to an established model.

## Remap the source anatomy too

Review both ends of a transfer against hierarchy, rest positions and actual skin ownership. The original wolf's rear semantic labels start one articulation later than the target maps: its physical hip/stifle/hock/paw chain is `anchor/upper/lower/ankle`, with the named foot farther down as a toe. Copying its named upper/lower control angles into a target's physical hip/stifle chain gives the wrong folding even when subsequent paw IK passes.

The source foreleg's named ankle is a sibling heel helper, while some targets have a serial wrist. Exclude the sibling from the anatomical segment chain. An extra target wrist needs a native subdivision and paw-orientation adapter. Do not treat every fourth named node as an equivalent articulation.

`video_motion.anatomical.validate_limb_chains` rejects duplicate nodes, inactive joints and sibling helpers presented as serial joints. It does not infer the anatomy. `limb_segment_directions` evaluates native unit segment vectors in rest-cancelled chest/hip frames. Explicitly store the reviewed source chains, frames and target subdivisions.

## Fit pose intent before polishing support

Use native segment directions, bend planes and actual paw orientation as intent, together with support timing, surfaces and temporal regularity. Preserve native bone lengths. Initialize a continuous anatomical branch; restarting from an incorrect late-contact solution can reproduce the same local minimum. Temporal smoothing makes an incorrect pose smoother without correcting its anatomical correspondence.

Check geometric joint-bend magnitudes as well as segment-vector residuals. An almost antiparallel limb can trap a vector-only solve in an excessively tight fold. Mossbound's resting rear knee remained about170 degrees while the established source was about81 degrees. A soft geometric-bend guide and a native limb-only endpoint solve brought it to about105 degrees with contacts intact. A quintic correction confined to that limb preserved the body and other native controls. Use native proportions and clearance to judge the remaining difference; avoid inventing new joints merely to compensate for an optimization minimum.

Adapt the torso to the target's proportions and physical supports. Forcing identical source torso rotations on unlike rigs can push neck, armor or muzzle controls to their bounds. Conversely, freezing every target torso control can prevent a useful anatomical fit. Compare the complete native deformation and source-relative limb paths, and choose the coupled result with actual clearance and credible posture. Do not select a candidate from its version number, contact pass or lowest angular-error statistic alone.

Fit a feasible native fallen pose jointly with all required body supports and limb clearance. Keep its source-directed limb intent. Approach this pose with a bounded, nonperiodic transition and retain the established settled time. A quintic **convex pose blend** stays within the native bounds when both input poses do; adding an endpoint correction to a changing curve can exceed those bounds between endpoints. Recheck the actual limb path and supports after blending. This is an endpoint initialization, not permission to replace intervening motion with a static pose.

Project active paws together where skin shares influences, then inspect temporal quality again. During unsupported fall, solve native body and limb clearance together. No post-export whole-actor lift or contact-tolerance relaxation should conceal a failed pose.

Keep anatomical bend-side checks covariant with the rotating native limb frame. An `atan2` hinge angle changes representation at plus/minus pi; a direct signed-angle inequality can ask an almost folded hock to unwind through straight. The tested `video_motion.anatomical.hinge_branch_residual` uses `sign * sin(angle)` with a small margin, choosing the nearby physical branch across that boundary. Review the native anatomy and retain its full bounds; the pilot's three-degree guard and slightly larger terminal margin are fitting choices, not universal canine joint limits.

Recheck fixed original foreleg edge IDs after changing the motion. A new pose can expose chest, neck or shoulder stretch despite identical repaired weights. Prefer a native pose/torso adapter or a deformation-aware coupled correction when possible. Review its effect on the intended limb fold, supports and the approach to the hold; an isolated final-key correction can restore jerk. Do not change an influence mask merely to improve the strain statistic.

## Deliver reviewable evidence

Include the established model and transferred actor from the same selected camera direction at the same speed and timestamp, plus the original Meshy reference and a previous-version option. Disclose independent full-body framing. Colored-chain diagrams aid diagnosis; fresh textured reimports are the deformation review.

Bind chain-direction comparisons, motion continuity, contacts, holds, preservation and playback to exact combined-file hashes. Record source-relative direction errors and their changes across phases as diagnostics, not universal artistic thresholds. Check original frames and exported half-keys, and inspect all four legs from multiple views. Preserve every unrelated clip, prior delivery and prepared skin/rest repair.

The reusable `death.anatomical-intent.json` supplement describes physical segment directions from the established fitted model at the original cadence. Keep it separate from legacy angular control names and unchanged source packages. A new actor still needs reviewed anatomical mapping, native surfaces, proportion adaptation and fitting.

For a new canine death transfer, use the physical guide in `family-pilot-v4` alongside the original support/timing package. Treat the legacy angular mapper as initialization, then qualify the actual target anatomy. The guide includes explicit physical joint positions, rest spans, sole centers and geometric bend magnitudes, plus the known-source-artifact policy.

Write review HTML, JavaScript and handoff text explicitly as UTF-8 on Windows. Validate comparison links and inline JavaScript as well as the videos; the system text encoding can otherwise corrupt new labels or prevent exact text replacements.

## Apply the audit to a lunge and bite

Review anticipation, the last supported launch pose, airborne extension, the bite, each landing and recovered hold. The revision-5 canine audit found that several angular transfers lowered the pelvis and chest during the bite while the established wolf rose. A believable muzzle angle alone concealed the wrong body trajectory. Compare native-stance-relative hip/chest displacement as well as body-frame limb directions, actual upper-muzzle reach and the native lower-jaw arc. Preserve native lengths and anatomical proportions rather than matching absolute source joint coordinates.

Use the same reviewed physical source chains as the death audit; their anatomical correspondence does not change with the action. Adapt serial wrists independently from source sibling heel helpers. Keep already good muzzle extension from retracting when correcting the torso or matching a source cheek angle. Jaw and tail controls can remain exact while torso and limb trajectories are revised.

Audit the source attack's temporal path independently. The established wolf attack has a sharp fitted transition around3.17 seconds; it is pose evidence, not an instruction to reproduce that acceleration. Preserve original launch/bite/landing/recovery event times and the recovered stance. A per-frame physical-pose seed can jump when a landing support window becomes active. Follow pose fitting with nonperiodic temporal fitting coupled to all active soles and whole-skin clearance, then inspect the exported skin and limb paths again. Do not promote a raw anatomical candidate on the strength of its bite pose or contact report.

When native pose fitting needs initialization, a source-directed per-pose solve can escape a poor angular seed. Remove exactly protected controls from the optimization variables instead of expecting extremely narrow bounds to be an efficient numerical lock. Retain native bounds and physical branch checks. Compare candidate posture and deformation; these numerical choices do not establish visual acceptance.

Rebase actor-specific muzzle trajectories after the torso adaptation. An old world-space nose guide can pull the newly raised body back down in a later temporal fit. Keep the seed guide as provenance and evaluate the qualified muzzle features from the actual final native export. The shared source muzzle supplement remains unchanged.

Apply only the contact correction the actor needs. Full projection can introduce a shared-skin landing jump or lower a remote tail surface that was absent from an initial near-floor subset. Recheck the entire exported skin, all active paws and temporal quality. In revision5, Mossbound needed a bounded fraction of the full coupled correction: the uncorrected smooth curve failed the denser slide check, while full correction created a worse landing jerk. The selected fraction passed the original contact limits with lower acceleration. Fox's unprojected coupled temporal result passed dense contact checks; a later full projection was rejected for floor penetration. These are measured native choices, not universal correction factors or permission to relax tolerances. Freeze the selected source of each actor explicitly.

Close checkpoint readers promptly on Windows. An open NumPy archive can prevent an atomic checkpoint replacement and interrupt a concurrent fit. Inspect completed reports or use a short-lived context-managed read, with a writer retry for transient locks where needed. Resume only a checkpoint whose source, prepared rig, parameters, solver and settings bindings match; do not recover by resubmitting paid generation.
