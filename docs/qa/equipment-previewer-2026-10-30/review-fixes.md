# First equipment review corrections

These revisions are implemented for visual review. They are not a record of
artistic approval or a release. Saved reviewer comments, screenshots, original
assets and intermediate candidates remain in ignored local authoring storage.
The product's item IDs, stats, equipment mappings and starting inventory are
unchanged.

The later [complete torso collar audit](collar-fit.md) supersedes this stage's
Scout/Recruit torso collar fits and their corresponding model/icon hashes.
The [second equipment review](second-review.md) records later headwear, arm,
clothing and bow-grip revisions and supersedes their overlapping file hashes.

| Equipment | Revision |
| --- | --- |
| All boot icons | Render the neutral fitted pair with parallel toe directions, rather than a living idle stance that bends one ankle. |
| Scout and Recruit armor | Fit the collars to the neck and remove inappropriate clavicle ownership from their upper rims. |
| Quivers | Measure the roof of the worn shoulder as well as its front surface; lift the shoulder band with bounded clearance. Keep the case outside that band unchanged. |
| Longbow and Recurve Bow | Carry the relaxed bow upright beside the wearer. Preserve the existing draw/release presentation. |
| Acolyte Hood | Lower the front cowl below the mouth and taper its lower skirt toward the torso collar; retain the crown and ornaments. |
| Leaf Cape | Advance the shared cloth solver at a fixed cadence, interpolate root travel between those steps, and retain the solved pose on intervening display frames. This prevents idle oscillation and returning to the authored hang above 60 Hz. |
| Recruit Hood | Use adjacent fabric color to repair isolated dark paint artifacts in the client cloth material. The source texture and UVs are retained. |
| Short sleeves | Split the existing anatomical lining into cloth and exposed skin. Correct forearm ownership at the elbow and follow the wearer's selected skin color. Applies to Footman, Soldier and Cavalry armor, and Homespun, Patchwork and Ragged shirts. |
| Footman Boots | Open both shafts over the fitted trousers without changing the ankle or toe. |
| Mercenary Armor | Mirror the clean lower garment, including its geometry, texture coordinates and matching skin ownership. |
| Sergeant Armor | Center and extend the visible cuffs toward the wrists. |
| Knight and Cavalier Boots | Shorten the upper shafts by 60 and 80 mm respectively, leaving the feet intact. |
| Knight Helmet | Lower the visor/brow opening to the eyes. |
| Cavalier Leggings | Refit the existing front badge as a hanging plate, remove flattened repair scraps and match the lining to the blue cloth. |
| Paladin Leggings | Mirror the right upper-leg armor onto the left, including the hanging front plates, their texture and skin ownership. Lower legs remain unchanged. |

The mixed Ranger Starter Kit still uses the Rogue Hood. The existing Scout Cap
is the recommended alternative: its brown leather and open face match the Scout
armor. A local comparison is available; this recommendation does not change the
class's actual starting equipment.

## Validation

- 78 revised native GLBs across 18 visual keys; original rig nodes, rest
  transforms and inverse binds retained. Mesh arrays, triangle indices and
  normalized skin weights are checked during authoring.
- All 78 outputs rebuilt from the preceding client revision with identical
  file hashes, independently of the original local stage.
- All 78 outputs imported in fresh Blender scenes from an isolated dependency
  bundle; seven representative component renders reviewed. Client-only cloth
  paint repair is verified in Godot.
- All 20 saved review views replayed, plus 50 movement views covering walking,
  jogging and combat idle on both body types and a travelling cape.
- 298 focused runtime checks across eight races and both body types, including
  skin selection, bow action transitions, idle settling, pose retention between
  steps and moving-cape consistency under mixed display timing.
- The static idle cadence comparison is exact; moving-cape particle positions
  differ by less than 5 micrometers between the two tested display cadences.
  The mounted-cape integration also passes its 47 checks.
- 13,306 quiver integration checks across eight quivers on male and female
  Luminous actors. The test inspects the retained strap-fit input before the
  existing actor body-proportion pass, while also checking the displayed mesh
  for finite geometry and deterministic outfit changes.
- Six catalog/icon checks, wardrobe navigation checks and the graphical
  previewer self-test, including swaps, visibility and comment saving.

The existing optional head-normal-texture fallback and shutdown cache warnings
remain. Final replay and graphical test logs contain no script/resource/import
errors. Tests and screenshots demonstrate implementation behavior; final visual
acceptance remains with the reviewer.

`review-fixes.json` binds this receipt to the exact model and source hashes.

## Reproduce the native repairs

Run from a client task worktree with Python, NumPy and trimesh. Start from the
preceding equipment-preview revision, or supply it as `--source-ref`. The stage
retains original bytes; later runs use those originals. Installation rejects
active files whose hashes show unrelated intervening edits.

```powershell
python eloria-assets/tools/refine_equipment_review.py --stage .local/asset-authoring/working/equipment-review-fixes --source-ref 0f16c298
```

Inspect the stage's `revised` models and `manifest.json`. Adding `--install`
copies those candidates into the task checkout. This does not publish or release
them. Regenerate affected preview icons afterward using `render_icons.gd`.
