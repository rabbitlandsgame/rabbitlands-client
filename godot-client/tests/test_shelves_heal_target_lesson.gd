extends "res://tests/test_quest_first_pass_cinematics.gd"
## Native healing proves the lesson; presentation only explains and releases it.

func run() -> void:
	root.get_node("Network").block_for_hud_preview()
	expect("campaign_shelves_heal_target_v1" in EloriaProtocol.CLIENT_CAPABILITIES,
		"the client advertises the paired friendly-target lesson")
	var catalog: Dictionary=JSON.parse_string(FileAccess.get_file_as_string("res://data/spells/catalog.json"))
	var heal: Dictionary=(catalog.spells as Array).filter(func(row: Dictionary) -> bool:return int(row.id)==1)[0]
	expect(heal.name=="Heal Target" and heal.level==0 and heal.mana==5 and heal.scope=="target" and not heal.hostile,
		"the native targeted heal remains Magic zero with five base ether")
	for item: String in ["Life Essence","Water Essence"]:
		expect((heal.reagents as Array).any(func(row: Dictionary) -> bool:return row.name==item and row.quantity==1),
			"the lesson uses the real single "+item+" cost")
	var definitions:=Scene.scene_definitions()
	var lesson: Dictionary=definitions.get("measure.shelves.basics.heal_target",{})
	expect(not lesson.is_empty() and lesson.get("live_camera")=="gameplay" and lesson.get("shots",[])==[],
		"friendly healing keeps the established practice-room view")
	expect(lesson.get("required_actors")==["mentor"] and lesson.get("stage_protagonist")==false,
		"the same native Ostrid speaks without new staged bodies")
	var original_fire: String=definitions["measure.shelves.basics.fire"].lines[0].text
	expect(not original_fire.begins_with("That helped")
		and str(definitions["measure.shelves.basics.fire"].lines[0].variants.ally_healed).begins_with("That helped"),
		"only the confirmed-heal variant adds the ally-healing follow-up; legacy Fire speech remains")
	for variable: String in ["RL_HEAL_TARGET_LESSON_EVIDENCE","RL_EARLY_MAGIC_EVIDENCE"]:
		var path:=OS.get_environment(variable)
		if path.is_empty():continue
		var raw: Variant=JSON.parse_string(FileAccess.get_file_as_string(path))
		var rows: Array=raw.snapshots if raw is Dictionary else raw
		for record: Dictionary in rows:
			var state: Dictionary=record.get("snapshot",record)
			var decoded:=EloriaProtocol.decode_campaign(JSON.stringify(state).to_utf8_buffer())
			expect(decoded.type=="campaign","new and retained native lesson states decode: "+str(decoded.get("error","")))
		if variable=="RL_HEAL_TARGET_LESSON_EVIDENCE":
			var prompt: Dictionary=rows.filter(func(row: Dictionary)->bool:return row.get("capture_label")=="target-prompt")[0]
			var ready: Dictionary=rows.filter(func(row: Dictionary)->bool:return row.get("capture_label")=="target-play")[0]
			var healed: Dictionary=rows.filter(func(row: Dictionary)->bool:return row.get("capture_label")=="ally-healed-fire")[0]
			var legacy: Dictionary=rows.filter(func(row: Dictionary)->bool:return row.get("capture_label")=="legacy-fire")[0]
			expect(prompt.actors.practice_patient==prompt.actors.mentor
				and int(prompt.native_cast.mentor.health)<int(prompt.native_cast.mentor.max_health),
				"the native instruction names its real injured mentor as the patient")
			expect(ready.shelves.phase=="work" and ready.actors.practice_patient==ready.actors.mentor
				and not bool(ready.scene.get("requires_ack",false)),"native acknowledgement releases actual targeted-healing play")
			expect(healed.scene.variant=="ally_healed" and int(healed.native_cast.mentor.health)>int(ready.native_cast.mentor.health)
				and not healed.actors.has("practice_patient"),"the actual paid heal changes the follow-up and releases friendly targeting")
			expect(legacy.scene.id=="measure.shelves.basics.fire" and str(legacy.scene.get("variant",""))!="ally_healed"
				and not legacy.actors.has("practice_patient"),"retained Fire lessons do not invent ally-healing completion")

	var f:=fixture(); f.scene.cancel("replace_fixture")
	f.scene._definitions=definitions
	f.scene._definition=lesson.duplicate(true); f.scene._scene_id="measure.shelves.basics.heal_target"
	f.scene._run="ally-lesson"; f.scene._token="prompt"; f.scene._map="landfall_town"
	f.scene._start(f.rig,f.rig.camera,f.player,f.nodes,{"mentor":2,"recipient":1,"protagonist":1})
	f.state={"active":true,"kind":"shelves","run_id":"ally-lesson","map":"landfall_town",
		"scene":{"id":"measure.shelves.basics.heal_target","token":"prompt","requires_ack":true,
			"actors":{"mentor":2,"recipient":1,"protagonist":1}}}
	f.acks.clear()
	var held: Transform3D=f.rig.camera.global_transform
	var before:=JSON.stringify(f.state)
	expect(f.scene._dialogue.portrait_visible() and f.scene._line_continue.visible,
		"Ostrid's native profile and Continue appear with the instruction")
	expect("Life Essence" in f.scene._caption.text and "Water Essence" in f.scene._caption.text
		and "power one" in f.scene._caption.text,"the lesson explains both ingredients and the base-power cost")
	f.scene.continue_dialogue()
	expect(not f.scene.blocks_input() and f.acks==[["prompt","finished"]]
		and JSON.stringify(f.state)==before,"Continue releases gameplay without claiming a successful heal")
	expect(f.rig.camera.global_transform.is_equal_approx(held),"the player can cast from the unchanged practice view")
	f.state.scene={"id":"measure.shelves.basics.fire","token":"fire","variant":"ally_healed","requires_ack":true,
		"actors":{"mentor":2,"recipient":1,"protagonist":1}}
	tick(f,0)
	expect(f.scene._caption.text.begins_with("That helped") and f.scene._dialogue.portrait_visible()
		and f.scene._line_continue.visible,"the native confirmed-heal snapshot presents its follow-up immediately")
	expect(f.rig.camera.global_transform.is_equal_approx(held),"the ally-healing follow-up adds no camera movement")
	dispose(f)

	var main: Node=(load("res://src/app/main.tscn") as PackedScene).instantiate(); root.add_child(main)
	main.set_process(false); main.hide()
	var app:=root.get_node("AppState")
	app.authenticated=true; app.death={}; app.local_actor_id=1; app.current_map="landfall_town"
	var state: Dictionary={"kind":"shelves","active":true,"run_id":"ally-lesson","map":"landfall_town",
		"actors":{"mentor":2,"practice_patient":2},"shelves":{"chapter":"intro","private_practice":true,"sparring":false}}
	var patient: Dictionary={"actor_id":2,"kind":2,"alive":true,"health":190,"max_health":200}
	app.campaign=state.duplicate(true); app.actors={2:patient,3:{"actor_id":3,"kind":2,"alive":true,"health":10,"max_health":20}}
	expect(main.call("_is_shelves_practice_patient",2,patient) and main.call("_spell_target_candidate",1,2),
		"only the exact current private Ostrid can receive the targeted healing lesson")
	expect(main.call("_overhead_health_for",2,patient,-1),"the consenting practice ally exposes her actual health")
	expect(not main.call("_spell_target_candidate",0,2) and not main.call("_spell_target_candidate",68,2)
		and not main.call("_is_attackable_actor",2,patient),"the friendly patient does not become an offensive or self-spell target")
	expect(not main.call("_spell_target_candidate",1,3),"an unrelated NPC is not a substitute for the lesson patient")
	var body:=ReplicatedActor3D.new(); root.add_child(body)
	body.apply_vitals(190,200); main.set("actor_nodes",{2:body})
	main.call("_on_state_changed",&"campaign")
	expect(body._health_shown and body._health_current==190,"campaign-only patient assignment exposes the native injured health pair")
	app.campaign.actors.erase("practice_patient"); main.call("_on_state_changed",&"campaign")
	expect(not body._health_shown,"campaign-only lesson completion removes the friendly health lease")
	app.campaign=state.duplicate(true); app.actors.erase(2); main.set("actor_nodes",{})
	main.call("_on_state_changed",&"campaign")
	app.actors[2]=patient; main.set("actor_nodes",{2:body}); main.call("_apply_overhead_health",2,-1)
	expect(body._health_shown,"the ordinary actor health path also admits a patient whose body arrives after the campaign")
	for case: String in ["no_alias","wrong_mentor","other_map","paused","complete","no_run","public","sparring","other_quest"]:
		app.campaign=state.duplicate(true); app.current_map="landfall_town"
		match case:
			"no_alias": app.campaign.actors.erase("practice_patient")
			"wrong_mentor": app.campaign.actors.mentor=3
			"other_map": app.current_map="landfall"
			"paused": app.campaign.active=false
			"complete": app.campaign.active=false; app.campaign.completed=true
			"no_run": app.campaign.run_id=""
			"public": app.campaign.shelves.private_practice=false
			"sparring": app.campaign.shelves.sparring=true
			"other_quest": app.campaign.kind="rescue"
		expect(not main.call("_is_shelves_practice_patient",2,patient)
			and not main.call("_spell_target_candidate",1,2),case+" cannot grant targeted-heal eligibility")
	app.campaign=state.duplicate(true)
	expect(not main.call("_is_shelves_practice_patient",0,patient)
		and not main.call("_is_shelves_practice_patient",2,{"kind":3}),"nonpositive IDs and creature kinds cannot impersonate the ally")
	main.set("actor_nodes",{}); body.queue_free()
	app.authenticated=false; main.queue_free()
	for _i: int in 3:await process_frame
	print("Heal Target lesson client: %d checks; %d failures"%[checks,failures])
	quit(1 if failures else 0)
