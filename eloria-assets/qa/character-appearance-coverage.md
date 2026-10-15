# Shirt coverage and fitted hairstyles

**Status (2026-10).** This page records the September 8 repair of the shared
canonical bodies, which are retired. The Human bodies were regenerated on
2026-10-05 (`pack_human_body.py`, their own shirt and collar) and the fourteen
race bodies rebuilt on them by `rebase_race_body.py`. Hair now has nine styles
per body: Human fits come from `fit_human_hair.py`, race fits from
`fit_character_appearance.py --race <slug>` (with its `tuck_ears` pass and
`--install`); horns, crowns and crystals live on `race_feature_*` nodes and
show through hair. The retired refits `expand_hairstyles.py` and
`install_high_resolution_race_heads.py` refuse to run, and
`restore_buzzcuts.py` is deleted, so none of them can overwrite these fits.
The `--model` reproduction below rebuilds the September candidates from their
archived inputs only.

The September 8 repair updates all sixteen shared canonical bodies and adds
three fitted hairstyles per body under `assets/actors/native/hair/fitted/`.
Appearance style 0 is bald, including after changing styles or removing a helmet.
Styles 1–3 retain the parted, long and buns designs and existing colour mapping.

The shirt had two separate problems: faceted normals separated coincident
vertices when material grow was applied, and the source collar left openings
over the reconstructed neck. `tools/fit_character_appearance.py` bakes a common
11 mm displacement at coincident shirt vertices, reconciles their skin weights,
refits the collar, patches small internal holes, and adds a narrow cloth facing
below the neckline. The front opening, cuffs and hem remain. The model's
`wardrobeBakedGrow` list prevents a second runtime displacement.

Each hairstyle is fitted to the actual retained skull, using the style's own
crown height, one subdivision of the source faces and a 10 mm radial clearance.
UVs interpolate from the authored design. The fitted assets carry the unchanged
canonical skeleton and bind poses, with weights interpolated from the head.
`hairSkinned` selects direct binding to the actor skeleton. This is necessary
because the skull includes neck/head weight blending; a rigid Head attachment
separated from the occiput during animation even after a correct rest fit.
Retained horns and crystals can still protrude through hair.

Before installation, every non-shirt position, normal, UV, index and weight
array was compared exactly with its input, as were node transforms, inverse
binds and existing texture payloads. Those checks passed for all sixteen bodies.
The existing exact head/neck seam check remains in place. Its lower boundary
used to coincide with the original shirt, so the fitted garment now has a
separate ray-based coverage check. Shared trunk and sleeve comparisons exclude
the small collar fitting area; the head sources remain distinct.

Validation on the installed assets:

- 11 focused Python tests and 1,666 subtests passed, including 220 back-coverage
  rays per body, crown coverage for all 48 fitted hairstyles, canonical binds,
  head joins and shared body geometry outside the collar fit.
- `tests/integration/character_appearance_fit.gd`: 16 variants, 1,105 checks,
  zero failures. Actual Godot renders include all four styles from front/back,
  walking and running, plus bald/style and helmet transitions.
- `tests/integration/armour_body_cover.gd`: 16 races, 528 transitions,
  zero failures, including exact equipment removal and restoration.
- The character-creation integration check passed in structure-only mode,
  including all races, hairstyle 0 and the existing wardrobe dye controls.

Inputs, candidate reports and installed Godot captures are in the workspace's
`work-output/character-coverage/` directory. The `original/` snapshot contains
the input bodies and model registry; use those inputs when rebuilding, because
the fitter rejects already fitted bodies. For one body, run from the client root:

```powershell
python eloria-assets/tools/fit_character_appearance.py --model ../work-output/character-coverage/original/luminous_male.glb --models ../work-output/character-coverage/original/models.json --hair-root godot-client/assets/actors/native/hair --out ../work-output/character-coverage/rebuild
```

The tool writes candidates and a config fragment for `tests/tpose_body_preview.gd`
(`--config`, `--model`, `--style`, `--angle back`). Review before copying assets
and applying the config fragment to the registry. Update catalogue hashes and
counts when installing. Runtime fits use resource paths, not scratch paths.
Godot caches meshes during a session; restart an already running client to load
the replacements.
