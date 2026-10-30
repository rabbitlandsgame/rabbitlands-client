extends Node
## Stages starting looks without changing the editor until the player confirms.
const Library := preload("res://src/ui/creation_base_library.gd")
const Picker := preload("res://src/ui/creation_base_picker.gd")
const Art := preload("res://src/ui/leaderboard_art.gd")
var entry_opening := false
var _main: Control
var picker
var _button: Button
var _spacer: Control
var _rows: Array[Dictionary] = []
var _saved: Dictionary = {}
var _basis_id := ""
var _first_entry := false
var _registry: Dictionary = {}
var _heading: VBoxContainer


func configure(main: Control) -> void:
	_main = main
	_registry = {"models": main.get("models"), "actorTypes": main.get("actor_type_models"),
		"creationOptions": main.get("creation_options")}
	_button = Button.new()
	_button.name = "ChooseStartingLook"
	_button.text = "Choose starting look"
	_button.tooltip_text = "Browse editable starting looks for every race and sex"
	_button.accessibility_name = _button.text
	_button.custom_minimum_size.y = 38
	var form := main.get_node("CreationPanel/Columns/FormPanel/Form")
	form.add_child(_button)
	form.move_child(_button, 0)
	_button.pressed.connect(open.bind(false))
	_main.resized.connect(_update_layout)


func is_open() -> bool:
	return not _saved.is_empty()


func forget_basis() -> void:
	_basis_id = ""


func open(first_entry: bool = false) -> void:
	if is_open() or not _main.get_node("%CreationPanel").is_visible_in_tree():
		return
	if not is_instance_valid(picker):
		picker = Picker.new()
		picker.name = "CreationBasePicker"
		_main.add_child(picker)
		picker.set_anchors_and_offsets_preset(Control.PRESET_FULL_RECT)
		picker.basis_selected.connect(_use_basis)
		picker.dismissed.connect(_cancel)
		picker.preview_requested.connect(_preview)
	_rows = Library.rows(_registry, _protocol())
	_first_entry = first_entry
	var preview := _main.get_node("%CharacterPreview") as Control
	_saved = {"rail": _main.get_node("%ClassRail").visible,
		"form": _main.get_node("%FormPanel").visible,
		"preview_visible": preview.visible, "minimum": preview.custom_minimum_size,
		"flags": preview.size_flags_horizontal, "z_index": preview.z_index,
		"mouse_filter": preview.mouse_filter, "distance": _main.get("preview_distance"),
		"yaw": _main.get("preview_yaw"), "pitch": _main.get("preview_pitch"),
		"face": _main.get("creation_face_focus")}
	_saved["stage_visibility"] = {}
	for path: String in ["PreviewGround", "OldcraftStage"]:
		var stage := _main.get_node("%PreviewRoot").get_node_or_null(path) as Node3D
		if stage != null:
			_saved.stage_visibility[stage] = stage.visible
			stage.hide()
	_main.get_node("%ClassRail").hide()
	_main.get_node("%FormPanel").hide()
	preview.z_index = 200
	preview.mouse_filter = Control.MOUSE_FILTER_IGNORE
	if not is_instance_valid(_spacer):
		_spacer = Control.new()
		_spacer.name = "StartingLookSpace"
		_spacer.mouse_filter = Control.MOUSE_FILTER_IGNORE
		_spacer.size_flags_horizontal = Control.SIZE_EXPAND_FILL
		_main.get_node("CreationPanel/Columns").add_child(_spacer)
	_spacer.show()
	_main.set("preview_yaw", PI + 0.12)
	_main.set("preview_pitch", 0.04)
	_main.set("creation_face_focus", false)
	picker.setup(_rows, _current_basis(), {"registry": _registry,
		"equipment": _main.get("equipment_config")})
	picker.open()
	_ensure_heading()
	_heading.move_to_front()
	_update_layout()
	if not picker.selected_id().is_empty():
		_preview(picker.selected_id())


func close_for_exit() -> void:
	if is_instance_valid(picker):
		picker.close()
	_restore_layout()
	entry_opening = false


func refresh_protocol() -> void:
	if not is_open():
		return
	var id: String = picker.selected_id()
	_rows = Library.rows(_registry, _protocol())
	picker.setup(_rows, id, {"registry": _registry,
		"equipment": _main.get("equipment_config")})
	_preview(id)


func _protocol() -> int:
	return int(get_node("/root/Network").appearance_protocol_version())


func _current_basis() -> String:
	for row: Dictionary in _rows:
		if str(row.id) == _basis_id:
			return _basis_id
	var actor_type: int = (_main.get_node("%CreateGender") as OptionButton).get_selected_id()
	for row: Dictionary in _rows:
		if int(row.look.actor_type) == actor_type:
			return str(row.id)
	return str(_rows[0].id) if not _rows.is_empty() else ""


func _find(id: String) -> Dictionary:
	for row: Dictionary in _rows:
		if str(row.id) == id:
			return row
	return {}


func _preview(id: String) -> void:
	var row := _find(id)
	if is_open() and not row.is_empty():
		_main.call("_refresh_creation_preview", row.look)


func _use_basis(id: String) -> void:
	# Resolve against the current negotiated protocol, including a reconnect.
	_rows = Library.rows(_registry, _protocol())
	var row := _find(id)
	if row.is_empty():
		_cancel()
		return
	var actor_type := int(row.look.actor_type)
	var race := _main.get_node("%CreateRace") as OptionButton
	var sex := _main.get_node("%CreateGender") as OptionButton
	for index: int in race.item_count:
		if str(race.get_item_metadata(index)) == str(row.race_id):
			race.select(index)
			break
	_main.call("_populate_creation_sexes")
	sex.select(sex.get_item_index(actor_type))
	_main.call("_populate_creation_choices", true)
	var appearance: Dictionary = row.look.appearance
	var values := {"CreateSkin": int(appearance.get("skin", 0)),
		"CreateHair": AppearanceVariants.hair_style(int(appearance.get("hair", 0))),
		"CreateHairColor": AppearanceVariants.hair_color_index(int(appearance.get("hair", 0))),
		"CreateEyes": int(appearance.get("eyes", 0)),
		"CreateShirt": int(appearance.get("shirt", 0)),
		"CreatePants": int(appearance.get("pants", 0)),
		"CreateBoots": int(appearance.get("boots", 0))}
	for name: String in values:
		var option := _main.get_node("%" + name) as OptionButton
		var index := option.get_item_index(int(values[name]))
		if index >= 0:
			option.select(index)
	if actor_type in [0, 1]:
		_main.get("portrait_form").set_values(appearance)
		_main.get("creation_colours").set_values(appearance)
	_basis_id = id
	_restore_layout()
	_main.call("_refresh_creation_preview", {}, true)
	_button.grab_focus.call_deferred()


func _cancel() -> void:
	var return_to_login := _first_entry
	_restore_layout()
	if return_to_login:
		_main.call("_on_creation_back_pressed")
	else:
		_main.call("_refresh_creation_preview", {}, true)
		_button.grab_focus.call_deferred()


func _update_layout() -> void:
	if not is_open():
		return
	var width := _main.size.x
	var preview := _main.get_node("%CharacterPreview") as Control
	preview.visible = width >= 1100
	preview.custom_minimum_size = Vector2(clampf(width * 0.29, 280, 560), 0)
	preview.size_flags_horizontal = Control.SIZE_FILL
	if is_instance_valid(_heading):
		_heading.visible = width >= 1100
	_main.call("_frame_preview_actor")


func _ensure_heading() -> void:
	if is_instance_valid(_heading):
		return
	_heading = VBoxContainer.new()
	_heading.z_index = 201
	_heading.position = Vector2(28, 18)
	_heading.mouse_filter = Control.MOUSE_FILTER_IGNORE
	_main.add_child(_heading)
	var logo := TextureRect.new()
	logo.texture = load("res://assets/branding/rabbitlands-logo.png")
	logo.expand_mode = TextureRect.EXPAND_IGNORE_SIZE
	logo.stretch_mode = TextureRect.STRETCH_KEEP_ASPECT_CENTERED
	logo.custom_minimum_size = Vector2(270, 76)
	logo.mouse_filter = Control.MOUSE_FILTER_IGNORE
	_heading.add_child(logo)
	var title := Label.new()
	title.text = "Create character"
	title.horizontal_alignment = HORIZONTAL_ALIGNMENT_CENTER
	title.add_theme_font_override("font", Art.title_font())
	title.add_theme_font_size_override("font_size", 22)
	title.add_theme_color_override("font_color", Color("f0e8d8"))
	title.mouse_filter = Control.MOUSE_FILTER_IGNORE
	_heading.add_child(title)


func _restore_layout() -> void:
	if _saved.is_empty():
		return
	_main.get_node("%ClassRail").visible = bool(_saved.rail)
	_main.get_node("%FormPanel").visible = bool(_saved.form)
	var preview := _main.get_node("%CharacterPreview") as Control
	preview.visible = bool(_saved.preview_visible)
	preview.custom_minimum_size = _saved.minimum
	preview.size_flags_horizontal = int(_saved.flags)
	preview.z_index = int(_saved.z_index)
	preview.mouse_filter = int(_saved.mouse_filter)
	for pair: Array in [["preview_distance", "distance"], ["preview_yaw", "yaw"],
			["preview_pitch", "pitch"], ["creation_face_focus", "face"]]:
		_main.set(pair[0], _saved[pair[1]])
	if is_instance_valid(_spacer):
		_spacer.hide()
	if is_instance_valid(_heading):
		_heading.hide()
	for node: Node3D in _saved.get("stage_visibility", {}):
		if is_instance_valid(node):
			node.visible = bool(_saved.stage_visibility[node])
	_saved.clear()
	_first_entry = false
