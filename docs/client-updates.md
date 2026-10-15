# Automatic client updates

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

The initial RSA signing key pair for this workspace has been generated:

- Public key: `godot-client/data/update_public.pem` (commit this).
- Private key: `../work-output/client-updates/signing-private.pem` (keep private,
  back it up outside the repositories, never upload it).

Future builds must use that same signing key. Players pin its public half in
the initial client and restart launcher. To create a key pair in another
workspace, use Godot's `tools/sign_client_release.gd` with arguments
`-- generate <private.pem> <public.pem>`; it refuses to overwrite existing keys.
`--update-signing-key` and `--update-public-key` select a different pair at
package time. The packaging tool verifies that the two keys match.

Godot 4.7.2 and its matching Windows/Linux export templates are required.
Run the packaging commands from the client repository root (`rabbitlands-client/`
or `clean_client/` in this workspace).

Commit the client changes, then run from that repository:

```powershell
python godot-client/tools/package_client.py --ref HEAD --server "YOUR_PUBLIC_HOST:2000"
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

## Publish on GitHub

The release repository is configured as `rabbitlandsgame/rabbitlands-client`; make it public before publishing player releases. Players need no
GitHub credentials, and no credentials are embedded in the client.

The packaging tool writes a `*-github-release.txt` file listing the exact
release tag and assets to upload, and a `*-server-policy.json` file. The tag is
`client-<full-client-commit>` and download URLs are pinned to that tag, rather
than GitHub's moving “latest release.” This keeps the chosen client tied to the
server being deployed.

1. Create a GitHub Release at the packaged client commit using that tag.
2. Upload the signed platform manifest and every `.update.zip.###` part listed
   in the instructions. These parts are each at most 1 GiB, below GitHub's
   release asset limit. The regular standalone ZIP/tarball is an initial
   install artifact; if it exceeds 2 GiB, use the optional Windows installer
   with its `.bin` slices or another initial-download distribution method.
3. Publish the release and confirm its assets download without signing in.
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

## Verification

- Server: `python -m pytest tests/test_client_updates.py`
- Payload/launchers: `python -m pytest godot-client/tests/test_client_release.py`
- Runtime: `tests/test_client_updates.gd` verifies signatures, restart install,
  corrupted data, archive paths, ancestry, backups and interrupted recovery.
- Runtime and real local HTTPS downloads/retry:
  `python godot-client/tests/run_client_update_tests.py --godot <godot-path>`.

The runtime runner creates an isolated project, test keys, HTTPS server and
certificate. Its fixtures never change an installed game or the production
signing keys. The GitHub workflow runs these checks on client changes.
