# Traversal modes: shapeshifting into the water and under it

A design note, written because Manymouth Delta is the first Nymara region where
*most of the map is not walkable* and the question stops being hypothetical.
Nothing here is implemented. What **is** done is that this package is authored
so that implementing it needs no rebuild — the numbers a swim or aquatic form
would need are already in `world.json`, and the geometry they would need is
already under the water. The last section says exactly what is and is not there.

---

## 1. Why this region raises the question at all

31.4% of Manymouth's reachable tiles are walkable. The other 68.6% are water
with real bed geometry beneath them, at a mean depth of about 2.6 m and a
maximum of 25.8 m in the whirlpool under the great arch.

That is not a defect, it is the concept: the aerial is a braided distributary
fan and the detail board's ten panels are, without exception, either *on* the
water or *over* it. But it does mean a walking-only player experiences roughly
a third of a 576 m × 576 m region, and the two-thirds they cannot reach is the
part the paintings are actually about. Three panels are unreachable on foot in
principle — the canoe of panel 1, the moored market of panel 6, and the drowned
chamber of panel 8.

The region already answers this partly, through the walkway network: 27 routes
and 101 deck segments that let you walk from the town to the temple without a
boat. But a walkway is a corridor. It gives access, not freedom, and the
delta's whole character is that the water is the commons.

## 2. Three candidate modes, and which one earns its keep

### 2a. Swim — surface only

The cheapest. The player enters water above a depth threshold and switches to a
surface-swim state: movement continues on the 2-D server grid, the client
places the actor at `seaLevel` instead of on the surface the grounding ray
found, and the camera and animation change.

**What it unlocks.** Every channel and the open sea. Panels 1 and 6 become
reachable — you can be *among* the moored boats rather than looking at them
from a deck. It roughly triples the reachable area of this region at a stroke.

**What it costs.** A movement state, a swim animation, and one decision on the
server about whether a water tile is passable. It does not need new geometry,
new collision, or a third dimension in the server grid, because the swimmer is
always at exactly one height: `seaLevel`.

**Verdict: this is the one to build first.** It is a small change with the
largest possible effect on this region, and it needs nothing from the art side
that is not already shipped.

### 2b. Dive — below the surface

The player descends from the swim state and moves in three dimensions between
`seaLevel` and the bed.

**What it unlocks.** The sunken stelae around the arch, the drowned approach
platform, the dredged channels, and the whirlpool throat itself. Structurally
it is the difference between the arch being a monument you row past and the
arch being an entrance.

**What it costs.** Considerably more. The server grid is two-dimensional; a
diver's *depth* has no representation in it. The honest cheap version is that
depth is client-side presentation only — the server still tracks one tile per
player, and diving changes what you see and what you can interact with but not
where you are on the grid. That is enough for exploration and for gated
entrances, and it is not enough for combat or for anything two players must
agree about precisely.

**Verdict: worth it for this region specifically**, because the arch is the
region's centrepiece and it is a hole in the water. But it is the point at
which "add a movement state" becomes "extend the world model", and it should be
costed as the latter.

### 2c. Aquatic form — a shapeshift proper

Not a movement state but a **transformation**: the player becomes a different
creature, with a different silhouette, a different speed, a different set of
affordances, and — the part that makes it a game mechanic rather than a
traversal convenience — a different set of *restrictions*. An otter-form or
naga-form that swims fast and dives deep but cannot climb a ladder, carry cargo,
open a door, or fight with a polearm.

**Why this is the interesting answer.** A swim state is a way of crossing
water. A form is a way of *choosing* what kind of access you want, and it turns
the delta's geography into a real decision: the walkway network is the slow,
capable route and the water is the fast, limited one. In a region built out of
that exact tension — every village is on piles over a channel, every panel is
about the boundary between deck and water — a mechanic that makes the player
pick a side each time they set off is doing thematic work, not just locomotion
work.

It also gives the region its own answer to a problem every one of these maps
has: what stops the player just walking everywhere. Here, nothing has to stop
them. The water is open in one form and the decks are open in the other.

**Where it should be earned.** Not a starting ability. The obvious place is the
Flooded Labyrinth: you enter the drowned ruin under the headland by boat, and
what you bring out is the form that lets you go back in properly. That makes
the region's one interior the region's one unlock, and it is why the cave mouth
in this package is a real portal with a real threshold rather than set dressing.

## 3. Underground: what "the ruins under the delta" actually needs

The board's panel 8 is a flooded cavern with a glowing ring-portal in it. It is
not in this package, and that is deliberate: it is the
`manymouth_flooded_labyrinth` map, which already exists server-side as a 32×32
interior. This package ships its **threshold** — the cut arch in the rock
headland at server tile (390, 198), a real `map-transition` portal, with the
glyph-inlaid stone and the cut face around it.

For the underground to work with the modes above, three things are needed and
only the first is done:

1. **A way in that reads as a way in.** Done. The mouth is modelled, lit by the
   emissive glyph band, walkable up to the threshold, and portalled.
2. **An interior authored as flooded**, i.e. with a water plane, a bed below it,
   and headroom above it — so that a diver and a walker experience the same
   room differently. The current interior is a flat 32×32 placeholder.
3. **A gate.** If the aquatic form is the reward for the labyrinth, something in
   the labyrinth has to be reachable only by the form, or the reward is
   cosmetic. The natural shape is a two-visit structure: swim in, find the
   thing, come back able to dive, and the second visit opens the parts of the
   *exterior* — the whirlpool throat, the sunken court — that were visible from
   the start and unreachable.

That last point is the one worth designing around, because it is what makes the
exterior map pay the mechanic back. Every one of those places is already built
and already under the water in this package.

## 4. What this package has already done for it

None of this is speculative work in the geometry. Concretely:

| Need | State in this package |
| --- | --- |
| A real surface under every water tile | **Done.** The bed is terrain everywhere, at a real depth. `verify_runtime` grounds all 331,776 reachable tiles with zero misses, water included — a swimmer stepping out onto the bed always lands on something. |
| Water cells distinguishable from walls | **Done.** `collision.swimmable` in `world.json` records the rule (grid value 0 **and** terrain below `seaLevel`), the cell count, the fraction and the mean and maximum depths. `collision.bin` is unchanged — EWCG v1 has no spare bit, and inventing v2 for a flag no client reads would be worse. |
| A declared water surface height | **Done.** `asset.seaLevel` and `water.seaLevel`, both 0.0. Every swimmable cell's depth is `seaLevel` minus the bed. |
| Depth bands a designer can tune against | **Done.** `water.depths` gives the four authored levels: bar flat −2.6, navigable channel −7.2, open sea −17.0, whirlpool −13.5. |
| Navigable routes for a boat or a fast swim | **Done.** `water.channels` carries all seven distributaries as waypoint polylines, each tagged `navigable` or `shallow-braid`. |
| Submerged geometry worth diving to | **Done.** The arch's approach platform sits at −0.55, fourteen stelae stand in the shallows around the whirlpool, and the whirlpool throat is a modelled funnel. |
| A declaration of intent the client can read | **Done.** `environment.traversal` declares `walk` available and `swim` and `dive` unavailable-but-authored-for, with the reasons and the limits. |
| An interior to unlock it in | **Not done, and out of scope.** `manymouth_flooded_labyrinth` is still a flat placeholder. It is a separate map and a separate piece of work. |
| Any client or server implementation | **Not done.** There is no swim state in `main.gd`, and the server has no notion of a passable water tile. Nothing here changes that. |

## 5. The one thing I would not do

Do not encode swimmability by making water tiles *walkable* in `collision.bin`
as an interim step. It costs nothing today and it is very expensive later: the
grid is the server's authority on where a player may be, a walkable water tile
is a player standing on the bottom of a channel, and every pathfinder, spawn
placement and creature leash in the region would immediately start using it.
Water is correctly blocked today. The classification above is additive and
throws nothing away.
