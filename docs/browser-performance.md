# Browser performance integration

The November 7, 2026 browser work starts from desktop source `eee50d2b`.
Exporting that source includes the shared size-class scenery batches, distance
and shadow budgets, generated prototype LODs, shared actor image textures,
retained local avatars, marker-light limits and map-transition work behind the
arrival curtain. Browser defaults remain Medium with half-size map textures;
existing player preferences are preserved.

## Character and mount preparation

The desktop actor preparer builds on a worker. Browser glTF parsing can still
touch renderer resources, so its adaptation queues the same required raw files
on the main thread, with at most one new file started per process frame. Actor
and mount bodies wait for their source closure to be cached. Selected mounts
are prepared before mounting, and live mount binding is queued outside packet
handlers. Source downloads remain pinned through preparation; changed outfits,
departed actors and retired sources cancel obsolete work.

The internal `browser_actor_preparation` boolean in the generated manifest
allows controlled comparisons of the same export. The normal build enables it.
`--browser-actor-preparation off` retains the earlier browser scheduling.
Diagnostics report queued/prepared files, preparation time, maximum single-file
time, failures and cancellation. One large file can still take a long frame;
this is not a hard per-frame time guarantee.

## Offline scenery detail levels

`tools/build_browser_prototype_lods.py` produces optional index-only sidecars
using the desktop WD-C5 generator and its original eligibility rule. It does
not change GLBs, materials, vertices or full-detail indices. Its CPU-only
temporary project writes under `.local`; select repository-relative prototype
GLBs with repeated `--source` arguments or a JSON list via `--sources-json`.

```powershell
python godot-client/tools/build_browser_prototype_lods.py `
  --godot C:/path/to/Godot_v4.7.2-stable_win64.exe `
  --sources-json .local/browser-performance/prototype-sources.json `
  --out .local/browser-performance/prototype-lods
```

Pass the resulting `index.json` to the browser builder's `--prototype-lods`.
The builder checks source hashes and packages each sidecar next to its source
in the same lazy asset archive. These files do not become a global startup
download. Their decoded bytes count toward that group's memory budget.

The browser validates the engine, policy, source identity, base surface data
and index bounds before applying a sidecar. Missing or invalid data retains the
existing generator. The native desktop generation path is unchanged. The
prepared Landfall/Four Gates cohort considered 442 prototypes and emitted
sidecars for 212 eligible ones (about 9 MB decoded JSON); other prototypes retain
ordinary generation.

## Build identity and hosting

The browser package includes its actual source commit and complete public Git
ancestry, using the supported custom/source identity and standalone distribution.
This permits the normal server minimum-version check without impersonating a
Windows build or weakening enforcement. Keep a full Git checkout when building.

Only the exported `site/` belongs on the launch server. Large payloads continue
to use R2 and verified local caching. See [build instructions](browser-prototype.md)
and [hosting requirements](browser-hosting.md). Runtime rendering, decoding and
animation still use the player's CPU, GPU and memory.

Local build and benchmark output is not a public release. New R2 objects,
deployment and source integration require their separate owner approvals.
