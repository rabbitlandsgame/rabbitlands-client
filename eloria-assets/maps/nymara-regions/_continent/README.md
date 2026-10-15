# Nymara: the diagonal mountain spine

The continent is authored in one coordinate system before any territory is
exported. X runs east, Z runs south, and sea level is Y = 0. Named territories
are server and content identities. Their boundaries do not determine the
height, water level, ground colour, or vegetation of the landscape.

**QA state: verified local rebuild (2026-09-27).** Source revision
`71e4a8884bc3d2004d3442dacebe5e604f77fa2e`, master `e3a139bd73ae2be28ba66a22600bbdc39d0ef22e6cc78c9a9ab7de45db12f066`, publication
`cf67f52a3465204c5b7ed6e105045f3624b7cad73b32c7ad5e3020f24d16e2fa`. The normal saved-scene bake, retained libraries,
composition, geometry, contracts, local publication and atlas chain was run on
these bytes. This integrates the twelve partial source visual passes and the
reviewed asset-binding, Sunmane road-approach and terrain-conforming road repairs;
it is not a claim that every region's larger redesign is complete.

Eight editable return controls now bind sixteen independent instance-definition
exits. Find them under `Gameplay/RuntimePoints/Returns`, with IDs
`runtime-instance-return-<region>`. Moving a marker updates its preferred exit
target, including a one-metre edit, subject to the unchanged five-metre settlement
limit and final standing, hub-access and no-portal-trigger checks. Existing keeper
and portal controls retain their separate identities. All sixteen exits settle at their
authored targets (0 m). Sunmane's final exit is 6.083 m from its previously served
position; that historical displacement is separate from the authored-target budget.

Final evidence: 2,153 placements with
0 failures, 10,593 runtime crossing rows: 10,587 walking directions and six ferry directions, fast audit passed with zero errors and 315 roads / 21,816 stations checked, package digests
0 changed / 0 missing,
and static walk preparation passed for all 65 family maps, sixteen instance exits and 1,557 outdoor content objects. Border coverage is
verified for published lanes; the 39 coarse unmatched samples (78 directions) are explained by 66 directions unreachable under actual terminal-aware transport and twelve rejected by the exact original landing rule, with zero unresolved sampled directions. This does not claim exhaustive coverage of unsampled unpublished cells; Crownwater's shore links
retain their explicit ferry rules. The 42 authored marker identities/positions
and twelve coordinate frames are preserved; published trigger tiles follow the
verified runtime rows. Actual ELM/source-fold identity is exact across all twelve regions, including the sixteen actual served instance exits.

The three changed source suites recorded **141 passed, 32 subtests passed, and
one pre-existing failure**: `test_saved_runtime_edits_reach_normal_placement_with_distinct_endpoint_offsets`
cannot load the absent historical
`godot-client/test-artifacts/sunmane-edit-regression/before/continent-authoring.json`.
The changed static-validator suite passed **39 tests and 19 subtests**. Its separate
validation-only commit is `8619f417bbf3a65853d2197ebf149d124a5ca1b3`; it did not alter
the certified build inputs.

Terrain-conforming roads materially increase geometry cost. The measured master
is **974,735,468 bytes**, with **2,218,227 additional
visible faces** relative to the preserved geometry before the terrain-conforming
road repair. This is a size/count observation, not an FPS or live performance result.

All testing and data generation were local. No remote game-server session,
live deployment, live walk or database migration was run. Ownership selection and
coordinate capability remain inactive. Changed terrain revisions mean the existing
startup migration will reseat residents in all twelve maps when this content is
loaded; that migration policy is unchanged and was not run against a live database.
Develop publication is recorded by the final paired Git commits
`c9df9afcf88c1bc877581956017fa01ca9a520f6` and the client commit containing this notice. Any later
shaping/export change requires fresh normal certificates and validation.

**Historical QA state: published as the nineteenth publication (2026-09-18) and verified
for what it changed.** Master `461ba604cb050a275cd4275898ad5451429c060567c108626964e6d3640f1073` (the
seventeenth's: no geometry changed), publication
`ae6d195f86189f66be90fea5a0148be0cfae1c1876e6e48f617ffa258b4f1ac7`. It opens the four
borders no road crosses - Grey Moors and Four Gates, Whitehorn and Mirrorhold,
Manymouth and Ssarathi, Four Gates and Verdant Stair - wherever their ground meets
(`crossings.open_borders`; Crownwater's three shore borders stay ferry crossings), and
takes the hub out of the lane rule: a lane is ground walkable on both sides of its border
with a legal step between, kept where a walker from some map's hub can get onto it and
step off where it lands (`crossings.settle_crossings`, which withdrew 182 lanes on
unreachable scraps and one-tile dead ends). The publication has 10,163 lane directions
where the eighteenth had 8,136. On these bytes
the strict contracts passed with 0 failures, the audit passed and verified the
publication, and the live fixture audit proved all 10,163 lanes offline by the server's
own walking rules with 0 errors; the continent, crossing-related server and client
tests passed. The live suites on a real server and client were not run for this
publication, at the owner's request. Known limitations are listed in
`STATUS-2026-09-13-takeover.md`: roads are not yet walkable (the walkable-roads round);
the reach links leave wall steps over the 4 m smoothing limit where the Moors pass
switchback's legs are stacked on the Whitehorn face; the Grey Moors undercut mouth is
served at the foot of its slope; and the Four Gates north and south gates still have no
roads of their own - the ground in front of them offers no seam station both hubs can
reach (the north gate faces a gully that needs an access deck), recorded in
`door_approaches.py`. Any later change to a shaping or export source returns this
notice to provisional until the same chain is repeated.

**QA follow-up (2026-09-19; the nineteenth publication is unchanged).** The offline
proof now emits one roadless crossing walk in each direction for all four roadless pairs,
plus one neighbour-terrain, one Tab-map and one minimap click for the same audited target:
8 walks and 24 clicks in total. Its audit is ready with 10,163/10,163 lanes and 0 errors.
The focused Python generator suite passed 33 tests with no skips; the focused roadless-map
headless suite passed 19 checks with 0 failures; and the border-crossing and exterior-walk
continuation headless suites passed. The world-input suite still has two unrelated failures
for imported material texture filtering and mip chains. No live suite, full server suite or
build chain was run, and this follow-up changed no geometry, publication or server data.
Evidence is retained in `../../../../../after/roadless-fixtures-tests-20260919-190518.log`,
`../../../../../after/roadless-prepare-20260919-191643.log`,
`../../../../../after/headless-roadless-map-clicks-agent-20260919-r2.log`, and
`../../../../../after/roadless-fixture-validation-20260919.json`.

The coarse `border_audit.py` midpoint diagnostic was rerun on the unchanged server inputs
and did not reproduce the earlier blanket `both == crossed` claim: several non-Crownwater
rows differ, including Whitehorn-Mirrorhold at 48/47. Its `both` count checks only nonzero
floor bytes at two segment-midpoint samples, while `crossed` checks exact served portal-tile
membership; it does not apply actual step-height, collar, reachability, landing or lane-
pruning rules. This is recorded as an unresolved diagnostic discrepancy, not evidence that
each unmatched sample is a legal missing lane. See
`../../../../../STATUS-2026-09-19-roadless-fixtures.md`
and `../../../../../after/roadless-border-audit-20260919-191929.log`.

**MC007 + MC008 QA candidate (2026-09-21; approved for publication).** The
corrected clean normal build preserves all 313 composed road polylines and all
10 non-Mirrorhold region GLBs byte-for-byte against `8134002f`. Mirrorhold's
encoded terrain changes only at the 10 reviewed City-turnout vertices (maximum
cut `1.6841355 m`, no fill); its other encoded changes are the reviewed City
and Sanctuary Drowned Crown arm geometry. Normal publication, targeted access,
collision, offline movement, and visual checks passed. The orchestrator approved
the reviewed source and generated allowlists for publication under the user's
authorization; owner deployment and live confirmation remain pending. See
`QA-MC007-MC008-2026-09-21.md`.

**MC005 QA candidate (2026-09-21; validated isolated build).** The
Mirrorhold cliff-house source keeps every existing house and railing triangle
and adds one closed timber sill beneath each of the 27 decorative railings.
The sill is decorative and is not a walk surface. The normal isolated build
preserves all 313 composed roads, terrain and grounding arrays, placements,
the Mirrorhold transform, and collision data. See
`QA-MC005-2026-09-21.md` for the exact candidate identity, emitted proof,
known baseline limitations, and review evidence. Owner deployment and live
confirmation remain pending.

`diagonal-plan.json` describes the coast, connected mountain chain, river
catchments, islands, territory centres, and placement controls. `landscape.py`
evaluates the common height and climate fields. No territory border enters
those functions. `world_layout.py` samples the surface at two metres, fits
settlement footings, and finds roads through manageable ground. `content.py`
places retained architecture and discoveries, then scatters woodland and
related rock formations using moisture, slope, road, and exposure fields.

The northern high country feeds the wet western basin. Amberwood occupies
the sheltered slopes below the snowline; Grey Moors occupies the wetter
western uplands. Mirrorhold controls a pass through the spine. Amethyst and
Sunmane share its dry eastern side, with gradual grassland and dry-soil
transitions. The mountain chain diminishes into the southern limestone
uplands, while the western rivers divide into the Manymouth estuary and
Crownwater islands. Rivers reach the sea through actual low ground.

The eastern coast has dry grassland and coastal downs between the mineral lee
and the sea. Northern snow, upland heath, and sheltered woodland overlap by
height and exposure rather than changing at a territory edge. Mirror Lake is
an inland water body with its own surveyed level and an outlet into the western
watershed. Its harbour follows that lake datum; coastal harbours follow sea
level. The upper rivers have low flood shelves before their broader valley
shoulders rise. Later road and foundation grading restores a ten-metre natural
bank apron, feathering to 42 metres, with a smooth 32-metre exclusion around
real hard footings. Retained support conflicts are reported for visual and
collision review; this protection is not proof that every bank is finished.

This is designed fantasy geography, not a geological or hydrological
simulation. Ridges, drainage, and settlement approaches are editable design
controls. Coherent broad shapes take priority over uniform terrain noise.

## Authored sources and exports

Use these source responsibilities when changing the world:

| Source | Authority |
| --- | --- |
| `diagonal-plan.json`, `landscape.py` | Shared coast, mountain spine, drainage, natural ground, climate and biome materials. |
| Regional `build_*.py` recipes and shared toolkit | Original reusable architecture, authored object names, linked content and foundation surveys. |
| `build_library.py` | Certified reconstruction of retained assets from those recipes, with trusted intermediate caches. |
| `assemblies.py`, `content.py` | Connected structure grouping, common transforms, actual footing categories, mapped content and ecological placement. |
| `crown_support.py`, `westhaven_support.py`, `manymouth_support.py`, `mirror_support.py` | Local island, harbour, landing and bank support fitted to retained structures. |
| `mirror_streets.py`, `four_gates_support.py` | Civic circulation, actual building footings and the graded east-gate approach; an exterior branch that starts on a civic street is trimmed where it first leaves the street network (a later touch keeps the descent and the bridge between). |
| `mirror_access_geometry.py` | Low stone bank ramps and the physical opening onto the sanctuary walkway. |
| `access_decks.py` | The plan's `access_decks`: short named walking decks (a polyline with a height per point and a width, every segment at .45 or less) where two walk surfaces stop short of each other over water or a hole, built in the geometry stage and refused unless `designed_decks` names them under this module (the Lamp Rock causeway link). |
| `mirror_lake_support.py`, `ssarathi_bank_support.py` | Containing lake shores and natural river banks fitted around retained walking floors. |
| `manymouth_boats.py` | Actual hull contact with water or ground for independent decorative dugouts. |
| `hull_settle.py` | Every other decorative watercraft, standalone or inside a rigid assembly, settled by rigid Y only onto the actual water surface or hauled up on the ground, with rigs and cargo standing within a hull following it. |
| `resource_trails.py` | A narrow trail from the nearest road station to every cluster of authored harvest nodes and territory markers that stands on ground steeper than the walkable grade with no road corridor within 12 m, so the served fold keeps a walkable corridor at each site. |
| `amberwood_support.py`, `amberwood_access.py` | Woodland workyard paths, coherent camp layout and visible canopy/root entrance construction; the market stair and the root ramp onto the Great Tree's root plateau, both built on the final ground with their strips reserved before routing; the ridge camp's discovery branch is graded as an approach (one earth surface at .45 from a bounded-grade profile of its own stations), because the shared road solve holds the camp's footing feather. |
| `manymouth_access.py` | Visible tidal fishing boardwalks linking retained porches and the landing. |
| `manymouth_village_streets.py` | Graded timber streets connecting the other delta hamlets to their actual porch floors. |
| `grey_crossings.py` | Retirement of the three duplicate Grey Moors boardwalk spans, the four pinned server positions they anchored, and their landmark identities on the actual continental crossing floors. |
| `four_gates_sage.py` | The six Four Gates tutorial Sage records pinned 48 tiles from the arrival beside the plaza approach, keeping their surveyed layout. |
| `object_edits.py`, `continent-edits.json` | Authored object edits from the continent plan editor: retained placements removed before grouping, rotated/scaled on their source roots and moved on their shift before footings and routing; copies cloned into their own territory's document with their own footing and collision identity; vegetation areas that clear or thin ecological scatter without renumbering anything outside them. `python object_edits.py --library <library>` checks the file before composing. |
| `door_approaches.py` | Authored road ends for doors inside retained pavilions (the Shrine of the Nine Lost on the South Quay), shared by the server-declared discovery branch to the same door, so the road meets the pavilion's open side and no deck is built onto its threshold. Every authored road end, server road end and seam or door waypoint is checked dry and outside the river setback before routing (`validate_river_setbacks`). |
| `river_crossings.py` | River crossing sites: every plan river cut in cross sections, the locally shortest square reaches with dry landings offered as candidates and claimed by the roads that cross them, at least 100 m apart along a river; river setbacks, dry road ends and branch starts (see "Roads and rivers"). |
| `reach_links.py` | The plan's `reach_links`: authored ground (the terrain edit shapes and ops) written onto the finished composition after the roads and the support stages, so served ground the arrival cannot reach is joined to it and nothing grades the link again; never on a river centreline or a rigid compound (see "Reach links"). |
| `authored_points.py` | The plan's `authored_points`: a server record (a secret door, its return, its interactive) pinned by its authored tile to open ground beside an entrance no served ground reaches, as `four_gates_sage.py` pins the Sage; the placer still resolves standing ground within the record's budget, and door roads route to the pin. |
| `winding.py` | Library triangles wound against their own vertex normals, reversed per sheet in a private copy of each library document as `content.load` reads it, before any bounds, grouping, turn or edit (see "Inverted winding in retained library meshes"). |
| `crossing_contracts.py` | Contracts-stage declaration of each continental bridge floor's two standing points from the served collision fold, with every floor's walkable parts reported; each declaration names the crossing site its floor serves. |
| `ferry_export.py`, `ferry_support.py` | Actual quay/boat fit and preservation of its complete shoreline footprint through road grading. |
| `world_layout.py` | Ownership polygons, server address envelopes, road alignment (retained solids impassable, river water and its setback impassable except on a crossing site's bridge edge, hubs and terminals joined to dry open ground, gentle traverses preferred, the station terrain terms per territory, legs rerouted round earthworks beyond the limits), common road grading with cut and fill limited outside footings, foundation reconciliation and drainage protection. |
| `bridge_export.py` | One union of visible continental bridge decks: each claimed crossing site's span with landings of at most 6 m (named by its site), decks over deep sea water away from any site, piers only where they stand in water; fitted to the common road surface and actual banks, an unfittable bank reported rather than grown. |
| `bridge_prepare.py` | Final shaping coordinator that applies only the bounded coastal road edits required by the explicit release selection, fits claimed river terrain, inventories the resulting loose coastal water, and prepares those selected coastal claims before road-height refresh and content regrounding. |
| `coastal_prepare.py`, `sea_crossings.py`, `coastal_bank_fit.py`, `coastal_bridge_export.py` | Stable-road and exact live-cell coastal claims. This incremental release prepares only component 502 (`discovery-manymouth_delta-1003`); component 501 and every other loose crossing remain gated to the legacy floor path. Selected claims export and query their same encoded floor and support triangles, and stale, duplicate, overlapping or out-of-authority selected partitions fail before export. |
| `terrain_export.py` | Shared terrain faces and physically clipped shorelines, partitioned from the complete world surface. |
| `build_continent.py`, `scene_io.py` | Global composition (seam roads route with the hub's own solids only, so a terminal beside a city wall threads the gate), master scene, named packages, independent loading cells and shared image dependencies. |
| `crossings.py`, `export_contracts.py` | Reciprocal crossing lanes and authoritative standing positions derived from actual exported walking surfaces. |
| `../../../tools/publish_diagonal_continent.py` | Coordinated client/server publication, remaps, package digests and save-migration data. |
| `atlas_export.py` | Actual-master overview, matching territory crops and Tab-map publication. |

Edit the responsible authored sources and rebuild their dependent stages.
Generated GLBs, collision files, manifests, ELMs and atlas crops are outputs.
The frozen legacy geography/profile is a coordinate reference, not the new
continent's layout or a second copy of visible terrain.

`build_library.py` rebuilds reusable architecture from the original regional
sources and shared toolkit. Frozen `legacy-geography.json` and
`legacy-contracts.json` supply the old composition's foundation reference.
The library's old terrain is sampled for placement offsets and never drawn
in the new world. Source and output hashes certify each reusable library.

`build_continent.py` assembles a complete global scene and writes
`generated/continent.glb`. It exports the same scene into named ownership
polygons and 96-metre streaming cells. Terrain faces and bridge decks are
cut at ownership boundaries; buildings stay whole and are assigned once.
All chunk geometry remains in its territory's local coordinate system.
The complete GLB is a reproducible review artifact, not a runtime load.
`generated/shared-terrain.glb` is the reproducible geometry intermediate used by continent audit
and freshness checks, not a runtime region or chunk asset. A normal build regenerates it locally
before the audit; it is ignored by Git because the complete twelve-region terrain and Walk surface
exceeds the ordinary Git object limit.

The twelve named territories retain their identities and content contracts.
Their irregular ownership shapes are independent of the 96-metre loading
grid. A building assigned by its bounds centre can extend beyond that cell;
its manifest records its actual bounds so it can load before becoming visible.
Do not clip a connected building to the loading grid or duplicate it into
neighbouring cells. Chunk count is an export result, not a fixed contract.

Runtime assets are each territory's `world.json`, `world.glb`, `collision.bin`,
and `chunks/<x>_<z>/world.glb` plus its manifest. Shared PNGs are stored by
SHA256 under `shared-assets/`. Chunk manifests declare their image dependencies
and separate geometry memory from image memory; the client counts identical
images once per territory and pools their GPU textures.

Chunk manifests carry no `minimap` block. The map picture belongs to the
territory: its own `minimap` block frames the HUD minimap and the Tab map,
and its `minimap.webp` is the picture `godot-client/data/maps/cartography.json`
names. `export_geometry` still deep-copies the territory block into each
chunk, naming a `chunks/<x>_<z>/minimap.webp` that no stage writes, and the
client packager refuses a manifest that names a missing file. The published
chunk manifests were stripped as data, because `build_continent.py` is pinned
by `cartography/continent-atlas.json` and `generated/export.json`: at the next
geometry export, add `'minimap'` to the keys `export_geometry` pops from each
chunk copy. Until then `StageCommittedMaps` in
`godot-client/tests/test_package_vram.py` fails when an export brings the
block back. Do not commit pictures beside the chunks instead.

`continent_chunk_stream.gd` loads independent cells around the real focus;
current manifests request 240 metres of preload and retain to 320 metres,
subject to 64 cells and an estimated 256 MiB resident budget per territory
stream. Those estimates include geometry and shared resources; they are not
measured process or GPU memory. Actual loading, retirement, adjacent-territory
adoption and cold arrivals require client proof. Named manifests declare
`geometryMode: continent-chunks-v1`; old regional rebuild entrypoints must not
replace these packages with standalone legacy terrain.

The addressable server envelope remains square because the existing ELM
format uses square map cells. Rendered and walkable territory ownership is
nonrectangular. An envelope can include sea or another territory's bounding
box without granting movement there. Compact retained settlements and their
surroundings occupy only part of these envelopes; open hills, rivers and sea
provide the geographic transitions between them.

`crossings.py` surveys the seven metre-cell lanes of each road crossing's
gate and every other tile of the border a walker can cross on. A lane is the
neighbour's first tile across the border, stepped onto from this territory's
own ground; it exists wherever both served grids let an actor stand there and
both hubs can reach it (a seam named in `GATED_SEAMS` keeps only its gate).
The crossing hands the walker over at that same cell, read in the other map's
tile frame - every territory's tiles are one metre grid in the shared frame -
so an arrival shares its departure's global cell centre, and no departure is
owned by the map it departs from, which keeps every arrival clear of the
crossing back. The collision export opens that first strip of the
neighbour's ground along the whole border (`collision_export.seam_collar`)
without letting it stretch the territory's height scale. Short invisible
threshold floors still carry the gate's own lanes across the ownership
boundary; they do not duplicate visible terrain. The published survey ships
each end's crossings as runs, so a client aims a walk at the crossing on its
way. Shared boundaries without a road are declared as visual adjacencies
without adding travel portals.

Island connections without a continuous road remain explicit ferries. Their
fixtures require the exact authoritative receiving tile and its global metre
coordinate at the tile centre. A visible neighbouring shore does not imply
that water can be crossed on foot. Cross-territory click targets must be
verified through the real client and server, including resumed movement.

## Connected settlements and approaches

Architecture that shares a floor, quay, courtyard, stair or bridge uses one
coordinated assembly transform. Linked doors and metadata use that transform
as well. Do not reground separate roof, wall, deck or fountain meshes to
independent terrain samples. Actual footing cores retain support, while
suspended canopy platforms and walkways do not manufacture ground underneath
themselves. Foliage is not a foundation constraint.

Mirrorhold's fortress, streets, lake harbour and associated content share its
city survey and lake datum. Four Gates keeps its civic complex coherent;
Manymouth keeps connected boardwalks and temple/hamlet groups while allowing
water beneath raised floors. These local supports must blend back into the
common watershed without making former rectangular map bases.

Manymouth's local timber streets meet actual retained porch heights and avoid
house bodies. Paddy, fishing, town and outlying hamlets keep separate street
networks rather than sharing a flat platform. The Temple quay bank interpolates
between its real floor aprons and blends into the higher eastern hamlet.
Source tests cover exported diagonal precision, bounded street grades and
floor contacts; the final named geometry must also pass the complete 99-floor
standing and connectivity audit. Independent dugout boats use full hull
contact with water or land, while ferry boats keep their surveyed moorings.

Crownwater's causeway city uses **17 named islands** matched to its retained
source survey. `crown_support.py` limits that survey to island shelves, fits
bridgeheads, repairs two specified stale causeway profiles as whole bridges,
and reserves crossing corridors against ferry placement. The surrounding sea
remains shared continental geography. Westhaven separates its working harbour
and lighthouse into coherent maritime assemblies: quays, yards, warehouses,
boats and associated doors keep their common relationships. Irregular local
support envelopes fit the shore, and actual submerged hull geometry determines
berth clearance. Verify both harbours from water and from their street
approaches after changing these supports.

Ferry selection tests ranked coastal sites against a complete quay and moored
boat footprint. Existing working quays and causeways are excluded; selected
landings remain at least 20 metres apart so automatic destination triggers
are distinct. Trial terrain/contact edits are rolled back before selection.
The selected fit preserves the terrain vertices beneath the complete quay and
boat, including a full terrain-triangle margin. Road grading approaches this
shoreline constraint. Composition checks all final quay and mooring fits again
before caching the world; an earlier successful candidate is insufficient.

Grey Moors retires exactly three surveyed boardwalk spans (gate, centre and
south) whose retained floors duplicated the continental bridge union at the
headwater outlet and the southern pool. The other spans, both causeway
bridges and the boardwalk cache discovery remain. Four server records that
had used those spans as nearest deformation anchors keep their expected
global positions through explicit authored points, and the three generic
`Grey Moor Crossing` landmark identities are re-associated at export with the
actual emitted crossing floors. The Moor pools and their banks are not
reshaped by this correction.

Mirrorhold's lake-path correction uses the exposed upper walking surface.
Lower sleepers and structural supports do not justify excavating terrain.
Only the inherited local bank overlap is lowered, with a short shoulder;
the lake bed, levels and connected city geometry remain intact.

Visible interior doors receive narrow approach routes. Composition also reads
the frozen authoritative `maps.txt` portal entries and exterior returns,
including hidden rooms absent from client portal markers. Mapped destinations
receive branch trails with a 1.65-metre half-width from an existing public road. Nearby duplicate
destinations share a branch. These are authored discoveries with accessible
approaches; collision export must not conceal a disconnected entrance by
carving an invisible corridor or moving it away from its building. The entrance
profile hash is part of composition freshness.

## Roads and rivers

The road rules since the R1 pass (2026-09-16): a road crosses a river only on a bridge at a locally shortest,
square reach; several bridges may cross one river when they stand at least 100 m apart along it; a road that
travels in a river's direction keeps to its bank outside a setback; roads do not float; earthworks outside
footings are limited and written into the ground. The plan key `crossing_policy` holds the numbers
(`landscape.CROSSING_POLICY_DEFAULTS`, validated against `CROSSING_POLICY_LIMITS`).

**Crossing sites** (`river_crossings.py`). Every plan river is cut every 2 m along its curved centreline. A
section costs its wet width plus an approach term (the bank rise a .35 grade cannot absorb over a 12 m landing).
Sections are excluded over lakes and the sea, within 20 m of another channel (confluences), across the rigid
core of a settlement footing or a retained solid, within 12 m of a territory seam, whose own line lies in two
territories or none, more than 15 degrees off square to the flow, with a landing that is not dry ground above
the sea, or where a deck would stand more than 0.3 m over its banks. A section within a quarter metre of the
cheapest valid section within 40 m along its river is a candidate (thinned to one every 20 m). A candidate whose
approach exceeds 6 m is a last resort, offered only to a leg that finds no other crossing. The plan key
`authored_crossings` names a section (a river id and metres along it) that is a candidate although the model
excludes it, when its only reasons are a deck that cannot sit at water level between high banks, a retained
solid beside a landing, or standing nearer a territory seam than the policy prefers
(`landscape.AUTHORED_CROSSING_WAIVERS`). A span in two territories is never waived: each territory exports its
own geometry, so such a deck would be built in halves. An authored crossing also keeps its place whatever the
minimum spacing says, and the audit judges the local-shortest and spacing rules only on the sites the model
chose for itself: the plan names three, the Mirrorwater ravine below Mirror Lake that the Verdant Stair seam road
crosses as design O5 did, and the Amberwater and Mirrorwater in front of the Four Gates north and south gates.

**Routing.** River water is impassable to the router. Every claimed site in the leg's territory, and every
candidate there standing at least 100 m along its river from each claimed site, adds one bridge edge between its
two routed landings (9 m beyond the wet edges), costing 60 m of alignment on top of its length; a site a public
road (seam, ferry or door road) already crosses costs a quarter of that. A routed road claims the sites it
crosses. A road of half width w keeps max(6 m, w + 4 m) from river water and pays a soft penalty over a 16 m
bank shelf beyond that. Seam terminals, door pins, server road ends, discovery branch starts and ends and trail
starts stand on dry land outside the setback; a branch starts on its destination's bank and never on a bridge.
A seam road that cannot be routed through its chosen station tries up to ten alternatives spread along the
seam. `composition.json` reports `riverCrossings` (sites, claims, last-resort claims, unrouted legs),
`movedSeamCrossings` and `dryRoadEnds`.

**Earthworks.** Outside footings (the rigid core of an assembly footing, and Mirrorhold's released civic
ground) a road's profile cuts at most 4 m and fills at most 3 m, and the solved corridor written into the
ground obeys the same limits (`graded_profile`, `limit_corridor_earthworks`). A leg whose ground no .45 grade
can carry within the limits is rerouted up to three times with a penalty on the offending stations; what
remains is reported under `earthworks.legsStillExceeding` and needs authored switchback waypoints
(`SEAM_ROAD_WAYPOINTS`, `DOOR_ROAD_WAYPOINTS`).

**Bridge decks** (`bridge_export.py`). A deck is a claimed site's span with landings of at most 6 m, lifted at
most 0.3 m over dry ground; lifted landing cells are trimmed rather than raised, and piers stand only in
water. The retired plan keys `bridge_approach_aprons` and `bridge_approach_connections` are refused. The
union floor `Walk_ContinentalBridgeUnion_<n>` names its site (`n` is the site id plus one; decks over deep sea
water away from any site number from 500), one node per territory even when a site's deck falls into disconnected
pieces, and `crossing_contracts.py` records that site with each declared crossing.

**Geometry consumers of the roads.** A Manymouth village street with no retained public contact starts
from the nearest public road within 36 m, else within 64 m (`manymouth_village_streets.public_road_station`);
the Grey Moors boardwalk identities retired onto the continental crossing floors associate with the nearest
emitted Grey Moors floor within 64 m (`grey_crossings.MAXIMUM_ASSOCIATION_METRES`).

**Designed decks.** Every other elevated walk is a named designed deck in the plan key `designed_decks`
(an exact name or a trailing-`*` prefix, the module that builds it, a note): the Amberwood market stair, root
ramp and root hatch, the Manymouth boardwalks and village streets, the Mirrorhold bank ramps, the ferry quays
and the Grey Moors boardwalks. A building module refuses a deck the plan does not name under that module.

**Audit.** `audit_continent.py` checks the rules on `generated/roads.json` (stations, widths and crossing
sites), the emitted terrain and `river-bridges.glb`: no road station over river water outside a site's span,
no wet run crossing under 70 degrees, each site within 4 m of the locally shortest buildable crossing and at
least the spacing from its river's other sites (sections within the policy's seam distance of a territory seam are no
comparison), no pier over 8 m outside designed decks, and no road station more than 1.5 m over its ground outside
site spans and designed decks. Sea spans and their landings are
reported, not judged by the river rules.

Compounds from the retained asset audit (`experiments/asset-audit/REPORT.md`, 2026-09-16), all in
`assemblies.py`:

- **Natural companions.** `content.load` keeps a natural placement only as a landmark or a compound member,
  so a landmark built with rocks at its flanks lost them. A natural placement named
  `<structure node>_<word>_<n>` for a word of `COMPANION_WORDS` (`EarthRock`: the four Sunmane cave mouths)
  and the pairs of `COMPANION_PAIRS` (the Amethyst Northern Grotto arch with its abutment stones and the geode
  cave it spans; not the Amberwood sea arch, which stood further from its legacy ground as a compound) form the
  compound `<territory>.<structure node>` with their structure (or join the compound the structure already
  belongs to). The structure and each companion carry the legacy slope they stood on as footprints, and the
  companions stay scatter prototypes too (the EarthRocks are Sunmane's only rocks).
- **Pulled sites.** A single outside its territory, or on wet ground, is pulled 10 % of the way to the hub per
  step on its own, so the pieces of one legacy site converged. `PULLED_SITES` makes such sites compounds that
  move as one body at their legacy spacing: Amberwood's east quarry (its lodges, towers and dressing; placed by
  `assembly_sites.amberwood.east-quarry.center` because its whole pull would land it on the garden), Verdant
  Stair's temple summit and Amethyst's upland geode cave with its crystal field. Sunmane's palisade gates join
  the encampment and Westhaven's chandlery stock and working loads join the harbour
  (`westhaven_support.HARBOUR_PREFIXES`). A pulled site steps 2 % of the way per step (`SITE_PULL`), and the
  geode site also waits for every member centre to stand on dry ground; every other compound keeps its 8 %.
  Every member of a pulled site but those in water or in the air (`site_supports_ground`) keeps its legacy
  ground as a footprint, props included: moved onto other ground, a prop without one floats or sinks.
- **Footprint datum.** `REFERENCE` datum `'footprints'` stands a compound at the median, over a 2 m grid on
  every member's bounds, of the continent ground less the legacy ground (`Assembly.footprint_lift`), instead
  of the ground at its reference point. The pulled sites use it. The canopy village does not: the lift it
  would get (11.5 m on the O5 plan) raises the market stair's deck beyond the stair's 45 m run.
- **Member offsets.** The plan's `assembly_member_offsets` (`{"<assembly id>": {"<member node>": [dx, dy,
  dz]}}`, metres of the legacy source frame) moves one member's placement root before any bounds, turn or
  grouping (`content.apply_member_offsets`), since object edits refuse compound members. Unknown ids,
  non-members, trees and malformed vectors are refused. It seats the Mirrorhold cistern-yard and quarry-shelf
  bollards on their survey ground.

## Rebuild

Use Python with NumPy, SciPy, and Pillow, the shared toolkit's native raster
library, and the paired server dependencies. Godot is required for client
tests and visual proof. The pipeline enforces a common processor affinity
of at most eight logical cores and one numerical-library worker per process.
Two library processes may run concurrently within that same CPU allocation.
The eight-core limit is shared by concurrent work, not eight additional cores
per process. Launch independent diagnostics through the same affinity-limited
task wrapper; do not start uncapped build or numerical workers alongside it.

From the client checkout:

```powershell
python eloria-assets/maps/nymara-regions/_continent/build_pipeline.py --server C:/path/to/server --data C:/path/to/generated-data --artifacts C:/path/to/review-output --cores 8
```

Stages are `libraries`, `compose`, `geometry`, `contracts`, `publish`, `atlas`,
and `verify`. Use `--stage` to run one stage and `--library` to reuse an existing
certified cache. `compose` must run again after landscape, placement, or road
sources change. Export-only fixes can reuse its checked composition cache.
Generated caches are trusted local build artifacts, never interchange files.

With no `--stage`, this command runs the entire sequence, including publication
to the supplied paired server and client packages. Use individual stages for
provisional geometry review. Composition freshness checks the plan, all
shaping modules (`landscape`, `world_layout`, `content`, `assemblies`,
`crown_support`, `westhaven_support`, `ferry_export`, `ferry_support`,
`mirror_support`, `manymouth_support`, `mirror_streets`, `four_gates_support`,
`amberwood_support`, `amberwood_access`, `mirror_lake_support`,
`ssarathi_bank_support`, `manymouth_boats`, `terrain_export`, `scene_io`,
`grey_crossings`, `four_gates_sage`, `door_approaches`, `hull_settle`, `resource_trails`, `object_edits`,
`winding`, `river_crossings`, `reach_links`, `authored_points`, `bridge_export`, `bridge_prepare`,
`coastal_prepare`, `coastal_bridge_export`, `bridge_profiles`, `sea_crossings`, `coastal_bank_fit`,
and `../_northern/requirements.txt`),
the object edits file `continent-edits.json` (absent means no edits),
the composition algorithm, the authoritative
entrance profile, the actual Shapely/GEOS runtime versions, and each retained library certificate. A changed source must
be recomposed rather than accepted by editing a certificate.

Geometry export independently records `geometrySources` in `export.json` for
`build_continent.py`, `scene_io.py`, `terrain_export.py`, `bridge_export.py`, `bridge_profiles.py`,
`sea_crossings.py`, `coastal_prepare.py`, `coastal_bridge_export.py`, `coastal_bank_fit.py`,
`../_northern/requirements.txt`,
`ferry_export.py`, `crossings.py`, `amberwood_access.py`, `manymouth_access.py`,
`manymouth_village_streets.py`, `collision_export.py`, `mirror_access_geometry.py`,
`grey_crossings.py` and `access_decks.py`, and checks that none changed during the
build. It also records the actual Shapely and GEOS runtime versions without
requiring one platform-specific GEOS patch release. The audit requires these current export hashes as well as the
composition certificates. Bridge export participates in claimed-deck terrain
grading and requires composition. Ferry code also participates in landing selection and requires composition.
Terrain export and scene decoding participate in actual boat flotation and
ground contact, so changes to either also require fresh composition.
Village streets use the collision module's actual triangle slope and water
sampling, so that module is also a geometry export dependency.
The contract stage checks the exact composition, master and named GLB hashes
before reading terrain, so a newer landform cannot be paired with an older mesh.

The contract stage uses actual upward walking surfaces, half-metre collision
samples, structural intersections, and the server's height-stage rules. It
samples the same clipped shoreline and continuous hydraulic plane as the
visible water mesh, including elevated riverbank corners. Its raster cache
includes those surface sources and water-domain controls. It requires
arrivals, doors, services, resources, encounters, and all road lanes
to connect to the inhabited arrival. A failed contract produces a diagnostic;
it does not carve invisible routes through cliffs or move a doorway far from
its building.

`legacy-server-profile/` preserves the original coordinate authority.
Content rows added after that freeze are listed in
`runtime-content-amendments.json` (`runtime_content_amendment.py`). Each block
is appended after the last line of its frozen content file, so frozen rows keep
their lines and identities and the new rows take the next lines and ordinals.
Contract export places and binds them like frozen rows (each needs a saved
runtime marker, in the region's seed and counts), the profile check rebuilds
them, and publication rewrites them by the same identity.
`python runtime_content_amendment.py --server <server> [--check]` writes (or
checks) the blocks in a server's served files, at the tiles the last certified
publication gives them. Sunmane's herds (`sunmane-herds-v1`: wild golden plains
horses and `tame` camp horses) are the first block.
`publication-history/` records exact prior remaps so a revised build can move
from currently served coordinates without deforming them twice. Interior-local
coordinates remain local; exterior return positions follow the new landscape.
Each territory's `terrainRevision` is `diagonal-spine-v1:<sha256>` derived from
its emitted GLB, collision bytes and height encoding, folded server grid,
address origin/dimensions, continent translation, safe arrival and mapped
content positions. The release label alone is insufficient after another
terrain edit. Identical exports keep the same revision, including after a
first publication; bookkeeping-only baseline changes do not alter it. Named
and chunk manifests receive the same territory revision. Runtime migration
returns saved exterior characters in changed territories to their own
collision-verified arrival once, preserving progression and interior saves.
Historical daily-quest bookmarks are retained; there is no invented nonlinear
mapping from old gathering locations to unrelated new ground.

Publication updates the paired server profile, registry, exterior connection
tables, returns, collision, generated ELMs, invasion positions, and package
digests. The atlas stage renders the actual complete master once, crops every
territory on the same pixel lattice, and publishes the Tab continent image and
hit polygons. It never uses a concept image as the playable atlas.

## Validation sequence

1. Run the relevant `_continent/tests` and client/server contract tests under
   the common CPU limit. Rebuild affected libraries, compose, then export
   geometry. Inspect retained assembly reports and drainage conflicts before
   treating the scene as ready for contracts.
2. Run `audit_continent.py --geometry-only --output <review>/geometry-audit.json`
   against the current export. This provisional mode derives ownership,
   translations, envelopes and provenance from actual named manifests and
   `export.json`; it does not require an already published canonical layout.
   It exhaustively compares the master, source terrain, named territories and
   independent chunks for exact face ownership, shared position/normal/UV/colour
   membership, materials and external image hashes. It does not certify a live
   server or current collision publication.
3. Review gameplay-camera captures and the master overview. Check riverbanks,
   approaches, canopy obstruction, city floors, bridge silhouettes, island
   bridgeheads and occupied harbours. Bridge export checks a single shared
   deck union, actual bank fit, emitted triangle grade and hidden threshold
   support; inspect its reports rather than using a centreline slope alone.
4. Run `contracts` against the actual exported surfaces. Its report must cover
   every required arrival, lane, entrance/return and content standing point.
   Then run coordinated `publish`, `atlas` and `verify`. Full
   `audit_continent.py --server <paired-server> --output <review>/continent-audit.json`
   additionally checks canonical/client/server publication and height alignment.
   Pipeline `verify` also checks the Tab-map build; it does not run all the
   independent tests or the live walking harness.
5. Generate fixtures with
   `eloria-assets/tools/generate_continent_walk_proof.py --server <paired-server> --data <ELM-directory> --output <review>/walk`.
   Require its package, geographic adjacency, reciprocal lane, ferry and
   independent server path audits to pass. Inspect `allContentAccess` for
   exhaustive content claims; representative fixtures alone are insufficient.
   Counts come from the current publication and actual ownership adjacencies.
6. Run `godot-client/tests/integration/rendered_landscape_walk.gd` in the real
   client against that server, setting `ELORIA_WALK_SPEC`, `ELORIA_ARTIFACT_DIR`
   and the integration host/port for each generated fixture set. Prove centre
   and shoulder crossings, neighbouring-map clicks, services/resources,
   interior round trips and ferry round trips. Check exact ferry actor-spawn
   tile/global centre before a subsequent move, cold-arrival focus and active
   collision, grounding, camera overlaps, retained target movement and actual
   loading/retirement behaviour. Capture matching before/after viewpoints and
   record measured performance limitations.

Keep reports with their input hashes and do not mutate their inputs during a
proof. A geometry-only pass, generated route fixture or diagnostic camera
survey is useful evidence within its scope; none substitutes for the final
paired publication and live route proof. Update the provisional QA notice only
after those artifacts have been reviewed together.

## Regional design responsibilities

| Territory identity | Geographic and inhabited role | Next regional art pass |
| --- | --- | --- |
| Whitehorn Range (`whitehorn_range`) | Highest northern spine, headwaters, alpine refuges and cave approaches. | Use connected rocky shoulders, sparse exposed vegetation and snow pockets. Keep headwater banks readable and let conifers enter sheltered lower slopes gradually. |
| Grey Moors (`grey_moors`) | Wet western uplands, old crossings and scattered shelter. | Group peat hollows and damp heath around drainage; preserve open grazing, distant silhouettes and modest groves instead of turning the moors into Amberwood. |
| Amberwood (`amberwood`) | Sheltered woodland and inhabited canopy country below the snowline. | Establish uneven age/density, clear village approaches and low riverside shelves. Protect trunks and ground stairs while leaving real air beneath elevated platforms. |
| Amethyst Barrens (`amethyst_barrens`) | Dry northern lee, mineral workings and exposed stony routes. | Build related mineral formations with debris and sparse hardy plants; weather the same mountain shoulders into dry gravel before reaching steppe. |
| Mirrorhold (`mirrorhold`) | Fortified pass city and inland lake harbour. | Preserve its coordinated streets and roof silhouettes; fit civic terraces and lake edges to local geography, with clear gates and readable lake-to-pass approaches. |
| Sunmane Steppe (`sunmane_steppe`) | Eastern grasslands and broad overland travel beneath coastal downs. | Emphasise long grasses, grazing/open combat space, sparse dry-country groves and greener drainage. Keep a grassland/coastal buffer between bare mineral ground and sea. |
| Four Gates (`four_gates`) | Principal western road junction and convenient civic service hub. | Make roads widen at useful shared spaces; add restrained yards, cultivated plots and work areas around coherent civic floors, with open sightlines to gate landmarks. |
| Westhaven (`westhaven`) | Working western harbour, lighthouse and sea trade. | Connect quays to warehouses, fish market, ropewalk and yards. Read water depth, tidal margins and harbour machinery at gameplay distance; preserve boat/shore relationships. |
| Manymouth Delta (`manymouth_delta`) | Western distributaries, raised boardwalk town, paddies and fishing hamlets. | Let reeds cluster at sheltered banks and fields follow wet ground. Preserve navigable water beneath floors and readable temple/hamlet approaches without filling the delta. |
| Crownwater (`crownwater`) | Seventeen-island causeway city and southwestern sea connections. | Refine bridgehead shelves, quays and sheltered landings around individual islands; retain open water, island silhouettes and the formal causeway network's deliberate order. |
| Verdant Stair (`verdant_stair`) | Humid southern limestone uplands below the declining spine. | Group wooded terraces, exposed limestone and moist clefts; route paths with the relief and leave open landform views between groves. |
| Ssarathi Ruins (`ssarathi_ruins`) | Southern ruins and wet lowlands below the limestone chain. | Keep temple, pyramid, vault entrance and ritual plaza as a coherent complex. Use old masonry, roots and quieter overgrown branches to make danger emerge beyond the approach. |

Further art passes should modify the shared landform and these local activities
before adding small dressing. Keep settlement service routes easy to read,
leave combat room and quiet ground, and let danger emerge from exposure,
terrain and discoveries rather than identical rings around every arrival.
Always re-export the complete continent after changes that affect a shared
ridge, drainage line, road, material field, or ownership boundary.

The reusable principles are shared geography, connected assembly support,
ecological grouping, purposeful routes, readable silhouettes and quiet space.
Reuse those rules and the shared toolkit while varying soil, vegetation,
building activity, water edges and landmark rhythm by the table above. Work
from broad landforms to routes, major structures, vegetation and finally
surface detail, revisiting earlier steps from the gameplay camera. Neither
equal territory sizes nor a repeated settlement/attraction template is a goal.

## Authored terrain edits

`diagonal-plan.json` may carry a `terrain_edits` list of authored corrections to
the modelled ground. `landscape.height_at` applies them in the plan's own list
order after the natural ground, drainage, relief sources and dry basins, and
before the foundations, so a building pad still settles last. An absent or empty
list changes nothing. The plan editor previews an edit by importing `landscape`
and calling the same `height_at`, so what it draws is what `compose` builds.

```json
{"id": "camp_shelf", "name": "Ridge camp shelf", "op": "flatten",
 "shape": {"circle": {"center": [640, 700], "radius": 26}},
 "target": 42.7, "feather": 12, "strength": 1}
```

`op` is `raise`, `lower` or `flatten`. `shape` holds exactly one of `circle`
(`center`, `radius`), `polyline` (`points`, `width`, the whole band measured
across the straight segments between the authored vertices, not a curve) or
`polygon` (`points`, closed, even-odd containment); every point is `[x, z]` in
continent metres. `feather` is the metres over which the effect fades outside
the shape (`weight = 1 - smoothstep(0, feather, distance outside)`, so a feather
of 0 is a hard edge) and the optional `strength` in 0..1 multiplies that weight.
`raise` adds `amount * weight` metres, `lower` subtracts them, and `flatten`
blends the ground toward `target` metres. `ramp` takes a `polyline` and a
`heights` list with one height in metres per point, and blends the ground toward
its own sloped surface: the heights interpolated along the nearest straight
segment, level beyond the first and last point, so a gentle walkable way can be
cut or filled through a band of ground too steep to walk (the seventeenth
publication's reach links). A `smooth` op is deliberately not part
of v1: a pass that reads its neighbours cannot be evaluated at one broadcast
point, and the validator rejects it by name.

A stored plan always carries numeric targets. `resolve_terrain_edit_targets(plan)`
returns a copy in which a flatten `target` of `"min"`, `"max"` or `"mean"` has
become that statistic of the natural ground, which is the plan with every
terrain edit removed, sampled on the composed 2 m grid inside the shape and
rounded to 0.1 m; numbers are kept. `validate_terrain_edits(plan)` returns the
problems the editor shows: missing or duplicate ids, unknown keys or op, a shape
that is not exactly one of the three, a polygon under three points, a polyline
under two, a radius or width of zero, and points outside the plan `bounds` by
more than their feather. `height_at` itself refuses an unresolved string target,
an unknown op or shape, a negative amount or feather and a strength outside
0..1, naming the edit in the message.

```powershell
python landscape.py --check-terrain-edits [plan]              # exit 1 on problems
python landscape.py --resolve-terrain-edits <plan_in> <plan_out>
```

`relief_outline(source)` returns the four `[x, z]` continent-metre corners of a
relief source's crop rectangle, in the order `x0z0`, `x1z0`, `x1z1`, `x0z1`,
carried by that source's own translation and squeeze (the whole sampled extent
when it declares no `crop`). The plan editor draws that polygon instead of
repeating the retained transform's arithmetic.

## Reach links

The contracts refuse a placement the served walk grid cannot reach from its territory's arrival, and served ground is
walkable only at a grade of .65 or less. Where a band of steeper ground cuts an area off, `diagonal-plan.json` may
carry `reach_links`: entries in exactly the terrain edit format above (`ramp`, `flatten`, `raise`, `lower`, with
`feather` and `strength`, checked by `reach_links.validate_reach_links`). Unlike a terrain edit, which shapes the
modelled ground before the foundations and the roads (so a road that re-routes onto its gentle ground, or a footing
feather, grades it again), a reach link is written by `reach_links.apply_reach_links` once the roads are settled and
the support stages have finished the ground; the road heights are refreshed onto it and the placements regrounded on
it afterwards, and nothing else moves it. A link whose weight reaches a river's centreline, or the footprint of a
member of a rigid compound (which reground does not move), is refused; a member that hangs above the ground (a canopy
walkway or platform) holds none, and a tree member holds only the three metres round its trunk. Outside the links'
bands the linked ground is then smoothed (`smooth_link_change`): no two neighbouring 2 m cells differ by more than
`WALL_METRES` (4 m), or by the ground's own step plus a metre where it was already steeper, so a deep cut or fill on a
steep face ends as a broader terrace instead of a wall. The smoothing moves only ground too steep to walk: the bands,
every corner of a triangle gentle enough to carry walking (`WALKABLE_GRADE`), the river centrelines and the ground under
compound members keep their heights, so it never takes reach away. Where that fixed ground leaves no room for 4 m (a
switchback's crowded legs), the allowed wall grows by half again pass by pass and the fall is shared out as evenly as it
can be; a step between two fixed cells stays, and the report counts the walls left (`wallsLeft`,
`tallestWallLeftMetres`). Walls between crowded legs are a design matter: space the legs further apart. The
composition records every link's changed cells and the smoothing
(`composition.json` `reachLinks`). Links are designed against the served walk grid of the previous composition;
because they do not change the routing, that prediction holds.

## Authored points

Some records stand where no served ground can reach them however the ground is linked: a secret door on a cliff face or
a tower wall, a return inside a building's box. `diagonal-plan.json` may pin such a record in `authored_points`:
`{"region", "tile": [x, y], "point": [x, z], "record", "reason"}`, where `tile` is the record's tile in the authored
server profile (the contracts report's `oldTile`) and `point` is open ground beside the entrance in continent metres.
`authored_points.prepare_authored_points` pins them before any road is routed (inside the territory and on dry ground,
or the composition stops), exactly as the Four Gates Sage records are pinned; the placer still resolves each pin to
standing ground within the record's own displacement budget, and `refresh_authored_point_heights` reads the heights
from the finished ground after the reach links. The composition records them (`composition.json` `authoredPoints`).
The door and discovery roads are routed to a pin by default. A pin with `"roads": "entrance"` keeps them on the
record's own entrance: a road re-routed to a pin re-settles its territory's road earthworks, which moves the ground
under reach links designed on the old ground (routed to its pin, the Grey Moors undercut mouth lost its discovery
trail; the territory's roads settled up to 6 m differently as far as 150 m away and 49 barrow-country records were
cut off).

## Build progress and composition freshness

`build_pipeline.py` and `build_continent.py` write `generated/progress.json`
while they work, so a separate tool can follow a running build without parsing
the console. Every record replaces the file atomically:

```json
{
  "stage": "compose",
  "step": "roads and routing",
  "fraction": 0.25,
  "status": "running",
  "startedAt": "2026-09-15T20:12:31.004Z",
  "updatedAt": "2026-09-15T20:18:02.560Z",
  "exit": null,
  "pid": 8124
}
```

The stage runner writes one record as each stage starts and one as it ends
(`status` `done` with `exit` 0, or `failed` with the failing stage's exit code),
so a stage with no inner steps still reports. The composer adds inner steps: the
four compose phases (loading libraries and content, roads and routing, supports
and ground, writing the composition), and one step for each exported territory
during geometry, where `fraction` is territories exported over their total.
`fraction` is always 0..1 and `pid` identifies the process that wrote the
record, since the composer runs as its own process. Progress is reporting only:
a record that cannot be written (a locked file, a read-only directory) prints a
warning and the build continues.

`python build_continent.py --freshness [--output <generated>]` reports whether
the composition on disk still matches the inputs it recorded, without composing
or exporting anything. It prints the report as JSON and exits `0` when fresh,
`1` when stale and `2` when nothing is composed:

```json
{"fresh": false, "composed": true, "changed": ["plan"], "missing": [],
 "unknown": [], "recorded": {"plan": "9325..."}, "current": {"plan": "44c1..."}}
```

The digests are exactly those the composed cache is loaded against: the plan,
the entrance profile, the composition algorithm, every shaping module, and any
other single-file digest recorded under a `*Sha256` key that this branch can
name (an optional `continent-edits.json` beside the plan, recorded as
`objectEditsSha256`). `changed` lists inputs whose bytes differ, `missing` lists
recorded inputs that no longer exist, and `unknown` lists recorded `*Sha256`
keys that cannot be mapped to a file, such as one written by another branch;
all three read as stale rather than raising. Retained content libraries are not
covered, because their cache path is a `--library` argument the composition does
not record: the `compose` and `geometry` stages remain the authority there.

## Seam road waypoints

A seam road runs from a territory's hub to its side of a border crossing.
`door_approaches.py` lets such a road follow authored waypoints, exactly as a
door road does: `SEAM_ROAD_WAYPOINTS` keys `(region, connection id)` to
continent-metre points, and `RETAINED_SEAM_ROAD_WAYPOINTS` keys the same to
source (library) metres, which the plan's retained transform carries where the
retained layout stands. A connection id is the crossing's own id, the two region
ids sorted and joined by `--`, and each of the two sides of a crossing is
authored under its own region: the mountain side takes the climb while the other
side stays a straight run to the terminal.

`prepare_door_approaches` validates a waypoint exactly as it validates a pinned
road end - inside the territory whose hub the road leaves, on dry ground
(`MINIMUM_DRY_METRES`) and out of the water - naming the offender
`<region>:<connection id> waypoint <index>`; a source-frame entry for a
territory with no retained transform is refused rather than placed anywhere.
The prepared points become `content.seam_road_waypoints`, read with
`seam_road_waypoints(content, region, connection_id)` (empty for every seam
without an authored pass), and are reported under `doorApproaches.seamWaypoints`
as `{"<region>:<connection id>": [[x, z], ...]}`, beside the door roads' own
`doorApproaches.waypoints`.

Composition routes both kinds of road with `route_in_legs`: hub -> waypoint ->
... -> end, where every leg but the last drops its final station so a joint is
not a station twice over, and the road's own retained solids (the hub's, for a
seam road) ride the first leg only. With no waypoints this is the single
`world.route(hub, end)` call it has always been, so unauthored seams and doors
keep their alignments unchanged and only an authored pass moves.

The plan phase authors two passes, both in the source frame because Whitehorn
Range keeps its legacy relief under a retained transform:
`('whitehorn_range', 'grey_moors--whitehorn_range')` for the Moors pass,
authored as a switchback climb, and
`('whitehorn_range', 'amethyst_barrens--whitehorn_range')` for the east pass.
Both tables ship empty until then.

## Masked relief sources

A relief source may carry an optional `mask`: an authored polygon that narrows
its rectangular crop to a leaf shape, so a legacy heightfield fades along an
outline someone drew instead of along the edges of its crop.

```json
{"samples": "legacy-relief/whitehorn_range.npz", "translation": [477, 90, 272],
 "crop": [-105, -291, 280, 95], "feather": 56,
 "mask": {"polygon": [[380, 40], [600, 12], [648, 180], [470, 300]], "feather": 60}}
```

`polygon` is at least three `[x, z]` points in **continent** metres, not in the
source's own surveyed frame: the leaf is drawn over the composed map, where its
shape is judged, so changing the source's translation, squeeze or yaw moves the
heightfield under a mask that stays where it was drawn. Its edges are the
straight segments between the authored vertices and containment is even-odd,
exactly the rule a polygon terrain edit follows. `feather` is the metres over
which the source fades outside the leaf (`1 - smoothstep(0, feather, distance
outside)`, so 0 is a hard edge, and 0 is the default).

The source's weight becomes `crop_weight * mask_weight`. The crop rectangle and
its own `feather` therefore keep working unchanged and the mask only ever takes
weight away; a source without a `mask` is evaluated exactly as before, to the
last decimal. `snowline_at` already carries the source's whole weight, so a
`snowline_drop` follows the leaf as well: past the mask and its feather the
plain latitude snowline stands, even well inside the crop.
`relief_mask_outline(source)` returns the polygon as `[[x, z], ...]`, or `None`
for a source without one, beside the crop rectangle `relief_outline(source)`
gives the plan editor. `height_at` refuses a mask of fewer than three points, a
point that is not a finite `[x, z]`, and a negative feather, naming the source.

Only the points inside the polygon's bounding box grown by its feather pay for
its geometry, the window the terrain edits use, so a leaf over one territory
costs the 631k-point composed grid about 40 ms - inside the noise of the 30 s
that grid's `height_at` already takes.

## Extra ownership sites

Territory ownership is a Voronoi partition of the plan's region `center` points,
biased by `ownership_bias`. An optional `ownership_sites` section gives a region
further sites, so a territory can carry a tail into ground a single centre
cannot reach:

```json
"ownership_sites": {"westhaven": [[300, 1320], [418, 1402]]}
```

Each region's score at a cell becomes the **least** squared distance over its
centre and its own extra sites, minus its `ownership_bias`; the lowest score
owns the cell and a tie keeps the region listed first, as before. A region owns
the ground nearest any site it declares, as well as the ground nearest its
centre. Everything downstream is unchanged: `World.owner`, `owner_at`,
`polygons`, `bounds` and `address` read the same grid as they always did, and
`plan_connections` still scores and orients its crossings on the region centres,
not on the sites.

`world_layout.ownership_sites(plan, ids)` is the authority the `World`
constructor uses, and the constructor keeps its result as
`world.ownership_sites`. It raises `ValueError` for a region the plan does not
name and for a site outside the plan `bounds`; a region with no extra site is
absent from the mapping and is scored exactly as it was. A tail must stay joined
to the rest of its territory: `outline` traces one contour per region, so ground
that a site wins on the far side of a neighbour still belongs to the region in
`owner` and `owner_at` but is quietly missing from its `polygons` entry, and so
from its `bounds` and `address`. Each extra site is one more vectorised distance
field over the 630k ownership cells, about 15 ms, so a handful is not felt.

## The ownership partition on its own

`world_layout.ownership_map(plan, cell=CELL, ids=None)` returns
`(ids, owner, x0, z0)`: the territory partition of the plan's `bounds` on cell
centres `cell` metres apart, scored from the region `center` points,
`ownership_bias` and `ownership_sites` and nothing else. No heights, no water
and no sampled continent, so the plan editor draws the partition at 8 m in
milliseconds without building a `World`. `ids` are the plan's regions in its own
order unless a list is given, and `owner` is an int grid of indices into them,
row 0 at `z0` and column 0 at `x0`, whose cell `[row][column]` covers
`[x0+column*cell, x0+(column+1)*cell)` by `[z0+row*cell, z0+(row+1)*cell)` and
is scored at its centre. The `World` constructor is one call to this at `CELL`
on its own grid, so the preview and the world it previews cannot drift: the
scoring, the bias and the tie rule exist in one place only.

`owner_components(plan, region, cell=8.0)` labels that region's cells
4-connected and returns one boolean mask per component, each the grid's own
shape, largest first; count a mask with `np.count_nonzero` and read its metres
with `component_extent(mask, x0, z0, cell)`, which gives
`{"cells": n, "bounds": [x0, z0, x1, z1]}`. `owner_islands` is the same list
past the largest, empty when the territory is one body of land. This is how to
see the trap the section above names: a site that wins ground on the far side of
a neighbour leaves a territory in two pieces, and since `outline` traces a
single contour that island is quietly missing from `polygons`, and so from
`bounds` and `address`, while `owner` and `owner_at` still name the region. Every
territory of the live plan is one component at 8 m.

## The published content transform

`export_contracts.content_transform(content, region)` builds the
`contentTransform` each region's publication spec carries: the mapping from that
territory's legacy source frame into the continent, and the continuous fallback
for any content point the export never placed explicitly.

The old fields stay. `scale` about `sourceCenter`, with `targetCenter`, is one
uniform scale and no turn, and it is all that
`publish_diagonal_continent.transform_tile`, `estimated_served_tile` here and
the paired server's `tests/geographic_contracts.native_area_tile` can read. A
retained transform may now squeeze its layout per axis and turn it about its own
point (Whitehorn), and no scalar carries either, so an exact `affine`
`[a, b, c, d, e, f]` is published besides: continent `X = a*x + b*z + e` and
`Z = c*x + d*z + f` for a source point `(x, z)`. It is read straight off
`Content.mapped_xz` at `(0, 0)`, `(1, 0)` and `(0, 1)`, so it reproduces
`landscape.retained_map_xz` for a retained territory and the centre-and-scale
rule for every other one - to about 1e-11 m, the cost of differencing probes -
with no second copy of either rule to drift. A dict transform publishes its own
`yawDegrees` and `squeeze` `[sx, sz]` as well, for a reader that would rather
compose the turn itself. Mind the frames: `affine` lands on absolute continent
metres, while the old fields land relative to the territory's centre, the spec's
`translation`.

`scale` stays a number wherever the mapping really is a uniform scale - every
territory on the centre-and-scale rule, and a retained transform that is a rigid
translation - and is `null` where the layout squeezes per axis or turns, where a
single number would be a wrong answer rather than a rounded one. That case used
to be `float()` of a two-axis scale, which raises `TypeError` under numpy 2 for
*any* retained transform, a rigid translation's `[1, 1]` included. The three
readers above all take `scale` as a number and
`publish_diagonal_continent.validate_spec` rejects a `null` outright, so
publishing a squeezed or turned territory needs them taught the affine first:
that is a follow-up, not something this transform can paper over.

## Inverted winding in retained library meshes

Many certified library meshes wind their triangles against their own vertex normals. The toolkit's
`mesh.lathe` does, and so do the sides of `mesh.cylinder` (`routecraft.annular_walk` and
`templecraft.sun_disc` say so where they compensate), so barrels, log piles, posts, towers, domes,
pavilion floors and pine crowns stand inside out: the client and the atlas rasteriser
(`_toolkit/native/raster.c`) cull their outsides, and every classifier that reads a face's facing
from `cross(b - a, c - a)` sees their walking faces pointing down. `winding.py` corrects them in
memory; the certified `library.glb` files are never rewritten.

`normalise_winding(document, body, *, min_cos=-0.2)` returns a private copy of a loaded document,
its body and a report. The vertex normals are the evidence: a triangle whose geometric normal opposes
the sum of its three vertex normals (cosine below `min_cos`) is listed backwards. The decision is
taken per sheet, the triangles joined across welded edges they traverse in opposite directions, and a
sheet turns whole when its area-weighted mean cosine is below `min_cos`. A lone triangle is the plain
rule; a crease whose smoothed normals point the wrong way inside a consistently wound surface is
outvoted (the Amethyst geode mouths, boulders). The normals are not always the right side, because a
lathe points its normals by its profile's direction: a profile running clockwise round its solid has
inward normals over an outward winding. So the back copy of a two-sided card that kept its front's
normals keeps its winding (the Grey Moors scrub), as does a closed sheet that already encloses a
positive signed volume, and an open sheet of a clockwise lathe named in `KEEP_WINDING` (the Whitehorn
icefall columns, the skep, the Crownwater compass-rose ring); and a level triangle whose winding is in
question faces up when its material has `water` as a whole word of its name, whatever its normals say
(fountain and well pools are flat lathes run outward from the axis, the Ssarathi waterfall plunge rings
clockwise ones). Primitives without normals, non-triangle modes, double-sided materials and unreadable
accessors are reported and left alone. A reversed triangle has two indices swapped in a new index
accessor of the same component type, on a new buffer view appended to a new body at a 4-byte boundary;
untouched primitives keep their accessors, geometry shared by several meshes is corrected once, and the
result exports through `scene_io.Exporter` as the original does. `winding_report(document, body,
nodes=None)` measures without correcting, with placed (world) areas over the given node instances.

`content.load` corrects each library document straight after reading it, before the Amberwood camp
source, part edits, the layout turn, object edits, bounds and grouping, so retained structures,
natural prototypes, ecological scatter and object-edit copies all read corrected geometry. That costs
0.3 to 1 s a library, about 7 s for all twelve.

    python winding.py --library <task root>/library [--region R] [--output report.json]

audits the libraries without changing them: per territory the primitives corrected, the triangles
flipped, their placed area, what was left alone and why, and the meshes with the most flipped area,
written to `<task root>/experiments/winding-audit/report.json`. Downstream, backwards library `Walk_`
decks become deck support in the served collision (a closed slab serves its top instead of its
underside), a colliding solid whose inward-wound part overlapped its outward body blocks that volume
again (collision_export's winding number had summed to zero inside it), and the atlas draws the roofs
it used to cull.

The sheets a rule keeps wound against their normals (the open sheets of a `KEEP_WINDING` lathe and level
water facing up) would be lit from behind: `normalise_winding` negates their vertex normals in a new float
NORMAL accessor on the same appended body (`relit_*` in the report), except at a vertex another triangle
also uses. The Whitehorn icefalls, the compass rose, the fountain pools and the Ssarathi waterfall plunge
rings no longer read black.

Some authored open sheets are meant to be seen from both sides and were built single-sided: the Sunmane
canvases (pavilion roofs, tents, windmill sails, market canopies), the Four Gates arcade walls, boats, the
Ssarathi shrine and ruin roofs, the Mirrorhold rose window and falls. `winding.DOUBLE_SIDED_SHEETS` names them
per territory, as whole materials when every use is a sheet and as (mesh pattern, material) pairs when the
material also dresses closed solids; `content.load` applies it with `double_sided_sheets` straight after the
winding correction, pointing the listed primitives at a doubleSided copy of the material that keeps its name.
Bark and branch meshes and models built against terrain are left out.
