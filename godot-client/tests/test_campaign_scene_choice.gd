extends SceneTree
var checks := 0
var failures := 0
var main: Node
var scene_double: Node
var app: Node
var network: Node
var local: Node3D
var odo: Node3D

static func snapshot() -> Dictionary:
	return {"version":1,"active":true,"run_id":"choice-run","map":"greenlight","title":"The Ferry That Arrived Twice",
		"actors":{"odo":20},"targets":[],"party":{"role":"owner","owner":"Aster"},"approach":"",
		"scene":{"id":"measure.landing.plan","token":"choice-run:measure.landing.plan","choice":{
			"id":"opening_rescue","title":"Choose the rescue plan","selected":"","response":"","owner":"Aster","owner_is_you":true,"can_choose":true,
			"options":[{"id":"defend","label":"Protect the crew","detail":"Keep the work site clear."},{"id":"repair","label":"Repair the landing","detail":"Inspect, compare, fit a plank and test."},{"id":"evacuate","label":"Guide the worker out","detail":"Prepare and walk the safe refuge route."}]}}}

func _init() -> void:run.call_deferred()
func expect(ok: bool, message: String) -> void:
	checks+=1
	if ok:print("PASS: ",message)
	else:
		failures+=1
		push_error(message)
func decode(state: Dictionary) -> Dictionary:
	return EloriaProtocol.decode_campaign(JSON.stringify(state).to_utf8_buffer())
func reset_main() -> void:
	app.authenticated=true;app.death={};app.local_actor_id=1;app.current_map="greenlight";app.campaign=snapshot()
	app.actors.clear();app.actors[20]={"actor_id":20,"kind":2,"name":"Odo Fenn"}
	main.set("_disconnect_console_active",false);main.set("actor_nodes",{1:local,20:odo})
	(main.get("_grounded_actors") as Dictionary).clear();(main.get("_grounded_actors") as Dictionary)[1]=true
	scene_double.set("playing",true);scene_double.set("test_replay",false);scene_double.set("retries",0)
	scene_double.set("test_context",{"run_id":"choice-run","token":"choice-run:measure.landing.plan","id":"opening_rescue","waiting":true})
	(network.get("sent_frames") as Array).clear();network.set("fail_send",false)
func run() -> void:
	create_timer(75).timeout.connect(func()->void:push_error("Scene-choice checks timed out");quit(1))
	var state:=snapshot()
	expect(decode(state).get("type")=="campaign","the explicit owner scene-choice contract decodes")
	var legacy:=state.duplicate(true);legacy.scene.erase("choice")
	expect(decode(legacy).get("type")=="campaign","older snapshots without scene-choice metadata remain compatible")
	for selected:String in ["defend","repair","evacuate"]:
		var recorded:=state.duplicate(true);recorded.scene.choice.selected=selected;recorded.scene.choice.can_choose=false;recorded.scene.choice.response="Odo acknowledges the recorded plan."
		expect(decode(recorded).get("type")=="campaign",selected+" remains readable with all three replay options")
	var helper:=state.duplicate(true);helper.party.role="helper";helper.scene.choice.can_choose=false;helper.scene.choice.owner_is_you=false
	expect(decode(helper).get("type")=="campaign","party helpers receive all three choices as read-only information")
	for bad:Dictionary in [{"id":"other_choice"},{"selected":"loot"},{"selected":"repair"},{"owner_is_you":false},{"can_choose":1},{"owner_is_you":"true"},{"owner":null},{"response":42},{"title":[]},{"options":[]},{"options":[{"id":"repair","label":"Repair","detail":""},{"id":"repair","label":"Again","detail":""},{"id":"evacuate","label":"Leave","detail":""}]}]:
		var malformed:=state.duplicate(true);malformed.scene.choice.merge(bad,true)
		expect(decode(malformed).get("type")=="invalid","malformed authority, selection or option metadata is rejected")
	var missing:=state.duplicate(true);missing.scene.choice.erase("selected")
	expect(decode(missing).get("type")=="invalid","a missing selected value is rejected without a dictionary access error")
	for field:String in ["label","detail"]:
		var bad_option:=state.duplicate(true);bad_option.scene.choice.options[0][field]=false
		expect(decode(bad_option).get("type")=="invalid","choice option "+field+" must be ordinary text")
	var foreign_option:=state.duplicate(true);foreign_option.scene.choice.options[0].id="steal"
	expect(decode(foreign_option).get("type")=="invalid","an unknown action cannot be smuggled into the choice list")
	network=root.get_node("Network");var recorder:=GDScript.new()
	recorder.source_code='extends "res://src/network/network_client.gd"\nvar sent_frames:Array=[]\nvar fail_send:=false\nfunc send_frame(frame:PackedByteArray,_sensitive:=false)->Error:\n\tif fail_send:return ERR_UNAVAILABLE\n\tsent_frames.append(frame)\n\treturn OK\n'
	expect(recorder.reload()==OK,"the isolated production transport recorder compiles")
	network.set_script(recorder);network.call("block_for_hud_preview")
	var frames:Array=network.get("sent_frames")
	for option:String in ["defend","repair","evacuate"]:
		var before:=frames.size()
		expect(network.call("campaign_scene_choice","choice-run","choice-run:measure.landing.plan",option)==OK and frames.size()==before+1 and frames.back()==EloriaProtocol.chat("#campaign scene_choice choice-run choice-run:measure.landing.plan "+option),"the dedicated "+option+" command binds the exact run and scene token")
	for args:Array in [["bad run","scene","repair"],["run","bad token","repair"],["run","scene","steal"],["","scene","defend"]]:
		var before:=frames.size()
		expect(network.call("campaign_scene_choice",args[0],args[1],args[2])==ERR_INVALID_PARAMETER and frames.size()==before,"invalid transport identities or options never reach the wire")
	main=(load("res://src/app/main.tscn") as PackedScene).instantiate();root.add_child(main);main.set_process(false);main.hide()
	var double_script:=GDScript.new()
	double_script.source_code='extends "res://src/world/campaign_scene.gd"\nvar test_context:Dictionary={}\nvar test_replay:=false\nvar retries:=0\nfunc choice_context()->Dictionary:return test_context\nfunc is_replaying()->bool:return test_replay\nfunc choice_send_failed()->void:retries+=1\n'
	expect(double_script.reload()==OK,"the Main guard fixture implements the controller's read-only choice context")
	var previous:Node=main.get("campaign_scene");scene_double=double_script.new();main.add_child(scene_double);main.set("campaign_scene",scene_double);previous.queue_free()
	local=Node3D.new();root.add_child(local);local.position=Vector3(100,2.5,100)
	odo=Node3D.new();root.add_child(odo);odo.position=Vector3(15,2.5,135)
	app=root.get_node("AppState");reset_main()
	expect(bool(main.call("_world_input_blocked")),"ordinary world input is blocked while the cinematic decision is offered")
	for option:String in ["defend","repair","evacuate"]:
		reset_main();main.call("_on_campaign_scene_choice",option)
		expect(frames.size()==1 and frames[0]==EloriaProtocol.chat("#campaign scene_choice choice-run choice-run:measure.landing.plan "+option),"Main accepts the current owner "+option+" choice without an NPC proximity requirement")
	for blocker:String in ["replay","helper","not_owner","already_selected","stale_run","stale_token","stale_choice","not_waiting","wrong_scene","foreign_map","travel","inactive","dead","disconnect","signed_out","ungrounded","not_playing","missing_odo","non_npc_odo","unknown_option"]:
		reset_main()
		match blocker:
			"replay":scene_double.set("test_replay",true)
			"helper":app.campaign.party.role="helper"
			"not_owner":app.campaign.scene.choice.owner_is_you=false;app.campaign.scene.choice.can_choose=false
			"already_selected":app.campaign.scene.choice.selected="repair";app.campaign.scene.choice.can_choose=false
			"stale_run":scene_double.get("test_context").run_id="older-run"
			"stale_token":scene_double.get("test_context").token="older-token"
			"stale_choice":scene_double.get("test_context").id="older-choice"
			"not_waiting":scene_double.get("test_context").waiting=false
			"wrong_scene":app.campaign.scene.id="measure.landing.arrival"
			"foreign_map":app.current_map="twinbrook"
			"travel":app.campaign.travel={"map":"twinbrook","npc":"Odo Fenn"}
			"inactive":app.campaign.active=false
			"dead":app.death={"dead":true}
			"disconnect":main.set("_disconnect_console_active",true)
			"signed_out":app.authenticated=false
			"ungrounded":(main.get("_grounded_actors") as Dictionary).clear()
			"not_playing":scene_double.set("playing",false)
			"missing_odo":(main.get("actor_nodes") as Dictionary).erase(20)
			"non_npc_odo":app.actors[20].kind=1
		main.call("_on_campaign_scene_choice","steal" if blocker=="unknown_option" else "repair")
		expect(frames.is_empty(),blocker+" rejects a queued cinematic choice without network or gameplay effects")
	reset_main();app.campaign.erase("party");main.call("_on_campaign_scene_choice","repair")
	expect(frames.size()==1,"legacy solo owners work without inventing a party role")
	reset_main();network.set("fail_send",true);main.call("_on_campaign_scene_choice","repair")
	expect(frames.is_empty() and int(scene_double.get("retries"))==1,"a failed send releases the controller's pending state for a local retry")
	expect(str(app.campaign.scene.choice.selected).is_empty() and str(app.campaign.approach).is_empty(),"sending or failing a choice never changes local quest progress")
	main.set("actor_nodes",{});app.authenticated=false;main.queue_free();local.queue_free();odo.queue_free()
	await process_frame;await process_frame
	print("campaign scene choice: ",checks," checks; ",failures," failures")
	quit(1 if failures else 0)
