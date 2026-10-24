extends SceneTree
## Exercise real gauntlet wire messages in the production session log.
const FOLDER := "res://test-artifacts/gauntlet-console"
const ANNOUNCEMENTS := [
	"Red Canyon begins: steady, set at level 35. You have 45 minutes.",
	"A horn sounds over The First Bowl.",
	"Wave 1/3: 12 enemies remaining on this wave. All reinforcement pulses have arrived.",
	"The First Bowl is quiet. Wave 1/3 complete. The road goes on.",
	"Time. The road closes behind you.",
]
var failures := 0
var main: Control
var app: Node

func _init() -> void:
	call_deferred("_run")

func _run() -> void:
	create_timer(60).timeout.connect(func() -> void: quit(99))
	root.get_node("Network").block_for_hud_preview()
	DirAccess.make_dir_recursive_absolute(ProjectSettings.globalize_path(FOLDER))
	var settings := FOLDER.path_join("settings.cfg")
	ConfigFile.new().save(settings)
	root.size = Vector2i(1280, 720)
	main = load("res://src/app/main.tscn").instantiate()
	main.get_node("GameView/ChatWindow").preferences_path = settings
	root.add_child(main)
	main.get_node("LoginPanel").hide()
	main.get_node("LoginBackground").hide()
	main.game_view.show()
	app = root.get_node("AppState")
	app.authenticated = true
	await _settle()
	app.chat_lines.clear()
	app.chat_history.clear()
	main.call("_sync_chat")
	main.call("_sync_console")
	for text: String in ANNOUNCEMENTS:
		_chat(text)
	_expect(app.chat_lines.size() == ANNOUNCEMENTS.size(), "all gauntlet announcements reach history")
	for line: Dictionary in app.chat_lines:
		_expect(int(line.colour) == 18, "the original gauntlet colour survives decoding")
		_expect(main.ChatMessages.kind(line) == "system", "gauntlet messages belong in System")
	main.call("_toggle_console")
	for section: String in ["all", "system"]:
		main.chat_log_tabs.buttons[section].pressed.emit()
		_check_announcements(section)
	main.chat_log_tabs.buttons["all"].pressed.emit()
	_chat("The horn sounds again over The First Bowl.")
	_expect(main.console_output.get_parsed_text().contains("The horn sounds again"),
		"new gauntlet messages appear while the console is open")
	_chat("Tavi: Early local message", 0, 0)
	_chat("[PM from Mira: Early private message]", 1, 0)
	_chat("[42] Rowan: Early channel message", 5, 0)
	var initial_count: int = app.chat_history.size()
	await _settle()
	# Ordinary gameplay must not evict earlier gauntlet announcements from
	# the full log when the bounded recent-message buffer rolls over.
	for index: int in range(app.CHAT_LINE_LIMIT + 5):
		match index % 3:
			0: _chat("Background notice %d" % index)
			1: app.append_local_line("Client notice %d" % index)
			2: app.append_local_message("Game notice %d" % index)
	_expect(app.chat_lines.size() == app.CHAT_LINE_LIMIT,
		"the HUD's recent-message buffer stays bounded")
	_expect(app.chat_history.size() == initial_count + app.CHAT_LINE_LIMIT + 5,
		"wire messages and both client message paths retain the complete session")
	_expect(is_same(app.chat_lines.back(), app.chat_history.back()),
		"recent and archived messages share presentation metadata")
	_check_announcements("All after recent-buffer rollover")
	main.chat_log_tabs.buttons["system"].pressed.emit()
	_check_announcements("System after recent-buffer rollover")
	_expect(not main.console_output.get_parsed_text().contains("Early local message"),
		"the System filter still excludes player conversations")
	for spec: Array in [["local", "Early local message"], ["pm:mira", "Early private message"],
			["channel:42", "Early channel message"]]:
		_expect(main.chat_log_tabs.buttons.has(spec[0]), "archived log tab survives: " + str(spec[0]))
		if main.chat_log_tabs.buttons.has(spec[0]):
			main.chat_log_tabs.buttons[spec[0]].pressed.emit()
			_expect(main.console_output.get_parsed_text().contains(spec[1]), "archived section retains: " + str(spec[1]))
	main.console_commands.ignored.append("mira")
	main.call("_sync_console")
	main.chat_log_tabs.buttons["pm:mira"].pressed.emit()
	_expect(not main.console_output.get_parsed_text().contains("Early private message"),
		"ignore also applies when rebuilding an archived log")
	main.console_commands.ignored.erase("mira")
	main.chat_log_tabs.buttons["all"].pressed.emit()
	main.call("_on_chat_submitted", "#find Red Canyon")
	_expect(main.console_output.get_parsed_text().contains("1 line(s) contain red canyon:"),
		"console search includes gauntlet messages older than the recent buffer")
	main.console_output.scroll_to_line(0)
	await _settle()
	if DisplayServer.get_name() != "headless":
		await RenderingServer.frame_post_draw
		root.get_texture().get_image().save_png(FOLDER.path_join("console.png"))
	main.call("_toggle_console")
	main.call("_toggle_console")
	_check_announcements("reopened All")
	app.call("_on_connection_state_changed", "disconnected")
	main.call("_sync_console")
	_expect(app.chat_lines.is_empty() and app.chat_history.is_empty()
		and main.console_output.get_parsed_text().is_empty(), "disconnect clears both histories for the next session")
	main.queue_free()
	await _settle()
	NativeAnimationImporter.clear()
	GlbSceneCache.clear()
	print("gauntlet console tests: ", "PASS" if failures == 0 else "FAIL (%d)" % failures)
	quit(failures)

func _chat(text: String, channel: int = 0, colour: int = 18) -> void:
	# gauntlets.say/status_text use deep_blue_text: local channel, EL c_blue3.
	var payload := PackedByteArray([channel])
	if colour > 0:
		payload.append(127 + colour)
	payload.append_array(text.to_utf8_buffer())
	payload.append(0)
	app.call("_on_packet", 0, payload)

func _check_announcements(section: String) -> void:
	for text: String in ANNOUNCEMENTS:
		_expect(main.console_output.get_parsed_text().contains(text), section + " retains " + text)

func _settle() -> void:
	for frame: int in range(8):
		await process_frame

func _expect(value: bool, label: String) -> void:
	if not value:
		failures += 1
		push_error("FAIL: " + label)
