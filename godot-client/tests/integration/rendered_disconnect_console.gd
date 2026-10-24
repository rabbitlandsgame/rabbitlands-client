extends SceneTree
## Render the production disconnect console and exercise its live palette controls.
const Colors := preload("res://src/ui/chat_colors.gd")
const TextColors := preload("res://src/ui/text_colors.gd")
const Presets := preload("res://src/ui/hud_presets.gd")
const SETTINGS_PATH := "res://test-artifacts/disconnect-console/rendered-settings.cfg"
var failures := 0

func _init() -> void:
	_run.call_deferred()

func _run() -> void:
	root.size = Vector2i(1280, 720)
	var out := OS.get_environment("ELORIA_ARTIFACT_DIR")
	if out.is_empty():
		out = ProjectSettings.globalize_path("res://test-artifacts/disconnect-console/rendered")
	DirAccess.make_dir_recursive_absolute(out)
	DirAccess.make_dir_recursive_absolute(ProjectSettings.globalize_path(SETTINGS_PATH.get_base_dir()))
	Colors.save_colors(Colors.defaults(), SETTINGS_PATH)
	var main: Control = (load("res://src/app/main.tscn") as PackedScene).instantiate()
	main.get_node("GameView/ChatWindow").preferences_path = SETTINGS_PATH
	root.add_child(main)
	await _settle()
	await _capture(out.path_join("login-text.png"))
	var network := root.get_node("Network")
	var app := root.get_node("AppState")
	network.set_process(false)
	network.set("_host", "127.0.0.1")
	network.set("_port", 1)
	network.set("_session_username", "render-fixture")
	network.set("_session_password", "in-memory-fixture")
	network.set("_session_credentials_confirmed", true)
	network.call("_set_state", "connected")
	app.set("authenticated", true)
	app.active_channels.assign([3, 6, 4, 17771])
	app.active_channel_index = 0
	main.call("_set_login_screen_visible", false)
	main.game_view.show()
	# Exercise role rendering in a real ItemList, including its explicit colors.
	main.stats_panel.show()
	main.stats_tabs.current_tab = 1
	main.knowledge_catalog.assign(["Known entry", "Unread entry"])
	app.known_knowledge.assign([0])
	app.selected_knowledge = -1
	main.call("_sync_knowledge")
	_expect(main.knowledge_list.get_item_custom_fg_color(0) == Color.WHITE
		and main.knowledge_list.get_item_custom_fg_color(1) == Color("999999"), "knowledge read and unread use EL defaults")
	app.selected_knowledge = 0
	main.set("_knowledge_hover_index", 1)
	main.call("_sync_knowledge_item_colors")
	_expect(main.knowledge_list.get_item_custom_fg_color(0) == TextColors.color("knowledge_selected")
		and main.knowledge_list.get_item_custom_fg_color(1) == TextColors.color("knowledge_hover"), "selected and hovered knowledge entries have independent colors")
	main.stats_panel.hide()
	main.hud_workspace.change_part("timer", "text_color", Color("55ccff"))
	main.call("_sync_hud_timer_label")
	TextColors.set_color("hud_timer_stopped", Color.MAGENTA)
	_expect(main.hud_timer_label.get_theme_color("font_color") == Color("55ccff"), "runtime refresh and shared colors preserve custom HUD tint")
	TextColors.reset("hud_timer_stopped")
	var migrated: Dictionary = Presets.normalise({"version": Presets.VERSION, "parts": {"timer": {"text_color": Color("eee3c8")}}})
	_expect(not migrated.parts.timer.text_color_custom, "old untouched HUD cream upgrades to semantic text defaults")
	migrated = Presets.normalise({"version": Presets.VERSION, "parts": {"timer": {"text_color": Color.MAGENTA}}})
	_expect(migrated.parts.timer.text_color_custom, "old custom HUD colors remain explicit choices")
	main.hud_workspace.model.working.legacy = true
	TextColors.set_color("hud_timer_stopped", Color.MAGENTA)
	_expect(main.hud_timer_label.get_theme_color("font_color") == Color.MAGENTA
		and not main.hud_timer_label.has_meta("hud_text_color_override"), "legacy HUD clears stale component tint and restores the current role")
	main.hud_workspace.model.working.legacy = false
	main.hud_workspace.apply_layout()
	TextColors.reset("hud_timer_stopped")
	_chat(app, 3, 8, "While harvesting, Mother Nature blessed you with 253 harvesting experience!")
	_chat(app, 6, 6, "[6] Leonard: Coming home, far away, as the vapor trails alight.")
	_chat(app, 3, 11, "Thargas found 1 Pear.")
	_chat(app, 2, 11, "#GM from Shrek: Warriors... come out to play.")
	_chat(app, 5, 5, "[3] DarkShark: WTT: 100 s2e ings + food for s2e")
	_chat(app, 3, 8, "While trying to harvest, the outhouse lid fell on Rabbitman, hitting for 20 health.")
	_chat(app, 3, 3, "Local files saved, asking server to save too...")
	_chat(app, 3, 3, "You have been saved!")
	main.call("_on_chat_submitted", "#disco")
	await _settle()
	_expect(main.console_panel.visible and not main.login_panel.visible,
		"manual disconnect shows the console instead of login")
	_expect(main.get_node("%ConsoleClose").disabled, "the console cannot close over a disconnected world")
	_expect(not main.chat_hud.visible and not main.system_chat_hud.visible,
		"floating feeds do not overlap the full console")
	_expect(main.console_output.get_parsed_text().contains("Thargas found 1 Pear.")
		and main.console_output.get_parsed_text().contains("Press any key"), "the rendered log retains context and instructions")
	_expect(main.get_node("%DisconnectButton").is_visible_in_tree(), "the logout menu icon remains available")
	await _capture(out.path_join("console.png"))
	main.settings_window.open_tab("Chat")
	await _settle()
	var page: VBoxContainer = main.settings_window.page_body("Chat")
	var reset: Button = page.find_child("chat_colors_reset", true, false)
	var scroll := page.get_parent() as ScrollContainer
	scroll.ensure_control_visible(reset)
	await _settle()
	var picker: ColorPickerButton = page.find_child("chat_color_harvest", true, false)
	var replacement := Color("e0a0ff")
	picker.color_changed.emit(replacement)
	_expect(main.call("_chat_line_colour", {"channel": 3, "text": "You started to harvest Sunleaf."}) == replacement,
		"a real settings picker updates production message colors")
	_expect(Colors.load_colors(SETTINGS_PATH).harvest == replacement,
		"the production settings handler persists the chosen color")
	reset.pressed.emit()
	_expect(main.get("_chat_colors") == Colors.defaults(), "the real reset control restores every default")
	main.chat_hud.set_destination("channel:17771")
	_expect(main.call("_chat_active_channel_number") == 17771, "the fourth channel can be the active color heading")
	main.call("_on_client_setting_changed", "Chat", "chat_channel_color:17771", replacement)
	_expect(Colors.is_overridden(main.get("_chat_colors"), Colors.channel_override_key(17771)), "channel picker creates a saved explicit choice")
	main.call("_on_client_setting_changed", "Chat", "chat_channel_reset:17771", true)
	_expect(not Colors.is_overridden(Colors.load_colors(SETTINGS_PATH), Colors.channel_override_key(17771)), "channel reset removes the persisted override")
	await _capture(out.path_join("chat-colors.png"))
	main.settings_window.open_tab("TextColors")
	await _settle()
	var text_page: VBoxContainer = main.settings_window.page_body("TextColors")
	var label_picker: ColorPickerButton = text_page.find_child("text_color_ui_label", true, false)
	label_picker.color_changed.emit(replacement)
	_expect(main.theme.get_color("font_color", "Label") == replacement,
		"the settings picker updates the real shared interface theme")
	var saved := ConfigFile.new()
	_expect(saved.load(SETTINGS_PATH) == OK and saved.get_value("text_colors", "ui_label") == replacement,
		"the settings picker persists shared text colors beside chat preferences")
	(text_page.find_child("text_color_reset_ui_label", true, false) as Button).pressed.emit()
	_expect(main.theme.get_color("font_color", "Label") == TextColors.DEFAULTS.ui_label,
		"the real per-role reset restores its EL default")
	await _capture(out.path_join("text-colors.png"))
	var escape := InputEventKey.new()
	escape.keycode = KEY_ESCAPE
	escape.physical_keycode = KEY_ESCAPE
	escape.pressed = true
	root.push_input(escape, true)
	_expect(not main.settings_panel.visible and main.console_panel.visible and not network.is_reconnecting(),
		"closing settings restores the disconnected console without starting a retry")
	main.get_node("%DisconnectButton").pressed.emit()
	_expect(main.login_panel.visible and not main.game_view.visible and app.chat_lines.is_empty(),
		"the menu icon returns to login and clears the session")
	main.queue_free()
	await _settle()
	DirAccess.remove_absolute(ProjectSettings.globalize_path(SETTINGS_PATH))
	print("rendered disconnect console: ", "PASS" if failures == 0 else "FAIL (%d)" % failures)
	quit(failures)

func _chat(app: Node, channel: int, color: int, text: String) -> void:
	var payload := PackedByteArray([channel, 127 + color])
	payload.append_array(text.to_utf8_buffer())
	payload.append(0)
	app.call("_on_packet", 0, payload)

func _settle() -> void:
	for _frame: int in 6:
		await process_frame

func _capture(path: String) -> void:
	if DisplayServer.get_name() == "headless":
		return
	await RenderingServer.frame_post_draw
	var screenshot := root.get_texture().get_image()
	_expect(screenshot != null and screenshot.save_png(path) == OK, "saved " + path.get_file())

func _expect(value: bool, message: String) -> void:
	if not value:
		failures += 1
		push_error("FAIL: " + message)
