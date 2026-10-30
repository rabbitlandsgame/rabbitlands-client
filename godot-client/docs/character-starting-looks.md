# Character starting looks

Creating a character opens the starting-look library before the full editor. Search, race, sex and hair filters work together. Selecting a card previews the body and appearance; only **Use this basis** changes the editor. Cancelling the first window returns to login. The **Choose starting look** button at the top of the editor opens the library again; cancelling that window preserves all current edits and the camera. Changing a basis preserves the character name, password fields and calling.

The library currently contains 22 choices: both sexes for all eight playable races, the established Mira/Rowan/Tavi studies and the three integrated Human pilot bases. Human choices appear first. Ssarathi is the public race label; Lizardfolk remains a search alias. Hairstyle descriptions stay searchable alongside names. A basis name does not fill the player's character-name field.

Human names are Lyra and Alden for the general bases; Mira, Rowan and Tavi retain their established names. The fitted pilot names are Amara (01), Corin (08), Nessa (14), Darian (20), Elowen (27) and Bram (34). Corin, Nessa and Elowen remain in fit review and appear automatically when their bases are integrated; naming them does not register their assets.

`src/ui/creation_base_library.gd` derives available bodies from `data/actors/models.json.creationOptions` and the Human bases from `data/actors/rl_head_archetypes.json`. Protocol 3 receives the full appearance, protocol 2 its saved fallback and older protocols only the seven legacy cosmetic fields. Stable internal IDs, appearance values and calling inventory remain unchanged. High-detail hair follows the normal client quality rules.

`creation_base_flow.gd` stages a temporary preview separately from the editor. `creation_base_picker.gd` owns the modal controls and requests only visible portraits from the existing single-stage queued portrait renderer. Its bounded texture cache is local to the window; closing it stops queued work. The existing logged-in appearance editor keeps its Human-only/race-change boundary.

Focused checks:

```text
Godot --headless --path godot-client --script res://tests/test_creation_base_library.gd
Godot --headless --path godot-client --script res://tests/test_creation_base_picker.gd
Godot --path godot-client --script res://tests/test_creation_base_flow.gd -- --no-map-cache
Godot --path godot-client --script res://tests/test_character_creation.gd -- --no-map-cache
```

The real-renderer tests isolate unrelated arrival/world preparation and never open a connection or submit a character. They check staging, confirmation/cancellation, actor and colour transfer, credential/calling preservation, Ssarathi bodies and protocol fallback. The component is also checked at compact and desktop sizes with keyboard/gamepad focus.
