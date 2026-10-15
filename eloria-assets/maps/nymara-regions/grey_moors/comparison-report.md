# September 2026 visual comparisons

Current measurements and review are in [layout-review.md](layout-review.md).
The current comparison sheets use the 32 Godot frames in
references/godot-captures, rendered with --environment=manifest. Offline
captures use the same camera index. Earlier client-captures remain historical.

The report below records the original pass. Its counts, lighting description
and grades are historical; they are superseded by the current layout review,
performance summary, GLB validator outputs and verification-report.json.

---

# Grey Moors â€” comparison report

The build graded against its two authorities: the aerial concept for
composition, the ten-panel detail board for player scale. Sheets are in
`references/comparisons/`.

**Grades are deliberately harsh.** Where a panel is a partial match it says so
and says why; nothing here is graded on effort.

## What the images are

| directory | what it is |
| --- | --- |
| `references/captures/` | **Offline preview renders**, from the toolkit's own C rasteriser. Not client frames. They use this region's authored overcast light, from `source/views.py`. |
| `references/client-captures/` | **Real Godot 4.7.2 frames**, rendered on an NVIDIA GPU by loading `world.json` through the client's own `WorldLoader.load_world()`. Real engine, real materials, real geometry. |
| `references/comparisons/` | The sheets: `panel-comparison.webp`, `aerial-comparison.webp`, `landmark-contact-sheet.webp`. Built from the **offline** captures. |

One thing to hold on to when reading the client captures:
`_toolkit/godot_capture.gd` lights every region identically on purpose, so
regions can be compared with each other. Those frames are therefore correct
geometry and materials under *standard comparison light*, not under this
region's authored weather. Judge silhouette, scale, placement and material from
them; judge mood from the offline captures.

## The aerial â€” partial match

The composition is right and the density is not.

**What matches.** The web of tracks meeting at three junctions rather than a
road tree; the crowned central barrow with its stone court on a low ridge across
the north-centre; barrow mounds scattered around it; rings and avenues of
standing stones; black bog basins through the low ground; peat cuttings as dark
rectangles; broken towers around the edges; the sea confined to the south-west
corner; waymarker lights strung along the routes.

**What does not.** Three things, honestly:

1. **Density.** The painting reads as a crowded, textured moor â€” stones,
   scrub and broken ground filling every square metre. Mine reads as a broad
   plain with features placed on it. Two rounds of work closed part of this
   (ground cover raised from 1.13 to 2.03 triangles per square metre, and 360
   scattered standing stones added after measuring that the painting's stones
   stand near 5 m and mine were 1.7â€“3.2 m). The gap is narrower than it was and
   it is still the largest remaining difference.
2. **Colour temperature.** The concept is a warm brown-olive-ochre moor shot
   with purple. Mine is cooler and greyer. The palette was warmed once; it is
   still short of the painting.
3. **The world boundary.** The closing rim reads as a stepped scarp at the map
   edge and the distant backdrop as a flat-topped band above it. The painting
   ends in mist. This is inherited from `terrain.clamp_edges` and the shared
   backdrop and is common to the finished regions, but it is more obvious on a
   flat moor than on a mountainous one.

## The ten panels

| # | subject | grade | notes |
| --- | --- | --- | --- |
| 1 | raised causeway | **partial** | The moor around it is right â€” stones, bog, lit markers receding. The causeway itself reads as a broad pale band rather than the concept's narrow wet flagstone track vanishing into mist, and the frame is looking at a bridge crossing rather than along the track. |
| 2 | turf barrow | **good** | Mound, lintelled megalithic doorway, votive light in it, kerb stones, candles on the threshold. The revetment reads as a flat wall rather than visibly coursed drystone at this distance, and the mound is greener than the painting's. |
| 3 | standing stones | **good** | Inside the ring, menhirs of varied height and lean, one fallen, the low altar slab at the centre, more stones behind. The stones are smoother and paler than the concept's rough lichened granite. |
| 4 | bog boardwalk | **partial** | The boardwalk, its driven posts and its rope handrail are all there and correct. But the camera sees it side-on rather than standing on the deck looking along it, and the bog beneath reads as a hard-edged pool rather than as sodden ground. |
| 5 | crypt threshold | **fair** | Square on to a lintelled doorway with warm light and candles, on its stepped surround. Two real misses: **the runed carving does not read at all** â€” the jambs look plain at this distance â€” and the light is a visible emissive sphere rather than light spilling from an opening. |
| 6 | abandoned cottage | **good** | Drystone walls, standing gable with what is left of its sod roof, collapsed far end, fallen roof timbers, a cairn beside it, the sea behind. The walls are more regular than the painting's tumbled ones. |
| 7 | wisp tree | **good** | The whole gnarled dead tree in frame with its root spread, marsh lights beneath it. The tree is less contorted than the concept's and its branches thinner. |
| 8 | peat and orchids | **partial** | The stepped cut bank, the timber winch and the drying turves are right. Two misses: the bank reads as clean geometric steps rather than cut peat, and **there are no flowers in frame** â€” the bog cotton exists in the scrub atlas but is rare and none fell in this shot. |
| 9 | coastal panorama | **partial** | Much improved after the bay was widened from 2.6% to 5.8% of the map: a real bay with cliffs, not an inlet. But the water plane's edge is stepped at its 4 m sampling grid, so the shoreline is visibly geometric, and the sea is a more saturated teal than the concept's grey-green. |
| 10 | material study | **partial** | Shows peat, wet stone and heather at close range beside a fallen slab, which is the right subject matter. It is a low three-quarter view of standing stones rather than the concept's near-macro of ground materials, so it reads as a scene rather than a study. |

**Summary: 4 good, 1 fair, 5 partial, 0 failures.** Every panel's subject exists
in the map and is findable; five of them are framed or resolved less well than
the board shows.

## What the real client frames added

Worth recording, because the offline previews were clean throughout and would
have shipped a visible defect:

The first Godot capture came back with **every scrub clump on the map shaded
solid black**. Three compounding causes, none of which the offline renderer
exercises: card normals perpendicular to a vertical card, an atlas drawn on a
black background so mipping averaged plant colour with void, and a double-sided
material â€” which makes Godot invert the normal on the back face, turning an
up-leaning normal into a down-leaning one. Fixed by bending the normals up,
bleeding colour into the transparent texels, and giving each card an explicit
back face so the material can be single-sided.

The client frames also showed the barrow turf reading as mown lawn, which the
offline light had hidden.

That is the case for capturing through the real engine: a region can pass both
validators, look right in every offline preview, and still be wrong.

## Known visual limitations

- **Surface-class boundaries are visibly polygonal.** Terrain classes are a hard
  per-cell choice on a 2 m grid, so a bog meeting a moor is a staircase of 2 m
  quads. Dithering softens it; it does not remove it. Most obvious where peat
  meets heather in flat open ground.
- **The water plane's shoreline is stepped** at its own 4 m sampling grid.
- **The votive lights are emissive spheres.** The package ships no
  `KHR_lights_punctual` â€” it must load with no extensions â€” so a candle is a
  small bright ball rather than a light source, and nothing near it is lit by
  it.
- **The revetment and drystone courses stop reading beyond about 15 m.** Block
  size is 0.3â€“0.6 m against a 512-texel material, so at distance the walls flatten
  into planes.
