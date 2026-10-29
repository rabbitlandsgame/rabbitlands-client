class_name SkinToneSlider
extends VBoxContainer
## The natural skin tone slider, its undertone slider and the four Eloria
## tones (colour model spec 2.1, 2.2 and 6.1). Positions 1..201 run through
## the six natural palette tones; the undertone 1..201 moves the tone towards
## Pink, Rosy, Golden or Olive (101 is the tone as designed, saved as 0).
## The widget holds what the player chose; AppearanceColours.canonical()
## turns it into the saved form (a stop with no undertone is the palette byte).

signal changed

const COLOURS := preload("res://src/actors/appearance_colours.gd")
const KIT := preload("res://src/ui/appearance_ui_kit.gd")
## The natural tones in slider order (AppearanceColours.SKIN_STOP_INDEX).
const STOP_NAMES: Array[String] = ["Pale beige", "Soft tan", "Golden tan", "Warm brown", "Deep brown", "Ebony brown"]
const ELORIA := {6: "Frost blue", 7: "Moss green", 8: "Dusk violet", 9: "Stone grey"}
const LANDMARKS: Array = [[1, "Pink"], [51, "Rosy"], [101, "Neutral"], [151, "Golden"], [201, "Olive"]]
const NEUTRAL := 101
## The undertone's centre detent: positions within 3 of Neutral snap to it.
const DETENT := 3

var tone_slider: HSlider
var undertone_slider: HSlider
var tone_readout: Label
var undertone_readout: Label
var limit_notice: HBoxContainer
var eloria_buttons: Dictionary = {}
var tone_previous: Button
var tone_next: Button
var undertone_previous: Button
var undertone_next: Button
var _eloria := -1
var _sex := "male"
var _model_config: Dictionary = {}
var _last_undertone := NEUTRAL
var _quiet := false


func _init() -> void:
	name = "SkinToneSlider"
	size_flags_horizontal = Control.SIZE_EXPAND_FILL
	add_theme_constant_override("separation", 3)
	var header := HBoxContainer.new()
	add_child(header)
	var title := Label.new()
	title.text = "Skin tone"
	header.add_child(title)
	tone_readout = _readout_label("ToneReadout")
	header.add_child(tone_readout)
	var tone_row := HBoxContainer.new()
	add_child(tone_row)
	tone_previous = _step_button("‹", "Previous named skin tone")
	tone_row.add_child(tone_previous)
	tone_slider = _slider("SkinTone", "Skin tone")
	tone_row.add_child(tone_slider)
	tone_next = _step_button("›", "Next named skin tone")
	tone_row.add_child(tone_next)
	var tone_ticks: Array = []
	for stop: int in COLOURS.SKIN_STOP_POSITION.size():
		tone_ticks.append([COLOURS.SKIN_STOP_POSITION[stop], ""])
	add_child(_tick_row(tone_slider, tone_ticks))
	var under_header := HBoxContainer.new()
	add_child(under_header)
	var under_title := Label.new()
	under_title.text = "Undertone"
	under_header.add_child(under_title)
	undertone_readout = _readout_label("UndertoneReadout")
	under_header.add_child(undertone_readout)
	var under_row := HBoxContainer.new()
	add_child(under_row)
	undertone_previous = _step_button("‹", "Previous undertone landmark")
	under_row.add_child(undertone_previous)
	undertone_slider = _slider("SkinUndertone", "Skin undertone")
	undertone_slider.value = NEUTRAL
	undertone_slider.tooltip_text = "Pink, Rosy, Neutral, Golden or Olive. The centre keeps the tone as designed."
	under_row.add_child(undertone_slider)
	undertone_next = _step_button("›", "Next undertone landmark")
	under_row.add_child(undertone_next)
	add_child(_tick_row(undertone_slider, LANDMARKS))
	limit_notice = KIT.notice("Limited to natural skin colours", "", "UndertoneLimit")
	add_child(limit_notice)
	var eloria_row := HBoxContainer.new()
	eloria_row.name = "EloriaTones"
	add_child(eloria_row)
	var eloria_title := Label.new()
	eloria_title.text = "Eloria tones"
	eloria_row.add_child(eloria_title)
	var group := ButtonGroup.new()
	group.allow_unpress = true
	for id: int in ELORIA:
		var button := Button.new()
		button.name = "Eloria%d" % id
		button.toggle_mode = true
		button.button_group = group
		button.icon = KIT.swatch_icon(AppearanceVariants.skin_color(id), 18)
		button.custom_minimum_size = Vector2(32, 28)
		button.tooltip_text = str(ELORIA[id])
		button.accessibility_name = "Eloria tone: " + str(ELORIA[id])
		eloria_row.add_child(button)
		eloria_buttons[id] = button
		button.toggled.connect(func(pressed: bool) -> void:
			if _quiet:
				return
			if pressed:
				_eloria = id
			elif _eloria == id:
				_eloria = -1
			_sync()
			changed.emit())
	tone_slider.value_changed.connect(func(_value: float) -> void:
		if _quiet:
			return
		if _eloria >= 0:
			# Moving the natural slider leaves the Eloria tone.
			_set_eloria(-1)
		_sync()
		changed.emit())
	undertone_slider.value_changed.connect(_on_undertone)
	tone_previous.pressed.connect(func() -> void: step_tone(-1))
	tone_next.pressed.connect(func() -> void: step_tone(1))
	undertone_previous.pressed.connect(func() -> void: step_undertone(-1))
	undertone_next.pressed.connect(func() -> void: step_undertone(1))
	_quiet = true
	tone_slider.value = COLOURS.SKIN_STOP_POSITION[0]
	_quiet = false
	_rebuild_tracks()
	_sync()


## A readout that wraps rather than widening a narrow column.
func _readout_label(node_name: String) -> Label:
	var label := Label.new()
	label.name = node_name
	label.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	label.horizontal_alignment = HORIZONTAL_ALIGNMENT_RIGHT
	label.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
	label.custom_minimum_size.x = 120
	return label


func _slider(node_name: String, accessible: String) -> HSlider:
	var slider := HSlider.new()
	slider.name = node_name
	slider.min_value = 1
	slider.max_value = 201
	slider.step = 1
	slider.custom_minimum_size = Vector2(150, 24)
	slider.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	slider.focus_mode = Control.FOCUS_ALL
	slider.accessibility_name = accessible
	KIT.page_keys(slider, 10)
	return slider


func _step_button(text: String, accessible: String) -> Button:
	var button := Button.new()
	button.text = text
	button.custom_minimum_size = Vector2(KIT.TARGET, KIT.TARGET)
	button.tooltip_text = accessible
	button.accessibility_name = accessible
	return button


func _tick_row(slider: HSlider, ticks: Array) -> Control:
	# Ticks sit under the slider only, between the two step buttons.
	var row := HBoxContainer.new()
	var left := Control.new()
	left.custom_minimum_size.x = KIT.TARGET
	row.add_child(left)
	var strip := KIT.TickStrip.new(slider, ticks)
	row.add_child(strip)
	var right := Control.new()
	right.custom_minimum_size.x = KIT.TARGET
	row.add_child(right)
	return row


func _on_undertone(value: float) -> void:
	if _quiet:
		return
	var position := roundi(value)
	if position != NEUTRAL and absi(position - NEUTRAL) <= DETENT:
		# Leaving the detent jumps past it; arriving inside it snaps to Neutral.
		position = NEUTRAL + (DETENT + 1) * signi(position - NEUTRAL) if _last_undertone == NEUTRAL else NEUTRAL
		_quiet = true
		undertone_slider.value = position
		_quiet = false
	_last_undertone = position
	_sync()
	changed.emit()


## The body's sex ("female" / "male") and model: the Soft tan stop and the
## gradients follow the body's reference skin.
func set_body(sex: String, model_config: Dictionary = {}) -> void:
	_sex = "male" if sex == "male" else "female"
	_model_config = model_config
	_rebuild_tracks()
	_sync()


## Shows a saved choice without emitting `changed`: an Eloria tone (skin 6..9),
## or a natural tone at `tone` (0 = the stop of a natural `skin` 0..5) with
## `undertone` (0 = neutral).
func set_from(skin: int, tone: int, undertone: int) -> void:
	_quiet = true
	if skin >= 6 and skin <= 9:
		_set_eloria(skin)
	else:
		_set_eloria(-1)
		var position := tone if tone >= 1 else COLOURS.skin_position(skin)
		tone_slider.value = clampi(position if position >= 1 else COLOURS.SKIN_STOP_POSITION[0], 1, 201)
		undertone_slider.value = clampi(undertone, 1, 201) if undertone >= 1 else NEUTRAL
		_last_undertone = roundi(undertone_slider.value)
	_quiet = false
	_rebuild_tracks()
	_sync()


func _set_eloria(id: int) -> void:
	var was_quiet := _quiet
	_quiet = true
	_eloria = id
	for key: int in eloria_buttons:
		(eloria_buttons[key] as Button).set_pressed_no_signal(key == id)
	_quiet = was_quiet


## The choice: {"skin", "skin_tone", "skin_undertone"} - an Eloria tone with
## the other two 0, or the nearest natural index with the slider position and
## the undertone (0 at Neutral).
func values() -> Dictionary:
	if _eloria >= 6:
		return {"skin": _eloria, "skin_tone": 0, "skin_undertone": 0}
	var position := tone()
	return {"skin": COLOURS.nearest_skin_index(position), "skin_tone": position,
		"skin_undertone": undertone()}


func tone() -> int:
	return roundi(tone_slider.value)


func undertone() -> int:
	var value := roundi(undertone_slider.value)
	return 0 if value == NEUTRAL else value


func eloria() -> int:
	return _eloria


## True when the undertone's limits (hue window, chroma cap) change the colour.
func limited() -> bool:
	if _eloria >= 0 or undertone() == 0:
		return false
	return bool(COLOURS.skin_lab(tone(), COLOURS.undertone_t(undertone()), _sex, _model_config).limited)


## The skin colour the choice shows (sRGB).
func colour() -> Color:
	if _eloria >= 0:
		return AppearanceVariants.skin_color(_eloria)
	return COLOURS.from_oklab(COLOURS.skin_lab(tone(), COLOURS.undertone_t(undertone()), _sex, _model_config).lab)


## ‹ › on the tone: the previous or next named tone.
func step_tone(direction: int) -> void:
	var position := tone()
	var target := position
	if direction < 0:
		for stop: int in range(COLOURS.SKIN_STOP_POSITION.size() - 1, -1, -1):
			if COLOURS.SKIN_STOP_POSITION[stop] < position:
				target = COLOURS.SKIN_STOP_POSITION[stop]
				break
	else:
		for stop: int in COLOURS.SKIN_STOP_POSITION.size():
			if COLOURS.SKIN_STOP_POSITION[stop] > position:
				target = COLOURS.SKIN_STOP_POSITION[stop]
				break
	if _eloria >= 0:
		_set_eloria(-1)
		target = position
	_quiet = true
	tone_slider.value = target
	_quiet = false
	_sync()
	changed.emit()


## ‹ › on the undertone: the previous or next landmark.
func step_undertone(direction: int) -> void:
	if _eloria >= 0:
		return
	var position := roundi(undertone_slider.value)
	var target := position
	var order := range(LANDMARKS.size()) if direction > 0 else range(LANDMARKS.size() - 1, -1, -1)
	for index: int in order:
		var mark := int(LANDMARKS[index][0])
		if (direction > 0 and mark > position) or (direction < 0 and mark < position):
			target = mark
			break
	_quiet = true
	undertone_slider.value = target
	_quiet = false
	_last_undertone = target
	_sync()
	changed.emit()


func tone_name() -> String:
	if _eloria >= 0:
		return "Eloria tone: " + str(ELORIA[_eloria])
	var position := tone()
	for stop: int in COLOURS.SKIN_STOP_POSITION.size():
		if position == COLOURS.SKIN_STOP_POSITION[stop]:
			return STOP_NAMES[stop]
	for stop: int in COLOURS.SKIN_STOP_POSITION.size() - 1:
		if position < COLOURS.SKIN_STOP_POSITION[stop + 1]:
			return "Between %s and %s" % [STOP_NAMES[stop], STOP_NAMES[stop + 1]]
	return STOP_NAMES[-1]


func undertone_name() -> String:
	if _eloria >= 0:
		return "Not used with Eloria tones"
	var position := roundi(undertone_slider.value)
	var best := 0
	for index: int in LANDMARKS.size():
		if absi(position - int(LANDMARKS[index][0])) < absi(position - int(LANDMARKS[best][0])):
			best = index
	var landmark := str(LANDMARKS[best][1])
	if position == int(LANDMARKS[best][0]):
		return landmark
	return "Near %s" % landmark


func _sync() -> void:
	tone_readout.text = tone_name()
	undertone_readout.text = undertone_name()
	tone_slider.accessibility_description = tone_readout.text
	undertone_slider.accessibility_description = undertone_readout.text
	var natural := _eloria < 0
	undertone_slider.editable = natural
	undertone_previous.disabled = not natural
	undertone_next.disabled = not natural
	undertone_slider.modulate.a = 1.0 if natural else 0.45
	limit_notice.visible = limited()
	_rebuild_undertone_track()


func _rebuild_tracks() -> void:
	var colours := PackedColorArray()
	for sample: int in 41:
		var position := 1.0 + 200.0 * float(sample) / 40.0
		colours.append(COLOURS.from_oklab(COLOURS.skin_path(position, _sex, _model_config)))
	KIT.gradient_track(tone_slider, colours)
	_rebuild_undertone_track()


func _rebuild_undertone_track() -> void:
	var colours := PackedColorArray()
	var position := float(tone())
	for sample: int in 21:
		var t := -1.0 + 2.0 * float(sample) / 20.0
		colours.append(COLOURS.from_oklab(COLOURS.skin_lab(position, t, _sex, _model_config).lab))
	KIT.gradient_track(undertone_slider, colours)
