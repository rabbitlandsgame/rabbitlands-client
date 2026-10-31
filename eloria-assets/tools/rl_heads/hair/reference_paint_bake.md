# Optional continuous reference paint bake

`bake_reference_paint.bake_chart_paint` accepts separate donor and recipient
position/UV/index arrays, an RGB/RGBA donor image, and a destination chart size.
It returns an RGBA NumPy image and a JSON-compatible receipt. It changes no
geometry, normals, joints, skin weights, morph payload or input array.

The recipient must already have an explicit, unique chart in `[0, 1]`. Repeating
shell-sector charts need separate packed islands first; keep each island's local
triangle mapping and duplicated seams. Conflicting overlapping recipient texels
fail closed. Existing authoring paths do not call this utility automatically.

`pack_chart_islands` optionally packs disconnected indexed charts into separate
tiles using positive affine UV transforms. This retains every triangle's local
mapping and orientation, including duplicated sector seams. It does not unwrap
a connected mesh whose UV chart overlaps itself; that needs an authored chart.

For every covered chart pixel, rasterization finds its physical recipient point.
The nearest nondegenerate donor triangle supplies barycentric UV coordinates;
bilinear sampling reads that donor triangle's actual paint in linear light.
UV `v=0` and image row zero both mean the top of the atlas. This avoids the
cross-island interpolation caused by projecting UVs only at recipient vertices.

Closed backing layers must retain the default `force_opaque=True`. The receipt
records donor transparency separately and the covered output alpha minimum.
Uncovered chart texels are opaque neutral gray; a small nearest-covered gutter
protects filtering. The receipt separates covered, unused and gutter texels,
reports unfilled covered texels, sampling orientation and physical projection
distance. It does not certify backing inset, attachment, silhouette, material
binding, grooming, coverage or visual quality; those remain independent gates.

Run `python test_reference_paint_bake.py` for the public two-island, orientation,
opacity and overlapping-chart fixtures. Source-specific forehead/temple evidence
belongs in ignored authoring stages, never in this repository.
