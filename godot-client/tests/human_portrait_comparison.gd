extends SceneTree
## Actual High graphics portraits for comparison with the Human studies.
## RL_HUMAN_PORTRAIT_OUTPUT selects ignored evidence. Optional
## RL_HUMAN_PORTRAIT_LOOKS points to a local JSON dictionary of preset overrides.
const PRESETS := preload("res://src/actors/human_portrait_presets.gd")
var stage: Node3D
var camera: Camera3D
var output: String
var records: Array = []
var failures := 0

func _init() -> void:
	run.call_deferred()

func run() -> void:
	output = OS.get_environment("RL_HUMAN_PORTRAIT_OUTPUT")
	if output.is_empty(): output = ProjectSettings.globalize_path("res://test-artifacts/human-portraits")
	DirAccess.make_dir_recursive_absolute(output)
	root.size = Vector2i(800, 900)
	stage = Node3D.new()
	root.add_child(stage)
	var world := WorldEnvironment.new()
	world.environment = Environment.new()
	world.environment.background_mode = Environment.BG_COLOR
	world.environment.background_color = Color("bdb7ae")
	world.environment.ambient_light_source = Environment.AMBIENT_SOURCE_COLOR
	world.environment.ambient_light_color = Color("e2d8c8")
	var studio := OS.get_environment("RL_HUMAN_PORTRAIT_LIGHTING") != "flat"
	root.msaa_3d = Viewport.MSAA_2X if studio else Viewport.MSAA_DISABLED
	world.environment.ambient_light_energy = 0.28 if studio else 0.40
	if studio and RenderingServer.get_current_rendering_method() == "forward_plus":
		world.environment.ssao_enabled = true
		world.environment.ssao_radius = LookProfile.SSAO_RADIUS
		world.environment.ssao_intensity = LookProfile.SSAO_INTENSITY
		world.environment.ssao_power = LookProfile.SSAO_POWER
		world.environment.ssao_detail = LookProfile.SSAO_DETAIL
		world.environment.ssao_light_affect = LookProfile.SSAO_LIGHT_AFFECT
		world.environment.ssil_enabled = true
		world.environment.ssil_radius = LookProfile.SSIL_RADIUS
		world.environment.ssil_intensity = LookProfile.SSIL_INTENSITY
	stage.add_child(world)
	var key := DirectionalLight3D.new()
	key.rotation_degrees = Vector3(-28, -32, 0)
	key.light_color = Color("fff0da")
	key.light_energy = 1.0 if studio else 0.90
	key.shadow_enabled = studio
	key.directional_shadow_max_distance = 5.0
	key.light_angular_distance = 0.75
	stage.add_child(key)
	var fill := DirectionalLight3D.new()
	fill.rotation_degrees = Vector3(-10, 125, 0)
	fill.light_color = Color("d7dfeb")
	fill.light_energy = 0.16 if studio else 0.28
	stage.add_child(fill)
	camera = Camera3D.new()
	camera.projection = Camera3D.PROJECTION_ORTHOGONAL
	camera.current = true
	camera.cull_mask = 3
	stage.add_child(camera)
	var models: Dictionary = JSON.parse_string(FileAccess.get_file_as_string("res://data/actors/models.json")).models
	var equipment: Dictionary = JSON.parse_string(FileAccess.get_file_as_string("res://data/actors/equipment.json"))
	var animations: Dictionary = JSON.parse_string(FileAccess.get_file_as_string("res://data/animations/luminous.json"))
	var looks: Dictionary = {}
	var override_path := OS.get_environment("RL_HUMAN_PORTRAIT_LOOKS")
	if not override_path.is_empty():
		var parsed: Variant = JSON.parse_string(FileAccess.get_file_as_string(override_path))
		if parsed is Dictionary: looks = parsed
	var selected := OS.get_environment("RL_HUMAN_PORTRAIT_CHARACTERS").split(",", false)
	for name: String in ["Rowan", "Mira", "Tavi"]:
		if not selected.is_empty() and not selected.has(name): continue
		var actor := ReplicatedActor3D.new()
		actor.apply_render_quality(2, true)
		stage.add_child(actor)
		var look := PRESETS.appearance(name).merged({"shirt": 5, "pants": 2, "boots": 2})
		look.merge(looks.get(name, {}), true)
		var model: Dictionary = models["luminous_female" if name == "Mira" else "luminous_male"].duplicate(true)
		var loadout := {5: 225, 2: 100} if name == "Mira" else {5: 209, 2: 105}
		var errors := actor.configure({"actor_id": 9931, "x": 0, "y": 0, "rotation": 0,
			"kind": 1, "name": "", "appearance": look, "equipment_visuals": loadout},
			CoordinateAdapter.new({"walkingHeight": 0.0}), model, animations, equipment)
		if not errors.is_empty():
			failures += 1
			push_error(str(errors))
		actor.set_process(false)
		actor.set_physics_process(false)
		actor.rotation.y = PI
		actor._advance_facing_offset(1.0)
		for node: Node in actor.get_children():
			if node is Node3D and node.name != "NativeModel": (node as Node3D).hide()
		actor.play_action(&"idle", true)
		actor.animation_player.seek(0.40, true)
		actor.animation_player.pause()
		var rig := actor.get_skeleton()
		rig.force_update_all_bone_transforms()
		var head_origin := rig.to_global(rig.get_bone_global_pose(rig.find_bone("Head")).origin)
		# Include the full crown/updo, keeping one physical portrait scale for
		# all three bodies rather than cropping the most voluminous hairstyle.
		var focus := head_origin + Vector3(0, 0.08, 0)
		for view: String in ["front", "study"]:
			camera.size = 0.50
			var study_offset: Vector3 = {"Rowan": Vector3(-0.75, 0.18, 1),
				"Mira": Vector3(-0.50, 0.18, 1), "Tavi": Vector3(-0.70, 0.18, 1)}[name]
			camera.position = focus + (Vector3(0, 0, 1) if view == "front" else study_offset)
			camera.look_at(focus)
			var filename := name.to_lower() + "-high-" + view + ".png"
			for _frame: int in 6: await process_frame
			await RenderingServer.frame_post_draw
			var image := root.get_texture().get_image()
			if image.save_png(output.path_join(filename)) != OK: failures += 1
			records.append({"character": name, "view": view, "file": filename, "appearance": look,
				"equipment": loadout, "camera_position": str(camera.position), "focus": str(focus),
				"orthographic_size": camera.size, "dimensions": [image.get_width(), image.get_height()],
				"source_sha256": FileAccess.get_sha256(model.scene), "errors": errors,
				"portrait_cache": HighPortraitAppearance.cache_metrics()})
			print("HUMAN PORTRAIT ", filename)
		actor.free()
		await process_frame
	FileAccess.open(output.path_join("manifest.json"), FileAccess.WRITE).store_string(JSON.stringify({
		"graphics": "High", "renderer": RenderingServer.get_current_rendering_method(),
		"lighting": "soft studio key with High scene occlusion" if studio else "flat diagnostic key and fill",
		"portrait_msaa": 2 if studio else 0,
		"reference_pose": "front and shallow three-quarter; unchanged production idle at 0.40 seconds",
		"failures": failures, "portraits": records}, "  "))
	NativeAnimationImporter.clear()
	GlbSceneCache.clear()
	quit(1 if failures else 0)
