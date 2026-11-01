# Swan grounded idle motion

The Swan's `Idle_A` and `Fighting_Idle` previously looped a completely static
pose. This revision gives each a restrained neck scan, nod and chest rise.
The feet remain planted and the wings remain folded. It addresses the confirmed
static-idle part of stream issue RL31-11; a second failure in live Gauntlet
combat has not been established or ruled out.

Only `neck_01:rotation` and `spine_02:translation` change in those two clips.
The original mesh, skin, rest/binds, textures, materials, IDs, import scale,
clip names and durations remain exact. All six other native animations,
including Fly, retain their original animation records and binary payload.
The ordinary GLB grows from 605,324 to 610,124 bytes; no bone, surface or
corrective target is added. New curves stay at or below 24 samples per second;
the existing 30 Hz native import policy is retained.

The [hash-bound receipt](swan-idle-motion.json) records the selection and checks.
The earlier October 28 visual approval still identifies the previous exact
file. It is preserved under `previousRuntimeVisualAcceptance` in the current
action map and roster. This task's technical and implementation visual review
does not manufacture a new user approval.

Independent GLB skin evaluation covers 718 states across both idles, including
every authored key, midpoint and shifted-time samples. Measured foot
displacement and added coincident seam gaps are zero;
head motion reaches 16.0 mm in idle and 11.0 mm in combat idle. Both loops close.
The production Godot test passes 17 checks, including independent off-grid
joint witnesses, sustained motion, looping, attack/hit recovery, stepped
animation tiers, return to view and held death. The independent witness differs
from native playback by at most 0.054 mm in joint position.

The actual client comparison covers 490 states and 56 directed action switches,
including first-tick and frame-stepped blends. All 66 sampled poses in the
untouched clips match the old runtime exactly, as do configured default and
RESET. A separate two-actor continuous probe passes all 16 phases at full,
half and quarter animation rates, offscreen/return, repeated attacks and death.
Fresh Blender imports of both files pass finite-action checks. Normal-speed
cycles and multiple camera views were reviewed in the synchronized production
actor viewer. Raw client loading is the production loose-asset path; this is
not a claim about editor PackedScene import or full-session performance.

The older generic creature validator applies a different material/root/scale
contract. Its findings are identical before and after this change and are not
reported as a successful check. Original authoring witnesses and historical
delivery receipts remain unchanged; this revision has its own independent
fixture and receipt.

To replay, recover the public baseline from commit `c78751a2` into an ignored
stage (binary-safe Git output), then run:

```text
python eloria-assets/tools/refine_swan_idle.py --source .local/swan-idle/baseline.glb --output .local/swan-idle/candidate.glb --report .local/swan-idle/authoring.json
python eloria-assets/tools/check_swan_idle.py --source .local/swan-idle/baseline.glb --candidate .local/swan-idle/candidate.glb --report .local/swan-idle/checks.json
```

The authoring command rejects another baseline hash, source overwrite or an
existing candidate. An independent replay produced byte-identical output.
With the supported Godot executable, run `res://tests/test_swan_idle_motion.gd`
using `--headless --path godot-client --script`. The existing comparison viewer
accepts the two explicit GLB paths and provides synchronized clip selection,
orbit, zoom, scrub, pause and playback speed controls.
