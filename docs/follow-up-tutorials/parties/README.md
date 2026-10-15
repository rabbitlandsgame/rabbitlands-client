# The Sealed Road

**Parties and gauntlets storyboard · Proposal · Solo rehearsal 35–45 minutes · Optional duo 15–20 minutes · Ten core frames**

[Illustrated storyboard](storyboard.html) · [Collection](../README.md) · [Shared contract](../design-contract.md)

At **Waystone Yard**, road keeper **Orin** needs a small team to open the passage carrying the workshop's supplies. Two plainly labeled practice companions, **Ise** and **Bran**, can join the expedition. The player assembles the group, chooses a reasonable challenge, keeps track of who is present and helps everyone reach the final cache.

**Orin:** “A road opens for the people standing here, not the people you meant to bring.”

The main adventure is solo with scripted partners using real player sessions and party rules. A separately offered two-human run tests actual coordination. Finishing with bots never awards a claim of multiplayer readiness.

## Access and four-gate map

Offer near a gauntlet keeper after basic combat. Magic support is optional; provide a borrowed support kit where required without assuming all players have spells. Practice participants use isolated inventories, achievements, memberships and cache rewards. Do not replace an existing real party silently. Let grouped players return later or explicitly leave their real party themselves before entering.

Propose **144 × 144 tiles**. Muster Court (72,72) has Orin, supplies and return waystone. North (72,115) is Assembly, East (115,72) the Split Road, South (72,29) the Captain's Court and West (29,72) the Vault Walk. The visual hub connects four courts, but the actual gauntlet legs, fork, gate states and exit follow a registered tutorial route definition.

| Gate | Composition | Purpose |
| --- | --- | --- |
| North · Assembly | Wide keeper approach, companions in/out of range | Invites, roster and real participant selection |
| East · Split Road | Two authored alternate lanes around a closed shortcut | Fork commitment and group location |
| South · Captain's Court | Boss lane with recovery alcove outside combat | Support, regrouping and shared progress |
| West · Vault Walk | Reachable cache and waystone | Individual claims, departure and changed replay |

Use a disclosed generous **45-minute practice gauntlet limit** for the first run once started; it is still a real gauntlet timer. Briefing and breaks happen before start or after an explicit saved exercise exit. Public time limits/cooldowns are never suspended by this story. A tutorial-specific definition with its own cooldown namespace is new content.

## Ten storyboard frames

### 01 · People before the road — 3 minutes

**Picture:** Two companions wait by Orin, with one party portrait space empty in the guide's proposed roster aid.

**Voice:** “Invite Ise. Watch for her answer.”

**Play:** Use the current `#party invite <name>` command to invite the clearly scripted Ise. Observe her ordinary acceptance and open the native Party window. Receive and accept a practice invitation in a brief second setup so both sides of the native flow are exercised.

**Learn:** A party is a live group, distinct from the buddy list or guild. Invitations can be accepted or declined.

**Evidence:** Actual invitation and membership events. Opening the panel or seeing a nearby actor does not mean they joined.

**Recovery / observe:** Expired or declined invitations receive an ordinary retry. An unrelated public invitation cannot satisfy this objective. Can the tester identify the current leader and actual member count?

### 02 · Speak where the team can hear — 3 minutes

**Picture:** Ise moves just off screen while her roster row remains visible. Bran waits at the assembly point.

**Voice:** “Tell us when you are ready, and check where we are.”

**Play:** Send a short message through the actual party channel using `#p`, invite Bran and inspect each member's location/health/online state in the current Party window. Walk to the assembly area together. A scripted response acknowledges the party message but does not substitute for membership.

**Learn:** Party communication and roster information help track people beyond the immediate viewport. Guild chat is a different audience.

**Evidence:** Correct channel routing to practice members and actual arrival of the invited actors. Do not score the wording of the message.

**Recovery / observe:** Keep chat focus from triggering movement or spells. If a row omits a needed status, add truthful server-fed feedback as a dependency rather than inventing a current field.

### 03 · Gather the people who will enter — 4 minutes

**Picture:** Bran stands visibly outside Orin's intake distance while Ise and the player are close to the keeper.

**Voice:** “Bran is in your party. He is not at the gate yet.”

**Play:** Inspect the intended roster before starting. Attempt a tutorial route whose minimum participant requirement cannot be met without Bran, read the actual shortage, then bring him within the keeper's normal eight-tile intake distance. Use a proposed read-only participant preview to verify that all three now qualify; leave the successful difficulty selection and start for the next frame.

**Learn:** Party membership and the instance's captured participant roster are not identical. Online, same-map and nearby conditions matter.

**Evidence:** Actual start rejection followed by valid nearby roster selection. Never teleport an absent member by simply counting their party name.

**Recovery / observe:** A disconnected member gets an explicit wait/retry or a smaller supported exercise, not a silent omission. Test a returning member outside the intake range.

### 04 · Choose the road you can finish — 4 minutes

**Picture:** Orin's actual difficulty menu appears beside the assembled group. The strongest member's relevant combat level is readable.

**Voice:** “A harder road pays more. It also asks more of everyone.”

**Play:** Inspect the real challenge choices, displayed timer and route requirements. Choose an easy or fair practice run and enter through the ordinary keeper request. Compare the selected scale with the strongest participating member's combat level; current scaling derives that member's level from Attack and Defense rather than the weakest member or group average.

**Learn:** Challenge changes enemy strength and reward scaling; participant composition affects the result. Cooldowns and occupied copies can prevent entry.

**Evidence:** Server run with recorded participant IDs, tier, effective level, timer and map copy. Menu selection without a started run is insufficient.

**Recovery / observe:** Busy copies or cooldowns show a truthful reason. Practice retries use their own definition/namespace and must not erase real route cooldowns.

### 05 · A fork closes another way — 4 minutes

**Picture:** East splits around a ruined wall. Both routes are visible; one gate seals only after the group commits.

**Voice:** “Choose a lane we can all take. The other road will close.”

**Play:** Resolve the first normal wave, inspect the fork and choose one route through actual gate interaction. Move the team through, then inspect the sealed alternative and the next objective. Use the party roster to locate a companion still near the entrance.

**Learn:** Gauntlets advance through authored legs and committed forks. Quiet ground is not proof every gate is unlocked.

**Evidence:** Real wave completion, fork state and legal party passage. Do not award the leg for merely reaching a waypoint.

**Recovery / observe:** The chosen route must retain a reachable path for trailing participants. Never close a gate that strands a required companion without recovery. On replay swap the easier-looking art between routes to test rule understanding.

### 06 · Help the person who needs it — 4 minutes

**Picture:** In South's first encounter, Ise is hurt while Bran remains healthy. Both have readable party rows and eligible world targets.

**Voice:** “Check the team. Choose where your help will matter.”

**Play:** Use a borrowed real support action on Ise, or execute another validated useful role such as removing a threat before it downs her. For the explicit support substep, cast a genuinely eligible targeted/Allies heal on a wounded party actor and observe actual restored health. Avoid a rigid tank/healer/damage role system that the runtime does not implement.

**Learn:** Party membership affects support eligibility, and useful help depends on current health and position.

**Evidence:** Actual eligible recipient and useful effect, followed by encounter resolution. No credit for healing a full-health member or a dialogue-only NPC.

**Recovery / observe:** Refill practice reagents after genuine mistakes. Reset a downed scripted partner openly at the checkpoint. Track whether the player reads the roster before selecting a target.

### 07 · Leadership can move — 3 minutes

**Picture:** The team rests in a safe alcove. The crown/leader indicator moves from the player to Ise after an ordinary command.

**Voice:** “A team still needs a way forward when one person steps aside.”

**Play:** Use `#party promote <name>` to transfer leadership to the practice partner, inspect the result and have her return it through the same server path. Check which leader-only action is now permitted. Explain offline grace and automatic leadership transfer with a visible optional disconnect exercise.

**Learn:** Leadership is a current role; parties are temporary and do not survive a server restart as saved quest groups.

**Evidence:** Two accepted promotion events and correct authorization feedback. No requirement to kick a member or leave the actual human party.

**Recovery / observe:** Reconnect rebuilds the unfinished practice group without pretending a live party survived restart. Save completed lesson evidence separately. Test leader loss with a real second client before release.

### 08 · Everyone has a share — 4 minutes

**Picture:** The Captain's Court becomes quiet and the West cache opens. Each participant stands at a reachable approach tile.

**Voice:** “The road is clear. Make room, then each of you take your share.”

**Play:** Finish the actual boss/remaining enemies, ensure the player can carry the authored cache result, approach and claim through normal object use. Observe the player's individual claim and a partner's separate claim. Attempting a second claim should return the real already-claimed response.

**Learn:** Final quiet state opens the cache; each registered participant claims once. Ordinary creature loot is a separate system and is not promised to split automatically.

**Evidence:** Finished run, participant ownership and one actual reward receipt per claimant, all inside practice storage/instances.

**Recovery / observe:** Current cache code can mark a claim even when nothing fits. This must be fixed or given an authoritative capacity-preserving claim path before this lesson ships; a guide warning alone is insufficient.

### 09 · Lead a changed expedition — 6 minutes

**Picture:** A short second practice road starts from the opposite side. One companion has lower supplies and the fork layout is changed.

**Voice:** “This time, bring everyone through with the plan you choose.”

**Play:** Use the actual waystone to return from the first run, then assemble the participants for the short second road. Choose an appropriate challenge, communicate readiness, take a route, provide useful help and bring each person to a valid cache claim or explicit voluntary exit. Change two variables: member readiness and fork arrangement. The guide names the expedition outcome, not commands or targets.

**Learn:** Combine roster, preparation, scaling, route commitment and support in a new run.

**Evidence:** Valid captured roster, useful player contribution and final participant outcomes. Scripted companions cannot finish every fight while the player idles.

**Recovery / observe:** A failed attempt restarts only this short road with a fresh run ID. Do not keep a fabricated live run across server restart. Record whether the player notices a missing member before entering.

### 10 · Leave together, return by choice — 3 minutes

**Picture:** The waystone carries the team back to Orin. The player's practice roster clears and the permanent character returns.

**Voice:** “You know the road's rules. Another person will bring their own plan.”

**Play:** Use the real waystone exit, leave the practice party through ordinary membership cleanup and restore the permanent profile. Offer the optional duo run with another willing player, or inspect a real keeper's requirements without starting an instance. Solo completion is a full story ending.

**Learn:** Exiting an instance and leaving a party are distinct. A live expedition includes human decisions the rehearsal cannot supply.

**Evidence:** Map exit, clean practice party/run state, exact real profile restoration and one solo completion stamp. Duo evidence is recorded separately.

**Recovery / observe:** Handle a partner disconnect or declined duo invitation without blocking completion. Do not send public invitations or messages automatically on behalf of the player.

## Optional roads and feature coverage

| Feature | Lesson | Demonstration |
| --- | --- | --- |
| Invite/accept/decline, party versus buddy/guild | 01–02 | Actual membership and correct chat audience |
| Roster health/location/online status | 02, 06 | Locate a member and deliver useful support |
| Nearby captured participants; min/max group size | 03 | Genuine intake rejection and recovery |
| Strongest-member difficulty, timer, cooldown/copy availability | 04 | Actual selected run values; no promised constant difficulty |
| Waves, locked legs, committed fork, final boss | 05–06, 08 | Gate state follows ordinary completion |
| Leadership, offline grace, transient party state | 07; Road A | Real leader transfer; optional disconnect/return |
| Cache ownership, once-per-person claim, capacity | 08 | Actual individual receipt, repeat rejection |
| Waystone and death exit | 10; Road B | Voluntary exit; optional practice defeat returns outside according to route rules, without a promised public mid-run rejoin |
| Mutators and reward tradeoffs | Road C | Inspect actual Frenzy/Hunted/Bounty/Swift message and play a short matching variation; no forced random selection disguised as public behavior |
| Two-human coordination | Duo road | Two ordinary clients alternate leader/support roles, agree on route and each claim their share |

Optional roads are 5–8 minutes except the 15–20 minute duo. Practice-specific retries, generous limits and scripted companions are clearly disclosed. Public gauntlets retain their own penalties and admission rules.

## Implementation dependencies and audit

New work includes session-backed scripted companions, isolated party/run and reward state, Waystone map/route definitions, exact participant preview and an evidence-driven short replay. Tutorial achievements must not increment permanent public counters through a borrowed profile's side effects. Extend the runtime's practice isolation to party and gauntlet services deliberately.

Fix cache capacity behavior: a full or partially fitting result must not consume an unrecoverable one-time claim; stage reward contents/remaining entitlement or reject before awarding. Preserve ordinary once-only ownership and verify duplicate requests. This is an identified implementation requirement, not a claim of a shipped fix.

Audit declined/expired invites, max size, leader offline, same-name casing, member outside eight tiles, different map, online but not ready, active public party, occupied map copy, cooldown, strongest member leaving, fork with trailing member, timer expiry while a panel is open, death/waystone exit, full/partial cache capacity, duplicate claim, server restart and two simultaneous practice parties.

## Human playtest emphasis

Target 5/6 assembling the intended roster and locating a hurt member, and 4/6 completing the changed expedition without mechanical prompts. Record accidental exclusions before instance start. For duo validation use at least three pairs, change leader on replay and observe communication without facilitator coordination. A solo bot run cannot pass this separate human criterion. Later transfer is inspecting a real party/keeper state or completing a voluntary small expedition with a willing partner.

## Source audit

- [Parties](../../../../dev-server/eloria/parties.py), [server party commands/state](../../../../dev-server/eloria/server.py), [native Party window](../../../godot-client/src/ui/extension_windows.gd): actual invitations, roster, leadership and grace periods.
- [Gauntlets](../../../../dev-server/eloria/gauntlets.py), [instance definitions](../../../../dev-server/eloria/spawn_groups.py): participant capture, strongest-member scale, forks, limits, cache behavior and exits.
- [Magic runtime](../../../../dev-server/eloria/magic_runtime.py), [world](../../../../dev-server/eloria/world.py): real support eligibility and player-session behavior.
