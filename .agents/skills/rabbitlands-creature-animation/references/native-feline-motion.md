# Native feline pilots

Use this reference for the current imported cat family. All seven cats have user visual acceptance. Puma, Leopard and Cheetah use the simple native profiles; Moonshadow Lynx, Ice Snow Leopard, Stormmane Lion and Tidal Crystal Lion use separate ornate profiles; shared category intent does not establish shared rig topology. The installed behavior and portable checks are documented in `docs/felid-motion.md`. Current selections, receipts and any unfinished jobs live in the private `working/memory/felid-motion-20261017.json` under the authoring workspace.

## Anatomy before transfer

The simple trio has the same 25-joint hierarchy, but its visible surfaces do not share identical anatomical centers. Measure each paired physical pad from strongly owned low vertices. In Puma, the visible body and paws are offset from the skeleton's x=0 plane. A side test against x=0 incorrectly splits its right paw and creates a spike during alternating steps. Record the physical fore/hind midplanes and use anatomical side ownership rather than the armature origin when repairing cross-leg leakage. Preserve native joint-role proportions when redistributing opposite-leg weights; do not flatten an entire limb onto its foot.

Keep repairs in a versioned prepared input. Feather low paw ownership into the native lower limb, and audit central chest/pelvic underside separately from the legs. Compare unchanged rows exactly, preserve geometry/rest/binds/images and inherited curves, and measure identical original topology at identical poses. A repaired pad can reduce one defect while creating a harsh transition higher on the leg. Inspect the worst original edge and coincident seam pairs; a contact pass alone does not certify skin quality.

## Motion and articulation

Use category behavior, not another family's curves: a four-beat cat walk and diagonal trot differ from paired rabbit hopping. Keep the faster gait labelled as a trot unless a separate gallop is actually authored. Block pounce anticipation, launch, reaching forepaws, landing and recovery in seconds. Coordinate torso recovery with the returning paw targets; moving the body back before the reaching paws release can exceed native length even when the initial strike fits.

A projected pole vector can swivel rapidly when a collapsing limb's direction approaches that pole. In this pilot, retaining the signed native flexion-plane normal through Death removed the fast elbow swivel. This is a mode-specific native adapter, not a requirement to change already qualified gait or attack articulation. Review the full approach and off-grid local/world rotations; endpoints and locked paws can remain valid through a severe swivel.

Fit fallen support from actual skin, including the native free-limb fold and full visible tail. A swept tail surface can touch the floor although every tail rest joint is on the skeleton's center line. Turn the relevant section coherently in the action, preserving source geometry/rest unless a rest correction is explicitly requested. Use anatomically distinct muzzle and body-side patches; label proximal haunch/shoulder support honestly. The simple cats' forward face blends neck and head influences, so a strict Head-only threshold loses the actual muzzle. Multiple feasible starting poses can resolve a local support-fit minimum without relaxing the floor or head-clearance gate.

## Export and review

Measure actual exported interpolation. The initial 1536 Hz trot narrowly failed the existing planted-paw velocity gate between keys; 3072 Hz source sampling fixed that residual in the pilot without changing stride. Do not make this a universal rate. Keep per-slot rates in the manifest and test the current client's supported bake cadence through independent off-grid witnesses; the present loader caps declared cadence at 3072 Hz.

Package normal-speed side/game/front movies and same-time rear/opposite pose evidence. For dense GLB previews, test Blender imports at a sufficiently high scene time base. In this pilot, importing the 3072 Hz trot at scene 24 fps introduced about .0015 unit-height joint error; importing and evaluating at scene 240 fps reduced the error below .000001. Keep video cadence and normal-speed seconds separate from that scene time base, and retain independent witnesses. This is an observed preview-import issue, not a reason to alter the runtime curves.

A comparison-only unit-height normalization must be disclosed and must not alter runtime scale. Preserve Idle, Fighting Idle and Hit when revising the four movement/action slots. Keep authored behavior, exported contact/fidelity, fresh imports, engine playback and user visual acceptance as separate facts. No reference video was used for this pilot.

## Ornate native rigs

Identify the skin actually referenced by the visible mesh. An asset can contain additional unweighted rigs with duplicate bone names; a union of those rigs is not the physical skeleton. Keep unused rigs inert during new actions and bind witnesses to the primary skin. Preserve all serial segments even when an IK chord spans an intermediate native joint. Sibling heel helpers should follow their physical paw. A mane, beard or crown accidentally parented to a leg needs explicit head-following groups; low-paw repair must exclude those groups.

Fit pivot defects in a prepared rig, rebase inverse binds, and preserve inherited animation through parent/self rest deltas. Translation resampling must include original breakpoints as well as a dense grid: omitting a breakpoint can change an inherited action despite a high average sample rate. Compare geometry, attributes, binds and images by logical contents, rather than accessor indices after lossless packing. Respect each joint accessor's component type and stride; these ornate models use byte joint indices.

A shortest-arc segment alignment can flip around the limb axis as its vectors become opposite. A complete segment frame, including the signed flexion-plane normal, removes that ambiguity. A poorly oriented source hinge may still need a geometry-guided plane. Keep mode-specific choices explicit and inspect the actual surface, especially armored legs. Density cannot repair a real pose discontinuity.

Check both maximum reach and minimum folded distance, `abs(upper_length-lower_length)`. A reach check that only reports target distance beyond the total length silently accepts overfolding. In the ornate pilot, high free paws crossed the minimum fold radius and caused sharp twists. Smoothly limiting the free wrist's rise relative to its physical shoulder/hip avoided that singularity while leaving planted targets alone. Recheck full motion, floor clearance and all serial lengths after this adjustment.

The current client importer transfers bone tracks; it can omit animation on a non-bone armature wrapper. If independent engine witnesses expose this, bake that wrapper's world motion into its physical root bones while neutralizing the wrapper track. Verify primary bone worlds and the full skinned surface at source breakpoints and between them. The intentionally neutralized wrapper itself is not a preserved world-pose witness. Do not claim inherited channel bytes are unchanged after this adaptation.

Use the full native support envelope when fitting an ornate fallen pose. A thick mane/jaw can support the head while the upper nose remains above the floor; report both separately. Include proximal shoulder armor in body support and inspect each native tail. Twin tails are authored features to preserve, not a horizontal-centering defect.

Float32 storage can leave tiny contact residuals in a large rig. If required, bound any compensation in existing distal translations to measured quantization scale, record the delta and hashes, and recheck native lengths and between-key planted-surface velocity. Such compensation is not permission to stretch a leg or relax a contact gate.

Retain exact support-event keys, but inspect nearly coincident regular-grid keys. In this pilot, a grid point only a few microseconds from an event amplified float32 contact noise; removing that redundant nearby grid point retained the event and reduced the residual. Two remaining trot slots needed extra distal-translation samples within existing rotation intervals. Keep such refinements scoped and numerically bounded, and verify the current engine's actual cadence rather than raising a global sampling rate.
