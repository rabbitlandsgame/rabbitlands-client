# Grey Moors — coverage map

What stands where. Coordinates are Godot metres; server tiles are
`(x + 174, 174 − z)`. Design-space coordinates are the ones in
`source/region.py`, at one third of the world values.

## The shape of it

```
  north (−Z)
        rim scarp — closed, unwalkable
   ┌──────────────────────────────────────────────┐
   │  tower_nw      barrow_north   tower_north_east│
   │        croft_north  ring_north                │
   │   crypt_west   ┌─ THE BARROW RIDGE ─┐         │
   │  barrow_west   │  GREAT BARROW +    │  barrow_far_east
   │                │  stone court       │         │
   │  tower_west    └─ shrine, avenue ───┘  crypt_east
   │        ring_west     hanged_oak     ring_east │
   │  peat_west   moor_gate    barrow_south  croft_mid
   │        ARRIVAL ●        peat_centre   peat_east│
   │  croft_west   ring_centre   crypt_south       │
   │        ring_coast   bog basins   ring_far_east│
   │  croft_coast    croft_south                   │
   │ ~~SEA~~  shrine_coast  ring_south   tower_south
   │ ~~~~~~~~ coast_head                           │
   └──────────────────────────────────────────────┘
  south (+Z)
```

The composition is read off `references/01-concept-aerial-overview.png`. A
design point maps to that 512 px painting as
`px = (x + 58) × 512 / 192`, `py = (z + 134) × 512 / 192`.

## Landmarks — 61 in the manifest

| type | count | what |
| --- | --- | --- |
| monument | 15 | 6 barrows, 8 stone rings, the barrow avenue |
| bridge | 11 | 8 boardwalks, 3 causeway bridges |
| ruin | 12 | 6 broken towers, 6 abandoned crofts |
| landmark-tree | 10 | the Hanged Oak and 9 lesser dead trees |
| shrine | 5 | ritual altar slabs with their candles |
| entrance | 4 | crypt doorways |
| worksite | 4 | peat cuttings |

These are the counts the region's QA brief gives, plus the towers and peat
workings the painting shows and the brief omits.

## The set pieces

**The Great Barrow** — design (38, −91), world (114, −273). The one thing in the
region that stands above the rest. Its mound is terrain, raised 6 m by
`region.build_terrain`; the portal is cut into its downhill face, with a
drystone revetment, kerb stones and votive candles. Its crown carries a levelled
court and a thirteen-stone ring at design (38, −84). The Barrow Avenue runs up
to it from `shrine_great`. Panel 2 is this doorway.

**The bog** — twelve basins, listed in `region.BOG_BASINS`, each hollowed below
the moor and holding a water skin. The margins are walkable; the deep middles
are blocked. Eight boardwalks cross the ones on a route. Panel 4 is
`boardwalk_gate`.

**The coast** — the south-west corner only, 5.8% of the playable area. The
headland at design (−34, 34) carries `shrine_coast`, the lit beacon on the
aerial's coastal spur. Panel 9 looks out over it.

**The peat workings** — four, at design (−26, −6), (48, −8), (6, −70) and
(86, −14). Each is a terrain terrace cut 1.1 m down, floored with bare peat, with
a stepped bank, stacked drying turves and a timber winch standing over it.
Panel 8.

**The towers** — six broken drystone stumps on rises at the map's edges. They
are what gives a flat middle distance a horizon, and they are the small dark
verticals all round the edge of the painting.

## Ground cover

| surface class | share of terrain | material |
| --- | --- | --- |
| `HEATHER_MOOR` | the default | `grey_heather_moor` |
| `PEAT_BOG` | hollows, drains, flat low ground | `grey_peat_bog` |
| `ROCK` | rim scarp, coastal cliffs, steep ground | `cliff_rock` |
| `SHORE` | the bay margin and shallows | `shore_shingle` |
| `CAUSEWAY` | 4 laid routes, barrow court, shrines, arrival | `grey_causeway` |
| `MOOR_TRACK` | 8 worn routes, croft yards | `grey_moor_track` |
| `BARROW_TURF` | the eight mounds | `grey_barrow_turf` |

Scatter: 6,048 scrub clumps (heather, sedge, bog cotton, bracken), 360 scattered
standing stones, 778 erratics.

## Routes

Twelve, in `region.ROUTES`. Four are laid causeway — `arrival_causeway`,
`barrow_causeway`, `coast_road`, `east_road` — and eight are worn moor track.
They meet at the moor gate, at the central ring and below the barrow ridge, which
is the web the aerial shows rather than a road tree. Waymarkers and cairns are
placed along them at 46 m intervals, alternating, offset to the shoulder; those
are the small bright points scattered across the painting.

## Spawns and portals

7 spawn points: `default` (the arrival apron), `barrow-court`, `coast-landing`,
and one return point for each of the four interior doors.

2 map transitions, both from `config/eloria/maps.txt`:
`west-waygate` at server (18, 174) → `sunmane_steppe`, and `east-waygate` at
server (330, 174) → `westhaven`.

4 interior entrances, all to `maps/nymara/grey_moor_barrows.elm`: the Great
Barrow's mouth and the west, east and fen crypt stairs. That interior map is
**not built by this package**.

## Population markers

15 markers, all `"authority": "server"` — the server owns actual spawning and
nothing dynamic is baked into the static mesh. 10 NPC sites and 5 creature
zones (barrow wight, bog lurker, marsh wisp, moor hound, cairn shade). 64
harvestable peat banks, sited on `PEAT_BOG` cells inside the playable footprint.

Every name is a placeholder — see `modeling-assumptions.md`.

## What has no coverage

- No interiors. Four doors lead to a map this package does not build.
- No settlement of any kind. The crofts are ruins; nobody lives on this moor.
  That is what the concept shows, but it means the region has no shop, no
  crafting station and no safe indoor space.
- Nothing in the north-west quarter between `tower_west` and `barrow_north` but
  moor, bog and scattered stones — it is the emptiest part of the map, and the
  painting is emptier there too.


## September 2026 circulation overlay

The west arrival now connects to the Haven departure through the peat road.
The refuge at world (-16,-11) groups information, storage, crafting and training,
with the dry pony pen to its west. Peat workings occupy the first gathering
loop; lower-risk wildlife stays around the southern and western worked moor.
Hounds occupy the middle bogs and barrow approaches, while spectral knights,
constructs and other high-risk species occupy the northern burial grounds.

The eight boardwalks and three stone crossings follow surveyed shore stations;
a twelfth span carries the Crownwater ferry into the south-west cove. The
original eleven exterior/inside departures remain, and the ferry retains the
stable east-waygate id. The coast shrine is now at (-93,60), the headland at
(-105,60), the dry landing at (-60,72) and the jetty runs to (-60,89).

The Great Barrow's crown is at (114,-273), with a south-facing door near
(114,-241) and a side ascent around the east shoulder. Source/layout.py holds
the settlement, crossing surveys and named NPC posts; source/region.py holds
the path polylines. The older tables above describe the previous composition.
