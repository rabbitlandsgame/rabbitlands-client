extends SceneTree
## Guards the technique interface: the Techniques tab of the Spells &
## Techniques window, the Tab-held technique ring, techniques in quick spell
## slots, and keys.ini.
##
## The tab draws only what the server sends - ELORIA_MAGIC_STATE kind
## "techniques" - fed here through AppState the way the network does. The ring
## and the quick slots aim through the tab, so all three send the same request.

var failures := 0
var sent: Array[Dictionary] = []

func _init() -> void:
	call_deferred("_run")

func _record(request: Dictionary) -> Error:
	sent.append(request)
	return OK

func _run() -> void:
	root.size = Vector2i(1280, 720)
	var app_state: Node = root.get_node("/root/AppState")
	app_state.set("local_actor_id", 7)
	var catalog := SpellCatalog.new()
	catalog.configure(JSON.parse_string(FileAccess.get_file_as_string("res://data/spells/catalog.json")))
	var window: Control = (load("res://src/ui/spells_window.gd") as GDScript).new() as Control
	root.add_child(window)
	await process_frame
	window.call("configure", catalog, func(_id: int) -> void: pass)
	var panel: PanelContainer = window.get_node("SpellsWindow") as PanelContainer
	var tab: VBoxContainer = window.get("techniques_panel") as VBoxContainer
	if not _expect(tab != null, "the window carries a Techniques tab"):
		quit(failures)
		return
	tab.call("configure", _record, func(actor_id: int) -> bool: return actor_id == 31,
		func(actor_id: int) -> bool: return actor_id == 44)

	# --- the tabs ---------------------------------------------------------------
	_expect((panel.find_child("SpellsTitle", true, false) as Label).text == "Spells & Techniques",
		"the window is titled for both")
	window.call("toggle_techniques")
	await process_frame
	_expect(panel.visible and str(window.get("current_tab")) == "techniques" and tab.visible,
		"Ctrl+X opens the window on Techniques")
	var scroll: Control = panel.find_child("SpellContentScroll", true, false) as Control
	_expect(not scroll.is_visible_in_tree(), "the magic browser is hidden behind the Techniques tab")
	window.call("set_tab", "magic")
	_expect(scroll.visible and not tab.visible, "the Magic tab brings the browser back")
	window.call("set_tab", "techniques")
	window.call("toggle_techniques")
	_expect(not panel.visible, "Ctrl+X closes the window when it already shows Techniques")
	window.call("toggle")
	_expect(panel.visible and str(window.get("current_tab")) == "techniques", "Ctrl+S reopens the last tab")

	# --- the panel -------------------------------------------------------------
	var state := {"kind": "techniques", "action_points": 30, "max_action_points": 200,
		"queued": "", "stance": "", "round": 2.0, "techniques": [
			_row("heavy_blow", "Heavy Blow", "Any weapon", "strike", 0, true, ""),
			_row("fighting_retreat", "Fighting Retreat", "Any weapon", "instant", 0, false, ""),
			_row("charge", "Charge", "Any weapon", "charge", 10, true, ""),
			_row("war_cry", "War Cry", "Any weapon", "instant", 20, false, "You need Attack level 40 to use War Cry."),
			_row("cleave", "Cleave", "Two-handed", "strike", 10, true, "", false),
			_row("brace", "Brace", "Shield", "stance", 5, false, ""),
			_row("shield_bash", "Shield Bash", "Shield", "strike", 10, true, "You need a shield."),
		]}
	state.techniques[0]["ready_in"] = 30.0
	app_state.call("_on_packet", 212, JSON.stringify(state).to_utf8_buffer())
	await process_frame
	var buttons: Dictionary = tab.get("buttons")
	_expect(buttons.size() == 7, "one button per technique: %d" % buttons.size())
	_expect((tab.find_child("ActionPoints", true, false) as Label).text == "Action points 30 / 200",
		"the real action-point pool is shown")
	var remaining: String = tab.get("_row_controls")["heavy_blow"].get_node("Cooldown").text
	_expect(not (buttons["heavy_blow"] as Button).disabled and remaining.ends_with("s") and remaining.to_int() > 0 and remaining.to_int() <= 30,
		"a cooling-down technique is inspectable and counts down")
	_expect((buttons["heavy_blow"] as Button).icon != null, "rows carry the painted icon")
	_expect(not (buttons["war_cry"] as Button).disabled and "Attack level 40" in (buttons["war_cry"] as Button).tooltip_text,
		"a refused technique says why")
	_expect(not (buttons["cleave"] as Button).disabled and "Manual of Cleave" in (buttons["cleave"] as Button).tooltip_text,
		"an unlearned technique names its manual")
	(buttons["fighting_retreat"] as Button).pressed.emit()
	_expect(sent.is_empty(), "inspecting a technique never activates it")
	(tab.get("use_button") as Button).pressed.emit()
	_expect(sent.back() == {"op": "use", "key": "fighting_retreat"}, "an instant technique is requested at once")
	app_state.set("selected_actor_id", -1)
	(buttons["charge"] as Button).pressed.emit()
	(tab.get("use_button") as Button).pressed.emit()
	_expect(str(tab.get("pending_key")) == "charge" and "click a creature" in (tab.get("status_label") as Label).text.to_lower(),
		"a targeted technique with no creature in hand is armed and says so")
	_expect(not bool(tab.call("fire_at", 99)), "a click on something it cannot strike does not take it")
	_expect(bool(tab.call("fire_at", 31)) and sent.back() == {"op": "use", "key": "charge", "target_id": 31},
		"the next creature clicked receives it")
	var placed: Array[String] = []
	tab.connect("place_on_bar", func(key: String) -> void: placed.append(key))
	tab.call("select_technique", "charge")
	var requirement_row: Control = (tab.get("requirements_rows") as Control).get_child(0)
	tab.call("_refresh_buttons")
	_expect((tab.get("requirements_rows") as Control).get_child(0) == requirement_row, "cooldown refreshes preserve the requirement controls")
	(tab.get("assign_button") as Button).pressed.emit()
	_expect(placed == ["charge"], "the inspector assigns the selected technique")
	state.stance = "brace"
	state.techniques[5]["active"] = true
	app_state.call("_on_packet", 212, JSON.stringify(state).to_utf8_buffer())
	tab.call("select_technique", "brace")
	_expect(not (tab.get("use_button") as Button).disabled and "Held" in tab.get("_row_controls")["brace"].get_node("Cooldown").text
		and (tab.get("use_button") as Button).text == "Release Brace",
		"a held stance can be let go and says it is held")

	# --- repeat casting's state ---------------------------------------------
	app_state.call("_on_packet", 212, JSON.stringify({"kind": "autocast", "enabled": true,
		"active": true, "spell_id": 6, "target_id": 31}).to_utf8_buffer())
	var autocast: Dictionary = app_state.get("autocast")
	_expect(bool(autocast.get("enabled")) and bool(autocast.get("active")) and int(autocast.get("spell_id")) == 6,
		"the server's repeat-casting switch and run reach AppState")
	_expect(EloriaProtocol.CLIENT_CAPABILITIES.has("magic_autocast_v1")
		and EloriaProtocol.CLIENT_CAPABILITIES.has("techniques_v1"), "both capabilities are advertised")

	# --- the ring ----------------------------------------------------------------
	var ring: Control = (load("res://src/ui/technique_ring.gd") as GDScript).new() as Control
	ring.set("techniques", tab)
	root.add_child(ring)
	await process_frame
	var offered: Array = ring.call("offered")
	var offered_keys := offered.map(func(row: Dictionary) -> String: return str(row.key))
	_expect("cleave" not in offered_keys and "shield_bash" not in offered_keys and "war_cry" not in offered_keys,
		"the ring leaves out unlearned techniques and ones the gear or level refuses")
	_expect("heavy_blow" in offered_keys and "brace" in offered_keys, "and offers what can be used, cooling down or not")
	var hold := InputEventKey.new()
	hold.physical_keycode = KEY_Z
	hold.pressed = true
	var ring_gate := [true]
	ring.set("can_open", func() -> bool: return ring_gate[0])
	_expect(bool(ring.call("handle_event", hold)) and ring.visible, "pressing Z opens the ring")
	await process_frame
	_expect(ring.visible, "and it stays open while it may")
	_expect((ring.get("buttons") as Array).size() == offered.size(), "one wedge per offered technique")
	var before := sent.size()
	var number := InputEventKey.new()
	number.physical_keycode = KEY_2
	number.pressed = true
	app_state.set("selected_actor_id", 31)
	ring.call("handle_event", number)
	_expect(not ring.visible and sent.size() == before + 1, "a number key uses its wedge and closes the ring")
	var release := hold.duplicate() as InputEventKey
	release.pressed = false
	ring.call("handle_event", hold)
	_expect(bool(ring.call("handle_event", release)) and not ring.visible, "letting go of Z closes it")
	InputMap.action_erase_events("technique_ring")
	var rebound := InputEventKey.new()
	rebound.physical_keycode = KEY_G
	InputMap.action_add_event("technique_ring", rebound)
	_expect(not bool(ring.call("handle_event", hold)) and not ring.visible, "a rebound ring key releases Z")
	var g := InputEventKey.new()
	g.physical_keycode = KEY_G
	g.pressed = true
	_expect(bool(ring.call("handle_event", g)) and ring.visible, "and the new key opens it")
	ring.call("dismiss")
	InputMap.load_from_project_settings()

	# --- quick slots ---------------------------------------------------------
	var loadout = preload("res://src/ui/spell_loadout.gd").new()
	loadout.configure(catalog)
	loadout.path = "user://test-techniques-loadout-%d.cfg" % Time.get_ticks_usec()
	loadout.load_profile("server/tester")
	loadout.assign_slot(11, -1, 1)
	var empty: int = int(loadout.call("first_empty_slot"))
	_expect(empty >= 0 and empty <= 11, "a cleared slot is found empty")
	loadout.call("assign_technique", empty, "shield_bash")
	_expect(int(loadout.call("first_empty_slot")) != empty, "and is no longer empty once it holds a technique")
	_expect(loadout.call("technique_at", empty) == "shield_bash", "a quick slot can hold a technique")
	loadout.call("assign_technique", 0, "Not A Key")
	_expect(loadout.call("technique_at", 0) != "Not A Key", "only technique keys are accepted")
	loadout.load_profile("server/tester")
	_expect(loadout.call("technique_at", empty) == "shield_bash", "and it survives a reload")
	DirAccess.remove_absolute(ProjectSettings.globalize_path(loadout.path))
	var slot_button: Button = (load("res://src/ui/prepared_spell_button.gd") as GDScript).new() as Button
	slot_button.set("accepts_spells", true)
	var dropped: Array[String] = []
	slot_button.connect("technique_dropped", func(key: String) -> void: dropped.append(key))
	_expect(bool(slot_button.call("_can_drop_data", Vector2.ZERO, {"kind": "technique", "key": "brace"})),
		"a slot accepts a dragged technique")
	slot_button.call("_drop_data", Vector2.ZERO, {"kind": "technique", "key": "brace"})
	_expect(dropped == ["brace"], "and takes it")
	slot_button.free()

	# --- keys.ini ------------------------------------------------------------
	var Keys := load("res://src/ui/key_bindings.gd")
	for spec: String in ["CTRL S", "ALT 1", "LSHIFT", "TAB", "M", "Z", "1", "SHIFT F3", "-"]:
		var event: InputEventKey = Keys.parse(spec)
		_expect(event != null and Keys.describe(event) == spec, "keys.ini reads and writes %s: %s" % [
			spec, Keys.describe(event) if event != null else "null"])
	var parsed: Dictionary = Keys.read("; comment\n#K_TOGGLE_MAP = M\n#K_QUICK_ITEM_1 = 1, CTRL 1\n"
		+ "#K_NOT_AN_ACTION = X\n#K_SPELL_RING = nonsense key\n", ["toggle_map", "quick_item_1", "spell_ring"])
	_expect(parsed.size() == 2 and (parsed["quick_item_1"] as Array).size() == 2,
		"comments, unknown actions and unreadable keys are skipped")
	var path := "user://test-keys-%d.ini" % Time.get_ticks_usec()
	InputMap.action_erase_events("toggle_map")
	InputMap.action_add_event("toggle_map", Keys.parse("CTRL ALT K"))
	_expect(Keys.save(["toggle_map", "spell_ring"], path) == OK, "keys.ini is written")
	var text := FileAccess.get_file_as_string(path)
	_expect("#K_TOGGLE_MAP = CTRL ALT K" in text and "#K_SPELL_RING = LSHIFT" in text,
		"one #K_ line per action: " + text.get_slice("\n", 6))
	Keys.reset_to_defaults(["toggle_map"])
	_expect(Keys.describe(InputMap.action_get_events("toggle_map")[0]) == "TAB", "reset restores the shipped key")
	_expect(Keys.load_file(["toggle_map", "spell_ring"], path) == 2
		and Keys.describe(InputMap.action_get_events("toggle_map")[0]) == "CTRL ALT K",
		"keys.ini wins at start-up")
	# A file the previous build wrote lists its defaults, the map on M and
	# the ring on Tab: those give way to the new defaults, a chosen key stays,
	# and the file is rewritten so a later choice of M or Tab is kept.
	var old_file := FileAccess.open(path, FileAccess.WRITE)
	old_file.store_string("; Rabbit Lands key bindings.\n#K_TOGGLE_MAP = M\n"
		+ "#K_TECHNIQUE_RING = TAB\n#K_SPELL_RING = RSHIFT\n")
	old_file.close()
	var three := ["toggle_map", "technique_ring", "spell_ring"]
	# Start-up reads keys.ini over the shipped defaults.
	InputMap.load_from_project_settings()
	_expect(Keys.load_file(three, path) == 1
		and Keys.describe(InputMap.action_get_events("toggle_map")[0]) == "TAB"
		and Keys.describe(InputMap.action_get_events("technique_ring")[0]) == "Z"
		and Keys.describe(InputMap.action_get_events("spell_ring")[0]) == "RSHIFT",
		"an older keys.ini gives up its old defaults and keeps chosen keys")
	text = FileAccess.get_file_as_string(path)
	_expect("#KEYS_VERSION = 2" in text and "#K_TOGGLE_MAP = TAB" in text
		and "#K_TECHNIQUE_RING = Z" in text, "and is written again at the new version")
	InputMap.action_erase_events("toggle_map")
	InputMap.action_add_event("toggle_map", Keys.parse("M"))
	Keys.save(three, path)
	Keys.reset_to_defaults(three)
	_expect(Keys.load_file(three, path) == 3
		and Keys.describe(InputMap.action_get_events("toggle_map")[0]) == "M",
		"M chosen in a current keys.ini stays M")
	DirAccess.remove_absolute(ProjectSettings.globalize_path(path))
	InputMap.load_from_project_settings()

	# --- the settings window's Controls page ---------------------------------
	var settings: Control = (load("res://src/ui/settings_window.gd") as GDScript).new() as Control
	root.add_child(settings)
	await process_frame
	var bindable: Array = settings.call("bindable_actions")
	_expect("spell_ring" in bindable and "technique_ring" in bindable and "toggle_techniques" in bindable,
		"the rings and the Techniques tab can be rebound")
	_expect(settings.find_child("ResetKeys", true, false) is Button, "there is a reset-all-keys button")
	settings.call("begin_capture", "spell_ring")
	var left_shift := InputEventKey.new()
	left_shift.physical_keycode = KEY_SHIFT
	left_shift.shift_pressed = true
	left_shift.location = KEY_LOCATION_LEFT
	left_shift.pressed = true
	settings.call("apply_capture", left_shift)
	var stored: InputEventKey = InputMap.action_get_events("spell_ring")[0] as InputEventKey
	_expect(not stored.shift_pressed and stored.location == KEY_LOCATION_LEFT,
		"a held modifier is captured as the key itself, with its side")
	settings.call("begin_capture", "toggle_map")
	var t_key := InputEventKey.new()
	t_key.physical_keycode = KEY_Z
	t_key.pressed = true
	settings.call("apply_capture", t_key)
	_expect("technique ring" in (settings.get("capture_label") as Label).text,
		"binding a key already in use names the other action")
	InputMap.load_from_project_settings()
	settings.call("reset_keys")
	_expect(Keys.describe(InputMap.action_get_events("toggle_map")[0]) == "TAB"
		and Keys.describe(InputMap.action_get_events("technique_ring")[0]) == "Z", "Reset puts every key back")

	print("techniques ui tests: ", "PASS" if failures == 0 else "FAIL (%d)" % failures)
	settings.queue_free()
	ring.queue_free()
	window.queue_free()
	await process_frame
	quit(failures)

func _row(key: String, name: String, group: String, kind: String, ap: int,
		targeted: bool, blocker: String, known := true) -> Dictionary:
	return {"key": key, "name": name, "group": group, "kind": kind, "skill": "Attack",
		"level": 0, "ap": ap, "cooldown": 6.0, "ready_in": 0.0, "known": known,
		"manual": "" if key in ["heavy_blow", "fighting_retreat"] else "Manual of " + name,
		"targeted": targeted, "active": false, "blocker": blocker,
		"description": name + " does a thing.", "attribute": "might"}

func _expect(value: bool, label: String) -> bool:
	if not value:
		failures += 1
		push_error("FAIL: " + label)
	return value
