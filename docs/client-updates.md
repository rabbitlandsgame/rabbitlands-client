# Automatic client updates

This page covers the GitHub Windows/Linux distribution. [Steam and macOS builds](store-builds.md)
use an explicit distribution owner: Steam replaces its own game files, and
standalone macOS updates replace the complete signed app. Those builds retain
commit compatibility checks but never download or apply GitHub update payloads.

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
  the RSA signature, complete archive and extracted files before installing.
  Setup can repair the same build. Players need an internet connection, and
  do not manually download the update parts. Shortcuts start the restart updater.
- **Linux:** a `.tar.gz` containing the native executable, updater and launch
  scripts with executable permissions. An archive larger than 256 MiB is
  split into `.tar.gz.001`, `.002`, etc., each at most 256 MiB. The
  generated release notes give the exact reassembly/extraction command.
- Both signed update manifests and their bounded `.update.zip.###` downloads.
- `SHA256SUMS` and `RELEASE-NOTES.md` for players, `release.json` listing exactly
  the upload assets, and a combined **local** `client_updates.json` policy.

Only the listed player downloads, signed manifests, update parts and checksums
are uploaded. Build folders, logs, signing keys and server policy stay local.
The initial Windows ZIP is omitted because the installer handles large games.
The source archive alone lacks imported Godot resources and generated texture
caches; online setup downloads the prepared runtime files from the same release.
Its commit-pinned downloads require a published release. Draft installers can be
reviewed and tested locally; public downloads begin after publication. Get a new
setup executable when the current compiled release is replaced.
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

Transient upload connection failures are retried up to five times per file;
failed upload reservations are cleared before retrying. An interrupted draft can
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
`client-<full-client-commit>` and download URLs are pinned to that tag, rather
than GitHub's moving “latest release.” This keeps the chosen client tied to the
server being deployed.

1. Reuse the current client release entry as a draft, targeting the packaged
   client commit with that build's tag. Create an entry if none exists yet.
2. Upload the signed platform manifest and every `.update.zip.###` part listed
   in the instructions. These parts are each at most 256 MiB, below GitHub's
   release asset limit. The regular standalone ZIP/tarball is an initial
   install artifact; if it reaches 2 GiB, use `build_release.py` to prepare the
   Windows installer slices and split Linux download described above.
3. After verifying all replacement assets, remove the previous compiled files,
   publish the release and confirm its assets download without signing in.
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
and the assembled payload, and announces when it is ready for the next launch.
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

These first updates replace the full game payload, not just changed assets.
Keep enough free space for the download, staged game and previous version.
Archive entries are divided into 8 MiB chunks so a large PCK does not require
loading the entire file into RAM. The initial restart bootstrap is stable and
keeps the original trust key; a change to the bootstrap or signing trust root
requires an initial installer upgrade.

Existing installations without this updater require one manual upgrade.
Building artifacts does not upload them or change any live server policy.

## Optional manual verification

Choose the minimum checks for the behavior being changed. For example:

- Launcher shortcut changes, from the client repository:
  `python -m pytest -q godot-client/tests/test_client_release.py::test_updating_shortcuts_use_restart_launcher_for_both_platforms`.
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
