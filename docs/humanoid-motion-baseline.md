# Humanoid animation baseline

Revision 10 installs 40 creatures across eight families as an improved baseline in develop. The user authorized this integration while explicitly retaining further edits. This is an iterative selection, not final artistic acceptance. The local revision-10 review remains the reference for the next editing pass.

| Family | Creatures |
| --- | ---: |
| Beastfolk | 4 |
| Undead | 6 |
| Armored warriors | 9 |
| Stone golems | 6 |
| Giants | 3 |
| Woodland humanoids | 5 |
| Treants | 3 |
| Winged humanoids | 4 |

The registry keeps stable actor IDs, model paths, import transforms and attachments. Each creature has a dedicated map under `godot-client/data/animations/humanoid-baseline/`. Walk, run, primary attack and death play at the reviewed speed. Grounded stride speed uses measured complete-sole travel and model import scale; it also follows runtime actor scaling. Root glides, hover forms and the Harpy retain their explicit non-grounded interpretation. Existing server commands and damage scheduling are unchanged. Dedicated ground-pound attacks and all retained native actions remain available: 288 clips in total.

## Runtime export

Raw high-resolution authoring models, renders, fitting stages and provider records remain in the ignored asset-authoring workspace. Only processed runtime GLBs are installed. Their combined size is about 815 MB; the largest is 85.3 MB. Further runtime size and rendering-cost optimization remains possible and requires new fidelity checks.

`video_motion.runtime_shapes` retains base geometry, topology, textures, materials, hierarchy, binds, rest transforms and native joint curves. Oversized skin layouts are packed to eight influences. Eight rigs need pose-space compensation for dropped influence contributions; the correction is sampled over all native actions. Drowned Pirate's twelve stored slots contain only seven active influences and can be packed without dropping active weights.

Animated corrective position and normal fields use a bounded positive affine basis. Signed coefficients alone are unsafe when an importer clamps weights. A constant bias shape and coefficients in [0,1] preserve both signed deformation and authored defaults. RESET must restore those defaults rather than setting every corrective weight to zero. Thornwood uses a measured 640-vector prefix plus the bias to meet the runtime file-size limit, with total local fitting error below 0.000077 of native height. Its report records this approximation explicitly.

Example rebuild with a preserved local reviewed input, from the client root:

```powershell
$env:PYTHONPATH='eloria-assets/tools'
python -m video_motion.runtime_shapes --source <reviewed.glb> --output <runtime.glb> --height <native-height> --report <packing.json>
python -m video_motion.runtime_validation --source <reviewed.glb> --runtime <runtime.glb> --height <native-height> --report <conformance.json>
```

Use `--basis-prefix 640` only for this measured Thornwood recipe. The tool rejects a prefix that exceeds its total error budget. Rebuilds require the pinned local authoring input; source models are deliberately excluded from Git. New output hashes need fresh native and engine receipts. Other rigs and bases require their own qualification.

## Verification and limits

The [manifest](qa/humanoid-motion-baseline/manifest.json) binds reviewed input hashes, final runtime hashes, mappings, cadence, measured gaits and per-actor export comparisons. The [native report](qa/humanoid-motion-baseline/native.json) and [Godot report](qa/humanoid-motion-baseline/godot.json) cover all 40 installed models and 288 native clips.

All-vertex native comparisons cover rest and 18 key/off-grid samples per clip. Fixed complete-sole fields are compared at 513 samples per gait, including active correctives. Maximum sampled export surface error is 0.0000284 of native height. The largest added p95 sole velocity is 0.35% of travel speed. These are preservation measurements against revision 10, not claims of perfect gait naturalness.

Fresh isolated Godot imports use the current client scene cache, native animation importer and action resolver, with the actual installed registry entries, maps and tracked import policies. Six independent off-grid pose/surface witnesses per clip cover both engine paths, finite poses, loop policy, one-shot terminal holds, attack switching, idle restoration and RESET. Import cadence is 4096 Hz for these models; optimizer/compression are disabled. Thornwood's small late-run corrective coefficients exhibit a maximum 0.000134 weight discrepancy despite higher bake cadences. The coefficient guard is 0.0002, alongside independent surface and bone guards; the surface comparison remains authoritative across basis changes.

This is focused animation-component integration. It is not a full client/server playthrough or a rendering-performance certification of all 40 models together. Continue visual edits using multiple angles, fixed physical left/right sole fields and common reconstructed ground motion, especially for the previously flagged spectral knights, Living Armor and Thornwood.

Run the portable checks after a change:

```powershell
python -m pytest eloria-assets/tools/test_runtime_shapes.py eloria-assets/tools/test_native_shape_matrices.py -q
python eloria-assets/tools/test_humanoid_baseline.py --report <native-report.json>
# After the normal project resource import:
godot --headless --path godot-client --script res://tests/test_humanoid_baseline.gd -- --report=<godot-report.json>
```

Both baseline checks accept `--actor <stable-id>` (Godot: `--actor=<stable-id>`) for a focused iteration. Keep authoring/source validation, runtime export fidelity, engine playback and human artistic acceptance as separate records.
