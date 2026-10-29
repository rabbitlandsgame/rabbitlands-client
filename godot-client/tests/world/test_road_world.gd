extends SceneTree
## Real published leaves exercise raw loading, worker publication and live look changes.
const Road := preload("res://src/world/road_ground/road_ground.gd")
var failures: Array[String] = []
var checks := 0

func _init() -> void:
	_run.call_deferred()

func _expect(ok: bool, label: String) -> void:
	checks += 1
	if not ok: failures.append(label)

func _worker(path: String) -> WorldLoader:
	return WorldLoader.prepare_detached(path, false)

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
	print(JSON.stringify({"checks": checks, "failures": failures}))
	quit(0 if failures.is_empty() else 1)
