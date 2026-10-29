extends PanelContainer
## Existing-player dressing room. Nothing changes in-world until the server
## accepts the explicit Apply command. Closing frees the preview actor.
## On a server that negotiated PC/3 (the version comes from the host through a
## callable, as `send` does) it offers the skin tone slider, the colour wheels,
## the hair finish slider and More face detail; otherwise develop's controls.

const FORM = preload("res://src/ui/portrait_customization_form.gd")
const CHOICES = preload("res://src/actors/appearance_choices.gd")
const CUSTOMIZATION = preload("res://src/actors/portrait_customization.gd")
const COLOURS = preload("res://src/actors/appearance_colours.gd")
const COLOUR_PANEL = preload("res://src/ui/appearance_colour_panel.gd")
var _form
var _colours
var _grid: GridContainer
var _version: Callable
var _closeup_before := false
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
## category -> {"saved": the save's byte its dropdown does not list,
## "shown": the listed entry shown for it}: the byte is kept unless the player
## picks another entry (a merged dye, e.g. Human pants 11, typed on develop).
var _unlisted: Dictionary = {}
var quality_level := -1

func set_preview_quality(level: int) -> void:
	quality_level = clampi(level, 0, 2)
	refresh_render_quality()

func refresh_render_quality() -> void:
	if is_instance_valid(_actor):
		_actor.apply_render_quality(quality_level if quality_level >= 0 else LookProfile.quality(), true)

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
	_grid = grid
	for category: String in ["skin", "hair", "hair_color", "eyes", "shirt", "pants", "boots"]:
		var label := Label.new()
		label.text = category.replace("_", " ").capitalize()
		grid.add_child(label)
		var picker := OptionButton.new()
		picker.size_flags_horizontal = Control.SIZE_EXPAND_FILL
		grid.add_child(picker)
		_pickers[category] = picker
		picker.item_selected.connect(func(_index: int) -> void: _refresh())
	_colours = COLOUR_PANEL.new()
	options.add_child(_colours)
	_colours.setup(_pickers, grid)
	_colours.changed.connect(_refresh)
	_colours.face_focus.connect(func(enabled: bool) -> void:
		# The eye wheel inspects the face; closing it restores the framing.
		if enabled:
			_closeup_before = _closeup
		_closeup = enabled or _closeup_before
		_frame())
	_form = FORM.new()
	options.add_child(_form)
	_form.changed.connect(_refresh)
	_form.preset_selected.connect(_apply_preset)
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

## `version` returns the negotiated appearance protocol (Network's
## appearance_protocol_version); without one the editor behaves as offline (1).
func open_for(dto: Dictionary, model: Dictionary, animations: Dictionary,
		equipment: Dictionary, send: Callable, version: Callable = Callable()) -> void:
	_dto = dto.duplicate(true)
	_model = model
	_animations = animations
	_equipment = equipment
	_send = send
	_version = version
	var appearance: Dictionary = _dto.get("appearance", {})
	var culture := AppearanceVariants.culture_for_actor_type(int(dto.get("actor_type", 0)))
	for category: String in _pickers:
		var part: int = {"shirt": 5, "pants": 4, "boots": 6}.get(category, 0)
		var choices := CHOICES.options("wardrobe" if int(part) > 0 else category, culture, part)
		if category == "skin" and culture == "luminous" and appearance.has("skin") and int(appearance.get("skin", -1)) == 0:
			# A Human save with Soft tan (skin 0, which the list does not offer
			# as a new pick) shows and keeps it.
			choices.insert(mini(1, choices.size()), CHOICES.soft_tan_option())
		CHOICES.populate(_pickers[category], choices)
	_set_palette(appearance)
	_form.set_values(appearance)
	_form.set_body(int(dto.get("actor_type", 0)))
	_form.set_hair_style(AppearanceVariants.hair_style(int(appearance.get("hair", 0))))
	_colours.set_body("female" if int(dto.get("actor_type", 0)) == 0 else "male", model)
	_colours.set_values(appearance)
	set_protocol_version(protocol_version())
	_status.text = "Drag the preview to rotate. Apply saves your choices for everyone to see."
	size = Vector2(780, 650).min(get_viewport_rect().size - Vector2(24, 24))
	position = (get_viewport_rect().size - size) * 0.5
	show()
	_refresh()
	_fit.call_deferred()

## The negotiated version; 1 (offline) without a version source.
func protocol_version() -> int:
	return int(_version.call()) if _version.is_valid() else 1

## PC/3 controls follow the negotiated version (and its changes while open).
func set_protocol_version(version: int) -> void:
	var enabled := version >= PortraitCustomization.LATEST and int(_dto.get("actor_type", -1)) in [0, 1]
	set_detail_enabled(enabled)
	_colours.set_custom_colours_enabled(enabled)

func set_detail_enabled(enabled: bool) -> void:
	_form.set_detail_enabled(enabled)

func _apply_preset(look: Dictionary) -> void:
	_set_palette(look)
	_colours.apply_preset(look.get("colours", {}) as Dictionary)

func _fit() -> void:
	if not is_visible_in_tree():
		return
	size = Vector2(780, 650).min(get_viewport_rect().size - Vector2(24, 24))
	position = (get_viewport_rect().size - size) * 0.5

func _set_palette(appearance: Dictionary) -> void:
	for category: String in _pickers:
		if not appearance.has(category) and category != "hair_color":
			continue
		_unlisted.erase(category)
		var value := int(appearance.get(category, 0))
		if category == "hair":
			value = AppearanceVariants.hair_style(int(appearance.get("hair", 0)))
		elif category == "hair_color":
			value = AppearanceVariants.hair_color_index(int(appearance.get("hair", 0)))
		var picker := _pickers[category] as OptionButton
		var index := picker.get_item_index(value)
		if index < 0 and category in ["shirt", "pants", "boots"]:
			index = _nearest_listed(picker, category, value)
			if index >= 0:
				_unlisted[category] = {"saved": value, "shown": picker.get_item_id(index)}
		if index >= 0:
			picker.select(index)

## The listed dye nearest (OKLab) to a byte the dropdown merged away.
func _nearest_listed(picker: OptionButton, category: String, value: int) -> int:
	var culture := AppearanceVariants.culture_for_actor_type(int(_dto.get("actor_type", 0)))
	var part: int = {"shirt": AppearanceVariants.PART_SHIRT, "pants": AppearanceVariants.PART_PANTS,
		"boots": AppearanceVariants.PART_BOOTS}[category]
	var target := COLOURS.oklab(AppearanceVariants.wardrobe_color(culture, part, value))
	var best := -1
	var distance := INF
	for row: int in picker.item_count:
		var d := target.distance_to(COLOURS.oklab(AppearanceVariants.wardrobe_color(culture, part, picker.get_item_id(row))))
		if d < distance:
			distance = d
			best = row
	return best

func _values() -> Dictionary:
	var result: Dictionary = _form.values()
	for category: String in ["skin", "eyes", "shirt", "pants", "boots"]:
		result[category] = (_pickers[category] as OptionButton).get_selected_id()
		var kept: Dictionary = _unlisted.get(category, {})
		if not kept.is_empty() and int(result[category]) == int(kept.shown):
			result[category] = int(kept.saved)
	result.hair = AppearanceVariants.pack_hair((_pickers.hair as OptionButton).get_selected_id(), (_pickers.hair_color as OptionButton).get_selected_id())
	# The colour panel adds the skin tone and colour fields in saved form.
	result = _colours.values(result)
	# A palette pick replaces a custom colour or slider position it opened with.
	return COLOURS.clear_replaced(_dto.get("appearance", {}) as Dictionary, result)

func _refresh() -> void:
	if not is_visible_in_tree():
		return
	var look := _values()
	_form.set_hair_style(AppearanceVariants.hair_style(int(look.get("hair", 0))))
	_form.update_derived(look)
	_colours.update_context(look, _model)
	if not is_instance_valid(_actor):
		_actor = ReplicatedActor3D.new()
		_stage.add_child(_actor)
		_actor.apply_render_quality(quality_level if quality_level >= 0 else LookProfile.quality(), true)
		var dto := _dto.duplicate(true)
		dto.x = 0
		dto.y = 0
		dto.rotation = 0
		dto.appearance = look
		dto.equipment_visuals = _dto.get("equipment_visuals", {}) if _show_equipment else {}
		dto.equipment_fallback_parts = []
		_actor.configure(dto, CoordinateAdapter.new({"walkingHeight": 0.0}), _model, _animations, _equipment)
		_actor.set_nameplate_visible(false)
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

## Sends the palette bytes and every field the negotiated version carries;
## a value the server cannot save is refused here, with the gate's message.
## Without a version source (the local preview lab) every field is sent, as
## before.
func _apply() -> void:
	var look := _values()
	var version := protocol_version() if _version.is_valid() else PortraitCustomization.LATEST
	var validation := PortraitCustomization.validate(look, version)
	var error: int = OK
	if not validation.ok:
		error = ERR_UNAVAILABLE if validation.error == "unsupported" else ERR_INVALID_DATA
	else:
		var entries := PackedStringArray()
		for field: String in look:
			var carried := PortraitCustomization.field_version(field)
			if carried == 0 or carried <= version:
				entries.append("%s=%d" % [field, look[field]])
		error = _send.call("#appearance " + " ".join(entries))
	if error == OK:
		_status.text = "Appearance requested. The server will confirm in chat."
	elif error == ERR_UNAVAILABLE:
		var reason := str(validation.get("message", "")) if not validation.ok else ""
		_status.text = (reason if not reason.is_empty() else "This server needs an update to save the new face, eye and hair controls.") \
			+ " Your preview is still available."
	else:
		_status.text = "Could not send. Reconnect and try again."

func _release_preview() -> void:
	if is_instance_valid(_actor):
		_actor.queue_free()
		_actor = null
	if is_instance_valid(_viewport):
		_viewport.render_target_update_mode = SubViewport.UPDATE_DISABLED

func _close() -> void:
	hide()
