extends SceneTree

var failures := 0
var main: Control

func _init() -> void:
	_run.call_deferred()

func expect(value: bool, message: String) -> void:
	if not value:
		failures += 1
		push_error(message)

func settle() -> void:
	for frame: int in 5:
		await process_frame

func capture(name: String) -> void:
	var directory := OS.get_environment("ELORIA_ARTIFACT_DIR")
	if directory.is_empty() or DisplayServer.get_name() == "headless": return
	await RenderingServer.frame_post_draw
	root.get_texture().get_image().save_png(directory.path_join(name + ".png"))

func _run() -> void:
	root.size = Vector2i(1280, 720)
	main = load("res://src/app/main.tscn").instantiate()
	root.add_child(main)
	await settle()
	main.get_node("%LoginPanel").hide()
	main.get_node("%CreationPanel").show()
	await settle()
	var create := main.get_node("CreationPanel/Columns/FormPanel/Form/Actions/Create") as Control
	expect(Rect2(Vector2.ZERO, Vector2(1280, 720)).encloses(create.get_global_rect()),
		"creation action stays on screen")
	expect((main.get_node("%CreatePants") as Control).size.x >= 180,
		"appearance choices have room for swatches and readable names")
	expect((main.get_node("%CreatePants") as Control).get_global_rect().end.y < create.get_global_rect().position.y,
		"appearance controls and creation action are visible together")
	await capture("creation-layout")
	(main.get_node("%ShowClassGear") as CheckBox).set_pressed_no_signal(false)
	main.call("_on_creation_class_gear_toggled", false)
	var trousers := main.get_node("%CreatePants") as OptionButton
	var cream := trousers.get_item_index(10)
	trousers.select(cream)
	trousers.item_selected.emit(cream)
	await settle()
	await capture("cream-trousers")
	main.get_node("%CreationPanel").hide()
	main.get_node("%GameView").show()
	var state := root.get_node("AppState")
	state.set("authenticated", true)
	var windows: Control = main.get("extension_windows")
	state.set("merchant", {"open": true, "actor_id": 91, "npc_name": "Bettany Orl",
		"gold": 200, "carried": 10, "capacity": 80, "items": [
			{"index": 1, "name": "Raw Meat", "image_id": 1, "owned": 106, "buy_price": 4, "sell_price": 2, "emu": 1},
			{"index": 2, "name": "Bread", "image_id": 2, "owned": 2, "buy_price": 5, "sell_price": 1, "emu": 1}]})
	windows._sync_merchant()
	windows._on_merchant_mode("sell")
	windows.merchant_quantity.text = "106"
	state.get("merchant").items[0].owned = 0
	windows._sync_merchant()
	expect(windows._merchant_entry().is_empty() and windows.merchant_trade.disabled,
		"selling a complete stack does not select a different item")
	expect(windows.merchant_quantity.text == "1", "vanished selection clears the previous quantity")
	windows.merchant_sell_list.select(0)
	windows._on_merchant_selected(0, "sell")
	windows.merchant_quantity.text = "106"
	windows._sync_merchant_summary()
	expect(not windows.merchant_totals.text.contains("Gold after"), "invalid quantities do not preview imaginary balances")
	state.call("close_merchant")
	state.set("npc_dialogue", {"open": true, "name": "Bettany Orl", "text": "", "options": []})
	main.call("_sync_dialogue")
	expect(not (main.get_node("%DialoguePanel") as Control).visible, "an empty merchant dialogue stays closed")
	state.set("inventory", {0: {"image_id": 505, "quantity": 1}})
	state.set("inventory_names", {0: "Deer Hide"})
	main.call("_sync_inventory")
	expect(main.call("_inventory_tooltip", state.get("inventory")[0], 0).begins_with("Deer Hide"),
		"authoritative names resolve newly looted items")
	state.call("_on_packet", EloriaProtocol.ServerMessage.INVENTORY_ITEM_TEXT,
		PackedByteArray([0]) + "You made Bandage and gained 5 potion experience.".to_utf8_buffer())
	await create_timer(8.1).timeout
	expect(state.get("inventory_text").is_empty(), "crafting messages expire")
	expect(not str((main.get("inventory_description") as Control).get("text")).contains("You made"),
		"expired status does not replace the current item description")
	var guide: Control = main.get("lantern_guide")
	(main.get_node("%ManufacturingPanel") as Control).show()
	guide.call("apply_state", {"active": true, "title": "Prepare the medicine", "hint":
		"At the healer's table, mix 2 Sage and 1 Cloth Roll using Mortar and Pestle. Keep food above zero.",
		"action": "manufacture", "item": "Bandage"})
	await settle()
	var mixing := main.get_node("%ManufacturingPanel") as Control
	var action := main.get_node("%ManufacturingMixOne") as Control
	expect(mixing.get_global_rect().end.y <= 680, "docked guide clears the bottom toolbar")
	expect(mixing.get_global_rect().encloses(action.get_global_rect()), "docked guide keeps Mix Now inside the panel")
	await capture("crafting-guide-layout")
	guide.hide()
	mixing.hide()
	main.call("_apply_minimap_scale")
	var minimap: Control = main.get("minimap_frame")
	minimap.position = Vector2(10000, 10000)
	main.call("_apply_minimap_scale")
	expect(minimap.get_rect().end.x <= 1184 and minimap.get_rect().end.y <= 680,
		"minimap cannot cover the rail or toolbar")
	var canvas := InvasionMapCanvas.new()
	root.add_child(canvas)
	canvas.size = Vector2(400, 300)
	var creatures: Array[Dictionary] = []
	for index: int in 1400:
		creatures.append({"name": "Rabbit", "x": 90 if index == 0 else 10, "y": 20, "boss": index == 0})
	canvas.set_map_state({"map": {"width": 100, "height": 100}, "creatures": creatures})
	var clusters := canvas._creature_clusters()
	expect(clusters.size() == 1 and clusters[0].count == 1399, "dense map groups ordinary creatures and keeps bosses separate")
	canvas._update_hover(clusters[0].position)
	expect(canvas.tooltip_text.contains("1399"), "cluster hover reports the complete count")
	var sample := Image.create(2, 1, false, Image.FORMAT_RGBA8)
	sample.set_pixel(0, 0, Color(0.3, 0.12, 0.04))
	sample.set_pixel(1, 0, Color(0.6, 0.24, 0.08))
	var source := ImageTexture.create_from_image(sample)
	var neutral := ReplicatedActor3D._wardrobe_dye_texture(source).get_image()
	var dyed := neutral.get_pixel(1, 0)
	expect(is_equal_approx(dyed.r, dyed.g) and is_equal_approx(dyed.g, dyed.b) and dyed.r > 0.9,
		"light wardrobe dyes use neutral fabric instead of baked brown")
	expect(source.get_image().get_pixel(0, 0).r > source.get_image().get_pixel(0, 0).g,
		"dye conversion preserves the source atlas")
	var assistant := InvasionAssistantWindow.new()
	root.add_child(assistant)
	assistant.show()
	assistant.position = Vector2i(9000, 9000)
	assistant.tabs.current_tab = 1
	await settle()
	expect(assistant.position.x + assistant.size.x <= 1184
		and assistant.position.y + assistant.size.y <= 680,
		"dragged assistant stays visible even outside the map tab")
	assistant.queue_free()
	var camera: Camera3D = main.get("gameplay_camera")
	camera.global_position = Vector3(0, 8, 10)
	camera.look_at(Vector3(0, 1, 0))
	var nodes: Dictionary = main.get("actor_nodes")
	for id: int in [901, 902, 903]:
		var actor := ReplicatedActor3D.new()
		(main.get("world_root") as Node).add_child(actor)
		var dto := {"actor_id": id, "x": 0, "y": 0, "rotation": 0,
			"actor_type": 1, "kind": ReplicatedActor3D.CREATURE_ACTOR_KIND,
			"name": "Rabbit", "health": 10, "max_health": 10}
		actor.configure(dto, CoordinateAdapter.new({"metresPerTile": 1.0}), {}, {})
		nodes[id] = actor
		state.get("actors")[id] = dto
	main.call("_declutter_actor_overheads", 902)
	expect(not nodes[902].get("_overhead_crowded") and nodes[901].get("_overhead_crowded")
		and nodes[903].get("_overhead_crowded"), "combat target retains its banner when crowd banners overlap")
	main.call("_spawn_health_change_label", nodes[902], -5)
	main.call("_spawn_health_change_label", nodes[902], -7)
	var damage_rows := 0
	for label: Label in main.get("_active_floating_labels"):
		if int(label.get_meta("feedback_actor", -1)) == 902:
			damage_rows += 1
			expect(label.text == "-12", "damage bursts show their combined amount")
	expect(damage_rows == 1, "damage bursts share one floating label")
	for id: int in [901, 902, 903]:
		nodes[id].queue_free()
		nodes.erase(id)
		state.get("actors").erase(id)
	state.set("authenticated", false)
	canvas.queue_free()
	main.queue_free()
	await process_frame
	ReplicatedActor3D.clear_wardrobe_texture_cache()
	print("recording regressions: %d failures" % failures)
	quit(failures)
