# Desktop browser prototype

The prototype runs the existing Godot client in a desktop browser and uses the
same game protocol and server. Its current playable map is **Landfall**. First-launch browser settings use
Medium graphics, half-size map textures, a 60 FPS cap and no decorative grass;
these preferences stay separate from the desktop client. It is a
local development build, not a published web release.

Use an existing isolated test character saved on Landfall. Character creation,
other maps, the desktop updater and animated login backgrounds are outside this
prototype. A character arriving on another map is disconnected with a message
directing them to the desktop client. Use a separate test database: this build
does not move or rewrite production characters.

## Build and run

Work in a task worktree based on `origin/develop`. Use the supported Godot 4.7.2
editor and its matching standard web export templates. Extract `web_debug.zip`
and `web_release.zip` from the official export templates into an ignored local
folder. This tool does not download tools or publish anything.

```powershell
python godot-client/tools/build_web_prototype.py `
  --godot C:/rabbitlands/rabbitlands-client/godot-client/Godot_v4.7.2-stable_win64.exe `
  --templates .local/browser-prototype/templates

python godot-client/tools/serve_web_prototype.py .local/browser-prototype/build/site
```

Open `http://127.0.0.1:8060/` in Chrome or Edge, then connect and log in. The local
game server must expose its opt-in WebSocket listener on `127.0.0.1:2002` and
allow the origin `http://127.0.0.1:8060`. Server operators should follow their
server handbook for test database setup and listener configuration.

`--endpoint` chooses another WebSocket URL at build time. Outside loopback, use
`wss://` with a trusted certificate. Do not put credentials in URLs or build
configuration. The ordinary desktop client continues using TCP/TLS.

`--assets-url https://.../assets.zip` independently selects the asset download
host. The file must match the hash embedded in the build and permit cross-origin
browser requests. This lets downloads bypass the play/game machine. Existing
GitHub release-download links must be checked for CORS; a browser cannot assume
that a link which works for the desktop updater can also be fetched by a page.

The build writes only under this worktree's ignored `.local` directory. It
copies runtime source to an isolated export project, disables editor plugins,
uses a separate editor profile and temporary directory, and selects Compatibility
rendering. Runtime code shared with the desktop client remains shared.

Landfall's declared chunks, shared prototypes, verified image dependencies,
current humanoids, supported creatures, home NPC clothing and starter equipment
and verified road-ground fields are packaged from tracked source files. Raw actor and map files are extracted
into the browser's private virtual filesystem before the ordinary client starts;
they are not editor-imported or installed onto the desktop game. The generated
`build.json` records file counts, byte sizes, source base commit and asset hash.

## Current limits

- The first load is large: this proof uses the existing desktop art and one
  compressed asset archive, without on-demand territory downloads or a smaller
  browser art profile. The loader displays progress and verifies the archive.
- The threaded build requires cross-origin isolation. The local serving tool
  supplies the required headers and serves only the chosen generated site folder.
  The export reserves 16 browser workers, with four in Godot's worker pool, to
  leave capacity for existing map and actor loading threads.
- The downloaded archive uses temporary memory-backed storage, outside IndexedDB.
  Browser settings use a separate application storage directory. Login
  credentials remain in process memory and clear through the existing logout
  and failed-authentication paths. Closing a tab loses an active connection;
  switching tabs can pause the game and require reconnecting.
- Browser chunk construction runs one deferred cell on the main thread: WebGL
  mesh assembly stalled on background imports. This can cause loading and travel
  pauses. Desktop imports retain their worker path.
- Browser graphics, input shortcuts, memory use and reconnect behavior still
  need qualification across desktop browsers. This is not a mobile/touch build.

For a focused networking check, run `godot-client/tests/test_browser_connection.gd`
with the exported staging project and an isolated local server. Supply
`RL_QA_USER` and `RL_QA_PASSWORD` through environment variables. By default the
probe uses TCP port 22000; `-- --probe-websocket` uses WebSocket port 2002.
It checks login, a server-confirmed movement step and chat echo through the real
client autoloads. Never use production credentials for automated probes.
