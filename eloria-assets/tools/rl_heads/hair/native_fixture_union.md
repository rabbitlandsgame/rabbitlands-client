# Evaluated Native Rest union

`NativeFixtureUnion(manifest, sex, case_names=None, optimize=True,
horizontal_slice_proof=False)` in `native_fixture_union.py`
loads complete body/scalp/shirt surfaces through the shared evaluated-fixture
reader, verifying every NPZ SHA. It requires fixturev2's `native_fixed_skull`
policy and zero High hair identity controls. Only Rest_Pose/fraction0 records
are authoring constraints; identical Low/Medium physical products are deduplicated
by mesh name and NPZ SHA. `records` identifies the retained cases.

`signed(points)` returns the minimum signed distance across the complete
surfaces and that limiting surface's closest point/outward normal. Do not replace
this with a mesh of detached changed-face patches: those can give invalid signs.
No positions, runtime controls or assets are changed. Native authoring still needs
the independent full evaluated checker across qualities, grooms, LODs and poses.
This preserves the mechanics used for the female Buzzed1674-case Native pass.

The optional query optimization leaves each complete surface intact. It reuses
a baseline closest triangle only when the bounds of every changed triangle
(before and after deformation) are strictly farther away. Compatible topology,
an identical repeated baseline witness, and a unique nearest triangle are
required. Edge, vertex, overlapping and spatially separate equal-distance ties
use the full query. Incompatible surfaces also use the full query.

Reused geometry never reuses another fixture's signed result or normal. The
fixture's own vertex normals reconstruct the interpolated normal and raw sign;
only then is that fixture's complete-actor outside-bounds proof applied. Planar
fixtures retain their original sign. This ordering matters when a distant face
change alters the actor bounds or shading normals without moving the closest
triangle.

Use `signed(points, optimize=False)` for the unoptimized reference query.
`last_query_stats` reports queried and conservatively avoided points. Small
queries automatically retain the full route when the extra baseline witness
would cost more queries than it could save. No fitting threshold, displacement
bound, fixture selection or independent qualification gate changes.

The optional complete-fixture horizontal-slice outside proof is explicit:
`NativeFixtureUnion(manifest, sex, optimize=False, horizontal_slice_proof=True)`.
Each retained fixture loads its own full, hash-verified physical triangles before
contact-region filtering. Its ordinary full signed query applies its own slice
proof. The existing default is unchanged. This initial optional route rejects
optimized queries until reused witness reconstruction has been independently
qualified against the same per-fixture proof. It does not alter distance,
closest point, normal, clearance thresholds or the total fitting bound.
