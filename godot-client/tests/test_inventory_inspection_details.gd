extends SceneTree
## Authoritative equipment/instance text must survive every compact layout.
const Presets := preload("res://src/ui/inventory_presets.gd")
const Wire := preload("res://src/network/protocol.gd")
var failures := 0
var checks := 0
var main: Control

func _init() -> void: run.call_deferred()

func expect(value: bool, label: String) -> void:
	checks += 1
	if not value:
		failures += 1
		push_error(label)

func frames(count := 5) -> void:
	for index: int in count: await process_frame

func detail_packet() -> Dictionary:
	var fields: Array[String] = ["Phoenix Helm", "Armor", "head",
		"A phoenix-forged helm.\nObject #9856; Durability 79/100; Quality 93; Bound to Fixture; Created by Smith\nLegendary effects:\nMindfire: 20% chance on a landed hit to burn up to 12 mana and deal that much bonus damage.\nStoneward: 20% chance when hit to gain 5 temporary evasion, up to 15.",
		"Armor 8-12, Accuracy +2, Defense +3, Weight 4 EMU, Durability 79/100, Quality 93",
		"Iron Helm", "Armor +3/+5, Accuracy +2, Defense +1, Weight +1 EMU"]
	var payload := PackedByteArray()
	payload.resize(7)
	payload.encode_u16(0, 118)
	payload.encode_u32(2, 1)
	payload[6] = 0
	for value: String in fields:
		payload.append_array(value.to_utf8_buffer())
		payload.append(0)
	var parsed: Dictionary = Wire.decode_item_detail(payload)
	parsed["open"] = true
	return parsed

func run() -> void:
	create_timer(90).timeout.connect(func() -> void: quit(99))
	root.get_node("Network").block_for_hud_preview()
	root.size = Vector2i(1280, 720)
	main = (load("res://src/app/main.tscn") as PackedScene).instantiate()
	main.get_node("GameView/ChatWindow").preferences_path = "user://inspection-fixture.cfg"
	root.add_child(main)
	await frames(8)
	main.get_node("LoginPanel").hide()
	main.get_node("LoginBackground").hide()
	main.game_view.show()
	var app := root.get_node("AppState")
	app.set("inventory", {0: {"image_id": 118, "quantity": 1, "inventory_usable": false}})
	app.set("inventory_names", {0: "Phoenix Helm"})
	main.selected_inventory_slot = 0
	main.inventory_panel.show()
	main._sync_inventory()
	var workspace: Control = main.inventory_workspace
	var detail := detail_packet()
	expect(detail.type == "item_detail", "current item-detail packet decodes")
	for id: String in Presets.BUILT_INS:
		for ui_scale: float in [1.0, 0.75]:
			workspace.choose_preset(id, true)
			workspace.model.working.scale = ui_scale
			workspace.request_inspection(0, true)
			workspace.present_detail(detail, true)
			workspace.apply_layout()
			await frames()
			var label := "%s at %.2f" % [id, ui_scale]
			var text: RichTextLabel = workspace.inspection_text
			expect(workspace.groups.inspection.is_visible_in_tree(), label + " exposes the inspection surface")
			expect(text.text.contains(str(detail.stats)), label + " retains all equipment stats, durability and quality")
			expect(text.text.contains(str(detail.description)), label + " retains object identity and both complete legendary effects")
			expect(text.text.contains(str(detail.comparison)), label + " retains the equipped-item comparison")
			expect(text.scroll_active and text.size.x > 0 and text.size.y > 0, label + " gives overflowing details a usable scrolling region")
			var bar := text.get_v_scroll_bar()
			expect(bar.max_value > bar.page, label + " scrolls the long instance detail instead of clipping it")
			text.scroll_to_line(text.get_line_count() - 1)
			await frames(2)
			expect(bar.value > 0, label + " reaches the comparison at the bottom")
			workspace.close_inspection()
	# Loot/storage replies do not bind inventory actions to an unrelated slot.
	workspace.present_detail(detail, true)
	await frames()
	expect(workspace._detail_slot == -1 and main.extension_windows.detail_panel.visible,
		"external loot/storage details use the full inspection card")
	expect(workspace.inspection_text.text.contains(str(detail.description)), "external details retain all instance effects")
	print("INVENTORY INSPECTION DETAILS: ", checks, " checks, ", failures, " failures")
	main.queue_free()
	await frames()
	quit(1 if failures > 0 else 0)
