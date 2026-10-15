# The Borrowed Sky: playable client integration

Stillglass Observatory is implemented in the main Godot client and sibling
`dev-server`. Its private 120 × 120 map has four gates, 39 saved core objectives
and 31 objectives across four optional experiments. Players use the normal
Left Shift spell ring, spellbook, quick slots, actor and ground targeting, inventory,
storage, merchant, active effects and dialogue.

## Play

For this branch, run **[`test-magic-tutorial.bat`](../../test-magic-tutorial.bat)**.
It starts the matching sibling `dev-server` checkout on localhost:2013
with a separate database. Log in as **RingStudent**, password **ringpractice**,
then enter **`#tutorial magic`**. `-Fresh` starts another local profile without
deleting saved progress; `-ServerRoot` selects another matching server checkout.

Launch [`prototypes/last-lantern/play.cmd`](../../prototypes/last-lantern/play.cmd)
with the matching updated client and server. Finish or leave The Last Lantern,
then enter **`#tutorial magic`** in chat. Ilyon's adventure dialogue in Four Gates
also offers **The Borrowed Sky: magic practice**. An active older Four Gates
walkthrough retains its own dialogue; the explicit command remains available.

Hold **Left Shift** to open the Quick ring. Hover a class or press its displayed
number, then hover an effect. **Right click** cycles available target types;
**scroll** changes power. Click the effect or press its number to choose it.
Release Shift before aiming in the world. Target uses a compatible selected
recipient or waits for an actor click; Burst and Blink wait for a ground click.
**Escape** cancels targeting. Releasing Shift before choosing dismisses the ring.
The **Ring** button opens it without holding a key; Escape dismisses it.

**Alt+number** remains the quickbar shortcut. Each icon shows its saved target
type at top left and saved power at top right. A submitted cast updates the
assigned slots of that family; browsing or cancelling does not. Ring choices
and pins persist per character. **Spells / Ctrl+S** remains the reference book.
The selected spell shows a server quote for its actual power, ether cost,
materials and focus substitution. The normal book search and scope filter work.

**Ask Sera** repeats contextual instructions and records assistance. Speak to
Keeper Sera in Lens Court for practice refills or to retry the current lesson.
**Leave tutorial** pauses and restores the permanent character at the Four Gates
beam. `#tutorial magic` resumes the saved checkpoint. Disconnecting saves the
private encounter; unfinished timed observations restart on reconnect so they
can be observed during play. The guide's next instruction replaces the marker
as soon as its real objective completes.

After the core rescue, use `#tutorial magic a`, `b`, `c` or `d` for an experiment.
These also appear in Ilyon's dialogue after The Second Bell is complete. An
unfinished experiment can be paused and resumed; it cannot be overwritten by
starting another experiment. Completed experiments are replayable.

## The rescue

| Scene | Hands-on action | Completion evidence |
| --- | --- | --- |
| A sky held together | Inspect Spells; open the ring; browse a class; dismiss; borrow attunement; collect the missing Heal sigil | Ordered UI observations for book/open/browse/dismiss, then nearby Sera responses; browsing spends nothing |
| Your hand first | Cast Heal from the ring; try the quickbar and read its corner badges; cancel a Burst cursor; switch to Target and heal Tavin | Real health gain, server resource spending and an eligible actor in range |
| Supplies | Withdraw 35 Sunleaf; use a mana potion; eat Bread | Actual storage transfer, ether restored and positive food |
| How much light? | Scroll Heal P1 → P2 → P1; check the saved quickbar power; use a charged focus; cast after its charge is spent | Correct selected power, useful healing, focus substitution and subsequent ordinary anchor consumption |
| Who is with you? | Right click to Allies near Tavin and Mira, then Burst at unaffiliated Oren | The Allies cast heals both practice guildmates and excludes Oren; the Burst really heals Oren |
| Prism lane | Cast Magic Bolt; hit the pair with Magic Burst; observe a poison tick; finish and loot the encounter | Both Burst targets take damage; a real timed poison tick occurs; defeat and loot are recorded |
| Protection | Use Shield, Magic Ward and Heat Ward; take the prism's matching attacks; Dispel poison; refresh a ward | Ordinary buffs, real incoming spells, removal of harmful modifiers and poison, normal effect durations |
| Folded Gate | Blink across an impassable gap; use Haste while walking | Valid landing within 15 tiles and movement with the effect active |
| Hidden garden | Conceal before approaching the patrol; find Oren with Reveal Burst; talk to him and choose Return to Sera | Reveal must find Oren, who then lowers his own concealment; nearby dialogue explicitly asks Sera to recall him to Lens Court. Waiting leaves him in the garden. |
| The fitting | Cancel a Transmute quote; convert one Bones; buy and install a Wood Plank | Inventory slot/item validation, actual gold, normal merchant transaction and nearby object use |
| The last crossing | Choose spells and equipment, defeat the West guardians, heal and escort all three apprentices | Living enemies prevent escort; insufficient health prevents movement; all three must reach the rally |
| The borrowed sky | Align the lens; Recall at P1 | Nearby lens interaction, all companions visibly home, restored permanent profile and one-time completion |

There is no global failure timer. The final rescue provides fewer mechanical
prompts, with contextual help available. Sera explicitly recharges practice
ether after the resource exercise and when the player chooses to begin the last
rescue. Other replenishment uses the supplied potions, normal food recovery,
Storage or Sera's assisted refill.

### Ring training compatibility

Clients advertise `spell_ring_v1`. The existing `book` checkpoint gains ordered
book-open (7), ring-open (20), class-browse (21) and ring-dismiss (22) observations
over `ELORIA_TUTORIAL_UI`. The saved `sky_ring_intro` substep survives reconnects;
the 39 core checkpoint numbers are unchanged. Out-of-order or repeated events
cannot skip it. Choosing a spell, releasing Shift after choosing, and focus loss
do not report dismissal. These UI events never complete a cast or aiming-cancel
lesson: those continue to use the existing resolved gameplay checks. Later cast
lessons teach the ring without requiring a particular input device to succeed.

Ring-capable clients receive ring-specific hints and highlights for Ring,
target type, power and quickbar. The guide moves beside the visible ring.
Older clients retain the original book guidance and progression; resuming with
an older client does not leave a ring-only gate in the way.

Checks for this change: the server's 42 `test_sky.py` cases pass, including both
39-objective playthroughs (ring and legacy book), ordered/resumable orientation,
and rejection of UI observations as cast evidence. Client casting, comparison,
world-input and ring-guide tests pass. `test-magic-tutorial.bat -Check` logs a
real Godot client into a disposable local server and completes the introduction
through the actual book button, Left Shift, class shortcut and Shift release.
`test_magic_ring_tutorial.gd -- --render` captures native guide/ring layout.

## Optional experiments

| Experiment | Practice |
| --- | --- |
| A — Living equations | Regeneration's real tick; Life Drain's actual damage/healing; Ether Drain against a consenting non-ally inside the private PK arena; an empty target; up to three genuine low-Magic Heal attempts to observe success/fizzle spending |
| B — Prism and steel | Four damage types; separate borrowed Magic Offense and Defense changes; Cold, Radiation and Elemental Wards; each weakening spell followed by its matching bolt; Cripple, Accuracy and Elemental Weapon followed by real equipped weapon hits |
| C — The unbroken circle | Magic Immunity rejects the prism's hostile cast; Disrupt damages a hostile summon; Shield Burst applies around the apprentices |
| D — Fold and value | P5 Recall's actual portal chooser; Blink out of the annex; charged Hearthstone Focus; deposit it and compare a mismatched Riftglass Focus; common Transmute; inspect an Uncommon vessel's P3 requirement, then convert it at P3 |

Together these routes exercise all **31 spell families** in the current
86-variant book. They do not require casting every scope variant. The fizzle
exercise never forces a random failure: it ends after the first fizzle or three
attempts and reports which happened. Later rarity thresholds remain visible in
the normal Transmute chooser and are covered by spell-system tests.

## Practice isolation and recovery

The server creates a separate practice `Character` with an internal inventory
owner, its own skills, attributes, sigils, equipment instances, supplies, XP and
quest progress. Ordinary gameplay operates on that character. The database save
boundary serializes its checkpoint into the permanent account without replacing
the permanent character's possessions or equipment instances. Ordinary practice
XP stays private; fixed lesson bonuses advance the permanent character separately.

Each account owns a separate map, companions, guardians and private practice PK
zone. Borrowed items cannot be traded or taken to another map. Recall destinations
are restricted to the practice annex until P1 Recall restores the permanent
profile. Death returns the player safely to Lens Court; the encounter remains.
Leaving clears practice effects and actors. Completion retires practice item
instances and grants **25 gold in permanent Storage once**; labs grant no repeat
gold. Borrowed Magic 104 and practice sigils are not transferred.

Completed gameplay lessons now grant permanent milestone XP: the core route
awards **1,545 Overall, 1,120 Magic and 100 Engineering XP** in total. Skill XP
is included in the Overall total. Most spell lessons award 40 Magic; the final
rescue awards 100 Magic, and Recall awards 60 Magic plus 150 Overall. Opening
the spell book, borrowing the profile, cancelling previews and starting the
final encounter give no XP.

Experiments have independent, one-time bonuses: A grants 200 Magic + 250 Overall;
B grants 640 Magic + 690 Overall; C grants 120 Magic + 170 Overall; D grants
240 Magic + 290 Overall. Each includes 50 Overall for finishing. Native chat
identifies XP saved to the permanent character; borrowed HUD stats remain in
place until returning. The XP, receipt and practice checkpoint share one saved
permanent row before notification. Repeats and already completed experiments
cannot pay again, and old completed routes receive no retroactive grant.

Saved final-rescue positions and health survive reconnects, including already
escorted companions. If an unfinished loot exercise loses its temporary bag on
disconnect, a guardian is openly restored so actual loot can still complete it.
The last five completed runs retain compact spell outcome records, per-stage
elapsed times, assistance and recovery counts in `quest_state.sky_results`.
Elapsed times include pauses; they are diagnostic evidence, not active-play-time
measurements or a novice score.

## Engineering and verification

The authored geometry, client collision and server terrain come from
[`tools/build_stillglass.py`](../../tools/build_stillglass.py). The walk grid has
5,617 traversable tiles before closed-gate restrictions. Closed destination
courts reject Blink bypasses. The gap and Recall annex require real movement
spells. Markers follow current actor positions and provide a nearby approach.

The server content lives in `dev-server/eloria/sky.py` and `sky_lessons.py`.
The client uses `src/world/sky_scene.gd`, the existing quest guide and native
spell UI. The implementation also fixes creature spell damage stopping at 1 HP,
includes Cripple's evasion modifier in creature melee checks, cancels timed magic
when a creature is removed, and sends movement before a replacement actor when
crossing a PK boundary to prevent a duplicate client step.

Automated coverage includes the full core route, all four experiments, saved
partial rescues, permanent item instances, independent map ownership, paused lab
resumption, actual focus/power costs, invalid Blink and rarity selections,
death/loot handling, cancellation and the practice request boundary.

Verification on 9 September 2026:

- Full server suite: **2,133 tests and 498 subtests passed**.
- Latest magic/tutorial regression run after the reconnect fixes: **297 passed**,
  including 16 Stillglass tests.
- Native TCP playthrough: all 39 core objectives and all four experiments
  completed through gameplay; reconnects resumed unfinished lessons.
- Native object picking succeeded for the cabinet, workbench and lens. The
  Recall chooser and disabled P1 Uncommon Transmute quote were captured and
  visually checked.
- Godot spellbook, selected-power quote, utility selection and tutorial protocol
  fixtures passed; shared asset placement validation passed.
- Before milestone rewards, the final QA account had core and all four labs complete, permanent Magic 0,
  exactly 25 reward gold in Storage, no remaining practice checkpoint, and
  location Four Gates `(360, 226)`.

`godot-client/tests/integration/rendered_sky.gd` drives the real client over TCP
through the native callbacks and captures the playthrough. Set
`ELORIA_INTEGRATION_PORT` and `ELORIA_ARTIFACT_DIR` for an isolated loopback QA
server with account `SkyQA`; `ELORIA_SKY_EXPERIMENTS=1` adds the experiments.
The QA server accelerates walking/combat scheduling, not quest progression or
spell outcomes. Production timings are retained in normal play.

If a required spell target is defeated before the intended observation, the
prism restores that exercise after a short pause and says so. Restored targets
do not count as completed actions. Client capability negotiation and creature
replication also run after reconnect, so the guide and actors remain usable.

The [storyboard's human playtest protocol](README.md) remains the acceptance
plan for onboarding quality. Automated completion establishes reachability and
mechanical correctness; it does not establish the proposed 45–55 minute novice
duration or comprehension targets. No human playtest is claimed here.
