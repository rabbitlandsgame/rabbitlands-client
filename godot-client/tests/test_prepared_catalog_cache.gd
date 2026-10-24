extends SceneTree
## Fresh catalog bytes, not timestamps or a successful prior acquisition,
## authorize parsed-data reuse. This fixture needs no rendered geometry.
const Prepared := preload("res://src/world/prepared_content.gd")
const DIRECTORY := "user://prepared-catalog-cache-fixture"
const SOURCE := DIRECTORY + "/source.glb"
const CATALOG := DIRECTORY + "/index.json"
const TOKEN := "catalog-cache-fixture"
var failures := 0

func _init() -> void:
	_run.call_deferred()

func _expect(condition: bool, message: String) -> void:
	if condition:
		print("PASS: ", message)
	else:
		failures += 1
		push_error("FAIL: " + message)

func _write(path: String, text: String) -> void:
	var file := FileAccess.open(path, FileAccess.WRITE)
	file.store_string(text)
	file.close()

func _text(entry: Dictionary) -> String:
	return JSON.stringify({"schema_version": Prepared.SCHEMA,
		"policy": Prepared.COOK_POLICY, "entries": [entry]})

func _cache() -> Dictionary:
	return Prepared.snapshot().catalog_cache

func _acquire(sha: String, path := CATALOG) -> Dictionary:
	return Prepared.acquire("scene", SOURCE, sha, TOKEN, "auto", path)

func _run() -> void:
	DirAccess.make_dir_recursive_absolute(DIRECTORY)
	_write(SOURCE, "source-v1")
	var source_sha := FileAccess.get_sha256(SOURCE)
	var root := Node3D.new()
	root.name = "CatalogFixture"
	var packed := PackedScene.new()
	_expect(packed.pack(root) == OK, "data-only catalog fixture packs")
	root.free()
	var temporary := DIRECTORY + "/writing.scn"
	_expect(ResourceSaver.save(packed, temporary) == OK, "catalog fixture payload saves")
	var payload_sha := FileAccess.get_sha256(temporary)
	var payload_path := DIRECTORY.path_join(payload_sha + ".scn")
	if FileAccess.file_exists(payload_path):
		DirAccess.remove_absolute(temporary)
	else:
		_expect(DirAccess.rename_absolute(temporary, payload_path) == OK, "payload path binds its actual SHA-256")
	packed = null
	var entry := {"kind": "scene", "source": SOURCE, "source_digest": source_sha,
		"texture_token": TOKEN, "node_policy": "retain", "engine_policy": Prepared.engine_policy(),
		"resource": payload_path, "inputs": [{"path": SOURCE, "sha256": source_sha}],
		"payloads": [{"path": payload_path, "sha256": payload_sha}],
		"shared_images": {}, "shared_meshes": {},
		"metadata_json": Prepared.encode_metadata({"tag": "A", "nested": {"value": 1}})}
	entry["entry_id"] = Prepared.entry_identity(entry)
	var original_text := _text(entry)
	_write(CATALOG, original_text)
	var before := _cache()
	var first := _acquire(source_sha)
	var second := _acquire(source_sha)
	var after := _cache()
	_expect(str(first.status) == "hit" and str(second.status) == "hit", "cold and warm exact acquisitions succeed")
	_expect(int(after.reads) - int(before.reads) == 2 and int(after.byte_hashes) - int(before.byte_hashes) == 2
		and int(after.json_parses) - int(before.json_parses) == 1
		and int(after.parse_hits) - int(before.parse_hits) == 1,
		"warm acquisition rereads and hashes bytes while avoiding only duplicate JSON parsing")
	first.entry.inputs[0]["sha256"] = "0".repeat(64)
	first.entry.engine_policy["hash"] = "caller-poison"
	first.entry.metadata.nested["value"] = 99
	var unpoisoned := _acquire(source_sha)
	_expect(str(unpoisoned.status) == "hit" and str(unpoisoned.entry.entry_id) == str(entry.entry_id)
		and int(unpoisoned.entry.metadata.nested.value) == 1,
		"returned nested entry and decoded metadata cannot poison cached parsed data")
	_write(SOURCE, "source-v2")
	_expect(str(_acquire(source_sha).reason) == "input_hash_mismatch",
		"a warm catalog never substitutes for fresh source hashing")
	_write(SOURCE, "source-v1")
	var payload_bytes := FileAccess.get_file_as_bytes(payload_path)
	var damaged := payload_bytes.duplicate()
	damaged[damaged.size() - 1] = damaged[damaged.size() - 1] ^ 1
	var output := FileAccess.open(payload_path, FileAccess.WRITE)
	output.store_buffer(damaged)
	output.close()
	_expect(str(_acquire(source_sha).reason) == "payload_hash_mismatch",
		"a warm catalog never substitutes for fresh native payload hashing")
	output = FileAccess.open(payload_path, FileAccess.WRITE)
	output.store_buffer(payload_bytes)
	output.close()
	var changed := entry.duplicate(true)
	changed["metadata_json"] = Prepared.encode_metadata({"tag": "B", "nested": {"value": 1}})
	changed["entry_id"] = Prepared.entry_identity(changed)
	var changed_text := _text(changed)
	_expect(original_text.to_utf8_buffer().size() == changed_text.to_utf8_buffer().size(),
		"changed catalog generation has exactly the same byte length")
	var same_time := false
	# FileAccess exposes whole-second mtime. Observe equal timestamps rather
	# than assuming fast writes cannot cross a second boundary.
	for _attempt: int in 8:
		_write(CATALOG, original_text)
		var prior_time := FileAccess.get_modified_time(CATALOG)
		_write(CATALOG, changed_text)
		if prior_time == FileAccess.get_modified_time(CATALOG):
			same_time = true
			break
	_expect(same_time, "same-length catalog edit also has an observed identical timestamp")
	var changed_result := _acquire(source_sha)
	_expect(str(changed_result.status) == "hit" and str(changed_result.entry.metadata.tag) == "B"
		and str(changed_result.entry.entry_id) == str(changed.entry_id),
		"actual changed bytes select the new generation despite equal size and mtime")
	_write(CATALOG, changed_text.replace(str(changed.entry_id), "f".repeat(64)))
	_expect(str(_acquire(source_sha).reason) == "entry_identity_mismatch",
		"equal-length catalog identity corruption is rejected after a prior cache hit")
	_write(CATALOG, "[]")
	_expect(str(_acquire(source_sha).reason) == "catalog_invalid", "non-object catalog replacement cannot reuse an earlier document")
	_write(CATALOG, "{}")
	_expect(str(_acquire(source_sha).reason) == "catalog_schema", "empty-object schema rejection retains its original reason")
	_expect(DirAccess.remove_absolute(CATALOG) == OK, "warm catalog fixture is removed")
	_expect(str(_acquire(source_sha).reason) == "catalog_missing", "deleted catalog cannot be served from parsed cache")
	_write(CATALOG, changed_text)
	_expect(str(_acquire(source_sha).status) == "hit", "recreated valid catalog is read and verified normally")
	var replacement := CATALOG + ".replacement"
	_write(replacement, original_text)
	DirAccess.remove_absolute(CATALOG)
	_expect(DirAccess.rename_absolute(replacement, CATALOG) == OK, "catalog path receives a different complete file")
	var replaced := _acquire(source_sha)
	_expect(str(replaced.status) == "hit" and str(replaced.entry.metadata.tag) == "A",
		"path replacement exposes the replacement generation rather than stale parsed data")
	for index: int in Prepared.CATALOG_CACHE_PATH_LIMIT + 1:
		var path := DIRECTORY.path_join("empty-%d.json" % index)
		_write(path, JSON.stringify({"schema_version": Prepared.SCHEMA, "policy": Prepared.COOK_POLICY, "entries": []}))
		_expect(str(_acquire(source_sha, path).reason) == "not_listed", "independent catalog remains independently selected")
	_expect(int(_cache().cached_paths) <= Prepared.CATALOG_CACHE_PATH_LIMIT, "parsed catalog retention is bounded across paths")
	var parses_before := int(_cache().json_parses)
	_expect(str(_acquire(source_sha).status) == "hit" and int(_cache().json_parses) == parses_before + 1,
		"least-recently-used catalog is reparsed and fully verified after eviction")
	first.clear()
	second.clear()
	unpoisoned.clear()
	changed_result.clear()
	replaced.clear()
	for _frame: int in 2:
		await process_frame
	print("prepared catalog cache: ", "PASS" if failures == 0 else "FAIL")
	quit(failures)
