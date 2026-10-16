extends "res://tests/integration/rendered_bell.gd"
## Real TCP, native spellbook / target selection / storage / merchant callbacks.
## The isolated server changes walking speed only; quest state is never written.
const CASTS := {
	"heal":["Heal",1],"quick":["Heal",1],"power_one":["Heal",1],
	"power_two":["Heal",2],"power_small":["Heal",1],"anchor":["Heal",4],
	"allies":["Heal Allies",1],"bolt":["Magic Bolt",1],"burst_attack":["Magic Burst",1],
	"poison":["Poison Target",1],"shield":["Shield",1],"ward":["Magic Ward",1],
	"heat":["Heat Ward",1],"dispel":["Dispel",1],"refresh":["Magic Ward",1]}

func spell_id(spell_name: String) -> int:
	for id: int in main.spell_catalog.spell_ids():
		if main.spell_catalog.spell(id).name==spell_name:return id
	return -1

func book_cast(spell_name: String, power: int=1, target: int=-1, tile:=Vector2i(-1,-1), cancel:=false) -> void:
	while main.requested_spell_power<power:main._on_spell_power_up_pressed()
	while main.requested_spell_power>power:main._on_spell_power_down_pressed()
	if not main.spells_window.is_open():main._on_spells_button_pressed()
	main.spells_window._on_spell_pressed(spell_id(spell_name))
	await wait_until(func():return not main.spells_window.cast_button.disabled,"ready "+spell_name)
	main.spells_window.cast_button.pressed.emit()
	await create_timer(.25).timeout
	if cancel:
		if spell_name=="Transmute":
			await wait_until(func():return main.magic_selection.popup.visible,"Transmute quote")
			for i in range(main.magic_selection.entries.size()):
				if main.magic_selection.entries[i].name==("Empty Echo Vessel" if key()=="d_rare_quote" else "Bones"):
					main.magic_selection.choices.select(i)
			main.magic_selection._update_quote()
			if key()=="d_rare_quote":
				await wait_until(func():return main.magic_selection.popup.get_ok_button().disabled,"Uncommon quote blocked at P1")
			await capture("experiment-uncommon-quote" if key()=="d_rare_quote" else "09-transmute-quote")
		var escape:=InputEventKey.new()
		escape.keycode=KEY_ESCAPE;escape.pressed=true
		Input.parse_input_event(escape)
	elif spell_name=="Transmute":
		await wait_until(func():return main.magic_selection.popup.visible,"Transmute chooser")
		for i in range(main.magic_selection.entries.size()):
			if main.magic_selection.entries[i].name==("Empty Echo Vessel" if key()=="d_rare" else "Bones"):main.magic_selection.choices.select(i)
		main.magic_selection.quantity.value=1
		main.magic_selection._update_quote()
		main.magic_selection._confirm()
	elif spell_name=="Recall" and power>=5:
		await wait_until(func():return main.magic_selection.popup.visible,"Recall destination chooser")
		await capture("experiment-recall-chooser")
		main.magic_selection.choices.select(0);main.magic_selection._confirm()
	elif target>=0:net.touch_actor(target)
	elif tile.x>=0:net.move_to(tile)
	await create_timer(.5).timeout
	main.spells_window.close()

func keeper(response: int) -> void:
	await go(Vector2i(55,67))
	var id:=actor_id("Keeper Sera")
	net.touch_actor(id)
	await create_timer(.35).timeout
	main._on_dialogue_option(id,response)
	await create_timer(.5).timeout

func cupboard() -> void:
	await use_target("cache")
	await wait_until(func():return main.storage_panel.visible,"supply cabinet")
	await create_timer(.5).timeout

func guardian() -> int:
	for id: Variant in state.actors:
		var a: Dictionary=state.actors[id]
		var label:=str(a.get("name","")).to_lower()
		if (label.contains("guardian") or label.contains("summon")) and int(a.get("health",0))>0:return int(id)
	return -1

func clear_guardians() -> void:
	var original_key:=key()
	for attempt in range(30):
		if key()!=original_key:return
		var id:=guardian()
		if id<0:return
		var a: Dictionary=state.actors[id]
		if position().distance_to(Vector2i(a.x,a.y))>12:await go(Vector2i(int(a.x)-6,int(a.y)))
		await book_cast("Magic Bolt",1,id)
	await wait_until(func():return guardian()<0,"guardians defeated")

func run() -> void:
	output=OS.get_environment("ELORIA_ARTIFACT_DIR")
	DirAccess.make_dir_recursive_absolute(output)
	root.size=Vector2i(1280,720)
	main=load("res://src/app/main.tscn").instantiate();root.add_child(main)
	await process_frame
	state=root.get_node("AppState");net=root.get_node("Network")
	main.host_edit.text="127.0.0.1";main.port_edit.value=int(OS.get_environment("ELORIA_INTEGRATION_PORT"))
	main._dev_plain_tcp=true;main._on_connect_pressed()
	if not await wait_until(func():return state.connection_state=="connected","connect"):return
	main.user_edit.text="SkyQA";main.password_edit.text="SkyReview42";main._on_login_pressed()
	if not await wait_until(func():return state.authenticated,"login"):return
	if OS.get_environment("ELORIA_SKY_LABS_ONLY")=="1":
		await create_timer(1).timeout
		await experiments();quit(failures);return
	if not state.lantern_tutorial.get("tutorial","")=="borrowed_sky":net.send_chat("#tutorial magic")
	await wait_until(func():return state.lantern_tutorial.get("tutorial","")=="borrowed_sky" and state.lantern_tutorial.get("active",false),"Stillglass entry")
	await wait_until(func():return main.lantern_scene!=null and main.actor_nodes.has(state.local_actor_id),"Stillglass native scene")
	await create_timer(2).timeout
	await capture("01-observatory")
	for iteration in range(85):
		if not state.lantern_tutorial.get("active",false):break
		var old:=key();print("STILLGLASS stage: ",old)
		if old=="book":
			main._on_spells_button_pressed()
			main.spells_window._on_spell_pressed(spell_id("Magic Immunity"))
			await create_timer(.4).timeout;await capture("02-borrowed-attunement")
			main.spells_window.close()
		elif old=="borrow":await keeper(1461)
		elif old=="tome":await keeper(1462)
		elif old=="cancel":await go_target();await book_cast("Heal Target",1,-1,Vector2i(-1,-1),true)
		elif old=="target":await go_target();await book_cast("Heal Target",1,actor_id("Tavin"))
		elif old=="withdraw":await cupboard();await withdraw("Life Distillate",35);main._on_storage_close_pressed()
		elif old in ["mana","food"]:await double_click("Potion of Mana" if old=="mana" else "Bread")
		elif old=="focus":
			await cupboard();await withdraw("Hearthstone Focus",1);await withdraw("Attunement Charge",1)
			main._on_storage_close_pressed();await book_cast("Heal",4)
		elif old=="burst":
			await go_target();var a: Dictionary=state.actors[actor_id("Oren")]
			await book_cast("Heal Burst",1,-1,Vector2i(a.x,a.y));await capture("04-glasshouse")
		elif old in CASTS:
			await go_target()
			var id:=guardian() if old in ["bolt","burst_attack","poison"] else -1
			var tile:=Vector2i(-1,-1)
			if old=="burst_attack" and id>=0:tile=Vector2i(state.actors[id].x,state.actors[id].y);id=-1
			await book_cast(CASTS[old][0],CASTS[old][1],id,tile)
			if old=="poison":await create_timer(5.2).timeout
			if old in ["ward","heat"]:await create_timer(5).timeout
			if old=="heat":await capture("06-prism-lane")
		elif old=="clear":await clear_guardians()
		elif old=="blink":await go_target();await book_cast("Blink",1,-1,Vector2i(60,21));await capture("07-folded-gate")
		elif old=="haste":await book_cast("Haste");await go(Vector2i(64,20))
		elif old=="conceal":await book_cast("Conceal");await go(Vector2i(69,14))
		elif old=="reveal":await book_cast("Reveal Burst",1,-1,Vector2i(72,14));await capture("08-hidden-apprentice")
		elif old=="rescue":
			await go_target();net.touch_actor(actor_id("Oren"))
			await wait_until(func():return main.dialogue_panel.visible,"Oren return dialogue")
			main._on_dialogue_option(actor_id("Oren"),1469)
		elif old=="quote_cancel":await go_target();await book_cast("Transmute",1,-1,Vector2i(-1,-1),true)
		elif old=="transmute":await book_cast("Transmute")
		elif old=="purchase":
			await go_target();net.use_map_object(7203);await create_timer(.6).timeout
			main.extension_windows._on_merchant_mode("buy")
			main.extension_windows.merchant_list.select(0)
			main.extension_windows.merchant_quantity.text = "1"
			main.extension_windows._on_merchant_trade()
		elif old=="fitting":net.use_map_object(7203)
		elif old=="final_ready":await book_cast("Blink",1,-1,Vector2i(60,29));await keeper(1466)
		elif old=="final":
			await go_target();await clear_guardians()
			for who: String in ["Tavin","Mira","Oren"]:
				var id:=actor_id(who);var a: Dictionary=state.actors[id]
				await go(Vector2i(int(a.x)-2,int(a.y)));await book_cast("Heal Target",3,id)
				net.touch_actor(id);await create_timer(.4).timeout
			await capture("11-rescue")
		elif old=="lens":await go_target();net.use_map_object(7202);await create_timer(.7).timeout;await capture("12-restored-sky")
		elif old=="recall":await book_cast("Recall")
		else:push_error("Unhandled stage "+old);quit(1);return
		await wait_until(func():return key()!=old or not state.lantern_tutorial.get("active",false),"advance "+old,20)
	await wait_until(func():return not state.lantern_tutorial.get("active",false),"permanent profile restored")
	await create_timer(2).timeout
	await capture("13-home")
	print("STILLGLASS RENDERED CORE PASS")
	if OS.get_environment("ELORIA_SKY_EXPERIMENTS")=="1":await experiments()
	quit(failures)

func experiments() -> void:
	var spell_names := {"a_regen":"Regeneration","a_life":"Life Drain Target","a_ether":"Ether Drain Target","a_empty":"Ether Drain Target","a_restore":"Restore Ether","a_fizzle":"Heal",
		"b_magic":"Magic Bolt","b_heat":"Fire Bolt","b_cold":"Frost Bolt","b_radiation":"Radiation Bolt","b_offense":"Magic Bolt","b_defense":"Magic Ward",
		"b_coldward":"Cold Ward","b_radward":"Radiation Ward","b_mixed":"Elemental Ward","b_weakenmagic":"Weaken Magic Target","b_weakenheat":"Weaken Heat Target",
		"b_weakencold":"Weaken Cold Target","b_weakenrad":"Weaken Radiation Target","b_cripple":"Cripple Target","b_accuracy":"Accuracy","b_weapon":"Elemental Weapon",
		"c_immunity":"Magic Immunity","c_disrupt":"Disrupt Target","c_scope":"Shield Burst"}
	for lab: String in ["a","b","c","d"]:
		var selected_lab:=OS.get_environment("ELORIA_SKY_LAB")
		if not selected_lab.is_empty() and lab!=selected_lab:continue
		if state.lantern_tutorial.get("active",false) and not key().begins_with(lab+"_"):continue
		net.send_chat("#tutorial magic "+lab)
		await wait_until(func():return state.lantern_tutorial.get("active",false),"experiment "+lab)
		await create_timer(.8).timeout
		for _iteration in range(35):
			if not state.lantern_tutorial.get("active",false):break
			var old:=key();print("STILLGLASS EXPERIMENT: ",old)
			if old=="d_recall":await book_cast("Recall",5)
			elif old=="d_return":await book_cast("Blink",1,-1,Vector2i(44,12))
			elif old=="d_focus":
				await use_target("bench")
				await go(Vector2i(60,21));await book_cast("Blink",1,-1,Vector2i(60,29))
				await use_target("lens")
				await cupboard();await withdraw("Hearthstone Focus",1);await withdraw("Attunement Charge",1)
				main._on_storage_close_pressed();await book_cast("Heal",4)
			elif old=="d_anchor":
				await cupboard();select_item(main.storage_inventory,"Hearthstone Focus")
				main.storage_quantity.value=1;main._on_storage_deposit_pressed();await create_timer(.4).timeout
				main._on_storage_close_pressed();await book_cast("Heal",4)
			elif old=="d_value":await book_cast("Transmute")
			elif old=="d_rare_quote":await book_cast("Transmute",1,-1,Vector2i(-1,-1),true)
			elif old=="d_rare":await book_cast("Transmute",3)
			elif old in spell_names:
				await go_target()
				var target: int=guardian() if old in ["b_cripple","c_disrupt"] else actor_id("Prism")
				var row: Dictionary=main.spell_catalog.spell(spell_id(spell_names[old]))
				if row.scope!="target":target=-1
				var tile:=Vector2i(60,101) if old=="c_scope" else Vector2i(-1,-1)
				await book_cast(spell_names[old],1,target,tile)
				if old in ["a_regen","a_restore"]:await create_timer(5.2).timeout
				if old=="a_fizzle":
					for _retry in range(2):
						if not state.lantern_tutorial.get("active",false):break
						await book_cast("Heal")
				if old.begins_with("b_weaken"):
					await book_cast({"b_weakenmagic":"Magic Bolt","b_weakenheat":"Fire Bolt","b_weakencold":"Frost Bolt","b_weakenrad":"Radiation Bolt"}[old],1,actor_id("Prism"))
				if old in ["b_cripple","b_accuracy","b_weapon"]:
					if state.inventory_names.get(36,"")!="Militia Arming Sword":await double_click("Militia Arming Sword")
					main._send_attack(guardian())
			else:push_error("Unknown experiment "+old);quit(1);return
			await wait_until(func():return key()!=old or not state.lantern_tutorial.get("active",false),"finish "+old,25)
			await create_timer(.3).timeout
		await wait_until(func():return not state.lantern_tutorial.get("active",false),"experiment finished "+lab)
		await create_timer(1).timeout
		print("STILLGLASS EXPERIMENT PASS: ",lab)
