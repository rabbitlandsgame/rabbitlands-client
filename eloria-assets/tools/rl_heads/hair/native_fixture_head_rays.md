# Evaluated head-only authoring rays

`native_fixture_head_rays.from_current_head_cases(head, manifest)` returns the
evaluated head geometry from complete v2 Native Rest fixtures, selecting exact
source `bodyCut.hiddenBodyTriangles` rows plus the native scalp. It verifies
source/body/fixture hashes, zero High IDs, vertex counts and per-row triangle
identity despite Godot's winding conversion. Duplicate evaluated head parts
are shared. Clothing and lower-body triangles cannot enter the ray envelope.

The returned object intentionally has no signed-distance API. Its P/N/T/mesh
are only for ray queries in a `NativeHeadSurface` adapter whose `signed()`
delegates to `NativeFixtureUnion`. That retains complete-fixture sign/bounds
semantics while providing a coherent outermost ray seed across Rest controls.
Full Native pose/control, High identity, coverage, budget and visual checks
remain required. Existing baseline extraction and defaults are unchanged.
