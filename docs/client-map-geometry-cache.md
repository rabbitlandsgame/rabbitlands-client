# Map geometry cache

The geometry cache keeps prepared meshes, collision, scene structure and texture
references separate from texture pixels. Normal texture loading still selects
the current texture quality and uses existing VRAM sidecars where compatible.
Preparing geometry does not generate textures, actors or authored map assets.

Detached loading may create private texture Resources on its worker, as the raw
loader does. The main thread alone publishes them to the weak pool, binds the
scene and creates its Nodes. Stale completions retain no Nodes and release their
private candidates. World instances keep private materials and MultiMesh buffers;
static scenery retains the existing immutable-template sharing and its consumers
create overrides when styling or fading an instance.

Scope is declared in `godot-client/data/maps/geometry-cache-scope.json`: all 17
Landfall continent territories, `landfall_insides`, and all 17 canonical gauntlet
maps. Tier aliases share their canonical scene. Landfall means the complete
`continent-v2` territory group; the region named `landfall` is only one member.
Streaming territories prepare their declared chunk leaves, excluding review
GLBs. Used underground scenery assets are separate preparation targets.

This path is independent of the six optional optimization-profile features.
Normal scoped loads can consume a valid geometry entry. Missing, stale or
incompatible entries retain the ordinary source-loading fallback. Cache keys
must match the current source closure and application cache format; the runtime
rechecks each entry when resuming preparation.

Continuous background continent streaming keeps the original detached raw loader:
rendered trials found the native path's publication checks increased frame stalls.
All continent chunks are still prepared for foreground loads. The diagnostic
`ELORIA_GEOMETRY_BACKGROUND_CHUNKS=1` switch enables native background consumption
for qualification and further performance work; it is not the default.

The commands require the matching runtime cache consumer and preparation script.
Use a client built with these changes; generating a plan alone does not update an
older installed client.

`MapGeometryCache.VERSION` in `src/world/map_geometry_cache.gd` is the central
format version. Bump it whenever a loader/producer change alters saved geometry,
collision, batching, scene structure or material interpretation, even when map
source bytes are unchanged. Update the writer, texture-source or binding policy
identifiers as well when their contracts change. The policy key also includes
the engine build, renderer, archived-model policy and older map-cache format.

Development checkouts lack a release identity. Selected source-input metadata
provides a cheap hint that preparation should run again; it is not evidence that
a cache entry is valid. Runtime source and payload hashes remain authoritative,
including when bytes change without a corresponding metadata hint. An invalid
entry falls back to source loading; explicit preparation can rebuild it.

Inspect the exact source closure without starting Godot:

```powershell
python godot-client/tools/map_geometry_cache.py plan --project godot-client --out .local/map-geometry-plan.json
```

Run preparation with an existing Godot executable and previously imported
runtime dependencies:

```powershell
python godot-client/tools/map_geometry_cache.py build --project godot-client --godot C:/path/to/Godot.exe --resume
```

The tool uses Forward+ by default; `--rendering-method gl_compatibility` selects
OpenGL explicitly. It renders in an offscreen window with dummy audio, and keeps
its profile, jobs, reports and logs under the ignored
`godot-client/test-artifacts/map-geometry-prepare/` directory. `--user-root`
selects another isolated output/profile directory; it does not copy player
settings. `--plan` accepts a saved plan and `--no-assets` excludes the separate
underground scenery targets. Resume validates source/cache identity rather than
skipping files merely because they exist.

The producer reads raw source content with the older map cache and VRAM sidecars
disabled for that child process. Logs are checked while it runs; engine errors
stop that process promptly. The default preparation timeout is two hours and can
be changed with `--timeout-seconds`. Logs and any partial report remain available
for diagnosis and resumption.

After installation or an update, a normal launch prepares the scoped world data
once before showing the login screen. Its completion marker includes the release
identity and cache format. Later launches reuse it. Headless launches and launches
with map/geometry caching disabled skip automatic preparation. The settings window
includes both cache families in its displayed disk usage and Clear action.
"Skip for now" retains completed entries and continues to login; a later launch
resumes preparation. Missing entries use source loading in the meantime.
Clear also removes older geometry-policy files and is disabled during cooking.
Older policy folders are otherwise retained; a successful cook prunes only
unreferenced blobs in its current policy. Clearing the completion marker means a
later normal launch with caching enabled prepares the scoped data again.

The explicit client entry point `--prepare-map-geometry` prepares even when the
completion marker already exists, then exits with a success/failure status. The
Python command is the isolated developer workflow and does not run an editor
import. Missing imported dependencies, preparation failures and their logs are
reported instead of silently qualifying a cache. Generated caches belong in local
or installed cache storage, outside tracked source files.
