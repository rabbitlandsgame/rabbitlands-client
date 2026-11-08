extends "res://tests/test_campaign_scene_recovery.gd"
## Real dialogue controls, authoritative choice snapshots and delayed native actions.

func decision(f: Dictionary, name: String) -> void:
	var ids := {"abduction":"rescue_response","commitment":"rescue_accept","resolved":"rescue_reward"}
	var options := {"abduction":["help","watch"],"commitment":["accept","defer"],"resolved":["sword","bow","wand"]}
	f.state.scene.id="measure.rescue."+name
	f.scene._scene_id=f.state.scene.id
	f.scene._definition=Scene.scene_definitions()[f.state.scene.id].duplicate(true)
	if name=="resolved":
		f.scene._actors.recipient=f.nodes[1]
		f.scene._posts.recipient=f.scene._posts.protagonist
	f.state.scene.choice.id=ids[name]
	f.state.scene.choice.options=[]
	for option: String in options[name]:
		f.state.scene.choice.options.append({"id":option,"label":option.capitalize(),"detail":"Choose this approach."})

func run() -> void:
	create_timer(45).timeout.connect(func() -> void: push_error("Skip-to-decision checks timed out");quit(1))
	root.get_node("Network").call("block_for_hud_preview")
	for name: String in ["abduction","commitment","resolved"]:
		var f:=fixture();tick(f,1)
		decision(f,name)
		var before:=JSON.stringify(f.state)
		f.scene._skip.pressed.emit();tick(f)
		expect(f.scene.playing and f.scene._choice_waiting and not f.scene._choice_review,name+" skips directly to its live question")
		expect(is_equal_approx(f.scene.elapsed,float(f.scene._definition.choice_at)),name+" stops at its exact authored decision point")
		expect(f.scene._dialogue.portrait_visible() and f.scene._choice_dialog.option_buttons.size()==f.state.scene.choice.options.size(),name+" retains the portrait dialogue and every answer")
		f.scene.skip();f.scene.skip();tick(f)
		expect(f.events.finished.is_empty() and f.events.choices.is_empty() and JSON.stringify(f.state)==before,name+" repeated Return never answers or acknowledges an unanswered question")
		dispose(f);await process_frame

	var rewarded:=fixture();tick(rewarded,1);decision(rewarded,"resolved")
	rewarded.scene.skip();tick(rewarded)
	rewarded.scene._choice_dialog.option_buttons.sword.pressed.emit()
	rewarded.state.scene.choice.selected="sword";rewarded.state.scene.choice.can_choose=false
	rewarded.state.scene.choice.response="The sword is yours. May it guard you as you guarded Liora."
	tick(rewarded)
	for moment:float in [31.0,41.9,42.0,45.0,50.9]:
		rewarded.scene.elapsed=moment;rewarded.scene._update_caption()
		expect(rewarded.scene._caption.text==rewarded.state.scene.choice.response and not rewarded.scene._choice_waiting,
			"the confirmed weapon remains acknowledged without another choice prompt at "+str(moment))
	rewarded.scene.elapsed=51;rewarded.scene._update_caption()
	expect(rewarded.scene._caption.text.contains("always be welcome") and rewarded.events.choices==["sword"],"the single weapon selection proceeds directly to Elen's farewell")
	dispose(rewarded);await process_frame

	var f:=fixture();tick(f,1);f.scene.skip();tick(f)
	f.scene._choice_dialog.option_buttons.accept.pressed.emit()
	f.scene.skip();tick(f)
	expect(f.events.choices==["accept"] and f.scene._choice_waiting and f.scene._choice_pending_at>=0,"Return preserves a pending native selection without resending it")
	f.state.scene.choice.selected="accept";f.state.scene.choice.can_choose=false
	f.state.scene.choice.response="Follow me. We will bring her home."
	tick(f)
	expect(f.scene._choice_completed and f.scene._caption.text.contains("We will bring her home"),"server-confirmed answers resume the NPC's follow-up instructions")
	dispose(f);await process_frame

	f=fixture();tick(f,1)
	f.state.scene.choice.owner_is_you=false;f.state.scene.choice.can_choose=false
	f.scene.skip();tick(f)
	f.scene._choice_dialog.option_buttons.accept.pressed.emit()
	expect(f.scene._choice_waiting and f.events.choices.is_empty(),"party helpers can skip speech but cannot answer for the owner")
	dispose(f);await process_frame

	f=fixture();tick(f,1)
	f.scene.cancel("finished");f.state.scene.requires_ack=false
	f.state.scene.choice.selected="accept";f.state.scene.choice.can_choose=false
	f.state.scene.choice.response="Follow me."
	expect(f.scene.request_replay(f.state,"landfall"),"the recorded native question can be replayed")
	f.events.finished.clear()
	tick(f,1)
	f.scene.skip();tick(f)
	expect(f.scene._choice_waiting and f.scene._choice_review and f.scene._choice_dialog._content.accept.heading.text.begins_with("✓ "),"replay skips to all recorded answers with the selected one highlighted")
	f.scene._choice_dialog.option_buttons.defer.pressed.emit()
	expect(f.events.choices.is_empty() and f.events.finished.is_empty(),"replay seeking remains read-only")
	dispose(f);await process_frame

	f=fixture();tick(f,1)
	f.state.scene.id="measure.rescue.captive";f.scene._scene_id=f.state.scene.id
	f.scene._definition=Scene.scene_definitions()[f.state.scene.id].duplicate(true)
	f.state.scene.erase("choice")
	f.state.scene.inspection={"id":"rescue_family","status":"pending","can_start":true,
		"actor_id":20,"object_id":64003,"path":[[268,128],[269,128]],"approach":[269,128]}
	var actions:Array=[]
	f.scene.inspection_requested.connect(func(action:String) -> void: actions.append(action))
	tick(f,0);f.scene.skip();tick(f)
	expect(actions==["start"] and f.scene.elapsed==28 and f.scene._seeking_decision,"skipping the rescue starts the actual escort and waits at its native barrier")
	for i in 3: f.scene.skip();tick(f)
	expect(actions==["start"] and f.events.finished.is_empty(),"repeated skipping cannot fake escort completion or cancel the required action")
	f.state.scene.inspection.status="complete";f.state.scene.inspection.can_start=false
	tick(f);tick(f,0.6)
	expect(f.events.finished.size()==1 and f.scene._exit_black.color.a==1,"the rescue acknowledges once under black after native escort confirmation")
	var reward:Dictionary=Scene.scene_definitions()["measure.rescue.resolved"].duplicate(true)
	reward.required_actors=["mother","protagonist"]
	f.scene._definitions={"measure.rescue.resolved":reward}
	f.state.scene={"id":"measure.rescue.resolved","token":"reward-question","requires_ack":true,
		"actors":{"mother":20,"protagonist":1},"choice":{"id":"rescue_reward","title":"Choose your reward",
			"owner":"Aster","owner_is_you":true,"can_choose":true,"selected":"","response":"",
			"options":[{"id":"sword","label":"Sword","detail":"Melee"},{"id":"bow","label":"Bow","detail":"Ranging"},{"id":"wand","label":"Wand","detail":"Magic"}]}}
	f.state.anchors.reward=[268,128]
	tick(f);tick(f,0.6)
	expect(f.scene.playing and f.scene._choice_waiting and f.scene._choice_dialog.option_buttons.size()==3,"one skip carries seamlessly through the escort into the next reward question")
	expect(f.events.finished.size()==1 and f.events.choices.is_empty(),"the chained reward still requires an explicit player answer")
	dispose(f);await process_frame
	f=fixture();tick(f,1)
	f.scene._definition=Scene.scene_definitions()["measure.rescue.captive"].duplicate(true)
	f.state.scene.erase("choice")
	f.state.scene.inspection={"id":"rescue_family","status":"blocked","can_start":true,
		"actor_id":20,"object_id":64003,"path":[[268,128],[269,128]],"approach":[269,128]}
	tick(f,0);f.scene._inspection_error="The path is blocked. Return to play to help."
	f.scene.skip();tick(f,0.7)
	expect(not f.scene.blocks_input() and f.scene._scene_handoff.is_empty(),"a blocked required action can return to gameplay without waiting in black for an impossible next scene")
	dispose(f);await process_frame
	print("Skip-to-decision checks: ",checks,"; failures: ",failures)
	quit(1 if failures else 0)
