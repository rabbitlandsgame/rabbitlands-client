extends SceneTree
## Production attachment path; three new mounts, three paces, real wardrobes.
const IDS := ["cave_salamander","lantern_stag","cheetah"]
var actors: Array[ReplicatedActor3D] = []
var failures: Array[String] = []

func _init() -> void: call_deferred("run")

func run() -> void:
	root.size = Vector2i(1500,1140)
	var models: Dictionary = JSON.parse_string(FileAccess.get_file_as_string("res://data/actors/models.json")).models
	var mapping: Dictionary = JSON.parse_string(FileAccess.get_file_as_string("res://data/animations/luminous.json"))
	var equipment: Dictionary = JSON.parse_string(FileAccess.get_file_as_string("res://data/actors/equipment.json"))
	var page := VBoxContainer.new()
	page.set_anchors_and_offsets_preset(Control.PRESET_FULL_RECT)
	root.add_child(page)
	var title := Label.new()
	title.text = "RABBIT LANDS  /  CAVE SALAMANDER, LANTERN STAG & CHEETAH"
	title.add_theme_font_size_override("font_size",24)
	page.add_child(title)
	var grid := GridContainer.new()
	var gallery := "--coats" in OS.get_cmdline_user_args()
	grid.columns = 5 if gallery else 3
	grid.size_flags_vertical = Control.SIZE_EXPAND_FILL
	page.add_child(grid)
	for id: String in IDS:
		for column: int in (5 if gallery else 3):
			var pace := 0 if gallery else column
			var box := VBoxContainer.new()
			box.size_flags_horizontal = Control.SIZE_EXPAND_FILL
			box.size_flags_vertical = Control.SIZE_EXPAND_FILL
			grid.add_child(box)
			var label := Label.new()
			label.text = "%s  /  %s" % [preload("res://src/mounts/mount_profiles.gd").display_name(id),preload("res://src/mounts/mount_coats.gd").LABELS[preload("res://src/mounts/mount_coats.gd").IDS[column]] if gallery else ["Idle","Normal · 1.5x run","Fast · 2x run"][pace]]
			label.add_theme_font_size_override("font_size",13 if gallery else 16)
			box.add_child(label)
			var container := SubViewportContainer.new()
			container.stretch = true
			container.size_flags_horizontal = Control.SIZE_EXPAND_FILL
			container.size_flags_vertical = Control.SIZE_EXPAND_FILL
			box.add_child(container)
			var viewport := SubViewport.new()
			viewport.own_world_3d = true
			viewport.msaa_3d = Viewport.MSAA_4X
			container.add_child(viewport)
			var stage := Node3D.new()
			viewport.add_child(stage)
			var env := WorldEnvironment.new()
			env.environment = Environment.new()
			env.environment.background_mode = Environment.BG_COLOR
			env.environment.background_color = Color("25343a")
			env.environment.ambient_light_source = Environment.AMBIENT_SOURCE_COLOR
			env.environment.ambient_light_color = Color("d0dcf0")
			env.environment.ambient_light_energy = .7
			stage.add_child(env)
			var light := DirectionalLight3D.new()
			light.rotation_degrees = Vector3(-40,-35,0)
			light.light_energy = 1.2
			stage.add_child(light)
			var ground := MeshInstance3D.new()
			var plane := PlaneMesh.new()
			plane.size = Vector2(20,20)
			ground.mesh = plane
			var mat := StandardMaterial3D.new()
			mat.albedo_color = Color("46534c")
			ground.material_override = mat
			stage.add_child(ground)
			var camera := Camera3D.new()
			camera.projection = Camera3D.PROJECTION_ORTHOGONAL
			camera.size = 4.8 if id == "cave_salamander" else 4.2
			stage.add_child(camera)
			camera.position = [Vector3(5,2.6,-5),Vector3(7,2.7,0),Vector3(4,4,6)][pace]
			camera.look_at(Vector3(0,1.4,.1))
			var actor := ReplicatedActor3D.new()
			stage.add_child(actor)
			var errors := actor.configure({"actor_id":900+actors.size(),"x":0,"y":0,"rotation":0,"kind":1,"name":"","appearance":{"hair":0},"equipment_visuals":{2:1}},CoordinateAdapter.new({"walkingHeight":0.0}),models["luminous_female" if pace == 2 else "luminous_male"],mapping,equipment)
			failures.append_array(errors)
			actor.set_physics_process(false)
			actor.set_process(false)
			actor._presentation_speed = 10.0 if pace == 2 else 7.5
			var coat_id := "original"
			if gallery: coat_id = preload("res://src/mounts/mount_coats.gd").IDS[column]
			for argument: String in OS.get_cmdline_user_args():
				if argument.begins_with("--coat="): coat_id = argument.trim_prefix("--coat=")
			actor.set_mount_state({"mode":"mounted","mount_id":id,"gait":"burst" if pace == 2 else "cruise","coat_id":coat_id},models)
			if actor._mount_visual == null:
				failures.append("Missing production mount: "+id)
				continue
			actor._mount_visual.set_process(false)
			actor.play_action(&"idle" if pace == 0 else &"run",true)
			for child: Node in actor.get_children():
				if child is Node3D and child.name not in ["NativeModel","MountedPony","CombatPresentation"]: (child as Node3D).hide()
			actors.append(actor)
	var artifacts := OS.get_environment("ELORIA_ARTIFACT_DIR")
	if artifacts.is_empty(): artifacts = ProjectSettings.globalize_path("res://test-artifacts/wild-mounts")
	DirAccess.make_dir_recursive_absolute(artifacts.path_join("frames"))
	for frame: int in 4: await process_frame
	var frames := 120 if "--video" in OS.get_cmdline_user_args() else 45
	var contact := 0.0
	for frame: int in frames:
		for actor: ReplicatedActor3D in actors:
			actor._mount_visual._process(1.0/30.0)
			for error: float in actor._mount_visual.pose.last_errors.values(): contact = maxf(contact,error)
		await process_frame
		await RenderingServer.frame_post_draw
		if frames > 45: root.get_texture().get_image().save_png(artifacts.path_join("frames/%04d.png" % frame))
	root.get_texture().get_image().save_png(artifacts.path_join("wild-mounts.png"))
	FileAccess.open(artifacts.path_join("checks.json"),FileAccess.WRITE).store_string(JSON.stringify({"actors":actors.size(),"frames":frames,"maxContactError":contact,"failures":failures},"  "))
	print("WILD_MOUNTS_CAPTURE ",artifacts," contact=",contact," failures=",failures)
	for actor: ReplicatedActor3D in actors: actor.set_mount_state({},models)
	page.queue_free()
	await process_frame
	NativeAnimationImporter.clear()
	GlbSceneCache.clear()
	quit(1 if contact >= .06 or not failures.is_empty() else 0)
