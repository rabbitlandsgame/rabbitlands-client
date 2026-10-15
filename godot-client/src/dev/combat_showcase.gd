extends Control
## F6: a looping, offline review of the actual actor and prop implementation.
## Space pauses/resumes; R restarts the six sequences together.
const PANELS := [
	["CHANNELING", "luminous_female", "cast_channel_enter", "Gather → sustain", {}],
	["AGGRESSIVE CAST", "luminous_male", "cast_aggressive", "Anticipation → two-hand release", {}],
	["DEFENSIVE CAST", "glasswarden_female", "cast_defensive", "Brace → ward seal", {}],
	["HEALING", "votary_female", "heal", "Gather → rising restoration", {}],
	["RANGING", "luminous_male", "ranged_draw", "Nock → draw → hold → release", {0: 64}],
	["MELEE", "greyhaven_male", "attack_primary", "Alternating cuts → recovery", {0: 114}]]
var actors: Array[ReplicatedActor3D] = []
var stages: Array[Node3D] = []
var _clock := 0.0
var _released := false
var _paused := false

func _ready() -> void:
	var background := ColorRect.new()
	background.color = Color("111b23")
	background.set_anchors_and_offsets_preset(Control.PRESET_FULL_RECT)
	add_child(background)
	var margin := MarginContainer.new()
	margin.set_anchors_and_offsets_preset(Control.PRESET_FULL_RECT)
	for side: String in ["left", "right", "top", "bottom"]:
		margin.add_theme_constant_override("margin_"+side, 22)
	add_child(margin)
	var column := VBoxContainer.new()
	column.add_theme_constant_override("separation", 14)
	margin.add_child(column)
	var title := Label.new()
	title.text = "RABBIT LANDS   /   COMBAT & SPELLCRAFT"
	title.add_theme_font_size_override("font_size", 25)
	title.add_theme_color_override("font_color", Color("e6d3a7"))
	column.add_child(title)
	var grid := GridContainer.new()
	grid.columns = 3
	grid.size_flags_vertical = Control.SIZE_EXPAND_FILL
	grid.add_theme_constant_override("h_separation", 12)
	grid.add_theme_constant_override("v_separation", 12)
	column.add_child(grid)
	var models: Dictionary = JSON.parse_string(FileAccess.get_file_as_string("res://data/actors/models.json"))["models"]
	var animations: Dictionary = JSON.parse_string(FileAccess.get_file_as_string("res://data/animations/luminous.json"))
	var equipment: Dictionary = JSON.parse_string(FileAccess.get_file_as_string("res://data/actors/equipment.json"))
	for i: int in PANELS.size():
		var box := VBoxContainer.new()
		box.size_flags_horizontal = Control.SIZE_EXPAND_FILL
		box.size_flags_vertical = Control.SIZE_EXPAND_FILL
		grid.add_child(box)
		var heading := Label.new()
		heading.text = "%02d   %s" % [i+1, PANELS[i][0]]
		heading.add_theme_font_size_override("font_size", 17)
		box.add_child(heading)
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
		stages.append(stage)
		var environment := WorldEnvironment.new()
		environment.environment = Environment.new()
		environment.environment.background_mode = Environment.BG_COLOR
		environment.environment.background_color = Color("202e37")
		environment.environment.ambient_light_source = Environment.AMBIENT_SOURCE_COLOR
		environment.environment.ambient_light_color = Color(0.78, 0.86, 1.0)
		environment.environment.ambient_light_energy = 0.6
		stage.add_child(environment)
		var key := DirectionalLight3D.new()
		key.rotation_degrees = Vector3(-35, -35, 0)
		key.light_energy = 1.15
		stage.add_child(key)
		var floor_node := MeshInstance3D.new()
		var floor_mesh := CylinderMesh.new()
		floor_mesh.top_radius = 1.05
		floor_mesh.bottom_radius = 1.05
		floor_mesh.height = 0.06
		floor_mesh.radial_segments = 64
		floor_node.mesh = floor_mesh
		floor_node.position.y = -0.035
		var floor_material := StandardMaterial3D.new()
		floor_material.albedo_color = Color("35444c")
		floor_node.material_override = floor_material
		stage.add_child(floor_node)
		var camera := Camera3D.new()
		camera.projection = Camera3D.PROJECTION_ORTHOGONAL
		camera.size = 2.7
		camera.cull_mask = 1
		stage.add_child(camera)
		camera.position = Vector3(2.7, 2.2, 5.0)
		camera.look_at(Vector3(0, 0.93, 0))
		var actor := ReplicatedActor3D.new()
		stage.add_child(actor)
		var errors := actor.configure({"actor_id": 900+i, "x": 0, "y": 0, "rotation": 0,
			"appearance": {"hair": 1}, "equipment_visuals": PANELS[i][4]},
			CoordinateAdapter.new({"walkingHeight": 0.0}), models[PANELS[i][1]], animations, equipment)
		if not errors.is_empty():
			push_error(str(errors))
		actor.position = Vector3.ZERO
		actor.rotation.y = PI
		actor.set_physics_process(false)
		actors.append(actor)
		var caption := Label.new()
		caption.text = PANELS[i][3]
		caption.add_theme_font_size_override("font_size", 14)
		caption.add_theme_color_override("font_color", Color("a6b7bc"))
		box.add_child(caption)
	var instructions := Label.new()
	instructions.text = "SPACE  pause / resume     R  restart     •     Native player rigs and gameplay effects"
	instructions.add_theme_font_size_override("font_size", 14)
	column.add_child(instructions)
	restart()

func restart() -> void:
	_clock = 0.0
	_released = false
	for i: int in actors.size():
		actors[i].play_action(StringName(PANELS[i][2]), true)

func _process(delta: float) -> void:
	if _paused or actors.size() != PANELS.size():
		return
	_clock += delta
	for actor: ReplicatedActor3D in actors:
		actor._advance_facing_offset(delta)
	if _clock > 1.25 and not _released:
		_released = true
		var archer := actors[4]
		var missile := MissileFlight3D.new()
		stages[4].add_child(missile)
		missile.configure(archer.position, Vector3(0, 0, 4), archer.ranged_release_origin())
		archer.play_action(&"ranged_attack", true)
		actors[5].play_action(&"attack_secondary", true)
	if _clock > 3.0:
		restart()

func _unhandled_key_input(event: InputEvent) -> void:
	if event is InputEventKey and event.pressed and not event.echo:
		if event.keycode == KEY_SPACE:
			_paused = not _paused
			for actor: ReplicatedActor3D in actors:
				actor.animation_player.speed_scale = 0.0 if _paused else 1.0
		elif event.keycode == KEY_R:
			restart()
