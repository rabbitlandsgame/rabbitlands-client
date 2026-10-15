# Equipment on shared canonical player bodies

## Current layout (2026-10, after the race programme)

The text below this section records the September 2026 shared-body delivery.
Since then:

- **Bodies.** The Human bodies (`races/luminous_<sex>.glb`) were regenerated on
  2026-10-05, and all fourteen race bodies were rebuilt on them below the neck
  by `rebase_race_body.py` (build, verify, install, post-import), with horns,
  crowns, crystals and growths on their own `race_feature_*` nodes.
- **Torso, legs, boots (200 designs).** One fit per sex, on the Human body:
  `variants/human_male|human_female/<slug>.glb`, registry groups
  `canonical_human_male|female`. Every race lists its own group first and
  falls back to the Human group of its sex.
- **Headwear (64 designs).** The Human fits plus one fit per race body:
  `variants/<race>/<slug>.glb`, group `canonical_<race>` (896 race variants).
- **Base scenes.** Each generated model's base `scene` is its
  `canonical_human_male` file (`authoredFor: human_male`, mapped to
  `luminous_male` by `authoringRigs`). The race programme's P7 cleanup
  (2026-10-08) deleted the old-male base scenes `equipment/<slug>.glb` (264),
  the `variants/luminous_female` scenes (264) and the 128 textures only they
  named, dropped the `canonical_luminous_*` variants, and set
  `fitGroups.luminous_<sex>` to `[canonical_human_<sex>]`. A simulation of all
  6,864 body-by-model resolutions showed nothing worn changed.
- **Retired tools.** `refit_canonical_equipment.py build` and
  `pack_canonical_equipment.py pack|install` raise (`build_one`,
  `tool_hashes`, `pack_glb` and `validate` drive the current tools);
  `import_generated_equipment.py` no longer rebuilds an installed piece's
  `equipment/<slug>.glb` (it builds installed pieces only into scratch, with
  `--meshes-only --build-dir`);
  `build_shared_player_body_set.py`, `prepare_shared_registry.py`,
  `revise_class_equipment_fit.py`, `build_class_equipment_fit_references.py`,
  `install_neck_refinements.py`, `repair_ssarathi_*`, `build_neck_textures.py`
  and `verify_orun_neck_apron_mask.py` are deleted; they remain in git history
  (last present at a35ff1c43).

All races now use the Luminous male or female body shape below the neck, with
their original heads and Ssarathi tails retained. A continuous neck adaptor
joins each head to its body. Equipment is rebuilt from the original Meshy
`.glb.orig` designs and fitted to those two body shapes.

This supersedes the earlier sixteen-body equipment delivery. The isolated
worktree began at `68f4f6e20e7c11051aecbb580c03b47b89a25393`.
Item definitions and gameplay stats are unchanged.

## Two body shapes, preserved race identity

There are **two body equipment fits**, with 200 torso/leg/boot designs each,
and 64 headwear designs fitted to each of the sixteen retained heads: 1,424
equipment GLBs in total. The client still loads sixteen assembled race GLBs;
each contains the common body plus its individual head and optional tail.
This is geometry reuse in authoring, not a runtime modular-head loader.

The source Luminous shoulders, armpits, female chest and limbs are preserved
outside the localized neck transition. All bodies keep the same ordered 77
joints, inverse binds and canonical Rest_Pose. Head rest Y is
`1.5684900288581848`; pelvis rest Y is approximately `0.916700`.
Idle_Subtle, Walk, Jog, Run_Female and Fighting_Idle, runtime run selection,
hairFit, original head features and the Ssarathi pelvis-bound tail are retained.
Whitehorn uses `votary`. Mycelari eyebrows remain absent.

The neck joins the common upper chest to the retained head with several
anatomical rings. Boundary copies have identical positions, normals and skin
weights; all sixteen reports have zero unmatched boundary edges and zero
attribute deltas. A continuous cylindrical texture blends into the retained
head boundary. The original shirt collar is restored as a separate wardrobe
surface on unequip. Geometry is approximately 20,000 triangles per assembled
body. Original source triangles, UVs and skinning outside the explicit cut
remain intact, as verified by triangle-level comparison.

## Equipment fitting and visibility

Torso remapping measures source trunk walls, separates sleeves from the medial
seam and poses each source part into canonical limb frames. Per-band surface
envelopes fit the chest without parity saturation on overlapping closed shells.
Short ornaments travel whole. Low hem tabs stay with the trunk. The three
previously requested raised collars retain their 45 mm lift.

Original armour positions, normals, UVs, indices, texture bytes and skin weights
in the final neckline revision match all 128 reviewed male/female torso fits
exactly. They were rebuilt from original sources using the verified original
canonical Luminous templates as stable anatomical skin samples. Only the
replacement lining follows the reconstructed neck surface. This prevents new
neck tessellation from changing sleeve/plate weight inheritance.

The lining's central neckline is clipped before thickening, with the shoulder
coverage retained. This removes folded backing shards at the throat. Runtime
coverage keeps neck skin, hides the old shirt collar and preserves the default
torso region when adding that collar region. Body cover changes private index
buffers only; exact mesh/material restoration on unequip is tested.

Leg and boot fitting use original source parts, weighted foot chains and
continuous garment weight fields. Tail vertices cannot supply foot landmarks
or garment weights. The reported Bark Legguards 49.6 mm hem came from backing;
the test now measures original visible art, verifies that it clears the foot
and checks overlap with its matching boot. It does not merely loosen the old
absolute bound. Boot sink and floating limits are checked against each weighted
sole, including the former Amberwood 01 failure.

Lowercase split surfaces are selected explicitly. Shared attribute accessors
are read once and their relevant face buffers are united. Wardrobe samples
participate in fitting. Both authoring and runtime use the current head rest
reference for canonical fits. `fitProfiles.legacy` retains the old `1.5998`
reference for existing socketed props and applies its approximately `0.980429`
compensation once. Matching body templates bypass additional girth and sole
correction; slimmer bodies do not depend on the legacy `[1,2]` clamp.

BodyGirth, footAnchor, soleDrop and fitGroups were measured again. Shared-body
soles are approximately 2.56/0 mm for males and 0.72/0 mm for females. Per-race
stature remains an actor transform. Per-surface skin tints, wardrobe normal
grow, matching combined-set backings and lining variants remain active.
Closed headwear hides/restores hair and scalp; open bands preserve hair.

## Measurements and tests

Independent front-depth measurements use the actual current bodies. These
are distinct from the older 68% headline baseline on previous bodies.

| Template | Median covered chest width | Worst covered width | Proud cells, with backing |
| --- | ---: | ---: | ---: |
| Male | 100% | 95.008% | 407,751 |
| Female | 100% | 95.497% | 403,756 |

The final neckline change adds one male proud cell and leaves the female count
unchanged. Original-art proud counts remain 403,277 and 399,931 respectively;
original-art worst widths are 88.240% and 92.014%. The fitted backing fills the
remaining designed openings. Original-source, true-scale worn and gameplay
images are supplied separately so coverage cannot conceal silhouette errors.

Installed validation:

- 48 equipment/fitter tests pass, including all declared variants and boot/hem checks.
- 15 relevant body/binding tests pass, with 2,256 passing subtests.
- Animation looping passes.
- Torso cover and equip/unequip pass on all sixteen races.
- Combined armour passes 528 transitions and 1,144,460 checks.
- Fit profiles pass 23,205 checks, including material restoration and legacy sockets.
- Historical torso tests retain thirteen existing failures; sorted full identifiers
  with multiplicity show no new failures. The flat-decoration classifier failure
  is resolved. Retired visual-ID assumptions remain in that historical suite.

All sixteen changed bodies were replayed through five complete locomotion
cycles using FK and linear-blend skinning, sampling source keys plus 60 Hz.
The final 128 torso fits were replayed again: 1,280 surface/clip records,
maximum loop drift 0.00191 mm. Remaining stretch warnings are below.
The installed client supplies 90 front/side/gameplay captures across Luminous,
Ssarathi and Mycelari male/female through all five clips. Separate open-collar
front/side/back views cover every race; exception close-ups include 24-frame
cycles. These use the real actor, appearance, equipment and animation paths.

## Review evidence and storage

Current evidence is in [shared-equipment](shared-equipment/manifest.json):

- [Male neck joins](shared-equipment/sheets/neck-male-1.jpg) and
  [remaining males](shared-equipment/sheets/neck-male-2.jpg);
  [female neck joins](shared-equipment/sheets/neck-female-1.jpg) and
  [remaining females](shared-equipment/sheets/neck-female-2.jpg).
- [Male complete sets](shared-equipment/sheets/blender-sets-male.jpg),
  [female complete sets](shared-equipment/sheets/blender-sets-female.jpg),
  [Ssarathi/Mycelari complete sets](shared-equipment/sheets/blender-exceptions.jpg).
- Six `godot-<race>.jpg` sheets show installed gameplay through five clips.
- `comparisons/` contains both source and worn PNGs for Phoenix 01,
  Ranger 05 and Amberwood 04.
- `reports/` contains exact installed test logs, body geometry/motion reports,
  coverage, source-art identity checks, motion comparison and packed hashes.

Earlier equipment before/after sheets remain under
[canonical-equipment/sheets](canonical-equipment/sheets/). Their original
sixteen-fit measurements are historical and do not describe the shared-body set.

Equipment geometry plus shared textures totals **1,833,800,330 bytes (1.834 GB)**,
down from approximately 7.97 GB for the sixteen-body draft: about 77% smaller.
2,800 redundant body variants are omitted. Identical images share content-addressed
files; eligible indices use unsigned 16-bit storage without changing their values.
Every decoded accessor and image is checked during packing.

Large captures and editable `.blend` files remain in ignored local scratch,
not the delivered Git tree. Final complete-set scenes are in
`equipment-fit-build/shared-bodies/preview/shared-16-blender/`; each set has
armour-only and worn scenes. Historical full-resolution evidence is retained in
`equipment-fit-build/shared-bodies/archived-16-fit-qa/`. The evidence manifest
records local paths and hashes. Compact review sheets and required source/worn
PNGs are versioned. Clean delivery history excludes the oversized draft commits.

## Reproduction

Run from an isolated client worktree. Keep scratch input/output separate from
client assets. Recover the sixteen original canonical bodies from commit
`68f4f6e20e7c11051aecbb580c03b47b89a25393` into a new scratch input directory
(binary-safe Git extraction); retain them as read-only anatomical references.
Original Meshy `.glb.orig` files remain in the adjacent `generate_models` folder.

**Current path (2026-10).** Fit the Human bodies, then each race body's
headwear; both drive `refit_canonical_equipment.build_one` from the original
Meshy sources. Install order is pack, then share textures, then commit.

```powershell
python eloria-assets/tools/refit_human_bodies.py --bodies <dir holding luminous_male.glb and luminous_female.glb> --out <scratch> --pieces all --jobs 4
python eloria-assets/tools/install_human_equipment.py <scratch> --tag human
python eloria-assets/tools/share_human_equipment_textures.py
python eloria-assets/tools/refit_race_headwear.py fit --out <scratch> --tag <t> --pieces all --races all --jobs 4
python eloria-assets/tools/refit_race_headwear.py measure --out <scratch> --tag <t>
python eloria-assets/tools/refit_race_headwear.py human-check --out <scratch> --tag <t>
python eloria-assets/tools/refit_race_headwear.py install --out <scratch> --tag <t> --rigs <race slugs, comma separated>
```

`install_human_equipment.py` writes the two Human variants per piece, keeps a
piece's base fields equal to its `canonical_human_male` variant and sets
`fitGroups.luminous_<sex>` to the Human group alone. `refit_race_headwear.py
install` refuses fits whose recorded fitter, race-pass, body or policy hashes no
longer match the checkout, writes `variants["canonical_<race>"]` only and never
touches `fitGroups`. Race bodies come from `rebase_race_body.py`; race hair from
`fit_character_appearance.py --race`.

**Refit before reinstalling.** `tool_hashes()` hashes
`refit_canonical_equipment.py` itself, and its retirement edit (2026-10-08)
changed that hash. Every fit recorded before it - the installed P5 headwear
fits, and any `refit_human_bodies.py` tag - now fails the fitter check:
`refit_race_headwear.py install` refuses it ("fitter changed since the fit")
and `--resume` will not reuse it ("Use a new tag; candidate is not an
unchanged resumable build"). The installed variants are unaffected; run the
fit again under a new tag before the next install. Run
`share_human_equipment_textures.py` after
`install_human_equipment.py` and before committing: it matches only shipped
(1024 px) textures, so after a commit a piece whose other scenes no longer name
the shipped texture is re-encoded into a duplicate.

The rest of this section is the September 2026 path, kept as history. Its
`build_shared_player_body_set.py`, `prepare_shared_registry.py`,
`refit_canonical_equipment.py build` and `pack_canonical_equipment.py
pack|install` steps are retired (see the top of this file).

```powershell
(Get-Process -Id $PID).ProcessorAffinity = [intptr]255
$env:OPENBLAS_NUM_THREADS = '1'
$env:OMP_NUM_THREADS = '1'
$env:MKL_NUM_THREADS = '1'
$env:BLIS_NUM_THREADS = '1'
$env:NUMEXPR_NUM_THREADS = '1'
python eloria-assets/tools/build_shared_player_body_set.py --sources equipment-fit-build/shared-bodies/in --out equipment-fit-build/shared-bodies/rebuilt --jobs 4 --library godot-client/assets/actors/native/shared/Universal_Animation_Library.glb
```

`verify_shared_player_bodies.py` checks original head/tail/common-body triangles,
skeleton and every neck boundary. `prepare_shared_registry.py` prepared measured
equipment/model/catalogue metadata for reviewed scratch body candidates.
`install_shared_equipment.py install --plan <reviewed-plan.json>` installs only
explicit replacements/removals after validating all expected hashes. The plan
format is `replace: {path: {source, sha256, expected}}`, `remove: {path: sha256}`
and `protected: {path: sha256}`. Do not export Blender directly over client assets.

For equipment rebuilding on the installed shared bodies, use a fresh snapshot
and measurement path. **Both reference options matter**: head references retain
socket landmarks; anatomy references stabilize torso art and skin samples.

```powershell
python eloria-assets/tools/pack_canonical_equipment.py snapshot
python eloria-assets/tools/refit_canonical_equipment.py measure --measurements equipment-fit-build/reports/rebuild-measurements.json
python eloria-assets/tools/refit_canonical_equipment.py build --tag rebuilt --races all --pieces all --jobs 6 --measurements equipment-fit-build/reports/rebuild-measurements.json --head-reference equipment-fit-build/shared-bodies/in --anatomy-reference equipment-fit-build/shared-bodies/in
python eloria-assets/tools/audit_canonical_batch.py equipment-fit-build/out/rebuilt --out equipment-fit-build/reports/rebuilt-audit.json
python eloria-assets/tools/audit_canonical_coverage.py equipment-fit-build/out/rebuilt --jobs 2 --out equipment-fit-build/reports/rebuilt-coverage.json
python eloria-assets/tools/audit_canonical_motion.py equipment-fit-build/out/rebuilt --out equipment-fit-build/reports/rebuilt-motion
python eloria-assets/tools/pack_canonical_equipment.py pack rebuilt --out-tag reviewed
```

The builder deduplicates body-template work while retaining sixteen head fits.
`pack_equipment_revision.py` supports partial original-source revisions with
explicit parent, audit and body evidence, including original-art identity guards.
Installation remains separate from packing. Never regenerate item definitions;
always use `--meshes-only` if invoking the older batch driver (since 2026-10
also `--build-dir <scratch>`: it no longer rebuilds installed pieces in place).

`capture_canonical_equipment.ps1` and `canonical_equipment_preview.gd` reproduce
actual client views. `compare_conformed_piece.py --ensemble --save-blend`
produces complete-set Blender scenes; provide `--worn` for the body sheet and
`--worn-pose source` for posed arms. Renderer masking preserves imported corner
normals. Refresh the Godot editor import cache before integration tests.

## Remaining limitations

- This provides two common body shapes, not two physical race files. Headwear
  remains individual because head shapes, horns, crystals and mushrooms differ.
- Source texture charts still contain dark markings and stretched details,
  most apparent on Glasswarden neck skin and some armour. The neck has no open
  boundary or mismatched join normals; source texture cleanup is separate.
- Original long-cloth stretch warnings remain. Final torso maximum extension
  is 93.29 mm on the male Patched Workshirt. The neckline change leaves original
  art skinning identical but increases some lining warnings: maximum +4.67 mm
  on male Frontier 03 Jog and +6.20 mm on female Arcane 02 Fighting_Idle;
  largest lining p99 increase is +3.90 mm on female Militia 08 Jog.
- The pre-existing Ssarathi male upper-leg p99 warning remains approximately
  30–31 mm in Jog/Run_Female. A new internal tail-root closure edge reaches
  approximately 85.5 mm maximum extension; that cap is inside the pelvis.
- Battle Gauntlet `0:184` remains a rigid hand-socket prop with protruding
  fingers; it is not a finger-skinned glove and is outside the 264 generated
  torso/head/leg/boot designs. Existing socket behaviour is preserved.
- Headwear and hairstyle review is representative, not every possible pairing.
  No standalone executable export was tested; this checkout has no export preset.
