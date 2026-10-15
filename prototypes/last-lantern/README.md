# The Last Lantern — in Eloria

`play.cmd` now launches **the actual Eloria client and a private local dev-server**.
Create a character to begin the rescue on Lantern Reach, a small coastal map
that leads into Four Gates. The original standalone project remains a design reference.

## Play

Double-click `play.cmd`, or run `.\play.cmd`. Click **Connect**, then **New Character**.
Returning players can log in with the same local name and password.

The launcher requires Godot 4.7 and Python 3.11+. It finds the installed copies;
optional overrides are `-Godot "C:/path/Godot.exe"`, `-Python "C:/path/python.exe"`
and `-Port 2009`. It keeps the PowerShell execution-policy override in the
launcher process, so running it does not change the system policy.

The server listens only on `127.0.0.1:2008`, uses normal gameplay timing, and
stops when this client closes. Terrain is prepared from the shipped collision
grids. Local characters and client preferences live in `.local/native/`.
`-Fresh` creates a separate profile without deleting previous saves.
The matching `dev-server` checkout must sit beside `eloria-client`.

## The real gameplay route

| Scene | What the player actually does |
| --- | --- |
| Grounded ferry | Click the ground, turn the camera, follow Nesh's marker |
| Boathouse | Talk to Caldus through NPC dialogue, read the chart, open Map with Tab |
| Tidal garden | Start native harvesting; collect 3 Reed and 1 Quartz with a Pickaxe |
| Repair shed | Deposit materials in Storage, withdraw tools and ingredients, make a Torch in Manufacturing |
| Causeway | Equip the sword and shield in Inventory, fight the level-1 otter, collect its real drops |
| Beacon steps | Eat Bread and spend an earned attribute pickpoint in Statistics |
| Lantern room | Withdraw the stored repair materials, repair the housing and light it with the crafted Torch |
| Return dock | Sell meat and buy Bread through the merchant window, then sail to Four Gates |
| Four Gates | Speak to Gate Warden Ilyon to complete the rescue |

The guide stays visible across 28 objectives and highlights the relevant
existing button, item list or equipment item. It fits beside Storage and inside
Manufacturing. World markers and map markers use the same server target.
The guide never grants inventory or claims a successful harvest, craft or kill.
Only opening the local map is reported as a UI action.

Each character gets a private map copy. Progress, items, equipment, storage and
opened gates persist. A novice defeat keeps the kit and allows another attempt;
the bench and Caldus recover missing essentials after a failed mix or lost bag.
Global days that forbid harvesting, crafting, food or combat do not block the
private rescue. Ordinary cooldowns, tools, carrying capacity and crafting outcomes apply.

New characters on the updated server begin here. Existing characters keep their
current progress; `#tutorial lantern` offers a one-time opt-in for reviewing the
rescue. **Skip tutorial** asks for confirmation and takes the character to Four
Gates without awarding completion. Closing instructions never completes a lesson.

## Implementation and design reference

The client loads `eloria-assets/maps/lantern-reach/` through its normal map registry.
Server integration lives in `dev-server/eloria/lantern.py`; gameplay remains in
the existing server handlers. Client rendering is in `src/world/lantern_scene.gd`
and guidance in `src/ui/lantern_guide.gd`.

See [the integration notes](../../docs/last-lantern-integration.md),
[the original storyboard](prototype-design.md), [the art pass](art-pass.md)
and [the map plan](map-plan.png). Opening this folder's `project.godot` still runs
the older simulated prototype; use `play.cmd` for the integrated game.
