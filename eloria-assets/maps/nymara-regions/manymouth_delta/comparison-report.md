# Manymouth Delta comparison report

What the build actually matches in the concept art, and what it does not.

The sheets in `references/comparisons/` are built from **real Godot 4.7.2 client
frames**, not from the offline preview renderer, and each row is labelled as
such. Judge water, transparency and lighting from those; the offline set in
`references/captures/` cannot draw blended materials at all (see
`validation-report.md`).

| Sheet | What it holds |
| --- | --- |
| `aerial-comparison.webp` | The aerial concept beside the build's aerial |
| `panel-comparison.webp` | All ten detail-board panels beside their framings |
| `landmark-contact-sheet.webp` | The full 27-view capture set |

## Against the aerial

The structural reading — a braided distributary fan, not an island with rivers
in it — carries. Land thins toward the north-west into open sea and thickens
south-east into jungle; the bars are lens-shaped and drawn out along the flow;
the walkway chains are visible as thin lines between them; the ring-arch sits on
the centre axis; the stepped temple stands on the eastern rim; the paddy terraces
read as green rectangles inland.

**Where it diverges:**

* **Density of built structure.** The painting shows more settlement from the
  air than the build does — more boats, more roofs, more bridges per island. The
  build is vegetation-dominated at that distance. Adding settlement is the
  single most valuable next pass.
* **Channel depth banding.** The aerial has a strong tonal ladder from pale
  bar-edge shallows through mid-channel to dark navigable water. The build has
  that ladder but weaker: the deep pass reaches the dredged mouths and the sea,
  and the shallow braid between bars reads as one tone.
* **The sea corner.** The painting's north-west is open ocean with a visible
  horizon line. The build drowns that corner correctly but the transition from
  authored terrain to the water plane is a visible straight edge from high
  cameras, because there is deliberately no rim wall.

## Against the ten panels

| # | Subject | Match | Notes |
| --- | --- | --- | --- |
| 1 | Mangrove channel from a canoe bow | **partial** | The channel, the mangrove belt and the far silhouette are there. The canoe bow the panel is framed *through* is not: there is no first-person prop rig in this package, so the shot is a low water-level view instead. |
| 2 | Tiered gilded hall over a plank village | **partial** | The village, the walkways and the hall all exist and the framing now holds all three. The hall's three tiers and bronze finial read at distance; its carved gallery detail does not, because the balusters were thinned from one per 0.46 m to seven per tier to keep the building under 9k triangles. |
| 3 | Boardwalk junction over turquoise shallows | **good** | The closest match of the ten. Deck junction, thatched pavilions, piles, clear water over a pale bed, boats alongside. |
| 4 | Arched market hall on the walkway | **good** | The bent-timber barrel and its canopy read correctly, along the walkway as in the panel. Lateen sailing boats are absent — the region has dugouts and awning boats, no rigged sail. |
| 5 | Deck inside a great banyan's roots | **partial** | The banyan and the landing deck are both built and the camera now sees both. The panel's *enclosure* — being inside the root cage — is not reproduced: the tree's aerial roots are a root spread on a single trunk, not a walk-through structure. |
| 6 | Raft of moored awning canoes | **partial** | 24 awning boats with produce crates are moored at the market, and the framing is among them. The panel's density — boats gunwale to gunwale filling the frame — is not reached; ours reads as a scatter. |
| 7 | Bamboo causeway across lotus and rice | **partial** | The terraces, the lotus beds (219) and the rice clumps (301) exist and the bamboo causeway crosses them. The panel's foreground — individual lily pads and pink flowers at arm's length — does not: the lotus is instanced ground dressing, and there is no pink blossom material. |
| 8 | Flooded ruin with a glowing ring-portal | **out of scope, threshold only** | This panel is the **interior** of the `manymouth_flooded_labyrinth` map, which is a separate 32×32 placeholder. This package ships the way in: the cut arch in the rock headland, glyph-banded, walkable to the door and portalled. The sheet says so on the row itself. |
| 9 | Two figures on a plank deck over the delta | **partial** | The overlook deck exists and looks out over the fan. The panel's read — a high vantage with the whole delta and a far citadel below — is weakened by the overlook's own palms in the near frame, and there is no distant citadel silhouette on the horizon. |
| 10 | Macro: matting, rope, bronze staff, blossom | **good** | Authored as a vignette (`stiltkit.deck_study`) and placed on the arch approach walkway. Woven bamboo matting, a coiled rope, a bronze water jar, a fish trap and a laid staff on wet planking. The fallen blossom is green rather than pink: there is no blossom material, and the petals reuse the foliage atlas. |

Summary: **3 good, 6 partial, 1 out of scope.**

## The three things most worth fixing next

1. **A pink blossom material and a proper lotus flower.** It is the accent colour
   of two panels and the region has no pink in it at all. One small alpha atlas.
2. **Settlement density from the air.** More huts, more moored boats, more short
   spur walkways per inhabited bar. The kit exists; it is a density decision.
3. **A distant citadel silhouette.** Panels 1 and 9 both put spires on the
   horizon. There is nothing on this map's horizon but its own jungle head.

## What could not be compared

* Nothing in this package has been seen in a **networked client session**. The
  frames are real Godot renders of the real GLB through `GLTFDocument`, which is
  the loader path, but no server, no player, no movement.
* The **reduced package** `world-lod2.glb` has never been rendered by Godot;
  nothing selects it.
* The detail board supplied for this region is the intact one — the committed
  `00-concept-detail-board.png` in the placeholder package was truncated to
  786,445 bytes and only its top row decoded. All ten panels were readable for
  this work.
