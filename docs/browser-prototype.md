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

# In a second terminal, simulate the external asset origin locally:
python godot-client/tools/serve_web_prototype.py .local/browser-prototype/build/assets --assets --port 8061
```

Open `http://127.0.0.1:8060/` in Chrome or Edge, then connect and log in. The local
game server must expose its opt-in WebSocket listener on `127.0.0.1:2002` and
allow the origin `http://127.0.0.1:8060`. Server operators should follow their
server handbook for test database setup and listener configuration.

`--endpoint` chooses another WebSocket URL at build time. Outside loopback, use
`wss://` with a trusted certificate. Do not put credentials in URLs or build
configuration. The ordinary desktop client continues using TCP/TLS.

`--assets-base-url https://.../folder/` selects the external asset origin. The
default is the separate loopback server on port 8061. Only the small `site/`
folder belongs on the launch host. The `assets/` folder contains every large
payload, including the WASM runtime, imported game package and raw art archives.
The launch page never proxies these downloads through the game server.

For a GitHub prototype, publish the generated hash-named payload files on a
separate asset branch, then set `site/browser-assets.json`'s `base_url` to
`https://raw.githubusercontent.com/rabbitlandsgame/rabbitlands-client/<commit>/<folder>/`.
Pin a full commit rather than a moving branch. Changing only this base URL does
not require re-exporting. Raw GitHub responses were checked with a browser Origin
and supply `Access-Control-Allow-Origin: *` and cross-origin resource policy.
GitHub release downloads did not supply these headers; the desktop updater's
release URLs cannot be reused directly. This remains prototype hosting, without
a production bandwidth or availability commitment.

The build writes only under this worktree's ignored `.local` directory. It
copies runtime source to an isolated export project, disables editor plugins,
uses a separate editor profile and temporary directory, and selects Compatibility
rendering. Runtime code shared with the desktop client remains shared.

Landfall's declared chunks, shared prototypes, verified image dependencies,
current humanoids, supported creatures, home NPC clothing and starter equipment
and starter mounts and verified road-ground fields are packaged from tracked source files. Raw actor and map files are extracted
into the browser's private virtual filesystem before the ordinary client starts;
they are not editor-imported or installed onto the desktop game. The generated
`build.json` records file counts, byte sizes, source base commit and archive hashes.
The browser checks the SHA-256 and length of the runtime, each package part and
every raw archive. Downloads use no credentials. Missing or corrupt payloads stop
loading. Independently unpacked art archives are about 24 MiB each or smaller;
the package parts are capped at 24 MiB. No generated payload approaches GitHub's
100 MiB per-file Git limit.

Rendering, animations, input, decompression, map construction, client CPU, GPU
and RAM all run on the player's machine. That machine needs a current desktop
Chrome or Edge with WebGL 2, WebAssembly, workers and cross-origin isolation.
The launch host serves HTML/JavaScript/icons and the isolation headers; GitHub
transfers runtime and art bytes. The existing game server retains authoritative
gameplay, accounts, persistence and the normal state/message traffic, with an
optional WebSocket listener for browsers. It does not render frames or unpack
player assets.

A local build uses about 913 MB of external payloads and a 1.6 MB launch folder.
Browser-only exported hair albedo textures are limited to 1024 pixels, reducing
the imported package by about 84 MB. Authored PNGs, raw actors and desktop art
are unchanged. The loader transfers ownership of its immutable package/archive
buffers to the virtual filesystem instead of making an extra full copy.

Browser streaming uses a 128 m preparation lead and 192 m retention distance,
with 250 ms recovery between off-camera imports. The existing 64 m framed-ground
admission, arrival ring and explicit view holds remain intact. The desktop
worker path and its distances are unchanged. A fixed-position comparison kept
14 cells instead of 17 with the former browser lead. Short frame-timing samples
varied with shader warm-up and game lighting, so those streaming changes alone
did not establish an FPS gain. Medium graphics and full 3D resolution remain the defaults.

The web runtime's frame-presentation blit now queries `SCISSOR_TEST` with
`isEnabled` instead of `getParameter`. Both read the same capability, but
Chromium can answer `isEnabled` from its cached state instead of waiting for
the graphics command queue. Framebuffer validation, graphics detail and the
blit's state restoration are unchanged. The builder checks the exact supported
template hook and fails if it changes. See Chromium's
[capability query implementation](https://chromium.googlesource.com/chromium/src/+/main/gpu/command_buffer/client/gles2_implementation.cc).

A paired 1280 x 900 visible Chrome window test on the RTX 5080 laptop GPU
measured typical frame times of 29.2 ms before and 20.8-24.9 ms after this
change (about 34 to 40-48 FPS). The 95th percentile improved from 37.5 to
29.2 ms. A separate headless test improved from about 27 to 34 FPS. This does
not establish a steady 60 FPS target. The heavily occupied Intel GPU was too
variable for a useful performance comparison. These are local prototype
measurements, not minimum hardware requirements.

The page requests a high-performance graphics context, which the browser or OS
can override. On Windows, start the local site and then use
`python godot-client/tools/open_web_prototype.py` to open a separate Chrome
profile requesting the faster GPU. It leaves normal Chrome settings unchanged.
That profile has its own saved downloads: keep the same profile and launch
address on subsequent visits. A public website cannot force a particular GPU;
the launcher is a local testing aid.

Dedicated Chrome process groups still used roughly 5.1-5.5 GB private memory in
the local Intel graphics samples. Loading and travel can stall while raw actor
and scene resources are constructed. These are measured prototype costs, not
minimum hardware requirements or production targets.

## Saved downloads

The launcher stores verified runtime, package parts and art archives in the
origin's `rabbitlands-browser-assets-v1` Cache storage. Entries are keyed by
SHA-256 rather than the GitHub commit URL, so unchanged files survive an asset
hosting/version change. Every reuse checks length and SHA-256; a damaged or
missing entry is fetched and repaired independently. Incomplete downloads are
never cached. Only public game files are stored here, never account credentials
or server databases. User graphics preferences retain their separate browser
application storage.

A real Chrome profile was closed and reopened with the ordinary HTTP cache
disabled and the asset hosts blocked. All 50 payloads (913 MB) were reused, with
zero asset requests. This verifies disk reuse across browser sessions. The
small launch page and multiplayer server still need to be reachable; this is
not an offline game.

The browser is asked for persistent-storage protection. It can deny protection
while still allowing saved files to work across visits. Browsers can evict
unprotected storage, and clearing the site's data removes these files. Storage
quota or access failures leave gameplay available and show that future visits
may need to download again. Protection denial alone is not treated as a save
failure. See the browser's [Cache API](https://developer.mozilla.org/en-US/docs/Web/API/Cache)
and [persistent storage](https://developer.mozilla.org/en-US/docs/Web/API/StorageManager/persist)
documentation. Use a stable launch origin: changing the hostname or port uses a
different browser storage area.

## Current limits

- The first load is large: this proof uses the existing desktop art and one
  compressed art archives, without on-demand territory downloads or a smaller
  browser art profile. The loader displays progress and verifies the payloads.
- The threaded build requires cross-origin isolation. The local serving tool
  supplies the required headers and serves only the chosen generated site folder.
  The export reserves 16 browser workers, with four in Godot's worker pool, to
  leave capacity for existing map and actor loading threads.
- Each downloaded art archive uses temporary memory-backed storage, outside IndexedDB,
  and is removed after extraction. The ordinary package and extracted art remain
  in browser memory for the session, while compressed downloads persist in Cache
  storage. A subsequent visit still reconstructs runtime resources from saved
  files; the cache removes the repeated network transfer, not all startup work.
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

Focused packaging and loader checks:

```powershell
python -m unittest discover -s godot-client/tests -p test_web_prototype_package.py -v
node --test godot-client/tests/test_browser_asset_loader.cjs
```
