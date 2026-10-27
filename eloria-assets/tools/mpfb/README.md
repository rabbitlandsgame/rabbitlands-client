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

Run `test-mpfb-prototype.bat` from this prepared worktree. Select **MPFB
prototype** and High graphics. Low/Medium select the current models. The
independent Equipment menu offers **No equipment**, **Sword and shield**, and
**Staff**, while the outfit menu retains clothing and capes. Review the two
single cuts, original Flurry, combat ready, idle, walk and run from all sides.

`test-human-customization.bat` remains the ordinary preview. Neither launcher
connects to a server or changes production/player assets.

Focused evidence fixtures:

- `tests/human_portrait_comparison.gd`: identical studio portraits, with
  `RL_MPFB_PROTOTYPE_ROOT` set only for the prototype captures.
- `tests/test_mpfb_prototype_integration.gd`: actual rig/action/equipment checks.
- `tests/mpfb_prototype_cost.gd`: Current High versus MPFB High at the same
  1280x720 viewport, both a 16-character grid and a close portrait.

Use an isolated guarded Godot project/profile and `--offline-hud-preview`.
The portrait output directory is `RL_HUMAN_PORTRAIT_OUTPUT`; integration/cost
output is `RL_MPFB_REVIEW_OUTPUT`. Rendered comparisons must use the actual
export hashes, identical cameras and lights, and unretouched game pixels.

This is a geometry/material workflow prototype. Existing hair is deliberately
shared for comparison, the study brows are baked to their chosen color, and
the production stubble paint has not been transferred. It is not a finished
painted portrait match or a production replacement. Shipping an MPFB target
library, Blender, subdivision, skin microdisplacement or hair simulation is
unnecessary; runtime consumes only the fitted static skinned mesh and atlases.

## Measured budget

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
