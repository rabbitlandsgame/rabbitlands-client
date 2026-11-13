# Imported carrying packs

Small Pack and Large Pack are newly generated Meshy equipment occupying cape
part 2, visuals 151 and 152. Both use ordinary named player skin bindings. The
bag stays rigid on `spine_03`; existing shoulder-loop vertices inherit the
wearer's torso weights. They do not use cape cloth simulation or cape draping.
The renderer fits the chest straps over worn armor. A worn quiver moves beside
the pack while its chest strap stays on the torso.

The server defines the Small Pack at 1,000 gold with +200 EMU capacity and the
Large Pack at 10,000 gold with +500 EMU. Mara Vell sells both. Capacity applies
only while equipped; the ordinary cloak conflict prevents stacking packs or
wearing a perk cape with one. Removing a loaded pack does not delete holdings.

`catalog.json` contains measured source frames and fit parameters. `sources.json`
pins the original-provider and portable-source hashes. These compact sources
retain the imported mesh, UVs, indices and painted base color. No procedural
model builder, provider rigging or additional paid retry was used. Original
concepts, exact prompts, provider downloads, task receipts, rejected fit stages
and full-resolution paintings remain in ignored local authoring storage.

Rebuild all sixteen body variants in a fresh ignored directory:

```powershell
python eloria-assets/tools/fit_packs.py --out .local/asset-authoring/working/packs-new --install
```

The tool preserves existing source triangles and UVs, reshapes the shoulder
loops, recomputes normals and binds the mesh to each body's current rest pose.
The `packs` fit profile prevents an additional legacy stature correction.
Runtime texture bytes are shared across the body variants.

Checks:

```powershell
godot --headless --path godot-client --script res://tests/integration/pack_equipment_fit.gd
python eloria-assets/tools/build_item_icon_atlases.py --check
```

The engine probe exercises all 32 fits, five armor transitions, named bindings,
idle/walk/run/ranged/melee poses, repeated outfit restoration and switching back
to an ordinary cape. IDs 634 and 635 are new painted icons; the existing direct
custom icon at 633 remains unchanged. Prior paintings remain unchanged.

Technical and fresh-import visual checks do not imply owner visual approval.
