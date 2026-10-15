# Shared equipment evidence

See [the delivery guide](../canonical-equipment-refit.md) for current scope,
measurements, validation and remaining limitations.

The `reproduction/` files record the scratch capture recipes. To execute them,
place them in `equipment-fit-build/shared-bodies/` in a client worktree and use
new output directory names. Their paths intentionally refer to that scratch
location. The public fitting/building tools are in `eloria-assets/tools/`.
Large capture cycles and editable Blender scenes stay in ignored local scratch;
`manifest.json` records their paths and hashes.

`neck-before-after.jpg` compares the prior visible throat fault with the final
installed client. Hair is enabled in the old screenshot and disabled in the
new close-up to expose the neck. Hair geometry and placement were preserved.
