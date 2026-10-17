extends SceneTree
## Exercise the real HUD, including input routing and a fresh scene reload.
var failures := 0
var captures := ""
const SETTINGS := "user://eloria_hud.cfg"

func _init() -> void:
	for arg in OS.get_cmdline_user_args():
		if arg.begins_with("--capture="): captures = arg.trim_prefix("--capture=")
	call_deferred("run")

func check(value: bool, message: String) -> void:
	if not value:
		failures += 1
		push_error("FAIL: " + message)

func settle() -> void:
	for frame in range(5): await process_frame

func scene() -> Control:
	var main := (load("res://src/app/main.tscn") as PackedScene).instantiate() as Control
	root.add_child(main)
	main.get_node("LoginPanel").hide()
	main.get_node("GameView").show()
	return main

func capture(filename: String) -> void:
	if captures.is_empty(): return
	await settle()
	await RenderingServer.frame_post_draw
	DirAccess.make_dir_recursive_absolute(captures)
	root.get_texture().get_image().save_png(captures.path_join(filename))

func check_hud_dock(main: Control) -> void:
	var bar = main.casting_bar
	var shown: Control = bar.panel if bar.panel.visible else bar.launcher
	check(bar._dock_bounds().encloses(shown.get_rect()), "the spell bar stays in the space below the logo and above skills")
	for path in ["EloriaLogoFrame", "ItemQuickbar", "ResourceHud", "RailMeters", "ClockFrame", "CompassFrame"]:
		check(not shown.get_global_rect().intersects(main.get_node("GameView/" + path).get_global_rect()), "the attached spell bar leaves " + path + " clear")
	check(not shown.get_global_rect().intersects(main.get_node("%ChatInput").get_global_rect()), "the movable chat footer stays clear of the spell bar")
	var items: ScrollContainer = main.get_node("GameView/ItemQuickbar")
	check(main.right_rail.get_global_rect().encloses(items.get_global_rect()), "item shortcuts stay inside the right HUD")
	for path in ["ResourceHud", "RailMeters", "ClockFrame", "CompassFrame"]:
		check(not items.get_global_rect().intersects(main.get_node("GameView/" + path).get_global_rect()), "the item viewport leaves " + path + " clear")
	for index in range(mini(6, bar.visible_slot_count)):
		var item: Button = main.quick_slot_buttons[index]
		var spell: Button = bar.buttons[index]
		check(item.size.is_equal_approx(spell.size), "paired item and spell cells have equal dimensions")
		check(item.get_theme_constant("icon_max_width") == spell.get_theme_constant("icon_max_width"), "paired item and spell artwork have equal size")
		var item_y: float = item.global_position.y + items.scroll_vertical
		var spell_y: float = spell.global_position.y + bar._scroll.scroll_vertical
		if bar.panel.visible:
			check(is_equal_approx(item_y, spell_y), "item and spell rows align vertically: item=%s spell=%s" % [item_y, spell_y])
		check(is_equal_approx(item.get_theme_stylebox("normal").get_content_margin(SIDE_TOP), spell.get_theme_stylebox("normal").get_content_margin(SIDE_TOP)), "item and spell artwork align below their shortcut headers")

func run() -> void:
	root.size = Vector2i(1280, 720)
	var original := FileAccess.get_file_as_string(SETTINGS) if FileAccess.file_exists(SETTINGS) else ""
	var clean := ConfigFile.new()
	clean.load(SETTINGS)
	if clean.has_section_key("hud", "spell_quickbar"): clean.erase_section_key("hud", "spell_quickbar")
	clean.set_value("hud", "ui_scale", 1.0)
	clean.set_value("hud", "combat_hud_position", Vector2(16, 100))
	clean.save(SETTINGS)
	var main := scene()
	await settle()
	var bar = main.casting_bar
	var items: Control = main.get_node("GameView/ItemQuickbar")
	var rail: Control = main.get_node("GameView/RightRail")
	var bottom: Control = main.get_node("GameView/Quickbar")
	check(bar.docked and bar.panel.visible and not bar.launcher.visible, "the fresh HUD shows the attached spell bar")
	check(bar.buttons.size() == 12, "all twelve saved shortcuts remain available")
	check(bar.visible_slot_count == 6, "the HUD defaults to six quick spell icons")
	check(rail.get_global_rect().encloses(bar.panel.get_global_rect()), "the dock sits inside the HUD rail beside the item slots")
	check_hud_dock(main)
	for index in range(bar.buttons.size()):
		var button: Button = bar.buttons[index]
		check(button.get_parent().visible == (index < 6), "only the six default slots are shown")
		if index < 6:
			check(bar._scroll.get_global_rect().encloses(button.get_global_rect()), "all six docked shortcuts fit at 1280 by 720")
	check(bar.panel.get_global_rect().end.y < bottom.global_position.y, "the attached bar clears the bottom HUD")
	main.spell_loadout.assign_slot(0, 1, 10)
	var app := root.get_node("AppState")
	for index in range(8):
		app.inventory[index] = {"image_id": [3, 31, 35, 42][index % 4], "quantity": index + 1, "slot": index, "inventory_usable": true}
	main.call("_sync_inventory")
	await settle()
	check(main.quick_slot_buttons.size() == 8, "all eight item shortcuts are preserved")
	var item_view: ScrollContainer = items as ScrollContainer
	item_view.ensure_control_visible(main.quick_slot_buttons[7])
	await settle()
	check(item_view.get_global_rect().encloses(main.quick_slot_buttons[7].get_global_rect()), "the eighth item remains reachable by scrolling")
	check(main.quick_slot_buttons[7].icon != null and not main.quick_slot_buttons[7].disabled, "the eighth item retains its artwork and usable state")
	item_view.scroll_vertical = 0
	await settle()
	check_hud_dock(main)
	app.actors[42] = {"name": "Mira", "kind": 1, "alive": true, "health": 40}
	app.select_actor(42)
	await settle()
	var slot: Button = bar.buttons[0]
	var target: Label = slot.get_node("Target")
	var power: Label = slot.get_node("Power")
	check(target.text == "T" and power.text == "10", "badges retain the target letter and two-digit power")
	check(target.has_theme_stylebox_override("normal") and power.has_theme_stylebox_override("normal"), "both corner labels have opaque backings")
	check(not target.get_rect().intersects(power.get_rect()), "target and power ten fit in separate corners")
	var shortcut: Label = slot.get_node("Shortcut")
	check(not target.get_rect().intersects(shortcut.get_rect()) and not power.get_rect().intersects(shortcut.get_rect()), "the shortcut number fits between the target and power: %s, %s, %s" % [target.get_rect(), shortcut.get_rect(), power.get_rect()])
	var slot_style: StyleBox = slot.get_theme_stylebox("normal")
	var art_size: Vector2 = slot.size - slot_style.get_minimum_size()
	check(art_size.x >= 26 and art_size.y >= 26 and slot.get_theme_constant("icon_max_width") >= 26, "each docked spell has a larger readable square of artwork")
	check(slot_style.get_content_margin(SIDE_TOP) >= maxf(target.get_rect().end.y, power.get_rect().end.y), "the target and power badges sit above the spell artwork: %s, %s" % [slot_style.get_content_margin(SIDE_TOP), maxf(target.get_rect().end.y, power.get_rect().end.y)])
	check(slot.tooltip_text.contains("Target: click the recipient") and not slot.tooltip_text.contains("Mira")
		and slot.tooltip_text.contains("Power 10"), "the tooltip says a target is clicked, never pre-chosen, and gives the power")
	check(slot.modulate.a == 1 and target.modulate.a == 1, "unavailable spells do not fade their corner badges")
	# Exercise the same clear action as the context menu, including its refresh.
	main.spell_loadout.path = "user://spell-bar-clear-regression.cfg"
	main.spell_loadout.load_profile("clear-slot-regression")
	main.spell_loadout.assign_slot(0, 1, 10)
	for attempt in range(2):
		bar.buttons[1].tooltip_text = "refresh did not finish"
		var right_click := InputEventMouseButton.new()
		right_click.button_index = MOUSE_BUTTON_RIGHT
		right_click.pressed = true
		bar.call("_slot_input", right_click, 0)
		bar.menu.id_pressed.emit(1)
		bar.menu.hide()
		await settle()
		check(main.spell_loadout.slots[0].id == -1 and slot.icon == null and slot.text == "+", "clearing a slot leaves an empty assignable button")
		check(not target.visible and not power.visible and slot.self_modulate.a == 1, "an empty slot clears its badges and dimming")
		check(bar.buttons[1].tooltip_text != "refresh did not finish", "clearing a slot completes the refresh of later slots")
	var restored_loadout = load("res://src/ui/spell_loadout.gd").new()
	restored_loadout.configure(main.spell_catalog)
	restored_loadout.path = main.spell_loadout.path
	restored_loadout.load_profile("clear-slot-regression")
	check(restored_loadout.slots[0].id == -1, "the cleared slot survives a profile reload")
	slot.spell_dropped.emit(1, 10)
	await settle()
	check(slot.spell_id == 1 and slot.icon != null and target.visible and power.text == "10", "a cleared slot accepts a new spell and restores its badges")
	await capture("docked.png")
	# Drag through the same viewport events a player sends, rather than
	# setting position directly. An ordinary grip click must keep it attached.
	var grip_position: Vector2 = bar.grip.get_global_rect().get_center()
	var hover := InputEventMouseMotion.new()
	hover.position = grip_position
	hover.global_position = grip_position
	root.push_input(hover, true)
	mouse(grip_position, true)
	mouse(grip_position, false)
	await settle()
	check(bar.docked, "clicking the grip does not detach the bar")
	mouse(grip_position, true)
	var motion := InputEventMouseMotion.new()
	motion.position = grip_position + Vector2(-250, 12)
	motion.global_position = motion.position
	motion.relative = Vector2(-250, 12)
	motion.button_mask = MOUSE_BUTTON_MASK_LEFT
	root.push_input(motion, true)
	mouse(motion.position, false)
	await settle()
	check(not bar.docked and bar.panel.position.x < items.position.x - 150, "dragging the grip detaches and moves the bar")
	check(rail.get_global_rect().encloses(items.get_global_rect()) and main.quick_slot_buttons[0].get_theme_constant("icon_max_width") == 26, "detaching spells keeps compact item shortcuts in the HUD")
	check(bar.buttons[0].size.x >= 36, "detaching restores the larger floating spell icons")
	var detached: Vector2 = bar.panel.position
	var saved := ConfigFile.new()
	saved.load(SETTINGS)
	var layout: Dictionary = saved.get_value("hud", "spell_quickbar", {})
	check(not bool(layout.get("docked", true)) and layout.get("position") == detached, "drag release saves detached placement")
	await capture("detached.png")
	main.free()
	await settle()
	main = scene()
	await settle()
	bar = main.casting_bar
	check(not bar.docked and bar.panel.position.is_equal_approx(detached), "a new scene restores the detached bar position")
	check(main.right_rail.get_global_rect().encloses(main.get_node("GameView/ItemQuickbar").get_global_rect()), "a session restored with detached spells keeps the item shortcuts in the rail")
	bar.call("_dock_menu_action", 0)
	await settle()
	items = main.get_node("GameView/ItemQuickbar")
	rail = main.get_node("GameView/RightRail")
	check(bar.docked and rail.get_global_rect().encloses(bar.panel.get_global_rect()), "Attach to HUD returns the bar inside the rail beside item slots")
	check_hud_dock(main)
	bar.dock_menu.get_popup().id_pressed.emit(2)
	await settle()
	check(main.settings_window.is_open(), "the compact menu opens ring and casting settings")
	main.spell_loadout.assign_slot(11, 69, 3)
	bar.slot_count_picker.item_selected.emit(bar.slot_count_picker.get_item_index(12))
	await settle()
	check(bar.visible_slot_count == 12 and bar.buttons[11].get_parent().visible and bar.buttons[11].spell_id == 69, "showing more icons keeps the extra saved spells")
	bar._scroll.ensure_control_visible(bar.buttons[11])
	await settle()
	check(bar._scroll.get_global_rect().encloses(bar.buttons[11].get_global_rect()), "all twelve larger shortcuts remain reachable by scrolling")
	bar.slot_count_picker.item_selected.emit(bar.slot_count_picker.get_item_index(6))
	await settle()
	check(main.spell_loadout.slots[11] == {"id": 69, "power": 3}, "returning to six icons preserves hidden assignments")
	check_hud_dock(main)
	bar.ring_size_picker.item_selected.emit(bar.ring_size_picker.get_item_index(125))
	check(main.spell_loadout.ring_size == 125, "the menu keeps the ring size control functional")
	main.settings_window.close()
	await settle()
	check(not main.settings_window.is_open() and bar.panel.visible, "Done dismisses settings without hiding the bar")
	# Resize the actual HUD canvas, then test a high UI scale as well.
	for dimensions in [Vector2i(960, 600), Vector2i(2559, 1531), Vector2i(1600, 900)]:
		root.size = dimensions
		await settle()
		check(Rect2(Vector2.ZERO, main.size).encloses(bar.panel.get_rect()), "the attached bar fits after resizing to " + str(dimensions))
		check(rail.get_global_rect().encloses(bar.panel.get_global_rect()), "the resized dock remains inside the rail")
		check_hud_dock(main)
	main.call("_on_ui_scale_changed", 1.5)
	await settle()
	check(Rect2(Vector2.ZERO, main.size).encloses(bar.panel.get_rect()), "the bar remains accessible at 150 percent HUD scale")
	check_hud_dock(main)
	bar._scroll.ensure_control_visible(bar.buttons[bar.visible_slot_count - 1])
	await settle()
	check(bar._scroll.get_global_rect().encloses(bar.buttons[bar.visible_slot_count - 1].get_global_rect()), "the last shown slot remains reachable when the dock needs scrolling")
	bar._scroll.scroll_vertical = 0
	await capture("docked-scaled.png")
	bar.set_visible_slot_count(8)
	bar.set_expanded(false)
	await settle()
	check_hud_dock(main)
	main.free()
	await settle()
	main = scene()
	await settle()
	bar = main.casting_bar
	check(bar.docked and not bar.panel.visible and bar.launcher.visible, "attachment and explicit hiding both survive a reload")
	check(bar.visible_slot_count == 8, "the chosen number of quick spell icons survives a reload")
	check_hud_dock(main)
	bar.launcher.pressed.emit()
	await settle()
	check(bar.panel.visible and not bar.launcher.visible, "the HUD launcher reopens the saved dock")
	check_hud_dock(main)
	main.free()
	await settle()
	var restore := FileAccess.open(SETTINGS, FileAccess.WRITE)
	restore.store_string(original)
	restore.close()
	NativeAnimationImporter.clear()
	GlbSceneCache.clear()
	print("spell bar docking: ", "PASS" if failures == 0 else "FAIL (%d)" % failures)
	quit(failures)

func mouse(where: Vector2, pressed: bool) -> void:
	var event := InputEventMouseButton.new()
	event.position = where
	event.global_position = where
	event.button_index = MOUSE_BUTTON_LEFT
	event.button_mask = MOUSE_BUTTON_MASK_LEFT if pressed else 0
	event.pressed = pressed
	root.push_input(event, true)
