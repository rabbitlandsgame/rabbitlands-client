extends Control
## Offline review using the same rider, mount, action router and props as play.
const PANELS := [
 ["STANDING / FRONT", "luminous_male", "cruise", "idle", false],
 ["WALK", "luminous_female", "walk", "walk", true],
 ["SCUTTLE", "luminous_male", "cruise", "run", true],
 ["RUSH / GAME CAMERA + CAPE", "luminous_female", "burst", "run", true],
 ["MOUNTED BOW / SCUTTLE", "luminous_female", "cruise", "ranged_draw", true],
 ["MOUNTED SPELL / RUSH", "luminous_male", "burst", "cast_aggressive", true]]
var actors: Array[ReplicatedActor3D] = []
var clock := 0.0
var released := false
var paused := false
var manual := false

func _ready() -> void:
	var background := ColorRect.new()
	background.color = Color("111b23")
	background.set_anchors_and_offsets_preset(Control.PRESET_FULL_RECT)
	add_child(background)
	var margin := MarginContainer.new()
	margin.set_anchors_and_offsets_preset(Control.PRESET_FULL_RECT)
	for side: String in ["left", "right", "top", "bottom"]:
		margin.add_theme_constant_override("margin_" + side, 18)
	add_child(margin)
	var column := VBoxContainer.new()
	column.add_theme_constant_override("separation", 10)
	margin.add_child(column)
	var title := Label.new()
	title.text = "RABBIT LANDS   /   CRYSTALBACK TORTOISE"
	title.add_theme_font_size_override("font_size", 23)
	title.add_theme_color_override("font_color", Color("e6d3a7"))
	column.add_child(title)
	var grid := GridContainer.new()
	grid.columns = 3
	grid.size_flags_vertical = Control.SIZE_EXPAND_FILL
	column.add_child(grid)
	var models: Dictionary = JSON.parse_string(FileAccess.get_file_as_string("res://data/actors/models.json")).models
	var mapping: Dictionary = JSON.parse_string(FileAccess.get_file_as_string("res://data/animations/luminous.json"))
	var equipment: Dictionary = JSON.parse_string(FileAccess.get_file_as_string("res://data/actors/equipment.json"))
	for index: int in PANELS.size():
		var panel: Array = PANELS[index]
		var box := VBoxContainer.new()
		box.size_flags_horizontal = Control.SIZE_EXPAND_FILL
		box.size_flags_vertical = Control.SIZE_EXPAND_FILL
		grid.add_child(box)
		var label := Label.new()
		label.text = panel[0]
		label.add_theme_font_size_override("font_size", 17)
		box.add_child(label)
		var container := SubViewportContainer.new()
		container.stretch = true
		container.size_flags_horizontal = Control.SIZE_EXPAND_FILL
		container.size_flags_vertical = Control.SIZE_EXPAND_FILL
		box.add_child(container)
		var viewport := SubViewport.new()
		viewport.own_world_3d = true
		viewport.render_target_update_mode = SubViewport.UPDATE_ALWAYS
		viewport.msaa_3d = Viewport.MSAA_4X
		container.add_child(viewport)
		var stage := Node3D.new()
		viewport.add_child(stage)
		var environment := WorldEnvironment.new()
		environment.environment = Environment.new()
		environment.environment.background_mode = Environment.BG_COLOR
		environment.environment.background_color = Color("29353b")
		environment.environment.ambient_light_source = Environment.AMBIENT_SOURCE_COLOR
		environment.environment.ambient_light_color = Color("d0dcf0")
		environment.environment.ambient_light_energy = .65
		stage.add_child(environment)
		var light := DirectionalLight3D.new()
		light.rotation_degrees = Vector3(-45, -35, 0)
		light.light_energy = 1.2
		stage.add_child(light)
		var ground := MeshInstance3D.new()
		var mesh := CylinderMesh.new()
		mesh.top_radius = 2.5
		mesh.bottom_radius = 2.5
		mesh.height = .06
		ground.mesh = mesh
		ground.position.y = -.03
		var material := StandardMaterial3D.new()
		material.albedo_color = Color("46504a")
		ground.material_override = material
		stage.add_child(ground)
		var camera := Camera3D.new()
		camera.fov = 43
		camera.projection = Camera3D.PROJECTION_ORTHOGONAL
		camera.size = 4.0
		camera.cull_mask = 3
		stage.add_child(camera)
		camera.position = Vector3(4.8, 3.1, -3.8) if index != 3 else Vector3(3.8, 3.8, 5.7)
		if index == 0:
			camera.position = Vector3(0, 2.6, -6.5)
		elif index == 2:
			camera.position = Vector3(6.5, 2.6, -.3)
		camera.look_at(Vector3(0, 1.55, .15))
		var actor := ReplicatedActor3D.new()
		stage.add_child(actor)
		var worn := {0: 164} if index == 4 else {}
		if index in [1, 2, 3, 5]:
			worn[2] = 1
		var errors := actor.configure({"actor_id": 900 + index, "x": 0, "y": 0,
			"rotation": 0, "kind": 1, "name": "", "appearance": {"hair": 0},
			"equipment_visuals": worn},
			CoordinateAdapter.new({"walkingHeight": 0.0}), models[panel[1]], mapping, equipment)
		if not errors.is_empty():
			push_error(str(errors))
		actor.set_physics_process(false)
		actor.set_process(false)
		actor._presentation_speed = 1.5 if panel[2] == "cruise" else (2.25 if panel[2] == "burst" else .5)
		actor.set_mount_state({"mode": "mounted", "mount_id": "crystalback_tortoise", "gait": panel[2], "step_us": 200000}, models)
		for child: Node in actor.get_children():
			if child is Node3D and child.name not in ["NativeModel", "MountedPony", "CombatPresentation"]:
				(child as Node3D).hide()
		actors.append(actor)
	var instructions := Label.new()
	instructions.text = "SPACE  pause / resume     R  restart     |     Crystalback Tortoise riding prototype"
	instructions.add_theme_font_size_override("font_size", 14)
	column.add_child(instructions)
	restart()

func restart() -> void:
	clock = 0.0
	released = false
	for index: int in actors.size():
		if index == 5:
			actors[index].set_spell_variant(2)
		actors[index].play_action(&"run" if PANELS[index][4] else &"idle")
		actors[index].play_action(StringName(PANELS[index][3]), true)

func _process(delta: float) -> void:
	if not paused and not manual:
		advance_sequence(delta)

func advance_sequence(delta: float) -> void:
	clock += delta
	if clock >= 1.0 and not released:
		released = true
		actors[4].play_action(&"ranged_attack", true)
	if clock > 4.5:
		restart()

func _unhandled_key_input(event: InputEvent) -> void:
	if event is InputEventKey and event.pressed and not event.echo:
		if event.keycode == KEY_SPACE:
			paused = not paused
			for actor: ReplicatedActor3D in actors:
				actor._mount_visual.set_process(not paused)
		elif event.keycode == KEY_R:
			restart()
