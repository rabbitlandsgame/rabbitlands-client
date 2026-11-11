extends SceneTree
const Protocol := preload("res://src/network/protocol.gd")
const Tiers := preload("res://src/state/item_instance_tiers.gd")
const Icons := preload("res://src/ui/item_effect_icons.gd")
var failures := 0

func _init() -> void:
	call_deferred("_run")

func _expect(ok: bool, message: String) -> void:
	if not ok:
		failures += 1
		push_error(message)

func _run() -> void:
	OS.set_environment("ELORIA_NO_MAP_CACHE", "1")
	root.size = Vector2i(1280, 800)
	_expect(Icons.PATHS.size() == 32, "all 32 modifiers have unique artwork")
	for effect_name: String in Icons.PATHS:
		var icon := Icons.texture(effect_name)
		_expect(icon != null, effect_name + " artwork loads")
		if icon != null: _expect(icon.get_width() <= 128, effect_name + " imports at a small UI texture size")
	var proc := Icons.presentation("Renewal: 20% chance when hit to restore up to 10 health.")
	_expect(proc.roll == "20%" and proc.body == "When hit: restore up to 10 health.", "proc presentation retains the roll, trigger and strength")
	var stat := Icons.presentation("Vital: +50 maximum health.")
	_expect(stat.roll == "+50" and stat.body == "Maximum health.", "stat rolls are emphasized without losing their meaning")
	var state := root.get_node("AppState")
	var payload := PackedByteArray([2, 1, 0])
	# One structured storage row and a capability-gated enchanted-position tail.
	for value: int in [32768, 182]: _u16(payload, value)
	_u32(payload, 3)
	_u32(payload, 22)
	payload.append(4)
	payload.append_array("Phoenix Helm".to_utf8_buffer())
	payload.append(0)
	payload.append_array("Head".to_utf8_buffer())
	payload.append(0)
	var legacy: Dictionary = Protocol.decode_storage_state(payload)
	_expect(legacy.type == "storage_state", "legacy storage rows remain readable")
	_expect(not bool(legacy.enchanted_sent), "legacy storage rows do not claim an enchanted list")
	var read_only_only := payload.duplicate()
	read_only_only.append(1)
	var remote: Dictionary = Protocol.decode_storage_state(read_only_only)
	_expect(remote.type == "storage_state" and remote.read_only and not bool(remote.enchanted_sent),
		"an older server's read-only byte alone is not an enchanted list")
	var empty_list := payload.duplicate()
	empty_list.append_array(PackedByteArray([0, 0, 0]))
	_expect(bool(Protocol.decode_storage_state(empty_list).enchanted_sent), "an empty enchanted list still counts as sent")
	payload.append_array(PackedByteArray([0, 1, 0, 0, 128]))
	var grouped: Dictionary = Protocol.decode_storage_state(payload)
	_expect(grouped.type == "storage_state" and grouped.rows[0].enchanted, "the matching stack receives its enchanted marker")
	_expect(bool(grouped.enchanted_sent), "the enchanted list is reported as sent")
	var damaged := payload.slice(0, payload.size() - 1)
	_expect(Protocol.decode_storage_state(damaged).type == "invalid", "truncated markers are refused")
	var detail := PackedByteArray([182, 0, 1, 0, 0, 0, 0])
	for text: String in ["Phoenix Helm", "Armor", "head", "Four saved effects", "Armor 5", "", ""]:
		detail.append_array(text.to_utf8_buffer())
		detail.append(0)
	var untiered: Dictionary = Protocol.decode_item_detail(detail)
	_expect(untiered.instance_tier == "normal" and not bool(untiered.instance_tier_sent), "an older server's detail sends no tier")
	detail.append(2)
	_expect(Protocol.decode_item_detail(detail).instance_tier == "rare", "rare item details retain their tier")
	_expect(bool(Protocol.decode_item_detail(detail).instance_tier_sent), "the tier byte is reported as sent")
	_expect(Tiers.color("magic") != Tiers.color("rare"), "magic and rare names have different colors")
	var main: Control = (load("res://src/app/main.tscn") as PackedScene).instantiate()
	root.add_child(main)
	await process_frame
	main.get_node("LoginPanel").hide()
	main.get_node("LoginBackground").hide()
	main.get_node("GameView").show()
	state.set("storage", {"open": true, "category_id": 2,
		"categories": [{"id": 2, "name": "Armor"}],
		"items": {0: {"image_id": 182, "quantity": 12}, 32768: {"image_id": 182, "quantity": 3}},
		"described": {0: {"name": "Phoenix Helm", "subtype": "Head", "enchanted": false},
			32768: {"name": "Phoenix Helm", "subtype": "Head", "enchanted": true}}})
	main.call("_sync_storage")
	await process_frame
	var workspace: Node = main.get("classic_storage")
	var glowing: Button = workspace.get("_storage_cells")[32768]
	_expect(bool(glowing.get_meta("enchanted", false)), "the enchanted stack is visibly marked")
	workspace.call("_on_storage_cell_pressed", glowing.get_index())
	var ledger: PanelContainer = workspace.get("instance_ledger")
	_expect(ledger.visible, "one click on the enchanted stack opens its ledger")
	_expect(int(main.get("_storage_carried_position")) < 0, "opening the ledger does not carry or withdraw an arbitrary copy")
	var copies: Array = [
		{"instance_id": 501, "tier": "magic", "quality": 100, "durability": 94, "max_durability": 100,
			"effects": ["Emberstrike: 15% chance on a landed hit to deal 12 bonus damage.", "Renewal: 20% chance when hit to restore 10 health."]},
		{"instance_id": 502, "tier": "rare", "quality": 110, "durability": 96, "max_durability": 100,
			"effects": ["Plated: +20 armor.", "Vital: +50 maximum health.", "Spellguard: +25% less incoming spell damage.", "Restorative: +10 mana per normal regeneration tick."],
			"base_stats": "Armor 7-17, Defense -1, Max Health +12, Weight 18 EMU",
			"stats": "Armor 27-37, Defense -1, Max Health +62, Spell damage reduction +25%, Mana per regeneration tick +10, Weight 18 EMU"},
		{"instance_id": 503, "tier": "magic", "quality": 100, "durability": 91, "max_durability": 100,
			"effects": ["Renewal: 12% chance when hit to restore 14 health.", "Restorative: +10 mana per normal regeneration tick."]}]
	var snapshot := {"version": 1, "name": "Phoenix Helm", "image_id": 182,
		"total": 3, "offset": 0, "read_only": false, "error": "", "rows": copies}
	state.call("_on_packet", 187, JSON.stringify(snapshot).to_utf8_buffer())
	await process_frame
	_expect((ledger.get("rows") as VBoxContainer).get_child_count() == 3, "the ledger shows each individual copy")
	_expect((ledger.get("withdraw") as Button).disabled, "withdrawal requires an explicit selection")
	var selected_row := (ledger.get("rows") as VBoxContainer).get_child(1)
	(selected_row.find_child("SelectCopy", true, false) as Button).pressed.emit()
	_expect(int(ledger.get("selected_id")) == 502, "the portrait button selects that exact copy")
	_expect(not (ledger.get("withdraw") as Button).disabled, "selecting a specific copy enables withdrawal")
	_expect((ledger.get("summary") as Label).text.contains("4 saved effects"), "a rare copy displays all four effects")
	var name_label: Label = selected_row.find_child("ItemName", true, false)
	_expect(selected_row.find_child("Effects", true, false).get_child_count() == 4, "all four effects receive their own icon and text cell")
	var effect_cell: Control = selected_row.find_child("Effects", true, false).get_child(0)
	_expect(effect_cell.tooltip_text == copies[1].effects[0] and effect_cell.mouse_filter != Control.MOUSE_FILTER_IGNORE, "hovering an effect reveals its complete authoritative description")
	_expect(name_label.text == "Phoenix Helm", "the viewer retains the item name without a Magic or Rare prefix")
	_expect(name_label.get_theme_color("font_color") == Tiers.color("rare"), "the selected tier is conveyed by name color")
	var request: PackedByteArray = Protocol.storage_instance_request("Phoenix Helm", 0, 502)
	var command: Dictionary = JSON.parse_string(request.slice(3).get_string_from_utf8())
	_expect(command.instance_id == 502 and command.op == "withdraw", "the request addresses the selected object")
	for _frame: int in range(4): await process_frame
	var before_drag := ledger.position
	var grab_point := before_drag + Vector2(300, 36)
	var press := InputEventMouseButton.new()
	press.button_index = MOUSE_BUTTON_LEFT
	press.pressed = true
	press.position = grab_point
	press.global_position = grab_point
	root.push_input(press)
	var motion := InputEventMouseMotion.new()
	motion.position = grab_point - Vector2(20, 20)
	motion.global_position = motion.position
	motion.relative = Vector2(-20, -20)
	root.push_input(motion)
	press.pressed = false
	press.position = motion.position
	press.global_position = motion.position
	root.push_input(press)
	_expect(ledger.position.distance_to(before_drag - Vector2(20, 20)) < 1, "dragging the title content moves the ledger")
	ledger.set("_placed", false)
	ledger.call("_fit")
	for _frame: int in range(3): await process_frame
	print("Ledger layout: ", ledger.position, " ", ledger.size, " minimum ", ledger.get_combined_minimum_size())
	_expect(ledger.size.x <= 940 and ledger.size.y < 780, "the compact ledger stays inside the playable view")
	_expect(ledger.position.x >= 200, "the initial ledger leaves the storage stacks visible")
	if "--capture" in OS.get_cmdline_user_args():
		await RenderingServer.frame_post_draw
		DirAccess.make_dir_recursive_absolute(ProjectSettings.globalize_path("res://test-artifacts/equipment-instances"))
		root.get_texture().get_image().save_png("res://test-artifacts/equipment-instances/ledger-implemented.png")
	root.size = Vector2i(1024, 720)
	root.content_scale_size = Vector2i(1024, 720)
	for _frame: int in range(8): await process_frame
	print("Small ledger layout: ", ledger.get_viewport_rect().size, " ", ledger.position, " ", ledger.size)
	_expect(ledger.get_rect().end.x <= 1024 - 96 and ledger.get_rect().end.y <= 720 - 88, "the smaller layout stays clear of the fixed HUD")
	_expect((selected_row.find_child("Effects", true, false) as GridContainer).columns == 1, "smaller windows stack effect cells for readable text")
	var bar := (ledger.get("scroll") as ScrollContainer).get_v_scroll_bar()
	_expect(bar.max_value > bar.page, "a smaller window can scroll to every stored copy")
	if "--capture" in OS.get_cmdline_user_args():
		await RenderingServer.frame_post_draw
		root.get_texture().get_image().save_png("res://test-artifacts/equipment-instances/ledger-small.png")
	root.size = Vector2i(1280, 800)
	root.content_scale_size = Vector2i(1280, 800)
	for _frame: int in range(5): await process_frame
	snapshot.read_only = true
	state.call("_on_packet", 187, JSON.stringify(snapshot).to_utf8_buffer())
	_expect((ledger.get("withdraw") as Button).disabled, "preview storage cannot withdraw")
	state.call("close_storage")
	_expect(not ledger.visible, "closing storage closes the ledger")
	main.queue_free()
	await process_frame
	print("Equipment instances: ", failures, " failures")
	quit(0 if failures == 0 else 1)

func _u16(bytes: PackedByteArray, value: int) -> void:
	bytes.append(value & 255)
	bytes.append((value >> 8) & 255)

func _u32(bytes: PackedByteArray, value: int) -> void:
	_u16(bytes, value & 65535)
	_u16(bytes, value >> 16)
