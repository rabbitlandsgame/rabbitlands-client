extends Control
## The Emotes window: the gestures this client can play, laid out the way
## Eternal Lands lays its own out - a category list, the emotes under it, and
## the trigger text along the bottom.
##
## The catalogue is read from the client's own animation table
## (res://data/animations/luminous.json): every action named `emote_*` is a
## gesture the rig can actually perform, so the list can never offer an emote
## the client has no animation for. Nothing here decides whether an emote
## happens - the window only asks, through the Callable it is given, and the
## server answers an unknown emote by listing the ones it has. This list is
## the client's playable set, not a claim about the server's.
##
## Performing is throttled to one emote a second, exactly as the legacy
## client throttles emote spam; a throttled attempt does nothing at all.

const PANEL_SIZE := Vector2(300.0, 380.0)
## Nothing may cover the fixed resource rail down the right-hand edge.
const RESERVED_RIGHT_RAIL := 96.0
## The legacy client lets one emote through per second, so this one does too.
const PERFORM_COOLDOWN_MSEC := 1000

var panel: PanelContainer
var category_list: ItemList
var emote_list: ItemList
var trigger_label: Label
var do_button: Button

## The wire names, stripped of their emote_ prefix and sorted, in list order.
var _emotes: Array[String] = []
var _perform: Callable
var _last_perform_msec: int = -PERFORM_COOLDOWN_MSEC

func _ready() -> void:
	name = "EmotesLayer"
	mouse_filter = Control.MOUSE_FILTER_IGNORE
	set_anchors_and_offsets_preset(Control.PRESET_FULL_RECT)
	_emotes = _read_catalog()
	_build()
	sync()

## How an emote is actually asked for: the callable is handed the wire name
## ("bow"), and what it does with it - a #emote line, a packet - is its own.
func configure(perform: Callable) -> void:
	_perform = perform

func is_open() -> bool:
	return panel.visible

func toggle() -> void:
	panel.visible = not panel.visible
	if panel.visible:
		panel.move_to_front()
		sync()

func close() -> void:
	panel.hide()

## The wire names this client can play, sorted, without the emote_ prefix.
func emote_names() -> Array[String]:
	return _emotes.duplicate()

func sync() -> void:
	if category_list.item_count == 0:
		category_list.add_item("Actions")
	category_list.select(0)
	var selected: PackedInt32Array = emote_list.get_selected_items()
	var kept: String = (str(emote_list.get_item_metadata(selected[0]))
		if not selected.is_empty() else "")
	emote_list.clear()
	for wire: String in _emotes:
		var index: int = emote_list.item_count
		emote_list.add_item(wire.capitalize())
		emote_list.set_item_metadata(index, wire)
		if wire == kept:
			emote_list.select(index)
	if kept.is_empty():
		trigger_label.text = ""
		do_button.disabled = true

## Every action in the client's animation table whose name says it is an
## emote. The table is the same one the player model plays from, so what is
## listed here is exactly what the rig can do.
func _read_catalog() -> Array[String]:
	var found: Array[String] = []
	var file: FileAccess = FileAccess.open(
		"res://data/animations/luminous.json", FileAccess.READ)
	if file == null:
		return found
	var parsed: Variant = JSON.parse_string(file.get_as_text())
	if parsed is not Dictionary:
		return found
	var actions: Variant = (parsed as Dictionary).get("actions", {})
	if actions is not Dictionary:
		return found
	for key: Variant in actions as Dictionary:
		var action: String = str(key)
		if action.begins_with("emote_"):
			found.append(action.trim_prefix("emote_"))
	found.sort()
	return found

func _on_emote_selected(index: int) -> void:
	trigger_label.text = "Trigger:  #emote %s" % str(
		emote_list.get_item_metadata(index))
	do_button.disabled = false

func _on_emote_activated(index: int) -> void:
	_perform_emote(str(emote_list.get_item_metadata(index)))

func _on_do_pressed() -> void:
	var selected: PackedInt32Array = emote_list.get_selected_items()
	if selected.is_empty():
		return
	_perform_emote(str(emote_list.get_item_metadata(selected[0])))

## One perform a second. An attempt inside the cooldown does nothing: it is
## not queued, because the legacy client drops it too.
func _perform_emote(wire: String) -> void:
	if not _perform.is_valid():
		return
	var now: int = Time.get_ticks_msec()
	if now - _last_perform_msec < PERFORM_COOLDOWN_MSEC:
		return
	_last_perform_msec = now
	_perform.call(wire)

func _build() -> void:
	panel = PanelContainer.new()
	panel.name = "EmotesWindow"
	panel.mouse_filter = Control.MOUSE_FILTER_STOP
	panel.position = Vector2(
		(1280.0 - RESERVED_RIGHT_RAIL) * 0.5 - PANEL_SIZE.x, 80.0)
	panel.custom_minimum_size = PANEL_SIZE
	panel.size = PANEL_SIZE
	panel.hide()
	add_child(panel)

	var column := VBoxContainer.new()
	column.name = "EmotesBody"
	panel.add_child(column)
	var header := HBoxContainer.new()
	header.name = "EmotesHeader"
	column.add_child(header)
	WindowDrag.attach(panel, header)
	var title := Label.new()
	title.name = "EmotesTitle"
	title.text = "Emotes"
	title.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	title.horizontal_alignment = HORIZONTAL_ALIGNMENT_CENTER
	header.add_child(title)
	var close_button := Button.new()
	close_button.name = "EmotesClose"
	close_button.text = "X"
	close_button.pressed.connect(close)
	header.add_child(close_button)

	var categories_label := Label.new()
	categories_label.name = "CategoriesLabel"
	categories_label.text = "Categories"
	column.add_child(categories_label)
	category_list = ItemList.new()
	category_list.name = "CategoryList"
	category_list.custom_minimum_size = Vector2(0.0, 30.0)
	column.add_child(category_list)

	var emotes_label := Label.new()
	emotes_label.name = "EmotesLabel"
	emotes_label.text = "Emotes"
	column.add_child(emotes_label)
	emote_list = ItemList.new()
	emote_list.name = "EmoteList"
	emote_list.size_flags_vertical = Control.SIZE_EXPAND_FILL
	emote_list.item_selected.connect(_on_emote_selected)
	emote_list.item_activated.connect(_on_emote_activated)
	column.add_child(emote_list)

	var footer := HBoxContainer.new()
	footer.name = "EmotesFooter"
	column.add_child(footer)
	trigger_label = Label.new()
	trigger_label.name = "TriggerLine"
	trigger_label.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	footer.add_child(trigger_label)
	do_button = Button.new()
	do_button.name = "DoButton"
	do_button.text = "Do"
	do_button.disabled = true
	do_button.pressed.connect(_on_do_pressed)
	footer.add_child(do_button)
