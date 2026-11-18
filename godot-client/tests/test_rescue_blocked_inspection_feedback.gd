extends "res://tests/test_rescue_inspection_rejoin.gd"
## Authoritative blocked escorts offer recovery immediately; native permission
## controls Retry, and merely observing permission never sends an action.

func blocked(can_start:bool) -> Dictionary:
	var f:=captive("walking")
	tick(f,0);f.scene.skip();tick(f)
	f.state.scene.inspection.status="blocked"
	f.state.scene.inspection.can_start=can_start
	f.state.party={"role":"owner" if can_start else "helper"}
	tick(f,0)
	return f

func run() -> void:
	root.get_node("Network").block_for_hud_preview()
	var f:=blocked(true)
	var before:=JSON.stringify(f.state)
	var held:Transform3D=f.rig.camera.global_transform
	expect(not f.scene._inspection_error.is_empty() and f.scene._inspection_retry.visible,
		"a native blocked family walk exposes recovery without waiting sixty seconds")
	expect(not f.scene._inspection_retry.disabled and f.actions.is_empty(),
		"the authorized owner sees Retry but no request is sent automatically")
	expect("cage" not in f.scene._caption.text.to_lower() and "inspect" not in f.scene._inspection_retry.text.to_lower(),
		"family recovery describes the route rather than directing an exit walk back to the cage")
	expect(f.rig.camera.global_transform.is_equal_approx(held) and JSON.stringify(f.state)==before,
		"blocked-action feedback changes neither the established view nor native progress")
	f.scene._inspection_retry.pressed.emit()
	expect(f.actions==["start"] and f.scene._inspection_active and f.scene._inspection_error.is_empty(),
		"only the owner's explicit Retry starts and owns a native walk")
	f.state.scene.inspection.status="walking";f.state.scene.inspection.can_start=false
	tick(f,0)
	expect(not f.scene._inspection_retry.visible and f.actions==["start"],
		"the new native walking state clears retry feedback without another request")
	dispose(f);await process_frame
	f=blocked(false)
	expect(not f.scene._inspection_error.is_empty() and f.scene._inspection_retry.disabled,
		"a helper or unavailable owner gets recovery feedback without an authorized Retry")
	f.scene._request_inspection()
	expect(f.actions.is_empty() and not f.scene._inspection_active,
		"a helper cannot start or acquire ownership of the family's native movement")
	f.scene.skip();tick(f,0.7)
	expect(not f.scene.blocks_input() and f.scene._scene_handoff.is_empty() and f.actions.is_empty(),
		"Return to play releases an observed blocked escort without cancelling it or fading to a successor")
	dispose(f);await process_frame
	f=blocked(false)
	f.state.party.role="owner";f.state.scene.inspection.can_start=true
	tick(f,0)
	expect(f.scene._inspection_retry.visible and not f.scene._inspection_retry.disabled and f.actions.is_empty(),
		"late native permission enables Retry without automatically restarting the action")
	f.state.scene.inspection.status="walking";f.state.scene.inspection.can_start=false
	tick(f,0)
	expect(f.scene._inspection_error.is_empty() and not f.scene._inspection_retry.visible
		and f.actions.is_empty() and not f.scene._inspection_active and f.scene._inspection_pending_at>=0,
		"another authorized client's resumed walk clears stale blocked feedback and rearms observation only")
	dispose(f);await process_frame
	f=captive("blocked");f.state.scene.inspection.can_start=true
	tick(f,0);f.scene.skip();tick(f)
	expect(f.scene._inspection_retry.visible and not f.scene._inspection_retry.disabled
		and f.actions.is_empty() and not f.scene._inspection_active,
		"a fresh blocked checkpoint waits for explicit Retry instead of automatically restarting it")
	dispose(f);await process_frame
	f=captive("blocked")
	f.scene._replaying=true
	f.scene._replay_bindings=f.state.scene.actors.duplicate()
	f.scene._replay_nodes=f.nodes.duplicate()
	f.scene.elapsed=28;tick(f,0)
	expect(f.scene.playing and f.scene._inspection_error.is_empty() and not f.scene._inspection_retry.visible
		and f.actions.is_empty() and not f.scene._inspection_active,
		"a recorded blocked checkpoint remains read-only without live Retry controls")
	dispose(f);await process_frame
	var path:=OS.get_environment("RL_RESCUE_BLOCKED_EVIDENCE")
	if not path.is_empty():
		var bundle:Dictionary=JSON.parse_string(FileAccess.get_file_as_string(path))
		for row:Dictionary in bundle.snapshots:
			var native:Dictionary=row.get("snapshot",row)
			var decoded:=EloriaProtocol.decode_campaign(JSON.stringify(native).to_utf8_buffer())
			expect(decoded.type=="campaign" and native.scene.inspection.id=="rescue_family"
				and native.scene.inspection.status=="blocked",
				"the retained earned-save blocked family snapshot decodes unchanged")
			var permission:bool=bool(native.scene.inspection.can_start)
			f=blocked(permission)
			expect(f.scene._inspection_retry.disabled==not permission and f.actions.is_empty(),
				"the same native permission controls immediate recovery without generating movement")
			dispose(f);await process_frame
	print("Blocked rescue feedback: %d checks; %d failures"%[checks,failures])
	quit(0 if failures==0 else 1)
