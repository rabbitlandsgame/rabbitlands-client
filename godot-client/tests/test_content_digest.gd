extends SceneTree
## The content-digest facade (NH-A0): every backend gives the digest
## FileAccess.get_sha256 gives, CRLF folding matches the per-byte rule the
## package digest always used (also across read-block boundaries), a batch
## reports per-row failures in caller order and reads a repeated row once, and
## the package digest is unchanged. Run with an isolated user directory:
##
##   Godot_v4.7.2-stable_win64.exe --headless --path . --script tests/test_content_digest.gd

const Digest := preload("res://src/runtime/content_digest.gd")
const MapCache := preload("res://src/world/map_scene_cache.gd")
const DIRECTORY := "user://content-digest-tests"
const BLOCK := Digest.BLOCK_BYTES

var failures := 0
var _written: PackedStringArray = []

func _init() -> void:
	_run.call_deferred()

func expect(ok: bool, message: String) -> void:
	if ok:
		print("PASS: " + message)
	else:
		failures += 1
		push_error("FAIL: " + message)

func write(name: String, bytes: PackedByteArray) -> String:
	DirAccess.make_dir_recursive_absolute(DIRECTORY)
	var path := DIRECTORY.path_join(name)
	var file := FileAccess.open(path, FileAccess.WRITE)
	file.store_buffer(bytes)
	file.close()
	if not _written.has(path):
		_written.append(path)
	return path

## The per-byte fold every manifest went through before wave 1's CR-free fast
## path: drop a CR directly followed by LF, keep every other byte.
static func reference_fold(raw: PackedByteArray) -> PackedByteArray:
	var out := PackedByteArray()
	out.resize(raw.size())
	var written := 0
	for index: int in raw.size():
		if raw[index] == 13 and index + 1 < raw.size() and raw[index + 1] == 10:
			continue
		out[written] = raw[index]
		written += 1
	out.resize(written)
	return out

static func sha(bytes: PackedByteArray) -> String:
	var context := HashingContext.new()
	context.start(HashingContext.HASH_SHA256)
	if not bytes.is_empty():
		context.update(bytes)
	return context.finish().hex_encode()

## `size` bytes from a seeded 4 KiB tile rich in CR and LF.
static func pattern(size: int, seed_value: int) -> PackedByteArray:
	var rng := RandomNumberGenerator.new()
	rng.seed = seed_value
	var tile := PackedByteArray()
	for index: int in 4096:
		var pick := rng.randi_range(0, 9)
		tile.append(13 if pick < 2 else (10 if pick < 4 else rng.randi_range(0, 255)))
	var out := PackedByteArray()
	while out.size() + tile.size() <= size:
		out.append_array(tile)
	out.append_array(tile.slice(0, size - out.size()))
	return out

func _run() -> void:
	_check_resolve()
	_check_buffers()
	var fixtures := _write_fixtures()
	for mode: String in ["sequential", "gdscript"]:
		for threads: int in [1, 4]:
			Digest.configure(mode, threads)
			_check_files(fixtures, "%s x%d" % [mode, threads])
	Digest.configure("gdscript", 4)
	_check_batch(fixtures)
	_check_verify(fixtures)
	_check_worker_thread(fixtures)
	_check_order()
	_check_package_digest()
	_check_snapshot()
	Digest.reset()
	for path: String in _written:
		DirAccess.remove_absolute(ProjectSettings.globalize_path(path))
	DirAccess.remove_absolute(ProjectSettings.globalize_path(DIRECTORY))
	print("content digest: ", failures, " failures")
	quit(failures)

func _check_resolve() -> void:
	var none := PackedStringArray()
	var default := Digest.resolve({}, none, 8)
	expect(default.mode == "auto" and default.backend == "gdscript" and default.requested == "auto"
		and default.reason == "native_not_initialized",
		"the default is auto, served by the GDScript backend while no native payload was probed")
	expect(int(default.threads) == 4 and int(default.worker_threads) == 1,
		"main thread uses half the logical processors (8 -> 4); workers hash alone")
	expect(int(Digest.resolve({}, none, 24).threads) == 4 and int(Digest.resolve({}, none, 2).threads) == 1
		and int(Digest.resolve({}, none, 1).threads) == 1, "main-thread count is clamped to 1..4")
	var sequential := Digest.resolve({Digest.ENVIRONMENT: " Sequential "}, none, 8)
	expect(sequential.mode == "sequential" and sequential.backend == "sequential"
		and int(sequential.threads) == 1 and int(sequential.worker_threads) == 1,
		"sequential from the environment: one thread, the old cost profile")
	var argument := Digest.resolve({Digest.ENVIRONMENT: "sequential"},
		PackedStringArray(["--content-digest=gdscript"]), 8)
	expect(argument.mode == "gdscript" and argument.reason == "gdscript_selected",
		"the command-line argument overrides the environment")
	var invalid := Digest.resolve({Digest.ENVIRONMENT: "fastest"}, none, 8)
	expect(invalid.mode == "auto" and invalid.requested == "fastest" and invalid.reason == "invalid_mode_auto",
		"an unknown mode falls back to auto and says so")
	var compare := Digest.resolve({Digest.ENVIRONMENT: "compare"}, none, 8)
	expect(compare.mode == "compare" and compare.backend == "gdscript" and compare.reason == "compare_native_not_initialized",
		"compare without a native backend hashes with GDScript and says why")
	var threads := Digest.resolve({Digest.THREADS_ENVIRONMENT: "3"}, none, 8)
	var both := Digest.resolve({Digest.THREADS_ENVIRONMENT: "2, 2"}, none, 8)
	var junk := Digest.resolve({Digest.THREADS_ENVIRONMENT: "many"}, none, 8)
	var capped := Digest.resolve({Digest.THREADS_ENVIRONMENT: "64"}, none, 8)
	var forced := Digest.resolve({Digest.THREADS_ENVIRONMENT: "3,3", Digest.ENVIRONMENT: "sequential"}, none, 8)
	expect(int(threads.threads) == 3 and int(threads.worker_threads) == 1
		and int(both.threads) == 2 and int(both.worker_threads) == 2
		and int(junk.threads) == 4 and int(capped.threads) == Digest.MAX_THREAD_OVERRIDE
		and int(forced.threads) == 1 and int(forced.worker_threads) == 1,
		"the thread override sets main (and worker) counts, ignores junk, is capped, and never threads sequential")

func _check_buffers() -> void:
	expect(Digest.buffer_sha256("abc".to_utf8_buffer())
		== "ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad", "NIST abc")
	expect(Digest.buffer_sha256("abcdbcdecdefdefgefghfghighijhijkijkljklmklmnlmnomnopnopq".to_utf8_buffer())
		== "248d6a61d20638b8e5c026930c3e6039a33ce45964ff2167f6ecedd419db06c1", "NIST 448-bit message")
	expect(Digest.buffer_sha256(PackedByteArray()) == Digest.EMPTY_SHA256
		and Digest.EMPTY_SHA256 == sha(PackedByteArray()), "the empty buffer's digest, without an empty update")
	var samples: Array[PackedByteArray] = ["a\r\nb".to_utf8_buffer(), "a\rb".to_utf8_buffer(),
		"a\r".to_utf8_buffer(), "\r\r\n".to_utf8_buffer(), "\r".to_utf8_buffer(), "\r\n".to_utf8_buffer(),
		"\n\r".to_utf8_buffer(), "{\"a\": 1}".to_utf8_buffer(), "x\r\n\r\ny\r".to_utf8_buffer(),
		PackedByteArray(), pattern(10000, 7)]
	var same := true
	for sample: PackedByteArray in samples:
		same = same and Digest.fold_crlf(sample) == reference_fold(sample) \
			and MapCache._strip_carriage_returns(sample) == reference_fold(sample)
	expect(same, "fold_crlf (and the package digest's fold) match the per-byte rule on every edge case")
	expect(Digest.fold_crlf("a\r\nb".to_utf8_buffer()) == "a\nb".to_utf8_buffer()
		and Digest.fold_crlf("\r\r\n".to_utf8_buffer()) == "\r\n".to_utf8_buffer()
		and Digest.fold_crlf("a\r".to_utf8_buffer()) == "a\r".to_utf8_buffer(),
		"CRLF folds, a lone CR and a CR at the end stay")

## name -> [path, raw digest, folded digest, fold changed bytes]
func _write_fixtures() -> Dictionary:
	var bodies := {
		"empty.bin": PackedByteArray(),
		"text_lf.json": "{\n\"asset\": 1\n}\n".to_utf8_buffer(),
		"text_crlf.json": "{\r\n\"asset\": 1\r\n}\r\n".to_utf8_buffer(),
		"lone_cr.txt": "a\rb".to_utf8_buffer(),
		"cr_at_eof.txt": "a\r\nb\r".to_utf8_buffer(),
		"cr_cr_lf.txt": "\r\r\n".to_utf8_buffer(),
		"only_cr.txt": "\r".to_utf8_buffer(),
		"block_minus_one.bin": pattern(BLOCK - 1, 1),
		"block.bin": pattern(BLOCK, 2),
		"block_plus_one.bin": pattern(BLOCK + 1, 3),
		"two_blocks.bin": pattern(2 * BLOCK + 3, 4),
	}
	# A CR that ends the first read block, followed by LF / by another byte /
	# by CR LF, and a CR that ends the file exactly at a block boundary.
	var straddle := pattern(BLOCK + 5, 5)
	straddle[BLOCK - 2] = 65
	straddle[BLOCK - 1] = 13
	straddle[BLOCK] = 10
	bodies["boundary_crlf.bin"] = straddle
	var lone := straddle.duplicate()
	lone[BLOCK] = 65
	bodies["boundary_cr_other.bin"] = lone
	var doubled := straddle.duplicate()
	doubled[BLOCK] = 13
	doubled[BLOCK + 1] = 10
	bodies["boundary_cr_crlf.bin"] = doubled
	var tail := pattern(BLOCK, 6)
	tail[BLOCK - 2] = 65
	tail[BLOCK - 1] = 13
	bodies["eof_cr_at_block.bin"] = tail
	var fixtures := {}
	for name: String in bodies:
		var raw: PackedByteArray = bodies[name]
		var path := write(name, raw)
		var reference := reference_fold(raw)
		fixtures[name] = [path, sha(raw), sha(reference), reference.size() != raw.size()]
	return fixtures

func _check_files(fixtures: Dictionary, label: String) -> void:
	var paths := PackedStringArray()
	var flags := PackedInt32Array()
	for name: String in fixtures:
		paths.append(fixtures[name][0])
		flags.append(0)
		paths.append(fixtures[name][0])
		flags.append(Digest.FOLD_CRLF)
	var result := Digest.hash_files(paths, flags)
	var digests: PackedStringArray = result.digests
	var status: PackedInt32Array = result.status
	var folded: PackedByteArray = result.folded
	var raw_ok := true
	var fold_ok := true
	var flag_ok := true
	var row := 0
	for name: String in fixtures:
		var fixture: Array = fixtures[name]
		raw_ok = raw_ok and digests[row] == fixture[1] and digests[row] == FileAccess.get_sha256(fixture[0]) \
			and status[row] == Digest.STATUS_OK and folded[row] == 0
		fold_ok = fold_ok and digests[row + 1] == fixture[2] and status[row + 1] == Digest.STATUS_OK
		flag_ok = flag_ok and (folded[row + 1] == 1) == bool(fixture[3])
		if digests[row] != fixture[1] or digests[row + 1] != fixture[2]:
			print("  mismatch %s %s raw=%s fold=%s" % [label, name, digests[row], digests[row + 1]])
		row += 2
	expect(raw_ok, label + ": raw digests equal FileAccess.get_sha256 on every fixture")
	expect(fold_ok, label + ": folded digests equal the per-byte fold, across block boundaries")
	expect(flag_ok, label + ": `folded` says exactly when the fold dropped a byte")
	expect(int(result.files) == paths.size(), label + ": raw and folded rows of one file are distinct jobs")
	var expected_threads := 1 if label.begins_with("sequential") or label.ends_with("x1") else 4
	expect(int(result.threads) == expected_threads, label + ": batch ran on %d thread(s)" % expected_threads)
	var single := true
	for name: String in fixtures:
		single = single and Digest.file_sha256(fixtures[name][0]) == fixtures[name][1] \
			and Digest.normalised_text_sha256(fixtures[name][0]) == fixtures[name][2]
	expect(single, label + ": file_sha256 and normalised_text_sha256 agree")

func _check_batch(fixtures: Dictionary) -> void:
	var text: String = fixtures["text_crlf.json"][0]
	var big: String = fixtures["two_blocks.bin"][0]
	var missing := DIRECTORY.path_join("absent.bin")
	var paths := PackedStringArray([text, big, text, missing, "", big, DIRECTORY])
	var flags := PackedInt32Array([0, 0, 0, 0, 0, Digest.FOLD_CRLF | 8, 0])
	var result := Digest.hash_files(paths, flags)
	var digests: PackedStringArray = result.digests
	var status: PackedInt32Array = result.status
	expect(int(result.files) == 6, "a repeated (path, flags) row is read once; unknown flag bits are ignored")
	expect(digests[0] == digests[2] and digests[0] == fixtures["text_crlf.json"][1],
		"a repeated row reports its digest in every position")
	expect(digests[3].is_empty() and status[3] == Digest.STATUS_OPEN, "a missing file is '' with STATUS_OPEN")
	expect(digests[4].is_empty() and status[4] == Digest.STATUS_BAD_PATH, "an empty path is STATUS_BAD_PATH, never opened")
	expect(digests[5] == fixtures["two_blocks.bin"][2], "flag bits beyond FOLD_CRLF do not change the digest")
	expect(digests[6].is_empty() and status[6] != Digest.STATUS_OK, "a directory is not a file")
	expect(Digest.files_sha256(PackedStringArray([text, big])) == PackedStringArray([fixtures["text_crlf.json"][1],
		fixtures["two_blocks.bin"][1]]), "files_sha256 is the digests of hash_files")
	var empty := Digest.hash_files(PackedStringArray())
	expect((empty.digests as PackedStringArray).is_empty() and int(empty.files) == 0, "an empty batch is empty")
	# A job a thread took and never stored (a script error on a helper) must
	# read as failed, not as STATUS_OK with an empty digest.
	var lost := Digest._Batch.new()
	lost.setup(PackedStringArray([text, big]), PackedInt32Array([0, 0]), PackedInt32Array([0, 1]), false)
	var taken := lost.take()
	Digest._drain(lost)
	expect(taken == 0 and lost.status[0] == Digest.STATUS_INTERNAL and lost.digests[0].is_empty()
		and lost.folded[0] == 0 and lost.status[1] == Digest.STATUS_OK
		and lost.digests[1] == fixtures["two_blocks.bin"][1],
		"a job taken and never finished is STATUS_INTERNAL with no digest; the rest of the batch completes")
	var sized := Digest.hash_files(PackedStringArray([text, big]), PackedInt32Array(), PackedInt64Array([10, BLOCK * 2]))
	expect(sized.digests == PackedStringArray([fixtures["text_crlf.json"][1], fixtures["two_blocks.bin"][1]]),
		"size hints reorder the work, never the results")
	expect(int(result.bytes) > 2 * BLOCK, "the reader counts the bytes it read")

func _check_verify(fixtures: Dictionary) -> void:
	var rows: Array = []
	for name: String in fixtures:
		rows.append({"path": fixtures[name][0], "sha256": fixtures[name][1]})
	rows.append({"path": fixtures["text_crlf.json"][0], "sha256": fixtures["text_crlf.json"][2], "flags": Digest.FOLD_CRLF})
	var good := Digest.verify(rows)
	expect(bool(good.ok) and int(good.first_failure) == -1 and (good.matches as PackedByteArray).count(1) == rows.size(),
		"every row of an intact batch verifies, folded rows included")
	var bad := rows.duplicate(true)
	bad[3]["sha256"] = "0".repeat(64)
	bad[5]["sha256"] = str(bad[5]["sha256"]).to_upper()
	bad[7]["path"] = DIRECTORY.path_join("absent.bin")
	bad[8]["sha256"] = ""
	var result := Digest.verify(bad)
	var matches: PackedByteArray = result.matches
	expect(not bool(result.ok) and int(result.first_failure) == 3, "the first failing row in caller order is reported")
	expect(matches[3] == 0 and matches[5] == 0 and matches[7] == 0 and matches[8] == 0
		and matches.count(0) == 4, "a wrong digest, an upper-case digest, a missing file and an empty expectation fail")
	expect((result.digests as PackedStringArray)[9] == fixtures.values()[9][1],
		"rows after a failure are still hashed")
	var odd := Digest.verify([{"path": fixtures["empty.bin"][0], "sha256": Digest.EMPTY_SHA256}, "not a row"])
	expect(not bool(odd.ok) and int(odd.first_failure) == 1 and (odd.matches as PackedByteArray)[0] == 1,
		"an empty file verifies and a malformed row fails in place")

func _check_worker_thread(fixtures: Dictionary) -> void:
	var paths := PackedStringArray()
	for name: String in fixtures:
		paths.append(fixtures[name][0])
	var box := {}
	var thread := Thread.new()
	thread.start(func() -> void: box["result"] = Digest.hash_files(paths))
	thread.wait_to_finish()
	var result: Dictionary = box.get("result", {})
	var main := Digest.hash_files(paths)
	expect(int(result.get("threads", 0)) == 1 and int(main.threads) == 4,
		"a worker-thread caller hashes alone; the main thread shares the batch")
	expect(result.get("digests", PackedStringArray()) == main.digests, "and both give the same digests")
	Digest.configure("gdscript", 4, 2)
	var shared := {}
	thread = Thread.new()
	thread.start(func() -> void: shared["result"] = Digest.hash_files(paths))
	thread.wait_to_finish()
	expect(int(shared.result.threads) == 2 and shared.result.digests == main.digests,
		"the worker count can be raised explicitly")
	Digest.configure("gdscript", 4)

func _check_order() -> void:
	expect(Digest._largest_first(PackedInt64Array([-1, -1, -1])) == PackedInt32Array([0, 1, 2]),
		"without size hints the caller's order stands")
	expect(Digest._largest_first(PackedInt64Array([5, 90, -1, 90, 7])) == PackedInt32Array([1, 3, 4, 0, 2]),
		"with hints the largest go first, ties and unknowns in caller order")

func _check_package_digest() -> void:
	var glb := write("world.glb", pattern(BLOCK + 17, 9))
	var lf := write("world.json", "{\n\"asset\": {\"glb\": \"world.glb\"}\n}\n".to_utf8_buffer())
	var crlf := write("world_crlf.json", "{\r\n\"asset\": {\"glb\": \"world.glb\"}\r\n}\r\n".to_utf8_buffer())
	var old := sha(("%s\n%s\n%s\n" % [MapCache.PACKAGE_DIGEST_VERSION, FileAccess.get_sha256(glb),
		FileAccess.get_sha256(lf)]).to_utf8_buffer())
	var digests := {}
	for mode: String in ["sequential", "gdscript"]:
		Digest.configure(mode, 4)
		var parts := MapCache.package_digest_parts(lf, glb)
		var folded := MapCache.package_digest_parts(crlf, glb)
		digests[mode] = parts.digest
		expect(str(parts.digest) == old and str(folded.digest) == old,
			mode + ": the package digest is the one the old code computed, CRLF or LF")
		expect(str(parts.glb_sha256) == FileAccess.get_sha256(glb) and str(parts.manifest_sha256) == FileAccess.get_sha256(lf)
			and str(folded.manifest_sha256).is_empty() and str(folded.glb_sha256) == str(parts.glb_sha256),
			mode + ": the raw file digests are offered, never a folded manifest's")
		var absent := MapCache.package_digest_parts(DIRECTORY.path_join("absent.json"), glb)
		var no_glb := MapCache.package_digest_parts(lf, DIRECTORY.path_join("absent.glb"))
		expect(str(absent.digest).is_empty() and str(absent.glb_sha256).is_empty()
			and str(no_glb.digest).is_empty() and str(no_glb.manifest_sha256).is_empty(),
			mode + ": a package missing either file reports nothing")
	expect(MapCache.compose_package_digest(FileAccess.get_sha256(glb), FileAccess.get_sha256(lf)) == old
		and MapCache.compose_package_digest("", FileAccess.get_sha256(lf)).is_empty()
		and MapCache.compose_package_digest(FileAccess.get_sha256(glb), "").is_empty(),
		"compose_package_digest builds the same digest from the two file digests, and nothing from a missing one")
	Digest.configure("gdscript", 4)

func _check_snapshot() -> void:
	Digest.reset()
	Digest.configure("gdscript", 2)
	var before := Digest.snapshot()
	Digest.hash_files(PackedStringArray([_written[0], _written[1], _written[2]]))
	var after := Digest.snapshot()
	expect(after.backend == "gdscript" and int(after.threads) == 2 and int(after.calls) == int(before.calls) + 1
		and int(after.files) == int(before.files) + 3 and int(after.parallel_calls) == int(before.parallel_calls) + 1
		and int(after.us) >= int(before.us), "snapshot counts calls, files, parallel batches and time")
	Digest.reset()
	expect(int(Digest.snapshot().calls) == 0, "reset clears the counters and resolves the mode again")
