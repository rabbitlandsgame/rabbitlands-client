# Optional client runtime

The engine-independent Rust core owns immutable rig records and numeric planning
state. A thin official GDExtension adapter owns its lifetime on the creating main
thread. Godot owns scene nodes, animation playback and rendering. Phase 4 only
compares scheduling; legacy presentation remains authoritative.

Build from the client directory:

```powershell
python tools/build_client_runtime.py --cmake "C:/Program Files/CMake/bin/cmake.exe" --jobs 2
```

Rust 1.99.1 is pinned. The default installed `stable` alias must report that exact
version; select another installed alias with `--toolchain`. The dependency-free
core builds/tests offline. CMake fetches godot-cpp at
`507ed9d840c01a3c5b2a39af8bb4000bfac30bf5`, targeting Godot 4.7.
Generated libraries, dependencies and output manifests are ignored.

Set `RABBITLANDS_CLIENT_RUNTIME=compare` before launching the source client to
enable comparison mode, or `legacy` for the ordinary path. Default is legacy.
Pass `--client-runtime <absolute bin/client_runtime directory>` to
`tools/package_client.py` to include a verified optional payload. Its native
source digest must match the commit being exported. The package includes
comparison and legacy launchers. Omitting this option produces a native-absent
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
