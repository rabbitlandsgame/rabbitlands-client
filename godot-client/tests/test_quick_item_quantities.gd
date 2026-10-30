extends SceneTree
## Offline coverage of the live quick-item quantity display and saved HUD preference.
var main: Control
var checks := 0
var failures := 0

func _init() -> void:
	call_deferred("run")

func run() -> void:
	root.size = Vector2i(1280, 720)
	main = (load("res://src/app/main.tscn") as PackedScene).instantiate() as Control
	root.add_child(main)
	for frame: int in range(8):
		await process_frame
	main.get_node("LoginPanel").hide()
	main.get_node("LoginBackground").hide()
	main.get("game_view").show()
	var state: Node = root.get_node("AppState")
	state.set("authenticated", true)
	var inventory := {}
	for slot in range(8):
		inventory[slot] = {"slot": slot, "image_id": 3, "inventory_usable": true, "quantity": 9}
	state.set("inventory", inventory)
	state.set("inventory_cooldowns", {})
	state.emit_signal("state_changed", &"inventory")
	_test_quantities(main.get("settings_window"), state, inventory)
	for frame: int in range(8):
		await process_frame
	main.queue_free()
	await process_frame
	await process_frame
	NativeAnimationImporter.clear()
	GlbSceneCache.clear()
	print("QUICK ITEM QUANTITIES: %d checks, %d failures" % [checks, failures])
	quit(1 if failures else 0)

func _test_quantities(settings: Control, state: Node, inventory: Dictionary) -> void:
	var toggle := (settings.get("panel") as Control).find_child(
		"quick_item_quantities", true, false) as CheckBox
	expect(toggle != null and toggle.button_pressed,
		"HUD offers quick item quantities enabled by default")
	for button: Button in main.get("quick_slot_buttons"):
		var quantity := button.get_node("Quantity") as Label
		expect(quantity.visible and quantity.text == "9"
			and quantity.mouse_filter == Control.MOUSE_FILTER_IGNORE,
			"each quick slot shows its stack without intercepting clicks")
	var first: Button = (main.get("quick_slot_buttons") as Array)[0]
	var count := first.get_node("Quantity") as Label
	inventory[0]["quantity"] = 1
	state.emit_signal("state_changed", &"inventory")
	expect(count.text == "1" and count.visible, "the last item still shows a count")
	inventory[0]["quantity"] = 123456
	state.emit_signal("state_changed", &"inventory")
	expect(count.text == "123456", "inventory updates refresh the full stack count")
	state.set("inventory_cooldowns", {0: {
		"end_msec": Time.get_ticks_msec() + 60000, "maximum_msec": 60000}})
	main.call("_sync_quick_slots")
	main.call("_update_cooldown_overlays")
	expect(first.disabled and count.visible and count.text == "123456"
		and count.z_index > (first.get_node("Cooldown") as Control).z_index,
		"quantity remains readable while an item is on cooldown")
	if toggle != null:
		toggle.button_pressed = false
		expect(not count.visible, "the HUD toggle hides counts immediately")
		var saved := ConfigFile.new()
		expect(saved.load("user://eloria_hud.cfg") == OK
			and not bool(saved.get_value("hud", "quick_item_quantities", true)),
			"the quantity preference is saved")
		(main.get("_hud_element_options") as Dictionary)["quick_item_quantities"] = true
		main.call("_load_hud_settings")
		main.call("_apply_hud_element_options")
		expect(not count.visible and not toggle.button_pressed,
			"the hidden preference survives reloading settings")
		toggle.button_pressed = true
		expect(count.visible and count.text == "123456", "counts can be shown again")
	var original: Dictionary = inventory[0]
	inventory.erase(0)
	state.emit_signal("state_changed", &"inventory")
	expect(not count.visible and count.text.is_empty(), "empty slots clear stale counts")
	inventory[0] = original
	inventory[0]["quantity"] = 9
	state.set("inventory_cooldowns", {})
	state.emit_signal("state_changed", &"inventory")

func expect(condition: bool, label: String) -> void:
	checks += 1
	if not condition:
		failures += 1
		push_error("FAIL: " + label)
