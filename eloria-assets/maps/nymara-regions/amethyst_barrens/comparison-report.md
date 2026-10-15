# September 2026 update

Current layout measurements, visual review and limitations are in
[layout-review.md](layout-review.md). The current comparison sheets use the
35 frames in references/godot-captures with the manifest environment.
Validator JSON and verification-report.json describe the current package.

The original report below is historical. Its counts, camera descriptions and
grades are superseded by the current review and performance summary.

---

# Amethyst Barrens â€” concept comparison

Sheets are in `references/comparisons/`:

- `aerial-comparison.webp` â€” the aerial concept against the build
- `panel-comparison.webp` â€” all ten detail-board panels, concept beside build
- `landmark-contact-sheet.webp` â€” the twenty supporting views

Two capture sets exist and they are **not** the same thing:

| Directory | What it is |
| --- | --- |
| `references/captures/` | the offline rasteriser in `_toolkit/native/`. A preview. **Not a client frame.** |
| `references/client-captures/` | Godot 4.7.2 on an NVIDIA GPU, loading `world.json` through the client's own `WorldLoader.load_world()`. Real engine frames, rendered by the shared `_toolkit/godot_capture.gd`, which lights every region the same way so regions can be compared with each other. |

The comparison sheets are built from the offline set, because that is what
`make_comparison.py` consumes. The client set is the better evidence and is what
the assessment below is based on.

## What matches

**Composition (aerial).** The road web across the basin, the Glasswarden
Observatory on its terrace in the north-west, the crystal massif in the
north-centre, the mountain ring closing north and west, and sea in the
north-east and south-east corners with a dry headland between them â€” all of it
is where the painting puts it.

**Panel 2, the Observatory.** The strongest match. Domed hall on a walkable
podium, verdigris roof, corner pinnacles, balustrade, and the brass armillary
sphere on the dome reading as the tallest built thing in the region.

**Panel 5, levitating shards.** A large stone hanging low with smaller shards
around it, over open barrens. Reads correctly at player scale.

**Panel 6, storm ruins.** Broken colonnade, surviving lintels, a standard on a
pole, crystal pushing up through the floor.

**Panel 11 / the massif.** Large faceted spires on a rock hill. The faceting
matters: crystal is flat planes meeting at hard edges, and the first version â€”
smooth lofted rings â€” read as violet carrots.

**Landmark inventory.** Exactly the counts the QA brief and the placeholder
`world.json` specify: 1 observatory, 7 crystal bridges, 4 geode caves, 8
levitating-shard fields, 6 storm ruins, 10 resonant clusters, 6 field stations.

## What does not match â€” the honest list

1. **Density.** This is the biggest gap. The concept is crowded: dozens of
   slender spires, ruin compounds, tents and small structures fill the plain
   between landmarks. The build has 47 landmarks and ground scatter, and reads
   as an empty plain with things on it. At 1.34 unique triangles per square
   metre against Amberwood's ~9.5, there is a large budget left to spend
   precisely here.

2. **Hard-edged ground patches.** The terrain surface class is a per-cell choice
   on a 2 m grid, so a crystal or roadway patch renders as a flat polygon with
   straight edges lying on the ochre. Two dither passes and much smaller patches
   improved this a lot, but the *authored* surfaces are still crisp by design:
   the arrival apron and the ten digging terraces are discs and rectangles of
   `ResonantRoad` and `CrystalField`, and they read as laid plazas rather than
   as worked ground. Visible in `01-barrens-road`, `03-crystal-bridge` and
   `07-resonant-digging`.

3. **The ground is two colours.** Ochre dust and pale violet crystal, meeting at
   a boundary. The concept's ground has far more tonal variety â€” scorched
   patches, gravel, wet rock, shadow.

4. **Verdigris still darkens.** Spire caps and bridge lamp cones read as dark
   cones rather than teal in the client. Lowering the metallic value from 1.0 to
   0.12 fixed the worst of it, but a cone whose faces point away from the single
   directional light still has almost nothing to reflect. This wants either a
   reflection probe in the client or a brighter ambient term.

5. **Panel 4, geode cave, does not read.** The rock collar frames the opening
   correctly in isolation, but placed against rising ground and seen from the
   camera in `views.py`, it reads as a rock lump with a crystal wedge rather
   than as a cave mouth. Either the camera or the placement is wrong; the mesh
   is probably fine.

6. **Panel 10, material study, is not a still life.** The concept panel is a
   close arrangement of amethyst chunks, a brass compass, a vial and a carved
   tablet on a ledge. The capture is a single large outcrop filling the frame.
   The props for this panel were not modelled.

7. **Panel 1's watchtowers are distant.** The concept has two slender lit towers
   framing the road at middle distance. Three towers exist and are placed at the
   region's edges, so the road view does not frame them the way the panel does.

8. **`09-cliff-overlook` blows out.** The distant half of the frame washes to
   white under the region's fog settings at that draw distance. The fog density
   in the manifest is tuned for ground-level views.

## Aerial concept vs build

The build's aerial reads as the same map. The differences are the density point
above, and that the massif dominates the top third of the painting while in the
build it is a distinct but not overwhelming feature. The painting's shards are
enormous relative to the basin; the build's largest is 58 m.
