extends SceneTree
## Party content, saved HUD geometry and popup placement must agree.

const FOLDER := "res://test-artifacts/party-hud-layout"
var failures := 0
var main: Control
var workspace: Control
var windows: Control

func _init() -> void:
	_run.call_deferred()

func _frames() -> void:
	for frame: int in 10: await process_frame

func _run() -> void:
	create_timer(60).timeout.connect(func() -> void: quit(99))
	root.get_node("Network").block_for_hud_preview()
	if OS.get_cmdline_user_args().has("--embedded"): root.gui_embed_subwindows = true
	root.size = Vector2i(1024, 600)
	DirAccess.make_dir_recursive_absolute(ProjectSettings.globalize_path(FOLDER))
	var settings := FOLDER.path_join("settings.cfg")
	ConfigFile.new().save(settings)
	main = load("res://src/app/main.tscn").instantiate()
	main.get_node("GameView/ChatWindow").preferences_path = settings
	root.add_child(main)
	main.get_node("LoginPanel").hide()
	main.get_node("LoginBackground").hide()
	main.game_view.show()
	root.content_scale_factor = 1.0
	await _frames()
	workspace = main.hud_workspace
	windows = main.extension_windows
	windows.preferences_path = settings
	_party(2)
	workspace.choose_preset("classic", true)
	var config: Dictionary = workspace.model.working.parts.party
	config.enabled = true
	config.dock_target = "none"
	config.edge_dock = "none"
	config.axis_scale = Vector2.ONE
	for key: String in workspace.Presets.PARTS:
		if workspace.model.working.parts[key].dock_target == "party":
			workspace.model.working.parts[key].dock_target = "none"
	config.compact = false
	config.frame_style = "panel"
	config.show_background = true
	config.show_border = true
	config.show_player_details = true
	config.show_self = true
	config.dimensions = Vector2(220, 180)
	workspace.apply_layout()
	await _frames()
	var panel: Control = windows.party_panel
	_expect(panel.get_global_rect().encloses(windows.party_add_bot.get_global_rect()), "party actions stay inside the HUD frame")
	_expect(_frame_matches(), "HUD border follows settled content minimum")
	windows.resize_party_window(Vector2(320, 380))
	windows._save_party_layout()
	await _frames()
	var resized := panel.size
	_expect(_frame_matches(), "native party resize updates the HUD border")
	workspace.apply_layout()
	await _frames()
	_expect(panel.size.is_equal_approx(resized), "reapplying HUD settings preserves a party-grip resize")
	windows.party_collapse.pressed.emit()
	await _frames()
	_expect(not windows.party_resize_grip.is_visible_in_tree() and panel.size.y < resized.y, "HUD processing keeps a collapsed party compact")
	_expect(_frame_matches(), "collapsed party border matches the header")
	windows.party_collapse.pressed.emit()
	await _frames()
	_expect(panel.size.is_equal_approx(resized), "expanding restores the requested party dimensions")
	config.compact = true
	workspace.apply_layout()
	await _frames()
	_expect(_frame_matches(), "compact visibility changes refresh the HUD border")
	config.compact = false
	config.show_player_details = false
	config.dimensions = Vector2(2000, 1600)
	config.scale = 1.5
	workspace.apply_layout()
	await _frames()
	_expect(root.get_visible_rect().encloses(panel.get_global_rect()), "scaled party HUD fits the viewport")
	_expect(_frame_matches(), "scaled party border uses the fitted dimensions")
	config.scale = 1.0
	config.dimensions = Vector2(244, 180)
	config.anchor = "bottom_right"
	config.offset = Vector2(-8, -8)
	workspace.apply_layout()
	await _frames()
	var picker: MenuButton = windows.party_add_bot
	# Use the real MenuButton input path, including its automatic placement.
	var click := InputEventMouseButton.new()
	click.button_index = MOUSE_BUTTON_LEFT
	click.pressed = true
	click.position = picker.get_global_rect().get_center()
	click.global_position = click.position
	root.push_input(click, true)
	await _frames()
	var popup: PopupMenu = picker.get_popup()
	_expect(popup.visible, "add-bot button opens its class menu")
	var menu_bounds := Rect2i(root.get_visible_rect()) if popup.is_embedded() else Rect2i(root.get_screen_transform() * root.get_visible_rect())
	_expect(menu_bounds.encloses(Rect2i(popup.position, popup.size)), "bot menu stays inside the bottom and right viewport edges")
	var button_rect := picker.get_global_rect() if popup.is_embedded() else picker.get_screen_transform() * Rect2(Vector2.ZERO, picker.size)
	_expect(popup.position.y + popup.size.y <= ceili(button_rect.position.y), "bottom-edge bot menu opens above its button")
	if DisplayServer.get_name() != "headless":
		await RenderingServer.frame_post_draw
		root.get_texture().get_image().save_png(FOLDER.path_join("party-bottom-menu.png"))
	popup.hide()
	# Auto height must track a roster update after the container pass.
	windows.party_options.get_popup().id_pressed.emit(1)
	await _frames()
	var small_height := panel.size.y
	_party(7)
	await _frames()
	_expect(panel.size.y > small_height and _frame_matches(), "growing roster resizes its content and HUD border together")
	_party(2)
	await _frames()
	_expect(is_equal_approx(panel.size.y, small_height) and _frame_matches(), "shrinking roster removes unused HUD height")
	main.free()
	await process_frame
	print("party HUD layout: ", "PASS" if failures == 0 else "FAIL (%d)" % failures)
	quit(failures)

func _party(count: int) -> void:
	var members: Array = []
	for index: int in count:
		members.append({"name":"Leader" if index == 0 else "Companion %d" % index,
			"is_self":index == 0, "leader":index == 0, "online":true,
			"health":80, "max_health":100, "ether":20, "max_ether":40, "map_id":"landfall"})
	var app: Node = root.get_node("AppState")
	app.party = {"in_party":true, "members":members, "invited_by":""}
	app.state_changed.emit(&"party")

func _frame_matches() -> bool:
	var inverse: Transform2D = main.game_view.get_global_transform().affine_inverse()
	var actual: Rect2 = inverse * windows.party_panel.get_global_rect()
	for frame: Dictionary in workspace.frame_overlay.panels:
		if frame.rect.is_equal_approx(actual): return true
	return false

func _expect(value: bool, label: String) -> void:
	if value: print("PASS: ", label)
	else:
		failures += 1
		push_error("FAIL: " + label)
