extends "res://tests/test_quest_first_pass_cinematics.gd"
## Real Life report/raid definitions must share one view across delayed rewards.

func run() -> void:
	root.get_node("Network").block_for_hud_preview()
	var definitions := Scene.scene_definitions()
	var f := fixture()
	f.scene.cancel("replace_fixture")
	f.scene._definition = definitions["measure.shelves.growers.report_crew"].duplicate(true)
	f.scene._definitions = definitions
	f.scene._scene_id = "measure.shelves.growers.report_crew"
	f.scene._run = "crew-report"; f.scene._token = "report"
	var bindings := {"mentor":2,"recipient":1,"protagonist":1}
	f.scene._start(f.rig,f.rig.camera,f.player,f.nodes,bindings)
	f.acks.clear()
	var held: Transform3D = f.rig.camera.global_transform
	expect(f.scene._dialogue._portrait_frame.visible and f.scene._line_continue.visible,
		"Ilka's consolidated report has its portrait and immediate Continue")
	expect(f.scene._dialogue.body_label.text.contains("Old Warren"),
		"the report preserves the trail leading into the next assignment")
	expect(f.scene.continue_dialogue() and f.acks.size()==1,
		"one Continue finishes the same-speaker report and requests its earned reward")
	f.state = {"active":true,"kind":"shelves","run_id":"crew-report","map":"landfall_town","scene":{}}
	for _i: int in 10: tick(f,0.1)
	expect(f.scene.blocks_input() and f.scene._dialogue.visible and not f.scene.playing,
		"the completed report waits in its portrait frame for the raid assignment")
	expect(f.rig.camera.global_transform.is_equal_approx(held),
		"a delayed assignment does not flash or reset the player's viewport")
	f.state.run_id = "warren-raid"
	f.state.scene = {"id":"measure.shelves.growers.brief_raid","token":"brief","requires_ack":true,"actors":bindings}
	tick(f,0.1,false)
	expect(f.scene.blocks_input() and f.scene._dialogue.visible,
		"a pending actor barrier preserves the held report while the successor arrives")
	tick(f)
	expect(f.scene.playing and f.scene._scene_id=="measure.shelves.growers.brief_raid",
		"the actual raid briefing begins from the report's explicit successor")
	expect(f.scene._dialogue.body_label.text.contains("Grask") and f.scene._dialogue._portrait_frame.visible,
		"Ilka introduces Grask in the same portrait dialogue")
	expect(f.rig.camera.global_transform.is_equal_approx(held) and f.acks.size()==1,
		"the next assignment inherits the settled view without another acknowledgement")
	f.scene.continue_dialogue()
	expect(not f.scene.blocks_input() and f.acks.size()==2,
		"the final briefing returns control once after its own Continue")
	dispose(f)
	for _i: int in 3: await process_frame
	print("Quest scene quality: %d checks; %d failures" % [checks,failures])
	quit(1 if failures else 0)
