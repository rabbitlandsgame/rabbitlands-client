class_name ColourChoice
extends VBoxContainer
## One colour (hair, eyes, shirt, pants or boots; colour model spec 6.1): the
## existing palette dropdown, a swatch chip and name, and a Custom… toggle that
## opens an inline OKHSL wheel. A pick is quantised to the wire triple, shown
## as decoded, and snapped (Rule B): a triple equal to a palette entry's frozen
## value is that palette entry, saved with the custom fields 0. Otherwise the
## dropdown shows the nearest palette entry, which is also the legacy byte
## older recipients get. A later palette pick replaces the custom colour.
##
## Hair shows apparent colours (what the hair looks like, on the skin swatches'
## scale), with the reach of the current hairstyle; eyes are iris pigments
## within the readability limits; garments are dyes kept readable against
## the skin.

signal changed
## The wheel opened (true) or closed (false).
signal toggled_open(open: bool)

const COLOURS := preload("res://src/actors/appearance_colours.gd")
const HAIR_FINISH := preload("res://src/actors/hair_finish.gd")
const KIT := preload("res://src/ui/appearance_ui_kit.gd")
const TITLES := {"hair": "Hair colour", "eyes": "Eye colour", "shirt": "Shirt dye",
	"pants": "Pants dye", "boots": "Boots dye"}
## Hairstyle slots 1..9 (0 is Bald): the reach ceiling over every hairstyle.
const HAIR_STYLES := 9

var group := ""
var picker: OptionButton
var title_label: Label
var chip: ColorRect
var custom_button: Button
var name_label: Label
var panel: VBoxContainer
var color_picker: ColorPicker
var shown_chip: ColorRect
var shown_label: Label
var light_bar: Control
var reach_notice: HBoxContainer
var limit_notice: HBoxContainer
var _row: HBoxContainer
var _wire := Vector3i.ZERO
var _wire_id := -1
var _enabled := false
var _sex := "male"
var _look: Dictionary = {}
var _model_config: Dictionary = {}
var _quiet := false
var _last_pick := Vector3i.ZERO
var _commit: Timer


func _init(colour_group := "hair") -> void:
	group = colour_group
	name = "%sColour" % group.capitalize()
	size_flags_horizontal = Control.SIZE_EXPAND_FILL
	add_theme_constant_override("separation", 3)
	_row = HBoxContainer.new()
	_row.name = "Row"
	add_child(_row)
	title_label = Label.new()
	title_label.text = str(TITLES.get(group, group.capitalize()))
	title_label.custom_minimum_size.x = 88
	_row.add_child(title_label)
	chip = ColorRect.new()
	chip.name = "Chip"
	chip.custom_minimum_size = Vector2(KIT.TARGET, KIT.TARGET)
	chip.size_flags_vertical = Control.SIZE_SHRINK_CENTER
	chip.mouse_filter = Control.MOUSE_FILTER_IGNORE
	_row.add_child(chip)
	custom_button = Button.new()
	custom_button.name = "Custom"
	custom_button.text = "Custom…"
	custom_button.toggle_mode = true
	custom_button.custom_minimum_size = Vector2(KIT.TARGET, KIT.TARGET)
	custom_button.tooltip_text = "Open a colour wheel for any %s" % title_label.text.to_lower()
	custom_button.accessibility_name = "Custom " + title_label.text.to_lower()
	_row.add_child(custom_button)
	custom_button.toggled.connect(func(pressed: bool) -> void: set_open(pressed))
	name_label = Label.new()
	name_label.name = "Name"
	name_label.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
	name_label.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	add_child(name_label)
	panel = VBoxContainer.new()
	panel.name = "Wheel"
	panel.add_theme_constant_override("separation", 4)
	panel.hide()
	add_child(panel)
	color_picker = ColorPicker.new()
	color_picker.name = "Picker"
	color_picker.picker_shape = ColorPicker.SHAPE_OKHSL_CIRCLE
	color_picker.color_mode = ColorPicker.MODE_OKHSL
	color_picker.edit_alpha = false
	color_picker.edit_intensity = false
	color_picker.sampler_visible = false
	color_picker.color_modes_visible = false
	color_picker.hex_visible = false
	color_picker.sliders_visible = true
	color_picker.presets_visible = true
	color_picker.can_add_swatches = false
	color_picker.deferred_mode = false
	color_picker.size_flags_horizontal = Control.SIZE_SHRINK_CENTER
	color_picker.accessibility_name = title_label.text + " wheel"
	color_picker.color_changed.connect(_on_pick)
	_tidy_picker(color_picker)
	var shown_row := HBoxContainer.new()
	shown_row.name = "Shown"
	panel.add_child(shown_row)
	shown_chip = ColorRect.new()
	shown_chip.custom_minimum_size = Vector2(KIT.TARGET, KIT.TARGET)
	shown_chip.mouse_filter = Control.MOUSE_FILTER_IGNORE
	shown_row.add_child(shown_chip)
	shown_label = Label.new()
	shown_label.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
	shown_label.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	shown_row.add_child(shown_label)
	shown_row.visible = group in ["hair", "eyes"]
	light_bar = KIT.LightBar.new()
	light_bar.name = "Lightness"
	light_bar.visible = group in ["hair", "eyes"]
	panel.add_child(light_bar)
	reach_notice = KIT.notice("Lighter than some hairstyles can show", "", "ReachNotice")
	panel.add_child(reach_notice)
	limit_notice = KIT.notice("Adjusted to stand out from your skin", "", "LimitNotice")
	panel.add_child(limit_notice)
	panel.add_child(color_picker)
	_commit = Timer.new()
	_commit.one_shot = true
	_commit.wait_time = 0.12
	add_child(_commit)
	_commit.timeout.connect(_show_decoded)
	set_custom_enabled(false)


## The wheel shows the palette as open swatches and nothing a player cannot
## use here: no swatch menu, recent colours or colour-space link.
static func _tidy_picker(picker_node: ColorPicker) -> void:
	var pending: Array[Node] = [picker_node]
	while not pending.is_empty():
		var node: Node = pending.pop_back()
		for child: Node in node.get_children(true):
			pending.append(child)
		if node is LinkButton:
			(node as Control).hide()
		elif node is MenuButton and (node as MenuButton).tooltip_text == "Show all options available.":
			(node as Control).hide()
		elif node is Button and (node as Button).text == "Recent Colors":
			(node as Control).hide()
			var index := node.get_index(true)
			var parent := node.get_parent()
			if index + 1 < parent.get_child_count(true):
				var recent := parent.get_child(index + 1, true) as Control
				if recent != null:
					recent.hide()
		elif node is Button and (node as Button).text == "Swatches":
			var button := node as Button
			if button.toggle_mode:
				button.button_pressed = true
			else:
				button.pressed.emit()


## The palette dropdown this choice wraps (connected once).
func bind(option: OptionButton) -> void:
	picker = option
	picker.accessibility_name = title_label.text
	picker.item_selected.connect(func(_index: int) -> void:
		# A palette pick replaces the custom colour (the stale check in wire()
		# already ignores it, whichever handler runs first).
		_wire = Vector3i.ZERO
		_wire_id = -1
		_sync())
	_sync()


## Moves the dropdown into this row (the colour layout). The panel records
## where it came from and puts it back (develop's layout).
func attach() -> void:
	if picker == null or picker.get_parent() == _row:
		return
	picker.reparent(_row, false)
	_row.move_child(picker, 1)
	picker.size_flags_horizontal = Control.SIZE_EXPAND_FILL


func set_custom_enabled(enabled: bool) -> void:
	_enabled = enabled
	custom_button.visible = enabled
	chip.visible = enabled
	if not enabled:
		set_open(false)
	_sync()


func set_open(open: bool) -> void:
	open = open and _enabled
	var was := panel.visible
	panel.visible = open
	custom_button.set_pressed_no_signal(open)
	if open:
		_load_presets()
		_quiet = true
		color_picker.color = current_colour()
		_quiet = false
		_last_pick = COLOURS.quantise(color_picker.color)
		_sync()
	if was != open:
		toggled_open.emit(open)


func is_open() -> bool:
	return panel.visible


## The body's sex: hair apparent colours and their snapping are per sex.
func set_sex(sex: String) -> void:
	_sex = "male" if sex == "male" else "female"
	if panel.visible:
		_load_presets()
	_sync()


## The whole current look and model (reach on the hairstyle, garment contrast
## against the skin); refreshes the indications.
func set_context(look: Dictionary, model_config: Dictionary) -> void:
	_look = look
	_model_config = model_config
	_sync()


## The custom triple to save, or ZERO for the palette. A custom value is
## stale once the dropdown shows another entry than it was saved with.
func wire() -> Vector3i:
	if _wire != Vector3i.ZERO and (picker == null or picker.get_selected_id() != _wire_id):
		_wire = Vector3i.ZERO
		_wire_id = -1
	return _wire


func is_custom() -> bool:
	return wire() != Vector3i.ZERO


## Shows a saved triple (after the host selected the legacy byte). Neutral
## and a typed frozen value are the palette; a value whose nearest entry is
## not the saved byte is drawn as the palette (the guard), so it is dropped.
## With `follow`, the dropdown moves to the triple's nearest entry instead.
func set_wire(value: Vector3i, follow := false) -> void:
	_wire = Vector3i.ZERO
	_wire_id = -1
	if value.x < 1 or value.y < 1 or value.z < 1 or picker == null:
		_sync()
		return
	var snapped := _snap(value)
	if snapped >= 0:
		if follow:
			_select(snapped)
		_sync()
		return
	var nearest := nearest_index(COLOURS.triple_colour(value))
	if follow:
		_select(nearest)
	elif nearest != picker.get_selected_id() and frozen(picker.get_selected_id()) != value:
		_sync()
		return
	_wire = value
	_wire_id = picker.get_selected_id()
	_sync()


func clear_custom() -> void:
	_wire = Vector3i.ZERO
	_wire_id = -1
	_sync()


## The palette entry whose frozen triple is `value`, else -1 (Rule B).
func _snap(value: Vector3i) -> int:
	for index: int in palette_size():
		if frozen(index) == value:
			return index
	return -1


func palette_size() -> int:
	return 20 if group == "hair" else 12


func frozen(index: int) -> Vector3i:
	match group:
		"hair":
			return COLOURS.frozen_hair(index, _sex)
		"eyes":
			return COLOURS.EYE_FROZEN[posmod(index, 12)]
	return COLOURS.frozen_dye(group, index)


## The colour a palette entry shows on the wheel: hair as its apparent colour.
func palette_colour(index: int) -> Color:
	match group:
		"hair":
			return COLOURS.palette_apparent(index, _sex)
		"eyes":
			return AppearanceVariants.eye_color(index)
	return AppearanceVariants.wardrobe_color("luminous", COLOURS.PARTS[group], index)


func nearest_index(colour: Color) -> int:
	match group:
		"hair":
			return COLOURS.nearest_hair_index(colour, _sex)
		"eyes":
			return COLOURS.nearest_eye_index(colour)
	return COLOURS.nearest_dye_index(colour, group)


## The colour chosen: the custom triple's, else the selected palette entry's.
func current_colour() -> Color:
	var value := wire()
	if value != Vector3i.ZERO:
		return COLOURS.triple_colour(value)
	return palette_colour(picker.get_selected_id() if picker != null else 0)


func _select(index: int) -> void:
	if picker == null:
		return
	var item := picker.get_item_index(index)
	if item < 0:
		# The dropdown merges near-identical dyes: show the closest listed one.
		var target := COLOURS.oklab(palette_colour(index))
		var best := INF
		for row: int in picker.item_count:
			var d := target.distance_to(COLOURS.oklab(palette_colour(picker.get_item_id(row))))
			if d < best:
				best = d
				item = row
	if item >= 0:
		picker.select(item)


func _on_pick(colour: Color) -> void:
	if _quiet or not _enabled:
		return
	var value := COLOURS.quantise(colour)
	if value.y <= 1:
		# Grey has no hue: keep the last hue so the wheel does not jump to red.
		value.x = _last_pick.x if _last_pick.x >= 1 else value.x
	if value == _last_pick and is_custom():
		return
	_last_pick = value
	var snapped := _snap(value)
	if snapped >= 0:
		_wire = Vector3i.ZERO
		_wire_id = -1
		_select(snapped)
	else:
		_select(nearest_index(COLOURS.triple_colour(value)))
		_wire = value
		_wire_id = picker.get_selected_id()
	_commit.start()
	_sync(false)
	changed.emit()


## Shows the saved (decoded) value on the wheel once the pick settles.
func _show_decoded() -> void:
	if not panel.visible:
		return
	_sync()
	var decoded := current_colour()
	if decoded.ok_hsl_s <= 0.0001:
		return
	_quiet = true
	color_picker.set_pick_color(decoded)
	_quiet = false


func _load_presets() -> void:
	for preset: Color in color_picker.get_presets():
		color_picker.erase_preset(preset)
	var seen := {}
	for row: int in (picker.item_count if picker != null else 0):
		var colour := palette_colour(picker.get_item_id(row))
		var key := colour.to_html(false)
		if not seen.has(key):
			seen[key] = true
			color_picker.add_preset(colour)


## The name readout: the palette entry's, or "Custom, near <entry>".
func readout() -> String:
	if picker == null or picker.selected < 0:
		return ""
	var entry := picker.get_item_text(picker.selected)
	return ("Custom, near " + entry) if is_custom() else entry


## `full` also refreshes the wheel's indications (the hair reach ceilings
## cost a few milliseconds, so a drag refreshes them once it settles).
func _sync(full := true) -> void:
	if picker == null:
		return
	var colour := current_colour()
	chip.color = _chip_colour(colour)
	name_label.text = readout()
	name_label.visible = _enabled and is_custom()
	custom_button.accessibility_description = name_label.text
	picker.accessibility_description = name_label.text
	if not panel.visible or not full:
		return
	reach_notice.hide()
	limit_notice.hide()
	match group:
		"hair":
			_sync_hair(colour)
		"eyes":
			_sync_eyes(colour)
		_:
			_sync_garment(colour)


func _chip_colour(colour: Color) -> Color:
	if group == "eyes":
		var pigment := COLOURS.limit_eye(colour) if is_custom() else colour
		return RLHeadPortraitMap.natural_iris(pigment)
	return colour


# --------------------------------------------------------------- hair reach

## The hair draw paths a hairstyle uses for the current look: the Low/Medium
## one (P1 Classic at length and volume 50, P2 Classic reshaped, P3 a
## finish) and develop's classic High (P4), with the finish position.
func hair_paths() -> Dictionary:
	var detail := clampi(int(_look.get("hair_detail", 0)), 0, 2)
	var finish := HAIR_FINISH.resolve(_look)
	var custom_finish := bool(finish.custom)
	var length := roundi(CharacterProportions.value(_look, "hair_length"))
	var volume := roundi(CharacterProportions.value(_look, "hair_volume"))
	var medium := "P3" if custom_finish or detail != 0 else ("P1" if length == 50 and volume == 50 else "P2")
	return {"paths": [medium, "P4"], "s": float(finish.s), "length": length, "volume": volume}


## The uniform reach (1 = in reach) of apparent colour `colour` on `style`:
## the smaller of its Low/Medium and classic High paths.
func hair_reach(colour: Color, style: int) -> float:
	var paths := hair_paths()
	var reach := 1.0
	for path: String in paths.paths:
		var result := COLOURS.hair_dye_linear(COLOURS.to_linear(colour), _sex, path, style,
			float(paths.s), int(paths.length), int(paths.volume))
		reach = minf(reach, float(result.reach))
	return reach


## The lightest OKHSL lightness a hairstyle shows at this hue and saturation:
## a near-white of the hue scaled into reach, as the renderer scales it.
func hair_ceiling(colour: Color, style: int) -> float:
	var top := Color.from_ok_hsl(colour.ok_hsl_h, colour.ok_hsl_s, 0.95)
	var reach := hair_reach(top, style)
	if reach >= 0.9999:
		return 1.0
	return COLOURS.to_srgb(COLOURS.to_linear(top) * reach).ok_hsl_l


func hair_style() -> int:
	return AppearanceVariants.hair_style(int(_look.get("hair", 0)))


func _sync_hair(colour: Color) -> void:
	var style := hair_style()
	var own := hair_ceiling(colour, style) if style > 0 else 1.0
	var every := 1.0
	for slot: int in range(1, HAIR_STYLES + 1):
		every = minf(every, hair_ceiling(colour, slot))
	var reach := hair_reach(colour, style) if style > 0 else 1.0
	var shown := COLOURS.to_srgb(COLOURS.to_linear(colour) * reach)
	shown_chip.color = shown
	shown_label.text = "On this hairstyle" + ("" if reach >= 0.9999 else " (as light as it can show)")
	var marks: Array = [[every, "all styles"]]
	if own < 0.9999 and absf(own - every) > 0.02:
		marks.append([own, "this style"])
	elif own < 0.9999:
		marks = [[own, "this style / all"]]
	light_bar.configure(colour.ok_hsl_h, colour.ok_hsl_s, colour.ok_hsl_l, [], marks)
	light_bar.set_meta("ceilings", {"style": own, "every": every})
	var label := reach_notice.get_meta("label") as Label
	if colour.ok_hsl_l > own + 0.005:
		label.text = "Lighter than this hairstyle can show"
		reach_notice.show()
	elif colour.ok_hsl_l > every + 0.005:
		label.text = "Lighter than some hairstyles can show"
		reach_notice.show()


func _sync_eyes(colour: Color) -> void:
	var pigment := COLOURS.limit_eye(colour) if is_custom() else colour
	shown_chip.color = RLHeadPortraitMap.natural_iris(pigment)
	shown_label.text = "Iris as drawn"
	light_bar.configure(colour.ok_hsl_h, colour.ok_hsl_s, colour.ok_hsl_l,
		[[0.0, COLOURS.EYE_LIGHT_MIN], [COLOURS.EYE_LIGHT_MAX, 1.0]], [])
	if is_custom() and not pigment.is_equal_approx(colour):
		(limit_notice.get_meta("label") as Label).text = "Kept readable against the pupil and the white of the eye"
		limit_notice.show()


func _sync_garment(colour: Color) -> void:
	if not is_custom():
		return
	var skin := COLOURS.skin_shown(_look, _model_config) if not _model_config.is_empty() \
		else Color(0.8, 0.63, 0.53)
	var window := Color.from_ok_hsl(colour.ok_hsl_h, colour.ok_hsl_s,
		clampf(colour.ok_hsl_l, COLOURS.GARMENT_LIGHT_MIN, COLOURS.GARMENT_LIGHT_MAX))
	var final := COLOURS.limit_garment(colour, group, skin)
	var label := limit_notice.get_meta("label") as Label
	if not final.is_equal_approx(window):
		label.text = "Adjusted to stand out from your skin"
		limit_notice.show()
	elif not window.is_equal_approx(colour):
		label.text = "Kept within the readable lightness range"
		limit_notice.show()
