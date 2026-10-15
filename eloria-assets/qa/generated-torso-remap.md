# Source-pose torso conversion

> Historical report for the previous body generation. The 16 current bodies
> now share the canonical Rest_Pose and split wardrobe surfaces; references
> below to 14 fused bodies and older fit measurements are obsolete. See
> [the canonical-body equipment refit](canonical-equipment-refit.md) for the
> current authoring, runtime units and validation.

The 64 generated torso pieces now enter `torso_remap.build` directly from
`conform_equipment.build`. They read the `.glb.orig` sibling when it exists.
The previous seat/repose/unsquash correction chain does not run for torsos.

The source frame uses the common concept-sheet shoulder/waist proportions and
measures each cuff independently. The trunk maps shoulder-to-waist onto the arm
roots and pelvis, with the same initial frontal X/Y scale. Each sleeve maps
isotropically from its source shoulder/cuff frame onto upperarm/hand. Welded
pauldron islands move together and bind to the clavicle. Long sewn cloth blends
at the attachment; fused flank/sleeve bridges that stretch excessively are
opened and backed instead of becoming textured triangle fans. Front/back
contact rays then fit an affine depth cage; short ornaments translate whole.

The three reviewed designs (Phoenix Cuirass, Mossfringe Jerkin and Leafscale
Cuirass) also receive the requested 45 mm lift at the collar top. This blends
up from the shoulder height; pauldrons remain fixed and short collar ornaments
translate whole. The resulting collars reach approximately 1.633 m on the
authoring rig and clear the chin in the worn comparisons.

The replacement backing carries body skin weights, fits inside the artwork's
sleeves and collar, and takes its colour from the original sleeve texture. Its named mesh
enables `TorsoBodyCover` only when the replacement actually loaded. The runtime
copies body index buffers to suppress covered default clothing, including the
14 races whose shirts are painted into their body atlas. Original mesh
resources, UVs, materials and weights remain available and are restored on
unequip. Other torso equipment keeps its previous wardrobe behaviour.

Original artwork UVs, embedded JPEG bytes and double-sided material behaviour
are retained. JPEGs now have the correct MIME type; the previous writer labelled
them PNG and caused corrupt Godot image sidecars. Coincident opposing triangles
are deduplicated instead of being mistaken for zero-volume closed shells.
Keeping the original geometry and images increases the shipped GLBs from about
0.4–0.8 MB to 3.2–5.6 MB each. Runtime performance and LODs have not been benchmarked
as part of this fit validation.

## Measurements

`generated-torso-remap.json` is produced by `tools/audit_torso_remap.py`. Its
orthographic triangle raster is independent of the fitter's contact rays.
The original unmasked body remains the denominator and depth reference for
both covered width and absolute proud cells.

| Version | Median chest coverage | Absolute proud cells |
| --- | ---: | ---: |
| Task's initial meshes | 68.06% | 483,341 |
| Intermediate profile fit (`8d2e7e29d`) | 100% | 741,855 |
| Source-pose conversion | 95.41% | 733,726 |

No piece loses proud cells against the task's initial meshes. Against the
intermediate profile fit, 37 pieces lose some geometric proud cells and the
aggregate is 1.10% lower; the original silhouette is allowed to sit inside the
loose default shirt. The runtime replaces that shirt. Against the task's initial
meshes, aggregate proud cells rise 51.80%. A separate raster of surviving
body triangles records **zero visible body cells for every piece** in the
audited torso region. Minimum geometric chest coverage is 93.10%.

| Piece | Geometric chest coverage | Proud cells | Visible body cells |
| --- | ---: | ---: | ---: |
| legendary_hero_cuirass_01 | 100% | 11,779 | 0 |
| leather_ranger_torso_05 | 93.10% | 8,897 | 0 |
| amberwood_woodland_cuirass_04 | 93.10% | 11,054 | 0 |

These numbers cover the fixed front rest-pose grid, not every view or animation.
The comparison renderer also resets all imported pose bones before posing the
body and equipment together. It reproduces the replacement mask only for meshes
carrying the new backing. Both normalized original/fitted sheets and true-scale
worn sheets were rendered for all three pieces, with additional bent-arm and
side checks. A side check caught excessive backplate displacement from nearly
coplanar shoulder contacts. Using the outer contact envelope, limiting band
depth ease to 35% and its translation to 25 mm removed that fault; a regression
fixture checks it. Local final front renders are in
`qa/torso-remap/*-shipped*.png`.

## Validation and rebuild

The captured test baseline has 31 failure identifiers. The final run has 17:
14 existing failures removed, **no new identifiers**. The remaining failures
include one existing generated topology case and the existing authored
garment/registry/legwear failures. The new conversion tests and the existing
profile tests all pass (eight tests), including collar height, fixed shoulders
and rigid collar ornaments. Headless Godot checks pass for body masking
and exact restoration on all 16 races, plus 48 actual equip/unequip cycles for
the three selected generated pieces on every race. Hair and eye meshes are
excluded from body replacement.

The second block below is the September 2026 run, which rebuilt the old-male
base scenes `equipment/<slug>.glb` in place. Those scenes were deleted in the race
programme's P7 cleanup (2026-10): every torso now ships as its Human fit
(`variants/human_male|human_female/<slug>.glb`, refit with
`refit_human_bodies.py` and installed with `install_human_equipment.py`), and
`import_generated_equipment.py` no longer rebuilds an installed piece in place.
To repeat this audit on rebuilt meshes, build them into scratch and audit that
folder; without `--directory` the audit reads the installed Human male fits:

```powershell
python eloria-assets/tools/import_generated_equipment.py --meshes-only --build-dir <scratch>
python eloria-assets/tools/audit_torso_remap.py --directory <scratch> --out <scratch>/generated-torso-remap.json
```

The September 2026 run (history; its first line no longer rebuilds anything):

```powershell
python eloria-assets/tools/import_generated_equipment.py --meshes-only
python eloria-assets/tools/audit_torso_remap.py --out eloria-assets/qa/generated-torso-remap.json
cd godot-client
python -m pytest tests/test_torso_coverage.py tests/test_equipment_fit.py tests/test_torso_remap.py tests/test_conform_torso_profile.py -q
./Godot_v4.7.2-stable_win64_console.exe --headless --path . --script res://tests/integration/torso_body_cover.gd
```

The full 264-piece meshes-only rebuild succeeded; the final torso refinement was
rebuilt through eight meshes-only sheet runs. The 64 headwear files whose BIN
chunks were unchanged were restored individually. Godot's eight modified
tracked image sidecars were also verified against the imported original image
bytes and restored individually. Item definitions and balance data were not
changed.
