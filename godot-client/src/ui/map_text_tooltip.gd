extends TextureRect
## The map still owns mouse input. Its hover labels use each mark's text
## color while the ordinary application tooltip keeps the shared UI color.
var _last_label: WeakRef
var tooltip_text_color := Color.WHITE:
	set(value):
		tooltip_text_color = value
		if _last_label != null:
			var label: Label = _last_label.get_ref()
			if label != null:
				label.add_theme_color_override("font_color", value)

func _make_custom_tooltip(for_text: String) -> Object:
	var label := Label.new()
	label.text = for_text
	label.add_theme_color_override("font_color", tooltip_text_color)
	_last_label = weakref(label)
	return label
