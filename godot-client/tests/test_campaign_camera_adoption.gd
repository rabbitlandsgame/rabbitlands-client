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
	check_follow_orbit()
	check_exit_fade()
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
	expect(f.scene._beat_matches({"when":["help","watch"]}) and not f.scene._beat_matches({"when":["watch",""]}),"array-valued branch conditions select the current answer without comparing arrays to strings")
	f.scene._choice_state.selected = ""
	expect(f.scene._beat_matches({"when":["watch",""]}),"array-valued branch conditions can explicitly include the pre-choice default")
	f.scene._choice_state.selected = "help"
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
	f.scene._definition.cues = [{"at":0,"actor":"protagonist","destination":"start","face":"combat","face_offset":[0,0,2]}]
	f.scene._apply_actors()
	expect(is_equal_approx(f.actor.rotation.y,atan2(-10.0,-2.0)),"face_offset aims through the authored side approach without moving the face anchor")
	f.scene._definition.cues[0].erase("face_offset")
	f.scene._apply_actors()
	expect(is_equal_approx(f.actor.rotation.y,-PI/2),"omitting face_offset preserves the existing facing direction")
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

func check_follow_orbit() -> void:
	var f := fixture()
	f.scene._anchors.impact = Vector3(4,0,0)
	f.scene._definition.shots = [
		{"t":0,"anchor_actor":"protagonist","position":[-8,5,0],"target":[0,1,0]},
		{"t":42,"anchor_actor":"protagonist","follow_actor":"protagonist","orbit":true,"position":[-8,5,0],"target":[0,1,0]},
		{"t":46.15,"anchor_actor":"protagonist","position":[0,5,8],"target":[0,1,0]},
		{"t":46.16,"anchor":"combat","position":[-6,5,8],"target":[-6,1,0]},
		{"t":68,"anchor":"combat","position":[-6,5,8],"target":[-6,1,0]}]
	f.scene._definition.cues = [
		{"at":0,"actor":"protagonist","destination":"start","face":"post"},
		{"at":42,"actor":"protagonist","from":"start","destination":"impact","move_seconds":4.15,"action":"run","face":"post"}]
	pose_at(f,42)
	var beginning: Transform3D = f.rig.camera.global_transform
	expect(beginning.origin.is_equal_approx(Vector3(-8,5,0)),"a follow orbit begins at the existing approach view without a cut")
	pose_at(f,44.075)
	var target: Vector3 = f.scene._capture_camera().target
	var orbit: Vector3 = f.rig.camera.global_position-target
	expect(target.is_equal_approx(f.actor.global_position+Vector3.UP),"the moving player's look-at point remains attached throughout the approach")
	expect(is_equal_approx(orbit.length(),sqrt(80.0)) and orbit.is_equal_approx(Vector3(-sqrt(32.0),4,sqrt(32.0))),"the camera rotates at the authored radius instead of cutting a shorter chord through the action")
	var held: Transform3D = f.rig.camera.global_transform
	var movement := Vector3(1.7,0.3,-0.6)
	f.actor.global_position += movement
	f.scene._apply_camera()
	expect(f.rig.camera.global_position.is_equal_approx(held.origin+movement) and f.scene._capture_camera().target.is_equal_approx(target+movement),"a player step moves the entire orbit frame equally with no pull toward the future combat post")
	# Explicit follow applies to both keys, even if an endpoint's fallback anchor differs.
	f.scene._definition.shots[2].erase("anchor_actor")
	f.scene._definition.shots[2].anchor = "combat"
	pose_at(f,44.075)
	expect(f.scene._capture_camera().target.is_equal_approx(f.actor.global_position+Vector3.UP),"transition follow_actor pins both endpoint offsets to the same current player")
	f.scene._definition.shots[2].erase("anchor")
	f.scene._definition.shots[2].anchor_actor = "protagonist"
	var previous_yaw := -PI/2
	var continuous := true
	for time: float in [42.0,42.5,43.0,43.5,44.0,44.5,45.0,45.5,46.0,46.15]:
		pose_at(f,time)
		var offset: Vector3 = f.rig.camera.global_position-f.scene._capture_camera().target
		var yaw := atan2(offset.x,offset.z)
		continuous = continuous and yaw >= previous_yaw-0.0001 and yaw-previous_yaw < deg_to_rad(18)
		previous_yaw = yaw
	expect(continuous and is_zero_approx(previous_yaw),"rotation progresses smoothly across the whole run and reaches the final angle at impact")
	pose_at(f,43)
	var early_offset: Vector3 = f.rig.camera.global_position-f.scene._capture_camera().target
	expect(atan2(early_offset.x,early_offset.z) > deg_to_rad(-80),"rotation has already begun during the early run instead of waiting for the last second")
	pose_at(f,46.15)
	var impact: Transform3D = f.rig.camera.global_transform
	pose_at(f,46.155)
	expect(f.rig.camera.global_transform.is_equal_approx(impact),"the moving endpoint and equal static hold connect continuously without duplicate timestamps")
	pose_at(f,46.16)
	expect(f.rig.camera.global_transform.is_equal_approx(impact),"the final fixed confrontation view matches the orbit endpoint exactly")
	f.actor.global_position += Vector3(2,0,1)
	f.scene.elapsed = 50
	f.scene._apply_camera()
	expect(f.rig.camera.global_transform.is_equal_approx(impact),"after impact the final hold stays in world space rather than continuing to chase the actor")
	pose_at(f,68)
	f.scene.cancel("finished")
	expect(f.rig.camera.global_transform.is_equal_approx(impact) and not f.scene.blocks_input(),"live Help still adopts the fixed confrontation view after an orbit transition")
	dispose(f)
	f = fixture()
	f.scene._definition.shots = [
		{"t":0,"anchor":"start","position":[-8,5,0],"target":[0,1,0]},
		{"t":10,"anchor":"combat","position":[0,5,8],"target":[0,1,0]}]
	pose_at(f,5)
	expect(f.rig.camera.global_position.is_equal_approx(Vector3(1,5,4)),"ordinary shots without opt-in retain their original linear interpolation")
	f.scene._definition.shots[0].follow_actor = "missing-role"
	pose_at(f,5)
	expect(f.rig.camera.global_position.is_equal_approx(Vector3(1,5,4)),"an unavailable optional follower safely retains ordinary authored anchors")
	f.scene._replaying = true
	f.scene._definition.shots[0].orbit = true
	pose_at(f,5)
	expect(f.rig.camera.global_position.is_finite() and not f.scene._ack_requested,"read-only replay can sample the same orbit without requesting gameplay acknowledgement")
	f.scene.reduced_motion = true
	pose_at(f,5)
	expect(f.rig.camera.global_transform.is_equal_approx(f.original),"reduced motion suppresses the optional orbit during playback")
	dispose(f)
	var seam := Scene._orbit_offset(Vector3(0.01,2,-10),Vector3(-0.01,2,-10),0.5)
	expect(seam.z < -9.99 and absf(seam.x) < 0.001,"an orbit crossing180 degrees uses the short yaw arc")
	expect(Scene._orbit_offset(Vector3.ZERO,Vector3(4,2,8),0.5) == Vector3(2,1,4),"a zero-radius endpoint falls back to finite linear interpolation")

func fade_policy(f: Dictionary) -> void:
	f.scene._definition.erase("exit_camera")
	f.scene._definition.exit_transition = {"mode":"fade","out_seconds":0.6,"in_seconds":0.6}

func check_exit_fade() -> void:
	var f := fixture()
	fade_policy(f)
	pose_at(f,68)
	var finale: Transform3D = f.rig.camera.global_transform
	expect(not finale.is_equal_approx(f.original),"a fade-exit film never begins the ordinary camera pan during its final shot")
	var completed: Array = []
	f.scene.presentation_finished.connect(func(_token: String,reason: String) -> void:
		completed.append([reason,f.scene._exit_black.color.a,f.scene.blocks_input()]))
	f.scene.cancel("finished")
	expect(f.scene.blocks_input() and completed.is_empty() and f.scene._exit_fade.phase == "out","completion first reserves a fade-out while retaining the scene camera and input lease")
	f.scene._advance_exit_fade(0.3)
	expect(f.scene._exit_black.color.a > 0.49 and f.scene._exit_black.color.a < 0.51 and f.rig.camera.global_transform.is_equal_approx(finale),"the first half darkens the unchanged finale without visible camera travel")
	f.scene._advance_exit_fade(0.3)
	expect(f.rig.camera.global_transform.is_equal_approx(f.original) and f.scene._exit_black.color.a == 1 and not f.scene.blocks_input(),"only full black restores the gameplay camera and releases normal controls")
	expect(completed == [["finished",1.0,false]] and f.scene._ack_requested,"the one normal completion is emitted after camera restoration underneath full black")
	var yaw: float = f.rig.yaw_degrees
	f.rig.handle_keyboard(Vector2.RIGHT,0.1)
	expect(is_equal_approx(f.rig.yaw_degrees,yaw-9),"ordinary camera controls are available during the gameplay fade-in")
	f.scene.update(0.3,{"active":false},f.rig,{1:f.actor},1,"landfall")
	expect(f.scene._exit_black.color.a > 0.49 and f.scene._exit_black.color.a < 0.51 and not f.scene.blocks_input(),"the authentic completed/inactive snapshot continues revealing gameplay rather than popping the fade off")
	f.scene.update(0.3,{"active":false},f.rig,{1:f.actor},1,"landfall")
	expect(f.scene._exit_fade.is_empty() and not f.scene._exit_black.visible and completed.size() == 1,"the completed fade clears its overlay and cannot emit a duplicate ACK")
	expect(f.scene._exit_black.mouse_filter == Control.MOUSE_FILTER_IGNORE,"the fade overlay never captures input after gameplay control is released")
	dispose(f)
	for replay: bool in [false,true]:
		f = fixture("watch",replay)
		fade_policy(f)
		pose_at(f,42)
		var before: Transform3D = f.rig.camera.global_transform
		var normal: Array = []
		var reviewed: Array = []
		f.scene.presentation_finished.connect(func(_token: String,reason: String) -> void: normal.append(reason))
		f.scene.replay_finished.connect(func(_token: String,reason: String) -> void: reviewed.append(reason))
		f.scene.skip()
		f.scene.skip()
		f.scene._advance_exit_fade(0.2)
		expect(f.rig.camera.global_transform.is_equal_approx(before) and f.scene.blocks_input(),"rapid repeated Skip retains the current camera until black in "+("replay" if replay else "live playback"))
		f.scene._advance_exit_fade(0.4)
		expect(f.rig.camera.global_transform.is_equal_approx(f.original) and f.scene._exit_black.color.a == 1,"Skip restores the saved camera beneath black in "+("replay" if replay else "live playback"))
		expect((normal == [] and reviewed == ["skipped"] and not f.scene._ack_requested) if replay else (normal == ["skipped"] and reviewed == [] and f.scene._ack_requested),"fade replay remains read-only while live Skip acknowledges exactly once")
		dispose(f)
	f = fixture()
	fade_policy(f)
	pose_at(f,50)
	f.scene.skip()
	f.scene._advance_exit_fade(0.3)
	f.scene.cancel("map_changed")
	expect(not f.scene.blocks_input() and f.scene._exit_fade.is_empty() and not f.scene._exit_black.visible and f.rig.camera.global_transform.is_equal_approx(f.original),"a map interruption clears a partial blackout and restores the normal camera immediately")
	dispose(f)
	f = fixture()
	fade_policy(f)
	f.scene.reduced_motion = true
	pose_at(f,50)
	var still: Transform3D = f.rig.camera.global_transform
	f.scene.skip()
	f.scene._advance_exit_fade(0.3)
	expect(f.rig.camera.global_transform.is_equal_approx(still),"reduced motion uses opacity alone and never adds camera movement to the exit")
	f.scene._advance_exit_fade(0.3)
	f.scene._start(f.rig,f.rig.camera,f.actor,{1:f.actor},{"protagonist":1})
	expect(f.scene._exit_fade.is_empty() and not f.scene._exit_black.visible,"the next authenticated film cannot inherit an old gameplay fade overlay")
	dispose(f)
