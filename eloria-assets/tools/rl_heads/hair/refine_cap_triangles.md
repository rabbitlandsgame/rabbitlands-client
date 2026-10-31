# Conforming cap support before Native corrective fitting

`refine_cap(attributes, triangles, selected_faces, max_extra_triangles)` operates
on a cap-only mesh slice. It does not seat a surface or choose a skull.
Selected triangles split at their edges; adjacent faces receive conforming
splits, including POSITION-coincident UV-seam copies. A strict extra-triangle
budget fails closed.

Original attribute rows remain an exact prefix. New rows interpolate positions,
UVs, colours, arbitrary shape deltas and optional Native seed positions.
Normals use normalized interpolation. Skin influences must be identical along
each split edge, preserving the High posed surface for the current single-root
caps; unsupported variable influences fail closed. The caller must include
every target array and preserve its own part ranges when reassembling.

The result records old/new counts, edge splits, child/parent face mapping and
High surface-area parity. It does not change painted exterior vertices, native
fit limits, shader coverage or qualification gates. Retain High and Native
positions separately, then validate clearance, actual posed fixtures, all LOD
budgets and source appearance before accepting a corrective target.
