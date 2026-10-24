extends SceneTree
## Focused checks for semantic palette routing, wire colors, persistence and
## settings controls. No server or player account is required.
const Colors := preload("res://src/ui/chat_colors.gd")
const Protocol := preload("res://src/network/protocol.gd")
const Settings := preload("res://src/ui/settings_window.gd")
const ChatHud := preload("res://src/ui/chat_hud.gd")
const SETTINGS_PATH := "res://test-artifacts/chat-colors/settings.cfg"
var failures := 0

func _init() -> void:
	call_deferred("_run")

func _run() -> void:
	var palette := Colors.defaults()
	_expect(palette.harvest == Color("fc7a3a") and palette.harvest_event == palette.harvest,
		"harvesting and harvesting events use exact EL orange2")
	_expect(palette.channel_inactive == Color("999999") and palette.channel == Color("fbfabe"),
		"inactive headings and fallback channel bodies use exact EL colors")
	_expect(palette.error == Color("fa5a5a") and palette.connecting == Color("ffb3c1"),
		"disconnects are red and connecting is pink")
	_expect(palette.private == Color("f7c49f") and palette.special == Color("7697f8")
		and palette.system == Color.WHITE, "private, find and uncolored system defaults match EL")
	for entry: Array in [
		["You started to harvest Sunleaf.", "harvest"],
		["You stopped harvesting.", "harvest"],
		["Mother Nature blesses you with 42 harvesting experience!", "harvest_event"],
		["A swarm of bees interrupts your harvesting!", "harvest_event"],
		["You found a Pear while harvesting!", "special"],
		["While trying to harvest, a lid fell on Tavi.", "harvest_event"],
		["Welcome to the new server!", "welcome"],
		["Disconnected from server!", "error"],
		["Connecting to Server...", "connecting"],
	]:
		_expect(Colors.role({"channel": 3, "text": entry[0]}) == entry[1], "semantic category: " + entry[0])
	_expect(Colors.role({"channel": 0, "text": "Tavi: You found a Pear while harvesting!"}) == "local",
		"player speech cannot impersonate a special find")
	_expect(Colors.role({"channel": 1, "text": "[PM from Tavi: Disconnected from server!]"}) == "private",
		"private messages cannot impersonate disconnect notices")
	_expect(Colors.role({"channel": 3, "text": "A translated failure", "chat_role": "error"}) == "error",
		"client-provided roles do not depend on English text")
	var channel := {"channel": 5, "channel_number": 3, "text": "[3] Tavi: WTT [b]Pear[/b]",
		"text_runs": [{"text": "[3] Tavi: ", "colour": 6}, {"text": "WTT [b]Pear[/b]", "colour": 2}]}
	var inactive := Colors.segments(channel, "[12:00:00] [#3] Tavi: WTT [b]Pear[/b]", 6, palette)
	var active := Colors.segments(channel, "[12:00:00] [#3] Tavi: WTT [b]Pear[/b]", 3, palette)
	_expect(inactive.size() == 2 and inactive[0].color == palette.channel_inactive
		and inactive[1].color == palette.channel and active[0].color == palette.channel_active,
		"channel headings follow the active numeric channel without repainting its body")
	var label := RichTextLabel.new()
	root.add_child(label)
	for segment: Dictionary in inactive:
		label.push_color(segment.color)
		label.add_text(segment.text)
		label.pop()
	_expect(label.get_parsed_text().contains("[b]Pear[/b]"), "colored text keeps player BBCode literal")
	label.queue_free()
	_check_wire_colors(palette)
	_check_persistence(palette)
	await _check_preview(inactive, palette)
	var window := Settings.new()
	root.add_child(window)
	await process_frame
	var changed: Array[Array] = []
	window.setting_changed.connect(func(section: String, key: String, value: Variant) -> void:
		changed.append([section, key, value]))
	for key: String in Colors.DEFAULTS:
		var picker := window.panel.find_child("chat_color_" + key, true, false) as ColorPickerButton
		_expect(picker != null and not picker.edit_alpha, "editable opaque color control: " + key)
		if picker != null:
			picker.color_changed.emit(Color.MAGENTA)
			_expect(changed.back()[0] == "Chat" and changed.back()[1] == "chat_color_" + key,
				"the picker changes its own category: " + key)
		var category_reset := window.panel.find_child("chat_color_reset_" + key, true, false) as Button
		_expect(category_reset != null, "every chat category can restore server colors: " + key)
		if category_reset != null:
			category_reset.pressed.emit()
			_expect(changed.back()[1] == "chat_color_reset_" + key, "category reset targets its own role: " + key)
	_expect(window.panel.find_child("chat_colors_reset", true, false) is Button,
		"Chat has an explicit reset-colors action")
	window.panel.find_child("chat_colors_reset", true, false).pressed.emit()
	_expect(changed.back()[1] == "chat_colors_reset", "reset emits the palette reset action")
	var before_restore := changed.size()
	window.restore_chat_colors({"harvest": Color.MAGENTA})
	_expect((window.panel.find_child("chat_color_harvest", true, false) as ColorPickerButton).color == Color.MAGENTA,
		"settings restore the saved color without emitting a change")
	_expect(changed.size() == before_restore, "restoring controls never writes preferences again")
	var channel_number := window.panel.find_child("ChatColorChannelNumber", true, false) as SpinBox
	channel_number.value = 6
	var channel_picker := window.panel.find_child("ChatChannelColor", true, false) as ColorPickerButton
	channel_picker.color_changed.emit(Color.CYAN)
	_expect(changed.back()[1] == "chat_channel_color:6", "per-channel picker includes the selected channel number")
	window.panel.find_child("ChatChannelColorReset", true, false).pressed.emit()
	_expect(changed.back()[1] == "chat_channel_reset:6", "per-channel reset includes the selected channel number")
	window.queue_free()
	print("chat color tests: ", "PASS" if failures == 0 else "FAIL")
	quit(failures)

func _check_wire_colors(palette: Dictionary) -> void:
	var ordinary_guild := {"channel": 2, "text": "Tavi: hello"}
	_expect(Colors.role(ordinary_guild) == "guild", "ordinary guild chat keeps the guild palette")
	var gm_text := "#GM from Ari: hello"
	var server_gm := {"channel": 2, "text": gm_text,
		"text_runs": [{"text": gm_text, "colour": 11}]}
	var server_segments := Colors.segments(server_gm, "[Guild] " + gm_text, 0, palette)
	_expect(Colors.role(server_gm) == "gm" and server_segments.size() == 1
		and server_segments[0].color == palette.gm_prefix,
		"single-color GM packets retain the server's blue2 for heading and body")
	var bytes := PackedByteArray([138]) # c_blue2 announcement heading.
	bytes.append_array("#GM from Tavi: ".to_utf8_buffer())
	bytes.append(144) # c_green3 body.
	bytes.append_array("Hello café 🐇 [color=red]players[/color]".to_utf8_buffer())
	var payload := PackedByteArray([2])
	payload.append_array(bytes)
	var event := Protocol.decode_server(Protocol.ServerMessage.RAW_TEXT, payload)
	_expect(event.text == "#GM from Tavi: Hello café 🐇 [color=red]players[/color]"
		and event.text_runs.size() == 2 and event.text_runs[1].colour == 17,
		"wire colors preserve Unicode and literal markup, including the body color")
	var gm := Colors.segments(event, "[System] " + event.text, 0, palette)
	_expect(gm.size() == 2 and gm[0].color == palette.gm_prefix
		and gm[1].color == Protocol.EL_TEXT_COLOURS[17], "GM heading and server-selected body colors stay distinct")
	var custom := Colors.set_override(palette, "gm", Color.MAGENTA)
	gm = Colors.segments(event, "[System] " + event.text, 0, custom)
	_expect(gm[1].color == Color.MAGENTA, "the player's GM text override wins over server color")
	var red := Protocol.legacy_colored_runs(PackedByteArray([127]) + "Connecting".to_utf8_buffer())
	_expect(red.size() == 1 and red[0].colour == 0, "marker 127 is retained rather than confused with uncolored text")
	_expect(Protocol.legacy_colored_runs("Hello café 🐇".to_utf8_buffer())[0].colour == -1,
		"plain Unicode text has no accidental color marker")
	var urls := Colors.segments({"channel": 0, "text": "Tavi: https://rabbitlandsgame.com"},
		"[Local] Tavi: https://rabbitlandsgame.com", 0, palette)
	_expect(urls.size() == 1 and urls[0].color == Color.WHITE, "links retain their surrounding text color by default")
	var custom_url := Colors.set_override(palette, "url", Color.CYAN)
	urls = Colors.segments({"channel": 0, "text": "Tavi: HTTPS://rabbitlandsgame.com www.example.com"},
		"Tavi: HTTPS://rabbitlandsgame.com www.example.com", 0, custom_url)
	_expect(urls.size() == 4 and urls[1].color == Color.CYAN and urls[3].color == Color.CYAN,
		"explicit link overrides support uppercase schemes and www")
	# Every protocol shade survives in every chat category, rather than being
	# collapsed to one semantic orange, blue or green.
	for category: int in [0, 1, 2, 3, 4, 8]:
		for index: int in Protocol.EL_TEXT_COLOURS.size():
			var line := {"channel": category, "text": "A message", "text_runs": [{"text": "A message", "colour": index}]}
			var rendered := Colors.segments(line, "A message", 0, palette)
			_expect(rendered.size() == 1 and rendered[0].color == Protocol.EL_TEXT_COLOURS[index],
				"wire shade %d survives category %d" % [index, category])
	var local := {"channel": 0, "text": "Tavi: hello", "text_runs": [{"text": "Tavi: ", "colour": 6}, {"text": "hello", "colour": 2}]}
	var nearby := Colors.segments(local, "[Local] Tavi: hello", 0, palette)
	_expect(nearby.size() == 2 and nearby[0].color == Color.WHITE and nearby[1].color == Color("fbfabe"),
		"nearby speech preserves white names and yellow bodies")
	var pm := {"channel": 1, "text": "[PM from Tavi: hello]", "text_runs": [{"text": "[PM from Tavi: ", "colour": 1}, {"text": "hello]", "colour": 2}]}
	var private_runs := Colors.segments(pm, "[Private] Tavi: hello", 0, palette)
	_expect(private_runs.size() == 2 and private_runs[0].text == "[Private] Tavi: "
		and private_runs[1].text == "hello" and private_runs[1].color == Color("fbfabe"),
		"abbreviated private wrappers retain their embedded run boundaries")
	var same_default := Colors.set_override(palette, "success", palette.success)
	var green := {"channel": 3, "text": "Saved", "text_runs": [{"text": "Saved", "colour": 17}]}
	_expect(Colors.segments(green, "Saved", 0, same_default)[0].color == palette.success,
		"explicitly choosing the default RGB still overrides server colors")
	_expect(Colors.segments(green, "Saved", 0, Colors.reset_override(same_default, "success"))[0].color == Color("25c400"),
		"reset restores server color preservation")
	var numbered := {"channel": 5, "channel_number": 3, "text": "[3] Tavi: hello",
		"text_runs": [{"text": "[3] Tavi: ", "colour": 6}, {"text": "hello", "colour": 2}]}
	var per_channel := Colors.set_channel_override(palette, 3, Color.MAGENTA)
	var numbered_runs := Colors.segments(numbered, "[#3] Tavi: hello", 6, per_channel)
	_expect(numbered_runs[0].color == Color.MAGENTA and numbered_runs[1].color == Color("fbfabe"),
		"per-channel color changes only the first wire run, as in EL")
	var single_run := {"channel": 5, "channel_number": 3, "text": "[3] Tavi: hello", "colour": 6}
	_expect(Colors.segments(single_run, "[#3] Tavi: hello", 6, palette)[0].color == palette.channel_inactive,
		"single-run inactive channel packets remain gray throughout, as in EL")

func _check_persistence(palette: Dictionary) -> void:
	DirAccess.make_dir_recursive_absolute(ProjectSettings.globalize_path(SETTINGS_PATH.get_base_dir()))
	var config := ConfigFile.new()
	config.set_value("other", "keep", 42)
	config.save(SETTINGS_PATH)
	var custom := Colors.set_override(palette, "harvest", Color(0.2, 0.4, 0.8, 0.2))
	custom = Colors.set_override(custom, "system", Color.WHITE)
	custom = Colors.set_channel_override(custom, 6, Color.MAGENTA)
	_expect(Colors.save_colors(custom, SETTINGS_PATH) == OK, "colors save to the preferences file")
	var loaded := Colors.load_colors(SETTINGS_PATH)
	_expect(loaded.harvest.is_equal_approx(Color(0.2, 0.4, 0.8, 1)), "custom colors survive reload and stay opaque")
	_expect(Colors.is_overridden(loaded, "system") and loaded["channel:6"] == Color.MAGENTA,
		"explicit default RGB and per-channel overrides survive reload")
	config.load(SETTINGS_PATH)
	_expect(config.get_value("other", "keep") == 42, "saving colors preserves unrelated settings")
	config.set_value(Colors.SECTION, "harvest", "not a color")
	config.set_value(Colors.SECTION, "system", "#123456")
	config.save(SETTINGS_PATH)
	loaded = Colors.load_colors(SETTINGS_PATH)
	_expect(loaded.harvest == palette.harvest and loaded.system == Color("123456"),
		"invalid preferences fall back while valid HTML colors are accepted")
	Colors.save_colors(Colors.defaults(), SETTINGS_PATH)
	_expect(Colors.load_colors(SETTINGS_PATH) == palette, "resetting defaults also survives reload")
	# Simulate the previous full-palette file: factory values upgrade while a
	# custom GM choice remains an explicit override.
	config.erase_section(Colors.SECTION)
	for key: String in Colors.LEGACY_DEFAULTS:
		config.set_value(Colors.SECTION, key, Colors.LEGACY_DEFAULTS[key])
	config.set_value(Colors.SECTION, "gm", Color.MAGENTA)
	config.save(SETTINGS_PATH)
	loaded = Colors.load_colors(SETTINGS_PATH)
	_expect(loaded.harvest == Color("fc7a3a") and not Colors.is_overridden(loaded, "harvest")
		and loaded.gm == Color.MAGENTA and Colors.is_overridden(loaded, "gm"),
		"legacy factory colors migrate while custom colors remain")
	DirAccess.remove_absolute(ProjectSettings.globalize_path(SETTINGS_PATH))

func _check_preview(segments: Array[Dictionary], palette: Dictionary) -> void:
	var source := ChatHud.new()
	source.preferences_path = SETTINGS_PATH
	root.add_child(source)
	await process_frame
	await process_frame
	source.dismiss()
	source.reveal_message("Tavi: WTT [b]Pear[/b]", palette.channel, segments)
	await process_frame
	var preview: Control = source.preview_feed
	_expect(preview.get_child_count() == 1 and preview.get_child(0) is RichTextLabel,
		"closed previews retain multiple message colors")
	if preview.get_child_count() == 1 and preview.get_child(0) is RichTextLabel:
		var text := preview.get_child(0) as RichTextLabel
		_expect(text.get_parsed_text().contains("[b]Pear[/b]") and text.size.y > 0,
			"multicolor previews remain readable and keep markup literal")
	preview.clear_messages()
	source.reveal_message("An inactive channel", Color.WHITE,
		[{"text": "An inactive channel", "color": palette.channel_inactive}])
	_expect(preview.get_child_count() == 1 and preview.get_child(0).get_theme_color("font_color") == palette.channel_inactive,
		"single-run closed previews retain the rendered inactive channel color")
	source.queue_free()
	await process_frame
	DirAccess.remove_absolute(ProjectSettings.globalize_path(SETTINGS_PATH))

func _expect(value: bool, message: String) -> void:
	if not value:
		failures += 1
		push_error("FAIL: " + message)
