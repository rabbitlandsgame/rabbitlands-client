# Legwear contact sheets

One sheet per design per authored rig, 192 in all: sixty-four designs on
`luminous_male`, `luminous_female` and `ssarathi_male` — the reference rig and
the two fit groups. Named `4-<visual>__<rig>.png`.

Every sheet is nine cells:

| row | cells |
|---|---|
| top | front, back, left, right, low three-quarter |
| bottom | `Jog`, `Sprint`, `Meditate`, `Sitting_Exit`, all from the low three-quarter |

The low three-quarter is the last of the still angles and the only one used for
the posed frames, because it is roughly where the game camera sits and it is the
angle that actually shows a hem meeting a boot cuff. A front elevation hides that
seam behind the shin.

**The figure wears a shirt and boots on purpose.** A leg garment photographed on
its own hides the two joins most likely to be wrong. Part 5 visual 110 and part 6
visual 100 come along in every shot so the waist seam and the boot cuff are
visible in the evidence rather than only in the fit numbers.

Regenerate with:

    Godot_v4.7.2-stable_win64_console.exe --path godot-client \
        --script res://tests/legwear_contact_sheets.gd

**Not `--headless`** — headless has no framebuffer and every capture comes back
blank. `ELORIA_LEGWEAR_SHEETS` sets the output directory and
`ELORIA_LEGWEAR_ONLY` limits the run to a comma-separated list of visual ids,
which is how to iterate on one design without re-rendering the set.

Stored at half the rendered resolution and quantised, which is enough to judge a
silhouette against its concept tile and keeps 192 sheets to about thirteen
megabytes instead of a hundred and nine. Unlike the concept tiles in
`eloria-assets/concepts/legwear`, quantising these is safe: nothing measures a
palette from them, they are only looked at.

## The blue band

Some cells show a band of sky above the figure. It is the low three-quarter
camera looking up past the environment, it is background, and it obscures no
part of any garment. It is left rather than cropped because cropping the frame
to hide it would also crop the headroom that shows a waistband sitting proud of
a shirt hem.
