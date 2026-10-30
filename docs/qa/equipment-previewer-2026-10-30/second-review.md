# Second equipment review

The later [wrist, chest and under-helmet review](third-review.md) corrects the
bow wrist alignment and supersedes overlapping native file hashes below.

The 22 new saved comments are addressed in the equipment previewer. All 64
headwear designs were reviewed on the male and female Human heads. Sixty designs
have smaller, lower native fits (120 files); the four open pieces retain their
existing calibrated RL-head fits. Tidecaller's veil also has a repaired back.

Other races retain their existing native headwear geometry, including cleared
ear, crown and horn openings. The Human size reduction failed those clearance
checks when applied to other races; that candidate was withdrawn. The retained
fits pass all 1,968 race-clearance subtests. Antler's palette correction applies
to every body variant.

| Component | Revision |
| --- | --- |
| Human helmets, caps and hats | Size against the actual bald skull instead of the envelope of every hairstyle; reduce crown height and lower the seat, retaining face clearance. |
| Runic, Hunter, Rogue and Tracker hoods, and other cloth hoods | Extend and taper the lower skirt into the torso collar while clearing the exposed neck above it. |
| Acolyte Hood | Gather the uneven lower flare into the collar. |
| Crystalward Helmet | Lower the neck guard separately from the face opening. |
| Tidecaller Veil | Exclude undrawn vertices from the drape envelope, shorten the draped panels, and back the missing cloth over the actual skull with the veil's own fabric. |
| Antler Hood | Change olive dye to brown leather while preserving neutral fur, antlers and gold details. Original atlas bytes remain unchanged; the client applies the palette. |
| Ranger Starter Kit | Use the matching Scout Cap in the preview outfit. The game's class starting inventory is unchanged. |
| Carried bows | Move the hand and bow together, with a small shoulder spread for body clearance. Preserve the existing draw/hold/release presentation. |
| Exposed arms | Shape the existing forearm lining around the elbow and wrist, remove its duplicate hand faces, and share the hands' textured, calibrated skin material. Applies to Footman, Soldier, Homespun, Patchwork, Ragged and Cavalry torsos. |
| Recruit Leggings | Inset and lower the waistband beneath the torso hem. |
| Acolyte Leggings | Trim the cloth foot-wrap inside the boot shaft, retain a continuous shin lining, and match that lining to the pale cloth. |
| Guard Armor | Seat the collar root and give coincident UV seams matching skin ownership so they move together. |
| Herbalist Tunic | Narrow the upper body and reduce its depth. |
| Amber and Starglass armor | Pull the central breast ornament back toward the shell. |
| Silver Ward Armor | Tighten the front and back of the collar. |
| Preview icons | Frame actual drawn triangles, including narrow ornaments. Unused GLB vertices no longer enlarge the bounds. Render all 443 icons again at 512 pixels with transparency. |

## Verification

- Independent comparisons cover all 160 final revised native files. Rig nodes,
  rest transforms, inverse binds and image payloads/references are preserved.
  Headwear and torso-shell topology, and non-arm UVs, are retained. The explicit
  exceptions are the forearm skin UVs and duplicate hand trim, the Acolyte
  foot-wrap trim, and the Acolyte lining color. No new collapsed faces;
  maximum skin weight sum error 0.003922, within normalized 8-bit precision.
- All 160 exact final versions imported into clean Blender scenes from an
  isolated bundle of only the declared models and images. Nine components
  rendered and inspected. Client palette, veil backing and shared skin materials
  are additionally checked in Godot, where they are applied.
- 128 Human headwear views, 22 saved comment views, additional hood/helmet
  side/rear views, and 158 race/movement views reviewed in the actual client.
  Movement coverage includes walking, jogging, combat idle and head nodding.
- The neck-continuation suite (4,830 checks), existing review-fit suite (298),
  second-review regressions (21), weapon-carry suite, race-clearance suite
  (4 tests plus 1,968 subtests), quiver integration (13,354 checks), catalog/icon
  checks (6), and graphical previewer self-test pass.
- The weapon-carry test now uses the current Longbow visual 164, replacing its
  retired visual 64. Headless bow checks explicitly advance the production
  skeleton modifier before inspecting its wrist-owned grip.
- Final client logs have no script/resource/import errors. The existing
  optional head-normal fallback and shutdown cache warning remain.

Default proportions and selected motion samples were checked; arbitrary mixed
outfits, extreme appearance controls and every animation frame are not exhaustive
coverage. These changes are ready for review, not a record of artistic approval
or a release. This receipt supersedes overlapping file hashes in the earlier
[review corrections](review-fixes.md) and [collar audit](collar-fit.md).

Source originals, rejected candidates, comments, screenshots and logs remain in
ignored authoring storage. `second-review.json` records exact source/result and
implementation hashes. No item IDs, stats or equipment catalog mappings change.

## Reproduce the native edits

Use Python with NumPy, SciPy, Pillow and trimesh in a client task worktree. A
fresh stage can read the preceding revision's original GLBs:

```powershell
python eloria-assets/tools/refine_equipment_review_second.py --stage .local/asset-authoring/working/second-equipment-review --source-ref 56c59723
```

Review the candidates before adding `--install`. Reuse that stage for later
iterations so an already fitted model is not fitted twice. `--keys` and
`--bodies` scope a trial. Installation rejects unrelated intervening edits and
retains the race fits described above. Independently compare installed files:

```powershell
python eloria-assets/tools/refine_equipment_review_second.py --stage .local/asset-authoring/working/second-equipment-review --validate
```

The previewer's `render_icons.gd` rebuilds the component icons. F5 also reloads
the headwear-fit data and its derived caches. These commands do not publish or
release assets.
