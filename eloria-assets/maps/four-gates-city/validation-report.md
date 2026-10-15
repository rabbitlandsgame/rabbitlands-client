# Validation report

Validated 2026-08-27 for asset version 0.9.0.

## Passed

- LOD1 GLB header is `glTF`, version 2; declared and actual length both 2,992,552 bytes.
- LOD2 GLB header is `glTF`, version 2; declared and actual length both 851,056 bytes.
- JSON parses successfully and names `four-gates-city.glb` exactly.
- LOD1 contains 1,750 unique named nodes; compact LOD2 contains 663.
- Every landmark, district, gate, portcullis, bridge, collision, and navigation node referenced by JSON exists exactly in the GLB.
- All primitives use indexed triangles with float32 positions and uint32 indices.
- Materials use glTF metallic-roughness, alpha blending, emissive factors, and baked atlas UV rectangles; no proprietary extensions or broken external texture paths exist.
- Seven PNG maps are embedded: the citywide base-color/normal/ORM atlas and landmark base-color/normal/ORM/emissive family.
- Every visible primitive provides `POSITION`, `NORMAL`, and `TEXCOORD_0` attributes.
- Every normal-mapped primitive also provides a portable `TANGENT` attribute.
- Seven standard glTF animation clips reference existing nodes and valid translation or scale channels.
- Ten principal/district convex navmesh polygons, two exclusions, and one sanctuary off-mesh link use documented asset coordinates.
- Seventy major-building obstacles provide conservative navigation blockers.
- Eight water channels, plunge pools, foam surfaces, and mist locators are present with stable programmatic names and loader metadata.
- The deterministic close-detail contract contains 267 `Detail_` nodes across gate, civic, market, residential, vegetation, and waterfall families; all are absent from LOD2.
- All principal cardinal routes retain a 30 m half-width visual-clearance zone, and central planting stays clear of the player start.
- LOD2 retains only referenced meshes, materials, textures, images, accessors, and buffer views; embedded overview textures are capped at 512 px.
- Scene root, coordinate system, units, origin, bounds, gate approaches, spawns, paths, and camera targets are explicit.
- Collision proxies are separate from visible meshes and align by construction.
- Static transforms remain coherent when animation and custom effects are disabled.
- Twenty requested verification cameras/renders and one generated architectural reference sheet are included.
- The portable 1536×1536 collision grid contains both blocked and walkable terrain, preserves all four causeways, blocks the central monument, water channels, and final building footprints, and keeps all required gameplay anchors walkable.
- The portable manifest contains four portals, six NPC markers, three creature spawn zones, four harvestables, five gameplay regions, and eight waterfall effect stacks whose node names resolve in the GLB.
- `four_gates.dds` is a client-readable 512×512 uncompressed BGRA DDS with exactly four mip levels.

## Independent-validator/viewer status

The 0.9 package passes local binary/container, embedded-image, accessor-bound, metadata cross-reference, detail-count, route-clearance, portable-runtime, and collision checks. The 0.8 geometry/material base passed Khronos glTF Validator at 0 errors and 0 warnings for both assets; its machine-readable reports remain checked in beside the GLBs as the independent baseline. The PR's Godot importer/render gate validates the added standard glTF mesh and instances in the target engine; refresh the standalone Khronos reports before tagging 1.0.0.

Pull requests that change Four Gates run an independent Godot/Xvfb render and upload aerial, gameplay, central-plaza, south-gate, market, and waterfall screenshots. Blender, Babylon.js Sandbox, or Don McCurdy's glTF Viewer inspection remains recommended before tagging 1.0.0.

## Release-gate limitations

- Major gate towers, domes, bridge arches, cliffs, radial gardens, market props, and inner-ring vegetation now use authored modular topology and baked atlas UVs.
- Bespoke district unwraps and production water/mist/energy shaders remain future work.
