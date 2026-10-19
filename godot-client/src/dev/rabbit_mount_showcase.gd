extends Control
## Offline review using the same rider, mount, action router and props as play.
const Draft := preload("res://src/dev/rabbit_mount_draft.gd")
const PANELS := [
 ["REST / SIDE", "luminous_male", "cruise", "idle", false],
 ["REST / FRONT", "luminous_female", "cruise", "idle", false],
 ["NORMAL / SIDE  |  2x RUN", "luminous_male", "cruise", "run", true],
 ["NORMAL / GAME CAMERA  |  2x RUN", "luminous_female", "cruise", "run", true],
 ["FAST / QUARTER  |  4x RUN", "luminous_male", "burst", "run", true],
 ["FAST / REAR + CAPE  |  4x RUN", "luminous_female", "burst", "run", true]]
var actors: Array[ReplicatedActor3D] = []
var clock := 0.0
var paused := false
var manual := false
var panels: Array = PANELS.duplicate(true)
var all_mounts := false
var pace_review := false
var travelling_views: Array[Dictionary] = []

func _ready() -> void:
	all_mounts = "--all-mounts" in OS.get_cmdline_user_args()
	pace_review = "--tortoise-cadence" in OS.get_cmdline_user_args()
	if pace_review:
		all_mounts = true
		panels = [
			["NORMAL / EARLIER CADENCE", "luminous_female", "cruise", "run", true, "crystalback_tortoise", true],
			["NORMAL / FASTER CADENCE", "luminous_female", "cruise", "run", true, "crystalback_tortoise", false],
			["FAST / EARLIER CADENCE", "luminous_female", "burst", "run", true, "crystalback_tortoise", true],
			["FAST / FASTER CADENCE", "luminous_female", "burst", "run", true, "crystalback_tortoise", false]]
	elif all_mounts:
		panels.clear()
		for gait: String in ["cruise", "burst"]:
			for id: String in preload("res://src/mounts/mount_profiles.gd").PATHS:
				var label := preload("res://src/mounts/mount_profiles.gd").display_name(id)
				panels.append([label + (" / 4x" if gait == "burst" else " / 2x"),
					"luminous_female", gait, "run", true, id])
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
	title.text = "RABBIT LANDS   /   " + ("ALL MOUNTS / NORMAL + FAST" if all_mounts else "GIANT MEADOW RABBIT")
	if pace_review: title.text = "RABBIT LANDS   /   TORTOISE CADENCE / 10 AND 20 METRES PER SECOND"
	title.add_theme_font_size_override("font_size", 23)
	title.add_theme_color_override("font_color", Color("e6d3a7"))
	column.add_child(title)
	var grid := GridContainer.new()
	grid.columns = 2 if pace_review else (4 if all_mounts else 3)
	grid.size_flags_vertical = Control.SIZE_EXPAND_FILL
	column.add_child(grid)
	var models: Dictionary = JSON.parse_string(FileAccess.get_file_as_string("res://data/actors/models.json")).models
	var mapping: Dictionary = JSON.parse_string(FileAccess.get_file_as_string("res://data/animations/luminous.json"))
	var equipment: Dictionary = JSON.parse_string(FileAccess.get_file_as_string("res://data/actors/equipment.json"))
	for index: int in panels.size():
		var panel: Array = panels[index]
		var box := VBoxContainer.new()
		box.size_flags_horizontal = Control.SIZE_EXPAND_FILL
		box.size_flags_vertical = Control.SIZE_EXPAND_FILL
		grid.add_child(box)
		var label := Label.new()
		label.text = panel[0]
		label.add_theme_font_size_override("font_size", 15 if all_mounts else 17)
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
		camera.position = Vector3(4.8, 3.1, -3.8) if index not in [3, 5] else Vector3(3.8, 3.8, 5.7)
		if index in [0, 2]:
			camera.position = Vector3(6.5, 2.6, -.3)
		elif index == 1:
			camera.position = Vector3(0, 2.6, -6.5)
		camera.look_at(Vector3(0, 1.55, .15))
		if pace_review:
			ground.hide()
			var floor_mesh := MeshInstance3D.new()
			var plane := PlaneMesh.new()
			plane.size = Vector2(30, 220)
			floor_mesh.mesh = plane
			floor_mesh.material_override = material
			floor_mesh.position.z = -70
			stage.add_child(floor_mesh)
			# Fixed five-metre road markers make server travel speed visible
			# while the camera follows the actual rider across the review floor.
			for marker: int in range(-25, 7):
				var line := MeshInstance3D.new()
				var stripe := BoxMesh.new()
				stripe.size = Vector3(30,.008,.035)
				line.mesh = stripe
				line.position.z = marker * 5.0
				stage.add_child(line)
			camera.position = Vector3(4.8,3.8,5.7)
			camera.look_at(Vector3(0,1.5,0))
		var actor := ReplicatedActor3D.new()
		stage.add_child(actor)
		var worn := {}
		if all_mounts or index in [0, 3, 5]:
			worn[2] = 1
		var errors := actor.configure({"actor_id": 900 + index, "x": 0, "y": 0,
			"rotation": 0, "kind": 1, "name": "", "appearance": {"hair": 0},
			"equipment_visuals": worn},
			CoordinateAdapter.new({"walkingHeight": 0.0}), models[panel[1]], mapping, equipment)
		if not errors.is_empty():
			push_error(str(errors))
		actor.set_physics_process(false)
		actor.set_process(false)
		actor._presentation_speed = 20.0 if panel[2] == "burst" else 10.0
		if all_mounts:
			actor.set_mount_state({"mode":"mounted", "mount_id":panel[5], "gait":panel[2],
				"step_us":50000 if panel[2] == "burst" else 100000}, models)
		else:
			var mount_errors := Draft.attach(actor, models)
			if not mount_errors.is_empty(): push_error(str(mount_errors))
		Draft.pace(actor, panel[2])
		if pace_review:
			if bool(panel[6]):
				actor._mount_visual.profile.maximumCyclesPerSecond = {"trot":2.0,"gallop":3.0}
			travelling_views.append({"actor":actor,"camera":camera,"camera_rest":camera.position,
				"speed":actor._presentation_speed})
		for child: Node in actor.get_children():
			if child is Node3D and child.name not in ["NativeModel", "RabbitMountDraft", "MountedPony", "CombatPresentation"]:
				(child as Node3D).hide()
		actors.append(actor)
	var instructions := Label.new()
	instructions.text = "SPACE  pause / resume     R  restart     |     Giant Meadow Rabbit / normal + fast riding"
	if pace_review: instructions.text = "LEFT: earlier cadence    RIGHT: doubled cadence    |    Ground markers are five metres apart"
	instructions.add_theme_font_size_override("font_size", 14)
	column.add_child(instructions)
	restart()

func restart() -> void:
	clock = 0.0
	for view: Dictionary in travelling_views:
		(view.actor as Node3D).position = Vector3.ZERO
		(view.camera as Node3D).position = view.camera_rest
	for index: int in actors.size():
		actors[index]._mount_visual.elapsed = 0.0
		actors[index].play_action(&"run" if panels[index][4] else &"idle")
		actors[index].play_action(StringName(panels[index][3]), true)

func _process(delta: float) -> void:
	if not paused and not manual:
		advance_sequence(delta)

func advance_sequence(delta: float) -> void:
	clock += delta
	if clock > 4.5:
		restart()
	for view: Dictionary in travelling_views:
		var offset := Vector3.FORWARD * float(view.speed) * clock
		(view.actor as Node3D).position = offset
		(view.camera as Node3D).position = (view.camera_rest as Vector3) + offset

func _unhandled_key_input(event: InputEvent) -> void:
	if event is InputEventKey and event.pressed and not event.echo:
		if event.keycode == KEY_SPACE:
			paused = not paused
			for actor: ReplicatedActor3D in actors:
				actor._mount_visual.set_process(not paused)
		elif event.keycode == KEY_R:
			restart()
