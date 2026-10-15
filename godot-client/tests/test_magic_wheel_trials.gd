extends SceneTree
var failures := 0
var requests: Array[Dictionary] = []
func _init() -> void: call_deferred("run")
func check(value: bool, message: String) -> void:
	if not value:
		failures += 1
		push_error("FAIL: " + message)
func key(code: Key, pressed := true) -> InputEventKey:
	var result := InputEventKey.new()
	result.keycode = code
	result.physical_keycode = code
	if code == KEY_SHIFT: result.location = KEY_LOCATION_LEFT
	result.pressed = pressed
	result.shift_pressed = true
	return result
func run() -> void:
	root.size = Vector2i(1280, 720)
	var lab := (load("res://src/dev/magic_practice.tscn") as PackedScene).instantiate()
	root.add_child(lab)
	lab.trial_preferences_path = ""
	lab.loadout.profile = ""
	lab.loadout.set_ring_size(100)
	lab.loadout.set_wheel_power(3)
	lab.selector.request_sender = func(data: Dictionary) -> Error:
		requests.append(data.duplicate(true))
		return OK
	var state := root.get_node("AppState")
	for variant in ["quick", "orbit"]:
		lab.trial_preferences = {"scopes": {}, "powers": {}, "pins": {}}
		lab.set_wheel_variant(variant)
		lab.loadout.assign_slot(0, 0, 1)
		lab.loadout.assign_slot(1, 1, 2)
		var wheel: Control = lab.wheel
		state.select_actor(2)
		var right_shift := key(KEY_SHIFT)
		right_shift.location = KEY_LOCATION_RIGHT
		root.push_input(right_shift, true)
		check(not wheel.visible, "Right Shift does not open the ring")
		root.push_input(alt_key(KEY_ALT), true)
		check(not wheel.visible, "Alt is reserved for the quickbar")
		root.push_input(alt_key(KEY_ALT, false), true)
		root.push_input(key(KEY_SHIFT), true)
		await process_frame
		check(wheel.visible, variant + " opens through real Left Shift input")
		right_shift.pressed = false
		root.push_input(right_shift, true)
		check(wheel.visible, "releasing Right Shift cannot dismiss the Left Shift ring")
		var frozen: Vector2 = wheel.center
		lab.actors[1].tile += Vector2i(1, 0)
		await process_frame
		check(wheel.center == frozen, variant + " stays fixed while the character moves")
		if variant == "quick":
			await right_click(wheel.center)
			check(wheel.visible and wheel.stage == "classes", "right click before a spell is highlighted keeps classes open")
			var sector: Button = wheel.buttons[0]
			await move_to_sector(sector)
			await create_timer(0.25).timeout
			check(wheel.stage == "effects" and wheel.category == "Healing", "hover enters Healing without a click")
		else:
			wheel.handle_event(key(KEY_E))
			check(wheel.category == "Offense", "Orbit class letters switch the inner ring")
			wheel.handle_event(key(KEY_Q))
		check(wheel.resolve_spell("heal") == 1, "first Heal uses an eligible selected recipient")
		check(wheel._preview.text.contains("Tavin"), "preview names the selected recipient")
		var before := requests.size()
		wheel.change_power(1)
		wheel.select_scope("target")
		check(requests.size() == before, "hover, power, and target controls do not cast")
		for scope in ["allies", "burst", "self", "target"]:
			await right_click(wheel.center + Vector2(0, -210))
			check(lab.catalog.spell(wheel.resolve_spell("heal")).scope == scope, variant + " right click advances once to " + scope)
			check(wheel.visible and wheel.stage == "effects" and wheel.power_for(1) == 4, "cycling keeps the wheel open and preserves power")
		check(requests.size() == before and lab.selector.pending.is_empty(), "right clicks never cast or start targeting")
		await click_sector(wheel.buttons[0])
		check(requests.back() == {"op": "cast", "id": 1, "power": 4, "target_id": 2}, variant + " one click casts the previewed spell and power")
		root.push_input(key(KEY_SHIFT, false), true)
		check(lab.loadout.slots[0] == {"id": 1, "power": 4} and lab.loadout.slots[1] == lab.loadout.slots[0], "ring cast updates matching quickbar target types and powers")
		check(lab.bar.buttons[0].get_node("Target").text == "T" and lab.bar.buttons[0].get_node("Power").text == "4", "quickbar corner labels reflect the last cast")
		before = requests.size()
		root.push_input(alt_key(KEY_1), true)
		root.push_input(alt_key(KEY_1, false), true)
		check(not wheel.visible and requests.size() == before + 1 and requests.back() == {"op": "cast", "id": 1, "power": 4, "target_id": 2}, "Alt+1 repeats the quickbar setup exactly once in wheel mode")
		state.select_actor(3)
		root.push_input(key(KEY_SHIFT), true)
		root.push_input(key(KEY_SPACE), true)
		check(requests.back().get("target_id") == 3 and requests.back().power == 4, "repeat uses the current recipient and previous power")
		root.push_input(key(KEY_SHIFT, false), true)
		wheel.open_wheel()
		wheel.enter_class("Healing")
		check(wheel.power_for(1) == 4, "family power is remembered")
		wheel.select_scope("burst")
		wheel.choose(0)
		check(lab.selector.pending.get("id") == 21, "Burst still asks for ground placement")
		lab.selector.confirm_location(Vector2i(12, 7))
		check(requests.back().get("x") == 12 and requests.back().power == 4, "ground confirmation preserves chosen power")
		wheel.open_wheel()
		wheel.enter_class("Healing")
		check(wheel.resolve_spell("heal") == 21, "last target type is remembered per family")
		before = requests.size()
		wheel.handle_event(key(KEY_SHIFT, false))
		check(requests.size() == before and not wheel.visible, "release cancels unfinished selection")
		wheel.open_wheel()
		wheel.enter_class("Offense")
		before = requests.size()
		for scope in ["burst", "target"]:
			await right_click(wheel.center)
			check(lab.catalog.spell(wheel.resolve_spell("poison")).scope == scope, "cycling skips unavailable Self and Allies options")
		check(requests.size() == before, "cycling a hostile spell never casts")
		check(wheel.pinned_families("Offense").size() == 6, "Offense begins with six stable pinned families")
		var initial: Array[String] = wheel.pinned_families("Offense")
		wheel.effect = initial[0]
		wheel.toggle_pin()
		wheel.change_page(1)
		var add: String = wheel.entries[0].value
		wheel.effect = add
		wheel.toggle_pin()
		check(add in wheel.pinned_families("Offense") and wheel.pinned_families("Offense").size() == 6, "a family from More can replace an unpinned family")
		var reachable: Array[String] = wheel.pinned_families("Offense")
		reachable.append_array(wheel._remaining())
		var expected: Array[String] = wheel.effects_for("Offense")
		reachable.sort()
		expected.sort()
		check(reachable == expected, "pinning leaves every family reachable")
		var saved: Array[String] = wheel.pinned_families("Offense")
		wheel.enter_class("Utility")
		var utility_id: int = wheel.resolve_spell("blink")
		await right_click(wheel.center)
		check(wheel.visible and wheel.category == "Utility" and wheel.resolve_spell("blink") == utility_id, "single-option utility keeps its target and the wheel open")
		check(requests.size() == before and not lab.selector.popup.visible, "right click cannot launch a utility action")
		wheel.handle_event(key(KEY_BACKSPACE))
		check(wheel.stage == "classes" if variant == "quick" else not wheel.visible, "Backspace retains back navigation")
		wheel.open_wheel()
		state.spell_power["heal"] = {"limit": 2}
		wheel.enter_class("Healing")
		check(wheel.power_for(1) == 2, "remembered power respects a lower server limit")
		check(wheel.pinned_families("Offense") == saved, "limits cannot reorder pins")
		state.spell_power["heal"] = {"limit": 10}
		wheel.reset()
	# Trial switching does not replace the baseline implementation or lose pins.
	lab.set_wheel_variant("baseline")
	check(lab.wheel.get_script() == load("res://src/ui/spell_wheel.gd"), "baseline uses the original wheel")
	lab.set_wheel_variant("orbit")
	check(lab.wheel.preferences == lab.trial_preferences, "switching trials preserves comparison preferences")
	await test_sizes(lab)
	lab.free()
	await process_frame
	print("magic wheel trials: ", "PASS" if failures == 0 else "FAIL")
	quit(failures)

func test_sizes(lab: Control) -> void:
	var state := root.get_node("AppState")
	state.select_actor(2)
	for variant in ["quick", "orbit", "baseline"]:
		lab.set_wheel_variant(variant)
		for percent in [75,90,100,110,125]:
			var picker: OptionButton = lab.bar.ring_size_picker
			var before := requests.size()
			picker.item_selected.emit(picker.get_item_index(percent))
			check(lab.loadout.ring_size == percent and requests.size() == before, "size picker changes the preference without casting")
			var wheel: Control = lab.wheel
			wheel.open_wheel()
			await process_frame
			check(Rect2(Vector2.ZERO,Vector2(root.size)).encloses(wheel.get_ring_bounds()), variant + " fits the window at " + str(percent))
			check(wheel.buttons[0].scale == Vector2.ONE * wheel.display_scale(), "visual and button transforms share the selected scale")
			check(Rect2(Vector2.ZERO,Vector2(root.size)).encloses(lab.bar.panel.get_global_rect()), "size control and quickbar stay reachable")
			if variant == "quick": await click_scaled_sector(wheel.buttons[0])
			elif variant == "baseline":
				wheel.choose(0)
				wheel.choose(0)
			if variant != "baseline":
				wheel.effect = "heal"
				wheel.select_scope("target")
				wheel.change_power(1-wheel.power_for(1))
				await click_scaled_sector(wheel.buttons[0])
			else:
				wheel.choose(1)
			check(requests.back().get("id") == 1 and requests.back().get("target_id") == 2, "resized " + variant + " still casts Heal Target through the real selector")
	# Refit a still-open ring on a smaller viewport without changing the preference.
	lab.set_wheel_variant("quick")
	lab.loadout.set_ring_size(125)
	lab.wheel.open_wheel()
	var original_canvas := root.content_scale_size
	root.content_scale_size = Vector2i.ZERO
	root.size = Vector2i(800,600)
	for frame in range(3): await process_frame
	check(Rect2(Vector2.ZERO,Vector2(root.size)).encloses(lab.wheel.get_ring_bounds()), "an open ring refits on window resize: " + str(lab.wheel.get_ring_bounds()) + " size=" + str(lab.wheel.size) + " visible=" + str(lab.wheel.visible))
	check(lab.loadout.ring_size == 125, "automatic fitting preserves the requested size")
	root.content_scale_size = original_canvas
	root.size = Vector2i(1280,720)
	lab.wheel.reset()
	lab.loadout.set_ring_size(100)

func click_scaled_sector(button: Button) -> void:
	var point: Vector2 = button.get_global_transform() * (Vector2.ONE * button.outer + Vector2.from_angle(button.angle + button.spread * 0.3) * (button.inner+button.outer)/2)
	for pressed in [true,false]:
		var event := InputEventMouseButton.new()
		event.position = point
		event.global_position = point
		event.pressed = pressed
		event.button_index = MOUSE_BUTTON_LEFT
		root.push_input(event,true)
		await process_frame
func alt_key(code: Key, pressed := true) -> InputEventKey:
	var result := key(code, pressed)
	result.shift_pressed = false
	result.alt_pressed = true
	return result
func move_to_sector(button: Button) -> void:
	var event := InputEventMouseMotion.new()
	event.position = button.global_position + Vector2.ONE * button.outer + Vector2.from_angle(button.angle) * (button.inner + button.outer) / 2
	event.global_position = event.position
	root.push_input(event, true)
	await process_frame
func right_click(point: Vector2) -> void:
	for pressed in [true, false]:
		var event := InputEventMouseButton.new()
		event.position = point
		event.global_position = point
		event.pressed = pressed
		event.button_index = MOUSE_BUTTON_RIGHT
		event.shift_pressed = true
		root.push_input(event, true)
		await process_frame
func click_sector(button: Button) -> void:
	var point: Vector2 = button.global_position + Vector2.ONE * button.outer + Vector2.from_angle(button.angle + button.spread * 0.30) * (button.inner + button.outer) / 2
	for pressed in [true, false]:
		var event := InputEventMouseButton.new()
		event.position = point
		event.global_position = point
		event.pressed = pressed
		event.button_index = MOUSE_BUTTON_LEFT
		event.shift_pressed = true
		root.push_input(event, true)
		await process_frame
