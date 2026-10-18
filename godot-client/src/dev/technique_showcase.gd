extends Control
## Offline review of the exact effects and rig playback used by the client.
const Preview = preload("res://src/ui/technique_effect_preview.gd")
const Icons = preload("res://src/ui/technique_icons.gd")
const UI = preload("res://src/ui/action_book_ui.gd")
var preview
var title: Label
var paused := false

func _ready() -> void:
	set_anchors_and_offsets_preset(Control.PRESET_FULL_RECT)
	var background := ColorRect.new()
	background.color = Color("100d09")
	background.set_anchors_and_offsets_preset(Control.PRESET_FULL_RECT)
	add_child(background)
	var margin := MarginContainer.new()
	margin.set_anchors_and_offsets_preset(Control.PRESET_FULL_RECT)
	for side in ["left", "right", "top", "bottom"]: margin.add_theme_constant_override("margin_" + side, 18)
	add_child(margin)
	var column := VBoxContainer.new()
	margin.add_child(column)
	title = UI.label("Combat techniques", 22)
	column.add_child(title)
	var body := HBoxContainer.new()
	body.size_flags_vertical = Control.SIZE_EXPAND_FILL
	column.add_child(body)
	var scroll := UI.scroll("TechniqueChoices")
	scroll.custom_minimum_size.x = 220
	scroll.size_flags_horizontal = Control.SIZE_FILL
	body.add_child(scroll)
	var choices := VBoxContainer.new()
	choices.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	scroll.add_child(choices)
	for key in Icons.ORDER:
		var button := UI.button(key.replace("_", " ").capitalize())
		button.icon = Icons.icon_for(key)
		button.expand_icon = true
		button.add_theme_constant_override("icon_max_width", 28)
		button.pressed.connect(select_technique.bind(key))
		choices.add_child(button)
	preview = Preview.new()
	preview.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	preview.size_flags_vertical = Control.SIZE_EXPAND_FILL
	body.add_child(preview)
	var controls := HBoxContainer.new()
	column.add_child(controls)
	var replay := UI.button("Replay")
	replay.pressed.connect(func(): preview.replay())
	controls.add_child(replay)
	var pause := UI.button("Pause")
	pause.toggle_mode = true
	pause.toggled.connect(func(value: bool):
		paused = value
		preview.set_process(not value)
		preview.stage.process_mode = Node.PROCESS_MODE_DISABLED if value else Node.PROCESS_MODE_INHERIT)
	controls.add_child(pause)
	controls.add_child(UI.label("Production rigs, weapons and effects · offline demonstration", 13))
	select_technique("shield_bash")

func select_technique(key: String) -> void:
	title.text = "Combat techniques · " + key.replace("_", " ").capitalize()
	preview.set_technique({"key": key})
	if paused:
		preview.set_process(false)
		preview.stage.process_mode = Node.PROCESS_MODE_DISABLED
