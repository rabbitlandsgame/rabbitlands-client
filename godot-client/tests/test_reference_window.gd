extends SceneTree
## Guards the reference windows.
##
## Help is generated from the client's own input map and console table rather
## than written out, so it cannot drift from what the keys and commands
## actually are. Links collects what the server said and invents nothing.
## Notes belong to the player and never leave the machine.

var failures := 0

func _init() -> void:
	call_deferred("_run")

func _run() -> void:
	root.size = Vector2i(1280, 720)
	var main: Control = (load("res://src/app/main.tscn") as PackedScene).instantiate() as Control
	root.add_child(main)
	await process_frame
	(main.get_node("GameView") as Control).show()
	(main.get_node("LoginPanel") as Control).hide()
	var app_state: Node = root.get_node("/root/AppState")
	var window: Control = main.get("reference_window") as Control
	var panel: PanelContainer = window.get_node("ReferenceWindow") as PanelContainer
	var resource_rail: Control = main.get_node("GameView/ResourceHud") as Control
	await process_frame

	_expect(not panel.visible, "the reference window starts closed")
	main.call("_on_reference_pressed")
	await process_frame
	_expect(panel.visible, "the button opens it")
	_expect((window.call("tab_titles") as Array)
			== ["Help", "Notes", "Links", "Encyclopedia", "Almanac", "Buddies"],
		"it carries the six pages: %s" % str(window.call("tab_titles")))
	var rect: Rect2 = panel.get_global_rect()
	_expect(rect.position.x >= 0.0 and rect.position.y >= 0.0
		and rect.end.x <= 1280.0 and rect.end.y <= 720.0
		and not rect.intersects(resource_rail.get_global_rect()),
		"it fits 1280x720 clear of the resource rail: %s" % rect)

	# Help is generated, so it says what the keys and commands really are.
	var help: RichTextLabel = window.get_node(
		"ReferenceWindow/ReferenceBody/ReferenceTabs/Help/HelpScroll/HelpText"
		) as RichTextLabel
	_expect(help != null and help.text.contains("toggle inventory")
		and help.text.contains("#calc"),
		"help lists both a bound key and a console command")
	for command: Variant in ConsoleCommands.COMMANDS:
		_expect(help.text.contains(str(command)),
			"help lists %s" % str(command))
	# Rebinding changes the help, because the help is read from the bindings.
	# The original is put back below: these suites share one settings file,
	# and a test that leaves a key moved breaks the next one.
	var original: Array[InputEvent] = InputMap.action_get_events(
		"toggle_inventory").duplicate()
	var settings: Control = main.get("settings_window") as Control
	settings.call("begin_capture", "toggle_inventory")
	var pressed := InputEventKey.new()
	pressed.pressed = true
	pressed.physical_keycode = KEY_F7
	main.call("_unhandled_input", pressed)
	await process_frame
	_expect(help.text.contains("F7  -  toggle inventory"),
		"a rebound key shows up in the help without anyone editing it")

	# Links: what the server said, once each, nothing invented.
	app_state.call("_on_packet", 0, _line("Toran: the roads are at https://eloria.example/roads today"))
	app_state.call("_on_packet", 0, _line("Salina: mirror of https://eloria.example/roads"))
	app_state.call("_on_packet", 0, _line("Pell: nothing to see here"))
	await process_frame
	var links: Array = window.call("known_links") as Array
	_expect(links.size() == 1 and str(links[0]) == "https://eloria.example/roads",
		"an address said twice is listed once, and a line without one adds"
			+ " nothing: %s" % str(links))
	_expect(ConsoleCommands.urls_in("see www.eloria.example/a, then go").size() == 1,
		"a bare www address is found and its trailing comma is not part of it")
	_expect(ConsoleCommands.urls_in("no address here").is_empty(),
		"and a line with none finds none")

	# Notes belong to the player and are kept.
	var notes: TextEdit = window.get_node(
		"ReferenceWindow/ReferenceBody/ReferenceTabs/Notes/NotesEdit") as TextEdit
	notes.text = "Reed bank is north of the falls."
	window.call("_on_notes_changed")
	await process_frame
	var config := ConfigFile.new()
	_expect(config.load(str(main.get("SETTINGS_PATH"))) == OK
		and str(config.get_value("notes", "text", "")).contains("Reed bank"),
		"the note is written to the client's own settings file")

	# The encyclopedia is real content, not an empty shell.
	_expect(int(window.call("entry_count")) >= 5,
		"the encyclopedia has entries: %d" % int(window.call("entry_count")))
	# The document renderer sits inside the encyclopedia's middle pane now, so
	# it is reached through the view rather than by a path off the window.
	var body: RichTextLabel = (window.get("encyclopedia") as EncyclopediaView).get(
		"entry_body") as RichTextLabel
	_expect(not body.text.strip_edges().is_empty(),
		"and shows one when the window opens")
	window.call("_show_entry", 1)
	_expect(body.text != "" and body.text.length() > 80,
		"selecting another entry shows its text")

	# The almanac. Everything on the page is what command 238 said; before it
	# arrives the page says so rather than guessing at today's date.
	var almanac_text: RichTextLabel = window.get_node(
		"ReferenceWindow/ReferenceBody/ReferenceTabs/Almanac/AlmanacScroll/AlmanacText"
		) as RichTextLabel
	_expect(int(window.call("almanac_day_count")) == 0
		and almanac_text.text.contains("not sent the almanac"),
		"before the packet arrives the page says so rather than inventing a date")
	app_state.call("_on_packet", 238, _almanac_bytes())
	await process_frame
	_expect(int(window.call("almanac_day_count")) == 2,
		"the catalogue the server sent is the one shown: %d"
			% int(window.call("almanac_day_count")))
	_expect(almanac_text.text.contains("4 Zartia, Year 132"),
		"the date is rendered from its numbers: " + almanac_text.text)
	_expect(almanac_text.text.contains("Day of Sun Tzu")
		and almanac_text.text.contains("Attack experience x2")
		and almanac_text.text.contains("Defense experience x2"),
		"the day in force and its multipliers are stated, not read out of prose")
	_expect(almanac_text.text.contains("Ordinary Day")
		and almanac_text.text.contains("Day of Sun Tzu"),
		"and the whole catalogue is listed under it")
	_expect(not almanac_text.text.contains("x1.00"),
		"a bonus of exactly one is not printed as a multiplier")

	# The buddy list. It belongs to the server, which states all of it, so this
	# page shows what arrived rather than a list the client keeps.
	var buddy_list: ItemList = window.get_node(
		"ReferenceWindow/ReferenceBody/ReferenceTabs/Buddies/BuddyList") as ItemList
	_expect((window.call("buddy_names") as Array).is_empty()
		and buddy_list.item_count == 1
		and buddy_list.get_item_text(0).contains("Add one below"),
		"an empty list says how to start one rather than showing nothing")

	# The add row. The window sends nothing itself: it emits the asked-for name
	# and whoever listens sends #add_buddy; the list changes only when the
	# server answers.
	var buddy_name_edit: LineEdit = window.get_node(
		"ReferenceWindow/ReferenceBody/ReferenceTabs/Buddies/BuddyAddRow/BuddyNameEdit"
		) as LineEdit
	var add_buddy_button: Button = window.get_node(
		"ReferenceWindow/ReferenceBody/ReferenceTabs/Buddies/BuddyAddRow/AddBuddyButton"
		) as Button
	_expect(buddy_name_edit != null and add_buddy_button != null
		and add_buddy_button.text == "Add buddy",
		"the add row carries a name field and an Add buddy button")
	var asked: Array = []
	window.connect("buddy_add_requested",
		func(buddy_name: String) -> void: asked.append(buddy_name))
	buddy_name_edit.text = "  Toran  "
	add_buddy_button.pressed.emit()
	_expect(asked == ["Toran"] and buddy_name_edit.text.is_empty(),
		"the button asks for the stripped name and clears the field: %s"
			% str(asked))
	add_buddy_button.pressed.emit()
	buddy_name_edit.text = "   "
	buddy_name_edit.text_submitted.emit("   ")
	_expect(asked.size() == 1, "an empty or blank name asks for nothing")
	buddy_name_edit.text = "Vesna"
	buddy_name_edit.text_submitted.emit("Vesna")
	_expect(asked == ["Toran", "Vesna"] and buddy_name_edit.text.is_empty(),
		"submitting the field works like the button: %s" % str(asked))
	_expect((window.call("buddy_names") as Array).is_empty(),
		"and asking alone changes nothing until the server answers")

	app_state.call("_on_packet", 59, _buddy_bytes(2, "Bo"))
	app_state.call("_on_packet", 59, _buddy_bytes(2, "Cass"))
	app_state.call("_on_packet", 59, _buddy_bytes(1, "Cass"))
	await process_frame
	_expect((window.call("buddy_names") as Array) == ["Bo", "Cass"],
		"both names are listed: %s" % str(window.call("buddy_names")))
	_expect(buddy_list.get_item_text(0).contains("away")
		and buddy_list.get_item_text(1).contains("here now"),
		"and each says whether they are here: "
			+ buddy_list.get_item_text(0) + " / " + buddy_list.get_item_text(1))
	app_state.call("_on_packet", 59, _buddy_bytes(0, "Cass"))
	await process_frame
	_expect(buddy_list.get_item_text(1).contains("away"),
		"somebody leaving is shown as away rather than removed")
	app_state.call("_on_packet", 59, _buddy_bytes(3, "Bo"))
	await process_frame
	_expect((window.call("buddy_names") as Array) == ["Cass"],
		"and a name taken off the list is gone: %s"
			% str(window.call("buddy_names")))

	InputMap.action_erase_events("toggle_inventory")
	for event: InputEvent in original:
		InputMap.action_add_event("toggle_inventory", event)
	main.call("_save_hud_settings")
	_expect(not InputMap.action_get_events("toggle_inventory").is_empty(),
		"the key this suite moved is put back for the next one")

	var cancel: InputEventKey = InputMap.action_get_events(
		"cancel")[0].duplicate() as InputEventKey
	cancel.pressed = true
	main.call("_unhandled_input", cancel)
	await process_frame
	_expect(not panel.visible, "cancel closes it")

	print("reference window tests: ",
		"PASS" if failures == 0 else "FAIL (%d)" % failures)
	main.queue_free()
	await process_frame
	quit(failures)

## One almanac payload, built here the way the server builds it: 4 Zartia of
## year 132, the Day of Sun Tzu in force, and a two-entry catalogue.
func _almanac_bytes() -> PackedByteArray:
	var payload := PackedByteArray([4, 4])
	payload.append_array(_u16(132))
	payload.append(1)               # kind: good
	payload.append_array(_u16(100))  # experience bonus x1.00
	payload.append_array(_nul("Day of Sun Tzu"))
	payload.append_array(_nul("Attack and defense experience are doubled."))
	payload.append(0)               # no tagged effects
	payload.append(2)               # two multipliers
	payload.append_array(_nul("attack"))
	payload.append_array(_u16(200))
	payload.append_array(_nul("defense"))
	payload.append_array(_u16(200))
	payload.append_array(_u16(2))   # catalogue of two
	payload.append(0)
	payload.append_array(_nul("Ordinary Day"))
	payload.append_array(_nul("There are no special day effects."))
	payload.append(1)
	payload.append_array(_nul("Day of Sun Tzu"))
	payload.append_array(_nul("Attack and defense experience are doubled."))
	return payload

func _u16(value: int) -> PackedByteArray:
	return PackedByteArray([value & 0xFF, (value >> 8) & 0xFF])

func _nul(text: String) -> PackedByteArray:
	var bytes: PackedByteArray = text.to_utf8_buffer()
	bytes.append(0)
	return bytes

func _line(text: String) -> PackedByteArray:
	var bytes := PackedByteArray([0])
	bytes.append_array(text.to_utf8_buffer())
	bytes.append(0)
	return bytes

func _expect(value: bool, label: String) -> bool:
	if not value:
		failures += 1
		push_error("FAIL: " + label)
	return value

func _buddy_bytes(event: int, name: String) -> PackedByteArray:
	var payload := PackedByteArray([event])
	payload.append_array(_nul(name))
	return payload
