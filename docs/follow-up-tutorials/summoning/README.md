# The Missing Caravan

**Summoning storyboard · Proposal · Solo · 30–40 minutes · Ten core frames**

[Illustrated storyboard](storyboard.html) · [Collection](../README.md) · [Shared contract](../design-contract.md)

The caravan carrying Stillglass's repaired instruments has scattered at **Reedway Halt**. Its driver, **Mara**, is pinned beside an overturned wagon. **Toma**, a creature keeper, has enough supplies to call help but must tend the injured travelers already in the refuge. The player gathers the wagons by learning when a summoned creature should fight, when it should wait and when its fading strength means retreat.

**Toma:** “You do not need another sword arm. You need to know what your other pair of eyes will do.”

Wagons return visibly to the central hitching ring. There is no first-run countdown. Summon decay remains real; instructions are delivered before spawning a time-limited companion. Wagon movement is an authored quest interaction after a lane is safe, not a new summon command or a hauling simulation.

## Access and four-gate map

Offer after Last Lantern or when the Summoning window is first explored. Magic is useful context, not a prerequisite. Borrow an explicitly labeled keeper profile with adequate ether, supplies, Animal Nexus 2 and Summoning at least 30; calibrate above individual recipe requirements for reliable introductory attempts. Level 30 is required by the current server for behavior selection. On departure inspect the player's actual access again.

Propose **128 × 128 tiles** with a central hitching ring around (64,64). Court centers are North (64,101), East (103,64), South (64,27) and West (25,64). Coordinates await collision and multi-actor path testing.

| Gate | Composition | Purpose |
| --- | --- | --- |
| North · Reed Pen | Low fence, ingredient cabinet, three clear spawn spaces | Read recipes and call the first companion |
| East · Axle Lane | Broad path, ordinary hostile, waiting wagon | Shared target and disengagement |
| South · Rival Yard | Separate creature and hostile-summon pens | Behavior filters and ownership |
| West · Return Road | Two short lanes around an obstruction, stranded final wagon | Independent preparation and recovery |

Unlock North → East → South → West. Keep the hitching ring reachable. Do not place a pressure plate that demands precise companion steering: the current behaviors select attack targets; they do not provide move-to, stay-on-tile, hauling or manual formation commands.

## Ten storyboard frames

### 01 · An empty hitching ring — 3 minutes

**Picture:** Three empty wagon spaces face Toma's lit cabinet. Mara can be seen across the North fence, giving the first summon a purpose.

**Voice:** “Read the cost before you call. A name in the book is only a possibility.”

**Play:** Open the actual Summoning window, inspect Mirrorfin Otter and the blocked Gate Turtle, then accept the keeper profile through dialogue. Find ingredients, ether, skill and Animal Nexus requirements. Check the real character's behavior-control restriction before borrowing if below 30.

**Learn:** Summoning uses recipe and resource rules; behavior access has its own level gate.

**Evidence:** Record inspection and the profile transition separately. No summon credit yet. The displayed blockers must match server validation.

**Recovery / observe:** A qualified returning character skips the rejection demonstration. Can the tester locate the missing requirement and explain which borrowed capability will disappear on departure?

### 02 · A shape in the reeds — 3 minutes

**Picture:** A shallow reed bed sits beside open ground, with the player's ether rail and the spawned creature visible together.

**Voice:** “One otter. Watch what leaves your pack, and what arrives beside you.”

**Play:** Withdraw Bones ×1, Reed ×2 and Aether Salt ×1 for the current Mirrorfin Otter recipe. Maintain positive food even though this recipe's food cost is zero. Click its native Summoning row once, then observe the real recipe result, ether spend and owned actor. The current base ether cost is 5; display the effective cost for the practice profile.

**Learn:** A successful summon produces a creature, not a new inventory pet item.

**Evidence:** Successful mix plus spawned actor with this player as owner. A submitted request or failure is insufficient.

**Recovery / observe:** Refill outstanding costs after genuine failures. Keep spawn tiles free. Can the player distinguish the owned companion from wildlife without relying on color alone?

### 03 · Walk before the fight — 3 minutes

**Picture:** The player and otter cross a broad S-shaped lane; the wagon wheel remains visible ahead.

**Voice:** “Give it room. These tracks were made for more than one body.”

**Play:** Set Do not attack through the native behavior control, then walk the lane while the summon uses its ordinary movement. Stop in an open area and observe its position and health. Turn back if it is obstructed. Open the wagon latch personally after arriving together.

**Learn:** Ownership and movement do not confer exact tile control; behavior is a standing target preference.

**Evidence:** Accepted behavior setting and owner/summon presence in the roomy arrival region. Never demand a precise formation or count the latch alone.

**Recovery / observe:** If normal movement cannot reach the region, disclose a pen reset and re-summon; do not silently teleport the actor. Test narrow corners before authoring. Observe whether players assume the behavior label means an unimplemented stay command.

### 04 · The same opponent — 4 minutes

**Picture:** One raider blocks Axle Lane. Safe open ground is visible behind the player; the companion starts beside them.

**Voice:** “Tell it whose fight this is. Then choose your opponent.”

**Play:** Before engaging, select Attack my opponent. Click the tagged raider using normal combat targeting and let the summon join. Watch the companion's actual attack and the shared opponent. Clear the lane and use the wagon latch to bring the first cart home.

**Learn:** The behavior chooses from eligible enemies; the player initiates this particular shared fight.

**Evidence:** At least one successful companion attack on the owner's current opponent, followed by the lane's actual defeat and latch use. The summon need not land the final hit.

**Recovery / observe:** Tune enemy health so the ordinary player cannot routinely end the fight before the summon acts. If that happens, offer another short encounter. Record target confusion, owner attacks and companion contribution separately.

### 05 · A companion cannot be called everywhere — 4 minutes

**Picture:** A second threat appears at the lane's bend. The hitching ring is plainly visible through the open gate.

**Voice:** “Make space before you call again.”

**Play:** During a manageable engagement inspect or attempt the unavailable summon action. The current server rejects recipe summons while in combat. Use normal retreat, recover ether with food or a potion as appropriate, then call a fresh companion outside combat and return. Existing invasion knowledge shortens the retreat hint.

**Learn:** Replenishment is part of preparation; clicking a recipe during combat does not create emergency reinforcements.

**Evidence:** Genuine combat restriction or native blocking state, successful disengagement and a subsequent owned spawn outside combat. Do not require consuming a full-ether potion.

**Recovery / observe:** Disclose a refuge rescue if retreat becomes unsafe. Repeated rejection should name the remaining blocker. Can the player change the condition themselves rather than repeatedly clicking Summon?

### 06 · The borrowed life fades — 3 minutes

**Picture:** A healthy summon waits beside a quiet trough. Its bar falls on an ordinary decay tick while no enemy is nearby.

**Voice:** “That loss came from time. Plan the next call before the road needs it.”

**Play:** Observe one real decay tick in a safe pen, inspect remaining health and decide whether to continue with that companion or summon another. The baseline runtime currently applies 10 decay damage every 20 seconds; the **Summoner** perk changes the decay path to 5. Read the active profile rather than teaching the baseline as universal. The internal helper calls this advanced summoning, but the offered perk name is Summoner.

**Learn:** Summons are temporary resources, with health lost outside combat as well as in it.

**Evidence:** Authoritative decay event followed by a viable preparation choice. No compulsory wait until the creature dies.

**Recovery / observe:** Start a new healthy summon if the observation was missed. Give dialogue before the timer begins. Verify that testers distinguish decay from poison or an invisible attacker and do not assume feeding mechanics exist.

### 07 · Pick the right kind of enemy — 4 minutes

**Picture:** A rival keeper's hostile summon and an ordinary hostile occupy separate reachable bays in South Yard.

**Voice:** “A command can choose a kind of danger, not just a name.”

**Play:** Select Attack only summoned creatures. Approach the two bays without personally engaging the ordinary enemy and observe the companion choose the hostile summon. Reset safely, select Do not attack summoned creatures and observe a valid ordinary target instead. Keep combatants close enough to be eligible under normal movement rules.

**Learn:** The filters refer to creature ownership/type, not visual size or magic-looking art.

**Evidence:** Correct target selection and actual companion combat under each mode; simply selecting the menu rows is insufficient.

**Recovery / observe:** Opposing summons need a real non-allied practice owner. If one expires early, replenish that attempt openly. A wolf-shaped summon and similar ordinary creature in replay test whether the player learned the ownership distinction.

### 08 · Friends are still friends — 3 minutes

**Picture:** A clearly labeled practice partner and their summon enter the yard beside one hostile actor.

**Voice:** “Your companion shares your party's boundaries.”

**Play:** Use Attack at will in the mixed yard. Observe it select the eligible hostile while leaving the party member's summon alone. Return to Do not attack before walking the rescued second wagon through. The partner must be a real session-backed party member, visibly identified as scripted practice.

**Learn:** Attack at will is still constrained by owner and party protections; changing mode is not permission to attack everyone.

**Evidence:** Party relationship, target eligibility evaluation and attack on the hostile, followed by a safe nonattacking interval. No claim of immunity from every hostile effect.

**Recovery / observe:** Restore the practice relationship on reconnect before resuming. Test with a matching nonmember summon in a separate attempt. Can the tester predict the different behavior without memorizing which character model is friendly?

### 09 · Bring the last wagon home — 6 minutes

**Picture:** West Road combines one obstructed approach, an ordinary guard and a hostile summon. The final wagon is visible beyond both lanes.

**Voice:** “I can see the wagon. You know what help you need.”

**Play:** Prepare and clear the route with a companion, collect the dropped axle fitting and install it through ordinary object use. Change the entry side and swap enemy ownership from the guided layout. The objective names the wagon, not a behavior setting. Accept a sound shared-target strategy or selective targeting with staged retreat.

**Learn:** Apply cost, positioning, ownership, behavior and replacement decisions to a changed problem.

**Evidence:** Useful summon contribution, recovered fitting and completed wagon interaction. Require no particular species or last-hit ownership.

**Recovery / observe:** Bound enemies and spare supplies; the fitting follows its real bag or inventory state. Record whether the player notices a decaying companion and prepares before engagement. Help remains available and is marked assisted.

### 10 · An ordinary road again — 2 minutes

**Picture:** Three wagons stand at the hitching ring. Toma folds the practice ledger and the real character's Statistics return.

**Voice:** “Out there, call what you can sustain. The road will wait for a careful keeper.”

**Play:** Return the practice profile, inspect the real Summoning window and identify one currently usable recipe or the first missing requirement. Choose to revisit a pen or leave for Four Gates. No real summon or permanent nexus purchase is demanded.

**Learn:** Borrowed behavior access, resources and companion strength do not become permanent unlocks.

**Evidence:** Exact profile restoration, no surviving private-owned creatures, journal completion once and correct real requirement display.

**Recovery / observe:** Logout during handoff must resume on one side of the transaction, never duplicate practice stock. On the later transfer task, ask the player to prepare an affordable summon or show what prevents it without guide prompts.

## Specialist pens and feature coverage

Optional pens last 4–6 minutes each and save separately. They are not required to finish the caravan.

| Feature | Core / experiment | Required action or boundary |
| --- | --- | --- |
| Native recipes, ingredients, ether, positive food, success/failure | 01–02, 05 | Resolve real mix and inspect cost; failure is recoverable, never required |
| Summoning level, Animal Nexus, level-30 behavior control | 01, 10 | Identify one genuine blocker before/after borrowing |
| Ownership, ordinary movement, blocked approaches | 02–03 | Owned actor reaches roomy region through normal movement |
| Do not attack; Attack my opponent | 03–04 | Hold fire, then join the chosen fight |
| Attack only summoned creatures; Do not attack summoned creatures | 07 | Different eligible targets under each filter |
| Attack at will and party protection | 08 | Hostile selected in mixed yard |
| Do not attack my opponent | Pen A · divided attention | Owner engages one target; summon demonstrably selects a different eligible enemy; then switch back and regroup |
| Decay and Summoner perk | 06; Pen B · borrowed time | Observe base tick; inspect and compare perk-adjusted decay in separate profiles, without requiring a death |
| Instant recipe versus summoning stone | Pen C · a sealed call | Use one catalog-valid stone through ordinary item use and compare its actual restrictions/consumption with a recipe |
| Summon strength and skill/perks | Pen B | Inspect profile and actual spawned stats; do not infer power from appearance alone |

Pen C requires new catalog content: the active Eloria item catalog currently has no summoning stones. The shared legacy stone table is not proof of available native content. Register an explicit stone mapped to a creature actually served by the profile, with its native icon and normal item-use route, before enabling the experiment. Do not teach a nonexistent dismissal, pet inventory, loyalty, feeding or precise move command.

## Implementation dependencies and completion audit

Reuse the real recipe path, behavior popup and owned-creature combat. New work includes the Reedway map, wagon/latch quest events, guided evidence, generalized borrowed profile, scripted rival/party sessions and isolated ownership cleanup. Summons must not open gates or push carts by merely wandering nearby.

Audit all six behavior modes with ordinary, summoned, own and party-owned targets; blocked spawn tiles; player already in combat; insufficient Animal Nexus; skill below 30; zero food/ether; decay killing a target between selection and action; owner disconnect; party relationship changes; two private caravans; expired fitting bag. Check both the Summoning row and the underlying mixing route. Completion must remain possible after every case through an explained retry.

## Human playtest emphasis

Use the shared six-newcomer protocol. At least 5/6 should call a creature and resolve an actual blocker; 4/6 should choose a useful behavior in the changed final yard and recognize when to replace a fading summon. Record companion-related waiting separately from reading. If normal pathing requires repeated rescue, redesign the lane before increasing tutorial hints.

For the later transfer, change creature appearance and ownership. For two-client QA, verify that a genuine party member's summon is excluded under Attack at will and a nonmember's eligible summon is not. Scripted companions alone cannot establish this result.

## Source audit

- [Summoning rules and six behavior labels](../../../../dev-server/eloria/summoning.py), [world runtime](../../../../dev-server/eloria/world.py): ownership, behavior level, decay, mixing restrictions and spawn lifecycle.
- [Current profile recipes](../../../../dev-server/config/eloria/recipes.txt): Mirrorfin Otter, Stag and Gate Turtle costs and mappings.
- [Native Summoning window](../../../godot-client/src/ui/summoning_window.gd): cost/blocker presentation and real request path.
- [Perks](../../../../dev-server/eloria/perks.py) and [parties](../../../../dev-server/eloria/parties.py): borrowed perk effects and actual ally membership.
