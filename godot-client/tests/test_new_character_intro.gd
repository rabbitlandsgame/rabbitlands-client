extends SceneTree

const Intro := preload("res://src/camera/new_character_intro.gd")
var failures := 0

class Guide extends Node3D:
	var post := Vector3.ZERO
	var action: StringName = &"idle"
	var restored := false
	func set_cinematic_presentation(point: Vector3, yaw: float, value: StringName, _speed: float) -> void:
		global_position = point
		rotation.y = yaw
		action = value
	func cinematic_action_duration(_action: StringName) -> float:
		return 1.0
	func end_cinematic_presentation() -> void:
		global_position = post
		action = &"idle"
		restored = true

func _init() -> void:
	call_deferred("run")

func expect(ok: bool, message: String) -> void:
	if not ok:
		failures += 1
		push_error(message)
	else:
		print("PASS: ", message)

func run() -> void:
	var spawn := Vector3(-152, 121.6, 34)
	var shot: RefCounted = Intro.build_shot(spawn)
	expect(shot.errors.is_empty() and is_equal_approx(shot.duration, 8.0), "eight-second trailer spline resolves")
	var end: Dictionary = Intro.evaluate(shot, shot.duration)
	expect((end.position as Vector3).is_equal_approx(Intro.final_position(spawn, 0)), "spline ends at the playable camera pose")
	var previous: Dictionary = Intro.evaluate(shot, shot.duration - 0.001)
	expect((previous.position as Vector3).distance_to(end.position) < 0.001, "descent comes to rest before control returns")
	for time: float in [0.0, 1.0, 3.0, 5.0, 7.0, 8.0]:
		var pose: Dictionary = Intro.evaluate(shot, time)
		expect((pose.position as Vector3).is_finite() and (pose.position as Vector3).y > spawn.y + 3.0,
			"camera stays above the arrival plaza at %.1fs" % time)
	var stream := ContinentChunkStream.new()
	stream.entries.assign([
		{"id": "spawn", "bounds": {"min": [-10,0,-10], "max": [10,1,10]}, "estimatedResidentBytes": 10},
		{"id": "vista", "bounds": {"min": [390,0,-10], "max": [410,1,10]}, "estimatedResidentBytes": 10},
		{"id": "unused", "bounds": {"min": [790,0,-10], "max": [810,1,10]}, "estimatedResidentBytes": 10}])
	stream.maximum_resident_bytes = 15
	stream.preload_views(PackedVector3Array([Vector3.ZERO, Vector3(400,0,0)]), 20)
	var selected: Array = stream.selection(Vector3(400,0,0))
	expect(selected.size() == 2 and selected[0].id == "spawn" and selected[1].id == "vista",
		"background load prioritizes spawn and holds the distant view across camera movement")
	expect(not stream.views_ready(), "intro waits for every required chunk")
	stream.cells = {"spawn": {}, "vista": {}}
	expect(stream.views_ready(), "all required chunks unlock the intro")
	stream.cells.clear()
	stream.release_views()
	expect(stream.selection(Vector3.ZERO).size() == 1, "normal distance and byte budgets return after the intro")
	stream.free()

	var main := (load("res://src/app/main.tscn") as PackedScene).instantiate()
	root.add_child(main)
	await process_frame
	expect(main.has_method("_update_character_intro"), "production main scene compiles")
	if not main.has_method("_update_character_intro"):
		quit(1)
		return
	var intro: Node = main.character_intro
	var rig: IsometricCameraController = main.camera_rig
	var player := Node3D.new()
	main.world_root.add_child(player)
	player.global_position = spawn
	expect(not intro.blocks_input(), "ordinary login starts with no intro armed")
	intro.arm(main.main_viewport)
	intro.update(0.016, rig, player, true, false)
	expect(intro.pending and not intro.playing, "wait for Nash and his authoritative quest marker")
	intro.update(0.016, rig, player, false, true)
	expect(intro.pending, "wait for actual player ground")
	for frame: int in range(3):
		intro.update(0.016, rig, player, true, true)
	expect(intro.playing and intro.blocks_input(), "play once scenery, player and guide are ready")
	intro.update(8.0, rig, player, true, true)
	expect(not intro.blocks_input() and not intro.playing, "control returns after the brief flyover")
	expect(rig.camera.global_position.is_equal_approx(end.position), "no position jump at camera handoff")
	expect(is_equal_approx(rig.distance, 9.0) and is_equal_approx(rig.pitch_degrees, -24.0), "closer rear view persists in gameplay")
	var guide_head := spawn + Vector3(4, 2.4, -6)
	var projected: Vector2 = rig.camera.unproject_position(guide_head)
	expect(not rig.camera.is_position_behind(guide_head) and Rect2(Vector2.ZERO, Vector2(main.main_viewport.size)).has_point(projected),
		"Nash's head marker is inside the starting camera frame")
	intro.arm(main.main_viewport)
	intro.cancel()
	expect(not intro.blocks_input(), "cancelled login restores input and dismisses loading curtain")
	var guide := Guide.new()
	main.world_root.add_child(guide)
	guide.post = spawn + Vector3(4,0,-6)
	guide.global_position = guide.post
	var requests: Array[int] = []
	intro.conversation_requested.connect(func(id: int) -> void: requests.append(id))
	intro.arm(main.main_viewport)
	for frame: int in range(3):
		intro.update(0.016, rig, player, true, true, guide, 100)
	intro.update(8.0, rig, player, true, true, guide, 100)
	expect(intro.greeting_phase == &"wave" and guide.action == &"emote_greet", "Nash waves when the camera arrives")
	expect(intro.blocks_input() and bool(main.call("_movement_locked", true)), "movement remains locked after the flyover, including its modifier override")
	intro.update(1.1, rig, player, true, true)
	intro.update(0.2, rig, player, true, true)
	expect(guide.action == &"run" and guide.global_position.distance_to(guide.post) > 0.1, "Nash runs towards the player after waving")
	var beacon: MapMarker3D = intro._guide_beacon
	var sparks: int = beacon.get_node("RisingSparks").get_instance_id()
	expect(beacon.global_position.is_equal_approx(guide.global_position), "green particles follow Nash's approach")
	intro.update(2.0, rig, player, true, true)
	expect(requests == [100] and intro.allows_dialogue(), "approach opens the actual tutorial exactly once and enables dialogue controls")
	var conversation := {"open":true, "name":"Nash", "text":"Ilyon needs a dressing.", "options":[]}
	intro.update(0.1, rig, player, true, true, null, -1, conversation)
	intro.update(600.0, rig, player, true, true, null, -1, conversation)
	expect(intro.greeting_phase == &"conversation" and intro.blocks_input(), "player can read and answer without a conversation time limit")
	intro.update(0.1, rig, player, true, true, null, -1, {"open":false})
	intro.update(0.2, rig, player, true, true)
	expect(intro.greeting_phase == &"return" and intro.blocks_input(), "closing the conversation starts the run back while movement stays locked")
	expect(beacon.global_position.is_equal_approx(guide.global_position) and beacon.get_node("RisingSparks").get_instance_id() == sparks,
		"the same particle animation follows Nash back without restarting")
	intro.update(2.0, rig, player, true, true)
	expect(guide.restored and guide.global_position.is_equal_approx(guide.post) and not intro.blocks_input(),
		"only arriving at Nash's original post restores player control")
	expect(requests == [100], "conversation updates never restart the tutorial")
	expect(not intro.owns_guide_beacon(100) and beacon.is_queued_for_deletion(), "arrival beacon ends after Nash returns")
	intro.arm(main.main_viewport)
	for frame: int in range(3):
		intro.update(0.016, rig, player, true, true, guide, 100)
	intro.update(8.0, rig, player, true, true)
	intro.update(1.1, rig, player, true, true)
	intro.update(2.0, rig, player, true, true)
	intro.update(13.0, rig, player, true, true)
	expect(intro.greeting_phase == &"return", "an unavailable dialogue returns Nash rather than stranding the player")
	intro.cancel()
	expect(not intro.blocks_input() and guide.global_position.is_equal_approx(guide.post), "disconnect or map change restores Nash and input immediately")
	main.queue_free()
	await process_frame
	print("new character intro: ", "PASS" if failures == 0 else "FAIL", " (", failures, " failures)")
	quit(failures)
