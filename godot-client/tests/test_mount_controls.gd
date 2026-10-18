extends SceneTree
## Exercise the actual floating control against a moving/resizing nameplate.
var failures := 0
var checks := 0

func _init() -> void:
	call_deferred("run")

func expect(value: bool, label: String) -> void:
	checks += 1
	if not value:
		failures += 1
		push_error(label)

func run() -> void:
	var state := root.get_node("AppState")
	var view := Control.new()
	view.size = Vector2(1280, 720)
	root.add_child(view)
	var banner := Control.new()
	banner.name = "ActorResourceOverlay"
	banner.position = Vector2(500, 240)
	banner.size = Vector2(150, 86)
	view.add_child(banner)
	var controls: Variant = (load("res://src/mounts/mount_controls.gd") as Script).new()
	view.add_child(controls)
	await process_frame
	expect(not controls.visible, "no controls before authenticated mount state")
	state.authenticated = true
	state.local_actor_id = 1
	state.actor_mounts = {1: {"mode": "mounted", "gait": "cruise", "endurance_ms": 8000}}
	state.state_changed.emit(&"mount_states")
	await process_frame
	await process_frame
	expect(controls.visible, "mount state shows controls beside visible banner")
	expect(controls.position.is_equal_approx(Vector2(656, 240)), "controls sit immediately right of name and bars")
	expect(controls.toggle.get_theme_font_size("font_size") == 11, "button font matches resource numbers")
	expect(controls.status.text == "Trot · 8.0s", "compact gait and endurance")
	expect(not controls.gallop.disabled, "gallop available while trotting")
	controls.set_options({"mount_button": false, "key_hints": false, "status": false})
	expect(not controls.toggle.visible and controls.gallop.visible, "mount and gallop buttons can be hidden independently")
	expect(controls.gallop.text == "Gallop" and controls.status.text == "8.0s", "key hints and gait can be hidden while keeping endurance")
	controls.set_options({"endurance": false})
	expect(controls.status.text == "Trot", "gait can remain without endurance")
	controls.set_options({"mount_button": false, "gallop_button": false, "status": false, "endurance": false})
	expect(not controls.wants_banner(), "hiding every component leaves no empty banner")
	controls.set_options({"show_banner": false})
	expect(not controls.visible, "master preference hides mount banner")
	controls.set_options({})
	banner.position += Vector2(40, 35)
	banner.size.x = 180
	await process_frame
	await process_frame
	expect(controls.position.is_equal_approx(Vector2(726, 275)), "controls follow moving and resized banner")
	view.size = Vector2(900, 600)
	await process_frame
	await process_frame
	expect(controls.position.x + controls.size.x <= 810.1, "controls stay clear of right HUD rail")
	banner.hide()
	await process_frame
	await process_frame
	expect(not controls.visible, "hidden or offscreen banner hides floating controls")
	banner.show()
	state.actor_mounts[1] = {"mode": "on_foot", "blocked_reason": ""}
	state.state_changed.emit(&"mount_states")
	await process_frame
	expect(controls.visible and controls.toggle.text.begins_with("Mount pony"), "on-foot mount button remains available")
	expect(controls.gallop.disabled, "on-foot gallop remains unavailable")
	state.actor_mounts[1] = {"mode": "summoning", "summon_remaining_ms": 1000}
	state.state_changed.emit(&"mount_states")
	expect(controls.status.text == "Calling… 1.0s" and controls.toggle.text.begins_with("Cancel"), "moving call keeps countdown and cancellation available")
	state.authenticated = false
	state.state_changed.emit(&"authentication")
	await process_frame
	expect(not controls.visible, "logout hides mount controls")
	view.queue_free()
	await process_frame
	print("MOUNT_CONTROLS_CHECKS ", checks, " failures=", failures)
	quit(1 if failures else 0)
