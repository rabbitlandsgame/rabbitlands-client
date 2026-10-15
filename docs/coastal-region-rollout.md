# Coastal landscapes

Westhaven, Four Gates and Crownwater each use a 396 × 396 metre playable
footprint. The replan shortens empty travel while retaining the dimensions of
useful buildings, gate passages, bridges, workshops and combat space. Their
different shores, civic histories and daily work determine their layouts.

| Region | Landscape and identity | Inhabitation and travel |
| --- | --- | --- |
| Westhaven | A south-facing working harbour below a climbing masonry town, sheltered Gullscar pasture and two exposed rocky islands | A quiet cargo strip serves loading doors, working piers, shipyard and four services. Full-sized houses face lanes and yards. The Long Arcade and church have a retained civic court; a quay ramp and footbridge reach Gullstone, while the eastern path reaches Lamp Rock. A dry shingle wrack shelf gives shore resources and fauna actual room outside the road. The League Post-House retains its returned-mail and countersign story. |
| Four Gates | A formal civic island with four avenues descending to causeways, an irregular limestone shore and a northern Sanctuary shelf | The monument, gatehouses and native shops remain full-sized. A smaller central square, ring street and six frontage parcels organize the city. Outer working shores, tutorial gardens and two separate 35 × 35 metre practice areas retain their roles and 40/60 caps. The Sanctuary has an authored stair and clear approach. |
| Crownwater | A compact archipelago with meaningful open water between inhabited islands, pearl-working shores, garden banks and quiet reefs | A sheltered harbour holds services, ferry crews' cottages, net-menders, customs and cargo yards. The Crown Basilica, tower and pavilions retain their scale. Separate packet piers keep the six ferries recognizable journeys. Feather palms follow sheltered ground, and exposed shores stay sparse. The drowned court and Grating story remain. |

Westhaven's origin is `(120,172)`, Four Gates' is `(198,198)` and Crownwater's
is `(120,120)`, with one metre per server collision tile. These are local map
coordinates; the map frames establish the relation at a surveyed crossing.
The three regions are not a uniform miniature of their earlier packages.

## Three shared joins

| End A | End B | Authored approach |
| --- | --- | --- |
| Grey Moors `west-waygate` | Westhaven `north-road` | Pasture, moor grass and packed earth meet along the upland road. |
| Mirrorhold `south-road` | Four Gates `north` | A graded receiving road meets the northern stone causeway and Sanctuary approach. |
| Four Gates `west` | Crownwater `east-quay` | A seven-metre clear stone carriageway crosses continuous water and meets both island approaches. |

The shared authoring API is
[`streaming_borders.py`](../eloria-assets/maps/nymara-regions/_toolkit/streaming_borders.py).
Its reciprocal frames reserve the last 42 metres of each collar, with a
40-metre half-width receiving view. Doors and services remain outside those
collars. Terrain, exposed deck triangles and static previews agree at the seam;
the receiving scene includes props whose full transformed bounds meet the view,
including near-edge boulders and canopies. Each biome keeps its own material
and vegetation decisions beyond the shared approach.

The six previously surveyed northern links plus these three authored joins
bring published coverage to **9 of 17 land links**, excluding ferries. The final
coastal client run completed **42 of 42 handoffs**: three joins, both directions
and seven road lanes, with zero failures and all 294 hashed inputs unchanged.
East and south Four Gates, Westhaven's east road and the remaining
southern roads retain their current ordinary transitions until their receiving
regions are rebuilt.

## Preserve content and real floor support

All existing ordinary portal, interior and secret identities remain. Westhaven
retains eleven ordinary portals and fourteen exterior secrets; Crownwater
retains fourteen ordinary portals, twenty landmarks and thirteen exterior
secrets. Their existing combined interior packages remain destinations.

Four Gates retains six separate native interiors, each with a real automatic
door and corresponding return post:

| Room | Map ID |
| --- | --- |
| Lantern Row | `four-gates-lantern-row` |
| The Reedworks | `four-gates-reedworks` |
| The Stormglass House | `four-gates-stormglass-house` |
| Mirrorsmith's Forge | `four-gates-mirrorsmith-forge` |
| The Ferryman's Rest | `four-gates-ferrymans-rest` |
| Deposit of the Four Keys | `four-gates-deposit-four-keys` |

The final collision pass samples the **actual actor centre at tile + 0.5**,
matching `CoordinateAdapter`. The inherited fold was centred on integer
coordinates and could retain unsupported pier edges. The shared
[`guard_actor_surfaces.py`](../eloria-assets/maps/nymara-regions/_toolkit/guard_actor_surfaces.py)
now runs after height refinement, exposed-deck opening and solid-landmark
stamping. It closes unsupported, submerged or incorrectly grounded folded
tiles. The server publisher preserves this guarded geometry: it does not reopen
content tiles, add artificial joins or relax steps to conceal a broken road.

Single-arrival connectivity is supplemented by exact `World.find_path` ends
and bounded road lengths. NPCs, resources and encounter footprints must fit on
reachable ground with space left for travel. Authored habitat packing rejects
missing wildlife counts. Live tests must still exercise occupancy, positive
service replies, doors in both directions and actual map transitions.

## Reproduce and publish the paired contracts

From the client checkout, with the matching server checkout and ELM output
directory specified explicitly:

```powershell
python eloria-assets/tools/rebuild_coastal_regions.py --server ../wt-coast-server --data ../work-output/coastal-rollout/eloria-data
```

The [coordinator](../eloria-assets/tools/rebuild_coastal_regions.py) rebuilds
the three new exteriors and the receiving Grey Moors and Mirrorhold packages,
applies guarded coordinate migrations, publishes collision and scoped content,
synchronizes portals and registry transforms, then regenerates the continent
map. `--skip-build` publishes reviewed packages; `--stage prepare`, `collision`,
`content` or `publish` resumes a contract phase. These commands write to the
specified server checkout and output directory, so they belong to the paired
integration run rather than an independent regional preview.

To regenerate Four Gates' six native room meshes as well, first run:

```powershell
python eloria-assets/maps/four-gates/source/rebuild_landscape.py --rebuild-interiors
```

The coordinator always exports their served collision and synchronizes their
door contracts. Regional sources remain the authority for terrain, plots,
roads, named content posts and deterministic population. Never replace an
authored source correction with an unexplained edit to a generated GLB or grid.

The artifact entry point is
[`work-output/coastal-rollout/index.html`](../../work-output/coastal-rollout/index.html).
It links all three regional reviews, raw gameplay-camera before/after evidence,
geometry-derived minimaps, provenance and strict route checks. Camera labels and
SVG annotations sit above or beside untouched raw images. The final combined
regional result covers **58 exact routes, 254 legs and 134 grounded captures**,
with maximum measured ground offset **0.020092 metres**. The
[coverage verifier](../../work-output/coastal-rollout/verify_final_coverage.py)
accepts only complete successful routes whose exact fixture matches the current
canonical file. The [coverage report](../../work-output/coastal-rollout/regional-final-coverage.json)
records 293 common unchanged inputs and verifies all 297 replay inputs against
the current files after publication.

This is **56 complete routes from the full run plus two complete successful
replays**. The full run recorded two failures and exited with code 2; the replay
completed both routes, eleven legs and 33 checks with no failures and exit 0.
The corrections moved the Cistern start to clear floor and added an open-court
waypoint to avoid an unintended Four Gates doorway. Both raw reports, both
fixtures and both provenance records remain linked in the review. Failed
partial routes contribute no aggregate coverage; this is not a claim that the
full 58-route run exited successfully.

The completed final [crossing report](../../work-output/coastal-rollout/live-streaming-final/walk-report.json)
records three routes, 42 handoffs, 347 positive checks and exit 0. Its
[provenance](../../work-output/coastal-rollout/live-streaming-final/provenance.json)
records 294 unchanged inputs. Every crossing retained the Traveller and reused
the preloaded scene. The final crossing 29 raw pair confirms that low causeway
curbs remain present and opaque during adoption; tall occluding structures
retain their ordinary fade behaviour.

All-42 captured handoff frames measured median **201.4345 ms**, interpolated
p95 **255.12665 ms**, and maximum **701.117 ms**. Peak reported static memory was
**847,233,991 bytes (808.0 MiB)** with one resident neighbour. The largest observed
incremental retirement slice was **4.928 ms**; focused runtime tests separately
cover bounded retirement. These are instrumented GL Compatibility client frame
intervals at 1440 × 900 and 100 ms test movement, not isolated GPU timings.

The longer regional run provides a separate retirement workload: **72 events**,
including **six 12,020-node Manymouth evictions**, with maximum measured slice
**20.102 ms**. The two-millisecond budget is soft because a single atomic
node/resource release can exceed it. These retirement slices are distinct from
the **701.117 ms whole-frame** handoff maximum. The actual
[retirement events](../../work-output/coastal-rollout/live-regions-final/retirement-summary.json)
are preserved.

The earlier diagnostic's **3,001.312 ms** frame remains documented. The final run
never preloaded Manymouth and held only one neighbour, compared with two in the
earlier run. Its lower timings and memory therefore do not establish a
like-for-like teardown improvement. Both runs show visible handoff pauses.
See the [measured summary](../../work-output/coastal-rollout/live-streaming-final/summary.json)
and [diagnostic performance analysis](../../work-output/coastal-rollout/handoff-performance-audit.md).

The final regression battery passes 72 client tests plus 310 subtests, 207
server tests, and a final 19-test door/contract subset. A further **100-test
coordinate/achievement batch** verifies saved Lantern handoff recovery at the
current arrival and classifies all six standalone Four Gates rooms as interiors,
while retaining the eleven-interior achievement threshold. This resolves the
classification failure in the earlier supplemental 113-pass run. Four collision
provenance regressions isolate and correct the missing Git-commit report field;
the served grids remain unchanged.

The final [publication repeat](../../work-output/coastal-rollout/publication-repeat.json)
reproduces **all 248 served map, package and profile files byte-for-byte**, with
exit 0. The three-region batch is prepared on the local paired feature branches;
the previous northern batch is already merged and pushed to develop.

## Remaining biomes and the next linked group

Complete **Sunmane Steppe → Verdant Stair → Ssarathi Ruins** next. They form a
connected chain with useful receiving approaches already available in Amethyst
Barrens and Four Gates. This would address five more land links: Amethyst–Sunmane,
Four Gates–Sunmane, Sunmane–Verdant, Verdant–Ssarathi and Four Gates–Ssarathi.
Manymouth Delta can then close the three remaining western links to Ssarathi,
Grey Moors and Westhaven. Extents below are targets, subject to service,
encounter and practical-path checks.

| Region | Target extent | Terrain, water and habitation to preserve |
| --- | ---: | --- |
| Sunmane Steppe | 384 m | Broad quiet grazing land, long horizons and shallow drainage. Caravan tracks follow the dry ground; wells, stock handling and camps give routes a purpose. Sparse lee vegetation and broken mineral ground lead toward Amethyst. Preserve the watch-cairn frontier as a frontier, without inventing an eastern road. |
| Verdant Stair | 360 m | Limestone terraces, spray-fed vegetation and sheltered jungle pockets. Build a connected ascent with open combat landings before placing the canopy. Working landings, physick activity and the moved-anchor story should explain the paths. Avoid uniform forest density and narrow corner-only connections. |
| Ssarathi Ruins | 384 m | Monumental ruin sequences, historical axes, broken aqueducts and sheltered courts. Water and shade determine vegetation. Preserve the lineage house, Royal Archive and Tenth Mouth roles; approach the monuments through readable courts rather than shrinking their scale. |
| Manymouth Delta | 360 m | Branching drainage and credible flood levels. Raised working hamlets, deliberate fields, bunds and causeways organize travel. Reeds and mud follow wet ground, while resources and crab encounters have usable dry approach space. Preserve the water-lineage stelae and flooded labyrinth. |

The shared toolkit establishes continuity and reproducibility, not a common
visual style. Every receiving side needs the same geometry, grounding and
gameplay-camera review as the newly authored region. A broad mountain collar
does not justify snow on a marsh road, and a successful flood-fill does not
justify an impractical detour or a vertical paved wedge.

Close views still show polygonal material edges, repeated textures, strong
facade shadows and some intrusive occluder fading. Static scenery can remain
continuous while NPCs and resources are still map-scoped. The measured live
handoff pauses above remain a limitation; settled debug survey FPS must not be
presented as a crossing-performance result.
