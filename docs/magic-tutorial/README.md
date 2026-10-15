# The Borrowed Sky

## Magic tutorial storyboard

**Implemented storyboard · 9 September 2026 · Native Eloria client · Solo · Target: 45–55 minutes**

[Open the illustrated storyboard](storyboard.html) or the
[play instructions and implementation notes](implementation.md).
The core rescue and four experiments now run in the native client with the
matching `dev-server`; enter `#tutorial magic` after leaving The Last Lantern.
This document retains the design and human playtest specification. It follows the four-gate structure and
show → practice → independent application rhythm of [The Second Bell](../invasion-tutorial/README.md).
Mechanics below were checked against the current client and sibling `dev-server`.
Session lengths and learning targets are hypotheses for human testing.

The supplies brought through Bellwatch have reached **Stillglass Observatory**.
A storm has knocked its great lens out of alignment, trapping three apprentices
in separate courts. Keeper Sera can hold the lens steady, but cannot leave it.
The player borrows the observatory's practice attunement, reaches the apprentices,
and brings them back before reopening the road home.

**Sera:** “I can keep the sky in place. I need you to bring them home.”

There is no countdown on the first run. Weather and a wavering constellation
provide atmosphere; danger advances with encounters, not while someone reads.
Rescued apprentices gather visibly around the central lens. Each restored court
adds one steady arc of light overhead. Spells act on actual eligible actors,
health, resources and positions. Repairing the lens is an ordinary nearby object
interaction after the rescue, not an invented “cast Heal on machinery” rule.

The core adventure teaches the decisions that recur across the spellbook.
Four optional, replayable experiments cover advanced and specialist families.
The coverage matrix at the end assigns **all 31 current families / 86 variants**
to a lesson; it does not require a novice to cast every variant in one sitting.

## A small map with four gates

Proposed **120 × 120 tiles**, one central refuge and four compact courts.
Coordinates and walk times are layout intentions until a native collision pass.

```text
                       NORTH · Glasshouse Gate
                       First aid / shared healing
                                  │
 WEST · Homeward Gate ─── LENS COURT ─── EAST · Prism Gate
 Final rescue / departure Sera / store    Threats / protection
                                  │
                       SOUTH · Folded Gate
                       Blink / concealment / workshop
```

| Place | Scene composition | Gameplay purpose |
| --- | --- | --- |
| Lens Court | A copper lens, three empty seats, a clearly named supply cabinet; no enemies | Safe preparation, pauses, replenishment and visible rescue progress |
| North / Glasshouse | Broken glass beside a safe workbench; an injured apprentice across a short lane; a group near a fountain | Self/target healing, power, resource costs, Allies versus Burst |
| East / Prism Yard | Separate physical and spell threats, broad approach lane, a shelter alcove and labeled heat/cold prisms | Casting under pressure, damage types, wards, poison and recovery |
| South / Folded Walk | A short broken walkway with a visible landing, a patrolled garden, a concealed apprentice and a scrap bench | Ground targeting, movement, detection and inventory selection |
| West / Homeward Garden | Familiar geometry with a different arrangement of threats and injuries; exit visible beyond | Independent rescue with several valid spell choices, then Recall |

Open North first, East after the first rescue, South after the prism lesson and
West after the other apprentices return. Return routes remain open. Teleport
destinations obey the same locked-stage geometry as walking; a gate cannot be
merely a decorative mesh that Blink bypasses. Every required gap is under the
real 15-tile Blink limit and has a valid landing plus an assisted recovery route.

Use the existing native map and 3D quest pins. A movement instruction becomes an
action instruction immediately on arrival. Living targets and dropped supplies
use their actual locations; a walking marker points to a free approach tile.
No spell selection is hidden behind the guide. Keep chat, ether, health, active
effects and spell result feedback visible when the book or a utility dialog opens.

## Access without a leveling grind

Many essential examples are above a new character's Magic level. Even Heal at
its minimum level can fail frequently. Do not silently grant permanent levels,
fake a successful spell, or make players grind to continue the story.

Propose a **private practice profile**, clearly labeled **Borrowed attunement —
practice only** in the native client. The player keeps their appearance and uses
the ordinary spellbook, inventory and casting controls. The server supplies a
separate practice state for skills, nexus, attributes, sigils, belongings, buffs
and XP. It must not overwrite the permanent character. This profile and its
safe lifecycle are new implementation work, not existing functionality.

Before borrowing, inspect one locked spell in the real book. Then accept Sera's
offer through normal NPC dialogue. Teach one missing sigil first by lending it
through an actual ownership update. Sigils are permissions that remain after
casting; reagents are the consumable materials. In the outside world sigils
come from vendors. No permanent money or pickpoint spend is required here.

For each lesson, derive the practice profile from its actual spells and powers:
meet the variant's Magic requirement and the family's nexus/power requirements;
normally use at least spell level +28 Magic for reliable introductory casts.
Avoid arbitrary global “Power 10 unlocked” assumptions. Give enough health and
ether capacity that the planned P1/P2 comparison is measurable without overheal.
The short optional fizzle exercise uses a visibly less-practiced profile and
normal random rolls. It can be left at any time; failing is never a progress gate.

Practice XP appears in practice Statistics. At departure, restore real statistics
and sigil ownership and inspect the real next unlock. A fixed, one-time journal
reward may persist; borrowed items, transmuted practice gold, temporary buffs,
practice XP and portal access cannot leave. If this separation is not implemented,
advanced scenes stay unavailable with a clear explanation; do not present them
as already supported for ordinary novice characters.

## Twelve storyboard frames

### 01 · A sky held together — 3 minutes

**Picture:** Through the West gate, a cracked lens hangs above three empty seats.
Sera braces its turning handle. North is the only illuminated exit.

**Sera:** “Read what the spell needs. Then we can give you a place to begin.”

**Play:** Open the real spellbook (HUD icon; default Ctrl+S), inspect Heal and one
locked spell, then accept the practice attunement. Locate the named missing
sigil, collect it from the cabinet and watch the ownership display update.
Search and scope filters stay available, with only one suggested spell at a time.

**Learn:** Where spells live; requirements are sigils, Magic/nexus, ether and
reagents. A visible icon is not a promise that a cast will succeed.

**Evidence:** Book inspected, practice profile entered and real sigil ownership
changed. These orientation actions do not count as a cast. **Recovery:** An
existing owner skips the missing-sigil substep. **Observe:** Can the tester find
the named requirement without being told which icon to click?

### 02 · A steadier hand — 4 minutes

**Picture:** A shallow glass cut has reduced the player's health; Tavin sits
injured at a bench farther down the same lane. Both health bars are readable.

**Sera:** “Your hand first. Then his.”

**Play:** Cast Heal on yourself. Repeat using the existing Heal quick slot or
its current binding (default Alt+1). Select Heal Target, cancel targeting with
Escape, walk a few steps, then select it again and click Tavin. Approach if out
of range. Tavin must be a real eligible support actor, not a dialogue-only NPC.

**Learn:** Self casts resolve immediately; Target waits for an actor click.
Cancel returns control to movement. Target spells reach up to 15 tiles.

**Evidence:** Separate positive health deltas on self and Tavin after successful
casts; canceled selection spends nothing and leaves no pending target.
**Recovery:** If an early heal removed the wound, use an explicitly offered
practice wound/retry, never unexplained damage. **Observe:** Can the tester
change recipients and return to walking without accidentally attacking?

### 03 · Enough for another try — 4 minutes

**Picture:** Tavin points to a cabinet and a kettle. The ether bar is low; the
book names a missing material instead of leaving the player to guess.

**Sera:** “A failed cast spent nothing - not your ether, not your ingredients. Try again.”

**Play:** In a safe preparation step, fix a real missing-reagent condition by
withdrawing the named item from storage. Restore depleted ether with a Potion
of Mana or a larger appropriate potion. Eat Bread and observe an ordinary
positive-food regeneration tick while walking to the fountain. Offer a short
fizzle experiment; if a natural failure happens, compare ether and item counts
before retrying. No forced failure or requirement to wait for bad luck.

**Learn:** A rejected request spends nothing, and neither does an attempted
cast that fizzles; only success consumes ether and reagents. Positive food supports
passive ether recovery on the normal food tick. Potions have their own cooldowns.

**Evidence:** Required material arrives, ether actually rises after a potion,
and food is positive. Record regeneration/fizzle observations separately from
required actions. **Recovery:** Bounded cabinet refills; no wait-only mana lock.
**Observe:** After a blocked cast, does the player solve the stated shortage?

### 04 · How much light? — 4 minutes

**Picture:** Two injured practice companions wait at matching benches. A small
copper focus sits beside a single Attunement Charge.

**Sera:** “Enough is a choice. More has a cost.”

**Play:** Heal comparable wounds at P1 and P2 with the native power stepper;
compare actual health restored, ether spent and materials used. Reduce power
before topping up a smaller wound. Move a Hearthstone Focus plus a charge into
inventory and cast a supported Heal again; observe the anchor substitution.
Repeat with no charge using the ordinary anchor material.

**Learn:** Power changes strength and often duration/cost; allowed power depends
on the spell family, Magic and Magic nexus. Heal variants share an effect family.
A matching focus works from inventory: one charge replaces the anchor, not the
whole recipe. It does not need an invented equipment slot.

**Evidence:** Server records selected/actual power, non-capped healing and exact
resource deltas; focus remains, one charge is spent and the anchor is retained.
**Recovery:** Restore comparable wounds only on explicit practice retry.
**Observe:** Does the player lower power without a “use P1 now” instruction?

### 05 · Who is inside the circle? — 5 minutes

**Picture:** Tavin and Mira are nearby party companions. Oren, a friendly visitor,
stands beside them but is not in the party; another companion waits farther away.

**Sera:** “Near you is not the same as with you.”

**Play:** Cast Heal Allies while near the party, then reposition so the distant
companion is included. Use Heal Burst centered on Oren's group. Move the selected
center once and observe who receives healing. Use actual party membership and
health changes; the actors' clothing or green names cannot confer eligibility.

**Learn:** Allies centers on the caster and includes nearby party/guild
characters. Burst centers where you click and beneficial Burst can include
unaffiliated characters. Both use the current four-tile neighborhood; the center
must be within 15 tiles. Scope changes recipients and resource cost.

**Evidence:** Ally in/out of range and unaffiliated visitor receive exactly the
expected effects. Use target health deltas, not merely the cast animation.
**Recovery:** Actors hold reachable positions during selection; no scarce
resource penalty for exploratory centers. **Observe:** Can the tester include
the intended people in a changed arrangement without selecting a spell for them?

### 06 · The prism pushes back — 5 minutes

**Picture:** A loose guardian blocks the East lane; two smaller threats wait
beyond it, separated from the apprentices by a low wall and a retreat route.

**Sera:** “Choose the target. Leave yourself a way back.”

**Play:** Select Magic Bolt, aim at the guardian and respond to actual retaliation.
Use Magic Burst on the separated pair. Try Poison Target and watch at least one
damage tick while moving to cover. Select a safe enemy target rather than a
friendly actor. Loot only after the normal defeat path completes.

**Learn:** Target versus area damage, periodic damage and resource use under
pressure. Hostile spells exclude allies and obey player-versus-player rules.
Spell effects must end in real combat outcomes, including death and loot.

**Evidence:** Correct recipients lose health, poison ticks, retaliation occurs
and normal defeat clears the encounter. **Recovery:** If a strong cast defeats
a target before an observation, offer an optional replay; do not trap a winner.
**Observe:** Does the player cancel/reposition before spending another cast?

### 07 · Match the protection — 5 minutes

**Picture:** An armed guardian and a labeled spell prism stand in separate
practice lanes. A second prism emits heat; a poisoned apprentice waits in shelter.

**Sera:** “A shield cannot answer every kind of harm.”

**Play:** Use Shield for the physical lane and Magic Ward for a magic attack.
Read the heat prism and choose Heat Ward, then complete the short crossing.
Cast Dispel on a real negative condition and observe poison stop. Examine the
active effect and remaining duration, then refresh one buff once.

**Learn:** Physical defense and matching magical protections solve different
problems; resistance may reduce damage rather than erase it. Buffs expire and
refresh instead of stacking indefinitely. Dispel removes negative conditions;
it is not a general “strip every beneficial enemy buff” spell.

**Evidence:** Actual defense/protection values and resolved attack outcomes,
negative state cleared, no later poison tick, one refreshed effect.
**Recovery:** Safe baseline comparisons use bounded attacks and enough health;
never demand the player take lethal damage to prove a ward. **Observe:** Change
the second prism to cold on replay: does the tester look for Cold Ward?

### 08 · The missing step — 3 minutes

**Picture:** A broken path exposes the sky below. Its landing is visible, close
enough to click, with an uninterrupted floor beyond it.

**Sera:** “Choose where your feet will be.”

**Play:** Select Blink, test an invalid landing in safety, then choose the valid
tile across the gap. Cancel another Blink and resume walking. Cast Haste before
the next open stretch; notice shorter movement steps without a race timer.

**Learn:** Ground selection is not actor selection. Blink checks a walkable
destination within 15 tiles; Haste changes movement speed, not spell potency.
The current Blink path validates the landing, not a general line-of-sight rule.

**Evidence:** Invalid destination spends nothing; successful cast changes real
position; canceled selection cannot swallow the next movement command.
**Recovery:** Reopen the book after a rejected click and keep both landing and
return point reachable. **Observe:** Can the tester identify a new landing when
the obvious bright spot is outside range?

### 09 · A voice in the garden — 3 minutes

**Picture:** A guardian patrol crosses the garden. Beyond it, a concealed
apprentice calls from one of two alcoves.

**Sera:** “Be unseen before they find you. Then listen for someone else.”

**Play:** Cast Conceal before entering the patrol's detection area. After crossing,
aim Reveal Burst at the alcoves and read the native result identifying the hidden
apprentice. Approach and speak to them; their return is a story interaction.

**Learn:** Conceal prevents relevant new creature aggression; it does not end
an existing fight. Reveal detects concealed players in the chosen neighborhood.
Its current result names them in chat; it does not promise to remove invisibility
or render a new through-wall silhouette.

**Evidence:** Patrol acquires an unprotected control actor but not the concealed
player; Reveal names the concealed eligible actor and the rescue interaction
follows. **Recovery:** If combat already began, retreat before retrying Conceal.
**Observe:** Does the player use the detection result rather than a pre-revealed pin?

### 10 · One small sacrifice — 3 minutes

**Picture:** The apprentice's bench contains spare Bones and a lamp missing a
common fitting. The player's own gear is outside the practice inventory.

**Sera:** “Check what you are giving up before you cast.”

**Play:** Open Transmute's real item/quantity dialog. Select a small stack,
read the gold quote, cancel once, then select and confirm the intended quantity.
Use that practice gold at the nearby normal vendor for a fitting; install it
through a nearby object interaction. Nothing automatically transmutes on arrival.

**Learn:** Inventory and quantity targeting; confirmation matters because the
chosen items are consumed. Rarity sets minimum power. Quest items and gold are
excluded. A focus does not remove Transmute's separate sacrifice.

**Evidence:** Cancellation changes nothing; exact selected items become the
quoted gold; the fitting is purchased and installed. **Recovery:** Provide enough
eligible common scrap for a retry; stale slot/instance selections are rejected.
**Observe:** Can the tester catch an unintended quantity before confirming?

### 11 · The last crossing — 6 minutes

**Picture:** All three apprentices gather at West, but the final garden holds
one injury, one matching-resistance threat and a broken approach. The constellation
is nearly complete. Sera's voice falls quiet.

**Sera:** “Bring everyone through. You have what you need.”

**Play:** Prepare resources, inspect the changed layout and choose a workable
rescue plan. Heal or regenerate, protect or evade the threat, use an appropriate
attack or debuff, and cross by Blink or the longer cleared path. Choose useful
power. Call for help if wanted; it stays available without giving an exam answer.

**Learn:** Transfer: solve the situation instead of following a spell checklist.
Winning by a different valid combination is still winning. Choosing an inexpensive
cast, taking cover or returning for supplies can be good play.

**Evidence:** Living apprentices reach the safe rally area, threats no longer
block the selected route, the player can leave, and the lens interaction succeeds.
Track demonstrated skills separately: a missing demonstration prompts an optional
rehearsal, never invalidates a legitimate rescue. **Recovery:** Saved progress,
bounded supplies and a safe retry point. **Observe:** Can the tester plan and
recover with environmental clues but no spell names in the guide?

### 12 · A sky of your own — 3 minutes

**Picture:** All three seats are occupied. The lens settles; the moving storm
becomes a quiet star field. A normal Recall cast begins the journey home.

**Sera:** “That strength was borrowed. What you learned is yours.”

**Play:** Cast Recall at P1 to return to actual Four Gates. Settle practice state
atomically at the map transition. Open the book and Statistics with the real
character, inspect one attainable next spell and its named requirements, then
leave the optional experiment invitation in the journal.

**Learn:** Low-power Recall goes to Four Gates. Practice access differs from
permanent progression. Magic governs practice/unlocks; Magic nexus constrains
power; Magic Offense/Defense affect hostile/support strength; Ethereality supports
ether capacity. No forced permanent stat allocation or purchase.

**Evidence:** Real map transition, permanent character restored, one-time reward
and durable completion record. **Recovery:** Early Recall pauses rather than
finishes the story; returning resumes the precise checkpoint. **Observe:** Can
the tester identify what they need for their next real-world spell?

## Optional observatory experiments

Offer these as four short return visits, **about 5–8 minutes each**, rather than
four more mandatory corridors. Each has a demonstration, an active retry and a
changed setup without spell-name prompts. Completion remains independent of the
main rescue. The player operates the same native client against eligible actors.

| Experiment | Hands-on sequence | Evidence and misconception to catch |
| --- | --- | --- |
| A · Living equations | Compare Heal with Regeneration ticks; use Life Drain while wounded; drain ether from a consenting practice rival that actually has ether, then try an empty rival | Health gained cannot exceed damage actually stolen; ether transfer is limited by target supply and caster capacity. Ether Drain currently targets player characters, not arbitrary monsters or batteries |
| B · A prism has four faces | Rotate magic/heat/cold/radiation opponents; use corresponding bolts, wards and Weaken spells. Compare a prepared weapon hit with Accuracy, Cripple and Elemental Weapon. Try Elemental Ward against mixed elemental damage | All four damage/protection families demonstrated across replays. Cripple reduces physical defense/evasion; do not teach it as a movement slow. Accuracy is not guaranteed hits; Elemental Weapon adds typed damage. Use resolved outcomes, not visual color alone |
| C · The unbroken circle | Cast Magic Immunity before a hostile spell; observe expiry and retry. Use Disrupt on an enemy's actual summon, then test an ineligible ordinary creature. Revisit Target/Allies/Burst with changed membership and spacing | Immunity blocks eligible hostile spells while active; not every environmental or physical hazard. Disrupt damages hostile summons rather than universally deleting pets. A friendly summon is not a valid hostile target |
| D · Roads beyond the lens | Use Recall at P5 to select a real configured portal entrance and travel there, then use P1 to Four Gates. Inspect an item at each Transmute rarity/power boundary in a practice inventory. Try a matching and mismatched charged focus | P1–4 versus P5–10 Recall; multiple entrances are distinct destinations. Common/Uncommon/Rare/Epic/Legendary need P1/3/5/7/9. Quote and exact item identity survive confirmation. Wrong focus does not replace the anchor |

Travel experiments require a small **private destination map with an actual
configured portal entry** and instance-aware arrival resolution. This is new
tutorial routing work: do not expose borrowed power or inventory on public maps.
If the destination is removed between selection and confirmation, reject without
spending and return to a valid chooser.

Summoning itself is a separate skill using the mixing/summoning interface.
This tutorial teaches how magic interacts with summons; it does not mislabel
summon recipes as spells or claim to teach summon behavior controls fully.

## Implementation dependencies discovered in the source audit

These are prerequisites for a truthful playable version, not changes made by
this storyboard. General combat fixes must use the ordinary gameplay path.

| Dependency | Current evidence | Required outcome before testing the affected scene |
| --- | --- | --- |
| Practice profile and transitions | No Stillglass controller/profile exists | Separate practice state, atomic entry/exit, real character preserved across crash, logout, Recall and defeat; no item, XP, sigil or buff export |
| Cast readiness at selected power | `SpellCatalog.unavailable_reasons` checks base mana/reagents; spell details show base cost. The current focus can replace an anchor on the server while that base check still reports it missing | A selected-spell display must show actual allowed power, nexus/variant requirements, focus-adjusted materials and cost. No ready/blocked contradiction between UI and server; accurate per-spell clamping |
| Eligible practice people | `magic_targets` gathers session characters and animals; Allies specifically includes characters with real party/guild eligibility; a named dialogue NPC is not included | Isolated server-controlled session-backed practice companions/rivals, truthful membership and PK permissions. Player still makes every gameplay request through normal controls; no second human required |
| Creature magic defeat and response | Current `magic_damage` clamps Animal damage at one remaining HP; the book damage path does not itself route through ordinary creature defeat/loot or establish retaliation | Integrate damage, aggression, kill credit, loot and cleanup with normal combat. Exercise direct damage, poison and Disrupt; never delete an actor in the quest just because a visual played |
| Detection feedback | Reveal currently emits `Hidden nearby: <name>` for concealed session characters | Keep chat feedback visible and give a reachable search area. Any new silhouette or removal of invisibility requires an explicit general feature decision |
| Geometry of area feedback | Server uses max-axis distance for 15-tile targeting and four-tile neighborhoods | Target previews must match authoritative tile membership, including diagonal edges. A decorative circular pulse is not an exact targeting guarantee |
| Recovery and effect observability | Generic cast activity reports the spell name, while timed effects and target deltas live in separate paths | Typed outcome events and saved lesson evidence. Actual HP/ether/status changes must validate learning objectives; animation and cast requests alone cannot |

Do not add universal cooldown, silence, channel interruption, line-of-sight,
revival, guaranteed elemental weakness, friendly fire or taunt rules that are
not supported by the current system. Avoid promising that every high-power
spell scales all properties: scope, strength, duration and utility each have
their authored behavior.

## Completion, recovery and instrumentation

Use one active objective with atomic text/marker updates. Persist stage, rescued
actors, completed gameplay evidence, assistance and loan ledger. Reconnect must
not recreate a resolved enemy or apply a second Transmute/reward. Define behavior
for a timed effect interrupted by logout: restart the unfinished observation
with a refill, or resume an explicitly saved duration; never silently grant credit.

Record a proposed `magic_tutorial_action` event with stage, spell ID/effect/scope,
requested and effective power, practice status, target/center, request result and
reason, pre/post resources, affected actors, HP/ether deltas and relevant status
changes. Record instruction/hint exposures separately. These telemetry hooks are
new work. A successful full-health heal can be a valid cast but not evidence of
health restored; a valid Reveal with no hidden actor can be useful information
but is not the apprentice-detection objective.

Offer help in three steps: name the problem, highlight the relevant native
control, then offer an explicit safe retry/refill. Hints never cast for the player.
Mark assisted attempts distinctly. Replenish to a bounded lesson allowance based
on actual spell costs; a Focus or Transmute can change that allowance. Keep free
slots and carrying capacity for required materials and fitting. Existing inventory
is protected by the separate practice profile, not fragile “subtract a kit” logic.

## Playtesting: prove learning through play

### Round one — six newcomers, normal client and timing

Use six players unfamiliar with Eloria magic, including at least two with little
MMO experience. Start from the post-Lantern state; Second Bell is narrative context,
not a leveling prerequisite. Run three pausable acts: foundation (01–05), rescue
(06–10), independent return (11–12). Allow breaks and record elapsed versus active
play time. No facilitator control instructions unless requested or required to
resolve a product defect; record every intervention.

For each scene capture time to first useful action, wrong-recipient/ground clicks,
invalid-cast reasons, actual resource changes, ineffective overheal, power choice,
cancel/retry behavior, marker searches, recovery and hint level. Observe each
prediction through an action: “Show me how you would help those two” is preferable
to a multiple-choice quiz. After a surprise, ask “What did you expect to happen?”

### Round two — change the problem, keep the rules

Give frame 11 a different entry side, injuries and enemy protection. Across the
cohort, rotate which person is not in the party, which Burst center is useful,
which ward matches, whether mana or an anchor is missing, and which Blink landing
is valid. Keep the load manageable: change two variables per replay, not all at once.
Leave spell names out of the objective. Accept successful alternate strategies.

After a break or the next day, ask the tester to perform one small real-character
task using their available spells and diagnose a blocked higher-level spell.
This checks whether borrowed access created the false belief that everything
remains unlocked. Test advanced experiments separately with at least four
participants so a long first session does not conceal fatigue as a control defect.

### Engineering completion audit

| Case | Required result |
| --- | --- |
| Restart before/after every cast, stage, loan, purchase, Transmute and Recall | Exactly one mutation and next objective; permanent character intact |
| Full health, empty/full ether, depleted reagent, missing sigil, no focus charge, mismatched focus, reduced nexus/level | Accurate reason or actual useful outcome; bounded recovery; no impossible observation gate |
| Target moves, dies, leaves range or map while selected; Escape; chat owns keyboard focus | No wrong-recipient cast, stale selection or swallowed movement; text entry never accidentally casts |
| Allies member/stranger/owned summon; Burst edge and diagonal; hostile player outside PK; immune target | Exact recipient rules, no private/public spill, truthful feedback |
| Spell, poison or Disrupt delivers the final hit | Ordinary defeat, credit, loot and combat cleanup; no one-HP survivor lock |
| Refresh/expire effects; Dispel then wait through the next poison tick; logout with modifier | No stacking drift, zombie tasks, false cure or permanent practice bonus |
| Closed gate, walkable landing beyond locked content, occupied destination, invalid/removed portal | No progression bypass; no spend on rejected destination; safe arrival/retry |
| Transmute quantity changes, inventory reorder, item instance replaced, rarity too high, quest item/gold selected | Exact quote revalidation; no unintended item loss or free conversion |
| Two simultaneous tutorials; party/guild outside instance; early leave or defeat | Independent actors, memberships, items and progress; cleanup stays within owner session |
| 1280×720 and narrower layouts, keyboard remaps, muted audio, color-vision differences | Native controls, named targets, resource changes and next instruction remain legible |

### Initial acceptance targets — proposed, not measured

- All twelve core scenes and recovery cases complete with ordinary player input.
- At least **5 of 6** newcomers finish without facilitator control instructions;
  at least **4 of 6** solve the changed final rescue without mechanical prompts.
- At least **5 of 6** demonstrate correct recipient selection, cancel/retry and
  recovery from a real resource shortage. A debrief answer alone is insufficient.
- At least **4 of 6** choose a suitable power/protection in a changed setup and
  correctly identify a real-character unlock requirement after returning.
- No revealed mandatory target takes over 30 seconds to find because its marker
  is stale/hidden. Reading and deliberate tactical observation are measured separately.
- Zero permanent-character loss, exported practice value, duplicate rewards,
  cross-instance effects or unrecoverable progression gates in the completion audit.

These are formative thresholds for iteration, not statistical proof of learning.
Keep automated completion separate from human understanding. Before claiming
multiplayer readiness, run two ordinary players on an isolated server to verify
real party/guild healing, Burst on a nonmember, hostile eligibility, immunity,
drains and ownership of summons. Solo practice actors cannot establish human
coordination or all live-server behavior.

## Source audit

| Source | Basis for this design |
| --- | --- |
| [Current spellbook definitions](../../../dev-server/config/eloria/magic_book.json) and [reference](../../../dev-server/docs/spellbook.md) | 31 families / 86 variants, scopes, names, requirements and utility rules |
| [Magic runtime](../../../dev-server/eloria/magic_runtime.py) | Actual target eligibility, validation/spending, area geometry, Transmute/Recall, damage and timed effects |
| [Magic costs and power](../../../dev-server/eloria/magic.py) | Sigils, per-family limits, charges/foci, success/fizzle costs, Magic Offense/Defense scaling |
| [World behavior](../../../dev-server/eloria/world.py) and [potions](../../../dev-server/eloria/potions.py) | Creature detection, physical/elemental bonuses, food regeneration, potion effects/cooldowns |
| [Spellbook UI](../../godot-client/src/ui/spells_window.gd), [selection](../../godot-client/src/ui/magic_selection.gd), [catalog](../../godot-client/src/ui/spell_catalog.gd) | Actual controls, filters, missing-requirement display, actor/ground selection, Escape, utility confirmation |
| [Main client](../../godot-client/src/app/main.gd) and [bindings](../../godot-client/project.godot) | Quick slots, power stepper, effect feedback and current default keys |
| [Magic book tests](../../../dev-server/tests/test_magic_book.py) and [UI tests](../../godot-client/tests/test_magic_book_ui.gd) | Existing test coverage for family contracts and target/utility behavior; not evidence this proposed tutorial was played |
| [Second Bell implementation](../invasion-tutorial/implementation.md) | Four-gate native presentation, reliable markers, saved progress and real-action precedent |

The following coverage table is generated from the audited spellbook. **Core**
means a required story example; **Experiment** means a hands-on optional lesson.
Variants reuse a learned targeting mode and appear in replay, not an 86-cast checklist.

<!-- FAMILY_COVERAGE -->

| Family / representative spell | Variants | Lesson | Play evidence |
| --- | ---: | --- | --- |
| Heal (`heal`) | 4 | Core 02, 04, 05 | Self, Target, Allies and Burst; useful healing and power choice |
| Magic Ward (`magic_protection`) | 4 | Core 07; B | Match a magic attack; compare a ward with physical Shield |
| Shield (`shield`) | 4 | Core 07; B | Physical defense before engaging; refresh and expiry |
| Poison Target (`poison`) | 2 | Core 06, 07 | Observe damage over time; Dispel stops the negative effect |
| Blink (`blink`) | 1 | Core 08, 11 | Valid ground landing, range, cancellation and repositioning |
| Magic Bolt (`harm`) | 2 | Core 06, 11 | Magic Bolt and Magic Burst; recipients, resistance and actual defeat |
| Transmute (`transmute`) | 1 | Core 10; D | Item, quantity, quote, cancellation and rarity/power boundaries |
| Recall (`recall`) | 1 | Core 12; D | P1 Four Gates; P5 chosen configured portal entrance |
| Life Drain Target (`life_drain`) | 2 | Experiment A | Damage an eligible target while wounded; compare actual health transfer |
| Magic Immunity (`magic_immunity`) | 4 | Experiment C | Block an eligible hostile spell while active; retry after expiry |
| Dispel (`dispel`) | 4 | Core 07; A, B | Clear poison, negative combat modifiers and drained stats |
| Disrupt Target (`disrupt`) | 2 | Experiment C | Damage a hostile summon; reject ordinary or allied creatures |
| Ether Drain Target (`mana_drain`) | 2 | Experiment A | Transfer ether from a valid player rival, then test an empty rival |
| Conceal (`invisibility`) | 4 | Core 09 | Avoid new creature aggression; never substitute for ending combat |
| Reveal Burst (`reveal`) | 1 | Core 09 | Select the hidden-player neighborhood and read the detection result |
| Haste (`haste`) | 4 | Core 08 | Compare actual movement before/after, without a speed trial |
| Elemental Ward (`element_ward`) | 4 | Experiment B | Protect against mixed heat, cold and radiation damage |
| Regeneration (`regeneration`) | 4 | Experiment A; choice in 11 | Observe five-second healing ticks and compare with immediate Heal |
| Heat Ward (`heat_protection`) | 4 | Core 07; B | Choose Heat Ward for the labeled heat threat |
| Cold Ward (`cold_protection`) | 4 | Core 07 replay; B | Change the threat to cold and choose matching protection |
| Radiation Ward (`radiation_protection`) | 4 | Experiment B | Match the radiation threat with Radiation Ward |
| Accuracy (`accuracy`) | 4 | Experiment B | Compare weapon attacks with a temporary accuracy modifier |
| Elemental Weapon (`elemental_weapon`) | 4 | Experiment B | Inspect actual typed damage added to a weapon attack |
| Fire Bolt (`heat_bolt`) | 2 | Experiment B | Use Fire Bolt/Burst against known heat protection states |
| Frost Bolt (`cold_bolt`) | 2 | Experiment B | Use Frost Bolt/Burst in the changed prism encounter |
| Radiation Bolt (`radiation_bolt`) | 2 | Experiment B | Use Radiation Bolt/Burst with correct target and cost |
| Cripple Target (`cripple`) | 2 | Experiment B | Reduce physical defense/evasion before a weapon attack |
| Weaken Magic Target (`expose_magic`) | 2 | Experiment B | Weaken Magic, then compare the magic attack result |
| Weaken Heat Target (`expose_heat`) | 2 | Experiment B | Weaken Heat, then compare the heat attack result |
| Weaken Cold Target (`expose_cold`) | 2 | Experiment B | Weaken Cold, then compare the cold attack result |
| Weaken Radiation Target (`expose_radiation`) | 2 | Experiment B | Weaken Radiation, then compare the radiation attack result |
