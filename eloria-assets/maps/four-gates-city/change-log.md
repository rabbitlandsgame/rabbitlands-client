# Change log

## 0.9.0 — 2026-08-27

- Added 267 deterministic gameplay-distance detail nodes aligned to the canonical concept art while preserving 30 m half-width clearance around every cardinal route.
- Layered integrated aged-gold crowns, sapphire tracery, and hanging standards onto all five traversable gate structures.
- Added eight radial civic planters, bespoke low-poly broadleaf shrubs and inner-ring trees, market stock/sign dressing, residential balconies, and roof finials.
- Integrated each waterfall into the shoreline with rock clusters and stepped foam ribbons that remain readable when client effects are disabled.
- Kept the compact LOD2 unchanged at 663 nodes by pruning every `Detail_` node and its now-unused broadleaf mesh resources.
- Restored the lost 0.8 polish step and art-directed generator inputs to the rebuild pipeline, and advanced portable-package guards to 0.9.0.
- Expanded Godot/Xvfb visual evidence with central-plaza, south-gate, market, and waterfall close views.

## 0.8.0 — 2026-08-27

- Repainted the city and landmark atlases as restrained, seamless material swatches based on the concept palette; removed literal scene fragments that produced collage-like repetition in Godot.
- Baked each material's atlas rectangle into primitive UVs, eliminating the client importer's inconsistent `KHR_texture_transform` behavior and cross-material sampling.
- Reduced normal intensity, surface glare, and landmark emission so charcoal masonry, aged gold, turquoise water, and sapphire inlays retain the paintings' value hierarchy.
- Replaced cone mountains and crowns with deterministic faceted peaks, fitted snowcaps, and tiered evergreen silhouettes.
- Removed the validation overlay and calibrated neutral lighting in CI screenshots so visual review reflects the map itself.

## 0.7.0 — 2026-08-27

- Replaced the flat placeholder atlases with concept-derived 4×4 city and 2×2 landmark PBR source atlases matching the canonical warm limestone, charcoal slate, aged gold, sapphire, turquoise, and alpine-green palette.
- Removed the legacy dark per-material tint that multiplied textured surfaces into olive/near-black output in Godot.
- Rebuilt atlas resizing and normal derivation per UV cell to prevent cross-material color and normal seams.
- Replaced residential and farmhouse cone roofs with reusable gabled roof geometry and oriented district façades radially around the civic plan.
- Added 28 deterministic rock/snow peak pairs and 49 outer evergreens to reproduce the painted alpine skyline while preserving all four cardinal approaches.
- Added a server-independent Godot/Xvfb rendered validation job that captures aerial and gameplay map views for every Four Gates asset pull request.
- Revalidated LOD1 and compact LOD2 with the Khronos glTF Validator at zero errors and zero warnings.

## Portable runtime integration — 2026-08-26

- Replaced the all-walkable collision placeholder with terrain-, causeway-, water-channel-, monument-, and building-aware collision at 1536×1536 resolution.
- Exported the authored convex navigation polygons, sanctuary off-mesh link, and final building obstacle count into `world.json`.
- Added four portal hooks, six civic NPC anchors, three creature population zones, four harvest sites, and five tagged gameplay regions.
- Added eight loader-addressable waterfall effect stacks plus water, waterfall, and landmark-energy material animation parameters.
- Added a matching client-readable 512×512 uncompressed BGRA DDS map with four mip levels.
- Extended offline validation to reject missing effect nodes, malformed minimaps, out-of-bounds placements, and gameplay anchors on blocked collision.

## 0.6.1 — 2026-08-26

- Rebuilt both committed GLBs after detecting truncated binary chunks in the prior delivery.
- Added deterministic atlas fallbacks and a compact blockout seed so a clean checkout can reproduce the complete package.
- Normalized strict glTF material properties, removed empty child arrays, separated animation accessors from vertex-buffer targets, and added tangent attributes to every normal-mapped primitive.
- Pruned LOD2 metadata references to match the nodes actually retained by the distant model.
- Added package-integrity validation for container lengths, buffer bounds, embedded images, unique node names, and JSON-to-GLB node references.
- Rebuilt the truncated reference composite as a labeled contact sheet from all 20 verified source renders.
- Passed Khronos glTF Validator with zero errors and zero warnings for both LOD1 and LOD2.

## 0.6.0 — 2026-08-26

- Replaced the flat city plateau with authored concentric terrain terraces and a continuous irregular rocky shoreline transition.
- Reoriented and deepened the existing stable cliff nodes into tangent-aligned shoreline buttresses.
- Added eight radial water channels, eight plunge pools, eight foam surfaces, and eight loader-addressable mist emitter locators.
- Added explicit terrain elevation, shoreline, water-system, shader-fallback, and effect metadata.
- Rebuilt LOD2 with resource pruning and 512 px overview textures while retaining overview landmarks.
- Increased reusable unique mesh geometry from 2,682 to 4,310 triangles.

## 0.5.0 — 2026-08-26

- Replaced stable gate tower and roof nodes with authored multi-ring shafts and ribbed dome meshes.
- Added extruded structural bridge arches and subdivided irregular cliff-face modules.
- Added gate façade energy inlays using a dedicated emissive material.
- Embedded a dedicated 1024×1024 landmark base-color, normal, ORM, and emissive texture family.
- Added modular landmark UVs and 70 building-derived navigation obstacles.
- Increased reusable unique mesh geometry from 1,168 to 2,682 triangles.

## 0.4.0 — 2026-08-26

- Added district-specific civic halls, arcades, cupolas, residences, courtyards, farmhouses, granaries, irrigation channels, docks, and cranes.
- Added ring-road lamps and banners plus deterministic tree/trunk population outside principal routes.
- Expanded navigation from five principal polygons to ten principal and district walkable polygons with monument and wall exclusions.
- Added `four-gates-city-lod2.glb` and companion JSON; LOD2 reduces active nodes from 1,319 to 557 and removes animation and close-detail overlays.

## 0.3.0 — 2026-08-25

- Added thick pointed arch-ring and bronze-trim meshes to all five traversable gate structures.
- Added layered buttresses, finials, façade beacons, twelve sanctuary spires, and three plaza stair rings.
- Added five standard glTF portcullis clips and two energy-pulse clips with sensible static initial transforms.
- Added an inline principal-route convex navmesh with agent dimensions, slope limits, and a sanctuary off-mesh link.
- Replaced placeholder LOD notes with explicit suffix, screen-coverage, and fallback metadata.

## 0.2.0 — 2026-08-25

- Embedded 1024×1024 base-color, tangent-normal, and packed ORM atlases.
- Added normals and UVs to every reusable visible primitive using `KHR_texture_transform` atlas addressing.
- Added 239 detail nodes covering battlements, bridge parapets and piers, plaza furniture and lighting, market stalls, and farm fences.
- Preserved every loader-facing landmark, collision, navigation, interaction, and marker identifier.

## 0.1.0 — 2026-08-25

- Established canonical 720 m radial plan and elevation conventions.
- Added hierarchical LOD1 city, terrain, water, four gates, four bridges, plaza, sanctuary, districts, walls, effects, collision, navigation, and markers.
- Added versioned loader metadata and 20-view reference coverage.
