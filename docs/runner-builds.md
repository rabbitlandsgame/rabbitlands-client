# Desktop releases on runners with limited disk space

For the separate Steam depot and macOS test workflow, see [store builds](store-builds.md).
The GitHub installer workflow described here builds and publishes both desktop installers.

`godot-client/tools/runner_release.py` stages one platform in an existing draft
release. Windows and Linux use **separate jobs**, pinned to the same full client
commit. `finalize_runner_release.py` combines their small receipts after both
jobs succeed. A final publishing job rechecks the downloads and makes the
verified release public. The usual local `build_release.py` commands remain available.
Serialize complete release workflows with one repository-wide concurrency group
and `cancel-in-progress: false`; only the two platform jobs within a single
release should stage into the draft concurrently.

GitHub builds now emit independently checksummed asset packages, a stable
`RabbitLands-<platform>.json` alias, and separate updater/uninstaller executables.
The Windows setup remains one downloadable file; Linux keeps its one-file
download helper. See [package updates and migration](client-updates.md#independent-packages-and-the-updater).
Promote the packaging tools and published-release cleanup changes together to
the default branch before publishing the first package-format release.

The workflow is `.github/workflows/desktop-release.yml`, named **Build desktop
release**. It builds both desktop platforms on GitHub's hosted runners, with
Inno Setup 6 for Windows. After both builds, signing/startup checks, finalization
and receipt retention succeed, it automatically publishes the release as
**latest**. The server's client-update enforcement policy remains a separate deployment.

The currently published installer remains online while a replacement draft is
built. After publication, the publishing job runs the existing verified cleanup
to remove older compiled releases and unused supporting files. Manual publication
still triggers **Retire previous published client**, using the same cleanup.
An in-progress replacement draft is preserved.

## Full optimization packages

Both hosted desktop jobs use `--full-optimizations` to package and qualify the
optional optimization paths. Ordinary launches default to `legacy`: the newer
native backends and prepared-content paths remain off. Explicitly selecting
`--optimization-profile=human-testing` enables Rust mounted poses, remote
presentation and heat bolts, Rust resource admission, prepared content in `auto`
mode, and the `lazy-source-v1` object policy. Earlier graphics improvements and
the water-texture fix remain available in ordinary launches. This build policy
is not a performance claim. See [optimization testing](client-optimization-testing.md).

Each native Windows/Linux job builds the pinned Rust/Godot adapter or restores
a separate payload-only native cache. Its key includes committed native sources,
shared native dependencies, build helpers and the actual compiler/toolchain
identity. A hit is verified against the selected source commit and actual
library, descriptor and provenance bytes before staging. A corrupt or mismatched
native cache stops the build; it is not accepted as an older working payload.
Compilation uses bounded parallelism and disposable, measured scratch storage.

Prepared content is generated fresh for each release from the current pilot
plan and the actual first export's import records and texture products. It is
not restored from a historical cooked catalog. Full, half and quarter texture
jobs include the retained pilot and the Four Gates lazy-object target. The
exact planned sources and resulting entry identities are recorded; an old
entry count is not evidence that a new generation is complete. This optional
pilot remains separate from the complete lean world preparation below.

## Shipped world preparation

Native Windows and Linux packages prepare the complete production geometry
scope, including its collision faces and paving coverage, during the release
build. Texture pixels remain in their existing raw/VRAM assets. This is one
default-renderer generation rather than copies of the entire world at every
texture tier. Windows uses Forward+ with system WARP; Linux uses Forward+ with
the distro-installed Mesa lavapipe Vulkan driver. The existing optimization
pilot's Linux Compatibility cook is unchanged. Actual CPU-adapter, format and
native-buffer observations must pass before the world cook.

The finished data stays loose in `app/prepared-world/`. Native dependencies use
stable installation paths, and a small PCK record binds the loose catalog's
checksum. A persistent, verified world-preparation cache reuses unchanged
source closures and payload bytes across builds. Compatibility, producer policy
and producer inputs govern reuse; the overall game commit does not. In
particular, generated native resource identifiers must not cause a code-only
release to download every map again.

The official desktop runner requires this step. Custom native builds can omit
it with `--no-prepared-world`; cross-platform builds require a matching
`--prepared-world-catalog` when preparation is requested. The dedicated
`--world-preparation-cache` is retained across successful desktop and store
builds independently of other asset caches. Missing or incompatible shipped
data retains validated source/local-cache loading without automatic whole-world
preparation before login. `--prepare-map-geometry` still explicitly builds a
player-owned cache.

The ordinary signed updater inventories these files in independent stable
packages. New releases reuse unchanged packages and download changed or damaged
ones, rather than replacing one monolithic prepared-world archive. Build output,
cache scratch and local profiles remain ignored authoring/build evidence.

Before compiling or loading game assets, a tiny isolated project qualifies the
actual renderer and saves its observations. Windows identifies system WARP by
its DXGI adapter identity in Godot's adapter order; a guessed index or matching
display name is insufficient. The engine must still report a CPU adapter, the
required texture formats and a successful native buffer save/reload. Temporary
probe projects and user caches are retired after verification, with reports and
logs retained in diagnostics.

Cooking needs real rendering-resource storage. Windows uses D3D12 WARP;
Linux uses Mesa llvmpipe under Xvfb with the Compatibility renderer. These are
build-time software renderers, not drivers shipped with the game. Each job
selects dummy audio so qualification does not require a hosted audio device.
The game keeps its ordinary audio-driver selection. Each job
must report its actual renderer, adapter and supported texture-format mask,
and pass a resource-buffer save/reload check. A dummy/headless renderer,
unexpected hardware adapter or unsupported format mask fails qualification;
the tools do not manufacture a capability token.

Before signing or uploading game parts, the build requires positive native
contract checks, ordinary startup with the newer features off, a separate explicit
`human-testing` startup with all six paths active, and acquisition of
every planned entry from the final normal PCK at each texture quality. The
guard checks exact source/catalog/entry identities, readable resource buffers,
lazy restoration and owned cleanup using isolated user data outside the
package. It rejects engine errors, skipped work and changes to the stage.
Neither a benchmark PCK nor source-project resource fallback qualifies a release.
The version 2 optimization proof binds both startup snapshots and their profile
defaults. Earlier proofs that only qualified an enabled-by-default launch cannot
publish a new release under this policy.
The final-PCK guard temporarily runs the verified editor beside the package's
PCK because release templates do not support the external check script. Its
bytes are verified, its copy is budgeted, and it is removed on success or failure
before the final stage inventory and any signing or packaging.

Platform receipts contain optimization proofs bound to the selected commit,
native source digest and prepared coverage plan. Finalization and publication
require matching Windows/Linux source and coverage proofs as well as verified
downloads. Software rendering and functional guards do not replace visual
review, gameplay checks or target-hardware performance qualification. Hosted
execution of this expanded path must be judged from its own run diagnostics;
older local rehearsals below do not qualify it.

## Reusing uploaded downloads

Both the Actions runner and the local combined release build use one permanent
`client-assets` **prerelease** for supporting downloads. It is never marked
latest. The ordinary `client-<commit>` release still contains the Windows setup,
Linux installation helper, signed manifests and checksum inventory. Its release
notes link to standalone updater/uninstaller downloads in the shared release.
There is still one retained playable release, with a replacement draft while
building. The shared release is a file store, not compiled version history.

Package parts have names `RabbitLands-pkg-<SHA256>.zip.part`; helper names include
their kind, complete SHA-256 and platform extension. Their bytes and URLs stay
the same across build dates and client commits when their contents stay the
same. Common Windows/Linux packages can share a single upload. ZIP timestamps,
file ordering and package membership remain deterministic.

Before each upload, the build compares the local SHA-256 and size with GitHub's
recorded digest, size and completed-upload state. An exact match is reused
without an upload, rename or delete. Changed bytes get a new checksum name.
An unexpected completed file with a conflicting checksum stops the build.
Concurrent platform jobs wait for an identical in-flight upload instead of
deleting one another's reservation. An interrupted starter reservation older
than six hours can be retired and retried; active uploads are preserved.

Finalization rereads and verifies **every referenced file** in both releases
before changing the draft tag or pruning previous draft files. `SHA256SUMS`
covers files in both locations. Uploaded and reused byte totals are included
in the runner receipts. The first build using shared storage must upload its
newly named files once; later builds upload only new checksums for packages and
helpers. Per-build manifests and Windows setup change with the build identity.

### Code-only releases

The desktop workflow also keeps a separate Windows/Linux Actions cache of
import and texture build products. Its key hashes the committed asset trees, import settings,
project configuration, updater sources and build tools (including the pinned
engine/template and Python dependency versions). Ordinary game script changes
do not invalidate that key. Adding, changing or deleting an asset does.

On a verified cache hit, the build restores Godot import products and their
generated import records, reuses existing compressed texture encodes and keeps
an unchanged native updater and
uninstaller. It still scans the current project, exports the current game code
and release identity, runs the graphics/startup checks, and signs a fresh
manifest. Generated import settings are restored only when their source bytes
and the fresh checkout's import policy match. Script registries and other
editor state are regenerated.

Each package's **actual staged file paths, sizes and SHA-256 hashes** are compared
with a previous signed manifest. If they match and GitHub confirms every
checksum-named part is complete with the correct size and digest, the ZIP is
reused without compression or uploading. Changed packages are rebuilt normally;
missing remote parts are recreated. A conflicting completed download stops the
build. Deleted files cannot survive through a cached package inventory.

Consequently a code-only release normally uploads the client code package,
fresh installer and signed metadata; unchanged asset packages keep their URLs.
An updater change or a changed native executable can add a small helper/engine
package. The first build for an asset key, an evicted cache, or a corrupt cache
falls back to a full build. A cache miss never skips validation. Cache files
are checksummed before reuse, and the prior manifest must verify with the
current public signing key. Signing secrets, complete game folders, freshly
cooked prepared catalogs and quality scratch files are excluded from this cache.

The workflow saves the cache only after a successful build and only when that
key was absent, so code-only runs do not repeatedly upload the cache itself.
GitHub may evict caches, and a branch may need its own first cache build. The
platform job summary and runner receipt report cache hits, packages rebuilt or
reused, and uploaded/reused bytes. The first run of this optimization populates
the caches; the next code-only run demonstrates the fast path.

After verifying the public replacement, the publishing job retires older
compiled releases and removes shared files no longer referenced by the current
build. It postpones shared
cleanup whenever any client draft exists, including unfinished builds whose
inventories are not yet ready. Failed builds leave the working release intact.
The manual-publication cleanup job loads its tools from the published client
tag; automatic publication uses the same source commit as the builds.
[GitHub's workflow token does not trigger release-event workflows](https://docs.github.com/en/actions/how-tos/write-workflows/choose-when-workflows-run/trigger-a-workflow#triggering-a-workflow-from-a-workflow), so the publishing job
invokes cleanup directly. No additional account token or secret is needed.

Linux installation now downloads and verifies the native updater, which installs
the same independent packages used for updates. Its signed manifest is embedded
in the shell installer, so a draft installs its own build even while a different
release is public. The updater retains the verified manifest across its own
replacement and preserves the build's server defaults. No second full-game tar archive
is built or uploaded by release orchestration. Run the installed
`~/Games/RabbitLands/RabbitLands-updater.x86_64` to play again. A different parent
folder can be passed to the downloaded shell helper. Explicit standalone local
packaging can still create a portable archive when requested.

## Enable and run the workflow

One-time maintainer setup:

1. In the repository's [Actions secrets settings](https://github.com/rabbitlandsgame/rabbitlands-client/settings/secrets/actions),
   create `CLIENT_UPDATE_SIGNING_KEY` containing the existing private RSA PEM key
   that matches `godot-client/data/update_public.pem`. Do not generate a replacement
   key or put the key in Git, a workflow file, an issue, or an artifact. This is
   an explicit transfer of the private key to GitHub's encrypted Actions storage.
2. Deliberately merge the release tooling and workflow into `master`. GitHub's
   [manual trigger requires the workflow on the default branch](https://docs.github.com/en/actions/how-tos/manage-workflow-runs/manually-run-a-workflow).
   Check the complete `develop` promotion, including game changes, before merging.
   The first merge itself starts a build.

After activation:

- **Automatic:** merging into `master` starts the workflow at that merge commit.
  Direct pushes to `master` also start it. A push to `develop` does not.
- **Manual:** open [Actions → Build desktop release](https://github.com/rabbitlandsgame/rabbitlands-client/actions/workflows/desktop-release.yml),
  click **Run workflow**, choose **master** for the stable source or **develop**
  for a develop release, then click **Run workflow** again. Both platforms use
  that run's exact commit, even if the branch advances during the build. Both
  manual and automatic runs publish after all required checks pass.
- **Progress:** the run has a draft preparation job, separate Windows and Linux
  jobs, final verification, and publication. The summary links to the public release.
- **Result:** download from the [latest release](https://github.com/rabbitlandsgame/rabbitlands-client/releases/latest).
  Published installers become available to the client's startup update check.
  Shared supporting files are available while the replacement is still building.
  Download the named Windows setup or Linux helper from the release's **Assets**
  list. GitHub supplies temporary download URLs for drafts, so the instructions
  use that list rather than links to a tag that is not yet published. The same
  instructions continue to work after publication.

The workflow reuses the project's existing client draft or creates one when
needed. Previously published downloads remain available while a new commit
builds; finalization removes older compiled releases only after verifying both
platforms. Rebuilding an already published commit requires first returning that
release to draft, or selecting a newer source commit. Unrelated release entries
are not selected for staging.

Only one release workflow runs at a time. After failure, fix the cause and start
a fresh manual run (or use GitHub's rerun controls). Previous downloads are not
pruned by a failed platform build. Small receipts, disk reports and startup logs
are retained as run artifacts for seven days; complete game folders are not.

Build or verification failures leave the replacement in draft. The final publish
job rechecks the exact source commit, installer inventory and every shared
download's size/digest before publication, then checks the public result before
retiring previous releases. It refuses a source commit that does not contain
the currently published client, preventing an older manual build becoming latest.
If publication succeeds but cleanup fails, the new build stays published and
older downloads remain available. Use **Re-run failed jobs** to retry publication
and cleanup without rebuilding; an already published verified release is accepted
only while it is still latest.

`setup_runner_tools.py` downloads Godot 4.7.2 and Inno Setup 6.7.3 from their
official releases, checks pinned sizes and SHA-256 hashes, extracts only the
job's release template, and removes downloaded archives before packaging.
`runner-requirements.txt` pins the Python libraries tested with the tools.
The existing local Inno Setup installation is unaffected.

## Disk budget

The default budget is **14,000,000,000 bytes**, with **2,000,000,000 bytes reserved**.
The build checks its measured working set and upcoming allocations against the
remaining 12 GB, and also checks actual free space on the output volume.
`disk-usage.json` records phase measurements, observed peak, planned peak and
the reserve. File sizes include the Git object store and supplied tool folders;
hard links count once. Filesystem overhead and unexpected growth consume the
reserved headroom. This is a disk budget, not a RAM limit.

Space is saved by:

- Checking out only the build scripts initially, with complete commit ancestry
  and blob filtering. Historical binary versions are not required.
- Streaming the immutable GitHub source archive into one disposable runtime
  worktree. Each selected file must match its committed Git blob before use;
  Git retains the index and complete history without caching a second copy of
  the runtime blobs. The compressed source archive is never saved. Original art,
  QA and other trees outside the runtime inputs are not materialized. Archive
  writes are checked in bounded batches against the same disk reserve.
- Checking world-authoring references once, freezing that asset-inclusion proof,
  then retiring the editor-only tree before import. Editor plugins are disabled
  in the temporary project. Runtime sources and asset checks remain enabled.
- Hard-linking unchanged assets and generated graphics sidecars into the stage.
  A filesystem that cannot create these links fails rather than making copies.
- Encoding and quality-checking graphics in batches with at most 128 MiB of raw
  DDS scratch, preserving all shared-image cutoff checks in the same batch.
- Moving verified import products to the reusable cache after export, and
  hard-linking retained graphics products into the stage. Without caching,
  temporary import and graphics caches are removed after validation. Full
  optimization builds retain the selected imports through cooking and the
  second export, then release them after final-package qualification.
- Keeping the pinned Rust toolchain, native build/dependency scratch and native
  payload cache in accounted job directories. Native compilation samples its
  owned scratch usage and stops on a budget violation before publication.
- Writing each deterministic package ZIP into bounded parts, without
  first making a full archive and then copying it into parts.
- Keeping package inventories in the signed manifest rather than retaining
  previous complete builds. Package hashes depend on contents, not a build date.
  Updater/uninstaller copies use hard links in the runner stage.
- Uploading one completed part at a time. GitHub must record the expected size
  and SHA-256 before the local part is removed. A failed part remains local.
- Checking each upload's returned asset record directly, then rechecking the
  whole release during finalization. This avoids listing hundreds of assets
  again for every small package.
- Removing the full source and stage after success, before saving the asset
  cache. The disk budget includes retained products and worst-case compressed
  cache-upload scratch, preserving the same 2 GB reserve. Each runner handles
  only one platform.

ZIP data is streamed with bounded memory. Release builds avoid the duplicate
Linux tar entirely; standalone portable tar exports still use executable modes.

### Local validation

The 2026-10-17 cold-cache Windows rehearsal at commit `b0af6cf2b` reached an
observed working-set peak of **11.10 GB**. Its conservative allocation forecast,
including the installed Inno Setup footprint, was **11.64 GB**, leaving about
**2.36 GB** against the 14 GB capacity. This rehearsal counted the full public
Git object store and both desktop release templates; a blob-filtered job with
one platform template should need less space.

The real Linux archive was streamed and read back successfully: about 3.03 GB
across 12 parts, retaining at most one 256 MiB compressed part locally. Native
Linux startup and graphics checks passed. Focused tests also cover streamed ZIP
installation with Godot, graphics scratch batching, checksum failures, executable
modes and Windows long-path cleanup. These are local checks; a hosted workflow
still needs its first run once it is configured.

Those measurements describe the earlier packaging path. They are not a measured
peak or elapsed-time guarantee for the full native build and fresh cooking path.

## Job setup

Use the final `rabbitlandsgame/rabbitlands-client` repository only. For the initial
Actions checkout, configure:

```yaml
fetch-depth: 0
filter: blob:none
sparse-checkout: godot-client/tools
```

Keep full ancestry; a shallow checkout cannot create the update identity. Place
the output directory outside the checkout and use a fresh output directory on
each attempt. Do not point runner mode at a developer's normal full checkout:
its ignored files and caches are included in the budget and may exceed it.

Install Godot 4.7.2-stable and **only the release export template for the job's
platform**. The Windows job also needs Inno Setup 6. Both jobs need Python with
`numpy`, `Pillow`, `zstandard` and `cryptography`, plus Git and GitHub CLI. Remove verified tool
download archives after extraction. Include every downloaded tool/template
directory in `--tool-root`; the flag can be repeated. Keeping these downloads
under one toolchain folder makes accounting straightforward.

Windows runs its native executable. Linux runs its native executable directly,
without WSL. The packaging checks still require the login screen and graphics
texture self-tests. Windows Git operations enable long-path handling locally
for these builds.

Full optimization builds additionally require Rust 1.99.1, CMake, Ninja and the
native C++ toolchain: MSVC x64 on Windows or GNU x86_64 on Linux. The workflow
keeps `RUSTUP_HOME` and `CARGO_HOME` under the accounted native-toolchain folder.
Linux also installs Mesa OpenGL libraries, Xvfb and xauth for software cooking.
Installed package versions and the actual renderer observation are retained in
the diagnostics. No graphics DLLs are copied into the release stage.

The workflow token needs `contents: write` on this repository. Runner staging
accepts the repository's own Actions installation token; local staging requires
the `rabbitlandsgame` account. Both platforms receive the **same draft release
ID and source commit**. An existing published release is not accepted as a
staging destination.

Signing still requires the existing private key matching
`godot-client/data/update_public.pem`. Keep it outside both repositories and
outside uploaded receipts/logs. Hosted builds validate its public identity before
downloading the toolchain, remove the secret from child-process environments,
and delete their temporary key file on completion or failure. The build scripts
do not upload or configure the Actions secret themselves.

## Build one platform

Example Windows job command (substitute the job's actual paths and draft ID):

```powershell
python godot-client/tools/runner_release.py `
  --platform windows --ref $env:GITHUB_SHA `
  --out "$env:RUNNER_TEMP/releases" `
  --godot "$env:RUNNER_TEMP/toolchain/Godot.exe" `
  --iscc "C:/Program Files (x86)/Inno Setup 6/ISCC.exe" `
  --tool-root "$env:RUNNER_TEMP/toolchain" `
  --tool-root "$env:RUNNER_TEMP/rabbitlands-native-toolchain" `
  --update-signing-key "$env:RUNNER_TEMP/signing-private.pem" `
  --draft-release-id 123456
```

For Linux, select `--platform linux`, pass the native Godot executable and omit
`--iscc`. The default server is `game.rabbitlandsgame.com:2001`; use `--server`
to override it for a testing round.

Each job produces `<platform>-runner.json` under
`<out>/runner-<platform>-<commit>/`. Transfer just this small receipt to the
finalization job. Logs and disk reports may be retained briefly for diagnosis;
do not transfer a complete build folder through Actions artifacts.

## Finalize both receipts

```powershell
python godot-client/tools/finalize_runner_release.py `
  --windows windows-runner.json --linux linux-runner.json `
  --out final-release
```

Finalization rejects mismatched commits, release IDs, platform inventories and
remote checksums. After every replacement download is verified, it adds
`SHA256SUMS`, updates the release's commit-specific tag and installation notes,
and removes previous draft files. This standalone command leaves a **draft**.
The Actions workflow then publishes using
`publish_runner_release.py --receipt <out>/runner-release.json` in a separate
job. The local `client_updates.json` output is not deployed automatically.

The online installers' public download URLs become usable after publication.
On failure, previous downloads are retained. Rerun in a fresh job/output
directory; an already uploaded part is reused only when GitHub's recorded
checksum and size match the new build's bytes.
