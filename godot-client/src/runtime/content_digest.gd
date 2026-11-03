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
## (`GeometryCache.world_proof`) keeps its scope; this class never sees it.
##
## ## Backends
##
## `RABBITLANDS_CONTENT_DIGEST` or `--content-digest=` picks the mode:
##
## * `auto` (default) - the fastest correct backend there is. Until the native
##   backend lands (NH-A2, `client_runtime`), that is `gdscript`.
## * `gdscript` - this file's reader. On the main thread a batch is shared
##   between the caller and short-lived `Thread`s (never the WorkerThreadPool:
##   a main-thread wait on a pool the chunk workers fill is the streaming
##   deadlock trap); on a worker thread the caller hashes alone.
## * `sequential` - exactly the old cost profile: `FileAccess.get_sha256` per
##   file in caller order, a folded file read whole and folded, no threads. For
##   A/B runs and as the kill switch.
## * `compare` - qualification of the native backend (NH-A2). Without it, the
##   `gdscript` backend runs and the reason says why.
##
## The switch is separate from `--optimization-profile`: it changes no result,
## only the time a result takes.
##
## ## Threads
##
## On the main thread a batch uses `clamp(processors / 2, 1, 4)` threads in all,
## the caller included: roughly the physical cores, while the arrival curtain
## is up. Worker-thread callers (texture workers, chunk builds) hash alone.
## `RABBITLANDS_CONTENT_DIGEST_THREADS=N` overrides the main-thread count, and
## `N,M` the worker count as well. A batch takes its files largest first when the
## rows carry a `bytes` hint (prepared catalogs record sizes) and in caller order
## otherwise: a size probe costs ~100 us a file on Windows (measured: 23 ms for
## the 218 external images of one map), which is more than the ordering buys.
## Callers that know which file is big put it first (the package digest does).
##
## ## Line endings
##
## `FOLD_CRLF` hashes a text file with every CR that is directly followed by LF
## dropped: a lone CR stays, a CR at the end of the file stays, and a CR that
## ends one read block is decided by the first byte of the next. That is the
## normalisation `MapSceneCache.package_digest` has always applied to
## `world.json`, now streaming and without a per-byte GDScript loop.

const ENVIRONMENT := "RABBITLANDS_CONTENT_DIGEST"
const ARGUMENT := "--content-digest="
const THREADS_ENVIRONMENT := "RABBITLANDS_CONTENT_DIGEST_THREADS"
const MODES := ["auto", "gdscript", "sequential", "compare"]
const DEFAULT_MODE := "auto"

## Row flags. Unknown bits are ignored.
const FOLD_CRLF := 1
const KNOWN_FLAGS := FOLD_CRLF

## Per-row status, the same codes the native backend will report.
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

const _CR := 13
const _LF := 10

static var _lock := Mutex.new()
static var _resolved := false
static var _settings: Dictionary = {}
static var _calls := 0
static var _files := 0
static var _bytes := 0
static var _us := 0
static var _parallel_calls := 0
## Native calls that fell back to GDScript (always 0 until NH-A2).
static var _fallbacks := 0

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
## Returns {requested, mode, backend, reason, threads, worker_threads}.
static func resolve(environment: Dictionary, arguments: PackedStringArray, processors: int) -> Dictionary:
	var requested := str(environment.get(ENVIRONMENT, "")).strip_edges().to_lower()
	var present := not requested.is_empty()
	for argument: String in arguments:
		if argument.begins_with(ARGUMENT):
			requested = argument.trim_prefix(ARGUMENT).strip_edges().to_lower()
			present = true
	var mode := requested if requested in MODES else DEFAULT_MODE
	var backend := "sequential" if mode == "sequential" else "gdscript"
	var reason := ""
	if present and not requested in MODES:
		reason = "invalid_mode_auto"
	elif mode == "sequential":
		reason = "sequential_selected"
	elif mode == "gdscript":
		reason = "gdscript_selected"
	elif mode == "compare":
		reason = "compare_needs_native_backend"
	else:
		reason = "native_backend_not_built"
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
		"reason": reason, "threads": threads, "worker_threads": worker_threads}

## Resolves the mode from this process's environment and command line. Main
## thread, once, before the first load (NH-A2 adds the native load and its
## self-test here). Every other entry point resolves lazily if this was not
## called, so a tool or fixture needs nothing extra.
static func initialize() -> void:
	var environment := {ENVIRONMENT: OS.get_environment(ENVIRONMENT),
		THREADS_ENVIRONMENT: OS.get_environment(THREADS_ENVIRONMENT)}
	var arguments := OS.get_cmdline_args()
	arguments.append_array(OS.get_cmdline_user_args())
	_apply(resolve(environment, arguments, OS.get_processor_count()))

## Sets the mode and thread counts directly, for fixtures and benchmarks that
## compare backends inside one process. `threads` <= 0 keeps the resolved
## main-thread count. Not for the player path.
static func configure(mode: String, threads := 0, worker_threads := 0) -> void:
	var environment := {ENVIRONMENT: mode}
	var settings := resolve(environment, PackedStringArray(), OS.get_processor_count())
	if threads > 0 and settings.backend != "sequential":
		settings.threads = clampi(threads, 1, MAX_THREAD_OVERRIDE)
	if worker_threads > 0 and settings.backend != "sequential":
		settings.worker_threads = clampi(worker_threads, 1, MAX_THREAD_OVERRIDE)
	_apply(settings)

## Forgets the resolved mode and the counters; the next call resolves again.
static func reset() -> void:
	_lock.lock()
	_resolved = false
	_settings = {}
	_calls = 0
	_files = 0
	_bytes = 0
	_us = 0
	_parallel_calls = 0
	_fallbacks = 0
	_lock.unlock()

static func _apply(settings: Dictionary) -> void:
	_lock.lock()
	_settings = settings
	_resolved = true
	_lock.unlock()
	print("content_digest stage=backend mode=%s backend=%s reason=%s threads=%d worker_threads=%d" % [
		settings.mode, settings.backend, settings.reason, int(settings.threads), int(settings.worker_threads)])

static func _current() -> Dictionary:
	_lock.lock()
	var resolved := _resolved
	var settings := _settings
	_lock.unlock()
	if not resolved:
		initialize()
		_lock.lock()
		settings = _settings
		_lock.unlock()
	return settings

## Backend, reason and counters since the last `reset`.
static func snapshot() -> Dictionary:
	var settings := _current()
	_lock.lock()
	var out := {"mode": settings.mode, "requested": settings.requested, "backend": settings.backend,
		"reason": settings.reason, "threads": settings.threads, "worker_threads": settings.worker_threads,
		"calls": _calls, "files": _files, "bytes": _bytes, "us": _us,
		"parallel_calls": _parallel_calls, "fallbacks": _fallbacks}
	_lock.unlock()
	return out

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
## files (distinct files read), bytes (bytes read by this reader; the
## `sequential` backend's FileAccess.get_sha256 rows count 0), elapsed_us,
## backend, threads}. `sizes` are optional per-row byte hints for ordering.
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
	var sequential := str(settings.backend) == "sequential"
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
	var batch := _Batch.new()
	batch.setup(job_paths, job_flags, _largest_first(job_sizes), sequential)
	var on_main := OS.get_thread_caller_id() == OS.get_main_thread_id()
	var threads: int = int(settings.threads) if on_main else int(settings.worker_threads)
	if sequential or distinct < PARALLEL_MIN_FILES:
		threads = 1
	threads = clampi(threads, 1, maxi(distinct, 1))
	var helpers: Array[Thread] = []
	for index: int in threads - 1:
		var thread := Thread.new()
		if thread.start(_drain.bind(batch)) == OK:
			helpers.append(thread)
	_drain(batch)
	for thread: Thread in helpers:
		thread.wait_to_finish()
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
	if helpers.size() > 0:
		_parallel_calls += 1
	_lock.unlock()
	return {"digests": digests, "status": status, "folded": folded, "files": distinct,
		"bytes": batch.bytes, "elapsed_us": elapsed, "backend": str(settings.backend),
		"threads": helpers.size() + 1}

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
	return [buffer_sha256(normalised), STATUS_OK, normalised.size() != raw.size(), raw.size()]

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
