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
- Hold the mouse wheel button and drag to rotate the view; scroll to zoom. The camera always stays focused on your player.
- Right-click the world to cycle Move → Trade → Fight → Use → Pick up → Harvest → Talk → Look. Left-click applies the selected action. Move retains contextual interactions on hover; other tools ignore incompatible targets. Use also selects the inventory's use-item tool. Right-click first cancels a carried item or pending spell; `Esc` returns to Move.
- Targeted spells: choose the spell, then click its recipient. Your character moves within 15 tiles, faces the target, then channels and casts. Walking elsewhere, `Esc`, or right-click cancels the approach or channel.
- `Ctrl+I`: toggle inventory. Drag its title bar to move it and its lower-right grip to scale the whole window proportionally. Right-click Sto All or Drop All to protect individual edge rows/columns; Get All opens and empties the ground bag on your tile subject to server slot/load validation.
- `Ctrl+Shift+L` or the Leaderboards HUD button: open the podium and top-ten rankings. Search or expand the category groups to choose any of the 22 boards, switch between **All time** and **Last 30 days**, and use **Refresh** for a current snapshot. Painted gold, silver and bronze medallions identify the leaders; the bottom strip shows your rank even outside the top ten. Portraits show each character's actual race, hair, dyes and visible worn equipment, including offline players. The client renders them once per appearance and reuses the images; initials appear when appearance data is unavailable. Skill boards rank by XP (XP gained for the last 30 days). `Esc` closes the window. The shortcut can be rebound in Settings → Controls; existing custom bindings are preserved, and the earlier conflicting default migrates automatically. `Ctrl+L` still opens Mail. `#leaderboards category [all|30]` opens the same board; older clients receive chat results, and `#top_players` remains available.
- `Tab`: toggle the full map. Scroll over it to zoom; above 100% (up to 400%), the map zooms around the cursor and keeps the location under it in place. While zoomed in, left-click and drag to pan; the view stays where you leave it as your character moves. Choose **Current map** to recenter on your player. A click without dragging still walks there; hold Shift to run. At 100% or below it frames the region, with continent exteriors able to zoom out over their neighbors. `Alt+M`: toggle the minimap; drag its thick compass border and right-click it for north-up, player-up, or viewport-up orientation.
- The Tab map fills the play area up to the right and bottom HUD. Its left sidebar has a fixed width and scrolls when needed. Hover or scroll over the map to read the cursor's X/Y coordinates beside the pointer. A red X marks your selected movement destination until arrival, cancellation, or a replacement movement order.
- Regional Tab maps and the minimap use detailed renders at four pixels per metre. Detailed images load for the current region, nearby regions visible while zooming or panning, and the selected region preview. The cache retains at most five visible regions and one preview; the wider continent view uses smaller images.
- `T`: open and focus conversations. `Esc` releases typing focus and preserves the draft; press `Esc` again outside a text field to clear it. If chat was hidden before `T`, it returns to hidden when typing ends with no draft, after the second `Esc` clears the draft, or after successfully sending it. A pending draft keeps the window visible, and `T` resumes it. Chat that was already visible stays visible. Use either window's × button to close it. Conversations start upper left and system messages lower left, with a soft, borderless fade behind the text. Drag either header to move that window and its bottom-right corner to resize it; both layouts are saved independently. Settings → Chat configures each window's visibility, lock, text size, background opacity, line spacing and idle dimming, or combines both feeds in the conversation window. The visible **To:** selector identifies the send destination; Private needs a selected player or `/name message`. Party/Guild/channel tabs select that destination, while reading the full log never retargets a draft. Backtick/tilde or either window's Log button opens session history with All, System, Chat, Local, Party, Guild, Private, numbered-channel and individual private-conversation filters.
- Drag across text in either chat window or the full log to select it, then use `Ctrl+C` or right-click → Copy. The chat composer supports `Ctrl+V` and its native edit menu. **URLs** opens links seen this session, newest first, with Open in browser, Copy URL and double-click opening. `F2` opens the latest seen URL in the system default browser, including while typing a reply; it can be rebound in Settings → Controls. Links survive the message log's scrollback limit and clear on disconnect. Ignored/filtered messages do not contribute links.
- Party uses a compact roster with health and ether bars, a leader crown, collapse and close buttons. Drag its header to move it or its bottom-right grip to resize it. Narrow layouts hide names and keep initials badges; hover a row for full details. The header's … menu switches bars to colored current/max numbers and resets window size. Position, size, collapse state and number preference are saved; health updates respect a closed roster.
- `Alt+A`: attack the selected target. `Alt+S`: sit or stand.
- The Eternal Lands window keys: `Ctrl+S` spells, `Ctrl+M` manufacture, `Ctrl+J` emotes, `Ctrl+G` quest journal, `Ctrl+B` buddies, `Ctrl+A` stats, `Ctrl+T` ranging, `Ctrl+H` help, `Ctrl+N` notepad, `Ctrl+O` options, `Ctrl+L` mail, `Ctrl+E` encyclopedia. All rebindable in Settings → Controls.
- Quest windows can be hidden without skipping the quest: choose **Untrack** on the guide, the tracked note's **×**, or **Untrack** for that quest in the journal (`Ctrl+G`). Objective updates keep the window hidden. Select the quest and choose **Track** to show its current objective again.
- Every window moves by its title bar, and stays inside the viewport and clear of the right rail. The inventory and ground bag also scale from their lower-right grip and remember where they were left.
- A HUD icon is drawn in colour whenever its action is available and greyed only when it is not. An open window or armed mode is not marked yet: the quickbar icons are flat buttons, so the lit pressed frame set for them never draws. The sit icon becomes the stand icon while you are seated.
- The right rail carries the legacy misc-window column: skill rows (click one to watch it on the experience bar), the countdown/stopwatch timer (click to start/stop, Shift+click for stopwatch, wheel to set), the knowledge bar, the digital and analog clocks, and the compass. The settings window's HUD tab shows or hides each, plus the FPS readout and the S H P M R G A indicator letters.

The click, item-carry and movement-pacing contracts behind these controls are in [input and movement contracts](../docs/input-and-movement-contracts.md).

## Settings inventory

The Options icon, Options button and `Ctrl+O` open one settings window. Tabs scroll independently; tab arrows keep every category reachable on smaller screens. Right-clicking the lower HUD opens HUD, and the spell bar's settings shortcut opens Spells. Preferences apply immediately and retain their existing settings-file keys.

| Tab | Available preferences |
| --- | --- |
| HUD | UI scale; FPS, clocks, seconds, knowledge, timer, stats, indicators and chat timestamps; combat HUD visibility and pinning; countdown duration and stopwatch mode; lower HUD bar order and visibility; watched experience skill; invasion assistant scale. |
| Chat | Separate or combined feeds; independent visibility, movement/resize lock, text size, soft-fade opacity, line spacing, idle dimming and layout reset for the conversation and system windows. |
| Minimap | Visibility, size, orientation, shape, border, map range, marker size, and all eleven marker categories. |
| Banners | Names; health, ether, food and action bars and numbers; instance mode; speech bubbles; background; sit and ranging locks. |
| Graphics | Performance preset; 3D resolution; map texture resolution and renderer (next launch); frame limit; appearance (Original / Painted ground / Full painted); quality; shadows; effects; extra grass; nameplates and distance; crowd bodies and capes; map cache usage and clearing. |
| Camera | Rotation sensitivity. The camera stays focused on the player. |
| Audio | Sound enablement and volume, with offline attribution credits. |
| Inventory | Equipment side, inventory and ground bag scales, storage docking, six editable quantity shortcuts and active quantity, plus all eight Store All/Drop All protection switches. |
| Spells | Spell bar visibility and docking, casting mode, number of visible shortcuts, and magic ring size. |
| Gameplay | Server commands for target mode and autogather, secure connection for the next login, and login background and animation. |
| Controls | Every declared client input action, including party, screenshot and obstacle visibility shortcuts. |

The audit covers client preferences, context-menu choices, `eloria_hud.cfg`, window scale preferences, and casting-bar options. Window positions remain adjustable by dragging their title bars or grips. Notes, bookmarks, console aliases/filters/ignored names, favorite item lists, prepared spell assignments/powers and magic ring pins/target scopes are player-authored content managed by their existing editors or commands. Server-owned character, combat and administrative state remains on the corresponding gameplay windows. Casting mode keeps its existing session-only behavior; ring size remains per character.

For slower machines, **Apply Performance preset** selects Low quality, Painted ground, 75% 3D resolution, 30 FPS, 60 crowd bodies, no remote cape cloth or directional shadows, a 20 m name distance, and no extra grass. Spell and projectile cues remain enabled; Low halves the ordinary combat visual budgets and reduces remote animation budgets. Player and target effects retain priority. Every control remains editable afterward. The preset also selects half-resolution map textures, which take effect after restarting; it preserves the renderer choice and map cache preference.

3D resolution offers 100%, 75% and 50% while menus and overhead text stay at native resolution. Map textures offer Full, Half and Quarter resolution for external map images, keeping compressed textures compressed; UI and actor textures are unchanged. Texture and renderer preferences apply on the next launch. Explicit compatibility/safe-mode launchers override the saved renderer. Extra grass affects Full painted's cosmetic beds, leaving terrain and interaction objects present. A still flame identifies placed fires when effects are disabled; their particle systems and real lights stop. Low quality also limits nearby fire lights, and changing quality updates settled precipitation immediately without restarting the weather transition.

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
- `src/dev/trailer_camera/trailer_camera.tscn`: flies a camera along a keyframed shot file over a served map, for trailer world shots rendered with Movie Maker. Its [README](src/dev/trailer_camera/README.md) also covers the live client's capture-only HUD toggle (`-- --trailer-capture`, F9).

A PASS label is evidence of source/runtime loading only. Record screenshots and review skeletons, materials, attachments, navigation, and coordinate placement before changing traceability to VERIFIED.

Look and lighting checks:

- Settings → Graphics → Appearance defaults to **Painted ground**: painted terrain with the original lighting, creatures, props, foliage and water. **Original** restores the original terrain too; **Full painted** includes the painted sky, foliage, water, global grade and extra grass. Overhead text and banners render in a separate transparent pass at native resolution, with original colors and no world fog or glow. Old On preferences migrate to Painted ground; old Off preferences remain Original.
- `ELORIA_LOOK=original`, `painted_ground` or `full_painted` forces an appearance; legacy `0` and `1` still force Original and Full painted, and `ELORIA_LOOK_QUALITY=low`, `medium` or `high` forces the graphics quality, over the saved Settings → Graphics choices; the overridden control is greyed out (`src/world/look/look_profile.gd`, presets in `QUALITY_PRESETS`). Per-map look data lives in `src/world/look/regions/`, whose README covers the schema.
- Check shadow and sun-elevation changes on vertical casters, such as Four Gates' walls in `src/dev/world_validation.tscn`: at grazing sun angles flat ground already faces away from the light (N·L ≤ 0) and shows no difference. Shadow strength is a package's `environment.sun.shadowOpacity`, or else `WorldEnvironmentBinder.sun_shadow_opacity` lets `SUN_SHADOW_LEAK_ENERGY` through. `ambient_light_energy` does not change sky-sourced ambient (see the comments in `src/world/world_environment_binder.gd`).

## Branding and local settings

The login logo, compact HUD mark, application/updater icons and startup splash
use the Rabbit Lands artwork adapted from the selected Discord crest. See
[`assets/branding/README.md`](assets/branding/README.md) for the canonical kit,
usage and provenance. Other gameplay artwork is unchanged.
The application title is Rabbit Lands, while the existing Godot user directory
`Godot/app_userdata/Eloria` (Linux: `godot/app_userdata/Eloria`) is retained so
settings, notes and trusted local certificates continue to work. Internal
`ELORIA_*` environment and protocol names, schemas and resource paths remain
stable for compatibility. No GitHub Actions or default merge test gates are
configured; the older developer tests remain optional.
