extends SceneTree
## Actual orbit rig + shared scene controller; no map, network, or rendered proof.
const Scene := preload("res://src/world/campaign_scene.gd")
const Crowd := preload("res://src/world/crowd_presentation.gd")
var checks := 0
var failures := 0

class Actor extends Node3D:
	var actor_id := -1
	var _last_command_sequence := -1
	var server_target := Transform3D.IDENTITY
	var sampled := -1.0
	var last_action := &"idle"
	func set_cinematic_presentation(point: Vector3, yaw: float, action: StringName, _speed: float) -> void:
		global_position = point
		rotation.y = yaw
		last_action = action
	func set_cinematic_action_elapsed(value: float) -> void: sampled = value
	func end_cinematic_presentation() -> void: global_transform = server_target

func _init() -> void: run.call_deferred()
func expect(value: bool, detail: String) -> void:
	checks += 1
	if value: print("PASS: ", detail)
	else:
		failures += 1
		push_error(detail)

func make_rig() -> IsometricCameraController:
	var rig := IsometricCameraController.new()
	var camera := Camera3D.new()
	camera.name = "Camera"
	camera.fov = 63
	rig.add_child(camera)
	camera.owner = rig
	camera.unique_name_in_owner = true
	root.add_child(rig)
	return rig

func view(position: Vector3, target: Vector3) -> Dictionary:
	return {"transform":Transform3D(Basis.IDENTITY,position).looking_at(target,Vector3.UP),
		"target":target,"fov":51.0,"near":0.5,"far":1900.0}

func fixture(branch := "help", replay := false) -> Dictionary:
	var rig := make_rig()
	var actor := Actor.new()
	root.add_child(actor)
	actor.server_target = actor.global_transform
	rig.set_focus(actor.global_position)
	var scene := Scene.new()
	root.add_child(scene)
	scene.reduced_motion = false
	scene._definition = {"duration":68,"entry_seconds":2,"exit_seconds":2,
		"stage_protagonist":true,"exit_camera":{"mode":"keep_scene","when":"help"},
		"shots":[
			{"t":0,"anchor":"start","position":[-4,6,9],"target":[0,1,0]},
			{"t":42,"anchor":"start","position":[-4,6,9],"target":[0,1,0]},
			{"t":58,"anchor":"combat","position":[6,6,10],"target":[1,-0.8,0]},
			{"t":68,"anchor":"combat","position":[6,6,10],"target":[1,-0.8,0]}],
		"cues":[{"at":0,"actor":"protagonist","destination":"start","face":"post"},
			{"at":58,"actor":"protagonist","destination":"player_end","face":"post"}]}
	scene._choice_state = {"selected":branch}
	scene._anchors = {"start":Vector3.ZERO,"combat":Vector3(10,0,0),"player_end":Vector3(11,0,0)}
	scene._replaying = replay
	scene._token = "camera-test"
	scene._run = "handoff-run"
	scene._map = "landfall"
	scene._start(rig,rig.camera,actor,{1:actor},{"protagonist":1})
	return {"rig":rig,"actor":actor,"scene":scene,"original":scene._saved.camera,
		"initial_focus":scene._saved.focus,"definition":scene._definition.duplicate(true)}

func pose_at(f: Dictionary, time: float) -> void:
	f.scene.elapsed = time
	f.scene._camera_entry_elapsed = time
	f.scene._apply_actors()
	f.scene._apply_camera()

func dispose(f: Dictionary) -> void:
	f.scene.cancel("test_done")
	f.scene.queue_free()
	f.actor.queue_free()
	f.rig.queue_free()
	for actor: Node3D in f.get("departed", {}).values():
		if is_instance_valid(actor): actor.queue_free()

func run() -> void:
	create_timer(60).timeout.connect(func() -> void: push_error("camera adoption test timeout"); quit(1))
	root.get_node("Network").call("block_for_hud_preview")
	check_rig()
	check_live_finish()
	check_early_skip()
	check_other_exits()
	check_cue_sampling()
	check_departed_visibility()
	await process_frame
	print("Campaign camera adoption checks: ",checks,"; failures: ",failures)
	quit(1 if failures else 0)

func check_rig() -> void:
	var rig := make_rig()
	var actor := Vector3(3,0,4)
	rig.set_focus(actor)
	expect(rig.focus == actor and rig.follow_offset == Vector3.ZERO,"ordinary focus retains its original zero-offset behavior")
	var authored := view(Vector3(9,8,15),Vector3(5,1.1,4))
	expect(rig.adopt_world_view(authored,actor),"a supported authored view can become a real orbit camera")
	expect(rig.camera.global_transform.is_equal_approx(authored.transform),"adoption reconstructs the exact authored camera position and orientation")
	expect(rig.camera.fov == 51 and rig.camera.far == 1900,"adoption keeps the authored lens")
	var focus := rig.focus
	var adopted := rig.camera.global_transform
	rig.set_focus(actor)
	expect(rig.camera.global_transform.is_equal_approx(adopted),"the next ordinary player-follow update does not snap the adopted view")
	var movement := Vector3(2,0.4,-1)
	rig.set_focus(actor+movement)
	expect(rig.focus.is_equal_approx(focus+movement) and rig.camera.global_position.is_equal_approx(adopted.origin+movement),"normal walking translates the adopted frame without changing its orbit")
	var yaw := rig.yaw_degrees
	rig.handle_keyboard(Vector2(1,0),0.1)
	expect(is_equal_approx(rig.yaw_degrees,yaw-9) and rig.focus.is_equal_approx(focus+movement),"keyboard orbit remains live around the adopted pivot")
	var wheel := InputEventMouseButton.new()
	wheel.button_index = MOUSE_BUTTON_WHEEL_UP
	wheel.pressed = true
	var distance := rig.distance
	expect(rig.handle_mouse_button(wheel) and is_equal_approx(rig.distance,distance-rig.zoom_step),"normal wheel zoom immediately operates on the adopted distance")
	var middle := InputEventMouseButton.new()
	middle.button_index = MOUSE_BUTTON_MIDDLE
	middle.pressed = true
	rig.handle_mouse_button(middle)
	var motion := InputEventMouseMotion.new()
	motion.relative = Vector2(4,2)
	yaw = rig.yaw_degrees
	expect(rig.handle_mouse_motion(motion) and is_equal_approx(rig.yaw_degrees,yaw-1),"mouse orbit remains live after adoption")
	var frame := Transform3D(Basis(Vector3.UP,PI/2),Vector3(100,0,-30))
	var old_camera := rig.camera.global_transform
	var old_offset := rig.follow_offset
	rig.rebase_world(frame)
	expect(rig.follow_offset.is_equal_approx(frame.basis*old_offset) and rig.camera.global_transform.is_equal_approx(frame*old_camera),"world rebasing rotates the adopted offset and complete camera together")
	rig.reset_follow_offset()
	expect(rig.follow_offset == Vector3.ZERO and rig.focus.is_equal_approx(frame*(actor+movement)),"explicit reset returns focus to the followed actor")
	var before := rig.camera.global_transform
	expect(not rig.adopt_world_view({"target":Vector3.INF},actor) and rig.camera.global_transform.is_equal_approx(before),"invalid authored views cannot partially mutate the rig")
	rig.queue_free()

func check_live_finish() -> void:
	var f := fixture()
	var results: Array = []
	f.scene.presentation_finished.connect(func(token: String,reason: String) -> void: results.append([token,reason]))
	pose_at(f,68)
	var last: Transform3D = f.rig.camera.global_transform
	expect(not last.is_equal_approx(f.original),"live Help keeps its last confrontation shot instead of easing back to the old player camera")
	f.scene.cancel("finished")
	expect(not f.scene.blocks_input() and f.rig.camera.global_transform.is_equal_approx(last),"normal completion hands the exact final frame to ordinary gameplay")
	expect(results == [["camera-test","finished"]] and f.scene._ack_requested,"completion acknowledges once after releasing control")
	expect(f.actor.global_position == Vector3.ZERO,"camera adoption cannot move the native player to its visual endpoint")
	var offset: Vector3 = f.rig.follow_offset
	f.rig.set_focus(Vector3(4,0,0))
	expect(f.rig.camera.global_transform.is_equal_approx(last),"the real approaching player cannot pull the combat frame back toward the old post")
	f.rig.set_focus(Vector3(11,0,0))
	expect(f.rig.camera.global_transform.is_equal_approx(last),"native arrival joins the adopted follow camera with no final snap")
	f.rig.set_focus(Vector3(12,0,0))
	expect(f.rig.focus.is_equal_approx(Vector3(12,0,0)+offset),"later gameplay movement follows normally from the combat post")
	# A later unrelated film must restore this same adopted view and follow state.
	f.actor.server_target.origin = Vector3(12,0,0)
	f.actor.global_transform = f.actor.server_target
	var saved: Transform3D = f.rig.camera.global_transform
	f.scene.elapsed = 0
	f.scene._definition.erase("exit_camera")
	f.scene._start(f.rig,f.rig.camera,f.actor,{1:f.actor},{"protagonist":1})
	pose_at(f,20)
	f.scene.cancel("actor_lost")
	expect(f.rig.follow_offset.is_equal_approx(offset) and f.rig.camera.global_transform.is_equal_approx(saved),"an interrupted later film restores the previously adopted follow state")
	f.rig.set_focus(f.actor.global_position)
	expect(f.rig.camera.global_transform.is_equal_approx(saved),"the next player-follow update after a later film preserves its restored framing")
	f.scene.reset_session()
	expect(f.rig.follow_offset == Vector3.ZERO,"session reset removes the combat framing from the next character")
	dispose(f)

func check_early_skip() -> void:
	var f := fixture()
	pose_at(f,42)
	var question: Transform3D = f.rig.camera.global_transform
	var events: Array = []
	f.scene.event_requested.connect(func(id: String) -> void: events.append(id))
	f.scene._definition.events = [{"at":64,"id":"not-gameplay-proof","request":true}]
	f.scene.skip()
	var expected := view(Vector3(16,6,10),Vector3(11,-0.8,0))
	expect(not f.scene.is_active() and f.rig.camera.global_transform.is_equal_approx(expected.transform),"Help Skip from the question adopts the final intended confrontation camera")
	expect(not f.rig.camera.global_transform.is_equal_approx(question),"early Skip never retains the choice-facing shot")
	expect(events.is_empty() and f.actor.global_position == Vector3.ZERO,"sampling the final visual frame does not execute future events or native movement")
	var held: Transform3D = f.rig.camera.global_transform
	f.rig._follow_arrival_until = 0
	f.rig.set_focus(Vector3(2,0,0))
	expect(f.rig.camera.global_transform.is_equal_approx(held),"a stalled native approach has a bounded no-snap fallback")
	f.rig.set_focus(Vector3(3,0,0))
	expect(f.rig.camera.global_position.is_equal_approx(held.origin+Vector3.RIGHT),"normal following resumes after the bounded fallback")
	dispose(f)

func check_other_exits() -> void:
	for branch: String in ["watch","help"]:
		for reason: String in ["map_changed","actor_lost","cancelled"]:
			var f := fixture(branch)
			pose_at(f,60)
			f.scene.cancel(reason)
			expect(f.rig.follow_offset == Vector3.ZERO and f.rig.camera.global_transform.is_equal_approx(f.original),branch+" interruption "+reason+" retains the ordinary restoration contract")
			dispose(f)
	var f := fixture("watch")
	pose_at(f,68)
	expect(f.rig.camera.global_transform.is_equal_approx(f.original),"Watch still eases back to the ordinary camera at the film end")
	f.scene.cancel("finished")
	expect(f.rig.follow_offset == Vector3.ZERO,"Watch completion never adopts Help framing")
	dispose(f)
	f = fixture("help",true)
	pose_at(f,68)
	f.scene.cancel("finished")
	expect(f.rig.follow_offset == Vector3.ZERO and f.rig.camera.global_transform.is_equal_approx(f.original) and not f.scene._ack_requested,"read-only Help replay restores its saved viewport and requests no normal ACK")
	dispose(f)
	f = fixture()
	f.scene.reduced_motion = true
	pose_at(f,42)
	f.scene.skip()
	var expected := view(Vector3(16,6,10),Vector3(11,-0.8,0))
	expect(f.rig.camera.global_transform.is_equal_approx(expected.transform),"reduced-motion Help Skip cuts directly to the final static combat view without flying back")
	var yaw: float = f.rig.yaw_degrees
	f.rig.handle_keyboard(Vector2.RIGHT,0.1)
	expect(is_equal_approx(f.rig.yaw_degrees,yaw-9),"the reduced-motion adopted view immediately accepts normal camera controls")
	dispose(f)
	f = fixture()
	f.scene.reduced_motion = true
	pose_at(f,68)
	f.scene.cancel("finished")
	expect(f.rig.camera.global_transform.is_equal_approx(expected.transform),"normal reduced-motion Help completion adopts the same final confrontation view")
	dispose(f)

func check_cue_sampling() -> void:
	var f := fixture()
	f.scene._definition.cues = [{"at":2,"actor":"protagonist","from":"start",
		"destination":"combat","destination_offset":[-0.4,0,0.3],"move_seconds":4,"action":"tackle_fall","face":"post"}]
	pose_at(f,4)
	expect(f.actor.global_position.is_equal_approx(Vector3(4.8,0,0.15)),"destination_offset participates in actual cue interpolation")
	expect(f.actor.sampled == 2 and f.actor.last_action == &"tackle_fall","the actor samples the exact current cue time after its pose is applied")
	f.scene._apply_actors()
	expect(f.actor.sampled == 2,"a manual dialogue hold samples the same pose without advancing its clip")
	f.scene.elapsed = 2
	f.scene._apply_actors()
	expect(f.actor.sampled == 0 and f.actor.global_position == Vector3.ZERO,"seeking back to a cue start resets its visual sample deterministically")
	f.scene._definition.cues[0].erase("destination_offset")
	f.scene.elapsed = 4
	f.scene._apply_actors()
	expect(f.actor.global_position == Vector3(5,0,0),"omitting destination_offset preserves the existing cue coordinates")
	dispose(f)

func add_departed(f: Dictionary) -> Dictionary:
	var nodes := {1:f.actor}
	var departed := {}
	for role: String in ["daughter","abductor","escort"]:
		var actor := Actor.new()
		root.add_child(actor)
		actor.actor_id = nodes.size()+1
		actor.position = Vector3(actor.actor_id,0,-2)
		actor.server_target = actor.global_transform
		actor.set_meta(&"identity_key",role)
		departed[role] = actor
		nodes[actor.actor_id] = actor
		f.scene._actors[role] = actor
		f.scene._posts[role] = actor.global_transform
		f.scene._visibility_posts[role] = true
		f.scene._definition.cues.append({"at":26,"actor":role,"visible":false,"face":"post"})
	f.scene._definition.hide_on_handoff = ["daughter","abductor","escort"]
	f.departed = departed
	return nodes

func check_departed_visibility() -> void:
	var snapshot := {"active":true,"run_id":"handoff-run","map":"landfall"}
	for reason: String in ["finished","skipped"]:
		var f := fixture()
		var nodes := add_departed(f)
		pose_at(f,68 if reason == "finished" else 42)
		f.scene.cancel(reason) if reason == "finished" else f.scene.skip()
		expect(not f.departed.daughter.visible and not f.departed.abductor.visible and not f.departed.escort.visible,"departed family captors remain hidden after live "+reason+" while native ACK is pending")
		for index in 300: f.scene._update_handoff_visibility(snapshot,nodes,"landfall")
		expect(f.scene._handoff_hidden.size() == 3 and not f.departed.abductor.visible,"arbitrarily long unchanged party reading cannot resurrect departed cast after "+reason)
		expect(f.departed.daughter.server_target.origin == Vector3(2,0,-2) and nodes.size() == 4,"the visibility handoff does not alter native positions, actor IDs, or actor-table lifecycle")
		f.departed.abductor.server_target.origin += Vector3.RIGHT
		f.scene._update_handoff_visibility(snapshot,nodes,"landfall")
		expect(f.departed.abductor.visible and not f.departed.daughter.visible,"a fresh native movement takes ownership of only its exact actor's visibility")
		f.departed.escort._last_command_sequence = 4
		f.scene._update_handoff_visibility(snapshot,nodes,"landfall")
		expect(f.departed.escort.visible,"a fresh native command releases a departed actor even without tile movement")
		var crowd := Crowd.new()
		crowd.park = true
		expect(crowd.park_node(f.departed.daughter.actor_id,f.departed.daughter,"departed-child",1000),"the actual native crowd policy parks the departed child for reuse")
		nodes.erase(f.departed.daughter.actor_id)
		f.scene._update_handoff_visibility(snapshot,nodes,"landfall")
		expect(f.scene._handoff_hidden.is_empty() and not f.departed.daughter.visible and f.departed.daughter.process_mode == Node.PROCESS_MODE_DISABLED,"native removal drops the lease without resurrecting the actual parked hidden body")
		var revived := crowd.take_parked(f.departed.daughter.actor_id,"departed-child")
		expect(revived == f.departed.daughter and revived.visible and revived.process_mode == Node.PROCESS_MODE_INHERIT,"ordinary native take_parked alone owns the later legitimate reappearance")
		nodes[f.departed.daughter.actor_id] = revived
		f.scene._update_handoff_visibility(snapshot,nodes,"landfall")
		expect(revived.visible,"the ended cinematic cannot hide a natively revived body again")
		dispose(f)
	for reason: String in ["map_changed","actor_lost","cancelled"]:
		var f := fixture()
		add_departed(f)
		pose_at(f,28)
		f.scene.cancel(reason)
		expect(f.departed.daughter.visible and f.departed.abductor.visible and f.scene._handoff_hidden.is_empty(),"an interrupted "+reason+" restores original cast visibility")
		dispose(f)
	var f := fixture("help",true)
	add_departed(f)
	pose_at(f,68)
	f.scene.cancel("finished")
	expect(f.departed.daughter.visible and f.departed.abductor.visible and f.scene._handoff_hidden.is_empty(),"read-only replay restores original departed-cast visibility")
	dispose(f)
	f = fixture()
	var nodes := add_departed(f)
	pose_at(f,68)
	f.scene.cancel("finished")
	f.departed.daughter.set_meta(&"identity_key","a legitimate different native person")
	f.scene._update_handoff_visibility(snapshot,nodes,"landfall")
	expect(f.departed.daughter.visible and f.scene._handoff_hidden.size() == 2,"a reused native node identity cannot inherit an old person's hidden lease")
	var replacement := Actor.new()
	root.add_child(replacement)
	replacement.actor_id = f.departed.abductor.actor_id
	nodes[replacement.actor_id] = replacement
	f.scene._update_handoff_visibility(snapshot,nodes,"landfall")
	expect(replacement.visible and not f.departed.abductor.visible,"actor-ID replacement leaves the removed predecessor hidden and never touches the replacement")
	replacement.queue_free()
	f.scene.reset_session()
	expect(f.departed.escort.visible and f.scene._handoff_hidden.is_empty(),"session cleanup releases every remaining exact-node visibility lease")
	dispose(f)
	f = fixture()
	add_departed(f)
	pose_at(f,68)
	f.scene.cancel("finished")
	f.scene._start(f.rig,f.rig.camera,f.actor,{1:f.actor},{"protagonist":1})
	expect(f.departed.daughter.visible and f.scene._handoff_hidden.is_empty(),"the next authenticated film owns its cast visibility without an old handoff lease")
	dispose(f)
