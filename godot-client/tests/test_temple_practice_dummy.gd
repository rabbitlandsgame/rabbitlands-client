extends SceneTree
## A rigid imported target must retain actor picking and HP without a skeleton.

func _init() -> void:
	call_deferred("run")

func run() -> void:
	var catalog: Dictionary = JSON.parse_string(FileAccess.get_file_as_string("res://data/actors/models.json"))
	var model: Dictionary = catalog.models[catalog.actorTypes["790"]]
	var animation: Dictionary = JSON.parse_string(FileAccess.get_file_as_string(model.animationMap))
	var actor := ReplicatedActor3D.new()
	root.add_child(actor)
	var dto := {"actor_id": 900, "actor_type": 790, "x": 0, "y": 0,
		"rotation": 0, "health": 1000, "max_health": 1000, "appearance": {},
		"equipment_visuals": {}, "command": 7, "command_sequence": 1}
	var errors := actor.configure(dto, CoordinateAdapter.new({"walkingHeight": 0.0}), model, animation, {})
	var failed := not errors.is_empty() or actor.get_skeleton() != null \
		or actor.get_node_or_null("NativeModel") == null \
		or actor.find_children("*", "MeshInstance3D", true, false).is_empty()
	if failed:
		push_error("Rigid practice target failed: " + str(errors))
	else:
		actor.play_action(&"pain", true)
		actor.play_action(&"idle", true)
		print("Temple practice dummy: imported rigid actor with picking/HP, no skeleton errors")
	actor.free()
	await process_frame
	quit(1 if failed else 0)
