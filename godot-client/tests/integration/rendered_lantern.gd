extends SceneTree
## Runs against an explicitly selected loopback dev-server. All progress comes
## from network responses to the same UI callbacks a player uses.
var main: Control
var state: Node
var net: Node
var failures := 0
var output := ""

func _init() -> void:
	call_deferred("run")

func wait_until(check: Callable, label: String, seconds := 45.0) -> bool:
	var deadline := Time.get_ticks_msec()+int(seconds*1000)
	while not check.call() and Time.get_ticks_msec()<deadline:
		await create_timer(.05).timeout
	if check.call(): return true
	failures += 1
	push_error("LANTERN: "+label+"; stage="+str(state.get("lantern_tutorial")))
	await capture("failure")
	quit(1)
	await process_frame
	return false

func stage(key: String) -> void:
	await wait_until(func(): return str(state.lantern_tutorial.get("key",""))==key,key)
	print("LANTERN stage: ",key)

func capture(label: String) -> void:
	await process_frame
	await RenderingServer.frame_post_draw
	root.get_texture().get_image().save_png(output.path_join(label+".png"))

func go(tile: Vector2i) -> void:
	net.move_to(tile)
	await wait_until(func():
		var a: Dictionary = state.actors.get(state.local_actor_id,{})
		return abs(int(a.get("x",-100))-tile.x)<=0 and abs(int(a.get("y",-100))-tile.y)<=0,
		"walk to "+str(tile),60)
	await create_timer(.3).timeout

func use_target(key: String) -> void:
	var layout: Dictionary = main.lantern_scene.layout
	for t: Dictionary in layout.targets:
		if str(t.id)==key:
			await go(Vector2i(t.approach[0],t.approach[1]))
			var object: Node = main.map_object_nodes.get(int(t.objectId))
			if object == null:
				failures+=1; push_error("Missing native object "+key); return
			var camera: Camera3D=main.camera_rig.get_node("Camera")
			var screen := camera.unproject_position(object.global_position+Vector3(0,.3,0))
			var picked: Node=main._pick_map_object(screen)
			if picked!=object:
				failures+=1;push_error("Native world picking missed "+key)
			main._activate_map_object(object,false)
			await create_timer(.5).timeout
			return

func actor_id(name_text: String) -> int:
	for id: Variant in state.actors:
		if str(state.actors[id].get("name","")).contains(name_text): return int(id)
	return -1

func select_item(list: ItemList, text: String) -> int:
	for i in range(list.item_count):
		if list.get_item_text(i).contains(text):
			list.select(i)
			list.item_selected.emit(i)
			return i
	return -1

func withdraw(item: String, amount: int) -> void:
	var found := false
	for i in range(main.storage_categories.item_count):
		# Follow the category named by the guide instead of searching every tab.
		var category := "Tools" if item == "Hatchet" else "Misc"
		if main.storage_categories.get_item_text(i) != category: continue
		main.storage_categories.select(i)
		main._on_storage_category_selected(i)
		await create_timer(.3).timeout
		if select_item(main.storage_items,item)>=0:
			found=true; break
	if not found:
		failures+=1;push_error("Storage item missing: "+item);return
	main.storage_quantity.value=amount
	main._on_storage_withdraw_pressed()
	await create_timer(.5).timeout

func double_click(item: String) -> void:
	await wait_until(func():return item in state.inventory_names.values(),"inventory named "+item)
	for slot: Variant in state.inventory_names:
		if str(state.inventory_names[slot])==item and int(slot)<36:
			var click := InputEventMouseButton.new()
			click.button_index=MOUSE_BUTTON_LEFT;click.pressed=true;click.double_click=true
			main._on_inventory_slot_gui_input(click,int(slot))
			return

func run() -> void:
	output=OS.get_environment("ELORIA_ARTIFACT_DIR")
	if output.is_empty(): output=ProjectSettings.globalize_path("res://test-artifacts/lantern")
	DirAccess.make_dir_recursive_absolute(output)
	root.size=Vector2i(1280,720)
	main=load("res://src/app/main.tscn").instantiate()
	root.add_child(main)
	await process_frame
	state=root.get_node("AppState");net=root.get_node("Network")
	main.host_edit.text="127.0.0.1"
	main.port_edit.value=int(OS.get_environment("ELORIA_INTEGRATION_PORT"))
	main.secure_check.button_pressed=false
	main._on_connect_pressed()
	if not await wait_until(func():return state.connection_state=="connected","connect"): return
	main._on_new_character_pressed()
	var name_text := "Keeper"+Crypto.new().generate_random_bytes(4).hex_encode()
	main.create_name.text=name_text
	main.create_password.text="LanternReview42"
	main.create_confirm.text="LanternReview42"
	main._on_create_pressed()
	if not await wait_until(func():return state.authenticated,"create and login"): return
	await stage("arrival")
	net.send_chat("#autogather")
	await wait_until(func():return main.lantern_scene!=null and main.actor_nodes.has(state.local_actor_id),"native presentation")
	await create_timer(2).timeout
	await capture("01-arrival")
	await go(Vector2i(21,23))
	await stage("supplies")
	await go(Vector2i(33,32))
	net.touch_actor(actor_id("Ferryman Caldus"))
	await create_timer(.5).timeout
	await capture("02-dialogue")
	main._on_dialogue_option(actor_id("Ferryman Caldus"),1400)
	await stage("chart")
	await use_target("chart")
	await stage("map")
	main._toggle_full_map()
	await stage("reed")
	await capture("03-map")
	if OS.get_environment("ELORIA_LANTERN_MAP_ONLY")=="1":
		var marker: Node3D=main.actor_nodes[state.local_actor_id].get_node("MapDot")
		if marker.scale.x>.2 or main.player_map_marker.scale.x>.2 or main.full_map_camera.size>140:
			failures+=1;push_error("Island map framing or marker scale regressed")
		net.disconnect_from_server()
		print("LANTERN MAP UI: ","PASS" if failures==0 else "FAIL")
		quit(failures)
		return
	main._toggle_full_map()
	await use_target("reed")
	await stage("quartz")
	await capture("04-harvesting")
	await use_target("quartz")
	await stage("store_pickaxe")
	await use_target("lower_cache")
	await wait_until(func():return main.storage_inventory.item_count>0,"storage window")
	await capture("05-storage")
	await wait_until(func():return select_item(main.storage_inventory,"Pickaxe")>=0,"select Pickaxe deposit")
	main.storage_quantity.value=1
	main._on_storage_deposit_pressed()
	await create_timer(.6).timeout
	await stage("plank")
	for item in ["Wood Plank","Cloth Roll","Hatchet"]:
		await withdraw(item,1)
	await stage("torch")
	main._on_storage_close_pressed()
	main._on_manufacturing_button_pressed()
	await create_timer(.5).timeout
	var recipes: ItemList=main.get_node("%ManufacturingList")
	select_item(recipes,"Torch")
	await create_timer(.3).timeout
	if main.lantern_guide.control_for_step()!=main.manufacturing_mix_one:
		failures+=1;push_error("Guide did not highlight native Mix Now")
	if main.manufacturing_panel.get_global_rect().end.y>root.size.y:
		failures+=1;push_error("Manufacturing extends below the screen")
	await capture("06-manufacturing")
	for attempt in range(10):
		main._on_manufacturing_mix_one_pressed()
		await create_timer(2).timeout
		if str(state.lantern_tutorial.get("key",""))!="torch": break
		main._on_manufacturing_close_pressed()
		await use_target("bench")
		await use_target("lower_cache")
		for item in ["Wood Plank","Cloth Roll"]:
			if item not in state.inventory_names.values(): await withdraw(item,1)
		main._on_storage_close_pressed()
		main._on_manufacturing_button_pressed()
		select_item(recipes,"Torch")
	await stage("sword")
	await capture("07-made-torch")
	main._on_manufacturing_close_pressed()
	main._on_inventory_button_pressed()
	await double_click("Militia Arming Sword")
	await stage("shield")
	await double_click("Wooden Round Shield")
	await stage("fight")
	await capture("08-equipment")
	main._on_inventory_close_pressed()
	await go(Vector2i(66,53))
	main._send_attack(actor_id("Storm-frightened otter"))
	await stage("loot")
	await capture("09-combat-loot")
	await wait_until(func():return not state.ground_bags.is_empty(),"dropped bag")
	for id: Variant in state.ground_bags:
		net.inspect_bag(int(id));break
	await wait_until(func():return bool(state.ground_bag.get("open",false)),"open bag")
	main._on_inventory_get_all_pressed()
	await stage("rest")
	await go(Vector2i(83,70))
	await stage("food")
	main._on_inventory_button_pressed()
	await double_click("Bread")
	await stage("attribute")
	main._on_inventory_close_pressed()
	main._on_stats_button_pressed()
	await create_timer(.5).timeout
	await capture("10-attributes")
	main._adjust_pickpoint("attribute","magic_defense",1)
	main._adjust_pickpoint("attribute","magic_defense",1)
	main._confirm_pickpoints()
	await stage("repair")
	main.stats_panel.hide()
	if "Reed" not in state.inventory_names.values() or "Quartz" not in state.inventory_names.values():
		failures+=1;push_error("Repair materials did not stay in the pack")
	await use_target("housing")
	await stage("light")
	await use_target("housing")
	await stage("dock")
	await capture("11-beacon-lit")
	await go(Vector2i(101,26))
	await stage("sell")
	net.touch_actor(actor_id("Caldus's galley"))
	var ext: Control=main.extension_windows
	await wait_until(func():return ext.merchant_panel.visible,"merchant")
	ext._on_merchant_mode("sell")
	select_item(ext.merchant_list,"Raw Meat")
	await capture("12-merchant")
	ext._on_merchant_trade()
	await stage("buy")
	ext._on_merchant_mode("buy")
	select_item(ext.merchant_list,"Bread")
	ext._on_merchant_trade()
	await stage("depart")
	ext.merchant_panel.hide()
	await use_target("ferry")
	main._on_popup_option_pressed(1,1)
	await stage("handoff")
	await wait_until(func():return actor_id("Gate Warden Ilyon")>=0,"Four Gates Ilyon")
	var destination: Array=state.lantern_tutorial.target
	await go(Vector2i(destination[0],destination[1]))
	await capture("13-four-gates")
	net.touch_actor(actor_id("Gate Warden Ilyon"))
	await wait_until(func():return not bool(state.lantern_tutorial.get("active",true)),"tutorial completed")
	await capture("14-complete")
	net.disconnect_from_server()
	print("LANTERN NATIVE UI: ","PASS" if failures==0 else "FAIL")
	quit(failures)
