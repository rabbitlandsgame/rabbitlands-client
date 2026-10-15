extends "res://tests/integration/rendered_lantern.gd"
## Real TCP native scene, objective, cabinet, and checkpoint smoke coverage.
## Full authoritative gameplay paths are exercised by test_roads.py.

func run() -> void:
	output=OS.get_environment("ELORIA_ARTIFACT_DIR")
	DirAccess.make_dir_recursive_absolute(output)
	root.size=Vector2i(1280,720)
	main=load("res://src/app/main.tscn").instantiate();root.add_child(main)
	await process_frame
	state=root.get_node("AppState");net=root.get_node("Network")
	var adventure:=OS.get_environment("ELORIA_ROAD")
	main.host_edit.text="127.0.0.1";main.port_edit.value=int(OS.get_environment("ELORIA_INTEGRATION_PORT"))
	main.secure_check.button_pressed=false;main._on_connect_pressed()
	if not await wait_until(func():return state.connection_state=="connected","connect"):return
	main.user_edit.text="Road"+adventure;main.password_edit.text="RoadReview42";main._on_login_pressed()
	if not await wait_until(func():return state.authenticated,"login"):return
	# These fixtures exercise retained legacy adventures. Help now opens the
	# ordered curriculum, whose entry and counters have their own UI coverage.
	net.send_chat("#tutorial "+adventure)
	await wait_until(func():return state.lantern_tutorial.get("tutorial","")=="followup" and state.lantern_tutorial.get("active",false),"private entry")
	await wait_until(func():return main.lantern_scene!=null and main.actor_nodes.has(state.local_actor_id),"native scene")
	await create_timer(2).timeout
	await capture(adventure+"-01-arrival")
	var old:=str(state.lantern_tutorial.key)
	if adventure=="summoning":main._on_summoning_button_pressed()
	elif adventure=="builds":main._on_stats_button_pressed()
	elif adventure in ["equipment","trading"]:
		main._on_inventory_button_pressed()
		if adventure=="equipment":
			await wait_until(func():return "Militia Arming Sword" in state.inventory_names.values(),"named practice sword")
			main._on_inventory_inspect_pressed()
			for slot: Variant in state.inventory_names:
				if state.inventory_names[slot]=="Militia Arming Sword":main._on_inventory_slot_pressed(int(slot));break
	elif adventure=="crafting":main._on_manufacturing_button_pressed()
	elif adventure=="parties":net.send_chat("#party invite Ise")
	await wait_until(func():return str(state.lantern_tutorial.key)!=old,"first real objective")
	await capture(adventure+"-02-gameplay")
	if adventure=="crafting":
		main._on_manufacturing_button_pressed()
		await use_target("ore")
		await stage("coal")
		await use_target("coal")
		await stage("materials")
		await capture(adventure+"-harvest")
	if adventure=="equipment":
		await double_click("Militia Arming Sword")
		await double_click("Wooden Round Shield")
		await stage("twohand")
	await use_target("cache")
	await wait_until(func():return main.storage_panel.visible,"native cabinet")
	await withdraw("Bread",1)
	if adventure=="summoning":
		await withdraw("Bones",1);await withdraw("Reed",2);await withdraw("Aether Salt",1)
		await stage("otter")
	await capture(adventure+"-03-supplies")
	main._on_storage_close_pressed()
	if adventure=="summoning":
		for target: Dictionary in main.lantern_scene.layout.targets:
			if target.id == "calling_circle": await go(Vector2i(target.approach[0],target.approach[1]))
		if not main.summoning_window.is_open():main._on_summoning_button_pressed()
		main.summoning_window._on_row_pressed(main.summoning_window.summon_recipes()[0])
		await stage("hold")
		await capture(adventure+"-summoned")
		main.summoning_window.behavior_button.pressed.emit()
		await wait_until(func(): return state.popup.get("title", "") == "Summon Behavior", "native behavior chooser")
		main._on_popup_option_pressed(0,1)
		if main.summoning_window.is_open(): main._on_summoning_button_pressed()
		for target: Dictionary in main.lantern_scene.layout.targets:
			if target.id == "north": await go(Vector2i(target.approach[0],target.approach[1]))
		await stage("latch")
		await use_target("north_object")
		await stage("shared_mode")
		await wait_until(func(): return state.lantern_tutorial.flags.get("caravan_north_open",false), "saved North rescue")
		await capture(adventure+"-north-rescue")
	var checkpoint:=str(state.lantern_tutorial.key)
	var previous_scene_id: int = main.lantern_scene.get_instance_id()
	net.send_chat("#tutorial leave")
	await create_timer(.4).timeout
	main._on_popup_option_pressed(0,1)
	await wait_until(func():return not state.lantern_tutorial.get("active",false),"public character restored")
	net.send_chat("#tutorial "+adventure)
	await wait_until(func():return state.lantern_tutorial.get("active",false) and str(state.lantern_tutorial.get("key",""))==checkpoint,"saved checkpoint resumed")
	await wait_until(func(): return main.lantern_scene != null and main.lantern_scene.get_instance_id() != previous_scene_id \
		and main.actor_nodes.has(state.local_actor_id) and absf(main.actor_nodes[state.local_actor_id].global_position.y - .4) < .2,
		"resumed actor grounded in the new native scene")
	await capture(adventure+"-04-resumed")
	net.disconnect_from_server()
	main.queue_free()
	for _i in range(8): await process_frame
	print("ROADS PASS ",adventure)
	quit(failures)
