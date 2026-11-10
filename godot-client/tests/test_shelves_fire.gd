extends "res://tests/test_shelves_dialogue_flow.gd"
func snapshot()->Dictionary:
	var s:Dictionary=Supplies.snapshot();s.key="fire";s.title="The Toll at Blackcut";s.stage="work";s.scene={};s.targets=[]
	s.shelves.chapter="fire";s.shelves.phase="work";s.shelves.current_supply="Fire";s.shelves.unlocked=["Life"]
	s.shelves.fire={"stage":"fire","route":"silence","step":"extract","recovered":1000,"mined":100,
		"recovered_goal":4000,"mined_goal":1000,"carried":25,"repair":0,"passages":0,
		"signal":true,"water":false,"powder":false,"wave":2,"cart_tile":[51,216],"carts":[{"actor_id":102,"tile":[51,216],"height":0.0},{"actor_id":103,"tile":[52,216],"height":0.0}],"workers":[],"hazards":[]}
	for i:int in 4:s.shelves.fire.workers.append({"actor_id":100+i,"name":"Crew "+str(i),"health":80,"max_health":80,
		"downed":false,"cargo":25 if i==0 else 0,"activity":"harvest","harvesting":true})
	return s
func run()->void:
	root.get_node("Network").block_for_hud_preview()
	var evidence:=OS.get_environment("RL_FIRE_EVIDENCE")
	if not evidence.is_empty():
		var rows:Variant=JSON.parse_string(FileAccess.get_file_as_string(evidence))
		expect(rows is Array and rows.size()>10,"native evidence includes branching work, confrontation and reports")
		for row:Dictionary in rows:
			var decoded:=EloriaProtocol.decode_campaign(JSON.stringify(row).to_utf8_buffer())
			expect(decoded.type=="campaign","native "+str(row.title)+" / "+str(row.stage)+": "+str(decoded.get("error","valid")))
	var s:=snapshot()
	expect(EloriaProtocol.decode_campaign(JSON.stringify(s).to_utf8_buffer()).type=="campaign","Fire shipment uses the production decoder")
	var bad:=s.duplicate(true);bad.shelves.fire.recovered=4001
	expect(EloriaProtocol.decode_campaign(JSON.stringify(bad).to_utf8_buffer()).type=="invalid","shipment totals cannot exceed secured stock")
	bad=s.duplicate(true);bad.shelves.fire.workers[1].actor_id=100
	expect(EloriaProtocol.decode_campaign(JSON.stringify(bad).to_utf8_buffer()).type=="invalid","duplicate workers are rejected")
	bad=s.duplicate(true);bad.shelves.fire.hazards=[{"kind":"warning","tile":[51,216],"radius":100,"seconds":4}]
	expect(EloriaProtocol.decode_campaign(JSON.stringify(bad).to_utf8_buffer()).type=="invalid","unbounded blast zones are rejected")
	var hud:Control=load("res://src/ui/campaign_hud.gd").new();root.add_child(hud);hud.apply_state(s,Vector2i(51,216),"landfall")
	expect(hud._shelves.text.contains("Recovered stock secured: 1000/4000") and hud._shelves.text.contains("Newly mined secured: 100/1000"),"the ledger distinguishes recovered stock from new mining")
	var app:Node=root.get_node("AppState");app.authenticated=true;app.current_map="landfall";app.campaign=s;app.actors={}
	for worker:Dictionary in s.shelves.fire.workers:app.actors[int(worker.actor_id)]={"kind":2,"actor_type":0,"name":worker.name,"x":51,"y":216}
	var windows:Node=load("res://src/ui/extension_windows.gd").new()
	expect(windows._quest_party_members().size()==4,"all four Fire workers use the normal party companion view")
	var main:Node=load("res://src/app/main.gd").new()
	expect(main._is_shelves_grower(100,app.actors[100]),"Fire workers have visible health before selection")
	var f:Dictionary=fixture("measure.shelves.fire.entry_quarry")
	f.state.key="fire"
	f.state.scene.choice={"id":"shelves_fire_quarry","title":"How shall we reopen Blackcut?","owner":"You","owner_is_you":true,
		"can_choose":true,"selected":"","response":"","options":[{"id":"assault","label":"Break the barricade","detail":"Fight"},{"id":"silence","label":"Silence the alarm","detail":"Flank"}]}
	tick(f);f.scene.skip();tick(f)
	expect(f.scene._choice_waiting and f.acks.is_empty(),"Return to Play stops at the unanswered quarry decision")
	f.state.scene.choice.selected="silence";f.state.scene.choice.can_choose=false;f.state.scene.choice.response="Cut the signal rope before releasing the crew."
	tick(f)
	expect(f.scene._dialogue.body_label.text==f.state.scene.choice.response,"Brenna gives follow-up instructions in the same dialogue frame")
	f.scene.continue_dialogue();tick(f,3)
	expect(f.acks==["one"] and not f.scene.blocks_input(),"finishing the route reply returns control and acknowledges once")
	dispose(f)
	f=fixture("measure.shelves.fire.report");f.scene.continue_dialogue()
	expect(f.scene.blocks_input() and f.acks==["one"],"the reward conversation holds its portrait for the next assignment")
	f.state.key="fire_coal";f.state.scene={"id":"measure.shelves.fire.brief","token":"two","requires_ack":true,"actors":f.state.scene.actors}
	tick(f)
	expect(f.scene.playing and f.scene._dialogue.visible,"the next briefing starts without briefly revealing gameplay")
	dispose(f)
	f=fixture("measure.shelves.fire.report_final");f.scene.continue_dialogue()
	expect(not f.scene.blocks_input() and f.acks==["one"],"the final Continue closes the conversation without waiting for another quest")
	dispose(f)
	var registry:Dictionary=JSON.parse_string(FileAccess.get_file_as_string("res://data/actors/models.json"))
	var actor:=ReplicatedActor3D.new();root.add_child(actor)
	var dto:Dictionary={"actor_id":200,"kind":3,"actor_type":791,"name":"Powder store","x":51,"y":216,"rotation":0,"health":300,"max_health":300,"alive":true}
	var config:Dictionary=registry.models[registry.actorTypes["791"]]
	var errors:=actor.configure(dto,main.adapter,config,main._animation_for_model(config),{})
	expect(errors.is_empty() and actor.get_node_or_null("NativeModel")!=null,"the spell target is an actual approved barrel model")
	var works:Node3D=load("res://src/world/campaign_fire_works.gd").new();root.add_child(works)
	s.shelves.fire.stage="fire_coal";s.anchors={"lift":[51,216],"storage":[54,216],"stock":[48,216]}
	s.shelves.fire.hazards=[{"kind":"warning","tile":[52,216],"radius":2,"seconds":4}]
	works.apply_snapshot(s,main.adapter,"landfall",func(_p:Vector3)->float:return 0.0)
	expect(works.props.has("lift") and works.props.has("cart") and works.props.has("cart_two"),"the Coal route shows native hauling machinery and both crew carts")
	expect(is_instance_valid(works._warning) and works._warning.get("pointer").text.contains("MOVE"),"blast warnings explain the required action on the ground")
	works.clear();await process_frame
	expect(works.get_child_count()==0,"leaving a worksite removes its props and warnings")
	works.free();actor.free();windows.free();hud.queue_free()
	app.authenticated=false;app.campaign={};app.actors={}
	var freed:Dictionary={}
	for property:Dictionary in main.get_property_list():
		if (int(property.get("usage",0)) & PROPERTY_USAGE_SCRIPT_VARIABLE)==0:continue
		var value:Variant=main.get(str(property.name))
		if value is Node and is_instance_valid(value) and value!=main and value.get_parent()==null and not freed.has(value.get_instance_id()):freed[value.get_instance_id()]=true;value.free()
	main.free();NativeAnimationImporter.clear();GlbSceneCache.clear();CharacterProportions.clear()
	print("Fire supply client: %d checks, %d failures" % [checks,failures]);quit(1 if failures else 0)
