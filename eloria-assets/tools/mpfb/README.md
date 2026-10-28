# MPFB Human portrait prototype

This is an opt-in local authoring experiment for Rowan and Mira, using MPFB
2.0.18 and the MakeHuman CC0 system assets. It does not replace the model
registry, production actor assets, animation library or equipment files.
Originals, downloads, Blender files, textures, exports and evidence stay under
the ignored `.local/mpfb-prototype/` directory.

The first full-body fit exposed garment intersections. The review candidate
therefore uses the MPFB head and upper neck on the accepted Human torso and
hands. All 77 current skin joints, hierarchy, rest transforms and inverse binds
are preserved. Existing body refinement, height/build scaling, hair choices,
equipment fitting, weapon sockets and accepted animation curves remain active.
The production High face projection and source-specific sculpt are bypassed
only for a model explicitly marked `geometryProfile: mpfb`.

## Authoring dependencies

- Blender 4.2 or later; this study used Blender 5.2.1 LTS.
- [MPFB 2.0.18](https://github.com/makehumancommunity/mpfb2/releases/tag/v2.0.18),
  source tag `d0a32e5`. MPFB is a GPL authoring dependency, not a game dependency.
- [MakeHuman system assets](https://static.makehumancommunity.org/assets/assetpacks/makehuman_system_assets.html),
  CC0 pack SHA-256 `b542127a8e25547c7c29c19f2d1d2adb9a664c80396ecd694095dbc8028a0107`.
- Python with NumPy, SciPy and Pillow for offline packing/fitting.

The core basemesh, targets, skins, eyes and brows used here are CC0. No
third-party hair, paid generation or service is required. The selected
MakeHuman skin/eye/brow files retain their source provenance in local receipts.

Run `create_prototypes.py` in a fresh background Blender process with factory
settings and an isolated `BLENDER_USER_RESOURCES` directory. It loads the local
MPFB source for that process without saving or changing the user's installed
extensions. From the client root, supply explicit local paths:

```powershell
blender --background --factory-startup --python eloria-assets/tools/mpfb/create_prototypes.py -- --mpfb-source MPFB_SRC --assets SYSTEM_ASSETS --profiles eloria-assets/source/humans/mpfb/study-profiles.json --output .local/mpfb-prototype/authored
```

The output contains editable MPFB presets and Blender sources, evaluated body
and eye meshes, joint landmarks and original vertex ownership. Helper geometry
is excluded. The profile values are authoring targets, not wire protocol values.

Repack each sex's skin and bake its source brow pigment into the same atlas:

```powershell
python eloria-assets/tools/mpfb/bake_study_atlas.py --mesh .local/mpfb-prototype/authored/male.npz --metadata .local/mpfb-prototype/authored/male-mesh.json --output .local/mpfb-prototype/paint/male
```

Use the emitted NPZ **and** PNG together. The 1024-square atlas devotes more
texels to the head; it preserves geometry and eye UVs, needs one skin material,
and adds no runtime texture sample. Repeat with `female` paths.

Fit against the matching current native Human source; never overwrite it:

```powershell
python eloria-assets/tools/mpfb/fit_canonical.py --source godot-client/assets/actors/native/races/luminous_male.glb --mesh REPACKED_MALE_NPZ --metadata .local/mpfb-prototype/authored/male-mesh.json --mpfb-data MPFB_SRC/mpfb/data --skin-texture REPACKED_MALE_PNG --output .local/mpfb-prototype/fitted/male/luminous_male.glb --report .local/mpfb-prototype/fit/male.json --body-mode hybrid
```

Repeat with the female source/output. `--body-mode full` preserves the failed
full-body research route for further authoring; it is not the review candidate
and must not replace the validated hybrid exports. Fit reports and compact
landmark metadata accompany the runtime files. Keep the `luminous_male.glb` /
`luminous_female.glb` basenames: existing equipment fitting derives body identity
from them. Do not rename the shared rig or substitute MPFB's stock armature.

The fitter matches corresponding seam normals and feathers the head-side
normals over one centimetre. Match the two source skin colors offline too:

```powershell
python eloria-assets/tools/mpfb/match_neck_tone.py --input .local/mpfb-prototype/fitted/male/luminous_male.glb --output .local/mpfb-prototype/runtime/male/luminous_male.glb --texture-output .local/mpfb-prototype/paint/male-neck.png --receipt .local/mpfb-prototype/paint/male-neck.json
Copy-Item .local/mpfb-prototype/fitted/male/fit.json .local/mpfb-prototype/runtime/male/fit.json
```

Repeat for female. Keep the geometry-source fit report and final grade receipt
together: the grade changes only the embedded head PNG, not skinning or geometry.
Its five-to-sixty millimetre neck fade protects the face, ears, lips and brows,
and adds no runtime shader work or maps. The sidecar supplies measured face
landmarks to the preview. Runtime face sliders center their matching Rowan/Mira
preset on the already-authored MPFB targets, with both slider endpoints retained.

## Local review

The game no longer draws these studies (owner decision D2, 2026-10-28): the
MPFB High runtime (`mpfb_prototype_appearance.gd` and its shaders, the
`geometryProfile: "mpfb"` branches, `test-mpfb-prototype.bat`, the workshop's
MPFB model choice and the MPFB-only tests) was removed once the RL head, built
from the same MPFB/MakeHuman authoring (`eloria-assets/tools/rl_heads/`),
became the High Human head. These tools remain for authoring and reproducing
the studies; their outputs stay local, and earlier revisions keep the removed
preview and evidence fixtures. `test-human-customization.bat` remains the
ordinary preview; its workshop compares the RL head with the classic High head.

Use an isolated guarded Godot project/profile and `--offline-hud-preview`.
The portrait output directory is `RL_HUMAN_PORTRAIT_OUTPUT`; integration/cost
output is `RL_MPFB_REVIEW_OUTPUT`. Rendered comparisons must use the actual
export hashes, identical cameras and lights, and unretouched game pixels.

This is a geometry/material workflow prototype, not a production replacement.
Shipping an MPFB target library, Blender, subdivision, skin microdisplacement
or hair simulation is unnecessary; runtime consumes fitted static skinned
meshes and small atlases.

## Concept-led High refinement

The Human studies' front, side and three-quarter views define the High head,
neck and hair direction; see [art direction](../../../docs/human-character-art-direction.md).
Both clothing sets are useful references. There is no rear reference. The
older Eternal Lands character style limits do not constrain these surfaces.

The refinement uses `source/humans/mpfb/concept-profiles-v2.json` instead of
the first study profiles. Its evaluated MPFB topology is shared by every
identity of the same sex. The ten compact face parameters deform skin, lids
and eyes coherently once when appearance changes; they do not generate new
assets or modify animation tracks. `fit.json.head_shape_center` can specify
the authoring preset's slider center without hardcoding a different mesh per
identity. This is identity customization; facial expression/blink targets
have not been authored.

The additional offline stages are deliberately separate and preserve inputs:

The fitter trims the source at the true neck and joins it to the exact canonical
body rim with four rings of 96 samples. Connected edge order and a zipper join
preserve the annulus topology. A verified empty 256-square region of the same
skin atlas holds the new neck pigment; retained face/ear/internal UVs stay exact.
The earlier shoulder-derived patch produced folds and an hourglass throat and
is preserved only in ignored recovery records. Existing studies can use
`repair_neck_topology.py --input INPUT_GLB --output NEW_GLB --report REPORT_JSON`
before lower-face sculpting/painting; the native body already in primitive 1
supplies the canonical rim. Never overwrite the source stage.

1. `refine_concept_eyes.py` widens the eye opening with its lids and sclera,
   preserving the nose bridge, ears and scalp. The factor used is 1.30.
2. `refine_concept_lower_face.py` adjusts measured mouth/chin height without
   touching the canonical neck seam. It also updates mouth landmarks in the
   output `fit.json`, which grooming and the face controls consume.
3. `author_concept_hair.py`, run inside Blender, builds editable opaque clump
   curves from `source/mpfb/hair-concept-curves-v2.json`. Exported hair is one
   Head-local mesh/material per sex. Vertex alpha pins roots during bounded
   length/volume changes; it is not transparency. UV0 follows lock growth.
4. `face_landmark_audit.py` measures the exported anatomical anchors.
   `tests/mpfb_concept_portrait.gd` captures actual High portraits and projected
   mesh coordinates with reference-framed cameras. Portrait-only head yaw,
   pitch and roll never alter shared gameplay animations or skeleton rests.
5. `bake_concept_reference.py` uses those projections and original reference
   images offline. Face detail is a restrained residual over continuous skin,
   rather than opaque captured lighting. Hair has one 1024-square map in UV2,
   with separate guttered lock islands and directional highlights. RGB paint
   and pinned-root alpha remain independent.
6. `bake_neck_paint.py` uses the loft metadata to blend the retained head cut's
   pigment into the canonical body rim in the reserved atlas patch. Supply
   `--accepted-head-root` for an approved facial paint stage and `--hair-root`
   for accepted painted hair. Retained face/ear/internal pixels and other
   images stay exact; the new neck uses neutral mask alpha. No texture is
   added. Older non-loft recovery inputs use nearest native neck pigment with
   a protected fade below the face.
7. `bake_head_masks.py` packs disjoint brow/lip/stubble coverage into the existing
   skin PNG's alpha: 128 is neutral, the low range covers brows/lips and the
   high range covers stubble. An audited lip UV rectangle separates lips from
   brows. RGB and geometry remain exact. The opaque shader recolors brows with
   the hair palette, gives lips a restrained satin finish, and samples stable
   rest-UV stubble pigment. No extra map or draw is needed. Freckles and
   complexion detail remain authored paint.

Concept eyes use stronger iris recoloring with warm brown/olive defaults,
retaining the source luminance fibers, pupil and limbus. The stock eye maps'
two iris UV regions provide spatial coverage for dark, low-chroma pigment;
per-sex centers and protected pupils/whites remain stable through identity
sculpts. Linear-luminance normalization keeps the chosen color readable.
A bounded pigment
blend strengthens weak source brows through the existing anatomical mask;
the inner bridge and lip region remain excluded. These material changes add
no maps or geometry.

Each command's `--help` lists explicit input/output paths. Keep the archive,
downloads, editable Blender files, PNG studies, numbered exports, registration
JSON and receipts in ignored `.local/` storage. Rebuild projection maps whenever
geometry or framing changes; never reuse a stale camera map as final evidence.
Every paint/mask stage asserts unchanged geometry/rig/accessors. Native body,
equipment and animation sources must retain their hashes.

The prototype adapter accepts the sidecar's `concept_hair.styles` overrides
only in the opt-in preview. Other hair choices retain their existing sources.
Authored concept hair bypasses legacy sculpt/desaturation passes. Raw GLB
textures receive cached mipmaps once, keeping narrow painted locks and stubble
stable as their screen size changes. Mutable raw study textures are updated in
place to avoid retaining a second GPU allocation. There is no hair simulation.
Godot's material-directed glTF import moves the hair atlas's `texCoord=1` to
primary UV and retains growth coordinates in UV2. The authored shader follows
that imported layout; the validation fixture checks both channels against the
original GLB with a tolerance for engine vertex quantization.

`tests/mpfb_identity_validation.gd` checks three identities per sex, endpoint
and mixed fields, eye/skin correspondence, UV/weight preservation, grooming
toggles, repeated editing and identity persistence through accepted actions.
GPU portraits are required in addition to finite/Jacobian checks: a numerical
pass cannot approve a visible fold or paint seam.

## Refined concept study measured budget

The final male/female head and hair containers total **11,670,036 bytes
(11.13 MiB)**, an increase of **2.23 MiB** over the first MPFB pair. This includes
duplicated canonical bodies and wardrobes for the isolated trial. A future
head-only format reusing those assets is estimated at **5.51 MiB**, before
headers, metadata and alignment; that format is not implemented. Authoring
inputs and review images are excluded. Production packaging is unchanged
because these opt-in studies remain outside its registry.

On the RTX 5080 Laptop GPU, Godot 4.7.2 Forward+ at 1280x720 measured the
following median actor-viewport GPU times with sixty warm-up and 120 measured
frames per case. Camera, lighting, accepted idle animation and appearance
settings matched between models.

| Case | Current | Refined MPFB | Draw calls, Current / MPFB |
| --- | ---: | ---: | ---: |
| Sixteen bodies sharing two identities | 0.230 ms | 0.345 ms | 128 / 98 |
| Sixteen distinct customized identities | 0.268 ms | 0.255 ms | 128 / 98 |
| One close portrait | 0.104 ms | 0.097 ms | 8 / 7 |

Grid 95th-percentile GPU times were 1.301 / 1.315 ms for shared identities and
0.291 / 0.689 ms for distinct identities. These are isolated actor costs, not
full-game FPS measurements or a performance guarantee for other devices.
The larger grid renders 605,784 / 755,240 primitives. The authored hair uses
16,660 male and 20,576 female triangles, one opaque mesh/material each, with
no hair physics or new bones.

Unique bound mesh data was 3,258,350 / 2,986,610 bytes for shared identities
and 10,112,722 / 9,476,716 bytes for sixteen distinct identities. Bound texture
image data was 106,605,384 / 92,274,678 bytes in both grids. These are referenced
resource payloads, not total process VRAM; both modes' source caches coexist.
Four first-use face edits took 97-140 ms Current / 111-125 ms MPFB; repeated edits
took 5.3-7.1 / 4.9-6.0 ms. That appearance-function timing excludes deferred
GPU upload and the complete UI frame. There is no MPFB evaluation per frame.

The review captures cover all twelve available reference views, with actual
unretouched High renders. Shadow-free studio comparisons isolate silhouette
and pigment; separate shadowed captures are retained. Facial likeness and
paint still fall short of the concept art, especially hair clump regularity,
close-up neck shading and the eyes' expression. Expressions and blinks remain
future work. This is a locally testable prototype, not a production replacement.

## First prototype measured budget (historical)

The local pair of self-contained study GLBs totals **9,328,764 bytes** (8.90 MiB),
including copies of the existing body and wardrobe to keep the trial isolated.
Those files stay ignored and are not packaged. A future head-only format reusing
the current body and maps is estimated at **3.28 MiB** for both heads, eyes and
baked maps before container/metadata overhead; that format is not implemented.

On an RTX 5080 Laptop GPU at 1280x720, the same High viewport measured median
GPU time of **0.264 ms Current / 0.273 ms MPFB** for sixteen mixed bodies, and
**0.100 / 0.105 ms** for one close portrait. Each case used sixty warm-up and
120 measured frames. Grid 95th-percentile values had roughly 1.3 ms spikes in
both modes, so small median differences should not be treated as a universal
performance guarantee or full-game FPS measurement. Draw calls were 128/112
in the grid and 8/7 in the portrait.

The two-sex grid referenced 3,258,350 / 3,237,920 packed mesh bytes and
106,605,384 / 81,439,400 texture image-data bytes for Current/MPFB respectively.
These count unique bound resources, not total process VRAM: source caches from
both modes coexist in the benchmark. Warm actor configuration medians were
16.5/16.6 ms; first configurations also include source loading and cold caches.
There is no MPFB evaluation or mesh regeneration per frame.
