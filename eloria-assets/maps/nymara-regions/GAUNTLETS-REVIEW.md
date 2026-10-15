# Gauntlets: what needs a decision

Everything below is a recommendation on top of what ships. The eight roads
run with existing species, items and mechanics; these are the things that
would make them more their own.

## New bosses (built, please review the numbers)

Eight boss creatures were added to `creatures.txt` with `boss: 1`, each
scaled from its species (bar times five, blows times one and a half, level
plus fourteen to eighteen) and given a fight in `bosses.def`. They share
their species' body, so no client work; a distinctive rig each would be the
upgrade. Their drop tables are in `drops.txt`.

| boss | species | level | heals | calls |
|---|---|---|---|---|
| Boar King of the Resin Road | rootback boar | 40 | 18 x 30 | brambleback boars, 3/3/4 |
| Rime Matriarch | crystal polar bear | 52 | 30 x 30 | ice snow leopards, 2/2/3 |
| Sunscale Sovereign | sunscale basilisk | 74 | 40 x 25 | scalevine stalkers, 2/3/3 |
| Barrow Reeve | spectral forest knight | 54 | 28 x 30 | moor wisp hounds, 3/3/3 |
| Bell Warden | abyssal armoured fish | 43 | 26 x 30 | tidecoil serpents, 3/3/3 |
| Duskmane | sunmane cat | 48 | 24 x 30 | stormmane lions, 2/3/3 |
| Songstone Tyrant | prism wyrm | 66 | 40 x 25 | crystal dire wolves, 2/3/3 |
| Bund Tyrant | floodmaw | 78 | 44 x 25 | delta crocodiles, 2/2/3 |

## New drops and items (proposed, not added)

- **Gauntlet tokens.** One token per completed run (two under `bounty`),
  redeemable with any keeper for consumables and, at ten, a piece of
  themed gear. Needs an item id, an icon and a token shop.
- **Boss trophies.** One rare drop per boss that is a wearable or a
  cosmetic rather than an ingredient: the Boar King's tusk (a dagger), the
  Matriarch's pelt (a cloak), the Sovereign's crest, the Reeve's chain, the
  Warden's bell-clapper (a mace), Duskmane's claw, a Songstone shard focus,
  the Bund Tyrant's jaw. Each is an item plus a rig or an icon.
- **Cache upgrades by time.** A run under a par time adds a second rare
  roll. The best time is already recorded per character; par times per
  band are the tuning.

## Mechanics (proposed, not built)

| feature | today | what it would take |
|---|---|---|
| A run HUD (leg, wave remaining, clock) | announcements in the chat channel at every gate | a small `ELORIA_*` packet with a capability gate and a panel, as the other HUD windows are done |
| Gates that visibly open | the gate prop stands; using it steps you through the cut | a map-object state packet so the client hides the bars, or swaps the prop |
| Checkpoints | death puts you outside; the party carries on without you | a `checkpoint` waystone every third leg that re-admits a dead participant while the run lives |
| Leaderboards | best time per character in quest state | a per-route board in the leaderboard stats, and the keeper reading it out |
| Hard mode | superseded: the keeper's five-step challenge sets any road as far as 1.8x the party's level | a clock that shortens with the step |
| Weekly featured road | every road is open every day | the special-days calendar naming one road with double tokens |
| Ranged and magic legs | the ranges and null wells live in the secrets | an `area` on a leg (`no_magic` on the bridge, `cheap_magic` in the court) - the area kinds exist, the leg would declare one |
| Party size scaling | wave size is fixed per roster; the level follows the strongest member | multiply the variant's count by the party size over four |

## Things worth a look in play

- The Whitehorn route's bonus node is declared on a stair leg, which has no
  alcove; only gallery legs place a node. Either move the bonus to a
  gallery or give stairs an alcove.
- The keepers stand on open ground near their landmark and the exit tile is
  two tiles from them; `tools/relocate_map_content.py` moves them if the
  region's walk grid changes under them.
- Three copies per route is a guess at concurrency. The number is one
  constant in `tools/author_gauntlets.py` (COPIES) and the table patches.
- The `hunted` mutator turns every trigger to `at_gate`; on the bridges
  (which advance on a timer) that means running through a full span.
