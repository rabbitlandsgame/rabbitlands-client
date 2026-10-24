extends SceneTree
const Prepared := preload("res://src/world/prepared_content.gd")
const Lifecycle := preload("res://src/world/prepared_scene_lifecycle.gd")
const DIRECTORY := "user://prepared-content-fixture"
const SOURCE := DIRECTORY + "/input.glb"
const CATALOG := DIRECTORY + "/index.json"
const TOKEN := "fixture-full-format7"
var failures := 0

func _init() -> void:
	_run.call_deferred()

func _expect(value: bool, message: String) -> void:
	if value:
		print("PASS: ", message)
	else:
		failures += 1
		push_error("FAIL: " + message)

func _write(path: String, value: String) -> void:
	var output := FileAccess.open(path, FileAccess.WRITE)
	output.store_string(value)
	output.close()

func _catalog(entry: Dictionary) -> void:
	_write(CATALOG, JSON.stringify({"schema_version": Prepared.SCHEMA,
		"policy": Prepared.COOK_POLICY, "entries": [entry]}))

func _native_scene(identity: String) -> Dictionary:
	var source := Node3D.new()
	source.name = identity
	var floor := StaticBody3D.new()
	floor.name = "NavigationSurface"
	floor.collision_layer = WorldLoader.NAVIGATION_SURFACE_LAYER
	var shape := CollisionShape3D.new()
	shape.shape = BoxShape3D.new()
	source.add_child(floor)
	floor.add_child(shape)
	floor.owner = source
	shape.owner = source
	var scene := PackedScene.new()
	var pack_error := scene.pack(source)
	source.free()
	_expect(pack_error == OK, "synthetic native scene packs on main")
	var staging := DIRECTORY + "/writing.scn"
	_expect(ResourceSaver.save(scene, staging) == OK, "synthetic native scene saves")
	var sha := FileAccess.get_sha256(staging)
	var path := DIRECTORY.path_join(sha + ".scn")
	if FileAccess.file_exists(path):
		DirAccess.remove_absolute(staging)
	else:
		_expect(DirAccess.rename_absolute(staging, path) == OK, "native payload uses its complete content hash")
	return {"path": path, "sha256": sha}

func _entry(payload: Dictionary) -> Dictionary:
	var sha := FileAccess.get_sha256(SOURCE)
	var result := {"kind": "world", "source": SOURCE, "source_digest": sha,
		"texture_token": TOKEN, "engine_policy": Prepared.engine_policy(),
		"resource": payload.path,
		"inputs": [{"path": SOURCE, "sha256": sha}], "payloads": [payload],
		"shared_images": {}, "shared_meshes": {},
		"metadata_json": Prepared.encode_metadata({"numeric_roundtrip": [1,
			{"vertices": 3, "scale": 0.17364817766693033,
			"rest": [-0.172595977783203125, 0.172595977783203125, 2.98023223876953125e-08]}]})}
	result["entry_id"] = Prepared.entry_identity(result)
	return result

func _acquire(source_digest: String, mode := "auto", token := TOKEN) -> Dictionary:
	return Prepared.acquire("world", SOURCE, source_digest, token, mode, CATALOG)

func _worker_read(source_digest: String) -> Dictionary:
	var result := _acquire(source_digest)
	return {"status": result.status, "packed": result.get("resource") is PackedScene,
		"thread": OS.get_thread_caller_id()}

func _lifecycle_isolation() -> void:
	var root := Node3D.new()
	var mesh := BoxMesh.new()
	var material := StandardMaterial3D.new()
	material.albedo_color = Color.RED
	mesh.material = material
	var source := MeshInstance3D.new()
	source.name = "Member"
	source.mesh = mesh
	root.add_child(source)
	source.owner = root
	var multimesh := MultiMesh.new()
	multimesh.transform_format = MultiMesh.TRANSFORM_3D
	multimesh.mesh = mesh
	multimesh.instance_count = 1
	multimesh.set_instance_transform(0, Transform3D(Basis.IDENTITY, Vector3(3, 2, 1)))
	var batch := MultiMeshInstance3D.new()
	batch.name = "Batch"
	batch.multimesh = multimesh
	root.add_child(batch)
	batch.owner = root
	var packed := PackedScene.new()
	_expect(packed.pack(root) == OK, "isolation fixture packs")
	root.free()
	var record := {"status": "hit", "resource": packed, "entry": {}}
	var first := Lifecycle.instantiate(record)
	var second := Lifecycle.instantiate(record)
	_expect(first != null and second != null, "native lifecycle creates independent scene instances")
	if first == null or second == null:
		if first != null: first.free()
		if second != null: second.free()
		return
	var a := first.get_node("Batch") as MultiMeshInstance3D
	var b := second.get_node("Batch") as MultiMeshInstance3D
	a.multimesh.set_instance_transform(0, Transform3D(Basis.IDENTITY, Vector3(99, 0, 0)))
	_expect(b.multimesh.get_instance_transform(0).origin == Vector3(3, 2, 1)
		and multimesh.get_instance_transform(0).origin == Vector3(3, 2, 1),
		"non-pooled batch fade transform cannot mutate another instance or template")
	var member_a := first.get_node("Member") as MeshInstance3D
	var member_b := second.get_node("Member") as MeshInstance3D
	(member_a.get_active_material(0) as StandardMaterial3D).albedo_color = Color.BLUE
	_expect((member_b.get_active_material(0) as StandardMaterial3D).albedo_color == Color.RED
		and material.albedo_color == Color.RED,
		"per-instance material mutation cannot change another instance or native template")
	first.free()
	second.free()

func _script_preflight() -> void:
	var script := GDScript.new()
	script.source_code = "extends Node3D\nfunc _init():\n\tEngine.set_meta('prepared_script_ran', true)\n"
	_expect(script.reload() == OK, "script preflight fixture compiles")
	var root := Node3D.new()
	root.set_script(script)
	var packed := PackedScene.new()
	_expect(packed.pack(root) == OK, "script preflight fixture packs")
	root.free()
	if Engine.has_meta("prepared_script_ran"):
		Engine.remove_meta("prepared_script_ran")
	var instance := Lifecycle.instantiate({"status": "hit", "resource": packed, "entry": {}})
	_expect(instance == null and not Engine.has_meta("prepared_script_ran"),
		"unexpected Node script is rejected before its initializer can run")
	if instance != null:
		instance.free()
	if Engine.has_meta("prepared_script_ran"):
		Engine.remove_meta("prepared_script_ran")

func _run() -> void:
	_expect(Prepared._resource_root("", "C:/fixture/app/RabbitLands.exe") == "C:/fixture/app",
		"PCK template with an empty resource root uses its executable directory")
	_expect(Prepared._resource_root("C:/fixture/project/", "C:/engine/Godot.exe") == "C:/fixture/project",
		"editor project keeps its actual project root")
	_expect(Prepared.logical_source("res://assets/world/fixture.glb") == "godot-client/assets/world/fixture.glb"
		and Prepared.logical_source("res://../eloria-assets/maps/fixture/world.glb") == "eloria-assets/maps/fixture/world.glb"
		and Prepared.logical_source("res://../../outside.glb").is_empty(),
		"virtual project and sibling asset scopes normalize without accepting an escape")
	_lifecycle_isolation()
	_script_preflight()
	DirAccess.make_dir_recursive_absolute(DIRECTORY)
	_write(SOURCE, "source-v1")
	var payload := _native_scene("OriginalRoot")
	var entry := _entry(payload)
	_catalog(entry)
	var sha := FileAccess.get_sha256(SOURCE)
	_expect(str(_acquire(sha, "raw").reason) == "disabled", "raw selector does not read prepared content")
	var loaded := _acquire(sha)
	_expect(str(loaded.status) == "hit" and loaded.resource is PackedScene,
		"exact native variant is source/payload verified before loading")
	_expect(loaded.get("entry") is Dictionary
		and loaded.entry.get("metadata") is Dictionary
		and str(loaded.entry.metadata_json) == str(entry.metadata_json)
		and Prepared.entry_identity(loaded.entry) == str(entry.entry_id),
		"verified entry retains exact authoritative float wire String and decoded convenience view")
	var alias_damage: Dictionary = loaded.entry.duplicate(true)
	alias_damage.metadata.numeric_roundtrip[1]["vertices"] = 4
	_expect(Prepared.entry_identity(alias_damage).is_empty(),
		"mutated decoded runtime alias cannot retain the authoritative entry identity")
	var instance := Lifecycle.instantiate(loaded)
	_expect(instance != null and instance.name == &"OriginalRoot"
		and instance.get_child(0) is StaticBody3D
		and (instance.get_child(0) as StaticBody3D).collision_layer == WorldLoader.NAVIGATION_SURFACE_LAYER,
		"main adapter retains native root naming and structural/navigation ownership")
	if instance != null:
		instance.free()
	_expect(str(_acquire(sha, "auto", "fixture-half-format7").reason) == "variant_missing",
		"missing texture tier never substitutes a full-quality baked scene")
	_expect(str(_acquire(sha, "require-pilot", "fixture-half-format7").status) == "reject",
		"required listed pilot refuses silent raw fallback")
	var stale := entry.duplicate(true)
	stale.engine_policy.hash = "wrong-engine"
	_catalog(stale)
	_expect(str(_acquire(sha).reason) == "engine_or_cook_policy", "foreign engine policy cannot load")
	_catalog(entry)
	var metadata_damage := entry.duplicate(true)
	metadata_damage["metadata_json"] = str(metadata_damage.metadata_json) + " "
	_catalog(metadata_damage)
	_expect(str(_acquire(sha).reason) == "entry_identity_mismatch", "even metadata wire whitespace remains covered by exact entry identity")
	var ambiguous := entry.duplicate(true)
	ambiguous["metadata"] = JSON.parse_string(str(entry.metadata_json))
	_catalog(ambiguous)
	_expect(str(_acquire(sha).reason) == "catalog_metadata_representation",
		"stored decoded alias is rejected even if it agrees with the authoritative String")
	var invalid_metadata := entry.duplicate(true)
	invalid_metadata["metadata_json"] = "[]"
	invalid_metadata.entry_id = Prepared.entry_identity(invalid_metadata)
	_catalog(invalid_metadata)
	_expect(str(_acquire(sha).reason) == "metadata_json_invalid",
		"identity-valid non-object metadata cannot become a runtime view")
	var legacy_metadata := entry.duplicate(true)
	legacy_metadata.erase("metadata_json")
	legacy_metadata["metadata"] = {"legacy": true}
	legacy_metadata.entry_id = Prepared.entry_identity(legacy_metadata)
	_catalog(legacy_metadata)
	_expect(str(_acquire(sha).reason) == "catalog_metadata_representation",
		"old numeric Dictionary catalog requires a fresh cook rather than a hash exemption")
	_catalog(entry)
	# Identical path, length and expected source identity: a previously successful
	# load cannot authorize the replacement bytes. No verification cache is used.
	_write(SOURCE, "source-v2")
	_expect(str(_acquire(sha).reason) == "input_hash_mismatch", "same-size source replacement fails after a prior hit")
	_write(SOURCE, "source-v1")
	var unsafe := entry.duplicate(true)
	unsafe.payloads[0].path = DIRECTORY + "/../outside.scn"
	unsafe.entry_id = Prepared.entry_identity(unsafe)
	_catalog(unsafe)
	_expect(str(_acquire(sha).reason) == "payload_path_or_digest", "native payload cannot escape its catalog namespace")
	_catalog(entry)
	# Corruption is rejected without invoking the native parser, which would
	# otherwise print an unexpected engine error before fallback was possible.
	var bytes := FileAccess.get_file_as_bytes(payload.path)
	var damaged := bytes.duplicate()
	damaged[damaged.size() - 1] = damaged[damaged.size() - 1] ^ 1
	var output := FileAccess.open(payload.path, FileAccess.WRITE)
	output.store_buffer(damaged)
	output.close()
	_expect(str(_acquire(sha).reason) == "payload_hash_mismatch", "corrupt native bytes never reach ResourceLoader")
	output = FileAccess.open(payload.path, FileAccess.WRITE)
	output.store_buffer(bytes)
	output.close()
	# Worker reads publish only an immutable resource record. Node construction
	# above and all source node pack/free operations remain on main.
	var worker := Thread.new()
	var started := worker.start(_worker_read.bind(sha))
	_expect(started == OK, "immutable native resource read starts on worker")
	if started != OK:
		quit(1)
		return
	var deadline := Time.get_ticks_msec() + 5000
	while worker.is_alive() and Time.get_ticks_msec() < deadline:
		await process_frame
	if worker.is_alive():
		_expect(false, "native resource read completes while main continues serving frames")
		quit(1)
		return
	var result: Dictionary = worker.wait_to_finish()
	_expect(str(result.status) == "hit" and bool(result.packed)
		and int(result.thread) != OS.get_main_thread_id(),
		"worker completion carries PackedScene data rather than a private Node tree")
	loaded.clear()
	entry.clear()
	for _frame: int in 3:
		await process_frame
	print("prepared content: ", "PASS" if failures == 0 else "FAIL")
	quit(failures)
