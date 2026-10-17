extends SceneTree
## Cached spell bodies must not recolor concurrent casts or lose power tiers.
const Flight = preload("res://src/world/spell_flight_3d.gd")
var failures := 0

func _init() -> void:
	call_deferred("_run")

func _run() -> void:
	var fire: Node3D = Flight.new()
	var frost: Node3D = Flight.new()
	root.add_child(fire)
	root.add_child(frost)
	fire.configure(2, Color("ff9a42"), Vector3.ZERO, Vector3.RIGHT * 5, 5)
	var fire_material: ShaderMaterial = fire.get("_ribbon_material")
	var fire_colour: Color = fire_material.get_shader_parameter("tint")
	frost.configure(84, Color("76dbff"), Vector3.ZERO, Vector3.RIGHT * 5, 5)
	var frost_material: ShaderMaterial = frost.get("_ribbon_material")
	_expect(fire_material != frost_material, "concurrent palettes have independent materials")
	_expect(fire_material.get_shader_parameter("tint") == fire_colour,
		"configuring frost cannot recolor a fire spell already in flight")
	_expect(frost_material.get_shader_parameter("tint") == Color("1376c4"),
		"frost uses the exact approved option A body")
	var previous_intensity := 0.0
	for power: int in range(1, 11):
		frost.configure(84, Color("76dbff"), Vector3.ZERO, Vector3.RIGHT * 5, power)
		var body: ShaderMaterial = frost.get("_ribbon_material")
		var intensity: float = body.get_shader_parameter("intensity")
		_expect(intensity > previous_intensity, "power %d increases body intensity" % power)
		_expect(body.next_pass != null, "power %d retains its glow" % power)
		previous_intensity = intensity
	fire.free()
	frost.free()
	# Exercise real hand attachments independently of weapon catalog fixtures.
	var models: Dictionary = JSON.parse_string(FileAccess.get_file_as_string("res://data/actors/models.json"))
	var animations: Dictionary = JSON.parse_string(FileAccess.get_file_as_string("res://data/animations/luminous.json"))
	var equipment: Dictionary = JSON.parse_string(FileAccess.get_file_as_string("res://data/actors/equipment.json"))
	var actor := ReplicatedActor3D.new()
	root.add_child(actor)
	var errors := actor.configure({"actor_id": 901, "x": 0, "y": 0, "rotation": 0, "appearance": {}},
		CoordinateAdapter.new({"walkingHeight": 0.0}), models.models.luminous_female, animations, equipment)
	_expect(errors.is_empty(), "current player rig loads")
	if actor.combat_presentation != null:
		actor.set_physics_process(false)
		actor.play_action(&"cast_aggressive", true)
		actor.combat_presentation.set_spell_palette(Color("76dbff"), 5)
		actor.animation_player.seek(0.3, true)
		actor.combat_presentation.update_pose()
		var action_mesh: Mesh = actor.combat_presentation.get_node("ActionEffects").mesh
		_expect(action_mesh.get_surface_count() > 0, "the current casting action draws its hand cues")
		if action_mesh.get_surface_count() > 0:
			var hand_material := action_mesh.surface_get_material(0) as ShaderMaterial
			_expect(hand_material != null and hand_material.get_shader_parameter("tint") == Color("1376c4"),
				"hand cues retain the approved frost body")
	else:
		_expect(false, "the current player has combat presentation")
	actor.free()
	await process_frame
	NativeAnimationImporter.clear()
	GlbSceneCache.clear()
	print("spell visual materials: ", "PASS" if failures == 0 else "FAIL")
	quit(failures)

func _expect(condition: bool, message: String) -> void:
	if not condition:
		failures += 1
		push_error(message)
