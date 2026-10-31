# Final surface-rooted ribbon details

`attach_surface_details.py --source <hair.glb> --out <fresh/hair.glb>` reattaches
two-column detail ribbons after final core geometry and grooming have settled.
Each root is projected onto an opaque exterior triangle. Fixed barycentric
parameters then give it the exact parent-root displacement for every identity
and grooming target, retaining the strand's relative motion. The optional
`hl_native_fit` follows each root column rigidly, preserving the parent's bound.
All linear control combinations keep their roots on the parent triangles.

The tool requires matching rigid skin influences at the roots and columns; it
fails rather than silently breaking a spring or mixed-influence attachment.
Core/cap primitives, all detail UVs, COLOR keep bands, skin and indices remain
exact. Source files stay untouched. The private receipt retains root parameters
and safe hashes; runtime extras contain no authoring paths.

This step changes detail positions and shape fields. Repeat clearance, strip
attachment, pose/headwear and actual-client appearance checks on the result.
It does not qualify or register a module, and is not applied to existing assets
automatically.
