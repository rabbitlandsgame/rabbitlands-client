extends Control
## Offline review of the production effects, with deterministic frame stepping.
const PANELS := [
	["FIRE BOLT", "Focused core · ember wake · contact burst", 2],
	["POISON TARGET", "Winding trail · drifting venom", 0],
	["HEAL TARGET", "Arcing wisps · rising restoration", 1],
	["ETHER DRAIN TARGET", "Energy flows from target back to caster", 10]]
@export var power_comparison := false
@export var family_page := 0
var panels: Array = PANELS
var power_levels: Array[int] = [1, 1, 1, 1]
var actors: Array[ReplicatedActor3D] = []
var stages: Array[Node3D] = []
var effects: Array[WorldEffect3D] = []
var clock := 0.0
var paused := false

func _ready() -> void:
	if family_page > 0:
		panels = [["MAGIC BOLT", "Focused violet helix", 83], ["FROST BOLT", "Icy trail and six-point impact", 84],
			["RADIATION BOLT", "Orbiting energy strands", 85], ["LIFE DRAIN TARGET", "Crimson energy returns to caster", 86]] if family_page == 1 else [
			["ELEMENTAL WARD", "Heat, cold and radiation arcs", 74], ["DISPEL", "Purifying outward sparks", 79],
			["TRANSMUTE", "Gathering light becomes rising coins", 19], ["RECALL", "Stacked portal rings", 18]]
		power_levels = [3,3,3,3]
	if power_comparison:
		power_levels = [1, 5, 8, 10]
		panels = []
		for power: int in power_levels:
			panels.append(["FIRE BOLT  /  POWER %d" % power,
				"Same cast and distance · power tier %d / 10" % power, 2])
	var background := ColorRect.new()
	background.color = Color("101c25")
	background.set_anchors_and_offsets_preset(Control.PRESET_FULL_RECT)
	add_child(background)
	var margin := MarginContainer.new()
	margin.set_anchors_and_offsets_preset(Control.PRESET_FULL_RECT)
	for side: String in ["left", "right", "top", "bottom"]:
		margin.add_theme_constant_override("margin_" + side, 22)
	add_child(margin)
	var column := VBoxContainer.new()
	column.add_theme_constant_override("separation", 12)
	margin.add_child(column)
	var title := Label.new()
	title.text = "RABBIT LANDS   /   MAGIC POWER" if power_comparison else "RABBIT LANDS   /   SPELL EXCHANGES"
	title.add_theme_font_size_override("font_size", 25)
	title.add_theme_color_override("font_color", Color("ead5a6"))
	column.add_child(title)
	var grid := GridContainer.new()
	grid.columns = 2
	grid.size_flags_vertical = Control.SIZE_EXPAND_FILL
	grid.add_theme_constant_override("h_separation", 16)
	grid.add_theme_constant_override("v_separation", 16)
	column.add_child(grid)
	var models: Dictionary = JSON.parse_string(FileAccess.get_file_as_string("res://data/actors/models.json"))["models"]
	var animations: Dictionary = JSON.parse_string(FileAccess.get_file_as_string("res://data/animations/luminous.json"))
	var equipment: Dictionary = JSON.parse_string(FileAccess.get_file_as_string("res://data/actors/equipment.json"))
	for panel: Array in panels:
		var box := VBoxContainer.new()
		box.size_flags_horizontal = Control.SIZE_EXPAND_FILL
		box.size_flags_vertical = Control.SIZE_EXPAND_FILL
		grid.add_child(box)
		var label := Label.new()
		label.text = panel[0]
		label.add_theme_font_size_override("font_size", 18)
		box.add_child(label)
		var container := SubViewportContainer.new()
		container.stretch = true
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
		environment.environment.background_color = Color("253945")
		environment.environment.ambient_light_source = Environment.AMBIENT_SOURCE_COLOR
		environment.environment.ambient_light_color = Color(0.78, 0.86, 1.0)
		environment.environment.ambient_light_energy = 0.65
		stage.add_child(environment)
		var sun := DirectionalLight3D.new()
		sun.rotation_degrees = Vector3(-40, -30, 0)
		sun.light_energy = 1.1
		stage.add_child(sun)
		var floor_node := MeshInstance3D.new()
		var floor_mesh := BoxMesh.new()
		floor_mesh.size = Vector3(7.4, 0.08, 3.0)
		floor_node.mesh = floor_mesh
		floor_node.position.y = -0.05
		var floor_material := StandardMaterial3D.new()
		floor_material.albedo_color = Color("415254")
		floor_node.material_override = floor_material
		stage.add_child(floor_node)
		var camera := Camera3D.new()
		camera.projection = Camera3D.PROJECTION_ORTHOGONAL
		camera.size = 7.7
		camera.cull_mask = 1
		camera.keep_aspect = Camera3D.KEEP_WIDTH
		stage.add_child(camera)
		camera.position = Vector3(0.7, 4.4, 8.3)
		camera.look_at(Vector3(0, 0.65, 0))
		for i: int in 2:
			var actor := ReplicatedActor3D.new()
			stage.add_child(actor)
			var errors := actor.configure({"actor_id": 800 + actors.size(), "x": 0, "y": 0,
				"rotation": 0, "appearance": {"hair": 0}}, CoordinateAdapter.new({"walkingHeight": 0.0}),
				models["luminous_female" if i == 0 else "greyhaven_male"], animations, equipment)
			if not errors.is_empty():
				push_error(str(errors))
			actor.set_physics_process(false)
			actor.position = Vector3(-2.4 if i == 0 else 2.4, 0, 0)
			actor.rotation.y = -PI * 0.5 if i == 0 else PI * 0.5
			actors.append(actor)
		var caption := Label.new()
		caption.text = panel[1]
		caption.add_theme_font_size_override("font_size", 14)
		caption.add_theme_color_override("font_color", Color("b1c4c9"))
		box.add_child(caption)
	var instructions := Label.new()
	instructions.text = "SPACE  pause / resume     R  restart     •     Caster left / target right"
	instructions.add_theme_font_size_override("font_size", 14)
	column.add_child(instructions)
	restart()

func restart() -> void:
	clock = 0.0
	for effect: WorldEffect3D in effects:
		if is_instance_valid(effect):
			effect.free()
	effects.clear()
	for i: int in panels.size():
		var caster := actors[i * 2]
		var target := actors[i * 2 + 1]
		caster.set_spell_variant(int(panels[i][2]))
		caster.play_action(SpellPresentation.action_for_effect(panels[i][2]), true)
		target.play_action(&"combat_idle", true)
		for actor: ReplicatedActor3D in [caster, target]:
			actor.animation_player.stop()
			actor.animation_player.play(actor.resolver.clip_for_action(actor.current_action), 0.0)
			actor.animation_player.advance(0.0)
			actor.animation_player.pause()
			actor._advance_facing_offset(1.0)
		var effect := WorldEffect3D.new()
		stages[i].add_child(effect)
		effect.configure(panels[i][2], caster.global_position, null if family_page == 2 else target.global_position, power_levels[i])
		effect.bind_actors(caster, target)
		effect.set_process(false)
		effects.append(effect)
	advance(0.0)

func advance(delta: float) -> void:
	clock += delta
	for actor: ReplicatedActor3D in actors:
		actor.animation_player.seek(minf(clock, actor.animation_player.current_animation_length - 0.001), true)
		actor.combat_presentation.update_pose()
	for effect: WorldEffect3D in effects:
		if is_instance_valid(effect):
			effect._process(delta)

func _process(delta: float) -> void:
	if not paused:
		advance(delta)
		if clock > 2.5:
			restart()

func _unhandled_key_input(event: InputEvent) -> void:
	if event is InputEventKey and event.pressed and not event.echo:
		if event.keycode == KEY_SPACE:
			paused = not paused
			for effect: WorldEffect3D in effects:
				if is_instance_valid(effect):
					(effect.get_node("EffectBurst") as GPUParticles3D).speed_scale = 0.0 if paused else 1.0
		elif event.keycode == KEY_R:
			restart()
