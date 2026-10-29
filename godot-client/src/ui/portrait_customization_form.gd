extends VBoxContainer
## The same controls drive creation and the existing-player dressing room.
##
## On a server that negotiated PC/3 (set_detail_enabled) the hair finish is a
## Sleek ↔ Messy slider and the More face detail section offers the High head's
## extra shape sliders and painted details (PC/3 spec 8, colour model spec
## 6.1). Otherwise - offline, older servers - the controls are develop's,
## and values held from a PC/3 save are kept, shown with a notice and refused
## by the version gate rather than dropped.

signal changed
signal preset_selected(appearance: Dictionary)
const CUSTOMIZATION = preload("res://src/actors/portrait_customization.gd")
const PRESETS = preload("res://src/actors/human_portrait_presets.gd")
const HAIR_FINISH = preload("res://src/actors/hair_finish.gd")
const CHOICES = preload("res://src/actors/appearance_choices.gd")
const KIT = preload("res://src/ui/appearance_ui_kit.gd")
## Names at the saved finishes' slider positions (Swept 25, Classic 50, Tousled 75).
const FINISH_TICKS: Array = [[25, "Swept"], [50, "Classic"], [75, "Tousled"]]
## A slider position within this of a tick snaps to it (and saves the enum).
const FINISH_SNAP := 2
const FINISH_TOOLTIP := "How sleek or loose your hair looks at every graphics level; High also shows fine flyaways."
## The More face detail section (PC/3 spec 8.3): [group, [[field, label, low, high]]].
const DETAIL_GROUPS: Array = [
	["Eyes", [["eyelid", "Eyelids", "Hooded", "Open"]]],
	["Brows", [["brow_height", "Brow height", "Lower", "Higher"],
		["brow_style", "Brow shape", "Arched", "Angled"],
		["brow_thickness", "Brow thickness", "Thin", "Thick"]]],
	["Nose", [["nose_length", "Nose length", "Shorter", "Longer"],
		["nose_bridge", "Nose bridge", "Scooped", "Humped"],
		["nose_tip", "Nose tip", "Lowered", "Upturned"]]],
	["Lips", [["mouth_width", "Mouth width", "Narrow", "Wide"],
		["cupid_bow", "Cupid's bow", "Flat", "Defined"],
		["lip_tint", "Lip colour", "", ""]]],
	["Cheeks", [["cheek_fullness", "Cheek fullness", "Hollow", "Full"]]],
	["Jaw & chin", [["chin_projection", "Chin projection", "Receding", "Forward"],
		["chin_width", "Chin width", "Narrow", "Broad"]]],
	["Ears", [["ear_size", "Ear size", "Smaller", "Larger"]]],
	["Skin details", [["freckles", "Freckles", "None", "Many"],
		["liner", "Eyeliner", "None", "Bold"],
		["liner_wing", "Liner wing", "None", "Long"],
		["stubble", "Stubble shadow (male only)", "None", "Dense"]]],
	["Hair", [["hair_module", "High-detail hair", "", ""]]],
]
## Detail fields with an Auto box (0 = Auto, then an explicit 1..maximum).
const AUTO_FIELDS: Array[String] = ["brow_style", "brow_thickness", "freckles", "liner", "liner_wing", "stubble"]
const BROW_NAMES: Array[String] = ["Arched", "Straight", "Soft", "Angled"]
const MODULE_NAMES := {"rowan_shag": "Rowan shag", "mira_bun": "Mira bun"}
var controls: Dictionary = {}
## Saved fields this form has no control for (the colour fields, which the
## hosts' colour panel owns): kept as opened and returned by values(), so an
## Apply or a preset never drops them (pc3 spec 8.2).
var _carried: Dictionary = {}
var _timer: Timer
## The PC/3 widgets: field -> HSlider, or for an Auto field
## {"auto": CheckBox, "slider": HSlider, "readout": Label}, or an OptionButton.
var detail_controls: Dictionary = {}
var finish_slider: HSlider
var finish_readout: Label
var finish_previous: Button
var finish_next: Button
var finish_row: VBoxContainer
var finish_notice: HBoxContainer
var detail_toggle: Button
var detail_box: VBoxContainer
var detail_notice: HBoxContainer
var module_hint: Label
var _finish_s := 50
var _finish_last := 50
var _finish_dragging := false
var _module := 0
var _detail_enabled := false
var _sex := "male"
var _hair_style := -1
var _stubble_row: Array[Control] = []
var _quiet := false

func _init() -> void:
	name = "PortraitCustomization"
	size_flags_horizontal = Control.SIZE_EXPAND_FILL
	add_theme_constant_override("separation", 6)
	_timer = Timer.new()
	_timer.one_shot = true
	_timer.wait_time = 0.12
	add_child(_timer)
	_timer.timeout.connect(func() -> void: changed.emit())
	var title := Label.new()
	title.text = "Face & silhouette"
	add_child(title)
	var grid := GridContainer.new()
	grid.columns = 2
	grid.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	add_child(grid)
	_add_choice(grid, "facial_hair", "Facial hair", ["Clean shaven", "Stubble", "Moustache", "Goatee", "Short beard", "Full beard"])
	_add_choice(grid, "hair_detail", "Hair finish", ["Classic", "Tousled", "Swept"])
	_add_finish_slider(controls["hair_detail"] as OptionButton)
	_add_slider(grid, "hair_length", "Hair length", "Shorter", "Longer")
	_add_slider(grid, "hair_volume", "Hair volume", "Close", "Full")
	_add_slider(grid, "jaw", "Jaw width", "Narrow", "Broad")
	_add_slider(grid, "cheekbones", "Cheekbones", "Soft", "Defined")
	_add_slider(grid, "face_length", "Face length", "Shorter", "Longer")
	_add_slider(grid, "nose", "Nose profile", "Delicate", "Strong")
	_add_slider(grid, "nose_width", "Nose width", "Narrow", "Broad")
	_add_slider(grid, "lip_fullness", "Lip fullness", "Fine", "Full")
	_add_slider(grid, "brow_depth", "Brow definition", "Soft", "Strong")
	_add_slider(grid, "eye_size", "Eye size", "Smaller", "Larger")
	_add_slider(grid, "eye_tilt", "Eye angle", "Lower", "Lifted")
	_add_slider(grid, "eye_spacing", "Eye spacing", "Closer", "Wider")
	_add_slider(grid, "height", "Height", "90%", "110%")
	_add_slider(grid, "build", "Body breadth", "85%", "115%")
	var presets := HBoxContainer.new()
	add_child(presets)
	# Keep the starting looks above the longer list of individual controls.
	move_child(presets, 2)
	for preset_name: String in PRESETS.LOOKS:
		var button := Button.new()
		button.text = preset_name
		button.tooltip_text = "Editable face and hair from the Human player studies; keeps your selected sex and class"
		button.accessibility_name = "Preset " + preset_name
		presets.add_child(button)
		button.pressed.connect(func() -> void: apply_preset(preset_name))
	var reset := Button.new()
	reset.text = "Reset shape"
	reset.accessibility_name = "Reset shape"
	presets.add_child(reset)
	reset.pressed.connect(func() -> void:
		reset_shape()
		changed.emit())
	finish_notice = KIT.notice("A custom hair finish is set, but this server can't save it.", "Use nearest finish", "FinishNotice")
	add_child(finish_notice)
	(finish_notice.get_meta("button") as Button).pressed.connect(use_nearest_finish)
	_add_detail_section()
	var hint := Label.new()
	hint.text = "Appearance only. Your movement, reach and equipment stats stay the same."
	hint.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
	add_child(hint)
	_carry(CUSTOMIZATION.normalized({}))
	_apply_detail_enabled()

func _label(grid: GridContainer, text: String) -> Label:
	var label := Label.new()
	label.text = text
	grid.add_child(label)
	return label

func _add_choice(grid: GridContainer, field: String, title: String, entries: Array) -> void:
	_label(grid, title)
	var control := OptionButton.new()
	control.name = field.to_pascal_case()
	control.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	control.accessibility_name = title
	for entry: String in entries:
		control.add_item(entry)
	grid.add_child(control)
	controls[field] = control
	control.item_selected.connect(func(index: int) -> void:
		if field == "hair_detail":
			# Picking a saved finish replaces a slider position (as the server's
			# clearing rule does for an older client).
			_finish_s = HAIR_FINISH.enum_slider(index)
			_sync_finish()
		changed.emit())

## The Sleek ↔ Messy slider shares the Hair finish cell with develop's dropdown;
## one of the two is shown (set_detail_enabled).
func _add_finish_slider(dropdown: OptionButton) -> void:
	var cell := VBoxContainer.new()
	cell.name = "HairFinishCell"
	cell.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	var grid := dropdown.get_parent()
	var index := dropdown.get_index()
	grid.remove_child(dropdown)
	cell.add_child(dropdown)
	grid.add_child(cell)
	grid.move_child(cell, index)
	finish_row = VBoxContainer.new()
	finish_row.name = "HairFinishSlider"
	finish_row.add_theme_constant_override("separation", 0)
	cell.add_child(finish_row)
	var line := HBoxContainer.new()
	line.add_theme_constant_override("separation", 4)
	finish_row.add_child(line)
	finish_previous = _finish_step_button("‹", "Previous named hair finish")
	line.add_child(finish_previous)
	finish_previous.pressed.connect(func() -> void: step_finish(-1))
	var sleek := Label.new()
	sleek.text = "Sleek"
	line.add_child(sleek)
	finish_slider = HSlider.new()
	finish_slider.name = "HairFinish"
	finish_slider.max_value = 100
	finish_slider.step = 1
	finish_slider.value = 50
	finish_slider.custom_minimum_size = Vector2(120, KIT.TARGET)
	finish_slider.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	finish_slider.tooltip_text = FINISH_TOOLTIP
	finish_slider.accessibility_name = "Hair finish"
	finish_slider.focus_mode = Control.FOCUS_ALL
	line.add_child(finish_slider)
	var messy := Label.new()
	messy.text = "Messy"
	line.add_child(messy)
	finish_next = _finish_step_button("›", "Next named hair finish")
	line.add_child(finish_next)
	finish_next.pressed.connect(func() -> void: step_finish(1))
	var ticks := HBoxContainer.new()
	ticks.add_theme_constant_override("separation", 4)
	finish_row.add_child(ticks)
	var left := Control.new()
	left.custom_minimum_size.x = KIT.TARGET + sleek.get_minimum_size().x + 4
	ticks.add_child(left)
	ticks.add_child(KIT.TickStrip.new(finish_slider, FINISH_TICKS))
	var right := Control.new()
	right.custom_minimum_size.x = KIT.TARGET + messy.get_minimum_size().x + 4
	ticks.add_child(right)
	finish_readout = Label.new()
	finish_readout.name = "HairFinishReadout"
	finish_row.add_child(finish_readout)
	KIT.page_keys(finish_slider, 5)
	finish_slider.drag_started.connect(func() -> void: _finish_dragging = true)
	finish_slider.drag_ended.connect(func(_changed: bool) -> void:
		_finish_dragging = false
		_timer.start())
	finish_slider.value_changed.connect(_on_finish_slider)
	_sync_finish()

func _finish_step_button(text: String, accessible: String) -> Button:
	var button := Button.new()
	button.text = text
	button.custom_minimum_size = Vector2(KIT.TARGET, KIT.TARGET)
	button.tooltip_text = accessible
	button.accessibility_name = accessible
	return button

## ‹ › beside the finish slider: the previous or next named finish.
func step_finish(direction: int) -> void:
	if not finish_slider.editable:
		return
	var target := _finish_s
	var order := range(FINISH_TICKS.size()) if direction > 0 else range(FINISH_TICKS.size() - 1, -1, -1)
	for index: int in order:
		var at := int(FINISH_TICKS[index][0])
		if (direction > 0 and at > _finish_s) or (direction < 0 and at < _finish_s):
			target = at
			break
	if target == _finish_s:
		return
	_finish_s = target
	_sync_finish()
	_update_notices()
	changed.emit()

func _on_finish_slider(value: float) -> void:
	if _quiet:
		return
	var s := roundi(value)
	for tick: Array in FINISH_TICKS:
		var at := int(tick[0])
		if s != at and absi(s - at) <= FINISH_SNAP:
			# Leaving a named finish jumps past its snap zone; arriving snaps.
			s = at + (FINISH_SNAP + 1) * signi(s - at) if _finish_last == at else at
			_quiet = true
			finish_slider.value = s
			_quiet = false
			break
	_finish_last = s
	_finish_s = s
	_sync_finish()
	# The preview refits once the drag is released (or after a key press).
	if not _finish_dragging:
		_timer.start()

func _add_slider(grid: GridContainer, field: String, title: String, low: String, high: String,
		tooltip_tail := "centre keeps the authored proportions") -> HSlider:
	_label(grid, title)
	var row := HBoxContainer.new()
	row.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	grid.add_child(row)
	var slider := HSlider.new()
	slider.name = field.to_pascal_case()
	slider.max_value = 100
	slider.step = 1
	slider.value = 50
	slider.custom_minimum_size.x = 120
	slider.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	slider.tooltip_text = low + " — " + high + "; " + tooltip_tail
	slider.accessibility_name = title
	row.add_child(slider)
	var readout := Label.new()
	readout.custom_minimum_size.x = 42
	row.add_child(readout)
	if field in CUSTOMIZATION.V3_CONTROLS:
		detail_controls[field] = slider
	else:
		controls[field] = slider
	slider.value_changed.connect(func(value: float) -> void:
		readout.text = _readout(field, value)
		slider.accessibility_description = readout.text
		_update_notices()
		_timer.start())
	readout.text = _readout(field, 50)
	slider.accessibility_description = readout.text
	slider.set_meta("readout", readout)
	return slider

func _readout(field: String, value: float) -> String:
	if field == "height":
		return "%d%%" % roundi(90 + value * 0.2)
	if field == "build":
		return "%d%%" % roundi(85 + value * 0.3)
	return str(roundi(value))

# ---------------------------------------------------------------- PC/3 detail

func _add_detail_section() -> void:
	detail_notice = KIT.notice("High-detail options are set, but this server can't save them.", "Reset to Auto", "DetailNotice")
	add_child(detail_notice)
	(detail_notice.get_meta("button") as Button).pressed.connect(func() -> void:
		reset_detail()
		changed.emit())
	detail_toggle = Button.new()
	detail_toggle.name = "MoreFaceDetail"
	detail_toggle.text = "More face detail"
	detail_toggle.toggle_mode = true
	detail_toggle.alignment = HORIZONTAL_ALIGNMENT_LEFT
	detail_toggle.custom_minimum_size.y = KIT.TARGET
	detail_toggle.accessibility_name = "More face detail"
	add_child(detail_toggle)
	detail_box = VBoxContainer.new()
	detail_box.name = "FaceDetail"
	detail_box.add_theme_constant_override("separation", 4)
	detail_box.hide()
	add_child(detail_box)
	detail_toggle.toggled.connect(func(open: bool) -> void:
		detail_box.visible = open)
	var subtitle := Label.new()
	subtitle.text = "Shown at High graphics. Low and Medium keep the classic look."
	subtitle.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
	detail_box.add_child(subtitle)
	var grid := GridContainer.new()
	grid.name = "FaceDetailGrid"
	grid.columns = 2
	grid.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	detail_box.add_child(grid)
	for group: Array in DETAIL_GROUPS:
		var heading := Label.new()
		heading.text = str(group[0]).to_upper()
		heading.add_theme_font_size_override("font_size", 11)
		grid.add_child(heading)
		grid.add_child(Control.new())
		for entry: Array in group[1]:
			var field := str(entry[0])
			if field in AUTO_FIELDS:
				_add_auto(grid, field, str(entry[1]), str(entry[2]), str(entry[3]))
			elif field == "lip_tint":
				_add_lip_tint(grid, str(entry[1]))
			elif field == "hair_module":
				_add_module(grid, str(entry[1]))
			else:
				_add_slider(grid, field, str(entry[1]), str(entry[2]), str(entry[3]), "centre keeps your face's default")

func _add_auto(grid: GridContainer, field: String, title: String, low: String, high: String) -> void:
	var label := _label(grid, title)
	var row := HBoxContainer.new()
	row.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	grid.add_child(row)
	var auto := CheckBox.new()
	auto.name = field.to_pascal_case() + "Auto"
	auto.text = "Auto"
	auto.button_pressed = true
	auto.custom_minimum_size.y = KIT.TARGET
	auto.tooltip_text = "Automatic: derived from your skin, sex and facial hair"
	auto.accessibility_name = "Automatic " + title.to_lower()
	row.add_child(auto)
	var slider := HSlider.new()
	slider.name = field.to_pascal_case()
	slider.min_value = 1
	slider.max_value = CUSTOMIZATION.maximum(field)
	slider.step = 1
	slider.value = 1
	slider.editable = false
	slider.custom_minimum_size.x = 96
	slider.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	slider.tooltip_text = low + " — " + high
	slider.accessibility_name = title
	row.add_child(slider)
	var readout := Label.new()
	readout.custom_minimum_size.x = 64
	row.add_child(readout)
	detail_controls[field] = {"auto": auto, "slider": slider, "readout": readout}
	if field == "stubble":
		_stubble_row = [label, row]
	auto.toggled.connect(func(automatic: bool) -> void:
		slider.editable = not automatic
		# Unticking keeps the knob where the derived look put it.
		_sync_auto_readout(field)
		_update_notices()
		changed.emit())
	slider.value_changed.connect(func(_value: float) -> void:
		_sync_auto_readout(field)
		if _quiet:
			return
		_update_notices()
		_timer.start())
	_sync_auto_readout(field)

func _sync_auto_readout(field: String) -> void:
	var entry: Dictionary = detail_controls[field]
	var slider := entry.slider as HSlider
	var value := roundi(slider.value)
	var text := ""
	match field:
		"brow_style":
			var style := float(value - 1) / 4.0
			var low := floori(style)
			var part := roundi((style - low) * 100.0)
			text = BROW_NAMES[clampi(low, 0, 3)] if part == 0 \
				else "%s to %s %d%%" % [BROW_NAMES[clampi(low, 0, 3)], BROW_NAMES[clampi(low + 1, 0, 3)], part]
		"brow_thickness":
			text = "%+d" % ((value - 51) * 2)
		_:
			text = "%d%%" % (value - 1)
	if (entry.auto as CheckBox).button_pressed:
		text = "Auto (%s)" % text
	(entry.readout as Label).text = text
	slider.accessibility_description = text

func _add_lip_tint(grid: GridContainer, title: String) -> void:
	_label(grid, title)
	var option := OptionButton.new()
	option.name = "LipTint"
	option.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	option.accessibility_name = title
	option.add_item("Auto", 0)
	for entry: Dictionary in CHOICES.options("lip_tint"):
		option.add_icon_item(KIT.swatch_icon(entry.color as Color), str(entry.label), int(entry.id))
	grid.add_child(option)
	detail_controls["lip_tint"] = option
	option.item_selected.connect(func(_index: int) -> void:
		option.accessibility_description = option.get_item_text(option.selected)
		_update_notices()
		changed.emit())

func _add_module(grid: GridContainer, title: String) -> void:
	_label(grid, title)
	var cell := VBoxContainer.new()
	cell.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	grid.add_child(cell)
	var option := OptionButton.new()
	option.name = "HairModule"
	option.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	option.tooltip_text = "Replaces your hairstyle only at High graphics. Low and Medium (and any fallback) draw the hairstyle you chose above."
	option.accessibility_name = title
	cell.add_child(option)
	module_hint = Label.new()
	module_hint.name = "HairModuleHint"
	module_hint.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
	cell.add_child(module_hint)
	detail_controls["hair_module"] = option
	option.item_selected.connect(func(index: int) -> void:
		_module = option.get_item_id(index)
		_sync_module()
		_update_notices()
		changed.emit())
	_fill_modules()

func _fill_modules() -> void:
	var option := detail_controls["hair_module"] as OptionButton
	option.clear()
	option.add_item("Automatic (by hairstyle)", 0)
	option.add_item("Classic hairstyle", 1)
	for id: int in RLHeadPortraitMap.HAIR_MODULES:
		var module: Dictionary = RLHeadPortraitMap.HAIR_MODULES[id]
		if str(module.sex) == _sex:
			option.add_item(str(MODULE_NAMES.get(str(module.name), str(module.name).capitalize())), id)
	_sync_module()

func _sync_module() -> void:
	var option := detail_controls["hair_module"] as OptionButton
	var index := option.get_item_index(_module)
	# A saved module this body cannot show stays saved (shown as Automatic).
	option.select(index if index >= 0 else 0)
	option.disabled = _hair_style == 0
	option.accessibility_description = option.get_item_text(option.selected)
	var hair := RLHeadPortraitMap.hair({"hair": AppearanceVariants.pack_hair(maxi(_hair_style, 0), 0),
		"hair_module": _module}, _sex)
	if _hair_style == 0:
		module_hint.text = "Bald at every graphics level."
	elif RLHeadPortraitMap.is_module(hair):
		module_hint.text = "At High: " + str(MODULE_NAMES.get(hair, hair))
	else:
		module_hint.text = "At High: your hairstyle"

# ---------------------------------------------------------------- state

func _carry(normalized: Dictionary) -> void:
	_carried.clear()
	for field: String in CUSTOMIZATION.FIELDS:
		if not controls.has(field) and not detail_controls.has(field) and field != "hair_finish":
			_carried[field] = normalized[field]

func values() -> Dictionary:
	var result := _carried.duplicate()
	for field: String in controls:
		var control: Control = controls[field]
		result[field] = (control as OptionButton).selected if control is OptionButton else roundi((control as Range).value)
	result.merge(HAIR_FINISH.canonical(_finish_s), true)
	for field: String in detail_controls:
		var widget: Variant = detail_controls[field]
		if widget is Dictionary:
			var entry := widget as Dictionary
			result[field] = 0 if (entry.auto as CheckBox).button_pressed else roundi((entry.slider as HSlider).value)
		elif field == "hair_module":
			result[field] = _module
		elif widget is OptionButton:
			result[field] = (widget as OptionButton).get_selected_id()
		else:
			result[field] = roundi((widget as Range).value)
	return result

func set_values(appearance: Dictionary) -> void:
	var normalized := CUSTOMIZATION.normalized(appearance)
	_carry(normalized)
	_quiet = true
	for field: String in controls:
		var control: Control = controls[field]
		if control is OptionButton:
			(control as OptionButton).select(normalized[field])
		else:
			(control as Range).set_value_no_signal(normalized[field])
			(control.get_meta("readout") as Label).text = _readout(field, normalized[field])
	# A slider position the renderer would not draw (its nearest finish is not
	# the saved hair_detail) shows the saved finish, as the renderer does.
	_finish_s = int(HAIR_FINISH.resolve(normalized).s)
	_finish_last = _finish_s
	for field: String in detail_controls:
		var widget: Variant = detail_controls[field]
		var value := int(normalized[field])
		if widget is Dictionary:
			var entry := widget as Dictionary
			(entry.auto as CheckBox).set_pressed_no_signal(value == 0)
			(entry.slider as HSlider).editable = value != 0
			if value != 0:
				(entry.slider as HSlider).set_value_no_signal(value)
			_sync_auto_readout(field)
		elif field == "hair_module":
			_module = value
		elif widget is OptionButton:
			var option := widget as OptionButton
			option.select(maxi(0, option.get_item_index(value)))
		else:
			(widget as Range).set_value_no_signal(value)
			var readout := (widget as Control).get_meta("readout") as Label
			readout.text = _readout(field, value)
	_quiet = false
	_sync_finish()
	_sync_module()
	update_derived(normalized)
	_update_notices()

## The preset buttons: the study's face and hair, its PC/3 detail while the
## section is offered (else neutral), and its colours through preset_selected
## (HumanPortraitPresets.pick: the nearest palette bytes plus the concept
## colours, which the host applies while custom colours are offered).
func apply_preset(preset_name: String) -> void:
	var look := PRESETS.shape(preset_name)
	if _detail_enabled:
		look.merge(PRESETS.detail(preset_name), true)
		if _sex != "male":
			# Stubble shows only on a male head at High.
			look["stubble"] = 0
	for field: String in _carried:
		if field in CUSTOMIZATION.V3_COLOURS:
			look[field] = _carried[field]
	set_values(look)
	preset_selected.emit(PRESETS.pick(preset_name))
	changed.emit()

## Reset shape: every face and body field to neutral. On a PC/3 server the
## hair finish keeps its value (its own slider resets it); with develop's
## dropdown it returns to Classic as before. Colours are untouched.
func reset_shape() -> void:
	var keep := {}
	for field: String in _carried:
		if field in CUSTOMIZATION.V3_COLOURS:
			keep[field] = _carried[field]
	if _detail_enabled:
		keep.merge(HAIR_FINISH.canonical(_finish_s), true)
	set_values(keep)

# ---------------------------------------------------------------- gating

## Offers the PC/3 controls - the Sleek ↔ Messy slider and More face detail -
## when the server negotiated PC/3 (Humans only: the form is Human-only).
func set_detail_enabled(enabled: bool) -> void:
	if enabled == _detail_enabled:
		_update_notices()
		return
	_detail_enabled = enabled
	_apply_detail_enabled()

func detail_enabled() -> bool:
	return _detail_enabled

func _apply_detail_enabled() -> void:
	(controls["hair_detail"] as OptionButton).visible = not _detail_enabled
	finish_row.visible = _detail_enabled
	detail_toggle.visible = _detail_enabled
	detail_box.visible = _detail_enabled and detail_toggle.button_pressed
	_sync_finish()
	_update_notices()

## The body: 0 female, 1 male. Stubble shows for men only and the High-detail
## hair list offers the body's modules. With `reset_incompatible` (creation),
## a female body also clears stubble and a module of the other sex.
func set_body(actor_type: int, reset_incompatible := false) -> void:
	_sex = "female" if actor_type == 0 else "male"
	for control: Control in _stubble_row:
		control.visible = _sex == "male"
	if reset_incompatible:
		if _sex == "female":
			var stubble: Dictionary = detail_controls["stubble"]
			(stubble.auto as CheckBox).set_pressed_no_signal(true)
			(stubble.slider as HSlider).editable = false
			_sync_auto_readout("stubble")
		if RLHeadPortraitMap.HAIR_MODULES.has(_module) \
				and str((RLHeadPortraitMap.HAIR_MODULES[_module] as Dictionary).sex) != _sex:
			_module = 0
	_fill_modules()
	update_derived(values())
	_update_notices()

## The hairstyle (0 Bald disables the finish slider and the hair module).
func set_hair_style(style: int) -> void:
	_hair_style = style
	finish_slider.editable = style != 0
	finish_previous.disabled = style == 0
	finish_next.disabled = style == 0
	finish_slider.tooltip_text = FINISH_TOOLTIP if style != 0 else "Bald has no hair finish."
	_sync_module()

## Every PC/3 detail field back to neutral: offsets 50, details Auto.
func reset_detail() -> void:
	var look := values()
	for field: String in CUSTOMIZATION.V3_CONTROLS + CUSTOMIZATION.V3_DETAILS:
		if field != "hair_finish":
			look[field] = CUSTOMIZATION.DEFAULTS[field]
	set_values(look)

## True while a PC/3 detail value is not neutral (the section's notice).
func unsupported_detail() -> bool:
	var look := values()
	for field: String in CUSTOMIZATION.V3_CONTROLS + CUSTOMIZATION.V3_DETAILS:
		if field != "hair_finish" and int(look[field]) != int(CUSTOMIZATION.DEFAULTS[field]):
			return true
	return false

## True while the finish is a slider position other than a saved finish.
func custom_finish() -> bool:
	return int(HAIR_FINISH.canonical(_finish_s).hair_finish) != 0

## The finish notice's button: the nearest saved finish.
func use_nearest_finish() -> void:
	_finish_s = HAIR_FINISH.enum_slider(HAIR_FINISH.nearest_enum(_finish_s))
	_sync_finish()
	_update_notices()
	changed.emit()

## Places each Auto knob where the derived look puts it (RLHeadPortraitMap
## .details), so unticking Auto starts from the current look.
func update_derived(look: Dictionary) -> void:
	var automatic := look.duplicate()
	for field: String in AUTO_FIELDS:
		automatic[field] = 0
	var derived := RLHeadPortraitMap.details(automatic, _sex)
	_quiet = true
	for field: String in AUTO_FIELDS:
		var entry: Dictionary = detail_controls[field]
		if not (entry.auto as CheckBox).button_pressed:
			continue
		var amount := float(derived.get(field, 0.0))
		var wire := 1 + roundi(100.0 * amount)
		if field == "brow_style":
			wire = 1 + roundi(4.0 * amount)
		elif field == "brow_thickness":
			wire = 51 + roundi(50.0 * amount)
		(entry.slider as HSlider).set_value_no_signal(clampi(wire, 1, CUSTOMIZATION.maximum(field)))
		_sync_auto_readout(field)
	_quiet = false

func _sync_finish() -> void:
	var detail := controls.get("hair_detail") as OptionButton
	var saved := HAIR_FINISH.canonical(_finish_s)
	if detail != null:
		detail.select(int(saved.hair_detail))
	if finish_slider == null:
		return
	var was := _quiet
	_quiet = true
	finish_slider.value = _finish_s
	_quiet = was
	_finish_last = _finish_s
	finish_readout.text = finish_name(_finish_s)
	finish_slider.accessibility_description = finish_readout.text

## The readout: a saved finish's name, or where between them the slider is.
static func finish_name(s: int) -> String:
	for tick: Array in FINISH_TICKS:
		if s == int(tick[0]):
			return str(tick[1])
	if s < 25:
		return "Sleeker than Swept (%d)" % s
	if s < 50:
		return "Between Swept and Classic (%d)" % s
	if s < 75:
		return "Between Classic and Tousled (%d)" % s
	return "Messier than Tousled (%d)" % s

func _update_notices() -> void:
	if finish_notice == null or detail_notice == null:
		return
	finish_notice.visible = not _detail_enabled and custom_finish()
	detail_notice.visible = not _detail_enabled and unsupported_detail()
