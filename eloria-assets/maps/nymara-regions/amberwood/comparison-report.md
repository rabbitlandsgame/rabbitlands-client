# Amberwood: concept versus build

Sheets: `references/comparisons/aerial-comparison.webp` (aerial overview),
`references/comparisons/panel-comparison.webp` (all ten close-up panels, concept
left, build right), `references/comparisons/landmark-contact-sheet.webp` (the
twenty-eight further landmark, movement and golden-hour captures).

Every capture comes from the offline renderer in `source/amberwood/render.py`,
driven by the same material table the GLB ships. It is a faithful preview of the
authored asset, **not** a Godot frame — see `validation-report.md`.

## Evaluation against the brief's criteria

| Criterion | Assessment |
| --- | --- |
| Overall geography, composition, silhouette | **Close.** Sea and rugged coast west, forest mass through the centre, monument on the central axis, burnt country and mountain wall east. The concept's diagonal coastline and its forest-to-barren gradient both read in the build. |
| Landmark presence and relative scale | **Close.** All nineteen checklist landmarks are present, grounded and connected by road (`coverage-map.md`). The Amber Gate reads as the dominant silhouette at 20 m; the great tree at 39 m. |
| Forest canopy depth and tree variation | **Good at ground level, still thinner than the concept from the air.** Eleven species, three detail tiers, three canopy palettes, ~2,700 instances over 576 m. Coverage is much improved — forest floor is 41% of the terrain grid — but the concept's canopy is effectively unbroken and ours is not. |
| Architectural shape language | **Close.** Steep shingled roofs, timber frames with real studs and braces, stone plinths, carved brackets, turned balusters, turrets and dormers. |
| Integration with trees, roots, stone, water | **Good.** Platforms are cut around the trunks they sit on and braced back into them; the hollow tree has a modelled chamber and stair; arches carry real root geometry; retaining walls hold the built terraces. |
| Material and colour fidelity | **Improved but not matched.** After a palette pass the canopy reads amber-to-rust and the sea deep teal, but the concept's painted contrast — near-black shadow between crowns, wet dark rock — is still stronger than the build's. |
| Prop and environmental density | **Good in the settlement, sparse in the wild.** 121 settlement props, 20 lamp posts, market, workshops, amber stations, forestry and charcoal works. Only three ruin fragments made it into the forest — the scatter threshold is too tight and is the clearest quick win. |
| Terrain, coastline, water, vegetation character | **Partial.** Sculpted relief, carved watercourses, four waterfalls and a shelving harbour bay all read. The coast is smoother than the concept's stacks and cliffs, and the sea plane's clipped edge is visible from a high aerial. |
| Player-scale detail | **Good.** Leaf-covered trails, lantern posts, porch railings, banners, carts and barrels hold up at 1.7 m eye height. |
| Lighting and atmosphere | **Partial.** Directional sun with PCF shadows, hemispheric ambient and height fog are authored into `world.json`. Falling leaves, mist, chimney smoke and water spray are declared as presentation settings, not yet emitters. |
| Navigation readability | **Good.** Roads are graded into the terrain, cleared of trees, lamp-lit on the main axes, and every landmark has an authored clearance. |
| Repetition and procedural artefacts | **Acceptable.** Palette, species, scale and rotation vary per instance; terrain material boundaries are dithered. Visible repeats remain in shingle and paving tiling at grazing angles. |
| Performance and LOD | **Measured, well over the desktop guideline.** 3.12 M instanced triangles for a region nine times the original area — about 9.4 triangles per square metre — against the repository's stated 1.5 M desktop guideline. A reduced package (`world-lod2.glb`, 2.20 M triangles, 19.4 MB) ships alongside; nothing in the current loader selects between them. |

## The honest headline

The build matches the concept most closely at the **aerial and composition
level** — coastline, forest mass, monument on the axis, burnt east, mountain
frame — and least closely at the **panel level**. Side by side with the painted
close-ups, the geometry is simpler, the material response is flatter, and the
staging is looser: panel 2's hall has the massing and the tracery but not the
carved richness; panel 3's lodge has the porch, chimney and workshop but not the
clutter and warmth; panel 4 shows the colossal trunk but the camera does not
frame the lit arched entrance the concept leads with. Read the sheets as
evidence of what is actually built and where the remaining art distance is, not
as a claim to have matched the paintings.

## Known deviations, stated precisely

1. **Aerial canopy coverage** is roughly 70–80 % of the concept's after the
   coverage pass. Raising it further costs triangles the package can no longer
   afford at this extent.
2. **Instanced triangle count exceeds the desktop budget** by roughly 2.1x at
   LOD1 (3.12 M against 1.5 M) for nine times the original ground
   area. LOD2 is 2.20 M, still above it. Nothing switches between
   the two yet, and neither is streamed.
3. **The coastline is under-detailed**: no sea stacks, no wave foam geometry, and
   the sea plane is clipped at a straight eastern edge visible only from a high
   aerial.
4. **The barren east is under-dressed** compared with the concept's smoke
   plumes, dead stands and roadside wreckage.
5. **Atmospheric effects are declared, not implemented** — no particle systems
   ship in the GLB.
6. **Forest ruin scatter** was three fragments at 192 m and is 71 at 384 m; the
   threshold was corrected with the enlargement.
7. **Framing of a few panel captures is imperfect.** The camera search keeps the
   lens out of solid geometry and requires line of sight to the subject, but in
   the densest parts of the settlement it sometimes settles on a neighbouring
   building.
8. **All place names are invented** — the authoritative written region
   description was not available to this build.
