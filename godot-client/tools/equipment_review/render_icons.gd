extends SceneTree
## Render existing fitted equipment through the client actor; no model generation.
## Godot --path godot-client --script res://tools/equipment_review/render_icons.gd -- --out <folder> [--keys 5:209,6:249]

var args: Dictionary = {}
var viewport: SubViewport
var stage: Node3D
var actor: ReplicatedActor3D
var camera: Camera3D
var registry: Dictionary
var records: Dictionary = {}
var failures: Array[String] = []


func _init() -> void:
	var values := OS.get_cmdline_user_args()
	for i in range(0, values.size() - 1, 2):
		args[values[i].trim_prefix("--")] = values[i + 1]
	call_deferred("_run")


func _json(path: String) -> Dictionary:
	return JSON.parse_string(FileAccess.get_file_as_string(path)) as Dictionary


func _run() -> void:
	root.size = Vector2i(640, 640)
	viewport = SubViewport.new()
	viewport.size = Vector2i(512, 512)
	viewport.own_world_3d = true
	viewport.transparent_bg = true
	viewport.msaa_3d = Viewport.MSAA_4X
	viewport.render_target_update_mode = SubViewport.UPDATE_ALWAYS
	root.add_child(viewport)
	stage = Node3D.new()
	viewport.add_child(stage)
	var world := WorldEnvironment.new()
	world.environment = Environment.new()
	world.environment.background_mode = Environment.BG_CLEAR_COLOR
	world.environment.ambient_light_source = Environment.AMBIENT_SOURCE_COLOR
	world.environment.ambient_light_color = Color(0.90, 0.94, 1.0)
	world.environment.ambient_light_energy = 0.85
	world.environment.tonemap_mode = Environment.TONE_MAPPER_FILMIC
	stage.add_child(world)
	for setup: Array in [[Vector3(-35, -25, 0), 1.25], [Vector3(-15, 145, 0), 0.6], [Vector3(20, 60, 0), 0.25]]:
		var light := DirectionalLight3D.new()
		light.rotation_degrees = setup[0]
		light.light_energy = float(setup[1])
		stage.add_child(light)
	camera = Camera3D.new()
	camera.projection = Camera3D.PROJECTION_ORTHOGONAL
	camera.near = 0.01
	camera.far = 100.0
	stage.add_child(camera)
	camera.current = true
	registry = _json("res://data/actors/equipment.json")
	var config: Dictionary = _json("res://data/actors/models.json")["models"]["luminous_male"].duplicate(true)
	config["hairStyles"] = []
	if config.has("faceAppearance") and not ResourceLoader.exists(str(config.faceAppearance.get("mask", ""))):
		config.erase("faceAppearance")
	actor = ReplicatedActor3D.new()
	stage.add_child(actor)
	var errors: Array = actor.configure({"actor_id": 9020, "x": 0, "y": 0, "rotation": 0, "kind": 1,
		"name": "", "appearance": {"skin": 0, "eyes": 0, "hair": 0, "shirt": 0, "pants": 0, "boots": 0, "head": 0},
		"equipment_visuals": {}}, CoordinateAdapter.new({"walkingHeight": 0.0}), config,
		_json("res://data/animations/luminous.json"), registry)
	if not errors.is_empty():
		push_error(str(errors))
		quit(1)
		return
	actor.rotation.y = PI
	actor.set_process(false)
	actor.set_physics_process(false)
	actor.apply_render_quality(ActorRenderQuality.QUALITY_NAMES.find("high"), false)
	actor.set_cape_cloth_allowed(false)
	actor.play_action(&"idle", true)
	actor._advance_facing_offset(1.0)
	if actor.animation_player != null and actor.animation_player.has_animation("Idle_Subtle"):
		actor.animation_player.play("Idle_Subtle")
		actor.animation_player.seek(0.3, true)
		actor.animation_player.pause()
	await process_frame
	var out := str(args.get("out", ProjectSettings.globalize_path("res://tools/equipment_review/icons")))
	DirAccess.make_dir_recursive_absolute(out)
	var requested := str(args.get("keys", "")).split(",", false)
	var keys: Array = registry.models.keys()
	keys.sort_custom(func(a: String, b: String) -> bool: return a.naturalnocasecmp_to(b) < 0)
	var old_manifest := out.path_join("manifest.json")
	if FileAccess.file_exists(old_manifest):
		records = _json(old_manifest).get("icons", {})
	var done := 0
	for key: String in keys:
		if not requested.is_empty() and key not in requested:
			continue
		var file := key.replace(":", "_") + ".png"
		if args.get("resume", "no") == "yes" and records.has(key) and FileAccess.file_exists(out.path_join(file)):
			continue
		await _render(key, out.path_join(file))
		done += 1
		if done % 16 == 0:
			print("ICON_PROGRESS ", done, " latest=", key)
			ReplicatedActor3D._equipment_pieces_cache.clear()
			ReplicatedActor3D._rebound_skins.clear()
			GlbSceneCache.clear()
			_write_manifest(old_manifest)
	_write_manifest(old_manifest)
	print("EQUIPMENT_ICONS_OK " if failures.is_empty() else "EQUIPMENT_ICONS_FAILED ",
		records.size(), " records; failures=", failures)
	quit(0 if failures.is_empty() else 1)


func _render(key: String, path: String) -> void:
	var part := int(key.get_slice(":", 0))
	var visual := int(key.get_slice(":", 1))
	var model: Dictionary = registry.models[key]
	var resolved: Dictionary = actor._fit_variant(model)
	var source := str(resolved.get("scene", ""))
	var standalone: Node3D = null
	actor.show()
	actor.apply_equipment_visuals({part: visual})
	if actor.animation_player != null:
		actor.animation_player.play("Idle_Subtle")
		actor.animation_player.seek(0.3, true)
		actor.animation_player.pause()
	if part == 6:
		# Product views need the authored, level pair of soles. A living idle
		# bends one ankle and turns its toe out, disguising the actual boot fit.
		actor.animation_player.stop()
		actor.get_skeleton().reset_bone_poses()
		_parallel_boot_pose()
	actor._advance_facing_offset(1.0)
	await process_frame
	var wanted: Array[MeshInstance3D] = []
	if part == 0 and not actor._ranged_bow_path(resolved).is_empty():
		# These two registered bow meshes are hidden by the actor's animated
		# presentation. Render their existing rigid source directly for the icon.
		standalone = GlbSceneCache.instantiate(source) as Node3D
		if standalone != null:
			stage.add_child(standalone)
			actor.hide()
			for child: Node in standalone.find_children("*", "MeshInstance3D", true, false):
				wanted.append(child as MeshInstance3D)
	else:
		for node: Node in actor._equipment_nodes.get(part, []):
			if node is MeshInstance3D:
				wanted.append(node)
			for child: Node in node.find_children("*", "MeshInstance3D", true, false):
				wanted.append(child as MeshInstance3D)
	# Fitting envelopes cover the wearer in gameplay. Component icons show the
	# authored garment only, without neck skin or generated body/boot liners.
	wanted = wanted.filter(func(mesh: MeshInstance3D) -> bool:
		return mesh.visible and not mesh.has_meta("neck_source") and not mesh.has_meta("equipment_forearm_skin") and not mesh.has_meta("suppress_generated_backing") and not str(mesh.name).contains("_Generated"))
	for node: Node in actor.find_children("*", "MeshInstance3D", true, false):
		(node as MeshInstance3D).visible = node in wanted
	# The client hides socketed bows while its animated bow presentation owns
	# them. Icon isolation renders the registered component itself, so reveal
	# its attachment parents as well as its mesh.
	for mesh: MeshInstance3D in wanted:
		var parent: Node = mesh
		while parent != actor and parent != stage and parent != null:
			if parent is Node3D:
				(parent as Node3D).visible = true
			parent = parent.get_parent()
	var points: PackedVector3Array = PackedVector3Array()
	for mesh: MeshInstance3D in wanted:
		if mesh.mesh != null and mesh.visible:
			points.append_array(_posed_points(mesh))
	if points.is_empty():
		failures.append(key + ": no equipment mesh")
		return
	var bounds := AABB(points[0], Vector3.ZERO)
	for point: Vector3 in points:
		bounds = bounds.expand(point)
	var focus := bounds.get_center()
	var direction := Vector3(0.28, 0.13, 1.0).normalized()
	if part in [2, 8]:
		direction = Vector3(-0.35, 0.12, -1.0).normalized()
	elif part == 6:
		direction = Vector3(0.6, 0.25, 1.0).normalized()
	camera.position = focus + direction * 5.0
	camera.look_at(focus)
	var view := camera.global_transform.affine_inverse()
	var low := Vector2(INF, INF)
	var high := Vector2(-INF, -INF)
	for point: Vector3 in points:
		var p := view * point
		low = low.min(Vector2(p.x, p.y))
		high = high.max(Vector2(p.x, p.y))
	var middle := (low + high) * 0.5
	camera.position += camera.global_basis.x * middle.x + camera.global_basis.y * middle.y
	camera.size = maxf(high.x - low.x, high.y - low.y) * 1.18
	for frame in range(3):
		await RenderingServer.frame_post_draw
	var image := viewport.get_texture().get_image()
	var used := image.get_used_rect()
	if used.size.x == 0 or used.size.y == 0:
		failures.append(key + ": empty render")
		records.erase(key)
		if standalone != null:
			standalone.queue_free()
		return
	var error := image.save_png(path)
	if error != OK:
		failures.append(key + ": " + error_string(error))
		return
	records[key] = {"file": path.get_file(), "size": [512, 512], "transparent": true,
		"sha256": FileAccess.get_sha256(path), "scene": source,
		"scene_sha256": FileAccess.get_sha256(source), "mesh_count": wanted.size(),
		"pose": "Idle_Subtle at 0.3 seconds; luminous_male client fit",
		"camera_size": camera.size}
	if standalone != null:
		records[key]["pose"] = "registered rigid bow source; native rest shape"
		standalone.queue_free()
	elif part == 6:
		records[key]["pose"] = "canonical bind pose with whole legs turned to parallel toes; luminous_male client fit"


func _parallel_boot_pose() -> void:
	var skeleton := actor.get_skeleton()
	var world_basis := skeleton.global_basis.orthonormalized()
	for side: String in ["l", "r"]:
		var foot := skeleton.find_bone("foot_" + side)
		var ball := skeleton.find_bone("ball_" + side)
		var thigh := skeleton.find_bone("thigh_" + side)
		var direction := world_basis * (skeleton.get_bone_global_pose(ball).origin - skeleton.get_bone_global_pose(foot).origin)
		var yaw := atan2(direction.x, direction.z)
		var pose := skeleton.get_bone_global_pose(thigh)
		var turn := world_basis.inverse() * Basis(Vector3.UP, -yaw) * world_basis
		var parent := skeleton.get_bone_global_pose(skeleton.get_bone_parent(thigh))
		skeleton.set_bone_pose_rotation(thigh, (parent.basis.inverse() * turn * pose.basis).get_rotation_quaternion())
	# Turn complete legs, so the calf and foot keep the same ankle angle.
	# Rotating feet alone would manufacture a kink in a rigid greave.


func _posed_points(instance: MeshInstance3D) -> PackedVector3Array:
	var result := PackedVector3Array()
	var skeleton := instance.get_node_or_null(instance.skeleton) as Skeleton3D
	var transforms: Array[Transform3D] = []
	if skeleton != null and instance.skin != null:
		for bind in range(instance.skin.get_bind_count()):
			var bone := instance.skin.get_bind_bone(bind)
			if bone < 0:
				bone = skeleton.find_bone(instance.skin.get_bind_name(bind))
			transforms.append(skeleton.global_transform * skeleton.get_bone_global_pose(bone) * instance.skin.get_bind_pose(bind) if bone >= 0 else instance.global_transform)
	for surface in range(instance.mesh.get_surface_count()):
		var arrays := instance.mesh.surface_get_arrays(surface)
		var vertices: PackedVector3Array = arrays[Mesh.ARRAY_VERTEX]
		var bones: Variant = arrays[Mesh.ARRAY_BONES]
		var weights: Variant = arrays[Mesh.ARRAY_WEIGHTS]
		var skinned: bool = not transforms.is_empty() and bones != null and weights != null and vertices.size() > 0
		var influences := int(bones.size() / vertices.size()) if skinned else 0
		# Shared GLB arrays can retain removed feet, hands or backing vertices.
		# Frame only drawn triangles, including narrow plumes and ornaments.
		var used := {}
		if arrays[Mesh.ARRAY_INDEX] is PackedInt32Array:
			for index: int in arrays[Mesh.ARRAY_INDEX]:
				used[index] = true
		else:
			for index: int in vertices.size():
				used[index] = true
		for i: int in used:
			var point := instance.global_transform * vertices[i]
			if skinned:
				point = Vector3.ZERO
				for j in range(influences):
					var weight := float(weights[i * influences + j])
					var bone := int(bones[i * influences + j])
					if weight > 0.0 and bone >= 0 and bone < transforms.size():
						point += (transforms[bone] * vertices[i]) * weight
			result.append(point)
	return result


func _write_manifest(path: String) -> void:
	var file := FileAccess.open(path, FileAccess.WRITE)
	file.store_string(JSON.stringify({"schema": 1, "product": "Rabbit Lands",
		"renderer": "existing client actor and fitted equipment; transparent 512px SubViewport",
		"renderer_sha256": FileAccess.get_sha256("res://tools/equipment_review/render_icons.gd"),
		"icons": records, "failures": failures}, "\t") + "\n")
