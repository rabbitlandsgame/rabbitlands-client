# The Last Lantern: native client integration

Lantern Reach is now an opening adventure in the main Godot client and the
matching `dev-server` checkout. New characters enter a private island, complete
25 server-owned objectives across eight scenes, and sail into Four Gates with
their actual inventory, equipment and storage. The final objective is a real
conversation with Gate Warden Ilyon.

Run `prototypes/last-lantern/play.cmd`, click Connect, then New Character. The
launcher prepares local terrain, starts a loopback server on port 2008 and runs
`godot-client/project.godot`. It uses normal gameplay timings and a separate
`.local/native/characters.sqlite3` database. Closing the client stops its local
server. `-Fresh` creates another profile; it does not erase existing characters.
Existing characters on a matching server can opt in once with `#tutorial lantern`.
The original prototype's `project.godot` remains available for design reference.

## What is integrated

| Lesson | Native control | Completion evidence |
| --- | --- | --- |
| Movement | Ground clicks, camera drag/zoom | Server position reaches the displayed marker |
| NPCs | NPC dialogue options | Caldus accepts the request and grants ordinary inventory items |
| Map | Tab or Map toolbar button | Map window actually opens |
| Harvesting | Click Reed / Quartz in the viewport | Successful server harvests; tools and capacity apply |
| Storage | Store the finished Pickaxe; withdraw Torch supplies by category | Pickaxe stays stored; Reed and Quartz stay in the pack for the repair |
| Manufacturing | Torch recipe, quantity 1, Mix Now | The normal recipe produces a real Torch |
| Equipment | Inventory double-click or drag | Sword and shield occupy real equipment slots |
| Combat | Click the otter | Normal combat resolves its defeat |
| Loot | Ground bag, Get All / auto-gather | Real drops reach inventory |
| Food | Double-click Bread | An actual meal is consumed and food reaches 35 |
| Character growth | Statistics, Character, attribute +, confirmation | A pickpoint is spent by the server |
| Repair | Click the housing | Three Reed and one Quartz are consumed |
| Beacon | Click the housing while carrying the crafted Torch | The server lights the beacon and opens the return stair |
| Trading | Merchant Buy / Sell mode, item, quantity, Trade | Real meat sale and Bread purchase succeed |
| Departure | Click the boat, sail or boarding point and confirm sailing | Character changes to Four Gates; Ilyon completes the quest |

The guide highlights the existing control relevant to the current lesson. It
uses the native manufacturing side pane, fits beside storage and merchant
windows, and leaves the world clickable. Storage's inventory column now uses
server-provided item names, allowing instructions to identify Reed unambiguously.
The wooden shield's embedded JPEG is correctly labelled in its GLB metadata.

The cache stop follows directly from mining: deposit the Pickaxe, withdraw one
Wood Plank and one Cloth Roll from **Misc**, then one Hatchet from **Tools**.
Carry the three Reed and one Quartz straight to the lantern housing after the
combat and rest lessons. There is no required second cache visit. If repair
materials were stored voluntarily, the guide points to the upstairs cache and
names **Flowers** for Reed or **Minerals** for Quartz, with only the missing
quantity requested. The guide and journal return to the housing once the
materials are in the pack.

## Tutorial experience rewards

All tutorial bonuses use the normal green, rising and fading XP numbers above
the player. Skill rewards float by skill; only additional Overall XP floats
separately, so the matching Overall total is not repeated. Permanent rewards
earned in borrowed profiles also float without replacing practice stats.

Clients advertise `tutorial_rewards_v1`. The server then sends a stateless
`ELORIA_LANTERN_STATE` (207) event with `version: 1`, `event: "experience"`, a
boolean `permanent`, and `rewards: [{"skill": "magic", "amount": 40}, ...]`.
Amounts are awarded deltas, including the full Overall award, rather than
cumulative XP. The client validates the entire message before requesting the
existing floating feedback animation. These events neither replace the guide
nor count as Ranging hits. Older clients retain the chat announcement and stats
updates. Receipts are saved before sending feedback; guide refreshes and
previously rewarded lessons do not replay it.

Floating feedback verification (2026-09-10): 90 targeted server tests pass, along
with the tutorial XP feedback, tutorial protocol (56 checks), Ranging window and
skill-update client suites. The broader world-input test still reports two
spell availability/dimming failures; both reproduce using the unchanged HEAD
HUD script. The focused feedback tests cover simultaneous normal and bonus XP,
Overall suppression, borrowed stats, malformed messages and silent stats refreshes.

Completed milestones award these bonuses in addition to ordinary gameplay XP.
Skill bonuses also grant the same total to Overall. Each completion announces
the earned XP and updates levels and available pickpoints through the normal
stats notifications.

| Milestone | Skill XP | Overall XP |
| --- | --- | ---: |
| Reach Nesh, accept Caldus's supplies, read the chart | — | 20 each |
| Gather 3 Reed | 40 Harvesting | 40 |
| Mine 1 Quartz | 60 Harvesting | 60 |
| Store the Pickaxe | — | 25 |
| Finish collecting the Torch materials and Hatchet | — | 25 |
| Make the Torch | 100 Manufacturing | 100 |
| Finish equipping sword and shield | — | 25 |
| Defeat the otter | 90 Attack + 90 Defense | 180 |
| Collect the loot | — | 25 |
| Reach the rest landing | — | 20 |
| Eat and recover to 35 food | — | 30 |
| Spend two pickpoints | — | 30 |
| Repair the housing | 100 Engineering | 100 |
| Light the beacon | — | 100 |
| Return to the dock | — | 20 |
| Sell the meat, buy Bread | — | 40 each |
| Sail to Four Gates | — | 50 |
| Deliver the seal to Ilyon | — | 150 |

A full rescue awards **1,120 bonus Overall XP**, **100 Harvesting**,
**100 Manufacturing**, **100 Engineering**, **90 Attack** and **90 Defense**.
There are enough earned overall levels to fund the two-pickpoint lesson before
it appears. Opening the map and the intermediate withdrawal/equipment prompts
have no separate bonus; rewards belong to the completed lesson.

The checkpoint, XP and per-milestone receipt are saved together before network
notifications. Repeated actions, reconnects, recovery requests and skipping do
not duplicate or grant unearned bonuses. Existing saves continue earning bonuses
from their current lesson onward; completed lessons receive no retroactive XP.
The old 180 Overall XP combat receipt counts as an already-paid combat reward.

Ilyon's final handoff also awards a complete starter armor set, one of each:

| Slot | Item | Armor | Defense | Weight |
|---|---|---|---|---|
| Head | Buckled Hood | 1–5 | −1 | 8 EMU |
| Torso | Scout Vest | 2–8 | −1 | 8 EMU |
| Legs | Sidelace Breeches | 1–6 | −1 | 8 EMU |
| Feet | Laced Fieldboots | 1–3 | 0 | 8 EMU |

All four pieces are beginner-equippable. They arrive in Inventory with equip
instructions. Pieces that exceed the available slots or carrying capacity go to
Storage's **Armor** category. Separate messages name exactly which pieces went
to the pack and which went to Storage, with withdrawal guidance for stored gear.
The item reward, completion state and one-time receipt are saved together.
Skipping, reconnecting, repeating the handoff or reloading an already completed
tutorial cannot grant another set. Existing completed saves are not backfilled.

## Boat interaction

The saved boat's hull and both faces of its sail share the server's boarding
action. The door cursor appears once the boat is docked and the server's guide
reaches departure; the original boarding point remains usable. Earlier lesson
states and the arriving boat do not offer the map-change cursor. Alt inspects
the boarding object, and sailing still uses the native confirmation.

## State and map ownership

- `dev-server/eloria/lantern.py` defines the sequence and listens to ordinary
  gameplay outcomes. `last_lantern` and `lantern_*` quest fields are persisted
  with the character. The client cannot grant items or advance gameplay lessons.
- Capability `lantern_tutorial_v1` enables server packet 207, a validated JSON
  guide snapshot. Client packet 203 accepts only map-opened, skip-request and
  refresh actions. Skip and sailing use the existing popup protocol.
- `eloria-assets/maps/lantern-reach/` is registered as `lantern_reach`. Its native
  world loader, actors, resource objects, picking, markers and equipment remain
  in charge of presentation. `lantern_scene.gd` adds water, gates, lights and boat
  motion; it contains no local quest simulation.
- The server clones the template for each owner. Other characters cannot enter
  that copy. Gate collision is reconstructed from saved facts, using the authored
  120 × 120 grid in `config/eloria/lantern_reach.json`.
- Object IDs and approach tiles come from the authored layout. Loot markers use
  the actual bag location. Arrival checks use the marker's approach coordinate.
- The optional manifest `asset.mapBounds` frames the playable island on the
  full map, while `asset.bounds` still describes its large ocean backdrop.

Reconnect restores the stage, gates and belongings. Supplies held in inventory,
equipment, storage or a dropped bag are not duplicated. Caldus and the bench
recover missing essentials after loss or crafting failure. A novice defeat keeps
the kit and resets the otter; a defeated otter does not respawn. Global days that
prohibit harvesting, mixing, food or combat cannot block the private rescue.

`lantern_flow_version` records the revised sequence. Login maps all 28 original
stage numbers to the corresponding current lesson without changing belongings,
earned progress or completion rewards. Old upstairs withdrawal saves resume at
the repair lesson with category-specific recovery instructions. Finished and
skipped saves stay finished.

The causeway encounter is a level-1 Mirrorfin Otter named "Storm-frightened
otter", rendered with the updated `river_otter.glb` model (actor type 400).
It keeps the novice combat stats and guaranteed Raw Meat drop for the trading
lesson. The internal `lantern_boar` species and `boar` marker IDs remain stable
for the existing encounter hooks and authored target references.

The template is intentionally absent from the public portal and invasion graphs
and from required public exploration totals. Existing quest progress is preserved
when a character opts in; the old opening walkthrough is suppressed for new
characters that finish or skip this opening adventure.

## Verification

Experience rewards verified on 2026-09-10: **112 targeted server tests pass**
against the current develop XP curve (66 tutorial/reward tests and 46 return,
experience and XP-migration tests). All four full rescue playthroughs earn every
milestone bonus. The reward tests also pass in the local development checkout.
Walking and running delays are disabled in the tutorial test fixture; real
pathfinding, collision, inventory transfers, crafting and combat handlers remain
in use.

Storage-flow revision verified on 2026-09-10: **85 targeted server tests pass**,
including all four full rescue playthroughs, saved-stage migration, tutorial
returns and storage behavior. The final partial-withdrawal and voluntary-deposit
refresh checks also pass. Godot's tutorial protocol reports **56 checks, zero
failures**, and the storage organizer tests pass. The rendered playthrough script
now follows the revised route and named categories and passes Godot's syntax
check; the full rendered run has not been repeated for this revision.

Earlier baseline, verified locally on 2026-09-09: **2,112 server tests and 498 subtests pass**;
the complete 28-objective rendered native-client playthrough passes, including
Four Gates and Ilyon; all 25 tutorial protocol checks and the storage regression
checks pass. The rendered run also verifies real object picking and that the
highlighted Mix Now button and manufacturing window remain on screen. A separate
rendered map check passes with the island framing and smaller marker discs.

- `dev-server/tests/test_lantern.py`: complete real-handler playthroughs with and
  without auto-gather and early equipment, persistence, private-copy isolation,
  defeat, crafting recovery, lost loot, older-character opt-in and marker arrivals.
- `dev-server/tests/test_lantern_rewards.py`: reward totals, skill/Overall level
  updates, caps, persistence before notification, early and previously paid kills,
  and protection against duplicate or unearned XP.
- `godot-client/tests/integration/rendered_lantern.gd`: creates a real character
  over a loopback connection, uses native UI callbacks and viewport picking,
  completes the entire rescue, and captures each lesson window. Craft failures
  are recovered through the actual cache and manufacturing controls.
- `godot-client/tests/test_lantern_protocol.gd`: 25 packet validation checks.
- `godot-client/tests/test_boat_portals.gd`: authored hull and both sail faces
  through native cursor/click rays, exact boarding requests, availability,
  reconnect and object-removal checks. The server's
  `test_boat_boarding_requires_departure_and_confirmation` checks the crossing
  and preservation of inventory, storage and equipment.
- `godot-client/tests/test_storage_organizer.gd`: native storage regression checks.
- The launcher was exercised with the real server and a headless client; local
  terrain preparation and server shutdown completed successfully.

The broader client protocol test currently has two existing failures: the missing
`magic_book_v2` capability fixture and a walk/run facing assertion. Both also
reproduce using the repository's HEAD protocol and HEAD test, independently of
these tutorial changes. Dedicated tutorial and storage checks pass.

Client and server changes must be installed together. This implementation has
been tested locally; this work does not deploy or push a live server.
