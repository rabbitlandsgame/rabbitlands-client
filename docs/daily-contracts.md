# Landfall Daily Contracts

Speak with **Batu Ensh at the Landfall watch house** and choose **Landfall daily contracts**. You can also open **Contracts** from the quest journal to browse your assignments while traveling. Accepting work, collecting rewards, and exchanging service marks require returning to Batu.

## Pick your work

Choose from **three assignments in each discipline**, each with two posted routes or sets of terms. Use **Discipline** on the Available tab to browse all offers or focus on one skill. The Accepted and Marks tabs remain separate from this filter.

| Discipline | Assignments | What changes |
| --- | --- | --- |
| Melee | The Watch on the Road; The Unbroken Perimeter; Clearing the Approaches | Escort the repair crew, hold its camp against changing approaches, or clear three hostile posts. Make your own melee contribution. |
| Magic | The Warden’s Call; Triage at the Watch; Breaking the Siege | Escort wounded wardens, restore real health at the recovery camp, or clear threat posts with magic. Healing a full-health character does not count. |
| Ranging | Towpath Lookout; The Distant Watch; Along the Ridgeline | Cover a moving crew, defend the lookout, or clear dispersed ambushers. Bring an equipped, compatible bow and ammunition. |
| Summoning | A Watchful Companion; Guardians of the Supply; The Burrow Hunt | Escort the patrol, defend a supply camp, or clear hostile posts using your own summon. Learn a usable summon first. |
| Harvesting | The Gatherer’s Round; The Apothecary’s Basket; A Gatherer’s Survey | Gather one fresh resource, assemble a two-resource bundle, or gather a quota while sampling three distinct nodes. Bring a Pickaxe for mining terms. |
| Alchemy | The Apprentice’s Order; From Reagent to Essence; A Shelf Ready for Sale | Mix fresh batches, gather a fresh ingredient before mixing, or mix and deliver ordinary essences for the shelves. Bring a learned recipe and your Mortar and Pestle. |

You can accept up to **three contracts** and track one at a time. Accepted objectives and rewards stay fixed if your level changes. The marked destination and Instructions explain where to go. Walk there yourself, then choose **Start** when ready. Opening the board or crossing a worksite does not begin an encounter.

The Accepted board and quest card show your current step. A two-resource basket moves its destination to the second patch when the first is finished. A reagent order changes from gathering to mixing at The True Note. Surveys mark the resource nodes you still need to sample, and the card shows the sample count alongside any remaining gathering quota.

Check **Instructions** for preparation before starting: the usable recipe or spell, tools, ingredients, and other essentials are listed with their current readiness. Summoning assignments use your own companion **summoned inside the worksite**; a creature left on the public map does not accompany you into the private patrol.

The ordinary quest card controls still apply: collapse it to the ribbon, or use **More** for Instructions, Replay, Hide, and Untrack. Hiding or untracking guidance preserves the assignment.

## Work with your party

Field patrols are private to admitted party members. A party member can join at the marked public worksite using the Contracts board. Helpers keep their personal assignments.

If you accepted the same assignment with matching encounter terms, being present for a completed encounter advances its shared objective. A different assignment in the same discipline keeps its own objectives. Each player must also demonstrate the posted discipline. You do not need the killing blow. Summoning credit comes from your own summon; ordinary attacks by another player do not satisfy it.

Crew health is visible. Use **Heal Target** to recover fallen workers. You may leave an encounter and resume later. After defeat, an explicit retry restores the crew for another attempt while retaining completed checkpoints. It does not restore your health, ether, or supplies.

During Triage at the Watch, the Heal Target controls also include living wounded crew while your healing objective remains unfinished, including after the attacks end. These are ordinary paid casts; fully healed crew stop appearing as patients.

## Report and rewards

Return to Batu when both objectives are complete. Each contract awards the displayed discipline experience, gold, supplies, and **one service mark**, in addition to ordinary gameplay experience and loot. Melee contract experience is split between Attack and Defense.

You keep harvested and mixed goods unless the posted assignment explicitly requires a handover. **A Shelf Ready for Sale** requires the listed ordinary essences when you report. Enriched results count toward mixing practice, but are never taken for the handover; mix enough ordinary stock to fill the order.

If that ordinary stock is missing, the card shows what to prepare instead of telling you to report immediately. Once the stock is ready, the destination returns to Batu.

The Apprentice’s Order can instead offer an optional donation of ordinary essences for extra gold. Its normal report remains available without donating, and the board shows the amount before you choose.

If your pack fills while gathering, store or unload the goods and return to the patch. The fresh gathering already recorded stays counted.

Exchange service marks with Batu for posted consumable supplies. Completing **five contracts in a UTC week**, in any disciplines, automatically awards **three extra marks**. There is no consecutive-day requirement.

## Daily reset

You may collect one completion per discipline per UTC day. The board displays the next reset. Unfinished accepted work survives the reset and disconnects, but still uses that discipline’s allowance on the day you report it.

One free replacement is available per UTC day before starting that discipline’s work. Use the posted replacement control at Batu; it changes the unstarted terms rather than awarding anything.

These contracts are separate from the older Daily assignment and Ilka’s standing supply orders.

## Restart for testing

For development and quest testing, use `#reset dailies all` to restart your own daily assignments, or replace `all` with `melee`, `magic`, `ranging`, `summoning`, `harvesting`, or `alchemy`. Repeat the same command within 30 seconds after reading its confirmation. You must be alive, out of combat, and outside a private encounter.

The selected disciplines get fresh offers; their accepted progress, daily completion limit, and replacement cooldown are reset. Their old scenes and choices cannot be reused. Other assignments stay intact. Experience, gold, inventory, service marks, weekly completion progress, and already paid weekly bonuses are preserved. This testing command does not undo rewards you already received.
