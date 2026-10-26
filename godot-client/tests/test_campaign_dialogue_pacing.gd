extends SceneTree

const Presentation := preload("res://src/world/campaign_scene.gd")
const CameraFixture := preload("res://tests/test_campaign_ferry_camera.gd")
const Wiring := preload("res://tests/test_campaign_cart_wiring.gd")
var checks := 0
var failures := 0

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
	var adapter := CoordinateAdapter.new({"metresPerTile":1.0,"serverOrigin":[435,448],"walkingHeight":2.5,"invertServerY":true})
	var actors := {}
	for id: int in {1:Vector2i(444,322),2:Vector2i(442,319),3:Vector2i(425,316),5:Vector2i(423,318)}:
		var actor := CameraFixture.Actor.new()
		stage.add_child(actor)
		var tiles := {1:Vector2i(444,322),2:Vector2i(442,319),3:Vector2i(425,316),5:Vector2i(423,318)}
		actor.position = adapter.tile_center(tiles[id].x, tiles[id].y)
		actor.server_target = actor.global_transform
		actors[id] = actor
	var rig := CameraFixture.Rig.new()
	stage.add_child(rig)
	rig.focus = actors[1].global_position
	rig.position = rig.focus
	var camera := Camera3D.new()
	rig.add_child(camera)
	rig.camera = camera
	camera.position = Vector3(14,17,11)
	camera.look_at(rig.focus + Vector3.UP)
	var scene := Presentation.new()
	root.add_child(scene)
	scene.configure()
	scene.set_auto_dialogue(false, false)
	scene.set_reduced_motion(false, false)
	var state := Wiring.snapshot()
	state.run_id = "pacing"
	state.scene.token = token
	state.scene.requires_ack = true
	state.scene.ack_revision = 0
	state.actors = {"odo":2,"worker":3,"foreman":5,"protagonist":1,"voss":99,"clerk":98}
	state.scene.actors = state.actors.duplicate(true)
	state.cart.holder = "foreman"
	state.cart.worker_presentation_offset = [-0.48,0,0.32]
	state.anchors = CameraFixture.PIER_ANCHORS.duplicate(true)
	state.anchors.merge({"cart_anchor":[422,316],"cart_post":[426,316],"mooring_post":[426,316],"cart_release":[420,316],
		"cart_fulcrum":[424,318],"cart_unload_1":[428,315],"cart_unload_2":[429,316],"cart_rope_1":[424,314],
		"cart_rope_2":[427,315],"cart_hold":[426,318],"inspection_turn":[438,321],"inspection_stand":[428,319],
		"inspection_damage":[422,316],"muster_odo":[441,324],"muster_worker":[441,325],"odo_post":[442,319]},true)
	var events := {"inspection":[],"choice":[],"normal":[],"replay":[]}
	scene.inspection_requested.connect(func(action: String) -> void: events.inspection.append(action))
	scene.choice_requested.connect(func(id: String) -> void: events.choice.append(id))
	scene.presentation_finished.connect(func(value: String, reason: String) -> void: events.normal.append([value,reason]))
	scene.replay_finished.connect(func(value: String, reason: String) -> void: events.replay.append([value,reason]))
	return {"stage":stage,"scene":scene,"actors":actors,"rig":rig,"camera":camera,"adapter":adapter,"state":state,"events":events}

func tick(f: Dictionary, delta: float) -> void:
	f.scene.update(delta,f.state,f.rig,f.actors,1,"greenlight",true,f.adapter,func(_at: Vector3) -> float:return 2.5)
func at(f: Dictionary, time: float) -> void: tick(f,maxf(0,time-float(f.scene.elapsed)))
func dispose(f: Dictionary) -> void:
	f.scene.cancel("test_complete")
	f.scene.queue_free()
	f.stage.queue_free()
func completed_inspection(f: Dictionary) -> void:
	f.state.scene.inspection.status = "complete"
	f.state.scene.inspection.can_start = false
	f.state.scene.choice.can_choose = true
	f.actors[1].server_target.origin = f.adapter.tile_center(428,319)
	tick(f,0)
func read_gate(f: Dictionary, gate: float) -> void:
	at(f,gate+0.1)
	expect(f.scene.is_dialogue_waiting() and is_equal_approx(f.scene.elapsed,gate-0.001),"manual dialogue holds immediately before its authored reading gate " + str(gate))
	var old: float = f.scene.elapsed
	tick(f,65)
	expect(is_equal_approx(f.scene.elapsed,old),"a long frame cannot consume the held line " + str(gate))
	expect(f.scene.continue_dialogue() and not f.scene.continue_dialogue() and is_equal_approx(f.scene.elapsed,gate),"Continue releases exactly one current line " + str(gate))

func run() -> void:
	create_timer(90).timeout.connect(func() -> void:push_error("Dialogue pacing checks timed out");quit(1))
	root.size = Vector2i(1280,720)
	root.get_node("Network").call("block_for_hud_preview")
	var definitions := Presentation.scene_definitions()
	var arrival: Dictionary = definitions["measure.cart.arrival"]
	expect(arrival.duration == 82 and arrival.inspection_at == 36 and arrival.inspection_wait_at == 43 and arrival.choice_at == 60,"the complete opening keeps its authored inspection, decision and slower duration")
	expect(arrival.dialogue_holds == [8.0,16.0,26.0,36.0,52.0,60.0,72.0],"every major opening exchange has an explicit reading pause")
	for id: String in ["measure.cart.arrival","measure.cart.resolved","measure.claims.inquiry","measure.claims.verified"]:
		expect(definitions.has(id) and float(definitions[id].duration) <= Presentation.MAX_DURATION,"the bounded data loader retains the complete authored scene " + id)
	var f := fixture("pacing-arrival")
	tick(f,0)
	expect(f.scene.playing and not f.scene._actors.has("voss") and not f.scene._actors.has("clerk"),"unused distant NPCs do not delay or join the new scene")
	expect(f.scene.cart_accident_progress() == 0,"the cart begins level before the visible accident")
	at(f,5)
	expect(is_equal_approx(f.scene.cart_accident_progress(),0.5),"the original accident progresses between four and six seconds")
	var original_identity := ""
	for gate: float in [8.0,16.0,26.0,36.0]:
		if gate == 8.0:
			at(f,8.1)
			original_identity = f.scene._line_identity(8.0)
		read_gate(f,gate)
		expect(f.events.inspection.is_empty(),"reading the briefing grants no native inspection before the next controller update")
	tick(f,0)
	expect(f.events.inspection == ["start"],"only the authored inspection point requests the server-owned walk")
	tick(f,65)
	expect(f.scene.elapsed == 43 and not f.scene.is_dialogue_waiting() and f.events.inspection == ["start"] and f.events.choice.is_empty(),"a sixty-five-second frame stops at unproved inspection rather than a later reading gate or choice")
	completed_inspection(f)
	read_gate(f,52)
	read_gate(f,60)
	tick(f,0)
	expect(f.scene.choice_context().waiting and f.scene.elapsed == 60,"the bottom decision waits at its own gate after the line is read")
	tick(f,65)
	expect(f.scene.elapsed == 60 and not f.scene.is_dialogue_waiting() and f.events.choice.is_empty(),"an unresolved choice cannot jump to Odo's response during a large frame")
	f.scene._choice_dialog.option_buttons.unload.pressed.emit()
	expect(f.events.choice == ["unload"] and str(f.state.scene.choice.selected).is_empty(),"a player decision requests confirmation without manufacturing its result")
	f.state.scene.choice.selected = "unload"
	f.state.scene.choice.response = "Set down both loads first, then lift the cart safely."
	f.state.scene.choice.can_choose = false
	f.state.scene.ack_revision = 1
	f.state.cart.route = "unload"
	tick(f,0)
	expect(not f.scene.choice_context().waiting,"only the confirmed snapshot releases the live choice")
	read_gate(f,72)
	expect(f.scene.cart_accident_progress() == 1,"the opening retains its original trapped cart pose through the complete response")
	var accepted := JSON.stringify(f.state)
	at(f,float(arrival.duration))
	expect(not f.scene.playing and f.events.normal == [["pacing-arrival","finished"]] and JSON.stringify(f.state)==accepted,"completion releases input once without changing authoritative progress")
	expect(f.scene.request_replay(f.state,"greenlight"),"a completed acknowledged scene can replay locally")
	tick(f,0)
	at(f,8.1)
	f.scene._on_line_continue(original_identity)
	expect(f.scene.is_dialogue_waiting(),"a queued Continue from the previous playback cannot release a same-token replay line")
	for gate: float in [8.0,16.0,26.0,36.0,52.0,60.0]:read_gate(f,gate)
	tick(f,0)
	var disabled := true
	for button: Button in f.scene._choice_dialog.option_buttons.values():disabled = disabled and button.disabled
	expect(f.scene.is_replaying() and disabled and f.scene._choice_dialog.continue_button.visible,"replay shows all three recorded options as read-only with a reachable Continue")
	f.scene._choice_dialog.option_buttons.lever.pressed.emit()
	f.scene._choice_dialog.continue_button.pressed.emit()
	tick(f,0)
	read_gate(f,72)
	at(f,float(arrival.duration))
	expect(f.events.inspection == ["start"] and f.events.choice == ["unload"] and f.events.normal.size()==1 and f.events.replay == [["pacing-arrival","finished"]] and JSON.stringify(f.state)==accepted,"replay keeps manual pacing while sending no inspection, choice, normal acknowledgment or proof")
	expect(f.scene.cart_accident_progress() == -1,"finished presentation removes its cosmetic cart override")
	dispose(f)
	var automatic := fixture("auto-pacing")
	automatic.scene.set_auto_dialogue(true,false)
	tick(automatic,0);at(automatic,27)
	automatic.scene.set_auto_dialogue(false,false);tick(automatic,0)
	expect(automatic.scene.elapsed==27 and not automatic.scene.is_dialogue_waiting(),"switching Auto off never rewinds previously passed reading gates")
	at(automatic,36.1)
	expect(automatic.scene.is_dialogue_waiting() and is_equal_approx(automatic.scene.elapsed,35.999),"the next unread line still pauses after Auto is disabled")
	automatic.scene.set_auto_dialogue(true,false);tick(automatic,65)
	expect(automatic.scene.elapsed==43 and automatic.events.inspection==["start"],"Auto never bypasses an unproved native inspection")
	automatic.scene.set_auto_dialogue(false,false);completed_inspection(automatic);at(automatic,52.1)
	expect(automatic.scene.is_dialogue_waiting() and is_equal_approx(automatic.scene.elapsed,51.999),"the inspection cap prevents Auto from incorrectly marking a later line read")
	dispose(automatic)
	var reduced := fixture("reduced-pacing")
	reduced.scene.set_reduced_motion(true,false);tick(reduced,0);at(reduced,8.1)
	expect(reduced.scene.is_dialogue_waiting(),"reduced camera motion preserves manual reading pauses")
	var stale: String = reduced.scene._line_identity(8.0)
	reduced.scene.cancel("replaced")
	reduced.state.scene.token = "replacement"
	tick(reduced,0);at(reduced,8.1);reduced.scene._on_line_continue(stale)
	expect(reduced.scene.is_dialogue_waiting(),"a canceled scene's queued Continue cannot release its replacement")
	dispose(reduced)
	var transcript := fixture("account-pause")
	tick(transcript,0);at(transcript,5);transcript.scene.show_transcript();tick(transcript,65)
	expect(transcript.scene.elapsed==5 and transcript.events.inspection.is_empty(),"reading the scene account pauses the timeline and native requests")
	transcript.scene._transcript.hide();at(transcript,8.1)
	expect(transcript.scene.is_dialogue_waiting(),"closing the account resumes at the next unread exchange")
	dispose(transcript)
	var ambient := fixture("ambient")
	var source := JSON.stringify(ambient.state)
	var worker_target: Transform3D = ambient.actors[3].server_target
	var foreman_target: Transform3D = ambient.actors[5].server_target
	ambient.scene.update_ambient(ambient.state,ambient.actors,ambient.adapter,func(_at: Vector3)->float:return 2.5)
	expect(ambient.actors[5].action==&"defend" and ambient.actors[3].action==&"seated_idle","the actual foreman holds while the living injured worker sits beside the cart")
	expect(ambient.actors[3].position.is_equal_approx(worker_target.origin+Vector3(-0.48,0,0.32)) and ambient.actors[3].server_target==worker_target and ambient.actors[5].server_target==foreman_target and JSON.stringify(ambient.state)==source,"contact staging stays grounded and leaves server body positions and gameplay state intact")
	ambient.state.cart.holder = "Aster"
	ambient.scene.update_ambient(ambient.state,ambient.actors,ambient.adapter,func(_at: Vector3)->float:return 2.5)
	expect(ambient.actors[5].action==&"idle" and ambient.actors[5].global_transform==foreman_target,"a real party brake holder releases the foreman's cosmetic hold pose")
	ambient.state.cart.released = true
	ambient.scene.update_ambient(ambient.state,ambient.actors,ambient.adapter,func(_at: Vector3)->float:return 2.5)
	expect(ambient.actors[3].position.is_equal_approx(worker_target.origin) and ambient.actors[3].action==&"seated_idle","actual release removes the pin offset while leaving the untreated worker seated")
	ambient.actors[3].server_target.origin += Vector3(2,0,1)
	ambient.scene.update_ambient(ambient.state,ambient.actors,ambient.adapter,func(_at: Vector3)->float:return 2.5)
	expect(ambient.actors[3].position.is_equal_approx(ambient.actors[3].server_target.origin),"a late native worker movement updates the ambient presentation immediately")
	ambient.state.cart.treated = true
	ambient.scene.update_ambient(ambient.state,ambient.actors,ambient.adapter,func(_at: Vector3)->float:return 2.5)
	expect(ambient.actors[3].action==&"idle" and ambient.scene._cart_ambient.is_empty(),"treatment releases all remaining injured-worker animation overrides")
	dispose(ambient)
	await process_frame
	await process_frame
	print("campaign dialogue pacing: ",checks," checks; ",failures," failures")
	quit(1 if failures else 0)
