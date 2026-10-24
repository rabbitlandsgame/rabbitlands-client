extends SceneTree
## Actual detached territory -> main install boundary. Tiny synthetic GLBs only.
const Prepared := preload("res://src/world/prepared_content.gd")
const Quantization := preload("res://src/world/gltf_quantization.gd")
const Vram := preload("res://src/world/vram_textures.gd")
const MapExtension := preload("res://src/world/map_mesh_extension.gd")
const DIRECTORY := "user://prepared-stream-publication-fixture"
var failures := 0
var added_meshes := 0
var foreign_tree_adds := 0

func _init() -> void:
	_run.call_deferred()

func _expect(value: bool, message: String) -> void:
	if not value:
		failures += 1
		push_error("prepared stream publication: " + message)

func _added(node: Node) -> void:
	if node is MeshInstance3D:
		added_meshes += 1
		foreign_tree_adds += 1 if OS.get_thread_caller_id() != OS.get_main_thread_id() else 0

func _write_json(path: String, data: Dictionary) -> void:
	var file := FileAccess.open(path, FileAccess.WRITE)
	file.store_string(JSON.stringify(data))
	file.close()

func _manifest(identity: String) -> Dictionary:
	return {"schemaVersion": "1.0.0", "asset": {"id": identity, "glb": "world.glb", "units": "meters",
		"coordinateSystem": {"upAxis": "Y"}, "bounds": {"min": [-2,0,-2], "max": [2,1,2]}},
		"coordinateTransform": {"metresPerTile": 1, "origin": [0,0,0], "serverOrigin": [0,0],
			"walkingHeight": 0, "invertServerY": true}, "spawnPoints": [{"position": [0,0,0]}],
		"collision": {"nodeNames": []}, "navigation": {"surfaceNodePrefixes": ["Terrain_"]}}

func _fixture() -> String:
	DirAccess.make_dir_recursive_absolute(DIRECTORY)
	var source := Node3D.new()
	var ground := MeshInstance3D.new()
	ground.name = "Terrain_Fixture"
	ground.mesh = PlaneMesh.new()
	source.add_child(ground)
	var document := GLTFDocument.new()
	var state := GLTFState.new()
	_expect(document.append_from_scene(source, state) == OK, "valid synthetic terrain encodes")
	_expect(document.write_to_filesystem(state, DIRECTORY.path_join("world.glb")) == OK, "synthetic terrain writes")
	source.free()
	var encoded := FileAccess.get_file_as_bytes(DIRECTORY.path_join("world.glb"))
	var entries: Array[Dictionary] = []
	for identity: String in ["a", "b"]:
		var directory := DIRECTORY.path_join(identity)
		DirAccess.make_dir_recursive_absolute(directory)
		var file := FileAccess.open(directory.path_join("world.glb"), FileAccess.WRITE)
		file.store_buffer(encoded)
		file.close()
		_write_json(directory.path_join("world.json"), _manifest(identity))
		entries.append({"id": identity, "manifest": identity + "/world.json", "estimatedResidentBytes": 1024,
			"bounds": {"min": [-2,0,-2], "max": [2,1,2]}})
	var territory := _manifest("prepared_stream_fixture")
	territory["streamingChunks"] = {"schemaVersion": "1.0", "coordinateSpace": "territory-local",
		"maximumLoadedChunks": 4, "maximumResidentBytes": 1048576, "chunks": entries}
	var path := DIRECTORY.path_join("world.json")
	_write_json(path, territory)
	return path

func _prepare(path: String) -> WorldLoader:
	return WorldLoader.prepare_detached(path, false, PackedStringArray(), Vector3.ZERO)

func _join(thread: Thread) -> WorldLoader:
	for _frame: int in 600:
		if not thread.is_alive():
			return thread.wait_to_finish() as WorldLoader
		await process_frame
	_expect(false, "owned territory worker finishes; strict runner must terminate on timeout")
	return null

func _direct_packed_scene_stays_raw(path: String) -> void:
	GlbSceneCache.clear()
	var key := GlbSceneCache._canonical_path(path)
	var source := Node3D.new()
	source.name = "PreparedTemplateMustNotEscape"
	var packed := PackedScene.new()
	_expect(packed.pack(source) == OK, "direct-access prepared sentinel packs")
	source.free()
	GlbSceneCache._scenes[key] = packed
	GlbSceneCache._prepared_entries[key] = {"source": path}
	var direct := GlbSceneCache.packed_scene(path)
	_expect(direct != null and direct != packed and GlbSceneCache._direct_raw_scenes.get(key) == direct,
		"public PackedScene accessor returns validated legacy scene instead of an unadapted native template")
	var instance: Node = direct.instantiate() if direct != null else null
	_expect(instance != null and str(instance.name) != "PreparedTemplateMustNotEscape",
		"ambient-style direct instantiate cannot bypass native lifecycle/material isolation")
	if instance != null:
		instance.free()
	_expect(GlbSceneCache.cached_scene_count() == 2, "both distinct strong scene entries are counted")
	GlbSceneCache.clear()
	_expect(GlbSceneCache._direct_raw_scenes.is_empty() and GlbSceneCache.cached_scene_count() == 0,
		"session clear releases both accessor representations")
	# An earlier native record is not a publication permit. No user fixture is
	# listed in the production catalog, so auto must build current raw content.
	GlbSceneCache.install_prepared({key: {"status": "hit", "resource": packed, "entry": {"source": path}}})
	_expect(GlbSceneCache._scenes.get(key) != packed and not GlbSceneCache._prepared_entries.has(key),
		"worker record cannot publish an unlisted or aged prepared template")
	GlbSceneCache.clear()
	GlbSceneCache._scenes[key] = packed
	GlbSceneCache._prepared_entries[key] = {"source": path}
	instance = GlbSceneCache.instantiate(path)
	_expect(instance != null and str(instance.name) != "PreparedTemplateMustNotEscape"
		and not GlbSceneCache._prepared_entries.has(key),
		"prepared-aware cache hit revalidates current catalog and falls back before materialization")
	if instance != null:
		instance.free()
	GlbSceneCache.clear()

func _run() -> void:
	var registered := Quantization.ensure_registered() and Vram.ensure_registered() and MapExtension.ensure_registered()
	_expect(registered, "full runtime extension set is registered on main before workers")
	if not registered:
		quit(1)
		return
	var old_mode := OS.get_environment("RABBITLANDS_PREPARED_CONTENT")
	OS.set_environment("RABBITLANDS_PREPARED_CONTENT", "auto")
	var path := _fixture()
	node_added.connect(_added)
	var thread := Thread.new()
	_expect(thread.start(_prepare.bind(path)) == OK, "real detached territory preparation starts")
	var builder: WorldLoader = await _join(thread)
	if builder == null:
		return
	var prepared := builder.world_root as ContinentChunkStream
	_expect(prepared != null and prepared.cells.is_empty() and builder._deferred_stream_arrival.is_finite(),
		"worker publishes only an unprimed territory skeleton and scalar pending arrival")
	var resident := builder.release_world()
	builder.free()
	var imported := resident.root as ContinentChunkStream
	_expect(imported != null and imported.cells.is_empty() and added_meshes == 0,
		"release does not instantiate child scenes before actual main attachment")
	root.add_child(imported)
	_expect(WorldLoader.publish_resident_stream(resident), "attached main owner publishes pending arrival")
	_expect(imported.cells.size() == 2 and added_meshes >= 2 and foreign_tree_adds == 0,
		"actual child terrain installs on main with preserved arrival residency")
	_expect(not (resident.deferred_stream_arrival as Vector3).is_finite()
		and int(resident.phases.get(&"streamPrimePublish", -1)) >= 0,
		"pending prime is consumed once with named actual atomic cost")
	var count := added_meshes
	_expect(WorldLoader.publish_resident_stream(resident) and added_meshes == count,
		"repeated publication cannot duplicate terrain")
	imported.pause_streaming()
	imported.free()
	thread = Thread.new()
	_expect(thread.start(_prepare.bind(path)) == OK, "stale territory fixture starts")
	builder = await _join(thread)
	if builder == null:
		return
	var stale := builder.release_world(true, false)
	builder.free()
	var discarded := stale.root as ContinentChunkStream
	_expect(discarded != null and discarded.cells.is_empty()
		and not (stale.deferred_stream_arrival as Vector3).is_finite() and added_meshes == count,
		"stale completion drops pending prime without any child instantiation")
	discarded.free()
	_direct_packed_scene_stays_raw(DIRECTORY.path_join("a/world.glb"))
	if old_mode.is_empty(): OS.unset_environment("RABBITLANDS_PREPARED_CONTENT")
	else: OS.set_environment("RABBITLANDS_PREPARED_CONTENT", old_mode)
	await process_frame
	await process_frame
	print("prepared stream publication tests: ", "PASS" if failures == 0 else "FAIL")
	quit(1 if failures else 0)
