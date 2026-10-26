extends SceneTree

const Scene := preload("res://src/world/campaign_scene.gd")
const Hud := preload("res://src/ui/campaign_hud.gd")
const CameraFixture := preload("res://tests/test_campaign_ferry_camera.gd")
var failures := 0
var checks := 0

class Rig extends Node3D:
	var camera: Camera3D
	var focus := Vector3(9.5, 2.5, 125.5)
	var distance := 17.0
	var pitch_degrees := -47.0
	var yaw_degrees := 12.0
	var rotation_cancelled := false
	func cancel_rotation() -> void:
		rotation_cancelled = true

class Actor extends Node3D:
	var post := Transform3D.IDENTITY
	var action := &"idle"
	var restored := false
	func set_cinematic_presentation(point: Vector3, yaw: float, value: StringName, _speed: float) -> void:
		global_position = point
		rotation.y = yaw
		action = value
	func end_cinematic_presentation() -> void:
		global_transform = post
		action = &"idle"
		restored = true

func _init() -> void:
	call_deferred("run")

func expect(ok: bool, message: String) -> void:
	checks += 1
	if not ok:
		failures += 1
		push_error(message)
	else:
		print("PASS: ", message)

func snapshot(token := "arrival-1", scene_id := "measure.landing.arrival") -> Dictionary:
	return {"version": 1, "active": true, "run_id": "run-test", "map": "maps/nymara/greenlight.elm",
		"title": "The Ferry That Arrived Twice", "stage": "rescue", "key": "assess",
		"actors": {"odo": 2, "worker": 3}, "targets": [
			{"id": "assess", "object_id": 61001, "label": "Inspect the landing", "tile": [435, 320], "enabled": true, "completed": false}],
		"anchors": CameraFixture.PIER_ANCHORS.duplicate(true),
		"scene": {"id": scene_id, "token": token, "variant": "medical"}}

func run() -> void:
	var definitions := Scene.scene_definitions()
	expect(definitions.size() >= 3, "authored arrival, consequence and demonstration scenes load")
	for id: String in definitions:
		var authored: Dictionary = definitions[id]
		expect(float(authored.duration) > 0.0 and float(authored.duration) <= 60.0, id + " is a bounded scene")
		expect((authored.shots as Array).size() >= 2 and not (authored.lines as Array).is_empty(), id + " has camera staging and a transcript")
	var good := snapshot()
	var decoded := EloriaProtocol.decode_server(191, JSON.stringify(good).to_utf8_buffer())
	expect(decoded.get("type") == "campaign" and decoded.state.run_id == "run-test", "packet 191 decodes the negotiated campaign snapshot")
	var runtime_shape := good.duplicate(true)
	runtime_shape.stage = 1
	runtime_shape.targets[0].approach = [436, 320]
	expect(EloriaProtocol.decode_campaign(JSON.stringify(runtime_shape).to_utf8_buffer()).get("type") == "campaign", "the server's numeric stage and physical approach tiles decode")
	var app_state := root.get_node("AppState")
	app_state.call("_on_packet", 191, JSON.stringify(runtime_shape).to_utf8_buffer())
	expect(app_state.get("campaign").get("run_id") == "run-test", "the real packet reducer publishes campaign state to the HUD integration")
	expect("campaign_v1" in EloriaProtocol.CLIENT_CAPABILITIES, "the decoding client advertises campaign_v1")
	for malformed: Dictionary in [
		{"version": 1, "active": "yes"},
		{"version": 1, "active": true, "run_id": "", "map": "greenlight"},
		{"version": 1, "active": true, "run_id": "r", "map": "greenlight", "targets": [{"id": "x", "label": "X", "object_id": 61000, "tile": [1.5, 2]}]},
		{"version": 1, "active": true, "run_id": "r", "map": "greenlight", "scene": {"id": "x"}},
		{"version": 1, "active": true, "run_id": "r", "map": "greenlight", "actors": {"odo": "2"}}]:
		expect(EloriaProtocol.decode_campaign(JSON.stringify(malformed).to_utf8_buffer()).get("type") == "invalid", "malformed campaign identity/action data is rejected")
	expect(EloriaProtocol.decode_campaign(JSON.stringify({"version": 1, "active": false, "available": true}).to_utf8_buffer()).get("type") == "campaign", "the inactive local entry offer is supported")
	var rig := Rig.new()
	root.add_child(rig)
	var camera := Camera3D.new()
	rig.add_child(camera)
	rig.camera = camera
	camera.position = Vector3(4, 14, 12)
	camera.fov = 61.0
	camera.near = 0.8
	var original_camera := camera.global_transform
	var local := Actor.new()
	var odo := Actor.new()
	var worker := Actor.new()
	for actor: Actor in [local, odo, worker]:
		root.add_child(actor)
	local.position = Vector3(9.5, 2.5, 125.5)
	odo.position = Vector3(7.5, 2.5, 128.5)
	worker.position = Vector3(-9.5, 2.5, 131.5)
	odo.post = odo.global_transform
	worker.post = worker.global_transform
	var actors := {1: local, 2: odo, 3: worker}
	var scene := Scene.new()
	root.add_child(scene)
	scene.set_reduced_motion(false, false)
	var finished: Array = []
	scene.presentation_finished.connect(func(token: String, reason: String) -> void: finished.append([token, reason]))
	scene.update(0.0, good, rig, actors, 1, "greenlight", true)
	expect(scene.playing and scene.blocks_input() and rig.rotation_cancelled, "only a ready scene acquires presentation and control")
	expect(camera.global_transform.is_equal_approx(original_camera), "the opening starts from the player's live 3D camera")
	scene.update(4.0, good, rig, actors, 1, "greenlight", true)
	expect(odo.global_position.is_equal_approx(odo.post.origin) and not camera.global_transform.is_equal_approx(original_camera), "the camera approaches Odo while he waits for the crew")
	scene.update(2.0, good, rig, actors, 1, "greenlight", true)
	expect(odo.action == &"emote_greet" and scene._dialogue.speaker_label.text == "Odo Fenn", "NPC gesture and attributed subtitle accompany the scene")
	expect(scene.transcript_text().contains("jammed support at the pier mouth") and scene.transcript_text().contains("You examine the lodged driftwood and the loose pier support"), "the arrival account describes the visible pier inspection before choosing a rescue plan")
	scene.skip()
	expect(scene.blocks_input() and scene._returning, "skip begins the opening's short camera return")
	scene.update(0.7, good, rig, actors, 1, "greenlight", true)
	expect(not scene.blocks_input() and not scene.playing, "skip releases gameplay control after the camera returns")
	expect(camera.global_transform.is_equal_approx(original_camera) and is_equal_approx(camera.fov, 61.0) and is_equal_approx(camera.near, 0.8), "skip restores camera pose and lens exactly")
	expect(odo.restored and worker.restored and odo.global_transform.is_equal_approx(odo.post), "skip relinquishes actor presentation to server targets")
	expect(finished == [["arrival-1", "skipped"]], "completion is an informational presentation result, emitted once")
	scene.update(1.0, good, rig, actors, 1, "greenlight", true)
	expect(not scene.is_active(), "snapshot resends cannot restart the same run/token")
	scene.cancel("disconnected")
	scene.update(1.0, good, rig, actors, 1, "greenlight", true)
	expect(not scene.is_active(), "reconnect with the same scene token preserves the already-seen presentation")
	var reduced := snapshot("reduced-1")
	scene.set_reduced_motion(true, false)
	scene.update(0.0, reduced, rig, actors, 1, "greenlight", true)
	var static_camera := camera.global_transform
	scene.update(6.0, reduced, rig, actors, 1, "greenlight", true)
	expect(camera.global_transform.is_equal_approx(static_camera), "reduced motion holds one stable camera framing")
	scene.update(0.1, reduced, rig, actors, 1, "landfall", true)
	expect(not scene.blocks_input() and camera.global_transform.is_equal_approx(original_camera), "map change restores the camera and releases input")
	scene.update(0.0, snapshot("lost-actor"), rig, actors, 1, "greenlight", true)
	worker.free()
	scene.update(0.1, snapshot("lost-actor"), rig, {1: local, 2: odo}, 1, "greenlight", true)
	expect(not scene.blocks_input(), "a missing bound actor cannot strand a scene")
	scene.update(0.0, snapshot("wait-timeout"), rig, {}, 1, "greenlight", false)
	expect(scene.pending and not scene.blocks_input(), "loading waits without acquiring a gameplay lock")
	scene.update(46.0, snapshot("wait-timeout"), rig, {}, 1, "greenlight", false)
	expect(not scene.is_active(), "missing scenery/player readiness has a bounded timeout")
	scene.update(0.0, snapshot("unknown", "unrecognized.future.scene"), rig, actors, 1, "greenlight", true)
	expect(not scene.is_active(), "unknown authored scene IDs leave the quest playable")
	var consequence := snapshot("consequence", "measure.landing.resolved")
	consequence.actors = {"odo": 2}
	scene.update(0.0, consequence, rig, {1: local, 2: odo}, 1, "greenlight", true)
	expect(scene.transcript_text().contains("medical chest comes first"), "the account reflects the authoritative cargo-priority variant")
	scene.update(12.0, consequence, rig, {1: local, 2: odo}, 1, "greenlight", true)
	expect(not scene.blocks_input() and camera.global_transform.is_equal_approx(original_camera), "normal completion restores the same controls and camera as skip")
	var hud := Hud.new()
	root.add_child(hud)
	var requests: Array = []
	hud.target_requested.connect(func(id: int, tile: Vector2i, near: bool) -> void: requests.append([id, tile, near]))
	hud.apply_state(good, Vector2i(436, 320), "greenlight")
	hud._request_target("assess", 61001)
	expect(requests == [[61001, Vector2i(435, 320), true]], "a nearby HUD target requests ordinary authoritative use")
	hud.apply_state(good, Vector2i(444, 322), "greenlight")
	hud._request_target("assess", 61001)
	expect(requests.back()[2] == false, "a distant target requests walking rather than remote objective completion")
	hud.apply_state(runtime_shape, Vector2i(444, 322), "greenlight")
	hud._request_target("assess", 61001)
	expect(requests.back()[1] == Vector2i(436, 320), "walking uses the authored approach rather than the occupied object tile")
	var completed := good.duplicate(true)
	completed.targets[0].completed = true
	hud.apply_state(completed, Vector2i(436, 320), "greenlight")
	hud._request_target("assess", 61001)
	expect(requests.size() == 3, "completed targets cannot be activated through the checklist")
	hud.apply_state(good, Vector2i(436, 320), "landfall")
	expect(not hud.visible, "target controls do not survive into another map")
	await process_frame
	hud.queue_free()
	scene.queue_free()
	odo.queue_free()
	local.queue_free()
	rig.queue_free()
	await process_frame
	print("campaign scene: ", checks, " checks; ", failures, " failures")
	quit(1 if failures else 0)
