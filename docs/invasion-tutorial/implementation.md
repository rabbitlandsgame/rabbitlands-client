# The Second Bell: playable client integration

Bellwatch is implemented in the main Godot client and the sibling `dev-server`.
It contains 32 saved objectives across the ten storyboard scenes, on a private
144 × 144 map with four gates. It uses normal inventory, storage, combat, flee,
ranging, loot, chat, statistics, NPC dialogue and object interactions.

## Play it

Start the client and matching server with
[`prototypes/last-lantern/play.cmd`](../../prototypes/last-lantern/play.cmd).
Finish or leave The Last Lantern, then talk to Gate Warden Ilyon in Four Gates
and choose **Help at Bellwatch: The Second Bell**. Existing characters can enter
directly through chat with `#tutorial invasions`. An active older Four Gates
walkthrough retains Ilyon's original dialogue until it finishes or is stopped.

`#tutorial` repeats the current objective. **Ask Nesh** gives contextual help;
Nesh in the central court lends replacements and offers checkpoint recovery.
**Leave tutorial** pauses the adventure and returns to Four Gates. Talk to
Ilyon or use the entry command again to resume. This is one adventure per
character; completion grants 25 gold and two Bread in storage once.

Gameplay milestones also grant one-time XP alongside ordinary action XP. The
full route adds **1,575 Overall XP**, including **380 Attack, 480 Defense,
80 Ranging and 60 Engineering XP**. Encounters reward Attack and Defense;
the winch rewards Engineering, the bow lesson rewards Ranging, and departure
adds 150 Overall. Native chat identifies each completed lesson's bonus and
normal stats/level notifications refresh immediately.

The checkpoint, XP and receipt are saved before notifications. Reconnecting,
recovering supplies and replaying events cannot duplicate rewards. Window-only
steps, help and explicitly skipped recovery lessons award no XP. Existing
completed tutorials are not backfilled.

The `.cmd` launcher avoids PowerShell's restriction on launching `.ps1` files
directly. This change has not been deployed to a remote server.

## Implemented route

| Scene | Player action | What the server verifies |
| --- | --- | --- |
| First bell | Meet Nesh, open Map, submit `#il` | Arrival, native map opening, actual public count command |
| Kit | Take the kit, deposit three planks, withdraw a potion, equip sword/shield | Real quantities and equipment slots |
| Orchard | Approach a red invader, fight, collect its bag | Defeat and actual meat in inventory; manual loot and auto-gather both work |
| Retreat | Engage the East raiders, click ground to flee, reach the refuge, use a potion | Successful flee, safe position and health actually restored |
| Mill breach | Clear two finite waves separated by a seven-second lull; operate the winch | Every required actor defeated, pending wave resolved, real nearby object use |
| Ranging | Equip bow and compatible Arrow, fire a hit, open Ranging, finish the sentry | Real ammunition consumption, ranging hit, retaliation, panel opening and defeat |
| Captain overlook | Enter the South approach and inspect the captain | Player position; the armed, larger captain already exists |
| Mire Goblin captain | Fight through healing charges and health-triggered reinforcements | Normal boss logic: three heals, two summon thresholds, finite summon budget; followers disperse on death |
| Departure road | Ready the cart, defeat a Great captain, clear its survivors | Strength 1.15, dispersal disabled, no required living actors left |
| Second bell | Ring the bell, open Counters, submit `#il`, board the cart | Native interactions, statistics tab, fresh command and one-time completion |

The practice bow has missile accuracy +6 in the normal item stat system. It
uses the Sunmane bow's existing model and icon. It is a loan, excluded from
public drops and crafting; other bows and global hit probabilities are unchanged.
The sentry patrol stays within one tile of its starting post until ordinary
retaliation moves it, keeping the firing marker outside minimum bow range.

Every encounter uses reviewed creature art: scouts use the updated red fox
model, while raiders, the sentry and both captains use the updated Mire Goblin.
The level-1 fox retains the scout's gentle combat stats and required meat drop.
Waves, captain reinforcements and resumed encounters share these definitions.
Their nameplates use the normal species names, **Red Fox** and **Mire Goblin**,
including both captains. Tutorial roles remain in the quest instructions;
saved encounters receive the current species names when resumed.

The Mire Goblin captain now has 40 health (down from 60), and the final captain
has 46 (down from 69). Both have attack 1 and innate damage 1 (previously
attack 2 and damage 1–2), before sword damage and player defenses. Their
attributes remain at 1, keeping sword strikes gentle. Their swords, three
healing charges and two summon thresholds still teach the boss mechanics.
Older saved encounters receive the lower stats on resume, preserving the
remaining health proportion, defeated enemies and spent healing/summon budgets.

The final encounter has fewer prompts. Asking for help, checkpoint recovery or
choosing the explicit recovery-practice waiver records assistance in the journal.
The waiver is available for returning characters who already know fleeing and
potions; it does not falsely record a flee or heal. Early player actions can
already satisfy equipment, loot or recovery objectives.

## Recovery and isolation

- The server owns progress, gates, actors, item changes and rewards. The client
  can report opening a teaching window, request help, refresh or request leave.
- Each character has a separate map and spawn groups. Public `#il`, invasion
  kill counters and public invasion clearing exclude these private encounters.
  Bellwatch's own remaining count is explicitly labeled; it does not impersonate `#ii`.
- Defeat returns the player to the refuge with their kit. Dead opponents stay
  dead; surviving boss health, remaining heal charges, summons and fired
  thresholds survive logout and restart. Enemy movement stays within its sector.
- Enemy pins follow the actual actor. The guide's walking destination is a free
  adjacent tile, so returning from the refuge does not request a path into the
  enemy's occupied square. Loot markers follow actual bags.
- Nesh replaces missing supplies and lost essential loot. A sentry killed before
  the ranged lesson can be retried. Full health cannot falsely satisfy potion use.
- Borrowed quantities are settled across inventory, equipment, storage and private
  bags on departure. Existing belongings are protected by an entry baseline;
  resuming refreshes that baseline for items acquired while away. Marketplace
  mutations and mixing require leaving first so loan materials cannot be exported.
- The cart remains at its boarding marker until departure. Gate lights show the
  safe road after the second bell. An old welcome popup cannot cover the adventure,
  and the guide moves beside the Ranging window.

## Files and regeneration

[`tools/build_bellwatch.py`](../../tools/build_bellwatch.py) builds the textured GLB,
manifest, target layout, client walk grid and authoritative server grid from one
layout. Outputs are in [`eloria-assets/maps/bellwatch`](../../eloria-assets/maps/bellwatch),
`dev-server/config/eloria/bellwatch.json` and `dev-server/tools/collision/bellwatch.escg.gz`.
The server wheel includes the quest layout.

The controller is [`dev-server/eloria/bell.py`](../../../dev-server/eloria/bell.py).
Client gate/prop presentation is [`bell_scene.gd`](../../godot-client/src/world/bell_scene.gd).
The existing guide packet 207 and UI packet 203 are capability-gated by
`second_bell_v1`; the client validates the additional counts and gate flags.
The reused bow GLB's image MIME type was corrected to JPEG without changing
its embedded image or mesh payload.

```powershell
python tools/build_bellwatch.py
```

Run that from `eloria-client`. Prepare the server's local terrain from `dev-server`:

```powershell
python tools/prepare_local_maps.py build/local-maps
```

## Verification

- Full server regression: **2,118 passed**, plus **498 subtests**.
- After the final encounter/recovery changes: **92 focused tests passed**, covering
  Bellwatch, The Last Lantern, the older walkthrough, bosses and flee behavior.
- After the ranging notification fix: **23 focused tests passed**, covering
  Bellwatch, ranging and interrupted flee handling.
- Native guide protocol: **33 checks passed**; the flee state test passes.
- Ranging window tests pass. A server wheel builds successfully and includes
  both the controller and Bellwatch layout.
- A separate rendered ranging probe confirmed the live window recorded one shot,
  one hit and eight experience after a real server-authorized attack. Successful
  hits now send the experience delta used by that window before the full stats snapshot.
- A rendered TCP playthrough completed all ten scenes, including real manual bag
  collection, flee, potion use, ranging, both captain endings, counters and return
  to Four Gates. It also resumed across client/server restarts with boss progress intact.
- Tests run against an isolated database and all 67 generated server terrain maps.
  Rendered automation uses 100 ms walking and 500 ms combat rounds to shorten QA;
  shipping timings are unchanged. Unit combat tests use faster rounds.

The checked-in client driver is
[`rendered_bell.gd`](../../godot-client/tests/integration/rendered_bell.gd).
It accepts `ELORIA_INTEGRATION_PORT` and `ELORIA_ARTIFACT_DIR` and logs in as an
ordinary `BellQA` test character. It advances through normal UI callbacks and
network requests, without writing quest progress or using privileged commands.
`tests/test_bell.py` covers both loot modes, private counts and permissions,
moving targets, locked gates, pause/resume, boss budgets, rewards, owned items,
full-health healing refusal and premature sentry defeat.

These checks establish completion and client integration. The storyboard's
six-player learning study and multiplayer facilitator session remain human
playtests; no claims about comprehension or public multiplayer readiness are made.
