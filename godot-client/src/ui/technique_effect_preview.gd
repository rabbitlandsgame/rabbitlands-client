extends SubViewportContainer
## Isolated demo with production rigs, equipment, animation and combat effects.
## It never creates packets or gameplay actors.
const Presentation = preload("res://src/world/technique_presentation.gd")
const Effect = preload("res://src/world/technique_effect_3d.gd")
const LOOP_SECONDS := 3.1
var row: Dictionary = {}
var clock := 0.0
var viewport: SubViewport
var stage: Node3D
var effects: Node3D
var source: ReplicatedActor3D
var target: ReplicatedActor3D
var _released := false
var _flurry_hits := 0
var _countered := false
var _camera: Camera3D
var _equipment: Dictionary

func _ready() -> void:
	custom_minimum_size = Vector2(120, 72)
	mouse_filter = Control.MOUSE_FILTER_IGNORE
	stretch = true
	visibility_changed.connect(_update_processing)
	resized.connect(_fit_camera)
	set_process(false)
	tooltip_text = "Technique preview · actual combat animation and effects"

func set_technique(value: Dictionary) -> void:
	var changed: bool = row.get("key") != value.get("key")
	row = value.duplicate(true)
	if changed:
		_update_processing()

func _update_processing() -> void:
	var active := is_visible_in_tree() and Presentation.PROFILES.has(str(row.get("key", "")))
	set_process(active)
	if active and stage == null: _build_stage()
	if viewport == null: return
	viewport.render_target_update_mode = SubViewport.UPDATE_ALWAYS if active else SubViewport.UPDATE_DISABLED
	stage.process_mode = Node.PROCESS_MODE_INHERIT if active else Node.PROCESS_MODE_DISABLED
	if active: replay()

func _build_stage() -> void:
	viewport = SubViewport.new()
	viewport.name = "TechniquePreviewWorld"
	viewport.own_world_3d = true
	viewport.handle_input_locally = false
	viewport.gui_disable_input = true
	viewport.msaa_3d = Viewport.MSAA_2X
	add_child(viewport)
	stage = Node3D.new()
	viewport.add_child(stage)
	var environment := WorldEnvironment.new()
	environment.environment = Environment.new()
	environment.environment.background_mode = Environment.BG_COLOR
	environment.environment.background_color = Color("14202a")
	environment.environment.ambient_light_source = Environment.AMBIENT_SOURCE_COLOR
	environment.environment.ambient_light_color = Color("ced9df")
	environment.environment.ambient_light_energy = 0.75
	stage.add_child(environment)
	var light := DirectionalLight3D.new()
	light.rotation_degrees = Vector3(-40, -30, 0)
	light.light_energy = 1.1
	stage.add_child(light)
	_camera = Camera3D.new()
	_camera.projection = Camera3D.PROJECTION_ORTHOGONAL
	_camera.size = 3.9
	_camera.keep_aspect = Camera3D.KEEP_WIDTH
	_camera.cull_mask = 1
	stage.add_child(_camera)
	_camera.position = Vector3(2.0, 2.3, 5.8)
	_camera.look_at(Vector3(0, 0.85, 0))
	var floor_node := MeshInstance3D.new()
	var floor_mesh := PlaneMesh.new()
	floor_mesh.size = Vector2(16, 12)
	floor_node.mesh = floor_mesh
	floor_node.position.y = -0.035
	var material := StandardMaterial3D.new()
	material.albedo_color = Color("243039")
	material.roughness = 1.0
	floor_node.material_override = material
	stage.add_child(floor_node)
	var models: Dictionary = JSON.parse_string(FileAccess.get_file_as_string("res://data/actors/models.json"))
	var animations: Dictionary = JSON.parse_string(FileAccess.get_file_as_string("res://data/animations/luminous.json"))
	_equipment = JSON.parse_string(FileAccess.get_file_as_string("res://data/actors/equipment.json"))
	for index: int in 2:
		var actor := ReplicatedActor3D.new()
		stage.add_child(actor)
		var errors := actor.configure({"actor_id": 900001 + index, "x": 0, "y": 0, "rotation": 0,
			"appearance": {"hair": 1}, "equipment_visuals": {}, "in_combat": true},
			CoordinateAdapter.new({"walkingHeight": 0.0}), models.models["greyhaven_male" if index == 0 else "glasswarden_male"], animations, _equipment)
		if not errors.is_empty(): push_error("Technique preview: " + str(errors))
		actor.set_physics_process(false)
		if index == 0: source = actor
		else: target = actor
	effects = Node3D.new()
	effects.name = "TechniquePreviewEffects"
	stage.add_child(effects)

func replay() -> void:
	if stage == null: return
	source.end_charge_leap()
	source.set_physics_process(false)
	clock = 0.0
	_released = false
	_flurry_hits = 0
	_countered = false
	for effect in effects.get_children(): effect.free()
	var key := str(row.get("key", ""))
	var ranged := key in Presentation.RANGED
	var support := key in Presentation.SUPPORT
	_fit_camera()
	source.position = Vector3(-1.5 if ranged else -0.75, 0, 0)
	target.position = Vector3(1.5 if ranged else 0.75, 0, 0)
	if key == "charge":
		source.position.x = -2.4
		target.position.x = 0.9
	source.server_target = source.position
	source.rotation.y = -PI * 0.5
	target.rotation.y = PI * 0.5
	target.visible = not support or key in ["intercept", "challenge", "provoke", "riposte"]
	if support and not target.visible: source.position.x = 0
	var equipment := {0: 114}
	if key in ["shield_bash", "brace", "intercept"]: equipment[1] = 106
	elif key in ["cleave", "executioners_stroke"]: equipment = {0: 144}
	elif key == "sunder": equipment = {0: 130}
	elif key in ["lunge", "keep_at_bay"]: equipment = {0: 134}
	elif key == "backstab": equipment = {0: 119}
	elif key == "flurry": equipment = {0: 114, 1: 160}
	elif ranged or key == "step_back": equipment = {0: 164}
	source.apply_equipment_visuals(equipment)
	target.play_action(&"combat_idle", true)
	if ranged: source.play_action(&"ranged_draw", true)
	else: source.play_action(&"combat_idle", true)

func _process(delta: float) -> void:
	clock += delta
	if source == null: return
	source._advance_facing_offset(delta)
	target._advance_facing_offset(delta)
	var key := str(row.get("key", ""))
	var ranged := key in Presentation.RANGED
	var release := 0.85 if ranged else 0.3
	if key == "charge":
		if clock >= release and not _released:
			_released = true
			var landing := Vector3(-0.45, 0, 0)
			_emit_cue(key, "activate", false)
			source.begin_charge_leap(PackedVector3Array([source.position, landing]), 0.36)
			source.server_target = landing
			source.set_physics_process(false)
		if _released and not _countered:
			source._physics_process(delta)
			if clock >= release + 0.36:
				_countered = true
				source.end_charge_leap()
				_emit_cue(key, "land", false)
				_emit_cue(key, "strike", true)
		if clock >= LOOP_SECONDS: replay()
		return
	if clock >= release and not _released:
		_released = true
		var phase := "shot" if ranged else "activate" if key in Presentation.SUPPORT else "strike"
		_emit_cue(key, phase, key not in Presentation.SUPPORT)
		_flurry_hits = 1
		if key in ["challenge", "provoke"]: _emit_cue(key, "impact", true)
		if ranged:
			var arrow := MissileFlight3D.new()
			effects.add_child(arrow)
			arrow.configure(source.global_position, target.global_position, source.ranged_release_origin())
	if key == "flurry" and _released:
		while _flurry_hits < 3 and clock >= release + _flurry_hits * 0.35:
			_emit_cue(key, "strike", true)
			_flurry_hits += 1
	if key == "riposte" and not _countered and clock >= release + 0.9:
		_countered = true
		_emit_cue(key, "counter", true)
	if clock >= LOOP_SECONDS: replay()

func _emit_cue(key: String, phase: String, landed: bool) -> void:
	source.play_technique(key, phase)
	var effect := Effect.new()
	effects.add_child(effect)
	effect.configure(key, phase, source, target if target.visible else null, landed)

func _fit_camera() -> void:
	if _camera == null: return
	var key := str(row.get("key", ""))
	var width := 6.2 if key == "charge" else 5.8 if key in Presentation.RANGED or key == "war_cry" else 3.9
	# The book is a wide strip, while the review scene is nearly square.
	# Preserve enough vertical room for heads, feet and overhead impact cues.
	_camera.size = maxf(width, 2.6 * size.x / maxf(1.0, size.y))
