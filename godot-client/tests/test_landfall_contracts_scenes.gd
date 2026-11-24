extends "res://tests/test_campaign_scene_recovery.gd"
const Contracts := preload("res://tests/test_landfall_contracts.gd")

func contract_fixture(skill: String, scene_id: String) -> Dictionary:
	var f := fixture()
	f.scene.set_auto_dialogue(false,false)
	f.state = Contracts.snapshot(Contracts.board_state())
	f.state.key = skill
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
	dispose(pause); await process_frame
	var path := OS.get_environment("RL_CONTRACTS_NATIVE")
	if not path.is_empty():
		var records: Array = JSON.parse_string(FileAccess.get_file_as_string(path))
		for row: Dictionary in records:
			var dto: Dictionary = row.get("snapshot",row)
			if str((dto.get("scene",{}) as Dictionary).get("id","")).is_empty(): continue
			var decoded := EloriaProtocol.decode_campaign(JSON.stringify(dto).to_utf8_buffer())
			expect(decoded.type == "campaign","native contract scene packet decodes: "+str(decoded.get("error","")))
			if decoded.type != "campaign":continue
			var f := contract_fixture(str(dto.key),str(dto.scene.id))
			f.state = dto.duplicate(true); f.state.actors = {"mentor":20,"worker":20,"protagonist":1,"recipient":1}; f.state.scene.actors = f.state.actors.duplicate(true)
			tick(f,0.1,str(dto.map))
			expect(f.scene.playing and not f.scene._caption.text.is_empty(),"actual native contract state selects its authored portrait scene")
			dispose(f); await process_frame
	print("Landfall contracts scenes: ",checks," checks; ",failures," failures")
	quit(1 if failures else 0)
