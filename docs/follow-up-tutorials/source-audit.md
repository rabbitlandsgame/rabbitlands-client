# Source findings that shape these storyboards

**Read-only audit · 9 September 2026 · No gameplay fixes are included in this storyboard delivery**

This is a compact index of the concrete implementation requirements discovered while drafting. Each full specification explains the corresponding scene and recovery behavior. All eight new maps, guides, quest stages and objective evidence are proposed content.

| System | Observed current behavior | Storyboard consequence |
| --- | --- | --- |
| Character attributes | The active model has twelve directly purchased attributes; the old six are retained for save migration. Carry directly controls capacity at 20 per point. | Teach Carry and the current twelve-attribute catalog; do not repeat the retired Physique/Coordination model. |
| Summon behavior | Native behavior selection requires Summoning 30, independent of individual summon recipe requirements. | Borrow a labeled qualified profile, then inspect the real character's restriction after departure. |
| Summon decay | Baseline is 10 HP per 20 seconds; the current Summoner perk path uses 5. | Show an actual tick and use the offered perk name, not the internal advanced-summoner helper name. |
| Stone content | The active catalog contains no removal items or summoning stones, despite recognized runtime handlers. | Register handler-compatible items and native representations before the removal scene or optional stone pen can run. |
| Research | Default books require 600 pages; Book of Steel Smelting is registered. Rationality is directly purchased and the current purchase ceiling is 100. | Lend a disclosed Rationality profile and let six ordinary research ticks run alongside production; validate actual pacing. |
| Production queue | Queue state lives in the native client and does not survive logout; goods already produced persist. | Resume the remaining order openly; never claim the old queue survived or reproduce completed goods. |
| Repairs | The command targets a slot or matching exact name, selects the most worn matching copy, and repairs immediately when funded. | Teach slot verification and actual direct-command semantics; a quote/confirmation dialog is new UI work. |
| Marketplace UI | Native Buy purchases the whole selected listing. Partial quantity, selling, cancellation and renewal have command paths. | Teach the actual controls and distinguish whole-listing cost; do not draw an unimplemented selling/quantity form as current UI. |
| Listing duration | Auction creation defaults to 365 days, while command help still says seven for selling. | Reconcile help during implementation and use authoritative listing expiry in the lesson. |
| Gauntlet admission | Participants are captured from nearby same-map party sessions; scaling uses the strongest participant's A/D-derived combat level. | Preview who will enter, gather absent members and explain what the difficulty is based on. |
| Gauntlet cache | The current claim loop may mark a participant claimed even when all or part of the roll cannot be carried. | Implement a capacity-preserving entitlement or atomic preflight before shipping the cache lesson. A warning alone does not make retry safe. |
| Worship catalog | Lucaa references Blue Lupine and Red Rose, both absent from the active item/resource catalog. Many other patrons reference absent legacy items too. | Register missing flowers and actual harvest definitions for the selected core path; validate every optional offering. Jayden's first five potion offerings are an available alternative design. |
| Worship rules | Join starts at rank -2 / -8% in the patron skill; offerings add a rank, up to +5 / +20%. Max three gods, with conflicts checked. | Demonstrate initial cost, source-specific offerings and compatibility; do not present worship as an instant universal bonus. |
| Priest extras | Aluwen's definition includes extra-benefit prose that the inspected generic priest response path does not expose as service options. | Keep those extras out of mandatory play until real menu/handler paths are implemented or verified. |
| PvP policy | Public zone definitions are marked provisional. Caps affect A/D. Death handling has distinct novice, stone, no-drop and special-day ordering. | Present effective rules from the server; do not promise universal normalization or zero consumable cost in every no-drop area. |
| Private services | Existing magic practice isolates the character and blocks public actions; auction escrow, parties, gauntlet runs and item ledgers have their own state. | Explicitly extend isolation to the relevant services before enabling practice trading, groups, worship or death exercises. |

## Reproducing the content checks

Read the active `dev-server` profile, not the retired sibling `eloria-server` and not only the introductory server README, whose older feature counts/attribute wording do not describe all current systems. Key modules are [models](../../../dev-server/eloria/models.py), [perks](../../../dev-server/eloria/perks.py), [items](../../../dev-server/eloria/items.py), [world](../../../dev-server/eloria/world.py), [auction](../../../dev-server/eloria/auction.py), [gauntlets](../../../dev-server/eloria/gauntlets.py), [gods](../../../dev-server/eloria/gods.py), [PK](../../../dev-server/eloria/pk.py) and the [native client](../../godot-client/src/app/main.gd). The individual storyboards link the focused UI/config sources.

The static catalog check compared god offering names and stone names against the active `eloria.items.ITEMS`, rather than assuming a recognized helper implies playable content. These observations are scoped to this checkout and should be refreshed before implementing each adventure.

## Storyboard artifact verification

The collection renderer validates ten numbered frames and all six required fields in each adventure. The delivery was checked for local-link/anchor resolution, browser JavaScript errors, responsive overflow and SVG label bounds at desktop and narrow widths. Search, topic filters, empty results and expansion/collapse of all scene evidence were exercised.

These checks validate the review documents. They are not game-engine traversal tests or human learning results. No new tutorial can be entered in the client from this delivery alone.
