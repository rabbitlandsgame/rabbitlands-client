extends GridContainer
## Optional visible shortcuts to the existing protected inventory actions.
const ACTIONS := {"store": "Store all", "get": "Get all", "drop": "Drop all",
	"mix": "Mix all", "lists": "Lists"}
const Chrome := preload("res://src/ui/compact_hud_style.gd")
var main: Control
var workspace: Control
var buttons: Dictionary = {}
var sources: Dictionary = {}
var confirmation: ConfirmationDialog
var mix_options: PopupMenu

func configure(owner_main: Control, owner_workspace: Control) -> void:
	main = owner_main
	workspace = owner_workspace
	name = "InventoryBulkActions"
	add_theme_constant_override("h_separation", 4)
	add_theme_constant_override("v_separation", 4)
	sources = {"store": main.inventory_store_all, "get": main.inventory_get_all,
		"drop": main.inventory_drop_all, "mix": main.inventory_mix_all,
		"lists": main.inventory_item_lists}
	for action: String in ACTIONS:
		var button := Button.new()
		button.name = action.to_pascal_case()
		button.text = ACTIONS[action]
		button.size_flags_horizontal = Control.SIZE_EXPAND_FILL
		button.custom_minimum_size.y = 24
		Chrome.button(button)
		button.pressed.connect(_pressed.bind(action))
		if action in ["store", "drop", "mix"]:
			button.gui_input.connect(shortcut_input.bind(action, button))
		add_child(button)
		buttons[action] = button
	confirmation = ConfirmationDialog.new()
	confirmation.title = "Drop all unprotected items?"
	confirmation.dialog_text = "Every unprotected backpack and pouch stack will be dropped.\nProtected backpack slots stay in your pack."
	confirmation.ok_button_text = "Drop unprotected items"
	confirmation.confirmed.connect(_dispatch.bind("drop"))
	add_child(confirmation)
	mix_options = PopupMenu.new()
	mix_options.name = "MixOptions"
	mix_options.about_to_popup.connect(_refresh_mix_options)
	mix_options.id_pressed.connect(_mix_option_selected)
	add_child(mix_options)


func apply_options(part: Dictionary) -> int:
	columns = clampi(int(part.get("columns", 3)), 1, 5)
	var count := 0
	for action: String in ACTIONS:
		buttons[action].visible = part.get("show_" + action, true) == true
		count += int(buttons[action].visible)
	refresh_enabled()
	return ceili(float(count) / columns) * 28 if count else 0

func available(action: String) -> bool:
	if workspace.is_editing() or not is_instance_valid(sources.get(action)):
		return false
	if (sources[action] as Button).disabled:
		return false
	if action in ["store", "drop", "mix"] and AppState.trade.get("open", false):
		return false
	match action:
		"store": return bool(AppState.storage.get("open", false)) and not bool(AppState.storage.get("read_only", false)) and _has_backpack()
		"get": return main._ground_bag_below_player() >= 0
		"drop": return _has_backpack()
	return true

func _has_backpack() -> bool:
	for raw_slot: Variant in AppState.inventory:
		if int(raw_slot) >= 0 and (int(raw_slot) < 24 or int(raw_slot) >= 127):
			return true
	return false

func refresh_enabled() -> void:
	for action: String in buttons:
		buttons[action].disabled = not available(action)
		buttons[action].tooltip_text = (sources[action] as Button).tooltip_text
	buttons.store.tooltip_text = "Store all unprotected stacks. Middle-click: protection options. Open storage first."
	buttons.get.tooltip_text = "Take items from the ground bag below you."
	buttons.drop.tooltip_text = "Drop all unprotected stacks. Middle-click: protection options."
	buttons.mix.tooltip_text = "Mix all available ingredients for the selected recipe. Middle-click: mixing options."

func _process(_delta: float) -> void:
	if is_visible_in_tree(): refresh_enabled()

func _pressed(action: String) -> void:
	if not available(action): return
	if action == "drop": confirmation.popup_centered()
	else: _dispatch(action)

func _dispatch(action: String) -> void:
	# Context and editor mode can change while confirmation is open.
	if available(action): (sources[action] as Button).pressed.emit()

func shortcut_input(event: InputEvent, action: String, button: Button) -> void:
	if not event is InputEventMouseButton or not event.pressed or workspace.is_editing(): return
	if event.button_index == MOUSE_BUTTON_RIGHT:
		_pressed(action)
	elif event.button_index == MOUSE_BUTTON_MIDDLE:
		open_options(action, button.global_position + Vector2(0, button.size.y))
	else: return
	button.accept_event()

func open_options(action: String, where: Vector2) -> void:
	if workspace.is_editing(): return
	var menu: PopupMenu
	match action:
		"store": menu = main._store_options_menu
		"drop": menu = main._drop_options_menu
		"mix": menu = mix_options
		_: return
	menu.position = Vector2i(where)
	menu.popup()

func _refresh_mix_options() -> void:
	mix_options.clear()
	var recipe: Dictionary = main.manufacturing_catalog.recipe(main.selected_manufacturing_recipe)
	mix_options.add_item("Recipe: " + str(recipe.get("output", "Choose a recipe")), 10)
	mix_options.set_item_disabled(0, true)
	mix_options.add_item("Choose recipe and quantity…", 0)
	mix_options.add_separator()
	mix_options.add_radio_check_item("Use inventory ingredients", 1)
	mix_options.add_radio_check_item("Use nearby storage ingredients", 2)
	var use_storage: bool = main._manufacturing_from_storage()
	mix_options.set_item_checked(mix_options.get_item_index(1), not use_storage)
	mix_options.set_item_checked(mix_options.get_item_index(2), use_storage)
	mix_options.set_item_disabled(mix_options.get_item_index(2), not AppState.mix_state.get("near_storage", false))

func _mix_option_selected(id: int) -> void:
	if workspace.is_editing(): return
	if id == 0:
		if AppState.trade.get("open", false): return
		main.manufacturing_panel.show()
		main.manufacturing_panel.move_to_front()
		main._sync_manufacturing()
	elif id == 1:
		main.manufacturing_source.button_pressed = false
	elif id == 2 and AppState.mix_state.get("near_storage", false):
		main.manufacturing_source.button_pressed = true
