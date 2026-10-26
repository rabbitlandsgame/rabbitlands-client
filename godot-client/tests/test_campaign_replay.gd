extends SceneTree
## Local viewing must never satisfy or repeat a server scene barrier.
const Presentation := preload("res://src/world/campaign_scene.gd")
var checks := 0
var failures := 0

class Rig extends Node3D:
	var camera: Camera3D
	var focus := Vector3(15, 2.5, 140)
	var distance := 17.0
	var pitch_degrees := -47.0
	var yaw_degrees := 12.0
	func cancel_rotation() -> void:
		pass

class MovingActor extends Node3D:
	var server_target := Transform3D.IDENTITY
	var presentation := false
	func set_cinematic_presentation(point: Vector3, yaw: float, _action: StringName, _speed: float) -> void:
		presentation = true
		global_position = point
		rotation.y = yaw
	func end_cinematic_presentation() -> void:
		presentation = false
		global_transform = server_target

func _init() -> void:
	run.call_deferred()

func expect(ok: bool, message: String) -> void:
	checks += 1
	if not ok:
		failures += 1
		push_error(message)
	else:
		print("PASS: ", message)

func run() -> void:
	create_timer(90).timeout.connect(func() -> void: push_error("Campaign replay probe timed out"); quit(1))
	root.get_node("Network").call("block_for_hud_preview")
	var state := {"version": 1, "active": true, "run_id": "run-test", "map": "maps/nymara/greenlight.elm",
		"title": "The Ferry That Arrived Twice", "stage": "rescue", "key": "assess",
		"actors": {"odo": 2, "worker": 3}, "targets": [
			{"id": "assess", "object_id": 61001, "label": "Inspect the landing", "tile": [450, 310], "enabled": true, "completed": false}],
		"scene": {"id": "measure.landing.arrival", "token": "arrival-1", "variant": "medical"}}
	state.scene.requires_ack = true
	state.scene.ack_revision = 1
	var original_state := JSON.stringify(state)
	var rig := Rig.new()
	root.add_child(rig)
	var camera := Camera3D.new()
	rig.add_child(camera)
	rig.camera = camera
	camera.position = Vector3(4, 14, 12)
	camera.fov = 61.0
	camera.near = 0.8
	var camera_post := camera.global_transform
	var actors := {}
	for id: int in [1, 2, 3]:
		var actor := MovingActor.new()
		root.add_child(actor)
		actor.position = Vector3(10 + id * 2, 2.5, 140 - id * 3)
		actor.server_target = actor.global_transform
		actors[id] = actor
	var scene := Presentation.new()
	root.add_child(scene)
	scene.set_reduced_motion(false, false)
	var ordinary: Array = []
	var replay: Array = []
	scene.presentation_finished.connect(func(token: String, reason: String) -> void: ordinary.append([token, reason]))
	scene.replay_finished.connect(func(token: String, reason: String) -> void: replay.append([token, reason]))
	expect(not scene.can_replay(state, "greenlight"), "an unseen scene cannot be replayed to bypass its normal viewing")
	scene.update(0.0, state, rig, actors, 1, "greenlight")
	expect(not scene.request_replay(state, "greenlight"), "a running scene rejects overlapping replay")
	scene.skip()
	expect(ordinary == [["arrival-1", "skipped"]], "the original skip produces exactly one normal presentation result")
	expect(scene.can_replay(state, "maps/nymara/greenlight.elm"), "a handled current scene offers replay with normalized map identity")
	expect(scene.request_replay(state, "greenlight"), "explicit replay is accepted after viewing")
	expect(not scene.request_replay(state, "greenlight"), "a queued replay cannot be queued twice")
	scene.update(0.0, state, rig, actors, 1, "greenlight")
	expect(scene.playing and scene.elapsed == 0.0, "replay restarts camera and actor staging from the beginning")
	scene.update(4.0, state, rig, actors, 1, "greenlight")
	expect((actors[2] as MovingActor).presentation, "replay animates the bound NPC in the live world")
	var latest_target := Transform3D(Basis.IDENTITY, Vector3(40, 3, 110))
	(actors[2] as MovingActor).server_target = latest_target
	scene.show_transcript()
	var paused_at := scene.elapsed
	scene.update(1.0, state, rig, actors, 1, "greenlight")
	expect(scene.elapsed == paused_at, "the scene account pauses replay for review")
	scene.skip()
	expect(not scene.is_active() and not scene._transcript.visible, "skipping replay closes its account and releases controls")
	expect((actors[2] as MovingActor).global_transform.is_equal_approx(latest_target), "replay relinquishes the actor to its latest server target")
	expect(camera.global_transform.is_equal_approx(camera_post) and is_equal_approx(camera.fov, 61.0) and is_equal_approx(camera.near, 0.8), "replay restores camera pose and lens")
	expect(ordinary.size() == 1 and replay == [["arrival-1", "skipped"]], "replay uses a separate local completion signal")
	scene.update(0.1, state, rig, actors, 1, "greenlight")
	expect(ordinary.size() == 1 and not scene.is_active(), "the next snapshot neither acknowledges nor automatically repeats a replay")
	scene.set_reduced_motion(true, false)
	expect(scene.request_replay(state, "greenlight"), "the same current cinematic can be reviewed repeatedly")
	scene.update(0.0, state, rig, actors, 1, "greenlight")
	var static_camera := camera.global_transform
	scene.update(5.0, state, rig, actors, 1, "greenlight")
	expect(camera.global_transform.is_equal_approx(static_camera), "replay respects reduced camera motion")
	scene.update(60.0, state, rig, actors, 1, "greenlight")
	expect(replay.back() == ["arrival-1", "finished"] and ordinary.size() == 1, "normal replay completion never emits a server presentation result")
	expect(JSON.stringify(state) == original_state, "replay leaves authoritative campaign objectives and rewards untouched")
	var stale := state.duplicate(true)
	stale.scene.token = "unseen-token"
	expect(not scene.request_replay(stale, "greenlight"), "a different scene token requires its original viewing")
	stale = state.duplicate(true)
	stale.run_id = "new-party-run"
	expect(not scene.request_replay(stale, "greenlight"), "replay cannot carry into another party run")
	expect(not scene.request_replay(state, "twinbrook"), "replay is unavailable after leaving the scene map")
	stale = state.duplicate(true)
	stale.active = false
	expect(not scene.request_replay(stale, "greenlight"), "an inactive campaign cannot replay")
	stale = state.duplicate(true)
	stale.scene.id = "unknown.future.scene"
	expect(not scene.request_replay(stale, "greenlight"), "an unknown scene definition cannot replay")
	stale = state.duplicate(true)
	stale.scene.ack_revision = 2
	expect(not scene.request_replay(stale, "greenlight"), "a new authoritative acknowledgement takes precedence over replay")
	scene.update(0.0, stale, rig, actors, 1, "greenlight")
	expect(ordinary.back() == ["arrival-1", "already_seen"] and ordinary.size() == 2, "a fresh rejoin barrier still receives its ordinary deduplicated acknowledgement")
	scene.update(0.0, stale, rig, actors, 1, "greenlight")
	expect(ordinary.size() == 2, "a repeated barrier snapshot does not duplicate its acknowledgement")
	state = stale
	expect(scene.request_replay(state, "greenlight"), "a current scene can queue replay before an authoritative scene clear")
	var cleared := state.duplicate(true)
	cleared.scene = {}
	scene.update(0.0, cleared, rig, actors, 1, "greenlight")
	expect(scene._replay_requested_identity.is_empty() and not scene.is_active(), "a cleared server scene discards queued replay immediately")
	scene.update(0.0, state, rig, actors, 1, "greenlight")
	expect(not scene.is_active(), "restoring a handled snapshot cannot resurrect a discarded replay request")
	expect(scene.request_replay(state, "greenlight"), "replay is available again after the rejoin acknowledgement")
	scene.update(0.0, state, rig, actors, 1, "greenlight")
	var replacement := MovingActor.new()
	root.add_child(replacement)
	replacement.server_target = replacement.global_transform
	var original_actor: MovingActor = actors[2]
	actors[2] = replacement
	scene.update(0.1, state, rig, actors, 1, "greenlight")
	expect(not scene.is_active() and replay.back()[1] == "actor_lost" and not original_actor.presentation, "replacing an actor ID cancels replay even while its previous node remains alive")
	expect(ordinary.size() == 2, "cast replacement during replay does not satisfy a scene barrier")
	actors[2] = original_actor
	replacement.free()
	expect(scene.request_replay(state, "greenlight"), "a restored cast can replay again")
	scene.update(0.0, state, rig, actors, 1, "greenlight")
	var recast := state.duplicate(true)
	recast.actors = {"odo": 3, "worker": 2}
	scene.update(0.1, recast, rig, actors, 1, "greenlight")
	expect(not scene.is_active() and replay.back()[1] == "actor_lost", "a changed role binding cancels replay safely")
	expect(scene.request_replay(state, "greenlight"), "a replay may wait briefly for its current cast")
	scene.update(0.0, state, rig, {1: actors[1]}, 1, "greenlight")
	expect(scene.pending and not scene.blocks_input(), "missing replay actors do not lock gameplay while loading")
	scene.update(2.1, state, rig, {1: actors[1]}, 1, "greenlight")
	expect(not scene.is_active() and ordinary.size() == 2, "a missing replay cast cancels without acknowledgement")
	expect(scene.request_replay(state, "greenlight"), "a current replay request can be queued before a map transition")
	scene.update(0.0, state, rig, actors, 1, "twinbrook")
	expect(not scene.is_active() and scene._replay_requested_identity.is_empty(), "a map transition clears queued replay")
	# Return/reconnect acknowledgement belongs to the original server flow.
	scene.update(0.0, state, rig, actors, 1, "greenlight")
	var ordinary_count := ordinary.size()
	expect(scene.request_replay(state, "greenlight"), "replay can resume after returning and acknowledging")
	scene.update(0.0, state, rig, actors, 1, "greenlight", false)
	scene.update(46.0, state, rig, actors, 1, "greenlight", false)
	expect(not scene.is_active() and ordinary.size() == ordinary_count, "world-loading timeout restores replay without a normal completion")
	expect(scene.request_replay(state, "greenlight"), "replay is available before lifecycle cancellation")
	scene.update(0.0, state, rig, actors, 1, "greenlight")
	scene.cancel("unavailable")
	expect(not scene.blocks_input() and camera.global_transform.is_equal_approx(camera_post) and ordinary.size() == ordinary_count, "death or disconnect cancellation restores replay without sending a completion")
	scene.reset_session()
	expect(not scene.can_replay(state, "greenlight"), "session reset clears prior viewing authorization")
	scene.free()
	await check_main_flow(state, actors)
	for actor: MovingActor in actors.values():
		actor.free()
	rig.free()
	await process_frame
	print("campaign replay: ", checks, " checks; ", failures, " failures")
	quit(1 if failures else 0)

func check_main_flow(state: Dictionary, actors: Dictionary) -> void:
	var network := root.get_node("Network")
	var recorder := GDScript.new()
	recorder.source_code = 'extends "res://src/network/network_client.gd"\nvar sent_frames: Array = []\nfunc send_frame(frame: PackedByteArray, _sensitive := false) -> Error:\n\tsent_frames.append(frame)\n\treturn OK\n'
	expect(recorder.reload() == OK, "the Main replay test records native packets without a socket")
	network.set_script(recorder)
	network.call("block_for_hud_preview")
	var main := (load("res://src/app/main.tscn") as PackedScene).instantiate()
	root.add_child(main)
	main.set_process(false)
	main.hide()
	var app := root.get_node("AppState")
	app.authenticated = true
	app.death = {}
	app.local_actor_id = 1
	app.current_map = "greenlight"
	app.campaign = state.duplicate(true)
	main.set("actor_nodes", actors)
	(main.get("_grounded_actors") as Dictionary)[1] = true
	var production_scene: Node = main.get("campaign_scene")
	var production_rig: Node3D = main.get("camera_rig")
	var production_hud: Control = main.get("campaign_hud")
	var windows: Control = main.get("extension_windows")
	(main.get("arrival_curtain") as CanvasLayer).hide()
	production_scene.call("update", 0.0, app.campaign, production_rig, actors, 1, "greenlight")
	production_scene.call("skip")
	var frames: Array = network.get("sent_frames")
	expect(frames.size() == 1, "production Main acknowledges the original presentation once")
	main.call("_update_campaign", 0.0)
	expect(bool(production_hud.get("_replay_available")) and not windows.get("quest_replay_button").disabled, "production Main enables both replay controls only for a ready viewed scene")
	production_hud.replay_requested.emit()
	main.call("_update_campaign", 0.0)
	expect(bool(production_scene.get("playing")), "the production replay signal starts the local cinematic")
	production_scene.call("skip")
	main.call("_update_campaign", 0.0)
	expect(frames.size() == 1, "production Main never sends scene_done for local replay or its next update")
	# Model the server's eventual ordinary acknowledgement echo.
	app.campaign.scene.requires_ack = false
	for blocker: String in ["ungrounded", "intro", "curtain", "dead", "disconnect", "signed_out"]:
		match blocker:
			"ungrounded": (main.get("_grounded_actors") as Dictionary).clear()
			"intro": main.get("character_intro").set("pending", true)
			"curtain": (main.get("arrival_curtain") as CanvasLayer).show()
			"dead": app.death = {"dead": true}
			"disconnect": main.set("_disconnect_console_active", true)
			"signed_out": app.authenticated = false
		main.call("_update_campaign", 0.0)
		expect(not bool(production_hud.get("_replay_available")) and windows.get("quest_replay_button").disabled, blocker + " disables replay in the field and journal through production Main")
		# A previously enabled GUI signal must still be checked at dispatch time.
		production_hud.replay_requested.emit()
		expect(str(production_scene.get("_replay_requested_identity")).is_empty() and frames.size() == 1, blocker + " rejects a stale replay click without network traffic")
		(main.get("_grounded_actors") as Dictionary)[1] = true
		main.get("character_intro").set("pending", false)
		(main.get("arrival_curtain") as CanvasLayer).hide()
		app.death = {}
		main.set("_disconnect_console_active", false)
		app.authenticated = true
		main.call("_update_campaign", 0.0)
	main.set("actor_nodes", {})
	app.authenticated = false
	main.queue_free()
	await process_frame
	await process_frame
