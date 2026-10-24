# Completed creature animation draft baseline

Forty-seven completed creature sets are installed as updated draft baselines. They cover the original two wolves, three further wolf-like mammals, twenty birds, six reptiles, fifteen other land mammals and Walrus. Their 339 available native clips include seven mapped actions per actor and ten retained flight clips. Publication does not mark their artistic reviews approved.

Each actor uses its own action map at native speed. Ground travel uses the authored stride and cycle duration at the unchanged import scale, including runtime actor scaling. The original wolf walk speeds come from their accepted contact solves; their existing native run curves remain available. Registry forward correction and visual backset are preserved. Invalid generic body/neck attachment names are replaced with matching native controls.

The sixteen newest mammals and three wolf-like transfers use their qualified anatomical preparations. Earlier flexible corrective drafts use measured position subset bases and actual unit-normal poses, retaining the original corrective prefix and every joint knot. Base geometry, UVs, skin, binds, materials and texture bytes match each selected prepared draft. High-resolution originals, dense authoring stages, recipes, provider records and review videos remain in the ignored authoring workspace.

The complete runtime files total about 1.22 GB, reduced from 2.57 GB of selected authoring exports without reducing textures. Some flexible corrective rigs remain large: Snapping Turtle is about 102.2 MB (97.5 MiB). These are fidelity-qualified game assets; further crowd-memory and frame-rate profiling remains separate from this animation integration.

Whole-surface conformance passes for all 45 family drafts. Across the optimized models, the largest measured position difference is under 0.000061 of native height and the largest normal-vector difference is under 0.00255. The largest 95th-percentile added planted-foot velocity is under 0.11% of ground speed. The original two wolf pilots preserve newer unrelated clips and the accepted centered Moorland tail. Their ignored object-level run bob is baked into the root skin joint; all-key and midpoint complete-surface differences remain below 0.00000006 native units.

The checks use exact final hashes. Native checks cover all 47 models, mapped actions, retained clips, actual influence budgets, unsigned joint accessors, attachment names, import policy and independent off-grid bones, surfaces and normals. Fresh Godot 4.7.2 checks cover the actual scene-cache/native-library paths, loops, one-shot endpoint holds, attack switching, RESET and independent imported surface normals. Fresh Blender 5.2.1 checks cover every available clip with independent bone and posed-surface probes. Multi-part retained flight uses original corrective signatures to distinguish overlapping feathers. Headless qualification does not claim a full game session or new human acceptance.

Run these from the repository root:

```powershell
python -B eloria-assets/tools/test_completed_creature_motion.py
python -B tools/asset-authoring/test_creature_review.py
```

After importing the Godot client, run `tests/test_completed_creature_motion.gd`. The standalone Blender probe is `eloria-assets/tools/check_completed_creatures_blender.py`; pass `--root` and `--report` after Blender's `--` separator. Optional `--actor` limits each check to a single creature. Hash-bound results are in `docs/qa/completed-creature-motion/`.

Use `review-creature-animations.bat` for the local review catalog and persistent per-creature/per-animation comments. Existing media versions and comment keys survive installation; the installed runtime hash is recorded separately. All pending reviews remain pending. The completion queue is paused after Walrus, with Manatee's existing anatomy assessment preserved for an explicit resume.
