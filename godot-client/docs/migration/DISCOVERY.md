# Discovery inventory — milestone 1 baseline

Audited client branch: `develop@77860e5ac120937560cc9cfc7cd50e28c526252d`.
Audited server branch: `main` (protocol blob `b24072ed87693e41272194b068e7e23b288f33a2`).

## Legacy subsystem sources

| Area | Client source | Server source | Godot target |
|---|---|---|---|
| TCP/protocol | `connection.cpp`, `socket.cpp`, `client_serv.h`, `multiplayer.c` | `eloria/protocol.py` | `src/network` |
| Login/endpoints | `loginwin.c`, `servers.c` | session handlers + protocol | auth scenes/config |
| Actors/animation | `actors.c`, `new_actors.c`, `actor_glb_runtime.cpp` | actor packets/state | state DTOs + Actor3D |
| Maps | `map.c`, `map.h`, GLB runtime sources | `eloria/maps.py`, map connections | GLB scene + JSON adapter |
| HUD/windows | `hud*.c/cpp`, `interface.c`, feature modules | packet-driven state | Control scenes/window manager |
| Input | `keys.c`, mouse handlers | validated movement/actions | InputMap actions |
| Inventory/trade | `items.c`, `storage.c`, `trade.c` | inventory/trade services | reducers + window scenes |
| Magic/crafting | `spells.c`, `manufacture.c` | spell/crafting services | reducers + action UI |
| Chat/social | `chat.c`, `buddy.c` | chat/PM/buddy handlers | channel model + UI |

## Window inventory

Login/account, main viewport frame, status bars, quickbar, quick spells, minimap/full map, chat tabs, inventory, equipment, statistics, skills, knowledge, quest log, magic, manufacture, storage, bags, NPC dialogue, trade, buddy list, options, help, console/system messages, overlays, tooltips, quantity/confirmation dialogs, and context menus.

## Asset baseline

Four Gates already has production-path GLB/JSON assets under `eloria-assets/maps/four-gates-city/`. Native playable GLBs must remain unconverted. Registries will store model path, import scale/orientation, skeleton path, explicit clip map, and attachment bone names per model.

HUD presentation is sourced from the legacy `hud.c` and `hud_misc_window.c` layout:
a horizontal lower status region, right-side controls, and the compass region at atlas pixels
`(32, 193, 63, 63)`. The source `gamebuttons.png` and `gamebuttons2.png` atlases are
copied unchanged into `godot-client/assets/ui/` so Godot exports include them. Only
functional actions are exposed in the initial quickbar.

## Intentional architecture changes

Legacy rendering globals become state reducers plus reactive scenes. GLB is native. Legacy ELM support, if retained, is isolated behind an adapter. Gameplay authority remains server-side.
