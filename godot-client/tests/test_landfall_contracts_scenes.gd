extends "res://tests/test_campaign_scene_recovery.gd"
const Contracts := preload("res://tests/test_landfall_contracts.gd")

func contract_fixture(skill: String, scene_id: String) -> Dictionary:
	var f := fixture()
	f.scene.set_auto_dialogue(false,false)
	f.state = Contracts.snapshot(Contracts.board_state())
	f.state.key = skill
	var row := Contracts.offer(skill)
	f.state.run_id = str(row.id); f.state.contracts.current = row
	f.state.contracts.accepted = [row]; f.state.contracts.tracked_id = str(row.id)
	f.state.actors = {"mentor":20,"worker":20,"protagonist":1,"recipient":1}
	f.state.scene = {"id":scene_id,"token":skill+":"+scene_id,"requires_ack":true,"variant":skill,"actors":f.state.actors.duplicate(true)}
	return f

func run() -> void:
	create_timer(90).timeout.connect(func() -> void:push_error("Contracts scenes timed out");quit(1))
	root.get_node("Network").block_for_hud_preview()
	for skill: String in EloriaProtocol.ContractsProtocol.SKILLS:
		for scene_id: String in ["contracts.brief","contracts.entry","contracts.report"]:
			var f := contract_fixture(skill,scene_id)
			var before: Transform3D = f.rig.camera.global_transform
			var original := JSON.stringify(f.state)
			tick(f,0.1)
			expect(f.scene.playing and f.scene._dialogue.portrait_visible() and not f.scene._caption.text.is_empty(),skill+" "+scene_id+" opens its portrait dialogue")
			expect(f.scene._uses_gameplay_camera() and f.rig.camera.global_transform.is_equal_approx(before),skill+" preserves the established gameplay camera")
			expect(f.scene._line_continue.visible,skill+" Continue is available as soon as dialogue appears")
			tick(f,20)
			expect(f.scene.is_dialogue_waiting() and f.events.finished.is_empty(),skill+" does not auto-consume its manual conversation")
			f.scene.continue_dialogue(); tick(f,0)
			expect(f.events.finished.size() == 1 and not f.scene.blocks_input(),skill+" acknowledges once and returns to the same game view")
			expect(f.scene.request_replay(f.state,"landfall"),skill+" supports the existing read-only replay")
			tick(f,0.1); f.scene.continue_dialogue(); tick(f,0)
			expect(f.events.finished.size() == 1 and f.events.replay.size() == 1 and JSON.stringify(f.state) == original,skill+" replay cannot emit another live completion or alter proof")
			dispose(f); await process_frame
	for template: String in EloriaProtocol.ContractsProtocol.TEMPLATES:
		var binding: Array = EloriaProtocol.ContractsProtocol.TEMPLATES[template]
		if int(binding[1]) < 1100: continue
		for scene_id: String in ["contracts.brief","contracts.entry"]:
			var f := contract_fixture(str(binding[0]),scene_id)
			f.state.contracts.current = Contracts.offer(str(binding[0]))
			f.state.contracts.current.template_id = template; f.state.contracts.current.quest_id = int(binding[1])
			f.state.scene.variant = template
			expect(EloriaProtocol.decode_campaign(JSON.stringify(f.state).to_utf8_buffer()).type == "campaign",template+" admits only its declared discipline and journal binding")
			var before: Transform3D = f.rig.camera.global_transform
			tick(f,0.1)
			expect(f.scene.playing and f.scene._dialogue.portrait_visible() and not f.scene._caption.text.is_empty(),template+" has its own brief and entry portrait dialogue")
			expect(f.rig.camera.global_transform.is_equal_approx(before) and f.scene._line_continue.visible,template+" keeps the current view and immediate Continue")
			f.scene.continue_dialogue(); tick(f,0)
			expect(f.events.finished.size() == 1,template+" acknowledges its manual scene once")
			dispose(f); await process_frame
	for region: String in ["pinebrow", "ravenhead", "whitepeak"]:
		for scene_id: String in ["contracts.brief", "contracts.entry"]:
			var f := contract_fixture("melee",scene_id)
			f.state.map = region
			f.state.contracts.current.journey = {"version":3,"map":region,"tile":[128,128],"label":"Relief route",
				"description":"Take the relief crew along the orchard road and protect their crossing.",
				"objective":"I will lead the crew along the orchard road and protect the crossing."}
			f.nodes[1].global_position = Vector3(345,0,781); f.nodes[1].server_target = f.nodes[1].global_position
			f.nodes[20].global_position = Vector3(346,0,781); f.nodes[20].server_target = f.nodes[20].global_position
			f.rig.camera.global_position = Vector3(345,12,793); f.rig.camera.look_at(f.nodes[1].global_position)
			var before: Transform3D = f.rig.camera.global_transform
			var original := JSON.stringify(f.state)
			var expected := str(f.state.contracts.current.journey.description if scene_id == "contracts.brief" else f.state.contracts.current.journey.objective)
			tick(f,0.1,region)
			expect(f.scene.playing and f.scene._dialogue.portrait_visible() and expected in f.scene._caption.text,
				region+" uses the frozen route's existing single portrait line")
			expect(f.rig.camera.global_transform.is_equal_approx(before) and f.scene._line_continue.visible,
				region+" opens the short briefing at the player's current camera with immediate Continue")
			f.scene.continue_dialogue(); tick(f,0,region)
			expect(f.events.finished.size() == 1 and f.rig.camera.global_transform.is_equal_approx(before),region+" finishes without a camera recenter")
			expect(f.scene.request_replay(f.state,region),region+" supports the same route briefing on replay")
			tick(f,0.1,region)
			expect(expected in f.scene._caption.text and f.rig.camera.global_transform.is_equal_approx(before),region+" replay keeps the regional text and current framing")
			f.scene.continue_dialogue(); tick(f,0,region)
			expect(f.events.finished.size() == 1 and f.events.replay.size() == 1 and JSON.stringify(f.state) == original,region+" replay cannot change accepted work")
			dispose(f); await process_frame
	var pause := contract_fixture("melee","contracts.pause")
	pause.state.scene.choice = {"id":"contract_retry","title":"What next?","owner":"You","owner_is_you":true,"can_choose":true,"selected":"","response":"",
		"options":[{"id":"resume","label":"Continue","detail":"Keep health and progress."},{"id":"leave","label":"Leave for now","detail":"Return later."}]}
	tick(pause,0.1); pause.scene.skip(); tick(pause,0)
	expect(pause.scene._choice_waiting and pause.events.finished.is_empty(),"Return to Play stops at the unanswered contract decision")
	dispose(pause); await process_frame
	pause = contract_fixture("melee","contracts.pause")
	pause.state.scene.choice = {"id":"contract_retry","title":"What next?","owner":"You","owner_is_you":true,"can_choose":true,"selected":"","response":"",
		"options":[{"id":"retry","label":"Retry this stage","detail":"Keep completed stages."},{"id":"leave","label":"Leave for now","detail":"Return later."}]}
	tick(pause,0.1); pause.scene.skip(); tick(pause,0)
	expect(pause.scene._choice_waiting and pause.events.finished.is_empty(),"a failed contract stage offers its actual retry/leave decision")
	var app: Node = root.get_node("AppState"); app.authenticated = true
	var main: Node = load("res://src/app/main.gd").new()
	var hud: Control = load("res://src/ui/campaign_hud.gd").new(); root.add_child(hud)
	main.campaign_scene = pause.scene; main.campaign_hud = hud
	app.campaign = {"kind":"shelves","run_id":"retained-story"}; app.contracts_board = {"reset_skills":["ranging"]}
	hud.set_replay_available(true)
	var before: Transform3D = pause.rig.camera.global_transform
	main._on_state_changed(&"contracts_reset")
	expect(pause.scene._choice_waiting and hud._replay_available and before.is_equal_approx(pause.rig.camera.global_transform),"an unrelated reset preserves the live question, camera and Replay state")
	app.campaign = {}; app.contracts_board.reset_skills = ["melee"]
	main._on_state_changed(&"contracts_reset")
	expect(not pause.scene.blocks_input() and not hud._replay_available and not pause.scene._handled.has(identity(pause)),"a matching reset releases the pending decision without marking it completed")
	expect(pause.events.finished[-1][1] == "contracts_reset" and before.is_equal_approx(pause.rig.camera.global_transform),"reset cancellation sends no successful completion and preserves the current gameplay view")
	main.free(); hud.queue_free()
	dispose(pause); await process_frame
	var path := OS.get_environment("RL_CONTRACTS_NATIVE")
	if not path.is_empty():
		var records: Array = JSON.parse_string(FileAccess.get_file_as_string(path))
		var missions: Dictionary = {}
		var rotation := false
		for row: Dictionary in records:
			var dto: Dictionary = row.get("snapshot",row)
			rotation = rotation or str(row.get("label", "")).begins_with("journey.board.")
			for offer: Dictionary in (dto.get("contracts", {}) as Dictionary).get("offers", []):
				if offer.has("journey"):
					missions[str(offer.template_id)+":"+str(offer.route)] = offer
			if str((dto.get("scene",{}) as Dictionary).get("id","")).is_empty(): continue
			var decoded := EloriaProtocol.decode_campaign(JSON.stringify(dto).to_utf8_buffer())
			expect(decoded.type == "campaign","native contract scene packet decodes: "+str(decoded.get("error","")))
			if decoded.type != "campaign":continue
			var f := contract_fixture(str(dto.key),str(dto.scene.id))
			f.state = dto.duplicate(true); f.state.actors = {"mentor":20,"worker":20,"protagonist":1,"recipient":1}; f.state.scene.actors = f.state.actors.duplicate(true)
			var native_camera_before: Transform3D = f.rig.camera.global_transform
			tick(f,0.1,str(dto.map))
			expect(f.scene.playing and not f.scene._caption.text.is_empty(),"actual native contract state selects its authored portrait scene")
			var journey: Dictionary = (dto.contracts.get("current",{}) as Dictionary).get("journey",{})
			if not journey.is_empty() and str(dto.scene.id) in ["contracts.brief","contracts.entry"]:
				var expected := str(journey.description if str(dto.scene.id) == "contracts.brief" else journey.objective)
				expect(expected in f.scene._caption.text and f.scene._dialogue.portrait_visible(),"actual native itinerary supplies its single portrait briefing line")
				expect(f.rig.camera.global_transform.is_equal_approx(native_camera_before),"actual regional scene keeps the established gameplay view")
			dispose(f); await process_frame
		if rotation: expect(missions.size() == 40,"the native board rotation supplies all forty frozen mission variants")
		# These are actual offer rows presented through the scene controller,
		# rather than forty additional server encounter playthroughs.
		for mission: String in missions:
			var offer: Dictionary = missions[mission]
			for scene_id: String in ["contracts.brief", "contracts.entry"]:
				var f := contract_fixture(str(offer.skill), scene_id)
				var region := str(offer.journey.map)
				f.state.map = region; f.state.run_id = str(offer.id)
				f.state.contracts.current = offer.duplicate(true)
				f.state.contracts.accepted = [f.state.contracts.current]
				f.state.contracts.tracked_id = str(offer.id)
				f.state.scene.variant = str(offer.template_id)
				f.nodes[1].global_position = Vector3(345,0,781); f.nodes[1].server_target = f.nodes[1].global_position
				f.nodes[20].global_position = Vector3(346,0,781); f.nodes[20].server_target = f.nodes[20].global_position
				f.rig.camera.global_position = Vector3(345,12,793); f.rig.camera.look_at(f.nodes[1].global_position)
				var mission_camera: Transform3D = f.rig.camera.global_transform
				var original := JSON.stringify(f.state)
				var expected := str(offer.journey.description if scene_id == "contracts.brief" else offer.journey.objective)
				tick(f,0.1,region)
				expect(f.scene.playing and f.scene._dialogue.portrait_visible() and expected in f.scene._caption.text,mission+" presents its frozen "+scene_id+" line")
				expect(f.rig.camera.global_transform.is_equal_approx(mission_camera) and f.scene._line_continue.visible,mission+" keeps the player's view and immediate Continue")
				f.scene.continue_dialogue(); tick(f,0,region)
				expect(f.events.finished.size() == 1 and f.rig.camera.global_transform.is_equal_approx(mission_camera),mission+" finishes without recentering")
				expect(f.scene.request_replay(f.state,region),mission+" can replay its frozen mission line")
				tick(f,0.1,region)
				expect(expected in f.scene._caption.text and f.rig.camera.global_transform.is_equal_approx(mission_camera),mission+" replay retains its text and current camera")
				f.scene.continue_dialogue(); tick(f,0,region)
				expect(f.events.finished.size() == 1 and f.events.replay.size() == 1 and JSON.stringify(f.state) == original,mission+" replay cannot alter accepted work")
				dispose(f); await process_frame
	print("Landfall contracts scenes: ",checks," checks; ",failures," failures")
	quit(1 if failures else 0)
