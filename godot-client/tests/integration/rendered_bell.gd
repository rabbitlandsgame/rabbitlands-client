extends "res://tests/integration/rendered_lantern.gd"
## Real TCP playthrough; no quest state writes or privileged commands.
var last_potion := 0
const STEPS := ["arrival","map","count_start","supplies","deposit","potion","sword","shield","lookout","orchard","loot","east","retreat","refuge","heal","pressure","wave_one","lull","wave_two","winch","bow","shot","ranging","sentry","overlook","captain","final_ready","final","bell","counters","count_end","depart"]

func reached(wanted: String) -> bool:
	return STEPS.find(key())>=STEPS.find(wanted)

func stage(wanted: String) -> void:
	await wait_until(func():return reached(wanted),wanted)
	print("BELLWATCH stage: ",key())

func key() -> String:
	return str(state.lantern_tutorial.get("key", ""))

func position() -> Vector2i:
	var a: Dictionary=state.actors.get(state.local_actor_id,{})
	return Vector2i(int(a.get("x",0)),int(a.get("y",0)))

func hp() -> int:
	return int(state.stats.get("health",20))

func go_target() -> void:
	var tile: Array=state.lantern_tutorial.target
	await go(Vector2i(tile[0],tile[1]))

func go(tile: Vector2i) -> void:
	# Nearby invaders deliberately interrupt walking. Repeat the same ground
	# click only after movement stalls, just as the lesson instructs the player.
	net.move_to(tile)
	var last_position:=position()
	var last_change:=Time.get_ticks_msec()
	var deadline:=last_change+60000
	while position()!=tile and Time.get_ticks_msec()<deadline:
		await create_timer(.15).timeout
		if position()!=last_position:
			last_position=position();last_change=Time.get_ticks_msec()
		elif Time.get_ticks_msec()-last_change>1200:
			net.move_to(tile);last_change=Time.get_ticks_msec()
	await wait_until(func():return position()==tile,"walk to "+str(tile),1)
	await create_timer(.3).timeout

func nesh(response: int) -> void:
	await go(Vector2i(68,76))
	var id:=actor_id("Wayfinder Nesh")
	net.touch_actor(id)
	await create_timer(.4).timeout
	main._on_dialogue_option(id,response)
	await create_timer(.5).timeout

func unequip_all() -> void:
	for slot: Variant in state.inventory_names.keys():
		if int(slot)>=36:
			var click := InputEventMouseButton.new()
			click.button_index=MOUSE_BUTTON_LEFT;click.pressed=true;click.double_click=true
			main._on_inventory_slot_gui_input(click,int(slot))
			await create_timer(.4).timeout

func enemy() -> int:
	var best: int=-1
	var nearest: float=10000
	for id: Variant in state.actors:
		var a: Dictionary=state.actors[id]
		var label:=str(a.get("name",""))
		if int(a.get("health",0))<=0 or not (label.contains("invader") or label.contains("raider") or label.contains("sentry") or label.contains("Captain")):continue
		var distance:=position().distance_to(Vector2i(a.x,a.y))
		if label.contains("Captain"):distance-=100
		if distance<nearest:nearest=distance;best=int(id)
	return best

func fight_to(next_key: String) -> void:
	var deadline:=Time.get_ticks_msec()+240000
	var last_action:=0
	var captured_boss:=false
	while not reached(next_key) and Time.get_ticks_msec()<deadline:
		if hp()<=11 and Time.get_ticks_msec()-last_potion>4200 and "Potion of Minor Healing" in state.inventory_names.values():
			await double_click("Potion of Minor Healing");last_potion=Time.get_ticks_msec()
		var id:=enemy()
		if id>=0 and not captured_boss:
			var a: Dictionary=state.actors[id]
			if str(a.get("name","")).contains("Captain") and position().distance_to(Vector2i(a.x,a.y))<9:
				captured_boss=true
				await capture("captain-"+next_key)
		if Time.get_ticks_msec()-last_action>1800:
			last_action=Time.get_ticks_msec()
			if id<0:
				var tile: Array=state.lantern_tutorial.target
				net.move_to(Vector2i(tile[0],tile[1]))
			else:
				main._send_attack(id)
		await create_timer(.4).timeout
	await stage(next_key)

func run() -> void:
	output=OS.get_environment("ELORIA_ARTIFACT_DIR")
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
	if not await wait_until(func():return state.connection_state=="connected","connect"):return
	main.user_edit.text="BellQA";main.password_edit.text="BellReview42"
	main._on_login_pressed()
	if not await wait_until(func():return state.authenticated,"login"):return
	if OS.get_environment("ELORIA_BELL_RESUME")=="pressure":
		await stage("pressure")
		await wait_until(func():return main.lantern_scene!=null and main.actor_nodes.has(state.local_actor_id),"restored Bellwatch")
		await finish_rescue()
		return
	if OS.get_environment("ELORIA_BELL_RESUME")=="shot":
		await stage("shot")
		await wait_until(func():return main.lantern_scene!=null and main.actor_nodes.has(state.local_actor_id),"restored Bellwatch")
		await ranged_lesson()
		return
	if OS.get_environment("ELORIA_BELL_RESUME")=="sentry":
		await stage("sentry")
		await wait_until(func():return main.lantern_scene!=null and main.actor_nodes.has(state.local_actor_id),"restored Bellwatch")
		await resolve_sentry()
		return
	if OS.get_environment("ELORIA_BELL_RESUME")=="captain":
		await stage("captain")
		await wait_until(func():return main.lantern_scene!=null and main.actor_nodes.has(state.local_actor_id),"restored Bellwatch")
		await finish_captains()
		return
	net.send_chat("#tutorial invasions")
	await stage("arrival")
	net.send_chat("#autogather") # Fresh characters start with auto-gather on; test manual bags.
	await wait_until(func():return main.lantern_scene!=null and main.actor_nodes.has(state.local_actor_id),"Bellwatch native scene")
	await create_timer(2).timeout
	await capture("01-arrival")
	await go(Vector2i(68,76))
	await stage("map")
	main._toggle_full_map()
	await stage("count_start")
	await capture("02-four-gates-map")
	main._toggle_full_map()
	net.send_chat("#il")
	await stage("supplies")
	await nesh(1451)
	await stage("deposit")
	await use_target("cache")
	await wait_until(func():return main.storage_inventory.item_count>0,"storage")
	select_item(main.storage_inventory,"Wood Plank")
	main.storage_quantity.value=3;main._on_storage_deposit_pressed()
	await stage("potion")
	await withdraw("Potion of Minor Healing",3)
	await stage("sword")
	main._on_storage_close_pressed();main._on_inventory_button_pressed()
	await double_click("Militia Arming Sword")
	await stage("shield")
	await double_click("Wooden Round Shield")
	await stage("lookout")
	await capture("03-kit")
	main._on_inventory_close_pressed()
	await go_target()
	await stage("orchard")
	await fight_to("loot")
	await capture("04-first-combat")
	for id: Variant in state.ground_bags:
		net.inspect_bag(int(id));break
	await wait_until(func():return bool(state.ground_bag.get("open",false)),"actual loot bag")
	main._on_inventory_get_all_pressed()
	await stage("east")
	main._on_inventory_close_pressed()
	await go_target()
	await stage("retreat")
	await wait_until(func():return enemy()>=0,"East raiders visible")
	main._send_attack(enemy())
	await wait_until(func():return bool(state.combat_state.get("active",false)),"engage raider",60)
	var before:=hp()
	await wait_until(func():return hp()<before,"take real damage",60)
	for attempt in range(12):
		net.move_to(Vector2i(89,72))
		await create_timer(1).timeout
		if key()!="retreat":break
	await stage("refuge")
	await go(Vector2i(89,72))
	await stage("heal")
	main._on_inventory_button_pressed()
	await double_click("Potion of Minor Healing")
	await stage("pressure")
	await capture("05-retreat-heal")
	main._on_inventory_close_pressed()
	await finish_rescue()

func finish_rescue() -> void:
	await fight_to("wave_one")
	await fight_to("lull")
	await capture("06-wave-lull")
	await stage("wave_two")
	await fight_to("winch")
	await use_target("winch")
	await stage("bow")
	main._on_inventory_button_pressed()
	await unequip_all()
	await double_click("Bellwatch Practice Bow")
	await double_click("Arrow")
	await stage("shot")
	main._on_inventory_close_pressed()
	await ranged_lesson()

func ranged_lesson() -> void:
	await go_target()
	await wait_until(func():return enemy()>=0,"sentry visible")
	var a: Dictionary=state.actors[enemy()]
	if maxi(abs(position().x-int(a.x)),abs(position().y-int(a.y)))<4:
		await go(Vector2i(72,48))
	main._send_attack(enemy())
	await stage("ranging")
	await wait_until(func():return main.ranging_window.hits>=1,"real ranging hit counter")
	main._on_ranging_button_pressed()
	await stage("sentry")
	await process_frame
	if main.lantern_guide.card.get_global_rect().intersects(main.ranging_window.panel.get_global_rect()):
		failures+=1;push_error("Guide covers Ranging controls")
	await capture("07-ranging")
	main.ranging_window.close()
	await resolve_sentry()

func resolve_sentry() -> void:
	main._on_inventory_button_pressed()
	await unequip_all()
	await double_click("Militia Arming Sword")
	await double_click("Wooden Round Shield")
	main._on_inventory_close_pressed()
	await fight_to("overlook")
	if key()=="overlook":await go_target()
	await stage("captain")
	await capture("08-captain")
	await finish_captains()

func finish_captains() -> void:
	await fight_to("final_ready")
	await capture("09-dispersal")
	await use_target("cart")
	await stage("final")
	await fight_to("bell")
	await use_target("bell")
	await stage("counters")
	await capture("10-second-bell")
	main._on_stats_button_pressed();main.stats_tabs.current_tab=2
	await stage("count_end")
	await capture("11-counters")
	main.stats_panel.hide();net.send_chat("#il")
	await stage("depart")
	await use_target("cart")
	main._on_popup_option_pressed(1,1)
	await wait_until(func():return not bool(state.lantern_tutorial.get("active",true)),"completed in Four Gates")
	await capture("12-complete")
	net.disconnect_from_server()
	print("BELLWATCH NATIVE UI: ","PASS" if failures==0 else "FAIL")
	quit(failures)
