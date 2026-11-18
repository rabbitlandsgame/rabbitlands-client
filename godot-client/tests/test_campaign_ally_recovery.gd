extends "res://tests/test_shelves_water.gd"
const Recovery := preload("res://src/ui/campaign_ally_recovery.gd")
const RescueState := preload("res://tests/test_campaign_rescue.gd")

func run() -> void:
	var network := root.get_node("Network")
	network.block_for_hud_preview()
	var recorder := GDScript.new()
	recorder.source_code = 'extends "res://src/network/network_client.gd"\nvar sent_frames:Array=[]\nfunc send_frame(frame:PackedByteArray,_sensitive:=false)->Error:\n\tsent_frames.append(frame)\n\treturn OK\n'
	expect(recorder.reload() == OK, "the real spell transport recorder compiles")
	network.set_script(recorder); network.block_for_hud_preview()
	var state := snapshot()
	state.shelves.water.workers[0].merge({"downed":true,"health":0}, true)
	expect(Recovery.patients(state,"landfall")==[{"actor_id":100,"name":"Cutter 0"}], "the exact fallen cutter offers recovery")
	var before := JSON.stringify(state)
	var hud: Control = load("res://src/ui/campaign_hud.gd").new()
	root.add_child(hud)
	var healthy:=state.duplicate(true);healthy.shelves.water.workers[0].merge({"downed":false,"health":80},true)
	hud.apply_state(healthy,Vector2i(430,300),"landfall")
	expect(not hud._recovery_actions.visible,"healthy work offers no unnecessary healing control")
	hud.apply_state(state,Vector2i(430,300),"landfall")
	expect(hud._recovery_actions.visible and hud._recovery_actions.get_child_count()==1
		and "Heal Target" in hud._recovery_actions.get_child(0).text, "the quest card exposes a named native healing action")
	expect(hud._recovery_actions.get_index()<hud._scroll.get_index(),"a newly fallen worker's recovery moves above the already-visible routine work objectives")
	expect(JSON.stringify(state)==before and network.sent_frames.is_empty(),"displaying a fallen ally never casts or claims recovery")
	var host := (load("res://src/app/main.tscn") as PackedScene).instantiate()
	root.add_child(host);host.set_process(false);host.hide()
	var app := root.get_node("AppState")
	app.authenticated=true;app.death={};app.local_actor_id=1;app.current_map="landfall";app.campaign=state
	app.actors={1:{"kind":1,"alive":true,"health":20,"x":430,"y":300},
		100:{"kind":2,"alive":false,"health":0,"max_health":80,"x":431,"y":300},
		101:{"kind":2,"alive":true,"health":60,"max_health":80,"x":432,"y":300},
		900:{"kind":2,"alive":false,"health":0,"max_health":80,"x":430,"y":301}}
	var body := ReplicatedActor3D.new();root.add_child(body)
	host.actor_nodes={100:body,101:body};host._grounded_actors={1:true}
	expect(host._spell_target_candidate(1,100),"ordinary manual Heal Target can select the fallen current crew member")
	expect(host._spell_target_candidate(1,101),"ordinary manual Heal Target can help an injured living crew member")
	expect(not host._spell_target_candidate(1,900) and not host._spell_target_candidate(68,100)
		and not host._is_attackable_actor(100,app.actors[100]),"crew healing grants no unrelated NPC or offensive targeting")
	hud.ally_heal_requested.connect(host._on_campaign_ally_heal)
	network.sent_frames.clear()
	hud._recovery_actions.get_child(0).pressed.emit()
	expect(network.sent_frames.size()==1,"one explicit quest-card click sends the normal cast")
	if network.sent_frames.size()==1:
		var frame:PackedByteArray=network.sent_frames[0]
		var request:Dictionary=JSON.parse_string(frame.slice(3).get_string_from_utf8())
		expect(frame[0]==202
			and request.size()==4 and request.get("op")=="cast" and int(request.get("id",-1))==1
			and int(request.get("power",0))==1 and int(request.get("target_id",-1))==100,"the exact native targeted spell request retains Power 1 and its real recipient")
	host.magic_selection.active_target_cast={"id":1,"power":1,"target_id":100}
	hud._recovery_actions.get_child(0).pressed.emit()
	expect(network.sent_frames.size()==1,"a repeat recovery click cannot cancel the active cast")
	host.magic_selection.active_target_cast.clear()
	for variant: String in ["hidden","blocked","other_map","paused","travel","other_run","recovered","missing_body","dead_player"]:
		app.campaign=state.duplicate(true);app.current_map="landfall";app.actors[1].health=20;host.actor_nodes={100:body}
		hud.show();hud.apply_state(app.campaign,Vector2i(430,300),"landfall")
		match variant:
			"hidden":hud.hide()
			"blocked":hud.apply_state(app.campaign,Vector2i(430,300),"landfall",false,true)
			"other_map":app.current_map="landfall_town"
			"paused":app.campaign.active=false
			"travel":app.campaign.travel={"npc":"Ilka"}
			"other_run":app.campaign.run_id="later-run"
			"recovered":app.campaign.shelves.water.workers[0].downed=false
			"missing_body":host.actor_nodes={}
			"dead_player":app.actors[1].health=0
		network.sent_frames.clear();hud._request_ally_heal(str(state.run_id),100)
		expect(network.sent_frames.is_empty(),variant+" rejects a stale recovery action")
	var rescued := RescueState.snapshot();rescued.scene={};rescued.map="landfall_insides"
	rescued.rescue.stage="boss_defeated";rescued.rescue.mother.merge({"configured":true,"enabled":true,"downed":true,"health":0},true)
	expect(Recovery.patients(rescued,"landfall_insides")==[{"actor_id":20,"name":"Elen Reed","assisted":true}],"fallen Elen retains her unused first recovery lesson before the family leaves after the boss")
	rescued.completed=false;rescued.party.role="eligible";rescued.rescue.reward.claimed=true
	expect(Recovery.contains(rescued,"landfall_insides",20),"a prior rewarded rescuer can still help fallen Elen in another owner's current expedition")
	hud.show();hud.apply_state(rescued,Vector2i(430,300),"landfall_insides")
	expect(hud._recovery_actions.visible and hud._rescue.visible and hud._leave.text=="Return"
		and "first recovery lesson" in hud._recovery_actions.get_child(0).tooltip_text,"an eligible helper retains the shared encounter's recovery controls")
	rescued.rescue.stage="injured"
	expect(Recovery.contains(rescued,"landfall_insides",20),"the actual downed mine-patient stage retains Elen's recovery action")
	rescued.map="landfall"
	expect(Recovery.patients(rescued,"landfall").is_empty(),"the road patient's existing first lesson is not duplicated")
	for field: String in ["growers","fire"]:
		var other := state.duplicate(true);other.shelves[field]={"workers":other.shelves.water.workers};other.shelves.erase("water")
		expect(Recovery.contains(other,"landfall",100),field+" uses the same exact-ally recovery action")
	for variable: String in ["RL_SUPPLY_RECOVERY_EVIDENCE","RL_RESCUE_FIELD_EVIDENCE"]:
		var path := OS.get_environment(variable)
		if path.is_empty():continue
		var bundle:Variant=JSON.parse_string(FileAccess.get_file_as_string(path))
		var records:Array=bundle.snapshots if bundle is Dictionary else bundle
		for native:Dictionary in records:
			var decoded:=EloriaProtocol.decode_campaign(JSON.stringify(native).to_utf8_buffer())
			expect(decoded.type=="campaign","the actual native recovery snapshot decodes without a new protocol")
			if decoded.type!="campaign":continue
			var patients:=Recovery.patients(decoded.state,str(native.map))
			var expected_ids:Array=[]
			if variable=="RL_SUPPLY_RECOVERY_EVIDENCE":
				for field:String in ["growers","fire","water"]:
					for worker:Dictionary in (native.shelves.get(field,{}) as Dictionary).get("workers",[]):
						if bool(worker.downed):expected_ids.append(int(worker.actor_id))
			else:
				if bool(native.rescue.mother.downed):expected_ids.append(int(native.actors.mother))
			var actual_ids:Array=[]
			for patient:Dictionary in patients:actual_ids.append(int(patient.actor_id))
			expect(actual_ids==expected_ids,"native fallen allies and recovered allies produce exactly the appropriate controls")
			app.campaign=decoded.state;app.current_map=str(native.map);app.actors={}
			for actor_id:int in expected_ids:
				var dto:Dictionary=(native.get("native_cast",{}) as Dictionary).get("mother",{}).duplicate(true)
				if dto.is_empty():dto={"kind":2,"health":1,"max_health":80}
				app.actors[actor_id]=dto
				expect(host._spell_target_candidate(1,actor_id),"the actual native campaign's fallen ally remains eligible for normal manual targeting")
			hud.show();hud.apply_state(decoded.state,Vector2i(430,300),str(native.map))
			expect(hud._recovery_actions.get_child_count()==expected_ids.size()
				and hud._recovery_actions.visible==not expected_ids.is_empty(),"the actual native guide renders the right recovery controls without casting")
			if variable=="RL_RESCUE_FIELD_EVIDENCE" and not expected_ids.is_empty():
				expect(not hud._patient_heal.visible and "Elen Reed" in hud._rescue.text,"known Elen has one named recovery action, including the injured mine stage")
				var assisted:bool=int(native.rescue.patient.lesson_remaining)>0
				expect(hud._recovery_actions.get_child_count()>0 and ("first recovery lesson" in hud._recovery_actions.get_child(0).tooltip_text)==assisted,
					"the tooltip distinguishes real remaining assistance from ordinary paid healing")
	host.actor_nodes={};app.authenticated=false;host.queue_free();body.queue_free();hud.queue_free()
	for _i in 3:await process_frame
	print("Quest ally recovery: %d checks; %d failures"%[checks,failures]);quit(0 if failures==0 else 1)
