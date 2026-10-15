# Crowd engine CPU profile

The 300-actor production scheduling fixture spends substantial time in animation and skeleton processing before rendering. In the clean headless Tracy window, `SceneTree::_process` occupies 16.77 ms per process frame, `AnimationMixer::_process_animation` 3.73 ms, and `Skeleton3D::NOTIFICATION_UPDATE_SKELETON` 7.96 ms. These are nested inclusive spans and cannot be added. The matching Forward+ window also exposes 13.13 ms per frame in `RenderingServer::draw` and 3.67 ms in render-device fence waits.

The exact-content `Skin` interning candidate reduces the direct `Skeleton3D::update_skins` span from 0.918 to 0.403 ms per frame headless and from 1.299 to 0.529 ms per frame in Forward+. Its census drops actor-local skin identities from 1,500 to 450 and bind entries from 115,500 to 34,650 while retaining the same 450 actor-local exact-content groups and three global content forms. This is a consistent component-level reduction in these two comparisons, but it cannot by itself close the 60 FPS gap.

## Measured windows

The baseline sessions use the frozen `acceptance-mixed300` fixture at commit `359028002a081d4c66520d08047a9db7633baf2f`, source hash `978b9a7d2233514a71e4a2e33f3ce6ce2887504c152beb14530ff979d05be1e4`. The candidate sessions use commit `01e9af09cf0296bef44c1973c7e82dce1fb81784`, source hash `878a0bcc850ff29fdd55ba94d7e1fb58387a420ab99852fe00bf88f57d017723`. All use the same GDScript scheduling, `NativePresentation=All`, ten-second sample, and CPU affinity mask 15. Marker messages bracket the steady sample outside the measured loop. The analyzer validates the marker PID, cell, frame count, UTC interval, engine interval, and report boundaries before accepting a session.

The reusable profile baseline predates the immediate pre-candidate code commit used by the official-runtime ABBA check, so it is not presented as a same-source disconnected run. The exact commit and source attestations above are retained for that reason. The component comparison relies on unchanged call cadence and the direct `update_skins` zone repeating across both renderer modes; total-frame differences remain subject to the broader source and host variation described below.

| Variant and mode | Frames | Harness wall mean / p95 | Main iteration | Scene traversal | Animation process | Skeleton notification | Skin update | Renderer draw | Fence wait |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| Baseline, headless GL | 522 | 19.09 / 30.39 ms | 19.18 | 16.77 | 3.73 | 7.96 | 0.918 | 0.002 | n/a |
| Candidate, headless GL | 541 | 18.43 / 28.78 ms | 18.52 | 16.17 | 3.76 | 7.33 | 0.403 | 0.002 | n/a |
| Baseline, windowed Forward+ | 220 | 45.40 / 70.23 ms | 45.51 | 26.14 | 4.83 | 9.33 | 1.299 | 13.13 | 3.67 |
| Candidate, windowed Forward+ | 259 | 38.59 / 62.35 ms | 38.69 | 22.09 | 4.12 | 7.78 | 0.529 | 11.68 | 2.90 |

The candidate reduces `update_skins` by 0.516 ms per frame (56.2%) headless and 0.770 ms (59.3%) in Forward+. The inclusive total skeleton notification span falls by 0.630 ms (7.9%) headless and 1.556 ms (16.7%) in Forward+. Call cadence is unchanged at 150 skin updates and 300 skeleton notifications per frame. These direct zone changes support the interning effect. The larger Forward+ changes in animation, renderer draw, and fence waits show that the single baseline/candidate capture pair also contains substantial run and shared-host variation; the 6.82 ms Main difference cannot be assigned wholly to skin interning.

The custom engine was also run without a recorder attached. Headless reported 18.35 ms mean, 30.11 ms p95, and 41.19 ms p99 across 543 frames. Forward+ reported 43.06 ms mean, 71.30 ms p95, and 88.90 ms p99 across 232 frames. The captured runs reported 19.09/30.39/42.09 ms and 45.40/70.23/81.81 ms respectively. These gaps combine potential recording overhead with ordinary host variation; they do not isolate either effect and do not compare the custom runtime with the official runtime.

Selected baseline named-zone results, in milliseconds per process frame:

| Stage | Headless inclusive / self | Forward+ inclusive / self | Calls per frame |
|---|---:|---:|---:|
| `AnimationMixer::_process_animation` | 3.727 / 0.920 | 4.835 / 1.788 | 150 |
| `AnimationMixer::_blend_process` | 2.182 / 2.182 | 2.407 / 2.407 | 150 |
| `AnimationMixer::_blend_apply` | 0.622 / 0.622 | 0.632 / 0.632 | 150 |
| `Skeleton3D::NOTIFICATION_UPDATE_SKELETON` | 7.956 / 0.567 | 9.332 / 0.611 | 300 |
| `Skeleton3D::_process_modifiers` | 3.238 / 0.298 | 3.613 / 0.304 | 300 |
| `Skeleton3D::emit_skeleton_updated` | 2.298 / 0.297 | 2.849 / 0.310 | 150 |
| `Skeleton3D::_force_update_all_bone_transforms` | 0.993 / 0.993 | 1.025 / 1.025 | about 237 |
| `Skeleton3D::update_skins` | 0.918 / 0.918 | 1.299 / 1.299 | 150 |

The 150 animation, emit, and skin-update calls per frame and 300 skeleton notification/modifier calls per frame in both variants confirm that the profile retained the real scheduling cadence. The profile is not a synthetic loop around engine APIs.

Source-aware script zones further separate modifier work in the headless trace. `cape_cloth.gd::_process_modification_with_delta` runs 75 times per frame and occupies 2.769 ms inclusive, with 0.175 ms self. `weapon_carry_pose.gd::_process_modification_with_delta` runs about 38 times per frame and occupies 0.113 ms inclusive. `combat_presentation_3d.gd::update_pose` runs about 91 times per frame and occupies 2.091 ms inclusive, with 0.571 ms self. These callbacks are nested in the skeleton stages; their inclusive values must not be summed with `_process_modifiers` or `emit_skeleton_updated`. Their call counts also show that a notification count alone cannot be treated as proof that every offscreen actor performs the same callback work.

## Reproducible engine and tools

The existing executable reports `4.7.2.stable.official.ed1daf0bf`, but the 4.7.2 release provides no Windows symbol archive. The usable route was therefore an exact-tag local build from commit `ed1daf0bf001b61586d9930840f2f1394092c079`. The official source archive SHA-256 is `a18ce0ccec3ecc40b0dd6c4f5132ca934e9fb7c2979717940ff32aee1eb35481`.

The profiling runtime is `4.7.2.stable.custom_build.ed1daf0bf`, SHA-256 `0e8401142bfafcd268d68ea382116741dc7341a4d95fa871b71044e86821ab32`. It is a `template_release production=yes` MinGW GCC 16.2.0 build with embedded DWARF, Tracy 0.13.0 on-demand zones, all Godot modules, and Vulkan/Forward+ support. D3D12 and ANGLE are disabled. GDB resolves the custom zones to `AnimationMixer::_process_animation`, `Skeleton3D::_process_modifiers`, and `SceneTree::_process_group` source lines.

The exact build configuration and source patches are in:

- `scripts/engine-profile/build-config.json`
- `scripts/engine-profile/godot-4.7.2-tracy-crowd-zones.patch`
- `scripts/engine-profile/tracy-0.13.0-mingw-sleep.patch`
- `scripts/engine-profile/README.md`

Windows `ar` could not consume a generated renderer object at a 269-character canonical path. The build therefore uses an ignored worktree-root `ep` junction pointing at `godot-client/test-artifacts/engine-profile`. This shortens generated paths without moving the canonical artifact directory. The final executable remains under `test-artifacts/engine-profile/godot-4.7.2-stable/bin`.

The engine patch adds bounded Tracy zones to scene traversal, animation mixing, skeleton finalization/modifiers, and skin updates. Render and wait zones in this report already existed in the engine. The patch also forwards only `ELORIA_CROWD_ENGINE_PROFILE` lines into trace messages. The production build normally removes path override support, so the patch enables `OVERRIDE_PATH_ENABLED` only in the two Windows-relevant translation units that serve the existing `--path` launcher.

The stable capture build defines `TRACY_NO_CALLSTACK` and `TRACY_NO_SYSTEM_TRACING`. An earlier callstack build linked and resolved DWARF, but repeatedly terminated with Windows status `0xC0000409`. A bounded GDB run localized the fault to MinGW pthread nanosleep called from Tracy's DXT1 compression worker. The Tracy patch uses Win32 `Sleep()` for millisecond waits on Windows and preserves `std::this_thread::sleep_for` elsewhere. With the patch, 10 of 10 direct version launches and 5 of 5 normal 120-frame SceneTree lifecycles passed. This is a profiling-tool compatibility patch, not evidence of a Godot gameplay defect.

`scripts/run_tracy_crowd_profile.ps1` runs a disconnected baseline and a capture with a 45-second recorder lifetime and at least 60 seconds of post-report grace. The recorder and engine are verified through their exact process handles, executable paths, start times, and affinity. `scripts/finalize_tracy_crowd_profile.ps1` can resume export and analysis from a valid existing trace, so postprocessor failures do not require replaying the workload. `scripts/analyze_tracy_crowd_profile.py` streams focused CSV exports and retains events only when their true inclusive spans overlap validated sample windows.

## Evidence paths

The reusable headless baseline for a candidate comparison is:

`test-artifacts/native-crowd/engine-tracy-headless-all-v2-disconnected-primary-gdscript-gl_compatibility-headless-trial1-20260919T173828181Z.json`

The clean headless captured report is:

`test-artifacts/native-crowd/engine-tracy-headless-all-v4-captured-primary-gdscript-gl_compatibility-headless-trial1-20260919T174252313Z.json`

Its session is `test-artifacts/engine-profile/captures/20260919T174250149Z-headless-gl_compatibility`; trace SHA-256 is `98cc339dd4b21c59c5de4b1f4392e93bcbb81cd7b844de565cbd9d7bb9cd8fa3`.

The reusable Forward+ baseline is:

`test-artifacts/native-crowd/engine-tracy-forward-all-disconnected-primary-gdscript-forward_plus-windowed-trial1-20260919T174814451Z.json`

The clean Forward+ captured report is:

`test-artifacts/native-crowd/engine-tracy-forward-all-captured-primary-gdscript-forward_plus-windowed-trial1-20260919T174854646Z.json`

Its session is `test-artifacts/engine-profile/captures/20260919T174812814Z-windowed-forward_plus`; trace SHA-256 is `a4767d5e774754171388908367460bc6c6a3e2c8ede38d9180452e5f2d67ff1a`.

The candidate headless captured report is:

`test-artifacts/native-crowd/engine-tracy-skin-intern-candidate-captured-primary-gdscript-gl_compatibility-headless-trial1-20260919T180756803Z.json`

Its session is `test-artifacts/engine-profile/captures/20260919T180754135Z-headless-gl_compatibility`; trace SHA-256 is `3c5670a54b1d6b2e3eac9f11d464bade247d76efaf4be7a908fa51cd0becfaa5`.

The candidate Forward+ captured report is:

`test-artifacts/native-crowd/engine-tracy-skin-intern-candidate-captured-primary-gdscript-forward_plus-windowed-trial1-20260919T180933268Z.json`

Its session is `test-artifacts/engine-profile/captures/20260919T180930579Z-windowed-forward_plus`; trace SHA-256 is `a523adf93bb9f4e7809c9bdb4e2790e1fba5768dc48868067ad5e45271d9a19a`.

Each process report records a clean exit, valid benchmark report, no forced post-report stop, the expected PID, commit, and source hash. The compact machine-readable result is `docs/benchmarks/crowd-engine-profile-2026-09-19.json`. Raw traces, focused CSV exports, and logs stay in ignored test artifacts.

## Limits and prior failures

- The custom production template is optimized differently from the checked-in official editor/debug-enabled executable. Its wall time cannot be presented as an optimization relative to the official runtime.
- Tracy instrumentation can add overhead, and the host was shared. The observed captured/disconnected gaps combine potential recording overhead with host variation. The recorded interference label is `shared host; unrelated Godot jobs authorized; activity not continuously monitored`.
- Named-zone durations are wall-clock spans and can include scheduler preemption and waits; they are not CPU-cycle accounting. Sampled call stacks and context-switch/system traces are absent, so unzoned residual time remains unattributed.
- Whole-trace aggregates include roughly 14,000 startup frames in the headless session. All hotspot numbers above come only from the marker-bounded steady window.
- Each profiling variant has one marker-bounded capture per renderer. Component changes repeated across both renderers are stronger evidence than total-frame differences; neither pair is a statistical performance distribution.
- Inclusive child zones overlap their parents. Forward+ draw, stalls, and fence waits also overlap, so subtracting or summing them as a flat CPU budget would be misleading.
- Tracy CSV `exec_time_ns` is the inclusive span in the default export and the exclusive duration only in `-e` self exports. Because the exclusive duration is not a contiguous interval, the analyzer omits self time for events crossing a sample boundary and reports the omitted count.
- Early setup failures included a missing isolated SCons module, the long-path archive failure, missing `dbghelp` linkage, the Tracy/MinGW worker failure, and a production `--path` rejection. Each was resolved without changing the benchmark schedule. A 240-second recorder paired with a shorter report grace also held the engine open; the stable wrapper uses a 45-second recorder and a grace longer than the recorder lifetime.

The official upstream references for this route are Godot's [profiling guide](https://docs.godotengine.org/en/4.7/engine_details/development/profiling/), its [Tracy integration guide](https://docs.godotengine.org/en/4.7/engine_details/development/profiling/tracy.html), and the [Godot 4.7.2 release](https://github.com/godotengine/godot/releases/tag/4.7.2-stable).
