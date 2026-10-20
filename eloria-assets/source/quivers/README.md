# Imported quiver sources

These are compact, portable sources for the eight user-selected Meshy designs.
`sources.json` records original and compact source hashes. Provider receipts,
original downloads and processing stages remain in ignored local authoring data.

`catalog.json` records measured case axes and the strap side for each design.
The Skirmisher's broad case needs a later strap boundary than the narrow cases.
Its `caseScale` of 0.8 makes the case and seated arrows 20% smaller; the shoulder
strap is fitted to the wearer at that size rather than scaling away from the body.
The fitting tool reshapes existing strap vertices; it creates no replacement
geometry. Base-color UVs and triangle indices are preserved. Cases and seated
arrows are rigid on `spine_03`; straps inherit the current body's torso weights.

Build and install into a **new** stage using current public sources:

```powershell
python eloria-assets/tools/fit_quivers.py `
  --out .local/asset-authoring/working/quivers-fit-new --install
```

`--races` and `--pieces` support isolated fitting studies. Installation requires
all sixteen body fits for each selected design. Use `--pieces rl-quiver-skirmisher`
with `--install` to update only that quiver. `--prepare` is only for deliberately
compacting new original downloads; it is unnecessary for a normal rebuild.

Runtime visuals are part **8**, IDs **1–8**, in catalog order. Image IDs are
**599–606**. The registry uses the `quivers` fit profile because these variants
already fit current body rest space. Do not apply legacy stature scaling again.
Textures are shared by content hash across all body variants.

Validation:

```powershell
godot --headless --path godot-client `
  --script res://tests/integration/quiver_equipment_fit.gd
python eloria-assets/tools/build_item_icon_atlases.py --check
```

The engine probe checks every variant, named skin bindings, independent equipment
parts and idle/walk/ranged animation poses. Set `RL_QUIVER_REVIEW_DIR` to an ignored
absolute output directory and run with a graphics display to capture front/back
pose evidence. Icon cells live in the public `item-icons/quivers-2026-10-20`
supplement; rebuilding atlases preserves the existing approved image IDs 0–598.
