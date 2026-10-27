# Continent streaming measurements

The October 27, 2026 investigation measures continuous travel separately from
the loading curtain. It uses the real `ContinentChunkStream`, production terrain
limits, full map-texture resolution and the default painted-ground appearance.
The machine is a Core Ultra 9 275HX with an RTX 5080 Laptop GPU, running Godot
4.7.2 Forward+/Vulkan. Fresh processes do not imply a cold operating-system or
driver cache.

## Repeated cache and sampler result

Six qualified 160 m route runs used three matched, counterbalanced pairs
(AB/BA/AB), including a fast-first pair. Both arms used accepted full-resolution
BC textures, imported ground mips, the 256 MiB territory budget, 36 m arrival
readiness and a 60 FPS limit. Controls disabled prepared collision/paving and
restored the old late-filter order; candidates enabled all three changes.

| Per-run statistic, median across three processes | Control | Candidate |
| --- | ---: | ---: |
| Worst movement frame | 103.108 ms | 56.246 ms |
| Movement p99 | 25.441 ms | 25.259 ms |
| Movement plus final drain, worst frame | 103.108 ms | 56.246 ms |
| Movement plus final drain, p99 | 25.441 ms | 25.319 ms |
| Loading-curtain wall time | 3.607 s | 3.314 s |
| Final drain wall time | 87.744 ms | 186.511 ms |
| Windows peak working set | 1.314 GB | 1.226 GB |

The median worst-frame target improved 45.5%, with no terrain misses or failed
chunks. Peak memory stayed within the declared 10% nonregression limit; maxima
across all processes were 1.977 versus 1.273 GB. Manifest residency and GPU-video
maxima were identical (268,199,602 and 423,751,776 bytes respectively). Final
draining took about 99 ms longer, within the declared 250 ms allowance.

**The original 20% p99 improvement target did not pass.** Its measured improvement
was 0.7%; the overall comparison therefore reports `performance_targets_met=false`.
The result supports shorter worst pauses, not a claim that every smoothness
target passed. Idle frames had p99 around 19.3–19.5 ms, while importer-active
frames still had a wider tail. Pipeline counters identify submitted work and do
not by themselves prove when compilation executed.

One control process had a 955 ms frame; the other controls peaked at about
100 ms. Candidate maxima were 56, 55 and 84 ms. The table uses cohort medians,
rather than presenting the cold outlier as a repeatable 94% improvement.

A separate actual-Main 35 m pair retained its deferred surface and season
listeners. Worst movement frames were 1,321 versus 59 ms, but p99 was 28.38
versus 30.05 ms. This single pair qualifies that integration path and does not
establish a p99 benefit. The default-mode smoke omitted all three feature
overrides and confirmed prepared hits, grounded actors, active season work,
drained queues and clean resource teardown. The fixture used one capsule actor,
12 generic objects and four markers; it is not a crowded live-world benchmark.

## What caused the pauses

Long pauses occurred while a detached loader read mesh arrays back from the
rendering server. Moving that work to a worker did not prevent a renderer
synchronization stall. Collision construction and the existing kit-paving
coverage pass both used those arrays. Scene attachment itself was usually only
one or two milliseconds in these traces.

Repeated trials also isolated a separate one-second material operation: binding
the paving mesh forced `BaseMaterial3D.get_rid()` after the loader had changed
the material's texture filter. Fine-grained timings separated that shader/RID
preparation from source validation, the mesh setter and metadata checks. A
single fast cache run was therefore insufficient evidence of a stable win.
Raw map and prototype imports now set the existing final anisotropic filter
before first mesh materialization. The later pass avoids setting an identical
value again. A real 08_09 comparison across 116 mesh paths retained every stored
material property and mesh array, with zero changed rendered bytes. The
diagnostic opt-out restores the old ordering and unconditional late setter.

Preparation now saves collision faces from the authoritative native shapes and
saves the existing paving mesh arrays. Runtime streaming uses the same collision
coordinates, vertex attributes and currently selected materials. A rendered
08_09 comparison with the accepted BC sidecars produced identical pixels. The
full-painted decorative-grass path retains ordinary collision construction,
because grass also consumes the triangle data that construction supplies.

Five ground-class textures now generate the same mip chains during import. Runtime
recognizes the supported imported texture header without reading GPU pixels.
The original base level and every mip are byte-identical to the prior runtime
generation. Unknown import formats retain the old fallback.

The whole-scene native background shortcut remains disabled. Earlier rendered
trials found that its publication checks increased stalls; the separate derived
caches avoid those checks while keeping the existing detached source loader.

## Options and their costs

| Option | Timing implication | Memory and disk implication |
| --- | --- | --- |
| Prepared collision and paving | Avoids the two measured mesh readbacks during streaming | Small persistent derived files; runtime resources still retire with their chunks |
| Offline ground-class mip chains | Avoids the first-use pixel readback and mip generation | 2,568,596 additional imported bytes; identical final mip pixels |
| Accepted full-resolution BC sidecars | Avoids image decoding and reduces texture uploads; does not eliminate scene work | Existing release packaging already ships accepted files; a development checkout needs local preparation |
| Half-resolution map textures | Uses fewer pixels and reduces texture residency | About one quarter of full-resolution upload bytes, using the same sidecar files; an appearance tradeoff |
| Larger territory memory budget | Can keep more nearby chunks resident | More memory; exploratory 512/768 MiB runs did not establish a repeatable timing advantage |
| Delay between imports or a larger arrival warm-up | Can move or spread first-traversal work | Must report added arrival time and ground readiness; timing results do not imply extra disk |

The complete continent collision cache has 1,276 entries and uses 58,470,792
bytes (55.76 MiB). It covers 2,097 mesh paths and 6,810,073 triangles. Prepared
paving's 34 metadata entries and nine meshes add 677,794 bytes (0.65 MiB).
Together with the imported ground-class mips, the current-policy local cache and
imported-product disk increase is 61,717,182 bytes (58.86 MiB). This is
additional to the previously implemented geometry cache, approximately 435 MiB.
Old policy folders, encoding scratch, copied benchmark profiles and raw evidence
are excluded from this current-generation runtime total. It is not a measured
release-download delta.

The collision faces decode to 245,162,628 bytes across the 17 Landfall continent
territories. That is an inventory sum: each loader decodes its requested chunk
entry, releases its temporary face dictionary after shape construction, and
retains collision with the existing chunk lifetime. Independent loaders can
overlap; they do not keep the continent-wide inventory in RAM. The unchanged
geometry scope still contains 1,449 targets, including gauntlets, insides and
their declared underground scenery assets.

The public preparer reused all 1,449 existing geometry targets and built the
missing derived entries in 428 seconds. An explicit full verification/resume
took 182 seconds and wrote nothing. A separate 34-target paving rebuild matched
the existing metadata and payloads exactly. The completion marker was valid, so
an ordinary unchanged launch skips this full verification. These are upgrade
measurements with an existing geometry cache, not a fresh all-GLB cook time.

Landfall proper's accepted sidecars contain 135,261,365 unique payload bytes
(129.0 MiB), or 137,522,615 bytes with copies in both image pools. Four quality
failures and one unaligned image retain raw loading. These preserve the existing
package quality floors; they are not lossless image encodings. Median accepted
base-colour PSNR was 44.46 dB.

The all-territory inventory found about 588 MiB of existing matching accepted
package payloads. This is a selected set of files already shipped by packaging,
not a new release-download estimate. The 3.77 GiB decoded-image inventory is a
union across the continent, not simultaneous GPU residency. See
[local texture preparation](client-texture-preparation.md) for scope and staging
details.

## Reproducing and interpreting a run

`godot-client/tools/continent_stream_benchmark.py` drives a declared movement
route in an isolated profile. It records frame distributions, separate arrival
and settle phases, terrain probes, worker events, renderer counters and Windows
process memory. The Main-listener mode adds the real client's deferred surface
callbacks to a synthetic offline actor/object fixture. It does not simulate a
live server, a populated territory or every authored map feature.

The runner rejects missing or stale reports, changed runtime/import inputs,
engine errors including shutdown errors, and runs with no movement. It reports
Windows' peak working-set high-water mark separately from sampled memory,
manifest residency estimates and GPU counters. Logical process I/O includes
page-cache traffic and is not a physical disk measurement.

`continent_stream_benchmark_compare.py` requires at least three unique matched
pairs and counterbalanced process order. Compare per-run tails rather than
pooling all frames into one average. A 60 FPS cap imposes a frame-time floor;
shader preparation and the operating system can still produce a tail above it.
An intentional change to arrival radius is a loading-time tradeoff and must be
reported separately from a matched-radius comparison.

Exploratory recovery delays of 0, 100 and 250 ms produced movement p99 values
of 28.74, 30.15 and 31.27 ms before the early-filter correction. They did not
establish a smoother timing policy, so normal imports remain immediate. An
arrival radius of 64 m selected the same four required cells as 36 m at this
spawn; it did not test an actual increase in warmed coverage. These single
option trials are not the repeated acceptance cohort.

Two counterbalanced short pairs also tried early vertex-colour shader flags.
P99 improved by 10.3% and 2.2%, while worst frames increased in both pairs. The
additional graph/context handling was omitted from production because it did
not establish the required benefit. Its exact-property and pixel-parity checks
remain useful evidence, but correctness alone was not a reason to retain it.

An isolated startup comparison of the automatic worker pool against eight
workers used auto/8/8/auto order on this 24-thread host. Median p99 was 24.167
versus 23.962 ms, a 0.8% difference; worst-frame medians were 74.076 versus
71.816 ms. All four trials qualified, and no project, OS or GPU setting was
changed outside the ignored test overlay. The normal pool remains automatic.
A positive global worker count is literal in this engine, so an eight-worker
default would also start eight workers on a smaller CPU. These results do not
justify that broader scheduling change.

The rendered probe observed a focused, visible 1280 by 720 window at position
(0, 0), with low-processor mode disabled. The requested negative command-line
position did not make that run offscreen. The runner records observed rendering
context and frame focus rather than inferring either from launch arguments.

Generated profiles, runtime caches, texture stages and raw evidence remain in
ignored task storage. They are not repository source assets. The normal
[map preparer](client-map-geometry-cache.md) handles installation/update and
resumption of the geometry and derived caches.

Validation included all 1,276 authoritative collision comparisons and 34 paving
entries, exact 08_09 rendered parity, 60 ground-mip checks, 63 collision-cache
checks, 42 paving checks and 13 early-filter checks. Renderer-sensitive checks
also ran on Vulkan. The scope/producer planner passed 16 Python tests, benchmark
guards passed 23, and texture preparation passed 21 pure tests with one Windows
directory-symlink privilege skip. Engine logs, including shutdown, were clean.
After the rejected coverage experiment was removed, the three production runtime
files matched the qualified cohort hashes exactly and the default Main smoke
passed again.
