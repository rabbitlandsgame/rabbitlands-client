extends "res://tests/integration/rendered_cape_over_armour.gd"
## Check the skinned fabric, not helper-bone directions: the old solver had
## vertical particles while its tilted bind frames held the hem out behind.

const STEP := 1.0 / 60.0
const MAX_IDLE_SLOPE := 0.06

func _run() -> void:
	_main = (load("res://src/app/main.tscn") as PackedScene).instantiate() as Control
	root.add_child(_main)
	await process_frame
	_main.hide()
	_equipment_config = _main.get("equipment_config") as Dictionary
	_adapter = CoordinateAdapter.new({"walkingHeight": 0.0})
	_stage = Node3D.new()
	root.add_child(_stage)
	var models: Dictionary = _main.get("models")
	for rig: String in ["luminous_male", "luminous_female"]:
		_model_config = models[rig]
		_animation_config = _main.call("_animation_for_model", _model_config)
		for body: int in BODIES:
			var actor := _spawn({"0": 114, "1": 106, "2": 1,
				"3": 117, "4": 171, "5": body, "6": 192})
			actor.set_process(false)
			actor.set_physics_process(false)
			var player := actor.animation_player
			actor.play_action(&"idle")
			player.advance(0.4)
			player.pause()
			var skeleton := _skeleton_of(actor)
			var cloth := skeleton.get_node("CapeCloth")
			cloth.call("reset")
			_step_cloth(cloth, 180)
			_check_hang(skeleton, "%s body %d fresh idle" % [rig, body])
			var settled := _posed(skeleton, 2)
			_step_cloth(cloth, 60)
			var later := _posed(skeleton, 2)
			var drift := 0.0
			for i: int in range(settled.size()):
				drift = maxf(drift, settled[i].distance_to(later[i]))
			_check(drift < 0.008, "%s body %d settles (%.1f mm drift)"
				% [rig, body, drift * 1000.0])
			actor.play_action(&"walk")
			for frame: int in range(90):
				actor.position.z -= 0.05
				player.advance(STEP)
				_step_cloth(cloth, 1)
			actor.play_action(&"idle")
			player.advance(0.4)
			player.pause()
			_step_cloth(cloth, 180)
			_check_hang(skeleton, "%s body %d stopped walking" % [rig, body])
			actor.queue_free()
			await process_frame
	print("cape idle tests: ", "PASS" if _failures == 0 else "FAIL (%d)" % _failures)
	_main.queue_free()
	await process_frame
	quit(1 if _failures else 0)

func _step_cloth(cloth: Node, count: int) -> void:
	for frame: int in range(count):
		cloth.call("_process_modification_with_delta", STEP)

func _check_hang(skeleton: Skeleton3D, label: String) -> void:
	var cape := _posed(skeleton, 2)
	var anchor := skeleton.get_bone_global_pose(skeleton.find_bone("spine_03")).origin
	var depths := PackedFloat32Array()
	for fraction: float in [0.55, 0.25]:
		var total := 0.0
		var count := 0
		for p: Vector3 in cape:
			if absf(p.x - anchor.x) < 0.10 and absf(p.y - anchor.y * fraction) < 0.06:
				total += p.z
				count += 1
		_check(count > 0, label + " has fabric in the measured band")
		depths.append(total / maxf(count, 1))
	var slope := absf(depths[1] - depths[0])
	_check(slope < MAX_IDLE_SLOPE, "%s hangs down (%.1f mm depth change)"
		% [label, slope * 1000.0])

func _check(ok: bool, label: String) -> void:
	if not ok:
		_failures += 1
	print("  ", "ok " if ok else "FAIL ", label)
