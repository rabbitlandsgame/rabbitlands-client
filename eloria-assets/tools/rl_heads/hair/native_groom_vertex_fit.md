# Native grooming vertex corrective

`native_groom_vertex_fit.fit_vertices(native, P, targets, groom_cases=None,
margin_mm=3, max_shift_mm=14, initial_delta=None)` returns a single constant
POSITION delta and an explicitly unqualified, vertex-only receipt. `native`
provides `signed(points) -> distance, closest, outward_normal`; it can represent
one evaluated Native surface or a conservative union of complete fixtures.

Supply every target named by the requested grooming cases. The default checks
all nine length/volume combinations. Identical physical moves are deduplicated.
The fitter uses signed geometric separation, keeps POSITION-split seams on the
same displacement and projects solver updates into the unchanged total bound.
Unresolved contacts raise `NativeVertexFitFailure` with private diagnostic points
and a receipt. An explicit different style-local bound requires project review;
the generic default remains14mm.

Input High positions and target arrays are never changed. `initial_delta` can
seed a previously interpolated Native field; it is included in the total bound.
This utility performs no triangle-interior, pose, identity, coverage or attachment
qualification and writes no asset. Use the independent evaluated-fixture checker
and visual gates before registering a style.
