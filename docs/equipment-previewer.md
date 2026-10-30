# Equipment previewer

Double-click `godot-client/preview-equipment.bat` (or the existing
`review-equipment.bat`). It uses Godot 4.7.2 beside the client, or `GODOT_EXE`.
The previewer uses the game's actor, fitted equipment, animations and icon atlas.
It runs locally without logging into a server.

Choose a set from the top dropdown, or press **Left / Right** to move between
sets. All pieces in the chosen set are shown initially. Each slot has a checkbox
to hide/show its selected piece and a dropdown offering every registered piece
for that slot. Selecting a replacement changes that slot alone. Click the slot
name to inspect it without changing it. Its game name, icon, description, stats
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
