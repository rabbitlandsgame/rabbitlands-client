# The Quartermaster's Test

**Equipment and maintenance storyboard · Proposal · Solo · 30–40 minutes · Ten core frames**

[Illustrated storyboard](storyboard.html) · [Collection](../README.md) · [Shared contract](../design-contract.md)

At **Wayfarer Bastion**, quartermaster **Nesh** must send a small rescue team through a storm-damaged road. Three packs stand open. The player tests equipment, prepares one pack for each hazard and repairs the worn weapon the team needs for the last crossing. The question in every scene is practical: what will this arrangement help the wearer do?

**Nesh:** “Lay out the journey before you lay out the gear.”

Packed supplies and visible equipment changes carry the story. A safe test lane makes a poor choice recoverable. There is no requirement to win a damage contest or acquire rare loot. The tutorial teaches preparation beyond Second Bell's basic equip-and-fight lesson.

## Access and four-gate map

Offer after a player acquires a second comparable equipment item or encounters wear. Use an isolated practice profile with a small verified kit and exact tracked item instances. The maintenance demonstration starts with an openly pre-worn practice item; do not force random breakage or damage the player's permanent gear.

Propose **128 × 128 tiles**. Quarter Court (64,64) contains Nesh, Storage and three packs. North (64,101) is Fitting Hall, East (103,64) the Weather Yard, South (64,27) the Repair Bench and West (25,64) the Rescue Road.

| Gate | Composition | Purpose |
| --- | --- | --- |
| North · Fitting Hall | Clearly labeled one-hand, shield, two-hand and bow racks | Slots, requirements and compatible arrangements |
| East · Weather Yard | Separated physical and elemental test lanes | Match protection and understand tradeoffs |
| South · Repair Bench | Two visibly similar tracked items and cost ledger | Durability, exact selection and repair |
| West · Rescue Road | Mixed hazard and limited load allowance | Independent preparation and maintenance decision |

All comparison exemplars must be existing catalog definitions/instances or explicitly registered practice content. Art alone cannot establish weight, rarity, protection or two-handed behavior.

## Ten storyboard frames

### 01 · Three packs, three journeys — 3 minutes

**Picture:** Nesh points at a weathered route sketch. Three open packs sit beside equipment with readable names.

**Voice:** “This one crosses rubble. This one crosses heat. Read what each piece actually gives.”

**Play:** Enter the practice profile, inspect an inventory item through the native eye/description action and compare it with the equipped item. Locate weight, damage/armor range and relevant modifiers. Use the existing equipment summary, including `#arm` where needed, to see the combined result.

**Learn:** An item's description and the character's total equipment effects answer different questions.

**Evidence:** Inspection and accurate current kit state. No combat mastery credit yet.

**Recovery / observe:** Keep the full description readable at the smallest supported window size. Can the player identify one benefit and one cost without guessing from rarity color or model size?

### 02 · A hand can hold only so much — 3 minutes

**Picture:** A one-handed weapon and shield hang beside a two-handed weapon. Changes are visible on the player's model.

**Voice:** “Try both arrangements. Look at what had to leave your hands.”

**Play:** Equip a compatible one-hand/shield arrangement through ordinary drag or double-click. Change to a verified two-handed item and inspect the resulting occupied/excluded slots. Restore a chosen arrangement and make a short real attack in the safe lane.

**Learn:** Slot compatibility is authoritative; a two-handed weapon excludes a shield. Visual appearance should follow actual equipment state.

**Evidence:** Correct equipment packets/instance ownership and a valid attack with each requested arrangement, without requiring a particular damage roll.

**Recovery / observe:** Reserve inventory room for displaced gear. Test a full pack before swaps. The player should explain an equip rejection from its actual reason rather than assume the item vanished.

### 03 · Requirements are part of the kit — 3 minutes

**Picture:** One rack label names the requirement on a currently unusable item; a usable alternative sits alongside it.

**Voice:** “The best piece for this journey is one you can actually use.”

**Play:** Inspect a registered item with a genuine current requirement, attempt the ordinary equip if appropriate, then choose a valid alternative or accept a disclosed qualified practice profile for the demonstration. Read all blockers from actual item rules; do not assume every item has a Human Nexus requirement.

**Learn:** Ownership does not guarantee equipment eligibility, and a tutorial loan does not permanently unlock it.

**Evidence:** Valid rejection/blocker and a subsequent usable kit. If no suitable current item enforces the planned requirement, author a different real constraint such as incompatible slots instead of inventing one.

**Recovery / observe:** Give an alternative in immediate reach. At departure revisit the requirement on the real character. Record whether a tester confuses item level, skill and nexus.

### 04 · Armor meets the blow — 4 minutes

**Picture:** East's first lane has one physical attacker and a broad retreat path. The equipment summary stays visible before entry.

**Voice:** “Take a few blows, then compare what the kit was meant to change.”

**Play:** Inspect two valid armor arrangements, enter the physical lane with one, retreat and compare with the other. Use actual combat and healing. The observation centers on the reported effective armor/defense modifier and relevant damage events, not an expectation that every hit is smaller.

**Learn:** Armor, defense and damage rolls are distinct. A heavier kit may have costs in other modifiers or carrying capacity.

**Evidence:** Real incoming physical attacks under both recorded kits and the expected modifier change. A short sample illustrates variability; it does not prove statistical superiority.

**Recovery / observe:** Pause comparisons in the refuge. Failed flee follows ordinary rules with an explicit practice rescue fallback. Ask what the player expected after a surprising large hit.

### 05 · Heat asks a different question — 4 minutes

**Picture:** The next lane has a labeled heat hazard and a matching elemental protection rack. Its shape differs from the physical lane.

**Voice:** “That attack is heat. A number called armor is not the whole answer.”

**Play:** Inspect current heat protection, choose a piece that improves it and enter a short real typed-attack encounter. Compare the server's actual protection and damage components with a known baseline. In replay change the threat to cold or radiation and let the player inspect the appropriate modifier.

**Learn:** Match equipment to damage type; protection is not a guarantee of invulnerability. Magic Ward and physical Shield are not substitutes for reading equipment.

**Evidence:** Correct typed incoming attack and effective matching equipment modifier. No mandatory threshold based on a lucky damage roll.

**Recovery / observe:** Use an eligible actor capable of the declared damage type. If presentation cannot expose that type accurately, add labeled practice threat feedback as new work before testing learning.

### 06 · Reach, ammunition and room — 4 minutes

**Picture:** A bow lane opens beside a broad melee lane. The ammunition stack and retreat route remain visible.

**Voice:** “Distance needs supplies too.”

**Play:** Equip a catalog-valid bow and compatible ammunition, take an actual aimed shot, then change to a usable melee arrangement and finish a short encounter. Compare ranged/missile modifiers and pack space in the equipment summary. Second Bell graduates can use the short refresher path.

**Learn:** A ranged loadout includes ammunition and relevant modifiers, plus a plan for close contact. Weapon swapping does not cancel engagement automatically.

**Evidence:** Ammo consumed, actual ranged hit and valid melee attack after a real swap. Do not require re-learning the entire Ranging window.

**Recovery / observe:** Recover after missing ammo, incompatible item or no room for displaced equipment. Record whether the player checks the current weapon instead of repeatedly clicking a stale action.

### 07 · Wear belongs to this item — 3 minutes

**Picture:** South's bench holds two copies of one item with distinct instance identities and durability. One is explicitly marked as borrowed and pre-worn.

**Voice:** “Same name. Different history. Check the one you are taking.”

**Play:** Inspect each tracked item's actual durability and identity through existing descriptions, adding a proposed read-only detail view if necessary. Equip the worn one for a brief ordinary use, then inspect it again. Read any wear event without requiring one to occur.

**Learn:** Durability belongs to a particular instance; a random wear chance is not a guaranteed loss every attack. An item name alone may match several copies.

**Evidence:** Correct instance selection and pre/post durability values. The demonstration begins with disclosed preexisting wear, so no random event blocks it.

**Recovery / observe:** Test sorting and slot changes. The marker/objective follows the instance, not a remembered inventory index. Never destroy a player's real gear to make the lesson dramatic.

### 08 · Pay for the right repair — 4 minutes

**Picture:** The repair bench shows the selected instance beside practice coins, with the other copy kept visible for comparison.

**Voice:** “Check the price and the piece. Repair changes this one.”

**Play:** Use the current `#repair` command with the exact current slot. First request with insufficient practice gold to receive the real cost response; then withdraw enough and repeat. This command currently repairs immediately when funded—it has no separate quote-confirmation step. Inspect restored durability, gold spent and the untouched other copy.

**Learn:** Repair cost depends on missing durability and item weight; selection by name can choose the most worn matching item. Use a verified slot for precision.

**Evidence:** Actual rejection without spend, followed by one repair transaction on the intended instance and exact coin delta.

**Recovery / observe:** Revalidate the slot after sorting. A proposed future repair dialog must show cost and confirm exact identity before mutation; do not depict that dialog as already present.

### 09 · Pack for the real problem — 6 minutes

**Picture:** West's revised route has one typed hazard, one ordinary enemy and a supply bundle within a limited carry allowance.

**Voice:** “Choose the kit. Bring the people and their supplies back.”

**Play:** Inspect the route, prepare a compatible kit, choose whether a worn practice item is worth repairing, carry the required supplies and complete the rescue. Change damage type and the damaged item from earlier scenes. Several validated loadouts must work; protection, food, ammunition and free capacity are all available.

**Learn:** Equipment decisions serve a trip rather than a single maximum stat.

**Evidence:** Successful rescue/delivery, compatible equipment and at least one preparation choice responding to the changed condition. No prescribed best-in-slot answer.

**Recovery / observe:** Offer return to the bench, bounded practice gold and an explicit retry. Record missed requirements, self-correction and whether the player notices the damaged copy rather than repairing by name indiscriminately.

### 10 · The packs are ready — 2 minutes

**Picture:** Three packed bundles sit beside the departing team. The player's original equipment and durability return unchanged.

**Voice:** “Inspect what you own before buying what you think you need.”

**Play:** Restore the permanent profile, inspect one current item and compare a plausible alternative already visible in the catalog or inventory. Identify the next useful improvement without requiring a purchase or repair. Depart or revisit a lane.

**Learn:** Practice gear and repairs do not become public possessions, and useful upgrades depend on the intended activity.

**Evidence:** Exact item identities, equipment slots, durability and coins restored; journal stamp once.

**Recovery / observe:** Exit while a repair or equip request is pending must settle within the practice namespace. Later ask the player to prepare an owned kit for a changed threat and locate the real cost of any proposed repair safely.

## Optional equipment trials and coverage

| Feature | Lesson | Demonstration |
| --- | --- | --- |
| Descriptions, aggregate modifiers, load and comparison | 01, 04–05 | Inspect item and effective kit, then perform matching activity |
| Slots, two-handed exclusion, equip requirements | 02–03 | Valid arrangements and truthful rejection |
| Physical versus heat/cold/radiation protection | 04–05; Trial A | Two matching threat/protection comparisons |
| Ranged ammo and close-range transition | 06 | Actual shot and compatible swap |
| Tracked durability, random wear and exact identity | 07 | Read two copies without waiting for breakage |
| Repair cost, direct command semantics and selection | 08 | One actual paid repair, other item unchanged |
| Rarity, affixes and conditional perk effects | Trial B · the unusual piece | Compare supplied valid common/rare exemplars; equip and observe registered modifier. No forced loot roll |
| Dual wield and Two Handed Wielding perks | Trial C · two ways to fight | Borrow eligible perk profile, inspect actual bonuses/penalties and execute compatible attacks |
| Degradation/breakage and wear-reducing perks | Trial D · an old blade | Inspect registered transformation chain and genuine wear event in an optional extended run; no required destruction |
| Independent preparation | 09–10 | Changed trip with multiple accepted loadouts |

Trials take 5–7 minutes each. No salvage, enchanting, socketing or repair NPC service is implied unless its actual control and runtime are separately verified.

## Implementation dependencies and audit

New content includes the Bastion map, hazard actors, instance-safe practice kit, readable durability/identity feedback where missing and objective evidence. A cost-confirming repair UI is a recommended follow-up dependency, not a prerequisite quietly assumed by this storyboard; core 08 teaches the existing direct command accurately using practice coins.

Audit duplicate names/different rarity, item sort while selected, full pack during equip, no ammo, incompatible slots, wrong instance ownership, insufficient repair gold, fully repaired item, duplicate repair request, wear between cost observation and repair, broken/degraded instance, buff/perk expiration, two private kits and departure during a pending mutation. Comparison data must use effective stats with any temporary effects clearly shown.

## Human playtest emphasis

Apply the shared protocol. Target 5/6 assembling a compatible kit and repairing the intended copy, and 4/6 adapting to the changed damage type and load constraint in the final rescue. Ask testers to locate the supporting modifier before entering the lane. Do not mark a valid build wrong because random damage differs from the guide's expectation. Later transfer uses owned equipment and no required purchase.

## Source audit

- [Items](../../../../dev-server/eloria/items.py), [instances](../../../../dev-server/eloria/item_instances.py), [rarity](../../../../dev-server/eloria/rarity.py): equipment definitions, identity and modifiers.
- [World runtime](../../../../dev-server/eloria/world.py): equipment swaps, wear, typed attacks and direct `repair_item` behavior.
- [Perks](../../../../dev-server/eloria/perks.py), [ranging](../../../../dev-server/eloria/ranging.py): conditional weapon effects and ranged rules.
- [Native client](../../../godot-client/src/app/main.gd): inventory inspection, equipment controls and feedback.
