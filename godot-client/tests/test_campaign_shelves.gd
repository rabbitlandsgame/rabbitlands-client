extends SceneTree
const Bodies:=preload("res://tests/test_campaign_scene_recovery.gd")
var checks:=0
var failures:=0
func _init()->void:run.call_deferred()
func expect(ok:bool,message:String)->void:
	checks+=1
	if ok:print("PASS: ",message)
	else:failures+=1;push_error(message)

func return_fixture()->Dictionary:
	var rig:=IsometricCameraController.new()
	var camera:=Camera3D.new();camera.name="Camera";rig.add_child(camera)
	camera.owner=rig;camera.unique_name_in_owner=true;root.add_child(rig)
	var actor:=Bodies.Actor.new();root.add_child(actor);rig.set_focus(actor.position)
	var scene:Node=load("res://src/world/campaign_scene.gd").new();root.add_child(scene)
	scene.set_auto_dialogue(true,false)
	scene._scene_id="measure.shelves.review";scene._token="finish";scene._run="shelves-run";scene._map="landfall"
	scene._definition={"duration":1,"entry_seconds":0,"exit_seconds":0,"native_roles":["protagonist"],"live_camera":"gameplay","shots":[],"handoff":{"mode":"fade","to":[],"gameplay_map":"landfall_town"}}
	scene._start(rig,rig.camera,actor,{1:actor},{"protagonist":1})
	return {"scene":scene,"rig":rig,"actor":actor,"state":{"active":true,"kind":"shelves","run_id":"shelves-run","map":"landfall","scene":{"id":"measure.shelves.review","token":"finish","requires_ack":true}}}

func return_tick(f:Dictionary,delta:float,ready:=true,here:="landfall")->void:
	f.scene.update(delta,f.state,f.rig,{1:f.actor},1,here,ready)

static func snapshot()->Dictionary:
	return {"version":1,"kind":"shelves","active":true,"available":false,"started":true,"completed":false,
		"run_id":"shelves-run","map":"landfall","stage":"brief","key":"intro","title":"The Last Few Measures",
		"hint":"Learn the four starter casts and a real Life Essence mix.","targets":[],"actors":{"mentor":20,"protagonist":1},
		"party":{"owner":"Aster","role":"owner","members":[]},
		"shelves":{"chapter":"intro","phase":"brief","objectives":[{"id":"mix","label":"Mix three Life Essences","current":0,"target":3,"personal":true}],
			"unlocked":[],"cart_tile":[268,128],"cart_integrity":100,"samples":0,"can_complete":false},
		"scene":{"id":"measure.shelves.brief","token":"shelves-run:intro:1","requires_ack":true,"variant":"intro",
			"actors":{"mentor":20,"protagonist":1,"recipient":1},"choice":{"id":"shelves_route","title":"How shall we proceed?","owner":"Aster","owner_is_you":true,
				"can_choose":true,"selected":"","response":"","options":[{"id":"direct","label":"Learn by doing","detail":"Practise together."},
				{"id":"careful","label":"Check my existing knowledge","detail":"Demonstrate the same real skills."}]}}}

func run()->void:
	create_timer(90).timeout.connect(func()->void:push_error("Supply quest checks timed out");quit(1))
	var state:=snapshot()
	var evidence:=OS.get_environment("RL_SHELVES_PROTOCOL_EVIDENCE")
	if not evidence.is_empty():
		var native:Variant=JSON.parse_string(FileAccess.get_file_as_string(evidence))
		expect(native is Array and native.size()>=33,"native playthrough supplies every chapter’s actual state packets")
		if native is Array:
			for row:Dictionary in native:
				var decoded:=EloriaProtocol.decode_campaign(JSON.stringify(row).to_utf8_buffer())
				expect(decoded.type=="campaign","native "+str(row.get("key",row.get("title")))+" / "+str(row.get("stage","complete"))+" decodes: "+str(decoded.get("error","valid")))
	expect(EloriaProtocol.decode_campaign(JSON.stringify(state).to_utf8_buffer()).type=="campaign","the supply ledger and cinematic route pass the actual protocol decoder")
	for field:String in ["current","target"]:
		var bad:=state.duplicate(true);bad.shelves.objectives[0][field]=-1
		expect(EloriaProtocol.decode_campaign(JSON.stringify(bad).to_utf8_buffer()).type=="invalid","negative supply "+field+" is rejected")
	var duplicate:=state.duplicate(true);duplicate.shelves.unlocked=["Life","Life"]
	expect(EloriaProtocol.decode_campaign(JSON.stringify(duplicate).to_utf8_buffer()).type=="invalid","duplicate shelf unlocks are rejected")
	var wrong:=state.duplicate(true);wrong.scene.id="measure.shelves.lesson"
	expect(EloriaProtocol.decode_campaign(JSON.stringify(wrong).to_utf8_buffer()).type=="invalid","a route decision cannot masquerade as an apprentice lesson")
	var network:=root.get_node("Network");network.block_for_hud_preview()
	var recorder:=GDScript.new()
	recorder.source_code='extends "res://src/network/network_client.gd"\nvar sent_frames:Array=[]\nfunc send_frame(frame:PackedByteArray,_sensitive:=false)->Error:\n\tsent_frames.append(frame)\n\treturn OK\n'
	expect(recorder.reload()==OK,"the offline request recorder compiles")
	network.set_script(recorder);network.block_for_hud_preview()
	var app:=root.get_node("AppState");app.authenticated=false;app.current_map="";app.actors={}
	var main:Control=(load("res://src/app/main.tscn") as PackedScene).instantiate();root.add_child(main)
	main.set_process(false);main.set_physics_process(false);await process_frame
	app.authenticated=true;app.current_map="landfall";app.local_actor_id=1;app.death={};app.campaign=state
	var hero:=Bodies.Actor.new();var mentor:=Bodies.Actor.new()
	main.world_root.add_child(hero);main.world_root.add_child(mentor)
	hero.server_target=Vector3(1,0,0);hero.position=hero.server_target;mentor.server_target=Vector3(2,0,1);mentor.position=mentor.server_target
	main.actor_nodes={1:hero,20:mentor};app.actors={1:{"actor_id":1,"kind":1,"health":30,"x":1,"y":0}}
	main.camera_rig.set_focus(hero.position)
	var scene:Node=main.campaign_scene;scene.set_auto_dialogue(true,false)
	scene.update(2.1,state,main.camera_rig,main.actor_nodes,1,"landfall",true,CoordinateAdapter.new({"walkingHeight":0}),func(_p:Vector3)->float:return 0)
	expect(scene.playing and scene._dialogue.visible and scene._caption.text.contains("shelves"),"Ilka speaks inside the shared cinematic dialogue")
	scene.skip();scene.update(0.1,state,main.camera_rig,main.actor_nodes,1,"landfall",true)
	expect(scene.choice_context().waiting and scene._choice_dialog.option_buttons.size()==2,"Return to Play stops at the two live route choices")
	expect(scene._dialogue._actor.get_ref()==hero,"route options show the player’s portrait in the normal dialogue frame")
	main._on_campaign_scene_choice("direct")
	expect(network.sent_frames.size()==1 and (network.sent_frames[0] as PackedByteArray).slice(3).get_string_from_utf8().contains("shelves_choice shelves-run shelves-run:intro:1 direct"),"the real cinematic choice submits one token-scoped native request")
	network.sent_frames.clear();scene._replaying=true;main._on_campaign_scene_choice("careful")
	expect(network.sent_frames.is_empty(),"read-only replay cannot submit another route")
	scene._replaying=false;scene.cancel("test_stop")
	state.stage="work";state.scene={};state.targets=[{"id":"sage","object_id":31,"tile":[1,0],"label":"Gather Sage","enabled":true,"harvest":true}]
	main._on_campaign_target(31,Vector2i(1,0),true)
	expect(network.sent_frames.size()==1 and network.sent_frames[0]==EloriaProtocol.harvest(31),"a supply gathering action uses the normal harvest request")
	var windows:Control=main.extension_windows
	app.merchant={"gold":10000,"capacity":100,"carried":0}
	windows._merchant_mode="buy"
	expect(windows._merchant_maximum({"buy_price":0,"emu":0})==0,"out-of-stock weightless essences cannot be bought for free")
	expect(windows._merchant_price_label({"buy_price":0},false)=="Out of stock","locked essence rows show Out of stock")
	expect(main._model_for_actor({"actor_type":0,"kind":2,"name":"Mara Vale"})=="luminous_female"
		and not main._model_for_actor({"actor_type":309,"kind":2,"name":"Tovin"}).is_empty(),"the apprentices use supported native bodies rather than legacy placeholder records")
	var travel:=snapshot();travel.stage="travel";travel.scene={};travel.targets=[]
	travel.shelves.phase="travel";travel.shelves.can_begin=false;travel.shelves.start_label="Start the delivery escort"
	travel.travel={"map":"landfall","tile":[268,128],"label":"Potters’ loading point","route":"Walk to the loading point and start the delivery when ready.",
		"via":[{"map":"landfall_town","tile":[175,21],"label":"Leave The True Note for the supply worksite"}]}
	expect(EloriaProtocol.decode_campaign(JSON.stringify(travel).to_utf8_buffer()).type=="campaign","a saved travel assignment passes the native decoder")
	var invalid_pin:=travel.duplicate(true);invalid_pin.travel.via[0].tile=[-1,21]
	expect(EloriaProtocol.decode_campaign(JSON.stringify(invalid_pin).to_utf8_buffer()).type=="invalid","malformed route markers are rejected")
	var guide:Script=preload("res://src/world/campaign_guidance.gd")
	expect(guide.navigation_targets(travel,"landfall",true)[0].tile==[268,128],"Landfall shows the actual worksite marker")
	expect(guide.navigation_targets(travel,"landfall_town",true)[0].tile==[175,21],"the shop map marks its exit instead of plotting outdoor coordinates inside the shop")
	expect(guide.navigation_targets(travel,"twinbrook",true).is_empty(),"markers do not leak onto another region")
	expect(guide.navigation_targets(travel,"landfall",false).is_empty(),"untracking removes destination markers without changing the assignment")
	app.campaign=travel;app.current_map="landfall_town"
	main.lantern_guide.apply_campaign(travel);main.lantern_guide.set_campaign_tracked(true)
	expect(not str(main.lantern_guide.campaign_entry().objective).contains("Speak with the local crew"),"travel instructions do not invent a conversation at an unmanned worksite")
	expect(main._campaign_destination_marks().size()==1,"the actual map collector receives the tracked quest’s door marker")
	main.lantern_guide.hide_window()
	expect(main._campaign_destination_marks().size()==1,"hiding the quest window retains its tracked map marker")
	main.lantern_guide.set_campaign_tracked(false)
	expect(main._campaign_destination_marks().is_empty(),"the actual map collector drops an untracked quest")
	var hud:Control=load("res://src/ui/campaign_hud.gd").new();root.add_child(hud)
	var actions:Array=[];hud.action_requested.connect(func(action:String)->void:actions.append(action))
	hud.apply_state(travel,Vector2i(178,26),"landfall_town")
	expect(hud._entry.visible and hud._entry.text=="Do now · Show on map" and hud._shelves.text.contains("Mix three Life Essences"),"the quest instructions retain a checklist and an optional Do now action while travelling")
	hud._request_entry()
	expect(actions==["shelves_destination"],"Do now requests the map, never remote encounter entry or fast travel")
	travel.shelves.can_begin=true;hud.apply_state(travel,Vector2i(268,128),"landfall")
	hud._request_entry()
	expect(hud._entry.text=="Start the delivery escort" and actions.back()=="shelves","arrival offers an explicit event start using the normal campaign request")
	app.current_map="landfall";network.sent_frames.clear()
	travel.targets=[{"id":"shelves_start","object_id":61974,"tile":[268,128],"label":"Start the delivery escort","enabled":true}]
	main._on_campaign_target(61974,Vector2i(268,128),true)
	expect(network.sent_frames.size()==1 and network.sent_frames[0]==EloriaProtocol.use_map_object(61974),"an untracked public worksite still uses the normal interaction request")
	for identity:String in ["measure.shelves.brief","measure.shelves.gear","measure.shelves.resolved","measure.shelves.enriched"]:
		expect(not scene._definitions[identity].has("handoff"),identity+" releases the player without waiting for automatic travel")
	var spar:=snapshot();spar.scene={};spar.map="landfall_town";spar.shelves.private_practice=true;spar.shelves.sparring=true
	app.current_map="landfall_town";app.campaign=spar
	app.actors[20]={"actor_id":20,"kind":2,"health":35,"alive":true}
	app.actors[21]={"actor_id":21,"kind":2,"health":35,"alive":true}
	expect(main._spell_target_candidate(68,20),"Fire Bolt can target the actual NPC mentor during the private arena bout")
	expect(not main._spell_target_candidate(68,21),"other NPCs remain protected during that bout")
	spar.shelves.sparring=false
	expect(not main._spell_target_candidate(68,20),"the teacher stays protected in the practice range and during conversations")
	spar.shelves.sparring=true;app.current_map="landfall"
	expect(not main._spell_target_candidate(68,20),"a stale temple snapshot cannot expose an NPC on another map")
	hud.queue_free()
	var f:=return_fixture()
	f.scene.cancel("finished");return_tick(f,.6)
	f.state.active=false;f.state.completed=true;f.state.map="landfall_town";f.state.scene={}
	return_tick(f,.1,false,"landfall_town")
	expect(f.scene.blocks_input() and f.scene._exit_black.color.a>0.99,"completion keeps the return fade closed while the destination is loading")
	f.actor.position=Vector3(5,0,3);f.actor.server_target=f.actor.position
	return_tick(f,.1,true,"landfall_town");return_tick(f,.7,true,"landfall_town")
	expect(f.rig.focus.is_equal_approx(f.actor.position) and not f.scene.blocks_input(),"the completed supply quest reveals the actual local player when the destination is ready")
	f.scene.cancel("test_done");f.scene.queue_free();f.actor.queue_free();f.rig.queue_free()
	app.authenticated=false;main._clear_world_presentation()
	expect(await ContinentChunkStream.drain_workers(self,30000),"owned world workers drain after the supply probe")
	main.queue_free();await process_frame;await process_frame;GlbSceneCache.clear();NativeAnimationImporter.clear()
	print("Supply quest client: ",checks," checks; ",failures," failures")
	quit(1 if failures else 0)
