extends SceneTree
const Presets := preload("res://src/ui/inventory_presets.gd")
var main: Control
var checks := 0
var failures := 0

func _init() -> void: run.call_deferred()

func expect(value: bool, label: String) -> void:
	checks += 1
	if not value:
		failures += 1
		push_error(label)

func frames(count := 4) -> void:
	for index: int in count: await process_frame

func run() -> void:
	create_timer(90).timeout.connect(func() -> void: quit(99))
	root.get_node("Network").block_for_hud_preview()
	root.size = Vector2i(1280, 720)
	main = (load("res://src/app/main.tscn") as PackedScene).instantiate()
	main.get_node("GameView/ChatWindow").preferences_path = "user://expanded-mix-fixture.cfg"
	root.add_child(main)
	await frames(8)
	main.get_node("LoginPanel").hide()
	main.get_node("LoginBackground").hide()
	main.game_view.show()
	var app := root.get_node("AppState")
	var workspace: Control = main.inventory_workspace
	app.set("inventory", {0: {"image_id": 618, "quantity": 1}})
	app.set("inventory_names", {0: "Enriched Fire Essence"})
	main.selected_inventory_slot = -1
	main.inventory_panel.show()
	workspace._detail_slot = 0
	workspace._detail = {"image_id": 618, "name": "Enriched Fire Essence", "stats": "Original item statistics", "description": "Original item description"}
	var recipe: Dictionary = main.manufacturing_catalog.recipe(0)
	var output: String = recipe.output
	for preset: String in Presets.BUILT_INS:
		workspace.choose_preset(preset, true)
		app.set("inventory_text", "")
		main._mix_pending.assign([{"output": output}])
		main._sync_inventory()
		workspace.inspect_selected()
		await frames()
		expect(workspace.groups.inspection.is_visible_in_tree(), preset + " expands mixing without a selected slot")
		expect(workspace.inspection_icon.texture != null and workspace.inspection_icon.texture == workspace.preview_icon.texture, preset + " shows the active recipe icon")
		expect(workspace.inspection_text.text == main.inventory_description.text and workspace.inspection_text.text.begins_with("Mixing "), preset + " mirrors active mixing text")
		for result: Array in [[10, "You made " + output + " and gained 5 manufacturing experience.", Color("66dd88")],
			[0, "You failed to make " + output + ".", Color("ff6666")],
			[0, "You critically failed to make " + output + "; the ingredients were lost.", Color("ff6666")],
			[4, "You made Enriched Fire Essence and gained 8 alchemy experience.", Color("ffd166")]]:
			# Use the real server encoding, not a bare color index.
			app.call("_on_packet", EloriaProtocol.ServerMessage.INVENTORY_ITEM_TEXT,
				PackedByteArray([127 + result[0]]) + str(result[1]).to_utf8_buffer() + PackedByteArray([0]))
			workspace.apply_layout()
			await frames()
			expect(main.inventory_description.get_theme_color("default_color") == result[2], preset + " compact result color")
			expect(workspace.inspection_text.get_theme_color("default_color") == result[2], preset + " expanded result color survives layout")
			expect(workspace.inspection_text.text == main.inventory_description.text, preset + " mirrors result text")
			expect(workspace.inspection_icon.texture != null and workspace.inspection_icon.texture == workspace.preview_icon.texture, preset + " mirrors result icon")
			for button: Button in workspace.inspection_actions.get_children():
				expect(not button.visible, preset + " hides unrelated item actions while showing mix feedback")
		workspace.close_inspection()
	main._mix_pending.clear()
	app.set("inventory_text", "")
	main._sync_inventory()
	expect(main.inventory_description.get_theme_color("default_color") == Color.WHITE, "cleared feedback restores normal preview color")
	expect(workspace.inspection_text.get_theme_color("default_color") == workspace.model.working.text, "cleared feedback restores normal detail color")
	expect(workspace.inspection_text.text.contains("Original item statistics") and workspace.inspection_text.text.contains("Original item description"), "cleared feedback restores the inspected item details")
	print("EXPANDED MIX FEEDBACK: ", checks, " checks, ", failures, " failures")
	main.queue_free()
	await frames()
	quit(1 if failures else 0)
