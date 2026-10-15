# Six playable follow-up adventures

The first six storyboards are implemented in the native client and `dev-server`: 103 main objectives and 22 optional exercises with 74 further objectives. Worship and PvP remain proposals. The duration estimates in the storyboards still need novice playtesting.

Cinderbank and Reedway now have dedicated environment polish passes. The workshop has distinct work areas and saved machinery changes; the caravan camp has woodland pens, detailed wagons and saved rescues. See the [Cinderbank art review](crafting/polish.md) and [Reedway art review](summoning/polish.md). The other four follow-ups retain their initial shared environment kit; gameplay implementation does not imply final environment art.

## Play

Run the updated server and native client together. Open **Help → Practice adventures**, or enter `#tutorial adventures` in chat and choose an adventure. Direct entries are:

| Command | Adventure | Private map | Main objectives |
| --- | --- | --- | --- |
| `#tutorial summoning` | The Missing Caravan | Reedway Halt | 19 |
| `#tutorial crafting` | The Broken Workshop | Cinderbank Works | 20 |
| `#tutorial builds` | The Wraith's Three Trials | Echo Court | 18 |
| `#tutorial equipment` | The Quartermaster's Test | Wayfarer Bastion | 15 |
| `#tutorial trading` | The First Commission | Lantern Exchange | 17 |
| `#tutorial parties` | The Sealed Road | Waystone Yard | 14 |

Each map has a refuge, four gates, a guide and a supply cabinet. Follow the visible world marker and instruction card. Completed dispatches gain a lit beacon; Cinderbank changes workshop props and machinery, while Reedway returns rescued wagons to the hitching yard. Open the actual Inventory, Manufacturing, Summoning, Statistics/Perks, merchant, trade, marketplace and Party windows to perform the exercises. Walking to a marker never substitutes for the requested action.

**Leave tutorial** saves the checkpoint and restores the public character. Resume with the same command. Reconnecting also restores active practice after the client advertises its capabilities. Finish the saved adventure before selecting a different one. The guide's **Restore supplies and retry** option replenishes practice resources and restarts the current encounter; help and retries mark the attempt assisted.

An interrupted gauntlet restarts at its keeper checkpoint. Completed earlier chapters remain saved. Client manufacturing queues are intentionally rebuilt by the player after reconnecting; completed goods and server research progress persist.

## Optional exercises

After completing an adventure, append its exercise letter, for example `#tutorial crafting b`.

| Adventure | Exercises |
| --- | --- |
| Summoning | **a** different/current opponents; **b** decay and Summoner; **c** a summoning stone versus a recipe |
| Crafting | **a** potion catalyst; **b** lens crafting; **c** tailoring; **d** engineering; **e** unusual results and Careful Mixer |
| Builds | **a** attributes versus nexus; **b** toggleable perks; **c** removing a drawback |
| Equipment | **a** cold/radiation protection; **b** equipment perks; **c** dual wielding/two-handed weapons; **d** instance durability and repair |
| Trading | **a** renewal and expired returns; **b** a stale listing and refresh; **c** trading the intended worn instance |
| Parties | **a** leadership and reconnection; **b** leaving early; **c** a mutator; **duo** two consenting players |

For the duo exercise, the host enters `#tutorial parties duo` and shares the displayed code. The other player enters `#tutorial join <code>`. The host invites their displayed name with `#party invite <name>`; the guest accepts, and both gather beside Orin. Both use their own practice profiles, enter the same real gauntlet and claim separate rewards. Either can leave independently. A departing guest resets the shared crossing so the host can invite again; a closed host session invalidates the old code.

## Gameplay and isolation

- Summons use real recipes, ownership, target filters, combat, fleeing, decay and the registered stone path.
- Production consumes actual materials, tools, food and ether. Steel Smelting uses ordinary research ticks. Queue exercises require native queue controls and successful outputs; rare rolls are never mandatory.
- Attributes, nexus, purchased/effective perks, removal items, equipment slots and durability use the existing rules. Worn practice fixtures are disclosed, and repair/trade objectives check the intended instance ID.
- The exchange uses ordinary merchants, reciprocal trades, two acceptance stages, storage destinations, listings, partial purchases, cancellation, expiry and escrow collection. Its scripted buyer and prices belong to this private exercise.
- Parties use the real PartyBook, chat, leadership, gauntlet scaling, waves, fork selection, healing, individual caches and waystones. The second expedition changes the encounter arrangement. Scripted companions are identified as such; the duo exercise requires a separate player session.

Each run owns a separate World, SQLite database, market, guild service and party roster. The public Session and Character are parked outside it. Borrowed items, instance identities, skills, perks, ordinary practice XP, currency and summons cannot reach public containers or markets. Authored milestone bonuses are credited directly to the permanent character, alongside completion, assistance and resume information. Finishing restores the original Character object with its earned bonuses.

## Milestone experience

Validated objectives award fixed XP once per character and lesson. Skill awards also count toward Overall. Full core-route bonus totals are:

| Adventure | Overall XP | Skill XP included in that Overall total |
|---|---:|---|
| The Missing Caravan | 950 | 600 Summoning, 50 Defense |
| The Broken Workshop | 1,015 | 100 Harvesting, 300 Alchemy, 180 Manufacturing, 60 Engineering |
| The Wraith's Three Trials | 820 | 60 Summoning, 60 Manufacturing, 110 Attack, 110 Defense |
| The Quartermaster's Test | 810 | 180 Defense, 80 Ranging, 120 Attack, 60 Engineering |
| The First Commission | 810 | — |
| The Sealed Road | 810 | 60 Magic |

Each core total includes 150 Overall for returning to the guide. All 22 optional exercises have separate one-time lesson awards plus 50 Overall for completion. The two-player road awards each participant their own bonuses (270 Overall for the full exercise). Opening windows, inspecting items, and reviewing repair quotes pay nothing.

The native chat reports each bonus as saved to the permanent character. The practice HUD continues to show borrowed stats; returning restores the permanent stats with the earned XP and levels. Public XP and its receipt are committed before the private checkpoint, so interrupted saves, reconnects, retries and replays cannot duplicate a bonus. Previously completed core routes and labs remain ineligible; rewards are not backfilled. Ordinary practice combat, crafting and trading stay isolated.

`eloria/tutorial_rewards.py` defines the fixed amounts and receipt keys. `test_roads.py` checks each core route and lab through real gameplay, including exact permanent XP totals; `test_tutorial_rewards.py` covers interrupted persistence, replay eligibility and isolation.

Practice databases live beside the configured server database in `<database filename>.practice/`. Back them up with the public database if preserving practice checkpoints matters. They contain private test transactions, not public economy records.

## Source and regeneration

`dev-server/eloria/road_lessons.py` contains the objective sequences. `roads.py` owns lifecycle and packet routing; `road_content.py` observes outcomes and configures encounters; `road_partners.py` drives scripted participants; `road_duo.py` handles the optional guest. Actual mutations remain in the normal gameplay handlers.

Run `python tools/build_followup_maps.py` from `eloria-client` to regenerate all six GLBs, manifests, client/server collision grids and shared target layouts. Client layout and server harvest nodes use the same authored coordinates. The native guide validates the `followup` state and teaches existing controls.

Use `python tools/build_followup_maps.py --adventure crafting` for Cinderbank alone. Its dedicated generator is `tools/build_cinderbank.py`; full regeneration also calls it. It authors prop footprints and native picking dimensions alongside the art. Older crafting checkpoints inside a new prop or a closed court return to the refuge without resetting the lesson or inventory.

Use `python tools/build_followup_maps.py --adventure summoning` for Reedway alone. `tools/build_reedway.py` supplies its woodland camp, wagon tableaux, companion course, encounter positions and matching latch approaches. Older summoning checkpoints receive the same safe-position recovery. The North calling circle stages the player before summoning; the lesson uses the real wandering leash and decay.

After item changes, regenerate the recipe and knowledge catalogs with `tools/generate_manufacturing_catalog.py` against `../dev-server`, update the server content manifest hashes, and run `dev-server/tools/generate_perk_reference.py` for equipment-granted perks. Borrowed practice gear is explicitly excluded from generated public crafting and loot tables.

## Verification

The focused server run passes **83 tests**, including all six main paths, all optional exercises, real-session duo completion, reconnect/leave recovery, public-state isolation, cache capacity and companion combat locks. Tests drive real walking, harvesting, mixing, research ticks, purchases, trades, spells and combat handlers. Combat/movement timers and successful mix rolls are controlled for deterministic automation.

The complete server suite passed **2,173 tests and 498 subtests**. The distribution wheel builds with all six layout JSON files included. A final targeted crafting run also checks harvesting through the native packet dispatcher.

`godot-client/tests/integration/rendered_roads.gd` checks all six rendered maps over real TCP: the Help adventure chooser, a real first objective, object picking, storage withdrawal, leaving and resuming. The expanded paths also harvest both workshop nodes, summon an owned companion, use its behavior picker, complete the North wagon rescue and equip the sword/shield kit. `tests/test_lantern_protocol.gd` now passes 56 packet-validation checks. The latest environment regression run passes all 40 tests in `test_roads.py`; both polished maps also pass their coordinate and reachability checks. These checks establish functionality, not that a novice understands the lessons; the storyboard's observation and transfer-playtest plans remain the next human validation step.
