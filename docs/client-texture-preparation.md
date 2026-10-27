# Preparing map texture sidecars locally

The client can load map textures from precompressed BC7, BC5 and BC1 sidecars.
This avoids decoding their original PNG/JPEG pixels and generating their mip
chains during map loading. The original images, GLBs and manifests stay intact.
Unsupported formats, missing sidecars and quality failures use the original
texture path.

Release packaging already runs `godot-client/tools/build_vram_textures.py` and
ships the accepted sidecars. The installer and updater deploy those files; they
do not encode them on the player's machine. A source checkout does not have the
ignored package outputs automatically, so a local run may exercise a different
texture path from an installed release.

## Prepare a declared runtime scope

Use a task worktree and the supported Godot 4.7.2 **editor** executable. The
export template cannot encode BC textures. Python needs NumPy and Pillow;
`zstandard` also permits quality remeasurement from existing cached sidecars.
Coordinate this CPU and disk work with anyone running performance measurements.

From the task worktree's repository root, this PowerShell example prepares only
Landfall proper and the prototypes its 34 declared chunks reference:

```powershell
$clientRepo = (Get-Location).Path
$godotEditor = 'C:\rabbitlands\rabbitlands-client\godot-client\Godot_v4.7.2-stable_win64.exe'
$textureTool = Join-Path $clientRepo 'godot-client\tools\build_vram_textures.py'
$mapSources = Join-Path $clientRepo 'eloria-assets\maps'
$encodeCache = Join-Path $clientRepo '.local\texture-preparation\cache'
$landfallStage = Join-Path $clientRepo '.local\texture-preparation\landfall\maps'

python $textureTool --maps $mapSources `
  --manifest (Join-Path $mapSources 'continent-v2\landfall\client\world.json') `
  --out-root $landfallStage --cache $encodeCache --godot $godotEditor `
  --procs 4 --no-prune
```

Set `$godotEditor` to an existing supported editor on the machine. Both console
and non-console executables work; automatic discovery also checks both names in
the primary checkout when the command runs from a normal sibling worktree.
Reading that executable does not import or modify the primary checkout.

For all 17 currently served Landfall continent territories, use a fresh stage:

```powershell
$continentStage = Join-Path $clientRepo '.local\texture-preparation\landfall-continent\maps'
python $textureTool --maps $mapSources --scope-group landfall_continent `
  --out-root $continentStage --cache $encodeCache --godot $godotEditor `
  --procs 4 --no-prune
```

`--scope-group` resolves the group in
`godot-client/data/maps/geometry-cache-scope.json` through the current map
registry. It selects map manifests; separate geometry asset overlays are not
part of this texture command. `--manifest` is repeatable and also accepts an
individual leaf manifest. Both selectors follow declared `streamingChunks`
leaves and their `externalMeshes`, including the image URIs in those prototype
GLBs. They omit streamed roots' review GLBs and unrelated authoring maps and
prototypes. Keep `--maps` broad enough to contain every referenced image and
prototype, including the shared pools.
Prefer one common ancestor `--maps` root: overlapping roots retain the legacy
first-match relative-output layout, which can depend on argument order.

Scoped builds require `--out-root` outside the source map trees. Each resulting
index describes the selected scope's use of its pool, so a small scope must not
replace a broader pool's index accidentally. The ordinary command without a
scope selector retains the existing whole-tree packaging behavior.

## Review and use the output

The stage mirrors image-pool paths beneath `--maps`. Each `vram/` directory has
an index, accepted `.evt` payloads and a local quality report. Source SHA keys,
payload hashes, material roles and dimensions protect runtime reuse. Scoped
preparation also checks prototypes against the manifests' declared file SHA values
and their used image URIs against the prototype index's image SHA values.
Missing or stale dependencies fail preparation. Resolved output directories
must remain inside the chosen stage, including through existing directory links.
The tool keeps the existing per-mip colour, alpha, normal and ORM gates, including the
BC7 retry for ORM that fails BC1. A rejected image remains a documented raw
fallback; do not lower quality floors to force complete coverage.

The encode cache must be ignored. It is keyed by source SHA, recipe, recipe
version and engine version. `--no-prune` preserves encodes used by other local
scopes. The default publishes ordinary copies into the stage. Optional
`--link-output` uses hard links and bounded encoding batches when the cache and
stage share a volume and the filesystem permits creating those links. It must
not be assumed to work on every Windows profile.

Staging does not install anything in a source checkout. For a coordinated local
trial, close the game, retain any existing ignored `vram/` directories, then
copy only the staged `vram/` directories to the corresponding image pools in
the same owned task worktree. Resolve and check destination paths first,
including junctions, and verify copied indices and payload SHA values. Keep
the quality reports as ignored evidence. Do not copy the whole map stage,
overwrite authored images, or automatically publish these outputs into the
primary checkout. Normal release packaging remains responsible for its own
shipping outputs.

## Disk and texture-quality choices

Full-resolution sidecars preserve the authored dimensions and full mip chains.
The current `half` and `quarter` map-texture settings slice existing mip levels
for upload. They can reduce texture GPU bytes to roughly one quarter and one
sixteenth respectively, while using the same full sidecar files on disk. They
still read and decompress those files. Smaller installed mip variants would
need an explicit format and runtime change; truncating today's files is invalid.

The October 26 Landfall-proper preparation accepted 252 unique image contents:
135,261,365 bytes of deduplicated payloads (129.0 MiB), or 137,522,615 bytes with
the six duplicate contents copied into both pools. Indices and local reports
add about 200 KiB. Four quality failures and one unaligned image use raw
fallback. The median accepted base-colour PSNR was 44.46 dB. This is a local
preparation result, not a frame-time measurement.

The wider scope resolves to 1,276 leaves, 532 prototypes and 1,219 unique image
contents. An inventory of existing accepted package outputs found about
588 MiB of matching payloads for 1,199 contents; a fresh all-territory cook has
not been measured here. Those payloads already exist in the package's continent
and Nymara pools. Their selected-set size is therefore not an incremental
release-download estimate: existing files, cross-pool references and package
deduplication must be accounted for first. Local preparation needs an encode
cache, a stage and temporary quality scratch in addition to the final outputs.
Use the actual build summary for a chosen scope when budgeting that disk space.
