# Steam builds, macOS, Steam Deck and Android

## Distribution paths

| Target | Packaging | Update owner | Current implementation |
| --- | --- | --- | --- |
| GitHub Windows | Inno Setup 6 download installer + signed game parts | Existing Rabbit Lands updater | Existing release workflow retained |
| GitHub Linux | Portable archive/download helper + signed game parts | Existing Rabbit Lands updater | Existing release workflow retained |
| Steam Windows / Linux | Complete game files in separate OS depots | Steam | Build workflow, depot handoff and SteamPipe configuration generator |
| macOS | Universal Intel/Apple Silicon `.app`, complete assets inside bundle | Steam, or replace the whole standalone app | Native build/test workflow; Apple signing/notarization and hardware QA still required |
| Steam Deck | Native Linux Steam depot, with Windows/Proton as a test alternative | Steam | Needs controls, UI, performance and hardware work below |
| Android | Signed ARM64 AAB + mobile asset delivery | Google Play for application updates | Porting work below; no Android release is produced yet |

The embedded `distribution` field selects the update owner. It is built from a
commit, not inferred from whether Steam is running. Steam builds include no
GitHub updater, update payload or download installer. They keep the real client
commit, full ancestry and public key. The server can still enforce compatibility.
Old GitHub identities without this field retain the existing updater behavior.
No Steamworks SDK integration, Steam login, achievements or Cloud is implied.

## Build through GitHub Actions

After this workflow is present on the default branch:

1. Open the repository **Actions** tab and choose **Build Steam depots and macOS
   tests** (`.github/workflows/store-build.yml`).
2. Choose **Run workflow**, select the branch (normally a tested `master`, or
   `develop` for testing), then choose `all` + `steam` for three native jobs.
   Choose `macos` + `standalone` for a manually replaced Mac test app.
3. Wait for the selected jobs to succeed. Each job checks out the same exact
   workflow commit; builds cannot use uncommitted local assets.
4. Download the `depot-steam-windows-<commit>`, `depot-steam-linux-<commit>` and,
   optionally, `depot-steam-macos-<commit>` artifacts. Retention is seven days.
5. Unzip each artifact into its own folder. Restore the game with Python 3.13:

   ```powershell
   python godot-client/tools/store_build.py extract --artifact C:/builds/windows-artifact --out C:/builds/windows
   python godot-client/tools/store_build.py extract --artifact C:/builds/linux-artifact --out C:/builds/linux
   ```

   Run extraction for macOS on a Mac to preserve its permissions and bundle
   links. This streams and verifies the archive parts without creating another
   full archive. Do not use the GitHub setup EXE or download helper as a depot.

This workflow has read-only repository permissions, needs no signing secret or
Steam credentials, and does not upload to Steam or change GitHub Releases.
The existing **Build desktop release** workflow continues to build the GitHub
installers automatically on `master` and through its manual trigger.

For a local native build with verified tool downloads, use a fresh tools-only
checkout as on the runner (the 14 GB check counts ignored files too):

```powershell
python godot-client/tools/store_build.py build --platform windows --distribution steam --ref HEAD --out C:/builds/steam-windows
```

Use `linux` on Linux or `macos` on a Mac. The output must be a new directory
outside both repositories. A selected commit must contain distribution support;
older game code cannot safely be relabeled as Steam-managed.
In a normal asset-authoring checkout, use `package_client.py --platform windows
--distribution steam --ref HEAD --no-zip --godot PATH_TO_GODOT` instead; it uses
the existing local tool installation and the usual detached build worktree.

## Disk use

The new workflow retains the existing 14 GB accounting limit and 2 GB reserve.
It uses separate native jobs, sparse runtime sources, hard-link staging, bounded
texture encoding, and removes its owned source worktree before archive streaming.
It writes gzip/tar directly to 256 MiB parts, never a full archive plus split copy.
The parts preserve executable permissions and macOS bundle links. Artifact upload
uses compression level zero because the parts are already compressed.

Unlike the GitHub release sink, Actions artifact parts remain locally until their
upload step. They count against the budget. A larger future build fails before
consuming the reserve; inspect `store-diagnostics-<platform>/disk-usage.json`.
The first full Mac run must establish actual import/export and archive peaks.
SteamPipe's chunk cache is deliberately outside this workflow: upload from a
separate machine/volume with room for restored depots plus the SteamPipe cache.
Do not assemble three complete depots on a 14 GB runner.

## First Steam upload

An enrolled Steamworks partner, assigned App ID and Windows/Linux depot IDs are
still required. Add macOS only after the Mac checks below. There are no assigned
IDs or stored Steam credentials in this repository.

1. In Steamworks, create one depot per supported OS, leave language unrestricted,
   add every depot to the developer/testing package and later the customer
   package, and publish the installation settings. Use a private testing branch.
2. Build and restore Windows/Linux from the **same full client commit**.
3. Generate SteamPipe preview configuration using the actual IDs:

   ```powershell
   python godot-client/tools/steam_release.py --app-id APP_ID --commit FULL_CLIENT_SHA --windows-depot WINDOWS_DEPOT_ID --windows-stage C:/builds/windows --linux-depot LINUX_DEPOT_ID --linux-stage C:/builds/linux --out C:/builds/steampipe-preview
   ```

   `APP_ID`/depot placeholders must be replaced with assigned numeric IDs. The
   command rejects GitHub builds, mixed commits, duplicate IDs, update helpers,
   private signing material and a cache/script directory inside shipped content.
   It creates `app-build.vdf`, per-depot VDFs and
   `steamworks-launch-settings.json`. It performs no upload.
4. Enter the generated launch settings under Steamworks **Installation > General
   Installation**. Windows: executable `app/RabbitLands.exe`, Working Dir `app`.
   Linux: executable `app/RabbitLands.x86_64`, Working Dir `app`. Arguments empty.
   macOS, when ready: executable `Rabbit Lands.app`, Working Dir empty.
   Keep OS restrictions on launch options and depots. Configure compatibility
   launch options separately if needed; do not launch a GitHub updater in Steam.
5. On the upload machine, install the official Steamworks ContentBuilder, then
   open SteamCMD interactively and sign in with the authorized build account.
   Complete Steam Guard interactively; do not put passwords in command lines:

   ```text
   login YOUR_BUILD_ACCOUNT
   run_app_build C:/builds/steampipe-preview/app-build.vdf
   quit
   ```

   `Preview=1` checks file mappings and produces manifests/logs without uploading
   content. Inspect them. SteamCMD can still require an authenticated session.
6. Generate a **new** configuration directory with the same arguments plus
   `--upload-config`. This sets `Preview=0` while leaving `SetLive` empty. Run that
   VDF in the authenticated SteamCMD session to upload. Neither Python command
   publishes a Steam branch.
7. In Steamworks Builds, put the complete build on the private test branch. Test
   clean installation, login, maps/characters, repair, and an update from a
   previous build on every OS. Verify that no GitHub update files are created and
   that Steam reports the game running until it exits.
8. Promote the tested complete build in Steamworks when ready. Publish the same
   compatible GitHub build before advancing any enforced server client commit.
   A server requirement newer than the public Steam build would lock Steam users
   out. Do not bypass compatibility enforcement to hide this deployment mismatch.

See Valve's [SteamPipe upload guide](https://partner.steamgames.com/doc/sdk/uploading)
and [depot setup](https://partner.steamgames.com/doc/store/application/depots).
Steam distributes content and updates without an application-side Steam API
integration. API features can be added separately after rights/plugin review.

## macOS completion and public distribution

The macOS runner uses pinned Godot 4.7.2 and its official universal template,
both S3TC/BPTC and ETC2/ASTC imports, and the existing Rabbit Lands `.icns` icon.
It exports a normal bundle, placing the PCK and loose app files in
`Contents/Resources` and map assets in `Contents/eloria-assets`. Godot 4.7 sets its
working directory to Resources before scripts run, preserving the existing
`assets/...` and `../eloria-assets` paths. It uses Godot's original universal
executable as the entry point. Asset placement uses renames, with one final PCK
and no `--main-pack`/`--path` overrides.
The completed signed bundle is launched headless, its code signature is checked
again after startup, and the archive is restored and tested after the original
stage is released. Both Intel/Apple Silicon slices are verified. This does not prove
GPU rendering, playability, or Intel/Apple Silicon hardware compatibility.

Mac builds currently omit the BC-only map sidecars; source-image fallback is
retained. Godot requires both import families for universal validation; its 4.7.2
universal Mac exporter selects desktop S3TC/BPTC products for the PCK. Measure real
GPU texture support, loading time and RAM before declaring minimum specs.
The test bundle is ad-hoc signed after all contents are finalized. It is **not a
public release installer**. Do not advertise macOS support based on this export.

To finish:

1. Run the workflow and inspect both startup logs and disk measurements. Test
   the restored bundle on Apple Silicon and Intel Macs, on a fresh user account,
   from Finder and Steam, in paths with spaces, and after moving to Applications.
2. Check rendering, sound, permissions, account creation/login, character assets,
   world maps, resizing/Retina scaling, sleep/reconnect and data persistence.
3. Obtain an Apple Developer ID Application certificate, install it in the Mac
   build machine's keychain and configure a `notarytool` keychain profile. These
   are separate from the existing RSA GitHub update key; keep all private
   certificate material and credentials out of Git and build artifacts.
4. On the Mac, sign the complete restored app and notarize/staple/assess it:

   ```sh
   python3 godot-client/tools/sign_macos.py --app '/builds/macos/Rabbit Lands.app' --identity 'Developer ID Application: YOUR REGISTERED NAME (TEAMID)' --notary-profile RabbitLands
   ```

   The script signs nested Mach-O files before the app, enables hardened runtime
   for Developer ID, waits for Apple's acceptance, staples and verifies the ticket,
   and runs Gatekeeper assessment. Steam builds receive Valve's overlay-related
   entitlements; they do not enable the Mac App Store sandbox or debug entitlement.
5. For Steam, run the VDF generator **on the Mac** with the Windows/Linux depots
   restored there, plus `--macos-depot MAC_DEPOT_ID --macos-stage /builds/macos`.
   It checks signing, stapling and Gatekeeper before including the Mac depot.
   Valve requires new Mac applications to be 64-bit and notarized. Test the Steam
   overlay and complete update flow with the production signature.
6. For standalone downloads, select `standalone` at build time, sign/notarize the
   app, then use `ditto -c -k --sequesterRsrc --keepParent 'Rabbit Lands.app'
   RabbitLands-macOS.zip` on the Mac. Test a freshly downloaded/quarantined copy
   before publishing. Updates replace the whole signed app; the GitHub updater
   must not modify bundle contents. A signed DMG can be added later.

Sources: [Godot macOS export](https://docs.godotengine.org/en/stable/tutorials/export/exporting_for_macos.html),
[Apple notarization](https://developer.apple.com/documentation/security/notarizing-macos-software-before-distribution),
[Valve macOS distribution requirements](https://partner.steamgames.com/doc/store/application/platforms).

## Steam Deck work

Use the Linux Steam depot first; there is no separate Deck installer. Test the
Windows Steam build under Proton as a fallback, and pick the better supported
default. A successful Ubuntu headless startup is not Deck validation.

1. Implement full controller navigation through login/account creation, character
   creation, movement/camera, combat targeting, inventory/storage, crafting,
   spells, quests, dialogs and settings. Current input is keyboard/mouse; this
   change does not add gamepad navigation. A Steam Input keyboard/mouse mapping
   can be a first usability experiment, not a claim of full controller support.
2. Provide correct active-input glyphs, controller focus indicators and text
   entry. Account names, passwords, character names and chat need automatic Steam
   keyboard invocation or a fully controller-operated in-game keyboard. Review a
   suitable Godot Steamworks integration before adding that API dependency.
3. Support 1280x800/1280x720 with readable/scalable UI. Valve's current minimum is
   9-pixel character height at 800p, with 12px recommended. Avoid mouse-only hover
   tooltips and tiny click targets.
4. Profile dense maps, crowds, effects and asset streaming on actual hardware.
   Choose defaults that sustain at least Valve's 30fps at 800p requirement, and
   measure memory, VRAM, frame pacing, loading and battery draw. Test Steam Linux
   Runtime, case-sensitive paths, fullscreen/windowing, audio, Wi-Fi changes and
   suspend/resume with safe network reconnection.
5. Test clean install, Steam overlay, update/repair and leaving/rejoining the
   online world. Request Valve's compatibility review when all criteria pass;
   do not claim **Verified** before Valve assigns that result.

Source: [Valve's current compatibility checklist](https://partner.steamgames.com/doc/steamhardware/compat).

## Android work

Android is a client port, not another desktop export preset. The current loose
desktop paths and BC-only texture cache cannot simply be placed inside an APK.

1. Build a small ARM64 development APK with Godot's Android template, OpenJDK 17
   and the matching Android SDK/Gradle toolchain. Establish renderer/device targets
   first (Mobile or Compatibility as measured), then test physical phones/tablets.
2. Introduce an asset-path layer for APK/PCK resources and Play-delivered packs
   or app-private extracted files. Runtime GLTFDocument reads and sibling
   `../eloria-assets` paths need explicit handling. Keep source/world data out of
   APK working-directory assumptions; stream/extract only data assets, never
   replace installed application code using the desktop GitHub updater.
3. Produce ETC2/ASTC variants and a lower memory/LOD/effects profile, reduce
   desktop-sized content, and test Adreno/Mali GPUs, thermals and low-memory
   recovery. Design Play Asset Delivery around the measured content size; it
   supports install-time, fast-follow and on-demand packs. Native integration
   with the Godot asset readers is additional work.
4. Add touch movement/camera/targeting, suitable combat shortcuts, larger controls,
   scalable UI, safe areas and on-screen keyboard handling. Retain optional gamepad
   support where useful. Test keyboard focus, chat and account creation end to end.
5. Handle Android background/pause, process death, network changes/reconnect,
   audio interruption and restoring a session without duplicating game actions.
   Keep writable settings/caches in app-private storage and require only necessary
   permissions (including internet access).
6. Create a stable package ID (candidate `com.rabbitlandsgame.client`, confirm
   ownership), release upload keystore and Play App Signing configuration. Store
   signing credentials privately. Build a signed AAB for Play, with unique version
   codes; use APKs for development testing. Verify 64-bit native libraries and
   16 KB page-size compatibility of the engine and every extension.
7. As checked on 2026-10-17, Google requires **API 36 / Android 16 or higher**
   for new phone/tablet apps and updates submitted since August 31, 2026. This is
   the target API, not the minimum supported Android version. Recheck at submission;
   the generic Godot setup example still lists API 35.
8. Complete Play Console onboarding, privacy policy/Data safety, content rating,
   account deletion flow and applicable testing requirements. Provide review access
   to the online game. Add an Android distribution/platform handshake and
   store-managed update instructions on both client/server after the port works.
   This change deliberately does not label desktop files as an Android build.

Sources: [Godot Android export](https://docs.godotengine.org/en/stable/tutorials/export/exporting_for_android.html),
[Google target API rules](https://developer.android.com/google/play/requirements/target-sdk),
[Play Asset Delivery](https://developer.android.com/guide/playcore/asset-delivery),
[16 KB native compatibility](https://developer.android.com/guide/practices/page-sizes),
[Play Data safety](https://support.google.com/googleplay/android-developer/answer/10787469).
