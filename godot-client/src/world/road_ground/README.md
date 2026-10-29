# Portable road ground

`road_ground.gd` consumes `roadGround: {metadata, sha256}` on a chunk manifest.
Its field format is `rabbitlands-road-terrain-blend-v1`: full-resolution 4 px/m
R8 coverage mips, a nearest RG8/RGB8 triangle-ID grid, and a full-precision affine
UV coefficient table. The selected source affine map supplies both texture
gradients and the road normal's orthogonal, handed tangent frame. No road mesh,
collision carrier, additional render pass or vertex/depth offset is created.

Loader API:

- `prepare(config, manifest_path)` decodes and checks portable fields, images,
  style/material contracts and the asset-tree resource closure without Nodes.
  Its `data` Resource retains private source texture candidates for publication.
- `bind(root, manifest, prepared)` rehashes the source closure before adopting
  texture identities and installing private existing-ground material overrides.
  Call after ordinary look materials and after clean native-cache capture.
- `rebind(root, manifest)` uses retained fields and shader sources for live look
  changes. It performs no field/source-file reads or source-closure hashing.
- `query(node, world_point)` finds the nearest chunk binding and returns raw
  bilinear L0 coverage and the selected style in its current rebased frame.
- `dependency_closure(config, manifest_path)` returns every checked loose file
  and digest for cache/packaging integration. Paths remain in `eloria-assets`.

The same road evaluation is blended before lighting in the Base and existing
local ground-patch passes, preserving patch alpha/discard. This avoids raised
patches hiding Base-only roads. Shared authored image slots and up to two style
factor/UV sets preserve current regional PBR and painting. Original mode uses
authored PBR; painted modes use the maintained paint/edge functions. Active biome
and soft-ground shader adapters preserve the current base material; explicit
`biomeBlend:null` remains authoritative.

Terrain supplies walking physics. Footsteps and grass consult the field only
for terrain hits, so structural bridges/decks retain their geometry and physics.
Visual ground has its ordinary millimetre layer offsets above terrain collision;
the former 55 mm road-only collision lift is absent. A producer/decoder error is
fatal for a required field. There is no fallback to missing road visuals.

`tests/world/test_road_ground.gd --roads PATH` exercises a compact producer
fixture headlessly. Rendering and performance still require the shared GPU
qualification on representative regions, raised patches and both renderers.
