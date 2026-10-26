extends SceneTree
## A real loopback session. The launcher supplies its isolated account privately.
const Presets := preload("res://src/ui/mixing_presets.gd")
const Chrome := preload("res://src/ui/compact_hud_style.gd")
var main: Control
var account: Dictionary = {}
var smoke := false
func _init() -> void: call_deferred("run")
func frames(count := 5) -> void:
	for frame: int in count: await process_frame
func fail(message: String) -> void:
	push_error("Mixing trial: " + message)
	quit(1)
func run() -> void:
	smoke = OS.get_environment("RL_MIXING_TRIAL_SMOKE") == "1"
	if smoke: create_timer(180).timeout.connect(func() -> void: fail("Trial verification exceeded its time limit."))
	var path := OS.get_environment("RL_MIXING_TRIAL_SESSION")
	if path.is_empty() or not FileAccess.file_exists(path):
		fail("Run test-mixing-editor.bat to start the private local server.")
		return
	var raw: Variant = JSON.parse_string(FileAccess.get_file_as_string(path))
	if not raw is Dictionary or raw.get("host") != "127.0.0.1":
		fail("The trial requires an isolated loopback session.")
		return
	account = raw
	root.title = "Rabbit Lands · local mixing design trial"
	root.size = Vector2i(1440, 900)
	main = (load("res://src/app/main.tscn") as PackedScene).instantiate()
	main.get_node("GameView/ChatWindow").preferences_path = "user://mixing-trial.cfg"
	root.add_child(main)
	await frames(10)
	main.host_edit.text = "127.0.0.1"
	main.port_edit.value = int(account.port)
	main._dev_plain_tcp = true
	main._on_connect_pressed()
	var app := root.get_node("AppState")
	var deadline := Time.get_ticks_msec() + 20000
	while app.connection_state != "connected" and Time.get_ticks_msec() < deadline: await process_frame
	if app.connection_state != "connected":
		fail("Could not connect to the local trial server.")
		return
	main.user_edit.text = str(account.username)
	main.password_edit.text = str(account.password)
	main._on_login_pressed()
	deadline = Time.get_ticks_msec() + 90000
	while not app.authenticated and Time.get_ticks_msec() < deadline: await process_frame
	if not app.authenticated:
		fail("Local trial login did not complete.")
		return
	while (main.arrival_curtain.blocks_input() or not app.mix_state.get("near_storage", false)) and Time.get_ticks_msec() < deadline: await process_frame
	if not app.mix_state.get("near_storage", false):
		fail("The trial storage keeper is not reachable.")
		return
	if main.arrival_curtain.blocks_input():
		fail("The trial world did not finish loading.")
		return
	main.window_stack.close_session_windows()
	main.lantern_guide.hide()
	main.manufacturing_source.button_pressed = true
	main.manufacturing_skill = ""
	main.manufacturing_filter.text = ""
	var bandage := -1
	for index: int in main.manufacturing_catalog.count():
		var recipe: Dictionary = main.manufacturing_catalog.recipe(index)
		if recipe.get("output") == "Bandage" and recipe.get("skill") == "potion": bandage = index
	main.selected_manufacturing_recipe = bandage
	main._set_manufacturing_quantity(20)
	main.manufacturing_panel.show()
	main._sync_manufacturing()
	_build_controls()
	await frames()
	if smoke: await _verify(bandage)

func _button(parent: Control, text: String, callback: Callable) -> void:
	var button := Button.new()
	button.text = text
	Chrome.button(button)
	button.pressed.connect(callback)
	parent.add_child(button)

func _build_controls() -> void:
	var panel := PanelContainer.new()
	panel.name = "MixingTrialControls"
	panel.position = Vector2(16, 95)
	panel.add_theme_stylebox_override("panel", Chrome.box())
	main.game_view.add_child(panel)
	var column := VBoxContainer.new()
	panel.add_child(column)
	var title := Label.new()
	title.text = "Local mixing trial"
	column.add_child(title)
	var hint := Label.new()
	hint.text = "Private character · stocked storage\nAll required tools are in your pack.\nThe storage keeper is beside you."
	hint.add_theme_font_size_override("font_size", 12)
	column.add_child(hint)
	var picker := OptionButton.new()
	for id: String in Presets.BUILT_INS:
		picker.add_item(Presets.BUILT_INS[id])
		picker.set_item_metadata(picker.item_count - 1, id)
		if id == main.mixing_workspace.model.active: picker.select(picker.item_count - 1)
	picker.item_selected.connect(func(index: int) -> void:
		main.mixing_workspace.choose_preset(str(picker.get_item_metadata(index)))
		main.manufacturing_panel.show())
	column.add_child(picker)
	_button(column, "Edit mixing…", main.mixing_workspace.open_editor)
	_button(column, "Show mixing window", func() -> void: main.manufacturing_panel.show())
	var row := HBoxContainer.new()
	column.add_child(row)
	var skill := OptionButton.new()
	for value: String in ["potion", "alchemy", "manufacturing", "crafting", "engineering", "tailoring", "summoning"]: skill.add_item(value)
	row.add_child(skill)
	var level := SpinBox.new()
	level.min_value = 0
	level.max_value = 200
	level.value = 100
	level.custom_minimum_size.x = 65
	row.add_child(level)
	_button(row, "Boost", func() -> void:
		main.get_node("/root/Network").send_chat("#boost %s %d" % [skill.get_item_text(skill.selected), int(level.value)]))
	var command_hint := Label.new()
	command_hint.text = "Or press Enter and type:\n#boost potion 1\n#boost potion 100\nEat Bread when food runs low."
	command_hint.add_theme_font_size_override("font_size", 12)
	column.add_child(command_hint)
	main.window_stack.register(panel)

func _verify(bandage: int) -> void:
	var valid: bool = bandage >= 0 and main.manufacturing_catalog.count() >= 475 and not main.manufacturing_mix_one.disabled
	valid = valid and not main.find_children("*", "AcceptDialog", true, false).any(func(dialog: Node) -> bool: return dialog.visible)
	var folder := str(account.trial_root).path_join("renders")
	var render := DisplayServer.get_name() != "headless"
	if render:
		DirAccess.make_dir_recursive_absolute(folder)
		main.game_view.get_node("MixingTrialControls").hide()
		main.chat_hud.hide()
		main.system_chat_hud.hide()
		root.size = Vector2i(1672, 941)
	for id: String in Presets.BUILT_INS:
		main.mixing_workspace.choose_preset(id, true)
		await frames()
		valid = valid and main.mixing_workspace._available_rect().grow(1).encloses(main.manufacturing_panel.get_global_rect())
		if render:
			await RenderingServer.frame_post_draw
			root.get_texture().get_image().save_png(folder.path_join(id + ".png"))
	main.mixing_workspace.open_editor()
	valid = valid and main.mixing_workspace.is_editing()
	if render:
		await frames()
		await RenderingServer.frame_post_draw
		root.get_texture().get_image().save_png(folder.path_join("editor.png"))
	main.mixing_workspace.finish_edit(false)
	main.mixing_workspace.choose_preset("workbench", true)
	main.mixing_workspace.set_sort_mode("level")
	var sword := -1
	for index: int in main.manufacturing_catalog.count():
		if main.manufacturing_catalog.recipe(index).get("output") == "Militia Arming Sword": sword = index
	main.selected_manufacturing_recipe = sword
	main._sync_manufacturing()
	await frames()
	valid = valid and sword >= 0 and main.mixing_workspace.selector.get_item_text(0) == "Iron Sword"
	var title: OptionButton = main.mixing_workspace.selector
	valid = valid and main.mixing_workspace.groups.details.get_global_rect().grow(1).encloses(title.get_global_rect())
	if render:
		await RenderingServer.frame_post_draw
		root.get_texture().get_image().save_png(folder.path_join("iron-sword.png"))
	main.mixing_workspace.set_sort_mode("name")
	main.selected_manufacturing_recipe = bandage
	main._sync_manufacturing()
	var app := root.get_node("AppState")
	for level: int in [1, 100]:
		main.get_node("/root/Network").send_chat("#boost potion %d" % level)
		var boost_deadline := Time.get_ticks_msec() + 8000
		while int(app.stats.get("potion_base", -1)) != level and Time.get_ticks_msec() < boost_deadline: await process_frame
		valid = valid and int(app.stats.get("potion_base", -1)) == level
	main._set_manufacturing_quantity(1)
	main._on_manufacturing_mix_one_pressed()
	var deadline := Time.get_ticks_msec() + 25000
	while Time.get_ticks_msec() < deadline:
		if app.mix_state.get("output") == "Bandage" and not app.mix_state.get("running", false) and int(app.mix_state.get("made", 0)) > 0: break
		await process_frame
	valid = valid and int(app.mix_state.get("made", 0)) > 0
	main._enqueue_selected()
	main._enqueue_selected()
	main._on_manufacturing_queue_start_pressed()
	deadline = Time.get_ticks_msec() + 25000
	while main.manufacturing_queue_running and Time.get_ticks_msec() < deadline: await process_frame
	valid = valid and not main.manufacturing_queue_running and main.manufacturing_queue.size() == 2
	for batch: Dictionary in main.manufacturing_queue: valid = valid and int(batch.made) == 1
	main.mixing_workspace.choose_preset(Presets.DEFAULT, true)
	print("MIXING TRIAL: ", "PASS" if valid else "FAIL")
	main.get_node("/root/Network").disconnect_from_server()
	main.queue_free()
	await frames()
	quit(0 if valid else 1)
