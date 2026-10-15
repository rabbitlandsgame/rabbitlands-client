extends SceneTree

func _init() -> void:
	call_deferred("_run")

func _run() -> void:
	var scene = load("res://main.tscn").instantiate()
	root.add_child(scene)
	await physics_frame
	await physics_frame
	var failures := 0
	for target: Dictionary in scene.q.layout.targets:
		var tile := Vector2i(target.approach[0],target.approach[1])
		var expected: Vector3 = scene.tile_position(tile)
		var hit: Dictionary = scene.get_world_3d().direct_space_state.intersect_ray(
			PhysicsRayQueryParameters3D.create(expected+Vector3.UP*10,expected-Vector3.UP*2))
		if hit.is_empty() or absf(hit.position.y-expected.y) > .11:
			push_error("Authored floor does not support target: "+str(target.id))
			failures += 1
	var floor_found := false
	for child: Node in scene.get_child(0).get_children():
		if child is MeshInstance3D and str(child.name).begins_with("Walk_"):
			var mat: BaseMaterial3D = child.get_active_material(0)
			floor_found = true
			if not mat.vertex_color_use_as_albedo or not mat.albedo_texture.get_image().has_mipmaps():
				push_error("Terrain blend or texture mipmaps are missing")
				failures += 1
	if not floor_found: failures += 1
	print("Grounding/materials: %d target approaches, %d failures." % [scene.q.layout.targets.size(),failures])
	quit(1 if failures else 0)
