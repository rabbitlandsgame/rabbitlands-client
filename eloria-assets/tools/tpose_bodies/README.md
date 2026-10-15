# Canonical T-pose race bodies

This document records the approved canonical source build at commit
`68f4f6e20e7c11051aecbb580c03b47b89a25393`. The subsequent user-approved
[shared-body equipment build](../../qa/canonical-equipment-refit.md) reuses its
Luminous male/female bodies below the neck and retains the individual race heads
and Ssarathi tails. Its geometry and neck-join reports supersede the physique
inventory here. The skeleton, animation and source-preservation evidence below
remain the reference for that later build.

This build keeps each race's own Meshy T-pose derivative, fits it to the shared
animation library's actual `Rest_Pose`, and partitions its triangles into the
client's appearance surfaces. It does not use the abandoned Luminous head graft.

The September 2026 build contains all 16 catalog entries. Whitehorn source names
map to the client's `votary` slug. Inputs, intermediate GLBs, full reports and
Godot captures live in the ignored `tpose-body-build/` directory of this worktree.
The promoted GLBs live in `godot-client/assets/actors/native/races/`.

## Input and rig contract

The inventory parses GLB JSON and binary accessors; filenames are not evidence
of a rig or surface split. Raw `_tpose.glb` meshes have about 1.9 million triangles
and no skin. The user selected the existing roughly 20,000-triangle
`_tpose_rigged.glb` derivatives, which have one fused mesh and 24 joints.

Every output has the same ordered 77-joint skeleton, full finger chains and
inverse binds built from its rest matrices. The animation library supplies 65
matching body joints; its additional `head_leaf` is not part of the body contract.
The body's 12 unused cape joints retain the template hierarchy/transforms. The
library uses `head`, the body uses `Head`, and `models.json` keeps that bone alias.
No tail bones or new cape weights are introduced. Body hands retain the source's
hand-weighted simplified representation; finger chains remain available to gear.
The existing strict rig report is run with its documented `--mitts` option.

The reference is the **Rest_Pose animation**, sampled at time zero, never the
library's arbitrarily posed node defaults. All body rests are identical, with
Head Y approximately 1.568490 m and pelvis Y 0.916700 m. Tiny export scale noise
is cleared; proportions are baked into vertices rather than joint scales.

## Geometry and appearance

`build.py` reuses the existing limb tool's minimal rotation about each segment's
joint, plus axial length fitting. Source weights blend these transforms. A single
physical pelvis-to-shoulder torso fit preserves chest/breast placement; blindly
mapping Meshy's differently spaced spine names had lowered and over-projected
the chest. Source spine weights are distributed by their fitted physical height.
There is no cutting, welding or head/neck seam surgery.

Shoulder caps are tapered radially around the upper-arm axes. A separate smooth,
localized underside taper reduces the bulky axilla fold without moving the
breasts or waist. Shading normals are reconciled at coincident positions before
the split because runtime normal-grow otherwise reveals split facet edges.

`surfaces.py` adapts the existing UV-centroid palette classifier and small-island
cleanup, with per-side eye contrast, calibrated painted-eye regions where the
human nose prior fails, thin brow patches, a head-weight guard and skull fitting.
Every source triangle belongs to exactly one output part. Parts share the exact
unsplit position/normal/UV/joint/weight accessors. The tool compares every attribute
and the complete face multiset after serialization. Thus fitting changes positions
and weights, but **splitting preserves the fitted unsplit geometry exactly**.

The source-derived parts are `body`, `eyes`, `eyebrows`, `scalp`,
`wardrobe_shirt`, `wardrobe_pants`, and `wardrobe_boots`. Head band and cap add
288 triangles using the existing splitter's ring/dome generators. No artificial
trim/seam material is added where the art does not provide one.

All sources are deliberately bald: the original closed skull provides `scalp`,
and nonexistent sculpted `hair` is omitted with user approval. Both Mycelari
bodies also omit nonexistent painted `eyebrows`, explicitly approved by the user.
Runtime hairstyles remain separate assets. Optional per-model `hairFit` applies
scale and translation to the attached hairstyle in Head-local space. It never
changes the skeleton or its bind matrices. Fits were inspected in Godot from the
side; horns/crystals are retained and may protrude through generic hair/headwear.

Ssarathi tails use the existing **12 mesh-edge-hop smoothstep** feather into
pelvis. Adjacency is welded only for analysis; exported topology is not welded.
The mask includes the striped underside instead of using green texels alone.
Each entire tail is rigidly lifted around pelvis just enough to clear the floor
through the five reviewed clips (34.5 degrees female, 28.5 male). It keeps its
curve and length and remains functionally static relative to pelvis. The female
source soles sit 107 mm above the tail minimum: its original ankle positions are
retained, and only its misplaced toe anchors are rebuilt. A 130 mm calf/foot
transition, feathered ball-joint weights, canonical ball-to-leaf forefoot length
and 12 mm toe-tip clearance keep the boots grounded through toe-off. Static
tests check each weighted sole separately, so a low tail cannot hide floating feet.

## Animation changes

`animations.py` edits only `Idle_Subtle`, `Walk`, `Jog`, `Run_Female`, and
`Fighting_Idle`. It preserves the other 157 clips, including Rest_Pose, numerically.
The runtime `run` action uses **Run_Female**; Jog is reviewed too but is not the
current action mapping. The existing `Sword_Attack` cycle was rendered and
reviewed; its simplified overhead strike/recovery is retained.

- Walk's previously locked knee motion is restored from the same library at
  repository commit `fffb64e77`, whose Rest_Pose matches the current reference.
- Two-bone IK reduces excessive foot lift, retaining the original swing phase.
  Actual skinned boot soles guide the floor-contact correction.
- Clavicles regain the narrower backward sweep of the reference, with a slight
  downward slope. Elbows rest closer to the torso; run arms retain a bent swing.
- Loop endpoint residuals are eased out before contact solving, including the
  original Run_Female right-toe discontinuity.
- The stance-travel measurement in `locomotion_map.py` sets playback stride
  speeds to 0.767 m/s for Walk and 2.759 m/s for Run_Female. Foot travel is within
  one degree of model forward, so obsolete approximately 23-degree facing
  offsets are removed.

## Validation and promotion

`verify.py` independently replays FK and four-weight LBS by library bone name,
unions all index buffers sharing attributes, and samples complete clips at 60 Hz
plus authored keys. Reports include edge-length ratios, absolute edge extension,
loop closure and minimum vertex height. The five clips were replayed on all 16
bodies. The 100 mm maximum edge-extension gate and 20 mm p99 warning are review
limits, not claims of physically accurate cloth deformation.

`godot-client/tests/tpose_body_preview.gd` runs the real `ReplicatedActor3D`,
animation importer, appearance system, hair attachments and equipment binder in
Godot 4.7.2. It captures gameplay/front/side angles, tint/headwear changes, native
gear and animation cycles. Its paused simulation explicitly completes the facing
blend before capture. Reported engine bone poses match the independent replay
within 4e-7 in the sampled matrices. Offline rendering is not used as socket proof.

The live legacy gate is `generate_models/meshy_to_client/promote.py` (not the
previously documented `rigged_races/promote.py`). The new `promote.py` imports its
pure checks through AST without modifying that unversioned directory, runs
`rig_report.py --strict --mitts`, and adds exact-rest, inverse-bind, replay,
surface-preservation and hash-matched Godot evidence checks.
For migration iterations, strict weight expectations use the hash-verified
original shipped snapshot. An intermediate output must not redefine a keyed toe
bone as permanently unused merely because that iteration omitted its weights.
Names/order still compare with the current destination and rests with the library.

An explicit `--canonical-rest-migration` replaces only the old per-body Head-Y
tolerance. Eleven old body heights cannot meet that 20 mm tolerance while also
matching the user's required shared Rest_Pose. Reports retain the original
legacy failures, old/new Head values and runtime rig-fit scale. Migration requires
installed hairFit metadata and actual fitted-hair/native-equipment captures.
No name, order, socket, skin-region, rest, weight or deformation failure is waived.
Promotion is restricted to this isolated `wt-*` checkout and rechecks hashes
immediately before writing. The main client checkout is not overwritten.

Known limits: preexisting militia armor has displaced sleeve envelopes on both
the shipped control and new bodies. Successful native binding does not certify
that armor's silhouette. Generic equipment can intersect retained horns/crystals
or mushrooms. Ssarathi male has p99 upper-leg edge extension around 30–31 mm in
Jog/Run_Female; its maximum is below 64 mm and rendered cycles show no open tear.
Other reviewed bodies stay below the 20 mm p99 warning. Small source texture
boundaries at collars remain visible. On the original build base, the equipment
suite had three preexisting failures (unused fit groups, legwear hems, and
closed-shell assumptions), plus an older boot's 13 mm offset below the newly
grounded body. After integrating develop at `15a848d43`, its newer equipment
passes the closed-shell check; three equipment checks still fail: unused fit
groups, legwear hems, and boot clearance (26.2 mm below the luminous male sole).
Equipment still requires refitting. The 15 body/native-binding checks and the
Godot animation-looping test pass on the integrated code. The upstream torso
cover/equip/unequip test passes on all 16 races; combined armour coverage passes
528 transitions and 20,228 checks. Fresh Luminous female and Ssarathi female
Godot captures cover walking, tints/headwear, fitted hair and native equipment.
These limits are recorded rather than hidden by an offline-only pass; the
equipment suite is not claimed to be green.

## Reproduce in this checkout

Use Python with NumPy, SciPy and Pillow. Run commands from this worktree root.
The saved input manifest records SHA-256 and the original path of each snapshot.
Keep scratch `in/` and `out/` distinct. Build/split/animation tools refuse client
asset output paths. Re-inventory changed sources before replacing any snapshot.

```powershell
$py = 'C:/Python/Python313/python.exe'
$tool = 'eloria-assets/tools/tpose_bodies'
& $py "$tool/audit.py" --out tpose-body-build/reports/inventory-current.json

# Initial pilot fit against the snapshotted library's Rest_Pose.
& $py "$tool/build.py" tpose-body-build/in/luminous_human_female_tpose_rigged.glb tpose-body-build/out/luminous_female_unsplit.glb --library tpose-body-build/in/Universal_Animation_Library.glb --template tpose-body-build/in/luminous_female.glb
& $py "$tool/surfaces.py" tpose-body-build/out/luminous_female_unsplit.glb tpose-body-build/out/luminous_female.glb

# The historical donor is extracted from the repository at commit fffb64e77.
& $py "$tool/animations.py" tpose-body-build/in/Universal_Animation_Library.glb tpose-body-build/in/library_before_pose_tuning.glb tpose-body-build/out/Universal_Animation_Library.glb --contact-body tpose-body-build/out/luminous_female.glb
& $py "$tool/locomotion_map.py" --write
& $py "$tool/verify.py" tpose-body-build/out/luminous_female.glb --library tpose-body-build/out/Universal_Animation_Library.glb --template tpose-body-build/in/luminous_female.glb --clips Idle_Subtle,Walk,Jog,Run_Female,Fighting_Idle --out tpose-body-build/reports/luminous_female_validation.json
& "$tool/render.ps1" -Prefix pilot -Cycles

# Inspect actual captures; record an honest, hash-matched visual review.
# batch.py refuses to proceed without the current pilot review.
& $py "$tool/batch.py"
& $py "$tool/render_batch.py"
& $py "$tool/install.py" metadata

# Inspect every body, then invoke this once per reviewed slug.
$slug = 'luminous_male'
& $py "$tool/promote.py" "tpose-body-build/out/$slug.glb" --slug $slug --library tpose-body-build/out/Universal_Animation_Library.glb --review "tpose-body-build/reports/${slug}_visual_review.json" --canonical-rest-migration --write

# Refuses until all 16 are promoted against this exact library.
& $py "$tool/install.py" library
```

The pilot's reviewed shared-hair fit is scale `[1.02, 0.8246916389194927, 1.08]`,
offset `[0, 0, -0.015]`, saved as `out/luminous_female.hair-fit.json`.
Other fits are derived by `batch.hair_fit` and still require engine inspection.
The Windows render tools launch Godot without visible helper windows. Render
evidence is generated output, not committed source art.

## Reused implementation sources

- `vendor/glbkit.py`, `vendor/retarget.py`: `generate_models/meshy_to_client/`.
- `vendor/fix_limbs.py`: `generate_models/limb_fix/fix_limbs.py`.
- `vendor/split_reference.py`: the mature classifier in
  `wt-luminous-human/eloria-assets/tools/split_race_surfaces.py`; only classification
  and smoothing are reused, never its branch's head-graft architecture. Local
  change: eye contrast thresholds are computed independently for each side.
- GLB append/read helpers and headwear generators: the current checkout's
  `eloria-assets/tools/split_race_surfaces.py`.
- Tail feather policy: `eloria-assets/tools/fix_ssarathi_tail_weights.py`.

Vendored modules are imported as libraries. Their original standalone entry
points are not pipeline commands and may retain paths from the earlier tools.
