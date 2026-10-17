extends SceneTree
## Exercise the real command entry point and both chat displays with wire text.
var failures := 0
var main: Control
var app: Node
const SETTINGS := "user://eloria_hud.cfg"
var saved_settings := PackedByteArray()
var had_settings := false

func _init() -> void:
	call_deferred("_run")

func _run() -> void:
	had_settings = FileAccess.file_exists(SETTINGS)
	if had_settings:
		saved_settings = FileAccess.get_file_as_bytes(SETTINGS)
	await _mount()
	main.console_commands.ignored.clear()
	main.console_commands.filters.clear()
	main.console_commands.aliases.clear()
	main.call("_on_chat_tab_pressed", "all")
	app.call("_on_packet", 71, PackedByteArray([0, 1, 0, 0, 0, 2, 0, 0, 0, 3, 0, 0, 0]))
	(app.get("chat_lines") as Array).clear()
	main.call("_sync_chat")
	main.call("_sync_console")
	_messages("before")
	_expect_messages("before", true)

	main.call("_on_chat_submitted", "#IGNORE GrIeFeR")
	_expect(main.console_commands.ignored == ["griefer"], "ignore accepts mixed case")
	_expect_messages("before", false)
	_messages("ignored")
	_expect_messages("ignored", false)
	# Exercise category tabs when the split-chat UI is present too.
	var log_tabs: Variant = main.get("chat_log_tabs")
	if log_tabs != null:
		for section: String in ["all", "chat", "local", "private", "channel:1", "pm:griefer"]:
			log_tabs.select(section)
			main.call("_sync_console")
			_expect(not main.console_output.get_parsed_text().contains("blocked-"),
				"ignore survives full-log rebuild for " + section)
		log_tabs.select("all")
	main.call("_sync_console")
	main.call("_on_chat_submitted", "#ignore GRIEFER")
	_expect(main.console_commands.ignored.size() == 1, "duplicate ignore does not duplicate names")
	main.call("_on_chat_submitted", "#ignores")
	_expect(main.console_output.get_parsed_text().contains("Ignoring: griefer"), "ignores lists the player")
	_chat(0, "Friend: still-visible")
	_chat(0, "Griefer2: similar-name-visible")
	_chat(3, "A system notice")
	for output: RichTextLabel in [main.chat_output, main.console_output]:
		_expect(output.get_parsed_text().contains("still-visible")
			and output.get_parsed_text().contains("similar-name-visible"),
			"other players and similarly named players remain visible")
	_expect(main.console_output.get_parsed_text().contains("A system notice"),
		"ignore preserves system notices")
	_chat(1, "[PM to Griefer: outgoing-visible]")
	_expect(main.chat_output.get_parsed_text().contains("outgoing-visible"), "own outgoing PM is visible")
	var config := ConfigFile.new()
	_expect(config.load(SETTINGS) == OK and config.get_value("console", "ignored", []) == ["griefer"],
		"ignore is saved in client preferences")
	await _unmount()
	await _mount()
	_expect(main.console_commands.ignored == ["griefer"], "ignore survives a fresh client scene")
	main.call("_on_chat_tab_pressed", "all")
	log_tabs = main.get("chat_log_tabs")
	if log_tabs != null:
		log_tabs.select("all")
	_messages("restart")
	_expect_messages("restart", false)
	main.call("_on_chat_submitted", "#UNIGNORE GRIEFER")
	_expect(main.console_commands.ignored.is_empty(), "unignore removes the player regardless of case")
	_expect_messages("restart", true)
	_messages("restored")
	_expect_messages("restored", true)
	config.load(SETTINGS)
	_expect(config.get_value("console", "ignored", ["unexpected"]).is_empty(), "unignore is saved")
	await _unmount()
	if had_settings:
		var file := FileAccess.open(SETTINGS, FileAccess.WRITE)
		file.store_buffer(saved_settings)
	else:
		DirAccess.remove_absolute(ProjectSettings.globalize_path(SETTINGS))
	NativeAnimationImporter.clear()
	GlbSceneCache.clear()
	await process_frame
	print("ignore chat tests: ", "PASS" if failures == 0 else "FAIL (%d)" % failures)
	quit(failures)

func _mount() -> void:
	main = (load("res://src/app/main.tscn") as PackedScene).instantiate() as Control
	main.get_node("GameView/ChatWindow").preferences_path = "res://test-artifacts/ignore-chat-ui.cfg"
	root.add_child(main)
	app = root.get_node("AppState")
	app.set("authenticated", true)
	main.get_node("LoginPanel").hide()
	main.get_node("GameView").show()
	await process_frame

func _unmount() -> void:
	main.queue_free()
	await process_frame

func _messages(suffix: String) -> void:
	_chat(0, "Griefer: blocked-local-" + suffix)
	_chat(5, "[1] Griefer: blocked-channel-" + suffix)
	_chat(6, "[2] GRIEFER: blocked-channel-two-" + suffix)
	_chat(7, "[3] griefer: blocked-channel-three-" + suffix)
	_chat(1, "[PM from Griefer: blocked-pm-" + suffix + "]")
	_chat(0, "[Party] Griefer: blocked-party-" + suffix)
	_chat(2, "Griefer: blocked-guild-" + suffix)

func _expect_messages(suffix: String, visible: bool) -> void:
	for output: RichTextLabel in [main.chat_output, main.console_output]:
		for kind: String in ["local", "channel", "channel-two", "channel-three", "pm", "party", "guild"]:
			_expect(output.get_parsed_text().contains("blocked-" + kind + "-" + suffix) == visible,
				"%s %s message in %s is %s" % [suffix, kind, output.name, "visible" if visible else "hidden"])

func _chat(channel: int, text: String) -> void:
	var payload := PackedByteArray([channel])
	payload.append_array(text.to_utf8_buffer())
	payload.append(0)
	app.call("_on_packet", 0, payload)

func _expect(value: bool, label: String) -> void:
	if not value:
		failures += 1
		push_error("FAIL: " + label)
