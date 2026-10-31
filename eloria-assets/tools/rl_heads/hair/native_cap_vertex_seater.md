# Optional bounded cap vertex seater

`native_cap_fit.fit_cap(..., vertex_seater=None)` keeps the existing radial
path unchanged. An explicit callback receives `(native, positions, center,
vertex_margin_mm, max_shift_mm)` at each refinement level and returns
`(seated_positions, private_receipt)`. It may choose a coherent local branch
before nearest-surface fitting.

The helper rejects non-finite or differently sized output, checks the total
displacement from the unchanged High positions and verifies the requested
vertex margin against the actual supplied collision surface. Existing face
support, refinement budgets, prefix preservation and final 2 mm checks remain
mandatory. This callback is an authoring hook, not a qualification or a style
default; final evaluated controls, poses and live client checks remain separate.
