# Optional client runtime

The engine-independent Rust core owns immutable rig records, numeric planning
state and an optional spell-flight service. A thin official GDExtension adapter
owns its lifetime on the creating main thread. Godot owns scene nodes, animation
playback and rendering. Ordinary play uses legacy presentation; the approved
mounted and heat-bolt pilots are explicitly selectable.

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
The broader mounted path remains an opt-in experiment until repeated rendered
comparisons establish a worthwhile benefit. Source parity alone never enables
the native default or qualifies other target devices.

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
remains experimental and off by default pending complete-scene qualification.
