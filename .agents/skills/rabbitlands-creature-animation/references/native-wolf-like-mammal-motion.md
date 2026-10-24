# Native wolf-like mammal motion

Use for actor-specific wolf, warg and hyena motion. These can share grounded quadruped intent without sharing a rig or a taxonomic family. Consult the current private continuation for selected candidates; draft qualification, human acceptance and runtime promotion remain separate.

## Frame, skin and steps

Estimate the body frame from paired fore/hind roots and the visible torso before assigning mirrored paw lanes. A source can be diagonal even when its wrapper rotation is neutral. If a new anatomical frame must survive engine import, append a real skin joint, reparent the native roots explicitly and verify the original world transforms through that frame. Retain the original node prefix, binds and complete influence sets; declare the rest-frame preparation.

Equal per-leg stride distances do not guarantee equal alternating steps. Original longitudinal offsets can leave one paw stepping past the other while its partner only catches up. Reconstruct successive touchdown positions in a common moving-ground frame, measure signed left-right advances over two cycles and compare their balance. Use a shared paired touchdown origin when the source stagger is an accidental rest artifact. Keep cadence, movement speed and stance duration in the same measurement.

Upper socket fur may be wholly leg weighted even when it visually belongs to the torso. Repair the actual girdle/socket transition through a feathered ownership field. Protect low paw rows and inspect upper-leg volume from side, front and rear; a narrow central belly mask can miss outer socket fur. Pin geometry, UVs, normals, texture bytes and rest-surface correspondence separately from changed skin rows.

## Collapse and release

Keep paw constraints while planted, then blend into articulated released limbs. Preserve native local joint offsets while blending rotations. Interpolating world link directions can preserve lengths at guide poses yet still shorten serial chains between exported keys. Audit every native section on the exported file, including key midpoints.

Include the full released paws in whole-surface clearance. Exclude only actual planted sole cores when necessary; excluding the entire paw population can certify a trajectory that sinks through the floor. A root-height change can alter a partially constrained limb nonlinearly, so re-evaluate the deformed surface after refinement. If a final whole-pose clearance translation occurs before the last hind paw releases, reproject that planted paw and verify contact again.

Keep clearance translation on actual skin joints. Moving a non-joint armature wrapper can pass native and Blender checks while the runtime bone importer drops that wrapper track. If this occurs, bake its translation into every affected skin root, neutralize the wrapper and prove world-space equality over the shared linear intervals. Refresh the final-file engine witnesses.

Separate head, chest and pelvis support envelopes. A combined body minimum may be supplied by one shoulder while the rear torso floats. Fit or audit both disjoint torso regions, whole-surface floor clearance and a still final hold. The suitable resting flank and head hinge are actor-specific; do not impose one signed roll on every native asymmetry.

## Review and delivery

Center tail segment directions in the anatomical body frame while preserving lengths and vertical shape. Spread motion coherently along the tail instead of overdriving its tip. Inspect actual tail skin from both rear quarters as well as the bones.

Use independent GLB surface/bone witnesses for fresh Blender and current Godot imports. Frame the complete all-motion surface envelope, including the tail, rather than only chosen pose samples. Keep native-speed six-angle movies, pose sheets and contact close-ups bound to the exact candidate hashes. Numerical qualification does not imply visual acceptance or permission to install drafts.

## Broader mammal assessment

Treat node labels as hypotheses. A node named upper hind leg may lie below the true pelvis-side hip; using it as the root removes visible thigh motion and can pull knee tissue below the floor. Measure the actual hip, stifle and ankle pivots and their full serial lengths before assigning the chain. Source snout labels can belong to ears or beard strands; do not infer a jaw from the label alone.

A source hip control can sit below the visible haunch rather than at the anatomical pelvis. Where the surface measurements support a higher pivot, a new physical hip guide can parent the original femur helper with compensating local translation. Preserve and prove the original joint world rest, surface correspondence and bind prefix; do not claim original local transforms or inherited animation correspondence when parenting changed. Keep the body motion frame explicit rather than assuming the last appended joint is the frame. When newly weighted guides share a nonidentity prepared rest skin transform, their binds must retain that transform. Inverting a new guide world matrix alone can drop the declared frame for its newly assigned vertices; verify the full prepared rest surface after weighting.

A vertex-only socket column can include a webbed foot or miss a body boundary between large triangles. Compare actual triangle cross-sections with the visible upper-limb mass and attachment. Moving a guide along the torso also changes the rest hinge plane: carrying a wolf sagittal frame onto a sprawling foreleg can produce an axial arm twist while lengths and contacts still pass. Inspect the posed arm before treating that rig error as a skin-weight defect.

Ground height is only one contact check. A native sole can be tilted substantially while its lowest toe stays on the floor. Identify the full physical plantar surface from its triangles and normals, remove duplicate-position sampling bias, and measure plane tilt, longitudinal coverage and height span. Declare the selected surface and a native foot orientation correction explicitly; preserve geometry, use that orientation throughout planted and released phases, and recheck reach, complete-paw clearance and alternating ground advances. A broad, curved sole retains its native curvature; a narrow toe sample is not a flat-paw certificate.

For long-necked or bearded creatures, keep beard/neck ownership separate from the skull and torso. Derive head support from an exposed physical skull or muzzle patch rather than an interior forehead subset or the beard. Preserve the native neck branch through collapse and fit exposed head, chest and pelvis support simultaneously. Inspect the resulting neck pose from both sides and rear quarters.

## Skin repair and diagnostic sampling

A rigid abdomen patch and coincident seam checks can both pass while a different chest or rump edge stretches during the fall. Sample the exported whole-surface edge lengths and local/world joint turns at playback cadence, then inspect the measured worst times from several views. The thresholds used for hard-bodied mammal drafts are not universal limits for elastic bodies or fast wings.

Inspect wrong-side leg and stray skull influences before smoothing. Use welded topology to diffuse only the affected girdle ownership, anchoring rigid cores and complete paw rows. Hard spatial masks can move calf tissue into the torso; a global left/right swap can damage intentionally crossed source geometry. Pin geometry, binds, images and protected paw weights independently.

A skin-only repair can change the floor envelope even when every curve is exact. Recheck keys and midpoints. If a small released-phase clearance correction is necessary, put it on the real skin root after the last planted foot releases, preserve the planted interval and all unrelated channels, and report that one channel changed. Add imported-surface witnesses and diagnostic renders at the actual corrective and worst-deformation times; a few uniform off-grid samples can miss a short event.

For clawed, curved paws, a low toe band can miss the supporting heel even when its fitted plane looks level. A broad lower convex support plane can capture heel and claw pads without flattening native geometry. Require several unique non-collinear contacts, substantial lateral and longitudinal coverage, rigid ownership and a tolerance justified by source quantization. Recheck the actual exported planted plane, complete-paw clearance and stance velocity. Verify that declared pad parameters actually drive the preparation code rather than retaining another pilot's constants.

For armored mammals with disconnected shell bands, apply the complete-component ownership guidance in [native turtle motion](native-chelonian-motion.md). High proximal tail labels can own the shell as well as the visible tail. Keep those armor islands rigid, restrict tail fields to the true posterior shaft, and fair only diagnosed soft transitions with shell, skull and low paw cores anchored.

## Clearance timing and exported contact

A whole-root clearance shift after limb fitting can introduce a paw pop when planted-foot reprojection stops at a Boolean release event. Relax that correction continuously through release while preserving native local section offsets, then refit the actual skin clearance. Moving the whole correction before IK is not automatically equivalent: the changed constrained shape can intersect the floor or exceed reach. A released paw target near the minimum fold radius can still cause a hock twitch. An alternative is to capture the actual corrected release pose and blend its parent-local rotations toward a relaxed body-following pose, retaining native offsets throughout. Match the incoming local angular velocity at release, then ease that short extrapolation out before blending to the relaxed pose. A pose-continuous but velocity-discontinuous release can pass native and Blender checks while dense Godot baking still misses an off-grid basis witness. If clearance is refined, refresh release references against the complete time-varying height field rather than a constant trial height at unrelated times. Check the exported sole-centroid stance velocity on every key and midpoint during collapse as well as during gait and attack.

Filter height envelopes in elapsed time. Index-based dilation or smoothing around inserted, nonuniform event times can produce a sharp root rise even when all fitted key poses have exact contact. Use a uniform time grid or a time-aware envelope, retain the final hold, and recheck full-surface floor, planted contact and local/world angular rates between exported keys. Do not hide such a failure by increasing cadence or relaxing the contact limit.

## Short-legged mammals and facial contact details

A source's named upper-leg helper may sit below the actual shoulder or hip. Adding a high socket alone can leave no useful elbow or knee and cause cuff tissue to follow the wrong section. Measure the visible limb volume with triangle cross-sections, add actual intermediate hinges when needed, compensate original parenting to retain world rest, and repaint the physical upper/hinge/distal sections. Prove the original bind prefix and declared rest surface independently. New weighted controls must keep the common prepared rest skin transform.

Include the complete posterior heel or high cuff in paw clearance even when it rises well above the ankle. Its ownership can otherwise pull a fleshy heel through the floor while a toe-only goal stays exact. Keep the low broad plantar footprint separate from this larger clearance population: require broad non-collinear heel/claw coverage and keep the entire paw above the supporting plane. Do not classify a high cuff as a flat sole merely to increase coverage.

Abrupt ownership decisions can stretch adjacent foreleg/belly or thigh/heel edges even with rigid paw contact and correct section lengths. Inspect the measured edge endpoints and native weights. Fair only the diagnosed welded transitions with complete plantar rows, rigid body cores and detached appendages anchored. Restrict transferred weights to the actual limb's native ownership so diffusion cannot introduce opposite-leg influences or silently discard extra influences. Recheck all exported keys and midpoints, and prove any skin-only revision keeps motion arrays and protected skin rows exact.

A short tail need not become a load-bearing ground support in a flank collapse. Specify required head/chest/pelvis contact separately; keep the whole tail in floor, section-length and shape checks. Detached whiskers can contact before the real skull. Exclude them only from the head's load-support definition, retain their complete floor clearance, and add measured base pivots if a gentle lower-side fold is needed. Keep each whisker coherent and verify its geometry and attachment through the full action.


For a barrel-shaped body, the physical supporting shoulder and haunch can blend body and proximal socket ownership. A rigid-body-only mask can omit the actual outer load surfaces and make an otherwise supported pose appear to fail. Measure those surfaces from the native anatomy, include the appropriate proximal tissue, exclude distal limbs with both ownership and source-height evidence, and keep chest/pelvis regions disjoint. Preserve complete-surface floor clearance and the existing final support limits; do not redefine a foot or lower limb as torso support. Keep an explicit receipt of the region change and inspect the terminal pose from all sides.
