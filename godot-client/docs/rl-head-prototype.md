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
  draws it instead, for side-by-side checks and rollback. The Compatibility renderer
  also keeps the classic head (`ReplicatedActor3D.rl_heads_renderer_supported`): there the
  RL head's live identity blend shapes cost 3.2-3.9x develop's crowd frame time (40 and
  160 Humans); with the identity baked per face (below) it still costs 1.46x/1.24x, and
  its instance uniforms overflow the 4096-item global buffer between 40 and 160 Humans.
  `RL_HEADS=all` draws it anyway, baked. See *Cost at High* below.
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
* **Grooming (the hair author's contract).** Both RL hairstyles (the hair author's
  2026-10-27 builds, fitted to the shipped heads) carry, beside the 42 `id_` shapes:
  * **`hl_length_p` / `hl_length_n`** (each lock re-meshed along its own growth curve at
    +60% / -40% of its length, roots pinned; Mira's locks that end in the bun keep their
    length) and **`hl_volume_p` / `hl_volume_n`** (+80% / -50% of the stand-off above a
    hugging base, ramped in from the root). Weight 1 is the full effect, 0 the authored
    hair; every grooming shape stays at least 2.6 mm clear of the skin, the identity
    extremes included. `RLHeadRig` drives them from hair_length / hair_volume as
    `x = clamp((v - preset) / 50, -1, 1)` (`_p` for x > 0, `_n` for x < 0), preset =
    Rowan's values (75 / 76) for `rowan_shag` and Mira's (70 / 72) for `mira_bun`, so
    0 / 50 / 100 give Rowan length -1 / -0.5 / +0.5. A missing shape is a no-op.
  * **Fine detail (`hair_detail`).** COLOR_0.A is each point's keep level: 1 for core
    geometry (shell, clumps, ribbons, bun, braid, curls, baby hairs), 0.5-0.95 spread per
    card for flyaway and wisp cards; beards and older assets carry 1. `rl_hair.gdshader`
    drops a fragment where `A < 1 - hair_detail` (the instance uniform, 0-1) through the
    same alpha scissor as the coverage, so the hair stays in the opaque pass in both
    renderers. The RL face's `hair_detail` is a level 0-100 (the uniform is a hundredth
    of it): 50, the default, is the authored look, lower drops flyaways from the lowest
    keep level up, 0 is smooth, and above 50 nothing more appears - the strands gain up
    to 35% contrast about the atlas's local mean instead. Beards keep 50.
  * **From the saved finish.** A Human's hair finish (`hair_detail` 0 Classic, 1 Tousled,
    2 Swept) gives the level `clamp(50 + 25 * (rank[finish] - rank[preset finish]), 0,
    100)`, ranked Swept 0 < Classic 1 < Tousled 2 and centred, like length and volume, on
    the module's own preset (Rowan is Tousled, Mira Swept): `rowan_shag` Classic 25,
    Tousled 50, Swept 0; `mira_bun` Classic 75, Tousled 100, Swept 50
    (`data/actors/rl_head_wire_defaults.json` `hair.detail`; a seed for owner review).
  * **Springs** keep their authored rest lengths; extended tips stay weighted to the last
    joint and swing with it, shortened locks use fewer joints.
    `tests/test_rl_head.gd` swings both hairstyles at full length and volume.
  * The animation importer keeps RESET defaults off `id_`, `ex_` and `hl_` shapes, and
    `tests/test_rl_head.gd` pins the shipped head builds and fails when any hairstyle or
    beard records another head build (`headSHA256`).
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

* The saved hair finish reaches the RL hairstyles only as the fine-detail level above;
  develop's Tousled and Swept reshaping of the game's own hairstyles has no RL
  counterpart.
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

## Cost at High (perf gate, 2026-10-28)

Measured on the development laptop (RTX 5080 Laptop GPU, shared with other jobs, so
repeats differ by up to about 10%) against develop's own High head (`RL_HEADS=classic`,
which the parity capture shows is develop's High exactly). Crowds: the all-Human
wrapper of `crowd_presentation_benchmark.gd` on four_gates, 1280x720, a third of the
crowd moving or fighting, presets, all-50 and extreme faces, both RL hairstyles and
beards; mean frame work in ms, two runs each at 26 m.

| Renderer, camera | 40 Humans: develop / RL | 160 Humans: develop / RL |
|---|---|---|
| Forward+, 26 m | 12.2 / 12.5 (1.02x) | 28.4 / 26.6 (0.94x) |
| Forward+, 10 m | 10.7 / 12.2 (1.14x) | 20.1 / 25.2 (1.25x) |
| Compatibility (RL_HEADS=all), 26 m, live shapes | 15.1 / 59.2 (3.9x) | 43.5 / 140.4 (3.2x) |
| Compatibility (RL_HEADS=all), 26 m, baked | 16.2 / 23.7 (1.46x) | 49.1 / 60.8 (1.24x) |

* **Identity bake** (`RLHeadIdentityBake`). A face's identity (`id_` and the hairstyle's
  `hl_` shapes) is baked into one cached mesh per source mesh and quantised weights,
  keeping only the `ex_` shapes live and the source's materials, names and LODs; actors
  with the same face share it. Requests wait 400 ms, run on the WorkerThreadPool and are
  built within 3 ms a frame; the cache keeps 48 idle entries and 192 MB in all, beyond
  which faces draw live. Only the shown level is baked; `set_control` goes live. On by
  default in the Compatibility renderer only (`RL_HEAD_BAKE=1`/`0` forces it): Forward+
  deforms the shapes in one compute pass and measured no gain while the cache would cost
  memory. Baked vertices are within 1e-5 m of the live result
  (`tests/test_rl_head_identity_bake.gd`, worst 9.6e-7 m) and render the same silhouettes
  (`tests/integration/rl_head_bake_silhouette.gd`). A crowd of 16 looks holds about
  50 MB of baked meshes.
* **Still open in Compatibility.** The baked crowd is 1.46x/1.24x develop's frame time
  (p95 1.42x/1.32x), and at 10 m 1.42x/1.66x; each RL mesh instance also takes a
  16-slot block of the 4096-item instance-uniform buffer whether it is shown or not
  (head, beard and hair at three levels), which runs out between 40 and 160 Humans.
  Options: keep develop's High head there (current); per-face materials instead of
  instance uniforms there; one mesh instance per part with the level's mesh swapped in;
  no blend shapes on the baked mesh while the face is neutral; fewer head surfaces at the
  far levels.
* **Per-frame scripts** (blink, expressions, LOD, spring ranking): 0.73 ms a frame for 160
  Humans at 26 m (4.5 us an actor), 0.82 ms at 10 m with eight spring-hair actors.
* **Draw calls**: about two more per Human (Forward+ 26 m: 635 against 559 at 40, 2,414
  against 2,103 at 160). **Close portrait** (`mpfb_prototype_cost.gd` method, one head):
  GPU 0.14 against 0.10 ms in Forward+, 0.09 against 0.05 ms in Compatibility.
* **Triangles up close** (level 0): head 12,152 (male) / 12,077 (female), rowan_shag
  12,908, mira_bun 17,976, beards 872-4,536: Rowan 25,060 and Tavi with a full beard
  29,596 against develop's 17,408 and 19,886; Mira 30,053 against 23,496 (develop's head
  share of the body plus eyes, brows and scalp, its hairstyle and beard shell).
* **Video memory**, both sexes loaded (Rowan and Mira, Forward+): develop +200 MB, RL
  +311 MB (textures +56 MB, mesh buffers +55 MB: the source meshes carry all 55 shapes).
  RL maps: per sex albedo 2.8 MB, features and brows 5.6 MB each, features2 1.4 MB
  (kept at 1024 px; the feature and brow maps visibly soften at 1024), plus eye, lash,
  hair and beard maps, about 37 MB in all.
* **Creation preview** (a new actor per debounced edit): RL rebuilds in 70-160 ms against
  develop's 170-345 ms; the first preview takes 2.0-3.2 s against 1.3-2.0 s.
* **Quality switch** with 40 Humans: Medium/Low to High 2.5-2.9 s against develop's
  4.7-6.3 s; High to Medium 1.2 s the first time (0.1 s after) against 25 ms.
* **Repository**: the RL assets are 27.0 MB (22 files; 25.7 MB before the hairstyles
  gained their four grooming shapes), against 3.7 MB for develop's High portrait and hair
  data. The grooming rebuild left every hairstyle level's triangle count unchanged; the
  memory figures above predate it (four more blend shapes on each hair mesh).

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
| `src/actors/rl_head/` | runtime: appearance data, rig, identity bake, body cut, expressions, hair motion, shaders |
| `prototypes/rl_heads/` + `open-rl-head-lab.bat` | interactive lab |
| `tests/integration/rl_head_renders.gd`, `tests/test_rl_head.gd`, `tests/integration/rl_head_metrics.gd` | evidence and checks |
| `tests/test_rl_head_portrait_map.gd`, `tests/test_rl_head_quality_switch.gd` | mapping and tier-switch checks |
| `tests/test_rl_head_identity_bake.gd`, `tests/integration/rl_head_bake_silhouette.gd` | identity bake against the live shapes (vertices; rendered silhouettes) |
| `tests/rl_head_gain_probe.gd`, `tests/integration/rl_head_colour_calibration.gd` | calibration probes behind the mapping data |
| `eloria-assets/tools/rl_heads/` | authoring/build scripts, not yet synced to this branch (inputs and outputs stay in ignored `.local/rl-heads/`) |

(Measurements, verification results and limitations: see the evidence report.)
