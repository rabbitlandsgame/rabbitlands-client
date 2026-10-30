# Torso collar audit

All 64 torso designs have revised male and female native fits (128 GLBs).
The later [second equipment review](second-review.md) supersedes overlapping
file hashes and adds the Guard/Silver Ward collar refinements.
Oversized collars are shorter and narrower, with their openings centered on the
wearer's neck. The deformation fades into the existing chest and shoulders.
Collar skin ownership is transferred from each body type's actual neck surface:
the nape follows the head, while the lower garment blends into the torso.

The skin continuation under an equipped collar now tucks inward toward the neck
axis. It previously expanded and extended backward, exposing a skin flap after
a collar was made smaller. Its original joining edge, UVs and skin ownership
remain intact. All 64 torso icons were rendered again at 512 pixels with alpha.

The collar revisions supersede the Scout/Recruit torso entries in
[the first review receipt](review-fixes.md). That earlier receipt and its model
hashes describe the preceding stage. Item names, descriptions, stats and IDs
remain as recorded by the equipment previewer catalog.

## Verification

- Every revised GLB independently compared with retained original bytes:
  topology, UVs, materials, image references, rig nodes and inverse bind matrices
  are preserved. Geometry outside the collar region has exactly zero
  displacement. There are no newly collapsed faces. Maximum skin weight sum
  error is 0.003922, within the source's normalized 8-bit weight precision.
- All 128 GLBs freshly imported into Blender from a bundle containing only
  those files and their declared image dependencies. Seven representative
  torso components rendered and inspected.
- All 128 front views inspected in the actual Godot previewer, plus 122
  movement/race views covering walk, jog, combat idle, head nodding, side and
  rear views. Representative collars checked on all eight races and both body
  types. These samples do not constitute exhaustive animation or outfit
  combination coverage.
- 4,830 neck continuation checks pass, including exact visible join attributes,
  inward placement, skin changes and removal on unequip across the body models.
  The test separately checks the retained native source and the displayed body
  after modular head cutting and cosmetic body refinement.
- 298 existing review-fit checks and 13,354 quiver checks pass with the combined
  changes. Six catalog/icon tests and the graphical previewer self-test pass.
- Final runtime logs contain no script/resource/import errors. The existing
  optional head-normal-texture fallback and shutdown cache warning remain.

Originals, candidates, screenshots, logs and dependency bundles stay in ignored
local authoring storage. The companion `collar-fit.json` records source/result
hashes and measurements. These are implemented changes for review, not a record
of artistic approval or a release.

## Reproduce

From a client task worktree with Python, NumPy and trimesh:

```powershell
python eloria-assets/tools/fit_equipment_collars.py --stage .local/asset-authoring/working/collar-fit --source-ref 10718e3a
```

The stage retains the originals. Review its `revised` GLBs before adding
`--install`; installation rejects unrelated intervening edits. The body's
current neck surface supplies the skin transfer, and its hash is recorded.
`--audit-only` writes measurements to `audit.json` without replacing candidates.
After installation, independently compare the installed files and originals:

```powershell
python eloria-assets/tools/fit_equipment_collars.py --stage .local/asset-authoring/working/collar-fit --validate
```

Regenerate torso icons with the previewer's `render_icons.gd`, selecting keys
`5:184` through `5:247`. This workflow does not publish or release assets.
