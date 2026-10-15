# Southern landscapes

Sunmane Steppe, Verdant Stair and Ssarathi Ruins complete the southern chain
between Amethyst Barrens and Four Gates. Empty travel is shorter; useful
architecture, door widths, working yards and combat landings keep their scale.

| Region | Playable extent | Landscape and daily life |
| --- | --- | --- |
| Sunmane Steppe | 384 × 384 m | Broad grazing ground and shallow drainage surround the full-sized caravan camp. Clan tents face shared yards, with stock pens, water points, a working shore and cave outcrops. The northern dusty track inherits mineral ground from Amethyst. The southern track approaches Verdant's high limestone country; the eastern frontier stays a frontier. |
| Verdant Stair | 360 × 360 m | Seven limestone levels rise from the quay through the physick neighbourhood, canopy and ritual terraces to the high pass. Six generous stair flights and useful landings make the ascent legible. Vegetation follows sheltered shelves and water; stair approaches retain sightlines. The Moved Anchor, temple procession, cenote and quarry keep their identities. |
| Ssarathi Ruins | 384 × 384 m | A low basin, connected water channels and inhabited quays sit below the full-sized temple. Formal historical axes survive among broken aqueducts, sheltered courts and jungle. Records and cargo work give the archive approach a purpose. The Water Gate, lineage records and Tenth Mouth remain part of the region. |

Local server origins are `(116,116)`, `(108,108)` and `(116,116)` respectively,
with one metre per server tile. Their safe arrivals are `(137,95)`, `(108,108)`
and `(116,116)`. A revision-guarded migration moves existing residents to their
own safe arrival once, retaining progress and leaving other regions alone.

## Five receiving approaches

| Connection | Shared geography |
| --- | --- |
| Amethyst south road ↔ Sunmane north track | Low mineral and grass shoulders meet along a dusty caravan road. Amethyst's ascent reaches the landing gradually; its geode mouth and linked entrance move clear of the third cart lane. |
| Four Gates east ↔ Sunmane west landing | A seven-metre causeway spans the lake channel and meets the steppe shore road. |
| Sunmane south track ↔ Verdant east pass | Open grass and dust give way to limestone upland, with the actual neighbouring approach visible ahead. |
| Verdant west quay ↔ Ssarathi east causeway | A stone crossing joins the quay and the ruin basin. |
| Four Gates south ↔ Ssarathi north stair | The southern avenue and grounded gate meet a causeway across a connected inlet. |

These bring surveyed scenery coverage to fourteen of seventeen exterior land
links. Seven ferries remain journeys. The three unsurveyed land links connect
Manymouth Delta to Grey Moors, Westhaven and Ssarathi.

The shared toolkit reserves 42 metres of approach and an 80-metre-wide receiving
strip. The client preloads nearby geometry and adopts the same scene at the
server handoff. Region-local frames carry the camera and traveller together.
The receiving view uses single authored terrain pieces and whole nearby props.
Those pieces are removed from the core, with shared membership where approaches
overlap; there are no duplicated border previews or extended stand-in surfaces.
The same nodes survive the handoff. Nearby imports start at 170 m and remain
resident until 220 m, with two neighbors and one background worker.

Clicking rendered neighboring ground retains the destination map and tile,
routes through the appropriate road, and resumes toward that exact point after
the server crossing. The destination marker now shows the clicked ground.
The continent atlas is 1800 × 1880 m, with narrow gaps, full wrapped labels and
graph-derived roads/causeways; dashed ferries preserve the sea journeys.

Road grading must not lift a lake plane into a dry pass. Only causeways receive
a surveyed water elevation; dry collars keep underlying water submerged. The
final collision guard reads real actor-centre floor triangles. It closes invalid
tiles instead of inventing floors or reopening a route through a structure.

## Reproduce the paired contracts

From the client checkout:

```powershell
python eloria-assets/tools/rebuild_southern_regions.py --server ../wt-south-server --data ../work-output/southern-rollout/eloria-data
```

The coordinator rebuilds the three new packages and receiving Amethyst/Four
Gates approaches. It also migrates the six earlier surveyed exteriors to the
shared approach pieces, preserving their established regional layouts. It then
applies guarded coordinate migrations, publishes exact
collision, synchronizes content and reciprocal doors, updates registry and
package digests, and regenerates the continent map. `--skip-build` uses reviewed
geometry. `--stage prepare`, `collision`, `content` or `publish` resumes a phase.
Regional agents own local sources; only this coordinator writes shared server
configuration.

Sunmane's two cave doors both enter the existing combined `sunmane_wind_caves`
map at their respective sections. The unused legacy Crystal Hollow map name
must not become a served destination. Source markers retain their identities,
while `runtimePopulation` records the actual authoritative roster. LOD markers
use the same identities and posts, sampled on their own exposed floors.

Daily harvest assignments follow the actual Sunmane and Verdant resource
plots without changing task indices or rewards. Gauntlet completion and bailout
returns follow their ordinary surveyed exterior return posts.

## Evidence and practical limits

The review entry point is
[`work-output/southern-rollout/index.html`](../../work-output/southern-rollout/index.html).
It links matched gameplay-camera captures, annotations, geometry-derived
minimaps, actual-client route reports, seam measurements and build provenance.
Static scenery surveys and authoritative route walks are identified separately.

Final verification covers 67 exact regional routes and 257 legs, with 201
grounded captures (maximum floor offset 0.0207 m). The full run supplies 63
complete routes; a successful four-route replay supplies the remainder. The
original failures remain available: two paths crossed automatic doorways,
one creature assertion used a species label instead of the served actor type,
and one statically clear Amethyst target appears to have been occupied.
The revised fixtures use real server storage collision and NPC blocking,
checking for unintended portal crossings after pathfinding.

All 88 surveyed-road handoffs and 20 actual clicks on neighboring ground pass.
Every measured handoff retains the Traveller and reuses the resident scene;
maximum camera movement is 0.151 m. Fourteen joins have no missing required
geometry rays, and resident surfaces match their active-map surfaces exactly.
The paired publication repeats all 345 recorded files byte for byte. Each of
the three new regional source builds also reproduces its geometry and collision.
Relevant checks pass: 66 server contracts, 70 client/toolkit contracts, the
regional source checks, and focused Godot streaming, lighting, cache and
material checks.

The develop integration retains its creature catalog cleanup, sigil shops,
HUD changes and larger invasion waves. All 668 natural spawn positions are
preserved; 136 entries adopt the retained species IDs. The current served
rosters and package digests are republished together. The coordinator also
regenerates invasion anchors on the final terrain while preserving all 1,776
wave identities, compositions and population ranges across 74 maps.
Integration validation passes 95 server map/content checks, 70 client/toolkit
checks and 106 invasion checks, plus Godot scene, atlas, HUD and material checks.
The merged build also passes all 20 neighboring-ground clicks and six complete
service/encounter routes (17 legs), with unchanged inputs during both runs.
The earlier complete route coverage describes the pre-integration inputs;
separate live integration reports are retained under the review's publish
directory and its adjacent `live-publish-*` / `live-regions-publish-*` folders.

The instrumented 1440 × 900 GL Compatibility run records a 162.512 ms median
handoff frame, a 264.941 ms p95 and a 529.405 ms maximum. Peak reported static
memory is 1067.9 MiB with at most two resident neighbors. These full frame
intervals include the instrumented client work; they are not isolated GPU
timings or evidence of stall-free movement.

The shared collision migration also corrects bounded older approaches:
Amberwood's stone ring, waystone and smuggler landing, plus Whitehorn's mine,
ice cave, temple joint, watch cave and snowline entrance. Their identities and
destinations remain intact. Matching captures and complete live round trips
are linked from the review.

The relevant checks include single-arrival access to all authored destinations,
the full forty-metre approach of all seventy new directed crossing lanes,
portal and content contracts, saved-resident migration, actor-centre grounding
and runtime scene/camera continuity. Checks must use final published packages.
An incomplete live route does not count as successful coverage.

This remains scenery streaming between authoritative server maps. Players,
enemies, resources, audio and dynamic lamps activate with the active map.
Cross-border combat and actor visibility need server interest management.
The minimap still adopts each active region's coordinate frame. A cold arrival
can take the synchronous fallback; preloading is not a guarantee of stall-free
rendering. Performance evidence uses an isolated QA traveller, not a crowded
multiplayer crossing.

## Remaining rollout

Finish Manymouth Delta as a roughly 360-metre floodplain, allowing more extent
only where river branches need meaningful separation. Raised hamlets, boat
yards and deliberate fields should sit above wet ground; reeds belong to mud
and shallow channels. Preserve distributary waterways and distinct crossings.
Rebuild its three receiving approaches together: wet moor pasture at Grey
Moors, the trading road at Westhaven, and the ruin causeway at Ssarathi.

Subsequent passes should deepen regional life without homogenizing landscapes:

| Region | Follow-up character to protect |
| --- | --- |
| Amberwood | Sheltered woodland villages, familiar cart roads, uneven forest edges and quiet clearings. |
| Whitehorn Range | Connected exposed ridges, sheltered pass stations, broad snow accumulation and sparse hardy growth. |
| Grey Moors | Peat drainage, burial ridges, open grazing and a warm refuge; keep the horizon low. |
| Mirrorhold | Useful civic terraces and a working lower basin; retain the Orrery and distinct northern cols. |
| Amethyst Barrens | Exposed crystal country around a sheltered assay community; group mineral formations and preserve bare ground. |
| Westhaven | Cargo streets, a climbing harbour town, pasture and salt-exposed shores. |
| Four Gates | Formal avenues, a convenient civic core and full-sized gate passages. Irregular shores should not erase deliberate civic order. |
| Crownwater | Separate inhabited islands, pearl-working shores and meaningful ferry journeys. |
| Sunmane Steppe | Long grazing views, caravan life and seasonal drainage; avoid filling the open plains with attractions. |
| Verdant Stair | Limestone shelves, spray-fed jungle pockets, ritual ascent and spacious stair landings. |
| Ssarathi Ruins | Historical axes and monumental silhouettes, with occupation concentrated on useful dry courts and quays. |
| Manymouth Delta | Branching floodwater, raised daily work and changing mud margins; retain readable channels and routes. |

Use the shared toolkit for reproducible terrain, grading and reciprocal frames.
Let each region determine the shape, material, planting and purpose of its
landscape. Every further batch needs matched captures, real door and road walks,
and a coordinated publication of client and server data.
