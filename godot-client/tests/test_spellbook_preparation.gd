extends SceneTree
## Real application/theme checks plus optional native screenshots.
var failures := 0
var requests: Array[Dictionary] = []
func _init() -> void:
	create_timer(60).timeout.connect(func(): push_error("Action book capture timed out"); quit(98))
	call_deferred("run")
func check(value: bool, message: String) -> void:
	if not value:
		failures += 1
		push_error("FAIL: " + message)
func settle() -> void:
	for frame in range(12): await process_frame

func technique(key: String, title: String, group: String, kind: String, ap: int, rounds: int) -> Dictionary:
	var shield := key in ["shield_bash", "brace", "intercept"]
	return {"key": key, "name": title, "group": group, "kind": kind, "skill": "Defense" if shield else "Attack",
		"level": 10 if shield else 0, "ap": ap, "cooldown": rounds * 2.0, "cooldown_rounds": rounds,
		"ready_in": 0.0, "known": true, "manual": "Manual of " + title, "targeted": kind in ["strike", "charge", "shot"],
		"active": false, "blocker": "Equip a shield." if shield else "", "attribute": "toughness",
		"description": "Your next shield strike stuns a creature." if key == "shield_bash" else "Use " + title + " in combat.",
		"requirements": [{"kind": "skill", "label": "Defense 10" if shield else "Attack 0", "detail": "Current 32", "met": true},
			{"kind": "knowledge", "label": "Manual of " + title, "detail": "Known", "met": true},
			{"kind": "equipment", "label": "Shield" if shield else "Weapon", "detail": "Not equipped" if shield else "Equipped", "met": not shield}]}

func run() -> void:
	root.size = Vector2i(1280, 720)
	var main = load("res://src/app/main.tscn").instantiate()
	root.add_child(main)
	await settle()
	main.get_node("LoginPanel").hide()
	main.game_view.show()
	var state := root.get_node("AppState")
	state.stats = {"magic": 32, "ether": 1000, "attack": 32, "defense": 32}
	state.known_knowledge.assign(range(256))
	state.inventory = {0: {"image_id": 584, "quantity": 12}, 1: {"image_id": 586, "quantity": 0}}
	state.state_changed.emit(&"inventory")
	var book = main.spells_window
	book.loadout.profile = ""
	book.open_tab("magic")
	book._on_spell_pressed(1)
	await settle()
	check(book.reagents_rows.get_child_count() == 2 and book.cast_button.disabled, "live inspector shows two reagents and missing water")
	book.slot_picker.select(3)
	book._assign_button.pressed.emit()
	check(main.spell_loadout.slots[3].id == 1, "live book assigns to the chosen slot")
	var tab = book.techniques_panel
	state.techniques = {"kind": "techniques", "action_points": 28, "max_action_points": 30, "round": 2.0,
		"received_msec": Time.get_ticks_msec(), "techniques": [
			technique("heavy_blow", "Heavy Blow", "Any weapon", "strike", 0, 3),
			technique("measured_strike", "Measured Strike", "Any weapon", "strike", 0, 3),
			technique("charge", "Charge", "Any weapon", "charge", 10, 10),
			technique("shield_bash", "Shield Bash", "Shield", "strike", 10, 6),
			technique("brace", "Brace", "Shield", "stance", 5, 2),
			technique("intercept", "Intercept", "Shield", "instant", 15, 10),
			technique("flurry", "Flurry", "One-handed", "strike", 15, 5),
			technique("riposte", "Riposte", "One-handed", "stance", 5, 2),
			technique("aimed_shot", "Aimed Shot", "Ranged", "shot", 5, 4),
			technique("pinning_shot", "Pinning Shot", "Ranged", "shot", 10, 6)]}
	state.state_changed.emit(&"techniques")
	for dimensions in [Vector2i(1280, 720), Vector2i(960, 540), Vector2i(800, 450)]:
		root.size = dimensions
		for page in ["magic", "techniques"]:
			book.open_tab(page)
			if page == "techniques": tab.select_technique("shield_bash")
			book._fit_panel()
			await settle()
			var rect: Rect2 = book.panel.get_global_rect()
			var bounds: Vector2 = book.get_viewport_rect().size
			check(rect.position.x >= 0 and rect.end.x <= bounds.x - 96 and rect.end.y <= main.get_node("GameView/Quickbar").global_position.y,
				"%s %s fits the actual theme and HUD: %s in %s" % [dimensions, page, rect, bounds])
			var action: Control = book.cast_button if page == "magic" else tab.use_button
			var assignment: Control = book._assign_button if page == "magic" else tab.assign_button
			check(rect.encloses(action.get_global_rect()) and rect.encloses(assignment.get_global_rect()), "both %s actions visible at %s" % [page, dimensions])
			if page == "magic":
				var columns := book._grid_headings.get_child(0) as HBoxContainer
				var self_cell := columns.get_node("SelfCell") as Control
				var target_cell := columns.get_node("TargetCell") as Control
				check(is_equal_approx(target_cell.global_position.x - self_cell.global_position.x, 44), "target columns do not expand or drift")
			else:
				check(tab.use_button.disabled and not tab.assign_button.disabled, "missing equipment blocks use but not assignment")
				check(tab.requirements_rows.get_child(2).get_meta("requirement").met == false, "server equipment check is shown independently")
			if dimensions == Vector2i(1280, 720):
				var rows: Control = book.reagents_rows if page == "magic" else tab.requirements_rows
				var info_scroll: Control = book._info_scroll if page == "magic" else tab._info_scroll
				check(info_scroll.get_global_rect().encloses(rows.get_child(rows.get_child_count() - 1).get_global_rect()), "all selected %s requirements visible at default size" % page)
			await capture("%dx%d-%s.png" % [dimensions.x, dimensions.y, page])
	root.size = Vector2i(1280, 720)
	root.content_scale_factor = 1.5
	for page in ["magic", "techniques"]:
		book.open_tab(page)
		book._fit_panel()
		await settle()
		var rect: Rect2 = book.panel.get_global_rect()
		check(rect.end.x <= book.get_viewport_rect().size.x - 96 and rect.end.y <= main.get_node("GameView/Quickbar").global_position.y, "150%% UI %s leaves rail and HUD clear" % page)
		var rows: Control = book.reagents_rows if page == "magic" else tab.requirements_rows
		var info_scroll: Control = book._info_scroll if page == "magic" else tab._info_scroll
		check(info_scroll.get_global_rect().encloses(rows.get_child(rows.get_child_count() - 1).get_global_rect()), "selected %s requirements visible at 150%% UI" % page)
		await capture("1280x720-ui-150-%s.png" % page)
	root.content_scale_factor = 1.0
	book.open_tab("techniques")
	tab.slot_picker.select(6)
	tab.select_technique("shield_bash")
	tab.assign_button.pressed.emit()
	check(main.spell_loadout.technique_at(6) == "shield_bash", "Technique inspector uses the chosen shared slot")
	book.edit_prepared_slot(6)
	check(tab.selected_key == "shield_bash" and tab.slot_picker.selected == 6, "editing a saved technique restores selection and destination")
	tab.configure(func(data: Dictionary) -> Error: requests.append(data); return OK,
		func(id: int) -> bool: return id == 31, func(id: int) -> bool: return id == 44)
	state.selected_actor_id = -1
	tab.select_technique("charge")
	check(requests.is_empty(), "inspecting a real row does not use it")
	tab.use_button.pressed.emit()
	check(tab.pending_key == "charge" and not book.is_open(), "using a targeted technique closes the book and arms targeting")
	check(tab.fire_at(31) and requests.back() == {"op": "use", "key": "charge", "target_id": 31}, "existing targeting submits the selected technique")
	await settle()
	main.free()
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
