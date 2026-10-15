# Mirrorhold: build against concept

Sheets in `references/comparisons/`:

| Sheet | What it shows |
| --- | --- |
| `aerial-comparison.webp` | The aerial concept above the build's overview |
| `panel-comparison.webp` | All ten detail-board panels beside the matching shot |
| `landmark-contact-sheet.webp` | Every capture in the set |

**The right-hand column is a real Godot frame**, not the offline preview
renderer — `make_comparison.py` prefers `references/godot-captures/` when a
package has it, and captions which it used.

## Read the caveat first

Five of the ten concept panels are not in this repository, and a sixth of the
other five is missing. `references/00-concept-detail-board.png` is truncated to
786,446 bytes, and only about **24% of the top row's height decodes**; the
bottom row does not decode at all. The sheet says so per panel rather than
showing black and letting it read as an empty concept.

The modelling itself was done against an intact board supplied in conversation,
which could not be written to disk. Drop the full file in and re-run
`make_comparison.py` and the sheet is complete.

## Aerial

The build follows the painting's structure: glacier and bare peaks closing the
north, the observatory citadel on the summit massif with the mirror-sphere
above it, a terraced civic descent down the south face, and the lake in the
southern basin with the ring at its centre on radial causeways. Roads
switchback between the bands, and conifer stands break up the middle slopes.

Where it differs, and these are the honest gaps:

1. **Density.** The painting is built across its whole middle band — terraces,
   walls, arcades and roofs to the frame edges. The build has the citadel, the
   civic descent, the stair town and eighteen satellite sites. It reads as the
   same place, more thinly settled.
2. **Vertical drama.** The concept's cliffs are near-vertical with structures
   cantilevered off them. The build's slopes are walkable, because the region
   has to satisfy a grounding contract across all 331,776 server tiles.
3. **The east quarter and the far south** are the thinnest ground.
4. **Waterfall count.** The painting has water falling almost everywhere;
   the build has eleven, at the terrace edges and the canal district.

## Panels

| # | Panel | Concept available? | Verdict |
| --- | --- | --- | --- |
| 1 | Grand causeway to the monumental gate | ~24% | Matched in language: the gate wall, its crystal panels and the gilded corner domes read against the snow peak. The causeway itself is a graded road rather than the concept's monumental stair. |
| 2 | Canal and waterfall district | ~24% | Partial. Channels, retaining walls and terrace falls are there; the concept's dense arcaded frontage is not. |
| 3 | Tiered fountain plaza | ~24% | Structure matched — tiered fountain, statues, crystal lamps, gilded pavilion behind. The concept's facade is far more ornate. |
| 4 | The ring on the mirror lake | ~24% | The closest match in the set. Colonnaded ring, inner basin, four radial causeways, turquoise glacier-fed water, cliffs behind. |
| 5 | Mirror-sphere in its armillary | ~24% | Matched. Brass rings, tilted, around a dark polished sphere on its drum, snow peak behind. |
| 6 | Blue rose window and gallery | not in repo | Built: gilt tracery wheel over blue crystal on the gallery's south face, above a run of crystal panels. Cannot be compared. |
| 7 | Stepped cliff town | not in repo | Built: five shelves of stone houses with slate roofs, timber jetties and lit crystal windows. Cannot be compared. |
| 8 | Harbour quay and piers | not in repo | Built: masonry quay with a walkable apron, three piers, moored boats, bollards, crates and barrels. Cannot be compared. |
| 9 | Terrace overlook toward the peaks | not in repo | Built: balustraded terrace and gilded pavilion looking north to the summit. Cannot be compared. |
| 10 | Gate wall detail in snow | not in repo | Built: gilt-framed crystal panels and banners in the wall face, snow on the ledges. Cannot be compared. |

So: **five panels compared against a quarter of their concept, five not
compared at all.** Every one of the ten has a shot in the sheet, and the build
was authored against the intact board — but this repository cannot currently
demonstrate that, and this report should not pretend otherwise.

## What would close the gaps

In the order that would matter most:

1. Restore the detail board and re-run `make_comparison.py`.
2. Raise built density across the middle band — more terraces, arcades and
   roofs east of the citadel and south of the canal district.
3. Ornament the principal facades: the concept's language is heavily carved
   and arcaded, and the build's blocks are plainer than that.
4. More water: falls off more terrace edges, and channels running with the
   roads rather than only in the canal district.
