# Automatic client updates

This page covers the GitHub Windows/Linux distribution. [Steam and macOS builds](store-builds.md)
use an explicit distribution owner: Steam replaces its own game files, and
standalone macOS updates replace the complete signed app. Those builds retain
commit compatibility checks but never download or apply GitHub update payloads.

## Checking when the game opens

The Windows/Linux GitHub client checks the latest **published** release when
it opens, before a server connection is needed. Draft releases are excluded.
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
`client-assets` supporting prerelease; older builds use `.pkg.<id>.zip.###` names.
Each package has a full ZIP SHA-256, bounded download-part hashes, and a signed
inventory of its files, sizes and hashes. Fixed groups cover the engine,
client pack, actors, maps, audio, shared assets and records. Path-based buckets
keep membership stable when another file is added. ZIP timestamps, entry order
and permissions are fixed, so an unchanged package keeps its checksum across
builds, independent of the release date, filename and source-file timestamps.
The exported `RabbitLands.pck` remains one client package; this is package reuse,
not a binary patch within a PCK, GLB or ZIP.

The build compares local file hashes with GitHub's recorded SHA-256 and size,
reusing identical uploaded packages across releases. Changed packages get new
checksum names. Both platform manifests and `SHA256SUMS` reference those files;
the latest playable release remains separate from this shared download store.
New helpers also have checksum names, so unchanged updaters and uninstallers
are reused. The signature still binds the repository, helper kind, platform,
exact download URL and expected hashes. Arbitrary external URLs are rejected.

For the first upgrade from a client without shared-download support, run the
new setup file or the newly downloaded standalone updater once. Keep its
downloaded filename when running it; the installed canonical updater serves
normal launch shortcuts. New helpers accept both older commit-pinned downloads
and shared downloads. Linux's one-file shell installer now downloads the native
updater, which installs the required packages directly; it no longer downloads
a separate complete game archive. The helper embeds its signed manifest, so it
installs the matching build even during a draft test. Shared downloads are
public supporting files; the draft itself is not promoted to latest by a build.

The updater checks actual installed file hashes. Matching packages use local
files; missing or damaged packages download again. This also works with an older
installation that has no package receipt. Downloads resume from checksum-verified
cached parts. A corrupt or interrupted download never replaces the live game.
Unchanged files and verified changed packages are staged locally, then `app/`
and `eloria-assets/` are promoted together with a recovery journal and previous
installation backup. Files absent from the new inventory are retired. Allow
space for that local stage and the changed package downloads.

When explicitly run or accepted from the game, the updater checks the stable `RabbitLands-<platform>.json` alias in
the latest published release. Its **bootstrap schema 1** contract verifies the
signature, platform and updater/uninstaller hashes before parsing the game
package format. If the updater needs replacement, it downloads and verifies
its successor, hands over to a temporary copy outside the installation, closes
the original, replaces the executables, and restarts. Windows never overwrites
its running updater in place. Game revisions do not enter the bootstrap's
embedded trust identity. The same existing signing key is retained.

Before-package clients cannot understand schema 2. For their first upgrade,
run the new setup file, or put the new standalone updater in the game folder
and run it once. The new updater checks their installed files and downloads
only packages that differ. Subsequent updates use the installed updater.

Run `RabbitLands-uninstall.exe` or `RabbitLands-uninstall.x86_64` to remove the
installation and its download cache. It asks for confirmation and refuses a
running or Steam-managed installation. On Windows it uses the registered Inno
uninstaller when available, preserving Windows' shortcut/app-entry cleanup;
otherwise a hidden native helper removes the files after the executable exits.
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

For bounded-storage hosted builds, see [runner builds](runner-builds.md). That
path builds one platform per job, streams verified parts into an existing draft,
and finalizes small receipts without copying full builds between jobs.

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
after all replacement files pass verification. After the replacement is published,
the **Retire previous published client** workflow verifies its checksum inventory
and retires older published compiled releases. A published release and replacement
draft can coexist temporarily; compiled version history is not retained afterwards.

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
   Retire the previous compiled release after the replacement is available.
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

The server defaults to re-reading this file every 30 seconds and notifies
existing connections when the policy changes. A partial/invalid edit retains
the last valid policy. Write the policy atomically after all assets have been
published. `enforce: true` blocks incompatible **new logins/character creation**
before credentials are processed. Connected players finish their session and
install at restart. `enforce: false` offers the update without blocking login.
An empty object disables release checks. The server settings
`client_updates_file` and `client_update_check_seconds` select the file and
poll interval.

## Player behavior and recovery

Start with `RabbitLands.bat`, `RabbitLands.sh`, or the installer shortcut. The game shows
download progress, verifies the signed manifest, verifies every download part
and each assembled package, and announces when it is ready for the next launch.
Hashing and assembly run on a worker thread. Failed downloads retry automatically
with backoff from 30 seconds to five minutes. Parts interrupted by an exit are
retried; already complete verified parts are reused. Changing the server's
chosen commit supersedes an in-flight update. Compatible clients receive only
the compatibility notice and download nothing.

The game never overwrites itself while running. On the next launch, the small
restart launcher verifies the download again, extracts to a sibling staging
folder, validates paths/checksums, and replaces `app/` and `eloria-assets/`
together. It retains the previous version in `.eloria-previous/`. A journal
recovers an interrupted replacement on the next launch. A lock protects an
installation from concurrent launchers and from installation while its game
process is still running. Downloads and readiness records are scoped to each
installation under the player's game user directory; account preferences stay
in the existing user directory.

Only changed or damaged asset packages are downloaded. The local staging area
also contains unchanged files so both game roots can be replaced together.
Keep enough free space for the changed downloads and staged game; the previous
installation is retained by renaming its folders. ZIP entries use 8 MiB chunks
and 64-bit archive offsets, so even a large PCK uses bounded extraction memory.
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
  the installed Godot/Inno tools on Windows and WSL Ubuntu-24.04 for Linux.
- Login enforcement changes, from the sibling server repository:
  `python -m pytest -q tests/test_client_updates.py::test_login_denied_before_password_or_world_processing`.

The older full modules above remain available manually when broader coverage is
needed. `godot-client/tests/test_client_updates.gd` covers runtime signatures,
restart install, corrupted data, archive paths, ancestry, backups and recovery.
For relevant download/retry changes, the optional local HTTPS harness is
`python godot-client/tests/run_client_update_tests.py --godot <godot-path>`.

The runtime runner creates an isolated project, test keys, HTTPS server and
certificate. Its fixtures never change an installed game or the production
signing keys. These checks are manual, and the full historical suites are not
release gates. The desktop release workflow runs the packaging checks for its
selected source commit.
