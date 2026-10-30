extends SceneTree
## A bow grip must follow the anatomical hand, without bending it out of cuffs.
var checks := 0
var failures: Array[String] = []
var max_wrist_change := 0.0
var max_grip_distance := 0.0
func _init() -> void:
	call_deferred("run")
func check(ok: bool, label: String) -> void:
	checks += 1
	if not ok:
		failures.append(label)
		push_error(label)
func read_json(path: String) -> Dictionary:
	return JSON.parse_string(FileAccess.get_file_as_string(path)) as Dictionary
func run() -> void:
	var models: Dictionary = read_json("res://data/actors/models.json").models
	var equipment := read_json("res://data/actors/equipment.json")
	var bow_visuals: Array[int] = []
	for key: String in equipment.models:
		if key.begins_with("0:") and RangerBow3D.supports_asset(str(equipment.models[key].get("scene", ""))):
			bow_visuals.append(int(key.split(":")[1]))
	check(bow_visuals.size() == 2, "both current imported bow designs are covered")
	for race: String in ["luminous","votary","glasswarden","orun","greyhaven","ssarathi","stoneborn","mycelari"]:
		for sex: String in ["male","female"]:
			var slug := race + "_" + sex
			var config: Dictionary = models[slug].duplicate(true)
			config["hairStyles"] = []
			var actor := ReplicatedActor3D.new()
			root.add_child(actor)
			var errors := actor.configure({"actor_id":9112,"kind":1,"x":0,"y":0,"rotation":0,
				"appearance":{},"equipment_visuals":{}},CoordinateAdapter.new({"walkingHeight":0.}),
				config,read_json(str(config.animationMap)),equipment)
			check(errors.is_empty(),slug+" configures")
			actor.set_process(false);actor.set_physics_process(false)
			var skeleton := actor.get_skeleton()
			var hand := skeleton.find_bone("hand_l")
			for bow_visual: int in bow_visuals:
				actor.apply_equipment_visuals({0:bow_visual,5:225})
				for action: StringName in [&"idle",&"walk",&"run",&"combat_idle",&"ranged_draw",&"ranged_hold",&"ranged_attack",&"idle"]:
					for time: float in [.2,.7,1.2]:
						actor.play_action(action,true)
						actor.animation_player.advance(time);actor.animation_player.pause()
						var original := skeleton.get_bone_pose_rotation(hand)
						actor._weapon_carry._process_modification_with_delta(.3)
						var corrected := skeleton.get_bone_pose_rotation(hand)
						var change := original.angle_to(corrected)
						max_wrist_change = maxf(max_wrist_change, change)
						check(change<.001,slug+" retains animated wrist: "+str(action))
						var grip := actor.combat_presentation.carried_bow_grip()
						var wrist := skeleton.global_transform * skeleton.get_bone_global_pose(hand)
						var distance := grip.origin.distance_to(wrist.origin)
						max_grip_distance = maxf(max_grip_distance, distance)
						check(distance<.11,slug+" grip stays in the fist")
						actor.combat_presentation.update_pose()
						check(actor.combat_presentation.bow.global_transform.is_finite(),slug+" finite bow/action switch")
			actor.free();await process_frame
	print("EQUIPMENT_WRIST_ALIGNMENT ",checks," checks; failures=",failures)
	print("WRIST_MEASURE max_local_change_rad=",max_wrist_change," max_grip_distance_m=",max_grip_distance)
	quit(0 if failures.is_empty() else 1)
