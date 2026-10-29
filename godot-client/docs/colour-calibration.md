# Human colour calibration (PC/3 custom colours)

The PC/3 colour fields (skin tone slider and undertone; hair, eye and garment
colour wheels; colour model spec revision 3) draw a custom value through
measured data, so the same value looks the same on every hairstyle, finish and
quality. The palette path (every colour field 0, a typed value equal to the
palette entry's frozen value, or a guarded value) never reads this data: old
saves, NPCs and palette picks draw exactly as before.

## What is measured

All measurements are on the RL head stage (`prototypes/rl_heads/rl_head_stage.gd`,
neutral look, Forward+), front view, 512 px, no MSAA, with every other mesh
hidden. Apparent hair colour is the lit hair mean over the hair-only pixels
(the same over a black and a white backdrop), minus the path's own black,
divided by the stage's skin gain: hair of apparent colour A looks like skin of
swatch A under the same light.

| Data | File | Probe | Fit |
|---|---|---|---|
| Low/Medium and classic High hair and beard shells (P1-P4, B1, B2), per sex, style and finish position (0, 12, 25, 37, 49, 50, 51, 63, 75, 88, 100), and the length x volume shape factors | `data/actors/hair_apparent.json` | `tests/integration/hair_apparent_calibration.gd --mode=fit` | `tools/colour_calibration/fit_hair.py` |
| RL module hair per fine-detail level and RL beards (`hairLut`, `beardLut`) | `data/actors/rl_head_wire_defaults.json` `colours` | the same hair probe (groups `rl`) | `fit_hair.py`, then `merge_rl_data.py` |
| RL skin tone and undertone knots (`skinTone`), RL iris (`eyeLut`) | `rl_head_wire_defaults.json` `colours` | `tests/integration/rl_head_colour_calibration.gd --part=skin` and `--part=eyes` | `fit_skin_eyes.py`, then `merge_rl_data.py` |

Every response is fitted in the functional form of its shader (see
`AppearanceColours.model_mu`): linear for the StandardMaterial, `portrait_hair`
and the beard shells; `high_hair_appearance`'s `pigment()` for the classic High
finish; the RL hair shader's diffuse plus its hue-normalised sheen for RL hair
and beards. Both irises and both skins are affine in their colour. The hair
probe renders at tone-mapping exposure 0.5 and divides by it, so bright dyes
(up to `D_MAX` 1.6) and light beards are measured unclipped.

Each table records the SHA-256 of its source files (hair and beard GLBs,
bodies, shaders, RL textures). `tests/test_appearance_colours.gd` and
`tests/test_rl_head_colour_map.gd` fail when one changes: re-run the probe and
the fit for that data.

## Re-running

Windowed renders, one at a time on the development laptop: wrap each Godot
command in `gpu_lock.sh` and give it its own `APPDATA`/`LOCALAPPDATA` under an
ignored folder. From `godot-client/`:

```
# hair: fit renders (about 2 + 11 + 12 minutes), then the fit
Godot --path . --resolution 512x512 --script res://tests/integration/hair_apparent_calibration.gd -- --mode=fit --out=<abs>/fit-main.json
Godot --path . --resolution 512x512 --script res://tests/integration/hair_apparent_calibration.gd -- --mode=fit --groups=shape,shapehigh,rlshape --out=<abs>/fit-shapes.json
Godot --path . --resolution 512x512 --script res://tests/integration/hair_apparent_calibration.gd -- --mode=fit --groups=positions,positionshigh,shapefinish,shapefinishhigh --out=<abs>/fit-positions.json
python tools/colour_calibration/fit_hair.py <out-dir> <abs>/fit-main.json <abs>/fit-shapes.json <abs>/fit-positions.json

# RL skin knots and iris (about a minute)
Godot --path . --resolution 512x512 --script res://tests/integration/rl_head_colour_calibration.gd -- --part=skin --out=<abs>/skin.json
Godot --path . --resolution 512x512 --script res://tests/integration/rl_head_colour_calibration.gd -- --part=eyes --out=<abs>/eyes.json
python tools/colour_calibration/fit_skin_eyes.py <abs>/skin.json <abs>/eyes.json <out-dir>
python tools/colour_calibration/merge_rl_data.py <out-dir>/rl_hair_luts.json <out-dir>/rl_skin_eye_luts.json

# accuracy (hold-out colours drawn through the game's own resolver)
Godot ... hair_apparent_calibration.gd -- --mode=verify --groups=low,medium,shape,rl,high,shapehigh --out=<abs>/verify-hair.json
Godot ... rl_head_colour_calibration.gd -- --part=verify-skin --out=<abs>/verify-skin.json   (and --part=verify-eyes)
python tools/colour_calibration/verify_hair.py <out-dir> <abs>/verify-hair.json
python tools/colour_calibration/verify_skin_eyes.py <out-dir> fp <abs>/verify-skin.json <abs>/verify-eyes.json
```

`merge_rl_data.py` replaces only its own keys in `colours`; the palette tables
(`skin`, `hair`, `beard`, `eyes`) come from `rl_head_colour_calibration.gd`'s
default `--part=palette` and are edited by hand.

## Measured limits worth knowing

* **Low quality** draws hair 1.25-1.65 times brighter (linear) than Medium for
  every colour, palette included: Low actors cast no shadows, so the hair does
  not shadow itself. Custom colours use the Medium response at Low, keeping the
  palette's relationship there.
* **Length and volume** change a hairstyle's response by 0.87-1.29 times; the
  shape factors in `hair_apparent.json` compensate (a 5 x 5 grid at Classic and
  3 x 3 grids at the other measured finish positions, bilinear, linear in the
  finish position). The RL modules change by at most 3% and are not
  compensated.
* **The classic High finish** mixes a tenth of the luminance into every
  channel (`pigment()`), so it cannot show the most saturated wheel colours:
  their weakest channel stays above the target even at dye 0.
* **A finish position between measured ones** is linear between its
  neighbours; the probe measures the custom positions 12, 37, 49, 51, 63 and 88
  as well as the saved finishes, since the response is not linear across a
  saved finish's whole span.
* The calibration is Forward+. The RL head in the Compatibility renderer
  (`RL_HEADS=all` only) is not calibrated for custom colours or palette ones.
