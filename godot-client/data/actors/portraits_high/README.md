# Human High portrait artwork

High graphics adds an optional, shared portrait layer to the two Human heads.
Low and Medium retain their exact current meshes, materials and source atlases.
No skeleton, animation or equipment variant is added. High alone refines the
front head using the retained, registered high-resolution Human sources.

The six 1024-pixel maps contain reprojected 4K source albedo plus authored warm
and cool facial planes, lip pigment, sparse freckles and restrained brow strokes;
the original painted iris/pupil artwork within a narrower lid opening; packed
eye/brow regions and roughness; and restrained pore detail. The CPU sculpt grids
transfer lip/nose/lid planes and coherent source normals, including at neutral
face sliders. This remains a stylized game portrait, rather than the full source
sculpt or a replacement skeleton.

`HighPortraitAppearance` creates a compact High-only derivative carrying UV2
coordinates measured in the canonical Head rest frame. Those coordinates follow
the ordinary rig, rather than being projected from world position during an
animation. Original UV1 and skin influences stay exact on retained vertices.
Adaptive edge splitting adds 1,761 male / 1,766 female front-head
triangles; midpoint UVs and four/eight skin influences are interpolated and
normalized. Shared edge decisions and a position-only field keep duplicated UV
seams closed even when their normals differ. The field is exactly zero at the
neck, ears, rear skull and cap perimeter. Measured original-vertex displacement
is at most 1.57 mm male / 3.12 mm female in the reviewed presets, below the
5.5 mm authoring clamp. The facial-hair shell follows the same skin-point delta
while retaining its existing shader and attributes. Restoring Medium reinstates
the exact source Mesh and Material objects.
The stubble pigment include uses the original source UV atlas at every tier.

The three maps per sex are shared between actors, use BPTC compression and have
mipmaps. Their compiled texture payload is approximately 4 MiB per sex, 8 MiB for
both. The two compressed `.bin` grids total 380 KiB on disk and decode to
384 KiB CPU memory per sex; these are not GPU textures. Each grid is 256 square,
six bytes per sample: signed XYZ delta within ±6 mm, followed by XYZ source
normal in [-1,1], both encoded to unsigned bytes. The descriptor owns the path,
dimensions, range and SHA-256; the payload uses gzip compression with a `.bin`
extension included by the client package filter.

A tested head's four High surfaces use about 0.62–0.65 MiB of arrays. A custom
face also retains the shared canonical High body, bringing a single distinct
custom head's cache total to about 1.17–1.22 MiB. Canonical topology/normal-field
work is shared across sliders (eight mesh entries); finished derivatives are
bounded to 24 entries. New complete-actor jaw slider values measured 17–39 ms
clean-shaven and 47–84 ms with the full beard (including its existing grooming
rebuild) in the debug Vulkan preview. Cached preset updates were about 5–9 ms. The cold
first High application measured 0.11–0.17 seconds; none of this deformation runs
per frame. Last-user downgrade
or removal releases the High bundles and derivative cache. Low/Medium creation
does not load a High texture or allocate a High mesh. Extra pixel shading work
is restricted to this optional material pass; no draw, bone or physics shape is
added. Low/Medium never decode the sculpt or create a High derivative.

An isolated warmed 120-frame Vulkan comparison on an RTX 5080 Laptop GPU at
1280×720 held hair, shadows, LOD and animation policy at Medium. Sixteen full-body
Humans measured median GPU 0.228→0.231 ms; a close male head 0.113→0.120 ms.
The two distinct custom heads shared ten unique canonical/finished meshes,
2,498,456 bytes of decoded arrays and 1,333,796 packed GPU stream bytes. These
are fixture measurements, rather than an estimate for every device or scene.

Rebuild offline using the retained ignored `human_bodies_2026-10` authoring folder:

```powershell
python godot-client/tools/bake_human_high_portraits.py `
  --root <task-client-checkout> `
  --sources <ignored-human-authoring-folder> `
  --stage <ignored-versioned-output-folder> --geometry-v2 --install
```

A sparse authoring worktree can supply `--tools-root <full-reader-checkout>`.
The recipe verifies the split GLB hashes against the runtime body's provenance,
preserves those inputs, and records the normal transfer's measured registration
error and output hashes in the ignored stage. Installing writes only this data
folder. The source meshes and original 4K textures are not runtime deliverables.

Import these six PNGs with their authored `.import` settings before previewing.
Run `tests/high_portrait_appearance.gd` using the normal production renderer; set
`RL_HIGH_PORTRAIT_OUTPUT` to an ignored directory. It exercises both heads at
three angles, neutral/custom sliders, three eye and skin colours, rotated lights,
exact quality restoration after sliders/helmets/removal, initial Low/Medium
allocation, bounded geometry, UV-seam midpoint coherence, normalized skin weights,
animation-stable UV2, fitted facial hair and retained stubble pigment.
