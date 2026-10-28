# RL head prototype (MPFB-based heads, hair and facial customisation)

Status: **prototype on the local branch `concept/rl-heads-claude-20261027`** (started from
origin/develop `c7da7ff608b255ff754a94d41f7d0c543c3b5dee`). It is opt-in: with no
`rl_head` appearance entry and no `RL_HEADS` developer variable, actors are built exactly
as before. Nothing here replaces a shipped asset.

## What it is

Two reusable head modules (female and male) built from MPFB / MakeHuman `hm08`
topology and fitted to the shipped Human bodies (`luminous_female`, `luminous_male`):

* **Likeness base.** The female base is sculpted toward Mira, the male toward Rowan
  (Rabbit Lands human player studies, 2026-10-26), with MPFB macro targets, MPFB face
  targets and a few authored likeness weights. The editable source is an MPFB human in
  Blender (`.local/rl-heads/authoring/rl_head_<sex>_source.blend`) plus the likeness
  spec JSON; the build is scripted and reproducible.
* **Placement.** The cranium is scaled/translated onto the shipped head shell (ICP on
  the skull above the brow and behind the ears) and then conformed at least 1.5 mm
  inside it, so all 64 headwear pieces, which are fitted to that shell, still fit.
* **Neck seam.** The body is cut exactly at the race-head neck plane (0.075 m along
  `neck_01 -> Head`). Every body triangle with any corner above the plane is hidden;
  a small *body patch* (the clipped lower parts of those triangles, body UVs, weights
  and normals, drawn with the body's own material) ends the body in one planar loop.
  The head's neck ring is pulled onto that loop and zipped to it. The body GLB is
  untouched, so the 14 race bodies that pin its SHA-256 are unaffected.
* **Customisation.** 21 identity controls in 7 groups (eyes/eyelids, brows, nose,
  lips, cheeks, jaw & chin, ears), each a pair of MPFB-derived blend shapes
  `id_<control>_p` / `id_<control>_n`. Controls are compatible authored variations of
  the same topology, so any combination stays anatomically coherent.
* **Expressions.** 13 blend shapes `ex_*` from MPFB's FACS-like expression units
  (blinks, squint, wide eyes, brow raise/sad/furrow, smile, grin, frown, jaw open,
  pucker, sneer). Identity and expression shapes live in separate namespaces and
  separate controllers; the animation importer skips both prefixes, so clips never
  hold or overwrite them.
* **Proxies.** Eyes (eyeball + glossy cornea shell), eyelashes, teeth and tongue are
  MPFB proxies fitted with MPFB's own `.mhclo` maths, so every identity and expression
  shape moves them too.
* **LODs.** `rl_head_lod0` (High), `rl_head_lod1` (Medium) and `rl_head_lod2` (Low),
  each with the full blend-shape set and the same rim, so the seam never opens when
  the LOD changes.

* **Open headwear.** Circlets, bands, crowns and a veil on a band (3:111, 3:112,
  3:114, 3:119) are fitted to the shipped head by a helmet rule (one scale and an
  offset clearing every offered hairstyle by 9 mm at one level section), so they
  float several centimetres clear, ride the outer hair, and their ribbons stand
  out. `RLHeadwearFit` rebuilds such a piece from
  `data/actors/rl_head_headwear_fit.json`: a similarity and a low-order radial
  warp seat the band about level on the skull - forehead 2.5-3.5 cm over the
  brows, over the ears, round the back of the head and never under the
  occipital bulge - a few millimetres clear of the skin, or on the hair's
  under-layer (at most 6 mm over the skull) when hair is drawn, so loose locks
  pass over and through it; one fit per head and hairstyle. The trails hang
  from the band through an envelope of the neck, hair, shoulders and worn
  torso, skinned Head -> neck_01 -> spine_03/clavicle. It applies to RL heads
  (fits keyed by sex) and, as a separate switch, to the shipped luminous heads
  (`shippedBodies`, fits keyed by body and hairstyle file); other races and
  every closed helm, hood, cap and hat keep their shipped placement. The fit is
  solved offline by `.local/rl-heads/scripts/headwear/fit_open_headwear.py`
  (`fit_all.sh`); rerun it when a head, a hairstyle or a piece changes.
  `RL_HEADWEAR_FIT=0` draws every shipped placement, `=rl` only the RL fits.

## Files

| Path | What |
|---|---|
| `assets/actors/rl_heads/rl_head_<sex>.glb` | head module (skinned to `spine_03/neck_01/Head`, LODs, morphs, `asset.extras.rlHead`) |
| `assets/actors/rl_heads/textures/` | painted maps + `manifest.json` (channel meanings, skin reference) |
| `assets/actors/rl_heads/hair/<style>.glb` | hair module with its own small skeleton for spring locks |
| `assets/actors/rl_heads/beards/<style>.glb` | facial hair skinned like the head, with all `id_*` and `ex_*` shapes |
| `data/actors/rl_head_presets.json` | identity presets |
| `data/actors/rl_head_headwear_fit.json` | per-piece fit of the open head pieces on RL and shipped luminous heads (generated) |
| `src/actors/rl_head/` | runtime: appearance data, rig, body cut, expressions, hair motion, shaders |
| `prototypes/rl_heads/` + `open-rl-head-lab.bat` | interactive lab |
| `tests/integration/rl_head_renders.gd`, `tests/test_rl_head.gd`, `tests/integration/rl_head_metrics.gd` | evidence and checks |
| `eloria-assets/tools/rl_heads/` | authoring/build scripts (inputs and outputs stay in ignored `.local/rl-heads/`) |

(Measurements, verification results and limitations: see the evidence report.)
