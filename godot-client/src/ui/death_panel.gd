extends PanelContainer
## The server owns readiness; the local death clip must also reach its last pose.
var actor_for_player: Callable
var message := Label.new()
var respawn := Button.new()
var _request_at := -1
@onready var app_state: Node = get_node("/root/AppState")
@onready var network: Node = get_node("/root/Network")

func _ready() -> void:
	name = "DeathPanel"
	set_anchors_and_offsets_preset(Control.PRESET_CENTER_BOTTOM)
	offset_left = -230.0
	offset_right = 230.0
	offset_top = -210.0
	offset_bottom = -100.0
	z_index = 20
	var margin := MarginContainer.new()
	for side: String in ["left", "right", "top", "bottom"]:
		margin.add_theme_constant_override("margin_" + side, 14)
	add_child(margin)
	var column := VBoxContainer.new()
	column.add_theme_constant_override("separation", 10)
	margin.add_child(column)
	message.horizontal_alignment = HORIZONTAL_ALIGNMENT_CENTER
	column.add_child(message)
	respawn.text = "Respawn Now"
	respawn.custom_minimum_size.y = 38.0
	column.add_child(respawn)
	respawn.pressed.connect(_respawn_now)
	hide()

func _process(_delta: float) -> void:
	var state: Dictionary = app_state.death
	visible = app_state.authenticated and bool(state.get("dead", false))
	if not visible:
		_request_at = -1
		return
	var remaining := maxf(0.0, float(state.get("remaining", 0.0))
		- float(Time.get_ticks_msec() - int(state.get("received_msec", 0))) / 1000.0)
	var actor: Variant = actor_for_player.call() if actor_for_player.is_valid() else null
	var clip_finished := is_instance_valid(actor) and bool(actor.death_animation_finished())
	respawn.visible = bool(state.get("ready", false)) and clip_finished
	respawn.disabled = _request_at >= 0 and Time.get_ticks_msec() - _request_at < 2000
	message.text = "You have fallen.\nA player can revive you with a targeted heal."
	if remaining > 0.0:
		message.text += "\nRespawn available in %d seconds." % ceili(remaining)

func _respawn_now() -> void:
	if network.magic_request({"op": "respawn"}) == OK:
		_request_at = Time.get_ticks_msec()
		respawn.disabled = true
