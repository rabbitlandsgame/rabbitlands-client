# Shared gameplay and playtest contract

**Applies to all eight proposed follow-up adventures · Source audit: 9 September 2026**

## Teach through an ordinary action

Use the native client with the matching sibling `dev-server`. Reuse its actual inventory, storage, manufacturing, Summoning, Statistics, Perks, trade, party and dialogue controls. When a capability currently uses chat, teach the real command and its response. A proposed convenience button must dispatch the same validated request and is listed as new UI work; a storyboard cannot assume it exists.

Each lesson follows a cause-and-effect sequence: show a need in the world; expose the relevant control; let the player perform it; show the result; change one condition and let them adapt. Opening a window is valid orientation evidence, but never substitutes for a successful transaction, useful effect or combat action. Guide dialogue is short and can be revisited. One active objective names the intended outcome and, only when needed, one suggested control.

Avoid duplicating the opening tutorial's basic movement and the magic/invasion adventures' complete combat lessons. Offer a contextual refresher instead. Let already demonstrated, stage-relevant evidence satisfy a step when safe; do not require an arbitrary unequip/re-equip or deposit/withdraw ritual just to replay an animation.

## Private practice and permanent identity

Borrowed Sky provides an existing separate-practice-profile precedent. Generalizing it to these adventures is new work. Audit every field before reuse: base attributes, nexus, earned/spent pickpoints, perk ownership/toggles, god ranks, known knowledge, research cursor, inventory and slot order, exact item instances and durability, storage, skills/XP, buffs, party membership and tutorial state.

Permanent choices are never required for completion. Entry states what is borrowed. The profile remains visibly labeled throughout. Taking a perk, renouncing a god, consuming a stone or losing a pack in training must be an actual ordinary mutation of the separate practice state. At departure the original character is restored, and the guide directs attention to real next requirements without spending points or money automatically.

Practice auctions, trade escrow, mail/notifications, item ownership, group instances, reward caches and death bags need an isolated persistence namespace as well as an isolated character. Swapping a Character object alone does not isolate these services. Borrowed gold, materials, blessings, knowledge, summons, market proceeds and group loot cannot enter the public economy. Disable public transfers for the duration and offer immediate safe departure. Do not remove real guild membership or silently replace an active real party to enter practice; explain the conflict and let the player return later.

Proposed completion reward: a journal stamp and replay access, once per adventure. No permanent gameplay reward is specified here; any later reward requires an explicit budget and an idempotent award transaction. Existing player progression remains the motivation for the outside-world handoff.

## Map and scene contract

Map sizes and court coordinates are design intentions until built and checked against native collision. North introduces a mechanic, East changes a constraint, South combines it with another system, and West tests transfer and provides departure. Tutorial-specific objects may move the narrative forward after a real action. They must not create false general rules: summons cannot be commanded to operate a winch unless that feature is actually implemented; repairs use equipment services; worship affects characters, not a magical door implicitly.

Every locked gate needs authoritative walk, portal, Blink and Recall handling. Unlocked return routes remain open, including after a failure. Central refuges are excluded from new hostile targeting, and existing engagements must be ended through a disclosed practice rescue if ordinary retreat fails. Do not imply that crossing a painted line universally cancels combat.

Map and 3D markers share one server objective target. Bind moving actors, resource objects, bags, markets and instance items by identity. Walk pins use free reachable approach tiles. On arrival update instruction and marker together: “Reach the bench” becomes “Open Manufacturing and make an Iron Bar,” with a persistent guide card. A missing marker never means an unexplained stage transition. Survey the actual resource placement, tool requirement and approach path for every required harvest.

## Objective and checkpoint semantics

Persist an adventure/version/run ID, frame/substep, entry checkpoint, evidence ledger, issued/consumed/returned practice supplies, resolved actors, assistance, branch choices and completion stamp. Use mutation IDs to deduplicate retries. Save after authoritative mutations, not after local animations. Reconnect restores a comprehensible next action without respawning a defeated target or repeating a purchase.

An interrupted live process may not be resumable: the manufacturing queue is client-local, parties are transient and gauntlet runs have timers. Save the completed learning evidence, state that the unfinished exercise restarted, and reconstruct only its remaining supplies/actors. Do not pretend a queue or public instance survives server restart. An explicit retry begins a new attempt ID. An assistance waiver records an incomplete demonstration and can close the story only with an assisted result, never a mastery badge.

Recovery must handle missing/dropped/consumed essentials, full inventory and storage, dead/moving targets, missed loot, changed slot ordering, menu cancellation, logout, server restart, premature gate use, repeated entry and two simultaneous tutorials. Restore to the finite outstanding lesson allowance; do not blindly add a fresh full kit. Preserve unrelated permanent data byte-for-byte where possible, and compare exact item identities as well as stack totals on exit.

## Honest timing and chance

First runs have atmospheric urgency without a hidden failure countdown. Where timing is itself the feature—research ticks, summon decay, potion cooldowns, blessings or gauntlet limits—use its real timer and explain it. Do not freeze ordinary combat, force a random failure or accelerate a hidden server clock to make a scripted beat work.

Introduce random outcomes through short optional observations. No mandatory objective requires a critical mix failure, rare item, particular damage roll, death-drop roll or a fixed number of successful dodges. Accept an equivalent demonstrated action when an outcome is already satisfied. Explicit bounded retries can replace lesson supplies while preserving the recorded result. Compare deterministic displayed modifiers and authoritative event components before drawing conclusions from random combat samples.

## Assistance and presentation

Hint 1 names the problem. Hint 2 highlights the relevant native control or current target. Hint 3 offers a disclosed retry/refill or safer practice configuration. Never click, cast, trade or allocate points for the player. Record hint level and recovery separately from success. Optional spoken lines are duplicated in readable text. Color is supported by labels, shapes and actor names. Controls remain usable with remapped keys, chat focus, large UI scale and muted sound.

The proposed timing budget is active play, separately recording reading, pauses and recovery. A player may leave from any refuge with a saved checkpoint. Long optional experiments are offered after the story, not added invisibly to its first-run duration.

## Proposed instrumentation

For each ordinary request and resolved action capture: tutorial/version/run/attempt, actor and target identity, objective, current practice status, requested operation, result/rejection reason, before/after relevant resources, exact item IDs, effective modifiers or zone flags, timestamp, hint exposure and checkpoint transition. Record client intent and server result separately. Include private-service namespace and transaction ID for trades, auctions, offerings, repairs and cache rewards.

Human observation adds time to first useful action, wrong control/target selections, stale-marker searches, self-correction, reasons for abandoning, and the player's expectation after surprising feedback. A window-open event does not prove reading. A spoken answer does not replace performing the action. Minimize retained information: local playtest participant codes suffice; collecting chat text or real identities is unnecessary.

## Human playtest protocol

Use six newcomers per adventure, including two with little MMO experience. Start with the promised prerequisite state and ordinary controls, timing and randomness. The facilitator asks what the player expects after a surprise but gives no control instructions unless asked or a defect blocks play. Log every intervention. Separate optional advanced tests so fatigue does not masquerade as a bad mechanic.

In the final challenge remove exact button/spell/recipe instructions, change two relevant variables and accept alternate correct solutions. After a break or on the next day, give a small task with the restored real character. It must be achievable with that character's actual resources; diagnosing a missing unlock is valid when the advanced action is unavailable. Do not require a permanent purchase merely to pass a research session.

Initial formative targets, all unmeasured: at least 5/6 finish the core without facilitator control instructions; at least 4/6 solve the changed final challenge without mechanical hints; at least 5/6 recover from one genuine rejected action or shortage; at least 5/6 identify which capabilities were borrowed after departure. Investigate any mandatory revealed target that takes over 30 seconds to locate because of the UI. Topic-specific demonstrations are listed in each proposal. Six participants guide iteration, not statistical claims.

## Engineering release gate

Automate traversal and fault injection at every mutation/checkpoint, then run native input tests. Verify two concurrent private runs, repeated requests, disconnect before and after commit, full inventory, reordered exact item slots, early exit, death, unsupported entry state and final restoration. Require zero leaked practice value, duplicated mutations or unrecoverable objectives. Check the smallest supported window and a narrow layout for controls hidden behind guide panels.

The party, trade and PvP stories additionally require two normal client sessions on an isolated server. Scripted partners can exercise protocol semantics but cannot prove human coordination, trust or live matchmaking quality. Report solo completion, assisted completion, human transfer and two-player validation separately.

## Audited baseline

The existing [magic practice](../../../dev-server/eloria/sky.py), [invasion practice](../../../dev-server/eloria/bell.py), [client guide](../../godot-client/src/ui/lantern_guide.gd), [world runtime](../../../dev-server/eloria/world.py) and [native client](../../godot-client/src/app/main.gd) provide precedents. Individual specifications link the relevant feature modules and identify gaps. Source inspection establishes design feasibility, not proof that these eight proposed adventures work.
