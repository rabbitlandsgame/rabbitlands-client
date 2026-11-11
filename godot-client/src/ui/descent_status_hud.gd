extends Control
## A small read-only line of where the party stands in a descent: the
## dungeon, the floor (number and name) and the time left, from the server's
## descent state (AppState.descent, server message 188). The clock counts down
## locally between states from when the last one arrived; the server's next
## state restates it.
##
## In the game the HUD workspace places it: it is the editor part
## "descent_status" (hud_presets.gd), by default MANAGED_WIDTH wide under the
## combat HUD's default spot, clear of every preset's parts, and the player can
## move or hide it in the HUD editor (`configure_hud`). Unmanaged (ExtensionWindows
## on its own) it sits under the combat HUD as before.

signal hud_layout_requested

## The readout's width when the workspace places it: its lines wrap to it.
const MANAGED_WIDTH := 240.0

var panel: PanelContainer
var heading: Label
var floor_line: Label
var clock: Label
var _state: Dictionary = {}
var _anchor_msec := 0
var _refresh_at := 0
var _anchor: Callable
var _app: Node
## Main's right rail: the readout keeps left of it while it shows, so a combat
## HUD dragged to the right edge does not push the readout under the rail.
var dock_rail: Control
var _hud_managed := false
var _hud_enabled := true
var _hud_preview := false
var _laid_out := Vector2(-1, -1)
var _laid_visible := false

func _ready() -> void:
	name = "DescentStatusHud"
	mouse_filter = Control.MOUSE_FILTER_IGNORE
	set_anchors_and_offsets_preset(Control.PRESET_FULL_RECT)
	panel = PanelContainer.new()
	panel.name = "DescentStatus"
	panel.mouse_filter = Control.MOUSE_FILTER_IGNORE
	panel.z_index = 7
	var style := StyleBoxFlat.new()
	style.bg_color = Color("162127ee")
	style.border_color = Color("ba9b62")
	style.set_border_width_all(1)
	style.set_corner_radius_all(4)
	style.set_content_margin_all(6)
	panel.add_theme_stylebox_override("panel", style)
	add_child(panel)
	var body := VBoxContainer.new()
	body.mouse_filter = Control.MOUSE_FILTER_IGNORE
	body.add_theme_constant_override("separation", 2)
	panel.add_child(body)
	heading = _label(body, "DescentHeading", 13)
	heading.add_theme_color_override("font_color", Color("ffe5a3"))
	floor_line = _label(body, "DescentFloor", 13)
	clock = _label(body, "DescentClock", 12)
	panel.hide()
	_app = get_node("/root/AppState")
	_app.state_changed.connect(_on_state_changed)
	get_viewport().size_changed.connect(_layout)
	apply_state(_app.descent, _app.descent_anchor_msec)

func _label(body: Control, title: String, font_size: int) -> Label:
	var label := Label.new()
	label.name = title
	label.mouse_filter = Control.MOUSE_FILTER_IGNORE
	label.horizontal_alignment = HORIZONTAL_ALIGNMENT_CENTER
	label.add_theme_font_size_override("font_size", font_size)
	label.add_theme_color_override("font_color", Color("f1e8d4"))
	label.add_theme_color_override("font_outline_color", Color.BLACK)
	label.add_theme_constant_override("outline_size", 2)
	body.add_child(label)
	return label

## `anchor` returns the global rectangle to sit under (the combat HUD's).
func configure(anchor: Callable) -> void:
	_anchor = anchor
	_refresh_at = 0

## The HUD workspace places the readout from now on: shown while a descent is
## open and the part is enabled, or as a sample while the HUD editor is open.
func configure_hud(enabled: bool, preview: bool) -> void:
	_hud_managed = true
	_hud_enabled = enabled
	_hud_preview = preview
	panel.custom_minimum_size.x = MANAGED_WIDTH
	for label: Label in [heading, floor_line, clock]:
		label.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
	_refresh_at = 0
	_refresh()

func _now_msec() -> int:
	return Time.get_ticks_msec()

func _on_state_changed(path: StringName) -> void:
	if path in [&"descent", &"connection", &"authentication"]:
		apply_state(_app.descent, _app.descent_anchor_msec)

func apply_state(state: Dictionary, received_msec: int) -> void:
	_state = state.duplicate(true)
	_anchor_msec = received_msec
	_refresh_at = 0
	_refresh()

func _process(_delta: float) -> void:
	if panel != null and panel.visible and _now_msec() >= _refresh_at:
		_refresh()

## Seconds left on the run now, counted down from the last state.
func seconds_left() -> int:
	var elapsed := maxi(0, _now_msec() - _anchor_msec) / 1000
	return maxi(0, int(_state.get("time_left", 0)) - elapsed)

static func clock_text(seconds: int) -> String:
	var shown := maxi(0, seconds)
	if shown >= 3600:
		return "%d:%02d:%02d" % [shown / 3600, (shown / 60) % 60, shown % 60]
	return "%d:%02d" % [shown / 60, shown % 60]

static func boss_text(boss: String) -> String:
	match boss:
		"waiting":
			return "The boss waits"
		"fighting":
			return "The boss is fighting"
		"defeated":
			return "Boss defeated: claim your reward at the dais"
	return ""

func _refresh() -> void:
	if panel == null:
		return
	_refresh_at = _now_msec() + 250
	var live := bool(_app.authenticated) and bool(_state.get("open", false))
	panel.visible = (_hud_enabled and (live or _hud_preview)) if _hud_managed else live
	if not panel.visible:
		_request_layout()
		return
	if not live:
		heading.text = "The Serpent Deep · Normal"
		floor_line.text = "Floor 1 of 6 · Descent status"
		clock.text = "Time left 60:00"
		_layout()
		return
	var title := str(_state.get("name", ""))
	if title.is_empty():
		title = str(_state.get("dungeon", "Descent")).capitalize()
	var difficulty := str(_state.get("difficulty", ""))
	heading.text = title + (" · " + difficulty if not difficulty.is_empty() else "")
	var floor_name := str(_state.get("floor_name", ""))
	floor_line.text = "Floor %d of %d" % [int(_state.get("floor", 1)), int(_state.get("floors", 1))] \
		+ (" · " + floor_name if not floor_name.is_empty() else "")
	var line := "Time left " + clock_text(seconds_left())
	var boss := boss_text(str(_state.get("boss", "")))
	clock.text = line + (" · " + boss if not boss.is_empty() else "")
	_layout()

## Managed: the workspace lays the readout out again only when its size or
## visibility changed (the clock ticks four times a second).
func _request_layout() -> void:
	if not _hud_managed:
		return
	var size_now := panel.get_combined_minimum_size()
	if size_now == _laid_out and panel.visible == _laid_visible:
		return
	_laid_out = size_now
	_laid_visible = panel.visible
	hud_layout_requested.emit()

## The default spot: centred, under the combat HUD's default rect (y 64-140 at
## 1280 x 720), where no preset puts a part.
static func default_hud_rect(viewport: Vector2, size_now: Vector2) -> Rect2:
	return Rect2(Vector2((viewport.x - size_now.x) / 2.0, 146.0), size_now)

func _layout() -> void:
	if panel == null or not panel.visible:
		return
	if _hud_managed:
		_request_layout()
		return
	var bounds := size
	var right := clear_right(self, dock_rail)
	panel.reset_size()
	var width := minf(panel.get_combined_minimum_size().x, maxf(120.0, right - 16.0))
	panel.size.x = width
	var anchor := Rect2(Vector2(right * 0.5 - width * 0.5, 64), Vector2(width, 60))
	if _anchor.is_valid():
		var value: Variant = _anchor.call()
		if value is Rect2 and (value as Rect2).size != Vector2.ZERO:
			anchor = Rect2((value as Rect2).position - global_position, (value as Rect2).size)
	var y := anchor.end.y + 6
	if y + panel.size.y > bounds.y - 8:
		y = anchor.position.y - panel.size.y - 6
	panel.position = Vector2(clampf(anchor.get_center().x - panel.size.x * 0.5, 8, maxf(8, right - panel.size.x - 8)),
		clampf(y, 8, maxf(8, bounds.y - panel.size.y - 8)))

## The right edge a readout in `owner_control` may reach: its own width, or
## the left edge of `rail` when that shows and lies inside it.
static func clear_right(owner_control: Control, rail: Control) -> float:
	var right := owner_control.size.x
	if is_instance_valid(rail) and rail.is_visible_in_tree():
		var left := (owner_control.get_global_transform().affine_inverse() * rail.global_position).x
		if left > 0.0:
			right = minf(right, left)
	return right
