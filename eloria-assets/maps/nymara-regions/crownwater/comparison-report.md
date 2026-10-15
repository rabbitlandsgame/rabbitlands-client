# Crownwater: concept versus build

Sheets in `references/comparisons/`:

- `aerial-comparison.webp` - the aerial concept beside the build's aerial
- `panel-comparison.webp` - all ten detail-board panels, concept left, build right
- `capture-contact-sheet.webp` - all 23 client captures

**Every build capture is a real Godot 4.7.2 client frame**, produced by
`godot-client/tests/integration/rendered_crownwater.gd` through the client's own
`WorldLoader` and `WorldEnvironmentBinder`. They are not offline previews.

## The detail board

The board shipped in the repository was truncated - 786,445 bytes, of which
**91 of 793 pixel rows decoded**. An intact 3,395,261-byte board was supplied
during this work and is now committed here, replacing it. All ten panels crop
cleanly and `panel-comparison.webp` is a genuine side-by-side.

`source/make_sheets.py` still measures how many rows decode and falls back to
printing each panel's written description if it is ever handed a broken board
again. It is used in place of `_toolkit/make_comparison.py`, which against a
truncated board does not fail - it crops garbage and presents it as concept art.

**Fifteen of the other sixteen region boards in this repository are still
truncated to ~786 KB.** Only `amberwood` and `sunmane_steppe` are intact. That
is worth fixing centrally rather than region by region.

## What changed once the real panels were visible

Seven of the ten framings were re-aimed against the actual artwork, and five
things were changed in the map itself. Recorded because none of it was visible
from the aerial concept alone:

| Change | Why |
| --- | --- |
| Cathedral precinct raised 9 m | The palace sat at island level, 100 m in from an 8 m shore, so from any boat you saw a grassy rise with a dome behind it. The concept's palace stands on terraces above the water. Lifts the silhouette clear of the island's own horizon; improves panels 1, 9, 11 and 12. |
| Lagoon alpha 0.82 to 0.70 | The concept's water is clear enough to read the seabed everywhere. At 0.82 nothing submerged came through and panel 7 was a blank turquoise field. |
| Sunken court raised to -1.05 m | At -1.90 even the clearer water washed the mosaic out completely. |
| Gilt metallic 1.0 to 0.34 | The client renders through OpenGL 3.3 compatibility with no image-based lighting, so a fully metallic surface has nothing to reflect and renders near-black. Every gilt finial and the panel-10 bollard were dark blobs. |
| Banner cloth to canvas | Wool is dark enough that a banner reads as a black slab against a bright sky; four of them stood across panel 2 like shutters. |

A `deck` camera mode was also added to the view emitter. It snaps an eye to the
walk surface beneath it, the way the client grounds an actor. A ground-relative
height cannot express "stand on a causeway", because the ground under one is
sometimes the lagoon floor at -6.6 m and sometimes an island shelf at -1.3 m, so
the same declared height lands 1.7 m above the deck in one place and 7 m above
it in another. Two attempts at panel 4 failed exactly that way.

## Panel by panel

| Panel | Subject | Assessment |
| --- | --- | --- |
| 1 | Palace across open water from a barge | **Partial.** The domed complex on its raised precinct now reads across the lagoon, but the concept's palace fills the frame and rises straight out of the water. Mine is a smaller mass on a large island, seen from further off. The clearest remaining structural gap - see below. |
| 2 | Quayside: bollards, rope, moored boat | **Partial.** Bollards, mosaic apron, lamps, moored boats and the city beyond all read at standing height. The concept is a tighter, busier, more elevated shot with barrels, crates and crowds; the build's quay is bare by comparison. |
| 3 | Plaza with compass-rose mosaic and fountain | **Close.** Inlaid gilt compass rose, fountain, statues, domed mass behind. The concept's plaza is enclosed by buildings on all sides; mine is open on three. |
| 4 | Long arched causeway over clear water | **Close.** Standing on the deck with balustrades either side and the cathedral at the end of the run. One of the best matches. |
| 5 | Islet with domed pavilion and stairs to water | **Close.** Pavilion, podium, planting, quays and turquoise shallows. The concept's islet carries more building and a proper water stair. |
| 6 | Waterfront walk, lamp standards, banners | **Close.** Lamp line receding along a mosaic quay with causeway and city behind. |
| 7 | Submerged tiled platform seen through water | **Partial.** The court and its inlaid figure now read through the surface. The concept's water is clearer still and its platform crisper; mine is soft and low-contrast. |
| 8 | Garden plaza, concentric beds, fountain | **Close.** Concentric hedge rings around a centre, palms, water beyond - the structure of the concept panel is there. |
| 9 | Rooftop across a gilt-finialled dome | **Close.** Verdigris dome, gilt finial, lesser domes, causeways and lagoon beyond. |
| 10 | Macro: brass bollard and rope on a quay edge | **Partial.** A true macro of a gilt bollard on mosaic paving at the water's edge. The concept has the mooring rope coiled around it, lily pads and a carved kerb; mine has the bollard and the paving. |

## The honest headline

Composition and materials are close. The radial archipelago, the causeway
network, the marble-and-verdigris palette and the turquoise water are all
genuinely there, and they are there in real client frames.

**Density is the gap, and it is a large one.** The concept is a city: every
island carries a cluster of halls, towers, terraces and planting, and every quay
is busy with people and cargo. The build gives most islands a single pavilion on
open ground and no people at all. That is a further population pass over
`populate.py` using kit that already exists, not a redesign - but it is not done.

**Second gap: the crown isle is too large for its palace.** The concept's central
island is barely wider than the building on it, so the palace rises out of the
water. Mine is 190 m across with a 40 m cathedral in the middle. Raising the
precinct helped the silhouette but did not change that proportion. Shrinking the
crown isle to roughly 60 m radius would be the faithful fix; it would also
change the aerial composition, which currently matches the concept well, so it
is deliberately left as a decision rather than taken unilaterally.

**Third: terrain finish.** Island edges are stepped where the plateau falloff
meets the 2 m terrain grid, and the waterline is faceted at 3.5 m. Neither is in
the concept and both are the first thing visible at close range.
