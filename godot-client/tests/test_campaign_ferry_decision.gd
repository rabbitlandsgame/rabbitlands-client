extends SceneTree
## Exercise the actual cinematic controller; the packets below model server
## replies, never a client-created gameplay outcome or reward.
const Presentation := preload("res://src/world/campaign_scene.gd")
const CameraFixture := preload("res://tests/test_campaign_ferry_camera.gd")
var checks := 0
var failures := 0
const RESPONSES := {
	"defend":"I will keep the crew back. Clear the startled cargo scavenger from the marked approach, then secure the landing rope so everyone can cross.",
	"repair":"Start at the leaking seal north of me. Inspect it, compare the workbench parts, fit one Wood Plank at the access mechanism, then test the repair.",
	"evacuate":"Start with the injured worker on the southeast quay. Use one Bandage, then walk with them to the dry muster point and confirm they are safe."}

func _init() -> void: run.call_deferred()
func expect(ok: bool, message: String) -> void:
	checks += 1
	if ok: print("PASS: ", message)
	else:
		failures += 1
		push_error(message)

func decision(owner := true) -> Dictionary:
	# Same public contract and initial instructions as the native server bundles.
	return {"id":"opening_rescue", "title":"How will you get the worker clear?", "selected":"", "response":"",
		"can_choose":owner, "owner":"MeasureHuman0", "owner_is_you":owner, "options":[
		{"id":"defend", "label":"Clear the approach", "detail":"Keep the crew back, defeat the startled cargo scavenger, then secure the landing rope. No supplies are required."},
		{"id":"repair", "label":"Repair the access", "detail":"Inspect the leaking joint, compare the workbench parts, fit one Wood Plank, then test the repair. The plank is consumed when fitted."},
		{"id":"evacuate", "label":"Lead an evacuation", "detail":"Use one Bandage to stabilize the injured worker, then walk with them to the dry muster point. The bandage is consumed during treatment."}]}

func fixture(token: String, owner := true) -> Dictionary:
	var stage := Node3D.new()
	root.add_child(stage)
	var adapter := CoordinateAdapter.new({"metresPerTile":1.0, "serverOrigin":[435,448], "walkingHeight":2.5, "invertServerY":true})
	var actors := {}
	var tiles := {1:Vector2i(450,308), 2:Vector2i(450,313), 3:Vector2i(457,319), 4:Vector2i(444,310), 5:Vector2i(456,318)}
	for id: int in tiles:
		var actor := CameraFixture.Actor.new()
		stage.add_child(actor)
		actor.global_position = adapter.tile_center(tiles[id].x, tiles[id].y)
		actor.server_target = actor.global_transform
		actors[id] = actor
	var rig := CameraFixture.Rig.new()
	stage.add_child(rig)
	rig.focus = actors[1].global_position
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
	scene.set_reduced_motion(false, false)
	var state := {"version":1, "kind":"opening", "active":true, "run_id":"decision-run", "map":"greenlight",
		"title":"The Ferry That Arrived Twice", "key":"rescue", "actors":{"odo":2,"worker":3,"clerk":4,"foreman":5}, "targets":[],
		"anchors":{"odo_meeting":[450,313], "clerk_arrival":[444,310], "clerk_stand":[447,312],
			"foreman_arrival":[456,318], "foreman_turn":[455,317], "foreman_stand":[453,315]},
		"scene":{"id":"measure.landing.plan", "token":token, "requires_ack":true, "ack_revision":1, "choice":decision(owner)}}
	var ordinary: Array = []
	var replay: Array = []
	var requests: Array[String] = []
	scene.presentation_finished.connect(func(value: String, reason: String) -> void: ordinary.append([value,reason]))
	scene.replay_finished.connect(func(value: String, reason: String) -> void: replay.append([value,reason]))
	scene.choice_requested.connect(func(id: String) -> void: requests.append(id))
	return {"stage":stage, "scene":scene, "rig":rig, "camera":camera, "adapter":adapter,
		"actors":actors, "state":state, "original":camera.global_transform, "ordinary":ordinary, "replay":replay, "requests":requests}

func tick(f: Dictionary, delta: float) -> void:
	f.scene.update(delta, f.state, f.rig, f.actors, 1, "greenlight", true, f.adapter)
func at(f: Dictionary, time: float) -> void: tick(f, maxf(0, time-float(f.scene.elapsed)))
func confirm(f: Dictionary, id: String) -> void:
	f.state.scene.choice.selected = id
	f.state.scene.choice.response = RESPONSES[id]
	f.state.scene.choice.can_choose = false
	tick(f, 0)
func dispose(f: Dictionary) -> void:
	f.scene.cancel("test_complete")
	f.scene.queue_free()
	f.stage.queue_free()

func run() -> void:
	create_timer(90).timeout.connect(func() -> void: push_error("Ferry decision test timed out"); quit(1))
	root.size = Vector2i(1280,720)
	root.get_node("Network").call("block_for_hud_preview")
	for id: String in ["defend","repair","evacuate"]:
		var f := fixture("plan-"+id)
		expect(EloriaProtocol.decode_campaign(JSON.stringify(f.state).to_utf8_buffer()).get("type") == "campaign", id+" uses a protocol-valid authoritative decision snapshot")
		tick(f, 0)
		at(f, 5.9)
		expect(not f.scene._choice_scroll.visible and not f.scene.choice_context().waiting, "the decision waits for Odo's question at six seconds")
		at(f, 6)
		expect(f.scene._choice_waiting and f.scene._choice_scroll.visible and f.scene._choice_dialog.option_buttons.size() == 3, "the real controller pauses with all three rescue approaches")
		expect(f.scene._dialogue.speaker_label.text == "Odo Fenn" and f.scene._caption.text.contains("How will you help"), "Odo asks the plan question before the controls appear")
		var held_view: Transform3D = f.camera.global_transform
		var source := JSON.stringify(f.state)
		var token: String = f.scene._choice_token()
		(f.scene._choice_dialog.option_buttons[id] as Button).pressed.emit()
		f.scene._on_choice_option(id, token)
		expect(f.requests == [id] and f.scene._choice_pending_at >= 0, "the chosen approach emits once and waits for confirmation")
		expect(JSON.stringify(f.state) == source and str(f.scene._choice_state.selected).is_empty(), "the request cannot select an approach locally")
		tick(f, 2)
		expect(is_equal_approx(f.scene.elapsed, 6) and f.scene._choice_waiting and f.camera.global_transform.is_equal_approx(held_view), "unconfirmed choice holds the same time and steady group camera")
		expect(f.ordinary.is_empty(), "waiting for a choice does not acknowledge the cinematic")
		confirm(f, id)
		expect(f.scene._choice_completed and not f.scene._choice_waiting and not f.scene._choice_scroll.visible, "the authoritative selection resumes the live scene without an extra Continue")
		expect(f.scene._dialogue.speaker_label.text == "Odo Fenn" and f.scene._caption.text == RESPONSES[id], "Odo immediately gives the selected approach's server-authored instruction")
		expect(f.scene.transcript_text().contains("[Recorded choice]") and f.scene.transcript_text().contains(RESPONSES[id]), "the scene account records the actual selected plan and response")
		at(f, 11.9)
		expect(f.scene._caption.text == RESPONSES[id] and f.ordinary.is_empty(), "Odo's response remains through its promised follow-up interval")
		at(f, 12)
		expect(f.scene._caption.text.contains("next work site"), "the scene then names the next physical work site")
		at(f, 16)
		expect(not f.scene.is_active() and f.ordinary == [["plan-"+id,"finished"]] and f.camera.global_transform.is_equal_approx(f.original), "normal plan completion restores play and reports one original presentation result")
		var selected_source := JSON.stringify(f.state)
		expect(f.scene.request_replay(f.state,"greenlight"), "the recorded plan can be replayed after its original viewing")
		tick(f, 0); at(f, 6)
		expect(f.scene.is_replaying() and f.scene._choice_review and f.scene._choice_waiting, "replay pauses for a read-only review of the plan")
		for option: String in f.scene._choice_dialog.option_buttons:
			var button: Button = f.scene._choice_dialog.option_buttons[option]
			expect(button.visible and button.disabled, "replay keeps "+option+" visible without making it selectable")
		expect(f.scene._choice_dialog._content[id].heading.text.begins_with("✓ "), "replay highlights the immutable recorded plan")
		var replay_view: Transform3D = f.camera.global_transform
		tick(f, 20)
		expect(f.scene.elapsed == 6 and f.camera.global_transform.is_equal_approx(replay_view), "replay review holds the steady group frame until Continue")
		if id == "repair":
			for size_and_scale: Array in [[1280,720,1.0],[720,480,1.5]]:
				root.size = Vector2i(size_and_scale[0],size_and_scale[1])
				root.content_scale_factor = size_and_scale[2]
				for _frame: int in range(5): await process_frame
				f.scene._layout_presentation()
				for _frame: int in range(5): await process_frame
				var viewport_box := Rect2(Vector2.ZERO,root.get_visible_rect().size)
				var choice_box: Rect2 = f.scene._choice_scroll.get_global_rect()
				expect(viewport_box.encloses(choice_box), "the integrated decision panel stays on-screen at "+str(size_and_scale))
				for button: Button in f.scene._choice_dialog.option_buttons.values():
					expect(choice_box.encloses(button.get_global_rect()), "every full native option is visible without scrolling at "+str(size_and_scale))
				expect(choice_box.encloses(f.scene._choice_dialog.continue_button.get_global_rect()), "replay Continue is reachable alongside all three options")
			root.size = Vector2i(1280,720)
			root.content_scale_factor = 1.0
		f.scene._on_choice_option("repair", f.scene._choice_token())
		expect(f.requests == [id], "replay cannot send a different approach")
		f.scene._choice_dialog.continue_button.pressed.emit()
		tick(f, 0)
		expect(f.scene._choice_completed and not f.scene._choice_waiting and f.scene._caption.text == RESPONSES[id], "Continue resumes the recorded Odo response")
		at(f, 16)
		expect(f.replay == [["plan-"+id,"finished"]] and f.ordinary.size() == 1 and JSON.stringify(f.state) == selected_source, "replay completion changes no authoritative state and emits no normal acknowledgement")
		dispose(f)
	var helper := fixture("helper-plan", false)
	tick(helper, 0); at(helper, 6)
	expect(helper.scene._choice_waiting and "Waiting for MeasureHuman0" in helper.scene._choice_dialog.status_label.text, "a party helper waits for the named story owner")
	expect(not helper.scene._choice_dialog.continue_button.visible, "the helper has no live Continue bypass")
	helper.scene._on_choice_option("repair", helper.scene._choice_token())
	tick(helper, 25)
	expect(helper.requests.is_empty() and helper.scene.elapsed == 6 and helper.ordinary.is_empty(), "helpers cannot select or time out into a fabricated decision")
	confirm(helper,"repair")
	expect(helper.scene._choice_completed and helper.scene._caption.text == RESPONSES.repair and not helper.scene._choice_scroll.visible, "the owner's confirmed choice immediately resumes the helper's Odo response")
	dispose(helper)
	var empty := fixture("empty-plan")
	tick(empty, 0); at(empty, 6)
	empty.scene.skip(); tick(empty,0.7)
	expect(empty.scene.request_replay(empty.state,"greenlight"), "an originally skipped, unchosen scene can be reviewed")
	tick(empty, 0); at(empty, 6)
	expect("No plan recorded yet" in empty.scene._choice_dialog.status_label.text and empty.scene._choice_dialog.option_buttons.size() == 3, "an empty replay honestly shows all options without inventing a plan")
	for row: Dictionary in empty.scene._choice_dialog._content.values():
		expect(not (row.heading as Label).text.begins_with("✓ "), "an empty replay invents no selected highlight")
	empty.scene._choice_dialog.continue_button.pressed.emit(); tick(empty,0)
	expect(empty.scene._caption.text.contains("No rescue plan was recorded"), "empty replay follow-up preserves the absence of a decision")
	at(empty,16)
	expect(empty.ordinary == [["empty-plan","skipped"]] and empty.requests.is_empty() and empty.replay == [["empty-plan","finished"]], "empty replay cannot choose or acknowledge another gameplay result")
	dispose(empty)
	var retry := fixture("retry-plan")
	tick(retry,0); at(retry,6)
	(retry.scene._choice_dialog.option_buttons.defend as Button).pressed.emit()
	retry.scene.choice_send_failed(); tick(retry,0)
	expect(retry.scene._choice_pending_at < 0 and not (retry.scene._choice_dialog.option_buttons.repair as Button).disabled and "Try again" in retry.scene._choice_dialog.status_label.text, "a send failure visibly releases the real controller for a retry")
	(retry.scene._choice_dialog.option_buttons.repair as Button).pressed.emit()
	expect(retry.requests == ["defend","repair"] and str(retry.state.scene.choice.selected).is_empty(), "retry submits a request while leaving selection to the server")
	var old_token: String = retry.scene._choice_token()
	var old_option: Callable = retry.scene._on_choice_option.bind("evacuate",old_token)
	var old_continue: Callable = retry.scene._on_choice_continue.bind(old_token)
	retry.state.scene.token = "replacement-plan"
	retry.state.run_id = "replacement-run"
	retry.state.scene.choice = decision()
	tick(retry,0); at(retry,6)
	old_option.call_deferred(); old_continue.call_deferred()
	await process_frame
	expect(retry.requests == ["defend","repair"] and retry.scene._choice_waiting and not retry.scene._choice_completed, "queued controls from the replaced scene cannot select or continue the new scene")
	var current_token: String = retry.scene._choice_token()
	retry.scene.cancel("disconnected")
	retry.scene._on_choice_option("evacuate",current_token)
	retry.scene._on_choice_continue(current_token)
	expect(not retry.scene.blocks_input() and not retry.scene._choice_scroll.visible and retry.requests == ["defend","repair"], "cancellation removes the choice and rejects outstanding callbacks")
	expect(retry.camera.global_transform.is_equal_approx(retry.original), "cancelling a decision restores the gameplay camera")
	dispose(retry)
	var late := fixture("long-decision")
	tick(late,0); at(late,6)
	var long_view: Transform3D = late.camera.global_transform
	tick(late,65)
	expect(late.scene.playing and late.scene.elapsed == 6 and late.scene._choice_waiting, "an owner can consider the decision for more than sixty seconds without advancing its timeline")
	expect(late.ordinary.is_empty() and late.replay.is_empty() and late.camera.global_transform.is_equal_approx(long_view), "a long decision wait neither acknowledges the scene nor moves its steady camera")
	(late.scene._choice_dialog.option_buttons.repair as Button).pressed.emit()
	expect(late.requests == ["repair"] and late.ordinary.is_empty(), "a choice after the long wait still awaits the authoritative reply")
	late.state.scene.ack_revision = 2
	confirm(late,"repair")
	expect(late.scene._choice_completed and late.scene._caption.text == RESPONSES.repair and late.scene._dialogue.speaker_label.text == "Odo Fenn", "a renewed acknowledgement revision plays the selected Odo response in the same run and scene")
	expect(late.camera.global_transform.is_equal_approx(long_view) and late.ordinary.is_empty() and str(late.scene._ack_identity).ends_with(":2"), "renewing the active barrier preserves the steady camera and emits no premature presentation result")
	at(late,11.9)
	expect(late.scene._caption.text == RESPONSES.repair and late.ordinary.is_empty(), "the renewed scene retains the complete response interval before acknowledging")
	at(late,16); tick(late,0)
	expect(late.ordinary == [["long-decision","finished"]] and late.replay.is_empty(), "the renewed long-decision scene acknowledges exactly once at its normal end")
	dispose(late)
	var handled := fixture("helper-renewed",false)
	tick(handled,0); at(handled,6)
	handled.scene.skip(); tick(handled,0.7)
	expect(handled.ordinary == [["helper-renewed","skipped"]] and not handled.scene.is_active(), "the helper has already handled the original scene token before the owner's delayed selection")
	tick(handled,65)
	expect(handled.ordinary.size() == 1 and handled.requests.is_empty(), "an unchanged expired-barrier snapshot does not replay or duplicate the helper's acknowledgement")
	handled.state.scene.ack_revision = 2
	confirm(handled,"repair")
	expect(handled.ordinary == [["helper-renewed","skipped"],["helper-renewed","already_seen"]], "a renewed revision requires one fresh already-seen acknowledgement from the handled helper")
	expect(not handled.scene.is_active() and not handled.scene._choice_scroll.visible and handled.requests.is_empty() and handled.replay.is_empty(), "the helper's renewed acknowledgement opens no replay or owner choice")
	tick(handled,0); tick(handled,1)
	expect(handled.ordinary.size() == 2 and handled.requests.is_empty() and handled.replay.is_empty(), "repeated renewed snapshots cannot duplicate the already-seen acknowledgement")
	dispose(handled)
	await process_frame; await process_frame
	print("ferry decision: ", checks, " checks; ", failures, " failures")
	quit(1 if failures else 0)
