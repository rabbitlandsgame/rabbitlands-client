extends Control
## The summoning window: every creature this profile can call up, one to a
## row, with what it costs written beside it.
##
## Summoning is a mixing skill, so the server already answers it through the
## manufacture window's packet - a summon is a recipe whose result is a
## creature instead of an item. That window lists all thirty-two recipes and
## asks the player to pick the summons out of them. This is the spell book's
## treatment of the same data: the summons alone, each with its ingredients,
## its nexus and its mana where they can be read, and one click to call it.
##
## Everything on it is a rendering of what the client honestly knows. The
## recipes are the client's own compiled catalog; the ingredients, the skill,
## the nexus and the ether are the server's state as it last arrived in
## `AppState`. A summon the client can see no way to make is dimmed with its
## first blocking reason beside it, the way the spell book dims a spell - but
## the window never decides whether a summon happens. Clicking only asks; the
## server owns the ingredients, the mana and the dice.
##
## The script declares no `class_name`: a global class is parsed before the
## autoload singletons are registered, and this reads `AppState` directly.

## Wide enough for the longest ingredient line the profile can produce - the
## turtle's four reagents - beside a name and an icon, because a summon whose
## cost is ellipsised is a summon whose cost has to be guessed at.
const PANEL_SIZE := Vector2(700.0, 360.0)
## The name column. Fixed rather than shrink-to-fit so the three cost lines
## start at the same place and can be read down the window as a column.
const NAME_WIDTH := 150.0
## Nothing may cover the fixed resource rail down the right-hand edge.
const RESERVED_RIGHT_RAIL := 96.0

## EL dims what you cannot do rather than hiding it, so it can still be read.
const BLOCKED_ALPHA := 0.45
const BLOCKED_COLOR := Color(1.0, 0.36, 0.36)
const READY_COLOR := Color(0.85, 1.0, 0.85)
const COST_COLOR := Color(0.72, 0.78, 0.9)
const ICON_SIZE := Vector2(32.0, 32.0)
const ROW_HEIGHT := 44.0

var catalog: ManufacturingCatalog
var atlas: ItemAtlas

var panel: PanelContainer
var rows_box: VBoxContainer
var status_label: Label
var behavior_button: Button

var _summon: Callable = Callable()
var _behavior: Callable = Callable()
## Recipe index to its row Button, for re-dimming without a rebuild.
var _rows: Dictionary = {}
## Recipe index to the Array[String] of everything blocking it, as this
## window last computed it from the server's state. Empty means the client
## can see no reason the summon would be refused.
var _reasons: Dictionary = {}
## Recipe index to the {slot, quantity} ingredient picks the catalog chose,
## which is what the manufacture packet is built from.
var _selections: Dictionary = {}

func _ready() -> void:
	name = "SummoningLayer"
	mouse_filter = Control.MOUSE_FILTER_IGNORE
	set_anchors_and_offsets_preset(Control.PRESET_FULL_RECT)
	_build()
	AppState.state_changed.connect(_on_state_changed)

func configure(manufacturing_catalog: ManufacturingCatalog, item_atlas: ItemAtlas,
		summon: Callable, behavior: Callable) -> void:
	catalog = manufacturing_catalog
	atlas = item_atlas
	_summon = summon
	_behavior = behavior
	_populate()
	sync()

func is_open() -> bool:
	return panel.visible

func toggle() -> void:
	panel.visible = not panel.visible
	if panel.visible:
		panel.move_to_front()
		sync()

func close() -> void:
	panel.hide()

## Every recipe in the compiled catalog that summons something, in the order
## the server declared them - which is also cheapest first.
func summon_recipes() -> Array[int]:
	var found: Array[int] = []
	if catalog == null:
		return found
	for index: int in range(catalog.count()):
		if str(catalog.recipe(index).get("skill", "")) == "summoning":
			found.append(index)
	return found

## Everything the client can see standing between the player and this summon.
##
## The shared catalog answers for ingredients, tools, books, food and ether.
## The two requirements only summoning has - the skill level and the Animal
## Nexus the creature costs - are added here, because the manufacture window
## has never asked about either and this window would otherwise offer a
## summon the server is certain to turn down.
func blocking_reasons(index: int) -> Array[String]:
	var reasons: Array[String] = []
	if catalog == null:
		return ["No recipe catalog"]
	var definition: Dictionary = catalog.recipe(index)
	if definition.is_empty():
		return ["Unknown recipe"]
	var stats: Dictionary = AppState.stats
	if stats.is_empty():
		reasons.append("Waiting for server statistics")
	else:
		var level: int = int(definition.get("level", 0))
		if int(stats.get("summoning", 0)) < level:
			reasons.append("Needs summoning level %d" % level)
		var nexus: int = int(definition.get("animalNexus", 0))
		if nexus > 0 and int(stats.get("animal_nexus", 0)) < nexus:
			reasons.append("Needs Animal Nexus %d" % nexus)
	var availability: Dictionary = catalog.availability(
		index, AppState.inventory, AppState.known_knowledge, stats,
		AppState.inventory_names)
	for reason: Variant in availability.get("reasons", []) as Array:
		reasons.append(str(reason))
	return reasons

func _on_state_changed(path: StringName) -> void:
	if path == &"inventory" or path == &"stats" or path == &"knowledge":
		sync()

## Re-asks what blocks every summon, dims accordingly and rewrites the costs.
## Everything it reads is the server's last word held in AppState.
func sync() -> void:
	if not panel.visible or catalog == null:
		return
	_reasons.clear()
	_selections.clear()
	for index: int in summon_recipes():
		var reasons: Array[String] = blocking_reasons(index)
		_reasons[index] = reasons
		_selections[index] = (catalog.availability(
			index, AppState.inventory, AppState.known_knowledge,
			AppState.stats, AppState.inventory_names).get("selection", []) as Array)
		var row: Button = _rows.get(index) as Button
		if row == null:
			continue
		row.disabled = not reasons.is_empty()
		row.modulate = Color(1.0, 1.0, 1.0,
			1.0 if reasons.is_empty() else BLOCKED_ALPHA)
		row.tooltip_text = ("Click to summon" if reasons.is_empty()
			else "\n".join(reasons))
		var note: Label = row.get_node("Row/Asks/Requirements") as Label
		note.text = _requirements_line(catalog.recipe(index), reasons)
		note.add_theme_color_override("font_color",
			READY_COLOR if reasons.is_empty() else BLOCKED_COLOR)
	if behavior_button != null:
		# The behaviour popup is the server's, and it refuses below summoning
		# thirty. Saying so here is cheaper than sending a request to be told.
		var trained: bool = int(AppState.stats.get("summoning", 0)) >= 30
		behavior_button.disabled = not trained
		behavior_button.tooltip_text = ("Choose how your summons pick targets"
			if trained else "Summoning level 30 sets summon behaviour")

## The first blocking reason, or the ingredients when nothing blocks. A player
## who can summon wants to know what it will cost them; a player who cannot
## wants to know why, and the reason is worth more than the list.
func _requirements_line(definition: Dictionary, reasons: Array[String]) -> String:
	if not reasons.is_empty():
		return str(reasons[0])
	var parts: Array[String] = []
	for ingredient_value: Variant in definition.get("ingredients", []) as Array:
		if ingredient_value is Dictionary:
			var ingredient: Dictionary = ingredient_value as Dictionary
			parts.append("%s x%d" % [str(ingredient.get("name", "?")),
				int(ingredient.get("quantity", 0))])
	return "  ".join(parts) if not parts.is_empty() else "No ingredients"

## What the summon costs, whether or not it can be paid right now.
func _cost_line(definition: Dictionary) -> String:
	var parts: Array[String] = ["Summoning %d" % int(definition.get("level", 0))]
	var nexus: int = int(definition.get("animalNexus", 0))
	if nexus > 0:
		parts.append("Animal Nexus %d" % nexus)
	parts.append("Mana %d" % int(definition.get("mana", 0)))
	var food: int = int(definition.get("food", 0))
	if food > 0:
		parts.append("Food %d" % food)
	parts.append("%d xp" % int(definition.get("experience", 0)))
	return "   ".join(parts)

## Only asks. The server owns the ingredients, the ether and the roll, so it
## alone decides whether anything is standing there afterwards.
func _on_row_pressed(index: int) -> void:
	var reasons: Array = _reasons.get(index, []) as Array
	var selection: Array = _selections.get(index, []) as Array
	if not reasons.is_empty() or selection.is_empty():
		status_label.text = ("Cannot summon: %s" % str(reasons[0])
			if not reasons.is_empty() else "Nothing to summon with.")
		return
	if not _summon.is_valid():
		return
	var typed_selection: Array[Dictionary] = []
	for selection_value: Variant in selection:
		if selection_value is Dictionary:
			typed_selection.append(selection_value as Dictionary)
	_summon.call(typed_selection)
	status_label.text = "Summon requested; awaiting the server."

func _on_behavior_pressed() -> void:
	if _behavior.is_valid():
		_behavior.call()
		status_label.text = "Asked the server for the behaviour popup."

## One row per summon: icon and name on the left, what it asks for on the
## right. The row is the button, so the whole line is the click target.
func _populate() -> void:
	for child: Node in rows_box.get_children():
		rows_box.remove_child(child)
		child.free()
	_rows.clear()
	if catalog == null:
		return
	for index: int in summon_recipes():
		var definition: Dictionary = catalog.recipe(index)
		var row := Button.new()
		row.name = "SummonRow%d" % index
		row.custom_minimum_size = Vector2(0.0, ROW_HEIGHT)
		# Disabled until the first sync has weighed it against the server's
		# state: a row nothing has checked yet should not be clickable.
		row.disabled = true
		row.pressed.connect(_on_row_pressed.bind(index))
		rows_box.add_child(row)
		_rows[index] = row

		# A Button lays nothing out for itself, so the row's contents are a
		# container pinned across it, and every child ignores the mouse so
		# the press still belongs to the button underneath.
		var line := HBoxContainer.new()
		line.name = "Row"
		line.set_anchors_and_offsets_preset(Control.PRESET_FULL_RECT)
		line.mouse_filter = Control.MOUSE_FILTER_IGNORE
		line.add_theme_constant_override("separation", 8)
		row.add_child(line)

		var icon := TextureRect.new()
		icon.name = "Icon"
		icon.custom_minimum_size = ICON_SIZE
		icon.expand_mode = TextureRect.EXPAND_IGNORE_SIZE
		icon.stretch_mode = TextureRect.STRETCH_KEEP_ASPECT_CENTERED
		icon.mouse_filter = Control.MOUSE_FILTER_IGNORE
		icon.texture = _icon_for(definition)
		line.add_child(icon)

		var title := Label.new()
		title.name = "Name"
		title.text = str(definition.get("output", "Unknown"))
		title.custom_minimum_size = Vector2(NAME_WIDTH, 0.0)
		title.vertical_alignment = VERTICAL_ALIGNMENT_CENTER
		title.mouse_filter = Control.MOUSE_FILTER_IGNORE
		line.add_child(title)

		# Everything the summon asks for stands to the right of the icon and
		# the name: what it spends on the first line, what it demands of the
		# summoner on the second. Right-aligned so the three rows line up
		# against the window's edge rather than against each other's lengths.
		var asks := VBoxContainer.new()
		asks.name = "Asks"
		asks.size_flags_horizontal = Control.SIZE_EXPAND_FILL
		asks.alignment = BoxContainer.ALIGNMENT_CENTER
		asks.mouse_filter = Control.MOUSE_FILTER_IGNORE
		asks.add_theme_constant_override("separation", 0)
		line.add_child(asks)

		var requirements := Label.new()
		requirements.name = "Requirements"
		requirements.mouse_filter = Control.MOUSE_FILTER_IGNORE
		requirements.horizontal_alignment = HORIZONTAL_ALIGNMENT_RIGHT
		requirements.autowrap_mode = TextServer.AUTOWRAP_OFF
		requirements.text_overrun_behavior = TextServer.OVERRUN_TRIM_ELLIPSIS
		asks.add_child(requirements)

		var cost := Label.new()
		cost.name = "Cost"
		cost.text = _cost_line(definition)
		cost.mouse_filter = Control.MOUSE_FILTER_IGNORE
		cost.horizontal_alignment = HORIZONTAL_ALIGNMENT_RIGHT
		cost.autowrap_mode = TextServer.AUTOWRAP_OFF
		cost.text_overrun_behavior = TextServer.OVERRUN_TRIM_ELLIPSIS
		cost.add_theme_color_override("font_color", COST_COLOR)
		asks.add_child(cost)

## A summon leaves no item behind, so its recipe carries no output image and
## the client has no picture of the creature. The atlas keeps one glyph for
## exactly this, and the name is right beside it.
func _icon_for(definition: Dictionary) -> Texture2D:
	if atlas == null:
		return null
	var icon: Texture2D = atlas.icon_for(int(definition.get("outputImageId", -1)))
	return icon if icon != null else atlas.placeholder_icon()

func _build() -> void:
	panel = PanelContainer.new()
	panel.name = "SummoningWindow"
	panel.mouse_filter = Control.MOUSE_FILTER_STOP
	# Beside the spell book rather than on top of it: a summoner keeps both
	# open, and two windows that open in the same place are one window.
	panel.position = Vector2(
		(1280.0 - RESERVED_RIGHT_RAIL - PANEL_SIZE.x) * 0.5 + 40.0, 150.0)
	panel.custom_minimum_size = PANEL_SIZE
	panel.size = PANEL_SIZE
	panel.hide()
	add_child(panel)

	var column := VBoxContainer.new()
	column.name = "SummoningBody"
	panel.add_child(column)

	var header := HBoxContainer.new()
	header.name = "SummoningHeader"
	column.add_child(header)
	WindowDrag.attach(panel, header)
	var title := Label.new()
	title.name = "SummoningTitle"
	title.text = "Summoning"
	title.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	title.horizontal_alignment = HORIZONTAL_ALIGNMENT_CENTER
	header.add_child(title)
	behavior_button = Button.new()
	behavior_button.name = "SummoningBehavior"
	behavior_button.text = "Behaviour"
	behavior_button.pressed.connect(_on_behavior_pressed)
	header.add_child(behavior_button)
	var close_button := Button.new()
	close_button.name = "SummoningClose"
	close_button.text = "X"
	close_button.pressed.connect(close)
	header.add_child(close_button)

	var scroll := ScrollContainer.new()
	scroll.name = "SummoningScroll"
	scroll.size_flags_vertical = Control.SIZE_EXPAND_FILL
	scroll.horizontal_scroll_mode = ScrollContainer.SCROLL_MODE_DISABLED
	column.add_child(scroll)
	rows_box = VBoxContainer.new()
	rows_box.name = "SummonRows"
	rows_box.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	scroll.add_child(rows_box)

	status_label = Label.new()
	status_label.name = "SummoningStatus"
	status_label.text = "Click a summon to call it. The server decides."
	status_label.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
	column.add_child(status_label)
