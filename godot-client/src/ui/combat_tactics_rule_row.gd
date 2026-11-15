extends Button
## One selectable summary. Dragging reorders this editor's draft only.
signal reorder_requested(source: int, destination: int)
signal enabled_changed(enabled: bool)
const Style := preload("res://src/ui/combat_tactics_style.gd")
var index := 0
var editor_id := 0
var enabled_toggle: CheckBox
var summary_label: Label

class RuleGlyph extends Control:
	var kind := "attack"
	func _draw() -> void:
		var color := Color("f0e4c8")
		var c := size / 2.0
		match kind:
			"heal":
				draw_circle(c + Vector2(-4, -3), 5, color)
				draw_circle(c + Vector2(4, -3), 5, color)
				draw_colored_polygon(PackedVector2Array([c + Vector2(-9, -2), c + Vector2(9, -2), c + Vector2(0, 9)]), color)
			"shield":
				draw_polyline(PackedVector2Array([c + Vector2(0, -9), c + Vector2(8, -6), c + Vector2(6, 4), c + Vector2(0, 9), c + Vector2(-6, 4), c + Vector2(-8, -6), c + Vector2(0, -9)]), color, 2, true)
			"dispel":
				for offset: Vector2 in [Vector2(-4, -3), Vector2(5, 4)]:
					draw_line(c + offset + Vector2(-4, 0), c + offset + Vector2(4, 0), color, 2, true)
					draw_line(c + offset + Vector2(0, -4), c + offset + Vector2(0, 4), color, 2, true)
			"target":
				draw_arc(c, 7, 0, TAU, 32, color, 2, true)
				draw_line(c + Vector2(-10, 0), c + Vector2(10, 0), color, 1, true)
				draw_line(c + Vector2(0, -10), c + Vector2(0, 10), color, 1, true)
			_:
				for direction: int in [-1, 1]:
					draw_line(c + Vector2(-7 * direction, 7), c + Vector2(7 * direction, -7), color, 2, true)
					draw_line(c + Vector2(-7 * direction, 2), c + Vector2(-2 * direction, 7), color, 2, true)

class Grip extends Control:
	func _draw() -> void:
		for x: int in [4, 10]:
			for y: int in [8, 14, 20]: draw_circle(Vector2(x, y), 1.5, Color("baad94"))

func configure(number: int, owner_id: int, summary: String, enabled: bool, glyph: String, selected: bool, compact := false) -> void:
	index = number
	editor_id = owner_id
	toggle_mode = true
	set_pressed_no_signal(selected)
	custom_minimum_size.y = 28 if compact else 38
	size_flags_horizontal = Control.SIZE_EXPAND_FILL
	add_theme_stylebox_override("normal", Style.surface(Color("1c1b15"), Style.EDGE, 5, 0))
	add_theme_stylebox_override("hover", Style.surface(Color("2b2d1e"), Style.BRASS, 5, 0))
	add_theme_stylebox_override("pressed", Style.surface(Style.MOSS, Style.GOLD, 5, 0))
	add_theme_stylebox_override("hover_pressed", Style.surface(Color("465528"), Style.GOLD, 5, 0))
	var content := HBoxContainer.new()
	content.set_anchors_and_offsets_preset(Control.PRESET_FULL_RECT)
	content.offset_left = 8; content.offset_right = -8
	content.add_theme_constant_override("separation", 8)
	content.mouse_filter = Control.MOUSE_FILTER_IGNORE
	add_child(content)
	var grip := Grip.new()
	grip.custom_minimum_size = Vector2(14, 28)
	grip.size_flags_vertical = Control.SIZE_SHRINK_CENTER
	grip.mouse_filter = Control.MOUSE_FILTER_IGNORE
	content.add_child(grip)
	enabled_toggle = CheckBox.new()
	enabled_toggle.name = "Enabled"
	enabled_toggle.button_pressed = enabled
	enabled_toggle.tooltip_text = "Enable rule %d" % (number + 1)
	enabled_toggle.toggled.connect(func(value: bool) -> void: enabled_changed.emit(value))
	content.add_child(enabled_toggle)
	var priority := Style.label(str(number + 1), 15)
	priority.custom_minimum_size.x = 14
	priority.mouse_filter = Control.MOUSE_FILTER_IGNORE
	content.add_child(priority)
	var icon := RuleGlyph.new()
	icon.kind = glyph
	icon.custom_minimum_size = Vector2(22, 22)
	icon.size_flags_vertical = Control.SIZE_SHRINK_CENTER
	icon.mouse_filter = Control.MOUSE_FILTER_IGNORE
	content.add_child(icon)
	summary_label = Style.label(summary, 13 if compact else 15)
	summary_label.text_overrun_behavior = TextServer.OVERRUN_TRIM_ELLIPSIS
	summary_label.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	summary_label.mouse_filter = Control.MOUSE_FILTER_IGNORE
	content.add_child(summary_label)
	tooltip_text = summary + "\nSelect to edit · Drag to reorder"
	if not enabled: summary_label.modulate.a = 0.55

func _get_drag_data(_position: Vector2) -> Variant:
	var preview := Style.label("%d   %s" % [index + 1, summary_label.text])
	set_drag_preview(preview)
	return {"tactics_editor": editor_id, "index": index}

func _can_drop_data(_position: Vector2, data: Variant) -> bool:
	return data is Dictionary and data.get("tactics_editor") == editor_id and data.get("index") is int and data.index != index

func _drop_data(_position: Vector2, data: Variant) -> void:
	if _can_drop_data(_position, data): reorder_requested.emit(int(data.index), index)
