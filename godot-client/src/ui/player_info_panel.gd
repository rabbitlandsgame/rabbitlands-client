extends Control
## The window that answers "who is that?".
##
## Everything in it is the server's own reply to `GET_PLAYER_INFO`: the actor
## id, the name and the achievements, all stated in one packet. Nothing here is
## paired with a request the client remembers making, and the client keeps no
## copy of the achievement catalog to translate a bitset with - which is what
## the legacy "You see:" line plus `SEND_ACHIEVEMENTS` forced on a client.
##
## It declares no `class_name`: a global class is parsed before the autoload
## singletons are registered, and this reads `AppState` directly.

const PANEL_SIZE := Vector2(340.0, 240.0)
## Nothing may cover the fixed resource rail down the right-hand edge.
const RESERVED_RIGHT_RAIL := 96.0

var panel: PanelContainer
var title: Label
var body: RichTextLabel

func _ready() -> void:
	name = "PlayerInfoLayer"
	mouse_filter = Control.MOUSE_FILTER_IGNORE
	set_anchors_and_offsets_preset(Control.PRESET_FULL_RECT)
	_build()
	AppState.state_changed.connect(_on_state_changed)
	_sync()

func is_open() -> bool:
	return panel.visible

func close() -> void:
	AppState.close_player_info()

func _on_state_changed(path: StringName) -> void:
	if path == &"player_info":
		_sync()
	elif path == &"connection" and AppState.connection_state == "disconnected":
		_sync()

func _sync() -> void:
	if not bool(AppState.player_info.get("open", false)):
		panel.hide()
		return
	var name_text: String = str(AppState.player_info.get("name", ""))
	# The title they chose, after the name, the way it reads in prose:
	# "Ilyon, Keeper of Secrets". Only when the server sent one - an older one
	# sends the frame it always did and this field is simply absent.
	var worn: String = str(AppState.player_info.get("title", ""))
	if not worn.is_empty():
		name_text = "%s, %s" % [name_text, worn]
	title.text = name_text if not name_text.is_empty() else "Player"
	var achievements: Array = AppState.player_info.get("achievements", [])
	var lines: Array[String] = []
	for achievement: Variant in achievements:
		lines.append("[color=#fac638]◆[/color] " + str(achievement))
	body.text = ("\n".join(lines) if not lines.is_empty()
		else "[i]%s[/i]" % tr("ELORIA_PLAYER_INFO_NONE"))
	panel.show()
	panel.move_to_front()

func _build() -> void:
	panel = PanelContainer.new()
	panel.name = "PlayerInfo"
	panel.mouse_filter = Control.MOUSE_FILTER_STOP
	panel.position = Vector2(
		1280.0 - RESERVED_RIGHT_RAIL - PANEL_SIZE.x - 16.0, 96.0)
	panel.custom_minimum_size = PANEL_SIZE
	panel.size = PANEL_SIZE
	panel.hide()
	add_child(panel)

	var column := VBoxContainer.new()
	panel.add_child(column)
	var header := HBoxContainer.new()
	header.name = "PlayerInfoHeader"
	column.add_child(header)
	WindowDrag.attach(panel, header)
	title = Label.new()
	title.name = "PlayerInfoName"
	title.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	header.add_child(title)
	var close_button := Button.new()
	close_button.name = "PlayerInfoClose"
	close_button.text = tr("ELORIA_SETTINGS_CLOSE")
	close_button.pressed.connect(close)
	header.add_child(close_button)
	body = RichTextLabel.new()
	body.name = "PlayerInfoAchievements"
	body.bbcode_enabled = true
	body.size_flags_vertical = Control.SIZE_EXPAND_FILL
	column.add_child(body)
