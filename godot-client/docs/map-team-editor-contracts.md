# Map-team answers to the editor contract questionnaire

26 September 2026. This answers the questionnaire against incoming editor `develop` commit `df50cd77c1a4c1b176097006bd834dc2d2516aa0` and the map team's preserved source/framework work. “Exists” means an inspected implementation, not proof that the twelve new source passes are published or deployed. “Build now/later” records approved recommendations for subsequent work, not features implemented by this merge. No delivery date is implied unless stated.

Source coordinates are territory-local metres (+X east, +Y up, +Z south); `continentTranslation` converts to continent coordinates. Logical server tiles, terrain vertices and 0.5 m collision samples are distinct grids. Snapshot `RegionSnapshot._server_tile()` uses `[floor(x/metres_per_tile + server_origin.x), floor(server_origin.y - z/metres_per_tile)]`; storage minima never rebase this transform. The snapshot schema is `eloria-continent-authoring-v1`.

Editors may edit agreed local controls/resources and tool code; the map team owns original base buffers, stable gameplay identities/bindings, shared catalogs, source specs, ownership/frames, shared water/routes, generated outputs and publication. Preserve all twelve accepted saved-source passes. Corrected ownership is approved but its production selector remains inactive; exact boundary mesh clipping is not integrated. Do not promise seamless polygon clipping from the current full-cell export.

Client code links are relative to this document's intended location, `eloria-client/godot-client/docs/`. Server references are explicitly namespaced `eloria-server/`. Function names identify the implementation; research-time line hints may shift during integration. QA archive references identify retained review evidence outside the shipping repositories. Unless explicitly labelled as run, test-data paragraphs are proposed verification, not execution claims. This questionnaire research performed no scene saves or editor tests.

## A1 Ground texture painting

**Decision:** Build now by creating/editing ordinary Ground/Regions controls; defer a new paintable splat-map schema until the first brush proves insufficient.

**Contract:** `Ground/Regions/<stable id>` uses `MapAuthoringGroundRegionControl`: enabled bool, ellipse/rectangle, local Transform3D, size Vector2 in metres, blend_width metres, opacity 0–1, integer priority and local `MapAuthoringSurface`. Inspector ranges are size ≥0.1, feather 0–8, priority −1000..1000 ([base declarations](../src/dev/map_authoring_pilot/ground_region.gd)); these are not all enforced by the Python validator. Example: ellipse 24×14 m, 3 m feather, opacity .90, priority 10, Limestone surface. No new per-territory weight-map resolution/layer contract is proposed now.

**Consumer:** [`_ground_region_records`](../src/dev/map_authoring_region/region_snapshot.gd) emits `groundRegions`; [`authored_overlays`](../../eloria-assets/maps/nymara-regions/_continent/terrain_export.py) emits alpha-weighted terrain-following GLB triangles. Existing [`build_masks`](../../eloria-assets/maps/nymara-regions/_continent/biome_blend.py) generates continent masks: 64² inner samples plus one-pixel gutter, up to four territorial palettes, each base plus at most one secondary. These are generated biome/seam data, not editable paint storage.

**Validation:** [`_validate_ground_regions`](../../eloria-assets/maps/nymara-regions/_continent/authoring.py) rejects invalid shape, nonpositive size and nonfinite fields; supported Surface required. Preview currently draws at most 127 controls ([line 777](../src/dev/map_authoring_region/terrain_control.gd)); brush must not silently exceed that. Keep footprint inside approved ownership; seam-spanning painting awaits clipping integration.

**Ownership:** Local scene and local surfaces only; shared masks/palette definitions remain map-team generated.

**Test data:** Verdant pass1 invariants (review archive: `work-output/verdant-stair-implementation/pass1/invariants.json`): joined court/apron remains visible after save/reopen/bake; all original objects and height/color bytes unchanged.

## A2 Grass and foliage painting

**Decision:** Build later, after A1/A4/A10 and the water contract; first settle a bounded foliage runtime budget with profiling. Sparse ordinary asset placement already exists.

**Contract:** No density-map or foliage-instance snapshot section exists. Density units should be instances/m² if introduced, but seed algorithm, catalog whitelist, view distance, LOD, chunk size and numerical budget are **unknown/unapproved**. Do not invent fields in `extras`. An initial editor scatter tool could instead commit deterministic ordinary asset wrappers, with seed used only during placement; that is a separate bounded proposal, not a foliage runtime contract.

**Consumer:** [`WorldLoader._create_batch`](../src/world/world_loader.gd) creates MultiMeshes for existing identical static meshes; constants are minimum four instances and 180 m spatial cells ([lines 10–18](../src/world/world_loader.gd)). This is batching, not density generation or foliage LOD. [`_is_batchable`](../src/world/world_loader.gd) excludes collision children, skins, instance overrides, blended materials and explicit visibility ranges. Current snapshots have `objects`, not `foliage` ([document fields](../src/dev/map_authoring_region/region_snapshot.gd)).

**Validation:** No foliage validator/error exists. Ordinary wrappers still require valid source nodes; editing generated Content fails with “edits inside Content are not exported” ([`_validate_asset_source_boundary`](../src/dev/map_authoring_region/region_snapshot.gd)). Cosmetic foliage collision-none is a proposed default, not permission to remove collision from existing trees.

**Ownership:** Editor may place approved catalog wrappers; runtime/data-schema and shared asset changes require map/runtime owners.

**Test data:** Existing Sunmane pass4 reused 12 cosmetic wrappers (checkpoint (review archive: `work-output/sunmane-steppe-implementation/pass4/checkpoint.md`)); useful sparse-placement fixture, not a dense-grass performance proof.

## A3 Water beyond ellipses

**Decision:** Build later after A1/A4/A10: explicit polygon-water contract and composer/preview/collision parity together. Build read-only shared-plan water display first; do not directly edit `diagonal-plan.json` from regional tools.

**Contract:** Existing `WaterRegions` controls support translation-only ellipses: stable id, optional `replacesPlanFeatureId`, name, center `[x,z]` metres, level Y metres, positive radii and nonnegative depth reference ([`_water_region_records`](../src/dev/map_authoring_region/region_snapshot.gd)). Depth does **not** reshape an authored lake bed; saved resolved terrain owns it ([`apply_plan`](../../eloria-assets/maps/nymara-regions/_continent/authoring.py)). Polygon rings/holes/flow fields and ranges are not implemented; freeze their version before UI writes them.

**Consumer:** Rivers use local `points[].position` as water-surface XYZ and `width` as full width; composer converts to continent X,Z,Y and half-width ([`apply_plan`](../../eloria-assets/maps/nymara-regions/_continent/authoring.py)). Proposed default: retain clicked surface elevation, expose explicit channelDepth 1.45 m/terrainFeather 5.5 m rather than silently subtracting bank depth; current [`_apply_river_effect`](../src/dev/map_authoring_region/terrain_control.gd) carves to surface minus depth. Full shared water must be displayed as context, including unclaimed plan features.

**Validation:** Current polygon input fails “shape must be ellipse” ([validator](../../eloria-assets/maps/nymara-regions/_continent/authoring.py)); rivers require channelDepth/valleyWidth/bankHeight. [`export_collision`](../../eloria-assets/maps/nymara-regions/_continent/collision_export.py) blocks water depth strictly greater than .35 m above the standing surface.

**Ownership:** Scene water only after explicit replacement migration; shared topology, mouths/joins and plan claims remain map-team reviewed.

**Test data:** Grey Moors tributary, headwater tarn and pool; [water export fixtures](../../eloria-assets/maps/nymara-regions/_continent/tests/test_water_export.py). Verify full extents and .35 m threshold, not just control points.

## A4 Cliffs and plateaus

**Decision:** Build now as an existing-control stamp: Add/Set terrain patches for editable plateaus; sparse sculpt for freeform strokes. No new cliff-mesh kit contract.

**Contract:** `Terrain/Patches/<id>` is `MapAuthoringTerrainPatch`, ellipse/rectangle, enabled bool, local transform, positive size metres, feather ≥0 metres; Add/Set operation. Node Y is the authoritative metre delta for Add and target height for Set, not an independent stored proxy ([`terrain_patch.gd`](../src/dev/map_authoring_region/terrain_patch.gd)). Example: Set, 30×20 m, Y=25 m, feather=6 m. Sparse sculpt stores base-bound indices/deltas instead (A10).

**Consumer:** [`TerrainControl._apply_patches`](../src/dev/map_authoring_region/terrain_control.gd) sorts by patch_id, applies Add or weighted Set, then path earthworks are applied; [`snapshot_record`](../src/dev/map_authoring_region/terrain_patch.gd) emits `terrain.patches` and resolved heights.

**Validation:** [`_validate_terrain_patches`](../src/dev/map_authoring_region/region_snapshot.gd) rejects tilted/singular XZ transforms; supports yaw and XZ scale. A plateau does not force walking: .65 grade, water, structural clearance and ownership still apply. It cannot represent caves/overhangs, which require existing mesh assets. Reuse sculpt's protected-border rules in a new stamp UI; patch schema alone does not enforce that strip.

**Ownership:** Editor writes local patches/sculpt; original heights, seam anchors, source meshes and ownership stay map-team controlled.

**Test data:** [terrain sculpt fixture](../tests/test_terrain_sculpt.gd); add a disposable Set-plateau fixture and verify Add/Set order, exact untouched border and resolved collision slope. Do not run source-saving editor fixtures against production scenes.

## A5 Named places

**Decision:** Existing landmark records may be edited through their current marker contract. Build later a dedicated visible place-label feature after A9, with client label rendering and naming policy agreed together.

**Contract:** `Gameplay` landmark markers already emit stable id, local position, calculated serverTile and label/JSON extras; `name` can exist in extras ([`_gameplay_records`](../src/dev/map_authoring_region/region_snapshot.gd)). Example existing-style record: `{id:"well", name:"Old Well", position:[20,4,10]}`. No point/polygon place-label schema, importance tier or zoom-range contract is implemented. Do not reuse landmark `type` casually: legacy collision stamps interpret some landmark types physically.

**Consumer:** [`authored_gameplay`/`apply_gameplay`](../../eloria-assets/maps/nymara-regions/_continent/authoring.py) publishes landmarks. [`build_continent_map`](../../eloria-assets/tools/build_continent_map.py) derives region names from `asset.name`, alongside image framing and ownership—not from landmark names. [`ContinentMap._draw`](../src/ui/continent_map.gd) draws territorial labels. Cartography JSON includes geometry/frame metadata, not merely pixels decoded from minimap.webp. Pure display labels need no server change; gameplay navigation labels would need a separate decision.

**Validation:** Existing marker IDs must be unique; reserved coordinate fields cannot be replaced by extras ([`authored_gameplay`](../../eloria-assets/maps/nymara-regions/_continent/authoring.py)). No label tier/zoom validator exists; maximum text/localization rules unknown.

**Ownership:** Editor local markers; map team generated cartography/manifest and shared place-name policy.

**Test data:** Four Gates landmark vs region label: changing a disposable landmark name must not be represented as automatically adding a tab-map label.

## A6 Lights, particle effects and sound emitters

**Decision:** Runtime support exists for manifest lights and limited ambience. Build later the scene-to-snapshot authoring bridge; generic particle presets, schedules and chunk budgets require a new contract.

**Contract:** Manifest `lighting.markers[]`: id string, position float[3] local metres, color float[3] or color string, energyHint float (default 2.4), rangeHint metres (14), shadows off. [`LightMarkerBinder.apply`](../src/world/light_marker_binder.gd). `environment.ambientAudio[]`: id, loop catalog string, gain linear float (.5), optional nodePrefix, radius metres (60); example `{id:"falls",loop:"<existing catalog id>",nodePrefix:"Waterfall_",gain:.4,radius:45}`. [`AmbientAudioBinder.apply`](../src/world/ambient_audio_binder.gd) loads WAV loops; no prefix means flat audio, not spatial region geometry.

**Consumer:** [`main._bind_ambient_audio`](../src/app/main.gd) and [light binding](../src/app/main.gd) recreate map-owned roots. Do not promise per-chunk lifetime: these are map bindings, not arbitrary streamed emitters. The authoring snapshot's [section list](../src/dev/map_authoring_region/region_snapshot.gd) has no lights/audio/effects section. Code-created gameplay/weather particles do not establish map particle-preset support.

**Validation:** Unknown loop warns “ambient audio loop not in the catalog”; malformed light positions are skipped. No finite/range/budget/schedule snapshot validator exists for these sections. Do not serialize unsupported fields and imply they work.

**Ownership:** Existing manifest declarations remain map-team owned until dedicated source controls/exporters land; editor must not patch generated manifests.

**Test data:** [test_ambient_audio.gd](../tests/test_ambient_audio.gd), [test_world_lighting.gd](../tests/test_world_lighting.gd). Verify map reload cleanup and unknown loop behavior; add streamed lifetime coverage before new schema acceptance.

## A7 Walkability overrides

**Decision:** Build later, last of this list. No current arbitrary force-walk/force-block authoring contract. A proposed first extension should only subtract walkability; do not offer unconditional force-walk.

**Contract:** No painted mask/polygon field is consumed. Current [`export_collision`](../../eloria-assets/maps/nymara-regions/_continent/collision_export.py) samples 0.5 m collision centres, checks grade ≤.65 or valid deck support, water depth ≤.35 m, structural actor clearance, finite heights, ownership and explicit seam/gate allowances. It writes EWCG-v2; zero remains blocked. Proposed future blocked regions would apply after all opening rules, never create support or expand ownership. Storage format remains unknown pending that implementation.

**Consumer:** Existing [`open_walk_surfaces.open_package`](../../eloria-assets/maps/nymara-regions/_toolkit/open_walk_surfaces.py) is a separate legacy package rewrite that opens exposed mesh decks, not a brush API; [`stamp_solid_landmarks.stamp`](../../eloria-assets/maps/nymara-regions/_toolkit/stamp_solid_landmarks.py) closes selected landmark boxes. [`rebuild_continent_geography.geometry`](../../eloria-assets/tools/rebuild_continent_geography.py) runs opening then stamping then guard. Do not mix those rewrites after a new override without explicit precedence. Server needs final published collision/height data and existing frame metadata, not editor strokes.

**Validation:** No override validator exists; silently accepted extras would not prove movement behavior. Proposed reject force-walk over water/structure/outside ownership, rather than granting an escape hatch.

**Ownership:** Editor future source controls only; map team owns collision exporter, legacy-tool ordering and publication.

**Test data:** [test_collision_export.py](../../eloria-assets/maps/nymara-regions/_continent/tests/test_collision_export.py): grade/water/deck/structure fixtures. Add precedence tests only when override contract is implemented.

## A8 NPC walking paths

**Decision:** Build later, after a dedicated server patrol feature. Static NPC placement exists; NPC-marker patrol/wander routes do not.

**Contract:** Server `NPCDefinition` (`eloria-server/eloria/npcs.py`) stores name, map_id, integer x/y logical server tiles, role/dialogue/appearance/actor_type/vendor fields. `load_npcs` (`eloria-server/eloria/npcs.py`) accepts `npc | name | map | x | y | role | portrait | dialogue [| vendor]`; no route points, loop mode or wait fields. Do not place invented patrol data in marker extras. Future route frame should be explicitly logical tiles, with metre conversion in the exporter, but version/fields remain unapproved.

**Consumer:** `World.load_configured_npcs` (`eloria-server/eloria/world.py`) instantiates static NPCActor records. `animal_loop` (`eloria-server/eloria/world.py`) handles creature wandering/combat; it is not an NPC patrol consumer. Client ambient wildlife movement likewise does not prove server NPC-route support.

**Validation:** Loader rejects incorrect column count with “expected npc | name | map | x | y | role | portrait | dialogue [| vendor]”; world rejects unknown maps. It does not validate an unimplemented route or all points against collision. A future implementation must validate segments/reachability, not just endpoints, and define blocked/dynamic-obstacle behavior.

**Ownership:** Editor can maintain existing approved marker positions; server owner must add route lifecycle/data publication before editor writes paths.

**Test data:** Disposable NPC text fixture with one static actor; confirm position loads and extra route columns fail. No production NPC source saves or server runs were performed for this research.

## A9 Map annotations

**Decision:** Build later, after A2 in the sequence below; no date is committed. This is proposed editor-only review storage, not an implemented format.

**Contract:** Proposed unreferenced sibling `<region>.editor-notes.json`: `{schema:"eloria-editor-notes-v1",regionId:"verdant_stair",notes:[{id:"review-001",position:[77,20,-36],text:"Check apron transition",status:"open"}]}`. UTF-8 JSON; local metre position float[3], stable nonempty id, plain text, status open/resolved. Author/time fields optional only after team agreement; text length limit unknown. It must not be a resource referenced by the scene, a Gameplay marker or a snapshot dependency.

**Consumer:** Editor review dock only; no runtime, server or bake consumer. [`_collect_dependencies`](../src/dev/map_authoring_region/region_snapshot.gd) follows ResourceLoader references; [`export_region`](../src/dev/map_authoring_region/region_snapshot.gd) explicitly constructs exported sections. An unrelated sibling JSON is not exported by that code. The editor implementation must add a packaging exclusion for the proposed notes before claiming “never ships.”

**Validation:** No validator exists yet. Proposed editor errors: unsupported schema, wrong regionId, duplicate IDs, nonfinite position, nonstring text, invalid status; do not attempt to “fix” positions into another territory silently.

**Ownership:** Editor/review team owns notes sidecar; map team owns runtime schema. No authority to rewrite source heights, scenes or generated files while resolving comments.

**Test data:** Disposable scene copy plus notes. Expected snapshot document/dependencies/GLB/collision hashes identical with and without notes; separately verify shipping export excludes sidecar. No production bake is needed to design this format.

## A10 Heightmap import

**Decision:** Build now using a bound sparse sculpt layer; do not overwrite original base buffers or apply unreviewed terrain migrations. Image import itself does not exist yet.

**Contract:** Base sidecar is raw little-endian float32, exactly width×height×4 bytes, absolute Y metres; x varies fastest, index `z*width+x`; sample X/Z = origin + index×cell_metres ([`_load_base_heights`](../src/dev/map_authoring_region/terrain_control.gd), [`_point`](../src/dev/map_authoring_region/terrain_control.gd)). No implicit image vertical scale: import dialog must require explicit metre range/offset and mapping. Replace computes target minus original base at editable samples. Offset adds image deltas to existing sculpt deltas. Both persist to `terrain.sculpt_layer`, leaving protected/excluded samples and original base bytes exact. Layer binds base SHA256, origin, grid_size, cell_metres; sorted PackedInt32 indices and finite PackedFloat32 deltas, |delta|≤4096 m ([`validation_error`](../src/dev/map_authoring_region/terrain_sculpt_layer.gd)).

**Consumer:** Existing patches and path shaping still apply after the sculpt layer, so an imported target image is not guaranteed to equal final resolved heights. [`apply_to`](../src/dev/map_authoring_region/terrain_sculpt_layer.gd) adds deltas. Snapshot exports sculpted base then resolved patches/roads/rivers ([`export_region`](../src/dev/map_authoring_region/region_snapshot.gd)).

**Validation:** Stale base/grid, duplicate/out-of-range indices and nonfinite deltas fail explicitly. Reuse [`boundary_fields`](../addons/map_authoring_workspace/terrain_sculpt_tool.gd): lock outer two rows/columns, outside ownership and within two terrain cells of ownership edge; fade next two cells inward. Layer validation alone is not border protection.

**Ownership:** Editor new sculpt resource/local reference; map team original sidecars, grids, frames and approved ownership.

**Test data:** [test_terrain_sculpt.gd](../tests/test_terrain_sculpt.gd), then disposable 2×2 known image resampled onto a larger fixture: verify row orientation, explicit metre conversion, stale-hash rejection, undo/reopen and byte-identical protected samples.

## B1 Group tags

**Decision:** Exists already; node group tags are acceptable in production scenes.

**Contract:** `metadata/map_authoring_group = "group-01"` is a Godot Node metadata string. Keep wrappers directly under `AuthoredAssets` and markers within `Gameplay`; do not introduce grouping parents. Distinguish Node metadata (`set_meta`) from the wrapper's exported `metadata: Dictionary`, which **is** serialized.

**Consumer:** Incoming [`group_tools.group()`](../addons/map_authoring_usability/group_tools.gd) uses `set_meta`. Task [`region_snapshot._object_records()`](../src/dev/map_authoring_region/region_snapshot.gd) and `_gameplay_records()` (545) enumerate explicit fields; neither reads that Node tag. Thus geometry/gameplay output ignores it, but saving the scene changes its provenance hash in `sources`—“never changes an export” is too broad.

**Validation:** Non-wrapper children of `AuthoredAssets` fail with “production assets must use MapAuthoringAssetControl wrappers.” There is no snapshot schema for the group-tag value.

**Ownership:** Editor may write these Node tags and undo them. Do not put UI grouping into exported asset `metadata`.

**Test data:** Group two disposable wrappers plus a marker, export before/after: object/gameplay records must match; only source hashes may differ. Save/reopen must retain tags and direct parents.

## B2 Copies and IDs

**Decision:** Supported fresh-ID copying exists. Build the Ctrl+D duplicate-ID warning/redirect next in editor code; do not silently regenerate certified originals.

**Contract:** [`commit_copies()`](../addons/map_authoring_usability/group_tools.gd) assigns fresh asset/marker strings, empties `runtime_bindings: Array[Dictionary]`, and remaps `follow_asset_id` to a copied asset or `""`. Marker IDs unique across Gameplay are a useful **stronger editor convention**: [`_validate_unique_ids()`](../src/dev/map_authoring_region/region_snapshot.gd) validates each exported section separately, with the narrowly retained Manymouth `stelae-court` pair exception. No required `-NNN` naming grammar exists beyond nonempty stable IDs.

**Consumer/validation:** Snapshot exports markers and bindings via `_gameplay_records()` (545); duplicates fail “contains duplicate id …”; missing followed assets fail “Follow Asset Id … does not exist.”

**Caveat/ownership:** Copies currently retain `default_spawn`, destination fields, `linked_node_name`, and extras. Clear `default_spawn` on new copies; fresh IDs and empty bindings alone do not make cloned gameplay semantics valid. Editor owns warning/copy safeguards; map team defines destination/link/extra reset policy. Never clone a runtime-point certification automatically.

**Test data:** Disposable asset+follower copy must follow its copy; follower-only copy must not follow the original. Copy a default spawn and assert the copy is nondefault after that safeguard; this is a required new regression, not current behavior.

## B3 Model library folder

**Decision:** Keep the drop-in folder; production admission remains conditional. Fix `.gltf` handling before claiming all listed formats are bakeable.

**Contract:** [`asset_catalog._scan_library()`](../addons/map_asset_palette/asset_catalog.gd) builds `library:<relative-basename>` entries under `res://assets/world/library/`; `.gltf` companion copying is at 179–205. Wrapper `scene_path: String` names the resource; `source_node: String` is empty/`.` for its root or an existing source node; `collision_role` is `none|solid|walk_surface`. No extras registration is inherently required. Prefer self-contained static GLB, Node3D root, metre-scale geometry and PBR textures. Transform the wrapper, not imported `Content`.

**Consumer/validation:** [`_baked_source_record()`](../src/dev/map_authoring_region/region_snapshot.gd) passes GLB/**glTF** through, converts native scenes with `GLTFDocument`, and binds hashes. However [`authoring._validate_objects()`](../../eloria-assets/maps/nymara-regions/_continent/authoring.py) rejects direct `.gltf`: “bakedSource.path must be a static GLB.” Paths must resolve inside the checkout and be hash-bound; preview success is insufficient. Scripts are not a runtime-map contract. Surface overrides reject arbitrary shaders/triplanar materials (`region_snapshot:778`); supported PBR and the certified road shader are exceptions. No universal import-size budget was found; [`export_map_asset_library.py:198`](../../eloria-assets/tools/export_map_asset_library.py) has extractor-specific 80 m dimensions and a manifest byte budget (default 50 MiB, line 269).

**Ownership:** Editor owns library/import validation. A universal required Godot import preset, file-size cap, material-count limit or LOD budget is **unknown/not centrally enforced in the inspected admission path**; the recommendations above are not verified mandatory rules. Current category heuristic (`region_control.prepare_palette_asset:132`) gives structure/interactive/landmark `solid`, otherwise `none`; treat it as editable suggestion, not certification. `walk_surface` needs explicit choice. Map team approves collision impact.

**Test data:** Native-scene export fixture in `test_continent_authoring_framework.gd`; add direct `.gltf` rejection/normalization coverage. [`package_client.py:102`](../tools/package_client.py) includes all resources and does not exclude this folder; actual release packaging was not run.

## B4 Markers in prefabs

**Decision:** Assets-only now; gameplay prefabs later, after the B2 reset rules and round-trip tests. No promised delivery date.

**Contract:** `world_authoring/prefabs/<name>.tscn` is an editor template; placement expands members into ordinary authored wrappers. The template itself is not a new snapshot section. Future marker members must instead enter their appropriate `Gameplay` container with fresh IDs, no certified bindings, nondefault spawns, reviewed destination/link/extras, and copied-asset follower remapping.

**Consumer/validation:** There is an actual enforcement gap: [`prefab_library.capturable()`](../addons/map_asset_palette/prefab_library.gd) checks ownership/ancestry, **not** asset type. [`commit_with_undo()`](../addons/map_asset_palette/prefab_library.gd) refreshes IDs only for asset wrappers and puts every member under `AuthoredAssets`. A marker passed through this path triggers the snapshot's “production assets must use MapAuthoringAssetControl wrappers” rejection (`region_snapshot:367`). The UI's assets-only description is not a sufficient filter.

**Ownership:** Editor owns enforcing that filter/warning now, before adding marker-prefab support. Map team owns gameplay semantics and binding admission.

**Test data:** Disposable mixed asset/marker selection must reject or explicitly exclude the marker before saving a prefab; two asset members must place as separate wrappers with fresh IDs and localized material overrides. Do not exercise this on preserved production scenes during integration.

## B5 Extending roads and rivers

**Decision:** Exists already for ordinary editable paths; map-team coordination is required for owned routes, replacement rivers and seam receiving tails.

**Contract:** [`_finish_extension()`](../addons/map_authoring_usability/path_draw_tool.gd) changes only Curve3D points, preserving ID/surface/properties/replacement claims. Points are path-local metres transformed to territory-local metres by snapshot. Widths are **full** widths in metres (editor setters clamp positive values to .5–16); [`width_path._on_curve_changed()`](../src/dev/map_authoring_pilot/width_path.gd) aligns retained per-point widths; new zero entries mean inherited/interpolated width. Preservation is not proof of unchanged connectivity.

**Consumer:** [`_path_records()`](../src/dev/map_authoring_region/region_snapshot.gd) exports paths; `authoring.replace_routes()` (1001) replaces entire claimed composer routes, converting widths to half-widths. `authoring.apply_plan()` (826) applies owned water replacements. Shape-terrain-off remains off; it does not certify new portions as traversable.

**Validation:** `authoring._validate_paths()` (382) rejects fewer than two controls/nonpositive widths, wrong road/water replacement kinds and duplicate route claims. Snapshot rejects undeclared claims and unsupported tilt/nonuniform XZ scale. These checks do not guarantee safe receiving tails or water continuation.

**Ownership/Test data:** Editor may extend unclaimed disposable paths. Map team owns shared-route changes. Test both ends with varying widths, undo/redo, `terrainConform=false`, then compare retained width anchors and exact semantic fields; do not extend live owned routes merely to test UI.

## C1 Which grid the server walks

**Decision:** Exists already, but neither proposed file is directly the runtime authority. The server loads the generated **ELM height field** from the configured data root (`eloria-server/config/eloria/server.txt:32`, `/opt/eloria-data`, unless an explicit environment override is present). `eloria-server/eloria/collision.py:315 load_elm_collision` decompresses gzip if needed, reads `elmf`, dimensions `tile_x*6 × tile_y*6`, and copies the height bytes at `height_offset`; `load_collision_maps:376` resolves each configured map filename. It does not read client EWCG on a player's move.

**Contract / consumer:** For all twelve exterior territories, the source is the published package `collision.bin`: `eloria-assets/maps/nymara-regions/<id>/collision.bin`, except Four Gates at `eloria-assets/maps/four-gates/collision.bin`. `eloria-server/tools/collision_sources.py:262 SOURCES` lists these exact mappings. `server-collision/<map>.bin` is for composed interior/gauntlet maps, not these twelve exteriors (`_composed:258`). Current exterior source files are EWCG-v2, uint8 rows/columns, 0.5 m cells, with `world.json.collision.{originMetres,heightEncoding,gridAlignment}` and `coordinateTransform.serverOrigin`. Logical server tiles are **1 metre**, integer `(x,y)`; positive tile Y goes north while local positive Z goes south. Physical upper-left storage origin is `(-serverOrigin.x,+serverOrigin.y)` for the current zero-minimum maps. Cell centres are `(x0+(column+.5)*.5, z1-(row+.5)*.5)`. One logical tile covers four half-metre cells; its metre centre is `(tileX+.5-originX, originY-tileY-.5)`. Storage minima must never be treated as moving this immutable logical frame.

`collision_sources.Source.load:202`, `resample:119`, `requantise:138`, then `sync_authored_collision.build:871` / `choose_stage:763` produce checked-in `tools/collision/<id>.escg.gz`. Any blocked covered sample blocks the tile; otherwise take the maximum height. For `tile-centres-v1`, samples are exactly `[2y:2y+2,2x:2x+2]`; older alignment uses its explicit historical shift. Requantise decoded metre heights relative to the lowest walkable height: `round((h-min(h))/0.2)+1`; stage selection then coarsens into 1–63. Strict authored exports avoid legacy opening/repair routines. The paired client `export_contracts.py:387 fold_server_grid` uses this same actual server quantisation/stage code.

`eloria-server/tools/authored_collision.py:24,54,75` defines gzip ESCG-v1 (`<4sHHI`: magic/version/stage millimetres/square cells), one byte per logical tile. `eloria-server/tools/generate_nymara_maps.py:519–542` loads those grids and copies `grid.at(x,y)` into `maps/nymara/<id>.elm`. The ELM carries the code, not the original world-height origin/stage metadata. An ESCG stage represents terrain-height quantisation, not a runtime metre-height reconstruction contract.

Current checked-in exterior inputs (all minima `(0,0)`, all 1 m logical tiles; EWCG width and height are twice the listed side):

| Territory ID | Logical square side | `serverOrigin` tiles | ESCG stage metres |
|---|---:|---|---:|
| amberwood | 426 | (242,182) | 1.8 |
| amethyst_barrens | 738 | (182,166) | 1.6 |
| crownwater | 774 | (294,114) | 0.4 |
| four_gates | 594 | (310,164) | 0.8 |
| grey_moors | 750 | (224,326) | 2.6 |
| manymouth_delta | 510 | (208,310) | 0.6 |
| mirrorhold | 540 | (208,350) | 3.0 |
| ssarathi_ruins | 780 | (376,244) | 1.0 |
| sunmane_steppe | 792 | (194,292) | 1.4 |
| verdant_stair | 702 | (298,164) | 1.6 |
| westhaven | 588 | (174,244) | 0.8 |
| whitehorn_range | 708 | (362,360) | 4.8 |

Values were read from the actual gzip headers and published `world.json`, saved in QA `current-grid-inventory.json`; they do not claim the new scene edits have been republished. No ELM/world rebuild occurred during the twelve visual passes.

**Validation:** EWCG reader rejects wrong magic/version/truncated payload (`collision_sources.py:67`); ESCG reader rejects magic/version/truncation/dimension mismatch (`authored_collision.py:54–82`); ELM rejects `not an ELM map` / `invalid ELM height-map range` (`collision.py:324–330`). New source storage checks reject frame/minimum mismatches; actual signed-source publication remains blocked until validity-based persistence migration exists (`client publish_diagonal_continent.py:898`).

**Ownership:** Editor consumes grids read-only. Map team owns generated EWCG/ESCG/ELM, coordinate/storage metadata and publication. **Test data:** all twelve above plus `tests/test_collision.py`, `tests/test_collision_sources.py`, and client `_continent/tests/test_export_contracts.py:test_fold_requires_each_of_four_actual_subcells`. A zero in any of four samples must block the one-metre tile.

## C2 Step rule

**Decision:** Eight-neighbour/no-corner-cut exists; the proposed height and timing interpretation needs correction now in editor parity work.

**Contract:** `CollisionMap.can_step` (`eloria-server/eloria/collision.py:146`) requires valid walkable start/end and **`abs(end_code-start_code) <= max_walk_height_change`**, currently 2. It compares integer ELM bytes, not decoded EWCG metres; no extra quantisation tolerance or diagonal height allowance is added. `World.step_allowed:3879` / `find_path:3934` also require both orthogonal moves from the same starting tile when diagonal. Example codes 11→13 pass, 11→14 fail; a diagonal whose orthogonal tile is blocked or exceeds the same code limit fails. Generated exteriors use the per-map stages in C1, so a universal 0.4 m terrain climb is incorrect even though legacy comments call ELM units 0.2 m.

The shipped server setting is **600 ms walking / 200 ms running** (`eloria-server/eloria/settings.py:17`, `eloria-server/config/eloria/server.txt:26`), not 250 ms. `normal_move_interval_ms=250` is creature pacing. `World.player_step_seconds:4437` halves the chosen pace for Speed Hax or haste; `await_player_step:4453` multiplies by `hypot(dx,dy)` (diagonal √2) and uses an absolute next-step deadline. These are server logical-tile steps, not 0.5 m preview-cell steps.

**Consumer / validation:** `World.move:5548` uses authoritative path search. Editor `df50cd77c addons/map_authoring_usability/playtest_walker.gd` currently has `.25`, `.4`, `SERVER_CELL=.5`, height tolerances and a coarsened preview AStar. It is an estimate, not server-equivalent. **Ownership:** editor team should consume the final server-folded grid/config and label live/EWCG routes estimates until parity is implemented; map team owns fold/config contract. **Test data:** `tests/test_collision.py:test_large_height_changes_block_steps_but_not_destination_walkability`, step-mask parity tests, and both orthogonal-corner fixtures. Timing tests must distinguish walk/run/haste/diagonal; no live speed claim.

## C3 Height codes

**Decision:** Confirmed for **EWCG decoded visual height only**; not a substitute for server ELM step codes.

**Contract:** `client collision_export.py:285 encode_heights` returns uint8 0 for blocked/out-of-range; valid codes 1–255 decode to `heightEncoding.origin + code*heightEncoding.step` in local metres. Step is `max(.2,(high-low)/253)`, origin `low-step`, encoding uses `numpy.rint`. The EWCG binary has no embedded metre encoding: read the matching `world.json` too (`export_collision:386–390`). Example code 10 with origin −1 and step .3 means 2 m; code 0 remains blocked, never −1 m ground.

The server's `CollisionMap.walkable:111` tests `(byte & 0x3F) != 0`; `elevation:115` returns the full byte for a walkable tile. Current generated maps intentionally use only codes 1–63, with 0 blocked. The final map's code step is C1's stage; absolute local height was rebased and must not be guessed from ELM alone.

**Consumer / validation:** EWCG overlay may use metre decoding for drawing, while authoritative path parity compares final ELM codes. Exact source/manifest association is required; reject stale/missing versioned metadata instead of assuming an origin. **Ownership:** generated codes/encoding are map-team output. **Test data:** `test_collision.py:test_elm_zero_height_cells_are_unwalkable` and `collision_export` encoding/reproducibility fixtures; low-six-bits-zero is blocked in ELM even if an upper byte bit is set.

## C4 Other server rules

**Decision:** Exists already; an offline preview cannot promise all live conditions.

**Contract / consumer:** `World.collision_for` / `is_walkable` (`eloria-server/eloria/world.py:3834–3870`) account for mover footprint/clearance. `blocking_tiles` and `walk_blocked:5525` add actor/NPC bodies and other portal tiles; path search approaches an occupied target to a neighbouring tile rather than walking onto it. Non-target walkway portals are excluded so a route does not leave its map early. `move:5548` carries a map/coordinate epoch token, interrupts harvesting, and ends on a portal transition. `check_portal:5690` distinguishes automatic walkway crossings from object portals requiring explicit `portal_intent`; `use_map_object` handles distance and gated interactions. `change_map` and coordinate admission validate destination support and map state.

Runtime collision can differ from the bare ELM: `collision.py:337 with_storage_collision` stamps storage-body footprints, `apply_walkable_floor_overrides:361` applies specific legacy floors, and tutorial/gauntlet systems can rebuild gates. Current occupancy is session/world data. The current `move` loop snapshots `occupied` for its route; do not claim arbitrary time-varying obstacle replanning beyond what the code does. Wading depth and structural/grade ownership rules are already baked; runtime does not re-query scene water every step. Seams need reciprocal lane/portal mapping and destination collision, not simply walking off an EWCG edge.

**Validation:** Unreachable search produces `You cannot reach that location.`; an occupied route tile produces `That tile is occupied.` (`world.py:5568,5591`). Offline live doors/quests/occupancy are **unknown** without server state. **Ownership:** editor can show static estimates and authored portal markers; server/map team owns dynamic state and crossing/door contracts. **Test data:** signed-storage path fixtures, storage collision fixtures, exterior connection and portal path tests; verify a non-target exit does not steal a route and an object portal is not triggered by incidental walking.

## C5 Live walkability estimate

**Decision:** Exact exported-mesh algorithm exists. Matching it is editor work after it can reproduce emitted mesh classification/transforms; bounding boxes must stay explicitly approximate.

**Contract / consumer:** `client _continent/collision_export.py:136 _mesh_groups` walks final exported GLB hierarchy, applies full node transforms, considers only triangle primitives, identifies solid roots by `manifest.collision.nodeNames`, and walks by `manifest.navigation.surfaceNodePrefixes` (defaults Terrain_/Walk_). An actual `Walk_` ancestor supports a deck; names containing ceiling/soffit/underside/roof are excluded from support and remain structural where declared. Source `collisionRole` alone is insufficient without the exporter’s emitted subtree semantics (`authoring.py:1592`).

For walk surfaces, `export_collision:366` calls `_toolkit/glb_reader.py:136 rasterise`: upward triangle normals must exceed `1/sqrt(1+.65²)-1e-9`, cells sample at their centres using barycentric triangle height, and take the highest eligible face. Deck support requires height ≥ terrain−.03 m; it replaces standing height and allows that surface despite the ground's slope.

For solids, `structural_mask:253` does triangle-vs-actor-prism separating-axis intersection (`triangle_prism_overlap:209`), including vertical and edge-on triangles, at each 0.5 m cell. Horizontal prism half-size is .25 m in X/Z; vertical range is **standing+.06 through standing+2.10 m**, not +2.16. `ACTOR_HEIGHT=2.1` is the top above standing; floor clearance is subtracted when calculating prism thickness. Closed meshes also use signed winding at standing+1.05 m to block their interiors (`closed_mesh:187`, `_ray_crossing:231`). A pen/fence therefore blocks its actual rails/walls, not automatically its entire bounding rectangle, while a closed solid blocks its inside. A roof above the actor band leaves an archway open.

The final half-cell additionally requires finite height, terrain grade ≤.65 unless supported by a valid deck, depth ≤.35 m below sampled water, and ownership or a specifically allowed halo/collar (`export_collision:357–381`). Decks never override solid or submerged checks. Then C1 folds all four half-cells conservatively. Ownership halo/collar are certified map-team contracts, not a brush override.

**Validation / ownership:** Preserve final GLB provenance and manifest identity; fail unsupported frame/minimum combinations before generation (`validate_storage_frame:318`). Editor owns its estimate; map team owns final raster/certificates. **Test data:** `_continent/tests/test_collision_export.py` has `test_arch_roof_above_head_does_not_block_the_doorway:130`, `test_a_tall_closed_solid_blocks_its_interior_not_just_its_walls:141`, `test_thin_edge_on_wall_is_not_lost_by_a_vertical_raycast:148`, bridge/water and half-cell fold fixtures. These must agree before calling a live overlay exact.

## D1 Dark terrain preview

**Decision:** Cause **unknown**; diagnose before choosing a fix. Do not retint source materials to compensate for an unmeasured editor/game mismatch.

**Contract/consumer:** Incoming [`time_of_day_preview.enable()`](../addons/map_authoring_usability/time_of_day_preview.gd) applies `WorldEnvironmentBinder` and `DayNightBinder` using the manifest; it refuses scenes with saved lighting. [`top_down_capture._map_environment()`](../addons/map_authoring_usability/top_down_capture.gd) floors ambient and disables fog. [`plugin.levelled_minimap()`](../addons/map_authoring_usability/plugin.gd) separately brightens the dock image toward mean luminance .4, factor clamped 1–6. That is compensation, not evidence of the cause. Captures remain unlevelled.

**Validation:** No measured material/lighting/colour-space diagnosis was established here. Preview and packaged terrain use different rendering paths; that alone does not identify a defect.

**Ownership:** Editor team owns controlled preview/renderer comparison; map team assists with material/export correspondence. Any source-shader or exporter fix needs shared ownership.

**Test data:** Use one frozen region, identical renderer, manifest/time, exposure, camera and neutral reference material; compare raw preview against the corresponding published geometry. Current source edits may be newer than its package. Working captures should match the declared source scene under a fixed rig; runtime-parity captures need a separately matched published baseline, not automatic brightening.

## D2 Minimap source

**Decision:** Published-image contract exists. Keep the live authored minimap for editing; add a clearly labelled “last published” comparison later if useful. Replacing it entirely would hide unpublished source edits, including these twelve passes.

**Contract:** Package `world.json.minimap`: `worldMin/worldMax` are numeric `[X,Z]` local-metre corners; `pixelsPerMetre=p>0`; `imageSize=[W,H]` positive integer pixels; north-up, top-left at worldMin. Full-image pixel-edge coordinates `(u,v)` map to `(x,z)=worldMin+(u,v)/p`; sample centres add `.5`. For `cartography.regions[].tabMap.region=[cx,cy,cw,ch]`, cropped pixels add `(cx,cy)` first. Y comes from terrain, not the image. Atlas pixels use a separate continent frame.

**Consumer/validation:** [`MapPicture.extent()`](../src/world/map_picture.gd) applies this crop; [`map_view.configure()`](../src/world/map_view.gd) adds camera margin/buffer, not image remapping. `build_continent_map.tab_map_crop/crop_world` (145/161) generates framing. [`render_region_cartography.frame()`](../../eloria-assets/tools/render_region_cartography.py) rejects invalid extents or disagreement between `(max-min)*p` and imageSize.

**Ownership:** Editor may read packages; map team regenerates images/cartography, never the editor by hand.

**Test data:** Westhaven published frame is min `[-170,-336]`, max `[202,240]`, `372×576`, p=1, crop `[0,0,372,576]`; pixel edge `(170,336)` maps to local `(0,0)`. `test_cartography.py:54` additionally verifies a nonzero crop and clamping. No imagery is proof of collision or current shared-water completeness.

## E1 Baseline

**Decision:** This document accompanies integration of accepted client task commit `b99a8a22e` with editor develop `df50cd77c1a4c1b176097006bd834dc2d2516aa0`. The accepted source and contracts land in the commit containing this file; verify that history with `git log`. The final delivered response and release checkpoint record the verified pushed OIDs. This is code/source integration, not deployment or a world rebuild. Paired server integration commit: `7e13e7956523ab258f8514cf122902bed128e217` (accepted server task `045f741` integrated with server develop `e4a2043b3de6a7f2d0573b0ffebead60a381add1`).

**Contract / ownership:** The client repository includes both `godot-client` and `eloria-assets` pipeline/source dependencies, including shared-field-v1 bytes. Explicit reviewed allowlists are 189 client paths and 33 server paths, plus this reviewed contract-response document and the approved four-line fixture correction in `godot-client/tests/test_terrain_sculpt.gd` (explicit 8×8 storage dimensions and origin) on integration. Primary checkouts remain untouched; isolated worktrees combine incoming editor/clock work with our accepted inactive contracts and twelve partial visual passes. The repository history and separate release checkpoint identify the resulting revisions.

Independent A-section UI with disposable fixtures can proceed; anything reading/writing ownership, storage, base/sculpt or snapshot contracts should use the merged baseline, not clean old develop. Source-minimum migration, selected topology activation, exact clipping integration, complete profile publication, validity-based persistence migration and integrated continent validation remain unfinished. The coordinate capability remains off; nonzero-min publication fails closed. Landing code is not activating those features or publishing maps.

**Test data:** `integration-plan.md` lists bounded required suites and `accepted-path-manifest.json` preserves exact input paths/hashes. The release checkpoint records the final focused verification results and merged OIDs. No unsafe sculpt-editor test in shared maps; no full continent generation.

## E2 Sculpt editor test

**Decision:** Build/fix now, **editor-tools owner**, before any further windowed harness use. The reported ten baseline failures are supplied history, not a newly rerun result. We deliberately did not execute the unsafe test on shared scenes.

**Contract / validation:** `df50cd77c godot-client/tests/test_terrain_sculpt_editor.gd` creates `sculpt_editor_fixture`, calls `open_scene_from_path(SCENE_PATH)`, waits two frames, then takes `get_edited_scene_root()` and merely checks root/terrain non-null. It does not assert the active scene path/region identity before later unconditional `EditorInterface.save_scene()`. `_expect` records failures but keeps executing. The fixture is absent from the real territory catalog, so its intended editable binding fails; a previous production scene can remain active and be saved. Fix with an isolated catalog fixture and editor state; wait/verify exact `scene_file_path == SCENE_PATH`, expected region ID and root identity; abort before input/save on mismatch; ensure all written paths remain under the fixture directory. No test-only production catalog entry or weakened source checks.

**Ownership:** Editor team owns this test/plugin fixture plumbing. Map team reviews any production catalog/source-contract change; production source scenes are never test fixtures. **Test data:** disposable integration fixture only. A missing/wrong active scene must exit before save and preserve a sentinel source hash; valid catalog setup should exercise the real brush/undo/save/reopen path. Reproduction/fix results remain pending until an explicitly safe harness is run.

## E3 Priority

**Decision:** Root's chosen order: **A1, A4, A10, A3, A2, A9, A5, A6, A8, A7**. First fix E2 and existing-copy/prefab admission guards as prerequisite maintenance. Begin with ground-region painting and existing sparse sculpt/stamps; height import must be non-destructive. Polygon/shared-water work follows after explicit source authority is agreed. Arbitrary force-walkable across hard constraints is not planned; authoritative terrain/collider correction is preferred.

**Ownership:** Editor team builds brushes, UI, safe fixtures and authored-control ergonomics. Map team owns any new snapshot/schema/base-storage contract, water/ownership authority, collision/export/publisher changes, route/landmark reconstruction and integrated validation. Foliage budgets/instancing, runtime names/effects/NPC routes need their respective runtime owners and explicit designs. These are priorities, not authorization to begin every schema/runtime feature in parallel; no calendar date is committed for later features.

## E4 Windowed checks

**Decision:** Existing source scenes may be inspected read-only, using the same bounded isolated QA discipline; unsafe harnesses are not allowed against the shared checkout.

**Contract / ownership:** All twelve `godot-client/world_authoring/regions/<id>/<id>.tscn` scenes have fresh normal saved-scene bake and fixed-rig source-preview evidence. Prefer a disposable integration checkout with clean editor state. For a source-team checkout, arrange its freeze/slot, hash before/after, do not save, disable/test no path that calls editor save, do not pack transient/generated preview nodes, and do not rewrite resources. Use external approved Godot, CPUs0–3, numerical workers1, hidden bounded JobObject (≤120s) for automated capture; only one Godot job at once. A visible interactive editor window is for an explicitly requested manual check, not an excuse to alter scenes or duplicate lighting. No foreign process inspection/termination.

**Test data:** Existing source-only captures and normal CLI bakes under `work-output/region-visual-redesign-2026-09-26/`; the latest two are Verdant `after/` and Westhaven `after-v2/`. Fixed neutral rig is exposure .85, sun1.2, ambient.45. These are saved-source previews, not runtime/seam acceptance, and shared ocean/neighbor water can be absent. Source drift or new diagnostics fail the QA comparison. No region is a disposable fixture; E2 must be fixed before using its harness anywhere with a production scene open.
