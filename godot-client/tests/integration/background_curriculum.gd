extends "res://tests/integration/rendered_lantern.gd"
## Local, normal-speed rendered client playtest. No OS input or server cheats.
## The small file inbox invokes the same callbacks as native player controls.
## Checkpoints are saved by the server; the inbox and timing log survive sleep.
var last_command := 0
var busy := false
var last_snapshot := 0
var last_frame := 0
var active_ms := 0
var observed_key := ""
var active_command := ""

func capture(label: String) -> void:
	# A minimized root does not emit frame_post_draw. Render explicitly without
	# showing the window or requesting OS focus.
	RenderingServer.force_draw(false)
	var image:=root.get_texture().get_image()
	if image!=null and not image.is_empty():image.save_png(output.path_join(label+".png"))

func log_event(kind: String, data: Dictionary = {}) -> void:
	data = data.duplicate(true)
	data.merge({"event":kind,"utc":Time.get_datetime_string_from_system(true),
		"ticks_ms":Time.get_ticks_msec(),"active_ms":active_ms},true)
	var f := FileAccess.open(output.path_join("events.jsonl"),FileAccess.READ_WRITE)
	if f == null: f=FileAccess.open(output.path_join("events.jsonl"),FileAccess.WRITE)
	f.seek_end();f.store_line(JSON.stringify(data));f.close()
	print("PLAYTEST ",JSON.stringify(data))

func local_tile() -> Vector2i:
	var a: Dictionary=state.actors.get(state.local_actor_id,{})
	return Vector2i(int(a.get("x",-999)),int(a.get("y",-999)))

func current_key() -> String:
	return str(state.lantern_tutorial.get("tutorial",""))+":"+str(state.lantern_tutorial.get("adventure",""))+":"+str(state.lantern_tutorial.get("stage",0))+":"+str(state.lantern_tutorial.get("key",""))

func write_state() -> void:
	var names: Dictionary=state.inventory_names
	var inv: Array=[]
	for s: Variant in state.inventory:
		var row: Dictionary=(state.inventory[s] as Dictionary).duplicate(true)
		row["slot"]=s;row["name"]=names.get(s,"");inv.append(row)
	var data := {"utc":Time.get_datetime_string_from_system(true),"active_ms":active_ms,
		"busy":busy,"command":active_command,"last_command":last_command,
		"tutorial":state.lantern_tutorial,"map":state.current_map,"tile":[local_tile().x,local_tile().y],
		"actors":state.actors,"inventory":inv,"storage":state.storage,
		"dialogue":state.npc_dialogue,"popup":state.popup,"stats":state.stats,
		"experience":state.experience64,"chat":state.chat_lines.slice(-18),
		"bags":state.ground_bags,"bag":state.ground_bag,"trade":state.trade,
		"reading":state.reading,"magic":state.last_spell_result,"active_spells":state.active_spells,
		"marketplace":state.marketplace,"mail":state.mail,"guild":state.guild,"party":state.party,
		"inventory_state":state.inventory_state,"item_detail":state.item_detail,"perks":state.perks,
		"combat":state.combat_state,"harvest":state.harvest,"navigation":state.navigation,
		"achievements":state.achievements_catalog,"almanac":state.almanac,
		"journal":state.quest_journal,"archive":state.quest_archive,
		"merchant":state.merchant,"manufacturing_status":main.manufacturing_server_status}
	var f:=FileAccess.open(output.path_join("state.next"),FileAccess.WRITE)
	f.store_string(JSON.stringify(data));f.close()
	DirAccess.rename_absolute(output.path_join("state.next"),output.path_join("state.json"))

func _process(_delta: float) -> bool:
	if output.is_empty() or state==null:return false
	Engine.max_fps=10 if OS.get_environment("ELORIA_PLAYTEST_WORKER")=="1" else 20
	var now:=Time.get_ticks_msec()
	if last_frame>0:
		var elapsed:=now-last_frame
		if elapsed<5000:active_ms+=elapsed
		else:log_event("pause_gap",{"milliseconds":elapsed,"command":active_command})
	last_frame=now
	if now-last_snapshot>1000:
		last_snapshot=now
		var key:=current_key()
		if key!=observed_key:
			observed_key=key
			log_event("objective",{"key":key,"tutorial":state.lantern_tutorial})
		write_state()
	if not busy and FileAccess.file_exists(output.path_join("command.json")):
		var parsed: Variant=JSON.parse_string(FileAccess.get_file_as_string(output.path_join("command.json")))
		if parsed is Dictionary and int(parsed.get("id",0))>last_command:
			last_command=int(parsed.id);busy=true;active_command=str(parsed.get("action",""))
			execute.call_deferred(parsed)
	return false

func wait_soft(check: Callable, seconds:=90.0) -> bool:
	var remaining:=seconds
	var previous:=Time.get_ticks_msec()
	while not check.call() and remaining>0:
		await create_timer(.1).timeout
		var now:=Time.get_ticks_msec()
		var elapsed:=float(now-previous)/1000.0
		if elapsed<5:remaining-=elapsed
		previous=now
	return check.call()

func walk_to(tile: Vector2i, radius:=0) -> bool:
	var before_key:=current_key()
	net.move_to(tile)
	return await wait_soft(func():return current_key()!=before_key or (state.combat_state.get("active",false) and int(state.combat_state.get("target_health",0))>0) or maxi(absi(local_tile().x-tile.x),absi(local_tile().y-tile.y))<=radius,55)

func find_target(key: String) -> Dictionary:
	if main.lantern_scene==null:return {}
	for t: Dictionary in main.lantern_scene.layout.get("targets",[]):
		if str(t.id)==key:return t
	return {}

func item_slot(item: String, equipped:=false) -> int:
	for s: Variant in state.inventory_names:
		if str(state.inventory_names[s])==item and (int(s)>=36 if equipped else int(s)<36):return int(s)
	return -1

func close_windows() -> void:
	main.extension_windows.close_all()
	for panel in [main.inventory_panel,main.storage_panel,main.manufacturing_panel,main.stats_panel,main.full_map]:panel.hide()
	if state.npc_dialogue.get("open",false):state.close_dialogue()
	if state.popup.get("open",false):main._on_popup_dismiss_pressed()
	main.spells_window.close()
	if main.summoning_window.is_open():main._on_summoning_button_pressed()

func execute(c: Dictionary) -> void:
	log_event("action_start",{"id":last_command,"action":active_command,"arguments":c})
	var ok:=true
	match active_command:
		"go":ok=await walk_to(Vector2i(c.x,c.y),int(c.get("radius",0)))
		"objective":
			var target: Array=state.lantern_tutorial.get("target",[])
			if target.size()==2:ok=await walk_to(Vector2i(target[0],target[1]),int(c.get("radius",0)))
			else:ok=false
		"chat":net.send_chat(str(c.text))
		"popup":main._on_popup_option_pressed(int(c.get("group",0)),int(c.value))
		"touch":net.touch_actor(int(c.get("actor",actor_id(str(c.get("name",""))))))
		"dialogue":main._on_dialogue_option(int(c.get("actor",actor_id(str(c.get("name",""))))),int(c.value))
		"target":
			var t:=find_target(str(c.key))
			if t.is_empty():ok=false
			else:
				ok=await walk_to(Vector2i(t.approach[0],t.approach[1]))
				if ok:
					var obj: Node=main.map_object_nodes.get(int(t.get("objectId",0)))
					if obj!=null:main._activate_map_object(obj,false)
					else:ok=false
		"harvest":net.harvest(int(c.object))
		"use","equip":
			var s:=int(c.get("slot",item_slot(str(c.get("item","")))))
			if s<0:ok=false
			else:
				main.inventory_panel.show()
				if active_command=="use":
					main._on_inventory_use_pressed();main._on_inventory_slot_pressed(s)
				else:
					var click:=InputEventMouseButton.new()
					click.button_index=MOUSE_BUTTON_LEFT;click.pressed=true;click.double_click=true
					main._on_inventory_slot_gui_input(click,s)
		"inspect":
			var s:=int(c.get("slot",item_slot(str(c.get("item","")))))
			if s<0:s=item_slot(str(c.get("item","")),true)
			if s<0:ok=false
			else:
				main.inventory_panel.show();main._on_inventory_inspect_pressed();main._on_inventory_slot_pressed(s)
		"mix":
			main._on_storage_close_pressed()
			if not main.manufacturing_panel.visible:main._on_manufacturing_button_pressed()
			main.manufacturing_tabs.get_child(0).pressed.emit()
			main.manufacturing_ready_only.button_pressed=false
			main.manufacturing_source.button_pressed=bool(c.get("storage",false))
			main.manufacturing_filter.text=str(c.item);main._on_manufacturing_filter_changed(str(c.item))
			await create_timer(.3).timeout
			ok=false
			for index in range(main.manufacturing_list.item_count):
				var definition: Dictionary=main.manufacturing_catalog.recipe(int(main.manufacturing_list.get_item_metadata(index)))
				if str(definition.get("output",""))==str(c.item):
					main.manufacturing_list.select(index);main.manufacturing_list.item_selected.emit(index);ok=true;break
			if ok:
				main.manufacturing_quantity.text=str(int(c.get("amount",1)))
				main.manufacturing_source.button_pressed=bool(c.get("storage",false))
				if c.get("queue",false):main._on_manufacturing_mix_all_pressed();main._on_manufacturing_queue_start_pressed()
				else:main._on_manufacturing_mix_one_pressed()
		"deposit":
			ok=select_item(main.storage_inventory,str(c.item))>=0
			if ok:main.storage_quantity.value=int(c.get("amount",1));main._on_storage_deposit_pressed()
		"withdraw":
			ok=false
			for i in range(main.storage_categories.item_count):
				main.storage_categories.select(i);main._on_storage_category_selected(i)
				await create_timer(.25).timeout
				if select_item(main.storage_items,str(c.item))>=0:
					main.storage_quantity.value=int(c.get("amount",1));main._on_storage_withdraw_pressed();ok=true;break
		"attack":main._send_attack(int(c.actor))
		"attack_retreat":
			main._send_attack(int(c.actor))
			ok=await wait_soft(func():return int(state.combat_state.get("target_id",-1))==int(c.actor) and int(state.combat_state.get("target_health",0))>0 and bool(state.combat_state.get("active",false)),8)
			if ok:net.move_to(Vector2i(c.x,c.y))
			await create_timer(2).timeout
		"range":main._send_attack(int(c.actor))
		"flee":
			net.move_to(Vector2i(c.x,c.y))
			await create_timer(2).timeout
		"move_item":net.move_inventory_item(int(c.source),int(c.destination))
		"summon":
			if not main.summoning_window.is_open():main._on_summoning_button_pressed()
			await create_timer(.2).timeout
			ok=false
			for recipe: int in main.summoning_window.summon_recipes():
				var row: Dictionary=main.manufacturing_catalog.recipe(recipe)
				var species:=str(c.creature).split("_")[-1]
				if str(row.get("summon", ""))==str(c.creature) or str(row.get("output", "")).to_lower().contains(species):
					main.summoning_window._on_row_pressed(recipe);ok=true;break
		"merchant":
			var ext: Control=main.extension_windows
			ext._on_merchant_mode(str(c.mode))
			var list: ItemList=ext.merchant_buy_list if c.mode=="buy" else ext.merchant_sell_list
			var selected:=select_item(list,str(c.item))
			ok=selected>=0
			if ok:
				ext._on_merchant_selected(selected,str(c.mode));ext.merchant_quantity.text=str(int(c.get("amount",1)));ext._on_merchant_trade()
		"trade_request":
			state.selected_actor_id=int(c.actor);main._on_trade_button_pressed()
		"trade_offer":
			ok=false
			var wanted:=int(c.get("slot",item_slot(str(c.get("item","")))))
			for index in range(main.trade_source.item_count):
				if int(main.trade_source.get_item_metadata(index))==wanted:
					main.trade_source.select(index);main.trade_source.item_selected.emit(index);ok=true;break
			if ok:main.trade_quantity.value=int(c.get("amount",1));main._on_trade_offer_pressed()
		"trade_accept":
			if c.get("storage",false):
				for i in range(main.trade_other_offers.item_count):
					main.trade_other_offers.select(i);main._on_trade_storage_destination_toggled(true)
			main._on_trade_accept_pressed()
		"trade_cancel":main._on_trade_cancel_pressed()
		"cancel_spell":main.magic_selection.cancel()
		"test_login":
			net.disconnect_from_server();await create_timer(.6).timeout
			main.host_edit.text="127.0.0.1";main.port_edit.value=int(OS.get_environment("ELORIA_PLAYTEST_PORT")) if not OS.get_environment("ELORIA_PLAYTEST_PORT").is_empty() else 2036;main.secure_check.button_pressed=false
			main._on_connect_pressed()
			ok=await wait_soft(func():return state.connection_state=="connected",30)
			if ok:
				main.user_edit.text=str(c.username);main.password_edit.text="PaceLocal42";main._on_login_pressed()
				ok=await wait_soft(func():return state.authenticated,30)
				await create_timer(2).timeout
		"bag":net.inspect_bag(int(c.bag))
		"get_all":main._on_inventory_get_all_pressed()
		"ui":
			match str(c.name):
				"inventory":main._on_inventory_button_pressed()
				"mixing":main._on_manufacturing_button_pressed()
				"spells":main._on_spells_button_pressed()
				"summoning":main._on_summoning_button_pressed()
				"stats":main._on_stats_button_pressed()
				"map":main._toggle_full_map()
				"help":main._on_help_button_pressed()
				"quests":main._on_quest_button_pressed()
		"spell":
			var id:=int(c.spell)
			main._begin_prepared_cast(id,int(c.get("power",1)))
			await create_timer(.5).timeout
			if c.has("actor"):net.touch_actor(int(c.actor))
			elif c.has("x"):net.move_to(Vector2i(c.x,c.y))
		"close":close_windows()
		"capture":await capture(str(c.label))
		"stop":
			net.disconnect_from_server();log_event("stopped");quit(0)
		_:ok=false
	await create_timer(.7).timeout
	log_event("action_end",{"id":last_command,"action":active_command,"ok":ok,"tile":[local_tile().x,local_tile().y]})
	busy=false;active_command="";write_state()

func run() -> void:
	output=OS.get_environment("ELORIA_ARTIFACT_DIR")
	DirAccess.make_dir_recursive_absolute(output)
	if FileAccess.file_exists(output.path_join("command.json")):
		var previous: Variant=JSON.parse_string(FileAccess.get_file_as_string(output.path_join("command.json")))
		if previous is Dictionary:last_command=int(previous.get("id",0))
	Engine.max_fps=20
	AudioServer.set_bus_mute(0,true)
	root.size=Vector2i(1280,720)
	DisplayServer.window_set_title("Eloria background tutorial playtest")
	DisplayServer.window_set_flag(DisplayServer.WINDOW_FLAG_NO_FOCUS,true)
	DisplayServer.window_set_mode(DisplayServer.WINDOW_MODE_MINIMIZED)
	main=load("res://src/app/main.tscn").instantiate();root.add_child(main)
	await process_frame
	state=root.get_node("AppState");net=root.get_node("Network")
	main.host_edit.text="127.0.0.1";main.port_edit.value=int(OS.get_environment("ELORIA_PLAYTEST_PORT")) if not OS.get_environment("ELORIA_PLAYTEST_PORT").is_empty() else 2036
	main.secure_check.button_pressed=false;main._on_connect_pressed()
	if not await wait_until(func():return state.connection_state=="connected","connect"):return
	var login_name:=OS.get_environment("ELORIA_PLAYTEST_USER")
	if login_name.is_empty():login_name="PaceStudent"
	if OS.get_environment("ELORIA_PLAYTEST_CREATE")=="1":
		main._on_new_character_pressed();main.create_name.text=login_name
		main.create_password.text="PaceLocal42";main.create_confirm.text="PaceLocal42";main._on_create_pressed()
	else:
		main.user_edit.text=login_name;main.password_edit.text="PaceLocal42";main._on_login_pressed()
	if not await wait_until(func():return state.authenticated,"local test login"):return
	await wait_until(func():return main.actor_nodes.has(state.local_actor_id),"rendered world",100)
	await create_timer(2).timeout
	await capture("opening")
	log_event("ready",{"map":state.current_map})
	write_state()
