extends SceneTree
## NH-A1: the native content digest `RabbitLandsContentDigest` in the
## client_runtime payload (core/src/digest.rs behind src/client_digest.cpp).
## Every result is checked against the engine (`FileAccess.get_sha256`,
## `HashingContext`) and the GDScript facade (`ContentDigest`, NH-A0): known
## vectors, buffers, files on read-size boundaries, CRLF folding, failures,
## thread counts, verify, a call from a worker thread and a sample of real
## project files.
##
## `--runtime-dir=<absolute payload directory>` tests a payload built outside
## the project (default: `NativeLibrary.default_directory()`).
## `--expect-native=present|absent` turns an unavailable or unexpected digest
## class into a failure, as in test_client_runtime.gd.

const NativeLibrary := preload("res://src/runtime/native_library.gd")
const Digest := preload("res://src/runtime/content_digest.gd")
const DIGEST_CLASS := &"RabbitLandsContentDigest"
const STATUS_OK := 0
const STATUS_OPEN := 1
const STATUS_BAD_PATH := 3
const STATUS_INTERNAL := 4
const FOLD := 1

var failures := 0
var _root := ""
var _read_bytes := 1048576
var _fixture_names := PackedStringArray()

func _init() -> void:
	call_deferred("_run")

func _expect(ok: bool, message: String) -> bool:
	if ok:
		print("PASS: ", message)
	else:
		failures += 1
		push_error("FAIL: " + message)
	return ok

func _bytes(text: String) -> PackedByteArray:
	return text.to_utf8_buffer()

func _write(path: String, bytes: PackedByteArray) -> bool:
	var file := FileAccess.open(path, FileAccess.WRITE)
	if file == null:
		return false
	file.store_buffer(bytes)
	file.close()
	return true

func _fold_reference(raw: PackedByteArray) -> Array:
	# The per-byte rule MapSceneCache._strip_carriage_returns always used.
	var out := PackedByteArray()
	for index: int in raw.size():
		if raw[index] == 13 and index + 1 < raw.size() and raw[index + 1] == 10:
			continue
		out.append(raw[index])
	return [out, out.size() != raw.size()]

func _random(size: int, seed_value: int) -> PackedByteArray:
	var rng := RandomNumberGenerator.new()
	rng.seed = seed_value
	var out := PackedByteArray()
	out.resize(size)
	var at := 0
	while at + 4 <= size:
		out.encode_u32(at, rng.randi())
		at += 4
	while at < size:
		out[at] = rng.randi() & 255
		at += 1
	return out

func _api(native: Object) -> void:
	var info: Dictionary = native.call("api_info")
	_expect(int(info.get("digest_api", 0)) == 1, "digest api is 1")
	var backend := str(info.get("sha256_backend", ""))
	_expect(backend in ["sha_ni", "portable"], "a SHA-256 backend was chosen (%s)" % backend)
	var forced := OS.get_environment("RABBITLANDS_CONTENT_DIGEST_SHA").strip_edges().to_lower() == "portable"
	if bool(info.get("cpu_sha_ni", false)) and not forced:
		_expect(backend == "sha_ni", "a CPU with SHA-NI uses it")
	else:
		_expect(backend == "portable", "the portable backend runs without SHA-NI or when forced")
	_expect(int(info.get("logical_cpus", 0)) >= 1 and int(info.get("max_threads", 0)) == 64
		and int(info.get("max_files", 0)) == 1048576 and int(info.get("read_bytes", 0)) == 1048576
		and int(info.get("flags", 0)) == FOLD, "limits and flags are reported (%s)" % JSON.stringify(info))
	_expect(info.get("index", {}) is Dictionary and not bool((info.get("index", {}) as Dictionary).get("supported", true)),
		"no BLAKE3 index in phase A")
	_read_bytes = int(info.get("read_bytes", _read_bytes))
	print("digest backend=%s cpu_sha_ni=%s logical_cpus=%d" % [backend, str(info.get("cpu_sha_ni")),
		int(info.get("logical_cpus", 0))])

func _vectors(native: Object) -> void:
	var nist := {
		"": "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855",
		"abc": "ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad",
		"abcdbcdecdefdefgefghfghighijhijkijkljklmklmnlmnomnopnopq":
			"248d6a61d20638b8e5c026930c3e6039a33ce45964ff2167f6ecedd419db06c1",
		"abcdefghbcdefghicdefghijdefghijkefghijklfghijklmghijklmnhijklmnoijklmnopjklmnopqklmnopqrlmnopqrsmnopqrstnopqrstu":
			"cf5b16a778af8380036ce59e7b0492370b249b11e8f07a51afac45037afee9d1",
	}
	for input: String in nist:
		_expect(str(native.call("sha256_buffer", _bytes(input))) == nist[input], "NIST vector of %d bytes" % input.length())
	var million := PackedByteArray()
	million.resize(1000000)
	million.fill(97)
	_expect(str(native.call("sha256_buffer", million)) == "cdc76e5c9914fb9281a1c7e284d73e67f1809a48a497200e046d39ccc7112cd0",
		"NIST million-a vector")
	var mismatched := 0
	for length: int in range(0, 300) + [511, 512, 513, 4095, 4096, 65537, 1048577]:
		var data := _random(length, 1000 + length)
		if str(native.call("sha256_buffer", data)) != Digest.buffer_sha256(data):
			mismatched += 1
	_expect(mismatched == 0, "buffers of 0-299 bytes and around block sizes equal HashingContext (%d mismatches)" % mismatched)

## Fixture files: name -> bytes. Sizes straddle the native read size.
func _fixtures() -> Dictionary:
	var big := _random(_read_bytes * 2 + 3, 77)
	var rows := {
		"empty.bin": PackedByteArray(),
		"small.bin": _bytes("hello"),
		"block-1.bin": big.slice(0, _read_bytes - 1),
		"block.bin": big.slice(0, _read_bytes),
		"block+1.bin": big.slice(0, _read_bytes + 1),
		"two-blocks+3.bin": big,
		"crlf.json": _bytes("{\r\n \"a\": 1\r\n}\r\n"),
		"lone-cr.json": _bytes("a\rb"),
		"cr-at-eof.json": _bytes("a\r"),
		"cr-cr-lf.json": _bytes("\r\r\n"),
		"lf-cr.json": _bytes("\n\r"),
		"café ünïcødé 名前.json": _bytes("non-ascii\r\nname"),
	}
	# CR LF straddling the first read, a CR then another byte at the boundary,
	# and a CR at the end of the file exactly on a read boundary.
	var straddle := _random(_read_bytes - 1, 5)
	straddle.append_array(_bytes("\r\nafter\r"))
	rows["straddle.json"] = straddle
	var cr_other := _random(_read_bytes - 1, 6)
	cr_other.append_array(_bytes("\rX"))
	rows["cr-then-other.json"] = cr_other
	var cr_end := _random(_read_bytes - 1, 7)
	cr_end.append(13)
	rows["cr-at-block-end.json"] = cr_end
	return rows

func _files(native: Object) -> void:
	var fixtures := _fixtures()
	var paths := PackedStringArray()
	var raw_expected := PackedStringArray()
	var folded_expected := PackedStringArray()
	var folded_flags := PackedByteArray()
	var total := 0
	for name: String in fixtures:
		var path := _root.path_join(name)
		if not _expect(_write(path, fixtures[name]), "fixture %s is writable" % name):
			continue
		_fixture_names.append(name)
		paths.append(path)
		raw_expected.append(FileAccess.get_sha256(path))
		var reference: Array = _fold_reference(fixtures[name])
		folded_expected.append(Digest.buffer_sha256(reference[0]))
		folded_flags.append(1 if reference[1] else 0)
		total += (fixtures[name] as PackedByteArray).size()
	var raw: Dictionary = native.call("sha256_files", paths, PackedInt32Array(), 4)
	_expect(int(raw.result) == 0 and raw.digests == raw_expected, "raw files equal FileAccess.get_sha256 (%d files)" % paths.size())
	_expect(int(raw.bytes) == total, "bytes read are reported (%d of %d)" % [int(raw.bytes), total])
	var all_ok := true
	for value: int in raw.status:
		all_ok = all_ok and value == STATUS_OK
	_expect(all_ok and Array(raw.folded).count(1) == 0, "raw rows are ok and never folded")
	_expect(str(raw.backend) in ["sha_ni", "portable"] and int(raw.elapsed_us) >= 0 and int(raw.threads) >= 1,
		"batch reports backend, time and threads")
	var flags := PackedInt32Array()
	flags.resize(paths.size())
	flags.fill(FOLD)
	var folded: Dictionary = native.call("sha256_files", paths, flags, 3)
	_expect(folded.digests == folded_expected, "folded files equal the per-byte CRLF rule")
	_expect(folded.folded == folded_flags, "the folded flag marks exactly the files that dropped a CR")
	# The GDScript facade (NH-A0) on the same rows, both backends.
	for mode: String in ["gdscript", "sequential"]:
		Digest.configure(mode, 2)
		var facade: Dictionary = Digest.hash_files(paths, flags)
		_expect(facade.digests == folded.digests and facade.folded == folded.folded and facade.status == folded.status,
			"native folded rows equal ContentDigest %s" % mode)
		var facade_raw: Dictionary = Digest.hash_files(paths)
		_expect(facade_raw.digests == raw.digests, "native raw rows equal ContentDigest %s" % mode)
	Digest.reset()
	# Unknown flag bits are ignored; -1 carries the fold bit.
	var odd := PackedInt32Array([0x40, -1])
	var odd_rows: Dictionary = native.call("sha256_files", PackedStringArray([paths[6], paths[6]]), odd, 1)
	_expect(odd_rows.digests[0] == raw_expected[6] and odd_rows.digests[1] == folded_expected[6],
		"unknown flag bits are ignored")
	# Flags shorter than the rows: the rest are 0.
	var short: Dictionary = native.call("sha256_files", PackedStringArray([paths[6], paths[6]]), PackedInt32Array([FOLD]), 2)
	_expect(short.digests[0] == folded_expected[6] and short.digests[1] == raw_expected[6], "missing flags are 0")
	_long_path(native)

func _long_path(native: Object) -> void:
	var directory := _root.path_join("d".repeat(120))
	var path := directory.path_join("f".repeat(150) + ".bin")
	DirAccess.make_dir_recursive_absolute(directory)
	if not _write(path, _bytes("long path")):
		print("SKIP: the engine cannot write a %d-character path here; core tests cover long paths" % path.length())
		return
	var row: Dictionary = native.call("sha256_files", PackedStringArray([path]), PackedInt32Array(), 1)
	_expect(path.length() > 260 and row.digests[0] == Digest.buffer_sha256(_bytes("long path")),
		"a %d-character path hashes" % path.length())

func _failures(native: Object) -> void:
	var good := _root.path_join("small.bin")
	var rows := PackedStringArray([good, _root.path_join("missing.bin"), _root, "relative/file.bin", "",
		"res://project.godot", "user://small.bin", good])
	var result: Dictionary = native.call("sha256_files", rows, PackedInt32Array(), 4)
	var wanted := PackedInt32Array([STATUS_OK, STATUS_OPEN, STATUS_OPEN, STATUS_BAD_PATH, STATUS_BAD_PATH,
		STATUS_BAD_PATH, STATUS_BAD_PATH, STATUS_OK])
	_expect(int(result.result) == 0 and result.status == wanted,
		"missing, directory, relative, empty and engine paths fail per row (%s)" % str(result.status))
	var failed_empty := true
	for index: int in [1, 2, 3, 4, 5, 6]:
		failed_empty = failed_empty and str(result.digests[index]).is_empty()
	_expect(failed_empty and result.digests[0] == FileAccess.get_sha256(good) and result.digests[7] == result.digests[0],
		"failed rows have no digest; good rows around them do")
	var empty: Dictionary = native.call("sha256_files", PackedStringArray(), PackedInt32Array(), 4)
	_expect(int(empty.result) == 0 and empty.digests.is_empty() and int(empty.bytes) == 0, "an empty batch is fine")
	_expect(str(native.call("sha256_buffer", PackedByteArray())) == Digest.EMPTY_SHA256, "the empty buffer")

func _fixture_paths() -> PackedStringArray:
	var paths := PackedStringArray()
	for name: String in _fixture_names:
		paths.append(_root.path_join(name))
	return paths

func _threads(native: Object) -> void:
	var paths := _fixture_paths()
	var reference: Dictionary = native.call("sha256_files", paths, PackedInt32Array(), 1)
	_expect(int(reference.threads) == 1, "one thread when one is asked for")
	for threads: int in [0, -5, 2, 3, 4, 8, 64, 1000]:
		var result: Dictionary = native.call("sha256_files", paths, PackedInt32Array(), threads)
		var limit := mini(clampi(threads, 1, 64), paths.size())
		_expect(result.digests == reference.digests and result.status == reference.status
			and int(result.threads) >= 1 and int(result.threads) <= limit,
			"threads=%d gives the same rows (%d threads ran)" % [threads, int(result.threads)])

func _verify(native: Object) -> void:
	var paths := PackedStringArray([_root.path_join("small.bin"), _root.path_join("crlf.json"),
		_root.path_join("small.bin"), _root.path_join("missing.bin")])
	var expected := PackedStringArray([FileAccess.get_sha256(paths[0]), FileAccess.get_sha256(paths[1]),
		FileAccess.get_sha256(paths[0]).to_upper(), FileAccess.get_sha256(paths[0])])
	var result: Dictionary = native.call("verify_files", paths, expected, PackedInt32Array(), 2)
	_expect(int(result.result) == 0 and result.ok == PackedByteArray([1, 1, 0, 0]),
		"verify passes exact lowercase matches only (%s)" % str(result.ok))
	_expect(result.digests[2] == expected[0] and result.status[3] == STATUS_OPEN, "verify still reports every row")
	var flags := PackedInt32Array([0, FOLD])
	var folded_expected := PackedStringArray([expected[0], Digest.buffer_sha256(_bytes("{\n \"a\": 1\n}\n"))])
	var folded: Dictionary = native.call("verify_files", paths.slice(0, 2), folded_expected, flags, 2)
	_expect(folded.ok == PackedByteArray([1, 1]) and folded.folded == PackedByteArray([0, 1]), "verify with the fold flag")
	var wrong := PackedStringArray(["", "zz" + expected[1].substr(2), expected[1] + "0", expected[1].substr(0, 63)])
	var bad: Dictionary = native.call("verify_files", PackedStringArray([paths[1], paths[1], paths[1], paths[1]]), wrong,
		PackedInt32Array(), 1)
	_expect(int(bad.result) == 0 and bad.ok == PackedByteArray([0, 0, 0, 0]) and bad.digests[0] == expected[1],
		"empty, non-hex, long and short expected values never pass")
	var mismatch: Dictionary = native.call("verify_files", paths, PackedStringArray([expected[0]]), PackedInt32Array(), 2)
	var internal := true
	for value: int in mismatch.status:
		internal = internal and value == STATUS_INTERNAL
	_expect(int(mismatch.result) == 1 and internal and mismatch.ok == PackedByteArray([0, 0, 0, 0])
		and str(mismatch.digests[0]).is_empty(), "an expected list of the wrong length is refused as a whole")

func _worker_thread(native: Object) -> void:
	var paths := _fixture_paths()
	var on_main: Dictionary = native.call("sha256_files", paths, PackedInt32Array(), 4)
	var expected := PackedStringArray(on_main.digests)
	var thread := Thread.new()
	thread.start(func() -> Array:
		var instance: Object = ClassDB.instantiate(DIGEST_CLASS)
		var hashed: Dictionary = instance.call("sha256_files", paths, PackedInt32Array(), 4)
		var checked: Dictionary = native.call("verify_files", paths, expected, PackedInt32Array(), 2)
		return [hashed.digests, checked.ok])
	var result: Array = thread.wait_to_finish()
	var all_ok := true
	for value: int in result[1]:
		all_ok = all_ok and value == 1
	_expect(result[0] == on_main.digests and all_ok, "a worker thread gets the same digests from a new and a shared instance")

func _collect(directory: String, out: PackedStringArray, limit: int) -> void:
	var dir := DirAccess.open(directory)
	if dir == null:
		return
	for name: String in dir.get_files():
		if out.size() >= limit:
			return
		out.append(directory.path_join(name))
	for name: String in dir.get_directories():
		if out.size() >= limit or name.begins_with("."):
			continue
		_collect(directory.path_join(name), out, limit)

func _project_files(native: Object) -> void:
	var paths := PackedStringArray()
	_collect(ProjectSettings.globalize_path("res://data"), paths, 600)
	_collect(ProjectSettings.globalize_path("res://src/runtime"), paths, 800)
	var expected := PackedStringArray()
	for path: String in paths:
		expected.append(FileAccess.get_sha256(path))
	var result: Dictionary = native.call("verify_files", paths, expected, PackedInt32Array(), 4)
	# The worktree is shared: a file another process rewrote between the two
	# reads is hashed again by both readers before it counts as a mismatch.
	var mismatched := 0
	for index: int in paths.size():
		if result.ok[index] == 1:
			continue
		var again: Dictionary = native.call("sha256_files", PackedStringArray([paths[index]]), PackedInt32Array(), 1)
		if again.digests[0] != FileAccess.get_sha256(paths[index]):
			mismatched += 1
	_expect(int(result.result) == 0 and mismatched == 0,
		"%d project files equal FileAccess.get_sha256 (%d bytes, %d us, %d threads, %d rechecked)" % [paths.size(),
		int(result.bytes), int(result.elapsed_us), int(result.threads), Array(result.ok).count(0)])

func _run() -> void:
	var args := OS.get_cmdline_user_args()
	var directory := ""
	for argument: String in args:
		if argument.begins_with("--runtime-dir="):
			directory = argument.trim_prefix("--runtime-dir=")
	var expect_present := args.has("--expect-native=present") or args.has("--expect-native")
	var expect_absent := args.has("--expect-native=absent")
	var loaded := NativeLibrary.load_verified(directory)
	var available := bool(loaded.ok) and ClassDB.class_exists(DIGEST_CLASS)
	if expect_present:
		_expect(available, "requested native-present run has the digest class (%s, %s)" % [loaded.code, loaded.directory])
	elif expect_absent:
		_expect(not available, "requested native-absent run has no digest class (%s)" % loaded.code)
	if not available:
		print("SKIP: native digest checks; payload %s (%s), digest class %s" % [loaded.directory, loaded.code,
			"present" if ClassDB.class_exists(DIGEST_CLASS) else "absent"])
		print("client runtime digest tests: ", "PASS" if failures == 0 else "FAIL")
		quit(failures)
		return
	_root = ProjectSettings.globalize_path("user://nh-a1-digest-%d" % OS.get_process_id())
	DirAccess.make_dir_recursive_absolute(_root)
	var native: Object = ClassDB.instantiate(DIGEST_CLASS)
	_expect(native != null and native is RefCounted, "the digest class instantiates as RefCounted")
	var runtime: Object = ClassDB.instantiate(NativeLibrary.RUNTIME_CLASS)
	_expect(runtime != null and int((runtime.call("runtime_info") as Dictionary).get("abi", 0)) == 1,
		"the client runtime class beside it still reports ABI 1")
	_api(native)
	_vectors(native)
	_files(native)
	_failures(native)
	_threads(native)
	_verify(native)
	_worker_thread(native)
	_project_files(native)
	# Each run writes ~5 MB of fixtures under a per-process directory; leave none behind.
	_remove_fixtures(_root)
	_expect(not DirAccess.dir_exists_absolute(_root), "this run's fixture directory is removed")
	print("client runtime digest tests: ", "PASS" if failures == 0 else "FAIL")
	quit(failures)

## Deletes this run's fixture tree. Only ever below `user://nh-a1-digest-<pid>`.
func _remove_fixtures(directory: String) -> void:
	if _root.is_empty() or not _root.get_file().begins_with("nh-a1-digest-") or not directory.begins_with(_root):
		return
	var dir := DirAccess.open(directory)
	if dir == null:
		return
	for name: String in dir.get_files():
		DirAccess.remove_absolute(directory.path_join(name))
	for name: String in dir.get_directories():
		_remove_fixtures(directory.path_join(name))
	DirAccess.remove_absolute(directory)
