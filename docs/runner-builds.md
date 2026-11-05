# Desktop release builds on GitHub runners

Desktop releases deliver their game content from R2 (see
[desktop R2 delivery](desktop-r2-delivery.md)). The owner's build machine builds,
qualifies and uploads the content. GitHub Actions does the rest:

- builds the executables;
- signs the release in owner-approved jobs;
- builds the installers;
- installs and starts the shipped combination on fresh runners;
- publishes on GitHub.

This page describes the workflows and what each runner does. The owner's
step-by-step release, rollback and outage runbooks are in
[desktop R2 delivery](desktop-r2-delivery.md). For Steam depots and macOS tests, see
[store builds](store-builds.md).

## Workflows

| Workflow (Actions name) | File | Use |
| --- | --- | --- |
| **Build desktop release (R2 content)** | `.github/workflows/desktop-release-r2.yml` | every desktop release from the helper-train release T on |
| **Repoint the desktop live channel (rollback)** | `.github/workflows/desktop-repoint.yml` | a rollback to a retained release; realigning R2 after an outage |
| **Build desktop release** | `.github/workflows/desktop-release.yml` | the [transitional full-CI workflow](#the-transitional-full-ci-workflow) |
| **Retire previous published client (no-op)** | `.github/workflows/published-client-cleanup.yml` | prunes nothing; keep it **disabled** in the Actions UI |

All four:

- are **dispatch-only**, so no push or merge starts a release;
- share the concurrency group `rabbitlands-desktop-release` with
  `cancel-in-progress: false`, so one release operation runs at a time. A run waiting
  for an approval holds the group, so a repoint dispatched meanwhile queues behind
  it.

GitHub dispatches only workflows that exist on the
[default branch](https://docs.github.com/en/actions/how-tos/manage-workflow-runs/manually-run-a-workflow),
so a new workflow can be dispatched only after it is promoted to `master`. A run
uses the workflow file and the head commit of the branch it is dispatched on
(`master` or `develop`). Both platforms use that exact commit, even if the branch
advances during the run.

## Running a release

1. Upload both content sets first, or choose `ci` sources (see the
   [forward runbook](desktop-r2-delivery.md#releasing-the-forward-runbook)).
2. Open Actions -> **Build desktop release (R2 content)** -> **Run workflow**. Choose
   the branch whose head is the release commit, and fill in:
   - `windows_source`, `linux_source`: `r2` (content uploaded from the build
     machine) or `ci` (content built on the runner);
   - `windows_set_sha256`, `linux_set_sha256`: the content set hashes that
     `desktop_content.py pack` printed (64 lowercase hex), for `r2` sources only;
     leave them empty for `ci`;
   - `dry_run`: build and check only.
3. Approve the three environments in order:
   - `desktop-sign`, after reading the content summaries;
   - `desktop-publish`, after the end-to-end tests and finalize;
   - `desktop-promote`, after the local R2 publish and the post-publish check.

The **prepare** job refuses, before anything is written:

- a run that is not a `workflow_dispatch` of this workflow from `master` or
  `develop` of this repository, or that checked out another commit;
- the signing key in its environment;
- invalid or inconsistent inputs. Each input is regex-validated, and the same set
  hash may not be given for both platforms;
- a tree without whole-release retention (`RETENTION_SCHEMA` below 2);
- an `r2` source when the commit's updater cannot read R2 rows. Its
  `src/updates/release.gd` must declare `const CODEC_SCHEMA := 3` and exactly
  `const DESKTOP_ASSETS := "https://assets.rabbitlandsgame.com/desktop/v1/"`, and its
  `src/updates/package_updates.gd` must read 2000 packages
  (`release.packages.size() > 2000`). The refusal names the missing declaration;
- another client draft;
- a commit that already has a published release. A published commit is never
  released twice.

Otherwise it finds or creates the draft `client-<commit>` (none in a dry run).

## Jobs

| Job | Runner | Token | Environment | Does |
| --- | --- | --- | --- | --- |
| `prepare` | Ubuntu 24.04 | write | - | validates the dispatch, finds or creates the draft |
| `Content <platform> (r2)` | Ubuntu 24.04 | read | - | `desktop_release_ci.py verify-content`: checks the uploaded set ([below](#content-check-r2-sources)) |
| `Content <platform> (ci)` | the platform's runner | write | - | `desktop_release_ci.py build-content`: builds the content on the runner ([below](#the-ci-content-leg)) |
| `Executables <platform>` | Windows Server 2025 / Ubuntu 24.04 | read | - | engine, native runtime, helpers, root files, CI packages |
| `Sign the release manifests` | Ubuntu 24.04 | read | **`desktop-sign`** | signs both platform manifests |
| `Installer <platform>` | the platform's runner | read | - | verifies the envelope with Godot; builds `setup.exe` or `download.sh` |
| `Stage the GitHub downloads` | Ubuntu 24.04 | write | - | uploads CI packages and helpers to the pools, and manifests and installers to the draft |
| `End-to-end <platform>` | the platform's runner | read | - | installs from R2 and GitHub with the shipped binaries, starts both profiles, re-checks |
| `Finalize the draft` | Ubuntu 24.04 | write | - | verifies every download; writes the inventories and notes |
| `Publish (not latest) with signed pointers` | Ubuntu 24.04 | write | **`desktop-publish`** | signs both pointers; publishes the release as not latest |
| `Promote to GitHub latest` | Ubuntu 24.04 | write | **`desktop-promote`** | confirms the live R2 pointers, flips `latest`, prunes |

Each later job names the result of every job it needs. A skipped content leg is
accepted only where that platform used the other source.

### Dry run

`dry_run: true` runs only `prepare` (no draft and no GitHub write), the content
jobs, `Executables` and `Installer`. In a dry run:

- the installer job only installs the tools and measures the disk;
- a `ci` content leg builds, qualifies and packs, but uploads nothing and opens no
  upload sink. Its caches may still be saved.

Signing, staging, the end-to-end tests, finalize, publish and promote are skipped.
The shipped executables pin the production key, so a test-key end-to-end run is not
possible. The dry run catches toolchain, disk and permission problems without
touching release state. It shows a Cloudflare challenge on runner requests only
with an `r2` source. With `ci` sources, its R2 reads fall back to GitHub without
failing, and the first R2 reads in this workflow that must succeed are those of
T's promote job.

An `r2` dry run needs a commit whose updater reads R2 rows and a content set already
uploaded for that commit, so dry runs before the first content upload use `ci`
sources. Run one before the first real release, and read the disk probes it records.

## Runner rules

These hold in `desktop-release-r2.yml`. The workflow and tool tests check them:

- **No R2 credential, ever.** Every R2 read is anonymous HTTPS through
  `https://assets.rabbitlandsgame.com/desktop/v1/`, and no job writes to R2. The
  build machine puts pointers live.
- **The signing key** (`CLIENT_UPDATE_SIGNING_KEY`) is an environment secret of
  `desktop-sign` and `desktop-publish` only.
  - It appears in exactly two step environments: the sign step and the publish
    pointer step. Both run only `desktop_release_ci.py sign` or `pointer`, with no
    other token or secret.
  - The key is read from the environment, kept in memory and never written to
    disk.
  - `promote` holds no secret at all.
- **No caches where anything is shipped, signed or published.** Specifically:
  - there is no `actions/cache` outside the `ci` content leg;
  - there is no `restore-keys` anywhere in the file;
  - setup-python has no cache;
  - the native runtime is compiled every run;
  - the engine template comes from the hash-pinned download every run;
  - helpers are reused only from a signed earlier manifest.
- **Read-only where possible.** The content check, executables, signing, installers
  and end-to-end jobs have `contents: read` and no GitHub token. Only `prepare`, the
  `ci` content leg, `stage`, `finalize`, `publish` and `promote` can write, and only
  `contents`.
- **Checkouts.** Every checkout uses the run's exact commit with full history
  (`fetch-depth: 0`) and blob filtering, without persisted credentials. It is
  sparse; under `godot-client/` it holds `tools/`, `src/updates/`,
  `src/app/main.tscn`, `assets/branding/`, `assets/audio/CREDITS.txt`, `native/`,
  `data/update_public.pem` and `project.godot`.
- **Exact bytes on Windows.** The Windows image sets `core.autocrlf=true`, which
  checks text files out with CRLF. Every job that can run on Windows therefore
  starts by setting `core.autocrlf false` and `core.eol lf` in the runner's global
  Git config, before `actions/checkout`. The native build proves its inputs against
  their blobs, and the runtime descriptor and the setup helper's scripts ship as
  they are checked out. Each job entry point (`actions_release.py`,
  `store_build.py`) runs `runner_release.exact_checkout` first. It refuses a
  converting checkout, or any checked-out file that differs from its blob, before
  anything is downloaded or built.
- **Inputs** reach scripts only through `env:`, never through `${{ }}` inside a
  `run:` script.
- **Artifacts** are passed by exact name, never by pattern. Each producer exports a
  digest of the artifact's files (path, size, SHA-256), and every consumer checks
  it.
- **Actions** are pinned by full commit SHA.
- **Python dependencies** are installed with
  `--require-hashes --no-deps --only-binary=:all:` from exact lock files:
  - `desktop-release-requirements.txt` for the ordinary jobs;
  - `desktop-sign-requirements.txt` (cryptography, cffi, pycparser) for the jobs
    that hold or check the key;
  - `desktop-content-requirements.txt` for the `ci` content leg.

## Content check (r2 sources)

`desktop_release_ci.py verify-content` takes the dispatched hash and makes these
checks:

1. **The set.**
   - It downloads the set anonymously (at most 32 MiB), checks its SHA-256 and parses
     it as canonical bytes.
   - It validates the set with the module's own constants, never the set's own
     fields: header, commit, platform, public key hash, ASCII paths, CI-owned
     paths, `.gdextension` rules, the package and part counts, and part URLs in the
     derived R2 form only.
2. **The builder block.** It requires a release-mode, clean, release-build set; a
   development set never reaches signing.
3. **The identity.** It recomputes the release identity from the commit.
4. **Every part exists.** It HEADs every distinct part (200 and the exact length).
5. **New bytes are decoded.** It downloads every package the currently published
   signed manifest does not already have, plus the release descriptor and the
   `client` package. For each package:
   - the joined parts must hash to the package;
   - the ZIP must hold exactly the expected entries;
   - every member is decoded (deflate, or one zstd frame per chunk) and checked for
     size and SHA-256;
   - every member's first bytes are checked for PE, ELF and Mach-O magic.

   The first R2 release after a GitHub-hosted one therefore downloads every part.
   Egress is free.
6. **The descriptors.** Both copies of the release descriptor must equal the
   recomputed identity. The core pack's embedded `res://data/client_release.json`
   must equal it too, and `.godot/extension_list.cfg` may name only the CI runtime
   extension.
7. **The split pack.** PCKs are read with `tools/pck_split.py`, the packager's own
   reader. The core pack's `data/content_packs.json` must list exactly the set's
   `app/packs/` files, with their signed size and SHA-256; beside a single PCK there
   may be no `app/packs/` file at all. Every new or changed content pack must have
   the core's PCK format, engine version and declared entry count, and may hold only
   entries that `pck_split` assigns to that pack and that the core does not hold. So
   no script, identity or extension list can ride in a content pack.
8. **The summary.** It writes the artifact `content-<platform>` (`set.json`,
   `verified.json`, `summary.md`) and appends the summary to the job page. The
   summary lists:
   - added, changed and removed package ids;
   - whether the core `client` package changed;
   - new file extensions and new bytes;
   - the PCK layout: split or single, the number and bytes of content packs, and
     how many were read entry by entry;
   - the builder block.

   The owner reads it before approving `desktop-sign`.

## Executables

`desktop_release_ci.py executables` runs on the native runner for each platform,
with no secret and no cache:

1. **Native runtime.** `app/bin/client_runtime/` (library, `.gdextension`,
   `runtime-manifest.json`) is compiled every run from the commit's native sources.
   It uses Rust 1.99.1 (minimal profile), CMake, Ninja and MSVC x64 or GNU x86_64. A
   cache hit is refused.
2. **Engine.**
   - Windows: a tiny project exported with the game's preset (`embed_pck=false`)
     and the game's branding, giving `app/RabbitLands.exe`.
   - Linux: a copy of the release template, giving `app/RabbitLands.x86_64`.
3. **Helpers.**
   - `desktop_helpers.py` computes a fingerprint over the inputs: the updater
     scripts, branding, trust file, editor and template hashes, a fixed minimal
     helper preset and the tool version.
   - When the previous signed release has the same fingerprint, its updater and
     uninstaller rows are downloaded and checked against their signed SHA-256, so
     the helper bytes are reused exactly. Otherwise the helper is exported.
   - A change to the game's own export preset does not change the fingerprint.
   - Local and full-CI builds export their helpers the same way:
     `client_release.export_launcher` uses the same project files, fixed preset and
     fingerprint, and keys its local helper cache by that fingerprint.
4. **Root files.** They are made after the helper exists, so launchers start the
   updater with `--launch-only` and the production server
   `game.rabbitlandsgame.com:2001`. They include the human-testing and pilot
   launchers, plus `AUDIO-CREDITS.txt`. Each is recorded by name, size and SHA-256.
5. **CI packages.** `engine` and `native-runtime` are written in the normal package
   format, in partitioned pool parts.
6. **Comparison record.** It compares the CI executable's hash with the build
   machine's. The difference is a warning, not a gate, until byte equality has been
   proven once; the native library is expected to differ.

The artifact `exec-<platform>` holds the CI packages, helpers, root files and their
rows.

## Signing

The `sign` job is a small Ubuntu job: no cache, no native build and no Godot. Only
the hash-locked `cryptography` stack is installed. It does the following:

1. It checks that each set's bytes hash to the dispatched input (`r2`), or that the
   `ci` leg's own record says it uploaded every part.
2. It validates each set again and checks the `exec-<platform>` records.
3. It builds both payloads:
   - schema 3 (see the next step), `bootstrap_schema` 1;
   - `sequence` (UTC seconds), the ancestors and the totals;
   - the content and CI rows, and helper rows in the legacy GitHub form;
   - the launch arguments, the helpers fingerprint, the root files and the content
     source with its set hash.
4. **The schema follows the commit's own updater.** A commit whose updater cannot
   read schema 3 gets schema 2, and then only `ci` sources are accepted. Such a
   release still cannot be published: the publish job signs pointers only for
   schema-3 manifests and refuses. Real releases through this workflow start with
   T.
5. It applies the 15 MiB envelope gate: released clients cap manifests at 16 MiB.
6. It signs, and verifies again in Python.

Nothing is written unless both platforms sign. The `envelopes` artifact holds
`<version>-<platform>.json`, the alias `RabbitLands-<platform>.json` and `sign.json`.

The publish job signs the two pointers in the same way, later and under its own
approval (see [publish](#publish-promote-and-retention)).

## Installers

The installer job first verifies each envelope in Python. It then verifies it again
with the commit's own `verify_client_release.gd` and updater scripts, taken from
Git, in a throwaway Godot project.

- **Linux.** `<version>-download.sh` embeds the signed manifest and the updater
  row's SHA-256. It downloads the updater from GitHub, checks it with `sha256sum`,
  and installs from the embedded manifest.
- **Windows.** `<version>-setup.exe` is built from a skeleton stage (root files,
  helpers, the recomputed `app/client-release.json`, branding) and the envelope.
  - The setup checks the installed files of each package and downloads only the
    parts of packages that are not current: an R2 part from its derived
    `desktop/v1/parts/<sha256>.bin` URL, a CI part from its pool. Inno Setup checks
    each download's SHA-256, and the embedded setup helper checks it again against
    the signed manifest. It moves each verified part into its cache, so setup asks
    for the download's space once.
  - The job **refuses** a manifest the commit's setup helper
    (`tools/install_client_payload.gd`) or the packager's online-installer script
    could not install: an unknown schema, R2 rows the helper cannot read, or more
    packages than it reads. That way it never builds a setup that cannot install.

## Staging and the shared download pools

GitHub keeps hosting the downloads CI builds. Helpers go to the permanent legacy
`client-assets` prerelease, which older updaters require. Package parts go to the
partitioned `client-assets-0` to `client-assets-f` prereleases, chosen by the first
hex digit of the part's SHA-256. The pools are never marked latest. They are file
stores, not version history.

`stage` uploads exactly the CI rows and helper rows of the signed manifests, never
rows taken from an unsigned record. It also adds the manifests, aliases and
installers to the draft. Everything is checked before the first upload.

Upload rules:

- **Stable names.** Part names are `RabbitLands-pkg-<SHA256>.zip.part`. Helper
  names carry their kind, full SHA-256 and platform extension. Unchanged bytes keep
  their names and URLs across builds and commits.
- **Reuse.** Before each upload, the local SHA-256 and size are compared with
  GitHub's recorded digest, size and completed state. An exact match is reused
  without an upload, rename or delete. Changed bytes get a new name.
- **Conflicts stop the build.** An unexpected completed file with a conflicting
  checksum stops the build. An identical upload in flight is waited for. An
  abandoned reservation older than six hours can be retired and retried.

## End-to-end tests

The `e2e` job runs on each platform's own runner. It uses only the signed envelope,
the executables and the installers from the artifacts:

1. **Fresh install.** The shipped updater (which must equal the signed `updater`
   row) runs
   `--headless -- --root <work>/install/RabbitLands --install-update --update-only --install-manifest <envelope>`.
   - The install exercises R2 parts, GitHub CI packages and helpers, the helper
     handover and per-file staging.
   - Afterwards every signed file is hashed again.
2. **Startup smokes.** The installed game runs `--headless --quit-after 600` with
   `ELORIA_VRAM_SELF_TEST=1` in both profiles: `legacy`, and
   `-- --optimization-profile=human-testing`.
   - The job checks `SMOKE_FAILURES`, the VRAM self-test and the startup snapshot.
   - `human-testing` must report the native runtime as available, in mode `rust`.
   - The installation must be unchanged by the launches.
3. **Re-check.** The installed updater runs again with `--update-only` and the
   envelope. It must report `0 of N packages needed downloads`, and leave the tree
   unchanged.
4. **Linux `download.sh`.** Its content is checked: the updater URL, the
   `sha256sum` line and the embedded envelope. It is then run under `xvfb-run` with
   a timeout, and must install the commit.
5. **Windows `setup.exe`.** It runs silently into a temporary folder, but only when
   the runner has at least 1.25 times the setup's declared disk need free. Otherwise
   the step is recorded as skipped for disk. Finalize then asks for the
   [local pre-promote setup check](desktop-r2-delivery.md#releasing-the-forward-runbook)
   before `desktop-promote`.

Linux steps run as a throwaway unprivileged user, under `xvfb-run` except for the
headless startup smokes, in a work folder that user can reach (`/mnt/rl-e2e`).
Windows steps use throwaway user folders. Each step is recorded with its result,
time and free disk; the receipt is written even on failure. The logs are kept as an
artifact.

## Finalize

`Finalize the draft` (`finalize_runner_release.finalize_r2`) makes these checks
before changing the draft:

1. **Manifests.** Both manifests verify and match `sign.json` and their aliases.
2. **Content.** Each manifest's content packages are exactly its set's packages.
   The set hashes to the signed `content.set.sha256`.
3. **Row forms.** Every row has its expected form:
   - R2 rows: the derived R2 URL, for `r2` content only;
   - pool rows: partitioned pool URLs, for CI packages and `ci` content;
   - helpers: legacy `client-assets` rows.
4. **The end-to-end receipts.** Every required step must have passed, and the
   `human-testing` startup must report the native runtime. The sets' qualification
   blocks are informational only.
5. **Installers.** `download.sh` is recomputed from the signed data, and must equal
   the draft's file. The draft's `setup.exe` must equal, by size and SHA-256, the
   only file of the `installers-windows` artifact, which the job checks against
   the installer job's digest first.
6. **GitHub rows.** GitHub rows are checked by digest in the draft and the pools. R2
   rows are never looked up on GitHub.
7. **No other draft.** Another client draft is refused, never deleted.

It then writes:

- **`R2-SHA256SUMS`**: every R2 part, each `r2` platform's set, and both R2 manifest
  copy keys. Pointers are mutable, so they are never listed.
- **`SHA256SUMS`**: every GitHub file, `R2-SHA256SUMS` included, but no R2 row and
  not the pointer assets, which publish adds later.
- **The release notes.** They name the R2 base only when a platform uses `r2`.
- **The release-verification artifact**, kept 30 days. It holds `client_updates.json`
  (its manifest URLs stay GitHub commit-tag URLs, for older clients) and
  `runner-release.json`, the input of publish and promote.

## Publish, promote and retention

**Publish** (`desktop-publish`):

1. **Sign the pointers.** The key step signs both pointers with a new `sequence`,
   `rollback: false`, the release id and the run id. A key-less step then checks
   that they are forward pointers of this commit and release, naming the manifests
   signed in this run.
2. **Check the draft and GitHub `latest`.** `publish_r2` re-verifies the draft. It
   refuses a release that is already GitHub `latest`, and requires `latest` to be
   an ancestor.
3. **Upload and publish.** It uploads `RabbitLands-<platform>-pointer.json`. A
   re-run replaces only this release's own pointers. Then it runs
   `gh release edit --draft=false --prerelease=false --latest=false`.
4. **Confirm that `latest` did not move.** It confirms that `/releases/latest` still
   names the previous release. Released games discover only through that, so the
   new release stays invisible to them. If GitHub moved `latest` anyway, the job
   fails and asks you to mark the previous release latest again.
5. **Print the next command.** The summary prints the local
   `upload_desktop_assets.py publish` command.

**Promote** (`desktop-promote`, no key):

1. **Check the release.** The release must be published (not a draft or
   prerelease), and its downloads still verify.
2. **Check each platform.** For each platform:
   - its pointer asset must verify as this release's forward pointer;
   - an anonymous GET of `https://assets.rabbitlandsgame.com/desktop/v1/channels/live/<platform>.json`
     must be **byte-equal** to that asset;
   - the R2 manifest copy the pointer names must be live and hash to the signed
     manifest.

   A 404 or any difference refuses with "Run the local publish for client-<X>
   first; GitHub latest is unchanged."
3. **Flip `latest`.** It runs `gh release edit --latest`, after an ancestor check of
   the current `latest`, and confirms it.
4. **Prune.** It runs `prune_published_release.prune` with the retained set. If
   pruning fails after the flip, re-run the promote job: it skips the flip and
   prunes again.
5. **Print the next command.** The summary prints the `check-policy` command for the
   server policy.

**Retention** (`RETENTION_SCHEMA = 2`). Pruning runs only in promote, never in
publish or on a release event. It keeps these releases, each with every pool asset
its manifests reference, helpers included:

- GitHub `latest`;
- every published release newer than `latest`;
- any release whose publication time cannot be read;
- the two most recently published releases before `latest`;
- the pinned last GitHub-hosted release (`PINNED_GITHUB_HOSTED`, set in the first R2
  content release). The prepare job refuses a release with `r2` content while the
  dispatched commit has no pin; dry runs and `ci`-only releases need none.

The prune rules:

- **Verify first.** Before deleting anything, it verifies every retained release's
  own `SHA256SUMS`. One unreadable inventory stops the prune.
- **Retired releases go.** It deletes only the retired releases.
- **Unreferenced pool assets go, with exceptions.** It deletes pool assets that no
  retained release references. It leaves the pools alone while a client draft
  exists, or while a release outside the retained set still exists.
- **Never R2.** It never touches R2.

**Never recreate, re-publish or re-tag an old `client-<sha>` release.** Release
events run the workflow file of the released tag. Older tags carry the old
cleanup workflow, which deletes every newer release and every pool asset outside
its own inventory. That is why the owner keeps
**Retire previous published client** disabled. Rollbacks only run
`gh release edit --latest` on a retained, published release (see the
[rollback runbook](desktop-r2-delivery.md#rollback-runbook)).

## Rollback workflow

`desktop-repoint.yml` takes `target_commit` and `platforms` (`both`, `windows` or
`linux`).

- **`check`** (read-only, no approval) verifies the target `client-<target>`:
  - it is published, by the project account or its workflow;
  - its tag points at the commit;
  - each selected platform's manifest verifies with the dispatched commit's key and
    is schema 3 (T or later);
  - every download the manifest names answers an anonymous HEAD with its exact
    length.
- **`repoint`** (`desktop-publish`) does the following:
  1. it checks again;
  2. it signs rollback pointers with a higher `sequence`, before any write, so a
     missing key stops the job before GitHub changes;
  3. it makes the target GitHub `latest` (GitHub first) and confirms it;
  4. it uploads the pointers as the target release's pointer assets (replacing
     the ones there), confirms them, and prints the local
     `upload_desktop_assets.py publish --rollback` command.

## The `ci` content leg

With a `ci` source, `Content <platform> (ci)` builds that platform's content on its
own runner, from the dispatched commit. This is the earlier hosted build, minus
anything that signs, publishes or builds an installer. It is used for the
helper-train release T, as a Linux fallback, and during an R2 outage.
`desktop_release_ci.py build-content` works in this order:

1. **Early refusals.** It refuses the signing key in its environment, work, output
   or cache folders inside the checkout, a non-empty output, and an existing native
   cache.
2. **Tools.** It installs the pinned editor and template (no Inno Setup), prepares
   the software graphics, and compiles the native runtime from the commit's blobs
   into an empty cache.
3. **The build.** It runs `package_client.py` in runner mode with
   `--distribution github --release-build --no-client-updates --no-zip --no-fetch
   --full-optimizations --prepared-world` and the production `--server`. The
   packager's own upload sink refuses every upload.
4. **Stage checks.** It checks the stage: the descriptor equals the recomputed
   identity, the core pack's identity and extension list are correct, and the split
   layout passes the same `pck_split` checks as the
   [content check](#content-check-r2-sources).
5. **Packing.** It packs the stage with `desktop_content.py --source ci`. That
   applies the same rules as a local pack, keeps the partitioned GitHub pool URLs,
   and validates the set with the commit's own package limit.
6. **Upload.** It uploads every part through the digest-verified pool sink. It
   deletes each local part once GitHub confirms it, then HEADs every pool URL
   anonymously.
7. **The artifact.** It writes `content-<platform>` in the same shape as the `r2`
   check, with `uploaded: true` and an owner summary that compares the content with
   the live release.

`sign` accepts a `ci` set only as this job left it: a finished, confirmed upload.

**Caches** in this leg are restored and saved by **exact key only**, in their own
`rl-desktop-ci-` namespace:

- the import and graphics cache, keyed on the committed asset and tool inputs, so
  ordinary game script changes do not invalidate it;
- the world preparation cache, keyed on the same inputs plus the world producer
  scripts.

No native cache is used. A cache miss never skips validation. Its trust level is
that of the earlier hosted workflow; no shipped executable comes from this job.

### Disk budget (ci leg)

The leg keeps the runner-mode budget:

- **The budget.** 14,000,000,000 bytes, with 2,000,000,000 bytes reserved, and a
  7 GB reservation before any source exists. The build checks its measured working
  set and upcoming allocations against the rest, and also checks actual free space.
- **What counts.** File sizes include the Git object store and the supplied tool
  folders; hard links count once.

Space is saved by the following:

- **Source.** The build checks out only the build scripts, with full ancestry and
  blob filtering. It streams the commit's source archive into one disposable
  worktree, and checks each file against its Git blob.
- **Authoring trees.** World-authoring references are checked once, and the
  editor-only tree is retired before import.
- **Stage.** Unchanged assets and graphics sidecars are hard-linked into the stage.
- **Graphics.** Graphics are encoded in batches with bounded scratch space.
- **Deterministic package ZIPs.** Each package ZIP is written straight into bounded
  parts.

Unlike the earlier workflow, the pack writes all local parts while the stage and
caches still exist. That is about 3.9 GB of deflate-1 parts for a 5.7 GB stage. The
pack refuses cleanly when free space is short. The job's disk probe records every
volume; the dry run measures it before a real release. An earlier cold-cache Windows
rehearsal of the older packaging path peaked at 11.10 GB, which is not a guarantee
for this one.

## What every content build qualifies

These checks belong to `package_client.py`. They apply equally to the build
machine's local builds and to the `ci` leg.

### Full optimization packages

Release content builds use `--full-optimizations` to package and qualify the
optional optimization paths.

- Ordinary launches default to `legacy`: the newer native backends and prepared
  content paths stay off.
- `--optimization-profile=human-testing` enables, explicitly:
  - Rust mounted poses, remote presentation and heat bolts;
  - Rust resource admission;
  - prepared content in `auto` mode;
  - the `lazy-source-v1` object policy.

This build policy is not a performance claim. See
[optimization testing](client-optimization-testing.md).

### Shipped world preparation

Windows and Linux content prepares the complete production geometry scope during
the build, including its collision faces and paving coverage. Texture pixels stay in
their existing raw/VRAM assets.

- **Renderers.** Windows uses Forward+ with system WARP. Linux uses Forward+ with the
  distro-installed Mesa lavapipe Vulkan driver, on native Linux.
- **Before the cook.** The actual CPU adapter, format and native-buffer observations
  must pass.
- **Where the data lives.** The finished data stays loose in `app/prepared-world/`,
  bound by a small record in the core pack.
- **The cache.** A persistent, verified world-preparation cache reuses unchanged
  source closures. Reuse depends on compatibility, producer policy and producer
  inputs, not the game commit. So a code-only release does not download every map
  again.
- **Custom builds.** Release content builds require this step. A custom native
  build can omit it with `--no-prepared-world`, or supply a matching
  `--prepared-world-catalog` made by the same engine executable. The
  `--world-preparation-cache` folder is kept separately from the other asset
  caches.

### Renderer and package qualification

- **Renderer.** Before compiling or loading game assets, a tiny isolated project
  qualifies the actual renderer:
  - Windows identifies system WARP by its DXGI adapter identity.
  - The engine must report a CPU adapter, the required texture formats, and a
    successful native buffer save and reload.
  - A dummy or headless renderer, an unexpected hardware adapter or an unsupported
    format mask fails qualification.
- **Startup and the final pack.** Before a stage counts as qualified, the build
  requires:
  - positive native contract checks;
  - ordinary startup with the newer features off;
  - a separate `human-testing` startup with all six paths active;
  - acquisition of every planned prepared entry from the final pack at each texture
    quality.
- **Rejections.** It rejects engine errors, skipped work and changes to the stage.

The version 2 optimization proof binds both startup snapshots. The content set
records the proof's hash and the smoke profiles, for information. Release gating
uses the CI end-to-end receipts.

Software rendering and these functional guards do not replace visual review,
gameplay checks or target-hardware performance qualification.

## The transitional full-CI workflow

`desktop-release.yml` (**Build desktop release**) is the earlier workflow. It builds
the whole release on two hosted runners with `runner_release.py`:

- a draft job;
- separate Windows and Linux build jobs (content, executables, signing and
  installers);
- `finalize_runner_release.py`;
- `publish_runner_release.py`, which publishes the release as latest and prunes.

It keeps a verified import and texture cache. A code-only release normally uploads
only the client code package, a fresh installer and the signed metadata. Its
manifests come from the same writer as the R2 workflow's
(`release_manifest.release_payload`), with the lowest schema their rows need, and no
`sequence`: R2-aware updaters treat them as older than any R2-era release.

Its status:

- It has **no push trigger**. Dispatch it manually from `master` or `develop`.
- Its first job, `r2-guard`, sends an anonymous GET to both live R2 pointers. It
  passes only when both return 404. A live pointer, a challenge page or a transport
  error refuses the run, so it fails closed.
- Once the owner moves `CLIENT_UPDATE_SIGNING_KEY` into the environment secrets and
  deletes the repository secret, it can no longer sign at all.
- Its publisher refuses an R2 receipt, and its pruning now keeps the retained set.
- It will be deleted one release after the first R2 content release.

The local `build_release.py` path documented in
[client updates](client-updates.md#upload-a-complete-desktop-release) also needs the
private key. In the R2 process the key lives only in GitHub environment secrets.

## Toolchains

- **Godot and Inno Setup.** `setup_runner_tools.py` downloads Godot 4.7.2 and Inno
  Setup 6.7.3 from their official releases. It checks pinned sizes and SHA-256
  hashes, extracts only the job's release template, and removes the archives.
- **Native builds.** These need Rust 1.99.1, CMake, Ninja and MSVC x64 or GNU x86_64.
  `RUSTUP_HOME` and `CARGO_HOME` stay in an accounted job folder.
- **Linux packages.** Linux jobs also install Mesa, Xvfb and xauth.
- **Python** is 3.13, with the hash-locked files above. `runner-requirements.txt`
  stays the transitional workflow's lock file.

## First hosted run

These cannot be proven without a hosted run. The dry run is the first check:

- **Matrix outputs.** Matrix jobs export per-platform digests
  (`windows_digest`, `linux_digest`). Their expectations fail closed if GitHub
  merges matrix outputs differently.
- **Disk.** The disk use of the `ci` leg and the Windows setup.exe test.
- **Cloudflare.** Cloudflare must not challenge the runners' requests to `/desktop/*`.
  A `ci`-only dry run does not prove this (see [dry run](#dry-run)).
- **actionlint.** It has not been run on these files; run it before the first push.

## Checks

```
python -B -m pytest -q -p no:cacheprovider godot-client/tests/test_desktop_release_workflow.py godot-client/tests/test_actions_release.py godot-client/tests/test_desktop_release_ci.py godot-client/tests/test_release_manifest.py godot-client/tests/test_desktop_helpers.py
python -B -m pytest -q -p no:cacheprovider godot-client/tests/test_prune_published_release.py godot-client/tests/test_shared_release_assets.py godot-client/tests/test_finalize_runner_release.py godot-client/tests/test_publish_runner_release.py godot-client/tests/test_release_entrypoint_imports.py
```

The workflow tests parse the YAML strictly. Among other things, they check that:

- every command and flag the workflows run exists in the real tool parsers;
- the rules under [runner rules](#runner-rules) hold;
- the job graph and dry-run gating are correct;
- no machine paths appear.
