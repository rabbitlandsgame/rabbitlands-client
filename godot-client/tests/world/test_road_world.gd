extends SceneTree
## Real published leaves exercise raw loading, worker publication and live look changes.
const Road := preload("res://src/world/road_ground/road_ground.gd")
const TERRITORY := "res://../eloria-assets/maps/continent-v2/landfall/client/world.json"
const ROAD_CHUNK := "07_09"
var failures: Array[String] = []
var checks := 0

func _init() -> void:
	_run.call_deferred()

func _expect(ok: bool, label: String) -> void:
	checks += 1
	if not ok: failures.append(label)

func _worker(path: String) -> WorldLoader:
	return WorldLoader.prepare_detached(path, false)

## The normal raw exterior worker primes a private territory, whose child
## loaders are released on that same worker. Retain one real road leaf so this
## regression does not need to parse a whole territory or rewrite its assets.
func _nested_worker() -> WorldLoader:
	var manifest := WorldManifest.load_file(TERRITORY)
	var selected: Array[Dictionary] = []
	for entry: Dictionary in manifest.data.streamingChunks.chunks:
		if str(entry.id) == ROAD_CHUNK:
			selected.append(entry)
	manifest.data.streamingChunks.chunks = selected
	var stream := ContinentChunkStream.new()
	stream.configure(manifest, false)
	var builder := WorldLoader.new()
	builder.detached_build = true
	builder.manifest = manifest
	builder.world_root = stream
	builder.add_child(stream)
	if not stream.entries.is_empty():
		var bounds: Dictionary = stream.entries[0].bounds
		var low: Array = bounds.min
		var high: Array = bounds.max
		stream.prime(Vector3((float(low[0]) + float(high[0])) * 0.5,
			(float(low[1]) + float(high[1])) * 0.5, (float(low[2]) + float(high[2])) * 0.5))
	return builder

func _nested_publication() -> void:
	var previous_mode := OS.get_environment("RABBITLANDS_PREPARED_CONTENT")
	var previous_geometry := OS.get_environment("ELORIA_NO_GEOMETRY_CACHE")
	OS.set_environment("RABBITLANDS_PREPARED_CONTENT", "raw")
	OS.set_environment("ELORIA_NO_GEOMETRY_CACHE", "1")
	for scenario: String in ["publish", "stale", "changed_dependency"]:
		var thread := Thread.new()
		_expect(thread.start(_nested_worker) == OK, "raw nested territory worker starts: " + scenario)
		while thread.is_alive(): await process_frame
		var builder := thread.wait_to_finish() as WorldLoader
		var stream := builder.world_root as ContinentChunkStream
		_expect(stream != null and stream.cells.has(ROAD_CHUNK),
			"raw nested worker retains the road chunk instead of rejecting its publication")
		if stream == null or not stream.cells.has(ROAD_CHUNK):
			builder.unload_world()
			builder.free()
			continue
		var cell: Dictionary = stream.cells[ROAD_CHUNK]
		var imported := cell.root as Node3D
		var prepared: Dictionary = cell.get("pending_road_ground", {})
		_expect(not prepared.is_empty() and not imported.has_meta(Road.META),
			"worker keeps decoded fields private until main publication")
		var mesh_count := imported.find_children("*", "MeshInstance3D", true, false).size()
		var data: Resource = prepared.get("data") as Resource
		if scenario == "changed_dependency" and data != null:
			# Change only the captured proof; never touch a production source.
			data.dependencies["user://missing-road-publication-dependency"] = "0".repeat(64)
		var resident := builder.release_world(true, scenario != "stale")
		builder.free()
		if scenario == "publish":
			_expect(stream.cells.has(ROAD_CHUNK) and cell.root == imported
				and imported.find_children("*", "MeshInstance3D", true, false).size() == mesh_count,
				"main publication preserves the worker's exact prepared geometry")
			_expect(imported.has_meta(Road.META) and imported.get_meta(Road.META).data == data
				and not cell.has("pending_road_ground"),
				"main binds the existing decoded fields once and consumes the private handoff")
			stream.publish_prepared_roads()
			_expect(imported.get_meta(Road.META).data == data and stream._retry_after.is_empty(),
				"repeated publication does not rebuild or mark a valid chunk failed")
		elif scenario == "stale":
			_expect(not imported.has_meta(Road.META) and not prepared.is_empty(),
				"stale parent release never binds or publishes private child fields")
		else:
			_expect(stream.cells.is_empty() and not is_instance_valid(imported)
				and stream._retry_after.has(ROAD_CHUNK),
				"main revalidates road sources and rejects the changed child before display")
		(resident.root as Node).free()
		for frame: int in 4: await process_frame
	if previous_mode.is_empty(): OS.unset_environment("RABBITLANDS_PREPARED_CONTENT")
	else: OS.set_environment("RABBITLANDS_PREPARED_CONTENT", previous_mode)
	if previous_geometry.is_empty(): OS.unset_environment("ELORIA_NO_GEOMETRY_CACHE")
	else: OS.set_environment("ELORIA_NO_GEOMETRY_CACHE", previous_geometry)

func _verify(loader: WorldLoader) -> void:
	_expect(is_instance_valid(loader.world_root), "world root exists")
	if not is_instance_valid(loader.world_root): return
	_expect(loader.world_root.has_meta(Road.META), "fields bound during main publication")
	if not loader.world_root.has_meta(Road.META): return
	var data: Resource = loader.world_root.get_meta(Road.META).data
	_expect(loader.manifest.road_ground_verified.size() == data.dependencies.size(), "cache proof includes exact road closure")
	var node_count := loader.world_root.find_children("*", "Node", true, false).size()
	var old_mode := LookProfile.player_mode()
	for mode: int in [LookProfile.Mode.ORIGINAL, LookProfile.Mode.PAINTED_GROUND, LookProfile.Mode.FULL_PAINTED]:
		LookProfile.set_player_mode(mode)
		LookSwitch.sync(loader.world_root, loader.manifest)
		_expect(loader.world_root.get_meta(Road.META).data == data, "live look retains decoded fields")
		_expect(loader.world_root.find_children("*", "Node", true, false).size() == node_count, "live look adds no nodes")
		for target: Dictionary in data.document.targets:
			var node := loader.world_root.find_child(str(target.name), true, false) as MeshInstance3D
			_expect(node != null, "retained terrain target exists")
			if node == null: continue
			for surface: int in node.mesh.get_surface_count():
				var material := node.get_active_material(surface) as ShaderMaterial
				_expect(material != null and material.has_meta(Road.MATERIAL_META) and material.next_pass == null,
					"road occupies existing single ground pass in every look")
	LookProfile.set_player_mode(old_mode)
	LookSwitch.sync(loader.world_root, loader.manifest)

func _run() -> void:
	var paths := PackedStringArray([
		"res://../eloria-assets/maps/continent-v2/suncoil/client/chunks/06_09/world.json",
		"res://../eloria-assets/maps/continent-v2/landfall/client/chunks/07_09/world.json"])
	for path: String in paths:
		var loader := WorldLoader.new()
		root.add_child(loader)
		loader.load_world(path)
		_verify(loader)
		loader.unload_world()
		loader.queue_free()
		for frame: int in 4: await process_frame
		var thread := Thread.new()
		_expect(thread.start(_worker.bind(path)) == OK, "worker starts")
		while thread.is_alive(): await process_frame
		var builder := thread.wait_to_finish() as WorldLoader
		_expect(builder != null, "worker returns private loader")
		if builder != null:
			if builder.world_root != null:
				_expect(not builder.world_root.has_meta(Road.META), "worker defers field publication")
			var resident := builder.release_world()
			builder.free()
			var adopted := WorldLoader.new()
			root.add_child(adopted)
			adopted.adopt_world(resident)
			_verify(adopted)
			adopted.unload_world()
			adopted.queue_free()
		for frame: int in 4: await process_frame
	await _nested_publication()
	print(JSON.stringify({"checks": checks, "failures": failures}))
	quit(0 if failures.is_empty() else 1)
