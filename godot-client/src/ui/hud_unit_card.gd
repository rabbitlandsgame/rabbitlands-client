extends Control
## Small live player/target card. No copied loadout, actor or gameplay state.
const Values := preload("res://src/ui/hud_resource_values.gd")
const Icons := preload("res://src/ui/hud_resource_icons.gd")
const Presets := preload("res://src/ui/hud_presets.gd")
var source: Control
var config: Dictionary = {}
var role := "player"
var _signature: Array = []
var palette: Dictionary = {}

func _ready() -> void:
	custom_minimum_size = Vector2(210, 66)
	mouse_filter = Control.MOUSE_FILTER_IGNORE
	resized.connect(queue_redraw)

func configure(owner_main: Control, value: Dictionary, colors: Dictionary = {}) -> void:
	source = owner_main
	config = value.duplicate(true)
	palette = Presets.RESOURCE_COLORS.duplicate()
	palette.merge(colors, true)
	custom_minimum_size.y = 156 if config.get("show_player_details", false) else 66
	size = Vector2(290, 108) if role == "player" else Vector2(280, 68)
	queue_redraw()

func _data() -> Dictionary:
	var id: int = AppState.local_actor_id if role == "player" else AppState.selected_actor_id
	var actor: Dictionary = AppState.actors.get(id, {})
	var stats: Dictionary = AppState.stats if role == "player" else actor
	var leader := false
	if role == "player":
		for member: Dictionary in AppState.party.get("members", []):
			if member.get("is_self", false): leader = member.get("leader", false)
	return {"name":str(actor.get("name", "Player" if role == "player" else "Target")),
		"leader":leader,
		"health":float(stats.get("health", 0)), "max_health":maxf(1, float(stats.get("max_health", 1))),
		"ether":float(stats.get("ether", 0)), "max_ether":maxf(1, float(stats.get("max_ether", 1))), "available":role == "player" or not actor.is_empty()}

func _process(_delta: float) -> void:
	if source == null: return
	var signature: Array = [_data(), Values.read("food"), Values.read("load"), Values.read("action")]
	if signature != _signature:
		_signature = signature
		queue_redraw()

func _draw() -> void:
	if config.is_empty(): return
	var data := _data()
	if not data.available: return
	var box := StyleBoxFlat.new()
	box.bg_color = config.background_color
	box.border_color = config.border_color
	box.set_border_width_all(1)
	box.set_corner_radius_all(5)
	if not config.get("show_background", true): box.bg_color.a = 0
	if not config.get("show_border", true): box.set_border_width_all(0)
	if not has_node("_HudChrome"): draw_style_box(box, Rect2(Vector2.ZERO, size))
	var font := ThemeDB.fallback_font
	var text: Color = config.text_color
	if role == "player" and config.get("show_player_details", false):
		_detailed_player(data, font, text)
		return
	var center := Vector2(32, 33)
	draw_circle(center, 23, config.background_color.darkened(0.3))
	draw_arc(center, 23, 0, TAU, 48, config.border_color, 2, true)
	draw_string(font, Vector2(9, 39), data.name.left(2).to_upper(), HORIZONTAL_ALIGNMENT_CENTER, 46, 15, text)
	draw_string(font, Vector2(65, 21), data.name, HORIZONTAL_ALIGNMENT_LEFT, size.x - 76, 14, text)
	_meter(Rect2(65, 29, size.x - 78, 8), data.health, data.max_health, palette.health)
	_meter(Rect2(65, 44, size.x - 78, 6), data.ether, data.max_ether, palette.mana)
	if config.show_values:
		draw_string(font, Vector2(65, 26), "%d / %d" % [data.health, data.max_health], HORIZONTAL_ALIGNMENT_RIGHT, size.x - 78, 10, text)
	if role == "player" and config.show_secondary:
		for index: int in 3:
			var key: String = ["food", "load", "action"][index]
			var resource := Values.read(key)
			var x := 10 + index * (size.x - 20) / 3
			draw_string(font, Vector2(x, 78), resource.label, HORIZONTAL_ALIGNMENT_LEFT, (size.x - 20) / 3, 10, text)
			draw_string(font, Vector2(x, 95), "%d / %d" % [resource.value, resource.maximum], HORIZONTAL_ALIGNMENT_LEFT, (size.x - 20) / 3, 11, text)
			_meter(Rect2(x, 100, (size.x - 26) / 3 - 6, 4), resource.value, resource.maximum, palette[key])

func _detailed_player(data: Dictionary, font: Font, text: Color) -> void:
	var center := Vector2(26, 25)
	draw_circle(center, 18, palette.health.darkened(0.72))
	draw_arc(center, 18, 0, TAU, 48, palette.health, 2, true)
	draw_string(font, Vector2(8, 31), data.name.left(2).to_upper(), HORIZONTAL_ALIGNMENT_CENTER, 36, 13, text)
	draw_string(font, Vector2(52, 23), data.name, HORIZONTAL_ALIGNMENT_LEFT, size.x - 60, 14, text)
	draw_string(font, Vector2(52, 39), "You · Party leader" if data.leader else "You · live resources", HORIZONTAL_ALIGNMENT_LEFT, size.x - 60, 10, text.darkened(0.15))
	for index: int in 5:
		var key: String = ["health", "mana", "food", "action", "load"][index]
		var resource := Values.read(key)
		var y := 53 + index * 20
		var color: Color = palette[key]
		var icon := Icons.tinted_icon(key, color)
		if icon != null: draw_texture_rect(icon, Rect2(8, y - 2, 16, 16), false)
		draw_string(font, Vector2(29, y + 6), resource.label, HORIZONTAL_ALIGNMENT_LEFT, size.x - 104, 10, text)
		draw_string(font, Vector2(29, y + 6), Values.value_text(resource), HORIZONTAL_ALIGNMENT_RIGHT, size.x - 40, 10, color.lightened(0.25))
		_meter(Rect2(29, y + 10, size.x - 40, 4), resource.value, resource.maximum, color)

func _meter(rect: Rect2, current: float, maximum: float, color: Color) -> void:
	draw_rect(rect, Color("131714"))
	var fill := rect
	fill.size.x *= clampf(current / maxf(1, maximum), 0, 1)
	draw_rect(fill, color)
	draw_rect(rect, config.border_color.darkened(0.45), false, 1)
