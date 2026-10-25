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
		add_child(button)
		buttons[action] = button
	confirmation = ConfirmationDialog.new()
	confirmation.title = "Drop all unprotected items?"
	confirmation.dialog_text = "Every unprotected backpack stack will be dropped.\nItems covered by your drop protection stay in your pack."
	confirmation.ok_button_text = "Drop unprotected items"
	confirmation.confirmed.connect(_dispatch.bind("drop"))
	add_child(confirmation)

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
	match action:
		"store": return bool(AppState.storage.get("open", false)) and not bool(AppState.storage.get("read_only", false)) and _has_backpack()
		"get": return main._ground_bag_below_player() >= 0
		"drop": return _has_backpack()
	return true

func _has_backpack() -> bool:
	for raw_slot: Variant in AppState.inventory:
		if int(raw_slot) >= 0 and int(raw_slot) < 36:
			return true
	return false

func refresh_enabled() -> void:
	for action: String in buttons:
		buttons[action].disabled = not available(action)
		buttons[action].tooltip_text = (sources[action] as Button).tooltip_text
	buttons.store.tooltip_text = "Store all unprotected stacks. Open storage first."
	buttons.get.tooltip_text = "Take items from the ground bag below you."
	buttons.drop.tooltip_text = "Confirm before dropping unprotected stacks."

func _process(_delta: float) -> void:
	if is_visible_in_tree(): refresh_enabled()

func _pressed(action: String) -> void:
	if not available(action): return
	if action == "drop": confirmation.popup_centered()
	else: _dispatch(action)

func _dispatch(action: String) -> void:
	# Context and editor mode can change while confirmation is open.
	if available(action): (sources[action] as Button).pressed.emit()
