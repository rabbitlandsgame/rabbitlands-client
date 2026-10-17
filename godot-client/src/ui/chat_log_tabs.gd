extends HFlowContainer
## Read filters only: selecting a log tab never changes the send destination.
const Messages := preload("res://src/ui/chat_messages.gd")
signal tab_selected(key: String)
var selected := "all"
var buttons: Dictionary = {}

func _ready() -> void:
	name = "ChatLogTabs"
	add_theme_constant_override("h_separation", 6)
	for spec: Array in [["all", "All"], ["system", "System"], ["chat", "Chat"],
			["local", "Local"], ["party", "Party"], ["guild", "Guild"], ["private", "Private"]]:
		_add_tab(str(spec[0]), str(spec[1]))
	select("all")

func _add_tab(key: String, title: String) -> void:
	var button := Button.new()
	button.name = "Log_" + key.replace(":", "_")
	button.text = title
	button.toggle_mode = true
	button.focus_mode = Control.FOCUS_NONE
	button.pressed.connect(func() -> void:
		select(key)
		tab_selected.emit(key))
	buttons[key] = button
	add_child(button)

func sync(channels: Array, lines: Array) -> void:
	var dynamic: Dictionary = {}
	for raw: Variant in channels:
		var number := int(raw)
		if number > 0:
			dynamic["channel:%d" % number] = "#%d" % number
	# Retain log sections for channels left earlier in this session.
	for line: Dictionary in lines:
		var number := Messages.channel_number(line)
		if number > 0:
			dynamic["channel:%d" % number] = "#%d" % number
		var person := Messages.peer(line)
		if not person.is_empty():
			dynamic["pm:" + person.to_lower()] = "Private · " + person
	for key: String in dynamic:
		if not buttons.has(key):
			_add_tab(key, str(dynamic[key]))
	for key: String in buttons.keys():
		if (key.begins_with("channel:") or key.begins_with("pm:")) and not dynamic.has(key):
			var button: Button = buttons[key]
			remove_child(button)
			button.queue_free()
			buttons.erase(key)
	if not buttons.has(selected):
		selected = "all"
	select(selected)

func select(key: String) -> void:
	selected = key
	for candidate: String in buttons:
		(buttons[candidate] as Button).set_pressed_no_signal(candidate == key)

func observe(line: Dictionary) -> void:
	var number := Messages.channel_number(line)
	if number > 0 and not buttons.has("channel:%d" % number):
		_add_tab("channel:%d" % number, "#%d" % number)
	var person := Messages.peer(line)
	var key := "pm:" + person.to_lower()
	if not person.is_empty() and not buttons.has(key):
		_add_tab(key, "Private · " + person)
	select(selected)
