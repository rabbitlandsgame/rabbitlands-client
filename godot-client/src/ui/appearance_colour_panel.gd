class_name AppearanceColourPanel
extends VBoxContainer
## The colour model's controls for one host (character creation and the
## dressing room; colour model spec 6): the skin tone slider with undertone
## and Eloria tones, and a colour wheel for hair, eyes, shirt, pants and boots
## around the host's own palette dropdowns.
##
## Offered only to Humans on a server that negotiated PC/3
## (set_custom_colours_enabled). Otherwise the host's palette grid is exactly
## develop's: the dropdowns stay where they were and nothing here draws. The
## dropdowns always show the palette byte saved for older recipients - the
## nearest entry of a custom colour - so they stay a full non-visual path.
## Disabling keeps custom values (they are still returned and the version gate
## refuses to save them), with a notice that offers the nearest palette
## colours instead.

signal changed
## The eye wheel opened or closed: hosts frame the face while it is open.
signal face_focus(enabled: bool)

const COLOURS := preload("res://src/actors/appearance_colours.gd")
const KIT := preload("res://src/ui/appearance_ui_kit.gd")
const SKIN_SLIDER := preload("res://src/ui/skin_tone_slider.gd")
const COLOUR_CHOICE := preload("res://src/ui/colour_choice.gd")
## The order of the colour layout (colour model spec 6.2).
const GROUPS: Array[String] = ["hair", "eyes", "shirt", "pants", "boots"]
## The host dropdown each colour wraps.
const PICKER_KEYS := {"hair": "hair_color", "eyes": "eyes", "shirt": "shirt", "pants": "pants", "boots": "boots"}
const HELD_TEXT := "Custom colours are set, but this server can't save them."

var skin_slider: SKIN_SLIDER
var choices: Dictionary = {}
var notice: HBoxContainer
var hair_row: HBoxContainer
var content: VBoxContainer
var _pickers: Dictionary = {}
var _grid: Control
var _enabled := false
var _sex := "male"
var _model_config: Dictionary = {}
var _look: Dictionary = {}
var _skin_custom := {"tone": 0, "undertone": 0, "id": -1}
## [node, parent, index] of each dropdown the colour layout moved.
var _homes: Array = []
var _timer: Timer
var _quiet := false


func _init() -> void:
	name = "AppearanceColours"
	size_flags_horizontal = Control.SIZE_EXPAND_FILL
	add_theme_constant_override("separation", 6)
	_timer = Timer.new()
	_timer.one_shot = true
	_timer.wait_time = 0.12
	add_child(_timer)
	_timer.timeout.connect(func() -> void: changed.emit())
	notice = KIT.notice(HELD_TEXT, "Use nearest palette colours", "HeldColours")
	add_child(notice)
	(notice.get_meta("button") as Button).pressed.connect(use_nearest_palette)
	content = VBoxContainer.new()
	content.name = "Content"
	content.add_theme_constant_override("separation", 6)
	content.hide()
	add_child(content)
	skin_slider = SKIN_SLIDER.new()
	content.add_child(skin_slider)
	skin_slider.changed.connect(_on_skin)
	hair_row = HBoxContainer.new()
	hair_row.name = "HairStyleRow"
	content.add_child(hair_row)
	var hair_label := Label.new()
	hair_label.text = "Hair style"
	hair_label.custom_minimum_size.x = 88
	hair_row.add_child(hair_label)
	for group: String in GROUPS:
		var choice: COLOUR_CHOICE = COLOUR_CHOICE.new(group)
		content.add_child(choice)
		choices[group] = choice
		choice.changed.connect(_schedule)
		choice.toggled_open.connect(func(open: bool) -> void: _on_opened(group, open))


## The host's seven dropdowns ("skin", "hair" style, "hair_color", "eyes",
## "shirt", "pants", "boots") and the grid that lays them out in develop's
## form. Connects once; changes nothing visible.
func setup(pickers: Dictionary, grid: Control) -> void:
	_pickers = pickers
	_grid = grid
	for group: String in GROUPS:
		(choices[group] as COLOUR_CHOICE).bind(pickers[PICKER_KEYS[group]] as OptionButton)
	(pickers.hair as OptionButton).item_selected.connect(func(_index: int) -> void:
		_look["hair"] = AppearanceVariants.pack_hair((pickers.hair as OptionButton).get_selected_id(),
			(pickers.hair_color as OptionButton).get_selected_id())
		_refresh_context())
	(pickers.skin as OptionButton).item_selected.connect(func(_index: int) -> void: _update_notice())
	(pickers.skin as OptionButton).accessibility_name = "Skin"
	(pickers.hair as OptionButton).accessibility_name = "Hair style"


func enabled() -> bool:
	return _enabled


## Offers the slider and wheels (Human on a PC/3 server) or develop's palette
## dropdowns. Keeps every value either way.
func set_custom_colours_enabled(value: bool) -> void:
	if value == _enabled:
		_update_notice()
		return
	_enabled = value
	if value:
		_skin_to_slider()
		_homes.clear()
		var moved: Array = [_pickers.get("hair")]
		for group: String in GROUPS:
			moved.append(_pickers.get(PICKER_KEYS[group]))
		for picker: Variant in moved:
			if picker is OptionButton and (picker as Node).get_parent() != null:
				_homes.append([picker, (picker as Node).get_parent(), (picker as Node).get_index()])
		var hair := _pickers.get("hair") as OptionButton
		if hair != null:
			hair.reparent(hair_row, false)
			hair.size_flags_horizontal = Control.SIZE_EXPAND_FILL
		for group: String in GROUPS:
			(choices[group] as COLOUR_CHOICE).attach()
	else:
		for group: String in GROUPS:
			(choices[group] as COLOUR_CHOICE).set_open(false)
		# Back into develop's grid, each at its original place: in ascending
		# order every earlier sibling is already back.
		_homes.sort_custom(func(a: Array, b: Array) -> bool: return int(a[2]) < int(b[2]))
		for home: Array in _homes:
			var picker := home[0] as Node
			var parent := home[1] as Node
			if picker.get_parent() != parent:
				picker.reparent(parent, false)
			parent.move_child(picker, mini(int(home[2]), parent.get_child_count() - 1))
		_homes.clear()
	for group: String in GROUPS:
		(choices[group] as COLOUR_CHOICE).set_custom_enabled(value)
	content.visible = value
	if _grid != null:
		_grid.visible = not value
	_update_notice()


## The body: "female" or "male", with its model config when known.
func set_body(sex: String, model_config: Dictionary = {}) -> void:
	_sex = "male" if sex == "male" else "female"
	_model_config = model_config
	skin_slider.set_body(_sex, model_config)
	for group: String in GROUPS:
		(choices[group] as COLOUR_CHOICE).set_sex(_sex)
	# A custom hair colour keeps its apparent colour; the other body's palette
	# entries may be nearer, so the legacy byte follows.
	var hair := choices.hair as COLOUR_CHOICE
	if hair.is_custom():
		hair.set_wire(hair.wire(), true)


## Shows a saved look's colours. The host first selects its dropdowns from the
## look's palette bytes. A custom value the renderer would not draw (its
## nearest entry is not the saved byte) is dropped, as the renderer drops it.
func set_values(appearance: Dictionary) -> void:
	var values := PortraitCustomization.normalized(appearance)
	var skin := (_pickers.skin as OptionButton).get_selected_id() if _pickers.has("skin") else int(appearance.get("skin", 1))
	var tone := int(values.skin_tone)
	var undertone := int(values.skin_undertone)
	if skin >= 6 or skin < 0 or (tone >= 1 and COLOURS.nearest_skin_index(tone) != skin):
		tone = 0
		undertone = 0
	_skin_custom = {"tone": tone, "undertone": undertone, "id": skin}
	skin_slider.set_from(skin, tone, undertone)
	for group: String in GROUPS:
		(choices[group] as COLOUR_CHOICE).set_wire(COLOURS.triple(values, group))
	_look = appearance.duplicate()
	_update_notice()


## Applies a preset's concept colours (HumanPortraitPresets.COLOURS) after the
## host selected the preset's palette entries: only while custom colours are
## offered; otherwise the palette entries alone.
func apply_preset(colours: Dictionary) -> void:
	for group: String in GROUPS:
		(choices[group] as COLOUR_CHOICE).clear_custom()
	_skin_custom = {"tone": 0, "undertone": 0, "id": -1}
	if not _enabled or colours.is_empty():
		_sync_slider_from_palette()
		_update_notice()
		return
	_set_skin(int(colours.get("skin_tone", 0)), int(colours.get("skin_undertone", 0)))
	var triple := Vector3i(int(colours.get("hair_hue", 0)), int(colours.get("hair_sat", 0)),
		int(colours.get("hair_light", 0)))
	(choices.hair as COLOUR_CHOICE).set_wire(triple, true)
	_update_notice()


## Randomise (owner Q12): the host's palette draws stand; with custom colours
## offered, one uniform skin tone draw and one undertone draw near neutral
## (76..126, Neutral written 0). An Eloria tone from the palette draw is kept.
## Custom hair, eye and garment colours give way to the palette draws. Draws
## nothing while custom colours are not offered, so develop's seeded sequence
## is unchanged there.
func randomise(rng: RandomNumberGenerator) -> void:
	for group: String in GROUPS:
		(choices[group] as COLOUR_CHOICE).clear_custom()
	_skin_custom = {"tone": 0, "undertone": 0, "id": -1}
	if not _enabled:
		_sync_slider_from_palette()
		_update_notice()
		return
	var tone := rng.randi_range(1, 201)
	var undertone := rng.randi_range(76, 126)
	var skin := (_pickers.skin as OptionButton).get_selected_id()
	if skin >= 6:
		_sync_slider_from_palette()
	else:
		_set_skin(tone, 0 if undertone == SKIN_SLIDER.NEUTRAL else undertone)
	_update_notice()


## The look with this panel's fields: skin tone and undertone and the five
## colour triples, in saved form (AppearanceColours.canonical: snapped values
## become palette bytes, custom values write the nearest palette bytes).
func values(base: Dictionary) -> Dictionary:
	var result := base.duplicate()
	var skin := int(result.get("skin", 0))
	if int(_skin_custom.id) == skin and skin >= 0 and skin <= 5:
		result["skin_tone"] = int(_skin_custom.tone)
		result["skin_undertone"] = int(_skin_custom.undertone)
	else:
		result["skin_tone"] = 0
		result["skin_undertone"] = 0
	for group: String in GROUPS:
		var wire := (choices[group] as COLOUR_CHOICE).wire()
		var names: Array = PortraitCustomization.COLOUR_TRIPLES[group]
		result[names[0]] = wire.x
		result[names[1]] = wire.y
		result[names[2]] = wire.z
	return COLOURS.canonical(result, _sex)


## True while any custom colour (or slider skin) is held.
func has_custom() -> bool:
	var skin := (_pickers.skin as OptionButton).get_selected_id() if _pickers.has("skin") else -1
	if int(_skin_custom.id) == skin and (int(_skin_custom.undertone) != 0
			or (int(_skin_custom.tone) >= 1 and int(_skin_custom.tone) != COLOURS.skin_position(skin))):
		return true
	for group: String in GROUPS:
		if (choices[group] as COLOUR_CHOICE).is_custom():
			return true
	return false


## The notice's button: every custom colour becomes its nearest palette entry
## (the bytes the dropdowns already show).
func use_nearest_palette() -> void:
	for group: String in GROUPS:
		(choices[group] as COLOUR_CHOICE).clear_custom()
	_skin_custom = {"tone": 0, "undertone": 0, "id": -1}
	_sync_slider_from_palette()
	_update_notice()
	changed.emit()


## The host's current look and model, for the wheels' indications.
func update_context(look: Dictionary, model_config: Dictionary = {}) -> void:
	_look = look.duplicate()
	if not model_config.is_empty():
		_model_config = model_config
	_refresh_context()


func close_wheels() -> void:
	for group: String in GROUPS:
		(choices[group] as COLOUR_CHOICE).set_open(false)


func _refresh_context() -> void:
	for group: String in GROUPS:
		(choices[group] as COLOUR_CHOICE).set_context(_look, _model_config)


func _schedule() -> void:
	_update_notice()
	_timer.start()


func _on_skin() -> void:
	var value := skin_slider.values()
	_select(_pickers.skin as OptionButton, int(value.skin))
	_skin_custom = {"tone": int(value.skin_tone), "undertone": int(value.skin_undertone), "id": int(value.skin)}
	_look.merge(value, true)
	_refresh_context()
	_schedule()


func _set_skin(tone: int, undertone: int) -> void:
	var skin := COLOURS.nearest_skin_index(tone)
	_select(_pickers.skin as OptionButton, skin)
	_skin_custom = {"tone": tone, "undertone": undertone, "id": skin}
	skin_slider.set_from(skin, tone, undertone)


## Opening the colour layout: the slider shows the skin the dropdown holds.
func _skin_to_slider() -> void:
	var skin := (_pickers.skin as OptionButton).get_selected_id()
	if int(_skin_custom.id) == skin:
		skin_slider.set_from(skin, int(_skin_custom.tone), int(_skin_custom.undertone))
	else:
		skin_slider.set_from(skin, 0, 0)


func _sync_slider_from_palette() -> void:
	if _pickers.has("skin"):
		skin_slider.set_from((_pickers.skin as OptionButton).get_selected_id(), 0, 0)


func _select(picker: OptionButton, id: int) -> void:
	var item := picker.get_item_index(id)
	if item >= 0:
		picker.select(item)


func _on_opened(group: String, open: bool) -> void:
	if open:
		# One wheel at a time.
		for other: String in GROUPS:
			if other != group:
				(choices[other] as COLOUR_CHOICE).set_open(false)
		(choices[group] as COLOUR_CHOICE).set_context(_look, _model_config)
	if group == "eyes":
		face_focus.emit(open)


func _update_notice() -> void:
	notice.visible = not _enabled and has_custom()
