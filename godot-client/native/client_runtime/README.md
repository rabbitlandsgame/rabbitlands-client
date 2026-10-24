# Optional client runtime

The engine-independent Rust core owns immutable rig records and numeric planning
state. A thin official GDExtension adapter owns its lifetime on the creating main
thread. Godot owns scene nodes, animation playback and rendering. Ordinary play
uses legacy presentation; the Moor Pony rider pilot is explicitly selectable.

Build from the client directory:

```powershell
python tools/build_client_runtime.py --cmake "C:/Program Files/CMake/bin/cmake.exe" --jobs 2
```

Rust 1.99.1 is pinned. The default installed `stable` alias must report that exact
version; select another installed alias with `--toolchain`. The dependency-free
core builds/tests offline. CMake fetches godot-cpp at
`507ed9d840c01a3c5b2a39af8bb4000bfac30bf5`, targeting Godot 4.7.
Generated libraries, dependencies and output manifests are ignored.

Set `RABBITLANDS_CLIENT_RUNTIME=rust` for the Moor Pony rider pilot, `compare`
for comparison with legacy driving presentation, or `legacy` for the ordinary
path. Default is legacy. Comparison mode copies complete poses and is deliberately
expensive; its timings do not establish live-mode performance.
Pass `--client-runtime <absolute bin/client_runtime directory>` to
`tools/package_client.py` to include a verified optional payload. Its native
source digest must match the commit being exported. The package includes
pilot, comparison and legacy launchers. Omitting this option produces a native-absent
package. Windows x86_64 is the initial validation host; other package targets
retain legacy support until their native payloads qualify.

The manifest checks API, architecture and file checksums before loading. These
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

## Moor Pony rider pilot

The complete base rider calculation includes seat fit, pelvis/spine stabilization,
both arm passes, legs, wrists, thumbs and fingers. Immutable rest transforms and
neutral local poses remain separate. Godot samples mount animation, then a late
same-frame coordinator submits all due riders together, validates complete tagged
outputs, applies each pose and calls the existing upper-body/cloth/rein finish
pass in order. No authoritative actor transform is owned by this service. Other
mount profiles retain legacy. The pilot requires API 1, x86_64 and a four-byte
engine scalar; unsupported native/engine combinations retain the ordinary path.

Epochs, generations, weak mount/skeleton/visual bindings and coordinate-frame
checks reject stale work. A failed batch falls back as a complete component.
Main closes pending work before session reset or exit. Native application guards
reject reentrant mutation and foreign-thread access; cleanup requested by a
callback is deferred until the owned application ends.

Mounted input records are `[actor, generation, rider, gait, sample_frame]` with
14 sample values per row: world seat affine (12), elapsed seconds and cycle
seconds. Gaits are idle/walk/trot/gallop (0–3). Comparison metadata is
`[actor, generation, epoch, sample_frame, offset, bone_count]`. Each numeric value
range contains visual affine (12), local position/quaternion/scale (10 per bone)
and five contact distances. Live mode keeps the full pose inside native buffers;
comparison getters are diagnostic operations.

Diagnostics separate actual applications, failed/fallback work, supported
profiles and active-tier coverage. The batch records submission, packing,
native calls and remaining Godot finish work. Submission and flush totals do
not overlap; packing/native/finish are subsets of flush. C++ conversion, Rust
solve, validation and application counters are subsets of the native call.
These cumulative counters include readiness/warmup and must not be summed with
their enclosing spans or described as sample-only measurements. Whole rendered
frame and delivered-frame measurements remain the performance decision gate.
