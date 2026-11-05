# Automatic client updates

This page covers the GitHub Windows/Linux distribution. [Steam and macOS builds](store-builds.md)
use an explicit distribution owner: Steam replaces its own game files, and
standalone macOS updates replace the complete signed app. Those builds retain
commit compatibility checks but never download or apply GitHub update payloads.

## Checking when the game opens

The Windows/Linux GitHub client checks the latest **published** release when
it opens, before a server connection is needed. Draft releases are excluded.
From release T on, it reads the signed release pointer on Cloudflare R2 first and
uses the GitHub release only as a fallback (see
[release discovery](#release-discovery-and-freshness)).
The check verifies the release signature and compares full Git commit ancestry;
hashes are never treated as increasing version numbers. Current builds and
descendants of the published release are left alone. Unrelated branches are
not automatically downgraded. An offline check leaves the game usable.

If the installed release is behind, the game asks whether to update. **Yes**
starts the installed updater, closes the game, waits for the game and its
previous launcher to relinquish the installation, installs changed packages,
and reopens the game. Normal, debug, compatibility and safe-mode launches retain
their renderer, diagnostic logging, server arguments and temporary safe-mode
settings. A failed updater launch leaves the current game open. **No** keeps
playing and leaves a compatibility warning asking the player to update as soon
as possible. Server update notices cannot override that choice.

Normal shortcuts use the launcher's `--launch-only` mode: they recover an
interrupted installation if needed, but do not silently install a pending or
new release before the game can ask. The updater also recognizes an installed
official build and uses this behavior for older shortcuts that lack that flag.
To update immediately from the command line, use `-- --install-update` to
update and play, or `-- --update-only` to update and exit. With no installed
game, the standalone updater performs the initial installation as before.

The launcher starts the game with the renderer its settings ask for: the
player's explicit choice (Forward+, Mobile or OpenGL Compatibility), or, for
Automatic, the renderer the game recorded for this computer while that
recommendation is active (`auto_renderer_state` trial or ok, with fewer than two
trial starts that did not reach ok; see `client-compatibility.md`). Without a
recorded recommendation Automatic is the project default, Forward+. The
compatibility and safe-mode launchers always force OpenGL. The launcher lists
`renderer-relaunch` in `RABBITLANDS_LAUNCHER_FEATURES` for the game. A game that
must restart into another renderer then exits with code 75, and the launcher
starts it once more with the renderer the settings now ask for, plus
`--graphics-renderer-restarted`, while it keeps the installation lock. It does
not relaunch a second time. If a start that tries the recorded renderer (state
trial) ends with an error exit within 60 seconds, the launcher sets
`auto_renderer_state` to `failed_start` and leaves every other setting as it
is. Automatic then starts the project default on that computer. A game started
by an older launcher sees no feature and restarts itself, as before.

Source checkouts and ordinary custom exports receive selectable manual commands
instead of an automatic replacement. The commands fetch the published commit's
release tag, show incoming commits, and request a fast-forward merge before
reimporting or rebuilding. They never reset, stash, discard local edits or
force a branch switch. Review and save local changes first; divergent branches
need a deliberate merge. The release orchestrator and Actions runner mark
official builds with `release_build`; `package_client.py` defaults to a custom
build unless deliberately given `--release-build`. The game additionally
requires its installed descriptor to match its embedded identity and an
installed updater before offering automatic replacement.

New signed manifests include the published commit's complete ancestor list.
For an older manifest without that list, the startup check uses GitHub's commit
comparison API. Older releases without a stable manifest alias are discovered
through GitHub's latest-release metadata; their manifest signature is still
required. No downloads are applied by the startup check itself.

## Release discovery and freshness

From release T on (the helper-train release, the first release of
[desktop R2 delivery](desktop-r2-delivery.md)), installed games and updaters find
releases through a small signed **pointer** on
Cloudflare R2, and fall back to the GitHub release when it cannot be used. Games and
updaters before T read only the GitHub alias. They reach T's updater through the
helper handover described [below](#independent-packages-and-the-updater), before
they read any R2 address.

**The pointer.** The signed record
`https://assets.rabbitlandsgame.com/desktop/v1/channels/live/<platform>.json`
names the live release's commit, version and sequence, and the address, size and
SHA-256 of an immutable copy of its signed manifest under `desktop/v1/manifests/`.
The R2 base is compiled into the game and the updater; no manifest, server or
environment setting can change it. Discovery works like this:

1. Read the pointer, waiting at most 15 seconds and reading at most 64 KiB.
2. Verify it with the pinned release key. Its kind, repository, platform and
   channel must match, and its sequence must be at least this installation's
   high-water mark (below).
3. Fetch the manifest copy it names, limited to that size. Its SHA-256 must be the
   pointer's, and its commit, version and sequence must be the ones the pointer
   states.

Any failure falls back to the GitHub `latest` alias: offline, DNS, a challenge
page, a 404, a bad, foreign or stale signature, or a manifest that is missing or
differs. A pointer is never taken for a manifest. It has no top-level commit or
package list, so every release verifier refuses it, and the game refuses any signed
record that has a `kind`.

At game start, a pointer naming the installed commit, or one of its ancestors, ends
the check at once, with no manifest download. Otherwise the game compares the
pointed release by ancestry, as above, and asks when the installed build is behind.

**High-water mark.** `release-pointer.json` in the installation's update cache
(`client-updates/<installation id>/` in the game's user data folder) holds the
highest pointer sequence the installation has accepted. It is written with a
temporary file and a rename, only ever raised, and a missing or damaged file counts
as no mark. Source and editor runs keep no mark.

**Installed-release record.** After the commit point, the updater and the setup
helper write `.rabbitlands-release.json` in the installation folder, with a
temporary file and a rename: the commit, the platform, the manifest's signed
sequence (0 for a manifest from before T) and, from the updater, the manifest's
SHA-256. It is also rewritten when an update finds nothing to install. A record
whose commit differs from `app/client-release.json` (another installer changed the
game since) is ignored, so a stale record never locks an installation out. A
pointer is accepted only when its sequence is at least the higher of the mark and
the record's sequence; an older one counts as stale.

**Downgrade guard.** The updater refuses a manifest whose signed sequence is lower
than the installed record's, with "This update is older than the installed game.",
unless a signed pointer marked `rollback: true` named exactly that manifest.

- A manifest from before T has no sequence and counts as 0. An installation without
  a record (installed before T) behaves as before.
- When the alias offers an older release, the updater still starts the installed
  game; `--update-only` and a fresh installation stop with the message.
- The game applies the same rule before it offers an update, and a download that an
  earlier game prepared for an older release is dropped the next time the updater
  installs, never installed.
- Only discovery is guarded: the pointer, the alias and the server's required
  release. An installer's own manifest is not: `*-setup.exe`, `*-download.sh` and
  `--install-manifest` install the release the player chose, and write the record.

**Rollback pointers.** A pointer marked `rollback: true` only admits the one
manifest it names, even when that release is older than the installed one. The game
offers only a release that has the installed commit among its ancestors, so an
installation that already has the newer release moves back only when the player
runs the updater explicitly (`-- --update-only` or `-- --install-update`).

**The server's required release.** When the game server requires a client commit
that the installed build lacks (see the table below), and the player has not
declined an update in this session, the game looks for exactly that release and
**bypasses the pointer**, which might be frozen or forgotten:

1. the GitHub alias;
2. the policy's `manifest_url`: a GitHub release download of this repository, or an
   R2 manifest copy, whose bytes must hash to the SHA-256 in its name.

Only a signed manifest of exactly that commit, not older than the installed
release, is offered: "The game server requires Rabbit Lands release <commit>."
Accepting starts the updater with `--target-commit=<commit>` and, when the
policy names a usable manifest address, `--target-manifest-url=<address>`. The
updater then installs only that commit: it skips a pointer that names another
commit, and uses the address when the alias names another commit. When nothing is
found, a later server notice may try again after five minutes.

**Handover limit.** When a release names another updater, the updater hands over to
it, and the new updater discovers again with the same request. Each handover adds
`--handoff-hops=<n>`; at three handovers the updater stops with "Updater versions
disagree; try again later." The `--target-commit=`, `--target-manifest-url=` and
`--handoff-hops=` flags belong to the updater: they are removed before the game
starts and from saved launch modes.

**What the updater logs.** Each discovery prints the path it used:

- `Release discovery: R2 pointer <sequence>, commit <first 9 hex digits>`, with
  `(rollback)` after the sequence for a rollback pointer;
- `Release discovery: the R2 pointer was not used (<reason>)`;
- `Release discovery: the R2 pointer names <commit>, not the requested <commit>`;
- `Release discovery: GitHub alias, commit <first 9 hex digits>`;
- `Release discovery: server target, commit <first 9 hex digits>`.

## Independent packages and the updater

Fresh installation still starts with **one file**: the Windows `*-setup.exe`,
or the Linux `*-download.sh` helper. The release also provides a standalone
`*-updater.exe` / `*-updater.x86_64`. Run it beside an existing `app/` folder
to update that installation. If downloaded elsewhere, it uses the per-user
`Programs/RabbitLands` folder on Windows or `~/Games/RabbitLands` on Linux.
`-- --root /absolute/game/folder` selects a custom installation explicitly;
`--update-only` checks and installs without starting the game.

The schema 2 signed manifest lists independent ZIP packages. New release builds
use checksum-named `RabbitLands-pkg-<SHA256>.zip.part` downloads in the permanent
supporting storage prereleases. Actions builds place packages in `client-assets-0`
through `client-assets-f`, selected by the first digit of each part's SHA-256.
This keeps GitHub's 1,000-assets-per-release limit independent of the total
package count. Existing `client-assets` URLs remain valid; older builds also use
`.pkg.<id>.zip.###` names.
From release T on, releases come from the
[R2 release workflow](desktop-r2-delivery.md). Content packages built on the
owner's build machine are stored on Cloudflare R2 as
`https://assets.rabbitlandsgame.com/desktop/v1/parts/<SHA256>.bin`, in parts of at
most 64 MiB. The `engine` and `native-runtime` packages and the updater and
uninstaller stay in the GitHub pools. A release built with the workflow's `ci`
source keeps all its parts on GitHub.
Each package has a full ZIP SHA-256, bounded download-part hashes, and a signed
inventory of its files, sizes and hashes. Fixed groups cover the engine,
client pack, content packs, release descriptor, actors, maps, audio, shared
assets and records.
The release descriptor (`app/client-release.json` and its loose copy
`app/data/client_release.json`) is its own `release-descriptor` package, so its
per-commit change no longer rewrites the client pack's package or a records
bucket. Path-based buckets
keep membership stable when another file is added. ZIP timestamps, entry order
and permissions are fixed, so an unchanged package keeps its checksum across
builds, independent of the release date, filename and source-file timestamps.
Windows and Linux builds split the exported PCK (W2-UD-06, `tools/pck_split.py`).
`app/RabbitLands.pck` is a small core pack in the `client` package. It holds
scripts, scenes, data, every `.import`/`.remap`, the UID and class caches, the
resources the engine reads before the first autoload, and
`data/content_packs.json`. Prepared content stays in it until W2-UD-07a. The
imported textures, audio and login videos are content packs in `app/packs/`
(`equipment-textures-0..3`, `textures-0..1`, `audio`, `video`), each its own
`pck-<name>` package. The packs keep their bytes from release to release, so a
code-only release downloads only `client` and `release-descriptor`, and a content
release also downloads the packs whose files changed. The first autoload,
`ContentPacks` (`src/boot/content_packs.gd`), checks each pack's size and mounts
it at start. If a pack is missing or the wrong size, the game asks the player to
repair the installation (run the updater; on Steam, Verify integrity of game
files; a standalone build is installed again from its download), which restores
it like any other installed file. This is package reuse, not a binary patch
within a PCK, GLB or ZIP. macOS bundles and `--benchmark-profile` keep one PCK,
and `--no-split-pck` builds one on purpose.
Actor VRAM sidecars (W2-AT-C3, `app/assets/actors/<a>/<b>/.../vram/*`; packaged
only once release-enabled, after W2-AT-C4) form `actors-<a>-<b>-textures-NN`
packages, 32 buckets per actor folder. Every other file keeps its package, so a
code-only or GLB-only release downloads no sidecar, and a re-encoded sidecar
re-downloads only its bucket.

**Manifest schema 3 (zstd payloads).** A schema 3 manifest is a schema 2
manifest whose inventory rows may carry `"codec": "zstd"`. Each 8 MiB chunk of
such a file is a STORED ZIP entry holding one zstd frame (level 19, content size
and checksum on) that decodes to exactly that chunk. The updater decodes each
frame into a buffer of the chunk's size. It refuses a chunk that is not stored,
a damaged frame, a failed frame checksum, and a frame that decodes to any other
size. It still checks every file's SHA-256 before anything live changes. Rows
without `codec` keep schema 2's deflate or stored chunks, and one package can
mix both. A codec row is refused under schema 2, and an unknown codec under any
schema. The codec does not change installed files or their SHA-256, so moving a
package to zstd downloads nothing extra for an existing installation. Updaters
before schema 3 refuse the manifest with "The update format is unsupported."
and delete a stale `pending.json`; they never extract it. They still verify its
bootstrap rows and replace themselves with the helper it names, and that helper
reads it. The setup helper (`tools/install_client_payload.gd`) chooses its path
with the same check (`Release.package_manifest`), and the Inno script queues
packages for schema 3 as it does for schema 2. The R2 workflow signs schema 3 from
release T on; only schema 3 may name R2 parts. The local and full-CI builds write
their payload with the same writer (`release_manifest.release_payload`), in
canonical bytes and with the lowest schema their rows need: 2, or 3 once rows carry
zstd.

Loose map textures use 128 stable buckets per map pool, with JSON metadata in
eight separate buckets. Updating a generated texture or its small index no longer
invalidates a large package of unrelated meshes and textures. The package format
and signed-file checks remain compatible with earlier package updaters.

Prepared world data is shipped loose under `app/prepared-world/`, outside the
client PCK. Each engine/renderer-family compatibility variant (Forward+ and
Mobile share one variant) has a small catalog package, eight stable metadata buckets and 128 stable native-payload buckets.
The geometry, collision and paving files use the same signed file inventories,
part checksums, repair checks and transactional installation as other assets.
Changing client code alone does not change these package identities. A changed
map changes its affected payload buckets and metadata, while unchanged buckets
remain reusable. Removed files are retired with the ordinary installation
inventory; the updater does not modify player cache directories.

The client PCK binds the compatible loose catalog by checksum. The client reads
shipped preparation in place, retaining its local-cache and raw-source fallbacks.
It does not copy a second full cache into the player profile at first launch.
Incompatible or missing preparation never qualifies as a cache hit. Explicit
local preparation remains available for alternate renderers and development.

The build compares local file hashes with GitHub's recorded SHA-256 and size,
reusing identical uploaded packages across releases. Changed packages get new
checksum names. Both platform manifests and `SHA256SUMS` reference those files;
the latest playable release remains separate from this shared download store.
New helpers also have checksum names, so unchanged updaters and uninstallers
are reused. Their URLs stay under `client-assets`, allowing installed launchers
to update their helpers before validating packages in partitioned storage.
Storage partitions affect download placement, not package membership or selective
updates. Both platforms' receipts identify their storage destinations; finalization
and publication verify bytes at those exact destinations. Unused pool parts are
removed only after publication and only when no competing client draft remains; the
R2 workflow keeps every part of the releases it retains for rollback, and nothing
on R2 is deleted.
The signature still binds the repository, helper kind, platform,
exact download URL and expected hashes. Arbitrary external URLs are rejected. An R2
part is accepted only in a schema 3 manifest and only at its one derived address,
`https://assets.rabbitlandsgame.com/desktop/v1/parts/<its signed SHA-256>.bin`:
no other host, path, port, query or spelling. Updater and uninstaller rows keep the
GitHub-only rule. A schema 2 or 3 release may list at most 2000 packages and 2000
parts in all (updaters before T: 850 packages).

For the first upgrade from a client without shared-download support, run the
new setup file or the newly downloaded standalone updater once. Keep its
downloaded filename when running it; the installed canonical updater serves
normal launch shortcuts. New helpers accept both older commit-pinned downloads
and shared downloads. Linux's one-file shell installer now downloads the native
updater, which installs the required packages directly; it no longer downloads
a separate complete game archive. The helper embeds its signed manifest, so it
installs the matching build even during a draft test. Shared downloads are
public supporting files; the draft itself is not promoted to latest by a build.

The updater checks actual installed file hashes, file by file. A package with a
missing, damaged or differently spelled member downloads again, but only those
members are unpacked; matching files stay where they are and are never copied.
This also works with an older installation that has no package receipt.
Downloads resume from checksum-verified cached parts. A corrupt or interrupted
download never replaces the live game. Package and updater-helper downloads read
1 MiB per pass of Godot's download thread, which sleeps until the next timer tick
after each read (15.6 ms at Windows' default timer resolution, about 2 ms when a
finer one is in effect). The engine's 64 KiB default capped downloads at about
4.2 MB/s (or about 30 MB/s); 1 MiB raises that ceiling to about 66 MB/s (or about
250 MB/s). On a connection slower than the ceiling the download thread keeps one
processor core busy, as it already did on connections slower than the old
ceiling, and closing the updater mid-download waits for the current 1 MiB read to
finish: up to about one second at 8 Mbit/s, about four seconds at 2 Mbit/s and
about eight seconds at 1 Mbit/s (64 KiB waited at most about half a second there).
Manifest and API requests keep the default.

Changed files are unpacked into `.eloria-update-stage/` and hashed again from
disk. Before any live file moves, the updater writes a per-update journal,
`.eloria-update-journal-v2.json`, listing every operation in order:

- **retire**: a file no package lists moves into `.eloria-update-backup/`;
- **replace**: the installed file moves into that backup, then its new version
  moves into place;
- **add**: a new file moves into place.

Every operation is a rename inside the installation folder. At the commit point
the updater checks the installed descriptor, executable and pack again, and
stats every file it did not replace. A file whose size or modification time
changed since the scan, or whose time is within three seconds of the scan (file
times have one-second resolution), is hashed again. It then deletes the journal,
the backup, the stage and the downloaded packages, and removes folders that
became empty. No backup is kept after a successful update. Before unpacking, the
updater checks that the changed files plus 64 MiB fit on the installation's
drive.

On Windows, a file whose name changes only in case is replaced so that its new
spelling lands. Folder spelling is left as installed, because Windows ignores it.
A fresh installation (no `app/` or `eloria-assets/` yet), or one with a linked
folder inside those roots, keeps the earlier two-root behavior: both roots are
staged in full and promoted together with the two-root journal.

The installer and updater keep the checked package plan in memory for their one
locked transaction, avoiding a second scan after downloading. The scan lists the
installed folders once, noting which files and folders are links, then hashes the
installed files on up to four threads (one fewer than the processor count; files
of 8 MiB and more first, largest first). The plan is the same as a one-thread
scan's. Setting `RABBITLANDS_UPDATE_SCAN_THREADS=1` restores the
one-thread scan (values above one choose the thread count, at most 16). Every
file still receives its signed SHA-256 check,
staged files are hashed again before anything live changes, and untouched files
are checked at the commit point as described above. The plan is never loaded
from disk or reused by a later updater run, and a plan made before an
interrupted update was recovered is discarded. Single-part packages are promoted
directly from their verified download instead of making another complete archive
copy.

When explicitly run or accepted from the game, the updater finds the release as
described under [release discovery](#release-discovery-and-freshness): the signed R2
pointer first (from release T on), then the stable `RabbitLands-<platform>.json`
alias in the latest published release. Its **bootstrap schema 1** contract verifies
the signature, platform and updater/uninstaller hashes before parsing the game
package format. If the updater needs replacement, it downloads and verifies
its successor, hands over to a temporary copy outside the installation, closes
the original, replaces the executables, and restarts. Windows never overwrites
its running updater in place. Game revisions do not enter the bootstrap's
embedded trust identity. The same existing signing key is retained.

Each launcher start removes what earlier handovers left in the update cache
while it holds the installation lock, and logs every removal in the Godot log.
A `handoff-<pid>` copy is removed once its starting launcher has exited and
both the copy and the latest handover record are more than ten minutes old.
Linux checks the pid in `/proc`. Godot on Windows reports only child processes,
but Windows refuses to delete an executable that is still running, so a copy in
use stays until a later start. Staged `bootstrap/<sha256>` helpers other than
those named by the latest verified handover record are removed; an unfinished
handover keeps the helper it still needs. When the installed updater itself is
running and both installed helpers are complete,
`.rabbitlands-bootstrap-previous/` is removed. Unrecognized files are kept.

Before-package clients cannot understand schema 2. For their first upgrade,
run the new setup file, or put the new standalone updater in the game folder
and run it once. The new updater checks their installed files and downloads
only packages that differ. Subsequent updates use the installed updater.

Run `RabbitLands-uninstall.exe` or `RabbitLands-uninstall.x86_64` to remove the
installation and its download cache. It asks for confirmation and refuses a
running or Steam-managed installation. On Windows it uses the registered Inno
uninstaller when available, preserving Windows' shortcut/app-entry cleanup;
otherwise a hidden native helper removes the files after the executable exits.
The Inno uninstaller also removes what an interrupted update can leave:
`.eloria-update-stage/`, `.eloria-update-backup/`, older updaters'
`.eloria-previous/`, the update journals with their temporary `.tmp` files, and
the installed-release record `.rabbitlands-release.json` with its `.tmp`.
Linux removes the recognized game folder directly. Player settings outside the
installation are retained. Windows **Installed apps** can also uninstall an
Inno installation.

The game server names the **client Git commit packaged for that server**. This
is independent of the server repository's own commit. Client builds contain
their full commit ID and complete ancestor list, generated from Git at package
time. The connection declares that history before login, in bounded packets.

| Installed client history | Behavior |
| --- | --- |
| Same commit as the server requires | Keep the installed game |
| Server's required client commit is an ancestor of the installed client | Keep the newer client, including merge descendants |
| Installed client is an ancestor of the required client commit | Download the server's chosen build |
| Installed client and required client are on unrelated/divergent branches | Download the server's chosen build |
| No complete build declaration | Require an initial manual install when enforcement is enabled |

No version/date ordering is used. Branch names and shortened hashes are not
accepted as release identities. Packaging from a shallow clone is refused.
The declaration is a compatibility check, like client capabilities; it is not
an anti-cheat attestation of executable code.

## Build machine setup

Player releases go through [desktop R2 delivery](desktop-r2-delivery.md). There
the build machine builds content with `package_client.py --no-client-updates`, which
needs no key, and GitHub Actions signs in owner-approved jobs. Once the owner moves
the signing key into those jobs, it is no longer on the build machine. The signed
local builds below need that key, so they serve only the transition before the key
moves, and distributions with a key of their own.

Signed release builds require the existing release private key matching
`godot-client/data/update_public.pem`. The private key is not included in a
clone. Keep it and its backup outside both repositories, never upload it, and
select its actual private location with `--update-signing-key`. Moving a
checkout does not create or replace that key.

Players pin the public key in their initial client and restart launcher. Reuse
that signing key for their updates. For a new distribution without an installed
trust key, Godot's `tools/sign_client_release.gd` can generate a pair with
`-- generate <private.pem> <public.pem>`; it refuses to overwrite existing keys.
`--update-public-key` selects the matching public key if needed. Packaging
checks that the pair matches. A newly generated key is not trusted by existing
installations; changing their trust root requires an initial installer upgrade.

Godot 4.7.2 and its matching Windows/Linux export templates are required. Run
packaging from the final `rabbitlandsgame/rabbitlands-client` checkout, normally
`C:\rabbitlands\rabbitlands-client`. Private source archives and retired
migration or clean-stage checkouts are not release sources: builds record the
Git history of the checkout they package.

Commit the client changes, then run from that repository, replacing the private
key placeholder and using the verified server endpoint for the deployment:

```powershell
python godot-client/tools/package_client.py --ref HEAD `
  --server "game.rabbitlandsgame.com:2001" `
  --update-signing-key "C:\path\to\private\signing-private.pem"
```

The default build includes the restart launcher and signed update artifacts.
The build reuses `dist/.build/client-src/` and its imported assets. If its Git
registration was lost when a source checkout moved or was replaced, packaging
re-registers that cached folder without discarding the import cache.
`--no-client-updates` builds a conventional download with the same commit
declaration but no downloader/launcher. `--platform linux` builds the Linux
client and updater. No Python or external updater runtime is required on
player computers. `--installer` also builds an Inno Setup installer whose
shortcuts launch through the updater.

## Build both desktop downloads

Maintainers can build a complete release with
`godot-client/tools/build_release.py`. Run it on **Windows** with Python 3.11+
and `numpy`, `Pillow`, and `zstandard` installed in that Python environment.
Install Godot **4.7.2-stable** and both matching x86_64 export templates,
[Inno Setup 6](https://jrsoftware.org/isdl.php), and **WSL Ubuntu-24.04**.
The Linux executable is exported by Godot on Windows and smoke-tested in WSL;
the Windows executable is smoke-tested directly. Missing prerequisites stop
the release before either platform is built.

From the final client repository:

```powershell
python godot-client/tools/build_release.py build --ref master `
  --update-signing-key "C:\path\to\private\signing-private.pem"
```

Use `--godot` or `--iscc` to select tools outside their usual locations.
`--server HOST:PORT` bakes the same server into both platforms' launchers.
The default ref is **local master**; the script does not fetch, promote a
branch, or include uncommitted changes. Deliberately select and commit the
client revision before building. Both targets use the same resolved full hash.

The output is `../dist/releases/client-<full-client-commit>/`:

- **Windows:** one small per-user `*-setup.exe`. It embeds the launch and setup
  helpers, then downloads the matching signed game payload during installation.
  Download progress and SHA-256 checks use Inno Setup 6; the helper also verifies
  the RSA signature, each needed package ZIP and extracted files before installing.
  Setup shows verification, preparation and unpacking progress, including the
  unpacked file count. Keep setup open until these steps finish. A second setup
  is blocked, and a helper still working in the background keeps the installation
  locked until it finishes. Locks left by a crashed helper can be recovered on retry.
  Online setup undoes an interrupted per-file update before it plans, as the
  launcher does. It asks for free space of one copy of its download (its helper
  moves each verified download from setup's temporary folder into the update cache:
  a rename on one drive, a copy across drives) plus the larger of the unpacked game
  and its largest multi-part package, plus 512 MiB. Multi-part packages are joined
  before unpacking starts, so the two never add up. A setup for an R2 release
  downloads its content parts from R2 and the rest from GitHub. A failed or
  tampered download stops setup before its helper runs and installs nothing; run
  setup again.
  Setup can repair the same build. Players need an internet connection, and
  do not manually download the update parts. Shortcuts start the restart updater.
- **Linux:** one `*-download.sh` helper. It verifies and starts the native
  updater, which installs the required independent packages. There is no
  duplicate full-game archive in the orchestrated release. Play again through
  `~/Games/RabbitLands/RabbitLands-updater.x86_64` (or your chosen parent folder).
- Both signed update manifests, their stable latest-release aliases, independent
  checksum-named package downloads, and standalone updater/uninstaller executables.
  Supporting packages and helpers live in the permanent `client-assets` prerelease
  and are linked from the playable release; their existing uploads are reused.
- `SHA256SUMS` and `RELEASE-NOTES.md` for players, `release.json` listing exactly
  the upload assets, and a combined **local** `client_updates.json` policy.

Only the listed player downloads, signed manifests, update parts and checksums
are uploaded. Build folders, logs, signing keys and server policy stay local.
The initial Windows ZIP is omitted because the installer handles large games.
The source archive alone lacks imported Godot resources and generated texture
caches; online setup downloads the prepared runtime files named by its signed manifest.
Shared package downloads are public supporting files, so a downloaded draft
installer can install its signed build before the playable release is published.
The startup check continues to use the latest published playable release.
Get a new setup executable when the current compiled release is replaced.
An offline Windows installer is still available with `package_client.py --installer`
without `--online-installer`; keep all of its companion `.bin` files together.
Every upload asset is checked against GitHub's limit and hashed. If a build
fails, fix the cause and use a fresh `--out` directory; existing release output
is never silently overwritten. The packager's shared import/texture cache is
reused across builds.

## Upload a complete desktop release

Desktop releases go through the R2 release workflow and its owner-approved steps;
see [desktop R2 delivery](desktop-r2-delivery.md) and
[runner builds](runner-builds.md). Every desktop workflow is dispatch-only: no push
or merge starts one. The R2 workflow publishes only after the owner's approvals,
and prunes only in its promote step, keeping whole releases for rollback. The
transitional full-CI workflow, once dispatched, still publishes its release as
latest and prunes with the same retention rule after its checks pass; it refuses
to run once a live R2 pointer exists.

**Do not publish with `build_release.py upload` once a release has gone out through
the R2 workflow.** The command below predates retention:

- it deletes every other client draft, and with `--publish` every other client
  release too, including the releases kept for rollback;
- it marks its release GitHub `latest` without checking the live R2 pointer;
- its manifests carry no signed sequence, so R2-aware updaters refuse them through
  the alias as older than the installed game;
- its bundle is built with the private signing key (`build_release.py build`),
  which the R2 process keeps in GitHub only.

It remains documented for the transition before the first R2-workflow release, and
for reference.

First push the selected client commit through the repository's configured SSH
identity. Uploads require GitHub CLI authenticated as **rabbitlandsgame** with
write access. SSH authentication and CLI authentication are separate; the
script checks the actual API account and refuses another account.

```powershell
$RabbitLandsRelease = "C:\rabbitlands\dist\releases\client-<full-client-commit>\release.json"
python godot-client/tools/build_release.py upload --bundle $RabbitLandsRelease
```

This creates or reuses the **current client draft**, using `RELEASE-NOTES.md` as
its description. The working published release stays available while its
replacement is prepared and reviewed. Older files in the draft are removed only
after all replacement files pass verification. With `--publish`, the script then
deletes the other client releases itself. The **Retire previous published client**
workflow no longer prunes anything; keep it disabled (see
[runner builds](runner-builds.md)).

The commit-specific tag keeps signed update URLs tied to the actual build. The
script verifies that commit exists in the public client repository and refuses
a conflicting tag. Source history and tags remain available independently of
the compiled downloads. No local Git history is pushed by the upload script.

Review the draft and installation instructions. To publish it after all assets
are present:

```powershell
python godot-client/tools/build_release.py upload --bundle $RabbitLandsRelease --publish
```

Ordinary metadata upload failures are retried up to five times per file. Shared
uploads allow longer retries for concurrent platform jobs and preserve active
reservations; only abandoned starters older than six hours are cleared. An interrupted draft can
use the same command again. Downloads already recorded
by GitHub with the expected size and SHA-256 are reused. The script checks the
remote asset list, upload states, sizes and SHA-256 checksums before publication; failures
leave the draft unpublished. `--publish` marks the completed release as latest.
Players can find it on the [client Releases page](https://github.com/rabbitlandsgame/rabbitlands-client/releases).
This local command remains available alongside the [hosted release workflow](runner-builds.md).

After publishing, verify anonymous downloads and deploy the generated combined
`client_updates.json` to the served server profile when ready to roll out the
client. Building and uploading do not change the live server policy.

## Publish on GitHub

The public release repository is `rabbitlandsgame/rabbitlands-client`. Publish player releases there using the project account. Players need no
GitHub credentials, and no credentials are embedded in the client.

The packaging tool writes a `*-github-release.txt` file listing the exact
release tag and assets to upload, and a `*-server-policy.json` file. The tag is
`client-<full-client-commit>`. Package and helper download URLs are pinned to
that tag. The standalone updater uses the latest-release alias only to discover
the signed manifest; its actual downloads retain immutable commit-specific URLs.
The server policy can still select an exact packaged client commit.

1. Reuse the current client release entry as a draft, targeting the packaged
   client commit with that build's tag. Create an entry if none exists yet.
2. Upload the signed manifests, aliases, updater/uninstaller executables and every
   `.pkg.<id>.zip.###` part listed in the instructions. Parts are at most 256 MiB.
   Initial installations use the Windows setup file or Linux download helper.
3. Verify all replacement assets, publish the release and confirm public downloads.
   Before the first R2-workflow release, retire the previous compiled release after
   the replacement is available. After it, never delete releases or assets by
   hand: the R2 workflow keeps the releases needed for rollback.
4. Put the generated policy into the **served server profile** as
   `client_updates.json`. If both platforms are published, combine their two
   `manifests` rows and keep the same `required_commit`.

Example policy (replace the full hash and manifest filename with the generated
values; do not paste a truncated commit):

```json
{
  "schema": 1,
  "required_commit": "<full-client-commit>",
  "enforce": true,
  "manifests": {
    "windows": "https://github.com/rabbitlandsgame/rabbitlands-client/releases/download/client-<full-client-commit>/<package>-windows.json"
  }
}
```

The release workflow's finalize step writes the `manifests` URLs as GitHub
commit-tag downloads, which every client reads; keep them. R2-aware games (release
T on) also accept the release's immutable R2 manifest copy,
`https://assets.rabbitlandsgame.com/desktop/v1/manifests/<platform>/<sha256>.json`,
whose bytes must hash to the name; older games accept only GitHub release
downloads. When `required_commit` names a release that the R2 pointer does not,
R2-aware games skip the pointer and look for that release (see
[release discovery](#release-discovery-and-freshness)).

The server defaults to re-reading this file every 30 seconds and notifies
existing connections when the policy changes. A partial/invalid edit retains
the last valid policy. Write the policy atomically after all assets have been
published and, for an R2-workflow release, after the `check-policy` mode of
`upload_desktop_assets.py` confirms that both live pointers and GitHub `latest`
name its commit. `enforce: true` blocks incompatible **new logins/character creation**
before credentials are processed. Connected players are not disconnected and can
finish their session. Games from release T on also offer the required release (see
[release discovery](#release-discovery-and-freshness)); earlier games show a
compatibility notice. `enforce: false` offers the update without blocking login.
An empty object disables release checks. The server settings
`client_updates_file` and `client_update_check_seconds` select the file and
poll interval.

## Player behavior and recovery

Start with `RabbitLands.bat`, `RabbitLands.sh`, or the installer shortcut. The game
itself downloads no update in the background: it asks when it opens, or when the
game server requires a release, and an accepted update starts the updater. The
updater shows download progress, verifies the signed manifest, every download
part and each assembled package, then installs. Hashing and assembly run on a
worker thread. Compatible clients receive only the compatibility notice and
download nothing.

Each download part gets at most three attempts: at once, after 5 seconds and after
30 seconds, and the progress line shows `<package> (retrying in N s)` meanwhile.

- **Retried:** no reply, a transfer that was cut short, too slow or longer than
  signed, the replies 403, 408 and 429 and every 5xx reply (for example a challenge
  page or a busy edge), and one hash mismatch.
- **Not retried:** 404 or 410, which ends with "The update files are not available
  yet. Try again later."; other replies; local file errors; and a request that
  could not start.
- **Ends:** a second hash mismatch ends with "A downloaded package failed
  verification." A verified part that cannot be moved into the cache ends with "The
  verified package download could not be recorded."

Every attempt starts from an empty file and the same signed row: there is no other
host, and never unverified bytes. Verified parts stay in the update cache, so the
next run resumes at part granularity, including after an exit.

The game never overwrites itself while running. The updater, once the game has
closed, verifies the downloads again, unpacks the changed files to a
sibling staging folder, validates paths/checksums, and moves them into `app/`
and `eloria-assets/` under the per-file journal. If the launcher stops part-way,
for example in a crash or power cut, the next start reads the journal and undoes
the moves in reverse order. New files go back to the stage, and the originals
return from `.eloria-update-backup/`, so the previous installation is restored
file for file. A retry needs no new download, because verified packages are
kept until the commit point. A backup left without its journal (a stop after
the journal was cleared) holds only replaced originals and is deleted at the
next start. If the journal itself cannot be read, for example because a power
cut lost its bytes but kept the moves made after it, recovery still puts every
original in the backup back; files the update added may stay until the next
update checks the installation again and retires or keeps them.

Journals and backups from earlier updaters stay readable: an interrupted
two-root update (`.eloria-update-journal.json` with `.eloria-previous/`) is
recovered as before. A whole-game `.eloria-previous/` left by an older updater,
or by the two-root path for a linked folder, is not needed once no journal
exists. The next update removes it before staging. The launcher also removes it
once the updated game has been running for a minute and has recorded its
running lease. That removal runs on a low-priority thread, never while a journal
exists, and pauses when the game closes. A lock protects an
installation from concurrent launchers and from installation while its game
process is still running. Downloads and readiness records are scoped to each
installation under the player's game user directory; account preferences stay
in the existing user directory.

The game also removes cache generations it can never read again from the
player's user directory (`src/runtime/cache_janitor.gd`). In release builds,
30 seconds after the update checker starts, a low-priority worker removes:
- map geometry, collision-face and paving policy folders whose own entry header
  shows an older cache version, or the same version under another engine,
  format or Mobile's former own renderer key;
- the legacy scene-cache entries (`map-cache`) of geometry-scoped whole maps
  such as the gauntlets, which load prepared geometry instead.

The newest policy of each renderer family is always kept (Forward+ and Mobile
share one; OpenGL Compatibility has its own), so switching renderers rebuilds
nothing. Folders it cannot prove stale are kept. It does nothing to the policy
folders while a world preparation runs or is pending, stops at the next file
when the game closes, and prints one `RABBITLANDS_CACHE_JANITOR` line with the
bytes it freed. Godot's shader caches are left alone unless
`RABBITLANDS_CACHE_JANITOR_SHADERS=on`; that rule (non-newest generations idle
for 14 days, GLES3 shaders capped at 128 MiB) waits for an owner decision.
`RABBITLANDS_CACHE_JANITOR=off` disables the janitor; `on` also runs it in a
source build. Like the pre-login world preparation, it stays off in timed
benchmark runs (`RABBITLANDS_CROWD_BENCH_START_TOKEN` set) unless switched `on`.

Only changed or damaged asset packages are downloaded, and only their changed
members are unpacked. Keep enough free space for the changed downloads and the
changed files. ZIP entries use 8 MiB chunks and 64-bit archive offsets, so even
a large PCK uses bounded extraction memory. On Windows, each file move retries
for up to five seconds to allow temporary file locks to clear. Game folders
themselves are not moved, so a program holding a folder open no longer blocks
an update. If a move still fails, recovery restores the previous files and the
error identifies the source, destination and error code.
It also gives the path to `last-install-error.json` in that installation's
update cache, recording the failed move, target commit and recovery result.
Close programs using the game folder and retry the updater; verified downloads
are retained after a failed move.
The schema 1 reader remains available for previously signed whole-game downloads.
The updater now replaces its own executable through a verified handover. Its
original trust key remains pinned; changing that key still requires a new
trusted installer rather than trusting a key supplied by a downloaded manifest.

Existing installations without this updater require one manual upgrade.
Building artifacts does not upload them or change any live server policy.

## Optional manual verification

Choose the minimum checks for the behavior being changed. For example:

- Launcher shortcut changes, from the client repository:
  `python -m pytest -q godot-client/tests/test_client_release.py::test_updating_shortcuts_use_restart_launcher_for_both_platforms`.
- Package downloads, self-update and uninstall changes:
  `python -m pytest -q godot-client/tests/test_asset_packages.py`. Native checks use
  the installed Godot/Inno tools on Windows and WSL Ubuntu-24.04 for Linux. The
  per-file install checks end the fixture's own process after every install step
  and require the next start to restore the previous files byte for byte. Its
  fixture project alone reads `RL_UPDATE_TEST_STOP_AFTER`, which shipped updaters
  never do. The checks also cover locked files, case-only renames, and journals
  and backups left by older updaters.
- Schema 3 and zstd packages:
  `python -m pytest -q godot-client/tests/test_asset_packages.py -k "zstd or codec or schema_3 or older_updater"`.
  It covers mixed zstd and deflate rows, multi-chunk and empty files, repair, a
  fresh install, eight kinds of damaged chunk, the schema rules, and a download
  the game prepared that installs at restart. An older updater, taken from Git
  (`RL_OLDER_UPDATER_REFS`, default `origin/develop`; add the live release's
  commit to check it too), must refuse the manifest, delete `pending.json` and
  still replace its helpers. The exported self-replacement check includes a
  schema 3 release and the migration from that older updater. The Inno setup
  checks (they need Inno Setup 6) install schema 2, schema 3, and schema 3 with
  every part at its derived R2 URL through the real setup helper;
  `test_online_installer_r2.py` covers the setup script, its disk space and a
  tampered or missing R2 part against a local mirror of `desktop/v1/`.
- R2 parts and per-part retries:
  `python godot-client/tests/run_client_update_tests.py --godot <godot-path>` runs
  `test_client_update_r2.gd` against a local HTTPS server with the `desktop/v1/`
  layout. Only the fixture's copy of `release.gd` moves the R2 base there. It covers
  scripted 5xx, 429, 403, dropped and garbage replies, a 404 that fails at once and
  a rerun that fetches only the missing parts, two hash mismatches, a cancelled
  wait, and R2 rows refused under schema 2.
  `python -m pytest -q godot-client/tests/test_updater_r2_reader.py` pins the lines
  the release tools read (the R2 base and the 2000-package limit) and the retry
  schedule.
- Release discovery and freshness: the same runner also runs
  `test_client_update_discovery.gd` (the pointer rules, the mark and record, the
  downgrade guard, rollback pointers, server targets, the handover limit and flag
  stripping, with a scripted transport).
  `python -m pytest -q godot-client/tests/test_updater_discovery.py godot-client/tests/test_startup_updates.py`
  exports the updater (it needs the installed export templates) and installs through
  a pointer and R2 parts signed by the release tools with a test key. It also checks
  the record, an older alias refused, a signed rollback, a replayed pointer, a server
  target through the R2 copy, the handover limit, and the setup helper writing the
  record. When the field release's updater (`945042f0`) is in the local Git
  history, it checks that updater handing over to the R2-aware one.
- Renderer launch arguments and the relaunch handshake:
  `godot --headless --path godot-client --script res://tests/test_launch_renderer.gd`.
  The runtime runner below also runs it in its updater-only project, which proves
  that `launch_options.gd` needs no game script. The native check
  `python -m pytest -q godot-client/tests/test_startup_updates.py -k relaunch`
  exports the updater and a stand-in game (it needs the installed export
  templates). It covers the exit-75 relaunch under one lock, the restart marker,
  `failed_start` after an error exit or an engine crash, no second relaunch,
  confirmed, explicit and compatibility starts left alone, and a relaunch that
  cannot start stopping a running backup removal before the lock is released.
- Login enforcement changes, from the sibling server repository:
  `python -m pytest -q tests/test_client_updates.py::test_login_denied_before_password_or_world_processing`.

The older full modules above remain available manually when broader coverage is
needed. `godot-client/tests/test_client_updates.gd` covers runtime signatures,
restart install, corrupted data, archive paths, ancestry, backups and recovery,
including per-file journal validation, rollback and commit.
`godot-client/tests/test_client_update_cleanup.gd` covers backup removal around
journals and the helper cache returning to one staged helper after handovers.
For relevant download/retry changes, the optional local HTTPS harness is
`python godot-client/tests/run_client_update_tests.py --godot <godot-path>`.

The runtime runner creates an isolated project, test keys, HTTPS server and
certificate. Its fixtures never change an installed game or the production
signing keys. These checks are manual, and the full historical suites are not
release gates. The desktop release workflow runs the packaging checks for its
selected source commit.
