# Client optimization testing on develop

The development client selects the `legacy` optimization profile on a normal
launch. All six optional paths are off: Rust mounted poses, remote presentation,
heat bolts, resource admission, prepared-content loading and lazy source objects.
Content uses the raw path with retained source objects. This profile change does
not revert the graphics or water-loading fixes.

The explicit `human-testing` profile enables those six experimental paths
together, using automatic prepared-content loading and `lazy-source-v1` static
objects. It is not a promise that every workload or graphics preset will run
faster, or a qualified recommendation for low-end hardware.

Requested features can fall back independently. An ordinary checkout without
the ignored native build or a matching prepared catalog can still play through
the legacy/raw paths. A launcher's name does not prove that an optional backend
actually ran.

## Start a test

Use a current native test package with its `app/` and `eloria-assets/` folders
kept together. Do not copy a DLL or catalog from another package into it.

- `RabbitLands.bat` uses the legacy profile unless explicitly overridden.
- `RabbitLands (optimization testing).bat` explicitly selects all six testing
  options and replaces inherited feature environment settings.
- `RabbitLands (legacy runtime).bat` explicitly disables all six families and
  selects raw content with retained source objects. Use it as the comparison
  control; close the other client first.
- The older Rust rider, comparison and heat bolt launchers start from the
  legacy profile and enable only their named pilot and its required runtime.

These named controls also disable inherited older native crowd/presentation
experiments. The ordinary launcher preserves deliberately supplied environment
settings.

Corresponding `.sh` launchers exist for Linux native packages. The desktop
release pipeline now assembles the native runtime and fresh prepared pilot on
both Windows and Linux. Its per-platform checks must succeed before signing
and uploading game parts; a package's actual diagnostics remain authoritative.

The global profile supplies defaults. A feature's command-line option overrides
its environment value, and either overrides the global profile. The global
profile's command-line option overrides `RABBITLANDS_OPTIMIZATION_PROFILE`.
For example, this opts into human testing while keeping raw content:

```powershell
.\RabbitLands.bat --optimization-profile=human-testing --prepared-content=raw
```

The launchers forward these options as Godot user arguments. When starting the
executable directly, include the separator yourself:

```powershell
.\app\RabbitLands.exe -- --optimization-profile=legacy
```

For a checkout or package made before this default change, that explicit option
or `RABBITLANDS_OPTIMIZATION_PROFILE=legacy` selects the legacy profile. After
updating, an ordinary launch needs no profile flag. To opt in through the
environment, set `RABBITLANDS_OPTIMIZATION_PROFILE=human-testing` for that launch.
These controls require no edits to user configuration or secrets.

Use the provided legacy launcher for a clean control if your shell already has
individual experimental options set: it resets all six feature environment
settings. Selecting the global legacy profile alone does not clear individual
overrides. Deliberately supplied command-line feature options can override that
launcher too.

## What to try and report

1. Log in, move through several adjacent areas, and return along the same route.
   Check arrival terrain, collision, grounding, interactive objects and loading
   pauses. Teleport between supported destinations, then return.
2. Mount and dismount, move, turn, stop, attack and cast. Check the rider, mount,
   reins, cape, equipment and other players' movements. The Rust mounted pilot
   covers supported pony, horse, tortoise, rabbit and raptor profiles; unsupported
   cases retain their ordinary path.
3. Use heat bolt during combat, including moving targets and effects ending
   while changing areas. Other spell effects can still use their ordinary path.
4. Change maps and log out while content is loading. Close the client normally.
   Report hangs, crashes, missing objects, failed interaction or persistent
   visual changes as well as frame-rate differences.
5. Repeat the same actions with the legacy launcher, using the same renderer,
   resolution, graphics settings and starting location. Restart when changing
   map texture quality; shared texture variants are fixed for that session.

Include the package commit, launcher used, renderer, graphics preset, map/position,
mount or spell, reproduction steps and whether the legacy control reproduces it.
The debug-console launcher uses the same legacy default and saves a
verbose `eloria-debug.log` beside the package. The ordinary engine log is under
the client's Godot user-data directory, normally
`%APPDATA%/Godot/app_userdata/Eloria/logs/client.log` on Windows. Review logs before
sharing them and remove account details, chat or other personal information.

Developers should inspect actual diagnostics, not just requested settings:
`client_runtime.optimization_profile` describes the resolved selections;
`client_runtime.mode`, `native_available` and `reason` report runtime fallback;
resource-admission and remote-presentation diagnostics report their actual state.
Prepared-content hits, consumed entries and miss reasons establish whether a
matching prepared resource was used. Not every requested feature is exercised
merely by reaching the login screen.

Look for the `RABBITLANDS_OPTIMIZATION_STARTUP` JSON line in the normal Godot log
or debug-console log. It separates the requested profile from actual runtime,
remote-presentation and admission state, and reports prepared catalog presence
and the selected content/node policies. Effects can correctly show inactive
until a supported flight is created. Catalog presence does not establish a
prepared hit; use later consumption diagnostics when qualifying that path.

## Prepared-content coverage and fallback

The catalog is a small exact-content pilot, not a prepared copy of the whole
world. It covers selected avatar/equipment/animation resources, an interior,
selected world chunks and a shared prototype. The original pilot includes
Whitehorn `05_01` and Four Gates `02_07`; coverage in a new package must be verified
from that package's actual catalog rather than inferred from an earlier count.

Entries must match current source bytes, engine/cook policy, texture format,
mip selection and node policy. Full/half/quarter textures can select different
entries. A renderer or device exposing different supported formats can miss the
catalog and use raw content. The fresh full-optimization release pipeline plans
the Four Gates lazy-object pilot for full, half and quarter textures. Earlier
packages may contain only the full-texture variant; inspect their actual catalog
before assuming reduced-quality coverage. It does not remove arbitrary interactive objects.

Human testing uses `auto`, so absent, changed or incompatible prepared content
falls back rather than requiring a pilot hit. If the exact lazy variant is
unavailable, it uses the ordinary raw path with retained source objects; it does
not implicitly select a different prepared node policy. `require-pilot` is a
qualification tool option, not the normal human-testing setting.

## Build and package prerequisites

The [desktop release workflow](runner-builds.md) uses `--full-optimizations` on
both native operating systems. It verifies or builds a source-matched native
payload, cooks a fresh source-derived pilot against the actual first export,
then checks the final normal PCK at all three texture qualities. Native payload
caching does not permit reuse of a stale cooked catalog. Full-feature packaging
and its proof gates remain required even though ordinary play defaults to
legacy. All-six activation and actual native availability are checked with the
explicit human-testing profile before the package can proceed to signing and
upload; the final normal-PCK guards remain required.

The cooker uses build-time software rendering: D3D12 WARP on Windows and Mesa
llvmpipe with Xvfb on Linux. Actual adapter identity, texture capabilities and
resource-buffer save/reload must pass; headless/dummy storage is insufficient.
These checks establish functional packaging, not visual equivalence, real-device
frame rates or whole-world prepared coverage. The workflow still runs
automatically on `master` pushes and manually for `master` or `develop`; pushing
to `develop` alone does not start or publish a release.

The commands below remain available for intentionally assembling and checking
explicit local payloads. An externally supplied prepared catalog still uses the
local standalone Windows path; the automated fresh-generation path supplies
the Windows/Linux release integration.

The native DLL and prepared payloads live in ignored build storage. Pushing source
to develop does not publish those binaries or automatically cook new content.
Builders must first select the exact source commit they intend to package, then
build the pinned runtime from that checkout:

```powershell
python godot-client/tools/build_client_runtime.py --out godot-client/bin/client_runtime
```

This requires the pinned Rust toolchain, CMake, C++ build tools and Godot adapter
inputs described by the build tool. Build it on the target platform. The
packager rejects a native payload built from different native source inputs or
whose descriptor/library checksums no longer match.

Create or independently validate a prepared generation against the selected
commit's actual staged assets and exported import products. The prepared planner
can describe targets and write jobs, but does not launch the cooker:

```powershell
python godot-client/tools/prepared_content_package.py --project C:/rl-builds/cook/godot-client describe-pilot
```

Cooking requires a complete marked disposable cook project, an actual exported
runtime-import snapshot and the exact engine/texture variants. Do not rerun a
historical cook setup against a new checkout or assume that an old catalog is
still valid. In particular, an earlier 44-entry catalog is not evidence of current
source or payload identity. Use the currently validated generation supplied by
the build coordinator.

Package a normal standalone client with both payloads explicitly selected:

```powershell
python godot-client/tools/package_client.py --platform windows --distribution standalone --ref FULL_COMMIT --client-runtime godot-client/bin/client_runtime --prepared-catalog C:/rl-builds/verified-cook/godot-client/prepared-content/index.json --build-dir C:/rl-builds/package-source --out C:/rl-builds/packages --no-zip
```

Replace the example paths and `FULL_COMMIT` with the current verified inputs. Do
not use `--benchmark-profile` for an ordinary human-testing package. Omit either
optional payload only when intentionally testing its fallback.

The packager validates native provenance, every selected prepared input and
payload against the actual stage, then checks the final exported PCK again.
Mismatch is a build failure; it must not be bypassed or silently replaced with
an older generation. Its ordinary headless startup check does not prove GPU
uploads or all-feature participation. Before handing a package to testers, run
the owned rendered functional checks with the options together and inspect
actual backend, prepared-content, readiness and teardown diagnostics.
