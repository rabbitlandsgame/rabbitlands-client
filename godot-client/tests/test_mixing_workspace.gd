extends SceneTree
const Presets := preload("res://src/ui/mixing_presets.gd")
const Fixture := preload("res://tests/fixtures/mixing_window_fixture.gd")
var checks := 0
var failures := 0
var main: Control
var workspace: Control
func _init() -> void: call_deferred("run")
func expect(value: bool, label: String) -> void:
	checks += 1
	if value: print("PASS: ", label)
	else:
		failures += 1
		push_error(label)
func frames(count := 6) -> void:
	for frame: int in count: await process_frame
func run() -> void:
	create_timer(100).timeout.connect(func() -> void: quit(99))
	root.get_node("Network").block_for_hud_preview()
	root.size = Vector2i(1280, 720)
	DirAccess.make_dir_recursive_absolute(ProjectSettings.globalize_path("res://test-artifacts/mixing-designs"))
	main = (load("res://src/app/main.tscn") as PackedScene).instantiate()
	main.get_node("GameView/ChatWindow").preferences_path = "res://test-artifacts/mixing-designs/test_%d.cfg" % Time.get_ticks_usec()
	root.add_child(main)
	await frames(10)
	main.get_node("LoginPanel").hide()
	main.get_node("LoginBackground").hide()
	main.game_view.show()
	var recipe := Fixture.populate(main)
	workspace = main.mixing_workspace
	await frames()
	var list: ItemList = main.manufacturing_list
	var quantity: LineEdit = main.manufacturing_quantity
	var mix: Button = main.manufacturing_mix_one
	var inventory_before: Dictionary = main.inventory_workspace.model.snapshot()
	var hud_before: Dictionary = main.hud_workspace.model.working.duplicate(true)
	expect(workspace.model.active == "workbench", "Compact workbench is the starting preset")
	for id: String in Presets.BUILT_INS:
		workspace.choose_preset(id, true)
		await frames()
		expect(main.manufacturing_list == list and main.manufacturing_quantity == quantity and main.manufacturing_mix_one == mix, id + " reuses the original recipe, quantity and action controls")
		expect(main.selected_manufacturing_recipe == recipe and main._manufacturing_quantity_value() == 20, id + " preserves recipe and batch quantity")
		var bounds: Rect2 = main.manufacturing_panel.get_global_rect()
		var available: Rect2 = workspace._available_rect()
		expect(available.grow(1).encloses(bounds), id + " stays inside the viewport and outside the HUD")
		expect(workspace.selector.get_item_text(0) == "Bandage", id + " shows the selected authoritative recipe")
		expect(not mix.disabled, id + " preserves the available mixing action")
		var controls_fit := true
		for control: Control in workspace.groups.controls.get_child(0).get_children():
			if not control.is_visible_in_tree(): continue
			controls_fit = controls_fit and workspace.groups.controls.get_global_rect().grow(1).encloses(control.get_global_rect())
		expect(controls_fit, id + " keeps source and quantity controls inside their section")
	expect(main.inventory_workspace.model.snapshot() == inventory_before and main.hud_workspace.model.working == hud_before, "mixing choices preserve the inventory and HUD designs")
	workspace.choose_preset("tabbed", true)
	await frames()
	var size_before: Vector2 = main.manufacturing_panel.size
	workspace._tab = 2
	workspace.apply_layout()
	expect(main.manufacturing_panel.size == size_before, "Mix and Queue tabs share one footprint")
	expect(workspace.queue_scroll.visible and not workspace.groups.details.visible, "Queue tab reveals its queue without an extra window")
	workspace.open_editor()
	var before: Dictionary = workspace.model.snapshot()
	workspace.change_part("details", "dimensions", Vector2(280, 260))
	expect(workspace.model.working.parts.details.dimensions == Vector2(280, 260), "editor resizes the live requirement section")
	workspace.undo_edit()
	expect(workspace.model.snapshot() == before, "Undo restores the design")
	workspace.undo_edit(true)
	expect(workspace.model.working.parts.details.dimensions.x == 280, "Redo restores the edit")
	workspace.choose_preset("tray", true)
	workspace.finish_edit(false)
	expect(workspace.model.snapshot() == before, "Cancel restores the whole preset and custom-design snapshot")
	workspace.open_editor()
	workspace.change_option("font_size", 13)
	var custom_id: String = workspace.model.save_custom("My workbench")
	workspace.finish_edit(true)
	var reloaded := Presets.new()
	reloaded.load_file(workspace.preferences_path)
	expect(reloaded.active == custom_id and reloaded.working.font_size == 13, "saved custom design survives reload")
	workspace.choose_preset("workbench", true)
	workspace.open_editor()
	var at: Vector2 = main.manufacturing_panel.position
	var press := InputEventMouseButton.new()
	press.button_index = MOUSE_BUTTON_LEFT
	press.pressed = true
	press.position = workspace.header.get_global_rect().position + Vector2(12, 10)
	workspace.handle_editor_input(press)
	var motion := InputEventMouseMotion.new()
	motion.position = press.position + Vector2(-30, 15)
	workspace.handle_editor_input(motion)
	expect(main.manufacturing_panel.position != at and workspace.model.working.anchor == "free", "editor header dragging moves and remembers the whole window")
	workspace.finish_edit(false)
	workspace.choose_preset("tabbed", true)
	main._set_manufacturing_quantity(999999)
	expect(main._manufacturing_quantity_value() == 1000, "batch quantity retains the existing 1,000-item limit")
	main._set_manufacturing_quantity(20)
	workspace.choose_preset("popover", true)
	main.get_node("/root/AppState").inventory.erase(2)
	main.get_node("/root/AppState").inventory_names.erase(2)
	main._sync_manufacturing()
	await frames()
	expect(mix.disabled, "missing tool disables Mix now")
	expect(workspace.details.find_children("*", "Button", true, false).any(func(button: Node) -> bool: return button is Button and button.text.begins_with("Take")), "missing tool has a storage recovery action")
	workspace.storage_source.pressed.emit()
	await frames()
	expect(main._manufacturing_from_storage(), "storage source uses the original server-authorized toggle")
	expect(workspace.details.find_children("*", "Label", true, false).any(func(label: Node) -> bool: return label is Label and label.text.contains("? / 40")), "storage requirements show unknown stock instead of inventing counts")
	main.get_node("/root/AppState").mix_state.near_storage = false
	main._sync_manufacturing()
	await frames()
	expect(not main._manufacturing_from_storage() and workspace.storage_source.disabled, "leaving storage restores inventory source and disables storage")
	var outside := InputEventMouseButton.new()
	outside.button_index = MOUSE_BUTTON_LEFT
	outside.pressed = true
	outside.position = Vector2(20, 20)
	workspace.pin.pressed.emit()
	workspace._unhandled_input(outside)
	expect(main.manufacturing_panel.visible, "a pinned quick-mix card remains open when clicking the world")
	workspace.pin.pressed.emit()
	workspace._unhandled_input(outside)
	expect(not main.manufacturing_panel.visible, "an unpinned quick-mix card dismisses on a world click")
	var limited := Presets.new()
	for index: int in 5: expect(not limited.save_custom("Design%d" % index).is_empty(), "custom design %d is saved" % (index + 1))
	expect(limited.save_custom("Overflow").is_empty(), "custom mixing designs stop at five without overwriting")
	var malformed := Presets.normalise({"scale": NAN, "parts": {"details": {"dimensions": Vector2(INF, NAN)}}})
	expect(is_finite(malformed.scale) and malformed.parts.details.dimensions.is_finite(), "invalid saved dimensions and scale recover safely")
	print("MIXING WORKSPACE: %d checks, %d failures" % [checks, failures])
	main.queue_free()
	await frames()
	quit(0 if failures == 0 else 1)
