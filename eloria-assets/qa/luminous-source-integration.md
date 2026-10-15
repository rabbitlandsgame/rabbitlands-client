# Luminous source models — 8 September 2026

The male and female Luminous player models now use reduced versions of the
approved original T-pose geometry. The Meshy rigged derivatives donate weights;
their reduced faces and collars are not used as the visual base.

| Model | Original triangles | Shipped triangles, including headwear | Joints |
| --- | ---: | ---: | ---: |
| Male | 1,937,266 | 35,158 | 77 |
| Female | 1,913,902 | 35,750 | 77 |

The models retain the source face, neck, collar, shoulders and clothing silhouette.
The female reduction reserves separate budgets for the head and eye region.
Original normals are transferred through the source UVs after reduction. No
procedural face morph, reconstructed neck, sleeve narrowing or global normal
smoothing is applied. Source-space trouser and upper-back weights are repaired
across welded copies before fitting. The torso uses physical hip centres rather
than the two rigs' differently placed pelvis bones. Head weighting is restricted
to the actual head/neck column, so T-pose shoulders cannot follow Head.

Seven independently editable RGBA textures per sex are in
`godot-client/assets/actors/native/race_textures/luminous_{male,female}`:
body, eyes, eyebrows, scalp, shirt, pants and boots. The alpha channel identifies
the group. Clothing also has neutral tint textures used by the runtime; the
original RGB crops are retained for editing. Each skin group samples its own
crop and maps into the shared face mask using its recorded UV scale and offset.
Skin, iris, brow, garment and hair appearance controls remain available.

The three existing hairstyles are fitted to each new skull. The broken cosmetic
headwear control is removed and its band/cap surfaces remain hidden. Equipped
helmets still work. Hair style and hair colour are independent named selectors:
four styles (including bald) and twenty colours. New choices use values 20–99 in
the existing hair byte (`20 + colour * 4 + style`); legacy values 0–19 retain their
appearance. The server stores and echoes that byte without a schema change.
The original source neck replaces the previous rebaked neck join.
Equipment retains its original author measurements in `authoredBodyGirth` and
`authoredFootAnchor`; `refittedBodies` identifies these two replacement wearers.
Other races retain their existing geometry and equipment fitting behavior.

## Reproduction

Run authoring processes on at most eight logical CPUs. Set process affinity to
mask 255 on Windows and set OMP, OpenBLAS, MKL and NumExpr thread limits to eight;
run Blender with `--threads 8`.

Source inputs live outside the client repository at
`generate_models/eloria-races-meshy/luminous_human_{male,female}_tpose.glb`.
The original SHA-256 values are recorded in the shipped asset catalog. Keep
these inputs immutable. The corresponding `_tpose_rigged.glb` files are donors.

1. `prepare_luminous_source.py` splits the original into seven texture groups
   and validates every triangle, position, normal, UV crop and decoded RGB pixel.
2. `reduce_luminous_source_blender.py` welds duplicate positions while retaining
   UV loops, then reduces the mesh. Use `--protect-face` for the female source.
3. `rig_luminous_source.py` restores source normals, transfers donor weights and
   fits the canonical Rest_Pose with `preserve_source_shape=True`.
4. Split the reduced and canonical results with `prepare_luminous_source.py`,
   reusing reduced triangle labels for the canonical model.
5. `integrate_luminous_sources.py --workspace <workspace> --client-root <checkout>
   --candidates <workspace>/work-output/luminous-body-repair/candidates`
   installs the reviewed `male/rigged` and `female/rigged` candidates. It rejects
   old candidates that lack the repair before fitting. It writes texture
   crops, masks, hair, headwear, equipment measurements and asset records.

## Original source-integration verification

- Independent comparison with both reviewed candidates: all seven groups retain
  their triangle indices, positions, normals, UVs and original texture RGB.
- Canonical rest pose and inverse binds match; each body replays 613 samples
  across Idle_Subtle, Walk, Run_Female and Fighting_Idle without verifier errors
  or warnings.
- All sixteen characters: 1,920 skin/eye combinations, 14,249 runtime assertions;
  equipment fitting, sockets, clothing and restore cycles: 23,162 assertions.
- Face-mask landmark, hair/collar, equipment-registry and native race geometry
  regressions pass. Source-replacement tests check the actual new geometry;
  shared-body tests continue checking the other fourteen characters.
- Actual client renders reviewed from front, side and back, with dark skin,
  hair, headwear, running poses and a complete equipped outfit. Artifacts and
  detailed verification records are in `work-output/luminous-install` in the
  authoring workspace. These are a source-preserving baseline; small source
  folds and facets remain visible at close range.

The initial clean Godot import also reports existing PNG-decoding problems on
unrelated equipment files. The selected outfit loads and renders through the
client's existing direct-image fallback. Runtime tests report only the sandbox's
unavailable user log/cache and system certificate store; no script errors.

## Body correction and customization verification

Current evidence is in `work-output/luminous-body-repair`, including matching
before/after close-ups, full running cycles, equipped views and the creation UI.
The measured front-trouser region has zero reversed triangles in both corrected
models, versus 180 male / 114 female before. Upper-back reversed-face fractions
fall from 0.92% / 1.67% to 0.48% / 0.77%; small source collar lips remain.
Positions, normals and UVs of the accepted head above the neck remain identical.
These checks inspect the serialized geometry and fail on the reported models.

- 22 body, hair/collar and canonical-equipment tests; 80 per-model subtests.
- 12 native race/registry tests; 1,593 subtests.
- Actual creation scene: all sixteen models, and all 80 independent hair choices
  on each Luminous sex, including rendered material tints and saved packet bytes.
- Appearance/helmet transitions: sixteen models, 809 checks, zero failures.
- Full Idle_Subtle, Walk, Jog, Run_Female and Fighting_Idle numerical replays,
  plus inspection of front/back rendered running cycles and equipped outfits.

The broad protocol suite still has two unrelated assertions failing: its known
capability list omits `magic_book_v2`, and its locomotion-facing expectation is
outdated. The new hair encoding/packet assertions pass. Render shutdown also
logs the existing texture cleanup warnings; no GDScript parse/runtime failure.
