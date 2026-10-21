extends Control
## Alternate presentation; the original live meters remain the data owners.
const Values := preload("res://src/ui/hud_resource_values.gd")
const Icons := preload("res://src/ui/hud_resource_icons.gd")
const Presets := preload("res://src/ui/hud_presets.gd")
var source: Control
var config: Dictionary = {}
var _signature: Array = []
var keys: Array[String] = []
var palette: Dictionary = {}

func _ready() -> void:
	custom_minimum_size = Vector2(84, 16)
	mouse_filter = Control.MOUSE_FILTER_PASS
	resized.connect(queue_redraw)

func configure(owner_main: Control, value: Dictionary, colors: Dictionary = {}) -> void:
	source = owner_main
	config = value.duplicate(true)
	palette = Presets.RESOURCE_COLORS.duplicate()
	palette.merge(colors, true)
	keys.clear()
	if not config.get("meter_keys", []).is_empty(): keys.assign(config.meter_keys)
	else:
		for key: String in source._hud_meter_order:
			if bool(source._hud_meter_visible.get(key, true)): keys.append(key)
	var rows := int(config.rows) if config.orientation == "horizontal" else maxi(1, keys.size())
	size = Vector2(600 if config.orientation == "horizontal" else 260, rows * (46 if config.show_labels and config.show_values else 30) + 12)
	_signature.clear()
	queue_redraw()

func geometry(requested: Vector2) -> Dictionary:
	var width := maxf(84, requested.x)
	var count := maxi(1, keys.size())
	var rows := clampi(int(config.get("rows", 1)), 1, count) if config.get("orientation") == "horizontal" else count
	# Reflow narrow strips before labels or icons can crowd out another meter.
	var min_cell := 96.0 if config.get("show_icons", false) else 68.0
	rows = maxi(rows, ceili(float(count) / maxi(1, floori((width - 16) / min_cell))))
	var columns := ceili(float(count) / rows)
	var content_width := (width - 16) / columns - (30 if config.get("show_icons", false) else 0)
	var stacked: bool = config.show_labels and config.show_values and content_width < 112
	var bar_y := 31.0 if stacked else (18.0 if config.show_labels or config.show_values else 5.0)
	var row_height := maxf(bar_y + 9, 28 if config.get("show_icons", false) else 0)
	var height := maxf(requested.y, rows * row_height + 12)
	return {"size":Vector2(width, height), "rows":rows, "columns":columns,
		"cell":Vector2((width - 16) / columns, (height - 12) / rows), "stacked":stacked, "bar_y":bar_y, "content_height":row_height}

func fitted_size(requested: Vector2) -> Vector2:
	return geometry(requested).size

func meter_rects() -> Array[Rect2]:
	var result: Array[Rect2] = []
	var grid := geometry(size)
	for index: int in keys.size():
		var row_index := index / int(grid.columns)
		var row_count := mini(grid.columns, keys.size() - row_index * int(grid.columns))
		var origin: Vector2 = Vector2(8 + (grid.columns - row_count) * grid.cell.x / 2, 6) + Vector2(index % int(grid.columns), row_index) * grid.cell
		result.append(Rect2(origin, Vector2(grid.cell.x - 8, grid.cell.y)))
	return result

func _process(_delta: float) -> void:
	if source == null or config.is_empty(): return
	var signature: Array = []
	var lines: Array[String] = []
	for key: String in keys:
		var bar := _bar(key)
		if bar == null: continue
		var values := _values(key, bar)
		signature.append(values)
		lines.append(_caption(key) + ": %d / %d" % [values.x, values.y])
	if signature != _signature:
		_signature = signature
		tooltip_text = "\n".join(lines)
		queue_redraw()

func _caption(key: String) -> String:
	if key == "load" and config.get("load_display") == "carried": return "Load"
	return {"mana":"Ether", "food":"Food", "health":"Health", "load":"Free load", "action":"Action", "experience":"XP"}.get(key, key)

func _values(key: String, bar: ProgressBar) -> Vector2:
	if key == "load" and config.get("load_display") == "carried":
		var data := Values.read("load")
		return Vector2(data.value, data.maximum)
	return Vector2(bar.value, bar.max_value)

func _bar(key: String) -> ProgressBar:
	for child: Node in source._meter_node(key).get_children():
		if child is ProgressBar: return child
	return null

func _draw() -> void:
	if source == null or config.is_empty() or keys.is_empty(): return
	var box := StyleBoxFlat.new()
	box.bg_color = config.background_color
	box.border_color = config.border_color
	box.set_border_width_all(1)
	box.set_corner_radius_all(3)
	if not config.get("show_background", config.get("frame_style") != "floating"): box.bg_color.a = 0
	if not config.get("show_border", config.get("frame_style") != "floating"): box.set_border_width_all(0)
	if not has_node("_HudChrome"): draw_style_box(box, Rect2(Vector2.ZERO, size))
	var grid := geometry(size)
	var cell: Vector2 = grid.cell
	var rects := meter_rects()
	var font := ThemeDB.fallback_font
	for index: int in keys.size():
		var key := keys[index]
		var bar := _bar(key)
		if bar == null: continue
		var values := _values(key, bar)
		var origin: Vector2 = rects[index].position
		origin.y += maxf(0, (cell.y - grid.content_height) / 2)
		var icon_width := 0.0
		if config.get("show_icons", false):
			var icon := Icons.tinted_icon(key, palette.get(key, Color.WHITE))
			if icon != null:
				var icon_size := minf(24, maxf(12, grid.content_height - 4))
				draw_texture_rect(icon, Rect2(origin + Vector2(0, maxf(0, (grid.content_height - icon_size) / 2)), Vector2.ONE * icon_size), false)
				icon_width = icon_size + 6
		origin.x += icon_width
		var content_width := cell.x - icon_width
		var stack_text: bool = grid.stacked
		if config.show_labels: draw_string(font, origin + Vector2(0, 12), _caption(key), HORIZONTAL_ALIGNMENT_LEFT, content_width - 8, 11, config.text_color)
		if config.show_values:
			draw_string(font, origin + Vector2(0, 25 if stack_text else 12), "%d / %d" % [values.x, values.y], HORIZONTAL_ALIGNMENT_RIGHT, content_width - 8, 10, config.text_color)
		var bar_y: float = grid.bar_y
		var rect := Rect2(origin + Vector2(0, bar_y), Vector2(maxf(2, content_width - 8), 7))
		draw_rect(rect, Color("101413"))
		var color: Color = palette.get(key, Color("65b873"))
		var fill := rect
		fill.size.x *= clampf(values.x / maxf(1, values.y), 0, 1)
		draw_rect(fill, color)
		draw_rect(rect, config.border_color, false, 1)
