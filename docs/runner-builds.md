# Desktop releases on runners with limited disk space

`godot-client/tools/runner_release.py` stages one platform in an existing draft
release. Windows and Linux use **separate jobs**, pinned to the same full client
commit. `finalize_runner_release.py` combines their small receipts after both
jobs succeed. The usual local `build_release.py` commands remain available.
Serialize complete release workflows with one repository-wide concurrency group
and `cancel-in-progress: false`; only the two platform jobs within a single
release should stage into the draft concurrently.

This prepares the build process for Actions. It does not install a workflow,
change repository settings, provision a signing secret, publish a release, or
deploy the server's client-update policy.

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
- Creating one sparse, disposable runtime worktree. Original art, QA and other
  authoring trees outside the runtime inputs are not materialized.
- Checking world-authoring references once, freezing that asset-inclusion proof,
  then retiring the editor-only tree before import. Editor plugins are disabled
  in the temporary project. Runtime sources and asset checks remain enabled.
- Hard-linking unchanged assets and generated graphics sidecars into the stage.
  A filesystem that cannot create these links fails rather than making copies.
- Encoding and quality-checking graphics in batches with at most 128 MiB of raw
  DDS scratch, preserving all shared-image cutoff checks in the same batch.
- Removing the main import cache after the exported pack is verified, and
  removing the temporary graphics cache after its staged files are verified.
- Writing ZIP and gzip/tar bytes directly into bounded download parts, without
  first making a full archive and then copying it into parts.
- Uploading one completed part at a time. GitHub must record the expected size
  and SHA-256 before the local part is removed. A failed part remains local.
- Keeping only receipts and logs after a successful build. No second platform's
  full stage, payloads or caches accumulate on the same runner.

ZIP and tar data are streamed with bounded memory. The Linux tar contains normal
files and executable launchers, even though its staging files use hard links.

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
`numpy`, `Pillow` and `zstandard`, plus Git and GitHub CLI. Remove verified tool
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
outside uploaded receipts/logs. Cloud provisioning of this key is a separate
maintainer decision; these tools do not upload or configure secrets.

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
