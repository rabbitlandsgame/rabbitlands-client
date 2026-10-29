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

## Scenery GLBs and one map's images in the shared pool

Scenery (world-object) GLBs under `godot-client/assets/world/` support embedded
images and verified external images. `--scenery-config` names a scenery config (its `assets` object of
`res://` GLB paths, such as `godot-client/data/world/town-scenery.json`); each
eligible image gets a sidecar in the `vram/` folder of its original GLB's
directory, keyed by the SHA-256 of the image bytes. Externalization preserves
the eligibility of embedded images and previously external images. The client
(`src/world/world_object_images.gd`) uploads it when the renderer samples its
format and the GLB samples the image only in the roles it was encoded for;
otherwise it decodes the original image bytes as before. `--scenery-out-root`
mirrors those folders below a stage; a scoped run requires it.

Release packaging skips the whole shared image pool `maps/_shared/images`.
`--unskip-map` keeps planning the images one map names there; the packager
passes it for Landfall Town and also builds the town scenery's sidecars into
the loose `app/assets/world/` folders. A Landfall Town trial in a task
worktree:

```powershell
python $textureTool --maps $mapSources `
  --manifest (Join-Path $mapSources 'continent-v2\landfall_town\client\world.json') `
  --out-root .local\texture-preparation\landfall-town\maps `
  --scenery-config godot-client\data\world\town-scenery.json `
  --scenery-out-root .local\texture-preparation\landfall-town\world `
  --cache $encodeCache --godot $godotEditor --procs 4 --no-prune
```

Then copy the staged `maps\_shared\images\vram` and `world\underground\vram`
folders (index and `.evt` files only) to `eloria-assets\maps\_shared\images\`
and `godot-client\assets\world\underground\`; both are ignored. Rebuild after
the town or its scenery is republished: an index left from older content only
misses the changed images, which then decode. On 2026-10-27 the town's
textures took about 365 MiB of GPU memory decoded and about 90 MiB with these
sidecars (shell 27 images: 90 to 22 MiB; scenery 201 images: 272 to 65 MiB,
three below the quality floors decoded), for about 63 MB of sidecar files.

## Shared standalone scenery sources

`eloria-assets/tools/externalize_scenery_images.py` stages ordinary world GLBs
whose image URIs reuse byte-identical files already in the selected map shipment.
Remaining unique images live in `eloria-assets/world/_shared/images/`, outside
Godot's editor import tree. Keep the sibling `eloria-assets` layout beside the
packaged application. Source pixel dimensions and encoded image bytes are preserved.

The GLB's `extras.rabbitlands_scenery_images` declares schema
`rabbitlands-scenery-images-v1`, `mipPolicy: full`, resource URI/SHA pairs and
original-directory policy lists. Each converted image records
`rl_texture_policy_directory` and `rl_texture_sidecar_eligible` in its extras.
The original world directory still selects its sidecars and quality fallback;
the canonical pixel file's location does not change that choice. Existing
ordinary URI models retain their source layout.

Scenery keeps its full mip chains at every map texture quality tier. Runtime
and native binding pools distinguish the actual full-resolution representation
from reduced map variants. Disk/cache acquisition checks the source GLB and
every declared external image; worker publication rechecks its captured inputs.
Raw decoding checks the bytes it actually reads against the declared source SHA.
Strict scenery failures reject the scene before fallback or pool publication.
Already installed in-memory templates reuse their immutable Resources without
new per-placement file reads. Source verification has no timestamp acceptance
cache and makes no sealed-content claim.

Run raw storage optimization before image externalization. Use a fresh ignored
plan/recovery directory, and a shipping list from the same combined checkout.
The externalizer refreshes current output hashes/image lists in the scenery
records and object catalog while preserving historical source/task records.
The new files stay ordinary GLBs and PNG/JPEG/WebP images.

Production packaging keeps raw world GLBs and the complete external image
closure. It skips unused editor scene imports and their extracted texture
copies only when the target loader and independent references prove that safe.
Explicit scene, material or image consumers retain their required imports.
Actor imports and independent world material textures retain their existing rules.

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


## Canonical pixels and original texture policy

`eloria-assets/tools/canonicalize_map_images.py` can remove byte-identical files
from the shared map image pools. It neither decodes nor re-encodes images.
Fixed minimap, detail-map, overview and road-field files are outside its default
candidate set. Plan only after other asset transformations have been applied;
an old plan must not replace newer geometry.

A canonical image URI identifies the physical pixel file. Its original sidecar
policy stays separate:

- A glTF image's `extras.rl_texture_policy_directory` is the original image
  directory, as a relative URI from that GLB. Every descriptor of an affected
  image content is annotated, including descriptors using the surviving copy.
- A world's `externalImagePolicies` maps each affected canonical URI in
  `externalResources` to a sorted array of original directory URIs, relative to
  `asset.glb`'s directory. Streaming roots retain the same collection for their
  existing resource set.
- A shared prototype's index record uses `imagePolicies` with the same shape,
  relative to the prototype/index directory. Road metadata uses its own
  `externalImagePolicies`, and material-document image descriptors carry the
  same glTF extra. Road-only fallback textures do not acquire new cooker roles.

Explicit directories must be plain relative paths (no percent escapes) and
remain inside `eloria-assets/maps`.
Invalid or undeclared policies fail validation instead of selecting the
canonical file's directory. These are ordinary image URIs and standard glTF
extras; offline tools can continue reading the canonical files.

The sidecar cooker reads pixels from the canonical URI but plans separately by
original directory and source SHA. Existing caller exclusions, roles, recipes,
alpha cutoffs, quality floors and full-mip fallback stay unchanged. Native
texture origins and binding IDs retain the original directory too. Cache tokens
and stream budgets read every declared original directory's index, even when
that directory contains no remaining raw image files.

Runtime weak pooling uses the actual uploaded variant: raw pixels, or the
accepted EVT payload SHA/recipe/format, plus the active mip tier. Compatible
variants share across policy directories; raw and compressed variants remain
separate. A refused sidecar gets the raw variant key after decoding. During an
offline native cook only, source discovery also separates policy directories so
one shared Texture2D cannot erase another usage's provenance. No strong resource
cache is added.

For explicitly annotated contents, streaming counts raw pixels once and each
distinct accepted payload/recipe/format once. Compatible copies in different
directories share one estimate; raw and compressed variants can coexist.
Fallback knowledge conservatively retains the raw estimate alongside accepted
variants. Unannotated legacy sources keep their existing accounting.

The canonicalizer writes an ignored plan and stage. Apply checks the SHA of every
scanned input, saves affected originals to a fresh ignored recovery directory,
and verifies ordinary references, unchanged non-JSON GLB bytes, image hashes,
prototype/manifest/road integrity links and the complete pre/post sidecar plan.
Duplicate images are deleted last. Any validation failure restores the exact
originals. Retirement `mapMeshCopies` file SHA bindings are refreshed without
changing their mesh lists. The plan and recovery receipt are local evidence;
source asset changes still require the normal integration and qualification.

## Measured map storage reduction, 2026-10-29

The release selector's loose `eloria-assets` payload decreased from
2,211,044,583 to 1,700,334,791 bytes: **510,709,792 bytes (510.71 MB, 23.10%)**.
MB here means 1,000,000 bytes. Approximate contributions were:

| Change | Net reduction |
| --- | ---: |
| Exact vertex consolidation in remaining map geometry | 253.7 MB |
| Byte-identical shared images, including reference metadata overhead | 182.2 MB |
| Exclude authoring snapshots, comparisons and concept/provenance images | 74.8 MB |

The selector retained all 6,638 shipped GLBs. Geometry verification covered
10,250,188 triangles; the final audit also checked six rewritten review/master
GLBs. All 3,806 shipped original-directory/source-SHA policy records and 1,697
eligible source/recipe variants matched the baseline. All 73 existing map-image
files and 29 regional frame/style contracts remained unchanged.

Ten fixed Forward+ views across Suncoil, Landfall Underground, Cinderbank and
Reedway were pixel-identical before and after. Prepared-cache and background
loading added 16 matching comparisons in Suncoil and Landfall Underground;
collision probes and visible mesh/material inventories matched too. Texture
GPU bytes matched the baseline in the four raw qualifications. Suncoil's
measured static CPU allocation increased by about 14 MB; these
qualification snapshots do not establish load-time or frame-time improvements.
Existing prepared map caches require rebuilding with the new policy versions.

This measures selected loose source assets. Exported PCK contents, generated
sidecars, prepared products and release archive compression require separate
release-build measurements. The standalone scenery qualification below also
corrects the old packaging assertion that expected unused extracted images for
raw-loaded world models; explicitly imported models retain that check.

## Measured standalone scenery reduction, 2026-10-29

The next pass reduces the tested PCK and selected loose asset payload by
**583,590,621 bytes (583.59 MB)** beyond the map reduction above. It adds no
compression container or runtime decompression step. The components do not
overlap:

| Change | Before | After | Reduction |
| --- | ---: | ---: | ---: |
| Fresh exported PCK, with unused world imports excluded | 1,039,241,516 | 518,814,388 | 520,427,128 |
| 262 loose world GLBs plus the new unique image pool | 114,500,144 | 54,299,826 | 60,200,318 |
| 36 unused loose extracted image copies | 2,963,175 | 0 | 2,963,175 |

The PCK comparison uses fresh controlled exports of the production PCK input
selection, before and after this pass. It is not an installer-size measurement.
Existing map images reused by scenery were already selected for shipping and
are not counted again. The new image pool contains 164 files (21,380,078 bytes);
the 262 GLBs now total 32,919,748 bytes. Provenance records outside the release
payload grow separately by 214,949 bytes. Optional newly generated prepared
products and archive compression are outside this comparison.

The changes share exact encoded image bytes, narrow legal 32-bit indices to
16-bit indices, and remove one unreferenced cave-mouth image. An independent
audit checked all 262 models against their originals: geometry values,
triangles, nodes, materials, samplers, bounds, and all 717 retained image uses
match. Image dimensions, full mip behavior and decoded RGBA values are
preserved. The production town sidecar scope retains all 198 eligible variants;
no new sidecar encoding is needed.

Four representative assets (bookcase, tree fern, storage and cave mouth) were
rendered from four views through raw and prepared loading, both normally and
on a worker with the quarter map-texture setting. All **64 before/after image
comparisons were pixel-identical**; mesh/material and texture inventories also
matched. The final decode guard passed 16 more matching worker comparisons.
Cache publication tests reject changed source images and preserve
immutable already-loaded scenes without hashing again for each placement.

The final PCK and loose files also passed a relocated-folder probe with an
empty exported `res://` root and an unrelated working directory. That probe
uses the supported editor executable beside the PCK, matching the existing
package guard: the installed debug export template disables external path
overrides and cannot run the probe script. It is not a full release-client
gameplay or frame-time benchmark. Fresh acquisition verifies GLB and image
hashes; no timing improvement is claimed. Older prepared caches require a
rebuild with scene format 11 and map geometry policy 4.
