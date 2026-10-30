# Wrist, chest and under-helmet fit review

The later [bow idle reference](bow-idle-reference.md) updates the resting bow
orientation. Its runtime/test hashes supersede this review; the native model
hashes below remain current.

The bow carry correction from the second review forced the hand into a world
orientation at the wrist. That bent it sideways out of long cuffs. The client
now retains the animated wrist rotation, centers the handle between the palm
and curled fingers, and gives the bow an outward cant. A small shoulder spread
provides clearance at ease. Draw, hold and release keep their aiming behavior.

The Phoenix breastplate's central front has been pulled closer to the wearer.
Its chest section's 98th-percentile forward extent is now 0.145 m, down from
0.200174 m on the male mesh and 0.187915 m on the female mesh. The waist,
shoulders, sleeves and collar opening retain their fit. The same section audit
covered all 64 torso designs on both Human bodies; 63 native files across 41
designs received a proportional front-depth correction.

Phoenix's separate under-helmet neck shell was removed. The helmet's main
shell, face opening and feathered nape remain. All 30 metal helmet designs on
both Human heads were checked for the same detached neck shell; 24 files across
13 designs received this correction. Only disconnected components contained
entirely in the small neck volume below the face opening are removed. The
existing broader shoulder skirts remain. Other races' headwear geometry is
unchanged.

## Verification

- All 87 final native outputs independently compare against retained originals:
  skeleton nodes, rest transforms, inverse binds, skin weights, UVs, materials,
  animation and image bytes/references are preserved. Torso topology is unchanged;
  helmet topology differs only by removing 3,767 neck-shell triangles in total.
  No new collapsed faces; maximum skin weight sum error 0.003922.
- All 87 exact final GLBs imported into fresh Blender scenes from an isolated
  bundle of only their declared model/image dependencies. Four components were
  rendered. Actual equipped appearance is additionally reviewed in Godot.
- Rendered review covers all 64 torso designs on both Human bodies (128 side
  views), 78 front/side/rear helmet views, 16 focused Scout/Phoenix views, and
  120 race/movement views. These include idle, walking, running, combat idle,
  nodding and the actual bow draw/hold/release clips.
- Wrist regression: 2,321 checks on all 16 body variants and both current bow
  designs, across three sample times and repeated action changes. Maximum
  quaternion angle comparison is 0.000976563 rad (floating-point precision);
  maximum wrist-to-grip distance is 0.095775 m, below the 0.11 m limit.
- Existing equipment review-fit (298 checks), second-review regressions (21),
  weapon-carry tests, catalog/icon tests (6 tests and 1,315 subtests), and the
  graphical previewer self-test pass. The older upright-bow assertion now allows
  the natural forearm cant; the new regression separately protects wrist anatomy.
- Affected preview icons were rendered again at 512 pixels with transparency.
  The complete icon manifest retains all 443 records without failures.
- Final client logs have no script/resource/import errors. The existing optional
  head-normal fallback, transparent-viewport SSS fallback, and shutdown cache
  warning remain.

These are fit corrections and sampled visual checks, not an exhaustive proof
for every mixed outfit, appearance slider or animation frame. Existing painted
skin/cloth texture seams can still be visible in close-ups; the source atlases
and UVs are preserved. User artistic approval is still pending. No item IDs,
stats, catalog mappings or shared animation clips change.

This record and `third-review.json` supersede overlapping final file hashes in
the earlier reviews. Originals, both attached reference images, rejected trials,
comments, renders and logs remain in ignored authoring storage. The machine
receipt binds the final native and implementation versions to their hashes.

## Reproduce

Use a task worktree and a fresh ignored stage. The preceding source revision is
`f809b150`; do not refit already revised meshes as new originals.

```powershell
python eloria-assets/tools/refine_equipment_review_third.py --stage .local/asset-authoring/working/equipment-third-review --source-ref f809b150
```

Inspect candidates before adding `--install`, then compare installed exports:

```powershell
python eloria-assets/tools/refine_equipment_review_third.py --stage .local/asset-authoring/working/equipment-third-review --validate
```

The tool retains source bytes and rejects unrelated intervening edits. It edits
current imported models only. No retired generator, paid generation, upload,
push or release is part of this review.
