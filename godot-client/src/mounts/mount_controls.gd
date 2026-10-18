extends PanelContainer
const Hotkeys := preload("res://src/mounts/mount_hotkeys.gd")
var toggle := Button.new()
var gallop := Button.new()
var status := Label.new()

func _ready() -> void:
	name = "MountControls"
	position = Vector2(340, 44)
	var row := HBoxContainer.new()
	add_child(row)
	row.add_child(toggle)
	row.add_child(gallop)
	row.add_child(status)
	toggle.focus_mode = Control.FOCUS_NONE
	gallop.focus_mode = Control.FOCUS_NONE
	toggle.tooltip_text = "Call your Moor Pony, or dismount. Stand still while calling."
	gallop.tooltip_text = "Toggle gallop while running (hold Shift for keyboard running). Eight seconds of endurance."
	toggle.pressed.connect(func() -> void: Network.send_chat("#mount"))
	gallop.pressed.connect(func() -> void: Network.send_chat("#gallop"))
	AppState.state_changed.connect(_changed)
	_refresh()

func _changed(_section: StringName) -> void:
	if _section in [&"mount_states", &"map", &"authentication", &"local_actor"]:
		_refresh()

func _refresh() -> void:
	var state: Dictionary = AppState.actor_mounts.get(AppState.local_actor_id, {})
	visible = AppState.authenticated and not state.is_empty()
	var mode: String = state.get("mode", "on_foot")
	toggle.text = "Dismount" if mode == "mounted" else ("Cancel" if mode == "summoning" else "Mount pony")
	toggle.text += Hotkeys.key_hint("toggle_mount")
	gallop.disabled = mode != "mounted" or state.get("gait") == "walk"
	gallop.text = "Stop gallop" if state.get("gait") == "burst" else "Gallop"
	gallop.text += Hotkeys.key_hint("toggle_gallop")
	if mode == "summoning":
		status.text = "  Calling pony… %.1fs" % (float(state.get("summon_remaining_ms", 0)) / 1000.0)
	elif mode == "mounted":
		status.text = "  %s · %.1fs endurance" % [str(state.get("gait", "cruise")).capitalize().replace("Cruise", "Trot").replace("Burst", "Gallop"), float(state.get("endurance_ms", 0)) / 1000.0]
	else:
		status.text = "  " + str(state.get("blocked_reason", "")).replace("_", " ").capitalize()
