# Client compatibility and diagnostics

A blue or empty gameplay viewport can come from the graphics driver, an inactive
camera, missing map data, delayed chunk loading or missing authoritative actor
state. A successful login alone does not distinguish these. Collect a log on the
affected computer before changing drivers or reinstalling.

## Packaged client

Close the client between attempts. Reproduce once with **RabbitLands (debug
console).bat**, then try **RabbitLands (compatibility).bat**, then **RabbitLands (safe
mode).bat**. Linux equivalents are `RabbitLands-debug.sh`,
`RabbitLands-compatibility.sh` and `RabbitLands-safe-mode.sh`.

| Launcher | Rendering and overrides | Log beside launcher |
| --- | --- | --- |
| Normal | Forward+, with the engine's available fallback | Automatic rotating log under the user data directory |
| Debug console | Normal rendering, verbose engine output | `eloria-debug.log` |
| Compatibility | OpenGL 3.3, selected before graphics initialization | `eloria-compatibility.log` |
| Safe mode | OpenGL 3.3, low quality, painted look off, map cache bypassed, original map textures | `eloria-safe-mode.log` |

Both compatibility launchers still use the restart updater when it is installed.
Renderer flags reach the child game as engine arguments, before `--`. Safe-mode
overrides are process environment variables and preserve saved preferences.
Renderer selection uses [Godot's command-line options](https://docs.godotengine.org/en/stable/tutorials/editor/command_line_tutorial.html).
Original map textures can use more memory; bypassing the cache can slow loading.
Safe mode is a diagnostic option, not necessarily the fastest option.

Send the three logs and identify which modes worked, whether the login panel or
the world after login went blue, and whether the HUD or minimap remained visible.
Keep earlier logs before retrying the same launcher, which overwrites its named
log. The affected machine still needs a functioning OpenGL 3.3 driver for these
compatibility modes; there is no bundled CPU software renderer.

Normal launches keep up to five logs, including engine warnings and errors:

- Windows: `%APPDATA%\Godot\app_userdata\Eloria\logs\client.log`
- Linux: `~/.local/share/godot/app_userdata/Eloria/logs/client.log` (or
  `$XDG_DATA_HOME/godot/app_userdata/Eloria/logs/client.log`).

The new launchers and diagnostic events require a new client build. For an older
Windows package, the existing debug launcher already produces `eloria-debug.log`.
To try its OpenGL mode from PowerShell in the package folder:

```powershell
Set-Location app
.\RabbitLands.exe --rendering-method gl_compatibility --rendering-driver opengl3 --verbose --log-file ..\eloria-compatibility.log
```

This direct invocation does not run the older restart updater. Use it only to
compare rendering, then return to the normal launcher for updates.

## What diagnostics capture

`client_diagnostic` JSON lines survive release exports. Startup records the build,
engine, OS, CPU/memory, GPU vendor/name, graphics API, active renderer/driver,
texture format support and graphics overrides. Driver version discovery runs once
on a worker so it cannot block login. The diagnostics autoload runs before the
application state and network, so its startup line survives a main-scene failure.

Connection and login events contain state and error codes, with no credentials or
server reply text. Map events report registry misses, load errors, cache state and
phase timings. A viewport snapshot runs after startup, login and map binding, and
every 30 seconds. It records viewport dimensions and update mode, texture binding,
camera position/mask, received/presented actor counts, local actor presence,
resident chunks, graphics settings, frame/draw counts and memory. It never reads
pixels back from the GPU. A snapshot proves submitted rendering state, not that
the driver displayed correct pixels.

The added events never log usernames, passwords, chat, raw packets or full command
lines. Engine logs can include local file paths; do not post them publicly without
reviewing them. No logs are uploaded automatically.

## Developer verification

```powershell
python -m pytest godot-client/tests/test_package_compatibility.py godot-client/tests/test_client_release.py
godot --headless --path godot-client --script res://tests/test_compatibility_launch.gd
godot --path godot-client --audio-driver Dummy --rendering-method gl_compatibility --rendering-driver opengl3 --script res://tests/test_compatibility_launch.gd
```

The runtime check exercises child-game argument separation, temporary safe-mode
overrides and the production viewport snapshot. Its output must not contain the
`DIAGNOSTIC_PRIVATE_` credential/reply sentinels used by the test.
