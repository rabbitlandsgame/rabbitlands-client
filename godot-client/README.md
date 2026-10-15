# Rabbit Lands Godot Client

Rabbit Lands (RL), a Godot fantasy MMORPG client compatible with the Rabbit Lands server. Eloria remains the world name.

## Engine and language

- Godot **4.7.2-stable** (pinned; do not use 4.8 development snapshots).
- Typed GDScript is the primary language. It keeps deployment simple while allowing native Godot scenes and resources.
- Desktop rendering uses Forward+. OpenGL Compatibility and safe-mode launchers are included in player packages; see [compatibility diagnostics](../docs/client-compatibility.md).

## Run

Windows: install Godot 4.7.2, open `godot-client/project.godot`, and press F6/F5.

Linux:

```sh
godot --editor --path godot-client
godot --path godot-client
```

The initial screen defaults to `game.rabbitlandsgame.com:2000`, connects over real TCP and sends the server's real `LOG_IN` frame. For local development use `-- --server=127.0.0.1 --port=2000`. A configured TLS listener uses port 2001 with **Encrypted connection (TLS)** selected; certificate verification stays enabled. The public hostname requires separately configured DNS and hosting.

## Default controls

- `W`/`S`: move forward/backward relative to facing. `A`/`D`: strafe without turning; combine keys for diagonal movement and hold Shift to run.
- `Q`/`E`: turn the local character. `Space`: recenter the viewport on your character.
- `Ctrl+I`: toggle inventory. Drag its title bar to move it and its lower-right grip to scale the whole window proportionally. Right-click Sto All or Drop All to protect individual edge rows/columns; Get All opens and empties the ground bag on your tile subject to server slot/load validation.
- `Tab`: toggle the full map. `Alt+M`: toggle the minimap; drag its thick compass border and right-click it for north-up, player-up, or viewport-up orientation.
- `T`: open and focus chat; `Esc`: release typing focus. Close hides chat until `T` or the Chat button reopens it. Drag the header to move chat and its bottom-right corner to resize it; both are saved. All combines messages, category tabs filter them, and each joined channel gets its own tab. Party/Guild/channel tabs also address ordinary messages to that destination. Backtick/tilde toggles full chat history.
- Party uses a compact roster with health and ether bars, a leader crown, collapse and close buttons. Drag its header to move it or its bottom-right grip to resize it. Narrow layouts hide names and keep initials badges; hover a row for full details. The header's … menu switches bars to colored current/max numbers and resets window size. Position, size, collapse state and number preference are saved; health updates respect a closed roster.
- `Alt+A`: attack the selected target. `Alt+S`: sit or stand.
- The Eternal Lands window keys: `Ctrl+S` spells, `Ctrl+M` manufacture, `Ctrl+J` emotes, `Ctrl+G` quest journal, `Ctrl+B` buddies, `Ctrl+A` stats, `Ctrl+T` ranging, `Ctrl+H` help, `Ctrl+N` notepad, `Ctrl+O` options, `Ctrl+L` mail, `Ctrl+E` encyclopedia. All rebindable in Settings → Controls.
- Every window moves by its title bar, and stays inside the viewport and clear of the right rail. The inventory and ground bag also scale from their lower-right grip and remember where they were left.
- A HUD icon is drawn in colour whenever its action is available and greyed only when it is not; an open window is marked by the lit frame around its icon. The sit icon becomes the stand icon while you are seated.
- The right rail carries the legacy misc-window column: skill rows (click one to watch it on the experience bar), the countdown/stopwatch timer (click to start/stop, Shift+click for stopwatch, wheel to set), the knowledge bar, the digital and analog clocks, and the compass. The settings window's HUD tab shows or hides each, plus the FPS readout and the S H P M R G A indicator letters.

## Settings inventory

The Options icon, Options button and `Ctrl+O` open one settings window. Tabs scroll independently; tab arrows keep every category reachable on smaller screens. Right-clicking your character opens its Banners tab, right-clicking the lower HUD opens HUD, and the spell bar's settings shortcut opens Spells. Preferences apply immediately and retain their existing settings-file keys.

| Tab | Available preferences |
| --- | --- |
| HUD | UI scale; FPS, clocks, seconds, knowledge, timer, stats, indicators and chat timestamps; combat HUD visibility and pinning; countdown duration and stopwatch mode; lower HUD bar order and visibility; watched experience skill; invasion assistant scale. |
| Minimap | Visibility, size, orientation, shape, border, map range, marker size, and all eleven marker categories. |
| Banners | Names; health, ether, food and action bars and numbers; instance mode; speech bubbles; background; sit and ranging locks; right-click shortcut. |
| Graphics | Frame limit, painted look, quality, shadows, particles, nameplates and distance, character visibility through obstacles, map cache usage and clearing. |
| Camera | Rotation sensitivity, pan sensitivity and player following. |
| Audio | Sound enablement and volume, with offline attribution credits. |
| Inventory | Equipment side, inventory and ground bag scales, storage docking, six editable quantity shortcuts and active quantity, plus all eight Store All/Drop All protection switches. |
| Spells | Spell bar visibility and docking, casting mode, number of visible shortcuts, and magic ring size. |
| Gameplay | Server commands for target mode and autogather, secure connection for the next login, and login background and animation. |
| Controls | Every declared client input action, including party, screenshot and obstacle visibility shortcuts. |

The audit covers client preferences, context-menu choices, `eloria_hud.cfg`, window scale preferences, and casting-bar options. Window positions remain adjustable by dragging their title bars or grips. Notes, bookmarks, console aliases/filters/ignored names, favorite item lists, prepared spell assignments/powers and magic ring pins/target scopes are player-authored content managed by their existing editors or commands. Server-owned character, combat and administrative state remains on the corresponding gameplay windows. Casting mode keeps its existing session-only behavior; ring size remains per character.

## Optional focused check

```sh
godot --headless --path godot-client --script res://tests/test_protocol.gd
```

The protocol test includes byte fixtures for framing, movement, fragmented headers, combined packets, and invalid lengths.

## Named NPCs

`data/actors/npc_characters.json` records the 256 named NPCs' models, dyes, equipment and the histories behind their clothes. Edit profiles by full lowercase name; update `wireNames` when a display name exceeds the native server's 29-byte Latin-1 limit. A profile only applies when both the NPC kind and actor type match.

Backstory excerpts and `dialogueTopics` refer to the server's personal conversations in `config/eloria/npc_dialogue.txt`. Keep those excerpts and outfit notes aligned with changes to the playable dialogue. Gauntlet keeper stories also live in the server's `tools/author_gauntlets.py` so rebuilding that content preserves them.

The optional developer suite validates the cast with `tests/test_npc_characters.py`, checks identity and state isolation with `tests/test_npc_character_looks.gd`, and loads every outfit through production presentation with `tests/integration/npc_character_appearances.gd`. The integration script accepts captured server spawn frames via `ELORIA_NPC_PACKETS` and writes representative front, side and walking previews when `ELORIA_NPC_PREVIEWS` names an output directory.

## Security

Password-containing frames are marked sensitive and never printed. The protocol inspector must preserve this redaction contract.

## Status

This milestone is an executable foundation, not parity completion. See `docs/migration/` for discovery, protocol, risks, and traceability.

## Validation scenes

Open and run these scenes in Godot 4.7.2:

- `src/dev/model_validation.tscn`: switches luminous male/female, retargets the native 162-clip animation GLB, cycles mapped clips, and rotates lighting.
- `src/dev/world_validation.tscn`: loads Four Gates through the production `WorldLoader`, including manifest validation and declared collision.

A PASS label is evidence of source/runtime loading only. Record screenshots and review skeletons, materials, attachments, navigation, and coordinate placement before changing traceability to VERIFIED.

## Branding and local settings

The temporary typographic Rabbit Lands/RL wordmark replaces the old visible
logo without altering gameplay artwork. Final logo artwork remains future work.
The application title is Rabbit Lands, while the existing Godot user directory
`Godot/app_userdata/Eloria` (Linux: `godot/app_userdata/Eloria`) is retained so
settings, notes and trusted local certificates continue to work. Internal
`ELORIA_*` environment and protocol names, schemas and resource paths remain
stable for compatibility. No GitHub Actions or default merge test gates are
configured; the older developer tests remain optional.
