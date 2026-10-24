extends Control
## Brief, click-through messages at a dismissed feed's saved position.
const HOLD_SECONDS := 4.0
const FADE_SECONDS := 2.0
const RISE_PIXELS := 30.0
const MAX_MESSAGES := 6
var source: Control
var _entries: Array[Dictionary] = []

func _init() -> void:
	mouse_filter = Control.MOUSE_FILTER_IGNORE
	clip_contents = true
	hide()
	set_process(false)

func add_message(text: String, colour: Color, segments: Array[Dictionary] = []) -> void:
	if text.is_empty():
		return
	_sync_layout()
	var label: Control
	if segments.size() > 1:
		var rich := RichTextLabel.new()
		rich.fit_content = true
		rich.scroll_active = false
		rich.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
		for segment: Dictionary in segments:
			rich.push_color(segment.color)
			rich.add_text(str(segment.text))
			rich.pop()
		label = rich
	else:
		var plain := Label.new()
		plain.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
		plain.text = str(segments[0].text) if segments.size() == 1 else text
		if segments.size() == 1:
			colour = segments[0].color
		label = plain
	# Establish the wrap width before text can create a tall minimum at width zero.
	label.size.x = size.x
	label.mouse_filter = Control.MOUSE_FILTER_IGNORE
	label.add_theme_color_override("font_color", colour)
	label.add_theme_color_override("default_color", colour)
	label.add_theme_color_override("font_outline_color", Color(0, 0, 0, 0.9))
	label.add_theme_constant_override("outline_size", 2)
	add_child(label)
	label.position.y = size.y
	if not _entries.is_empty():
		var previous: Control = _entries.back().label
		label.position.y = maxf(label.position.y,
			previous.position.y + previous.size.y + float(source.options.line_spacing) + 2.0)
	_entries.append({"label": label, "age": 0.0})
	while _entries.size() > MAX_MESSAGES:
		_remove_entry(0)
	refresh_style()
	_layout_messages(0.0)
	show()
	set_process(true)

func refresh_style() -> void:
	for entry: Dictionary in _entries:
		var label: Control = entry.label
		label.add_theme_font_override("font", source.output.get_theme_font("normal_font"))
		label.add_theme_font_override("normal_font", source.output.get_theme_font("normal_font"))
		label.add_theme_font_size_override("font_size", int(source.options.font_size))
		label.add_theme_font_size_override("normal_font_size", int(source.options.font_size))
		label.add_theme_constant_override("line_spacing", int(source.options.line_spacing))
		label.add_theme_constant_override("line_separation", int(source.options.line_spacing))

func clear_messages() -> void:
	while not _entries.is_empty():
		_remove_entry(_entries.size() - 1)
	hide()
	set_process(false)

func _remove_entry(index: int) -> void:
	var label: Control = _entries[index].label
	remove_child(label)
	label.queue_free()
	_entries.remove_at(index)

func _process(delta: float) -> void:
	for index in range(_entries.size() - 1, -1, -1):
		_entries[index].age += delta
		if float(_entries[index].age) >= HOLD_SECONDS + FADE_SECONDS:
			_remove_entry(index)
	if _entries.is_empty():
		clear_messages()
		return
	_sync_layout()
	_layout_messages(delta)

func _sync_layout() -> void:
	position = source.position + Vector2(6, 6)
	size = (source.size - Vector2(12, 12)).max(Vector2.ONE)
	scale = source.scale
	z_index = source.z_index

func _layout_messages(delta: float) -> void:
	var bottom := size.y
	for index in range(_entries.size() - 1, -1, -1):
		var entry := _entries[index]
		var label: Control = entry.label
		var age := float(entry.age)
		label.size = Vector2(size.x, 0)
		var target := minf(bottom - label.size.y,
			size.y - label.size.y - RISE_PIXELS * age / (HOLD_SECONDS + FADE_SECONDS))
		label.position.y = lerpf(label.position.y, target, 1.0 - exp(-12.0 * delta))
		label.modulate.a = 1.0 - clampf((age - HOLD_SECONDS) / FADE_SECONDS, 0.0, 1.0)
		bottom = target - float(source.options.line_spacing) - 2.0
