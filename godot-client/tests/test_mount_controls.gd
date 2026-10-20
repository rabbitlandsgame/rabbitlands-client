extends SceneTree
## The mount status belongs to the character bar stack and collapses on foot.
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
	var banner := PanelContainer.new()
	banner.position = Vector2(500, 240)
	root.add_child(banner)
	var rows := VBoxContainer.new()
	rows.add_theme_constant_override("separation", 0)
	banner.add_child(rows)
	var resource_bar := ProgressBar.new()
	resource_bar.custom_minimum_size = Vector2(100, 10)
	resource_bar.show_percentage = false
	rows.add_child(resource_bar)
	var controls: Variant = (load("res://src/mounts/mount_controls.gd") as Script).new()
	rows.add_child(controls)
	await process_frame
	expect(not controls.visible, "no status before authenticated mount state")
	state.authenticated = true
	state.local_actor_id = 1
	state.actor_mounts = {1: {"mode": "mounted", "gait": "cruise", "endurance_ms": 8000}}
	state.state_changed.emit(&"mount_states")
	for frame: int in 3: await process_frame
	expect(controls.visible and controls.get_parent() == rows, "mount status shares the character bar stack")
	expect(controls.position.y >= resource_bar.position.y + resource_bar.size.y, "mount status sits below resource bars")
	expect(controls.find_children("*", "BaseButton", true, false).is_empty(), "no separate mount buttons remain")
	expect(controls.status.get_theme_font_size("font_size") == 11, "status font matches resource numbers")
	expect(controls.status.text == "Trot · Gallop ready", "compact gait and gallop availability")
	var before: Vector2 = controls.global_position
	banner.position += Vector2(40, 35)
	await process_frame
	expect(controls.global_position.is_equal_approx(before + Vector2(40, 35)), "status moves with the character bars")
	state.actor_mounts[1].gait = "burst"
	state.actor_mounts[1].endurance_ms = 3750
	state.state_changed.emit(&"mount_states")
	expect(controls.status.text == "Gallop · 3.8s left", "gallop displays remaining endurance")
	state.actor_mounts[1].gait = "cruise"
	state.state_changed.emit(&"mount_states")
	expect(controls.status.text == "Trot · Gallop 3.8s", "trot displays available gallop time while recovering")
	controls.set_options({"status": false})
	expect(controls.status.text == "Gallop 3.8s", "gait can be hidden while keeping available time")
	controls.set_options({"endurance": false})
	expect(controls.status.text == "Trot", "gait can remain without endurance")
	controls.set_options({"status": false, "endurance": false})
	expect(not controls.wants_banner(), "hiding every component leaves no empty row")
	controls.set_options({"show_banner": false})
	expect(not controls.visible, "saved master preference hides inline status")
	controls.set_options({"pin_banner": true, "mount_button": true, "choose_button": true})
	expect(controls.options.size() == 3 and controls.visible, "legacy pin and button preferences cannot restore a separate banner")
	banner.hide()
	expect(not controls.is_visible_in_tree(), "status inherits character banner visibility")
	banner.show()
	state.actor_mounts[1] = {"mode": "on_foot", "blocked_reason": "combat"}
	state.state_changed.emit(&"mount_states")
	for frame: int in 3: await process_frame
	expect(not controls.visible and rows.get_combined_minimum_size().y == resource_bar.get_combined_minimum_size().y,
		"dismount removes the row without leaving a gap")
	state.actor_mounts[1] = {"mode": "summoning", "summon_remaining_ms": 1000}
	state.state_changed.emit(&"mount_states")
	expect(controls.visible and controls.status.text == "Calling… 1.0s", "call countdown uses the same inline row")
	state.authenticated = false
	state.state_changed.emit(&"authentication")
	expect(not controls.visible, "logout hides mount status")
	banner.queue_free()
	await process_frame
	print("MOUNT_CONTROLS_CHECKS ", checks, " failures=", failures)
	quit(1 if failures else 0)
