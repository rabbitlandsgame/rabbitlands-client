extends SceneTree
## Same-process Current/MPFB High renderer comparison, opt-in local assets.
const PRESETS = preload("res://src/actors/human_portrait_presets.gd")
var actors: Array[ReplicatedActor3D] = []
var results: Array = []
var stage: Node3D
var camera: Camera3D

func _init() -> void:
	call_deferred("run")

func median(values: Array[float]) -> float:
	values.sort()
	return values[values.size() / 2]

func measure(view: String, mode: String) -> void:
	for _frame: int in 60: await process_frame
	var gpu: Array[float] = []
	var cpu: Array[float] = []
	for _frame: int in 120:
		await process_frame
		await RenderingServer.frame_post_draw
		gpu.append(RenderingServer.viewport_get_measured_render_time_gpu(root.get_viewport_rid()))
		cpu.append(RenderingServer.viewport_get_measured_render_time_cpu(root.get_viewport_rid()))
	var item := {"mode": mode, "view": view, "frames": 120, "gpu_median_ms": median(gpu),
		"render_cpu_median_ms": median(cpu), "gpu_p95_ms": gpu[114],
		"draw_calls": RenderingServer.viewport_get_render_info(root.get_viewport_rid(), RenderingServer.VIEWPORT_RENDER_INFO_TYPE_VISIBLE, RenderingServer.VIEWPORT_RENDER_INFO_DRAW_CALLS_IN_FRAME),
		"rendered_primitives": RenderingServer.viewport_get_render_info(root.get_viewport_rid(), RenderingServer.VIEWPORT_RENDER_INFO_TYPE_VISIBLE, RenderingServer.VIEWPORT_RENDER_INFO_PRIMITIVES_IN_FRAME)}
	results.append(item)
	print("MPFB_COST ", item)

func used_resources() -> Dictionary:
	var meshes := {}
	var textures := {}
	var bytes := 0
	var triangles := 0
	for actor: ReplicatedActor3D in actors:
		for node: Node in actor.find_children("*", "MeshInstance3D", true, false):
			var instance := node as MeshInstance3D
			if not instance.is_visible_in_tree() or instance.mesh == null: continue
			var mesh := instance.mesh
			if not meshes.has(mesh.get_instance_id()):
				meshes[mesh.get_instance_id()] = true
				for surface: int in mesh.get_surface_count():
					var arrays := mesh.surface_get_arrays(surface)
					var indices: PackedInt32Array = arrays[Mesh.ARRAY_INDEX]
					triangles += indices.size() / 3 if not indices.is_empty() else (arrays[Mesh.ARRAY_VERTEX] as PackedVector3Array).size() / 3
					var packed := RenderingServer.mesh_get_surface(mesh.get_rid(), surface)
					for key: String in ["vertex_data", "attribute_data", "skin_data", "index_data", "blend_shape_data"]:
						var buffer: Variant = packed.get(key)
						if buffer is PackedByteArray: bytes += buffer.size()
			for surface: int in mesh.get_surface_count():
				var material := instance.get_active_material(surface)
				var maps: Array = []
				if material is StandardMaterial3D:
					maps = [material.albedo_texture, material.normal_texture, material.roughness_texture, material.ao_texture]
				elif material is ShaderMaterial:
					for uniform: Dictionary in material.shader.get_shader_uniform_list():
						var value: Variant = material.get_shader_parameter(uniform.name)
						if value is Texture2D: maps.append(value)
				for texture: Texture2D in maps:
					if texture == null or textures.has(texture.get_instance_id()): continue
					var image := texture.get_image()
					textures[texture.get_instance_id()] = {"size": [texture.get_width(), texture.get_height()],
						"image_data_bytes": image.get_data_size(), "format": image.get_format()}
	return {"unique_bound_meshes": meshes.size(), "packed_mesh_bytes": bytes,
		"unique_mesh_triangles": triangles, "bound_textures": textures.values()}

func run() -> void:
	root.get_node("Network").block_for_hud_preview()
	var prototype_root := OS.get_environment("RL_MPFB_PROTOTYPE_ROOT")
	var output := OS.get_environment("RL_MPFB_REVIEW_OUTPUT")
	if prototype_root.is_empty() or output.is_empty(): quit(2); return
	DirAccess.make_dir_recursive_absolute(output)
	Engine.max_fps = 0
	DisplayServer.window_set_vsync_mode(DisplayServer.VSYNC_DISABLED)
	root.size = Vector2i(1280, 720)
	stage = Node3D.new()
	root.add_child(stage)
	var world := WorldEnvironment.new()
	world.environment = Environment.new()
	world.environment.background_mode = Environment.BG_COLOR
	world.environment.background_color = Color("1b242b")
	world.environment.ambient_light_source = Environment.AMBIENT_SOURCE_COLOR
	world.environment.ambient_light_energy = 0.7
	stage.add_child(world)
	var light := DirectionalLight3D.new()
	light.rotation_degrees = Vector3(-35, -25, 0)
	light.light_energy = 1.2
	stage.add_child(light)
	camera = Camera3D.new()
	stage.add_child(camera)
	camera.current = true
	camera.cull_mask = 3
	camera.projection = Camera3D.PROJECTION_ORTHOGONAL
	var models: Dictionary = JSON.parse_string(FileAccess.get_file_as_string("res://data/actors/models.json")).models
	var equipment: Dictionary = JSON.parse_string(FileAccess.get_file_as_string("res://data/actors/equipment.json"))
	var animations: Dictionary = JSON.parse_string(FileAccess.get_file_as_string("res://data/animations/luminous.json"))
	RenderingServer.viewport_set_measure_render_time(root.get_viewport_rid(), true)
	var resources := {}
	var loads: Array = []
	for mode: String in ["Current", "MPFB"]:
		for index: int in 16:
			var sex := "female" if index % 2 else "male"
			var model: Dictionary = models["luminous_" + sex].duplicate(true)
			if mode == "MPFB":
				model.scene = prototype_root.path_join(sex).path_join("luminous_" + sex + ".glb")
				model.geometryProfile = "mpfb"
				model.erase("faceAppearance")
				model.erase("skinPalette")
				model.mpfbFaceFrame = JSON.parse_string(FileAccess.get_file_as_string(prototype_root.path_join(sex).path_join("fit.json"))).get("face_frame_head_local", {})
			var actor := ReplicatedActor3D.new()
			actor.apply_render_quality(2, true)
			stage.add_child(actor)
			var start := Time.get_ticks_usec()
			var errors := actor.configure({"actor_id": 9100 + index, "x": 0, "y": 0, "rotation": 0, "kind": 1,
				"name": "", "appearance": PRESETS.appearance("Mira" if sex == "female" else "Rowan"), "equipment_visuals": {}},
				CoordinateAdapter.new(), model, animations, equipment)
			loads.append({"mode": mode, "index": index, "configure_usec": Time.get_ticks_usec() - start})
			if not errors.is_empty(): push_error(str(errors)); quit(1); return
			actor.position = Vector3((float(index % 4) - 1.5) * .85, 0, (float(index / 4) - 1.5) * .95)
			actor.server_target = actor.position
			actor.rotation.y = PI
			actor._advance_facing_offset(1.0)
			actor.play_action(&"idle", true)
			actor.animation_player.seek(.4, true)
			actor.animation_player.pause()
			actor.set_process(false)
			actor.set_physics_process(false)
			for node: Node in actor.get_children():
				if node is Node3D and node.name != "NativeModel": (node as Node3D).hide()
			actors.append(actor)
		camera.size = 3.4
		camera.position = Vector3(0, 2.7, 9)
		camera.look_at(Vector3(0, .9, 0))
		await measure("16 mixed Human full bodies", mode)
		resources[mode] = used_resources()
		for index: int in actors.size(): actors[index].visible = index == 12
		var rig := actors[12].get_skeleton()
		var focus := rig.to_global(rig.get_bone_global_pose(rig.find_bone("Head")).origin) + Vector3(0, .055, 0)
		camera.size = .60
		camera.position = focus + Vector3(.12, .055, 1.4)
		camera.look_at(focus)
		await measure("one close portrait; 15 other actors hidden", mode)
		for actor: ReplicatedActor3D in actors: actor.free()
		actors.clear()
		await process_frame
	FileAccess.open(output.path_join("runtime-cost.json"), FileAccess.WRITE).store_string(JSON.stringify({
		"device": RenderingServer.get_video_adapter_name(), "renderer": RenderingServer.get_current_rendering_method(),
		"viewport": [1280, 720], "quality": "High for both modes, identical light/camera/accepted frozen idle",
		"warmup_frames": 60, "results": results, "bound_resources": resources, "configure_times": loads,
		"limitations": "Viewport render timings, not full game FPS. Bound mesh/texture bytes are distinct from total process VRAM; caches from both modes coexist."}, "  "))
	NativeAnimationImporter.clear()
	GlbSceneCache.clear()
	quit()
