extends SceneTree
## NH-A2: ContentDigest's native backend. Checked here:
##
## - the mode table with a probe (`resolve`), including the safe-mode default
##   and `NATIVE_DEFAULT`;
## - which paths the native reader may open (`native_path`);
## - `gdscript` and `sequential` never verify, let alone load, the payload;
## - the self-test, per-call fallback, per-row recheck and `compare` against a
##   scripted stand-in for the native class (no payload needed);
## - a refused payload (absent, bad checksum) leaves GDScript in charge;
## - with the real payload: the probe and self-test, every digest, fold flag
##   and status equal to FileAccess on main and worker threads, verify, the
##   package digest, `compare` with 0 mismatches over real project files, and
##   the legacy optimization profile keeping legacy presentation while the
##   digest backend is native.
##
## `--runtime-dir=<absolute payload directory>` tests a payload built outside
## the project (default: `NativeLibrary.default_directory()`).
## `--expect-native=present|absent` turns an unavailable or unexpected payload
## into a failure, as in test_client_runtime.gd.

const Digest := preload("res://src/runtime/content_digest.gd")
const NativeLibrary := preload("res://src/runtime/native_library.gd")
const Controller := preload("res://src/runtime/client_runtime.gd")
const MapCache := preload("res://src/world/map_scene_cache.gd")
const DIRECTORY := "user://content-digest-native-tests"
const BLOCK := Digest.BLOCK_BYTES

var failures := 0
var _written: PackedStringArray = []
var _directories: PackedStringArray = []
var _saved_environment: Dictionary = {}

## Stands in for RabbitLandsContentDigest: the same methods and result shapes,
## computed with FileAccess, with one injectable fault.
class FakeNative extends RefCounted:
	var fault := ""
	var marker := ""
	var calls := 0
	var buffer_calls := 0

	func api_info() -> Dictionary:
		return {"digest_api": 2 if fault == "api" else 1, "sha256_backend": "fake", "cpu_sha_ni": false,
			"logical_cpus": 4}

	func sha256_buffer(bytes: PackedByteArray) -> String:
		buffer_calls += 1
		if fault == "vector":
			return "0".repeat(64)
		var context := HashingContext.new()
		context.start(HashingContext.HASH_SHA256)
		if not bytes.is_empty():
			context.update(bytes)
		var value := context.finish().hex_encode()
		return _flip(value) if fault == "buffer" else value

	func sha256_files(paths: PackedStringArray, flags: PackedInt32Array, threads: int) -> Dictionary:
		calls += 1
		var digests := PackedStringArray()
		var status := PackedInt32Array()
		var folded := PackedByteArray()
		digests.resize(paths.size())
		status.resize(paths.size())
		folded.resize(paths.size())
		var bytes := 0
		for index: int in paths.size():
			# "nofold": a reader that ignores FOLD_CRLF.
			var fold := fault != "nofold" and index < flags.size() and (flags[index] & 1) != 0
			var row := _hash(paths[index], fold)
			digests[index] = str(row[0])
			status[index] = int(row[1])
			folded[index] = 1 if bool(row[2]) else 0
			bytes += int(row[3])
			if fault == "status":
				digests[index] = ""
				status[index] = 3
			elif fault == "mismatch" and not marker.is_empty() and paths[index].contains(marker) and status[index] == 0:
				digests[index] = _flip(digests[index])
			elif fault == "fold":
				folded[index] = 1 - folded[index]
		if fault == "refuse":
			status.fill(4)
			digests.fill("")
			return {"result": 1, "digests": digests, "status": status, "folded": folded, "bytes": 0,
				"threads": 0, "backend": "fake", "elapsed_us": 0}
		return {"result": 0, "digests": digests, "status": status, "folded": folded, "bytes": bytes,
			"threads": clampi(threads, 1, maxi(paths.size(), 1)), "backend": "fake", "elapsed_us": 0}

	static func _flip(value: String) -> String:
		if value.is_empty():
			return value
		return ("1" if value[0] == "0" else "0") + value.substr(1)

	static func _hash(path: String, fold: bool) -> Array:
		var file := FileAccess.open(path, FileAccess.READ)
		if file == null:
			return ["", 1, false, 0]
		var raw := file.get_buffer(file.get_length())
		file.close()
		var used := Digest.fold_crlf(raw) if fold else raw
		var context := HashingContext.new()
		context.start(HashingContext.HASH_SHA256)
		if not used.is_empty():
			context.update(used)
		return [context.finish().hex_encode(), 0, used.size() != raw.size(), raw.size()]

func _init() -> void:
	_run.call_deferred()

func expect(ok: bool, message: String) -> bool:
	if ok:
		print("PASS: " + message)
	else:
		failures += 1
		push_error("FAIL: " + message)
	return ok

func write(name: String, bytes: PackedByteArray, directory := DIRECTORY) -> String:
	DirAccess.make_dir_recursive_absolute(directory)
	if not _directories.has(directory):
		_directories.append(directory)
	var path := directory.path_join(name)
	var file := FileAccess.open(path, FileAccess.WRITE)
	file.store_buffer(bytes)
	file.close()
	if not _written.has(path):
		_written.append(path)
	return path

static func reference_fold(raw: PackedByteArray) -> PackedByteArray:
	var out := PackedByteArray()
	for index: int in raw.size():
		if raw[index] == 13 and index + 1 < raw.size() and raw[index + 1] == 10:
			continue
		out.append(raw[index])
	return out

static func sha(bytes: PackedByteArray) -> String:
	var context := HashingContext.new()
	context.start(HashingContext.HASH_SHA256)
	if not bytes.is_empty():
		context.update(bytes)
	return context.finish().hex_encode()

static func pattern(size: int, seed_value: int) -> PackedByteArray:
	var rng := RandomNumberGenerator.new()
	rng.seed = seed_value
	var out := PackedByteArray()
	out.resize(size)
	for index: int in size:
		var pick := rng.randi_range(0, 9)
		out[index] = 13 if pick < 2 else (10 if pick < 4 else rng.randi_range(0, 255))
	return out

func _set_environment(name: String, value: String) -> void:
	if not _saved_environment.has(name):
		_saved_environment[name] = OS.get_environment(name)
	OS.set_environment(name, value)

func _restore_environment() -> void:
	for name: String in _saved_environment:
		OS.set_environment(name, str(_saved_environment[name]))
	_saved_environment.clear()

func _argument(prefix: String) -> String:
	for argument: String in OS.get_cmdline_user_args():
		if argument.begins_with(prefix):
			return argument.trim_prefix(prefix)
	return ""

func _run() -> void:
	_check_resolve()
	_check_paths()
	var fixtures := _write_fixtures()
	_check_kill_switches()
	_check_fake(fixtures)
	_check_refused_payloads()
	_check_real_payload(fixtures)
	Digest.reset()
	_restore_environment()
	for path: String in _written:
		DirAccess.remove_absolute(ProjectSettings.globalize_path(path))
	_directories.reverse()
	for directory: String in _directories:
		DirAccess.remove_absolute(ProjectSettings.globalize_path(directory))
	print("content digest native: ", failures, " failures")
	quit(failures)

# --------------------------------------------------------------------------

func _check_resolve() -> void:
	var none := PackedStringArray()
	var ready := {"probed": true, "ready": true, "code": "ready", "sha256_backend": "sha_ni"}
	var refused := {"probed": true, "ready": false, "code": "checksum_mismatch"}
	var auto_off := Digest.resolve({}, none, 8, ready, false)
	expect(auto_off.backend == "gdscript" and auto_off.reason == "native_default_off" and bool(auto_off.probe)
		and not bool(auto_off.native_wanted),
		"auto with a ready payload stays on GDScript while the native default is off (D-NATIVE)")
	var auto_on := Digest.resolve({}, none, 8, ready, true)
	expect(auto_on.backend == "native:sha_ni" and auto_on.reason == "native_default" and bool(auto_on.native_wanted),
		"auto hashes natively once the native default is on")
	expect(Digest.resolve({}, none, 8, refused, true).backend == "gdscript"
		and Digest.resolve({}, none, 8, refused, true).reason == "native_unavailable_checksum_mismatch",
		"auto names why a refused payload left GDScript in charge")
	var native := Digest.resolve({Digest.ENVIRONMENT: "native"}, none, 8, ready)
	expect(native.mode == "native" and native.backend == "native:sha_ni" and native.reason == "native_selected"
		and int(native.threads) == 4 and int(native.worker_threads) == 1, "native mode with a ready payload")
	var native_missing := Digest.resolve({Digest.ENVIRONMENT: "native"}, none, 8, {})
	expect(native_missing.backend == "gdscript" and native_missing.reason == "native_not_initialized"
		and bool(native_missing.native_wanted), "native mode before any probe hashes with GDScript and wants a probe")
	var native_refused := Digest.resolve({Digest.ENVIRONMENT: "native"}, none, 8,
		{"probed": true, "ready": false, "code": "self_test_failed"})
	expect(native_refused.backend == "gdscript" and native_refused.reason == "native_unavailable_self_test_failed",
		"native mode after a failed self-test hashes with GDScript and says so")
	var compare := Digest.resolve({Digest.ENVIRONMENT: "compare"}, none, 8, ready)
	expect(compare.backend == "compare" and compare.reason == "compare_selected", "compare with a ready payload")
	expect(Digest.resolve({Digest.ENVIRONMENT: "compare"}, none, 8, refused).reason
		== "compare_native_unavailable_checksum_mismatch", "compare without a payload names the refusal")
	for mode: String in ["gdscript", "sequential"]:
		var killed := Digest.resolve({Digest.ENVIRONMENT: mode}, none, 8, ready, true)
		expect(killed.backend == mode and not bool(killed.probe) and not bool(killed.native_wanted),
			"%s is a kill switch: no probe, no native hashing, even with a ready payload and the default on" % mode)
	var safe := Digest.resolve({}, PackedStringArray(["--client-safe-mode"]), 8, ready, true)
	expect(safe.mode == "sequential" and safe.backend == "sequential" and safe.reason == "safe_mode_sequential"
		and not bool(safe.probe) and bool(safe.safe_mode) and int(safe.threads) == 1,
		"the safe-mode launcher argument selects sequential and no probe")
	var safe_explicit := Digest.resolve({Digest.ENVIRONMENT: "gdscript"}, PackedStringArray(["--client-safe-mode"]), 8)
	expect(safe_explicit.mode == "gdscript" and bool(safe_explicit.safe_mode),
		"an explicit mode still wins over the safe-mode default")
	var safe_argument := Digest.resolve({}, PackedStringArray(["--client-safe-mode", "--content-digest=native"]), 8, ready)
	expect(safe_argument.backend == "native:sha_ni", "an explicit argument wins over the safe-mode default too")
	var safe_invalid := Digest.resolve({Digest.ENVIRONMENT: "turbo"}, PackedStringArray(["--client-safe-mode"]), 8, ready, true)
	expect(safe_invalid.mode == "sequential" and safe_invalid.backend == "sequential" and not bool(safe_invalid.probe)
		and not bool(safe_invalid.native_wanted) and safe_invalid.reason == "invalid_mode_safe_mode_sequential",
		"an unknown mode does not turn safe mode into auto: still sequential, no probe (%s)" % safe_invalid.reason)
	var safe_empty := Digest.resolve({}, PackedStringArray(["--client-safe-mode", "--content-digest="]), 8, ready, true)
	expect(safe_empty.mode == "sequential" and not bool(safe_empty.probe),
		"an empty --content-digest= keeps safe mode sequential")
	var invalid := Digest.resolve({Digest.ENVIRONMENT: "turbo"}, none, 8, ready, true)
	expect(invalid.mode == "auto" and invalid.reason == "invalid_mode_auto" and invalid.backend == "native:sha_ni",
		"an unknown mode is auto and says so")
	expect(not Digest.NATIVE_DEFAULT, "the shipped native default is off until its release-build A/B")
	expect("native" in Digest.MODES and "compare" in Digest.MODES, "native and compare are selectable modes")

func _check_paths() -> void:
	var user_path := Digest.native_path("user://a/b.bin")
	expect(user_path == ProjectSettings.globalize_path("user://a/b.bin") and not user_path.begins_with("user://"),
		"user:// is globalized")
	expect(Digest.native_path("res://data/maps/registry.json", false)
		== ProjectSettings.globalize_path("res://data/maps/registry.json"), "res:// is globalized in a source run")
	expect(Digest.native_path("res://data/maps/registry.json", true).is_empty(),
		"an exported build keeps res:// (maybe inside the PCK) on GDScript")
	expect(Digest.native_path("res://../eloria-assets/maps/x/world.json", true)
		== ProjectSettings.globalize_path("res://../eloria-assets/maps/x/world.json"),
		"an exported build globalizes the installed asset tree under res://../")
	expect(Digest.native_path("relative/file.bin").is_empty() and Digest.native_path("").is_empty()
		and Digest.native_path("uid://abc").is_empty() and Digest.native_path("http://x/y").is_empty(),
		"relative paths, other schemes and empty paths stay on GDScript")
	if OS.get_name() == "Windows":
		expect(Digest.native_path("C:/x/y.bin") == "C:/x/y.bin" and Digest.native_path("d:\\x\\y.bin") == "d:\\x\\y.bin"
			and Digest.native_path("//server/share/y.bin") == "//server/share/y.bin",
			"drive and UNC paths go to the native reader unchanged")
		expect(Digest.native_path("/rooted/no/drive").is_empty() and Digest.native_path("C:relative").is_empty()
			and Digest.native_path("1:/x").is_empty(), "drive-less rooted and drive-relative paths stay on GDScript")
	else:
		expect(Digest.native_path("/x/y.bin") == "/x/y.bin", "absolute paths go to the native reader unchanged")

func _write_fixtures() -> Dictionary:
	var rows := {
		"empty.bin": PackedByteArray(),
		"abc.txt": "abc".to_utf8_buffer(),
		"crlf.json": "{\r\n  \"a\": 1\r\n}\r\n".to_utf8_buffer(),
		"lone_cr.json": "a\rb\r".to_utf8_buffer(),
		"block_cr.json": pattern(BLOCK - 1, 3) + PackedByteArray([13, 10]) + pattern(BLOCK, 4),
		"big.bin": pattern(BLOCK * 2 + 3, 5),
		"mismatch_me.bin": pattern(3000, 6),
		"plain.json": "{\"plain\": true}\n".to_utf8_buffer(),
	}
	var out := {}
	for name: String in rows:
		out[name] = write(name, rows[name])
	return out

## Every row of `paths` against FileAccess (raw) or the per-byte fold (FOLD).
func _same_as_reference(result: Dictionary, paths: PackedStringArray, flags: PackedInt32Array) -> bool:
	for index: int in paths.size():
		var fold := index < flags.size() and (flags[index] & Digest.FOLD_CRLF) != 0
		var path := paths[index]
		var exists := not path.is_empty() and FileAccess.file_exists(path)
		var want := ""
		var want_folded := false
		if exists:
			var raw := FileAccess.get_file_as_bytes(path)
			var used := reference_fold(raw) if fold else raw
			want = sha(used)
			want_folded = used.size() != raw.size()
			if not fold and want != FileAccess.get_sha256(path):
				return false
		if str(result.digests[index]) != want or (int(result.folded[index]) != 0) != want_folded:
			print("  row %d %s: got %s/%d want %s/%s" % [index, path, str(result.digests[index]),
				int(result.folded[index]), want, str(want_folded)])
			return false
		var status := int(result.status[index])
		if exists != (status == Digest.STATUS_OK):
			return false
		if path.is_empty() and status != Digest.STATUS_BAD_PATH:
			return false
	return true

func _fixture_batch(fixtures: Dictionary) -> Array:
	var paths := PackedStringArray()
	var flags := PackedInt32Array()
	for name: String in fixtures:
		paths.append(str(fixtures[name]))
		flags.append(0)
		paths.append(str(fixtures[name]))
		flags.append(Digest.FOLD_CRLF)
	paths.append(DIRECTORY.path_join("missing.bin"))
	flags.append(0)
	paths.append(DIRECTORY)
	flags.append(0)
	paths.append("")
	flags.append(0)
	paths.append(str(fixtures["big.bin"]))
	flags.append(0)
	return [paths, flags]

func _check_kill_switches() -> void:
	for mode: String in ["gdscript", "sequential"]:
		Digest.reset()
		_set_environment(Digest.ENVIRONMENT, mode)
		var before: Dictionary = NativeLibrary.stats()
		Digest.initialize()
		var after: Dictionary = NativeLibrary.stats()
		var snap := Digest.snapshot()
		expect(int(after.verifications) == int(before.verifications) and int(after.loads) == int(before.loads)
			and snap.backend == mode and not bool((snap.native as Dictionary).get("probed", true)),
			"initialize() in %s neither verifies nor loads the payload" % mode)
	_restore_environment()
	Digest.reset()
	var lazy_before: Dictionary = NativeLibrary.stats()
	var digest := Digest.file_sha256(ProjectSettings.globalize_path("res://project.godot"))
	expect(digest == FileAccess.get_sha256("res://project.godot")
		and int(NativeLibrary.stats().verifications) == int(lazy_before.verifications),
		"a lazy auto resolution (no initialize) hashes with GDScript and never touches the payload")
	Digest.reset()

## A payload-shaped fixture directory the self-test can read: a library over
## 1 MiB, a manifest and a descriptor, with the loader's result shape.
func _fake_payload() -> Dictionary:
	var directory := DIRECTORY.path_join("fake-payload")
	var library := write("client_runtime.dll", pattern(1048576 + 4099, 11), directory)
	var descriptor := write("client_runtime.gdextension",
		"[configuration]\r\nentry_symbol = \"x\"\r\ncompatibility_minimum = \"4.7\"\n".to_utf8_buffer(), directory)
	var manifest := {"library_sha256": FileAccess.get_sha256(library),
		"descriptor_sha256": FileAccess.get_sha256(descriptor)}
	write(NativeLibrary.MANIFEST_NAME, JSON.stringify(manifest).to_utf8_buffer(), directory)
	return {"ok": true, "code": "loaded", "directory": directory, "manifest": manifest,
		"library_path": library, "descriptor_path": descriptor, "load_status": -1}

## The shipped payload's line endings: an LF-only descriptor and a CRLF
## manifest (`tools/client_runtime_package.py` writes it on Windows).
func _fake_payload_shipped_endings() -> Dictionary:
	var directory := DIRECTORY.path_join("fake-payload-shipped")
	var library := write("client_runtime.dll", pattern(1048576 + 517, 12), directory)
	var descriptor := write("client_runtime.gdextension",
		"[configuration]\nentry_symbol = \"x\"\ncompatibility_minimum = \"4.7\"\n".to_utf8_buffer(), directory)
	var manifest := {"library_sha256": FileAccess.get_sha256(library),
		"descriptor_sha256": FileAccess.get_sha256(descriptor)}
	write(NativeLibrary.MANIFEST_NAME, JSON.stringify(manifest, "  ").replace("\n", "\r\n").to_utf8_buffer(),
		directory)
	return {"ok": true, "code": "loaded", "directory": directory, "manifest": manifest,
		"library_path": library, "descriptor_path": descriptor, "load_status": -1}

func _check_fake(fixtures: Dictionary) -> void:
	var loaded := _fake_payload()
	var batch: Array = _fixture_batch(fixtures)
	var paths: PackedStringArray = batch[0]
	var flags: PackedInt32Array = batch[1]
	# Self-test failures.
	for fault: String in ["vector", "api", "fold", "nofold", "refuse", "status"]:
		Digest.reset()
		var broken := FakeNative.new()
		broken.fault = fault
		var broken_probe := Digest.adopt_native_for_tests(loaded, broken)
		Digest.configure("native", 4)
		var broken_snap := Digest.snapshot()
		var want_code := "api_mismatch" if fault == "api" else "self_test_failed"
		expect(not bool(broken_probe.ready) and str(broken_probe.code) == want_code
			and broken_snap.backend == "gdscript" and broken_snap.reason == "native_unavailable_" + want_code,
			"a stand-in failing at '%s' never serves a load (%s, %s)" % [fault, str(broken_probe.code),
				str(broken_probe.self_test)])
	var failed_vector := FakeNative.new()
	failed_vector.fault = "vector"
	Digest.reset()
	expect(str(Digest.adopt_native_for_tests(loaded, failed_vector).self_test) == "failed:vector_0",
		"the self-test names its failing step")
	# The shipped payload's endings: only its CRLF manifest exercises the fold.
	var shipped := _fake_payload_shipped_endings()
	Digest.reset()
	var shipped_probe := Digest.adopt_native_for_tests(shipped, FakeNative.new())
	expect(bool(shipped_probe.ready) and str(shipped_probe.self_test) == "passed",
		"a correct stand-in passes the self-test on an LF descriptor and a CRLF manifest")
	var no_fold := FakeNative.new()
	no_fold.fault = "nofold"
	Digest.reset()
	var no_fold_probe := Digest.adopt_native_for_tests(shipped, no_fold)
	expect(not bool(no_fold_probe.ready) and str(no_fold_probe.self_test) == "failed:fold_digest",
		"a reader that ignores FOLD_CRLF fails the self-test although the descriptor has no CR (%s)"
			% str(no_fold_probe.self_test))
	# A good stand-in.
	Digest.reset()
	var fake := FakeNative.new()
	var probe := Digest.adopt_native_for_tests(loaded, fake)
	expect(bool(probe.ready) and probe.code == "ready" and probe.self_test == "passed"
		and probe.sha256_backend == "fake" and int(probe.digest_api) == 1, "a correct stand-in passes the self-test")
	for threads: int in [1, 4]:
		Digest.configure("native", threads)
		var calls := fake.calls
		var result := Digest.hash_files(paths, flags)
		expect(_same_as_reference(result, paths, flags) and fake.calls == calls + 1
			and str(result.backend) == "native:fake" and int(result.rechecked) == 2 and not bool(result.fallback),
			"native x%d: every row equals FileAccess; one native call; the missing file and the directory are read again by GDScript (%d rechecked)"
				% [threads, int(result.rechecked)])
	var snap := Digest.snapshot()
	expect(snap.backend == "native:fake" and int(snap.native_calls) == 2 and int(snap.rechecked) == 4
		and int(snap.fallbacks) == 0 and int(snap.native_rows) > 0, "snapshot counts native calls, rows and rechecks")
	# verify on the native backend keeps strictness and the first failure.
	var good := str(fixtures["abc.txt"])
	var verified := Digest.verify([
		{"path": good, "sha256": FileAccess.get_sha256(good)},
		{"path": good, "sha256": FileAccess.get_sha256(good).to_upper()},
		{"path": DIRECTORY.path_join("missing.bin"), "sha256": FileAccess.get_sha256(good)},
		{"path": good, "sha256": ""}])
	expect(not bool(verified.ok) and int(verified.first_failure) == 1 and verified.matches == PackedByteArray([1, 0, 0, 0]),
		"native verify: exact lowercase only, every row checked, first failure in caller order")
	# Worker-thread caller.
	var worker := Thread.new()
	worker.start(func() -> Dictionary: return Digest.hash_files(paths, flags))
	var from_worker: Dictionary = worker.wait_to_finish()
	expect(_same_as_reference(from_worker, paths, flags) and int(from_worker.threads) == 1
		and str(from_worker.backend) == "native:fake", "a worker-thread caller hashes natively alone")
	# Buffers.
	var buffer_calls := fake.buffer_calls
	var bytes := pattern(5000, 9)
	expect(Digest.buffer_sha256(bytes) == sha(bytes) and fake.buffer_calls == buffer_calls + 1
		and Digest.buffer_sha256(PackedByteArray()) == Digest.EMPTY_SHA256, "buffers go native; empty stays constant")
	# The package digest is the same on every backend.
	var glb := write("pkg.glb", pattern(70000, 21))
	var manifest := write("pkg.json", "{\r\n\"a\": 1\r\n}\r\n".to_utf8_buffer())
	var plain := write("pkg_lf.json", "{\n\"a\": 1\n}\n".to_utf8_buffer())
	var native_parts := MapCache.package_digest_parts(manifest, glb)
	var native_plain := MapCache.package_digest_parts(plain, glb)
	Digest.configure("sequential")
	var sequential_parts := MapCache.package_digest_parts(manifest, glb)
	var sequential_plain := MapCache.package_digest_parts(plain, glb)
	expect(native_parts == sequential_parts and native_plain == sequential_plain
		and str(native_parts.manifest_sha256).is_empty() and not str(native_plain.manifest_sha256).is_empty(),
		"the package digest and its parts are identical on native and sequential, CRLF or LF")
	# A call the native layer refuses as a whole falls back for that call.
	Digest.configure("native", 4)
	fake.fault = "refuse"
	var before_fallbacks := int(Digest.snapshot().fallbacks)
	var refused := Digest.hash_files(paths, flags)
	expect(_same_as_reference(refused, paths, flags) and bool(refused.fallback)
		and int(Digest.snapshot().fallbacks) == before_fallbacks + 1
		and Digest.snapshot().backend == "native:fake", "a refused native call falls back to GDScript for that call only")
	# Rows the native reader cannot read are read again by GDScript.
	fake.fault = "status"
	var rechecked := Digest.hash_files(paths, flags)
	# 20 rows: one is a repeat and the empty path never reaches the native reader.
	expect(_same_as_reference(rechecked, paths, flags) and int(rechecked.rechecked) == paths.size() - 2
		and int(rechecked.native_rows) == 0, "every row the native reader failed is read again by GDScript (%d)"
			% int(rechecked.rechecked))
	fake.fault = "buffer"
	expect(Digest.buffer_sha256(bytes) != sha(bytes), "the stand-in's buffer fault is visible outside compare")
	fake.fault = ""
	# compare: FileAccess values, native cross-checked, the first mismatch turns native off.
	Digest.configure("compare", 4)
	var compared := Digest.hash_files(paths, flags)
	snap = Digest.snapshot()
	expect(_same_as_reference(compared, paths, flags) and int(compared.mismatches) == 0
		and int(snap.compared_rows) >= paths.size() - 4 and int(snap.mismatches) == 0 and snap.backend == "compare",
		"compare: FileAccess values, every native row cross-checked, 0 mismatches (%d rows)" % int(snap.compared_rows))
	fake.fault = "buffer"
	expect(Digest.buffer_sha256(bytes) == sha(bytes) and int(Digest.snapshot().mismatches) == 1
		and Digest.snapshot().backend == "gdscript" and Digest.snapshot().reason == "compare_mismatch",
		"compare: a buffer mismatch returns the HashingContext value and turns native off")
	# Re-adopt and inject a file mismatch.
	fake.fault = ""
	Digest.reset()
	Digest.adopt_native_for_tests(loaded, fake)
	Digest.configure("compare", 4)
	fake.fault = "mismatch"
	fake.marker = "mismatch_me"
	var mismatched := Digest.hash_files(paths, flags)
	snap = Digest.snapshot()
	var samples: Array = snap.mismatch_samples
	expect(_same_as_reference(mismatched, paths, flags) and int(mismatched.mismatches) == 2
		and int(snap.mismatches) == 2 and samples.size() == 2 and str(samples[0].path).contains("mismatch_me")
		and snap.backend == "gdscript" and snap.reason == "compare_mismatch"
		and str((snap.native as Dictionary).code) == "disabled",
		"compare: a file mismatch is counted and sampled, FileAccess wins, native is off for the process")
	var calls_after := fake.calls
	var later := Digest.hash_files(paths, flags)
	expect(fake.calls == calls_after and _same_as_reference(later, paths, flags) and str(later.backend) == "gdscript",
		"after a mismatch the native class is never called again")
	# An explicit `native` mode can no longer pick the disabled stand-in.
	Digest.configure("native")
	expect(Digest.snapshot().backend == "gdscript" and Digest.snapshot().reason == "native_unavailable_disabled",
		"a disabled native backend stays off for every mode")
	_set_environment(Digest.ENVIRONMENT, "native")
	var verifications := int(NativeLibrary.stats().verifications)
	Digest.initialize()
	expect(Digest.snapshot().backend == "gdscript" and str((Digest.snapshot().native as Dictionary).code) == "disabled"
		and int(NativeLibrary.stats().verifications) == verifications,
		"a later initialize() does not probe a disabled backend again")
	_restore_environment()
	Digest.reset()

## A payload directory whose manifest is correct apart from `overrides`.
func _payload_fixture(name: String, overrides: Dictionary) -> String:
	var directory := DIRECTORY.path_join(name)
	var version: Dictionary = Engine.get_version_info()
	var library := write(NativeLibrary.library_name(), pattern(4096, 31), directory)
	var descriptor := write(NativeLibrary.DESCRIPTOR_NAME, "[configuration]\n".to_utf8_buffer(), directory)
	var manifest := {"abi": NativeLibrary.ABI, "engine_major": version.major, "engine_minor": version.minor,
		"platform": NativeLibrary.platform(), "architecture": "x86_64", "library": NativeLibrary.library_name(),
		"library_sha256": FileAccess.get_sha256(library), "descriptor_sha256": FileAccess.get_sha256(descriptor)}
	manifest.merge(overrides, true)
	write(NativeLibrary.MANIFEST_NAME, JSON.stringify(manifest).to_utf8_buffer(), directory)
	return ProjectSettings.globalize_path(directory)

func _check_refused_payloads() -> void:
	_set_environment(Digest.ENVIRONMENT, "native")
	var cases := {
		"absent": ProjectSettings.globalize_path(DIRECTORY.path_join("no-payload-here")),
		"checksum_mismatch": _payload_fixture("bad-checksum", {"library_sha256": "0".repeat(64)}),
		"api_mismatch": _payload_fixture("bad-abi", {"abi": 99}),
	}
	for code: String in cases:
		Digest.reset()
		var loads := int(NativeLibrary.stats().loads)
		Digest.initialize(str(cases[code]))
		var snap := Digest.snapshot()
		expect(snap.backend == "gdscript" and snap.reason == "native_unavailable_" + code
			and str((snap.native as Dictionary).code) == code and not bool((snap.native as Dictionary).ready)
			and int(NativeLibrary.stats().loads) == loads,
			"a payload refused as %s is never loaded and leaves GDScript hashing (%s)" % [code, snap.reason])
		var path := ProjectSettings.globalize_path("res://project.godot")
		expect(Digest.file_sha256(path) == FileAccess.get_sha256(path), "...and digests stay exact (%s)" % code)
	_restore_environment()
	Digest.reset()

## Up to `limit` files below `directory` with one of `extensions`.
func _collect(directory: String, extensions: PackedStringArray, limit: int, out: PackedStringArray) -> void:
	var access := DirAccess.open(directory)
	if access == null:
		return
	access.list_dir_begin()
	var name := access.get_next()
	while not name.is_empty() and out.size() < limit:
		var path := directory.path_join(name)
		if access.current_is_dir():
			if not name.begins_with("."):
				_collect(path, extensions, limit, out)
		elif name.get_extension() in extensions:
			out.append(path)
		name = access.get_next()
	access.list_dir_end()

func _check_real_payload(fixtures: Dictionary) -> void:
	var runtime_dir := _argument("--runtime-dir=")
	var expect_native := _argument("--expect-native=")
	if OS.get_cmdline_user_args().has("--expect-native"):
		expect_native = "present"
	Digest.reset()
	_set_environment(Digest.ENVIRONMENT, "")
	var loads := int(NativeLibrary.stats().loads)
	Digest.initialize(runtime_dir)
	var snap := Digest.snapshot()
	var native: Dictionary = snap.native
	print("NOTE: real payload probe: ", JSON.stringify(native))
	expect(bool(native.get("probed", false)) and bool(snap.initialized),
		"initialize() in auto probes the payload (D-NATIVE: load for every Windows player)")
	if expect_native == "present":
		expect(bool(native.get("ready", false)), "requested native-present run has a ready, self-tested payload")
	elif expect_native == "absent":
		expect(not bool(native.get("ready", false)) and snap.backend == "gdscript",
			"requested native-absent run hashes with GDScript")
	if not bool(native.get("ready", false)):
		print("SKIP: real native checks; payload not ready (", native.get("code", ""), ")")
		Digest.reset()
		_restore_environment()
		return
	expect(native.self_test == "passed" and str(native.sha256_backend) in ["sha_ni", "portable"]
		and int(native.digest_api) == 1, "the real payload passes the self-test (%s, %d us)"
			% [native.sha256_backend, int(native.elapsed_us)])
	expect(snap.backend == ("native:" + str(native.sha256_backend) if Digest.NATIVE_DEFAULT else "gdscript")
		and snap.reason == ("native_default" if Digest.NATIVE_DEFAULT else "native_default_off"),
		"auto follows NATIVE_DEFAULT with a ready payload (%s / %s)" % [snap.backend, snap.reason])
	expect(int(NativeLibrary.stats().loads) <= loads + 1, "the probe loads the payload at most once")
	var batch: Array = _fixture_batch(fixtures)
	var paths: PackedStringArray = batch[0]
	var flags: PackedInt32Array = batch[1]
	for threads: int in [1, 4]:
		Digest.configure("native", threads)
		var result := Digest.hash_files(paths, flags)
		expect(_same_as_reference(result, paths, flags) and str(result.backend).begins_with("native:")
			and int(result.native_rows) == paths.size() - 4 and int(result.rechecked) == 2,
			"real native x%d: digests, fold flags and status equal FileAccess on every fixture row" % threads)
	var worker := Thread.new()
	worker.start(func() -> Dictionary: return Digest.hash_files(paths, flags))
	var from_worker: Dictionary = worker.wait_to_finish()
	expect(_same_as_reference(from_worker, paths, flags) and int(from_worker.native_rows) == paths.size() - 4,
		"real native from a worker thread")
	var good := str(fixtures["big.bin"])
	var verified := Digest.verify([{"path": good, "sha256": FileAccess.get_sha256(good)},
		{"path": good, "sha256": FileAccess.get_sha256(good).to_upper()}])
	expect(not bool(verified.ok) and int(verified.first_failure) == 1, "real native verify stays strict")
	var bytes := pattern(1048576 + 77, 41)
	expect(Digest.buffer_sha256(bytes) == sha(bytes), "real native buffer over 1 MiB equals HashingContext")
	var real := PackedStringArray()
	_collect("res://src", PackedStringArray(["gd"]), 240, real)
	_collect("res://data", PackedStringArray(["json"]), 360, real)
	var real_flags := PackedInt32Array()
	for path: String in real:
		real_flags.append(Digest.FOLD_CRLF if path.get_extension() == "json" else 0)
	var real_result := Digest.hash_files(real, real_flags)
	expect(real.size() >= 300 and _same_as_reference(real_result, real, real_flags),
		"%d real project files (res:// paths, json folded) equal FileAccess natively" % real.size())
	var registry := "res://data/maps/registry.json"
	var maps: Variant = JSON.parse_string(FileAccess.get_file_as_string(registry))
	var checked_package := false
	if maps is Dictionary:
		for id: Variant in (maps as Dictionary).get("maps", {}):
			var manifest_path := str((maps.maps[id] as Dictionary).get("manifest", ""))
			var manifest := WorldManifest.load_file(manifest_path)
			if manifest == null or not manifest.is_valid() or not FileAccess.file_exists(manifest.glb_path()):
				continue
			Digest.configure("native", 4)
			var native_parts := MapCache.package_digest_parts(manifest_path, manifest.glb_path())
			Digest.configure("sequential")
			var sequential_parts := MapCache.package_digest_parts(manifest_path, manifest.glb_path())
			expect(not str(native_parts.digest).is_empty() and native_parts == sequential_parts,
				"real map %s: package digest native == sequential (%s)" % [str(id), str(native_parts.digest).left(12)])
			checked_package = true
			break
	expect(checked_package, "a real map package was digested")
	Digest.configure("compare", 4)
	var compared := Digest.hash_files(real + paths, real_flags + flags)
	snap = Digest.snapshot()
	expect(int(compared.mismatches) == 0 and int(snap.mismatches) == 0 and snap.backend == "compare"
		and int(snap.compared_rows) >= real.size(),
		"compare over %d real rows: 0 mismatches" % int(snap.compared_rows))
	# The legacy optimization profile keeps legacy presentation; hashing does not care.
	Digest.configure("native", 4)
	_set_environment("RABBITLANDS_OPTIMIZATION_PROFILE", "legacy")
	_set_environment("RABBITLANDS_CLIENT_RUNTIME", "")
	var controller := Controller.new()
	controller.initialize()
	var runtime := controller.snapshot()
	expect(runtime.mode == "legacy" and runtime.presentation_backend == "legacy" and not bool(runtime.native_available)
		and str(Digest.snapshot().backend).begins_with("native:"),
		"legacy profile: presentation legacy (%s) while the digest backend is %s" % [runtime.reason, Digest.snapshot().backend])
	controller.close()
	Digest.reset()
	_restore_environment()
