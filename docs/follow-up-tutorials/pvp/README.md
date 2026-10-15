# The Chalk Circle

**PvP storyboard · Proposal · Solo 30–40 minutes · Optional spar 10–15 minutes · Ten core frames**

[Illustrated storyboard](storyboard.html) · [Collection](../README.md) · [Shared contract](../design-contract.md)

At **Chalkwatch Yard**, steward **Vale** prepares volunteer road wardens for encounters with hostile players. The player rehearses against **Rook, practice rival**, a clearly scripted player session. The story is about reading the ground, choosing an engagement, surviving it and leaving with a plan. Winning every bout is unnecessary.

**Vale:** “First learn where a fight can begin. Then learn how to leave one.”

The rival follows ordinary player combat, equipment, spell and zone rules. Training opt-in is an entry agreement for this private exercise; the tutorial must not imply that public PK areas ask for mutual duel confirmation before every attack.

## Access and four-gate map

Offer only as an optional follow-up after basic combat, near a PK boundary or steward. Use a separate practice profile, disposable equipment/coins and private rival. Make the refuge and no-drop sparring conditions explicit. Completion does not require entering a public PK map, losing permanent items or sending an invitation to a stranger.

Propose **128 × 128 tiles**. Chalk Court (64,64) is a non-PK briefing refuge; North (64,101) is the Boundary Walk, East (103,64) the Measured Ring, South (64,27) the Retreat Yard and West (25,64) the Open Choice. Zone bounds are authoritative rectangles/areas registered for the practice map, not decorative circles alone.

| Gate | Composition | Purpose |
| --- | --- | --- |
| North · Boundary Walk | Clear inside/outside tiles and named rule signs | Shared-zone eligibility and truthful feedback |
| East · Measured Ring | No-drop single-combat ring with visible A/D cap | Actual player combat and limited normalization |
| South · Retreat Yard | Broad lane, second rival alcove and safe exit path | Flee, positioning and multi-combat |
| West · Open Choice | Changed ring layout plus neutral bypass | Independent preparation, engage/decline and departure |

A proposed server-fed rule card states current label, A/D cap, multi-combat flag, item-drop behavior and Rostogol/special-day effects. Current PK placements are explicitly provisional in the source. Read active rules at entry; do not hard-code permanent world coordinates or describe all public arenas as equivalent.

## Ten storyboard frames

### 01 · Agree to a practice fight — 3 minutes

**Picture:** Vale stands outside the chalk with a readable practice kit and an unobstructed departure gate.

**Voice:** “This yard lends you the risk. Your own belongings stay outside it.”

**Play:** Read the private practice terms, accept the isolated profile and inspect the ring's authoritative rule card. Locate the exit and confirm the real inventory is separate by viewing the borrowed label and kit. Declining returns to ordinary play without penalty.

**Learn:** This is a protected rehearsal. Public PK eligibility and loss rules depend on the actual zone and current conditions.

**Evidence:** Explicit practice entry and correctly loaded private rules; no hostile action before entry completes. This is orientation, not a combat achievement.

**Recovery / observe:** Clear pending targets and public-party interactions before borrowing. Can the tester identify the protection that applies here without concluding every PvP encounter is a mutually accepted duel?

### 02 · Both feet in the same rules — 3 minutes

**Picture:** Rook stands inside North's marked area while the player starts just outside. Tile labels support the boundary colors.

**Voice:** “The ground under both of you matters.”

**Play:** Select the rival outside shared eligibility and read the actual rejection or unavailable action. Move into the same valid practice PK zone and start a brief ordinary player attack. Reset at the refuge, then reverse which participant stands outside the bounds.

**Learn:** Standard player hostility requires the relevant shared eligible zone; visual proximity alone is insufficient. Territory-raid eligibility is a separate advanced case.

**Evidence:** Rejected outside attempt without unauthorized effect, followed by real eligible engagement. Both actor positions and effective zone must be recorded.

**Recovery / observe:** Do not move the boundary secretly. A stale target should get accurate feedback after movement. Observe whether the player reads the zone state or merely searches for a red outline.

### 03 · A cap is not an equal character — 3 minutes

**Picture:** East's ring displays an Attack/Defense cap beside the borrowed character's base values and equipment.

**Voice:** “The ring limits these skills. Your whole kit does not become the same as mine.”

**Play:** Inspect base and effective capped Attack/Defense, equip a valid kit and exchange a few ordinary attacks with Rook. Change a noncapped equipment modifier and observe its continued presence. The current cap is on A/D, not universal normalization of attributes, gear, magic or every skill.

**Learn:** A capped arena still rewards understanding the other systems; a label such as 40 A/D is not a promise of equal builds.

**Evidence:** Actual zone cap application and valid combat with recorded effective stats. No requirement for equal damage on both participants.

**Recovery / observe:** Select a practice profile above the cap so the effect is visible. Do not change permanent levels. If the native client lacks effective cap feedback, implement the truthful read-only display before testing this lesson.

### 04 · Choose a distance you can use — 4 minutes

**Picture:** A low obstacle divides East's approach lanes. Rook alternates clearly announced melee and ranged kits between attempts.

**Voice:** “Look at the reach and the route. Then choose where to stand.”

**Play:** Engage once with a valid melee kit and once with bow/ammunition or a qualified borrowed hostile spell. Use actual approach, range and target rules. Reposition around the obstacle only where the runtime's collision and targeting permit it; do not assume unimplemented cover or line-of-sight immunity.

**Learn:** Different attack modes have different costs and reach. Player opponents can change their kit and position.

**Evidence:** One real effect from each selected mode plus a legal position change. The objective accepts a hit, not a forced critical or knockout.

**Recovery / observe:** Refill ammunition/reagents to the lesson allowance. Wrong target, invalid range and missing equipment each get their true reason. Watch for uncontrolled repeated clicks when the rival moves.

### 05 · Leave before the last blow — 4 minutes

**Picture:** South's retreat lane stays visible behind the player. Vale stands safely beyond the practice engagement area.

**Voice:** “You have room to leave. Use it while you can still choose.”

**Play:** Enter an ordinary player engagement, request normal flee by movement, react to success or failure and reach the refuge once disengaged. Recover with a useful healing item, then decide whether to re-enter. A ground click is a flee request, not guaranteed escape or teleportation.

**Learn:** Retreat consumes real combat decisions and can fail. Crossing paint alone must not be taught as universal combat cancellation.

**Evidence:** Engagement, genuine successful flee, resolved combat links and safe arrival, followed by actual useful recovery.

**Recovery / observe:** Tune a generous health margin and offer a disclosed private rescue when necessary. A failed flee is a learning event, never a mandatory random gate. Test repeated failures in engineering QA without forcing them in the newcomer run.

### 06 · The second opponent changes the fight — 4 minutes

**Picture:** A second clearly scripted rival enters a separate South alcove. The rule card changes only when the player enters a different marked practice zone.

**Voice:** “Read whether this ground allows more than one opponent.”

**Play:** Compare a single-combat practice zone with a separate multi-combat zone using actual server eligibility. Engage a manageable pair in the latter, inspect the resulting pressure/defense penalty where applicable and retreat or remove one opponent to simplify the fight.

**Learn:** Multi-combat is a zone rule, and multiple attackers can alter effective defense. Relevant perks may modify the penalty.

**Evidence:** Actual allowed/rejected second engagement and changed combat membership, followed by a useful response. Do not simulate two attackers only through decorative animations.

**Recovery / observe:** Both rivals stop through normal resolution or an explicit practice rescue. Keep the exit path wide. On replay change which rival approaches first to avoid teaching one memorized target order.

### 07 · Read what protects you — 4 minutes

**Picture:** A short marked spell lane sits beside an ordinary weapon lane; the active effects display is readable from the refuge.

**Voice:** “A ward answers a kind of attack. It does not end the fight.”

**Play:** Borrow a verified small spell kit, use an appropriate protection and observe a real hostile player spell. Cancel an uncommitted target with Escape, then select the intended rival and land a valid hostile effect. Optional immunity practice compares an actually rejected hostile cast with an ordinary weapon attack.

**Learn:** Target eligibility, effect type and resources still matter in PvP. Beneficial party/guild relationships are not blanket immunity from every hostile action.

**Evidence:** Actual useful protection/effect, targeting cancellation without spend and correct subsequent target. No re-teaching every magic family.

**Recovery / observe:** Party membership and hostile eligibility must follow each real runtime path; do not assume all paths share identical ally rules. Record mismatches as implementation blockers rather than explain inconsistent behavior away.

### 08 · A defeat has rules too — 4 minutes

**Picture:** Vale offers a separate, explicit borrowed-kit defeat rehearsal. The exit and loss-rule card remain visible before it begins.

**Voice:** “Know what a loss means before you risk what matters.”

**Play:** Inspect current no-drop protection and optional death rehearsal. If accepted, let the real player-death path resolve on the practice profile and inspect respawn, inventory and equipment. If declined, examine the supplied event replay and continue; mark death demonstration unperformed rather than falsely completed.

**Learn:** Death destination, item drops, novice protection, Rostogol behavior and special days are separate conditions. No-drop does not mean no defeat, no consumable cost or no equipment wear.

**Evidence:** Real death/respawn and exact belongings reconciliation for participants who choose it; orientation-only evidence for others. Optional loss experiments use disposable practice value.

**Recovery / observe:** Never require a randomly dropped bag to progress. Current death code checks some stone consumption before no-drop; the rule card must reflect that ordering, and the core kit should contain no Rostogol Stone.

### 09 · Win the decision — 6 minutes

**Picture:** West offers two routes: a short eligible contest and a longer neutral supply delivery. Rook's kit and ring entry side differ from the guided bouts.

**Voice:** “Inspect the ground and the opponent. Bring the dispatch through.”

**Play:** Read the actual rules, prepare a kit and choose to engage or use the neutral route. The contest path accepts a useful hit followed by a controlled withdrawal, or a clean victory; the neutral path requires recognizing why the other route is unsuitable and completing the delivery. Change two variables: rival attack mode and cap/multi-combat configuration shown openly at entry.

**Learn:** Preparation, engagement choice and survival are valid outcomes; a tutorial should not teach fighting every visible player.

**Evidence:** Correct eligible action/withdrawal or completed bypass, plus dispatch delivery. Core earlier frames already demonstrate real combat.

**Recovery / observe:** Record rule inspection and the reason the player's action fits it. An optional hint may identify a mismatch without selecting the route for them. Multiple valid decisions are accepted.

### 10 · Beyond the chalk — 2 minutes

**Picture:** The practice rivals salute from the ring while the original character returns outside every hostile boundary.

**Voice:** “Out there, read the rules again. This yard's promise ends at its gate.”

**Play:** Restore the real profile and inspect the current rule information for a public destination without entering. Offer an optional spar with a willing player on an isolated practice server, or leave. No duel invitation, party change or public teleport is sent automatically.

**Learn:** Public zones can differ from practice and their placements/policies may change. Participation remains optional.

**Evidence:** No live hostile links, rival ownership or borrowed effects remain; original items, health/progression state and memberships restored under the shared contract; completion stamp once.

**Recovery / observe:** Exit while a projectile, spell or delayed effect is pending must prevent cross-profile damage. Later transfer asks the tester to read a changed zone and demonstrate a safe prepare/decline decision.

## Optional rings and feature coverage

| Feature | Lesson | Demonstration |
| --- | --- | --- |
| Opt-in practice versus public PK eligibility | 01–02 | Read actual zone; rejected and valid player target |
| Same-zone bounds and movement | 02 | Reverse inside/outside positions |
| A/D cap versus other attributes/gear/skills | 03 | Base/effective comparison in ordinary combat |
| Melee, ranged, hostile magic, range/resources | 04, 07 | Actual effects and truthful rejection |
| Flee, recovery, re-entry and target cancellation | 05, 07 | Real disengagement, useful heal and Escape |
| Single/multi-combat, multiple-attacker pressure | 06 | Genuine extra engagement rule and response |
| No-drop, death/respawn and novice protection | 08 | Optional actual defeat, no compulsory loss |
| Rostogol, no-Rostogol and special-day ordering | Ring A · a borrowed loss | Use disclosed above-novice practice profiles, registered stones and distinct rule fixtures; resolve actual deaths and item/stone events. Repeat only optionally; never require a random bag |
| Party/guild, summons, immunity and hostile eligibility | Ring B · names and sides | Two practice player sessions plus owned summons; test each real attack path, ally filters, immunity and eligible hostile Disrupt separately |
| Territory raid exception | Ring C · a contested road | Inspect registered raid team/zone state and play an optional isolated real raid objective; no claim that every public map becomes globally PK |
| Human opponent adaptation | Optional spar | Two willing ordinary clients alternate attacker/defender, call a pause through the practice service, then switch entry/kit |

Optional rings take 5–8 minutes and the human spar 10–15. Territory raids need their own scoped setup and cannot be represented by two ordinary hostile NPCs. Guild territory administration is outside this basic PvP adventure; a later guild-focused scenario can build on the real raid exercise.

## Implementation dependencies and audit

New work includes Chalkwatch, private player rival sessions, server-fed effective rule card, isolated death/stone/drop policy fixtures and safe cleanup of delayed combat. Register actual zone bounds and apply them consistently across melee, ranged, spells, summons and raid-specific paths. Reuse ordinary actions; a decorative NPC spar cannot prove player eligibility.

Current public PK definitions are marked provisional. Also audit the current ordering in `create_player_death_bag`: novice protection precedes stones; a stone can be consumed before a no-drop return; no-Rostogol map and special-day behavior are not identical. These are source observations requiring truthful presentation and policy review during implementation, not reasons to make the core lose items. Do not silently invent an alternative protection rule inside a supposed public-rules lesson.

Audit boundary crossing mid-attack, different zones on one map, cap applying only to A/D, active single/multi combat, failed flee, delayed poison/projectile on exit, death below/above Overall 20, full bag recovery, every stone/no-drop/special-day combination, party/guild ally paths, summon ownership, active territory raid, disconnect in combat and two private rings. No practice death bag, achievement, score or currency can affect public records.

## Human playtest emphasis

Target 5/6 finding the actual zone rule and demonstrating retreat/cancel, and 4/6 making a valid changed final decision without mechanical prompts. At least 5/6 must distinguish no-drop from no-cost and A/D cap from total normalization. Respect declining the optional death or human spar. Use at least three willing pairs for the separate two-client session; measure response to a moving human and agreed practice pauses, not win rate. Never interpret a bot victory as PvP readiness.

## Source audit

- [PK zones](../../../../dev-server/eloria/pk.py): provisional locations, caps and loss/multi-combat flags.
- [World runtime](../../../../dev-server/eloria/world.py): player melee/ranged, flee, death ordering, summons and raid eligibility.
- [Magic runtime](../../../../dev-server/eloria/magic_runtime.py), [territory raids](../../../../dev-server/eloria/territory_raids.py), [perks](../../../../dev-server/eloria/perks.py): hostile/support distinctions and advanced variants.
- [Native client](../../../godot-client/src/app/main.gd), [party UI](../../../godot-client/src/ui/extension_windows.gd): actual input and feedback; proposed zone summary is new work.
