extends RefCounted
## Offline native-file closure only. Never executes in the live loader and
## never treats a Resource class or a filename scan as a reclamation proof.
const Prepared := preload("res://src/world/prepared_content.gd")
const POLICY := "lossless-rscc-exact-native-closure-v1"

static func save(resource: Resource, path: String) -> Error:
	return ResourceSaver.save(resource, path, ResourceSaver.FLAG_COMPRESS)

static func _failure(message: String) -> Dictionary:
	return {"ok": false, "error": message}

static func _scoped(path: String, root_path: String) -> bool:
	return path == path.replace("\\", "/").simplify_path() \
		and path.get_base_dir() == root_path and path.get_extension() in ["res", "scn"]

static func _dependency_path(dependency: String) -> Dictionary:
	var path := ""
	var uid := ""
	for part: String in dependency.split("::"):
		if part.begins_with("uid://"):
			uid = part
		elif part.begins_with("res://") or part.begins_with("user://"):
			if not path.is_empty():
				return _failure("ambiguous native dependency: " + dependency)
			path = part
	if path.is_empty() or path != path.replace("\\", "/").simplify_path():
		return _failure("unresolved/noncanonical native dependency: " + dependency)
	if not uid.is_empty():
		var identity := ResourceUID.text_to_id(uid)
		if ResourceUID.has_id(identity) and ResourceUID.get_id_path(identity) != path:
			return _failure("native dependency UID resolves to different bytes: " + dependency)
	return {"ok": true, "path": path}

static func closure(primary: String, known: Dictionary, inputs: Dictionary, root_path: String) -> Dictionary:
	if root_path != root_path.replace("\\", "/").simplify_path() or root_path.ends_with("/"):
		return _failure("noncanonical owned native root")
	var pending: Array[String] = [primary]
	var reached: Dictionary = {}
	var checked_inputs: Dictionary = {}
	while not pending.is_empty():
		var path: String = pending.pop_back()
		if reached.has(path):
			continue
		if not _scoped(path, root_path) or not known.has(path):
			return _failure("unknown/unowned native dependency: " + path)
		var expected := str(known[path])
		if expected.length() != 64 or not FileAccess.file_exists(path) or FileAccess.get_sha256(path) != expected:
			return _failure("missing/changed native dependency: " + path)
		reached[path] = expected
		for dependency: String in ResourceLoader.get_dependencies(path):
			var decoded := _dependency_path(dependency)
			if not bool(decoded.ok):
				return decoded
			var target := str(decoded.path)
			if _scoped(target, root_path):
				pending.append(target)
			else:
				# Named shaders retain their exact semantic resource paths. Their
				# complete include closure was already added to the source inputs.
				# A native file outside this generation cannot become an input by
				# accident; it must be a current explicitly verified source file.
				var logical := Prepared.logical_source(target)
				if logical.is_empty() or not inputs.has(logical):
					return _failure("undeclared external native dependency: " + target)
				if not checked_inputs.has(logical):
					var digest := str(inputs[logical])
					if digest.length() != 64 or not FileAccess.file_exists(target) \
						or FileAccess.get_sha256(target) != digest:
						return _failure("missing/changed external native dependency: " + target)
					checked_inputs[logical] = digest
	return {"ok": true, "payloads": reached, "external_inputs": checked_inputs}

static func finalize(root_path: String, entries: Array, generated: Dictionary) -> Dictionary:
	# Plan and verify EVERY root before any deletion. Shared resources survive
	# if any entry needs them; failure leaves every generation-owned file in
	# place and prevents publication of a variant catalog.
	var retained: Dictionary = {}
	for value: Variant in entries:
		if not value is Dictionary:
			return _failure("invalid generation entry")
		var entry: Dictionary = value
		var inputs: Dictionary = {}
		for row: Dictionary in entry.get("inputs", []):
			if inputs.has(str(row.path)):
				return _failure("duplicate generation input")
			inputs[str(row.path)] = str(row.sha256)
		var current := closure(str(entry.get("resource", "")), generated, inputs, root_path)
		if not bool(current.ok):
			return current
		var declared: Dictionary = {}
		for row: Dictionary in entry.get("payloads", []):
			if declared.has(str(row.path)):
				return _failure("duplicate generation native payload")
			declared[str(row.path)] = str(row.sha256)
		if declared != current.payloads:
			return _failure("entry native closure changed before generation finalization")
		retained.merge(current.payloads)
	if entries.is_empty() or retained.is_empty():
		return _failure("empty native generation cannot be finalized")
	var stats := {"policy": POLICY, "saved_files": generated.size(), "saved_bytes": 0,
		"reachable_files": retained.size(), "reachable_bytes": 0, "removed_files": 0, "removed_bytes": 0}
	var removals: Array[String] = []
	var filenames: Dictionary = {}
	for path: String in generated:
		if not _scoped(path, root_path) or not FileAccess.file_exists(path) \
				or FileAccess.get_sha256(path) != str(generated[path]):
			return _failure("generation file changed before orphan cleanup: " + path)
		var file := FileAccess.open(path, FileAccess.READ)
		if file == null:
			return _failure("generation file cannot be inspected: " + path)
		var size := file.get_length()
		file = null
		stats.saved_bytes += size
		filenames[path.get_file()] = true
		if retained.has(path):
			stats.reachable_bytes += size
		else:
			removals.append(path)
			stats.removed_bytes += size
	if not DirAccess.get_directories_at(root_path).is_empty():
		return _failure("unexpected directory in flat owned generation")
	for filename: String in DirAccess.get_files_at(root_path):
		if not filenames.has(filename):
			return _failure("unowned file in native generation: " + filename)
	for path: String in removals:
		if DirAccess.remove_absolute(path) != OK:
			return _failure("native orphan removal failed: " + path)
		stats.removed_files += 1
	return {"ok": true, "stats": stats, "payloads": retained}
