# Desktop releases with content on R2

Windows and Linux releases keep their game content on Cloudflare R2. The owner's
build machine builds, qualifies and uploads the content. GitHub Actions builds only
the executables, signs the release, builds the installers, tests the shipped
combination and publishes it. From the helper-train release T on, installed games
and updaters find a release through a small signed pointer on R2. They fall back to
the GitHub release when R2 cannot be used.

R2 is untrusted transport. Every byte a player installs is checked against a row of
a manifest signed with the release key, as before. R2, Cloudflare and every R2
credential can delay or deny an update, but cannot change what a player runs.

Related pages:

- [Runner builds](runner-builds.md): the workflows, their jobs and the `ci` content
  build.
- [Automatic client updates](client-updates.md): the updater, release discovery,
  downloads and staging.
- [Client compatibility](client-compatibility.md#update-downloads): what to collect
  when an update cannot download.
- [Store builds](store-builds.md): Steam and macOS, which this page does not change.
- [Browser hosting](browser-hosting.md): the browser prototype. It uses the same
  bucket under its own `browser/` prefix, which desktop tools never read or write.

## Status

As of 2026-11-07 release R1 (`9baf44f2`) is GitHub `latest`, with its Windows content
on R2 and its Linux content on GitHub. T (`01279356`) stays published and was never
`latest`. The server's `client_updates.json` has not been changed for R1. Every part
of this path is in the repository:

- the build machine's tools: pack, upload, publish, public verification and the
  policy check;
- the release and repoint workflows, with whole-release retention;
- the player side: the updater's R2 reader with per-part retries, pointer discovery
  with the GitHub fallback, the installed-release record, the downgrade guard,
  server-target rediscovery, and the Windows online setup for schema 3 and R2 rows
  (see [what players' games and updaters do](#what-players-games-and-updaters-do)).

The uploader's self-test passed against the bucket and the custom domain. It proved
conditional create, conditional pointer replacement, SHA-256 upload checksums,
anonymous HTTPS reads, Range requests, and downloads by Godot's `HTTPRequest` on
Windows and by Inno Setup's download page. The updater, the game's start check and
the setup helper were tested against local HTTPS fixtures that use the same key
layout. Still open: the same Godot download check and the updater checks on native
Linux, a full-size setup.exe with R2 part URLs, and any IPv6 check.

These are the steps, in order. Steps 1 to 4 are done; only step 5 remains:

1. **The owner's one-time setup** (below), including the push of these workflows to
   `master`, then a dry run.
2. **The helper-train release T.** Both platforms use the `ci` source. T ships the
   R2-aware updater and setup while the content is still on GitHub. T is also the
   first release signed with the new release key (see
   [key rotation](#key-rotation-2026-11)), so installed games cannot verify it. T
   stays published and not latest, as the pinned last GitHub-hosted release: its
   setup.exe refuses every existing installation, so returning players do not use
   it. The owner rejects T's waiting `desktop-promote`, because a waiting run holds
   the release concurrency group. T's manifest copies and pointers are the first
   objects under `desktop/v1/`.
3. **The first full content upload**, after the package format settles. The zstd
   re-encode changes every part hash, so upload once, with or after it.
4. **The first R2 content release, R1.** Its commit pins T as the last GitHub-hosted
   release (`PINNED_GITHUB_HOSTED`). R1 is the first new GitHub `latest` since the
   rotation, and its setup.exe is the installer returning Windows players use.
   Installations of T update to R1 through the R2 pointer. When its updater inputs
   are unchanged since T, it reuses T's updater byte for byte, and players download
   no new updater.
5. **Retire `desktop-release.yml`**, one release after R1.

The workflow accepts an `r2` content source only for a commit whose updater reads R2
rows: `src/updates/release.gd` must declare `const CODEC_SCHEMA := 3` and exactly
`const DESKTOP_ASSETS := "https://assets.rabbitlandsgame.com/desktop/v1/"`, and
`src/updates/package_updates.gd` must read 2000 packages. Commits from T on do.

Until the owner moves the signing key into the new environments,
`desktop-release.yml` can still be dispatched, as described in
[runner builds](runner-builds.md#the-transitional-full-ci-workflow). It refuses to
run once a live R2 pointer exists.

## Key rotation (2026-11)

**Why.** The project no longer has the private half of the release key that signed
every release up to `client-945042f0`, so it cannot sign with that key again. The key
is retired, not gone: a copy may still exist elsewhere. On 2026-11-06 the owner
replaced it with a new RSA-4096 key. From the rotation commit on,
`godot-client/data/update_public.pem` holds the new public key, and
`CLIENT_UPDATE_SIGNING_KEY` holds its private half. The trust model and every
check are unchanged; only the key is new.

- **Releases start at T.** T is the first release signed with the new key. It must
  be built from a commit that contains the rotation: the sign job refuses a key
  that does not match the dispatched commit's `update_public.pem`. Content sets and
  stages made for an earlier commit pin the old key and cannot be used.
- **What players must do.** Every installed game pins the old key: in its core pack,
  `app/client-release.json`, its updater and its setup helper. None of them can
  verify T or any later release, so each player runs a new installer once, from R1's
  release page. Accounts and characters live on the server and are not affected.
- **Windows: R1's setup converts the folder.** T's `<version>-setup.exe` refuses every
  existing installation and can never be fixed, because a published commit is never
  released twice. R1's helper may overwrite a folder whose
  `app/client-release.json` holds the retired key (`RETIRED_KEY_SHA256` in
  `tools/install_client_payload.gd`, which is no updater input). Any other key,
  another repository, Steam or standalone ownership, the retired key with another
  platform, or a missing or non-text `public_key` stays refused before anything is
  written: "This installation belongs to a different distribution or signing key."
  The current key is not compared by platform, as before. The retired key
  decides only whether a folder may be overwritten. It never reaches a signature
  check, so holding its private half adds nothing here, and everything setup installs
  is verified with the new key.
- **Close the game first.** Setup checks for a running game only after it has
  downloaded, so a player with the game open waits, is refused, and loses that
  download. Setup's first page and the release notes say so. A game started from a
  `.bat` shortcut holds no lock and is not seen; the swap then fails and restores the
  folder (read in code, not run).
- **If setup is interrupted.** The helper finishes before Inno copies the root files.
  A cancel or crash in between leaves the old updater beside the new descriptor, and
  the shortcut says "Use its original installer". The original installer and the old
  uninstaller refuse that folder too. R1's setup heals it, so the release notes tell
  players to run it again. Inno cannot read paths over 260 characters, so setup
  fetches about 340 MB of such packages again and discards them; the rest is not
  downloaded again (inferred from a probe, not run). After a disk
  space failure, the verified downloads stay in the update cache and the retry
  downloads them again on top, so free more space or delete that folder's entry under
  `client-updates` (not measured).
- **Linux stays refused, on purpose.** `<version>-download.sh` over
  `~/Games/RabbitLands` and a standalone updater on either platform refuse a folder
  with the old key (`src/updates/bootstrap.gd`). Relaxing that check would change the
  updater inputs on both platforms, and R1 could no longer reuse T's updater. A Linux
  player with an old installation runs the old uninstaller first, or passes another
  parent folder to `download.sh`, and expects a full download.
- **Uninstallers from setups up to R1 leave some files.** Inno cannot remove paths over
  260 characters. Both routes leave them: Windows Installed apps runs Inno's uninstaller,
  and the Start Menu uninstaller calls it. Measured on 2026-11-07 on R1 test
  installations in a 48-character folder, as long as the default one: 6,019 files and
  409 MB in `app/prepared-world/`, the same again in any `.eloria-previous/`, the
  `.eloria-launcher-lock/` the Start Menu route writes, and the folder itself. By their
  lengths (230-236 characters inside the game folder), a folder of 22 characters or fewer
  leaves none of them, and one of 30 or more leaves them all. A later setup over those
  leftovers finished, and the game started (`945042f0`, 2026-11-06).
- **Setups built after that remove them.** Their uninstall code deletes the game's
  folders by name through the `\\?\` form first, and a `[Dirs]` row removes the folder
  when it is empty. An installation gets this uninstaller only by running such a setup:
  an update does not replace it.
- **An installation with no Inno uninstaller**, from a standalone updater, is removed by
  `src/updates/uninstall.gd`. Up to R1 its PowerShell cannot reach those paths where
  `LongPathsEnabled` is off. Measured on 2026-11-07 on real R1 installations in a
  48-character folder, through a copy of `powershell.exe` whose manifest sets
  `longPathAware` to false: R1's helper stops with an error after removing 4,164 of the
  26,170 files, all from `app/`, and with a leftover `.eloria-previous/` it removes none.
  The folder and the download cache stay. The helper with the `\\?\` form removes every
  file, the folder and the cache, and keeps the player's settings. An update does replace
  this helper, but the change gives it a new updater fingerprint on both platforms, though
  only Windows runs this code. So the first release carrying it exports a new helper
  (`helpers_reused` is false, on purpose) and every installation takes a handover. The owner
  chose on 2026-11-07 to ship it in the next release after R1.
- **What old installations do.** Their shortcuts still start the installed game. Its
  start check cannot verify T and offers nothing. An explicit updater run stops with
  "The release signature could not be verified." and changes nothing. Once the
  server's `required_commit` names R1 or later with `enforce: true`, the server
  refuses their logins with "A game update is required. ... Older installations
  need the latest client download." That is what makes players run the new installer.
  Set the policy as for any release, after `check-policy`. That check passes only
  after promote, so R1 is the first commit to require, and T's policy is never
  deployed.
- **Old installations still trust the retired key.** A holder of a copy would need
  write access to the repository's releases, a TLS break, or a player running a file
  they supplied through `--install-manifest`. The game server cannot steer them to a
  file. This ends for a player when they convert.
- **No rollback across the rotation.** A release before T is signed with the old
  key, which T and later releases do not trust, and its manifests are not schema 3.
  The repoint check refuses it. A rollback from R1 lands on T, and a repoint to T also
  makes T GitHub `latest`, which puts its refusing setup.exe on the latest page until
  a fix ships. Never re-publish or hand out a pre-rotation installer: it installs a
  game that can never update. Until R1 is promoted, the latest page still offers the
  `945042f0` installer; a player who takes it can convert later with R1's setup.
- **Retention and the pin apply from T on**, unchanged. T stays published and not
  latest as the last GitHub-hosted release, and the R1 commit pins it
  (`PINNED_GITHUB_HOSTED`). Pre-rotation releases stay only while they are among the
  two most recent before `latest`, and are then pruned as usual.
- **T has no previous release.** The tools verify the previous release with the
  dispatched commit's key, so the pre-rotation `latest` does not count. T's content
  summary lists every package as added, and T exports its own helper.
- **The post-publish check for T** is a fresh install from T's setup.exe and a
  pointer re-check (see [the check for T](#the-check-for-t)). Setup over an old
  installation belongs to R1 (see [the check for R1](#the-check-for-r1)).

## Who builds what

| Files | Built by | Delivered from |
| --- | --- | --- |
| Content packages: the core pack `app/RabbitLands.pck` (`client`), the content packs `app/packs/*.pck` (`pck-*`), the release descriptor, prepared world, actors, maps, audio, shared assets and records | the build machine (`r2` source), or a runner (`ci` source) | R2 `desktop/v1/parts/` (`r2`), or the GitHub `client-assets-<h>` pools (`ci`) |
| Content set: the unsigned list of content packages | the build machine, or the `ci` job | R2 `desktop/v1/sets/` (`r2`), or a workflow artifact (`ci`). Players never read it |
| Engine `app/RabbitLands.exe` / `app/RabbitLands.x86_64` (`engine` package) | Actions, every run, no cache | GitHub `client-assets-<h>` pools |
| Native runtime `app/bin/client_runtime/` (`native-runtime` package) | Actions, rebuilt every run, no cache | GitHub `client-assets-<h>` pools |
| Updater and uninstaller | Actions, with the pinned [helper template](#the-helper-template). While their inputs are unchanged, they are reused byte for byte from the previous signed release | GitHub legacy `client-assets` pool |
| Root files beside `app/` (launchers, `AUDIO-CREDITS.txt`) | Actions, after the helpers exist | listed in the signed manifest (`root_files`) |
| `<version>-setup.exe`, `<version>-download.sh` | Actions | the GitHub release `client-<commit>` |
| Signed manifests, alias, pointers | signed by Actions in owner-approved jobs | the GitHub release, plus immutable manifest copies and the live pointers on R2 |

Content sets never contain the CI-owned paths (`app/RabbitLands.exe`,
`app/RabbitLands.x86_64`, `app/bin/client_runtime/`), in any spelling, or any file
at the stage root. The core pack and the content packs come from one local export,
so the split-pack checks of that export stay valid.

## What players' games and updaters do

From release T on, installed games and updaters work like this. The details,
messages and log lines are in
[client updates](client-updates.md#release-discovery-and-freshness).

1. **Pointer first.** The game at start and the updater read the platform's signed
   pointer, `desktop/v1/channels/live/<platform>.json`. They wait at most 15 seconds
   and read at most 64 KiB. The pointer must verify with the release key, and its
   sequence must be at least the installation's high-water mark.
2. **The pointed manifest.** They fetch the immutable manifest copy the pointer
   names. Its size and SHA-256 must be exactly the pointer's, and its commit,
   version and sequence must be the ones the pointer states. A game whose installed
   commit is the pointer's commit, or a descendant of it, stops before this step and
   fetches no manifest.
3. **Fallback.** Any failure falls back to the GitHub `latest` alias, as before T:
   offline, DNS, a challenge page, a 404, a bad, foreign or stale signature, or a
   manifest that differs from its pointer.
4. **Downloads.** Content parts come from `desktop/v1/parts/<sha256>.bin`. The
   `engine` and `native-runtime` packages and the updater come from GitHub. Each part
   gets at most three attempts: at once, after 5 seconds and after 30 seconds. A 404
   or 410 ends the update at once. Every part, package and file is checked against
   the signed SHA-256 rows before anything installed changes.
5. **Freshness.** After installing, the updater records the installed release. It
   refuses an older signed manifest unless a signed rollback pointer names it (see
   [freshness, rollback and downgrade](#freshness-rollback-and-downgrade)).
6. **The server's required release.** When the game server requires a commit that the
   installed game lacks, the game skips the pointer and looks for exactly that
   signed release: first the GitHub alias, then the policy's manifest address.

Fresh installations do not read the pointer, because the player chose a release:

- `<version>-setup.exe` embeds its signed manifest and downloads the same rows, R2
  parts from R2. Inno Setup checks each download's SHA-256, and the embedded setup
  helper checks it again before installing.
- `<version>-download.sh` downloads the updater from GitHub, checks it with
  `sha256sum`, and installs from the manifest it embeds.

Games and updaters before T read only the GitHub alias, and they pin the retired
release key. They cannot verify T or any later release, so they never reach T's
updater; their players run R1's installer once (see
[key rotation](#key-rotation-2026-11)).

## R2 layout

Everything for the desktop lives under `desktop/` in the project's bucket.

| Key | Mutability | Written by | Content |
| --- | --- | --- | --- |
| `desktop/v1/parts/<sha256>.bin` | immutable, content-addressed | `upload_desktop_assets.py content` | one package part (for a one-part package, the whole package ZIP) |
| `desktop/v1/sets/<platform>/<sha256>.json` | immutable | `content`, **last** in an upload | the unsigned content set; `<sha256>` is the hash of its exact bytes |
| `desktop/v1/manifests/<platform>/<sha256>.json` | immutable | `upload_desktop_assets.py publish` | the signed release manifest, byte-identical to `<version>-<platform>.json` on GitHub |
| `desktop/v1/channels/live/<platform>.json` | **mutable** (the only mutable production keys) | `publish`, after the manifest | the signed pointer to the live release |
| `desktop/selftest/<YYYYMMDD>-<8 hex>/...` | immutable, except its test pointer | `selftest` only | test objects that no client reads |

| Object | Content-Type | Cache-Control | Metadata |
| --- | --- | --- | --- |
| part | `application/octet-stream` | `public, max-age=31536000, immutable` | `sha256` |
| set, manifest | `application/json` | `public, max-age=31536000, immutable` | `sha256` |
| pointer | `application/json` | `no-store` | `sha256`, `sequence` |

- **Public URLs.** Players and CI read through
  `https://assets.rabbitlandsgame.com/desktop/v1/`.
- **Edge caching.** `.bin` keys are cached at the Cloudflare edge. The first read
  in a location is a MISS and later reads are HITs, per location. `.json` keys always
  come from the origin, so a new pointer is visible at once. HEAD requests are never
  cached.
- **404s are cached.** A 404 for a cacheable key can stay cached for up to 4 hours.
  That is why nothing reads a part before it exists (rules below).
- **Metadata is bookkeeping.** The metadata and ETags help the uploader resume.
  No client or CI job treats them as integrity.
- **Parts are shared.** Parts are not split by platform: a package that is
  byte-identical on both platforms is stored once. Local part files keep their
  `RabbitLands-pkg-<sha256>.zip.part` names. The R2 key is derived only from the
  hash.
- **Spare levels.** `v1` lets a later, incompatible layout coexist. Only the `live`
  channel exists. The `channels/<name>/` level keeps room for a test channel later.
- **Desktop-only tools.** The desktop tools never touch `browser/`. The browser
  objects are not reused: they are packed differently and share no hashes with
  desktop packages.

### Uploader guard

`upload_desktop_assets.py` is the only desktop tool that writes to R2. It enforces
the following:

- **Key guard.** It refuses, before any request, every key that does not exactly
  match one of the forms above.
- **Operation allowlist.** An SDK-level handler allows only `HeadObject`,
  `GetObject`, `PutObject` and `ListObjectsV2` (under `desktop/` only). There is no
  delete call of any kind.
- **Conditional writes.** Every immutable PUT is a conditional create
  (`If-None-Match: *`). A pointer PUT replaces only the exact live version
  (`If-Match`), or creates the first pointer.
- **No overwrite.** An existing object that differs is a conflict and is never
  overwritten.
- **Sanitized output.** Errors and receipts carry only error codes. They never
  contain the endpoint, account id, key id or secret.

These controls limit the tool, not the credential. The credential itself is
narrowed by the owner (see [one-time setup](#one-time-setup)).

## Trust

```
godot-client/data/update_public.pem (in Git, RSA-4096; replaced at T, see Key rotation)
  pinned in: the core pack (res://data/client_release.json), app/client-release.json,
             the updater's trust file and the setup helper
      |
release signing key: a GitHub environment secret of desktop-sign and desktop-publish only
      |
      +-- sign job (after the owner approves desktop-sign)
      |     release manifest, schema 3: commit, ancestors, platform, version, launch
      |     arguments, sequence, every package {files: path, size, SHA-256, codec;
      |     parts: URL, size, SHA-256}, both helpers, root files, helpers fingerprint,
      |     content source and set hash
      |
      +-- publish job (after the end-to-end tests and the owner's desktop-publish approval)
            pointer: platform, channel, sequence, rollback flag, release id, run id,
            target {commit, version, manifest_sequence, manifest {url, sha256, size}}

R2, Cloudflare, every R2 credential: transport only
```

Signatures are RSA PKCS#1 v1.5 over the SHA-256 of the payload bytes, in the usual
`{"payload": ..., "signature": ...}` envelope.

### Signing

- Signing runs in two small Linux jobs. Each needs an owner-approved environment,
  restores no cache and runs no built code. The private key never reaches the build
  machine.
- The Python signature is byte-identical to the one `sign_client_release.gd` would
  write. Each envelope is verified again by Godot's `verify_client_release.gd`
  before an installer is built.
- **What the executables pin.** They pin the public key, and the R2 base
  `https://assets.rabbitlandsgame.com/desktop/v1/` as a compiled constant. The base
  never comes from a manifest, a set, the server or the environment.
- **Accepted R2 URLs.** Only these derived forms are accepted:
  - `<base>parts/<row sha256>.bin` for parts;
  - `<base>manifests/<platform>/<sha256>.json` for a pointer's manifest;
  - `<base>channels/live/<platform>.json` for discovery.

### Domain separation

- The pointer payload has `kind: "rabbitlands-release-pointer"` and no top-level
  `commit`, `schema`, `bootstrap_schema` or `packages`, so every manifest verifier
  refuses it.
- The pointer's release asset is named `RabbitLands-<platform>-pointer.json`. It
  never matches the name patterns older games search for.
- The content set is never signed and never read by players.

### Checks at install and at load

The install-time checks are unchanged:

1. each part's size and SHA-256;
2. each package's SHA-256;
3. each package's `inventory.json`, which must equal the signed file list;
4. every member, hashed while it is decoded;
5. staged files, hashed again;
6. the identity of the required files (commit, key, distribution);
7. a final re-check at the commit point.

After installation, per-load verification is anchored only in installed files. It
never depends on where the bytes were downloaded from. Moving delivery to R2
weakens neither.

### Content attestation

Content is built on the build machine, so the release needs a way to bind CI to it.

1. **The dispatch names the content.** It names each platform's content set by
   SHA-256.
2. **The `content` job verifies it.** It downloads the set anonymously and
   validates it:
   - the header, the commit, the public key, the paths and the CI-owned paths;
   - no native-code files and no PE, ELF or Mach-O magic bytes;
   - the rules for `.gdextension` and `.godot/extension_list.cfg`.
3. **It cross-checks the identity.** It recomputes the release identity and reads
   the identity embedded in the core pack.
4. **It checks the split pack.** It reads the core pack with `tools/pck_split.py`.
   The core's list of content packs must equal the set's `app/packs/` files, by size
   and SHA-256. Each new content pack may hold only the entries that `pck_split`
   assigns to it and the core does not hold, so no script, identity or extension
   list can ride in a content pack. The local pack makes the same checks.
5. **It checks every new byte.** It downloads and fully decodes every package the
   published release does not already have.
6. **It summarizes the difference.** The job summary lists the differences from the
   live release.
7. **The owner attests.** Approving `desktop-sign` is the owner's statement that
   this content is what they built for that commit.

Set hashes and content summaries appear in the public Actions logs. They reveal
nothing that the public GitHub pools and the readable bucket do not.

**Integrity is cryptographic; provenance is the owner's.**

- The core pack's GDScript is code. A compromised build machine could ship
  malicious scripts in a signed release, as the older local release path always
  could. The hygiene checks above are not containment.
- The packer refuses a dirty or unpublished tools checkout. The set records the
  tools commit, the dirty flag, the editor hash and a digest of the reused import
  cache.
- The `builder` and `qualification` blocks are informational. CI gates on its own
  end-to-end test receipts.

### Freshness, rollback and downgrade

The updater, the game's start check and the setup helper apply these rules from
release T on. The publication rule is in the tools.

- **Sequence.** Every new manifest and pointer carries a signed `sequence`, in UTC
  Unix seconds at signing. A pointer's sequence is always higher than its
  manifest's.
- **Pointer acceptance.** A client accepts a pointer only when its sequence is at
  least the higher of two marks:
  - the highest pointer sequence this installation has accepted, kept in
    `release-pointer.json` in its update cache and only ever raised;
  - the sequence in the installed-release record.

  An older pointer counts as stale, and the client uses the GitHub alias instead. A
  missing or damaged mark counts as none.
- **Installed-release record.** After the commit point, the updater and the setup
  helper write `.rabbitlands-release.json` in the installation folder: the commit,
  platform and sequence, and the manifest's SHA-256 when it is known. A record whose
  commit is not the installed game's is ignored, so a stale record never locks an
  installation out.
- **Downgrade guard.** The updater refuses a manifest whose sequence is lower than
  the installed record's, with "This update is older than the installed game.",
  unless a signed pointer marked `rollback: true` names exactly that manifest.
  - Manifests without a sequence (before T) count as 0. So the GitHub alias alone can
    never roll an R2-aware installation back.
  - The game applies the same rule before it offers an update. A download that an
    earlier game prepared for an older release is dropped, never installed.
  - Discovery is guarded: the pointer, the alias and the server's required release.
    An installer's own embedded manifest is not: setup.exe, download.sh and
    `--install-manifest` install the release the player chose.
- **The rollback flag.** `rollback: true` only admits the one manifest the pointer
  names, even when it is older than the installed release. It has no other effect.
- **Server-target rediscovery.** When the server requires a commit that the
  installed game does not contain, rediscovery skips the pointer and looks for that
  exact signed release: the GitHub alias, then the policy's `manifest_url` (a GitHub
  release download named `<tag>/<name>.json` with plain names only, because the
  address is passed on the updater's command line, or an R2 manifest copy whose
  bytes must hash to its name). A
  frozen or forgotten pointer therefore never locks players out. Rediscovery still
  refuses an older release, respects a player who declined the update, and retries
  at most every five minutes.
- **Publication.** It refuses a pointer whose sequence is not above the live one.
  It also stops when the live pointer's sequence is below the last value in the
  local publish receipt, because R2 was rolled back.

Games and updaters before T are unchanged. They read the GitHub `latest` alias and
compare commit ancestry, and the server enforces its required commit at login.
Since the [key rotation](#key-rotation-2026-11) they cannot verify T or any later
release.

### Who can do what

| Party | Can | Cannot |
| --- | --- | --- |
| A holder of an R2 credential | upload objects; replay or freeze a pointer; delete or overwrite objects outside the bucket's lock rules (the tools never do): denial of service, or delayed optional updates | forge a manifest or pointer; make a player run bytes that are not in a signed row; make an unapproved release live (pointers are signed only after approval) |
| Cloudflare zone, account or DNS administrators | the same as an R2 credential | the same |
| The Cloudflare edge or the network | serve wrong bytes, 404s or challenge pages, all rejected by hash or status | substitute content |
| GitHub accounts with write or Actions access | dispatch the workflows; add assets to pools and drafts; edit or delete releases and assets, including which release is GitHub `latest`: denial of service, or an older signed release for updaters without the downgrade guard | sign anything without the owner approving `desktop-sign` or `desktop-publish`; read the key from another branch |
| The owner, approving environments | sign and publish | - |
| The build machine | choose the content bytes, attested by the owner at `desktop-sign` | change the CI-built executables or helpers |

One residual stays with the owner. An approval signs whatever workflow file the
approved run uses, so approve only runs you dispatched yourself, on commits you
authorized, from a protected branch.

## Publication order

1. **No GET before a key exists.** A part is never read publicly before a HEAD has
   returned 200 with the right length.
2. **The set goes last.** A set is uploaded only after all its parts are verified.
3. **CI only after the set.** The workflow is dispatched only after the set exists.
4. **Manifest before pointer.** The R2 manifest copy is written before the pointer
   that names it.
5. **Forward releases: R2 first, then GitHub.** The R2 manifest and pointer go live
   before GitHub `latest` flips. **Rollbacks: GitHub first, then R2.** The rule is
   that the side the destination release's updater reads is updated first.
6. **The server policy last.** The server's `required_commit` changes last, after
   `check-policy` confirms that both live pointers and GitHub `latest` name that
   commit.
7. **Fresh self-test prefixes.** The self-test always uses a new prefix.

**Two go-live moments.** The local R2 publish is the moment R2-aware installations
are offered a release. The `desktop-promote` approval (GitHub `latest`) is the
moment new downloads from the latest-release page are, and R2-aware installations
that fall back to the alias. Installations from before T cannot verify any new
release (see [key rotation](#key-rotation-2026-11)).

## One-time setup

The owner does all of these; agents do none of them.

### GitHub

1. Create the environments `desktop-sign`, `desktop-publish` and `desktop-promote`.
   - Required reviewer: the owner's account.
   - Deployment branches: `master` and `develop`.
   - Leave "prevent self-review" off while the owner is the only reviewer;
     otherwise the owner could not approve their own dispatch.
2. Store `CLIENT_UPDATE_SIGNING_KEY` as an environment secret of `desktop-sign`
   and `desktop-publish`. Since the [key rotation](#key-rotation-2026-11) this is
   the new key, the private half of the committed `update_public.pem`. Then
   **delete the repository secret**. This also stops
   `desktop-release.yml` from signing, which is intended.
3. Protect `master` and `develop`: no force pushes, and restricted pushers.
4. **Disable "Retire previous published client"**
   (`published-client-cleanup.yml`) in the Actions UI, and confirm that it shows as
   disabled.
   - It is a no-op on current branches. However, a release event runs the workflow
     file of the released tag, and older tags carry the old pruner.
5. Promote the commit that adds `desktop-release-r2.yml` to `master`. GitHub
   dispatches only workflows on the default branch. That push starts nothing,
   because every workflow in the repository is dispatch-only.
6. Run a **dry run** (see [runner builds](runner-builds.md#dry-run)). It checks
   the toolchains, runner disk and permissions before any signing. An `r2` dry run
   needs a content set already uploaded for the commit, so before the first content
   upload the dry run uses `ci` sources.
7. **Before T's build, publish the helper template** (see
   [the helper template](#the-helper-template)). Without the published template,
   the Windows `build` job stops with `helper-template`, because T must export a
   new helper. A template change after T costs every player another helper
   download.

### Cloudflare and R2

1. **No challenges for `/desktop/*`.** Bot Fight Mode, Browser Integrity Check and
   WAF or managed challenges must not challenge `/desktop/*` for non-browser
   clients: the game's `RabbitLands-Client` agent, Inno Setup, curl and GitHub
   runner addresses.
2. **Optional cache rule.** A Bypass cache rule for `/desktop/v1/channels/*`.
3. **A separate desktop R2 API token.** Scope it to this bucket and keep it
   separately revocable from the browser upload key. Store its private
   configuration file outside every repository and worktree.
4. **Bucket lock rules, where available.** Add them for `desktop/v1/parts/`,
   `desktop/v1/sets/` and `desktop/v1/manifests/`, **never** for `channels/`.

### The build machine

1. Install the hash-locked upload dependencies into a stable folder outside every
   repository and worktree:

   ```
   python -m pip install --require-hashes --no-deps --target <dependency folder> -r godot-client/tools/desktop-r2-requirements.txt
   ```

   Put that folder on `PYTHONPATH` when you run `upload_desktop_assets.py`.
2. Prepare a native Linux build environment for Linux content. The prepared-world
   cook needs the native platform and Mesa lavapipe.
   - This can be WSL, with the checkout on the Linux file system rather than a
     Windows drive.
   - Use a Linux Godot 4.7.2 editor taken from the download whose hash
     `setup_runner_tools.py` pins. An editor whose download was not kept cannot be
     verified, so fetch the pinned download again first.
   - Plan about 40-50 GB, because of the import cache, the stage, the parts and the
     caches.
   - Without it, Linux uses the `ci` source.

## Release build window

In `r2` mode every release needs one full Windows build and one full Linux build on
the build machine, including a one-line fix. Plan a **release build window** for
them:

- **Prerequisites.** Commit X is approved and already on `origin`. The branch you
  will dispatch on (`master` or `develop`) has X as its head.
- **Freeze that branch** until the dispatch. The workflow runs at the branch head,
  and the `content` job refuses a set built for any other commit.
- **No other heavy work.** Run no other Godot, GPU or long CPU jobs. The packager
  starts Godot directly and does not coordinate with other jobs.
- **Keep the machine awake.** It must not sleep for the whole window.
- **A clean checkout.** Build from a checkout or worktree that is clean, whose HEAD
  is on `origin` and contains X, and that nothing else writes to during the window.
  The packer refuses a dirty or unpublished tools tree.
- **Outputs outside every checkout.** Pass explicit `--build-dir` and `--out`
  folders outside every checkout. Keep upload plans and receipts outside every
  worktree too, or in ignored folders; the tools refuse other locations.
- **Disk.** Parts take about 4-4.6 GB per platform. They can be released after a
  verified upload.

The window ends when both content uploads are verified. The rest runs in Actions,
apart from the short local R2 publish.

**Measured Windows timings** (the first real local build and pack, 2026-11-05; Linux
is not measured yet):

| Step | Time |
| --- | --- |
| Stage build, warm build folder (native cache hit, warm VRAM cache, cold world cook) | about 36 min, of which the world cook is 15.5 min until its cache is warm |
| First import in a fresh build folder (two passes) | about 17 min, plus about 2 min of checkout and 3 min of native build |
| Whole cold build in a fresh folder | about 65-80 min |
| `desktop_content.py pack` (676 packages, 685 parts, 4.23 GB) | about 5 min |
| First full upload at the self-test's 11 MB/s | about 6.5 min |

- **Disk.** The build root (build folder with its import cache, stage, local parts
  and caches) peaked at about 24 GB.
- **One build folder per release.** A second full-optimization build in a
  `--build-dir` that an earlier one used currently stops on the leftover
  `bin/client_runtime` payload. Pass a fresh `--build-dir` for each release, or
  delete that build folder's ignored `godot-client/bin/client_runtime/` first (the
  native cache supplies it again and keeps the warm import).
- **Local and CI bytes.** Local deflate archives reproduce CI's bytes for the same
  files. BC7 VRAM sidecars encoded on the build machine differ slightly from the
  CI runner's (the other sidecar formats match), so the first R2 release
  re-downloads about 0.8 GB of texture packages once, unless it rides with a
  re-encode that changes them anyway. Later local builds stay stable through the
  persistent VRAM cache.

## Releasing: the forward runbook

All commands run from the repository root of the clean checkout. Every
`<placeholder>` is a folder or file outside every checkout.
`<private R2 credential file>` is the owner's private configuration; pass it only
as a path, and never print, copy or commit it.

1. **Build the Windows stage** (natively, on Windows):

   ```
   python godot-client/tools/package_client.py --platform windows --ref <X> --no-fetch --distribution github --no-client-updates --release-build --full-optimizations --prepared-world --no-zip --build-dir <build-dir> --out <out>
   ```

   - This runs the full qualification: imports, VRAM, the prepared-world cook, the
     split-pack proof, the static and native checks, both startup smokes, and the
     final package check.
   - `--no-client-updates` builds no updater and signs nothing, so no key is
     needed.
2. **Build the Linux stage** the same way, with `--platform linux`, in the native
   Linux environment. If Linux is not built locally, use `linux_source: ci` in step 6.
3. **Pack and upload Windows.** Pack the stage into a content set and an upload
   plan, then upload it:

   ```
   python godot-client/tools/desktop_content.py pack --stage <stage> --platform windows --out <pack-windows> --previous live --probe s3 --credentials <private R2 credential file> --build-dir <build-dir> --godot <editor>
   python godot-client/tools/upload_desktop_assets.py content --plan <pack-windows>/upload-plan.json --credentials <private R2 credential file> --receipt <receipts>/content-windows.json
   ```

   - **`--previous`.** `live` takes the previous release from the live signed
     pointer and its verified manifest. Use `none` when no pointer exists yet.
     Packages whose files are unchanged are reused without re-zipping, once their
     parts answer a HEAD on R2.
   - **The output folder** must be on the stage's volume.
   - **Output.** Pack prints the set SHA-256 and the exact dispatch inputs. A rerun
     on the same inputs gives byte-identical set bytes.
   - **Reruns resume.** An upload rerun skips objects that are already complete. A
     differing existing object is refused and listed in the receipt.
   - **`--workers`.** The default is 4. Add `--workers 1` or `--workers 2` on the
     build machine's connection: with 4 workers, a full upload failed 34 of its 685
     parts. A rerun uploads only what failed.
   - **`--release-local-parts`.** After a verified upload, this deletes the local
     part files. It deletes local files only.
4. **Pack and upload Linux**, after the Windows upload is complete.
   - **Pack** in the Linux environment with the same `pack` command, using
     `--platform linux`, `--probe public` instead of `--probe s3 --credentials`, and
     `--reuse-set <pack-windows>/set.json`. The public probe needs no credential, so
     the credential never enters WSL. Packages identical on both platforms are
     reused, because their parts are already on R2.
   - **Upload** from Windows with the same `content` command, passing the Linux plan
     through the WSL network share (`\\wsl.localhost\<distro>\...`) and a receipt
     of its own, such as `<receipts>/content-linux.json`.
   - **Drift check (optional).** `desktop_content.py compare` reports installed-file
     differences against a release (`--manifest live`, `github-latest` or a file).
   - **Independent check (optional, anonymous):**
     `upload_desktop_assets.py verify-public --platform <p> --set-sha256 <S> --sample 50`.
5. **Release the build window.**
6. **Dispatch** Actions -> **Build desktop release (R2 content)** on the branch whose
   head is X.
   - `windows_source` and `linux_source`: `r2` or `ci`.
   - `windows_set_sha256` and `linux_set_sha256`: the printed hashes for `r2`;
     empty for `ci`.
   - `dry_run`: off.
7. **Approval 1: `desktop-sign`.**
   - Before approving, read each `Content <platform>` job summary: added, changed
     and removed packages; whether the core `client` package changed; new file
     extensions; new bytes; and the builder block.
   - Check that each set hash is the one pack printed.
   - Read each `Executables <platform>` job summary: `helpers_reused` and the previous
     release's commit. For R1 it must say `true` and T's commit, unless the updater
     inputs changed on purpose. While GitHub `latest` is the pre-rotation `945042f0`,
     only the live pointer leads to T, and a failed read exports a new helper instead
     of failing the job. Find out why before approving: a new export may differ in
     bytes, and then every installation of T takes a handover.
   - Approve only if this is the content you built for X.
8. **Approval 2: `desktop-publish`.**
   - Wait for both `End-to-end` jobs and `Finalize the draft` to pass.
   - Approving signs both pointers and publishes the release as **not latest**.
     `/releases/latest` keeps naming the current `latest` (for R1, the pre-rotation
     `945042f0`), so older games and updaters see nothing yet.
   - The job summary prints the next command.
9. **Local R2 publish:**

   ```
   python godot-client/tools/upload_desktop_assets.py publish --release client-<X> --platform windows --platform linux --credentials <private R2 credential file> --receipt <receipts>/publish.json
   ```

   - **Always pass the same `--receipt` path.** It keeps the last pointer sequence
     per platform, which is how the tool notices that R2 was rolled back.
   - **What it checks.** It reads the release anonymously and verifies both
     signatures with the committed public key. It checks that the release is not
     yet `latest`, and that the current `latest` is an ancestor. It HEADs every row
     the manifest names. Then it writes the manifest copy, and the pointer through a
     conditional write.
   - **Read-back.** It reads both back anonymously through the custom domain.
   - **Failure.** Every platform is checked before anything is written, and a
     failure before a platform's pointer write leaves that platform's previous
     pointer live. Once a pointer is written it stays live: a later failure (its
     read-back, or the other platform) can leave one platform on X and the other
     on the previous release. Run the same command again; it treats a pointer
     that is already live as done.
10. **Local pre-promote setup check, only when required.** The `Finalize the draft`
    summary asks for it when the Windows runner had too little disk for the
    setup.exe test. Install `<version>-setup.exe` from the release into a new
    temporary folder. It must finish, and the game must start. For T, the
    post-publish check always includes this install.
11. **Post-publish check** (see [below](#post-publish-check)). At this point only
    the R2 pointer names X, so the check proves pointer discovery.
12. **Approval 3: `desktop-promote`.**
    - CI reads both live pointers anonymously through the custom domain. They must
      be byte-equal to the release's pointer assets and verify, and the manifest
      copies they name must be live.
    - CI then flips GitHub `latest`, confirms it, and prunes outside the retained
      set (see [rollback](#rollback-runbook)).
    - The job summary prints the next command.
13. **Server policy:**

    ```
    python godot-client/tools/upload_desktop_assets.py check-policy --policy <client_updates.json>
    ```

    - Take `client_updates.json` from the run's `release-verification` artifact,
      which is kept for 30 days. Keep a private copy for every release, because a
      rollback needs the target's.
    - The command passes only when both live pointers and GitHub `latest` name the
      policy's `required_commit`.
    - Keep the policy's manifest URLs as finalize wrote them: GitHub commit-tag
      downloads, which every client reads. R2-aware games also accept the R2
      manifest copy there; older games accept only GitHub addresses.
    - Then copy the policy to the served server profile. That is a separate, manual
      server deployment.

### Approvals and owner decisions per release

The workflow asks for exactly three environment approvals, each guarding its own
step:

| Approval | After | Means |
| --- | --- | --- |
| `desktop-sign` | the content summaries | "This is the content I built for X." Both manifests are signed |
| `desktop-publish` | e2e and finalize | the tested release is published as not latest, with signed pointers |
| `desktop-promote` | the local R2 publish and the post-publish check (and the local setup check, when required) | GitHub `latest` moves, then pruning |

The owner also decides each of these, every release:

- the content uploads;
- the dispatch, with its set hashes;
- the local R2 publish;
- the server policy, after `check-policy`.

Each approval covers one run. Saved notes and earlier approvals authorize nothing
new.

### Reruns and refusals

| Message or state | Meaning | Action |
| --- | --- | --- |
| `content`: incomplete, with failures in the receipt | some objects did not finish | run the same command again; it resumes |
| `content`: `conflict` | a different object already holds that key | stop and investigate; never overwrite or delete it |
| prepare or finalize: "Another client draft exists (client-<Y>)" | an earlier real run stopped after prepare and left its draft, for example after a failed job | delete that draft (`gh release delete client-<Y> --repo rabbitlandsgame/rabbitlands-client --yes`), then dispatch again. Its pool parts stay, and the new run reuses the unchanged ones |
| `content` job refuses the set | wrong commit (the branch moved), platform, key, URL form, CI path, or native code | fix the cause; if the branch moved, build and upload content for its new head, then dispatch again |
| `publish` (local): `pointer-stale` | the signed pointer is not newer than the live one, for example after a repoint | re-run the workflow's publish job, which signs fresh pointers, then run the local publish again |
| `publish` (local): `live-pointer-unverifiable` or `live-pointer-rolled-back` | the live pointer is not ours, or is older than the receipt | stop and report. R2-aware clients that refuse the live pointer use the GitHub alias meanwhile. Recovery is an owner decision; the tool has no override |
| `publish` (local): `release-already-latest` | GitHub `latest` already names the release | a forward pointer cannot follow GitHub. Realign through the repoint workflow (see the [emergency path](#when-r2-is-down-the-ci-emergency-path)) |
| promote: "Run the local publish for client-<X> first; GitHub latest is unchanged." | the live pointers are not this release's | run the local publish, then re-run the promote job |
| promote: "is GitHub latest; retiring releases outside the retained set failed" | the flip succeeded and pruning did not | re-run the promote job: it skips the flip and prunes again |
| publish job: "GitHub latest changed during publication" | GitHub moved `latest` despite `--latest=false` | mark the previous release latest again with `gh release edit <tag> --latest` before anything else |

## Post-publish check

Use a test installation of the previous release, never your normal game folder.
From R1 on, that installation's updater is R2-aware. T is checked from a fresh
installation instead ([below](#the-check-for-t)), and R1 adds a setup check over a
pre-rotation installation ([below](#the-check-for-r1)).

1. Run the installed updater once with `-- --update-only` (from its folder, or with
   `-- --root <folder>`), and keep its log by passing `--log-file <file>` before the
   `--`. It must install release X: `app/client-release.json` must name X
   afterwards, and the log must contain
   `Release discovery: R2 pointer <sequence>, commit <first 9 hex digits of X>`.
   When X changes the updater, this line comes before the handover, and the new
   updater discovers X again.
2. Run it again. It must download nothing; the log says
   `0 of N packages needed downloads`.
3. Start the game once. It must reach the login screen without an update prompt.

The other discovery lines say why the pointer was not used, for example
`Release discovery: the R2 pointer was not used (<reason>)` followed by
`Release discovery: GitHub alias, commit <...>`. Before promote, the alias still names
the current `latest`, so a run that took that path installs nothing. For R1 that is
the pre-rotation `945042f0`, which a T installation cannot verify, so the run stops
with "The release signature could not be verified."

Run the check after the local R2 publish and before approving `desktop-promote`. At
that point GitHub `latest` has not moved, so success can only come through the
pointer.

### The check for T

No installation from before T can update to T: they all pin the retired key (see
[key rotation](#key-rotation-2026-11)). Check T from a fresh installation, still
after the local R2 publish and before approving `desktop-promote`:

1. Install T's `<version>-setup.exe` from the release into a new temporary folder.
   It must finish, and `app/client-release.json` must name T.
2. Re-check the pointer: run the installed updater once with `-- --update-only` and
   `--log-file <file>`. The log must contain
   `Release discovery: R2 pointer <sequence>, commit <first 9 hex digits of T>` and
   `0 of N packages needed downloads`. GitHub `latest` still names a pre-rotation
   release, which T cannot verify, so only the pointer can give this result.
3. Start the game once. It must reach the login screen without an update prompt.

T's setup.exe cannot pass over an old installation: it exits 7 and leaves the folder
as it was, because its helper refuses the retired key. That is why T stays not latest,
and why that check belongs to R1 ([below](#the-check-for-r1)).

Check on a machine with a normal installation with care. Setup keeps one uninstall
entry and one Start Menu group per machine and ignores `/GROUP`, so a test setup
retargets the normal installation's shortcuts and uninstall entry to the test folder,
even when `/DIR` is correct. Export the uninstall key and copy the Start Menu group
first, and restore both after each setup. Remove the key while the test setup runs, so
setup cannot pick the normal folder as the previous installation. Give every test
installation its own `APPDATA` and `LOCALAPPDATA`.

Keep the fresh installation as the test installation for R1. An old installation's
explicit updater run stops with "The release signature could not be verified."
and changes nothing; that is expected, not a failure.

### The check for R1

R1's setup.exe is what returning Windows players run, and no automated test installs
a real release over a real pre-rotation folder. A full-size local replay proved the
conversion with T's GitHub rows; what this check adds first is a full-size setup with
R2 part URLs. Run this check as well as the post-publish check from T's test
installation, after the local R2 publish and before approving `desktop-promote`:

1. Follow [the care above for a machine with a normal installation](#the-check-for-t):
   back up and park the uninstall key, and restore the Start Menu group after every
   setup and uninstaller. Install `945042f0` into a test folder and start that old game
   once under a test `APPDATA` and `LOCALAPPDATA`. A game that nobody logged in to
   writes no settings file, so copy a played user folder into that `APPDATA` first and
   record the SHA-256 of its `eloria_hud.cfg`.
2. Run R1's `<version>-setup.exe` over that folder under the **same** `APPDATA` and
   `LOCALAPPDATA`, so the old game's settings and update cache are there. This is the
   one exception to "its own `APPDATA`" above: the old game and the setup share one.
3. Do this twice, from two copies of the folder: once with `.eloria-previous` in it
   and once without. Field installations that ever updated hold that whole second copy
   of the game, because no release before T removes it. A new `945042f0` holds only an
   empty `.eloria-previous`, so copy `app/` and `eloria-assets/` into it for this case.
4. Each time, setup must finish, `app/client-release.json` must name R1,
   `.eloria-previous` must be gone, and the game must reach the login screen with the
   hash of `eloria_hud.cfg` unchanged.

The order for R1, each step on the owner's approval:

1. Replay the fixed setup helper over a copy of an old installation, with an unfixed
   helper as the control, before any dispatch.
2. Reject T's waiting promote.
3. Push R1's commit to `develop`. The workflow accepts only the head of `develop` or
   `master`.
4. Run an `r2` dry run once R1's content set exists, then dispatch R1. Read
   `helpers_reused` before approving `desktop-sign`.
5. Run the post-publish check and this check.
6. Promote only after both checks pass.
7. Right after promote, update the public wiki pages `Access-and-Installation` and
   `Updates-and-Recovery`. Their text is true only once the release is `latest`. The
   wiki serves `master`, and a checkout on `develop` pushes with
   `git push origin develop:master`.
8. Set `enforce` only after promote, and fix the server's login message first. It
   tells a refused client to wait for a download that an old installation never
   starts, and it links a manifest JSON file instead of the release page.

### If the check fails

**Do not approve `desktop-promote`.** R2-aware installations are already being
offered X. If X itself is at fault:

1. Reject the pending promote. A run waiting for approval holds the release
   concurrency group, so a repoint would queue behind it.
2. From the release after R1 on, repoint the channel to the previous release, which
   is still GitHub `latest` (see [rollback](#rollback-runbook)).
3. For T and R1, fix forward with a new release. T has no release to repoint to. R1's
   previous release is T, which is not `latest`, so a repoint would also make T GitHub
   `latest` and put its refusing setup.exe on the latest page. Only fresh installations
   of T read the pointer at this stage, so a fix forward costs little. A repoint to T
   is an owner decision.

Installations that took X in the meantime keep it (see
[what a rollback moves](#rollback-runbook)). Ship the fix as a new commit. A
published commit is never released twice.

## Rollback runbook

**Rules:**

- **Only one GitHub move.** A rollback only makes a **retained, still-published**
  release GitHub `latest` again, with `gh release edit client-<target> --latest`.
  The repoint workflow does this for you. It is an `edited` event, which starts no
  workflow.
- **Never touch old tags.** Never recreate, re-publish, re-tag or return to draft
  an old `client-<sha>` release. Publishing an old tag runs that tag's own copy of
  the cleanup workflow, with the old pruner. The old pruner deletes every newer
  release and every pool asset outside its own inventory.
- **Never delete by hand.** Never delete releases, release assets or pool assets by
  hand, and never write or delete R2 objects outside the tools. The one exception is
  the never-published draft of a stopped run (see
  [reruns and refusals](#reruns-and-refusals)).

### What is retained

Pruning runs only in `desktop-promote`. It keeps whole releases, with every pool
asset their manifests reference, helpers included:

- GitHub `latest`;
- every published release newer than `latest` (for example, one waiting for promote,
  or one rolled back from);
- the two most recently published releases before `latest`;
- the pinned last GitHub-hosted release, normally T. The pin is set in the R1
  commit. Until a commit sets it, the R2 workflow refuses a release with `r2`
  content (a dry run excepted).

A release whose publication time cannot be read is also kept. Nothing on R2 is ever
deleted. A later, owner-approved cleanup would use the retained releases'
`R2-SHA256SUMS` files as its reference set.

### Steps

1. **Choose the target.** It must be a retained, published release whose manifests
   are schema 3 and signed with the current key, so T or later. A repoint to T also
   makes T GitHub `latest`, even though it never was, and T's setup.exe refuses every
   folder from before the rotation. Returning players then meet that setup on the
   latest page until a fix ships, so weigh that against fixing forward.
2. **Reject any waiting run.** If a release run is waiting for an approval, reject
   or cancel it first.
3. **Dispatch the repoint workflow.** Run Actions -> **Repoint the desktop live
   channel (rollback)** from `master` or `develop`, with `target_commit` (40 hex)
   and `platforms` (`both`, `windows` or `linux`).
   - Its `check` job needs no approval. It verifies that the target is published by
     the project account or its workflow, and that its tag points at the commit.
   - It also checks that each selected platform's manifest verifies with the
     dispatched commit's key and is schema 3, and that every download the manifest
     names still answers with its exact length.
4. **Approve `desktop-publish`** for the `repoint` job. The job does the following:
   1. It checks again.
   2. It signs one rollback pointer per platform, with a higher sequence and
      `rollback: true`. Signing comes before any write, so a missing key stops the
      job before GitHub changes.
   3. It makes the target GitHub `latest` (**GitHub first**) and confirms it.
   4. It uploads the pointers as the target release's pointer assets, replacing
      the ones there, confirms them, and prints the local command.
5. **Put the rollback pointers live on R2** with the command the job printed, and
   the same `--receipt` path as every publish. For both platforms it is:

   ```
   python godot-client/tools/upload_desktop_assets.py publish --release client-<target> --platform windows --platform linux --rollback --credentials <private R2 credential file> --receipt <receipts>/publish.json
   ```

   Pass only the platforms you repointed. The tool requires the target to be
   GitHub `latest` already.
6. **Run the post-publish check** from an installation of the release you rolled
   back from. It must land on the target, and its log must contain
   `Release discovery: R2 pointer <sequence> (rollback), commit <target>`, with the
   first 9 hex digits of the target. The downgrade guard admits the target only
   through the rollback pointer.
7. **Set the server policy.** Write a policy whose `required_commit` is the target,
   for example that release's own `client_updates.json`. Run `check-policy`, then
   deploy the policy.
   - If the server keeps requiring the newer commit, rolled-back players are sent
     straight back to it.

**What a rollback moves.** It changes what new installations, installations older
than the target, and explicit updater runs receive. It does not take X away from
installations that already have it:

- the game offers only a release that has the installed commit among its ancestors,
  and a pointer naming an ancestor of the installed commit counts as current;
- the server accepts every descendant of its required commit.

Such an installation moves to the target only when the player runs the updater
explicitly (`-- --update-only` or `-- --install-update`), which follows the rollback
pointer, or with the next forward release. If X harms the players who already have
it, ship the fix as a new release.

**Rolling back to a release before T is impossible.** Those releases are signed
with the key retired at T (see [key rotation](#key-rotation-2026-11)), which no
installation from T on trusts. Pointers also name only schema-3 manifests, and the
downgrade guard refuses older manifests reached through the alias. Roll forward
instead: revert the change and ship a new release. A rollback from R1 lands on T,
which is R2-aware, but whose setup.exe refuses old folders (see step 1 above).

## The `ci` content source

The source is chosen per platform. With `ci`, the platform's content is built on a
GitHub runner from the dispatched commit, the way the earlier full-CI workflow built
it, and its parts go to the GitHub pools. Everything afterwards is identical:
signing, installers, e2e, publish and promote. Pointers and R2 manifest copies are
published either way. A release may mix sources, for example Windows `r2` with
Linux `ci`.

Uses:

- **the helper-train release T** (both platforms);
- **a Linux fallback** while Linux content is not built locally;
- **an R2 outage** (below).

The runner content build restores its import, graphics and world caches by exact key
only. Its trust level is that of the earlier hosted workflow. A `ci` release
downloads from GitHub only, so R2 is needed only to make its pointer live. See
[runner builds](runner-builds.md#the-ci-content-leg).

### When R2 is down: the `ci` emergency path

**What an outage looks like.** Anonymous reads under
`https://assets.rabbitlandsgame.com/desktop/v1/` fail with 5xx errors, timeouts or
challenge pages.

**What players see:**

- Installed games keep running.
- R2-aware games and updaters wait up to 15 seconds for the pointer, then fall back
  to the GitHub alias for discovery. They cannot download the R2 parts of an R2-era
  release: after three attempts per part the update stops, nothing is installed,
  and verified parts stay cached for the next try.
- Setup programs of R2-era releases cannot install. Setup stops at the failed
  download, before its helper runs.

**When a release must ship anyway** (this path follows the tools but has never been
exercised):

1. **Dispatch** Build desktop release (R2 content) at the fix commit with
   `windows_source: ci`, `linux_source: ci` and empty set hashes. Each platform's
   `Content <platform> (ci)` job builds the content on its runner and uploads the
   parts to the GitHub pools. No workflow job before promote needs R2.
2. **Approve `desktop-sign` and `desktop-publish`** as usual. The content summary
   compares the CI-built content with the live release. The release is published
   as not latest, with its pointers.
3. **If R2 is back by now**, continue with the local R2 publish, the post-publish
   check and `desktop-promote`, as for any release.
4. **If R2 is still down and the release cannot wait:**
   - **Promote refuses.** `desktop-promote` refuses while the live pointers are
     unreadable. Reject the pending promote.
   - **Flip `latest` yourself.** With GitHub CLI signed in as the project account,
     run
     `gh release edit client-<X> --repo rabbitlandsgame/rabbitlands-client --latest`.
     This is the same single move a rollback makes, on a retained, published
     release.
   - **Effect.** R2-aware games and updaters cannot read the pointer, fall back to
     the alias, and accept X because its signed sequence is newer than what they
     have installed. Every download of X is on GitHub, and its setup programs work.
     Games from before T cannot verify X (see [key rotation](#key-rotation-2026-11)).
   - **Nothing is pruned**, because pruning runs only in promote.
   - **No `check-policy`.** It cannot pass while R2 is down. Leave the server's
     required commit unchanged unless the owner decides to raise it without that
     gate.
5. **When R2 recovers, realign the channel.** The live pointer still names the
   earlier release. R2-aware installations still on that release see a valid
   pointer naming their own commit, and are not offered X.
   1. Dispatch the repoint workflow with `target_commit` set to X. GitHub `latest`
      already names X, so the job only signs and uploads new pointers.
   2. Run the local `publish --release client-<X> ... --rollback`.
   3. Run the post-publish check.
   4. Run `check-policy`, then deploy the server policy.

   The next normal release would also realign the channel.

**The build machine is also a dependency.** The local R2 publish needs the R2
credential, which only the build machine holds. Without it, R2-aware installations
keep following the live pointer. They reach a GitHub-only release only after the
pointer is realigned, or when the server's required commit sends them to
rediscovery.

## The helper template

The updater and uninstaller are one small Godot program. From T on it is exported
from its own export template, built from the official Godot 4.7.2 source without
3D, 2D physics and navigation, Vulkan, D3D12 and every module the helper does not
use. Only the `gdscript`, `mbedtls`, `freetype`, `text_server_adv` and `svg`
modules remain, plus `astcenc` on Windows for ANGLE. The game keeps the official
template.

On Windows the template links the same two libraries as the official one, from
Godot's own prebuilt archives:

- **ANGLE** (OpenGL ES over Direct3D 11). The helper opens its window where native
  OpenGL 3.3 is missing (basic RDP and virtual-machine displays, very old GPUs),
  on Windows on ARM, and on the drivers Godot always sends to ANGLE.
  `--rendering-driver opengl3_angle` selects it. ANGLE's static library calls
  Godot's `astcenc` module, so the Windows build also enables that module (it adds
  no engine class).
- **AccessKit** (screen readers through UI Automation). A screen reader can read
  the helper's progress text and the uninstall dialog.

| Windows helper | Template | Helper |
| --- | ---: | ---: |
| Official template (before T, and the fallback) | 109,268,480 B | 111,372,248 B |
| Helper template (with ANGLE and AccessKit) | 41,797,632 B | 43,900,824 B |

`godot-client/tools/helper_template.json` is the recipe. It holds:

- the Godot tag and commit;
- the SCons arguments;
- the toolchain pins: MSYS2 MinGW GCC 16.2.0 package versions, compiler file
  hashes, and SCons under the python.org CPython 3.13;
- the dependency archives for Windows: ANGLE `chromium/7219` (x86_64, MinGW GCC)
  and AccessKit `0.22.3`, each with the URL that Godot's
  `misc/scripts/install_angle.py` or `install_accesskit.py` uses at the tag, its
  size and its SHA-256 (equal to the digest GitHub publishes for the asset);
- for each platform, the pinned template's file name, size and SHA-256;
- `select`, which says whether the helper uses that template (`custom`) or the
  official one (`official`).

`helper_template_classes.json` lists the 491 engine classes the template lacks. It
was measured by comparing `ClassDB.get_class_list()` in both templates.
`test_helper_template.py` fails if a helper script or scene uses one of them.

### How releases use it

- The helper fingerprint takes the **pinned** template SHA-256, not a file. When
  the helper's inputs are unchanged, a release reuses the previous helper without
  fetching anything. That is how R1 reuses T's helper.
- When the helper must be exported, `desktop_release_ci.executables` downloads the
  template from the pinned URL into its work folder. It uses no cache, and it
  refuses the file unless its size and SHA-256 match the pin. Local and
  `desktop-release.yml` builds (`export_into`) fetch it into the ignored
  `.local/helper-template/` folder instead.
- The pinned URL is an asset of the GitHub release `helper-template-4.7.2-rl1` in
  this repository. Its tag is never a `client-*` or `client-assets*` tag, so
  pruning never touches it. No workflow builds or caches the template.
- **Freeze rule for R1:** R1 reuses T's helper only if these are unchanged since
  T: the eight `src/updates` helper scripts, the branding, the trust fields,
  `desktop_helpers.py`'s project, preset and `TOOL_VERSION`, the editor and
  `helper_template.json`'s selected pin. The setup helper
  `tools/install_client_payload.gd` is not among them. R1's job finds T through the
  live pointer, because T is not GitHub `latest`.

### Publishing the template (owner, once per pin, before T)

Download the two dependency archives from the URLs in the recipe, each into its
own new folder outside the repositories. Then build twice and check the result. A
pin is accepted only when both fresh trees give identical bytes:

```
python godot-client/tools/helper_template.py build --platform windows --source https://github.com/godotengine/godot.git --work <new folder outside the repositories> --scons-wheel <scons-4.10.1-py3-none-any.whl> --msys2 <MSYS2 root> --dependency angle=<godot-angle-static-x86_64-gcc-release.zip> --dependency accesskit=<accesskit-c-0.22.3.zip> --twice
python godot-client/tools/helper_template.py verify --platform windows --file <work>/a/rabbitlands-helper-template-4.7.2-windows-x86_64.exe
```

- The SCons wheel is the one whose SHA-256 the recipe pins.
- The build refuses other MSYS2 package versions, other compiler files, and a
  Python whose path separator is not `\`. MSYS2's own Python writes `/` into
  `__FILE__` and gives other bytes.
- Before anything else, the build refuses a dependency archive whose size or
  SHA-256 differs from the recipe. Each tree unpacks the archives into its own
  work folder and gives SCons those folders, so the recipe never names a path.
- The build refuses a result in which SCons dropped a library, or whose imports
  lack `dxgi.dll` (ANGLE) or `uiautomationcore.dll` (AccessKit). It also refuses a
  result that holds the work folder, an archive folder or the home folder.
- AccessKit's Rust library carries its publisher's own build paths
  (`/home/runner/.cargo/registry/...`, `/rustc/<hash>`). The official template
  carries the same strings.

Then upload the verified file as a **prerelease that is never marked latest**.
Old games discover updates through `releases/latest`, so a latest template
release would hide the game:

```
gh release create helper-template-4.7.2-rl1 --repo rabbitlandsgame/rabbitlands-client --target master --prerelease --latest=false --title "Updater helper template (Godot 4.7.2, rl1)" --notes "Pinned in godot-client/tools/helper_template.json." <file>
```

- Create it after `master` carries the no-op `published-client-cleanup.yml`
  (one-time setup step 5).
- Never delete or replace the asset. A new pin needs a new `rl<n>` tag and a
  commit that changes the recipe.

### Fallback and open decisions

- **Fallback:** set a platform's `select` to `official` and commit. The fingerprint
  then takes the official template's pin, and the next release ships an
  official-template helper, which players download once.
- **Linux** stays on the official template. A build on Ubuntu 24.04 needs glibc
  2.38, while the official template needs 2.28. It would fail to start on Ubuntu
  22.04 and Debian 12. The custom Linux template is pinned but blocked until it is
  built with a glibc 2.28 toolchain.
- **ANGLE and AccessKit stay linked.** Every Windows shortcut starts the helper
  first, including **Safe mode** and **Compatibility**, and so does every updater
  handover. A template without ANGLE could not open its window where
  native OpenGL 3.3 is missing, so those players could neither update nor start
  the game from a shortcut. Removing either library is a new pin, and after T it
  is another helper download for every player.
- **Before the release exists**, local exports of this tree's helper (for example
  the exported-updater tests) need the verified file in `.local/helper-template/`:
  copy the built file there, or run `helper_template.py fetch` once it is
  published. Older revisions are exported with the official template, as the
  field built them.

## Limits

| Item | Limit |
| --- | --- |
| Signed manifest envelope | at most 15 MiB at signing (released clients accept 16 MiB) |
| Pointer | at most 64 KiB; R2-aware clients wait at most 15 s for it, then use the alias |
| Pointed manifest | exactly the size and SHA-256 the pointer names, at most 16 MiB |
| Content set | at most 32 MiB |
| Part | R2 parts are cut at 64 MiB, GitHub-hosted parts at 256 MiB; readers accept up to 256 MiB; one PUT each |
| Part downloads | at most 3 attempts per part (at once, after 5 s, after 30 s); a 404 or 410 stops at once; one hash mismatch is retried |
| Packages and parts | R2-aware readers (T on): at most 2000 packages and 2000 parts in all; a set's parts plus the CI packages must fit in 2000. Readers before T: 850 packages |
| Files per release | 100,000 |
| Root files | 64 |
| Pointer writes | one per second per key (R2) |
| Costs | egress is free; storage beyond the free 10 GB-month and operations beyond the free allowance are billed (see [browser hosting](browser-hosting.md)) |
| Public scope | the whole bucket is readable through the custom domain: never upload receipts, plans, logs, keys or server policies |

## Checks when changing this path

These tests use fakes for R2, GitHub and Godot, plus throwaway Git repositories,
and make no network calls:

```
python -B -m pytest -q -p no:cacheprovider godot-client/tests/test_helper_template.py godot-client/tests/test_desktop_r2.py godot-client/tests/test_desktop_asset_upload.py godot-client/tests/test_desktop_content.py godot-client/tests/test_release_manifest.py godot-client/tests/test_desktop_helpers.py godot-client/tests/test_desktop_release_ci.py
python -B -m pytest -q -p no:cacheprovider godot-client/tests/test_desktop_release_workflow.py godot-client/tests/test_actions_release.py godot-client/tests/test_release_entrypoint_imports.py godot-client/tests/test_prune_published_release.py godot-client/tests/test_shared_release_assets.py godot-client/tests/test_finalize_runner_release.py godot-client/tests/test_publish_runner_release.py
```

The SDK-guard tests that need botocore are skipped without it.

The player side needs Godot 4.7.2 with its export templates, and the native setup
checks also need Inno Setup 6; checks whose tools are missing are skipped. The
runner serves local HTTPS fixtures with the `desktop/v1/` key layout and never
reads R2:

```
python godot-client/tests/run_client_update_tests.py --godot <Godot 4.7.2 executable>
python -B -m pytest -q -p no:cacheprovider godot-client/tests/test_updater_r2_reader.py godot-client/tests/test_updater_discovery.py godot-client/tests/test_startup_updates.py godot-client/tests/test_online_installer_r2.py
```

The live self-test writes at most 100 MB under a fresh `desktop/selftest/` prefix
and never deletes:

```
python -B godot-client/tools/upload_desktop_assets.py selftest --work <private folder> --credentials <private R2 credential file> --receipt <receipt> --ledger <one ledger file for every self-test run>
```
