extends SceneTree
var failures := 0
var checks := 0

func _init() -> void:
	call_deferred("run")

func expect(ok: bool, message: String) -> void:
	checks += 1
	if not ok:
		failures += 1
		push_error(message)

func run() -> void:
	root.size = Vector2i(1280, 720)
	var state := root.get_node("AppState")
	state.authenticated = true
	state.local_actor_id = 42
	state.actor_mounts[42] = {"mode": "on_foot", "selected_mount_id": "moor_pony", "mount_id": "",
		"owned_mount_ids": ["moor_pony", "golden_plains_horse", "crystalback_tortoise", "rabbit"], "blocked_reason": "", "gait": "on_foot"}
	var window: Variant = (load("res://src/ui/mounts_window.gd") as Script).new()
	root.add_child(window)
	var sent: Array[String] = []
	window.send_command = func(text: String) -> void: sent.append(text)
	window.open()
	for frame: int in 4:
		await process_frame
	expect(window.panel.get_rect().end.y <= 680, "mount window fits above the fixed bottom bar")
	expect(window.is_open() and window.cards.size() == 4, "four enabled mounts appear")
	window.choose("golden_plains_horse")
	expect(not window.ride.disabled, "horse can be chosen by this player")
	expect(state.actor_mounts[42].selected_mount_id == "moor_pony", "browsing never predicts server selection")
	window._ride()
	expect(sent == ["#mount ride golden_plains_horse"], "Ride asks server to select and call the chosen horse")
	state.actor_mounts[42].mode = "summoning"
	state.actor_mounts[42].mount_id = "golden_plains_horse"
	state.state_changed.emit(&"mount_states")
	for frame: int in 4:
		await process_frame
	expect(window.panel.get_rect().end.y <= 680, "calling status keeps the window above the bottom bar")
	state.actor_mounts[42].mode = "on_foot"
	state.actor_mounts[42].mount_id = ""
	state.state_changed.emit(&"mount_states")
	window._dismount()
	expect(sent.size() == 1, "disabled dismount never starts an unintended call")
	state.actor_mounts[42].mode = "mounted"
	state.actor_mounts[42].mount_id = "golden_plains_horse"
	state.actor_mounts[42].selected_mount_id = "golden_plains_horse"
	state.state_changed.emit(&"mount_states")
	expect(window.ride.disabled and not window.dismount.disabled, "mounted snapshot confirms horse and enables dismount")
	window.choose("moor_pony")
	window._ride()
	expect(sent.back() == "#mount ride moor_pony", "mounted rider can switch back to pony")
	window.choose("crystalback_tortoise")
	window._ride()
	expect(sent.back() == "#mount ride crystalback_tortoise", "third mount uses the same authoritative selection command")
	window.choose("rabbit")
	window._ride()
	expect(sent.back() == "#mount ride rabbit", "rabbit uses normal authoritative switching")
	window._dismount()
	expect(sent.back() == "#mount", "Dismount uses normal server command")
	state.actor_mounts[42].blocked_reason = "combat"
	state.state_changed.emit(&"mount_states")
	expect(window.ride.disabled, "server combat block disables switching")
	root.size = Vector2i(800,720)
	root.content_scale_size = Vector2i(800,720)
	for frame: int in 8: await process_frame
	expect(window.panel.get_global_rect().end.x <= 704, "four cards scroll inside a smaller game window")
	window.choose("crystalback_tortoise")
	window.close()
	expect(not window.is_open(), "window closes")
	for portrait: Variant in window.portraits.values():
		expect(portrait.viewport.render_target_update_mode == SubViewport.UPDATE_DISABLED, "closed window stops portrait rendering")
	window.free()
	state.actor_mounts.clear()
	state.authenticated = false
	print("MOUNTS_WINDOW_CHECKS ", checks, " failures=", failures)
	NativeAnimationImporter.clear()
	GlbSceneCache.clear()
	quit(1 if failures else 0)
