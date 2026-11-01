# Character starting looks

Creating a character opens the starting-look library before the full editor. Search, race, sex and hair filters work together. Selecting a card previews the body and appearance; only **Use this basis** changes the editor. Cancelling the first window returns to login. The **Choose starting look** button at the top of the editor opens the library again; cancelling that window preserves all current edits and the camera. Changing a basis preserves the character name, password fields and calling.

New players currently choose Humans only. The development library contains 41 starting looks: both Human sexes, the established Mira/Rowan/Tavi studies and all 36 named Human archetypes. The additional 30 looks are awaiting likeness review before merging. The full editor and Randomize use the same race availability policy. Hairstyle descriptions stay searchable alongside names. A basis name does not fill the player's character-name field.

Human names are Lyra and Alden for the general bases; Mira, Rowan and Tavi retain their established names. The six selectable fitted pilots are Amara (01), Corin (08), Nessa (14), Darian (20), Elowen (27) and Bram (34).

The additional looks retain their concept names, from Stellan and Selene to Lenora and Ewan. Each is an editable face, age, pigment and grooming configuration on the existing Human rig. Existing customizable hairstyles are reused; the new smooth low bun and short coils extend the library. Their High models use separate modern updo and buzz-cut fallbacks at lower graphics levels while dedicated Native fits remain unqualified. Some concepts still need topology-specific styles such as braided crowns, side braids and twin braids; the development review identifies those approximations explicitly.

`src/actors/player_creation_policy.gd` filters the shared body catalog for player creation. Main's selectors, `creation_base_library.gd` and the network creation guard reuse that policy. The complete `models.json` model, actor-type and body-option catalogs remain available for NPCs and authoring; existing non-Human characters can still log in. The Human archetypes come from `data/actors/rl_head_archetypes.json`. Protocol 4 includes saved aging controls, protocol 3 the other advanced cosmetics, protocol 2 its saved fallback and older protocols only the seven legacy cosmetic fields. Stable IDs and calling inventory remain unchanged.

`creation_base_flow.gd` stages a temporary preview separately from the editor. The picker loads pre-rendered portraits; only the active character uses a live 3D preview. Existing non-Human portrait assets are retained without making those bodies selectable. The logged-in appearance editor keeps its existing Human-only/race-change boundary.

Focused checks:

```text
Godot --headless --path godot-client --script res://tests/test_player_creation_policy.gd
Godot --headless --path godot-client --script res://tests/test_creation_base_library.gd
Godot --headless --path godot-client --script res://tests/test_creation_base_picker.gd
Godot --headless --path godot-client --script res://tests/test_remaining_human_bases.gd
Godot --path godot-client --script res://tests/test_creation_base_flow.gd -- --no-map-cache
Godot --path godot-client --script res://tests/test_character_creation.gd -- --no-map-cache
```

The real-renderer tests isolate unrelated arrival/world preparation and never open a connection or submit a character. They check staging, confirmation/cancellation, actor and colour transfer, credential/calling preservation, Human-only selectors/randomization, rejected stale non-Human choices and protocol fallback. The component is also checked at compact and desktop sizes with keyboard/gamepad focus. `test_player_creation_policy.gd` uses a recording transport to prove direct non-Human requests send no frame while the NPC/model catalog remains intact.
