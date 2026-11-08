extends Node
## One verified archive at a time. Compressed downloads live in CacheStorage;
## this service bounds the extracted, session-only filesystem separately.
signal archive_ready(ok: bool, message: String)
signal files_evicted(paths: PackedStringArray)
const ARCHIVE := "/tmp/rabbitlands-prototype-assets.zip"
const UNPACK_SLICE_USEC := 2000
const STARTUP_UNPACK_SLICE_USEC := 12000
const READY_GRACE_MSEC := 1500
var bridge: JavaScriptObject
var callback: JavaScriptObject
var groups: Dictionary = {}
var states: Dictionary = {}
var pins: Dictionary = {}
var files: Dictionary = {}
var _source_paths: Dictionary = {}
var sizes: Dictionary = {}
var touched: Dictionary = {}
var queue: Array[String] = []
var _priorities: Dictionary = {}
var _queue_order: Dictionary = {}
var _next_order := 0
var busy := false
var current := ""
var error := ""
var errors: Dictionary = {}
var completed_archives := 0
var live_bytes := 0
var budget_bytes := 768 * 1024 * 1024
var _evictions := 0
var archive_path := ARCHIVE
var _archive_response: Array = []
var _archive_proof_consumer: Callable
var _archive_proof_hits := 0
var _archive_proof_bytes := 0
var _archive_sha_checks := 0
var _archive_sha_usec := 0
var _unpack_yields := 0

func configure(configuration: Dictionary, manifest: Dictionary) -> bool:
	groups = configuration.get("groups", {})
	if groups.is_empty():
		groups = {"startup":{"archives":configuration.get("archives", []), "dependencies":[], "unpacked_bytes":0}}
	elif groups != manifest.get("groups", {}):
		error = "Game download catalog does not match this build."
		return false
	if configuration.get("archives", []) != manifest.get("archives", []):
		error = "Game download catalog does not match this build."
		return false
	if configuration.get("source_groups", {}) != manifest.get("source_groups", {}):
		error = "Game appearance catalog does not match this build."
		return false
	budget_bytes = maxi(1, int(configuration.get("live_asset_budget_bytes", budget_bytes)))
	bridge = JavaScriptBridge.get_interface("RabbitLandsBrowser")
	callback = JavaScriptBridge.create_callback(_archive_ready)
	_archive_proof_consumer = Callable()
	if OS.has_feature("web") and bridge != null:
		_configure_archive_proof(bridge.archive_proof_version, _consume_bridge_archive_proof)
	pin_groups("startup", ["startup"])
	return true

func _configure_archive_proof(version: Variant, consumer: Callable) -> void:
	_archive_proof_consumer = Callable()
	# Older launchers have no property; strings and booleans are not a version.
	if typeof(version) in [TYPE_INT, TYPE_FLOAT] and version == 1 and consumer.is_valid():
		_archive_proof_consumer = consumer

func _consume_bridge_archive_proof(expected: String, expected_bytes: int) -> bool:
	var result: Variant = bridge.consume_archive_proof(expected, expected_bytes)
	return typeof(result) == TYPE_BOOL and result

func _take_archive_proof(expected: String, expected_bytes: int) -> bool:
	# Only the loader's one owned handoff file can use its page-local proof.
	# A different path, older launcher or a consumed/mismatched proof still hashes.
	if archive_path != ARCHIVE or expected_bytes <= 0 or not _archive_proof_consumer.is_valid():
		return false
	var result: Variant = _archive_proof_consumer.call(expected, expected_bytes)
	return typeof(result) == TYPE_BOOL and result

func _unpack_slice_usec() -> int:
	# Startup blocks Main/login; spend more of its frames preparing local files.
	# All interactive map/actor work retains the short slice.
	return STARTUP_UNPACK_SLICE_USEC if current == "startup" else UNPACK_SLICE_USEC

func _closure(ids: Array, result: Dictionary) -> bool:
	for value: Variant in ids:
		var id := str(value)
		if result.has(id): continue
		if not groups.has(id):
			error = "A required game asset group is unavailable."
			return false
		result[id] = true
		if not _closure(groups[id].get("dependencies", []), result): return false
	return true

func pin_groups(owner: String, ids: Array) -> void:
	var expanded := {}
	if _closure(ids, expanded): pins[owner] = expanded

func release_groups(owner: String) -> void:
	pins.erase(owner)

func retry_failed() -> int:
	var count := 0
	for id: String in states.keys():
		if states[id] == "failed":
			states.erase(id)
			count += 1
	errors.clear()
	error = ""
	return count

func ensure_groups(ids: Array, owner := "", priority := -1) -> bool:
	if not owner.is_empty(): pin_groups(owner, ids)
	if priority < 0:
		priority = 2 if owner in ["startup", "destination"] else (1 if not owner.is_empty() else 0)
	var required := {}
	if not _closure(ids, required): return false
	var ready := true
	var changed := false
	for id: String in required:
		touched[id] = Time.get_ticks_msec()
		if str(states.get(id, "")) == "ready": continue
		ready = false
		if str(states.get(id, "")) in ["loading", "failed"]: continue
		changed = _queue_group(id, priority) or changed
	if changed:
		queue.sort_custom(func(a: String, b: String) -> bool:
			var first := int(_priorities.get(a, 0))
			var second := int(_priorities.get(b, 0))
			return first > second if first != second else int(_queue_order[a]) < int(_queue_order[b]))
	return ready

func groups_ready(ids: Array) -> bool:
	var required := {}
	if not _closure(ids, required): return false
	for id: String in required:
		if states.get(id, "") != "ready": return false
	return true

func _queue_group(id: String, priority: int) -> bool:
	if states.has(id):
		if states[id] == "queued" and priority > int(_priorities.get(id, 0)):
			_priorities[id] = priority
			for dependency: String in groups[id].get("dependencies", []): _queue_group(dependency, priority)
			return true
		return false
	states[id] = "queued"
	for dependency: String in groups[id].get("dependencies", []): _queue_group(dependency, priority)
	_priorities[id] = priority
	_queue_order[id] = _next_order
	_next_order += 1
	queue.append(id)
	return true

func _process(_delta: float) -> void:
	if not busy and not queue.is_empty():
		busy = true
		_load_next.call_deferred()
	elif not busy:
		_evict()

func _load_next() -> void:
	current = queue.pop_front()
	_priorities.erase(current)
	_queue_order.erase(current)
	states[current] = "loading"
	files[current] = []
	var archives: Array = groups[current].get("archives", [])
	var total := 0
	for index: int in archives.size():
		_archive_response = []
		if int(WebPrototype.configuration().get("schema", 2)) == 3:
			bridge.fetch_group_archive(current, index, callback)
		else:
			bridge.fetch_archive(index, callback)
		# A rejected JS request can call back before the bridge method returns.
		var response: Array = _archive_response if not _archive_response.is_empty() else await archive_ready
		if not bool(response[0]):
			_fail(str(response[1]))
			return
		var unpacked := await _unpack(str(archives[index].sha256), int(archives[index].get("bytes", -1)))
		if unpacked < 0:
			_fail(error)
			return
		total += unpacked
		completed_archives += 1
	states[current] = "ready"
	var expected := int(groups[current].get("unpacked_bytes", 0))
	if expected > 0 and total != expected:
		_fail("The extracted game files do not match this build.")
		return
	sizes[current] = total
	if current != "startup": live_bytes += total
	touched[current] = Time.get_ticks_msec()
	current = ""
	busy = false
	_evict()

func _archive_ready(args: Array) -> void:
	_archive_response = [bool(args[0]), str(args[1])]
	archive_ready.emit(bool(args[0]), str(args[1]))

func _fail(message: String) -> void:
	error = message
	errors[current] = message
	states[current] = "failed"
	_remove_files(current)
	current = ""
	busy = false
	DirAccess.remove_absolute(archive_path)

func _destination(entry: String) -> String:
	if ".." in entry.split("/") or "\\" in entry or ":" in entry or entry.begins_with("/"):
		return ""
	if not (entry.begins_with("godot-client/assets/") or entry.begins_with("eloria-assets/")): return ""
	var logical := ("res://" + entry.trim_prefix("godot-client/")) if entry.begins_with("godot-client/") else "res://../" + entry
	var path := ProjectSettings.globalize_path(logical)
	if path.begins_with("res://"): path = path.trim_prefix("res://")
	if not path.is_absolute_path(): path = "/".path_join(path)
	return path.simplify_path()

func _unpack(expected: String, expected_bytes := -1) -> int:
	await get_tree().process_frame
	var input := FileAccess.open(archive_path, FileAccess.READ)
	if input == null or (expected_bytes >= 0 and input.get_length() != expected_bytes):
		if input != null: input.close()
		error = "Game download is incomplete or outdated."
		return -1
	input.close()
	if _take_archive_proof(expected, expected_bytes):
		_archive_proof_hits += 1
		_archive_proof_bytes += expected_bytes
	else:
		var hash_began := Time.get_ticks_usec()
		var actual := FileAccess.get_sha256(archive_path)
		_archive_sha_usec += Time.get_ticks_usec() - hash_began
		_archive_sha_checks += 1
		if actual != expected:
			error = "Game download is incomplete or outdated."
			return -1
	var zip := ZIPReader.new()
	if zip.open(archive_path) != OK:
		error = "Cannot open downloaded game files."
		return -1
	var bytes := 0
	var slice := Time.get_ticks_usec()
	var slice_usec := _unpack_slice_usec()
	for entry: String in zip.get_files():
		if entry.ends_with("/"): continue
		var offset := -1
		var logical := entry
		var marker := entry.rfind(".__rlpart_")
		if marker >= 0:
			var position := entry.substr(marker + 10)
			if position.length() != 12 or not position.is_valid_int():
				error = "Invalid game asset piece."
				zip.close()
				return -1
			offset = position.to_int()
			if offset < 0:
				error = "Invalid game asset piece offset."
				zip.close()
				return -1
			logical = entry.substr(0, marker)
		var destination := _destination(logical)
		if destination.is_empty() or DirAccess.make_dir_recursive_absolute(destination.get_base_dir()) != OK:
			error = "Invalid game asset folder."
			zip.close()
			return -1
		var file := FileAccess.open(destination, FileAccess.READ_WRITE if offset > 0 else FileAccess.WRITE)
		if file == null:
			error = "Cannot prepare a game asset."
			zip.close()
			return -1
		if offset > 0:
			if file.get_length() != offset:
				error = "Invalid game asset piece order."
				file.close()
				zip.close()
				return -1
			file.seek_end()
		var buffer := zip.read_file(entry)
		file.store_buffer(buffer)
		file.close()
		bytes += buffer.size()
		if offset <= 0:
			(files[current] as Array).append(destination)
			_source_paths[destination] = "res://" + logical.trim_prefix("godot-client/") if logical.begins_with("godot-client/") else "res://../" + logical
		if Time.get_ticks_usec() - slice >= slice_usec:
			_unpack_yields += 1
			await get_tree().process_frame
			slice = Time.get_ticks_usec()
	zip.close()
	DirAccess.remove_absolute(archive_path)
	return bytes

func _remove_files(id: String) -> void:
	var aliases := PackedStringArray()
	for path: String in files.get(id, []):
		aliases.append(path)
		# Web exports can have an empty resource root. Supply the original
		# resource alias as well as the concrete MEMFS path for parsed caches.
		if _source_paths.has(path): aliases.append(str(_source_paths[path]))
	files_evicted.emit(aliases)
	for path: String in files.get(id, []): DirAccess.remove_absolute(path)
	for path: String in files.get(id, []): _source_paths.erase(path)
	files.erase(id)
	if id != "startup": live_bytes -= int(sizes.get(id, 0))
	sizes.erase(id)

func _evict() -> void:
	if live_bytes <= budget_bytes: return
	var protected := {"startup":true}
	for owner: Dictionary in pins.values(): protected.merge(owner)
	var candidates: Array[String] = []
	for id: String in states:
		# Give a preloader one scheduling turn to claim newly delivered files.
		if states[id] == "ready" and not protected.has(id) \
				and Time.get_ticks_msec() - int(touched.get(id, 0)) > READY_GRACE_MSEC:
			candidates.append(id)
	candidates.sort_custom(func(a: String, b: String) -> bool: return int(touched.get(a, 0)) < int(touched.get(b, 0)))
	for id: String in candidates:
		if live_bytes <= budget_bytes: break
		_remove_files(id)
		states.erase(id)
		_evictions += 1

func snapshot() -> Dictionary:
	return {"busy":busy, "current":current, "queued":queue.size(), "error":error,
		"failed_groups":errors.keys(),
		"live_bytes":live_bytes, "budget_bytes":budget_bytes, "over_budget":live_bytes > budget_bytes,
		"evictions":_evictions, "completed_archives":completed_archives,
		"archive_proof_hits":_archive_proof_hits, "archive_sha_checks":_archive_sha_checks,
		"archive_proof_bytes":_archive_proof_bytes,
		"archive_sha_usec":_archive_sha_usec, "unpack_yields":_unpack_yields,
		"unpack_slice_usec":_unpack_slice_usec()}
