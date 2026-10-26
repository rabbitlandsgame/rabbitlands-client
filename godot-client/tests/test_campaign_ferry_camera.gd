extends SceneTree
const Presentation := preload("res://src/world/campaign_scene.gd")
var checks := 0
var failures := 0

class Rig extends Node3D:
	var camera: Camera3D
	var focus := Vector3.ZERO
	var distance := 31.0
	var pitch_degrees := -52.0
	var yaw_degrees := 42.0
	func cancel_rotation() -> void: pass

class Actor extends Node3D:
	var server_target := Transform3D.IDENTITY
	var action := &"idle"
	func set_cinematic_presentation(point: Vector3, yaw: float, value: StringName, _speed: float) -> void:
		global_position = point
		rotation.y = yaw
		action = value
	func end_cinematic_presentation() -> void:
		global_transform = server_target
		action = &"idle"

func _init() -> void: run.call_deferred()
func expect(ok: bool, message: String) -> void:
	checks += 1
	if ok: print("PASS: ", message)
	else:
		failures += 1
		push_error(message)

func fixture(token: String) -> Dictionary:
	var stage := Node3D.new()
	root.add_child(stage)
	var adapter := CoordinateAdapter.new({"metresPerTile": 1.0, "serverOrigin": [435, 448], "walkingHeight": 2.5, "invertServerY": true})
	var roles := {"odo": 2, "worker": 3, "clerk": 4, "foreman": 5}
	var tiles := {1: Vector2i(450, 308), 2: Vector2i(450, 313), 3: Vector2i(457, 319), 4: Vector2i(444, 310), 5: Vector2i(456, 318)}
	var actors := {}
	for id: int in tiles:
		var actor := Actor.new()
		stage.add_child(actor)
		var tile: Vector2i = tiles[id]
		actor.global_position = adapter.tile_center(tile.x, tile.y)
		actor.server_target = actor.global_transform
		actors[id] = actor
	var rig := Rig.new()
	stage.add_child(rig)
	rig.focus = (actors[1] as Node3D).global_position
	rig.global_position = rig.focus
	var camera := Camera3D.new()
	rig.add_child(camera)
	rig.camera = camera
	camera.position = Vector3(14, 17, 11)
	camera.look_at(rig.focus + Vector3.UP * 1.2)
	camera.fov = 67.0
	camera.near = 0.8
	camera.far = 1800.0
	var scene := Presentation.new()
	root.add_child(scene)
	scene.set_reduced_motion(false, false)
	var state := {"version": 1, "kind": "opening", "active": true, "run_id": "ferry-camera", "map": "greenlight",
		"title": "The Ferry That Arrived Twice", "key": "assess", "actors": roles, "targets": [],
		"anchors": {"odo_meeting": [450, 313], "clerk_arrival": [444, 310], "clerk_stand": [447, 312],
			"foreman_arrival": [456, 318], "foreman_turn": [455, 317], "foreman_stand": [453, 315]},
		"scene": {"id": "measure.landing.arrival", "token": token, "requires_ack": true, "ack_revision": 1}}
	return {"stage": stage, "scene": scene, "rig": rig, "camera": camera, "actors": actors,
		"adapter": adapter, "state": state, "original": camera.global_transform, "focus": rig.focus,
		"source": JSON.stringify(state)}

func tick(f: Dictionary, delta: float, map := "greenlight", ready := true) -> void:
	f.scene.update(delta, f.state, f.rig, f.actors, 1, map, ready, f.adapter)
func at(f: Dictionary, time: float) -> void: tick(f, maxf(0, time - float(f.scene.elapsed)))
func tile_position(f: Dictionary, tile: Vector2i) -> Vector3: return f.adapter.tile_center(tile.x, tile.y)
func dispose(f: Dictionary) -> void:
	f.scene.cancel("test_complete")
	f.scene.queue_free()
	f.stage.queue_free()

func run() -> void:
	create_timer(90).timeout.connect(func() -> void: push_error("Ferry camera test timed out"); quit(1))
	root.size = Vector2i(1280, 720)
	root.get_node("Network").call("block_for_hud_preview")
	var arrival: Dictionary = Presentation.scene_definitions()["measure.landing.arrival"]
	var duration := float(arrival.duration)
	var f := fixture("continuous")
	var results: Array = []
	f.scene.presentation_finished.connect(func(token: String, reason: String) -> void: results.append([token, reason]))
	tick(f, 0.0)
	expect(f.scene.playing and f.camera.global_transform.is_equal_approx(f.original), "the first cinematic frame keeps the player's exact current viewport")
	expect(is_equal_approx(f.camera.fov, 67.0) and is_equal_approx(f.camera.near, 0.8), "entry keeps the player's existing lens before easing")
	tick(f, 0.01)
	expect(f.camera.global_position.distance_to(f.original.origin) < 0.01, "entry starts gently without a position jump")
	at(f, 1.2)
	expect(f.camera.global_position.distance_to(f.original.origin) > 0.1 and f.camera.fov > 50 and f.camera.fov < 67, "the camera and lens interpolate through the approach")
	at(f, 4.0)
	var group_view: Transform3D = f.camera.global_transform
	expect((f.actors[4] as Node3D).global_position.is_equal_approx(tile_position(f, Vector2i(447, 312))), "the clerk walks from the ferry side to Odo before speaking")
	expect((f.actors[5] as Node3D).global_position.is_equal_approx(tile_position(f, Vector2i(455, 317))), "the foreman approaches through the dry quay waypoint")
	expect((f.actors[3] as Node3D).global_transform.is_equal_approx((f.actors[3] as Actor).server_target), "the injured worker stays at the rescue site during the briefing")
	at(f, 6.0)
	expect(f.scene._dialogue.speaker_label.text == "Odo Fenn" and f.scene._caption.text.contains("safe way"), "Odo's highlighted name is separate from his dialogue")
	at(f, 10.0)
	expect(f.scene._dialogue.speaker_label.text == "Landing clerk", "the visible clerk receives the clerk's dialogue")
	expect(f.camera.global_transform.is_equal_approx(group_view), "the clerk speaks inside the same steady group view")
	at(f, 14.0)
	expect(f.scene._dialogue.speaker_label.text == "Dock foreman" and f.scene._caption.text.contains("crew"), "the healthy foreman speaks for the crew")
	at(f, 19.0)
	expect(f.scene._caption.text.contains("damaged boards"), "Odo names the physical inspection before any rescue choice")
	expect(f.camera.global_transform.is_equal_approx(group_view), "speaker changes and the inspection instruction keep the group framing steady")
	at(f, duration - 2.0)
	expect((f.actors[4] as Node3D).global_position.is_equal_approx((f.actors[4] as Actor).server_target.origin) \
		and (f.actors[5] as Node3D).global_position.is_equal_approx((f.actors[5] as Actor).server_target.origin), "both healthy speakers walk back to their live posts before camera release")
	var moving: Actor = f.actors[1]
	var displacement := Vector3(2, 0.3, -1)
	moving.global_position += displacement
	var target: Transform3D = f.original
	target.origin += displacement
	at(f, duration - 0.5)
	var near_end: float = f.camera.global_position.distance_to(target.origin)
	at(f, duration - 0.01)
	expect(f.camera.global_position.distance_to(target.origin) < near_end and f.camera.global_position.distance_to(target.origin) < 0.02, "the final shot eases into the player's latest live position")
	at(f, duration)
	expect(not f.scene.blocks_input() and f.camera.global_transform.is_equal_approx(target), "normal completion reaches the gameplay viewport with no final cut")
	expect(f.rig.focus.is_equal_approx(f.focus + displacement) and f.rig.distance == 31 and f.rig.yaw_degrees == 42 and f.rig.pitch_degrees == -52, "return preserves the player's zoom, orbit and updated focus")
	expect(is_equal_approx(f.camera.fov, 67) and is_equal_approx(f.camera.near, 0.8) and is_equal_approx(f.camera.far, 1800), "return restores every lens setting")
	expect(results == [["continuous", "finished"]] and JSON.stringify(f.state) == f.source, "one original acknowledgement follows release without changing objectives")
	dispose(f)
	var seek := fixture("seek")
	tick(seek, 0.0); at(seek, 10.0)
	var shot_offset: Array = arrival.shots[0].position
	var group_shot: Vector3 = (seek.actors[2] as Node3D).global_position + Vector3(shot_offset[0],shot_offset[1],shot_offset[2])
	expect(seek.camera.global_position.is_equal_approx(group_shot), "a direct arrival seek retains the authored group view rather than cutting to the current speaker")
	dispose(seek)
	# Keep the generic pose-order regression independent of this scene's new
	# steady group shot: a speaker-anchored shot must use the staged actor pose.
	seek = fixture("speaker-pose-order")
	var speaker_definition: Dictionary = Presentation.scene_definitions()["measure.landing.arrival"].duplicate(true)
	speaker_definition.shots = [
		{"t":0.0, "anchor_actor":"clerk", "position":[4.0, 3.5, 6.0], "target":[0.0, 1.2, 0.0]},
		{"t":duration, "anchor_actor":"clerk", "position":[4.0, 3.5, 6.0], "target":[0.0, 1.2, 0.0]}]
	seek.scene._definitions = {"measure.landing.arrival":speaker_definition}
	tick(seek, 0.0); at(seek, 10.0)
	var clerk_shot: Vector3 = (seek.actors[4] as Node3D).global_position + Vector3(4, 3.5, 6)
	expect(seek.camera.global_position.is_equal_approx(clerk_shot), "a generic speaker-anchored seek frames the current staged speaker rather than the old server post")
	dispose(seek)
	f = fixture("skip")
	results.clear()
	f.scene.presentation_finished.connect(func(token: String, reason: String) -> void: results.append([token, reason]))
	tick(f, 0.0); at(f, 10)
	var before_skip: Transform3D = f.camera.global_transform
	f.scene.skip()
	expect(f.scene.blocks_input() and f.scene._returning and f.camera.global_transform.is_equal_approx(before_skip) and results.is_empty(), "skip begins a short return without cutting or acknowledging early")
	tick(f, 0.35)
	expect(not f.camera.global_transform.is_equal_approx(before_skip) and not f.camera.global_transform.is_equal_approx(f.original), "skip passes through a real intermediate camera pose")
	tick(f, 0.35)
	expect(not f.scene.is_active() and f.camera.global_transform.is_equal_approx(f.original) and results == [["skip", "skipped"]], "skip releases control and acknowledges once after the gentle return")
	expect(f.scene.request_replay(f.state, "greenlight"), "the new camera handoff remains replayable")
	var replay: Array = []
	f.scene.replay_finished.connect(func(token: String, reason: String) -> void: replay.append([token, reason]))
	tick(f, 0.0); at(f, 8)
	f.scene.skip(); tick(f, 0.7); tick(f, 0.1)
	expect(results.size() == 1 and replay == [["skip", "skipped"]], "a replayed handoff never repeats the server acknowledgement")
	dispose(f)
	f = fixture("reduce")
	f.scene.set_reduced_motion(true, false)
	tick(f, 0.0); at(f, 14)
	expect(f.camera.global_transform.is_equal_approx(f.original) and is_equal_approx(f.camera.fov, 67), "reduced motion retains the player's own view throughout the scene")
	f.scene.skip()
	expect(not f.scene.is_active() and f.camera.global_transform.is_equal_approx(f.original), "reduced-motion skip releases immediately without a flyback")
	dispose(f)
	f = fixture("toggle")
	# Pause during the moving entry, because the later authored group shot is
	# intentionally static and has no camera motion to resume.
	tick(f, 0.0); at(f, 1.2)
	var before_toggle: Transform3D = f.camera.global_transform
	f.scene.set_reduced_motion(true, false); tick(f, 0.1)
	expect(f.camera.global_transform.is_equal_approx(before_toggle), "enabling reduced motion mid-scene freezes the current framing without a cut")
	f.scene.set_reduced_motion(false, false); tick(f, 0.0)
	expect(f.camera.global_transform.is_equal_approx(before_toggle), "resuming camera motion starts from the held viewport")
	tick(f, 0.5)
	expect(not f.camera.global_transform.is_equal_approx(before_toggle), "resumed camera motion eases back into the authored shot")
	f.scene.skip(); tick(f, 0.2); f.scene.set_reduced_motion(true, false)
	expect(not f.scene.is_active() and f.camera.global_transform.is_equal_approx(f.original), "enabling reduced motion during a skip-return ends the motion immediately")
	dispose(f)
	for reason: String in ["map_changed", "disconnected", "death", "actor_lost"]:
		f = fixture(reason)
		tick(f, 0.0); at(f, 10); f.scene.skip()
		f.scene.cancel(reason)
		expect(not f.scene.is_active() and f.camera.global_transform.is_equal_approx(f.original), reason + " interrupts the return safely without holding controls")
		dispose(f)
	f = fixture("wait-speaker")
	var clerk: Actor = f.actors[4]
	f.actors.erase(4)
	tick(f, 3.0)
	expect(f.scene.pending and not f.scene.blocks_input() and f.camera.global_transform.is_equal_approx(f.original), "a known speaker's pending native model cannot produce an empty speaking shot")
	f.actors[4] = clerk; tick(f, 0.0)
	expect(f.scene.playing, "the scene begins when the complete named cast is ready")
	dispose(f)
	await process_frame; await process_frame
	print("ferry camera: ", checks, " checks; ", failures, " failures")
	quit(1 if failures else 0)
