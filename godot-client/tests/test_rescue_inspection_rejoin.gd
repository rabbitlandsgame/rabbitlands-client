extends "res://tests/test_campaign_skip_to_decision.gd"
## Rejoining an already-running native escort must retain a way back to play.
## Observing that action never gives this client ownership of its movement.

func captive(status := "walking") -> Dictionary:
	var f := fixture()
	tick(f, 1)
	f.state.scene.id = "measure.rescue.captive"
	f.scene._scene_id = f.state.scene.id
	f.scene._definition = Scene.scene_definitions()[f.state.scene.id].duplicate(true)
	f.state.scene.erase("choice")
	f.state.scene.inspection = {"id":"rescue_family","status":status,"can_start":status=="pending",
		"actor_id":20,"object_id":64003,"path":[[268,128],[269,128]],"approach":[269,128]}
	f.actions = []
	f.scene.inspection_requested.connect(func(action: String) -> void: f.actions.append(action))
	return f

func run() -> void:
	root.get_node("Network").block_for_hud_preview()
	for interruption: String in ["map_changed","unavailable","disconnected"]:
		var f := captive()
		var before := JSON.stringify(f.state)
		tick(f, 0)
		expect(f.scene._inspection_sent and f.scene._inspection_pending_at >= 0,
			"a saved walking escort starts the normal presentation recovery clock")
		expect(not f.scene._inspection_active and f.actions.is_empty(),
			"observing an escort does not restart it or acquire cancellation ownership")
		f.scene.cancel(interruption)
		expect(not f.scene.blocks_input() and f.actions.is_empty()
			and f.events.finished==[[f.state.scene.token,interruption]] and not f.scene._ack_requested
			and JSON.stringify(f.state)==before,
			interruption + " releases the scene without cancel/start/proof/ACK changes")
		dispose(f)
		await process_frame
	var f := captive()
	var before := JSON.stringify(f.state)
	tick(f, 0)
	expect(f.scene._definition.inspection_timeout == 60, "the authored native-walk recovery interval is preserved")
	var started: int = f.scene._inspection_pending_at
	f.scene.skip();tick(f)
	f.scene.skip();tick(f)
	expect(f.scene.blocks_input() and f.scene.elapsed==28 and f.scene._inspection_pending_at==started
		and f.events.finished.is_empty() and f.actions.is_empty(),
		"repeated Return during a healthy walk neither resets its deadline nor bypasses its native barrier")
	# Cross only the presentation timer boundary; no server timing or proof is
	# changed. The real authored timeout above remains separately asserted.
	f.scene._definition.inspection_timeout = 0
	tick(f)
	expect(not f.scene._inspection_error.is_empty() and f.scene._inspection_retry.visible,
		"an overdue saved walk exposes its existing manual recovery controls")
	f.scene._skip.pressed.emit();tick(f, 0.7)
	expect(not f.scene.blocks_input() and f.scene._scene_handoff.is_empty() and f.actions.is_empty(),
		"Return releases play without canceling an observed walk or fading toward an unconfirmed successor")
	expect(f.events.finished.size()==1 and f.events.finished[0][1]=="skipped"
		and JSON.stringify(f.state)==before, "manual recovery acknowledges once and never invents daughter-returned proof")
	dispose(f)
	await process_frame
	f = captive("pending")
	tick(f,0);f.scene.skip();tick(f)
	expect(f.actions==["start"] and f.scene._inspection_active,
		"the original owner entry still starts and owns its one real native request")
	f.state.scene.inspection.status="walking";f.state.scene.inspection.can_start=false
	f.scene._definition.inspection_timeout=0
	tick(f);f.scene.skip();tick(f,0.7)
	expect(f.actions==["start","cancel"] and not f.scene.blocks_input(),
		"only a client that started the request cancels it during manual recovery")
	dispose(f)
	await process_frame
	f = captive()
	tick(f,0)
	f.scene.skip();tick(f)
	f.state.scene.inspection.status="complete"
	tick(f);tick(f,0.6)
	expect(f.actions.is_empty() and f.events.finished.size()==1 and not f.scene._scene_handoff.is_empty(),
		"actual native completion retains the seamless confirmed-successor handoff")
	dispose(f)
	await process_frame
	f = captive()
	f.scene._replaying=true
	f.scene._replay_bindings=f.state.scene.actors.duplicate()
	f.scene._replay_nodes=f.nodes.duplicate()
	tick(f,0)
	expect(f.scene.playing and f.scene._inspection_pending_at==-1 and not f.scene._inspection_sent
		and not f.scene._inspection_active and f.actions.is_empty(),
		"read-only replay never adopts a native escort or starts its recovery clock")
	dispose(f)
	await process_frame
	print("Rescue inspection rejoin: %d checks; %d failures" % [checks, failures])
	quit(0 if failures==0 else 1)
