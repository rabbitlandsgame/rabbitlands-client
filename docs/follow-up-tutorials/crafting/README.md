# The Broken Workshop

**Production and research storyboard · Proposal · Solo · 35–45 minutes · Ten core frames**

[Illustrated storyboard](storyboard.html) · [Collection](../README.md) · [Shared contract](../design-contract.md)

The caravan reaches **Cinderbank Works**, but its forge benches are dark. **Master Edda** needs a sword for the road guard, a steel brace for the damaged pump and enough supplies to reopen the workshop. The player becomes the person who makes an order possible: read the requirement, plan the materials, keep the work going and deliver something useful.

**Edda:** “We have most of what we need. Find out what the work is missing.”

Completed orders add visible tools and warm lamps to the workshop. Delivery and machinery repair are ordinary quest-object interactions using produced items. A crafting button does not operate a distant pump by magic. No production deadline advances while a newcomer reads.

## Access and four-gate map

Offer after the first basic mix or research-book acquisition. Last Lantern already teaches collecting and a simple recipe; this adventure focuses on chains, research and managing a batch. Borrow a separate production profile with appropriate tools, recipe skills, ether, positive food and Rationality. Never grant permanent knowledge or require a novice to spend hours raising skills.

Propose **128 × 128 tiles**. Work Court (64,64) has storage, Edda and the order board. North (64,101) is Raw Yard; East (103,64) the Reading Room; South (64,27) the Foundry; West (25,64) Dispatch. All sources and workstations require native approach and collision checks.

| Gate | Composition | Purpose |
| --- | --- | --- |
| North · Raw Yard | Real ore/coal objects, reachable tool rack | Plan a small ingredient supply |
| East · Reading Room | Safe shelf beside a workbench and food tray | Read knowledge while useful work continues |
| South · Foundry | Storage-side bench and separate distant bench | Compare source modes, queue and recovery |
| West · Dispatch | Guard, pump and revised order board | Independent chain and actual delivery |

The proposed primary chain uses current recipes: **Iron Ore + Deep Coal → Iron Bar → Militia Arming Sword**. A later **Steel Bar** requires Steel Smelting knowledge, Iron Bars, Deep Coal and Bone Ash. Exact quantities come from the current catalog; stock includes a failure allowance beyond the guaranteed successful minimum.

## Ten storyboard frames

### 01 · Read the order, not the whole book — 3 minutes

**Picture:** Edda stands between an empty sword rack and a silent pump. Only the guard's order is highlighted.

**Voice:** “One working sword first. Start with what it is made of.”

**Play:** Open native Manufacturing, find Militia Arming Sword and inspect its ingredients, tool, recommended skill and food cost. Follow its Iron Bar intermediate to the corresponding alchemy recipe. Accept the borrowed workshop profile after inspecting one actual blocker.

**Learn:** A finished item can depend on another profession; a recipe is a plan with requirements.

**Evidence:** Record recipe inspection and a valid staged plan; no crafting credit until an item is actually made. The order board references catalog identities, not copied free-text names.

**Recovery / observe:** Existing knowledge or tools count. Highlight only the first missing requirement. Can the tester trace the sword back to ore without being handed a complete click sequence?

### 02 · Enough material, room to move — 4 minutes

**Picture:** Short ore and coal paths lead back to the central store. A heavy crate beside the bench makes pack space visible.

**Voice:** “Bring the first batch. The whole quarry need not come with you.”

**Play:** Collect a small number of actual Iron Ore and Deep Coal harvests using each configured tool and approach tile. Withdraw the remaining order allowance from Storage. Keep room for intermediates and the finished item; return bulky stock if necessary. For one sword, the current successful minimum includes three Iron Bars plus one Wood Plank.

**Learn:** Production planning includes carrying capacity, tools and output space, not just ingredient totals.

**Evidence:** Real harvest receipts, storage transfers and enough available stock for the next batch. No requirement to grind the whole allowance.

**Recovery / observe:** Mark actual objects, never guessed coordinates. Test full pack and missing tool separately. Observe whether the player checks output space before starting work.

### 03 · The first bar — 3 minutes

**Picture:** The native recipe and pack remain visible beside a cold forge bench. A small bar appears only after the server reports success.

**Voice:** “Make one. See what changed before you make many.”

**Play:** Keep Mortar and Pestle in inventory or equipped as permitted, select the Iron Bar recipe and use Mix One. Inspect actual consumed ingredients, food, XP and output. The current recipe uses Iron Ore ×3 and Deep Coal ×2, with food cost 2.

**Learn:** One request may fail; a successful mix has an observable material result.

**Evidence:** Server-created Iron Bar with source consumption and mix outcome. A progress animation or attempted mix is not success.

**Recovery / observe:** Use normal random rolls. Failure supplies are restored only to the outstanding allowance. Do not require a failure to advance. Can the tester distinguish no output from output sent to a different source/destination view?

### 04 · A book that changes the work — 4 minutes

**Picture:** The Steel Bar row is blocked beside a readable Steel Smelting book; the food tray is within the same quiet alcove.

**Voice:** “That brace needs knowledge. Begin reading while the sword takes shape.”

**Play:** Inspect the real knowledge blocker, use the registered Steel Smelting book and locate research progress in Statistics/Knowledge. Observe a genuine positive-food research tick. Briefly compare the paused state at nonpositive food, then eat and resume while working on the earlier order.

**Learn:** Research completes over game-minute ticks, advances with Rationality and needs positive food. Starting a book is not finishing it.

**Evidence:** Active book identity, actual research increment and later known-book transition. No invisible instant unlock.

**Recovery / observe:** Current default books require 600 pages. A disclosed borrowed Rationality of 100 is within the current purchase ceiling and budgets six positive-food research ticks. Let those ordinary ticks occur during the following work; validate the actual elapsed time in the client. If the pacing still does not fit, split the act into a resumable return visit. Never silently shorten the public book or timer.

### 05 · Work in batches — 4 minutes

**Picture:** Three empty bar outlines on the order board fill as actual output accumulates. Food and ether remain unobscured.

**Voice:** “Ask for enough work. Watch what stops it.”

**Play:** Use Mix All for a bounded issued batch, stop it through the native control, then finish the necessary bars. Build the sword with the actual Hatchet tool requirement. Explain that the current Mix All request is a run of attempts, so failures can leave fewer successes than hoped.

**Learn:** Batch controls save repetition but still obey resources, tools, food, ether and random outcomes.

**Evidence:** At least two successful outputs across the batch, a real stop acknowledgement and a manufactured sword. Count outputs, not button clicks or attempted quantity.

**Recovery / observe:** A depleted ingredient naturally ends the run. Reconcile partial products before refilling. Watch whether the player diagnoses the first stop reason or restarts an impossible batch repeatedly.

### 06 · The store is part of the workshop — 3 minutes

**Picture:** A bench sits beside Storage; a second bench is clearly farther away. The source toggle is shown with a text label.

**Voice:** “The store can supply this bench. It cannot follow you down the road.”

**Play:** Put recipe materials in Storage, retain the required tool in the pack, select the real storage-source option and mix beside the storage NPC. Inspect where the current server puts the result. Stop before leaving range; try the source at the distant bench and read its rejection, then return or switch to inventory ingredients.

**Learn:** Ingredient source, output destination and tool location are distinct constraints. Storage mixing requires proximity.

**Evidence:** One storage-sourced successful mix and a valid recovery from lost access. Do not assume toggling source transfers stock automatically.

**Recovery / observe:** Reconnect clears any stale source assumption. Test a tool stored instead of carried. Can the player locate both the consumed material and finished output?

### 07 · A queue is a plan, not a promise — 4 minutes

**Picture:** Two short queue rows mirror the bar and brace work. The guard waits beside the already completed sword rack.

**Voice:** “Line up the work. Leave yourself a way to stop.”

**Play:** Add a small intermediate batch and a dependent recipe to the native queue. Start, stop and edit an unfinished row. Complete the needed items through ordinary queue responses. Read the explicit notice that this queue lives in the client and is lost on logout; the produced inventory persists.

**Learn:** Dependencies need sufficient successful output, and an unfinished plan is different from completed goods.

**Evidence:** Queue operation plus actual server successes in the expected dependency order. The queue display alone earns no production credit.

**Recovery / observe:** On reconnect offer to rebuild only remaining work from the objective ledger, with a clear notice. Test a critical failure consuming an intermediate. Do not silently duplicate a finished batch when reconstructing the plan.

### 08 · The brace can finally be made — 4 minutes

**Picture:** Steel Smelting becomes known; the pump's empty brace slot is visible through South's open gate.

**Voice:** “Now the knowledge and the materials can meet.”

**Play:** Return to Steel Bar after real research completion. Assemble its current ingredients—Iron Bar ×2, Deep Coal ×3, Bone Ash ×1—and satisfy tool, food and ether costs. Make the bar and install it at the pump through normal object use. This installation is authored quest content, not a claim that all pumps take a Steel Bar.

**Learn:** Knowledge removes one blocker; every other recipe requirement still applies.

**Evidence:** Known Steel Smelting, successful Steel Bar mix and exact item consumption at the nearby pump. A borrowed preexisting bar alone does not satisfy the research demonstration.

**Recovery / observe:** If research is still progressing, show honest remaining time and allow a pause or optional work. Never trap the player behind an unexplained locked gate.

### 09 · An order Edda did not prepare — 6 minutes

**Picture:** Dispatch posts a revised request: a shield and fresh torch for the returning guard. Stock distribution differs from the guided scenes.

**Voice:** “Here is what the next traveler needs. The benches are yours.”

**Play:** Produce a Wooden Round Shield and Torch using their catalog recipes. Change two constraints: place one material in Storage and omit one required tool from the pack while leaving it available nearby. Choose inventory mixing, storage mixing or a queue. Deliver the actual outputs to the guard.

**Learn:** Transfer recipe inspection, source choice, preparation and recovery to a new order.

**Evidence:** Successful outputs from this attempt and exact delivery consumption. Accept any valid production order and preexisting intermediate made earlier in practice.

**Recovery / observe:** Supplies are finite but sufficient with bounded retries. Record whether the tester reads the rejection and fixes the actual condition. The objective names products, not button sequences.

### 10 · Leave a working bench — 2 minutes

**Picture:** The forge, pump and dispatch lamps are lit. Edda marks the order complete while the real character's knowledge list returns.

**Voice:** “The next order is yours to choose. Start with what you can make.”

**Play:** Return practice stock and profile. Inspect one affordable recipe on the real character and its first missing requirement. Choose an optional profession bench or depart. The proposed handoff may bookmark a recipe, but bookmarking is new UI work unless a current control is verified.

**Learn:** Borrowed research, Rationality, skills and goods do not persist as public production capacity.

**Evidence:** Original inventory, known books and research cursor restored; queue stopped; journal stamp once.

**Recovery / observe:** An original research task must resume under the ordinary lifecycle, not lose its cursor. Next day, ask the player to make one available item or demonstrate the true blocker without the workshop guide.

## Optional profession benches and coverage

Each 5–8 minute bench has one order, one changed constraint and one actual use/delivery. Choose a branch; do not require all seven mixing disciplines in a first session.

| Feature | Lesson | Demonstration |
| --- | --- | --- |
| Harvest/tool/capacity planning; intermediate chains | 01–03, 09 | Actual material receipt and two-step product |
| Recipe knowledge, food-dependent research, Rationality | 04, 08 | Real tick, completion and newly permitted recipe |
| Mix One, Mix All, ordinary/critical failure, output count | 03, 05 | Useful output and diagnosis; random failure optional |
| Storage source and proximity; tools retained in pack | 06 | Successful remote-stock consumption beside store |
| Queue dependencies, stop/edit, logout loss | 07 | Success ledger distinct from client plan |
| Alchemy and manufacturing | Core | Iron/Steel Bar, sword, shield and torch |
| Potion | Bench A | Make a catalog-valid potion or catalyst; use it only if it has a registered consumable effect, otherwise deliver as material |
| Crafting | Bench B | Make Quartz Lens and fit an authored survey instrument |
| Tailoring | Bench C | Research the required branch, produce a catalog garment and equip it |
| Engineering | Bench D | Make a registered engineering product and use its implemented effect or deliver it; no invented trap placement |
| Summoning | Caravan handoff | Produce an actual owned creature in the dedicated adventure |
| Rare outcomes and production perks | Bench E | Inspect a disclosed supplied rare exemplar; compare valid modifiers. Natural rare rolls are optional, never a completion gate |

## Implementation dependencies and audit

New work: Cinderbank map/orders, recipe-linked objective ledger, a borrowable production/research profile, bounded stock, guide overlays and reconstruction of remaining queue work. Validate research book registration, native item model and recipe linkage before production. Exact success budgets derive from the live catalog, with explicit refill after unlucky rolls.

Audit food at 0 and below, insufficient ether, wrong tool/source, nonpositive-food research pauses, duplicate book use, already-known research, original research active on entry, full output slots, movement away from Storage during a batch, queue stop versus in-flight server result, restart between output and delivery, rare substitution and two overlapping private orders. Every result must preserve exact completed goods and offer a next action.

## Human playtest emphasis

Apply the shared six-newcomer protocol. Target 5/6 diagnosing a real recipe blocker and 4/6 completing the revised order without mechanical prompts. At least 5/6 should find a partial batch's actual output and resume only the missing work. Record research wait separately; if it dominates the session, change the structure rather than hiding the timer. A changed-source replay tests whether the lesson taught source rules instead of a particular bench location.

## Source audit

- [Recipe catalog](../../../../dev-server/config/eloria/recipes.txt), [recipe outcomes](../../../../dev-server/eloria/recipes.py), [knowledge](../../../../dev-server/eloria/knowledge.py), [book tuning](../../../../dev-server/config/eloria/books.txt): actual chains, research and failure definitions.
- [World runtime](../../../../dev-server/eloria/world.py): storage-source checks, tools, resource costs, mixing loops and research ticks.
- [Native client](../../../godot-client/src/app/main.gd): Manufacturing controls, client-local queue, source toggle and research display.
- [Rare mixes](../../../../dev-server/eloria/rare_mixes.py), [perks](../../../../dev-server/eloria/perks.py): specialist outcomes without mandatory random rolls.
