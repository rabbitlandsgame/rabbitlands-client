extends SceneTree
const Presets := preload("res://src/ui/hud_presets.gd")
const FOLDER := "res://test-artifacts/hud-launch"
var checks := 0
var failures := 0

func _init() -> void: call_deferred("run")

func expect(value: bool, label: String) -> void:
	checks += 1
	if value: print("PASS: ", label)
	else:
		failures += 1
		push_error(label)

func frames(count := 4) -> void:
	for index: int in count: await process_frame

func run() -> void:
	create_timer(100).timeout.connect(func() -> void: quit(99))
	DirAccess.make_dir_recursive_absolute(ProjectSettings.globalize_path(FOLDER))
	var model := Presets.new()
	expect(model.active == "heritage" and not model.working.legacy,
		"fresh profiles start on modern Classic")
	expect(Presets.BUILT_INS.values() == ["Classic", "Compact", "Modular", "Adventure", "Minimal"]
		and not Presets.BUILT_INS.has("current") and not Presets.STYLES.has("current"),
		"five simple preset names replace legacy choices")
	model.select("current")
	expect(model.active == "heritage" and not model.working.legacy, "retired preset aliases migrate to Classic")
	var ids: Array[String] = []
	for index: int in 5:
		model.working.parts.items.slots = index + 1
		ids.append(model.save_custom("Design %d" % (index + 1)))
	expect(model.custom.size() == 5 and "" not in ids, "five independent custom designs can be saved")
	var fifth: Dictionary = model.custom[ids[4]].duplicate(true)
	expect(model.save_custom("Sixth").is_empty() and model.custom[ids[4]] == fifth,
		"a sixth design is rejected without overwriting existing designs")
	expect(model.save_custom("Renamed fifth", ids[4]) == ids[4] and model.custom.size() == 5
		and model.custom[ids[4]].name == "Renamed fifth", "existing designs can update and rename at capacity")
	var path := FOLDER.path_join("custom-roundtrip.cfg")
	expect(model.save_file(path) == OK, "five custom designs save successfully")
	var reloaded := Presets.new()
	reloaded.load_file(path)
	expect(reloaded.custom.size() == 5 and reloaded.active == ids[4]
		and reloaded.working.parts.items.slots == 5, "all five designs and the active layout survive reopening")
	expect(not reloaded.delete_custom("heritage"), "built-in presets cannot be deleted")
	expect(reloaded.delete_custom(ids[4]) and reloaded.custom.size() == 4 and reloaded.active == "heritage",
		"deleting the selected custom frees a slot and selects Classic")
	expect(not reloaded.save_custom("Replacement").is_empty() and reloaded.custom.size() == 5,
		"a freed custom slot can be reused")
	# Profiles from the previous editor may contain six to twenty-four designs.
	var legacy := Presets._preset_recipe("current")
	legacy.chat_windows = {"chat":{"options":{"font_size":19}}}
	var config := ConfigFile.new()
	config.set_value("unrelated", "keep", "untouched")
	config.set_value(Presets.SECTION, "working", legacy)
	config.set_value(Presets.SECTION, "active", "current")
	var migration_path := FOLDER.path_join("legacy-migration.cfg")
	config.save(migration_path)
	var migrated := Presets.new()
	migrated.load_file(migration_path)
	expect(migrated.active == "heritage" and not migrated.working.legacy
		and migrated.working.parts.logo.dimensions == Presets.preset("heritage").parts.logo.dimensions
		and migrated.working.chat_windows.chat.options.font_size == 19,
		"legacy profiles migrate to Classic while retaining chat appearance")
	var old_custom := {}
	for index: int in 7: old_custom["custom_old_%d" % index] = {"name":"Older %d" % index, "layout":Presets.preset("adventure")}
	config.set_value(Presets.SECTION, "custom", old_custom)
	config.set_value(Presets.SECTION, "active", "custom_old_6")
	config.set_value(Presets.SECTION, "working", Presets.preset("adventure"))
	config.save(migration_path)
	migrated.load_file(migration_path)
	expect(migrated.custom.size() == 5 and migrated.custom.has("custom_old_6")
		and migrated.archived_custom.size() == 2, "migration keeps the selected custom and preserves excess older designs")
	migrated.save_file(migration_path)
	var saved := ConfigFile.new()
	saved.load(migration_path)
	expect(saved.get_value("unrelated", "keep") == "untouched"
		and saved.get_value(Presets.SECTION, "archived_custom").size() == 2,
		"saving preserves unrelated settings and archived excess designs")
	var archive_roundtrip := Presets.new()
	archive_roundtrip.load_file(migration_path)
	expect(archive_roundtrip.custom.size() == 5 and archive_roundtrip.archived_custom.size() == 2,
		"archived designs survive another load without filling a freed slot")
	# Exercise the actual player controls, including Undo and Cancel.
	root.get_node("Network").block_for_hud_preview()
	root.size = Vector2i(1440, 900)
	var fresh_path := FOLDER.path_join("new-install.cfg")
	ConfigFile.new().save(fresh_path)
	var main: Control = (load("res://src/app/main.tscn") as PackedScene).instantiate()
	main.get_node("GameView/ChatWindow").preferences_path = fresh_path
	root.add_child(main)
	await frames(8)
	main.get_node("LoginPanel").hide()
	main.get_node("LoginBackground").hide()
	main.game_view.show()
	var workspace: Control = main.hud_workspace
	expect(workspace.manages_layout() and workspace.model.active == "heritage"
		and not main.right_rail.visible and workspace.parts.rail_panel.visible,
		"a new client scene applies Classic automatically")
	expect(workspace.settings_picker.item_count == 5 and workspace.preset_picker.item_count == 5,
		"both preset pickers show exactly five built-in designs")
	workspace.open_editor()
	workspace.select_component("minimap")
	expect(workspace.selection_summary.text.contains("hidden")
		and workspace.component_picker.get_item_text(workspace.component_picker.selected).contains("hidden"),
		"hidden components are identified in the picker and selection summary")
	workspace.change_part("minimap", "enabled", true)
	expect(workspace.selection_summary.text.contains("visible")
		and not workspace.component_picker.get_item_text(workspace.component_picker.selected).contains("hidden"),
		"visibility labels update immediately after enabling a component")
	workspace.change_part("items", "slots", 4)
	workspace.select_component("minimap")
	workspace.reset_component_button.pressed.emit()
	expect(not workspace.model.working.parts.minimap.enabled and workspace.model.working.parts.items.slots == 4,
		"Reset part restores only the selected component")
	workspace.undo_edit()
	expect(workspace.model.working.parts.minimap.enabled and workspace.model.working.parts.items.slots == 4,
		"Undo reverses a component reset without changing other parts")
	workspace.choose_preset("adventure", true)
	workspace.select_component("medallion", 0)
	var untouched: Dictionary = workspace.model.working.parts.medallion.arcs[1].duplicate(true)
	workspace.change_arc(0, "thickness", 14)
	workspace.reset_component_button.pressed.emit()
	expect(workspace.model.working.parts.medallion.arcs[0].thickness == Presets.preset("adventure").parts.medallion.arcs[0].thickness
		and workspace.model.working.parts.medallion.arcs[1] == untouched, "Reset part targets just the selected resource curve")
	var snap: CheckBox = workspace.panel.find_child("HudEditorSnap", true, false)
	snap.button_pressed = false
	expect(not workspace._snap_enabled and not workspace._resize_snap_enabled, "one toolbar switch controls both docking and resizing snaps")
	snap.button_pressed = true
	var grid: CheckBox = workspace.panel.find_child("HudEditorGrid", true, false)
	grid.button_pressed = true
	expect(workspace._show_grid, "alignment grid can be enabled without changing the layout")
	workspace.cancel_edit()
	workspace.open_editor()
	for index: int in 5:
		workspace.preset_name.text = "Player design %d" % (index + 1)
		workspace.save_new_button.pressed.emit()
		await frames(2)
	expect(workspace.model.custom.size() == 5 and workspace.save_new_button.disabled
		and not workspace.update_custom_button.disabled and workspace.custom_count_label.text.ends_with("5 / 5"),
		"the editor shows five used slots and keeps Update available")
	workspace.delete_custom_button.pressed.emit()
	expect(workspace.model.custom.size() == 4 and not workspace.save_new_button.disabled
		and workspace.delete_custom_button.disabled, "Delete frees a slot and cannot delete the selected built-in")
	workspace.undo_button.pressed.emit()
	expect(workspace.model.custom.size() == 5 and not workspace.delete_custom_button.disabled,
		"Undo recovers a deleted custom design")
	expect(workspace.commit() == OK, "Done and save commits the player's custom collection")
	workspace.panel.hide()
	workspace.open_editor()
	workspace.delete_custom_button.pressed.emit()
	workspace.cancel_edit()
	expect(workspace.model.custom.size() == 5, "Cancel recovers the custom collection from before editing")
	main.queue_free()
	await frames(2)
	print("CUSTOM HUD DESIGNS: %d checks, %d failures" % [checks, failures])
	quit(0 if failures == 0 else 1)
