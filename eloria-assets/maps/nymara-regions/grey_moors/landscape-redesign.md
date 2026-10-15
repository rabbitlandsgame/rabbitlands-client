# Grey Moors: inhabited burial country

The exterior is 384 by 384 metres at one metre per server tile, with origin
(116,116). Travel space contracts between protected refuge and Great Barrow
bands; shelters, stones, doors and furniture retain their human dimensions.
Timber crossings are rebuilt at 3.2 metres wide and stone crossings at 4.2.

The peat road refuge now has connected work and holding yards: smith and
chandler benches under the wind roof, drying stacks and a cart behind the
court, a pony watering corner, and an inland loading place above the ferry.
Its floor is worked earth. Laid stone remains on the wet causeways and burial
approach. The Great Barrow keeps its high stone crown, winding side ascent,
south-facing entrance and the Breached Barrow's blank return-field stakes.

The low moor continues beyond the rectangle. The old perimeter ridge and
radial mountain backdrop are gone. The northern Amberwood approach is a broad
4-metre meadow saddle; its roadside croft moved west into a sheltered yard so
the 42-metre approach and 60-metre-wide collar have no service or door in them.
The south-west cove remains the Crownwater ferry landing even though its
stable portal ID is east-waygate.

Sedge and heather grow in coherent moisture and shelter patches. Grazing
ground beside the refuge remains open; solitary ritual stones concentrate on
the burial ridge and selected moor shoulders. Deep pool interiors block
walking, their margins permit shallow wading, and actual deck triangles carry
the routes over water. Doors into the west, east and fen crypts use the ground
in front of their lintels and gain short approach paths.

All four exterior portal IDs, seven interior entrance IDs and fifteen exterior
secret interactives remain. The secret inside the West Crypt remains on its
existing interior map. Species, resource roles, services and narrative names
are preserved; content patches and authoritative coordinates are migrated by
the source survey and the integration pipeline.

## Reproduction

Run `python source/rebuild_landscape.py` for geometry, minimap, reduced package,
height refinement, deck opening, solid-footprint stamping and runtime proof.
The shared toolkit supplies the native rasteriser, mesh recipes, material
recipes and collision rasterisation. Region source owns its geographic bands,
yard paths, vegetation fields and objects; nothing is generated at login.

Before synchronizing a pre-redesign server, integration runs
`python source/migrate_compact_server.py SERVER_CHECKOUT`. Its
`inhabited-384-v1` revision guard prevents a second coordinate transformation.
Integration then regenerates map extents, collision, portal lanes, NPC/resource
posts, package markers and the shared streaming manifest. The region wrapper
does not independently rewrite shared server files.

## Review evidence

The frozen 576-metre baseline and compact result are captured by the complete
Godot client through its production isometric camera at identical yaw, zoom
and game minute 180 (brightest point of its 360-minute day). Camera targets
follow the authored coordinate survey. The survey is rendering/grounding proof;
the integration checkout additionally walks authoritative server routes.

Terrain-only verification sampled all 147,456 compact server tiles with zero
grounding misses, errors or warnings. Final exported geometry and border QA
are recorded in the adjacent validator/runtime reports and the northern
rollout Grey Moors review artifact. The review must distinguish these checks
from multiplayer actor streaming, which remains outside this landscape pass.
