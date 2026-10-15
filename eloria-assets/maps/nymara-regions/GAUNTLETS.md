# The gauntlets

Eight instanced routes, one per region theme, run by a party from a keeper
NPC standing in that region. Each is a linear road under the region: a
staging hall, seven legs each behind a barred way, a fork where the party
picks one of two ways, a boss court, and a vault with the reward cache and
the waystone home. The maps come from `_toolkit/gauntlets/` (designs, rooms,
composer); the server side is written from the same designs by the server's
`tools/author_gauntlets.py`.

| route | region | keeper | rosters (authored a/d) | boss |
|---|---|---|---|---|
| The Resin Road | Amberwood | Old Pyke, at the charcoal camp | 8-30, 24-55 | the Boar King |
| The Ice Stair | Whitehorn Range | Hesk Varne, at the mine | 10-35, 28-65 | the Rime Matriarch |
| The Coil Causeway | Ssarathi Ruins | Ssethis the Doorkeeper, at the south water gate | 20-50, 40-80 | the Sunscale Sovereign |
| The Barrow Run | Grey Moors | Widow Carrow, at the breached barrows | 8-30, 25-60 | the Barrow Reeve |
| The Drowned Arcades | Crownwater | Tollmaster Quent, at the customs hall | 5-30, 24-55 | the Bell Warden |
| The Red Canyon | Sunmane Steppe | Rider Anse, at the east gate | 1-25, 20-50 | Duskmane |
| The Resonant Cut | Amethyst Barrens | Grinder Vell, at the geode cave | 5-30, 25-65 | the Songstone Tyrant |
| The Bund Run | Manymouth Delta | Bund Warden Ilse, at the paddy watchtower | 8-30, 30-70 | the Bund Tyrant |

The lower roster of each road ends on a bigger, named one of an ordinary
species (an inline boss); the upper roster ends on a boss that is its own
creature (`boss: 1` in `creatures.txt`, a fight in `bosses.def`: it heals on
the blow and calls its region up out of the ground in three stages).

## How a run works

- **Starting.** The party leader talks to the keeper (NPC role `instance`).
  The keeper asks how hard a road they want - five answers, from an easy
  ride to an impossible challenge, each shown with the level it would set
  the road to - and everyone in the leader's party standing within eight
  tiles goes in together, onto the first copy of the map that no party
  holds (three copies per route, so three parties can run the same road at
  once). There is no level bracket: any party may start, off cooldown
  (`cooldown_hours`, per route). Solo is allowed.
- **The challenge.** The road is set from the strongest member's combat
  level, the average of attack and defense. A fair fight is that level
  exactly; an easy ride is three quarters of it, a hard road a fifth more,
  a brutal road nearly half again, an impossible challenge four fifths
  more, and the steps are held at least three levels apart so a low party
  still has five real choices. Every creature the road lands is its species
  scaled to that level - health, both combat levels and damage together,
  bounded between a third and three times its own - and the experience it
  gives follows. The route's two authored bands are rosters: the band whose
  bracket holds the level is the one whose creatures and boss appear, so
  the road changes flavour as a party grows.
- **What it pays.** The harder the road, the more it drops. Creatures on a
  hard or brutal road roll their tables twice when they fall, on an
  impossible one three times; the cache at the end rolls once, once, twice,
  twice and three times by step, with its rare lines half as likely on an
  easy ride and up to three times as likely on an impossible challenge.
- **Gates.** Every leg starts behind a barred way: a cut in the floor wider
  than two tiles with a gate prop across it. Using the gate (a `gate`
  interactive bound to a same-map portal) steps you through when the leg
  behind it is quiet; before that it tells you so. The first gate opens as
  the run begins.
- **Waves.** A leg's wave lands when the first participant steps into its
  room (`trigger: enter`), or the moment its gate opens (`at_gate`). Every
  wave is one kind of creature, in a shape the room calls for: a *pack* (so
  many of one kind), a *swarm* (half as many again of a smaller kind, each
  at four fifths of the road's level), *heavies* (a few of a bigger kind,
  each a quarter over it), an *escort* (a pack with one of the next kind up
  at its head, a quarter over the road's level) or, on the bridges, a
  *pair* (two kinds in equal number). Each leg has one wave per shape its
  kind takes, each of a different kind, generated from the band's roster
  round the slice the leg's `late` names; the run picks one per leg, never
  one whose kind the last room had, so the road changes creature and
  number at every gate. `advance: cleared` opens the next gate when
  everything is dead; `time:N` opens it N seconds after the wave lands
  whether or not it is dead, which is what the bridges do - you can run
  them.
- **The fork.** Both branch gates open when the hub is quiet. The first
  branch gate a participant uses is the party's choice; the other seals.
  The gate after the fork opens when the chosen branch is quiet.
- **The court.** The adds land first and the boss is on the floor at once.
  When it falls its horde disperses, the run is recorded (the `instances_done`
  counter, and a best time per route in the character's quest state), and
  the cache in the vault opens once for each participant.
- **Leaving.** The waystones in the staging hall and the vault take you
  home to the keeper's side. Dying on the road wakes you there too. Time
  running out, or ninety seconds with nobody on the map, ends the run and
  frees the copy.
- **Mutators.** Rolled per run and announced at the first gate: `frenzy`
  (creatures at 125% health), `hunted` (every room is full when you reach
  it), `bounty` (the cache rolls twice), `swift` (a quarter less time),
  or none.

## Files

Client: `interiors/<route>/` packages (`world.glb`, `world.json` with a
`gauntlet` block, `collision.bin`), `server-collision/<route>.bin`, and
registry entries for each route and its copies (`_2`, `_3` alias the
route). Server: `config/eloria/instances/<route>_<band>.def` (the
`[instance]` header carries `keeper`, `copies`, `exit_map`, the cache and
waystone objects and the mutator table; each `[leg]` carries its gate,
trigger, advance, bounds and `[variant]` groups; a fork's `[branch]` blocks
are legs of their own), `spawn_groups/invasion/gauntlets_nymara.def` (the
waves and courts), and marked blocks in `maps.txt` (map lines, gate and exit
portals), `interactives.txt`, `harvesting.txt` (the bonus nodes),
`drops.txt` (cache tables, boss drops), `npcs.txt` and `npc_dialogue.txt`
(the keepers). The runtime is `eloria/gauntlets.py`.

## Rebuilding

```sh
cd eloria-assets/maps/nymara-regions && python _toolkit/gauntlets/build.py <region>
# server side
python tools/author_gauntlets.py --client <client repo> --apply
python tools/sync_authored_collision.py --client <eloria-assets/maps>
python tools/generate_nymara_maps.py <maps dir>
```

Use the full authoring tool when intentionally changing rosters or rules; it
regenerates waves for every route. For a layout change to an existing route,
preserve its published encounters and exterior return berth with the narrower
refresh instead:

```sh
# after building the one client package, run in the server worktree
python tools/sync_gauntlet_layout.py --client <client repo> --route <route> --apply
python tools/sync_authored_collision.py --client <eloria-assets/maps> --region <route>
python tools/sync_authored_collision.py --client <eloria-assets/maps> --region <route>_2
python tools/sync_authored_collision.py --client <eloria-assets/maps> --region <route>_3
python tools/generate_nymara_maps.py <maps dir>
```

Omit --apply to review the files that would change. The refresh updates existing
instance bounds, gates, waves, interactives and bonus-node coordinates, plus the
client coordinate transform and server arrival constants. It preserves creature
types, counts, variants, rules, rewards, keeper locations and exterior returns.
Each wave moves to distinct authored spawn candidates. Unknown room or object
identities fail before writing. A second run makes no further changes.

Do not run the exterior height-field correction passes on a gauntlet: its
geometry-derived grid deliberately seals the gates until the server opens them.

The package build writes the grid the server walks on
(`server-collision/<route>.bin`) itself, and three things about it were
learned the hard way. Its heights are in the server's 0.2 m step (a grid
fitted to its own relief at 0.1 m read as twice as steep on the server, and
every stair was a step it refused). Each tile is the block of half-metre
cells *round* its centre, blocked if any of them is - the client draws a
tile centred on an integer metre - so a creature's tile stops short of a
wall instead of reaching half a metre into it. And what stands on a floor
blocks it: pillars, boulders, crates and the walls' own faces, through the
band a body occupies, with the tiles under waystones, the cache, nodes and
plaques kept walkable because the server's content contract holds them so.
Spawn tiles the grid does not carry are dropped from the manifest, so no
wave lands in a boulder. `tests/test_gauntlet_packages.py` walks every
route on that grid, gate to gate, and the server's `tests/test_gauntlets.py`
walks the vendored copy.

## Barrow Run layout pass

The Barrow Run now follows a candlelit family visitation road: cists and
offering shelves, a piled timber crossing over flooded peat, an intact carved
branch and a breached rooted branch, then the Reeve's stone-crowned hall.
Shorter connecting passages remove thirty-six metres of empty travel.
Published bands, roster, rules, rewards and keeper returns are preserved.
The package's README, assumptions, coverage, comparison and validation live
under interiors/grey_moors_gauntlet.


## Drowned Arcades layout pass

The Drowned Arcades now follows Crownwater's flooded customs road: raised
bonded stores, marble arcades, a supported stone crossing, cistern screw
lifts and outfalls, an intact valve aisle and a silted branch, then the
great bell above the reward doorway. Shorter connecting passages remove
thirty-six metres of empty travel. Shallow water sits above actual floors
and behind climbable stone thresholds. Published bands, roster, rules,
rewards and keeper returns are preserved. The package's README,
assumptions, coverage, comparison and validation live under
interiors/crownwater_gauntlet.


## Red Canyon layout pass

The Red Canyon now follows an open sandstone herd wash. Undercut ledges
shelter the Horse Cave and Shade Fork; a surviving rock rib crosses the
dry ravine; the Sun Fork stays exposed; and the split rock crown marks
the final court beyond the Long Wash. The three-metre climb uses short
surveyed ramp strips so the geometry-derived grid remains gradual.
Shorter links remove thirty-six metres of travel. Published rosters,
rules, rewards and keeper returns are preserved. The package's README,
assumptions, coverage, comparison and validation live under
interiors/sunmane_gauntlet.
