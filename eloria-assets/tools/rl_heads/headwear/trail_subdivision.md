# Optional cloth trail preparation

A single fit may set `trailSubdivision` before the existing headwear drape:

```json
{"maxEdgeMm": 30, "maxAddedTriangles": 8192, "maxPasses": 10}
```

It splits long edges only in triangles touching the fit's hanging-cloth mask.
Coincident geometric edges share split decisions, while separate UV corners
retain their own paint coordinates. Every old vertex row stays exact. New
positions, UVs, colours and skin influences are interpolated; joint IDs are
merged by weight, never averaged or silently pruned. Rigid crown triangles
keep the same surface. The ordinary draper then seats the prepared cloth and
computes its existing head/neck/shoulder weights.

The preparation is bounded by a 3–50 mm edge target, 1–16,384 added triangles
per source surface, and 1–12 passes. Invalid input, unsupported attributes,
excess skin influences or an exhausted bound retains that original surface
and emits a warning. No option means the unchanged old path. Successful
meshes expose an `rl_trail_subdivision` diagnostic and use the existing
piece/style/outfit/source mesh cache; this is never a per-frame operation.

An opt-in requires an actual resource render and cache reuse check. Pure
preservation checks run with `tests/test_headwear_trail_subdivision.gd`.
