extends SceneTree
const Presets := preload("res://src/ui/inventory_presets.gd")
const FOLDER := "res://test-artifacts/inventory-designs"
var failures := 0
var checks := 0
var main: Control
var workspace: Control
var app: Node

func _init() -> void: call_deferred("run")

func expect(value: bool, label: String) -> void:
	checks += 1
	if value: print("PASS: ", label)
	else:
		failures += 1
		push_error(label)

func frames(count := 5) -> void:
	for index: int in count: await process_frame

func run() -> void:
	create_timer(100).timeout.connect(func() -> void: quit(99))
	var fresh := Presets.new()
	expect(fresh.active == "unified" and fresh.working.recipe == "unified", "Unified compact is the default for new players")
	DirAccess.make_dir_recursive_absolute(ProjectSettings.globalize_path(FOLDER))
	root.get_node("Network").block_for_hud_preview()
	root.size = Vector2i(1280, 720)
	root.gui_embed_subwindows = true
	app = root.get_node("AppState")
	main = (load("res://src/app/main.tscn") as PackedScene).instantiate()
	main.get_node("GameView/ChatWindow").preferences_path = FOLDER.path_join("isolated_%d.cfg" % Time.get_ticks_usec())
	root.add_child(main)
	await frames(8)
	main.get_node("LoginPanel").hide()
	main.get_node("LoginBackground").hide()
	main.game_view.show()
	workspace = main.inventory_workspace
	expect(workspace.model.active == "unified", "a fresh player profile opens Unified compact")
	app.set("inventory", {0: {"image_id": 1, "quantity": 24, "inventory_usable": true},
		1: {"image_id": 35, "quantity": 1, "inventory_usable": false},
		36: {"image_id": 8, "quantity": 1, "inventory_usable": false}})
	app.set("inventory_names", {0: "Hearth Bread", 1: "Iron Sword", 36: "Leather Armor"})
	app.set("stats", {"carried": 205, "capacity": 320})
	main.selected_inventory_slot = 0
	main.inventory_panel.show()
	main._sync_inventory()
	await _check_bulk_shortcuts()
	var pack_buttons: Array = main.inventory_slot_buttons.duplicate()
	var worn_buttons: Array = main.equipment_slot_buttons.duplicate()
	var hud_before: Dictionary = main.hud_workspace.model.working.duplicate(true)
	var pouch = workspace.reagent_pouch
	expect(pouch.look_button.text.is_empty() and pouch.store_button.text.is_empty() and pouch.drop_button.text.is_empty() and pouch.mix_button.text.is_empty(), "pouch shortcuts use icons with no word labels")
	expect(pouch.look_button.icon != null and pouch.store_button.icon != null and pouch.drop_button.icon != null and pouch.mix_button.icon != null, "pouch shortcuts reuse the real game artwork")
	expect(pouch.auxiliary.global_position.x < pouch.contents.global_position.x, "gold and shortcuts occupy the space beneath Equipment")
	main.manufacturing_panel.hide()
	pouch.mix_button.pressed.emit()
	expect(main.manufacturing_panel.visible, "Mix opens the existing crafting window")
	main.manufacturing_panel.hide()
	main.inventory_panel.show()

	for id: String in Presets.BUILT_INS:
		workspace.choose_preset(id, true)
		await frames()
		var compact: bool = id in ["unified", "tabbed", "dock"]
		expect(workspace.bulk_actions.buttons.store.visible == not compact and workspace.bulk_actions.buttons.drop.visible == not compact and workspace.bulk_actions.buttons.mix.visible == not compact, id + " has the intended default text shortcuts")
		expect(main.inventory_slot_buttons.size() == 24 and main.equipment_slot_buttons.size() == 8, id + " retains all 24 pack and 8 wear slots")
		expect(main.inventory_slot_buttons == pack_buttons and main.equipment_slot_buttons == worn_buttons, id + " reuses live controls and their signals")

		if id == "tabbed":
			expect(main.inventory_slot_buttons[0].custom_minimum_size.x >= 48, "Tabbed satchel uses larger item icons")
			var pack_end: float = workspace.groups.backpack.position.y + workspace.groups.backpack.size.y
			expect(is_equal_approx(workspace.groups.pouch.position.y - pack_end, 8.0), "Tabbed satchel places the pouch directly after the backpack without reserved blank space")
		if id == "dock":
			expect(main.inventory_slot_buttons[0].custom_minimum_size.x >= 60 and main.equipment_slot_buttons[0].custom_minimum_size.x >= 44, "Edge dock uses larger backpack and equipment icons")
			var equipment_rect: Rect2 = workspace.groups.equipment.get_rect()
			var pouch_rect: Rect2 = workspace.groups.pouch.get_rect()
			expect(is_equal_approx(equipment_rect.position.y, pouch_rect.position.y) and pouch_rect.position.x >= equipment_rect.end.x + 8, "Edge dock puts the pouch at the top right beside equipment")
			expect(workspace.groups.backpack.position.y >= maxf(equipment_rect.end.y, pouch_rect.end.y) + 8, "Edge dock keeps the backpack clear of both top-row sections")
		var bounds: Rect2 = main.inventory_panel.get_global_rect()
		expect(bounds.position.x >= -1 and bounds.position.y >= -1 and bounds.end.x <= main.game_view.size.x + 1 and bounds.end.y <= main.game_view.size.y + 1, id + " fits 1280x720")
		workspace.request_inspection(0, true)
		workspace.present_detail(_bread(), true)
		await frames()
		expect(workspace.inspection_title.text == "Hearth Bread" and workspace.inspection_text.text.contains("Restores 40 food"), id + " shows authoritative item details")
		if id == "popover": expect(main.extension_windows.detail_panel.visible, "popover uses a compact external card")
		else: expect(not main.extension_windows.detail_panel.visible, id + " has no separate item modal")
		workspace.close_inspection()
	expect(main.hud_workspace.model.working == hud_before, "inventory design selection preserves the player's HUD")
	workspace.choose_preset("tabbed", true)
	await frames()
	var pack_size: Vector2 = main.inventory_panel.size
	workspace.request_inspection(0, true)
	workspace.present_detail(_bread(), true)
	await frames()
	expect(main.inventory_panel.size.is_equal_approx(pack_size), "tabbed Pack and Inspect occupy the same rectangle")
	workspace.open_editor()
	var before: Dictionary = workspace.model.snapshot()
	workspace.change_part("backpack", "columns", 9)
	expect(main.inventory_grid.columns == 9, "column changes reflow the real grid live")
	workspace.undo_edit()
	expect(main.inventory_grid.columns == 6, "Undo restores grid geometry")
	workspace.undo_edit(true)
	expect(main.inventory_grid.columns == 9, "Redo restores the edit")
	workspace.change_option("background", Color("283228ee"))
	workspace.choose_preset("tray", true)
	workspace.finish_edit(false)
	expect(workspace.model.snapshot() == before, "Cancel restores the design and all preset caches")
	expect(not workspace.is_editing() and not main._world_input_blocked(), "leaving the editor restores gameplay input")
	workspace.open_editor()
	workspace.change_part("backpack", "cell", 40)
	var custom_id: String = workspace.model.save_custom("My satchel")
	workspace.finish_edit(true)
	var reloaded := Presets.new()
	reloaded.load_file(workspace.preferences_path)
	expect(reloaded.active == custom_id and reloaded.working.parts.backpack.cell == 40, "saved custom design survives reopening")
	workspace.choose_preset("unified", true)
	workspace.open_editor()
	workspace.change_part("backpack", "columns", 12)
	workspace.choose_preset("dock", true)
	workspace.choose_preset("unified")
	expect(workspace.model.working.parts.backpack.columns == 12, "switching presets retains per-preset edits")
	workspace.finish_edit(false)
	workspace.choose_preset("popover", true)
	workspace.request_inspection(0, true)
	workspace.present_detail(_bread(), true)
	await frames()
	workspace._pinned = true
	main.inventory_panel.hide()
	await frames()
	expect(main.extension_windows.detail_panel.visible, "a pinned card remains visible when inventory closes")
	workspace.close_inspection()
	await frames()
	expect(not main.extension_windows.detail_panel.visible, "closing the pinned card dismisses its independent window")
	main.inventory_panel.show()
	workspace.choose_preset("unified", true)
	var shortcuts: Array = main._inventory_quantities.duplicate()
	workspace._quantity_submitted("17")
	expect(main._selected_quantity() == 17 and main._inventory_quantities == shortcuts, "typing an amount preserves the player's six quantity shortcuts")
	app.get("inventory")[0].quantity = 2000000000
	workspace._quantity_all()
	expect(main._selected_quantity() == 2000000000, "All retains the complete server stack amount beyond seven digits")
	main._on_quantity_box_pressed(1)
	expect(main._selected_quantity() == shortcuts[1], "choosing a shortcut clears the temporary quantity")
	main._on_quantity_box_pressed(0)
	app.get("inventory")[0].quantity = 24
	workspace.search.text = "bread"
	workspace.search.text_changed.emit("bread")
	expect(main.inventory_slot_buttons[0].self_modulate.a == 1 and main.inventory_slot_buttons[1].self_modulate.a < 1,
		"search dims nonmatches without moving or hiding server positions")
	workspace.search.text = ""
	workspace.search.text_changed.emit("")
	expect(main.inventory_slot_buttons[1].self_modulate.a == 1, "clearing search restores every slot")
	workspace.open_editor()
	var window_position: Vector2 = main.inventory_panel.position
	var press := InputEventMouseButton.new()
	press.button_index = MOUSE_BUTTON_LEFT
	press.pressed = true
	press.position = workspace.header.get_global_rect().get_center()
	workspace.handle_editor_input(press)
	var motion := InputEventMouseMotion.new()
	motion.position = press.position - Vector2(80, 0)
	workspace.handle_editor_input(motion)
	expect(main.inventory_panel.position.x < window_position.x and workspace.model.working.anchor == "free", "the inventory header moves the whole window during editing")
	press.pressed = false
	workspace.handle_editor_input(press)
	workspace.finish_edit(false)
	main.classic_storage._attach_inventory()
	workspace.apply_layout()
	expect(main.classic_storage.is_inventory_docked() and main.inventory_panel.get_parent() == main.classic_storage.body,
		"storage can still dock the customized real inventory")
	main.classic_storage._detach_inventory()
	workspace.apply_layout()
	expect(main.inventory_panel.get_parent() == main.game_view and main.inventory_grid.get_child_count() == 24,
		"undocking restores the customized inventory and all its controls")
	workspace.open_editor()
	workspace.editor.select_component("pouch")
	expect(workspace.editor.selected == "pouch", "Pouch is a selectable inventory customization section")
	workspace.change_part("pouch", "columns", 8)
	workspace.change_part("pouch", "cell", 58)
	workspace.change_part("pouch", "offset", Vector2(12, 9))
	workspace.change_part("pouch", "show_quantity", false)
	workspace.change_part("pouch", "icon_opacity", 0.5)
	workspace.apply_layout()
	expect(workspace.reagent_pouch.grid.columns == 8 and workspace.reagent_pouch.slots[0].custom_minimum_size == Vector2(58, 58), "pouch columns and slot size apply to the live controls")
	expect(not workspace.reagent_pouch.counts[0].visible and is_equal_approx(workspace.reagent_pouch.slots[0].get_theme_color("icon_normal_color").a, 0.5), "pouch quantity display and icon opacity are customizable")
	var pouch_design: Dictionary = workspace.model.working.duplicate(true)
	var normalised: Dictionary = Presets.normalise(pouch_design)
	expect(normalised.parts.pouch.offset == Vector2(12, 9) and normalised.parts.pouch.columns == 8, "pouch customization survives saved-design normalization")
	workspace.finish_edit(false)
	expect(workspace.model.working.parts.pouch != pouch_design.parts.pouch, "Cancel restores the previous pouch customization")
	var saved_pouch := Presets.new()
	saved_pouch.working = pouch_design
	var custom_pouch_id := saved_pouch.save_custom("Pouch layout")
	var pouch_file := FOLDER.path_join("pouch_roundtrip_%d.cfg" % Time.get_ticks_usec())
	expect(saved_pouch.save_file(pouch_file) == OK, "a custom pouch design saves to the player settings file")
	var loaded_pouch := Presets.new()
	loaded_pouch.load_file(pouch_file)
	expect(loaded_pouch.active == custom_pouch_id and loaded_pouch.working.parts.pouch == pouch_design.parts.pouch, "a saved custom pouch design reloads with all section options")
	var legacy_layout: Dictionary = Presets.preset("unified")
	legacy_layout.parts.erase("pouch")
	legacy_layout.parts.backpack.cell = 42
	var upgraded: Dictionary = Presets.normalise(legacy_layout)
	expect(upgraded.parts.pouch.columns == 4 and upgraded.parts.backpack.cell == 42, "older player layouts gain the pouch while retaining their customization")
	var standalone := Presets.new()
	var ids: Array[String] = []
	for index: int in 5: ids.append(standalone.save_custom("Design %d" % index))
	expect(standalone.custom.size() == 5 and standalone.save_custom("Sixth").is_empty(), "custom designs stop at five without overwriting saved designs")
	expect(standalone.save_custom("Renamed", ids[0]) == ids[0] and standalone.custom.size() == 5, "a custom design can update at capacity")
	standalone.delete_custom(ids[0])
	expect(standalone.custom.size() == 4 and standalone.active == Presets.DEFAULT, "deleting the active custom design recovers a built-in layout")
	var config := ConfigFile.new()
	config.load(workspace.preferences_path)
	config.set_value("unrelated_settings", "sentinel", "preserved")
	config.save(workspace.preferences_path)
	workspace.store()
	config.load(workspace.preferences_path)
	expect(config.get_value("unrelated_settings", "sentinel", "") == "preserved", "inventory persistence keeps the other HUD and settings sections")
	workspace.request_inspection(0, true)
	var unrelated := _bread()
	unrelated.image_id = 999
	workspace.present_detail(unrelated, true)
	expect(workspace._detail_slot != 1, "mismatched late detail never targets a different inventory item")
	workspace.request_inspection(0, true)
	workspace.present_detail(_bread(), true)
	app.get("inventory_cooldowns")[0] = {"end_msec": Time.get_ticks_msec() + 30000}
	workspace.refresh_actions()
	expect((workspace.inspection_actions.get_node("use") as Button).disabled, "inspection Use follows an active cooldown")
	app.get("inventory_cooldowns")[0].end_msec = Time.get_ticks_msec() - 1
	workspace.refresh_actions()
	expect(not (workspace.inspection_actions.get_node("use") as Button).disabled, "inspection Use becomes available when cooldown expires")
	app.get("inventory_cooldowns").clear()
	app.get("inventory").erase(0)
	workspace.sync_inventory()
	var any_enabled := false
	for button: Button in workspace.inspection_actions.get_children(): any_enabled = any_enabled or (button.visible and not button.disabled)
	expect(not any_enabled, "inspection actions stop when the inspected item leaves its slot")
	# Malformed saved preferences cannot create non-finite positions or erase slots.
	var invalid := Presets.preset("unified")
	invalid.scale = NAN
	invalid.position = Vector2(INF, 1)
	invalid.parts.backpack.columns = -999
	invalid.parts.backpack.enabled = false
	var repaired := Presets.normalise(invalid)
	expect(is_finite(repaired.scale) and repaired.position.is_finite() and repaired.parts.backpack.columns >= 1 and repaired.parts.backpack.enabled, "invalid preferences recover safely")
	print("INVENTORY WORKSPACE: ", checks, " checks, ", failures, " failures")
	main.queue_free()
	await frames()
	quit(1 if failures > 0 else 0)

func _bread() -> Dictionary:
	return {"open": true, "image_id": 1, "name": "Hearth Bread", "category": "Food", "quantity": 24,
		"description": "Baked before dawn at the Four Gates ovens.", "stats": "Restores 40 food. Weight 2.", "equipped": false}

func _click_action(button: Button, mouse_button: int) -> void:
	var event := InputEventMouseButton.new()
	event.position = button.get_global_rect().get_center()
	event.global_position = event.position
	event.button_index = mouse_button
	event.pressed = true
	root.push_input(event, true)
	event.pressed = false
	root.push_input(event, true)
	await frames(2)

func _check_bulk_shortcuts() -> void:
	workspace.choose_preset("unified", true)
	await frames()
	var pouch = workspace.reagent_pouch
	var bulk = workspace.bulk_actions
	var counts := {"store": 0, "drop": 0, "mix": 0, "single": 0}
	main.inventory_store_all.pressed.connect(func() -> void: counts.store += 1)
	main.inventory_drop_all.pressed.connect(func() -> void: counts.drop += 1)
	main.inventory_mix_all.pressed.connect(func() -> void: counts.mix += 1)
	pouch.drop_button.pressed.connect(func() -> void: counts.single += 1)
	app.set("storage", {"open": false, "read_only": false})
	pouch.sync()
	expect(pouch.store_button.disabled, "Store remains unavailable without storage or a selected pouch item")
	await _click_action(pouch.store_button, MOUSE_BUTTON_MIDDLE)
	expect(main._store_options_menu.visible, "middle-click opens protection options on the disabled Store icon")
	main._store_options_menu.hide()
	await _click_action(pouch.store_button, MOUSE_BUTTON_RIGHT)
	expect(counts.store == 0 and not main._store_options_menu.visible, "right-click Store respects storage access and never opens options")
	main._bulk_exclusions.store = [true, false, false, false]
	main._sync_bulk_option_menus()
	expect(main._store_options_menu.is_item_checked(0) and main._inventory_slot_is_protected(5, "store") and not main._inventory_slot_is_protected(6, "store"), "Store menu and bulk action share protected slots")
	main.inventory_grid.columns = 12
	expect(main._inventory_slot_is_protected(11, "store") and not main._inventory_slot_is_protected(12, "store"), "protected rows follow the customized backpack columns")
	main._bulk_exclusions.store = [false, false, false, false]
	workspace.apply_layout()
	app.set("storage", {"open": true, "read_only": false})
	pouch.sync()
	await _click_action(pouch.store_button, MOUSE_BUTTON_RIGHT)
	expect(counts.store == 1, "right-click Store sends the all action even when no pouch item is selected")
	app.set("storage", {"open": false, "read_only": false})
	pouch.sync()
	await _click_action(pouch.drop_button, MOUSE_BUTTON_MIDDLE)
	expect(main._drop_options_menu.visible, "middle-click Drop opens its protection options")
	main._drop_options_menu.hide()
	await _click_action(pouch.drop_button, MOUSE_BUTTON_RIGHT)
	expect(bulk.confirmation.visible and counts.drop == 0 and counts.single == 0, "right-click Drop starts the existing bulk confirmation without a single-item drop")
	bulk.confirmation.confirmed.emit()
	bulk.confirmation.hide()
	expect(counts.drop == 1, "confirmed bulk Drop uses the same protected all action as the text button")
	await _click_action(pouch.mix_button, MOUSE_BUTTON_MIDDLE)
	expect(bulk.mix_options.visible and bulk.mix_options.is_item_disabled(bulk.mix_options.get_item_index(2)), "middle-click Mix opens recipe and source options, with storage access checked")
	bulk.mix_options.hide()
	await _click_action(pouch.mix_button, MOUSE_BUTTON_RIGHT)
	expect(counts.mix == 1 and main.manufacturing_panel.visible, "right-click Mix starts Mix All, opening recipe selection when needed")
	main.manufacturing_panel.hide()
	main.inventory_panel.show()
	app.trade = {"open": true}
	pouch.sync()
	await _click_action(pouch.mix_button, MOUSE_BUTTON_RIGHT)
	expect(counts.mix == 1, "right-click cannot bypass the trade lock on Mix")
	app.trade = {"open": false}
	pouch.sync()
	workspace.open_editor()
	workspace.editor.select_component("actions")
	for action: String in ["store", "drop", "mix"]: workspace.change_part("actions", "show_" + action, true)
	expect(bulk.buttons.store.visible and bulk.buttons.drop.visible and bulk.buttons.mix.visible, "the inventory editor can restore every text bulk shortcut")
	await _click_action(pouch.mix_button, MOUSE_BUTTON_RIGHT)
	expect(counts.mix == 1, "editing the inventory never starts a bulk action")
	workspace.finish_edit(false)
	workspace.choose_preset("unified", true)
	main._sync_bulk_option_menus()
	await frames()
