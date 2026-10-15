# Whitehorn Range comparison report

Concept sources against the build. Sheets are in `references/comparisons/`.

**Every capture except `90-godot-client-spawn.png` is from the toolkit's offline
C rasteriser, not from Godot.** They are an art-direction tool. The one real
client frame is labelled below and is lit by the check harness, not the game.

## Aerial — `comparisons/aerial-comparison.webp`

Source: `eloria-assets/concepts/nymara-regions/whitehorn_range_region_concept.png`
(intact, 622 KB). This is the composition authority and it was matched
structurally rather than pixel for pixel.

| Concept element | In the build | Notes |
| --- | --- | --- |
| Bowl opening south, rising north | yes | `add_slope` + boundary ridges; 6 m to 180 m |
| Glacier temple high at the north end | yes | on a cut shelf at z = -309 |
| Central glacier tongue running south | yes | authored ICE route, 45 m wide, with 77 seracs |
| Gorge crossed by rope bridges | yes | one cut across the map, two spans |
| Cairn-lined approach from the south | yes | 177 cairns |
| Ice cave, west | yes | teal-lit mouth |
| Mine, east | yes | timbered portal with rails |
| Frozen cascades off the shoulders | yes | two |
| Conifers on the lower slopes only | yes | 870, gated below the snow line |
| Peaks ringing the region | **partially** | see gaps below |

### Where the aerial does not match

Honest list, in order of how much it matters.

1. **The boundary reads as a rectangular lip with square corners.** This is
   the largest visual departure, and the aerial shows it plainly: the
   south-west and south-east corners are visibly right-angled. `clamp_edges`
   raises a continuous rim on a rectangular foot, so on a region walled on all
   four sides — which Whitehorn is, having no coast — the world boundary reads
   as the edge of a table rather than as mountains. The concept has individual
   summits with sky between them.

   It is not inherent to a heightfield. The fix is a ridged wall on an
   irregular foot rather than an axis-aligned ramp: `add_ridge` along a wandering
   boundary polyline, with summit domes at intervals, so the silhouette breaks
   up and the corners round off. The Mirrorhold build has since written exactly
   this as `region._close_world`, and adopting it is the single highest-value
   change available to this region's terrain. It is deliberately **not** done
   here, because it would mean rewriting the world boundary after the package
   was verified and pushed; it should be the first thing done next.
2. **Relief is gentler than the painting.** The concept implies near-vertical
   faces; the build tops out around a 1.2 gradient because anything steeper
   stops being walkable and starts breaking the grounding contract.
3. **Surface boundaries stair-step.** The terrain cell is 2 m and material is
   assigned per cell, so class edges are visible as small rectangles from the
   air. `dither_boundaries` is turned down to 0.18 because a heavier dither made
   it worse, not better.
4. **The concept's structures are more numerous.** It suggests small buildings
   scattered on several ledges; the build has the temple, gate, three shrines,
   three watch posts and three camps.

## Detail board — `comparisons/panel-comparison.webp`

The board supplied in the package was truncated to 786,445 bytes and would not
decode. An intact 3,371,891-byte copy decoding all 793 rows was found in the
main working tree and is now committed here, so **this sheet compares against
real concept art**, panel for panel.

Having actually seen them side by side, the honest grading is below. It is
harsher than the "nine of ten built" I claimed before the sheet existed, which
was an inventory check — the pieces are present — rather than a comparison.

| # | Panel | Match | What is actually there |
| --- | --- | --- | --- |
| 1 | Cairn-lined approach | **weak** | Road, cairns and conifers are present, but the concept's enclosing gorge walls are not: the build's approach is open snowfield, so the composition reads flat and the temple is not framed by anything. |
| 2 | Temple facade | **good** | Marble facade, arch ring, glowing blue portal, flanking columns, snow cap and icicle fringe, set into rock. Statues, braziers and the inlaid plaza exist but sit below the camera's rise and are not in frame. |
| 3 | Rope bridge | **good** | Full span in profile over the gorge: timber anchor posts both ends, sagging deck and handrail cables, plank deck, ice walls either side. |
| 4 | Shrine alcove | moderate | Recessed marble alcove, arch ring, statue on a plinth, steps. Smaller and plainer than the concept's carved surround. |
| 5 | Cairn field | moderate | A 44-cairn cluster with waystones on a ridge. The cairns are cruder than the concept's stacked slate. |
| 6 | Ice cave | moderate | Now a legible mouth — flanking ice shoulders, a brow, a dark void, icicle fringe, lanterns. Rounder and softer than the concept's fractured ice. |
| 7 | Mine portal | **good** | Stone surround, timber frame and lintel, dark adit, rails and sleepers running out, spoil heaps. No hanging lanterns. |
| 8 | Frozen cascade | moderate | Ice columns with icicles on a rock backing, frozen pool and ice rubble at the foot, waystones beside. Reads as an icefall, but far coarser than the concept's fine curtain. |
| 9 | High overlook | moderate | The panorama is there; the peaks behind it are a boundary rim rather than summits. |
| 10 | Material study | **weak** | Answered with a bridge-anchor study of rope, iron, timber, ice and dressed stone. The concept's hero props — a gem-set clasp and a chalice — are not modelled at all. They are inventory-scale objects and no prop kit entry exists for them. |

Two systemic causes account for most of the gap, and both are recorded rather
than fixed:

1. **The terrain is more open than the concept.** Panels 1, 5 and 9 all want
   enclosing walls and vertical drama; the build gives rolling snowfield
   between a rectangular boundary rim. This is the same root cause as the
   aerial's square-cornered lip, above.
2. **Kit pieces are simpler than the paintings.** Every landmark is built from
   boxes, cylinders, lathes and icospheres. That is enough for silhouette and
   material, not for the carved relief the board shows.

Panels 2, 3 and 7 are the ones that hold up.

## Other views — `comparisons/landmark-contact-sheet.webp`

Thirteen views that answer no panel: spawn grounding, gorge edge, upper bridge,
temple forecourt, glacier snout and head, mine yard, south gate, pine shelf,
north shrine, west watch, east camp, snow line, plus two golden-hour passes.

## Real client frame

`references/captures/90-godot-client-spawn.png` — Godot 4.7.2, through
`WorldLoader.load_world()`, OpenGL compatibility renderer, RTX 5080. It shows
the geometry loading and rendering in-engine. Its lighting is a bare
directional light and procedural sky created by `tools/region_client_check.gd`,
**not** the game's environment, so it is evidence of load correctness and not of
final appearance.
