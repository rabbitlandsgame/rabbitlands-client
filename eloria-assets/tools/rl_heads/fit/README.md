# RL reference fitter

Fits the RL head module (21 identity controls, colours, hair envelope, beard) to a
Meshy image-to-3D / multi-image-to-3D GLB of a head or bust. CPU only, no network,
no new packages (numpy, scipy, trimesh, Pillow). The tools are committed here;
their inputs and outputs stay in the ignored `.local/rl-heads/` tree.

```
python eloria-assets/tools/rl_heads/fit/fit_reference.py <reference.glb> --sex male|female --out <dir>
       [--landmarks <json>] [--up auto|y|z|-y|-z|x|-x] [--yaw auto|0|90|180|270]
       [--weights <json>] [--no-envelope] [--quick] [--gap-targets] [--label NAME]
       [--weak auto|fit|off] [--strict] [--seed N] [--quiet]
python eloria-assets/tools/rl_heads/fit/combine_fits.py <fitA> <fitB> [...] --out <preset.json> [--tol 0.3] [--label NAME]
```

`RL/scripts/` = `eloria-assets/tools/rl_heads/`; the inputs and outputs stay in the ignored local authoring area `.local/rl-heads` (`RL_HEADS_LOCAL`).
Exit code 0 on success (1 with a traceback on failure; 3 with `--strict` when `quality.status` is
`fail`). Typical runtime 35-55 s per reference (30k-2.3M triangles; harness mean 39.1 s, max 45 s; the first run
after a hair-module change spends 2-3 extra minutes caching the style envelopes); `--quick` about 60 %
(harness mean 24.2 s, max 29 s).

**Real-data workflow.** One image-to-3D reconstruction is not a measurement: two Meshy busts made from
the same three concept images differ by ~3 mm rms on the face and ~6 mm at the chin. Generate the
character at least twice, fit each with `--label`, and merge with `combine_fits.py`, which keeps only
controls that every fit measured and that agree within 0.3 (see below). Always look at the previews and
`quality.status` before merging; `review` means a warning needs a human look, `fail` means do not use.

## Outputs (`<dir>/`)

### fit.json

| key | meaning |
|---|---|
| `sex`, `reference` | as given (absolute path) |
| `reference_fingerprint` | `sha256`, `bytes`, `mtime` of the reference file (detects stale fits after a regeneration) |
| `controls` | all 21 controls (order of `specs/controls.json`), value in [-1, 1] rounded to 0.01: the values the shape fit used (residuals, previews). Runtime semantics: `id_<c>_p` weight max(v,0), `id_<c>_n` weight max(-v,0). Controls with status `hidden` or `not_measured` are pinned to 0 during the solve; `prior` and `low_observability` controls keep their fitted value here but are not in the preset (see `preset`, `preset_fallbacks`). |
| `control_reliability` | per control: `status` (first matching rule) = `hidden` (>= 50 % of its support or >= 65 % of its evidence is covered by hair or beard, see `covered`: unobservable, pinned to 0), `not_measured` (an eye/lip control whose snr < 1.5, see `--weak`: pinned to 0), `prior` (e/lambda < 1: the prior, not the data, decides), `at_limit` (\|v\| >= 0.98), `low_observability` (an eye/lip control with e/lambda < 25, i.e. a data-only sd > 0.1, or with 1.5 <= snr < 2: value kept, not trusted), `measured`. `observability` = e/lambda (data curvature over prior; the data-only sd is 0.5/sqrt(e/lambda)); `snr` = the control's full-range surface effect over the residual where it acts (both weighted by where it moves the surface); `sd` = marginal posterior sd (correlations with the other controls and the pose included; null when pinned); `covered` / `covered_evidence` = share of its support (exposed skin vertices weighted by the larger of the control's two per-vertex \|delta\|) / of its point-to-plane evidence ((delta . n)^2 x vertex area x region weight) that is covered by hair or beard; `seen` = support share whose outward normal meets reference skin first (method step 7) |
| `transform` | `{scale, R (3x3), t (3)}`: `x_game = scale * R @ x_ref + t`, x_ref = reference-file world coordinates (glTF node transforms applied), game space = metres, Y up, face toward +Z, +X = character's left |
| `orientation` | `up`: reference axis mapped to game +Y (`y`, `z`, `-y`, `-z`, `x`, `-x`; `z` = Blender-style Z-up where the face looks toward -Y at yaw 0). `yaw_deg`: the face direction in the up-converted reference is (sin yaw, 0, cos yaw), i.e. 0 = +Z, 90 = +X. Extra: `tilt_deg` (residual rotation beyond the axis-aligned quadrant), `search`, `margin` (best start score minus the best start that converged elsewhere) |
| `residual_mm` | after the fit, reference skin points to the fitted RL skin (point to surface, signed by the RL normal, + = reference outside). Robust: per region, points further than 3.5 robust sigmas (1.4826 MAD, >= 0.5 mm) from the region median are outliers (isolated cavity walls, seams) and left out. `face_rms`, `face_p90` over forehead, brow, nose, cheeks, jaw, chin (not eyes/lips); `by_region` rms for every region with >= 20 points: forehead, brow, eyes, nose, cheeks, mouth, jaw, chin, ears, neck, cranium; `outliers_by_region` counts. Points are confident, visible skin (hair, beard, clothing, cavities and their boundaries excluded); matches past open boundaries, with opposed normals or > 15 mm away are dropped. Eyes and mouth statistics include two rings around them. |
| `residual_mm_before` | same statistics on the **same points**, all controls 0 at the best similarity for controls 0 |
| `control_gaps` | regions whose robust rms after the fit is >= 1.4 mm or whose robust mean is >= 0.9 mm (>= 20 inliers): `region`, `rms_mm`, `mean_mm`, `direction` (`out` = reference outside the fitted skin on average, `in` = inside), `note` (which controls act there / which are at their limit / which are hidden under hair or beard / no control acts there), `points`, `outliers` |
| `colours` | sRGB 0-1 medians: `skin_srgb` (cheeks + forehead skin), `hair_srgb` (scalp hair, else beard), `lip_srgb` (RL lips group, redder half, hair-coloured samples such as a moustache removed; null if indistinguishable from skin or covered), `brow_srgb` (band above the eyes, darker than skin by > 12 L*; null if not found), `eye_srgb` (iris area at the front of each eyeball, sclera/pupil/skin removed; null if < 10 points). Clipped texels (any channel >= 0.98) never enter a median. A directional baked light is estimated on the skin (linear luminance ~ a + b.n, trimmed, unclipped texels), normalised so that the median shading over the skin-colour set is 1 (the correction removes the light's direction-dependent part without changing the exposure of the median) and divided out; points left in deep shadow (shading < 0.55) are dropped; then luminance-trimmed medians are taken (skin 20-80 %, hair 15-85 %) |
| `hair` | `present`, `coverage` (cos-lat weighted fraction of the scalp bins, i.e. grid bins whose ray hits MPFB scalp-group skin, that have hair), `max_thickness_mm` (99th percentile of the envelope), `lowest_y` (game Y of the hair's lowest point: the minimum over drape sectors of the sector's 1st percentile, sectors with >= 30 points, else the 1st percentile of all hair points; **null when there is no hair**), `nearest_style` (closest candidate hair style, see below; null without hair), `style_score` (smaller = closer; > 1.8 gives a warning), `style_runner_up` |
| `beard` | `present`, `coverage` (area fraction of the RL beard region - upper lip, chin, jaw, lower cheeks, front neck - with beard geometry along the vertex normal, within 13 mm, < 3.5 mm off-axis); when present also `style` and `thickness_mm` (median stand-off); `stubble: true` for painted stubble. Present = coverage > 0.3 **and** >= 0.4 of the chin front or of the moustache area |
| `quality` | `registration_inlier_fraction` (visible RL skin samples on forehead, brow, nose, cheeks, jaw, chin, ears, neck with a reference skin point within 4 mm, \|point-to-plane\| < 2 mm, normal agreement > 0.8), `status` (`ok` / `review` / `fail`), `status_reasons`, `warnings` (list of strings). `fail`: inlier fraction < 0.35, robust face rms > 3 mm or < 1500 skin points. `review`: a control beyond the RL range (it sits at its limit and a re-solve with that bound raised to 2 takes it past +-1.15; a control exactly at +-1 is not a reason), inlier fraction < 0.5, an orientation-search runner-up within 0.05, a face mirror plane > 4 deg off, more than half of the skin texels clipped or a near-white skin colour, a poor hair-style match, an envelope > 120 mm thick or hair > 250 mm below the neck rim, or more than 2 envelope bins rejected as spikes. Informational warnings (no `--label`, 20-50 % clipped texels with colours from the unclipped part, hidden / low-observability / not-measured controls, a beard) do not change the status |
| `preset` | ready-to-merge `rl_head_presets.json` entry: `sex`, `label` (`--label`, else the file name - with a warning), `controls` (status `measured` / `at_limit` and \|v\| >= 0.05 only, the runtime stores 4-bit values; a control at its limit next to a remaining gap > 1.5 mm in its region is clamped to +-0.5), `skin`, `eyes`, `hair_color`, `brow_color` (measured, else 0.62 x hair colour), `lip_tint` (base preset `mira`/`rowan` where unmeasured), neutral defaults for what a mesh cannot show (`freckles` 0, `liner` 0, `liner_wing` 0, `brow_style` `soft`, `brow_thickness` 0), `hair` = nearest style or `none`, `beard` = `full_beard` / `short_beard` / `goatee` / `moustache` / `stubble` / `none`. So `preset.controls` equals `controls` restricted to measured / at-limit controls with \|v\| >= 0.05 (except the clamp); hidden and not-measured controls are 0 in both, prior / low-observability ones are non-zero only in `controls` |
| `preset_key` | suggested key for the presets document (slug of the label) |
| `preset_fallbacks` | every preset field that is not measured: base-preset colours, neutral style defaults, and the controls left at the base value 0, grouped by status (`hidden`, `not_measured`, `prior`, `low_observability`) |
| `details` | diagnostics: mesh summary, sampling (head-zone resample), `registration` (search mode; `quick_fallback` when a `--quick` search was inconclusive and the full search ran), segmentation counts, hair pieces kept/dropped, occluded skin points, colour models, symmetry plane, priors (`lambda_abs_mm2` per control part, `n_eff`, residual sigma and correlation lengths), `hidden_controls` and `coverage` (probe counts of the hidden-control test), `weak_dropped`, `low_observability`, `limit_test` (unbounded re-solve of controls at their limit), the pose before controls and how far the rotation moved, unrounded controls, per-region mean residuals, hair/beard style scores, per-iteration logs, timings |
| `gap_targets` | only with `--gap-targets`, see below |

### envelope.npz (only when hair is present and `--no-envelope` is not given)

Exact definition (headref frame, game space, metres; implemented in `envelope.py`):

* `lon_deg` (L=120,): bin centres -178.5 .. 178.5 step 3 (lon 0 = face/+Z, +90 = character's left/+X).
  `lat_deg` (M=50,): bin centres -58.5 .. 88.5 step 3 (lat +90 = top/+Y). `C` (3,): the ray origin,
  headref's cranium centre `Head(sex).C`.
* `rho_skin_m` (M, L): distance from C to the outermost hit of the bin-centre ray `headref.lonlat_dir(lon, lat)`
  on the fitted RL skin without ears (headref's `noear` triangles, vertices = base skin + fitted control
  deltas); NaN where the ray misses the skin (below the neck rim).
* `thickness_m` (M, L): every hair point p (beard excluded) gets its radial height above the skin in its
  own direction, h_p = |p - C| - rho_skin(dir(p - C)) (rho_skin bilinear on a 2-degree grid), so a sloping
  skin inside a bin does not bias it; thickness = max(98th percentile of h_p in the bin (max for < 10
  points), 0). NaN where no hair point falls in the bin, where the outermost surface in the bin is not hair
  (skin/clothing more than 3 mm beyond the hair), where the ray misses the skin, or where the bin is an
  isolated spike (> 2.5 x and > 40 mm above its 8-neighbourhood median: mislabelled geometry, warned).
  Empty bins whose 8-neighbourhood is >= 5/8 hair are filled with the neighbour mean.
* `rho_outer_m` (M, L) = `rho_skin_m + thickness_m`: the outer hair surface is the point
  `C + lonlat_dir(lon, lat) * rho_outer_m`.
* `height_normal_m` (M, L): height of the outer hair surface along the skin normal at the bin's skin point
  S = C + dir * rho_skin, i.e. the value `Head.frame_point(lon, lat, height=...)` needs. Finite exactly
  where `thickness_m` is finite. `height_normal_src` (M, L) int8 says how each bin got its value:
  1 = measured: the largest projection onto the normal of the hair points inside a 3 mm-radius cylinder
  around the normal half-line (clamped at 0); 2 = no hair point inside that cylinder (a filled bin, a sparse
  sample, or the normal leaving the hair sideways at its edge): the distance along the normal to the radial
  outer surface `C + dir * rho_outer_m` (bilinear in lon/lat, first crossing); 3 = the normal never crosses
  that surface inside the hair region: `thickness_m` itself; 0 = NaN. On the harness 99.9 % of the bins are
  source 1. (Before 2026-10-27 v3 the value was the last 2 mm probe step whose 3 mm sphere touched hair: it
  read ~2 mm beyond the hair and was NaN where no hair lay along the normal.)
* `state` (M, L) int8: 0 no hair, 1 hair measured, 2 filled from neighbours, 3 covered by other geometry,
  4 ray misses the skin. `count` (M, L): hair points in the bin (confidence). `height_normal_src`: see above.
* Drape (hair below the head) as a cylinder around the vertical axis through C:
  `drape_lon_deg` (K=72,) sector centres -177.5 .. 177.5 step 5 of the horizontal angle
  atan2(x - Cx, z - Cz); `drape_y_m` (Y=60,) slice centres C_y - 0.045, C_y - 0.055, ... (10 mm slices);
  `drape_r_outer_m`, `drape_r_inner_m` (Y, K) = 98th / 2nd percentile of the horizontal distance from the
  axis of the hair points in the cell (max / min for < 10 points; NaN = no hair); `drape_count` (Y, K);
  `drape_lowest_y` (K,) = 1st percentile of the hair points' game Y in the sector (NaN for < 30 points).
* `hair_points` (N <= 20000, 3): hair points in game space. Hair is only what is one connected piece with
  the scalp hair (or lies on the head, e.g. bangs); torso creases, clothing and the bust cut are not.

**Consumer recipe** (hair generator):

```python
E = np.load('envelope.npz'); h = Head(sex)
LO, LA = np.meshgrid(E['lon_deg'], E['lat_deg'])
m = np.isfinite(E['thickness_m'])                       # always mask: frame_point returns ok=True with NaN heights
outer = E['C'] + lonlat_dir(LO[m], LA[m]) * E['rho_outer_m'][m][:, None]          # radial (exact)
# or, for code that offsets along the skin normal (hairgen's height_mm):
P, N, ok = h.frame_point(LO[m], LA[m], height=np.nan_to_num(E['height_normal_m'][m]))
```

Do not pass `thickness_m` to `frame_point`: thickness is radial and the skin normal leaves the ray by
7-9 deg (median) and up to 45-80 deg at the nape, which put long hair 14-50 mm off (checked with
`fit/dev/tools/envelope_check.py` on the v3 harness case c03: distance from the fit's own hair points at
lat < -30, radial placement median 2.2 mm / max 5.0 mm, `frame_point(height=height_normal_m)` 1.9 / 6.0 mm,
the old recipe 14 / 47 mm; against the ground-truth outer surface (`fit/review/final_verify/envelope_vs_truth.py`)
the normal recipe is now within 0.4 mm of the radial one: median 1.5-2.1 mm at lat >= -30 on c03 / c04 / c08, v2
2.4-3.2 mm). Hair below the
grid (long hair) is in the drape arrays: per sector and 10 mm slice the outer radius from the axis
through C, i.e. lock lengths = how far down a sector has hair, gravity targets = the outer radius.

Hair styles: candidates are the RL hair modules in `godot-client/assets/actors/rl_heads/hair/` (any sex)
and the shipped fitted legacy hairstyles for the fit's sex
(`godot-client/assets/actors/native/hair/fitted/luminous_<sex>_<style>_<sex>.glb`, runtime name
`legacy:<style>`; they are authored in the same body space and sit 5-12 mm off the RL skull). Each
envelope is computed exactly like the reference's on the base head of the module's sex (cached in
`RL/fit/cache/`). Distance = mean |thickness difference| / 15 mm over the union of hair bins (a bin
without hair counts 0 mm; cos-lat weighted, crown and back x1.5) + 0.5 x (1 - IoU) + difference of the
lowest point below the neck rim / 0.10 m (hair ending above the rim counts as ending at the rim). Hair
reaching > 30 mm below the rim is only matched to styles that also reach below it. Beard modules: shape
decides the family (jaw sides covered >= 0.6 = full/short beard, chin front without the jaw = goatee,
upper lip only = moustache), the measured stand-off decides full (>= 3 mm) vs short beard; weighted L1
part distances are kept as scores.

### Previews, report

`front.png`, `profile.png`, `three_quarter.png`: 3 x 512 px panels: reference (textured, in game space via
`transform`) | fitted RL head with the hair envelope drawn as dots (outer surface + drape) | signed
residual heat map on the fitted head (red = reference outside, blue = inside, +-4 mm, green-grey = no skin
data: hair, beard, clothing). `segmentation.png`: reference coloured by class (skin / hair brown /
beard green / other blue - cavities, occluded skin, clothing, sculpted brows). `report.md`: quality
status, orientation, scale, inlier fraction, controls with status and snr, residuals before/after per
region, gaps, colours, hair/beard with style scores, warnings, the preset with its key and fallbacks.

## Method

1. **Load** (`gltfio.py`, `refmesh.py`): own minimal glTF reader (all triangle primitives of the default
   scene, node transforms applied, sparse/normalized accessors, strips/fans, KHR_texture_transform,
   embedded or external images; Draco/meshopt rejected with a message; skinned meshes keep bind
   positions; other formats via trimesh). Colour = baseColorTexture (bilinear, repeat) x COLOR_0 (when
   both exist, multiplied in linear space) x baseColorFactor. Normals = welded vertex normals
   interpolated at the sample, parts made outward if inside-out. Area-uniform sample of 240k points
   (110k with --quick) with normals, colours and face ids.
2. **Orientation + scale** (`register.py`): 6 up axes x 4 yaw quadrants (or the --up/--yaw subset). For
   each up axis the vertical width profile gives the head top, the neck narrowing and the head width; two
   scale guesses are combined and spread x0.72..x1.38 (5 scales, also with --quick) -> 120 starts. Every
   start runs a short wide-gate trimmed point-to-plane similarity ICP of the RL face, eyes, ears and upper
   neck (no cranium). Trimming is one-sided: the largest positive residuals (reference outside the RL skin
   = hair, beard, clothing) are dropped, the reference-inside evidence is kept, so a full beard plus hair
   cannot shrink the reference onto the RL head. The best 12 starts (8 with --quick) continue with tighter
   gates, the best 3 distinct ones are refined and scored by the weighted fraction of face points with a
   close normal-compatible reference point minus 0.02 per mm of trimmed rms, plus small priors (0.03 Y-up,
   0.02 Z-up, 0.01 yaw within 30 deg of 0). --quick uses 45k instead of 70k reference points and 1200
   instead of 1800 model points; when its best start has an inlier fraction < 0.4 or a runner-up within
   0.1, the full search runs on the same sample and the better-scoring pose is kept
   (`details.registration.quick_fallback`). With the old quick setting (3 scales, 6 + 2 candidates) the
   densest harness case c08 had no start in the right basin and converged 17 deg off; with 5 scales it
   registers like the full search. `--landmarks` replaces the search by a Umeyama similarity on the
   named landmarks (then ICP).
3. **Mirror plane**: iterative reflect-and-match on the face area; if it differs 0.3-8 deg from the RL
   sagittal plane the pose is rotated onto it (kept as a diagnostic in `details.symmetry`).
4. **Head-zone resample**: faces within 0.19 m of the RL cranium centre (game space, current pose) are
   resampled with 160k points (80k quick) and merged with the global sample outside that sphere. Real
   busts carry a torso and voluminous hair, so an area-uniform sample left the face 3-6 % of the points
   (7k confident skin points on the real m6-lite bust; now 22k).
5. **Segmentation** (`segment.py`): per point a robust Gaussian (Student-t tails) colour likelihood in Lab
   with L* down-weighted for skin (seeded on the nose, upper cheeks and forehead close to the registered
   RL skin), hair (seeded on the crown, well outside the RL cranium; plus a second hair-colour model
   seeded on beard candidates) and other (below the neck rim, neither skin- nor hair-coloured); plus
   geometric log-priors from the signed distance to the RL skin, points past the neck rim (where the hair
   prior decays by 1 nat per 80 mm from 40 mm below the rim on) and points far from the head. Posteriors are smoothed
   over 10 nearest neighbours (3 passes). Then:
   * hair connectivity: hair points are linked to their 8 nearest hair neighbours closer than 3.5 x the
     sample spacing; only pieces that contain crown hair seeds or lie mostly on the head are hair, the rest
     (texture creases on the torso, clothing, the bust cut) is other. Hair-coloured pieces on the brow /
     eyelids that are not part of the scalp hair (sculpted eyebrows) are other.
   * occlusion: a skin point whose outward normal ray (from r + 1 mm to 15 mm, r = 1.6 x the head-zone
     spacing) passes within r of another reference point faces into a cavity (fused mouth / nostril /
     lip-seam interiors) or lies under an overhang (fringe, behind the ears): other, never skin evidence.
   * beard seeds must stand off the skin over the beard region, not face downward (n_y > -0.4: the
     shadowed underside of the jaw) and differ from the skin in linear-RGB chromaticity (> 0.03) or be
     > 38 L* darker - baked shading changes luminance, not chromaticity. Beard = hair close to the face
     over the RL beard region, grown into adjacent hair below nose height; isolated specks revert. In the
     final pass a "beard" lying on the skin (median < 0.9 mm) is painted stubble.
6. **Similarity refinement, controls 0** (`solve.py`, controls pinned), alternated with the segmentation
   (up to 3 rounds, until the pose moves < 1 % / 1 deg / 3 mm): gives `residual_mm_before` and the
   pose R0 / scale s0.
7. **Control solve** (`solve.py`): Gauss-Newton/ICP iterations. Each iteration morphs the skin with the
   current controls, finds correspondences (data -> model: confident reference skin points to the
   closest exposed RL skin/eyeball point, rejected past an open boundary, with opposed normals or beyond a
   gate shrinking 25 -> 10 mm; model -> data: RL vertices to the nearest reference point, kept only if
   that point is skin), and solves one bounded linear least-squares problem jointly for all controls and
   a small similarity update. Residuals are point-to-plane in mm; weights = region weight x Cauchy robust
   weight (scale 8 -> 3 mm) x normal agreement, data -> model normalised to 1 and model -> data to 0.5.
   Region weights (override with --weights): forehead 1, brow 0.8, eyes (eyelid skin) 0.3, eyeballs 0.5,
   nose 1, cheeks 1, mouth 0.45, jaw 1, chin 1, ears 0.5, neck 0.35, cranium 0.6. The model surface is the
   exposed skin plus the RL eyeballs (`rl_eye` with its id_ deltas; the `rl_cornea` shell is left out -
   with it a 2.35 mm cornea bulge that fused references do not show biased eye_size by -0.3 and
   eye_spacing by up to 0.5); the mouth bag and the eye-socket lining behind the eyeballs (visibility
   computed with the eyeballs as occluders) are not part of it.
   Priors:
   * rotation (refinement only; the first pass is free): a prior toward the controls-0 rotation R0 on the
     same footing as the control prior, lambda_rot = sigma^2 / (N_eff (0.5 deg)^2) (`rot_prior` in
     --weights fixes it for both passes). Real busts get ~470-640 mm^2/rad^2: without it the pitch absorbed
     brow and chin shape (two fits of one character ended 5.2 deg apart in pitch with brow_height -1 vs
     +1); now the rotation moves 0.13-0.18 deg. In-model synthetic references get < 2 mm^2/rad^2, i.e. none:
     there the controls-0 rotation is the biased one (control effects tilt it by up to 0.7 deg) and a fixed
     800 mm^2/rad^2 prior had doubled the control RMSE on dense cases (c03 0.075 -> 0.152, c05 0.088 -> 0.128).
   * scale: 4 mm^2 per (log scale)^2 toward the current scale (a weak guard; re-anchored on the fitted
     scale before the refinement - the controls-0 scale had absorbed control effects).
   * controls: Tikhonov lambda_j z_j^2 with lambda_j = 0.002 e_j + lambda_abs (e_j = mean squared
     effect of part j on the current correspondences). First pass lambda_abs = 0.001 mm^2. The
     refinement ties lambda_abs to the residual statistics of the first pass (MAP for a control prior
     with sd 0.5): lambda_abs,j = 4 sigma_j^2 / N_eff, where sigma_j^2 is the residual where part j acts
     (weighted by its squared effect) and N_eff = 20000 mm^2 / (pi ell^2) (clipped 30..2000) with ell the
     measured residual correlation length. In-model synthetic references (sigma ~0.1-0.4 mm, ell ~3 mm)
     get 1e-5..1e-3 mm^2, i.e. practically no shrinkage (the old fixed 0.001 shrank cupid_bow to 13-25 %
     even on exact data); real busts (sigma ~1.1 mm, ell 19-24 mm: the residual is unmodelled shape, not
     noise) get ~0.15 mm^2, so the controls stop chasing the mismatch.
   Converges when controls move < 0.004, rotation < 0.02 deg and translation < 0.05 mm after the robust
   schedule, then re-segments against the fitted head and refines (8 more).
   **Hidden controls** (`analysis.control_coverage`): before the refinement every exposed RL skin vertex
   (welded, eyeballs excluded) of the first-pass head is probed along its outward normal, from 2 mm inside
   to 150 mm outside in steps of the probe radius (max(2 mm, 1.6 x the head-zone spacing)), against the
   segmented head-zone reference points: `seen` when the first point met is skin, `covered` when it is not
   skin and hair or beard lies along the normal within 30 mm of that first point (fused hair/beard, or skin
   under a separate hair mesh, which the occlusion test labels other). Per control two shares of covered
   vertices are formed over both of its sides (per vertex the larger of the p and n effect, so the test does
   not depend on the sign the first pass gave a control it cannot see): `covered` = support share, weights
   \|delta\| (the weighting of the harness's ground-truth `visible_fraction`, which uses the true side), and
   `covered_evidence` = evidence share, weights (delta . n)^2 x vertex area x region weight, i.e. what the
   point-to-plane data term can see (a mouth corner sliding sideways contributes nothing). A control with
   support >= 0.5 or evidence >= 0.65 is `hidden`: pinned to 0 for the refinement and left out of the preset.
   The evidence share is needed for mouth_width: under a full beard or goatee only ~25 % of its \|delta\|
   support is covered (the lips stay visible but move tangentially), but 74-83 % of its evidence is. With the
   active side instead of both sides, brow_ridge on the long-hair cases (c03, c05, c08, truth visible) sat
   at 0.43-0.45 / 0.51-0.56, close to the thresholds; over both sides it is 0.24-0.25 / 0.21-0.22, and on the
   m6-lite bust brow_height no longer flipped with the seed's first-pass sign. Without the test the beard edge drove
   mouth_width to +0.88 (c02) and +0.85 (c10, truth 0) and chin_width to +0.57 (c10) as `measured`: the
   e/lambda test passed them because the prior is tiny on clean data. Skin that only hidden controls move
   then gets its data weight multiplied by 1 - H/(H + A + (0.5 mm)^2) (H, A = summed squared full-range
   effects of the hidden / still-fitted controls at the vertex): with ear_size pinned under a bob (c05) the
   visible ear lobes otherwise dragged the other controls and the scale (control RMSE 0.053 -> 0.110; with
   the down-weighting 0.080), while they now show up as an honest `control_gaps` entry on the ears.
8. **Sign handling (p/n parts)**: unknowns are z = [a; b], a = max(v,0), b = max(-v,0), each in [0, 1];
   the skin is exactly linear in z, matching the runtime. The bounded problem is solved with both parts
   free (convex relaxation, BVLS), each control gets the side its relaxed solution prefers and is
   re-solved per orthant; sides are flipped one control at a time while the energy drops, so the result is
   a KKT point with exactly one part active per control (verified against brute force over all 2^k sign
   patterns on 300 random problems by the review, `fit/review/t04_orthant_solver.py`).
9. **Weak controls** (`--weak auto`, default): eye_size, eye_tilt, eyelid, cupid_bow and lip_fullness
   move the surface by a few mm at most, under eyelids and lip seams that image-to-3D output renders
   unreliably (two real Meshy busts of Rowan gave opposite signs for all of them). After the refinement
   each one's snr (full-range effect / residual where it acts) is checked; below 1.5 it is pinned to 0
   (status `not_measured`, base value in the preset) and the refinement is re-run without it. A weak control
   that passes the snr test but has e/lambda < 25 (data-only sd 0.5/sqrt(e/lambda) > 0.1, i.e. coarser than
   ~1.5 runtime 4-bit steps) or snr < 2 (its whole range is less than twice the local residual) keeps its value in `controls` but gets status `low_observability` and stays out
   of the preset: its error on the harness is dominated by how the reference renders lids and the lip seam,
   not by noise (e.g. c08 eye_size 0.00 vs truth 0.57 at e/lambda 23-26 and snr 1.85-1.88 in full / quick
   mode, cupid_bow 0.00 vs -0.60 at e/lambda 3.6, both formerly `measured`). `--weak fit` always fits them, `--weak off` never.
10. **Analysis** (`analysis.py`): robust per-region residuals before/after on the same points, gaps,
    reliability, colours, beard coverage/style; **envelope** (`envelope.py`); **previews**; **report**.
11. **`--gap-targets`** (`gaptargets.py`): every MPFB target under head, forehead, eyebrows, nose, mouth,
    cheek, chin, ears, eyes, neck that the controls do not use is mapped onto the skin like
    `build_head.py` maps control targets and tested as one extra column on the final correspondences:
    best weight in [0, 1] and the energy reduction. The top 15 are listed as candidate new controls.

### Options

* `--landmarks <json>`: `{"eye_l": [x,y,z], "eye_r": ..., "nose_tip": ..., "chin": ..., "mouth": ...,
  "ear_l": ..., "ear_r": ...}` in reference-file coordinates (at least 3; `_l` = the character's left
  = game +X). RL landmarks: eyeball centres, nose tip, menton, front of the mouth (stomion), ear centroids.
* `--up`, `--yaw`: restrict the orientation search (yaw convention as in `orientation.yaw_deg`).
* `--weights <json>`: region weights `{"eyes": 0.1, "eyeballs": 0.3, "jaw": 0.5, ...}` and/or `lambda_rel`,
  `lambda_abs` (mm^2, replaces the automatic prior in both passes), `scale_prior` (mm^2), `rot_prior`
  (mm^2/rad^2; 0 = free rotation).
* `--weak auto|fit|off`: see method step 9.
* `--quick`: 110k + 80k head-zone samples, the same 120 orientation/scale starts on smaller ICP samples
  (full search as a fallback, method step 2), fewer solver iterations.
* `--no-envelope`: skip envelope.npz (hair summary still computed).
* `--strict`: exit code 3 when `quality.status` is `fail` (outputs are still written).
* `--label`: preset label; pass one whenever fits will be merged into the presets document.

### combine_fits.py

Merges the fits of two or more generations of one character: a control enters the preset when every fit
measured it (`measured` / `at_limit`) and their preset values agree within `--tol` (0.3); the value is
the mean. Colours are per-channel medians, hair/beard style the majority. Writes `{key, preset,
combined_from, disagreements, not_measured}`; refuses fits of different sexes or with status `fail`.

### Self-test (developer)

`selftest.py run|build|eval` builds the fitter's own synthetic references from the RL head (see its
docstring; references in `RL/fit/dev/synth/`, fits in `<--out-root>/fits/`, default `RL/fit/dev/`). `run`
prints a PASS/FAIL line per case (hair/beard presence, scale < 2 %, rotation < 3 deg, status not `fail`,
reliable-control RMSE <= 0.12 on in-model cases) and exits 1 when a case fails or crashes. `male_bald_clean`
is a bald, clean-shaven, in-model male head (no hair or beard point at all; it would have hit the
`KeyError: 'in_seeded'` crash of the previous version): run it in both modes with
`selftest.py run --cases male_bald_clean,female_bald_nm [--quick] --out-root <dir>`. The older references
(female_long, male_beard, male_short_dense) were built with the RL cornea shell in the eyes, before the
model switched to the eyeball only, so rebuild them (`--rebuild`) before comparing eye controls. The
official tool is the harness in `synth/`. v3 results (`RL/fit/dev/selftest_v3/`): male_bald_clean PASS in both
modes (no hair or beard point; reliable-control RMSE 0.013 full / 0.017 quick, scale error 0.01 %), female_bald_nm
PASS (presence, transform, status; its 1.2 mm off-model displacement gives a long residual correlation, so the
automatic prior holds controls near 0 and its reliable-control RMSE is 0.29, not gated). The two dev
fits that the review found stale (`fits/female_long_lm`, `fits/female_long_upyaw`) were re-run against
the current `female_long.glb` (landmarks regenerated from its truth.json): orientation z / 90.09 deg /
tilt 6.01, scale error 0.07 %; `reference_fingerprint` now pins the file each fit was made from.

## Results

All numbers below are from runs on 2026-10-27 with the current code ("v3"). Outputs:
`RL/fit/dev/acceptance_v3/` and `RL/fit/dev/acceptance_v3_quick/` (harness, full and `--quick`),
`RL/fit/dev/probes_v3/` (review probes), `RL/fit/dev/real_v3/` (real Meshy busts), `RL/fit/dev/x01_v3/`
(non-head), `RL/fit/dev/bald_v3/` and `RL/fit/dev/selftest_v3/` (bald, clean-shaven references). The
previous version ("v2") is `RL/fit/dev/acceptance_v2/` (identical numbers to the independent re-run in
`RL/fit/review/final_verify/`).

### Synthetic acceptance harness (`synth/run_acceptance.py`, 13 voxel-remeshed cases)

`python eloria-assets/tools/rl_heads/fit/synth/run_acceptance.py --cases all --report-dir RL/fit/dev/acceptance_v3` (and
`--extra-args=--quick`; note the `=`, argparse rejects `--extra-args "--quick"`): **11 of 13 cases pass
every gate; overall FAIL on G4 (c03, c08) and G3 (c08, full mode only)**, the same two cases as before -
see "Limitations, weak controls". No gate was changed.

| measure | v2 | v3 full | v3 `--quick` |
|---|---|---|---|
| gates failed | G3 c08; G4 c03, c08 | G3 c08; G4 c03, c08 | G4 c03, c08 (v2 quick: G1 c08 crash, G4 c03) |
| pooled control RMSE clean / noisy (observable; gate per case 0.12 / 0.20) | 0.065 / 0.098 | 0.0687 / 0.0984 | 0.0693 / 0.0925 |
| same incl. the low-observability controls | 0.1047 / 0.1567 | 0.1066 / 0.1542 | 0.1039 / 0.1584 |
| c08 control RMSE (G3 limit 0.20) | 0.2017 | 0.2114 | 0.1922 (scale error 0.009 %, rotation 0.024 deg, hair and short beard found) |
| per-control RMSE eye_spacing / nose_tip / jaw_width | 0.034 / 0.066 / 0.026 | 0.029 / 0.065 / 0.035 | |
| per-control RMSE eye_size / cupid_bow (weak) | 0.25 / 0.352 | 0.251 / 0.351 | |
| worst scale / rotation / centre error | 0.054 % / 0.13 deg / 0.39 mm | 0.098 % / 0.143 deg / 0.41 mm | 0.108 % / 0.175 deg / 0.45 mm |
| worst envelope MAE (gate 4 mm) | 1.11 mm | 1.21 mm (c05) | 1.36 mm |
| `measured`/`at_limit` controls with error > 0.35 (non-extreme cases) | 7 (mouth_width c02 0.88, c08 0.39, c10 0.85; chin_width c10 0.57; eye_size c08 0.57; cupid_bow c03 0.58, c08 0.60) | 0 (largest 0.33) | 0 (largest 0.33) |
| hidden controls vs the ground truth's `occluded_controls` | (not detected) | identical on all 13 cases (17 hidden) | identical on all 13 |
| quality status ok / review | 9 / 4 (c01, c07, c11 partly clipped light; c06 9 controls exactly at +-1) | 13 / 0 | 13 / 0 (no full-search fallback needed) |
| `height_normal_m` NaN where `thickness_m` is finite | 15 of 49910 bins | 0 of 49938 | |
| `control_gaps` on in-model cases | 0 | 1 (c05 ears: ear_size hidden under the bob) | |
| envelope presence precision | 0.98-0.99 | 0.98-0.99 | |
| hair lowest_y error c11 / c02 / c08 | 0.3 / 14 / 3.5 mm | 0.3 / 14 / 3.4 mm | |
| beard style (c02 full, c08 short, c10 goatee) | 3 of 3 | 3 of 3 | 3 of 3 |
| lip colour error under the full beard (c02); worst skin colour error | 0.005; 0.034 | 0.005; 0.034 | |
| runtime max / mean | 61 / 43 s | 45 / 39.1 s | 29 / 24.2 s |

Per-case control RMSE changed only where controls are now hidden: c02 0.078 -> 0.023 and c08 0.202 -> 0.211
(beard), c10 0.023 -> 0.049 (goatee: chin_length pinned although its visible part measured it), c05 0.053
-> 0.080 (ear_size pinned under the bob; 0.110 before the down-weighting of hidden-only skin). Failing gates,
all on weak eye/lip controls: c03 cupid_bow 0.16 vs truth 0.74 (G4), c08 eye_size 0.00 vs 0.57 (G4, now
status `low_observability`; it and brow_height -0.12 vs -0.42 keep c08's full-mode RMSE above 0.20). Under
the harness's strict spec (`control_over_limit_strict`) cupid_bow is also over 0.5 on c06 (extreme), c07
and c08, with a surface change < 1 mm.

### Real Meshy busts (pilot, read-only local files)

`RL/meshy/pilot/rowan_m6lite/rowan_m6lite_glb.glb` (meshy-6-lite, 152k triangles) and
`RL/meshy/pilot/rowan_m71/rowan_m71_glb.glb` (meshy-7.1, 1.37M triangles), both made from the same three
Rowan concept images. The male base head was sculpted toward Rowan and the Rowan preset has no controls,
so the expected answer is "near 0" and "the same for both".

| measure | v2 | v3 |
|---|---|---|
| m6-lite vs m7.1 control RMS difference, all / large-proportion controls | 0.328 / 0.378 | 0.343 / 0.394 |
| RMS distance from the Rowan preset (all 0), `controls` (preset in brackets) | 0.37 / 0.24 | 0.336 / 0.239 (0.325 / 0.230) |
| controls at +-1 (m6-lite / m7.1) | 0 / 0 | 0 / 0 |
| preset controls agreeing within 0.3 | 14 / 21 | 14 / 21 |
| hidden controls (m6-lite / m7.1) | - | brow_height, brow_ridge, ear_size / brow_height |
| second seed, RMS change m6-lite / m7.1 | 0.020 / 0.016 | 0.164 / 0.021 (see below) |
| `--quick` vs full, m7.1 / m6-lite | 0.026 / - | 0.060 (33 s) / 0.037 (26 s) |
| rotation moved during the control solve | 0.13 / 0.18 deg | 0.37 / 0.30 deg |
| confident face skin points | 22.6k / 19.0k | 22.6k / 19.0k |
| face rms before -> after (robust) | 2.21 -> 1.18 / 1.94 -> 1.40 mm | 2.20 -> 1.21 / 1.95 -> 1.42 mm |
| beard (Rowan has painted stubble) | none / none | none / none (coverage 0.04 / 0.004): nothing hidden by it, mouth_width, jaw_width and chin controls stay measured on both |
| hair lowest_y (m6-lite); hair style | 1.490 m; rowan_shag (both) | 1.491 m; rowan_shag (both) |
| quality status | ok / ok | ok / ok (m6-lite seed 1: review, orientation runner-up margin 0.029, as in v2) |
| runtime | 38 / 52 s | 36 / 43 s |

Eye/lip controls not measured on either bust (eye_size, eye_tilt, cupid_bow; eyelid too on m6-lite; on
m7.1 lip_fullness is `low_observability`). Rowan's shag hides part of the brow and the ears: brow_height is
hidden on both busts and both seeds (support 0.60-0.70 / 0.47, evidence 0.73-0.81 / 0.68 covered),
brow_ridge on m6-lite only (0.59-0.69; m7.1 0.47, just under the threshold). The m6-lite ear_size support
is 0.52 covered with seed 0 and 0.49 with seed 1, on either side of the 0.5 threshold, so it is hidden (0)
in one fit and measured (-0.74) in the other: that one control is the whole m6-lite seed change (0.164;
without it 0.03). `combine_fits.py` drops such a control because not every fit measured it. The residual
correlation length is 23-24 mm (vs ~3 mm on the synthetic cases), so the control prior is ~0.14 / 0.22 mm^2 (median
over the control parts) and the rotation prior ~470-640 mm^2/rad^2. The remaining disagreement is the reconstructions' own: after a
face-only similarity the two busts still differ by +6.3 mm at the chin and +3 mm at the jaw
(`fit/review/tools/compare_meshy_faces.py`), which is chin_length +0.19 vs -0.57. `combine_fits.py` on the
two keeps nose_depth -0.26, mouth_width 0.62, cheek_fullness -0.09, jaw_width -0.14, chin_width 0.12 and drops
4 disagreeing (nose_width, cheekbones, chin_length, chin_projection) and 12 not-measured controls
(`fit/dev/real_v3/rowan_combined.json`). A female fit of the male bust is flagged `review` (inlier 0.49, face
rms 2.18 mm vs 0.55 / 1.21 for the right sex; mouth_width beyond the RL range) but not `fail`.

### Review probes (`RL/fit/review/probes`, scored by the harness)

`run_acceptance.py --cases-dir RL/fit/review/probes --cases r01,...,r07 --report-dir RL/fit/dev/probes_v3`:
the same gate results as v2 (G2 r04, G4 r01 and r04, G11 r02); no probe has a hidden control (none in the
ground truth either).

| probe | stress | result |
|---|---|---|
| r01 | dark high collar touching the jaw | collar not hair (max envelope thickness 22.3 mm), style legacy:buzzed (expected); cupid_bow over limit (G4) |
| r02 | lit side blown out (58 % of skin texels clipped), shadow at 10 % | skin colour unrecoverable: texel median [1,1,1] (error 0.35, G11) **with** warnings (clipped, near white) and status review |
| r02b | one-sided light, lit side capped (30 % clipped) | skin error 0.003; status now ok (v2: review for the 30 % clipped warning alone) |
| r03 | curtain of hair over one ear and half the forehead | all gates pass; ear_size support 0.47 covered: not hidden (ground truth: visible) |
| r04 | controls at +-1.3-1.45 + off-model nose hump | 6 controls at the limit, 2 of them beyond the RL range by the unbounded re-solve (jaw_width 1.20, ear_size 1.23): status review; fails G2/G4 by design (truth outside the range) |
| r05 | plinth, fragments, earring, cm units, Z-up | all gates pass; status review (6 envelope bins rejected as spikes) |
| r06 | 1.9M triangles, scale 100 | all gates pass, 42 s |
| r07 | yaw 35 deg | all gates pass, rotation error 0.07 deg |
| x01 | snowman (not a head) | `quality.status` fail (inlier 0.23, face rms 5.6 mm); `--strict` exits 3. With `--quick` the quick orientation search is inconclusive (inliers 0.22, margin 0.03), the full search runs (`details.registration.quick_fallback`), status fail (inlier 0.33), exit 3 |
| bald | RL skin + sphere eyes, no hair, no beard (`fit/review/final_verify/make_bald.py`) | v2 crashed (`KeyError: 'in_seeded'`, full and quick); v3 status ok in both modes (24 / 15 s), hair and beard absent, preset hair/beard `none` (`fit/dev/bald_v3/`) |

## Limitations

* **Weak controls.** eye_size, eye_tilt, eyelid, cupid_bow and lip_fullness are weakly observable on fused,
  remeshed references: the lid margins slide over the fused eyeball and the lip seam is fused, so most of
  their displacement is tangential or hidden. On the harness, the data energy itself (prior removed,
  everything else re-optimised, `fit/dev/tools/control_profile.py`) is minimal at eye_size ~+0.1 on c08
  (truth 0.57; only 1.46 mm of visible displacement at full weight) and at cupid_bow ~+0.3 on c03 (truth
  0.74; 124 of 38886 correspondences move > 0.1 mm, the whole [-1, 1] range changes the energy by
  2e-4 mm^2). With these references both truths are practically unobservable for a surface-distance fitter
  (the data barely prefers any value; this is a measured energy profile, not a proof that no method could
  recover them). On real busts the
  snr test drops eye_size, eye_tilt and cupid_bow (and eyelid on m6-lite); they flipped sign between two
  generations before. The harness counts an error as detectable from the raw vertex delta (c08 eye_size
  1.29 mm, c03 cupid_bow 1.93 mm), but the displacement visible on the fused references is 0.57 x 1.46 =
  0.83 mm and 0.58 x 1.30 = 0.75 mm. The gates were not widened (the review asked not to); this is an
  owner decision, as are the harness agent's three earlier threshold changes.
* **Meshy variance.** Two Meshy generations of one character differ by ~3 mm rms on the face (6 mm at the
  chin after a face-only alignment), so single-fit controls carry that variance (chin_length +0.19 vs
  -0.57 for the two Rowan busts). Use `combine_fits.py` on two or more generations.
* nose_tip (point-up side) and nose_length trade off in dense noses.
* Controls whose support is mostly under a beard (jaw_width, chin_*, mouth_width, cheek_fullness) or hair
  (ear_size under a bob, brow controls under a fringe) are `hidden`: pinned to 0, left out of the preset,
  listed in a warning (method step 7). The test is a threshold (support share 0.5, evidence share 0.65), so
  a control near it can flip between two fits of the same bust: the m6-lite ear_size support is 0.52
  covered with seed 0 and 0.49 with seed 1 (hidden 0 vs measured -0.74). `combine_fits.py` drops such a
  control; a single fit's preset does not. Pinning also costs accuracy where the visible rest of the support
  did determine the control (c05 ear_size 0.38 was measured exactly under the bob; c10 chin_length under the
  goatee), which the harness accepts because its ground truth hides the same controls. Painted stubble is
  skin and hides nothing.
* Open mouths / expressions are not modelled (the mouth is low weight; chin_length can absorb an open jaw).
* Orientation: the search covers the 6 up axes x 4 yaw quadrants with ICP from each; the review's probe at
  yaw 35 deg (between quadrants) converged to 0.075 deg. Lying heads or full bodies need `--landmarks` or
  `--up/--yaw`; a small best-vs-runner-up margin gives a warning.
* Segmentation: hats and hoods become hair when they stand off the skin and touch the scalp hair; clothing
  that is hair-coloured AND touches the hair (a high collar under a nape-length cut) can still join the hair
  piece (the hair prior decays below the neck rim, the envelope rejects isolated spikes, and a warning fires
  when the envelope exceeds 120 mm or the hair reaches 250 mm below the rim). Very blond hair on fair skin
  relies on the geometric prior. Thin beards (< ~1 mm) are reported as painted stubble; painted stubble
  without any stand-off is not detected (the preset then says `none`).
* Colour: the baked-light correction is first-order (one directional light); exposure (global brightness)
  cannot be separated from albedo; texels clipped at >= 0.98 are excluded and a warning fires above 20 % (status `review` only above 50 %,
  where the albedo cannot be recovered).
* Hair style: the matcher compares envelopes (thickness map, coverage, length below the rim). Real Rowan
  busts map to `rowan_shag`, long hair to `legacy:braid`; the harness's thin synthetic shells (bun, bob,
  shag cases, 10-20 mm uniform shells) map to `legacy:buzzed`, whose shell is the closest by envelope even
  where the generator intended another style name.
* The wrong sex is not detected (a female head fitted as male reaches a similar inlier fraction; the face
  residual is higher). Pass `--sex` deliberately.
* The fitter imports the hair agent's live `scripts/hair/{headref,rlglb,paths}.py` read-only. The interface
  it needs is checked at import (`fitcommon.HEADREF_API`, `HEAD_ATTRS`); a refactor in progress fails with a
  clear `HeadrefError` instead of deep inside (seen once for ~1 minute on 2026-10-27). Retry, or pin a copy.
* Never published or merged anything: presets are written into fit.json only; merging into
  `godot-client/data/actors/rl_head_presets.json` is a manual, reviewed step.

## Modules

| file | role |
|---|---|
| `fit_reference.py` | CLI, pipeline, priors, reliability, fit.json, report.md |
| `combine_fits.py` | consensus preset from several generations of one character |
| `fitcommon.py` | paths, headref interface check, similarity class, colour maths, KD-query helper |
| `gltfio.py` | glTF reader / GLB writer |
| `refmesh.py` | reference mesh, colour lookup (texture x COLOR_0 x factor), area-uniform sampling |
| `rlmodel.py` | RL head as a linear model (headref.Head), regions, landmarks, exposed-face mask (eyeballs as occluders), projection; `RL_FIT_EYE_MATERIALS` (default `rl_eye`; the cornea shell biased eye_size/eye_spacing) |
| `register.py` | orientation/scale search, ICP, landmark init, mirror plane |
| `segment.py` | skin/hair/other/beard classification, hair connectivity, cavity/occlusion test |
| `solve.py` | joint control + similarity solver with the orthant active-set, residual statistics (sigma, correlation length, local sigma, snr, observability) |
| `analysis.py` | robust residuals, gaps, colours, beard coverage/presence/style |
| `envelope.py` | hair envelope, drape cylinder, candidate style envelopes and matching |
| `gaptargets.py` | `--gap-targets` ranking |
| `raster.py`, `fitviz.py` | CPU rasteriser and preview panels (hair overlay) |
| `selftest.py` | the fitter's own synthetic references and scoring (developer); `synth/` is the separate acceptance harness |

Developer tools (not part of the fitter): `RL/fit/dev/tools/` - `batch.sh`, `cmp_real.py` (two fits of one
character), `envelope_check.py` (envelope consumer recipes), `style_eval.py`, `control_profile.py` (energy
profile of one control, adapted from the review's t10).

Caches: `RL/fit/cache/` (hidden-face masks per head build, hair/beard module envelopes and coverages; keyed
on file size + mtime, safe to delete).

