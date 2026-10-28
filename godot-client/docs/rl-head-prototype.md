# RL head (MPFB-based heads, hair and facial customisation)

Status: **the High Human head, on the task branch `feature/rl-heads-high`** (from
origin/develop `159bb0c5`; the prototype was `concept/rl-heads-claude-20261027`). Every
Human (culture `luminous`, bodyTemplate `luminous_male` / `luminous_female`) at High
quality draws it, players and NPCs alike; Low, Medium and every other race keep their
art exactly. No asset is replaced: the shipped bodies, hair and equipment are untouched.

## How the game uses it

* **Activation by tier.** `ReplicatedActor3D` builds the RL head for a Human at High when
  the head module for its sex is on disk, and swaps heads in place when quality crosses
  High (down from High the actor ends exactly as develop's own in-place switch leaves
  it; `tests/test_rl_head_quality_switch.gd`). Develop's classic High head
  (`HighPortraitAppearance`) is kept dormant: `RL_HEADS=classic` (or `off`, `0`, `no`)
  draws it instead, for side-by-side checks and rollback.
* **Face from the saved appearance.** `RLHeadPortraitMap` derives the face from the
  PortraitCustomization fields and palette indices (nothing new is saved or sent):
  `x = clamp(g * (v - c) / 50, -1, 1)` per face field, `c` from the Rowan (male) / Mira
  (female) preset so those presets are the authored heads, `g` per field and sex from
  `tests/rl_head_gain_probe.gd` (displacement per slider unit matched to the Low/Medium
  sculpt near the centre; `eye_tilt` is negative because RL `eye_tilt` raises the inner
  corners). Secondary couplings (jaw -> chin_width, nose -> nose_bridge, face_length ->
  nose_length, brow_depth -> brow_height, eye_size -> eyelid) and the colour tables
  (`tests/integration/rl_head_colour_calibration.gd`: skin 10, hair 20, eyes 12 per sex,
  matched to the lit Low/Medium head) are in `data/actors/rl_head_wire_defaults.json`,
  with per-sex freckle, liner, brow and lip-tint defaults keyed by skin index. PC/3
  fields (planned) slot in when present.
* **Hair and beards.** Male Parted is `rowan_shag`, female Buns `mira_bun`; every other
  style is the game's own fitted hairstyle (`ReplicatedActor3D._add_hair_variant`, with
  the High hair finish), which also stays built, hidden, under an RL module and is the
  fallback when a module file is missing. facial_hair 2-5 are the RL beards by name, 1 is
  painted stubble; women draw neither at High (their saved choice is kept). Under the
  RL head the body's face sculpt, PortraitGroom beard shell and painted stubble are off.
* **Hair-shape contract (hair author, pending assets).** An RL hairstyle may carry blend
  shapes `hl_length_p`, `hl_length_n`, `hl_volume_p`, `hl_volume_n` (weight 1 = the full
  change, 0 = as authored) and `hl_detail_1`, `hl_detail_2` (the Tousled and Swept
  finishes; 0 is the authored finish). `RLHeadRig` drives them from hair_length /
  hair_volume (`clamp((v - preset) / 50, -1, 1)`, preset = Rowan's values for
  `rowan_shag`, Mira's for `mira_bun`) and hair_detail; a missing shape is a no-op. The
  animation importer keeps RESET defaults off `id_`, `ex_` and `hl_` shapes.
* **Portraits.** `ReplicatedActor3D.hold_portrait_pose` / `release_portrait_pose`:
  while a dialogue line shows the speaker (`CampaignPortraitLayer`) or a leaderboard card
  renders, the head keeps its first level of detail, a neutral face and open eyes.
* **Lifecycle.** RL meshes carry the actor's animated-head cull margin and the body's
  render layers, and are skipped by the body refinement (`rl_head` meta). Each rig counts
  as a user of `RLHeadLibrary`'s caches; the last one to go releases them (heads, beards,
  textures, materials, GlbSceneCache entries, body cuts, headwear refits).
* **Open headwear.** RL heads take the RL fits of pieces 111/112/114/119. The data's
  shipped-head fits (`shippedBodies`) would change Low/Medium heads, so they are off
  unless `RL_HEADWEAR_FIT=shipped` (owner decision pending); `=0` draws every piece as
  shipped.
* **Development-only:** the occlusion silhouette clones every mesh onto the actor
  skeleton, RL hair (skinned to its own skeleton) included; it is enabled only by
  development scripts.

The lab (`open-rl-head-lab.bat`) and the evidence scripts still use the explicit
`appearance.rl_head` override (a preset name or the dictionary form), which the game and
the wire never set and which is honoured at every quality.

## Known issues

* `hair/mira_bun.glb` records `headSHA256` `7dc7d99a...`, a female head build older than
  the shipped `rl_head_female.glb` (`abd93434...`); it needs a rebuild by the hair author.
  `tests/test_rl_head.gd` reports it as a known issue and fails on any other mismatch.
* The hl_ hair shapes are not in the hairstyle files yet, so hair length, volume and
  finish do not change the two RL hairstyles.
* A missing RL beard file draws the face clean-shaven (with a one-time notice): the
  body's own beard shell cannot be built on the cut body.
* Texture loading still mipmaps and S3TC-compresses on first use; the packaging route
  (step 8 of the integration plan) is open.

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
  `RL_HEADWEAR_FIT=0` draws every shipped placement; the default refits only RL
  heads; `=shipped` adds the shipped luminous heads.

## Files

| Path | What |
|---|---|
| `assets/actors/rl_heads/rl_head_<sex>.glb` | head module (skinned to `spine_03/neck_01/Head`, LODs, morphs, `asset.extras.rlHead`) |
| `assets/actors/rl_heads/textures/` | painted maps + `manifest.json` (channel meanings, skin reference) |
| `assets/actors/rl_heads/hair/<style>.glb` | hair module with its own small skeleton for spring locks |
| `assets/actors/rl_heads/beards/<style>.glb` | facial hair skinned like the head, with all `id_*` and `ex_*` shapes |
| `data/actors/rl_head_presets.json` | identity presets (lab) |
| `data/actors/rl_head_wire_defaults.json` | appearance-to-RL mapping data: gains, couplings, colour tables, per-sex defaults |
| `data/actors/rl_head_headwear_fit.json` | per-piece fit of the open head pieces on RL and shipped luminous heads (generated) |
| `src/actors/rl_head/` | runtime: appearance data, rig, body cut, expressions, hair motion, shaders |
| `prototypes/rl_heads/` + `open-rl-head-lab.bat` | interactive lab |
| `tests/integration/rl_head_renders.gd`, `tests/test_rl_head.gd`, `tests/integration/rl_head_metrics.gd` | evidence and checks |
| `tests/test_rl_head_portrait_map.gd`, `tests/test_rl_head_quality_switch.gd` | mapping and tier-switch checks |
| `tests/rl_head_gain_probe.gd`, `tests/integration/rl_head_colour_calibration.gd` | calibration probes behind the mapping data |
| `eloria-assets/tools/rl_heads/` | authoring/build scripts, not yet synced to this branch (inputs and outputs stay in ignored `.local/rl-heads/`) |

(Measurements, verification results and limitations: see the evidence report.)
