# Approved idle and customization — 2026-09-08

Installed the reviewed shared `Idle_Subtle`: each foot and hand moves outward
by 0.05 m, with an additional 10 degrees of elbow flexion. The elbow adjustment
keeps the reviewed lateral hand clearance. The skeleton, bind pose, and other
161 clips are unchanged. The installed library SHA-256 is
`161f9b54aed6a172ac5b1a37960264f106015bbc8622cd33af2061c9c4f6d69c`.

Hair now offers Bald, Buzzcut, Parted, Long, and Buns, independently of color.
The four authored hair designs are fitted to all 16 skulls. Original appearance
bytes 0–19 and the previous independent encoding 20–99 retain their meanings;
new choices use 100–199. Cosmetic headwear remains retired.

Creation controls have descriptive names and color swatches. Skin and hair
shades are grouped from light to dark, followed by fantasy colors; wardrobe
dyes are grouped by hue and brightness, with near-identical culture dyes
removed. Option IDs remain independent of display order. Race names are
alphabetical, with female and male entries together.

Validation: 22 geometry/equipment tests (96 subtests), 12 native-asset tests
(1,593 subtests), all 16 rendered creation previews, and all 100 independent
hair choices for both Luminous sexes passed. The broader protocol suite still
has its two existing failures concerning the capability list and Walk/Run
facing; the new hair encoding and backward-compatibility checks pass.

Review artifacts: workspace `work-output/pose-customization`, including the
rendered creation UI and equipped male idle. Source pose measurements remain
in `work-output/luminous-idle-preview/validation.json` and
`work-output/luminous-idle-elbow-preview/validation.json`.
