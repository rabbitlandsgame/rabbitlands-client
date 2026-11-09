extends RefCounted
## Tracked destinations keep a readable size and name at every map zoom.
const GLYPH_SIZE := 32
const MINIMAP_GLYPH_SIZE := 27
const RADIUS := 10.0
const OUTLINE := Color(0.03, 0.035, 0.045, 0.98)
const BACKGROUND := Color(0.035, 0.055, 0.07, 0.9)
const EntranceLabels := preload("res://src/ui/entrance_map_overlay.gd")

static func draw_icon(canvas: Control, point: Vector2, colour: Color, glyph_size: int) -> void:
	var font := canvas.get_theme_default_font()
	if font == null:return
	var extent := font.get_string_size("!", HORIZONTAL_ALIGNMENT_LEFT, -1, glyph_size)
	var baseline := point + Vector2(-extent.x*0.5, (font.get_ascent(glyph_size)-font.get_descent(glyph_size))*0.5)
	canvas.draw_string_outline(font, baseline, "!", HORIZONTAL_ALIGNMENT_LEFT, -1, glyph_size, 5, OUTLINE)
	canvas.draw_string(font, baseline, "!", HORIZONTAL_ALIGNMENT_LEFT, -1, glyph_size, colour)

static func draw_label(canvas: Control, point: Vector2, label: String, colour: Color,
		glyph_size: int, compact := false, round_mask := false, avoid: Array[Rect2] = []) -> Rect2:
	var font := canvas.get_theme_default_font()
	if font == null or label.is_empty():return Rect2()
	var font_size := 13 if compact else 15
	var bounds := Rect2(Vector2(4,4), canvas.size-Vector2(8,8))
	if round_mask:
		# An inset square keeps all four label corners inside the round mask.
		var side := maxf(1.0, minf(canvas.size.x, canvas.size.y)*sqrt(0.5)-10.0)
		bounds = Rect2((canvas.size-Vector2.ONE*side)*0.5, Vector2.ONE*side)
	var lines := EntranceLabels.label_lines(font, label, font_size, minf(180.0,bounds.size.x-12.0))
	var width := 0.0
	for line: String in lines:
		width = maxf(width, font.get_string_size(line, HORIZONTAL_ALIGNMENT_LEFT, -1, font_size).x)
	var line_height := font.get_height(font_size)
	var extent := Vector2(width+12.0, line_height*lines.size()+6.0)
	var gap := float(glyph_size)*0.5+5.0
	var candidates: Array[Vector2] = [point+Vector2(gap,-extent.y*0.5),
		point-Vector2(gap+extent.x,extent.y*0.5), point+Vector2(-extent.x*0.5,gap),
		point-Vector2(extent.x*0.5,gap+extent.y), point+Vector2(gap,gap+extent.y),
		point-Vector2(gap+extent.x,gap+extent.y*2)]
	var rect := Rect2()
	var best_score := INF
	for at: Vector2 in candidates:
		at.x = clampf(at.x,bounds.position.x,maxf(bounds.position.x,bounds.end.x-extent.x))
		at.y = clampf(at.y,bounds.position.y,maxf(bounds.position.y,bounds.end.y-extent.y))
		var candidate := Rect2(at,extent)
		var score := 0.0
		for occupied: Rect2 in avoid:
			if candidate.intersects(occupied):score += candidate.intersection(occupied).get_area()
		if score < best_score:
			rect = candidate
			best_score = score
		if is_zero_approx(score):break
	var nearest := Vector2(clampf(point.x,rect.position.x,rect.end.x),clampf(point.y,rect.position.y,rect.end.y))
	if point.distance_to(nearest)>gap+2.0:
		var start := point+point.direction_to(nearest)*gap
		canvas.draw_line(start,nearest,OUTLINE,3.0,true)
		canvas.draw_line(start,nearest,colour,1.0,true)
	var plaque := StyleBoxFlat.new()
	plaque.bg_color = BACKGROUND
	plaque.corner_radius_top_left = 3
	plaque.corner_radius_top_right = 3
	plaque.corner_radius_bottom_left = 3
	plaque.corner_radius_bottom_right = 3
	canvas.draw_style_box(plaque,rect)
	var baseline := rect.position+Vector2(6,3+font.get_ascent(font_size))
	for line: String in lines:
		canvas.draw_string_outline(font,baseline,line,HORIZONTAL_ALIGNMENT_LEFT,-1,font_size,3,OUTLINE)
		canvas.draw_string(font,baseline,line,HORIZONTAL_ALIGNMENT_LEFT,-1,font_size,colour)
		baseline.y += line_height
	return rect
