# Staged video fitting

The user-accepted walk is `fit-v13` / `delivery-v8` (2026-10-14). It includes corrected backward elbows, contact-aware shoulder placement, localized neck/collar/back weight repairs, coherent actor-specific tail motion, and the explicitly centered/rebound Moorland tail. `user-acceptance.json` identifies the exact accepted files. Helpers `center_moorland_tail.py`, `validate_centered_tail.py`, `validate_secondary_motion.py`, `validate_polish.py` and `validate_shoulders.py` reproduce and independently audit the final state. Read [attachments and secondary motion](secondary-motion.md) for scope and transfer policy. Earlier stages remain available.

Run from the project root using Python with NumPy, SciPy, OpenCV and Pillow. Blender creates the actual-model reference and independently reimports exports; live Blender control is optional.

## Reference and video

Copy the source GLB into an immutable stage. Review its actual anatomy and fitted rig.

```powershell
python eloria-assets/tools/video_motion_cli.py inspect --model STAGE/source/wolf.glb --out STAGE/source/wolf.rig.json
& 'C:/Program Files/Blender Foundation/Blender 5.2/blender.exe' --background --python eloria-assets/tools/video_motion/prepare_blender.py -- STAGE/source/wolf.glb STAGE/reference
```

Inspect all four reference views. The renderer excludes custom bone-shape helpers from bounds and saves the orthographic glTF Y-up projection in `camera.json`.

Meshy's website supplies image-to-video; no public video API endpoint was established for this pilot. Use the supported browser upload/download workflow, not undocumented internal requests. For a walk, request a stable full-body side camera, exact construction and limb count, neutral background, no cuts and a steady in-place gait. Record the displayed cost and task ID; never resubmit an unknown job.

New action videos require their own scoped upload and spending authorization. The prior one-job walk approval is not authorization for a new reference image or paid job. Stage the actual corrected-model render, prompts, action contracts and displayed quotes for review before the approval question. If automatic review rejects an upload, explain the specific rejection and obtain explicit image-to-provider authorization; do not route around it.

## Decode and track

```powershell
python eloria-assets/tools/video_motion_cli.py extract --video STAGE/video/reference.mp4 --out STAGE/tracking
python eloria-assets/tools/video_motion_cli.py track --model STAGE/source/wolf.glb --profile STAGE/source/wolf.rig.json --camera STAGE/reference/camera.json --tracking STAGE/tracking --contour-paws
```

`video.json` distinguishes container FPS, sampled timestamps and duplicate-frame cadence. Cadence diagnostics do not change playback speed automatically. `cycle.json` is an editable inclusive interval; inspect per-limb identity before accepting a mask-derived period.

Review `tracking-candidates.jpg` and full frames. Each landmark in `observations.json` has pixel `xy`, confidence, method and review status. Keep occluded/merged feet uncertain. Record left/right corrections explicitly. `anchors` are `{frame, role, xy, confidence}` and interpolate coordinates across their span; two endpoints alone must not flatten a full foot trajectory. Save observations before rerunning tracking, which regenerates candidates.

## Solve, transfer and validate

```powershell
python eloria-assets/tools/video_motion_cli.py fit --model STAGE/source/wolf.glb --profile STAGE/source/wolf.rig.json --camera STAGE/reference/camera.json --tracking STAGE/tracking --initial-clip none --out STAGE/fit-v1
python eloria-assets/tools/video_motion_cli.py retarget --model STAGE/source/second_actor.glb --profile STAGE/source/second_actor.rig.json --motion STAGE/fit-v1/quadruped_walk.motion.json --out STAGE/fit-v1/transfer
python eloria-assets/tools/video_motion_cli.py validate --source STAGE/source/wolf.glb --export STAGE/fit-v1/wolf__video_walk.glb --out STAGE/fit-v1/validation.json
```

`--clip NAME` sets the action, `--initial-clip NAME` selects an optional prior and `--one-shot` retains the endpoint instead of reconciling a loop. The initial output filenames retain `walk`; read the package's `clip` field. The package is sampled from the video interval; exports may contain additional keys for surface contact.

The validator independently reads the GLB, checks structure and original bytes, preservation of unrelated actions, quaternion norms, bone lengths, loop closure and sampled floor clearance. Fresh Blender import, Godot playback, stance direction, foot slide, deformation and normal-speed readability remain separate gates. Keep pilot candidates out of runtime assets until accepted for that purpose.

For an existing short-stride or sliding walk, prepare a reviewed gait JSON and versioned actor profiles, then run:

```powershell
python eloria-assets/tools/video_motion_cli.py polish --model STAGE/source/wolf.glb --profile STAGE/fit-v2/wolf.rig.json --motion STAGE/fit-v1/quadruped_walk.motion.json --gait STAGE/fit-v2/source-gait.json --out STAGE/fit-v2
python eloria-assets/tools/video_motion_cli.py retarget --model STAGE/source/second_actor.glb --profile STAGE/fit-v2/second_actor.rig.json --motion STAGE/fit-v2/quadruped_walk.motion.json --out STAGE/fit-v2/transfer
```

The version-2 path solves at 96 samples per second and exports at 192 by default. Unlike the initial bake, it keeps solved paw contact and does not add a global body lift. Independently evaluate contacts at 384 samples per second for the final report. Read [contact polish](contact-polish.md) for the gait fields, target adaptation and measurement definitions. The wolf stages preserve the stride/contact baseline (`fit-v7`), folded swing (`fit-v8`), and shoulder placement (`fit-v9`, `delivery-v4`). The selected delivery's report and hashes are authoritative.

The shoulder revision's local helpers are `refine_shoulders.py`, `adapt_target_shoulders.py`, `finalize_shoulders.py` and `validate_shoulders.py` in the pilot stage. They retain the preceding cadence/sole trajectories and carry reviewed shoulder intent in the motion JSON, with deformation and body-height corrections in the actor profiles. The backward elbow and localized neck-skin correction is `fit-v10` / `delivery-v5`, using `refine_elbow_direction.py`, CLI retargeting and `finalize_elbow_fix.py`. Its repaired source template and changed-vertex report live under `fit-v10/rig-repair`; this repair is not applied to target actors. For new actors, use the CLI `retarget` with a reviewed native profile; the pilot-specific helpers are not universal rig defaults. The final Godot probe checks a nonzero Walk pose and restoration to the baseline Idle pose, rather than only checking the current clip name.
