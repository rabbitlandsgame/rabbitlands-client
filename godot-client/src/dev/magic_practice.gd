extends Control
## Offline interaction lab. Uses production controls; outcomes are simulated.
var catalog := SpellCatalog.new()
var loadout = preload("res://src/ui/spell_loadout.gd").new()
var book: Control
var bar: Control
var selector: Control
var wheel: Control
var wheel_variant := "baseline"
var variant_picker: OptionButton
var trial_preferences := {"scopes": {}, "powers": {}, "pins": {}}
var trial_preferences_path := "user://magic_wheel_trials.cfg"
var arena: Control
var log_label: Label
var target_label: Label
var events: Array[String] = []
var pulses: Array[Dictionary] = []
var actors := {
	1: {"name": "You", "tile": Vector2i(10, 7), "health": 45, "friendly": true},
	2: {"name": "Tavin", "tile": Vector2i(12, 4), "health": 35, "friendly": true},
	3: {"name": "Mira", "tile": Vector2i(13, 10), "health": 55, "friendly": true},
	4: {"name": "Training wisp", "tile": Vector2i(20, 7), "health": 100, "friendly": false},
}

class PracticeArena extends Control:
	var lab
	const CELL := 24.0
	func _process(_delta: float) -> void: queue_redraw()
	func _draw() -> void:
		draw_style_box(get_theme_stylebox("panel", "PanelContainer"), Rect2(Vector2.ZERO, size))
		for x in range(0, int(size.x), int(CELL)):
			draw_line(Vector2(x, 0), Vector2(x, size.y), Color(0.35, 0.31, 0.22, 0.25))
		for y in range(0, int(size.y), int(CELL)):
			draw_line(Vector2(0, y), Vector2(size.x, y), Color(0.35, 0.31, 0.22, 0.25))
		var font := get_theme_default_font()
		for id in lab.actors:
			var actor: Dictionary = lab.actors[id]
			var point := Vector2(actor.tile) * CELL + Vector2.ONE * CELL / 2
			var colour := Color(0.45, 0.75, 0.65) if actor.friendly else Color(0.9, 0.43, 0.25)
			draw_circle(point, 18, colour)
			if AppState.selected_actor_id == id: draw_arc(point, 23, 0, TAU, 48, Color(1, 0.8, 0.35), 3)
			draw_string(font, point + Vector2(-35, -30), actor.name, HORIZONTAL_ALIGNMENT_LEFT, -1, 15)
			draw_rect(Rect2(point + Vector2(-25, 25), Vector2(50, 5)), Color(0.2, 0.16, 0.13))
			draw_rect(Rect2(point + Vector2(-25, 25), Vector2(0.5 * actor.health, 5)), colour)
		if not lab.selector.pending.is_empty() and Network.magic_scope in ["burst", "location"]:
			var tile := Vector2i(get_local_mouse_position() / CELL)
			var width := 9 if Network.magic_scope == "burst" else 1
			var area := Rect2(Vector2(tile - Vector2i.ONE * (width / 2)) * CELL, Vector2.ONE * width * CELL)
			var distance: Vector2i = (tile - lab.actors[1].tile).abs()
			var colour := Color(0.3, 0.75, 1, 0.2) if maxi(distance.x, distance.y) <= 15 else Color(1, 0.25, 0.15, 0.2)
			draw_rect(area, colour)
			draw_rect(area, Color(colour, 0.85), false, 2)
		for pulse: Dictionary in lab.pulses:
			var elapsed := float(Time.get_ticks_msec() - int(pulse.time)) / 650.0
			if elapsed < 1:
				draw_arc(Vector2(pulse.tile) * CELL + Vector2.ONE * CELL / 2, 15 + 35 * elapsed, 0, TAU, 48, Color(0.95, 0.8, 0.4, 1 - elapsed), 3)
	func _gui_input(event: InputEvent) -> void:
		if not event is InputEventMouseButton or not event.pressed: return
		if event.button_index == MOUSE_BUTTON_RIGHT:
			lab.selector.cancel()
			lab.record("Targeting cancelled.")
			accept_event()
			return
		if event.button_index != MOUSE_BUTTON_LEFT: return
		var tile := Vector2i(event.position / CELL)
		if Network.magic_scope in ["burst", "location"] and not lab.selector.pending.is_empty():
			lab.selector.confirm_location(tile)
		else:
			var picked := -1
			for id in lab.actors:
				if event.position.distance_to(Vector2(lab.actors[id].tile) * CELL + Vector2.ONE * CELL / 2) < 25:
					picked = id
			if picked >= 0:
				if AppState.pending_spell_target == "actor": lab.selector.confirm_actor(picked)
				else: AppState.select_actor(picked)
				lab.target_label.text = "Selected: " + str(lab.actors[picked].name)
			elif lab.selector.pending.is_empty():
				lab.actors[1].tile = tile
		accept_event()

func _ready() -> void:
	_apply_theme()
	catalog.configure(JSON.parse_string(FileAccess.get_file_as_string("res://data/spells/catalog.json")))
	catalog.default_quick_slots = [0, 1, 6, 69, 3, 5, 22, 9, 8, 17, 12, 15]
	loadout.configure(catalog)
	loadout.load_profile("offline-practice")
	for argument in OS.get_cmdline_user_args():
		if argument.begins_with("--magic-mode="): loadout.set_mode(argument.trim_prefix("--magic-mode="))
		if argument.begins_with("--wheel-variant=") and argument.trim_prefix("--wheel-variant=") in ["baseline", "quick", "orbit"]:
			wheel_variant = argument.trim_prefix("--wheel-variant=")
	var trial_config := ConfigFile.new()
	if trial_config.load(trial_preferences_path) == OK:
		for key in trial_preferences:
			var saved: Variant = trial_config.get_value("practice", key, {})
			if saved is Dictionary: trial_preferences[key] = saved
	AppState.local_actor_id = 1
	AppState.stats = {"magic": 100, "ether": 10000}
	for index in range(256): AppState.known_knowledge.append(index)
	for id in catalog.spell_ids(): AppState.spell_power[catalog.effect_for(id)] = {"limit": 10}
	for id in actors:
		AppState.actors[id] = {"name": actors[id].name, "kind": 1 if actors[id].friendly else 3, "health": actors[id].health, "alive": true}
	_seed_reagents()
	var title := Label.new()
	title.text = "Magic casting lab"
	title.position = Vector2(26, 20)
	title.add_theme_font_size_override("font_size", 28)
	add_child(title)
	var caption := Label.new()
	caption.position = Vector2(26, 63)
	caption.text = "Practice sandbox · unlimited resources · simulated outcomes"
	add_child(caption)
	variant_picker = OptionButton.new()
	variant_picker.position = Vector2(840, 24)
	variant_picker.custom_minimum_size = Vector2(360, 36)
	for title_text in ["F1 · Baseline / three steps", "F2 · Quick / hover then cast", "F3 · Orbit / two rings"]: variant_picker.add_item(title_text)
	variant_picker.select(["baseline", "quick", "orbit"].find(wheel_variant))
	variant_picker.item_selected.connect(func(index: int): set_wheel_variant(["baseline", "quick", "orbit"][index]))
	add_child(variant_picker)
	var instructions := Label.new()
	instructions.position = Vector2(26, 126)
	instructions.text = "TRY THIS\n\n1. Select Tavin. Cast Heal Target twice.\n2. Try Aimed mode and repeat.\n3. Place Fire Burst near the wisp.\n4. Arm Blink, then switch spells.\n5. Right click a slot to change its power.\n\nClick the floor to move.\nAlt+1–0, Alt+-, Alt+= cast slots.\nCtrl+S opens the spellbook.\nEsc / right click cancels targeting."
	instructions.custom_minimum_size.x = 290
	instructions.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
	add_child(instructions)
	target_label = Label.new()
	target_label.position = Vector2(350, 94)
	target_label.text = "Selected: none"
	add_child(target_label)
	arena = PracticeArena.new()
	arena.lab = self
	arena.position = Vector2(350, 125)
	arena.size = Vector2(860, 370)
	add_child(arena)
	log_label = Label.new()
	log_label.position = Vector2(26, 520)
	log_label.custom_minimum_size.x = 290
	log_label.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
	log_label.add_theme_font_size_override("font_size", 13)
	add_child(log_label)
	selector = preload("res://src/ui/magic_selection.gd").new()
	selector.catalog = catalog
	selector.request_sender = _simulate
	selector.target_validator = _candidate
	selector.target_mode = loadout.targeting_mode()
	selector.z_index = 10
	add_child(selector)
	selector.status_changed.connect(record)
	selector.cast_submitted.connect(loadout.remember_cast)
	loadout.changed.connect(func(): selector.target_mode = loadout.targeting_mode())
	book = preload("res://src/ui/spells_window.gd").new()
	book.z_index = 7
	add_child(book)
	book.configure(catalog, _cast_from_book)
	book.set_loadout(loadout)
	bar = preload("res://src/ui/casting_bar.gd").new()
	bar.loadout = loadout
	bar.z_index = 8
	add_child(bar)
	bar.panel.position = Vector2(800, 530)
	bar.cast_slot.connect(_cast_slot)
	bar.open_book.connect(book.toggle)
	bar.edit_slot.connect(book.edit_prepared_slot)
	_install_wheel()
	var standard_instructions := instructions.text
	var wheel_instructions := "TRY THE WHEEL\n\nHold Left Shift. Pick a class with 1–5 or click it. Choose a spell, then its target.\n\nLeft Shift → 1 → 1 → 2 = Heal Target.\nSelect Tavin first to heal him directly.\n\nScroll up / down changes power.\nRelease Left Shift to dismiss.\nBackspace / right click goes back.\n[ / ] or Previous/Next changes pages.\n\nWheel button: click to open."
	loadout.changed.connect(func():
		variant_picker.visible = loadout.mode == "wheel"
		instructions.add_theme_font_size_override("font_size", 14 if wheel_variant != "baseline" else 16)
		instructions.text = _trial_instructions() if loadout.mode == "wheel" and wheel_variant != "baseline" else (wheel_instructions if loadout.mode == "wheel" else standard_instructions))
	loadout.changed.emit()
	record("Ready. Choose a recipient and try a spell.")

func _install_wheel() -> void:
	var previous_spell := -1
	var previous_power := 1
	if wheel != null:
		if wheel.get_script() == load("res://src/dev/streamlined_spell_wheel.gd"):
			previous_spell = wheel.last_spell
			previous_power = wheel.last_power
		wheel.free()
	wheel = load("res://src/ui/spell_wheel.gd").new() if wheel_variant == "baseline" else load("res://src/dev/streamlined_spell_wheel.gd").new()
	wheel.loadout = loadout
	wheel.z_index = 20
	wheel.anchor_provider = func() -> Vector2: return arena.global_position + (Vector2(actors[1].tile) + Vector2.ONE * 0.5) * PracticeArena.CELL
	wheel.can_open = func() -> bool: return not (get_viewport().gui_get_focus_owner() is LineEdit or get_viewport().gui_get_focus_owner() is TextEdit) and not selector.popup.visible
	if wheel_variant != "baseline":
		wheel.variant = wheel_variant
		wheel.preferences = trial_preferences
		wheel.target_validator = _candidate
		wheel.last_spell = previous_spell
		wheel.last_power = previous_power
		wheel.preferences_changed.connect(_save_trial_preferences)
	add_child(wheel)
	wheel.spell_chosen.connect(_cast_from_wheel)
	wheel.opened.connect(func():
		selector.cancel()
		book.close())
	bar.open_wheel.connect(wheel.open_wheel)

func set_wheel_variant(value: String) -> void:
	if value not in ["baseline", "quick", "orbit"]: return
	selector.cancel()
	wheel_variant = value
	variant_picker.select(["baseline", "quick", "orbit"].find(value))
	_install_wheel()
	loadout.set_mode("wheel")
	record("Preview: " + value.capitalize())

func _save_trial_preferences() -> void:
	if trial_preferences_path.is_empty(): return
	var config := ConfigFile.new()
	for key in trial_preferences: config.set_value("practice", key, trial_preferences[key])
	config.save(trial_preferences_path)

func _trial_instructions() -> String:
	var method := "Hover a class; click its spell.\n1–5: class · 1–7: spell" if wheel_variant == "quick" else "Hover an inner class; click its spell.\nQ/W/E/R/T: class · 1–7: spell"
	return "%s WHEEL\n\n%s\n\nScroll: power\nRight click: cycle target type\nAlt+number: quickbar\nLeft Shift+Space: repeat last spell\n\nSelect Tavin → Heal twice.\n\nUnpin to make room for More.\n[ / ]: More pages · Backspace: back\nRelease Left Shift / Esc: cancel\n\nF1 / F2 / F3: compare versions" % [wheel_variant.to_upper(), method]

func _seed_reagents() -> void:
	var images: Dictionary = {}
	for id in catalog.spell_ids():
		for reagent: Dictionary in catalog.spell(id).get("reagents", []): images[int(reagent.image_id)] = true
	var index := 0
	for id in images:
		AppState.inventory[index] = {"image_id": id, "quantity": 999}
		index += 1

func _input(event: InputEvent) -> void:
	if event is InputEventKey and event.pressed and not event.echo and event.keycode in [KEY_F1, KEY_F2, KEY_F3]:
		set_wheel_variant(["baseline", "quick", "orbit"][event.keycode - KEY_F1])
		get_viewport().set_input_as_handled()
		return
	if wheel != null and wheel.handle_event(event): get_viewport().set_input_as_handled()

func _unhandled_key_input(event: InputEvent) -> void:
	if wheel != null and wheel.visible: return
	if selector.popup.visible: return
	if get_viewport().gui_get_focus_owner() is LineEdit or get_viewport().gui_get_focus_owner() is TextEdit: return
	if event is InputEventKey and event.echo: return
	if event.is_action_pressed("toggle_spells"):
		book.toggle()
		get_viewport().set_input_as_handled()
	for index in range(12):
		if event.is_action_pressed("quick_spell_%d" % (index + 1)):
			_cast_slot(index)
			get_viewport().set_input_as_handled()

func _cast_slot(index: int) -> void:
	var entry: Dictionary = loadout.slots[index]
	if int(entry.id) < 0: book.edit_prepared_slot(index)
	else:
		var limit: Dictionary = AppState.spell_power.get(catalog.effect_for(int(entry.id)), {})
		selector.begin(int(entry.id), mini(int(entry.power), maxi(1, int(limit.get("limit", 1)))), AppState.selected_actor_id)
		book.close()

func _cast_from_book(id: int) -> void:
	selector.begin(id, loadout.power_for(id), AppState.selected_actor_id)
	book.close()

func _cast_from_wheel(id: int, power: int) -> void:
	selector.begin(id, power, AppState.selected_actor_id)
	book.close()

func _candidate(id: int, target: int) -> bool:
	if not actors.has(target): return false
	return bool(actors[target].friendly) != bool(catalog.spell(id).get("hostile", false))

func _simulate(request: Dictionary) -> Error:
	var operation := str(request.get("op", ""))
	if operation == "cancel": return OK
	var id := int(request.get("id", -1))
	var definition := catalog.spell(id)
	if operation == "options":
		var transmute: bool = definition.get("effect") == "transmute"
		selector.call_deferred("_receive", {"kind": "transmute" if transmute else "recall", "id": id,
			"entries": [{"name": "Practice scrap", "rarity": "Common", "available": 10, "required_power": 1, "unit_gold": 3, "slot": 0, "item_id": 1}] if transmute else [{"name": "Practice courtyard", "key": "practice", "x": 6, "y": 7}]})
		return OK
	if operation != "cast": return OK
	var scope := str(definition.get("scope", "self"))
	var target := int(request.get("target_id", 1))
	if scope == "target" and not _candidate(id, target):
		record("Practice: choose a compatible recipient for " + str(definition.name))
		return OK
	var tile: Vector2i = actors[target].tile if actors.has(target) else actors[1].tile
	if scope in ["burst", "location"]:
		tile = Vector2i(int(request.x), int(request.y))
	if scope in ["target", "burst", "location"]:
		var distance: Vector2i = (tile - actors[1].tile).abs()
		if maxi(distance.x, distance.y) > 15:
			record("Out of range. Move closer and try again.")
			return OK
	var power := int(request.get("power", 1))
	if scope == "location": actors[1].tile = tile
	var recipients: Array[int] = [target]
	if scope in ["allies", "burst"]:
		recipients.clear()
		for actor_id: int in actors:
			var offset: Vector2i = (actors[actor_id].tile - tile).abs()
			if maxi(offset.x, offset.y) <= 4 and _candidate(id, actor_id): recipients.append(actor_id)
	for actor_id: int in recipients:
		if definition.effect == "heal": actors[actor_id].health = mini(100, int(actors[actor_id].health) + 10 * power)
		if bool(definition.get("hostile", false)): actors[actor_id].health = maxi(10, int(actors[actor_id].health) - 10 * power)
	pulses.append({"tile": tile, "time": Time.get_ticks_msec()})
	if pulses.size() > 8: pulses.pop_front()
	record("%s · P%d → %s" % [definition.name, power, actors[target].name if scope == "target" else scope.capitalize()])
	return OK

func record(message: String) -> void:
	events.push_front(message)
	if events.size() > 5: events.pop_back()
	if log_label != null: log_label.text = "RECENT ACTIONS\n\n" + "\n\n".join(events)

func _apply_theme() -> void:
	var background := ColorRect.new()
	background.color = Color(0.07, 0.09, 0.085)
	background.mouse_filter = Control.MOUSE_FILTER_IGNORE
	background.set_anchors_and_offsets_preset(Control.PRESET_FULL_RECT)
	add_child(background)
	var palette := Theme.new()
	var panel := StyleBoxFlat.new()
	panel.bg_color = Color(0.045, 0.037, 0.027)
	panel.border_color = Color(0.65, 0.47, 0.27)
	panel.set_border_width_all(1)
	panel.set_content_margin_all(6)
	palette.set_stylebox("panel", "PanelContainer", panel)
	palette.set_stylebox("normal", "Button", panel.duplicate())
	palette.set_color("font_color", "Label", Color(0.91, 0.86, 0.70))
	palette.set_color("font_color", "Button", Color(0.93, 0.80, 0.58))
	theme = palette
