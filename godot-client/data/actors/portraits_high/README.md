# Human High portrait artwork

Ten shared face controls shape the existing Human body, eyes, brows and scalp
at every graphics tier. Neutral values restore exact original/refined mesh
objects. High adds optional detail without a new skeleton, animation, physics
shape, equipment variant or head draw.

Version 5 builds on version 3's source-derived head form and 4K pigment. The
iris retains irregular source crypt/stroma detail, remapped around a defined
pupil and limbus with a warm inner collarette and darker outer ring. A tapered
almond aperture, continuous upper-lid rim, crease, canthus and lower waterline
anchor it in the face. Only the existing eye
patch receives curved corneal normal/specular response; covered lid pixels use
skin roughness. All of this uses the existing three maps per sex.

Measured male/female mouth landmarks anchor vermilion, the centre seam, corners
and philtrum. A bounded vermilion outline and outer Cupid-bow highlight retain
the source pigment. Lip/lid relief is at most 0.83 mm over the version 3 sculpt,
including a 0.65 mm reduction below the lower waterline. The male grid also adds
broad lateral cheek planes: up to 0.89 mm malar rise and 1.22 mm buccal hollow
after quantization. Those planes have zero influence across the central 60 mm
of the face and at the eye, ear and neck boundaries. The total bake clamp remains
5.5 mm. Lip colour/roughness remains readable through
skin choices. Smooth source normals cover the frontal head independently of the
stricter positional seam mask and weld across coincident UV positions. These
are interpretations of the supplied studies, not painted portrait matches.

Thin imported eye/brow cuts receive a continuous position-based damping of
sculpt XY to prevent local projected folds. High-owned outward normals use a
vertex marker to retain their facing across near-degenerate cuts. Inner mouth,
nostril and rear surfaces retain their original normal ownership. These High
repairs preserve the original lower-tier mesh objects and add no geometry.
The female canonical head also rounds the diagnosed outer nasal cut with a
shared-position solve capped at 2 mm. Its local normals follow the achieved
surface; the center, bridge, lips, interior and bindings stay protected. This
does not run on the male head. No vertices or triangles are added.

The imported male pigment also contained a false dashed cut below one eye.
The bake repairs exactly 19 audited RGB texels in the 1024-square projection,
using their immediate clean neighbours across the cut. A source-value/chroma
predicate must match the reviewed one-pixel footprint before writing. Alpha,
all other texels, eyelid/crease/freckle detail and the other maps/grids stay exact.
This cleanup does not modify source GLBs or lower-tier artwork.

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
sex, 8 MiB shared for both. Compressed CPU grids total 392,638 bytes (383 KiB),
decoding to 384 KiB per sex / 768 KiB both. Each 256-square sample has six bytes:
signed XYZ delta within +/-6 mm and XYZ source normal in [-1,1]. Descriptors own
range, dimensions, thresholds, landmarks and SHA-256. Gzip payloads use `.bin`,
which the client package filter includes. PNG/JSON/grids total 3,626,512 bytes
(3.46 MiB) on disk. Compiled texture memory,
decoded grid memory, topology and draw counts are unchanged. Raw high-poly/4K
sources never ship.

The frozen reference fixture's four head parts use 396,212 decoded array bytes
at Medium versus 949,316 at High for Rowan/Tavi; Mira uses 437,300 versus 886,860.
A custom High face also retains a shared canonical derivative: approximately
1.81 MiB decoded arrays male / 1.69 MiB female before optional beard, plus shared
maps/grid. Decoded bytes are not a GPU memory estimate. Canonical cache is
bounded to eight meshes and finished derivatives to 24. Last-user downgrade or
removal releases High bundles, sculpt and mesh caches. Initial Low/Medium loads
none of them. Live actors can retain evicted mesh entries.

The recorded version 4 isolated Vulkan fixture held hair, animation and render policy at
Medium on an RTX 5080 Laptop GPU, 1280x720, 120 warmed frames. Median GPU time was
0.226 to 0.241 ms for sixteen bodies and 0.115 to 0.130 ms for a close head.
Sixteen actors with two distinct faces shared sixteen canonical/finished meshes:
3,672,352 decoded array bytes, 1,958,392 packed GPU stream bytes, 786,432 CPU
sculpt bytes and 8,388,768 compiled texture bytes. Their conservative CPU-plus-GPU
sum is 14.81 MB decimal, not a VRAM figure. After ten novel controls the bounded
caches held about 7.53 MB decoded arrays and 4.02 MB packed streams.

That version 4 feature-pass run measured 49-125 ms for novel High head processing,
separately from 23-50 ms for the Medium actor update; cached High calls were
1.14-4.47 ms. CPU timing varies with other work and machine state. The topology
thresholds and counts are unchanged from version 3. Deformation runs only on
changes. Beard/equipment fitting can add work. The detail reference fixture
measured 0.18-0.22 seconds for full quality switches, including the independent
hair finish. Initial Medium configuration took 1.56/0.82 seconds for the first
male/female source bodies and 0.19 seconds for a later cached male; these source
loads are separate from High processing.
These measurements describe that fixture and machine, not a universal bound.
The final version 5 run of the same isolated fixture measured 0.225 to 0.240 ms
for sixteen bodies and 0.114 to 0.128 ms for a close head. The decoded arrays,
packed streams, texture and grid byte counts above remain exact. Novel controls
on warmed canonical geometry took 51–64 ms; cached High calls took 0.91–4.17 ms.
These compare the complete current High head against Medium; they do not
isolate version 5 from version 4 or predict a full-scene frame rate.

Rebuild offline from the retained ignored `human_bodies_2026-10` folder:

```powershell
python godot-client/tools/bake_human_high_portraits.py `
  --root <task-client-checkout> `
  --sources <ignored-human-authoring-folder> `
  --stage <ignored-versioned-output-folder> --features-v5 --male-cheek-planes `
  --repair-source-pigment --install
```

Sparse worktrees may supply `--tools-root <full-reader-checkout>`. The recipe
verifies source split hashes against runtime provenance, preserves inputs, and
records registration/output hashes in the ignored stage. Installation writes
only this data folder. Version 3 retained the clean exact source projection;
the current recipe remaps iris pigment and layers bounded lid/lip paint while
preserving the underlying source detail. The optional
RL_FACE_REFERENCE_DETAIL=1 preview setting gives close feature views under two
lights; RL_FACE_REFERENCE_PALETTE=1 adds three iris/skin combinations.

Import the PNGs with authored `.import` settings. Run
`tests/test_human_face_controls.gd` for shared fields/restoration,
`tests/high_portrait_appearance.gd` for High geometry/weights/seams/lifecycle,
and `tests/human_face_reference_preview.gd` for central presets, both tiers,
square-aspect front/side/three-quarter views and alternate light. Respectively,
`RL_FACE_CONTROL_OUTPUT`, `RL_HIGH_PORTRAIT_OUTPUT` and `RL_FACE_REFERENCE_OUTPUT`
select ignored evidence directories.

`tests/human_portrait_comparison.gd` renders High front and shallow three-quarter
busts for the supplied studies. `RL_HUMAN_PORTRAIT_OUTPUT` selects ignored evidence;
`RL_HUMAN_PORTRAIT_LOOKS` may name a local JSON dictionary of preset overrides.
