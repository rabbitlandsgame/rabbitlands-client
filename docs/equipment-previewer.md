# Equipment previewer

Double-click `godot-client/preview-equipment.bat` (or the existing
`review-equipment.bat`). It uses Godot 4.7.2 beside the client, or `GODOT_EXE`.
The previewer uses the game's actor, fitted equipment and animations, with
512 × 512 transparent component renders for its detail icons.
It runs locally without logging into a server.

Choose a set from the top dropdown, or press **Left / Right** to move between
sets. All pieces in the chosen set are shown initially. Each slot has a checkbox
to hide/show its selected piece and a dropdown offering every registered piece
for that slot. Selecting a replacement changes that slot alone. Click the slot
name to inspect it without changing it. Its preview name, icon, description, stats
and effects appear on the right, including when the piece is hidden.
Press **Up / Down** to cycle this inspection through the currently equipped
pieces in slot order. Empty slots are skipped; selection wraps at either end.
Hidden pieces remain equipped and can still be inspected.

Edits stay with each set while the previewer is open. **Restore set** restores
the original pieces and visibility. All eight legendary outfits use their Boots
variants. Their Sabatons are temporarily hidden from the slot lists; older saved
notes can still replay those original appearances. Spare weapons, off-hand
weapons, capes and quivers are available in the slot lists.
Registry visuals without an equippable item definition are marked **visual only**;
their game stats are explicitly unavailable.

- **T:** comment on the selected piece, identified by item ID and visual key.
- **S:** comment on the full set, including replacements and hidden pieces.
- **Ctrl+Enter:** save a comment. **Esc:** cancel it.
- **F2 / C:** screenshot and general view comment.
- Drag to orbit; right/middle drag to pan; wheel or Q/E to zoom.
- A/D rotates the camera; Page Up/Down tilts it; 1–5 chooses standard views.
- Space pauses; comma/period steps; V toggles travel; F5 reloads assets.

Comments persist in the checkout's ignored
`.local/asset-authoring/working/equipment-review/<session>/` directory. **Open
saved comments** opens it. `notes.md` is readable; `notes.jsonl` retains item
identity, complete loadout (including disabled pieces), character, animation,
camera and screenshot for replay. New sessions retain earlier session folders.
The right panel shows comments from the current session. Comments are local and
are never sent or committed automatically.

To replay a saved review with its exact mixed outfit:

```powershell
godot-client/review-equipment.bat --replay "C:/path/to/notes.jsonl"
```

The preview's item facts are an offline snapshot of the authored server catalog.
After changing game definitions, refresh and check them from a client task checkout:

```powershell
python godot-client/tools/equipment_review/export_catalog.py --server C:/rabbitlands/rabbitlands-server
python godot-client/tools/equipment_review/export_catalog.py --server C:/rabbitlands/rabbitlands-server --check
```

The exporter reads item definitions and their visual mappings only. Client
models absent from the registry are excluded; previewing does not alter gameplay
equipment, item balance or model files. Custom candidate model registries still
work with `--equipment C:/path/to/equipment.json`.

Preview names use the approved 64 set identities and simple component types,
such as Guard Helmet, Guard Armor, Guard Leggings and Guard Boots. Descriptions
explain the component and the visual character of its set. Shared weapons,
shields, capes and quivers have independent names so mixing outfits does not
relabel the same accessory. `gear_presentation.py` owns this authored text;
the export keeps the original item IDs, visual keys and stats. Legacy outfit
names remain internal replay identifiers, while the dropdown and new comments
use the new labels. The mixed Ranger Starter Kit remains a separate outfit.

The detail icons depict the actual registered gear, fitted to the client actor
and captured in a fixed idle pose. Boots use the canonical bind pose with
parallel toe directions, preserving the ankle angle through the whole leg.
Actor skin, hair, generated fitting liners,
floor and background are excluded. The two animated bows use their registered
rigid source scenes. Each transparent 512-pixel PNG is keyed by part and visual
ID, including color capes and historical Sabatons for old note replay. The
classic gameplay inventory atlases remain separate.

Rebuild these icons with a graphics-capable Godot process:

```powershell
godot --path godot-client --script res://tools/equipment_review/render_icons.gd -- --out C:/path/to/icons
```

`--keys 5:209,6:249` scopes a repair. The render manifest records source scenes,
hashes and capture settings. `tests/test_equipment_review_presentation.py`
checks full coverage, unique names, preserved game facts, 512-pixel resolution,
transparent image borders and unclipped content. See the preview icon audit in
`docs/qa/equipment-previewer-2026-10-30/icon-audit.json` for the original painted
background-removal findings and replacement validation.

The first equipment review corrections are documented in
[review-fixes.md](qa/equipment-previewer-2026-10-30/review-fixes.md).
They include native garment repairs and shared actor fitting/cloth corrections,
so the revised equipment behaves the same in the client and the previewer.
The Ranger Starter Kit's headwear remains unchanged pending review of the
existing Scout Cap alternative.
