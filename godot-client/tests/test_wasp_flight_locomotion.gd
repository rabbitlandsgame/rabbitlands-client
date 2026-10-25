extends SceneTree
var failures := 0
func _init() -> void: run.call_deferred()
func check(ok: bool, message: String) -> void:
	if not ok:
		failures += 1
		push_error(message)
func run() -> void:
	var models: Dictionary = JSON.parse_string(FileAccess.get_file_as_string("res://data/actors/models.json"))
	var model: Dictionary = models.models.giant_wasp
	var mapping: Dictionary = JSON.parse_string(FileAccess.get_file_as_string(model.animationMap))
	var actor := ReplicatedActor3D.new()
	root.add_child(actor)
	var dto := {"actor_id": 901, "kind": 5, "x": 0, "y": 0, "rotation": 0, "health": 100, "max_health": 100}
	check(actor.configure(dto, CoordinateAdapter.new({}), model, mapping).is_empty(), "current wasp imports")
	actor.set_physics_process(false)
	var player := actor.animation_player
	player.callback_mode_process = AnimationMixer.ANIMATION_CALLBACK_MODE_PROCESS_MANUAL
	for action: StringName in [&"idle", &"combat_idle", &"walk", &"run", &"turn"]:
		actor.play_action(action)
		player.advance(.31)
		check(player.assigned_animation == &"Fly", "ordinary server action flies: " + str(action))
		check(player.get_animation("Fly").loop_mode == Animation.LOOP_LINEAR, "flight loops")
		var corrective := 0.0
		for mesh: MeshInstance3D in actor.find_children("*", "MeshInstance3D", true, false):
			if not mesh.mesh is ArrayMesh: continue
			for shape: int in mesh.mesh.get_blend_shape_count(): corrective += absf(mesh.get_blend_shape_value(shape))
		print("WASP_CORRECTIVE ", action, " ", corrective, " at=", player.current_animation_position)
		check(corrective > .5, "flight keeps anatomical wing correctives")
	actor.play_action(&"attack_primary", true)
	player.advance(.2)
	check(player.assigned_animation == &"Sword_Attack", "authored sting preserved")
	player.advance(2)
	check(actor.current_action == &"idle" and player.assigned_animation == &"Fly", "attack recovers to flight")
	actor.play_action(&"death", true)
	player.advance(3)
	check(actor.current_action == &"death", "death remains latched")
	actor.free()
	NativeAnimationImporter.clear()
	GlbSceneCache.clear()
	await process_frame
	print("wasp flight failures=", failures)
	quit(failures)
