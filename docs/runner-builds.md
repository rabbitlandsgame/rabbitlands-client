# Desktop releases on runners with limited disk space

For the separate Steam depot and macOS test workflow, see [store builds](store-builds.md).
The GitHub installer workflow described here retains its current triggers and outputs.

`godot-client/tools/runner_release.py` stages one platform in an existing draft
release. Windows and Linux use **separate jobs**, pinned to the same full client
commit. `finalize_runner_release.py` combines their small receipts after both
jobs succeed. The usual local `build_release.py` commands remain available.
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
Inno Setup 6 for Windows, and leaves the verified result as a draft. It does not
publish the release or deploy the server's client-update policy.

The currently published installer remains online while a replacement draft is
built. Publishing the verified replacement triggers **Retire previous published
client**, which checks the public asset inventory before removing older published
compiled releases. It leaves any in-progress replacement draft alone.

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

Publishing still requires the usual manual review. After verifying the public
replacement, the cleanup workflow retires older compiled releases and removes
shared files no longer referenced by the current build. It postpones shared
cleanup whenever any client draft exists, including unfinished builds whose
inventories are not yet ready. Failed builds leave the working release intact.
The cleanup job loads its tools from the published client tag, so its format
matches that release. Promote this workflow change to the default branch before
publishing the first shared-storage build.

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
  for a test build, then click **Run workflow** again. Both platforms use that
  run's exact commit, even if the branch advances during the build.
- **Progress:** the run has a draft preparation job, separate Windows and Linux
  jobs, and final verification. The summary links to the release downloads.
- **Result:** review the current [draft release](https://github.com/rabbitlandsgame/rabbitlands-client/releases).
  Publication remains manual. Shared supporting files are available during the
  build, so the downloaded draft installers can be tested before publication.

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
- Removing the main import cache after the exported pack is verified, and
  removing the temporary graphics cache after its staged files are verified.
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
- Keeping only receipts and logs after a successful build. No second platform's
  full stage, payloads or caches accumulate on the same runner.

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
and removes previous compiled files. The result stays a **draft**. The local
`client_updates.json` output is not uploaded or deployed automatically.

The online installers' public download URLs become usable after publication.
On failure, previous downloads are retained. Rerun in a fresh job/output
directory; an already uploaded part is reused only when GitHub's recorded
checksum and size match the new build's bytes.
