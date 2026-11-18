extends "res://tests/test_quest_first_pass_cinematics.gd"
## Real supply definitions must make native answers and party waits intelligible.

func choice(id: String, selected := "", response := "") -> Dictionary:
	var ids: Array=EloriaProtocol.SHELVES_CHOICE_OPTIONS[id]
	var options: Array=[]
	for option: String in ids: options.append({"id":option,"label":"Approach "+option,"detail":"Test consequence."})
	return {"id":id,"title":"Choose","selected":selected,"response":response,
		"owner":"Aster","owner_is_you":true,"can_choose":selected.is_empty(),"options":options}

func authored(id: String, answer: Dictionary) -> Dictionary:
	var f:=fixture(); f.scene.cancel("replace_fixture")
	f.scene._definitions=Scene.scene_definitions()
	f.scene._definition=f.scene._definitions[id].duplicate(true)
	f.scene._scene_id=id; f.scene._run="outcome"; f.scene._token="answer"; f.scene._map="landfall_town"
	f.scene._choice_state=answer.duplicate(true)
	var bindings: Dictionary={"mentor":2,"worker":2,"recipient":1,"protagonist":1}
	f.scene._start(f.rig,f.rig.camera,f.player,f.nodes,bindings)
	f.state={"active":true,"kind":"shelves","run_id":"outcome","map":"landfall_town",
		"scene":{"id":id,"token":"answer","requires_ack":true,"actors":bindings,"choice":answer.duplicate(true)}}
	f.acks.clear()
	return f

func run() -> void:
	root.get_node("Network").block_for_hud_preview()
	for kind: String in ["growers","fire","water"]:
		var identity: String={"growers":"shelves_patrol_retry","fire":"shelves_fire_retry","water":"shelves_water_retry"}[kind]
		var f:=authored("measure.shelves."+kind+".retry",choice(identity))
		tick(f,0)
		expect(f.scene._choice_waiting and f.scene._dialogue.portrait_visible(),kind+" retry choices retain the local recipient's headshot")
		var requests: Array=[]
		f.scene.choice_requested.connect(func(id: String) -> void: requests.append(id))
		f.scene._choice_dialog.option_buttons.retry.pressed.emit()
		expect(requests==["retry"] and str(f.state.scene.choice.selected).is_empty(),"retry asks the server without choosing locally")
		f.state.scene.choice.selected="retry"; f.state.scene.choice.can_choose=false
		f.state.scene.choice.response="Regroup and protect the next load."
		tick(f,0)
		expect(f.scene._choice_completed and f.scene._dialogue.portrait_visible()
			and f.scene._caption.text==f.state.scene.choice.response,kind+" retry follow-up retains the same real headshot")
		dispose(f)
	for site: String in ["quarry","coal"]:
		var f:=authored("measure.shelves.fire.entry_"+site,choice("shelves_fire_"+site))
		f.scene.skip(); tick(f,0)
		expect(f.scene._choice_waiting and f.scene._dialogue.portrait_visible()
			and f.scene._dialogue._actor.get_ref()==f.player,"Fire "+site+" plans show the current recipient's choice portrait")
		dispose(f)

	for present: bool in [false,true]:
		var f:=authored("measure.shelves.fire.entry_coal",choice("shelves_fire_coal"))
		f.state.scene.choice.owner_is_you=false; f.state.scene.choice.can_choose=false
		f.state.party={"owner":"Aster","members":[{"name":"Aster","role":"owner","online":true,"present":present}]}
		f.scene.skip(); tick(f,0)
		var status: String=f.scene._choice_dialog.status_label.text
		expect("Waiting for Aster" in status and ("join" in status if not present else "choose" in status),
			"helper waiting explains whether the owner must return to the conversation or choose")
		expect(not f.scene._choice_dialog.continue_button.visible and f.acks.is_empty(),"helper explanation grants no decision or acknowledgement bypass")
		dispose(f)
	var f:=authored("measure.shelves.water.entry_water_barge",choice("shelves_water_route"))
	f.state.scene.choice.owner_is_you=false; f.state.scene.choice.can_choose=false
	f.state.party={"waiting_for_owner":true}
	f.scene.skip(); tick(f,0)
	expect("Aster to return" in f.scene._choice_dialog.status_label.text,"the explicit owner-away flag has a reason in the cinematic")
	dispose(f)

	f=authored("measure.shelves.fire.entry_coal",choice("shelves_fire_coal","lift"))
	f.scene.set_auto_dialogue(true,false); tick(f,20)
	expect("Approach lift" in f.scene._caption.text and not "ready to decide" in f.scene._caption.text,
		"a recorded legacy answer without a reply is summarized instead of posing the old question again")
	expect(f.scene._dialogue.portrait_visible() and f.scene._dialogue.speaker_label.text=="Aster",
		"the missing-reply summary is attributed to the player's record rather than invented NPC speech")
	dispose(f)

	f=authored("measure.shelves.fire.entry_coal",choice("shelves_fire_coal"))
	f.scene.cancel("finished"); f.state.scene.requires_ack=false
	var before:=JSON.stringify(f.state)
	expect(f.scene.request_replay(f.state,"landfall_town"),"a legacy unanswered scene can be reviewed")
	tick(f,0); f.scene.skip(); tick(f,0)
	f.scene._choice_dialog.continue_button.pressed.emit(); tick(f,0)
	expect("No answer was recorded" in f.scene._caption.text and not "ready to decide" in f.scene._caption.text,
		"an unanswered replay states the missing record without obsolete gameplay directions")
	expect(JSON.stringify(f.state)==before,"an honest replay summary does not invent a selected answer")
	dispose(f)

	f=authored("measure.shelves.review",choice("shelves_cape","keeper","The cape is yours."))
	f.scene.set_auto_dialogue(true,false); tick(f,16)
	var held: Transform3D=f.rig.camera.global_transform
	expect(f.scene.continue_dialogue(),"the confirmed cape outcome offers Continue immediately")
	tick(f,0)
	expect(not f.scene._scene_handoff.is_empty() and f.acks==[["answer","finished"]],
		"one Continue from the cape response reaches the enriched gift without a repeated announcement")
	f.state.scene={"id":"measure.shelves.enriched","token":"gift","requires_ack":true,
		"actors":{"mentor":2,"recipient":1},"choice":choice("shelves_enriched")}
	tick(f,0)
	expect("one enriched essence" in f.scene._caption.text and f.rig.camera.global_transform.is_equal_approx(held),
		"Ilka introduces the next gift once in the established portrait view")
	dispose(f)

	f=authored("measure.shelves.gear",choice("shelves_gear","wand","The wand is yours."))
	f.scene.set_auto_dialogue(true,false); tick(f,16); tick(f,18)
	expect(not "return to The True Note" in f.scene._caption.text,"a reward at Ilka's shop does not send the player back to the same conversation")
	dispose(f)
	await process_frame
	print("Quest choice outcomes: %d checks; %d failures"%[checks,failures])
	quit(1 if failures else 0)
