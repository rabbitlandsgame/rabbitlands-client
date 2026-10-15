# Eight roads after the lantern

**Storyboard collection · 9 September 2026 · First six implemented; novice playtesting pending**

The first six adventures are now playable through **Help → Practice adventures** or `#tutorial adventures`. See the [implementation and play guide](implementation.md) for entry commands, optional exercises, recovery, isolation and validation. Worship and PvP remain design proposals.

[Open the illustrated collection](index.html). Each adventure has a full specification and an illustrated storyboard. These follow the scene, gameplay evidence, recovery and transfer-test format of [The Second Bell](../invasion-tutorial/README.md) and [The Borrowed Sky](../magic-tutorial/README.md).

The people rescued in the first three adventures are rebuilding the road beyond Four Gates. Their needs introduce production, character choices, companions and cooperation. Each story can stand alone: a returning player gets one sentence of context and an immediate practical problem. The earlier adventures are invitations, not a compulsory chain of eight more tutorials.

| Order | Adventure | Learning focus | Proposed first-run duration | Specification |
| --- | --- | --- | --- | --- |
| 1 | The Missing Caravan | Summoning and behavior | 30–40 minutes | [Read](summoning/README.md) · [Illustrated](summoning/storyboard.html) |
| 2 | The Broken Workshop | Production, research and batch planning | 35–45 minutes | [Read](crafting/README.md) · [Illustrated](crafting/storyboard.html) |
| 3 | The Wraith's Three Trials | Attributes, nexus, skills and perks | 30–40 minutes | [Read](character-development/README.md) · [Illustrated](character-development/storyboard.html) |
| 4 | The Quartermaster's Test | Equipment, protection and maintenance | 30–40 minutes | [Read](equipment/README.md) · [Illustrated](equipment/storyboard.html) |
| 5 | The First Commission | Trading, marketplace and delivery | 30–40 minutes | [Read](trading/README.md) · [Illustrated](trading/storyboard.html) |
| 6 | The Sealed Road | Parties and gauntlets | 35–45 minutes solo; optional 15–20 minute duo | [Read](parties/README.md) · [Illustrated](parties/storyboard.html) |
| 7 | The Unlit Shrine | Worship, offerings and blessings | 30–40 minutes | [Read](worship/README.md) · [Illustrated](worship/storyboard.html) |
| 8 | The Chalk Circle | PvP eligibility, zone rules and survival | 30–40 minutes solo; optional 10–15 minute spar | [Read](pvp/README.md) · [Illustrated](pvp/storyboard.html) |

Durations exclude optional experiments and are hypotheses for human testing. Each proposal has ten core storyboard frames; a frame can contain several separately saved gameplay objectives. A frame count is not an implemented quest-stage count.

## A connected setting, independent invitations

The caravan brings tools to the workshop; the workshop supplies the quartermaster; the commission funds the next road expedition. The Wraith offers a reflection before the player commits to a specialization. Shrine keepers and arena stewards offer optional paths once the player understands what a persistent choice means.

Contextual invitations remain a future addition. The implemented first six are accessible through Help or `#tutorial adventures`; individual commands resume saved progress. The specifications below retain the proposed contextual triggers and later transfer tests for human evaluation.

Every map has one refuge and four short courts. The player sees what their actions change: wagons reunite, workstations light, trial tokens fill, packs become ready, a commission board clears, a road opens, shrine lamps kindle or chalk circles become familiar. The route is guided; the final solution can vary.

## What each storyboard specifies

Each specification includes a narrative premise, access requirements, a four-gate map, ten frames with composition and guide dialogue, actual native gameplay, completion evidence, recovery and observations. Feature matrices assign specialist mechanics to optional experiments. Implementation gaps are separated from existing systems. Each adventure has a changed final challenge, a later transfer task and topic-specific engineering checks.

Read the [shared gameplay and playtest contract](design-contract.md) alongside any individual proposal. It defines checkpoint semantics, private practice, markers, assistance, audit events, accessibility and the common human test protocol. Those requirements apply to every frame, including optional experiments.

The [source findings](source-audit.md) summarize current behavior and concrete gaps that must be resolved during implementation, including catalog content, service isolation and UI inconsistencies.

## Suggested production sequence

Build summoning first to establish reusable practice companions and ownership evidence. Build production and character development next; these have strong everyday value and expose knowledge, queue and persistent-choice requirements. Equipment can then reuse the loadout work. Trading requires a separate practice economy, and parties require actual session-backed companions plus a genuine two-player validation pass. Worship and PvP follow after practice-state restoration and policy displays have been verified.

Each adventure needs its own novice test before building the next one. Do not use these duration targets or an automated completion run as evidence that the teaching works.

## Maintaining this collection

The Markdown specifications are the source. `build_storyboards.py` renders the local HTML collection and scene diagrams from them; it uses only the Python standard library and has no network dependencies. Run it from any directory with `python path/to/build_storyboards.py`. The illustrations are blocking diagrams, not client screenshots or final environment art.
