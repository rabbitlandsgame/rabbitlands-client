extends SceneTree
const Guidance := preload("res://src/world/campaign_guidance.gd")
const Hud := preload("res://src/ui/campaign_hud.gd")
var checks := 0
var failures := 0
func _init() -> void:run.call_deferred()
func expect(ok: bool, message: String) -> void:
	checks+=1
	if ok:print("PASS: ",message)
	else:
		failures+=1
		push_error(message)
static func snapshot() -> Dictionary:
	var state := {"version":1,"active":true,"run_id":"guidance-run","map":"greenlight","title":"The Ferry That Arrived Twice","key":"rescue","hint":"First inspect the damaged landing, then speak to Odo.","scene":{},"actors":{"odo":20},"targets":[
		{"id":"assess","object_id":61001,"label":"Inspect the damaged landing","tile":[450,310],"approach":[450,309],"enabled":true,"completed":false},
		{"id":"repair","object_id":61002,"label":"Compare the broken component","tile":[451,310],"enabled":false,"completed":false},
		{"id":"old","object_id":61003,"label":"Later work","tile":[452,310],"enabled":false,"completed":false},
		{"id":"return","object_id":61017,"label":"Return to the public road","tile":[450,308],"enabled":true,"completed":false}]}
	for id: int in range(61004,61017):
		state.targets.append({"id":"future_"+str(id),"object_id":id,"label":"Later field work","tile":[450+(id-61004)%5,314+(id-61004)/5],"enabled":false,"completed":false})
	state.targets.append({"id":"practice","object_id":61018,"label":"Record your own practical observation","tile":[450,310],"enabled":false,"completed":false})
	return state
func make_object(id:int,tile:Vector2i,adapter:CoordinateAdapter)->MapObject3D:
	var object:=MapObject3D.new();root.add_child(object)
	object.configure({"object_id":id,"kind":EloriaProtocol.MAP_OBJECT_INTERACTIVE,"x":tile.x,"y":tile.y,"label":"Work "+str(id)},adapter,{"interactives":{"roles":{},"models":{}}})
	return object
func run()->void:
	create_timer(60).timeout.connect(func()->void:push_error("Guidance test timed out");quit(1))
	var state:=snapshot();var adapter:=CoordinateAdapter.new({"serverOrigin":[435,448],"metresPerTile":1.0,"walkingHeight":2.5})
	var objects:Dictionary={}
	for row:Dictionary in state.targets:objects[int(row.object_id)]=make_object(row.object_id,Vector2i(row.tile[0],row.tile[1]),adapter)
	objects[9]=make_object(9,Vector2i(449,309),adapter)
	var odo:=Node3D.new();root.add_child(odo);odo.position=adapter.tile_center(450,313)
	var guidance:=Guidance.new();root.add_child(guidance)
	guidance.apply_snapshot(state,objects,{20:odo},"maps/nymara/greenlight.elm",Vector2i(450,308),true,false)
	expect((objects[61001].get_node("Ring") as Node3D).visible and objects[61001].collision_layer==MapObject3D.PICK_LAYER,"the available landing work keeps its existing clickable ground circle")
	expect(not (objects[61002].get_node("Ring") as Node3D).visible and objects[61002].collision_layer==0,"unavailable future work stops advertising a circle or intercepting ground clicks")
	var all_hidden := objects.size()==19
	for id: int in objects:
		if id in [61001,9]:continue
		all_hidden = all_hidden and not (objects[id].get_node("Ring") as Node3D).visible and not (objects[id].get_node("MapMarker") as Node3D).visible and objects[id].collision_layer==0
	expect(all_hidden,"all 18 declared opening sites are accounted for immediately, with every future, practice and Return marker hidden")
	expect(not (objects[61003].get_node("MapMarker") as Node3D).visible and not (objects[61017].get_node("Ring") as Node3D).visible,"completed work and the separate Return control do not clutter the next step")
	expect(objects[9].collision_layer==MapObject3D.PICK_LAYER and (objects[9].get_node("Ring") as Node3D).visible,"unrelated world objects are unchanged")
	expect(guidance._labels.assess.visible and guidance._labels.assess.text.contains("NEXT") and guidance._labels.assess.text.contains("Inspect the damaged landing"),"the first circle is named for the actual first action")
	guidance.apply_snapshot(state,objects,{20:odo},"greenlight",Vector2i(450,310),true,false)
	expect(guidance._labels.assess.text.ends_with("Interact"),"a nearby work label changes from walking guidance to interaction")
	var choices:=state.duplicate(true)
	for index:int in range(4):choices.targets[index].enabled=true;choices.targets[index].completed=false
	choices.targets[4].enabled=true
	guidance.apply_snapshot(choices,objects,{20:odo},"greenlight",Vector2i(450,310),true,false)
	var visible_labels:=0;var forced_next:=false
	for label:Label3D in guidance._labels.values():
		if label.visible:
			visible_labels+=1;forced_next=forced_next or label.text.begins_with("NEXT")
	expect(visible_labels==3 and not forced_next,"several available work choices get at most three labels without inventing a preferred resolution")
	choices.approach="repair"
	expect(Guidance.legend(choices).contains("current objective") and not Guidance.legend(choices).contains("Choose one"),"choosing a rescue approach keeps the current objective as the lead instruction")
	choices.targets[1].id="damage"
	expect(Guidance.work_targets(choices)[0].id=="damage" and Guidance.work_targets(choices).size()==4,"the selected approach leads the checklist without removing alternate available methods")
	guidance.apply_snapshot(state,objects,{20:odo},"greenlight",Vector2i(450,310),true,true)
	expect(not guidance._labels.assess.visible and not (objects[61001].get_node("Ring") as Node3D).visible and objects[61001].collision_layer==0,"cinematic entry, playback and return hide field clutter and disable its picks")
	guidance.apply_snapshot(state,objects,{20:odo},"greenlight",Vector2i(450,310),false,false)
	expect(not guidance._labels.assess.visible and objects[61001].collision_layer==MapObject3D.PICK_LAYER,"Untrack hides guidance text while preserving ordinary available world work")
	var hud:=Hud.new();root.add_child(hud);hud.apply_state(state,Vector2i(450,308),"greenlight")
	expect(hud._guidance.visible and hud._guidance.text.contains("Next: Inspect") and hud._guidance.text.contains("Ground circles mark available work"),"the existing quest card explains the circles and identifies the first action")
	expect(hud._targets.get_child_count()==1,"the field list shows ready work rather than future disabled tasks")
	expect(hud._scroll.get_index()<hud._guidance.get_index() and hud._scroll.get_index()<hud._party.get_index(),"the next action is placed above the legend and party details in the existing quest card")
	var waiting:=state.duplicate(true)
	for row:Dictionary in waiting.targets:row.enabled=false
	waiting.party={"waiting_for_scene":true}
	hud.apply_state(waiting,Vector2i(450,308),"greenlight")
	expect(not hud._scroll.visible and hud._guidance.text.contains("Waiting for the party"),"a party scene barrier explains why work is not ready and leaves no empty action box")
	hud.apply_state(state,Vector2i(450,308),"greenlight")
	var requests:Array=[];hud.target_requested.connect(func(id:int,tile:Vector2i,near:bool)->void:requests.append([id,tile,near]))
	hud.apply_state(state,Vector2i(440,300),"greenlight");hud._request_target("assess",61001)
	expect(requests[0]==[61001,Vector2i(450,309),false],"a distant work button requests its safe approach")
	state.targets[0].completed=true;state.targets[0].enabled=false
	var talk:Dictionary={"id":"talk_odo","object_id":0,"actor_id":20,"role":"odo","label":"Speak to Odo Fenn","tile":[450,313],"approach":[450,312],"range":4,"enabled":true,"completed":false}
	state.targets.append(talk)
	expect(EloriaProtocol.decode_campaign(JSON.stringify(state).to_utf8_buffer()).type=="campaign","the real role-bound NPC navigation contract decodes")
	for invalid:Dictionary in [{"actor_id":1.5},{"actor_id":-1},{"actor_id":20,"role":""},{"actor_id":21},{"object_id":61001}]:
		var bad:=state.duplicate(true);bad.targets[-1].merge(invalid,true)
		expect(EloriaProtocol.decode_campaign(JSON.stringify(bad).to_utf8_buffer()).type=="invalid","malformed or mismatched NPC targets never become interaction requests")
	guidance.apply_snapshot(state,objects,{20:odo},"greenlight",Vector2i(450,310),true,false)
	expect(guidance._labels.talk_odo.get_parent()==odo and guidance._labels.talk_odo.text.contains("NEXT"),"speaking to Odo is labelled above the actual NPC rather than an invented use object")
	hud.apply_state(state,Vector2i(450,310),"greenlight");var talks:Array=[]
	hud.actor_target_requested.connect(func(id:int,tile:Vector2i,near:bool)->void:talks.append([id,tile,near]));hud._request_target("talk_odo",0)
	expect(talks==[[20,Vector2i(450,313),true]] and requests.size()==1,"a nearby conversation is distinct from an ordinary movement checkpoint")
	state.targets.append({"id":"checkpoint","object_id":0,"label":"Walk the next safe post","tile":[449,311],"enabled":true,"completed":false})
	hud.apply_state(state,Vector2i(450,310),"greenlight");hud._request_target("checkpoint",0)
	expect(requests.size()==2 and requests[1][0]==0,"non-NPC zero-object checkpoints remain movement-only")
	state.targets[1].enabled=true;guidance.apply_snapshot(state,objects,{20:odo},"greenlight",Vector2i.ZERO,true,false)
	expect(objects[61002].collision_layer==MapObject3D.PICK_LAYER,"the next authoritative work step restores its existing world interaction")
	state.targets.erase(state.targets[1]);guidance.apply_snapshot(state,objects,{20:odo},"greenlight",Vector2i.ZERO,true,false)
	expect(objects[61002].collision_layer==0,"a removed owned target cannot leave a stale clickable circle")
	guidance.apply_snapshot(state,objects,{20:odo},"twinbrook",Vector2i.ZERO,true,false)
	expect(guidance._labels.is_empty() and objects[61001].collision_layer==MapObject3D.PICK_LAYER and not objects[61001].has_meta("campaign_work_available"),"map changes restore original object presentation and remove guidance labels")
	var network:=root.get_node("Network");var recorder:=GDScript.new()
	recorder.source_code='extends "res://src/network/network_client.gd"\nvar sent_frames:Array=[]\nfunc send_frame(frame:PackedByteArray,_sensitive:=false)->Error:\n\tsent_frames.append(frame)\n\treturn OK\n'
	expect(recorder.reload()==OK,"the offline production transport recorder compiles")
	network.set_script(recorder);network.call("block_for_hud_preview")
	var main:Node=(load("res://src/app/main.tscn") as PackedScene).instantiate();root.add_child(main);await process_frame;main.set_process(false);main.hide()
	var app:=root.get_node("AppState");app.authenticated=true;app.local_actor_id=1;app.current_map="greenlight";app.campaign=state
	app.actors[20]={"actor_id":20,"kind":2,"name":"Odo Fenn"};main.adapter=adapter
	var local:=Node3D.new();root.add_child(local);local.position=adapter.tile_center(440,300);main.actor_nodes[1]=local
	var frames:Array=network.get("sent_frames");frames.clear()
	main.call("_on_campaign_actor_target",20,Vector2i(450,313),true)
	expect(frames.size()==1 and frames[0]==EloriaProtocol.move_to(450,312),"Main recalculates real proximity and moves to Odo's free approach while far away")
	local.position=adapter.tile_center(450,310);main.call("_on_campaign_actor_target",20,Vector2i(450,312),false)
	expect(frames.size()==2 and frames[1]==EloriaProtocol.touch_actor(20),"a physically nearby Odo marker opens the ordinary native NPC conversation")
	app.actors[20].kind=1;main.call("_on_campaign_actor_target",20,Vector2i(450,313),true)
	expect(frames.size()==2,"a non-NPC replicated actor never receives the conversation action")
	app.actors[20].kind=2;state.actors.odo=99;main.call("_on_campaign_actor_target",20,Vector2i(450,313),true)
	expect(frames.size()==2,"a stale actor binding cannot redirect a conversation")
	state.actors.odo=20;state.targets[0].completed=false;state.targets[0].enabled=true;local.position=adapter.tile_center(440,300)
	main.call("_activate_map_object",objects[61001],false)
	expect(frames.size()==3 and frames[2]==EloriaProtocol.move_to(450,309),"a distant world circle uses the same walk-to-approach behavior as the quest card")
	local.position=adapter.tile_center(450,310);main.call("_activate_map_object",objects[61001],false)
	expect(frames.size()==4 and frames[3]==EloriaProtocol.use_map_object(61001),"clicking the circle again when near performs the existing use action")
	state.targets[0].enabled=false;main.call("_activate_map_object",objects[61001],false)
	expect(frames.size()==4,"disabled world work cannot be activated by a stale click")
	app.current_map="twinbrook";main.call("_on_campaign_actor_target",20,Vector2i(450,313),true)
	expect(frames.size()==4,"foreign-map NPC guidance sends no movement or talk request")
	main.queue_free();local.queue_free();hud.queue_free();guidance.queue_free();odo.queue_free()
	for object:Node in objects.values():object.queue_free()
	await process_frame;await process_frame
	print("campaign guidance: ",checks," checks; ",failures," failures")
	quit(1 if failures else 0)
