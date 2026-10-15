extends Control
## One active decoder, a still fallback, and a saved choice for the entry screen.

signal backdrop_changed(backdrop_id: String)

const SETTINGS_PATH := "user://eloria_hud.cfg"
const ASSET_ROOT := "res://assets/ui/start_screen/"
const BACKDROPS: Array[Dictionary] = [
	{"id": "oldcraft_landfall", "label": "Oldcraft · Landfall", "file": "06-oldcraft-landfall"},
	{"id": "crownwater", "label": "Crownwater · First Light", "file": "01-crownwater-first-light"},
	{"id": "amberwood", "label": "Amberwood · Lantern Path", "file": "02-amberwood-lantern-path"},
	{"id": "whitehorn", "label": "Whitehorn · Silent Ascent", "file": "03-whitehorn-silent-ascent"},
	{"id": "sunmane", "label": "Sunmane · Golden Horizon", "file": "04-sunmane-golden-horizon"},
	{"id": "amethyst", "label": "Amethyst Barrens · Starwatch", "file": "05-amethyst-barrens-starwatch"},
]

var selected_id := "oldcraft_landfall"
var animation_enabled := true
var settings_path := SETTINGS_PATH
var selector: OptionButton
var animation_toggle: CheckBox
var video: VideoStreamPlayer
var poster: TextureRect
var _active := false


func _ready() -> void:
	name = "StartScreenBackdrop"
	mouse_filter = Control.MOUSE_FILTER_IGNORE
	clip_contents = true
	set_anchors_and_offsets_preset(Control.PRESET_FULL_RECT)
	poster = TextureRect.new()
	poster.name = "Still"
	poster.mouse_filter = Control.MOUSE_FILTER_IGNORE
	poster.expand_mode = TextureRect.EXPAND_IGNORE_SIZE
	poster.stretch_mode = TextureRect.STRETCH_KEEP_ASPECT_COVERED
	add_child(poster)
	poster.set_anchors_and_offsets_preset(Control.PRESET_FULL_RECT)
	video = VideoStreamPlayer.new()
	video.name = "Animation"
	video.expand = true
	video.loop = true
	video.volume_db = -80.0
	video.mouse_filter = Control.MOUSE_FILTER_IGNORE
	add_child(video)
	resized.connect(_fit_video)
	_fit_video()
	_build_selector()
	var config := ConfigFile.new()
	var migrated := false
	if config.load(settings_path) == OK:
		var saved: Variant = config.get_value("start_screen", "backdrop", selected_id)
		if saved == "oldcraft_waygate":
			saved = "oldcraft_landfall"
			migrated = true
		if saved is String and _index_of(saved) >= 0:
			selected_id = saved
		var motion: Variant = config.get_value("start_screen", "animated", true)
		animation_enabled = motion if motion is bool else true
	animation_toggle.set_pressed_no_signal(animation_enabled)
	_select(selected_id, false)
	if migrated:
		_save_preferences()


func _build_selector() -> void:
	var panel := PanelContainer.new()
	panel.name = "BackdropPicker"
	panel.set_anchors_and_offsets_preset(Control.PRESET_BOTTOM_LEFT)
	panel.anchor_left = 0.77
	panel.anchor_right = 0.77
	panel.offset_left = -180
	panel.offset_right = 180
	panel.offset_top = -96
	panel.offset_bottom = -20
	var frame := StyleBoxFlat.new()
	frame.bg_color = Color(0.025, 0.028, 0.037, 0.82)
	frame.border_color = Color(0.722, 0.541, 0.231, 0.72)
	frame.set_border_width_all(1)
	frame.set_corner_radius_all(8)
	frame.content_margin_left = 12
	frame.content_margin_right = 12
	frame.content_margin_top = 8
	frame.content_margin_bottom = 8
	panel.add_theme_stylebox_override("panel", frame)
	add_child(panel)
	var column := VBoxContainer.new()
	column.add_theme_constant_override("separation", 3)
	panel.add_child(column)
	var header := HBoxContainer.new()
	column.add_child(header)
	var label := Label.new()
	label.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	label.text = "Start screen"
	label.add_theme_color_override("font_color", Color(0.83, 0.75, 0.60))
	label.add_theme_font_size_override("font_size", 12)
	header.add_child(label)
	animation_toggle = CheckBox.new()
	animation_toggle.name = "AnimateBackdrop"
	animation_toggle.text = "Animate"
	animation_toggle.tooltip_text = "Play this scene on every graphics quality. Turn off for a still background."
	animation_toggle.add_theme_font_size_override("font_size", 12)
	animation_toggle.add_theme_color_override("font_color", Color(0.96, 0.90, 0.76))
	header.add_child(animation_toggle)
	animation_toggle.toggled.connect(set_animation_enabled)
	selector = OptionButton.new()
	selector.name = "BackdropChoice"
	selector.custom_minimum_size.y = 30
	selector.tooltip_text = "Choose your start-screen scene. Your choice is saved on this device."
	selector.add_theme_color_override("font_color", Color(0.96, 0.90, 0.76))
	selector.add_theme_font_size_override("font_size", 14)
	var field := frame.duplicate() as StyleBoxFlat
	field.bg_color = Color(0.075, 0.079, 0.091, 0.94)
	field.content_margin_top = 4
	field.content_margin_bottom = 4
	for state: String in ["normal", "hover", "pressed", "focus"]:
		selector.add_theme_stylebox_override(state, field)
	for entry: Dictionary in BACKDROPS:
		selector.add_item(entry.label)
	column.add_child(selector)
	var popup := selector.get_popup()
	var popup_frame := frame.duplicate() as StyleBoxFlat
	popup_frame.bg_color = Color(0.025, 0.028, 0.037, 0.97)
	popup.add_theme_stylebox_override("panel", popup_frame)
	popup.add_theme_color_override("font_color", Color(0.96, 0.90, 0.76))
	popup.add_theme_color_override("font_hover_color", Color(1.0, 0.82, 0.35))
	popup.add_theme_font_size_override("font_size", 14)
	var hover := StyleBoxFlat.new()
	hover.bg_color = Color(0.30, 0.22, 0.08, 0.85)
	hover.set_corner_radius_all(4)
	popup.add_theme_stylebox_override("hover", hover)
	selector.item_selected.connect(_on_selected)


func _fit_video() -> void:
	if video == null:
		return
	# VideoStreamPlayer stretches; crop its 16:9 rectangle to cover any viewport.
	var width := maxf(size.x, size.y * 16.0 / 9.0)
	video.size = Vector2(width, width * 9.0 / 16.0)
	video.position = (size - video.size) * 0.5


func _index_of(backdrop_id: String) -> int:
	for index: int in BACKDROPS.size():
		if BACKDROPS[index].id == backdrop_id:
			return index
	return -1


func _on_selected(index: int) -> void:
	_select(BACKDROPS[index].id, true)


func select_backdrop(backdrop_id: String) -> void:
	if _index_of(backdrop_id) >= 0:
		_select(backdrop_id, true)


func _select(backdrop_id: String, persist: bool) -> void:
	selected_id = backdrop_id
	var index := _index_of(backdrop_id)
	selector.select(index)
	video.stop()
	video.stream = null
	var path: String = ASSET_ROOT + BACKDROPS[index].file
	# Imported textures also resolve correctly from an exported game pack.
	var poster_path := path + "-poster.jpg"
	if ResourceLoader.exists(poster_path):
		poster.texture = load(poster_path) as Texture2D
	else:
		var image := Image.load_from_file(poster_path)
		poster.texture = ImageTexture.create_from_image(image) if image != null else null
	_update_playback()
	if persist:
		_save_preferences()
		backdrop_changed.emit(selected_id)


func set_active(value: bool) -> void:
	_active = value
	visible = value
	_update_playback()


func set_animation_enabled(value: bool) -> void:
	animation_enabled = value
	animation_toggle.set_pressed_no_signal(value)
	_update_playback()
	_save_preferences()


func _save_preferences() -> void:
	var config := ConfigFile.new()
	config.load(settings_path)
	config.set_value("start_screen", "backdrop", selected_id)
	config.set_value("start_screen", "animated", animation_enabled)
	var error := config.save(settings_path)
	if error != OK:
		push_warning("Could not save the start-screen choice: %s" % error_string(error))


func _update_playback() -> void:
	if video == null:
		return
	if not _active or not animation_enabled:
		video.stop()
		video.stream = null
		video.hide()
		return
	if video.stream == null:
		var path: String = ASSET_ROOT + BACKDROPS[_index_of(selected_id)].file + ".ogv"
		if not ResourceLoader.exists(path):
			push_warning("Start-screen animation is missing: " + path)
			video.hide()
			return
		video.stream = load(path) as VideoStream
		if video.stream == null:
			push_warning("Could not load the start-screen animation: " + path)
			video.hide()
			return
	video.show()
	if not video.is_playing():
		video.play()
