# Human High portrait artwork

Ten shared face controls shape the existing Human body, eyes, brows and scalp
at every graphics tier. Neutral values restore exact original/refined mesh
objects. High adds optional detail without a new skeleton, animation, physics
shape, equipment variant or head draw.

Version 3 preserves the exact split source's 4K pigment and iris artwork. Lip
colour and roughness follow measured male/female mouth landmarks. Sculpt fields
refine lip, philtrum, nose, lid and tapered brow planes. Smooth source normals
cover the full frontal head independently of the stricter positional seam mask
and weld across coincident UV positions; the normal map adds fine relief.
These are interpretations of the supplied studies, not painted portrait matches.

The four head parts have 7,846 male / 7,592 female Head-weighted triangles versus
1,926 / 2,604 at Low/Medium: +5,920 / +4,988. Two adaptive splitting passes
prioritize eyes, nose and lips. Retained UV1/bone influences stay exact; midpoint
UVs and four/eight influences are interpolated and normalized. Shared edge
choices and a position-only field keep UV seams closed. Geometry delta is
exactly zero at neck, ears, rear skull and cap perimeter. The authoring clamp is
5.5 mm; final neutral/custom proofs measured retained-vertex deltas under 4 mm
and original seam gaps under 0.3 micrometres. Shared controls apply after the
canonical High refinement.

UV2 is measured once in canonical Head rest space and follows ordinary skinning;
paint never projects from animated/world position. Stubble uses original UV1.
Beards follow the same skin-point delta while preserving fitted anchors and
canonical coverage; the independent High hair finish may refine them afterward.
Downgrading restores exact incoming selected Mesh/Material objects.

Six 1024-pixel PNGs retain BPTC/mipmap import settings: about 4 MiB compiled per
sex, 8 MiB shared for both. Compressed CPU grids total 391,748 bytes (383 KiB),
decoding to 384 KiB per sex / 768 KiB both. Each 256-square sample has six bytes:
signed XYZ delta within +/-6 mm and XYZ source normal in [-1,1]. Descriptors own
range, dimensions, thresholds, landmarks and SHA-256. Gzip payloads use `.bin`,
which the client package filter includes. PNG/JSON/grids total about 3.46 MiB on
disk, approximately 4 KiB more than version 2. Raw high-poly/4K sources never ship.

The frozen reference fixture's four head parts use 396,212 decoded array bytes
at Medium versus 949,316 at High for Rowan/Tavi; Mira uses 437,300 versus 886,860.
A custom High face also retains a shared canonical derivative: approximately
1.81 MiB decoded arrays male / 1.69 MiB female before optional beard, plus shared
maps/grid. Decoded bytes are not a GPU memory estimate. Canonical cache is
bounded to eight meshes and finished derivatives to 24. Last-user downgrade or
removal releases High bundles, sculpt and mesh caches. Initial Low/Medium loads
none of them. Live actors can retain evicted mesh entries.

The final isolated Vulkan fixture held hair, animation and render policy at
Medium on an RTX 5080 Laptop GPU, 1280x720, 120 warmed frames. Median GPU time was
0.227 to 0.241 ms for sixteen bodies and 0.115 to 0.126 ms for a close head.
Sixteen actors with two distinct faces shared sixteen canonical/finished meshes:
3,672,352 decoded array bytes, 1,958,392 packed GPU stream bytes, 786,432 CPU
sculpt bytes and 8,388,768 compiled texture bytes. Their conservative CPU-plus-GPU
sum is 14.81 MB decimal, not a VRAM figure. After ten novel controls the bounded
caches held about 7.53 MB decoded arrays and 4.02 MB packed streams.

Novel High head processing measured 53-68 ms, separately from 21-34 ms for the
Medium actor update; cached High calls were 0.95-3.75 ms. Deformation runs only
on changes. Beard/equipment fitting can add work. Frozen reference quality
switches took 0.23-0.32 seconds including the independent hair finish. Initial
Medium configuration took 1.24-1.80 seconds for the first two source bodies and
0.24 seconds for a later cached male; those loads are not High processing costs.
These measurements describe this fixture and machine, not a universal bound.

Rebuild offline from the retained ignored `human_bodies_2026-10` folder:

```powershell
python godot-client/tools/bake_human_high_portraits.py `
  --root <task-client-checkout> `
  --sources <ignored-human-authoring-folder> `
  --stage <ignored-versioned-output-folder> --geometry-v3 --install
```

Sparse worktrees may supply `--tools-root <full-reader-checkout>`. The recipe
verifies source split hashes against runtime provenance, preserves inputs, and
records registration/output hashes in the ignored stage. Installation writes
only this data folder. The nearest-surface raw albedo experiment was rejected;
version 3 retains the clean exact source projection.

Import the PNGs with authored `.import` settings. Run
`tests/test_human_face_controls.gd` for shared fields/restoration,
`tests/high_portrait_appearance.gd` for High geometry/weights/seams/lifecycle,
and `tests/human_face_reference_preview.gd` for central presets, both tiers,
square-aspect front/side/three-quarter views and alternate light. Respectively,
`RL_FACE_CONTROL_OUTPUT`, `RL_HIGH_PORTRAIT_OUTPUT` and `RL_FACE_REFERENCE_OUTPUT`
select ignored evidence directories.
