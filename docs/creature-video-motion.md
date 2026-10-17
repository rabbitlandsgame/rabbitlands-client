# Reference motion for canine creatures

The seven family actors now use the selected revision-5 Walk, lunge/bite and death fits. Their repaired foreleg ownership, centered physical tails, native jaw policies and body pivots are included. Existing scene paths, stable actor IDs, attachments, import scales and facing corrections are retained. Each actor has a dedicated action map; all seven original runtime slots remain available.

The four other clips (Idle_A, Fighting_Idle, Hit_Chest and Jog) came from the current Rabbit Lands client, which had newer native animation refinements than the fitting pilot's baseline. They were preserved in world space through the repaired rig. Static inserted parent transforms were rebased exactly to float precision. Thornhide's reparented hind toe required a dense local bake; its independently checked original-joint world-matrix error stays below 3.3e-6. New controls receive neutral keys and the runtime generates RESET tracks.

The fitted clips retain every nonconstant value and timestamp. Only exactly constant LINEAR/STEP samplers retain their two original endpoint samples. Unreachable accessors and old appended buffers were removed; mesh/skin/bind arrays, rest transforms and embedded image bytes match the selected fits exactly. Runtime models are about 5–6 MB each. There is no approximate curve reduction. Do not use geometry-only duplicate pruning on animation changes.

Dedicated import settings disable animation optimization and compression, including on a clean checkout. Godot also bakes glTF animation at 30 Hz by default: disabling optimization alone did not preserve the fitted motion. These assets declare `asset.extras.rabbitlands_animation_bake_fps` (1536, or 3072 for Thornhide's rebased toe), matched by tracked import settings and both raw loading paths. Independent off-grid GLB world-pose witnesses verify the engine result; comparing two engine imports alone would miss a shared resampling error.

Both JOINTS/WEIGHTS sets are retained and checked in the actual engine mesh. Each walk map stores measured native stride speed multiplied by import scale. The opt-in `strideScalesWithActor` also accounts for the existing small-creature enlargement (notably Red Fox) and server scale. Other action maps keep their previous behavior. The existing travel-speed clamp still applies at extreme travel rates.

The five-second attack preserves anticipation, launch, bite, landing and recovery. It follows existing game interruption/attack-command behavior; this asset change does not alter server attack scheduling or damage timing. Death preserves its early supported fold and settled hold. A one-shot's airborne translation is authored body motion within an in-place action, not accumulated locomotion root motion.

Evidence under `docs/qa/canine-motion` distinguishes:

- `selected-fit-validation.json`: original qualified contact/clearance evidence. Runtime inheritance is justified by exact fitted channel and static-array equality in `promotion.json`.
- `promotion.json`: current-runtime provenance, original-joint preservation, packed file hashes, exact fitted-channel receipts and measured walk speeds.
- `runtime-playback.json`: fresh import with actual client scene-cache/native-library/action-resolver components, all 49 clips, eight influences, finite poses, import/native agreement, independent off-grid world-pose witnesses, terminal holds and idle restoration. This focused probe does not claim a full game or server test.
- `portable-replay.json`: all seven offline package replays, checked against runtime at fitted keys and half-keys.
- `deformation-comparison.json`: numerical deformation tradeoffs from the selected multi-angle review. Five attacks improve fixed original foreleg strain; Mossbound and Fox increase. Six acceleration metrics improve; Moss Armored increases. These are not universal artistic scores.

The user requested merging this development revision. Prior review acceptance labels remain in the authoring records; numerical checks and publication authorization do not retroactively create a blanket artistic-approval receipt. Original source and rejected intermediate fits remain preserved privately.

Focused validation from the repository root:

```powershell
python eloria-assets/tools/test_video_motion_promotion.py
godot --headless --path godot-client --script tests/test_canine_video_motion.gd
```

Import the project before running the engine probe. The same probe can run in an isolated project containing these seven assets, their maps and the unchanged client component scripts. Use the creature-animation skill for anatomical audit and new category fitting; replay alone is for these exact prepared rigs.
