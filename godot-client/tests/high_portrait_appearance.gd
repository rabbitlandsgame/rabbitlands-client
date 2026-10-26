extends SceneTree
## Production actor, production renderer, exact quality restoration and UV2
## anchoring checks. RL_HIGH_PORTRAIT_OUTPUT selects ignored evidence output.
const HIGH := preload("res://src/actors/high_portrait_appearance.gd")
var failures := 0
var checks := 0
var stage: Node3D
var camera: Camera3D
var folder := ""
var results: Array = []

func _init() -> void:
	call_deferred("run")

func expect(ok: bool, label: String) -> void:
	checks += 1
	if not ok:
		failures += 1
		push_error(label)

func run() -> void:
	folder = OS.get_environment("RL_HIGH_PORTRAIT_OUTPUT")
	if folder.is_empty():
		folder = ProjectSettings.globalize_path("res://test-artifacts/high-portraits")
	DirAccess.make_dir_recursive_absolute(folder)
	root.size = Vector2i(720, 720)
	stage = Node3D.new()
	root.add_child(stage)
	var world := WorldEnvironment.new()
	world.environment = Environment.new()
	world.environment.background_mode = Environment.BG_COLOR
	world.environment.background_color = Color("1b242b")
	world.environment.ambient_light_source = Environment.AMBIENT_SOURCE_COLOR
	world.environment.ambient_light_color = Color("b8c3d0")
	world.environment.ambient_light_energy = 0.62
	stage.add_child(world)
	var key := DirectionalLight3D.new()
	key.rotation_degrees = Vector3(-32, -28, 0)
	key.light_energy = 1.15
	key.light_color = Color("ffe9d1")
	stage.add_child(key)
	var fill := DirectionalLight3D.new()
	fill.rotation_degrees = Vector3(-20, 145, 0)
	fill.light_energy = 0.45
	fill.light_color = Color("a1beca")
	stage.add_child(fill)
	camera = Camera3D.new()
	camera.projection = Camera3D.PROJECTION_ORTHOGONAL
	camera.size = 0.48
	camera.current = true
	camera.cull_mask = 3
	stage.add_child(camera)
	var models: Dictionary = JSON.parse_string(FileAccess.get_file_as_string("res://data/actors/models.json")).models
	var equipment: Dictionary = JSON.parse_string(FileAccess.get_file_as_string("res://data/actors/equipment.json"))
	var animation: Dictionary = JSON.parse_string(FileAccess.get_file_as_string("res://data/animations/luminous.json"))
	HIGH.clear()
	for sex: String in ["male", "female"]:
		var slug := "luminous_" + sex
		var actor := ReplicatedActor3D.new()
		actor.apply_render_quality(1, true)
		stage.add_child(actor)
		var appearance := {"skin": 2, "eyes": 1, "hair": AppearanceVariants.pack_hair(1 if sex == "male" else 3, 1 if sex == "male" else 14),
			"hair_detail": 1 if sex == "male" else 2, "facial_hair": 0, "jaw": 62 if sex == "male" else 35,
			"cheekbones": 68 if sex == "male" else 70, "nose": 44 if sex == "male" else 35}
		var error := actor.configure({"actor_id": 9901, "x": 0, "y": 0, "rotation": 0, "kind": 1,
			"name": "", "appearance": appearance, "equipment_visuals": {}}, CoordinateAdapter.new({"walkingHeight": 0.0}),
			models[slug], animation, equipment)
		expect(error.is_empty(), sex + " production actor configures")
		expect(HIGH.cache_metrics().texture_bundles == 0 and HIGH.cache_metrics().mesh_entries == 0,
			"initial Medium loads no High resources")
		actor.set_process(false)
		actor.set_physics_process(false)
		actor.rotation.y = PI
		actor._advance_facing_offset(1.0)
		for node: Node in actor.get_children():
			if node is Node3D and node.name != "NativeModel":
				(node as Node3D).hide()
		freeze(actor, "idle", 0.4)
		var baseline: Dictionary = {}
		for part: String in HIGH.PARTS:
			var node := actor._native_model.find_child(part, true, false) as MeshInstance3D
			baseline[part] = {"mesh": node.mesh, "material": node.material_override, "skin": node.skin}
		for level: int in [1, 2]:
			var started := Time.get_ticks_usec()
			actor.apply_render_quality(level, true)
			var elapsed := Time.get_ticks_usec() - started
			if level == 2:
				expect(HIGH.cache_metrics().texture_bundles == 1, "one shared High texture bundle")
				for part: String in HIGH.PARTS:
					var node := actor._native_model.find_child(part, true, false) as MeshInstance3D
					expect(node.has_meta(HIGH.META), "High artwork applies " + part)
					expect(node.skin == baseline[part].skin, "High retains exact canonical skin binding")
					check_geometry(baseline[part].mesh, node.mesh, part)
					var material := node.material_override as ShaderMaterial
					expect(material.shader == HIGH.SHADER, "High shader active")
					expect(material.get_shader_parameter("skin_color") == (baseline[part].material as ShaderMaterial).get_shader_parameter("skin_color"), "skin selection preserved")
			for angle: String in ["front", "threequarter", "profile"]:
				var skeleton := actor.get_skeleton()
				var focus := skeleton.to_global(skeleton.get_bone_global_pose(skeleton.find_bone("Head")).origin) + Vector3(0, 0.06, 0)
				var offset: Vector3 = {"front": Vector3(0, .055, 1), "threequarter": Vector3(.4, .055, 1), "profile": Vector3(.95, .055, .02)}[angle]
				camera.position = focus + offset
				camera.look_at(focus)
				await capture("%s-%s-%s" % [sex, "high" if level == 2 else "medium", angle])
			results.append({"sex": sex, "level": level, "apply_usec": elapsed, "cache": HIGH.cache_metrics()})
		if sex == "male":
			for color: int in [0, 2]:
				appearance.eyes = color
				actor.apply_appearance_variants(appearance)
				freeze(actor, "idle", .4)
				var skeleton := actor.get_skeleton()
				var focus := skeleton.to_global(skeleton.get_bone_global_pose(skeleton.find_bone("Head")).origin) + Vector3(0, .06, 0)
				camera.position = focus + Vector3(.4, .055, 1)
				camera.look_at(focus)
				await capture("male-high-eyes-" + str(color))
			appearance.eyes = 1
			actor.apply_appearance_variants(appearance)
		var body := actor._native_model.find_child("body", true, false) as MeshInstance3D
		var high_mesh := body.mesh
		var uv: PackedVector2Array = body.mesh.surface_get_arrays(0)[Mesh.ARRAY_TEX_UV2]
		for action: String in ["walk", "run", "idle"]:
			freeze(actor, action, .37)
			expect(body.mesh == high_mesh and body.mesh.surface_get_arrays(0)[Mesh.ARRAY_TEX_UV2] == uv,
				"High painted coordinates stay exact through " + action)
		actor.apply_render_quality(1, true)
		for part: String in HIGH.PARTS:
			var node := actor._native_model.find_child(part, true, false) as MeshInstance3D
			expect(node.mesh == baseline[part].mesh and node.material_override == baseline[part].material,
				"Medium restores exact refined mesh/material " + part)
		expect(HIGH.cache_metrics().texture_bundles == 0 and HIGH.cache_metrics().mesh_entries == 0,
			"last High user downgrade releases images and mesh cache")
		actor.apply_render_quality(0, true)
		expect(HIGH.cache_metrics().texture_bundles == 0, "Low allocates no High texture")
		appearance.facial_hair = 1
		actor.apply_appearance_variants(appearance)
		actor.apply_render_quality(2, true)
		for part: String in HIGH.PARTS:
			var node := actor._native_model.find_child(part, true, false) as MeshInstance3D
			var material := node.material_override as ShaderMaterial
			expect(bool(material.get_shader_parameter("stubble_enabled"))
				and material.get_shader_parameter("stubble_mask") is Texture2D, "High retains surface-bound stubble pigment")
		actor.apply_render_quality(1, true)
		expect(HIGH.cache_metrics().texture_bundles == 0, "stubble High downgrade also releases resources")
		actor.free()
		await process_frame
	FileAccess.open(folder.path_join("checks.json"), FileAccess.WRITE).store_string(JSON.stringify({"checks": checks,
		"failures": failures, "results": results}, "  "))
	print("High portraits: ", checks, " checks, ", failures, " failures")
	quit(1 if failures else 0)

func freeze(actor: ReplicatedActor3D, action: String, seconds: float) -> void:
	actor.play_action(StringName(action), true)
	actor.animation_player.seek(seconds, true)
	actor.animation_player.pause()
	actor.get_skeleton().force_update_all_bone_transforms()

func check_geometry(source: Mesh, result: Mesh, label: String) -> void:
	expect(source.get_surface_count() == result.get_surface_count(), "surface count preserved " + label)
	for surface: int in source.get_surface_count():
		var a := source.surface_get_arrays(surface)
		var b := result.surface_get_arrays(surface)
		var ai: PackedInt32Array = a[Mesh.ARRAY_INDEX]
		var bi: PackedInt32Array = b[Mesh.ARRAY_INDEX]
		expect(ai.size() == bi.size(), "triangle count preserved")
		for corner: int in ai.size():
			expect((a[Mesh.ARRAY_VERTEX][ai[corner]] as Vector3).distance_to(b[Mesh.ARRAY_VERTEX][bi[corner]]) < 0.000001,
				"High adds only anchored texture coordinates; position unchanged")

func capture(name: String) -> void:
	for frame: int in 5:
		await process_frame
	await RenderingServer.frame_post_draw
	expect(root.get_texture().get_image().save_png(folder.path_join(name + ".png")) == OK, "save " + name)
	print("HIGH PORTRAIT RENDER ", name)
