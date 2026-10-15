# Nymara continent geography

Exterior scenes and the Tab atlas now share the same north-up metre coordinates.
`continent-geography.json` owns region translations, irregular footprints,
shared edge elevations, public road connections and native/server grid frames.
Buildings retain their authored scale. Extra server address cells remain
blocked where no owned ground exists; they do not imply a square visible map.

Manymouth has a 480 × 396 metre native delta around its unchanged 151 × 109 metre
market district. Outer journeys contract through an invertible authored field.
Its doors, inhabitants, resources, encounters and discoveries use the same
coordinate migration. Other regions retain their native cores and gain or give
up peripheral ground where their shared geography requires it.

Existing characters saved outdoors in Manymouth receive a one-time move to
the safe town arrival when the revised server loads them. Their inventory and
other character state are retained. Other exterior saves receive the matching
integer origin shift; this publication process does not open a live database.

## Landscape and travel

Seventeen land connections and seven additional scenery boundaries share real
terrain. The old distant backdrop rings and copied receiving strips are removed
from owned scenes. Shared boundaries have committed elevation knots; connected
road profiles meet those heights. Road decks are subdivided before grading so
their centres agree with the underlying ground. Invisible trigger support
covers the server's conservative half-metre collision samples at a crossing.

Whitehorn and Mirrorhold open into broad northern cols. Their surveyed road
heights remain fixed while curved slopes replace narrow cuts through mountain
walls. Retained landmark and discovery footings meet the final soil. Natural scrub,
rocks and crystals follow the ground; signpost metadata follows moved poles.
The northern finishing pass samples the final graded road mesh. Terrain paint
then follows the actual shaped substrate, with distinct offsets below the road
surface. Redundant nested paint copies are removed after verifying their
coverage is already supplied by the direct layer.
Paint depth must agree across the shared edge as well as physical ground.
The Sunmane receiving layers meet Amethyst's surveyed offsets, then return
smoothly to their inland levels. Its mineral wash retains the shared mask
contour and fades into grass farther from the border. This closes the thin
exposed substrate line without changing the landform. Amberwood's shore and
Verdant's northern recipe intersections use the same paint ordering to remove
overlapping surface colours after their banks have been shaped.
Four Gates' north-east recipe junction uses a small, opaque PBR texture blend
between its existing meadow and mineral materials. The regional exporter bakes
albedo in linear light, blends normal and surface properties, and clamps the
geographic texture edges. The client renders the complete material; the atlas
samples its same embedded albedo.
The physical substrate, original cutout contour and common boundary material
remain intact. This replaces the visible cutout grain in that local wash;
coarse material edges elsewhere remain a later landscape task.
Northern road bends use a connected surface with a bounded grade across the
whole travel width. The soil follows those final triangles. Where the Barrens
road crosses the retained grotto, stone ribs and seated abutments carry the
deck above the cave instead of filling the discovery with terrain.
Other generated connectors use the same conforming surface rules after the
local landscape has finished shaping. Intersections share one height grid;
native bridge decks keep their actual footprints and geometry. This avoids
the detached rectangular spans revealed by the gameplay-camera survey.
Water crossings preserve downstream drainage and use bridges with measured
landings, undersides and grounded supports. Collision checks sample upward
walking faces, including the conservative server tile footprints at bends.
Sunmane's southern approach sits within a broad dry ridge instead of a narrow
grass wall. Verdant's north burn passes under its road and cuts an exposed
limestone ravine while retaining the aqueduct foundations and downstream pools.
Ssarathi's western causeway retains its ruin foundation while clearing the full
approach beside it. Manymouth's channel routes, temple approach and hidden
entries retain explicit standing and contact checks.

Grey Moors' delta bend sits farther inland and climbs the high bank before its
descent to the crossing. Broad dry shoulders replace the narrow roadside walls;
the shared boundary and final arrival height remain fixed. Scrub follows the
new verges. A short rock-backed turnout and coarse material edges remain.

The geode workers' front shelf has a broad earth approach through the Barrens
bank. Its four-metre route and supported shoulders reconnect both workers and
the gauntlet return without changing the cave, arch or water. Movement checks
include the actual occupied world and a reachable conversation position;
roof clearance alone did not establish access. Mirrorhold's Aurel stands on
the flat public apron beside the same west-bench house, clear of the watch and
roof geometry, rather than in the disconnected space outside its fence.
The Lens Vault's full-size covered entrance fronts the connected lower working
road. A short graded approach joins its stone court, and its former isolated
high footing is released. The door identity, Orrery association and interior
arrival stay the same; the exterior trigger and reciprocal return follow the
new location. The court preserves the doorway's solid side walls and is checked
with both the occupied movement graph and the player's physical clearance.
Lens-Master Corvine and Orrery Keeper Sabel stand on opposite sides of this
working court. Their authored posts replace disconnected upper remnants,
retain their dialogue and roles, and leave the entrance and return route clear
with both characters present.
The Basin Spring discovery stone lies on the dry court beside its gallery;
the original basin lip keeps its own structural ground support. The Orrery
Vault's cracked flagstone lies beside the keepers' approach. Its former
secret-only footing no longer holds up an isolated soil spike. These moves
retain both secret identities, room destinations and the Storage Token gate.

Outer margins are shaped from the native perimeter instead of extrapolating
its last height sample into a rectangular plateau. Wet regions descend toward
their existing sea plane; Whitehorn ends in an irregular dry escarpment.
Retained bridge decks, shared boundaries and important structure footings
keep their surveyed surfaces. Local ground and service posts can change to
preserve useful approaches. Tidal vegetation keeps its native
habitat, while other natural props follow the revised ground. This pass does
not reshape every older straight edge inside those protected areas.

The lowered Verdant and Ssarathi banks seat unlinked trees by their actual
trunk roots against the final terrain triangles. Carrying the old placement
offset through a terrain edit left some trees floating; using hanging palm
fronds as the contact point would bury the trunks. Both exported detail levels
receive the root check, while water lilies retain their deliberate water habitat.

Adjacent scenery begins preparing within 240 metres of a finite shared edge.
The client retains at most three neighbors within 320 metres, with one loader
worker and bounded scene retirement. It renders each neighbor's full owned
geometry under normal frustum culling. A clicked neighboring surface remains an
exact movement destination, including scenery boundaries reached through a
different public road. The client renews long movement legs before the server's
512-step path limit, preserves expected cold-load transitions and cancels the
intent on new input or unrelated travel.

Camera-to-player occluder fading covers both active and resident scenery. Each
imported root keeps its own material fade state and spatial index through
promotion and rebasing; the index uses root-local coordinates while the final
hit test keeps each mesh's oriented bounds. Regional opacity and size limits
remain separate. Retirement restores original materials and batch membership;
disabling the setting blends retained roots back to their ordinary appearance.
Actors and collision proxies stay outside this scenery fade. Focused rendered
checks verify batch-transform restoration as well as the headless lifecycle
checks; this is a correctness result, not a frame-time guarantee.

Manymouth now declares the same authored landscape presentation for exterior
departures as the other geographic regions. This suppresses the extra generic
portal obelisk that appeared only while Manymouth was active. The registry fix
changes only that presentation flag; interior and secret entries, server
actions and package geometry remain unchanged.

Amberwood's distant package derives from the completed landscape. Terrain,
water, roads and retained object poses stay identical while tree meshes use
their low tier and unlinked ground detail is omitted. Rebuilding a separate
random forest previously changed terrain constraints and could move surfaces
between detail levels.
The Cinder Tower approach follows its authored woodland bypass. Its exported
centreline carries that bend into client/server route verification, so checks
sample the walking surface around the retained tower. Four unlinked plant
assemblies move onto nearby verges, with their actual trunk roots seated in
both detail levels; the terrain, road and tower keep their geometry.
At the Amberwood–Whitehorn ownership edge, Whitehorn's packed-earth road now
continues across the half-metre gap between the retained road mouths. Its
surface and texture coordinates meet both existing edges. This is a regional
road covering over continuous ground; it does not add a duplicate border scene.

Sea-level water uses the shared toolkit texture in continent coordinates,
with common colour, ripple phase and shading under scene rebasing. A visible
water strip remains in the reviewed crossing views; shared material coordinates
do not by themselves establish a visually continuous water edge. Raised ponds,
fountains and river surfaces retain their authored materials. The sea uses opaque shading to avoid
overlapping transparent planes exposing the old map rectangles. Scene cache
format 6 includes these water overrides.

The atlas renders the packaged geometry in the same coordinates with one
lighting setup. Its texture filter uses each triangle's projected UV footprint
to select a mip level in linear light. This removes fine texture aliasing at
continent scale while preserving broad colour variation, cutout silhouettes,
coverage and framing. It does not smooth the image or conceal rectangular
terrain and material boundaries that still exist in the authored landscape.
Opaque geographic albedo textures retain their declared clamp or repeat mode
through mip reconstruction and the atlas sampler. Unsupported clamp combinations
fail explicitly instead of silently repeating the opposite texture edge.
Soft ground paint uses the client's UV-based coverage rule in the atlas as
well. The atlas adapter compiles a small, verified specialization from the
shared raster source into its output cache and records the compiler, shader,
source and binary hashes. It leaves the shared raster source and library
unchanged. Set `ELORIA_ATLAS_CC` to a C compiler command or path when it is not
available through the normal environment.

## Reproduction and evidence

Use the staged command and verification sequence in
[exterior-streaming.md](exterior-streaming.md). Geometry packages record source
hashes, and publication rejects a stale package. The full paired publication
updates the 65 served exterior/interior/secret/gauntlet map identities, their
collision data, reciprocal returns, content positions, registry, saved-position
migrations, map digests and continent atlas.
Database initialization applies geographic address changes before outstanding
coastal and southern landscape resets. Those resets use the current served
safe arrivals, so characters upgrading across several releases receive the
address change once; later travel, inventory and quest progress are preserved.
Connector construction uses the offline NumPy/SciPy dependencies listed in
`eloria-assets/maps/nymara-regions/_northern/requirements.txt`. The preparation
stage also runs `export_continent_water.py --apply`, copying the toolkit's
unchanged embedded PNG into the client; no editor import is required.
Content publication reapplies six surveyed interior staff posts after generic
collision relocation and before package digests. They keep their names, roles
and dialogue while leaving the room arrivals and conversation approaches clear.
Manymouth's underdeck now connects its existing corridor and maze doorways with
the omitted twelve-metre timber passage. The original shallow-water setting
remains. Collision publication first regenerates its composed interior grid
from the room package, then updates the server copy and ELM.
Section-link triggers use a standing tile on the connected room floor beside
their decorative waystone. Publication searches within two tiles on each axis
and checks the exported floor and player clearance; the largest selected move
is 2.24 tiles. The subsequent occupied-world
audit verifies actual arrivals, departures and paths with staff and storage.
The publish stage copies the pure approach-contract reader into the server's
tools directory and records its exact source hash in the geography manifest.
Standalone server checks therefore use the same optional curved-road contract
as the client-side audit without depending on a local client checkout.

`audit_continent_geography.py` examines actual exported surfaces and collision
data. `generate_continent_walk_proof.py` uses the production server movement
graph to create live-client routes, exact neighbor-click targets, interior
round trips and an inventory of accessible content. The gameplay survey and
Tab atlas harnesses capture the actual client camera and map UI. Numeric
checks complement camera inspection; they do not establish visual quality by
themselves.
The legacy Emberhaven connection sits outside the 65 authored Nymara map
identities. Its boundary check uses the original solid-placement bootstrap ELM
generated by the server's existing production data recipe. It does not imply
an authored Emberhaven GLB or a streamed continent connection.

## Remaining limits

Actors, creatures, resources, interiors and ambient audio activate with the
authoritative server map. Scenery streaming does not yet simulate actors across
map boundaries. A scene that has not completed preparation uses the existing
loading fallback. Full resident packages have a larger memory footprint than
terrain chunks; chunk streaming and cross-map server interest remain separate
work.

The final gameplay views still show a visible water strip, coarse coastal paint
edges and terrain tiling, high cut cliffs around the Crownwater–Four Gates
approach, and dense translucent palms obstructing the view at Manymouth's south
landing. Whitehorn
retains coarse snow edges and exposed steep faces. Mirrorhold's basin walk is
visible from several directions, while the gallery wall occludes another.
The Ssarathi Archive's entrance projection and deep shadow obscure the pawn in
the surveyed exterior-return direction, despite successful movement and
grounding checks. Its feet cannot be confirmed visually from that capture.
These are current visual limitations, not a blanket classification of
inherited defects. Passing collision and route checks does not resolve this
remaining landscape and visibility work.

Further landscape passes should retain each biome's character: sheltered woods
in Amberwood, exposed pilgrimage routes in Whitehorn, formal civic terraces in
Mirrorhold, sparse mineral ground in the Barrens, peat drainage in Grey Moors,
working shores in Westhaven, island and ferry geography in Crownwater, ordered
causeways in Four Gates, long grassland views in Sunmane, lush climbing terraces
in Verdant Stair, reclaimed monumental ruins in Ssarathi and inhabited channels
in Manymouth. Shared geographic rules need not produce a shared settlement or
vegetation pattern.
