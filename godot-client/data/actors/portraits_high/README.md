# Human High portrait artwork

High graphics adds an optional, shared portrait layer to the two Human heads.
Low and Medium retain their exact current meshes, materials and source atlases.
No skeleton, animation, skin weights, triangle count or equipment fit is changed.

The six 1024-pixel maps contain reprojected 4K source albedo plus authored warm
and cool facial planes, lip pigment, sparse freckles and restrained brow strokes;
new iris fibres, pupils and a subtle limbal edge; packed eye/brow regions and
roughness; and normals transferred from the retained high-resolution Human
sculpts with small surface detail. This is a first painted portrait pass. The
current head silhouette and topology remain; this pass is available through the
High graphics setting for local review.

`HighPortraitAppearance` creates a compact High-only derivative carrying UV2
coordinates measured in the canonical Head rest frame. Those coordinates follow
the ordinary rig, rather than being projected from world position during an
animation. Source UVs, vertices, normals, skin weights, blend shapes and LODs stay
intact. Restoring Medium reinstates the exact source Mesh and Material objects.
The stubble pigment include uses the original source UV atlas at every tier.

The three maps per sex are shared between actors, use BPTC compression and have
mipmaps. Their compiled texture payload is approximately 4 MiB per sex, 8 MiB for
both. A tested head's four derivative surfaces use about 0.48–0.52 MiB of arrays;
the unused-derivative cache is bounded to 24 mesh resources. Last-user downgrade
or removal releases the High bundles and derivative cache. Low/Medium creation
does not load a High texture or allocate a High mesh. Extra pixel shading work
is restricted to this optional material pass; no draw, bone, physics or mesh
triangle is added. Crowd frame-time impact still needs a dedicated benchmark.

Rebuild offline using the retained ignored `human_bodies_2026-10` authoring folder:

```powershell
python godot-client/tools/bake_human_high_portraits.py `
  --root <task-client-checkout> `
  --sources <ignored-human-authoring-folder> `
  --stage <ignored-versioned-output-folder> --install
```

A sparse authoring worktree can supply `--tools-root <full-reader-checkout>`.
The recipe verifies the split GLB hashes against the runtime body's provenance,
preserves those inputs, and records the normal transfer's measured registration
error and output hashes in the ignored stage. Installing writes only this data
folder. The source meshes and original 4K textures are not runtime deliverables.

Import these six PNGs with their authored `.import` settings before previewing.
Run `tests/high_portrait_appearance.gd` using the normal production renderer; set
`RL_HIGH_PORTRAIT_OUTPUT` to an ignored directory. It exercises both heads at
three angles, exact quality restoration, initial Low/Medium allocation, unchanged
geometry and skin bindings, animation-stable UV2, and retained stubble pigment.
