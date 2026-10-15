# Continent territory chunks

The continent exporter authors shared world geography, then emits named territory
packages containing independent spatial GLBs. Runtime loading boundaries are
independent of the server's named-map ownership. Legacy packages and interiors
continue through the ordinary `WorldLoader` path.

## Manifest contract

A territory retains its existing `asset`, coordinate transform, exterior frames,
gameplay metadata and full `world.glb` review export. It adds:

```json
{
  "streamingChunks": {
    "schemaVersion": "1.0",
    "coordinateSpace": "territory-local",
    "preloadDistance": 240,
    "retainDistance": 320,
    "maximumLoadedChunks": 64,
    "maximumResidentBytes": 268435456,
    "chunks": [
      {
        "id": "0_1",
        "manifest": "chunks/0_1/world.json",
        "bounds": {"min": [0, -4, 96], "max": [103, 35, 192]},
        "byteLength": 123456,
        "estimatedResidentBytes": 4194304,
        "geometryResidentBytes": 617280,
        "sharedResourceResidentBytes": {"<SHA256>": 1398102},
        "packageDigest": "<64 lowercase SHA256 characters>"
      }
    ]
  }
}
```

Each child is a regular world manifest with a unique asset ID, its own GLB and
filtered collision declarations. It must not contain another `streamingChunks`
block. Vertices and node transforms are territory-local; there is no additional
cell-origin translation at runtime. `bounds` includes the full geometry extents
of assigned buildings, trees and other overhanging objects. Navigation polygons
must belong to that chunk; a territory-wide invisible surface repeated in every
cell would produce picking and grounding outside the loaded scenery.

`packageDigest` is the existing `eloria-map-package-v1` digest of the child GLB
and normalized child JSON. Recording these hashes in the territory JSON lets the
existing client/server package digest cover the complete exported set. The child
digest is checked before its nodes enter the live scene.

Shared image resources use URI references in the GLB and matching top-level
manifest hashes:

```json
{"externalResources": {"../../../../_continent/shared-assets/example.png": "<SHA256>"}}
```

URIs resolve relative to the GLB. Parent-directory references are permitted
within `eloria-assets`; absolute paths and paths leaving that asset tree are
rejected. External bytes are verified when the individual chunk loads, including
before reading a cached child scene. The manifest hash includes the URI and
expected hash, preserving the existing package digest format. Identical external
images share a mipmapped GPU texture through a weak content-addressed pool. They
are released when the last imported user releases them.

## Runtime behavior

`WorldLoader` recognizes a chunked territory before attempting to import its
review GLB. It creates a `ContinentChunkStream` root instead. The review GLB is
hashed for the existing server digest contract, but never parsed or instantiated.
No cache of a partially loaded territory is read or written. Individual child
packages retain ordinary digest-based cache reads; proximity loading does not
write scene caches on gameplay frames.

On a cold login, teleport or preload miss, `CHANGE_MAP` arrives before the actor
packet carrying the destination position. The client initially loads metadata
only. Before first grounding the local actor, it primes chunks around that
actor's actual tile. A neighbor preload instead receives the player/camera focus
transformed into the destination's coordinate frame. It does not load the
neighbor's default spawn. A teleport within an already loaded territory also
primes its new destination before grounding unless every chunk whose bounds
cover it is resident. Bounds include overhanging props, so neighbours overlap;
one resident neighbour covering the tile does not mean its ground is loaded.
Normal movement remains asynchronous; the synchronous path handles arrival or
a missed preload before the actor can sample missing terrain. Priming imports
synchronously only the chunks the byte budget admits plus every chunk under
the arrival; framed chunks beyond the budget follow on the worker. A script
that quits the SceneTree itself (the rendered tests) therefore usually has a
worker importing when it finishes; it awaits
`ContinentChunkStream.drain_workers(tree)` before `quit()`, as the client's
own close waits for its exterior stream, because a worker still running when
the process exits crashes it at teardown and joining it would deadlock.

Each resident root selects chunks by distance to their full XZ bounds. Retention
uses a wider radius to prevent oscillation. One chunk worker per resident root
performs subsequent imports; there is no full-continent scene hidden in memory.
Count and decoded-byte estimates bound the selected set. The nearest chunk is
allowed even if it alone exceeds a configured byte budget, so an undersized
budget cannot deliberately omit the arrival ground. So is every chunk within
`FRAMED_RADIUS` (64 m) of the focus, the ground the camera frames: a single
oversize chunk must not leave its neighbours, or a second chunk under the
focus, unloaded. The byte budget trims only the lead beyond that radius.
Estimates are conservative accounting inputs, not measurements of GPU driver
allocation. Retirement debt is drained before another load is dispatched; an
already in-flight result may temporarily coexist with retiring nodes.

When `geometryResidentBytes` is supplied, selection adds that decoded geometry
estimate to the unique SHA256 entries in `sharedResourceResidentBytes`. Multiple
resident chunks referencing the same PNG consume its texture estimate once.
The exporter estimates full RGBA pixels plus mip levels from PNG dimensions.
Legacy chunks without these fields retain `estimatedResidentBytes` accounting.
The selected set is a nearest-first prefix: exceeding the budget cannot replace
the closest terrain with a distant inexpensive chunk. Retirement nodes continue
to count until their last resource is released. Accounting is per territory;
the GPU pool also shares textures between adjacent territories, so their combined
estimate remains conservative.

Chunk retirement frees a bounded number of nodes per frame. Territory retirement
pauses new work and waits by polling any existing worker before releasing its
descendants. Continuous territory adoption transfers the same root and cell
instances. Existing neighbor picking uses layer 16, while active grounding uses
layer 8; cells arriving later inherit the current ownership. Each cell also owns
an independent camera-obstruction fade index, so late-arriving trees are indexed
and retired cells release their fade resources.

Server actors, resources and combat retain existing active-territory ownership.
Clicking visible neighbor terrain preserves the exact destination tile and
follows existing surveyed crossings and authoritative movement continuations.

Scenery wildlife is owned by its actual geometry chunk. On first activation,
the territory gets an `AmbientPopulation` controller which deterministically
samples `ambientPopulation.groups` without loading models. `cell_ready` waits
through a physics boundary before finding the owned ground under each sample.
Only a successful ray against active or preview ground creates an animal; cold
terrain never substitutes the declared centre height. The animal is a child of
the hit chunk. `cell_retiring` releases its animation bookkeeping and unused
model cache, and normal chunk retirement frees the instance. Territory adoption
retains the same wildlife controller and instances. Legacy unchunked maps keep
their existing population behavior.

## Validation

The real `rendered_landscape_walk.gd` ferry proof requires `travelMode: "ferry"`
routes and an `expectedArrival` on each transition: destination map, exact
authoritative tile, and global tile centre in metres from the published manifest.
It freezes the first destination actor packet and checks it before issuing any
later movement. A later correction or walking to the expected tile cannot repair
a wrong landing. The proof also checks the loaded package identity, continent
transform, covering resident chunks, and a real active-layer collision hit owned
by the destination. Cold loads must record their first focus at the authoritative
landing; preloaded root adoption is recorded separately. The harness does not
prime chunks or place actors to satisfy these checks.

`tests/test_landscape_walk_arrival.gd` feeds real protocol bytes through the
arrival observer and covers wrong first arrivals, missing ferry assertions,
other actors, return bounces, stale placement and wrong rendered packages.

`tests/test_continent_chunks.gd` writes real independent GLBs and shared external
PNGs in an isolated user directory. Its territory review GLB is deliberately
invalid and a distant chunk is deliberately absent. This verifies that only
selected child GLBs are imported. It also covers actual arrival priming,
asynchronous replacement, node release, byte/count limits, external integrity,
actual shared image identity, neighbor picking, continuous adoption and later
preview collision ownership.

`tests/test_chunk_ambient_population.gd` uses actual translated physics terrain,
a saved model scene, cold cells, preview collision and bounded retirement to
verify deferred instantiation, grounding, resource ownership and adoption.

`tests/test_stream_cell_packages.py` reads the actual generated files for every
territory. It verifies independent imports, complete transformed prop bounds,
external PNG hashes and pixel-based resident estimates, and that summed chunk
triangles match the full territory export without loss or duplication.

The old `build_exterior_streaming.py` stops before publishing when it finds
`continent-chunks-v1` geography or new chunk manifests awaiting publication.
The canonical graph includes surveyed edge spans and visual neighbors that the
old graph builder cannot reconstruct. Rebuild and publish through
`eloria-assets/maps/nymara-regions/_continent/build_pipeline.py` instead.
The geographic audit dispatches this mode to the independent whole-continent
auditor and requires collision coverage; a partial legacy audit cannot certify
the shared world. Legacy terrain algorithm regressions use the tracked
`_continent/legacy-geography.json` fixture so their original coordinates remain
meaningful after current geography changes.

Validated alongside `test_shared_stream_cells`, `test_exterior_preloading`,
`test_exterior_retirement`, `test_exterior_streaming`,
`test_exterior_walk_continuation` and `test_resident_occluder_fade` on Godot 4.7.2.
The main application script compiles with its normal autoloads. These checks
exercise the runtime contract; full generated-continent route/performance checks
remain part of the content integration pass.
