# Optional client runtime

The engine-independent Rust core owns immutable rig records, numeric planning
state and an optional spell-flight service. A thin official GDExtension adapter
owns its lifetime on the creating main thread. Godot owns scene nodes, animation
playback and rendering. Development builds default to the experimental
`human-testing` optimization profile. The mounted, heat-bolt and remote pilots
activate when a compatible native payload is present; missing capabilities
retain their legacy fallback. See the [human-testing guide](../../../docs/client-optimization-testing.md)
for the combined profile, actual diagnostics and comparison controls.

Build from the client directory:

```powershell
python tools/build_client_runtime.py --cmake "C:/Program Files/CMake/bin/cmake.exe" --jobs 2
```

Rust 1.99.1 is pinned. The default installed `stable` alias must report that exact
version; select another installed alias with `--toolchain`. The dependency-free
core builds/tests offline. CMake fetches godot-cpp at
`507ed9d840c01a3c5b2a39af8bb4000bfac30bf5`, targeting Godot 4.7.
The build verifies the actual clean binding checkout before compilation.
Generated libraries, dependencies and output manifests are ignored.

Set `RABBITLANDS_CLIENT_RUNTIME=rust` for the mounted pilot, `compare`
for comparison with legacy driving presentation, or `legacy` for that component's
previous path. Use `--optimization-profile=legacy` without individual overrides,
or the package's legacy launcher, to restore all previous defaults. Comparison
mode copies complete poses and is deliberately
expensive; its timings do not establish live-mode performance.
Pass `--client-runtime <absolute bin/client_runtime directory>` to
`tools/package_client.py` to include a verified optional payload. Its native
source digest must match the commit being exported. The package includes
pilot, comparison and legacy launchers. Omitting this option produces a native-absent
package. Windows x86_64 is the initial validation host; other package targets
retain legacy support until their native payloads qualify.

The manifest checks API, architecture and file checksums before loading. One
GDScript loader, `src/runtime/native_library.gd`, owns these checks and the
`load_extension` call for every caller (the client runtime controller and the
mounted cape arithmetic); each caller keeps its own fallback reasons. These
are compatibility and integrity checks, not a signature or a sandbox for
untrusted libraries. No optional missing library is registered automatically.
An invalid result causes a whole-batch fallback, with no partial application.
Arbitrary native memory corruption or a process crash cannot be recovered by
GDScript. Shutdown releases the service without unloading code that may still
have live engine objects.

ABI 1 records use signed 64-bit actor/generation/epoch tags. Rig handles are
unsigned monotonically increasing values, invalidated by session reset and never
reused. Rest transforms are column-major affine basis X/Y/Z and origin (12 f64
values per bone); neutral poses are parent-local position XYZ, quaternion XYZW
and scale XYZ (10 f64 values). These are separate immutable inputs. Scheduling
input is `[id, generation, rig, tier, phase]`; output is
`[id, generation, epoch, due]`. At most 65,536 records and 1,024 bones per rig
are accepted. The adapter reuses input/output capacity; comparison diagnostics
are sampled every 60 calls and capped at 256 records. Runtime diagnostics report
requested and actual mode, fallback reason, epoch and comparison counts.

## Mounted presentation pilot

The complete base rider calculation includes seat fit, pelvis/spine stabilization,
both arm passes, legs, wrists, thumbs and fingers. Immutable rest transforms and
neutral local poses remain separate. Godot samples mount animation, then a late
same-frame coordinator submits all due riders together, validates complete tagged
outputs and applies each pose. Five explicit profiles are supported: Moor Pony,
Golden Plains Horse, Crystalback Tortoise, Giant Meadow Rabbit and Jadefeather
Raptor. Giant Rat retains legacy. No authoritative actor transform is owned by
this service. The pilot requires API 1, x86_64 and a four-byte
engine scalar; unsupported native/engine combinations retain the ordinary path.

Cached C++ upper-body sampling modifies the complete Rust base pose before one
scene commit. Existing Godot action clocks remain authoritative. Native reins
retain per-rider geometry buffers and an ArrayMesh, with the existing material
and spatial grouping. Mounted cloth reuses the existing compiled C++ capsule
and Verlet arithmetic with sampled mount contacts and flow; its packed point
and history state, rest/fabric construction and bone output remain in Godot.
This is a mixed Rust/C++ runtime, not a rewrite of every operation into Rust.
The exact shared-header bytes are included in native payload provenance.

The late coordinator is created during optional mount configuration so the first
prepared frame can finish in that frame. On the pinned official release engine,
positive bone scales use a verified complete-transform setter span. Nonpositive
scales and other engine builds retain guarded separate TRS setters. Mesh calls
retain ownership checks at each callback boundary. Cancellation is scoped to the
owned operation; it cannot prevent later riders from registering.

Epochs, generations, weak mount/skeleton/visual bindings and coordinate-frame
checks reject stale work. A failed batch falls back as a complete component.
Main closes pending work before session reset or exit. Native application guards
reject reentrant mutation and foreign-thread access; cleanup requested by a
callback is deferred until the owned application ends.

Mounted input records are `[actor, generation, rider, gait, sample_frame]` with
14 sample values per row: world seat affine (12), elapsed seconds and cycle
seconds. The presentation batch also carries action index, clip time, blend
weight, returning flag and grip weight per rider. Gaits are idle/walk/trot/gallop
(0–3). Comparison metadata is
`[actor, generation, epoch, sample_frame, offset, bone_count]`. Each numeric value
range contains visual affine (12), local position/quaternion/scale (10 per bone)
and five contact distances. Live mode keeps the full pose inside native buffers;
comparison getters are diagnostic operations.

Diagnostics separate actual applications, failed/fallback work, supported
profiles, current-submission freshness and active-tier coverage. Actual upper,
rein and mounted-cloth successes/failures are separate counters. The batch records submission, packing,
native calls and remaining Godot finish work. Submission and flush totals do
not overlap; packing/native/finish are subsets of flush. C++ conversion, Rust
solve, upper sampling, validation and application counters are subsets of the
native call. Rein time is inside application; mounted-cloth time is a later
native call inside the Godot finish pass.
These cumulative counters include readiness/warmup and must not be summed with
their enclosing spans or described as sample-only measurements. Whole rendered
frame and delivered-frame measurements remain the performance decision gate.

The Phase 5 single matched exported screen showed no complete-workload gain.
The broader mounted path remains experimental. Activation for human testing
does not establish a worthwhile benefit or qualify other target devices;
repeated rendered comparisons remain necessary.

## Optional heat-bolt family

`RABBITLANDS_RUST_EFFECTS=heat_bolt` with `RABBITLANDS_CLIENT_RUNTIME=rust`
enables the effect-2 family, powers 1–10. The core owns admission, release and
travel clocks, moving endpoints, exact-once arrival/expiry and ribbon/glow
geometry in a coarse frame batch. Godot keeps the approved impact visuals,
particles, materials, per-effect meshes and transparency sorting. Unsupported
and self/area effects retain their existing path. A native capacity limit never
drops a visual already admitted by the ordinary priority policy.

The entire numeric result is validated before publication. Epochs, generations,
weak scene bindings and callback checks protect mesh/material/tree boundaries.
An invalid batch transfers surviving effects to the existing clock exactly
once; unexpected queued deletion is distinct from normal expiry. Importer
extensions are fully registered on main before any runtime glTF workers start.

The verified DLL also includes the unchanged existing C++ flight-geometry
implementation. Both its source files participate in payload provenance, and
diagnostics distinguish the verified provider from an external extension.
The rendered comparison uses identical on-foot content and global runtime,
varying Script, `ELORIA_NATIVE_PRESENTATION=flight`, or the Rust family only.
Counters include admission, packing, validation and mesh/impact submission;
native arithmetic alone does not establish a performance benefit. The family
remains experimental despite activation in the human-testing profile;
complete-scene performance qualification remains pending.

## native_crowd kernels and reducer

The payload also compiles the `native_crowd` presentation kernels and the
actor-command reducer from `../native_crowd/src`: `NativeCapeConstraintKernel`,
`NativeWorldEffectGeometry`, `NativeCrowdReducer` and `NativeCrowdStore`, next
to the existing `NativeSpellFlightGeometry`. Their source stays in
`native_crowd/`, which also builds the benchmark extension. Every file compiled
or included from outside this directory is listed in
`tools/client_runtime_package.py` `EXTERNAL_SOURCE_INPUTS`, so the payload's
`source_digest` follows them; `tests/test_client_runtime_package.py` checks that
list against `CMakeLists.txt` and the `#include` lines.

* Registration is guarded per class. This library registers a class only when
  no other extension registered it first, and the benchmark
  `native_crowd.gdextension` does the same, so either library can load first.
  `RabbitLandsClientRuntime.runtime_info().native_crowd_providers` maps each of
  the five classes to `client_runtime`, `external` or `absent`;
  `cpp_spell_flight_provider` is unchanged.
* Registering changes no default. Each caller keeps its own opt-in:
  `ELORIA_NATIVE_PRESENTATION` (`cape`, `flight`, `world`, `both`/`1`, `all`)
  for the kernels and `ELORIA_NATIVE_CROWD=1` for AppState's reducer. When the
  payload is loaded anyway (the human-testing profile, mounted cape arithmetic),
  an opt-in now finds the classes without the benchmark extension. Making them a
  player default is a separate, owner-gated step.
* The runtime ABI stays 1; added classes are backward compatible.

Checks: `tests/test_client_runtime_crowd_kernels.gd` covers registration,
providers, unchanged defaults, the opt-ins, one call per class and the reducer
against `ActorReducer` for every command byte; `--external-crowd=` also loads
the benchmark extension, before or after the payload. The
`tests/test_client_runtime_kernels_*.gd` wrappers run the existing kernel and
reducer suites unchanged against the payload (`--runtime-dir=`,
`--expect-native=present`).

## Content digest (SHA-256)

`RabbitLandsContentDigest` (`src/client_digest.{h,cpp}` over
`core/src/digest.rs` and `digest_ffi.rs`) produces the SHA-256 digests every
manifest, cache key, prepared record and server value already carries:
lowercase hex, byte-identical to `FileAccess.get_sha256`. It changes no format;
it only makes the same digest cheaper. The `ContentDigest` facade
(`src/runtime/content_digest.gd`) is its only caller. `ContentDigest.initialize()`
loads the payload through `native_library.gd` and self-tests this class (the API
number, NIST vectors, the payload's own files against the loader's SHA-256, and
its manifest and descriptor CRLF-folded against the GDScript reader) before any
load uses it. It is used for hashing with
`--content-digest=native` or `compare`, and by `auto` once the facade's
`NATIVE_DEFAULT` is turned on after the native digest's release-build A/B.

* The block function is chosen once per process: the x86 SHA extensions
  (SHA-NI) when the CPU reports `sha`, `sse2`, `ssse3` and `sse4.1`, otherwise a
  portable FIPS 180-4 implementation. `RABBITLANDS_CONTENT_DIGEST_SHA=portable`
  forces the portable path, for measuring the no-SHA-NI cost on a SHA-NI machine.
  The core stays dependency-free and builds and tests offline.
* Files are streamed in reads of at most 1 MiB (smaller files get a buffer just
  big enough); a whole file is never held in memory. Flag 1 (`FOLD_CRLF`) hashes
  a file with every CR that is directly followed by LF dropped, deciding a CR at
  the end of one read by the next read, exactly as `ContentDigest.FOLD_CRLF`; a
  per-row `folded` result says whether any byte was dropped. Unknown flag bits
  are ignored.
* A batch runs on `threads` threads in all (1-64, the caller included):
  `std::thread::scope` helpers take rows in caller order from one atomic index,
  so the caller decides the order (largest first). It never uses the Godot
  `WorkerThreadPool` and touches no engine object, so any thread may call it;
  every method is const and the class holds no state. A helper thread that
  cannot start leaves its share to the others; a row whose hashing panics is
  status 4. Every FFI entry is wrapped in `catch_unwind`, and outputs are written
  only after the whole batch succeeded.
* Paths are absolute OS paths in UTF-8. Empty, relative, NUL-containing, longer
  than the longest Windows path, and engine paths (`res://`, `user://`) are
  status 3 without touching the file system: the caller globalizes `user://`
  and installed `res://../` paths and keeps PCK paths on `FileAccess`.
  Paths longer than 260 characters work (Rust's standard library adds the
  `\\?\` prefix).

GDScript API (results per row, in caller order):

* `api_info()` -> `{digest_api: 1, sha256_backend: "sha_ni"|"portable", cpu_sha_ni,
  logical_cpus, max_files, max_threads, max_path_bytes, read_bytes, flags: 1,
  index: {supported: false, active: false}}`
* `sha256_buffer(bytes)` -> lowercase hex
* `sha256_files(paths, flags = [], threads = 1)` -> `{result, digests ("" on failure),
  status (0 ok, 1 open, 2 read, 3 bad path, 4 internal), folded, bytes, threads,
  backend, elapsed_us}`
* `verify_files(paths, expected, flags = [], threads = 1)` -> the same plus `ok`
  (1 when the row was read and equals its expected value exactly; an empty,
  upper-case or malformed expected value never passes). Every row is hashed
  even after a failure.

`result` is 0, or 1 for a refused call (more than 1,048,576 rows, an expected
list of the wrong length); a refused call reports every row as status 4.
Nothing is remembered between calls: no path, size or modification-time key
and no table of earlier results. The Phase B BLAKE3 equivalence index is not
built; `index.supported` says so. The runtime ABI stays 1 (an added class is
backward compatible); callers gate on `ClassDB.class_exists` and
`digest_api == 1`.

Checks: `cargo test --offline --locked` (NIST vectors on both backends, SHA-NI
against portable on every length to 8 KiB and every split around block
boundaries, CRLF folding at read sizes 1-4096, empty/missing/directory/
non-ASCII/over-260-character files, batches on 1-1000 threads, FFI refusals),
`tests/test_client_runtime_digest.gd` (engine and `ContentDigest` agreement),
`tests/test_content_digest_native.gd` (the facade's native backend, self-test,
fallbacks and `compare`), `tests/integration/content_digest_compare_tour.gd`
(`compare` over 10 maps and 200 chunks) and `tools/native_digest_check.py`
(every file of an install against Python's hashlib). `cargo run --release --offline --locked --example digest_bench` is a
micro-benchmark over a list of files.

## Optional remote derived-state pilot

`RABBITLANDS_REMOTE_PRESENTATION=rust` together with
`RABBITLANDS_CLIENT_RUNTIME=rust` selects the experimental remote presentation
slice, also requested by the human-testing profile. AppState dictionaries, network messages,
local-player movement and UI remain authoritative on their existing paths.
Unsupported cinematic, charge, predicted-turn and custom-action states transfer
their complete derived history back to legacy presentation.

The ordered bridge applies touched-actor events synchronously at the existing
state boundary. It retains movement and gait histories, separate server and
arrival clocks, mounted fast-segment pacing, teleport/combat resets and body
replacement state. One native physics batch advances enrolled remote actors;
Godot validates the complete tagged result before applying it in that same
physics frame. Epochs, generations, weak scene bindings and map-frame identity
reject removed, reused or obsolete actors. A rejected result transfers surviving
state back to legacy rather than publishing a partial batch.

The ordinary AnimationGate keeps its shared group membership, accumulated delta
and manual skeleton sampling semantics. Mounted coupled clocks remain with the
mounted coordinator. Godot still samples AnimationPlayer clips and performs
scene, selection and speech updates; the remote service does not advance a
second animation clock. Diagnostics expose actual enrollment and fallback
coverage, ordered event calls, complete server/action boundaries, physics
packing/call/application and gate work. Nested timing counters are subsets of
their enclosing spans and must not be added to them.

Component parity and lifecycle checks do not establish a whole-crowd
benefit. Human-testing activation is separate from qualification through complete
rendered workloads, coverage, shutdown and repeated matched hardware comparisons.
