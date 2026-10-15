# The inhabited Crownwater shores

The 396-metre archipelago keeps the Crown Basilica, campanile, customs house and
pavilions at their existing human scale. Shorter water crossings and deliberately
placed shores create the smaller footprint. The origin is (120,120), with the
arrival at world (0,0) in the working harbour.

The harbour has a service court, market, net-menders' and ferry crews' cottages,
customs ramp, cargo yards, boats and lamps. The civic island rises above it on a
graded approach. Garden banks, pearl-working shores, northern packet berths and
quiet exposed reef islands have distinct uses. Feather palms grow on sheltered
banks; open water and sparsely planted outer shores remain part of the layout.
The exposed seabed is continuous, so even water tiles have a grounding surface.
The lake is one continuous common-water plane. Actual limestone banks occlude
its shoreline; the shared causeway pass partitions the seam patch exactly.
This avoids rectangular dry gaps from coarse water-cell clipping.

Six ferries remain intentional journeys: Mirrorhold, Amethyst Barrens,
Westhaven, Grey Moors, Manymouth Delta and Ssarathi Ruins each have their own
departure pier. The Four Gates causeway is the continuous exterior join. Its
stone carriageway is seven metres clear and four metres above water. The native
deck meets the shared transition at world (228.5,4,-10.5); the seam anchor is
(270.5,4,-10.5). No services or doorways occupy its last 42 metres.

All 20 landmark IDs, 14 ordinary portal IDs and 13 exterior secret IDs remain.
Seven ordinary doors lead into the existing `drowned_crown` package. The Customs
Cache remains inside that package. Tollmaster Quent still controls the Drowned
Arcades. Its authored keeper tile is (135,123) and return court is (152,122).
The current configured exterior roster is 14 NPCs, 44 resource nodes and 49
creatures, including three later-added barnacle ogres. Broad habitat discs are
footprint-packed on reachable working ground; `requireFullWildlife` rejects any
future rebuild/publication that silently loses an authored encounter.

Run `python source/rebuild_landscape.py --verify` to build the main GLB, far
package and geometry-derived minimap, then refine walking heights, open exposed
surfaces, stamp solid landmarks and guard actual actor-centre support. This
never writes server configuration. The coordinating rollout applies the
revision-guarded migration helper and scoped content/portal publication.

`source/coastal_plan.py` records the explicit islands, shores, piers and protected
neighborhood mapping. `source/coastal_population.py` composes grounded shore
buildings and decks from the shared toolkit. The palm leaf geometry and planar
plaza mosaic projection are authored locally. Existing interior geometry and
all lore, keys and destinations remain intact.

Main and far glTF validators report zero errors and warnings. The runtime
geometry verifier samples all 156,816 server positions with zero grounding
misses. The strict server movement audit starts only in the harbour and checks
every departure and secret standing tile. Eighteen real-client route fixtures
cover services, the civic approach, working shores, the gauntlet keeper and all
fourteen named transitions.

The current fixture has 39 exact `World.find_path` legs, at most 21 steps each,
using the served ELM collision and configured one-tile NPC footprints. Service
furniture receives conservative 3×3 clearance. Information and crafting steps
require positive text replies; storage must open. Tollmaster Quent is approached
at (135,124), adjacent to his occupied (135,123) post. The pearl-diver route starts
at clear (286,189), beside Ansil Quen's (287,189) post.

All seven interior walks first move two metres away from the automatic arrival
and exit, then walk back through the real return. Drowned Chapel Verger Tomas
Rill works at (45,277), beside the undercroft threshold at (43,277). The scoped
migration reproduces this post even when the exterior revision is already
applied. A server regression checks every ordinary interior arrival and exit
against configured NPC footprints. No interior geometry or dialogue changed.

Regenerate these fixtures with `python source/write_walk_fixture.py --server
<server-checkout> --data <served-ELM-directory> --out <artifact>/live-fixture.json`.
The companion `fixture-occupancy-audit.json` records paths, all fourteen arrival
checks, configuration hashes and served ELM hashes. Moving creatures remain the
live traversal's responsibility.

The first corrected package exposed a collision mismatch at bridge edges:
the inherited integer-centred conservative fold could extend a deck past the
actual actor centre at tile + 0.5. The final shared actor-surface guard closes
unsupported tiles without inventing geometry. These checks are distinct from
expected height discontinuities between elevated bridges and the lakebed below.
The final report records exact guard and verification results.

Matched gameplay-camera captures, frozen capture package hashes, annotated
comparison, current package hashes, strict collision/content probes and the live
fixture are retained under `work-output/coastal-rollout/crownwater`. The survey
uses the complete client at 1440 × 900 with the same camera yaw/distance at each
named place. Older comparison documents describe the previous 576-metre build.
