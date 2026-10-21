extends SceneTree
## Interactive local-only client fixture. The networking guard is armed before
## the real main scene exists. All preferences and samples use a test profile.
const PreviewState := preload("res://prototypes/hud_preview_state.gd")
var main: Control
var controls: PanelContainer

func _init() -> void:
	call_deferred("_run")

func _run() -> void:
	var smoke := OS.get_cmdline_user_args().has("--preview-smoke-check")
	if smoke: create_timer(40).timeout.connect(func() -> void: quit(99))
	var capture := OS.get_cmdline_user_args().has("--preview-capture")
	if capture: create_timer(120).timeout.connect(func() -> void: quit(99))
	root.get_node("Network").block_for_hud_preview()
	root.size = Vector2i(1440, 900)
	root.title = "Rabbit Lands · local HUD sandbox · no server connection"
	main = (load("res://src/app/main.tscn") as PackedScene).instantiate()
	main.get_node("GameView/ChatWindow").preferences_path = "user://hud-preview.cfg"
	root.add_child(main)
	for frame: int in 8: await process_frame
	main.get_node("LoginPanel").hide()
	main.get_node("LoginBackground").hide()
	main.game_view.show()
	var app := root.get_node("AppState")
	PreviewState.populate(main, app)
	if not smoke:
		main._load_server_map()
		main._sync_world()
	if not main.hud_workspace.model.loaded: main.hud_workspace.choose_preset("classic")
	var layer := CanvasLayer.new()
	layer.layer = 1000
	root.add_child(layer)
	controls = PreviewControls.new()
	layer.add_child(controls)
	controls.configure(main, app)
	main.hud_workspace.input_exclusions.append(controls)
	var deadline := Time.get_ticks_msec() + 45000
	while not smoke and main.world_loader.world_root == null and Time.get_ticks_msec() < deadline: await process_frame
	while not smoke and main.arrival_curtain.is_showing() and Time.get_ticks_msec() < deadline: await process_frame
	main._end_arrival()
	if smoke:
		await _smoke_check()
	elif capture:
		await _capture_preview()

func _capture_preview() -> void:
	var folder := "res://test-artifacts/hud-presets/local-sandbox"
	DirAccess.make_dir_recursive_absolute(ProjectSettings.globalize_path(folder))
	for frame: int in 60: await process_frame
	main._end_arrival()
	await RenderingServer.frame_post_draw
	root.get_texture().get_image().save_png(folder.path_join("sandbox.png"))
	main.hud_workspace.open_editor()
	main.hud_workspace.panel.position = Vector2(30, 180)
	main.hud_workspace.select_component("utilities")
	controls.position = Vector2(720, 70)
	for frame: int in 12: await process_frame
	await RenderingServer.frame_post_draw
	root.get_texture().get_image().save_png(folder.path_join("sandbox-editor.png"))
	main.character_intro.cancel()
	main.exterior_stream.clear()
	while not main.exterior_stream.is_idle(): await process_frame
	await ContinentChunkStream.drain_workers(self)
	main.queue_free()
	controls.get_parent().queue_free()
	for frame: int in 5: await process_frame
	Input.set_custom_mouse_cursor(null, Input.CURSOR_ARROW)
	Input.set_custom_mouse_cursor(null, Input.CURSOR_IBEAM)
	NativeAnimationImporter.clear()
	GlbSceneCache.clear()
	(load("res://src/ui/technique_icons.gd") as GDScript)._cache.clear()
	(load("res://src/ui/hud_resource_icons.gd") as GDScript)._cache.clear()
	(load("res://src/ui/hud_resource_icons.gd") as GDScript)._tinted.clear()
	(load("res://src/ui/hud_medallion.gd") as GDScript)._textures.clear()
	var actor_script: GDScript = load("res://src/actors/replicated_actor_3d.gd")
	actor_script._wardrobe_texture_cache.clear()
	actor_script._equipment_pieces_cache.clear()
	(load("res://src/world/look/look_ground.gd") as GDScript)._class_textures.clear()
	for frame: int in 2: await process_frame
	quit()

func _smoke_check() -> void:
	var network := root.get_node("Network")
	main.hud_workspace.open_editor()
	var click := InputEventMouseButton.new()
	click.position = controls.get_global_rect().get_center()
	click.pressed = true
	click.button_index = MOUSE_BUTTON_LEFT
	var controls_reachable: bool = not main.hud_workspace.handle_input(click)
	var initial: int = root.get_node("AppState").party.members.size()
	controls.add_member()
	var added: bool = root.get_node("AppState").party.members.size() == initial + 1
	controls.remove_member()
	var removed: bool = root.get_node("AppState").party.members.size() == initial
	controls.clear_party()
	var cleared: bool = root.get_node("AppState").party.members.is_empty()
	controls.reset_party()
	main.hud_workspace.choose_preset("classic")
	main.hud_workspace.change_part("party", "enabled", true)
	controls.picker.select(0)
	controls.cycle_health()
	var blocked: bool = network.offline_hud_preview and network.connect_to_server("127.0.0.1", 2000, false) == ERR_UNAVAILABLE and network.send_frame(PackedByteArray([1])) == ERR_UNAVAILABLE
	for frame: int in 5: await process_frame
	var live_rows: bool = main.extension_windows.party_rows.get_child_count() == initial
	var detailed_player: bool = main.hud_workspace.party_summary.visible and main.hud_workspace.party_summary._data().health == controls.members[0].health
	var ok := added and removed and cleared and blocked and controls_reachable and live_rows and detailed_player
	print("LOCAL HUD SANDBOX: ", "PASS" if ok else "FAIL", " · add/remove/clear/reset; real party rows and live player summary; controls usable during editing; connections and sends blocked")
	main.queue_free()
	controls.get_parent().queue_free()
	for frame: int in 5: await process_frame
	quit(0 if ok else 1)

class PreviewControls extends PanelContainer:
	var main: Control
	var app: Node
	var picker: OptionButton
	var presets: OptionButton
	var count_label: Label
	var body: VBoxContainer
	var members: Array = []
	var next_member := 3
	var offline: CheckBox
	var show_roster: CheckBox
	var restore_button: Button
	var _sync_time := 0.0
	var _refreshing := false

	func configure(owner_main: Control, state: Node) -> void:
		main = owner_main
		app = state
		name = "LocalHudPreviewControls"
		position = Vector2(390, 120)
		custom_minimum_size = Vector2(380, 0)
		var box := StyleBoxFlat.new()
		box.bg_color = Color("141d22f5")
		box.border_color = Color("8cb7bf")
		box.set_border_width_all(1)
		box.set_corner_radius_all(6)
		box.set_content_margin_all(12)
		add_theme_stylebox_override("panel", box)
		var column := VBoxContainer.new()
		column.add_theme_constant_override("separation", 7)
		add_child(column)
		var title_row := HBoxContainer.new()
		column.add_child(title_row)
		var title := Label.new()
		title.text = "Local HUD sandbox"
		title.size_flags_horizontal = Control.SIZE_EXPAND_FILL
		title.add_theme_font_size_override("font_size", 17)
		title_row.add_child(title)
		var fold := _button("Fold", func() -> void:
			body.visible = not body.visible
			reset_size())
		title_row.add_child(fold)
		var dragger := WindowDrag.attach(self, title_row)
		dragger.reserved_right = 6
		dragger.reserved_bottom = 6
		body = VBoxContainer.new()
		body.add_theme_constant_override("separation", 7)
		column.add_child(body)
		var notice := Label.new()
		notice.text = "Sample data · no login or server connection"
		notice.add_theme_font_size_override("font_size", 12)
		body.add_child(notice)
		presets = OptionButton.new()
		var model: Object = main.hud_workspace.model
		for id: String in model.BUILT_INS:
			presets.add_item(model.BUILT_INS[id])
			presets.set_item_metadata(presets.item_count - 1, id)
			if id == model.active: presets.select(presets.item_count - 1)
		presets.item_selected.connect(func(index: int) -> void: main.hud_workspace.choose_preset(str(presets.get_item_metadata(index))))
		body.add_child(presets)
		var edit_row := HBoxContainer.new()
		body.add_child(edit_row)
		edit_row.add_child(_button("Edit HUD", func() -> void: main.hud_workspace.open_editor()))
		restore_button = _button("Restore preset default", func() -> void: main.hud_workspace.reset_builtin())
		edit_row.add_child(restore_button)
		show_roster = CheckBox.new()
		show_roster.text = "Show party roster in this preset"
		show_roster.set_pressed_no_signal(main.hud_workspace.model.working.parts.party.enabled)
		show_roster.toggled.connect(func(value: bool) -> void: main.hud_workspace.change_part("party", "enabled", value))
		body.add_child(show_roster)
		picker = OptionButton.new()
		body.add_child(picker)
		picker.item_selected.connect(func(_index: int) -> void: _refresh_member())
		var row := HBoxContainer.new()
		body.add_child(row)
		row.add_child(_button("+ Add member", add_member))
		row.add_child(_button("− Remove selected", remove_member))
		var secondary := HBoxContainer.new()
		body.add_child(secondary)
		secondary.add_child(_button("Clear party", clear_party))
		secondary.add_child(_button("Reset samples", reset_party))
		offline = CheckBox.new()
		offline.text = "Selected member offline"
		offline.toggled.connect(func(value: bool) -> void:
			if _refreshing or picker.selected < 0 or members.is_empty(): return
			members[picker.selected].online = not value
			PreviewState.set_party(app, members))
		body.add_child(offline)
		body.add_child(_button("Cycle selected member's health", cycle_health))
		count_label = Label.new()
		count_label.add_theme_font_size_override("font_size", 12)
		body.add_child(count_label)
		members = app.party.members.duplicate(true)
		_refresh_list()

	func cycle_health() -> void:
		if picker.selected < 0 or members.is_empty(): return
		var member: Dictionary = members[picker.selected]
		member.health = 150 if int(member.health) <= 25 else maxi(10, int(member.health) - 40)
		if member.get("is_self", false):
			app.stats.health = member.health
			app.stats.max_health = member.max_health
			app.emit_signal("state_changed", &"stats")
		PreviewState.set_party(app, members)

	func _process(delta: float) -> void:
		if main == null or show_roster == null: return
		_sync_time += delta
		if _sync_time < 0.2: return
		_sync_time = 0
		var model: Object = main.hud_workspace.model
		show_roster.set_pressed_no_signal(model.working.parts.party.enabled)
		restore_button.disabled = not model.BUILT_INS.has(model.active)
		for index: int in presets.item_count:
			if presets.get_item_metadata(index) == model.active:
				if presets.selected != index: presets.select(index)
				return
		if model.custom.has(model.active):
			presets.add_item("Custom · " + str(model.custom[model.active].name))
			presets.set_item_metadata(presets.item_count - 1, model.active)
			presets.select(presets.item_count - 1)

	func _button(caption: String, action: Callable) -> Button:
		var button := Button.new()
		button.text = caption
		button.focus_mode = Control.FOCUS_NONE
		button.add_theme_font_size_override("font_size", 12)
		button.pressed.connect(action)
		return button

	func add_member() -> void:
		if members.size() >= 12: return
		members.append(PreviewState.member(next_member))
		next_member += 1
		_refresh_list(members.size() - 1)

	func remove_member() -> void:
		if members.is_empty(): return
		members.remove_at(maxi(0, picker.selected))
		_refresh_list(mini(picker.selected, members.size() - 1))

	func clear_party() -> void:
		members.clear()
		_refresh_list()

	func reset_party() -> void:
		members = [PreviewState.member(0), PreviewState.member(1), PreviewState.member(2)]
		next_member = 3
		_refresh_list()

	func _refresh_list(selected_index := 0) -> void:
		picker.clear()
		for member: Dictionary in members: picker.add_item(str(member.name))
		if not members.is_empty(): picker.select(clampi(selected_index, 0, members.size() - 1))
		count_label.text = "%d / 12 sample party members · drag this box to move it" % members.size()
		PreviewState.set_party(app, members)
		_refresh_member()

	func _refresh_member() -> void:
		_refreshing = true
		offline.disabled = members.is_empty()
		offline.set_pressed_no_signal(not members[picker.selected].online if not members.is_empty() and picker.selected >= 0 else false)
		_refreshing = false
