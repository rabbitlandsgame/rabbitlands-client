# Optional shell boundary rings

New profiles can confine root-coverage interpolation to a narrow rim without
increasing the density of the entire cap. Existing profiles omit both options
and retain the identical position, normal, UV, triangle and shading parameters.

`shell.boundary_rows: [0.97, 0.99]` adds normalized radial samples before the
existing scalp-ray construction. These follow the scalp's geometry and provide
an author-controlled radial grid.

`shell.boundary_ring_mm: [1, 2]` inserts physical samples after the existing
shell's face-clearance step. The new rows interpolate along each final last-row
edge at exactly one and two millimetres from its outer boundary. Existing outer
vertices/UVs are retained exactly. Normals and shading parameters interpolate
with the geometry; topology receives two narrow strips. The last original row
must be wider than the requested rim distances or the build fails closed.

The options are mutually exclusive. Both preserve the original boundary and
remain authoring-only; neither changes a runtime shader or its coverage gate.
Later source conformance or binding guards can move exported vertices, so final
fitted spacing and shader-equivalent scalp coverage still require measurement
at every LOD and grooming corner.

`test_shell_boundary_rows.py` covers unchanged defaults, unique normalized rows,
exact physical spacing, retained boundaries and invalid configurations. Local
actual-head parity checks additionally compare all six shell arrays against the
prior implementation on both sexes at three LODs.
