extends "res://tests/test_rescue_player_camera_return.gd"
## Help starts ordinary combat in the final tackle view. Watch still uses its
## existing dialogue handoff and restores the local player's chosen viewport.

func run() -> void:
	root.get_node("Network").block_for_hud_preview()
	var definitions:=Scene.scene_definitions()
	expect(definitions["measure.rescue.abduction"].exit_camera=={"mode":"keep_scene","when":"help"},
		"only Help adopts the established combat view")
	for helper:bool in [false,true]:
		for finish:String in ["finished","skipped"]:
			var f:=fixture("abduction",helper)
			f.scene._variant="help"
			f.scene._choice_state={"selected":"help"}
			f.state.scene.variant="help"
			f.scene.elapsed=f.scene._duration()
			f.scene._camera_entry_elapsed=f.scene.elapsed
			f.scene._apply_camera()
			var held:Transform3D=f.rig.camera.global_transform
			var lens:float=f.rig.camera.fov
			f.scene.elapsed=f.scene._duration()-0.5
			f.scene._apply_camera()
			expect(f.rig.camera.global_transform.is_equal_approx(held),
				"Help's final half-second stays in the established scene instead of beginning an exit pan")
			if finish=="skipped":
				f.scene.elapsed=43;f.scene._apply_camera()
			else:
				f.scene.elapsed=f.scene._duration();f.scene._apply_camera()
			var before:=JSON.stringify(f.state)
			f.scene.cancel(finish)
			var label:="Help "+finish+(" helper" if helper else " owner")
			expect(not f.scene.blocks_input() and not f.scene.playing and f.scene._scene_handoff.is_empty(),
				label+" ends the film and returns normal gameplay input")
			expect(JSON.stringify(f.state)==before,"camera adoption supplies no invented combat progress")
			expect(f.rig.camera.global_transform.is_equal_approx(held) and is_equal_approx(f.rig.camera.fov,lens),
				label+" retains the final shot and lens instead of panning back")
			expect(not held.is_equal_approx(f.original) and is_equal_approx(lens,46),
				label+" keeps the authored scene framing rather than the prior player preset")
			f.rig.set_focus(f.actor.global_position)
			expect(f.rig.camera.global_transform.is_equal_approx(held),
				label+" survives the first ordinary player-follow update without a jump")
			var old:Vector3=f.rig.camera.global_position
			var movement:=Vector3(2,0,1)
			f.actor.position+=movement;f.actor.server_target=f.actor.position
			f.rig.set_focus(f.actor.position)
			expect(f.rig.camera.global_position.is_equal_approx(old+movement),
				label+" follows actual player movement in the adopted view")
			var yaw:float=f.rig.yaw_degrees
			f.rig.handle_keyboard(Vector2(1,0),0.05)
			expect(not is_equal_approx(f.rig.yaw_degrees,yaw),
				label+" leaves normal camera orbit usable during combat")
			var gameplay:Transform3D=f.rig.camera.global_transform
			f.state.scene={"id":"measure.rescue.commitment","token":"after-real-combat",
				"variant":"help","actors":f.state.actors,"requires_ack":true}
			tick(f,0)
			expect(f.scene.playing and f.rig.camera.global_transform.is_equal_approx(gameplay)
				and f.scene.elapsed==0 and not f.scene._choice_waiting,
				label+" lets the later conversation inherit the actual combat viewport and begin at its introduction")
			dispose(f)
			await process_frame
	var replay:=fixture("abduction")
	replay.scene._variant="help";replay.scene._choice_state={"selected":"help"}
	replay.scene._replaying=true
	expect(not replay.scene._keeps_exit_camera(),"read-only Help replay does not replace the gameplay viewport")
	dispose(replay)
	await process_frame
	print("Rescue Help combat camera: %d checks; %d failures"%[checks,failures])
	quit(0 if failures==0 else 1)
