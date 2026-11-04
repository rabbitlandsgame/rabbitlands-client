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
Settings → Graphics also offers Automatic, Forward+, Mobile and OpenGL
Compatibility as a saved renderer preference. Mobile is listed once the
installed updater can start it. The Automatic item names the renderer it starts
on this computer, for example "Automatic (Forward+)". The renderer's tooltip
names the renderer, graphics API and adapter running now, and says what each
choice is for: Mobile is often faster on integrated graphics, Forward+ adds
contact shade and bounce light in the Full painted look, and OpenGL
Compatibility uses the least memory. Close and reopen the game after changing
it; the page asks for a restart only when the choice starts a different
renderer. A note under the choice says when a renderer could not start on this
computer, for example "Mobile could not start on this computer, so Automatic
uses Forward+."
The compatibility and safe-mode launchers take precedence over this preference.
A renderer passed directly as an engine flag (`--rendering-method`) is honoured
while the preference is Automatic and Automatic starts the project default; the
game cannot see engine flags, so with an explicit preference (or an active
recommendation, below) a direct launch restarts into that renderer.
The updater selects the saved renderer before starting the child game; a direct
game launch relaunches once when needed, with a guard against fallback loops.
Renderer flags reach the child game as engine arguments, before `--`. Safe-mode
overrides are process environment variables and preserve saved preferences.
Renderer selection uses [Godot's command-line options](https://docs.godotengine.org/en/stable/tutorials/editor/command_line_tutorial.html).
Original map textures can use more memory; bypassing the cache can slow loading.
Safe mode is a diagnostic option, not necessarily the fastest option.

A new installation chooses its starting graphics from the computer, once, before
any graphics setting has been saved. Computers with integrated graphics (other
than Apple silicon), about 8 GB of memory or less, or four CPU threads or fewer
start on the Performance preset (without its renderer change), and the start
screen shows its still image. Other computers keep the High defaults.
Settings → Graphics notes a Performance preset start, and every setting can
still be changed. Existing settings and the renderer choice are never changed,
and launches with graphics overrides choose nothing.

### Automatic renderer on integrated graphics

Automatic can also record which renderer it starts on a computer
(`src/runtime/renderer_policy.gd`). On a first run the game classifies the
graphics adapter it actually renders on; for an integrated GPU on Windows,
while Forward+ or Mobile works there, it can record the Mobile renderer and
restart into it once. **This recommendation is switched off**
(`RendererPolicy.INTEGRATED_RENDERER` is empty) until Mobile passes a
performance and visual re-qualification, so Automatic starts Forward+ as
before. Developers can turn it on for a launch with
`RABBITLANDS_INTEGRATED_RENDERER=mobile` (`off` turns it off); that variable
does not stop a first run from choosing its starting graphics.

When it is on, the recommendation is a record beside the first-run choice in
`[graphics]` of `eloria_hud.cfg` (`auto_renderer`, `auto_renderer_basis`,
`auto_renderer_adapter`, `auto_renderer_state`, `auto_renderer_attempts`),
never the player's choice:

- an explicit renderer choice always wins, and only fresh profiles get one;
- the compatibility and safe-mode launchers always keep OpenGL;
- a process that runs the recommendation for 30 seconds marks it `ok`;
- if it falls back to OpenGL (`failed_fallback`) or two starts end before `ok`
  (`failed_start`), Automatic returns to Forward+ for good on that profile;
- with the policy off again, the next ordinary launch withdraws a recorded
  recommendation (`withdrawn`), so the switch also works as a kill switch;
- launches that pin graphics or measure (overrides, tools, tests, benchmarks,
  headless, the browser) record and change nothing.

A restart into another renderer (the recommendation or an explicit choice)
exits with code 75 when the updater announced in
`RABBITLANDS_LAUNCHER_FEATURES` that it relaunches the game and keeps its
installation lock; otherwise the game restarts itself.

### Lights in Mobile and OpenGL Compatibility

Mobile and OpenGL Compatibility light each mesh with at most 8 point lights and
drop the rest in an order that has nothing to do with distance. Interiors such
as Landfall Town's castle and the Landfall underground reach one floor with up
to 22 and 78 map lights, so lamps beside the player used to go dark at random.
The client therefore keeps only the map lights nearest the camera lit
(`src/world/light_marker_budget.gd`): 6 at Low quality, 12 at Medium and 24 at
High, and never more than 8 in Mobile or Compatibility. Lights that change
because the camera moved fade over 0.3 seconds; a room's lights come on with the
room. Street-lamp lights stay at 6 or fewer and fire lights at 2 or fewer in
these renderers, so a ground mesh gets at most 8. Distant lamps are dark rather
than random lamps dropping out. Forward+ keeps its street-lamp and fire lights
unchanged.

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

## Disconnects and chat colors

Losing a logged-in connection opens the console and preserves the session's chat
history. Press a key to start reconnecting: the first attempt starts immediately,
then attempts repeat every two seconds until the session resumes. The client
signs back into the same character and requests fresh world state. Credentials
remain in memory only and are cleared when you log out or authentication fails.

Use `#disco` to enter this waiting state deliberately. Use the disconnect menu
icon to cancel retries and return to the login screen. A rejected login or invalid
session needs a return to login; its error remains visible in the console.

Settings → Chat offers individual message colors, a reset for each category,
per-numbered-channel heading colors and **Reset all chat colors to defaults**.
Changes apply to both floating feeds, their previews and the full console, including
messages already received. Saved choices survive a restart.

The default renderer uses Eternal Lands' exact 28-color protocol palette. It
preserves the server's color markers throughout every message, including local
speech, private messages, guild messages, moderator messages and system feedback.
Uncolored text is white. The first numbered-channel color is white when active
and gray when inactive; later body markers retain their server colors. When a
server sends only one color marker, that whole channel message follows the
active/inactive color, as in EL. Links retain their surrounding message color.

Choosing a category color overrides its server colors. The separate guild and
numbered-channel heading controls keep headings independently adjustable. A
per-channel choice overrides that channel's first color marker. Reset removes
the custom choice and restores the normal server-color behavior. An explicit
choice remains an override even when its RGB equals the displayed default.

| Message or text role | Default behavior |
| --- | --- |
| Harvesting and harvesting events | EL orange2 (`#fc7a3a`), supplied by the RL server |
| Special finds and guild messages | Server-supplied EL blue2 (`#7697f8`), with later color markers preserved |
| Private messages | Server-supplied EL orange1 (`#f7c49f`) |
| Nearby speech | White speaker, server-supplied EL yellow1 (`#fbfabe`) body |
| Inactive numbered channel headings | Gray (`#999999`) |
| Active numbered channel headings | White (`#ffffff`) |
| Uncolored system and client feedback | White (`#ffffff`) |
| Disconnects | EL red2 (`#fa5a5a`) |
| Connection attempts | Pink (`#ffb3c1`) |
| Welcome, success, warnings and announcements | Preserve each server-supplied shade |
| Web links | Preserve the message color; a separate link-color override is optional |

Harvest feedback appears in the System feed; nearby players' speech keeps its
conversation category even when it mentions harvesting. Existing preferences from
the earlier full-palette format keep custom colors while untouched factory values
upgrade to the new defaults. Old files did not distinguish an untouched factory
color from an intentionally chosen identical RGB.

Settings → Text colors covers interface controls, login, NPC dialogue, inventory,
crafting, statistics, knowledge, quests, books, spells, contacts, HUD controls,
world labels, floating combat/progression feedback and map text. Search or filter
by area, choose individual colors, or reset a role, an area or the whole palette.
Changes apply immediately and persist across restarts. Defaults follow EL where
the games share a text role; RL-specific text retains its existing palette.
Personal map marks retain any saved individual RGB until a global personal-mark
override is chosen. Explicit HUD component and local-player banner customizations
retain precedence through their existing controls.

## What diagnostics capture

`client_diagnostic` JSON lines survive release exports. Startup records the build,
engine, OS, CPU/memory, GPU vendor/name, graphics API, active renderer/driver,
texture format support and graphics overrides. It also records the adapter class
and the renderer decision: what the settings resolve to (`renderer_effective`),
what the settings ask the engine for once that decision is made
(`renderer_requested`; after a failed Automatic recommendation, the renderer
Automatic starts next, not the one this launch tried), whether a RenderingDevice
request fell back to OpenGL (`renderer_fallback`), the `auto_renderer` record and
the policy's action. A `renderer_restart` event precedes a restart into another
renderer, and `renderer_confirmed` marks a recommendation confirmed. Driver
version discovery runs once on a worker so it cannot block login. The diagnostics
autoload runs before the
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
godot --headless --path godot-client --script res://tests/test_renderer_policy.gd
godot --headless --path godot-client --script res://tests/test_settings_renderer.gd
```

The runtime check exercises child-game argument separation, temporary safe-mode
overrides and the production viewport snapshot. Its output must not contain the
`DIAGNOSTIC_PRIVATE_` credential/reply sentinels used by the test. The renderer
policy check covers the recommendation, its trial states and the restart plan;
its two `ConfigFile parse error` lines are its unreadable-file case. With
`RABBITLANDS_LAUNCHER_FEATURES=renderer-relaunch` and `-- --relaunch-child` it
instead performs a real relaunch restart and must exit with code 75. The
settings check covers the renderer menu, its labels and tooltip, the fallback
note and the restart-notice rule, with the Mobile cases simulated
(`renderers_for_tests` in `settings_window.gd`, `RendererFamily.override_for_tests`).
