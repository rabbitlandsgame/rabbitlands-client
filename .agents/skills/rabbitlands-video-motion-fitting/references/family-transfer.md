# Transferring the canine motion to a model family

Use this for a batch of existing wolf, hound or fox models. The working example is `.local/asset-authoring/workspace/generate_models/canine_motion_transfer_pilot`; read its final selection manifest before choosing outputs. Intermediate fitting folders contain rejected candidates.

## Map anatomy before copying intent

Audit the physical source chain as well as the target. The original wolf's legacy rear labels do not align with the target hip/stifle/hock/paw roles. For a contact-valid action whose legs still move incorrectly, follow [the anatomical motion audit](anatomical-motion-audit.md); smoother copied angles do not establish the correct anatomical fold.

Inspect the actual weighted skin, joint positions and parent chains. A named `Upper` can be an elbow or stifle. Mossbound Hound's foreleg is scapula → humerus → named upper → named lower → ankle → foot: these correspond to attachment → shoulder → elbow → wrist → paw → toe. Treating the humerus as a compensated decoration freezes the real upper arm. Preserve unweighted extra armatures and ambiguous generic names; use unique names or node IDs for mapped roles.

Use a consistent physical map: upper at shoulder/hip, lower at elbow/stifle, ankle at wrist/hock, foot at the paw root. Uncontrolled toes follow the paw. A torso helper may remain neutral while the physical limb root moves. Alias `anchor` to `upper` when no independent attachment control is required; omit the duplicate control.

Foreleg bend ends at a **serial wrist**, while a sibling heel helper is excluded from that chain. `elbow_endpoint()` handles this distinction. Rotating the wrist must not change the measured elbow bend. Check both pose direction and the lifted paw, not only its endpoint.

Keep limb initialization neutral on unfamiliar rigs. Transfer paw paths, support timing and body intent; solve the actual target joints rather than preserving source corrections on the wrong segment.

## Scale consistently and account for the paw

Measure source and target spans between equivalent anatomical joints. The original wolf package's legacy hind labels do not identify the same segments as every target's bone names. Store the anatomical source measurements and the actor's scale basis separately from the unchanged accepted source package. Use one common median scale and walking speed for all four paws.

Measure to the paw pivot, not the end of a long claw. Align the stance center through the source's limb-root-to-paw-pivot offset, then add the target's own sole-centroid offset. `retarget_paw_forward()` similarly transfers airborne pivot travel before restoring each model's rotated paw offset. It preserves an identity transfer and the exact support anchors. Copying a sole-to-shoulder offset can make the rear half of a long-clawed actor's stride unreachable.

Paw turning can need an actor amplitude adapter. The long Crystal Dire Wolf claws need a gentler turn than the Moorland paw. Preserve stride and timing while adapting that orientation. Before repainting a suspicious muzzle deformation, isolate the moving component: a raised long claw can overlap the face in side view.

## Keep preparation separate

Save rig and skin repairs as versioned inputs with changed-node/vertex lists and a neutral-shape comparison. The demonstrated cases include Briarhide's missing foreleg joints; Thornhide's mislabelled tail/right-leg chains, toe parent and torso-weighted sole vertices; jaw controls; and Crystal's head/neck ownership. Model positions, textures and materials remain unchanged in these preparations, except for an explicitly requested rest-shape correction such as tail centering. Rebase existing clips and add reset channels when adding/reparenting joints.

Audit the body driver as carefully as the limbs. Crystal and Moss Armored Hound's native `root` lies near a front paw, so copying body pitch rotates the hips around an unsuitable point. An unweighted parent driver at the physical hips can give new actions a useful pivot. Split inherited root translation between the new parent and fixed child offset on the original channel timestamps; keep all other channels intact. Compare the complete evaluated skin at neutral and throughout every inherited clip. Do not resample unrelated curves merely to add the parent, or merge almost-equal double-precision times that become duplicate float32 GLB timestamps.

Transfer evaluated physical hip height with equivalent anatomical scale and the native paw-pivot-to-floor offset; another rig's root-local height has no portable physical meaning. Keep a previously qualified walk by rebasing its original pitch control and carrying height through the new parent (`body_height_node`) when appropriate. Check fixed parent distances and equality of the full animated skin after that rebase. A new pivot does not by itself justify changing a qualified gait.

A qualified one-shot can be preserved too: retain its original pitch mapping and carry translation plus whole-body roll through the new unweighted parent (`body_height_node` and `body_roll_node`). Roll still pivots about the posed hips. Compare the old and rebased full skin, fast FK versus reconstructed local transforms, and every connector length. A new hierarchy does not require refitting an already sound collapse. Per-motion native profiles may differ while using the same prepared actor; the unchanged semantic source package remains the category contract.

Check low paw/heel vertices for inappropriate head or torso influence. Briarhide had Nose influence on a forepaw heel; fitting that moving mixed surface produced sudden wrist solutions. Verify the bone's actual position before calling this a weighting error—a misleading name can instead describe a genuine leg bone. Repair the reviewed pad/carpal volumes in a new input and test that a head-only turn no longer moves them. Preserve both the previous review artifact and the repair's exact vertex scope. Refit all affected clips against the same prepared input.

Judge jaw ownership and pivot independently. A closed-mouth model supports a smaller opening than a sculpted open mandible; a bone alone does not create a mouth cavity. Record the actor's jaw range and review the actual upper snout, not only the head transform.

## Contacts and endpoints

Rigid armor carried by neutral torso helpers belongs to body support geometry. Do not demand chest contact through a rigid shoulder plate that physically props up the torso. A very short tail may settle above the floor; adapt its contact window instead of forcing it to the long-tailed source's ground contact. Keep whole-surface nonpenetration and the terminal hold. A short neck or tail can need an explicit existing-bone yaw control for the authored sideways collapse; keep those lateral choices neutral during the supported stance and bite.

IK can drift along a family of poses with identical paw coordinates. A walk needs a periodic posture as well as periodic sole paths; a zero endpoint surface gap alone misses a fast final-key correction. For attack recovery, approach the initial native posture while retaining the fixed paws. For death, cache the **final constrained pose** at support release and transition to the fitted native terminal pose. Returning to the raw source seed at release creates a jump.

Keep reviewed early-collapse height fractions and elbow-fold targets as explicit intent constraints. Contact locking by itself can certify a target that remains too upright during the head drop. Match native chest/hips/head lowering before solving supported paws, then check the visible fold independently of terminal contact. Carry the preceding native body correction forward with the authored intent delta; resetting to an unreachable raw body seed each frame discards useful coupled IK progress.

Video cadence, fitted intent knots and exported key density are different. More interpolated keys do not repair nonlinear skin/contact error. Solve evaluated soles between the coarse knots, then validate the exported quaternion/translation interpolation at keys and half-keys. Merge numerically identical event/grid times within a tiny floating-point tolerance; preserve meaningful adaptive timing.

Inspect isolated key/contact spikes as well as broad sliding. Nonsmooth lowest-vertex changes and IK nullspace choices can leave one bad pose between otherwise correct samples. Use the preceding fitted native pose as a solve seed and review posture continuity; a blind angular-speed cap can prevent a paw from reaching its declared landing. An airborne minimum-height guide still needs a soft height preference and a continuous touchdown, or its unused vertical freedom can leave the paw floating until contact. After a pair releases during collapse, repair that pair's own full skin clearance while the other paws remain planted. A forward muzzle contact patch is not the complete head-clearance region: check the jaw and remaining head-owned vertices too.

For recovery, distinguish a stable starting stance from exact equality of every internal joint angle in a nonlooping clip. Free IK joints can reach identical planted feet through different postures; an unconditional last-key reset can create a visible snap. Retain the actual constrained recovered pose or continuously guide the complete native posture into the intended hold. During collapse, avoid replacing a reviewed roll/overshoot waveform with a generic monotonic release-to-end interpolation; preserve event-relative body intent and blend native release/ground corrections around it.

The recovered hold must use the last **dense constrained pose**, not the earlier coarse fit at that timestamp. The two can have different internal joint solutions despite identical paw endpoints; switching between them caused a subframe paw dip. Validate the final exported hold boundary at half-keys. For mixed neck/chest vertices, majority ownership alone can miss clearance after head adjustment: check the complete skin after all contact projections. Repair the relevant head/neck pose while preserving supported paws. Review any generic angular cap that blocks the small required correction; document an actor-specific range adapter rather than increasing key density or repainting valid skin to hide it.

Check full skin clearance, real hinge branches, source cadence, shared stance speed, loop transition, supported/airborne boundaries, bite direction, coherent tail sections and held death separately. Reimport final combined GLBs in Blender and test Godot playback, stopping and return to Idle with optimizer/compression disabled. Record visual approval separately from these technical checks.

Verify the actual comparison movies' frame counts, rates and durations, not just the declared JSON FPS. A passthrough trim can omit the last selected frame's full display duration. Keep every selected reference frame once on the original cadence, and exclude a duplicate render endpoint from a looping walk movie. In this pilot the full walk loop has 34 complete frames at 24 fps; one-shot movies retain their final endpoint display frame. Bind media validation to the delivered movie hashes.

For full-tail ownership, fixed anatomical deformation comparisons, explicit sole/distal-support IDs and contact-aware settling after skin repairs, read [skin and tail repair](skin-and-tail-repair.md). A small named tail chain is not evidence of a short visible tail.

Contact success is not a continuity gate. Check exported physical trajectories and fit native muzzle reach/aim rather than assuming copied neck angles extend every snout. Shared skin can couple otherwise separate legs; project all active soles together. See [temporal quality and native muzzle reach](temporal-quality.md).
