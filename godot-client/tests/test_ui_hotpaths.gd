extends SceneTree
## Per-packet UI refreshes skip work that would change nothing on screen:
## unchanged theme overrides, closed windows, hidden tabs and repeated chat
## lines. Each check also proves the painted result still matches what a full
## refresh shows. Prints the measured refresh costs for the performance notes.
const TextColors := preload("res://src/ui/text_colors.gd")
const UI := preload("res://src/ui/action_book_ui.gd")
const Profiles := preload("res://src/mounts/mount_profiles.gd")
var failures := 0
var checks := 0
var timings := {}

func _init() -> void: call_deferred("run")

## The windows name autoloads, which a test script cannot see when it is
## compiled, so the counting subclasses are compiled once the tree is running.
func counting(path: String, method: String, counter: String, signature := "", arguments := "") -> Script:
	var script := GDScript.new()
	script.source_code = "extends \"%s\"\nvar %s := 0\nfunc %s(%s) -> void:\n\t%s += 1\n\tsuper(%s)\n" % [
		path, counter, method, signature, counter, arguments]
	expect(script.reload() == OK, "counting subclass of " + path + " compiles")
	return script

func expect(value: bool, message: String) -> void:
	checks += 1
	if not value:
		failures += 1
		push_error("FAIL: " + message)

func count_theme_changes(control: Control) -> Array:
	var counter := [0]
	control.theme_changed.connect(func() -> void: counter[0] += 1)
	return counter

func run() -> void:
	root.size = Vector2i(1280, 720)
	_check_text_colors()
	_check_icon_availability()
	var catalog := _check_spell_catalog()
	await _check_spells_window(catalog)
	_check_chat_tabs()
	await _check_mounts_window()
	print("ui_hotpaths_timings ", JSON.stringify(timings))
	print("ui hotpaths: %d checks, %d failures" % [checks, failures])
	NativeAnimationImporter.clear()
	GlbSceneCache.clear()
	quit(failures)

func _check_text_colors() -> void:
	var label := Label.new()
	root.add_child(label)
	var changes := count_theme_changes(label)
	TextColors.bind(label, "ui_label")
	var first: int = changes[0]
	for index: int in 50: TextColors.bind(label, "ui_label")
	expect(changes[0] == first, "rebinding an unchanged role does not notify the control")
	expect(label.get_theme_color("font_color") == TextColors.color("ui_label"), "the bound colour is applied")
	TextColors.bind(label, "spell_ready")
	expect(changes[0] == first + 1 and label.get_theme_color("font_color") == TextColors.color("spell_ready")
		and label.get_meta("text_color_role") == "spell_ready", "a different role still recolours once")
	var button := Button.new()
	root.add_child(button)
	TextColors.bind(button, "chat_tab")
	TextColors.bind(button, "chat_selector", "font_hover_color")
	expect(button.get_meta("text_color_role") == "chat_selector", "the last bound role is recorded")
	TextColors.bind(button, "chat_tab")
	expect(button.get_meta("text_color_role") == "chat_tab", "rebinding an earlier property still records it as the last role")
	var button_changes := count_theme_changes(button)
	TextColors.bind(button, "chat_tab")
	TextColors.bind(button, "chat_selector", "font_hover_color")
	TextColors.bind(button, "chat_selector", "font_hover_color")
	expect(button_changes[0] == 0, "rebinding unchanged roles never notifies, whichever property was last: %d" % button_changes[0])
	button.add_theme_color_override("font_color", Color.BLACK)
	TextColors.bind(button, "chat_tab")
	expect(button.get_theme_color("font_color") == TextColors.color("chat_tab"), "a foreign override is replaced by the bound colour")
	button.remove_theme_color_override("font_color")
	TextColors.bind(button, "chat_tab")
	expect(button.get_theme_color("font_color") == TextColors.color("chat_tab"), "a removed override is restored")
	button.set_meta("hud_text_color_override", Color.ORANGE)
	TextColors.bind(button, "chat_tab")
	expect(button.get_theme_color("font_color") == Color.ORANGE, "a HUD component colour still wins")
	button.remove_meta("hud_text_color_override")
	TextColors.bind(button, "chat_tab")
	expect(button.get_theme_color("font_color") == TextColors.color("chat_tab"), "and is dropped again on the next refresh")
	TextColors.set_color("chat_tab", Color.CYAN)
	expect(button.get_theme_color("font_color") == Color.CYAN, "palette changes still reach bound controls")
	TextColors.reset("chat_tab")
	expect(button.get_theme_color("font_color") == TextColors.DEFAULTS.chat_tab, "and so do resets")
	var outside := Label.new()
	TextColors.bind(outside, "ui_label")
	TextColors.bind(outside, "ui_label")
	expect(outside.get_theme_color("font_color") == TextColors.color("ui_label"), "controls outside the tree are coloured")
	var world := Label3D.new()
	root.add_child(world)
	TextColors.bind_property(world, "world_npc", "modulate")
	expect(world.modulate == TextColors.color("world_npc"), "direct-property bindings apply")
	world.modulate = Color.BLACK
	TextColors.bind_property(world, "world_npc", "modulate")
	expect(world.modulate == TextColors.color("world_npc"), "direct-property bindings restore a changed value")
	var started := Time.get_ticks_usec()
	for index: int in 1000: TextColors.bind(label, "spell_ready")
	timings["rebind_unchanged_us"] = float(Time.get_ticks_usec() - started) / 1000.0
	label.free()
	button.free()
	outside.free()
	world.free()

func _check_icon_availability() -> void:
	var icon := Button.new()
	root.add_child(icon)
	var changes := count_theme_changes(icon)
	UI.icon_availability(icon, false)
	var dimmed: int = changes[0]
	UI.icon_availability(icon, false)
	expect(changes[0] == dimmed, "repeating an availability state does not notify the button")
	for state: String in ["icon_normal_color", "icon_hover_color", "icon_pressed_color", "icon_hover_pressed_color"]:
		expect(is_equal_approx(icon.get_theme_color(state).a, 0.45), "unavailable dims " + state)
	UI.icon_availability(icon, true)
	expect(changes[0] == dimmed + 4, "a changed state still sets all four icon colours")
	for state: String in ["icon_normal_color", "icon_hover_color", "icon_pressed_color", "icon_hover_pressed_color"]:
		expect(icon.get_theme_color(state) == Color.WHITE, "available restores " + state)
	icon.free()

func _check_spell_catalog() -> SpellCatalog:
	var catalog := SpellCatalog.new()
	catalog.configure(JSON.parse_string(FileAccess.get_file_as_string("res://data/spells/catalog.json")))
	var entries: Array = (JSON.parse_string(FileAccess.get_file_as_string("res://data/knowledge/catalog.json")) as Dictionary).entries
	var same := true
	for entry: Variant in entries:
		same = same and catalog.knowledge_index(str(entry)) == entries.find(entry)
	expect(same and catalog.knowledge_index("No such tome") == -1, "cached knowledge indices keep the catalog's first-match order")
	var inventory := {0: {"image_id": 584, "quantity": 12}, 5: {"image_id": 584, "quantity": 3},
		30: {"image_id": 584, "quantity": 99}, 127: {"image_id": 3, "quantity": 50},
		130: {"image_id": 586, "quantity": 7}, 1: {"image_id": 586, "quantity": 0}, 2: {"quantity": 4}}
	var totals := SpellCatalog.reagent_totals(inventory)
	for image_id: int in [584, 586, 3, -1, 999]:
		expect(int(totals.get(image_id, 0)) == catalog.inventory_quantity(image_id, inventory),
			"one-pass reagent totals match the per-reagent scan for image %d" % image_id)
	var knowledge_sets: Array = [[], range(256), [0, 1, 2]]
	var stat_sets: Array = [{}, {"magic": 100, "ether": 1000, "magic_nexus": 3}, {"magic": 5, "ether": 3}]
	var inventories: Array = [{}, inventory, {0: {"image_id": 584, "quantity": 1000}, 3: {"image_id": 586, "quantity": 1000}}]
	var identical := true
	var reagent_counts := true
	for raw_known: Array in knowledge_sets:
		var known: Array[int] = []
		known.assign(raw_known)
		for stats: Dictionary in stat_sets:
			for items: Dictionary in inventories:
				var shared := SpellCatalog.reagent_totals(items)
				for id: int in catalog.spell_ids():
					var reasons := catalog.unavailable_reasons(id, known, stats, items)
					identical = identical and reasons == catalog.unavailable_reasons(id, known, stats, items, shared)
					for reagent: Dictionary in catalog.spell(id).get("reagents", []):
						var have := catalog.inventory_quantity(int(reagent.get("image_id", -1)), items)
						if have < int(reagent.get("quantity", 0)):
							reagent_counts = reagent_counts and reasons.has("Requires %d %s (have %d)" % [
								int(reagent.get("quantity", 0)), SpellCatalog.reagent_name(reagent), have])
	expect(identical, "availability is the same with and without shared reagent totals")
	expect(reagent_counts, "missing reagents still report the per-reagent backpack count")
	return catalog

func _check_spells_window(catalog: SpellCatalog) -> void:
	var state := root.get_node("AppState")
	state.stats = {"magic": 100, "ether": 1000}
	state.known_knowledge.assign(range(256))
	state.inventory = {0: {"image_id": 584, "quantity": 12}}
	var book: Variant = counting("res://src/ui/spells_window.gd", "_refresh_availability", "refreshes").new()
	root.add_child(book)
	book.configure(catalog, func(_id: int) -> void: pass)
	await process_frame
	var closed: int = book.refreshes
	var started := Time.get_ticks_usec()
	for index: int in 100:
		state.state_changed.emit(&"stats")
		state.state_changed.emit(&"inventory")
	timings["closed_book_200_packets_us"] = Time.get_ticks_usec() - started
	await process_frame
	expect(book.refreshes == closed and book._sync_pending, "a closed book skips availability work for every packet")
	book.toggle()
	expect(book.refreshes == closed + 1 and not book._sync_pending, "opening the book refreshes it once")
	await process_frame
	var opened: int = book.refreshes
	started = Time.get_ticks_usec()
	for index: int in 100: state.state_changed.emit(&"stats")
	timings["open_book_100_packets_inline_us"] = Time.get_ticks_usec() - started
	expect(book.refreshes == opened, "packets do not refresh the open book inline")
	await process_frame
	await process_frame
	expect(book.refreshes == opened + 1, "the open book refreshes once per frame: %d" % (book.refreshes - opened))
	started = Time.get_ticks_usec()
	for index: int in 20: book.sync()
	timings["open_book_sync_us"] = float(Time.get_ticks_usec() - started) / 20.0
	state.inventory = {}
	state.stats = {"magic": 1, "ether": 1000}
	state.state_changed.emit(&"inventory")
	await process_frame
	var dimmed := true
	for id: int in catalog.spell_ids():
		var ready := catalog.unavailable_reasons(id, state.known_knowledge, state.stats, state.inventory).is_empty()
		var tint: Color = (book._buttons[id] as Button).get_theme_color("icon_normal_color")
		dimmed = dimmed and is_equal_approx(tint.a, 1.0 if ready else 0.45)
	expect(dimmed, "every spell icon shows its current availability after the coalesced refresh")
	book.set_tab("techniques")
	var behind: int = book.refreshes
	state.state_changed.emit(&"stats")
	await process_frame
	expect(book.refreshes == behind, "the Techniques tab leaves the hidden spell grid alone")
	book.set_tab("magic")
	expect(book.refreshes == behind + 1, "returning to Magic refreshes the grid")
	# The Techniques tab keeps its rows while hidden and repaints when shown.
	var tab: VBoxContainer = book.techniques_panel
	book.close()
	state.techniques = {"kind": "techniques", "action_points": 10, "max_action_points": 20, "round": 2.0,
		"techniques": [{"key": "heavy_blow", "name": "Heavy Blow", "group": "Any weapon", "kind": "strike",
			"skill": "Attack", "level": 0, "ap": 5, "cooldown": 6.0, "ready_in": 0.0, "known": true,
			"targeted": true, "active": false, "blocker": "", "description": "A blow."}]}
	state.state_changed.emit(&"techniques")
	expect(tab.get("_buttons_pending") and (tab.get("rows") as Dictionary).has("heavy_blow")
		and tab.call("unavailable_reason", "heavy_blow") == "", "a hidden Techniques tab keeps its rows current without repainting")
	book.open_tab("techniques")
	await process_frame
	expect(not tab.get("_buttons_pending") and (tab.get("points_label") as Label).text == "Action points 10 / 20",
		"showing the Techniques tab repaints it")
	state.techniques = {}
	book.queue_free()
	await process_frame

func _check_chat_tabs() -> void:
	var tabs: Variant = counting("res://src/ui/chat_log_tabs.gd", "select", "selects", "key: String", "key").new()
	root.add_child(tabs)
	tabs.select("party")
	var base: int = tabs.selects
	tabs.observe({"kind": "local", "text": "hello"})
	expect(tabs.selects == base + 1 and tabs._unread.has("local") and tabs._unread.has("all"), "a new unread tab recolours the row")
	for index: int in 20: tabs.observe({"kind": "local", "text": "again %d" % index})
	expect(tabs.selects == base + 1, "lines for tabs already unread do not recolour every tab")
	expect(tabs.buttons.local.get_theme_color("font_color") == TextColors.color("chat_unread")
		and tabs.buttons.party.get_theme_color("font_color") == TextColors.color("chat_tab")
		and tabs.buttons.party.button_pressed, "unread and selected tabs keep their colours")
	tabs.observe({"kind": "party", "text": "for the selected tab"})
	expect(tabs.selects == base + 1, "a line for the selected tab changes nothing")
	tabs.observe({"kind": "system", "text": "Server notice"})
	expect(tabs.selects == base + 2 and tabs.buttons.system.get_theme_color("font_color") == TextColors.color("chat_unread"),
		"a newly unread tab is still recoloured")
	tabs.observe({"channel": 1, "text": "[PM from Tavi: hi"})
	expect(tabs.selects == base + 3 and tabs.buttons.has("pm:tavi")
		and tabs.buttons["pm:tavi"].get_theme_color("font_color") == TextColors.color("chat_unread"), "a new private tab appears unread")
	tabs.select("local")
	expect(not tabs._unread.has("local") and tabs.buttons.local.get_theme_color("font_color") == TextColors.color("chat_tab"),
		"selecting a tab clears its unread colour")
	tabs.free()
	var hud: Variant = counting("res://src/ui/chat_hud.gd", "select_tab", "selects", "key: String", "key").new()
	for key: String in ["all", "local", "party"]:
		var button := Button.new()
		button.toggle_mode = true
		hud.buttons[key] = button
	hud.select_tab("party")
	var hud_base: int = hud.selects
	hud.observe({"kind": "local", "text": "hello"})
	for index: int in 10: hud.observe({"kind": "local", "text": "again"})
	expect(hud.selects == hud_base + 1 and hud.buttons.local.get_theme_color("font_color") == TextColors.color("chat_unread"),
		"the HUD chat recolours tabs only when the unread set grows")
	for button: Button in hud.buttons.values(): button.free()
	hud.free()

func _check_mounts_window() -> void:
	var state := root.get_node("AppState")
	state.authenticated = true
	state.local_actor_id = 42
	state.actor_mounts[42] = {"mode": "on_foot", "selected_mount_id": "moor_pony", "mount_id": "",
		"owned_mount_ids": Profiles.PATHS.keys(), "mount_coats": {}, "blocked_reason": "", "gait": "on_foot"}
	# A shorter game window leaves the last row of cards scrolled out of view.
	root.size = Vector2i(1280, 600)
	root.content_scale_size = Vector2i(1280, 600)
	var window: Variant = (load("res://src/ui/mounts_window.gd") as Script).new()
	root.add_child(window)
	window.send_command = func(_text: String) -> void: pass
	state.actor_mounts[42].mode = "summoning"
	state.actor_mounts[42].mount_id = "moor_pony"
	state.actor_mounts[42].summon_remaining_ms = 1500
	var before: String = window.status.text
	state.state_changed.emit(&"mount_countdowns")
	expect(window.status.text == before, "a closed mounts window ignores countdown packets")
	var opening := Time.get_ticks_msec()
	window.open()
	timings["mount_window_first_open_ms"] = Time.get_ticks_msec() - opening
	expect(window.status.text.begins_with("Calling"), "opening shows the current call")
	var frames := {}
	for id: String in window.cards: frames[window.cards[id].get_theme_stylebox("panel")] = true
	expect(frames.size() == 2, "cards share one selected and one plain frame: %d" % frames.size())
	var card_changes := count_theme_changes(window.cards.moor_pony)
	for index: int in 10: state.state_changed.emit(&"mount_countdowns")
	expect(card_changes[0] == 0, "countdown refreshes keep the card frames")
	window.choose("rabbit")
	expect(card_changes[0] == 1 and window.cards.rabbit.get_theme_stylebox("panel") == window._card_box(true),
		"choosing another mount moves the selected frame")
	# Every card has its still as the window opens (none shows empty) and
	# renders it once, in or out of the scrolled view.
	for frame: int in 3:
		await process_frame
	for id: String in window.portraits:
		var image: Control = window.portraits[id]
		var viewport: SubViewport = image.get("viewport")
		expect(viewport != null and image.get("actor") != null
			and viewport.render_target_update_mode == SubViewport.UPDATE_ONCE,
			"%s keeps its still and renders it once rather than every frame" % id)
	var clip: Rect2 = window.scroll.get_global_rect()
	var offscreen := 0
	for image: Control in window.portraits.values():
		if not (image.is_visible_in_tree() and clip.intersects(image.get_global_rect())): offscreen += 1
	expect(offscreen > 0 and offscreen < window.portraits.size(), "the shorter window scrolls some cards out of view: %d" % offscreen)
	window.scroll.scroll_vertical = 100000
	await process_frame
	await process_frame
	var scrolled := true
	for image: Control in window.portraits.values():
		var viewport: SubViewport = image.get("viewport")
		scrolled = scrolled and viewport != null and viewport.render_target_update_mode == SubViewport.UPDATE_ONCE
	expect(scrolled, "scrolling shows each kept still without rendering it every frame")
	# SubViewportContainer returns its viewport to UPDATE_ALWAYS when shown again.
	window.panel.hide()
	window.panel.show()
	await process_frame
	var single := true
	for image: Control in window.portraits.values():
		var viewport: SubViewport = image.get("viewport")
		if viewport != null: single = single and viewport.render_target_update_mode == SubViewport.UPDATE_ONCE
	expect(single, "a window shown again renders each built still once more, not every frame")
	window.close()
	for id: String in window.portraits:
		var viewport: SubViewport = window.portraits[id].get("viewport")
		expect(viewport != null and viewport.render_target_update_mode == SubViewport.UPDATE_DISABLED,
			"closing stops the %s portrait rendering and keeps its still for the next opening" % id)
	var reopening := Time.get_ticks_usec()
	window.open()
	timings["mount_window_reopen_us"] = Time.get_ticks_usec() - reopening
	await process_frame
	var reopened := true
	for image: Control in window.portraits.values():
		var viewport: SubViewport = image.get("viewport")
		reopened = reopened and viewport != null and viewport.render_target_update_mode == SubViewport.UPDATE_ONCE
	expect(reopened, "opening again shows every still at once and renders each once more")
	window.close()
	window.free()
	state.actor_mounts.clear()
	state.authenticated = false
	state.local_actor_id = -1
	root.size = Vector2i(1280, 720)
	root.content_scale_size = Vector2i(1280, 720)
