extends SceneTree
## Hashes every path of a list with the native `RabbitLandsContentDigest` and
## writes the results as JSON, for `tools/native_digest_check.py`, which
## compares them with Python's hashlib over a whole install (NH-A1).
##
## Arguments (after `--`):
##   --list=<file>         one absolute path per line (UTF-8)
##   --out=<file>          JSON result
##   --runtime-dir=<dir>   payload directory (default: NativeLibrary.default_directory())
##   --threads=<n>         threads per batch (default 4)
##   --batch=<n>           rows per call (default 4096)
##   --fold-suffix=<ext>   also hash files ending in <ext> with FOLD_CRLF (repeatable)
##
## Exit code: 0 when every row was hashed (status 0), 1 when any row failed,
## 2 when the digest class is unavailable.

const NativeLibrary := preload("res://src/runtime/native_library.gd")
const DIGEST_CLASS := &"RabbitLandsContentDigest"
const FOLD := 1

func _init() -> void:
	call_deferred("_run")

func _write(path: String, value: Dictionary) -> void:
	var file := FileAccess.open(path, FileAccess.WRITE)
	if file == null:
		push_error("native_digest_check: cannot write " + path)
		return
	file.store_string(JSON.stringify(value))
	file.close()

func _run() -> void:
	var list := ""
	var out := ""
	var directory := ""
	var threads := 4
	var batch := 4096
	var suffixes := PackedStringArray()
	for argument: String in OS.get_cmdline_user_args():
		if argument.begins_with("--list="):
			list = argument.trim_prefix("--list=")
		elif argument.begins_with("--out="):
			out = argument.trim_prefix("--out=")
		elif argument.begins_with("--runtime-dir="):
			directory = argument.trim_prefix("--runtime-dir=")
		elif argument.begins_with("--threads="):
			threads = maxi(1, int(argument.trim_prefix("--threads=")))
		elif argument.begins_with("--batch="):
			batch = maxi(1, int(argument.trim_prefix("--batch=")))
		elif argument.begins_with("--fold-suffix="):
			suffixes.append(argument.trim_prefix("--fold-suffix=").to_lower())
	var loaded := NativeLibrary.load_verified(directory)
	if not bool(loaded.ok) or not ClassDB.class_exists(DIGEST_CLASS):
		_write(out, {"error": "digest_unavailable", "code": str(loaded.code), "directory": str(loaded.directory)})
		print("native_digest_check: digest class unavailable (%s)" % loaded.code)
		quit(2)
		return
	var native: Object = ClassDB.instantiate(DIGEST_CLASS)
	var paths := PackedStringArray()
	for line: String in FileAccess.get_file_as_string(list).split("\n", false):
		var path := line.strip_edges(false, true)
		if not path.is_empty():
			paths.append(path)
	var digests := PackedStringArray()
	var status := PackedInt32Array()
	var fold_rows: Dictionary = {}
	var bytes := 0
	var native_us := 0
	var batches := 0
	var failed := 0
	var began := Time.get_ticks_usec()
	var start := 0
	while start < paths.size():
		var rows := paths.slice(start, mini(start + batch, paths.size()))
		var result: Dictionary = native.call("sha256_files", rows, PackedInt32Array(), threads)
		digests.append_array(result.digests)
		status.append_array(result.status)
		bytes += int(result.bytes)
		native_us += int(result.elapsed_us)
		batches += 1
		var fold_paths := PackedStringArray()
		var fold_index := PackedInt32Array()
		for offset: int in rows.size():
			for suffix: String in suffixes:
				if rows[offset].to_lower().ends_with(suffix):
					fold_paths.append(rows[offset])
					fold_index.append(start + offset)
					break
		if not fold_paths.is_empty():
			var flags := PackedInt32Array()
			flags.resize(fold_paths.size())
			flags.fill(FOLD)
			var folded: Dictionary = native.call("sha256_files", fold_paths, flags, threads)
			native_us += int(folded.elapsed_us)
			for offset: int in fold_paths.size():
				fold_rows[str(fold_index[offset])] = [folded.digests[offset], int(folded.status[offset]),
					int(folded.folded[offset])]
				if int(folded.status[offset]) != 0:
					failed += 1
		start += rows.size()
	for value: int in status:
		if value != 0:
			failed += 1
	_write(out, {"api_info": native.call("api_info"), "count": paths.size(), "digests": digests,
		"status": Array(status), "fold": fold_rows, "bytes": bytes, "native_us": native_us,
		"wall_us": Time.get_ticks_usec() - began, "threads": threads, "batches": batches, "failed": failed})
	print("native_digest_check: %d files, %d bytes, %d failed, %.1f ms in native calls" % [paths.size(), bytes,
		failed, native_us / 1000.0])
	quit(1 if failed > 0 else 0)
