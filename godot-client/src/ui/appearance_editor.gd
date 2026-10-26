extends PanelContainer
## Existing-player dressing room. Nothing changes in-world until the server
## accepts the explicit Apply command. Closing frees the preview actor.

const FORM = preload("res://src/ui/portrait_customization_form.gd")
const CHOICES = preload("res://src/actors/appearance_choices.gd")
const CUSTOMIZATION = preload("res://src/actors/portrait_customization.gd")
var _form
var _pickers: Dictionary = {}
var _viewport: SubViewport
var _stage: Node3D
var _camera: Camera3D
var _actor: ReplicatedActor3D
var _dto: Dictionary
var _model: Dictionary
var _animations: Dictionary
var _equipment: Dictionary
var _send: Callable
var _status: Label
var _yaw := PI + 0.2
var _closeup := false
var _show_equipment := false

func _ready() -> void:
	name = "AppearanceEditor"
	set_anchors_and_offsets_preset(Control.PRESET_CENTER)
	z_index = 50
	var content := VBoxContainer.new()
	add_child(content)
	var header := HBoxContainer.new()
	content.add_child(header)
	var title := Label.new()
	title.text = "Character appearance"
	title.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	header.add_child(title)
	var close := Button.new()
	close.text = "Close"
	header.add_child(close)
	close.pressed.connect(_close)
	var columns := HBoxContainer.new()
	columns.size_flags_vertical = Control.SIZE_EXPAND_FILL
	content.add_child(columns)
	var preview := SubViewportContainer.new()
	preview.custom_minimum_size = Vector2(300, 440)
	preview.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	preview.stretch = true
	columns.add_child(preview)
	_viewport = SubViewport.new()
	_viewport.size = Vector2i(360, 540)
	_viewport.own_world_3d = true
	_viewport.render_target_update_mode = SubViewport.UPDATE_DISABLED
	preview.add_child(_viewport)
	_stage = Node3D.new()
	_viewport.add_child(_stage)
	_camera = Camera3D.new()
	_camera.cull_mask = 3
	_camera.fov = 35.0
	_camera.current = true
	_stage.add_child(_camera)
	var environment := WorldEnvironment.new()
	environment.environment = Environment.new()
	environment.environment.background_mode = Environment.BG_COLOR
	environment.environment.background_color = Color(0.035, 0.045, 0.055)
	environment.environment.ambient_light_source = Environment.AMBIENT_SOURCE_COLOR
	environment.environment.ambient_light_color = Color(0.62, 0.68, 0.78)
	environment.environment.ambient_light_energy = 0.7
	_stage.add_child(environment)
	for angle: float in [-0.6, 2.2]:
		var light := DirectionalLight3D.new()
		light.rotation = Vector3(-0.5, angle, 0)
		light.light_color = Color(1.0, 0.83, 0.66) if angle < 0 else Color(0.6, 0.8, 1.0)
		light.light_energy = 1.2 if angle < 0 else 0.6
		_stage.add_child(light)
	preview.gui_input.connect(func(event: InputEvent) -> void:
		if event is InputEventMouseMotion and (event.button_mask & MOUSE_BUTTON_MASK_LEFT) != 0:
			_yaw -= event.relative.x * 0.01
			_frame())
	var scroll := ScrollContainer.new()
	scroll.horizontal_scroll_mode = ScrollContainer.SCROLL_MODE_DISABLED
	scroll.custom_minimum_size.x = 390
	scroll.size_flags_vertical = Control.SIZE_EXPAND_FILL
	columns.add_child(scroll)
	var options := VBoxContainer.new()
	options.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	scroll.add_child(options)
	var grid := GridContainer.new()
	grid.columns = 2
	options.add_child(grid)
	for category: String in ["skin", "hair", "hair_color", "eyes", "shirt", "pants", "boots"]:
		var label := Label.new()
		label.text = category.replace("_", " ").capitalize()
		grid.add_child(label)
		var picker := OptionButton.new()
		picker.size_flags_horizontal = Control.SIZE_EXPAND_FILL
		grid.add_child(picker)
		_pickers[category] = picker
		picker.item_selected.connect(func(_index: int) -> void: _refresh())
	_form = FORM.new()
	options.add_child(_form)
	_form.changed.connect(_refresh)
	_form.preset_selected.connect(_set_palette)
	var actions := HBoxContainer.new()
	content.add_child(actions)
	var gear := CheckBox.new()
	gear.text = "Show equipment"
	actions.add_child(gear)
	gear.toggled.connect(func(enabled: bool) -> void:
		_show_equipment = enabled
		if is_instance_valid(_actor):
			_actor.apply_equipment_visuals(_dto.get("equipment_visuals", {}) if enabled else {}))
	var zoom := Button.new()
	zoom.text = "Face / full body"
	actions.add_child(zoom)
	zoom.pressed.connect(func() -> void:
		_closeup = not _closeup
		_frame())
	var apply := Button.new()
	apply.text = "Apply appearance"
	actions.add_child(apply)
	apply.pressed.connect(_apply)
	_status = Label.new()
	_status.custom_minimum_size.x = 400
	_status.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
	content.add_child(_status)
	visibility_changed.connect(func() -> void:
		if not is_visible_in_tree():
			_release_preview())
	hide()

func open_for(dto: Dictionary, model: Dictionary, animations: Dictionary,
		equipment: Dictionary, send: Callable) -> void:
	_dto = dto.duplicate(true)
	_model = model
	_animations = animations
	_equipment = equipment
	_send = send
	var appearance: Dictionary = _dto.get("appearance", {})
	var culture := AppearanceVariants.culture_for_actor_type(int(dto.get("actor_type", 0)))
	for category: String in _pickers:
		var part: int = {"shirt": 5, "pants": 4, "boots": 6}.get(category, 0)
		CHOICES.populate(_pickers[category], CHOICES.options("wardrobe" if int(part) > 0 else category, culture, part))
	_set_palette(appearance)
	_form.set_values(appearance)
	_status.text = "Drag the preview to rotate. Apply saves your choices for everyone to see."
	size = Vector2(780, 650).min(get_viewport_rect().size - Vector2(24, 24))
	position = (get_viewport_rect().size - size) * 0.5
	show()
	_refresh()
	_fit.call_deferred()

func _fit() -> void:
	if not is_visible_in_tree():
		return
	size = Vector2(780, 650).min(get_viewport_rect().size - Vector2(24, 24))
	position = (get_viewport_rect().size - size) * 0.5

func _set_palette(appearance: Dictionary) -> void:
	for category: String in _pickers:
		if not appearance.has(category) and category != "hair_color":
			continue
		var value := int(appearance.get(category, 0))
		if category == "hair":
			value = AppearanceVariants.hair_style(int(appearance.get("hair", 0)))
		elif category == "hair_color":
			value = AppearanceVariants.hair_color_index(int(appearance.get("hair", 0)))
		var picker := _pickers[category] as OptionButton
		var index := picker.get_item_index(value)
		if index >= 0:
			picker.select(index)

func _values() -> Dictionary:
	var result: Dictionary = _form.values()
	for category: String in ["skin", "eyes", "shirt", "pants", "boots"]:
		result[category] = (_pickers[category] as OptionButton).get_selected_id()
	result.hair = AppearanceVariants.pack_hair((_pickers.hair as OptionButton).get_selected_id(), (_pickers.hair_color as OptionButton).get_selected_id())
	return result

func _refresh() -> void:
	if not is_visible_in_tree():
		return
	var look := _values()
	if not is_instance_valid(_actor):
		_actor = ReplicatedActor3D.new()
		_stage.add_child(_actor)
		var dto := _dto.duplicate(true)
		dto.x = 0
		dto.y = 0
		dto.rotation = 0
		dto.appearance = look
		dto.equipment_visuals = _dto.get("equipment_visuals", {}) if _show_equipment else {}
		dto.equipment_fallback_parts = []
		_actor.configure(dto, CoordinateAdapter.new({"walkingHeight": 0.0}), _model, _animations, _equipment)
		_actor.set_nameplate_visible(false)
		_actor.apply_render_quality(LookProfile.quality(), true)
	else:
		_actor.apply_appearance_variants(look)
	_viewport.render_target_update_mode = SubViewport.UPDATE_ALWAYS
	_frame()

func _frame() -> void:
	if not is_instance_valid(_actor):
		return
	var rise := _actor.head_height()
	var focus := _actor.position + Vector3(0, rise * (0.86 if _closeup else 0.48), 0)
	var distance := rise * (0.7 if _closeup else 1.9)
	_camera.position = focus + Vector3(sin(_yaw), 0.08, cos(_yaw)) * distance
	_camera.look_at(focus)

func _apply() -> void:
	var look := _values()
	var entries := PackedStringArray()
	for field: String in look:
		entries.append("%s=%d" % [field, look[field]])
	var error: int = _send.call("#appearance " + " ".join(entries))
	_status.text = "Appearance requested. The server will confirm in chat." if error == OK else "Could not send. Reconnect and try again."

func _release_preview() -> void:
	if is_instance_valid(_actor):
		_actor.queue_free()
		_actor = null
	if is_instance_valid(_viewport):
		_viewport.render_target_update_mode = SubViewport.UPDATE_DISABLED

func _close() -> void:
	hide()
