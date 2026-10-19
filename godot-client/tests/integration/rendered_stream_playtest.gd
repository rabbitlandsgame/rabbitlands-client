extends SceneTree

func _init() -> void:
	call_deferred("run")

func run() -> void:
	root.size = Vector2i(1280, 720)
	var main: Control = load("res://src/app/main.tscn").instantiate()
	root.add_child(main)
	await process_frame
	main.set_process(false)
	main.get_node("LoginPanel").hide()
	main.get_node("GameView").show()
	var state := root.get_node("AppState")
	state.authenticated = true
	state.stats = {"food": 0, "ether": 0}
	main.manufacturing_catalog.configure({"recipes": [{"output": "Potion of Minor Healing", "skill": "potion", "level": 0,
		"ingredients": [{"name": "Sage", "quantity": 2}], "tools": [{"name": "Mortar and Pestle"}], "mana": 1}]})
	main.manufacturing_ready_preference = false
	main.selected_manufacturing_recipe = 0
	main.manufacturing_panel.show()
	main._settle_mix_run({"entry": -1, "output": "Potion of Minor Healing"}, 0)
	main._sync_manufacturing()
	main.manufacturing_panel.show()
	main.casting_bar.set_visible_slot_count(12)
	main.casting_bar.set_horizontal(true)
	main.casting_bar.set_expanded(true)
	var folder := ProjectSettings.globalize_path("res://test-artifacts/stream-playtest")
	DirAccess.make_dir_recursive_absolute(folder)
	for i in range(12): await process_frame
	await RenderingServer.frame_post_draw
	root.get_texture().get_image().save_png(folder.path_join("crafting-horizontal.png"))
	main.manufacturing_panel.hide()
	state.combat_state = {"active": true, "target_name": "Dread Chord", "target_health": 34, "target_max_health": 80, "player_health": 18, "player_max_health": 20, "event": 1, "damage": 8}
	main.extension_windows.combat_hud_enabled = true
	main.extension_windows._sync_combat()
	for i in range(4): await process_frame
	await RenderingServer.frame_post_draw
	root.get_texture().get_image().save_png(folder.path_join("combat-horizontal.png"))
	main.spell_wheel.can_open = func(): return true
	main.spell_loadout.set_mode("wheel")
	main.spell_wheel.open_wheel()
	for i in range(4): await process_frame
	await RenderingServer.frame_post_draw
	root.get_texture().get_image().save_png(folder.path_join("spell-wheel.png"))
	main.spell_wheel.dismiss()
	main.technique_ring.can_open = func(): return true
	state.techniques = {"techniques":[{"key":"heavy_blow","name":"Heavy Blow","known":true,"blocker":"","cost":3}]}
	main.technique_ring.open_ring()
	for i in range(4): await process_frame
	await RenderingServer.frame_post_draw
	root.get_texture().get_image().save_png(folder.path_join("technique-wheel.png"))
	print("STREAM_RENDER_COMPLETE ", folder)
	Input.set_custom_mouse_cursor(null,Input.CURSOR_ARROW)
	Input.set_custom_mouse_cursor(null,Input.CURSOR_IBEAM)
	main.queue_free()
	state._on_connection_state_changed("disconnected")
	for i in range(8): await process_frame
	GlbSceneCache.clear()
	NativeAnimationImporter.clear()
	SubjectIcons._cache.clear()
	SubjectIcons._sheet = null
	for i in range(4): await process_frame
	quit()
