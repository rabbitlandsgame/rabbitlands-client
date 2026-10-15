# Sunmane Steppe - server integration

Everything in this document is server-side work that this client change
does **not** perform. The client change is self-contained and does not
alter the network protocol or any gameplay behaviour; the region loads
and is traversable with the server exactly as it is today.

`eloria-server` was not reachable from the workspace this package was
built in, so none of the records below could be committed there. They are
generated from the committed manifests by
`maps/nymara-regions/sunmane_steppe/source/server_integration.py`, so the matching server pull
request is transcription rather than redesign.

## Hooks

The region's hook names come from
`maps/nymara-regions/region-connections.json` and are
unchanged:

| Hook | Name |
|---|---|
| npc | `npcs.nymara.sunmane_steppe` |
| spawn | `spawns.nymara.sunmane_steppe` |
| hazard | `hazards.nymara.sunmane_steppe` |
| harvest | `harvest.nymara.sunmane_steppe` |

## Map registration

| Property | Value |
|---|---|
| Server map id | `maps/nymara/sunmane_steppe.elm` |
| Metres per server tile | 1.0 |
| Arrival datum | `(58, 58)` |
| Addressable tiles | 0..191 on both axes |
| Addressable world band | X -58..133, Z -133..58 |
| Crossing west | `(6, 58)` to Mirrorhold (the west road); the gate is a pair of menhirs astride the road |
| Crossing north | `(66, 184)` to the Amethyst Barrens (the desert track) |
| Crossing south | `(62, 18)` to the Verdant Stair (the shore road) |
| North barrow | `(58, 100)`, a sealed passage; the Ssarathi Royal Archive is entered from the Ssarathi Ruins |

Three things in the walk grid used to seal the camp: gate lintels stamped onto
the ground plane (`collision.py` now ignores geometry more than 2.1 m above a
node's seat), the great hall's plinth running through the palisade so the
north gate opened into its back wall (the hall is 13 m across now, at
`(0, -12)`), and a cart parked in the south gate with the crossroads well on
the road behind it (both moved). All four gates and all three crossings are
reachable from the plaza on the server's folded grid.

The region is wider than the addressable band on purpose. Everything
outside it - the far spires, the summits, the open sea - is scenery a
player can see but never stand on, and it is marked
`"reachable": false` in the manifest. The server needs no record of it.

## The interior map

Sunmane's two cave systems share **one** interior map, the way
Crownwater's and Ssarathi's insides do: one package, one server map id,
one collision grid, and unwalkable blackspace between the systems. Which
system a player gets is decided by the mouth they entered, so there is
one portal pair per door rather than one per system:

| Section | Mouth on the steppe | Arrival inside | Exit back to |
|---|---|---|---|
| Sunmane Wind Caves | `(128, 175)` | `(43, 27)` | `(128, 175)` |
| Amethyst Crystal Hollow | `(182, 154)` | `(169, 28)` | `(182, 154)` |

Both doors go to `maps/nymara/sunmane_wind_caves.elm`, which is one metre
per tile like the surface map, uses `invertServerY`, and puts its datum
at the map corner rather than the centre of a square, so a section's
tiles are simply its metres. The package is 192 m across, so the map needs
32 server tiles where the wind caves alone needed 10.

`maps/nymara/sunmane_crystal_hollow.elm` is **retired** as a served map.
The other two cave mouths on the surface - the drovers' shelter and the
eastern adit - are modelled shelters with no interior and need no
registration.

## Safe spawn surfaces

The client grounds actors by raycasting the navigation surface, and every
sampled column in the region grounds successfully, so any walkable tile is
a safe spawn. The positions the manifests name explicitly:

| Spawn id | Server tile | Map | Note |
|---|---|---|---|
| arrival-datum | `(58, 58)` | sunmane_steppe | ceremonial crossroads at the shared market |
| west-caravanserai | `(6, 58)` | sunmane_steppe | arrival from Mirrorhold along the west road |
| east-caravanserai | `(110, 58)` | sunmane_steppe | the east caravanserai; the east gate is the frontier and leads nowhere |
| north-barrowfield | `(58, 100)` | sunmane_steppe | the barrow field; the passage barrow is sealed |
| default | `(43, 27)` | sunmane_wind_caves | Arrival for the wind caves mouth, and the map default. |
| wind-caves-mouth | `(43, 27)` | sunmane_wind_caves | Arrival for Sunmane Wind Caves. |
| crystal-hollow-adit | `(169, 28)` | sunmane_wind_caves | Arrival for Amethyst Crystal Hollow. |

## NPC posts (15)

| Id | Label | Role | Server tile |
|---|---|---|---|
| `khan-of-the-sunmane` | Orun khan | quest | `(58, 60)` |
| `market-broker` | Seasonal market broker | trade | `(50, 48)` |
| `horse-master` | Camp horse master | trade | `(28, 92)` |
| `caravan-master-west` | West caravan master | travel | `(16, 54)` |
| `caravan-master-east` | East caravan master | travel | `(100, 54)` |
| `shrine-keeper` | Banner shrine keeper | quest | `(33, 92)` |
| `miller` | Steppe miller | trade | `(102, 25)` |
| `well-keeper` | Crossroads well keeper | service | `(58, 37)` |
| `barrow-warden` | Barrow warden | quest | `(58, 96)` |
| `cove-factor` | Cove landing factor | trade | `(5, 14)` |
| `dune-well-keeper` | Dune well keeper | service | `(62, 148)` |
| `salt-factor` | Salt-pan factor | trade | `(122, 156)` |
| `wind-cave-watch` | Wind caves watch | quest | `(128, 170)` |
| `amethyst-prospector` | Amethyst prospector | trade | `(180, 150)` |
| `range-warden` | Whitehorn range warden | quest | `(156, 146)` |

## Harvestable resources (20)

| Id | Label | Kind | Server tile |
|---|---|---|---|
| `sunmane-wheat-00` | Sunmane wheat | crop | `(92, 28)` |
| `sunmane-wheat-01` | Sunmane wheat | crop | `(24, 104)` |
| `sunmane-wheat-02` | Sunmane wheat | crop | `(110, 14)` |
| `sunmane-wheat-03` | Sunmane wheat | crop | `(6, 36)` |
| `sunmane-wheat-04` | Sunmane wheat | crop | `(80, 116)` |
| `steppe-herbs-00` | Steppe herbs | herb | `(8, 78)` |
| `steppe-herbs-01` | Steppe herbs | herb | `(120, 98)` |
| `steppe-herbs-02` | Steppe herbs | herb | `(34, 0)` |
| `shore-clay-00` | Shore clay | mineral | `(4, 10)` |
| `shore-clay-01` | Shore clay | mineral | `(6, 104)` |
| `mesa-flint-00` | Mesa flint | mineral | `(38, 132)` |
| `mesa-flint-01` | Mesa flint | mineral | `(118, 120)` |
| `amethyst-shard-00` | Amethyst shard | mineral | `(168, 154)` |
| `amethyst-shard-01` | Amethyst shard | mineral | `(184, 128)` |
| `pan-salt-00` | Pan salt | mineral | `(64, 182)` |
| `pan-salt-01` | Pan salt | mineral | `(120, 168)` |
| `dune-sage-00` | Dune sage | herb | `(38, 166)` |
| `dune-sage-01` | Dune sage | herb | `(98, 154)` |
| `scree-ore-00` | Scree iron ore | mineral | `(182, 98)` |
| `scree-ore-01` | Scree iron ore | mineral | `(12, 184)` |

## Hostile creature spawns (10)

All models below already exist in the client's creature catalogue.

| Model | Area | Count | Radius | Server tile |
|---|---|---|---|---|
| `dire_wolf` | north mesa breaks | 3 | 10.0 m | `(28, 126)` |
| `dire_wolf` | eastern breaks | 3 | 10.0 m | `(132, 92)` |
| `wild_boar` | south-west scrub | 4 | 11.0 m | `(10, 8)` |
| `red_fox` | open steppe | 4 | 14.0 m | `(88, 108)` |
| `elk` | northern pasture | 4 | 12.0 m | `(6, 108)` |
| `mountain_goat` | coastal cliffs | 3 | 9.0 m | `(6, 46)` |
| `mountain_goat` | Whitehorn foothills | 3 | 12.0 m | `(150, 178)` |
| `dire_wolf` | wind cave approach | 3 | 11.0 m | `(114, 166)` |
| `red_fox` | amethyst badland | 3 | 12.0 m | `(172, 136)` |
| `wild_boar` | dune margin scrub | 4 | 12.0 m | `(34, 150)` |

## Interaction points needing server behaviour

The manifest declares 70 interaction points. The ones that need a server
decision rather than a client-side prompt are the map transitions:

| Id | Label | Server tile | Destination map | Arrival tile |
|---|---|---|---|---|
| `cave-wind_caves` | Sunmane Wind Caves | `(128, 175)` | `maps/nymara/sunmane_wind_caves.elm` | `(30, 12)` |
| `cave-crystal_hollow` | Amethyst Crystal Hollow | `(182, 154)` | `maps/nymara/sunmane_crystal_hollow.elm` | `(30, 13)` |

The remainder - wells, water stations, shrines, markets, shelters,
hitching rails - are ordinary interaction points and behave like the
equivalents in other regions.

## Livestock actor types

Three creature assets ship with this change: `sunmane_steppe_horse`,
`sunmane_dun_mare` and `sunmane_grey_pony`. They are registered in
`godot-client/data/actors/models.json` by model id and are instanced as
**scenery** by the client's ambient population system, so they need
nothing from the server to appear.

They are deliberately registered with `serverActorType: null`. Actor-type
numbers are the server's to allocate, and the creature block in
`models.json` currently runs 204-235. If the server wants these as
networked, attackable or rideable actors it should allocate the next free
numbers and add the matching `actorTypes` entries; until then the client
will simply never receive one over the wire, which is harmless.

## What must not change

The map deliberately requires no protocol change:

- One metre per server tile, and the arrival datum at `(58, 58)`, both
  matching the entry already committed in
  `godot-client/data/maps/registry.json`.
- Server tile to world position uses the existing `CoordinateAdapter`
  unchanged; the region moved its world centre, not its datum.
- Walkability remains server-authoritative. The client's navigation
  surface covers the whole landform on purpose, so a grounding raycast
  can never miss; it does not decide where a player may go.
