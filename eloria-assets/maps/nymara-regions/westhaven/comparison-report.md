> Historical record of the previous 576m package. The current 396m coordinate contract and layout are documented in [README.md](README.md) and [layout-review.md](layout-review.md); current metrics are generated in `performance.json` and `verification-report.json`.

Current checkpoint: [2026-09-07 layout review](layout-review.md). The earlier
counts and camera comments below describe the previous build.

# Westhaven: comparison report

The build against the concept art, panel by panel. An honest reading, not a
score sheet.

The sheets are in `references/comparisons/`:

- `aerial-comparison.webp` — the concept aerial above the build's aerial
- `panel-comparison.webp` — all ten detail-board panels against their captures
- `landmark-contact-sheet.webp` — every capture in the set

**The build frames in these sheets are real Godot 4.7.2 client frames**, drawn
through the project's own `WorldLoader` with the Vulkan driver on Forward+.
They are not offline previews. The sheet says so on its own caption line, and
the provenance is recorded per frame in `references/godot-captures/index.json`.

The offline previews from the toolkit's C rasteriser are also shipped, in
`references/captures/`, using the same camera table. They are an authoring aid.
Where the two differ — the offline set is warmer and lower-contrast — that is a
difference between two renderers.

## The aerial

**What matches.** The composition transfers. A dense terracotta-roofed city on
a south-facing headland; a continuous quay across its foot; a curved mole
closing a harbour; finger piers and moored ships; two rocky masses out in the
water to the south, each with a light; open green upland with tree belts and
switchbacked roads to the north-east; a sandy bay biting into the east coast.
Everything in the painting is in the map and in the right place, because the
reading grid maps 1:1.

**What does not match.**

1. **Projection.** The concept is a three-quarter oblique from the south-west;
   the build's aerial is near-vertical. They cannot be overlaid. A matching
   oblique would compare better but would hide half the map behind the city,
   and this shot's job is coverage.
2. **Vertical drama.** The painting's skyline is still spikier: its towers are
   proportionally taller and thinner than anything here. Seven lesser towers
   were added on the terrace bands, which closes much of the gap seen from the
   water; from directly above it still reads flatter than the painting.
3. **Density of shipping.** The painting has roughly twenty vessels and a dozen
   small jetties. The build now has sixteen hulls, two working piers and eight
   jetties, where the first pass had nine hulls and two piers.
4. **Colour temperature.** Closer than it was. The `environment` block is now
   art-directed against the painting — warmer and lower sun, saturation 1.34,
   less fog — and the coast carries white water, which is a large part of the
   painting's brightness. The client frame is still cooler than the painting's
   golden afternoon.
5. **Ground texture variety.** The painting's upland is a patchwork of ochre,
   olive and dry gold. The build's salt turf is one recipe with noise, so the
   upland reads more uniform. Unchanged in the second pass.

## The ten panels

| # | subject | verdict |
| --- | --- | --- |
| 1 | arched harbour gate | **Good.** A channel is now cut north from the harbour through the gate line, so there is open water under the arch and a boat can pass beneath it, which was the one thing separating this from the panel. The gate's roadway is a walk surface, so the quay route west crosses on top of it rather than being severed by the cut. |
| 2 | lighthouse on a wave-battered rock | **Good.** Battered tower, string courses, corbelled gallery with an iron rail, glazed lantern, lead dome, keeper's house, and the rock reads as rock. The region now has surf and there is foam at the rock's foot, but three framings were tried and none puts the tower and its breaking water in one frame the way the panel does. The sea is present rather than the subject. |
| 3 | cobbled street climbing through an arch | **Good.** The climb now runs *through* an arch with two jettied storeys carried over it, which was the panel's defining feature and the thing the build had no equivalent of. Granite setts, warehouse frontage, lamps. |
| 4 | ship alongside with a gantry | **Good.** Pier on piles with a planked deck, shear-legs gantry with a crate on the fall, a two-masted hull alongside. Rigging is much simpler than the panel's. |
| 5 | timber cargo crane | **Good.** The treadwheel crane is the closest single object in the region to its panel: A-frames, spoked wheel on its axle, raked jib, laden net. The wheels were below the quay until the transform bug was fixed. |
| 6 | hull under construction on the stocks | **Good.** Keel, raked stem and sternpost, fifteen open frames, three garboard strakes a side, shores and keel blocks. You can see through it, which is the point. |
| 7 | fish stalls under awnings in an arcade | **Good.** Arcade with arches and a tiled roof, nine stalls with striped awnings, catch on the trestles, baskets. |
| 8 | sea wall bastion with a banner | **Good.** The mole now runs out with surf breaking along its whole weather face, which is most of what the panel is, and the bastion stands at the bend with its merlons and banner. Framed along the mole rather than up at it from the water. |
| 9 | rooftop terrace over a brass dome | **Good.** Colonnaded drum, ribbed brass dome, lantern and finial, balustraded terrace, city and sea beyond. |
| 10 | dockside still-life | **Good.** A macro at last. The rope coils, chain runs, crates, barrels and fishing gear fill the foreground at the scale the panel has them, with the crane and the moored ships behind. The framing was authored correctly from the start; what kept it wide was the capture harness, whose camera-placement search demanded 4.8 m of standing room and stepped back up to 57 m to find it. Both are now scaled to the shot. |

**Nine of ten are good, one partial, none weak.** The first pass was four good, five partial and one weak.

The one still partial is panel 2: the lighthouse reads and the rock now has foam at its foot, but four framings have been tried — from the crown, from the shoulder, from 114 m out on the water, and low on the south-west shore — and none holds the tower and its breaking water in one frame the way the panel does. Lamp Rock is 180 m across with the light near its middle, so any camera far enough out to see the surf line is too far out for the tower to be the subject. Moving the lighthouse toward the rock's seaward edge would fix the shot and would move a landmark away from where the aerial puts it, which is the wrong trade.

## What the second pass changed

Everything on the first pass's list was done.

1. **Surf.** 719 alpha-cut foam cards and seven breaker sheets, placed where the
   terrain crosses the water line and weighted by **exposure**: the outward
   direction of a shore cell is downhill, so a cell facing south or west takes
   the weather and gets heavy foam, and one facing into the harbour gets almost
   none. 1,522 triangles, and by a distance the largest improvement in this
   document. Two bugs on the way — a height band caught 797 cells out of 101,761
   on a coast this steep and had to become a blurred ring mask, and the exposure
   term was written with the gradient's own sign and so came out exactly
   negated, putting the heavy foam inside the harbour.
2. **Rope and chain**, and the panel-10 cluster composed around them.
3. **An arch over the quay street**, carrying two jettied storeys.
4. **`environment` art-directed** against the painting: warmer and lower sun,
   saturation 1.22 to 1.34, less fog.
5. **Seven more towers** on the terrace bands — a parish belfry and a merchant's
   lookout, not another cathedral.
6. **Eight jetties and seven more hulls.**

Adding surf also let a texture bug be removed rather than papered over.
`westhaven_sea_rock` baked the three tide zones in as horizontal bands of the V
coordinate, which is right for a vertical sea wall and wrong for the terrain the
same material covers: at terrain UV scale the bands tiled into hard stripes
every three and a half metres, and the lighthouse rocks read as corrugated iron.
The recipe is now isotropic — jointing, fracture, lichen and weed as blotches —
and the tide is told by the surf geometry, which is correct at every
orientation.

## The third pass

The rest of the previous list, and one thing it had not noticed.

- **The harbour gate stands in water.** A channel cut north from the harbour
  through the gate line, with the gate's roadway made a walk surface so the
  quay route crosses on it instead of being severed.
- **Rigging.** Two yards a mast, each with its sail, four shrouds a side, and a
  forestay and backstay. A mast with one sheet on it read as a pole standing
  loose in a deck.
- **The panel-10 macro**, by scaling the capture harness's two camera searches
  to the shot rather than to the region.
- **Upland ground variety.** A second, drier pasture recipe laid against the
  salt turf on a long-wavelength field, so the north-east is a patchwork rather
  than one texture with noise on it.
- **The upland roads were surfaced in ship decking.** Not on any list: the
  terrain class the road operator marks is PATH, and PATH was pointed at
  `westhaven_quay_plank` because the shipyard slipway needed decking. Every cart
  track on the map was planked like a deck. PATH is now a proper cart track —
  packed earth, embedded stones, wheel ruts, a weedy crown — and the slipway,
  the one place decking on the ground was right, is authored as paving.

Two placement bugs surfaced with the inlet, and one of them had been there from
the first build:

- **`west_quay` had been sitting in sixteen metres of water since day one.** The
  coast at that v runs through u = 1.11 and the anchor was at 0.72. Nothing
  caught it, and once the walkable-cell check existed it quietly relocated the
  Crownwater berth 16 m every build rather than reporting the anchor as wrong.
  The anchor is now probed against the built terrain, not guessed.
- **The nudge could relocate a portal under a deck.** An elevated deck makes its
  footprint walkable at deck height, and the harbour gate's piers stand on dry
  ground, so "nearest walkable cell with dry ground" could land under the gate
  roadway and then take its Y from the terrain sixteen metres below.
  `build_collision` now records which cells a deck claims and the nudge excludes
  them.

## What would most improve it next

1. **Panel 2's framing**, which needs the lighthouse nearer the seaward edge of
   Lamp Rock, or a longer lens than the harness's fixed field allows.
2. **The aerial's projection.** The concept is a three-quarter oblique and the
   build's aerial is near-vertical, so the two cannot be overlaid.
3. **Interiors for the rest of the region.** Four are built; the guild hall, the
   cathedral and the arcade are all doors nobody can open.

## What this report does not say

It does not say the map is finished art. It says which subjects are present,
which are recognisable and which are not, judged by looking at the captures
beside the concept. Composition, proportion and colour are reported as I read
them; someone who owns the art direction should disagree with some of it.
