# RL head (MPFB-based heads, hair and facial customisation)

Status: **the High Human head, on the task branch `feature/rl-heads-high`** (on
origin/develop `98c76adf`; the prototype was `concept/rl-heads-claude-20261027`). Every
Human (culture `luminous`, bodyTemplate `luminous_male` / `luminous_female`) at High
quality draws it in Forward+, players and NPCs alike (the Compatibility renderer keeps
develop's classic High head unless `RL_HEADS=all`; see below);
Low, Medium and every other race keep their art exactly. No asset is replaced: the
shipped bodies, hair and equipment are untouched.

## How the game uses it

* **Activation by tier.** `ReplicatedActor3D` builds the RL head for a Human at High when
  the head module for its sex is on disk, and swaps heads in place when quality crosses
  High (down from High the actor ends exactly as develop's own in-place switch leaves
  it; `tests/test_rl_head_quality_switch.gd`). Develop's classic High head
  (`HighPortraitAppearance`) is kept dormant: `RL_HEADS=classic` (or `off`, `0`, `no`)
  draws it instead, for side-by-side checks and rollback. Forward+ draws the RL head
  (`ReplicatedActor3D.rl_heads_renderer_supported`); the Compatibility renderer keeps
  develop's classic High head unless `RL_HEADS=all`. Its cost there is no longer the
  obstacle (its identity baked, its per-actor values as material uniforms, no instance
  uniforms, and a lighter profile: within 1.15x of the classic head; see *Draw cost*
  and *Cost at High* below), but its colours are: the RL skin, iris, hair and beard
  tables are measured in Forward+ only, and in Compatibility the RL iris draws up to
  0.28 and the module hair 0.22 (sRGB) off the Medium head. Admitting that renderer
  (where its driver samples BPTC, the masks' format) waits for its own tables and an
  owner decision.
* **Draw cost.** Only the nearest few faces draw live expressions (blinks; the lab's
  expressions): `RLHeadRig.MAX_EXPRESSIVE` (8) within `EXPRESSIVE_RANGE` (8 m) of the
  camera, ranked with the level checks every six frames (a face keeps them 1 m past the
  range, so one on the line does not swap meshes back and forth). Every other face,
  every level from the second on and every hairstyle draws a *still bake*
  (`RLHeadIdentityBake`,
  `still`): the identity and grooming shapes baked in, no live shape at all, the teeth
  and tongue left out, and its `RLFaceExpression` resting. The gameplay camera starts
  26 m out, where a blink is a pixel or two; the creation preview, the lab, a camera
  zoomed in close and a held portrait pose keep their expressions. The resting hair
  spring simulator is taken out of the hair skeleton, so a resting hairstyle is not
  re-posed every frame. In the Compatibility renderer, which skins every surface of every
  drawn mesh with a transform-feedback pass a frame (a mesh with live shapes takes a
  blend-shape pass per surface besides), the first level ends at 6 m instead of 10 m, the
  nearest 4 faces within 4 m draw expressions, and still bakes also leave out the
  cornea's glossy shell and, from the second level on, the eyelashes.
  `RL_HEAD_STILL=0` turns still bakes off and `RL_HEAD_VALUES=material|instance` forces
  either way of passing the per-actor values, for A/B checks.
* **Face from the saved appearance.** `RLHeadPortraitMap` derives the face from the
  PortraitCustomization fields and palette indices (nothing new is saved or sent):
  `x = clamp(g * (v - c) / 50, -1, 1)` per face field, `c` from the Rowan (male) / Mira
  (female) preset so those presets are the authored heads, `g` per field and sex from
  `tests/rl_head_gain_probe.gd` (displacement per slider unit matched to the Low/Medium
  sculpt near the centre; `eye_tilt` is negative because RL `eye_tilt` raises the inner
  corners). Secondary couplings (jaw -> chin_width, nose -> nose_bridge, face_length ->
  nose_length, brow_depth -> brow_height, eye_size -> eyelid) and the colour tables
  (`tests/integration/rl_head_colour_calibration.gd`: skin 10, hair 20, eyes 12 per sex
  and 20 male beards, matched to the lit Low/Medium head; hair and beards recalibrated
  2026-10-28 for the flat hair shading below, residuals at most 0.001 sRGB where they were
  0.09 for hair and 0.27 for beards) are in `data/actors/rl_head_wire_defaults.json`,
  with per-sex freckle, liner, brow and lip-tint defaults keyed by skin index. PC/3
  fields (planned) slot in when present.
* **Hair and beards.** Male Parted is `rowan_shag`, female Buns `mira_bun`; every other
  style is the game's own fitted hairstyle (`ReplicatedActor3D._add_hair_variant`, with
  the High hair finish), which also stays built, hidden, under an RL module and is the
  fallback when a module file is missing. facial_hair 2-5 are the RL beards by name, 1 is
  painted stubble; women draw neither at High (their saved choice is kept). Under the
  RL head the body's face sculpt, PortraitGroom beard shell and painted stubble are off.
* **Grooming (the hair author's contract).** Both RL hairstyles (the hair author's
  2026-10-28 builds, fitted to the shipped heads) carry, beside the 42 `id_` shapes:
  * **`hl_length_p` / `hl_length_n`** (each lock re-meshed along its own growth curve at
    +60% / -40% of its length, roots pinned; Mira's locks that end in the bun keep their
    length) and **`hl_volume_p` / `hl_volume_n`** (+80% / -50% of the stand-off above a
    hugging base, ramped in from the root). Weight 1 is the full effect, 0 the authored
    hair; every grooming shape stays at least 2.6 mm clear of the skin, the identity
    extremes included. `RLHeadRig` drives them from hair_length / hair_volume as
    `x = clamp((v - preset) / 50, -1, 1)` (`_p` for x > 0, `_n` for x < 0), preset =
    Rowan's values (75 / 76) for `rowan_shag` and Mira's (70 / 72) for `mira_bun`, so
    0 / 50 / 100 give Rowan length -1 / -0.5 / +0.5. A missing shape is a no-op.
  * **Fine detail (`hair_detail`).** COLOR_0.A is each point's keep level, in one of
    three bands and nothing else: 1 for core geometry (shell, clumps, ribbons, bun,
    braid, curls, baby hairs); 0.5-0.95, spread per card, for the authored flyaway and
    wisp cards (cards only); 0.05-0.45 for the messy extras - strays, crown and temple
    frizz, loose locks, separated tips, and Rowan's two fringe-gap locks (clump locks at
    0.38 and 0.22) - added for "messier than authored" (owner decision Q-N11, PC/3
    spec). The last level is all core; beards and older assets carry 1.
    `rl_hair.gdshader` drops a fragment where `A < 1 - hair_detail` (the instance
    uniform, 0-1, less half an 8-bit step) through the same alpha scissor as the
    coverage, so the hair stays in the opaque pass in both renderers. The RL face's
    `hair_detail` is a level 0-100 (the uniform is a hundredth of it): 50, the default,
    is the authored look, lower drops flyaways from the lowest keep level up, 0 is
    smooth, and above 50 the strands gain up to 35% contrast about the atlas's local
    mean while the messy extras fade in - a point with keep level A shows above level
    `100 * (1 - A)`, so the band appears from 55 to 95. Beards keep 50.
  * **From the saved finish** (owner decision; colour model spec revision 3, 4.7). A
    Human's hair finish (`hair_detail` 0 Classic, 1 Tousled, 2 Swept) sits on the hair
    finish slider (0 sleekest to 100 messiest) at Swept 25, Classic 50, Tousled 75.
    `RLHeadPortraitMap.detail_level(s, module)` maps slider position `s` to the level
    piecewise linearly through (0, 0), (`s_p`, 50) and (100, 100), rounded, where `s_p`
    is the slider position of the module's own preset finish (Rowan is Tousled, 75; Mira
    Swept, 25), so each preset finish is the authored look: `rowan_shag` Swept 17,
    Classic 33, Tousled 50; `mira_bun` Swept 50, Classic 67, Tousled 83
    (`data/actors/rl_head_wire_defaults.json` `hair.detail.sliderPresetFinish`). A later
    PC/3 `hair_finish` slider value feeds the same function. So no finish of Rowan's
    shows the messy band (Tousled, his messiest, is his authored look), and neither does
    Mira's Swept; her Classic (67) and Tousled (83) are messier than authored and show
    part of it by design: 406 and 1,078 of her 1,476 first-level messy points (19 and 48
    of its 70 keep values). `tests/test_rl_head.gd` checks both against the shader's rule.
  * **Springs** keep their authored rest lengths; extended tips stay weighted to the last
    joint and swing with it, shortened locks use fewer joints.
    `tests/test_rl_head.gd` swings both hairstyles at full length and volume.
  * **Scalp coverage** (2026-10-28 rebuild). The earlier builds let the scalp show
    through from behind and above. Each style's scalp under-shell now spans whole
    texture sectors (40 columns over 12 sectors had left a 36-degree wedge bare from the
    crown to the nape on Rowan's first level, and a gap behind Mira's right ear), is
    lifted until its faces, not only its vertices, clear the skin (the coarse last level
    dipped up to 6 mm under it), shares morph deltas across its duplicated seam vertices
    (the seams cracked under identity shapes) and reaches past the nape hairline. The
    hair author's ray-cast gate (900 scalp samples, 165 view directions, level 0, where
    only core geometry draws) counted up to 96 / 2 / 41 samples showing scalp through
    the hair on levels 0 / 1 / 2 of the earlier Rowan at rest or under the grooming
    extremes, and 29 / 1 / 16 on Mira; the rebuilt styles have none. The all-identity
    extremes, which the gate reports as warnings, leave at most two single-ray samples
    at the sides of the head.
  * The animation importer keeps RESET defaults off `id_`, `ex_` and `hl_` shapes, and
    `tests/test_rl_head.gd` pins the shipped head builds and fails when any hairstyle or
    beard records another head build (`headSHA256`).
* **Hair shading** (`rl_hair.gdshader`; option B, "flat painterly", of the 2026-10-28
  hair look review). Hair and beards are a flat, painterly colour mass, as in the concept
  art: a wrapped Lambert (wrap 0.45) for gentle form, each pixel's painted luminance
  moved 65% of the way to its lock's mean (`flatness`; cards, whose strand atlas is
  mostly white fill, towards a fixed `card_flat_level` 0.35), and only a faint, broad
  sheen in the hair's own hue (primary 0.015 with no white, secondary 0.08 at gloss 12),
  root darkening 0.25, occlusion 0.4, exposure 2.5. The header of the shader lists the
  uniforms of the earlier look and of two other options.
  * **The double-albedo correction.** Godot 4.7.2 multiplies `DIFFUSE_LIGHT` by `ALBEDO`
    after `light()`, in Forward+ and the Compatibility renderer alike (with `ALBEDO` pure
    green every lit pixel came back with red and blue exactly 0). The earlier `light()`
    multiplied `ALBEDO` in as well, so the diffuse fell with the square of the colour:
    dark hair took almost no key light and its strand highlights carried 70-90% of its
    light. `light()` now adds the diffuse without it; the uniform `double_albedo`
    (default 0) restores the old term for comparison renders only.
  * **Measured** on the RL head stage (neutral look, Forward+, front view, the
    75th-percentile hair pixel against the preset colour's luminance), the earlier look
    against this one: Rowan 0.57 -> 1.08, Mira 0.34 -> 0.82, Tavi 1.09 -> 1.15; the
    highlights' share of Rowan's light 69% -> 6%, his luminance spread p90/p10 12.4 ->
    4.0.
  * **Beards** light like the hair of the same colour: the `rl_beard` material sets the
    shader's `beard`, which draws it at `beard_gain` 1.7. Without the gain Tavi's full
    beard in his hair colour lit to 0.68 of that colour against his hair's 1.15 (front;
    0.59 of the hair over the front, three-quarter and profile views); with it 1.16
    (1.10 against 1.10 over the three views). The earlier look's beard was at 0.19.
  * The colour tables' hair and beard rows were recalibrated for this shading (above):
    every hair and beard colour now lands on what Low/Medium show.
* **Portraits.** `ReplicatedActor3D.hold_portrait_pose` / `release_portrait_pose`:
  while a dialogue line shows the speaker (`CampaignPortraitLayer`) or a leaderboard card
  renders, the head keeps its first level of detail, a neutral face and open eyes.
* **Lifecycle.** RL meshes carry the actor's animated-head cull margin and the body's
  render layers, and are skipped by the body refinement (`rl_head` meta). Each rig counts
  as a user of `RLHeadLibrary`'s caches; when the last one goes they are kept for
  `RETAIN_SECONDS` (120 s) and released then if no RL head took them again (heads,
  beards, textures, materials, GlbSceneCache entries, body cuts, headwear refits), so a
  switch down and back up, or the next creation preview, reads and parses nothing.
* **Prewarm.** When the graphics quality is or becomes High (`main.gd`'s quality pass,
  `ReplicatedActor3D.prewarm_rl_heads`), every RL GLB a High Human can draw is parsed on
  the WorkerThreadPool, one file at a time, and published to GlbSceneCache on the main
  thread when its task has finished (the main thread never waits for one: a file it
  needs first it parses itself); the maps are then loaded one a frame and, in Forward+,
  one instance of every RL surface stays out of sight for 30 frames so its render
  pipelines are compiled before the first RL head is drawn. Below High, prewarmed caches
  no head uses go after the retention time. A headless process never prewarms; closing
  the client waits for a parse still on a worker; `RL_HEAD_PREWARM=0` turns it off. At
  High this holds every RL file and map (about 55 MB) from the login screen on.
* **Packaging** (`tools/package_client.py`; the route develop ships its native actors
  by). The head, hair and beard GLBs are the loose-only actor folder
  `assets/actors/native/rl_heads/`: never imported (the local `.gdignore` AGENTS.md
  prepares for every `actor_shipping()` loose folder), staged beside the executable, and
  parsed raw by `GLTFDocument` through `GlbSceneCache` from the globalized path, in a
  checkout and a package alike; their only LODs are the authored `_lod<k>` levels. The
  maps and `manifest.json` are `assets/actors/native/rl_head_textures/`
  (`LOADED_IMAGE_FOLDERS`), in the PCK only, each PNG imported by the settings committed
  beside it: VRAM-compressed with mipmaps; BPTC without the alpha-border fix for the
  channel-packed masks (features, features2, brows, eye), DXT1 for the albedo and DXT5
  for the hair, beard and lash atlases; features2 limited to 1024 px. Against the PNGs
  uncompressed, in nine close stills of Rowan, Mira and Tavi, they halve the large errors
  of the old runtime-DXT route (pixels more than 12/255 off: 14,579 against 28,694): the
  light ring the border fix painted round each iris and the bleed along the brow strokes
  are gone, while the skin carries slightly more fine noise (mean error 0.3-2.3/255
  against 0.2-1.6). `RLHeadLibrary` uses such an import as it is (no GPU readback, no
  runtime mip build; a raw file not imported yet still gets one, left uncompressed: client
  code never calls an Image compressor, `tests/test_build_vram_textures.py`). `check_actor_imports` refuses a map without VRAM
  compression, mipmaps or an S3TC/BPTC product and `check_actor_pack` holds every RL
  file to one place; `tests/test_package_client.py` and `tests/test_rl_head.gd` check the
  route. The lab (`prototypes/rl_heads`) and the RL tests and evidence scripts are not
  exported. A Windows package carries 54.9 MB of RL head: the GLBs loose (17.8 MB; 17.1
  MB before the 2026-10-28 hair rebuild, when the package was measured), the maps in
  the PCK (36.7 MB: VRAM-compressed, as large on disk as in video memory), code and data
  0.3 MB. Exported unchanged, the old layout (`assets/actors/rl_heads`) would
  have carried about 104 MB: imported scenes the game never reads and lossless maps
  without mipmaps in the PCK, and every GLB and PNG loose as well.
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
* The Compatibility renderer keeps the classic High head by default: the RL head's
  colour tables are not measured there (above). The channel-packed masks are imported
  as BPTC (BC7) only; every desktop GPU that runs Forward+ (Vulkan or D3D12) samples
  it, and a Compatibility (OpenGL) driver without BPTC would have to decompress the
  masks or draw without them (`RL_HEADS=all`).
* In the Compatibility renderer the RL head's first level ends at 6 m, and faces that
  draw no expressions (all but the nearest 4 within 4 m) have no cornea highlight and,
  beyond 6 m, no eyelashes; Forward+ keeps both up to 10 m and on every still face.
* The first switch down from High with 40 Humans takes 0.8-1.5 s (the Medium head's
  resources load for the first time), as on develop with the RL head; later switches
  down take about 0.1 s (develop's classic head: 15 ms).

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

## Cost at High (2026-10-29, after the load-time and draw-cost work)

Same laptop, wrapper and crowds as the gate below; develop `86f110d0` (the fixed hair
and flat hair shading) measured in its own worktree beside this branch, the runs
interleaved, two passes each, on the final code (the 10 m rows) or code that draws the
same there (the 26 m rows; `.local/rl-perf/f1`, `f2`, `f3`, `f1p` of the task
worktree). Mean frame work in ms; the ratio is to develop's classic High head of the
same session (develop's High in the Compatibility renderer, its `RL_HEADS=classic` in
Forward+); develop's RL head in the Compatibility renderer is given against the classic
runs of its own session (`f1`), 0-12% faster than the column's. Other agents' jobs
shared the machine, so a repeat can differ by 5-10%. Develop's RL head and this branch
render the same stills, apart from isolated rasteriser ties (36 stills of Rowan, Mira
and Tavi, front, profile and three-quarter, springs at rest: Forward+ 120 differing
pixels, all single pixels on Tavi's hair and beard; Compatibility 93, on shadow edges),
and the Compatibility renderer's material values draw what its instance uniforms drew
(2 pixels off by at most 4/255); `tests/integration/rl_head_bake_silhouette.gd` passes
all 56 views in both renderers.

| Renderer, camera, Humans | classic | develop's RL head | this branch |
|---|---|---|---|
| Forward+, 26 m, 40 | 10.2 | 10.5 (1.03x) | 10.2 (1.01x) |
| Forward+, 26 m, 160 | 19.9 | 22.0 (1.10x) | 21.2 (1.06x) |
| Forward+, 10 m, 40 | 9.4 | 9.8 (1.04x) | 9.7 (1.03x) |
| Forward+, 10 m, 160 | 16.1 | 18.0 (1.12x) | 17.0 (1.05x) |
| Compatibility, 26 m, 40 | 14.2 | 18.1 (1.38x) | 13.5 (0.95x) |
| Compatibility, 26 m, 160 | 36.0 | 47.6 (1.36x) | 35.8 (0.99x) |
| Compatibility, 10 m, 40 | 11.4 | 16.7 (1.47x) | 12.0 (1.05x) |
| Compatibility, 10 m, 160 | 25.6 | 37.3 (1.65x) | 24.8 (0.97x) |

The Forward+ cells are within run-to-run spread of develop's RL head rather than a
clear gain: an independent rerun at 10 m (review, 2026-10-29, two passes each with
nothing else running) measured this branch at 0.98x develop's RL head with 40 Humans
and 1.03x with 160 (1.07x and 1.14x the classic head), its 160-Human passes ranging
16.5-20.1 ms. That rerun reproduced the Compatibility rows (1.04x and 1.12x the classic
head at 10 m; develop's RL head 17.4-18.9 and 36.8-38.4 ms).

Develop's RL head in the Compatibility renderer (`RL_HEADS=all`) also logged about 4,100
"Too many instances using shader instance variables" errors a run; this branch logs
none. Loading (40 Humans for the switch; the probe's preview is a fresh actor of the
Rowan and Mira presets after a Medium warm-up actor, with the High prewarm done as at
the login screen):

| Renderer | | classic | develop's RL head | this branch |
|---|---|---|---|---|
| Forward+ | first creation preview, male (build + first frame) | 1.7-2.0 s | 3.4-4.6 s | 1.4-1.6 s |
| Forward+ | first creation preview, female | 2.8-2.9 s | 3.4-3.7 s | 2.5-2.6 s |
| Forward+ | Medium/Low to High | 4.8-5.7 s | 2.5-3.0 s | 0.55-0.66 s |
| Compatibility | first creation preview, male | 1.5-1.9 s | 1.8-2.0 s | 1.0-1.5 s |
| Compatibility | first creation preview, female | 2.5-2.7 s | 2.3-2.8 s | 1.8-1.9 s |
| Compatibility | Medium/Low to High | 3.6-4.8 s | 2.1-2.7 s | 0.36-0.51 s |

The develop RL head's first male preview spent 1.5-2.6 s of it on its first frame
(Forward+ compiling the RL surfaces' pipelines); with the prewarm it is 0.14-0.28 s.

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

* **Packaged route** (2026-10-28, after the move to `native/`). The gate above ran on the
  editor's imports of the RL GLBs, which added automatic index LODs to every level (each
  halved four or five times); a package never had them, and a checkout now parses the
  GLBs raw as a package does. Two runs per cell on that route, Forward+, against the
  classic head of the same session: 26 m 1.09x / 1.02x (40 / 160 Humans), 10 m
  1.22x / 1.32x. World GPU time is unchanged (160 Humans: 2.70 ms against the imported
  route's 2.60 and the classic head's 2.94 at 26 m; 2.10 against 1.98 and 2.05 at 10 m);
  the ratios moved because that session's classic runs were 10-25% faster than the gate's
  (`.local/rl-high/package/perf*`). Loading costs more on this route (one run): the RL GLBs
  are parsed again whenever the last RL head released them, so switching 40 Humans up to
  High takes 5.0-5.3 s (imported route 2.7-2.9 s, classic head 6.0-6.3 s) and the first
  creation preview opens in 4.0-5.1 s (3.0-3.2 s; classic 2.0 s); the first switch down
  takes 1.8 s. In an exported build the first High Human's four GLB parses (the RL head
  and hair among them) took 1.0-1.3 s in all, the largest 0.5 s. Keeping the parsed RL
  scenes across a switch down, or parsing them on a worker (they name no URI textures),
  would win this back.

* **Identity bake** (`RLHeadIdentityBake`). A face's identity (`id_` and the hairstyle's
  `hl_` shapes) is baked into one cached mesh per source mesh and quantised weights,
  keeping only the `ex_` shapes live and the source's materials, names and LODs; actors
  with the same face share it. Requests wait 400 ms, run on the WorkerThreadPool and are
  built within 3 ms a frame; the cache keeps 48 idle entries and 192 MB in all, beyond
  which faces draw live. Only the shown level is baked; `set_control` goes live. Bakes
  that keep the expression shapes (the nearest few faces' first level) are on by default
  in the Compatibility renderer only (`RL_HEAD_BAKE=1`/`0` forces it): Forward+ deforms
  the shapes in one compute pass and measured no gain while the cache would cost memory.
  Still bakes (below) are drawn in both renderers. Baked vertices are within 1e-5 m of the live result
  (`tests/test_rl_head_identity_bake.gd`, worst 4.9e-6 m) and render the same silhouettes
  and view depth as the live shapes apart from rasteriser ties
  (`tests/integration/rl_head_bake_silhouette.gd`, 2026-10-28: all 56 views of seven
  faces pass in Forward+ and in Compatibility; at most 36 tie pixels in a view, 72% of
  its allowance, each alone or, on the female all-100 face, in one diagonal pair a view
  along a 45-degree edge; no strip of 3 or more). A crowd of 16 looks holds about
  50 MB of baked meshes.
* **Compatibility cost (resolved 2026-10-29; see the table above; the renderer still
  keeps the classic head by default for its colours).** The baked crowd was
  1.46x/1.24x develop's frame time at 26 m and 1.42x/1.66x at 10 m, and each RL mesh
  instance took a 16-slot block of the 4096-item instance-uniform buffer whether it was
  shown or not, which ran out between 40 and 160 Humans. Now: the per-actor values are
  material uniforms on per-face copies of the shared materials, which are themselves
  compiled with `RL_MATERIAL_VALUES` (`RLHeadLibrary.material_values`), so no RL surface
  declares an instance uniform; every face but the nearest few draws still bakes (no
  blend-shape pass at all); and the Compatibility profile (*Draw cost* above). The
  measured steps at 10 m with 160 Humans, two passes each: Forward+'s profile 1.21x;
  first level to 6 m and no expressive face 1.15x; still bakes without the cornea 1.10x
  (no face was within 6 m there, so that step was noise); without the far eyelashes
  1.07x. Of what remained, hiding the RL head alone took the crowd to 0.85x and hiding
  the hair or beard changed nothing (the hair rides its own resting skeleton and is not
  re-skinned per frame).
* **Still bakes** (`RLHeadIdentityBake` with `still`). The same cache and budget; a
  still bake keeps no live shape and leaves out the mouth (and in the Compatibility
  renderer the cornea and, from the second level on, the eyelashes), so its mesh can
  have fewer surfaces than its source, whose materials it takes by surface name. Its
  vertices are the full bake's (`tests/test_rl_head_identity_bake.gd`), and a crowd of
  16 looks holds a few MB of them.
* **Per-frame scripts** (blink, expressions, LOD, spring ranking): 0.73 ms a frame for 160
  Humans at 26 m (4.5 us an actor), 0.82 ms at 10 m with eight spring-hair actors
  (2026-10-28; since then a still face's expression node does not run).
* **Draw calls**: about two more per Human (Forward+ 26 m: 635 against 559 at 40, 2,414
  against 2,103 at 160). **Close portrait** (the method of the former `mpfb_prototype_cost.gd`, one head):
  GPU 0.14 against 0.10 ms in Forward+, 0.09 against 0.05 ms in Compatibility.
* **Triangles up close** (level 0): head 12,152 (male) / 12,077 (female), rowan_shag
  14,686, mira_bun 19,232, beards 872-4,536: Rowan 26,838 and Tavi with a full beard
  31,374 against develop's 17,408 and 19,886; Mira 31,309 against 23,496 (develop's head
  share of the body plus eyes, brows and scalp, its hairstyle and beard shell). The
  2026-10-28 coverage rebuild added 1,778 (Rowan) and 1,256 (Mira) of these on level 0,
  mostly messy-band cards that are drawn but discarded per fragment at level 55 and
  below. The perf gate above ran on the earlier builds (12,908 and 17,976).
* **Video memory**, both sexes loaded (Rowan and Mira, Forward+): develop +200 MB, RL
  +311 MB (textures +56 MB, mesh buffers +55 MB: the source meshes carry all 55 shapes).
  RL maps: per sex albedo 2.8 MB, features and brows 5.6 MB each, features2 1.4 MB
  (kept at 1024 px; the feature and brow maps visibly soften at 1024), plus eye, lash,
  hair and beard maps, about 37 MB in all.
* **Creation preview** (a new actor per debounced edit): RL rebuilds in 70-160 ms against
  develop's 170-345 ms; the first preview took 2.0-3.2 s against 1.3-2.0 s (4.0-5.1 s on
  the packaged route, above); since 2026-10-29 it is faster than the classic head's
  (first table of this section).
* **Quality switch** with 40 Humans: Medium/Low to High 2.5-2.9 s against develop's
  4.7-6.3 s (5.0-5.3 s on the packaged route; 0.4-0.7 s since 2026-10-29, with the caches
  kept across the switch); High to Medium 1.2 s the first time (0.1 s after) against
  25 ms.
* **Repository**: the RL assets are 27.7 MB (22 files; 27.0 MB before the 2026-10-28
  coverage rebuild, 25.7 MB before the hairstyles gained their four grooming shapes),
  against 3.7 MB for develop's High portrait and hair data. The grooming rebuild left
  every hairstyle level's triangle count unchanged; the memory figures above predate it
  (four more blend shapes on each hair mesh) and the coverage rebuild.

## Files

| Path | What |
|---|---|
| `assets/actors/native/rl_heads/rl_head_<sex>.glb` | head module (skinned to `spine_03/neck_01/Head`, LODs, morphs, `asset.extras.rlHead`) |
| `assets/actors/native/rl_head_textures/` | painted maps + `manifest.json` (channel meanings, skin reference) + each map's committed `.import` settings |
| `assets/actors/native/rl_heads/hair/<style>.glb` | hair module with its own small skeleton for spring locks |
| `assets/actors/native/rl_heads/beards/<style>.glb` | facial hair skinned like the head, with all `id_*` and `ex_*` shapes |
| `data/actors/rl_head_presets.json` | identity presets (lab) |
| `data/actors/rl_head_wire_defaults.json` | appearance-to-RL mapping data: gains, couplings, colour tables, per-sex defaults |
| `data/actors/rl_head_headwear_fit.json` | per-piece fit of the open head pieces on RL and shipped luminous heads (generated) |
| `src/actors/rl_head/` | runtime: appearance data, rig, identity bake, body cut, expressions, hair motion, shaders |
| `prototypes/rl_heads/` + `open-rl-head-lab.bat` | interactive lab (not exported) |
| `tests/integration/rl_head_renders.gd`, `tests/test_rl_head.gd`, `tests/integration/rl_head_metrics.gd` | evidence and checks |
| `tests/test_rl_head_portrait_map.gd`, `tests/test_rl_head_quality_switch.gd` | mapping and tier-switch checks |
| `tests/test_rl_head_identity_bake.gd`, `tests/integration/rl_head_bake_silhouette.gd` | identity bake against the live shapes (vertices; rendered silhouettes) |
| `tests/rl_head_gain_probe.gd`, `tests/integration/rl_head_colour_calibration.gd` | calibration probes behind the mapping data |
| `eloria-assets/tools/rl_heads/` | authoring/build scripts (README: inputs, outputs, commands, provenance and licences; inputs and outputs stay in ignored `.local/rl-heads/`) |

(Measurements, verification results and limitations: see the evidence report.)
