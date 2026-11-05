class_name ContentDigest
extends RefCounted

## SHA-256 of installed content, many files at a time, in the one format every
## manifest, cache key, prepared record and server digest already carries:
## lowercase hex, 64 characters. Nothing here changes a digest. It changes how
## fast the same digest is produced.
##
## ## Strictness
##
## Every call reads and hashes every byte it is asked about, and compares (in
## `verify`) against the expected value the caller names. Nothing is remembered
## across calls: no path, size or mtime key, no table of earlier results. The
## only sharing is inside ONE call, where the same (path, flags) row named twice
## is read once - the same file at the same instant. A load's own proof
## (`GeometryCache.world_proof`) keeps its scope; this class never sees it. The
## native backend changes none of this: it is another reader of the same bytes.
##
## ## Backends
##
## `RABBITLANDS_CONTENT_DIGEST` or `--content-digest=` picks the mode:
##
## * `auto` (default) - the fastest backend that is on by default. The native
##   backend is on by default only when `NATIVE_DEFAULT` is true, which waits for
##   its release-build A/B (owner D-NATIVE, 2026-11-04). Until then `auto`
##   hashes with `gdscript`, while `initialize()` still loads and self-tests the
##   verified native payload so `snapshot().native` reports whether it would run.
## * `native` - `RabbitLandsContentDigest` from the verified `client_runtime`
##   payload (SHA-NI where the CPU has it, a portable path otherwise), on its own
##   scoped threads. Without a verified, self-tested payload: `gdscript`, and
##   the reason names why (`native_unavailable_<code>`).
## * `gdscript` - this file's reader. On the main thread a batch is shared
##   between the caller and short-lived `Thread`s (never the WorkerThreadPool:
##   a main-thread wait on a pool the chunk workers fill is the streaming
##   deadlock trap); on a worker thread the caller hashes alone.
## * `sequential` - exactly the old cost profile: `FileAccess.get_sha256` per
##   file in caller order, a folded file read whole and folded, no threads. For
##   A/B runs and as the kill switch. `--client-safe-mode` selects it unless a
##   valid mode is set explicitly (an unknown value does not count).
## * `compare` - native qualification: every native-readable row is hashed by
##   the native backend AND by `FileAccess` (the `sequential` reader), the
##   FileAccess value is returned, and the first disagreement logs
##   `content_digest mismatch`, is counted, and turns the native backend off for
##   the rest of the process. Without a native backend it is `gdscript`.
##
## `gdscript` and `sequential` never touch the native payload: the DLL is not
## even verified. The switch is separate from `--optimization-profile`: it
## changes no result, only the time a result takes.
##
## ## The native payload
##
## `initialize()` (main thread, once at startup) loads the payload through the
## shared verified loader (`native_library.gd`, `NativeLibrary.ensure()`), then
## self-tests the digest class before any load uses it: the API number, three
## NIST vectors, the payload's own three files against the SHA-256 the loader
## checked with `FileAccess`, on two threads, and the manifest and descriptor
## CRLF-folded against this file's reader. Any failure, a missing class or a refused payload leaves
## the native backend off for the process (`snapshot().native.code`). A call that
## the native layer refuses as a whole falls back to GDScript for that call
## (`fallbacks`); a row it cannot read is read again by GDScript (`rechecked`),
## so a missing file fails exactly as it did, with the same status.
##
## The native layer opens OS paths only. `user://` and absolute paths are
## globalized; `res://` paths are globalized in editor/source runs and, in an
## exported build, only below `res://../` (the installed asset tree). Every
## other `res://` path of an exported build may live inside the PCK, so it, a
## relative path or any other scheme stays on GDScript (`native_path`).
##
## ## Threads
##
## On the main thread a batch uses `clamp(processors / 2, 1, 4)` threads in all,
## the caller included: roughly the physical cores, while the arrival curtain
## is up. Worker-thread callers (texture workers, chunk builds) hash alone.
## `RABBITLANDS_CONTENT_DIGEST_THREADS=N` overrides the main-thread count, and
## `N,M` the worker count as well. The native backend gets the same counts. A
## batch takes its files largest first when the rows carry a `bytes` hint
## (prepared catalogs record sizes) and in caller order otherwise: a size probe
## costs ~100 us a file on Windows (measured: 23 ms for the 218 external images
## of one map), which is more than the ordering buys. Callers that know which
## file is big put it first (the package digest does).
##
## ## Line endings
##
## `FOLD_CRLF` hashes a text file with every CR that is directly followed by LF
## dropped: a lone CR stays, a CR at the end of the file stays, and a CR that
## ends one read block is decided by the first byte of the next. That is the
## normalisation `MapSceneCache.package_digest` has always applied to
## `world.json`, now streaming and without a per-byte GDScript loop. The native
## reader applies the same rule.

const NativeLibrary := preload("res://src/runtime/native_library.gd")

const ENVIRONMENT := "RABBITLANDS_CONTENT_DIGEST"
const ARGUMENT := "--content-digest="
const THREADS_ENVIRONMENT := "RABBITLANDS_CONTENT_DIGEST_THREADS"
## The packaged safe-mode launcher's user argument. Without a valid explicit
## mode it selects `sequential`, so safe mode never loads the native payload for
## hashing.
const SAFE_MODE_ARGUMENT := "--client-safe-mode"
const MODES := ["auto", "native", "gdscript", "sequential", "compare"]
const DEFAULT_MODE := "auto"
## Whether `auto` hashes with a verified, self-tested native backend. Off until
## the native digest's own release-build A/B (native-hash NH-A7) qualifies it:
## owner decision D-NATIVE (2026-11-04) loads `client_runtime` for every Windows
## player, but turns each native feature on by default only after its own
## release-build A/B. Turning it on changes no digest.
const NATIVE_DEFAULT := false

## The native class and the one API version this facade speaks.
const DIGEST_CLASS := &"RabbitLandsContentDigest"
const DIGEST_API := 1

## Row flags. Unknown bits are ignored.
const FOLD_CRLF := 1
const KNOWN_FLAGS := FOLD_CRLF

## Per-row status, the same codes the native backend reports.
const STATUS_OK := 0
const STATUS_OPEN := 1
const STATUS_READ := 2
const STATUS_BAD_PATH := 3
const STATUS_INTERNAL := 4

## Read size of the streaming reader. A whole-file buffer is never allocated
## for a file larger than this. On one thread the reader is as fast as
## `FileAccess.get_sha256` (measured 32 KiB-1 MiB blocks, interleaved, best of
## 15: within 5 % either way on a 17 MB glb, 218 images and 136 geometry files;
## 256 KiB was at or near the best on all three).
const BLOCK_BYTES := 262144
const MAX_MAIN_THREADS := 4
const MAX_THREAD_OVERRIDE := 16
## A batch shares work between threads from this many distinct files. Two is
## enough for the package digest's glb + world.json to hash side by side.
const PARALLEL_MIN_FILES := 2
const EMPTY_SHA256 := "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855"
## The self-test's known answers (FIPS 180-2 examples).
const SELF_TEST_VECTORS := {
	"": "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855",
	"abc": "ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad",
	"abcdbcdecdefdefgefghfghighijhijkijkljklmklmnlmnomnopnopq":
		"248d6a61d20638b8e5c026930c3e6039a33ce45964ff2167f6ecedd419db06c1",
}
## At most this many mismatches are kept in `snapshot().mismatch_samples`.
const MISMATCH_SAMPLES := 4

const _CR := 13
const _LF := 10

static var _lock := Mutex.new()
static var _resolved := false
static var _initialized := false
static var _settings: Dictionary = {}
## The native probe of this process: {} until a probe ran (see `_probe_native`).
static var _probe: Dictionary = {}
## The self-tested native digest object, or null.
static var _native: Object = null
static var _calls := 0
static var _files := 0
static var _bytes := 0
static var _us := 0
static var _parallel_calls := 0
## Native calls refused as a whole, and native buffers refused, that GDScript
## then served.
static var _fallbacks := 0
static var _native_calls := 0
static var _native_rows := 0
## Rows the native reader could not read, read again by GDScript.
static var _rechecked := 0
static var _compared_rows := 0
static var _mismatches := 0
static var _mismatch_samples: Array = []

## One batch: the distinct files, in the order threads take them, and their
## results. Threads take the next index under the mutex and write their
## results under it too (a packed array written from two threads at once is
## not safe), so the only contention is two short critical sections per file.
class _Batch extends RefCounted:
	var paths := PackedStringArray()
	var flags := PackedInt32Array()
	var order := PackedInt32Array()
	var sequential := false
	var digests := PackedStringArray()
	var status := PackedInt32Array()
	var folded := PackedByteArray()
	var bytes := 0
	var next := 0
	var mutex := Mutex.new()

	func setup(job_paths: PackedStringArray, job_flags: PackedInt32Array, job_order: PackedInt32Array,
			in_sequence: bool) -> void:
		paths = job_paths
		flags = job_flags
		order = job_order
		sequential = in_sequence
		# A job reads as failed until a thread stores its result, so a job a
		# helper took and never finished (a script error on that thread) is
		# STATUS_INTERNAL with "", never an OK row with an empty digest.
		digests.resize(job_paths.size())
		status.resize(job_paths.size())
		status.fill(STATUS_INTERNAL)
		folded.resize(job_paths.size())
		folded.fill(0)

	## The jobs the next drain takes, from the start.
	func queue(job_order: PackedInt32Array) -> void:
		mutex.lock()
		order = job_order
		next = 0
		mutex.unlock()

	func take() -> int:
		mutex.lock()
		var at := next
		next += 1
		mutex.unlock()
		return order[at] if at < order.size() else -1

	func store(index: int, result: Array) -> void:
		mutex.lock()
		digests[index] = str(result[0])
		status[index] = int(result[1])
		folded[index] = 1 if bool(result[2]) else 0
		bytes += int(result[3])
		mutex.unlock()

# --------------------------------------------------------------------------
# Mode
# --------------------------------------------------------------------------

## Pure resolver, for fixtures and reporting. `environment` is read only.
## `native` is the probe summary (`snapshot().native` shape; {} when no probe
## ran) and `native_default` stands in for `NATIVE_DEFAULT`. Returns
## {requested, mode, backend, reason, threads, worker_threads, probe (whether
## `initialize()` probes the payload for this mode), native_wanted (whether this
## mode hashes natively when the payload is ready), safe_mode}.
static func resolve(environment: Dictionary, arguments: PackedStringArray, processors: int,
		native := {}, native_default := NATIVE_DEFAULT) -> Dictionary:
	var requested := str(environment.get(ENVIRONMENT, "")).strip_edges().to_lower()
	var present := not requested.is_empty()
	var safe_mode := false
	for argument: String in arguments:
		if argument.begins_with(ARGUMENT):
			requested = argument.trim_prefix(ARGUMENT).strip_edges().to_lower()
			present = true
		elif argument == SAFE_MODE_ARGUMENT:
			safe_mode = true
	var valid := present and requested in MODES
	var mode := requested if valid else DEFAULT_MODE
	# Safe mode keeps the pre-wave-2 reader unless a valid mode was asked for:
	# an unknown or empty value must not turn safe mode into `auto`, which
	# loads the payload.
	var safe_default := safe_mode and not valid
	if safe_default:
		mode = "sequential"
	var ready := bool(native.get("ready", false))
	var unavailable := "native_not_initialized" if native.is_empty() \
		else "native_unavailable_" + str(native.get("code", "unknown"))
	var native_backend := "native:" + str(native.get("sha256_backend", "unknown"))
	var native_wanted := mode == "native" or mode == "compare" or (mode == "auto" and native_default)
	var backend := "gdscript"
	var reason := ""
	match mode:
		"sequential":
			backend = "sequential"
			reason = "safe_mode_sequential" if safe_default else "sequential_selected"
		"gdscript":
			reason = "gdscript_selected"
		"native":
			backend = native_backend if ready else "gdscript"
			reason = "native_selected" if ready else unavailable
		"compare":
			backend = "compare" if ready else "gdscript"
			reason = "compare_selected" if ready else "compare_" + unavailable
		_:
			if ready and native_default:
				backend = native_backend
				reason = "native_default"
			else:
				reason = "native_default_off" if ready else unavailable
	if present and not valid:
		reason = "invalid_mode_safe_mode_sequential" if safe_default else "invalid_mode_auto"
	var threads := clampi(processors / 2, 1, MAX_MAIN_THREADS)
	var worker_threads := 1
	var override := str(environment.get(THREADS_ENVIRONMENT, "")).strip_edges()
	if not override.is_empty():
		var parts := override.split(",")
		if parts[0].strip_edges().is_valid_int():
			threads = clampi(int(parts[0].strip_edges()), 1, MAX_THREAD_OVERRIDE)
		if parts.size() > 1 and parts[1].strip_edges().is_valid_int():
			worker_threads = clampi(int(parts[1].strip_edges()), 1, MAX_THREAD_OVERRIDE)
	if backend == "sequential":
		threads = 1
		worker_threads = 1
	return {"requested": requested if present else DEFAULT_MODE, "mode": mode, "backend": backend,
		"reason": reason, "threads": threads, "worker_threads": worker_threads,
		"probe": mode in ["auto", "native", "compare"], "native_wanted": native_wanted, "safe_mode": safe_mode}

## Resolves the mode from this process's environment and command line and, for
## `auto`, `native` and `compare`, loads and self-tests the native payload.
## Main thread, once, at startup before the first load (`Main._ready`).
## `directory` names a payload directory other than the default one (fixtures
## and benchmarks: `NativeLibrary.load_verified(directory)` instead of
## `NativeLibrary.ensure()`). Every other entry point resolves lazily if this was
## not called; a lazy resolution probes the payload only when the mode hashes
## natively (`native`, `compare`), so a tool or fixture needs nothing extra.
static func initialize(directory := "") -> void:
	var environment := _environment()
	var arguments := _arguments()
	var settings := resolve(environment, arguments, OS.get_processor_count(), _probe_summary())
	# A backend a `compare` mismatch turned off stays off for the process.
	var disabled := str(_probe_summary().get("code", "")) == "disabled"
	if bool(settings.probe) and _on_main_thread() and not disabled:
		_probe_native(directory)
		settings = resolve(environment, arguments, OS.get_processor_count(), _probe_summary())
	elif bool(settings.native_wanted):
		settings["native_pending"] = true
	_lock.lock()
	_initialized = true
	_lock.unlock()
	_apply(settings)

## Sets the mode and thread counts directly, for fixtures and benchmarks that
## compare backends inside one process. `threads` <= 0 keeps the resolved
## main-thread count. A native mode uses the payload this process already
## probed, and probes the default payload first when none was. Not for the
## player path.
static func configure(mode: String, threads := 0, worker_threads := 0) -> void:
	var environment := {ENVIRONMENT: mode}
	var settings := resolve(environment, PackedStringArray(), OS.get_processor_count(), _probe_summary())
	if bool(settings.native_wanted) and _probe_summary().is_empty() and _on_main_thread():
		_probe_native("")
		settings = resolve(environment, PackedStringArray(), OS.get_processor_count(), _probe_summary())
	if threads > 0 and settings.backend != "sequential":
		settings.threads = clampi(threads, 1, MAX_THREAD_OVERRIDE)
	if worker_threads > 0 and settings.backend != "sequential":
		settings.worker_threads = clampi(worker_threads, 1, MAX_THREAD_OVERRIDE)
	_apply(settings)

## Forgets the resolved mode, the native probe and the counters; the next call
## resolves again. A loaded library stays loaded (NativeLibrary keeps its own
## once-per-process result).
static func reset() -> void:
	_lock.lock()
	_resolved = false
	_initialized = false
	_settings = {}
	_probe = {}
	_native = null
	_calls = 0
	_files = 0
	_bytes = 0
	_us = 0
	_parallel_calls = 0
	_fallbacks = 0
	_native_calls = 0
	_native_rows = 0
	_rechecked = 0
	_compared_rows = 0
	_mismatches = 0
	_mismatch_samples = []
	_lock.unlock()

## Fixtures only: self-tests `native` (any object with the digest class's
## methods) against the payload files `loaded` names (a `NativeLibrary.verify`
## shaped result) and makes it this process's probe, exactly as `initialize()`
## does with the real class. Call `configure()` afterwards to use it. Returns
## the probe summary.
static func adopt_native_for_tests(loaded: Dictionary, native: Object) -> Dictionary:
	_adopt(loaded, native, Time.get_ticks_usec())
	return _probe_summary()

static func _environment() -> Dictionary:
	return {ENVIRONMENT: OS.get_environment(ENVIRONMENT),
		THREADS_ENVIRONMENT: OS.get_environment(THREADS_ENVIRONMENT)}

static func _arguments() -> PackedStringArray:
	var arguments := OS.get_cmdline_args()
	arguments.append_array(OS.get_cmdline_user_args())
	return arguments

static func _on_main_thread() -> bool:
	return OS.get_thread_caller_id() == OS.get_main_thread_id()

static func _apply(settings: Dictionary) -> void:
	# One critical section from reading `_native` to publishing the settings:
	# a `compare` mismatch on another thread (`_disable_native`) either runs
	# before it, and this resolution is withdrawn, or after it, and replaces it.
	# It can never be overwritten by a resolution that still holds the object.
	_lock.lock()
	var native := _probe.duplicate(true)
	var object: Object = _native
	var backend := str(settings.backend)
	if backend.begins_with("native:") or backend == "compare":
		if object == null:
			# The probe this resolution read was withdrawn meanwhile.
			settings.backend = "gdscript"
			settings.reason = "native_withdrawn"
		else:
			settings["_native"] = object
	_settings = settings
	_resolved = true
	_lock.unlock()
	print("content_digest stage=backend mode=%s backend=%s reason=%s threads=%d worker_threads=%d native=%s sha=%s self_test=%s" % [
		settings.mode, settings.backend, settings.reason, int(settings.threads), int(settings.worker_threads),
		str(native.get("code", "not_probed")), str(native.get("sha256_backend", "none")),
		str(native.get("self_test", "not_run"))])

static func _current() -> Dictionary:
	_lock.lock()
	var resolved := _resolved
	var settings := _settings
	_lock.unlock()
	if not resolved or (bool(settings.get("native_pending", false)) and _on_main_thread()):
		_resolve_lazily()
		_lock.lock()
		settings = _settings
		_lock.unlock()
	return settings

## Resolution without `initialize()`: the mode, and the payload probe only
## when the mode hashes natively and this is the main thread (a worker thread
## cannot load an extension; the next main-thread call probes instead).
static func _resolve_lazily() -> void:
	var environment := _environment()
	var arguments := _arguments()
	var settings := resolve(environment, arguments, OS.get_processor_count(), _probe_summary())
	if bool(settings.native_wanted) and _probe_summary().is_empty():
		if _on_main_thread():
			_probe_native("")
			settings = resolve(environment, arguments, OS.get_processor_count(), _probe_summary())
		else:
			settings["native_pending"] = true
	_apply(settings)

## Backend, reason, the native probe and the counters since the last `reset`.
static func snapshot() -> Dictionary:
	var settings := _current()
	var native := _probe_summary()
	_lock.lock()
	var out := {"mode": settings.mode, "requested": settings.requested, "backend": settings.backend,
		"reason": settings.reason, "threads": settings.threads, "worker_threads": settings.worker_threads,
		"initialized": _initialized, "safe_mode": bool(settings.get("safe_mode", false)),
		"native_default": NATIVE_DEFAULT,
		"native": native if not native.is_empty() else {"probed": false},
		"calls": _calls, "files": _files, "bytes": _bytes, "us": _us,
		"parallel_calls": _parallel_calls, "fallbacks": _fallbacks,
		"native_calls": _native_calls, "native_rows": _native_rows, "rechecked": _rechecked,
		"compared_rows": _compared_rows, "mismatches": _mismatches,
		"mismatch_samples": _mismatch_samples.duplicate(true)}
	_lock.unlock()
	return out

# --------------------------------------------------------------------------
# Native payload: probe and self-test
# --------------------------------------------------------------------------

## {} when no probe ran; else {probed, code, ready, sha256_backend, cpu_sha_ni,
## digest_api, logical_cpus, self_test, self_test_us, directory, elapsed_us}
## (`elapsed_us` includes the loader's verify and load). `code` is the
## loader's code when the payload was refused (`absent`, `checksum_mismatch`,
## ...), `web`, `class_missing`, `api_mismatch`, `self_test_failed`, `disabled`
## (a `compare` mismatch) or `ready`.
static func _probe_summary() -> Dictionary:
	_lock.lock()
	var out := _probe.duplicate(true)
	_lock.unlock()
	return out

## Loads (default directory: `NativeLibrary.ensure()`) and self-tests the
## payload. Main thread only. Leaves `_probe`/`_native` set either way.
static func _probe_native(directory: String) -> void:
	var began := Time.get_ticks_usec()
	if OS.has_feature("web"):
		_set_probe({"code": "web"}, null, began)
		return
	var loaded: Dictionary = NativeLibrary.ensure() if directory.is_empty() else NativeLibrary.load_verified(directory)
	if not bool(loaded.get("ok", false)):
		_set_probe({"code": str(loaded.get("code", "absent")), "directory": str(loaded.get("directory", ""))},
			null, began)
		return
	if not ClassDB.class_exists(DIGEST_CLASS) or not ClassDB.can_instantiate(DIGEST_CLASS):
		_set_probe({"code": "class_missing", "directory": str(loaded.get("directory", ""))}, null, began)
		return
	_adopt(loaded, ClassDB.instantiate(DIGEST_CLASS), began)

## API check and self-test of `native` against the payload `loaded` names.
static func _adopt(loaded: Dictionary, native: Object, began: int) -> void:
	var state := {"directory": str(loaded.get("directory", ""))}
	var info: Variant = native.call("api_info") if native != null and native.has_method("api_info") else null
	if not info is Dictionary or int((info as Dictionary).get("digest_api", -1)) != DIGEST_API:
		state.code = "api_mismatch"
		state.digest_api = int((info as Dictionary).get("digest_api", -1)) if info is Dictionary else -1
		_set_probe(state, null, began)
		return
	var details: Dictionary = info
	state.digest_api = DIGEST_API
	state.sha256_backend = str(details.get("sha256_backend", "unknown"))
	state.cpu_sha_ni = bool(details.get("cpu_sha_ni", false))
	state.logical_cpus = int(details.get("logical_cpus", 0))
	var tested := Time.get_ticks_usec()
	var failed := _self_test(native, loaded)
	state.self_test_us = Time.get_ticks_usec() - tested
	state.self_test = "passed" if failed.is_empty() else "failed:" + failed
	state.code = "ready" if failed.is_empty() else "self_test_failed"
	_set_probe(state, native if failed.is_empty() else null, began)

static func _set_probe(state: Dictionary, native: Object, began: int) -> void:
	state.probed = true
	state.ready = native != null
	if not state.has("self_test"):
		state.self_test = "not_run"
	if not state.has("sha256_backend"):
		state.sha256_backend = "none"
	state.elapsed_us = Time.get_ticks_usec() - began
	_lock.lock()
	_probe = state
	_native = native
	_lock.unlock()

## "" when `native` hashes exactly as this file does, else the failing step.
## Uses only files the loader already proved with `FileAccess.get_sha256`: the
## library (over 1 MiB, so more than one native read) and the descriptor, plus
## the manifest, hashed here with FileAccess. The manifest and the descriptor
## are then hashed CRLF-folded against `_hash_streaming`.
static func _self_test(native: Object, loaded: Dictionary) -> String:
	for input: String in SELF_TEST_VECTORS:
		if str(native.call("sha256_buffer", input.to_utf8_buffer())) != str(SELF_TEST_VECTORS[input]):
			return "vector_%d" % input.length()
	var manifest: Dictionary = loaded.get("manifest", {}) if loaded.get("manifest", {}) is Dictionary else {}
	var manifest_path := str(loaded.get("directory", "")).path_join(NativeLibrary.MANIFEST_NAME)
	var sources := PackedStringArray([str(loaded.get("library_path", "")), manifest_path,
		str(loaded.get("descriptor_path", ""))])
	var expected := PackedStringArray([str(manifest.get("library_sha256", "")), FileAccess.get_sha256(manifest_path),
		str(manifest.get("descriptor_sha256", ""))])
	var paths := PackedStringArray()
	for source: String in sources:
		paths.append(native_path(source))
	for index: int in paths.size():
		if paths[index].is_empty() or expected[index].length() != 64:
			return "payload_paths"
	var raw: Variant = native.call("sha256_files", paths, PackedInt32Array([0, 0, 0]), 2)
	if not raw is Dictionary or int((raw as Dictionary).get("result", -1)) != 0:
		return "files_refused"
	var result: Dictionary = raw
	if not result.get("digests") is PackedStringArray or (result.digests as PackedStringArray).size() != 3 \
			or not result.get("status") is PackedInt32Array or (result.status as PackedInt32Array).size() != 3:
		return "files_shape"
	for index: int in 3:
		if int(result.status[index]) != STATUS_OK or str(result.digests[index]) != expected[index]:
			return "files_digest"
	# CRLF folding on the manifest and the descriptor, against this file's
	# reader. The descriptor is LF-only in the shipped payload; the manifest is
	# CRLF when the payload was built on Windows, so the CR-dropping path runs on
	# a real payload too, not only the no-CR case.
	var folded_raw: Variant = native.call("sha256_files", PackedStringArray([paths[1], paths[2]]),
		PackedInt32Array([FOLD_CRLF, FOLD_CRLF]), 1)
	if not folded_raw is Dictionary or int((folded_raw as Dictionary).get("result", -1)) != 0:
		return "fold_refused"
	var folded: Dictionary = folded_raw
	if not folded.get("digests") is PackedStringArray or (folded.digests as PackedStringArray).size() != 2 \
			or not folded.get("status") is PackedInt32Array or (folded.status as PackedInt32Array).size() != 2 \
			or not folded.get("folded") is PackedByteArray or (folded.folded as PackedByteArray).size() != 2:
		return "fold_shape"
	for index: int in 2:
		var reference := _hash_streaming(sources[index + 1], true)
		if int(reference[1]) != STATUS_OK or int(folded.status[index]) != STATUS_OK \
				or str(folded.digests[index]) != str(reference[0]) \
				or (int(folded.folded[index]) != 0) != bool(reference[2]):
			return "fold_digest"
	return ""

## Turns the native backend off for the rest of the process (a `compare`
## mismatch). Calls already running keep the settings they read.
static func _disable_native(reason: String) -> void:
	_lock.lock()
	var already := _native == null
	_native = null
	if not _probe.is_empty():
		_probe.code = "disabled"
		_probe.ready = false
		_probe.disabled_reason = reason
	var settings := _settings.duplicate()
	_lock.unlock()
	if already and not str(settings.get("backend", "")).begins_with("native:") and settings.get("backend") != "compare":
		return
	settings.erase("_native")
	settings.backend = "gdscript"
	settings.reason = reason
	_apply(settings)

## The OS path the native reader opens for `path`, or "" when the row must stay
## on GDScript: a PCK-resident `res://` path of an exported build, a relative
## path, another scheme, or an empty path. `exported` stands in for "not an
## editor/source run" (fixtures).
static func native_path(path: String, exported := not OS.has_feature("editor")) -> String:
	if path.is_empty():
		return ""
	if path.begins_with("user://"):
		return ProjectSettings.globalize_path(path)
	if path.begins_with("res://"):
		if exported and not path.begins_with("res://../"):
			return ""
		return ProjectSettings.globalize_path(path)
	if path.find("://") >= 0:
		return ""
	return path if _os_absolute(path) else ""

static func _os_absolute(path: String) -> bool:
	if OS.get_name() != "Windows":
		return path.begins_with("/")
	if path.begins_with("//") or path.begins_with("\\\\"):
		return true
	if path.length() < 3 or path[1] != ":" or not (path[2] == "/" or path[2] == "\\"):
		return false
	var drive := path.unicode_at(0)
	return (drive >= 65 and drive <= 90) or (drive >= 97 and drive <= 122)

# --------------------------------------------------------------------------
# Single values
# --------------------------------------------------------------------------

## sha256 of one file's raw bytes; "" when it cannot be read. One file cannot
## be split between threads, so this never starts one.
static func file_sha256(path: String) -> String:
	return str(hash_files(PackedStringArray([path])).digests[0])

## sha256 of one text file with CRLF folded to LF (see `FOLD_CRLF`).
static func normalised_text_sha256(path: String) -> String:
	return str(hash_files(PackedStringArray([path]), PackedInt32Array([FOLD_CRLF])).digests[0])

## sha256 of bytes already in memory.
static func buffer_sha256(bytes: PackedByteArray) -> String:
	if bytes.is_empty():
		return EMPTY_SHA256
	var settings := _current()
	var backend := str(settings.backend)
	var native: Object = settings.get("_native")
	if native == null or not (backend.begins_with("native:") or backend == "compare"):
		return _context_sha256(bytes)
	var value := str(native.call("sha256_buffer", bytes))
	if backend == "compare":
		var reference := _context_sha256(bytes)
		_lock.lock()
		_compared_rows += 1
		_lock.unlock()
		if value != reference:
			_note_mismatch({"path": "<buffer %d bytes>" % bytes.size(), "flags": 0, "native": value,
				"reference": reference, "native_folded": false, "reference_folded": false})
		return reference
	if value.length() != 64:
		_lock.lock()
		_fallbacks += 1
		_lock.unlock()
		return _context_sha256(bytes)
	return value

static func _context_sha256(bytes: PackedByteArray) -> String:
	if bytes.is_empty():
		return EMPTY_SHA256
	var context := HashingContext.new()
	context.start(HashingContext.HASH_SHA256)
	context.update(bytes)
	return context.finish().hex_encode()

## CRLF to LF over a buffer, with the same rule as `FOLD_CRLF`. Returns the
## input itself when it holds no CR (every shipped manifest), so the common
## case copies nothing.
static func fold_crlf(raw: PackedByteArray) -> PackedByteArray:
	var at := raw.find(_CR)
	if at < 0:
		return raw
	var out := PackedByteArray()
	var size := raw.size()
	var start := 0
	while at >= 0:
		if at + 1 < size and raw[at + 1] == _LF:
			if at > start:
				out.append_array(raw.slice(start, at))
			start = at + 1
		at = raw.find(_CR, at + 1)
	if start < size:
		out.append_array(raw.slice(start))
	return out

# --------------------------------------------------------------------------
# Batches
# --------------------------------------------------------------------------

## sha256 per path, "" for a file that cannot be read. `flags` is per path
## (missing entries are 0).
static func files_sha256(paths: PackedStringArray, flags := PackedInt32Array()) -> PackedStringArray:
	return hash_files(paths, flags).digests

## The whole result of hashing a batch, per row in caller order:
## {digests (PackedStringArray, "" on failure), status (PackedInt32Array,
## STATUS_*), folded (PackedByteArray, 1 when FOLD_CRLF dropped a byte),
## files (distinct files read), bytes (bytes read by this reader and the native
## one; the `sequential` backend's FileAccess.get_sha256 rows count 0),
## elapsed_us, backend, threads, native_rows (rows the native reader served),
## rechecked (rows GDScript read again after the native reader failed them),
## fallback (the native layer refused the call), mismatches (`compare`)}.
## `sizes` are optional per-row byte hints for ordering.
static func hash_files(paths: PackedStringArray, flags := PackedInt32Array(),
		sizes := PackedInt64Array()) -> Dictionary:
	return _run(paths, flags, sizes)

## Checks rows [{path, sha256, flags?, bytes?}] in caller order. A row passes
## when its file was read and its sha256 is exactly the expected string (no
## case folding: an expected value that is not lowercase hex fails, as it did
## with `FileAccess.get_sha256(path) != expected`). Every row is hashed even
## after a failure; `first_failure` is the first failing row index (or -1), so a
## caller reports the same first reason it reported when it checked one row at
## a time. Returns the `hash_files` result plus {ok, first_failure, matches}.
static func verify(rows: Array) -> Dictionary:
	var paths := PackedStringArray()
	var flags := PackedInt32Array()
	var sizes := PackedInt64Array()
	var expected := PackedStringArray()
	for row: Variant in rows:
		var entry: Dictionary = row if row is Dictionary else {}
		paths.append(str(entry.get("path", "")))
		flags.append(int(entry.get("flags", 0)))
		sizes.append(int(entry.get("bytes", -1)))
		expected.append(str(entry.get("sha256", "")))
	var result := _run(paths, flags, sizes)
	var digests: PackedStringArray = result.digests
	var status: PackedInt32Array = result.status
	var matches := PackedByteArray()
	matches.resize(paths.size())
	var first_failure := -1
	for row: int in paths.size():
		var ok := status[row] == STATUS_OK and not digests[row].is_empty() \
			and not expected[row].is_empty() and digests[row] == expected[row]
		matches[row] = 1 if ok else 0
		if not ok and first_failure < 0:
			first_failure = row
	result["ok"] = first_failure < 0
	result["first_failure"] = first_failure
	result["matches"] = matches
	return result

static func _run(paths: PackedStringArray, flags: PackedInt32Array, sizes: PackedInt64Array) -> Dictionary:
	var began := Time.get_ticks_usec()
	var settings := _current()
	var count := paths.size()
	var backend := str(settings.backend)
	var sequential := backend == "sequential"
	var comparing := backend == "compare"
	var native: Object = settings.get("_native") if backend.begins_with("native:") or comparing else null
	# Distinct (path, flags) rows; a repeated row reads its file once.
	var row_job := PackedInt32Array()
	row_job.resize(count)
	var job_paths := PackedStringArray()
	var job_flags := PackedInt32Array()
	var job_sizes := PackedInt64Array()
	var jobs: Dictionary = {}
	for row: int in count:
		var flag := (flags[row] if row < flags.size() else 0) & KNOWN_FLAGS
		var key := "%d|%s" % [flag, paths[row]]
		var job: int = jobs.get(key, -1)
		var size: int = sizes[row] if row < sizes.size() else -1
		if job < 0:
			job = job_paths.size()
			jobs[key] = job
			job_paths.append(paths[row])
			job_flags.append(flag)
			job_sizes.append(size)
		elif size > job_sizes[job]:
			job_sizes[job] = size
		row_job[row] = job
	var distinct := job_paths.size()
	var order := _largest_first(job_sizes)
	var batch := _Batch.new()
	# `compare` returns the FileAccess (sequential reader) value of every row.
	batch.setup(job_paths, job_flags, order, sequential or comparing)
	var on_main := OS.get_thread_caller_id() == OS.get_main_thread_id()
	var threads: int = int(settings.threads) if on_main else int(settings.worker_threads)
	var report := {"native_rows": 0, "rechecked": 0, "fallback": false, "mismatches": 0, "threads": 1}
	var native_result: Dictionary = {}
	var remaining := order
	if native != null and distinct > 0:
		native_result = _native_pass(native, batch, order, threads, comparing, report)
		if not comparing:
			remaining = native_result.remaining
	var used := _gdscript_pass(batch, remaining, 1 if sequential else threads)
	report.threads = maxi(int(report.threads), used)
	if comparing and not native_result.is_empty():
		_compare_pass(batch, native_result, report)
	var digests := PackedStringArray()
	var status := PackedInt32Array()
	var folded := PackedByteArray()
	digests.resize(count)
	status.resize(count)
	folded.resize(count)
	for row: int in count:
		var job := row_job[row]
		digests[row] = batch.digests[job]
		status[row] = batch.status[job]
		folded[row] = batch.folded[job]
	var elapsed := Time.get_ticks_usec() - began
	_lock.lock()
	_calls += 1
	_files += distinct
	_bytes += batch.bytes
	_us += elapsed
	if int(report.threads) > 1:
		_parallel_calls += 1
	_lock.unlock()
	return {"digests": digests, "status": status, "folded": folded, "files": distinct,
		"bytes": batch.bytes, "elapsed_us": elapsed, "backend": backend,
		"threads": int(report.threads), "native_rows": int(report.native_rows),
		"rechecked": int(report.rechecked), "fallback": bool(report.fallback),
		"mismatches": int(report.mismatches)}

## Hashes on the caller and on `threads - 1` helper threads the jobs of
## `job_order` that `batch` still has to read. Returns the threads used.
static func _gdscript_pass(batch: _Batch, job_order: PackedInt32Array, threads: int) -> int:
	if job_order.is_empty():
		return 1
	batch.queue(job_order)
	var count := job_order.size()
	if count < PARALLEL_MIN_FILES:
		threads = 1
	threads = clampi(threads, 1, maxi(count, 1))
	var helpers: Array[Thread] = []
	for index: int in threads - 1:
		var thread := Thread.new()
		if thread.start(_drain.bind(batch)) == OK:
			helpers.append(thread)
	_drain(batch)
	for thread: Thread in helpers:
		thread.wait_to_finish()
	return helpers.size() + 1

## One native call over the jobs of `job_order` the native reader can open,
## in that order. Outside `compare` the rows it read are stored in `batch`;
## `remaining` lists the jobs GDScript still reads (other paths, rows the
## native reader failed, everything when the call was refused). In `compare`
## nothing is stored: the native rows come back for `_compare_pass`.
static func _native_pass(native: Object, batch: _Batch, job_order: PackedInt32Array, threads: int,
		comparing: bool, report: Dictionary) -> Dictionary:
	var native_jobs := PackedInt32Array()
	var native_paths := PackedStringArray()
	var native_flags := PackedInt32Array()
	var remaining := PackedInt32Array()
	for job: int in job_order:
		var mapped := native_path(batch.paths[job])
		if mapped.is_empty():
			remaining.append(job)
		else:
			native_jobs.append(job)
			native_paths.append(mapped)
			native_flags.append(batch.flags[job])
	if native_jobs.is_empty():
		return {"remaining": remaining, "jobs": native_jobs}
	var raw: Variant = native.call("sha256_files", native_paths, native_flags, clampi(threads, 1, native_jobs.size()))
	var result: Dictionary = raw if raw is Dictionary else {}
	var digests: Variant = result.get("digests")
	var status: Variant = result.get("status")
	var folded: Variant = result.get("folded")
	var usable := int(result.get("result", -1)) == 0 and digests is PackedStringArray \
		and status is PackedInt32Array and folded is PackedByteArray \
		and (digests as PackedStringArray).size() == native_jobs.size() \
		and (status as PackedInt32Array).size() == native_jobs.size() \
		and (folded as PackedByteArray).size() == native_jobs.size()
	_lock.lock()
	_native_calls += 1
	if not usable:
		_fallbacks += 1
	_lock.unlock()
	if not usable:
		report.fallback = true
		remaining.append_array(native_jobs)
		return {"remaining": remaining, "jobs": PackedInt32Array()}
	report.threads = maxi(int(report.threads), int(result.get("threads", 1)))
	var out := {"remaining": remaining, "jobs": native_jobs, "digests": digests, "status": status, "folded": folded}
	var served := 0
	var rechecked := 0
	if not comparing:
		for index: int in native_jobs.size():
			var job := native_jobs[index]
			if int(status[index]) == STATUS_OK and str(digests[index]).length() == 64:
				batch.store(job, [str(digests[index]), STATUS_OK, int(folded[index]) != 0, 0])
				served += 1
			else:
				remaining.append(job)
				rechecked += 1
		batch.mutex.lock()
		batch.bytes += int(result.get("bytes", 0))
		batch.mutex.unlock()
		out.remaining = remaining
	else:
		served = native_jobs.size()
	report.native_rows = served
	report.rechecked = rechecked
	_lock.lock()
	_native_rows += served
	_rechecked += rechecked
	_lock.unlock()
	return out

## `compare`: the native rows of `native_result` against the FileAccess values
## `batch` holds. Rows that both readers failed agree.
static func _compare_pass(batch: _Batch, native_result: Dictionary, report: Dictionary) -> void:
	var jobs: PackedInt32Array = native_result.get("jobs", PackedInt32Array())
	if jobs.is_empty():
		return
	var digests: PackedStringArray = native_result.digests
	var status: PackedInt32Array = native_result.status
	var folded: PackedByteArray = native_result.folded
	var mismatched := 0
	for index: int in jobs.size():
		var job := jobs[index]
		var native_ok := int(status[index]) == STATUS_OK
		var reference_ok := batch.status[job] == STATUS_OK
		var native_digest := str(digests[index]) if native_ok else ""
		var reference_digest := batch.digests[job] if reference_ok else ""
		var agree := native_digest == reference_digest and (not native_ok or (int(folded[index]) != 0) == (batch.folded[job] != 0))
		if not agree:
			mismatched += 1
			_note_mismatch({"path": batch.paths[job], "flags": batch.flags[job], "native": native_digest,
				"reference": reference_digest, "native_status": int(status[index]),
				"reference_status": batch.status[job], "native_folded": int(folded[index]) != 0,
				"reference_folded": batch.folded[job] != 0})
	report.mismatches = mismatched
	_lock.lock()
	_compared_rows += jobs.size()
	_lock.unlock()

static func _note_mismatch(sample: Dictionary) -> void:
	_lock.lock()
	_mismatches += 1
	if _mismatch_samples.size() < MISMATCH_SAMPLES:
		_mismatch_samples.append(sample)
	_lock.unlock()
	push_warning("content_digest mismatch %s" % JSON.stringify(sample))
	_disable_native("compare_mismatch")

## Job indices, largest hinted size first; equal or unknown sizes keep caller
## order.
static func _largest_first(sizes: PackedInt64Array) -> PackedInt32Array:
	var order := PackedInt32Array()
	var hinted := false
	for index: int in sizes.size():
		order.append(index)
		hinted = hinted or sizes[index] >= 0
	if not hinted or sizes.size() < 2:
		return order
	var keyed: Array = []
	for index: int in sizes.size():
		keyed.append([sizes[index], index])
	keyed.sort_custom(func(a: Array, b: Array) -> bool:
		return a[0] > b[0] or (a[0] == b[0] and a[1] < b[1]))
	for index: int in keyed.size():
		order[index] = int(keyed[index][1])
	return order

## Runs on the caller and on every helper thread until the batch is empty.
static func _drain(batch: _Batch) -> void:
	while true:
		var job := batch.take()
		if job < 0:
			return
		var path: String = batch.paths[job]
		var fold := (batch.flags[job] & FOLD_CRLF) != 0
		var result: Array
		if path.is_empty():
			result = ["", STATUS_BAD_PATH, false, 0]
		elif batch.sequential:
			result = _hash_sequential(path, fold)
		else:
			result = _hash_streaming(path, fold)
		batch.store(job, result)

## The old cost profile: FileAccess.get_sha256 for raw files; a folded file
## read whole and folded, as `package_digest` did. [digest, status, folded, bytes]
static func _hash_sequential(path: String, fold: bool) -> Array:
	if not fold:
		var digest := FileAccess.get_sha256(path)
		return [digest, STATUS_OK if not digest.is_empty() else STATUS_OPEN, false, 0]
	var file := FileAccess.open(path, FileAccess.READ)
	if file == null:
		return ["", STATUS_OPEN, false, 0]
	var length := file.get_length()
	var raw := file.get_buffer(length)
	file.close()
	if raw.size() != length:
		return ["", STATUS_READ, false, raw.size()]
	var normalised := fold_crlf(raw)
	return [_context_sha256(normalised), STATUS_OK, normalised.size() != raw.size(), raw.size()]

## The streaming reader: BLOCK_BYTES at a time, CRLF folded across block
## boundaries. [digest, status, folded, bytes]
static func _hash_streaming(path: String, fold: bool) -> Array:
	var file := FileAccess.open(path, FileAccess.READ)
	if file == null:
		return ["", STATUS_OPEN, false, 0]
	var length := file.get_length()
	var context := HashingContext.new()
	if context.start(HashingContext.HASH_SHA256) != OK:
		return ["", STATUS_INTERNAL, false, 0]
	var remaining := length
	var read := 0
	var pending_cr := false
	var folded := false
	while remaining > 0:
		var want := mini(remaining, BLOCK_BYTES)
		var block := file.get_buffer(want)
		read += block.size()
		if block.size() != want:
			return ["", STATUS_READ, folded, read]
		remaining -= want
		if not fold:
			context.update(block)
			continue
		var size := block.size()
		var start := 0
		if pending_cr:
			pending_cr = false
			if block[0] == _LF:
				folded = true
			else:
				context.update(PackedByteArray([_CR]))
		var at := block.find(_CR)
		while at >= 0:
			if at + 1 >= size:
				# The block's last byte: the next block decides.
				if at > start:
					context.update(block.slice(start, at))
				start = size
				pending_cr = true
				break
			if block[at + 1] == _LF:
				if at > start:
					context.update(block.slice(start, at))
				start = at + 1
				folded = true
			at = block.find(_CR, at + 1)
		if start == 0:
			context.update(block)
		elif start < size:
			context.update(block.slice(start))
	if pending_cr:
		# A CR at the end of the file is kept.
		context.update(PackedByteArray([_CR]))
	file.close()
	return [context.finish().hex_encode(), STATUS_OK, folded, read]
