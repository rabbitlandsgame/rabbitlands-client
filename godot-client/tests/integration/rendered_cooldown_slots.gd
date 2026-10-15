extends SceneTree
## Rendered evidence that item cooldowns draw independently per slot, in
## both the quick bar and the inventory grid, and that the seconds label
## stays centered on the icon as the shade drains instead of drifting down
## it.
##
## Run under a real display:
##   godot --rendering-method gl_compatibility --path . \
##     --script tests/integration/rendered_cooldown_slots.gd

const SCREEN_SIZE := Vector2i(1280, 720)

var _artifact_directory := ""
var _failures := 0

func _init() -> void:
	call_deferred("_run")

func _run() -> void:
	_artifact_directory = OS.get_environment("ELORIA_ARTIFACT_DIR")
	if _artifact_directory.is_empty():
		_artifact_directory = ProjectSettings.globalize_path(
			"res://test-artifacts/cooldown-slots")
	_expect(DirAccess.make_dir_recursive_absolute(_artifact_directory) == OK,
		"artifact directory is writable")
	root.size = SCREEN_SIZE
	var main: Control = (load("res://src/app/main.tscn") as PackedScene
		).instantiate() as Control
	root.add_child(main)
	await process_frame
	(main.get_node("LoginBackground") as TextureRect).hide()
	(main.get_node("LoginPanel") as Control).hide()
	(main.get_node("GameView") as Control).show()

	var app_state: Node = root.get_node("AppState")
	app_state.set("authenticated", true)
	app_state.set("local_actor_id", 99)
	app_state.set("stats", {
		"health": 72, "max_health": 100, "ether": 33, "max_ether": 50,
		"action_points": 18, "max_action_points": 30, "food": 42,
		"carried": 205, "capacity": 320})
	app_state.set("inventory", {
		0: {"image_id": 3, "quantity": 9, "slot": 0, "inventory_usable": true},
		1: {"image_id": 31, "quantity": 3, "slot": 1, "inventory_usable": true},
		10: {"image_id": 35, "quantity": 1, "slot": 10, "inventory_usable": true}})
	main.call("_on_inventory_button_pressed")
	main.set("selected_inventory_slot", -1)
	main.call("_sync_inventory")

	# Two quick-bar slots and one inventory-only slot on cooldown at once, at
	# three different fractions remaining - proof that every slot on
	# cooldown draws its own countdown rather than only the most recently
	# announced one.
	var cooldowns: Dictionary = app_state.get("inventory_cooldowns") as Dictionary
	cooldowns[0] = {"maximum_msec": 10000, "end_msec": Time.get_ticks_msec() + 9500}
	cooldowns[1] = {"maximum_msec": 10000, "end_msec": Time.get_ticks_msec() + 5000}
	cooldowns[10] = {"maximum_msec": 10000, "end_msec": Time.get_ticks_msec() + 1500}
	main.call("_update_cooldown_overlays")
	await _capture("cooldown-slots-multiple.png")

	# The same slot, freshly on cooldown versus nearly drained: the shade
	# shrinks toward the bottom, but the number must land in the same place
	# both times rather than following it down.
	var quick_slot: Button = (main.get("quick_slot_buttons") as Array)[0] as Button
	var seconds_label: Label = quick_slot.get_node("Seconds") as Label
	cooldowns[0] = {"maximum_msec": 10000, "end_msec": Time.get_ticks_msec() + 9900}
	main.call("_update_cooldown_overlays")
	await _capture("cooldown-slot-fresh.png")
	var fresh_center: Vector2 = seconds_label.get_global_rect().get_center()
	cooldowns[0] = {"maximum_msec": 10000, "end_msec": Time.get_ticks_msec() + 900}
	main.call("_update_cooldown_overlays")
	await _capture("cooldown-slot-draining.png")
	var draining_center: Vector2 = seconds_label.get_global_rect().get_center()
	_expect(fresh_center.distance_to(draining_center) < 0.5,
		"the seconds label does not move as the shade drains: fresh=%s draining=%s"
			% [fresh_center, draining_center])

	print("rendered cooldown slots: ",
		"PASS" if _failures == 0 else "FAIL (%d)" % _failures)
	main.queue_free()
	await process_frame
	quit(_failures)

func _capture(file_name: String) -> void:
	for unused_frame: int in range(4):
		await process_frame
	RenderingServer.force_draw(false)
	var image_value: Variant = root.get_texture().get_image()
	if not image_value is Image:
		_expect(false, "%s: a rendered frame is available" % file_name)
		return
	var image: Image = image_value as Image
	_expect(not image.is_empty() and image.get_size() == SCREEN_SIZE,
		"%s: the frame has reference dimensions" % file_name)
	var sampled: Dictionary = {}
	for y: int in range(0, image.get_height(), 16):
		for x: int in range(0, image.get_width(), 16):
			sampled[image.get_pixel(x, y).to_html()] = true
	_expect(sampled.size() >= 48,
		"%s: the frame carries visual detail (%d colours)"
			% [file_name, sampled.size()])
	_expect(image.save_png(_artifact_directory.path_join(file_name)) == OK,
		"%s: written" % file_name)

func _expect(value: bool, label: String) -> bool:
	if not value:
		_failures += 1
		push_error("FAIL: " + label)
	return value
