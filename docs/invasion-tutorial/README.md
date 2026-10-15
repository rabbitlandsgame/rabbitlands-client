# The Second Bell

## Invasion tutorial storyboard

**Design draft · 9 September 2026 · Native Eloria client · Solo · 30–40 minutes**

[Open the visual storyboard](storyboard.html). The native client implementation
is now playable; see [implementation, launch instructions and verification](implementation.md).
This document preserves the design and human playtest plan. Mechanics were checked
against the client and `dev-server` source. Times and learning targets below remain
hypotheses for human testing.

After **The Last Lantern**, Ilyon sends the player to Bellwatch, a small outpost
with four gates. The first bell warned the nearby farms. The second bell means
the road is safe enough for the last supply cart to leave. An invasion reaches
the outpost before that bell can ring.

**Ilyon:** “You brought a boat home. Help me bring these people through.”

The player scouts a breach, survives an encounter, learns when to withdraw,
recognizes reinforcements, breaks a captain's warband and clears the departure
road. The cart and changing gate lights make progress visible. Nesh supplies
short, contextual advice; the player performs every fight, retreat, inventory
action and interaction through the normal client.

The learning rhythm is **show once → practice with help → apply without a prompt**.
There is no countdown during a first attempt, no required multiplayer partner,
and no dialogue answer that substitutes for doing a gameplay lesson.

## The four-gate map

**144 × 144 one-metre tiles**, with a central refuge and four short encounter
pockets. Each pocket should fit within a useful camera view; walks between
lessons should take about 10–20 seconds. These are layout intentions, not
validated collision coordinates.

```text
                         NORTH · Orchard Gate
                         Scout → first contact
                                  │
                                  │
 WEST · Road Gate ─────── BELL COURT ─────── EAST · Mill Gate
 Arrival / final road    Nesh · supplies    Retreat → reinforcements
                                  │
                                  │
                         SOUTH · Muster Gate
                         Captain → warband breaks
```

| Place | Staging and camera composition | Why it exists |
| --- | --- | --- |
| Bell Court | Warm lantern, Nesh, storekeeper, bell and waiting cart; no hostile spawn points | A recognizable refuge, recovery point and checkpoint between lessons |
| West / Road Gate | Wagon silhouettes beyond an arch; initially only the arrival lane is accessible | Establish the rescue, then reuse a familiar place for independent play |
| North / Orchard Gate | A lookout before a bend; ordinary wildlife in a separate pen, red-named invaders beyond | Identify threats and choose an approach before first contact |
| East / Mill Gate | Wide retreat lane, supply alcove and an observable breach beyond it | Experience disengagement and the difference between a lull and completion |
| South / Muster Gate | Large court with several walkable routes, visible captain and followers | Read boss size, equipment, healing, summons and group dispersal |

The North gate opens after preparation; East after first contact; South after
the reinforcement lesson; the West departure lane after the captain falls.
Unlocked return routes stay available. Gates govern actual pathfinding, not
just their appearance. The refuge needs a real server-enforced boundary and
enough separation to prevent ranged attacks or summons crossing into it.

Keep roofs, smoke and vegetation away from clickable actors and approach tiles.
Use one persistent objective and one active marker, visible both on the map and
in the 3D viewport. Enemy targets follow their live actor positions. Bags use
their actual drop coordinates. Reaching a location replaces the movement
instruction with the next action immediately; it never leaves a blank guide.

## Ten storyboard frames

### 01 · The first bell — arrival and orientation · 2 minutes

**Picture:** The camera starts behind the player's arrival wagon. The bell
tower is visible through the West arch. An empty space in the cart waits for
the outpost's remaining supplies. A short local alarm appears in normal chat.

**Nesh:** “North orchard. Red names beyond the fence. Find our lookout first.”

**Play:** Walk to Ilyon's approach marker and accept the rescue using NPC
dialogue. Open Map with **Tab**, locate North and identify Bell Court as the
return point. Focus chat with **T**, submit **`#il`**, and read the real response.
The guide explains: “That counts public invaders across the server. Our private
training encounter has its own progress.” Introduce **Statistics → Counters**
as the place to revisit personal totals; do not claim `#il` is personal or local.

**Evidence:** Accepted quest, server position at the lookout approach, map-open
UI event and successful command response. Reading comprehension is checked
later through behavior and the facilitator's debrief, not a fake server flag.

**Recovery / playtest:** Close chat and map early, reopen them, then reconnect.
The North destination must still be visible. Ask an uncoached tester to show
where they would retreat; opening Map alone does not prove that they understood it.

### 02 · Leave room to come home — preparation · 3 minutes

**Picture:** A lit supply alcove faces the cold North arch. Equipment is visible
on the player; the cart remains in view behind them.

**Nesh:** “A shield, a drink, and room for what you bring back.”

**Play:** Use the real Storage window to leave a bulky supply bundle behind.
Withdraw the issued **Potion of Minor Healing** and food. Open Inventory with
**Ctrl+I**, equip a suitable weapon and shield, and check the load and health
meters. Existing suitable equipment counts immediately. Players retain their
build; a loan kit fills missing essentials.

**Evidence:** Actual inventory/storage transfers, equipped slots and enough
capacity for the authored minimum loot. No progression for merely opening
Inventory or hovering the right item. North opens when the kit is usable.

**Recovery / playtest:** Test a full inventory, materials already in storage,
items dropped in a bag and equipment worn before acceptance. The quartermaster
recovers genuinely missing essentials without duplicating belongings. Verify a
tester can name and locate the healing item before entering combat.

### 03 · Not every creature is the same — first contact · 3 minutes

**Picture:** Ordinary wildlife is visible behind the lookout fence. One
red-named invader wanders on the reachable orchard path. Its position changes;
the objective marker stays attached to it.

**Nesh:** “That one came with the raid. Watch its path. Take it where you have room.”

**Play:** Observe the invader, walk to an open approach and click it to fight
through normal targeting and combat. Watch both health bars. Collect the real
drop with the ground-bag window, or let an enabled auto-gather setting collect
it. Candidates are an existing low-tier Bilge Rat or Mossbound Hound, selected
after normal-timing combat tests with a post-Lantern character.

**Evidence:** Server-owned defeat of the tagged lesson actor and an actual
inventory receipt from its bag. Ordinary wildlife kills cannot satisfy it.

**Recovery / playtest:** A wandering invader can stop nearby movement and attack
at reach even though pursuit is off by default. Do not write “it will chase you”
or make the lesson depend on it doing so. If the player dies or the bag expires,
restore the encounter or the required recovery item and show the next action.
Test manual loot and auto-gather separately; a vanished bag can mean success.

### 04 · Coming back is part of fighting — retreat and recovery · 4 minutes

**Picture:** At the East gate, a second invader enters the player's peripheral
view. The lit return lane remains unobstructed behind them.

**Nesh:** “Two now. Come back while you can still choose.”

**Play:** Engage the first opponent. A small second opponent creates manageable
pressure. Click clear ground toward the refuge to request the **normal flee
action**. If it fails, read the message and try again after the combat round.
Once safely out, double-click Potion of Minor Healing in Inventory and watch
health rise. It currently heals 10 and has a four-second cooldown. Use food as
needed; food and an immediate healing potion are not interchangeable lessons.
Return and finish the encounter when ready.

**Evidence:** A real engagement, a successful server flee, arrival in refuge,
an actual potion consumption that restores health, and the encounter resolved.
Do not award retreat for an unengaged walk. If no damage was taken, accept a
previous demonstrated heal or offer a short spar before departure; never make
the player waste a potion at full health.

**Recovery / playtest:** Trigger advice with a generous health margin established
by testing. Failed flee attempts spend a combat round; repeated ground clicks
are not a guaranteed escape. A private rescue checkpoint prevents inventory
loss from ending the lesson, and its protection must be stated as training-only.
Test both a real failed flee and a successful retry using the server path.

### 05 · A quiet lane is not a finished invasion — reinforcements · 4 minutes

**Picture:** The East breach becomes quiet after two enemies fall. Before the
cart moves, fresh red names appear beyond the fence. The instruction changes
from fighting to assessing the lane.

**Nesh:** “A wave is down. The breach is still feeding it.”

**Play:** Clear a small one-shot group, watch the next group arrive, and decide
to return for supplies before re-entering. Fight the second group, then walk to
and click the breach winch. The winch closes the authored reinforcement source
and opens South. The player experiences **kill → lull → renewed danger → stop
the source**, with no arbitrary demand to kill the same five enemies forever.

**Evidence:** Both distinct groups defeated and the server accepts the winch
interaction at its real approach tile. A zero remaining count during the lull
does not complete the scene. Two finite activations make this lesson reliable.

**Recovery / playtest:** The winch is a **new quest interaction**, not an existing
universal way to end invasions. Its caption says “Close this breach.” Explain
that public invasions may receive further waves or respawns and that the
organizer's all-clear matters. Test the arrival of a new wave while Map or
Inventory is open; retain health, visible enemies and a usable retreat route.

### 06 · A shot is an invitation — ranged retaliation · 3 minutes

**Picture:** From the South staging lane, one separated sentry is visible with
a clear path toward the player. Other enemies remain behind a closed inner gate.

**Nesh:** “Distance buys you time. It doesn't make you unseen.”

**Play:** Equip a novice-usable bow and matching ammunition through Inventory;
use normal attack targeting to fire at the sentry. Observe it approach in
retaliation, then change back to the melee kit and resolve the encounter, or
retreat and re-engage. Open **Ranging, Ctrl+T**, to see shots and hits. Missing
an arrow is a normal outcome; supplies allow retries.

**Evidence:** A server-resolved ranged attack, observed retaliation against its
attacker when a reachable path exists, and the encounter safely resolved. A
shot animation or an open ranging window cannot award the combat lesson.

**Recovery / playtest:** Validate bow requirements, ammunition, slot conflicts,
range and unobstructed retaliation with a fresh character. The Ranging panel
is a session tally and its critical-rate field is unavailable; do not invent a
critical lesson. If low-level bow access requires new content, ship that content
before this scene is enabled. Do not silently grant a skill increase.

### 07 · Find the one holding them together — read the captain · 2 minutes

**Picture:** The inner South gate reveals a visibly larger, named captain with
an authored weapon loadout and a few followers gathered around it. The player
can inspect the court from outside engagement range.

**Nesh:** “Look at the weapons. Look at the size. Then choose your way in.”

**Play:** Rotate the camera to read the captain, clear one isolated follower
and approach through the open lane. Verify supplies before committing. Seeing
the boss changes the objective to preparation/engagement; standing on its old
spawn marker never counts as defeating it.

**Evidence:** The player engages the correct boss after reaching an accessible
approach. Observation of size, equipment and group behavior is checked in the
playtest and independently again in frame 09.

**Recovery / playtest:** A boss-enabled group currently spawns its first boss
on its first processing pass, not after a guaranteed kill quota. Activate the
group only when this scene is ready. No hidden “kill all followers to summon
boss” rule. The first captain uses fixed strength for consistent learning.

### 08 · The captain answers back — healing, summons and dispersal · 5 minutes

**Picture:** The captain's health recovers after a landed hit. Later, small
reinforcements appear at its feet. When it falls, surviving members of this
warband disappear through the real group-dispersal behavior; the South lamps turn warm.

**Nesh, on the first actual heal:** “It has remedies too. Those will run out.”

**Nesh, on the first actual summon:** “More at its feet. Make room, then finish it.”

**Play:** Fight a novice **Mire Goblin** captain, using the ordinary
boss response system. Starting tuning: three small healing charges and two
single-creature summon stages near 65% and 30% health; final values depend on
measured novice damage. Change targets to relieve pressure, heal or retreat as
needed, then defeat the captain. Native auto-retargeting may help when another
aggressor is active; it does not make the remaining court safe automatically.

**Evidence:** At least one real boss heal and summon occur during the encounter,
the boss is defeated through gameplay, its surviving group disperses, and
combat locks are cleared. The guide reacts to actual outcomes; it never moves
health bars, fakes a summon, or marks all followers as player kills.

**Recovery / playtest:** Boss healing is finite and responds to landed blows;
waiting alone does not exhaust it. Summons fire once per threshold, after the
healing response, with a finite budget. Tune health and damage so a novice sees
these behaviors without a prolonged stalemate. Powerful returning characters
may skip this introduction or use an explicitly separate rehearsal character;
do not secretly weaken their equipment or require impossible observations after
they have already killed the boss. Dispersal is removal today, not a routed
enemy animation; any running-away animation would be additional presentation.

### 09 · The road without a voice — independent application · 5 minutes

**Picture:** The West departure lane opens. A second captain blocks the cart:
the same recognizable **Mire Goblin**, now a larger captain. Nesh stays
with the cart. Only the destination and “Clear the departure road” remain.

**Nesh:** “I'll stay with them. You know what to look for.”

**Play:** Prepare, assess the stronger captain, choose an approach, fight,
recover when necessary and collect loot. Use a fixed strength roll of **1.15**
for this first comparison, which currently earns the “Great” epithet; tune the
base encounter so it is still novice-completable. This group has dispersal
disabled and contains a weak survivor. The player must notice that the road is
not clear just because its boss died and deal with the remaining threat.

**Evidence:** Captain and all remaining actors in the departure group resolved;
no reinforcements scheduled for this route; the player reaches the cart's safe
approach. Server evidence evaluates the result, not a prescribed click order.
A successful alternative strategy counts. If all followers died first, accept
the clear and use a later replay variant to assess survivor recognition.

**Recovery / playtest:** Do not spawn a new wave under a looting player or remove
supplies to force mistakes. The checkpoint remains available. Extra instruction
is offered after inactivity or repeated failures; using it completes the story
but records **assisted**, rather than pretending independent mastery occurred.
The larger captain demonstrates a strength roll; public bosses can vary in
health, attack/defense, damage, healing amount and drawn size. This is not a
promise that the same name always has the same difficulty.

### 10 · The second bell — reward and public handoff · 2 minutes

**Picture:** The player rings the real bell interactive. The cart leaves through
West in a short in-world presentation. The camera stays under player control.

**Ilyon:** “You cleared a road, not the whole world. Listen for the next call.”

**Play:** Finish collecting available loot with the ordinary bag controls,
return borrowed supplies through the quartermaster interaction, and ring the
bell. Open **Ctrl+A → Counters** and compare personal totals with the entry
baseline. Submit `#il` again: public invaders may remain even though Bellwatch
is safe. Use native NPC dialogue to return to Four Gates.

**Evidence:** Departure group resolved, server accepts bell use, one-time quest
reward recorded, and actual map transition. The journal records the completed
story and whether independent practice was assisted. Closing the guide neither
awards completion nor loses the return destination.

**Reward:** Proposed one-time modest supply reward and journal entry; exact
items should use the existing economy budget. Replays give practice, not an
unlimited supply farm. Private encounters do not inflate public invasion kill
totals. The debrief explicitly explains this rather than displaying invented
counter increases.

**Public handoff:** “Read the announced map and intended strength. Bring supplies,
find the regroup point, and ask for help if the group is too strong.” Public
cooperation needs a separate multiplayer test; an NPC companion cannot establish
that a player knows how to coordinate with real people.

## Feature coverage and what is already real

“New” below means content or integration still required for this storyboard.
It does not mean the underlying combat action should be simulated.

| Invasion feature | Hands-on lesson | Current behavior / design boundary |
| --- | --- | --- |
| Alerts, location and readiness | 01–02: normal chat, Map and equipment | Public announcements can be sent by an organizer. A private alarm and persistent lesson guide are new |
| Red names and hostility | 03: pick and fight the invader | Red invasion name prefix exists. Normal creatures can also be dangerous; do not teach “non-red means safe” |
| Wander, spatial spread and engagement | 03–04: observe, approach, retreat | Served pursuit defaults off; close detection can stop movement; adjacent enemies still attack. Unbounded groups can roam across a map |
| Flee, failed attempts and recovery | 04: click ground while engaged, heal, return | Native flee can fail and costs a round. Private rescue protection is new, not a public death rule |
| Ranged retaliation | 06: fire, respond to approach | Ranged aggressors can be pursued even when ordinary invasion pursuit is off |
| Multiple aggressors and target changes | 04, 08–09: relieve pressure | Actual combat targets and auto-retargeting exist; teach the player to watch surviving enemies |
| Waves, one-shot groups and respawns | 05: experience a lull and renewed danger | Assistant-created groups default to one-shot. Authored respawn settings vary. The breach switch and finite sequence are new |
| Boss arrival and followers | 07: scout an active warband | First boss is scheduled immediately; existing followers gather around its region. No universal “kill X to unlock boss” rule |
| Boss strength, names, size and equipment | 07 vs 09: reassess a familiar opponent | Strength roll and epithets are real. Authored gear can add stats and effects, including multiple weapons |
| Limited boss healing | 08: sustain an actual fight | Charged healing responds to hits; it is not a timed regeneration phase |
| Health-triggered reinforcements | 08: react to adds | Finite budget, one firing per health threshold. New novice boss data needed |
| Boss death and optional dispersal | 08 vs 09: two different all-clear decisions | Dispersal is configurable; summoned adds belong to cleanup. Removal does not award their kills or loot |
| Drops, capacity and auto-gather | 02–03, 10: make room, collect | Real bags, expiry and inventory capacity apply. Random rare drops never gate the quest |
| Remaining count versus personal totals | 01, 10: `#il` and Counters | `#il` counts live public invasion actors across maps, excluding `instance_name`; public invasion kills/boss kills also exclude those actors |
| Reconnect, defeat and an unfinished invasion | All frames: resume or retry | Durable tutorial checkpoints, scoped actor restoration and supply recovery must be added for this quest |
| Organizer tools and difficulty composition | Facilitator track below | Invasion Assistant is privileged; normal players must not receive its powers |

No ordinary-invasion A/D admission cap, automatic matchmaking, shared reward
guarantee or public boss timer was established by this audit. Do not invent them
in dialogue. Gauntlets have their own entry, scaling, gates and reward lifecycle;
territory raids have opt-in teams and capture/effects; specialty events can wrap
invasions in timed objectives. Those are adjacent modes, suitable for later
chapters rather than silently treated as universal invasion rules here.

## Facilitator track: stage it, play it, verify it

An optional **15–20 minute local rehearsal** teaches invasion masters the tools
and gives designers control over playtest cases. It uses a dedicated local
server, an authorized organizer account and an ordinary player account. The
player account stays ordinary throughout. This is separate from the story.

| Exercise | Real organizer action | What the ordinary player must experience / what to verify |
| --- | --- | --- |
| Survey | Open `#invasion_assistant`; Maps, select map, inspect player/invader/boss markers, refresh, stage and use Teleport | Live positions agree with the world. The tactical map is an organizer view, not a player radar |
| Build | Groups → duplicate a read-only authored group or Create group; Monsters → inspect rating, gear-relevant stats and model status; add/remove a small quantity at chosen coordinates | A practical novice fight, not only a plausible numeric strength rating. “Updated models only” helps inspect presentation; placeholders are marked |
| Configure | Save group name, map, min/max quantity, health multiplier and optional boss; open its map | Selected composition lands on reachable distinct tiles and does not block exits. Health multiplier alone does not scale every combat stat |
| Activate | Spawn selected group; try the quick “Spawn X monsters at my location” action in a separate test | Correct quantities, native hostility, visible nameplates and accurate refreshed live counts |
| Compare persistence | Inspect group respawn summary; on a temporary bossless test group use `#set_spawn <group> auto_respawn -1`, then a positive window, then `0` in separate runs | One-shot stays cleared; positive values bound the respawn window; zero is unbounded. It is a window, not “spawn every N minutes.” Observe actual upkeep cadence |
| Boss variants | Use authored tutorial definitions for fixed/strong rolls, healing, summon thresholds, gear and dispersal on/off | Native boss responses occur and match each lesson. The GUI does not expose every boss field. Advanced values need authored data, not invented UI controls |
| Announce and inspect | Send a local-test broadcast via `#bc`; use `#show_spawn`, `#im_stats`/`#ilim` as appropriate | Real alarm reaches chat, player can find the map, counts and combat condition are comprehensible |
| Recover and finish | Clear active group; verify actors/aggressors disappear; delete only after clearing; optionally test dump/export | No stranded models, combat locks or summons. Dynamic groups are process-local; verify exported fields before relying on persistence |

Use scoped group clearing for rehearsal cleanup; do not clear unrelated public
invasions. Test `#god_storage` and demigod only as organizer conveniences, with
an explicit check that the playtest participant has neither. Privileged state
must be rejected when requested by the ordinary account.

## Implementation contracts for a playable version

1. **Reuse the native tutorial approach.** Extend the server-owned guide pattern
   from `lantern.py` and the native guide overlay. New quest IDs, authored map,
   targets and boss definitions are required. The existing Last Lantern guide
   is not already a generic invasion quest engine.
2. **Isolate the run.** Clone Bellwatch per owner and use run-scoped group keys.
   Mark its invasion actors with an `instance_name` so current public invasion
   totals and cleanup exclude them. Add a private remaining/pending-wave count
   to the tutorial snapshot. This label must say “Bellwatch,” never impersonate
   `#il`. Do not call `#ii` unless the run is actually registered with the
   instance service; a tag alone does not register an active instance.
3. **Own the lifecycle.** Finite waves are separate one-shot activations under
   the tutorial controller. Persist stage, phase, surviving encounter facts,
   issued/recovered supplies and reward receipt. Resume idempotently after
   reconnect or server restart; do not resurrect a completed boss or duplicate
   a bag. An empty actor list with a pending wave is not a completed invasion.
4. **Give every interaction a usable target.** One authored target record owns
   its map, object/actor/bag ID and reachable approach. Resolve spawned actors'
   actual positions after collision displacement. Verify every gate state with
   pathfinding and native viewport picking, including large boss footprints.
5. **Make recovery explicit.** Provide checkpoint restart and a leave/return
   option through native dialogue, restoring only this run's essentials. Keep
   real item transactions, damage, cooldowns and flee rules. Disable obstructive
   special-day rules only within the private lesson; current public rules may
   prohibit combat, food or fleeing. Never change the global day for a tutorial.
6. **Observe outcomes.** Listen to attack/kill, flee, heal, transfer, bag pickup,
   boss-response, group-dispersal and interactive outcomes. UI-open events prove
   UI use only. Record assistance separately from completion; have the server
   emit the next instruction and target together at each transition.

The supply cart, lamp transitions, bell response, shelter boundary, private
alarm and winch are new story content. They can use ordinary world interactives
and presentation, but must not be described as invasion features that already
exist. No unimplemented escort AI, threat/taunt ability, interrupt, dodge roll,
revive spell or cooperative loot rule is required to finish this design.

## Playtest plan and release criteria

### First session: can a new player learn it?

Recruit **six players unfamiliar with invasions** for an initial formative round.
Use fresh post-Lantern characters, normal server timing and the actual main
client. Capture screen, server outcomes and hints shown. Ask them to think aloud;
the facilitator does not give controls until help is requested or the player
has clearly stalled. Count facilitator instructions as assistance.

For each frame record time to first useful action, completion time, wrong-target
clicks, marker searches, deaths, flee attempts/results, healing at useful health,
loot problems and hint escalation. After a failure ask “What did you expect?”
Avoid teaching the answer in the question.

### Second session: did the lesson transfer?

Replay frame 09 with the entry side and enemy positions changed. Keep encounters
within the tested novice band. Include one dispersing and one non-dispersing
boss across the test cohort, and run a separate group with a pending wave.
Do not display mechanical prompts initially. The player should prepare, assess
the changed boss, recover when necessary, check survivors and wait for the real
route-clear condition. Reward a successful strategy even if it differs from
the authored demonstration; do not force damage just to tick “used potion.”

Afterward ask players to explain why a count may rise again, why a boss's health
rose, why remaining enemies sometimes disappear, what a larger familiar boss
suggests, and why `#il` need not read zero. Pair answers with observed behavior;
a memorized line by itself is not mastery.

### Completion audit: make every stage recoverable

| Test case | Required result |
| --- | --- |
| Restart/reconnect before and after each transition, including boss heal/summon/dispersal | Exact checkpoint and next instruction; no duplicate wave, kit, credit or reward |
| Walk/map-click every closed gate and approach every interaction from each legal side | No bypass or unreachable marker; viewport pick hits the intended object |
| Enemy wanders or is displaced at spawn; bag drops away from the authored point | Markers follow actual live targets; no obsolete coordinates |
| No spare weight, full slots, pre-equipped kit, missing bow/ammo, expired bag, lost potion | Actionable recovery and successful retry without creating unlimited supplies |
| Flee succeeds, fails once, fails repeatedly; death during each encounter | Normal feedback; recoverable checkpoint; no stranded combat/movement state |
| Boss heals across a threshold, crosses multiple thresholds, dies before a threshold | Actual ordering respected, bounded summons, no impossible “observe” gate after a legitimate victory |
| Auto-gather on/off, changed HUD layout, small window, color-vision differences, audio muted | Required targets/health/controls remain readable; instructions use names/shapes as well as color/audio |
| Two owners run simultaneously; one leaves, another restarts | No shared gates, enemies, bags or quest progress; independent cleanup |
| Other public invasion remains active while Bellwatch is cleared | Public `#il` remains truthful; private success ignores unrelated actors |
| Ordinary account requests assistant commands; organizer refresh/clear during local rehearsal | Permission rejected for player; organizer changes leave no stale actors or combat locks |
| First-time novice versus high-level returning character | First run exposes mechanics; high-level victory never softlocks observation objectives |

### Initial acceptance targets

- All ten scenes and recovery cases can finish without privileged intervention.
- At least **5 of 6** first-time testers finish the story without facilitator
  control instructions; at least **4 of 6** complete the changed final encounter
  without additional mechanical prompts. These small-sample targets guide
  iteration; they are not statistical proof of learning.
- No tester spends over **30 seconds searching an already-revealed required
  target** because its marker is wrong, hidden or missing. Reading and tactical
  observation time are measured separately.
- At least 5 of 6 can demonstrate retreat/recovery and distinguish a cleared
  local encounter from the public remaining count using play plus debrief.
- No permanent progression block, inventory loss caused by training recovery,
  duplicate completion reward or interference with another run/public invasion.

Do an additional small multiplayer session on an isolated test server before
claiming public readiness: two ordinary players read a real announcement, agree
on a regroup point through normal chat, handle simultaneous aggression and
inspect actual loot/counter attribution. Do not assume a solo scene validates
shared kill credit or team coordination.

## Source audit

Paths below are relative to this folder. Code takes precedence over older prose;
some README descriptions and command-help labels are stale. For example, the
current `#lb` handler lists nearby bags, despite a help label calling it a
leaderboard. This storyboard therefore does not teach a leaderboard command.

| Source | What it establishes |
| --- | --- |
| [Last Lantern integration](../last-lantern-integration.md) | Native scene/guide style, real-action completion and recovery precedent |
| [Client controls](../../godot-client/project.godot) and [main client](../../godot-client/src/app/main.gd) | Map, chat, inventory, statistics, ranging and world targeting |
| [Ranging window](../../godot-client/src/ui/ranging_window.gd) | Real shot/session measurements and unavailable critical rate |
| [Invasion Assistant UI](../../godot-client/src/ui/invasion_assistant.gd) | Maps, group builder, monsters, privileged operational controls |
| [Server world](../../../dev-server/eloria/world.py) | Spawn groups, boss response/strength/dispersal, flee, actor AI, drops and public totals |
| [Chat handlers](../../../dev-server/eloria/server.py) and [IM commands](../../../dev-server/eloria/im_commands.py) | `#il`, `#ii`, permissions, broadcasts, temporary groups and operational commands |
| [Spawn definitions](../../../dev-server/eloria/spawn_groups.py) | Respawn window semantics, quantity scaling, boss fields and instance distinctions |
| [Boss content](../../../dev-server/config/eloria/spawn_groups/invasion/bosses.def) | Actual authored gear, healing and summon budgets |
| [Settings](../../../dev-server/eloria/settings.py), [served settings](../../../dev-server/config/eloria/server.txt), [potions](../../../dev-server/eloria/potions.py) | Pursuit default, flee behavior and recovery item values |
| [Wander tests](../../../dev-server/tests/test_invasion_wander.py), [spread tests](../../../dev-server/tests/test_invasion_spread.py), [boss tests](../../../dev-server/tests/test_boss_fight.py) | Behavioral evidence for the lesson assumptions |
| [Gauntlets](../../../dev-server/eloria/gauntlets.py), [territory raids](../../../dev-server/eloria/territory_raids.py), [specialty events](../../../dev-server/docs/special-events.md) | Adjacent systems with distinct lifecycles |

The automated completion and rendered-client results are recorded in
[implementation.md](implementation.md). The human learning study above remains
separate from those engineering checks.
