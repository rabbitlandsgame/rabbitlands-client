extends Control
## A read-only companion to the movable combat HUD. No client clock advances
## encounters: only a new server pulse serial announces an arrival.
const ARRIVAL_HOLD_MSEC := 2500
const DescentStatusHud := preload("res://src/ui/descent_status_hud.gd")
var panel: PanelContainer
var heading: Label
var counts: Label
var release: Label
var arrival: Label
var _state: Dictionary = {}
var _anchor_msec := 0
var _identity := ""
var _serial := -1
var _arrival_until := 0
var _refresh_at := 0
var _anchor: Callable
var _enabled: Callable
var _app: Node
## Main's right rail: the readout keeps left of it (descent_status_hud.gd clear_right).
var dock_rail: Control

func _ready() -> void:
	name = "GauntletProgressHud"
	mouse_filter = Control.MOUSE_FILTER_IGNORE
	set_anchors_and_offsets_preset(Control.PRESET_FULL_RECT)
	panel = PanelContainer.new()
	panel.mouse_filter = Control.MOUSE_FILTER_IGNORE
	panel.z_index = 7
	var style := StyleBoxFlat.new()
	style.bg_color = Color("162127ee")
	style.border_color = Color("ba9b62")
	style.set_border_width_all(1)
	style.set_corner_radius_all(4)
	style.set_content_margin_all(8)
	panel.add_theme_stylebox_override("panel", style)
	add_child(panel)
	var body := VBoxContainer.new()
	body.mouse_filter = Control.MOUSE_FILTER_IGNORE
	body.add_theme_constant_override("separation", 3)
	panel.add_child(body)
	heading = _label(body, "EncounterWave")
	counts = _label(body, "EncounterCounts")
	release = _label(body, "EncounterRelease")
	arrival = _label(body, "EncounterArrival")
	arrival.add_theme_color_override("font_color", Color("ffe5a3"))
	_app = get_node("/root/AppState")
	_app.state_changed.connect(_on_state_changed)
	get_viewport().size_changed.connect(_layout)
	apply_snapshot(_app.gauntlet_progress, _app.gauntlet_progress_anchor_msec)

func _label(body: Control, title: String) -> Label:
	var label := Label.new()
	label.name = title
	label.mouse_filter = Control.MOUSE_FILTER_IGNORE
	label.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
	label.add_theme_font_size_override("font_size", 13)
	label.add_theme_color_override("font_color", Color("f1e8d4"))
	label.add_theme_color_override("font_outline_color", Color.BLACK)
	label.add_theme_constant_override("outline_size", 2)
	body.add_child(label)
	return label

func configure(anchor: Callable, enabled: Callable) -> void:
	_anchor = anchor
	_enabled = enabled
	_refresh_at = 0

func _now_msec() -> int:
	return Time.get_ticks_msec()

func _on_state_changed(path: StringName) -> void:
	if path == &"gauntlet_progress":
		apply_snapshot(_app.gauntlet_progress, _app.gauntlet_progress_anchor_msec)
	elif path in [&"map", &"connection", &"authentication"]:
		apply_snapshot(_app.gauntlet_progress, _app.gauntlet_progress_anchor_msec)

func apply_snapshot(state: Dictionary, received_msec: int) -> void:
	var identity := "%s:%d" % [str(state.get("run_id", "")), int(state.get("wave", 0))]
	var serial := int(state.get("arrival_serial", 0))
	if bool(state.get("active", false)) and identity == _identity and serial < _serial:
		return
	if not bool(state.get("active", false)):
		_identity = ""
		_serial = -1
		_arrival_until = 0
	elif identity == _identity and _serial >= 0 and serial > _serial:
		arrival.text = "Wave begins" if _serial == 0 else "Reinforcements arrived"
		_arrival_until = _now_msec() + ARRIVAL_HOLD_MSEC
	elif identity != _identity:
		# A reconnect or the first received snapshot must not replay old horns.
		_arrival_until = 0
	_identity = identity if bool(state.get("active", false)) else ""
	_serial = serial if bool(state.get("active", false)) else -1
	_state = state.duplicate(true)
	_anchor_msec = received_msec
	_refresh_at = 0
	_refresh()

func _process(_delta: float) -> void:
	if _now_msec() >= _refresh_at:
		_refresh()

func _refresh() -> void:
	if panel == null:
		return
	var now := _now_msec()
	_refresh_at = now + 200
	var here := EloriaProtocol.map_id_from_reference(_app.current_map)
	var matches := EloriaProtocol.map_id_from_reference(str(_state.get("map_id", ""))) == here
	panel.visible = _app.authenticated and bool(_state.get("active", false)) and matches \
		and (not _enabled.is_valid() or bool(_enabled.call()))
	if not panel.visible:
		return
	heading.text = "Wave %d / %d · %s" % [int(_state.wave), int(_state.waves), str(_state.title)]
	var pending := int(_state.pulses_pending)
	counts.text = "Enemies remaining: %d · Future pulses: %d" % [int(_state.enemies), pending]
	if str(_state.phase) == "waiting":
		release.text = "Enter the next encounter to begin."
	elif pending == 0:
		release.text = "All reinforcement pulses have arrived."
	elif _state.release_enemy_threshold != null:
		var threshold := int(_state.release_enemy_threshold)
		if _state.release_remaining_ms != null:
			var remaining := maxi(0, int(_state.release_remaining_ms) - maxi(0, now - _anchor_msec))
			release.text = ("Reinforcements in ≤%ds or at %d enemies remaining." % [ceili(remaining / 1000.0), threshold]) \
				if remaining > 0 else "Reinforcements due · awaiting the next server pulse."
		else:
			release.text = "Reinforcements when %d or fewer enemies remain." % threshold
	else:
		release.text = "Awaiting the next reinforcement pulse."
	arrival.visible = now < _arrival_until
	_layout()

func _layout() -> void:
	if panel == null or not panel.visible:
		return
	var bounds := size
	var right: float = DescentStatusHud.clear_right(self, dock_rail)
	var width := minf(380.0, maxf(120.0, right - 16.0))
	panel.custom_minimum_size.x = width
	panel.size.x = width
	panel.reset_size()
	var anchor := Rect2(Vector2(right * 0.5 - width * 0.5, 64), Vector2(width, 60))
	if _anchor.is_valid():
		var value: Variant = _anchor.call()
		if value is Rect2:
			anchor = Rect2((value as Rect2).position - global_position, (value as Rect2).size)
	var y := anchor.end.y + 6
	if y + panel.size.y > bounds.y - 8:
		y = anchor.position.y - panel.size.y - 6
	panel.position = Vector2(clampf(anchor.get_center().x - panel.size.x * 0.5, 8, maxf(8, right - panel.size.x - 8)),
		clampf(y, 8, maxf(8, bounds.y - panel.size.y - 8)))
