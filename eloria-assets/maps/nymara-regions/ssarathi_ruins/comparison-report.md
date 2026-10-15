> Historical report: the September 2026 circulation pass is documented in
> [layout-review.md](layout-review.md). Its measurements supersede this report.

# Ssarathi Ruins: concept versus build

Sheets:

* `references/comparisons/aerial-comparison.webp` — the aerial concept above the
  build's matching framing.
* `references/comparisons/panel-comparison.webp` — all ten close-up panels,
  concept left, build right.
* `references/comparisons/landmark-contact-sheet.webp` — the further landmark,
  movement and golden-hour captures.

**Two sets of captures ship, and they are not the same thing.**

* `references/captures/` is the **offline preview renderer**
  (`_toolkit/amberwood/render.py`), driven by the same material table the GLB
  ships. It is a faithful preview of the authored asset. **It is not a Godot
  frame.** The comparison sheets above are built from these.
* `references/client-captures/` is **twenty-four real Godot 4.7.2 frames**,
  rendered on a GPU through the project's own `WorldLoader`, lit by this
  package's own `environment` block through the project's own
  `WorldEnvironmentBinder`. These are what the game will actually show.

The two differ visibly: the client frames are cooler, higher-contrast and
carry real cascaded shadows, and their fog and tonemap come from the manifest
rather than from the preview renderer's own lighting model. Where they
disagree, **the client frames are the truth** and the preview is the
art-direction tool.

## Panel by panel

| # | Assessment |
| --- | --- |
| 1 | **Close.** The framing is the concept's: a paved causeway receding north between water and ruins, serpent columns flanking it in receding pairs, the temple closing the axis with its sun disc. The build is emptier — the concept's causeway runs between continuous architecture and ours runs between scattered blocks and water. |
| 2 | **Close on massing, far on ornament.** Stepped stages, scale-tiled cornices, gilt string courses, the stair on the axis, serpent volutes and the summit shrine all read. The concept's facade is covered in figurative carving, tiered galleries and flanking waterfalls; ours has none of the carving and the falls are elsewhere in the region, not at this framing. |
| 3 | **Close.** The subject is matched: a recessed stepped portal closed by a great circular sun-disc door with guardian faces either side. Ours is flatter — the concept's door is deep bronze relief with concentric glyph rings and ours is a rayed disc with a face. |
| 4 | **The weakest panel.** The capture shows the channel, the causeways and the water correctly, but the bridge itself is too far away to read as an arch. The geometry is right — a segmental span with the arch below the deck, checked in isolation — and the framing fails to show it. A reviewer should treat panel 4 as unproven. |
| 5 | **Good.** The circular terraced court, the sunken pool, the colonnade ring with a third of it broken, and lily cover all read. The concept has concentric terraces stepping down to the water and far more statuary; ours is one rim and one pool. |
| 6 | **Partial.** Pool, rim, lilies and colonnade are present. The concept's columns are close, paired and massive and dominate the frame; ours stand across the pool and read as a distant ring. |
| 7 | **Partial.** The stela carries a gilt sun face on a jade slab, which is the subject. The capture crops to the head of the stela and loses the stepped plinth, the knoll and the ruins behind that the concept frames it against, and the sun face reads more graphic than carved. |
| 8 | **Good.** Broken arch, unequal piers, fallen voussoirs, a rubble field, strangler roots crossing the opening and the tree they come from. The concept's masonry is coursed and weathered in a way ours is not, and its root system is far denser. |
| 9 | **Good.** The elevated three-quarter view over the causeway network reads much as the concept's does. No waterfall is in frame, which the concept has on the left. |
| 10 | **Partial and mis-framed.** The capture is of the carved guardian face, which is one of the panel's four subjects. The scale tiling, the gilt scrollwork and the shell boss are all built — `ssarathi_jade_scale` is drawn as real overlapping scales precisely for this panel — and the camera does not frame them. |

## Evaluation against the brief's criteria

| Criterion | Assessment |
| --- | --- |
| Overall geography, composition, silhouette | **Close.** Flooded basin, causeway grid, temple on the north axis, courts either side, market and docks on the fringes, jungle closing every horizon. The aerial reads as the painting's plan. |
| Landmark presence and relative scale | **Close.** All ten panel subjects are built, grounded and connected by route. The temple is the dominant silhouette at 56 m; nothing else competes with it, which is right. |
| Density and canopy | **Improved but still below the concept.** 2,089 trees, 55 ruin buildings, 21 towers, 69 blocks. The massing pass took the region from a causeway network on an empty lake to a city; it is still airier than the painting. |
| Architectural shape language | **Partial.** Battered stages, coursed jade ashlar, scale tiling, gilt string courses, serpent volutes, obelisks and stepped reveals. No figurative carving anywhere. |
| Integration with water, roots, stone | **Good.** Causeways are retained embankments at the waterline, the drowned quarter is paving under water, trees grow through the ruin blocks, roots cross the arch, vines fall down every masonry face. |
| Material and colour fidelity | **Improved but not matched.** Jade paving with gilt inlay, verdigris ashlar, scale tiling and turquoise water are the concept's palette. The painting is richer and darker — its deep shadow between masses and its warm gold highlights are both stronger than the build's. |
| Terrain, coastline, water character | **Good.** Shallow water over a visible silt floor, three deeper carved channels, two waterfalls, a closed valley rim. |
| Player-scale detail | **Adequate.** Kerbs, balustrades, lamp posts, market stalls, rubble, lily rafts and vine curtains hold up at 1.7 m. The causeway is bare compared with the concept's clutter. |
| Lighting and atmosphere | **Verified, and tuned against real frames.** The manifest environment was corrected three times against Godot output — the first version rendered dim and flat because it declared no `tonemap` and put the sun almost vertical. Particles are declared, not implemented. |
| Navigation readability | **Good.** Routes are graded, cleared of vegetation, kerbed and lamp-lit; every landmark has an authored clearance. |
| Repetition and procedural artefacts | **Acceptable.** 2,895 placements over 89 unique meshes, varied by scale, rotation and per-instance seed. Visible repeats in the ruin-building kit at close range and in the paving tiling at grazing angles. |
| Performance | **Measured, modestly over the guideline.** 1.88 M instanced triangles, 5.67 per square metre, ~1.25x the 1.5 M desktop guideline. LOD2 at 855 k is inside it. |

## The honest headline

The build matches the concept most closely at the **composition and plan level**
— the flooded basin, the causeway grid, the temple on the axis, the two courts,
the jungle rim — and least closely at **ornament and density**. Side by side
with the painted panels, the geometry is simpler, there is no figurative
carving anywhere in the region, and the city is airier than the painting's.

Panels 4, 7 and 10 are additionally let down by their **framing** rather than by
the geometry: in all three the built subject exists and the camera does not show
it properly. That is worth fixing before the sheets are used to judge those
three.

Read the sheets as evidence of what is actually built and where the remaining
art distance is, not as a claim to have matched the paintings.

## Known deviations, stated precisely

1. **Vertical density is the largest gap.** The concept's skyline is dozens of
   towers and spires; the build has 21 towers, 9 obelisks and the temple.
2. **No figurative carving.** Every relief in the region is geometric or a
   guardian face. The concept's temple front, its arches and its stelae are
   covered in figures.
3. **Three panel captures are mis-framed** — 4 (bridge too distant to read as an
   arch), 7 (plinth and setting cropped out), 10 (frames the face, not the
   material board it is a close-up of).
4. **The build is cooler and lower-contrast than the painting** in both
   renderers, and more so in the client than in the preview.
5. **No boats, no figures, and no suspended platform** — three things the aerial
   contains that are not built. See `coverage-map.md`.
6. **Atmospheric effects are declared, not implemented.** No particle systems
   ship in the GLB: mist, spray, insects and birds are presentation settings for
   whoever writes them.
7. **The aerial comparison framing was changed** partway through, from a camera
   covering the whole 576 m region to one covering the city core. The
   composition is written in a 192 m design space and scaled by `region.SCALE`,
   so framing the whole map compares the painting against three times its own
   extent. `30-region-overview` keeps the wide shot.
8. **All place names are invented.** No authoritative written region description
   was available.
