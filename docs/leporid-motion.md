# Rabbit-family motion

Rabbit and Jackalope use the reviewed small hop, faster bound, attack and death from the authored rabbit-family pilot. Rabbit attacks with a forward hop-lunge; Jackalope lowers its antlers into the strike. The collapse folds the supporting forelegs, releases each support pair, falls onto its side and holds. These rigs have no independently articulated jaw.

The motion was authored after four local open-weights video attempts failed the motion-source review. No generated video supplied these animation curves. High-resolution sources, videos, rejected experiments and fitting stages remain in the private ignored authoring workspace.

Runtime GLBs are byte-identical to the reviewed selection. Geometry, native rest/bind transforms, textures and all 25 Jackalope corrective targets are retained. Rabbit's ear/muzzle ownership and Jackalope's foreleg transitions use the reviewed shared-skin repairs. Idle, fighting idle and hit joint/morph arrays remain exact; their surfaces intentionally use that corrected shared skin. New actions explicitly neutralize corrective weights, and RESET/action switching is checked.

Native movement uses each species' `Jog` hopping clip, matching the Giant Meadow Rabbit mount's normal and fast movement. Ordinary movement caps at 1.8 hops per second; running and haste cap at 2.6. The action maps use the measured `Jog` stride at the unchanged registry import scale, and `strideScalesWithActor` applies the existing runtime creature enlargement and server scale. These presentation caps keep short strides readable at game travel speeds; the server still controls ground speed. The authored `Walk` clip remains available to mount walking and authoring tools. Stable IDs, model paths, facing and attachments are unchanged. The attack lasts 1.65 seconds and death 2.50 seconds; the existing game command and interruption behavior still applies. This change does not alter server damage or attack scheduling.

Both assets declare a 3072-Hz glTF bake cadence, matched by narrowly tracked import policies. Optimization and animation compression are disabled. Exported keys and between-key poses pass full-surface floor, planted-sole, native-length, loop/hold and physical muzzle/body support checks. Fresh Blender imports agree with independent joint samples. A fresh isolated project using the actual client scene cache, native importer and action resolver checks all 14 slots, corrective shapes, off-grid GLB worlds, loop behavior, terminal holds and restoration. This is focused component integration evidence, not a full client/server session.

Evidence is in `docs/qa/leporid-motion/`: the selection/preservation receipt, per-actor contact patches, qualified export metrics, scoped skin repair, same-pose deformation comparison, fresh Blender import and runtime playback report. Global edge strain is a diagnostic, not an artistic score. The public fixture binds independent poses and corrective weights to the exact runtime GLBs.

From the repository root:

```powershell
python eloria-assets/tools/test_leporid_motion.py
```

After importing the project, run:

```powershell
godot --headless --path godot-client --script tests/test_leporid_motion.gd
godot --headless --path godot-client --script tests/test_leporid_locomotion.gd
```

The engine check can also use an isolated project containing these two assets and their unchanged registry entries, maps, fixture and current client component scripts. This verifies exact known rigs; adding another anatomical category requires its own native profile and review.
