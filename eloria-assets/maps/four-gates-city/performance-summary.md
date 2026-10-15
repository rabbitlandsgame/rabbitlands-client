# Performance summary

```json
{
  "nodes": 1750,
  "meshes": 42,
  "materials": 19,
  "animations": 7,
  "textures": 7,
  "textureMemoryBytes": 29360128,
  "glbBytes": 2992552,
  "lod2Nodes": 663,
  "lod2Meshes": 26,
  "lod2Materials": 17,
  "lod2TextureMaxResolution": 512,
  "lod2GlbBytes": 851056,
  "lod2SizeReductionPercent": 71.6,
  "uniqueMeshTriangles": 4538,
  "lod2UniqueMeshTriangles": 3676
}
```

Recommended budgets: desktop LOD1 under 1.5M visible triangles and 512 MiB textures; mobile LOD1 under 350k visible triangles and 192 MiB textures. The seven LOD1 embedded maps total approximately 28 MiB uncompressed. The close-detail pass adds only one reusable 88-triangle broadleaf mesh; most cost comes from instancing existing authored primitives. LOD2 embeds six resource-pruned maps capped at 512 px and is 71.6% smaller on disk than LOD1.
