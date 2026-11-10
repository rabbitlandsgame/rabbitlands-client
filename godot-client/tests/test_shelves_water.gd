extends "res://tests/test_shelves_dialogue_flow.gd"

func snapshot()->Dictionary:
	var s:Dictionary=Supplies.snapshot();s.key="water_cutters";s.title="The Cutters’ Share";s.stage="work";s.scene={};s.targets=[]
	s.shelves.chapter="water_cutters";s.shelves.phase="work";s.shelves.current_supply="Water";s.shelves.unlocked=["Life","Fire"]
	s.shelves.water={"stage":"water_cutters","route":"","command":"work","flow":[2,1,0],"channels":true,
		"stored":{"kelp":1000,"cress":500},"bins":{"kelp":200,"cress":100},"cut":{"kelp":1200,"cress":600},"goals":{"kelp":4000,"cress":2000},
		"workers":[],"bed":0,"hull":100,"landing":0,"sailing":false,"boat_tile":[430,300],"path":[[430,300],[431,300]],"north":false,"south":false,"boss_defeated":false,"wave":2,"hazards":[]}
	for i:int in 4:s.shelves.water.workers.append({"actor_id":100+i,"name":"Cutter "+str(i),"health":80,"max_health":80,
		"downed":false,"cargo":0,"activity":"return" if i==3 else "harvest","harvesting":i<3})
	return s

func run()->void:
	root.get_node("Network").block_for_hud_preview()
	var evidence:=OS.get_environment("RL_WATER_EVIDENCE")
	if not evidence.is_empty():
		var rows:Variant=JSON.parse_string(FileAccess.get_file_as_string(evidence))
		expect(rows is Array and rows.size()>15,"native evidence covers gate choices, crew, boat and final report")
		for row:Dictionary in rows:
			var decoded:=EloriaProtocol.decode_campaign(JSON.stringify(row).to_utf8_buffer())
			expect(decoded.type=="campaign","native "+str(row.title)+" / "+str(row.stage)+": "+str(decoded.get("error","valid")))
	var s:=snapshot()
	expect(EloriaProtocol.decode_campaign(JSON.stringify(s).to_utf8_buffer()).type=="campaign","Water shipment uses the production decoder")
	var bad:=s.duplicate(true);bad.shelves.water.cut.kelp=4001
	expect(EloriaProtocol.decode_campaign(JSON.stringify(bad).to_utf8_buffer()).type=="invalid","cutting cannot exceed the authored shipment")
	bad=s.duplicate(true);bad.shelves.water.workers[1].actor_id=100
	expect(EloriaProtocol.decode_campaign(JSON.stringify(bad).to_utf8_buffer()).type=="invalid","duplicate crew identities are rejected")
	bad=s.duplicate(true);bad.shelves.water.path.resize(513)
	expect(EloriaProtocol.decode_campaign(JSON.stringify(bad).to_utf8_buffer()).type=="invalid","unbounded boat paths are rejected")
	var hud:Control=load("res://src/ui/campaign_hud.gd").new();root.add_child(hud);hud.apply_state(s,Vector2i(430,300),"landfall")
	expect(hud._shelves.text.contains("Cut 1200/4000") and hud._shelves.text.contains("Secured 1000/4000"),"the ledger distinguishes cutting from secured delivery")
	var app:Node=root.get_node("AppState");app.authenticated=true;app.current_map="landfall";app.campaign=s;app.actors={}
	for worker:Dictionary in s.shelves.water.workers:app.actors[int(worker.actor_id)]={"kind":2,"actor_type":0,"name":worker.name,"x":430,"y":300}
	var windows:Node=load("res://src/ui/extension_windows.gd").new()
	expect(windows._quest_party_members().size()==4,"all four Water workers appear in the companion view")
	var main:Node=load("res://src/app/main.gd").new()
	expect(main._is_shelves_grower(100,app.actors[100]),"worker health is visible before selection")
	var f:Dictionary=fixture("measure.shelves.water.entry_water")
	f.state.key="water"
	f.state.scene.choice={"id":"shelves_water_gates","title":"How shall we restore the channels?","owner":"You","owner_is_you":true,
		"can_choose":true,"selected":"","response":"","options":[{"id":"repair","label":"Repair the gates","detail":"Balance flow"},{"id":"breach","label":"Breach the diversion","detail":"Fight"}]}
	tick(f);f.scene.skip();tick(f)
	expect(f.scene._choice_waiting and f.acks.is_empty(),"Return to Play stops at the player's gate decision")
	expect(f.scene._dialogue._actor!=null and f.scene._dialogue._actor.get_ref()==f.player,"choices bind the real player's portrait without staging their body")
	f.state.scene.choice.selected="repair";f.state.scene.choice.can_choose=false;f.state.scene.choice.response="Fresh two, Tide one, Drain zero. Test the channels when ready."
	tick(f)
	expect(f.scene._dialogue.body_label.text==f.state.scene.choice.response,"Iona gives the chosen instructions in the same portrait frame")
	f.scene.continue_dialogue();tick(f,3)
	expect(f.acks==["one"] and not f.scene.blocks_input(),"the gate conversation releases control and acknowledges once")
	dispose(f)
	f=fixture("measure.shelves.water.report");f.state.key="water";f.scene.continue_dialogue()
	expect(f.scene.blocks_input() and f.acks==["one"],"the reward portrait holds for the next briefing")
	f.state.key="water_cutters";f.state.scene={"id":"measure.shelves.water.brief","token":"two","requires_ack":true,"actors":f.state.scene.actors}
	tick(f)
	expect(f.scene.playing and f.scene._dialogue.visible,"the next Water briefing arrives without a gameplay flash")
	dispose(f)
	f=fixture("measure.shelves.water.report_final");f.scene.continue_dialogue()
	expect(not f.scene.blocks_input() and f.acks==["one"],"final Continue closes the conversation immediately")
	dispose(f)
	var registry:Dictionary=JSON.parse_string(FileAccess.get_file_as_string("res://data/actors/models.json"))
	var actor:=ReplicatedActor3D.new();root.add_child(actor)
	var dto:Dictionary={"actor_id":200,"kind":5,"actor_type":792,"name":"Veyra Lockhand","x":430,"y":276,"rotation":0,"health":500,"max_health":500,"alive":true}
	var config:Dictionary=registry.models[registry.actorTypes["792"]]
	var presented:Dictionary=main._presentation_dto(dto)
	var errors:=actor.configure(presented,main.adapter,config,main._animation_for_model(config),{})
	expect(errors.is_empty() and actor.get_node_or_null("NativeModel")!=null,"Veyra uses an approved native Human body")
	expect(int(presented.appearance.head)==0 and presented.equipment_visuals.has(0),"the captain has visible equipment and no headpiece")
	var works:Node3D=load("res://src/world/campaign_water_works.gd").new();root.add_child(works)
	s.shelves.water.stage="water_barge";s.shelves.water.route="sheltered"
	s.anchors={"entry":[430,300],"upper":[425,300],"sea":[435,300],"cress":[425,305],"kelp_a":[435,305],"landing_end":[438,300]}
	s.shelves.water.hazards=[{"kind":"warning","tile":[430,300],"radius":2,"seconds":4},{"kind":"impact","tile":[432,300],"radius":2,"seconds":2}]
	works.apply_snapshot(s,main.adapter,"landfall",func(_p:Vector3)->float:return 0.0)
	expect(works.water_props.has("boat") and works.water_props.has("upper") and works.water_props.has("landing_end"),"the worksite shows real gates, boat and landing art")
	expect(works._streams.size()>=3,"gathering channels and the boat's waterway are visible")
	expect(is_instance_valid(works._surge) and works._surge.get("pointer").text.contains("MOVE"),"surge warnings give an explicit movement instruction")
	var controls:Dictionary={}
	for id:int in range(61840,61852)+[61990]:
		var control:=MapObject3D.new();control.object_id=id;root.add_child(control);controls[id]=control
	s.targets=[]
	for id:int in [61843,61847,61848,61849]:s.targets.append({"id":str(id),"object_id":id,"tile":[434,301],"label":"Boat command","enabled":true})
	works.apply_controls(s,main.adapter,"landfall",func(_p:Vector3)->float:return 2.0,controls,false)
	expect(controls[61843].visible and not controls[61848].visible and not controls[61849].visible,"one obstruction control represents the shared boat station")
	expect(not controls[61840].visible and controls[61840].collision_layer==0,"unused chapter controls have no map marker or world pick")
	s.targets.remove_at(0);s.shelves.water.sailing=true
	for target:Dictionary in s.targets:target.tile=[435,301]
	works.apply_controls(s,main.adapter,"landfall",func(_p:Vector3)->float:return 2.0,controls,false)
	expect(controls[61847].visible and controls[61847].collision_layer==MapObject3D.PICK_LAYER and not controls[61848].visible,"the moving boat offers Wait while sailing")
	expect(controls[61847].server_tile==Vector2i(435,301) and is_equal_approx(controls[61847].global_position.y,2.0),"native world controls follow the server's boat position and ground")
	works.apply_controls(s,main.adapter,"landfall",func(_p:Vector3)->float:return 2.0,controls,true)
	expect(controls[61847].collision_layer==0,"cinematics block native boat picks")
	s.shelves.water.stage="water_cutters";s.shelves.water.command="wait";s.targets=[]
	for id:int in [61845,61846,61847]:s.targets.append({"id":str(id),"object_id":id,"tile":[433,302],"label":"Crew command","enabled":true})
	works.apply_controls(s,main.adapter,"landfall",func(_p:Vector3)->float:return 0.0,controls,false)
	expect(controls[61845].visible and not controls[61846].visible and not controls[61847].visible,"a waiting crew offers one Work pick with alternate commands in the quest window")
	for control:MapObject3D in controls.values():control.free()
	works.clear();await process_frame
	expect(works.get_child_count()==0,"leaving removes all Water props and flow effects")
	works.free();actor.free();windows.free();hud.queue_free()
	app.authenticated=false;app.campaign={};app.actors={}
	var freed:Dictionary={}
	for property:Dictionary in main.get_property_list():
		if (int(property.get("usage",0)) & PROPERTY_USAGE_SCRIPT_VARIABLE)==0:continue
		var value:Variant=main.get(str(property.name))
		if value is Node and is_instance_valid(value) and value!=main and value.get_parent()==null and not freed.has(value.get_instance_id()):freed[value.get_instance_id()]=true;value.free()
	main.free();NativeAnimationImporter.clear();GlbSceneCache.clear();CharacterProportions.clear()
	print("Water supply client: %d checks, %d failures" % [checks,failures]);quit(1 if failures else 0)
