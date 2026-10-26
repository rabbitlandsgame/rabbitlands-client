extends SceneTree
## The controller stages a view of the protagonist, while only an explicit
## native server reply can finish inspection or enable a rescue decision.
const Presentation := preload("res://src/world/campaign_scene.gd")
const CameraFixture := preload("res://tests/test_campaign_ferry_camera.gd")
const Decisions := preload("res://tests/test_campaign_ferry_decision.gd")
var checks := 0
var failures := 0

func _init() -> void: run.call_deferred()
func expect(ok: bool, message: String) -> void:
	checks += 1
	if ok: print("PASS: ", message)
	else:
		failures += 1
		push_error(message)

func fixture(token: String, helper := false) -> Dictionary:
	var stage := Node3D.new()
	root.add_child(stage)
	var adapter := CoordinateAdapter.new({"metresPerTile":1.0,"serverOrigin":[435,448],"walkingHeight":2.5,"invertServerY":true})
	var actors := {}
	for id: int in [1,2,3,4,5,6]:
		var tile: Vector2i = {1:Vector2i(450,308),2:Vector2i(450,313),3:Vector2i(457,319),4:Vector2i(444,310),5:Vector2i(456,318),6:Vector2i(451,308)}[id]
		var actor := CameraFixture.Actor.new()
		stage.add_child(actor)
		actor.global_position = adapter.tile_center(tile.x,tile.y)
		actor.server_target = actor.global_transform
		actors[id] = actor
	var local_id := 6 if helper else 1
	var rig := CameraFixture.Rig.new()
	stage.add_child(rig)
	rig.focus = actors[local_id].global_position
	rig.global_position = rig.focus
	var camera := Camera3D.new()
	rig.add_child(camera)
	rig.camera = camera
	camera.position = Vector3(14,17,11)
	camera.look_at(rig.focus+Vector3.UP*1.2)
	camera.fov = 67
	camera.near = 0.8
	var scene := Presentation.new()
	root.add_child(scene)
	scene.set_reduced_motion(false,false)
	var choice := Decisions.decision(not helper)
	choice.can_choose = false
	var state := {"version":1,"kind":"opening","active":true,"run_id":"inspection-run","map":"greenlight","title":"The Ferry That Arrived Twice","key":"assess","targets":[],
		"actors":{"odo":2,"worker":3,"clerk":4,"foreman":5,"protagonist":1},
		"anchors":{"clerk_arrival":[444,310],"clerk_stand":[447,312],"foreman_arrival":[456,318],"foreman_turn":[455,317],"foreman_stand":[453,315],"protagonist_post":[450,308],"inspection_turn":[449,309],"inspection_stand":[448,310],"inspection_damage":[450,310]},
		"scene":{"id":"measure.landing.arrival","token":token,"requires_ack":true,"ack_revision":0,"choice":choice,
			"inspection":{"id":"landing_overview","actor_id":1,"object_id":61001,"status":"waiting_owner" if helper else "pending","can_start":not helper,"path":[[449,309],[448,310]],"approach":[448,310]}}}
	state.scene.actors = state.actors.duplicate(true)
	var inspections: Array[String] = []
	var choices: Array[String] = []
	var ordinary: Array = []
	var replay: Array = []
	scene.inspection_requested.connect(func(action: String) -> void: inspections.append(action))
	scene.choice_requested.connect(func(id: String) -> void: choices.append(id))
	scene.presentation_finished.connect(func(value: String, reason: String) -> void: ordinary.append([value,reason]))
	scene.replay_finished.connect(func(value: String, reason: String) -> void: replay.append([value,reason]))
	return {"stage":stage,"scene":scene,"state":state,"actors":actors,"adapter":adapter,"local_id":local_id,"rig":rig,"camera":camera,"original":camera.global_transform,"focus":rig.focus,"inspections":inspections,"choices":choices,"ordinary":ordinary,"replay":replay}

func tick(f: Dictionary, delta: float) -> void:
	f.scene.update(delta,f.state,f.rig,f.actors,f.local_id,"greenlight",true,f.adapter)
func at(f: Dictionary, elapsed: float) -> void: tick(f,maxf(0,elapsed-float(f.scene.elapsed)))
func complete(f: Dictionary) -> void:
	f.state.scene.inspection.status = "complete"
	f.state.scene.inspection.can_start = false
	f.state.scene.choice.can_choose = bool(f.state.scene.choice.owner_is_you)
	tick(f,0)
func select(f: Dictionary) -> void:
	f.state.scene.choice.selected = "repair"
	f.state.scene.choice.response = Decisions.RESPONSES.repair
	f.state.scene.choice.can_choose = false
	f.state.scene.ack_revision = 1
	tick(f,0)
func dispose(f: Dictionary) -> void:
	f.scene.cancel("test_complete")
	f.scene.queue_free()
	f.stage.queue_free()

func run() -> void:
	create_timer(90).timeout.connect(func() -> void: push_error("Ferry inspection check timed out"); quit(1))
	root.size = Vector2i(1280,720)
	root.get_node("Network").call("block_for_hud_preview")
	var f := fixture("inspection-owner")
	expect(EloriaProtocol.decode_campaign(JSON.stringify(f.state).to_utf8_buffer()).get("type") == "campaign","the native inspection path and scene metadata decode without a private fixture dependency")
	var original_target: Transform3D = f.actors[1].server_target
	var original_state := JSON.stringify(f.state)
	tick(f,0); at(f,18.9)
	expect(f.inspections.is_empty() and f.scene._actors.protagonist == f.actors[1],"the actual local protagonist is staged but inspection is not requested before its authored cue")
	at(f,19); tick(f,0); tick(f,0.1)
	expect(f.inspections == ["start"] and f.scene.inspection_context().waiting,"the inspection cue requests native work exactly once")
	at(f,20.2)
	expect(f.actors[1].global_position.is_equal_approx(f.adapter.tile_center(449,309)),"the visible protagonist follows the actual inspection turn anchor")
	expect(f.actors[1].server_target == original_target and JSON.stringify(f.state) == original_state,"visual staging alone cannot move the authoritative target or mark inspection complete")
	f.state.scene.inspection.status = "walking"
	f.state.scene.inspection.can_start = false
	f.actors[1].server_target.origin = f.adapter.tile_center(449,309)
	at(f,22)
	expect(f.actors[1].global_position.is_equal_approx(f.adapter.tile_center(448,310)) and f.actors[1].action == &"pickup","the protagonist reaches and examines the authored damaged-access post")
	f.actors[1].server_target.origin = f.adapter.tile_center(448,310)
	at(f,24)
	var wait_view: Transform3D = f.camera.global_transform
	tick(f,65)
	expect(f.scene.elapsed == 24 and not f.scene._choice_waiting and f.choices.is_empty() and f.ordinary.is_empty(),"the film waits for native inspection instead of unlocking choices through elapsed time")
	expect(f.camera.global_transform.is_equal_approx(wait_view) and f.inspections == ["start"],"waiting for the native result keeps the group view steady and sends no repeated inspection")
	complete(f); at(f,26)
	expect(f.scene._choice_waiting and f.scene._dialogue.content_active() and f.scene._dialogue._actor.get_ref() == f.actors[1],"native completion unlocks the player-profile choice in the same bottom dialogue")
	expect(f.scene.choice_context().run_id == "inspection-run" and f.scene.choice_context().token == "inspection-owner" and f.state.scene.id == "measure.landing.arrival","inspection and decision preserve the same run and arrival token")
	(f.scene._choice_dialog.option_buttons.repair as Button).pressed.emit()
	expect(f.choices == ["repair"] and str(f.state.scene.choice.selected).is_empty(),"the embedded rescue button requests a plan without inventing a server selection")
	select(f)
	expect(f.scene._caption.text == Decisions.RESPONSES.repair and f.scene._dialogue._actor.get_ref() == f.actors[2] and not f.scene._dialogue.content_active(),"the confirmed plan restores Odo's actual portrait and instructions")
	var displacement: Vector3 = f.actors[1].server_target.origin-original_target.origin
	var expected: Transform3D = f.original
	expected.origin += displacement
	at(f,34)
	expect(f.actors[1].action == &"idle", "a protagonist already at the native return post idles instead of shuffling through a zero-distance walk")
	var latest_target: Transform3D = f.actors[1].server_target
	latest_target.basis = Basis(Vector3.UP,1.1)
	f.actors[1].server_target = latest_target
	at(f,38.2)
	expect(is_equal_approx(f.actors[1].rotation.y,1.1), "the protagonist's final staged facing matches the latest authoritative yaw before release")
	at(f,40)
	expect(f.camera.global_transform.is_equal_approx(expected) and f.rig.focus.is_equal_approx(f.focus+displacement),"camera restoration follows the protagonist's latest native target instead of its old staged position")
	expect(f.actors[1].global_transform.is_equal_approx(f.actors[1].server_target) and f.inspections == ["start"],"completion releases the player to the real native post without a spurious cancellation")
	expect(f.ordinary == [["inspection-owner","finished"]],"the full arrival reports one acknowledgement after inspection, decision and response")
	var saved := JSON.stringify(f.state)
	expect(f.scene.request_replay(f.state,"greenlight"),"the complete arrival can be replayed locally")
	tick(f,0); at(f,19); at(f,26)
	expect(f.inspections == ["start"] and f.scene._choice_review,"replay stages the inspection without starting real native work")
	f.scene._choice_dialog.continue_button.pressed.emit(); tick(f,0); at(f,40)
	expect(f.inspections == ["start"] and f.ordinary.size() == 1 and f.replay == [["inspection-owner","finished"]] and JSON.stringify(f.state) == saved,"replay creates no native inspection, selection, acknowledgement or progress mutation")
	dispose(f)
	var retry := fixture("inspection-retry")
	tick(retry,0); at(retry,19)
	retry.scene.inspection_send_failed(); tick(retry,0)
	expect(retry.scene._inspection_retry.visible and retry.inspections == ["start"],"a send failure offers an explicit retry without silently starting again")
	retry.scene._inspection_retry.pressed.emit()
	expect(retry.inspections == ["start","start"],"explicit retry requests one replacement native walk")
	retry.state.scene.inspection.status = "blocked"
	at(retry,24)
	expect(retry.scene.elapsed == 24 and retry.scene._inspection_retry.visible and retry.scene._caption.text.contains("blocked"),"a blocked native path remains recoverable and cannot open the rescue choice")
	retry.scene.skip(); tick(retry,0.7)
	expect(retry.inspections == ["start","start","cancel"] and not retry.scene.blocks_input(),"returning to play cancels an unfinished inspection exactly once")
	retry.scene._request_inspection()
	expect(retry.inspections.size() == 3,"a retry callback after cancellation cannot restart native work")
	expect(retry.scene.request_replay(retry.state,"greenlight"),"a skipped blocked inspection remains available for local review")
	tick(retry,0); at(retry,19); at(retry,26)
	expect(retry.state.scene.inspection.can_start and retry.inspections == ["start","start","cancel"] and retry.scene._choice_review,"even a still-eligible blocked inspection cannot start real work or block a local replay")
	retry.scene._choice_dialog.continue_button.pressed.emit(); tick(retry,0); at(retry,40)
	expect(retry.ordinary.size() == 1 and retry.replay == [["inspection-retry","finished"]] and retry.inspections.size() == 3 and retry.choices.is_empty(),"reviewing an unfinished inspection creates no command, choice or normal acknowledgement")
	dispose(retry)
	var helper := fixture("inspection-helper",true)
	tick(helper,0); at(helper,24); tick(helper,65)
	expect(helper.inspections.is_empty() and helper.scene.elapsed == 24 and helper.scene._caption.text.contains("story owner"),"a helper waits for the owner's native inspection and sends no movement command")
	expect(helper.scene._actors.protagonist == helper.actors[1] and helper.scene._actors.protagonist != helper.actors[helper.local_id],"the shared protagonist remains the owner rather than replacing a helper's own body")
	complete(helper); at(helper,26)
	expect(helper.scene._choice_waiting and not helper.scene._choice_dialog.continue_button.visible and "Waiting for MeasureHuman0" in helper.scene._choice_dialog.status_label.text,"inspection completion shows the owner-choice waiting state for helpers")
	select(helper)
	expect(helper.scene._caption.text == Decisions.RESPONSES.repair and helper.inspections.is_empty() and helper.choices.is_empty(),"owner confirmation restores Odo for helpers without submitting their own choice")
	at(helper,40)
	expect(helper.camera.global_transform.is_equal_approx(helper.original),"a helper returns to their own unchanged gameplay camera")
	dispose(helper)
	await process_frame; await process_frame
	print("ferry inspection: ",checks," checks; ",failures," failures")
	quit(1 if failures else 0)
