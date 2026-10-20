extends SceneTree
## Static gameplay-scale views of production markers, placement and attack clips.

const OUT := "res://test-artifacts/combat-readability/implemented.png"
var models: Dictionary
var animations: Dictionary
var equipment: Dictionary
var adapter := CoordinateAdapter.new({"walkingHeight": 0.0})

func _init() -> void:
	call_deferred("run")

func run() -> void:
	root.size = Vector2i(1800, 780)
	root.content_scale_size = root.size
	root.content_scale_factor = 1.0
	models = JSON.parse_string(FileAccess.get_file_as_string("res://data/actors/models.json")).models
	animations = JSON.parse_string(FileAccess.get_file_as_string("res://data/animations/luminous.json"))
	equipment = JSON.parse_string(FileAccess.get_file_as_string("res://data/actors/equipment.json"))
	var ui := Control.new()
	root.add_child(ui)
	var bg := ColorRect.new()
	bg.size = Vector2(root.size)
	bg.color = Color("121c24")
	ui.add_child(bg)
	label(ui, "RABBIT LANDS  /  IMPLEMENTED COMBAT READABILITY", Vector2(24, 18), 28)
	label(ui, "Current game models and production code. Red marks the active opponent; yellow marks a different tentative target.", Vector2(24, 62), 18)
	for mode: int in 3:
		label(ui, ["Crowded combat: resting wolves", "Crowded combat: bite / sword strike", "Unarmed punches / equipped sword cuts"][mode], Vector2(20 + mode * 600, 108), 20)
		var container := SubViewportContainer.new()
		container.position = Vector2(10 + mode * 600, 150)
		container.size = Vector2(580, 550)
		ui.add_child(container)
		var view := SubViewport.new()
		view.size = Vector2i(580, 550)
		view.own_world_3d = true
		view.render_target_update_mode = SubViewport.UPDATE_ALWAYS
		view.msaa_3d = Viewport.MSAA_4X
		container.add_child(view)
		var stage := Node3D.new()
		view.add_child(stage)
		light_stage(stage)
		var camera := Camera3D.new()
		camera.fov = 50.0
		camera.cull_mask = 3
		stage.add_child(camera)
		camera.position = Vector3(2.8, 5.7, 4.1) if mode < 2 else Vector3(0, 2.1, 5.2)
		camera.look_at(Vector3(0, 0.5 if mode < 2 else 0.9, 0))
		if mode < 2:
			var player := make_actor(stage, "greyhaven_male", Vector3.ZERO, -PI * 0.5, false, {0: 114})
			pose(player, &"combat_idle" if mode == 0 else &"attack_primary", 0.5 if mode == 0 else 0.3)
			var points := [Vector3(0, 0, -1), Vector3(1, 0, 0), Vector3(0, 0, 1), Vector3(-1, 0, 0)]
			for i: int in points.size():
				var point: Vector3 = points[i]
				var wolf := make_actor(stage, "dire_wolf", point, atan2(point.x, point.z), true, {})
				pose(wolf, &"attack_primary" if mode == 1 and i == 1 else &"combat_idle", 0.625 if mode == 1 and i == 1 else 0.5)
				if i == 1:
					wolf.set_health_visible(true)
					wolf.set_combat_target(true)
				if i == 3:
					wolf.set_selected(true)
		else:
			var unarmed := make_actor(stage, "greyhaven_male", Vector3(-0.85, 0, 0), PI, false, {})
			var armed := make_actor(stage, "greyhaven_male", Vector3(0.85, 0, 0), PI, false, {0: 114})
			pose(unarmed, &"attack_primary", 0.22)
			pose(armed, &"attack_primary", 0.3)
			unarmed.set_nameplate_visible(false)
			armed.set_nameplate_visible(false)
		label(ui, ["Red ring + pointer: active target. Yellow circle: tentative target.", "Species setback gives the player room through the bite.", "Reference jabs when unarmed; sword mapping returns on equip."][mode], Vector2(18 + mode * 600, 728), 16)
	for i: int in 12:
		await process_frame
	await RenderingServer.frame_post_draw
	DirAccess.make_dir_recursive_absolute(ProjectSettings.globalize_path(OUT.get_base_dir()))
	var result := root.get_texture().get_image().save_png(ProjectSettings.globalize_path(OUT))
	print("COMBAT_READABILITY_RENDER ", "PASS" if result == OK else "FAIL", " ", ProjectSettings.globalize_path(OUT))
	quit(result)

func label(parent: Node, text: String, at: Vector2, size: int) -> void:
	var node := Label.new()
	node.text = text
	node.position = at
	node.add_theme_font_size_override("font_size", size)
	node.add_theme_color_override("font_color", Color("e7dfcb"))
	parent.add_child(node)

func light_stage(stage: Node3D) -> void:
	var world := WorldEnvironment.new()
	world.environment = Environment.new()
	world.environment.background_mode = Environment.BG_COLOR
	world.environment.background_color = Color("25343b")
	world.environment.ambient_light_source = Environment.AMBIENT_SOURCE_COLOR
	world.environment.ambient_light_color = Color(0.85, 0.9, 1.0)
	world.environment.ambient_light_energy = 0.65
	stage.add_child(world)
	var light := DirectionalLight3D.new()
	light.rotation_degrees = Vector3(-45, -30, 0)
	light.light_energy = 1.1
	stage.add_child(light)
	var floor_node := MeshInstance3D.new()
	var plane := PlaneMesh.new()
	plane.size = Vector2(40, 40)
	floor_node.mesh = plane
	floor_node.position.y = -0.01
	var material := StandardMaterial3D.new()
	material.albedo_color = Color("506044")
	floor_node.material_override = material
	stage.add_child(floor_node)

func make_actor(stage: Node3D, model: String, at: Vector3, yaw: float, creature: bool, loadout: Dictionary) -> ReplicatedActor3D:
	var actor := ReplicatedActor3D.new()
	stage.add_child(actor)
	var config: Dictionary = models[model]
	var actions: Dictionary = (JSON.parse_string(FileAccess.get_file_as_string(config.animationMap)) if creature else animations)
	var errors := actor.configure({"actor_id": 100 + stage.get_child_count(), "actor_type": 218 if creature else 0,
		"kind": ReplicatedActor3D.CREATURE_ACTOR_KIND if creature else 0, "x": 0, "y": 0, "rotation": 0, "appearance": {},
		"name": "Dire Wolf" if creature else "Player", "health": 220, "max_health": 305,
		"in_combat": true, "equipment_visuals": loadout}, adapter, config, actions, equipment)
	assert(errors.is_empty(), str(errors))
	actor.position = at
	actor.rotation.y = yaw
	actor.set_physics_process(false)
	actor.set_process(false)
	actor.get_node("MapDot").hide()
	return actor

func pose(actor: ReplicatedActor3D, action: StringName, time: float) -> void:
	actor.play_action(action, true)
	# A static witness of the requested pose, separate from transition tests.
	actor.animation_player.play(actor.resolver.clip_for_action(action), 0.0)
	actor.animation_player.seek(time, true)
	actor.animation_player.pause()
	if actor.combat_presentation != null:
		actor.combat_presentation.update_pose()
