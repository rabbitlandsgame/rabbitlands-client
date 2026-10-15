# Original-source leg, foot and head fitting

> Historical report for the previous body generation. The 16 current bodies
> now share the canonical Rest_Pose and split wardrobe surfaces; references
> below to 14 fused bodies and older fit measurements are obsolete. See
> [the canonical-body equipment refit](canonical-equipment-refit.md) for the
> current authoring, runtime units and validation.

The 64 leg pieces, 72 foot pieces and 64 head pieces now enter
`limb_head_remap.build` from `conform_equipment.build`. They read their original
`.glb.orig` exports. The previous seat/correction chain is bypassed for these
slots. The 64 previously fitted torsos, including their raised collars, are
byte-identical to the starting checkout. Item definitions and balanced stats
are unchanged; every shipped rebuild used `--meshes-only`.

Legwear starts with one uniform waist-to-hem scale, then maps each trouser tube
to its own shin axis. The hip transition joins those tubes to the pelvis.
Short welded ornaments move together, and coincident UV vertices receive the
same transform. Boots use each foot's heel-to-toe length and sole independently.
Their original proportions determine shaft height, instead of compressing
every design into the old 333 mm height. Soles sit approximately 4 mm below the
wearer's sole. The legendary leg harness and its matching sabatons are both
reconstructed from the same original parent and split at Y=0.320 m, so their
ornament and geometry line up when worn together.

Headwear uses inner enclosure rays, excluding the intentional face opening,
to locate the cranium inside the original geometry. One uniform transform
preserves the crest, brim, cheekguards and UVs. When a frontal opening is
detected, the fit constrains its brow to the wearer's brow while clearing the
skull. Simply raising an already fitted helmet caused the back of the head to
intersect a narrower section of the cap; the joint fit avoids that. Circlets
and headbands fit their band around the upper head. Closed headwear declares
`coversHair` in glTF mesh extras; the runtime hides the chosen hairstyle and scalp cap while
it is worn and restores it for circlets or unequip. Eyes and faces remain intact.

Legwear and boots supply closed linings with the body's original skin weights.
The lining follows cross-sections inside the original artwork. Named
`GeneratedLegBacking` and `GeneratedBootBacking` meshes declare their
`bodyCover` regions in glTF extras. The runtime combines active regions, copies
only the body's index buffers, and restores the exact original mesh on unequip.
This also works for the 14 races whose default clothes are painted into their
body atlas. UVs, positions, weights and material assignments remain intact.

A standalone garment needs a transition to the default pants. When generated
legs and boots are both equipped, the runtime instead selects
`GeneratedLegBackingWithBoots` and `GeneratedBootBackingWithLegs`. These omit
the bulky default-pants transition that otherwise protrudes behind the calf.
Exactly one lining per slot is visible. The Blender comparison renderer uses
the same selection and body-mask rules; opening a raw GLB in another viewer
does not automatically apply those Eloria-specific visibility rules.

Original embedded JPEG bytes, UVs and double-sided materials are preserved.
A sparse atlas sample also exposed an empty percentile-selection case in the
shared lining-colour helper; its fallback now selects an actual dark sample
instead of writing NaN into a GLB material. The existing torso colours are
unchanged. The 200 output GLBs total approximately 777 MB because they retain
the original textures. Runtime population-scale performance and LODs were not
benchmarked in this fitting pass.

## Independent measurements

`generated-limb-head-remap.json` includes the per-piece fit passes, asset hashes
and fixed-grid coverage results. The raster uses projected triangle
barycentrics, independently of the fitter's enclosure rays. The original,
unmasked body remains the absolute depth reference in both versions.

| Slot | Pieces | Original proud cells | Rebuilt proud cells | Change | Surviving body cells in covered region |
| --- | ---: | ---: | ---: | ---: | ---: |
| Head | 64 | 99,124 | 116,530 | +17.56% | Not a masked region |
| Legs | 64 | 226,502 | 210,998 | -6.84% | 0 |
| Feet | 72 | 108,695 | 186,970 | +72.01% | 0 |

The leg proud-cell count decreases because the original designs are narrower
than the old oversized legwear and loose default pants. The fitted replacement
lining permits that silhouette without revealing the default body through it.
This decrease is reported explicitly rather than changing the reference body
or dropping hidden cells from the denominator. Every one of the 136 leg/foot
pieces has zero surviving body cells in its declared region on this grid.

These measurements cover the luminous-male front rest view. They do not prove
coverage from every angle, in every animation, or on every race. Side and bent
complete-set renders separately check the visible joins. Open faces, hands,
and hair under circlets are intentional.

## Validation

- The captured torso/equipment suite has **no new failure identifiers**:
  17 before, 16 after. The existing closed-leg-tubes failure is resolved.
  The remaining identifiers are recorded in `generated-limb-head-test-baseline.txt`.
- All 17 focused source-fitting tests pass, including original-source dispatch,
  preserved JPEG bytes, uniform boot/head transforms, UV seams, welded cuff
  boundaries, both lining variants and sparse atlas sampling.
- Godot integration exercises all 16 races, 528 equipment transitions and
  8,264 assertions with zero failures. It checks mixed slot removal orders,
  exact body restoration, the selected lining variant, hairstyle restoration
  and untouched eyes. The existing torso integration test also passes.
- All 200 GLBs pass strict JSON, finite-accessor, index, normalized-weight and
  closed positive-volume lining checks. All 200 have changed BIN chunks;
  there are no material-name-only rewrites to include.
- Hash checks confirm that original inputs, torso GLBs and item definitions
  were not modified.

## Rendered comparisons

The local `qa/limb-head-remap/sets/index.html` gallery contains 72 outfit pairs:
all 64 matched sets plus eight alternative legendary boot combinations.
Each pair shows the assembled armour and the complete set on luminous male.
Both views have a packed, editable `.blend` scene beside the PNG. The
armour-only view is normalized for detail; the worn view keeps character scale.

The gallery pairs the same concept-sheet cell across each family. The main
legendary outfits use the derived sabatons that match the original leg harness.
The alternate versions show the independently drawn legendary boots.

Nine individual pieces also have normalized original/fitted and true-scale
worn sheets: the Phoenix, Mossfringe and Leafscale head/leg/foot examples.
The Phoenix leg comparison shows its separate wearable leg slot beside the
original full harness, including the feet; the complete set restores those
feet with the matching sabatons. Side and bent-pose checks cover those three
sets and the Palesteel set with its open circlet.

Reproduce the complete gallery from `eloria-client`:

```powershell
python eloria-assets/tools/render_generated_armour_sets.py --alternate-boots --save-blend --out qa/limb-head-remap/sets
```

Use `--set legendary_01` to render one outfit, `--yaw 90` for a side view, or
`--pose bent --yaw 45` to check articulation. `--resume` resumes a render batch
whose source files and render options have not changed. Rebuild an individual
sheet with `import_generated_equipment.py --meshes-only --sheet <sheet>`.

Since the race programme's P7 cleanup (2026-10) the old-male base scenes
`equipment/<slug>.glb` are deleted: each piece ships as its Human fit
(`variants/human_male|human_female/<slug>.glb`, refit with
`refit_human_bodies.py` and installed with `install_human_equipment.py`), and
the renderer and `audit_limb_head_remap.py` default to the Human male fits.
The importer no longer rebuilds an installed piece in place; rebuild a sheet
into scratch with `import_generated_equipment.py --meshes-only --sheet <sheet>
--build-dir <scratch>` and pass that folder as `--equipment` (renderer) or
`--directory` (audit).

Representative images and family contact sheets are committed in
`generated-armour-comparisons/`; the full PNG/Blender gallery remains in the
local QA directory and can be regenerated with the command above.
