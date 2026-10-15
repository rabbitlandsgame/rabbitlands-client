# Input parity baseline

The complete legacy `keys.c` audit is in progress. Names below are stable Godot actions; exact defaults must be copied only after resolving platform conditionals.

| Legacy behavior | Context | Godot action | Rebindable |
|---|---|---|---|
| Ground click / move | world | world_move | yes |
| Run modifier / run-to | world | world_run | yes |
| Rotate camera | world | camera_rotate | yes |
| Zoom | world | camera_zoom_in/out | yes |
| Select / context action | world | select / interact | yes |
| Attack | world | attack | yes |
| Focus chat / submit | HUD | chat_focus / chat_submit | yes |
| Full map | HUD | toggle_map | yes |
| Inventory | HUD | toggle_inventory | yes |
| Magic | HUD | toggle_magic | yes |
| Manufacture | HUD | toggle_manufacture | yes |
| Escape / cancel | global | cancel | yes |
| Sit / stand (Alt+S) | world | toggle_sit | yes |
| Screenshot | global | screenshot | yes |
| Fullscreen | global | toggle_fullscreen | yes |

World input must be suppressed when a Control consumes the pointer event. Debug bindings exist only in development builds.

## Implemented gameplay shell controls

| Gesture | Result |
|---|---|
| Left click on world | Convert Godot ground point to server tile and send MOVE_TO |
| Left click on minimap / full map | Project through that map camera and send MOVE_TO |
| Shift + left click | Send RUN_TO |
| Right-button drag | Orbit yaw and pitch |
| Middle-button drag | Pan focus offset |
| Mouse wheel | Zoom with configured limits |
| Tab | Toggle full map using the minimap render |
| Alt+S | Send the authoritative desired sit/stand state |
| T / Enter | Focus chat; Enter submits RAW_TEXT |
| Click NPC | Select actor and send TOUCH_PLAYER |
| Ctrl+E | Open the reference window on the encyclopedia, or close it from there |
| Hold Alt | The move icon shows the attack icon: a click attacks what it lands on |

The full-screen `SubViewportContainer` owns world mouse input through its `gui_input`
signal. HUD controls render above it and consume their own events, preventing click-through.
This explicit route is required because mouse events delivered to an embedded viewport are
not guaranteed to reappear in the root Control's `_unhandled_input()` callback.

The camera focus is updated every rendered frame from the local actor's presentation
transform. Server reconciliation, interpolation, and terrain-height projection therefore
cannot leave the camera at a stale position. Focus updates preserve yaw, pitch, zoom, and
the explicit user pan offset.

## Binding resolution

Every keyboard binding is resolved through the InputMap. `main.gd` contains no
raw keycode comparison for a bound action: `_input()` delegates to
`_handle_bound_action()`, which is a list of `is_action_pressed()` branches, and
`_unhandled_input()` owns the gameplay actions a focused control is allowed to
swallow. Before this, `toggle_inventory`, `turn_left` and `turn_right` were
declared as actions but resolved by keycode, so rebinding them appeared to work
and changed nothing, and `toggle_map`, `toggle_minimap` and `toggle_console`
were resolved twice - once by keycode and once by action.

`_handle_bound_action()` returns early while a `LineEdit` or `TextEdit` has
focus. Several actions default to bare printable keys, so without that a
backtick typed into chat would open the console at the same time, and `Ctrl+C`
would connect instead of copying. `cancel` is the one exception: it still
dismisses the chat entry from a focused field.

| Action | Default | Handler |
|---|---|---|
| `connect` | Ctrl+C | `_on_connect_pressed()` - available before the world exists |
| `disconnect` | Ctrl+D | `_on_disconnect_pressed()` - the action shipped with an empty event list and no handler |
| `toggle_inventory` | Ctrl+I | `_on_inventory_button_pressed()` |
| `toggle_map` | Tab | `_toggle_full_map()` |
| `toggle_minimap` | Alt+M | `_toggle_minimap()` |
| `toggle_console` | ` | `_toggle_console()` |
| `recenter_viewport` | Space | `_recenter_viewport_on_player()` |
| `turn_left` / `turn_right` | Q / E | `_turn_local_actor()` |
| `toggle_encyclopedia` | Ctrl+E | `_on_encyclopedia_button_pressed()` |

`toggle_encyclopedia` is the one action resolved with an exact modifier match.
Godot compares an action's modifiers only when asked to, so `turn_right` - a
bare E - takes a key event carrying a Ctrl it was never bound with. The
encyclopedia is therefore checked ahead of turning, and checked exactly, so
Ctrl+E opens a window without also turning the player and a bare E turns the
player without also opening a window.

## The move icon and Alt

Holding Alt makes an ordinary click an attack, and the move icon on the lower
HUD says so by wearing the attack icon while Alt is down. It is a preview and
not a mode: letting Alt go puts the icon back, and neither pressing nor
releasing Alt changes the interaction mode. An attack mode the player chose by
clicking the attack icon is therefore untouched by Alt - it was their decision,
and it stays until they choose the move icon again. Pressing the move icon
while it is showing the attack icon does what the attack icon does, because
that is what it is showing.

`connect` keeps its declared Ctrl+C default, which collides with copy on any
focused text surface other than a `LineEdit`/`TextEdit`. The rebinding UI in
Phase 3.3 is where a player resolves that; it is recorded here rather than
silently changed.
