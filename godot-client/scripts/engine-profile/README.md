# Godot 4.7.2 Tracy crowd profile

This setup builds an optimized, symbol-bearing Godot runtime and captures the
primary 300-actor crowd schedule with Tracy. It is diagnostic evidence. The
runtime is a `template_release production=yes` build, while the checked-in
official runtime is editor/debug-enabled, so their wall times are not directly
comparable.

## Exact inputs

- Existing runtime reports `4.7.2.stable.official.ed1daf0bf`.
- Official tag `4.7.2-stable` resolves to
  `ed1daf0bf001b61586d9930840f2f1394092c079`.
- Official source URL:
  `https://github.com/godotengine/godot/releases/download/4.7.2-stable/godot-4.7.2-stable.tar.xz`
- Source SHA-256:
  `a18ce0ccec3ecc40b0dd6c4f5132ca934e9fb7c2979717940ff32aee1eb35481`
- Tracy source tag: `https://github.com/wolfpld/tracy/tree/v0.13.0`
- Tracy source archive SHA-256:
  `b0e972dfeebe42470187c1a47b449c8ee9e8656900bcf87b403175ed50796918`
- Tracy Windows tools URL:
  `https://github.com/wolfpld/tracy/releases/download/v0.13.0/windows-0.13.0.zip`
- Tracy Windows tools SHA-256:
  `3872f4644c2d8f973076484314b189795e4b67d56b13778fe8ab9c2fea4024fb`
- Local toolchain: MSYS2 MinGW GCC 16.2.0 and GDB 17.2.
- Local SCons: 4.10.1 installed with `pip --target` below the ignored artifact
  directory, with no global installation.

The 4.7.2 release has no Windows symbol archive. Its symbol assets are Android
only. Building the exact tag is therefore the reproducible Windows route.

## Source patch and build

Extract the source and Tracy 0.13.0 under
`godot-client/test-artifacts/engine-profile`, then apply
`godot-4.7.2-tracy-crowd-zones.patch` from the engine source directory with
`patch -p1`, and apply `tracy-0.13.0-mingw-sleep.patch` from the Tracy source
directory with `patch -p1`. The patches add bounded zones for scene traversal, animation mix,
skeleton finalization/modifiers and skin binding updates. It also forwards only
`ELORIA_CROWD_ENGINE_PROFILE` lines to Tracy messages, and adds `dbghelp` for
the MinGW Tracy Windows client in a production template.

Windows `ar` failed on a generated renderer object whose canonical path was 269
characters. Create the ignored worktree-root junction `ep` pointing to
`godot-client/test-artifacts/engine-profile` and run SCons through that short
path. This preserves the canonical artifact location while keeping generated
paths below `MAX_PATH`.

The exact build arguments are:

```text
-j4 platform=windows target=template_release production=yes
debug_symbols=yes separate_debug_symbols=no use_mingw=yes
profiler=tracy
profiler_path=C:/rabbitlands/rabbitlands-client/ep/tracy-0.13.0
profiler_sample_callstack=no profiler_record_on_demand=yes
d3d12=no angle=no scu_build=yes
disable_path_overrides=yes
```

All Godot modules and Vulkan/Forward+ remain enabled. D3D12 and ANGLE are
disabled because their external SDKs are not required for this profile. The
`template_release` target preserves the ABI expected by
`native_crowd.windows.template_release.x86_64.dll`.
The production default keeps the global path-override define disabled. The
profiling patch enables `OVERRIDE_PATH_ENABLED` only in `main/main.cpp` and
`core/config/project_settings.cpp` on Windows, the only relevant translation
units. This provides the `--path` behavior required by the existing benchmark
launcher without changing every compiled object.

Callstack sampling is disabled. The equivalent build with
`profiler_sample_callstack=yes` linked after adding DbgHelp and resolved DWARF
symbols under GDB, but repeatedly aborted outside GDB with Windows status
`0xC0000409` and `*** stack smashing detected ***`, including before project
startup. Disabling per-zone callstacks alone remained flaky in 3 of 10 version
launches. The Tracy client is therefore compiled with `TRACY_NO_CALLSTACK` and
`TRACY_NO_SYSTEM_TRACING`; named Tracy zones are the supported evidence from
this build, and sampled call stacks/context switches are deliberately absent.
The patch also routes TracyProfiler.cpp's millisecond waits through Win32
`Sleep()` on Windows. A symbolized intermittent `0xC0000409` fault occurred in
MinGW's pthread nanosleep beneath Tracy's DXT1 compression worker; non-Windows
builds retain `std::this_thread::sleep_for`.

## Capture and analysis

`../run_tracy_crowd_profile.ps1` first runs the same custom engine with no
profiler attached, then captures a second diagnostic run. Its defaults use the
primary profile, GDScript scheduling, `NativePresentation=All`, trace-native
sample boundary messages, one repeat, a 45-second recorder, at least 60 seconds
of post-report grace, and process affinity mask 15. The recorder lifetime must
end before the grace period: Tracy keeps the client alive while a recorder is
connected. Run the wrapper once headless with `gl_compatibility`, then once
windowed with `forward_plus`.

Each capture session contains the raw `.tracy` file, aggregate zones, unwrapped
inclusive and self-time zones, marker messages, runner output and a manifest.
Run `../analyze_tracy_crowd_profile.py <session>` to clip zone events to the
paired marker timestamps. The analyzer does not assume that Tracy frame indices
match `Engine.get_process_frames()`. Inclusive values overlap for nested zones
and are reported independently.

If capture and the benchmark completed cleanly but a later export or analyzer
step failed, resume from the existing session instead of rerunning the workload:

```powershell
../finalize_tracy_crowd_profile.ps1 -Session <capture-session> `
  -DisconnectedRunId <matching-disconnected-run-id>
```

The finalizer verifies the clean process report and preserves the source
attestation plus any engine path/hash recorded by the capture wrapper. If an
export failure occurred before that manifest was written, it retains the
monitored executable path from the process report and explicitly marks the
capture-time engine hash unavailable. It then regenerates focused exports,
manifest hashes and marker-bounded summaries. The resume-engine hash describes
the postprocessing environment; a trace does not independently prove that an
arbitrary supplied binary created it.
The validated baseline sessions and their exact report paths are recorded in
`docs/crowd-engine-profile.md` and
`docs/benchmarks/crowd-engine-profile-2026-09-19.json`.

The headless trace attributes scene, animation and skeleton work without a real
renderer. The windowed Forward+ trace adds renderer and skin upload behavior.
Keep render/present waits and `OS::add_frame_delay` separate rather than
assigning all remaining frame time to CPU work.
