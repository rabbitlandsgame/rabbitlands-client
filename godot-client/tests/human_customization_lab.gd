extends SceneTree
## Interactive, network-blocked review of the production Human appearance UI.

const EDITOR = preload("res://src/ui/appearance_editor.gd")
const SAVE_PATH := "user://human-workshop.json"
const POSES := [&"idle", &"walk", &"run", &"attack_primary", &"cast_channel"]
var _canvas: Control
var _header_margin: MarginContainer
var _editor
var _sex: OptionButton
var _outfit: OptionButton
var _pose: OptionButton
var _quality: OptionButton
var _pause: CheckBox
var _message: Label
var _models: Dictionary
var _animations: Dictionary
var _equipment: Dictionary
var _looks: Dictionary = {}
var _current_sex := -1
var _failures := 0
var _smoke := false
var _changing := false

func _init() -> void:
	call_deferred("_run")

func _run() -> void:
	root.get_node("Network").block_for_hud_preview()
	_smoke = OS.get_cmdline_user_args().has("--smoke-test")
	Engine.max_fps = 60
	root.content_scale_size = Vector2i.ZERO
	root.size = Vector2i(1440, 900)
	DisplayServer.window_set_title("Rabbit Lands — Human Customization Workshop")
	DisplayServer.window_set_min_size(Vector2i(1080, 760))
	DisplayServer.window_set_size(Vector2i(1440, 900))
	_models = _json("res://data/actors/models.json").get("models", {})
	_animations = _json("res://data/animations/luminous.json")
	_equipment = _json("res://data/actors/equipment.json")
	if FileAccess.file_exists(SAVE_PATH):
		_looks = _json(SAVE_PATH)
	_build_ui()
	_select_sex(0)
	root.size_changed.connect(_fit)
	await process_frame
	await process_frame
	_fit()
	if _smoke:
		await _run_smoke()

func _json(path: String) -> Dictionary:
	var value: Variant = JSON.parse_string(FileAccess.get_file_as_string(path))
	return value if value is Dictionary else {}

func _build_ui() -> void:
	_canvas = Control.new()
	root.add_child(_canvas)
	_canvas.set_anchors_and_offsets_preset(Control.PRESET_FULL_RECT)
	var background := ColorRect.new()
	background.color = Color("10191f")
	background.mouse_filter = Control.MOUSE_FILTER_IGNORE
	_canvas.add_child(background)
	background.set_anchors_and_offsets_preset(Control.PRESET_FULL_RECT)
	_canvas.theme = _theme()
	var margin := MarginContainer.new()
	_header_margin = margin
	_canvas.add_child(margin)
	margin.set_anchors_and_offsets_preset(Control.PRESET_TOP_WIDE)
	for edge: String in ["left", "right", "top"]:
		margin.add_theme_constant_override("margin_" + edge, 20)
	var header := VBoxContainer.new()
	margin.add_child(header)
	var title := Label.new()
	title.text = "Rabbit Lands · Human Workshop"
	title.add_theme_font_size_override("font_size", 25)
	header.add_child(title)
	var toolbar := HFlowContainer.new()
	toolbar.add_theme_constant_override("h_separation", 8)
	toolbar.add_theme_constant_override("v_separation", 6)
	header.add_child(toolbar)
	_sex = _picker(toolbar, "Body", ["Human Female", "Human Male"])
	_sex.item_selected.connect(_select_sex)
	_outfit = _picker(toolbar, "Outfit", ["Portrait outfit", "Vanguard", "Ranger", "Arcanist", "Warden"])
	_outfit.item_selected.connect(func(_index: int) -> void: _refresh_outfit())
	_pose = _picker(toolbar, "Pose", ["Idle", "Walk in place", "Run in place", "Attack", "Cast"])
	_pose.item_selected.connect(func(_index: int) -> void: _play_pose())
	_quality = _picker(toolbar, "Graphics", ["Low", "Medium", "High"])
	_quality.select(1)
	_quality.item_selected.connect(func(index: int) -> void:
		_editor.set_preview_quality(index)
		_message.text = "High uses the portrait art in development. Low and Medium use the lightweight Human appearance.")
	_pause = CheckBox.new()
	_pause.text = "Pause"
	toolbar.add_child(_pause)
	_pause.toggled.connect(func(held: bool) -> void:
		var actor: ReplicatedActor3D = _editor.get("_actor")
		if is_instance_valid(actor):
			if held:
				actor.animation_player.pause()
			else:
				actor.animation_player.play())
	var front := Button.new()
	front.text = "Front view"
	front.tooltip_text = "Face the camera straight on to inspect the face and arm movement"
	toolbar.add_child(front)
	front.pressed.connect(_front_view)
	var screenshot := Button.new()
	screenshot.text = "Screenshot"
	toolbar.add_child(screenshot)
	screenshot.pressed.connect(_capture)
	var folder := Button.new()
	folder.text = "Open saves"
	folder.tooltip_text = "Open screenshots and saved preview choices"
	toolbar.add_child(folder)
	folder.pressed.connect(func() -> void: OS.shell_open(OS.get_user_data_dir()))
	_message = Label.new()
	_message.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
	_message.minimum_size_changed.connect(_fit.call_deferred)
	_message.text = "Offline preview · Drag to rotate · Face / full body changes zoom · Save preview keeps your choices on this computer."
	header.add_child(_message)
	_editor = EDITOR.new()
	_canvas.add_child(_editor)
	_editor.set_preview_quality(_quality.selected)
	for node: Node in _editor.find_children("*", "Button", true, false):
		var button := node as Button
		if button.text == "Close":
			button.text = "Exit preview"
			button.pressed.connect(func() -> void: quit())
		elif button.text == "Apply appearance":
			button.text = "Save preview"
	_editor.get("_form").changed.connect(func() -> void:
		if not _changing:
			_play_pose(false))

func _picker(parent: Node, label_text: String, entries: Array) -> OptionButton:
	var group := HBoxContainer.new()
	parent.add_child(group)
	var label := Label.new()
	label.text = label_text
	group.add_child(label)
	var picker := OptionButton.new()
	for entry: String in entries:
		picker.add_item(entry)
	group.add_child(picker)
	return picker

func _theme() -> Theme:
	var theme := Theme.new()
	theme.default_font_size = 17
	for type: String in ["Label", "Button", "OptionButton", "CheckBox"]:
		theme.set_color("font_color", type, Color("ead3a3"))
	for type: String in ["Button", "OptionButton"]:
		for state: String in ["normal", "hover", "pressed", "focus"]:
			var box := StyleBoxFlat.new()
			box.bg_color = Color("26343d") if state == "hover" else Color("121a20")
			box.border_color = Color("c99b48")
			box.set_border_width_all(1)
			box.set_corner_radius_all(3)
			box.set_content_margin_all(6)
			theme.set_stylebox(state, type, box)
	var panel := StyleBoxFlat.new()
	panel.bg_color = Color("11191e")
	panel.border_color = Color("a67b3d")
	panel.set_border_width_all(2)
	panel.set_content_margin_all(10)
	theme.set_stylebox("panel", "PanelContainer", panel)
	return theme

func _default_look(sex: int) -> Dictionary:
	return {"skin": 2, "eyes": 1 if sex == 0 else 2, "hair": AppearanceVariants.pack_hair(3 if sex == 0 else 1, 4 if sex == 0 else 1),
		"shirt": 5, "pants": 2, "boots": 2, "hair_detail": 2 if sex == 0 else 1,
		"facial_hair": 0, "jaw": 35 if sex == 0 else 60, "cheekbones": 70 if sex == 0 else 65,
		"nose": 35 if sex == 0 else 45, "height": 50, "build": 38 if sex == 0 else 50}

func _select_sex(index: int) -> void:
	if is_instance_valid(_editor.get("_actor")) and _current_sex >= 0:
		_looks[str(_current_sex)] = _editor.call("_values")
	_current_sex = index
	_sex.select(index)
	_changing = true
	_editor.call("_release_preview")
	var look: Dictionary = _looks.get(str(index), _default_look(index))
	var dto := {"actor_id": 1, "actor_type": index, "kind": 1, "x": 0, "y": 0,
		"rotation": 0, "name": "", "appearance": look, "equipment_visuals": _loadout()}
	_editor.set_preview_quality(_quality.selected)
	_editor.open_for(dto, _models["luminous_female" if index == 0 else "luminous_male"], _animations, _equipment, _save_preview)
	for node: Node in _editor.find_children("*", "CheckBox", true, false):
		var check := node as CheckBox
		if check.text == "Show equipment":
			check.set_pressed_no_signal(true)
	_editor.set("_show_equipment", true)
	_refresh_outfit()
	(_editor.get("_status") as Label).text = "Try the portrait presets, face sliders, hair and beard choices. Your live character is unchanged."
	_changing = false
	_play_pose()
	_fit.call_deferred()

func _loadout() -> Dictionary:
	if _outfit.selected > 0:
		return CreationArchetypes.loadout_at(_outfit.selected - 1)
	return {5: 225, 2: 100} if _current_sex == 0 else {5: 209, 2: 105}

func _refresh_outfit() -> void:
	var dto: Dictionary = _editor.get("_dto")
	dto["equipment_visuals"] = _loadout()
	var actor: ReplicatedActor3D = _editor.get("_actor")
	if is_instance_valid(actor):
		actor.apply_equipment_visuals(_loadout() if bool(_editor.get("_show_equipment")) else {})
		_play_pose()

func _play_pose(restart := true) -> void:
	var actor: ReplicatedActor3D = _editor.get("_actor")
	if not is_instance_valid(actor):
		return
	actor.play_action(POSES[_pose.selected], restart)
	actor.set_process(false)
	actor.set_physics_process(false)
	actor.animation_player.speed_scale = 1.0
	actor.call("_advance_facing_offset", 1.0)
	if _pause.button_pressed:
		actor.animation_player.pause()

func _front_view() -> void:
	_editor.set("_yaw", PI)
	_editor.call("_frame")

func _save_preview(_command: String) -> int:
	_looks[str(_current_sex)] = _editor.call("_values")
	var file := FileAccess.open(SAVE_PATH, FileAccess.WRITE)
	if file == null:
		_message.text = "The preview could not save your choices. They remain visible until you close it."
		return ERR_CANT_CREATE
	file.store_string(JSON.stringify(_looks, "\t"))
	_message.text = "Preview saved on this computer. Switch bodies or reopen the launcher to restore it."
	_set_saved_status.call_deferred()
	return OK

func _set_saved_status() -> void:
	(_editor.get("_status") as Label).text = "Saved for this offline preview."

func _fit() -> void:
	if not is_instance_valid(_editor) or not _editor.visible:
		return
	var top := maxf(128.0, _header_margin.get_global_rect().end.y + 12.0)
	_editor.size = Vector2(1160, 740).min(Vector2(root.size.x - 40, root.size.y - top - 20))
	_editor.position = Vector2((root.size.x - _editor.size.x) * 0.5, top)

func _capture() -> void:
	await RenderingServer.frame_post_draw
	var path := "user://human-workshop-%d.png" % Time.get_unix_time_from_system()
	var result := root.get_texture().get_image().save_png(path)
	_message.text = "Screenshot saved. Use Open saves to view it." if result == OK else "Screenshot could not be saved."

func _unhandled_input(event: InputEvent) -> void:
	if event.is_action_pressed("cancel"):
		quit()

func _expect(value: bool, label: String) -> void:
	if not value:
		_failures += 1
		push_error(label)

func _run_smoke() -> void:
	_expect(bool(root.get_node("Network").get("offline_hud_preview")), "network is blocked for this preview")
	for sex: int in [0, 1]:
		_select_sex(sex)
		_expect(ReplicatedActor3D.HIGH_PORTRAIT.cache_metrics().texture_bundles == 0, "Medium starts without High portrait textures")
		_expect(ReplicatedActor3D.HIGH_HAIR.cache_metrics().mesh_entries == 0, "Medium starts without High hair geometry")
		for outfit: int in range(5):
			_outfit.select(outfit)
			_refresh_outfit()
			(_editor.get("_form")).set_values({"jaw": 65, "nose": 40, "height": 100, "build": 0, "facial_hair": 4 if sex == 1 else 0, "hair_detail": 2})
			_editor.call("_refresh")
			var actor: ReplicatedActor3D = _editor.get("_actor")
			_expect(actor.get("_model_config").gender == ("female" if sex == 0 else "male"), "selected Human body matches")
			_expect(actor.get("_portrait_scale").is_equal_approx(Vector3(0.85, 1.1, 0.85)), "sliders affect the rendered body")
			for pose: int in POSES.size():
				_pose.select(pose)
				_play_pose()
				_expect(actor.animation_player.is_playing(), "selected pose plays")
			await process_frame
		_outfit.select(0)
		_refresh_outfit()
		_pose.select(1)
		_play_pose()
		_front_view()
		var actor: ReplicatedActor3D = _editor.get("_actor")
		var body := actor._native_model.find_child("body", true, false) as MeshInstance3D
		var medium_mesh := body.mesh
		var hair_sources: Array[Dictionary] = []
		for node: Node in actor._native_model.find_children("*", "MeshInstance3D", true, false):
			if node.get_parent() != null and str(node.get_parent().name).begins_with("AppearanceHair_"):
				var hair := node as MeshInstance3D
				var materials: Array[Material] = []
				for surface: int in hair.mesh.get_surface_count():
					materials.append(hair.get_surface_override_material(surface))
				hair_sources.append({"node": hair, "mesh": hair.mesh, "override": hair.material_override, "materials": materials})
		_editor.set_preview_quality(0)
		_expect(ReplicatedActor3D.HIGH_PORTRAIT.cache_metrics().texture_bundles == 0, "Low loads no High portrait textures")
		_expect(ReplicatedActor3D.HIGH_HAIR.cache_metrics().mesh_entries == 0, "Low loads no High hair geometry")
		_editor.set_preview_quality(2)
		_expect(ReplicatedActor3D.HIGH_PORTRAIT.cache_metrics().texture_bundles == 1, "High activates only the selected body's portrait artwork")
		_expect(body.mesh != medium_mesh, "High uses its anchored portrait UVs")
		_expect(ReplicatedActor3D.HIGH_HAIR.cache_metrics().mesh_entries > 0, "High refines visible Human hair")
		_editor.set_preview_quality(1)
		_expect(body.mesh == medium_mesh, "Medium restores the exact lightweight mesh")
		_expect(ReplicatedActor3D.HIGH_PORTRAIT.cache_metrics().texture_bundles == 0, "returning to Medium releases High resources")
		_expect(ReplicatedActor3D.HIGH_HAIR.cache_metrics().mesh_entries == 0, "returning to Medium releases High hair resources")
		for source: Dictionary in hair_sources:
			var hair: MeshInstance3D = source.node
			_expect(hair.mesh == source.mesh and hair.material_override == source.override, "Medium restores exact hair geometry and material")
			for surface: int in source.materials.size():
				_expect(hair.get_surface_override_material(surface) == source.materials[surface], "Medium restores each hair surface material")
		_expect(_save_preview("") == OK, "local preview saves")
		_expect(_json(SAVE_PATH).has(str(sex)), "saved Human body can be restored")
	await process_frame
	_fit()
	_expect(_editor.position.y >= 100 and _editor.get_global_rect().end.y <= root.size.y, "preview fits below toolbar")
	await RenderingServer.frame_post_draw
	root.get_texture().get_image().save_png("user://workshop-smoke.png")
	print("HUMAN_WORKSHOP_SMOKE: ", "PASS" if _failures == 0 else "FAIL %d" % _failures)
	_editor.call("_release_preview")
	_canvas.queue_free()
	await process_frame
	quit(0 if _failures == 0 else 1)
