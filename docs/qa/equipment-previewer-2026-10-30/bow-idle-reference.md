# Bow idle reference

The idle bow now matches the user's annotated reference: its upper limb points
forward/up at approximately 45 degrees, its lower limb trails behind/down, and
the wooden belly curves in front of the string.

Each body calibrates this grip from its own native idle pose at 0.7 seconds,
including the existing shoulder spread. Calibration reads animation channels
without seeking or changing the live rig. The grip remains attached to the
anatomical wrist. After the user accepted the orientation, the handle was seated
20 mm closer to the wrist, higher in the palm. The sleeve/wrist corrections and
approved idle angle are retained.
The existing activity crossfade blends into the movement carry frame. Bow
draw/hold/release continue to use their existing aiming presentation.

Verified on both current bow designs and all 16 body variants: 3,089 wrist,
direction, read-only calibration, live-transition and equip-during-aim checks
pass. Maximum quaternion comparison is 0.000976563 rad, within the existing
floating-point tolerance; maximum wrist-to-grip distance is now 0.077024 m.
The 298 review-fit checks, 21 second-review checks, weapon-carry tests,
catalog/icon tests (6 tests and 1,315 subtests), and graphical self-test pass.

Client visual review includes 36 male/female idle views of both bows at three
times, and 120 race/movement views. The later palm-seat refinement has eight
matched before/after close-ups across
both bows, both Human bodies and front/side angles, plus a fresh pass of all
3,089 wrist checks on all 16 body variants. The bow icons use the rigid sources;
their re-render retains the existing images and the complete 443-record
manifest. Existing optional head-normal fallback and shutdown cache warnings
remain. Selected views and transitions were checked; arbitrary combinations,
appearance sliders and every animation frame are not exhaustive coverage.

No native models, rigs, shared animation clips, textures or catalog records are
changed in this revision. The native geometry receipts from the third review
remain current; this record supersedes its overlapping runtime/test hashes.
`bow-idle-reference.json` binds the source and final implementation to hashes.
The annotated reference, rejected trials and final evidence remain locally
ignored. Technical and visual checks are complete; user artistic approval is
pending. No publication or release is included.
