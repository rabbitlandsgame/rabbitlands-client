extends ItemList
## A second line keeps the exact backpack slot visible when a long name is clipped.
func _draw() -> void:
	var notes: Dictionary = get_meta("copy_notes", {})
	var font := get_theme_font("font")
	for index: int in item_count:
		var identity: Variant = get_item_metadata(index)
		if not identity is int or not notes.has(identity): continue
		var rect := get_item_rect(index, false)
		rect.position -= Vector2(get_h_scroll_bar().value, get_v_scroll_bar().value)
		if rect.size.x <= 0 or rect.size.y <= 0: continue
		if not rect.intersects(Rect2(Vector2.ZERO, size)): continue
		var baseline := rect.end.y - 7
		if baseline < 14 or baseline > size.y - 8: continue
		draw_string(font, Vector2(rect.position.x + 50, baseline), str(notes[identity]), HORIZONTAL_ALIGNMENT_LEFT, maxf(0, size.x - 62), 12, Color("b5b9ac"))
