extends VBoxContainer
## The Techniques tab of the Spells & Techniques window: the fighter's and the
## archer's own moves.
##
## Everything here is the server's: which techniques exist, which this
## character knows, what each costs, why one is refused, how long one is
## cooling down and how many action points are left. The tab draws the state it
## is sent (ELORIA_MAGIC_STATE kind "techniques", gated by techniques_v1) and
## asks to use a technique; it never decides one is usable. The Tab-held ring
## and the quick spell slots use it too, so every launcher aims the same way.
##
## A strike or shot needs a creature. The one the player has selected is used
## when it is one; failing that the creature they are fighting; failing that
## the technique is armed and the next creature they click receives it, the
## way a targeted spell waits for its target. Charge is the reason: it is for
## a creature you are not fighting yet, maybe far away.
##
## The script declares no `class_name`: it reads `AppState` directly, and a
## global class is parsed before the autoloads exist.

signal place_on_bar(key: String)
signal used(key: String)

const REFRESH_MSEC := 200
const HUD_STYLE := preload("res://src/ui/compact_hud_style.gd")
const Icons := preload("res://src/ui/technique_icons.gd")
const READY := Color("eee3c8")
const LOCKED := Color(0.62, 0.58, 0.5, 0.6)
const ACTIVE := Color("e8c77a")

## A technique's button, which can be dragged onto a quick spell slot.
class TechniqueButton extends Button:
	var key := ""
	## Learned techniques can be dragged even while cooling down.
	var draggable := false
	func _get_drag_data(_position: Vector2) -> Variant:
		if key.is_empty() or not draggable:
			return null
		var preview := TextureRect.new()
		preview.texture = icon
		preview.custom_minimum_size = Vector2(40, 40)
		preview.expand_mode = TextureRect.EXPAND_IGNORE_SIZE
		set_drag_preview(preview)
		return {"kind": "technique", "key": key}

var points_label: Label
var status_label: Label
var hint_label: Label
var list: VBoxContainer
var show_locked: CheckButton
## key -> Button, rebuilt only when the set of techniques changes.
var buttons: Dictionary = {}
## key -> the server's row for it.
var rows: Dictionary = {}
var _order: Array = []
var _next_refresh := 0
## Sends one request dictionary; main wires Network.technique_request.
var request_sender: Callable
## Whether an actor id is a creature this player could strike, and whether
## it is another player (Intercept guards one).
var creature_validator: Callable
var player_validator: Callable
## A targeted technique waiting for the next creature the player clicks.
var pending_key := ""

func _ready() -> void:
	name = "TechniquesTab"
	size_flags_vertical = Control.SIZE_EXPAND_FILL
	_build()
	AppState.state_changed.connect(_on_state_changed)
	sync()

func configure(sender: Callable, creature_check: Callable = Callable(),
		player_check: Callable = Callable()) -> void:
	request_sender = sender
	creature_validator = creature_check
	player_validator = player_check

## The server's current pool, or -1 when this server sends none.
static func action_points(state: Dictionary) -> Vector2i:
	if not state.has("action_points"):
		return Vector2i(-1, -1)
	return Vector2i(int(state.get("action_points", 0)), int(state.get("max_action_points", 0)))

## A row a launcher should offer now: learned, and not refused for anything
## but the points or the moment (a missing shield or level hides it).
static func offered(row: Dictionary) -> bool:
	var blocker := str(row.get("blocker", ""))
	return bool(row.get("known", false)) and (blocker.is_empty() or "action points" in blocker)

## The first key bound to an action, as a player reads it ("Tab", "Ctrl+X").
static func key_name(action: String) -> String:
	if not InputMap.has_action(action):
		return "?"
	for event: InputEvent in InputMap.action_get_events(action):
		if event is InputEventKey:
			return (event as InputEventKey).as_text_physical_keycode() if (event as InputEventKey).physical_keycode != 0 else event.as_text()
	return "an unbound key"

func _on_state_changed(path: StringName) -> void:
	if path == &"techniques":
		sync()

func _process(_delta: float) -> void:
	if not is_visible_in_tree() or Time.get_ticks_msec() < _next_refresh:
		return
	_next_refresh = Time.get_ticks_msec() + REFRESH_MSEC
	_refresh_buttons()

func sync() -> void:
	var state: Dictionary = AppState.techniques
	var incoming: Array = state.get("techniques", []) if state.get("techniques") is Array else []
	rows.clear()
	var order: Array = []
	for raw: Variant in incoming:
		if raw is Dictionary and str(raw.get("key", "")) != "":
			rows[str(raw.key)] = raw
			order.append(str(raw.key))
	if order != _order:
		_order = order
		_rebuild()
	var pool := action_points(state)
	points_label.text = ("Action points %d / %d" % [pool.x, pool.y]) if pool.x >= 0 else "Action points -"
	if hint_label != null:
		hint_label.text = ("Hold %s for the technique ring. Drag a technique onto a quick spell slot "
			+ "to use it from the quick bar.") % key_name("technique_ring")
	if pending_key != "" and not rows.has(pending_key):
		cancel_pending()
	_refresh_buttons()

## Seconds left on a technique's cooldown, counted down from when the server
## said it.
func ready_in(key: String) -> float:
	var row: Dictionary = rows.get(key, {})
	var elapsed := float(Time.get_ticks_msec() - int(AppState.techniques.get("received_msec", 0))) / 1000.0
	return maxf(0.0, float(row.get("ready_in", 0.0)) - elapsed)

## Why this technique cannot be pressed right now, or "" when it can.
func unavailable_reason(key: String) -> String:
	var row: Dictionary = rows.get(key, {})
	if row.is_empty():
		return "Unknown technique."
	if not bool(row.get("known", false)):
		return "Read the %s to learn it." % str(row.get("manual", "manual"))
	if str(row.get("kind", "")) == "stance" and bool(row.get("active", false)):
		return ""
	var blocker := str(row.get("blocker", ""))
	if not blocker.is_empty():
		return blocker
	var waiting := ready_in(key)
	if waiting > 0.05:
		return "Ready in %ds." % ceili(waiting)
	var pool := action_points(AppState.techniques)
	if pool.x >= 0 and pool.x < int(row.get("ap", 0)):
		return "You need %d action points." % int(row.get("ap", 0))
	return ""

func tooltip_for(key: String) -> String:
	var row: Dictionary = rows.get(key, {})
	var tip := str(row.get("name", key)) + "\n" + str(row.get("description", ""))
	tip += "\n%s %d · %s" % [str(row.get("skill", "")), int(row.get("level", 0)), str(row.get("group", ""))]
	if int(row.get("ap", 0)) > 0:
		tip += " · %d AP" % int(row.get("ap", 0))
	if float(row.get("cooldown", 0.0)) > 0.0:
		tip += " · cooldown %ds" % roundi(float(row.get("cooldown", 0.0)))
	var reason := unavailable_reason(key)
	if not reason.is_empty():
		tip += "\n" + reason
	return tip

func _refresh_buttons() -> void:
	for key: String in buttons:
		var button: Button = buttons[key]
		var row: Dictionary = rows.get(key, {})
		var known := bool(row.get("known", false))
		var waiting := ready_in(key)
		var active := bool(row.get("active", false)) or pending_key == key
		var label := str(row.get("name", key))
		var cost := int(row.get("ap", 0))
		label += "  [%d AP]" % cost if cost > 0 else ""
		if waiting > 0.05:
			label += "  %ds" % ceili(waiting)
		if pending_key == key:
			label += "  - click a creature"
		elif bool(row.get("active", false)):
			label += "  - held" if str(row.get("kind", "")) == "stance" else "  - readied"
		button.text = label
		button.disabled = not unavailable_reason(key).is_empty() and not active
		button.modulate = ACTIVE if active else (READY if not button.disabled else LOCKED)
		button.tooltip_text = tooltip_for(key)
		(button as TechniqueButton).draggable = known
		var line: Control = button.get_parent()
		line.visible = known or show_locked.button_pressed
		var place: Button = line.get_node_or_null("Place") as Button
		if place != null:
			place.disabled = not known

func use(key: String) -> void:
	var row: Dictionary = rows.get(key, {})
	if row.is_empty():
		return
	if pending_key == key:
		cancel_pending()
		return
	var request := {"op": "use", "key": key}
	if bool(row.get("targeted", false)):
		var target := _selected(creature_validator)
		if target < 0 and bool(AppState.combat_state.get("active", false)):
			target = int(AppState.combat_state.get("target_id", -1))
		if target < 0:
			pending_key = key
			status_label.text = "Click a creature for %s." % str(row.get("name", key))
			_refresh_buttons()
			return
		request["target_id"] = target
	elif key == "intercept":
		var ally := _selected(player_validator)
		if ally >= 0:
			request["target_id"] = ally
	_send(request)

## The next creature clicked receives the armed technique. True when one was
## armed, so the click does nothing else.
func fire_at(actor_id: int) -> bool:
	if pending_key == "":
		return false
	if creature_validator.is_valid() and not bool(creature_validator.call(actor_id)):
		return false
	var key := pending_key
	cancel_pending()
	_send({"op": "use", "key": key, "target_id": actor_id})
	return true

func cancel_pending() -> void:
	pending_key = ""
	if status_label != null:
		status_label.text = ""
	if list != null:
		_refresh_buttons()

func _selected(validator: Callable) -> int:
	var actor_id := int(AppState.selected_actor_id)
	if actor_id < 0 or actor_id == AppState.local_actor_id:
		return -1
	if validator.is_valid() and not bool(validator.call(actor_id)):
		return -1
	return actor_id

func _send(request: Dictionary) -> void:
	if status_label != null:
		status_label.text = ""
	if request_sender.is_valid():
		request_sender.call(request)
	used.emit(str(request.get("key", "")))

func _rebuild() -> void:
	for child: Node in list.get_children():
		list.remove_child(child)
		child.queue_free()
	buttons.clear()
	var group := ""
	for key: String in _order:
		var row: Dictionary = rows[key]
		if str(row.get("group", "")) != group:
			group = str(row.get("group", ""))
			var heading := Label.new()
			heading.name = "Group" + group.replace(" ", "").replace("-", "")
			heading.text = group
			heading.add_theme_color_override("font_color", HUD_STYLE.BRASS)
			list.add_child(heading)
		var line := HBoxContainer.new()
		line.name = "Row_" + key
		list.add_child(line)
		var button := TechniqueButton.new()
		button.key = key
		button.name = "Use_" + key
		button.size_flags_horizontal = Control.SIZE_EXPAND_FILL
		button.alignment = HORIZONTAL_ALIGNMENT_LEFT
		button.icon = Icons.icon_for(key)
		button.expand_icon = false
		button.add_theme_constant_override("icon_max_width", 28)
		HUD_STYLE.button(button)
		button.pressed.connect(use.bind(key))
		line.add_child(button)
		var place := Button.new()
		place.name = "Place"
		place.text = "+"
		place.tooltip_text = "Put on the first empty quick spell slot (or drag the technique onto one)."
		HUD_STYLE.button(place)
		place.pressed.connect(func() -> void: place_on_bar.emit(key))
		line.add_child(place)
		buttons[key] = button

func _build() -> void:
	var info := HBoxContainer.new()
	info.name = "TechniquesInfo"
	add_child(info)
	points_label = Label.new()
	points_label.name = "ActionPoints"
	points_label.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	info.add_child(points_label)
	show_locked = CheckButton.new()
	show_locked.name = "ShowLocked"
	show_locked.text = "Show unlearned"
	show_locked.button_pressed = true
	show_locked.toggled.connect(func(_on: bool) -> void: _refresh_buttons())
	info.add_child(show_locked)

	status_label = Label.new()
	status_label.name = "TechniquesStatus"
	status_label.add_theme_color_override("font_color", ACTIVE)
	add_child(status_label)

	hint_label = Label.new()
	hint_label.name = "TechniquesHint"
	hint_label.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
	hint_label.add_theme_color_override("font_color", HUD_STYLE.MUTED)
	add_child(hint_label)

	var scroll := ScrollContainer.new()
	scroll.name = "TechniquesScroll"
	scroll.size_flags_vertical = Control.SIZE_EXPAND_FILL
	scroll.horizontal_scroll_mode = ScrollContainer.SCROLL_MODE_DISABLED
	add_child(scroll)
	list = VBoxContainer.new()
	list.name = "TechniquesList"
	list.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	scroll.add_child(list)
