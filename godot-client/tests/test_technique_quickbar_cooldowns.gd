extends SceneTree
## Exercise cooldowns on the actual quick bar with and without corner badges.
var failures := 0

func _init() -> void:
	call_deferred("_run")

func _run() -> void:
	root.size = Vector2i(800, 320)
	root.content_scale_size = root.size
	var state: Node = root.get_node("AppState")
	var catalog := SpellCatalog.new()
	catalog.configure(JSON.parse_string(FileAccess.get_file_as_string("res://data/spells/catalog.json")))
	var loadout = preload("res://src/ui/spell_loadout.gd").new()
	loadout.configure(catalog)
	loadout.slots[0] = {"id": -1, "power": 1, "technique": "heavy_blow"}
	loadout.slots[1] = {"id": -1, "power": 1, "technique": "charge"}
	loadout.slots[2] = loadout.slots[0].duplicate()
	var bar = load("res://src/ui/casting_bar.gd").new()
	bar.loadout = loadout
	root.add_child(bar)
	await process_frame
	var packet := {"kind": "techniques", "techniques": [
		{"key": "heavy_blow", "name": "Heavy Blow", "known": true, "ap": 0,
			"ready_in": 24.0, "cooldown": 30.0, "blocker": "You need a weapon."},
		{"key": "charge", "name": "Charge", "known": true, "ap": 10,
			"ready_in": 6.0, "cooldown": 30.0},
	]}
	state.call("_on_packet", 212, JSON.stringify(packet).to_utf8_buffer())
	await process_frame
	var first: Button = bar.buttons[0]
	var second: Button = bar.buttons[1]
	var duplicate_slot: Button = bar.buttons[2]
	var shade: ColorRect = first.get_node("Cooldown")
	var seconds: Label = first.get_node("Seconds")
	_expect(seconds.is_visible_in_tree() and seconds.text.to_int() > 20,
		"a technique shows remaining seconds even when equipment also blocks it")
	_expect(second.get_node("Seconds").visible and second.get_node("Seconds").text.to_int() <= 6,
		"another technique shows its own cooldown")
	_expect(duplicate_slot.get_node("Seconds").text == seconds.text,
		"two slots holding the same technique agree")
	_expect(shade.visible and absf(shade.anchor_top - 0.2) < 0.05,
		"the shade shows the fraction of cooldown remaining")
	_expect(second.get_node("Cooldown").anchor_top > shade.anchor_top,
		"different cooldowns drain independently")
	_expect(seconds.mouse_filter == Control.MOUSE_FILTER_IGNORE and shade.mouse_filter == Control.MOUSE_FILTER_IGNORE,
		"cooldown overlays preserve clicks and drag assignment")

	bar.workspace_layout = {"style": "minimal", "slots": 6, "orientation": "horizontal",
		"show_badges": false, "position": Vector2(30, 30), "icon_opacity": 0.25}
	await process_frame
	await process_frame
	_expect(not first.get_node("Target").visible and not first.get_node("Power").visible,
		"the compact HUD hides optional badges")
	_expect(seconds.is_visible_in_tree() and shade.is_visible_in_tree() and seconds.modulate.a == 1.0,
		"the cooldown stays visible and readable with badges hidden and dimmed icons")
	var center := seconds.get_global_rect().get_center()
	var before := seconds.text.to_int()
	# Advance the authoritative snapshot's age and let the bar's own timer update it.
	state.get("techniques")["received_msec"] -= 3000
	await create_timer(0.3).timeout
	_expect(seconds.text.to_int() < before and shade.anchor_top > 0.25,
		"the live bar counts down and drains without another server packet")
	_expect(center.distance_to(seconds.get_global_rect().get_center()) < 0.5,
		"the number stays centered while the shade drains")
	for arg in OS.get_cmdline_user_args():
		if arg.begins_with("--capture="):
			await RenderingServer.frame_post_draw
			_expect(root.get_texture().get_image().save_png(arg.trim_prefix("--capture=")) == OK,
				"the quick bar preview is saved")

	# A server correction updates an existing countdown immediately.
	packet.techniques[0].ready_in = 12.0
	state.call("_on_packet", 212, JSON.stringify(packet).to_utf8_buffer())
	_expect(seconds.text.to_int() >= 11 and seconds.text.to_int() <= 12,
		"a fresh server snapshot corrects the countdown")
	loadout.slots[0] = {"id": catalog.default_quick_slots[0], "power": 1}
	loadout.slots[1] = {"id": -1, "power": 1}
	loadout.changed.emit()
	_expect(not shade.visible and not seconds.visible and not second.get_node("Seconds").visible,
		"replacing a technique with a spell or empty slot clears its cooldown")
	state.get("techniques")["received_msec"] -= 60000
	await create_timer(0.3).timeout
	_expect(not duplicate_slot.get_node("Cooldown").visible and not duplicate_slot.get_node("Seconds").visible,
		"the cooldown disappears automatically when the technique is ready")
	_expect(not bool(bar.get("_technique_cooling")), "the bar stops cooldown refreshes after expiry")
	bar.queue_free()
	await process_frame
	print("technique quickbar cooldown tests: ", "PASS" if failures == 0 else "FAIL (%d)" % failures)
	quit(failures)

func _expect(value: bool, message: String) -> void:
	if not value:
		failures += 1
		push_error("FAIL: " + message)
