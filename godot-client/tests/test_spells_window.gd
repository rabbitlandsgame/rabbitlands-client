extends SceneTree
## Real-catalog coverage for the compact book and its authoritative inspector.
var failures := 0
var cast_ids: Array[int] = []

func _init() -> void: call_deferred("run")
func check(value: bool, message: String) -> void:
	if not value:
		failures += 1
		push_error("FAIL: " + message)
func settle() -> void:
	for frame in range(8): await process_frame

func run() -> void:
	root.size = Vector2i(1280, 720)
	var state := root.get_node("AppState")
	state.stats = {"magic": 100, "ether": 1000}
	state.known_knowledge.assign(range(256))
	state.inventory = {0: {"image_id": 584, "quantity": 12}, 1: {"image_id": 586, "quantity": 0}}
	var catalog := SpellCatalog.new()
	catalog.configure(JSON.parse_string(FileAccess.get_file_as_string("res://data/spells/catalog.json")))
	var book = load("res://src/ui/spells_window.gd").new()
	root.add_child(book)
	book.configure(catalog, func(id: int): cast_ids.append(id))
	var loadout = load("res://src/ui/spell_loadout.gd").new()
	loadout.configure(catalog)
	loadout.path = "user://action-book-test-%d.cfg" % Time.get_ticks_usec()
	loadout.load_profile("local/book-tester")
	book.set_loadout(loadout)
	check(not book.is_open(), "book starts closed")
	book.toggle()
	await settle()
	check(book._buttons.size() == 89, "the actual 89 spells all remain in the grid")
	check(book.TARGET_COLUMNS == ["self", "target", "allies", "burst"], "only four target columns")
	check(book.browser_picker.selected == 0, "the default is the comparison grid")
	for id: int in catalog.spell_ids():
		var button: Button = book._buttons[id]
		var scope := str(catalog.spell(id).get("scope", "self"))
		var expected := scope if scope in ["self", "target", "allies", "burst"] else "self"
		check(str(button.get_parent().name) == expected.capitalize() + "Cell", "spell %d has correct library placement" % id)
		check(button.custom_minimum_size == Vector2(36, 36), "selection hugs the icon %d" % id)
	var blink: Button = book._buttons[5]
	check(str(blink.get_parent().name) == "SelfCell" and catalog.spell(5).scope == "location", "moving utility does not rewrite ground targeting")
	book._on_spell_pressed(1)
	await settle()
	check(cast_ids.is_empty(), "inspection sends no cast")
	check(book.name_label.text == "Heal Target" and book.cast_button.disabled, "missing water disables Cast, not inspection")
	check(book.reagents_rows.get_child_count() == 2, "only reagents required at Power 1 are listed")
	var life: Dictionary = book.reagents_rows.get_child(0).get_meta("reagent")
	var water: Dictionary = book.reagents_rows.get_child(1).get_meta("reagent")
	check(life == {"name": "Life Distillate", "required": 1, "have": 12}, "available counts are explicit")
	check(water == {"name": "Water Distillate", "required": 1, "have": 0}, "missing counts are explicit")
	check(book.reagents_rows.get_child(0).get_child(0).get_theme_color("font_color") == book.UI.GOOD, "available reagent is green")
	check(book.reagents_rows.get_child(1).get_child(0).get_theme_color("font_color") == book.UI.BAD, "missing reagent is red")
	check(not book._assign_button.disabled, "unavailable spells remain assignable")
	book.slot_picker.select(4)
	book._assign_button.pressed.emit()
	check(loadout.slots[4].id == 1, "assignment respects the chosen shared slot")
	book.cast_button.pressed.emit()
	check(cast_ids.is_empty(), "a disabled cast cannot be activated by a signal")
	state.inventory[1].quantity = 3
	state.state_changed.emit(&"inventory")
	check(not book.cast_button.disabled, "inventory updates immediately enable a valid base cast")
	book.cast_button.pressed.emit()
	check(cast_ids == [1] and not book.is_open(), "Cast uses the selected id and releases the world for targeting")
	book.toggle()
	book._on_spell_pressed(1)
	book._toggle_favorite()
	book.set_filter("favorites")
	check(book._buttons[1].visible and not book._buttons[0].visible, "favorites filter keeps individual variants")
	loadout.load_profile("local/other-character")
	check(loadout.book_preferences.is_empty(), "favorites do not leak across characters")
	loadout.load_profile("local/book-tester")
	check(1 in book._favorites and book._filter == "favorites", "favorites and view survive a profile reload")
	book.set_filter("all")
	book.search.text = "fire burst"
	book._filter_spells()
	check(book.selected_spell_id == 69, "search selects the matching visible variant")
	book.search.text = "no such spell"
	book._filter_spells()
	check(book.selected_spell_id == -1 and book.cast_button.disabled and book._assign_button.disabled, "empty search cannot use a hidden selection")
	book.search.clear()
	book._on_spell_pressed(1)
	book.requested_power = 3
	book._refresh_details()
	book._quote_state({"kind": "preview", "id": 1, "requested": 3, "power": 2, "limit": 2, "mana": 17, "ready": false, "reason": "Missing materials.", "reagents": [{"name": "Life Distillate", "quantity": 20, "have": 12}]})
	check(book.numbers_label.text.contains("Ether 17") and book.cast_button.disabled, "server quote controls effective cost and readiness")
	check(book.effect_preview.power_level == 2, "preview uses the effective power from the server quote")
	book._quote_state({"kind": "preview", "id": 1, "requested": 3, "power": 2, "limit": 2, "mana": 17, "ready": false, "reagents": [], "unlock_level": 0, "recommended_level": 10, "potency": {"mean": 200.0, "minimum": 196.0, "maximum": 204.0}})
	check(book.potency_label.text.contains("Recommended 10") and book.potency_label.text.contains("200% average"), "potency and recommendation come from the authoritative quote")
	book._quote_state({"kind": "preview", "id": 1, "requested": 3, "power": 2, "limit": 2, "mana": 17, "ready": true, "reagents": [], "casts_remaining": 2.0, "reagent_casts": 300.0})
	check(book.casts_label.text == "Casts now: 2 · Supplies: 300", "selected-power cast reserves separate current ether from supplies")
	book._quote_state({"kind": "preview", "id": 1, "requested": 3, "power": 2, "limit": 2, "mana": 17, "ready": false, "reason": "Missing materials.", "reagents": [{"name": "Life Distillate", "quantity": 20, "have": 12}]})
	check(book.reagents_rows.get_child_count() == 1 and book.reagents_rows.get_child(0).get_meta("reagent").required == 20, "quote replaces base quantities")
	book._quote_state({"kind": "preview", "id": 1, "requested": 1, "power": 1, "limit": 5, "mana": 5, "ready": true, "reagents": []})
	check(book.cast_button.disabled and book.numbers_label.text.contains("Ether 17"), "stale quotes cannot restore an old power")
	var preview = book.effect_preview
	check(preview.viewport.own_world_3d, "animated preview is isolated from the game world")
	book.requested_power = 1
	book._refresh_details()
	for dimensions in [Vector2i(1280, 720), Vector2i(960, 540), Vector2i(800, 450)]:
		root.size = dimensions
		book._fit_panel()
		await settle()
		check_layout(book, "magic")
		book.open_tab("techniques")
		await settle()
		check_layout(book, "techniques")
		book.open_tab("magic")
	root.size = Vector2i(1280, 720)
	root.content_scale_factor = 1.5
	book._fit_panel()
	await settle()
	check_layout(book, "magic ui 150%")
	root.content_scale_factor = 1.0
	DirAccess.remove_absolute(ProjectSettings.globalize_path(loadout.path))
	book.queue_free()
	await process_frame
	print("compact spells window: ", "PASS" if failures == 0 else "FAIL (%d)" % failures)
	quit(failures)

func check_layout(book, tag: String) -> void:
	var bounds: Vector2 = book.get_viewport_rect().size
	var rect: Rect2 = book.panel.get_global_rect()
	check(rect.position.x >= 0 and rect.end.x <= bounds.x - 96 and rect.end.y <= bounds.y - 40, "%s fits clear of the HUD: %s in %s" % [tag, rect, bounds])
	if tag.begins_with("magic"):
		check(rect.encloses(book.cast_button.get_global_rect()) and rect.encloses(book._prepare_controls.get_global_rect()), "Magic action controls stay inside")
		check(book._inspector.global_position.x >= book._browser.get_global_rect().end.x, "the inspector is beside the grid")
	else:
		check(rect.encloses(book.techniques_panel.use_button.get_global_rect()) and rect.encloses(book.techniques_panel.assign_button.get_global_rect()), "Technique actions stay inside")
