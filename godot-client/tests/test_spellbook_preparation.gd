extends SceneTree
## Exercises the live book with a loadout, selected variants and long quotes.
var failures := 0

func _init() -> void:
	call_deferred("run")

func check(condition: bool, message: String) -> void:
	if not condition:
		failures += 1
		push_error("FAIL: " + message)

func settle() -> void:
	for frame in range(8): await process_frame

func run() -> void:
	root.size = Vector2i(1280, 720)
	var main := (load("res://src/app/main.tscn") as PackedScene).instantiate()
	root.add_child(main)
	await settle()
	main.get_node("LoginPanel").hide()
	main.game_view.show()
	var book: Control = main.spells_window
	var model = main.spell_loadout
	model.profile = ""
	model.assign_slot(1, 68, 1)
	book.edit_prepared_slot(1)
	book.scope_filter.select(4)
	book.call("_filter_spells")
	check(book.selected_spell_id == 69, "filtering the selected Fire family to Burst selects Fire Burst instead of retaining Fire Target")
	var assign := book.find_child("AssignSpell", true, false) as Button
	if assign != null:
		assign.pressed.emit()
		check(model.slots[1].id == 69, "Assign saves the Burst variant to the edited quick slot")
	else:
		check(false, "the quick-slot assignment control is available")
	var requests: Array[Dictionary] = []
	main.magic_selection.request_sender = func(data: Dictionary) -> Error:
		requests.append(data.duplicate(true))
		return OK
	if model.slots[1].id == 69:
		main.call("_cast_spell_slot", 1)
		check(main.magic_selection.pending.get("id") == 69 and root.get_node("Network").magic_scope == "burst", "the assigned shortcut arms Fire Burst ground targeting")
		main.magic_selection.confirm_location(Vector2i(12, 14))
		check(requests.back() == {"op": "cast", "id": 69, "power": 1, "x": 12, "y": 14}, "the shortcut submits Fire Burst with the chosen location")
	book.edit_prepared_slot(1)
	book.call("_on_family_pressed", "heat_bolt")
	check(book.selected_spell_id == 69, "clicking the selected family preserves its Burst variant")
	var variants: OptionButton = book.get("_variant_picker")
	var burst_index := variants.get_item_index(69)
	check(variants.get_item_text(burst_index).contains("Fire Burst"), "the variant picker identifies Fire Burst by name")
	variants.select(variants.get_item_index(68))
	variants.item_selected.emit(variants.selected)
	book.search.text = "fire burst"
	book.call("_filter_spells")
	check(book.selected_spell_id == 69, "searching Fire Burst replaces a hidden Fire Target selection")
	book.search.text = "no such spell"
	book.call("_filter_spells")
	check(book.selected_spell_id == -1 and assign.disabled and book.cast_button.disabled, "an empty search cannot assign or cast an invisible selection")
	book.edit_prepared_slot(1)
	check(book.selected_spell_id == 69 and book.search.text.is_empty() and book.scope_filter.selected == 0, "editing a quick slot restores its exact spell and clears incompatible filters")
	book.call("_on_spell_pressed", 69)
	var quote := {"kind": "preview", "id": 69, "requested": 1, "power": 1, "limit": 1, "mana": 75, "ready": false,
		"reason": "Requires Magic Nexus 2.", "reagents": [
			{"name": "Fire Distillate", "quantity": 2, "have": 123456},
			{"name": "Energy Distillate", "quantity": 1, "have": 123456},
			{"name": "Air Distillate", "quantity": 1, "have": 123456},
			{"name": "Quartz Lens", "quantity": 1, "have": 123456}]}
	for dimensions in [Vector2i(1280, 720), Vector2i(960, 540), Vector2i(800, 450)]:
		root.size = dimensions
		for mode in [1, 0]:
			book.browser_picker.select(mode)
			book.call("_filter_spells")
			book.toggle() if not book.is_open() else book.sync()
			book.call("_quote_state", quote)
			await settle()
			var bounds := book.get_viewport_rect()
			var rect: Rect2 = book.panel.get_global_rect()
			check(rect.position.x >= 0 and rect.position.y >= 0 and rect.end.x <= bounds.end.x - 96 and rect.end.y <= bounds.end.y - 40,
				"book fits %s in browser mode %d: %s" % [dimensions, mode, rect])
			var preparation: Control = book.get("_prepare_controls")
			check(rect.encloses(preparation.get_global_rect()), "preparation controls stay inside the visible book")
			check(rect.encloses(book.cast_button.get_global_rect()), "Cast stays inside the visible book")
			check(rect.end.y < main.get_node("GameView/Quickbar").global_position.y, "the book leaves the bottom HUD clear")
			await capture("%dx%d-%s.png" % [dimensions.x, dimensions.y, "families" if mode == 1 else "grid"])
	root.size = Vector2i(1280, 720)
	root.content_scale_factor = 1.5
	book.browser_picker.select(1)
	book.call("_filter_spells")
	await settle()
	var scaled_bounds := book.get_viewport_rect()
	var scaled_rect: Rect2 = book.panel.get_global_rect()
	check(scaled_rect.end.x <= scaled_bounds.end.x - 96 and scaled_rect.end.y <= scaled_bounds.end.y - 40,
		"the book fits with the largest supported UI scale: %s in %s" % [scaled_rect, scaled_bounds])
	check(scaled_rect.end.y < main.get_node("GameView/Quickbar").global_position.y, "the enlarged UI keeps assignment and Cast above the bottom HUD")
	await capture("1280x720-ui-150.png")
	main.free()
	model = null
	await process_frame
	NativeAnimationImporter.clear()
	GlbSceneCache.clear()
	print("spellbook preparation: ", "PASS" if failures == 0 else "FAIL (%d)" % failures)
	quit(failures)

func capture(filename: String) -> void:
	var output := OS.get_environment("ELORIA_ARTIFACT_DIR")
	if output.is_empty() or DisplayServer.get_name() == "headless": return
	await RenderingServer.frame_post_draw
	DirAccess.make_dir_recursive_absolute(output)
	root.get_texture().get_image().save_png(output.path_join(filename))
