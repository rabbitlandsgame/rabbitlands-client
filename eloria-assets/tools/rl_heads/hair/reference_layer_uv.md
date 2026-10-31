# UV charts for newly authored hidden reference layers

`unwrap_reference_layer.py` is an optional Blender background utility for a
newly authored hidden backing. It reads immutable NPZ `P`/`T` arrays and writes
only per-corner UVs, plus geometry hashes proving Blender did not alter triangle
positions or indices. It does not unwrap or rewrite the approved painted
exterior. Run it in a fresh factory scene with two threads; its output must be a
new file.

`reference_layer_uv.split_corner_uv(P, T, corner_uv, attributes)` splits the
recipient's attribute seams before skin or morph authoring. It copies supplied
normal/colour arrays and proves every indexed triangle corner remains exactly
equal to its source. The result includes safe geometry hashes, never source
paths.

The deliberately small Smart UV angle avoids overlaps found on concave closed
backings. Pack the resulting disconnected charts with
`bake_reference_paint.pack_chart_islands` before a continuous recipient paint
bake. This helper is not a certificate of a unique chart: the real bake's
overlap/unfilled-texel checks must pass. UV mechanics alone do not qualify
clearance, coverage, grooming, appearance or an asset for runtime use.
