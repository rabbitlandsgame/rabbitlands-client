# Reviewed animation set for imported bears

Obsidian Bear, Crystal Polar Bear and Owlbear use the reviewed Walk, Jog and death transfers plus the final high descending two-claw attack. The attack has a shorter apex, restrained sideways travel, straight arms through the descending pair and claws rolling from upward to downward. It plays at its authored 1.90-second duration through the existing `Sword_Attack` action slot. Rejected attack choices are kept only in the ignored authoring workspace.

Each bear has its own action map with measured stride speed at its existing import scale, and opts into actor-scale stride adjustment. Registry IDs, scene paths, attachment configuration and facing/import transforms are retained. Moss Bear and its approved animation set are unchanged. This client asset change does not alter server combat scheduling or damage events.

The packed runtime assets retain reviewed geometry, textures, skin, rests and binds. Obsidian includes its reviewed 80-vertex paw-weight preparation and forward face alignment; nonface idle/hit motion is preserved. Crystal Polar Bear's inherited idle/hit curves remain exact. Owlbear's inherited idle animates an armature-object translation that the bone-only runtime loader omits: promotion moves that translation into the existing root-bone track, preserving its visible world motion and skin at source keys and half-keys. Constant scale channels are retained and included in independent world-pose evaluation.

Tracked import policies use 1536 Hz with animation optimizer/compression disabled. The runtime files contain seven selected slots, without approximate curve reduction. `docs/qa/ursine-family-motion` binds packed hashes to exact reviewed curve/static comparisons (and Owlbear's explicit idle world rebase), source contact/extension checks, fresh Blender import, and current scene-cache/native-library/action-resolver playback for all21 slots. The isolated probe also verifies the unchanged seven Moss Bear slots. This is focused component integration, not a full client/server session.

After importing the project, run:

```powershell
godot --headless --path godot-client --script tests/test_ursine_family_motion.gd
```

`eloria-assets/tools/promote_ursine_motion.py` accepts an explicit reviewed local delivery and ignored output directory; `--apply` installs its checked result. High-resolution models, source videos, working checkpoints and authoring logs remain Git-ignored under `.local/asset-authoring/`.
